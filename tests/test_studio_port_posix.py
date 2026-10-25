# SPDX-License-Identifier: GPL-3.0-or-later
"""test_studio_port_posix.py - macOS/Linux port-ownership + kill paths.

6.29.0 fixed a cluster of bugs that only ever showed up off Windows, and none of
them had a test:

  * `_port_owner_posix` returned an EMPTY executable path, and `check_studio_port`
    decided "is this Roblox?" from the path alone - so on a healthy macOS machine
    Studio's own process was reported as a port squatter on every single boot
    (either an interactive kill prompt, or a spurious "close it yourself").
  * Three Studio-reaping helpers called `taskkill` unguarded. `taskkill` does not
    exist on macOS/Linux, so the exception was swallowed and a zombie StudioMCP
    kept the port forever.
  * `_descendant_pids` returned None unconditionally off Windows, which made the
    ownership guard in `_reclaim_studio_port` inert there.
  * macOS Studio detection probed only `pgrep -x RobloxStudio`, while the launcher
    accepts three binary names.

Every OS boundary is stubbed at the `subprocess` / `os` boundary, so this is
deterministic on any host - including the Windows box it was written on.
"""
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# bridge.py imports websockets lazily, but stub it anyway so the import can never
# depend on the package being installed.
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


class _FakeSys:
    """Minimal sys stand-in so we can flip bridge.sys.platform per assertion
    WITHOUT mutating the real global sys module."""

    def __init__(self, platform):
        self.platform = platform


def _stub_run(calls, stdout="", returncode=0):
    def run(*a, **k):
        calls.append(a[0] if a else [])
        return types.SimpleNamespace(stdout=stdout, returncode=returncode)
    return run


real_sys, real_os, real_subprocess = bridge.sys, bridge.os, bridge.subprocess
real_log = bridge.log

# ── 1. _is_roblox_owner: name OR path, and it must not over-match ────────
print("\n1. _is_roblox_owner recognises Roblox on both probe shapes")
check(bridge._is_roblox_owner("RobloxStudio", "/Applications/RobloxStudio.app/Contents/MacOS/RobloxStudio"),
      "macOS full path -> Roblox owner")
check(bridge._is_roblox_owner("RobloxStudio", ""),
      "name only, EMPTY path -> still a Roblox owner (the exact macOS regression)")
check(bridge._is_roblox_owner("StudioMCP.exe", ""), "StudioMCP by name -> Roblox owner")
check(bridge._is_roblox_owner("RobloxStudioBeta.exe", r"C:\Users\x\AppData\Local\Roblox\Versions\1\RobloxStudioBeta.exe"),
      "Windows path -> Roblox owner")
check(not bridge._is_roblox_owner("ropilot", "/usr/local/bin/ropilot"), "a foreign app is NOT a Roblox owner")
check(not bridge._is_roblox_owner("python3", "/usr/bin/python3"), "python is NOT a Roblox owner")

# ── 2. check_studio_port must not accuse Studio itself ───────────────────
print("\n2. check_studio_port does not flag a legitimate Roblox owner")
logged = []
bridge.log = lambda msg, color="dim", terminal=True: logged.append(str(msg))
bridge.sys = _FakeSys("darwin")

# The shape the POSIX probe used to return: a real name, an EMPTY path.
bridge._port_owner = lambda port: ("4242", "RobloxStudio", "")
logged.clear()
check(bridge.check_studio_port() is False, "returns False for a Roblox owner")
check(not any("non-Roblox process" in m for m in logged),
      "does NOT log 'held by a non-Roblox process' (the macOS false positive)")

# And with a real path, for good measure.
bridge._port_owner = lambda port: ("4242", "RobloxStudio", "/Applications/RobloxStudio.app/Contents/MacOS/RobloxStudio")
logged.clear()
check(bridge.check_studio_port() is False, "returns False with a full macOS path too")
check(not any("non-Roblox process" in m for m in logged), "still no false accusation")

