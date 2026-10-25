import importlib.util,json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
w=types.ModuleType('websockets'); w.ConnectionClosed=Exception; sys.modules.setdefault('websockets',w)
spec=importlib.util.spec_from_file_location('ms_bridge',ROOT/'runtime'/'bridge.py'); b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
class M: pass
out=json.loads(b._builtin_call('ms_enhance_brief',{'request':'make me a cool UI shop panel with a studded texture','engine':'roblox','quality':'polished'},M())['text'])
text=out['enhancedPrompt'].lower(); brief=out['brief']
for phrase in ['category navigation','purchase confirmation','seamless studded surface','beveled stud edges','responsive','required states']:
 assert phrase in text,phrase
assert brief['originalRequest']=='make me a cool UI shop panel with a studded texture'
score=json.loads(b._builtin_call('ms_quality_scorecard',{'objective':'polished shop','scores':{'clarity':9,'cohesion':8,'originality':5},'evidence':['phone and desktop screenshots']},M())['text'])
assert score['verdict']=='improve' and 'originality' in score['priorityImprovements']
print('PASS general quality enhancer example and scorecard')

classic=json.loads(b._builtin_call('ms_enhance_brief',{'request':'make me a good ui for this roblox game, classic','engine':'roblox','quality':'polished'},M())['text'])
assert classic['implementImmediately'] is True and classic['showBriefToUser'] is False
assert classic['brief']['augmentationMode']=='silent' and classic['brief']['preserveExplicitRequirements'] is True
text=classic['enhancedPrompt'].lower()
for phrase in ['roblox-inspired','crisp outlines','controller focus','phone, desktop']:
    assert phrase in text,phrase
assert 'generic glassmorphism' in text
print('PASS task-first classic Roblox UI silent quality boost')
