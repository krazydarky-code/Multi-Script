import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
w = types.ModuleType("websockets")
w.ConnectionClosed = Exception
sys.modules.setdefault("websockets", w)
spec = importlib.util.spec_from_file_location("plugin_bridge", ROOT / "runtime" / "bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

catalog = json.loads((ROOT / "runtime" / "roblox-plugin-tools.json").read_text())
tools = catalog["tools"]
assert len(tools) == 26 and len({t["name"] for t in tools}) == 26
assert {t["permission"] for t in tools} == {"read", "project", "full"}
assert sum(t["permission"] == "read" for t in tools) == 8
assert sum(t["permission"] in ("read", "project") for t in tools) == 17

plugin_source = (ROOT / "roblox-plugin" / "MultiScriptCompanion.server.lua").read_text(encoding="utf-8")
for required in [
    'BRIDGE_URL = "http://127.0.0.1:17614"', 'PLUGIN_VERSION = "'+json.loads((ROOT/'extension/manifest.json').read_text())['version']+'"',
    "DIAGNOSTIC_VERSION = 3", '"/plugin/register"', '"/plugin/next"',
    '"/plugin/result"', '"/plugin/unregister"', "PERMISSION_RANK",
    "Confirm Full tools", "Run non-destructive readiness scan", "readinessScore",
]:
    assert required in plugin_source, required
for tool in tools:
    assert f"handlers.{tool['name']}=" in plugin_source, tool["name"]
assert "loadstring(" not in plugin_source
assert "loadstring(" not in plugin_source and "ScriptEditorService" in plugin_source

class FakeClient:
    tools_cache = [{"name": "get_studio_state"}, {"name": "script_read"}]
    def is_alive(self): return True

bridge.mgr.clients = {"roblox": FakeClient()}
bridge.probe_studio = lambda: {"app": True, "place": True}

async def request(port, method, path, body=None, headers=None):
    payload = json.dumps(body).encode() if body is not None else b""
    merged = {"Host": "127.0.0.1", "Content-Length": str(len(payload)), "Connection": "close"}
    if body is not None: merged["Content-Type"] = "application/json"
    merged.update(headers or {})
    lines = "".join(f"{k}: {v}\r\n" for k, v in merged.items())
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(f"{method} {path} HTTP/1.1\r\n{lines}\r\n".encode("ascii") + payload)
    await writer.drain()
    raw = await reader.read()
    writer.close(); await writer.wait_closed()
    head, data = raw.split(b"\r\n\r\n", 1)
    return int(head.split()[1]), json.loads(data)

async def main():
    server = await asyncio.start_server(bridge.plugin_http_handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        assert not any(t["name"].startswith("msrb_") for t in bridge.mgr.list_tools())
        code, registered = await request(port, "POST", "/plugin/register", {
            "pluginVersion": "6.49.9", "pluginId": "test-plugin", "executionEnabled": True, "permissionMode": "read"
        })
        assert code == 200 and registered["toolCount"] == 8
        token = registered["token"]
        auth = {"Authorization": f"Bearer {token}"}
        assert sum(t["name"].startswith("msrb_") for t in bridge.mgr.list_tools()) == 8

        code, _ = await request(port, "GET", "/plugin/next")
        assert code == 403
        try:
            bridge._companion_call("msrb_replace_script", {"path": "Workspace.X", "source": ""}, 1)
            raise AssertionError("read mode accepted a Full tool")
        except RuntimeError as exc:
            assert "needs companion permission 'full'" in str(exc)

        call_task = asyncio.create_task(asyncio.to_thread(bridge._companion_call, "msrb_project_summary", {}, 5))
        job = None
        for _ in range(20):
            code, polled = await request(port, "GET", "/plugin/next", headers=auth)
            assert code == 200
            job = polled.get("job")
            if job: break
            await asyncio.sleep(0.02)
        assert job and job["tool"] == "msrb_project_summary" and job["permission"] == "read"
        code, result = await request(port, "POST", "/plugin/result", {
            "id": job["id"], "result": {"ok": True, "data": {"placeName": "Test Place"}}
        }, auth)
        assert code == 200 and result["ok"]
        completed = await call_task
        assert "Test Place" in completed["text"]

        heartbeat = {
            "pluginVersion": "6.49.9", "placeId": 42, "placeName": "T" * 300,
            "diagnosticVersion": 3, "scriptCount": 99_999_999, "moduleCount": 3,
            "readinessScore": 140, "issueCount": 500, "highIssueCount": 7,
            "scanDurationMs": -5, "ignoredSecret": "must not persist",
        }
        code, result = await request(port, "POST", "/plugin/heartbeat", heartbeat)
        assert code == 200 and result["ok"]
        assert "ignoredSecret" not in bridge.plugin_state
        assert bridge.plugin_state["sessionToken"] == token and bridge.plugin_state["permissionMode"] == "read"
        assert len(bridge.plugin_state["placeName"]) == 120
        assert bridge.plugin_state["scriptCount"] == 10_000_000
        assert bridge.plugin_state["readinessScore"] == 100
        assert bridge.plugin_state["issueCount"] == 100
        assert bridge.plugin_state["scanDurationMs"] == 0

        code, public_catalog = await request(port, "GET", "/catalog?fresh=1")
        assert code == 200 and public_catalog["nativeToolCount"] == 2 and public_catalog["companionPluginTools"] == 26
        code, status = await request(port, "GET", "/status")
        assert code == 200 and status["bridgeVersion"] == json.loads((ROOT / "extension/manifest.json").read_text())["version"]
        assert status["roblox"]["connected"] is True and status["companionPlugin"]["connected"] is True
        assert "sessionToken" not in status["companionPlugin"] and "executionLastSeen" not in status["companionPlugin"]

        code, elevated = await request(port, "POST", "/plugin/register", {
            "pluginVersion": "6.49.9", "pluginId": "test-plugin", "executionEnabled": True, "permissionMode": "full"
        })
        assert code == 200 and elevated["toolCount"] == 26 and elevated["token"] != token
        token = elevated["token"]; auth = {"Authorization": f"Bearer {token}"}
        assert sum(t["name"].startswith("msrb_") for t in bridge.mgr.list_tools()) == 26
        code, _ = await request(port, "POST", "/plugin/unregister", {}, auth)
        assert code == 200 and not bridge._companion_execution_available()
        assert not any(t["name"].startswith("msrb_") for t in bridge.mgr.list_tools())
        code, _ = await request(port, "GET", "/missing")
        assert code == 404

asyncio.run(main())
print("PASS Roblox companion: 26 tools, tier gating, ephemeral auth, job round-trip, heartbeat preservation, and disable")
