import importlib.util, json, sys, types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
w=types.ModuleType('websockets');w.ConnectionClosed=Exception;sys.modules.setdefault('websockets',w)
spec=importlib.util.spec_from_file_location('param_bridge',ROOT/'runtime'/'bridge.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

def sample(spec):
    t=spec.get('type')
    if 'enum' in spec:return spec['enum'][0]
    if t=='string':return 'sample'
    if t=='integer':return int(spec.get('minimum',1))
    if t=='number':return float(spec.get('minimum',1))
    if t=='boolean':return True
    if t=='array':return [sample(spec.get('items') or {'type':'string'}) for _ in range(max(1,int(spec.get('minItems',1))))]
    if t=='object':
        props=spec.get('properties') or {}
        return {name:sample(props[name]) for name in spec.get('required',[]) if name in props}
    return None

expected=json.loads((ROOT/'runtime/product-manifest.json').read_text())['catalogue']['directTools']
assert len(b.BUILTIN_TOOLS)==len(b.BUILTIN_TOOL_NAMES)==expected
for tool in b.BUILTIN_TOOLS:
    schema=tool['inputSchema'];props=schema.get('properties',{})
    args={name:sample(props[name]) for name in schema.get('required',[])}
    clean=b._normalize_tool_arguments(schema,args,tool['name'])
    assert isinstance(clean,dict),tool['name']
    # Every declared optional parameter must independently normalize too.
    for name,prop in props.items():
        value=sample(prop)
        one=dict(args);one[name]=value
        got=b._normalize_tool_arguments(schema,one,tool['name'])
        assert name in got,(tool['name'],name)
# Provider quirks: stringified containers, booleans, numbers, comma arrays, case-insensitive enums.
schema={'type':'object','properties':{'count':{'type':'integer','minimum':1,'maximum':5},'enabled':{'type':'boolean'},'tags':{'type':'array','items':{'type':'string'}},'mode':{'type':'string','enum':['Balanced','Compact']},'options':{'type':'object'}},'required':['count','enabled']}
got=b._normalize_tool_arguments(schema,{'count':'3','enabled':'yes','tags':'ui,mobile','mode':'compact','options':'{"x":1}'},'probe')
assert got=={'count':3,'enabled':True,'tags':['ui','mobile'],'mode':'Compact','options':{'x':1}}
for bad in ({'count':0,'enabled':True},{'count':2,'enabled':'maybe'},[],{'enabled':True}):
    try:b._normalize_tool_arguments(schema,bad,'probe');raise AssertionError(('expected validation failure',bad))
    except RuntimeError:pass
standard=json.load(open(ROOT/'runtime'/'studio-standard.json',encoding='utf-8'))
assert len(standard['principles'])>=6 and len(standard['definitionOfDone'])>=8
assert set(['roblox','unity','godot','blender','figma','general'])<=set(standard['engines'])
print('PASS all 271 tool schemas, every declared parameter, provider coercions, bounds, enums and studio standards')
