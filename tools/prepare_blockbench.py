"""Prepare the same pinned optional runtime used by the product, for native QA."""
from pathlib import Path
import json,os,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
import blockbench_workspace as b
if '--ci-shard' in sys.argv:
 shard=int(sys.argv[sys.argv.index('--ci-shard')+1]);names=json.loads((Path(__file__).resolve().parents[1]/'tools/ci-suites.json').read_text())
 if not {'test_blockbench_native_650.py','test_asset_vault_wire_650.py'} & {name for index,name in enumerate(names) if index%4==shard}:
  print('This shard has no native Blockbench suites.');raise SystemExit(0)
print(json.dumps(b.prepare(render='--render' in sys.argv)))
if os.environ.get('GITHUB_ENV'):
 with open(os.environ['GITHUB_ENV'],'a',encoding='utf-8') as out:out.write('MS_BLOCKBENCH_CACHE='+str(b.cache_root())+'\n')
