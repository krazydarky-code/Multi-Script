"""Test-only persistent phone service controlled over parent-owned stdin/stdout."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from mobile_remote import Remote
r=Remote(port=0)
try:
    for line in sys.stdin:
        item=json.loads(line)
        try:
            result=r.admin(item['op'],item.get('payload'),owner='fixture-browser')
            if 'addresses' in result:result['addresses']=['127.0.0.1']
            print(json.dumps({'id':item['id'],'result':result}),flush=True)
        except Exception as e:print(json.dumps({'id':item['id'],'result':{'ok':False,'error':str(e)}}),flush=True)
finally:r.close()
