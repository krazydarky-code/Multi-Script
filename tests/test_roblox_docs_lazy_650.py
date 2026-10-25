import pathlib, sys, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'))
import roblox_docs as docs
class LazyDocs(unittest.TestCase):
    def test_api_and_lint_globals_do_not_load_all_guide_bodies(self):
        docs._S.clear()
        result=docs.api({'names':['TweenService:Create','Enum.EasingStyle.Quint']})
        self.assertTrue(all(row['found'] for row in result['results']))
        self.assertIn('game',docs.known_globals());self.assertFalse(docs._S['loaded_shards']);self.assertNotIn('fields',docs._S)
        result=docs.read({'title':'TweenService','max_chars':1000})
        self.assertIn('TweenService',result['text']);self.assertEqual(len(docs._S['loaded_shards']),1)
        self.assertNotIn('fields',docs._S)
        results=docs.search({'query':'UIListLayout','limit':3})['results'];self.assertTrue(results)
        self.assertIn('fields',docs._S)
        again=docs.read({'title':'TweenService','max_chars':1000});self.assertEqual(result['text'],again['text'])
if __name__=='__main__':unittest.main()
