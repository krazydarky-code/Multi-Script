# SPDX-License-Identifier: GPL-3.0-or-later
"""Roblox audio + NPC tools for engine_toolkit.

ms_roblox_audio_kit     install audio systems (mixer, audio API, ambience, music, footsteps, UI sounds, 3D emitters, triggers, reverb, jukebox, low-health)
ms_roblox_audio_tools   list / audit / fix / create sounds, groups and effects
ms_roblox_npc_builder   build a humanoid NPC (description-based with a mannequin fallback)
ms_roblox_npc_behavior  install NPC AI scripts (wander, patrol, follow, guard, enemies, flee, merchant, quest giver, dialogue, spawner)
ms_roblox_npc_manage    list / inspect / configure / crowd-spawn / audit / snap NPCs

Every tool compiles to one Luau program for the official Studio MCP `execute_luau`. Programs and the scripts they
install use only syntax that also loads in stock Lua (no +=, continue, type annotations) so tests can load them."""
import re

from engine_toolkit import tool, as_list, as_dict, vec3, num, boolean, ToolkitError
from toolkit_roblox import _exec, _paths, PATH, PATHS, VEC
from toolkit_roblox_pro import _x, _lua, _LIB_MK, _norm

RB = "roblox"


def _lit(v):
    """Python -> Luau literal safe for embedding in a generated script."""
    s = _lua(v)
    return re.sub(r"\\u00([0-9a-fA-F]{2})", lambda m: "\\%03d" % int(m.group(1), 16), s)


def sound_id(v):
    s = "" if v is None else str(v).strip()
    if not s:
        return ""
    if s.isdigit():
        return "rbxassetid://" + s
    m = re.fullmatch(r"(?:rbxassetid://|https?://(?:www\.)?roblox\.com/asset/?\?id=)(\d+)", s, re.I)
    return "rbxassetid://" + m.group(1) if m else s


_ENTRY_KEYS = {"id", "volume", "pitch", "group", "loop", "pitchJitter", "minDistance", "maxDistance"}
_ID_OPTS = {"sounds", "states", "tracks", "hover", "click", "heartbeat", "materials"}


def _norm_ids(v, ids=False):
    """Normalise sound ids. In an id context (sounds/states/tracks/...), bare numbers become rbxassetid:// strings too."""
    if isinstance(v, dict):
        if ids and set(v) & _ENTRY_KEYS:
            return {k: (_norm_ids(x, True) if k == "id" else x) for k, x in v.items()}
        return {k: _norm_ids(x, ids) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_norm_ids(x, ids) for x in v]
    if isinstance(v, bool):
        return v
    if isinstance(v, int) and ids:
        return sound_id(v)
    if isinstance(v, str):
        return sound_id(v)
    return v


def _fill(src, opts):
    for k, v in opts.items():
        src = src.replace("@" + k + "@", _lit(v))
    left = re.findall(r"@(\w+)@", src)
    if left:
        raise ToolkitError("missing option(s): " + ", ".join(sorted(set(left))))
    return src


_LIB_INSTALL = '''
local CS = game:GetService("CollectionService")
local function parentFor(path, create)
    local cur = game
    for seg in string.gmatch(path, "[^%.]+") do
        local nxt
        if cur == game then nxt = game:GetService(seg) else nxt = cur:FindFirstChild(seg) end
        if not nxt and create and cur ~= game then nxt = mk("Folder", {Name = seg}, cur) end
        if not nxt then error("cannot find " .. seg .. " in " .. path) end
        cur = nxt
    end
    return cur
end
local function installScripts(list)
    local out = {}
    for _, sc in ipairs(list or {}) do
        local parent = parentFor(sc.parent_path, true)
        local old = parent:FindFirstChild(sc.name)
        if old then old:Destroy() end
        local s = Instance.new(sc.class)
        s.Name = sc.name
        s.Source = sc.source
        s.Parent = parent
        table.insert(out, s:GetFullName())
    end
    return out
end
local function tagAndPlace(A)
    local tagged = {}
    if A.tag then
        for _, p in ipairs(A.targets or {}) do
            local t = resolve(p)
            CS:AddTag(t, A.tag)
            for _, extra in ipairs(A.extra_tags or {}) do CS:AddTag(t, extra) end
            for k, v in pairs(A.attributes or {}) do t:SetAttribute(k, v) end
            table.insert(tagged, t:GetFullName())
        end
        if #(A.targets or {}) == 0 and A.position and A.style then
            local st = A.style
            local part = mk("Part", {Name = A.tag, Anchored = true, Size = vec3(st[3]), Position = vec3(A.position), Color = hex(st[1]), Material = enumOf("Material", st[2], "Plastic")}, workspace)
            if st[4] then part.Transparency = st[4]; part.CanCollide = false end
            CS:AddTag(part, A.tag)
            for k, v in pairs(A.attributes or {}) do part:SetAttribute(k, v) end
            table.insert(tagged, part:GetFullName())
        end
    end
    return tagged
end
'''

# ─────────────────────────────── Audio kit ───────────────────────────────
_AUDIO_COMMON = '''local Players = game:GetService("Players")
local SoundService = game:GetService("SoundService")
local TweenService = game:GetService("TweenService")
local RunService = game:GetService("RunService")
local CS = game:GetService("CollectionService")
local Debris = game:GetService("Debris")
local function groupNamed(name)
    if not name or name == "" then return nil end
    return SoundService:FindFirstChild(name, true)
end
local function attr(inst, name, default)
    local v = inst:GetAttribute(name)
    if v == nil then return default end
    return v
end
local function pickId(v)
    if type(v) == "table" then
        if #v == 0 then return nil end
        return v[math.random(1, #v)]
    end
    return v
end
local function inside(part, pos)
    local rel = part.CFrame:PointToObjectSpace(pos)
    local h = part.Size * 0.5
    return math.abs(rel.X) <= h.X and math.abs(rel.Y) <= h.Y and math.abs(rel.Z) <= h.Z
end
local function listenerPos()
    local cam = workspace.CurrentCamera
    if cam then return cam.CFrame.Position end
    return Vector3.new(0, 0, 0)
end
'''

