"""Real vault files, FTS recall, project isolation, media preservation and root setup."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import gzip,hashlib,io,json,os,shutil,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'))
import obsidian_vault as v
import update_manager as u

class VaultTests(unittest.TestCase):
 def test_seed_contains_every_current_skill_and_tool(self):
  data=json.loads(gzip.decompress((ROOT/'runtime/vault-library.json.gz').read_bytes()))
  self.assertEqual(data['skills'],json.loads((ROOT/'runtime/skills.json').read_text(encoding='utf-8')))
  import bridge
  self.assertEqual(data['tools'],bridge.BUILTIN_TOOLS);self.assertEqual(len(data['manuals']),84)
  self.assertEqual(len(json.loads(data['references']['OMNI/catalog.json'])['references']),522)
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='ms-vault-');self.root=Path(self.temp.name);self.app=self.root/'Multi-Script';self.runtime=self.app/'runtime';self.runtime.mkdir(parents=True)
  shutil.copyfile(ROOT/'runtime/vault-library.json.gz',self.runtime/'vault-library.json.gz')
  self.env=patch.dict(os.environ,{'MS_STUDIO_DATA_DIR':str(self.runtime/'studio-data')});self.env.start()
  self.override=os.environ.pop('MS_OBSIDIAN_VAULT',None)
  self.here=patch.object(v,'HERE',self.runtime);self.here.start();v._INDEX_AT.clear()
 def tearDown(self):
  self.here.stop()
  if self.override is not None:os.environ['MS_OBSIDIAN_VAULT']=self.override
  self.env.stop();self.temp.cleanup()
 def test_each_install_root_setup_idempotence_and_edited_notes(self):
  self.assertFalse(v.status()['configured']);state=v.setup();vault=self.app/'Multi-Script Memory'
  self.assertEqual(state['vault'],str(vault.resolve()));self.assertTrue(state['available'])
  self.assertEqual(json.loads((vault/'.obsidian/app.json').read_text())['attachmentFolderPath'],'Attachments')
  library=next((vault/'Library').glob('Multi-Script-*'));self.assertEqual(len(list((library/'Skills').glob('*.md'))),249)
  self.assertEqual(len(list((library/'Ultra').glob('*.md'))),84)
  note=next((library/'Skills').glob('*.md'));note.write_text('archivedonlycanary650',encoding='utf-8')
  (vault/'.obsidian/app.json').write_text('{"user":"preferences"}')
  v.setup();self.assertEqual(note.read_text(),'archivedonlycanary650');self.assertEqual(json.loads((vault/'.obsidian/app.json').read_text()),{'user':'preferences'})
  bundle=self.runtime/'vault-library.json.gz';data=json.loads(gzip.decompress(bundle.read_bytes()));data['references']['new.md']='New useful reference'
  bundle.write_bytes(gzip.compress(json.dumps(data).encode(),mtime=0));v.setup()
  self.assertEqual(len(list((vault/'Library').glob('Multi-Script-*'))),2);self.assertEqual(note.read_text(),'archivedonlycanary650')
  self.assertFalse(v.search({'query':'archivedonlycanary650','library':True})['results'])
  self.assertTrue(v.search({'query':'archivedonlycanary650','library':True,'archives':True})['results'])
  self.assertFalse(v.search({'query':'archivedonlycanary650','library':True})['results'])
 def test_project_isolation_search_refresh_and_bounded_read(self):
  v.setup();a=v.remember({'project':'alpha_a','title':'Durable decision','text':'canaryseparate Prefer studs and incremental native execution.'})
  v.remember({'project':'alphaba','title':'Private other project','text':'canaryseparate otherprojectsecret'})
  found=v.search({'query':'canaryseparate','project':'alpha_a','library':False})['results']
  self.assertEqual(len(found),1);self.assertNotIn('otherprojectsecret',json.dumps(found))
  self.assertTrue(v.search({'query':'inventory','project':'alpha_a'})['results'])
  read=json.loads(v.read({'path':a['path'],'max_chars':500})['text']);self.assertIn('incremental',read['text']);self.assertIn('%20',read['uri'])
  note=Path(v.status()['vault'])/a['path'];note.write_text('changedrefreshcanary',encoding='utf-8')
  self.assertTrue(v.search({'query':'changedrefreshcanary','project':'alpha_a','refresh':True,'library':False})['results'])
  self.assertFalse(v.search({'query':'canaryseparate','project':'alpha_a','refresh':True,'library':False})['results'])
  for path in ('../outside','C:/private','/etc/passwd','Projects\\escape','.obsidian/app.json','Library/../../outside'):
   with self.assertRaises(ValueError):v.read({'path':path})
  with self.assertRaises(ValueError):v.search({'query':'x','limit':500})
 def test_large_import_dedupe_no_execution_and_image_recall(self):
  v.setup();source=self.root/'all-omni.zip';source.write_bytes(b'Not executable archive data\0'*100000)
  a=v.import_attachment(source);b=v.import_attachment(source)
  self.assertTrue(a['created']);self.assertFalse(b['created']);self.assertEqual(a['sha256'],hashlib.sha256(source.read_bytes()).hexdigest())
  self.assertEqual((Path(v.status()['vault'])/a['path']).read_bytes(),source.read_bytes())
  self.assertTrue(v.search({'query':'all-omni.zip'})['results'])
  metadata=json.loads(v.read({'path':a['path']})['text']);self.assertFalse(metadata['contentRead'])
  from PIL import Image
  image=self.root/'reference.png';Image.new('RGB',(24,24),(10,150,30)).save(image)
  imported=v.import_attachment(image);reply=v.read({'path':imported['path']});self.assertEqual(reply['images'][0]['mimeType'],'image/png')
  stored=Path(v.status()['vault'])/a['path'];stored.write_bytes(b'User edited original')
  with self.assertRaises(ValueError):v.import_attachment(source)
  self.assertEqual(stored.read_bytes(),b'User edited original')
 def test_concurrent_memory_dedup_and_private_package_boundary(self):
  v.setup();args={'project':'game','title':'Remember me','text':'one durable useful decision'}
  with ThreadPoolExecutor(max_workers=8) as pool:rows=list(pool.map(lambda _:v.remember(args),range(24)))
  self.assertEqual(sum(row['created'] for row in rows),1)
  path=Path(v.status()['vault'])/rows[0]['path'];path.write_text('User edited memory')
  new=v.remember(args);self.assertNotEqual(rows[0]['path'],new['path']);self.assertEqual(path.read_text(),'User edited memory')
  for name in ('Multi-Script Memory/Notes/a.md','multi-script memory/Attachments/original.zip','MULTI-SCRIPT MEMORY/library/index.md'):self.assertTrue(u.protected(name))
  with self.assertRaises(ValueError):v.setup(str(self.app))
  with self.assertRaises(ValueError):v.setup(str(self.runtime/'bad-vault'))
  self.assertNotIn('setup',v.TOOL['inputSchema']['properties']['action']['enum']);self.assertNotIn('import',v.TOOL['inputSchema']['properties']['action']['enum'])
 def test_unavailable_vault_does_not_silently_create_replacement(self):
  v.setup();vault=Path(v.status()['vault']);moved=self.root/'MovedVault';vault.rename(moved)
  self.assertFalse(v.status()['available'])
  with self.assertRaises(ValueError):v.remember({'title':'x','text':'y'})
  self.assertFalse(vault.exists());self.assertTrue(v.setup(str(moved))['available'])
 def test_invalid_configuration_and_snapshot_do_not_replace_notes(self):
  v.setup();vault=Path(v.status()['vault']);note=v.remember({'title':'Keep','text':'important original'})
  marker=next((vault/'Library').glob('*/snapshot.json'));marker.write_text('broken metadata')
  v.setup();self.assertTrue((vault/note['path']).is_file());self.assertEqual(len(list((vault/'Library').glob('Multi-Script-*'))),2)
  cfg=v.data_root()/'obsidian.json';cfg.write_text('[]')
  self.assertFalse(v.status()['ok'])
  with self.assertRaises(ValueError):v.setup()
  self.assertTrue(v.setup(str(vault))['available']);self.assertTrue((vault/note['path']).is_file())

if __name__=='__main__':unittest.main()
