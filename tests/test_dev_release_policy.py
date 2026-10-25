# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise real archives: frozen Public bytes, Dev versions, clean data and bundles."""
import copy, hashlib, importlib.util, json, tempfile, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release_builder',ROOT/'tools/build_release.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

def reject(fn,message):
    try:fn()
    except ValueError as error:assert message in str(error),str(error)
    else:raise AssertionError('Expected release rejection: '+message)

with tempfile.TemporaryDirectory() as directory:
    base=Path(directory);source=base/'source';source.mkdir();out=source/'custom-output'
    for name,data in {
        'extension/manifest.json':json.dumps({'version':'6.42.1','key':'stable-test-key'}),
        'extension/core/build-edition.js':'must be generated',
        'runtime/edition.json':'{}','runtime/config.example.json':'{"mcpServers":{}}',
        'runtime/config.json':'private installed config','README.md':'Current development source',
        'runtime/studio-data/private.txt':'private','runtime/.env':'private',
        'runtime/.workshop-connection.json':'private','runtime/com.multiscript.bridge.json':'private local path',
        'runtime/native_host.bat':'private local path','runtime/sessions.sqlite3':'private',
        'runtime/agent-state.json':'private','logs/debug.log':'private','node_modules/test.js':'private',
        'runtime/engine-prefs.json':'private local engine selection',
    }.items():
        p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data,encoding='utf-8')
    public=base/'public.zip'
    def make_public(edition='public',key='stable-test-key'):
        with zipfile.ZipFile(public,'w') as archive:
            archive.writestr('Multi-Script/extension/manifest.json',json.dumps({'version':'6.42.0','key':key}))
            archive.writestr('Multi-Script/runtime/edition.json',json.dumps({'edition':edition}))
            archive.writestr('Multi-Script/README.md','Frozen Public source stays untouched')
    make_public();original=public.read_bytes()
    policy={'primaryEdition':'dev','publicBuild':'frozen','publicCompanion':{'version':'6.42.0','file':'Multi-Script-6.42.0-Public.zip','sha256':b.digest(public)}}
    b.ROOT=source;b.VERSION='6.42.1'
    manifest=b.build(out,public,policy)
    assert manifest['primaryEdition']=='dev'
    dev=out/'Multi-Script-6.42.1-Dev.zip';frozen=out/policy['publicCompanion']['file']
    assert frozen.read_bytes()==original==public.read_bytes()
    assert not (out/'Multi-Script-6.42.1-Public.zip').exists()
    with zipfile.ZipFile(dev) as archive:
        assert set(archive.namelist())=={'Multi-Script/'+name for name in ['extension/manifest.json','extension/core/build-edition.js','runtime/edition.json','runtime/config.example.json','runtime/config.json','README.md','update-files.json']}
        managed=json.loads(archive.read('Multi-Script/update-files.json'))
        assert 'runtime/config.json' not in managed
        assert all(hashlib.sha256(archive.read('Multi-Script/'+name)).hexdigest()==value for name,value in managed.items())
        assert archive.read('Multi-Script/runtime/config.json')==archive.read('Multi-Script/runtime/config.example.json')
        assert json.loads(archive.read('Multi-Script/runtime/edition.json'))=={'edition':'dev','workspace':{'maxPayloadBytes':None,'maxCommandSeconds':None,'background':True}}
    with zipfile.ZipFile(out/manifest['bundle']['file']) as archive:
        assert archive.testzip() is None
        assert archive.read(frozen.name)==original and archive.read(dev.name)==dev.read_bytes()
        assert 'Install '+dev.name in archive.read('START-HERE.txt').decode()
        assert json.loads(archive.read('release-manifest.json'))['artifacts']==manifest['artifacts']
    first=dev.read_bytes();bundle=(out/manifest['bundle']['file']).read_bytes()
    # Repeated packaging excludes its own output and stays deterministic.
    b.build(out,public,policy)
    assert dev.read_bytes()==first and (out/manifest['bundle']['file']).read_bytes()==bundle
    reject(lambda:b.validate_public(public,policy,'6.42.0'),'Dev must be newer')
    reject(lambda:b.validate_public(public,policy,'6.41.9'),'Dev must be newer')
    reject(lambda:b.validate_public(base/'absent.zip',policy,'6.42.1'),'missing')
    public.write_bytes(b'changed')
    reject(lambda:b.build(out,public,policy),'checksum mismatch')
    assert dev.read_bytes()==first and frozen.read_bytes()==original
    make_public('dev');wrong=copy.deepcopy(policy);wrong['publicCompanion']['sha256']=b.digest(public)
    reject(lambda:b.build(out,public,wrong),'Edition/version mismatch')
    make_public(key='different-key');wrong['publicCompanion']['sha256']=b.digest(public)
    # Use a clean output to reach the stable identity check.
    reject(lambda:b.build(base/'wrong-key-output',public,wrong),'stable extension key')
    public.write_bytes(original);frozen.write_bytes(b'conflicting local archive')
    reject(lambda:b.build(out,public,policy),'Refusing to overwrite')
    assert frozen.read_bytes()==b'conflicting local archive' and dev.read_bytes()==first
    assert b.version_tuple('6.42.10')>b.version_tuple('6.42.9')
print('PASS Dev-first release policy: deterministic Dev/bundle, frozen Public bytes/checksum, newer version, stable identity, no private/generated data and safe rejection paths.')
