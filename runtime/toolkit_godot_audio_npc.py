# SPDX-License-Identifier: GPL-3.0-or-later
"""Godot audio + NPC kits for engine_toolkit (6.28.2).

ms_godot_audio_kit  GDScript audio systems: AudioManager autoload (buses, pooled SFX, music crossfade, ducking, saved volumes),
                    positional SFX pool, footsteps, ambience zones, music playlist and UI sounds.
ms_godot_npc_kit    NPC brain (idle / wander / patrol / follow / guard / flee / enemy_melee with NavigationAgent and a no-navmesh
                    fallback), talk-to dialogue and an NPC spawner, each as a script plus an optional prefab scene.

Both write plain files under res:// (no engine needed to generate) and follow the Out/SB conventions of ms_godot_gameplay_kit.
Sound paths are only accepted as res:// paths made of safe characters."""
import re

from engine_toolkit import tool, as_list, as_dict, boolean, ToolkitError
from toolkit_godot import _proj, _abs, _res, _read, _write, G, set_setting
from toolkit_godot_pro import SB, Out, OVERWRITE, f, ident, norm_res
from toolkit_godot_game import _shape3, _shape2, _mesh_node, _mats, _poly, define_inputs

_SAFE_RES = re.compile(r"^res://[A-Za-z0-9_./ -]+$")


def _res_path(v):
    s = str(v or "").strip().replace("\\", "/")
    if not s:
        return ""
    if not s.startswith("res://"):
        s = "res://" + s.lstrip("/")
    return s if _SAFE_RES.match(s) and ".." not in s else ""


def _sounds(args, warns):
    """options.sounds {name: path} -> {name: res path}; unsafe entries are dropped with a warning."""
    out = {}
    for k, v in as_dict(as_dict(args.get("options")).get("sounds")).items():
        name = ident(k, "")
        path = _res_path(v)
        if not name or not path:
            warns.append("ignored sound %r: expected a res:// path with letters, digits, _ . / - and spaces" % str(k))
            continue
        out[name] = path
    return out


def _dict_lit(d):
    return "{" + ", ".join('"%s": "%s"' % (k, v) for k, v in sorted(d.items())) + "}"


# ───────────────────────────── audio scripts ─────────────────────────────
AUDIO_MANAGER = '''extends Node
## Multi-Script AudioManager (autoload "AudioManager").
## Creates the Music / SFX / UI / Ambience buses if they are missing, pools one-shot sounds,
## crossfades music, ducks a bus and remembers the player's volumes in user://audio_settings.cfg.
## Example: AudioManager.play_sfx("res://audio/hit.ogg"); AudioManager.play_music(preload("res://audio/theme.ogg"))

const BUSES := ["Music", "SFX", "UI", "Ambience"]
const SAVE_PATH := "user://audio_settings.cfg"
const POOL_SIZE := 12
const SOUNDS := __SOUNDS__

var _pool: Array[AudioStreamPlayer] = []
var _music_a: AudioStreamPlayer
var _music_b: AudioStreamPlayer
var _music_front: AudioStreamPlayer
var _music_tween: Tween
var _duck_tween: Tween
var _duck_base := {}


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	for bus_name in BUSES:
		_ensure_bus(bus_name)
	for i in POOL_SIZE:
		var p := AudioStreamPlayer.new()
		add_child(p)
		_pool.append(p)
	_music_a = AudioStreamPlayer.new()
	_music_b = AudioStreamPlayer.new()
	for m in [_music_a, _music_b]:
		m.bus = "Music"
		m.volume_db = -80.0
		add_child(m)
	_music_front = _music_a
	load_settings()


func _ensure_bus(bus_name: String) -> void:
	if AudioServer.get_bus_index(bus_name) != -1:
		return
	AudioServer.add_bus()
	var idx := AudioServer.bus_count - 1
	AudioServer.set_bus_name(idx, bus_name)
	AudioServer.set_bus_send(idx, "Master")


func _as_stream(v: Variant) -> AudioStream:
	if v is AudioStream:
		return v as AudioStream
	if v is String or v is StringName:
		var key := String(v)
		if SOUNDS.has(key):
			key = String(SOUNDS[key])
		if ResourceLoader.exists(key):
			return load(key) as AudioStream
	return null


func _free_player() -> AudioStreamPlayer:
	for p in _pool:
		if not p.playing:
			return p
	return _pool[0]


## Play a one-shot. `stream` is an AudioStream, a res:// path or a name from SOUNDS.
func play_sfx(stream: Variant, bus: String = "SFX", volume_db: float = 0.0, pitch: float = 1.0) -> AudioStreamPlayer:
	var s := _as_stream(stream)
	if s == null:
		return null
	var player := _free_player()
	player.stream = s
	player.bus = bus
	player.volume_db = volume_db
	player.pitch_scale = pitch
	player.play()
	return player


func play_sfx_random(streams: Array, bus: String = "SFX", volume_db: float = 0.0, pitch_jitter: float = 0.08) -> AudioStreamPlayer:
	if streams.is_empty():
		return null
	var pick: Variant = streams[randi() % streams.size()]
	return play_sfx(pick, bus, volume_db, 1.0 + randf_range(-pitch_jitter, pitch_jitter))


func play_ui(stream: Variant, volume_db: float = 0.0) -> AudioStreamPlayer:
	return play_sfx(stream, "UI", volume_db)


## Crossfade to a new music track. Loop the stream in its import settings if it should repeat.
func play_music(stream: Variant, fade: float = 1.5, volume_db: float = 0.0) -> void:
	var s := _as_stream(stream)
	if s == null:
		return
	if _music_front.playing and _music_front.stream == s:
		return
	var old := _music_front
	var back := _music_b if old == _music_a else _music_a
	back.stream = s
	back.volume_db = -80.0
	back.play()
	_music_front = back
	if _music_tween:
		_music_tween.kill()
	_music_tween = create_tween().set_parallel(true)
	_music_tween.tween_property(back, "volume_db", volume_db, fade)
	_music_tween.tween_property(old, "volume_db", -80.0, fade)
	_music_tween.chain().tween_callback(old.stop)


func stop_music(fade: float = 1.0) -> void:
	if _music_tween:
		_music_tween.kill()
	_music_tween = create_tween()
	_music_tween.tween_property(_music_front, "volume_db", -80.0, fade)
	_music_tween.tween_callback(_music_front.stop)


func set_bus_volume(bus_name: String, linear: float) -> void:
	var idx := AudioServer.get_bus_index(bus_name)
	if idx == -1:
		return
	AudioServer.set_bus_volume_db(idx, linear_to_db(clampf(linear, 0.0, 1.0)))
	AudioServer.set_bus_mute(idx, linear <= 0.001)


func get_bus_volume(bus_name: String) -> float:
	var idx := AudioServer.get_bus_index(bus_name)
	if idx == -1:
		return 1.0
	return db_to_linear(AudioServer.get_bus_volume_db(idx))


## Lower a bus (default Music) for `hold` seconds, e.g. while dialogue or a stinger plays.
func duck(bus_name: String = "Music", amount_db: float = -10.0, hold: float = 1.0, fade: float = 0.3) -> void:
	var idx := AudioServer.get_bus_index(bus_name)
	if idx == -1:
		return
	if not _duck_base.has(bus_name):
		_duck_base[bus_name] = AudioServer.get_bus_volume_db(idx)
	var base: float = _duck_base[bus_name]
	if _duck_tween:
		_duck_tween.kill()
	_duck_tween = create_tween()
	_duck_tween.tween_method(func(v: float): AudioServer.set_bus_volume_db(idx, v), AudioServer.get_bus_volume_db(idx), base + amount_db, fade)
	_duck_tween.tween_interval(hold)
	_duck_tween.tween_method(func(v: float): AudioServer.set_bus_volume_db(idx, v), base + amount_db, base, fade)
	_duck_tween.tween_callback(func(): _duck_base.erase(bus_name))


func _all_buses() -> Array:
	var all: Array = ["Master"]
	all.append_array(BUSES)
	return all


func save_settings() -> void:
	var cfg := ConfigFile.new()
	for bus_name in _all_buses():
		cfg.set_value("volume", bus_name, get_bus_volume(bus_name))
	cfg.save(SAVE_PATH)


func load_settings() -> void:
	var cfg := ConfigFile.new()
	if cfg.load(SAVE_PATH) != OK:
		return
	for bus_name in _all_buses():
		if cfg.has_section_key("volume", bus_name):
			set_bus_volume(bus_name, float(cfg.get_value("volume", bus_name, 1.0)))
'''

