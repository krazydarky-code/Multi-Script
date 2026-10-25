# SPDX-License-Identifier: GPL-3.0-or-later
"""Roblox Studio tools for engine_toolkit. Each compiles to one Luau program run through
the official Studio MCP `execute_luau` (studio_id injected, argument-safe JSON transport)."""
import re
import time

from engine_toolkit import (tool, run_code, as_list, as_dict, vec3, num, boolean, ToolkitError, _need,
                            snapshot_store, snapshot_get, diff_maps, extract_result)

RB = "roblox"
PATH = {"type": "string", "description": "Dot path such as Workspace.Map.Door (a leading 'game.' is fine)."}
PATHS = {"type": "array", "items": {"type": "string"}, "description": "Dot paths."}
VEC = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}


def _exec(ctx, args, body, label, timeout=None):
    res, call = run_code(ctx, RB, body, args, timeout or int(num(args.get("timeout_seconds"), 120, 5, 600)), label)
    if res.get("dryRun"):
        return {"dryRun": True, "nativeCall": {"tool": call["tool"], "datamodel_type": call["arguments"].get("datamodel_type")}, "code": res["code"]}
    ok = res.pop("ok", True) if isinstance(res, dict) else True
    out = {"ok": ok, "nativeCall": call["tool"]}
    out.update(res if isinstance(res, dict) else {"result": res})
    return out


def _paths(args, *keys):
    out = []
    for k in keys or ("paths", "path"):
        out += [str(x) for x in as_list(args.get(k)) if str(x).strip()]
    return list(dict.fromkeys(out))


@tool(RB, "ms_roblox_list_children",
      "List the children (or descendants up to `depth`) of an instance with class, path, and for parts position/size/anchored. Read-only.",
      {"path": PATH, "depth": {"type": "integer", "minimum": 1, "maximum": 6}, "class_filter": {"type": "string", "description": "Only this class or subclass (IsA)."},
       "limit": {"type": "integer", "minimum": 1, "maximum": 2000}})
def list_children(args, ctx):
    a = dict(args, path=args.get("path") or "Workspace", depth=num(args.get("depth"), 1, 1, 6, True), limit=num(args.get("limit"), 200, 1, 2000, True))
    return _exec(ctx, a, '''
        local root = resolve(A.path)
        local rows = {}
        local function walk(inst, d)
            for _, c in ipairs(inst:GetChildren()) do
                if #rows >= A.limit then return end
                if not A.class_filter or c:IsA(A.class_filter) then
                    local row = brief(c); row.depth = d; row.children = #c:GetChildren(); table.insert(rows, row)
                end
                if d < A.depth then walk(c, d + 1) end
            end
        end
        walk(root, 1)
        R.root = root:GetFullName(); R.count = #rows; R.items = rows
        if #rows >= A.limit then R.truncated = true end
    ''', "list children")


@tool(RB, "ms_roblox_find_instances",
      "Search descendants by name text, class (IsA), CollectionService tag or attribute value. Returns paths and key properties. Read-only.",
      {"root": PATH, "name_contains": {"type": "string"}, "class": {"type": "string"}, "tag": {"type": "string"},
       "attribute_name": {"type": "string"}, "attribute_value": {"description": "String, number or boolean to match."}, "limit": {"type": "integer", "minimum": 1, "maximum": 2000}})
def find_instances(args, ctx):
    a = dict(args, root=args.get("root") or "game", limit=num(args.get("limit"), 100, 1, 2000, True))
    return _exec(ctx, a, '''
        local root = A.root == "game" and game or resolve(A.root)
        local CS = game:GetService("CollectionService")
        local rows, total = {}, 0
        local needle = A.name_contains and string.lower(A.name_contains)
        for _, d in ipairs(root:GetDescendants()) do
            local good = true
            if needle and not string.find(string.lower(d.Name), needle, 1, true) then good = false end
            if good and A.class and not d:IsA(A.class) then good = false end
            if good and A.tag and not CS:HasTag(d, A.tag) then good = false end
            if good and A.attribute_name then
                local v = d:GetAttribute(A.attribute_name)
                if v == nil or (A.attribute_value ~= nil and v ~= A.attribute_value) then good = false end
            end
            if good then
                total = total + 1
                if #rows < A.limit then table.insert(rows, brief(d)) end
            end
        end
        R.total = total; R.items = rows
        if total > A.limit then R.truncated = true end
    ''', "find")


@tool(RB, "ms_roblox_get_properties",
      "Read properties of one instance. Give `properties` to choose, or omit for a sensible set for its class (parts, GUI, lights, sounds, scripts). "
      "Also returns attributes and tags.",
      {"path": PATH, "properties": {"type": "array", "items": {"type": "string"}}}, ["path"])
def get_properties(args, ctx):
    return _exec(ctx, dict(args, properties=as_list(args.get("properties"))), '''
        local inst = resolve(A.path)
        local props = A.properties
        if not props or #props == 0 then
            props = {"Name", "ClassName"}
            local function add(t) for _, p in ipairs(t) do table.insert(props, p) end end
            if inst:IsA("BasePart") then add({"Position", "Size", "Orientation", "Color", "Material", "Transparency", "Anchored", "CanCollide", "CanTouch", "CanQuery", "CastShadow", "Massless", "CollisionGroup"}) end
            if inst:IsA("Model") then add({"PrimaryPart", "WorldPivot"}) end
            if inst:IsA("GuiObject") then add({"Position", "Size", "AnchorPoint", "BackgroundColor3", "BackgroundTransparency", "Visible", "ZIndex", "LayoutOrder"}) end
            if inst:IsA("TextLabel") or inst:IsA("TextButton") or inst:IsA("TextBox") then add({"Text", "TextColor3", "TextSize", "Font"}) end
            if inst:IsA("Light") then add({"Brightness", "Color", "Enabled"}) end
            if inst:IsA("Sound") then add({"SoundId", "Volume", "Looped", "Playing"}) end
            if inst:IsA("LuaSourceContainer") then add({"Disabled"}) end
            if inst:IsA("Script") then add({"RunContext", "Enabled"}) end
        end
        local out = {}
        for _, p in ipairs(props) do
            local ok, v = pcall(function() return inst[p] end)
            out[p] = ok and ser(v) or ("<unreadable: " .. tostring(v) .. ">")
        end
        R.path = inst:GetFullName(); R.properties = out
        R.attributes = {}
        for k, v in pairs(inst:GetAttributes()) do R.attributes[k] = ser(v) end
        R.tags = game:GetService("CollectionService"):GetTags(inst)
        if inst:IsA("LuaSourceContainer") then
            local ok, src = pcall(function() return inst.Source end)
            if ok then R.source_lines = select(2, string.gsub(src, "\\n", "\\n")) + 1; R.source_bytes = #src end
        end
    ''', "get properties")


