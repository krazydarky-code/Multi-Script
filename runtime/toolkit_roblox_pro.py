# SPDX-License-Identifier: GPL-3.0-or-later
"""Roblox Studio "pro" tools for engine_toolkit: VFX, lighting looks, UI kits + audits, tween/keyframe animation,
level blockout, terrain, scatter, paths, buildings, model utilities, constraints, gameplay scripts and optimisation.
Each compiles to one Luau program run through the official Studio MCP `execute_luau` (plain Luau 5.1-compatible
syntax only, so the generated source also loads in a stock Lua VM for tests)."""
import json
import math
import re
import textwrap

from engine_toolkit import tool, as_list, as_dict, vec3, num, boolean, ToolkitError
from toolkit_roblox import _exec, _paths, PATH, PATHS, VEC

RB = "roblox"


def _norm(args, **defaults):
    a = dict(args)
    for k, v in defaults.items():
        if a.get(k) is None:
            a[k] = v
    return a


def _x(lib, body):
    return textwrap.dedent(lib).strip("\n") + "\n" + textwrap.dedent(body).strip("\n")


_LIB_MK = '''
local function mk(class, props, parent)
    local i = Instance.new(class)
    for k, v in pairs(props or {}) do i[k] = v end
    if parent then i.Parent = parent end
    return i
end
local function hex(h) return Color3.fromHex(h) end
local function enumOf(kind, name, fallback)
    local ok, v = pcall(function() return Enum[kind][name] end)
    if ok and v then return v end
    return Enum[kind][fallback]
end
'''

# ─────────────────────────────── VFX / look ───────────────────────────────
FX = ["fire", "smoke", "sparks", "magic", "healing", "explosion", "rain", "snow", "dust", "portal", "hit_impact", "confetti", "bubbles", "steam"]


@tool(RB, "ms_roblox_particle_effect",
      "Create a tuned ParticleEmitter effect from a preset (fire, smoke, sparks, magic, healing, explosion, rain, snow, dust, portal, hit_impact, confetti, bubbles, steam) "
      "on an existing part/attachment or on a new anchored invisible emitter part. Sets rate, lifetime, size/transparency/colour curves, speed, spread, acceleration, light emission "
      "and an optional PointLight. Colour, intensity and size are adjustable; re-running replaces the previous effect of the same name.",
      {"preset": {"type": "string", "enum": FX}, "target": {"type": "string", "description": "Path of a BasePart or Attachment to attach to. Omit to create an emitter part."},
       "position": VEC, "name": {"type": "string"}, "color": {"type": ["string", "array"]}, "color2": {"type": ["string", "array"]}, "intensity": {"type": "number", "description": "Rate multiplier (default 1)."},
       "size_scale": {"type": "number"}, "texture": {"type": "string", "description": "Override texture asset id."}, "light": {"type": "boolean"}, "enabled": {"type": "boolean"},
       "parent": {"type": "string", "description": "Where the new emitter part goes (default Workspace)."}},
      ["preset"], writes=True)
def particle_effect(args, ctx):
    a = _norm(args, intensity=1.0, size_scale=1.0, enabled=True, parent="Workspace")
    a["preset"] = str(a.get("preset") or "").lower()
    if a["preset"] not in FX:
        raise ToolkitError(f"unknown preset '{a['preset']}'", "Use one of: " + ", ".join(FX))
    return _exec(ctx, a, _x(_LIB_MK, '''
        local P = A.preset
        -- rate, lifetime{min,max}, speed{min,max}, size{start,mid,end}, spread, accel(y), c1, c2, lightEmission, texture, light, rotSpeed, drag
        local S = {
            fire      = {rate = 60, life = {0.5, 1.1}, speed = {2, 5}, size = {1.6, 2.2, 0}, spread = 15, accel = 6, c1 = "#ffd23f", c2 = "#ff3d00", emission = 1, tex = "rbxasset://textures/particles/fire_main.dds", light = true, rot = 90},
            smoke     = {rate = 18, life = {2, 4}, speed = {2, 4}, size = {1.5, 5, 8}, spread = 20, accel = 2, c1 = "#9a9a9a", c2 = "#3a3a3a", emission = 0, tex = "rbxasset://textures/particles/smoke_main.dds", rot = 40, trans = {0.5, 0.7, 1}},
            sparks    = {rate = 45, life = {0.4, 1.0}, speed = {14, 28}, size = {0.35, 0.25, 0}, spread = 60, accel = -45, c1 = "#fff2a8", c2 = "#ff8a00", emission = 1, tex = "rbxasset://textures/particles/sparkles_main.dds", rot = 0, light = true},
            magic     = {rate = 35, life = {1, 2}, speed = {1, 4}, size = {0.6, 0.9, 0}, spread = 180, accel = 2, c1 = "#a66bff", c2 = "#38d9ff", emission = 1, tex = "rbxasset://textures/particles/sparkles_main.dds", rot = 120, light = true},
            healing   = {rate = 22, life = {1.2, 2}, speed = {2, 4}, size = {0.7, 0.8, 0}, spread = 25, accel = 3, c1 = "#7dff9a", c2 = "#d4ffe0", emission = 1, tex = "rbxasset://textures/particles/sparkles_main.dds", rot = 60},
            explosion = {rate = 300, life = {0.4, 1.0}, speed = {25, 60}, size = {3, 5, 0}, spread = 180, accel = 0, c1 = "#ffe08a", c2 = "#ff3b00", emission = 1, tex = "rbxasset://textures/particles/fire_main.dds", burst = 120, light = true, drag = 2},
            rain      = {rate = 250, life = {0.8, 1.2}, speed = {80, 100}, size = {0.15, 0.15, 0.15}, spread = 2, accel = 0, c1 = "#bcd7ff", c2 = "#bcd7ff", emission = 0.2, tex = "rbxasset://textures/particles/sparkles_main.dds", area = true, down = true, trans = {0.2, 0.3, 0.6}},
            snow      = {rate = 120, life = {5, 8}, speed = {2, 6}, size = {0.25, 0.3, 0.2}, spread = 40, accel = 0, c1 = "#ffffff", c2 = "#dfe9ff", emission = 0.3, tex = "rbxasset://textures/particles/sparkles_main.dds", area = true, down = true, rot = 40, trans = {0.1, 0.1, 0.5}},
            dust      = {rate = 14, life = {3, 6}, speed = {0.2, 1}, size = {0.5, 1, 0.5}, spread = 180, accel = 0, c1 = "#cbb892", c2 = "#a39172", emission = 0, tex = "rbxasset://textures/particles/smoke_main.dds", area = true, trans = {0.85, 0.8, 1}},
            portal    = {rate = 80, life = {0.8, 1.4}, speed = {1, 3}, size = {0.6, 0.5, 0}, spread = 180, accel = 0, c1 = "#ae6bff", c2 = "#3ac6ff", emission = 1, tex = "rbxasset://textures/particles/sparkles_main.dds", rot = 240, light = true, ring = true},
            hit_impact= {rate = 0, life = {0.2, 0.5}, speed = {12, 30}, size = {1.2, 0.8, 0}, spread = 180, accel = 0, c1 = "#ffffff", c2 = "#ffb347", emission = 1, tex = "rbxasset://textures/particles/sparkles_main.dds", burst = 25, drag = 6},
            confetti  = {rate = 0, life = {2, 3}, speed = {20, 45}, size = {0.35, 0.35, 0.35}, spread = 70, accel = -30, c1 = "#ff4d6d", c2 = "#4dd2ff", emission = 0, tex = "rbxasset://textures/particles/sparkles_main.dds", burst = 120, rot = 360, drag = 1.5, multi = true},
            bubbles   = {rate = 12, life = {2, 4}, speed = {1, 3}, size = {0.4, 0.6, 0.6}, spread = 25, accel = 3, c1 = "#cfeeff", c2 = "#ffffff", emission = 0.4, tex = "rbxasset://textures/particles/sparkles_main.dds", trans = {0.5, 0.5, 1}},
            steam     = {rate = 25, life = {1, 2}, speed = {4, 8}, size = {1, 3, 5}, spread = 12, accel = 3, c1 = "#ffffff", c2 = "#d8d8d8", emission = 0.1, tex = "rbxasset://textures/particles/smoke_main.dds", trans = {0.6, 0.8, 1}},
        }
        local s = S[P]
        local parent
        local made = {}
        local name = A.name or ("MS_FX_" .. P)
        local c1 = A.color and col3(A.color) or hex(s.c1)
        local c2 = A.color2 and col3(A.color2) or (A.color and col3(A.color) or hex(s.c2))
        local holder
        if A.target then
            local t = resolve(A.target)
            if t:IsA("Attachment") then holder = t
            elseif t:IsA("BasePart") then
                holder = t:FindFirstChild(name .. "_Att")
                if holder == nil then holder = mk("Attachment", {Name = name .. "_Att"}, t) end
            else error("target must be a BasePart or Attachment") end
        else
            local par = resolve(A.parent or "Workspace")
            local old = par:FindFirstChild(name)
            if old then old:Destroy() end
            local part = mk("Part", {Name = name, Anchored = true, CanCollide = false, CanQuery = false, CanTouch = false, Transparency = 1, Size = Vector3.new(s.area and 40 or 1, 1, s.area and 40 or 1)}, par)
            local pos = A.position or {0, 5, 0}
            if s.area then pos = {pos[1], pos[2] + 30, pos[3]} end
            part.Position = vec3(pos)
            holder = mk("Attachment", {Name = name .. "_Att"}, part)
            table.insert(made, part:GetFullName())
        end
        local old = holder:FindFirstChild(name)
        if old then old:Destroy() end
        local ps = A.intensity or 1
        local e = mk("ParticleEmitter", {Name = name}, holder)
        e.Texture = A.texture or s.tex
        e.Rate = s.rate * ps
        e.Lifetime = NumberRange.new(s.life[1], s.life[2])
        e.Speed = NumberRange.new(s.speed[1], s.speed[2])
        e.SpreadAngle = Vector2.new(s.spread, s.spread)
        e.Acceleration = Vector3.new(0, s.accel, 0)
        e.LightEmission = s.emission
        e.LightInfluence = 0
        e.Rotation = NumberRange.new(0, 360)
        e.RotSpeed = NumberRange.new(-(s.rot or 0), s.rot or 0)
        e.Drag = s.drag or 0
        local sz = A.size_scale or 1
        e.Size = NumberSequence.new({NumberSequenceKeypoint.new(0, s.size[1] * sz), NumberSequenceKeypoint.new(0.4, s.size[2] * sz), NumberSequenceKeypoint.new(1, s.size[3] * sz)})
        local tr = s.trans or {0, 0.2, 1}
        e.Transparency = NumberSequence.new({NumberSequenceKeypoint.new(0, tr[1]), NumberSequenceKeypoint.new(0.5, tr[2]), NumberSequenceKeypoint.new(1, tr[3])})
        if s.multi then
            e.Color = ColorSequence.new({ColorSequenceKeypoint.new(0, hex("#ff4d6d")), ColorSequenceKeypoint.new(0.33, hex("#ffd23f")), ColorSequenceKeypoint.new(0.66, hex("#4dd2ff")), ColorSequenceKeypoint.new(1, hex("#8dff6a"))})
        else
            e.Color = ColorSequence.new(c1, c2)
        end
        if s.down then e.EmissionDirection = Enum.NormalId.Bottom end
        if s.ring then e.Shape = Enum.ParticleEmitterShape.Disc; e.ShapeInOut = Enum.ParticleEmitterShapeInOut.Outward end
        e.Enabled = A.enabled ~= false
        if s.burst then
            e.Enabled = false
            e:SetAttribute("BurstCount", math.floor(s.burst * ps))
            if A.enabled ~= false then pcall(function() e:Emit(math.floor(s.burst * ps)) end) end
        end
        table.insert(made, e:GetFullName())
        local wantLight = A.light
        if wantLight == nil then wantLight = s.light end
        if wantLight then
            local lt = holder:FindFirstChild(name .. "_Light")
            if lt then lt:Destroy() end
            lt = mk("PointLight", {Name = name .. "_Light", Color = c1, Range = 14 * sz, Brightness = 1.5 * math.min(ps, 3)}, holder.Parent and holder.Parent:IsA("BasePart") and holder.Parent or holder)
            table.insert(made, lt:GetFullName())
        end
        R.preset = P
        R.created = made
        R.emitter = {rate = e.Rate, lifetime = {s.life[1], s.life[2]}, burst = s.burst, enabled = e.Enabled}
        waypoint("particle effect " .. P)
    '''), "particle effect " + a["preset"])


LOOKS = ["cinematic", "bright_cartoon", "horror", "sunset", "neon_night", "clean_day", "foggy_morning", "desert_noon", "underwater", "cyberpunk", "winter"]


@tool(RB, "ms_roblox_post_processing",
      "Apply a complete lighting + atmosphere + post-processing LOOK in one call: cinematic, bright_cartoon, horror, sunset, neon_night, clean_day, foggy_morning, desert_noon, underwater, "
      "cyberpunk, winter. Sets Lighting (time, brightness, ambient, shadows, exposure), Atmosphere, Sky, Bloom, ColorCorrection, DepthOfField, SunRays and Blur as named MS_* effects "
      "(re-running replaces them). `strength` scales the effects 0-2; `clear` removes every MS_* effect instead.",
      {"look": {"type": "string", "enum": LOOKS}, "strength": {"type": "number", "minimum": 0, "maximum": 2}, "clock_time": {"type": "number", "minimum": 0, "maximum": 24},
       "clear": {"type": "boolean"}, "keep_sky": {"type": "boolean"}}, ["look"], writes=True)
def post_processing(args, ctx):
    a = _norm(args, strength=1.0)
    a["look"] = str(a.get("look") or "").lower()
    if not a.get("clear") and a["look"] not in LOOKS:
        raise ToolkitError(f"unknown look '{a['look']}'", "Use one of: " + ", ".join(LOOKS))
    return _exec(ctx, a, _x(_LIB_MK, '''
        local L = game:GetService("Lighting")
        local function wipe()
            for _, c in ipairs(L:GetChildren()) do
                if string.sub(c.Name, 1, 3) == "MS_" then c:Destroy() end
            end
        end
        wipe()
        if A.clear then R.cleared = true; return end
        -- clock, brightness, exposure, ambient, outdoor, topShift, atmo{density, offset, color, decay, glare, haze}, bloom{int, size, thr}, cc{bright, contrast, sat, tint}, dof{far, focus, radius, dist}, rays, blur, stars, shadows
        local LK = {
            cinematic      = {clock = 17.2, bright = 2.4, exp = -0.1, amb = "#3a3f4d", out = "#5a5f70", top = "#ffd9a8", atmo = {0.32, 0.1, "#e8c9a4", "#8a6f56", 0.4, 1.4}, bloom = {0.6, 28, 0.9}, cc = {0, 0.18, -0.05, "#fff1de"}, dof = {0.2, 60, 0.6, 120}, rays = 0.12},
            bright_cartoon = {clock = 13, bright = 3, exp = 0.2, amb = "#8fa4c8", out = "#a9bfe0", top = "#ffffff", atmo = {0.18, 0, "#cfe7ff", "#ffffff", 0, 0.2}, bloom = {0.25, 20, 1.1}, cc = {0.02, 0.1, 0.3, "#ffffff"}, rays = 0.06},
            horror         = {clock = 0.2, bright = 0.2, exp = -0.6, amb = "#0a0d12", out = "#10141c", top = "#2b3a4a", atmo = {0.55, 0, "#1b2230", "#0c1018", 0, 2.2}, bloom = {0.15, 18, 1.3}, cc = {-0.05, 0.3, -0.45, "#b6c6d8"}, dof = {0.35, 30, 0.5, 80}, blur = 2, stars = 4000},
            sunset         = {clock = 18.3, bright = 2.2, exp = 0, amb = "#5b4a5c", out = "#8c6a63", top = "#ffb066", atmo = {0.35, 0.2, "#ffb07a", "#9a4a2a", 0.8, 1}, bloom = {0.5, 30, 0.95}, cc = {0, 0.12, 0.15, "#ffe0c4"}, rays = 0.25},
            neon_night     = {clock = 0, bright = 0.5, exp = 0.2, amb = "#1a1230", out = "#271a4a", top = "#ff2bd6", atmo = {0.4, 0, "#28104a", "#120830", 0, 1.6}, bloom = {1.2, 40, 0.6}, cc = {0, 0.3, 0.35, "#e0d0ff"}, stars = 3000},
            clean_day      = {clock = 14, bright = 2.6, exp = 0, amb = "#7a8696", out = "#9aa8bb", top = "#fff8ec", atmo = {0.28, 0, "#c7d9f0", "#e6edf7", 0.1, 0.3}, bloom = {0.2, 24, 1}, cc = {0, 0.05, 0.08, "#ffffff"}, rays = 0.04},
            foggy_morning  = {clock = 6.6, bright = 1.5, exp = -0.1, amb = "#6f7a86", out = "#8e99a5", top = "#fff0d8", atmo = {0.62, 0.3, "#c9d2d9", "#b9c3cb", 0, 3.2}, bloom = {0.3, 26, 1}, cc = {0, -0.05, -0.15, "#f0f4f8"}, rays = 0.1},
            desert_noon    = {clock = 12.2, bright = 3.2, exp = 0.15, amb = "#a58f70", out = "#c4aa86", top = "#fff4d6", atmo = {0.2, 0.4, "#e9d3a8", "#ffe9bd", 0.5, 0.8}, bloom = {0.35, 24, 0.9}, cc = {0.03, 0.2, 0.1, "#fff0d0"}, rays = 0.1},
            underwater     = {clock = 12, bright = 1.8, exp = -0.2, amb = "#1d4f66", out = "#2a6a85", top = "#7fe0ff", atmo = {0.75, 0, "#1a6a88", "#0a3550", 0, 2.5}, bloom = {0.4, 24, 0.9}, cc = {0, 0.1, 0.1, "#b8f0ff"}, dof = {0.5, 20, 0.6, 60}, blur = 4},
            cyberpunk      = {clock = 21.8, bright = 1.2, exp = 0.1, amb = "#251a3d", out = "#38245c", top = "#00f0ff", atmo = {0.45, 0, "#3a1a66", "#1a0a33", 0.3, 1.8}, bloom = {1, 36, 0.7}, cc = {0, 0.35, 0.4, "#e8d0ff"}, dof = {0.15, 90, 0.5, 200}, stars = 1500},
            winter         = {clock = 11, bright = 2.5, exp = 0.1, amb = "#8a9cb8", out = "#a8bad4", top = "#eaf4ff", atmo = {0.4, 0.2, "#dbe8f7", "#ffffff", 0, 0.6}, bloom = {0.3, 24, 1}, cc = {0.02, 0.05, -0.1, "#e8f2ff"}, rays = 0.05},
        }
        local k = LK[A.look]
        local st = A.strength or 1
        L.ClockTime = A.clock_time or k.clock
        L.Brightness = k.bright
        L.ExposureCompensation = k.exp
        L.Ambient = hex(k.amb)
        L.OutdoorAmbient = hex(k.out)
        L.ColorShift_Top = hex(k.top)
        L.GlobalShadows = true
        L.EnvironmentDiffuseScale = 1
        L.EnvironmentSpecularScale = 1
        local a = k.atmo
        mk("Atmosphere", {Name = "MS_Atmosphere", Density = a[1] * st, Offset = a[2], Color = hex(a[3]), Decay = hex(a[4]), Glare = a[5], Haze = a[6]}, L)
        local b = k.bloom
        mk("BloomEffect", {Name = "MS_Bloom", Intensity = b[1] * st, Size = b[2], Threshold = b[3]}, L)
        local c = k.cc
        mk("ColorCorrectionEffect", {Name = "MS_ColorCorrection", Brightness = c[1] * st, Contrast = c[2] * st, Saturation = c[3] * st, TintColor = hex(c[4])}, L)
        if k.dof then
            mk("DepthOfFieldEffect", {Name = "MS_DepthOfField", FarIntensity = k.dof[1] * st, FocusDistance = k.dof[2], InFocusRadius = k.dof[3] * 20, NearIntensity = 0}, L)
        end
        if k.rays then mk("SunRaysEffect", {Name = "MS_SunRays", Intensity = k.rays * st, Spread = 0.6}, L) end
        if k.blur then mk("BlurEffect", {Name = "MS_Blur", Size = k.blur * st}, L) end
        if not A.keep_sky then
            local sky = L:FindFirstChildOfClass("Sky")
            if sky == nil then sky = mk("Sky", {Name = "MS_Sky"}, L) end
            sky.StarCount = k.stars or 3000
            sky.CelestialBodiesShown = true
        end
        R.look = A.look
        R.lighting = {clock = L.ClockTime, brightness = L.Brightness, exposure = L.ExposureCompensation}
        local names = {}
        for _, c2 in ipairs(L:GetChildren()) do if string.sub(c2.Name, 1, 3) == "MS_" then table.insert(names, c2.Name) end end
        R.effects = names
        waypoint("look " .. A.look)
    '''), "post processing " + a["look"])


THEMES = {
    "classic": {"bg": "#202020", "panel": "#3a3a3a", "panel2": "#505050", "text": "#ffffff", "subtext": "#c8c8c8", "accent": "#00a2ff", "accent_text": "#ffffff", "stroke": "#000000", "thickness": 2,
                "corner": 4, "font": "SourceSans", "font_bold": "SourceSansBold", "panel_alpha": 0.1, "good": "#4cc44c", "bad": "#d43b3b", "warn": "#f0b429"},
    "modern_dark": {"bg": "#101216", "panel": "#1b1d23", "panel2": "#262a33", "text": "#f2f4f8", "subtext": "#9aa3b2", "accent": "#5b8cff", "accent_text": "#ffffff", "stroke": "#343a46", "thickness": 1,
                    "corner": 12, "font": "GothamMedium", "font_bold": "GothamBold", "panel_alpha": 0.02, "good": "#37d67a", "bad": "#ff5c5c", "warn": "#ffb020"},
    "glass": {"bg": "#0b0f1a", "panel": "#ffffff", "panel2": "#ffffff", "text": "#ffffff", "subtext": "#dfe6f5", "accent": "#7aa2ff", "accent_text": "#0b1020", "stroke": "#ffffff", "thickness": 1,
              "corner": 16, "font": "Gotham", "font_bold": "GothamBold", "panel_alpha": 0.82, "good": "#5ff0a0", "bad": "#ff7b7b", "warn": "#ffd166"},
    "neon": {"bg": "#07070f", "panel": "#0f0f1e", "panel2": "#171730", "text": "#e8f6ff", "subtext": "#8aa0c8", "accent": "#00f0ff", "accent_text": "#001418", "stroke": "#00f0ff", "thickness": 2,
             "corner": 6, "font": "GothamMedium", "font_bold": "GothamBlack", "panel_alpha": 0.05, "good": "#39ff88", "bad": "#ff2bd6", "warn": "#fff200"},
    "pastel": {"bg": "#fdf2f8", "panel": "#fff7f0", "panel2": "#ffe9f1", "text": "#5a4a52", "subtext": "#9b8590", "accent": "#ff9ecb", "accent_text": "#ffffff", "stroke": "#ffcfe2", "thickness": 2,
               "corner": 18, "font": "FredokaOne", "font_bold": "FredokaOne", "panel_alpha": 0, "good": "#7ed9a6", "bad": "#ff8a9b", "warn": "#ffcf70"},
    "retro_terminal": {"bg": "#000000", "panel": "#06140a", "panel2": "#0b2412", "text": "#5cff8a", "subtext": "#2fb85a", "accent": "#5cff8a", "accent_text": "#000000", "stroke": "#2fb85a", "thickness": 2,
                       "corner": 0, "font": "Code", "font_bold": "Code", "panel_alpha": 0.05, "good": "#5cff8a", "bad": "#ff5c5c", "warn": "#fff200"},
}
UI_COMPONENTS = ["main_menu", "hud", "shop", "inventory", "dialog", "toast", "settings", "leaderboard", "loading"]

