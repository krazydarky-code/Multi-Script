-- Roblox API mock for running engine_toolkit's generated Luau (tests only). Not a full engine: just enough
-- vector/CFrame math, instance tree, raycast ground plane and terrain/FillBlock counters to run the generators.
local unpack = table.unpack or unpack
local function mkvec(x, y, z)
  local v = {X = x, Y = y, Z = z}
  v.Magnitude = math.sqrt(x*x + y*y + z*z)
  return setmetatable(v, {__typeof = "Vector3",
    __add = function(a, b) return mkvec(a.X+b.X, a.Y+b.Y, a.Z+b.Z) end,
    __sub = function(a, b) return mkvec(a.X-b.X, a.Y-b.Y, a.Z-b.Z) end,
    __unm = function(a) return mkvec(-a.X, -a.Y, -a.Z) end,
    __eq = function(a, b) return a.X == b.X and a.Y == b.Y and a.Z == b.Z end,
    __tostring = function(a) return a.X .. ", " .. a.Y .. ", " .. a.Z end,
    __mul = function(a, b) if type(b) == "number" then return mkvec(a.X*b, a.Y*b, a.Z*b) end if type(a) == "number" then return mkvec(b.X*a, b.Y*a, b.Z*a) end return mkvec(a.X*b.X, a.Y*b.Y, a.Z*b.Z) end,
    __div = function(a, b) if type(b) == "number" then return mkvec(a.X/b, a.Y/b, a.Z/b) end return mkvec(a.X/b.X, a.Y/b.Y, a.Z/b.Z) end,
    __index = function(t, k)
      if k == "Unit" then local m = t.Magnitude; if m == 0 then return t end return mkvec(t.X/m, t.Y/m, t.Z/m) end
      if k == "Dot" then return function(a, b) return a.X*b.X + a.Y*b.Y + a.Z*b.Z end end
      if k == "Cross" then return function(a, b) return mkvec(a.Y*b.Z - a.Z*b.Y, a.Z*b.X - a.X*b.Z, a.X*b.Y - a.Y*b.X) end end
      if k == "Lerp" then return function(a, b, f) return mkvec(a.X + (b.X-a.X)*f, a.Y + (b.Y-a.Y)*f, a.Z + (b.Z-a.Z)*f) end end
      if k == "Max" then return function(a, b) return mkvec(math.max(a.X,b.X), math.max(a.Y,b.Y), math.max(a.Z,b.Z)) end end
      if k == "Min" then return function(a, b) return mkvec(math.min(a.X,b.X), math.min(a.Y,b.Y), math.min(a.Z,b.Z)) end end
    end})
end
Vector3 = {new = function(x, y, z) return mkvec(x or 0, y or 0, z or 0) end, zero = mkvec(0,0,0), one = mkvec(1,1,1), xAxis = mkvec(1,0,0), yAxis = mkvec(0,1,0), zAxis = mkvec(0,0,1)}
Vector2 = {new = function(x, y) return setmetatable({X = x or 0, Y = y or 0}, {__typeof = "Vector2"}) end}
local function mkcol(r, g, b) return setmetatable({R = r, G = g, B = b, ToHex = function() return string.format("%02x%02x%02x", math.floor(r*255+0.5), math.floor(g*255+0.5), math.floor(b*255+0.5)) end}, {__typeof = "Color3"}) end
Color3 = {new = function(r, g, b) return mkcol(r or 0, g or 0, b or 0) end, fromRGB = function(r, g, b) return mkcol(r/255, g/255, b/255) end,
  fromHex = function(h) h = h:gsub("#", ""); return mkcol(tonumber(h:sub(1,2),16)/255, tonumber(h:sub(3,4),16)/255, tonumber(h:sub(5,6),16)/255) end,
  fromHSV = function(h, s, v) return mkcol(v, v, v) end}
-- CFrame with a real rotation matrix: m = {r11,r12,r13,r21,r22,r23,r31,r32,r33}
local mkcf
local function matmul(a, b)
  local r = {}
  for i = 0, 2 do for j = 0, 2 do
    r[i*3+j+1] = a[i*3+1]*b[j+1] + a[i*3+2]*b[3+j+1] + a[i*3+3]*b[6+j+1]
  end end
  return r