@tool(RB, "ms_roblox_set_properties",
      "Set properties on one or many instances. Values are coerced to the real type: Vector3 from [x,y,z], Color3 from '#rrggbb' or [r,g,b], "
      "UDim2 from {xs,xo,ys,yo}, Enums from their name ('Neon'), CFrame from {pos:[x,y,z],rot_deg:{x,y,z}}. One undo step in Studio.",
      {"paths": PATHS, "path": PATH, "properties": {"type": "object", "description": "Property -> value."}}, ["properties"], writes=True)
def set_properties(args, ctx):
    paths = _paths(args)
    if not paths:
        raise ToolkitError("give `path` or `paths`")
    return _exec(ctx, dict(args, paths=paths, properties=as_dict(args.get("properties"))), '''
        local done = {}
        for _, p in ipairs(A.paths) do
            local inst = resolve(p)
            local applied = setprops(inst, A.properties)
            table.insert(done, {path = inst:GetFullName(), applied = applied})
        end
        waypoint("set properties")
        R.results = done
    ''', "set properties")


@tool(RB, "ms_roblox_create_instance",
      "Create an instance of any class under a parent with name, properties, attributes and tags. `count` makes several (names get a numeric suffix).",
      {"class_name": {"type": "string"}, "parent": PATH, "name": {"type": "string"}, "properties": {"type": "object"},
       "attributes": {"type": "object"}, "tags": {"type": "array", "items": {"type": "string"}}, "count": {"type": "integer", "minimum": 1, "maximum": 200}},
      ["class_name", "parent"], writes=True)
def create_instance(args, ctx):
    return _exec(ctx, dict(args, properties=as_dict(args.get("properties")), attributes=as_dict(args.get("attributes")), tags=as_list(args.get("tags")),
                           count=num(args.get("count"), 1, 1, 200, True)), '''
        local parent = resolve(A.parent)
        local CS = game:GetService("CollectionService")
        local made = {}
        for i = 1, A.count do
            local inst = Instance.new(A.class_name)
            if A.name then inst.Name = (A.count > 1) and (A.name .. i) or A.name end
            setprops(inst, A.properties)
            for k, v in pairs(A.attributes or {}) do inst:SetAttribute(k, v) end
            for _, t in ipairs(A.tags or {}) do CS:AddTag(inst, t) end
            inst.Parent = parent
            table.insert(made, brief(inst))
        end
        waypoint("create " .. A.class_name)
        R.created = made
    ''', "create instance")


@tool(RB, "ms_roblox_create_part",
      "Create a Part/MeshPart-style block, ball, cylinder, wedge or corner wedge with size, position, rotation, colour, material and physics flags in one call.",
      {"shape": {"type": "string", "enum": ["Block", "Ball", "Cylinder", "Wedge", "CornerWedge"]}, "name": {"type": "string"}, "parent": PATH,
       "size": VEC, "position": VEC, "rotation_deg": VEC, "color": {"type": "string", "description": "Hex like #ff8800."},
       "material": {"type": "string", "description": "Enum.Material name: Plastic, Neon, Wood, Metal, Concrete, Grass, Glass, ..."},
       "transparency": {"type": "number", "minimum": 0, "maximum": 1}, "anchored": {"type": "boolean"}, "can_collide": {"type": "boolean"}}, [], writes=True)
def create_part(args, ctx):
    a = dict(args, shape=str(args.get("shape") or "Block"), parent=args.get("parent") or "Workspace")
    return _exec(ctx, a, '''
        local p = Instance.new(A.shape == "Wedge" and "WedgePart" or (A.shape == "CornerWedge" and "CornerWedgePart" or "Part"))
        if A.shape == "Ball" or A.shape == "Cylinder" or A.shape == "Block" then p.Shape = Enum.PartType[A.shape] end
        p.Name = A.name or "Part"
        p.Anchored = (A.anchored == nil) and true or A.anchored
        if A.size then p.Size = vec3(A.size) end
        local cf = CFrame.new(A.position and vec3(A.position) or Vector3.new(0, 5, 0))
        if A.rotation_deg then cf = cf * CFrame.Angles(math.rad(A.rotation_deg[1] or 0), math.rad(A.rotation_deg[2] or 0), math.rad(A.rotation_deg[3] or 0)) end
        p.CFrame = cf
        if A.color then p.Color = col3(A.color) end
        if A.material then p.Material = Enum.Material[A.material] end
        if A.transparency then p.Transparency = A.transparency end
        if A.can_collide ~= nil then p.CanCollide = A.can_collide end
        p.Parent = resolve(A.parent)
        waypoint("create part")
        R.created = brief(p)
    ''', "create part")


@tool(RB, "ms_roblox_build_tree",
      "Build a whole instance tree from one JSON spec - perfect for UI (ScreenGui/Frame/TextLabel/UIListLayout...), models and rigs. Each node: "
      "{class, name, properties, attributes, tags, children:[...]}. Properties use the same coercions as ms_roblox_set_properties. Max 2000 nodes.",
      {"parent": PATH, "tree": {"type": "object", "description": "Root node {class,name,properties,children}."},
       "trees": {"type": "array", "items": {"type": "object"}, "description": "Several root nodes."}}, ["parent"], writes=True)
