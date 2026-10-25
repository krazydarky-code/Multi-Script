"""Audit actual skill/tool references and bounded, usable director guidance."""
import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'runtime')]
import schema_audit
b=schema_audit.load_bridge()
_sp=json.loads((ROOT/'runtime/skill-shared-policy.json').read_text(encoding='utf-8'));skills={k:{**_sp,**v} for k,v in json.loads((ROOT/'runtime/skills.json').read_text(encoding='utf-8')).items()}
names=b.BUILTIN_TOOL_NAMES|set(b._TOOLKIT.REGISTRY)
for sid,skill in skills.items():
    assert all(ref in names for ref in re.findall(r'\bms_[a-z0-9_]+',json.dumps(skill))),sid
    assert len(skill.get('tags',[]))==len(set(skill.get('tags',[]))),sid
    flow=skill['executionWorkflow']
    assert all(isinstance(flow[k],str) and flow[k].strip() for k in ['inspect','execute','verify','adaptation','recovery']),sid
    assert 'never permission' in flow['adaptation'],sid
class Manager:
    def health(self):return []
for engine in ['roblox','unity','godot','blender','figma','general']:
    for objective in ['Build a coherent game UI with keyboard navigation.','Inspect the existing project without editing it.','Fix an animation transition with actual motion evidence.']:
        out=json.loads(b._builtin_call('ms_studio_director',{'request':objective,'engine':engine},Manager())['text'])
        applied=out['appliedSkillWorkflows'];assert 1<=len(applied)<=6
        assert len({x['id'] for x in applied})==len(applied)
        assert all(x['id'] in out['selectedSkills'] and x['id'] in skills for x in applied)
        assert all(all(x.get(k) for k in ['inspect','execute','verify']) for x in applied)
        assert 'without unrequested edits' in out['scopeRule']
        assert sum(len(rule) for entry in applied for rule in entry.get('rules',[])) <= b.MESH_RULES_CHAR_BUDGET+8000
        summaries=[{k:v for k,v in entry.items() if k!='rules'} for entry in applied]
        assert len(json.dumps(summaries))<12000
discovery=skills['discover-project'];assert discovery['capabilityRole']=='validation' and discovery['capabilityDomain']=='engineering'
assert 'Do not edit' in discovery['completionPolicy'] and 'without changing' in discovery['executionWorkflow']['execute']
assert all(target not in b.RETIRED_FROM_CATALOGUE for target in b.RETIRED_FROM_CATALOGUE.values())
print(f'PASS {len(skills)} actual skill contracts/tool references/tag sets, 18 engine/objective applied-workflow results, read-only discovery and canonical aliases.')

import studio_hub
assert studio_hub.validate_skill({'id':'figma-user-flow','name':'Figma flow','engine':'figma','instructions':'Inspect the existing components, implement the requested flow and verify actual keyboard and touch states.'})['engine']=='figma'