_AK = {}
_AK["audio_api"] = ("ModuleScript", "ReplicatedStorage", None, '''-- require(ReplicatedStorage.MS_Audio).Play("click") / .PlayAt("boom", part) / .SetGroupVolume("Music", 0.3, 1) / .Duck("Music", 0.2, 3)
local SoundService = game:GetService("SoundService")
local TweenService = game:GetService("TweenService")
local Debris = game:GetService("Debris")
local Audio = {}
local REG = @sounds@
local function entry(name)
    local e = REG[name]
    if type(e) == "string" then e = {id = e} end
    if type(e) == "table" and e.id == nil and #e > 0 then e = {id = e[math.random(1, #e)]} end
    return e
end
local function groupNamed(name)
    if not name or name == "" then return nil end
    return SoundService:FindFirstChild(name, true)
end
local function configure(s, e, opts)
    s.SoundId = e.id
    s.Volume = opts.volume or e.volume or 0.7
    local speed = opts.pitch or e.pitch or 1
    local jitter = opts.pitchJitter or e.pitchJitter
    if jitter then speed = speed * (1 + (math.random() - 0.5) * 2 * jitter) end
    s.PlaybackSpeed = speed
    s.Looped = opts.loop or e.loop or false
    local g = groupNamed(opts.group or e.group or "SFX")
    if g then s.SoundGroup = g end
end
function Audio.Has(name)
    return REG[name] ~= nil
end
function Audio.Play(name, opts)
    local e = entry(name)
    if not e or not e.id or e.id == "" then return nil end
    opts = opts or {}
    local s = Instance.new("Sound")
    configure(s, e, opts)
    s.Parent = opts.parent or SoundService
    s:Play()
    if not s.Looped then
        s.Ended:Connect(function() s:Destroy() end)
        Debris:AddItem(s, 120)
    end
    return s
end
function Audio.PlayAt(name, where, opts)
    local e = entry(name)
    if not e or not e.id or e.id == "" then return nil end
    opts = opts or {}
    local holder = where
    local temp = false
    if typeof(where) == "Vector3" then
        holder = Instance.new("Part")
        holder.Anchored = true; holder.CanCollide = false; holder.CanQuery = false; holder.CanTouch = false
        holder.Transparency = 1; holder.Size = Vector3.new(0.2, 0.2, 0.2); holder.Position = where
        holder.Parent = workspace
        temp = true
    end
    local s = Instance.new("Sound")
    configure(s, e, opts)
    s.RollOffMode = Enum.RollOffMode.InverseTapered
    s.RollOffMinDistance = opts.minDistance or e.minDistance or 8
    s.RollOffMaxDistance = opts.maxDistance or e.maxDistance or 90
    s.Parent = holder
    s:Play()
    if not s.Looped then
        s.Ended:Connect(function() s:Destroy(); if temp then holder:Destroy() end end)
        Debris:AddItem(s, 120)
        if temp then Debris:AddItem(holder, 121) end
    end
    return s
end
function Audio.Stop(sound, fadeTime)
    if not sound then return end
    if fadeTime and fadeTime > 0 then
        local t = TweenService:Create(sound, TweenInfo.new(fadeTime), {Volume = 0})
        t:Play()
        t.Completed:Connect(function() sound:Stop(); sound:Destroy() end)
    else
        sound:Stop(); sound:Destroy()
    end
end
function Audio.SetGroupVolume(groupName, volume, fadeTime)
    local g = groupNamed(groupName)
    if not g then return false end
    if fadeTime and fadeTime > 0 then
        TweenService:Create(g, TweenInfo.new(fadeTime), {Volume = volume}):Play()
    else
        g.Volume = volume
    end
    return true
end
function Audio.Duck(groupName, volume, seconds)
    local g = groupNamed(groupName)
    if not g then return end
    local original = g:GetAttribute("MS_BaseVolume") or g.Volume
    g:SetAttribute("MS_BaseVolume", original)
    TweenService:Create(g, TweenInfo.new(0.25), {Volume = volume}):Play()
    task.delay(seconds or 2, function()
        TweenService:Create(g, TweenInfo.new(0.6), {Volume = original}):Play()
    end)
end
return Audio
''')
_AK["ambient_zones"] = ("LocalScript", "StarterPlayer.StarterPlayerScripts", "AmbientZone", '''-- Parts tagged "AmbientZone" (invisible volumes). Attributes: SoundId, Volume (@volume@), FadeTime (@fade@), Group (@group@).
local active = {}
local zones = {}
local function track(z)
    if z:IsA("BasePart") then
        table.insert(zones, z)
        z.Transparency = 1; z.CanCollide = false; z.CanQuery = false; z.CanTouch = false
    end
end
for _, z in ipairs(CS:GetTagged("AmbientZone")) do track(z) end
CS:GetInstanceAddedSignal("AmbientZone"):Connect(track)
local function enter(z)
    local id = attr(z, "SoundId", "")
    if id == "" then return end
    local s = Instance.new("Sound")
    s.SoundId = id; s.Looped = true; s.Volume = 0
    local g = groupNamed(attr(z, "Group", @group@))
    if g then s.SoundGroup = g end
    s.Parent = SoundService
    s:Play()
    TweenService:Create(s, TweenInfo.new(attr(z, "FadeTime", @fade@)), {Volume = attr(z, "Volume", @volume@)}):Play()
    active[z] = s
end
local function leave(z)
    local s = active[z]
    active[z] = nil
    if not s then return end
    local t = TweenService:Create(s, TweenInfo.new(attr(z, "FadeTime", @fade@)), {Volume = 0})
    t:Play()
    t.Completed:Connect(function() s:Stop(); s:Destroy() end)
end
local acc = 0
RunService.Heartbeat:Connect(function(dt)
    acc = acc + dt
    if acc < 0.2 then return end
    acc = 0
    local pos = listenerPos()
    for _, z in ipairs(zones) do
        if z.Parent then
            local isIn = inside(z, pos)
            if isIn and not active[z] then enter(z) elseif not isIn and active[z] then leave(z) end
        elseif active[z] then leave(z) end
    end
end)
''')
_AK["music_player"] = ("LocalScript", "StarterPlayer.StarterPlayerScripts", None, '''-- Dynamic music with crossfades. Set the state from the server with workspace:SetAttribute("MusicState", "combat")
-- (or per player with player:SetAttribute("MusicState", ...)). States and tracks are configured below.
local STATES = @states@
local DEFAULT_STATE = @default_state@
local FADE = @fade@
local VOLUME = @volume@
local player = Players.LocalPlayer
local current, currentState, lastId
local function nextId(state)
    local list = STATES[state]
    if type(list) == "string" then return list end
    if type(list) ~= "table" or #list == 0 then return nil end
    if #list == 1 then return list[1] end
    local id = list[math.random(1, #list)]
    local guard = 0
    while id == lastId and guard < 6 do id = list[math.random(1, #list)]; guard = guard + 1 end
    return id
end
local function target() return attr(player, "MusicVolume", VOLUME) end
local function fadeOut(s, t)
    if not s then return end
    local tw = TweenService:Create(s, TweenInfo.new(t), {Volume = 0})
    tw:Play()
    tw.Completed:Connect(function() s:Stop(); s:Destroy() end)
end
local function play(state)
    local id = nextId(state)
    local old = current
    if not id or id == "" then
        fadeOut(old, FADE); current = nil; currentState = state
        return
    end
    lastId = id
    local s = Instance.new("Sound")
    s.Name = "MS_Music"; s.SoundId = id; s.Volume = 0
    local list = STATES[state]
    s.Looped = (type(list) == "string") or (type(list) == "table" and #list <= 1)
    local g = groupNamed("Music")
    if g then s.SoundGroup = g end
    s.Parent = SoundService
    s:Play()
    TweenService:Create(s, TweenInfo.new(FADE), {Volume = target()}):Play()
    fadeOut(old, FADE)
    current = s; currentState = state
    s.Ended:Connect(function() if current == s then play(state) end end)
end
local function wanted()
    return attr(player, "MusicState", attr(workspace, "MusicState", DEFAULT_STATE))
end
local function refresh()
    local w = wanted()
    if w ~= currentState then play(w) end
end
workspace:GetAttributeChangedSignal("MusicState"):Connect(refresh)
player:GetAttributeChangedSignal("MusicState"):Connect(refresh)
player:GetAttributeChangedSignal("MusicVolume"):Connect(function()
    if current then TweenService:Create(current, TweenInfo.new(0.4), {Volume = target()}):Play() end
end)
refresh()
''')
_AK["footsteps"] = ("LocalScript", "StarterPlayer.StarterPlayerScripts", None, '''-- Footsteps by floor material. SOUNDS maps Enum.Material names (Grass, Concrete, Wood, ...) to an id or a list of ids; Default is the fallback.
local SOUNDS = @sounds@
local VOLUME = @volume@
local STRIDE = @stride@
local MUTE_DEFAULT = @mute_default@
local player = Players.LocalPlayer
local function stepSound(material)
    local v = SOUNDS[material] or SOUNDS.Default
    return pickId(v)
end
local function bind(char)
    local hum = char:WaitForChild("Humanoid")
    local hrp = char:WaitForChild("HumanoidRootPart")
    if MUTE_DEFAULT then
        local running = hrp:FindFirstChild("Running")
        if running then running.Volume = 0 end
    end
    local acc = 0
    local conn
    local function play(loud)
        local id = stepSound(hum.FloorMaterial.Name)
        if not id or id == "" then return end
        local s = Instance.new("Sound")
        s.SoundId = id
        s.Volume = VOLUME * (loud and 1.5 or 1)
        s.PlaybackSpeed = 0.92 + math.random() * 0.16
        s.RollOffMode = Enum.RollOffMode.InverseTapered
        s.RollOffMinDistance = 6; s.RollOffMaxDistance = 45
        local g = groupNamed("SFX")
        if g then s.SoundGroup = g end
        s.Parent = hrp
        s:Play()
        Debris:AddItem(s, 3)
    end
    conn = RunService.Heartbeat:Connect(function(dt)
        if not char.Parent or hum.Health <= 0 then conn:Disconnect() return end
        local v = hrp.AssemblyLinearVelocity
        local speed = Vector3.new(v.X, 0, v.Z).Magnitude
        if hum.FloorMaterial == Enum.Material.Air or speed < 1 then acc = 0 return end
        acc = acc + speed * dt
        if acc >= STRIDE then acc = 0; play(false) end
    end)
    hum.StateChanged:Connect(function(_, new)
        if new == Enum.HumanoidStateType.Landed then play(true) end
    end)
end
if player.Character then task.spawn(bind, player.Character) end
player.CharacterAdded:Connect(bind)
''')
_AK["ui_sounds"] = ("LocalScript", "StarterPlayer.StarterPlayerScripts", None, '''-- Hover/click sounds for every TextButton/ImageButton in PlayerGui. Set attribute NoSound=true on a button to skip it.
local HOVER, CLICK, VOLUME = @hover@, @click@, @volume@
local pg = Players.LocalPlayer:WaitForChild("PlayerGui")
local function beep(id)
    if not id or id == "" then return end
    local s = Instance.new("Sound")
    s.SoundId = id; s.Volume = VOLUME
    local g = groupNamed("UI")
    if g then s.SoundGroup = g end
    s.Parent = SoundService
    s:Play()
    Debris:AddItem(s, 4)
end
local function wire(b)
    if not (b:IsA("TextButton") or b:IsA("ImageButton")) then return end
    if b:GetAttribute("NoSound") or b:GetAttribute("MSWired") then return end
    b:SetAttribute("MSWired", true)
    b.MouseEnter:Connect(function() beep(HOVER) end)
    b.Activated:Connect(function() beep(CLICK) end)
end
for _, d in ipairs(pg:GetDescendants()) do wire(d) end
pg.DescendantAdded:Connect(wire)
''')
_AK["emitter_3d"] = ("Script", "ServerScriptService", "SoundEmitter", '''-- Parts tagged "SoundEmitter" get a positional Sound. Attributes: SoundId, Volume (@volume@), MinDistance (@min_distance@), MaxDistance (@max_distance@), Loop (@loop@), Playing (true), Pitch (1), Group (@group@).
local function setup(part)
    local old = part:FindFirstChild("MS_Emitter")
    if old then old:Destroy() end
    local s = Instance.new("Sound")
    s.Name = "MS_Emitter"
    s.RollOffMode = Enum.RollOffMode.InverseTapered
    local function apply()
        s.SoundId = attr(part, "SoundId", "")
        s.Volume = attr(part, "Volume", @volume@)
        s.PlaybackSpeed = attr(part, "Pitch", 1)
        s.RollOffMinDistance = attr(part, "MinDistance", @min_distance@)
        s.RollOffMaxDistance = attr(part, "MaxDistance", @max_distance@)
        s.Looped = attr(part, "Loop", @loop@)
        local g = groupNamed(attr(part, "Group", @group@))
        if g then s.SoundGroup = g end
        if attr(part, "Playing", true) and s.SoundId ~= "" then
            if not s.IsPlaying then s:Play() end
        else
            s:Stop()
        end
    end
    s.Parent = part
    apply()
    for _, n in ipairs({"SoundId", "Volume", "Pitch", "MinDistance", "MaxDistance", "Loop", "Playing", "Group"}) do
        part:GetAttributeChangedSignal(n):Connect(apply)
    end
end
for _, p in ipairs(CS:GetTagged("SoundEmitter")) do task.spawn(setup, p) end
CS:GetInstanceAddedSignal("SoundEmitter"):Connect(function(p) task.spawn(setup, p) end)
''')
_AK["audio_trigger"] = ("Script", "ServerScriptService", "AudioTrigger", '''-- Parts tagged "AudioTrigger" play a positional sound when a player touches them.
-- Attributes: SoundId, Volume (@volume@), Once (@once@), Cooldown (@cooldown@), MaxDistance (@max_distance@).
local function setup(part)
    local last = -1e9
    local used = false
    part.Touched:Connect(function(hit)
        local char = hit and hit.Parent
        local hum = char and char:FindFirstChildOfClass("Humanoid")
        if not hum or not Players:GetPlayerFromCharacter(char) then return end
        if used and attr(part, "Once", @once@) then return end
        if os.clock() - last < attr(part, "Cooldown", @cooldown@) then return end
        local id = attr(part, "SoundId", "")
        if id == "" then return end
        last = os.clock(); used = true
        local s = Instance.new("Sound")
        s.SoundId = id; s.Volume = attr(part, "Volume", @volume@)
        s.RollOffMode = Enum.RollOffMode.InverseTapered
        s.RollOffMaxDistance = attr(part, "MaxDistance", @max_distance@)
        local g = groupNamed(attr(part, "Group", "SFX"))
        if g then s.SoundGroup = g end
        s.Parent = part
        s:Play()
        Debris:AddItem(s, 60)
    end)
end
for _, p in ipairs(CS:GetTagged("AudioTrigger")) do task.spawn(setup, p) end
CS:GetInstanceAddedSignal("AudioTrigger"):Connect(function(p) task.spawn(setup, p) end)
''')
_AK["reverb_zones"] = ("LocalScript", "StarterPlayer.StarterPlayerScripts", "ReverbZone", '''-- Parts tagged "ReverbZone" switch SoundService.AmbientReverb while the camera is inside. Attribute Preset = Enum.ReverbType name (Cave, Hallway, Arena, StoneRoom, Forest, City, UnderWater...). Outside every zone: @default@.
local zones = {}
local function track(z)
    if z:IsA("BasePart") then
        table.insert(zones, z)
        z.Transparency = 1; z.CanCollide = false; z.CanQuery = false; z.CanTouch = false
    end
end
for _, z in ipairs(CS:GetTagged("ReverbZone")) do track(z) end
CS:GetInstanceAddedSignal("ReverbZone"):Connect(track)
local function reverbOf(name)
    local ok, item = pcall(function() return Enum.ReverbType[name] end)
    if ok and item then return item end
    return Enum.ReverbType.NoReverb
end
local current
local acc = 0
RunService.Heartbeat:Connect(function(dt)
    acc = acc + dt
    if acc < 0.25 then return end
    acc = 0
    local pos = listenerPos()
    local want = @default@
    for _, z in ipairs(zones) do
        if z.Parent and inside(z, pos) then want = attr(z, "Preset", "Cave") end
    end
    if want ~= current then
        current = want
        SoundService.AmbientReverb = reverbOf(want)
    end
end)
''')
_AK["jukebox"] = ("Script", "ServerScriptService", "Jukebox", '''-- Parts tagged "Jukebox" get a ProximityPrompt that cycles through tracks and then switches off.
-- Tracks: attribute Tracks ("id1,id2,...") or the list baked in below. Attribute Volume (@volume@), MaxDistance (@max_distance@).
local TRACKS = @tracks@
local function setup(part)
    local list = TRACKS
    local custom = part:GetAttribute("Tracks")
    if type(custom) == "string" and custom ~= "" then
        list = {}
        for piece in string.gmatch(custom, "[^,%s]+") do
            local tid = piece
            if string.match(piece, "^%d+$") then tid = "rbxassetid://" .. piece end
            table.insert(list, tid)
        end
    end
    local s = Instance.new("Sound")
    s.Name = "MS_Jukebox"; s.Looped = true; s.Volume = attr(part, "Volume", @volume@)
    s.RollOffMode = Enum.RollOffMode.InverseTapered
    s.RollOffMaxDistance = attr(part, "MaxDistance", @max_distance@)
    local g = groupNamed("Music")
    if g then s.SoundGroup = g end
    s.Parent = part
    local prompt = Instance.new("ProximityPrompt")
    prompt.ObjectText = "Jukebox"; prompt.ActionText = "Play music"; prompt.HoldDuration = 0.2; prompt.MaxActivationDistance = 12
    prompt.Parent = part
    local index = 0
    prompt.Triggered:Connect(function()
        index = index + 1
        if index > #list then
            index = 0; s:Stop(); prompt.ActionText = "Play music"
            return
        end
        s.SoundId = list[index]; s:Play()
        prompt.ActionText = "Next track (" .. index .. "/" .. #list .. ")"
    end)
end
for _, p in ipairs(CS:GetTagged("Jukebox")) do task.spawn(setup, p) end
CS:GetInstanceAddedSignal("Jukebox"):Connect(function(p) task.spawn(setup, p) end)
''')
_AK["low_health"] = ("LocalScript", "StarterPlayer.StarterPlayerScripts", None, '''-- Heartbeat loop that fades in as health drops below @threshold@ of max, plus an optional muffle on the Master group.
local HEART = @heartbeat@
local THRESHOLD = @threshold@
local player = Players.LocalPlayer
local function bind(char)
    local hum = char:WaitForChild("Humanoid")
    local s = Instance.new("Sound")
    s.Name = "MS_Heartbeat"; s.SoundId = HEART; s.Looped = true; s.Volume = 0
    local g = groupNamed("SFX")
    if g then s.SoundGroup = g end
    s.Parent = SoundService
    if HEART ~= "" then s:Play() end
    local eq
    local master = groupNamed("Master")
    if master then
        eq = Instance.new("EqualizerSoundEffect")
        eq.Name = "MS_LowHealthMuffle"; eq.Enabled = false; eq.HighGain = -25; eq.MidGain = -4; eq.LowGain = 2
        eq.Parent = master
    end
    local function update()
        local frac = hum.Health / math.max(hum.MaxHealth, 1)
        local danger = hum.Health > 0 and frac < THRESHOLD
        local amount = danger and (1 - frac / THRESHOLD) or 0
        TweenService:Create(s, TweenInfo.new(0.4), {Volume = amount * @volume@}):Play()
        s.PlaybackSpeed = 0.9 + amount * 0.5
        if eq then eq.Enabled = danger end
    end
    hum.HealthChanged:Connect(update)
    hum.Died:Connect(function() if eq then eq.Enabled = false end s.Volume = 0 end)
    char.AncestryChanged:Connect(function()
        if not char.Parent then s:Destroy(); if eq then eq:Destroy() end end
    end)
    update()
end
if player.Character then task.spawn(bind, player.Character) end
player.CharacterAdded:Connect(bind)
''')

_AK_DEFAULTS = {
    "audio_api": {"sounds": {}},
    "ambient_zones": {"volume": 0.5, "fade": 2, "group": "Ambience"},
    "music_player": {"states": {}, "default_state": "calm", "fade": 2, "volume": 0.45},
    "footsteps": {"sounds": {}, "volume": 0.5, "stride": 3.4, "mute_default": True},
    "ui_sounds": {"hover": "", "click": "", "volume": 0.5},
    "emitter_3d": {"volume": 0.8, "min_distance": 10, "max_distance": 80, "loop": True, "group": "Ambience"},
    "audio_trigger": {"volume": 0.8, "once": False, "cooldown": 3, "max_distance": 80},
    "reverb_zones": {"default": "NoReverb"},
    "jukebox": {"tracks": [], "volume": 0.7, "max_distance": 70},
    "low_health": {"heartbeat": "", "threshold": 0.35, "volume": 0.8},
}
# options that must be supplied for the script to make noise (we never ship copyrighted audio)
_AK_NEEDS = {"audio_api": "sounds", "music_player": "states", "footsteps": "sounds", "ui_sounds": ("hover", "click"), "low_health": "heartbeat", "jukebox": "tracks"}
_AK_STYLE = {"ambient_zones": ("#4dd2ff", "ForceField", [40, 20, 40], 0.85), "emitter_3d": ("#ffd23f", "Neon", [1.5, 1.5, 1.5], 0.3), "audio_trigger": ("#a66bff", "ForceField", [10, 6, 10], 0.8),
             "reverb_zones": ("#ff8a00", "ForceField", [40, 20, 40], 0.85), "jukebox": ("#ff5d8f", "Neon", [3, 4, 2])}
_AK_HELP = {
    "mixer": "Creates SoundService.Master with Music/SFX/Ambience/UI/Voice SoundGroups (volumes, optional limiter, optional music ducking under Voice). Assign sounds with ms_roblox_audio_tools assign_group.",
    "audio_api": "ModuleScript ReplicatedStorage.MS_Audio: Play/PlayAt/Stop/SetGroupVolume/Duck keyed by friendly names from options.sounds.",
    "ambient_zones": "Tag Parts 'AmbientZone', set attribute SoundId (+Volume/FadeTime/Group). Sound fades in/out as the camera enters/leaves.",
    "music_player": "Crossfading music by state: workspace:SetAttribute('MusicState','combat'). options.states = {calm=[ids], combat=[ids]}.",
    "footsteps": "Footsteps per Enum.Material, stride-based with pitch jitter and landing thud. options.sounds = {Grass=[ids], Default=id}.",
    "ui_sounds": "Hover/click sounds for every GUI button (skip with attribute NoSound). options.hover / options.click.",
    "emitter_3d": "Tag Parts 'SoundEmitter' + attribute SoundId: positional looping sound with tapered rolloff; attributes live-update.",
    "audio_trigger": "Tag Parts 'AudioTrigger' + SoundId: plays a 3D sound when a player touches (Once/Cooldown attributes).",
    "reverb_zones": "Tag Parts 'ReverbZone' + attribute Preset (Cave, Hallway, Arena...): switches SoundService.AmbientReverb while the camera is inside.",
    "jukebox": "Tag a Part 'Jukebox': ProximityPrompt cycles tracks then switches off (options.tracks or attribute Tracks).",
    "low_health": "Heartbeat loop + Master muffle that ramp up as health drops (options.heartbeat = sound id).",
}
AUDIO_KINDS = ["mixer"] + sorted(_AK)

_MIXER_DEFAULT = [
    {"name": "Master", "parent": None, "volume": 1.0},
    {"name": "Music", "parent": "Master", "volume": 0.6},
    {"name": "SFX", "parent": "Master", "volume": 0.9},
    {"name": "Ambience", "parent": "Master", "volume": 0.7},
    {"name": "UI", "parent": "Master", "volume": 0.7},
    {"name": "Voice", "parent": "Master", "volume": 1.0},
]


def _audio_source(kind, opts):
    cls, loc, tag, body = _AK[kind]
    merged = dict(_AK_DEFAULTS.get(kind, {}))
    merged.update({k: _norm_ids(v, k in _ID_OPTS) for k, v in opts.items() if v is not None})
    uses_common = kind != "audio_api"
    return cls, loc, tag, (_AUDIO_COMMON if uses_common else "") + _fill(body, merged), merged