def build_tree(args, ctx):
    trees = list(as_list(args.get("trees"))) if args.get("trees") else []
    if args.get("tree"):
        trees.insert(0, as_dict(args.get("tree")))
    trees = [as_dict(t) for t in trees if as_dict(t)]
    if not trees:
        raise ToolkitError("give `tree` (or `trees`)", 'Example: {"class":"ScreenGui","name":"HUD","children":[{"class":"TextLabel","name":"Score","properties":{"Text":"0"}}]}')
    return _exec(ctx, dict(args, trees=trees), '''
        local CS = game:GetService("CollectionService")
        local parent = resolve(A.parent)
        local count = 0
        local function build(node, par)
            count = count + 1
            if count > 2000 then error("tree too large (max 2000 nodes)") end
            local cls = node.class or node.Class or node.type or node.ClassName
            if not cls then error("every node needs a `class`") end
            local inst = Instance.new(cls)
            if node.name then inst.Name = node.name end
            setprops(inst, node.properties or node.props)
            for k, v in pairs(node.attributes or {}) do inst:SetAttribute(k, v) end
            for _, t in ipairs(node.tags or {}) do CS:AddTag(inst, t) end
            for _, ch in ipairs(node.children or {}) do build(ch, inst) end
            inst.Parent = par
            return inst
        end
        local roots = {}
        for _, t in ipairs(A.trees) do table.insert(roots, brief(build(t, parent))) end
        waypoint("build tree")
        R.roots = roots; R.nodes = count
    ''', "build tree")


@tool(RB, "ms_roblox_clone_instance",
      "Clone an instance `count` times, each offset from the previous, optionally into a new parent/name.",
      {"path": PATH, "count": {"type": "integer", "minimum": 1, "maximum": 200}, "offset": VEC, "parent": PATH, "new_name": {"type": "string"}}, ["path"], writes=True)
def clone_instance(args, ctx):
    return _exec(ctx, dict(args, count=num(args.get("count"), 1, 1, 200, True)), '''
        local src = resolve(A.path)
        local par = A.parent and resolve(A.parent) or src.Parent
        local off = A.offset and vec3(A.offset) or Vector3.new(0, 0, 0)
        local made, prev = {}, src
        for i = 1, A.count do
            local c = src:Clone()
            if A.new_name then c.Name = (A.count > 1) and (A.new_name .. i) or A.new_name end
            c.Parent = par
            if off.Magnitude > 0 then
                if c:IsA("Model") then c:PivotTo(prev:GetPivot() + off) elseif c:IsA("BasePart") then c.CFrame = prev.CFrame + off end
            end
            prev = c
            table.insert(made, brief(c))
        end
        waypoint("clone")
        R.created = made
    ''', "clone")


@tool(RB, "ms_roblox_delete_instances",
      "Destroy instances by path. Refuses services and the DataModel itself. Returns what was removed.",
      {"paths": PATHS, "path": PATH}, [], writes=True)
def delete_instances(args, ctx):
    paths = _paths(args)
    if not paths:
        raise ToolkitError("give `path` or `paths`")
    return _exec(ctx, dict(args, paths=paths), '''
        local gone = {}
        for _, p in ipairs(A.paths) do
            local inst = resolve(p)
            if inst == game or inst.Parent == game then error("refusing to delete a service: " .. p) end
            table.insert(gone, inst:GetFullName())
            inst:Destroy()
        end
        waypoint("delete")
        R.deleted = gone
    ''', "delete")


@tool(RB, "ms_roblox_move_instance",
      "Re-parent instances (`new_parent`) and/or rename them. For `group=true` the instances are wrapped in a new Model named `group_name`.",
      {"paths": PATHS, "path": PATH, "new_parent": PATH, "new_name": {"type": "string"}, "group": {"type": "boolean"}, "group_name": {"type": "string"}}, [], writes=True)
def move_instance(args, ctx):
    paths = _paths(args)
    if not paths:
        raise ToolkitError("give `path` or `paths`")
    return _exec(ctx, dict(args, paths=paths), '''
        local moved = {}
        local target = A.new_parent and resolve(A.new_parent) or nil
        local grp = nil
        if A.group then
            grp = Instance.new("Model"); grp.Name = A.group_name or "Group"
            grp.Parent = target or resolve(A.paths[1]).Parent
        end
        for _, p in ipairs(A.paths) do
            local inst = resolve(p)
            if A.new_name and #A.paths == 1 then inst.Name = A.new_name end
            if grp then inst.Parent = grp elseif target then inst.Parent = target end
            table.insert(moved, inst:GetFullName())
        end
        waypoint("move")
        R.moved = moved; if grp then R.group = grp:GetFullName() end
    ''', "move")


@tool(RB, "ms_roblox_transform",
      "Move/rotate/resize parts and models. position & rotation_deg are absolute (or added when relative=true); `scale_factor` scales a Model or part uniformly. "
      "Models use PivotTo so pivots are respected.",
      {"paths": PATHS, "path": PATH, "position": VEC, "rotation_deg": VEC, "size": VEC, "scale_factor": {"type": "number", "exclusiveMinimum": 0}, "relative": {"type": "boolean"}}, [], writes=True)