SFX_POOL_3D = '''extends Node
## Multi-Script positional sound pool (autoload "SpatialAudio").
## Example: SpatialAudio.play_at("res://audio/explosion.ogg", global_position)

@export var pool_size := 16
@export var bus: StringName = &"SFX"
@export var max_distance := 40.0
@export var unit_size := 4.0

var _players: Array[AudioStreamPlayer3D] = []
var _next := 0


func _ready() -> void:
	for i in pool_size:
		var p := AudioStreamPlayer3D.new()
		p.bus = bus
		p.max_distance = max_distance
		p.unit_size = unit_size
		add_child(p)
		_players.append(p)


func play_at(stream: Variant, pos: Vector3, volume_db: float = 0.0, pitch: float = 1.0) -> AudioStreamPlayer3D:
	var s: AudioStream = null
	if stream is AudioStream:
		s = stream as AudioStream
	elif (stream is String or stream is StringName) and ResourceLoader.exists(String(stream)):
		s = load(String(stream)) as AudioStream
	if s == null or _players.is_empty():
		return null
	var p := _players[_next]
	_next = (_next + 1) % _players.size()
	p.stream = s
	p.global_position = pos
	p.volume_db = volume_db
	p.pitch_scale = pitch
	p.play()
	return p
'''

SFX_POOL_2D = SFX_POOL_3D.replace("positional sound pool", "2D positional sound pool").replace("AudioStreamPlayer3D", "AudioStreamPlayer2D").replace(
    "pos: Vector3", "pos: Vector2").replace("@export var max_distance := 40.0", "@export var max_distance := 1500.0").replace("@export var unit_size := 4.0\n", "").replace(
    "\t\tp.unit_size = unit_size\n", "")

FOOTSTEPS_3D = '''extends Node
## Multi-Script footsteps. Add this node as a child of a CharacterBody3D and fill `streams`.
## Steps are paced by distance walked, so they speed up with the character.

@export var streams: Array[AudioStream] = []
@export var step_distance := 2.2
@export var min_speed := 0.8
@export var volume_db := -4.0
@export var pitch_jitter := 0.08
@export var bus: StringName = &"SFX"

var _body: CharacterBody3D
var _out: AudioStreamPlayer3D
var _dist := 0.0


func _ready() -> void:
	_body = get_parent() as CharacterBody3D
	if _body == null:
		push_warning("Footsteps must be a child of a CharacterBody3D")
		set_physics_process(false)
		return
	_out = AudioStreamPlayer3D.new()
	_out.bus = bus
	_out.volume_db = volume_db
	_body.add_child.call_deferred(_out)


func _physics_process(delta: float) -> void:
	if _body == null or _out == null or streams.is_empty() or not _out.is_inside_tree():
		return
	var speed := Vector2(_body.velocity.x, _body.velocity.z).length()
	if not _body.is_on_floor() or speed < min_speed:
		_dist = step_distance * 0.6
		return
	_dist += speed * delta
	if _dist >= step_distance:
		_dist = 0.0
		_out.stream = streams[randi() % streams.size()]
		_out.pitch_scale = 1.0 + randf_range(-pitch_jitter, pitch_jitter)
		_out.play()
'''

