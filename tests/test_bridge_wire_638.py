"""Actual loopback WebSocket protocol with the real runtime handler and tools.
Native editor launch, process cleanup and the user's configured bridge are not run.
"""
import asyncio,importlib.util,json,sys
from pathlib import Path
import websockets
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('wire_bridge',root/'runtime/bridge.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
b.mgr=b.MCPManager()
b.probe_studio=lambda:{'app':False,'place':False}
b.probe_unity=lambda:False
b.probe_godot=lambda:False
b._roblox_studio_app_running=lambda:False
async def main():
    async with websockets.serve(b.handler,'127.0.0.1',0,max_size=16*1024*1024) as server:
        port=server.sockets[0].getsockname()[1]
        async with websockets.connect(f'ws://127.0.0.1:{port}',max_size=16*1024*1024) as ws:
            seq=0
            async def request(kind,**fields):
                nonlocal seq
                seq+=1;await ws.send(json.dumps({'id':seq,'type':kind,**fields}))
                for _ in range(15):
                    item=json.loads(await asyncio.wait_for(ws.recv(),8))
                    if item.get('id')==seq:return item
                raise AssertionError('Matching wire reply did not arrive')
            tools=await request('list_tools');assert tools['type']=='tools' and any(t['name']=='ms_get_skill' for t in tools['tools'])
            listed=await request('call_tool',name='ms_list_skills',arguments={'query':'ui-ux-production','limit':1})
            assert listed['ok'];data=json.loads(listed['text']);assert data['count']==1
            skill=await request('call_tool',name='ms_get_skill',arguments={'skill_id':'ui-ux-production'})
            assert skill['ok'] and json.loads(skill['text'])['id']=='ui-ux-production'
            icon=await request('call_tool',name='ms_create_icon_pack',arguments={'name':'wire-638','icons':['sparkles'],'style':'duotone'})
            assert icon['ok'];artifact=json.loads(icon['text']);assert artifact['created'] and Path(artifact['icons'][0]['path']).read_text().startswith('<svg')
            print('PASS actual loopback WebSocket catalog, skill query/retrieval and real SVG artifact generation through the shipped runtime handler.')
asyncio.run(main())
