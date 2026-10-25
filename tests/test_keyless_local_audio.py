import importlib.util,tempfile,wave,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sp=importlib.util.spec_from_file_location('audio',ROOT/'runtime'/'elevenlabs_audio.py');a=importlib.util.module_from_spec(sp);sp.loader.exec_module(a)
a.OUTPUT_DIR=Path(tempfile.mkdtemp())
st=a.status();assert st['configured'] and st['noApiKeyRequired'] and st['defaultProvider']=='local' and not st['providers']['local']['apiKey']
classes={'click':'UI button click','impact':'heavy punch impact','explosion':'large explosion blast','laser':'magic laser','whoosh':'fast dash whoosh','footstep':'stone footstep','coin':'coin reward pickup','alarm':'warning alarm','rain':'rain ambience','wind':'wind ambience','engine':'engine motor hum'}
for kind,prompt in classes.items():
 m=a.generate_sound_effect(prompt,kind,duration_seconds=.08,provider='local',seed=42)
 assert m['provider']=='Multi-Script Local Audio' and m['soundClass']==kind and not m['apiKeyUsed'] and not m['networkUsed']
 with wave.open(m['created'],'rb') as w: assert w.getnchannels()==1 and w.getsampwidth()==2 and w.getframerate()==44100 and w.getnframes()>100
same1=a.generate_sound_effect('UI click','repeat-a',duration_seconds=.08,provider='local',seed=9)
same2=a.generate_sound_effect('UI click','repeat-b',duration_seconds=.08,provider='local',seed=9)
with open(same1['created'],'rb') as x,open(same2['created'],'rb') as y: assert x.read()==y.read()
try:a.generate_sound_effect('x','x',provider='unknown');raise AssertionError('bad provider accepted')
except RuntimeError:pass
print('PASS free keyless local audio: 11 sound classes, deterministic WAV, no network or API key')
