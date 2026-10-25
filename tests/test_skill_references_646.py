import json,sys,ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'))
import skill_references as refs,studio_hub,schema_repair

def rejected(args):
    try:refs.read(args)
    except ValueError:return
    raise AssertionError('Unsafe reference accepted')

sid='blender-reference-blockout'
index=json.loads(refs.read({'skill_id':sid,'action':'index'})['text']);assert 'scripts/build.py' in index['files'] and 'LICENSE' in index['files']
entry=json.loads(refs.read({'skill_id':sid})['text']);assert 'Goofy Studio' in entry['text'] and 'actual runtime tests' in entry['text']
image=refs.read({'skill_id':sid,'path':'examples/dragon.jpg'});assert image['images'][0]['mimeType']=='image/jpeg';assert 'not a render' in image['text']
first=json.loads(refs.read({'skill_id':sid,'path':'scripts/studkit.py','max_chars':1000})['text']);assert first['next_offset']==1000
second=json.loads(refs.read({'skill_id':sid,'path':'scripts/studkit.py','offset':1000,'max_chars':1000})['text']);assert first['text']!=second['text']
for path in ['../skills.json','/runtime/config.json','C:/private.txt','scripts/../../../config.json']:
    rejected({'skill_id':sid,'path':path})
rejected({'skill_id':'unknown','path':'LICENSE'})
for path in (refs.HERE/'stud-creatures').rglob('*.py'):ast.parse(path.read_text(encoding='utf-8'))
build=(refs.HERE/'stud-creatures/scripts/build.py').read_text();assert '10509831729' not in build and 'No verified stud texture IDs' in build
style=json.loads(studio_hub.call_tool('ms_skill_reference',{'skill_id':'roblox-architecture-services'})['text']);assert '80%' in style['text'] and 'Existing project style wins' in style['text']
schema={'type':'object','additionalProperties':False,'properties':{'target_file':{'type':'string'},'studio_id':{'type':'string'}},'required':['target_file','studio_id']}
fixed,notes=schema_repair.repair_arguments(schema,{'path':'game.ServerScriptService.Main','studio_id':'studio-a'},'script_read');assert fixed=={'target_file':'game.ServerScriptService.Main','studio_id':'studio-a'} and notes
missing,_=schema_repair.repair_arguments(schema,{'studio_id':'studio-a'},'script_read');assert 'target_file' not in missing,'Never invent a missing target'
skills=json.loads((ROOT/'runtime/skills.json').read_text());assert len(skills)==249
restored=set(json.loads((ROOT/'runtime/skill-restorations.json').read_text())['restoredSkillIds'])
assert len(restored)==8 and all(v['executionWorkflow']['revision']==('multi-script-restored-v6485' if sid in restored else 'multi-script-workflows-v6') for sid,v in skills.items())
assert skills[sid]['resources']['tool']=='ms_skill_reference'
print('PASS licensed full-method/example/image access, pagination/path boundaries, source syntax, texture handoff, service style, exact script target alias repair and 249 retained base/restored workflows.')
