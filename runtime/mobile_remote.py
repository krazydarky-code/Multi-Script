# SPDX-License-Identifier: GPL-3.0-or-later
"""Opt-in LAN phone remote. No engine/file endpoints; browser actions use receipts.

The normal engine bridge stays loopback-only. This separate listener is disabled
at boot and binds one explicitly selected private IPv4 address. Pairing grants
one hour of bounded status/follow-up/queue/stop access. Nothing persists to disk.
"""
import collections
import hashlib
import http.cookies
import http.server
import ipaddress
import json
from pathlib import Path
import secrets
import socket
import threading
import time
import urllib.parse

HERE=Path(__file__).resolve().parent
NETWORKS=[ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','127.0.0.0/8')]

class BoundedServer(http.server.ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,*args,**kwargs):self.slots=threading.BoundedSemaphore(16);super().__init__(*args,**kwargs)
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):self.shutdown_request(request);return
        try:super().process_request(request,address)
        except Exception:self.slots.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()

def allowed_address(host):
    try:return any(ipaddress.ip_address(host) in n for n in NETWORKS)
    except ValueError:return False

def local_addresses():
    found=set()
    try:
        for row in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
            host=row[4][0]
            if allowed_address(host) and not host.startswith('127.'):found.add(host)
    except OSError:pass
    return sorted(found)

def extension_origin():
    import base64
    key=json.loads((HERE.parent/'extension/manifest.json').read_text(encoding='utf-8'))['key']
    digest=hashlib.sha256(base64.b64decode(key)).digest()[:16]
    return 'chrome-extension://'+''.join(chr(97+(b>>4))+chr(97+(b&15)) for b in digest)

