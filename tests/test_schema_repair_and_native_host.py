# SPDX-License-Identifier: GPL-3.0-or-later
"""Schema auto-repair + the Native Messaging host that the terminal icon drives.

Part 1: runtime/schema_repair.py turns almost-right tool arguments into schema-valid
        ones (the "JSON schema errors" class of failures) and never raises.
Part 2: runtime/native_host.py speaks Chrome's length-prefixed protocol over real
        stdin/stdout; start/processes/stop are exercised against the REAL bridge on a
        spare port, so the terminal icon's start path is play-tested, not assumed.
"""
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RT = os.path.join(ROOT, "runtime")
sys.path.insert(0, RT)

fails = []


def check(name, cond, extra=""):
    if cond:
        print("PASS", name)
    else:
        print("FAIL", name, extra)
        fails.append(name)


# ── Part 1: schema repair ────────────────────────────────────────────────────
import schema_repair as S  # noqa: E402

SCHEMA = {
    "type": "object",
    "properties": {
        "count": {"type": "integer", "minimum": 1, "maximum": 5},
        "visible": {"type": "boolean"},
        "mode": {"type": "string", "enum": ["Fast", "Slow"]},
        "position": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
        "file_path": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "opts": {"type": "object", "properties": {"depth": {"type": "number"}}},
    },
    "required": ["file_path"],
}
out, notes = S.repair_arguments(SCHEMA, {"count": "9", "visible": "yes", "mode": "fast", "position": {"x": 1, "y": 2, "z": 3}, "path": "a.lua", "tags": "one"})
check("string number is converted and clamped to the schema range", out["count"] == 5)
check("boolean words become booleans", out["visible"] is True)
check("enum matches case-insensitively", out["mode"] == "Fast")
check("{x,y,z} becomes a vector array", out["position"] == [1, 2, 3])
check("near-miss key 'path' is renamed to 'file_path'", out.get("file_path") == "a.lua" and "path" not in out)
check("a bare string becomes a one-item array", out["tags"] == ["one"])
check("every repair is reported", len(notes) >= 6)

out, _ = S.repair_arguments(SCHEMA, {"arguments": {"count": 2, "file_path": "x"}})
check("{arguments:{...}} envelope is unwrapped", out == {"count": 2, "file_path": "x"})
out, _ = S.repair_arguments(SCHEMA, '{"count":"3","file_path":"y"}')
check("a stringified JSON object is parsed", out == {"count": 3, "file_path": "y"})
out, _ = S.repair_arguments(SCHEMA, {"filepath": "z", "position": "1, 2, 3"})
check("'1, 2, 3' becomes [1,2,3]", out["position"] == [1, 2, 3] and out["file_path"] == "z")
out, _ = S.repair_arguments(SCHEMA, {"file_path": "ok", "opts": '{"depth":"2"}'})
check("nested stringified objects are repaired recursively", out["opts"] == {"depth": 2})
out, notes = S.repair_arguments(SCHEMA, {"file_path": "ok", "count": 3})
check("already-valid arguments are left alone", out == {"file_path": "ok", "count": 3} and notes == [])
for junk in (None, 5, [], "not json at all", {"count": object()}):
    try:
        S.repair_arguments(SCHEMA, junk)
        S.repair_arguments(None, junk)
        good = True
    except Exception as exc:  # noqa: BLE001
        good = False
        print("   raised", exc)
    check(f"repair never raises on {type(junk).__name__}", good)
check("example() produces a schema-shaped sample", isinstance(S.example(SCHEMA), dict) and "file_path" in S.example(SCHEMA))
check("describe() names the required argument", "file_path" in S.describe(SCHEMA, "demo"))

# ── Part 2: native host protocol ─────────────────────────────────────────────
def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def frame(obj):
    b = json.dumps(obj).encode()
    return struct.pack("<I", len(b)) + b