FOOTSTEPS_2D = '''extends Node
## Multi-Script footsteps. Add this node as a child of a CharacterBody2D and fill `streams`.
## Set require_floor on for platformers so steps stop in the air; leave it off for top-down games.

@export var streams: Array[AudioStream] = []
@export var step_distance := 70.0
@export var min_speed := 20.0
@export var volume_db := -4.0
@export var pitch_jitter := 0.08
@export var require_floor := false
@export var bus: StringName = &"SFX"

var _body: CharacterBody2D
var _out: AudioStreamPlayer2D
var _dist := 0.0


func _ready() -> void:
	_body = get_parent() as CharacterBody2D
	if _body == null:
		push_warning("Footsteps must be a child of a CharacterBody2D")
		set_physics_process(false)
		return
	_out = AudioStreamPlayer2D.new()
	_out.bus = bus
	_out.volume_db = volume_db
	_body.add_child.call_deferred(_out)


func _physics_process(delta: float) -> void:
	if _body == null or _out == null or streams.is_empty() or not _out.is_inside_tree():
		return
	var speed := _body.velocity.length()
	if speed < min_speed or (require_floor and not _body.is_on_floor()):
		_dist = step_distance * 0.6
		return
	_dist += speed * delta
	if _dist >= step_distance:
		_dist = 0.0
		_out.stream = streams[randi() % streams.size()]
		_out.pitch_scale = 1.0 + randf_range(-pitch_jitter, pitch_jitter)
		_out.play()
'''

AMBIENCE_ZONE = '''extends __AREA__
## Multi-Script ambience zone. Fades a looping sound in while a body of `player_group` is inside.
## Loop the stream in its import settings (or use an AudioStreamRandomizer / playlist).

@export var stream: AudioStream
@export var volume_db := -6.0
@export var fade_time := 1.5
@export var player_group: StringName = &"player"
@export var bus: StringName = &"Ambience"

var _out: AudioStreamPlayer
var _tween: Tween
var _inside := 0


func _ready() -> void:
	_out = AudioStreamPlayer.new()
	_out.bus = bus
	_out.stream = stream
	_out.volume_db = -80.0
	add_child(_out)
	body_entered.connect(_on_enter)
	body_exited.connect(_on_exit)


func _on_enter(body: Node) -> void:
	if not body.is_in_group(player_group):
		return
	_inside += 1
	if _inside == 1:
		_fade(volume_db, true)


func _on_exit(body: Node) -> void:
	if not body.is_in_group(player_group):
		return
	_inside = maxi(0, _inside - 1)
	if _inside == 0:
		_fade(-80.0, false)


func _fade(target: float, start: bool) -> void:
	if stream == null:
		return
	if _tween:
		_tween.kill()
	if start and not _out.playing:
		_out.play()
	_tween = create_tween()
	_tween.tween_property(_out, "volume_db", target, fade_time)
	if not start:
		_tween.tween_callback(_out.stop)
'''

MUSIC_PLAYLIST = '''extends Node
## Multi-Script music playlist. Fill `tracks`; plays them in (shuffled) order with a fade-in.
## Tracks must not loop, otherwise `finished` never fires and the playlist stays on one track.

@export var tracks: Array[AudioStream] = []
@export var shuffle := true
@export var autoplay := true
@export var fade_in := 1.5
@export var volume_db := 0.0
@export var bus: StringName = &"Music"

var _out: AudioStreamPlayer
var _tween: Tween
var _order: Array[int] = []
var _i := -1


func _ready() -> void:
	_out = AudioStreamPlayer.new()
	_out.bus = bus
	add_child(_out)
	_out.finished.connect(next)
	if autoplay:
		next()


func _rebuild() -> void:
	_order.clear()
	for k in tracks.size():
		_order.append(k)
	if shuffle:
		_order.shuffle()
	_i = 0


func next() -> void:
	if tracks.is_empty():
		return
	_i += 1
	if _order.size() != tracks.size() or _i >= _order.size():
		_rebuild()
	play_track(_order[_i])


func play_track(index: int) -> void:
	if tracks.is_empty():
		return
	_out.stream = tracks[clampi(index, 0, tracks.size() - 1)]
	_out.volume_db = -80.0
	_out.play()
	if _tween:
		_tween.kill()
	_tween = create_tween()
	_tween.tween_property(_out, "volume_db", volume_db, fade_in)


func stop(fade: float = 1.0) -> void:
	if _tween:
		_tween.kill()
	_tween = create_tween()
	_tween.tween_property(_out, "volume_db", -80.0, fade)
	_tween.tween_callback(_out.stop)
'''

UI_SOUNDS = '''extends Node
## Multi-Script UI sounds (autoload "UiSounds"). Every Button that enters the tree gets a hover and a click sound.

const HOVER_PATH := "__HOVER__"
const CLICK_PATH := "__CLICK__"

@export var volume_db := -6.0

var hover_sound: AudioStream
var click_sound: AudioStream
var _out: AudioStreamPlayer


func _ready() -> void:
	if HOVER_PATH != "" and ResourceLoader.exists(HOVER_PATH):
		hover_sound = load(HOVER_PATH) as AudioStream
	if CLICK_PATH != "" and ResourceLoader.exists(CLICK_PATH):
		click_sound = load(CLICK_PATH) as AudioStream
	_out = AudioStreamPlayer.new()
	_out.bus = "UI" if AudioServer.get_bus_index("UI") != -1 else "Master"
	_out.volume_db = volume_db
	add_child(_out)
	get_tree().node_added.connect(_hook)
	_scan(get_tree().root)


func _scan(n: Node) -> void:
	_hook(n)
	for c in n.get_children():
		_scan(c)


func _hook(n: Node) -> void:
	if n is BaseButton and not n.has_meta("ms_ui_sound"):
		n.set_meta("ms_ui_sound", true)
		n.mouse_entered.connect(_play.bind(hover_sound))
		n.pressed.connect(_play.bind(click_sound))


func _play(s: AudioStream) -> void:
	if s == null:
		return
	_out.stream = s
	_out.play()
'''

