-- Behavioral Roblox API fixture. No native Studio/rendering is claimed.
local methods={};local objects={};local nextGuid=0
local function signal() local callbacks={};return {Connect=function(_,fn) table.insert(callbacks,fn);return {Disconnect=function() end} end,Fire=function(_,...) for _,fn in ipairs(callbacks) do fn(...) end end} end
local mt={}
mt.__index=function(self,key)
 if methods[key] then return methods[key] end
 if self._props[key]~=nil then return self._props[key] end
 if key=='Activated' or key=='Click' or key=='SelectionChanged' or key=='Unloading' then local s=signal();self._props[key]=s;return s end
 return nil
end
mt.__newindex=function(self,key,value)
 if key=='Parent' then local old=self._props.Parent;if old then for i,v in ipairs(old._children) do if v==self then table.remove(old._children,i);break end end end;if value then table.insert(value._children,self) end end
 self._props[key]=value
end
function methods:GetChildren() local out={};for _,v in ipairs(self._children) do table.insert(out,v) end;return out end
function methods:GetDescendants() local out={};local function visit(o) for _,c in ipairs(o._children) do table.insert(out,c);visit(c) end end;visit(self);return out end
function methods:GetFullName() if self.Parent and self.Parent.Name~='game' then return self.Parent:GetFullName()..'.'..self.Name end;return self.Name end
function methods:FindFirstChild(name) for _,c in ipairs(self._children) do if c.Name==name then return c end end end
function methods:IsA(name) return self.ClassName==name or name=='LuaSourceContainer' and (self.ClassName=='Script' or self.ClassName=='LocalScript' or self.ClassName=='ModuleScript') end
function methods:GetAttributes() return {} end
function methods:GetPropertyChangedSignal(name) self._signals[name]=self._signals[name] or signal();return self._signals[name] end
function methods:Destroy() self.Parent=nil end
function methods:IsDescendantOf(parent) local p=self.Parent;while p do if p==parent then return true end;p=p.Parent end;return false end
function methods:SetAttribute() end
function methods:SetActive() end
function methods:Clone() error('Not used in this fixture') end
Instance={new=function(class) local o=setmetatable({_props={ClassName=class,Name=class},_children={},_signals={}},mt);table.insert(objects,o);return o end}
game=Instance.new('DataModel');game.Name='game';game.PlaceId=7
local services={}
function methods:GetService(name) if not services[name] then local o=Instance.new(name);o.Name=name;o.Parent=game;services[name]=o end;return services[name] end
local http=game:GetService('HttpService')
http.GenerateGUID=function() nextGuid=nextGuid+1;return 'fixture-guid-'..nextGuid end
http.JSONEncode=function(_,value) return py_encode(value) end
http.JSONDecode=function(_,value) return py_decode(value) end
http.RequestAsync=function(_,request) return py_request(request) end
local selected=game:GetService('Selection');selected.Get=function() return {} end;selected.Set=function() end
local run=game:GetService('RunService');run.IsRunning=function() return fixturePlaying==true end
local tags=game:GetService('CollectionService');tags.GetTags=function() return {} end
local history=game:GetService('ChangeHistoryService');history.SetWaypoint=function() end
local editor=game:GetService('ScriptEditorService')
editor.GetEditorSource=function(_,script) return script.EditorBuffer or script.Source or '' end
editor.UpdateSourceAsync=function(_,script,callback)
 if fixtureConflict then script.EditorBuffer='user edited concurrently';fixtureConflict=false end
 local result=callback(editor:GetEditorSource(script))
 if result~=nil then script.EditorBuffer=result;script.Source=result end
end
plugin=Instance.new('Plugin');local settings={}
plugin.GetSetting=function(_,name) return settings[name] end
plugin.SetSetting=function(_,name,value) settings[name]=value end
plugin.CreateToolbar=function() return {CreateButton=function() return Instance.new('ToolbarButton') end} end
plugin.CreateDockWidgetPluginGui=function() return Instance.new('DockWidgetPluginGui') end
local function enumTree() return setmetatable({},{__index=function(self,key) local value=enumTree();rawset(self,key,value);return value end}) end
Enum=enumTree();Color3={fromRGB=function(r,g,b) return {R=r/255,G=g/255,B=b/255} end};ColorSequence={new=function(...) return {...} end}
UDim={new=function(...) return {...} end};UDim2={new=function(...) return {...} end,fromScale=function(...) return {...} end,fromOffset=function(...) return {...} end}
DockWidgetPluginGuiInfo={new=function(...) return {...} end};math.clamp=function(x,a,b) return math.max(a,math.min(b,x)) end
task={spawn=function() end,delay=function() end,wait=function() end};warn=function() end
typeof=function(value) if type(value)=='table' and value.ClassName then return 'Instance' end;return type(value) end
function fixtureScript(source) local s=Instance.new('ModuleScript');s.Name='Main';s.Source=source;s.EditorBuffer=source;s.Parent=game:GetService('ServerScriptService');return s end
