import importlib.util,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('publisher',ROOT/'tools/publish_github.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
cfg={'feedUrl':'https://github.com/krazydarky-code/Multi-Script/releases/latest/download/dev-update.json','publicKey':{'n':'test'}}
m.validate_repository('krazydarky-code/Multi-Script',cfg)
for repo in ['other/repo','../bad','https://github.com/krazydarky-code/Multi-Script']:
 try:m.validate_repository(repo,cfg)
 except ValueError:pass
 else:raise AssertionError('Wrong publisher repository accepted')
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)/'artifact.zip';p.write_bytes(b'actual artifact')
 item={'name':p.name,'state':'uploaded','size':p.stat().st_size,'digest':'sha256:'+m.hashlib.sha256(p.read_bytes()).hexdigest()}
 m.verify_assets({'assets':[item]},[p])
 for broken in [{**item,'size':0},{**item,'digest':'sha256:wrong'},{**item,'state':'new'}]:
  try:m.verify_assets({'assets':[broken]},[p])
  except ValueError:pass
  else:raise AssertionError('Incomplete/mismatched upload accepted')
workflow=(ROOT/'.github/workflows/release.yml').read_text()
assert 'pull_request_target' not in workflow
assert "workflow_run.event == 'push'" in workflow and "head_repository.full_name == github.repository" in workflow
assert '--require-ci' in workflow and 'MS_UPDATE_SIGNING_KEY' in workflow and 'always()' in workflow
assert 'contents: write' in workflow and 'refs/heads/main' in workflow
print('PASS pinned repository, uploaded size/hash/state validation, CI/main-only publishing, fork-event exclusion, scoped permissions and private-key cleanup contract.')
