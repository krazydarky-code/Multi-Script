# SPDX-License-Identifier: GPL-3.0-or-later
"""Deployable community workshop. Put behind an HTTPS reverse proxy.

Set MS_WORKSHOP_USERS to a JSON object mapping individual 24+ character tokens
to stable user ids. The authenticated identity, not the client's claimed id,
owns uploads and ratings. No public execution/installation or local bridge routes.
"""
import hmac,json,os,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from collections import defaultdict,deque
from threading import Lock,BoundedSemaphore
import studio_hub

RATES=defaultdict(deque);LOCK=Lock()
class WorkshopServer(ThreadingHTTPServer):
    daemon_threads=True
    request_queue_size=16
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.slots=BoundedSemaphore(16)
    def process_request(self,request,address):
        if not self.slots.acquire(False):
            try:request.sendall(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            finally:self.shutdown_request(request)
            return
        try:super().process_request(request,address)
        except Exception:self.slots.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()

class Handler(BaseHTTPRequestHandler):
    server_version="MultiScriptWorkshop/1"
    def log_message(self,*args):pass
    def reply(self,status,value):
        data=json.dumps(value,ensure_ascii=False).encode();self.send_response(status);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
    def do_POST(self):
        self.connection.settimeout(10)
        if self.path!="/workshop":return self.reply(404,{"ok":False,"error":"Unknown route"})
        auth=self.headers.get("Authorization","").removeprefix("Bearer ");user=""
        for token,identity in self.server.users.items():
            if hmac.compare_digest(auth,token):user=identity
        if not user:return self.reply(401,{"ok":False,"error":"Individual access token required"})
        with LOCK:
            q=RATES[user];now=time.time()
            while q and q[0]<now-60:q.popleft()
            if len(q)>=60:return self.reply(429,{"ok":False,"error":"Maximum 60 requests per minute"})
            q.append(now)
        try:
            length=int(self.headers.get("Content-Length","0"))
            if not 1<=length<=40000:return self.reply(413,{"ok":False,"error":"Payload exceeds 40 KB"})
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict) or data.get("action") not in ("list","publish","review"):raise ValueError("Only list, publish and review are exposed")
            out=studio_hub.workshop_local(data,identity=user);out["scope"]="Community";self.reply(200,out)
        except (ValueError,TypeError) as e:self.reply(400,{"ok":False,"error":str(e)})
        except Exception:self.reply(500,{"ok":False,"error":"Workshop storage unavailable"})

def main():
    users=json.loads(os.environ.get("MS_WORKSHOP_USERS","{}"))
    if not isinstance(users,dict) or not users:raise SystemExit("Set MS_WORKSHOP_USERS with individual access tokens first")
    for token,user in users.items():
        if len(token)<24:raise SystemExit("Access tokens must be at least 24 characters")
        studio_hub._client(user)
    address=os.environ.get("MS_WORKSHOP_HOST","127.0.0.1");port=int(os.environ.get("MS_WORKSHOP_PORT","8766"))
    server=WorkshopServer((address,port),Handler);server.users=users
    print(f"Workshop listening on {address}:{port}. Terminate TLS at your reverse proxy.");server.serve_forever()
if __name__=="__main__":main()
