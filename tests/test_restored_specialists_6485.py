import json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'tools'),str(R/'runtime')]
import schema_audit
b=schema_audit.load_bridge();restored=json.loads((R/'runtime/skill-restorations.json').read_text());skills=b._load_skills()
class M:
 def health(self):return []
assert len(skills)==249 and len(restored['restoredSkillIds'])==8
for sid in restored['restoredSkillIds']:
 skill=json.loads(b._builtin_call('ms_get_skill',{'skill_id':sid},M())['text'])
 assert len(skill['steps'])>=8 and len(set(skill['steps']))==len(skill['steps'])
 assert len(skill['executionWorkflow']['execute'])>300 and len(skill['executionWorkflow']['verify'])>200
 assert len(skill['relatedSkills'])>=4 and all(ref in skills for ref in skill['relatedSkills'])
 assert skill['researchReferences'][0].startswith('https://')
 assert 'Instructions must' not in str(skill)
shape=skills['blender-shape-keys'];assert 'vertex count and order' in ' '.join(shape['steps']) and 'editable maps' not in ' '.join(shape['steps'])
bake=skills['blender-texture-baking'];assert 'cage/ray' in ' '.join(bake['steps'])
figma=skills['figma-prototyping'];assert 'cannot author prototype links' in ' '.join(figma['steps'])
for tid in restored['restoredVirtualToolIds']:
 detail=json.loads(b._builtin_call('ms_virtual_tool_details',{'tool_id':tid},M())['text']);assert detail['engine']=='blender' and len(detail['stages'])>=8
 run=json.loads(b._builtin_call('ms_run_virtual_tool',{'tool_id':tid,'request':'Deliver the inspected game asset','project_context':'fixture scope'},M())['text']);assert run['outputContract']['realArtifactRequired'] and run['silentAugmentation']
print('PASS eight reviewed specialist restorations and two Blender guidance tools: real retrieval, concrete domain methods, valid collaborators, honest prototype/import boundaries and actual-artifact contracts.')
