# SPDX-License-Identifier: GPL-3.0-or-later
"""test_bridge_diagnostics.py - the 6.29.0 bridge improvements.

Covers the four additive changes, each of which must not alter existing
behaviour:

  1. `safe_call` now also returns an `errorInfo` block (code / retryable /
     tool) - while `ok`, `error` and `kind` stay byte-for-byte as they were, so
     no existing caller changes behaviour.
  2. `MCPManager.server_timeout` honours an optional
     `mcpServers.<id>.timeout_sec`, clamped so a typo cannot hang a call.
  3. `MCPManager.refresh_stale` re-lists tools for a server that sent
     notifications/tools/list_changed, and is a no-op otherwise.
  4. `_bridge_diagnostics` returns the full health report the new /diagnostics
     route serves.
"""
import importlib.util
import sys
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


# ── 1. structured errors are additive ────────────────────────────────────
print("\n1. safe_call adds errorInfo without changing the legacy keys")
real_mgr = bridge.mgr


class _Mgr:
    def __init__(self, exc=None, result=None):
        self.exc, self.result = exc, result

    def call(self, name, arguments, timeout):
        if self.exc:
            raise self.exc
        return self.result


bridge.mgr = _Mgr(result={"text": "hello", "images": []})
ok = bridge.safe_call("read_file", {}, 30)
check(ok == {"ok": True, "text": "hello", "images": []},
      "a successful call returns EXACTLY the old shape (no errorInfo noise)")

cases = [
    # (exception, expected legacy `kind`, expected code, expected retryable)
    # TimeoutError keeps its historical hardcoded kind "timeout" - the original
    # code set that explicitly and callers may match on it, so it must not change.
    (TimeoutError("no answer after 30s"), "timeout", "timeout", True),
    (RuntimeError("MCP server \"unity\" is not connected"), "RuntimeError", "server_disconnected", True),
    (RuntimeError("unknown tool 'nope'"), "RuntimeError", "unknown_tool", False),
    (RuntimeError("engine 'roblox' is switched off"), "RuntimeError", "engine_disabled", False),
    (RuntimeError("path is required"), "RuntimeError", "invalid_arguments", False),
    (RuntimeError("permission denied"), "RuntimeError", "permission_denied", False),
    (RuntimeError("something exploded"), "RuntimeError", "tool_error", True),
]
for exc, want_kind, want_code, want_retry in cases:
    bridge.mgr = _Mgr(exc=exc)
    res = bridge.safe_call("some_tool", {}, 30)
    check(res["ok"] is False and res["error"] == str(exc) and res["kind"] == want_kind,
          f"legacy keys unchanged for {type(exc).__name__} (kind={want_kind})")
    info = res.get("errorInfo") or {}
    check(info.get("code") == want_code and info.get("retryable") is want_retry,
          f"classified as {want_code} (retryable={want_retry})")
    check(info.get("tool") == "some_tool", "the failing tool is named in errorInfo")

bridge.mgr = real_mgr

# ── 2. per-server timeout override ───────────────────────────────────────
print("\n2. per-server timeouts are honoured and clamped")
mgr = bridge.MCPManager()
mgr.specs = {
    "slow": {"timeout_sec": 900},
    "bad": {"timeout_sec": "not-a-number"},
    "zero": {"timeout_sec": 0},
    "huge": {"timeout_sec": 99999},
    "none": {},
}
check(mgr.server_timeout("slow", 120) == 900, "an explicit override wins")
check(mgr.server_timeout("bad", 120) == 120, "a non-numeric value falls back to the default")
check(mgr.server_timeout("zero", 120) == 120, "0 is out of range -> default (never an instant timeout)")
check(mgr.server_timeout("huge", 120) == 120, "an absurd value is rejected -> default")
check(mgr.server_timeout("none", 120) == 120, "an absent key leaves the default untouched")
check(mgr.server_timeout("not-configured", 120) == 120, "an unknown server leaves the default untouched")
check(mgr.server_timeout(None, 120) == 120, "a None server id is handled")

# ── 3. tools/list_changed invalidates the cache ──────────────────────────
print("\n3. refresh_stale re-lists only the servers that asked for it")
mgr = bridge.MCPManager()
listed = []


class _Client:
    def __init__(self, cid, stale):
        self.id = cid
        self.tools_cache = []
        self.tools_stale = stale

    def is_alive(self):
        return True

    def refresh_tools(self, timeout=20):
        listed.append(self.id)
        self.tools_cache = [{"name": "%s_tool" % self.id}]
        self.tools_stale = False
        return self.tools_cache


mgr.clients = {"a": _Client("a", True), "b": _Client("b", False)}
changed = mgr.refresh_stale()
check(changed is True, "reports that it rebuilt")
check(listed == ["a"], f"only the stale server was re-listed (got {listed})")
check("a_tool" in mgr.index, "the refreshed tool is in the index")
check("b" not in listed, "a server that did NOT notify is left alone (cache stays cheap)")

listed.clear()
check(mgr.refresh_stale() is False, "a second call is a no-op once nothing is stale")
check(listed == [], "and it re-lists nothing")

# A refresh that throws must not take the bridge down.
class _Broken(_Client):
    def refresh_tools(self, timeout=20):
        raise RuntimeError("server died mid-refresh")


mgr.clients = {"x": _Broken("x", True)}
try:
    mgr.refresh_stale()
    check(True, "a failing refresh is swallowed, not propagated")
except Exception as e:
    check(False, f"a failing refresh must not raise (got {e})")

# ── 4. the diagnostics report ────────────────────────────────────────────
print("\n4. _bridge_diagnostics returns the full health report")
bridge.mgr = mgr
diag = bridge._bridge_diagnostics()
for key in ("ok", "bridgeVersion", "ports", "platform", "servers", "catalogue",
            "environment", "enginesDisabled", "extensionClients", "recentLog"):
    check(key in diag, f"report has '{key}'")
check(diag["ok"] is True, "report is marked ok")
check(diag["bridgeVersion"] == bridge.BRIDGE_VERSION, "reports the running bridge version")
check(set(diag["ports"]) == {"bridge", "companionPlugin", "studioMcp"}, "reports all three ports")
check(isinstance(diag["catalogue"].get("builtinTools"), int), "catalogue counts are real numbers")
check(diag["catalogue"]["skills"] > 0, "skill catalogue is non-empty")
check(isinstance(diag["enginesDisabled"], list), "enginesDisabled is a list")
check(isinstance(diag["recentLog"], list) and len(diag["recentLog"]) <= 15, "log tail is bounded")
bridge.mgr = real_mgr

# ── 5. the route is actually wired ───────────────────────────────────────
print("\n5. the /diagnostics route is wired into the HTTP surface")
src = (ROOT / "runtime" / "bridge.py").read_text(encoding="utf-8")
check('route == "/diagnostics"' in src, "the route is dispatched")
check("_bridge_diagnostics()" in src, "the route serves _bridge_diagnostics")
check('"--json"' in (ROOT / "runtime" / "bridge_status.py").read_text(encoding="utf-8"),
      "bridge_status.py exposes --json")
check("def diagnostics(" in (ROOT / "runtime" / "bridge_status.py").read_text(encoding="utf-8"),
      "bridge_status.py can fetch the report")

if failures:
    print(f"\ntest_bridge_diagnostics: {len(failures)} FAILED")
    for f in failures:
        print("   -", f)
    sys.exit(1)
print("\ntest_bridge_diagnostics: 5 sections passed")