_UI_BEHAVIOR = '''local TweenService = game:GetService("TweenService")
local gui = script.Parent
local info = TweenInfo.new(0.12, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)

local function hook(btn)
	local scale = btn:FindFirstChildOfClass("UIScale")
	if not scale then
		scale = Instance.new("UIScale")
		scale.Parent = btn
	end
	btn.MouseEnter:Connect(function()
		TweenService:Create(scale, info, {Scale = 1.04}):Play()
	end)
	btn.MouseLeave:Connect(function()
		TweenService:Create(scale, info, {Scale = 1}):Play()
	end)
	btn.MouseButton1Down:Connect(function()
		TweenService:Create(scale, info, {Scale = 0.96}):Play()
	end)
	btn.MouseButton1Up:Connect(function()
		TweenService:Create(scale, info, {Scale = 1.04}):Play()
	end)
	btn.Activated:Connect(function()
		local opens = btn:GetAttribute("Opens")
		local closes = btn:GetAttribute("Closes")
		if opens then
			local target = gui:FindFirstChild(opens)
			if target then target.Visible = not target.Visible end
		end
		if closes then
			local target = gui:FindFirstChild(closes)
			if target then target.Visible = false end
		end
	end)
end

for _, d in ipairs(gui:GetDescendants()) do
	if d:IsA("TextButton") then hook(d) end
end
gui.DescendantAdded:Connect(function(d)
	if d:IsA("TextButton") then hook(d) end
end)
'''


@tool(RB, "ms_roblox_ui_kit",
      "Generate a themed, responsive ScreenGui kit (UICorner/UIStroke/UIGradient, UIListLayout, UIScale, mobile-safe): main_menu, hud, shop, inventory, dialog, toast, settings, leaderboard, loading. Themes: classic, modern_dark, glass, neon, pastel, retro_terminal. Optional LocalScript wires hover/click tweens and open/close.",
      {"components": {"type": "array", "items": {"type": "string", "enum": UI_COMPONENTS}}, "theme": {"type": "string", "enum": sorted(THEMES)}, "name": {"type": "string", "description": "ScreenGui name (default MS_UI)."},
       "title": {"type": "string"}, "buttons": {"type": "array", "items": {"type": "string"}, "description": "Main-menu button labels."}, "items": {"type": "integer", "minimum": 1, "maximum": 60, "description": "Shop/inventory/leaderboard entries."},
       "accent": {"type": ["string", "array"], "description": "Override the theme accent colour."}, "parent": {"type": "string", "description": "Default StarterGui."}, "behavior_script": {"type": "boolean"},
       "show_all": {"type": "boolean", "description": "Make popups visible (default false)."}, "replace": {"type": "boolean", "description": "Replace an existing ScreenGui with the same name (default true)."}},
      ["components"], writes=True)
def ui_kit(args, ctx):
    a = _norm(args, theme="modern_dark", name="MS_UI", title="My Game", items=12, parent="StarterGui", behavior_script=True, show_all=False, replace=True)
    th = str(a["theme"]).lower()
    if th not in THEMES:
        raise ToolkitError(f"unknown theme '{th}'", "Use: " + ", ".join(sorted(THEMES)))
    comps = [str(c).lower() for c in as_list(a.get("components"))]
    bad = [c for c in comps if c not in UI_COMPONENTS]
    if bad or not comps:
        raise ToolkitError(f"unknown or missing components {bad}", "Use: " + ", ".join(UI_COMPONENTS))
    a["components"] = list(dict.fromkeys(comps))
    a["_theme"] = dict(THEMES[th])
    if a.get("accent") is not None:
        from engine_toolkit import color4
        c = color4(a["accent"])
        a["_theme"]["accent"] = "#%02x%02x%02x" % tuple(int(round(max(0, min(1, x)) * 255)) for x in c[:3])
    a["buttons"] = [str(b) for b in as_list(a.get("buttons"))] or ["Play", "Shop", "Settings"]
    a["_behavior"] = _UI_BEHAVIOR
    a["items"] = num(a.get("items"), 12, 1, 60, True)
    return _exec(ctx, a, _x(_LIB_MK, '''
        local T = A._theme
        local function font(bold) return enumOf("Font", bold and T.font_bold or T.font, "SourceSans") end
        local parent = resolve(A.parent or "StarterGui")
        if A.replace ~= false then
            local old = parent:FindFirstChild(A.name)
            if old then old:Destroy() end
        end
        local sg = mk("ScreenGui", {Name = A.name, ResetOnSpawn = false, IgnoreGuiInset = true, ZIndexBehavior = Enum.ZIndexBehavior.Sibling}, parent)
        local function skin(frame, o)
            o = o or {}
            mk("UICorner", {CornerRadius = UDim.new(0, o.corner or T.corner)}, frame)
            if (o.stroke ~= false) and T.thickness > 0 then
                mk("UIStroke", {Color = hex(o.strokeColor or T.stroke), Thickness = o.thickness or T.thickness, Transparency = (T.panel_alpha > 0.5) and 0.55 or 0, ApplyStrokeMode = Enum.ApplyStrokeMode.Border}, frame)
            end
            return frame
        end
        local function panel(parentI, props, o)
            local f = mk("Frame", {BackgroundColor3 = hex(o and o.color or T.panel), BackgroundTransparency = (o and o.alpha) or T.panel_alpha, BorderSizePixel = 0}, parentI)
            for k, v in pairs(props or {}) do f[k] = v end
            return skin(f, o)
        end
        local function label(parentI, text, size, o)
            o = o or {}
            local l = mk("TextLabel", {BackgroundTransparency = 1, Text = text, TextColor3 = hex(o.color or T.text), TextSize = size or 18, Font = font(o.bold), TextXAlignment = o.align or Enum.TextXAlignment.Left,
                TextYAlignment = Enum.TextYAlignment.Center, Size = o.size or UDim2.new(1, 0, 0, (size or 18) + 6), Position = o.pos or UDim2.new(0, 0, 0, 0), TextWrapped = o.wrap or false, RichText = false}, parentI)
            if o.name then l.Name = o.name end
            return l
        end
        local function button(parentI, text, o)
            o = o or {}
            local b = mk("TextButton", {Name = o.name or ("Btn_" .. string.gsub(text, "%W", "")), Text = text, AutoButtonColor = false, Font = font(true), TextSize = o.textSize or 20,
                TextColor3 = hex(o.primary and T.accent_text or T.text), BackgroundColor3 = hex(o.primary and T.accent or T.panel2), BackgroundTransparency = o.primary and 0 or math.min(T.panel_alpha, 0.5),
                Size = o.size or UDim2.new(1, 0, 0, 44), BorderSizePixel = 0, LayoutOrder = o.order or 0}, parentI)
            skin(b, {corner = math.max(0, T.corner - 2), strokeColor = o.primary and T.accent or T.stroke})
            return b
        end
        local function list(parentI, pad, dir, align)
            return mk("UIListLayout", {Padding = UDim.new(0, pad or 8), FillDirection = dir or Enum.FillDirection.Vertical, SortOrder = Enum.SortOrder.LayoutOrder,
                HorizontalAlignment = align or Enum.HorizontalAlignment.Center}, parentI)
        end
        local function pad(parentI, px) return mk("UIPadding", {PaddingTop = UDim.new(0, px), PaddingBottom = UDim.new(0, px), PaddingLeft = UDim.new(0, px), PaddingRight = UDim.new(0, px)}, parentI) end
        local function constrain(f, maxW, maxH) mk("UISizeConstraint", {MaxSize = Vector2.new(maxW, maxH), MinSize = Vector2.new(220, 120)}, f) end
        local function popup(name, title, w, h)
            local p = panel(sg, {Name = name, AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.new(0.5, 0, 0.5, 0), Size = UDim2.new(w, 0, h, 0), Visible = A.show_all == true})
            constrain(p, 760, 640)
            local head = mk("Frame", {Name = "Header", BackgroundTransparency = 1, Size = UDim2.new(1, 0, 0, 52)}, p)
            pad(head, 12)
            label(head, title, 24, {bold = true, size = UDim2.new(1, -60, 1, 0), name = "Title"})
            local x = button(head, "X", {name = "Close", size = UDim2.new(0, 36, 0, 36), textSize = 18})
            x.AnchorPoint = Vector2.new(1, 0.5); x.Position = UDim2.new(1, 0, 0.5, 0); x:SetAttribute("Closes", name)
            local body = mk("Frame", {Name = "Body", BackgroundTransparency = 1, Position = UDim2.new(0, 0, 0, 52), Size = UDim2.new(1, 0, 1, -52)}, p)
            pad(body, 12)
            return p, body
        end
        local built = {}
        local C = {}
        function C.main_menu()
            local p = panel(sg, {Name = "MainMenu", AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.new(0.5, 0, 0.5, 0), Size = UDim2.new(0.34, 0, 0.62, 0)})
            constrain(p, 460, 560)
            pad(p, 20); list(p, 12)
            label(p, A.title or "My Game", 40, {bold = true, align = Enum.TextXAlignment.Center, size = UDim2.new(1, 0, 0, 70), name = "Title"}).LayoutOrder = 0
            label(p, "", 16, {color = T.subtext, align = Enum.TextXAlignment.Center, size = UDim2.new(1, 0, 0, 10)}).LayoutOrder = 1
            for i, b in ipairs(A.buttons) do
                local btn = button(p, b, {primary = (i == 1), order = 10 + i, size = UDim2.new(1, 0, 0, 52)})
                local lower = string.lower(b)
                if lower == "shop" then btn:SetAttribute("Opens", "Shop")
                elseif lower == "settings" or lower == "options" then btn:SetAttribute("Opens", "Settings")
                elseif lower == "inventory" then btn:SetAttribute("Opens", "Inventory")
                elseif lower == "leaderboard" then btn:SetAttribute("Opens", "Leaderboard")
                elseif lower == "play" or lower == "start" then btn:SetAttribute("Closes", "MainMenu") end
            end
        end
        function C.hud()
            local h = mk("Frame", {Name = "HUD", BackgroundTransparency = 1, Size = UDim2.new(1, 0, 1, 0)}, sg)
            local bars = panel(h, {Name = "Bars", Position = UDim2.new(0, 16, 0, 16), Size = UDim2.new(0.22, 0, 0, 78)}); constrain(bars, 340, 110); pad(bars, 10); list(bars, 8)
            local function bar(name, color, txt)
                local row = mk("Frame", {Name = name, BackgroundTransparency = 1, Size = UDim2.new(1, 0, 0, 24)}, bars)
                local back = panel(row, {Name = "Back", Size = UDim2.new(1, 0, 1, 0), BackgroundColor3 = hex(T.bg)}, {corner = math.max(0, T.corner - 2), color = T.bg, alpha = 0.2})
                local fill = mk("Frame", {Name = "Fill", BackgroundColor3 = hex(color), Size = UDim2.new(1, 0, 1, 0), BorderSizePixel = 0}, back)
                mk("UICorner", {CornerRadius = UDim.new(0, math.max(0, T.corner - 2))}, fill)
                label(back, txt, 14, {bold = true, align = Enum.TextXAlignment.Center, size = UDim2.new(1, 0, 1, 0), name = "Value"})
            end
            bar("Health", T.bad, "100 / 100"); bar("Stamina", T.good, "100")
            local cur = panel(h, {Name = "Currency", AnchorPoint = Vector2.new(1, 0), Position = UDim2.new(1, -16, 0, 16), Size = UDim2.new(0, 160, 0, 44)}); pad(cur, 8)
            label(cur, "0 Coins", 20, {bold = true, align = Enum.TextXAlignment.Right, size = UDim2.new(1, 0, 1, 0), name = "Value"})
            local hot = mk("Frame", {Name = "Hotbar", AnchorPoint = Vector2.new(0.5, 1), Position = UDim2.new(0.5, 0, 1, -16), Size = UDim2.new(0, 5 * 64 + 4 * 8, 0, 64), BackgroundTransparency = 1}, h)
            list(hot, 8, Enum.FillDirection.Horizontal, Enum.HorizontalAlignment.Center)
            for i = 1, 5 do
                local slot = panel(hot, {Name = "Slot" .. i, Size = UDim2.new(0, 64, 0, 64), LayoutOrder = i})
                label(slot, tostring(i), 14, {color = T.subtext, pos = UDim2.new(0, 6, 0, 2), size = UDim2.new(0, 20, 0, 18), name = "Key"})
            end
        end
        local function grid(body, count, cell, withBuy)
            local sf = mk("ScrollingFrame", {Name = "Grid", BackgroundTransparency = 1, Size = UDim2.new(1, 0, 1, 0), CanvasSize = UDim2.new(0, 0, 0, 0), AutomaticCanvasSize = Enum.AutomaticSize.Y,
                ScrollBarThickness = 6, BorderSizePixel = 0, ScrollBarImageColor3 = hex(T.accent)}, body)
            mk("UIGridLayout", {CellSize = UDim2.new(0, cell, 0, withBuy and cell + 40 or cell), CellPadding = UDim2.new(0, 10, 0, 10), SortOrder = Enum.SortOrder.LayoutOrder}, sf)
            pad(sf, 4)
            for i = 1, count do
                local card = panel(sf, {Name = "Item" .. i, LayoutOrder = i}, {color = T.panel2})
                mk("ImageLabel", {Name = "Icon", BackgroundTransparency = 1, Image = "rbxasset://textures/ui/GuiImagePlaceholder.png", Size = UDim2.new(1, -16, 0, cell - 16), Position = UDim2.new(0, 8, 0, 8), ScaleType = Enum.ScaleType.Fit}, card)
                if withBuy then
                    label(card, "Item " .. i, 15, {bold = true, align = Enum.TextXAlignment.Center, pos = UDim2.new(0, 0, 0, cell - 8), size = UDim2.new(1, 0, 0, 18), name = "ItemName"})
                    local buy = button(card, tostring(i * 50) .. " Coins", {primary = true, size = UDim2.new(1, -16, 0, 24), textSize = 14, name = "Buy"})
                    buy.Position = UDim2.new(0, 8, 1, -30)
                end
            end
        end
        function C.shop()
            local p, body = popup("Shop", "Shop", 0.6, 0.7); grid(body, A.items, 120, true)
        end
        function C.inventory()
            local p, body = popup("Inventory", "Inventory", 0.55, 0.65); grid(body, A.items, 84, false)
        end
        function C.dialog()
            local p = panel(sg, {Name = "Dialog", AnchorPoint = Vector2.new(0.5, 1), Position = UDim2.new(0.5, 0, 1, -24), Size = UDim2.new(0.6, 0, 0, 160), Visible = A.show_all == true}); constrain(p, 820, 200); pad(p, 16)
            label(p, "Speaker", 22, {bold = true, color = T.accent, size = UDim2.new(1, 0, 0, 28), name = "Speaker"})
            label(p, "Dialogue text goes here. Replace it from a script.", 18, {wrap = true, pos = UDim2.new(0, 0, 0, 34), size = UDim2.new(1, 0, 1, -80), name = "Text"}).TextYAlignment = Enum.TextYAlignment.Top
            local nxt = button(p, "Continue", {primary = true, size = UDim2.new(0, 140, 0, 36), name = "Continue"}); nxt.AnchorPoint = Vector2.new(1, 1); nxt.Position = UDim2.new(1, 0, 1, 0)
        end
        function C.toast()
            local h = mk("Frame", {Name = "Toasts", BackgroundTransparency = 1, AnchorPoint = Vector2.new(0.5, 0), Position = UDim2.new(0.5, 0, 0, 16), Size = UDim2.new(0.4, 0, 0, 200)}, sg)
            constrain(h, 460, 300); list(h, 8)
            local t = panel(h, {Name = "Template", Size = UDim2.new(1, 0, 0, 44), Visible = false}); pad(t, 8)
            label(t, "Notification", 18, {bold = true, size = UDim2.new(1, 0, 1, 0), name = "Message", align = Enum.TextXAlignment.Center})
        end
        function C.settings()
            local p, body = popup("Settings", "Settings", 0.45, 0.6); list(body, 10)
            for i, n in ipairs({"Music", "Sound effects", "Screen shake", "Show tips"}) do
                local row = panel(body, {Name = "Row" .. i, Size = UDim2.new(1, 0, 0, 48), LayoutOrder = i}, {color = T.panel2}); pad(row, 8)
                label(row, n, 18, {size = UDim2.new(0.7, 0, 1, 0), name = "Label"})
                local tg = button(row, "ON", {primary = true, size = UDim2.new(0, 80, 1, 0), name = "Toggle"}); tg.AnchorPoint = Vector2.new(1, 0); tg.Position = UDim2.new(1, 0, 0, 0)
                tg:SetAttribute("Setting", n)
            end
        end
        function C.leaderboard()
            local p, body = popup("Leaderboard", "Leaderboard", 0.4, 0.7)
            local sf = mk("ScrollingFrame", {Name = "Rows", BackgroundTransparency = 1, Size = UDim2.new(1, 0, 1, 0), AutomaticCanvasSize = Enum.AutomaticSize.Y, CanvasSize = UDim2.new(0, 0, 0, 0), ScrollBarThickness = 6, BorderSizePixel = 0}, body)
            list(sf, 6)
            for i = 1, math.min(A.items, 20) do
                local row = panel(sf, {Name = "Rank" .. i, Size = UDim2.new(1, -8, 0, 40), LayoutOrder = i}, {color = T.panel2}); pad(row, 6)
                label(row, "#" .. i, 18, {bold = true, color = (i <= 3) and T.warn or T.subtext, size = UDim2.new(0, 44, 1, 0), name = "Rank"})
                label(row, "Player" .. i, 18, {pos = UDim2.new(0, 52, 0, 0), size = UDim2.new(0.5, 0, 1, 0), name = "Name"})
                label(row, tostring(1000 - i * 37), 18, {bold = true, align = Enum.TextXAlignment.Right, size = UDim2.new(1, 0, 1, 0), name = "Score"})
            end
        end
        function C.loading()
            local f = mk("Frame", {Name = "Loading", BackgroundColor3 = hex(T.bg), BorderSizePixel = 0, Size = UDim2.new(1, 0, 1, 0), ZIndex = 50, Visible = A.show_all == true}, sg)
            label(f, A.title or "Loading", 44, {bold = true, align = Enum.TextXAlignment.Center, pos = UDim2.new(0, 0, 0.4, 0), size = UDim2.new(1, 0, 0, 60), name = "Title"}).ZIndex = 51
            local back = panel(f, {Name = "ProgressBack", AnchorPoint = Vector2.new(0.5, 0), Position = UDim2.new(0.5, 0, 0.55, 0), Size = UDim2.new(0.4, 0, 0, 16), ZIndex = 51}, {corner = 8})
            constrain(back, 520, 24)
            local fill = mk("Frame", {Name = "Fill", BackgroundColor3 = hex(T.accent), BorderSizePixel = 0, Size = UDim2.new(0.35, 0, 1, 0), ZIndex = 52}, back)
            mk("UICorner", {CornerRadius = UDim.new(0, 8)}, fill)
        end
        for _, name in ipairs(A.components) do
            C[name]()
            table.insert(built, name)
        end
        if A.behavior_script ~= false then
            local s = mk("LocalScript", {Name = "MS_UI_Behavior"}, sg)
            s.Source = A._behavior
        end
        local count = 0
        for _ in ipairs(sg:GetDescendants()) do count = count + 1 end
        R.screen_gui = sg:GetFullName()
        R.components = built
        R.instances = count
        R.theme = A.theme
        waypoint("ui kit")
    '''), "ui kit " + th)


@tool(RB, "ms_roblox_ui_audit",
      "Audit ScreenGuis for real usability problems and return a ranked list with fixes: elements outside the viewport, text under the readable size, touch targets under 44px, "
      "low text/background contrast (WCAG ratio), TextScaled without a size constraint, big fixed-pixel layouts without scale/UIScale/constraints, empty buttons, missing images, "
      "overlapping siblings and oversized GUI trees. Read-only unless fix=true (applies safe fixes: min text size, UITextSizeConstraint, button min size).",
      {"path": {"type": "string", "description": "A ScreenGui (or its parent such as StarterGui). Default StarterGui."}, "viewport": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2,
        "description": "Design viewport [w,h] used for checks (default [1920,1080]); also checks [390,844] phone."}, "min_text_size": {"type": "number"}, "fix": {"type": "boolean"}, "limit": {"type": "integer"}})
def ui_audit(args, ctx):
    a = _norm(args, path="StarterGui", min_text_size=14, limit=80)
    a["viewport"] = list(a.get("viewport") or [1920, 1080])
    return _exec(ctx, a, _x(_LIB_MK, '''
        local root = resolve(A.path)
        local issues = {}
        local counts = {error = 0, warn = 0, info = 0}
        local function add(sev, inst, code, msg, fix)
            counts[sev] = counts[sev] + 1
            if #issues < (A.limit or 80) then table.insert(issues, {severity = sev, path = inst:GetFullName(), code = code, message = msg, fix = fix}) end
        end
        local function lum(c)
            local function f(v) if v <= 0.03928 then return v / 12.92 end return ((v + 0.055) / 1.055) ^ 2.4 end
            return 0.2126 * f(c.R) + 0.7152 * f(c.G) + 0.0722 * f(c.B)
        end
        local function ratio(a, b)
            local l1, l2 = lum(a), lum(b)
            if l1 < l2 then l1, l2 = l2, l1 end
            return (l1 + 0.05) / (l2 + 0.05)
        end
        local vw, vh = A.viewport[1], A.viewport[2]
        local total, fixed = 0, 0
        local guis = {}
        if root:IsA("ScreenGui") then guis = {root} else
            for _, c in ipairs(root:GetChildren()) do if c:IsA("ScreenGui") then table.insert(guis, c) end end
        end
        for _, sg in ipairs(guis) do
            local n = 0
            for _, d in ipairs(sg:GetDescendants()) do
                if d:IsA("GuiObject") then
                    n = n + 1
                    total = total + 1
                    local sz = d.Size
                    -- fixed-pixel giant elements
                    if sz.X.Scale == 0 and sz.X.Offset > vw * 0.9 and not d:FindFirstChildOfClass("UISizeConstraint") then
                        add("warn", d, "fixed_wide", "Fixed-pixel width " .. sz.X.Offset .. " fills the whole screen and will not adapt to phones.", "Use Scale width plus a UISizeConstraint.")
                    end
                    if d:IsA("TextButton") or d:IsA("ImageButton") then
                        local w = (sz.X.Scale == 0) and sz.X.Offset or (sz.X.Scale * vw)
                        local h = (sz.Y.Scale == 0) and sz.Y.Offset or (sz.Y.Scale * vh)
                        if (w > 0 and w < 44) or (h > 0 and h < 44) then
                            add("warn", d, "small_target", string.format("Touch target is about %dx%d px (minimum 44).", math.floor(w), math.floor(h)), "Make buttons at least 44x44 px or add padding.")
                            if A.fix and d.Visible then
                                if sz.X.Scale == 0 and sz.X.Offset < 44 then d.Size = UDim2.new(0, 44, sz.Y.Scale, sz.Y.Offset) end
                                if sz.Y.Scale == 0 and sz.Y.Offset < 44 then d.Size = UDim2.new(d.Size.X.Scale, d.Size.X.Offset, 0, 44) end
                                fixed = fixed + 1
                            end
                        end
                    end
                    if d:IsA("TextLabel") or d:IsA("TextButton") or d:IsA("TextBox") then
                        if not d.TextScaled and d.TextSize < (A.min_text_size or 14) then
                            add("warn", d, "tiny_text", "TextSize " .. d.TextSize .. " is under " .. (A.min_text_size or 14) .. ".", "Raise TextSize to at least " .. (A.min_text_size or 14) .. ".")
                            if A.fix then d.TextSize = A.min_text_size or 14; fixed = fixed + 1 end
                        end
                        if d.TextScaled and not d:FindFirstChildOfClass("UITextSizeConstraint") then
                            add("info", d, "scaled_no_constraint", "TextScaled without a UITextSizeConstraint can become unreadably small or huge.", "Add UITextSizeConstraint (Min 12, Max 36).")
                            if A.fix then mk("UITextSizeConstraint", {MinTextSize = 12, MaxTextSize = 40}, d); fixed = fixed + 1 end
                        end
                        if d.Text == "" and d:IsA("TextButton") then
                            add("info", d, "empty_button", "Button has no text (is it an icon button? give it an icon or a label).", "Set Text or add an ImageLabel child.")
                        end
                        if d.BackgroundTransparency < 0.5 then
                            local r = ratio(d.TextColor3, d.BackgroundColor3)
                            if r < 4.5 then add("warn", d, "low_contrast", string.format("Text/background contrast is %.1f:1 (needs 4.5:1).", r), "Darken the background or lighten the text.") end
                        end
                    end
                    if d:IsA("ImageLabel") or d:IsA("ImageButton") then
                        if d.Image == "" then add("info", d, "no_image", "Image is empty (placeholder?).", "Set Image to an asset id.") end
                    end
                    -- off-screen using absolute geometry when available
                    local ap, as = d.AbsolutePosition, d.AbsoluteSize
                    if as.X > 0 and as.Y > 0 and d.Visible then
                        if ap.X + as.X < 0 or ap.Y + as.Y < 0 or ap.X > vw or ap.Y > vh then
                            add("error", d, "offscreen", "Element is completely outside a " .. vw .. "x" .. vh .. " viewport.", "Reposition it or use AnchorPoint/Scale.")
                        end
                    end
                end
            end
            if n > 600 then add("warn", sg, "huge_tree", "ScreenGui contains " .. n .. " GuiObjects; consider pooling or lazy creation.", "Create popups on demand.") end
            if sg.ZIndexBehavior ~= Enum.ZIndexBehavior.Sibling then add("info", sg, "zindex_global", "ZIndexBehavior is Global; Sibling is easier to reason about.", "Set ZIndexBehavior = Sibling.") end
        end
        R.screen_guis = #guis
        R.gui_objects = total
        R.counts = counts
        R.issues = issues
        R.fixed = fixed
        R.grade = (counts.error > 0 and "needs work") or (counts.warn > 6 and "fair") or (counts.warn > 0 and "good") or "excellent"
    '''), "ui audit")