@tool(RB, "ms_roblox_audio_kit",
      "Install a Roblox audio system. kind: mixer (Master + Music/SFX/Ambience/UI/Voice SoundGroups, limiter, music ducking), audio_api (MS_Audio module), ambient_zones, music_player (state crossfades), footsteps (per material), ui_sounds, emitter_3d, audio_trigger, reverb_zones, jukebox, low_health. "
      "Sound ids come from `options` (numbers or rbxassetid://; none bundled). Tag `targets` or drop a marker at `position`. Result `usage` explains each kind.",
      {"kind": {"type": "string", "enum": AUDIO_KINDS}, "options": {"type": "object", "description": "Kind-specific settings, e.g. {sounds:{Grass:[id,...],Default:id}} for footsteps, {states:{calm:[ids],combat:[ids]}} for music_player, {hover:id,click:id} for ui_sounds, {groups:[{name,parent,volume}]} for mixer."},
       "targets": PATHS, "position": VEC, "attributes": {"type": "object", "description": "Attributes set on the targeted parts (SoundId, Volume, ...)."},
       "name": {"type": "string"}, "script_parent": {"type": "string", "description": "Override where the script is installed."},
       "limiter": {"type": "boolean", "description": "mixer: add a compressor/limiter on Master (default true)."}, "ducking": {"type": "boolean", "description": "mixer: duck Music while Voice plays (default true)."}},
      ["kind"], writes=True)
def audio_kit(args, ctx):
    a = dict(args)
    kind = str(a.get("kind") or "").lower()
    if kind not in AUDIO_KINDS:
        raise ToolkitError(f"unknown kind '{kind}'", "Use one of: " + ", ".join(AUDIO_KINDS))
    opts = as_dict(a.get("options"))
    payload = {"kind": kind, "attributes": as_dict(a.get("attributes")), "dry_run": a.get("dry_run"), "studio_id": a.get("studio_id"), "mode": a.get("mode"),
               "targets": _paths(a, "targets") if a.get("targets") else [], "position": a.get("position"), "scripts": [], "groups": None, "tag": None, "style": None, "limiter": a.get("limiter") is not False,
               "ducking": a.get("ducking") is not False}
    warnings = []
    if kind == "mixer":
        groups = opts.get("groups") or _MIXER_DEFAULT
        clean = []
        for g in as_list(groups):
            g = as_dict(g)
            if not str(g.get("name") or "").strip():
                continue
            clean.append({"name": str(g["name"]), "parent": g.get("parent"), "volume": num(g.get("volume"), 1.0, 0, 10)})
        if not clean:
            raise ToolkitError("options.groups had no usable entries")
        payload["groups"] = clean
    else:
        cls, loc, tag, src, merged = _audio_source(kind, opts)
        need = _AK_NEEDS.get(kind)
        for k in ([need] if isinstance(need, str) else list(need or [])):
            if not merged.get(k):
                warnings.append(f"options.{k} is empty: the script is installed but stays silent until sound ids are supplied (we never bundle copyrighted audio).")
        payload["scripts"] = [{"class": cls, "name": str(a.get("name") or "MS_" + "".join(w.title() for w in kind.split("_"))), "parent_path": a.get("script_parent") or loc, "source": src}]
        payload["tag"] = tag
        st = _AK_STYLE.get(kind)
        payload["style"] = list(st) if st else None
    res = _exec(ctx, payload, _x(_LIB_MK + _LIB_INSTALL, '''
        R.kind = A.kind
        R.installed = installScripts(A.scripts)
        if A.groups then
            local made = {}
            local byName = {}
            for _, g in ipairs(A.groups) do
                local existing = game:GetService("SoundService"):FindFirstChild(g.name, true)
                local sg = existing
                if not sg then
                    sg = Instance.new("SoundGroup")
                    sg.Name = g.name
                end
                sg.Volume = g.volume
                byName[g.name] = sg
                if g.parent and byName[g.parent] then sg.Parent = byName[g.parent]
                elseif g.parent then
                    local p = game:GetService("SoundService"):FindFirstChild(g.parent, true)
                    sg.Parent = p or game:GetService("SoundService")
                else sg.Parent = game:GetService("SoundService") end
                table.insert(made, sg:GetFullName())
            end
            R.groups = made
            local master = byName["Master"]
            if A.limiter and master and not master:FindFirstChild("MS_Limiter") then
                local c = Instance.new("CompressorSoundEffect")
                c.Name = "MS_Limiter"; c.Threshold = -6; c.Ratio = 8; c.Attack = 0.02; c.Release = 0.2
                c.Parent = master
                R.limiter = true
            end
            local music, voice = byName["Music"], byName["Voice"]
            if A.ducking and music and voice and not music:FindFirstChild("MS_Ducker") then
                local d = Instance.new("CompressorSoundEffect")
                d.Name = "MS_Ducker"; d.Threshold = -30; d.Ratio = 6; d.Attack = 0.1; d.Release = 0.6
                local okSide = pcall(function() d.SideChain = voice end)
                if not okSide then
                    okSide = pcall(function()
                        local ov = Instance.new("ObjectValue"); ov.Name = "SideChain"; ov.Value = voice; d.SideChain = ov
                    end)
                end
                d.Parent = music
                R.ducking = okSide
            end
        end
        R.tagged = tagAndPlace(A)
        R.tag = A.tag
        waypoint("audio kit " .. A.kind)
    '''), "audio kit " + kind)
    if isinstance(res, dict):
        res["usage"] = _AK_HELP[kind]
        if warnings:
            res["warnings"] = warnings
    return res


# ─────────────────────────────── Audio tools (list / audit / fix / create) ───────────────────────────────
EFFECTS = ["reverb", "echo", "equalizer", "compressor", "distortion", "chorus", "flange", "pitch_shift", "tremolo"]
EFFECT_PRESETS = ["cave", "room", "hall", "underwater", "radio", "telephone", "muffled", "megaphone", "helmet"]
AUDIO_ACTIONS = ["list", "audit", "create_group", "create_sound", "assign_group", "add_effect", "set"]


@tool(RB, "ms_roblox_audio_tools",
      "Inspect and fix Roblox audio. action: list; audit (empty/bad SoundIds, loud volumes, huge 3D rolloff, duplicate/too many loops, no mixer) with apply=true + fixes assign_group/rolloff_3d/clamp_volume/fix_ids; create_group; create_sound; assign_group; "
      "add_effect (reverb/echo/equalizer/compressor/distortion/chorus/flange/pitch_shift/tremolo or presets cave/underwater/radio/muffled/...); set (volume/pitch/loop/group/rolloff on many sounds).",
      {"action": {"type": "string", "enum": AUDIO_ACTIONS}, "root": {"type": "string", "description": "Where to look (default: the whole game)."},
       "paths": PATHS, "name_contains": {"type": "string", "description": "Only sounds whose name contains this text."},
       "group": {"type": "string", "description": "SoundGroup name for create_group / assign_group / audit fixes / create_sound."}, "parent_group": {"type": "string"},
       "volume": {"type": "number"}, "pitch": {"type": "number"}, "looped": {"type": "boolean"}, "playing": {"type": "boolean"},
       "sound_id": {"type": ["string", "number"]}, "name": {"type": "string"}, "parent": {"type": "string", "description": "create_sound: where to put the Sound (a BasePart/Attachment makes it positional)."},
       "min_distance": {"type": "number"}, "max_distance": {"type": "number"},
       "effect": {"type": "string", "enum": EFFECTS + EFFECT_PRESETS}, "props": {"type": "object", "description": "Effect/sound property overrides."},
       "apply": {"type": "boolean", "description": "audit: apply `fixes`."},
       "fixes": {"type": "array", "items": {"type": "string", "enum": ["assign_group", "rolloff_3d", "clamp_volume", "fix_ids"]}},
       "limit": {"type": "integer", "minimum": 1, "maximum": 1000}},
      ["action"], writes=True)
def audio_tools(args, ctx):
    a = dict(args)
    act = str(a.get("action") or "").lower()
    if act not in AUDIO_ACTIONS:
        raise ToolkitError(f"unknown action '{act}'", "Use one of: " + ", ".join(AUDIO_ACTIONS))
    a["action"] = act
    a["paths"] = _paths(a, "paths", "path")
    a["fixes"] = [str(x) for x in as_list(a.get("fixes"))]
    a["limit"] = num(a.get("limit"), 200, 1, 1000, True)
    if a.get("sound_id") is not None:
        a["sound_id"] = sound_id(a["sound_id"])
    a["props"] = _norm_ids(as_dict(a.get("props")))
    if act == "add_effect" and not a.get("effect"):
        raise ToolkitError("add_effect needs `effect`", "Pick an effect or a preset such as cave / underwater / radio.")
    if act in ("create_group",) and not a.get("group"):
        raise ToolkitError("create_group needs `group`")
    if act == "create_sound" and not a.get("parent"):
        a["parent"] = "SoundService"
    return _exec(ctx, a, _x(_LIB_MK, '''
        local SS = game:GetService("SoundService")
        local root = (A.root == nil or A.root == "" or A.root == "game") and game or resolve(A.root)
        local function groupNamed(n)
            if not n or n == "" then return nil end
            return SS:FindFirstChild(n, true)
        end
        local function is3D(s) return s.Parent ~= nil and (s.Parent:IsA("BasePart") or s.Parent:IsA("Attachment")) end
        local function validId(id)
            if id == nil or id == "" then return false end
            return string.match(id, "^rbxassetid://%d+$") ~= nil or string.match(id, "^rbxasset://") ~= nil or string.match(id, "^http") ~= nil
        end
        local function collect()
            local sounds, groups, effects = {}, {}, {}
            local ok, all = pcall(function() return root:GetDescendants() end)
            if not ok then all = {} end
            for _, d in ipairs(all) do
                if d:IsA("Sound") then table.insert(sounds, d)
                elseif d:IsA("SoundGroup") then table.insert(groups, d)
                elseif d:IsA("SoundEffect") then table.insert(effects, d) end
            end
            if root == game then
                for _, g in ipairs(SS:GetChildren()) do
                    if g:IsA("SoundGroup") then
                        local seen = false
                        for _, x in ipairs(groups) do if x == g then seen = true end end
                        if not seen then table.insert(groups, g) end
                    end
                end
            end
            if A.name_contains and A.name_contains ~= "" then
                local f = {}
                local needle = string.lower(A.name_contains)
                for _, s in ipairs(sounds) do if string.find(string.lower(s.Name), needle, 1, true) then table.insert(f, s) end end
                sounds = f
            end
            return sounds, groups, effects
        end
        local function row(s)
            return {path = s:GetFullName(), id = s.SoundId, volume = s.Volume, looped = s.Looped, playing = s.Playing, playOnRemove = s.PlayOnRemove,
                group = s.SoundGroup and s.SoundGroup.Name or nil, positional = is3D(s), rolloff = tostring(s.RollOffMode), minDistance = s.RollOffMinDistance, maxDistance = s.RollOffMaxDistance, speed = s.PlaybackSpeed}
        end
        local function targets()
            local out = {}
            if #(A.paths or {}) > 0 then
                for _, p in ipairs(A.paths) do
                    local t = resolve(p)
                    if t:IsA("Sound") then table.insert(out, t)
                    else for _, d in ipairs(t:GetDescendants()) do if d:IsA("Sound") then table.insert(out, d) end end end
                end
            else
                local s = collect()
                out = s
            end
            if #(A.paths or {}) > 0 and A.name_contains and A.name_contains ~= "" then
                local f = {}
                local needle = string.lower(A.name_contains)
                for _, s in ipairs(out) do if string.find(string.lower(s.Name), needle, 1, true) then table.insert(f, s) end end
                out = f
            end
            return out
        end
        local act = A.action

        if act == "list" then
            local sounds, groups, effects = collect()
            local rows = {}
            for _, s in ipairs(sounds) do if #rows < A.limit then table.insert(rows, row(s)) end end
            local grows = {}
            for _, g in ipairs(groups) do table.insert(grows, {path = g:GetFullName(), volume = g.Volume, parent = g.Parent and g.Parent.Name or nil, effects = #g:GetChildren()}) end
            local erows = {}
            for _, e in ipairs(effects) do if #erows < A.limit then table.insert(erows, {path = e:GetFullName(), class = e.ClassName, enabled = e.Enabled}) end end
            R.sounds = rows; R.soundCount = #sounds; R.groups = grows; R.effects = erows
            if #sounds > A.limit then R.truncated = true end

        elseif act == "audit" then
            local sounds, groups, effects = collect()
            local issues, fixed = {}, {}
            local want = {}
            for _, f in ipairs(A.fixes or {}) do want[f] = true end
            local apply = A.apply == true
            local function add(sev, inst, code, msg)
                if #issues < 150 then table.insert(issues, {severity = sev, path = inst:GetFullName(), code = code, message = msg}) end
            end
            local function fix(code) fixed[code] = (fixed[code] or 0) + 1 end
            local ids, loops, unassigned, positional = {}, 0, 0, 0
            for _, s in ipairs(sounds) do
                if s.SoundId == "" then add("warn", s, "empty_id", "Sound has no SoundId.")
                elseif not validId(s.SoundId) then
                    if want.fix_ids and apply and string.match(s.SoundId, "^%d+$") then s.SoundId = "rbxassetid://" .. s.SoundId; fix("fix_ids")
                    else add("error", s, "bad_id", "SoundId '" .. s.SoundId .. "' is not an rbxassetid:// asset.") end
                end
                if s.SoundId ~= "" then
                    ids[s.SoundId] = (ids[s.SoundId] or 0) + 1
                end
                if s.Looped then loops = loops + 1 end
                if s.Volume > 2 then
                    if want.clamp_volume and apply then s.Volume = 1; fix("clamp_volume") else add("warn", s, "loud", "Volume " .. s.Volume .. " is above 2; clipping likely.") end
                end
                if s.SoundGroup == nil then
                    unassigned = unassigned + 1
                    if want.assign_group and apply and A.group and groupNamed(A.group) then s.SoundGroup = groupNamed(A.group); fix("assign_group") end
                end
                if is3D(s) then
                    positional = positional + 1
                    if s.RollOffMaxDistance >= 10000 or s.RollOffMaxDistance > 1000 then
                        if want.rolloff_3d and apply then
                            s.RollOffMode = Enum.RollOffMode.InverseTapered
                            s.RollOffMinDistance = A.min_distance or 8
                            s.RollOffMaxDistance = A.max_distance or 80
                            fix("rolloff_3d")
                        else add("info", s, "wide_rolloff", "Positional sound audible up to " .. s.RollOffMaxDistance .. " studs; set a tighter RollOffMaxDistance (60-120).") end
                    end
                end
            end
            for id, n in pairs(ids) do
                if n > 5 then
                    table.insert(issues, {severity = "info", path = id, code = "duplicate_id", message = n .. " Sound instances share this id; consider one shared Sound or the MS_Audio module."})
                end
            end
            if loops > 12 then table.insert(issues, {severity = "warn", path = root:GetFullName(), code = "many_loops", message = loops .. " looping sounds exist; cap active loops (~10) for mobile."}) end
            if unassigned > 0 and #groups == 0 then
                table.insert(issues, {severity = "info", path = SS:GetFullName(), code = "no_mixer", message = "No SoundGroups exist; run ms_roblox_audio_kit kind=mixer, then assign sounds to groups."})
            end
            for _, g in ipairs(groups) do
                if g.Volume == 0 then add("warn", g, "muted_group", "SoundGroup volume is 0 (everything in it is silent).") end
            end
            R.counts = {sounds = #sounds, groups = #groups, effects = #effects, looping = loops, positional = positional, unassigned = unassigned}
            R.issues = issues; R.issueCount = #issues; R.fixed = fixed; R.applied = apply

        elseif act == "create_group" then
            local existing = groupNamed(A.group)
            local g = existing or Instance.new("SoundGroup")
            g.Name = A.group
            if A.volume then g.Volume = A.volume end
            local parent = A.parent_group and groupNamed(A.parent_group) or nil
            if not existing then g.Parent = parent or SS end
            R.group = g:GetFullName(); R.created = existing == nil

        elseif act == "create_sound" then
            local parent = resolve(A.parent)
            local s = Instance.new("Sound")
            s.Name = A.name or "MS_Sound"
            s.SoundId = A.sound_id or ""
            s.Volume = A.volume or 0.7
            if A.pitch then s.PlaybackSpeed = A.pitch end
            if A.looped ~= nil then s.Looped = A.looped end
            if A.group and groupNamed(A.group) then s.SoundGroup = groupNamed(A.group) end
            if parent:IsA("BasePart") or parent:IsA("Attachment") then
                s.RollOffMode = Enum.RollOffMode.InverseTapered
                s.RollOffMinDistance = A.min_distance or 10
                s.RollOffMaxDistance = A.max_distance or 80
            end
            for k, v in pairs(A.props or {}) do pcall(function() s[k] = v end) end
            s.Parent = parent
            R.sound = s:GetFullName(); R.positional = is3D(s)
            if A.playing and A.sound_id and A.sound_id ~= "" then pcall(function() s:Play() end) end

        elseif act == "assign_group" then
            local g = groupNamed(A.group)
            if not g then error("SoundGroup '" .. tostring(A.group) .. "' not found; create it first (create_group or audio_kit mixer)") end
            local n = 0
            for _, s in ipairs(targets()) do s.SoundGroup = g; n = n + 1 end
            R.assigned = n; R.group = g:GetFullName()

        elseif act == "add_effect" then
            local PRESETS = {
                cave = {{"ReverbSoundEffect", {DecayTime = 4, Density = 1, Diffusion = 1, DryLevel = -4, WetLevel = 2}}},
                room = {{"ReverbSoundEffect", {DecayTime = 1.1, Density = 0.8, Diffusion = 0.8, DryLevel = -2, WetLevel = -6}}},
                hall = {{"ReverbSoundEffect", {DecayTime = 3, Density = 1, Diffusion = 1, DryLevel = -3, WetLevel = 0}}},
                underwater = {{"EqualizerSoundEffect", {LowGain = 2, MidGain = -15, HighGain = -40}}, {"ChorusSoundEffect", {Depth = 0.3, Mix = 0.3, Rate = 0.6}}},
                radio = {{"EqualizerSoundEffect", {LowGain = -30, MidGain = 5, HighGain = -20}}, {"DistortionSoundEffect", {Level = 0.25}}},
                telephone = {{"EqualizerSoundEffect", {LowGain = -40, MidGain = 8, HighGain = -35}}, {"DistortionSoundEffect", {Level = 0.15}}},
                muffled = {{"EqualizerSoundEffect", {LowGain = 2, MidGain = -8, HighGain = -35}}},
                megaphone = {{"EqualizerSoundEffect", {LowGain = -35, MidGain = 6, HighGain = -10}}, {"DistortionSoundEffect", {Level = 0.45}}, {"CompressorSoundEffect", {Threshold = -25, Ratio = 8}}},
                helmet = {{"EqualizerSoundEffect", {LowGain = 4, MidGain = -6, HighGain = -25}}, {"ReverbSoundEffect", {DecayTime = 0.6, Density = 1, Diffusion = 1, DryLevel = -2, WetLevel = -8}}},
            }
            local SINGLE = {
                reverb = {"ReverbSoundEffect", {DecayTime = 1.5, Density = 1, Diffusion = 1, DryLevel = -6, WetLevel = 0}},
                echo = {"EchoSoundEffect", {Delay = 0.4, Feedback = 0.4, DryLevel = 0, WetLevel = -6}},
                equalizer = {"EqualizerSoundEffect", {LowGain = 0, MidGain = 0, HighGain = 0}},
                compressor = {"CompressorSoundEffect", {Attack = 0.1, Release = 0.1, Threshold = -20, Ratio = 4}},
                distortion = {"DistortionSoundEffect", {Level = 0.5}},
                chorus = {"ChorusSoundEffect", {Depth = 0.45, Mix = 0.5, Rate = 0.5}},
                flange = {"FlangeSoundEffect", {Depth = 0.45, Mix = 0.85, Rate = 5}},
                pitch_shift = {"PitchShiftSoundEffect", {Octave = 1}},
                tremolo = {"TremoloSoundEffect", {Depth = 1, Duty = 0.5, Frequency = 5}},
            }
            local list = PRESETS[A.effect] or {SINGLE[A.effect]}
            if #(A.paths or {}) == 0 then error("add_effect needs `paths` (Sound or SoundGroup paths)") end
            local made = {}
            for _, p in ipairs(A.paths) do
                local t = resolve(p)
                if not (t:IsA("Sound") or t:IsA("SoundGroup")) then error(p .. " is not a Sound or SoundGroup") end
                for _, def in ipairs(list) do
                    local tag = "MS_" .. A.effect .. "_" .. def[1]
                    local old = t:FindFirstChild(tag)
                    if old then old:Destroy() end
                    local e = Instance.new(def[1])
                    e.Name = tag
                    for k, v in pairs(def[2]) do pcall(function() e[k] = v end) end
                    for k, v in pairs(A.props or {}) do pcall(function() e[k] = v end) end
                    e.Parent = t
                    table.insert(made, e:GetFullName())
                end
            end
            R.effects = made

        elseif act == "set" then
            local n = 0
            local g = A.group and groupNamed(A.group) or nil
            for _, s in ipairs(targets()) do
                if A.volume ~= nil then s.Volume = A.volume end
                if A.pitch ~= nil then s.PlaybackSpeed = A.pitch end
                if A.looped ~= nil then s.Looped = A.looped end
                if g then s.SoundGroup = g end
                if A.min_distance then s.RollOffMinDistance = A.min_distance end
                if A.max_distance then s.RollOffMaxDistance = A.max_distance end
                if A.sound_id then s.SoundId = A.sound_id end
                for k, v in pairs(A.props or {}) do pcall(function() s[k] = v end) end
                n = n + 1
            end
            R.updated = n
        end
        waypoint("audio " .. act)
    '''), "audio " + act)


