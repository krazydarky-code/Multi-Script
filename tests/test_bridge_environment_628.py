#!/usr/bin/env python3
"""6.28: bridge environment diagnostics in the service snapshot + cached."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import schema_audit
b = schema_audit.load_bridge()

env = b._env_diagnostics()
assert isinstance(env, dict), env
for k in ("python", "platform", "uvx", "npx", "blenderAddon"):
    assert k in env, k
assert isinstance(env["uvx"], bool) and isinstance(env["npx"], bool) and isinstance(env["blenderAddon"], bool)
assert env["python"].count(".") == 2

# cached: same object back-to-back, no repeated PATH scans
assert b._env_diagnostics() is env

# snapshot carries it, and still carries the 6.25 fields the panel needs
snap = b._service_snapshot()
assert snap["environment"] is env
assert snap["bridgeVersion"] == b.BRIDGE_VERSION and "uptimeSeconds" in snap and "servers" in snap
print("PASS 6.28 bridge environment diagnostics: cached, honest, in the service snapshot")
