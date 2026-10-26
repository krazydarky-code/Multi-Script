#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build current Dev with the unchanged Public companion in one bundle.

python tools/build_release.py --output release --public-archive /path/to/Multi-Script-6.42.0-Public.zip
Public is checked against release-policy.json and never rebuilt from Dev source.
"""
from pathlib import Path
import argparse, hashlib, json, shutil, subprocess, sys, zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'runtime'))
from update_manager import protected
VERSION = json.loads((ROOT/'extension/manifest.json').read_text(encoding='utf-8'))['version']
SKIP_PARTS = {'.git','__pycache__','logs','generated','release','studio-data','node_modules','.venv','venv','.media-relay','test-results','Multi-Script Memory'}
PRIVATE_NAMES = {'.env','.workshop-connection.json','workspace-state.json','memory-graph.json','critic-loop-report.json','engine-compatibility-audit.json','bridge_debug.log','com.multiscript.bridge.json','native_host.bat','native_host.sh','engine-prefs.json','update-files.json'}


def include(p):
    rel = p.relative_to(ROOT)
    return p.is_file() and not any(x.casefold() in {part.casefold() for part in SKIP_PARTS} for x in rel.parts) and p.name not in PRIVATE_NAMES and p.suffix.lower() not in {'.pyc','.zip','.sqlite3','.db','.log','.pem','.key','.pfx','.p12'} and not p.name.endswith(('.sqlite3-wal','.sqlite3-shm','-state.json')) and not any(x.startswith('.') and x not in {'.github','.gitignore','.env.example'} for x in rel.parts)


def version_tuple(version):
    parts = str(version).split('.')
    if not 1 <= len(parts) <= 4 or not all(p.isdigit() and 0 <= int(p) <= 65535 for p in parts):
        raise ValueError('Invalid extension version: '+str(version))
    return tuple(map(int,parts))+(0,)*(4-len(parts))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_entry(archive,name,data,executable=False):
    info = zipfile.ZipInfo(name,(2026,10,16,12,0,0))
    info.external_attr = (0o755 if executable else 0o644)<<16
    archive.writestr(info,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)


def write_zip(path,files):
    caps = {'maxPayloadBytes':None,'maxCommandSeconds':None,'background':True}
    managed = {}
    with zipfile.ZipFile(path,'w') as archive:
        for p,arc in sorted(files,key=lambda x:x[1]):
            data = p.read_bytes()
            if arc=='runtime/edition.json':
                data = (json.dumps({'edition':'dev','workspace':caps},indent=2)+'\n').encode()
            elif arc=='extension/core/build-edition.js':
                data = ('// SPDX-License-Identifier: GPL-3.0-or-later\nconst MSBuild = Object.freeze('+json.dumps({'edition':'dev',**caps})+');\n').encode()
            elif arc=='runtime/config.json':
                data = (ROOT/'runtime/config.example.json').read_bytes()
            write_entry(archive,'Multi-Script/'+arc,data,p.suffix in {'.command','.py','.sh'})
            if not protected(arc):
                managed[arc] = hashlib.sha256(data).hexdigest()
        write_entry(archive,'Multi-Script/update-files.json',(json.dumps(managed,indent=2)+'\n').encode())


def check_archive(path,edition,version):
    with zipfile.ZipFile(path) as archive:
        if archive.testzip():
            raise ValueError('Archive CRC verification failed: '+path.name)
        names = archive.namelist()
        if len(set(names))!=len(names) or any('/studio-data/' in n or n.endswith('/.env') or '.workshop-connection' in n for n in names):
            raise ValueError('Duplicate or private entries in '+path.name)
        actual = json.loads(archive.read('Multi-Script/runtime/edition.json'))
        manifest = json.loads(archive.read('Multi-Script/extension/manifest.json'))
        if actual.get('edition')!=edition or manifest.get('version')!=version:
            raise ValueError('Edition/version mismatch: '+path.name)
        return manifest


def validate_public(path,policy,version):
    frozen = policy['publicCompanion']
    if policy.get('primaryEdition')!='dev' or policy.get('publicBuild')!='frozen':
        raise ValueError('Release policy must keep Dev primary and Public frozen')
    if version_tuple(version)<=version_tuple(frozen['version']):
        raise ValueError('Dev must be newer than the frozen Public companion')
    if not path.is_file():
        raise ValueError('Frozen Public archive missing; provide --public-archive '+frozen['file'])
    if digest(path)!=frozen['sha256']:
        raise ValueError('Frozen Public checksum mismatch; the companion will not be replaced')
    check_archive(path,'public',frozen['version'])
    return frozen


def artifact(path,edition,version,**extra):
    return {'file':path.name,'edition':edition,'version':version,'bytes':path.stat().st_size,'sha256':digest(path),**extra}


def publishing_note(dev,bundle):
    cfg_path=ROOT/'runtime/update-channel.json'
    cfg=json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    configured=bool(cfg.get('publicKey'))
    repository=cfg.get('feedUrl','').split('/releases/',1)[0]
    if configured:
        return f"""Multi-Script {VERSION}: publishing and updating

Official repository: {repository}
Normal release flow: raise version and merge tested changes into main. Successful
CI triggers Publish Dev release when MS_AUTOPUBLISH is enabled. It builds/signs/verifies draft assets and publishes
the latest release/feed. No manual upload or signing command is needed.

Current release: v{VERSION}
Dev: {dev.name}
Bundle: {bundle.name}
Public 6.42.0 stays frozen. Private signing keys never belong in this bundle.

Users install this configured Dev build manually once, preserving private config
and the same browser profile. Later: Settings > Help > Updates > Apply & reload
extension, then refresh provider tabs. Stop sessions and save drafts first.