def transform(args, ctx):
    paths = _paths(args)
    if not paths:
        raise ToolkitError("give `path` or `paths`")
    return _exec(ctx, dict(args, paths=paths), '''
        local out = {}
        for _, p in ipairs(A.paths) do
            local inst = resolve(p)
            local isModel, isPart = inst:IsA("Model"), inst:IsA("BasePart")
            if not (isModel or isPart) then error(inst.ClassName .. " cannot be transformed: " .. p) end
            local cf = inst:GetPivot()
            local pos = cf.Position
            if A.position then
                local v = vec3(A.position)
                pos = A.relative and (pos + v) or v
            end
            local rot = cf - cf.Position
            if A.rotation_deg then
                local r = CFrame.Angles(math.rad(A.rotation_deg[1] or 0), math.rad(A.rotation_deg[2] or 0), math.rad(A.rotation_deg[3] or 0))
                rot = A.relative and (rot * r) or r
            end
            inst:PivotTo(CFrame.new(pos) * rot)
            if A.size and isPart then inst.Size = vec3(A.size) end
            if A.scale_factor then
                if isModel then inst:ScaleTo(inst:GetScale() * A.scale_factor) else inst.Size = inst.Size * A.scale_factor end
            end
            table.insert(out, brief(inst))
        end
        waypoint("transform")
        R.results = out
    ''', "transform")


@tool(RB, "ms_roblox_tags",
      "CollectionService tags: action=list|add|remove|find. `find` returns every tagged instance.",
      {"action": {"type": "string", "enum": ["list", "add", "remove", "find"]}, "path": PATH, "tag": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}}, ["action"], writes=True)
def tags(args, ctx):
    return _exec(ctx, dict(args, action=str(args.get("action") or "list").lower(), tags=as_list(args.get("tags")) or ([args["tag"]] if args.get("tag") else [])), '''
        local CS = game:GetService("CollectionService")
        if A.action == "find" then
            local rows = {}
            for _, t in ipairs(A.tags) do for _, i in ipairs(CS:GetTagged(t)) do table.insert(rows, {tag = t, path = i:GetFullName(), class = i.ClassName}) end end
            R.items = rows
        else
            local inst = resolve(A.path)
            if A.action == "add" then for _, t in ipairs(A.tags) do CS:AddTag(inst, t) end
            elseif A.action == "remove" then for _, t in ipairs(A.tags) do CS:RemoveTag(inst, t) end end
            R.path = inst:GetFullName(); R.tags = CS:GetTags(inst)
        end
    ''', "tags")


@tool(RB, "ms_roblox_attributes",
      "Instance attributes: action=get|set|remove. set takes an `attributes` object (numbers, strings, booleans, Vector3 as [x,y,z], Color3 as #hex).",
      {"action": {"type": "string", "enum": ["get", "set", "remove"]}, "path": PATH, "attributes": {"type": "object"}, "names": {"type": "array", "items": {"type": "string"}}}, ["action", "path"], writes=True)
def attributes(args, ctx):
    return _exec(ctx, dict(args, action=str(args.get("action") or "get").lower(), attributes=as_dict(args.get("attributes")), names=as_list(args.get("names"))), '''
        local inst = resolve(A.path)
        if A.action == "set" then
            for k, v in pairs(A.attributes) do
                if type(v) == "table" and #v == 3 then v = Vector3.new(v[1], v[2], v[3]) elseif type(v) == "string" and string.match(v, "^#%x%x%x%x%x%x$") then v = Color3.fromHex(v) end
                inst:SetAttribute(k, v)
            end
            waypoint("set attributes")
        elseif A.action == "remove" then
            for _, n in ipairs(A.names) do inst:SetAttribute(n, nil) end
        end
        R.path = inst:GetFullName(); R.attributes = {}
        for k, v in pairs(inst:GetAttributes()) do R.attributes[k] = ser(v) end
    ''', "attributes")


@tool(RB, "ms_roblox_lighting",
      "Read or change Lighting: `properties` (ClockTime, Brightness, Ambient, OutdoorAmbient, Technology, ...), an `atmosphere` {Density,Offset,Color,Decay,Glare,Haze} "
      "and post effects [{class: Bloom|ColorCorrection|SunRays|DepthOfField|Blur, properties}]. Omit everything to read the current setup.",
      {"properties": {"type": "object"}, "atmosphere": {"type": "object"}, "effects": {"type": "array", "items": {"type": "object"}}}, [], writes=True)
def lighting(args, ctx):
    return _exec(ctx, dict(args, properties=as_dict(args.get("properties")), atmosphere=as_dict(args.get("atmosphere")), effects=[as_dict(e) for e in as_list(args.get("effects"))]), '''
        local L = game:GetService("Lighting")
        setprops(L, A.properties)
        if A.atmosphere and next(A.atmosphere) then
            local at = L:FindFirstChildOfClass("Atmosphere") or Instance.new("Atmosphere", L)
            setprops(at, A.atmosphere)
        end
        for _, e in ipairs(A.effects or {}) do
            local cls = e.class or e.Class
            local fx = L:FindFirstChildOfClass(cls) or Instance.new(cls, L)
            setprops(fx, e.properties or {})
        end
        waypoint("lighting")
        R.lighting = {}
        for _, p in ipairs({"ClockTime", "Brightness", "Ambient", "OutdoorAmbient", "ColorShift_Top", "EnvironmentDiffuseScale", "EnvironmentSpecularScale", "GlobalShadows", "Technology", "ExposureCompensation"}) do
            local ok, v = pcall(function() return L[p] end); if ok then R.lighting[p] = ser(v) end
        end
        R.children = {}
        for _, c in ipairs(L:GetChildren()) do table.insert(R.children, c.ClassName .. ":" .. c.Name) end
    ''', "lighting")


@tool(RB, "ms_roblox_terrain",
      "Terrain edits: action=fill_block|fill_ball|fill_cylinder|fill_wedge|clear|replace_material|stats. position/size/radius/height are in studs.",
      {"action": {"type": "string", "enum": ["fill_block", "fill_ball", "fill_cylinder", "fill_wedge", "clear", "replace_material", "stats"]},
       "material": {"type": "string", "description": "Enum.Material name (Grass, Sand, Water, Rock, Ground, Snow, ...)."}, "to_material": {"type": "string"},
       "position": VEC, "size": VEC, "radius": {"type": "number"}, "height": {"type": "number"}}, ["action"], writes=True)
