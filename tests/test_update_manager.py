"""Real signed releases, temporary installation, rollback and private data checks.
Publisher/test dependency: cryptography. Runtime verifier has no new dependency.
"""
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
import update_manager as u
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding

key=rsa.generate_private_key(public_exponent=65537,key_size=3072)
pub=key.public_key().public_numbers()
public={'n':format(pub.n,'x'),'e':pub.e}
cfg={'channel':'dev','feedUrl':'https://releases.example.test/dev.json','publicKey':public}
def sign(data):
    raw=json.dumps(data,separators=(',',':'),sort_keys=True).encode()
    return {'payload':base64.b64encode(raw).decode(),'signature':base64.b64encode(key.sign(raw,padding.PKCS1v15(),hashes.SHA256())).decode()}
def files(v):
    data={'extension/manifest.json':json.dumps({'version':v,'key':'stable-test-identity','permissions':['storage']}).encode(),
          'runtime/edition.json':b'{"edition":"dev"}', 'runtime/update-channel.json':json.dumps(cfg).encode(),
          'extension/code.js':('version '+v).encode(), 'runtime/bridge.py':b'# new bridge',
          'runtime/config.json':b'{"private":"must not overwrite"}'}
    if v=='1.0.0':data['obsolete.js']=b'old removable module'
    data['update-files.json']=json.dumps({n:u.sha(b) for n,b in data.items() if not u.protected(n)}).encode()
    return data
checks=0
def rejected(fn):
    global checks
    try:fn()
    except (ValueError,KeyError,OSError):checks+=1;return
    raise AssertionError('Expected rejection')
