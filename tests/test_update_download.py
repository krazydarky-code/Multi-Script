"""Actual TLS download and downgrade/size rejection, no internet or user keys."""
import datetime
import http.server
import ipaddress
from pathlib import Path
import ssl
import sys
import tempfile
import threading
import urllib.request
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
import update_manager as u
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa

key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Multi-Script local updater test')])
now=datetime.datetime.now(datetime.timezone.utc)
cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1)).not_valid_after(now+datetime.timedelta(hours=1)).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False).add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True).sign(key,hashes.SHA256())
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    retries=0
    truncated=0
    def do_GET(self):
        if self.path=='/retry':
            type(self).retries+=1
            if self.retries<3:
                self.send_response(503);self.send_header('Retry-After','0');self.end_headers();return
        if self.path=='/truncated':
            type(self).truncated+=1
            if self.truncated==1:
                self.send_response(200);self.send_header('Content-Length','50');self.end_headers();self.wfile.write(b'short');return
        if self.path=='/redirect':
            self.send_response(302);self.send_header('Location','http://127.0.0.1/insecure');self.end_headers();return
        raw=b'actual TLS bytes'
        self.send_response(200)
        if self.path!='/no-length':self.send_header('Content-Length',str(len(raw)))
        self.end_headers();self.wfile.write(raw)
with tempfile.TemporaryDirectory(prefix='ms-update-tls-') as tmp:
    folder=Path(tmp);pem=folder/'test-key.pem';ca=folder/'test-cert.pem'
    pem.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    ca.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(str(ca),str(pem));server.socket=context.wrap_socket(server.socket,server_side=True)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    original=urllib.request.build_opener
    trust=ssl.create_default_context(cafile=str(ca))
    def opener(*handlers):return original(*handlers,urllib.request.HTTPSHandler(context=trust))
    url=f'https://127.0.0.1:{server.server_port}'
    try:
        with patch.object(urllib.request,'build_opener',side_effect=opener):
            progress=[]
            assert u.download(url+'/file',100,progress=progress.append)==b'actual TLS bytes'
            assert progress[-1]['bytes']==len(b'actual TLS bytes')
            progress=[]
            assert u.download(url+'/no-length',100,progress=progress.append)==b'actual TLS bytes'
            assert progress[-1]['total']==0, 'An unknown response length must not use the safety limit as a fake total'
            assert u.download(url+'/retry',100)==b'actual TLS bytes' and Handler.retries==3
            assert u.download(url+'/truncated',100)==b'actual TLS bytes' and Handler.truncated==2
            for path in ['/file','/no-length','/redirect']:
                try:u.download(url+path,3)
                except ValueError:pass
                else:raise AssertionError(path+' should reject')
        for bad in ['http://example.test/a','file:///secret','https://user:pass@example.test/x','https://example.test/x#part']:
            try:u.download(bad,100)
            except ValueError:pass
            else:raise AssertionError('Unsafe URL accepted')
    finally:server.shutdown();server.server_close();worker.join(3)
print('PASS actual locally trusted HTTPS download, bounded advertised/chunked body, insecure redirect and unsafe URL rejection; no TLS verification bypass.')
