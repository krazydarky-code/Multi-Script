"""Exercise the production dispatch path, not just the creative handlers."""
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
if importlib.util.find_spec('websockets') is None:
    stub = types.ModuleType('websockets')
    stub.ConnectionClosed = Exception
    sys.modules['websockets'] = stub
spec = importlib.util.spec_from_file_location('hotfix_bridge', ROOT / 'runtime/bridge.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class CreativeArgumentHotfix(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_here = b.HERE
        b.HERE = self.tmp.name
        self.manager = object.__new__(b.MCPManager)
        self.manager.disabled = {}

    def tearDown(self):
        b.HERE = self.old_here
        self.tmp.cleanup()

    def call(self, tool, args):
        return json.loads(self.manager._dispatch(tool, args, 10)['text'])

    def test_nameless_texture_all_patterns(self):
        for pattern in b.BUILTIN_TOOL_BY_NAME['ms_create_canvas_texture']['inputSchema']['properties']['pattern']['enum']:
            with self.subTest(pattern=pattern):
                result = self.call('ms_create_canvas_texture', {'pattern': pattern, 'width': 64, 'height': 64})
                self.assertTrue(Path(result['created']).is_file())
                self.assertIn('<svg', result['svg'])
                self.assertEqual(result['pattern'], pattern)

    def test_unnamed_files_are_unique(self):
        for tool, args in [('ms_create_canvas_texture', {'pattern': 'studs', 'width': 64, 'height': 64}), ('ms_create_canvas_ui', {})]:
            first, second = self.call(tool, args), self.call(tool, args)
            self.assertNotEqual(first['created'], second['created'])
            self.assertTrue(Path(first['created']).is_file())

    def test_existing_named_texture_and_seed_zero(self):
        result = self.call('ms_create_canvas_texture', {'name': 'my texture', 'pattern': 'noise', 'seed': 0, 'width': 64, 'height': 64})
        self.assertEqual(Path(result['created']).name, 'my-texture.svg')
        self.assertEqual(result['seed'], 0)

    def test_wrapped_and_coerced_nameless_texture(self):
        result = self.call('ms_create_canvas_texture', {'arguments': {'pattern': 'STUDS', 'width': '64', 'height': '64'}})
        self.assertEqual(result['pattern'], 'studs')
        self.assertEqual(result['size'], [64, 64])

    def test_essential_inputs_still_required(self):
        for tool in ['ms_create_canvas_texture', 'ms_generate_sound_effect']:
            with self.assertRaises(RuntimeError):
                self.call(tool, {})
        with self.assertRaises(RuntimeError):
            self.call('ms_create_canvas_texture', {'pattern': 'unsupported-material-xyz'})

    def test_nameless_ui_preserves_content(self):
        result = self.call('ms_create_canvas_ui', {'title': 'My shop', 'theme': 'game'})
        self.assertIn('My shop', result['svg'])
        self.assertEqual(result['theme'], 'game')

    def test_nameless_local_sound(self):
        # Load the module from the real runtime; only its output goes to temp.
        b.HERE = self.old_here
        audio = b._elevenlabs_audio()
        b.HERE = self.tmp.name
        old_dir = audio.OUTPUT_DIR
        audio.OUTPUT_DIR = Path(self.tmp.name) / 'audio'
        try:
            result = self.call('ms_generate_sound_effect', {'text': 'short UI click', 'provider': 'local', 'duration_seconds': 0.5})
            # The backend returns the actual generated WAV path.
            candidates = list(audio.OUTPUT_DIR.glob('*.wav'))
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].read_bytes()[:4], b'RIFF')
        finally:
            audio.OUTPUT_DIR = old_dir


if __name__ == '__main__':
    unittest.main()