with tempfile.TemporaryDirectory(prefix='ms-update-') as tmp:
    root=Path(tmp)/'Multi-Script';root.mkdir()
    for name,raw in files('1.0.0').items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    private={'runtime/config.json':b'{"account":"keep-secret"}', 'studio-data/skills-state.json':b'private skills',
             'logs/private.log':b'keep log', 'runtime/native_host.bat':b'registered launcher', 'unmanaged-user.txt':b'user content'}
    for name,raw in private.items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    archive=Path(tmp)/'release.zip'
    def make_release(extra=None):
        contents=files('1.1.0');contents.update(extra or {})
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for name,raw in contents.items():z.writestr('Multi-Script/'+name,raw)
        raw=archive.read_bytes()
        data={'product':'Multi-Script','channel':'dev','version':'1.1.0','url':'https://releases.example.test/dev.zip','size':len(raw),'sha256':u.sha(raw)}
        return raw,data,sign(data)
    blob,data,envelope=make_release()
    assert u.verify_envelope(envelope,public)==data;checks+=1
    rejected(lambda:u.verify_envelope({**envelope,'signature':base64.b64encode(b'X'*384).decode()},public))
    rejected(lambda:u.verify_envelope(envelope,{**public,'n':format(pub.n+2,'x')}))
    rejected(lambda:u.verify_envelope(sign({**data,'channel':'public'}),public))
    rejected(lambda:u.verify_envelope(sign({**data,'url':'http://insecure.test/a.zip'}),public))
    rejected(lambda:u.verify_envelope(sign({**data,'size':u.MAX_ZIP+1}),public))
    for path in ['../escape','C:/escape','a\\b','/absolute','a/../b','aux.txt','a./code.js','a//b','a:stream']:
        rejected(lambda p=path:u.safe_path(root,p))
    for v in ['1.0-beta','1.70000','1.0.0.0.1','-1','1..0']:
        rejected(lambda value=v:u.version(value))
    updater=u.Updater(root)
    with patch.object(u,'download',side_effect=lambda url,limit,**kwargs:json.dumps(envelope).encode() if url.endswith('.json') else blob):
        assert updater.check()['staged']=='1.1.0'
        (updater.home/'release.zip').write_bytes(b'corrupt cached download')
        assert updater.check()['staged']=='1.1.0'
        assert (updater.home/'release.zip').read_bytes()==blob;checks+=1
        (updater.home/'staged.json').write_bytes(b'interrupted metadata')
        assert updater.status()['staged'] is None
        assert updater.check()['staged']=='1.1.0';checks+=1
    assert not (updater.home/'transaction.json').exists();checks+=1
    # Verify release changed neither private data nor installed code at staging.
    assert (root/'extension/code.js').read_bytes()==b'version 1.0.0'
    for n,raw in private.items():assert (root/n).read_bytes()==raw
    checks+=1
    (root/'extension/code.js').write_bytes(b'local change')
    rejected(updater.apply)
    assert (root/'extension/code.js').read_bytes()==b'local change'
    (root/'extension/code.js').write_bytes(b'version 1.0.0')
    # Fail after real writes; rollback restores every managed path and old index.
    replace=updater._replace;counter=[0]
    def fail_once(name,raw):
        counter[0]+=1
        if counter[0]==3:raise OSError('simulated disk failure')
        return replace(name,raw)
    with patch.object(updater,'_replace',side_effect=fail_once):rejected(updater.apply)
    assert (root/'extension/code.js').read_bytes()==b'version 1.0.0'
    assert json.loads((root/'extension/manifest.json').read_text())['version']=='1.0.0'
    assert (root/'obsolete.js').exists() and not updater.journal.exists();checks+=1
    # Abrupt termination (BaseException skips ordinary rollback) + restart recovery.
    counter[0]=0
    def crash(name,raw):
        counter[0]+=1
        if counter[0]==3:raise KeyboardInterrupt('simulated killed process')
        return replace(name,raw)
    try:
        with patch.object(updater,'_replace',side_effect=crash):updater.apply()
    except KeyboardInterrupt:pass
    assert updater.status()['recoveryRequired']
    (root/'extension/code.js.ms-update-tmp').write_bytes(b'interrupted atomic write')
    assert updater.recover()['recovered']
    assert not (root/'extension/code.js.ms-update-tmp').exists()
    assert (root/'extension/code.js').read_bytes()==b'version 1.0.0';checks+=1
    assert updater.apply()['installed']=='1.1.0'
    assert (root/'extension/code.js').read_bytes()==b'version 1.1.0'
    assert not (root/'obsolete.js').exists()
    for n,raw in private.items():assert (root/n).read_bytes()==raw
    assert updater.status()['staged'] is None;checks+=1
    rejected(updater.apply)
    # Signed archive identity/path/permission/index failures.
    for extra in [
      {'../escape':b'bad'},
      {'extension/manifest.json':b'{"version":"1.1.0","key":"other"}'},
      {'extension/manifest.json':b'{"version":"1.1.0","key":"stable-test-identity","permissions":["storage","management"]}'},
      {'runtime/edition.json':b'{"edition":"public"}'},
      {'extension/unindexed.js':b'bad'},
      {'extension/code.js':b'modified-after-hashing'},
      {'runtime/evil-state.json':b'protected'}
    ]:
        raw,meta,env=make_release(extra)
        # Protected ignored extras are not installed; all code changes fail.
        if 'runtime/evil-state.json' in extra:
            assert 'runtime/evil-state.json' not in updater.inspect(archive,meta);checks+=1
        else:rejected(lambda:updater.inspect(archive,meta))
    # Native endpoint refuses an active bridge and never accepts arbitrary verbs.
    import native_host
    with patch.object(native_host,'ROOT',str(root)),patch.object(native_host,'port_listening',return_value=True):
        assert not native_host.handle({'cmd':'update','action':'apply'})['ok'];checks+=1
    assert not native_host.handle({'cmd':'update','action':'shell'})['ok'];checks+=1
    # Exercise the actual publisher CLI against this exact archive and key.
    import subprocess
    from cryptography.hazmat.primitives import serialization
    key_file=Path(tmp)/'publisher-key.pem'
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    config_file=Path(tmp)/'publisher-channel.json';config_file.write_text(json.dumps(cfg))
    signed_file=Path(tmp)/'signed-feed.json'
    make_release()
    subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'tools/sign_update.py'),'--key',str(key_file),'--config',str(config_file),'--archive',str(archive),'--archive-url','https://releases.example.test/dev.zip','--output',str(signed_file)],check=True,capture_output=True)
    signed=u.verify_envelope(u.read_json(signed_file),public)
    assert signed['sha256']==u.sha(archive.read_bytes()) and signed['version']=='1.1.0';checks+=1
print(f'PASS {checks} signed metadata, path/identity/permissions, staging, local-edit protection, real apply, disk-failure rollback, killed-process recovery, obsolete-file removal and private-data preservation checks.')