# ─────────────────────────────── helpers for generated runtime scripts ───────────────────────────────
def _lua(v, indent=0):
    """Python value -> Luau literal (tables, strings, numbers, booleans)."""
    if v is None:
        return "nil"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        if isinstance(v, float):
            return repr(v) if v != int(v) else str(int(v))
        return str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return "{" + ", ".join(_lua(x) for x in v) + "}"
    if isinstance(v, dict):
        parts = []
        for k, x in v.items():
            key = str(k)
            parts.append((key if key.isidentifier() else "[" + json.dumps(key) + "]") + " = " + _lua(x))
        return "{" + ", ".join(parts) + "}"
    return json.dumps(str(v))


def _script_cls(a, default="Script"):
    c = str(a.get("script_type") or default)
    return c if c in ("Script", "LocalScript", "ModuleScript") else default


_PLACE_SCRIPT = '''
local parent = resolve(A.parent_path or "ServerScriptService")
local s = parent:FindFirstChild(A.script_name)
if s and s:IsA("LuaSourceContainer") then s:Destroy() end
s = Instance.new(A.script_class or "Script")
s.Name = A.script_name
s.Source = A.script_source
if s:IsA("Script") and A.run_context and A.run_context ~= "Legacy" then pcall(function() s.RunContext = Enum.RunContext[A.run_context] end) end
s.Parent = parent
R.script = s:GetFullName()
R.script_lines = select(2, string.gsub(A.script_source, "\\n", "\\n")) + 1
'''

# ─────────────────────────────── Tween animation scripts ───────────────────────────────
TWEEN_KINDS = ["float", "spin", "pulse", "slide", "swing", "fade", "color_cycle", "wobble", "orbit", "custom"]

_TWEEN_SRC = '''-- Generated by Multi-Script (ms_roblox_tween_animation: %(kind)s). Edit the CFG table to tune it.
local TweenService = game:GetService("TweenService")
local RunService = game:GetService("RunService")
local CFG = %(cfg)s
local target = script.Parent
local STYLE = Enum.EasingStyle[CFG.style] or Enum.EasingStyle.Sine
local DIR = Enum.EasingDirection[CFG.direction] or Enum.EasingDirection.InOut
local info = TweenInfo.new(CFG.duration, STYLE, DIR, 0, false, CFG.delay or 0)
local alive = true
script.Destroying:Connect(function() alive = false end)

local function isModel() return target:IsA("Model") end
local function pivot() if isModel() then return target:GetPivot() end return target.CFrame end
local function setPivot(cf) if isModel() then target:PivotTo(cf) else target.CFrame = cf end end
local base = pivot()
local driver = Instance.new("NumberValue")
local function drive(from, to, apply)
    driver.Value = from
    local conn = driver.Changed:Connect(apply)
    local tw = TweenService:Create(driver, info, {Value = to})
    tw:Play()
    tw.Completed:Wait()
    conn:Disconnect()
end
local function vec(t) return Vector3.new(t[1], t[2], t[3]) end

local function cycle(fn)
    repeat
        fn()
    until not CFG.loop or not alive
end

local kind = CFG.kind
if kind == "float" then
    local off = vec(CFG.offset)
    cycle(function()
        drive(0, 1, function(a) setPivot(base + off * a) end)
        if CFG.reverse then drive(1, 0, function(a) setPivot(base + off * a) end) end
    end)
elseif kind == "slide" then
    local off = vec(CFG.offset)
    cycle(function()
        drive(0, 1, function(a) setPivot(base + off * a) end)
        task.wait(CFG.pause or 0)
        if CFG.reverse then drive(1, 0, function(a) setPivot(base + off * a) end) end
        task.wait(CFG.pause or 0)
    end)
elseif kind == "spin" then
    local axis = vec(CFG.axis)
    local speed = math.rad(CFG.degrees_per_second)
    local angle = 0
    RunService.Heartbeat:Connect(function(dt)
        if not alive then return end
        angle = angle + speed * dt
        setPivot(base * CFG.cfAngles(axis, angle))
    end)
elseif kind == "swing" then
    local axis = vec(CFG.axis)
    local limit = math.rad(CFG.degrees)
    cycle(function()
        drive(-1, 1, function(a) setPivot(base * CFG.cfAngles(axis, limit * a)) end)
        drive(1, -1, function(a) setPivot(base * CFG.cfAngles(axis, limit * a)) end)
    end)
elseif kind == "wobble" then
    local axis = vec(CFG.axis)
    local limit = math.rad(CFG.degrees)
    local t0 = os.clock()
    RunService.Heartbeat:Connect(function()
        if not alive then return end
        local t = os.clock() - t0
        setPivot(base * CFG.cfAngles(axis, limit * math.sin(t * math.pi * 2 / CFG.duration)) + Vector3.new(0, (CFG.bob or 0) * math.sin(t * math.pi * 2 / CFG.duration), 0))
    end)
elseif kind == "orbit" then
    local center = vec(CFG.center)
    local radius = CFG.radius
    local speed = math.rad(CFG.degrees_per_second)
    local angle = CFG.start_degrees and math.rad(CFG.start_degrees) or 0
    RunService.Heartbeat:Connect(function(dt)
        if not alive then return end
        angle = angle + speed * dt
        local p = center + Vector3.new(math.cos(angle) * radius, 0, math.sin(angle) * radius)
        if CFG.face_center then setPivot(CFrame.lookAt(p, center)) else setPivot(CFrame.new(p) * (base - base.Position)) end
    end)
elseif kind == "pulse" then
    local s0 = isModel() and nil or target.Size
    local lo, hi = CFG.scale_min, CFG.scale_max
    local function apply(a)
        local k = lo + (hi - lo) * a
        if isModel() then target:ScaleTo(k) else target.Size = s0 * k end
    end
    cycle(function() drive(0, 1, apply); drive(1, 0, apply) end)
elseif kind == "fade" then
    local parts = {}
    if target:IsA("BasePart") then parts[1] = target end
    for _, d in ipairs(target:GetDescendants()) do if d:IsA("BasePart") then parts[#parts + 1] = d end end
    local orig = {}
    for i, p in ipairs(parts) do orig[i] = p.Transparency end
    local lo, hi = CFG.from_transparency, CFG.to_transparency
    local function apply(a) for i, p in ipairs(parts) do p.Transparency = lo + (hi - lo) * a end end
    cycle(function() drive(0, 1, apply); task.wait(CFG.pause or 0); drive(1, 0, apply); task.wait(CFG.pause or 0) end)
elseif kind == "color_cycle" then
    local cols = {}
    for i, h in ipairs(CFG.colors) do cols[i] = Color3.fromHex(h) end
    local i = 1
    target.Color = cols[1]
    cycle(function()
        for n = 1, #cols do
            local nxt = cols[(n %% #cols) + 1]
            local tw = TweenService:Create(target, info, {Color = nxt})
            tw:Play(); tw.Completed:Wait()
        end
    end)
elseif kind == "custom" then
    local function conv(inst, prop, v)
        local cur = inst[prop]
        local t = typeof(cur)
        if t == "Vector3" and type(v) == "table" then return Vector3.new(v[1], v[2], v[3]) end
        if t == "Vector2" and type(v) == "table" then return Vector2.new(v[1], v[2]) end
        if t == "Color3" and type(v) == "string" then return Color3.fromHex(v) end
        if t == "UDim2" and type(v) == "table" then return UDim2.new(v[1], v[2], v[3], v[4]) end
        if t == "CFrame" and type(v) == "table" then return CFrame.new(v[1], v[2], v[3]) end
        return v
    end
    cycle(function()
        for _, step in ipairs(CFG.steps) do
            local props = {}
            for k, v in pairs(step.props) do props[k] = conv(target, k, v) end
            local ti = TweenInfo.new(step.time or CFG.duration, Enum.EasingStyle[step.style or CFG.style] or STYLE, Enum.EasingDirection[step.direction or CFG.direction] or DIR)
            local tw = TweenService:Create(target, ti, props)
            tw:Play(); tw.Completed:Wait()
            if step.wait then task.wait(step.wait) end
        end
    end)
end
'''


def _fix_tween_src(src):
    # CFG.cfAngles is not serialisable, so emit a local helper instead
    helper = ('local function angleCF(axis, ang)\n    if axis.Magnitude < 1e-6 then return CFrame.new() end\n'
              '    return CFrame.fromAxisAngle(axis.Unit, ang)\nend\n')
    return helper_insert(src, helper).replace("CFG.cfAngles(", "angleCF(")


def helper_insert(src, helper):
    marker = "local function vec(t)"
    return src.replace(marker, helper + marker, 1)


@tool(RB, "ms_roblox_tween_animation",
      "Generate an animation Script/LocalScript (TweenService/Heartbeat) under a Part, Model or GuiObject: float, slide, spin, swing, wobble, orbit, pulse, fade, color_cycle or custom tween steps. Works on Models (PivotTo/ScaleTo); easing, loop and duration adjustable via an editable CFG table. Re-running replaces it.",
      {"target": PATH, "kind": {"type": "string", "enum": TWEEN_KINDS}, "duration": {"type": "number", "description": "Seconds per half-cycle (default 1.5)."},
       "offset": VEC, "axis": VEC, "degrees": {"type": "number"}, "degrees_per_second": {"type": "number"}, "radius": {"type": "number"}, "center": VEC,
       "scale_min": {"type": "number"}, "scale_max": {"type": "number"}, "from_transparency": {"type": "number"}, "to_transparency": {"type": "number"},
       "colors": {"type": "array", "items": {"type": "string"}}, "steps": {"type": "array", "items": {"type": "object"}, "description": "custom: [{props:{Position:[x,y,z]}, time, style, direction, wait}]"},
       "style": {"type": "string", "description": "Enum.EasingStyle name (Sine, Quad, Back, Elastic, Bounce, Linear...). Default Sine."},
       "direction": {"type": "string", "enum": ["In", "Out", "InOut"]}, "loop": {"type": "boolean"}, "reverse": {"type": "boolean"}, "delay": {"type": "number"}, "pause": {"type": "number"},
       "script_type": {"type": "string", "enum": ["Script", "LocalScript"]}, "name": {"type": "string"}},
      ["target", "kind"], writes=True)
def tween_animation(args, ctx):
    a = dict(args)
    kind = str(a.get("kind") or "").lower()
    if kind not in TWEEN_KINDS:
        raise ToolkitError(f"unknown kind '{kind}'", "Use one of: " + ", ".join(TWEEN_KINDS))
    if kind == "custom" and not as_list(a.get("steps")):
        raise ToolkitError("kind=custom needs `steps`", 'Example: [{"props":{"Position":[0,10,0]},"time":1}]')
    cfg = {"kind": kind, "duration": num(a.get("duration"), 1.5, 0.05, 600), "style": str(a.get("style") or "Sine"), "direction": str(a.get("direction") or "InOut"),
           "loop": boolean(a.get("loop"), True), "reverse": boolean(a.get("reverse"), True), "delay": num(a.get("delay"), 0, 0, 600), "pause": num(a.get("pause"), 0, 0, 600)}
    cfg["offset"] = vec3(a.get("offset"), (0, 4, 0)) if a.get("offset") is not None or kind in ("float", "slide") else [0, 0, 0]
    cfg["axis"] = vec3(a.get("axis"), (0, 1, 0)) if kind in ("spin", "swing", "wobble") else [0, 1, 0]
    cfg["degrees"] = num(a.get("degrees"), 45 if kind == "swing" else 8, -3600, 3600)
    cfg["degrees_per_second"] = num(a.get("degrees_per_second"), 90, -3600, 3600)
    cfg["radius"] = num(a.get("radius"), 12, 0.1, 5000)
    cfg["center"] = vec3(a.get("center"), (0, 5, 0))
    cfg["face_center"] = boolean(a.get("face_center"), False)
    cfg["scale_min"] = num(a.get("scale_min"), 0.9, 0.01, 100)
    cfg["scale_max"] = num(a.get("scale_max"), 1.15, 0.01, 100)
    cfg["from_transparency"] = num(a.get("from_transparency"), 0, 0, 1)
    cfg["to_transparency"] = num(a.get("to_transparency"), 0.85, 0, 1)
    cfg["colors"] = [str(c) for c in as_list(a.get("colors"))] or ["#ff4d6d", "#ffd23f", "#4dd2ff", "#a66bff"]
    cfg["steps"] = as_list(a.get("steps"))
    if kind == "wobble":
        cfg["bob"] = num(a.get("bob"), 0.4, 0, 100)
    src = _fix_tween_src(_TWEEN_SRC % {"kind": kind, "cfg": _lua(cfg)})
    sc = _script_cls(a, "Script")
    a.update({"script_class": sc, "script_name": str(a.get("name") or "MS_Tween_" + kind), "script_source": src, "parent_path": a["target"]})
    a.pop("kind", None)
    a["kind_name"] = kind
    return _exec(ctx, a, _x(_PLACE_SCRIPT, '''
        local t = resolve(A.target)
        if A.script_class == "LocalScript" and not (t:IsA("GuiObject") or t:IsA("LayerCollector")) then R.note = "LocalScripts only run under StarterGui/StarterPlayerScripts/character; use Script for world objects." end
        R.kind = A.kind_name
        waypoint("tween animation")
    '''), "tween animation " + kind)


# ─────────────────────────────── R15 keyframe sequences ───────────────────────────────
R15_TREE = {"LowerTorso": {"UpperTorso": {"Head": {}, "LeftUpperArm": {"LeftLowerArm": {"LeftHand": {}}}, "RightUpperArm": {"RightLowerArm": {"RightHand": {}}}},
                           "LeftUpperLeg": {"LeftLowerLeg": {"LeftFoot": {}}}, "RightUpperLeg": {"RightLowerLeg": {"RightFoot": {}}}}}
ANIM_PRESETS = ["idle", "walk", "run", "jump", "fall", "wave", "dance", "cheer", "sit", "punch", "crouch", "salute"]


def _sin(p, k=1, ph=0.0):
    return math.sin(2 * math.pi * (p * k + ph))


def _cos(p, k=1, ph=0.0):
    return math.cos(2 * math.pi * (p * k + ph))


def _r15_pose(preset, p, power=1.0):
    """Return (joint -> (rx, ry, rz) degrees, root_offset (x,y,z)) for phase p in [0,1]."""
    j = {}
    root = (0.0, 0.0, 0.0)
    s = power
    if preset == "idle":
        j = {"UpperTorso": (1.5 * _sin(p), 0, 0), "Head": (-1.0 * _sin(p), 2 * _sin(p, 1, 0.25), 0), "LeftUpperArm": (2 * _sin(p, 1, 0.1), 0, -4 - 1.5 * _sin(p)),
             "RightUpperArm": (2 * _sin(p, 1, 0.1), 0, 4 + 1.5 * _sin(p)), "LeftLowerArm": (6, 0, 0), "RightLowerArm": (6, 0, 0)}
        root = (0, 0.04 * _sin(p), 0)
    elif preset in ("walk", "run"):
        run = preset == "run"
        amp = (55 if run else 32) * s
        knee = (80 if run else 45) * s
        arm = (60 if run else 28) * s
        w = _sin(p)
        j = {"LeftUpperLeg": (amp * w, 0, 0), "RightUpperLeg": (-amp * w, 0, 0),
             "LeftLowerLeg": (-knee * max(0.0, -_cos(p)) - 4, 0, 0), "RightLowerLeg": (-knee * max(0.0, _cos(p)) - 4, 0, 0),
             "LeftFoot": (10 * _sin(p, 1, 0.25) * s, 0, 0), "RightFoot": (-10 * _sin(p, 1, 0.25) * s, 0, 0),
             "LeftUpperArm": (-arm * w, 0, -4), "RightUpperArm": (arm * w, 0, 4),
             "LeftLowerArm": ((70 if run else 12) + 12 * max(0.0, w), 0, 0), "RightLowerArm": ((70 if run else 12) + 12 * max(0.0, -w), 0, 0),
             "LowerTorso": (0, -(10 if run else 4) * w, 0), "UpperTorso": ((-12 if run else -3), (10 if run else 5) * w, 0), "Head": (0, -(6 if run else 3) * w, 0)}
        root = (0, 0.12 * abs(_sin(p, 1)) * (2 if run else 1) - 0.04, 0)
    elif preset == "jump":
        # p in [0,1]: crouch (0-0.2), launch (0.2-0.4), airborne tuck (0.4-1)
        if p < 0.2:
            k = p / 0.2
            j = {"LeftUpperLeg": (-40 * k, 0, 0), "RightUpperLeg": (-40 * k, 0, 0), "LeftLowerLeg": (70 * k, 0, 0), "RightLowerLeg": (70 * k, 0, 0),
                 "UpperTorso": (-18 * k, 0, 0), "LeftUpperArm": (30 * k, 0, -5), "RightUpperArm": (30 * k, 0, 5)}
            root = (0, -0.9 * k, 0)
        else:
            k = min(1.0, (p - 0.2) / 0.2)
            j = {"LeftUpperLeg": (-20 * k, 0, 0), "RightUpperLeg": (30 * k, 0, 0), "LeftLowerLeg": (-10 * k, 0, 0), "RightLowerLeg": (-50 * k, 0, 0),
                 "UpperTorso": (4, 0, 0), "LeftUpperArm": (-150 * k, 0, -20 * k), "RightUpperArm": (-150 * k, 0, 20 * k), "LeftLowerArm": (10, 0, 0), "RightLowerArm": (10, 0, 0)}
            root = (0, 0.3 * k, 0)
    elif preset == "fall":
        f = 0.5 + 0.5 * _sin(p)
        j = {"LeftUpperArm": (-140 + 15 * f, 0, -35 - 8 * f), "RightUpperArm": (-140 + 15 * (1 - f), 0, 35 + 8 * (1 - f)), "LeftLowerArm": (10, 0, 0), "RightLowerArm": (10, 0, 0),
             "LeftUpperLeg": (-10 + 12 * f, 0, -5), "RightUpperLeg": (-10 + 12 * (1 - f), 0, 5), "LeftLowerLeg": (-25, 0, 0), "RightLowerLeg": (-25, 0, 0), "UpperTorso": (-6, 0, 0)}
    elif preset == "wave":
        j = {"RightUpperArm": (0, 0, 150 * min(1.0, p * 6, (1 - p) * 6)), "RightLowerArm": (0, 0, -(5 + 28 * _sin(p, 3)) * min(1.0, p * 6, (1 - p) * 6)),
             "UpperTorso": (0, -4 * min(1.0, p * 6, (1 - p) * 6), 0), "Head": (0, -8 * min(1.0, p * 6, (1 - p) * 6), 0), "LeftUpperArm": (0, 0, -4)}
    elif preset == "dance":
        a = _sin(p)
        b = _sin(p, 2)
        j = {"UpperTorso": (4 * abs(b), 12 * a, 6 * a), "LowerTorso": (0, -8 * a, -3 * a), "Head": (4 * b, -12 * a, 0),
             "LeftUpperArm": (0, 0, -(70 + 60 * b)), "RightUpperArm": (0, 0, 70 + 60 * -b), "LeftLowerArm": (-30, 0, 0), "RightLowerArm": (-30, 0, 0),
             "LeftUpperLeg": (15 * b, 0, -8), "RightUpperLeg": (-15 * b, 0, 8), "LeftLowerLeg": (-25 * max(0.0, b), 0, 0), "RightLowerLeg": (-25 * max(0.0, -b), 0, 0)}
        root = (0.25 * a, 0.18 * abs(b) - 0.05, 0)
    elif preset == "cheer":
        b = abs(_sin(p, 2))
        j = {"LeftUpperArm": (0, 0, -(150 + 15 * b)), "RightUpperArm": (0, 0, 150 + 15 * b), "LeftLowerArm": (-8, 0, 0), "RightLowerArm": (-8, 0, 0),
             "UpperTorso": (-6, 0, 0), "Head": (-12, 0, 0), "LeftUpperLeg": (-10 * b, 0, -6), "RightUpperLeg": (-10 * b, 0, 6), "LeftLowerLeg": (20 * b, 0, 0), "RightLowerLeg": (20 * b, 0, 0)}
        root = (0, 0.5 * b, 0)
    elif preset == "sit":
        j = {"LeftUpperLeg": (-90, 0, -3), "RightUpperLeg": (-90, 0, 3), "LeftLowerLeg": (90, 0, 0), "RightLowerLeg": (90, 0, 0), "LeftUpperArm": (-25, 0, -8), "RightUpperArm": (-25, 0, 8),
             "LeftLowerArm": (50, 0, 0), "RightLowerArm": (50, 0, 0), "UpperTorso": (2 * _sin(p), 0, 0)}
        root = (0, -0.5, 0)
    elif preset == "punch":
        k = max(0.0, min(1.0, p * 5)) if p < 0.4 else max(0.0, 1 - (p - 0.4) * 3)
        j = {"RightUpperArm": (-90 * k, 0, 8), "RightLowerArm": (90 * (1 - k) + 5, 0, 0), "UpperTorso": (0, -35 * k, 0), "LowerTorso": (0, -12 * k, 0),
             "LeftUpperArm": (-60, 0, -10), "LeftLowerArm": (110, 0, 0), "LeftUpperLeg": (-12, 0, -4), "RightUpperLeg": (14 * k, 0, 4), "LeftLowerLeg": (14, 0, 0)}
    elif preset == "crouch":
        j = {"LeftUpperLeg": (-70, 0, -5), "RightUpperLeg": (-70, 0, 5), "LeftLowerLeg": (110, 0, 0), "RightLowerLeg": (110, 0, 0), "UpperTorso": (-25 + 1.5 * _sin(p), 0, 0),
             "LeftUpperArm": (-20, 0, -6), "RightUpperArm": (-20, 0, 6), "LeftFoot": (-20, 0, 0), "RightFoot": (-20, 0, 0)}
        root = (0, -1.0, 0)
    elif preset == "salute":
        k = min(1.0, p * 5, (1 - p) * 5)
        j = {"RightUpperArm": (-100 * k, 0, 25 * k), "RightLowerArm": (115 * k, 0, 0), "Head": (0, 0, 0), "LeftUpperArm": (0, 0, -4)}
    return j, root


@tool(RB, "ms_roblox_keyframe_sequence",
      "Build an R15 KeyframeSequence from a preset (idle, walk, run, jump, fall, wave, dance, cheer, sit, punch, crouch, salute) or custom keyframes ({time, poses:{Joint:[rx,ry,rz]}, root}). Nested poses, easing, loop, priority; optional playtest Script. Publish via the Animation Editor for an asset id.",
      {"preset": {"type": "string", "enum": ANIM_PRESETS}, "keyframes": {"type": "array", "items": {"type": "object"}, "description": "Custom keyframes (overrides preset)."},
       "name": {"type": "string"}, "parent": {"type": "string", "description": "Where to put it (default ReplicatedStorage)."}, "length": {"type": "number", "description": "Seconds."},
       "frames": {"type": "integer", "description": "Keyframe count for cyclic presets (default 9)."}, "power": {"type": "number", "description": "Amplitude multiplier (default 1)."},
       "loop": {"type": "boolean"}, "priority": {"type": "string", "enum": ["Core", "Idle", "Movement", "Action", "Action2", "Action3", "Action4"]},
       "easing": {"type": "string", "enum": ["Linear", "Constant", "Elastic", "Cubic", "Bounce", "CubicV2"]}, "play_script": {"type": "boolean"}},
      [], writes=True)