# ─────────────────────────────── NPC builder ───────────────────────────────
NPC_PRESETS = {
    "villager": {"skin": "#e0b48a", "shirt": "#5b8cc4", "pants": "#4a4a4a", "health": 100, "speed": 10, "scale": 1},
    "guard": {"skin": "#d9a679", "shirt": "#6b7280", "pants": "#374151", "health": 200, "speed": 14, "scale": 1.05},
    "merchant": {"skin": "#e0b48a", "shirt": "#a0522d", "pants": "#3b2f2f", "health": 100, "speed": 10, "scale": 1},
    "quest_giver": {"skin": "#e8c39e", "shirt": "#c9a227", "pants": "#4b3a2a", "health": 100, "speed": 10, "scale": 1},
    "zombie": {"skin": "#6b8e5a", "shirt": "#3f5a36", "pants": "#2c3a2a", "health": 120, "speed": 9, "scale": 1},
    "skeleton": {"skin": "#e8e6dc", "shirt": "#d8d6cc", "pants": "#c9c7bd", "health": 80, "speed": 13, "scale": 1},
    "robot": {"skin": "#9aa5b1", "shirt": "#556270", "pants": "#3d4852", "health": 150, "speed": 12, "scale": 1},
    "boss": {"skin": "#8a2a2a", "shirt": "#2a2a2a", "pants": "#1a1a1a", "health": 1000, "speed": 14, "scale": 2},
    "child": {"skin": "#f0c8a0", "shirt": "#e0556b", "pants": "#3a5fa0", "health": 60, "speed": 12, "scale": 0.7},
}
BEHAVIOR_TAGS = {"wander": "NpcWander", "patrol": "NpcPatrol", "follow": "NpcFollow", "guard": "NpcGuard", "enemy_melee": "NpcEnemy", "enemy_ranged": "NpcShooter",
                 "flee": "NpcFlee", "merchant": "NpcMerchant", "quest_giver": "NpcQuest", "dialogue": "NpcDialogue"}

_ANIMATE_SRC = '''-- Minimal server-side animator for NPCs: idle when standing, walk when moving. Replace the ids with your own animations.
local hum = script.Parent:WaitForChild("Humanoid")
local animator = hum:FindFirstChildOfClass("Animator")
if not animator then animator = Instance.new("Animator"); animator.Parent = hum end
local function load(id)
    local a = Instance.new("Animation")
    a.AnimationId = id
    local ok, track = pcall(function() return animator:LoadAnimation(a) end)
    if ok then return track end
    return nil
end
local idle = load(@idle@)
local walk = load(@walk@)
local moving = false
if idle then idle.Looped = true; idle:Play() end
if walk then walk.Looped = true end
hum.Running:Connect(function(speed)
    if speed > 0.5 then
        if not moving then
            moving = true
            if idle then idle:Stop(0.2) end
            if walk then walk:Play(0.2) end
        end
        if walk then walk:AdjustSpeed(speed / @ref_speed@) end
    elseif moving then
        moving = false
        if walk then walk:Stop(0.2) end
        if idle then idle:Play(0.2) end
    end
end)
'''
_R15_ANIMS = ("rbxassetid://507766666", "rbxassetid://507777826")
_R6_ANIMS = ("rbxassetid://180435571", "rbxassetid://180426354")


def _ids_csv(v):
    return ",".join(re.sub(r"\D", "", str(x)) for x in as_list(v) if re.sub(r"\D", "", str(x)))


@tool(RB, "ms_roblox_npc_builder",
      "Build a humanoid NPC: R15/R6 via Players:CreateHumanoidModelFromDescription (copy a user_id avatar or set shirt/pants/face/hat ids or plain colours) with a blocky R6 mannequin fallback. Presets villager/guard/merchant/quest_giver/zombie/skeleton/robot/boss/child set stats; "
      "adds name/title plate, scale, grounding, MS_NPC + behaviour tags and an idle/walk animator. Give it AI with ms_roblox_npc_behavior.",
      {"name": {"type": "string"}, "display_name": {"type": "string"}, "title": {"type": "string", "description": "Subtitle on the name plate, e.g. Blacksmith."},
       "position": VEC, "facing": {"type": "number", "description": "Y rotation in degrees."}, "preset": {"type": "string", "enum": sorted(NPC_PRESETS)}, "rig": {"type": "string", "enum": ["R15", "R6"]},
       "user_id": {"type": "integer", "description": "Copy this Roblox user's avatar."},
       "appearance": {"type": "object", "description": "{skin, shirt, pants (hex colours), shirt_id, pants_id, tshirt_id, face_id, hats:[ids], hair:[ids], accessories:{neck,front,back,shoulders,waist:[ids]}}"},
       "health": {"type": "number"}, "walk_speed": {"type": "number"}, "jump_power": {"type": "number"}, "scale": {"type": "number"},
       "behavior": {"type": "array", "items": {"type": "string", "enum": sorted(BEHAVIOR_TAGS)}, "description": "Behaviour tags to add so installed ms_roblox_npc_behavior scripts drive this NPC."},
       "tags": {"type": "array", "items": {"type": "string"}}, "attributes": {"type": "object"},
       "nameplate": {"type": "boolean", "description": "Custom floating name/title plate (default true)."}, "animate": {"type": "boolean", "description": "Install the idle/walk animator (default true)."},
       "idle_animation": {"type": ["string", "number"]}, "walk_animation": {"type": ["string", "number"]},
       "anchored": {"type": "boolean"}, "snap_ground": {"type": "boolean", "description": "Drop the NPC onto the ground below position (default true)."},
       "parent": {"type": "string", "description": "Destination (default Workspace). Use ServerStorage.NPCs to keep a spawner template (missing folders are created)."}},
      [], writes=True)
