# SPDX-License-Identifier: GPL-3.0-or-later
"""Local, paired Figma companion transport. Only stdio MCP can enqueue jobs."""
import collections,hashlib,http.server,json,secrets,threading,time
from urllib.parse import urlsplit

READ={'figma_get_document','figma_get_node','figma_export_node','figma_set_selection'}
WRITE={'figma_create_node','figma_update_node','figma_import_svg','figma_delete_node'}
def schema(properties=None,required=None):return {'type':'object','properties':properties or {},'required':required or [],'additionalProperties':False}
TEXT={'type':'string'}
PROPS=schema({k:{'type':'number'} for k in ['x','y','width','height','rotation','opacity','cornerRadius','fontSize','itemSpacing','paddingTop','paddingRight','paddingBottom','paddingLeft']})
PROPS['properties'].update({k:TEXT for k in ['name','characters','fill','stroke','layoutMode','primaryAxisAlignItems','counterAxisAlignItems','primaryAxisSizingMode','counterAxisSizingMode']})
PROPS['properties'].update({k:{'type':'boolean'} for k in ['visible','clipsContent']})
TOOLS=[
 {'name':'figma_status','description':'Check the paired Figma file, current page, permission and freshness. MCP process alive does not prove a live editable file.','inputSchema':schema()},
 {'name':'figma_get_document','description':'Inspect the current page, selected nodes and bounded hierarchy before editing.','inputSchema':schema({'depth':{'type':'integer','minimum':0,'maximum':4}})},
 {'name':'figma_get_node','description':'Read back a native node on the paired current page.','inputSchema':schema({'node_id':TEXT,'depth':{'type':'integer','minimum':0,'maximum':4}},['node_id'])},
 {'name':'figma_create_node','description':'Create an actual native FRAME, COMPONENT, RECTANGLE, ELLIPSE or TEXT on the current Figma page. Returns its real id and read-back. Fonts are loaded before text edits.','inputSchema':schema({'type':{'type':'string','enum':['FRAME','COMPONENT','RECTANGLE','ELLIPSE','TEXT']},'parent_id':TEXT,'properties':PROPS},['type'])},
 {'name':'figma_update_node','description':'Update allowlisted geometry, text, fills, strokes or Auto Layout properties on an unlocked native node. Read back and capture after editing.','inputSchema':schema({'node_id':TEXT,'properties':PROPS},['node_id','properties'])},
 {'name':'figma_import_svg','description':'Import an actual editable vector SVG into the paired current page; no external links/scripts. Source must be supplied, not a path.','inputSchema':schema({'svg':{'type':'string','maxLength':131072},'name':TEXT,'parent_id':TEXT},['svg'])},
 {'name':'figma_export_node','description':'Capture a native current-page node as PNG or SVG for real visual verification. Returns base64/image evidence, not a fabricated preview.','inputSchema':schema({'node_id':TEXT,'format':{'type':'string','enum':['PNG','SVG']},'scale':{'type':'number','minimum':0.25,'maximum':2}},['node_id'])},
 {'name':'figma_set_selection','description':'Select native current-page nodes and focus their bounds in Figma.','inputSchema':schema({'node_ids':{'type':'array','maxItems':30,'items':TEXT}},['node_ids'])},
 {'name':'figma_delete_node','description':'Delete an unlocked current-page node only after inspecting it and explicit confirm=true. Never deletes pages/documents.','inputSchema':schema({'node_id':TEXT,'confirm':{'type':'boolean'}},['node_id','confirm'])},
]

