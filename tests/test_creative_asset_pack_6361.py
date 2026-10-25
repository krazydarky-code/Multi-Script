import importlib.util, json, sys, types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
w=types.ModuleType('websockets'); w.ConnectionClosed=Exception; sys.modules.setdefault('websockets',w)
spec=importlib.util.spec_from_file_location('ms_bridge_6361_assets',ROOT/'runtime'/'bridge.py')
b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
class Manager:
    def health(self): return []
def call(name,args): return json.loads(b._builtin_call(name,args,Manager())['text'])
pack=call('ms_create_icon_pack',{'name':'qa-sword-shield','icons':['sword','shield','heart','coin','settings','sparkles'],'style':'duotone','size':96,'primary_color':'#f5f7ff','accent_color':'#32d7cf','background':'#111827'})
assert pack['created'] and pack['iconCount']==6 and pack['style']=='duotone'
assert all(Path(x['path']).is_file() and Path(x['path']).read_text().startswith('<svg') for x in pack['icons'])
assert Path(pack['spriteSheet']).is_file() and Path(pack['contactSheet']).is_file() and Path(pack['manifest']).is_file()
manifest=json.loads(Path(pack['manifest']).read_text())
assert manifest['version']=='6.49.9' and manifest['icons'][0]['name']=='sword' and 'does not automatically upload' in manifest['usage']['roblox']
# Unknown glyphs use a deterministic fallback rather than failing or emitting broken SVG.
fallback=call('ms_create_icon_pack',{'icons':['custom-unknown'],'style':'pixel'})
assert fallback['icons'][0]['knownGlyph'] is False and Path(fallback['icons'][0]['path']).is_file()
# UI style palettes are materially distinct and safely escaped.
ui=call('ms_create_canvas_ui',{'name':'qa-cyberpunk-ui','width':800,'height':600,'theme':'cyberpunk','components':[{'type':'text','x':30,'y':50,'width':300,'height':40,'label':'Inventory'},{'type':'button','x':40,'y':120,'width':180,'height':52,'label':'Equip'}]})
assert Path(ui['created']).is_file() and ui['tokens']['accent']=='#2de2e6' and 'linearGradient' in ui['svg'] and 'Equip' in ui['svg']
assert ui['components']==2 and Path(ui['tokensFile']).is_file() and Path(ui['manifest']).is_file()
# Every advertised visual style maps to a concrete palette and creates a source file.
styles=['dark','light','game','glass','anime','fantasy','low-poly','realistic-pbr','cyberpunk','gothic','cozy','pixel','minimal','sci-fi','cartoon','luxury']
accents=set()
for style in styles:
    out=call('ms_create_canvas_ui',{'name':'palette-'+style,'theme':style,'width':320,'height':320,'accent':'not-a-color','components':[{'type':'button','x':10,'y':10,'width':100,'height':40,'label':style}]})
    assert Path(out['created']).is_file() and out['tokens']['theme']==style and out['tokens']['accent'].startswith('#')
    accents.add(out['tokens']['accent'])
assert len(accents)>=10, 'themes should have materially distinct default accents'
print('PASS 6.49.9 real SVG icon pack, sprite/contact sheets, manifest, unknown glyph fallback and polished styled UI')
