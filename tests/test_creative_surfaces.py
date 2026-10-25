import importlib.util,json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
w=types.ModuleType('websockets'); w.ConnectionClosed=Exception; sys.modules.setdefault('websockets',w)
spec=importlib.util.spec_from_file_location('ms_bridge',ROOT/'runtime'/'bridge.py'); b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
class M:
 def health(self): return [{'id':'figma','alive':True,'tools':12}]
m=M()
t=json.loads(b._builtin_call('ms_create_canvas_texture',{'name':'studded test','pattern':'studs','width':256,'height':256,'tile_size':32,'seed':7},m)['text'])
assert t['format']=='SVG' and t['pattern']=='studs' and Path(t['created']).exists() and '<circle' in t['svg']
u=json.loads(b._builtin_call('ms_create_canvas_ui',{'name':'shop mockup','width':800,'height':600,'title':'Shop','theme':'game','components':[{'type':'frame','x':40,'y':40,'width':720,'height':520,'label':''},{'type':'button','x':500,'y':500,'width':200,'height':52,'label':'Purchase'}]},m)['text'])
assert u['format']=='SVG' and u['components']==2 and Path(u['created']).exists() and 'Purchase' in u['svg']
f=json.loads(b._builtin_call('ms_figma_handoff',{'objective':'Design a game shop','screens':['Shop','Item details']},m)['text'])
assert f['figmaMcpAvailable'] is True and 'Auto Layout' in f['componentRequirements']
print('PASS real SVG texture/UI creation and Figma-ready handoff')
