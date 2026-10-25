# SPDX-License-Identifier: GPL-3.0-or-later
"""Stale-bridge replacement (the "Connected to bridge v6.25.0, but this process does not
expose the Software Builder tools" report).

A NEW extension kept talking to an OLD bridge process that still held the port, because
stop/restart/Setup only recognised a bridge started from THIS folder. These tests start a
real "old" bridge (a copy of runtime/ with an older BRIDGE_VERSION, in another folder) on a
spare port and prove that:
  * bridge_status.py classifies it as stale (exit 2),
  * native_host restart replaces it with this folder's bridge,
  * a foreign program on the port is NOT killed (port_busy),
  * the bridge's own port reclaim replaces a stale bridge when launched directly (Start.bat),
  * install_native_host.replace_bridge (Setup.bat) ends with the current bridge running,
  * the extension carries the stale-bridge self-heal and the richer diagnosis.
"""
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RT = os.path.join(ROOT, "runtime")
PORT = 17913
os.environ["ZS_BRIDGE_PORT"] = str(PORT)
os.environ["ZS_PLUGIN_PORT"] = str(PORT + 1)
sys.path.insert(0, RT)

fails = []


def check(name, cond, extra=""):
    if cond:
        print("PASS", name)
    else:
        print("FAIL", name, extra)
        fails.append(name)


def port_open():
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.4):
            return True
    except OSError:
        return False


def wait_port(up, secs=40):
    end = time.time() + secs
    while time.time() < end:
        if port_open() == up:
            return True
        time.sleep(0.3)
    return False


def wait_version(want, secs=40):
    import bridge_status
    end = time.time() + secs
    while time.time() < end:
        if bridge_status.probe(PORT, 3)[0] == want:
            return True
        time.sleep(0.5)
    return False


def kill_all():
    import native_host
    for pid in native_host.port_owner_pids(PORT):
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, 9)
        except Exception:
            pass
    wait_port(False, 10)


tmp = tempfile.mkdtemp(prefix="ms-stale-")
old_root = os.path.join(tmp, "Multi-Script 6.25 old")  # a folder with a space, like real downloads
shutil.copytree(RT, os.path.join(old_root, "runtime"), ignore=shutil.ignore_patterns("logs", "__pycache__", "*.pyc"))
old_bridge = os.path.join(old_root, "runtime", "bridge.py")
src = open(old_bridge, encoding="utf-8").read()
src = re.sub(r'^BRIDGE_VERSION = .*$', 'BRIDGE_VERSION = "6.25.0"', src, count=1, flags=re.M)
open(old_bridge, "w", encoding="utf-8").write(src)

import bridge_status  # noqa: E402
import native_host  # noqa: E402

want = bridge_status.expected_version()
check("this folder declares a bridge version", bool(re.fullmatch(r"\d+\.\d+\.\d+", want)), want)
check("native host reports the same expected version", native_host.expected_bridge_version() == want)
check("ping advertises expectedBridgeVersion", native_host.cmd_ping({}).get("expectedBridgeVersion") == want)

procs = []


def launch(path, cwd):
    p = subprocess.Popen([sys.executable, "-u", path], cwd=cwd, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                         start_new_session=(os.name != "nt"))
    procs.append(p)
    return p


