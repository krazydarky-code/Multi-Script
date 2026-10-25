// SPDX-License-Identifier: GPL-3.0-or-later
// Native Figma operations. No eval, arbitrary script or off-page writes.
(function(g){'use strict';
 const WRITE=new Set(['figma_create_node','figma_update_node','figma_import_svg','figma_delete_node']);
 function create(api){let permission='read';const nonce=Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);
  const context=()=>nonce+'|'+(api.fileKey||api.root.id)+'|'+api.currentPage.id;
  const metadata=()=>({context:context(),file:api.root.name,page:api.currentPage.name,permission});
  function onPage(node,write=false){let n=node;if(!n||n.removed)throw Error('Node not found.');while(n&&n!==api.currentPage){if(write&&n.locked)throw Error('Node or ancestor is locked.');n=n.parent;}if(n!==api.currentPage)throw Error('Only the current page is available.');return node;}
  async function node(id,write=false){return onPage(await api.getNodeByIdAsync(id),write);}
  function inspect(root,depth=0,budget={left:300}){if(budget.left--<=0)return {id:root.id,truncated:true};const out={id:root.id,type:root.type,name:root.name};for(const k of ['x','y','width','height','rotation','opacity','visible','locked','characters','fontSize','layoutMode','itemSpacing','paddingTop','paddingRight','paddingBottom','paddingLeft','cornerRadius'])if(typeof root[k]==='string'||typeof root[k]==='number'||typeof root[k]==='boolean')out[k]=root[k];for(const k of ['fills','strokes'])if(Array.isArray(root[k]))out[k]=JSON.parse(JSON.stringify(root[k])).slice(0,10);if(root.children){out.childCount=root.children.length;if(depth>0)out.children=root.children.slice(0,300).map(n=>inspect(n,depth-1,budget));}return out;}
  function paint(value){if(typeof value!=='string'||!/^#[0-9a-f]{6}(?:[0-9a-f]{2})?$/i.test(value))throw Error('Use #RRGGBB or #RRGGBBAA colors.');return [{type:'SOLID',color:{r:parseInt(value.slice(1,3),16)/255,g:parseInt(value.slice(3,5),16)/255,b:parseInt(value.slice(5,7),16)/255},opacity:value.length===9?parseInt(value.slice(7,9),16)/255:1}];}
  const numbers={x:[-1e6,1e6],y:[-1e6,1e6],width:[1,16384],height:[1,16384],rotation:[-36000,36000],opacity:[0,1],cornerRadius:[0,4096],fontSize:[1,512],itemSpacing:[-1000,4096],paddingTop:[0,4096],paddingRight:[0,4096],paddingBottom:[0,4096],paddingLeft:[0,4096]};
  const enums={layoutMode:['NONE','HORIZONTAL','VERTICAL'],primaryAxisAlignItems:['MIN','MAX','CENTER','SPACE_BETWEEN'],counterAxisAlignItems:['MIN','MAX','CENTER','BASELINE'],primaryAxisSizingMode:['FIXED','AUTO'],counterAxisSizingMode:['FIXED','AUTO']};
  async function props(n,p,ensure=()=>{}){if(!p||typeof p!=='object'||Array.isArray(p))throw Error('Properties must be an object.');const prepared={};for(const [k,v]of Object.entries(p)){
   if(numbers[k]){if(!Number.isFinite(v)||v<numbers[k][0]||v>numbers[k][1])throw Error('Invalid '+k);}
   else if(enums[k]){if(!enums[k].includes(v))throw Error('Invalid '+k);}
   else if(['name','characters'].includes(k)){if(typeof v!=='string'||v.length>(k==='name'?200:20000))throw Error('Invalid '+k);}
   else if(['visible','clipsContent'].includes(k)){if(typeof v!=='boolean')throw Error('Invalid '+k);}
   else if(!['fill','stroke'].includes(k))throw Error('Unsupported property '+k);
   const target=k==='fill'?'fills':k==='stroke'?'strokes':k;
   if(!(target in n))throw Error(k+' is unavailable on '+n.type);
   prepared[target]=['fill','stroke'].includes(k)?paint(v):v;
  }
  if(n.type==='TEXT'&&('characters'in prepared||'fontSize'in prepared)){if(n.fontName===api.mixed)throw Error('Mixed fonts: choose a uniform text node first.');await api.loadFontAsync(n.fontName);}
  ensure();
  if('width'in prepared||'height'in prepared){n.resize(prepared.width??n.width,prepared.height??n.height);delete prepared.width;delete prepared.height;}
  for(const [k,v]of Object.entries(prepared))n[k]=v;
 }
 function base64(bytes){const table='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';let out='';for(let i=0;i<bytes.length;i+=3){const a=bytes[i],b=bytes[i+1],c=bytes[i+2],n=(a<<16)|((b||0)<<8)|(c||0);out+=table[(n>>>18)&63]+table[(n>>>12)&63]+(i+1<bytes.length?table[(n>>>6)&63]:'=')+(i+2<bytes.length?table[n&63]:'=');}return out;}
 async function execute(job){const ensure=()=>{if(job.context!==context())throw Error('File or page changed. Refresh the target before retrying.');if(WRITE.has(job.tool)&&permission!=='edit')throw Error('Edit is disabled inside Figma.');};ensure();const a=job.arguments||{},depth=Math.max(0,Math.min(4,Number(a.depth)||0));
  if(job.tool==='figma_get_document')return {...metadata(),selection:api.currentPage.selection.map(n=>inspect(n)),page:inspect(api.currentPage,Math.max(1,depth))};
  if(job.tool==='figma_get_node')return inspect(await node(a.node_id),depth);
  if(job.tool==='figma_create_node'){
   const factory={FRAME:'createFrame',COMPONENT:'createComponent',RECTANGLE:'createRectangle',ELLIPSE:'createEllipse',TEXT:'createText'}[a.type];if(!factory)throw Error('Unsupported native node type.');const parent=a.parent_id?await node(a.parent_id,true):api.currentPage;if(typeof parent.appendChild!=='function')throw Error('Parent is not a container.');let made;try{ensure();made=api[factory]();parent.appendChild(made);await props(made,a.properties||{},ensure);return {created:true,node:inspect(made)};}catch(e){made?.remove();throw e;}
  }
  if(job.tool==='figma_update_node'){const n=await node(a.node_id,true);if(n===api.currentPage)throw Error('Update a scene node, not the page.');try{await props(n,a.properties,ensure);return {updated:true,node:inspect(n)};}catch(e){throw Error(e.message+' Read back the node before retrying; native updates may be partial.');}}
  if(job.tool==='figma_import_svg'){if(typeof a.svg!=='string'||a.svg.length>131072||!/<svg[\s>]/i.test(a.svg)||/<(?:script|foreignObject)|<!DOCTYPE|\bon\w+\s*=/i.test(a.svg)||[...a.svg.matchAll(/(?:href|src)\s*=\s*(["'])(.*?)\1/gi)].some(m=>!m[2].trim().startsWith('#'))||[...a.svg.matchAll(/url\(\s*(["']?)(.*?)\1\s*\)/gi)].some(m=>!m[2].trim().startsWith('#')))throw Error('Use a bounded SVG with no scripts or external resources.');const parent=a.parent_id?await node(a.parent_id,true):api.currentPage;if(typeof parent.appendChild!=='function')throw Error('Parent is not a container.');ensure();const n=api.createNodeFromSvg(a.svg);try{parent.appendChild(n);n.name=String(a.name||'Multi-Script vector').slice(0,200);return {created:true,node:inspect(n,1)};}catch(e){n.remove();throw e;}}
  if(job.tool==='figma_export_node'){const n=await node(a.node_id);if(typeof n.exportAsync!=='function')throw Error('Node cannot be exported.');const format=a.format||'PNG';if(!['PNG','SVG'].includes(format))throw Error('Use PNG or SVG.');const scale=a.scale??1;if(!Number.isFinite(scale)||scale<.25||scale>2)throw Error('Scale must be 0.25–2.');ensure();const bytes=await n.exportAsync(format==='PNG'?{format,constraint:{type:'SCALE',value:scale}}:{format});ensure();if(bytes.length>3000000)throw Error('Export exceeds 3 MB; choose a smaller node or scale.');return {node_id:n.id,format,mimeType:format==='PNG'?'image/png':'image/svg+xml',base64:base64(bytes)};}
  if(job.tool==='figma_set_selection'){if(!Array.isArray(a.node_ids)||a.node_ids.length>30)throw Error('Choose up to 30 nodes.');const selected=await Promise.all(a.node_ids.map(id=>node(id)));if(selected.some(n=>n===api.currentPage))throw Error('Select scene nodes.');ensure();api.currentPage.selection=selected;if(selected.length)api.viewport.scrollAndZoomIntoView(selected);return {selected:selected.map(n=>n.id)};}
  if(job.tool==='figma_delete_node'){if(a.confirm!==true)throw Error('Inspect the node, then pass confirm=true.');const n=await node(a.node_id,true);if(n===api.currentPage)throw Error('Pages cannot be deleted.');ensure();n.remove();return {deleted:true,node_id:a.node_id};}
  throw Error('Unknown companion command.');
 }
 return {metadata,execute,setPermission:p=>{permission=p==='edit'?'edit':'read';},inspect};
 }
 if(typeof module!=='undefined'&&module.exports)module.exports={create};
 if(typeof figma!=='undefined'){
  const control=create(figma);figma.showUI(__html__,{width:360,height:470,themeColors:true});
  const publish=()=>figma.ui.postMessage({type:'metadata',...control.metadata()});
  figma.on('currentpagechange',publish);figma.on('selectionchange',publish);
  figma.ui.onmessage=async msg=>{if(msg.type==='permission'){control.setPermission(msg.permission);publish();}else if(msg.type==='metadata')publish();else if(msg.type==='job'){try{const result=await control.execute(msg.job);figma.ui.postMessage({type:'result',id:msg.job.id,context:msg.job.context,ok:true,result});}catch(e){figma.ui.postMessage({type:'result',id:msg.job.id,context:msg.job.context,ok:false,error:String(e.message||e)});}}};publish();
 }
})(globalThis);