def keyframe_sequence(args, ctx):
    a = dict(args)
    preset = str(a.get("preset") or "").lower()
    kfs = as_list(a.get("keyframes"))
    if not kfs and preset not in ANIM_PRESETS:
        raise ToolkitError("give a preset or keyframes", "Presets: " + ", ".join(ANIM_PRESETS))
    power = num(a.get("power"), 1.0, 0.05, 5)
    if kfs:
        frames = []
        for k in kfs:
            k = as_dict(k)
            frames.append({"t": num(k.get("time"), 0, 0, 600), "poses": {str(n): [num(x, 0, -720, 720) for x in as_list(v)[:3]] for n, v in as_dict(k.get("poses")).items()},
                           "root": vec3(k.get("root"), (0, 0, 0))})
        length = num(a.get("length"), max(f["t"] for f in frames) or 1.0, 0.05, 600)
        loop = boolean(a.get("loop"), False)
    else:
        cyc = preset in ("idle", "walk", "run", "fall", "dance", "cheer", "crouch", "sit")
        n = int(num(a.get("frames"), 9, 3, 60))
        length = num(a.get("length"), {"idle": 2.4, "walk": 0.9, "run": 0.55, "jump": 0.8, "fall": 1.0, "wave": 1.8, "dance": 1.6, "cheer": 1.2, "sit": 2.0, "punch": 0.5, "crouch": 1.5, "salute": 1.2}[preset], 0.05, 600)
        frames = []
        for i in range(n):
            ph = i / (n - 1)
            pose, root = _r15_pose(preset, ph if not cyc else (ph if i < n - 1 else 0.0), power)
            frames.append({"t": round(ph * length, 4), "poses": {k: [round(x, 3) for x in v] for k, v in pose.items()}, "root": [round(x, 4) for x in root]})
        loop = boolean(a.get("loop"), preset in ("idle", "walk", "run", "fall", "dance", "cheer", "crouch", "sit"))
    pri = str(a.get("priority") or {"idle": "Idle", "walk": "Movement", "run": "Movement", "fall": "Action", "sit": "Action"}.get(preset, "Action"))
    name = str(a.get("name") or "MS_Anim_" + (preset or "custom"))
    payload = {"name": name, "parent": a.get("parent") or "ReplicatedStorage", "frames": frames, "length": length, "loop": loop, "priority": pri,
               "easing": str(a.get("easing") or "Cubic"), "tree": R15_TREE, "play": boolean(a.get("play_script"), False),
               "play_src": _PLAY_SRC % {"name": name}, "dry_run": a.get("dry_run"), "studio_id": a.get("studio_id"), "mode": a.get("mode")}
    return _exec(ctx, payload, _x(_LIB_MK, _KS_BODY), "keyframe sequence " + (preset or "custom"))


_PLAY_SRC = '''-- Generated by Multi-Script: plays the KeyframeSequence %(name)s on this character (Studio playtest).
local RS = game:GetService("ReplicatedStorage")
local KSP = game:GetService("KeyframeSequenceProvider")
local char = script.Parent
local hum = char:WaitForChild("Humanoid")
local animator = hum:WaitForChild("Animator")
local ks = RS:WaitForChild("%(name)s")
local ok, id = pcall(function() return KSP:RegisterKeyframeSequence(ks) end)
if not ok then warn("RegisterKeyframeSequence failed: " .. tostring(id)) return end
local anim = Instance.new("Animation")
anim.AnimationId = id
local track = animator:LoadAnimation(anim)
track.Looped = ks.Loop
track:Play()
'''

_KS_BODY = '''
local parent = resolve(A.parent)
local old = parent:FindFirstChild(A.name)
if old then old:Destroy() end
local ks = Instance.new("KeyframeSequence")
ks.Name = A.name
ks.Loop = A.loop
pcall(function() ks.Priority = Enum.AnimationPriority[A.priority] end)
local easing = enumOf("PoseEasingStyle", A.easing, "Linear")
local function build(node, parentPose, poses)
    for jname, kids in pairs(node) do
        local pose = Instance.new("Pose")
        pose.Name = jname
        local d = poses[jname]
        local cf = CFrame.new()
        if d then cf = CFrame.Angles(math.rad(d[1] or 0), math.rad(d[2] or 0), math.rad(d[3] or 0)) end
        pose.CFrame = cf
        pose.Weight = d and 1 or 0
        pcall(function() pose.EasingStyle = easing end)
        pose.Parent = parentPose
        build(kids, pose, poses)
    end
end
for _, f in ipairs(A.frames) do
    local kf = Instance.new("Keyframe")
    kf.Time = f.t
    local root = Instance.new("Pose")
    root.Name = "HumanoidRootPart"
    root.Weight = 0
    local r = f.root or {0, 0, 0}
    root.CFrame = CFrame.new(r[1] or 0, r[2] or 0, r[3] or 0)
    root.Parent = kf
    build(A.tree, root, f.poses or {})
    kf.Parent = ks
end
ks.Parent = parent
R.sequence = ks:GetFullName()
R.keyframes = #A.frames
R.length = A.length
R.loop = A.loop
if A.play then
    local scs = game:GetService("StarterPlayer"):FindFirstChild("StarterCharacterScripts")
    if scs then
        local s = scs:FindFirstChild("MS_Play_" .. A.name)
        if s then s:Destroy() end
        s = Instance.new("LocalScript")
        s.Name = "MS_Play_" .. A.name
        s.Source = A.play_src
        s.Parent = scs
        R.play_script = s:GetFullName()
    end
end
R.note = "Publish through the Animation Editor to get an asset id for production; the play script works in Studio playtests."
waypoint("keyframe sequence")
'''


# ─────────────────────────────── Level blockout from ASCII ───────────────────────────────
BLOCK_THEMES = {
    "grassland": {"floor": ("#5aa64b", "Grass"), "wall": ("#8a8f98", "Slate"), "accent": ("#d9b45a", "Wood"), "lava": ("#ff4a1c", "Neon"), "water": ("#3a8fd8", "Glass")},
    "dungeon": {"floor": ("#4a4a52", "Cobblestone"), "wall": ("#2e2e36", "Brick"), "accent": ("#8a5a2b", "Wood"), "lava": ("#ff4a1c", "Neon"), "water": ("#2a5a78", "Glass")},
    "sci_fi": {"floor": ("#2b3547", "Metal"), "wall": ("#4d5d7a", "DiamondPlate"), "accent": ("#3df2ff", "Neon"), "lava": ("#ff2d6f", "Neon"), "water": ("#1b6aa8", "Glass")},
    "desert": {"floor": ("#d9bf80", "Sand"), "wall": ("#b58b55", "Sandstone"), "accent": ("#8a5a2b", "Wood"), "lava": ("#d94a1c", "Neon"), "water": ("#4aa8c8", "Glass")},
    "candy": {"floor": ("#ffb3d9", "SmoothPlastic"), "wall": ("#a0e8ff", "SmoothPlastic"), "accent": ("#ffe066", "SmoothPlastic"), "lava": ("#ff4d6d", "Neon"), "water": ("#9be3ff", "Glass")},
    "snow": {"floor": ("#eaf2ff", "Snow"), "wall": ("#9fb7d4", "Ice"), "accent": ("#6b4a2b", "Wood"), "lava": ("#ff6a3d", "Neon"), "water": ("#7ac4f0", "Ice")},
}
LEGEND = {"#": "wall", ".": "floor", "S": "spawn", "C": "coin", "L": "lava", "~": "water", "G": "goal", "D": "door", "P": "pillar", "T": "tree", "B": "crate", "K": "checkpoint",
          "E": "enemy", "^": "stairs", "=": "platform", "+": "floor"}
BLOCK_KINDS = sorted(set(LEGEND.values()))


@tool(RB, "ms_roblox_level_blockout",
      "Turn an ASCII map into a playable greybox level: # wall, . floor, S spawn, C coin, L lava, ~ water, G goal, P pillar, T tree, B crate, K checkpoint, E enemy, ^ stairs, = platform (override via legend). Merged rectangles, 6 themes, gameplay tags (Spawn, Coin, KillBrick, Goal, Checkpoint).",
      {"rows": {"type": "array", "items": {"type": "string"}, "description": "One string per map row (top = north)."}, "ascii": {"type": "string", "description": "Alternative to rows: newline separated map."},
       "cell": {"type": "number", "description": "Cell size in studs (default 8)."}, "wall_height": {"type": "number"}, "floor_thickness": {"type": "number"},
       "origin": VEC, "theme": {"type": "string", "enum": list(BLOCK_THEMES)}, "legend": {"type": "object", "description": "Override char -> kind (" + ", ".join(BLOCK_KINDS) + ")."},
       "name": {"type": "string"}, "parent": {"type": "string"}, "clear_existing": {"type": "boolean"}},
      [], writes=True)
def level_blockout(args, ctx):
    a = dict(args)
    rows = [str(r) for r in as_list(a.get("rows"))]
    if not rows and a.get("ascii"):
        rows = str(a["ascii"]).strip("\n").split("\n")
    if not rows:
        raise ToolkitError("give `rows` (array of strings) or `ascii`", 'Example rows: ["#####","#S.C#","#####"]')
    if len(rows) > 200 or max(len(r) for r in rows) > 200:
        raise ToolkitError("map too large (max 200x200 cells)")
    theme = str(a.get("theme") or "grassland")
    if theme not in BLOCK_THEMES:
        raise ToolkitError(f"unknown theme '{theme}'", "Use one of: " + ", ".join(BLOCK_THEMES))
    leg = dict(LEGEND)
    for k, v in as_dict(a.get("legend")).items():
        if str(v) not in BLOCK_KINDS:
            raise ToolkitError(f"legend kind '{v}' unknown", "Kinds: " + ", ".join(BLOCK_KINDS))
        leg[str(k)[:1]] = str(v)
    w = max(len(r) for r in rows)
    grid = [r.ljust(w) for r in rows]
    payload = {"grid": grid, "legend": leg, "cell": num(a.get("cell"), 8, 1, 100), "wall_height": num(a.get("wall_height"), 14, 1, 200), "floor_thickness": num(a.get("floor_thickness"), 1, 0.2, 20),
               "origin": vec3(a.get("origin"), (0, 0, 0)), "theme": {k: [v[0], v[1]] for k, v in BLOCK_THEMES[theme].items()}, "theme_name": theme, "name": str(a.get("name") or "MS_Blockout"),
               "parent": a.get("parent") or "Workspace", "clear": boolean(a.get("clear_existing"), True), "dry_run": a.get("dry_run"), "studio_id": a.get("studio_id"), "mode": a.get("mode")}
    return _exec(ctx, payload, _x(_LIB_MK, '''
        local CS = game:GetService("CollectionService")
        local parent = resolve(A.parent)
        if A.clear then local o = parent:FindFirstChild(A.name); if o then o:Destroy() end end
        local root = mk("Model", {Name = A.name}, parent)
        local cell, wh, ft = A.cell, A.wall_height, A.floor_thickness
        local ox, oy, oz = A.origin[1], A.origin[2], A.origin[3]
        local H, W = #A.grid, #A.grid[1]
        local function at(r, c)
            if r < 1 or r > H or c < 1 or c > W then return " " end
            local ch = string.sub(A.grid[r], c, c)
            return A.legend[ch] or (ch == " " and "void" or "floor")
        end
        local function cx(c) return ox + (c - 0.5) * cell end
        local function cz(r) return oz + (r - 0.5) * cell end
        local function mat(name) return enumOf("Material", name, "Plastic") end
        local T = A.theme
        local counts = {}
        local function bump(k) counts[k] = (counts[k] or 0) + 1 end
        local function slab(kind, r1, c1, r2, c2, y0, h, themeKey, extra)
            local sx, sz = (c2 - c1 + 1) * cell, (r2 - r1 + 1) * cell
            local p = mk("Part", {Name = kind, Anchored = true, Size = Vector3.new(sx, h, sz), Color = hex(T[themeKey][1]), Material = mat(T[themeKey][2]),
                Position = Vector3.new(ox + (c1 - 1) * cell + sx / 2, y0 + h / 2, oz + (r1 - 1) * cell + sz / 2)}, root)
            if extra then for k, v in pairs(extra) do p[k] = v end end
            bump(kind)
            return p
        end
        -- greedy rectangle merge for a set of kinds
        local function merge(match, make)
            local used = {}
            for r = 1, H do
                for c = 1, W do
                    if match(r, c) and not used[r * 1000 + c] then
                        local c2 = c
                        while c2 + 1 <= W and match(r, c2 + 1) and not used[r * 1000 + c2 + 1] do c2 = c2 + 1 end
                        local r2 = r
                        local grow = true
                        while grow and r2 + 1 <= H do
                            for cc = c, c2 do
                                if not match(r2 + 1, cc) or used[(r2 + 1) * 1000 + cc] then grow = false break end
                            end
                            if grow then r2 = r2 + 1 end
                        end
                        for rr = r, r2 do for cc = c, c2 do used[rr * 1000 + cc] = true end end
                        make(r, c, r2, c2)
                    end
                end
            end
        end
        local solidFloor = {floor = true, spawn = true, coin = true, goal = true, door = true, pillar = true, tree = true, crate = true, checkpoint = true, enemy = true, wall = true, stairs = true, platform = true}
        merge(function(r, c) return solidFloor[at(r, c)] == true end, function(r1, c1, r2, c2)
            slab("Floor", r1, c1, r2, c2, oy - ft, ft, "floor")
        end)
        merge(function(r, c) return at(r, c) == "wall" end, function(r1, c1, r2, c2)
            slab("Wall", r1, c1, r2, c2, oy, wh, "wall")
        end)
        merge(function(r, c) return at(r, c) == "lava" end, function(r1, c1, r2, c2)
            local p = slab("Lava", r1, c1, r2, c2, oy - ft, ft, "lava")
            CS:AddTag(p, "KillBrick")
            p:SetAttribute("Damage", 100)
        end)
        merge(function(r, c) return at(r, c) == "water" end, function(r1, c1, r2, c2)
            local p = slab("Water", r1, c1, r2, c2, oy - ft * 3, ft * 3, "water", {Transparency = 0.5, CanCollide = false})
        end)
        merge(function(r, c) return at(r, c) == "platform" end, function(r1, c1, r2, c2)
            slab("Platform", r1, c1, r2, c2, oy + cell * 0.5, ft, "accent")
        end)
        local spawns, coins, goals = 0, 0, 0
        for r = 1, H do
            for c = 1, W do
                local k = at(r, c)
                local x, z = cx(c), cz(r)
                if k == "spawn" then
                    local s = mk("SpawnLocation", {Name = "Spawn", Anchored = true, Size = Vector3.new(cell * 0.8, 1, cell * 0.8), Position = Vector3.new(x, oy + 0.5, z), Neutral = true,
                        Color = hex(T.accent[1]), Material = mat("Neon"), Transparency = 0.3}, root)
                    CS:AddTag(s, "Spawn")
                    spawns = spawns + 1
                elseif k == "coin" then
                    local p = mk("Part", {Name = "Coin", Anchored = true, CanCollide = false, Shape = Enum.PartType.Cylinder, Size = Vector3.new(0.4, 3, 3), Color = hex("#ffd23f"), Material = mat("Neon"),
                        CFrame = CFrame.new(x, oy + 3, z) * CFrame.Angles(0, 0, math.rad(90))}, root)
                    CS:AddTag(p, "Coin")
                    coins = coins + 1
                elseif k == "goal" then
                    local p = mk("Part", {Name = "Goal", Anchored = true, CanCollide = false, Size = Vector3.new(cell, wh * 0.6, cell), Position = Vector3.new(x, oy + wh * 0.3, z), Color = hex("#7dff9a"),
                        Material = mat("Neon"), Transparency = 0.6}, root)
                    CS:AddTag(p, "Goal")
                    goals = goals + 1
                elseif k == "pillar" then
                    mk("Part", {Name = "Pillar", Anchored = true, Shape = Enum.PartType.Cylinder, Size = Vector3.new(wh, cell * 0.5, cell * 0.5), Color = hex(T.wall[1]), Material = mat(T.wall[2]),
                        CFrame = CFrame.new(x, oy + wh / 2, z) * CFrame.Angles(0, 0, math.rad(90))}, root)
                    bump("Pillar")
                elseif k == "tree" then
                    mk("Part", {Name = "Trunk", Anchored = true, Shape = Enum.PartType.Cylinder, Size = Vector3.new(cell * 0.9, cell * 0.25, cell * 0.25), Color = hex("#6b4a2b"), Material = mat("Wood"),
                        CFrame = CFrame.new(x, oy + cell * 0.45, z) * CFrame.Angles(0, 0, math.rad(90))}, root)
                    mk("Part", {Name = "Leaves", Anchored = true, Shape = Enum.PartType.Ball, Size = Vector3.new(cell * 1.4, cell * 1.4, cell * 1.4), Color = hex("#3f8f3a"), Material = mat("Grass"),
                        Position = Vector3.new(x, oy + cell * 1.4, z)}, root)
                    bump("Tree")
                elseif k == "crate" then
                    mk("Part", {Name = "Crate", Anchored = true, Size = Vector3.new(cell * 0.7, cell * 0.7, cell * 0.7), Color = hex(T.accent[1]), Material = mat("Wood"),
                        Position = Vector3.new(x, oy + cell * 0.35, z)}, root)
                    bump("Crate")
                elseif k == "checkpoint" then
                    local p = mk("Part", {Name = "Checkpoint", Anchored = true, Size = Vector3.new(cell * 0.8, 0.6, cell * 0.8), Position = Vector3.new(x, oy + 0.3, z), Color = hex("#4dd2ff"), Material = mat("Neon")}, root)
                    CS:AddTag(p, "Checkpoint")
                    bump("Checkpoint")
                elseif k == "enemy" then
                    local p = mk("Part", {Name = "EnemySpawn", Anchored = true, CanCollide = false, Transparency = 0.7, Size = Vector3.new(2, 2, 2), Position = Vector3.new(x, oy + 1, z), Color = hex("#ff3d3d"), Material = mat("Neon")}, root)
                    CS:AddTag(p, "EnemySpawn")
                    bump("EnemySpawn")
                elseif k == "stairs" then
                    local steps = 6
                    for i = 1, steps do
                        mk("Part", {Name = "Stair", Anchored = true, Size = Vector3.new(cell, wh / steps * 0.5, cell / steps), Color = hex(T.accent[1]), Material = mat(T.accent[2]),
                            Position = Vector3.new(x, oy + (i - 0.5) * (wh / steps) * 0.5, z - cell / 2 + (i - 0.5) * (cell / steps))}, root)
                    end
                    bump("Stairs")
                end
            end
        end
        R.model = root:GetFullName()
        R.size_cells = {W, H}
        R.size_studs = {W * cell, H * cell}
        R.parts = #root:GetChildren()
        R.counts = counts
        R.spawns, R.coins, R.goals = spawns, coins, goals
        if spawns == 0 then R.warning = "No spawn (S) in the map: players will spawn at the default location." end
        waypoint("level blockout")
    '''), "level blockout")


# ─────────────────────────────── Terrain generation ───────────────────────────────
TERRAIN_PRESETS = ["plains", "hills", "mountains", "islands", "desert", "canyon", "tundra", "volcano", "flat"]


@tool(RB, "ms_roblox_terrain_generate",
      "Generate real voxel Terrain with layered noise: plains, hills, mountains, islands (radial falloff + ocean), desert dunes, canyon (ridged), tundra, volcano (cone + crater) or flat. "
      "Surface materials follow height and slope (grass/mud/rock/snow/sand/ground/basalt), an optional water level fills basins, and a seed makes the result repeatable. Uses Terrain:FillBlock columns "
      "(resolution studs per column, 4-16) and can clear the area first.",
      {"preset": {"type": "string", "enum": TERRAIN_PRESETS}, "size": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2, "description": "[x, z] studs, default [512,512]."},
       "center": VEC, "seed": {"type": "integer"}, "amplitude": {"type": "number", "description": "Max height variation in studs (preset default)."}, "scale": {"type": "number", "description": "Noise feature size in studs."},
       "base_height": {"type": "number"}, "water_level": {"type": "number"}, "resolution": {"type": "number", "description": "Studs per column (default 8)."}, "depth": {"type": "number", "description": "Terrain thickness below base (default 24)."},
       "clear": {"type": "boolean"}, "materials": {"type": "object", "description": "Override: {low, mid, high, rock, peak, beach}"}},
      [], writes=True)
def terrain_generate(args, ctx):
    a = dict(args)
    preset = str(a.get("preset") or "hills").lower()
    if preset not in TERRAIN_PRESETS:
        raise ToolkitError(f"unknown preset '{preset}'", "Use one of: " + ", ".join(TERRAIN_PRESETS))
    size = [num(x, 512, 32, 4096) for x in (as_list(a.get("size")) or [512, 512])[:2]]
    res = num(a.get("resolution"), 8, 4, 16)
    cells = (size[0] / res) * (size[1] / res)
    if cells > 40000:
        raise ToolkitError(f"{int(cells)} columns is too many (max 40000)", "Increase `resolution` or shrink `size`.")
    payload = {"preset": preset, "size": size, "center": vec3(a.get("center"), (0, 0, 0)), "seed": int(num(a.get("seed"), 1337, -10**6, 10**6)), "amplitude": a.get("amplitude"), "scale": a.get("scale"),
               "base_height": a.get("base_height"), "water_level": a.get("water_level"), "resolution": res, "depth": num(a.get("depth"), 24, 4, 200), "clear": boolean(a.get("clear"), False),
               "materials": as_dict(a.get("materials")), "dry_run": a.get("dry_run"), "studio_id": a.get("studio_id"), "mode": a.get("mode")}
    return _exec(ctx, payload, _x(_LIB_MK, '''
        local terrain = workspace.Terrain
        local P = {
            flat      = {amp = 0,   scale = 200, base = 4,  water = -100, oct = 1},
            plains    = {amp = 10,  scale = 220, base = 6,  water = -100, oct = 3},
            hills     = {amp = 38,  scale = 160, base = 12, water = 6,    oct = 4},
            mountains = {amp = 150, scale = 220, base = 20, water = 2,    oct = 5, ridged = true},
            islands   = {amp = 32,  scale = 120, base = 10, water = 4,    oct = 4, island = true},
            desert    = {amp = 22,  scale = 110, base = 8,  water = -100, oct = 3, dunes = true},
            canyon    = {amp = 90,  scale = 180, base = 40, water = -100, oct = 4, canyon = true},
            tundra    = {amp = 28,  scale = 200, base = 10, water = 3,    oct = 4},
            volcano   = {amp = 20,  scale = 140, base = 8,  water = 3,    oct = 3, volcano = true},
        }
        local pr = P[A.preset] or P.hills
        local amp = A.amplitude or pr.amp
        local scale = A.scale or pr.scale
        local base = A.base_height or pr.base
        local water = A.water_level
        if water == nil then water = pr.water end
        local M = {
            plains = {low = "Grass", mid = "Grass", high = "Ground", rock = "Rock", peak = "Rock", beach = "Sand"},
            hills = {low = "Grass", mid = "Grass", high = "Rock", rock = "Slate", peak = "Snow", beach = "Sand"},
            mountains = {low = "Grass", mid = "Rock", high = "Slate", rock = "Rock", peak = "Snow", beach = "Ground"},
            islands = {low = "Sand", mid = "Grass", high = "Rock", rock = "Rock", peak = "Rock", beach = "Sand"},
            desert = {low = "Sand", mid = "Sand", high = "Sandstone", rock = "Sandstone", peak = "Sandstone", beach = "Sand"},
            canyon = {low = "Sand", mid = "Sandstone", high = "Sandstone", rock = "Rock", peak = "Ground", beach = "Sand"},
            tundra = {low = "Snow", mid = "Snow", high = "Glacier", rock = "Slate", peak = "Glacier", beach = "Ground"},
            volcano = {low = "Ground", mid = "Basalt", high = "Basalt", rock = "Basalt", peak = "CrackedLava", beach = "Ground"},
        }
        local mats = M[A.preset] or M.hills
        for k, v in pairs(A.materials or {}) do mats[k] = v end
        local function E(n) return enumOf("Material", mats[n], "Ground") end
        local seed = A.seed
        local function fbm(x, z)
            local v, f, a2, norm = 0, 1, 1, 0
            for o = 1, pr.oct do
                local n = math.noise(x / scale * f + seed * 0.37, z / scale * f - seed * 0.11, o * 3.7)
                if pr.ridged then n = 1 - math.abs(n) * 2 end
                v = v + n * a2
                norm = norm + a2
                f = f * 2
                a2 = a2 * 0.5
            end
            return v / norm
        end
        local sx, sz = A.size[1], A.size[2]
        local res = A.resolution
        local nx, nz = math.max(1, math.floor(sx / res)), math.max(1, math.floor(sz / res))
        local cx0, cy0, cz0 = A.center[1], A.center[2], A.center[3]
        local x0, z0 = cx0 - sx / 2, cz0 - sz / 2
        if A.clear then terrain:Clear() end
        local heights = {}
        local minh, maxh = math.huge, -math.huge
        for i = 1, nx do
            heights[i] = {}
            for j = 1, nz do
                local x, z = x0 + (i - 0.5) * res, z0 + (j - 0.5) * res
                local h = fbm(x, z)
                if pr.dunes then h = (math.abs(math.sin(x / scale * 2.4 + h * 2)) * 0.8 + h * 0.4) end
                if pr.canyon then
                    local c = math.abs(fbm(x * 0.6 + 900, z * 0.6)) 
                    h = (c < 0.12) and -1 or (0.3 + h * 0.5)
                end
                local height = base + h * amp
                local dx, dz = (x - cx0) / (sx / 2), (z - cz0) / (sz / 2)
                local d = math.sqrt(dx * dx + dz * dz)
                if pr.island then
                    local fall = math.max(0, 1 - d * d)
                    height = base - 14 + (h * 0.5 + 0.6) * amp * fall * 1.6 - (1 - fall) * 28
                end
                if pr.volcano then
                    local cone = math.max(0, 1 - d * 1.4)
                    height = height + cone * cone * 130
                    if d < 0.07 then height = height - (0.07 - d) * 900 end
                    if d > 0.85 then height = height - (d - 0.85) * 60 end
                end
                if A.preset == "flat" then height = base end
                height = cy0 + height
                heights[i][j] = height
                if height < minh then minh = height end
                if height > maxh then maxh = height end
            end
        end
        local floorY = cy0 + math.min(minh, water) - A.depth
        -- ocean/lake slab first; land overwrites it
        local filled = 0
        if water > -50 then
            local wy = cy0 + water
            local top = wy
            local h = top - floorY
            if h > 0 then
                terrain:FillBlock(CFrame.new(cx0, floorY + h / 2, cz0), Vector3.new(sx, h, sz), Enum.Material.Water)
                filled = filled + 1
            end
        end
        local waterTop = cy0 + water
        for i = 1, nx do
            for j = 1, nz do
                local h = heights[i][j]
                local x, z = x0 + (i - 0.5) * res, z0 + (j - 0.5) * res
                local slope = 0
                if i > 1 and i < nx and j > 1 and j < nz then
                    slope = math.max(math.abs(heights[i + 1][j] - heights[i - 1][j]), math.abs(heights[i][j + 1] - heights[i][j - 1])) / (2 * res)
                end
                local rel = (h - cy0 - base) / math.max(amp, 1)
                local surface
                if h < waterTop + 2 and water > -50 then surface = "beach"
                elseif slope > 0.9 then surface = "rock"
                elseif rel > 0.85 then surface = "peak"
                elseif rel > 0.5 then surface = "high"
                elseif rel > 0.1 then surface = "mid"
                else surface = "low" end
                if A.preset == "volcano" and h > cy0 + 90 then surface = "peak" end
                local thick = h - floorY
                if thick > 0.5 then
                    local under = math.max(0.5, thick - 4)
                    terrain:FillBlock(CFrame.new(x, floorY + under / 2, z), Vector3.new(res, under, res), (surface == "peak" or surface == "high") and E("rock") or Enum.Material.Ground)
                    terrain:FillBlock(CFrame.new(x, floorY + under + (thick - under) / 2, z), Vector3.new(res, thick - under, res), E(surface))
                    filled = filled + 2
                end
            end
        end
        R.preset = A.preset
        R.columns = nx * nz
        R.fill_calls = filled
        R.height_range = {minh, maxh}
        R.water_level = water > -50 and (cy0 + water) or nil
        R.bounds = {{x0, floorY, z0}, {x0 + sx, maxh, z0 + sz}}
        waypoint("terrain " .. A.preset)
    '''), "terrain " + preset, timeout=300)


