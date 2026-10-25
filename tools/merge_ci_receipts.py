"""Require every CI shard, exact catalogue coverage and zero failures/skips."""
from pathlib import Path
import json,subprocess
ROOT=Path(__file__).resolve().parents[1];names=json.loads((ROOT/'tools/ci-suites.json').read_text());rows=[]
for shard in range(4):
 part=json.loads((ROOT/f'test-results/shard-{shard}/results.json').read_text())
 assert {r['file'] for r in part}=={n for i,n in enumerate(names) if i%4==shard},f'Missing/extra shard {shard} coverage'
 assert len(part)==len({r['file'] for r in part}) and all(r['exitCode']==0 and not r['skipped'] for r in part)
 rows+=part
assert len(rows)==len(names) and {r['file'] for r in rows}==set(names)
out=ROOT/'test-results/ci';out.mkdir(parents=True,exist_ok=True)
(out/'results.json').write_text(json.dumps(sorted(rows,key=lambda r:r['file']),indent=2)+'\n',encoding='utf-8')
(out/'metadata.json').write_text(json.dumps({'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'requiredSuites':len(names),'shards':4},indent=2)+'\n',encoding='utf-8')
print(f'PASS all {len(names)} required suites across four shards, with no omissions, failures or environment skips')