Full user steps, recovery and publisher fallback: Multi-Script/docs/UPDATES.md.
"""
    return f"Multi-Script {VERSION}: update hosting is not configured. See Multi-Script/docs/UPDATES.md before publishing.\n"


def build(output,public_archive,policy):
    frozen = validate_public(public_archive,policy,VERSION)
    output.mkdir(parents=True,exist_ok=True)
    public = output/frozen['file']
    if public.exists() and digest(public)!=frozen['sha256']:
        raise ValueError('Refusing to overwrite a different Public archive: '+str(public))
    files = [(p,p.relative_to(ROOT).as_posix()) for p in ROOT.rglob('*') if include(p) and not p.is_relative_to(output.resolve())]
    dev = output/f'Multi-Script-{VERSION}-Dev.zip'
    temporary = dev.with_suffix('.zip.tmp')
    try:
        write_zip(temporary,files)
        current_manifest = check_archive(temporary,'dev',VERSION)
        old_manifest = check_archive(public_archive,'public',frozen['version'])
        if current_manifest.get('key')!=old_manifest.get('key'):
            raise ValueError('Dev and Public must retain the same stable extension key')
        temporary.replace(dev)
    finally:
        temporary.unlink(missing_ok=True)
    if not public.exists():
        shutil.copyfile(public_archive,public)
    artifacts = [artifact(dev,'dev',VERSION,primary=True),artifact(public,'public',frozen['version'],primary=False,frozen=True)]
    manifest = {'product':'Multi-Script','version':VERSION,'primaryEdition':'dev','releasePolicy':'Dev advances; Public is a frozen companion, never rebuilt automatically.','artifacts':artifacts,
                'providerVerification':'Multi-Script/docs/PROVIDER_QA_6.41.md','workspaceVerification':'Multi-Script/docs/QA_6.50.0.md','workshopSetup':'Multi-Script/docs/WORKSHOP.md','updateSetup':'Multi-Script/docs/UPDATES.md','updateConfigured':bool(json.loads((ROOT/'runtime/update-channel.json').read_text()).get('feedUrl')) if (ROOT/'runtime/update-channel.json').exists() else False}
    sums = lambda items:'\n'.join(f"{x['sha256']}  {x['file']}" for x in items)+'\n'
    bundle = output/f'Multi-Script-{VERSION}-Bundle.zip'
    publish = publishing_note(dev,bundle)
    (output/f'Multi-Script-{VERSION}-Publishing.txt').write_text(publish,encoding='utf-8')
    guide = ROOT/'docs/UPDATES.md'
    if guide.is_file():
        (output/f'Multi-Script-{VERSION}-Update-Guide.md').write_bytes(guide.read_bytes())
    tutorial = ROOT/'docs/DISCORD_PHONE_TUTORIAL.md'
    if tutorial.is_file():
        (output/f'Multi-Script-{VERSION}-Discord-Phone-Tutorial.md').write_bytes(tutorial.read_bytes())
    note = f'''Multi-Script {VERSION}\n\nInstall {dev.name}: Dev is the primary, current edition.\n{public.name} is the unchanged Public {frozen['version']} companion. It does not contain the latest fixes.\n\nExtract ONE edition to a permanent folder. Run Setup.bat (Windows), Setup.sh or MacOS_Setup.command. Load that edition's extension folder, reload provider tabs and restart the bridge. Do not mix editions or run both together. Keep your existing private studio-data and browser profile when upgrading.\n\nDev release verification: Multi-Script/docs/QA_6.50.0.md inside the Dev ZIP.\nChecksums in this bundle cover both inner archives.\n\nUpdates: Multi-Script/docs/UPDATES.md explains GitHub setup once and publishing each later version. This configured Dev build pins the official GitHub update feed/public key. Older/unconfigured installs need a manual upgrade once. Users keep the same permanent install and browser profile, then use Settings > Help > Updates > Apply & reload and refresh provider tabs. Never uninstall to update.\n'''
    temporary_bundle = bundle.with_suffix('.zip.tmp')
    try:
        with zipfile.ZipFile(temporary_bundle,'w') as archive:
            for p in (dev,public):
                write_entry(archive,p.name,p.read_bytes())
            write_entry(archive,'START-HERE.txt',note.encode())
            write_entry(archive,'PUBLISHING.txt',publish.encode())
            if guide.is_file():write_entry(archive,'UPDATE-GUIDE.md',guide.read_bytes())
            if tutorial.is_file():write_entry(archive,'DISCORD-PHONE-TUTORIAL.md',tutorial.read_bytes())
            write_entry(archive,'release-manifest.json',(json.dumps(manifest,indent=2)+'\n').encode())
            write_entry(archive,'SHA256SUMS.txt',sums(artifacts).encode())
        with zipfile.ZipFile(temporary_bundle) as archive:
            if archive.testzip() or any(hashlib.sha256(archive.read(p.name)).hexdigest()!=digest(p) for p in (dev,public)):
                raise ValueError('Combined bundle integrity check failed')
        temporary_bundle.replace(bundle)
    finally:
        temporary_bundle.unlink(missing_ok=True)
    manifest['bundle'] = artifact(bundle,'bundle',VERSION)
    (output/'release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    (output/'SHA256SUMS.txt').write_text(sums(artifacts+[manifest['bundle']]),encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'release')
    parser.add_argument('--public-archive',type=Path,help='Previously released Public ZIP; preserved exactly')
    args = parser.parse_args()
    policy = json.loads((ROOT/'release-policy.json').read_text(encoding='utf-8'))
    public = args.public_archive or args.output/policy['publicCompanion']['file']
    validate_public(public,policy,VERSION)
    subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/release_check.py')],check=True)
    print(json.dumps(build(args.output.resolve(),public.resolve(),policy),indent=2))


if __name__=='__main__':
    main()