# ─────────────────────────────── Scatter (props on ground via raycasts) ───────────────────────────────
PROPS = ["tree", "pine", "rock", "bush", "crystal", "mushroom", "lamp_post", "flower", "grass_tuft", "barrel"]


@tool(RB, "ms_roblox_scatter",
      "Scatter props over an area with downward raycasts so they sit on terrain/parts: your own template (a Model/BasePart path) or a built-in prop (tree, pine, rock, bush, crystal, mushroom, lamp_post, flower, grass_tuft, barrel). "
      "Controls: rectangle or circle area, count or density, minimum spacing (Poisson-style), slope limit, random yaw, scale range, align to the surface normal, skip water, seed. Everything goes into one Folder so it is easy to undo or re-roll.",
      {"source": {"type": "string", "description": "Path of a Model/BasePart to clone."}, "prop": {"type": "string", "enum": PROPS}, "center": VEC,
       "size": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}, "radius": {"type": "number", "description": "Use a circle instead of a rectangle."},
       "count": {"type": "integer"}, "min_distance": {"type": "number"}, "max_slope_degrees": {"type": "number"}, "scale_min": {"type": "number"}, "scale_max": {"type": "number"},
       "align_to_normal": {"type": "boolean"}, "random_yaw": {"type": "boolean"}, "sink": {"type": "number", "description": "Studs to bury into the ground."}, "seed": {"type": "integer"},
       "name": {"type": "string"}, "parent": {"type": "string"}, "avoid": {"type": "array", "items": {"type": "string"}, "description": "Paths of parts/models to keep clear of."}},
      [], writes=True)
def scatter(args, ctx):
    a = dict(args)
    prop = str(a.get("prop") or "").lower()
    if not a.get("source") and prop not in PROPS:
        raise ToolkitError("give `source` (template path) or `prop`", "Props: " + ", ".join(PROPS))
    payload = {"source": a.get("source"), "prop": prop, "center": vec3(a.get("center"), (0, 0, 0)), "size": [num(x, 100, 1, 4096) for x in (as_list(a.get("size")) or [100, 100])[:2]],
               "radius": a.get("radius"), "count": int(num(a.get("count"), 40, 1, 2000)), "min_distance": num(a.get("min_distance"), 6, 0, 500), "max_slope": num(a.get("max_slope_degrees"), 35, 0, 90),
               "smin": num(a.get("scale_min"), 0.8, 0.05, 50), "smax": num(a.get("scale_max"), 1.3, 0.05, 50), "align": boolean(a.get("align_to_normal"), False), "yaw": boolean(a.get("random_yaw"), True),
               "sink": num(a.get("sink"), 0.2, -50, 50), "seed": int(num(a.get("seed"), 7, -10**6, 10**6)), "name": str(a.get("name") or "MS_Scatter_" + (prop or "custom")), "parent": a.get("parent") or "Workspace",
               "avoid": [str(x) for x in as_list(a.get("avoid"))], "dry_run": a.get("dry_run"), "studio_id": a.get("studio_id"), "mode": a.get("mode")}
    return _exec(ctx, payload, _x(_LIB_MK, '''
        local parent = resolve(A.parent)
        local old = parent:FindFirstChild(A.name)
        if old then old:Destroy() end
        local folder = mk("Folder", {Name = A.name}, parent)
        local rng = Random.new(A.seed)
        local function mat(n) return enumOf("Material", n, "Plastic") end
        local function part(props, par) props.Anchored = true; props.TopSurface = nil; return mk("Part", props, par) end
        local builders = {}
        function builders.tree(m)
            part({Name = "Trunk", Size = Vector3.new(1.2, 6, 1.2), Color = hex("#6b4a2b"), Material = mat("Wood"), CFrame = CFrame.new(0, 3, 0)}, m)
            part({Name = "Leaves", Shape = Enum.PartType.Ball, Size = Vector3.new(7, 6, 7), Color = hex("#3f8f3a"), Material = mat("Grass"), CFrame = CFrame.new(0, 8, 0)}, m)
        end
        function builders.pine(m)
            part({Name = "Trunk", Size = Vector3.new(1, 4, 1), Color = hex("#5a3d24"), Material = mat("Wood"), CFrame = CFrame.new(0, 2, 0)}, m)
            for i = 1, 4 do
                part({Name = "Tier", Shape = Enum.PartType.Ball, Size = Vector3.new(7 - i * 1.4, 2.6, 7 - i * 1.4), Color = hex("#2f6f3a"), Material = mat("Grass"), CFrame = CFrame.new(0, 3 + i * 1.8, 0)}, m)
            end
        end
        function builders.rock(m)
            part({Name = "Rock", Size = Vector3.new(3 + rng:NextNumber() * 2, 2 + rng:NextNumber() * 1.5, 3 + rng:NextNumber() * 2), Color = hex("#8a8f98"), Material = mat("Slate"), CFrame = CFrame.new(0, 1, 0)}, m)
        end
        function builders.bush(m)
            part({Name = "Bush", Shape = Enum.PartType.Ball, Size = Vector3.new(3.5, 2.6, 3.5), Color = hex("#3d8a3a"), Material = mat("Grass"), CFrame = CFrame.new(0, 1.2, 0)}, m)
        end
        function builders.crystal(m)
            local c = part({Name = "Crystal", Size = Vector3.new(1.4, 4.5, 1.4), Color = hex("#5ad2ff"), Material = mat("Neon"), Transparency = 0.25, CFrame = CFrame.new(0, 2.2, 0) * CFrame.Angles(0, 0, math.rad(8))}, m)
            local l = mk("PointLight", {Color = hex("#5ad2ff"), Range = 10, Brightness = 1}, c)
        end
        function builders.mushroom(m)
            part({Name = "Stem", Size = Vector3.new(0.8, 1.6, 0.8), Color = hex("#f2ead8"), Material = mat("SmoothPlastic"), CFrame = CFrame.new(0, 0.8, 0)}, m)
            part({Name = "Cap", Shape = Enum.PartType.Ball, Size = Vector3.new(3, 1.8, 3), Color = hex("#d93a3a"), Material = mat("SmoothPlastic"), CFrame = CFrame.new(0, 1.8, 0)}, m)
        end
        function builders.lamp_post(m)
            part({Name = "Post", Size = Vector3.new(0.6, 9, 0.6), Color = hex("#2e2e36"), Material = mat("Metal"), CFrame = CFrame.new(0, 4.5, 0)}, m)
            local h = part({Name = "Lamp", Size = Vector3.new(1.4, 1.2, 1.4), Color = hex("#fff2b0"), Material = mat("Neon"), CFrame = CFrame.new(0, 9.4, 0)}, m)
            mk("PointLight", {Color = hex("#ffe6a0"), Range = 22, Brightness = 1.4}, h)
        end
        function builders.flower(m)
            part({Name = "Stem", Size = Vector3.new(0.12, 1.4, 0.12), Color = hex("#3d8a3a"), Material = mat("Grass"), CFrame = CFrame.new(0, 0.7, 0)}, m)
            local cols = {"#ff5d8f", "#ffd23f", "#ffffff", "#8f6bff"}
            part({Name = "Bloom", Shape = Enum.PartType.Ball, Size = Vector3.new(0.7, 0.5, 0.7), Color = hex(cols[rng:NextInteger(1, #cols)]), Material = mat("SmoothPlastic"), CFrame = CFrame.new(0, 1.5, 0)}, m)
        end
        function builders.grass_tuft(m)
            for i = 1, 3 do
                part({Name = "Blade", Size = Vector3.new(0.12, 1.2 + rng:NextNumber() * 0.6, 0.12), Color = hex("#4ea84a"), Material = mat("Grass"), CFrame = CFrame.new((i - 2) * 0.25, 0.7, 0) * CFrame.Angles(0, 0, math.rad((i - 2) * 12))}, m)
            end
        end
        function builders.barrel(m)
            part({Name = "Barrel", Shape = Enum.PartType.Cylinder, Size = Vector3.new(3, 2.4, 2.4), Color = hex("#8a5a2b"), Material = mat("Wood"), CFrame = CFrame.new(0, 1.5, 0) * CFrame.Angles(0, 0, math.rad(90))}, m)
        end
        local template
        if A.source then template = resolve(A.source) end
        local function spawnOne()
            if template then return template:Clone() end
            local m = Instance.new("Model")
            m.Name = A.prop
            builders[A.prop](m)
            m.WorldPivot = CFrame.new(0, 0, 0)
            return m
        end
        local exclude = {folder}
        if template then exclude[#exclude + 1] = template end
        local params = RaycastParams.new()
        params.FilterType = Enum.RaycastFilterType.Exclude
        params.FilterDescendantsInstances = exclude
        local avoid = {}
        for _, p in ipairs(A.avoid or {}) do
            local o = resolve(p)
            local cf, sz
            if o:IsA("Model") then cf, sz = o:GetBoundingBox() else cf, sz = o.CFrame, o.Size end
            avoid[#avoid + 1] = {cf.Position, math.max(sz.X, sz.Z) / 2}
        end
        local cx, cy, cz = A.center[1], A.center[2], A.center[3]
        local placed, tries, skippedWater, skippedSlope = 0, 0, 0, 0
        local pts = {}
        local cell = math.max(A.min_distance, 1)
        local grid = {}
        local function key(x, z) return math.floor(x / cell) .. ":" .. math.floor(z / cell) end
        local function farEnough(x, z)
            if A.min_distance <= 0 then return true end
            local gx, gz = math.floor(x / cell), math.floor(z / cell)
            for dx = -1, 1 do
                for dz = -1, 1 do
                    local b = grid[(gx + dx) .. ":" .. (gz + dz)]
                    if b then
                        for _, q in ipairs(b) do
                            local ddx, ddz = q[1] - x, q[2] - z
                            if ddx * ddx + ddz * ddz < A.min_distance * A.min_distance then return false end
                        end
                    end
                end
            end
            return true
        end
        local maxTries = A.count * 25
        local slopeLimit = math.cos(math.rad(A.max_slope))
        while placed < A.count and tries < maxTries do
            tries = tries + 1
            local x, z
            if A.radius then
                local ang, rr = rng:NextNumber() * math.pi * 2, math.sqrt(rng:NextNumber()) * A.radius
                x, z = cx + math.cos(ang) * rr, cz + math.sin(ang) * rr
            else
                x, z = cx + (rng:NextNumber() - 0.5) * A.size[1], cz + (rng:NextNumber() - 0.5) * A.size[2]
            end
            local blocked = false
            for _, av in ipairs(avoid) do
                local dx, dz = av[1].X - x, av[1].Z - z
                if dx * dx + dz * dz < (av[2] + A.min_distance) ^ 2 then blocked = true break end
            end
            if not blocked and farEnough(x, z) then
                local hit = workspace:Raycast(Vector3.new(x, cy + 2000, z), Vector3.new(0, -4000, 0), params)
                if hit then
                    if hit.Material == Enum.Material.Water then skippedWater = skippedWater + 1
                    elseif hit.Normal.Y < slopeLimit then skippedSlope = skippedSlope + 1
                    else
                        local inst = spawnOne()
                        local sc = A.smin + rng:NextNumber() * (A.smax - A.smin)
                        local yaw = A.yaw and rng:NextNumber() * math.pi * 2 or 0
                        local pos = hit.Position - Vector3.new(0, A.sink, 0)
                        local cf = CFrame.new(pos) * CFrame.Angles(0, yaw, 0)
                        if A.align then
                            local up = hit.Normal
                            local right = up:Cross(Vector3.new(0, 0, 1))
                            if right.Magnitude < 0.01 then right = Vector3.new(1, 0, 0) end
                            right = right.Unit
                            local look = right:Cross(up)
                            cf = CFrame.fromMatrix(pos, right, up, -look) * CFrame.Angles(0, yaw, 0)
                        end
                        inst.Parent = folder
                        if inst:IsA("Model") then
                            if inst.ScaleTo then pcall(function() inst:ScaleTo(sc) end) end
                            inst:PivotTo(cf)
                        else
                            inst.Size = inst.Size * sc
                            inst.CFrame = cf
                        end
                        if inst:IsA("Model") then for _, d in ipairs(inst:GetDescendants()) do if d:IsA("BasePart") then d.Anchored = true end end end
                        -- drop the lowest point of whatever we placed onto the surface (works for any pivot)
                        local bcf, bsize
                        if inst:IsA("Model") then bcf, bsize = inst:GetBoundingBox() else bcf, bsize = inst.CFrame, inst.Size end
                        local shift = (hit.Position.Y - A.sink) - (bcf.Position.Y - bsize.Y / 2)
                        if inst:IsA("Model") then inst:PivotTo(inst:GetPivot() + Vector3.new(0, shift, 0)) else inst.CFrame = inst.CFrame + Vector3.new(0, shift, 0) end
                        local b = grid[key(x, z)]
                        if not b then b = {}; grid[key(x, z)] = b end
                        b[#b + 1] = {x, z}
                        placed = placed + 1
                    end
                end
            end
        end
        R.folder = folder:GetFullName()
        R.placed = placed
        R.attempts = tries
        R.skipped = {water = skippedWater, slope = skippedSlope}
        if placed < A.count then R.warning = "Placed fewer than requested (area full, min_distance too large, or no ground hit)." end
        waypoint("scatter")
    '''), "scatter " + (prop or "template"))


# ─────────────────────────────── Paths: roads, fences, rails, bridges, pipes ───────────────────────────────
PATH_KINDS = ["road", "path", "fence", "rail", "bridge", "wall", "pipe", "rope", "lamp_line", "stepping_stones"]


@tool(RB, "ms_roblox_path_builder",
      "Build linear structures along a list of waypoints: road (with dashed centre line), dirt/cobble path, picket fence, railway (rails + sleepers), plank bridge with rails, wall, pipe (with joints), sagging rope, "
      "lamp line and stepping stones. Optional Catmull-Rom smoothing, snapping to the ground by raycast, width/height/spacing and colours. Segments are oriented with CFrame.lookAt so curves and slopes work.",
      {"points": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}, "description": "[[x,y,z], ...] (at least 2)."}, "kind": {"type": "string", "enum": PATH_KINDS},
       "width": {"type": "number"}, "height": {"type": "number"}, "thickness": {"type": "number"}, "spacing": {"type": "number"}, "smooth": {"type": "integer", "description": "Subdivisions per span for Catmull-Rom smoothing (0 = straight)."},
       "snap_to_ground": {"type": "boolean"}, "closed": {"type": "boolean"}, "color": {"type": ["string", "array"]}, "material": {"type": "string"}, "name": {"type": "string"}, "parent": {"type": "string"}},
      ["points", "kind"], writes=True)
def path_builder(args, ctx):
    a = dict(args)
    kind = str(a.get("kind") or "").lower()
    if kind not in PATH_KINDS:
        raise ToolkitError(f"unknown kind '{kind}'", "Use one of: " + ", ".join(PATH_KINDS))
    pts = [vec3(p) for p in as_list(a.get("points"))]
    if len(pts) < 2:
        raise ToolkitError("`points` needs at least two [x,y,z] waypoints")
    d = {"road": (14, 0.6, 0), "path": (6, 0.5, 0), "fence": (0.4, 0.3, 4), "rail": (4.5, 0.6, 2), "bridge": (8, 0.8, 4), "wall": (2, 10, 0), "pipe": (2, 0, 0), "rope": (0.25, 0, 0), "lamp_line": (1, 0, 24), "stepping_stones": (3, 0.6, 5)}[kind]
    payload = {"points": pts, "kind": kind, "width": num(a.get("width"), d[0], 0.05, 500), "height": num(a.get("height"), 4 if kind in ("fence", "bridge") else (d[1] if kind == "wall" else 4), 0.05, 500),
               "thickness": num(a.get("thickness"), d[1] or 0.5, 0.05, 100), "spacing": num(a.get("spacing"), d[2] or 4, 0.5, 500), "smooth": int(num(a.get("smooth"), 0, 0, 24)),
               "snap": boolean(a.get("snap_to_ground"), False), "closed": boolean(a.get("closed"), False), "color": a.get("color"), "material": a.get("material"),
               "name": str(a.get("name") or "MS_" + kind), "parent": a.get("parent") or "Workspace", "dry_run": a.get("dry_run"), "studio_id": a.get("studio_id"), "mode": a.get("mode")}
    return _exec(ctx, payload, _x(_LIB_MK, '''
        local parent = resolve(A.parent)
        local old = parent:FindFirstChild(A.name)
        if old then old:Destroy() end
        local model = mk("Model", {Name = A.name}, parent)
        local kind = A.kind
        local defaults = {
            road = {"#3b3d42", "Asphalt"}, path = {"#a58b62", "Ground"}, fence = {"#e8dcc2", "Wood"}, rail = {"#6e7580", "Metal"}, bridge = {"#8a5a2b", "Wood"},
            wall = {"#8a8f98", "Brick"}, pipe = {"#7c8a96", "Metal"}, rope = {"#c9b27a", "Fabric"}, lamp_line = {"#2e2e36", "Metal"}, stepping_stones = {"#8a8f98", "Slate"},
        }
        local col = A.color and col3(A.color) or hex(defaults[kind][1])
        local mat = enumOf("Material", A.material or defaults[kind][2], "Plastic")
        local params = RaycastParams.new()
        params.FilterType = Enum.RaycastFilterType.Exclude
        params.FilterDescendantsInstances = {model}
        local function ground(v)
            if not A.snap then return v end
            local hit = workspace:Raycast(Vector3.new(v.X, v.Y + 500, v.Z), Vector3.new(0, -1500, 0), params)
            if hit then return Vector3.new(v.X, hit.Position.Y, v.Z) end
            return v
        end
        -- control points
        local ctrl = {}
        for i, p in ipairs(A.points) do ctrl[i] = Vector3.new(p[1], p[2], p[3]) end
        if A.closed then ctrl[#ctrl + 1] = ctrl[1] end
        local pts = {}
        if A.smooth > 0 and #ctrl > 2 then
            local n = #ctrl
            for i = 1, n - 1 do
                local p0, p1, p2, p3 = ctrl[math.max(i - 1, 1)], ctrl[i], ctrl[i + 1], ctrl[math.min(i + 2, n)]
                for s = 0, A.smooth - 1 do
                    local t = s / A.smooth
                    local t2, t3 = t * t, t * t * t
                    local v = (p1 * 2 + (p2 - p0) * t + (p0 * 2 - p1 * 5 + p2 * 4 - p3) * t2 + (p1 * 3 - p0 - p2 * 3 + p3) * t3) * 0.5
                    pts[#pts + 1] = v
                end
            end
            pts[#pts + 1] = ctrl[n]
        else
            pts = ctrl
        end
        for i = 1, #pts do pts[i] = ground(pts[i]) end
        -- polyline helpers
        local total = 0
        local segLen = {}
        for i = 1, #pts - 1 do segLen[i] = (pts[i + 1] - pts[i]).Magnitude; total = total + segLen[i] end
        local function sample(dist)
            local acc = 0
            for i = 1, #segLen do
                if dist <= acc + segLen[i] or i == #segLen then
                    local t = segLen[i] > 0 and math.min(1, (dist - acc) / segLen[i]) or 0
                    return pts[i] + (pts[i + 1] - pts[i]) * t, (pts[i + 1] - pts[i])
                end
                acc = acc + segLen[i]
            end
            return pts[#pts], pts[#pts] - pts[#pts - 1]
        end
        local made = 0
        local function box(name, size, cf, color, material, shape)
            local p = mk("Part", {Name = name, Anchored = true, Size = size, CFrame = cf, Color = color or col, Material = material or mat, TopSurface = Enum.SurfaceType.Smooth}, model)
            if shape then p.Shape = shape end
            made = made + 1
            return p
        end
        local function segmentBox(name, a, b, w, h, lift, color, material, extra)
            local len = (b - a).Magnitude
            if len < 0.01 then return nil end
            local mid = (a + b) / 2 + Vector3.new(0, lift or 0, 0)
            local cf = CFrame.lookAt(mid, mid + (b - a))
            return box(name, Vector3.new(w, h, len + (extra or 0.05)), cf, color, material)
        end
        local width, height, th, spacing = A.width, A.height, A.thickness, A.spacing
        if kind == "road" or kind == "path" or kind == "bridge" or kind == "wall" then
            for i = 1, #pts - 1 do
                if kind == "wall" then
                    segmentBox("Wall", pts[i], pts[i + 1], width, height, height / 2, nil, nil, 0.2)
                else
                    segmentBox(kind == "road" and "Asphalt" or (kind == "bridge" and "Deck" or "Path"), pts[i], pts[i + 1], width, th, -th / 2, nil, nil, 0.3)
                end
            end
        end
        if kind == "road" then
            local d = 0
            while d + 2 < total do
                local p1, dir = sample(d)
                local p2 = sample(d + 3)
                segmentBox("Line", p1, p2, 0.4, 0.05, 0.03, hex("#f2e9c8"), enumOf("Material", "SmoothPlastic", "Plastic"), 0)
                d = d + 7
            end
        elseif kind == "bridge" then
            for _, side in ipairs({-1, 1}) do
                for i = 1, #pts - 1 do
                    local dir = (pts[i + 1] - pts[i])
                    local right = dir:Cross(Vector3.new(0, 1, 0))
                    if right.Magnitude > 0.001 then
                        right = right.Unit * (side * (width / 2 - 0.15))
                        segmentBox("Rail", pts[i] + right, pts[i + 1] + right, 0.3, 0.3, height * 0.8, nil, nil, 0.2)
                        segmentBox("RailLow", pts[i] + right, pts[i + 1] + right, 0.3, 0.3, height * 0.4, nil, nil, 0.2)
                    end
                end
            end
            local d = 0
            while d <= total do
                local p, dir = sample(d)
                if dir.Magnitude > 0.001 then
                    local right = dir:Cross(Vector3.new(0, 1, 0)).Unit
                    for _, side in ipairs({-1, 1}) do
                        local pp = p + right * (side * (width / 2 - 0.15))
                        box("Post", Vector3.new(0.5, height, 0.5), CFrame.new(pp + Vector3.new(0, height / 2, 0)))
                    end
                end
                d = d + spacing
            end
        elseif kind == "fence" then
            local d = 0
            local prev
            while d <= total + 0.01 do
                local p = sample(math.min(d, total))
                box("Post", Vector3.new(width, height, width), CFrame.new(p + Vector3.new(0, height / 2, 0)))
                if prev then
                    for _, f in ipairs({0.35, 0.78}) do
                        segmentBox("Rail", prev, p, 0.2, 0.25, height * f, nil, nil, 0)
                    end
                end
                prev = p
                d = d + spacing
            end
        elseif kind == "rail" then
            for _, side in ipairs({-1, 1}) do
                for i = 1, #pts - 1 do
                    local dir = pts[i + 1] - pts[i]
                    if dir.Magnitude > 0.001 then
                        local right = dir:Cross(Vector3.new(0, 1, 0)).Unit * (side * width / 2)
                        segmentBox("Rail", pts[i] + right, pts[i + 1] + right, 0.3, 0.4, 0.45, nil, nil, 0.1)
                    end
                end
            end
            local d = 0
            while d <= total do
                local p, dir = sample(d)
                if dir.Magnitude > 0.001 then
                    box("Sleeper", Vector3.new(width + 1.4, 0.3, 0.7), CFrame.lookAt(p + Vector3.new(0, 0.15, 0), p + dir + Vector3.new(0, 0.15, 0)), hex("#5a3d24"), enumOf("Material", "Wood", "Plastic"))
                end
                d = d + 1.8
            end
        elseif kind == "pipe" then
            for i = 1, #pts - 1 do
                local a, b = pts[i], pts[i + 1]
                local len = (b - a).Magnitude
                if len > 0.01 then
                    local mid = (a + b) / 2
                    local cf = CFrame.lookAt(mid, b) * CFrame.Angles(0, math.rad(90), 0)
                    box("Pipe", Vector3.new(len, width, width), cf, nil, nil, Enum.PartType.Cylinder)
                end
            end
            for i = 1, #pts do
                box("Joint", Vector3.new(width * 1.15, width * 1.15, width * 1.15), CFrame.new(pts[i]), nil, nil, Enum.PartType.Ball)
            end
        elseif kind == "rope" then
            local sag = math.max(1, total * 0.06)
            local steps = math.max(6, math.floor(total / 3))
            local prev
            for i = 0, steps do
                local t = i / steps
                local p = sample(t * total)
                p = p - Vector3.new(0, sag * 4 * t * (1 - t), 0)
                if prev then segmentBox("Rope", prev, p, width, width, 0, nil, nil, 0.05) end
                prev = p
            end
        elseif kind == "lamp_line" then
            local d = 0
            while d <= total + 0.01 do
                local p, dir = sample(math.min(d, total))
                box("Post", Vector3.new(0.6, 9, 0.6), CFrame.new(p + Vector3.new(0, 4.5, 0)))
                local lamp = box("Lamp", Vector3.new(1.4, 1.2, 1.4), CFrame.new(p + Vector3.new(0, 9.4, 0)), hex("#fff2b0"), enumOf("Material", "Neon", "Plastic"))
                mk("PointLight", {Color = hex("#ffe6a0"), Range = 22, Brightness = 1.4}, lamp)
                d = d + spacing
            end
        elseif kind == "stepping_stones" then
            local rng = Random.new(11)
            local d = 0
            while d <= total do
                local p = sample(math.min(d, total))
                local w = width * (0.8 + rng:NextNumber() * 0.5)
                box("Stone", Vector3.new(w, th, w), CFrame.new(p + Vector3.new((rng:NextNumber() - 0.5) * 0.8, -th / 2, (rng:NextNumber() - 0.5) * 0.8)) * CFrame.Angles(0, rng:NextNumber() * 6.28, 0), nil, nil, Enum.PartType.Cylinder)
                d = d + spacing
            end
        end
        R.model = model:GetFullName()
        R.length = total
        R.parts = made
        R.points_used = #pts
        waypoint("path " .. kind)
    '''), "path " + kind)


