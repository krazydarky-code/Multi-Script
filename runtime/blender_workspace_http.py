# SPDX-License-Identifier: GPL-3.0-or-later
"""Authenticated loopback-only HTTP surface for the owned Blender workspace."""
from pathlib import Path
import http.cookies,http.server,json,mimetypes,threading,re
from urllib.parse import urlsplit,unquote

STATIC=Path(__file__).resolve().parent/'blender-studio'
ASSETS={'preview.glb':'model/gltf-binary','scene.blend':'application/octet-stream','render.png':'image/png','export.blend':'application/octet-stream','export.glb':'model/gltf-binary','export.fbx':'application/octet-stream'}

class Server(http.server.ThreadingHTTPServer):
    daemon_threads=True;allow_reuse_address=True
    def __init__(self,*a,**kw):self.slots=threading.BoundedSemaphore(8);super().__init__(*a,**kw)
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):self.shutdown_request(request);return
        try:super().process_request(request,address)
        except Exception:self.slots.release();raise
    def process_request_thread(self,*a):
        try:super().process_request_thread(*a)
        finally:self.slots.release()

def serve(workspace,port):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,status,value,kind='application/json',cookie=None,download=False):
            raw=json.dumps(value,allow_nan=False).encode() if not isinstance(value,bytes) else value
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Cross-Origin-Resource-Policy','same-origin')
            # GLTFLoader's ImageBitmapLoader fetches embedded GLB images through
            # local blob URLs. img-src alone does not authorize that fetch.
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self' data:; img-src 'self' data: blob:; connect-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            if cookie:self.send_header('Set-Cookie',cookie)
            if download:self.send_header('Content-Disposition','attachment')
            self.end_headers();self.wfile.write(raw)
        def origin(self):return 'http://127.0.0.1:'+str(workspace.port)
        def host_ok(self):return self.headers.get('Host')=='127.0.0.1:'+str(workspace.port)
        def token(self):
            try:
                c=http.cookies.SimpleCookie();c.load(self.headers.get('Cookie',''));return c['ms_blender'].value if 'ms_blender'in c else ''
            except http.cookies.CookieError:return ''
        def allowed(self):
            if not self.host_ok():raise PermissionError('Invalid local workspace host.')
            if not workspace.authorized(self.token()):raise PermissionError('Open Blender Workspace from Multi-Script to connect this browser.')
        def do_GET(self):
            try:
                if not self.host_ok():raise PermissionError('Invalid local workspace host.')
                route=urlsplit(self.path).path
                if route=='/favicon.ico':self.reply(204,b'','image/x-icon');return
                if route=='/api/status':self.allowed();self.reply(200,workspace.status());return
                if route.startswith('/api/asset/'):
                    self.allowed();parts=route.split('/')
                    if len(parts)!=5 or (parts[4] not in ASSETS and not re.fullmatch(r'handoff-[a-f0-9]{32}\.(glb|fbx)',parts[4])):raise ValueError('Unknown workspace asset.')
                    path=workspace.folder(parts[3])/parts[4]
                    with workspace.lock:
                        if not path.is_file():self.reply(404,{'error':'Asset is not available yet.'});return
                        raw=path.read_bytes()
                    self.reply(200,raw,ASSETS.get(parts[4],'application/octet-stream'),download=parts[4].startswith(('export.','handoff-')) or parts[4]=='scene.blend');return
                names={'/':'index.html','/index.html':'index.html','/studio.bundle.js':'studio.bundle.js','/studio.css':'studio.css','/THIRD_PARTY_LICENSES.txt':'THIRD_PARTY_LICENSES.txt'}
                name=names.get(route)
                if not name or not (STATIC/name).is_file():self.reply(404,{'error':'Not found.'});return
                self.reply(200,(STATIC/name).read_bytes(),{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8','txt':'text/plain; charset=utf-8'}[name.rsplit('.',1)[-1]])
            except PermissionError as e:self.reply(403,{'ok':False,'error':str(e)})
            except (ValueError,OSError) as e:self.reply(400,{'ok':False,'error':str(e)})
        def do_POST(self):
            try:
                if not self.host_ok() or self.headers.get('Origin')!=self.origin():raise PermissionError('Same-origin local requests only.')
                route=urlsplit(self.path).path
                length=int(self.headers.get('Content-Length','0'))
                cap=50_000_000 if route=='/api/import' else 1_000_000
                if not 0<length<=cap:self.reply(413,{'ok':False,'error':'Request exceeds the workspace size limit.'});return
                self.connection.settimeout(30)
                if route!='/api/session':self.allowed()
                raw=self.rfile.read(length)
                if len(raw)!=length:raise ValueError('Incomplete request body.')
                if route=='/api/session':
                    token=workspace.session(json.loads(raw)['key']);self.reply(200,{'ok':True},cookie='ms_blender='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200');return
                if route=='/api/import':
                    # Browser-picked input is copied into the owned project. No
                    # user-supplied filesystem path is accepted by this route.
                    suffix=self.headers.get('X-MS-Format','').lower();project=self.headers.get('X-MS-Project','')
                    if suffix not in ('blend','glb'):raise ValueError('Import a .blend or self-contained .glb file.')
                    if project!=workspace.project:raise ValueError('The active project changed before import.')
                    if not workspace.lock.acquire(blocking=False):raise RuntimeError('Blender is busy. Wait before importing.')
                    try:
                        target=workspace.folder()/('import.'+suffix);target.write_bytes(raw)
                        response=workspace._request('import',{'file':target.name},300);workspace.scene=response['data']['scene']
                    finally:workspace.lock.release()
                    self.reply(200,response);return
                data=json.loads(raw)
                if not isinstance(data,dict):raise ValueError('Expected a JSON object.')
                if route=='/api/control':self.reply(200,{'ok':True,'job':workspace.submit(data.get('op'),data.get('args'))});return
                if route=='/api/command':
                    op=data.get('op');a=data.get('args') or {}
                    if op not in ('snapshot','primitive','transform','material','keyframe','delete','frame','render','export','handoff'):raise ValueError('This UI action is unavailable.')
                    if not a.get('project') or a['project']!=workspace.project:raise ValueError('The active project changed. Refresh the workspace before editing.')
                    self.reply(200,workspace.command(op,a,300));return
                self.reply(404,{'ok':False,'error':'Not found.'})
            except PermissionError as e:self.reply(403,{'ok':False,'error':str(e)})
            except Exception as e:self.reply(400,{'ok':False,'error':str(e)[:10000]})
    server=Server(('127.0.0.1',port),Handler);threading.Thread(target=server.serve_forever,name='Multi-Script Blender window',daemon=True).start();return server