def terrain(args, ctx):
    return _exec(ctx, dict(args, action=str(args.get("action") or "stats").lower(), material=args.get("material") or "Grass"), '''
        local T = workspace.Terrain
        local act = A.action
        local mat = Enum.Material[A.material]
        local pos = A.position and vec3(A.position) or Vector3.new(0, 0, 0)
        if act == "fill_block" then T:FillBlock(CFrame.new(pos), vec3(A.size or {16, 4, 16}), mat)
        elseif act == "fill_ball" then T:FillBall(pos, A.radius or 8, mat)
        elseif act == "fill_cylinder" then T:FillCylinder(CFrame.new(pos), A.height or 8, A.radius or 8, mat)
        elseif act == "fill_wedge" then T:FillWedge(CFrame.new(pos), vec3(A.size or {8, 8, 8}), mat)
        elseif act == "clear" then T:Clear()
        elseif act == "replace_material" then
            local sz = vec3(A.size or {64, 64, 64})
            T:ReplaceMaterial(Region3.new(pos - sz / 2, pos + sz / 2):ExpandToGrid(4), 4, mat, Enum.Material[A.to_material or "Air"])
        end
        if act ~= "stats" then waypoint("terrain " .. act) end
        R.action = act
        local used = T.MaxExtents
        R.max_extents = {min = ser(used.Min), max = ser(used.Max)}
        R.water = {color = ser(T.WaterColor), wave_size = T.WaterWaveSize, transparency = T.WaterTransparency}
    ''', "terrain " + str(args.get("action")))


@tool(RB, "ms_roblox_script_manage",
      "Create, read, replace, append to, patch or delete a Script/LocalScript/ModuleScript. action=create|read|replace|append|replace_text|delete|configure. "
      "`source` may be given as `lines` (array) so newlines never need JSON escaping. configure sets RunContext/Enabled.",
      {"action": {"type": "string", "enum": ["create", "read", "replace", "append", "replace_text", "delete", "configure"]},
       "path": {"type": "string", "description": "Full path of the script (or of the parent when action=create plus `name`)."},
       "name": {"type": "string"}, "class_name": {"type": "string", "enum": ["Script", "LocalScript", "ModuleScript"]},
       "source": {"type": "string"}, "lines": {"type": "array", "items": {"type": "string"}},
       "find": {"type": "string", "description": "Plain text to find (replace_text)."}, "replace_with": {"type": "string"},
       "run_context": {"type": "string", "enum": ["Legacy", "Server", "Client", "Plugin"]}, "enabled": {"type": "boolean"}}, ["action", "path"], writes=True)
def script_manage(args, ctx):
    act = str(args.get("action") or "read").lower()
    src = "\n".join(str(x) for x in as_list(args.get("lines"))) if args.get("lines") else args.get("source")
    if act in ("create", "replace", "append") and src is None:
        raise ToolkitError(f"{act} needs `source` or `lines`")
    if act == "replace_text" and not args.get("find"):
        raise ToolkitError("replace_text needs `find`")
    return _exec(ctx, dict(args, action=act, source=src, lines=None), '''
        local act = A.action
        local s
        if act == "create" then
            local parent = resolve(A.path)
            s = Instance.new(A.class_name or "Script")
            s.Name = A.name or "NewScript"
            s.Source = A.source
            s.Parent = parent
        else
            s = resolve(A.path)
            if not s:IsA("LuaSourceContainer") then error(s:GetFullName() .. " is a " .. s.ClassName .. ", not a script") end
        end
        if act == "replace" then s.Source = A.source
        elseif act == "append" then s.Source = s.Source .. "\\n" .. A.source
        elseif act == "replace_text" then
            local src = s.Source
            local count = 0
            local out, i = {}, 1
            while true do
                local a, b = string.find(src, A.find, i, true)
                if not a then break end
                table.insert(out, string.sub(src, i, a - 1)); table.insert(out, A.replace_with or ""); i = b + 1; count = count + 1
            end
            table.insert(out, string.sub(src, i))
            if count == 0 then error("text not found in " .. s:GetFullName()) end
            s.Source = table.concat(out)
            R.replacements = count
        elseif act == "configure" then
            if A.run_context and s:IsA("Script") then s.RunContext = Enum.RunContext[A.run_context] end
            if A.enabled ~= nil then if s:IsA("Script") then s.Enabled = A.enabled else s.Disabled = not A.enabled end end
        end
        R.path = s:GetFullName(); R.class = s.ClassName
        if act == "read" then R.source = s.Source end
        local ok, src2 = pcall(function() return s.Source end)
        if ok then R.lines = select(2, string.gsub(src2, "\\n", "\\n")) + 1; R.bytes = #src2 end
        if act == "delete" then s:Destroy(); R.deleted = true end
        if act ~= "read" then waypoint("script " .. act) end
    ''', "script " + act)


@tool(RB, "ms_roblox_script_inventory",
      "Inventory every script under a root: class, path, line count, RunContext/Disabled, and static smells (wait/spawn/delay, deprecated Instance.new parent argument, "
      "loadstring, :connect, while-true without yield). Read-only.",
      {"root": PATH, "limit": {"type": "integer", "minimum": 1, "maximum": 1000}, "only_with_issues": {"type": "boolean"}})