def npc_builder(args, ctx):
    a = dict(args)
    preset = str(a.get("preset") or "villager").lower()
    if preset not in NPC_PRESETS:
        raise ToolkitError(f"unknown preset '{preset}'", "Use one of: " + ", ".join(sorted(NPC_PRESETS)))
    p = NPC_PRESETS[preset]
    ap = as_dict(a.get("appearance"))
    rig = str(a.get("rig") or "R15").upper()
    if rig not in ("R15", "R6"):
        raise ToolkitError("rig must be R15 or R6")
    idle_def, walk_def = _R15_ANIMS if rig == "R15" else _R6_ANIMS
    beh = []
    for b in as_list(a.get("behavior")):
        b = str(b).lower()
        if b not in BEHAVIOR_TAGS:
            raise ToolkitError(f"unknown behavior '{b}'", "Use: " + ", ".join(sorted(BEHAVIOR_TAGS)))
        beh.append(BEHAVIOR_TAGS[b])
    tags = ["MS_NPC"] + beh + [str(t) for t in as_list(a.get("tags")) if str(t).strip()]
    name = str(a.get("name") or preset.replace("_", " ").title()).strip() or "NPC"
    payload = {
        "name": name, "display_name": str(a.get("display_name") or name), "title": a.get("title"), "position": a.get("position") or [0, 5, 0], "facing": num(a.get("facing"), 0, -360, 360),
        "rig": rig, "user_id": int(a["user_id"]) if a.get("user_id") not in (None, "") else None,
        "skin": ap.get("skin") or p["skin"], "shirt": ap.get("shirt") or p["shirt"], "pants": ap.get("pants") or p["pants"],
        "shirt_id": re.sub(r"\D", "", str(ap.get("shirt_id") or "")), "pants_id": re.sub(r"\D", "", str(ap.get("pants_id") or "")), "tshirt_id": re.sub(r"\D", "", str(ap.get("tshirt_id") or "")),
        "face_id": re.sub(r"\D", "", str(ap.get("face_id") or "")), "hats": _ids_csv(ap.get("hats")), "hair": _ids_csv(ap.get("hair")),
        "acc": {k: _ids_csv(v) for k, v in as_dict(ap.get("accessories")).items() if _ids_csv(v)},
        "health": num(a.get("health"), p["health"], 1, 1e6), "walk_speed": num(a.get("walk_speed"), p["speed"], 0, 200), "jump_power": a.get("jump_power"),
        "scale": num(a.get("scale"), p["scale"], 0.1, 20), "tags": tags, "attributes": as_dict(a.get("attributes")), "preset": preset,
        "nameplate": a.get("nameplate") is not False, "anchored": bool(a.get("anchored")), "snap_ground": a.get("snap_ground") is not False,
        "parent": a.get("parent") or "Workspace", "animate": a.get("animate") is not False,
        "animate_src": _fill(_ANIMATE_SRC, {"idle": sound_id(a.get("idle_animation")) or idle_def, "walk": sound_id(a.get("walk_animation")) or walk_def, "ref_speed": 16 if rig == "R15" else 14}),
        "animate_src_r6": _fill(_ANIMATE_SRC, {"idle": sound_id(a.get("idle_animation")) or _R6_ANIMS[0], "walk": sound_id(a.get("walk_animation")) or _R6_ANIMS[1], "ref_speed": 14}),
        "dry_run": a.get("dry_run"), "studio_id": a.get("studio_id"), "mode": a.get("mode"),
    }
    return _exec(ctx, payload, _x(_LIB_MK + _LIB_INSTALL, '''
        local Players = game:GetService("Players")
        local function color(h) return hex(h) end
        local skin, shirt, pants = color(A.skin), color(A.shirt), color(A.pants)
        local hasShirt = (A.shirt_id ~= nil and A.shirt_id ~= "")
        local sleeves = hasShirt and skin or shirt
        local torsoC = hasShirt and skin or shirt
        local rigType = A.rig == "R6" and Enum.HumanoidRigType.R6 or Enum.HumanoidRigType.R15
        local model, method = nil, "mannequin"

        -- 1) avatar-service build
        local okD, desc = pcall(function()
            if A.user_id then return Players:GetHumanoidDescriptionFromUserId(A.user_id) end
            return Instance.new("HumanoidDescription")
        end)
        if okD and desc then
            local function try(prop, val) pcall(function() desc[prop] = val end) end
            if not A.user_id then
                try("HeadColor", skin); try("TorsoColor", torsoC); try("LeftArmColor", sleeves); try("RightArmColor", sleeves)
                try("LeftLegColor", pants); try("RightLegColor", pants)
                if A.shirt_id and A.shirt_id ~= "" then try("Shirt", tonumber(A.shirt_id)) end
                if A.pants_id and A.pants_id ~= "" then try("Pants", tonumber(A.pants_id)) end
                if A.tshirt_id and A.tshirt_id ~= "" then try("GraphicTShirt", tonumber(A.tshirt_id)) end
                if A.face_id and A.face_id ~= "" then try("Face", tonumber(A.face_id)) end
            end
            if A.hats and A.hats ~= "" then try("HatAccessory", A.hats) end
            if A.hair and A.hair ~= "" then try("HairAccessory", A.hair) end
            local slots = {neck = "NeckAccessory", front = "FrontAccessory", back = "BackAccessory", shoulders = "ShouldersAccessory", waist = "WaistAccessory"}
            for k, v in pairs(A.acc or {}) do if slots[k] then try(slots[k], v) end end
            local okM, m = pcall(function() return Players:CreateHumanoidModelFromDescription(desc, rigType) end)
            if okM and m then model = m; method = "avatar" end
        end

        -- 2) fallback: blocky R6 mannequin with proper Motor6D joints
        if not model then
            model = mk("Model", {Name = A.name})
            local function part(n, size, c, pos)
                return mk("Part", {Name = n, Size = size, Color = c, Position = pos, Anchored = false, CanCollide = n == "Torso" or n == "Head", TopSurface = enumOf("SurfaceType", "Smooth", "Smooth"), BottomSurface = enumOf("SurfaceType", "Smooth", "Smooth")}, model)
            end
            local hrp = part("HumanoidRootPart", Vector3.new(2, 2, 1), torsoC, Vector3.new(0, 3, 0))
            hrp.Transparency = 1; hrp.CanCollide = false
            local torso = part("Torso", Vector3.new(2, 2, 1), torsoC, Vector3.new(0, 3, 0))
            local head = part("Head", Vector3.new(2, 1, 1), skin, Vector3.new(0, 4.5, 0))
            mk("SpecialMesh", {MeshType = enumOf("MeshType", "Head", "Head"), Scale = Vector3.new(1.25, 1.25, 1.25)}, head)
            mk("Decal", {Name = "face", Texture = "rbxasset://textures/face.png", Face = enumOf("NormalId", "Front", "Front")}, head)
            local la = part("Left Arm", Vector3.new(1, 2, 1), sleeves, Vector3.new(-1.5, 3, 0))
            local ra = part("Right Arm", Vector3.new(1, 2, 1), sleeves, Vector3.new(1.5, 3, 0))
            local ll = part("Left Leg", Vector3.new(1, 2, 1), pants, Vector3.new(-0.5, 1, 0))
            local rl = part("Right Leg", Vector3.new(1, 2, 1), pants, Vector3.new(0.5, 1, 0))
            local function joint(n, p0, p1, c0, c1) return mk("Motor6D", {Name = n, Part0 = p0, Part1 = p1, C0 = c0, C1 = c1}, p0) end
            joint("RootJoint", hrp, torso, CFrame.new(0, 0, 0, -1, 0, 0, 0, 0, 1, 0, 1, 0), CFrame.new(0, 0, 0, -1, 0, 0, 0, 0, 1, 0, 1, 0))
            joint("Neck", torso, head, CFrame.new(0, 1, 0, -1, 0, 0, 0, 0, 1, 0, 1, 0), CFrame.new(0, -0.5, 0, -1, 0, 0, 0, 0, 1, 0, 1, 0))
            joint("Right Shoulder", torso, ra, CFrame.new(1, 0.5, 0, 0, 0, 1, 0, 1, 0, -1, 0, 0), CFrame.new(-0.5, 0.5, 0, 0, 0, 1, 0, 1, 0, -1, 0, 0))
            joint("Left Shoulder", torso, la, CFrame.new(-1, 0.5, 0, 0, 0, -1, 0, 1, 0, 1, 0, 0), CFrame.new(0.5, 0.5, 0, 0, 0, -1, 0, 1, 0, 1, 0, 0))
            joint("Right Hip", torso, rl, CFrame.new(1, -1, 0, 0, 0, 1, 0, 1, 0, -1, 0, 0), CFrame.new(0.5, 1, 0, 0, 0, 1, 0, 1, 0, -1, 0, 0))
            joint("Left Hip", torso, ll, CFrame.new(-1, -1, 0, 0, 0, -1, 0, 1, 0, 1, 0, 0), CFrame.new(-0.5, 1, 0, 0, 0, -1, 0, 1, 0, 1, 0, 0))
            local h = mk("Humanoid", {}, model)
            pcall(function() h.RigType = Enum.HumanoidRigType.R6 end)
            model.PrimaryPart = hrp
        end

        -- 3) tint plain bodies (avatar builds are coloured through the description)
        model.Name = A.name
        local hum = model:FindFirstChildOfClass("Humanoid")
        if not hum then error("the NPC model has no Humanoid") end
        hum.DisplayName = A.display_name
        hum.MaxHealth = A.health
        hum.Health = A.health
        hum.WalkSpeed = A.walk_speed
        if A.jump_power then pcall(function() hum.UseJumpPower = true; hum.JumpPower = A.jump_power end) end
        if A.nameplate then
            pcall(function() hum.DisplayDistanceType = Enum.HumanoidDisplayDistanceType.None end)
        end
        pcall(function() hum.HealthDisplayType = Enum.HumanoidHealthDisplayType.DisplayWhenDamaged end)

        -- 4) place
        local parent = parentFor(A.parent, true)
        local old = parent:FindFirstChild(A.name)
        if old and old:IsA("Model") then old:Destroy() end
        model.Parent = parent
        if A.scale ~= 1 then pcall(function() model:ScaleTo(A.scale) end) end
        local pos = vec3(A.position)
        model:PivotTo(CFrame.new(pos) * CFrame.Angles(0, math.rad(A.facing), 0))
        if A.snap_ground then
            local params = RaycastParams.new()
            params.FilterType = Enum.RaycastFilterType.Exclude
            params.FilterDescendantsInstances = {model}
            local hit = workspace:Raycast(pos + Vector3.new(0, 40, 0), Vector3.new(0, -400, 0), params)
            if hit then
                local cf, size = model:GetBoundingBox()
                local bottom = cf.Position.Y - size.Y / 2
                model:PivotTo(model:GetPivot() + Vector3.new(0, hit.Position.Y - bottom + 0.05, 0))
            end
        end
        local root = model:FindFirstChild("HumanoidRootPart")
        if A.anchored and root then root.Anchored = true end

        -- 5) name plate, tags, attributes, animator
        if A.nameplate then
            local head = model:FindFirstChild("Head")
            if head then
                local g = mk("BillboardGui", {Name = "MS_NamePlate", Size = UDim2.new(0, 200, 0, A.title and 52 or 30), StudsOffset = Vector3.new(0, 2.6, 0), AlwaysOnTop = false, MaxDistance = 60}, head)
                mk("TextLabel", {Name = "Name", BackgroundTransparency = 1, Size = UDim2.new(1, 0, A.title and 0.55 or 1, 0), Text = A.display_name, TextColor3 = Color3.new(1, 1, 1), TextStrokeTransparency = 0.4, TextScaled = true, Font = enumOf("Font", "GothamBold", "SourceSansBold")}, g)
                if A.title then
                    mk("TextLabel", {Name = "Title", BackgroundTransparency = 1, Position = UDim2.new(0, 0, 0.55, 0), Size = UDim2.new(1, 0, 0.45, 0), Text = A.title, TextColor3 = Color3.fromRGB(255, 214, 102), TextStrokeTransparency = 0.5, TextScaled = true, Font = enumOf("Font", "Gotham", "SourceSans")}, g)
                end
            end
        end
        for _, t in ipairs(A.tags) do CS:AddTag(model, t) end
        model:SetAttribute("MS_Preset", A.preset)
        for k, v in pairs(A.attributes or {}) do model:SetAttribute(k, v) end
        if A.animate then
            local old2 = model:FindFirstChild("NpcAnimate")
            if old2 then old2:Destroy() end
            local s = Instance.new("Script")
            s.Name = "NpcAnimate"; s.Source = (method == "mannequin") and A.animate_src_r6 or A.animate_src; s.Parent = model
        end
        R.npc = model:GetFullName(); R.method = method; R.rig = (method == "mannequin") and "R6" or A.rig; R.tags = A.tags
        R.position = {model:GetPivot().Position.X, model:GetPivot().Position.Y, model:GetPivot().Position.Z}
        if method == "mannequin" then R.note = "Avatar service unavailable here, so a blocky R6 mannequin was built (works with every behavior script)." end
        waypoint("npc " .. A.name)
    '''), "npc builder")


# ─────────────────────────────── NPC behaviour scripts ───────────────────────────────
_NPC_COMMON = '''local Players = game:GetService("Players")
local CS = game:GetService("CollectionService")
local RunService = game:GetService("RunService")
local PFS = game:GetService("PathfindingService")
local Debris = game:GetService("Debris")
local ServerStorage = game:GetService("ServerStorage")
local function onTagged(tag, fn)
    for _, i in ipairs(CS:GetTagged(tag)) do task.spawn(fn, i) end
    CS:GetInstanceAddedSignal(tag):Connect(function(i) task.spawn(fn, i) end)
end
local function attr(inst, name, default)
    local v = inst:GetAttribute(name)
    if v == nil then return default end
    return v
end
local function parts(npc)
    return npc:FindFirstChildOfClass("Humanoid"), npc:FindFirstChild("HumanoidRootPart")
end
local function claim(hrp) pcall(function() hrp:SetNetworkOwner(nil) end) end
local function ensureStat(player, name, initial)
    local ls = player:FindFirstChild("leaderstats")
    if not ls then ls = Instance.new("Folder"); ls.Name = "leaderstats"; ls.Parent = player end
    local v = ls:FindFirstChild(name)
    if not v then v = Instance.new("IntValue"); v.Name = name; v.Value = initial or 0; v.Parent = ls end
    return v
end
local function nearestPlayer(pos, maxDist)
    local best, bestD, bestChar, bestHum, bestHrp
    for _, p in ipairs(Players:GetPlayers()) do
        local c = p.Character
        local h = c and c:FindFirstChildOfClass("Humanoid")
        local r = c and c:FindFirstChild("HumanoidRootPart")
        if h and r and h.Health > 0 then
            local d = (r.Position - pos).Magnitude
            if d <= maxDist and (not bestD or d < bestD) then best, bestD, bestChar, bestHum, bestHrp = p, d, c, h, r end
        end
    end
    return best, bestD, bestChar, bestHum, bestHrp
end
local function hasLOS(fromPos, toPos, ignore)
    local params = RaycastParams.new()
    params.FilterType = Enum.RaycastFilterType.Exclude
    params.FilterDescendantsInstances = ignore
    return workspace:Raycast(fromPos, toPos - fromPos, params) == nil
end
local function say(npc, text, seconds)
    local head = npc:FindFirstChild("Head")
    if not head then return end
    local old = head:FindFirstChild("MS_Say")
    if old then old:Destroy() end
    local g = Instance.new("BillboardGui")
    g.Name = "MS_Say"; g.Size = UDim2.new(0, 240, 0, 56); g.StudsOffset = Vector3.new(0, 4.4, 0); g.AlwaysOnTop = true; g.MaxDistance = 70
    local t = Instance.new("TextLabel")
    t.Size = UDim2.new(1, 0, 1, 0); t.BackgroundColor3 = Color3.fromRGB(20, 20, 26); t.BackgroundTransparency = 0.2
    t.TextColor3 = Color3.new(1, 1, 1); t.TextScaled = true; t.Font = Enum.Font.GothamMedium; t.Text = tostring(text); t.Parent = g
    local c = Instance.new("UICorner"); c.CornerRadius = UDim.new(0, 10); c.Parent = t
    g.Parent = head
    Debris:AddItem(g, seconds or 4)
end
local function newPath()
    return PFS:CreatePath({AgentRadius = 2, AgentHeight = 5, AgentCanJump = true})
end
-- blocking walk with pathfinding and a direct-MoveTo fallback; returns true when it arrived
local function walkTo(npc, targetPos, timeout)
    local hum, hrp = parts(npc)
    if not hum or not hrp then return false end
    local deadline = os.clock() + (timeout or 20)
    local path = newPath()
    local ok = pcall(function() path:ComputeAsync(hrp.Position, targetPos) end)
    if ok and path.Status == Enum.PathStatus.Success then
        for _, wp in ipairs(path:GetWaypoints()) do
            if hum.Health <= 0 or os.clock() > deadline or not npc.Parent then return false end
            if wp.Action == Enum.PathWaypointAction.Jump then hum.Jump = true end
            hum:MoveTo(wp.Position)
            local reached = false
            local conn = hum.MoveToFinished:Connect(function() reached = true end)
            local t0 = os.clock()
            while not reached and os.clock() - t0 < 2.5 and hum.Health > 0 do task.wait(0.1) end
            conn:Disconnect()
            if not reached then break end
        end
    else
        hum:MoveTo(targetPos)
        local t0 = os.clock()
        while os.clock() - t0 < (timeout or 20) and hum.Health > 0 and npc.Parent do
            if (hrp.Position - targetPos).Magnitude < 4 then return true end
            task.wait(0.15)
        end
    end
    return (hrp.Position - targetPos).Magnitude < 6
end
-- one non-blocking chase tick: straight line when visible, otherwise follow a recomputed path
local function chaseStep(state, npc, targetHrp)
    local hum, hrp = parts(npc)
    local tp = targetHrp.Position
    if (hrp.Position - tp).Magnitude < 8 or hasLOS(hrp.Position, tp, {npc, targetHrp.Parent}) then
        state.wps = nil
        hum:MoveTo(tp)
        return
    end
    local now = os.clock()
    if not state.wps or now - (state.t or 0) > 1.2 then
        state.t = now
        local path = newPath()
        local ok = pcall(function() path:ComputeAsync(hrp.Position, tp) end)
        if ok and path.Status == Enum.PathStatus.Success then
            state.wps = path:GetWaypoints(); state.i = 2
        else
            state.wps = nil
            hum:MoveTo(tp)
            return
        end
    end
    local wp = state.wps and state.wps[state.i]
    if wp then
        if wp.Action == Enum.PathWaypointAction.Jump then hum.Jump = true end
        hum:MoveTo(wp.Position)
        local flat = Vector3.new(hrp.Position.X - wp.Position.X, 0, hrp.Position.Z - wp.Position.Z).Magnitude
        if flat < 4 then state.i = state.i + 1 end
    else
        hum:MoveTo(tp)
    end
end
local function respawnLater(npc, template, parent, cframe, seconds)
    if not template or seconds <= 0 then return end
    task.delay(seconds, function()
        local c = template:Clone()
        c.Parent = parent
        c:PivotTo(cframe)
    end)
end
local function alive(npc, hum) return npc.Parent ~= nil and hum.Health > 0 end
'''