AUDIO_KINDS = {
    "audio_manager": {"summary": "AudioManager autoload: bus creation, pooled SFX, music crossfade, ducking, saved volumes.", "modes": ["any"], "autoload": "AudioManager", "scene": False},
    "sfx_pool": {"summary": "Positional one-shot sound pool (autoload SpatialAudio) for 3D or 2D.", "modes": ["3d", "2d"], "autoload": "SpatialAudio", "scene": False},
    "footsteps": {"summary": "Distance-paced footsteps child node for a CharacterBody2D/3D.", "modes": ["3d", "2d"], "autoload": None, "scene": False},
    "ambience_zone": {"summary": "Area that fades a looping ambience in/out as the player enters/leaves.", "modes": ["3d", "2d"], "autoload": None, "scene": True},
    "music_playlist": {"summary": "Shuffled playlist node with fade-in between tracks.", "modes": ["any"], "autoload": None, "scene": False},
    "ui_sounds": {"summary": "Autoload that gives every Button hover and click sounds.", "modes": ["any"], "autoload": "UiSounds", "scene": False},
}
_AK = sorted(AUDIO_KINDS)


def _audio_source(kind, d3, sounds):
    if kind == "audio_manager":
        return AUDIO_MANAGER.replace("__SOUNDS__", _dict_lit(sounds))
    if kind == "sfx_pool":
        return SFX_POOL_3D if d3 else SFX_POOL_2D
    if kind == "footsteps":
        return FOOTSTEPS_3D if d3 else FOOTSTEPS_2D
    if kind == "ambience_zone":
        return AMBIENCE_ZONE.replace("__AREA__", "Area3D" if d3 else "Area2D")
    if kind == "music_playlist":
        return MUSIC_PLAYLIST
    return UI_SOUNDS.replace("__HOVER__", sounds.get("hover", "")).replace("__CLICK__", sounds.get("click", ""))


@tool(G, "ms_godot_audio_kit",
      "Install a GDScript audio system under res://: audio_manager (autoload: Music/SFX/UI/Ambience buses, pooled SFX, music crossfade, ducking, saved volumes), sfx_pool (3D/2D positional), footsteps, "
      "ambience_zone (Area + scene), music_playlist, ui_sounds (autoload). options.sounds {name: res://path} bakes named sounds. No audio is bundled. kind=list shows all.",
      {"kind": {"type": "string", "enum": _AK + ["list"]}, "mode": {"type": "string", "enum": ["3d", "2d"]}, "name": {"type": "string"}, "script_path": {"type": "string"},
       "scene_path": {"type": "string"}, "register_autoload": {"type": "boolean", "description": "Register autoload kinds in project.godot (default true)."},
       "options": {"type": "object", "description": "{sounds: {name: 'res://audio/x.ogg'}} - hover/click are used by ui_sounds."}, "overwrite": OVERWRITE}, [], writes=True, local=True)
def audio_kit(args, ctx):
    kind = str(args.get("kind") or "list").lower()
    if kind == "list":
        return {"kinds": [{"kind": k, "modes": v["modes"], "summary": v["summary"], "autoload": v["autoload"]} for k, v in sorted(AUDIO_KINDS.items())]}
    if kind not in AUDIO_KINDS:
        raise ToolkitError("unknown kind '%s'" % kind, "Kinds: " + ", ".join(_AK))
    spec = AUDIO_KINDS[kind]
    mode = str(args.get("mode") or ("3d" if "3d" in spec["modes"] else "any")).lower()
    if mode not in spec["modes"]:
        raise ToolkitError("%s supports mode %s" % (kind, " / ".join(spec["modes"])))
    d3 = mode != "2d"
    p = _proj(args, ctx)
    warns = []
    sounds = _sounds(args, warns)
    name = ident(args.get("name") or kind.title().replace("_", ""), "Audio")
    out = Out(p, args)
    suffix = "_2d" if (mode == "2d" and kind in ("sfx_pool", "footsteps", "ambience_zone")) else ""
    spath = out.put(norm_res(args.get("script_path") or "res://scripts/audio/%s%s.gd" % (kind, suffix), ".gd", "res://scripts"), _audio_source(kind, d3, sounds), "GDScript")
    scene = None
    if spec["scene"]:
        sb = SB(name, "Area3D" if d3 else "Area2D", "ak_" + kind)
        sb.nodes[0]["body"].append('script = ExtResource("%s")' % sb.ext_res(spath, "Script"))
        if d3:
            _shape3(sb, ".", "box", size=(10, 4, 10))
        else:
            _shape2(sb, ".", "rect", size=(480, 320))
        scene = out.put(norm_res(args.get("scene_path") or "res://scenes/audio/%s.tscn" % name.lower(), ".tscn", "res://scenes"), sb.render(), "scene")
    registered = None
    pj = _abs(p, "res://project.godot")
    if spec["autoload"] and boolean(args.get("register_autoload"), True):
        try:
            text = _read(pj)
        except Exception:
            text = None
        if text is not None:
            registered = spec["autoload"]
            new = set_setting(text, "autoload", registered, '"*%s"' % spath)
            if new != text:
                _write(pj, new, args)
        else:
            warns.append("project.godot not found - register %s as an autoload yourself" % spec["autoload"])
    usage = {
        "audio_manager": "AudioManager.play_sfx(\"hit\") / play_music(stream) / duck() / set_bus_volume(\"Music\", 0.5) / save_settings()",
        "sfx_pool": "SpatialAudio.play_at(stream_or_path, global_position)",
        "footsteps": "Add a Node with this script under your CharacterBody and assign `streams` in the Inspector.",
        "ambience_zone": "Instance the scene, resize its CollisionShape, assign `stream`; make sure the player is in group 'player'.",
        "music_playlist": "Add a Node with this script, assign `tracks` (non-looping streams).",
        "ui_sounds": "Registered as an autoload: every Button in the game now plays the hover/click sounds.",
    }[kind]
    if kind == "ui_sounds" and not (sounds.get("hover") or sounds.get("click")):
        warns.append("no hover/click sounds given - pass options.sounds {hover: 'res://...', click: 'res://...'} (the script is silent until then)")
    return out.done(kind=kind, mode=mode, script=spath, scene=scene, autoload=registered, usage=usage, warnings=warns, summary=spec["summary"])


