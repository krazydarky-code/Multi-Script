"""Exercise the shipped WebSocket origin boundary without opening a LAN port."""
import asyncio,importlib.util,json
from pathlib import Path
import websockets
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('phone_wire_bridge',root/'runtime/bridge.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
b.mgr=b.MCPManager()
b.probe_studio=lambda:{'app':False,'place':False}
b.probe_unity=lambda:False
b.probe_godot=lambda:False
b._roblox_studio_app_running=lambda:False
async def main():
    async with websockets.serve(b.handler,'127.0.0.1',0,max_size=16*1024*1024) as server:
        url=f'ws://127.0.0.1:{server.sockets[0].getsockname()[1]}'
        async def request(origin,owner='test-browser-profile',op='status'):
            async with websockets.connect(url,origin=origin) as ws:
                await ws.send(json.dumps({'id':17,'type':'mobile_admin','op':op,'owner':owner}))
                for _ in range(20):
                    item=json.loads(await asyncio.wait_for(ws.recv(),8))
                    if item.get('id')==17:return item
                raise AssertionError('No matching reply')
        for origin in (None,'https://example.com','https://c.vani.ai','chrome-extension://'+'a'*32):
            result=await request(origin);assert not result['ok'] and 'origin' in result['error']
        origin=b.mobile_remote.extension_origin()
        result=await request(origin);assert result['ok'] and not result['enabled']
        result=await request(origin,owner='bad');assert not result['ok'] and 'identity' in result['error']
        result=await request(origin,op='arbitrary');assert not result['ok'] and 'Unsupported' in result['error']
        assert not b.PHONE_REMOTE.status()['enabled']
    print('PASS real bridge WebSocket: only pinned extension origin can administer remote; rejects provider/web/missing origins, invalid identity and unknown operations; listener stays off.')
try:asyncio.run(main())
finally:b.PHONE_REMOTE.close()
