-- cutscene timeline module (camera, subtitles, sound, shake, flash, skip)
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire Cutscene module (ReplicatedStorage.BrickwireCutscene) 1.9 — timeline cutscenes + ready gacha / event / story scenes.
-- Default look: style = "animedice" (Roblox Anime Dice: chunky FredokaOne text with a black outline, roll ticker with "1 in N"
-- odds, rarity colours, bigger pause / shake / flash / rays the rarer it is, fake ending for Mythic+). style = "clean" is calmer.
-- CLIENT (LocalScript):
--   local Cutscene = require(game.ReplicatedStorage:WaitForChild("BrickwireCutscene"))
--   Cutscene.listen()   -- plays whatever the server sends: "case" | "egg" | "dice" | "event" | "story" | "timeline"
--   Cutscene.play({ style = "animedice", events = {
--     { at = 0,   camera = { { type = "push_in", target = "Workspace.Boss", from = 40, to = 14, time = 3 } } },   -- BrickwireCinema shots
--     { at = 0,   sound = "rbxassetid://…", music = true, volume = 0.6, fadeIn = 1, fadeOut = 1, time = 8 },
--     { at = 0.5, say = "You came…", speaker = "Shadow King", time = 2.5 },      -- subtitle typed letter by letter
--     { at = 3,   title = "BOSS FIGHT", sub = "Shadow King", time = 2 },         -- title card
--     { at = 3,   shake = 0.8, time = 0.4 }, { at = 3, flash = "#FFFFFF", time = 0.25 }, { at = 3, vfx = "explosion", where = "Workspace.Boss" },
--     { at = 4,   tween = "Workspace.Gate", goal = { Transparency = 1 }, time = 1 },
--     { at = 4,   fov = 50, time = 0.6 }, { at = 4, blur = 12, time = 0.3 }, { at = 5, color = { Saturation = -0.4 }, time = 1 },
--     { at = 6,   fire = "BossReady" },                                          -- opts.onEvent("BossReady")
--   } }, { skip = true, lockControls = true, onDone = function() end })
-- SERVER (Script): rewards are ALWAYS rolled on the server, the client only shows them:
--   local item = Cutscene.roll(POOL, { luck = 2 })       -- POOL = { { name = "Naruto", rarity = "Rare", chance = 1/300 }, … }
--   Cutscene.show(player | "all", "case", { result = item, pool = POOL })
-- Ready scenes (client): Cutscene.caseOpen(result, opts) · Cutscene.eggHatch(results, opts) · Cutscene.diceRoll(result, opts)
--   · Cutscene.eventStart(opts) · Cutscene.story(frames, opts). Each also has a *Timeline(...) builder for Cutscene.check.
-- Rarities: Common Uncommon Rare Epic Legendary Mythic Secret (or a number 1..7).
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")
local RS = game:GetService("ReplicatedStorage")
local Cutscene = { VERSION = "1.9.0", defaultStyle = "animedice" }

-- built-in Roblox sounds (always available); replace with your own rbxassetid:// ids
Cutscene.SOUNDS = {
	tick = "rbxasset://sounds/clickfast.wav", whoosh = "rbxasset://sounds/swoosh.wav", hit = "rbxasset://sounds/snap.wav",
	reveal = "rbxasset://sounds/electronicpingshort.wav", music = "",
}
Cutscene.RARITIES = { "Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic", "Secret" }
local COLORS = { Common = "#D2D2D2", Uncommon = "#5CFF5C", Rare = "#3DA5FF", Epic = "#B14CFF", Legendary = "#FFC727", Mythic = "#FF3D6E", Secret = "#FFFFFF" }
Cutscene.STYLES = {
	animedice = { font = Enum.Font.FredokaOne, titleFont = Enum.Font.LuckiestGuy, stroke = 3, dim = 0.35, punch = true, tilt = -6, speedLines = true, fakeout = true, colors = COLORS },
	clean = { font = Enum.Font.GothamBold, titleFont = Enum.Font.GothamBlack, stroke = 1.5, dim = 0.25, punch = false, tilt = 0, speedLines = false, fakeout = false, colors = COLORS },
}
Cutscene.MUTATIONS = { Silver = "#D9E3EA", Gold = "#FFD54A", Huge = "#7CF0FF", Titanic = "#FF7A3D", Perfect = "#FFF27A", Rainbow = "#FF66CC" }
-- reading time limits per scene kind (seconds) used by Cutscene.check
Cutscene.LIMITS = { case = { 4, 6 }, egg = { 3, 5 }, dice = { 0.8, 6 }, event = { 3, 12 }, story = { 6, 30 }, intro = { 4, 30 } }

local function C(v)
	if typeof(v) == "Color3" then return v end
	return Color3.fromHex(tostring(v or "#FFFFFF"))
end
local function styleOf(s)
	if type(s) == "table" then return s end
	return Cutscene.STYLES[s or Cutscene.defaultStyle] or Cutscene.STYLES.animedice
end
local function lib(name)
	local m = RS:FindFirstChild(name)
	if not m then return nil end
	local ok, mod = pcall(require, m)
	return ok and mod or nil
end
local RNG = (Random and Random.new) and Random.new() or nil
local function rand(a, b)
	local r = RNG and RNG:NextNumber() or math.random()
	if a then return a + (b - a) * r end
	return r
end

