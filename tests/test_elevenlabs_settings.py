import importlib.util,tempfile
from pathlib import Path
r=Path(__file__).resolve().parents[1];sp=importlib.util.spec_from_file_location('a',r/'runtime/elevenlabs_audio.py');a=importlib.util.module_from_spec(sp);sp.loader.exec_module(a)
with tempfile.TemporaryDirectory() as d:
 a.ENV_FILE=Path(d)/'.env';st=a.configure_api_key('sk_test_user_specific_12345');assert st['configured'] and st['elevenLabsConfigured'] and 'sk_test' not in str(st);assert a.ENV_FILE.is_file();st=a.clear_api_key();assert st['configured'] and not st['elevenLabsConfigured']
print('PASS per-user ElevenLabs local key save, sanitized status and removal')
