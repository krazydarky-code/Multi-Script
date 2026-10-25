--!nocheck
-- Multi-Script Companion for Roblox Studio
-- Secure, opt-in companion MCP tools. No arbitrary code execution.

local HttpService = game:GetService("HttpService")
local Selection = game:GetService("Selection")
local RunService = game:GetService("RunService")
local CollectionService = game:GetService("CollectionService")
local ChangeHistoryService = game:GetService("ChangeHistoryService")

local PLUGIN_VERSION = "6.50.0"
local DIAGNOSTIC_VERSION = 3
local BRIDGE_URL = "http://127.0.0.1:17614"
local STATUS_SECONDS = 5
local POLL_SECONDS = 0.35
local MAX_BATCH, MAX_TREE, MAX_SOURCE, MAX_OUTPUT = 200, 500, 4194304, 900000

local ROOT_NAMES = {ServerScriptService=true, ReplicatedFirst=true, Workspace=true, ReplicatedStorage=true, ServerStorage=true, StarterGui=true, StarterPlayer=true, Lighting=true, SoundService=true, Teams=true, TestService=true}
local CREATE_CLASSES = {
	Folder=true, Model=true, Configuration=true, Part=true, MeshPart=true, WedgePart=true, TrussPart=true,
	Attachment=true, WeldConstraint=true, Motor6D=true, ObjectValue=true, StringValue=true, BoolValue=true,
	IntValue=true, NumberValue=true, Vector3Value=true, CFrameValue=true, Color3Value=true, RemoteEvent=true,
	RemoteFunction=true, BindableEvent=true, BindableFunction=true, ScreenGui=true, Frame=true, TextLabel=true,
	TextButton=true, ImageLabel=true, ImageButton=true, UIListLayout=true, UIGridLayout=true, UIPadding=true,
	UICorner=true, UIStroke=true, Sound=true, Animation=true, ParticleEmitter=true, Beam=true, Trail=true,
	Highlight=true, ProximityPrompt=true, ClickDetector=true, SpawnLocation=true, Team=true,
}
local BLOCKED_PROPERTIES = {Parent=true, Source=true, ClassName=true, Archivable=true, RobloxLocked=true}
local PERMISSION_RANK = {off=0, read=1, project=2, full=3}
local TOOL_PERMISSION = {
	msrb_project_summary="read", msrb_get_selection="read", msrb_get_tree="read", msrb_find_instances="read",
	msrb_get_properties="read", msrb_export_snapshot="read", msrb_validate_paths="read",
	msrb_console_read="read", msrb_source_transfer="full", msrb_read_script="full", msrb_search_scripts="full", msrb_dependency_graph="full",
	msrb_set_selection="project", msrb_create_instances="project", msrb_set_properties="project",
	msrb_set_attributes="project", msrb_update_tags="project", msrb_reparent_instances="project",
	msrb_clone_instances="project", msrb_bulk_rename="project", msrb_checkpoint="project",
	msrb_patch_script="full", msrb_replace_script="full", msrb_delete_instances="full",
	msrb_undo="full", msrb_redo="full",
}

local alive, busy = true, false
local executionMode, sessionToken = "off", nil
local fullConfirmUntil = 0
local lastStatus = nil
local lastScan = {score=0, issueCount=0, high=0, medium=0, low=0, scanned=0, unreadable=0, durationMs=0}
local pluginId = plugin:GetSetting("MultiScriptPluginId")
if type(pluginId) ~= "string" or #pluginId < 8 then
	pluginId = HttpService:GenerateGUID(false)
	plugin:SetSetting("MultiScriptPluginId", pluginId)
end

local toolbar = plugin:CreateToolbar("Multi-Script")
local toggleButton = toolbar:CreateButton("Multi-Script Companion", "Secure MCP tools, health, and project readiness", "rbxassetid://4458901886")
toggleButton.ClickableWhenViewportHidden = true
local widget = plugin:CreateDockWidgetPluginGui("MultiScriptCompanion_v8", DockWidgetPluginGuiInfo.new(Enum.InitialDockState.Right, false, false, 430, 720, 340, 420))
widget.Title = "Multi-Script Companion"
-- A panel nobody can find is a panel that does not work. Open on first install
-- (so the toolbar button has something to toggle), then remember the choice.
local savedOpen = plugin:GetSetting("MultiScriptWidgetOpen")
widget.Enabled = savedOpen == nil and true or savedOpen == true
toggleButton:SetActive(widget.Enabled)


local disabledTools=plugin:GetSetting("MultiScriptDisabledTools")
if type(disabledTools)~="table" then disabledTools={} end
local TOOL_INFO={
{name="msrb_project_summary",description="Read a bounded live project/service inventory through the elevated companion plugin.",permission="read"},
{name="msrb_get_selection",description="Read the current Studio selection with paths and classes.",permission="read"},
{name="msrb_get_tree",description="Read a bounded instance tree rooted at path.",permission="read"},
{name="msrb_find_instances",description="Find instances by name/class/tag under a bounded root.",permission="read"},
{name="msrb_get_properties",description="Read selected properties, attributes and tags from instances.",permission="read"},
{name="msrb_read_script",description="Read one Script, LocalScript or ModuleScript source with a bounded result. Requires Full elevated mode.",permission="full"},
{name="msrb_search_scripts",description="Search script names/source with bounded matches. Requires Full elevated mode.",permission="full"},
{name="msrb_dependency_graph",description="Find static require() dependencies between project scripts. Requires Full elevated mode.",permission="full"},
{name="msrb_export_snapshot",description="Export a bounded JSON-safe snapshot of paths/classes/properties for review or diffing.",permission="read"},
{name="msrb_validate_paths",description="Check whether paths exist and report their classes.",permission="read"},
{name="msrb_set_selection",description="Set Studio selection to exact existing paths.",permission="project"},
{name="msrb_create_instances",description="Create a bounded batch of allowlisted instances. Source is never accepted here.",permission="project"},
{name="msrb_set_properties",description="Set JSON-safe non-Source properties in a bounded batch.",permission="project"},
{name="msrb_set_attributes",description="Set or clear attributes in a bounded batch; use {\"__type\":\"Null\"} to clear an attribute.",permission="project"},
{name="msrb_update_tags",description="Add or remove CollectionService tags in a bounded batch.",permission="project"},
{name="msrb_reparent_instances",description="Move instances to an existing parent. Refuses services and cycles.",permission="project"},
{name="msrb_clone_instances",description="Clone instances to an existing parent with optional new names.",permission="project"},
{name="msrb_bulk_rename",description="Rename exact instances with optional plain-text find/replace.",permission="project"},
{name="msrb_patch_script",description="Apply exact-match source replacements to one script with optional all-match replacement. Requires Full elevated mode.",permission="full"},
{name="msrb_replace_script",description="Replace the current editor source atomically, preserving concurrent user edits. Full access required. Sources over 32768 UTF-8 bytes automatically use msrb_source_transfer when selected; max 4 MiB, never clipped.",permission="full"},
{name="msrb_delete_instances",description="Delete exact instances after bridge/plugin trust checks. Services are refused. Requires Full elevated mode.",permission="full"},
{name="msrb_checkpoint",description="Create an explicit Studio undo waypoint.",permission="project"},
{name="msrb_undo",description="Undo the latest Studio change. Requires Full elevated mode.",permission="full"},
{name="msrb_redo",description="Redo the latest Studio change. Requires Full elevated mode.",permission="full"},
{name="msrb_console_read",description="Read actual Studio/bridge execution receipts and permitted output. Metadata is visible in Read; privileged output requires its original tier. Receipts are not project verification.",permission="read"},
{name="msrb_source_transfer",description="Stage a large Script/LocalScript/ModuleScript source without executing it. begin captures the current editor buffer; append uses UTF-8 byte offsets and <=32768 bytes per chunk; commit atomically replaces only the unchanged buffer. status recovers uncertain commit outcomes; abort discards staging. Max 4 MiB. Prefer msrb_replace_script: the bridge chunks large sources automatically.",permission="full"},
}
-- Raised brick surfaces and quiet stud details share Multi-Script's dark palette.
local T={mono0=Color3.fromRGB(12,15,21),mono1=Color3.fromRGB(21,26,34),mono2=Color3.fromRGB(30,37,47),mono3=Color3.fromRGB(43,52,64),ink=Color3.fromRGB(240,245,250),ink2=Color3.fromRGB(197,210,223),ink3=Color3.fromRGB(159,177,195),ink4=Color3.fromRGB(141,161,182),accent=Color3.fromRGB(133,229,190),good=Color3.fromRGB(133,229,190),warn=Color3.fromRGB(255,205,126),bad=Color3.fromRGB(255,153,158)}
local function make(class,parent,props)
 local obj=Instance.new(class);if parent and (class=='Frame' or class=='TextLabel' or class=='TextButton' or class=='TextBox') then obj.LayoutOrder=#parent:GetChildren() end;for key,value in pairs(props or {}) do obj[key]=value end;obj.Parent=parent;return obj