def script_inventory(args, ctx):
    return _exec(ctx, dict(args, root=args.get("root") or "game", limit=num(args.get("limit"), 300, 1, 1000, True)), '''
        local root = A.root == "game" and game or resolve(A.root)
        local rows, issues_total, scanned = {}, 0, 0
        local smells = {
            {"wait(", "%f[%w_]wait%s*%(", "wait() is deprecated - use task.wait"},
            {"spawn(", "%f[%w_]spawn%s*%(", "spawn() is deprecated - use task.spawn"},
            {"delay(", "%f[%w_]delay%s*%(", "delay() is deprecated - use task.delay"},
            {"loadstring", "loadstring", "loadstring is disabled/unsafe"},
            {":connect(", ":connect%s*%(", ":connect is deprecated - use :Connect"},
            {"Instance.new parent", "Instance%.new%s*%(%s*[%w\\"']+%s*,", "parenting through Instance.new's 2nd argument is slow/deprecated"},
        }
        for _, d in ipairs(root:GetDescendants()) do
            if d:IsA("LuaSourceContainer") then
                scanned = scanned + 1
                local ok, src = pcall(function() return d.Source end)
                src = ok and src or ""
                local found = {}
                for _, s in ipairs(smells) do
                    if string.find(src, s[2]) then table.insert(found, s[3]); issues_total = issues_total + 1 end
                end
                if string.find(src, "while%s+true%s+do") and not string.find(src, "task%.wait") and not string.find(src, "wait%s*%(") and not string.find(src, "%.Event:Wait") and not string.find(src, ":Wait%(") then
                    table.insert(found, "while true do with no yield"); issues_total = issues_total + 1
                end
                if (not A.only_with_issues or #found > 0) and #rows < A.limit then
                    local row = {path = d:GetFullName(), class = d.ClassName, lines = select(2, string.gsub(src, "\\n", "\\n")) + 1, issues = found}
                    if d:IsA("Script") then row.run_context = tostring(d.RunContext); row.enabled = d.Enabled end
                    table.insert(rows, row)
                end
            end
        end
        R.scanned = scanned; R.issues = issues_total; R.scripts = rows
    ''', "script inventory")


@tool(RB, "ms_roblox_replace_in_scripts",
      "Project-wide plain-text find/replace across script sources. apply=false (default) only reports matches per script; apply=true writes them as one undo step.",
      {"find": {"type": "string"}, "replace_with": {"type": "string"}, "root": PATH, "apply": {"type": "boolean"}}, ["find", "replace_with"], writes=True)
def replace_in_scripts(args, ctx):
    return _exec(ctx, dict(args, root=args.get("root") or "game", apply=boolean(args.get("apply"), False)), '''
        local root = A.root == "game" and game or resolve(A.root)
        local rows, total = {}, 0
        for _, d in ipairs(root:GetDescendants()) do
            if d:IsA("LuaSourceContainer") then
                local ok, src = pcall(function() return d.Source end)
                if ok and string.find(src, A.find, 1, true) then
                    local out, i, count = {}, 1, 0
                    while true do
                        local a, b = string.find(src, A.find, i, true)
                        if not a then break end
                        table.insert(out, string.sub(src, i, a - 1)); table.insert(out, A.replace_with); i = b + 1; count = count + 1
                    end
                    table.insert(out, string.sub(src, i))
                    if A.apply then d.Source = table.concat(out) end
                    total = total + count
                    table.insert(rows, {path = d:GetFullName(), matches = count})
                end
            end
        end
        if A.apply then waypoint("replace in scripts") end
        R.applied = A.apply and true or false; R.total_matches = total; R.scripts = rows
    ''', "replace in scripts")


@tool(RB, "ms_roblox_selection",
      "Studio selection: action=get|set|add|clear. Lets the AI act on what the user currently has selected, or show them what it changed.",
      {"action": {"type": "string", "enum": ["get", "set", "add", "clear"]}, "paths": PATHS}, ["action"], writes=True)
def selection(args, ctx):
    return _exec(ctx, dict(args, action=str(args.get("action") or "get").lower(), paths=_paths(args, "paths")), '''
        local S = game:GetService("Selection")
        local list = {}
        for _, p in ipairs(A.paths or {}) do table.insert(list, resolve(p)) end
        if A.action == "set" then S:Set(list)
        elseif A.action == "add" then local cur = S:Get(); for _, i in ipairs(list) do table.insert(cur, i) end; S:Set(cur)
        elseif A.action == "clear" then S:Set({}) end
        R.selection = {}
        for _, i in ipairs(S:Get()) do table.insert(R.selection, brief(i)) end
    ''', "selection")


@tool(RB, "ms_roblox_world_stats",
      "Place health snapshot: instance totals, parts (anchored/unanchored/MeshParts), scripts by class, GUI, lights, sounds, models, top-level breakdown, streaming and lighting tech. Read-only.",
      {})
def world_stats(args, ctx):
    return _exec(ctx, dict(args), '''
        local c = {parts = 0, unanchored = 0, meshparts = 0, unions = 0, models = 0, scripts = 0, localscripts = 0, modules = 0, guis = 0, lights = 0, sounds = 0, particles = 0, remotes = 0, total = 0}
        local function count(root)
            for _, d in ipairs(root:GetDescendants()) do
                c.total = c.total + 1
                if d:IsA("BasePart") then
                    c.parts = c.parts + 1
                    if not d.Anchored then c.unanchored = c.unanchored + 1 end
                    if d:IsA("MeshPart") then c.meshparts = c.meshparts + 1 elseif d:IsA("UnionOperation") then c.unions = c.unions + 1 end
                elseif d:IsA("Model") then c.models = c.models + 1
                elseif d:IsA("Script") then c.scripts = c.scripts + 1
                elseif d:IsA("LocalScript") then c.localscripts = c.localscripts + 1
                elseif d:IsA("ModuleScript") then c.modules = c.modules + 1
                elseif d:IsA("GuiObject") then c.guis = c.guis + 1
                elseif d:IsA("Light") then c.lights = c.lights + 1
                elseif d:IsA("Sound") then c.sounds = c.sounds + 1
                elseif d:IsA("ParticleEmitter") then c.particles = c.particles + 1
                elseif d:IsA("RemoteEvent") or d:IsA("RemoteFunction") then c.remotes = c.remotes + 1 end
            end
        end
        count(game)
        R.counts = c
        R.services = {}
        for _, n in ipairs({"Workspace", "ReplicatedStorage", "ServerScriptService", "ServerStorage", "StarterGui", "StarterPlayer", "Lighting", "SoundService"}) do
            local ok, s = pcall(function() return game:GetService(n) end)
            if ok and s then R.services[n] = #s:GetDescendants() end
        end
        R.streaming = workspace.StreamingEnabled
        -- Optional lighting properties may be restricted in Studio's MCP thread.
        -- Retain the observed world instead of losing the whole report.
        local lighting = game:GetService("Lighting")
        local lightingok, lightingstyle = pcall(function() return lighting.LightingStyle end)
        if lightingok then R.lighting_style = tostring(lightingstyle) end
        local technologyok, technology = pcall(function() return lighting.Technology end)
        if technologyok then R.lighting_technology = tostring(technology)
        else R.lighting_technology_unavailable = "Restricted in this execution context; other world observations remain valid." end
        R.place = {id = game.PlaceId, name = game.Name}
        local warn = {}
        if c.parts > 0 and c.unanchored / c.parts > 0.25 then table.insert(warn, "over 25% of parts are unanchored (physics cost)") end
        if c.total > 150000 then table.insert(warn, "very large instance count; consider StreamingEnabled") end
        R.warnings = warn
    ''', "world stats")