-- ---------------------------------------------------------------- rarity / odds / ease (pure)
function Cutscene.tier(r)
	if type(r) == "table" then r = r.rarity end
	if type(r) == "number" then return math.clamp(math.floor(r), 1, #Cutscene.RARITIES) end
	for i, n in ipairs(Cutscene.RARITIES) do
		if n == r or string.lower(n) == string.lower(tostring(r)) then return i end
	end
	return 1
end
-- Feel parameters for a rarity: the rarer, the longer the pause before the hit and the stronger everything is.
function Cutscene.rarity(r, style)
	local st = styleOf(style)
	local t = Cutscene.tier(r)
	local name = Cutscene.RARITIES[t]
	local k = (t - 1) / (#Cutscene.RARITIES - 1)
	return {
		name = name, tier = t, color = C(st.colors[name] or "#FFFFFF"), rainbow = t == #Cutscene.RARITIES,
		pause = 0.1 + 0.6 * k, shake = 0.1 + 1.2 * k * k, flash = t >= 3, rays = t >= 4, big = t >= 4,
		fakeout = st.fakeout == true and t >= 6, particles = 8 + 10 * t, label = string.upper(name) .. (t >= 4 and "!" or ""),
	}
end
-- 300 → "1 in 300", 17250 → "1 in 17.3k", 2.5e6 → "1 in 2.5M"
function Cutscene.odds(n)
	if type(n) ~= "number" or n <= 0 then return "" end
	if n < 1 then n = 1 / n end
	local units = { { 1e12, "T" }, { 1e9, "B" }, { 1e6, "M" }, { 1e3, "k" } }
	for _, u in ipairs(units) do
		if n >= u[1] then
			local v = n / u[1]
			local s = v >= 100 and string.format("%d", math.floor(v + 0.5)) or string.gsub(string.format("%.1f", math.floor(v * 10 + 0.5) / 10), "%.0$", "")
			return "1 in " .. s .. u[2]
		end
	end
	return "1 in " .. string.format("%d", math.floor(n + 0.5))
end
local EASE = {
	linear = function(t) return t end,
	sine = function(t) return -(math.cos(math.pi * t) - 1) / 2 end,
	quad = function(t) return 1 - (1 - t) * (1 - t) end,
	cubic = function(t) return 1 - (1 - t) ^ 3 end,
	quart = function(t) return 1 - (1 - t) ^ 4 end,
	quint = function(t) return 1 - (1 - t) ^ 5 end,
	expo = function(t) return t >= 1 and 1 or 1 - 2 ^ (-10 * t) end,
	back = function(t) local c = 1.70158 return 1 + (c + 1) * (t - 1) ^ 3 + c * (t - 1) ^ 2 end,
}
Cutscene.EASE = EASE
function Cutscene.ease(name, t)
	t = math.clamp(t, 0, 1)
	return (EASE[name or "quart"] or EASE.quart)(t)
end

-- ---------------------------------------------------------------- server: weighted roll
-- pool items: { name=, rarity=, weight= | chance= (0..1) | odds= (N of "1 in N"), icon=, … }. opts.luck boosts rarer items.
function Cutscene.roll(pool, opts)
	opts = opts or {}
	if RunService:IsClient() and not opts.allowClient then error("Cutscene.roll must run on the SERVER (the client only shows the result)", 2) end
	if type(pool) ~= "table" or #pool == 0 then error("Cutscene.roll: empty pool", 2) end
	local luck = math.max(opts.luck or 1, 0.01)
	local ws, total = {}, 0
	for i, it in ipairs(pool) do
		local w = it.weight or (it.chance and it.chance > 0 and it.chance) or (it.odds and it.odds > 0 and 1 / it.odds) or 1
		local k = (Cutscene.tier(it) - 1) / (#Cutscene.RARITIES - 1)
		w = w * luck ^ k
		ws[i] = w
		total += w
	end
	local pick, acc = #pool, rand() * total
	for i, w in ipairs(ws) do
		acc -= w
		if acc <= 0 then pick = i break end
	end
	local out = table.clone(pool[pick])
	out.rarity = out.rarity or Cutscene.RARITIES[Cutscene.tier(out)]
	out.odds = out.odds or math.floor(total / ws[pick] + 0.5)
	out.index = pick
	return out
end

-- ---------------------------------------------------------------- UI helpers
local function tw(o, t, goal, style, dir)
	local tween = TweenService:Create(o, TweenInfo.new(math.max(t, 0.01), style or Enum.EasingStyle.Quad, dir or Enum.EasingDirection.Out), goal)
	tween:Play()
	return tween
end
local function new(cls, props, parent)
	local o = Instance.new(cls)
	for k, v in pairs(props or {}) do o[k] = v end
	if parent then o.Parent = parent end
	return o
end
local function text(parent, st, props)
	local l = new("TextLabel", {
		BackgroundTransparency = 1, Font = props.font or st.font, Text = props.text or "", TextColor3 = C(props.color or "#FFFFFF"),
		TextScaled = true, Size = props.size or UDim2.fromScale(1, 0.2), Position = props.pos or UDim2.fromScale(0.5, 0.5),
		AnchorPoint = props.anchor or Vector2.new(0.5, 0.5), Rotation = props.rot or 0, ZIndex = props.z or 3, Name = props.name or "Text",
	}, parent)
	new("UIStroke", { Thickness = props.stroke or st.stroke, Color = C(props.strokeColor or "#000000"), Name = "Stroke" }, l)
	return l
end
local function rainbow(o)
	return new("UIGradient", { Name = "Rainbow", Color = ColorSequence.new({
		ColorSequenceKeypoint.new(0, C("#FF4D4D")), ColorSequenceKeypoint.new(0.2, C("#FFC727")), ColorSequenceKeypoint.new(0.4, C("#5CFF5C")),
		ColorSequenceKeypoint.new(0.6, C("#3DA5FF")), ColorSequenceKeypoint.new(0.8, C("#B14CFF")), ColorSequenceKeypoint.new(1, C("#FF4D4D")),
	}) }, o)
end
local function sound(parent, id, vol, pitch)
	if type(id) ~= "string" or id == "" then return nil end
	local s = new("Sound", { SoundId = id, Volume = vol or 0.6, PlaybackSpeed = pitch or 1, Name = "CutsceneSound" }, parent)
	s:Play()
	pcall(function() game:GetService("Debris"):AddItem(s, 8) end)
	return s
end

-- ---------------------------------------------------------------- timeline length + quality check (pure)
local function eventLength(e)
	local len = e.time or 0
	if e.camera then
		local cm = lib("BrickwireCinema")
		local d = 0
		if cm then d = cm.duration(e.camera) else for _, s in ipairs(e.camera) do d += s.time or 3 end end
		len = math.max(len, d)
	end
	return len
end
function Cutscene.duration(tl)
	local d = tl.length or 0
	for _, e in ipairs(tl.events or tl) do
		if type(e) == "table" then d = math.max(d, (e.at or 0) + eventLength(e)) end
	end
	return d
end
-- Quality gate: Skip, length per kind, sound on key moments, readable subtitles, camera (BrickwireCinema.check: walls,
-- speed, clipping), reward rolled on the server. opts: kind = "case"|"egg"|"dice"|"event"|"story"|"intro", reward, world.
function Cutscene.check(tl, opts)
	opts = opts or {}
	local issues = {}
	local function add(s) table.insert(issues, s) end
	if type(tl) ~= "table" then return { ok = false, issues = { "timeline must be a table" }, duration = 0 } end
	local events = tl.events or tl
	local kind = opts.kind or tl.kind
	local d = Cutscene.duration(tl)
	local lim = Cutscene.LIMITS[kind or ""] or { 0.5, 40 }
	if d > lim[2] + 0.05 then add(string.format("too long: %.1f s (aim ≤ %d s for %s) — players replay this; cut pauses", d, lim[2], kind or "a cutscene")) end
	if d < lim[1] - 0.05 then add(string.format("too short: %.1f s (≥ %d s for %s) — no build-up before the reveal", d, lim[1], kind or "a cutscene")) end
	if tl.skip == false or opts.skip == false then add("no Skip — every cutscene needs Skip (and a short skip-to-result for rewards)") end
	local sounds, keys = 0, 0
	local cm = lib("BrickwireCinema")
	for i, e in ipairs(events) do
		if type(e) ~= "table" then add("event " .. i .. " is not a table") continue end
		if (e.at or 0) < 0 then add("event " .. i .. ": negative at") end
		if e.sound or e.music or e.sfx then sounds += 1 end
		if e.title or e.flash or e.shake or e.vfx or e.key then keys += 1 end
		local line = e.say or e.subtitle
		if type(line) == "string" then
			local need = 0.8 + #line / 18
			if (e.time or 3) < need then add(string.format("event %d: subtitle shown %.1f s, needs ≥ %.1f s to read", i, e.time or 3, need)) end
		end
		if e.tween and type(e.goal) ~= "table" then add("event " .. i .. ": tween needs goal = { Property = value }") end
		if e.camera and cm then
			local r = cm.check(e.camera, { maxTotal = lim[2], world = opts.world })
			for _, s in ipairs(r.issues) do add("camera: " .. s) end
		end
	end
	if sounds == 0 then add("no sound — add a sound to every key moment (whoosh on moves, hit on impacts, reveal on the result, music for intros)") end
	if keys >= 3 and sounds < 2 then add(string.format("%d key moments but %d sound(s) — sound every accent", keys, sounds)) end
	local reward = opts.reward or tl.reward or kind == "case" or kind == "egg" or kind == "dice"
	if reward and not (tl.serverResult or opts.serverResult) then add("reward scene: roll the result on the SERVER (Cutscene.roll) and pass it in — the client only shows it") end
	return { ok = #issues == 0, issues = issues, duration = d }
end

-- ---------------------------------------------------------------- player (client)
local function localPlayer() return Players.LocalPlayer end
local function character()
	local ok, c = pcall(function() return localPlayer().Character end)
	return ok and c or nil
end
local function controls(on)
	pcall(function()
		local pm = require(localPlayer():WaitForChild("PlayerScripts"):WaitForChild("PlayerModule"))
		local c = pm:GetControls()
		if on then c:Enable() else c:Disable() end
	end)
end
local function resolve(v)
	if typeof(v) == "Instance" then return v end
	if type(v) ~= "string" then return nil end
	local cur = game
	for seg in string.gmatch(v, "[^%.]+") do
		if cur == game and seg == "Workspace" then cur = workspace else cur = cur and cur:FindFirstChild(seg) end
	end
	return cur ~= game and cur or nil
end
Cutscene.resolve = resolve
local ACTIVE = nil

-- Plays a timeline. tl = { events = {…}, style =, skip =, onSkip = fn(ctx), length = }. opts: skip (true), lockControls (true),
-- letterbox (false), restore (true), onDone(skipped), onEvent(name, e). Returns handle { stop(), skip(), done, skipped }.
function Cutscene.play(tl, opts)
	opts = opts or {}
	if not RunService:IsClient() then error("Cutscene.play runs on the CLIENT (LocalScript); on the server use Cutscene.show(player, scene, data)", 2) end
	if ACTIVE and not ACTIVE.done then ACTIVE.stop() end
	local st = styleOf(tl.style or opts.style)
	local player = localPlayer()
	local cam = workspace.CurrentCamera
	local handle = { done = false, skipped = false }
	ACTIVE = handle
	local gui = new("ScreenGui", { Name = "BrickwireCutscene", IgnoreGuiInset = true, ResetOnSpawn = false, DisplayOrder = 60 })
	local layer = new("Frame", { Name = "Layer", BackgroundTransparency = 1, Size = UDim2.fromScale(1, 1), ZIndex = 2 }, gui)
	local dim = new("Frame", { Name = "Dim", BackgroundColor3 = C("#000000"), BackgroundTransparency = 1, BorderSizePixel = 0, Size = UDim2.fromScale(1, 1), ZIndex = 1 }, gui)
	local top = new("Frame", { Name = "Top", BackgroundColor3 = C("#000000"), BorderSizePixel = 0, Size = UDim2.new(1, 0, 0, 0), ZIndex = 8 }, gui)
	local bottom = new("Frame", { Name = "Bottom", BackgroundColor3 = C("#000000"), BorderSizePixel = 0, AnchorPoint = Vector2.new(0, 1), Position = UDim2.fromScale(0, 1), Size = UDim2.new(1, 0, 0, 0), ZIndex = 8 }, gui)
	local flash = new("Frame", { Name = "Flash", BackgroundColor3 = C("#FFFFFF"), BackgroundTransparency = 1, BorderSizePixel = 0, Size = UDim2.fromScale(1, 1), ZIndex = 9 }, gui)
	gui.Parent = player:WaitForChild("PlayerGui")
	local prevType, prevFov, prevCF = cam.CameraType, cam.FieldOfView, cam.CFrame
	local owned = {}
	local frames = {}
	local camShots, camStart, camHold = nil, 0, nil
	local shakeAmp, shakeEnd = 0, 0
	local t0 = os.clock()
	local gen = 0
	local ctx = { gui = gui, layer = layer, style = st, cam = cam, handle = handle, player = player, sounds = tl.sounds or Cutscene.SOUNDS, owned = owned }
	local function now() return os.clock() - t0 end
	function ctx.after(t, fn)
		local g = gen
		task.delay(math.max(t or 0, 0), function() if g == gen and not handle.done then fn() end end)
	end
	function ctx.frame(fn) table.insert(frames, fn) end
	function ctx.sound(id, vol, pitch) return sound(gui, ctx.sounds[id] or id, vol, pitch) end
	function ctx.shake(a, t)
		shakeAmp = math.max(shakeAmp, a or 0.5)
		shakeEnd = now() + (t or 0.35)
	end
	function ctx.flash(color, t)
		flash.BackgroundColor3 = C(color or "#FFFFFF")
		flash.BackgroundTransparency = 0
		tw(flash, t or 0.3, { BackgroundTransparency = 1 })
	end
	function ctx.dim(alpha, t) tw(dim, t or 0.3, { BackgroundTransparency = 1 - (alpha or st.dim) }) end
	function ctx.letterbox(on, t)
		local h = on and 0.11 or 0
		tw(top, t or 0.5, { Size = UDim2.new(1, 0, h, 0) })
		tw(bottom, t or 0.5, { Size = UDim2.new(1, 0, h, 0) })
	end
	function ctx.text(props) return text(props.parent or layer, st, props) end
	function ctx.camera(shots)
		cam.CameraType = Enum.CameraType.Scriptable
		camShots, camStart, camHold = shots, now(), nil
	end
	function ctx.hold(cf)
		cam.CameraType = Enum.CameraType.Scriptable
		camShots, camHold = nil, cf
		cam.CFrame = cf
	end
	function ctx.effect(cls, props)
		local o = owned[cls]
		if not o then
			o = new(cls, props or {})
			o.Name = "BrickwireCutscene" .. cls
			o.Parent = cam
			owned[cls] = o
		end
		return o
	end
	function ctx.button(label, color, pos, cb)
		local b = new("TextButton", { Name = label, Text = label, Font = st.font, TextScaled = true, TextColor3 = C("#FFFFFF"), BackgroundColor3 = C(color or "#3CCB4A"),
			AnchorPoint = Vector2.new(0.5, 0.5), Position = pos or UDim2.fromScale(0.5, 0.86), Size = UDim2.fromScale(0.16, 0.075), ZIndex = 7, AutoButtonColor = true }, gui)
		new("UICorner", { CornerRadius = UDim.new(0.25, 0) }, b)
		new("UIStroke", { Thickness = st.stroke, Color = C("#000000"), ApplyStrokeMode = Enum.ApplyStrokeMode.Contextual }, b)
		new("UISizeConstraint", { MinSize = Vector2.new(120, 40) }, b)
		b.Activated:Connect(function() if cb then cb() end end)
		return b
	end
	-- rarity reveal card (centre of the screen): rays + RARITY! + name + odds, punch-in for style animedice
	function ctx.pop(result, o)
		o = o or {}
		local R = Cutscene.rarity(result, st)
		local card = new("Frame", { Name = "Reveal", BackgroundTransparency = 1, AnchorPoint = Vector2.new(0.5, 0.5), Position = o.pos or UDim2.fromScale(0.5, 0.45), Size = UDim2.fromScale(0.6, 0.4), ZIndex = 4 }, layer)
		new("UIAspectRatioConstraint", { AspectRatio = 1.6 }, card)
		local scale = new("UIScale", { Scale = st.punch and 0.2 or 0.85 }, card)
		if R.rays then
			local rays = new("Frame", { Name = "Rays", BackgroundTransparency = 1,
				AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.45), Size = UDim2.fromScale(1.6, 2.4), ZIndex = 3 }, card)
			for i = 1, 10 do
				new("Frame", { Name = "Ray" .. i, BackgroundColor3 = R.color, BackgroundTransparency = 0.55, BorderSizePixel = 0, AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.5), Size = UDim2.fromScale(0.05, 1.5), Rotation = i * 18, ZIndex = 3 }, rays)
			end
			local spin = 0
			ctx.frame(function(_, dt)
				if not rays.Parent then return true end
				spin += (dt or 1 / 60) * 40
				rays.Rotation = spin
				return false
			end)
		end
		local rl = text(card, st, { name = "Rarity", text = R.label, color = R.color, font = st.titleFont, size = UDim2.fromScale(1, 0.34), pos = UDim2.fromScale(0.5, 0.2), rot = st.tilt, z = 5, stroke = st.stroke + 1 })
		if R.rainbow then rainbow(rl) end
		text(card, st, { name = "ItemName", text = (result.mutation and (result.mutation .. " ") or "") .. tostring(result.name or "?"), size = UDim2.fromScale(1, 0.24), pos = UDim2.fromScale(0.5, 0.56), z = 5 })
		local odds = result.odds and Cutscene.odds(result.odds) or ""
		if odds ~= "" then text(card, st, { name = "Odds", text = odds, size = UDim2.fromScale(0.7, 0.15), pos = UDim2.fromScale(0.5, 0.78), z = 5 }) end
		if result.icon then
			new("ImageLabel", { Name = "Icon", BackgroundTransparency = 1, Image = result.icon, AnchorPoint = Vector2.new(0.5, 1), Position = UDim2.fromScale(0.5, 0.05), Size = UDim2.fromScale(0.35, 0.55), ZIndex = 5 }, card)
		end
		tw(scale, st.punch and 0.35 or 0.25, { Scale = 1 }, Enum.EasingStyle.Back)
		return card, R
	end
	local conn
	local function restore()
		gen += 1
		if conn then conn:Disconnect() conn = nil end
		if opts.restore ~= false then
			cam.CameraType = (prevType == Enum.CameraType.Scriptable) and Enum.CameraType.Custom or prevType
			cam.FieldOfView = prevFov
			if prevType == Enum.CameraType.Scriptable then cam.CFrame = prevCF end
		end
		for _, o in pairs(owned) do
			pcall(function()
				if o:IsA("Sound") then
					tw(o, 0.4, { Volume = 0 })
					task.delay(0.45, function() o:Destroy() end)
				else
					o:Destroy()
				end
			end)
		end
		if opts.lockControls ~= false then controls(true) end
		tw(top, 0.3, { Size = UDim2.new(1, 0, 0, 0) })
		tw(bottom, 0.3, { Size = UDim2.new(1, 0, 0, 0) })
		tw(dim, 0.3, { BackgroundTransparency = 1 })
		task.delay(0.35, function() gui:Destroy() end)
	end
	local function finish()
		if handle.done then return end
		handle.done = true
		restore()
		if ACTIVE == handle then ACTIVE = nil end
		if tl.onDone then task.spawn(tl.onDone, handle.skipped) end
		if opts.onDone then task.spawn(opts.onDone, handle.skipped) end
	end
	ctx.finish = finish
	handle.stop = finish
	function handle.skip()
		if handle.done or handle.skipped then return end
		handle.skipped = true
		if ctx.revealed then finish() return end
		gen += 1 -- cancels everything still scheduled
		frames = {}
		layer:ClearAllChildren()
		if tl.onSkip then
			local ok, err = pcall(tl.onSkip, ctx)
			if not ok then warn("BrickwireCutscene onSkip: " .. tostring(err)) finish() end
		else
			finish()
		end
	end
	if opts.lockControls ~= false then controls(false) end
	if opts.letterbox or tl.letterbox then ctx.letterbox(true) end
	if opts.skip ~= false and tl.skip ~= false then
		local b = ctx.button(opts.skipText or "Skip", "#2B2B2B", UDim2.new(1, -90, 1, -50), function() handle.skip() end)
		b.Name = "Skip"
		b.Size = UDim2.fromOffset(130, 46)
	end
	-- event runner
	local cinema = lib("BrickwireCinema")
	local vfx = lib("BrickwireVFX")
	local function runEvent(e)
		if e.run then e.run(ctx, e) end
		if e.camera then ctx.camera(e.camera) end
		if e.cut then ctx.hold(typeof(e.cut) == "CFrame" and e.cut or CFrame.lookAt(e.cut.pos, e.cut.look)) end
		if e.sound or e.sfx then
			local s = ctx.sound(e.sound or e.sfx, e.music and 0 or (e.volume or 0.6), e.pitch)
			if s then
				if e.music then
					s.Looped = true
					tw(s, e.fadeIn or 1, { Volume = e.volume or 0.5 })
					owned["Music" .. tostring(s)] = s
				end
				if e.time and e.fadeOut then ctx.after(math.max(e.time - e.fadeOut, 0), function() tw(s, e.fadeOut, { Volume = 0 }) end) end
			end
		end
		if e.say or e.subtitle then
			local line = e.say or e.subtitle
			local box = new("Frame", { Name = "Subtitle", BackgroundColor3 = C("#000000"), BackgroundTransparency = 0.45, AnchorPoint = Vector2.new(0.5, 1), Position = UDim2.fromScale(0.5, 0.86), Size = UDim2.fromScale(0.62, 0.12), ZIndex = 6 }, layer)
			new("UICorner", { CornerRadius = UDim.new(0.2, 0) }, box)
			if e.speaker then text(box, st, { name = "Speaker", text = e.speaker, color = e.speakerColor or "#FFD24D", size = UDim2.fromScale(0.4, 0.38), pos = UDim2.fromScale(0.03, -0.12), anchor = Vector2.new(0, 0.5), z = 7 }) end
			local l = text(box, st, { name = "Line", text = "", size = UDim2.fromScale(0.94, 0.62), pos = UDim2.fromScale(0.5, 0.58), z = 7, stroke = 1.5 })
			l.TextXAlignment = Enum.TextXAlignment.Left
			local n, cps = 0, e.cps or 38
			local started = now()
			ctx.frame(function()
				if not l.Parent then return true end
				local k = math.min(#line, math.floor((now() - started) * cps))
				if k ~= n then n = k l.Text = string.sub(line, 1, k) end
				return k >= #line
			end)
			if e.typing == false then l.Text = line end
			ctx.after(e.time or 3, function() box:Destroy() end)
		end
		if e.title then
			local card = new("Frame", { Name = "Title", BackgroundTransparency = 1, AnchorPoint = Vector2.new(0.5, 0.5), Position = e.pos or UDim2.fromScale(0.5, 0.42), Size = UDim2.fromScale(0.8, 0.3), ZIndex = 5 }, layer)
			local sc = new("UIScale", { Scale = st.punch and 1.8 or 1.1 }, card)
			local tl1 = text(card, st, { name = "Main", text = e.title, color = e.color or "#FFFFFF", font = st.titleFont, size = UDim2.fromScale(1, 0.62), pos = UDim2.fromScale(0.5, 0.35), rot = st.tilt, z = 6, stroke = st.stroke + 1 })
			if e.rainbow then rainbow(tl1) end
			if e.sub then text(card, st, { name = "Sub", text = e.sub, size = UDim2.fromScale(0.7, 0.26), pos = UDim2.fromScale(0.5, 0.85), z = 6 }) end
			tw(sc, 0.35, { Scale = 1 }, Enum.EasingStyle.Back)
			ctx.after(e.time or 2, function()
				tw(sc, 0.25, { Scale = 0.6 }, Enum.EasingStyle.Quad, Enum.EasingDirection.In)
				ctx.after(0.25, function() card:Destroy() end)
			end)
		end
		if e.flash then ctx.flash(e.flash == true and "#FFFFFF" or e.flash, e.time or 0.3) end
		if e.shake then ctx.shake(e.shake, e.time) end
		if e.dim then ctx.dim(e.dim == true and st.dim or e.dim, e.time) end
		if e.letterbox ~= nil then ctx.letterbox(e.letterbox, e.time) end
		if e.fov then tw(cam, e.time or 0.5, { FieldOfView = e.fov }, Enum.EasingStyle.Sine) end
		if e.blur then
			local b = ctx.effect("BlurEffect", { Size = 0 })
			tw(b, e.time or 0.3, { Size = e.blur })
		end
		if type(e.color) == "table" then
			local cc = ctx.effect("ColorCorrectionEffect", { Brightness = 0, Contrast = 0, Saturation = 0, TintColor = C("#FFFFFF") })
			local goal = {}
			for k, v in pairs(e.color) do goal[k] = (k == "TintColor") and C(v) or v end
			tw(cc, e.time or 0.5, goal)
		end
		if e.vfx and vfx then
			local where = resolve(e.where) or e.where
			if where then pcall(vfx.play, e.vfx, where, e.opts) end
		end
		if e.tween then
			local o = resolve(e.tween)
			if o then tw(o, e.time or 1, e.goal or {}, Enum.EasingStyle[e.ease or "Sine"] or Enum.EasingStyle.Sine) end
		end
		if e.fire then
			if opts.onEvent then task.spawn(opts.onEvent, e.fire, e) end
			if tl.onEvent then task.spawn(tl.onEvent, e.fire, e) end
		end
		if e.finish then finish() end
	end
	for _, e in ipairs(tl.events or tl) do
		if type(e) == "table" then ctx.after(e.at or 0, function() runEvent(e) end) end
	end
	local total = Cutscene.duration(tl)
	if tl.autoFinish ~= false then ctx.after(total + (tl.tail or 0.15), finish) end
	-- safety net: never leave a player locked in a cutscene (claim screens wait at most maxHold seconds)
	task.delay(total + (opts.maxHold or 12), function() if not handle.done then finish() end end)
	conn = RunService.RenderStepped:Connect(function(dt)
		if handle.done then return end
		local t = now()
		local cf
		if camShots and cinema then
			local local_t = t - camStart
			local d = cinema.duration(camShots)
			local i, p = cinema.at(camShots, math.min(local_t, d - 1e-3))
			local fov
			cf, fov = cinema.cframe(camShots[i], p)
			cam.FieldOfView = fov
		elseif camHold then
			cf = camHold
		end
		if shakeAmp > 0 then
			if t > shakeEnd then shakeAmp = 0 else
				local k = shakeAmp * 0.9
				cf = (cf or cam.CFrame) * CFrame.Angles(math.rad((rand() - 0.5) * k), math.rad((rand() - 0.5) * k), math.rad((rand() - 0.5) * k * 0.5))
			end
		end
		if cf then cam.CFrame = cf end
		local keep = {}
		for _, fn in ipairs(frames) do
			local ok, fin = pcall(fn, t, dt)
			if ok and not fin then table.insert(keep, fn) elseif not ok then warn("BrickwireCutscene frame: " .. tostring(fin)) end
		end
		frames = keep
	end)
	return handle
end

-- ---------------------------------------------------------------- ready scenes
local function resultCard(parent, st, item, size)
	local R = Cutscene.rarity(item, st)
	local f = new("Frame", { Name = "Card", BackgroundColor3 = C("#1E1E28"), BorderSizePixel = 0, Size = size, ZIndex = 3 }, parent)
	new("UICorner", { CornerRadius = UDim.new(0.08, 0) }, f)
	local stroke = new("UIStroke", { Thickness = 3, Color = R.color }, f)
	if R.rainbow then rainbow(stroke) end
	new("UIGradient", { Rotation = 90, Color = ColorSequence.new(C("#2C2C3A"), R.color:Lerp(C("#1E1E28"), 0.55)) }, f)
	if item.icon then
		new("ImageLabel", { Name = "Icon", BackgroundTransparency = 1, Image = item.icon, Size = UDim2.fromScale(0.8, 0.6), Position = UDim2.fromScale(0.1, 0.06), ZIndex = 4 }, f)
	else
		text(f, st, { name = "Initial", text = string.upper(string.sub(tostring(item.name or "?"), 1, 1)), color = R.color, size = UDim2.fromScale(0.7, 0.5), pos = UDim2.fromScale(0.5, 0.36), z = 4 })
	end
	text(f, st, { name = "Name", text = tostring(item.name or "?"), size = UDim2.fromScale(0.92, 0.2), pos = UDim2.fromScale(0.5, 0.8), z = 4, stroke = 1.5 })
	new("Frame", { Name = "Bar", BackgroundColor3 = R.color, BorderSizePixel = 0, AnchorPoint = Vector2.new(0, 1), Position = UDim2.fromScale(0, 1), Size = UDim2.fromScale(1, 0.06), ZIndex = 4 }, f)
	return f, R
end
local function fillerPool(pool, result)
	if type(pool) == "table" and #pool > 0 then return pool end
	local t = {}
	for i, r in ipairs(Cutscene.RARITIES) do t[i] = { name = r, rarity = r } end
	if result then table.insert(t, result) end
	return t
end
local function weightedFiller(pool)
	-- filler cards look like a real drop table: commons often, rares seldom (cosmetic only)
	local best, bestW = pool[1], -1
	for _ = 1, 2 do
		local it = pool[math.random(1, #pool)]
		local w = 1 / Cutscene.tier(it) + math.random()
		if w > bestW then best, bestW = it, w end
	end
	return best
end
local function claim(ctx, opts, hold)
	ctx.revealed = true
	local done = false
	local function close() if not done then done = true ctx.finish() end end
	ctx.button(opts.claimText or "Claim", "#3CCB4A", UDim2.fromScale(opts.rollAgain and 0.41 or 0.5, 0.86), close)
	if opts.rollAgain then
		ctx.button(opts.rollAgainText or "Roll again", "#3DA5FF", UDim2.fromScale(0.59, 0.86), function()
			close()
			task.spawn(opts.rollAgain)
		end)
	end
	ctx.after(opts.autoClose or hold or 3, close)
end

-- CS-style case: a strip of cards slides and decelerates (quart/quint ease) onto the server's result.
function Cutscene.caseTimeline(result, opts)
	opts = opts or {}
	local st = styleOf(opts.style)
	local R = Cutscene.rarity(result, st)
	local spin = opts.spin or 3.8
	local pool = fillerPool(opts.pool, result)
	local N, W = opts.cards or 44, opts.winIndex or 38
	local hit = spin + R.pause
	local tl = { kind = "case", style = opts.style, serverResult = opts.serverResult, skip = opts.skip, events = {} }
	local E = tl.events
	table.insert(E, { at = 0, dim = st.dim + 0.15, time = 0.25, sound = "whoosh", run = function(ctx)
		local win = new("Frame", { Name = "CaseWindow", BackgroundColor3 = C("#14141C"), BackgroundTransparency = 0.1, ClipsDescendants = true, AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.42), Size = UDim2.new(0.86, 0, 0, 170), ZIndex = 2 }, ctx.layer)
		new("UICorner", { CornerRadius = UDim.new(0, 14) }, win)
		new("UIStroke", { Thickness = 3, Color = C("#000000") }, win)
		local strip = new("Frame", { Name = "Strip", BackgroundTransparency = 1, AnchorPoint = Vector2.new(0, 0.5), Position = UDim2.new(0.5, 0, 0.5, 0), Size = UDim2.new(0, 1, 0, 150), ZIndex = 3 }, win)
		local cw, gap = opts.cardWidth or 130, 8
		local cards = {}
		for i = 1, N do
			local item = (i == W) and result or weightedFiller(pool)
			local c = resultCard(strip, st, item, UDim2.fromOffset(cw, 150))
			c.Position = UDim2.fromOffset((i - 1) * (cw + gap), 0)
			cards[i] = c
		end
		new("Frame", { Name = "Marker", BackgroundColor3 = C("#FFD24D"), BorderSizePixel = 0, AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.5), Size = UDim2.new(0, 4, 1, 0), ZIndex = 6 }, win)
		local target = (W - 1) * (cw + gap) + cw / 2 + rand(-0.38, 0.38) * cw -- cosmetic landing offset inside the winning card
		local start, lastIdx = os.clock(), 0
		ctx.frame(function()
			local p = math.clamp((os.clock() - start) / spin, 0, 1)
			local x = Cutscene.ease(opts.ease or "quint", p) * target
			strip.Position = UDim2.new(0.5, -x, 0.5, 0)
			local idx = math.floor(x / (cw + gap))
			if idx ~= lastIdx then
				lastIdx = idx
				ctx.sound("tick", 0.35, 1 + 0.25 * p)
			end
			return p >= 1
		end)
		ctx.caseWinner = cards[W]
	end })
	table.insert(E, { at = hit - 0.05, key = true, sound = "reveal", volume = 0.8, flash = R.flash and R.color or nil, time = 0.3, shake = R.shake, run = function(ctx)
		if ctx.caseWinner then
			local s = new("UIScale", { Scale = 1 }, ctx.caseWinner)
			tw(s, 0.25, { Scale = 1.12 }, Enum.EasingStyle.Back)
		end
	end })
	table.insert(E, { at = hit + 0.25, time = 1.2, run = function(ctx)
		local win = ctx.layer:FindFirstChild("CaseWindow")
		if win then tw(win, 0.25, { Position = UDim2.fromScale(0.5, 0.18) }) end
		ctx.pop(result, { pos = UDim2.fromScale(0.5, 0.52) })
		if R.big then ctx.sound("hit", 0.7) end
	end })
	tl.autoFinish = false
	table.insert(E, { at = hit + 1.45, run = function(ctx) claim(ctx, opts, 2.5) end })
	tl.onSkip = function(ctx)
		ctx.dim(st.dim + 0.15, 0.1)
		ctx.pop(result)
		ctx.sound("reveal", 0.8)
		claim(ctx, opts, 1.5)
	end
	return tl
end

-- Egg hatch: push-in, wobbles that grow, cracks, flash, the pet pops out with rarity glow. results = item or { item, item, … }.
function Cutscene.eggTimeline(results, opts)
	opts = opts or {}
	if results.name or results.rarity then results = { results } end
	local st = styleOf(opts.style)
	local best = results[1]
	for _, r in ipairs(results) do if Cutscene.tier(r) > Cutscene.tier(best) then best = r end end
	local R = Cutscene.rarity(best, st)
	local wob = opts.wobble or 1.9
	local hit = 0.4 + wob + R.pause
	local tl = { kind = "egg", style = opts.style, serverResult = opts.serverResult, skip = opts.skip, autoFinish = false, events = {} }
	local E = tl.events
	local eggs = {}
	local function eggFolder()
		local f = workspace:FindFirstChild("BrickwireEggs")
		if not f then f = new("Folder", { Name = "BrickwireEggs" }, workspace) end
		return f
	end
	table.insert(E, { at = 0, dim = st.dim, time = 0.3, sound = "whoosh", fov = 52, run = function(ctx)
		local cam = ctx.cam
		local base = cam.CFrame
		ctx.hold(base)
		local n = #results
		local spacing = opts.spacing or 4.2
		local folder = eggFolder()
		for i, r in ipairs(results) do
			local offset = (i - (n + 1) / 2) * spacing
			local cf = base * CFrame.new(offset, -0.6, -(opts.distance or 10) - (n > 1 and 2 or 0))
			local egg = new("Part", { Name = "Egg" .. i, Shape = Enum.PartType.Ball, Size = Vector3.new(3, 3, 3), Anchored = true, CanCollide = false, CastShadow = false,
				Color = C(opts.eggColor or "#FFF4DC"), Material = Enum.Material.SmoothPlastic, CFrame = cf }, folder)
			new("SpecialMesh", { MeshType = Enum.MeshType.Sphere, Scale = Vector3.new(1, 1.28, 1) }, egg)
			local spots = new("PointLight", { Color = Cutscene.rarity(r, st).color, Range = 8, Brightness = 0 }, egg)
			eggs[i] = { part = egg, cf = cf, item = r, light = spots }
			ctx.owned["Egg" .. i] = egg
		end
		local start = os.clock()
		ctx.frame(function()
			local t = os.clock() - start
			if t > 0.4 + wob then return true end
			local p = math.clamp((t - 0.4) / wob, 0, 1)
			local amp = math.rad(4 + 22 * p * p)
			for i, e in ipairs(eggs) do
				if e.part.Parent then
					local a = math.sin((t + i * 0.13) * (9 + 12 * p)) * amp * (t > 0.4 and 1 or 0)
					e.part.CFrame = e.cf * CFrame.new(0, math.abs(a) * 0.6, 0) * CFrame.Angles(0, 0, a)
					e.light.Brightness = 3 * p
				end
			end
			return false
		end)
	end })
	for i, at in ipairs({ 0.4 + wob * 0.35, 0.4 + wob * 0.7, 0.4 + wob * 0.92 }) do
		table.insert(E, { at = at, sfx = "hit", volume = 0.4 + 0.15 * i, pitch = 0.9 + 0.1 * i, shake = 0.15 * i, time = 0.15, run = function()
			if i < 2 then return end
			for _, e in ipairs(eggs) do
				if e.part.Parent then
					local col = Cutscene.rarity(e.item, st).color
					for k = 1, i do
						new("Part", { Name = "Crack", Anchored = true, CanCollide = false, Material = Enum.Material.Neon, Color = col, Size = Vector3.new(0.12, 0.9, 0.12),
							CFrame = e.part.CFrame * CFrame.new(rand(-0.7, 0.7), rand(-0.5, 0.9), -1.45) * CFrame.Angles(0, 0, math.rad(rand(-60, 60))) }, e.part)
					end
				end
			end
		end })
	end
	table.insert(E, { at = hit, key = true, flash = "#FFFFFF", time = 0.35, shake = R.shake + 0.3, sound = "reveal", volume = 0.9, run = function(ctx)
		local vfx = lib("BrickwireVFX")
		for i, e in ipairs(eggs) do
			local pos = e.part.CFrame
			local Ri = Cutscene.rarity(e.item, st)
			if e.part.Parent then e.part:Destroy() end
			if vfx then pcall(vfx.play, Ri.tier >= 5 and "level_up" or (Ri.tier >= 3 and "magic_burst" or "confetti"), pos, { color = Ri.color, scale = 0.6 }) end
			local pet
			if opts.petModel then pet = opts.petModel(e.item) end
			local tpl = not pet and RS:FindFirstChild(opts.petsFolder or "Pets")
			if tpl then tpl = tpl:FindFirstChild(tostring(e.item.name)) end
			if tpl then pet = tpl:Clone() end
			if not pet then
				pet = new("Part", { Name = tostring(e.item.name), Shape = Enum.PartType.Ball, Size = Vector3.new(2.4, 2.4, 2.4), Anchored = true, CanCollide = false, Material = Enum.Material.Neon, Color = Ri.color })
			end
			pet.Parent = eggFolder()
			ctx.owned["Pet" .. i] = pet
			local root = pet:IsA("BasePart") and pet or pet:FindFirstChildWhichIsA("BasePart")
			if pet:IsA("Model") then pet:PivotTo(pos) elseif root then root.CFrame = pos end
			if root then
				new("PointLight", { Color = Ri.color, Range = 10 + Ri.tier * 2, Brightness = 2 + Ri.tier * 0.5 }, root)
				local pe = new("ParticleEmitter", { Texture = "rbxasset://textures/particles/sparkles_main.dds", Color = ColorSequence.new(Ri.color), LightEmission = 1,
					Size = NumberSequence.new(0.5, 0), Lifetime = NumberRange.new(0.6, 1.2), Rate = Ri.particles, Speed = NumberRange.new(2, 5), SpreadAngle = Vector2.new(180, 180) }, root)
				pe:Emit(math.min(Ri.particles, 120))
			end
			local spin = 0
			ctx.frame(function(_, dt)
				if not pet.Parent then return true end
				spin += (dt or 1 / 60) * 90
				local cf = pos * CFrame.Angles(0, math.rad(spin), 0)
				if pet:IsA("Model") then pet:PivotTo(cf) elseif root then root.CFrame = cf end
				return false
			end)
			if #results > 1 then
				local bb = new("BillboardGui", { Name = "BrickwirePetTag", Size = UDim2.fromOffset(160, 60), StudsOffset = Vector3.new(0, 2.6, 0), AlwaysOnTop = true, Adornee = root }, ctx.gui.Parent)
				ctx.owned["Tag" .. i] = bb
				text(bb, ctx.style, { text = tostring(e.item.name), size = UDim2.fromScale(1, 0.5), pos = UDim2.fromScale(0.5, 0.25), z = 2, stroke = 2 })
				local rl = text(bb, ctx.style, { text = Ri.name, color = Ri.color, size = UDim2.fromScale(1, 0.45), pos = UDim2.fromScale(0.5, 0.75), z = 2, stroke = 2 })
				if Ri.rainbow then rainbow(rl) end
			end
		end
	end })
	table.insert(E, { at = hit + 0.3, time = 1, run = function(ctx)
		if #results == 1 or R.big then ctx.pop(best, { pos = UDim2.fromScale(0.5, #results > 1 and 0.2 or 0.24) }) end
	end })
	table.insert(E, { at = hit + 1.3, run = function(ctx) claim(ctx, opts, 2) end })
	tl.onSkip = function(ctx)
		for _, e in ipairs(eggs) do if e.part.Parent then e.part:Destroy() end end
		ctx.pop(best)
		ctx.sound("reveal", 0.8)
		claim(ctx, opts, 1.5)
	end
	return tl
end

-- Anime Dice roll: a ticker above the player's head (odds "1 in N", portrait, name) cycles faster→slower and lands on the
-- server's result; Epic+ adds a screen reveal (dim, rays, "LEGENDARY!", shake, flash); Mythic+ fakes an ending first.
function Cutscene.diceTimeline(result, opts)
	opts = opts or {}
	local st = styleOf(opts.style)
	local R = Cutscene.rarity(result, st)
	local pool = fillerPool(opts.pool, result)
	local rollT = opts.rollTime or math.min(0.9 + 0.22 * R.tier, 2.6)
	local fake = R.fakeout and not opts.noFakeout
	local land = rollT + (fake and 0.85 or 0) + R.pause * 0.6
	local tl = { kind = "dice", style = opts.style, serverResult = opts.serverResult, skip = opts.skip, autoFinish = not R.big, events = {} }
	local E = tl.events
	local ui = {}
	local function show(item, ctx)
		local Ri = Cutscene.rarity(item, st)
		ui.odds.Text = item.odds and Cutscene.odds(item.odds) or ""
		ui.name.Text = (item.mutation and (item.mutation .. " ") or "") .. tostring(item.name or "?")
		ui.tile.BackgroundColor3 = Ri.color
		ui.initial.Text = item.icon and "" or string.upper(string.sub(tostring(item.name or "?"), 1, 1))
		ui.icon.Image = item.icon or ""
		ui.rarity.Text = Ri.name
		ui.rarity.TextColor3 = Ri.color
	end
	table.insert(E, { at = 0, sound = "whoosh", volume = 0.4, run = function(ctx)
		local head = character() and character():FindFirstChild("Head")
		local holder
		if head and opts.overhead ~= false then
			holder = new("BillboardGui", { Name = "BrickwireDiceRoll", Size = UDim2.fromOffset(200, 190), StudsOffset = Vector3.new(0, 3.6, 0), AlwaysOnTop = true, Adornee = head, ResetOnSpawn = false }, ctx.gui.Parent)
		else
			holder = new("Frame", { Name = "DiceRoll", BackgroundTransparency = 1, AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.3), Size = UDim2.fromOffset(220, 210), ZIndex = 3 }, ctx.layer)
		end
		ctx.owned.DiceRoll = holder
		ui.root = new("Frame", { Name = "Ticker", BackgroundTransparency = 1, Size = UDim2.fromScale(1, 1), ZIndex = 3 }, holder)
		ui.scale = new("UIScale", { Scale = 1 }, ui.root)
		ui.odds = text(ui.root, st, { name = "Odds", text = "", size = UDim2.fromScale(0.8, 0.16), pos = UDim2.fromScale(0.5, 0.08), rot = st.tilt * 1.4, z = 4, stroke = 2.5 })
		ui.tile = new("Frame", { Name = "Portrait", BackgroundColor3 = C("#D2D2D2"), AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.44), Size = UDim2.fromScale(0.42, 0.44), ZIndex = 3 }, ui.root)
		new("UICorner", { CornerRadius = UDim.new(0.18, 0) }, ui.tile)
		new("UIStroke", { Thickness = 3, Color = C("#000000") }, ui.tile)
		ui.icon = new("ImageLabel", { Name = "Icon", BackgroundTransparency = 1, Image = "", Size = UDim2.fromScale(1, 1), ZIndex = 4 }, ui.tile)
		ui.initial = text(ui.tile, st, { name = "Initial", text = "", size = UDim2.fromScale(0.8, 0.8), z = 4 })
		ui.name = text(ui.root, st, { name = "UnitName", text = "", size = UDim2.fromScale(1, 0.17), pos = UDim2.fromScale(0.5, 0.77), z = 4, stroke = 2.5 })
		ui.rarity = text(ui.root, st, { name = "Rarity", text = "", size = UDim2.fromScale(0.8, 0.13), pos = UDim2.fromScale(0.5, 0.92), z = 4, stroke = 2 })
		local start, nextAt, k = os.clock(), 0, 0
		ctx.frame(function()
			local t = os.clock() - start
			if t >= rollT then return true end
			if t >= nextAt then
				k += 1
				local p = t / rollT
				nextAt = t + 0.05 + 0.3 * p * p -- fast → slow
				show(weightedFiller(pool), ctx)
				ui.scale.Scale = 1.08
				tw(ui.scale, 0.08, { Scale = 1 })
				ctx.sound("tick", 0.3, 0.9 + 0.5 * p)
			end
			return false
		end)
	end })
	if fake then
		-- fake ending: settles on something worse, holds, then the dice "kicks" to the real tier
		table.insert(E, { at = rollT, sfx = "hit", volume = 0.4, run = function(ctx)
			local worse = { name = (pool[1] and pool[1].name) or "Common", rarity = Cutscene.RARITIES[math.max(1, R.tier - 3)] }
			for _, it in ipairs(pool) do if Cutscene.tier(it) <= R.tier - 3 then worse = it break end end
			show(worse, ctx)
		end })
		table.insert(E, { at = rollT + 0.6, key = true, shake = 0.6, time = 0.3, sound = "whoosh", volume = 0.7, flash = R.color, run = function(ctx) ui.scale.Scale = 1.4 end })
	end
	table.insert(E, { at = land, key = true, sound = "reveal", volume = 0.5 + 0.06 * R.tier, shake = R.big and R.shake or nil, time = 0.35, flash = R.big and "#FFFFFF" or nil, run = function(ctx)
		show(result, ctx)
		if R.rainbow then rainbow(ui.rarity) end
		ui.scale.Scale = st.punch and 1.45 or 1.15
		tw(ui.scale, 0.3, { Scale = 1 }, Enum.EasingStyle.Back)
		if R.big then
			ctx.dim(st.dim, 0.2)
			ctx.pop(result, { pos = UDim2.fromScale(0.5, 0.45) })
			if st.speedLines then
				local lines = new("Frame", { Name = "SpeedLines", BackgroundTransparency = 1, Size = UDim2.fromScale(1, 1), ZIndex = 2 }, ctx.layer)
				for i = 1, 18 do
					local a = i / 18 * math.pi * 2
					new("Frame", { Name = "Line" .. i, BackgroundColor3 = C("#FFFFFF"), BackgroundTransparency = 0.35, BorderSizePixel = 0, AnchorPoint = Vector2.new(0.5, 0.5),
						Position = UDim2.fromScale(0.5 + math.cos(a) * 0.42, 0.5 + math.sin(a) * 0.42), Size = UDim2.new(0, 3, 0.35, 0), Rotation = math.deg(a) + 90, ZIndex = 2 }, lines)
				end
				ctx.after(0.5, function() lines:Destroy() end)
			end
		end
	end })
	if R.big then
		table.insert(E, { at = land + 0.4, time = 1.4, sfx = "hit", volume = 0.6 })
		table.insert(E, { at = land + 1.2, run = function(ctx) claim(ctx, opts, opts.auto and 1.2 or 2.2) end })
	else
		table.insert(E, { at = land + 0.2, time = opts.hold or 0.9 })
	end
	tl.onSkip = function(ctx)
		if not ui.root then ctx.finish() return end
		show(result, ctx)
		ctx.sound("reveal", 0.6)
		if R.big then ctx.pop(result) claim(ctx, opts, 1.4) else ctx.after(0.6, ctx.finish) end
	end
	return tl
end

-- Event start for everyone: countdown 3-2-1, letterbox, fly-over the event zone, "EVENT STARTED!" title.
function Cutscene.eventTimeline(opts)
	opts = opts or {}
	local st = styleOf(opts.style)
	local n = opts.countdown or 3
	local step = opts.step or 0.8
	local tl = { kind = "event", style = opts.style, skip = opts.skip, events = {} }
	local E = tl.events
	table.insert(E, { at = 0, letterbox = true, time = 0.4, sound = "whoosh", volume = 0.5 })
	for i = n, 1, -1 do
		local at = (n - i) * step
		table.insert(E, { at = at + 0.05, sfx = "tick", volume = 0.7, pitch = 1 + (n - i) * 0.12, run = function(ctx)
			local l = ctx.text({ name = "Count", text = tostring(i), font = st.titleFont, size = UDim2.fromScale(0.3, 0.3), pos = UDim2.fromScale(0.5, 0.45), color = opts.color or "#FFD24D", stroke = st.stroke + 2 })
			local s = new("UIScale", { Scale = 1.8 }, l)
			tw(s, step * 0.5, { Scale = 1 }, Enum.EasingStyle.Back)
			ctx.after(step * 0.9, function() l:Destroy() end)
		end })
	end
	local fly = n * step
	local zone = opts.zone
	local shots = opts.shots
	if not shots and zone then
		local cm = lib("BrickwireCinema")
		if cm then
			local ok, s = pcall(cm.auto, zone, "epic")
			if ok and type(s) == "table" and #s > 0 then
				shots = {}
				local budget = opts.flyTime or 5
				local m = math.min(#s, 2)
				local sum = 0
				for i = 1, m do sum += s[i].time or 3 end
				for i = 1, m do
					local c = table.clone(s[i])
					c.time = math.max(2, (s[i].time or 3) / sum * budget)
					c.cut = nil
					shots[i] = c
				end
			end
		end
	end
	if shots then table.insert(E, { at = fly, camera = shots, sound = "whoosh", volume = 0.6 }) end
	local cmL = lib("BrickwireCinema")
	local flyLen = shots and (cmL and cmL.duration(shots) or (opts.flyTime or 5)) or 0
	local titleAt = fly + math.max(flyLen - 2.2, 0.2)
	table.insert(E, { at = titleAt, key = true, title = opts.text or "EVENT STARTED!", sub = opts.name, color = opts.color or "#FFD24D", rainbow = opts.rainbow, time = 2.2, flash = "#FFFFFF", shake = 0.5, sound = "reveal", volume = 0.9 })
	if opts.music then table.insert(E, { at = 0, sound = opts.music, music = true, volume = 0.5, fadeIn = 0.8, fadeOut = 1, time = titleAt + 2.4 }) end
	table.insert(E, { at = titleAt + 2.3, letterbox = false, time = 0.4, fire = opts.fire or "EventStarted" })
	return tl
end

-- Back-story: 3–6 frames { shots = {…} | shot = {…}, text =, speaker =, time = } with dips to black, typed subtitles, music.
function Cutscene.storyTimeline(frames, opts)
	opts = opts or {}
	local tl = { kind = "story", style = opts.style, skip = opts.skip, letterbox = true, events = {} }
	local E = tl.events
	local at = 0
	for i, f in ipairs(frames) do
		local d = f.time or math.max(3.5, 1.2 + #(f.text or "") / 16)
		local shots = f.shots or (f.shot and { f.shot }) or nil
		if shots then
			local cm = lib("BrickwireCinema")
			local total = cm and cm.duration(shots) or d
			if total < d then shots = table.clone(shots) shots[#shots] = table.clone(shots[#shots]) shots[#shots].time = (shots[#shots].time or 3) + (d - total) end
		end
		table.insert(E, { at = at, camera = shots, run = function(ctx)
			if i > 1 then ctx.flash("#000000", 0.5) end
		end })
		if f.text then table.insert(E, { at = at + 0.3, say = f.text, speaker = f.speaker, time = d - 0.4 }) end
		if f.sound then table.insert(E, { at = at + 0.2, sound = f.sound }) end
		at += d
	end
	local music = opts.music or (Cutscene.SOUNDS.music ~= "" and Cutscene.SOUNDS.music) or nil
	table.insert(E, 1, { at = 0, sound = music or "whoosh", music = music ~= nil, volume = music and 0.45 or 0.5, fadeIn = 1.5, fadeOut = 1.2, time = at })
	if opts.title then table.insert(E, { at = math.max(at - 2.4, 0), title = opts.title, sub = opts.sub, time = 2.2, sound = "reveal", key = true }) end
	table.insert(E, { at = at, run = function(ctx) ctx.flash("#000000", 0.6) end })
	return tl
end

function Cutscene.caseOpen(result, opts) return Cutscene.play(Cutscene.caseTimeline(result, opts), opts) end
function Cutscene.eggHatch(results, opts) return Cutscene.play(Cutscene.eggTimeline(results, opts), opts) end
function Cutscene.diceRoll(result, opts) return Cutscene.play(Cutscene.diceTimeline(result, opts), opts) end
function Cutscene.eventStart(opts) return Cutscene.play(Cutscene.eventTimeline(opts), opts) end
function Cutscene.story(frames, opts) return Cutscene.play(Cutscene.storyTimeline(frames, opts), opts) end

-- Build a ready scene's timeline from network data (used by run/listen and by Cutscene.check / BW.cutsceneCheck).
function Cutscene.build(scene, data)
	data = data or {}
	local o = table.clone(data.opts or {})
	o.style = o.style or data.style
	o.pool = o.pool or data.pool
	o.serverResult = data.__server == true or o.serverResult
	if scene == "case" then return Cutscene.caseTimeline(data.result, o)
	elseif scene == "egg" then return Cutscene.eggTimeline(data.results or data.result, o)
	elseif scene == "dice" then return Cutscene.diceTimeline(data.result, o)
	elseif scene == "event" then o.zone = o.zone or data.zone o.name = o.name or data.name o.text = o.text or data.text return Cutscene.eventTimeline(o)
	elseif scene == "story" then o.title = o.title or data.title return Cutscene.storyTimeline(data.frames or {}, o)
	elseif scene == "timeline" then return data.timeline or data
	end
	error("BrickwireCutscene: unknown scene '" .. tostring(scene) .. "' (case, egg, dice, event, story, timeline)", 2)
end
function Cutscene.run(scene, data)
	local tl = Cutscene.build(scene, data)
	return Cutscene.play(tl, data and data.opts)
end

-- ---------------------------------------------------------------- networking
function Cutscene.remote()
	local r = RS:FindFirstChild("BrickwireCutsceneRemote")
	if r then return r end
	if RunService:IsClient() then return RS:WaitForChild("BrickwireCutsceneRemote", 15) end
	r = Instance.new("RemoteEvent")
	r.Name = "BrickwireCutsceneRemote"
	r.Parent = RS
	return r
end
-- SERVER: Cutscene.show(player | {players} | "all", scene, data). data.result must come from Cutscene.roll (server).
function Cutscene.show(who, scene, data)
	data = data or {}
	if RunService:IsClient() then return Cutscene.run(scene, data) end
	data.__server = true
	local r = Cutscene.remote()
	if who == nil or who == "all" then r:FireAllClients(scene, data)
	elseif type(who) == "table" and not (typeof(who) == "Instance") then for _, p in ipairs(who) do r:FireClient(p, scene, data) end
	else r:FireClient(who, scene, data) end
end
-- CLIENT: plays every scene the server sends. handlers[scene] = fn(data) overrides a scene. Returns the connection.
function Cutscene.listen(handlers)
	local r = Cutscene.remote()
	if not r then warn("BrickwireCutscene: no BrickwireCutsceneRemote — require the module on the server first") return nil end
	return r.OnClientEvent:Connect(function(scene, data)
		if handlers and handlers[scene] then handlers[scene](data) return end
		local ok, err = pcall(Cutscene.run, scene, data)
		if not ok then warn("BrickwireCutscene " .. tostring(scene) .. ": " .. tostring(err)) end
	end)
end
-- CLIENT → SERVER request (e.g. the ROLL button): Cutscene.request("roll", {dice = "Fire"})
function Cutscene.request(action, data)
	local r = Cutscene.remote()
	if r then r:FireServer(action, data) end
end
return Cutscene
