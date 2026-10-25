import json,http.client,sys,threading,time,subprocess,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from figma_link import Link,TOOLS
def reject(fn,kind=ValueError):
 try:fn()
 except kind:return
 raise AssertionError('Expected rejection')
r=Link();port=r.serve(0)
def post(path,data,token='',origin='null',host=None):
 c=http.client.HTTPConnection('127.0.0.1',port,timeout=3);headers={'Origin':origin,'Content-Type':'application/json','Authorization':'Bearer '+token}
 if host:headers['Host']=host
 c.request('POST',path,json.dumps(data),headers);response=c.getresponse();body=json.loads(response.read());status=response.status;c.close();return status,body
try:
 assert not r.status()['connected'];reject(lambda:r.call('figma_create_node',{}));assert len(TOOLS)==9
 meta={'context':'file|page','file':'Fixture','page':'Inventory','permission':'read'}
 assert post('/pair',{**meta,'code':r.code},origin='https://evil.example')[0]==403
 assert post('/pair',{**meta,'code':r.code},host='evil.example')[0]==403
 code=r.code;status,paired=post('/pair',{**meta,'code':code});assert status==200;token=paired['token'];assert post('/pair',{**meta,'code':code})[0]==400
 reject(lambda:r.call('figma_create_node',{'type':'FRAME'}));assert post('/poll',meta,token='wrong')[0]==401
 result={};thread=threading.Thread(target=lambda:result.update(data=r.call('figma_get_document',{},timeout=2)));thread.start()
 for _ in range(100):
  job=post('/poll',meta,token)[1]['job']
  if job:break
  time.sleep(.01)
 assert job['tool']=='figma_get_document';assert post('/poll',meta,token)[1]['job'] is None
 assert post('/result',{'id':job['id'],'context':job['context'],'ok':True,'result':{'native':'read-back'}},token)[0]==200;thread.join();assert result['data']['native']=='read-back'
 assert post('/result',{'id':job['id'],'context':job['context'],'ok':True},token)[0]==400
 r.poll(token,{**meta,'permission':'edit'});reject(lambda:r.call('figma_create_node',{},timeout=.02),TimeoutError);assert r.poll(token,{**meta,'permission':'edit'})['job'] is None,'Timed out jobs never replay'
 r.disconnect();assert not r.status()['connected']
finally:r.close()
# Use the actual stdio launcher and protocol, independent of bridge process setup.
runtime=Path(__file__).resolve().parents[1]/'runtime'
messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},{'jsonrpc':'2.0','method':'notifications/initialized'},{'jsonrpc':'2.0','id':2,'method':'tools/list'},{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'figma_status','arguments':{}}}]
proc=subprocess.run([sys.executable,str(runtime/'launch_figma_mcp.py')],input='\n'.join(map(json.dumps,messages))+'\n',capture_output=True,text=True,env={**os.environ,'MS_FIGMA_PORT':'0'},timeout=10)
assert proc.returncode==0,proc.stderr;replies=[json.loads(line) for line in proc.stdout.splitlines()];assert len(replies)==3 and len(replies[1]['result']['tools'])==9;assert json.loads(replies[2]['result']['content'][0]['text'])['connected'] is False
print('PASS Figma real loopback HTTP and stdio MCP: paired origin/host/token guards, read/edit gates, native result receipts, stale timeout/no replay, current file status and real catalog handshake. Figma application is simulated separately.')