@tool(RB, "ms_roblox_collision_groups",
      "PhysicsService collision groups: action=list|create|set_collidable|assign. assign puts `paths` (and their descendant parts) into `name`.",
      {"action": {"type": "string", "enum": ["list", "create", "set_collidable", "assign"]}, "name": {"type": "string"}, "other": {"type": "string"},
       "collidable": {"type": "boolean"}, "paths": PATHS}, ["action"], writes=True)
def collision_groups(args, ctx):
    return _exec(ctx, dict(args, action=str(args.get("action") or "list").lower(), paths=_paths(args, "paths")), '''
        local PS = game:GetService("PhysicsService")
        local act = A.action
        if act == "create" then if not PS:IsCollisionGroupRegistered(A.name) then PS:RegisterCollisionGroup(A.name) end
        elseif act == "set_collidable" then PS:CollisionGroupSetCollidable(A.name, A.other or A.name, A.collidable ~= false)
        elseif act == "assign" then
            local n = 0
            for _, p in ipairs(A.paths) do
                local inst = resolve(p)
                if inst:IsA("BasePart") then inst.CollisionGroup = A.name; n = n + 1 end
                for _, d in ipairs(inst:GetDescendants()) do if d:IsA("BasePart") then d.CollisionGroup = A.name; n = n + 1 end end
            end
            R.parts_assigned = n
        end
        R.groups = {}
        for _, g in ipairs(PS:GetRegisteredCollisionGroups()) do table.insert(R.groups, g.name) end
        if act ~= "list" then waypoint("collision groups") end
    ''', "collision groups")


@tool(RB, "ms_roblox_measure",
      "Bounding box (centre + size) of instances, and the distance between the first two. Read-only.",
      {"paths": PATHS}, ["paths"])
def measure(args, ctx):
    return _exec(ctx, dict(args, paths=_paths(args, "paths")), '''
        local out, centers = {}, {}
        for _, p in ipairs(A.paths) do
            local inst = resolve(p)
            local cf, size
            if inst:IsA("Model") then cf, size = inst:GetBoundingBox() elseif inst:IsA("BasePart") then cf, size = inst.CFrame, inst.Size else error(inst.ClassName .. " has no bounds: " .. p) end
            table.insert(out, {path = inst:GetFullName(), center = ser(cf.Position), size = ser(size)})
            table.insert(centers, cf.Position)
        end
        R.items = out
        if #centers >= 2 then R.distance = (centers[1] - centers[2]).Magnitude end
    ''', "measure")


@tool(RB, "ms_roblox_camera",
      "Studio camera: action=get|set. set takes `position` and optionally `look_at` [x,y,z] or `focus_path`.",
      {"action": {"type": "string", "enum": ["get", "set"]}, "position": VEC, "look_at": VEC, "focus_path": PATH, "field_of_view": {"type": "number"}}, ["action"], writes=True)
def camera(args, ctx):
    return _exec(ctx, dict(args, action=str(args.get("action") or "get").lower()), '''
        local cam = workspace.CurrentCamera
        if A.action == "set" then
            local pos = A.position and vec3(A.position) or cam.CFrame.Position
            local target = A.look_at and vec3(A.look_at) or (A.focus_path and resolve(A.focus_path):GetPivot().Position) or nil
            cam.CFrame = target and CFrame.new(pos, target) or CFrame.new(pos) * (cam.CFrame - cam.CFrame.Position)
            if A.field_of_view then cam.FieldOfView = A.field_of_view end
        end
        R.camera = {cframe = ser(cam.CFrame), fov = cam.FieldOfView}
    ''', "camera")


@tool(RB, "ms_roblox_history",
      "Studio undo history: action=undo|redo|waypoint. Every write tool already creates an undo waypoint.",
      {"action": {"type": "string", "enum": ["undo", "redo", "waypoint"]}, "name": {"type": "string"}}, ["action"], writes=True)
def history(args, ctx):
    return _exec(ctx, dict(args, action=str(args.get("action") or "waypoint").lower()), '''
        if A.action == "undo" then CHS:Undo() elseif A.action == "redo" then CHS:Redo() else CHS:SetWaypoint(A.name or "MS checkpoint") end
        R.action = A.action
    ''', "history")


@tool(RB, "ms_roblox_changes",
      "See what changed under a root since a checkpoint - including edits the USER made by hand. action=checkpoint snapshots every part/instance "
      "(position, size, colour, anchored); action=diff reports added/removed/changed. Capped at 6000 instances.",
      {"action": {"type": "string", "enum": ["checkpoint", "diff"]}, "root": PATH, "label": {"type": "string"}}, ["action"])