def talk(msgs, env_extra=None, raw=None, timeout=60):
    env = dict(os.environ)
    env.update(env_extra or {})
    p = subprocess.Popen([sys.executable, os.path.join(RT, "native_host.py")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    payload = raw if raw is not None else b"".join(frame(m) for m in msgs)
    out, err = p.communicate(payload, timeout=timeout)
    replies, i = [], 0
    while i + 4 <= len(out):
        (n,) = struct.unpack("<I", out[i:i + 4])
        replies.append(json.loads(out[i + 4:i + 4 + n].decode()))
        i += 4 + n
    return replies, err.decode(errors="replace"), p.returncode


port = free_port()
envp = {"ZS_BRIDGE_PORT": str(port)}
r, err, rc = talk([{"cmd": "ping", "id": 7}, {"cmd": "nope", "id": 8}], envp)
check("ping answers with host version and echoes the id", r and r[0].get("ok") and r[0].get("id") == 7 and r[0].get("hostVersion"), str(r))
check("unknown command is an error that lists valid commands", len(r) > 1 and r[1].get("ok") is False and "start" in r[1].get("commands", []))
check("host exits cleanly when Chrome closes the pipe", rc == 0, err[-200:])
r, _, rc = talk([], envp, raw=struct.pack("<I", 5 * 1024 * 1024) + b"x")
check("an oversized frame is rejected, not crashed on", r and r[0].get("ok") is False and rc == 0, str(r))
r, _, rc = talk([], envp, raw=struct.pack("<I", 3) + b"{no")
check("a malformed JSON frame is rejected, not crashed on", r and r[0].get("ok") is False and rc == 0, str(r))

# Real bridge: start → listening → processes → already running → stop → port closed.
def listening(p):
    try:
        with socket.create_connection(("127.0.0.1", p), timeout=0.4):
            return True
    except OSError:
        return False


tmp_state = tempfile.mkdtemp(prefix="ms-host-")
bridge_env = dict(envp)
bridge_env["ZS_STATE_DIR"] = tmp_state
try:
    r, err, rc = talk([{"cmd": "start", "wait": 25, "id": 1}], bridge_env, timeout=90)
    started = r and r[0].get("ok") and r[0].get("listening")
    check("start launches the real bridge and waits until it listens", bool(started) and listening(port), str(r)[:300] + err[-200:])
    if started:
        r, _, _ = talk([{"cmd": "processes"}, {"cmd": "start"}, {"cmd": "status"}], envp)
        procs = (r[0].get("processes") or []) if r else []
        check("processes lists the bridge process", any(p.get("role") == "bridge" for p in procs), str(r[0])[:300])
        check("a second start is idempotent (already running)", len(r) > 1 and r[1].get("ok") and r[1].get("already"))
        check("status reports listening", len(r) > 2 and r[2].get("listening") is True)
        r, _, _ = talk([{"cmd": "tail", "lines": 20}], envp)
        check("tail returns bridge output lines", r and r[0].get("ok") and isinstance(r[0].get("lines"), list))
        r, _, _ = talk([{"cmd": "stop"}], envp, timeout=60)
        time.sleep(0.8)
        check("stop terminates the bridge and frees the port", r and r[0].get("ok") and not listening(port), str(r)[:200])
        r, _, _ = talk([{"cmd": "restart", "wait": 25}], bridge_env, timeout=90)
        check("restart brings it back", r and r[0].get("ok") and listening(port), str(r)[:200])
finally:
    talk([{"cmd": "stop"}], envp, timeout=60)

# ── installer (dry: manifest content only, no registry/profile writes) ───────
import install_native_host as I  # noqa: E402

m = I.manifest_for("/x/native_host.sh", ["abcdefghijklmnopabcdefghijklmnop"])
check("native host manifest has the stdio contract", m["name"] == "com.multiscript.bridge" and m["type"] == "stdio" and m["allowed_origins"] == ["chrome-extension://abcdefghijklmnopabcdefghijklmnop/"])
check("installer can derive a stable extension id from the folder path", callable(I.detect_extension_ids))

# ── 6.25.1 regressions: flashing consoles, unstable id, launcher scripts ─────
import re as _re  # noqa: E402
import json as _json  # noqa: E402

os.chdir(ROOT)
host_src = open(os.path.join("runtime", "native_host.py"), encoding="utf-8").read()
spawn = host_src.split("def _spawn_bridge", 1)[1].split("def _kill_tree", 1)[0]
check("host never spawns the bridge with DETACHED_PROCESS (it overrides NO_WINDOW -> a console flashes per child)",
      "0x00000008" not in spawn and "DETACHED" not in spawn.replace("Do NOT add DETACHED_PROCESS", "").replace("overrides NO_WINDOW", ""))
check("host spawns the bridge with a hidden console (CREATE_NO_WINDOW)", "NO_WINDOW" in spawn)
check("host serialises starts with a lock", "_take_start_lock" in spawn or "_take_start_lock" in host_src)
bridge_src = open("runtime/bridge.py", encoding="utf-8").read()
check("bridge installs the windowless-subprocess patch before it launches anything", "winquiet" in bridge_src and bridge_src.index("winquiet") < bridge_src.index("def log("))
import winquiet as W  # noqa: E402
check("winquiet is a no-op off Windows and idempotent", W.install() in (True, False) and W.install() in (True, False))
check("crash-loop restarts back off", "loop_level" in bridge_src and "(15, 30, 60, 120, 300, 600)" in bridge_src)

man = _json.load(open("extension/manifest.json", encoding="utf-8"))
check("manifest pins a key so the extension id never depends on the folder", bool(man.get("key")))
pinned = I.manifest_extension_id()
check("installer derives the pinned id from the manifest key", bool(pinned) and bool(_re.fullmatch(r"[a-p]{32}", pinned)), pinned)
ids_probe = I.manifest_for("/x/y", [pinned])
check("the pinned id ends up in allowed_origins", ids_probe["allowed_origins"] == [f"chrome-extension://{pinned}/"])
check("installer can prove the launcher works before the browser restarts", callable(I.self_test))

for fname in ("Setup.bat", "Start.bat"):
    raw = open(fname, "rb").read()
    check(f"{fname} uses CRLF line endings", b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b""))
st = open("Start.bat", encoding="utf-8").read()
check("Start.bat refuses an unextracted zip, finds Python, installs websockets, detects a double launch",
      "Extract the WHOLE download" in st and ":findpy" in st and "websockets" in st and "already running" in st)
check("Start.bat runs the bridge in its own window", "runtime\\bridge.py" in st)
check("Setup.bat does not double-pause", "--no-pause" in open("Setup.bat", encoding="utf-8").read())
check("MacOS_Start.command exists and is LF", b"\r" not in open("MacOS_Start.command", "rb").read())

print()
if fails:
    print("FAILED:", len(fails))
    sys.exit(1)
print("ALL PASS")
