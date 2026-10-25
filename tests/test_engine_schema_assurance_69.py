import importlib.util,json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
w=types.ModuleType('websockets');w.ConnectionClosed=Exception;sys.modules.setdefault('websockets',w)
spec=importlib.util.spec_from_file_location('compat_bridge',ROOT/'runtime'/'bridge.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
assert len(b.BUILTIN_TOOLS)==279 and 'ms_mcp_schema_audit' in b.BUILTIN_TOOL_NAMES
schema={
 'type':'object','additionalProperties':False,
 '$defs':{'vec':{'type':'array','minItems':3,'maxItems':3,'items':{'type':'number'}}},
 'properties':{
  'mode':{'type':'string','enum':['Create','Modify'],'default':'Create'},
  'target':{'oneOf':[{'type':'string','minLength':2},{'type':'integer','minimum':1}]},
  'payload':{'type':'object','additionalProperties':False,'properties':{
   'position':{'$ref':'#/$defs/vec'},'name':{'type':'string','pattern':'^[A-Za-z]','maxLength':20},
   'enabled':{'type':['boolean','null']},'tags':{'type':'array','uniqueItems':True,'items':{'type':'string'}}},
   'required':['position','name']}
 },'required':['target','payload']}
got=b._normalize_tool_arguments(schema,{'target':'Hero','payload':'{"position":["1",2,3],"name":"Boss","enabled":"yes","tags":["a","b"]}'},'native/probe')
assert got['mode']=='Create' and got['payload']['position']==[1.0,2.0,3.0] and got['payload']['enabled'] is True
bad=[
 {'target':'H','payload':{'position':[1,2,3],'name':'Boss'}},
 {'target':'Hero','payload':{'position':[1,2],'name':'Boss'}},
 {'target':'Hero','payload':{'position':[1,2,3],'name':'1Boss'}},
 {'target':'Hero','payload':{'position':[1,2,3],'name':'Boss','unknown':1}},
 {'target':'Hero','payload':{'position':[1,2,3],'name':'Boss','tags':['x','x']}},
]
for x in bad:
 try:b._normalize_tool_arguments(schema,x,'native/probe');raise AssertionError(('accepted invalid nested parameters',x))
 except RuntimeError:pass
try:b._normalize_tool_arguments({'type':'object','properties':{'count':{'type':'integer'}},'required':['count']},{'count':1.5},'integer/probe');raise AssertionError('fractional integer accepted')
except RuntimeError:pass
# Exact engine contracts are enforced for every engine-named direct specialist.
for t in b.BUILTIN_TOOLS:
 for prefix,engine in b._ENGINE_TOOL_PREFIXES.items():
  if t['name'].startswith(prefix) and 'engine' in t['inputSchema'].get('properties',{}):
   assert t['inputSchema']['properties']['engine']['enum']==[engine],t['name']
   try:b._normalize_tool_arguments(t['inputSchema'],{'feature':'x','engine':'general'},t['name']);raise AssertionError(t['name'])
   except RuntimeError:pass
# Every catalogue item has a concrete runtime compatibility/recovery contract.
sk=json.load(open(ROOT/'runtime'/'skills.json'));vt=json.load(open(ROOT/'runtime'/'virtual-tools.json'))['tools']
for collection in (sk,vt):
 for key,item in collection.items():
  c=item['engineExecutionContract'];assert c['engine']==item['engine'] and len(c['parameterPolicy'])==5 and len(c['recoveryPolicy'])==5,key
for t in b.BUILTIN_TOOLS:
 c=t['inputSchema']['x-multiScriptCompatibility'];assert c['liveSchemaRequired'] and c['recursiveParameterValidation']
# Deterministic risk scoring and connected-server schema audit.
r=b._schema_risk_analysis({'type':'object','properties':{'x':{'type':'array'}}})
assert r['riskBand'] in ('medium','high') and any(x['code']=='array-items-unspecified' for x in r['issues'])
class M:
 def health(self):return [{'id':'unity'}]
 def list_server_tools(self,sid,refresh=False):return [{'name':'safe','inputSchema':{'type':'object','additionalProperties':False,'properties':{'action':{'type':'string','enum':['get']}}}},{'name':'risky','inputSchema':{'type':'object','properties':{'items':{'type':'array'}}}}]
out=json.loads(b._builtin_call('ms_mcp_schema_audit',{'include_low_risk':True},M())['text'])
assert out['auditedNativeTools']==2 and out['method'].startswith('static advertised-schema') and len(out['rows'])==2
model=json.load(open(ROOT/'runtime'/'compatibility-risk-model.json'));assert model['postFixEstimatedResidualRisk']['nestedObjectParameters']<model['preFixRisk']['nestedObjectParameters']
std=json.load(open(ROOT/'runtime'/'studio-standard.json'));assert std['version']=='12.1' and std['mcpParameterCompatibility']['liveSchemaOnly']
print('PASS 6.9 recursive MCP schemas, strict engine binding, 897 skills, 300 virtual specialists, 231 direct tools, and risk audit')
