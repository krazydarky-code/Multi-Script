import importlib.util,json,os,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("ela",ROOT/"runtime"/"elevenlabs_audio.py");a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
class Headers(dict):
 def get(self,k,d=None): return super().get(k,d)
class Response:
 def __init__(self): self.headers=Headers({"Content-Type":"audio/mpeg","character-cost":"17"})
 def read(self): return b"ID3\x04fake-audio-bytes"
 def __enter__(self): return self
 def __exit__(self,*x): pass
seen={}
def opener(req,timeout=0):
 seen["url"]=req.full_url;seen["headers"]={k.lower():v for k,v in req.header_items()};seen["body"]=json.loads(req.data);seen["timeout"]=timeout;return Response()
with tempfile.TemporaryDirectory() as td:
 a.OUTPUT_DIR=Path(td)/"audio";a.ENV_FILE=Path(td)/".env";os.environ["ELEVENLABS_API_KEY"]="test-secret-never-print"
 out=a.generate_sound_effect("Heavy stone door closes",name="door",duration_seconds=2.5,loop=False,prompt_influence=.6,opener=opener)
 assert Path(out["created"]).is_file() and Path(out["created"]).suffix==".mp3"
 assert "output_format=mp3_44100_128" in seen["url"] and seen["body"]["model_id"]=="eleven_text_to_sound_v2"
 assert seen["body"]["duration_seconds"]==2.5 and seen["body"]["prompt_influence"]==.6
 assert seen["headers"]["xi-api-key"]=="test-secret-never-print" and seen["timeout"]==120
 listed=a.list_generated_audio();assert listed["count"]==1 and listed["assets"][0]["sha256"]==out["sha256"]
 del os.environ["ELEVENLABS_API_KEY"]
 try:a.generate_sound_effect("x",opener=opener);raise AssertionError("missing key accepted")
 except RuntimeError as e: assert "configure_elevenlabs.py" in str(e)
print("PASS ElevenLabs secure status, authenticated request, audio save, metadata, listing and missing-key path")
