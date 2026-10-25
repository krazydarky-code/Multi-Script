"""Run one bounded shard without dropping any required CI suite."""
from pathlib import Path
import argparse,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--shard',type=int,required=True);p.add_argument('--shards',type=int,default=4);a=p.parse_args()
assert 0<=a.shard<a.shards and a.shards>0
names=json.loads((ROOT/'tools/ci-suites.json').read_text())
assert len(names)==len(set(names)) and all((ROOT/'tests'/n).is_file() for n in names)
selected=[n for i,n in enumerate(names) if i%a.shards==a.shard];assert selected
raise SystemExit(subprocess.call([sys.executable,'-X','utf8','tools/verify.py','all',*selected,'--output','test-results/ci'],cwd=ROOT))
