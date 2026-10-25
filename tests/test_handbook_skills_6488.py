import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'runtime')]
import schema_audit,ultra_handbook
b=schema_audit.load_bridge();skills=b._load_skills();pack=ultra_handbook.load()
class M:
    def health(self):return []
for sid,skill in skills.items():
    actual=json.loads(b._builtin_call('ms_get_skill',{'skill_id':sid,'objective':'Apply the relevant workflow within this inspected project.'},M())['text']);guide=actual['manualApplication'];assert guide['manual_id'] in pack['manuals'];assert guide['skillUse']['application'];assert guide['phaseChecklists'] and len(json.dumps(guide))<9000
    assert guide['fullDetail']['params']['skill_id']==sid
    for engine,route in pack['manuals'][guide['manual_id']]['skillRoutes'].items():assert all(x in skills for x in route)
assert len(skills)==249
cases={'roblox-responsive-ui':'ultragui','blender-shape-keys':'ultraanimation','godot-gpu-particles':'ultravfx','blender-sculpt-retopology':'ultramodelling','godot-procedural-generation':'ultraworld','roblox-melee-combat':'ultragameplay','unity-audio-mixer':'ultraaudio','roblox-data-store-safety':'ultranetwork','unity-profiler-memory':'ultraperformance','notion-model-router':'ultraengineering','roblox-accessibility':'ultraaccessibility','build-release':'ultraqa'}
for sid,mid in cases.items():
    result=json.loads(b._builtin_call('ms_get_skill',{'skill_id':sid,'objective':'Implement the requested improvement','manual_sections':list(ultra_handbook.PHASES)},M())['text'])['manualApplication'];assert result['manual_id']==mid,(sid,result['manual_id']);assert len(result['phaseChecklists'])==6;assert len(result['diagnostics'])==4
    for phase,steps in result['phaseChecklists'].items():assert steps==pack['manuals'][mid]['phases'][phase]
for goal in ['Explain how to build a menu','Inspect only the UI without editing it',"Don't edit this project"]:
    guide=ultra_handbook.skill_application('ui-ux-production',skills['ui-ux-production'],goal,['build','integrate']);assert guide['mode']=='inspection-only' and 'build' not in guide['phaseChecklists']
assert ultra_handbook.skill_application('ui-ux-production',skills['ui-ux-production'],'Inspect the current menu and then build the missing state')['mode']=='apply-within-request'
assert ultra_handbook.skill_application('discover-project',skills['discover-project'],'Build the game')['mode']=='inspection-only'
try:ultra_handbook.skill_application('ui-ux-production',skills['ui-ux-production'],'Build UI',['execute-anything'])
except ValueError:pass
else:raise AssertionError('Unknown phases must be rejected')
for engine in ['roblox','godot','unity','blender','figma','general']:
    result=json.loads(b._builtin_call('ms_studio_director',{'request':'Build an accessible game interface with readable animation','engine':engine},M())['text'])
    for flow in result['appliedSkillWorkflows']:
        route=flow['methodRetrieval'];assert route['skill_id']==flow['id'] and route['manual_id'] in pack['manuals'];assert 'ms_get_skill' in route['instruction']
print('PASS all 249 actual skill application results, all 12 domains, full phase retrieval, read-only/discovery scope, existing skill graph, bounded guides and six-engine director retrieval paths.')
