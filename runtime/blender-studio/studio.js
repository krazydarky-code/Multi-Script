import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {TransformControls} from 'three/addons/controls/TransformControls.js';
import {RoomEnvironment} from 'three/addons/environments/RoomEnvironment.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import GUI from 'lil-gui';
import {mountAssistant} from './assistant.js';
import {mountPipeline} from './pipeline.js';

const $=id=>document.getElementById(id),viewport=$('viewport');
let state=null,sceneData=null,model=null,mixer=null,clips=[],playing=false,selected='',inspector=null,loadedKey='',loadingKey='',requestGeneration=0,busy=false,frame=1,dragStart=null,uiError='';
const nodes=new Map(),world=new THREE.Scene(),camera=new THREE.PerspectiveCamera(42,1,.01,10000);
camera.position.set(8,6,9);world.background=null;
world.add(new THREE.HemisphereLight(0xdae4ff,0x36414e,2));const keyLight=new THREE.DirectionalLight(0xfff3df,3);keyLight.position.set(4,8,5);world.add(keyLight);
const grid=new THREE.GridHelper(30,30,0x49516a,0x303848);world.add(grid);
let renderer=null,orbit=null,gizmo=null;
try{
  renderer=new THREE.WebGLRenderer({antialias:true,alpha:true,preserveDrawingBuffer:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;viewport.prepend(renderer.domElement);const pmrem=new THREE.PMREMGenerator(renderer),room=new RoomEnvironment();world.environment=pmrem.fromScene(room,.04).texture;room.dispose();pmrem.dispose();
  orbit=new OrbitControls(camera,renderer.domElement);orbit.enableDamping=true;orbit.target.set(0,1,0);
  gizmo=new TransformControls(camera,renderer.domElement);world.add(gizmo.getHelper());gizmo.addEventListener('dragging-changed',e=>{orbit.enabled=!e.value;});
  gizmo.addEventListener('mouseUp',()=>{const node=gizmo.object;if(!node||!selected||busy)return;node.updateWorldMatrix(true,false);void command('transform',{name:selected,world_matrix:node.matrixWorld.toArray(),auto_key:$('auto-key').checked,frame});});
  const resize=()=>{const w=viewport.clientWidth,h=viewport.clientHeight;if(!w||!h)return;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();};new ResizeObserver(resize).observe(viewport);resize();
  renderer.domElement.addEventListener('pointerdown',e=>dragStart={x:e.clientX,y:e.clientY});
  renderer.domElement.addEventListener('pointerup',e=>{
    if(!dragStart||Math.hypot(e.clientX-dragStart.x,e.clientY-dragStart.y)>4||gizmo.axis||busy||!model)return;
    const r=renderer.domElement.getBoundingClientRect(),ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1),camera);
    let hit=ray.intersectObjects(model.children,true)[0]?.object;
    while(hit&&!hit.userData.ms_object_name)hit=hit.parent;
    if(hit)select(hit.userData.ms_object_name);
  });
}catch(e){$('viewport-error').hidden=false;$('viewport-error').textContent='The 3D preview needs WebGL. Enable browser graphics acceleration. Blender tools, files and real renders remain available.';}

