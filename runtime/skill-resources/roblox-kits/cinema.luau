-- camera fly-through module with splines and easing
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire Cinema module (ReplicatedStorage.BrickwireCinema). CLIENT-side camera cutscenes (LocalScript):
--   local Cinema = require(game.ReplicatedStorage:WaitForChild("BrickwireCinema"))
--   Cinema.play({
--     { type = "flyby", points = { {0,60,-120}, {40,30,-60}, {20,14,-25} }, look = "Workspace.Castle", time = 5 },
--     { type = "orbit", target = "Workspace.Castle", radius = 45, height = 14, from = 200, to = 290, time = 6 },
--     { type = "push_in", target = "Workspace.Castle.Gate", from = 40, to = 16, height = 4, angle = 180, time = 3, fov = { 70, 55 } },
--   }, { letterbox = true, skip = true, fadeIn = 0.6, fadeOut = 0.6 })
-- Shot types: hold, pan, dolly, orbit, flyby (Catmull-Rom spline, constant speed), push_in, pull_out, crane, reveal, track.
-- Common fields: time (s), ease ("sine" | "quad" | "cubic" | "quint" | "expo" | "back" | "smooth" | "linear"), fov (number or {from,to}),
--   roll (deg, dutch angle), shake (0..1), cut = "fade" (dip to black before the shot), focus = {x,y,z} offset added to the look point.
-- Targets: Vector3, {x,y,z}, an Instance, or a path string "Workspace.Castle" (centre of its bounding box).
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")
local Cinema = {}

local function V(v)
	if typeof(v) == "Vector3" then return v end
	if type(v) == "table" then return Vector3.new(v[1] or v.X or 0, v[2] or v.Y or 0, v[3] or v.Z or 0) end
	error("BrickwireCinema: expected a Vector3 or {x,y,z}, got " .. typeof(v), 3)
end
local function resolve(path)
	local cur = game
	for part in string.gmatch(path, "[^%.]+") do
		if cur == game and (part == "Workspace" or part == "workspace") then cur = workspace
		else
			local nxt = cur:FindFirstChild(part) or (RunService:IsRunning() and cur:WaitForChild(part, 5))
			if not nxt then return nil end
			cur = nxt
		end
	end
	return cur
end
-- Centre (Vector3) and size (number) of a target
function Cinema.focusOf(target)
	if typeof(target) == "string" then
		local inst = resolve(target)
		if not inst then error("BrickwireCinema: target '" .. target .. "' not found", 2) end
		target = inst
	end
	if typeof(target) == "Instance" then
		if target:IsA("BasePart") then return target.Position, math.max(target.Size.X, target.Size.Y, target.Size.Z) end
		if target:IsA("Model") then
			local ok, cf, size = pcall(function() return target:GetBoundingBox() end)
			if ok then return cf.Position, math.max(size.X, size.Y, size.Z) end
			return target:GetPivot().Position, 8
		end
		if target:IsA("Attachment") then return target.WorldPosition, 4 end
		error("BrickwireCinema: target must be a BasePart, Model or Attachment, got " .. target.ClassName, 2)
	end
	return V(target), 8
end

local EASE = {
	linear = function(t) return t end,
	sine = function(t) return -(math.cos(math.pi * t) - 1) / 2 end,
	quad = function(t) return t < 0.5 and 2 * t * t or 1 - (-2 * t + 2) ^ 2 / 2 end,
	cubic = function(t) return t < 0.5 and 4 * t * t * t or 1 - (-2 * t + 2) ^ 3 / 2 end,
	quint = function(t) return t < 0.5 and 16 * t ^ 5 or 1 - (-2 * t + 2) ^ 5 / 2 end,
	expo = function(t) if t <= 0 then return 0 elseif t >= 1 then return 1 end return t < 0.5 and 2 ^ (20 * t - 10) / 2 or (2 - 2 ^ (-20 * t + 10)) / 2 end,
	smooth = function(t) return t * t * t * (t * (t * 6 - 15) + 10) end,
	back = function(t) local c = 1.70158 * 1.525 return t < 0.5 and ((2 * t) ^ 2 * ((c + 1) * 2 * t - c)) / 2 or ((2 * t - 2) ^ 2 * ((c + 1) * (t * 2 - 2) + c) + 2) / 2 end,
	out = function(t) return 1 - (1 - t) ^ 3 end,
	["in"] = function(t) return t * t * t end,
}
Cinema.EASE = EASE
function Cinema.ease(name, t)
	t = math.clamp(t, 0, 1)
	local f = EASE[name or "sine"] or error("BrickwireCinema: unknown ease '" .. tostring(name) .. "'", 2)
	return f(t)
