# SPDX-License-Identifier: GPL-3.0-or-later
"""Owned Blender projects, a real background worker, and a local preview window."""
from pathlib import Path
import base64,hashlib,json,os,re,secrets,socket,subprocess,threading,time,uuid
import blender_portable
from blender_pipeline import Pipeline

HERE=Path(__file__).resolve().parent
NATIVE_NAMES={'execute_blender_code','get_scene_info','get_object_info','get_viewport_screenshot'}
NATIVE_TOOLS=[{'name':name,'description':description,'inputSchema':{'type':'object','properties':{'project':{'type':'string','description':'Expected Blender Workspace project id.'},**properties},'required':required,'additionalProperties':False}} for name,description,properties,required in [
    ('get_scene_info','Read the selected headless Blender Workspace scene. No desktop Blender add-on is required.',{},[]),
    ('get_object_info','Read an object in the selected headless Blender Workspace.',{'object_name':{'type':'string'}},['object_name']),
    ('execute_blender_code','Execute real bpy code in the selected headless Blender Workspace; edits auto-save the .blend.',{'code':{'type':'string'}},['code']),
    ('get_viewport_screenshot','Return a genuine Blender Workspace Cycles CPU render. Three.js is the separate material viewport preview.',{},[])
]]
PROPERTIES={
    'action':{'type':'string','enum':['status','snapshot','execute','render','export','frame','handoff']},
    'code':{'type':'string','maxLength':200000,'description':'Actual Blender Python; use bpy. Runs with local Python permissions in the selected owned project.'},
    'format':{'type':'string','enum':['blend','glb','fbx']},'frame':{'type':'integer'},
    'size':{'type':'integer','minimum':128,'maximum':1024},
    'project':{'type':'string','description':'Expected project id from status. Prevents editing a project switched by another window.'},
    'engine':{'type':'string','enum':['roblox','unity','godot']},
    'project_path':{'type':'string','description':'For handoff: absolute Unity/Godot project folder. Validated before copying; omit for Roblox.'},
    'name':{'type':'string','maxLength':64,'description':'Handoff asset name, letters/numbers/hyphens/underscores.'},
    'overwrite':{'type':'boolean','description':'Explicitly permit replacing an existing named handoff asset. Defaults false.'}
}
TOOLS=[{'name':'ms_blender_workspace','description':'Real portable headless Blender workspace. Read status/snapshot, execute bpy code, render a genuine Cycles CPU PNG, export blend/GLB/FBX or set the frame. Open and prepare it in Settings → Engines → Blender Workspace first. Existing ms_blender_* tools also work with target=workspace. Edits auto-save the real .blend and refresh the Three.js animation/model preview. Preview is glTF, not exact Blender shader fidelity. Never fabricate execution or captures.',
        'inputSchema':{'type':'object','properties':PROPERTIES,'required':['action'],'additionalProperties':False}}]

