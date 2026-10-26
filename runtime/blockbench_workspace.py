# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional pinned file-based Blockbench MCP runtime; no editor or startup download.

Projects stay under studio-data, separate from disposable runtime dependencies.
Only explicit preparation installs packages, using frozen integrity locks and no
package scripts. Normal launches are offline and stdout stays MCP-only.
"""
from pathlib import Path
import contextlib, hashlib, json, os, platform, shutil, stat, subprocess, threading, time, urllib.request, uuid, zipfile

HERE=Path(__file__).resolve().parent
SOURCE_VERSION='1.10.1'
SOURCE_SHA='328433446ad30c2263415be8c258eb193709dcf604257d2a7e8ab630119d8782'
SOURCE_URL='https://codeload.github.com/jasonjgardner/blockbench-mcp-plugin/zip/refs/tags/v1.10.1'
BUN_VERSION='1.3.8'
BUN_ASSETS={
 ('Windows','x64'):('bun-windows-x64-baseline.zip','74f4dad7b4873ee70f63add9918400334e31acab9ba3fce9ef9906d96646e231'),
 ('Linux','x64'):('bun-linux-x64-baseline.zip','bbe4632ac03d7495177d542ecefa8f21f9849273106525f6bb13172ec8e4ab2c'),
 ('Darwin','x64'):('bun-darwin-x64-baseline.zip','9812e5f6c7f818ef9c491e05a77481ab2e7a4a1580b378526e1611c102fe7ca3'),
 ('Darwin','arm64'):('bun-darwin-aarch64.zip','672a0a9a7b744d085a1d2219ca907e3e26f5579fca9e783a9510a4f98a36212f'),
}
_LOCK=threading.RLock()
_VERIFIED={}

def cache_root():return Path(os.environ.get('MS_BLOCKBENCH_CACHE',str(Path.home()/'.cache/multiscript/blockbench'))).expanduser().resolve()
def project_root():return Path(os.environ.get('MS_BLOCKBENCH_PROJECT_ROOT',str(Path(os.environ.get('MS_STUDIO_DATA_DIR',str(HERE/'studio-data')))/'blockbench-workspace'))).expanduser().resolve()
def _sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()
def _write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8');os.replace(temp,path)
def _locks_digest():
    return hashlib.sha256(b'\0'.join((HERE/'dependencies'/folder/file).read_bytes() for folder in ('blockbench','blockbench-render') for file in ('package.json','package-lock.json'))).hexdigest()
def _record():
    try:
        root=cache_root();record=json.loads((root/'ready.json').read_text(encoding='utf-8'))
        if record.get('revision')!=2 or record.get('sourceSha256')!=SOURCE_SHA or record.get('locksSha256')!=_locks_digest():return None
        for key in ('bun','server','renderer','dispatcher'):
            row=record.get(key)
            if not row:continue
            path=(root/row['file']).resolve()
            if not path.is_relative_to(root) or not path.is_file():return None
            info=path.stat();stamp=(str(path),info.st_size,info.st_mtime_ns,row['sha256'])
            if stamp not in _VERIFIED:
                if _sha(path)!=row['sha256']:return None
                _VERIFIED[stamp]=True
        if not record.get('bun') or not record.get('server') or not record.get('dispatcher'):return None
        return record
    except (OSError,ValueError,KeyError,TypeError):return None
def status():
    record=_record()
    return {'prepared':bool(record),'sourceVersion':SOURCE_VERSION,'backend':'headless-files','workspace':str(project_root()),'renderPrepared':bool(record and record.get('renderer')),'requiresDesktop':False,'connected':False,'connectionPolicy':'Prepared files are not a live MCP connection. Connection status requires a successful handshake and advertised tools.'}

@contextlib.contextmanager
def _install_lock(root):
    root.mkdir(parents=True,exist_ok=True)
    with (root/'prepare.lock').open('a+b') as handle:
        if not handle.tell():handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as error:raise RuntimeError('Blockbench preparation is already running. Wait for that operation; do not repeat it.') from error
        try:yield
        finally:
            handle.seek(0)
            if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle,fcntl.LOCK_UN)

def _download(url,path,digest,limit):
    if path.is_file() and _sha(path)==digest:return path
    part=path.with_name(path.name+'.part');received=0
    request=urllib.request.Request(url,headers={'User-Agent':'Multi-Script/6.50.0 dependency preparation'})
    with urllib.request.urlopen(request,timeout=60) as response,part.open('wb') as output:
        while True:
            data=response.read(1024*1024)
            if not data:break
            received+=len(data)
            if received>limit:raise ValueError('Dependency download exceeded its size bound.')
            output.write(data)
    if _sha(part)!=digest:raise ValueError('Dependency digest mismatch; no downloaded code was executed.')
    os.replace(part,path);return path

def _extract(archive,destination,limit=100_000_000):
    destination=destination.resolve();total=0
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            parts=Path(item.filename).parts
            if '\\' in item.filename or '..' in parts or Path(item.filename).is_absolute() or ':' in item.filename or stat.S_ISLNK(item.external_attr>>16):raise ValueError('Unsafe dependency archive path.')
            target=(destination/item.filename).resolve()
            if not target.is_relative_to(destination):raise ValueError('Dependency extraction escaped its cache.')
            total+=item.file_size
            if total>limit:raise ValueError('Dependency archive exceeds its extracted size bound.')
        bundle.extractall(destination)

def _run(command,cwd,timeout=180):
    kwargs={'creationflags':getattr(subprocess,'CREATE_NO_WINDOW',0)} if os.name=='nt' else {}
    result=subprocess.run(command,cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,**kwargs)
    if result.returncode:raise RuntimeError('Blockbench dependency/build step failed: '+(result.stderr or result.stdout)[-1800:])
    return result.stdout.strip()
def _npm(cwd):
    executable=shutil.which('npm.cmd' if os.name=='nt' else 'npm')
    if not executable:raise RuntimeError('Node.js with npm is required to prepare Blockbench. Existing engines and models were not changed.')
    # A .cmd shim cannot safely be treated as an arbitrary shell command. Invoke
    # npm's own JavaScript entry with Node and a structured argument array.
    node=shutil.which('node')
    cli=Path(executable).parent/'node_modules/npm/bin/npm-cli.js'
    if node and cli.is_file():command=[node,str(cli)]
    elif os.name!='nt':command=[executable]
    else:raise RuntimeError('Cannot locate npm-cli.js beside Node.js; repair the Node installation before preparing Blockbench.')
    return _run(command+['ci','--ignore-scripts','--no-audit','--no-fund'],cwd,240)

def prepare(render=False):
    with _LOCK,_install_lock(cache_root()):
        previous=_record()
        if previous and (not render or previous.get('renderer')):return status()
        root=cache_root();machine=platform.machine().lower();arch='arm64' if machine in ('arm64','aarch64') else 'x64' if machine in ('amd64','x86_64') else machine
        asset,digest=BUN_ASSETS.get((platform.system(),arch),(None,None))
        if not asset:raise RuntimeError('Automatic Blockbench preparation is unavailable on this OS/CPU; configure an existing compatible MCP server instead.')
        archives=root/'archives';archives.mkdir(exist_ok=True)
        source_zip=_download(SOURCE_URL,archives/'source-1.10.1.zip',SOURCE_SHA,15_000_000)
        bun_zip=_download(f'https://github.com/oven-sh/bun/releases/download/bun-v{BUN_VERSION}/{asset}',archives/asset,digest,60_000_000)
        # A fresh generation protects prior working caches and all project files.
        stage=root/('runtime-'+uuid.uuid4().hex[:12]);stage.mkdir()
        _extract(source_zip,stage/'source',30_000_000);_extract(bun_zip,stage/'bun',160_000_000)
        source=stage/'source'/('blockbench-mcp-plugin-'+SOURCE_VERSION)
        bun=next((stage/'bun').rglob('bun.exe' if os.name=='nt' else 'bun'));bun.chmod(0o755)
        for name in ('package.json','package-lock.json'):shutil.copyfile(HERE/'dependencies/blockbench'/name,source/name)
        _npm(source)
        server_source=source/'headless/server.ts';body=server_source.read_text(encoding='utf-8')
        marker='...renderTools, ...appTools]'
        if marker not in body:raise ValueError('Pinned Blockbench adapter patch no longer matches its reviewed source.')
        server_source.write_text(body.replace(marker,'...renderTools]'),encoding='utf-8')
        render_source=source/'headless/tools/render.ts';body=render_source.read_text(encoding='utf-8')
        old='The first render on a machine downloads and installs the render engine\'s packages with npm (three, three-blockbench and Dawn, about 130 MB) into a per-user cache folder; later renders reuse them.'
        if old not in body:raise ValueError('Pinned Blockbench render adapter patch no longer matches.')
        render_source.write_text(body.replace(old,'Prepare rendering explicitly with ms_blockbench_workspace action=prepare render=true. It uses frozen dependencies; normal render calls do not install packages. Node 24+ and a compatible GPU are required.'),encoding='utf-8')
        server=stage/'server.mjs'
        _run([str(bun),'build','headless/index.ts','--target=bun','--outfile',str(server)],source)
        renderer=None
        if render:
            node=shutil.which('node')
            if not node:raise RuntimeError('Node.js 24+ is required for the Blockbench render worker.')
            version=_run([node,'--version'],source).lstrip('v').split('.')
            if tuple(map(int,version[:2]))<(23,6):raise RuntimeError('Node.js 24+ is required for Blockbench rendering; file editing still works with the base runtime.')
            render_home=stage/'render';render_home.mkdir()
            for name in ('package.json','package-lock.json'):shutil.copyfile(HERE/'dependencies/blockbench-render'/name,render_home/name)
            _npm(render_home)
            renderer=render_home/'cli.mjs'
            _run([str(bun),'build','headless/render/engine/cli.ts','--target=node','--external','three','--external','three/*','--external','three-blockbench','--external','@rendergl/*','--outfile',str(renderer)],source)
        dispatcher=root/'renderer.mjs'
        dispatcher_entry=stage/'renderer-entry.mjs'
        dispatcher_entry.write_text('''// Multi-Script: stable render entry; no installer/network/LLM calls.
import {readFileSync,realpathSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {dirname,resolve,sep} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=realpathSync(dirname(fileURLToPath(import.meta.url)));
const record=JSON.parse(readFileSync(resolve(root,'ready.json'),'utf8'));
if(!record.renderer)throw Error('Prepare Blockbench rendering first in Multi-Script Settings → Engines. No packages were installed by this render call.');
const file=realpathSync(resolve(root,record.renderer.file));
const prefix=(root+sep).toLowerCase();
if(!file.toLowerCase().startsWith(prefix))throw Error('Render worker escaped its cache.');
if(createHash('sha256').update(readFileSync(file)).digest('hex')!==record.renderer.sha256)throw Error('Render worker changed; prepare Blockbench rendering again.');
await import(pathToFileURL(file).href);
''',encoding='utf-8')
        os.replace(dispatcher_entry,dispatcher)
        record={'revision':2,'sourceSha256':SOURCE_SHA,'sourceVersion':SOURCE_VERSION,'locksSha256':_locks_digest(),'preparedAt':time.time(),'patches':['File-based tools only; desktop launch and external model-URL tools excluded.','No automatic network installation in a normal launch; explicit frozen dependency preparation.','Stable verified render entry supports explicit preparation without restarting active model sessions.']}
        for name,path in [('bun',bun),('server',server),('renderer',renderer),('dispatcher',dispatcher)]:
            if path:record[name]={'file':path.relative_to(root).as_posix(),'sha256':_sha(path)}
        _write(root/'ready.json',record);return status()

def command():
    record=_record()
    if not record:raise RuntimeError('Blockbench is not prepared. Use Settings → Engines → Prepare Blockbench, or ms_blockbench_workspace action=prepare. No automatic download occurs during bridge startup.')
    root=cache_root();workspace=project_root();workspace.mkdir(parents=True,exist_ok=True)
    args=[str(root/record['bun']['file']),str(root/record['server']['file']),'--root',str(workspace),'--no-web-links','--scratch',str(workspace/'.previews'),'--render-concurrency','1']
    # Supplying a fixed CLI prevents upstream's unpinned first-render installer.
    args+=['--bb-render',str(root/record['dispatcher']['file']),'--node',shutil.which('node') or 'node']
    return args

TOOL={'name':'ms_blockbench_workspace','description':'Prepare or inspect the optional headless Blockbench asset workspace. Explicit prepare downloads checksum-pinned source/Bun and frozen npm dependencies, without changing existing engines or models. render=true also prepares the separate GPU render worker (Node 24+). Native bbmodel_* tools appear only after a real MCP handshake. Models stay in a dedicated workspace; prepared files alone are not a connected editor.', 'inputSchema':{'type':'object','additionalProperties':False,'properties':{'action':{'type':'string','enum':['status','prepare']},'render':{'type':'boolean','default':False}},'required':['action']}}