end
local IDENT = {1,0,0, 0,1,0, 0,0,1}
local function rotv(m, x, y, z) return m[1]*x + m[2]*y + m[3]*z, m[4]*x + m[5]*y + m[6]*z, m[7]*x + m[8]*y + m[9]*z end
mkcf = function(x, y, z, m)
  m = m or IDENT
  local c = {X = x, Y = y, Z = z, Position = mkvec(x, y, z), _m = m}
  local mt = {__typeof = "CFrame"}
  mt.__mul = function(a, b)
    if getmetatable(b) and getmetatable(b).__typeof == "Vector3" then
      local rx, ry, rz = rotv(a._m, b.X, b.Y, b.Z)
      return mkvec(a.X + rx, a.Y + ry, a.Z + rz)
    end
    local rx, ry, rz = rotv(a._m, b.X, b.Y, b.Z)
    return mkcf(a.X + rx, a.Y + ry, a.Z + rz, matmul(a._m, b._m))
  end
  mt.__add = function(a, b) return mkcf(a.X+b.X, a.Y+b.Y, a.Z+b.Z, a._m) end
  mt.__sub = function(a, b) return mkcf(a.X-b.X, a.Y-b.Y, a.Z-b.Z, a._m) end
  mt.__index = function(t, k)
    local m = rawget(t, "_m")
    if k == "LookVector" then return mkvec(-m[3], -m[6], -m[9]) end
    if k == "RightVector" then return mkvec(m[1], m[4], m[7]) end
    if k == "UpVector" then return mkvec(m[2], m[5], m[8]) end
    if k == "Rotation" then return mkcf(0, 0, 0, m) end
    if k == "Inverse" then return function(s)
      local mt2 = {m[1], m[4], m[7], m[2], m[5], m[8], m[3], m[6], m[9]}
      local rx, ry, rz = rotv(mt2, -s.X, -s.Y, -s.Z)
      return mkcf(rx, ry, rz, mt2) end end
    if k == "ToObjectSpace" then return function(s, o) return s:Inverse() * o end end
    if k == "ToWorldSpace" then return function(s, o) return s * o end end
    if k == "PointToObjectSpace" then return function(s, v) return s:Inverse() * v end end
    if k == "PointToWorldSpace" then return function(s, v) return s * v end end
    if k == "VectorToWorldSpace" then return function(s, v) local a, b, c2 = rotv(m, v.X, v.Y, v.Z); return mkvec(a, b, c2) end end
    if k == "ToEulerAnglesXYZ" then return function(s)
      local sy = m[3]
      local ry = math.asin(math.max(-1, math.min(1, sy)))
      local rx, rz
      if math.abs(sy) < 0.99999 then rx = math.atan2(-m[6], m[9]); rz = math.atan2(-m[2], m[1]) else rx = math.atan2(m[8], m[5]); rz = 0 end
      return rx, ry, rz end end
  end
  return setmetatable(c, mt)
end
local function normalize(x, y, z) local l = math.sqrt(x*x + y*y + z*z); if l == 0 then return 0, 0, 0 end return x/l, y/l, z/l end
local function rotFromLook(lx, ly, lz, ux, uy, uz)
  -- look = -Z axis
  local zx, zy, zz = normalize(-lx, -ly, -lz)
  local xx, xy, xz = uy*zz - uz*zy, uz*zx - ux*zz, ux*zy - uy*zx
  if xx*xx + xy*xy + xz*xz < 1e-8 then xx, xy, xz = 1, 0, 0 end
  xx, xy, xz = normalize(xx, xy, xz)
  local yx, yy, yz = zy*xz - zz*xy, zz*xx - zx*xz, zx*xy - zy*xx
  return {xx, yx, zx, xy, yy, zy, xz, yz, zz}
