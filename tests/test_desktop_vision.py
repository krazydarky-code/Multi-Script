# SPDX-License-Identifier: GPL-3.0-or-later
"""test_desktop_vision.py - the "see desktop apps" feature.

Covers both halves of the contract:
  * the pure logic in runtime/desktop_vision.py (parsers, capability probing,
    the honest-fidelity rules, and the no-auto-install guarantee), and
  * the bridge-side wiring (ms_app_* / ms_surface_list builtin tools, the
    desktop_vision import being optional rather than fatal, and the fact that
    the tool descriptions tell the model the truth about what each one does).

The module shells out to OS binaries, so every platform binary is stubbed at
the _run boundary. That keeps the test deterministic on a Windows CI box while
still exercising the REAL parsing code - which is where the bugs actually live.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "runtime"))

failures = []


def check(cond, label):
    if cond:
        print(f"  ok  {label}")
    else:
        print(f"  FAIL {label}")
        failures.append(label)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 1. module imports without any optional dependency ───────────────────
print("\n1. desktop_vision imports with only the stdlib")
dv = load("desktop_vision", ROOT / "runtime" / "desktop_vision.py")
check(hasattr(dv, "capabilities"), "exposes capabilities()")
check(hasattr(dv, "setup_plan"), "exposes setup_plan()")
check(hasattr(dv, "list_apps"), "exposes list_apps()")
check(hasattr(dv, "list_windows"), "exposes list_windows()")
check(hasattr(dv, "read_window"), "exposes read_window()")
check(hasattr(dv, "snapshot"), "exposes snapshot()")

# ── 2. capabilities() is honest and total ───────────────────────────────
print("\n2. capabilities() reports the three escalating levels truthfully")
caps = dv.capabilities()
for key in ("platform", "processes", "windows", "titles", "text", "backends", "notes"):
    check(key in caps, f"capabilities has '{key}'")
check(isinstance(caps["processes"], bool), "processes is a bool, not a guess")
check(isinstance(caps["windows"], bool), "windows is a bool")
check(caps["platform"] == sys.platform, "platform matches sys.platform")
check(isinstance(caps["notes"], list), "notes is a list")

# ── 3. setup_plan never installs anything ───────────────────────────────
print("\n3. setup_plan() describes commands but installs nothing")
plan = dv.setup_plan()
check("steps" in plan and isinstance(plan["steps"], list), "returns concrete steps")
check(plan["total"] == len(plan["steps"]), "total matches the step list")
check(all({"id", "label", "satisfied", "command", "why"} <= set(s) for s in plan["steps"]),
      "every step is fully described")
check("never" in plan["note"].lower() or "not installed automatically" in plan["note"].lower(),
      "the plan states it will not auto-install")
check(any(s["required"] for s in plan["steps"]) or plan["ready"],
      "either a required tool exists or the platform is already ready")

# ── 4. Windows tasklist CSV parsing ─────────────────────────────────────
print("\n4. process parsing handles the real tasklist CSV shape")
fake_tasklist = (
    '"RobloxStudioBeta.exe","1234","Console","1","512,340 K"\n'
    '"chrome.exe","5678","Console","1","204,800 K"\n'
    '"svchost.exe","999","Services","0","8,000 K"\n'
)
orig_run = dv._run
orig_plat = dv.sys.platform
dv._run = lambda cmd, timeout=8: fake_tasklist if "tasklist" in cmd else ""
dv.sys.platform = "win32"
rows = dv._processes_windows()
check(len(rows) == 3, f"parsed all three processes (got {len(rows)})")
by_name = {r["name"]: r for r in rows}
check(by_name["RobloxStudioBeta.exe"]["pid"] == 1234, "pid parsed from CSV")
check(by_name["RobloxStudioBeta.exe"]["app"] == "Roblox Studio", "friendly app name resolved")
check(by_name["chrome.exe"]["app"] == "Google Chrome", "chrome recognised")
check(by_name["svchost.exe"]["app"] == "", "unknown process yields no invented app name")

apps = dv.list_apps()
check(all(r["app"] for r in apps["apps"]), "list_apps hides unknowns by default")
apps_all = dv.list_apps(include_unknown=True)
check(len(apps_all["apps"]) == 3, "include_unknown surfaces the long tail")
apps_q = dv.list_apps(query="roblox")
check(len(apps_q["apps"]) == 1 and apps_q["apps"][0]["name"] == "RobloxStudioBeta.exe",
      "query filters case-insensitively")

# ── 5. window enumeration merges process names ──────────────────────────
print("\n5. windows carry real titles and a matched app name")
dv._windows_windows = lambda: [
    {"handle": 10, "pid": 1234, "title": "My Game - Roblox Studio", "bounds": {"x": 0, "y": 0, "width": 100, "height": 100}},
    {"handle": 11, "pid": 5678, "title": "Inbox", "bounds": {"x": 0, "y": 0, "width": 100, "height": 100}},
]
win = dv.list_windows()
check(win["count"] == 2, "both windows returned")
check(win["degraded"] is False, "not degraded when the real backend answered")
check(win["windows"][0]["title"] == "My Game - Roblox Studio", "real title preserved verbatim")
check(win["windows"][0]["app"] == "Roblox Studio", "window got its app from pid->process map")
check("handle" in win["windows"][0], "handle is exposed for follow-up reads")
wf = dv.list_windows(query="inbox")
check(wf["count"] == 1, "window query filters on title")

# ── 6. degraded mode is flagged, never silent ───────────────────────────
print("\n6. a missing window backend degrades loudly, not silently")
dv._windows_windows = lambda: None
degraded = dv.list_windows()
check(degraded["degraded"] is True, "degraded flag set")
check("process names" in degraded["note"], "note explains titles may be process names")
dv._windows_windows = lambda: []

# ── 7. read_window never fabricates content ─────────────────────────────
print("\n7. read_window reports an honest fidelity level")
dv.sys.platform = "linux"
r_none = dv.read_window()
check(r_none["fidelity"] == "none", "empty request yields fidelity 'none'")
check("error" in r_none or r_none["text"] == "", "no invented text")
r_title = dv.read_window(title="Some Window")
check(r_title["fidelity"] == "title-only", "title-only fidelity when only a title exists")
check(r_title["text"] == "Some Window", "the title is returned as the text honestly")
dv.sys.platform = orig_plat

# ── 8. snapshot is read-only and complete ───────────────────────────────
print("\n8. snapshot() returns a full picture without capturing anything")
dv._run = orig_run
snap = dv.snapshot()
for key in ("platform", "capabilities", "apps", "windows", "appCount", "windowCount", "degraded", "note"):
    check(key in snap, f"snapshot has '{key}'")
check("screenshot" in snap["note"].lower() or "process names" in snap["note"].lower(),
      "snapshot states it did not capture the screen")

# ── 9. bridge wires the tools and degrades if the module is missing ─────
print("\n9. bridge exposes the desktop tools and survives a missing module")
bridge_src = (ROOT / "runtime" / "bridge.py").read_text(encoding="utf-8")
for tool in ["ms_surface_list", "ms_app_list", "ms_app_snapshot",
             "ms_app_read_window", "ms_app_setup_plan"]:
    check(f'"name": "{tool}"' in bridge_src, f"bridge advertises {tool}")
check("import desktop_vision as _desktop" in bridge_src, "bridge imports desktop_vision positionally")
check("DESKTOP_VISION_ERROR" in bridge_src, "bridge records why the import failed")
check('DESKTOP_VISION is None' in bridge_src, "handlers refuse cleanly when the module is absent")
check("desktop vision failed:" in bridge_src, "handler errors are wrapped, not raw")
check("setup_plan" in bridge_src, "the install-plan tool is reachable from the bridge")

# ── 10. the model is told the truth in the descriptions ─────────────────
print("\n10. tool descriptions are honest about scope and safety")
check("Read-only" in bridge_src, "at least one surface tool is documented read-only")
check("never screenshots" in bridge_src.lower() or "no screenshots" in bridge_src.lower(),
      "app_list states it does not screenshot")
check("Installs NOTHING" in bridge_src or "installs NOTHING" in bridge_src,
      "setup_plan says it installs nothing")
check("Refuses javascript:" in bridge_src or "refuses javascript:" in bridge_src.lower(),
      "surface_open documents the scheme refusal")
check("window half" in bridge_src or "tab half" in bridge_src,
      "ms_surface_list explains the two-process split")

# ── 11. extension side: worker verbs + merged list ──────────────────────
print("\n11. the extension owns the tab half and merges both halves")
bg = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
for verb in ["surface_list", "surface_focus", "surface_read", "surface_open",
             "surface_type", "surface_close"]:
    check(f'case "{verb}"' in bg, f"worker handles {verb}")
check("function surfaceList" in bg, "surfaceList is defined")
check("executeScript" in bg, "reads use executeScript so no extra host permissions are needed")
check('only http: and https: are allowed' in bg, "surface_open refuses non-web schemes")
check("SURFACE_MAX_TEXT" in bg, "tab readback is capped to keep prompts small")

main_js = (ROOT / "extension" / "core" / "main.js").read_text(encoding="utf-8")
check("function mergeSurfaceList" in main_js, "main.js merges windows+tabs")
check("ms_surface_list" in main_js, "main.js intercepts ms_surface_list locally")
check('bg({ type: `surface_${verb}`' in main_js, "surface verbs are forwarded to the worker")
check("mergeSurfaceList(winHalf, tabHalf)" in main_js, "the merge is actually wired in")

man = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
check("tabs" in man["permissions"], "manifest requests the tabs permission")
check("scripting" in man["permissions"], "manifest keeps scripting for executeScript")

# ── 12. every advertised surface tool is routed somewhere ───────────────
print("\n12. no advertised surface tool is a dead end")
advertised = ["ms_surface_list", "ms_surface_read", "ms_surface_type",
              "ms_surface_open", "ms_surface_focus",
              "ms_app_list", "ms_app_snapshot", "ms_app_read_window", "ms_app_setup_plan"]
for tool in advertised:
    in_bridge = f'"name": "{tool}"' in bridge_src
    handled_bridge = f'name in ("ms_app_list"' in bridge_src or f'== "{tool}"' in bridge_src or f'name == "{tool}"' in bridge_src
    handled_ext = tool in main_js or f'"{tool}"' in main_js
    check(in_bridge and (handled_bridge or handled_ext), f"{tool} is advertised AND handled")

# ── 13. macOS + Linux paths (regression: these were never exercised) ────
# 6.29.0 fixed a real bug here: the friendly-name map was keyed ONLY on Windows
# image names ("blender.exe"), so on macOS/Linux every process was filtered out
# and "what desktop apps are open" silently returned nothing. Nothing caught it
# because this file only ever stubbed win32 and linux.
print("\n13. POSIX process names resolve, and Wayland windows are found")
dv.sys.platform = "darwin"
fake_ps = (
    "  501 /Applications/RobloxStudio.app/Contents/MacOS/RobloxStudio\n"
    "  502 /Applications/Unity/Hub/Editor/2022.3/Unity.app/Contents/MacOS/Unity\n"
    "  503 /Applications/Blender.app/Contents/MacOS/Blender\n"
    "  504 /opt/homebrew/bin/godot\n"
    "  505 /usr/sbin/cupsd\n"
)
dv._run = lambda cmd, timeout=8: fake_ps if "ps" in cmd else ""
posix_apps = {r["name"]: r["app"] for r in dv._processes_posix()}
check(posix_apps.get("RobloxStudio") == "Roblox Studio", "macOS RobloxStudio -> Roblox Studio")
check(posix_apps.get("Unity") == "Unity Editor", "macOS Unity -> Unity Editor (was never matched)")
check(posix_apps.get("Blender") == "Blender", "macOS Blender -> Blender")
check(posix_apps.get("godot") == "Godot", "Linux godot -> Godot")
check(posix_apps.get("cupsd") == "", "unknown POSIX process yields no invented app name")

# The same normalised lookup must keep the Windows names working.
check(dv._friendly_app("Blender.exe") == "Blender", "Windows .exe name still resolves")
check(dv._friendly_app("blender") == "Blender", "bare POSIX name resolves")
check(dv._friendly_app("Blender (deleted)") == "Blender", "Linux '(deleted)' suffix is stripped")
check(dv._friendly_app("communityd") == "", "a name merely CONTAINING a key is not mislabelled")

# macOS window enumeration goes through osascript.
dv._run = lambda cmd, timeout=8: ("Finder, Unity, Blender" if "background only is false" in " ".join(cmd)
                                  else "My Game - Unity")
mac_windows = dv._windows_macos()
check(mac_windows is not None and len(mac_windows) == 3, "osascript app list parsed")
check(mac_windows[0]["app"] == "Finder" and mac_windows[0]["title"] == "My Game - Unity",
      "osascript titles are attached to their app")

# A missing osascript degrades loudly rather than silently.
dv._run = lambda cmd, timeout=8: ""
check(dv._windows_macos() is None, "missing osascript -> None (degraded), not an empty list")

# Wayland: wmctrl (X11-only) answers nothing, swaymsg answers -> real titles.
sway_tree = json.dumps({"type": "root", "nodes": [
    {"type": "output", "nodes": [
        {"type": "con", "name": "Editor - Godot", "pid": 700, "nodes": []},
    ]},
]})
dv._run = lambda cmd, timeout=8: "" if "wmctrl" in cmd else (sway_tree if "swaymsg" in cmd else "")
wayland = dv._windows_linux()
check(wayland is not None and wayland[0]["title"] == "Editor - Godot",
      "swaymsg fallback yields real Wayland titles when wmctrl is blind")

# No X11 and no Wayland backend -> None, so list_windows can flag degraded.
dv._run = lambda cmd, timeout=8: ""
check(dv._windows_linux() is None, "no X11/Wayland backend -> None (degraded), never guessed")

dv.sys.platform = orig_plat
dv._run = orig_run

if failures:
    print(f"\ntest_desktop_vision: {len(failures)} FAILED")
    for f in failures:
        print("   -", f)
    sys.exit(1)
print("\ntest_desktop_vision: 13 sections passed")