_NB = {}
_NB["wander"] = ("NpcWander", '''-- Tag: NpcWander. Attributes: WanderRadius (@radius@), WalkSpeed, PauseMin/PauseMax (@pause_min@/@pause_max@).
onTagged("NpcWander", function(npc)
    local hum, hrp = parts(npc)
    if not hum or not hrp then return end
    claim(hrp)
    local home = hrp.Position
    local sp = attr(npc, "WalkSpeed", @speed@)
    if sp then hum.WalkSpeed = sp end
    local rng = Random.new()
    while alive(npc, hum) do
        local radius = attr(npc, "WanderRadius", @radius@)
        local ang = rng:NextNumber(0, math.pi * 2)
        local d = rng:NextNumber(radius * 0.3, radius)
        walkTo(npc, home + Vector3.new(math.cos(ang) * d, 0, math.sin(ang) * d), 12)
        task.wait(rng:NextNumber(attr(npc, "PauseMin", @pause_min@), attr(npc, "PauseMax", @pause_max@)))
    end
end)
''')
_NB["patrol"] = ("NpcPatrol", '''-- Tag: NpcPatrol. Walks through parts tagged "NpcPatrolPoint" (attribute Order, Wait; optional Group matching the NPC attribute PatrolGroup). Mode: @mode@ (loop | pingpong).
onTagged("NpcPatrol", function(npc)
    local hum, hrp = parts(npc)
    if not hum or not hrp then return end
    claim(hrp)
    local sp = attr(npc, "WalkSpeed", @speed@)
    if sp then hum.WalkSpeed = sp end
    local group = npc:GetAttribute("PatrolGroup")
    local i, dir = 0, 1
    while alive(npc, hum) do
        local pts = {}
        for _, p in ipairs(CS:GetTagged("NpcPatrolPoint")) do
            if group == nil or p:GetAttribute("Group") == group then table.insert(pts, p) end
        end
        table.sort(pts, function(a, b)
            local oa, ob = attr(a, "Order", 0), attr(b, "Order", 0)
            if oa ~= ob then return oa < ob end
            return a.Name < b.Name
        end)
        if #pts == 0 then
            task.wait(1)
        else
            if attr(npc, "PatrolMode", @mode@) == "pingpong" then
                i = i + dir
                if i > #pts then dir = -1; i = math.max(#pts - 1, 1) elseif i < 1 then dir = 1; i = math.min(2, #pts) end
            else
                i = i % #pts + 1
            end
            local p = pts[i]
            walkTo(npc, p.Position, 25)
            task.wait(attr(p, "Wait", @pause@))
        end
    end
end)
''')
_NB["follow"] = ("NpcFollow", '''-- Tag: NpcFollow. Follows attribute Owner (player name) or else the nearest player within SeeRange (@range@); keeps FollowDistance (@distance@); teleports when farther than @teleport@ studs.
onTagged("NpcFollow", function(npc)
    local hum, hrp = parts(npc)
    if not hum or not hrp then return end
    claim(hrp)
    local sp = attr(npc, "WalkSpeed", @speed@)
    if sp then hum.WalkSpeed = sp end
    local state = {}
    while alive(npc, hum) do
        local target
        local owner = npc:GetAttribute("Owner")
        if owner then
            local p = Players:FindFirstChild(owner)
            target = p and p.Character and p.Character:FindFirstChild("HumanoidRootPart")
        end
        if not target then
            local _, _, _, _, r = nearestPlayer(hrp.Position, attr(npc, "SeeRange", @range@))
            target = r
        end
        if target then
            local keep = attr(npc, "FollowDistance", @distance@)
            local d = (target.Position - hrp.Position).Magnitude
            if d > @teleport@ then
                npc:PivotTo(target.CFrame * CFrame.new(3, 0, 3))
            elseif d > keep + 2 then
                chaseStep(state, npc, target)
            elseif d < keep - 1 then
                hum:MoveTo(hrp.Position)
            end
        end
        task.wait(0.2)
    end
end)
''')
_NB["guard"] = ("NpcGuard", '''-- Tag: NpcGuard. Holds its post; challenges players inside AggroRange (@aggro@), attacks inside Reach (@reach@) for Damage (@damage@), gives up beyond Leash (@leash@) and walks back.
onTagged("NpcGuard", function(npc)
    local hum, hrp = parts(npc)
    if not hum or not hrp then return end
    claim(hrp)
    local post = hrp.Position
    local sp = attr(npc, "WalkSpeed", @speed@)
    if sp then hum.WalkSpeed = sp end
    local state, last, warned = {}, -1e9, nil
    while alive(npc, hum) do
        local plr, dist, char, thum, thrp = nearestPlayer(hrp.Position, attr(npc, "AggroRange", @aggro@))
        if plr and (thrp.Position - post).Magnitude <= attr(npc, "Leash", @leash@) then
            if warned ~= plr then warned = plr; say(npc, attr(npc, "WarnText", @warn@), 3) end
            if dist <= attr(npc, "Reach", @reach@) then
                hum:MoveTo(hrp.Position)
                if os.clock() - last >= attr(npc, "Cooldown", @cooldown@) then
                    last = os.clock()
                    thum:TakeDamage(attr(npc, "Damage", @damage@))
                end
            else
                chaseStep(state, npc, thrp)
            end
        else
            warned = nil
            if (hrp.Position - post).Magnitude > 4 then hum:MoveTo(post) end
        end
        task.wait(0.2)
    end
end)
''')
_NB["enemy_melee"] = ("NpcEnemy", '''-- Tag: NpcEnemy. Roams near home, chases players inside AggroRange (@aggro@), hits for Damage (@damage@) every Cooldown (@cooldown@)s. Death: Reward (@reward@) of leaderstat "@stat@" to the nearest player, respawn after Respawn (@respawn@)s (0 = never).
onTagged("NpcEnemy", function(npc)
    local hum, hrp = parts(npc)
    if not hum or not hrp then return end
    claim(hrp)
    local home = hrp.Position
    local homeCF = hrp.CFrame
    local parent = npc.Parent
    local template = npc:Clone()
    local sp = attr(npc, "WalkSpeed", @speed@)
    if sp then hum.WalkSpeed = sp end
    hum.Died:Connect(function()
        local plr = nearestPlayer(hrp.Position, 90)
        local reward = attr(npc, "Reward", @reward@)
        if plr and reward > 0 then
            local s = ensureStat(plr, attr(npc, "RewardStat", @stat@), 0)
            s.Value = s.Value + reward
        end
        Debris:AddItem(npc, 3)
        respawnLater(npc, template, parent, homeCF, attr(npc, "Respawn", @respawn@))
    end)
    local state, last = {}, -1e9
    local rng = Random.new()
    local nextRoam = 0
    while alive(npc, hum) do
        local plr, dist, char, thum, thrp = nearestPlayer(hrp.Position, attr(npc, "AggroRange", @aggro@))
        if plr then
            if dist <= attr(npc, "Reach", @reach@) then
                hum:MoveTo(hrp.Position)
                if os.clock() - last >= attr(npc, "Cooldown", @cooldown@) then
                    last = os.clock()
                    thum:TakeDamage(attr(npc, "Damage", @damage@))
                end
            else
                chaseStep(state, npc, thrp)
            end
        elseif os.clock() >= nextRoam then
            nextRoam = os.clock() + rng:NextNumber(3, 7)
            local ang = rng:NextNumber(0, math.pi * 2)
            hum:MoveTo(home + Vector3.new(math.cos(ang), 0, math.sin(ang)) * rng:NextNumber(4, attr(npc, "RoamRadius", @roam@)))
        end
        task.wait(0.2)
    end
end)
''')
_NB["enemy_ranged"] = ("NpcShooter", '''-- Tag: NpcShooter. Keeps KeepDistance (@keep@) from players inside Range (@range@), needs line of sight, hitscan Damage (@damage@) every Cooldown (@cooldown@)s with Accuracy (@accuracy@). Reward (@reward@) of "@stat@", Respawn (@respawn@)s.
local function tracer(a, b)
    local len = (b - a).Magnitude
    if len < 0.5 then return end
    local p = Instance.new("Part")
    p.Anchored = true; p.CanCollide = false; p.CanQuery = false; p.CanTouch = false
    p.Material = Enum.Material.Neon; p.Color = Color3.fromRGB(255, 200, 80)
    p.Size = Vector3.new(0.15, 0.15, len)
    p.CFrame = CFrame.lookAt(a, b) * CFrame.new(0, 0, -len / 2)
    p.Parent = workspace
    Debris:AddItem(p, 0.08)
end
onTagged("NpcShooter", function(npc)
    local hum, hrp = parts(npc)
    if not hum or not hrp then return end
    claim(hrp)
    local homeCF = hrp.CFrame
    local parent = npc.Parent
    local template = npc:Clone()
    local sp = attr(npc, "WalkSpeed", @speed@)
    if sp then hum.WalkSpeed = sp end
    hum.Died:Connect(function()
        local plr = nearestPlayer(hrp.Position, 90)
        local reward = attr(npc, "Reward", @reward@)
        if plr and reward > 0 then
            local s = ensureStat(plr, attr(npc, "RewardStat", @stat@), 0)
            s.Value = s.Value + reward
        end
        Debris:AddItem(npc, 3)
        respawnLater(npc, template, parent, homeCF, attr(npc, "Respawn", @respawn@))
    end)
    local state, last = {}, -1e9
    while alive(npc, hum) do
        local plr, dist, char, thum, thrp = nearestPlayer(hrp.Position, attr(npc, "Range", @range@))
        if plr then
            local head = npc:FindFirstChild("Head") or hrp
            local keep = attr(npc, "KeepDistance", @keep@)
            if hasLOS(head.Position, thrp.Position, {npc, char}) then
                if dist < keep - 4 then
                    local away = hrp.Position - thrp.Position
                    hum:MoveTo(hrp.Position + Vector3.new(away.X, 0, away.Z).Unit * 10)
                elseif dist > keep + 6 then
                    hum:MoveTo(thrp.Position)
                else
                    hum:MoveTo(hrp.Position)
                    hrp.CFrame = CFrame.lookAt(hrp.Position, Vector3.new(thrp.Position.X, hrp.Position.Y, thrp.Position.Z))
                end
                if os.clock() - last >= attr(npc, "Cooldown", @cooldown@) then
                    last = os.clock()
                    if math.random() <= attr(npc, "Accuracy", @accuracy@) then thum:TakeDamage(attr(npc, "Damage", @damage@)) end
                    tracer(head.Position, thrp.Position + Vector3.new(0, 0.5, 0))
                end
            else
                chaseStep(state, npc, thrp)
            end
        end
        task.wait(0.2)
    end
end)
''')
_NB["flee"] = ("NpcFlee", '''-- Tag: NpcFlee. Runs away (FleeSpeed @flee_speed@) from players inside FearRange (@range@), otherwise strolls near home.
onTagged("NpcFlee", function(npc)
    local hum, hrp = parts(npc)
    if not hum or not hrp then return end
    claim(hrp)
    local home = hrp.Position
    local calm = attr(npc, "WalkSpeed", hum.WalkSpeed)
    local rng = Random.new()
    local nextStroll = 0
    while alive(npc, hum) do
        local plr, dist, char, thum, thrp = nearestPlayer(hrp.Position, attr(npc, "FearRange", @range@))
        if plr then
            hum.WalkSpeed = attr(npc, "FleeSpeed", @flee_speed@)
            local away = hrp.Position - thrp.Position
            away = Vector3.new(away.X, 0, away.Z)
            if away.Magnitude < 0.1 then away = Vector3.new(1, 0, 0) end
            hum:MoveTo(hrp.Position + away.Unit * 25)
        else
            hum.WalkSpeed = calm
            if os.clock() >= nextStroll then
                nextStroll = os.clock() + rng:NextNumber(3, 8)
                local ang = rng:NextNumber(0, math.pi * 2)
                hum:MoveTo(home + Vector3.new(math.cos(ang), 0, math.sin(ang)) * rng:NextNumber(3, 14))
            end
        end
        task.wait(0.2)
    end
end)
''')
_NB["merchant"] = ("NpcMerchant", '''-- Tag: NpcMerchant. Two ProximityPrompts: "Next item" (E) and "Buy" (F). Currency = leaderstat "@currency@". Items: {name, price, tool = Tool in ServerStorage.@tools_folder@} | {name, price, heal = n} | {name, price, stat, amount}.
local STOCK = @stock@
local function itemText(it) return it.name .. " - " .. it.price .. " @currency@" end
onTagged("NpcMerchant", function(npc)
    local hum, hrp = parts(npc)
    if not hrp or #STOCK == 0 then return end
    claim(hrp)
    local selected = 1
    local att = Instance.new("Attachment"); att.Name = "MS_ShopAtt"; att.Parent = hrp
    local nextP = Instance.new("ProximityPrompt")
    nextP.ObjectText = npc.Name; nextP.KeyboardKeyCode = Enum.KeyCode.E; nextP.HoldDuration = 0; nextP.MaxActivationDistance = 10; nextP.RequiresLineOfSight = false; nextP.Parent = att
    local buyP = Instance.new("ProximityPrompt")
    buyP.ObjectText = npc.Name; buyP.KeyboardKeyCode = Enum.KeyCode.F; buyP.HoldDuration = 0.2; buyP.MaxActivationDistance = 10; buyP.RequiresLineOfSight = false
    buyP.UIOffset = Vector2.new(0, 80); buyP.Parent = att
    local function refresh()
        nextP.ActionText = "Next item (" .. selected .. "/" .. #STOCK .. ")"
        buyP.ActionText = "Buy " .. itemText(STOCK[selected])
    end
    refresh()
    nextP.Triggered:Connect(function(plr)
        selected = selected % #STOCK + 1
        refresh()
        say(npc, itemText(STOCK[selected]), 3)
    end)
    buyP.Triggered:Connect(function(plr)
        local it = STOCK[selected]
        local money = ensureStat(plr, "@currency@", 0)
        if money.Value < it.price then
            say(npc, "You need " .. (it.price - money.Value) .. " more @currency@.", 3)
            return
        end
        if it.tool then
            local folder = ServerStorage:FindFirstChild("@tools_folder@")
            local tool = folder and folder:FindFirstChild(it.tool)
            if not tool then say(npc, "Sorry, that is out of stock.", 3) return end
            money.Value = money.Value - it.price
            tool:Clone().Parent = plr:FindFirstChildOfClass("Backpack") or plr
            pcall(function() tool:Clone().Parent = plr:FindFirstChild("StarterGear") end)
        elseif it.heal then
            local h = plr.Character and plr.Character:FindFirstChildOfClass("Humanoid")
            if not h then return end
            money.Value = money.Value - it.price
            h.Health = math.min(h.MaxHealth, h.Health + it.heal)
        else
            money.Value = money.Value - it.price
            local s = ensureStat(plr, it.stat or it.name, 0)
            s.Value = s.Value + (it.amount or 1)
        end
        say(npc, attr(npc, "ThanksText", @thanks@), 2)
    end)
end)
''')
_NB["quest_giver"] = ("NpcQuest", '''-- Tag: NpcQuest. ProximityPrompt "Talk". Quests run in order; progress = how much leaderstat `stat` rose since accepting. Reward goes to leaderstat "@reward_stat@" (quest.reward_stat overrides).
-- Progress is kept per session; save it with your own DataStore code if you need persistence.
local QUESTS = @quests@
onTagged("NpcQuest", function(npc)
    local hum, hrp = parts(npc)
    if not hrp then return end
    claim(hrp)
    local progress = {}
    local prompt = Instance.new("ProximityPrompt")
    prompt.ActionText = "Talk"; prompt.ObjectText = npc.Name; prompt.HoldDuration = 0; prompt.MaxActivationDistance = 10; prompt.RequiresLineOfSight = false
    prompt.Parent = hrp
    prompt.Triggered:Connect(function(plr)
        local st = progress[plr.UserId]
        if not st then st = {index = 1}; progress[plr.UserId] = st end
        local q = QUESTS[st.index]
        if not q then say(npc, attr(npc, "DoneText", @done_text@), 4) return end
        local stat = ensureStat(plr, q.stat, 0)
        if st.base == nil then
            st.base = stat.Value
            plr:SetAttribute("MS_Quest", q.title .. " 0/" .. q.amount)
            say(npc, q.title .. ": " .. (q.text or ""), 6)
        else
            local cur = stat.Value - st.base
            if cur >= q.amount then
                local r = ensureStat(plr, q.reward_stat or "@reward_stat@", 0)
                r.Value = r.Value + (q.reward or 0)
                st.index = st.index + 1; st.base = nil
                plr:SetAttribute("MS_Quest", "")
                say(npc, "Quest complete! +" .. (q.reward or 0) .. " " .. (q.reward_stat or "@reward_stat@"), 5)
            else
                plr:SetAttribute("MS_Quest", q.title .. " " .. cur .. "/" .. q.amount)
                say(npc, q.title .. ": " .. cur .. "/" .. q.amount, 4)
            end
        end
    end)
end)
''')
_NB["dialogue"] = ("NpcDialogue", '''-- Tag: NpcDialogue. ProximityPrompt "Talk" shows each line as a speech bubble (LineSeconds @seconds@). Override lines per NPC with attribute Lines ("one|two|three").
local LINES = @lines@
onTagged("NpcDialogue", function(npc)
    local hum, hrp = parts(npc)
    if not hrp then return end
    claim(hrp)
    local prompt = Instance.new("ProximityPrompt")
    prompt.ActionText = "Talk"; prompt.ObjectText = npc.Name; prompt.HoldDuration = 0; prompt.MaxActivationDistance = 10; prompt.RequiresLineOfSight = false
    prompt.Parent = hrp
    local busy = false
    prompt.Triggered:Connect(function(plr)
        if busy then return end
        busy = true
        local lines = LINES
        local custom = npc:GetAttribute("Lines")
        if type(custom) == "string" and custom ~= "" then
            lines = {}
            for piece in string.gmatch(custom, "[^|]+") do table.insert(lines, piece) end
        end
        local char = plr.Character
        local pr = char and char:FindFirstChild("HumanoidRootPart")
        if pr then hrp.CFrame = CFrame.lookAt(hrp.Position, Vector3.new(pr.Position.X, hrp.Position.Y, pr.Position.Z)) end
        if @random@ then
            if #lines > 0 then say(npc, lines[math.random(1, #lines)], attr(npc, "LineSeconds", @seconds@)) end
            task.wait(attr(npc, "LineSeconds", @seconds@))
        else
            for _, line in ipairs(lines) do
                say(npc, line, attr(npc, "LineSeconds", @seconds@))
                task.wait(attr(npc, "LineSeconds", @seconds@))
            end
        end
        busy = false
    end)
end)
''')
_NB["spawner"] = ("NpcSpawner", '''-- Tag: NpcSpawner (on a Part). Clones Model Template (@template@) from ServerStorage.@folder@ near the part every Interval (@interval@)s up to Max (@max@) alive; only while a player is within ActiveRange (@active@).
onTagged("NpcSpawner", function(part)
    local alive_list = {}
    local rng = Random.new()
    while part.Parent do
        for i = #alive_list, 1, -1 do
            local m = alive_list[i]
            local h = m.Parent and m:FindFirstChildOfClass("Humanoid")
            if not h or h.Health <= 0 then table.remove(alive_list, i) end
        end
        local folder = ServerStorage:FindFirstChild("@folder@")
        local tpl = folder and folder:FindFirstChild(attr(part, "Template", @template@))
        local near = nearestPlayer(part.Position, attr(part, "ActiveRange", @active@))
        if tpl and near and #alive_list < attr(part, "Max", @max@) then
            local c = tpl:Clone()
            c.Parent = workspace
            local r = attr(part, "Radius", @radius@)
            local ang = rng:NextNumber(0, math.pi * 2)
            c:PivotTo(CFrame.new(part.Position + Vector3.new(math.cos(ang) * rng:NextNumber(0, r), 3, math.sin(ang) * rng:NextNumber(0, r))))
            table.insert(alive_list, c)
        end
        task.wait(attr(part, "Interval", @interval@))
    end
end)
''')

