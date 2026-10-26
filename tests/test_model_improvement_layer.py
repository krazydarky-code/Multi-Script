import importlib.util,json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
w=types.ModuleType('websockets');w.ConnectionClosed=Exception;sys.modules.setdefault('websockets',w)
s=importlib.util.spec_from_file_location('model_layer_bridge',ROOT/'runtime'/'bridge.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
skills={k:{**json.load(open(ROOT/'runtime'/'skill-shared-policy.json',encoding='utf-8')),'instructions':'\n'.join(v.get('steps',[])),**v} for k,v in json.load(open(ROOT/'runtime'/'skills.json',encoding='utf-8')).items()};virtual=json.load(open(ROOT/'runtime'/'virtual-tools.json',encoding='utf-8'));standard=json.load(open(ROOT/'runtime'/'studio-standard.json',encoding='utf-8'))
assert len(skills)==249
assert all(v.get('qualityProfile')=='studio-v4-project-aware' and len(v.get('instructions',''))>100 for v in skills.values())
for v in skills.values():
 for field in ['providerRole','completionPolicy','performancePolicy','failurePolicy']:assert v.get(field),field
assert virtual['total']==263 and virtual['engineCounts']=={'roblox':90,'unity':70,'godot':70,'blender':33}
for v in virtual['tools'].values():
 assert v.get('providerRole') and len(v.get('performanceChecklist') or [])==6
 assert v['outputContract'].get('providerModelOwnsExecution') and v['outputContract'].get('nativeToolsOnly')
assert len(b.BUILTIN_TOOLS)==json.loads((ROOT/'runtime/product-manifest.json').read_text())['catalogue']['directTools'] and len(b.BUILTIN_TOOL_NAMES)==json.loads((ROOT/'runtime/product-manifest.json').read_text())['catalogue']['directTools']
assert all('provider-model' in t['description'].lower() for t in b.BUILTIN_TOOLS)
for field in ['providerExecution','performance','resultQuality','toolDiscipline']:assert len(standard[field])>=6
assert len(json.load(open(ROOT/'runtime'/'roblox-plugin-tools.json'))['tools'])==26
assert not (ROOT/'runtime'/'quality-presets.json').exists()
assert 'ms_quality_multiplier' not in b.BUILTIN_TOOL_NAMES and 'ms_adaptive_quality_inference' not in b.BUILTIN_TOOL_NAMES
assert 'ms_full_spectrum_skill_mesh' in b.BUILTIN_TOOL_NAMES and 'ms_cross_discipline_integration_review' in b.BUILTIN_TOOL_NAMES
plugin=(ROOT/'roblox-plugin'/'MultiScriptCompanion.server.lua').read_text(encoding='utf-8')
assert '/plugin/next' in plugin and '/plugin/result' in plugin and 'PERMISSION_RANK' in plugin and 'loadstring(' not in plugin
class M:
 def health(self):return []
out=json.loads(b._builtin_call('ms_studio_director',{'request':'optimize lag and frame time','engine':'roblox'},M())['text'])
assert 'ms_performance_budget_designer' in out['selectedDirectTools'] and 'ms_frame_time_optimization' in out['selectedDirectTools']
skill=json.loads(b._builtin_call('ms_get_skill',{'skill_id':next(iter(skills))},M())['text'])
assert skill['studioStandard']['providerExecution'] and skill['studioStandard']['performance']
print('PASS model-improvement-only architecture: 249 practical skills, 277 callable built-ins, 263 virtual tools, secure companion execution surface kept separate from native tools')
