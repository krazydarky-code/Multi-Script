import base64, concurrent.futures, json, os, pathlib, subprocess, sys, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'))
import forge_assets as forge

class ForgePreservation(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.original=forge.OUT;self.serve=forge._serve
        forge.OUT=pathlib.Path(self.temp.name);forge._serve=lambda:'http://127.0.0.1:12345/token'
        self.png=base64.b64encode(b'\x89PNG\r\n\x1a\nexample').decode()
    def tearDown(self):forge.OUT=self.original;forge._serve=self.serve;self.temp.cleanup()
    def save(self,name='set',**extra):return forge.act_save({'name':name,'files':{'button':self.png},'manifest':{'type':'ui_kit','elements':{'button':{}}},**extra})
    def test_existing_artwork_is_never_deleted_or_overwritten(self):
        self.save();before=(forge.OUT/'set/button.png').read_bytes()
        with self.assertRaises(ValueError):self.save()
        self.assertEqual((forge.OUT/'set/button.png').read_bytes(),before)
        self.assertEqual(len(json.loads(forge.act_list({})['text'])['sets']),1)
    def test_batches_validation_and_unknown_generation(self):
        with self.assertRaises(ValueError):self.save(part='more')
        self.save(part='first');self.save(part='last')
        with self.assertRaises(ValueError):self.save(part='more',files={'button':base64.b64encode(b'\x89PNG\r\n\x1a\ndifferent').decode()})
        with self.assertRaises(ValueError):self.save(name='other',files={'../../escape':self.png})
        self.assertFalse((forge.OUT/'other').exists())
    def test_competing_generations_do_not_overwrite(self):
        def run(_):
            try:self.save();return True
            except ValueError:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sum(pool.map(run,range(2))),1)
    def test_real_luau_compiles_generated_builders(self):
        executable=os.environ.get('LUAU_BIN')
        if not executable:self.skipTest('Set LUAU_BIN for native generated-builder compilation.')
        compiler=pathlib.Path(executable).with_name('luau-compile'+('.exe' if os.name=='nt' else ''))
        samples={'ui':forge.ui_luau({'theme':{'style':'cartoon'},'elements':{'panel':{'slice':[12,12,244,244]}}},{'panel':'rbxassetid://123'}),'vfx':forge.vfx_luau({'textures':{'spark':{'kind':'single'}},'presets':{}},{'spark':'rbxassetid://123'})}
        for name,source in samples.items():
            target=pathlib.Path(self.temp.name)/(name+'.luau');target.write_text(source,encoding='utf-8')
            result=subprocess.run([str(compiler),str(target),'--null'],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
