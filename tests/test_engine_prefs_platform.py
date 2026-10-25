# SPDX-License-Identifier: GPL-3.0-or-later
"""test_engine_prefs_platform.py - which engines start switched off, per OS.

Two real 6.28.x bugs lived here, both caused by SHIPPING a runtime-state file:

  * `runtime/engine-prefs.json` shipped with `{"disabled":["blender","godot","unity"]}`,
    so every new user got Unity, Godot and Blender switched off out of the box.
  * Because the file existed, the Linux "Roblox Studio has no Linux build" auto-disable
    never fired (`_load_engine_prefs` only applied it when the file was ABSENT), so a
    Linux user got a crash-loop of "open Roblox Studio" prompts.

The file is no longer shipped (see .gitignore), but that alone is not enough: a prefs
file can still arrive from a copied folder, a shared home directory, or an older
release. So the loader now records which OS wrote the file and refuses to let a
FOREIGN file keep Roblox enabled on Linux.
"""
import importlib.util
import json
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
w = types.ModuleType("websockets")
w.ConnectionClosed = Exception
sys.modules.setdefault("websockets", w)
spec = importlib.util.spec_from_file_location("ms_bridge", ROOT / "runtime" / "bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

failures = []


def check(cond, label):
    if cond:
        print(f"  ok  {label}")
    else:
        print(f"  FAIL {label}")
        failures.append(label)


real_sys, real_os, real_path = bridge.sys, bridge.os, bridge.ENGINE_PREFS_PATH
tmpdir = Path(tempfile.mkdtemp(prefix="ms-prefs-"))
prefs = tmpdir / "engine-prefs.json"


class _FakeSys:
    def __init__(self, platform):
        self.platform = platform


class _FakeOs:
    """Just enough os for the loader/saver, so we never touch the real environ."""

    def __init__(self, environ):
        self.environ = environ

    @staticmethod
    def replace(a, b):
        return real_os.replace(a, b)


def set_env(platform, **env):
    bridge.sys = _FakeSys(platform)
    bridge.os = _FakeOs(dict(env))
    bridge.ENGINE_PREFS_PATH = str(prefs)


def write_prefs(obj):
    prefs.write_text(json.dumps(obj), encoding="utf-8")


def clear_prefs():
    if prefs.exists():
        prefs.unlink()


print("\n1. no prefs file at all")
clear_prefs()
set_env("linux")
check(bridge._load_engine_prefs() == {"roblox"},
      "Linux with no prefs -> Roblox starts off (no Studio build exists)")
set_env("darwin")
check(bridge._load_engine_prefs() == set(),
      "macOS with no prefs -> nothing forced off (Studio works there)")
set_env("win32")
check(bridge._load_engine_prefs() == set(), "Windows with no prefs -> nothing forced off")

print("\n2. the shipped-default file (Roblox ENABLED, foreign OS) must not defeat Linux")
write_prefs({"disabled": ["blender", "godot", "unity"]})          # legacy: no "os" key
set_env("linux")
check("roblox" in bridge._load_engine_prefs(),
      "legacy OS-less prefs with Roblox enabled -> Roblox forced off on Linux")

write_prefs({"os": "win32", "disabled": ["blender"]})             # copied from a PC
set_env("linux")
check("roblox" in bridge._load_engine_prefs(),
      "prefs written on Windows -> Roblox forced off on Linux")

print("\n3. this machine's OWN choice is respected")
write_prefs({"os": "linux", "disabled": []})
set_env("linux")
check(bridge._load_engine_prefs() == set(),
      "a Linux user who switched Roblox ON keeps it on (explicit choice wins)")

write_prefs({"os": "linux", "disabled": ["godot"]})
set_env("linux")
check(bridge._load_engine_prefs() == {"godot"},
      "only the engines the user actually disabled are returned")

print("\n4. an explicit Studio path overrides the Linux default")
write_prefs({"os": "win32", "disabled": []})
set_env("linux", ZS_STUDIO_MCP_PATH="/opt/studio/StudioMCP")
check(bridge._load_engine_prefs() == set(),
      "ZS_STUDIO_MCP_PATH set -> Roblox is left enabled even on Linux")

print("\n5. saving records the OS")
clear_prefs()
set_env("darwin")
check(bridge._save_engine_prefs({"godot"}) is True, "save succeeds")
saved = json.loads(prefs.read_text(encoding="utf-8"))
check(saved.get("os") == "darwin", f"the OS is recorded (got {saved.get('os')!r})")
check(saved.get("disabled") == ["godot"], f"the disabled set round-trips (got {saved.get('disabled')})")

# A file this codebase wrote must load back identically on the same OS.
set_env("darwin")
check(bridge._load_engine_prefs() == {"godot"}, "a saved file reloads to the same set on the same OS")

print("\n6. malformed input never crashes the bridge")
prefs.write_text("{ not json", encoding="utf-8")
set_env("darwin")
check(bridge._load_engine_prefs() == set(), "corrupt JSON -> empty set, no exception")
write_prefs({"disabled": "not-a-list"})
check(bridge._load_engine_prefs() == set(), "wrong type -> empty set, no exception")
write_prefs({"os": "darwin", "disabled": ["ok", "../../etc/passwd", "a" * 80, 42]})
check(bridge._load_engine_prefs() == {"ok"}, "only well-formed engine ids survive")

# restore
bridge.sys, bridge.os, bridge.ENGINE_PREFS_PATH = real_sys, real_os, real_path

if failures:
    print(f"\ntest_engine_prefs_platform: {len(failures)} FAILED")
    for f in failures:
        print("   -", f)
    sys.exit(1)
print("\ntest_engine_prefs_platform: 6 sections passed")
