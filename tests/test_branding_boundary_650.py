import json,pathlib,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class BrandingBoundary(unittest.TestCase):
    def test_product_has_its_own_identity_and_retains_required_original_notices(self):
        legal=ROOT/'legal/upstream-gpl';source=json.loads((legal/'SOURCE.json').read_text(encoding='utf-8'));name=source['originName'].lower()
        for filename in ('LICENSE','NOTICE.md','1.24.20-LICENSE.txt','1.24.20-BRANDING-NOTICE.txt','ORIGINAL_NOTICES.md'):
            self.assertTrue((legal/filename).is_file(),filename)
        self.assertIn('Existing copyright, license and third-party attribution notices must remain intact.',(legal/'1.24.20-BRANDING-NOTICE.txt').read_text(encoding='utf-8'))
        for folder in ('extension','runtime','docs'):
            for path in (ROOT/folder).rglob('*'):
                if not path.is_file() or path.suffix not in ('.js','.json','.md','.py','.css','.html','.lua','.luau'):continue
                if set(path.parts)&{'generated','studio-data','__pycache__','node_modules'} or path.name=='update-files.json':continue
                self.assertNotIn(name,path.read_text(encoding='utf-8').lower(),str(path.relative_to(ROOT)))
if __name__=='__main__':unittest.main()
