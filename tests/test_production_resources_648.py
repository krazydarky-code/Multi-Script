import importlib.util,json,sys,types
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'runtime'))
import skill_references as refs
w=types.ModuleType('websockets');w.ConnectionClosed=Exception;sys.modules.setdefault('websockets',w)
spec=importlib.util.spec_from_file_location('production_bridge',R/'runtime/bridge.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
for sid in ['roblox-studio-gui-composition','roblox-pro-animation']:
 value=json.loads(b.MCPManager._dispatch(types.SimpleNamespace(disabled=set()), 'ms_get_skill',{'skill_id':sid},10)['text']);assert value['resources']['tool']=='ms_skill_reference';assert len(value['executionWorkflow']['execute'])>1000
 entry=json.loads(refs.read({'skill_id':sid})['text']);assert 'Inspect' in entry['text'] and 'Integrate' in entry['text'] and 'Verify' in entry['text'];assert 'asset ID' in entry['text']
 provenance=json.loads(json.loads(refs.read({'skill_id':sid,'path':'PROVENANCE.json'})['text'])['text']);assert len(provenance['sources'])==3 and all(len(x['sha256'])==64 for x in provenance['sources'])
assert len(json.loads((R/'runtime/skills.json').read_text(encoding='utf-8')))==249
print('PASS actual Python skill and bounded resource retrieval, detailed stable workflows, supplied-reference provenance, and all 249 IDs retained.')
