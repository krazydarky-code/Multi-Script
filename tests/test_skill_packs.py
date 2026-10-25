import importlib.util,json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
w=types.ModuleType('websockets'); w.ConnectionClosed=Exception; sys.modules.setdefault('websockets',w)
spec=importlib.util.spec_from_file_location('ms_bridge',ROOT/'runtime'/'bridge.py'); b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
class M: pass
packs=json.load(open(ROOT/'runtime'/'skill-packs.json'))
assert packs['addedInThisRelease']==180
assert {k:v['count'] for k,v in packs['packs'].items()}=={'roblox':34,'unity':33,'godot':33}
listing=json.loads(b._builtin_call('ms_list_skills',{'engine':'unity','query':'shader','limit':10},M())['text'])
assert listing['count']>=1 and all(x['engine']=='unity' for x in listing['skills'])
rec=json.loads(b._builtin_call('ms_recommend_skills',{'engine':'roblox','objective':'secure server validated remote events and prevent exploits','limit':5},M())['text'])
ids=[x['id'] for x in rec['recommendations']]
assert any(x in ids for x in ['roblox-remote-security','roblox-anti-exploit']),ids
skill=json.loads(b._builtin_call('ms_get_skill',{'skill_id':'godot-control-ui'},M())['text'])
assert skill['engine']=='godot' and len(skill['steps'])>=6 and len(skill['qualityGates'])>=5
print('PASS 100 engine skill packs, filters, recommendations, and detail')
