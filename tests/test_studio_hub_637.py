"""Behavior checks for the real persistence, lease, recording and edition paths."""
import concurrent.futures,io,json,os,struct,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
import studio_hub as hub
import edition,software_workspace as ws

class HubTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.data=mock.patch.object(hub,'DATA_DIR',Path(self.tmp.name));self.data.start()
        self.conn=mock.patch.object(hub,'CONNECTION',Path(self.tmp.name)/'.connection.json');self.conn.start()
        self.skill={'id':'test-skill','name':'Practical test skill','engine':'general','instructions':'Read the actual project, implement the requested change, run tests and read back the finished artifact.','description':'Workflow test'}
    def tearDown(self):self.conn.stop();self.data.stop();self.tmp.cleanup()
    def test_publish_review_install_persist_and_ownership(self):
        hub.workshop_local({'action':'publish','skill':self.skill,'client':'author-a'})
        with self.assertRaises(ValueError):hub.workshop_local({'action':'publish','skill':self.skill,'client':'author-b'})
        hub.workshop_local({'action':'review','id':'test-skill','client':'voter-a','star':True,'rating':5,'feedback':'Useful <script>text</script>'})
        hub.workshop_local({'action':'review','id':'test-skill','client':'voter-a','star':True,'rating':3})
        row=hub.workshop_local({'action':'list'})['items'][0]
        self.assertEqual((row['stars'],row['ratings'],row['rating']),(1,1,3))
        hub.workshop({'action':'install','skill':self.skill,'client':'author-a'})
        self.assertEqual(hub.installed_skills()['test-skill']['instructions'],self.skill['instructions'])
        hub.workshop({'action':'uninstall','id':'test-skill','client':'author-a'});self.assertFalse(hub.installed_skills())
    def test_rate_size_capacity_and_server_identity(self):
        for i in range(20):hub.workshop_local({'action':'publish','skill':{**self.skill,'id':f'skill-{i}'},'client':'author-a'})
        with self.assertRaises(ValueError):hub.workshop_local({'action':'publish','skill':{**self.skill,'id':'skill-over'},'client':'author-a'})
        with self.assertRaises(ValueError):hub.validate_skill({**self.skill,'instructions':'x'*16001})
        with self.assertRaises(ValueError):hub.workshop_local({'action':'install','skill':self.skill,'client':'fake-id'},identity='server-user')
    def test_concurrent_claim_has_one_winner_and_requires_owner(self):
        task=hub.cowork({'action':'create','title':'Build UI','detail':'Own ShopGui only; test mobile.'})['task']
        def claim(owner):
            try:return hub.cowork({'action':'claim','id':task['id'],'owner':owner})['ok']
            except ValueError:return False
        with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(claim,['worker-a','worker-b']))
        self.assertEqual(sum(results),1)
        row=hub.cowork({'action':'list'})['tasks'][0];self.assertTrue(row['active'])
        with self.assertRaises(ValueError):hub.cowork({'action':'complete','id':row['id'],'owner':'intruder'})
        hub.cowork({'action':'update','id':row['id'],'owner':row['owner'],'note':'Mobile capture verified'})
        hub.cowork({'action':'complete','id':row['id'],'owner':row['owner']})
        self.assertEqual(hub.cowork({'action':'list'})['tasks'][0]['status'],'done')
    def test_lease_expiration_and_release(self):
        task=hub.cowork({'action':'create','title':'Test'})['task'];sid=task['id']
        hub.cowork({'action':'claim','id':sid,'owner':'worker-a'})
        with mock.patch.object(hub.time,'time',return_value=task['updated']+1900):
            hub.cowork({'action':'claim','id':sid,'owner':'worker-b'})
            hub.cowork({'action':'release','id':sid,'owner':'worker-b'})
        self.assertEqual(hub.cowork({'action':'list'})['tasks'][0]['status'],'open')
    def test_recording_is_real_bounded_avi_with_frames(self):
        from PIL import Image
        n=[0]
        def grab():n[0]+=1;return Image.new('RGB',(160,90),(n[0]*30,50,90))
        out=hub.screen_record({'seconds':.5,'fps':4},grab=grab);meta=json.loads(out['text']);raw=Path(meta['path']).read_bytes()
        self.assertEqual(raw[:4],b'RIFF');self.assertEqual(raw[8:12],b'AVI ')
        self.assertEqual(struct.unpack('<I',raw[4:8])[0],len(raw)-8)
        self.assertIn(b'MJPG',raw);self.assertIn(b'idx1',raw);self.assertGreaterEqual(meta['frames'],2);self.assertLessEqual(meta['duration'],5)
        self.assertEqual(len(out['images']),1)
        with self.assertRaises(ValueError):hub.screen_record({'seconds':6},grab=grab)
    def test_reference_blocks_private_and_connection_hides_token(self):
        with self.assertRaises(ValueError):hub.fetch_reference({'url':'http://127.0.0.1/'})
        r=hub.connection({'url':'http://localhost:8766','token':'a'*32});self.assertNotIn('token',r)
        hub.connection({'url':'','token':''});self.assertFalse(hub.workshop({'action':'list'})['items'])
    def test_public_limits_and_dev_has_no_product_caps(self):
        public={'edition':'public','workspace':{'maxPayloadBytes':262144,'maxCommandSeconds':60,'background':False}}
        with mock.patch.object(edition,'policy',return_value=public):
            self.assertTrue(edition.check('ms_ws_run',{'background':True}));self.assertTrue(edition.check('ms_ws_run',{'timeout_s':61}))
            self.assertTrue(edition.check('ms_ws_write',{'content':'x'*262145}));self.assertIsNone(edition.check('ms_ws_run',{'timeout_s':30}))
            with mock.patch.object(ws.subprocess,'run') as run:
                run.return_value=mock.Mock(returncode=0,stdout='built',stderr='');ws._run('compile',Path(self.tmp.name),900);self.assertEqual(run.call_args.kwargs['timeout'],60)
        with mock.patch.object(edition,'policy',return_value={'edition':'dev','workspace':{}}):self.assertIsNone(edition.check('ms_ws_run',{'background':True,'timeout_s':1800}))
    def test_community_http_auth_identity_and_remote_client(self):
        import urllib.request,urllib.error,threading,workshop_server
        server=workshop_server.WorkshopServer(('127.0.0.1',0),workshop_server.Handler);server.users={'a'*32:'author-a','b'*32:'author-b'}
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{server.server_port}'
        try:
            req=urllib.request.Request(url+'/workshop',data=b'{"action":"list"}',headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(req)
            self.assertEqual(caught.exception.code,401)
            hub.connection({'url':url,'token':'a'*32});self.assertTrue(hub.workshop({'action':'publish','skill':self.skill,'client':'forged-user'})['ok'])
            hub.connection({'url':url,'token':'b'*32})
            with self.assertRaises(urllib.error.HTTPError):hub.workshop({'action':'publish','skill':self.skill,'client':'author-a'})
            rows=hub.workshop({'action':'list'})
            self.assertEqual(rows['scope'],'Community');self.assertEqual(rows['items'][0]['id'],'test-skill')
        finally:server.shutdown();server.server_close();thread.join(2)

if __name__=='__main__':unittest.main(verbosity=2)