_NB_DEFAULTS = {
    "wander": {"radius": 30, "speed": None, "pause_min": 2, "pause_max": 6},
    "patrol": {"speed": None, "pause": 1.5, "mode": "loop"},
    "follow": {"speed": None, "range": 60, "distance": 7, "teleport": 120},
    "guard": {"speed": None, "aggro": 28, "reach": 5, "damage": 12, "cooldown": 1.2, "leash": 45, "warn": "Halt! Who goes there?"},
    "enemy_melee": {"speed": None, "aggro": 45, "reach": 5, "damage": 10, "cooldown": 1.2, "reward": 10, "stat": "Coins", "respawn": 15, "roam": 14},
    "enemy_ranged": {"speed": None, "range": 70, "keep": 28, "damage": 8, "cooldown": 1.6, "accuracy": 0.65, "reward": 15, "stat": "Coins", "respawn": 20},
    "flee": {"range": 22, "flee_speed": 24},
    "merchant": {"currency": "Coins", "tools_folder": "Tools", "thanks": "Pleasure doing business!",
                 "stock": [{"name": "Health Potion", "price": 25, "heal": 50}, {"name": "Big Potion", "price": 60, "heal": 100}]},
    "quest_giver": {"reward_stat": "Coins", "done_text": "You have done everything I asked. Thank you!",
                    "quests": [{"title": "Coin Collector", "text": "Collect 10 coins for me.", "stat": "Coins", "amount": 10, "reward": 50}]},
    "dialogue": {"lines": ["Hello, traveller!", "Nice weather today."], "seconds": 3, "random": False},
    "spawner": {"template": "Zombie", "folder": "NPCs", "interval": 8, "max": 5, "active": 150, "radius": 12},
}
_NB_HELP = {
    "wander": "NPCs tagged NpcWander stroll around their start point (attributes WanderRadius, PauseMin/Max, WalkSpeed).",
    "patrol": "NPCs tagged NpcPatrol walk through NpcPatrolPoint parts (create them with `points`; attributes Order, Wait, Group; NPC attr PatrolGroup/PatrolMode loop|pingpong).",
    "follow": "NPCs tagged NpcFollow follow the nearest player or attribute Owner (pet/companion), teleporting if left behind.",
    "guard": "NPCs tagged NpcGuard hold a post, warn then attack nearby players and walk back past their Leash.",
    "enemy_melee": "NPCs tagged NpcEnemy roam, chase and bite; death gives Reward to the nearest player and respawns from a clone.",
    "enemy_ranged": "NPCs tagged NpcShooter keep distance, need line of sight and fire hitscan shots with a tracer; same reward/respawn.",
    "flee": "NPCs tagged NpcFlee run from players within FearRange (prey animals, scared villagers).",
    "merchant": "NPCs tagged NpcMerchant get Next/Buy prompts selling options.stock (tool from ServerStorage, heal, or stat items) for leaderstat currency.",
    "quest_giver": "NPCs tagged NpcQuest hand out options.quests in order (kill/collect style: a leaderstat must rise by amount) and pay a reward.",
    "dialogue": "NPCs tagged NpcDialogue show options.lines as speech bubbles from a Talk prompt (or attribute Lines 'a|b|c').",
    "spawner": "Parts tagged NpcSpawner clone a template NPC from ServerStorage.NPCs on a timer (Max alive, ActiveRange).",
}
NPC_KINDS = sorted(_NB)
_NB_STYLE = {"spawner": ("#ff8a00", "Neon", [4, 0.4, 4]), "patrol_point": ("#4dd2ff", "Neon", [1.5, 0.3, 1.5])}


def _npc_source(kind, opts):
    tag, body = _NB[kind]
    merged = dict(_NB_DEFAULTS.get(kind, {}))
    merged.update({k: v for k, v in opts.items() if v is not None})
    if kind == "merchant":
        stock = []
        for it in as_list(merged.get("stock")):
            it = as_dict(it)
            if not it.get("name") or it.get("price") is None:
                raise ToolkitError("each stock item needs name and price")
            stock.append({k: v for k, v in it.items() if v is not None})
        merged["stock"] = stock
    if kind == "quest_giver":
        qs = []
        for q in as_list(merged.get("quests")):
            q = as_dict(q)
            if not q.get("title") or not q.get("stat") or q.get("amount") is None:
                raise ToolkitError("each quest needs title, stat and amount", "stat is the leaderstat that must rise, e.g. Kills or Coins.")
            qs.append({k: v for k, v in q.items() if v is not None})
        merged["quests"] = qs
    if kind == "dialogue":
        merged["lines"] = [str(x) for x in as_list(merged.get("lines"))]
    for k in ("currency", "tools_folder", "stat", "reward_stat", "folder"):
        if k in merged and not re.fullmatch(r"[A-Za-z0-9_ ]{1,40}", str(merged[k])):
            raise ToolkitError(f"option {k} must be a plain name (letters, digits, spaces, underscores)")
    # strings that are embedded inside quotes in the templates (currency/tools_folder/stat/reward_stat/folder) are substituted raw
    raw = {}
    for k in ("currency", "tools_folder", "reward_stat", "folder"):
        if k in merged:
            raw[k] = str(merged.pop(k))
    for k, v in raw.items():
        body = body.replace('"@' + k + '@"', _lit(v)).replace("@" + k + "@", v)
    merged["random"] = bool(merged.get("random"))
    if "stat" in merged:
        merged["stat"] = str(merged["stat"])
    return tag, _NPC_COMMON + _fill(body, merged), merged


@tool(RB, "ms_roblox_npc_behavior",
      "Install NPC AI as tag-driven Scripts. kind: wander, patrol, follow, guard, enemy_melee, enemy_ranged, flee, merchant (Next/Buy prompts), quest_giver (stat-delta quests), dialogue, spawner. Pathfinding with direct-move fallback; attributes on the NPC override `options` live. "
      "`targets` are NPC models (or spawner markers); `points` creates patrol markers.",
      {"kind": {"type": "string", "enum": NPC_KINDS}, "targets": PATHS, "options": {"type": "object", "description": "e.g. {damage:15, aggro:40, reward:20} (enemy), {stock:[{name,price,tool|heal}], currency:'Coins'} (merchant), {quests:[{title,text,stat,amount,reward}]} (quest_giver), {lines:[...]} (dialogue)."},
       "attributes": {"type": "object", "description": "Attributes set on the targets (WalkSpeed, Damage, AggroRange, Owner...)."},
       "points": {"type": "array", "items": VEC, "description": "patrol: positions for NpcPatrolPoint markers to create (in order)."}, "group": {"type": "string", "description": "patrol: Group attribute for created points."},
       "position": VEC, "name": {"type": "string"}, "script_parent": {"type": "string"}},
      ["kind"], writes=True)
def npc_behavior(args, ctx):
    a = dict(args)
    kind = str(a.get("kind") or "").lower()
    if kind not in _NB:
        raise ToolkitError(f"unknown kind '{kind}'", "Use one of: " + ", ".join(NPC_KINDS))
    tag, src, merged = _npc_source(kind, as_dict(a.get("options")))
    if kind != "spawner" and not a.get("targets") and not (kind == "patrol" and a.get("points")):
        raise ToolkitError("targets are required: the NPC model paths to drive", "Build NPCs with ms_roblox_npc_builder (they get the MS_NPC tag) and pass their paths.")
    points = [list(p) for p in as_list(a.get("points")) if isinstance(p, (list, tuple)) and len(p) == 3]
    payload = {"kind": kind, "tag": tag, "extra_tags": ["MS_NPC"] if kind != "spawner" else [], "targets": _paths(a, "targets") if a.get("targets") else [], "attributes": as_dict(a.get("attributes")),
               "position": a.get("position"), "style": list(_NB_STYLE["spawner"]) if kind == "spawner" else None, "points": points, "group": a.get("group"),
               "scripts": [{"class": "Script", "name": str(a.get("name") or "MS_Npc" + "".join(w.title() for w in kind.split("_"))), "parent_path": a.get("script_parent") or "ServerScriptService", "source": src}],
               "dry_run": a.get("dry_run"), "studio_id": a.get("studio_id"), "mode": a.get("mode")}
    res = _exec(ctx, payload, _x(_LIB_MK + _LIB_INSTALL, '''
        R.kind = A.kind
        R.installed = installScripts(A.scripts)
        R.tagged = tagAndPlace(A)
        R.tag = A.tag
        if #(A.points or {}) > 0 then
            local folder = workspace:FindFirstChild("MS_NPC_PatrolPoints") or mk("Folder", {Name = "MS_NPC_PatrolPoints"}, workspace)
            local made = {}
            for i, p in ipairs(A.points) do
                local part = mk("Part", {Name = "PatrolPoint_" .. i, Anchored = true, CanCollide = false, Size = Vector3.new(1.5, 0.3, 1.5), Position = vec3(p), Color = hex("#4dd2ff"), Material = enumOf("Material", "Neon", "Plastic"), Transparency = 0.4}, folder)
                part:SetAttribute("Order", i)
                if A.group then part:SetAttribute("Group", A.group) end
                CS:AddTag(part, "NpcPatrolPoint")
                table.insert(made, part:GetFullName())
            end
            R.points = made
        end
        waypoint("npc behavior " .. A.kind)
    '''), "npc behavior " + kind)
    if isinstance(res, dict):
        res["usage"] = _NB_HELP[kind]
    return res