# ───────────────────────────── NPC scripts ─────────────────────────────
NPC_3D = '''extends CharacterBody3D
## Multi-Script NPC brain (3D). Set `behavior` in the Inspector:
## idle, wander, patrol, follow, guard, flee, enemy_melee. Uses a NavigationAgent3D when a navmesh exists,
## otherwise walks in a straight line. Targets are bodies in `target_group`; damage goes to take_damage(amount, source).

signal state_changed(new_state: String)
signal attacked(target: Node)

@export_enum("idle", "wander", "patrol", "follow", "guard", "flee", "enemy_melee") var behavior: String = "__BEHAVIOR__"
@export var speed := 2.5
@export var run_speed := 4.5
@export var gravity := 20.0
@export var detect_range := 12.0
@export var lose_range := 18.0
@export var attack_range := 1.6
@export var attack_damage := 10.0
@export var attack_cooldown := 1.2
@export var wander_radius := 8.0
@export var pause_at_point := 1.5
@export var turn_speed := 8.0
@export var use_navmesh := true
@export var target_group: StringName = &"player"
@export var patrol_points: Array[Vector3] = __POINTS__

var state := "idle"
var _agent: NavigationAgent3D
var _home := Vector3.ZERO
var _target: Node3D
var _spd := 0.0
var _wait := 0.0
var _cd := 0.0
var _pi := 0
var _goal := Vector3.ZERO
var _has_goal := false
var _stuck := 0.0


func _ready() -> void:
	_home = global_position
	_agent = get_node_or_null("NavigationAgent3D") as NavigationAgent3D
	if _agent == null:
		_agent = NavigationAgent3D.new()
		_agent.path_desired_distance = 0.6
		_agent.target_desired_distance = 0.8
		add_child(_agent)
	add_to_group("npc")
	_set_state(behavior)


func _set_state(s: String) -> void:
	if s == state:
		return
	state = s
	state_changed.emit(s)


func _flat_dist(p: Vector3) -> float:
	return Vector2(global_position.x - p.x, global_position.z - p.z).length()


func _has_navmesh() -> bool:
	return use_navmesh and _agent != null and not NavigationServer3D.map_get_regions(_agent.get_navigation_map()).is_empty()


func _path_dir(pos: Vector3) -> Vector3:
	var d := Vector3.ZERO
	if _has_navmesh():
		_agent.target_position = pos
		if _agent.is_navigation_finished():
			return Vector3.ZERO
		d = _agent.get_next_path_position() - global_position
	else:
		d = pos - global_position
	d.y = 0.0
	if d.length() < 0.15:
		return Vector3.ZERO
	return d.normalized()


func _find_target() -> Node3D:
	var best: Node3D = null
	var best_d := lose_range
	for n in get_tree().get_nodes_in_group(target_group):
		var n3 := n as Node3D
		if n3 == null or n3 == self:
			continue
		var d := global_position.distance_to(n3.global_position)
		if d < best_d:
			best_d = d
			best = n3
	return best


func _wander(delta: float) -> Vector3:
	if _wait > 0.0:
		_wait -= delta
		return Vector3.ZERO
	if not _has_goal:
		var a := randf() * TAU
		var r := randf_range(2.0, wander_radius)
		_goal = _home + Vector3(cos(a) * r, 0.0, sin(a) * r)
		_has_goal = true
	if _flat_dist(_goal) < 0.8:
		_has_goal = false
		_wait = randf_range(1.0, 4.0)
		return Vector3.ZERO
	return _path_dir(_goal)


func _patrol(delta: float) -> Vector3:
	if patrol_points.is_empty():
		return _wander(delta)
	if _wait > 0.0:
		_wait -= delta
		return Vector3.ZERO
	var goal := patrol_points[_pi]
	if _flat_dist(goal) < 0.9:
		_pi = (_pi + 1) % patrol_points.size()
		_wait = pause_at_point
		return Vector3.ZERO
	return _path_dir(goal)


func _fight(delta: float, leash: bool) -> Vector3:
	var chasing := _target != null and (not leash or _flat_dist(_home) < lose_range)
	if chasing and global_position.distance_to(_target.global_position) > detect_range and state != "chase":
		chasing = false
	if not chasing:
		_set_state("guard" if leash else "enemy_melee")
		if leash:
			return _path_dir(_home) if _flat_dist(_home) > 1.0 else Vector3.ZERO
		return _wander(delta)
	_set_state("chase")
	var d := global_position.distance_to(_target.global_position)
	if d <= attack_range:
		if _cd <= 0.0:
			_cd = attack_cooldown
			attacked.emit(_target)
			if _target.has_method("take_damage"):
				_target.take_damage(attack_damage, self)
		return Vector3.ZERO
	_spd = run_speed
	return _path_dir(_target.global_position)


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y -= gravity * delta
	_cd = maxf(0.0, _cd - delta)
	_target = _find_target()
	_spd = speed
	var dir := Vector3.ZERO
	match behavior:
		"wander":
			dir = _wander(delta)
		"patrol":
			dir = _patrol(delta)
		"follow":
			if _target != null and global_position.distance_to(_target.global_position) > 2.2:
				dir = _path_dir(_target.global_position)
				_spd = run_speed
		"guard":
			dir = _fight(delta, true)
		"enemy_melee":
			dir = _fight(delta, false)
		"flee":
			if _target != null and global_position.distance_to(_target.global_position) < detect_range:
				dir = global_position - _target.global_position
				dir.y = 0.0
				dir = dir.normalized()
				_spd = run_speed
	velocity.x = dir.x * _spd
	velocity.z = dir.z * _spd
	if dir.length() > 0.01:
		rotation.y = lerp_angle(rotation.y, atan2(-dir.x, -dir.z), clampf(turn_speed * delta, 0.0, 1.0))
	move_and_slide()
	if dir.length() > 0.01 and get_real_velocity().length() < 0.2:
		_stuck += delta
		if _stuck > 2.0:
			_stuck = 0.0
			_has_goal = false
	else:
		_stuck = 0.0
'''