class Remote:
    def __init__(self,clock=time.time,port=17615):
        self.clock=clock;self.port=port;self.lock=threading.RLock();self.server=None;self.thread=None
        self.code='';self.code_until=0;self.sessions={};self.attempts={};self.requests=collections.OrderedDict();self.snapshot=[];self.snapshot_at=0;self.host='';self.owner='';self.owner_seen=0

    def _prune(self):
        now=self.clock()
        self.sessions={k:v for k,v in self.sessions.items() if v['until']>now}
        self.attempts={k:v for k,v in self.attempts.items() if now-v[0]<60}
        for r in self.requests.values():
            if r['status']=='queued' and now-r['at']>15:r.update(status='expired',error='Desktop did not claim this request. Nothing was dispatched.')
            elif r['status']=='dispatching' and now-r['at']>50:r.update(status='unconfirmed',error='No receipt. Inspect the desktop chat before sending again.')
        while len(self.requests)>200:self.requests.popitem(last=False)

    def status(self):
        with self.lock:
            self._prune()
            return {'ok':True,'enabled':self.server is not None,'addresses':local_addresses(),'host':self.host,'url':f'http://{self.host}:{self.port}' if self.server else '',
                    'pairCode':self.code if self.code_until>self.clock() else '', 'pairExpires':self.code_until,
                    'devices':[{'id':v['id'],'name':v['name'],'expires':v['until']} for v in self.sessions.values()],
                    'fresh':self.clock()-self.snapshot_at<12,'transport':'Trusted local network only; HTTP is not encrypted. Never port-forward this listener.'}

    def admin(self,op,payload=None,owner='desktop'):
        payload=payload or {}
        with self.lock:
            # Only one browser profile may own the remote while it is enabled.
            if self.server and self.owner!=owner:raise ValueError('Phone remote belongs to another connected browser profile. Disable it there first.')
        if op=='enable':
            host=payload.get('host','')
            if not isinstance(host,str) or not allowed_address(host):raise ValueError('Select a local private IPv4 address. Public/wildcard bindings are refused.')
            with self.lock:
                if self.server:raise ValueError('Disable the current phone remote before enabling another address.')
                handler=self._handler();server=BoundedServer((host,self.port),handler)
                self.port=server.server_address[1];self.server=server;self.host=host;self.owner=owner;self.owner_seen=self.clock();self.snapshot=[];self.snapshot_at=0
                self.code=f'{secrets.randbelow(100000000):08d}';self.code_until=self.clock()+120
                self.thread=threading.Thread(target=server.serve_forever,name='multiscript-phone',daemon=True);self.thread.start()
            return self.status()
        if op=='disable':self.close();return self.status()
        with self.lock:
            self._prune()
            if op=='pair':
                if not self.server:raise ValueError('Enable phone control first.')
                self.code=f'{secrets.randbelow(100000000):08d}';self.code_until=self.clock()+120
            elif op=='revoke':
                wanted=payload.get('device')
                self.sessions={k:v for k,v in self.sessions.items() if v['id']!=wanted}
                for r in self.requests.values():
                    if r['device']==wanted and r['status']=='queued':r.update(status='revoked',error='Device revoked before dispatch.')
            elif op=='sync':
                if not self.server:return {'ok':True,'enabled':False,'commands':[]}
                now=self.clock();self.owner_seen=now
                rows=payload.get('participants',[])
                if not isinstance(rows,list) or len(json.dumps(rows))>150000:raise ValueError('Remote snapshot exceeds its bounded size.')
                self.snapshot=[self._participant(x) for x in rows[:40] if isinstance(x,dict) and isinstance(x.get('tabId'),int)]
                self.snapshot_at=now
                for receipt in payload.get('receipts',[])[:32]:
                    if not isinstance(receipt,dict):continue
                    r=self.requests.get(receipt.get('id'))
                    if r and r['status'] in ('dispatching','unconfirmed'):
                        ok=receipt.get('ok') is True;r.update(status='acknowledged' if ok else 'rejected',result=str(receipt.get('note') or ('Queued in the selected chat.' if r['action']=='followup' else 'Desktop acknowledged the action.'))[:500],error='' if ok else str(receipt.get('error') or 'Desktop rejected the action.')[:500])
                commands=[]
                for r in self.requests.values():
                    if r['status']=='queued' and len(commands)<4:
                        r['status']='dispatching';commands.append({k:r[k] for k in ['id','tabId','context','action','text','kind']})
                return {'ok':True,'enabled':True,'commands':commands}
            elif op!='status':raise ValueError('Unsupported remote setting.')
            return self.status()

    def _participant(self,x):
        progress=x.get('progress') or {};steps=progress.get('steps') or []
        summary=progress.get('summary') or {}
        def bounded(value,maximum=28800000):
            return max(0,min(maximum,int(value))) if isinstance(value,(int,float)) and value==value and abs(value)!=float('inf') else 0
        estimate=summary.get('estimate') or {}
        monitor={'state':str(summary.get('state') or '')[:80],'stage':str(summary.get('stage') or '')[:240],
                 'timingLate':summary.get('timingLate') is True,'automatic':summary.get('automatic') is True,'elapsedMs':bounded(summary.get('elapsedMs'),604800000),
                 'estimate':{'lowMs':bounded(estimate.get('lowMs')),'highMs':bounded(estimate.get('highMs')),'source':str(estimate.get('source') or '')[:80]} if estimate else None}
        return {'tabId':x['tabId'],'name':str(x.get('name') or x.get('provider') or 'Provider')[:80],'title':str(x.get('title') or '')[:160],
                'context':str(x.get('context') or '')[:3000],'queuePending':max(0,min(20,int(x.get('queuePending') or 0))),**{k:x.get(k) is True for k in ['ok','started','starting','running','generating','stopped','providerFailed','hasDraft','background','queuePaused']},
                'progress':{'title':str(progress.get('title') or '')[:300],'calls':bounded(progress.get('calls'),1000000000),'errors':bounded(progress.get('errors'),1000000000),'summary':monitor,
                            'steps':[{'title':str(s.get('title') or '')[:200],'status':str(s.get('status') or 'pending')[:16],'evidence':str(s.get('evidence') or '')[:500],'blocker':str(s.get('blocker') or '')[:500]} for s in steps[:24] if isinstance(s,dict)]}}

    def pair(self,code,name,ip):
        with self.lock:
            self._prune();now=self.clock();window,count=self.attempts.get(ip,(now,0))
            if count>=6:raise PermissionError('Too many pairing attempts. Wait one minute.')
            if len(self.attempts)>=128 and ip not in self.attempts:raise PermissionError('Pairing is busy. Try again later.')
            self.attempts[ip]=(window,count+1)
            if not self.code or now>=self.code_until or not secrets.compare_digest(str(code),self.code):raise PermissionError('Pairing code is invalid or expired.')
            if len(self.sessions)>=4:raise ValueError('Maximum four paired devices. Revoke one on the desktop.')
            token=secrets.token_urlsafe(32);self.sessions[hashlib.sha256(token.encode()).hexdigest()]={'id':secrets.token_hex(8),'name':str(name or 'Phone')[:60],'until':now+3600}
            self.code='';self.code_until=0;return token

    def device(self,token):
        with self.lock:
            self._prune();key=hashlib.sha256(str(token).encode()).hexdigest();device=self.sessions.get(key)
            if not device:raise PermissionError('Pair this device from the desktop again.')
            return device

    def state(self,token):
        with self.lock:
            d=self.device(token);fresh=self.clock()-self.snapshot_at<12
            return {'ok':True,'fresh':fresh,'updated':self.snapshot_at,'participants':[{**p,'context':hashlib.sha256(p['context'].encode()).hexdigest()} for p in self.snapshot],
                    'receipts':[{k:r.get(k,'') for k in ['id','action','status','result','error']} for r in list(self.requests.values()) if r['device']==d['id']][-30:]}

    def command(self,token,data):
        with self.lock:
            d=self.device(token);rid=data.get('id','')
            if not isinstance(rid,str) or not 8<=len(rid)<=80 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-' for c in rid):raise ValueError('A unique request id is required.')
            if rid in self.requests:
                if self.requests[rid]['device']!=d['id']:raise ValueError('Request id belongs to another device.')
                return {'ok':True,'id':rid,'status':self.requests[rid]['status'],'duplicate':True}
            if self.clock()-self.snapshot_at>=12:raise ValueError('Desktop is disconnected. Refresh after reconnecting it.')
            target=next((x for x in self.snapshot if x['tabId']==data.get('tabId')),None)
            if not target or not target['ok'] or not target['context'] or data.get('context')!=hashlib.sha256(target['context'].encode()).hexdigest():raise ValueError('Chat changed. Refresh and choose the target again.')
            action=data.get('action');text=data.get('text','');kind=data.get('kind','followup')
            if action not in ['followup','pause','resume','stop']:raise ValueError('Only follow-up, pause/resume queue and stop are available.')
            if action=='followup' and (not target['started'] or not isinstance(text,str) or not text.strip() or len(text)>4000):raise ValueError('Choose a started chat and enter 1–4,000 characters.')
            if sum(r['status']=='queued' for r in self.requests.values())>=32:raise ValueError('Remote queue is full. Wait for receipts.')
            if sum(r['device']==d['id'] and self.clock()-r['at']<60 for r in self.requests.values())>=30:raise ValueError('Too many remote requests. Wait a minute.')
            self.requests[rid]={'id':rid,'device':d['id'],'tabId':target['tabId'],'context':target['context'],'action':action,'text':text.strip() if action=='followup' else '', 'kind':kind if kind in ['correction','goal'] else 'followup','at':self.clock(),'status':'queued'}
            self._prune();return {'ok':True,'id':rid,'status':'queued'}

    def close(self):
        with self.lock:
            server=self.server;self.server=None;self.code='';self.code_until=0;self.sessions={};self.requests.clear();self.snapshot=[];self.snapshot_at=0;self.owner=''
        if server:server.shutdown();server.server_close()

    def _handler(self):
        remote=self
        class Handler(http.server.BaseHTTPRequestHandler):
            server_version='MultiScriptPhone';sys_version='';protocol_version='HTTP/1.0'
            def setup(self):
                self.request.settimeout(5)
                super().setup()
            def log_message(self,*args):pass # Never log pairing codes or cookies.
            def reply(self,status,payload,kind='application/json; charset=utf-8',cookie=None):
                body=payload if isinstance(payload,bytes) else json.dumps(payload).encode()
                self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
                if cookie:self.send_header('Set-Cookie',cookie)
                self.end_headers();self.wfile.write(body)
            def valid_host(self):
                expected=f'{remote.host}:{remote.port}'
                return self.headers.get('Host')==expected
            def token(self):
                try:c=http.cookies.SimpleCookie();c.load(self.headers.get('Cookie',''));return c['ms_phone'].value if 'ms_phone' in c else ''
                except http.cookies.CookieError:return ''
            def do_GET(self):
                if not self.valid_host():self.reply(403,{'ok':False,'error':'Unexpected host.'});return
                path=urllib.parse.urlsplit(self.path).path
                if path in ['/', '/phone.js','/phone.css']:
                    file=HERE/'phone'/({'/':'index.html','/phone.js':'phone.js','/phone.css':'phone.css'}[path]);kind={'/':'text/html','/phone.js':'text/javascript','/phone.css':'text/css'}[path]
                    self.reply(200,file.read_bytes(),kind+'; charset=utf-8');return
                if path!='/api/state':self.reply(404,{'ok':False,'error':'Not found.'});return
                try:self.reply(200,remote.state(self.token()))
                except PermissionError as e:self.reply(401,{'ok':False,'error':str(e)})
            def do_POST(self):
                if not self.valid_host() or self.headers.get('Origin')!=f'http://{remote.host}:{remote.port}':self.reply(403,{'ok':False,'error':'Same-origin requests only.'});return
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=16000 or self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('Use bounded JSON requests.')
                    self.connection.settimeout(5);data=json.loads(self.rfile.read(length))
                    if not isinstance(data,dict):raise ValueError('Expected an object.')
                    if self.path=='/api/pair':
                        token=remote.pair(str(data.get('code','')).replace(' ',''),data.get('name'),self.client_address[0]);self.reply(200,{'ok':True},cookie='ms_phone='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600')
                    elif self.path=='/api/command':self.reply(200,remote.command(self.token(),data))
                    else:self.reply(404,{'ok':False,'error':'Not found.'})
                except PermissionError as e:self.reply(401,{'ok':False,'error':str(e)})
                except (ValueError,TypeError,KeyError,OverflowError) as e:self.reply(400,{'ok':False,'error':str(e)[:400]})
                except (OSError,TimeoutError):self.close_connection=True
        return Handler