# ─────────────────────────────── NPC manage ───────────────────────────────
NPC_ACTIONS = ["list", "inspect", "configure", "spawn_crowd", "remove", "audit", "snap_to_ground"]


@tool(RB, "ms_roblox_npc_manage",
      "Manage NPCs (humanoid models that are not players). action: list; inspect; configure (health/speed/jump/name/scale/tags/attributes); spawn_crowd (scatter/ring/grid clones with random scale and tint); remove; audit (no root, dead, void, floating, non-archivable, no behaviour, too many AIs; apply=true fixes safe ones); snap_to_ground.",
      {"action": {"type": "string", "enum": NPC_ACTIONS}, "paths": PATHS, "path": PATH, "tag": {"type": "string", "description": "Select NPCs by tag instead of paths (default MS_NPC for list/audit)."},
       "root": {"type": "string", "description": "list/audit: where to look (default Workspace)."},
       "health": {"type": "number"}, "walk_speed": {"type": "number"}, "jump_power": {"type": "number"}, "display_name": {"type": "string"}, "scale": {"type": "number"},
       "add_tags": {"type": "array", "items": {"type": "string"}}, "remove_tags": {"type": "array", "items": {"type": "string"}}, "attributes": {"type": "object"},
       "template": {"type": "string", "description": "spawn_crowd: path of the NPC model to clone."}, "count": {"type": "integer", "minimum": 1, "maximum": 200},
       "center": VEC, "radius": {"type": "number"}, "layout": {"type": "string", "enum": ["scatter", "ring", "grid"]}, "spacing": {"type": "number"},
       "scale_range": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}, "randomize_colors": {"type": "boolean"}, "seed": {"type": "integer"},
       "parent": {"type": "string", "description": "spawn_crowd: destination (default Workspace.MS_Crowd)."}, "name_prefix": {"type": "string"},
       "apply": {"type": "boolean", "description": "audit: apply safe fixes (snap floating NPCs, set Archivable, set PrimaryPart)."}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}},
      ["action"], writes=True)
def npc_manage(args, ctx):
    a = dict(args)
    act = str(a.get("action") or "").lower()
    if act not in NPC_ACTIONS:
        raise ToolkitError(f"unknown action '{act}'", "Use one of: " + ", ".join(NPC_ACTIONS))
    a["action"] = act
    a["paths"] = _paths(a, "paths", "path")
    a["limit"] = num(a.get("limit"), 200, 1, 500, True)
    a["add_tags"] = [str(x) for x in as_list(a.get("add_tags"))]
    a["remove_tags"] = [str(x) for x in as_list(a.get("remove_tags"))]
    a["attributes"] = as_dict(a.get("attributes"))
    if act == "spawn_crowd":
        if not a.get("template"):
            raise ToolkitError("spawn_crowd needs `template`", "Build one with ms_roblox_npc_builder first.")
        a["count"] = num(a.get("count"), 10, 1, 200, True)
        a["radius"] = num(a.get("radius"), 30, 1, 2000)
        a["spacing"] = num(a.get("spacing"), 6, 1, 200)
        a["center"] = a.get("center") or [0, 5, 0]
        a["layout"] = str(a.get("layout") or "scatter")
        sr = [float(x) for x in as_list(a.get("scale_range"))][:2]
        a["scale_range"] = sr if len(sr) == 2 else None
        a["seed"] = int(num(a.get("seed"), 7, 0, 1e9))
    if act in ("inspect", "remove", "snap_to_ground", "configure") and not a["paths"] and not a.get("tag"):
        raise ToolkitError(f"{act} needs `paths` (or `tag`)")
    return _exec(ctx, a, _x(_LIB_MK, '''
        local Players = game:GetService("Players")
        local CS = game:GetService("CollectionService")
        local act = A.action
        local function isPlayerChar(m)
            local ok, p = pcall(function() return Players:GetPlayerFromCharacter(m) end)
            return ok and p ~= nil
        end
        local function hasTag(i, t)
            local ok, r = pcall(function() return CS:HasTag(i, t) end)
            return ok and r
        end
        local function tagsOf(i)
            local ok, r = pcall(function() return CS:GetTags(i) end)
            return ok and r or {}
        end
        local function isNpc(m)
            return m:IsA("Model") and m:FindFirstChildOfClass("Humanoid") ~= nil and not isPlayerChar(m)
        end
        local function behaviours(m)
            local out = {}
            for _, t in ipairs(tagsOf(m)) do if string.sub(t, 1, 3) == "Npc" then table.insert(out, t) end end
            return out
        end
        local function findNpcs()
            local out = {}
            if #(A.paths or {}) > 0 then
                for _, p in ipairs(A.paths) do out[#out + 1] = resolve(p) end
                return out
            end
            local root = A.root and resolve(A.root) or workspace
            local want = A.tag
            for _, d in ipairs(root:GetDescendants()) do
                if d:IsA("Model") then
                    if want then if hasTag(d, want) then out[#out + 1] = d end
                    elseif isNpc(d) then out[#out + 1] = d end
                end
            end
            if want then
                local ok, tagged = pcall(function() return CS:GetTagged(want) end)
                if ok then for _, t in ipairs(tagged) do local seen = false for _, x in ipairs(out) do if x == t then seen = true end end if not seen and t:IsDescendantOf(root) then out[#out + 1] = t end end end
            end
            return out
        end
        local function pos(m)
            local p = m:GetPivot().Position
            return {p.X, p.Y, p.Z}
        end
        local function groundSnap(m)
            local params = RaycastParams.new()
            params.FilterType = Enum.RaycastFilterType.Exclude
            params.FilterDescendantsInstances = {m}
            local p = m:GetPivot().Position
            local hit = workspace:Raycast(p + Vector3.new(0, 40, 0), Vector3.new(0, -500, 0), params)
            if not hit then return false end
            local cf, size = m:GetBoundingBox()
            local bottom = cf.Position.Y - size.Y / 2
            m:PivotTo(m:GetPivot() + Vector3.new(0, hit.Position.Y - bottom + 0.05, 0))
            return true
        end

        if act == "list" then
            local rows = {}
            local all = findNpcs()
            for _, m in ipairs(all) do
                if #rows < A.limit then
                    local h = m:FindFirstChildOfClass("Humanoid")
                    table.insert(rows, {path = m:GetFullName(), name = m.Name, health = h and h.Health, maxHealth = h and h.MaxHealth, walkSpeed = h and h.WalkSpeed, rig = h and tostring(h.RigType) or nil,
                        behaviours = behaviours(m), position = pos(m)})
                end
            end
            R.npcs = rows; R.count = #all
            if #all > A.limit then R.truncated = true end

        elseif act == "inspect" then
            local out = {}
            for _, m in ipairs(findNpcs()) do
                local h = m:FindFirstChildOfClass("Humanoid")
                local scripts, accessories = {}, {}
                for _, d in ipairs(m:GetDescendants()) do
                    if d:IsA("LuaSourceContainer") then table.insert(scripts, d.Name) end
                    if d:IsA("Accessory") then table.insert(accessories, d.Name) end
                end
                table.insert(out, {path = m:GetFullName(), class = m.ClassName, health = h and h.Health, maxHealth = h and h.MaxHealth, walkSpeed = h and h.WalkSpeed, jumpPower = h and h.JumpPower,
                    displayName = h and h.DisplayName, hipHeight = h and h.HipHeight, rig = h and tostring(h.RigType) or nil, tags = tagsOf(m), attributes = m:GetAttributes(),
                    scripts = scripts, accessories = accessories, parts = #m:GetDescendants(), primaryPart = m.PrimaryPart and m.PrimaryPart.Name or nil, position = pos(m)})
            end
            R.npcs = out

        elseif act == "configure" then
            local n = 0
            for _, m in ipairs(findNpcs()) do
                local h = m:FindFirstChildOfClass("Humanoid")
                if h then
                    if A.health then h.MaxHealth = A.health; h.Health = A.health end
                    if A.walk_speed then h.WalkSpeed = A.walk_speed end
                    if A.jump_power then pcall(function() h.UseJumpPower = true; h.JumpPower = A.jump_power end) end
                    if A.display_name then h.DisplayName = A.display_name end
                end
                if A.scale then pcall(function() m:ScaleTo(A.scale) end) end
                for _, t in ipairs(A.add_tags or {}) do CS:AddTag(m, t) end
                for _, t in ipairs(A.remove_tags or {}) do CS:RemoveTag(m, t) end
                for k, v in pairs(A.attributes or {}) do m:SetAttribute(k, v) end
                n = n + 1
            end
            R.configured = n

        elseif act == "remove" then
            local n = 0
            for _, m in ipairs(findNpcs()) do m:Destroy(); n = n + 1 end
            R.removed = n

        elseif act == "snap_to_ground" then
            local n, missed = 0, 0
            for _, m in ipairs(findNpcs()) do if groundSnap(m) then n = n + 1 else missed = missed + 1 end end
            R.snapped = n; R.noGroundBelow = missed

        elseif act == "spawn_crowd" then
            local tpl = resolve(A.template)
            local parentName = A.parent or "Workspace.MS_Crowd"
            local parent
            if A.parent then parent = resolve(A.parent)
            else parent = workspace:FindFirstChild("MS_Crowd") or mk("Folder", {Name = "MS_Crowd"}, workspace) end
            local rng = Random.new(A.seed)
            local c = vec3(A.center)
            local made = {}
            local cols = math.max(1, math.ceil(math.sqrt(A.count)))
            local prefix = A.name_prefix or tpl.Name
            for i = 1, A.count do
                local clone = tpl:Clone()
                for _, t in ipairs(tagsOf(tpl)) do if not hasTag(clone, t) then CS:AddTag(clone, t) end end
                clone.Name = prefix .. "_" .. i
                clone.Parent = parent
                local p
                if A.layout == "ring" then
                    local ang = (i - 1) / A.count * math.pi * 2
                    p = c + Vector3.new(math.cos(ang) * A.radius, 0, math.sin(ang) * A.radius)
                elseif A.layout == "grid" then
                    local r, col = math.floor((i - 1) / cols), (i - 1) % cols
                    p = c + Vector3.new((col - (cols - 1) / 2) * A.spacing, 0, (r - (cols - 1) / 2) * A.spacing)
                else
                    local ang = rng:NextNumber(0, math.pi * 2)
                    local d = A.radius * math.sqrt(rng:NextNumber(0, 1))
                    p = c + Vector3.new(math.cos(ang) * d, 0, math.sin(ang) * d)
                end
                clone:PivotTo(CFrame.new(p) * CFrame.Angles(0, rng:NextNumber(0, math.pi * 2), 0))
                if A.scale_range then pcall(function() clone:ScaleTo(rng:NextNumber(A.scale_range[1], A.scale_range[2])) end) end
                if A.randomize_colors then
                    local tone = Color3.fromHSV(rng:NextNumber(0, 1), 0.45, 0.85)
                    for _, d in ipairs(clone:GetDescendants()) do
                        if d:IsA("BasePart") and (d.Name == "Torso" or d.Name == "UpperTorso" or d.Name == "Left Arm" or d.Name == "Right Arm" or d.Name == "LeftUpperArm" or d.Name == "RightUpperArm") then d.Color = tone end
                    end
                end
                groundSnap(clone)
                table.insert(made, clone:GetFullName())
            end
            R.spawned = #made; R.parent = parent:GetFullName(); R.first = made[1]

        elseif act == "audit" then
            local issues, fixed = {}, {}
            local all = findNpcs()
            local function add(sev, inst, code, msg)
                if #issues < 200 then table.insert(issues, {severity = sev, path = inst:GetFullName(), code = code, message = msg}) end
            end
            local pathfinders = 0
            local names = {}
            for _, m in ipairs(all) do
                local h = m:FindFirstChildOfClass("Humanoid")
                local hrp = m:FindFirstChild("HumanoidRootPart")
                if not h then add("error", m, "no_humanoid", "Tagged/selected model has no Humanoid.")
                else
                    if not hrp then add("error", m, "no_root", "No HumanoidRootPart: movement and AI scripts cannot drive this NPC.")
                    elseif m.PrimaryPart == nil then
                        if A.apply then m.PrimaryPart = hrp; fixed.primary_part = (fixed.primary_part or 0) + 1
                        else add("warn", m, "no_primary_part", "PrimaryPart is not set (use apply=true to set it to HumanoidRootPart).") end
                    end
                    if h.Health <= 0 then add("warn", m, "dead", "Humanoid health is 0.") end
                    if h.WalkSpeed <= 0 then add("info", m, "no_walk_speed", "WalkSpeed is 0; the NPC cannot move.") end
                    if h.MaxHealth > 100000 then add("info", m, "huge_health", "MaxHealth is very high (" .. h.MaxHealth .. ").") end
                end
                if m.Archivable == false then
                    if A.apply then m.Archivable = true; fixed.archivable = (fixed.archivable or 0) + 1
                    else add("warn", m, "not_archivable", "Archivable=false: cannot be cloned for respawns/crowds.") end
                end
                if hrp then
                    if hrp.Position.Y < -200 then add("error", m, "fell_into_void", "NPC is far below the map (Y=" .. math.floor(hrp.Position.Y) .. ").") end
                    local params = RaycastParams.new()
                    params.FilterType = Enum.RaycastFilterType.Exclude
                    params.FilterDescendantsInstances = {m}
                    local hit = workspace:Raycast(hrp.Position, Vector3.new(0, -60, 0), params)
                    if not hit and hrp.Position.Y > -200 then
                        if A.apply and groundSnap(m) then fixed.snapped = (fixed.snapped or 0) + 1
                        else add("warn", m, "floating", "No ground within 60 studs below the NPC.") end
                    end
                end
                local b = behaviours(m)
                if #b == 0 then add("info", m, "no_behaviour", "No Npc* behaviour tag; it will stand still (add one with ms_roblox_npc_behavior).")
                else pathfinders = pathfinders + 1 end
                names[m.Name] = (names[m.Name] or 0) + 1
            end
            for n, c in pairs(names) do
                if c > 1 and c <= 10 then table.insert(issues, {severity = "info", path = n, code = "duplicate_name", message = c .. " NPCs share the name '" .. n .. "' (fine for crowds)."}) end
            end
            if pathfinders > 60 then table.insert(issues, {severity = "warn", path = "Workspace", code = "many_ai", message = pathfinders .. " AI-driven NPCs; pathfinding cost grows quickly (keep chasers under ~40 active)."}) end
            R.counts = {npcs = #all, aiDriven = pathfinders}
            R.issues = issues; R.issueCount = #issues; R.fixed = fixed; R.applied = A.apply == true
        end
        waypoint("npc " .. act)
    '''), "npc " + act)