NPC_2D = '''extends CharacterBody2D
## Multi-Script NPC brain (2D, top-down movement). Set `behavior` in the Inspector:
## idle, wander, patrol, follow, guard, flee, enemy_melee. Uses a NavigationAgent2D when a navmesh exists,
## otherwise walks in a straight line. Targets are bodies in `target_group`; damage goes to take_damage(amount, source).

signal state_changed(new_state: String)
signal attacked(target: Node)

@export_enum("idle", "wander", "patrol", "follow", "guard", "flee", "enemy_melee") var behavior: String = "__BEHAVIOR__"
@export var speed := 80.0
@export var run_speed := 140.0
@export var detect_range := 320.0
@export var lose_range := 480.0
@export var attack_range := 36.0
@export var attack_damage := 10.0
@export var attack_cooldown := 1.2
@export var wander_radius := 220.0
@export var pause_at_point := 1.5
@export var use_navmesh := true
@export var target_group: StringName = &"player"
@export var patrol_points: Array[Vector2] = __POINTS__

var state := "idle"
var _agent: NavigationAgent2D
var _home := Vector2.ZERO
var _target: Node2D
var _spd := 0.0
var _wait := 0.0
var _cd := 0.0
var _pi := 0
var _goal := Vector2.ZERO
var _has_goal := false
var _stuck := 0.0


func _ready() -> void:
	_home = global_position
	_agent = get_node_or_null("NavigationAgent2D") as NavigationAgent2D
	if _agent == null:
		_agent = NavigationAgent2D.new()
		add_child(_agent)
	add_to_group("npc")
	_set_state(behavior)


func _set_state(s: String) -> void:
	if s == state:
		return
	state = s
	state_changed.emit(s)


func _has_navmesh() -> bool:
	return use_navmesh and _agent != null and not NavigationServer2D.map_get_regions(_agent.get_navigation_map()).is_empty()


func _path_dir(pos: Vector2) -> Vector2:
	var d := Vector2.ZERO
	if _has_navmesh():
		_agent.target_position = pos
		if _agent.is_navigation_finished():
			return Vector2.ZERO
		d = _agent.get_next_path_position() - global_position
	else:
		d = pos - global_position
	if d.length() < 4.0:
		return Vector2.ZERO
	return d.normalized()


func _find_target() -> Node2D:
	var best: Node2D = null
	var best_d := lose_range
	for n in get_tree().get_nodes_in_group(target_group):
		var n2 := n as Node2D
		if n2 == null or n2 == self:
			continue
		var d := global_position.distance_to(n2.global_position)
		if d < best_d:
			best_d = d
			best = n2
	return best


func _wander(delta: float) -> Vector2:
	if _wait > 0.0:
		_wait -= delta
		return Vector2.ZERO
	if not _has_goal:
		_goal = _home + Vector2.from_angle(randf() * TAU) * randf_range(40.0, wander_radius)
		_has_goal = true
	if global_position.distance_to(_goal) < 12.0:
		_has_goal = false
		_wait = randf_range(1.0, 4.0)
		return Vector2.ZERO
	return _path_dir(_goal)


func _patrol(delta: float) -> Vector2:
	if patrol_points.is_empty():
		return _wander(delta)
	if _wait > 0.0:
		_wait -= delta
		return Vector2.ZERO
	var goal := patrol_points[_pi]
	if global_position.distance_to(goal) < 12.0:
		_pi = (_pi + 1) % patrol_points.size()
		_wait = pause_at_point
		return Vector2.ZERO
	return _path_dir(goal)


func _fight(delta: float, leash: bool) -> Vector2:
	var chasing := _target != null and (not leash or global_position.distance_to(_home) < lose_range)
	if chasing and global_position.distance_to(_target.global_position) > detect_range and state != "chase":
		chasing = false
	if not chasing:
		_set_state("guard" if leash else "enemy_melee")
		if leash:
			return _path_dir(_home) if global_position.distance_to(_home) > 12.0 else Vector2.ZERO
		return _wander(delta)
	_set_state("chase")
	if global_position.distance_to(_target.global_position) <= attack_range:
		if _cd <= 0.0:
			_cd = attack_cooldown
			attacked.emit(_target)
			if _target.has_method("take_damage"):
				_target.take_damage(attack_damage, self)
		return Vector2.ZERO
	_spd = run_speed
	return _path_dir(_target.global_position)


func _physics_process(delta: float) -> void:
	_cd = maxf(0.0, _cd - delta)
	_target = _find_target()
	_spd = speed
	var dir := Vector2.ZERO
	match behavior:
		"wander":
			dir = _wander(delta)
		"patrol":
			dir = _patrol(delta)
		"follow":
			if _target != null and global_position.distance_to(_target.global_position) > 48.0:
				dir = _path_dir(_target.global_position)
				_spd = run_speed
		"guard":
			dir = _fight(delta, true)
		"enemy_melee":
			dir = _fight(delta, false)
		"flee":
			if _target != null and global_position.distance_to(_target.global_position) < detect_range:
				dir = (global_position - _target.global_position).normalized()
				_spd = run_speed
	velocity = dir * _spd
	move_and_slide()
	if dir.length() > 0.01 and get_real_velocity().length() < 4.0:
		_stuck += delta
		if _stuck > 2.0:
			_stuck = 0.0
			_has_goal = false
	else:
		_stuck = 0.0
'''

