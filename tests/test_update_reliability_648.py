import base64,json,sys,tempfile,threading
from pathlib import Path
from unittest.mock import patch
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
import update_manager as u
from cryptography.hazmat.primitives.asymmetric import rsa,padding
from cryptography.hazmat.primitives import hashes
key=rsa.generate_private_key(public_exponent=65537,key_size=3072);pub=key.public_key().public_numbers();cfg={'feedUrl':'https://example.test/feed.json','publicKey':{'n':format(pub.n,'x'),'e':pub.e}}
def setup(base):
 root=base/'install';root.mkdir();old={'extension/manifest.json':json.dumps({'version':'1.0','key':'stable'}).encode(),'runtime/edition.json':b'{"edition":"dev"}','runtime/update-channel.json':json.dumps(cfg).encode(),'main.txt':b'old','obsolete.txt':b'old remove'}
 old['update-files.json']=json.dumps({n:u.sha(v) for n,v in old.items()}).encode()
 for n,v in old.items():p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(v)
 private=root/'runtime/config.json';private.write_bytes(b'private')
 new={**old,'extension/manifest.json':b'{"version":"1.1","key":"stable"}','main.txt':b'new'};new.pop('obsolete.txt');new.pop('update-files.json');new['update-files.json']=json.dumps({n:u.sha(v) for n,v in new.items()}).encode()
 archive=base/'new.zip'
 with zipfile.ZipFile(archive,'w') as z:
  for n,v in new.items():z.writestr('Multi-Script/'+n,v)
 blob=archive.read_bytes();meta={'product':'Multi-Script','channel':'dev','version':'1.1','url':'https://example.test/new.zip','size':len(blob),'sha256':u.sha(blob)};raw=json.dumps(meta).encode();env={'payload':base64.b64encode(raw).decode(),'signature':base64.b64encode(key.sign(raw,padding.PKCS1v15(),hashes.SHA256())).decode()}
 updater=u.Updater(root)
 def download(url,limit,**kw):
  if url.endswith('.json'):return json.dumps(env).encode()
  if kw.get('progress'):kw['progress']({'bytes':len(blob),'total':len(blob),'attempt':1})
  return blob
 with patch.object(u,'download',side_effect=download):updater.check()
 return updater,old,new,download
with tempfile.TemporaryDirectory() as tmp:
 base=Path(tmp);updater,old,new,download=setup(base)
 entered=threading.Event();release=threading.Event();errors=[]
 (updater.home/'release.zip').unlink()
 def slow(url,limit,**kw):
  if not url.endswith('.json'):
   if kw.get('progress'):kw['progress']({'bytes':5,'total':100,'attempt':1})
   entered.set();release.wait(5)
  return download(url,limit,**kw)
 def check():
  try:updater.check()
  except Exception as e:errors.append(e)
 with patch.object(u,'download',side_effect=slow):
  t=threading.Thread(target=check);t.start()
  try:
   assert entered.wait(3);state=u.Updater(updater.root).status()
  finally:release.set();t.join(5)
  assert state['busy'] and state['progress']['phase']=='downloading',state
  assert not t.is_alive() and not errors
 assert not updater.status()['busy']
 with patch.object(u.shutil,'disk_usage',return_value=type('Space',(),{'free':0})()):
  try:updater.apply();raise AssertionError('Low disk accepted')
  except ValueError as e:assert 'disk space' in str(e)
 assert not updater.journal.exists() and (updater.root/'main.txt').read_bytes()==b'old'
 replace=updater._replace;count=[0]
 def crash(name,raw):
  count[0]+=1
  if count[0]==3:raise KeyboardInterrupt()
  replace(name,raw)
 try:
  with patch.object(updater,'_replace',side_effect=crash):updater.apply()
 except KeyboardInterrupt:pass
 backup=updater.home/'backup/obsolete.txt';saved=backup.read_bytes();backup.write_bytes(b'damaged');before={p.relative_to(updater.root).as_posix():p.read_bytes() for p in updater.root.rglob('*') if p.is_file() and '.updates' not in p.parts}
 try:updater.recover();raise AssertionError('Damaged backup accepted')
 except ValueError as e:assert 'backup is damaged' in str(e)
 assert all((updater.root/n).read_bytes()==v for n,v in before.items()),'Recovery must prevalidate all backups before changing files'
 backup.write_bytes(saved);assert updater.recover()['rolledBack']
 write=u.write_json;failed=[False]
 def fail_receipt(path,value):
  if Path(path).name=='last-update.json' and not failed[0]:failed[0]=True;raise OSError('receipt interrupted')
  return write(path,value)
 try:
  with patch.object(u,'write_json',side_effect=fail_receipt):updater.apply()
 except OSError:pass
 assert updater.status()['current']=='1.1' and updater.status()['recoveryRequired']
 result=u.Updater(updater.root).recover();assert result['installed']=='1.1' and result['lastUpdate']['version']=='1.1'
 assert (updater.root/'main.txt').read_bytes()==b'new' and (updater.root/'runtime/config.json').read_bytes()==b'private'
print('PASS actual cross-instance lock/progress reads, disk preflight, all-backup validation, interrupted committed-receipt recovery and private data retention.')
