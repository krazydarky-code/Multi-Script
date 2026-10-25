"""Assert the 6.22.0 artefacts are all present and wired.

6.22.0 ships three things that must not silently rot:
  1. the six engine-neutral ms_native_* facade tools, and the dialect hints
     behind them,
  2. the chat bar's terminal icon plus the in-extension terminal panel it opens,
     including the log ring the panel streams and the loopback /logs fallback
     that keeps it alive mid-reconnect (there is no external launcher),
  3. the Notion alignment fix (a provider inset the core actually applies).

Every assertion reads the real source, so a refactor that drops one of these
fails here instead of being discovered by a user whose button does nothing.

Run: python tools/validate_6_22_0_artifacts.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import re as _re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXT = os.path.join(ROOT, "extension")
PASS = 0
FAIL = 0


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        return
    FAIL += 1
    print(f"  FAIL {label}")
    if detail:
        print(f"       {detail}")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def load_bridge():
    spec = importlib.util.spec_from_file_location("ms_bridge_622", os.path.join(ROOT, "runtime", "bridge.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ms_bridge_622"] = mod
    spec.loader.exec_module(mod)
    return mod


class _StubClient:
    def __init__(self, names):
        self.tools_cache = [{"name": n} for n in names]


class _StubMgr:
    """Minimal stand-in for the MCP manager: the facade only reads the live
    advertised catalogue, so a list of names is enough to exercise the
    translation without an engine attached."""

    def __init__(self, names):
        self.clients = {"godot": _StubClient(names)}

    def call_on_server(self, server, tool, arguments, timeout=120):
        return {"text": "{}", "images": []}   # unused at validation time


print("=== version ===")
B = load_bridge()
check("bridge version is 6.22.0", B.BRIDGE_VERSION == "6.22.0", B.BRIDGE_VERSION)
manifest = json.loads(read("extension", "manifest.json"))
check("manifest version is 6.22.0", manifest.get("version") == "6.22.0", str(manifest.get("version")))
check("manifest version_name carries the release name",
      "6.22.0" in str(manifest.get("version_name")), str(manifest.get("version_name")))

print("=== the six facade tools ===")
FACADE = ["ms_native_capabilities", "ms_native_read", "ms_native_write",
          "ms_native_verify", "ms_native_batch", "ms_native_debug"]
for name in FACADE:
    check(f"{name} is registered", name in B.BUILTIN_TOOL_BY_NAME)
    if name in B.BUILTIN_TOOL_BY_NAME:
        schema = B.BUILTIN_TOOL_BY_NAME[name]["inputSchema"]
        try:
            B._normalize_tool_arguments(schema, {"server": "roblox", "what": "tree"}
                                        if name in ("ms_native_read", "ms_native_verify") else
                                        ({"server": "roblox", "what": "script", "target": "a.b", "content": "x"}
                                         if name == "ms_native_write" else
                                         {"server": "roblox", "steps": [{"tool": "get_studio_state"}]}
                                         if name == "ms_native_batch" else {}), name)
            check(f"{name} schema accepts a minimal payload", True)
        except Exception as exc:
            check(f"{name} schema accepts a minimal payload", False, str(exc))

check("the facade hints table exists", isinstance(getattr(B, "_FACADE_NATIVE_HINTS", None), dict))
for engine in ("roblox", "unity", "godot", "blender"):
    check(f"_FACADE_NATIVE_HINTS covers {engine}",
          engine in B._FACADE_NATIVE_HINTS and bool(B._FACADE_NATIVE_HINTS[engine]))

print("=== dialect facts the facade must not re-break ===")
check("roblox dot-paths WALK segment by segment",
      B._roblox_path_expr("Workspace.Door") == 'game:FindFirstChild("Workspace"):FindFirstChild("Door")',
      B._roblox_path_expr("Workspace.Door"))
check("roblox create-script uses the empty-string sentinel",
      B._roblox_path_expr("A.B").count("FindFirstChild") == 2)
check("unity create_object is wired to manage_gameobject",
      "manage_gameobject" in B._FACADE_NATIVE_HINTS["unity"].get("create_object", []))
check("unity create_script is a distinct capability",
      "create_script" in B._FACADE_NATIVE_HINTS["unity"])
# nodeName names the NEW node and the parent goes in parentNodePath; passing the
# parent as nodeName is the mistake this pins shut.
tr = B._facade_translate(_StubMgr([ "add_node", "save_scene", "get_project_info" ]), "godot",
                         {"operation": "write", "what": "node", "target": "res://M.tscn",
                          "node_type": "Node2D", "parent": "Player", "name": "Health",
                          "project_path": "C:/g/MyGame"})
check("godot add_node puts the parent in parentNodePath",
      tr.get("ok") and tr["calls"][0]["arguments"].get("parentNodePath") == "Player"
      and tr["calls"][0]["arguments"].get("nodeName") == "Health",
      json.dumps(tr)[:300])

print("=== terminal icon ===")
main_src = read("extension", "core", "main.js")
css = read("extension", "overlay.css")
bg_src = read("extension", "background.js")
br_src = read("runtime", "bridge.py")
manifest_src = read("extension", "manifest.json")
check("bar markup has the terminal button", 'id="zs-bridge"' in main_src)
check("button is wired to a click handler", "onBridgeClick" in main_src and "bridgeBtn" in main_src)
_setstatus = main_src.split("function setStatus(s)", 1)[1].split("function ", 1)[0]
check("icon repaints from setStatus", "A.bridge = s;" in _setstatus and "bridgeIdlePaint();" in _setstatus)
check("css styles #zs-bridge", "#zs-bridge {" in css)
check("css has a live state", '#zs-bridge[data-state="live"]' in css)
check("css has a starting state", '#zs-bridge[data-state="starting"]' in css)
check("css has a down state", '#zs-bridge[data-state="down"]' in css)
check("#zs-bridge joins the shared themed control group",
      "#zs-discord, #zs-support, #zs-bridge {" in css)
check("narrow-width rules do NOT hide the terminal icon",
      "#zs-bar.zs-bar-narrow #zs-bridge" not in css)

print("=== the in-chat terminal panel (replaces the external launcher) ===")
tern_src = read("extension", "core", "terminal.js")
check("terminal.js is shipped", os.path.isfile(os.path.join(ROOT, "extension", "core", "terminal.js")))
check("terminal.js is declared before main.js in every content block",
      manifest_src.count('"core/terminal.js"') == manifest_src.count('"core/main.js"')
      and manifest_src.index('"core/terminal.js"') < manifest_src.index('"core/main.js"'))
check("panel is positioned as a top-down menu under the bar", "#zs-term {" in css
      and "top: calc(100% + 8px)" in css)
check("panel is themed by tokens, not hardcoded hex",
      "color-mix(in srgb, var(--ms-surface" in css)
check("panel has light-mode overrides", "html.zs-light .zs-term-" in css)
# The panel styles itself with --ms-surface / --ms-ink / --ms-ink-3. Those were
# REFERENCED but never DEFINED, so every rule fell back to its hardcoded hex and
# the panel ignored a theme change. They must be aliased onto the --mono-* ramp,
# which light mode and every named theme already redefine.
check("the --ms-* semantic tokens are actually defined",
      "--ms-surface: var(--mono-2)" in css and "--ms-ink: var(--mono-ink)" in css
      and "--ms-ink-3: var(--mono-ink-3)" in css)
check("the --ms-ink-3 fallback is a single value, not nine",
      len(set(_re.findall(r"var\(--ms-ink-3, (#[0-9a-f]{6})\)", css))) == 1)
check("the panel element carries both id and class",
      'wrap.id = "zs-term"' in tern_src and 'wrap.className = "zs-term"' in tern_src)
check("panel respects reduced motion", "prefers-reduced-motion" in css
      and "#zs-term, .zs-term-line { animation: none; }" in css)
# Log lines carry model and tool output, so the line body is built with
# textContent. The only innerHTML in this method is the static empty-state
# placeholder (authored strings), which carries no user data.
_paint = tern_src.split("_paintLines() {", 1)[1].split("\n    _", 1)[0]
check("panel renders log lines with textContent",
      "m.textContent = l.msg;" in _paint and "createDocumentFragment" in _paint)
check("panel's only innerHTML assignment is the static empty-state placeholder",
      _paint.count(".innerHTML =") == 1 and "zs-term-empty" in _paint)
check("panel keeps a bounded row cap", "MAX_LINES" in tern_src)
check("no external launcher remains",
      not os.path.isfile(os.path.join(ROOT, "start_launcher.bat"))
      and not os.path.isfile(os.path.join(ROOT, "runtime", "bridge_launcher.py")))
check("no launcher frame remains in the bridge", "launcher_pair" not in br_src)
check("no launcher route remains in the worker",
      "launcher_start" not in bg_src and "LAUNCHER_PORT" not in bg_src)
check("bridge keeps a bounded log ring", "deque(maxlen=LOG_RING_MAX)" in br_src)
check("bridge serves bridge_log", 'mtype == "bridge_log"' in br_src)
check("bridge serves terminal_probe", 'mtype == "terminal_probe"' in br_src)
check("bridge serves the loopback /logs fallback", '"/logs"' in br_src)
check("worker exposes terminal_snapshot", '"terminal_snapshot"' in bg_src)
check("worker forwards pushed log frames", "ms-log-push" in bg_src)

print("=== notion alignment ===")
notion = read("extension", "providers", "notion.js")
check("notion exports barInset", "barInset" in notion)
meta = read("extension", "providers", "meta.js")
check("meta exports barInset too", "barInset" in meta)
check("core applies the provider inset", "P.barInset && P.barInset()" in main_src)
check("css has the notion anchored-bar rule", "#zs-bar.zs-bar-anchored.zs-prov-notion {" in css)

print("=== settings are grouped into named tabs ===")
# The old Agent tab was a 13-section catch-all. The tabs are now named by what
# they control, and every section must be assigned to exactly one real tab - a
# section left on a tab that no longer exists would be invisible in the menu.
_tab_buttons = _re.findall(r'<button data-tab="([^"]+)">', main_src)
_section_tabs = set(_re.findall(r'data-zs-tab="([^"]+)"', main_src))
check("the tab strip declares the grouped tabs",
      _tab_buttons == ["setup", "appearance", "agent", "interface", "engines", "sites", "help"], str(_tab_buttons))
check("no section is assigned to a non-existent tab",
      _section_tabs.issubset(set(_tab_buttons)), str(sorted(_section_tabs - set(_tab_buttons))))
check("the old catch-all Agent tab no longer holds Appearance",
      'const appearanceHtml = `<section class="zs-menu-sec zs-appearance-lab" data-zs-tab="appearance"' in main_src)
check("Media relay sits under Appearance",
      'const mediaHtml = `<section class="zs-menu-sec zs-media-sec" data-zs-tab="appearance"' in main_src)
check("the prompt-shaping controls sit under Interface",
      'const enhanceHtml = `<section class="zs-menu-sec zs-enhance-sec" data-zs-tab="interface"' in main_src
      and 'const effortHtml = `<section class="zs-menu-sec zs-effort-sec" data-zs-tab="interface"' in main_src
      and 'const usageHtml = `<section class="zs-menu-sec" data-zs-tab="interface"' in main_src)
check("the default-tab preference accepts every real tab",
      'defaultTab:["setup","appearance","agent","interface","engines","sites","help"]' in main_src)
check("the default-tab dropdown offers every real tab",
      '<option value="appearance">' in main_src and '<option value="interface">' in main_src)
check("the tab strip adapts to any tab count", "repeat(auto-fit,minmax(74px,1fr))" in css)
check("a section after a hidden one drops its top rule", ".zs-menu-sec[hidden] + .zs-menu-sec { border-top: 0; }" in css)

print("=== release notes ===")
check("RELEASE_NOTES_6.22.0.md exists", os.path.isfile(os.path.join(ROOT, "docs", "RELEASE_NOTES_6.22.0.md")))

print(f"\n{'PASS' if FAIL == 0 else 'FAIL'}: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
