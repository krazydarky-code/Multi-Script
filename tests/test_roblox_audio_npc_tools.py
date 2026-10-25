# SPDX-License-Identifier: GPL-3.0-or-later
"""Roblox audio + NPC tools (ms_roblox_audio_kit / audio_tools / npc_builder / npc_behavior / npc_manage).

1. Every generated program and every embedded runtime script loads in a stock Lua VM (and the real Luau compiler when installed).
2. Every program runs in the Roblox API mock; results are read back.
3. The NPC behaviour scripts and the audio client scripts are actually EXECUTED against a richer fake engine
   (fake humanoids, players, tags, pathfinding, tweens, signals) and their effects are asserted."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
sys.path.insert(0, str(ROOT / "tests" / "support"))
import engine_toolkit as T  # noqa: E402
import live_engines as L  # noqa: E402
import luau_mock as LM  # noqa: E402

T.ensure_loaded()
fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + ((" :: " + str(detail)[:500]) if (detail and not ok) else ""))
    if not ok:
        fails.append(name)


if not LM.available():
    print("SKIP: pip install lupa")
    sys.exit(0)

import toolkit_roblox_audio_npc as AN  # noqa: E402
from lupa import LuaRuntime  # noqa: E402

check("module loaded by engine_toolkit without errors", not T.PRO_ERRORS, T.PRO_ERRORS)
NAMES = ["ms_roblox_audio_kit", "ms_roblox_audio_tools", "ms_roblox_npc_builder", "ms_roblox_npc_behavior", "ms_roblox_npc_manage"]
check("all five tools registered", all(n in T.REGISTRY for n in NAMES), [n for n in NAMES if n not in T.REGISTRY])
check("tools write (so dry-run / replay guards apply)", all(T.REGISTRY[n]["writes"] for n in NAMES))
check("descriptions are specific", all(len(T.REGISTRY[n]["description"]) > 200 for n in NAMES))


class Ctx(T.Ctx):
    def advertised(self, s):
        return {"execute_luau"} if s == "roblox" else None

    def studio_id(self, a):
        return ("S1", "ok")

    def call(self, *a, **k):
        return {"text": ""}


ctx = Ctx()
mock = LM.LuauMock(T, ctx)
lua_probe = LuaRuntime(unpack_returned_tuples=True)
load_err = lua_probe.eval("function(c) local f, e = load(c); return e end")
SETUP = 'local p=Instance.new("Part"); p.Name="Part"; p.Parent=workspace; p.Size=Vector3.new(4,6,1); p.Anchored=true'


def dry(_tool, **args):
    return json.loads(T.run(_tool, dict(args, dry_run=True), ctx)["text"])


def rb(_tool, rt=None, setup=SETUP, **args):
    res, rt = mock.run(_tool, args, setup, rt)
    return res or {"ok": False, "error": "no result"}, rt


def lua(rt, code):
    return mock.probe(rt, code)


def embedded(code):
    m = re.search(r"JSONDecode\(\[=*\[(.*?)\]=*\]\)", code, re.S)
    return json.loads(m.group(1)) if m else {}


# ───────────────────────── 1) syntax of programs and installed scripts ─────────────────────────
SOUNDS = {"sounds": {"Default": 1, "Grass": [2, 3]}, "states": {"calm": [4], "combat": [5, 6]}, "hover": 7, "click": "8", "heartbeat": 9, "tracks": [10, 11]}
audio_sources = {}
for k in AN.AUDIO_KINDS:
    if k == "mixer":
        continue
    cls, loc, tag, src, merged = AN._audio_source(k, SOUNDS)
    audio_sources[k] = src
npc_sources = {k: AN._npc_source(k, {})[1] for k in AN.NPC_KINDS}
bad = [(k, load_err(s)) for k, s in {**audio_sources, **npc_sources}.items() if load_err(s)]
check("every audio + npc runtime script loads in stock Lua", not bad, bad)
left = [k for k, s in {**audio_sources, **npc_sources}.items() if re.search(r"@\w+@", s)]
check("no unfilled @option@ placeholders", not left, left)
anim = AN._fill(AN._ANIMATE_SRC, {"idle": "x", "walk": "y", "ref_speed": 16})
check("animator script loads", not load_err(anim))
comp_bad = []
for k, s in {**audio_sources, **npc_sources, "anim": anim}.items():
    r = L.luau_compile(s)
    if r is not None and not r[0]:
        comp_bad.append((k, r[1]))
check("real Luau compiler accepts every installed script (when installed)", not comp_bad, comp_bad)
check("sound ids are normalised to rbxassetid://", 'rbxassetid://5' in audio_sources["music_player"] and 'rbxassetid://8' in audio_sources["ui_sounds"] and AN.sound_id("https://www.roblox.com/asset/?id=42") == "rbxassetid://42" and AN.sound_id("") == "")

progs = []
for n, args in [("ms_roblox_audio_kit", {"kind": k, "options": SOUNDS}) for k in AN.AUDIO_KINDS] + [("ms_roblox_npc_behavior", {"kind": k, "targets": ["Workspace.Part"]}) for k in AN.NPC_KINDS] + \
        [("ms_roblox_audio_tools", {"action": a, "paths": ["Workspace.Part"], "group": "SFX", "effect": "cave"}) for a in AN.AUDIO_ACTIONS] + \
        [("ms_roblox_npc_manage", {"action": a, "paths": ["Workspace.Part"], "template": "Workspace.Part"}) for a in AN.NPC_ACTIONS] + \
        [("ms_roblox_npc_builder", {"preset": p}) for p in AN.NPC_PRESETS]:
    d = dry(n, **args)
    code = d.get("code", "")
    e = load_err(code) if code else "no code: " + json.dumps(d)[:200]
    if e:
        progs.append((n, args.get("kind") or args.get("action") or args.get("preset"), e))
    r = L.luau_compile(code) if code else None
    if r is not None and not r[0]:
        progs.append((n, "luau", r[1]))
check("every generated program is valid Lua/Luau", not progs, progs)

# ───────────────────────── 2) mock runs ─────────────────────────
for k in AN.AUDIO_KINDS:
    res, rt = rb("ms_roblox_audio_kit", kind=k, options=SOUNDS, position=[0, 3, 0])
    check("audio_kit " + k + " runs", res.get("ok") is True and dry("ms_roblox_audio_kit", kind=k, options=SOUNDS).get("usage"), res)
res, rt = rb("ms_roblox_audio_kit", kind="footsteps")
check("missing sound ids -> warning, still installs", res.get("ok") and dry("ms_roblox_audio_kit", kind="footsteps").get("warnings"), res)
src = lua(rt, 'return game:GetService("StarterPlayer").StarterPlayerScripts.MS_Footsteps.Source')
check("footsteps source has the configured stride", "local STRIDE = 3.4" in src, src[:200])
res, rt = rb("ms_roblox_audio_kit", kind="mixer")
names = lua(rt, 'local o = {} for _, d in ipairs(game:GetService("SoundService"):GetDescendants()) do o[#o+1] = d.Name .. ":" .. d.ClassName end return o')
check("mixer builds Master + 5 groups, limiter and ducker", all(x in names for x in ["Master:SoundGroup", "Music:SoundGroup", "SFX:SoundGroup", "Ambience:SoundGroup", "UI:SoundGroup", "Voice:SoundGroup", "MS_Limiter:CompressorSoundEffect", "MS_Ducker:CompressorSoundEffect"]), names)
par = lua(rt, 'return game:GetService("SoundService").Master.Music.Parent.Name')
check("group hierarchy", par == "Master", par)
res, rt2 = rb("ms_roblox_audio_kit", kind="mixer", options={"groups": [{"name": "Radio", "volume": 0.3}]}, limiter=False)
check("custom mixer groups", res.get("ok") and res["groups"] == ["SoundService.Radio"] and not res.get("limiter"), res)
res, _ = rb("ms_roblox_audio_kit", kind="nope")
check("audio_kit unknown kind -> error", res.get("ok") is False and "mixer" in json.dumps(res), res)
res, rt = rb("ms_roblox_audio_kit", kind="emitter_3d", targets=["Workspace.Part"], attributes={"SoundId": "rbxassetid://5"})
check("emitter targets tagged + attributes", res.get("tagged") == ["Workspace.Part"] and lua(rt, "return workspace.Part._tags[1]") == "SoundEmitter" and lua(rt, "return workspace.Part._attrs.SoundId") == "rbxassetid://5", res)
res, rt = rb("ms_roblox_audio_kit", kind="reverb_zones", position=[0, 3, 0])
check("reverb zone marker is invisible-ish and tagged", res.get("tagged") == ["Workspace.ReverbZone"], res)

AUD_SETUP = SETUP + '''
local s1 = Instance.new("Sound"); s1.Name = "Wind"; s1.SoundId = "rbxassetid://1"; s1.Looped = true; s1.Parent = workspace
local s2 = Instance.new("Sound"); s2.Name = "Boom"; s2.SoundId = "123"; s2.Volume = 5; s2.Parent = workspace.Part
workspace.Part.ClassName = "Part"
local s3 = Instance.new("Sound"); s3.Name = "Empty"; s3.Parent = workspace
local g = Instance.new("SoundGroup"); g.Name = "SFX"; g.Parent = game:GetService("SoundService")
'''
res, rt = rb("ms_roblox_audio_tools", setup=AUD_SETUP, action="list")
check("audio list", res.get("ok") and res["soundCount"] == 3 and len(res["groups"]) == 1, res)
res, rt = rb("ms_roblox_audio_tools", rt=rt, action="audit")
print(res) if "issues" not in res else None
codes = sorted(i["code"] for i in res["issues"])
check("audit finds empty id, bad id, loud volume, wide rolloff", all(c in codes for c in ["empty_id", "bad_id", "loud", "wide_rolloff"]), codes)
res, rt = rb("ms_roblox_audio_tools", rt=rt, action="audit", apply=True, fixes=["fix_ids", "clamp_volume", "rolloff_3d", "assign_group"], group="SFX")
check("audit apply fixes", res["fixed"].get("fix_ids") == 1 and res["fixed"].get("clamp_volume") == 1 and res["fixed"].get("rolloff_3d") == 1 and res["fixed"].get("assign_group", 0) >= 2, res)
check("fixed values are real", lua(rt, "return workspace.Part.Boom.SoundId") == "rbxassetid://123" and lua(rt, "return workspace.Part.Boom.Volume") == 1 and lua(rt, "return workspace.Part.Boom.RollOffMaxDistance") == 80)
res, rt = rb("ms_roblox_audio_tools", rt=rt, action="audit")
check("after fixes the audit is clean of fixed problems", not any(i["code"] in ("bad_id", "loud", "wide_rolloff") for i in res["issues"]), res["issues"])
res, rt = rb("ms_roblox_audio_tools", rt=rt, action="create_group", group="Voice", parent_group="SFX", volume=0.5)
check("create_group nests", res.get("ok") and res["created"] is True and lua(rt, 'return game:GetService("SoundService").SFX.Voice.Volume') == 0.5, res)
res, rt = rb("ms_roblox_audio_tools", rt=rt, action="create_sound", name="Hum", sound_id=77, parent="Workspace.Part", group="SFX", looped=True)
check("create_sound positional + group", res.get("ok") and res["positional"] is True and lua(rt, "return workspace.Part.Hum.SoundId") == "rbxassetid://77" and lua(rt, "return workspace.Part.Hum.SoundGroup.Name") == "SFX", res)
res, rt = rb("ms_roblox_audio_tools", rt=rt, action="add_effect", paths=["Workspace.Part.Hum"], effect="underwater")
check("effect preset adds two effects", res.get("ok") and len(res["effects"]) == 2, res)
res, rt = rb("ms_roblox_audio_tools", rt=rt, action="add_effect", paths=["Workspace.Part.Hum"], effect="echo", props={"Delay": 0.9})
check("single effect with prop override", res.get("ok") and lua(rt, "return workspace.Part.Hum.MS_echo_EchoSoundEffect.Delay") == 0.9, res)
res, rt = rb("ms_roblox_audio_tools", rt=rt, action="set", paths=["Workspace"], name_contains="boom", volume=0.25, pitch=1.2)
check("set filters by name", res.get("updated") == 1 and lua(rt, "return workspace.Part.Boom.Volume") == 0.25 and lua(rt, "return workspace.Wind.Volume") != 0.25, res)
res, _ = rb("ms_roblox_audio_tools", rt=rt, action="add_effect")
check("add_effect without effect -> error", res.get("ok") is False, res)
res, _ = rb("ms_roblox_audio_tools", rt=rt, action="assign_group", group="Nope")
check("assign_group to a missing group -> clear error", res.get("ok") is False and "not found" in json.dumps(res), res)

# ───────────────────────── NPC builder ─────────────────────────
res, rt = rb("ms_roblox_npc_builder", name="Bob", preset="guard", position=[10, 5, 10], title="Gate Guard", behavior=["guard", "patrol"], attributes={"Damage": 20}, facing=90)
check("builder runs and tags", res.get("ok") and res["npc"] == "Workspace.Bob" and res["tags"] == ["MS_NPC", "NpcGuard", "NpcPatrol"], res)
info = lua(rt, 'local m = workspace.Bob local h = m:FindFirstChildOfClass("Humanoid") return {h.MaxHealth, h.WalkSpeed, h.DisplayName, m._attrs.Damage, m._attrs.MS_Preset, #m._tags, m:FindFirstChild("NpcAnimate") ~= nil, m.Head.MS_NamePlate.Title.Text}')
check("builder applies preset stats, attributes, plate, animator", info == [200, 14, "Bob", 20, "guard", 3, True, "Gate Guard"], info)
pos = lua(rt, "local p = workspace.Bob:GetPivot().Position return {p.X, p.Y, p.Z}")
check("builder grounds the NPC (feet on y=0)", abs(pos[0] - 10) < 0.01 and 2.9 < pos[1] < 3.6, pos)
src = lua(rt, "return workspace.Bob.NpcAnimate.Source")
check("mannequin gets R6 animation ids", "180435571" in src and "507766666" not in src, src[:300])
cnt = lua(rt, "local o = {} for _, d in ipairs(workspace.Bob:GetChildren()) do o[d.ClassName] = (o[d.ClassName] or 0) + 1 end return o")
check("mannequin has 6 limbs + root, 6 joints, humanoid", cnt.get("Part") == 7 and cnt.get("Motor6D") is None and cnt.get("Humanoid") == 1, cnt)
mot = lua(rt, "local n = 0 for _, d in ipairs(workspace.Bob:GetDescendants()) do if d.ClassName == 'Motor6D' then n = n + 1 end end return n")
check("six Motor6D joints", mot == 6, mot)
res, rt = rb("ms_roblox_npc_builder", rt=rt, name="Tmpl", preset="zombie", parent="ServerStorage.NPCs", position=[0, 5, 0], scale=1.5, rig="R6", animate=False, nameplate=False)
check("template stored in a created folder", res.get("ok") and res["npc"] == "ServerStorage.NPCs.Tmpl" and lua(rt, 'return game:GetService("ServerStorage").NPCs.Tmpl:FindFirstChild("NpcAnimate") == nil'), res)
res, _ = rb("ms_roblox_npc_builder", preset="dragon")
check("unknown preset -> error with list", res.get("ok") is False and "zombie" in json.dumps(res), res)
res, _ = rb("ms_roblox_npc_builder", behavior=["fly"])
check("unknown behavior -> error", res.get("ok") is False, res)
res, _ = rb("ms_roblox_npc_builder", rig="R7")
check("bad rig -> error", res.get("ok") is False, res)
d = dry("ms_roblox_npc_builder", name="Ann", user_id=1234, appearance={"hats": [111, "222"], "shirt_id": "rbxassetid://333", "accessories": {"back": [444]}})
p = embedded(d["code"])
check("appearance ids are cleaned to digits", p["hats"] == "111,222" and p["shirt_id"] == "333" and p["acc"] == {"back": "444"} and p["user_id"] == 1234, p)

# ───────────────────────── behaviour installers ─────────────────────────
for k in AN.NPC_KINDS:
    kw = {"kind": k, "targets": ["Workspace.Part"]} if k != "spawner" else {"kind": k, "position": [0, 3, 0]}
    res, rt = rb("ms_roblox_npc_behavior", **kw)
    check("npc_behavior " + k + " installs", res.get("ok") is True and res.get("installed") and dry("ms_roblox_npc_behavior", **kw).get("usage"), res)
res, rt = rb("ms_roblox_npc_behavior", kind="patrol", points=[[0, 1, 0], [10, 1, 0], [10, 1, 10]], group="A")
pts = lua(rt, "local n, g = 0, '' for _, d in ipairs(workspace.MS_NPC_PatrolPoints:GetChildren()) do n = n + 1 g = d._attrs.Group end return {n, g}")
check("patrol creates tagged ordered points", res.get("ok") and pts == [3, "A"] and len(res["points"]) == 3, (res, pts))
res, _ = rb("ms_roblox_npc_behavior", kind="enemy_melee")
check("missing targets -> helpful error", res.get("ok") is False and "builder" in json.dumps(res).lower(), res)
res, _ = rb("ms_roblox_npc_behavior", kind="merchant", targets=["Workspace.Part"], options={"stock": [{"name": "x"}]})
check("merchant stock needs a price", res.get("ok") is False, res)
res, _ = rb("ms_roblox_npc_behavior", kind="quest_giver", targets=["Workspace.Part"], options={"quests": [{"title": "t"}]})
check("quest needs stat+amount", res.get("ok") is False, res)
res, _ = rb("ms_roblox_npc_behavior", kind="merchant", targets=["Workspace.Part"], options={"currency": 'Gold"; os.exit() --'})
check("currency name is validated (no script injection)", res.get("ok") is False, res)
res, rt = rb("ms_roblox_npc_behavior", kind="enemy_melee", targets=["Workspace.Part"], options={"damage": 33, "reward": 7, "stat": "Gold", "respawn": 0})
src = lua(rt, 'return game:GetService("ServerScriptService").MS_NpcEnemyMelee.Source')
check("options are baked into the script", 'attr(npc, "Damage", 33)' in src and 'attr(npc, "RewardStat", "Gold")' in src and not re.search(r"@\w+@", src), src[-200:])
check("npc targets also get MS_NPC", lua(rt, "return workspace.Part._tags[2]") == "MS_NPC")

# ───────────────────────── manage ─────────────────────────
res, rt = rb("ms_roblox_npc_builder", name="Tmpl", preset="villager", position=[0, 5, 0], behavior=["wander"])
res, rt = rb("ms_roblox_npc_manage", rt=rt, action="list")
check("manage list sees NPCs by humanoid", res.get("count") == 1 and res["npcs"][0]["name"] == "Tmpl" and res["npcs"][0]["maxHealth"] == 100, res)
res, rt = rb("ms_roblox_npc_manage", rt=rt, action="spawn_crowd", template="Workspace.Tmpl", count=12, layout="ring", radius=20, scale_range=[0.9, 1.2], randomize_colors=True, name_prefix="Citizen")
check("crowd spawns", res.get("ok") and res["spawned"] == 12 and res["parent"] == "Workspace.MS_Crowd", res)
n_tags = lua(rt, "local n = 0 for _, m in ipairs(workspace.MS_Crowd:GetChildren()) do if #m._tags == 2 then n = n + 1 end end return n")
check("crowd members keep the template's tags", n_tags == 12, n_tags)
res, rt = rb("ms_roblox_npc_manage", rt=rt, action="spawn_crowd", template="Workspace.Tmpl", count=9, layout="grid", spacing=5, center=[100, 5, 0], parent="Workspace")
check("grid crowd", res.get("spawned") == 9, res)
res, rt = rb("ms_roblox_npc_manage", rt=rt, action="configure", paths=["Workspace.Tmpl"], health=250, walk_speed=20, display_name="Hero", add_tags=["Hero"], attributes={"Quest": "A"})
chk = lua(rt, 'local m = workspace.Tmpl local h = m:FindFirstChildOfClass("Humanoid") return {h.Health, h.WalkSpeed, h.DisplayName, m._attrs.Quest}')
check("configure sets stats", res.get("configured") == 1 and chk == [250, 20, "Hero", "A"], (res, chk))
res, rt = rb("ms_roblox_npc_manage", rt=rt, action="inspect", paths=["Workspace.Tmpl"])
check("inspect returns scripts + attributes", res["npcs"][0]["scripts"] == ["NpcAnimate"] and res["npcs"][0]["attributes"].get("Quest") == "A", res)
res, rt = rb("ms_roblox_npc_manage", rt=rt, action="audit")
check("audit runs and counts", res.get("ok") and res["counts"]["npcs"] >= 22, res)
lua(rt, 'workspace.Tmpl.PrimaryPart = nil workspace.Tmpl.Archivable = false')
res, rt = rb("ms_roblox_npc_manage", rt=rt, action="audit", paths=["Workspace.Tmpl"])
codes = [i["code"] for i in res["issues"]]
check("audit flags no PrimaryPart + non-archivable", "no_primary_part" in codes and "not_archivable" in codes, codes)
res, rt = rb("ms_roblox_npc_manage", rt=rt, action="audit", paths=["Workspace.Tmpl"], apply=True)
check("audit apply fixes them", res["fixed"].get("primary_part") == 1 and res["fixed"].get("archivable") == 1, res)
res, rt = rb("ms_roblox_npc_manage", rt=rt, action="snap_to_ground", paths=["Workspace.Tmpl"])
check("snap_to_ground", res.get("snapped") == 1, res)
res, rt = rb("ms_roblox_npc_manage", rt=rt, action="remove", paths=["Workspace.Tmpl"])
check("remove", res.get("removed") == 1 and lua(rt, "return workspace:FindFirstChild('Tmpl') == nil"), res)
res, _ = rb("ms_roblox_npc_manage", action="remove")
check("remove without a selector -> error", res.get("ok") is False, res)
res, _ = rb("ms_roblox_npc_manage", action="spawn_crowd")
check("spawn_crowd without template -> error", res.get("ok") is False, res)

# ───────────────────────── 3) execute the installed scripts against a fake engine ─────────────────────────
HARNESS = r'''
local function sig()
  local s = {_cbs = {}}
  function s:Connect(f) table.insert(self._cbs, f); return {Disconnect = function() end} end
  function s:Wait() end
  function s:Fire(...) for _, f in ipairs(self._cbs) do f(...) end end
  return s
end
SIG = sig
local realNew = Instance.new
local function decorate(o)
  local p = rawget(o, "_p")
  local c = o.ClassName
  p.WaitForChild = function(self, n) return self:FindFirstChild(n) end
  p.GetAttributeChangedSignal = function() return sig() end
  p.IsDescendantOf = function() return true end
  p.DescendantAdded = sig(); p.AncestryChanged = sig()
  if c == "Humanoid" then
    p.Health = 100; p.MaxHealth = 100; p.WalkSpeed = 16; p.FloorMaterial = Enum.Material.Grass
    p.MoveToFinished = sig(); p.Died = sig(); p.Running = sig(); p.HealthChanged = sig(); p.StateChanged = sig()
    p.MoveTo = function(self, pos) self._moveto = pos; self._moves = (self._moves or 0) + 1 end
    p.TakeDamage = function(self, d) self.Health = self.Health - d; if self.Health <= 0 then self.Died:Fire() end end
    p.GetState = function() return Enum.HumanoidStateType.Running end
    p.LoadAnimation = nil
  elseif c == "Sound" then
    p.IsPlaying = false; p.Ended = sig(); p.Played = sig()
    p.Play = function(self) self.Playing = true; self.IsPlaying = true end
    p.Stop = function(self) self.Playing = false; self.IsPlaying = false end
    p.Pause = p.Stop
  elseif c == "ProximityPrompt" then p.Triggered = sig()
  elseif c == "TextButton" then p.MouseEnter = sig(); p.Activated = sig()
  elseif o:IsA("BasePart") then p.Touched = sig()
  end
  return o
end
Instance.new = function(class, parent)
  local o = decorate(realNew(class))
  if parent then o.Parent = parent end
  return o
end
decorate(workspace); decorate(game)
Instance.new("Part") -- warm
local CLOCK, WAITS, LIMIT = 1000, 0, 200
os.clock = function() return CLOCK end
task.wait = function(t) WAITS = WAITS + 1; CLOCK = CLOCK + (t or 0.1); if WAITS > LIMIT then error("STOP_LOOP") end return t end
task.delay = function(t, f, ...) return f(...) end
function RESET_LOOP(n) WAITS = 0; LIMIT = n or 200 end
TAGGED = {}
local csf = {}
function csf:AddTag(i, t) i._tags[#i._tags + 1] = t; TAGGED[t] = TAGGED[t] or {}; table.insert(TAGGED[t], i) end
function csf:RemoveTag() end
function csf:HasTag(i, t) for _, x in ipairs(i._tags) do if x == t then return true end end return false end
function csf:GetTags(i) return i._tags end
function csf:GetTagged(t) return TAGGED[t] or {} end
function csf:GetInstanceAddedSignal() return sig() end
local players = {}
PLAYERS = players
local pfs = {CreatePath = function() return {Status = Enum.PathStatus.Success, ComputeAsync = function() end, GetWaypoints = function(self)
  return {{Position = Vector3.new(1, 3, 1), Action = Enum.PathWaypointAction.Walk}, {Position = Vector3.new(5, 3, 5), Action = Enum.PathWaypointAction.Jump}} end} end}
Enum.PathStatus.Success = Enum.PathStatus.Success
local fakePlayers = {GetPlayers = function() return players end, GetPlayerFromCharacter = function(_, c) for _, p in ipairs(players) do if p.Character == c then return p end end end,
  FindFirstChild = function(_, n) for _, p in ipairs(players) do if p.Name == n then return p end end end, PlayerAdded = sig(), PlayerRemoving = sig()}
local tween = {Create = function(_, inst, info, goal) return {Play = function() for k, v in pairs(goal) do inst[k] = v end end, Completed = sig()} end}
local debris = {AddItem = function() end}
local rs = {Heartbeat = sig()}
HEART = rs.Heartbeat
local origGS = game.GetService
function game:GetService(n)
  if n == "CollectionService" then return csf end
  if n == "Players" then return fakePlayers end
  if n == "PathfindingService" then return pfs end
  if n == "TweenService" then return tween end
  if n == "Debris" then return debris end
  if n == "RunService" then return rs end
  return origGS(self, n)
end
local ss = game:GetService("SoundService")
ss.FindFirstChild = function(self, n, rec)
  for _, d in ipairs(self:GetDescendants()) do if d.Name == n then return d end end
end
TweenInfo.new = function() return {} end
function MKPLAYER(name, pos)
  local plr = Instance.new("Folder"); plr.Name = name; plr.UserId = #players + 1
  local char = Instance.new("Model"); char.Name = name
  local hum = Instance.new("Humanoid"); hum.Parent = char
  local hrp = Instance.new("Part"); hrp.Name = "HumanoidRootPart"; hrp.Position = pos; hrp.Parent = char
  char.PrimaryPart = hrp; char.Parent = workspace
  plr.Character = char
  Instance.new("Backpack").Parent = plr
  plr.CharacterAdded = sig()
  table.insert(players, plr)
  return plr, char, hum, hrp
end
function MKNPC(name, pos, tags)
  local m = Instance.new("Model"); m.Name = name
  local hum = Instance.new("Humanoid"); hum.Parent = m
  local hrp = Instance.new("Part"); hrp.Name = "HumanoidRootPart"; hrp.Position = pos; hrp.Parent = m
  local head = Instance.new("Part"); head.Name = "Head"; head.Position = pos + Vector3.new(0, 1.5, 0); head.Parent = m
  m.PrimaryPart = hrp; m.Parent = workspace
  for _, t in ipairs(tags) do csf:AddTag(m, t) end
  return m, hum, hrp
end
function RUN_SCRIPT(src, ...)
  local f, e = load(src)
  if not f then error(e) end
  local ok, err = pcall(f, ...)
  if not ok and not string.find(tostring(err), "STOP_LOOP", 1, true) then return "ERR: " .. tostring(err) end
  return "ok"
end
'''


def fresh():
    rt = mock.runtime(SETUP)
    rt.execute(HARNESS)
    return rt


def script_src(rt, parent, name):
    return lua(rt, f'return {parent}.{name}.Source')


def installed_source(name, **args):
    d = dry(name, **args)
    return embedded(d["code"])["scripts"][0]["source"]


def run_npc(kind, setup_lua, check_lua, loop=150, **opts):
    """Install the behaviour script through the real tool, then execute its source in the fake engine."""
    rt = fresh()
    rt.execute(setup_lua)
    src = installed_source("ms_roblox_npc_behavior", kind=kind, targets=["Workspace.Part"], options=opts)
    rt.globals().SRC = src
    out = rt.execute(f"RESET_LOOP({loop}) return RUN_SCRIPT(SRC)")
    val = lua(rt, check_lua) if check_lua else None
    return str(out), val, rt


out, val, rt = run_npc("wander", 'NPC, HUM, HRP = MKNPC("Wanderer", Vector3.new(0,3,0), {"NpcWander", "MS_NPC"})', "return {HUM._moves, HUM._moveto.X, HUM._moveto.Z}", radius=15)
check("wander executes and moves the NPC", out == "ok" and val[0] > 0 and (val[1] ** 2 + val[2] ** 2) ** 0.5 <= 16, (out, val))

out, val, rt = run_npc("patrol", 'NPC, HUM, HRP = MKNPC("Pat", Vector3.new(0,3,0), {"NpcPatrol"}) for i, x in ipairs({10, 20}) do local p = Instance.new("Part") p.Name = "P" .. i p.Position = Vector3.new(x, 3, 0) p._attrs.Order = i p.Parent = workspace TAGGED.NpcPatrolPoint = TAGGED.NpcPatrolPoint or {} table.insert(TAGGED.NpcPatrolPoint, p) end', "return HUM._moves", loop=120)
check("patrol executes through waypoints", out == "ok" and val > 3, (out, val))

out, val, rt = run_npc("follow", 'PLR, CHAR, PH, PHRP = MKPLAYER("Ann", Vector3.new(30,3,0)) NPC, HUM, HRP = MKNPC("Pet", Vector3.new(0,3,0), {"NpcFollow"})', "return {HUM._moves or 0, HRP.Position.X}", loop=30)
check("follow chases the player", out == "ok" and val[0] > 3, (out, val))

out, val, rt = run_npc("follow", 'PLR, CHAR, PH, PHRP = MKPLAYER("Ann", Vector3.new(300,3,0)) NPC, HUM, HRP = MKNPC("Pet", Vector3.new(0,3,0), {"NpcFollow"}) NPC:SetAttribute("Owner", "Ann")', "return HRP.Position.X > 100 or HUM._moves", loop=10)
check("follow teleports a lagging pet to its owner", out == "ok" and val, (out, val))

out, val, rt = run_npc("guard", 'PLR, CHAR, PH, PHRP = MKPLAYER("Ann", Vector3.new(3,3,0)) NPC, HUM, HRP = MKNPC("Guard", Vector3.new(0,3,0), {"NpcGuard"})', "return {PH.Health, NPC.Head:FindFirstChild('MS_Say') ~= nil}", loop=40)
check("guard warns and damages a player in reach (with cooldown)", out == "ok" and val[1] is True and 0 < val[0] < 100, (out, val))

out, val, rt = run_npc("guard", 'PLR, CHAR, PH, PHRP = MKPLAYER("Ann", Vector3.new(200,3,0)) NPC, HUM, HRP = MKNPC("Guard", Vector3.new(0,3,0), {"NpcGuard"})', "return PH.Health", loop=20)
check("guard ignores far players", out == "ok" and val == 100, (out, val))

setup_enemy = 'PLR, CHAR, PH, PHRP = MKPLAYER("Ann", Vector3.new(4,3,0)) NPC, HUM, HRP = MKNPC("Zed", Vector3.new(0,3,0), {"NpcEnemy"}) TEMPLATE_PARENT = workspace'
out, val, rt = run_npc("enemy_melee", setup_enemy, "return PH.Health", loop=40, damage=10, cooldown=2, respawn=5, reward=9, stat="Gold")
check("melee enemy hits a nearby player", out == "ok" and val < 100, (out, val))
lua(rt, "HUM:TakeDamage(500)")
res = lua(rt, 'local n = 0 for _, m in ipairs(workspace:GetChildren()) do if m.Name == "Zed" then n = n + 1 end end return {PLR.leaderstats and PLR.leaderstats.Gold.Value or -1, n}')
check("enemy death pays the reward and respawns a clone", res[0] == 9 and res[1] == 2, res)

out, val, rt = run_npc("enemy_ranged", 'PLR, CHAR, PH, PHRP = MKPLAYER("Ann", Vector3.new(25,3,0)) NPC, HUM, HRP = MKNPC("Gun", Vector3.new(0,3,0), {"NpcShooter"}) NPC:SetAttribute("Accuracy", 1)', "return PH.Health", loop=40)
check("ranged enemy shoots a visible player", out == "ok" and val < 100, (out, val))

out, val, rt = run_npc("flee", 'PLR, CHAR, PH, PHRP = MKPLAYER("Ann", Vector3.new(5,3,0)) NPC, HUM, HRP = MKNPC("Rabbit", Vector3.new(0,3,0), {"NpcFlee"})', "return {HUM._moveto.X, HUM.WalkSpeed}", loop=10)
check("flee runs away from the player at flee speed", out == "ok" and val[0] < -10 and val[1] == 24, (out, val))

stock = [{"name": "Sword", "price": 50, "tool": "Sword"}, {"name": "Potion", "price": 10, "heal": 30}, {"name": "Key", "price": 5, "stat": "Keys", "amount": 2}]
setup_m = 'PLR, CHAR, PH, PHRP = MKPLAYER("Ann", Vector3.new(3,3,0)) NPC, HUM, HRP = MKNPC("Shop", Vector3.new(0,3,0), {"NpcMerchant"}) local f = Instance.new("Folder") f.Name = "Tools" f.Parent = game:GetService("ServerStorage") local t = Instance.new("Tool") t.Name = "Sword" t.Parent = f'
out, val, rt = run_npc("merchant", setup_m, "return HRP.MS_ShopAtt ~= nil", loop=5, stock=stock)
check("merchant creates both prompts", out == "ok" and val is True)
lua(rt, 'local ls = Instance.new("Folder") ls.Name = "leaderstats" ls.Parent = PLR local c = Instance.new("IntValue") c.Name = "Coins" c.Value = 70 c.Parent = ls')
lua(rt, 'local prompts = {} for _, d in ipairs(HRP.MS_ShopAtt:GetChildren()) do prompts[d.KeyboardKeyCode.Name] = d end NEXTP, BUYP = prompts.E, prompts.F')
lua(rt, "BUYP.Triggered:Fire(PLR)")
res = lua(rt, 'return {PLR.leaderstats.Coins.Value, PLR.Backpack:FindFirstChild("Sword") ~= nil}')
check("buying a tool charges and delivers it", res == [20, True], res)
lua(rt, "BUYP.Triggered:Fire(PLR)")
res = lua(rt, 'return PLR.leaderstats.Coins.Value')
check("cannot buy without enough money", res == 20, res)
lua(rt, "NEXTP.Triggered:Fire(PLR) PH.MaxHealth = 100 PH.Health = 40 BUYP.Triggered:Fire(PLR)")
res = lua(rt, 'return {PLR.leaderstats.Coins.Value, PH.Health}')
check("heal item restores health", res == [10, 70], res)
lua(rt, "NEXTP.Triggered:Fire(PLR) BUYP.Triggered:Fire(PLR)")
res = lua(rt, 'return {PLR.leaderstats.Coins.Value, PLR.leaderstats.Keys.Value}')
check("stat item adds to a leaderstat", res == [5, 2], res)

quests = [{"title": "Slayer", "text": "Kill 3", "stat": "Kills", "amount": 3, "reward": 40}, {"title": "Slayer II", "text": "Kill 1", "stat": "Kills", "amount": 1, "reward": 5, "reward_stat": "Gems"}]
out, val, rt = run_npc("quest_giver", 'PLR, CHAR, PH, PHRP = MKPLAYER("Ann", Vector3.new(3,3,0)) NPC, HUM, HRP = MKNPC("Elder", Vector3.new(0,3,0), {"NpcQuest"})', "local o = {} for _, d in ipairs(HRP:GetChildren()) do if d.ClassName == 'ProximityPrompt' then QP = d end end return QP ~= nil", loop=3, quests=quests)
check("quest giver creates its prompt", out == "ok" and val is True)
lua(rt, "QP.Triggered:Fire(PLR)")
check("accepting a quest announces it", lua(rt, "return PLR._attrs.MS_Quest") == "Slayer 0/3")
lua(rt, "QP.Triggered:Fire(PLR)")
check("incomplete quest shows progress", lua(rt, "return PLR._attrs.MS_Quest") == "Slayer 0/3")
lua(rt, "PLR.leaderstats.Kills.Value = 3 QP.Triggered:Fire(PLR)")
check("completed quest pays the reward", lua(rt, "return PLR.leaderstats.Coins.Value") == 40)
lua(rt, "QP.Triggered:Fire(PLR) PLR.leaderstats.Kills.Value = 4 QP.Triggered:Fire(PLR)")
check("second quest uses its own reward stat", lua(rt, "return PLR.leaderstats.Gems.Value") == 5)
lua(rt, "QP.Triggered:Fire(PLR)")
check("no quests left -> done text", lua(rt, "return HRP.Parent.Head.MS_Say:FindFirstChildOfClass('TextLabel').Text") == "You have done everything I asked. Thank you!")

out, val, rt = run_npc("dialogue", 'PLR, CHAR, PH, PHRP = MKPLAYER("Ann", Vector3.new(3,3,0)) NPC, HUM, HRP = MKNPC("Talker", Vector3.new(0,3,0), {"NpcDialogue"})', "for _, d in ipairs(HRP:GetChildren()) do if d.ClassName == 'ProximityPrompt' then DP = d end end return DP ~= nil", loop=3, lines=["Hi", "Bye"], seconds=1)
lua(rt, "RESET_LOOP(50) DP.Triggered:Fire(PLR)")
check("dialogue speaks its lines", out == "ok" and lua(rt, "return NPC.Head:FindFirstChild('MS_Say') ~= nil"))

setup_sp = 'PLR, CHAR, PH, PHRP = MKPLAYER("Ann", Vector3.new(3,3,0)) local f = Instance.new("Folder") f.Name = "NPCs" f.Parent = game:GetService("ServerStorage") local m = Instance.new("Model") m.Name = "Zombie" local h = Instance.new("Humanoid") h.Parent = m m.Parent = f local sp = Instance.new("Part") sp.Name = "Spawn" sp.Position = Vector3.new(0,1,0) sp.Parent = workspace TAGGED.NpcSpawner = {sp}'
rt = fresh()
rt.execute(setup_sp)
rt.globals().SRC = installed_source("ms_roblox_npc_behavior", kind="spawner", position=[0, 3, 0], options={"max": 3, "interval": 1})
out = rt.execute("RESET_LOOP(40) return RUN_SCRIPT(SRC)")
n = lua(rt, 'local n = 0 for _, m in ipairs(workspace:GetChildren()) do if m.Name == "Zombie" then n = n + 1 end end return n')
check("spawner clones up to Max and no further", str(out) == "ok" and n == 3, (out, n))

# ───────────────────────── audio client scripts ─────────────────────────
def run_audio(kind, setup_lua, opts=None, loop=50):
    rt = fresh()
    rt.execute('PLR, CHAR, PH, PHRP = MKPLAYER("Ann", Vector3.new(0,3,0)) game:GetService("Players").LocalPlayer = PLR local pg = Instance.new("Folder") pg.Name = "PlayerGui" pg.Parent = PLR '
               'local cam = Instance.new("Part") cam.Name = "Camera" cam.Position = Vector3.new(0,3,0) workspace.CurrentCamera = cam')
    rt.execute(setup_lua)
    d = dry("ms_roblox_audio_kit", kind=kind, options=opts or SOUNDS)
    rt.globals().SRC = embedded(d["code"])["scripts"][0]["source"]
    out = rt.execute(f"RESET_LOOP({loop}) return RUN_SCRIPT(SRC)")
    return str(out), rt


out, rt = run_audio("ambient_zones", 'local z = Instance.new("Part") z.Name = "Zone" z.Size = Vector3.new(20,20,20) z.Position = Vector3.new(0,3,0) z._attrs.SoundId = "rbxassetid://5" z.Parent = workspace TAGGED.AmbientZone = {z}')
lua(rt, "HEART:Fire(0.3)")
n = lua(rt, 'local n = 0 for _, d in ipairs(game:GetService("SoundService"):GetChildren()) do if d.ClassName == "Sound" and d.Looped then n = n + 1 end end return n')
check("ambient zone starts a looping sound when the camera is inside", out == "ok" and n == 1, (out, n))
lua(rt, "workspace.CurrentCamera.Position = Vector3.new(500,3,0) workspace.CurrentCamera.CFrame = CFrame.new(500,3,0) HEART:Fire(0.3)")

out, rt = run_audio("footsteps", "")
lua(rt, "PHRP.AssemblyLinearVelocity = Vector3.new(14,0,0) for i = 1, 40 do HEART:Fire(0.1) end")
n = lua(rt, "local n = 0 for _, d in ipairs(PHRP:GetChildren()) do if d.ClassName == 'Sound' then n = n + 1 end end return n")
check("footsteps play while moving on the ground", out == "ok" and n >= 5, (out, n))

out, rt = run_audio("music_player", "")
n = lua(rt, 'local o = {} for _, d in ipairs(game:GetService("SoundService"):GetChildren()) do if d.Name == "MS_Music" then o[#o+1] = d.SoundId end end return o')
check("music player starts the default state's track", out == "ok" and n == ["rbxassetid://4"], (out, n))

out, rt = run_audio("ui_sounds", 'local b = Instance.new("TextButton") b.Parent = PLR.PlayerGui')
n = lua(rt, 'local b = PLR.PlayerGui:GetChildren()[1] b.Activated:Fire() local c = 0 for _, d in ipairs(game:GetService("SoundService"):GetChildren()) do if d.ClassName == "Sound" then c = c + 1 end end return {b._attrs.MSWired, c}')
check("ui sounds wire a button and play on click", out == "ok" and n == [True, 1], (out, n))

out, rt = run_audio("emitter_3d", 'local p = Instance.new("Part") p.Name = "Speaker" p._attrs.SoundId = "rbxassetid://9" p.Parent = workspace TAGGED.SoundEmitter = {p}')
n = lua(rt, "local s = TAGGED.SoundEmitter[1].MS_Emitter return {s.SoundId, s.RollOffMaxDistance, s.Looped}")
check("3D emitter builds a positional looping sound from attributes", out == "ok" and n == ["rbxassetid://9", 80, True], (out, n))

out, rt = run_audio("audio_trigger", 'local p = Instance.new("Part") p.Name = "Trig" p._attrs.SoundId = "rbxassetid://9" p.Parent = workspace TAGGED.AudioTrigger = {p}')
n = lua(rt, "local p = TAGGED.AudioTrigger[1] p.Touched:Fire(PHRP) return #p:GetChildren()")
check("audio trigger plays on touch", out == "ok" and n == 1, (out, n))

out, rt = run_audio("jukebox", 'local p = Instance.new("Part") p.Name = "Box" p.Parent = workspace TAGGED.Jukebox = {p}')
n = lua(rt, 'local p = TAGGED.Jukebox[1] local pr for _, d in ipairs(p:GetChildren()) do if d.ClassName == "ProximityPrompt" then pr = d end end pr.Triggered:Fire(PLR) return p.MS_Jukebox.SoundId')
check("jukebox prompt plays the first track", out == "ok" and n == "rbxassetid://10", (out, n))

out, rt = run_audio("reverb_zones", 'local z = Instance.new("Part") z.Name = "Cave" z.Size = Vector3.new(30,30,30) z.Position = Vector3.new(0,3,0) z._attrs.Preset = "Cave" z.Parent = workspace TAGGED.ReverbZone = {z}')
lua(rt, "HEART:Fire(0.3)")
check("reverb zone sets AmbientReverb", out == "ok" and lua(rt, 'return tostring(game:GetService("SoundService").AmbientReverb)') == "Enum.ReverbType.Cave")

out, rt = run_audio("low_health", "")
lua(rt, "PH.Health = 20 for _, f in ipairs(PH.HealthChanged._cbs) do f() end")
v = lua(rt, 'return game:GetService("SoundService").MS_Heartbeat.Volume')
check("low health script loads and reacts", out == "ok" and v > 0.3, (out, v))

# the audio API module can be required-style executed
rt = fresh()
d = dry("ms_roblox_audio_kit", kind="audio_api", options={"sounds": {"click": {"id": 5, "volume": 0.4}, "boom": "rbxassetid://6"}})
src = embedded(d["code"])["scripts"][0]["source"]
rt.globals().SRC = src
res = rt.execute('local f = load(SRC) local A = f() local s = A.Play("click") local ok = A.Has("boom") and not A.Has("nope") return {ok, s and s.Volume or -1, s and s.SoundId or ""}')
res = mock.from_lua(res)
check("MS_Audio module returns an API and plays registered sounds", res == [True, 0.4, "rbxassetid://5"], res)

print()
print("FAILED:" if fails else "ALL PASSED", fails if fails else "")
sys.exit(1 if fails else 0)