end
local function corner(parent,r) return make('UICorner',parent,{CornerRadius=UDim.new(0,r or 8)}) end
local function hairline(parent) return make('UIStroke',parent,{Color=T.ink3,Transparency=0.78,Thickness=1,ApplyStrokeMode=Enum.ApplyStrokeMode.Border}) end
local function pad(parent,n) return make('UIPadding',parent,{PaddingLeft=UDim.new(0,n),PaddingRight=UDim.new(0,n),PaddingTop=UDim.new(0,n),PaddingBottom=UDim.new(0,n)}) end
local function stack(parent,gap) return make('UIListLayout',parent,{Padding=UDim.new(0,gap or 10),SortOrder=Enum.SortOrder.LayoutOrder}) end
local function label(parent,text,height,size)
 return make('TextLabel',parent,{BackgroundTransparency=1,Size=UDim2.new(1,0,0,height or 36),AutomaticSize=Enum.AutomaticSize.Y,Font=Enum.Font.Gotham,TextSize=size or 13,TextColor3=T.ink2,Text=text,TextWrapped=true,TextXAlignment=Enum.TextXAlignment.Left,TextYAlignment=Enum.TextYAlignment.Center})
end
local function button(parent,text,height)
 local b=make('TextButton',parent,{TextWrapped=true,BackgroundColor3=T.mono3,BorderSizePixel=0,Size=UDim2.new(1,0,0,height or 36),Font=Enum.Font.GothamMedium,TextSize=13,TextColor3=T.ink,Text=text,AutoButtonColor=true});corner(b);hairline(b);return b
end
local function card(parent,title)
 local box=make('Frame',parent,{BackgroundColor3=T.mono1,BorderSizePixel=0,Size=UDim2.new(1,0,0,0),AutomaticSize=Enum.AutomaticSize.Y});corner(box,10);hairline(box);pad(box,12);stack(box,8)
 local heading=label(box,title,22,14);heading.Font=Enum.Font.GothamBold;heading.TextColor3=T.ink;return box
end
local U={tabs={},pages={},toolRows={}}
local root=make('Frame',widget,{Name='MultiScriptStudio',Size=UDim2.fromScale(1,1),BackgroundColor3=T.mono0,BorderSizePixel=0})
local header=make('Frame',root,{Name='BrickHeader',Size=UDim2.new(1,0,0,100),BackgroundColor3=T.mono1,BorderSizePixel=0});pad(header,16)
local brand=label(header,'✦ Multi-Script',30,21);brand.Font=Enum.Font.GothamBold;brand.TextColor3=T.ink
local subtitle=label(header,'STUDIO WORKBENCH   ·   v'..PLUGIN_VERSION,22,11);subtitle.Position=UDim2.fromOffset(0,35);subtitle.TextColor3=T.accent
for i=1,6 do
 local stud=make('Frame',header,{Name='Stud',Position=UDim2.new(1,-18-(i-1)*22,0,3),Size=UDim2.fromOffset(15,15),BackgroundColor3=T.mono3,BackgroundTransparency=0.25,BorderSizePixel=0});corner(stud,8);hairline(stud)
 make('UIGradient',stud,{Rotation=90,Color=ColorSequence.new(T.ink3,T.mono2)})
end
local nav=make('Frame',root,{Name='Navigation',Position=UDim2.fromOffset(12,106),Size=UDim2.new(1,-24,0,36),BackgroundTransparency=1})
for i,id in ipairs({'Overview','Toolset','Console','Guide'}) do
 local b=button(nav,id,36);b.Name=id;b.Size=UDim2.new(0.25,-5,1,0);b.Position=UDim2.new((i-1)/4,(i-1)*1.5,0,0);b.TextSize=12;U.tabs[id]=b
 local page=make('ScrollingFrame',root,{Name=id,Position=UDim2.fromOffset(12,152),Size=UDim2.new(1,-24,1,-184),BackgroundTransparency=1,BorderSizePixel=0,ScrollBarThickness=4,ScrollBarImageColor3=T.ink3,CanvasSize=UDim2.new(),AutomaticCanvasSize=Enum.AutomaticSize.Y,Visible=i==1});pad(page,2);stack(page,10);U.pages[id]=page
end
U.current='Overview'
local function showTab(id)
 U.current=id;for name,page in pairs(U.pages) do page.Visible=name==id;U.tabs[name].BackgroundColor3=name==id and T.mono3 or T.mono1;U.tabs[name].TextColor3=name==id and T.accent or T.ink2 end