DIALOGUE = '''extends Node
## Multi-Script talk-to dialogue. Add as a child of an NPC (Node2D or Node3D). Press `interact_action` near the NPC
## to open a text box and advance through `lines`. Walking away closes it. Signals: line_shown(text), finished.

signal line_shown(text: String)
signal finished

@export var npc_name := "__NAME__"
@export var lines: Array[String] = __LINES__
@export var interact_action: StringName = &"interact"
@export var radius := 3.0
@export var player_group: StringName = &"player"

var _host: Node
var _layer: CanvasLayer
var _text: Label
var _i := -1


func _ready() -> void:
	_host = get_parent()
	_layer = CanvasLayer.new()
	_layer.layer = 50
	_layer.visible = false
	add_child(_layer)
	var panel := PanelContainer.new()
	panel.anchor_left = 0.15
	panel.anchor_right = 0.85
	panel.anchor_top = 0.72
	panel.anchor_bottom = 0.95
	_layer.add_child(panel)
	var box := VBoxContainer.new()
	panel.add_child(box)
	var title := Label.new()
	title.text = npc_name
	box.add_child(title)
	_text = Label.new()
	_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_text.size_flags_vertical = Control.SIZE_EXPAND_FILL
	box.add_child(_text)


func _near() -> bool:
	if _host == null or not ("global_position" in _host):
		return false
	for p in get_tree().get_nodes_in_group(player_group):
		if "global_position" in p and typeof(p.global_position) == typeof(_host.global_position):
			if p.global_position.distance_to(_host.global_position) <= radius:
				return true
	return false


func _process(_delta: float) -> void:
	if _i >= 0 and not _near():
		_close()


func _unhandled_input(event: InputEvent) -> void:
	if not InputMap.has_action(interact_action) or not event.is_action_pressed(interact_action):
		return
	if _i < 0 and not _near():
		return
	get_viewport().set_input_as_handled()
	_advance()


func _advance() -> void:
	if lines.is_empty():
		return
	_i += 1
	if _i >= lines.size():
		_close()
		return
	_layer.visible = true
	_text.text = lines[_i]
	line_shown.emit(lines[_i])


func _close() -> void:
	var was_open := _i >= 0
	_i = -1
	_layer.visible = false
	if was_open:
		finished.emit()
'''

SPAWNER_3D = '''extends Node3D
## Multi-Script NPC spawner. Assign `npc_scene`; keeps up to `max_alive` NPCs around this node.

@export var npc_scene: PackedScene
@export var max_alive := 5
@export var interval := 6.0
@export var radius := 10.0
@export var spawn_on_start := 3
@export var behaviors: Array[String] = []

var _alive: Array = []
var _t := 0.0


func _ready() -> void:
	for i in spawn_on_start:
		spawn()


func _process(delta: float) -> void:
	_t += delta
	if _t >= interval:
		_t = 0.0
		spawn()


func spawn() -> Node:
	if npc_scene == null:
		return null
	_alive = _alive.filter(func(n): return is_instance_valid(n))
	if _alive.size() >= max_alive:
		return null
	var npc := npc_scene.instantiate()
	var a := randf() * TAU
	var r := randf_range(1.0, radius)
	if not behaviors.is_empty() and "behavior" in npc:
		npc.behavior = behaviors[randi() % behaviors.size()]
	npc.position = position + Vector3(cos(a) * r, 0.0, sin(a) * r)
	get_parent().add_child.call_deferred(npc)
	_alive.append(npc)
	return npc
'''

SPAWNER_2D = '''extends Node2D
## Multi-Script NPC spawner. Assign `npc_scene`; keeps up to `max_alive` NPCs around this node.

@export var npc_scene: PackedScene
@export var max_alive := 5
@export var interval := 6.0
@export var radius := 240.0
@export var spawn_on_start := 3
@export var behaviors: Array[String] = []

var _alive: Array = []
var _t := 0.0


func _ready() -> void:
	for i in spawn_on_start:
		spawn()


func _process(delta: float) -> void:
	_t += delta
	if _t >= interval:
		_t = 0.0
		spawn()


func spawn() -> Node:
	if npc_scene == null:
		return null
	_alive = _alive.filter(func(n): return is_instance_valid(n))
	if _alive.size() >= max_alive:
		return null
	var npc := npc_scene.instantiate()
	if not behaviors.is_empty() and "behavior" in npc:
		npc.behavior = behaviors[randi() % behaviors.size()]
	npc.position = position + Vector2.from_angle(randf() * TAU) * randf_range(24.0, radius)
	get_parent().add_child.call_deferred(npc)
	_alive.append(npc)
	return npc
'''

NPC_BEHAVIORS = ["idle", "wander", "patrol", "follow", "guard", "flee", "enemy_melee"]
NPC_KINDS = {
    "npc_brain": {"summary": "CharacterBody NPC with idle/wander/patrol/follow/guard/flee/enemy_melee, navmesh or straight-line movement, plus a prefab scene.", "inputs": []},
    "dialogue": {"summary": "Talk-to dialogue child node with an auto-built text box (press interact near the NPC).", "inputs": ["interact"]},
    "npc_spawner": {"summary": "Spawner that keeps up to N NPC scenes alive around it (random behaviors optional).", "inputs": []},
}
_NK = sorted(NPC_KINDS)


def _points(args, d3):
    out = []
    for pt in as_list(args.get("waypoints")):
        v = as_list(pt)
        try:
            nums = [float(x) for x in v]
        except (TypeError, ValueError):
            raise ToolkitError("waypoints must be [x, y, z] (3D) or [x, y] (2D) number lists")
        if len(nums) != (3 if d3 else 2) or any(abs(n) > 1e6 or n != n for n in nums):
            raise ToolkitError("each waypoint needs %d finite numbers" % (3 if d3 else 2))
        out.append(nums)
    return out