end
local function lerp(a, b, t) return a + (b - a) * t end

-- Catmull-Rom spline through points with constant-speed (arc-length) parameterisation
local function catmull(p0, p1, p2, p3, t)
	local t2, t3 = t * t, t * t * t
	return ((p1 * 2) + (p2 - p0) * t + (p0 * 2 - p1 * 5 + p2 * 4 - p3) * t2 + (p3 - p0 + p1 * 3 - p2 * 3) * t3) * 0.5
end
local function splineOf(points)
	local P = {}
	for i, p in ipairs(points) do P[i] = V(p) end
	if #P < 2 then error("BrickwireCinema: flyby needs at least 2 points", 3) end
	local segs = #P - 1
	local function raw(u) -- u in 0..1 over all segments
		local x = math.clamp(u, 0, 1) * segs
		local i = math.min(segs, math.floor(x) + 1)
		local lt = x - (i - 1)
		local p0 = P[math.max(1, i - 1)]
		local p3 = P[math.min(#P, i + 2)]
		return catmull(p0, P[i], P[i + 1], p3, lt)
	end
	local N = segs * 24
	local cum, prev = { 0 }, raw(0)
	for k = 1, N do
		local p = raw(k / N)
		cum[k + 1] = cum[k] + (p - prev).Magnitude
		prev = p
	end
	local total = cum[N + 1]
	return function(t)
		if total <= 0 then return raw(t) end
		local d = math.clamp(t, 0, 1) * total
		local lo, hi = 1, N + 1
		while hi - lo > 1 do
			local mid = (lo + hi) // 2
			if cum[mid] < d then lo = mid else hi = mid end
		end
		local span = cum[hi] - cum[lo]
		local f = span > 0 and (d - cum[lo]) / span or 0
		return raw(((lo - 1) + f) / N)
	end, total
end

local function orbitPos(c, r, h, deg) local a = math.rad(deg) return c + Vector3.new(math.sin(a) * r, h, math.cos(a) * r) end
-- Pure sampler: shot + eased progress e (0..1) → camera position, look point, fov, roll
local SAMPLERS = {}
function SAMPLERS.hold(s, e)
	return V(s.pos), s.look and Cinema.focusOf(s.look) or V(s.pos) + Vector3.new(0, 0, -1)
end
function SAMPLERS.pan(s, e)
	local a, b = Cinema.focusOf(s.from), Cinema.focusOf(s.to)
	return V(s.pos), a:Lerp(b, e)
end
function SAMPLERS.dolly(s, e)
	local a, b = V(s.from), V(s.to)
	local p = a:Lerp(b, e)
	return p, s.look and Cinema.focusOf(s.look) or p + (b - a).Unit * 10
end
function SAMPLERS.orbit(s, e)
	local c, size = Cinema.focusOf(s.target)
	local r = s.radius or math.max(12, size * 1.3)
	return orbitPos(c, r, s.height or r * 0.35, lerp(s.from or 0, s.to or 120, e)), c
end
function SAMPLERS.push_in(s, e, inv)
	local c, size = Cinema.focusOf(s.target)
	local d0, d1 = s.from or math.max(14, size * 2), s.to or math.max(6, size * 0.8)
	if inv then d0, d1 = d1, d0 end
	local d = lerp(d0, d1, e)
	local h = s.height or d * 0.25
	return orbitPos(c, d, h, s.angle or 0), c
end
function SAMPLERS.pull_out(s, e) return SAMPLERS.push_in(s, e, true) end
function SAMPLERS.crane(s, e)
	local c, size = Cinema.focusOf(s.target)
	local r = s.radius or math.max(14, size * 1.4)
	local h = lerp(s.fromHeight or 2, s.toHeight or size * 1.2 + 10, e)
	return orbitPos(c, lerp(r, r * (s.radiusEnd or 1), e), h, lerp(s.angle or 0, (s.angle or 0) + (s.turn or 25), e)), c + Vector3.new(0, lerp(0, s.lookRise or 0, e), 0)
end
-- reveal: starts low and close behind a foreground, rises and pulls back to show the whole target
function SAMPLERS.reveal(s, e)
	local c, size = Cinema.focusOf(s.target)
	local r0, r1 = s.fromRadius or math.max(8, size * 0.6), s.toRadius or math.max(20, size * 1.8)
	local h0, h1 = s.fromHeight or 1.5, s.toHeight or size * 0.9 + 6
	local ang = lerp(s.angle or 0, (s.angle or 0) + (s.turn or 40), e)
	return orbitPos(c, lerp(r0, r1, e), lerp(h0, h1, e), ang), c + Vector3.new(0, lerp(-size * 0.2, 0, e), 0)
end
function SAMPLERS.flyby(s, e)
	local f = s._spline
	if not f then f = splineOf(s.points) s._spline = f end
	local p = f(e)
	local look = s.look and Cinema.focusOf(s.look) or nil
	if not look then
		local q = f(math.min(1, e + 0.02))
		if (q - p).Magnitude < 1e-3 then q = p + (p - f(math.max(0, e - 0.02))) end
		look = p + (q - p).Unit * 20
	end
	return p, look
end
function SAMPLERS.track(s, e)
	local c = Cinema.focusOf(s.subject or s.target)
	local off = V(s.offset or { 0, 6, 16 })
	return c + off, c + V(s.focus or { 0, 1.5, 0 })
end

function Cinema.sample(shot, t)
	local f = SAMPLERS[shot.type or "hold"] or error("BrickwireCinema: unknown shot type '" .. tostring(shot.type) .. "'", 2)
	local e = Cinema.ease(shot.ease or (shot.type == "track" and "linear" or "sine"), t)
	local pos, look = f(shot, e)
	if shot.focus and shot.type ~= "track" then look = look + V(shot.focus) end
	local fov = shot.fov or 70
	if type(fov) == "table" then fov = lerp(fov[1], fov[2], e) end
	return pos, look, fov, lerp(type(shot.roll) == "table" and shot.roll[1] or shot.roll or 0, type(shot.roll) == "table" and shot.roll[2] or shot.roll or 0, e)
end
function Cinema.cframe(shot, t)
	local pos, look, fov, roll = Cinema.sample(shot, t)
	if (look - pos).Magnitude < 1e-3 then look = pos + Vector3.new(0, 0, -1) end
	return CFrame.lookAt(pos, look) * CFrame.Angles(0, 0, math.rad(roll)), fov
end
function Cinema.duration(shots)
	local t = 0
	for _, s in ipairs(shots) do t += (s.time or 3) end
	return t
end
-- Global time → shot index + local progress
function Cinema.at(shots, time)
	local acc = 0
	for i, s in ipairs(shots) do
		local d = s.time or 3
		if time <= acc + d or i == #shots then return i, math.clamp((time - acc) / d, 0, 1) end
		acc += d
	end
	return 1, 0
end

-- Quality check (pure math + optional raycasts in a live place). Returns { ok, issues = { "…" }, duration }
function Cinema.check(shots, opts)
	opts = opts or {}
	local issues = {}
	local function add(i, msg) table.insert(issues, string.format("shot %d (%s): %s", i, tostring(shots[i] and shots[i].type), msg)) end
	if type(shots) ~= "table" or #shots == 0 then return { ok = false, issues = { "no shots" }, duration = 0 } end
	local total = Cinema.duration(shots)
	if total > (opts.maxTotal or 40) then table.insert(issues, string.format("total %.1f s is long — players skip long intros; aim for 8–25 s", total)) end
	local types = {}
	local world = opts.world ~= false and select(2, pcall(function() return workspace.Raycast ~= nil and RaycastParams ~= nil end)) == true
	local ignore = table.clone(opts.ignore or {})
	for _, s in ipairs(shots) do
		for _, k in ipairs({ "target", "look", "subject", "from", "to" }) do
			local v = s[k]
			if typeof(v) == "string" then v = resolve(v) end
			if typeof(v) == "Instance" then table.insert(ignore, v) end
		end
	end
	for i, s in ipairs(shots) do
		local d = s.time or 3
		types[s.type or "hold"] = true
		if d < 1.2 then add(i, string.format("%.1f s is too short (reads as a glitch) — ≥1.5 s", d)) end
		if d > 12 and not opts.loop then add(i, string.format("%.1f s is long — split it or add motion", d)) end
		local okS, err = pcall(Cinema.sample, s, 0)
		if not okS then add(i, tostring(err)) else
			local N = 24
			local prevPos, prevVel, blocked, maxSpeed, near = nil, nil, 0, 0, math.huge
			for k = 0, N do
				local pos, look, fov, roll = Cinema.sample(s, k / N)
				local dir = look - pos
				near = math.min(near, dir.Magnitude)
				if k == 0 then
					if fov < 20 or fov > 100 then add(i, string.format("fov %.0f outside 20–100 (use 50–75 for most shots)", fov)) end
					if math.abs(roll) > 25 then add(i, string.format("roll %.0f° is extreme — keep dutch angles ≤ 15°", roll)) end
				end
				if dir.Magnitude > 1e-3 and math.abs(dir.Unit.Y) > 0.97 then add(i, "looks straight up/down — lookAt flips; offset the camera sideways") break end
				if prevPos then
					local vel = (pos - prevPos) / (d / N)
					maxSpeed = math.max(maxSpeed, vel.Magnitude)
					prevVel = vel
				end
				prevPos = pos
				if world then
					local okR, hit = pcall(function()
						local p = RaycastParams.new()
						p.FilterType = Enum.RaycastFilterType.Exclude
						p.FilterDescendantsInstances = ignore
						return workspace:Raycast(pos, dir * 0.95, p)
					end)
					if okR and hit and hit.Instance and hit.Instance.Transparency < 0.9 then blocked += 1 end
					if k % 6 == 0 then
						local okG, n = pcall(function()
							local c = 0
							for _, part in ipairs(workspace:GetPartBoundsInRadius(pos, 0.6)) do if part.Transparency < 0.9 then c += 1 end end
							return c
						end)
						if okG and n > 0 then add(i, string.format("camera is inside geometry at %.0f%% of the shot", k / N * 100)) end
					end
				end
			end
			if maxSpeed > (opts.maxSpeed or 140) then add(i, string.format("camera moves %.0f studs/s — too fast/nauseating; lengthen the shot or shorten the path", maxSpeed)) end
			if near < 2 then add(i, string.format("camera gets within %.1f studs of the look point — clipping risk", near)) end
			if blocked > N * 0.3 then add(i, string.format("view to the target is blocked in %d/%d samples — move the camera or ignore the blocker", blocked, N + 1)) end
		end
	end
	local n = 0
	for _ in pairs(types) do n += 1 end
	if #shots >= 3 and n == 1 then table.insert(issues, "every shot is the same type — vary it (wide → medium → close, orbit → push_in → crane)") end
	return { ok = #issues == 0, issues = issues, duration = total }
end

-- Ready-made shot lists. style: "intro" | "showcase" | "epic" | "boss" | "trailer" | "menu"
function Cinema.auto(target, style, opts)
	opts = opts or {}
	local c, size = Cinema.focusOf(target)
	local R = math.max(14, size * 1.3)
	local a = opts.angle or 200
	local T = opts.speed and (1 / opts.speed) or 1
	style = style or "intro"
	local t = target
	if style == "menu" then
		return { { type = "orbit", target = t, radius = R * 1.2, height = R * 0.35, from = a, to = a + 360, time = (opts.time or 60), ease = "linear", fov = 60 } }
	elseif style == "boss" then
		return {
			{ type = "reveal", target = t, angle = a, fromRadius = R * 0.5, toRadius = R * 1.1, fromHeight = 1, toHeight = size * 0.3, turn = 15, time = 3.5 * T, fov = 60, ease = "out" },
			{ type = "push_in", target = t, angle = a + 15, from = R * 1.1, to = R * 0.55, height = size * 0.15, time = 2 * T, fov = { 60, 45 }, roll = { 0, 8 }, ease = "quint", shake = 0.25 },
			{ type = "hold", pos = orbitPos(c, R * 0.55, size * 0.15, a + 15), look = t, time = 1.5 * T, fov = 45, roll = 8, shake = 0.15 },
		}
	elseif style == "epic" then
		return {
			{ type = "crane", target = t, angle = a, radius = R * 1.4, fromHeight = 1.5, toHeight = size * 1.4 + 12, turn = 20, time = 6 * T, fov = 65 },
			{ type = "orbit", target = t, radius = R * 1.1, height = size * 0.25, from = a + 20, to = a + 110, time = 6 * T, fov = 55 },
			{ type = "pull_out", target = t, angle = a + 110, from = R * 0.8, to = R * 2.4, height = size * 0.9, time = 5 * T, fov = 70, cut = "fade" },
		}
	elseif style == "trailer" then
		return {
			{ type = "flyby", points = { orbitPos(c, R * 3, size * 2 + 30, a - 40), orbitPos(c, R * 2, size + 15, a - 10), orbitPos(c, R * 1.2, size * 0.5, a + 10) }, look = t, time = 3 * T, fov = 70 },
			{ type = "push_in", target = t, angle = a + 60, from = R, to = R * 0.6, height = 2, time = 2.2 * T, fov = 55, cut = "fade" },
			{ type = "orbit", target = t, radius = R * 0.9, height = 3, from = a + 120, to = a + 160, time = 2.2 * T, fov = 50, roll = 6 },
			{ type = "crane", target = t, angle = a + 200, radius = R, fromHeight = 2, toHeight = size + 10, turn = 15, time = 2.5 * T, fov = 60 },
			{ type = "pull_out", target = t, angle = a + 230, from = R, to = R * 2.6, height = size * 0.8, time = 3 * T, fov = 65, cut = "fade" },
		}
	end
	-- intro / showcase: establishing fly-in → orbit → hero push-in → crane reveal
	return {
		{ type = "flyby", points = { orbitPos(c, R * 3.2, size * 1.6 + 35, a - 50), orbitPos(c, R * 2, size * 0.9 + 14, a - 20), orbitPos(c, R * 1.25, size * 0.4 + 3, a) }, look = t, time = 5 * T, fov = 70 },
		{ type = "orbit", target = t, radius = R * 1.25, height = size * 0.4 + 3, from = a, to = a + 75, time = 5 * T, fov = 60 },
		{ type = "push_in", target = t, angle = a + 75, from = R * 1.25, to = R * 0.7, height = size * 0.2 + 1.5, time = 3 * T, fov = { 60, 50 }, ease = "cubic" },
		{ type = "crane", target = t, angle = a + 75, radius = R * 0.9, fromHeight = size * 0.2 + 1.5, toHeight = size * 1.2 + 14, radiusEnd = 1.8, turn = 30, time = 4.5 * T, fov = 65, cut = "fade" },
	}
end

-- ---------------------------------------------------------------- player (client)
local function overlay()
	local pg = game:GetService("Players").LocalPlayer:WaitForChild("PlayerGui")
	local g = Instance.new("ScreenGui")
	g.Name = "BrickwireCinema"
	g.IgnoreGuiInset = true
	g.ResetOnSpawn = false
	g.DisplayOrder = 50
	local function bar(name, y, ay)
		local f = Instance.new("Frame")
		f.Name = name
		f.BackgroundColor3 = Color3.new(0, 0, 0)
		f.BorderSizePixel = 0
		f.AnchorPoint = Vector2.new(0, ay)
		f.Position = UDim2.fromScale(0, y)
		f.Size = UDim2.new(1, 0, 0, 0)
		f.Parent = g
		return f
	end
	local top, bottom = bar("Top", 0, 0), bar("Bottom", 1, 1)
	local fade = Instance.new("Frame")
	fade.Name = "Fade"
	fade.BackgroundColor3 = Color3.new(0, 0, 0)
	fade.BorderSizePixel = 0
	fade.Size = UDim2.fromScale(1, 1)
	fade.BackgroundTransparency = 1
	fade.ZIndex = 5
	fade.Parent = g
	g.Parent = pg
	return g, top, bottom, fade
end

-- Plays shots on the local camera. opts: letterbox (true), skip (true), fadeIn/fadeOut (s), dof (true), loop (false),
-- onDone(fn), restore (true: give the camera back to the player). Returns handle { stop = fn, done = bool }.
function Cinema.play(shots, opts)
	opts = opts or {}
	if not RunService:IsClient() then error("BrickwireCinema.play runs on the CLIENT (LocalScript)", 2) end
	local cam = workspace.CurrentCamera
	local handle = { done = false }
	local g, top, bottom, fade = overlay()
	local prevType, prevFov = cam.CameraType, cam.FieldOfView
	cam.CameraType = Enum.CameraType.Scriptable
	local dof
	if opts.dof then
		dof = Instance.new("DepthOfFieldEffect")
		dof.Name = "BrickwireCinemaDOF"
		dof.FarIntensity, dof.NearIntensity, dof.InFocusRadius = 0.35, 0.2, 18
		dof.Parent = cam
	end
	local tw = function(o, t, goal) TweenService:Create(o, TweenInfo.new(t, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut), goal):Play() end
	if opts.letterbox ~= false then
		tw(top, 0.6, { Size = UDim2.new(1, 0, 0.11, 0) })
		tw(bottom, 0.6, { Size = UDim2.new(1, 0, 0.11, 0) })
	end
	if opts.fadeIn and opts.fadeIn > 0 then
		fade.BackgroundTransparency = 0
		tw(fade, opts.fadeIn, { BackgroundTransparency = 1 })
	end
	local conn
	local function finish()
		if handle.done then return end
		handle.done = true
		if conn then conn:Disconnect() end
		local function restore()
			if opts.restore ~= false then
				cam.CameraType = prevType == Enum.CameraType.Scriptable and Enum.CameraType.Custom or prevType
				cam.FieldOfView = prevFov
			end
			if dof then dof:Destroy() end
			tw(top, 0.4, { Size = UDim2.new(1, 0, 0, 0) })
			tw(bottom, 0.4, { Size = UDim2.new(1, 0, 0, 0) })
			tw(fade, 0.4, { BackgroundTransparency = 1 })
			task.delay(0.5, function() g:Destroy() end)
			if opts.onDone then task.spawn(opts.onDone) end
		end
		if opts.fadeOut and opts.fadeOut > 0 then
			tw(fade, opts.fadeOut, { BackgroundTransparency = 0 })
			task.delay(opts.fadeOut, restore)
		else
			restore()
		end
	end
	handle.stop = finish
	if opts.skip ~= false then
		local b = Instance.new("TextButton")
		b.Name = "Skip"
		b.Text = opts.skipText or "Skip  ›"
		b.Font = Enum.Font.GothamBold
		b.TextSize = 18
		b.TextColor3 = Color3.new(1, 1, 1)
		b.BackgroundColor3 = Color3.new(0, 0, 0)
		b.BackgroundTransparency = 0.45
		b.AnchorPoint = Vector2.new(1, 1)
		b.Position = UDim2.new(1, -24, 1, -24)
		b.Size = UDim2.fromOffset(110, 40)
		b.ZIndex = 6
		local corner = Instance.new("UICorner")
		corner.CornerRadius = UDim.new(0, 10)
		corner.Parent = b
		b.Parent = g
		b.Activated:Connect(finish)
	end
	local total = Cinema.duration(shots)
	local t0 = os.clock()
	local lastIdx = 0
	conn = RunService.RenderStepped:Connect(function()
		local now = os.clock() - t0
		if now >= total then
			if opts.loop then t0 = os.clock() now = 0 else finish() return end
		end
		local i, p = Cinema.at(shots, now)
		local s = shots[i]
		if i ~= lastIdx then
			lastIdx = i
			if s.cut == "fade" and i > 1 then
				fade.BackgroundTransparency = 0
				tw(fade, 0.35, { BackgroundTransparency = 1 })
			end
		end
		local cf, fov = Cinema.cframe(s, p)
		if s.shake and s.shake > 0 then
			local k = s.shake * 0.6
			cf = cf * CFrame.Angles(math.rad((math.random() - 0.5) * k), math.rad((math.random() - 0.5) * k), 0)
		end
		cam.CFrame = cf
		cam.FieldOfView = fov
		if dof then
			local pos, look = Cinema.sample(s, p)
			dof.FocusDistance = (look - pos).Magnitude
		end
	end)
	return handle
end

-- Edit-mode preview: puts the (edit) camera where the cutscene is at time seconds (for screenshots).
function Cinema.preview(shots, time)
	local i, p = Cinema.at(shots, time or 0)
	local cf, fov = Cinema.cframe(shots[i], p)
	local cam = workspace.CurrentCamera
	cam.CFrame = cf
	cam.FieldOfView = fov
	return i, p
end
return Cinema