# ─────────────────────────────── Procedural buildings ───────────────────────────────
BUILDINGS = ["house", "cottage", "shop", "tower", "castle_keep", "barn", "watchtower", "hut"]
_BSTYLE = {
    "house": {"wall": ("#e8dcc2", "Plaster"), "trim": ("#6b4a2b", "Wood"), "roof": ("#a8452f", "Slate"), "floors": 2, "w": 22, "d": 18, "roof_t": "gable", "win": 7},
    "cottage": {"wall": ("#d8c9a3", "Brick"), "trim": ("#5a3d24", "Wood"), "roof": ("#7a5a3a", "Wood"), "floors": 1, "w": 16, "d": 14, "roof_t": "gable", "win": 6},
    "shop": {"wall": ("#c9a77a", "WoodPlanks"), "trim": ("#3b2a1a", "Wood"), "roof": ("#2e5a8a", "Slate"), "floors": 2, "w": 20, "d": 16, "roof_t": "flat", "win": 6},
    "tower": {"wall": ("#8a8f98", "Brick"), "trim": ("#4a4a52", "Cobblestone"), "roof": ("#2e3a5a", "Slate"), "floors": 5, "w": 14, "d": 14, "roof_t": "stepped", "win": 7},
    "castle_keep": {"wall": ("#9a9ca3", "Brick"), "trim": ("#5a5c63", "Cobblestone"), "roof": ("#5a5c63", "Cobblestone"), "floors": 4, "w": 34, "d": 30, "roof_t": "battlement", "win": 9},
    "barn": {"wall": ("#a83a2f", "WoodPlanks"), "trim": ("#f2ead8", "Wood"), "roof": ("#5a5c63", "Metal"), "floors": 1, "w": 30, "d": 20, "roof_t": "gable", "win": 10, "floor_h": 14},
    "watchtower": {"wall": ("#8a5a2b", "Wood"), "trim": ("#5a3d24", "Wood"), "roof": ("#6b4a2b", "Wood"), "floors": 3, "w": 10, "d": 10, "roof_t": "stepped", "win": 5},
    "hut": {"wall": ("#b58b55", "Sandstone"), "trim": ("#6b4a2b", "Wood"), "roof": ("#8a6a3a", "Grass"), "floors": 1, "w": 12, "d": 12, "roof_t": "stepped", "win": 5},
}


@tool(RB, "ms_roblox_building_generator",
      "Procedurally build a complete, enterable building as one Model: house, cottage, shop, tower, castle_keep, barn, watchtower or hut. Walls are made from segments around real door and window openings "
      "(glass panes, sills, lintels), with floors per storey, trim corners, and a gable / stepped / flat / battlement roof. Size, floors, colours, door side and rotation are adjustable; the PrimaryPart is the ground slab so PivotTo works.",
      {"kind": {"type": "string", "enum": BUILDINGS}, "position": VEC, "rotation_y": {"type": "number"}, "width": {"type": "number"}, "depth": {"type": "number"}, "floors": {"type": "integer"},
       "floor_height": {"type": "number"}, "wall_thickness": {"type": "number"}, "roof": {"type": "string", "enum": ["gable", "flat", "stepped", "battlement"]}, "door_side": {"type": "string", "enum": ["front", "back", "left", "right"]},
       "wall_color": {"type": ["string", "array"]}, "roof_color": {"type": ["string", "array"]}, "trim_color": {"type": ["string", "array"]}, "lit_windows": {"type": "boolean"}, "name": {"type": "string"}, "parent": {"type": "string"}},
      ["kind"], writes=True)
def building_generator(args, ctx):
    a = dict(args)
    kind = str(a.get("kind") or "house").lower()
    if kind not in BUILDINGS:
        raise ToolkitError(f"unknown kind '{kind}'", "Use one of: " + ", ".join(BUILDINGS))
    st = _BSTYLE[kind]
    payload = {"kind": kind, "position": vec3(a.get("position"), (0, 0, 0)), "rot": num(a.get("rotation_y"), 0, -360, 360), "w": num(a.get("width"), st["w"], 4, 400), "d": num(a.get("depth"), st["d"], 4, 400),
               "floors": int(num(a.get("floors"), st["floors"], 1, 30)), "fh": num(a.get("floor_height"), st.get("floor_h", 11), 6, 40), "wt": num(a.get("wall_thickness"), 1.2, 0.3, 6),
               "roof": str(a.get("roof") or st["roof_t"]), "door": str(a.get("door_side") or "front"), "wall": a.get("wall_color") or st["wall"][0], "roof_c": a.get("roof_color") or st["roof"][0],
               "trim": a.get("trim_color") or st["trim"][0], "style": {k: list(v) if isinstance(v, tuple) else v for k, v in st.items()}, "lit": boolean(a.get("lit_windows"), True),
               "name": str(a.get("name") or "MS_" + kind.title().replace("_", "")), "parent": a.get("parent") or "Workspace", "dry_run": a.get("dry_run"), "studio_id": a.get("studio_id"), "mode": a.get("mode")}
    return _exec(ctx, payload, _x(_LIB_MK, '''
        local parent = resolve(A.parent)
        local old = parent:FindFirstChild(A.name)
        if old then old:Destroy() end
        local model = mk("Model", {Name = A.name}, parent)
        local S = A.style
        local wallCol, trimCol, roofCol = col3(A.wall), col3(A.trim), col3(A.roof_c)
        local wallMat, trimMat, roofMat = enumOf("Material", S.wall[2], "Plastic"), enumOf("Material", S.trim[2], "Plastic"), enumOf("Material", S.roof[2], "Plastic")
        local W, D, FH, WT, floors = A.w, A.d, A.fh, A.wt, A.floors
        local parts = 0
        local origin = CFrame.new(A.position[1], A.position[2], A.position[3]) * CFrame.Angles(0, math.rad(A.rot), 0)
        local function box(name, size, lx, ly, lz, color, material, transparency, extra)
            local p = mk("Part", {Name = name, Anchored = true, Size = size, CFrame = origin * CFrame.new(lx, ly, lz), Color = color or wallCol, Material = material or wallMat,
                Transparency = transparency or 0, TopSurface = Enum.SurfaceType.Smooth}, model)
            if extra then for k, v in pairs(extra) do p[k] = v end end
            parts = parts + 1
            return p
        end
        local base = box("Foundation", Vector3.new(W + 2, 1, D + 2), 0, 0.5, 0, trimCol, trimMat)
        model.PrimaryPart = base
        -- wall: along local X (length L), thickness WT, centred at (cx, cz) with yaw handled by caller offsets
        local function wallRun(tag, length, cx, cz, alongX, openings, floorIdx)
            local y0 = 1 + (floorIdx - 1) * FH
            table.sort(openings, function(p, q) return p.c < q.c end)
            local function piece(u0, u1, yA, yB, nm, color, material, transp)
                if u1 - u0 < 0.05 or yB - yA < 0.05 then return end
                local uc, h = (u0 + u1) / 2, yB - yA
                local x, z = cx, cz
                local sx, sz = u1 - u0, WT
                if alongX then x = cx + uc else z = cz + uc; sx, sz = WT, u1 - u0 end
                box(nm, Vector3.new(sx, h, sz), x, yA + h / 2, z, color, material, transp)
            end
            local cur = -length / 2
            for _, op in ipairs(openings) do
                local a0, a1 = op.c - op.w / 2, op.c + op.w / 2
                piece(cur, a0, y0, y0 + FH, "Wall")
                piece(a0, a1, y0, y0 + op.sill, "Sill", trimCol, trimMat)
                piece(a0, a1, y0 + op.sill + op.h, y0 + FH, "Lintel", trimCol, trimMat)
                if op.glass then
                    local x, z = cx, cz
                    local sx, sz = op.w, 0.2
                    if alongX then x = cx + op.c else z = cz + op.c; sx, sz = 0.2, op.w end
                    local gl = box("Window", Vector3.new(sx, op.h, sz), x, y0 + op.sill + op.h / 2, z, hex(A.lit and "#ffe9a8" or "#9fd0f0"), enumOf("Material", A.lit and "Neon" or "Glass", "Glass"), A.lit and 0.35 or 0.5, {CanCollide = false})
                    if A.lit then mk("PointLight", {Color = hex("#ffd98a"), Range = 14, Brightness = 0.8}, gl) end
                end
                cur = a1
            end
            piece(cur, length / 2, y0, y0 + FH, "Wall")
        end
        local function openingsFor(side, length, floorIdx)
            local ops = {}
            if side == A.door and floorIdx == 1 then
                ops[#ops + 1] = {c = 0, w = 4.5, h = 7.5, sill = 0, glass = false}
            end
            local n = math.max(1, math.floor(length / S.win) - 1)
            for i = 1, n do
                local c = -length / 2 + (i * length / (n + 1))
                if not (side == A.door and floorIdx == 1 and math.abs(c) < 4.5) then
                    ops[#ops + 1] = {c = c, w = 3.2, h = 4, sill = 3.2, glass = true}
                end
            end
            return ops
        end
        for f = 1, floors do
            wallRun("front", W, 0, -D / 2 + WT / 2, true, openingsFor("front", W, f), f)
            wallRun("back", W, 0, D / 2 - WT / 2, true, openingsFor("back", W, f), f)
            wallRun("left", D - 2 * WT, -W / 2 + WT / 2, 0, false, openingsFor("left", D, f), f)
            wallRun("right", D - 2 * WT, W / 2 - WT / 2, 0, false, openingsFor("right", D, f), f)
            if f < floors then
                box("FloorSlab", Vector3.new(W - 2 * WT, 0.6, D - 2 * WT), 0, 1 + f * FH - 0.3, 0, trimCol, trimMat)
            end
        end
        -- corner trim posts
        for _, sx in ipairs({-1, 1}) do
            for _, sz in ipairs({-1, 1}) do
                box("Corner", Vector3.new(WT * 1.3, floors * FH + 0.4, WT * 1.3), sx * (W / 2 - WT * 0.1), 1 + floors * FH / 2, sz * (D / 2 - WT * 0.1), trimCol, trimMat)
            end
        end
        -- roof
        local top = 1 + floors * FH
        local roofType = A.roof
        if roofType == "gable" then
            local rise = math.max(4, D * 0.32)
            local run = D / 2 + 1
            local len = math.sqrt(run * run + rise * rise)
            local ang = math.atan2(rise, run)
            for _, side in ipairs({-1, 1}) do
                box("Roof", Vector3.new(W + 2.4, 0.8, len), 0, 0, 0, roofCol, roofMat)
                local p = model:GetChildren()[#model:GetChildren()]
                p.CFrame = origin * CFrame.new(0, top + rise / 2, side * run / 2) * CFrame.Angles(side * -ang * -1, 0, 0)
            end
            local steps = 6
            for i = 1, steps do
                local frac = 1 - (i - 0.5) / steps
                local ww = (D - 2 * WT) * frac
                for _, sx in ipairs({-1, 1}) do
                    box("Gable", Vector3.new(WT, rise / steps, ww), sx * (W / 2 - WT / 2), top + (i - 0.5) * rise / steps, 0, wallCol, wallMat)
                end
            end
            box("Ridge", Vector3.new(W + 2.6, 0.6, 1), 0, top + rise + 0.2, 0, trimCol, trimMat)
        elseif roofType == "stepped" then
            local steps = 6
            for i = 1, steps do
                local frac = 1 - (i - 1) / steps
                box("RoofStep", Vector3.new((W + 2) * frac, 1.2, (D + 2) * frac), 0, top + (i - 0.5) * 1.2, 0, roofCol, roofMat)
            end
        elseif roofType == "battlement" then
            box("Roof", Vector3.new(W + 1, 1, D + 1), 0, top + 0.5, 0, trimCol, trimMat)
            local nx, nz = math.floor((W + 1) / 4), math.floor((D + 1) / 4)
            for i = 0, nx do
                local x = -W / 2 + i * ((W) / math.max(nx, 1))
                box("Merlon", Vector3.new(2, 2.4, 1.6), x, top + 2.2, -D / 2 - 0.2, trimCol, trimMat)
                box("Merlon", Vector3.new(2, 2.4, 1.6), x, top + 2.2, D / 2 + 0.2, trimCol, trimMat)
            end
            for i = 1, nz - 1 do
                local z = -D / 2 + i * (D / math.max(nz, 1))
                box("Merlon", Vector3.new(1.6, 2.4, 2), -W / 2 - 0.2, top + 2.2, z, trimCol, trimMat)
                box("Merlon", Vector3.new(1.6, 2.4, 2), W / 2 + 0.2, top + 2.2, z, trimCol, trimMat)
            end
        else
            box("Roof", Vector3.new(W + 2, 1, D + 2), 0, top + 0.5, 0, roofCol, roofMat)
            box("Parapet", Vector3.new(W + 2, 1.6, 0.6), 0, top + 1.8, -D / 2 - 0.7, trimCol, trimMat)
            box("Parapet", Vector3.new(W + 2, 1.6, 0.6), 0, top + 1.8, D / 2 + 0.7, trimCol, trimMat)
        end
        -- door step
        local ds = {front = {0, -D / 2 - 1.5, 0}, back = {0, D / 2 + 1.5, 0}, left = {-W / 2 - 1.5, 0, 90}, right = {W / 2 + 1.5, 0, 90}}
        local d = ds[A.door] or ds.front
        if d[3] == 0 then box("Step", Vector3.new(6, 0.5, 3), d[1], 0.75, d[2], trimCol, trimMat) else box("Step", Vector3.new(3, 0.5, 6), d[1], 0.75, d[2], trimCol, trimMat) end
        local light = mk("PointLight", {Color = hex("#ffd98a"), Range = math.max(W, D), Brightness = 0.6}, base)
        R.model = model:GetFullName()
        R.parts = parts
        R.size = {W, floors * FH + 1, D}
        R.floors = floors
        R.roof = roofType
        waypoint("building " .. A.kind)
    '''), "building " + kind)


# ─────────────────────────────── Model utilities ───────────────────────────────
MODEL_OPS = ["stats", "pivot", "weld", "unweld", "array", "mirror", "align", "anchor", "group", "ungroup", "snap_to_ground", "randomize", "rename", "collision_group"]


