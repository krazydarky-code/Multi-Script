import importlib.util,json,subprocess
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('delivery_publisher',ROOT/'tools/publish_github.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
for code in [401,403,429,500]:
 result=subprocess.CompletedProcess([],1,'',f'HTTP {code}: fixture refusal')
 with patch.object(m.subprocess,'run',return_value=result) as request:
  try:m.gh_call('gh',['api','repos/example/repo/releases/latest'],missing=True);raise AssertionError('API refusal treated as missing release')
  except RuntimeError:pass
  assert request.call_count==1,'No automatic request replay on refusals'
with patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','HTTP 404: Not Found')):
 assert m.gh_call('gh',['api','repos/example/repo/releases/latest'],missing=True) is None
m._last_mutation=None
with patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'{}','')),patch.object(m.time,'monotonic',side_effect=[10,10.2,10.3]),patch.object(m.time,'sleep') as sleeping:
 m.gh_call('gh',['release','create','fixture'],mutating=True);m.gh_call('gh',['release','upload','fixture','one.zip'],mutating=True)
 assert abs(sleeping.call_args.args[0]-.8)<.001
cfg=json.loads((ROOT/'runtime/update-channel.json').read_text());repo='krazydarky-code/Multi-Script';m.validate_repository(repo,cfg)
product=json.loads((ROOT/'runtime/product-manifest.json').read_text());assert product['updates']['repository']==repo and product['updates']['feed']==cfg['feedUrl']
release=(ROOT/'.github/workflows/release.yml').read_text();assert "vars.MS_AUTOPUBLISH == 'true'" in release and '--check-only' in release and "steps.plan.outputs.publish == 'true'" in release
names=json.loads((ROOT/'tools/ci-suites.json').read_text());assert len(names)==len(set(names)) and len(names)>=130 and all((ROOT/'tests'/name).is_file() for name in names)
for name in ['test_chatgpt_native_document_6499.js','test_chatgpt_native_roundtrip_6499.js','test_github_delivery_6499.py','test_update_host_cooldown_6499.py']:assert name in names
source=(ROOT/'tools/publish_github.py').read_text();assert 'for artifact in artifacts:' in source and 'Main moved during upload' in source and 'Main moved during the build' in source
print('PASS new-repository consistency, single-request fail-closed publishing, serial write pacing, read-only release planning and complete sharded CI catalogue.')