# ── 3. ...but a genuine squatter IS still flagged (no new false negative) ─
print("\n3. a genuine non-Roblox squatter is still reported")
import builtins
orig_input = builtins.input
builtins.input = lambda *a, **k: "n"          # answer "no" so nothing is killed
try:
    bridge._port_owner = lambda port: ("9999", "ropilot", "/usr/local/bin/ropilot")
    logged.clear()
    check(bridge.check_studio_port() is False, "declining the prompt returns False")
    check(any("non-Roblox process" in m for m in logged),
          "a real squatter is still named (the check did not go blind)")
finally:
    builtins.input = orig_input

# ── 4. _kill_pid: platform-correct termination ───────────────────────────
print("\n4. _kill_pid never shells out to taskkill off Windows")
bridge.sys = _FakeSys("darwin")
ran, killed = [], []
bridge.subprocess = types.SimpleNamespace(run=_stub_run(ran))
bridge.os = types.SimpleNamespace(kill=lambda pid, sig: killed.append((pid, sig)))
ok, err = bridge._kill_pid(4242)
check(ok is True, "POSIX kill reports success")
check(not ran, "POSIX kill does NOT invoke taskkill (which does not exist there)")
# SIGKILL is absent on a Windows host, so resolve it the same way _kill_pid does.
_sigkill = getattr(bridge.signal, "SIGKILL", bridge.signal.SIGTERM)
check(killed == [(4242, _sigkill)], f"POSIX kill uses os.kill+SIGKILL (got {killed})")

bridge.sys = _FakeSys("win32")
ran = []
bridge.subprocess = types.SimpleNamespace(run=_stub_run(ran))
ok, err = bridge._kill_pid(4242)
check(ok is True and ran and list(ran[0][:2]) == ["taskkill", "/F"], f"Windows kill uses taskkill (got {ran})")

ok, err = bridge._kill_pid("not-a-pid")
check(ok is False and err, "an invalid pid is rejected, not crashed on")

# ── 5. _descendant_pids works on POSIX ───────────────────────────────────
print("\n5. _descendant_pids walks the tree on macOS/Linux too")
bridge.sys = _FakeSys("darwin")
ps_out = "100 1\n200 100\n300 200\n400 1\n"
calls = []
bridge.subprocess = types.SimpleNamespace(run=_stub_run(calls, stdout=ps_out))
tree = bridge._descendant_pids(100)
check(tree == {100, 200, 300}, f"POSIX descendant set is correct (got {tree})")
check(calls and calls[0][0] == "ps", f"uses ps on POSIX (got {calls[:1]})")

bridge.sys = _FakeSys("darwin")
bridge.subprocess = types.SimpleNamespace(run=_stub_run([], stdout=""))
check(bridge._descendant_pids(100) is None, "unreadable tree -> None (callers must not kill)")

# ── 6. macOS Studio detection tries every accepted bundle name ───────────
print("\n6. _roblox_studio_app_running tries all three macOS names")
bridge.sys = _FakeSys("darwin")
seen = []


def _pgrep(cmd, **k):
    seen.append(cmd[-1])
    hit = cmd[-1] == "RobloxStudioBeta"
    return types.SimpleNamespace(returncode=0 if hit else 1, stdout="123\n" if hit else "")


bridge.subprocess = types.SimpleNamespace(run=_pgrep)
check(bridge._roblox_studio_app_running() is True, "detects a RobloxStudioBeta install")
check(seen[:2] == ["RobloxStudio", "RobloxStudioBeta"],
      f"falls through to the next bundle name (tried {seen})")

seen.clear()
bridge.subprocess = types.SimpleNamespace(run=lambda cmd, **k: (seen.append(cmd[-1]), types.SimpleNamespace(returncode=1, stdout=""))[1])
check(bridge._roblox_studio_app_running() is False, "reports False when no Studio is running")
check(seen == ["RobloxStudio", "RobloxStudioBeta", "Roblox"], f"tries all three names (got {seen})")

# ── restore ──────────────────────────────────────────────────────────────
bridge.sys, bridge.os, bridge.subprocess, bridge.log = real_sys, real_os, real_subprocess, real_log

if failures:
    print(f"\ntest_studio_port_posix: {len(failures)} FAILED")
    for f in failures:
        print("   -", f)
    sys.exit(1)
print("\ntest_studio_port_posix: 6 sections passed")