def changes(args, ctx):
    label = str(args.get("label") or "default")
    res = _exec(ctx, dict(args, root=args.get("root") or "Workspace"), '''
        local root = resolve(A.root)
        local snap, n = {}, 0
        for _, d in ipairs(root:GetDescendants()) do
            n = n + 1
            if n > 6000 then R.truncated = true; break end
            local row = {class = d.ClassName}
            if d:IsA("BasePart") then
                row.pos = string.format("%.2f,%.2f,%.2f", d.Position.X, d.Position.Y, d.Position.Z)
                row.size = string.format("%.2f,%.2f,%.2f", d.Size.X, d.Size.Y, d.Size.Z)
                row.color = d.Color:ToHex(); row.anchored = d.Anchored
            end
            local key = d:GetFullName()
            if snap[key] then key = key .. "#" .. n end
            snap[key] = row
        end
        R.snapshot = snap
    ''', "snapshot")
    if not res.get("ok", True) or res.get("dryRun"):
        return res
    snap = res.pop("snapshot", {}) or {}
    act = str(args.get("action") or "diff").lower()
    key = args.get("root") or "Workspace"
    if act == "checkpoint":
        snapshot_store(RB, f"{key}:{label}", snap)
        return {"ok": True, "label": label, "instances": len(snap), "truncated": res.get("truncated", False)}
    prev = snapshot_get(RB, f"{key}:{label}")
    if not prev:
        raise ToolkitError(f"no checkpoint '{label}' for {key}", "Call with action=checkpoint first.")
    out = diff_maps(prev["data"], snap)
    for k in ("added", "removed"):
        out[k] = out[k][:200]
    out.update({"ok": True, "label": label, "since_seconds": int(time.time() - prev["at"])})
    return out


@tool(RB, "ms_roblox_run_luau",
      "Run Luau in Studio with the code given as `lines` (array of source lines - no JSON newline escaping) or `code`. studio_id and datamodel are handled for you. "
      "Prefer the typed ms_roblox_* tools; use this for anything they do not cover. Return a string/table with `return` to get data back.",
      {"lines": {"type": "array", "items": {"type": "string"}, "description": "Source lines of the Luau chunk."}, "code": {"type": "string", "description": "Whole chunk as one string (alternative to lines)."}, "timeout_seconds": {"type": "integer", "minimum": 5, "maximum": 600, "description": "Max seconds to wait for Studio (default 120)."}}, [], writes=True)
def run_luau(args, ctx):
    src = "\n".join(str(x) for x in as_list(args.get("lines"))) if args.get("lines") else str(args.get("code") or "")
    try:
        from schema_repair import repair_code_text
        src, _fixes = repair_code_text(src)
    except Exception:
        src = re.sub(r"^```(?:lua|luau)?\s*\n|\n```\s*$", "", src.strip())
    if not src.strip():
        raise ToolkitError("give `lines` or `code`")
    tool_name = _need(ctx, RB, "execute_luau")
    stud, why = ctx.studio_id(args)
    if why == "ambiguous":
        raise ToolkitError("more than one Roblox Studio is connected", "Pass studio_id (see list_roblox_studios).")
    call = {"code": src, "datamodel_type": str(args.get("mode") or "Edit")}
    if stud:
        call["studio_id"] = stud
    if args.get("dry_run"):
        return {"dryRun": True, "nativeCall": {"tool": tool_name}, "code": src}
    raw = ctx.call(RB, tool_name, call, int(num(args.get("timeout_seconds"), 120, 5, 600)))
    text = str((raw or {}).get("text") or "")
    return {"ok": not re.search(r"^\s*(?:error|failed|attempt to|.{0,80}:\d+:\s)|\b(attempt to |syntax error|unexpected symbol|failed to parse)", text[:600], re.I | re.M), "nativeCall": tool_name, "output": text[:8000]}


@tool(RB, "ms_roblox_playtest",
      "Play-test loop on the native tools: starts play mode, waits `seconds`, collects console output (errors/warnings first), and stops again. "
      "Returns an explicit verdict so you never claim a game works without evidence.",
      {"seconds": {"type": "integer", "minimum": 1, "maximum": 120}, "stop_after": {"type": "boolean"}}, [], writes=True)
def playtest(args, ctx):
    start = _need(ctx, RB, "start_stop_play")
    cons = _need(ctx, RB, "get_console_output")
    stud, why = ctx.studio_id(args)
    if why == "ambiguous":
        raise ToolkitError("more than one Roblox Studio is connected", "Pass studio_id.")
    base = {"studio_id": stud} if stud else {}
    secs = int(num(args.get("seconds"), 8, 1, 120))
    steps = [{"tool": start, "arguments": dict(base, is_start=True)}]
    if args.get("dry_run"):
        return {"dryRun": True, "plan": steps + [{"wait_seconds": secs}, {"tool": cons, "arguments": base}] + ([{"tool": start, "arguments": dict(base, is_start=False)}] if boolean(args.get("stop_after"), True) else [])}
    ctx.call(RB, start, dict(base, is_start=True), 60)
    time.sleep(secs)
    out = ctx.call(RB, cons, dict(base), 60)
    text = str((out or {}).get("text") or "")
    stopped = False
    if boolean(args.get("stop_after"), True):
        try:
            ctx.call(RB, start, dict(base, is_start=False), 60)
            stopped = True
        except Exception as exc:  # report, don't hide
            text += f"\n[could not stop play mode: {exc}]"
    lines = text.splitlines()
    errs = [l for l in lines if re.search(r"error|exception|attempt to|stack begin", l, re.I)]
    warns = [l for l in lines if re.search(r"warn", l, re.I) and l not in errs]
    verdict = "FAIL" if errs else ("WARN" if warns else "PASS")
    return {"ok": True, "verdict": verdict, "ran_seconds": secs, "stopped": stopped, "errors": errs[:30], "warnings": warns[:20],
            "console_tail": lines[-60:], "next": "Fix every error above, then run ms_roblox_playtest again until the verdict is PASS."}