def _points_lit(pts, d3):
    if not pts:
        return "[]"
    ctor = "Vector3" if d3 else "Vector2"
    return "[" + ", ".join("%s(%s)" % (ctor, ", ".join(f(x) for x in p)) for p in pts) + "]"


def _gd_str(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")


@tool(G, "ms_godot_npc_kit",
      "Install an NPC system (2D or 3D): npc_brain (CharacterBody script with idle/wander/patrol/follow/guard/flee/enemy_melee, NavigationAgent or straight-line fallback, take_damage(amount, source) hits) "
      "plus a prefab scene; dialogue (talk-to text box, interact input); npc_spawner. waypoints sets patrol points; lines sets dialogue. kind=list shows all.",
      {"kind": {"type": "string", "enum": _NK + ["list"]}, "mode": {"type": "string", "enum": ["3d", "2d"]}, "name": {"type": "string"}, "behavior": {"type": "string", "enum": NPC_BEHAVIORS},
       "waypoints": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}, "description": "Patrol points: [[x,y,z],...] in 3D or [[x,y],...] in 2D (global coordinates)."},
       "lines": {"type": "array", "items": {"type": "string"}, "description": "Dialogue lines."}, "npc_name": {"type": "string"}, "color": {"type": ["string", "array"]},
       "script_path": {"type": "string"}, "scene_path": {"type": "string"}, "with_scene": {"type": "boolean"}, "define_inputs": {"type": "boolean"}, "overwrite": OVERWRITE}, [], writes=True, local=True)
def npc_kit(args, ctx):
    kind = str(args.get("kind") or "list").lower()
    if kind == "list":
        return {"kinds": [{"kind": k, "modes": ["3d", "2d"], "summary": v["summary"], "inputs": v["inputs"]} for k, v in sorted(NPC_KINDS.items())], "behaviors": NPC_BEHAVIORS}
    if kind not in NPC_KINDS:
        raise ToolkitError("unknown kind '%s'" % kind, "Kinds: " + ", ".join(_NK))
    mode = str(args.get("mode") or "3d").lower()
    if mode not in ("3d", "2d"):
        raise ToolkitError("mode must be 3d or 2d")
    d3 = mode == "3d"
    behavior = str(args.get("behavior") or "wander").lower()
    if behavior not in NPC_BEHAVIORS:
        raise ToolkitError("unknown behavior '%s'" % behavior, "Behaviors: " + ", ".join(NPC_BEHAVIORS))
    p = _proj(args, ctx)
    name = ident(args.get("name") or {"npc_brain": "Npc", "dialogue": "NpcDialogue", "npc_spawner": "NpcSpawner"}[kind], "Npc")
    out = Out(p, args)
    warns = []
    pts = _points(args, d3)
    if behavior == "patrol" and not pts and kind == "npc_brain":
        warns.append("patrol without waypoints wanders instead - pass waypoints or fill patrol_points in the Inspector")
    if kind == "npc_brain":
        src = (NPC_3D if d3 else NPC_2D).replace("__BEHAVIOR__", behavior).replace("__POINTS__", _points_lit(pts, d3))
    elif kind == "dialogue":
        lines = [_gd_str(x)[:240] for x in as_list(args.get("lines")) if str(x).strip()][:30] or ["Hello, traveller!", "Safe travels."]
        lit = "[" + ", ".join('"%s"' % x for x in lines) + "]"
        src = DIALOGUE.replace("__NAME__", _gd_str(args.get("npc_name") or "Villager")[:60]).replace("__LINES__", lit)
    else:
        src = SPAWNER_3D if d3 else SPAWNER_2D
    suffix = "" if d3 else "_2d"
    spath = out.put(norm_res(args.get("script_path") or "res://scripts/npc/%s%s.gd" % (kind, suffix), ".gd", "res://scripts"), src, "GDScript")
    scene = None
    if kind == "npc_brain" and boolean(args.get("with_scene"), True):
        col = args.get("color") or "#6fa8dc"
        sb = SB(name, "CharacterBody3D" if d3 else "CharacterBody2D", "nk_npc")
        sb.nodes[0]["body"].append('script = ExtResource("%s")' % sb.ext_res(spath, "Script"))
        if d3:
            _shape3(sb, ".", "capsule", r=0.4, h=1.8, pos=(0, 0.9, 0))
            _mesh_node(sb, ".", "CapsuleMesh", ["radius = 0.4", "height = 1.8"], _mats(sb, col), "Body", pos=(0, 0.9, 0))
            sb.node("NavigationAgent3D", "NavigationAgent3D", ".", {"path_desired_distance": "0.6", "target_desired_distance": "0.8"})
        else:
            _shape2(sb, ".", "capsule", r=13, h=32)
            _poly(sb, ".", col, 26, 32)
            sb.node("NavigationAgent2D", "NavigationAgent2D", ".")
        scene = out.put(norm_res(args.get("scene_path") or "res://scenes/npc/%s.tscn" % name.lower(), ".tscn", "res://scenes"), sb.render(), "scene")
    added = []
    pj = _abs(p, "res://project.godot")
    if kind == "dialogue" and boolean(args.get("define_inputs"), True):
        try:
            text = _read(pj)
        except Exception:
            text = None
        if text is not None:
            new, added = define_inputs(text, NPC_KINDS[kind]["inputs"], args)
            if new != text:
                _write(pj, new, args)
    usage = {"npc_brain": "Instance the scene (or attach the script to a CharacterBody) and set `behavior`; put the player in group 'player'. Bake a NavigationRegion for pathfinding, or leave it for straight-line movement.",
             "dialogue": "Add a Node with this script as a child of the NPC; the player must be in group 'player'.",
             "npc_spawner": "Add the node, assign `npc_scene` (e.g. the npc_brain scene) and set max_alive / interval."}[kind]
    return out.done(kind=kind, mode=mode, behavior=behavior if kind == "npc_brain" else None, script=spath, scene=scene, inputs_defined=added, usage=usage, warnings=warns, summary=NPC_KINDS[kind]["summary"])
