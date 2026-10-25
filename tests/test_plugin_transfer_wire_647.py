import asyncio,importlib.util,json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'))
w=types.ModuleType('websockets');w.ConnectionClosed=Exception;sys.modules.setdefault('websockets',w)
spec=importlib.util.spec_from_file_location('wire_bridge_647',ROOT/'runtime/bridge.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
async def request(port,method,path,data=None,token=None):
 raw=json.dumps(data).encode() if data is not None else b''
 headers=f'Host: 127.0.0.1\r\nContent-Length: {len(raw)}\r\nContent-Type: application/json\r\n'+(f'Authorization: Bearer {token}\r\n' if token else '')
 reader,writer=await asyncio.open_connection('127.0.0.1',port);writer.write(f'{method} {path} HTTP/1.1\r\n{headers}\r\n'.encode()+raw);await writer.drain();response=await reader.read();writer.close();await writer.wait_closed();head,body=response.split(b'\r\n\r\n',1);return int(head.split()[1]),json.loads(body)
async def main():
 server=await asyncio.start_server(b.plugin_http_handler,'127.0.0.1',0);port=server.sockets[0].getsockname()[1]
 async with server:
  selected=['msrb_replace_script','msrb_source_transfer','msrb_console_read','msrb_project_summary']
  code,reg=await request(port,'POST','/plugin/register',{'executionEnabled':True,'permissionMode':'full','enabledTools':selected});assert code==200 and reg['toolCount']==len(selected);token=reg['token']
  assert (await request(port,'GET','/plugin/console'))[0]==403
  snapshot=b.engine_snapshot({'place':False,'app':True},False,False);rbx=next(x for x in snapshot if x['id']=='roblox');assert rbx['companionConnected'] and not rbx['nativeConnected'] and rbx['companionTools']==len(selected)
  b.mgr.disabled.add('roblox');assert not any(x.get('companionConnected') for x in b.engine_snapshot({'place':False,'app':True},False,False));b.mgr.disabled.discard('roblox')
  invalid=await request(port,'POST','/plugin/register',{'executionEnabled':True,'permissionMode':'full','enabledTools':['invented']});assert invalid[0]==400
  assert b.plugin_state['sessionToken']==token,'Invalid registrations must preserve an active session'
  source='-- café 🧱\n'*9000+'return 47';staged=[];received=0;commits=0;seen=[]
  task=asyncio.create_task(asyncio.to_thread(b.mgr.call,'msrb_replace_script',{'path':'ServerScriptService.Main','source':source},30))
  while not task.done():
   _,reply=await request(port,'GET','/plugin/next',token=token);job=reply.get('job')
   if not job:await asyncio.sleep(.005);continue
   args=job['arguments'];seen.append(args['action']);out={'transfer_id':'wire-source','state':'staging'}
   if args['action']=='begin':assert args['total_bytes']==len(source.encode())
   if args['action']=='append':
    chunk=args['source'];assert len(chunk.encode())<=32768 and args['offset']==received;staged.append(chunk);received+=len(chunk.encode());out['received_bytes']=received
   if args['action']=='commit':commits+=1;assert ''.join(staged)==source;out={'transfer_id':'wire-source','state':'committed','readBack':True}
   assert (await request(port,'POST','/plugin/result',{'id':job['id'],'result':{'ok':True,'data':out}},token))[0]==200
  result=json.loads((await task)['text']);assert result['readBack'] and commits==1 and seen[0]=='begin' and seen[-1]=='commit'
  _,console=await request(port,'GET','/plugin/console',token=token);assert any(x['tool']=='msrb_replace_script' and x['status']=='done' for x in console['entries'])
  # Result uploads exceed the old 64 KiB ceiling only with the plugin token.
  read=asyncio.create_task(asyncio.to_thread(b._companion_call,'msrb_console_read',{},10))
  job=None
  while not job:_,packet=await request(port,'GET','/plugin/next',token=token);job=packet.get('job');await asyncio.sleep(.005)
  big={'id':job['id'],'result':{'ok':True,'text':'x'*90000}}
  assert (await request(port,'POST','/plugin/result',big))[0]==413
  assert (await request(port,'POST','/plugin/result',big,token))[0]==200
  assert len((await read)['text'])==90000
  assert (await request(port,'POST','/plugin/toolset',{'enabledTools':['msrb_project_summary']},token))[0]==200
  try:await asyncio.to_thread(b._companion_call,'msrb_replace_script',{'path':'ServerScriptService.Main','source':'x'},1);raise AssertionError('Disabled tool dispatched')
  except RuntimeError as error:assert 'disabled' in str(error)
  await request(port,'POST','/plugin/heartbeat',{'pluginVersion':'6.49.9'},token);assert b.plugin_state['enabledTools']==['msrb_project_summary']
  await request(port,'POST','/plugin/unregister',{},token)
asyncio.run(main())
print('PASS actual loopback HTTP + bridge: automatic Unicode chunking, one commit, execution receipts, authenticated large results, per-tool disable and heartbeat preservation. Native Studio operations are fixtures.')
