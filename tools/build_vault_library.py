"""Build a small, reproducible library seed; actual user media never enter releases."""
from pathlib import Path
import gzip,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'))
import bridge
script="const m=require('./extension/core/ultra-manuals');const out={};for(const manual of m.manuals){out[manual.id]=m.read({action:'read',id:manual.id});for(const engine of ['roblox','godot','unity','blender','workspace','figma'])out[manual.id+'-'+engine]=m.read({action:'read',id:manual.id,engine});}process.stdout.write(JSON.stringify(out));"
manuals=json.loads(subprocess.check_output(['node','-e',script],cwd=ROOT))
references={}
omni=ROOT/'runtime/skill-resources/omni-gui'
for path in sorted(omni.rglob('*')):
 if path.is_file() and path.suffix in ('.md','.luau','.json'):
  references['OMNI/'+path.relative_to(omni).as_posix()]=path.read_text(encoding='utf-8')
references['OMNI/catalog.json']=gzip.decompress((omni/'catalog.json.gz').read_bytes()).decode('utf-8')
data={'revision':1,'version':json.loads((ROOT/'extension/manifest.json').read_text())['version'],'skills':json.loads((ROOT/'runtime/skills.json').read_text(encoding='utf-8')),'tools':bridge.BUILTIN_TOOLS,'manuals':manuals,'references':references}
raw=json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode();out=ROOT/'runtime/vault-library.json.gz'
with out.open('wb') as stream:
 with gzip.GzipFile(fileobj=stream,mode='wb',mtime=0) as compressor:compressor.write(raw)
print(json.dumps({'seedBytes':out.stat().st_size,'skills':len(data['skills']),'tools':len(data['tools']),'manualsWithEnginePlaybooks':len(manuals),'referenceFiles':len(references),'sha256':hashlib.sha256(out.read_bytes()).hexdigest()}))
