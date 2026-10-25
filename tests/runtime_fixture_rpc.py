"""Test transport: execute real local built-ins without launching native editors."""
import importlib.util,json,sys,types
from pathlib import Path
root=Path(__file__).resolve().parents[1]
w=types.ModuleType('websockets');w.ConnectionClosed=Exception;sys.modules.setdefault('websockets',w)
spec=importlib.util.spec_from_file_location('fixture_bridge',root/'runtime/bridge.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
class Manager:
    def health(self): return []
data=json.load(sys.stdin)
if data.get('action')=='catalog':
    tables=[v for k,v in vars(b).items() if isinstance(v,list) and any(isinstance(t,dict) and t.get('name')=='ms_get_skill' for t in v)]
    if not tables:raise RuntimeError('Real built-in catalog not found')
    retired=getattr(b,'RETIRED_FROM_CATALOGUE',{})
    print(json.dumps([dict(t,server='zeroscript') for t in max(tables,key=len) if t.get('name') not in retired]))
else:
    result=b._builtin_call(data['name'],data.get('arguments',{}),Manager())
    if result is None:raise RuntimeError('Unknown real local tool')
    print(json.dumps(result))