end
local function isvec(v) return type(v) == "table" and getmetatable(v) and getmetatable(v).__typeof == "Vector3" end
CFrame = {
  new = function(a, b, c)
    if a == nil then return mkcf(0, 0, 0) end
    if type(a) == "table" and isvec(a) then
      if b ~= nil and type(b) == "table" then return CFrame.lookAt(a, b) end
      return mkcf(a.X, a.Y, a.Z)
    end
    return mkcf(a or 0, b or 0, c or 0)
  end,
  lookAt = function(at, target, up)
    up = up or mkvec(0, 1, 0)
    return mkcf(at.X, at.Y, at.Z, rotFromLook(target.X - at.X, target.Y - at.Y, target.Z - at.Z, up.X, up.Y, up.Z))
  end,
  Angles = function(rx, ry, rz)
    rx, ry, rz = rx or 0, ry or 0, rz or 0
    local cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    local Rx = {1,0,0, 0,cx,-sx, 0,sx,cx}
    local Ry = {cy,0,sy, 0,1,0, -sy,0,cy}
    local Rz = {cz,-sz,0, sz,cz,0, 0,0,1}
    return mkcf(0, 0, 0, matmul(matmul(Rx, Ry), Rz))
  end,
  fromAxisAngle = function(axis, ang)
    local x, y, z = normalize(axis.X, axis.Y, axis.Z)
    local c, s = math.cos(ang), math.sin(ang)
    local t = 1 - c
    return mkcf(0, 0, 0, {t*x*x + c, t*x*y - s*z, t*x*z + s*y, t*x*y + s*z, t*y*y + c, t*y*z - s*x, t*x*z - s*y, t*y*z + s*x, t*z*z + c})
  end,
  fromMatrix = function(pos, vx, vy, vz)
    vz = vz or vx:Cross(vy)
    return mkcf(pos.X, pos.Y, pos.Z, {vx.X, vy.X, vz.X, vx.Y, vy.Y, vz.Y, vx.Z, vy.Z, vz.Z})
  end,
}
CFrame.fromEulerAnglesXYZ = CFrame.Angles
UDim2 = {new = function(a, b, c, d) return setmetatable({X = {Scale = a, Offset = b}, Y = {Scale = c, Offset = d}}, {__typeof = "UDim2"}) end,
  fromScale = function(a, b) return UDim2.new(a, 0, b, 0) end, fromOffset = function(a, b) return UDim2.new(0, a, 0, b) end}
UDim = {new = function(a, b) return setmetatable({Scale = a, Offset = b}, {__typeof = "UDim"}) end}
BrickColor = {new = function(n) return setmetatable({Name = n}, {__typeof = "BrickColor"}) end}
NumberRange = {new = function(a, b) return setmetatable({Min = a, Max = b or a}, {__typeof = "NumberRange"}) end}
NumberSequenceKeypoint = {new = function(t, v, e) return setmetatable({Time = t, Value = v, Envelope = e or 0}, {__typeof = "NumberSequenceKeypoint"}) end}
ColorSequenceKeypoint = {new = function(t, c) return setmetatable({Time = t, Value = c}, {__typeof = "ColorSequenceKeypoint"}) end}
NumberSequence = {new = function(a, b) if type(a) == "table" and not b then return setmetatable({Keypoints = a}, {__typeof = "NumberSequence"}) end return setmetatable({Keypoints = {NumberSequenceKeypoint.new(0, a), NumberSequenceKeypoint.new(1, b or a)}}, {__typeof = "NumberSequence"}) end}
ColorSequence = {new = function(a, b) if type(a) == "table" and getmetatable(a) == nil then return setmetatable({Keypoints = a}, {__typeof = "ColorSequence"}) end return setmetatable({Keypoints = {ColorSequenceKeypoint.new(0, a), ColorSequenceKeypoint.new(1, b or a)}}, {__typeof = "ColorSequence"}) end}
TweenInfo = {new = function(...) return setmetatable({args = {...}}, {__typeof = "TweenInfo"}) end}
PhysicalProperties = {new = function(...) return setmetatable({args = {...}}, {__typeof = "PhysicalProperties"}) end}
Rect = {new = function(a, b, c, d) return setmetatable({Min = {X = a, Y = b}, Max = {X = c, Y = d}}, {__typeof = "Rect"}) end}
Font = {new = function() return setmetatable({}, {__typeof = "Font"}) end, fromEnum = function() return setmetatable({}, {__typeof = "Font"}) end, fromName = function() return setmetatable({}, {__typeof = "Font"}) end}
Random = {new = function(seed)
  local s = (seed or 1) * 2654435761 % 4294967296
  local function nxt() s = (s * 1103515245 + 12345) % 2147483648; return s / 2147483648 end
  return {NextNumber = function(_, a, b) local r = nxt(); if a then return a + r * (b - a) end return r end,
          NextInteger = function(_, a, b) return a + math.floor(nxt() * (b - a + 1)) end}
end}
RaycastParams = {new = function() return {FilterDescendantsInstances = {}, FilterType = nil} end}
local enumcache = {}
local function mkenum(etype, name) return setmetatable({Name = name, EnumType = etype}, {__typeof = "EnumItem", __tostring = function() return "Enum." .. etype .. "." .. name end}) end
Enum = setmetatable({}, {__index = function(t, etype)
  local e = setmetatable({}, {__index = function(_, name) enumcache[etype .. name] = enumcache[etype .. name] or mkenum(etype, name); return enumcache[etype .. name] end})
  rawset(t, etype, e); return e end})
