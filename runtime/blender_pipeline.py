# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit companion preferences and real, non-overwriting game-asset handoff."""
from pathlib import Path
import hashlib,json,os,re,time,uuid

ENGINES=('roblox','unity','godot')
FORMATS={'roblox':'glb','unity':'fbx','godot':'glb'}

class Pipeline:
    def __init__(self,workspace):
        self.workspace=workspace;self.path=workspace.root/'companion.json'
        self.settings={'engines':[],'project':'','destinations':{}};self.last_handoff=None
        try:
            saved=json.loads(self.path.read_text(encoding='utf-8'))
            self.settings={'engines':[e for e in ENGINES if e in saved.get('engines',[])],
                           'project':str(saved.get('project','')),'destinations':{k:str(v) for k,v in saved.get('destinations',{}).items() if k in ENGINES}}
        except (OSError,ValueError,TypeError,AttributeError):pass
    def configure(self,args):
        allowed={'engines','project'}
        if not isinstance(args,dict) or set(args)-allowed:raise ValueError('Choose companion engines and a saved Blender project.')
        engines=args.get('engines',self.settings['engines']);project=args.get('project',self.settings['project'])
        if not isinstance(engines,list) or any(e not in ENGINES for e in engines):raise ValueError('Choose Roblox Studio, Unity or Godot.')
        if not isinstance(project,str):raise ValueError('Choose a saved Blender project.')
        if project and not (self.workspace.folder(project)/'project.json').is_file():raise ValueError('Choose an existing Blender project, or use the current project.')
        with self.workspace.state_lock:
            previous=self.settings;self.settings={**self.settings,'engines':[e for e in ENGINES if e in engines],'project':project}
            try:self._save()
            except OSError:self.settings=previous;raise
        return self.status()
    def _save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True);temp=self.path.with_suffix('.pending.json')
        temp.write_text(json.dumps(self.settings,indent=2)+'\n',encoding='utf-8');os.replace(temp,self.path)
    def status(self):
        last=self.last_handoff if self.last_handoff and self.last_handoff['project']==self.workspace.project else None
        with self.workspace.state_lock:return {'engines':list(self.settings['engines']),'project':self.settings['project'],'destinations':dict(self.settings['destinations']),'lastHandoff':last}
    def begin(self,engines):
        if not isinstance(engines,list) or any(e not in ENGINES for e in engines):raise ValueError('Invalid companion engine selection.')
        wanted=[e for e in engines if e in self.settings['engines']]
        if not wanted:return {'ok':True,'required':False}
        if not self.workspace.engine_enabled('blender'):raise RuntimeError('Enable Blender in Multi-Script Settings → Engines to include its workspace.')
        for engine in wanted:
            state=next((e for e in self.workspace.engines if e['id']==engine),{})
            if not self.workspace.engine_enabled(engine) or state.get('enabled') is False or state.get('connected') is not True or not state.get('alive'):
                raise RuntimeError(engine.title()+' is not connected. Connect its editor first, or turn off Include Blender for this engine.')
        job=self.workspace.submit('ensure',{'project':self.settings['project']})
        return {'ok':True,'required':True,'engines':wanted,'job':job}
    def handoff(self,args):
        w=self.workspace;engine=args.get('engine');expected=args.get('project')
        if engine not in ENGINES:raise ValueError('Choose Roblox Studio, Unity or Godot.')
        if not w.engine_enabled(engine):raise RuntimeError('Enable '+engine+' in Multi-Script Settings → Engines before its asset handoff.')
        if not expected or expected!=w.project:raise RuntimeError('The Blender project changed. Read status and use its current project id.')
        name=str(args.get('name') or 'BlenderAsset').strip()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',name):raise ValueError('Asset name: use 1–64 letters, numbers, hyphens or underscores.')
        fmt=FORMATS[engine];root=None
        if engine!='roblox':
            value=str(args.get('project_path') or self.settings['destinations'].get(engine) or '').strip()
            if not value or not Path(value).is_absolute():raise ValueError('Paste the absolute '+engine.title()+' project folder.')
            root=Path(value).resolve(strict=True)
            if engine=='unity' and (not (root/'Assets').is_dir() or not (root/'ProjectSettings/ProjectVersion.txt').is_file()):raise ValueError('Choose a Unity project containing Assets and ProjectSettings/ProjectVersion.txt.')
            if engine=='godot' and not (root/'project.godot').is_file():raise ValueError('Choose the folder containing project.godot.')
            rel=Path('Assets/MultiScript/Blender' if engine=='unity' else 'assets/multiscript/blender')/(name+'.'+fmt)
            destination=(root/rel).resolve()
            if not destination.is_relative_to(root):raise ValueError('The asset folder leaves the chosen game project. Remove the external symlink or choose a different project.')
        else:
            destination=w.folder()/('handoff-'+uuid.uuid4().hex+'.'+fmt)
        if not w.lock.acquire(blocking=False):raise RuntimeError('Blender is busy. Wait for the current operation before handing off an asset.')
        try:
            if w.project!=expected:raise RuntimeError('The Blender project changed before export.')
            w.phase='working';w.message='Exporting for '+engine.title()+'…'
            result=w._request('export',{'format':fmt},300);raw=(w.folder()/result['data']['file']).read_bytes()
            if not raw:raise RuntimeError('Blender produced an empty export. Nothing was copied.')
            if destination.exists():
                previous=destination.read_bytes()
                if previous!=raw and args.get('overwrite') is not True:raise FileExistsError('An asset with this name exists. Choose a new name or explicitly enable Replace existing asset.')
            destination.parent.mkdir(parents=True,exist_ok=True)
            # Exclusive creation protects against another session winning the name.
            try:
                with destination.open('xb') as target:target.write(raw)
            except FileExistsError:
                if destination.read_bytes()!=raw:
                    if args.get('overwrite') is not True:raise FileExistsError('This asset already exists. Choose a new name or explicitly enable Replace existing asset.')
                    temp=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.tmp')
                    try:temp.write_bytes(raw);os.replace(temp,destination)
                    finally:temp.unlink(missing_ok=True)
            sha=hashlib.sha256(raw).hexdigest()
            if hashlib.sha256(destination.read_bytes()).hexdigest()!=sha:raise RuntimeError('Copied asset did not pass verification.')
            asset=destination if engine=='roblox' else w.folder()/('handoff-'+uuid.uuid4().hex+'.'+fmt)
            if asset!=destination:asset.write_bytes(raw)
            self.last_handoff={'engine':engine,'project':expected,'format':fmt,'path':str(destination),'assetFile':asset.name,'bytes':len(raw),'sha256':sha,'at':time.time(),'state':'ready-to-import' if engine=='roblox' else 'copied-awaiting-editor-import','engineImportVerified':False}
            receipt=w.folder()/'handoff.json';receipt.write_text(json.dumps(self.last_handoff,indent=2)+'\n',encoding='utf-8')
            if root:
                with w.state_lock:self.settings['destinations'][engine]=str(root);self._save()
            w.phase='ready';w.error='';w.message='Asset exported. '+('Use Roblox Studio’s Importer to complete the import.' if engine=='roblox' else 'Open '+engine.title()+' and check the imported asset.')
            return dict(self.last_handoff)
        except Exception as e:w.phase='error';w.error=str(e);w.message=str(e);raise
        finally:w.lock.release()