end
for id,b in pairs(U.tabs) do b.Activated:Connect(function() showTab(id) end) end
local footer=label(root,'Local bridge · actual results · your tool permissions',24,11);footer.Position=UDim2.new(0,14,1,-27);footer.Size=UDim2.new(1,-28,0,24);footer.TextColor3=T.ink3
local statusCard=card(U.pages.Overview,'Connection surfaces')
local bridgeStatus=label(statusCard,'Bridge: checking…',34)
local studioStatus=label(statusCard,'Official Studio MCP: checking…',52)
local compatibilityStatus=label(statusCard,'Version compatibility: checking…',34)
local permissionStatus=label(statusCard,'Plugin toolset: Off',42)
local refreshButton=button(statusCard,'Refresh connection')
local projectCard=card(U.pages.Overview,'Current place')
local projectStatus=label(projectCard,'Inventory: waiting for inspection',44)
local selectionStatus=label(projectCard,'Selection: none',36)
local readinessStatus=label(projectCard,'Readiness: not scanned',34)
local barTrack=make('Frame',projectCard,{Size=UDim2.new(1,0,0,5),BackgroundColor3=T.mono3,BorderSizePixel=0});corner(barTrack,3)
local readinessBar=make('Frame',barTrack,{Size=UDim2.fromScale(0,1),BackgroundColor3=T.accent,BorderSizePixel=0});corner(readinessBar,3)
local scanButton=button(projectCard,'Run non-destructive readiness scan')
local diagnosticsButton=button(projectCard,'Print sanitized diagnostics')
local catalogButton=button(projectCard,'Inspect available tool catalog')
local accessCard=card(U.pages.Toolset,'Your Studio toolset')
U.master=button(accessCard,'☐ Enable plugin toolset',40)
label(accessCard,'The checkbox enables these companion tools. Roblox’s official MCP server is a separate connection for execute_luau, playtests and native capture.',72,12)
local readButton=button(accessCard,'Read · inspect without project edits')
local projectButton=button(accessCard,'Project · objects and properties')
local fullButton=button(accessCard,'Full · script editing and source transfer')
local disableButton=button(accessCard,'Turn toolset off')
U.search=make('TextBox',U.pages.Toolset,{Name='FindTool',Size=UDim2.new(1,0,0,38),BackgroundColor3=T.mono2,BorderSizePixel=0,Font=Enum.Font.Gotham,TextSize=13,TextColor3=T.ink,PlaceholderText='Find a tool…',PlaceholderColor3=T.ink3,Text='',ClearTextOnFocus=false});corner(U.search);pad(U.search,9)
local registerMode,disableExecution,refreshConsole,syncToolSelection,refresh
for _,tool in ipairs(TOOL_INFO) do
 local row=card(U.pages.Toolset,tool.name);local toggle=button(row,'',32);label(row,tool.description,66,12)
 U.toolRows[tool.name]={row=row,toggle=toggle,search=(tool.name..' '..tool.description):lower(),permission=tool.permission}
 toggle.Activated:Connect(function()
  disabledTools[tool.name]=not disabledTools[tool.name];pcall(function() plugin:SetSetting('MultiScriptDisabledTools',disabledTools) end)
  if syncToolSelection then task.spawn(syncToolSelection) end
 end)
end
U.search:GetPropertyChangedSignal('Text'):Connect(function() local q=U.search.Text:lower();for _,row in pairs(U.toolRows) do row.row.Visible=q=='' or row.search:find(q,1,true)~=nil end end)
local consoleCard=card(U.pages.Console,'Execution console')
label(consoleCard,'Actual tool receipts and permitted output from this bridge. The AI reads this same console with msrb_console_read. A green receipt means one command returned, not that the game is finished.',86,12)
U.consoleState=label(consoleCard,'Enable Read or higher in Toolset to connect the console.',46,12)
U.consoleRefresh=button(consoleCard,'Refresh execution receipts')
U.consoleRows=make('Frame',U.pages.Console,{BackgroundTransparency=1,Size=UDim2.new(1,0,0,0),AutomaticSize=Enum.AutomaticSize.Y});stack(U.consoleRows,8)
local guide=card(U.pages.Guide,'Choose the right workspace')
label(guide,'Studio engine: edits the real connected editor. Enable native Studio MCP for execute_luau, screenshots and playtests. The companion toolset adds curated object/script operations.',100,13)
label(guide,'Chat studio: intentionally engine-free. It creates code, designs and local general-tool artifacts in the chat. A globally connected Studio is not attached to this mode.',92,13)
label(guide,'Build software: uses the desktop workspace folder and file/build permissions you select. Engine access is a separate optional add-on. It does not require Roblox.',100,13)
local media=card(U.pages.Guide,'Sounds, motion and source')
label(media,'Interface sounds are browser notification tones. Live themes animate Multi-Script’s interface. Neither adds audio or animation to your game.',84,13)
label(media,'Game audio: generate/import a real WAV or use a licensed uploaded SoundId, then configure Sound/Audio objects and test playback. A local file is not a Roblox asset ID.',92,13)
label(media,'Game animation: inspect the rig, author or import a real clip, connect its AnimationId/Animator and test transitions. The AI needs native tools and usable asset permissions.',100,13)
label(media,'Large scripts: use msrb_replace_script with Full access; the bridge stages UTF-8 chunks and commits once through ScriptEditorService. Luau compiler limits still require modules and sensible function scopes.',112,13)
local function color(item,state) item.TextColor3=state=='good' and T.good or state=='bad' and T.bad or T.warn end
local function setReadiness(value) local n=math.clamp(tonumber(value) or 0,0,100);readinessBar.Size=UDim2.fromScale(n/100,1);readinessBar.BackgroundColor3=n>=80 and T.good or n>=50 and T.warn or T.bad;readinessStatus.Text='Heuristic readiness: '..tostring(n)..'/100 · not a playtest' end
showTab('Overview')
local function request(method, route, body, authorized)
	local headers={Accept="application/json"}
	if body ~= nil then headers["Content-Type"]="application/json" end
	if authorized and sessionToken then headers.Authorization="Bearer "..sessionToken end
	return HttpService:RequestAsync({Url=BRIDGE_URL..route, Method=method, Headers=headers, Body=body and HttpService:JSONEncode(body) or nil})
end
local function decodeResponse(response)
	if not response or not response.Success then return nil end
	local ok,data=pcall(function() return HttpService:JSONDecode(response.Body) end)
	return ok and data or nil
end
local function safeName(value)
	local s=tostring(value or ""):sub(1,100)
	if s=="" or s:find("[%z\1-\31]") then error("invalid instance name") end
	return s
end
local function pathOf(inst) return inst:GetFullName() end
local function splitPath(path)
	local clean=tostring(path or ""):gsub("^game[%.%/]?",""):gsub("/",".")
	local parts={}; for part in clean:gmatch("[^%.]+") do table.insert(parts,part) end; return parts
end
local function resolve(path)
	local parts=splitPath(path); if #parts==0 or not ROOT_NAMES[parts[1]] then return nil end
	local ok,current=pcall(function() return game:GetService(parts[1]) end); if not ok then return nil end
	for i=2,#parts do current=current:FindFirstChild(parts[i]); if not current then return nil end end
	return current