class Link:
 def __init__(self,clock=time.monotonic):
  self.clock=clock;self.lock=threading.RLock();self.code=f'{secrets.randbelow(100000000):08d}';self.code_until=clock()+300;self.attempts=collections.deque();self.token='';self.context='';self.meta={};self.seen=0;self.permission='read';self.jobs=collections.OrderedDict();self.server=None
 def status(self):
  with self.lock:return {'connected':bool(self.token and self.clock()-self.seen<12),'file':self.meta.get('file',''),'page':self.meta.get('page',''),'permission':self.permission,'pending':sum(not j['event'].is_set() for j in self.jobs.values()),'scope':'Current page only. Keep the companion open; writes require Edit mode.'}
 def pair(self,data):
  with self.lock:
   now=self.clock()
   while self.attempts and now-self.attempts[0]>60:self.attempts.popleft()
   if len(self.attempts)>=6:raise ValueError('Too many pairing attempts; wait a minute.')
   self.attempts.append(now)
   if not self.code or now>self.code_until or not secrets.compare_digest(str(data.get('code','')).replace(' ',''),self.code):raise ValueError('Invalid/expired code. Restart this Figma MCP server for a fresh code.')
   if not isinstance(data.get('context'),str) or not 1<=len(data['context'])<=500:raise ValueError('Missing file/page context.')
   self.disconnect();self.code='';self.token=secrets.token_urlsafe(32);self.context=data['context'];self.meta={k:str(data.get(k,''))[:200] for k in ['file','page']};self.permission='edit' if data.get('permission')=='edit' else 'read';self.seen=now
   return {'token':self.token,'ok':True}
 def authenticated(self,token):
  if not self.token or not secrets.compare_digest(str(token),self.token):raise PermissionError('Pair the companion first.')
 def poll(self,token,data):
  with self.lock:
   self.authenticated(token)
   if data.get('context')!=self.context:
    self._cancel('Figma page/file changed; inspect the new target before retrying.');self.context=str(data.get('context',''))[:500]
   permission='edit' if data.get('permission')=='edit' else 'read'
   if permission!=self.permission:self._cancel('Companion permission changed before completion.')
   self.permission=permission;self.meta={k:str(data.get(k,''))[:200] for k in ['file','page']};self.seen=self.clock()
   for job in self.jobs.values():
    if not job['claimed'] and not job['event'].is_set():job['claimed']=True;return {'ok':True,'job':{k:job[k] for k in ['id','tool','arguments','context']}}
   return {'ok':True,'job':None}
 def result(self,token,data):
  with self.lock:
   self.authenticated(token);job=self.jobs.get(data.get('id'))
   if not job or not job['claimed'] or job['event'].is_set():raise ValueError('Unknown/already-settled job. Never replay it.')
   if data.get('context')!=job['context'] or self.context!=job['context']:raise ValueError('Result belongs to a different page.')
   job['result']=data;job['event'].set();self.seen=self.clock();return {'ok':True}
 def call(self,name,args,timeout=60):
  if name=='figma_status':return self.status()
  if name not in READ|WRITE:raise ValueError('Unknown Figma command.')
  with self.lock:
   if not self.status()['connected']:raise ValueError('Figma is not paired or the companion is offline. Open the bundled plugin and pair it first.')
   if name in WRITE and self.permission!='edit':raise ValueError('Companion is Read only. Enable Edit inside Figma before changing nodes.')
   if len(self.jobs)>=32:raise ValueError('Too many pending Figma jobs.')
   job={'id':secrets.token_hex(16),'tool':name,'arguments':args,'context':self.context,'event':threading.Event(),'claimed':False};self.jobs[job['id']]=job
  ready=job['event'].wait(timeout)
  with self.lock:
   self.jobs.pop(job['id'],None)
   if not ready:raise TimeoutError('Figma did not confirm the job. Inspect the file before retrying; the edit may have run. It will not be replayed.')
   result=job.get('result',{})
   if result.get('ok') is not True:raise ValueError(str(result.get('error') or 'Figma rejected the operation.'))
   return result.get('result')
 def _cancel(self,error):
  for j in self.jobs.values():
   if not j['event'].is_set():j['result']={'ok':False,'error':error};j['event'].set()
 def disconnect(self):
  with self.lock:self._cancel('Figma companion disconnected. Check results before retrying.');self.token='';self.context='';self.meta={};self.seen=0
 def close(self):
  self.disconnect()
  if self.server:self.server.shutdown();self.server.server_close();self.server=None
 def serve(self,port=17616):
  link=self
  class Handler(http.server.BaseHTTPRequestHandler):
   def setup(self):self.request.settimeout(5);super().setup()
   def log_message(self,*a):pass
   def origin(self):
    raw=self.headers.get('Origin','');url=urlsplit(raw)
    return raw if raw=='null' or (url.scheme=='https' and (url.hostname in ['www.figma.com','figma.com'] or (url.hostname or '').endswith(('.figma.com','.figmausercontent.com')))) else ''
   def valid(self):return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}' and bool(self.origin())
   def reply(self,code,data):
    body=json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
    if self.origin():self.send_header('Access-Control-Allow-Origin',self.origin());self.send_header('Vary','Origin')
    self.end_headers();self.wfile.write(body)
   def do_OPTIONS(self):
    if not self.valid():self.reply(403,{'ok':False});return
    self.send_response(204);self.send_header('Access-Control-Allow-Origin',self.origin());self.send_header('Access-Control-Allow-Methods','POST, OPTIONS');self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type');self.send_header('Access-Control-Allow-Private-Network','true');self.end_headers()
   def do_POST(self):
    if not self.valid():self.reply(403,{'ok':False,'error':'Only the local Figma companion may connect.'});return
    try:
     size=int(self.headers.get('Content-Length','0'))
     if not 0<size<=6000000 or self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('Use bounded JSON.')
     data=json.loads(self.rfile.read(size))
     if not isinstance(data,dict):raise ValueError('Expected object.')
     token=self.headers.get('Authorization','').removeprefix('Bearer ')
     if self.path=='/pair':result=link.pair(data)
     elif self.path=='/poll':result=link.poll(token,data)
     elif self.path=='/result':result=link.result(token,data)
     elif self.path=='/disconnect':link.authenticated(token);link.disconnect();result={'ok':True}
     else:self.reply(404,{'ok':False,'error':'Not found.'});return
     self.reply(200,result)
    except PermissionError as e:self.reply(401,{'ok':False,'error':str(e)})
    except (ValueError,TypeError,KeyError) as e:self.reply(400,{'ok':False,'error':str(e)[:400]})
    except OSError:self.close_connection=True
  class Server(http.server.ThreadingHTTPServer):
   daemon_threads=True
   def __init__(self,*a):self.slots=threading.BoundedSemaphore(8);super().__init__(*a)
   def process_request(self,request,address):
    if not self.slots.acquire(False):self.shutdown_request(request);return
    try:super().process_request(request,address)
    except Exception:self.slots.release();raise
   def process_request_thread(self,*args):
    try:super().process_request_thread(*args)
    finally:self.slots.release()
  self.server=Server(('127.0.0.1',port),Handler);threading.Thread(target=self.server.serve_forever,daemon=True).start();return self.server.server_port