function showError(error){uiError=String(error.message||error);$('status').textContent=uiError;$('status-dot').className='dot error';}
async function api(path,body){
  const response=await fetch(path,body===undefined?{credentials:'same-origin'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),credentials:'same-origin'});
  const data=await response.json();if(!response.ok||data.ok===false)throw Error(data.error||'Workspace request failed.');return data;
}
function asset(name,project=state?.project){return '/api/asset/'+encodeURIComponent(project)+'/'+name;}
function dispose(root){
  const materials=new Set(),textures=new Set();root?.traverse(o=>{o.geometry?.dispose();for(const m of Array.isArray(o.material)?o.material:o.material?[o.material]:[])materials.add(m);});
  for(const m of materials){for(const value of Object.values(m))if(value?.isTexture)textures.add(value);m.dispose();}
  for(const t of textures){t.source?.data?.close?.();t.dispose();}
}
function setPlaying(value){playing=value&&clips.length>0;$('play').textContent=playing?'Ⅱ':'▶';$('play').setAttribute('aria-label',playing?'Pause animation':'Play animation');}
function chooseClip(){
  if(!mixer)return;mixer.stopAllAction();const choice=$('clips').value;
  for(const [i,clip] of clips.entries())if(choice==='all'||choice===String(i))mixer.clipAction(clip).play();
  mixer.setTime((frame-(sceneData?.frames?.start||1))/(sceneData?.frames?.fps||24));
}
function fit(target=model){
  if(!orbit||!target?.isObject3D)return;const box=new THREE.Box3().setFromObject(target);
  if(box.isEmpty())return;const center=box.getCenter(new THREE.Vector3()),size=box.getSize(new THREE.Vector3()).length();
  orbit.target.copy(center);camera.position.copy(center).add(new THREE.Vector3(1,.75,1).normalize().multiplyScalar(Math.max(2,size*1.5)));camera.near=Math.max(.001,size/10000);camera.far=Math.max(1000,size*50);camera.updateProjectionMatrix();orbit.update();
}
async function loadPreview(s){
  if(s.scene.previewError){showError(s.scene.previewError);return;}
  const baked=s.scene.previewMaterials;const caption=$('viewport-caption').lastElementChild;caption.textContent=baked?.bakedObjects||baked?.cachedObjects?'Material preview · baked color':'Three.js material preview';caption.title='Studio lighting for inspection. Blender renders reproduce scene lighting and full shader effects.';
  const key=s.project+':'+s.scene.revision;if(!renderer||loadedKey===key||loadingKey===key)return;
  loadingKey=key;const generation=++requestGeneration;
  try{
    let assetFailed=false;const manager=new THREE.LoadingManager();manager.onError=()=>assetFailed=true;
    const gltf=await new GLTFLoader(manager).loadAsync(asset('preview.glb',s.project)+'?revision='+s.scene.revision);
    if(assetFailed){dispose(gltf.scene);throw Error('A model texture could not load. The native .blend is saved; check the browser connection and reopen the workspace.');}
    if(generation!==requestGeneration||state?.project!==s.project){dispose(gltf.scene);return;}
    const first=!model||loadedKey.split(':')[0]!==s.project;gizmo?.detach();
    if(model){mixer?.stopAllAction();mixer?.uncacheRoot(model);world.remove(model);dispose(model);}
    model=gltf.scene;world.add(model);nodes.clear();model.traverse(o=>{if(o.userData.ms_object_name&&!nodes.has(o.userData.ms_object_name))nodes.set(o.userData.ms_object_name,o);});
    mixer=new THREE.AnimationMixer(model);clips=gltf.animations;const previous=$('clips').value;
    $('clips').replaceChildren(...(clips.length?[...(clips.length>1?[new Option('All exported clips','all')]:[]),...clips.map((c,i)=>new Option(c.name||'Clip '+(i+1),String(i)))]:[new Option('No animation clips','')]));
    if([...$('clips').options].some(x=>x.value===previous))$('clips').value=previous;
    chooseClip();setPlaying(playing);loadedKey=key;if(first)fit();select(selected,false);
    // Read-only probe for headless verification and other local QA. No fake scene.
    window.MSBlenderPreview={threeRevision:THREE.REVISION,project:s.project,revision:s.scene.revision,meshes:0,texturedMeshes:0,clips:clips.map(c=>({name:c.name,duration:c.duration})),ready:true};model.traverse(o=>{if(o.isMesh){window.MSBlenderPreview.meshes++;if((Array.isArray(o.material)?o.material:[o.material]).some(m=>m?.map?.image))window.MSBlenderPreview.texturedMeshes++;}});
  }catch(e){showError('Could not load the Blender preview: '+e.message);}finally{if(generation===requestGeneration)loadingKey='';}
}
function select(name,buildInspector=true){
  selected=(sceneData?.objects||[]).some(o=>o.name===name)?name:'';
  $('fit-selected').disabled=!selected;
  document.querySelectorAll('.object-row').forEach(b=>{b.classList.toggle('selected',b.dataset.name===selected);b.setAttribute('aria-pressed',String(b.dataset.name===selected));});
  const info=sceneData?.objects?.find(o=>o.name===selected),node=nodes.get(selected);
  if(gizmo){if(node)gizmo.attach(node);else gizmo.detach();}
  if(!buildInspector)return;
  inspector?.destroy();inspector=null;$('selection').textContent=info?.name||'Nothing selected';$('delete').disabled=!info||busy;
  $('selection-hint').textContent=info?info.type+(info.type==='MESH'?' · '+info.vertices.toLocaleString()+' vertices':''):'Select an object in the scene or outliner.';
  if(!info)return;
  inspector=new GUI({container:$('inspector'),title:'Blender coordinates'});
  const properties={};
  for(const [key,title] of [['location','Position'],['rotation_deg','Rotation °'],['scale','Scale']]){
    properties[key]={x:info[key][0],y:info[key][1],z:info[key][2]};const folder=inspector.addFolder(title);
    for(const axis of ['x','y','z'])folder.add(properties[key],axis).step(key==='rotation_deg'?1:.01).onFinishChange(()=>void command('transform',{name:info.name,[key]:['x','y','z'].map(a=>properties[key][a]),auto_key:$('auto-key').checked,frame}));
  }
  if(info.type==='MESH'){
    const color={base:'#'+new THREE.Color().setRGB(...info.color.slice(0,3)).getHexString()};inspector.addColor(color,'base').name('Base color').onFinishChange(value=>{const c=new THREE.Color(value);void command('material',{name:info.name,color:[c.r,c.g,c.b,info.color[3]??1]});});
  }
}
function refreshScene(s){
  const changed=!sceneData||sceneData.project!==s.scene.project||sceneData.revision!==s.scene.revision,frameChanged=sceneData?.frames?.current!==s.scene.frames.current;sceneData=s.scene;
  if(!changed){if(frameChanged)select(selected);return;}
  $('outliner').replaceChildren(...sceneData.objects.map(o=>{const button=document.createElement('button');button.type='button';button.className='object-row';button.dataset.name=o.name;button.setAttribute('role','listitem');button.setAttribute('aria-label',o.name+' · '+o.type);const icon=document.createElement('span');icon.textContent=({MESH:'◇',ARMATURE:'♧',EMPTY:'⊕',LIGHT:'☼',CAMERA:'▱'})[o.type]||'·';button.append(icon,document.createTextNode(o.name));button.onclick=()=>select(o.name);return button;}));
  $('object-count').textContent=sceneData.objects.length+' object'+(sceneData.objects.length===1?'':'s');
  $('timeline').min=sceneData.frames.start;$('timeline').max=sceneData.frames.end;$('start-frame').textContent=sceneData.frames.start;$('end-frame').textContent=sceneData.frames.end;$('fps').textContent=sceneData.frames.fps+' fps';
  if(!playing){frame=sceneData.frames.current;$('timeline').value=frame;$('frame-label').textContent='Frame '+frame;}
  select(selected);void loadPreview(s);
}
function updateButtons(){
  const ready=!!state?.running&&!busy&&!['working','starting','downloading','extracting','verifying'].includes(state?.phase);
  for(const id of ['add','delete','keyframe','save','import','target'])$(id).disabled=!ready||(id==='delete'||id==='keyframe')&&!selected;
  document.querySelectorAll('[data-export]').forEach(b=>b.disabled=!ready);if(gizmo)gizmo.enabled=ready;
  $('new-project').disabled=busy||state?.job?.state==='running';$('projects').disabled=$('new-project').disabled;$('welcome-start').disabled=$('new-project').disabled;$('prepare').disabled=$('new-project').disabled;$('stop').disabled=!state?.running||busy;
}
async function poll(){
  try{
    const s=await api('/api/status');state=s;$('status').textContent=uiError||s.error||s.message;$('status-dot').className='dot '+(uiError||s.error?'error':s.running?'ready':'');$('backend').textContent=s.scene?.backend||'Local workspace';$('target').textContent='AI target: '+(s.aiTarget?'Workspace':'Connected Blender');
    const known=$('projects').value,options=s.projects.map(p=>new Option(p.name,p.id));$('projects').replaceChildren(new Option('Choose a project',''),...options);$('projects').value=s.project||known;
    $('welcome').hidden=s.running||s.savedProject;$('resume').hidden=s.running||!s.savedProject;$('resume').disabled=s.job?.state==='running';$('progress').hidden=s.job?.state!=='running';$('progress').value=s.progress?.percent||0;$('revision').textContent=s.savedProject?'Saved · revision '+(s.scene?.revision||0)+(s.running?'':' · Blender stopped'):'';
    if(s.scene?.objects)refreshScene(s);updateButtons();
    if(!s.running)setPlaying(false);
  }catch(e){showError(e);$('welcome').hidden=false;$('welcome').querySelector('p').textContent='Open Blender Workspace from Multi-Script → Settings → Engines to connect this browser. Your project files stay on your computer.';}
}
async function command(op,args={}){
  if(busy||!state?.running)return;busy=true;uiError='';updateButtons();
  try{const r=await api('/api/command',{op,args:{...args,project:state.project}});await poll();return r;}
  catch(e){showError(e);await poll();}finally{busy=false;updateButtons();}
}
async function control(op,args={}){try{uiError='';await api('/api/control',{op,args});await poll();return {ok:true};}catch(e){showError(e);return {ok:false,error:e.message};}}
function newProject(){const d=$('project-dialog');d.showModal();$('project-name').focus();$('project-name').select();}
$('new-project').onclick=$('welcome-start').onclick=newProject;
$('project-dialog').addEventListener('close',()=>{if($('project-dialog').returnValue==='create')void control('create',{name:$('project-name').value});});
$('projects').onchange=()=>{if($('projects').value)void control('open',{project:$('projects').value});};
$('resume').onclick=()=>void control('ensure',{project:state.project});$('prepare').onclick=()=>void control('prepare');$('stop').onclick=()=>void control('close');$('target').onclick=()=>void control('target',{workspace:!state.aiTarget});
$('add').onclick=()=>void command('primitive',{shape:$('primitive').value});$('fit').onclick=()=>fit();$('fit-selected').onclick=()=>fit(nodes.get(selected));
$('save').onclick=()=>void command('snapshot');$('delete').onclick=()=>{if(selected&&confirm('Delete '+selected+' from this Blender project?'))void command('delete',{name:selected});};
$('keyframe').onclick=async()=>{for(const channel of ['location','rotation_euler','scale'])await command('keyframe',{name:selected,frame,channel});};
document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{gizmo?.setMode(b.dataset.mode);document.querySelectorAll('[data-mode]').forEach(x=>x.classList.toggle('active',x===b));});
$('play').onclick=()=>setPlaying(!playing);$('clips').onchange=chooseClip;
$('timeline').oninput=()=>{setPlaying(false);frame=Number($('timeline').value);$('frame-label').textContent='Frame '+frame;chooseClip();};
$('timeline').onchange=()=>void command('frame',{frame});
document.querySelectorAll('[data-export]').forEach(b=>b.onclick=async()=>{const project=state.project,r=await command('export',{format:b.dataset.export});if(r){const link=document.createElement('a');link.href=asset(r.data.file,project);link.download=r.data.file;link.click();}});
$('import').onclick=()=>$('import-file').click();$('import-file').onchange=async()=>{
  const file=$('import-file').files[0];if(!file)return;
  try{if(file.size>50_000_000)throw Error('Import limit is 50 MB. Use the AI Blender tools for larger local assets.');const response=await fetch('/api/import',{method:'POST',headers:{'X-MS-Format':file.name.split('.').pop().toLowerCase(),'X-MS-Project':state.project},body:file});const r=await response.json();if(!response.ok||r.ok===false)throw Error(r.error||'Import failed.');await poll();}catch(e){showError(e);}finally{$('import-file').value='';}
};
document.addEventListener('keydown',e=>{if(e.target.closest('input,textarea,select,dialog')||e.ctrlKey||e.metaKey||e.altKey)return;const key=e.key.toLowerCase();if(key==='f')fit();else if(key===' ')e.preventDefault(),setPlaying(!playing);else if(['g','r','s'].includes(key))document.querySelector('[data-mode="'+({g:'translate',r:'rotate',s:'scale'})[key]+'"]').click();});
const timer=new THREE.Clock();
function animate(){requestAnimationFrame(animate);const dt=Math.min(timer.getDelta(),.1);if(playing&&mixer&&sceneData){mixer.update(dt);const clip=clips[Number($('clips').value)]||clips[0];frame=sceneData.frames.start+Math.floor((mixer.time%(clip?.duration||1))*sceneData.frames.fps);$('timeline').value=frame;$('frame-label').textContent='Frame '+frame;}orbit?.update();renderer?.render(world,camera);}
animate();
async function start(){try{const params=new URLSearchParams(location.hash.slice(1)),key=params.get('launch');history.replaceState(null,'',location.pathname);if(key)await api('/api/session',{key});await poll();setInterval(()=>void poll(),1000);}catch(e){showError(e);$('welcome').querySelector('p').textContent=e.message;}}
void start();
mountAssistant();
mountPipeline({getState:()=>state,command,control});