@tool(RB, "ms_roblox_model_tools",
      "Swiss-army tool for Models/Parts. operation: stats, pivot, weld, unweld, array (linear/grid/circle), mirror, align (min/center/max/distribute), anchor, group, ungroup, snap_to_ground (raycast), randomize (yaw/scale/colour), rename, collision_group.",
      {"operation": {"type": "string", "enum": MODEL_OPS}, "targets": PATHS, "mode": {"type": "string", "description": "pivot: center|bottom|top|origin|custom; align: min|center|max|distribute"},
       "position": VEC, "count": {"type": "integer"}, "offset": VEC, "grid": {"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 3}, "spacing": VEC, "radius": {"type": "number"},
       "axis": {"type": "string", "enum": ["x", "y", "z"]}, "value": {"type": "boolean"}, "name": {"type": "string"}, "yaw": {"type": "boolean"}, "scale_min": {"type": "number"}, "scale_max": {"type": "number"},
       "color_jitter": {"type": "number"}, "seed": {"type": "integer"}, "group_name": {"type": "string"}},
      ["operation", "targets"], writes=True)
def model_tools(args, ctx):
    a = dict(args)
    op = str(a.get("operation") or "").lower()
    if op not in MODEL_OPS:
        raise ToolkitError(f"unknown operation '{op}'", "Use one of: " + ", ".join(MODEL_OPS))
    a["operation"] = op
    a["targets"] = _paths(a, "targets")
    if not a["targets"]:
        raise ToolkitError("`targets` needs at least one path")
    a["tool_mode"] = a.pop("mode", None)
    return _exec(ctx, a, _x(_LIB_MK, '''
        local op = A.operation
        local targets = {}
        for _, p in ipairs(A.targets) do targets[#targets + 1] = resolve(p) end
        local function pivotOf(i) if i:IsA("Model") then return i:GetPivot() end return i.CFrame end
        local function setPivot(i, cf) if i:IsA("Model") then i:PivotTo(cf) else i.CFrame = cf end end
        local function boundsOf(i)
            if i:IsA("Model") then return i:GetBoundingBox() end
            return i.CFrame, i.Size
        end
        local function partsOf(i)
            local out = {}
            if i:IsA("BasePart") then out[1] = i end
            for _, d in ipairs(i:GetDescendants()) do if d:IsA("BasePart") then out[#out + 1] = d end end
            return out
        end
        local axisIdx = {x = "X", y = "Y", z = "Z"}
        local changed = {}
        if op == "stats" then
            local report = {}
            for _, t in ipairs(targets) do
                local ps = partsOf(t)
                local mats, unanch, mass, tris = {}, 0, 0, 0
                for _, p in ipairs(ps) do
                    local mn = tostring(p.Material)
                    mats[mn] = (mats[mn] or 0) + 1
                    if not p.Anchored then unanch = unanch + 1 end
                    local okm, m = pcall(function() return p:GetMass() end)
                    if okm and m then mass = mass + m end
                end
                local cf, size = boundsOf(t)
                table.insert(report, {path = t:GetFullName(), class = t.ClassName, parts = #ps, unanchored = unanch, mass = mass, materials = mats, size = ser(size), center = ser(cf.Position)})
            end
            R.report = report
        elseif op == "pivot" then
            local mode = A.tool_mode or "center"
            for _, t in ipairs(targets) do
                local cf, size = boundsOf(t)
                local target
                if mode == "bottom" then target = cf * CFrame.new(0, -size.Y / 2, 0)
                elseif mode == "top" then target = cf * CFrame.new(0, size.Y / 2, 0)
                elseif mode == "origin" then target = CFrame.new(0, 0, 0)
                elseif mode == "custom" and A.position then target = CFrame.new(A.position[1], A.position[2], A.position[3])
                else target = cf end
                if t:IsA("Model") then t.WorldPivot = target else t.PivotOffset = pivotOf(t):ToObjectSpace(target) end
                table.insert(changed, t:GetFullName())
            end
        elseif op == "weld" or op == "unweld" then
            local n = 0
            for _, t in ipairs(targets) do
                local ps = partsOf(t)
                local root = (t:IsA("Model") and t.PrimaryPart) or ps[1]
                for _, p in ipairs(ps) do
                    if op == "weld" and p ~= root then
                        local w = Instance.new("WeldConstraint")
                        w.Name = "MS_Weld"
                        w.Part0 = root
                        w.Part1 = p
                        w.Parent = p
                        n = n + 1
                    elseif op == "unweld" then
                        for _, c in ipairs(p:GetChildren()) do if c:IsA("WeldConstraint") and c.Name == "MS_Weld" then c:Destroy(); n = n + 1 end end
                    end
                end
                if op == "weld" then for _, p in ipairs(ps) do p.Anchored = false end; if root then root.Anchored = A.value == true end end
            end
            R.welds = n
        elseif op == "array" then
            local made = {}
            local src = targets[1]
            local base = pivotOf(src)
            local function put(cf, idx)
                local c = src:Clone()
                c.Name = (A.name or src.Name) .. "_" .. idx
                c.Parent = src.Parent
                setPivot(c, cf)
                made[#made + 1] = c:GetFullName()
            end
            if A.grid then
                local sp = A.spacing or {8, 8, 8}
                local idx = 0
                for ix = 0, (A.grid[1] or 1) - 1 do
                    for iy = 0, (A.grid[2] or 1) - 1 do
                        for iz = 0, (A.grid[3] or 1) - 1 do
                            if not (ix == 0 and iy == 0 and iz == 0) then
                                idx = idx + 1
                                put(base * CFrame.new(ix * sp[1], iy * sp[2], iz * sp[3]), idx)
                            end
                        end
                    end
                end
            elseif A.radius then
                local n = A.count or 8
                local ax = A.axis or "y"
                for i = 1, n - 1 do
                    local ang = math.pi * 2 * i / n
                    local c = Vector3.new(math.cos(ang) * A.radius, 0, math.sin(ang) * A.radius)
                    local rot = CFrame.Angles(0, -ang, 0)
                    if ax == "x" then c = Vector3.new(0, math.cos(ang) * A.radius, math.sin(ang) * A.radius); rot = CFrame.Angles(-ang, 0, 0)
                    elseif ax == "z" then c = Vector3.new(math.cos(ang) * A.radius, math.sin(ang) * A.radius, 0); rot = CFrame.Angles(0, 0, ang) end
                    put(CFrame.new(base.Position + c - Vector3.new(A.radius, 0, 0) * (ax == "y" and 1 or 0)) * (base - base.Position) * rot, i)
                end
            else
                local off = A.offset or {8, 0, 0}
                for i = 1, (A.count or 5) - 1 do put(base * CFrame.new(off[1] * i, off[2] * i, off[3] * i), i) end
            end
            R.created = made
        elseif op == "mirror" then
            local ax = A.axis or "x"
            local made = {}
            for _, t in ipairs(targets) do
                local c = t:Clone()
                c.Name = t.Name .. "_Mirror"
                c.Parent = t.Parent
                local pos = pivotOf(t).Position
                local np = Vector3.new(ax == "x" and -pos.X or pos.X, ax == "y" and -pos.Y or pos.Y, ax == "z" and -pos.Z or pos.Z)
                setPivot(c, CFrame.new(np) * (pivotOf(t) - pivotOf(t).Position))
                made[#made + 1] = c:GetFullName()
            end
            R.created = made
        elseif op == "align" then
            local ax = axisIdx[A.axis or "x"]
            local mode = A.tool_mode or "center"
            local vals = {}
            for i, t in ipairs(targets) do
                local cf, size = boundsOf(t)
                vals[i] = {cf.Position[ax], size[ax]}
            end
            local lo, hi = math.huge, -math.huge
            for _, v in ipairs(vals) do lo = math.min(lo, v[1] - v[2] / 2); hi = math.max(hi, v[1] + v[2] / 2) end
            for i, t in ipairs(targets) do
                local pos = pivotOf(t).Position
                local nv
                if mode == "min" then nv = lo + vals[i][2] / 2
                elseif mode == "max" then nv = hi - vals[i][2] / 2
                elseif mode == "distribute" and #targets > 1 then nv = lo + vals[i][2] / 2 + (hi - lo - vals[i][2]) * (i - 1) / (#targets - 1)
                else nv = (lo + hi) / 2 end
                local np = Vector3.new(ax == "X" and nv or pos.X, ax == "Y" and nv or pos.Y, ax == "Z" and nv or pos.Z)
                setPivot(t, CFrame.new(np) * (pivotOf(t) - pivotOf(t).Position))
                table.insert(changed, t:GetFullName())
            end
        elseif op == "anchor" then
            local val = A.value ~= false
            local n = 0
            for _, t in ipairs(targets) do for _, p in ipairs(partsOf(t)) do p.Anchored = val; n = n + 1 end end
            R.parts_changed = n
        elseif op == "group" then
            local m = Instance.new("Model")
            m.Name = A.group_name or A.name or "MS_Group"
            m.Parent = targets[1].Parent
            for _, t in ipairs(targets) do t.Parent = m end
            R.group = m:GetFullName()
        elseif op == "ungroup" then
            for _, t in ipairs(targets) do
                local par = t.Parent
                for _, c in ipairs(t:GetChildren()) do c.Parent = par end
                t:Destroy()
            end
        elseif op == "snap_to_ground" then
            local params = RaycastParams.new()
            params.FilterType = Enum.RaycastFilterType.Exclude
            params.FilterDescendantsInstances = targets
            for _, t in ipairs(targets) do
                local cf, size = boundsOf(t)
                local hit = workspace:Raycast(cf.Position + Vector3.new(0, 1000, 0), Vector3.new(0, -3000, 0), params)
                if hit then
                    local bottom = cf.Position.Y - size.Y / 2
                    setPivot(t, pivotOf(t) + Vector3.new(0, hit.Position.Y - bottom, 0))
                    table.insert(changed, t:GetFullName())
                end
            end
        elseif op == "randomize" then
            local rng = Random.new(A.seed or 1)
            for _, t in ipairs(targets) do
                local pos = pivotOf(t).Position
                if A.yaw ~= false then setPivot(t, CFrame.new(pos) * CFrame.Angles(0, rng:NextNumber() * math.pi * 2, 0)) end
                if A.scale_min and t:IsA("Model") then pcall(function() t:ScaleTo(A.scale_min + rng:NextNumber() * ((A.scale_max or A.scale_min) - A.scale_min)) end) end
                if A.color_jitter then
                    for _, p in ipairs(partsOf(t)) do
                        local j = (rng:NextNumber() - 0.5) * A.color_jitter
                        local c = p.Color
                        p.Color = Color3.new(math.clamp(c.R + j, 0, 1), math.clamp(c.G + j, 0, 1), math.clamp(c.B + j, 0, 1))
                    end
                end
                table.insert(changed, t:GetFullName())
            end
        elseif op == "rename" then
            for i, t in ipairs(targets) do t.Name = (A.name or "Item") .. "_" .. i; table.insert(changed, t:GetFullName()) end
        elseif op == "collision_group" then
            local PS = game:GetService("PhysicsService")
            local gname = A.name or "MSGroup"
            pcall(function() PS:RegisterCollisionGroup(gname) end)
            for _, t in ipairs(targets) do for _, p in ipairs(partsOf(t)) do p.CollisionGroup = gname end end
            R.group = gname
        end
        R.operation = op
        if #changed > 0 then R.changed = changed end
        waypoint("model " .. op)
    '''), "model tools " + op)


# ─────────────────────────────── Constraint / mechanism presets ───────────────────────────────
MECHS = ["hinge_door", "sliding_door", "elevator", "spinner", "pendulum", "swing", "spring_pad", "conveyor", "car"]


@tool(RB, "ms_roblox_constraint_preset",
      "Rig mechanisms with modern constraints: hinge_door, sliding_door, elevator (prismatic servo + control script), spinner (motor), pendulum, swing (ropes), spring_pad, conveyor, car (4 motor wheels + VehicleSeat + driving script). Creates attachments, constraints and invisible anchored frames.",
      {"preset": {"type": "string", "enum": MECHS}, "target": PATH, "axis": {"type": "string", "enum": ["x", "y", "z"]}, "distance": {"type": "number", "description": "Travel (studs) / swing length."},
       "degrees": {"type": "number"}, "speed": {"type": "number"}, "position": VEC, "side": {"type": "string", "enum": ["left", "right", "top", "bottom", "front", "back"]}, "name": {"type": "string"}, "parent": {"type": "string"}},
      ["preset"], writes=True)
def constraint_preset(args, ctx):
    a = dict(args)
    preset = str(a.get("preset") or "").lower()
    if preset not in MECHS:
        raise ToolkitError(f"unknown preset '{preset}'", "Use one of: " + ", ".join(MECHS))
    if preset != "car" and not a.get("target"):
        raise ToolkitError(f"{preset} needs `target` (the moving part)")
    a["preset"] = preset
    a["car_src"] = _CAR_SRC
    a["lift_src"] = _LIFT_SRC
    return _exec(ctx, a, _x(_LIB_MK, '''
        local P = A.preset
        local name = A.name or ("MS_" .. P)
        local parent = A.parent and resolve(A.parent) or workspace
        local tgt = A.target and resolve(A.target) or nil
        local function frame(pos, size)
            return mk("Part", {Name = name .. "_Frame", Anchored = true, CanCollide = false, CanQuery = false, Transparency = 1, Size = size or Vector3.new(1, 1, 1), CFrame = pos}, parent)
        end
        local function att(part, cf, nm) return mk("Attachment", {Name = nm, CFrame = cf}, part) end
        local ax = A.axis or "y"
        local axisVec = ax == "x" and Vector3.new(1, 0, 0) or (ax == "z" and Vector3.new(0, 0, 1) or Vector3.new(0, 1, 0))
        R.preset = P
        if P == "hinge_door" then
            local side = A.side or "left"
            local half = tgt.Size.X / 2
            local sx = (side == "right") and half or -half
            local hingeWorld = tgt.CFrame * CFrame.new(sx, 0, 0)
            local fr = frame(hingeWorld)
            local a0 = att(fr, CFrame.new(), name .. "_A0")
            local a1 = att(tgt, CFrame.new(sx, 0, 0), name .. "_A1")
            a0.Orientation = Vector3.new(0, 0, 90)
            a1.Orientation = Vector3.new(0, 0, 90)
            tgt.Anchored = false
            local h = mk("HingeConstraint", {Name = name, Attachment0 = a0, Attachment1 = a1, LimitsEnabled = true, LowerAngle = -(A.degrees or 100), UpperAngle = 0}, tgt)
            R.constraint = h:GetFullName()
            R.note = "The door swings freely; add ms_roblox_gameplay_kit proximity_door for a prompt-controlled one."
        elseif P == "sliding_door" or P == "elevator" then
            local dist = A.distance or (P == "elevator" and 30 or 8)
            local dir = P == "elevator" and Vector3.new(0, 1, 0) or ((ax == "z") and Vector3.new(0, 0, 1) or Vector3.new(1, 0, 0))
            local fr = frame(tgt.CFrame)
            local a0 = att(fr, CFrame.new(), name .. "_A0")
            local a1 = att(tgt, CFrame.new(), name .. "_A1")
            -- Prismatic slides along the attachment X axis: rotate so X -> dir
            local rot = CFrame.lookAt(Vector3.new(), dir) * CFrame.Angles(0, math.rad(90), 0)
            a0.CFrame = rot
            a1.CFrame = rot
            tgt.Anchored = false
            local pc = mk("PrismaticConstraint", {Name = name, Attachment0 = a0, Attachment1 = a1, ActuatorType = Enum.ActuatorType.Servo, LimitsEnabled = true,
                LowerLimit = 0, UpperLimit = dist, ServoMaxForce = 1e6, Speed = A.speed or 6, TargetPosition = 0}, tgt)
            pc.Restitution = 0
            tgt:SetAttribute("MS_Travel", dist)
            local s = mk("Script", {Name = name .. "_Control", Source = A.lift_src}, tgt)
            R.constraint = pc:GetFullName()
            R.control_script = s:GetFullName()
            R.note = "Set the prismatic TargetPosition (0.." .. dist .. ") from any script, or use the generated control which toggles on a ProximityPrompt/Touched."
        elseif P == "spinner" then
            tgt.Anchored = false
            local fr = frame(tgt.CFrame)
            local rot = CFrame.lookAt(Vector3.new(), axisVec) * CFrame.Angles(0, math.rad(90), 0)
            local a0 = att(fr, rot, name .. "_A0")
            local a1 = att(tgt, rot, name .. "_A1")
            local h = mk("HingeConstraint", {Name = name, Attachment0 = a0, Attachment1 = a1, ActuatorType = Enum.ActuatorType.Motor, AngularVelocity = math.rad(A.speed or 90), MotorMaxTorque = 1e7}, tgt)
            R.constraint = h:GetFullName()
        elseif P == "pendulum" then
            tgt.Anchored = false
            local len = A.distance or 10
            local topPos = tgt.CFrame * CFrame.new(0, len, 0)
            local fr = frame(topPos)
            local a0 = att(fr, CFrame.Angles(0, math.rad(90), 0), name .. "_A0")
            local a1 = att(tgt, CFrame.new(0, len, 0) * CFrame.Angles(0, math.rad(90), 0), name .. "_A1")
            local h = mk("HingeConstraint", {Name = name, Attachment0 = a0, Attachment1 = a1}, tgt)
            tgt.CFrame = fr.CFrame * CFrame.Angles(0, 0, math.rad(A.degrees or 40)) * CFrame.new(0, -len, 0)
            R.constraint = h:GetFullName()
        elseif P == "swing" then
            tgt.Anchored = false
            local len = A.distance or 8
            local beam = frame(tgt.CFrame * CFrame.new(0, len, 0), Vector3.new(tgt.Size.X + 2, 1, 1))
            for i, sx in ipairs({-1, 1}) do
                local a0 = att(beam, CFrame.new(sx * tgt.Size.X / 2, 0, 0), name .. "_Top" .. i)
                local a1 = att(tgt, CFrame.new(sx * tgt.Size.X / 2, tgt.Size.Y / 2, 0), name .. "_Seat" .. i)
                mk("RopeConstraint", {Name = name .. "_Rope" .. i, Attachment0 = a0, Attachment1 = a1, Length = len - tgt.Size.Y / 2, Visible = true, Thickness = 0.15}, tgt)
            end
            R.note = "Push the seat to swing; add a Seat/VehicleSeat on top for riders."
        elseif P == "spring_pad" then
            tgt.Anchored = false
            local fr = frame(tgt.CFrame * CFrame.new(0, -tgt.Size.Y / 2 - 2, 0), Vector3.new(tgt.Size.X, 1, tgt.Size.Z))
            local a0 = att(fr, CFrame.new(), name .. "_A0")
            local a1 = att(tgt, CFrame.new(0, -tgt.Size.Y / 2, 0), name .. "_A1")
            local sp = mk("SpringConstraint", {Name = name, Attachment0 = a0, Attachment1 = a1, FreeLength = 2, Stiffness = 4000, Damping = 60, LimitsEnabled = true, MinLength = 0.5, MaxLength = 3.5}, tgt)
            local pr = mk("PrismaticConstraint", {Name = name .. "_Guide", Attachment0 = a0, Attachment1 = a1}, tgt)
            a0.Orientation = Vector3.new(0, 0, 90)
            a1.Orientation = Vector3.new(0, 0, 90)
            R.constraint = sp:GetFullName()
        elseif P == "conveyor" then
            tgt.Anchored = true
            local dir = tgt.CFrame.LookVector
            if ax == "x" then dir = tgt.CFrame.RightVector elseif ax == "y" then dir = tgt.CFrame.UpVector end
            tgt.AssemblyLinearVelocity = dir * (A.speed or 12)
            tgt:SetAttribute("MS_ConveyorSpeed", A.speed or 12)
            R.note = "Anchored parts with AssemblyLinearVelocity push anything standing on them."
        elseif P == "car" then
            local pos = A.position or {0, 6, 0}
            local origin = CFrame.new(pos[1], pos[2], pos[3])
            local model = mk("Model", {Name = name}, parent)
            local body = mk("Part", {Name = "Chassis", Size = Vector3.new(8, 1.2, 14), CFrame = origin, Color = hex("#d93a3a"), Material = enumOf("Material", "Metal", "Plastic")}, model)
            model.PrimaryPart = body
            mk("Part", {Name = "Cabin", Size = Vector3.new(6, 2.4, 6), CFrame = origin * CFrame.new(0, 1.8, 0.5), Color = hex("#2a2f3a"), Material = enumOf("Material", "Glass", "Plastic"), Transparency = 0.3, CanCollide = false}, model)
            local seat = mk("VehicleSeat", {Name = "DriverSeat", Size = Vector3.new(2, 1, 2), CFrame = origin * CFrame.new(0, 1.1, 1), MaxSpeed = A.speed or 60, Torque = 40, TurnSpeed = 2}, model)
            local sw = mk("WeldConstraint", {Part0 = body, Part1 = seat}, seat)
            local wheels = {}
            local spots = {{-4.6, -0.4, -4.5, "FL", true}, {4.6, -0.4, -4.5, "FR", true}, {-4.6, -0.4, 4.5, "RL", false}, {4.6, -0.4, 4.5, "RR", false}}
            for _, s in ipairs(spots) do
                local w = mk("Part", {Name = "Wheel" .. s[4], Shape = Enum.PartType.Cylinder, Size = Vector3.new(1.4, 3.2, 3.2), CFrame = origin * CFrame.new(s[1], s[2], s[3]), Color = hex("#1e1e22"), Material = enumOf("Material", "Rubber", "Plastic")}, model)
                w.CustomPhysicalProperties = PhysicalProperties.new(1, 1.4, 0, 1, 1)
                local a0 = att(body, CFrame.new(s[1], s[2], s[3]), "Mount" .. s[4])
                local a1 = att(w, CFrame.new(), "Hub" .. s[4])
                if s[1] < 0 then a0.Orientation = Vector3.new(0, 180, 0) end
                local h = mk("HingeConstraint", {Name = "Axle" .. s[4], Attachment0 = a0, Attachment1 = a1, ActuatorType = Enum.ActuatorType.Motor, MotorMaxTorque = 12000, AngularVelocity = 0}, w)
                                wheels[#wheels + 1] = w
            end
            local sc = mk("Script", {Name = "DriveScript", Source = A.car_src}, model)
            R.model = model:GetFullName()
            R.note = "Sit on DriverSeat and use W/A/S/D. Tune MaxSpeed/Torque on the seat."
        end
        waypoint("constraint " .. P)
    '''), "constraint preset " + preset)


_LIFT_SRC = '''-- Generated by Multi-Script: toggles this mechanism between 0 and MS_Travel.
local part = script.Parent
local pc = part:FindFirstChildWhichIsA("PrismaticConstraint")
local travel = part:GetAttribute("MS_Travel") or 8
local open = false
local function toggle() open = not open; pc.TargetPosition = open and travel or 0 end
local prompt = part:FindFirstChildOfClass("ProximityPrompt") or Instance.new("ProximityPrompt")
prompt.ActionText = "Use"
prompt.Parent = part
prompt.Triggered:Connect(toggle)
'''

_CAR_SRC = '''-- Generated by Multi-Script: drives the four wheel motors from the VehicleSeat (differential steering).
local model = script.Parent
local seat = model:WaitForChild("DriverSeat")
local RunService = game:GetService("RunService")
local wheels = {}
for _, d in ipairs(model:GetDescendants()) do
    if d:IsA("HingeConstraint") then
        d.ActuatorType = Enum.ActuatorType.Motor
        local left = d.Attachment0 and d.Attachment0.Position.X < 0
        wheels[#wheels + 1] = {motor = d, left = left}
    end
end
local RADIUS = 1.6
RunService.Heartbeat:Connect(function()
    local throttle, steer = seat.ThrottleFloat, seat.SteerFloat
    local base = seat.MaxSpeed / RADIUS
    for _, w in ipairs(wheels) do
        local side = w.left and 1 or -1
        -- left-side hinges spin the opposite way, steer slows the inside wheels
        local v = throttle * base * (1 - (w.left and -steer or steer) * 0.6 * (throttle >= 0 and 1 or -1))
        if throttle == 0 then v = (w.left and steer or -steer) * base * 0.35 end
        w.motor.AngularVelocity = -side * v
    end
end)
'''


# ─────────────────────────────── Gameplay kit (tag-driven server scripts) ───────────────────────────────
_GP_COMMON = '''local Players = game:GetService("Players")
local CS = game:GetService("CollectionService")
local TweenService = game:GetService("TweenService")
local RunService = game:GetService("RunService")
local function onTagged(tag, fn)
    for _, i in ipairs(CS:GetTagged(tag)) do task.spawn(fn, i) end
    CS:GetInstanceAddedSignal(tag):Connect(fn)
end
local function playerFromHit(hit)
    local char = hit and hit.Parent
    local hum = char and char:FindFirstChildOfClass("Humanoid")
    if not hum or hum.Health <= 0 then return nil end
    return Players:GetPlayerFromCharacter(char), hum, char
end
local function ensureStat(player, name, initial)
    local ls = player:FindFirstChild("leaderstats")
    if not ls then ls = Instance.new("Folder"); ls.Name = "leaderstats"; ls.Parent = player end
    local v = ls:FindFirstChild(name)
    if not v then v = Instance.new("IntValue"); v.Name = name; v.Value = initial or 0; v.Parent = ls end
    return v
end
'''

_GP = {}
_GP["leaderstats"] = ("Script", "ServerScriptService", None, '''local STATS = @stats@
Players.PlayerAdded:Connect(function(p)
    for _, s in ipairs(STATS) do ensureStat(p, s, 0) end
end)
for _, p in ipairs(Players:GetPlayers()) do for _, s in ipairs(STATS) do ensureStat(p, s, 0) end end
''')
_GP["checkpoint"] = ("Script", "ServerScriptService", "Checkpoint", '''-- Tag a part "Checkpoint" (the level blockout does this for K cells). Touching it sets your respawn point.
local last = {}
local function setup(part)
    part.Touched:Connect(function(hit)
        local plr = playerFromHit(hit)
        if plr and last[plr] ~= part then
            last[plr] = part
            ensureStat(plr, "Stage", 0).Value = (part:GetAttribute("Stage") or ensureStat(plr, "Stage", 0).Value + 1)
            part.Color = Color3.fromRGB(125, 255, 154)
        end
    end)
end
onTagged("Checkpoint", setup)
local function spawnAt(plr, char)
    local part = last[plr]
    if part then
        local hrp = char:WaitForChild("HumanoidRootPart", 5)
        if hrp then task.wait(0.1); char:PivotTo(part.CFrame * CFrame.new(0, part.Size.Y / 2 + 3.5, 0)) end
    end
end
Players.PlayerAdded:Connect(function(plr) plr.CharacterAdded:Connect(function(c) spawnAt(plr, c) end) end)
for _, plr in ipairs(Players:GetPlayers()) do plr.CharacterAdded:Connect(function(c) spawnAt(plr, c) end) end
Players.PlayerRemoving:Connect(function(p) last[p] = nil end)
''')
_GP["kill_brick"] = ("Script", "ServerScriptService", "KillBrick", '''-- Parts tagged "KillBrick" hurt on touch. Optional attribute Damage (default @damage@).
onTagged("KillBrick", function(part)
    local debounce = {}
    part.Touched:Connect(function(hit)
        local plr, hum = playerFromHit(hit)
        if hum and not debounce[hum] then
            debounce[hum] = true
            hum:TakeDamage(part:GetAttribute("Damage") or @damage@)
            task.delay(0.5, function() debounce[hum] = nil end)
        end
    end)
end)
''')
_GP["coins"] = ("Script", "ServerScriptService", "Coin", '''-- Parts tagged "Coin" are collectable. Value attribute (default 1), respawn after @respawn@ seconds (0 = never).
onTagged("Coin", function(coin)
    local home = coin.CFrame
    local active = true
    coin.Touched:Connect(function(hit)
        local plr = playerFromHit(hit)
        if plr and active then
            active = false
            ensureStat(plr, "Coins", 0).Value += (coin:GetAttribute("Value") or 1)
            coin.Transparency = 1
            coin.CanTouch = false
            if @respawn@ > 0 then
                task.delay(@respawn@, function() coin.Transparency = 0; coin.CanTouch = true; active = true end)
            else
                coin:Destroy()
            end
        end
    end)
    local t = math.random() * 6
    RunService.Heartbeat:Connect(function(dt)
        if coin.Parent and active then t += dt; coin.CFrame = home * CFrame.Angles(0, t * 2.2, 0) * CFrame.new(0, math.sin(t * 2) * 0.4, 0) end
    end)
end)
''')
_GP["jump_pad"] = ("Script", "ServerScriptService", "JumpPad", '''-- Parts tagged "JumpPad" launch players. Attribute Power (default @power@).
onTagged("JumpPad", function(pad)
    local cd = {}
    pad.Touched:Connect(function(hit)
        local plr, hum, char = playerFromHit(hit)
        local hrp = char and char:FindFirstChild("HumanoidRootPart")
        if hrp and not cd[char] then
            cd[char] = true
            local v = hrp.AssemblyLinearVelocity
            hrp.AssemblyLinearVelocity = Vector3.new(v.X, pad:GetAttribute("Power") or @power@, v.Z)
            task.delay(0.4, function() cd[char] = nil end)
        end
    end)
end)
''')
_GP["speed_boost"] = ("Script", "ServerScriptService", "SpeedPad", '''-- Parts tagged "SpeedPad" give a temporary WalkSpeed boost (attributes Speed=@speed@, Seconds=@seconds@).
onTagged("SpeedPad", function(pad)
    pad.Touched:Connect(function(hit)
        local plr, hum = playerFromHit(hit)
        if hum and not hum:GetAttribute("MS_Boost") then
            hum:SetAttribute("MS_Boost", true)
            local old = hum.WalkSpeed
            hum.WalkSpeed = pad:GetAttribute("Speed") or @speed@
            task.delay(pad:GetAttribute("Seconds") or @seconds@, function() if hum.Parent then hum.WalkSpeed = old; hum:SetAttribute("MS_Boost", nil) end end)
        end
    end)
end)
''')
_GP["teleporter"] = ("Script", "ServerScriptService", "Teleporter", '''-- Tag two parts "Teleporter" and give each attribute Target = the Name of the other. Cooldown @cooldown@s.
onTagged("Teleporter", function(pad)
    pad.Touched:Connect(function(hit)
        local plr, hum, char = playerFromHit(hit)
        if not char or char:GetAttribute("MS_TP") then return end
        local targetName = pad:GetAttribute("Target")
        local dest
        for _, other in ipairs(CS:GetTagged("Teleporter")) do if other ~= pad and (targetName == nil or other.Name == targetName) then dest = other break end end
        if dest then
            char:SetAttribute("MS_TP", true)
            char:PivotTo(dest.CFrame * CFrame.new(0, dest.Size.Y / 2 + 3.5, 0))
            task.delay(@cooldown@, function() char:SetAttribute("MS_TP", nil) end)
        end
    end)
end)
''')
_GP["health_pickup"] = ("Script", "ServerScriptService", "HealthPickup", '''onTagged("HealthPickup", function(p)
    local ready = true
    p.Touched:Connect(function(hit)
        local plr, hum = playerFromHit(hit)
        if hum and ready and hum.Health < hum.MaxHealth then
            ready = false
            hum.Health = math.min(hum.MaxHealth, hum.Health + (p:GetAttribute("Heal") or @heal@))
            p.Transparency = 1
            task.delay(@respawn@, function() p.Transparency = 0; ready = true end)
        end
    end)
end)
''')
_GP["damage_zone"] = ("Script", "ServerScriptService", "DamageZone", '''-- Parts tagged "DamageZone" hurt anyone inside (attribute DPS, default @dps@).
onTagged("DamageZone", function(zone)
    while zone.Parent do
        for _, part in ipairs(workspace:GetPartsInPart(zone)) do
            local plr, hum = playerFromHit(part)
            if hum then hum:TakeDamage((zone:GetAttribute("DPS") or @dps@) * 0.5) end
        end
        task.wait(0.5)
    end
end)
''')
_GP["goal"] = ("Script", "ServerScriptService", "Goal", '''-- Touching a part tagged "Goal" awards a Win and respawns the player.
onTagged("Goal", function(goal)
    local cd = {}
    goal.Touched:Connect(function(hit)
        local plr, hum = playerFromHit(hit)
        if plr and not cd[plr] then
            cd[plr] = true
            ensureStat(plr, "Wins", 0).Value += 1
            plr:SetAttribute("MS_Finished", os.time())
            task.wait(1.5)
            plr:LoadCharacter()
            cd[plr] = nil
        end
    end)
end)
''')
_GP["auto_door"] = ("Script", "ServerScriptService", "AutoDoor", '''-- Parts tagged "AutoDoor" slide up (attribute Lift, default @lift@) when a player is within @range@ studs.
onTagged("AutoDoor", function(door)
    local closed = door.CFrame
    local open = closed * CFrame.new(0, door:GetAttribute("Lift") or @lift@, 0)
    local state = false
    while door.Parent do
        local near = false
        for _, plr in ipairs(Players:GetPlayers()) do
            local hrp = plr.Character and plr.Character:FindFirstChild("HumanoidRootPart")
            if hrp and (hrp.Position - closed.Position).Magnitude < @range@ then near = true break end
        end
        if near ~= state then
            state = near
            TweenService:Create(door, TweenInfo.new(0.6, Enum.EasingStyle.Quad), {CFrame = state and open or closed}):Play()
        end
        task.wait(0.2)
    end
end)
''')
_GP["moving_platform"] = ("Script", "ServerScriptService", "MovingPlatform", '''-- Parts tagged "MovingPlatform": attributes OffsetX/OffsetY/OffsetZ (studs), Duration (s), Wait (s).
onTagged("MovingPlatform", function(p)
    local a = p.CFrame
    local off = Vector3.new(p:GetAttribute("OffsetX") or 0, p:GetAttribute("OffsetY") or 0, p:GetAttribute("OffsetZ") or @dz@)
    local b = a + off
    local info = TweenInfo.new(p:GetAttribute("Duration") or @duration@, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut)
    while p.Parent do
        local t1 = TweenService:Create(p, info, {CFrame = b}); t1:Play(); t1.Completed:Wait()
        task.wait(p:GetAttribute("Wait") or 0.5)
        local t2 = TweenService:Create(p, info, {CFrame = a}); t2:Play(); t2.Completed:Wait()
        task.wait(p:GetAttribute("Wait") or 0.5)
    end
end)
''')
_GP["tool_giver"] = ("Script", "ServerScriptService", None, '''-- Gives every tool inside ServerStorage.@folder@ to each player on spawn.
local SS = game:GetService("ServerStorage")
local folder = SS:FindFirstChild("@folder@")
local function give(plr)
    if not folder then return end
    for _, tool in ipairs(folder:GetChildren()) do
        if tool:IsA("Tool") and not plr.Backpack:FindFirstChild(tool.Name) then tool:Clone().Parent = plr.Backpack end
    end
end
Players.PlayerAdded:Connect(function(plr) plr.CharacterAdded:Connect(function() give(plr) end) end)
for _, plr in ipairs(Players:GetPlayers()) do plr.CharacterAdded:Connect(function() give(plr) end); give(plr) end
''')
_GP["round_system"] = ("Script", "ServerScriptService", None, '''-- Lobby -> intermission -> round loop. Put parts tagged "ArenaSpawn" in the arena; "LobbySpawn" optional.
local RS = game:GetService("ReplicatedStorage")
local state = RS:FindFirstChild("RoundState") or Instance.new("StringValue"); state.Name = "RoundState"; state.Parent = RS
local timer = RS:FindFirstChild("RoundTimer") or Instance.new("IntValue"); timer.Name = "RoundTimer"; timer.Parent = RS
local INTERMISSION, ROUND, MIN_PLAYERS = @intermission@, @round@, @min_players@
local function tp(list, tag)
    local spots = CS:GetTagged(tag)
    if #spots == 0 then return end
    for i, plr in ipairs(list) do
        local char = plr.Character
        local spot = spots[(i - 1) % #spots + 1]
        if char then char:PivotTo(spot.CFrame * CFrame.new(0, spot.Size.Y / 2 + 4, 0)) end
    end
end
while true do
    state.Value = "Waiting for players"
    repeat task.wait(1) until #Players:GetPlayers() >= MIN_PLAYERS
    for t = INTERMISSION, 1, -1 do state.Value = "Intermission"; timer.Value = t; task.wait(1) end
    local contestants = Players:GetPlayers()
    tp(contestants, "ArenaSpawn")
    local alive = #contestants
    for _, plr in ipairs(contestants) do
        local hum = plr.Character and plr.Character:FindFirstChildOfClass("Humanoid")
        if hum then hum.Died:Connect(function() alive -= 1 end) end
    end
    for t = ROUND, 1, -1 do
        state.Value = "Round in progress"; timer.Value = t
        if alive <= 1 and #contestants > 1 then break end
        task.wait(1)
    end
    state.Value = "Round over"; timer.Value = 0
    task.wait(4)
    for _, plr in ipairs(Players:GetPlayers()) do plr:LoadCharacter() end
    tp(Players:GetPlayers(), "LobbySpawn")
end
''')
_GP["spawn_protection"] = ("Script", "ServerScriptService", None, '''Players.PlayerAdded:Connect(function(plr)
    plr.CharacterAdded:Connect(function(char)
        local ff = Instance.new("ForceField"); ff.Visible = true; ff.Parent = char
        task.delay(@seconds@, function() if ff.Parent then ff:Destroy() end end)
    end)
end)
''')
_GP["day_night"] = ("Script", "ServerScriptService", None, '''local Lighting = game:GetService("Lighting")
local DAY_SECONDS = @day_seconds@
Lighting.ClockTime = @start_hour@
RunService.Heartbeat:Connect(function(dt)
    Lighting.ClockTime = (Lighting.ClockTime + dt * 24 / DAY_SECONDS) % 24
end)
''')
_GP["npc_patrol"] = ("Script", "ServerScriptService", None, '''-- Moves every Model tagged "PatrolNPC" (needs a Humanoid) through parts tagged "PatrolPoint" using PathfindingService.
local PFS = game:GetService("PathfindingService")
onTagged("PatrolNPC", function(npc)
    local hum = npc:FindFirstChildOfClass("Humanoid")
    local hrp = npc:FindFirstChild("HumanoidRootPart")
    if not hum or not hrp then return end
    hum.WalkSpeed = @speed@
    local i = 0
    while npc.Parent and hum.Health > 0 do
        local points = CS:GetTagged("PatrolPoint")
        if #points == 0 then task.wait(1) else
            i = i % #points + 1
            local path = PFS:CreatePath({AgentRadius = 2, AgentHeight = 5, AgentCanJump = true})
            local ok = pcall(function() path:ComputeAsync(hrp.Position, points[i].Position) end)
            if ok and path.Status == Enum.PathStatus.Success then
                for _, wp in ipairs(path:GetWaypoints()) do
                    if wp.Action == Enum.PathWaypointAction.Jump then hum.Jump = true end
                    hum:MoveTo(wp.Position)
                    hum.MoveToFinished:Wait()
                end
            end
            task.wait(@pause@)
        end
    end
end)
''')
_GP["sprint"] = ("LocalScript", "StarterPlayer.StarterPlayerScripts", None, '''local UIS = game:GetService("UserInputService")
local TweenService = game:GetService("TweenService")
local Players = game:GetService("Players")
local cam = workspace.CurrentCamera
local WALK, RUN, FOV = @walk@, @run@, @fov@
local function hum() local c = Players.LocalPlayer.Character return c and c:FindFirstChildOfClass("Humanoid") end
local function set(running)
    local h = hum()
    if h then h.WalkSpeed = running and RUN or WALK end
    TweenService:Create(cam, TweenInfo.new(0.25), {FieldOfView = running and 70 + FOV or 70}):Play()
end
UIS.InputBegan:Connect(function(i, gp) if not gp and i.KeyCode == Enum.KeyCode.LeftShift then set(true) end end)
UIS.InputEnded:Connect(function(i) if i.KeyCode == Enum.KeyCode.LeftShift then set(false) end end)
''')
_GP["double_jump"] = ("LocalScript", "StarterPlayer.StarterPlayerScripts", None, '''local UIS = game:GetService("UserInputService")
local Players = game:GetService("Players")
local MAX_JUMPS, used = @jumps@, 0
local function bind(char)
    local hum = char:WaitForChild("Humanoid")
    used = 0
    hum.StateChanged:Connect(function(_, new)
        if new == Enum.HumanoidStateType.Landed or new == Enum.HumanoidStateType.Running then used = 0 end
    end)
    UIS.JumpRequest:Connect(function()
        local s = hum:GetState()
        if (s == Enum.HumanoidStateType.Freefall or s == Enum.HumanoidStateType.Jumping) and used < MAX_JUMPS - 1 then
            used += 1
            hum:ChangeState(Enum.HumanoidStateType.Jumping)
        end
    end)
end
local p = Players.LocalPlayer
if p.Character then bind(p.Character) end
p.CharacterAdded:Connect(bind)
''')

_GP_DEFAULTS = {
    "leaderstats": {"stats": ["Coins", "Wins"]}, "kill_brick": {"damage": 100}, "coins": {"respawn": 0}, "jump_pad": {"power": 90}, "speed_boost": {"speed": 32, "seconds": 5},
    "teleporter": {"cooldown": 2}, "health_pickup": {"heal": 40, "respawn": 20}, "damage_zone": {"dps": 10}, "auto_door": {"lift": 12, "range": 14},
    "moving_platform": {"dz": 20, "duration": 4}, "tool_giver": {"folder": "Tools"}, "round_system": {"intermission": 15, "round": 90, "min_players": 2}, "spawn_protection": {"seconds": 4},
    "day_night": {"day_seconds": 240, "start_hour": 9}, "npc_patrol": {"speed": 12, "pause": 1}, "sprint": {"walk": 16, "run": 28, "fov": 12}, "double_jump": {"jumps": 2}, "checkpoint": {}, "goal": {},
}
_GP_STYLE = {
    "checkpoint": ("#4dd2ff", "Neon", [10, 1, 10]), "kill_brick": ("#ff3b30", "Neon", [10, 1, 10]), "coins": ("#ffd23f", "Neon", [2, 2, 0.4]), "jump_pad": ("#7dff9a", "Neon", [8, 1, 8]),
    "speed_boost": ("#38d9ff", "Neon", [8, 0.6, 8]), "teleporter": ("#a66bff", "Neon", [7, 1, 7]), "health_pickup": ("#ff5d8f", "Neon", [2, 2, 2]), "damage_zone": ("#ff8a00", "Neon", [16, 8, 16]),
    "goal": ("#7dff9a", "Neon", [12, 1, 12]), "auto_door": ("#8a8f98", "Metal", [10, 12, 1.5]), "moving_platform": ("#d9b45a", "Wood", [10, 1.2, 10]),
}
GAMEPLAY = sorted(_GP)


def _gp_source(kind, opts):
    cls, loc, tag, body = _GP[kind]
    merged = dict(_GP_DEFAULTS.get(kind, {}))
    merged.update({k: v for k, v in opts.items() if v is not None})
    for k, v in merged.items():
        body = body.replace("@" + k + "@", _lua(v) if isinstance(v, (list, dict)) else (str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)))
    left = re.findall(r"@(\w+)@", body)
    if left:
        raise ToolkitError(f"missing option(s) for {kind}: {', '.join(sorted(set(left)))}")
    uses_common = kind not in ("sprint", "double_jump")
    return (_GP_COMMON if uses_common else "") + body


