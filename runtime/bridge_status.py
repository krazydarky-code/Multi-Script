# SPDX-License-Identifier: GPL-3.0-or-later
"""bridge_status.py - which Multi-Script bridge is running on the bridge port?

    python runtime/bridge_status.py            # human readable
    python runtime/bridge_status.py --quiet    # no output, exit code only
    python runtime/bridge_status.py --json     # full health report, machine readable

Exit codes (used by Start.bat / MacOS_Start.command / Setup):
    0  a bridge of THIS folder's version is running
    1  nothing is listening on the port
    2  a Multi-Script bridge is running but it is OLDER / from another folder (stale)
    3  something that is not a Multi-Script bridge holds the port
"""
import json
import os
import re
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PORT = int(os.environ.get("ZS_BRIDGE_PORT", "17613"))
# The bridge serves its loopback HTTP surface (the companion plugin, /logs and
# /diagnostics) on PORT+1, overridable with the same variable the bridge reads.
PLUGIN_PORT = int(os.environ.get("ZS_PLUGIN_PORT", str(PORT + 1)))


def expected_version():
    try:
        with open(os.path.join(HERE, "bridge.py"), "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = re.match(r'\s*BRIDGE_VERSION\s*=\s*["\']([^"\']+)["\']', line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return ""


def listening(port=PORT, timeout=0.6):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def diagnostics(port=PLUGIN_PORT, timeout=6.0):
    """The bridge's own /diagnostics report, or None if it is unreachable.

    Read-only and best-effort: a missing report must never turn a healthy status
    check into a failure, so every error path returns None instead of raising.
    """
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:%d/diagnostics" % port, timeout=timeout) as r:
            if r.status != 200:
                return None
            data = json.loads(r.read().decode("utf-8", "replace"))
            return data if isinstance(data, dict) else None
    except Exception:
        return None


def probe(port=PORT, timeout=6.0):
    """(version, root) of the bridge on `port`; (None, None) if it is not a bridge."""
    try:
        import asyncio
        import websockets

        async def go():
            async with websockets.connect("ws://127.0.0.1:%d" % port, open_timeout=timeout,
                                          max_size=32 * 1024 * 1024) as ws:
                for _ in range(4):
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout))
                    if isinstance(msg, dict) and msg.get("type") == "connected":
                        return str(msg.get("bridge_version") or ""), str(msg.get("bridge_root") or "")
            return None, None

        return asyncio.run(go())
    except Exception:
        return None, None


def same_folder(a, b):
    if not a or not b:
        return False
    n = lambda p: os.path.normcase(os.path.realpath(p)).rstrip("\\/")
    return n(a) == n(b)


def classify(port=PORT):
    """-> (code, info dict)"""
    want = expected_version()
    if not listening(port):
        return 1, {"expected": want}
    have, root = probe(port)
    if have is None:
        return 3, {"expected": want}
    if have == want and (not root or same_folder(root, ROOT)):
        return 0, {"expected": want, "version": have, "root": root}
    return 2, {"expected": want, "version": have, "root": root}


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    quiet = "--quiet" in args
    as_json = "--json" in args
    code, info = classify()

    if as_json:
        # The full picture in one machine-readable object: the classification plus
        # the bridge's own health report (servers, environment, engines off).
        report = dict(info)
        report["code"] = code
        report["port"] = PORT
        report["pluginPort"] = PLUGIN_PORT
        report["diagnostics"] = diagnostics() if code == 0 else None
        print(json.dumps(report, indent=2, sort_keys=True))
        return code

    if not quiet:
        msgs = {
            0: "Bridge v{version} from this folder is running.",
            1: "No bridge is running on port %d." % PORT,
            2: "A STALE bridge is running: v{version}{where} (this folder is v{expected}).",
            3: "Port %d is held by a program that is not a Multi-Script bridge." % PORT,
        }
        where = (" from " + info["root"]) if info.get("root") else ""
        print("  " + msgs[code].format(where=where, **{k: info.get(k, "?") for k in ("version", "expected")}))
        # On a healthy bridge, add the per-server line: "which engine is down, and
        # why" is the actual support question, and it is already known here.
        if code == 0:
            report = diagnostics()
            servers = (report or {}).get("servers") or []
            for s in servers:
                state = "up" if s.get("alive") else "DOWN"
                detail = s.get("lastError")
                hint = ""
                if s.get("alive") and not s.get("tools") and not detail:
                    # Up with 0 tools = the server runs but its editor is not attached yet.
                    hint = {"unity": "  (open Unity with the MCP for Unity package - tools appear then)",
                            "blender": "  (open Blender and click Connect in the BlenderMCP add-on panel)",
                            "godot": "  (Godot tools load on first use; needs Node.js 18+ and GODOT_PATH)",
                            "roblox": "  (open Roblox Studio and enable its MCP server)"}.get(str(s.get("id")), "  (waiting for its app)")
                print("    %-8s %-4s %s tools%s%s" % (
                    s.get("id") or "?", state, s.get("tools") if s.get("tools") is not None else "?",
                    ("  last error: " + str(detail)) if detail else "", hint))
            env = (report or {}).get("environment") or {}
            if env:
                missing = [k for k in ("uvx", "npx") if env.get(k) is False]
                if missing:
                    print("    missing on this PC: " + ", ".join(missing) +
                          " (Unity/Blender need uvx; the Godot server needs npx)")
            off = (report or {}).get("enginesDisabled") or []
            if off:
                print("    engines switched off here: " + ", ".join(off))
    return code


if __name__ == "__main__":
    sys.exit(main())
