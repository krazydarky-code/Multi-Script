import importlib.util,json,re,sys,types,tempfile,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
w=types.ModuleType('websockets');w.ConnectionClosed=Exception;sys.modules.setdefault('websockets',w)
spec=importlib.util.spec_from_file_location('audit_bridge',ROOT/'runtime'/'bridge.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
skills=json.load(open(ROOT/'runtime'/'skills.json',encoding='utf-8'))
packs=json.load(open(ROOT/'runtime'/'skill-packs.json',encoding='utf-8'))
assert len(skills)==249 and packs['totalSkills']==249
assert len(set(skills))==249
cap=json.load(open(ROOT/'runtime'/'capability-index.json'))
assert cap['totalSkills']==249 and cap['policy']['minimumStackSize']>=3
for sid,v in skills.items():
 assert v.get('capabilityDomain') and v.get('capabilityRole'),sid
 assert len(v.get('relatedSkills') or [])>=4,sid
 assert all(x in skills and x!=sid for x in v['relatedSkills']),sid
allowed={None,'roblox','unity','godot','blender','figma','general'}
for sid,v in skills.items():
 assert re.fullmatch(r'[a-z0-9][a-z0-9-]*',sid),sid
 assert isinstance(v,dict) and str(v.get('name','')).strip(),sid
 assert str(v.get('description','')).strip(),sid
 steps=v.get('steps');assert isinstance(steps,list) and steps and all(isinstance(x,str) and x.strip() for x in steps),sid
 assert v.get('engine') in allowed,(sid,v.get('engine'))
 if 'tags' in v: assert isinstance(v['tags'],list) and all(isinstance(x,str) and x.strip() for x in v['tags']),sid
 if 'qualityGates' in v: assert isinstance(v['qualityGates'],list) and all(isinstance(x,str) and x.strip() for x in v['qualityGates']),sid
# Every pack reference must exist, have the advertised count, and match its engine.
refs=[]
for eng,pack in packs['packs'].items():
 ids=pack['skillIds'];assert len(ids)==pack['count']==len(set(ids)),eng
 for sid in ids: assert sid in skills and skills[sid].get('engine')==eng,(eng,sid)
 refs+=ids
for key,pack in packs.items():
 if isinstance(pack,dict) and 'skills' in pack:
  ids=pack['skills'];assert len(ids)==len(set(ids)),key
  if 'count' in pack: assert pack['count']==len(ids),key
  for sid in ids: assert sid in skills,(key,sid)
  refs+=ids
assert len(refs)==len(set(refs)), 'skill referenced by multiple packs'
class M:
 def health(self): return [{'id':'unity','alive':True,'tools':2},{'id':'figma','alive':True,'tools':1}]
 def list_resources(self,server,cursor=None): return {'server':server,'resources':[{'uri':'test://resource'}],'cursor':cursor}
 def read_resource(self,server,uri): return {'text':f'{server}:{uri}','images':[]}
 def call_on_server(self,server,tool,args,timeout): return {'text':json.dumps({'server':server,'tool':tool,'args':args}),'images':[]}
m=M()
def call(name,args):
 out=b._builtin_call(name,args,m); assert isinstance(out,dict) and isinstance(out.get('text'),str) and isinstance(out.get('images'),list),name; return out
# Retrieve and parse every skill through the public built-in.
for sid,v in skills.items():
 got=json.loads(call('ms_get_skill',{'skill_id':sid})['text']);assert got['id']==sid and got['name']==v['name']
# List every engine and query every skill id.
for eng in ['roblox','unity','godot','blender','figma','general']:
 expected=sum(v.get('engine')==eng for v in skills.values());got=json.loads(call('ms_list_skills',{'engine':eng,'limit':100})['text']);assert got['totalMatches']==expected,(eng,expected,got['totalMatches'])
for sid in skills:
 got=json.loads(call('ms_list_skills',{'query':sid,'limit':100})['text']);assert got['totalMatches']>=1,sid
# Exercise recommendation logic for every skill without requiring a particular rank for intentional overlaps.
for sid,v in skills.items():
 got=json.loads(call('ms_recommend_skills',{'objective':v['name'],'engine':v.get('engine') or '', 'limit':10})['text']);assert isinstance(got['recommendations'],list),sid
# Exercise all 20 built-ins and every enum-heavy branch.
expected_tools=json.load(open(ROOT/'runtime'/'product-manifest.json',encoding='utf-8'))['catalogue']['directTools']
assert len(b.BUILTIN_TOOLS)==expected_tools and len(b.BUILTIN_TOOL_NAMES)==expected_tools
class FakeAudio:
 def status(self): return {'provider':'ElevenLabs','configured':True}
 def list_generated_audio(self,limit): return {'count':0,'assets':[]}
 def generate_sound_effect(self,**kwargs): return {'created':'/tmp/fake.mp3','provider':'ElevenLabs'}
b._AUDIO_MODULE=FakeAudio()
assert json.loads(call('ms_elevenlabs_status',{})['text'])['configured']
call('ms_generate_sound_effect',{'text':'short UI click','name':'click','target_engine':'roblox'})
call('ms_list_generated_audio',{'limit':5})
call('ms_bridge_status',{});call('ms_list_resources',{'server':'unity'});call('ms_read_resource',{'server':'unity','uri':'test://resource'})
call('ms_critic_review',{'objective':'ship','changed_assets':['scene'],'checks':['build'],'evidence':['Build completed with zero errors'],'known_issues':[],'round':2})
call('ms_workflow_plan',{'objective':'ship','domains':['ui-ux','animation','vfx','model','gameplay','build'],'targets':['blender','unity']})
call('ms_parallel_tools',{'calls':[{'server':'unity','tool':'compile','arguments':{}},{'server':'figma','tool':'inspect','arguments':{}}]})
call('ms_enhance_brief',{'request':'Make a polished studded shop UI and 3D prop','engine':'roblox','quality':'ambitious','constraints':['mobile']})
call('ms_quality_scorecard',{'objective':'ship','scores':{x:8 for x in ['clarity','cohesion','originality','usability','responsiveness','accessibility','technicalQuality','performance','evidence']},'evidence':['verified build output']})
for d in ['ui-ux','animation','vfx','model','gameplay','build']: call('ms_quality_checklist',{'domain':d,'target':'test'})
call('ms_test_matrix',{'feature':'shop','platforms':['desktop','mobile']})
call('ms_asset_budget',{'target':'mobile scene','platform':'mobile'})
call('ms_release_checklist',{'engine':'unity','platform':'windows'})
call('ms_risk_register',{'objective':'release','systems':['save','network']})
for target in ['roblox','unity','godot','unreal','other']: call('ms_engine_handoff',{'source':'blender','target':target,'asset_type':'prop','format':'fbx'})
for pattern in ['studs','brick','checker','grid','dots','stripes','hex','noise']:
 out=call('ms_create_canvas_texture',{'name':'../audit texture','pattern':pattern,'width':64,'height':64,'tile_size':8,'seed':7});data=json.loads(out['text']);assert Path(data['created']).suffix=='.svg' and Path(data['created']).is_file() and '..' not in Path(data['created']).name
for theme in ['dark','light','game','glass']:
 out=call('ms_create_canvas_ui',{'name':'audit ui','width':320,'height':320,'theme':theme,'components':[{'type':t,'label':t,'x':4,'y':4,'width':100,'height':30} for t in ['frame','text','button','card','input','image','badge']]});info=json.loads(out['text']);assert Path(info['created']).is_file();assert info['artifactKind']=='local-svg-mockup' and info['nativeUiCreated'] is False and info['engineImported'] is False
call('ms_figma_handoff',{'objective':'shop','platform':'desktop','screens':['shop','confirm'],'style':'game'})
call('ms_prompt_rescue',{'prompt':'make game cool','engine':'roblox','constraints':['mobile']})
call('ms_game_blueprint',{'concept':'co-op survival','engine':'unity','platforms':['pc'],'multiplayer':True})
call('ms_vertical_slice_plan',{'objective':'first playable','engine':'godot','deadline':'two weeks'})
call('ms_system_design_review',{'system':'inventory','engine':'roblox','design':'server authority','dependencies':['save']})
call('ms_gameplay_balance_plan',{'system':'economy','goals':['fair'],'player_segments':['new','expert']})
call('ms_multiplayer_authority_audit',{'engine':'unity','feature':'combat','messages':['attack']})
call('ms_save_migration_plan',{'engine':'godot','current_version':'1','target_version':'2','changes':['add inventory']})
call('ms_performance_budget_plan',{'engine':'roblox','platforms':['mobile'],'scene':'hub'})
call('ms_accessibility_audit',{'feature':'shop','platforms':['mobile'],'evidence':['focus path tested']})
call('ms_content_pipeline_plan',{'engine':'unity','content_types':['models','animation'],'source_tools':['blender']})
call('ms_playtest_protocol',{'objective':'validate tutorial','build':'dev-1','participants':5,'platforms':['pc']})
call('ms_definition_of_done',{'feature':'combat','engine':'godot','risk':'high'})
stack=json.loads(call('ms_orchestrate_request',{'request':'professional animated boss with textured armor, VFX and audio','engine':'roblox','max_skills':6})['text']);assert len(stack['skillStack'])>=3 and stack['executionRequired']
ids=[x['id'] for x in stack['skillStack'][:4]]
active=json.loads(call('ms_activate_skill_stack',{'request':'build boss','engine':'roblox','skill_ids':ids})['text']);assert active['executionRequired'] and not active['planOnly'] and len(active['stages'])>=2
call('ms_animation_director',{'engine':'unity','subject':'boss','style':'weighty','actions':['idle','attack']})
call('ms_texture_art_pipeline',{'engine':'godot','asset':'stone temple','style':'stylized','platforms':['mobile']})
call('ms_art_direction',{'engine':'roblox','concept':'neon dungeon','mood':'mysterious','references':['arcade']})
call('ms_uiux_production',{'engine':'unity','feature':'inventory','platforms':['pc','mobile'],'style':'clean'})
call('ms_vfx_production',{'engine':'godot','effect':'magic impact','platforms':['web'],'style':'readable'})
call('ms_audio_production',{'engine':'roblox','feature':'combat','style':'punchy','platforms':['mobile']})

for tool_name in sorted(b.ADVANCED_DIRECT_CONTRACTS):
 data=json.loads(call(tool_name,{'engine':'unity','feature':'production feature','platforms':['pc','mobile'],'constraints':['60 fps'],'context':'existing project'})['text'])
 assert data['tool']==tool_name and data['realImplementationRequired'] and len(data['stages'])>=8 and len(data['qualityGates'])>=8,tool_name
virtual=json.load(open(ROOT/'runtime'/'virtual-tools.json'))['tools'];assert len(virtual)==263
for tid,v in virtual.items():
 detail=json.loads(call('ms_virtual_tool_details',{'tool_id':tid})['text']);assert detail['id']==tid
 run=json.loads(call('ms_run_virtual_tool',{'tool_id':tid,'request':'create a professional result','project_context':'test'})['text']);assert run['silentAugmentation'] and run['outputContract']['realArtifactRequired'] and len(run['stages'])>=8
for eng in ['roblox','unity','godot','blender']:
 listing=json.loads(call('ms_list_virtual_tools',{'engine':eng,'limit':50})['text']);assert listing['totalMatches']=={'roblox':90,'unity':70,'godot':70,'blender':33}[eng] and listing['count']==min(50,listing['totalMatches'])

# Expected validation failures.
for name,args in [('ms_get_skill',{'skill_id':'missing'}),('ms_parallel_tools',{'calls':[]}),('ms_parallel_tools',{'calls':[{'server':'x','tool':'a'},{'server':'x','tool':'b'}]}),('ms_quality_checklist',{'domain':'bad'})]:
 try:b._builtin_call(name,args,m);raise AssertionError('expected failure '+name)
 except RuntimeError:pass
# Retain generated fixture artifacts; never delete unrelated files in the shared output folder.

print(f'PASS exhaustive skill/tool audit: {len(skills)} skills retrieved, queried, recommended; {len(b.BUILTIN_TOOLS)} tools and all branch enums exercised')
