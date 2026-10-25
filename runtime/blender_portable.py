# SPDX-License-Identifier: GPL-3.0-or-later
"""Discover Blender or prepare a verified, per-user portable Windows runtime.

No administrator rights, registry edits, add-on install or TLS bypass. The
runtime cache lives outside releases; projects live in protected studio-data.
"""
from pathlib import Path,PurePosixPath
import contextlib,hashlib,json,os,platform,re,shutil,stat,subprocess,tempfile,time,urllib.request,urllib.error,zipfile

HERE=Path(__file__).resolve().parent
MANIFEST=json.loads((HERE/'blender-runtime.json').read_text())
HIDDEN={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def platform_id():
    return 'windows-'+('arm64' if platform.machine().lower() in ('arm64','aarch64') else 'x64') if os.name=='nt' else platform.system().lower()

def cache_root():
    return Path(os.environ.get('MS_BLENDER_CACHE') or (Path(os.environ.get('LOCALAPPDATA',Path.home()/'.cache'))/'Multi-Script'/'engines'/'Blender')).expanduser().resolve()

def portable_dir():return cache_root()/(MANIFEST['version']+'-'+platform_id())

def discover():
    configured=os.environ.get('MS_BLENDER_PATH','').strip()
    candidates=[Path(configured)] if configured else []
    found=shutil.which('blender')
    if found:candidates.append(Path(found))
    if os.name=='nt':
        candidates+=sorted(Path(os.environ.get('ProgramFiles','C:/Program Files'),'Blender Foundation').glob('Blender */blender.exe'),reverse=True)
    elif platform.system()=='Darwin':candidates+=[Path('/Applications/Blender.app/Contents/MacOS/Blender')]
    for p in candidates:
        if p.is_file():
            try:
                info=subprocess.run([str(p),'--version'],capture_output=True,text=True,timeout=15,**HIDDEN);version=re.search(r'Blender (\d+)\.(\d+)',info.stdout)
                if info.returncode==0 and version and tuple(map(int,version.groups()))>=(4,5):return str(p.resolve())
            except (OSError,subprocess.TimeoutExpired):pass
    if configured:raise RuntimeError('MS_BLENDER_PATH must point to a working Blender 4.5 or newer executable.')
    folder=portable_dir();receipt=folder/'runtime-receipt.json'
    try:
        info=json.loads(receipt.read_text());p=folder/info['executable']
        if p.resolve().is_relative_to(folder.resolve()) and p.is_file() and digest(p)==info['executableSha256']:return str(p.resolve())
    except (OSError,ValueError,KeyError):pass
    return None

@contextlib.contextmanager
def install_lock(root):
    root.mkdir(parents=True,exist_ok=True)
    with (root/'prepare.lock').open('a+b') as f:
        if not f.tell():f.write(b'0');f.flush()
        f.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as e:raise RuntimeError('Blender preparation is already running in another Multi-Script process.') from e
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f,fcntl.LOCK_UN)

def extract_verified(archive,stage,filename):
    stage=Path(stage).resolve();prefix=filename.removesuffix('.zip')
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist()
        if len(infos)>100000 or sum(i.file_size for i in infos)>3_000_000_000:raise ValueError('Blender archive exceeds extraction limits.')
        for item in infos:
            rel=PurePosixPath(item.filename)
            if '\\' in item.filename or rel.is_absolute() or '..' in rel.parts or not rel.parts or rel.parts[0]!=prefix or any(':' in p for p in rel.parts):raise ValueError('Unsafe archive path.')
            if stat.S_ISLNK(item.external_attr>>16):raise ValueError('Archive symbolic links are unsupported.')
            target=stage.joinpath(*rel.parts)
            if not target.resolve().is_relative_to(stage):raise ValueError('Archive escaped its staging folder.')
        z.extractall(stage)
    exe=stage/prefix/'blender.exe'
    if not exe.is_file():raise ValueError('Verified archive did not contain Blender.')
    return exe

