-- VFX preset module (18 presets)
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire VFX module (ReplicatedStorage.BrickwireVFX). Usage (Script or LocalScript):
--   local VFX = require(game.ReplicatedStorage:WaitForChild("BrickwireVFX"))
--   VFX.play("explosion", part.CFrame)            -- or a Vector3 / BasePart / Attachment
--   VFX.play("slash", hrp.CFrame, { color = Color3.fromRGB(120, 200, 255), scale = 1.5 })
--   VFX.bolt(fromPos, toPos, { color = … })      VFX.shake(1, 0.4) (client)      VFX.flash(model)
--   VFX.list() → preset names.  Hit/impact effects: call them on the CLIENT (via a RemoteEvent) for zero server cost.
local TweenService = game:GetService("TweenService")
local Debris = game:GetService("Debris")
local RunService = game:GetService("RunService")
local VFX = {}
local TEX = {
	spark = "rbxasset://textures/particles/sparkles_main.dds",
	fire = "rbxasset://textures/particles/fire_main.dds",
	smoke = "rbxasset://textures/particles/smoke_main.dds",
	embers = "rbxasset://textures/particles/fire_sparks_main.dds",
	core = "rbxasset://textures/particles/explosion01_core_main.dds",
	wave = "rbxasset://textures/particles/explosion01_shockwave_main.dds",
	puff = "rbxasset://textures/particles/explosion01_smoke_main.dds",
	implode = "rbxasset://textures/particles/explosion01_implosion_main.dds",
	glow = "rbxasset://textures/particles/forcefield_glow_main.dds",
	vortex = "rbxasset://textures/particles/forcefield_vortex_main.dds",
}
VFX.TEX = TEX
local function C(h) return typeof(h) == "Color3" and h or Color3.fromHex(h) end
local function cseq(c)
	if typeof(c) == "ColorSequence" then return c end
	if type(c) ~= "table" then return ColorSequence.new(C(c)) end
	local k = {}
	for i, v in ipairs(c) do table.insert(k, ColorSequenceKeypoint.new((i - 1) / math.max(1, #c - 1), C(v))) end
	if #k == 1 then table.insert(k, ColorSequenceKeypoint.new(1, k[1].Value)) end
	return ColorSequence.new(k)
end
local function nseq(v, scale)
	scale = scale or 1
	if typeof(v) == "NumberSequence" then return v end
	if type(v) == "number" then return NumberSequence.new(v * scale) end
	local k = {}
	for i, x in ipairs(v) do
		if type(x) == "table" then table.insert(k, NumberSequenceKeypoint.new(x[1], x[2] * scale))
		else table.insert(k, NumberSequenceKeypoint.new((i - 1) / math.max(1, #v - 1), x * scale)) end
	end
	if #k == 1 then table.insert(k, NumberSequenceKeypoint.new(1, k[1].Value)) end
	return NumberSequence.new(k)
end
local function range(v, s)
	s = s or 1
	if type(v) == "number" then return NumberRange.new(v * s) end
	return NumberRange.new(v[1] * s, (v[2] or v[1]) * s)
end
local function tween(o, t, goal, style, dir)
	local tw = TweenService:Create(o, TweenInfo.new(t, style or Enum.EasingStyle.Quad, dir or Enum.EasingDirection.Out), goal)
	tw:Play()
	return tw
end
local function later(t, fn) if t and t > 0 then task.delay(t, fn) else fn() end end
local folder
local function fxFolder()
	if folder and folder.Parent then return folder end
	folder = workspace:FindFirstChild("BrickwireFX")
	if not folder then
		folder = Instance.new("Folder")
		folder.Name = "BrickwireFX"
		folder.Parent = workspace
	end
	return folder
end
local function toCF(where)
	if typeof(where) == "CFrame" then return where end
	if typeof(where) == "Vector3" then return CFrame.new(where) end
	if typeof(where) == "Instance" then
		if where:IsA("Attachment") then return where.WorldCFrame end
		if where:IsA("BasePart") then return where.CFrame end
		if where:IsA("Model") then return where:GetPivot() end
	end
	error("BrickwireVFX: where must be a CFrame, Vector3, BasePart, Model or Attachment", 3)
end
local function anchorPart(cf, life)
	local p = Instance.new("Part")
	p.Name = "FX"
	p.Anchored = true
	p.CanCollide = false
	p.CanQuery = false
	p.CanTouch = false
	p.Transparency = 1
	p.Size = Vector3.new(0.2, 0.2, 0.2)
	p.CFrame = cf
	p.Parent = fxFolder()
	Debris:AddItem(p, life)
	return p
end
local function shellPart(parent, shape, color, material, cf, size, tr)
	local p = Instance.new("Part")
	p.Name = "Shell"
	p.Anchored = true
	p.CanCollide = false
	p.CanQuery = false
	p.CanTouch = false
	p.CastShadow = false
	p.Shape = shape
	p.Material = material
	p.Color = color
	p.Transparency = tr
	p.Size = size
	p.CFrame = cf
	p.Parent = parent
	return p
end

-- layer builders -------------------------------------------------------------------------------------------
local L = {}
-- particle burst: count, tex, color, size, transp, life, speed, spread, accel, drag, rot, rotSpeed, light, zoffset, orient, squash, shape, inward, rate+time (stream)
function L.emit(root, cf, d, o)
	local s = o.scale
	local a = Instance.new("Attachment")
	a.Parent = root
	if d.offset then a.Position = d.offset * s end
	local e = Instance.new("ParticleEmitter")
	e.Enabled = false
	e.Texture = TEX[d.tex or "spark"] or d.tex
	e.Color = cseq(o.color and d.tint ~= false and { o.color, d.color and (type(d.color) == "table" and d.color[#d.color] or d.color) or o.color } or d.color or "#FFFFFF")
	e.Size = nseq(d.size or { 1, 0 }, s)
	e.Transparency = nseq(d.transp or { 0, 1 })
	e.Lifetime = range(d.life or { 0.4, 0.8 })
	e.Speed = range(d.speed or { 5, 10 }, s)
	e.SpreadAngle = Vector2.new(d.spread or 180, d.spread or 180)
	e.Acceleration = d.accel or Vector3.new(0, 0, 0)
	e.Drag = d.drag or 0
	e.Rotation = range(d.rot or { 0, 360 })
	e.RotSpeed = range(d.rotSpeed or { -90, 90 })
	e.LightEmission = d.light or 1
	e.LightInfluence = d.lightInfluence or 0
	e.ZOffset = d.zoffset or 0
	if d.brightness then pcall(function() e.Brightness = d.brightness end) end
	if d.orient then e.Orientation = Enum.ParticleOrientation[d.orient] end
	if d.squash then pcall(function() e.Squash = nseq(d.squash) end) end
	if d.emitDir then e.EmissionDirection = Enum.NormalId[d.emitDir] end
	if d.shape then
		pcall(function()
			e.Shape = Enum.ParticleEmitterShape[d.shape]
			e.ShapeStyle = Enum.ParticleEmitterShapeStyle[d.shapeStyle or "Volume"]
			if d.inward then e.ShapeInOut = Enum.ParticleEmitterShapeInOut.Inward end
		end)
	end
	if d.lockedToPart then e.LockedToPart = true end
	e.Parent = a
	later(d.delay, function()
		if d.rate then
			e.Rate = d.rate
			e.Enabled = true
			task.delay(d.time or 0.5, function() e.Enabled = false end)
		else
			e:Emit(math.max(1, math.floor((d.count or 10) * (o.density or 1) + 0.5)))
		end
	end)
end
-- expanding shell: shape Ball|Cylinder (ring/disc, flat), material ForceField (bright edges) or Neon
function L.shell(root, cf, d, o)
	local s = o.scale
	local shape = d.ring and Enum.PartType.Cylinder or Enum.PartType.Ball
	local from, to = (d.from or 1) * s, (d.to or 10) * s
	local thick = (d.thick or 0.4) * s
	local pcf = d.ring and (cf * CFrame.Angles(0, 0, math.rad(90))) or cf
	if d.offset then pcf = pcf + d.offset * s end
	local function sz(r) return d.ring and Vector3.new(thick, r, r) or Vector3.new(r, r, r) end
	local p = shellPart(root.Parent, shape, C(o.color or d.color or "#FFFFFF"), Enum.Material[d.material or "ForceField"], pcf, sz(from), d.startT or 0)
	Debris:AddItem(p, (d.delay or 0) + (d.time or 0.4) + 0.2)
	if d.delay then p.Transparency = 1 end
	later(d.delay, function()
		p.Transparency = d.startT or 0
		tween(p, d.time or 0.4, { Size = sz(to), Transparency = 1 }, Enum.EasingStyle[d.ease or "Quart"])
	end)
end
-- point light flash
function L.light(root, cf, d, o)
	local l = Instance.new("PointLight")
	l.Color = C(o.color or d.color or "#FFFFFF")
	l.Range = (d.range or 16) * o.scale
	l.Brightness = 0
	l.Shadows = false
	l.Parent = root
	later(d.delay, function()
		l.Brightness = d.brightness or 4
		tween(l, d.time or 0.35, { Brightness = 0 })
	end)
end
-- lightning bolt made of neon segments (+ branches); from = offset above (studs) or Vector3 start
local function boltSegments(parent, a, b, color, width, segs, jitter, life)
	local pts = { a }
	for i = 1, segs - 1 do
		local t = i / segs
		local p = a:Lerp(b, t)
		local off = Vector3.new((math.random() - 0.5) * 2, (math.random() - 0.5) * 2, (math.random() - 0.5) * 2) * jitter
		table.insert(pts, p + off)
	end
	table.insert(pts, b)
	local parts = {}
	for i = 1, #pts - 1 do
		local p0, p1 = pts[i], pts[i + 1]
		local len = (p1 - p0).Magnitude
		local seg = shellPart(parent, Enum.PartType.Block, color, Enum.Material.Neon, CFrame.lookAt((p0 + p1) / 2, p1), Vector3.new(width, width, len), 0)
		table.insert(parts, seg)
		Debris:AddItem(seg, life + 0.2)
	end
	return parts, pts
end
function L.bolt(root, cf, d, o)
	local s = o.scale
	local b = cf.Position
	local a = d.fromPos or (b + Vector3.new((math.random() - 0.5) * 8, d.height or 40, (math.random() - 0.5) * 8) * s)
	later(d.delay, function()
		local col = C(o.color or d.color or "#BFE6FF")
		local life = d.time or 0.25
		local parts, pts = boltSegments(root.Parent, a, b, col, (d.width or 0.35) * s, d.segments or 9, (d.jitter or 2.2) * s, life)
		for _ = 1, d.branches or 2 do
			local i = math.random(2, math.max(2, #pts - 2))
			local start = pts[i]
			local dir = (pts[i + 1] - start).Unit
			local endp = start + (dir + Vector3.new((math.random() - 0.5) * 2, -0.3, (math.random() - 0.5) * 2)).Unit * (6 * s)
			local bp = boltSegments(root.Parent, start, endp, col, (d.width or 0.35) * 0.6 * s, 4, 1.2 * s, life)
			for _, x in ipairs(bp) do table.insert(parts, x) end
		end
		for _, p in ipairs(parts) do tween(p, life, { Transparency = 1 }, Enum.EasingStyle.Linear) end
	end)
end
-- slash arc: neon crescent segments that sweep in and fade (in the root's XZ plane, facing -Z)
function L.arc(root, cf, d, o)
	local s = o.scale
	local r = (d.radius or 6) * s
	local n = d.segments or 14
	local sweep = math.rad(d.sweep or 150)
	local tilt = CFrame.Angles(0, 0, math.rad(d.tilt or 0))
	local col = C(o.color or d.color or "#E6F7FF")
	for i = 1, n do
		local t = (i - 1) / (n - 1)
		local ang = -sweep / 2 + sweep * t
		local w = math.sin(t * math.pi) * (d.width or 1.2) * s + 0.1
		local pos = (cf * tilt * CFrame.new(math.sin(ang) * r, 0, -math.cos(ang) * r))
		local seg = shellPart(root.Parent, Enum.PartType.Block, col, Enum.Material.Neon, pos * CFrame.Angles(0, -ang, 0), Vector3.new(2 * r * math.sin(sweep / n / 2) * 1.15, 0.12 * s, w), 1)
		Debris:AddItem(seg, (d.delay or 0) + 0.6)
		later((d.delay or 0) + t * (d.time or 0.12), function()
			seg.Transparency = 0.05
			tween(seg, 0.25, { Transparency = 1, Size = seg.Size * Vector3.new(1, 1, 0.3) })
		end)
	end
end
-- physics debris (rocks / shards / confetti)
function L.debris(root, cf, d, o)
	local s = o.scale
	later(d.delay, function()
		for i = 1, d.count or 8 do
			local p = Instance.new("Part")
			p.Name = "Debris"
			p.Size = Vector3.new(math.random(4, 10) / 10, math.random(4, 10) / 10, math.random(4, 10) / 10) * (d.size or 1) * s
			local cols = d.colors or { d.color or "#6B6B6B" }
			p.Color = C(cols[(i - 1) % #cols + 1])
			p.Material = Enum.Material[d.material or "Slate"]
			p.CFrame = cf * CFrame.new(0, 0.5 * s, 0) * CFrame.Angles(math.random() * 6, math.random() * 6, math.random() * 6)
			p.CanCollide = d.collide ~= false
			p.CanQuery = false
			p.CastShadow = false
			p.Anchored = false
			p.Parent = root.Parent
			local dir = Vector3.new(math.random() - 0.5, (d.up or 0.9) + math.random() * 0.5, math.random() - 0.5).Unit
			p.AssemblyLinearVelocity = dir * (d.speed or 40) * (0.6 + math.random() * 0.6) * math.sqrt(s)
			p.AssemblyAngularVelocity = Vector3.new(math.random() - 0.5, math.random() - 0.5, math.random() - 0.5) * 20
			local life = d.time or 2
			task.delay(life * 0.6, function() if p.Parent then tween(p, life * 0.4, { Transparency = 1, Size = p.Size * 0.3 }) end end)
			Debris:AddItem(p, life + 0.1)
		end
	end)
end
-- vertical pillar of light (teleport / level up)
function L.pillar(root, cf, d, o)
	local s = o.scale
	local h = (d.height or 18) * s
	local p = shellPart(root.Parent, Enum.PartType.Cylinder, C(o.color or d.color or "#FFE27A"), Enum.Material[d.material or "Neon"], cf * CFrame.new(0, h / 2, 0) * CFrame.Angles(0, 0, math.rad(90)), Vector3.new(h, (d.width or 3) * s, (d.width or 3) * s), 0.2)
	Debris:AddItem(p, (d.delay or 0) + (d.time or 0.8) + 0.2)
	p.Transparency = 1
	later(d.delay, function()
		p.Transparency = 0.15
		tween(p, d.time or 0.8, { Transparency = 1, Size = Vector3.new(h * 1.1, 0.1, 0.1) }, Enum.EasingStyle.Quint, Enum.EasingDirection.In)
	end)
end
-- camera shake (client only; ignored on the server)
function L.shake(_, _, d, o) if RunService:IsClient() then later(d.delay, function() VFX.shake((d.amp or 0.6) * o.shake, d.time or 0.35) end) end end

-- presets: arrays of layers (timing in seconds; sizes in studs, multiplied by opts.scale) ---------------------------
local P = {}
VFX.PRESETS = P
P.explosion = {
	{ "light", color = "#FFB347", range = 40, brightness = 8, time = 0.6 },
	{ "emit", tex = "core", count = 2, color = { "#FFFFFF", "#FFD27A", "#FF6A00" }, size = { { 0, 2 }, { 0.3, 14 }, { 1, 16 } }, transp = { { 0, 0 }, { 0.6, 0.3 }, { 1, 1 } }, life = { 0.35, 0.45 }, speed = 0, rotSpeed = { -40, 40 } },
	{ "emit", tex = "fire", count = 40, color = { "#FFF2A8", "#FF8A00", "#7A1E00" }, size = { { 0, 3 }, { 1, 0 } }, life = { 0.5, 0.9 }, speed = { 18, 34 }, drag = 6, zoffset = 1 },
	{ "emit", tex = "spark", count = 40, color = { "#FFFFFF", "#FFC14D" }, size = { { 0, 0.6 }, { 1, 0 } }, life = { 0.5, 1.1 }, speed = { 40, 75 }, drag = 3, accel = Vector3.new(0, -40, 0), orient = "VelocityParallel", squash = { { 0, -1.5 }, { 1, -1.5 } } },
	{ "emit", tex = "puff", count = 16, color = { "#6B5B52", "#2B2B2B" }, size = { { 0, 5 }, { 1, 14 } }, transp = { { 0, 0.35 }, { 1, 1 } }, life = { 1.8, 3 }, speed = { 6, 14 }, drag = 2.5, accel = Vector3.new(0, 4, 0), light = 0, lightInfluence = 1, delay = 0.05, tint = false },
	{ "shell", color = "#FFB347", from = 2, to = 28, time = 0.4, material = "ForceField" },
	{ "shell", ring = true, color = "#FFE0A0", from = 2, to = 36, time = 0.55, thick = 0.3, offset = Vector3.new(0, -0.8, 0) },
	{ "debris", count = 8, speed = 45, time = 2.2 },
	{ "shake", amp = 1, time = 0.45 },
}
P.hit_spark = {
	{ "light", color = "#FFFFFF", range = 10, brightness = 4, time = 0.15 },
	{ "emit", tex = "core", count = 1, color = { "#FFFFFF", "#9FD8FF" }, size = { { 0, 1 }, { 0.3, 4 }, { 1, 4.5 } }, life = 0.18, speed = 0 },
	{ "emit", tex = "spark", count = 18, color = { "#FFFFFF", "#7FD3FF" }, size = { { 0, 0.35 }, { 1, 0 } }, life = { 0.18, 0.35 }, speed = { 25, 45 }, drag = 8, orient = "VelocityParallel", squash = { { 0, -2 }, { 1, -2 } } },
	{ "shell", color = "#BFE6FF", from = 0.5, to = 5, time = 0.18 },
	{ "shake", amp = 0.25, time = 0.12 },
}
P.slash = {
	{ "arc", radius = 6, sweep = 160, width = 1.4, time = 0.1, tilt = -20 },
	{ "arc", radius = 5.2, sweep = 140, width = 0.6, time = 0.12, tilt = -20, color = "#FFFFFF", delay = 0.02 },
	{ "emit", tex = "spark", count = 14, color = { "#FFFFFF", "#9FD8FF" }, size = { { 0, 0.4 }, { 1, 0 } }, life = { 0.2, 0.4 }, speed = { 12, 22 }, drag = 6, offset = Vector3.new(0, 0, -5), orient = "VelocityParallel", squash = { { 0, -1 }, { 1, -1 } } },
	{ "shake", amp = 0.2, time = 0.1 },
}
P.shockwave = {
	{ "light", color = "#9FD8FF", range = 30, brightness = 5, time = 0.5 },
	{ "shell", ring = true, color = "#BFE6FF", from = 2, to = 46, time = 0.7, thick = 0.5 },
	{ "shell", ring = true, color = "#FFFFFF", from = 1, to = 30, time = 0.5, thick = 0.25, delay = 0.08 },
	{ "emit", tex = "smoke", count = 30, color = { "#D9D2C5", "#8C857A" }, size = { { 0, 2 }, { 1, 6 } }, transp = { { 0, 0.4 }, { 1, 1 } }, life = { 0.8, 1.4 }, speed = { 30, 45 }, drag = 4, spread = 2, emitDir = "Top", shape = "Disc", light = 0, lightInfluence = 1, tint = false, orient = "FacingCamera" },
	{ "shake", amp = 0.7, time = 0.4 },
}
P.lightning = {
	{ "bolt", height = 45, branches = 3, time = 0.28 },
	{ "bolt", height = 45, branches = 1, time = 0.2, delay = 0.08 },
	{ "light", color = "#CFE9FF", range = 60, brightness = 10, time = 0.4 },
	{ "emit", tex = "spark", count = 30, color = { "#FFFFFF", "#8FD0FF" }, size = { { 0, 0.5 }, { 1, 0 } }, life = { 0.3, 0.7 }, speed = { 20, 40 }, drag = 4, accel = Vector3.new(0, -30, 0), orient = "VelocityParallel", squash = { { 0, -1.5 }, { 1, -1.5 } } },
	{ "shell", ring = true, color = "#BFE6FF", from = 1, to = 14, time = 0.35, thick = 0.3 },
	{ "emit", tex = "smoke", count = 8, color = { "#5A5A6A", "#2A2A33" }, size = { { 0, 2 }, { 1, 6 } }, transp = { { 0, 0.5 }, { 1, 1 } }, life = { 1, 1.8 }, speed = { 2, 5 }, light = 0, lightInfluence = 1, tint = false, delay = 0.1 },
	{ "shake", amp = 0.6, time = 0.3 },
}
P.magic_burst = {
	{ "light", color = "#C77DFF", range = 26, brightness = 6, time = 0.6 },
	{ "shell", color = "#B46CFF", from = 1, to = 12, time = 0.45, material = "Neon", startT = 0.3 },
	{ "shell", color = "#E0B3FF", from = 1, to = 18, time = 0.6 },
	{ "emit", tex = "implode", count = 1, color = { "#FFFFFF", "#B46CFF" }, size = { { 0, 2 }, { 1, 12 } }, life = 0.5, speed = 0 },
	{ "emit", tex = "spark", count = 50, color = { "#FFFFFF", "#FF7AD9", "#7B5CFF" }, size = { { 0, 0.8 }, { 1, 0 } }, life = { 0.6, 1.2 }, speed = { 14, 30 }, drag = 5, rotSpeed = { -200, 200 } },
	{ "emit", tex = "glow", count = 12, color = { "#C77DFF", "#5A2BFF" }, size = { { 0, 1.5 }, { 1, 0 } }, life = { 1, 1.6 }, speed = { 3, 8 }, drag = 2, accel = Vector3.new(0, 5, 0) },
}
P.heal = {
	{ "light", color = "#7CFFB2", range = 16, brightness = 3, time = 1.2 },
	{ "shell", ring = true, color = "#7CFFB2", from = 4, to = 9, time = 0.9, thick = 0.2, offset = Vector3.new(0, -2.8, 0) },
	{ "emit", tex = "spark", count = 36, color = { "#E6FFF0", "#3DFF8F" }, size = { { 0, 0 }, { 0.2, 0.7 }, { 1, 0 } }, life = { 1, 1.6 }, speed = { 1, 3 }, accel = Vector3.new(0, 7, 0), shape = "Cylinder", shapeStyle = "Surface", spread = 10, emitDir = "Top", offset = Vector3.new(0, -2.5, 0) },
	{ "emit", tex = "glow", count = 10, color = { "#B8FFD6", "#2BD67B" }, size = { { 0, 1.2 }, { 1, 0 } }, life = { 1.2, 1.8 }, speed = { 0.5, 1.5 }, accel = Vector3.new(0, 5, 0), delay = 0.1 },
}
P.level_up = {
	{ "light", color = "#FFD86B", range = 30, brightness = 7, time = 1.2 },
	{ "pillar", height = 22, width = 4, time = 0.9 },
	{ "shell", ring = true, color = "#FFE27A", from = 2, to = 22, time = 0.8, thick = 0.3, offset = Vector3.new(0, -2.8, 0) },
	{ "emit", tex = "spark", count = 60, color = { "#FFFFFF", "#FFD24D", "#FF9F1C" }, size = { { 0, 0.9 }, { 1, 0 } }, life = { 0.9, 1.6 }, speed = { 8, 20 }, accel = Vector3.new(0, 12, 0), drag = 2, spread = 40, emitDir = "Top", rotSpeed = { -180, 180 } },
	{ "debris", count = 26, colors = { "#FFD24D", "#FF5D8F", "#4FC3FF", "#7CFF6B", "#C77DFF" }, size = 0.5, material = "SmoothPlastic", speed = 35, up = 2, time = 2.5, collide = false, delay = 0.2 },
}
P.dash = {
	{ "emit", tex = "smoke", count = 10, color = { "#E8E8E8", "#9A9A9A" }, size = { { 0, 1.5 }, { 1, 4 } }, transp = { { 0, 0.4 }, { 1, 1 } }, life = { 0.4, 0.8 }, speed = { 4, 8 }, light = 0, lightInfluence = 1, tint = false, emitDir = "Back", spread = 30 },
	{ "emit", tex = "spark", count = 22, color = { "#FFFFFF", "#BFE6FF" }, size = { { 0, 0.25 }, { 1, 0 } }, life = { 0.15, 0.3 }, speed = { 40, 60 }, emitDir = "Back", spread = 12, orient = "VelocityParallel", squash = { { 0, -3 }, { 1, -3 } } },
	{ "shell", ring = true, color = "#FFFFFF", from = 1, to = 8, time = 0.25, thick = 0.15 },
}
P.ground_slam = {
	{ "light", color = "#FFC890", range = 30, brightness = 4, time = 0.5 },
	{ "shell", ring = true, color = "#FFE6C7", from = 3, to = 40, time = 0.6, thick = 0.6 },
	{ "emit", tex = "puff", count = 34, color = { "#B8A58C", "#6B5B4A" }, size = { { 0, 3 }, { 1, 8 } }, transp = { { 0, 0.3 }, { 1, 1 } }, life = { 0.9, 1.6 }, speed = { 25, 40 }, drag = 4, spread = 3, emitDir = "Top", shape = "Disc", light = 0, lightInfluence = 1, tint = false },
	{ "debris", count = 16, speed = 50, time = 2.4, size = 1.4 },
	{ "shake", amp = 1.2, time = 0.5 },
}
P.smoke_puff = {
	{ "emit", tex = "smoke", count = 18, color = { "#F0F0F0", "#8A8A8A" }, size = { { 0, 2 }, { 1, 6 } }, transp = { { 0, 0.3 }, { 1, 1 } }, life = { 0.8, 1.6 }, speed = { 4, 10 }, drag = 3, light = 0, lightInfluence = 1, tint = false },
}
P.confetti = {
	{ "debris", count = 60, colors = { "#FF5D8F", "#FFD24D", "#4FC3FF", "#7CFF6B", "#C77DFF", "#FF9F1C" }, size = 0.45, material = "SmoothPlastic", speed = 45, up = 2.5, time = 3.5, collide = false },
	{ "emit", tex = "spark", count = 30, color = { "#FFFFFF", "#FFE27A" }, size = { { 0, 0.8 }, { 1, 0 } }, life = { 0.4, 0.9 }, speed = { 15, 30 }, drag = 4 },
}
P.pickup = {
	{ "light", color = "#FFE27A", range = 12, brightness = 3, time = 0.3 },
	{ "shell", color = "#FFF2B3", from = 0.5, to = 6, time = 0.3 },
	{ "emit", tex = "spark", count = 16, color = { "#FFFFFF", "#FFD24D" }, size = { { 0, 0.7 }, { 1, 0 } }, life = { 0.4, 0.8 }, speed = { 6, 14 }, drag = 4, accel = Vector3.new(0, 8, 0) },
}
P.ice_shatter = {
	{ "light", color = "#9FE8FF", range = 20, brightness = 5, time = 0.4 },
	{ "shell", color = "#CFF6FF", from = 1, to = 10, time = 0.35 },
	{ "emit", tex = "spark", count = 30, color = { "#FFFFFF", "#7FDBFF" }, size = { { 0, 0.6 }, { 1, 0 } }, life = { 0.4, 0.9 }, speed = { 15, 30 }, drag = 5 },
	{ "emit", tex = "smoke", count = 10, color = { "#E6FBFF", "#9ADFFF" }, size = { { 0, 2 }, { 1, 5 } }, transp = { { 0, 0.5 }, { 1, 1 } }, life = { 0.8, 1.4 }, speed = { 3, 6 }, light = 0.3, tint = false },
	{ "debris", count = 12, colors = { "#BFF2FF", "#8FDFFF", "#E6FBFF" }, material = "Glass", size = 0.9, speed = 30, time = 2 },
}
P.teleport = {
	{ "light", color = "#6FE7FF", range = 26, brightness = 6, time = 0.8 },
	{ "pillar", color = "#6FE7FF", height = 16, width = 5, time = 0.7 },
	{ "emit", tex = "implode", count = 1, color = { "#FFFFFF", "#6FE7FF" }, size = { { 0, 12 }, { 1, 1 } }, life = 0.45, speed = 0, offset = Vector3.new(0, 2, 0) },
	{ "emit", tex = "spark", count = 40, color = { "#FFFFFF", "#6FE7FF", "#4F6BFF" }, size = { { 0, 0.6 }, { 1, 0 } }, life = { 0.8, 1.3 }, speed = { 2, 5 }, accel = Vector3.new(0, 14, 0), shape = "Cylinder", shapeStyle = "Surface", emitDir = "Top", spread = 5 },
	{ "shell", ring = true, color = "#6FE7FF", from = 8, to = 1, time = 0.5, thick = 0.25, offset = Vector3.new(0, -2.8, 0) },
}
P.fire_burst = {
	{ "light", color = "#FF8A3C", range = 24, brightness = 6, time = 0.6 },
	{ "emit", tex = "fire", count = 45, color = { "#FFF2A8", "#FF6A00", "#5A0F00" }, size = { { 0, 2.5 }, { 1, 0 } }, life = { 0.5, 1 }, speed = { 10, 22 }, drag = 4, accel = Vector3.new(0, 10, 0) },
	{ "emit", tex = "embers", count = 30, color = { "#FFD27A", "#FF4D00" }, size = { { 0, 0.4 }, { 1, 0 } }, life = { 0.8, 1.6 }, speed = { 12, 26 }, drag = 2, accel = Vector3.new(0, 6, 0) },
	{ "shell", color = "#FF9A3C", from = 1, to = 12, time = 0.35 },
}
P.poison = {
	{ "emit", tex = "smoke", rate = 30, time = 1.5, color = { "#B6FF6B", "#3E7F1A" }, size = { { 0, 2 }, { 1, 5 } }, transp = { { 0, 0.5 }, { 1, 1 } }, life = { 1.2, 2 }, speed = { 1, 3 }, accel = Vector3.new(0, 2, 0), light = 0.4, shape = "Sphere", tint = false },
	{ "emit", tex = "glow", rate = 14, time = 1.5, color = { "#E6FF9A", "#5ACF2A" }, size = { { 0, 0.6 }, { 1, 0 } }, life = { 0.8, 1.4 }, speed = { 1, 2 }, accel = Vector3.new(0, 4, 0), shape = "Sphere" },
}
P.vortex = {
	{ "light", color = "#9B5CFF", range = 30, brightness = 5, time = 1.6 },
	{ "emit", tex = "vortex", rate = 6, time = 1.2, color = { "#1A0033", "#9B5CFF" }, size = { { 0, 10 }, { 1, 2 } }, transp = { { 0, 0.2 }, { 1, 1 } }, life = 0.8, speed = 0, rotSpeed = { 200, 300 }, light = 0.6 },
	{ "emit", tex = "spark", rate = 60, time = 1.2, color = { "#FFFFFF", "#B46CFF" }, size = { { 0, 0.6 }, { 1, 0 } }, life = { 0.5, 0.8 }, speed = { 12, 16 }, shape = "Sphere", inward = true },
	{ "shell", color = "#2A0050", from = 10, to = 0.5, time = 1.2, material = "Neon", startT = 0.6, ease = "Quad" },
}

local DEFAULT_COLOR_LAYERS = { light = true, shell = true, bolt = true, arc = true, pillar = true }
function VFX.play(name, where, opts)
	opts = opts or {}
	local layers = type(name) == "table" and name or P[name]
	if not layers then error("BrickwireVFX: unknown preset '" .. tostring(name) .. "' — " .. table.concat(VFX.list(), ", "), 2) end
	local cf = toCF(where)
	local o = { scale = opts.scale or 1, color = opts.color and C(opts.color) or nil, density = opts.density or 1, shake = opts.shake or 1 }
	local root = anchorPart(cf, opts.life or 4)
	for _, d in ipairs(layers) do
		local fn = L[d[1]]
		if fn then
			local oo = o
			if o.color and not DEFAULT_COLOR_LAYERS[d[1]] and d.tint == false then oo = { scale = o.scale, density = o.density, shake = o.shake } end
			local ok, err = pcall(fn, root, cf, d, oo)
			if not ok then warn("BrickwireVFX layer " .. tostring(d[1]) .. ": " .. tostring(err)) end
		end
	end
	return root
end
function VFX.bolt(from, to, opts)
	opts = opts or {}
	local root = anchorPart(CFrame.new(to), 1)
	L.bolt(root, CFrame.new(to), { fromPos = from, branches = opts.branches or 2, time = opts.time or 0.25, width = opts.width }, { scale = opts.scale or 1, color = opts.color and C(opts.color) or nil })
	return root
end
function VFX.flash(target, color, time)
	local h = Instance.new("Highlight")
	h.FillColor = C(color or "#FFFFFF")
	h.OutlineColor = C(color or "#FFFFFF")
	h.FillTransparency = 0.2
	h.Parent = target
	tween(h, time or 0.25, { FillTransparency = 1, OutlineTransparency = 1 })
	Debris:AddItem(h, (time or 0.25) + 0.1)
	return h
end
function VFX.trail(part, opts)
	opts = opts or {}
	local a0, a1 = Instance.new("Attachment"), Instance.new("Attachment")
	local w = opts.width or 1.5
	a0.Position = Vector3.new(0, w / 2, 0)
	a1.Position = Vector3.new(0, -w / 2, 0)
	a0.Parent, a1.Parent = part, part
	local t = Instance.new("Trail")
	t.Attachment0, t.Attachment1 = a0, a1
	t.Color = cseq(opts.color or { "#FFFFFF", "#7FD3FF" })
	t.Transparency = nseq({ 0.2, 1 })
	t.Lifetime = opts.lifetime or 0.25
	t.LightEmission = 1
	t.FaceCamera = true
	t.Parent = part
	return t
end
local shaking = 0
function VFX.shake(intensity, duration)
	if not RunService:IsClient() then return end
	local cam = workspace.CurrentCamera
	if not cam then return end
	shaking += 1
	local id = shaking
	local t0 = os.clock()
	local conn
	conn = RunService.RenderStepped:Connect(function()
		local t = os.clock() - t0
		if t > duration or id ~= shaking then conn:Disconnect() return end
		local k = (1 - t / duration) * intensity
		cam.CFrame = cam.CFrame * CFrame.Angles(math.rad((math.random() - 0.5) * 2 * k), math.rad((math.random() - 0.5) * 2 * k), 0)
	end)
end
function VFX.list()
	local t = {}
	for k in pairs(P) do table.insert(t, k) end
	table.sort(t)
	return t
end
-- loop a preset on a part (demo pads, ambient effects): returns a stop() function
function VFX.loop(name, where, every, opts)
	local alive = true
	task.spawn(function()
		while alive do
			if typeof(where) == "Instance" and not where.Parent then break end
			VFX.play(name, typeof(where) == "Instance" and where:IsA("BasePart") and (where.CFrame * CFrame.new(0, where.Size.Y / 2 + 3, 0)) or where, opts)
			task.wait(every or 3)
		end
	end)
	return function() alive = false end
end
return VFX
