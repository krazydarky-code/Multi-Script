#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Multi-Script's native-node Figma companion MCP; stdlib only, no cloud token."""
import json,os,sys
from figma_link import Link,TOOLS
def main():
 link=Link()
 try:
  port=link.serve(int(os.environ.get('MS_FIGMA_PORT','17616')))
  print(f'Figma companion ready on 127.0.0.1:{port}. Pairing code (5 minutes, one use): {link.code}. Import figma-plugin/manifest.json in Figma, open it and enter this code. Never share the code.',file=sys.stderr,flush=True)
  for line in sys.stdin:
   try:
    request=json.loads(line);rid=request.get('id');method=request.get('method');params=request.get('params') or {}
    if rid is None:continue
    if method=='initialize':result={'protocolVersion':'2024-11-05','capabilities':{'tools':{}},'serverInfo':{'name':'Multi-Script Figma','version':'1.0.0'}}
    elif method=='ping':result={}
    elif method=='tools/list':result={'tools':TOOLS}
    elif method=='tools/call':
     try:
      data=link.call(params.get('name'),params.get('arguments') or {});content=[{'type':'text','text':json.dumps(data,ensure_ascii=False)}]
      if isinstance(data,dict) and data.get('format')=='PNG' and data.get('base64'):content=[{'type':'text','text':json.dumps({k:v for k,v in data.items() if k!='base64'})},{'type':'image','mimeType':'image/png','data':data['base64']}]
      result={'content':content,'isError':False}
     except Exception as e:result={'content':[{'type':'text','text':str(e)}],'isError':True}
    else:
     print(json.dumps({'jsonrpc':'2.0','id':rid,'error':{'code':-32601,'message':'Unknown method'}}),flush=True);continue
    print(json.dumps({'jsonrpc':'2.0','id':rid,'result':result}),flush=True)
   except (ValueError,TypeError) as e:print('Invalid Figma MCP request: '+str(e),file=sys.stderr,flush=True)
 finally:link.close()
if __name__=='__main__':main()
