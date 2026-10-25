import sys,tempfile,unittest,json
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'))
import studio_hub as h

class Evidence(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.patch=mock.patch.object(h,'DATA_DIR',Path(self.tmp.name));self.patch.start()
 def tearDown(self):self.patch.stop();self.tmp.cleanup()
 def call(self,action,**kwargs):return h.cowork({'action':action,**kwargs})
 def task(self,**kwargs):return self.call('create',title='Inventory',checks=['Keyboard navigation works','Phone layout has no clipping'],**kwargs)['task']
 def test_completion_requires_checks_evidence_and_no_blocker(self):
  t=self.task();sid=t['id'];self.call('claim',id=sid,owner='worker-a')
  for data in [{},{'note':'Rendered'},{'verified_checks':[0,1]},{'note':'Rendered','verified_checks':[0,1],'blocker':'Native playtest unavailable'}]:
   with self.assertRaisesRegex(ValueError,'Completion requires'):self.call('complete',id=sid,owner='worker-a',**data)
  self.assertEqual(self.call('list')['tasks'][0]['status'],'working')
  self.call('update',id=sid,owner='worker-a',note='Phone screenshot captured',verified_checks=[1],blocker='Keyboard check pending')
  with self.assertRaises(ValueError):self.call('complete',id=sid,owner='worker-a',verified_checks=[0,1])
  done=self.call('complete',id=sid,owner='worker-a',verified_checks=[0,1],blocker='',note='Phone capture and keyboard traversal checked')['task'];self.assertEqual(done['status'],'done')
  events=self.call('history',id=sid)['events'];self.assertIn('Verified acceptance indices: [0, 1]',events[0]['note'])
  reopened=self.call('reopen',id=sid)['task'];self.assertEqual(reopened['verified_checks'],[]);self.assertEqual(reopened['blocker'],'')
 def test_validation_scope_changes_and_permissions(self):
  for checks in [['x']*13,[''],[1],['x'*301]]:
   with self.assertRaises(ValueError):self.call('create',title='Bad',checks=checks)
  t=self.task();sid=t['id'];self.call('claim',id=sid,owner='worker-a')
  for checks in [[True],[-1],[2],['0']]:
   with self.assertRaises(ValueError):self.call('update',id=sid,owner='worker-a',verified_checks=checks)
  with self.assertRaises(ValueError):self.call('update',id=sid,owner='worker-b',verified_checks=[0,1])
  self.call('update',id=sid,owner='worker-a',verified_checks=[0],note='First check passed')
  self.call('release',id=sid,owner='worker-a')
  edited=self.call('edit',id=sid,checks=['New acceptance condition'])['task'];self.assertEqual(edited['verified_checks'],[])
 def test_reopened_dependency_prevents_completion(self):
  a=self.call('create',title='Core')['task'];self.call('claim',id=a['id'],owner='worker-a');self.call('complete',id=a['id'],owner='worker-a',note='Core checks passed')
  b=self.task(depends_on=[a['id']]);self.call('claim',id=b['id'],owner='worker-b');self.call('reopen',id=a['id'])
  with self.assertRaisesRegex(ValueError,'reopened dependency'):self.call('complete',id=b['id'],owner='worker-b',note='UI checked',verified_checks=[0,1])
 def test_schema_exposes_proof_fields(self):
  fields=next(t for t in h.TOOLS if t['name']=='ms_cowork')['inputSchema']['properties'];self.assertTrue(all(k in fields for k in ['checks','verified_checks','blocker']))

if __name__=='__main__':unittest.main(verbosity=2)