function typeof(v)
  local mt = type(v) == "table" and getmetatable(v)
  if mt and mt.__typeof then return mt.__typeof end
  if type(v) == "table" and v.__isinstance then return "Instance" end
  return type(v)
end
math.clamp = math.clamp or function(x, a, b) return math.max(a, math.min(b, x)) end
math.deg = math.deg or function(x) return x * 180 / math.pi end
math.rad = math.rad or function(x) return x * math.pi / 180 end
math.atan2 = math.atan2 or function(y, x) return math.atan(y, x) end
math.noise = function(x, y, z) return math.sin((x or 0) * 1.7 + (y or 0) * 0.3) * math.cos((z or 0) * 2.3 + (x or 0) * 0.9) * 0.6 end
table.unpack = table.unpack or unpack
table.find = table.find or function(t, v) for i, x in ipairs(t) do if x == v then return i end end end
task = task or {wait = function() return 0 end, spawn = function(f, ...) return f(...) end, delay = function() end, defer = function(f, ...) return f(...) end}
os.clock = os.clock or function() return 0 end
local classes = {Part = {"BasePart", "PVInstance"}, WedgePart = {"BasePart", "PVInstance"}, SpawnLocation = {"BasePart", "PVInstance"}, Seat = {"BasePart", "PVInstance"}, VehicleSeat = {"BasePart", "PVInstance"},
  MeshPart = {"BasePart", "PVInstance"}, UnionOperation = {"BasePart", "PVInstance"}, Terrain = {"BasePart"}, Model = {"PVInstance"}, Frame = {"GuiObject"}, TextLabel = {"GuiObject"}, TextButton = {"GuiObject"},
  ImageLabel = {"GuiObject"}, ImageButton = {"GuiObject"}, ScrollingFrame = {"GuiObject"}, TextBox = {"GuiObject"}, ScreenGui = {"LayerCollector"}, Script = {"LuaSourceContainer"}, LocalScript = {"LuaSourceContainer"},
  ModuleScript = {"LuaSourceContainer"}, PointLight = {"Light"}, SpotLight = {"Light"}, SurfaceLight = {"Light"}, HingeConstraint = {"Constraint"}, PrismaticConstraint = {"Constraint"},
  SpringConstraint = {"Constraint"}, RopeConstraint = {"Constraint"}, BloomEffect = {"PostEffect"}, BlurEffect = {"PostEffect"}, ColorCorrectionEffect = {"PostEffect"}, SunRaysEffect = {"PostEffect"},
  DepthOfFieldEffect = {"PostEffect"}, ReverbSoundEffect = {"SoundEffect"}, EchoSoundEffect = {"SoundEffect"}, EqualizerSoundEffect = {"SoundEffect"}, CompressorSoundEffect = {"SoundEffect"},
  DistortionSoundEffect = {"SoundEffect"}, ChorusSoundEffect = {"SoundEffect"}, FlangeSoundEffect = {"SoundEffect"}, PitchShiftSoundEffect = {"SoundEffect"}, TremoloSoundEffect = {"SoundEffect"}, Decal = {"FaceInstance"}, Texture = {"FaceInstance"}}
local defaults = {
  BasePart = {Position = mkvec(0,0,0), Size = mkvec(4,1,2), Anchored = false, Color = mkcol(0.6,0.6,0.6), Material = Enum.Material.Plastic, Transparency = 0, CanCollide = true, CFrame = mkcf(0,0,0),
    Shape = Enum.PartType.Block, CanTouch = true, CanQuery = true, CastShadow = true, AssemblyLinearVelocity = mkvec(0,0,0), CollisionFidelity = Enum.CollisionFidelity.Default, Orientation = mkvec(0,0,0)},
  GuiObject = {Position = UDim2.new(0,0,0,0), Size = UDim2.new(0,100,0,100), Visible = true, Text = "", BackgroundTransparency = 0, BackgroundColor3 = mkcol(1,1,1), TextColor3 = mkcol(0,0,0),
    AbsolutePosition = Vector2.new(0, 0), AbsoluteSize = Vector2.new(100, 100), ZIndex = 1, TextSize = 14, Image = ""},
  LayerCollector = {ZIndexBehavior = Enum.ZIndexBehavior.Global},
  LuaSourceContainer = {Source = ""}, Script = {Enabled = true, RunContext = Enum.RunContext.Legacy}, Light = {Brightness = 1, Shadows = false, Range = 8},
  Model = {WorldPivot = mkcf(0,0,0)}, Constraint = {},
  Sound = {Volume = 0.5, PlaybackSpeed = 1, Looped = false, Playing = false, PlayOnRemove = false, SoundId = "", RollOffMinDistance = 10, RollOffMaxDistance = 10000, RollOffMode = Enum.RollOffMode.Inverse},
  SoundGroup = {Volume = 1}, SoundEffect = {Enabled = true}}
