# SPDX-License-Identifier: GPL-3.0-or-later
"""Signed, settings-preserving updates for the registered unpacked Dev install.

Only the native host calls this module. No model tool exposes it. The publisher
pins a release key/feed in update-channel.json; empty configuration fails closed.
Browser-managed installs must use their store instead of this filesystem path.
"""
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import time
import urllib.parse
import urllib.request
import urllib.error
import http.client
import socket
import email.utils
import math
import subprocess
import sys
import zipfile
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[1]
MAX_ZIP = 80 * 1024 * 1024
MAX_EXPANDED = 300 * 1024 * 1024
PRIVATE = {'config.json', '.env', 'engine-prefs.json', 'native_host.bat', 'native_host.sh',
           'com.multiscript.bridge.json', 'workspace-state.json', 'memory-graph.json'}
PRIVATE_PARTS = {'studio-data', 'logs', 'generated', '.git', '.updates', 'node_modules', '.venv', 'Multi-Script Memory'}


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,5}(?:\.\d{1,5}){0,3}', value):
        raise ValueError('Invalid release version')
    out = tuple(int(x) for x in value.split('.'))
    if any(x > 65535 for x in out):
        raise ValueError('Invalid release version')
    return out + (0,) * (4 - len(out))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('w', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def safe_path(root, name):
    p = PurePosixPath(name)
    if not isinstance(name, str) or not name or '\\' in name or ':' in name or p.is_absolute() or any(x in ('', '.', '..') or x.endswith((' ', '.')) for x in name.split('/')):
        raise ValueError('Unsafe release path')
    if any(re.fullmatch(r'(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?', x, re.I) for x in p.parts):
        raise ValueError('Reserved release path')
    target = Path(root).joinpath(*p.parts)
    for ancestor in (target, *target.parents):
        if ancestor == Path(root).parent:
            break
        if ancestor.is_symlink() or (hasattr(ancestor, 'is_junction') and ancestor.is_junction()) or (ancestor.exists() and getattr(ancestor.stat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Links/reparse points are not update targets')
    if not target.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('Update target escaped installation')
    return target


def protected(name):
    p = PurePosixPath(name)
    return any(x.casefold() in {part.casefold() for part in PRIVATE_PARTS} or x.startswith('.') for x in p.parts) or p.name.casefold() in PRIVATE or p.name.endswith(('-state.json', '.pem', '.key', '.db', '.sqlite3', '.log'))


def https(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.fragment:
        raise ValueError('Update URLs must be HTTPS without credentials or fragments')
    return url


class SecureRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class DownloadDeferred(ValueError):
    def __init__(self,message,retry_at):
        super().__init__(message)
        self.retry_at=retry_at


def host_cooldown(error,now=None):
    now=time.time() if now is None else now
    headers={str(k).lower():str(v) for k,v in (error.headers or {}).items()}
    retry=headers.get('retry-after','');retry_at=0
    if retry:
        try:retry_at=now+max(0,float(retry))
        except (ValueError,OverflowError):
            try:retry_at=email.utils.parsedate_to_datetime(retry).timestamp()
            except (ValueError,TypeError,OverflowError):pass
    if headers.get('x-ratelimit-remaining')=='0':
        try:retry_at=max(retry_at,float(headers.get('x-ratelimit-reset','0')))
        except (ValueError,OverflowError):pass
    if not math.isfinite(retry_at):retry_at=now+86400
    rate=error.code==429 or (error.code==403 and (bool(retry) or headers.get('x-ratelimit-remaining')=='0'))
    if rate:return DownloadDeferred('Update hosting rate-limited this check. Automatic requests are paused until the server cooldown expires.',max(now+60,retry_at))
    if error.code in (401,403,404,410):
        return DownloadDeferred(f'Update hosting refused access or is unavailable (HTTP {error.code}). Verify the public repository/feed; automatic requests pause for 24 hours.',max(now+86400,retry_at))
    return None


def download(url, limit, *, progress=None):
    """Bounded HTTPS reads; retry transient transport failures, never bad content."""
    deadline = time.monotonic() + 90
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(https(url), headers={'User-Agent': 'Multi-Script-Updater/2', 'Accept-Encoding': 'identity'})
            with urllib.request.build_opener(SecureRedirect()).open(req, timeout=min(25, max(1, deadline-time.monotonic()))) as response:
                https(response.url)
                length = int(response.headers.get('Content-Length', 0))
                if length < 0 or length > limit: raise ValueError('Update exceeds download limit')
                chunks, size = [], 0
                while True:
                    if time.monotonic() > deadline: raise ValueError('Update download timed out; try again on a stable connection')
                    part = response.read(min(65536, limit + 1 - size))
                    if not part: break
                    size += len(part)
                    if size > limit: raise ValueError('Update exceeds download limit')
                    chunks.append(part)
                    if progress: progress({'bytes': size, 'total': length, 'attempt': attempt})
                if length and size != length: raise http.client.IncompleteRead(b'', length-size)
                return b''.join(chunks)
        except urllib.error.HTTPError as error:
            deferred=host_cooldown(error)
            if deferred:raise deferred from error
            if error.code not in (408,429,500,502,503,504): raise
            retry = error.headers.get('Retry-After', '')
            delay = float(retry) if retry.isdigit() else attempt
            if retry and (not retry.isdigit() or delay > 10): raise ValueError('Release server requested a later retry; try again later') from error
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.IncompleteRead, socket.timeout):
            delay = attempt
        if attempt == 3 or time.monotonic()+delay >= deadline:
            raise ValueError('Download interrupted after bounded retries; check your connection and try again')
        if progress: progress({'bytes':0,'total':0,'attempt':attempt+1,'retrying':True})
        time.sleep(delay)


def verify_envelope(envelope, public_key):
    """RSA PKCS#1 v1.5/SHA-256, fixed key policy, constant full-block comparison.
    Private signing uses cryptography in tools/sign_update.py, never this client.
    """
    import hmac
    raw = base64.b64decode(envelope['payload'], validate=True)
    signature = base64.b64decode(envelope['signature'], validate=True)
    n, e = int(public_key['n'], 16), int(public_key['e'])
    if n.bit_length() not in (3072, 4096) or e != 65537 or len(raw) > 16384:
        raise ValueError('Unsupported release key/payload')
    length = (n.bit_length() + 7) // 8
    sig = int.from_bytes(signature, 'big')
    if len(signature) != length or sig >= n:
        raise ValueError('Invalid release signature')
    digest_info = bytes.fromhex('3031300d060960864801650304020105000420') + hashlib.sha256(raw).digest()
    expected = b'\x00\x01' + b'\xff' * (length - len(digest_info) - 3) + b'\x00' + digest_info
    if not hmac.compare_digest(pow(sig, e, n).to_bytes(length, 'big'), expected):
        raise ValueError('Release signature verification failed')
    data = json.loads(raw)
    if data.get('product') != 'Multi-Script' or data.get('channel') != 'dev':
        raise ValueError('Wrong product or channel')
    version(data['version'])
    https(data['url'])
    if not isinstance(data.get('size'), int) or not 0 < data['size'] <= MAX_ZIP or not re.fullmatch('[a-f0-9]{64}', data.get('sha256', '')):
        raise ValueError('Invalid release archive metadata')
    return data


class Updater:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.home = self.root / '.updates'
        safe_path(self.root, '.updates')
        self.home.mkdir(exist_ok=True)
        self.journal = self.home / 'transaction.json'
        self.progress_path = self.home / 'progress.json'
        self._progress_at = 0
        self._progress_phase = None

    def progress(self, phase, message, **counts):
        now = time.monotonic()
        if phase == self._progress_phase == 'downloading' and now-self._progress_at < .2 and not counts.get('retrying'): return
        self._progress_at = now
        self._progress_phase = phase
        write_json(self.progress_path, {'phase':phase,'message':message,'updated':time.time(),**counts})

    def busy(self):
        try:
            with self.lock(): return False
        except (BlockingIOError, PermissionError, OSError): return True


    @contextmanager
    def lock(self):
        # OS lock is released even after a killed/crashed host; no stale PID lock.
        with (self.home / 'lock').open('a+b') as handle:
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                if handle.read(1) == b'':
                    handle.write(b'0'); handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                if os.name == 'nt':
                    handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def config(self):
        cfg = read_json(self.root / 'runtime/update-channel.json')
        if not cfg.get('feedUrl') or not cfg.get('publicKey'):
            raise ValueError('Release hosting is not configured. See docs/UPDATES.md for publisher setup.')
        https(cfg['feedUrl'])
        return cfg

    def status(self):
        current = read_json(self.root / 'extension/manifest.json')['version']
        configured = False
        try:
            self.config(); configured = True
        except (ValueError, OSError, KeyError):
            pass
        try:
            staged = read_json(self.home / 'staged.json')
            if version(staged['version']) <= version(current):
                staged = None
        except (ValueError, OSError, KeyError, TypeError):
            staged = None
        active = self.busy()
        try: progress = read_json(self.progress_path)
        except (ValueError,OSError,TypeError): progress = None
        if not active: progress = None
        try: receipt = read_json(self.home/'last-update.json')
        except (ValueError,OSError): receipt = None
        index_ok = (self.root/'update-files.json').is_file()
        try: setup_required=read_json(self.root/'runtime/product-manifest.json').get('updates',{}).get('postInstallSetup')=='native-host-v1'
        except (ValueError,OSError,TypeError): setup_required=False
        try: setup=read_json(self.home/'setup-complete.json')
        except (ValueError,OSError): setup=None
        setup_pending=setup_required and (not setup or setup.get('version')!=current or os.path.normcase(str(setup.get('root','')))!=os.path.normcase(str(self.root)) or not setup.get('launcherVerified'))
        cooldown=self.hosting_cooldown()
        return {'ok': True, 'configured': configured, 'current': current, 'root': str(self.root), 'staged': staged and staged['version'], 'recoveryRequired': self.journal.exists(), 'channel': 'dev', 'busy':active, 'progress':progress, 'lastUpdate':receipt, 'setupReady':configured and index_ok, 'setupPending':setup_pending,'setupComplete':setup_required and not setup_pending,'setupIssue':None if index_ok else 'Install the complete Dev package; its managed-file index is missing.','nextCheckAt':cooldown.get('retryAt',0)*1000,'lastCheckError':cooldown.get('error')}

    def hosting_cooldown(self,cfg=None):
        try:
            cfg=cfg or self.config();state=read_json(self.home/'host-retry.json');at=state.get('retryAt',0)
            if state.get('feedUrl')==cfg['feedUrl'] and isinstance(at,(int,float)) and math.isfinite(at) and at>time.time():return state
        except (ValueError,OSError,KeyError,TypeError):pass
        return {}

    def setup(self):
        """Run the signed installer's headless setup; never arbitrary release hooks."""
        with self.lock():
            if self.journal.exists(): raise ValueError('Recover the interrupted file transaction before setup')
            state=self.status()
            if not state.get('setupPending'): return state
            self.progress('setting-up','Setting up the updated version: dependencies, launcher and browser registration')
            cfg=self.config()
            try: data=verify_envelope(read_json(self.home/'staged-envelope.json'),cfg['publicKey'])
            except (OSError,ValueError,KeyError) as error: raise ValueError('Run Setup from this complete installed folder once; no signed update proof is available for automatic setup') from error
            if data['version']!=state['current']: raise ValueError('Automatic setup requires signed proof for the currently installed version')
            archive=self.home/'release.zip'
            if archive.stat().st_size!=data['size'] or sha(archive.read_bytes())!=data['sha256']: raise ValueError('Update archive was modified; automatic setup stopped')
            files=self.inspect(archive,data)
            for name,raw in files.items():
                path=safe_path(self.root,name)
                if not path.is_file() or sha(path.read_bytes())!=sha(raw): raise ValueError('Installed code differs from the signed release; run reviewed manual setup instead: '+name)
            installer=safe_path(self.root,'runtime/install_native_host.py')
            if 'runtime/install_native_host.py' not in files: raise ValueError('Signed release has no supported setup entry point')
            logs=safe_path(self.root,'logs');logs.mkdir(exist_ok=True)
            with (logs/'update-setup.log').open('ab') as output:
                process=subprocess.Popen([sys.executable,str(installer),'--post-update','--no-pause','--no-start'],cwd=self.root,stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,start_new_session=os.name!='nt',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0)
                try: code=process.wait(timeout=240)
                except subprocess.TimeoutExpired:
                    if os.name=='nt': subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    else:
                        import signal
                        os.killpg(process.pid,signal.SIGKILL)
                    process.wait();raise ValueError('Setup timed out. See logs/update-setup.log and retry Finish setup.')
            if code or self.status().get('setupPending'): raise ValueError('Updated files are installed, but setup is incomplete. See logs/update-setup.log and retry Finish setup.')
        return {**self.status(),'setupComplete':True}

    def check(self):
        with self.lock():
            cfg=self.config()
            cooldown=self.hosting_cooldown(cfg)
            if cooldown:raise DownloadDeferred(cooldown['error'],cooldown['retryAt'])
            try:result=self._check_release(cfg)
            except DownloadDeferred as error:
                write_json(self.home/'host-retry.json',{'feedUrl':cfg['feedUrl'],'retryAt':error.retry_at,'error':str(error)})
                raise
            (self.home/'host-retry.json').unlink(missing_ok=True)
            return result

    def _check_release(self,cfg):
        if self.journal.exists():
            raise ValueError('An interrupted update needs recovery before checking again')
        if self.status().get('setupPending'): raise ValueError('Finish setup for the installed update before checking another release')
        self.progress('checking', 'Checking the signed release feed')
        envelope = json.loads(download(cfg['feedUrl'], 32768))
        data = verify_envelope(envelope, cfg['publicKey'])
        current = self.status()['current']
        if version(data['version']) <= version(current):
            return {**self.status(), 'available': False}
        if (self.home / 'staged.json').exists():
            try:
                previous = read_json(self.home / 'staged.json')
                version(previous['version'])
            except (ValueError, OSError, KeyError, TypeError):
                previous = None
            if previous and version(data['version']) < version(previous['version']):
                raise ValueError('Release feed rolled back below staged version')
            if data == previous and (self.home / 'release.zip').is_file():
                cached = self.home / 'release.zip'
                if cached.stat().st_size == data['size'] and sha(cached.read_bytes()) == data['sha256']:
                    # Repair a missing/corrupt cached envelope from the freshly
                    # verified feed without downloading identical code again.
                    write_json(self.home / 'staged-envelope.json', envelope)
                    return {**self.status(), 'available': True}
        self.progress('downloading','Downloading verified release metadata target',bytes=0,total=data['size'],version=data['version'])
        blob = download(data['url'], data['size'], progress=lambda counts:self.progress('downloading','Downloading release archive',version=data['version'],**{**counts,'total':data['size']}))
        if len(blob) != data['size'] or sha(blob) != data['sha256']:
            raise ValueError('Release archive checksum/size mismatch')
        self.progress('verifying','Checking archive hash, identity and managed files',version=data['version'])
        archive = self.home / 'download.zip'
        archive.write_bytes(blob)
        try:
            self.inspect(archive, data)
            os.replace(archive, self.home / 'release.zip')
            write_json(self.home / 'staged-envelope.json', envelope)
            write_json(self.home / 'staged.json', data)
        finally:
            archive.unlink(missing_ok=True)
        return {**self.status(), 'available': True}

    def inspect(self, archive, data):
        files, folded, total = {}, set(), 0
        with zipfile.ZipFile(archive) as z:
            if len(z.infolist()) > 4000:
                raise ValueError('Too many release files')
            for entry in z.infolist():
                if entry.is_dir():
                    continue
                if not entry.filename.startswith('Multi-Script/'):
                    raise ValueError('Expected a Dev archive, not a bundle')
                name = entry.filename[len('Multi-Script/'):]
                safe_path(self.root, name)
                if name.casefold() in folded or stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                    raise ValueError('Duplicate, encrypted or linked archive entry')
                folded.add(name.casefold())
                total += entry.file_size
                if total > MAX_EXPANDED or entry.file_size > 40 * 1024 * 1024:
                    raise ValueError('Expanded release exceeds limit')
                files[name] = z.read(entry)
            manifest = json.loads(files['extension/manifest.json'])
            installed = read_json(self.root / 'extension/manifest.json')
            if manifest.get('version') != data['version'] or manifest.get('key') != installed.get('key') or not installed.get('key'):
                raise ValueError('Release version/extension identity mismatch')
            if json.loads((self.root / 'runtime/edition.json').read_text()).get('edition') != 'dev':
                raise ValueError('The frozen Public companion does not receive Dev updates')
            for field in ('permissions', 'host_permissions', 'optional_permissions', 'optional_host_permissions'):
                if set(manifest.get(field, [])) - set(installed.get(field, [])):
                    raise ValueError('New browser permissions require a reviewed manual installation')
            if json.loads(files['runtime/edition.json']).get('edition') != 'dev':
                raise ValueError('Only the current Dev edition can be updated')
            index = json.loads(files['update-files.json'])
            if not isinstance(index, dict) or not index:
                raise ValueError('Missing managed-file index')
            for name, expected in index.items():
                safe_path(self.root, name)
                if protected(name) or name not in files or sha(files[name]) != expected:
                    raise ValueError('Invalid managed file: ' + name)
            if any(not protected(n) and n != 'update-files.json' and n not in index for n in files):
                raise ValueError('Release contains unindexed code')
            return {n: files[n] for n in index} | {'update-files.json': files['update-files.json']}

    def _replace(self, name, data):
        path = safe_path(self.root, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + '.ms-update-tmp')
        if tmp.exists():
            raise ValueError('An update temporary file already exists: ' + name)
        try:
            with tmp.open('xb') as handle:
                handle.write(data); handle.flush(); os.fsync(handle.fileno())
            mode = path.stat().st_mode if path.exists() else (0o755 if path.suffix in {'.py', '.sh', '.command'} else 0o644)
            os.chmod(tmp, mode)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    def _finish_commit(self, transaction):
        write_json(self.home/'last-update.json', {'version':transaction['version'],'at':int(time.time())})
        self.journal.unlink()

    def _recover(self):
        if not self.journal.exists(): return {}
        transaction = read_json(self.journal)
        if transaction.get('phase') == 'committed':
            for name, expected in transaction['after'].items():
                path = safe_path(self.root,name)
                if protected(name) or (expected is None and path.exists()) or (expected is not None and (not path.is_file() or sha(path.read_bytes()) != expected)):
                    raise ValueError('Committed update was changed; preserve .updates for manual recovery')
            self._finish_commit(transaction)
            return {'installed':transaction['version'],'recovered':True}
        # Validate every backup BEFORE touching any installed file.
        backup_data = {}
        for name, old_hash in transaction['before'].items():
            if protected(name): raise ValueError('Unsafe recovery path')
            safe_path(self.root,name)
            if old_hash is not None:
                raw = safe_path(self.home/'backup',name).read_bytes()
                if sha(raw) != old_hash: raise ValueError('Recovery backup is damaged; retained for manual recovery')
                backup_data[name] = raw
        self.progress('recovering','Restoring the previous complete installation')
        for name, old_hash in sorted(transaction['before'].items(),key=lambda item:item[0]=='extension/manifest.json'):
            path = safe_path(self.root,name)
            safe_path(self.root,name+'.ms-update-tmp').unlink(missing_ok=True)
            if old_hash is None: path.unlink(missing_ok=True)
            else:
                self._replace(name,backup_data[name])
                if name in transaction.get('modes',{}): os.chmod(path,transaction['modes'][name])
        self.journal.unlink()
        return {'recovered':True,'rolledBack':True}

    def recover(self):
        with self.lock():
            result = self._recover()
        return {**self.status(),**result,'recovered':True,'reloadRequired':True}

    def apply(self):
        with self.lock():
            if self.journal.exists():
                result=self._recover()
                return {**self.status(),**result,'recovered':True,'reloadRequired':True}
            self.progress('preparing','Validating staged release and installation')
            cfg=self.config()
            data=verify_envelope(read_json(self.home/'staged-envelope.json'),cfg['publicKey'])
            if version(data['version']) <= version(self.status()['current']): raise ValueError('Refusing an old or already installed release')
            archive=self.home/'release.zip'
            if archive.stat().st_size!=data['size'] or sha(archive.read_bytes())!=data['sha256']: raise ValueError('Staged archive was modified; check and download it again')
            files=self.inspect(archive,data);old=read_json(self.root/'update-files.json')
            names=sorted(set(old)|set(files));before={};modes={};backup=self.home/'backup'
            needed=sum(len(raw) for raw in files.values())+8*1024*1024
            for name in names:
                if protected(name): raise ValueError('Private file cannot be managed: '+name)
                path=safe_path(self.root,name)
                if path.exists():
                    raw=path.read_bytes()
                    if name!='update-files.json' and (name not in old or sha(raw)!=old[name]): raise ValueError('Local code was edited; update left untouched: '+name)
                    before[name]=sha(raw);modes[name]=stat.S_IMODE(path.stat().st_mode);needed+=len(raw)
                else: before[name]=None
            if shutil.disk_usage(self.root).free < needed: raise ValueError('Not enough free disk space for update and recovery backup; free space and try again')
            self.progress('backing-up','Backing up managed files; private settings stay in place',totalFiles=len(names),files=0)
            for name,old_hash in before.items():
                if old_hash is not None:
                    raw=safe_path(self.root,name).read_bytes()
                    if sha(raw)!=old_hash: raise ValueError('Local code changed while preparing update; nothing installed: '+name)
                    dest=safe_path(backup,name);dest.parent.mkdir(parents=True,exist_ok=True)
                    with dest.open('wb') as handle: handle.write(raw);handle.flush();os.fsync(handle.fileno())
            transaction={'before':before,'modes':modes,'after':{n:sha(files[n]) if n in files else None for n in names},'version':data['version'],'phase':'applying'}
            write_json(self.journal,transaction)
            committed=False
            try:
                for count,name in enumerate(sorted(names,key=lambda n:n=='extension/manifest.json'),1):
                    self.progress('applying','Installing managed files',files=count,totalFiles=len(names),version=data['version'])
                    if name in files: self._replace(name,files[name])
                    else: safe_path(self.root,name).unlink(missing_ok=True)
                for name,expected in transaction['after'].items():
                    path=safe_path(self.root,name)
                    if (expected is None and path.exists()) or (expected is not None and sha(path.read_bytes())!=expected): raise ValueError('Installed file read-back failed: '+name)
                transaction['phase']='committed';write_json(self.journal,transaction);committed=True
                self._finish_commit(transaction)
            except Exception:
                if not committed: self._recover()
                raise
        if self.status().get('setupPending'): self.setup()
        return {**self.status(),'installed':data['version'],'reloadRequired':True}
