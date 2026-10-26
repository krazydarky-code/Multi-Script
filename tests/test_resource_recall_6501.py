"""Real catalogue/recipe reads, scoped recent memory and PDF page rendering."""
from pathlib import Path
import json,os,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'))
import omni_gui as o,obsidian_vault as v
class Recall(unittest.TestCase):
 def test_inventory_and_relevant_context(self):
  inventory=json.loads(o.call({'action':'packages'})['text'])
  self.assertEqual(inventory['references'],522);self.assertEqual(len(inventory['modules']),6);self.assertEqual(len(inventory['packages']),5)
  for kind in ('ui','vfx','pose','composite'):
   self.assertTrue(json.loads(o.call({'action':'recipe','recipe':kind})['text'])['text'])
  data=o.task_context({'query':'Create a cartoon inventory shop'})
  self.assertTrue(data['references']);self.assertTrue(data['recipe']['excerpt']);self.assertLess(len(json.dumps(data)),16000)
  with self.assertRaises(ValueError):o.call({'action':'preview','id':'nonexistent'})
 def test_scoped_recent_and_external_root_notes(self):
  with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'MS_STUDIO_DATA_DIR':temp+'/data','MS_OBSIDIAN_VAULT':temp+'/vault'}):
   v.setup();one=v.remember({'project':'my_game','title':'Inventory architecture','text':'Use authoritative inventory ownership and existing MenuRoot.'})
   v.remember({'project':'other_game','title':'Private','text':'neverleakthisproject'})
   root=v._root();(root/'New shared memory.md').write_text('sharedrootcanary inventory convention',encoding='utf-8')
   recall=v.context({'project':'my_game','query':'Please make the inventory with my existing architecture'})
   self.assertEqual(recall['recent'][0]['path'],one['path']);self.assertNotIn('neverleakthisproject',json.dumps(recall));self.assertTrue(recall['results'][0]['path'].startswith('Projects/my_game/'))
   found=v.search({'query':'sharedrootcanary','refresh':True});self.assertEqual(found['results'][0]['path'],'New shared memory.md')
   # A new keyword is not required to recover a recent saved decision.
   self.assertTrue(v.context({'project':'my_game'})['recent'])
 def test_real_pdf_page_and_bounds(self):
  from PIL import Image
  import base64,io
  with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'MS_STUDIO_DATA_DIR':temp+'/data','MS_OBSIDIAN_VAULT':temp+'/vault'}):
   v.setup();path=v._root()/'Notes/reference.pdf';Image.new('RGB',(80,100),'red').save(path,'PDF')
   result=v.read({'path':'Notes/reference.pdf','page':1});metadata=json.loads(result['text']);self.assertEqual(metadata['page'],1)
   with Image.open(io.BytesIO(base64.b64decode(result['images'][0]['data']))) as picture:self.assertGreater(picture.width,0)
   for page in (0,2001,True):
    with self.assertRaises(ValueError):v.read({'path':'Notes/reference.pdf','page':page})
   with self.assertRaises(ValueError):v.read({'path':'Notes/reference.pdf','page':2})
if __name__=='__main__':unittest.main()