try:
    # 1. classification
    check("nothing listening -> exit 1", bridge_status.classify(PORT)[0] == 1)
    launch(old_bridge, os.path.dirname(old_bridge))
    check("old bridge comes up", wait_port(True))
    check("old bridge reports 6.25.0", wait_version("6.25.0"))
    code, info = bridge_status.classify(PORT)
    check("old bridge is classified stale (2)", code == 2, str(info))
    # The record's `cmd` is deliberately shortened by native_host._short() for
    # display, so on a machine with a long %TEMP% the literal "bridge.py" falls
    # off the end of a 140-char string and a substring test on `cmd` alone gives
    # a FALSE failure. Assert on what actually matters: the scan found a bridge
    # holding our port that lives in a folder other than this one.
    _stale = native_host.stale_port_bridges()
    check("cmd-line scan sees it as a stale bridge from another folder",
          any(x.get("pid") and x.get("folder") and os.path.abspath(x["folder"]) != os.path.abspath(ROOT)
              for x in _stale),
          str(_stale))

    # 2. native host restart replaces it
    r = native_host.cmd_restart({"wait": 40})
    check("restart reports ok", r.get("ok") is True, str(r)[:300])
    check("restart names the stale bridge it stopped", bool(r.get("stale")), str(r)[:300])
    check("restart exposes the expected version", r.get("expectedBridgeVersion") == want)
    check("the bridge on the port is now this folder's version", wait_version(want))
    code, info = bridge_status.classify(PORT)
    check("classified current (0)", code == 0, str(info))
    check("new bridge reports where it runs from",
          os.path.normcase(os.path.realpath(info.get("root") or "-")) == os.path.normcase(os.path.realpath(ROOT)), str(info))
    kill_all()

    # 3. a foreign program is never killed
    foreign = subprocess.Popen([sys.executable, "-c",
                                "import socket,time;s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
                                "s.bind(('127.0.0.1',%d));s.listen(5);time.sleep(120)" % PORT],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(foreign)
    check("foreign listener up", wait_port(True))
    check("status: port held by a stranger (3)", bridge_status.classify(PORT)[0] == 3)
    r = native_host.cmd_restart({"wait": 5})
    check("restart refuses with port_busy", r.get("ok") is False and r.get("code") == "port_busy", str(r)[:300])
    check("the foreign program is still alive", foreign.poll() is None)
    foreign.kill()
    foreign.wait()
    wait_port(False, 10)

    # 4. the bridge reclaims its port from a stale bridge by itself (Start.bat / python bridge.py)
    launch(old_bridge, os.path.dirname(old_bridge))
    check("second old bridge up", wait_port(True) and wait_version("6.25.0"))
    launch(os.path.join(RT, "bridge.py"), RT)
    check("direct launch takes the port over from the stale bridge", wait_version(want, 60))
    kill_all()

    # 5. Setup's replace_bridge ends with the current bridge
    import install_native_host as inst
    launch(old_bridge, os.path.dirname(old_bridge))
    check("third old bridge up", wait_port(True) and wait_version("6.25.0"))
    check("Setup replace_bridge succeeds", inst.replace_bridge(False) is True)
    check("Setup left this folder's bridge running", wait_version(want))
    check("Setup is idempotent with --keep-running", inst.replace_bridge(True) is True)
    kill_all()
finally:
    kill_all()
    for p in procs:
        try:
            p.kill()
        except Exception:
            pass
    shutil.rmtree(tmp, ignore_errors=True)

# 6. extension side
rd = lambda *p: open(os.path.join(ROOT, *p), encoding="utf-8").read()
bg, main, term, bridge = rd("extension", "background.js"), rd("extension", "core", "main.js"), rd("extension", "core", "terminal.js"), rd("runtime", "bridge.py")
check("worker replaces a bridge older than the extension", "ensureFreshBridge" in bg and "cmpVersion(bridgeVersion, mine) < 0" in bg)
check("self-heal is bounded (3 tries, 2 min apart)", "upgradeTries >= 3" in bg and "120000" in bg)
check("self-heal respects the user's Stop", "prefs.msBridgeUserStopped === true" in bg)
check("worker exposes bridgeRoot/bridgeStale in status", "bridgeRoot" in bg and "bridgeStale" in bg)
check("diagnosis names the folder the stale bridge runs from", "It is running from" in main)
check("terminal panel narrates the replacement", 'msg.event === "upgrading"' in term)
check("bridge sends its folder and pid on connect", bridge.count('"bridge_root": _BRIDGE_ROOT') == 2)

check("worker does not shadow the global URL class", not re.search(r"^(const|let|var)\\s+URL\\b", bg, re.M) and "new WebSocket(BRIDGE_URL)" in bg)
inst_src = rd("runtime", "install_native_host.py")
check("Setup restarts a same-version bridge unless --keep-running", "is already running (port" not in inst_src and "keep_running and have == want" in inst_src)


print("\n%d failed" % len(fails))
sys.exit(1 if fails else 0)