@tool(RB, "ms_roblox_gameplay_kit",
      "Install tag-driven gameplay Scripts: leaderstats, checkpoint, kill_brick, coins, jump_pad, speed_boost, teleporter, health_pickup, damage_zone, goal, auto_door, moving_platform, tool_giver, round_system, spawn_protection, day_night, npc_patrol, sprint, double_jump. Tag `targets` or drop a styled part at `position`; `options` tune numbers.",
      {"kind": {"type": "string", "enum": GAMEPLAY}, "targets": PATHS, "position": VEC, "options": {"type": "object"}, "attributes": {"type": "object", "description": "Attributes set on the targeted parts (e.g. Power, Damage, Target)."},
       "name": {"type": "string"}, "script_parent": {"type": "string", "description": "Override where the script is installed."}},
      ["kind"], writes=True)
def gameplay_kit(args, ctx):
    a = dict(args)
    kind = str(a.get("kind") or "").lower()
    if kind not in _GP:
        raise ToolkitError(f"unknown kind '{kind}'", "Use one of: " + ", ".join(GAMEPLAY))
    cls, loc, tag, _ = _GP[kind]
    src = _gp_source(kind, as_dict(a.get("options")))
    style = _GP_STYLE.get(kind)
    payload = {"kind": kind, "script_class": cls, "script_name": str(a.get("name") or "MS_" + "".join(w.title() for w in kind.split("_"))), "parent_path": a.get("script_parent") or loc,
               "script_source": src, "tag": tag, "targets": _paths(a, "targets") if a.get("targets") else [], "position": a.get("position"), "attributes": as_dict(a.get("attributes")),
               "style": list(style) if style else None, "dry_run": a.get("dry_run"), "studio_id": a.get("studio_id"), "mode": a.get("mode")}
    return _exec(ctx, payload, _x(_LIB_MK, '''
        local CS = game:GetService("CollectionService")
        local function parentFor(path)
            local cur = game
            for seg in string.gmatch(path, "[^%.]+") do
                local nxt
                if cur == game then nxt = game:GetService(seg) else nxt = cur:FindFirstChild(seg) end
                if not nxt then error("cannot find " .. seg .. " in " .. path) end
                cur = nxt
            end
            return cur
        end
        local parent = parentFor(A.parent_path)
        local old = parent:FindFirstChild(A.script_name)
        if old then old:Destroy() end
        local s = Instance.new(A.script_class)
        s.Name = A.script_name
        s.Source = A.script_source
        s.Parent = parent
        R.script = s:GetFullName()
        local tagged = {}
        if A.tag then
            for _, p in ipairs(A.targets) do
                local t = resolve(p)
                CS:AddTag(t, A.tag)
                for k, v in pairs(A.attributes or {}) do t:SetAttribute(k, v) end
                table.insert(tagged, t:GetFullName())
            end
            if #A.targets == 0 and A.position and A.style then
                local st = A.style
                local part = mk("Part", {Name = A.tag, Anchored = true, Size = vec3(st[3]), Position = vec3(A.position), Color = hex(st[1]), Material = enumOf("Material", st[2], "Plastic")}, workspace)
                if A.kind == "coins" then part.Shape = Enum.PartType.Cylinder; part.CanCollide = false end
                if A.kind == "damage_zone" or A.kind == "goal" then part.CanCollide = false; part.Transparency = 0.6 end
                CS:AddTag(part, A.tag)
                for k, v in pairs(A.attributes or {}) do part:SetAttribute(k, v) end
                table.insert(tagged, part:GetFullName())
            end
            R.tag = A.tag
        end
        R.tagged = tagged
        R.kind = A.kind
        R.lines = select(2, string.gsub(A.script_source, "\\n", "\\n")) + 1
        waypoint("gameplay " .. A.kind)
    '''), "gameplay kit " + kind)


# ─────────────────────────────── Performance audit / optimisation ───────────────────────────────
@tool(RB, "ms_roblox_optimize",
      "Audit a place for performance (part/mesh/script/light/particle counts, unanchored static parts, heavy emitters, precise mesh collision, deprecated wait/spawn, missing StreamingEnabled). apply=true runs only the listed safe fixes: anchor_static, decor_no_collide, no_shadow_small, mesh_box_collision, cap_particles, disable_far_lights.",
      {"root": {"type": "string", "description": "Path to audit (default Workspace)."}, "apply": {"type": "boolean"},
       "fixes": {"type": "array", "items": {"type": "string", "enum": ["anchor_static", "decor_no_collide", "no_shadow_small", "mesh_box_collision", "cap_particles", "disable_far_lights"]}},
       "small_size": {"type": "number", "description": "Parts with all sides below this (studs) count as small (default 1)."}, "max_particle_rate": {"type": "number"}},
      [], writes=True)
def optimize(args, ctx):
    a = _norm(args, root="Workspace", small_size=1, max_particle_rate=60)
    a["fixes"] = [str(x) for x in as_list(a.get("fixes"))]
    return _exec(ctx, a, _x(_LIB_MK, '''
        local root = resolve(A.root)
        local want = {}
        for _, f in ipairs(A.fixes or {}) do want[f] = true end
        local apply = A.apply == true
        local c = {parts = 0, meshparts = 0, unions = 0, scripts = 0, lights = 0, emitters = 0, beams = 0, trails = 0, unanchored = 0, decals = 0, models = 0, sounds = 0, seats = 0}
        local issues = {}
        local fixed = {}
        local function add(sev, inst, code, msg)
            if #issues < 120 then table.insert(issues, {severity = sev, path = inst:GetFullName(), code = code, message = msg}) end
        end
        local function fix(code, inst) fixed[code] = (fixed[code] or 0) + 1 end
        local small = A.small_size
        local rate = A.max_particle_rate
        local dupe = {}
        for _, d in ipairs(root:GetDescendants()) do
            if d:IsA("BasePart") then
                c.parts = c.parts + 1
                local sz = d.Size
                if d:IsA("MeshPart") then c.meshparts = c.meshparts + 1 end
                if d:IsA("UnionOperation") then c.unions = c.unions + 1 end
                if d:IsA("Seat") or d:IsA("VehicleSeat") then c.seats = c.seats + 1 end
                local welded = false
                for _, k in ipairs(d:GetChildren()) do if k:IsA("Constraint") or k:IsA("WeldConstraint") or k:IsA("Weld") or k:IsA("Motor6D") then welded = true break end end
                local isCharacterPart = d.Parent and d.Parent:FindFirstChildOfClass("Humanoid") ~= nil
                if not d.Anchored and not welded and not isCharacterPart and not d:IsA("Seat") and not d:IsA("VehicleSeat") then
                    c.unanchored = c.unanchored + 1
                    if want.anchor_static and apply and d.AssemblyLinearVelocity.Magnitude < 0.01 then d.Anchored = true; fix("anchor_static", d)
                    elseif c.unanchored <= 15 then add("warn", d, "unanchored", "Unanchored part with no joints (physics cost). Anchor it if it should not move.") end
                end
                if math.max(sz.X, sz.Y, sz.Z) < small and d.CastShadow then
                    if want.no_shadow_small and apply then d.CastShadow = false; fix("no_shadow_small", d) end
                end
                if d.CanCollide and d.CanTouch == false and d.CanQuery == false then
                    -- already tuned
                elseif d.Transparency >= 0.95 and d.CanCollide and not d:IsA("SpawnLocation") then
                    add("info", d, "invisible_collider", "Invisible part still collides (intended?).")
                end
                if d.Anchored and d.CanCollide and math.max(sz.X, sz.Y, sz.Z) < 0.6 and not d:FindFirstChildOfClass("TouchTransmitter") then
                    if want.decor_no_collide and apply then d.CanCollide = false; d.CanTouch = false; d.CanQuery = false; fix("decor_no_collide", d)
                    elseif c.parts < 4000 then add("info", d, "tiny_collider", "Tiny anchored part collides; players rarely need that.") end
                end
                if d:IsA("MeshPart") and d.CollisionFidelity ~= Enum.CollisionFidelity.Box and d.CollisionFidelity ~= Enum.CollisionFidelity.Hull then
                    if want.mesh_box_collision and apply then d.CollisionFidelity = Enum.CollisionFidelity.Box; fix("mesh_box_collision", d)
                    else add("info", d, "precise_collision", "MeshPart uses " .. tostring(d.CollisionFidelity) .. " collision; Box/Hull is much cheaper.") end
                end
                if math.max(sz.X, sz.Y, sz.Z) > 2000 then add("warn", d, "huge_part", "Part larger than 2048 studs may clip or break lighting.") end
                local key = tostring(sz) .. tostring(d.Position)
                if dupe[key] then add("warn", d, "duplicate_part", "Another part has the same size and position (z-fighting / wasted part).") else dupe[key] = true end
            elseif d:IsA("LuaSourceContainer") then
                c.scripts = c.scripts + 1
                local ok, src = pcall(function() return d.Source end)
                if ok and src then
                    if string.find(src, "[^%w_%.]wait%(") or string.find(src, "^wait%(") then add("info", d, "deprecated_wait", "Uses wait(); prefer task.wait().") end
                    if string.find(src, "[^%w_%.]spawn%(") or string.find(src, "[^%w_%.]delay%(") then add("info", d, "deprecated_spawn", "Uses spawn()/delay(); prefer task.spawn/task.delay.") end
                    if string.find(src, "while true do") and not string.find(src, "wait") then add("error", d, "busy_loop", "while true do without a wait/yield will freeze the server.") end
                end
            elseif d:IsA("Light") then
                c.lights = c.lights + 1
                if want.disable_far_lights and apply and d.Shadows then d.Shadows = false; fix("disable_far_lights", d) end
            elseif d:IsA("ParticleEmitter") then
                c.emitters = c.emitters + 1
                if d.Rate > rate then
                    if want.cap_particles and apply then d.Rate = rate; fix("cap_particles", d) else add("warn", d, "heavy_emitter", "Rate " .. d.Rate .. "/s is high; keep below " .. rate .. ".") end
                end
            elseif d:IsA("Beam") then c.beams = c.beams + 1
            elseif d:IsA("Trail") then c.trails = c.trails + 1
            elseif d:IsA("Decal") or d:IsA("Texture") then c.decals = c.decals + 1
            elseif d:IsA("Sound") then c.sounds = c.sounds + 1
            elseif d:IsA("Model") then c.models = c.models + 1 end
        end
        if c.lights > 40 then add("warn", root, "many_lights", c.lights .. " lights; dynamic lights are expensive on mobile (cap ~30 active).") end
        if c.parts > 20000 then add("warn", root, "part_count", c.parts .. " parts; enable StreamingEnabled and consider merging static geometry.") end
        local sok, streaming = pcall(function() return workspace.StreamingEnabled end)
        if sok and streaming == false and c.parts > 5000 then add("warn", workspace, "no_streaming", "StreamingEnabled is off with " .. c.parts .. " parts. Enable it for large maps.") end
        R.root = root:GetFullName()
        R.counts = c
        R.issues = issues
        R.fixed = fixed
        R.applied = apply
        local score = 100 - math.min(40, #issues) - (c.parts > 20000 and 15 or 0)
        R.score = math.max(0, score)
        if apply then waypoint("optimize") end
    '''), "optimize")
