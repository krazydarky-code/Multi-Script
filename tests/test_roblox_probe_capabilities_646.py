"""Execute the shipped world-stat Lua body with a restricted Lighting fixture."""
import ast
from pathlib import Path
from lupa import LuaRuntime
ROOT=Path(__file__).resolve().parents[1]
tree=ast.parse((ROOT/'runtime/toolkit_roblox.py').read_text(encoding='utf-8'))
function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='world_stats')
call=next(n for n in ast.walk(function) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='_exec')
body=ast.literal_eval(call.args[2])
setup='''
R={}
local part={Anchored=true};function part:IsA(cls)return cls=='BasePart' end
local model={};function model:IsA(cls)return cls=='Model' end
local source={};function source:IsA(cls)return cls=='ModuleScript' end
workspace={StreamingEnabled=true};function workspace:GetDescendants()return {part,model}end
local empty={};function empty:GetDescendants()return {}end
local lighting=setmetatable({GetDescendants=function()return {}end},{__index=function(_,key)
 if key=='Technology' then %s end
 if key=='LightingStyle' then return 'Soft' end
 return nil
end})
game={PlaceId=42,Name='Existing nonempty project'}
function game:GetDescendants()return {part,model,source}end
function game:GetService(name)if name=='Workspace'then return workspace elseif name=='Lighting'then return lighting else return empty end end
'''
for restricted in [True,False]:
    lua=LuaRuntime();lua.execute(setup%('error("The current thread cannot read Technology (lacking capability RobloxScript)")' if restricted else 'return "Future"'));lua.execute(body)
    result=lua.globals().R
    assert result.counts.total==3 and result.counts.parts==1 and result.counts.models==1 and result.counts.modules==1
    assert result.place.id==42 and result.place.name=='Existing nonempty project' and result.lighting_style=='Soft'
    if restricted:assert result.lighting_technology is None and 'Restricted' in result.lighting_technology_unavailable
    else:assert result.lighting_technology=='Future' and result.lighting_technology_unavailable is None
print('PASS actual shipped world-stat Lua body preserves nonempty place observations under denied Technology capability and still reads supported lighting properties.')
