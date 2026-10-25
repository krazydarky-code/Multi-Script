import json,sys
from pathlib import Path
from lupa import LuaRuntime
ROOT=Path(__file__).resolve().parents[1]
lua=LuaRuntime(unpack_returned_tuples=True)
def plain(value):
 if hasattr(value,'items'):
  items=dict(value.items())
  if items and all(type(k)is int for k in items) and set(items)==set(range(1,len(items)+1)):return [plain(items[i]) for i in range(1,len(items)+1)]
  return {k:plain(v) for k,v in items.items()}
 return value
def table(value):
 if isinstance(value,dict):return lua.table_from({k:table(v) for k,v in value.items()})
 if isinstance(value,list):return lua.table_from([table(v) for v in value])
 return value
requests=[]
def request(value):
 data=plain(value);requests.append(data);url=data['Url']
 reply={'ok':True}
 if url.endswith('/plugin/register'):reply['token']='fixture-token'
 if url.endswith('/plugin/console'):reply={'entries':[],'lastSequence':0}
 return table({'Success':True,'StatusCode':200,'Body':json.dumps(reply)})
lua.globals().py_encode=lambda x:json.dumps(plain(x),ensure_ascii=False)
lua.globals().py_decode=lambda x:table(json.loads(x))
lua.globals().py_request=request
lua.execute((ROOT/'tests/support/roblox-plugin-host.lua').read_text())
api=lua.execute((ROOT/'roblox-plugin/MultiScriptCompanion.server.lua').read_text(encoding='utf-8'))
assert set(api['ui']['pages'].keys())=={'Overview','Toolset','Console','Guide'}
assert len(list(api['ui']['toolRows'].keys()))==26
api['registerMode']('full')
script=lua.globals().fixtureScript('return "original"')
def call(name,args):return plain(api['executeJob'](table({'tool':name,'permission':next(t['permission'] for t in json.loads((ROOT/'runtime/roblox-plugin-tools.json').read_text())['tools'] if t['name']==name),'arguments':args})))
assert call('msrb_replace_script',{'path':'game.ServerScriptService.Main','source':'return "safe editor write"'})['readBack']
assert script['EditorBuffer']=='return "safe editor write"'
lua.globals().fixtureConflict=True
try:call('msrb_replace_script',{'path':'ServerScriptService.Main','source':'must not overwrite'});raise AssertionError('Editor retry conflict accepted')
except Exception as error:assert 'changed' in str(error)
assert script['EditorBuffer']=='user edited concurrently'
props=call('msrb_get_properties',{'paths':['ServerScriptService.Main'],'properties':['Source','Name']});assert len(props['instances'])==1 and 'Use Full-tier' in json.dumps(props) and 'user edited concurrently' not in json.dumps(props)
source='-- café 🧱\n'*3000+'return 47'
begin=call('msrb_source_transfer',{'action':'begin','path':'ServerScriptService.Main','total_bytes':len(source.encode())});tid=begin['transfer_id']
try:call('msrb_source_transfer',{'action':'commit','transfer_id':tid});raise AssertionError('Incomplete write accepted')
except Exception as error:assert 'incomplete' in str(error)
offset=0
for part in [source[i:i+10000] for i in range(0,len(source),10000)]:
 result=call('msrb_source_transfer',{'action':'append','transfer_id':tid,'offset':offset,'source':part});offset+=len(part.encode());assert result['received_bytes']==offset
 assert call('msrb_source_transfer',{'action':'append','transfer_id':tid,'offset':offset-len(part.encode()),'source':part})['duplicate']
assert call('msrb_source_transfer',{'action':'commit','transfer_id':tid})['state']=='committed'
assert script['EditorBuffer']==source
assert call('msrb_source_transfer',{'action':'commit','transfer_id':tid})['duplicate']
page=call('msrb_read_script',{'path':'ServerScriptService.Main','max_chars':1001});assert page['next_offset'] and page['source'].encode().decode()==page['source']
begin=call('msrb_source_transfer',{'action':'begin','path':'ServerScriptService.Main','total_bytes':1});tid=begin['transfer_id']
call('msrb_source_transfer',{'action':'append','transfer_id':tid,'offset':0,'source':'x'});script['EditorBuffer']='user edited independently'
try:call('msrb_source_transfer',{'action':'commit','transfer_id':tid});raise AssertionError('Concurrent edits overwritten')
except Exception as error:assert 'editor changed' in str(error)
assert script['EditorBuffer']=='user edited independently'
lua.globals().fixturePlaying=True
try:call('msrb_replace_script',{'path':'ServerScriptService.Main','source':'bad'});raise AssertionError('Play-mode mutation accepted')
except Exception as error:assert 'Edit mode' in str(error)
lua.globals().fixturePlaying=False
api['ui']['toolRows']['msrb_replace_script']['toggle']['Activated']['Fire'](api['ui']['toolRows']['msrb_replace_script']['toggle']['Activated'])
try:call('msrb_replace_script',{'path':'ServerScriptService.Main','source':'bad'});raise AssertionError('Disabled tool ran')
except Exception as error:assert 'disabled' in str(error)
assert any(x['Url'].endswith('/plugin/toolset') for x in requests)==False,'Task scheduling is deliberately inert in the native API fixture'
api['disableExecution']()
try:call('msrb_read_script',{'path':'ServerScriptService.Main'});raise AssertionError('Off mode ran')
except Exception as error:assert 'permission' in str(error)
print('PASS shipped plugin behavior: four tabs/26 toggles, editor buffers, Unicode staged commit/read paging, idempotent receipts, incomplete/conflicting writes, Play-mode and permission guards. Roblox APIs are fixtures, not live Studio.')

# A browser layout preview uses the labels/colors constructed by the shipped Lua.
# It is a design review artifact, not Roblox's native renderer.
if '--snapshot' in sys.argv:
 def snapshot(obj):
  props=obj['_props'];color=props['TextColor3'] or props['BackgroundColor3']
  return {'className':obj['ClassName'],'name':obj['Name'],'text':obj['Text'],'visible':obj['Visible'] is not False,'color':('#%02x%02x%02x'%tuple(round(color[c]*255) for c in ['R','G','B'])) if color else None,'children':[snapshot(x) for x in obj['_children'].values() if x['ClassName'] in ['Frame','TextLabel','TextButton','TextBox']]}
 Path(sys.argv[sys.argv.index('--snapshot')+1]).write_text(json.dumps({k:snapshot(v) for k,v in api['ui']['pages'].items()},ensure_ascii=False),encoding='utf-8')