end
local function isRoot(inst) return inst.Parent==game and ROOT_NAMES[inst.Name]==true end
local function bounded(value, fallback, low, high) value=tonumber(value) or fallback; return math.max(low,math.min(high,math.floor(value))) end
local function listBound(value, max) if type(value)~="table" then return {} end; local out={}; for i=1,math.min(#value,max) do out[i]=value[i] end; return out end

local function encodeValue(value, depth)
	depth=depth or 0; if depth>4 then return "<depth-limit>" end
	local kind=typeof(value)
	if kind=="nil" or kind=="boolean" or kind=="number" or kind=="string" then return value end
	if kind=="Instance" then return {__type="Instance",path=pathOf(value),className=value.ClassName} end
	if kind=="Vector2" then return {__type="Vector2",x=value.X,y=value.Y} end
	if kind=="Vector3" then return {__type="Vector3",x=value.X,y=value.Y,z=value.Z} end
	if kind=="Color3" then return {__type="Color3",r=value.R,g=value.G,b=value.B} end
	if kind=="CFrame" then return {__type="CFrame",components={value:GetComponents()}} end
	if kind=="UDim" then return {__type="UDim",scale=value.Scale,offset=value.Offset} end
	if kind=="UDim2" then return {__type="UDim2",x={scale=value.X.Scale,offset=value.X.Offset},y={scale=value.Y.Scale,offset=value.Y.Offset}} end
	if kind=="BrickColor" then return {__type="BrickColor",name=value.Name} end
	if kind=="EnumItem" then return {__type="Enum",value=tostring(value)} end
	if kind=="table" then local out={}; local n=0; for k,v in pairs(value) do n=n+1; if n>200 then break end; out[tostring(k)]=encodeValue(v,depth+1) end; return out end
	return tostring(value)
end
local function decodeValue(value)
	if type(value)~="table" or type(value.__type)~="string" then return value end
	local t=value.__type
	if t=="Vector2" then return Vector2.new(tonumber(value.x) or 0,tonumber(value.y) or 0) end
	if t=="Vector3" then return Vector3.new(tonumber(value.x) or 0,tonumber(value.y) or 0,tonumber(value.z) or 0) end
	if t=="Color3" then return Color3.new(tonumber(value.r) or 0,tonumber(value.g) or 0,tonumber(value.b) or 0) end
	if t=="CFrame" and type(value.components)=="table" and #value.components==12 then return CFrame.new(table.unpack(value.components)) end
	if t=="UDim" then return UDim.new(tonumber(value.scale) or 0,tonumber(value.offset) or 0) end
	if t=="UDim2" then local x=value.x or {}; local y=value.y or {}; return UDim2.new(tonumber(x.scale) or 0,tonumber(x.offset) or 0,tonumber(y.scale) or 0,tonumber(y.offset) or 0) end
	if t=="BrickColor" then return BrickColor.new(tostring(value.name or "Medium stone grey")) end
	if t=="Instance" then return resolve(value.path) end
	if t=="Null" then return nil end
	if t=="Enum" then local enumName,item=tostring(value.value or ""):match("^Enum%.([%w_]+)%.([%w_]+)$"); if enumName and Enum[enumName] then return Enum[enumName][item] end end
	error("unsupported tagged value: "..t)
end
local function descriptor(inst) return {path=pathOf(inst),name=inst.Name,className=inst.ClassName,tags=CollectionService:GetTags(inst),attributes=encodeValue(inst:GetAttributes())} end
local function inventory()
	local result={scripts=0,modules=0,remotes=0,animations=0,sounds=0,particleEmitters=0,screenGuis=0,descendants=0}
	for _,inst in pairs(game:GetDescendants()) do result.descendants=result.descendants+1; if inst:IsA("ModuleScript") then result.modules=result.modules+1 elseif inst:IsA("LuaSourceContainer") then result.scripts=result.scripts+1 elseif inst:IsA("RemoteEvent") or inst:IsA("RemoteFunction") then result.remotes=result.remotes+1 elseif inst:IsA("Animation") then result.animations=result.animations+1 elseif inst:IsA("Sound") then result.sounds=result.sounds+1 elseif inst:IsA("ParticleEmitter") then result.particleEmitters=result.particleEmitters+1 elseif inst:IsA("ScreenGui") then result.screenGuis=result.screenGuis+1 end end
	return result
end
local function waypoint(labelText) pcall(function() ChangeHistoryService:SetWaypoint("Multi-Script: "..tostring(labelText):sub(1,100)) end) end
local function setProperties(inst, props)
	local changed={}; if type(props)~="table" then return changed end
	for name,value in pairs(props) do
		if type(name)~="string" or not name:match("^[%a_][%w_]*$") or BLOCKED_PROPERTIES[name] then error("blocked property: "..tostring(name)) end
		local ok,err=pcall(function() inst[name]=decodeValue(value) end); if not ok then error("cannot set "..pathOf(inst).."."..name..": "..tostring(err)) end; table.insert(changed,name)
	end
	return changed
end
local function exactReplace(source, old, new, replaceAll)
	-- Patch is a REPLACE, so an empty needle has no meaning here. Say what to use
	-- instead rather than a bare "cannot be empty" - the companion has a dedicated
	-- whole-source tool, and a caller that wanted to create or overwrite a script
	-- wants that one.
	if old=="" then error("old_string cannot be empty: msrb_patch_script replaces an exact match, so use msrb_replace_script to set a whole script source, or supply the exact existing text to patch") end
	local out,count,pos={},0,1
	while true do local a,b=string.find(source,old,pos,true); if not a then table.insert(out,string.sub(source,pos)); break end; table.insert(out,string.sub(source,pos,a-1)); table.insert(out,new); count=count+1; pos=b+1; if not replaceAll then table.insert(out,string.sub(source,pos)); break end end
	return table.concat(out),count
end

local ScriptEditorService=game:GetService('ScriptEditorService')
local transfers={}
local function editorSource(inst) return ScriptEditorService:GetEditorSource(inst) end
local function replaceSource(inst,source,expected)
 local conflict=false
 ScriptEditorService:UpdateSourceAsync(inst,function(current)
  if current~=expected then conflict=true;return nil end
  return source
 end)
 if conflict then error('Script editor changed during this edit. Nothing was replaced; re-read and merge the current buffer.') end
 if editorSource(inst)~=source then error('Editor read-back did not match. Inspect the script before retrying.') end
end
local function sourceTransfer(a)
 local now=os.clock()
 for id,state in pairs(transfers) do if now-state.updated>600 then transfers[id]=nil end end
 local action=tostring(a.action or '')
 if action=='begin' then
  local total=tonumber(a.total_bytes);if not total or total<0 or total%1~=0 or total>MAX_SOURCE then error('total_bytes must be 0–4194304; split larger code into modules') end
  local count=0;for _,state in pairs(transfers) do if state.status=='staging' then count=count+1 end end;if count>=2 then error('Two source transfers are already staged. Finish or abort one.') end
  local inst=resolve(a.path);if not inst or not inst:IsA('LuaSourceContainer') then error('script not found; create it first with msrb_create_instances') end
  local id=HttpService:GenerateGUID(false);transfers[id]={path=pathOf(inst),inst=inst,base=editorSource(inst),parts={},received=0,total=total,status='staging',updated=now}
  return {transfer_id=id,path=pathOf(inst),received_bytes=0,total_bytes=total,state='staging'}
 end
 local id=tostring(a.transfer_id or '');local state=transfers[id];if not state then error('Unknown or expired transfer; inspect current source before starting another.') end
 state.updated=now
 if action=='status' then return {transfer_id=id,path=state.path,state=state.status,received_bytes=state.received,total_bytes=state.total} end
 if action=='abort' then if state.status=='committed' then return {transfer_id=id,state='committed',note='Already committed; abort cannot undo it.'} end;transfers[id]=nil;return {transfer_id=id,state='aborted',changed=false} end
 if state.status=='committed' and action=='commit' then return {transfer_id=id,path=state.path,state='committed',length=state.total,duplicate=true} end
 if state.status~='staging' then error('Transfer is not staging') end
 if action=='append' then
  local chunk=tostring(a.source or '');local offset=tonumber(a.offset)
  if #chunk>32768 or not utf8.len(chunk) then error('Each chunk must be valid UTF-8 and at most 32768 bytes') end
  if offset==state.lastOffset and chunk==state.lastChunk then return {transfer_id=id,state='staging',received_bytes=state.received,duplicate=true} end
  if offset~=state.received then error('Wrong byte offset; read action=status, do not guess or replay a different chunk') end
  if state.received+#chunk>state.total then error('Chunk exceeds declared total_bytes') end
  table.insert(state.parts,chunk);state.lastOffset=offset;state.lastChunk=chunk;state.received=state.received+#chunk
  return {transfer_id=id,state='staging',received_bytes=state.received,total_bytes=state.total}
 end
 if action=='commit' then
  if state.received~=state.total then error('Source incomplete; no project change made') end
  if resolve(state.path)~=state.inst then error('Target moved or was replaced; no project change made') end
  local source=table.concat(state.parts);waypoint('before staged source commit');replaceSource(state.inst,source,state.base);waypoint('committed staged source')
  state.status='committed';state.parts=nil;state.base=nil;state.lastChunk=nil
  return {transfer_id=id,path=state.path,state='committed',length=#source,readBack=true}
 end
 error('Use begin, append, commit, status or abort')
end

local handlers={}
handlers.msrb_project_summary=function(a)
	local data={placeId=game.PlaceId,placeName=game.Name,isRunning=RunService:IsRunning(),selectionCount=#Selection:Get(),inventory=inventory()}
	if a.include_services then data.services={}; for name in pairs(ROOT_NAMES) do local ok,s=pcall(function() return game:GetService(name) end); if ok then data.services[name]=#s:GetDescendants() end end end; return data
end
handlers.msrb_get_selection=function() local out={}; for _,inst in pairs(Selection:Get()) do table.insert(out,descriptor(inst)) end; return {selection=out,count=#out} end
handlers.msrb_get_tree=function(a)
	local rootInst=resolve(a.path); if not rootInst then error("path not found") end; local depth=bounded(a.depth,3,0,8); local limit=bounded(a.limit,200,1,MAX_TREE); local out={}; local function walk(inst,d) if #out>=limit then return end; local row=descriptor(inst); row.depth=d; table.insert(out,row); if d<depth then for _,child in pairs(inst:GetChildren()) do walk(child,d+1); if #out>=limit then break end end end end; walk(rootInst,0); return {root=pathOf(rootInst),instances=out,truncated=#out>=limit}
end
handlers.msrb_find_instances=function(a)
	local rootInst=a.root and resolve(a.root) or game:GetService("Workspace"); if not rootInst then error("root not found") end; local limit=bounded(a.limit,100,1,MAX_TREE); local out={}; local needle=a.name and tostring(a.name):lower() or nil
	local candidates={rootInst}; for _,d in pairs(rootInst:GetDescendants()) do table.insert(candidates,d) end
	for _,inst in pairs(candidates) do if (not needle or inst.Name:lower():find(needle,1,true)) and (not a.class_name or inst:IsA(tostring(a.class_name))) and (not a.tag or CollectionService:HasTag(inst,tostring(a.tag))) then table.insert(out,descriptor(inst)); if #out>=limit then break end end end; return {matches=out,count=#out,truncated=#out>=limit}
end
handlers.msrb_get_properties=function(a)
	local result={}; for _,path in pairs(listBound(a.paths,100)) do local inst=resolve(path); if inst then local row=descriptor(inst); row.properties={}; for _,name in pairs(listBound(a.properties,80)) do local ok,v=pcall(function() if tostring(name)=="Source" then return "Use Full-tier msrb_read_script for source" end;return inst[tostring(name)] end); row.properties[tostring(name)]=ok and encodeValue(v) or "<unreadable>" end; table.insert(result,row) else table.insert(result,{path=path,error="not found"}) end end; return {instances=result}
end
handlers.msrb_read_script=function(a)
 local inst=resolve(a.path);if not inst or not inst:IsA("LuaSourceContainer") then error("script not found") end
 local source=editorSource(inst);local cap=bounded(a.max_chars,32000,1,200000);local offset=bounded(a.offset,0,0,#source)
 while offset>0 and offset<#source and string.byte(source,offset+1)>=128 and string.byte(source,offset+1)<192 do offset=offset-1 end
 local finish=math.min(#source,offset+cap)
 while finish<#source and string.byte(source,finish+1)>=128 and string.byte(source,finish+1)<192 do finish=finish-1 end
 return {path=pathOf(inst),className=inst.ClassName,source=source:sub(offset+1,finish),length=#source,offset=offset,next_offset=finish<#source and finish or nil,truncated=finish<#source,sourceSurface="current Script Editor buffer"}
end
handlers.msrb_search_scripts=function(a)
	local rootInst=a.root and resolve(a.root) or game; if not rootInst then error("root not found") end; local query=tostring(a.query or ""); if query=="" then error("query is required") end; local limit=bounded(a.limit,100,1,MAX_TREE); local out={}; for _,inst in pairs(rootInst:GetDescendants()) do if inst:IsA("LuaSourceContainer") then local ok,source=pcall(function() return editorSource(inst) end); local found=inst.Name:lower():find(query:lower(),1,true); if ok and not found then local success,index=pcall(string.find,source,query,1,a.plain~=false); found=success and index end; if found then table.insert(out,{path=pathOf(inst),className=inst.ClassName,length=ok and #source or nil}); if #out>=limit then break end end end end; return {matches=out,count=#out,truncated=#out>=limit}
end
handlers.msrb_dependency_graph=function(a)
	local rootInst=a.root and resolve(a.root) or game; if not rootInst then error("root not found") end; local limit=bounded(a.limit,200,1,MAX_TREE); local out={}; for _,inst in pairs(rootInst:GetDescendants()) do if inst:IsA("LuaSourceContainer") then local ok,source=pcall(function() return editorSource(inst) end); if ok then local deps={}; for expr in source:gmatch("require%s*%(([^%)]+)%)") do table.insert(deps,expr:sub(1,240)); if #deps>=50 then break end end; if #deps>0 then table.insert(out,{path=pathOf(inst),requires=deps}); if #out>=limit then break end end end end end; return {scripts=out,count=#out,truncated=#out>=limit}
end
handlers.msrb_export_snapshot=function(a)
	local tree=handlers.msrb_get_tree({path=a.root,depth=a.depth,limit=a.limit}); local props=listBound(a.properties,40); for _,row in pairs(tree.instances) do local inst=resolve(row.path); row.properties={}; for _,name in pairs(props) do local ok,v=pcall(function() if tostring(name)=="Source" then return "Use Full-tier msrb_read_script for source" end;return inst[tostring(name)] end); if ok then row.properties[tostring(name)]=encodeValue(v) end end end; return tree
end
handlers.msrb_validate_paths=function(a) local out={}; for _,path in pairs(listBound(a.paths,MAX_BATCH)) do local inst=resolve(path); table.insert(out,{path=path,exists=inst~=nil,className=inst and inst.ClassName or nil}) end; return {paths=out} end
handlers.msrb_set_selection=function(a) local selected={}; for _,path in pairs(listBound(a.paths,100)) do local inst=resolve(path); if not inst then error("path not found: "..tostring(path)) end; table.insert(selected,inst) end; Selection:Set(selected); return {count=#selected} end
handlers.msrb_create_instances=function(a)
	local made={}; waypoint("before create"); for _,spec in pairs(listBound(a.instances,100)) do local class=tostring(spec.class_name or ""); if not CREATE_CLASSES[class] then error("class is not allowlisted: "..class) end; local parent=resolve(spec.parent); if not parent then error("parent not found") end; local inst=Instance.new(class); inst.Name=spec.name and safeName(spec.name) or class; setProperties(inst,spec.properties); if type(spec.attributes)=="table" then for k,v in pairs(spec.attributes) do inst:SetAttribute(tostring(k):sub(1,100),decodeValue(v)) end end; for _,tag in pairs(listBound(spec.tags,50)) do CollectionService:AddTag(inst,tostring(tag):sub(1,100)) end; inst.Parent=parent; table.insert(made,descriptor(inst)) end; waypoint("created instances"); return {created=made,count=#made}
end
handlers.msrb_set_properties=function(a) local out={}; waypoint("before properties"); for _,change in pairs(listBound(a.changes,MAX_BATCH)) do local inst=resolve(change.path); if not inst then error("path not found") end; table.insert(out,{path=pathOf(inst),properties=setProperties(inst,change.properties)}) end; waypoint("set properties"); return {changed=out,count=#out} end
handlers.msrb_set_attributes=function(a) local n=0; waypoint("before attributes"); for _,change in pairs(listBound(a.changes,MAX_BATCH)) do local inst=resolve(change.path); if not inst then error("path not found") end; for k,v in pairs(change.attributes or {}) do inst:SetAttribute(tostring(k):sub(1,100),decodeValue(v)); n=n+1 end end; waypoint("set attributes"); return {changed=n} end
handlers.msrb_update_tags=function(a) local n=0; waypoint("before tags"); for _,change in pairs(listBound(a.changes,MAX_BATCH)) do local inst=resolve(change.path); if not inst then error("path not found") end; for _,tag in pairs(listBound(change.add,50)) do CollectionService:AddTag(inst,tostring(tag):sub(1,100)); n=n+1 end; for _,tag in pairs(listBound(change.remove,50)) do CollectionService:RemoveTag(inst,tostring(tag):sub(1,100)); n=n+1 end end; waypoint("updated tags"); return {changed=n} end
handlers.msrb_reparent_instances=function(a) local out={}; waypoint("before reparent"); for _,move in pairs(listBound(a.moves,100)) do local inst,parent=resolve(move.path),resolve(move.parent); if not inst or not parent then error("path or parent not found") end; if isRoot(inst) or parent==inst or parent:IsDescendantOf(inst) then error("service/cyclic reparent refused") end; inst.Parent=parent; table.insert(out,pathOf(inst)) end; waypoint("reparented instances"); return {moved=out,count=#out} end
handlers.msrb_clone_instances=function(a) local out={}; waypoint("before clone"); for _,spec in pairs(listBound(a.clones,100)) do local inst,parent=resolve(spec.path),resolve(spec.parent); if not inst or not parent or isRoot(inst) then error("path or parent invalid") end; local clone=inst:Clone(); if spec.name then clone.Name=safeName(spec.name) end; clone.Parent=parent; table.insert(out,descriptor(clone)) end; waypoint("cloned instances"); return {cloned=out,count=#out} end
handlers.msrb_bulk_rename=function(a) local out={}; waypoint("before rename"); for _,change in pairs(listBound(a.changes,MAX_BATCH)) do local inst=resolve(change.path); if not inst or isRoot(inst) then error("path invalid") end; inst.Name=safeName(change.name); table.insert(out,pathOf(inst)) end; waypoint("renamed instances"); return {renamed=out,count=#out} end
handlers.msrb_patch_script=function(a)
	local inst=resolve(a.path); if not inst or not inst:IsA("LuaSourceContainer") then error("script not found") end; local source=editorSource(inst);local original=source; local total=0; waypoint("before script patch"); for _,edit in pairs(listBound(a.edits,50)) do local count; source,count=exactReplace(source,tostring(edit.old_string or ""),tostring(edit.new_string or ""),edit.replace_all==true); if count==0 then error("exact old_string was not found") end; total=total+count; if #source>MAX_SOURCE then error("patched source exceeds 4 MiB; split larger code into modules") end end; replaceSource(inst,source,original); waypoint("patched script"); return {path=pathOf(inst),replacements=total,length=#source}
end
handlers.msrb_replace_script=function(a)
 local inst=resolve(a.path);if not inst or not inst:IsA("LuaSourceContainer") then error("script not found") end
 local source=tostring(a.source or "");if #source>MAX_SOURCE then error("Source exceeds 4 MiB; split larger code into modules") end
 local original=editorSource(inst);waypoint("before source replacement");replaceSource(inst,source,original);waypoint("replaced script")
 return {path=pathOf(inst),length=#source,readBack=true}
end
handlers.msrb_delete_instances=function(a) local removed={}; waypoint("before delete"); for _,path in pairs(listBound(a.paths,100)) do local inst=resolve(path); if not inst or isRoot(inst) then error("missing path or service deletion refused") end; table.insert(removed,pathOf(inst)); inst:Destroy() end; waypoint("deleted instances"); return {deleted=removed,count=#removed} end
handlers.msrb_checkpoint=function(a) waypoint(a.label or "checkpoint"); return {created=true} end
handlers.msrb_undo=function() ChangeHistoryService:Undo(); return {undone=true} end
handlers.msrb_redo=function() ChangeHistoryService:Redo(); return {redone=true} end

handlers.msrb_source_transfer=sourceTransfer
handlers.msrb_console_read=function() local data=decodeResponse(request("GET","/plugin/console",nil,true));if not data then error("Execution console unavailable") end;return data end

local function selectedTools()
 local names={};for _,tool in ipairs(TOOL_INFO) do if not disabledTools[tool.name] then table.insert(names,tool.name) end end;return names
end
local function updatePermissionStatus()
 local count=0
 for name,row in pairs(U.toolRows) do
  local selected=not disabledTools[name];local allowed=PERMISSION_RANK[executionMode]>=PERMISSION_RANK[row.permission]
  row.toggle.Text=(selected and "☑ " or "☐ ")..(selected and "Selected" or "Disabled").." · "..row.permission
  row.toggle.TextColor3=selected and T.accent or T.ink3
  if selected and allowed then count=count+1 end
 end
 U.master.Text=executionMode=="off" and "☐ Enable plugin toolset" or "☑ Plugin toolset enabled"
 permissionStatus.Text=executionMode=="off" and "Plugin toolset: Off · choose tools in the Toolset tab" or ("Plugin toolset: "..executionMode.." · "..count.." allowed tools")
 color(permissionStatus,executionMode=="off" and "warn" or "good")
end
registerMode=function(mode)
 local ok,response=pcall(function() return request("POST","/plugin/register",{pluginVersion=PLUGIN_VERSION,pluginId=pluginId,executionEnabled=true,permissionMode=mode,enabledTools=selectedTools()},false) end)
 local data=ok and decodeResponse(response) or nil
 if not data or type(data.token)~="string" then permissionStatus.Text="Could not enable tools. Start the bridge and allow Studio HTTP Requests.";color(permissionStatus,"bad");return end
 executionMode=mode;sessionToken=data.token;fullConfirmUntil=0;updatePermissionStatus()
end
disableExecution=function()
 if sessionToken then pcall(function() request("POST","/plugin/unregister",{},true) end) end
 executionMode="off";sessionToken=nil;fullConfirmUntil=0
 for id,state in pairs(transfers) do if state.status~="committed" then transfers[id]=nil end end
 updatePermissionStatus()
end
syncToolSelection=function()
 updatePermissionStatus()
 if executionMode~="off" then
  local ok,response=pcall(function() return request("POST","/plugin/toolset",{enabledTools=selectedTools()},true) end)
  if not ok or not decodeResponse(response) then disableExecution();permissionStatus.Text="Tool selection could not reach the bridge. Toolset disabled; enable it again.";color(permissionStatus,"bad") end
 end
end
local function executeJob(job)
 local name=tostring(job.tool or "");local required=TOOL_PERMISSION[name]
 if not required or not handlers[name] then error("tool is not allowlisted") end
 if disabledTools[name] then error("Tool is disabled in the Toolset tab") end
 if PERMISSION_RANK[executionMode]<PERMISSION_RANK[required] or tostring(job.permission or "")~=required then error("permission tier mismatch") end
 if PERMISSION_RANK[required]>=PERMISSION_RANK.project and RunService:IsRunning() then error("Return to Edit mode before changing persistent project objects or source") end
 return handlers[name](type(job.arguments)=="table" and job.arguments or {})
end
local function pollOnce()
 if executionMode=="off" or not sessionToken then return end
 local ok,response=pcall(function() return request("GET","/plugin/next",nil,true) end)
 if ok and response.StatusCode==403 then executionMode="off";sessionToken=nil;updatePermissionStatus();return end
 local data=ok and decodeResponse(response) or nil;if not data or not data.job then return end
 local job=data.job;local success,result=pcall(executeJob,job)
 local payload={id=job.id,result=success and {ok=true,data=result} or {ok=false,error=tostring(result):sub(1,1800)}}
 if #HttpService:JSONEncode(payload)>MAX_OUTPUT then payload.result={ok=false,error="Result exceeds the response budget. Read a smaller page using offset/max_chars; no source was clipped."} end
 local sent,reply=pcall(function() return request("POST","/plugin/result",payload,true) end)
 if not sent or not decodeResponse(reply) then U.consoleState.Text="Result delivery unconfirmed. Inspect the current state before repeating a write.";color(U.consoleState,"warn") end
end
refreshConsole=function()
 if executionMode=="off" then
  U.lastSequence=nil;for _,child in ipairs(U.consoleRows:GetChildren()) do if child:IsA("Frame") then child:Destroy() end end
  U.consoleState.Text="Enable Read or higher in Toolset to read execution receipts.";return
 end
 local ok,data=pcall(handlers.msrb_console_read,{})
 if not ok then U.consoleState.Text=tostring(data):sub(1,150);color(U.consoleState,"warn");return end
 local entries=data.entries or {};U.consoleState.Text=tostring(#entries).." retained receipts · newest first";color(U.consoleState,"good")
 if U.lastSequence==data.lastSequence and U.lastConsoleMode==executionMode then return end;U.lastSequence=data.lastSequence;U.lastConsoleMode=executionMode
 for _,child in ipairs(U.consoleRows:GetChildren()) do if child:IsA("Frame") then child:Destroy() end end
 for i=#entries,math.max(1,#entries-29),-1 do
  local item=entries[i];local box=card(U.consoleRows,(item.status=="error" and "! " or "✓ ")..tostring(item.tool))
  label(box,tostring(item.durationMs or 0).." ms · "..tostring(item.status),22,11)
  local output=label(box,tostring(item.output or "No output"),0,12);output.AutomaticSize=Enum.AutomaticSize.Y;output.TextYAlignment=Enum.TextYAlignment.Top
 end
end
local function readinessScore() local score=lastScan.score; if lastStatus then local roblox=lastStatus.roblox or {}; if roblox.connected then score=math.min(100,score+10) elseif roblox.alive then score=math.max(0,score-10) else score=math.max(0,score-25) end end; return score end
local function heartbeat()
	local inv=inventory(); pcall(function() request("POST","/plugin/heartbeat",{pluginVersion=PLUGIN_VERSION,diagnosticVersion=DIAGNOSTIC_VERSION,placeId=game.PlaceId,placeName=game.Name:sub(1,120),isRunning=RunService:IsRunning(),selectionCount=#Selection:Get(),scriptCount=inv.scripts,moduleCount=inv.modules,readinessScore=readinessScore(),issueCount=lastScan.issueCount,highIssueCount=lastScan.high,scanDurationMs=lastScan.durationMs},false) end)
end
local function updateSelection() local selected=Selection:Get(); if #selected==0 then selectionStatus.Text="Selection: none" else selectionStatus.Text=string.format("Selection: %d instance(s) · first: %s (%s)",#selected,pathOf(selected[1]):sub(1,90),selected[1].ClassName) end end
refresh=function()
	if busy then return end; busy=true
	local ok,response=pcall(function() return request("GET","/status",nil,false) end); local data=ok and decodeResponse(response) or nil
	if data then lastStatus=data; local roblox=data.roblox or {}; local nativeTools=tonumber(roblox.nativeTools) or 0; local bridgeVersion=tostring(data.bridgeVersion or "?"); bridgeStatus.Text=string.format("Bridge: online · v%s · loopback only",bridgeVersion); color(bridgeStatus,"good"); if bridgeVersion==PLUGIN_VERSION then compatibilityStatus.Text="Compatibility: plugin and bridge versions match"; color(compatibilityStatus,"good") else compatibilityStatus.Text=string.format("Compatibility: plugin v%s / bridge v%s · update the older component",PLUGIN_VERSION,bridgeVersion); color(compatibilityStatus,"warn") end; if roblox.connected then studioStatus.Text=string.format("Studio MCP: connected · %d official native + %d companion tools",nativeTools,tonumber(data.companionTools) or 26); color(studioStatus,"good") elseif roblox.alive then studioStatus.Text=string.format("Studio MCP proxy alive, but no usable place · %d cached tools",nativeTools); color(studioStatus,"warn") else studioStatus.Text="Official Studio MCP offline · companion tools can still work when enabled"; color(studioStatus,"warn") end; heartbeat() else bridgeStatus.Text="Bridge: offline, or Studio HTTP Requests are disabled"; color(bridgeStatus,"bad"); studioStatus.Text="Enable Game Settings → Security → Allow HTTP Requests, then start Multi-Script"; color(studioStatus,"warn"); compatibilityStatus.Text="Compatibility unavailable until the bridge responds"; color(compatibilityStatus,"warn") end
	updateSelection(); setReadiness(readinessScore()); busy=false
end

local RISK_PATTERNS={{pattern="loadstring",label="dynamic loadstring execution",severity="high"},{pattern="require%s*%(%s*%d+",label="numeric asset require",severity="high"},{pattern="OnServerInvoke",label="RemoteFunction handler validation",severity="medium"},{pattern="OnServerEvent",label="RemoteEvent handler validation",severity="medium"},{pattern="SetAsync%s*%(",label="consider conflict-safe UpdateAsync",severity="medium"},{pattern="while%s+true%s+do",label="unbounded loop",severity="medium"},{pattern="WaitForChild%s*%([^,%)]*%)",label="WaitForChild without timeout",severity="low"}}
local function scanProject()
	if busy then return end; busy=true; scanButton.Text="Scanning…"; local started=os.clock();local issues={}; local counts={high=0,medium=0,low=0}; local scanned,unreadable,visited=0,0,0
	for _,inst in pairs(game:GetDescendants()) do visited=visited+1; if inst:IsA("LuaSourceContainer") then scanned=scanned+1; local ok,source=pcall(function() return editorSource(inst) end); if ok then for _,entry in pairs(RISK_PATTERNS) do if source:find(entry.pattern) then counts[entry.severity]=counts[entry.severity]+1; table.insert(issues,{path=pathOf(inst),severity=entry.severity,message=entry.label}); if #issues>=100 then break end end end else unreadable=unreadable+1 end end; if #issues>=100 then break end; if visited%150==0 then task.wait() end end
	local duration=math.floor((os.clock()-started)*1000+.5); local score=math.max(0,100-counts.high*12-counts.medium*4-counts.low-unreadable*2); lastScan={score=score,issueCount=#issues,high=counts.high,medium=counts.medium,low=counts.low,scanned=scanned,unreadable=unreadable,durationMs=duration}; setReadiness(score); readinessStatus.Text=string.format("Readiness: %d/100 · %d high · %d medium · %d low",score,counts.high,counts.medium,counts.low); color(readinessStatus,counts.high>0 and "bad" or counts.medium>0 and "warn" or "good"); projectStatus.Text=string.format("Project scan: %d scripts · %d unreadable · %d ms",scanned,unreadable,duration); if #issues>0 then local lines={}; for _,issue in pairs(issues) do table.insert(lines,string.format("[%s] %s — %s",issue.severity:upper(),issue.path,issue.message)) end; warn("[Multi-Script] Readiness findings:\n- "..table.concat(lines,"\n- ")) end; scanButton.Text="Run non-destructive readiness scan"; busy=false; heartbeat()
end
local function printCatalog()
	local ok,response=pcall(function() return request("GET","/catalog",nil,false) end); local data=ok and decodeResponse(response) or nil; if not data then projectStatus.Text="Catalog unavailable · check bridge and HTTP Requests"; color(projectStatus,"warn"); return end; projectStatus.Text=string.format("Tools: %d official native · %d direct · %d opt-in companion",tonumber(data.nativeToolCount) or 0,tonumber(data.multiScriptDirectTools) or 0,tonumber(data.companionPluginTools) or 0); color(projectStatus,"good"); local names={}; for _,tool in pairs(data.tools or {}) do table.insert(names,tostring(tool.name or "?")) end; print("[Multi-Script] Official Roblox Studio MCP catalog:\n- "..table.concat(names,"\n- "))
end
local function diagnosticReport() local inv=inventory(); local roblox=lastStatus and lastStatus.roblox or {}; print("[Multi-Script] Sanitized diagnostic report:\n"..HttpService:JSONEncode({product="Multi-Script Companion",pluginVersion=PLUGIN_VERSION,diagnosticVersion=DIAGNOSTIC_VERSION,bridgeVersion=lastStatus and lastStatus.bridgeVersion or nil,studioMcpConnected=roblox.connected==true,officialNativeToolCount=roblox.nativeTools or 0,companionMode=executionMode,placeId=game.PlaceId,placeName=game.Name:sub(1,120),isRunning=RunService:IsRunning(),selectionCount=#Selection:Get(),inventory=inv,readiness=lastScan,privacy="No source, secrets, bearer token, or job payloads are included."})) end


U.master.Activated:Connect(function() task.spawn(function() if executionMode=="off" then registerMode("read") else disableExecution() end end) end)
readButton.Activated:Connect(function() task.spawn(function() registerMode("read") end) end)
projectButton.Activated:Connect(function() task.spawn(function() registerMode("project") end) end)
fullButton.Activated:Connect(function()
 if os.clock()>fullConfirmUntil then fullConfirmUntil=os.clock()+8;fullButton.Text="Confirm Full tools · click again";task.delay(8,function() fullButton.Text="Full · script editing and source transfer" end)
 else fullButton.Text="Full · script editing and source transfer";task.spawn(function() registerMode("full") end) end
end)
disableButton.Activated:Connect(function() task.spawn(disableExecution) end)
U.consoleRefresh.Activated:Connect(function() task.spawn(refreshConsole) end)
toggleButton.Click:Connect(function() widget.Enabled=not widget.Enabled;if widget.Enabled then task.spawn(refresh) end end)
refreshButton.Activated:Connect(function() task.spawn(refresh) end)
scanButton.Activated:Connect(function() task.spawn(scanProject) end)
diagnosticsButton.Activated:Connect(diagnosticReport);catalogButton.Activated:Connect(function() task.spawn(printCatalog) end)
Selection.SelectionChanged:Connect(updateSelection)
widget:GetPropertyChangedSignal("Enabled"):Connect(function() toggleButton:SetActive(widget.Enabled);pcall(function() plugin:SetSetting("MultiScriptWidgetOpen",widget.Enabled) end) end)
plugin.Unloading:Connect(function() alive=false;disableExecution() end)
updatePermissionStatus()
task.spawn(function() while alive do if widget.Enabled then refresh() end;task.wait(STATUS_SECONDS) end end)
task.spawn(function() while alive do if executionMode~="off" then pollOnce() end;task.wait(POLL_SECONDS) end end)
task.spawn(function() while alive do if widget.Enabled and U.current=="Console" then refreshConsole() end;task.wait(2) end end)
return {handlers=handlers,executeJob=executeJob,registerMode=registerMode,disableExecution=disableExecution,ui=U,sourceTransfer=sourceTransfer}
