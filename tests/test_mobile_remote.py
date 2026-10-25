import hashlib,http.client,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
import mobile_remote as m

def reject(fn,kind=ValueError):
    try:fn()
    except kind:return
    raise AssertionError('Expected rejection')

clock=[1000.0];r=m.Remote(clock=lambda:clock[0],port=0)
assert not r.status()['enabled'];assert m.extension_origin().startswith('chrome-extension://')
for host in ['0.0.0.0','8.8.8.8','localhost','::','169.254.1.1']:reject(lambda:r.admin('enable',{'host':host}))
try:
    state=r.admin('enable',{'host':'127.0.0.1'},owner='browser-a');assert state['enabled']
    reject(lambda:r.admin('status',owner='browser-b'))
    token=r.pair(state['pairCode'],'Test phone','127.0.0.2');reject(lambda:r.pair(state['pairCode'],'Replay','127.0.0.3'),PermissionError)
    def request(path,method='GET',data=None,origin=None,cookie=None,host=None):
        c=http.client.HTTPConnection('127.0.0.1',r.port,timeout=5);headers={}
        if origin:headers['Origin']=origin
        if cookie:headers['Cookie']='ms_phone='+cookie
        if host:headers['Host']=host
        if data is not None:headers['Content-Type']='application/json'
        c.request(method,path,body=json.dumps(data) if data is not None else None,headers=headers);resp=c.getresponse();body=resp.read();status=resp.status;head=dict(resp.getheaders());c.close();return status,body,head
    assert request('/api/state')[0]==401
    assert request('/api/state',cookie=token,host='evil.example')[0]==403
    assert request('/api/command','POST',{},origin='http://evil.example',cookie=token)[0]==403
    assert request('/')[0]==200 and 'frame-ancestors' in request('/')[2]['Content-Security-Policy']
    assert request('/runtime/config.json')[0]==404
    participant={'tabId':7,'name':'Vani','context':'vani|private-chat|C:/private/project','started':True,'ok':True,'progress':{'steps':[{'title':'Read source','status':'done','evidence':'Read-back'}]}}
    r.admin('sync',{'participants':[participant]},owner='browser-a');phone=r.state(token);context=phone['participants'][0]['context'];assert context!=participant['context'] and 'C:/private' not in json.dumps(phone)
    cmd={'id':'request-0001','tabId':7,'context':context,'action':'followup','text':'Preserve the camera'}
    assert r.command(token,cmd)['status']=='queued';assert r.command(token,cmd)['duplicate']
    packets=r.admin('sync',{'participants':[participant]},owner='browser-a');assert len(packets['commands'])==1 and packets['commands'][0]['context']==participant['context']
    assert not r.admin('sync',{'participants':[participant]},owner='browser-a')['commands'],'Never replay a dispatched request'
    r.admin('sync',{'participants':[participant],'receipts':[{'id':cmd['id'],'ok':True,'note':'Queued in chat'}]},owner='browser-a');assert r.state(token)['receipts'][0]['status']=='acknowledged'
    reject(lambda:r.command(token,{**cmd,'id':'request-0002','action':'execute_code'}))
    reject(lambda:r.command(token,{**cmd,'id':'request-0003','context':'stale'}))
    clock[0]+=13;reject(lambda:r.command(token,{**cmd,'id':'request-0004'}))
    state=r.admin('pair',owner='browser-a');clock[0]+=121;reject(lambda:r.pair(state['pairCode'],'Expired','1.2.3.4'),PermissionError)
    r.admin('pair',owner='browser-a')
    for _ in range(6):reject(lambda:r.pair('bad-code','Bad','192.168.1.50'),PermissionError)
    reject(lambda:r.pair(r.code,'Locked out','192.168.1.50'),PermissionError)
    device=r.status()['devices'][0]['id'];r.admin('revoke',{'device':device},owner='browser-a');reject(lambda:r.state(token),PermissionError)
    state=r.admin('pair',owner='browser-a');token=r.pair(state['pairCode'],'Expiry','192.168.1.51');clock[0]+=3601;reject(lambda:r.state(token),PermissionError)
finally:r.close()
assert not r.status()['enabled']
print('PASS opt-in phone service: real HTTP, pairing expiry/replay/rate limits, cookie auth, host/origin checks, bounded actions, opaque contexts, at-most-once dispatch, stale status and revocation.')
