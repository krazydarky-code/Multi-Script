"""Protect the old methods and exercise additions through actual skill retrieval."""
from pathlib import Path
import hashlib,json,sys
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'runtime'),str(R/'tools')]
import schema_audit,ultra_handbook
baseline=json.loads((R/'tests/fixtures/ultra-before-6493.json').read_text(encoding='utf-8'))
book=ultra_handbook.load();production=json.loads((R/'runtime/skill-resources/roblox-production/methods.json').read_text(encoding='utf-8'))
digest=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
assert hashlib.sha256((R/'runtime/skills.json').read_bytes()).hexdigest()==baseline['skillsSha256'],'Do not replace or add skill definitions for this expansion'
assert set(book['manuals'])==set(baseline['manuals']) and len(book['manuals'])==12
for mid,previous in baseline['manuals'].items():
    manual=book['manuals'][mid]
    for phase,old in previous['phases'].items():assert digest(manual['phases'][phase][:old['count']])==old['sha256'],(mid,phase,'previous checkpoints changed')
    for name,key in [('skillRoutes','routes'),('phaseExitCriteria','exits'),('acceptance','acceptance'),('diagnostics','diagnostics')]:assert digest(manual[name])==previous[key],(mid,name)
assert sum(len(v) for m in book['manuals'].values() for v in m['phases'].values())==564
assert set(production['themes'])==set(baseline['themes']) and len(production['themes'])==9
for key,value in baseline['themes'].items():assert production['themes'][key].startswith(value)
for domain in ['gui','animation']:
    for phase,value in baseline['production'][domain].items():assert production[domain][phase].startswith(value)
study=book['referenceStudies'];assert study==production['referenceStudies'];assert len(study['sources'])==25
assert [x['attachment'] for x in study['sources']]==list(range(1,26))
assert all(len(x['sha256'])==64 and x['existingStyle'] in production['themes'] and len(x['observed'])>70 for x in study['sources'])
assert 'do not prove animation timing' in study['policy']
b=schema_audit.load_bridge()
class Manager:
    def health(self):return []
original=b._load_skills();raw_before=json.dumps(original,sort_keys=True)
maximum=0
for sid,skill in original.items():
    result=json.loads(b._builtin_call('ms_get_skill',{'skill_id':sid,'objective':'Apply the requested improvement within the existing project style.'},Manager())['text'])
    guide=result['manualApplication'];maximum=max(maximum,len(json.dumps(guide)));assert len(json.dumps(guide))<9000,sid
    mid=guide['manual_id'];manual=book['manuals'][mid]
    if manual.get('referenceExpansionBaseline') and guide['mode']!='inspection-only':
        for phase,checks in guide['phaseChecklists'].items():
            additions=manual['phases'][phase][manual['referenceExpansionBaseline'][phase]:]
            assert additions and all(item in checks for item in additions),(sid,phase,'new guidance unreachable in normal skill reads')
assert json.dumps(b._load_skills(),sort_keys=True)==raw_before,'Runtime additions must not mutate cached original skills'
for sid,domain in [('roblox-studio-gui-composition','gui'),('roblox-pro-animation','animation')]:
    result=json.loads(b._builtin_call('ms_get_skill',{'skill_id':sid,'objective':'Improve the existing requested interface and animation.'},Manager())['text'])
    for field in ['inspect','craft','execute','verify','recovery']:assert result['executionWorkflow'][field].startswith(original[sid]['executionWorkflow'][field])
    assert len(result['executionWorkflow']['execute'])>len(original[sid]['executionWorkflow']['execute'])+500
    readonly=json.loads(b._builtin_call('ms_get_skill',{'skill_id':sid,'objective':'Inspect only, do not edit this project.','manual_sections':['build','integrate']},Manager())['text'])['manualApplication']
    assert readonly['mode']=='inspection-only' and set(readonly['phaseChecklists'])=={'inspect','verify'}
for mid,terms in {'ultragui':['stable item IDs','rarity','safe-area'],'ultramodelling':['stud pitch','white','collision'],'ultraworld':['roof thickness','stair','camera'],'ultravfx':['static images','cleanup','authority'],'ultraanimation':['support','interruption','marker'],'ultraperformance':['p50/p95','device','1000']}.items():
    text=' '.join(sum(book['manuals'][mid]['phases'].values(),[])).lower()
    for term in terms:assert term.lower() in text,(mid,term)
print('PASS original 249 skill definitions, all 480 checkpoints/routes/exits/acceptance/diagnostics and nine styles preserved; 84 direct additions, 25 traceable reference studies, all actual skill reads include bounded expanded guidance, original workflow prefixes and read-only scope retained. Maximum default guide:',maximum)
