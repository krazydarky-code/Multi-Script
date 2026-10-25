"""Signed temporary updates and a real launcher ping; no user registry edits."""
import base64,importlib.util,json,os,sys,tempfile,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
import update_manager as u
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa,padding
ROOT=Path(__file__).resolve().parents[1];key=rsa.generate_private_key(public_exponent=65537,key_size=3072);pub=key.public_key().public_numbers();cfg={'feedUrl':'https://updates.example.test/feed','publicKey':{'n':format(pub.n,'x'),'e':pub.e}}
installer='''import json,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1]
assert sys.argv[1:]==['--post-update','--no-pause','--no-start']
p=r/'runtime/studio-data';p.mkdir(exist_ok=True);c=p/'setup-runs.txt';c.write_text(str(int(c.read_text())+1 if c.exists() else 1))
if (p/'setup-fail').exists(): print('fixture dependency failure');sys.exit(3)
v=json.loads((r/'extension/manifest.json').read_text())['version']
(r/'.updates/setup-complete.json').write_text(json.dumps({'version':v,'root':str(r.resolve()),'launcherVerified':True}))
'''
def sign(data):
 raw=json.dumps(data).encode();return {'payload':base64.b64encode(raw).decode(),'signature':base64.b64encode(key.sign(raw,padding.PKCS1v15(),hashes.SHA256())).decode()}
def files(version,setup):
 result={'extension/manifest.json':json.dumps({'version':version,'key':'stable-test','permissions':['storage']}).encode(),'runtime/edition.json':b'{"edition":"dev"}','runtime/update-channel.json':json.dumps(cfg).encode(),'runtime/product-manifest.json':json.dumps({'updates':{'postInstallSetup':'native-host-v1'} if setup else {}}).encode(),'runtime/install_native_host.py':installer.encode(),'runtime/bridge.py':b'# fixture only'}
 result['update-files.json']=json.dumps({n:u.sha(raw) for n,raw in result.items()}).encode();return result
with tempfile.TemporaryDirectory(prefix='ms-setup-update-') as temp:
 root=Path(temp)/'Multi-Script';root.mkdir()
 for name,raw in files('1.0',False).items():p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
 private=root/'runtime/config.json';private.write_bytes(b'private MCP connections remain')
 manager=u.Updater(root)
 def stage(version):
  archive=Path(temp)/'release.zip'
  with zipfile.ZipFile(archive,'w') as z:
   for name,raw in files(version,True).items():z.writestr('Multi-Script/'+name,raw)
  blob=archive.read_bytes();data={'product':'Multi-Script','channel':'dev','version':version,'url':'https://updates.example.test/code.zip','size':len(blob),'sha256':u.sha(blob)};envelope=sign(data)
  with patch.object(u,'download',side_effect=lambda url,limit,**kw:json.dumps(envelope).encode() if url==cfg['feedUrl'] else blob):assert manager.check()['staged']==version
 stage('1.1');result=manager.apply();assert result['installed']=='1.1' and result['setupComplete'] and not result['setupPending']
 count=root/'runtime/studio-data/setup-runs.txt';assert count.read_text()=='1';manager.setup();assert count.read_text()=='1','Setup is once per version'
 stage('1.2');fail=root/'runtime/studio-data/setup-fail';fail.write_text('fixture only')
 try:manager.apply();raise AssertionError('Failed setup reported success')
 except ValueError as error:assert 'setup is incomplete' in str(error)
 state=manager.status();assert state['current']=='1.2' and state['setupPending'] and not state['recoveryRequired']
 try:manager.check();raise AssertionError('Pending setup proof can be overwritten')
 except ValueError as error:assert 'Finish setup' in str(error)
 fail.unlink();assert manager.setup()['setupComplete'];assert count.read_text()=='3';assert private.read_bytes()==b'private MCP connections remain'
 (manager.home/'setup-complete.json').unlink();script=root/'runtime/install_native_host.py';original=script.read_bytes();script.write_bytes(original+b'\n# locally changed')
 try:manager.setup();raise AssertionError('Unsigned modified installer executed')
 except ValueError as error:assert 'differs from the signed release' in str(error)
 assert count.read_text()=='3';script.write_bytes(original);(manager.home/'staged-envelope.json').unlink()
 try:manager.setup();raise AssertionError('Unproved installer executed')
 except ValueError as error:assert 'no signed update proof' in str(error)

# Exercise the shipped installer's real .bat/.sh and native_host.py framing in a
# temporary folder. Browser registration/dependency installation are fixtures.
spec=importlib.util.spec_from_file_location('setup6481',ROOT/'runtime/install_native_host.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
with tempfile.TemporaryDirectory(prefix='ms-real-launcher-') as temp:
 r=Path(temp);runtime=r/'runtime';runtime.mkdir();ext=r/'extension';ext.mkdir();(r/'logs').mkdir()
 manifest=json.loads((ROOT/'extension/manifest.json').read_text());manifest['version']='9.9.1';(ext/'manifest.json').write_text(json.dumps(manifest));(runtime/'native_host.py').write_bytes((ROOT/'runtime/native_host.py').read_bytes());(runtime/'bridge.py').write_text('BRIDGE_VERSION = "9.9.1"\n')
 with patch.multiple(module,ROOT=str(r),HERE=str(runtime),EXT_DIR=str(ext),HOST_PY=str(runtime/'native_host.py'),LOG_DIR=str(r/'logs')),patch.object(module,'register',return_value=['fixture']) as register,patch.object(module,'detect_extension_ids',side_effect=AssertionError('Post-update must not scan browser profiles')),patch.object(module,'sandboxed_browsers',return_value=[]),patch.object(module,'ensure_websockets',return_value=True) as deps,patch.object(module,'ensure_pillow',return_value=True),patch.object(module,'replace_bridge',side_effect=AssertionError('Setup must not start a bridge')):
  assert module.main(['--post-update','--no-pause','--no-start'])==0
  receipt=json.loads((r/'.updates/setup-complete.json').read_text());assert receipt['version']=='9.9.1' and receipt['launcherVerified'] and Path(receipt['root'])==r
  assert register.call_count==1 and deps.call_count==1
  (r/'.updates/setup-complete.json').unlink()
  with patch.object(module,'self_test',return_value=(False,'fixture launch failure')):assert module.main(['--post-update','--no-pause','--no-start'])==1
  assert not (r/'.updates/setup-complete.json').exists(),'A failed launcher cannot create a completion receipt'
print('PASS signed auto-setup, once-per-version receipts, retry after failure, private data, tamper/proof rejection, and real native launcher framing with isolated registration fixtures.')
