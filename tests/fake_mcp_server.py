import json,sys
for line in sys.stdin:
    try: m=json.loads(line)
    except Exception: continue
    if 'id' not in m: continue
    method=m.get('method'); rid=m['id']
    if method=='initialize': result={'protocolVersion':'2024-11-05','capabilities':{'tools':{},'resources':{}},'serverInfo':{'name':'fake','version':'1'}}
    elif method=='tools/list': result={'tools':[{'name':'ping','description':'ping','inputSchema':{'type':'object','properties':{}}}]}
    elif method=='tools/call': result={'content':[{'type':'text','text':'pong'}]}
    elif method=='resources/list': result={'resources':[{'uri':'mcpforunity://instances','name':'instances','mimeType':'application/json'}]}
    elif method=='resources/read': result={'contents':[{'uri':m.get('params',{}).get('uri'),'mimeType':'application/json','text':'{"success":true,"instance_count":1,"instances":[{"id":"Demo@abc"}]}'}]}
    else:
        print(json.dumps({'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'missing'}}),flush=True); continue
    print(json.dumps({'jsonrpc':'2.0','id':rid,'result':result}),flush=True)