class Workspace:
    def __init__(self,root=None,port=17616):
        self.root=Path(root or HERE/'studio-data'/'blender-workspace').resolve();self.port=port
        self.lock=threading.Lock();self.state_lock=threading.RLock();self.proc=None;self.log=None;self.worker_token='';self.worker_port=None
        self.project='';self.ai_target=False;self.server=None;self.phase='idle';self.message='Open a project to start Blender.';self.progress={};self.error='';self.job=None;self.job_thread=None;self.cancel_prepare=False;self.scene={}
        self.launch_keys={};self.sessions={};self.on_change=lambda:None
        self.engines=[];self.engines_at=0;self.engine_enabled=lambda engine:True
        self.last_success=None;self.pipeline=Pipeline(self)
        try:
            state=json.loads((self.root/'state.json').read_text())
            project=state.get('project','') if isinstance(state,dict) else ''
            if project and (self.folder(project)/'project.json').is_file():self.project=project;self.ai_target=bool(state.get('aiTarget'))
            if self.project:
                saved=json.loads((self.folder()/'snapshot.json').read_text())
                if isinstance(saved,dict) and isinstance(saved.get('objects'),list):self.scene=saved
        except (OSError,ValueError,TypeError):pass

    @property
    def running(self):return bool(self.proc and self.proc.poll() is None and self.worker_port)
    @property
    def selected(self):return self.ai_target and self.running
    @property
    def owns_target(self):return bool(self.ai_target and self.project)
    def folder(self,project=None):
        name=project or self.project
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}',str(name)):raise ValueError('Invalid Blender project id.')
        p=(self.root/'projects'/name).resolve()
        if not p.is_relative_to(self.root/'projects'):raise ValueError('Project path leaves the workspace.')
        return p
    def _save(self):
        self.root.mkdir(parents=True,exist_ok=True);tmp=self.root/'state.pending.json';tmp.write_text(json.dumps({'project':self.project,'aiTarget':self.ai_target}));os.replace(tmp,self.root/'state.json')
    def projects(self):
        rows=[]
        for p in sorted((self.root/'projects').glob('*/project.json')):
            try:rows.append(json.loads(p.read_text()))
            except (OSError,ValueError):pass
        return rows
    def status(self):
        if self.proc and self.proc.poll() is not None:self.phase='error';self.error='Blender stopped unexpectedly. Reopen the saved project.';self.message=self.error
        with self.state_lock:return {'ok':True,'enabled':self.server is not None,'running':self.running,'aiTarget':self.ai_target,'project':self.project,'projects':self.projects(),'phase':self.phase,'message':self.message,'progress':dict(self.progress),'error':self.error,'job':dict(self.job) if self.job else None,'scene':self.scene,'url':f'http://127.0.0.1:{self.port}/' if self.server else '',
            'execution':'Real local Blender Python; no desktop window or MCP add-on required.','preview':'Three.js glTF preview; use Blender renders for exact shading.',
            'verified':bool(self.running and self.last_success and self.last_success['project']==self.project),'lastSuccess':dict(self.last_success) if self.last_success else None,'companion':self.pipeline.status(),'engines':list(self.engines),'enginesUpdatedAt':self.engines_at,'savedProject':bool(self.project and (self.folder()/'scene.blend').is_file())}
    def set_engines(self,rows):
        with self.state_lock:self.engines=[dict(e) for e in rows];self.engines_at=time.time()
    def _progress(self,**values):
        with self.state_lock:
            self.progress.update(values);self.phase=values.get('phase',self.phase);self.message=values.get('message',self.message)
    def start_http(self):
        with self.state_lock:
            if self.server is None:
                from blender_workspace_http import serve
                self.server=serve(self,self.port);self.port=self.server.server_address[1]
            key=secrets.token_urlsafe(32);self.launch_keys[key]=time.monotonic()+90
            return f'http://127.0.0.1:{self.port}/#launch={key}'
    def session(self,key):
        with self.state_lock:
            deadline=self.launch_keys.pop(str(key),0)
            if deadline<time.monotonic():raise PermissionError('Open Blender Workspace from Multi-Script again to reconnect this browser.')
            token=secrets.token_urlsafe(32);self.sessions[hashlib.sha256(token.encode()).hexdigest()]=time.monotonic()+43200
            self.launch_keys={k:v for k,v in self.launch_keys.items() if v>time.monotonic()}
            return token
    def authorized(self,token):return self.sessions.get(hashlib.sha256(str(token).encode()).hexdigest(),0)>time.monotonic()
    def submit(self,op,data=None):
        if op=='companion':return {'state':'done','settings':self.pipeline.configure(data or {})}
        if op not in ('prepare','create','open','close','target','ensure'):raise ValueError('Unknown workspace control.')
        with self.state_lock:
            if self.job_thread and self.job_thread.is_alive():
                if op=='ensure' and self.job.get('op')=='ensure':return dict(self.job)
                raise RuntimeError('The previous workspace operation is still running.')
            self.job={'id':uuid.uuid4().hex,'op':op,'state':'running','startedAt':time.time()};self.error='';self.cancel_prepare=False
            def run():
                try:
                    with self.lock:
                        if op=='prepare':blender_portable.prepare(self._progress,lambda:self.cancel_prepare)
                        elif op=='create':self._create(str((data or {}).get('name','Untitled project')))
                        elif op=='open':self._open(str((data or {}).get('project','')))
                        elif op=='ensure':
                            desired=str((data or {}).get('project') or self.project or '')
                            if self.running:
                                if desired and desired!=self.project:raise RuntimeError('Another Blender project is already running. Open the chosen companion project explicitly before starting this chat.')
                                try:self.scene=self._request('snapshot',{},20)['data']
                                except (RuntimeError,TimeoutError,OSError,ValueError):self._open(self.project)
                                self.ai_target=True;self._save();self.error='';self.phase='ready';self.message='Blender companion connected. The engine session can use this project.'
                            elif desired and (self.folder(desired)/'project.json').is_file():self._open(desired)
                            else:self._create('Game Assets')
                        elif op=='close':self._stop();self._save();self.phase='idle';self.message='Blender stopped. Your project is saved. Resume Blender to use its tools.'
                        elif op=='target':self.ai_target=(data or {}).get('workspace') is True;self._save()
                    self.job.update(state='done',finishedAt=time.time());self.on_change()
                except Exception as e:
                    self.error=str(e);self.phase='error';self.message=str(e);self.job.update(state='error',error=str(e),finishedAt=time.time())
            self.job_thread=threading.Thread(target=run,name='Multi-Script Blender setup',daemon=True);self.job_thread.start();return dict(self.job)
    def _create(self,name):
        label=' '.join(name.split())[:100] or 'Untitled project';slug=re.sub('[^a-z0-9]+','-',label.lower()).strip('-')[:45] or 'project';pid=slug+'-'+uuid.uuid4().hex[:10]
        folder=self.folder(pid);folder.mkdir(parents=True,exist_ok=False);(folder/'project.json').write_text(json.dumps({'id':pid,'name':label,'createdAt':time.time()}))
        return self._open(pid)
    def _open(self,pid):
        folder=self.folder(pid)
        if not (folder/'project.json').is_file():raise ValueError('Unknown saved Blender project.')
        executable=blender_portable.prepare(self._progress,lambda:self.cancel_prepare)
        self._stop();self.phase='starting';self.message='Starting real Blender in the background…';self.project=pid
        ready=folder/('worker-'+uuid.uuid4().hex+'.json');self.worker_token=secrets.token_urlsafe(32)
        env=os.environ.copy();env['MS_BLENDER_WORKER_TOKEN']=self.worker_token;env['PYTHONIOENCODING']='utf-8'
        self.log=(folder/'worker.log').open('ab')
        self.proc=subprocess.Popen([executable,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(HERE/'blender_workspace_worker.py'),'--','--project',str(folder),'--ready',str(ready),'--owner-pid',str(os.getpid())],env=env,cwd=folder,stdin=subprocess.DEVNULL,stdout=self.log,stderr=subprocess.STDOUT,**blender_portable.HIDDEN)
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            if ready.exists():
                try:
                    info=json.loads(ready.read_text(encoding='utf-8'));port=int(info['port'])
                    if info.get('pid')!=self.proc.pid or not 0<port<65536:
                        self._stop(force=True);raise RuntimeError('The Blender startup receipt belongs to a different worker or has an invalid port. Reopen the saved project.')
                    self.worker_port=port;break
                except (ValueError,KeyError):pass
            if self.proc.poll() is not None:
                self.log.close();self.log=None;raise RuntimeError('Blender could not start: '+(folder/'worker.log').read_text(errors='replace')[-4000:])
            if self.cancel_prepare:self._stop();raise InterruptedError('Blender start cancelled.')
            time.sleep(.1)
        else:self._stop();raise TimeoutError('Blender did not become ready. Check the project worker log.')
        ready.unlink(missing_ok=True);self.scene=self._request('snapshot',{},30)['data'];self.ai_target=True;self._save();self.error='';self.phase='ready';self.message='Blender workspace ready. Changes are saved automatically.';return self.scene
    def _request(self,op,args,timeout):
        if not self.running:raise RuntimeError('Blender Workspace is stopped. Use Resume Blender in its workspace to reopen the saved project. A desktop Blender add-on is not required; the AI target has not changed.')
        payload=json.dumps({'token':self.worker_token,'op':op,'args':args},allow_nan=False).encode()+b'\n'
        if len(payload)>1_000_000:raise ValueError('Blender request exceeds 1 MB. Split the operation.')
        try:
            with socket.create_connection(('127.0.0.1',self.worker_port),timeout=5) as c:
                c.settimeout(timeout);c.sendall(payload);raw=b''
                while b'\n' not in raw and len(raw)<=16_000_000:
                    chunk=c.recv(65536)
                    if not chunk:break
                    raw+=chunk
                if len(raw)>16_000_000:raise ValueError('Blender result exceeds 16 MB. Request a smaller result.')
                if not raw.endswith(b'\n'):raise ValueError('Incomplete Blender response.')
                result=json.loads(raw.split(b'\n',1)[0])
                if not isinstance(result,dict) or not isinstance(result.get('ok'),bool) or result['ok'] and op!='close' and not isinstance(result.get('data'),dict):raise ValueError('Invalid Blender response envelope.')
        except (TimeoutError,socket.timeout) as e:
            # A timed-out mutation must not continue while a second tool edits
            # the scene. Terminate the worker; the committed project is retained.
            self._stop(force=True);self.phase='error';self.error='Blender operation timed out. Reopen the saved project before continuing.';raise TimeoutError(self.error) from e
        except (OSError,ValueError) as e:
            # A lost/malformed reply can follow an already-started edit. Stop
            # that worker before permitting another call; never replay the edit.
            self._stop(force=True);self.phase='error';self.error='Blender Workspace lost its connection. The operation may have started; do not replay it automatically. Resume or reopen the saved project and inspect it first; no desktop add-on is required.'
            raise RuntimeError(self.error) from e
        if not result.get('ok'):raise RuntimeError(result.get('error','Blender operation failed.'))
        if op!='close':self.last_success={'at':time.time(),'operation':op,'project':self.project}
        return result
    def command(self,op,args=None,timeout=180):
        if op=='handoff':
            data=self.pipeline.handoff(args or {});return {'ok':True,'data':data,'project':data['project']}
        if not self.lock.acquire(blocking=False):raise RuntimeError('Blender is busy with the previous operation. Wait for its result.')
        try:
            a=dict(args or {});expected=a.pop('project',None)
            if expected and expected!=self.project:raise RuntimeError('The active Blender project changed. Read status before editing.')
            self.phase='working';self.message='Blender is '+('rendering…' if op=='render' else 'working…')
            response=self._request(op,a,max(5,min(600,timeout)));data=response['data']
            if isinstance(data,dict):
                if 'scene'in data:self.scene=data['scene']
                elif 'objects'in data:self.scene=data
            self.phase='ready';self.message='Saved in Blender.' if 'scene'in data else 'Blender workspace ready.';self.error=''
            response['project']=self.project
            return response
        except Exception as e:self.error=str(e);self.phase='error';self.message=str(e);raise
        finally:self.lock.release()
    def native_call(self,name,args,timeout=180):
        if name not in NATIVE_NAMES:raise RuntimeError('Headless Blender does not advertise '+name)
        if name=='execute_blender_code':r=self.command('exec',args,timeout);return {'text':r.get('output',''),'images':[]}
        expected={'project':args['project']} if args.get('project') else {}
        if name=='get_scene_info':return {'text':json.dumps(self.command('snapshot',expected,timeout)['data']),'images':[]}
        if name=='get_object_info':
            scene=self.command('snapshot',expected,timeout)['data'];o=next((o for o in scene['objects'] if o['name']==args.get('object_name')),None)
            if not o:raise ValueError('Unknown Blender object.')
            return {'text':json.dumps(o),'images':[]}
        rendered=self.command('render',expected,timeout);return {'text':'Real Blender Cycles CPU render.','images':[{'mimeType':'image/png','data':base64.b64encode((self.folder(rendered['project'])/'render.png').read_bytes()).decode()}]}
    def tool(self,args):
        a=dict(args);action=a.pop('action');op={'execute':'exec'}.get(action,action)
        if op=='status':return {'text':json.dumps(self.status()),'images':[]}
        if op not in ('snapshot','exec','render','export','frame','handoff'):raise ValueError('Unknown Blender workspace action.')
        r=self.command(op,a,300);images=[]
        if op=='render':images=[{'mimeType':'image/png','data':base64.b64encode((self.folder(r['project'])/'render.png').read_bytes()).decode()}]
        return {'text':json.dumps({'data':r['data'],'output':r.get('output',''),'project':r['project'],'folder':str(self.folder(r['project']))}),'images':images}
    def _stop(self,force=False):
        proc=self.proc;log=self.log
        if proc and proc.poll() is None:
            if not force:
                try:self._request('close',{},3);proc.wait(timeout=5)
                except Exception:pass
            if proc.poll() is None:proc.terminate()
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
        if self.proc is proc:self.proc=None;self.worker_port=None;self.worker_token=''
        if log:log.close()
        if self.log is log:self.log=None
        self.last_success=None
    def close(self):
        self.cancel_prepare=True
        if not self.lock.acquire(timeout=1):
            self._stop(force=True)
        else:self.lock.release()
        if self.job_thread and self.job_thread.is_alive():self.job_thread.join(timeout=10)
        if self.lock.acquire(timeout=5):
            try:self._stop()
            finally:self.lock.release()
        else:self._stop(force=True)
        if self.server:self.server.shutdown();self.server.server_close();self.server=None
        self.sessions.clear();self.launch_keys.clear()
