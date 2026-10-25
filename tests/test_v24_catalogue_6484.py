"""Preserve the user-supplied v24 catalog and verify its effective shared policy."""
import hashlib,importlib.util,json,os,sys,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'tools'),str(R/'runtime')]
import schema_audit
b=schema_audit.load_bridge()
raw=json.loads((R/'runtime/skills.json').read_text(encoding='utf-8'))
restored=json.loads((R/'runtime/skill-restorations.json').read_text())['restoredSkillIds']
assert len(raw)==249 and len(restored)==8
base={k:v for k,v in raw.items() if k not in restored}
assert len(base)==241
assert hashlib.sha256(json.dumps(base,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()=='bbec8fcbf1e65661070093ca4059820efc46c4021d88458d69ef5995555f5ff2'
class Manager:
 def health(self):return []
for sid in ['check-clean-ui','check-props','code-quality','scripting-power','fix-errors','game-systems','npc-pathfinding','vfx-assets']:
 skill=json.loads(b._builtin_call('ms_get_skill',{'skill_id':sid},Manager())['text'])
 assert skill['id']==sid and skill['executionWorkflow']['execute'] and skill['studioStandard']['definitionOfDone']
 assert b._load_skills()[sid]['productionContractV6361']['workflow'] and b._load_skills()[sid]['completionPolicy']
 assert skill['steps']==raw[sid]['steps'],sid
with tempfile.TemporaryDirectory(prefix='ms-shared-policy-') as folder:
 root=Path(folder);skills=root/'skills.json';policy=root/'policy.json'
 skills.write_text('{"fixture":{"name":"Fixture","steps":["Preserve this step"],"completionPolicy":"Specific value wins"}}')
 policy.write_text('{"qualityProfile":"first","completionPolicy":"shared value"}')
 previous=b.SKILL_SHARED_POLICY_PATH
 try:
  b.SKILL_SHARED_POLICY_PATH=str(policy);b._CATALOG_CACHE.pop('skills',None)
  first=b._load_catalog_json(str(skills),'skills')['fixture'];assert first['qualityProfile']=='first' and first['completionPolicy']=='Specific value wins' and first['instructions']=='Preserve this step'
  policy.write_text('{"qualityProfile":"updated policy","completionPolicy":"shared value"}')
  second=b._load_catalog_json(str(skills),'skills')['fixture'];assert second['qualityProfile']=='updated policy' and second['completionPolicy']=='Specific value wins'
 finally:b.SKILL_SHARED_POLICY_PATH=previous;b._CATALOG_CACHE.pop('skills',None)
print('PASS all 241 base user-supplied v24 skill definitions preserved, eight core skills retrieve full effective contracts, policy-only hot reload and per-skill overrides.')