def prepare(progress=lambda **x:None,cancelled=lambda:False,archive=None):
    existing=discover()
    if existing:progress(phase='ready',message='Blender is ready.',percent=100);return existing
    pid=platform_id();spec=MANIFEST['platforms'].get(pid)
    if not spec:raise RuntimeError('Install Blender 4.5 LTS or newer, or set MS_BLENDER_PATH. Automatic portable preparation currently supports Windows x64/ARM64.')
    root=cache_root();root.mkdir(parents=True,exist_ok=True)
    with install_lock(root):
        existing=discover()
        if existing:return existing
        if shutil.disk_usage(root).free<2_200_000_000:raise RuntimeError('Blender needs about 2.2 GB of free space for download and extraction.')
        download=Path(archive) if archive else root/(spec['file']+'.download')
        if not archive:
            progress(phase='downloading',message='Preparing portable Blender 4.5 LTS…',totalBytes=spec['bytes'],downloadedBytes=0,percent=0)
            url='https://mirror.blender.org/release/Blender4.5/'+spec['file']
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Multi-Script-Blender'}),timeout=30) as r,download.open('wb') as f:
                    while True:
                        if cancelled():raise InterruptedError('Blender preparation cancelled.')
                        chunk=r.read(1024*1024)
                        if not chunk:break
                        f.write(chunk);size=f.tell()
                        if size>spec['bytes']:raise ValueError('Blender download exceeds its pinned size.')
                        progress(downloadedBytes=size,percent=min(80,round(size/spec['bytes']*80)))
            except (OSError,urllib.error.URLError):
                # Native curl uses the OS certificate store. Verification remains
                # enabled; the independently pinned digest is checked below too.
                curl=shutil.which('curl.exe' if os.name=='nt' else 'curl')
                if not curl:raise
                proc=subprocess.Popen([curl,'--silent','--show-error','--fail','--location','--proto','=https','--proto-redir','=https','--connect-timeout','20','--max-time','1200','--output',str(download),url],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,**HIDDEN)
                while proc.poll() is None:
                    if cancelled():proc.terminate();proc.wait(timeout=10);raise InterruptedError('Blender preparation cancelled.')
                    size=download.stat().st_size if download.exists() else 0
                    if size>spec['bytes']:proc.terminate();proc.wait(timeout=10);raise ValueError('Blender download exceeds its pinned size.')
                    progress(downloadedBytes=size,percent=min(80,round(size/spec['bytes']*80)));time.sleep(.2)
                if proc.returncode:raise RuntimeError('Verified HTTPS Blender download failed: '+proc.stderr.read(2000).decode(errors='replace'))
        progress(phase='verifying',message='Verifying the Blender download…',percent=82)
        if download.stat().st_size!=spec['bytes'] or digest(download)!=spec['sha256']:raise ValueError('Blender checksum verification failed. The runtime was not installed.')
        if cancelled():raise InterruptedError('Blender preparation cancelled.')
        stage=Path(tempfile.mkdtemp(prefix='prepare-',dir=root)).resolve()
        try:
            progress(phase='extracting',message='Unpacking portable Blender…',percent=88)
            exe=extract_verified(download,stage,spec['file']);dest=portable_dir()
            if dest.exists():raise RuntimeError('A partial Blender cache already exists. Choose an installed Blender through MS_BLENDER_PATH or remove only that incomplete cache folder.')
            rel=exe.relative_to(stage);receipt={'version':MANIFEST['version'],'archiveSha256':spec['sha256'],'executable':rel.as_posix(),'executableSha256':digest(exe)}
            (stage/'runtime-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
            os.replace(stage,dest)
        finally:
            if stage.exists():
                assert stage.is_relative_to(root.resolve()) and stage.name.startswith('prepare-')
                shutil.rmtree(stage)
        if not archive:download.unlink(missing_ok=True)
        progress(phase='ready',message='Blender is ready.',percent=100)
        return str(dest/rel)

if __name__=='__main__':
    print(prepare(progress=lambda **x:print(x.get('message',''),flush=True) if x.get('message') else None))