local function cloneVal(v) return v end
local newInstance
newInstance = function(class)
  local o = {ClassName = class, __isinstance = true, _kids = {}, _attrs = {}, _tags = {}, _p = {Name = class}}
  local isa = {[class] = true, Instance = true}
  for _, c in ipairs(classes[class] or {}) do isa[c] = true end
  for c in pairs(isa) do for k, v in pairs(defaults[c] or {}) do o._p[k] = v end end
  o.IsA = function(self, c) return isa[c] == true end
  o.GetChildren = function(self) local r = {}; for _, k in ipairs(self._kids) do r[#r+1] = k end; return r end
  o.FindFirstChild = function(self, n) for _, k in ipairs(self._kids) do if k.Name == n then return k end end end
  o.FindFirstChildOfClass = function(self, c) for _, k in ipairs(self._kids) do if k.ClassName == c then return k end end end
  o.FindFirstChildWhichIsA = function(self, c) for _, k in ipairs(self._kids) do if k:IsA(c) then return k end end end
  o.GetDescendants = function(self) local r = {}; local function w(i) for _, k in ipairs(i._kids) do r[#r+1] = k; w(k) end end; w(self); return r end
  o.GetFullName = function(self) if self.Parent == nil or self.Parent == game then return self.Name end return self.Parent:GetFullName() .. "." .. self.Name end
  o.Destroy = function(self) self.Parent = nil; self._destroyed = true end
  o.ClearAllChildren = function(self) for _, k in ipairs(self:GetChildren()) do k:Destroy() end end
  o.GetAttribute = function(self, k) return self._attrs[k] end
  o.SetAttribute = function(self, k, v) self._attrs[k] = v end
  o.GetAttributes = function(self) return self._attrs end
  o.GetPivot = function(self) if self.ClassName == "Model" then
      if self.PrimaryPart then return self.PrimaryPart.CFrame end
      if self._pivotSet then return self._p.WorldPivot end
      local cf = self:GetBoundingBox(); return cf end
    return self.CFrame or mkcf(0,0,0) end
  o.PivotTo = function(self, cf)
    if self.ClassName == "Model" then
      local cur = self:GetPivot()
      local delta = cf * cur:Inverse()
      for _, d in ipairs(self:GetDescendants()) do if d:IsA("BasePart") then d.CFrame = delta * d.CFrame end end
      self._p.WorldPivot = cf; self._pivotSet = true
    else self.CFrame = cf end
  end
  o.ScaleTo = function(self, k)
    local cur = self._scale or 1
    local f = k / cur
    local c0 = self:GetPivot()
    for _, d in ipairs(self:GetDescendants()) do
      if d:IsA("BasePart") then
        local rel = c0:Inverse() * d.CFrame
        d.Size = d.Size * f
        d.CFrame = c0 * mkcf(rel.X * f, rel.Y * f, rel.Z * f, rel._m)
      end
    end
    self._scale = k
  end
  o.Clone = function(self)
    local c = newInstance(self.ClassName)
    for k, v in pairs(self._p) do if k ~= "Parent" then c._p[k] = v end end
    for k, v in pairs(self._attrs) do c._attrs[k] = v end
    for _, t in ipairs(self._tags) do c._tags[#c._tags+1] = t end
    local pp = self.PrimaryPart
    for _, k in ipairs(self._kids) do local kc = k:Clone(); kc.Parent = c; if pp == k then c._p.PrimaryPart = kc end end
    return c
  end
  o.GetBoundingBox = function(self)
    local lo, hi
    for _, d in ipairs(self:GetDescendants()) do
      if d:IsA("BasePart") then
        local p, s = d.Position, d.Size
        local h = mkvec(s.X/2, s.Y/2, s.Z/2)
        local a, b = p - h, p + h
        lo = lo and lo:Min(a) or a; hi = hi and hi:Max(b) or b
      end
    end
    if not lo then return mkcf(0,0,0), mkvec(0,0,0) end
    local c = (lo + hi) / 2
    return mkcf(c.X, c.Y, c.Z), hi - lo
  end
  o.GetMass = function(self) local s = self.Size; return s.X * s.Y * s.Z * 0.7 end
  o.GetPropertyChangedSignal = function() return {Connect = function() return {Disconnect = function() end} end} end
  local noop = {Connect = function() return {Disconnect = function() end} end, Wait = function() end}
  return setmetatable(o, {
    __newindex = function(t, k, v)
      local p = rawget(t, "_p")
      if k == "Parent" then
        local old = p.Parent
        if old then for i, kid in ipairs(old._kids) do if kid == t then table.remove(old._kids, i) break end end end
        p.Parent = v
        if v then v._kids[#v._kids+1] = t end
      elseif k == "WorldPivot" then p.WorldPivot = v; rawset(t, "_pivotSet", true)
      elseif k == "CFrame" then p.CFrame = v; p.Position = v.Position
      elseif k == "Position" and getmetatable(v) and getmetatable(v).__typeof == "Vector3" then
        p.Position = v
        local m = p.CFrame and p.CFrame._m or IDENT
        p.CFrame = mkcf(v.X, v.Y, v.Z, m)
      else p[k] = v end
    end,
    __index = function(t, k)
      local p = rawget(t, "_p")
      local v = p[k]
      if v ~= nil then return v end
      if k == "NotAProp" then error(k .. " is not a valid member of " .. tostring(rawget(t, "ClassName"))) end
      if k == "Touched" or k == "Changed" or k == "Destroying" or k == "Triggered" or k == "ChildAdded" then return noop end
      if type(k) == "string" then for _, kid in ipairs(rawget(t, "_kids")) do if kid._p.Name == k then return kid end end end
      return nil
    end})
end
Instance = {new = function(class, parent) local o = newInstance(class); if parent then o.Parent = parent end; return o end}
game = newInstance("DataModel"); game._p.Name = "game"
local services = {}
function game:GetService(n)
  if n == "HttpService" then return {JSONDecode = function(_, s) return JSON_DECODE(s) end, JSONEncode = function(_, t) return JSON_ENCODE(t) end} end
  if n == "CollectionService" then return {AddTag = function(_, i, t) i._tags[#i._tags+1] = t end, RemoveTag = function() end, HasTag = function(_, i, t) for _, x in ipairs(i._tags) do if x == t then return true end end return false end,
    GetTags = function(_, i) return i._tags end, GetTagged = function() return {} end} end
  if n == "ChangeHistoryService" then return {SetWaypoint = function() end, Undo = function() end, Redo = function() end} end
  if n == "Selection" then return {Get = function() return {} end, Set = function() end} end
  if n == "PhysicsService" then return {RegisterCollisionGroup = function() end} end
  if services[n] then return services[n] end
  local s = newInstance(n); s.Name = n; s.Parent = game; services[n] = s
  if n == "Lighting" then s.ClockTime = 12; s.Brightness = 2 end
  if n == "StarterPlayer" then
    for _, k in ipairs({"StarterPlayerScripts", "StarterCharacterScripts"}) do local c = newInstance(k); c.Name = k; c.Parent = s end
  end
  return s
end
workspace = game:GetService("Workspace")
local terrain = newInstance("Terrain"); terrain.Name = "Terrain"
terrain._fills = {}
terrain.FillBlock = function(self, cf, size, mat) self._fills[#self._fills+1] = {cf = cf, size = size, mat = mat} end
terrain.Clear = function(self) self._fills = {} end
workspace.Terrain = terrain
workspace.Raycast = function(self, origin, dir, params)
  -- flat ground at y = GROUND_Y (default 0)
  local gy = GROUND_Y or 0
  if dir.Y >= 0 then return nil end
  local t = (gy - origin.Y) / dir.Y
  if t < 0 or t > 1 then return nil end
  return {Position = mkvec(origin.X + dir.X * t, gy, origin.Z + dir.Z * t), Normal = mkvec(0, 1, 0), Material = Enum.Material.Grass, Instance = terrain}
end
workspace.GetPartsInPart = function() return {} end
debug = debug or {traceback = function() return "" end}
