"""Actual pinned stdio server, native bbmodel read/write and optional real GPU render."""
from pathlib import Path
import base64,hashlib,io,json,os,sys,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'runtime'))
import blockbench_workspace as workspace
assert workspace.status()['prepared'],'Prepare the pinned runtime with tools/prepare_blockbench.py; this required native test does not silently skip.'
import bridge
from PIL import Image

with tempfile.TemporaryDirectory(prefix='ms-blockbench-native-') as temp:
 os.environ['MS_BLOCKBENCH_PROJECT_ROOT']=temp
 client=bridge.MCPClient('blockbench','launch_blockbench_mcp.py',[])
 try:
  client.start();assert client.is_alive() and len(client.tools_cache)==21
  names={x['name'] for x in client.tools_cache}
  assert not any('open_in' in n or 'launch' in n for n in names)
  def call(name,args,error=False):
   result=client.call_tool(name,args,timeout=75)
   assert bool(result.get('isError'))==error,(name,result['text'][:500])
   if error:return result
   return json.loads(result['text'])
  created=call('bbmodel_create',{'file':'qa.bbmodel','format':'bedrock','name':'Native Multi-Script QA'})
  edit=call('bbmodel_edit',{'file':'qa.bbmodel','expected_revision':created['revision'],'operations':[
   {'op':'add_group','name':'Root','origin':[0,0,0]},
   {'op':'add_cube','name':'Body','from':[-4,0,-2],'to':[4,12,2],'parent':'Root'},
   {'op':'add_animation','name':'qa_turn','length':1,'loop':'loop'},
   {'op':'set_keyframe','animation':'qa_turn','bone':'Root','channel':'rotation','time':0,'value':[0,0,0]},
   {'op':'set_keyframe','animation':'qa_turn','bone':'Root','channel':'rotation','time':0.5,'value':[0,45,0]}]})
  model=Path(temp)/'qa.bbmodel';stable=model.read_bytes()
  call('bbmodel_edit',{'file':'qa.bbmodel','expected_revision':created['revision'],'operations':[{'op':'remove_node','target':'Body'}]},True)
  assert model.read_bytes()==stable
  call('bbmodel_edit',{'file':'qa.bbmodel','expected_revision':edit['revision'],'operations':[{'op':'add_group','name':'Rollback'},{'op':'remove_node','target':'Missing'}]},True)
  assert model.read_bytes()==stable
  image=Image.new('RGBA',(32,32),(30,180,95,255));png=io.BytesIO();image.save(png,format='PNG')
  texture=call('bbmodel_add_texture',{'file':'qa.bbmodel','expected_revision':edit['revision'],'image':'data:image/png;base64,'+base64.b64encode(png.getvalue()).decode(),'name':'QA green','assign_to':['Body']})
  assert len(call('bbmodel_list_textures',{'file':'qa.bbmodel'})['textures'])==1
  call('bbmodel_sample_pose',{'file':'qa.bbmodel','animation':'qa_turn','time':0.25})
  call('bbmodel_validate',{'file':'qa.bbmodel'});call('bbmodel_validate_animations',{'file':'qa.bbmodel'})
  call('bbmodel_export_bedrock_geometry',{'file':'qa.bbmodel','output':'exports/qa.geo.json'})
  assert json.loads((Path(temp)/'exports/qa.geo.json').read_text())
  call('bbmodel_info',{'file':'../outside.bbmodel'},True);call('bbmodel_create',{'file':'qa.bbmodel'},True)
  if os.environ.get('MS_BLOCKBENCH_RENDER_TEST')=='1':
   assert workspace.status()['renderPrepared']
   result=call('bbmodel_render',{'file':'qa.bbmodel','output':'render.png','width':256,'height':256,'clip':'qa_turn','time':0.25,'lighting':'flat'})
   output=Path(temp)/'render.png';assert output.is_file()
   with Image.open(output) as rendered:assert rendered.size==(256,256) and len(rendered.convert('RGB').getcolors(65536))>10
   digest=hashlib.sha256(output.read_bytes()).hexdigest()
   call('bbmodel_render',{'file':'qa.bbmodel','output':'render.png','width':256,'height':256},True)
   assert hashlib.sha256(output.read_bytes()).hexdigest()==digest
   evidence=ROOT/'test-results/blockbench-650';evidence.mkdir(parents=True,exist_ok=True)
   (evidence/'render.png').write_bytes(output.read_bytes());(evidence/'model.bbmodel').write_bytes(model.read_bytes())
   print('PASS actual textured animated GPU render, PNG dimensions and existing-image preservation.')
  print('PASS actual 21-tool MCP handshake, create/edit/texture/pose/validation/export, stale-revision refusal, atomic rollback and path containment.')
 finally:client.stop()
