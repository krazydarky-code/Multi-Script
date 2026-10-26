import json,sys,tempfile,sqlite3,concurrent.futures,unittest
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'))
import studio_hub as h,skill_workflows

class Revamp(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.patch=mock.patch.object(h,'DATA_DIR',Path(self.tmp.name));self.patch.start()
 def tearDown(self):self.patch.stop();self.tmp.cleanup()
 def create(self,title='Task',**kw):return h.cowork(dict(action='create',title=title,**kw))['task']
 def test_all_skills_have_real_delivery_contracts(self):
  skills=json.loads((ROOT/'runtime/skills.json').read_text(encoding='utf-8'));self.assertEqual(len(skills),249)
  for sid,skill in skills.items():
   flow=skill['executionWorkflow'];self.assertEqual(flow['revision'],'multi-script-restored-v6485' if sid in ['blender-texture-baking', 'blender-shape-keys', 'blender-geometry-nodes', 'blender-sculpt-retopology', 'blender-gltf-export', 'figma-prototyping', 'figma-developer-handoff', 'canvas-svg-ui'] else 'multi-script-workflows-v6');self.assertTrue(all(flow.get(k) for k in ['inspect','execute','verify','role','handoff','evidence','recovery']))
   if sid not in ['blender-texture-baking', 'blender-shape-keys', 'blender-geometry-nodes', 'blender-sculpt-retopology', 'blender-gltf-export', 'figma-prototyping', 'figma-developer-handoff', 'canvas-svg-ui', 'roblox-pro-animation', 'roblox-studio-gui-composition']:
    for field,value in skill_workflows.contract(sid,skill).items():
     if isinstance(value,str):self.assertTrue(flow[field].startswith(value),(sid,field,'Earlier workflow content must be retained before additive extensions'))
     else:self.assertEqual(flow[field],value)
  self.assertIn('without changing',skills['discover-project']['executionWorkflow']['execute']);self.assertTrue(skills['discover-project']['instructions'].startswith('READ-ONLY PROJECT DISCOVERY.'))
 def test_legacy_db_migrates_without_losing_tasks(self):
  c=sqlite3.connect(Path(self.tmp.name)/'studio.sqlite3');c.execute("CREATE TABLE tasks(id TEXT PRIMARY KEY,title TEXT NOT NULL,detail TEXT NOT NULL,status TEXT NOT NULL,owner TEXT DEFAULT '',lease REAL DEFAULT 0,note TEXT DEFAULT '',updated REAL NOT NULL)");c.execute("INSERT INTO tasks(id,title,detail,status,updated) VALUES('old','Keep me','details','open',1)");c.commit();c.close()
  task=h.cowork({'action':'list'})['tasks'][0];self.assertEqual(task['id'],'old');self.assertEqual(task['resources'],[]);self.assertEqual(task['project'],'default')
 def test_dependencies_resource_conflicts_and_progress(self):
  a=self.create('Core',resources=['Src/Core/'],priority='high');b=self.create('UI',resources=['src/ui'],depends_on=[a['id']]);overlap=self.create('Nested',resources=['src/core/state.lua'])
  with self.assertRaisesRegex(ValueError,'dependency'):h.cowork({'action':'claim','id':b['id'],'owner':'worker-b'})
  h.cowork({'action':'claim','id':a['id'],'owner':'worker-a'})
  with self.assertRaisesRegex(ValueError,'Resource conflict'):h.cowork({'action':'claim','id':overlap['id'],'owner':'worker-b'})
  h.cowork({'action':'update','id':a['id'],'owner':'worker-a','note':'Built and tested core'})
  h.cowork({'action':'complete','id':a['id'],'owner':'worker-a'});h.cowork({'action':'claim','id':b['id'],'owner':'worker-b'})
  events=h.cowork({'action':'history','id':a['id']})['events'];self.assertEqual([e['action'] for e in events],['complete','update','claim','create'])
  h.cowork({'action':'reopen','id':a['id']});self.assertTrue(next(t for t in h.cowork({'action':'list'})['tasks'] if t['id']==b['id'])['blockedBy'])
 def test_cycles_project_boundaries_and_concurrent_resources(self):
  a=self.create(resources=['src/ui']);b=self.create(depends_on=[a['id']]);
  with self.assertRaisesRegex(ValueError,'cycle'):h.cowork({'action':'edit','id':a['id'],'depends_on':[b['id']]})
  c=self.create(resources=['src/ui/button'],project='another')
  h.cowork({'action':'claim','id':a['id'],'owner':'worker-a'});h.cowork({'action':'claim','id':c['id'],'owner':'worker-b'})
  x=self.create(resources=['Workspace/Shop']);y=self.create(resources=['workspace/shop/counter'])
  def claim(t):
   try:h.cowork({'action':'claim','id':t['id'],'owner':'worker-'+t['id']});return True
   except ValueError:return False
  with concurrent.futures.ThreadPoolExecutor(2) as pool:self.assertEqual(sum(pool.map(claim,[x,y])),1)
 def test_validation_and_expired_ownership(self):
  for resources in [['../oops'],[''],['x'*201]]:
   with self.assertRaises(ValueError):self.create(resources=resources)
  with self.assertRaises(ValueError):self.create(depends_on=['missing'])
  task=self.create();h.cowork({'action':'claim','id':task['id'],'owner':'worker-a'})
  with mock.patch.object(h.time,'time',return_value=task['updated']+1900):
   with self.assertRaises(ValueError):h.cowork({'action':'update','id':task['id'],'owner':'worker-a'})
   h.cowork({'action':'claim','id':task['id'],'owner':'worker-b'})

if __name__=='__main__':unittest.main(verbosity=2)
