# SPDX-License-Identifier: GPL-3.0-or-later
"""GDScript 4 gameplay templates for ms_godot_gameplay_kit (every script is compiled by a real headless Godot in the test-suite).

A tiny preprocessor keeps 2D/3D variants in one source:
  ##3D ... ##END   lines only for 3D          ##2D ... ##END   lines only for 2D
  @@D@@ -> 2D|3D   @@d@@ -> 2d|3d   @@V@@ -> Vector2|Vector3
Scripts never depend on each other through class_name; they talk through groups, signals and duck-typed methods:
  groups: player, enemy, coin, goal, checkpoint, killzone, player_spawn, enemy_spawn, saveable
  conventions: take_damage(amount, source), respawn(), set_meta("ms_checkpoint", pos), GameManager autoload (optional)."""
import re

T = {}      # name -> {"summary":..., "modes":(...), "src": ...}


def render(src, d3):
    out, skip = [], None
    for ln in src.split("\n"):
        s = ln.strip()
        if s in ("##3D", "##2D"):
            skip = (s == "##2D") if d3 else (s == "##3D")
            continue
        if s == "##END":
            skip = None
            continue
        if skip:
            continue
        out.append(ln)
    t = "\n".join(out)
    return t.replace("@@D@@", "3D" if d3 else "2D").replace("@@d@@", "3d" if d3 else "2d").replace("@@V@@", "Vector3" if d3 else "Vector2")


def add(name, summary, src, modes=("3d", "2d"), inputs=(), groups=(), autoload=False, extra=None, files=None):
    T[name] = {"summary": summary, "src": src, "modes": modes, "inputs": list(inputs), "groups": list(groups), "autoload": autoload, "extra": extra or {}, "files": files or {}}


def render_kind(name, d3):
    t = T[name]
    src = render(t["src"], d3)
    for k, v in t["extra"].items():
        src = src.replace("@@%s@@" % k, v[0] if d3 else v[1])
    left = re.findall(r"@@(\w+)@@", src)
    if left:
        raise ValueError("unfilled placeholders in %s: %s" % (name, left))
    return src


# ───────────────────────────── player controllers ─────────────────────────────
add("player_third_person", "Third-person CharacterBody3D: camera-relative movement, sprint, coyote time + jump buffer, mouse-look camera rig.", '''extends CharacterBody3D
## Third-person controller. Scene layout: this node + CollisionShape3D + Visual (Node3D) + CameraRig (Node3D) > SpringArm3D > Camera3D.
## Actions: move_left, move_right, move_forward, move_back, jump, sprint. Mouse look rotates the CameraRig.

signal jumped
signal landed
signal died
signal respawned

@export var walk_speed: float = 5.0
@export var sprint_speed: float = 8.5
@export var acceleration: float = 14.0
@export_range(0.0, 1.0) var air_control: float = 0.45
@export var jump_velocity: float = 5.4
@export var turn_speed: float = 12.0
@export var coyote_time: float = 0.12
@export var jump_buffer_time: float = 0.12
@export var mouse_sensitivity: float = 0.003
@export var capture_mouse: bool = true
@export var fall_limit: float = -60.0
@export var camera_rig_path: NodePath = ^"CameraRig"
@export var visual_path: NodePath = ^"Visual"

var gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")
var _coyote: float = 0.0
var _buffer: float = 0.0
var _was_on_floor: bool = false
var _pitch: float = -0.35
var _rig: Node3D
var _visual: Node3D
var _spawn: Vector3


func _ready() -> void:
	add_to_group("player")
	_spawn = global_position
	_rig = get_node_or_null(camera_rig_path) as Node3D
	_visual = get_node_or_null(visual_path) as Node3D
	if _rig:
		_rig.top_level = true
		_rig.global_position = global_position + Vector3(0, 1.4, 0)
	if capture_mouse:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED and _rig:
		_rig.rotation.y -= event.relative.x * mouse_sensitivity
		_pitch = clampf(_pitch - event.relative.y * mouse_sensitivity, -1.2, 0.5)
		_rig.rotation.x = _pitch
	elif event.is_action_pressed("ui_cancel"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED else Input.MOUSE_MODE_CAPTURED


func _physics_process(delta: float) -> void:
	if _rig:
		_rig.global_position = _rig.global_position.lerp(global_position + Vector3(0, 1.4, 0), 1.0 - exp(-16.0 * delta))
	if not is_on_floor():
		velocity.y -= gravity * delta
		_coyote -= delta
	else:
		_coyote = coyote_time
		if not _was_on_floor:
			landed.emit()
	_buffer -= delta
	if Input.is_action_just_pressed("jump"):
		_buffer = jump_buffer_time
	if _buffer > 0.0 and _coyote > 0.0:
		velocity.y = jump_velocity
		_buffer = 0.0
		_coyote = 0.0
		jumped.emit()
	var input := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var yaw: float = _rig.global_rotation.y if _rig else global_rotation.y
	var dir := Vector3(input.x, 0.0, input.y).rotated(Vector3.UP, yaw)
	var target_speed: float = sprint_speed if Input.is_action_pressed("sprint") else walk_speed
	var control: float = 1.0 if is_on_floor() else air_control
	var wanted := dir * target_speed
	velocity.x = move_toward(velocity.x, wanted.x, acceleration * target_speed * control * delta)
	velocity.z = move_toward(velocity.z, wanted.z, acceleration * target_speed * control * delta)
	if dir.length() > 0.1 and _visual:
		var target_yaw := atan2(-dir.x, -dir.z)
		_visual.rotation.y = lerp_angle(_visual.rotation.y, target_yaw, 1.0 - exp(-turn_speed * delta))
	_was_on_floor = is_on_floor()
	move_and_slide()
	if global_position.y < fall_limit:
		respawn()


## Anything that can hurt the player calls this (enemies, projectiles, hazards).
func take_damage(amount: float, source: Node = null) -> void:
	var health := get_node_or_null("Health")
	if health and health.has_method("damage"):
		health.damage(amount, source)


func respawn() -> void:
	global_position = get_meta("ms_checkpoint", _spawn)
	velocity = Vector3.ZERO
	respawned.emit()


func die() -> void:
	died.emit()
	respawn()
''', modes=("3d",), inputs=("move_left", "move_right", "move_forward", "move_back", "jump", "sprint"), groups=("player",))

add("player_first_person", "First-person CharacterBody3D: mouse-look head, sprint, head-bob, coyote time + jump buffer.", '''extends CharacterBody3D
## First-person controller. Scene layout: this node + CollisionShape3D + Head (Node3D) > Camera3D.
## Actions: move_left, move_right, move_forward, move_back, jump, sprint.

signal jumped
signal landed
signal died
signal respawned

@export var walk_speed: float = 5.0
@export var sprint_speed: float = 8.0
@export var acceleration: float = 12.0
@export var jump_velocity: float = 4.8
@export var mouse_sensitivity: float = 0.0022
@export var coyote_time: float = 0.1
@export var jump_buffer_time: float = 0.12
@export var head_bob: bool = true
@export var fall_limit: float = -60.0
@export var head_path: NodePath = ^"Head"

var gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")
var _head: Node3D
var _coyote: float = 0.0
var _buffer: float = 0.0
var _bob: float = 0.0
var _was_on_floor: bool = false
var _spawn: Vector3


func _ready() -> void:
	add_to_group("player")
	_spawn = global_position
	_head = get_node_or_null(head_path) as Node3D
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-event.relative.x * mouse_sensitivity)
		if _head:
			_head.rotate_x(-event.relative.y * mouse_sensitivity)
			_head.rotation.x = clampf(_head.rotation.x, deg_to_rad(-88.0), deg_to_rad(88.0))
	elif event.is_action_pressed("ui_cancel"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED else Input.MOUSE_MODE_CAPTURED


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y -= gravity * delta
		_coyote -= delta
	else:
		_coyote = coyote_time
		if not _was_on_floor:
			landed.emit()
	_buffer -= delta
	if Input.is_action_just_pressed("jump"):
		_buffer = jump_buffer_time
	if _buffer > 0.0 and _coyote > 0.0:
		velocity.y = jump_velocity
		_buffer = 0.0
		_coyote = 0.0
		jumped.emit()
	var input := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var dir := (transform.basis * Vector3(input.x, 0.0, input.y)).normalized()
	var speed: float = sprint_speed if Input.is_action_pressed("sprint") else walk_speed
	velocity.x = move_toward(velocity.x, dir.x * speed, acceleration * speed * delta)
	velocity.z = move_toward(velocity.z, dir.z * speed, acceleration * speed * delta)
	_was_on_floor = is_on_floor()
	move_and_slide()
	if head_bob and _head:
		var moving: bool = is_on_floor() and Vector2(velocity.x, velocity.z).length() > 0.5
		if moving:
			_bob += delta * Vector2(velocity.x, velocity.z).length() * 1.6
		_head.position.y = lerpf(_head.position.y, 0.7 + (sin(_bob) * 0.04 if moving else 0.0), 1.0 - exp(-12.0 * delta))
	if global_position.y < fall_limit:
		respawn()


func take_damage(amount: float, source: Node = null) -> void:
	var health := get_node_or_null("Health")
	if health and health.has_method("damage"):
		health.damage(amount, source)


func respawn() -> void:
	global_position = get_meta("ms_checkpoint", _spawn)
	velocity = Vector3.ZERO
	respawned.emit()


func die() -> void:
	died.emit()
	respawn()
''', modes=("3d",), inputs=("move_left", "move_right", "move_forward", "move_back", "jump", "sprint"), groups=("player",))

add("player_platformer", "2D platformer CharacterBody2D: acceleration, coyote time, jump buffer, variable jump height, double jump, optional dash.", '''extends CharacterBody2D
## 2D platformer controller. Scene layout: this node + CollisionShape2D + Visual (Node2D / Sprite2D / AnimatedSprite2D).
## Actions: move_left, move_right, jump, dash (optional).

signal jumped
signal landed
signal dashed
signal died
signal respawned

@export var speed: float = 220.0
@export var acceleration: float = 1800.0
@export var friction: float = 2200.0
@export var air_acceleration: float = 1100.0
@export var jump_velocity: float = -430.0
@export var max_jumps: int = 2
@export_range(0.1, 1.0) var jump_cut: float = 0.45
@export var coyote_time: float = 0.1
@export var jump_buffer_time: float = 0.12
@export var max_fall_speed: float = 900.0
@export var dash_speed: float = 520.0
@export var dash_time: float = 0.14
@export var dash_cooldown: float = 0.6
@export var fall_limit: float = 2000.0
@export var visual_path: NodePath = ^"Visual"

var gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")
var facing: int = 1
var _jumps_left: int = 0
var _coyote: float = 0.0
var _buffer: float = 0.0
var _dash_left: float = 0.0
var _dash_cd: float = 0.0
var _was_on_floor: bool = false
var _spawn: Vector2
var _visual: Node2D


func _ready() -> void:
	add_to_group("player")
	_spawn = global_position
	_visual = get_node_or_null(visual_path) as Node2D
	_jumps_left = max_jumps


func _physics_process(delta: float) -> void:
	var dir := Input.get_axis("move_left", "move_right")
	if dir != 0.0:
		facing = 1 if dir > 0.0 else -1
		if _visual:
			_visual.scale.x = absf(_visual.scale.x) * facing
	_dash_cd -= delta
	if InputMap.has_action("dash") and Input.is_action_just_pressed("dash") and _dash_cd <= 0.0:
		_dash_left = dash_time
		_dash_cd = dash_cooldown
		dashed.emit()
	if _dash_left > 0.0:
		_dash_left -= delta
		velocity = Vector2(facing * dash_speed, 0.0)
		move_and_slide()
		return
	if is_on_floor():
		_coyote = coyote_time
		_jumps_left = max_jumps
		if not _was_on_floor:
			landed.emit()
	else:
		_coyote -= delta
		velocity.y = minf(velocity.y + gravity * delta, max_fall_speed)
	_buffer -= delta
	if Input.is_action_just_pressed("jump"):
		_buffer = jump_buffer_time
	if _buffer > 0.0 and (_coyote > 0.0 or _jumps_left > 1):
		if _coyote <= 0.0:
			_jumps_left -= 1
		else:
			_jumps_left = max_jumps - 1
		velocity.y = jump_velocity
		_buffer = 0.0
		_coyote = 0.0
		jumped.emit()
	if Input.is_action_just_released("jump") and velocity.y < 0.0:
		velocity.y *= jump_cut
	var accel: float = acceleration if is_on_floor() else air_acceleration
	if dir != 0.0:
		velocity.x = move_toward(velocity.x, dir * speed, accel * delta)
	else:
		velocity.x = move_toward(velocity.x, 0.0, friction * delta)
	_was_on_floor = is_on_floor()
	move_and_slide()
	if global_position.y > fall_limit:
		respawn()


func take_damage(amount: float, source: Node = null) -> void:
	var health := get_node_or_null("Health")
	if health and health.has_method("damage"):
		health.damage(amount, source)


func respawn() -> void:
	global_position = get_meta("ms_checkpoint", _spawn)
	velocity = Vector2.ZERO
	respawned.emit()


func die() -> void:
	died.emit()
	respawn()
''', modes=("2d",), inputs=("move_left", "move_right", "jump", "dash"), groups=("player",))

add("player_topdown", "Top-down CharacterBody2D: smooth 8-direction movement, sprint, dash, facing.", '''extends CharacterBody2D
## Top-down controller. Scene layout: this node + CollisionShape2D + Visual (Node2D).
## Actions: move_left, move_right, move_up, move_down, sprint, dash (optional).

signal dashed
signal died
signal respawned

@export var speed: float = 190.0
@export var sprint_multiplier: float = 1.6
@export var acceleration: float = 1600.0
@export var friction: float = 2000.0
@export var dash_speed: float = 520.0
@export var dash_time: float = 0.12
@export var dash_cooldown: float = 0.6
@export var rotate_visual: bool = false
@export var visual_path: NodePath = ^"Visual"

var facing: Vector2 = Vector2.DOWN
var _dash_left: float = 0.0
var _dash_cd: float = 0.0
var _dash_dir: Vector2 = Vector2.ZERO
var _spawn: Vector2
var _visual: Node2D


func _ready() -> void:
	add_to_group("player")
	_spawn = global_position
	_visual = get_node_or_null(visual_path) as Node2D


func _physics_process(delta: float) -> void:
	var input := Input.get_vector("move_left", "move_right", "move_up", "move_down")
	if input != Vector2.ZERO:
		facing = input.normalized()
		if rotate_visual and _visual:
			_visual.rotation = lerp_angle(_visual.rotation, facing.angle(), 1.0 - exp(-14.0 * delta))
	_dash_cd -= delta
	if InputMap.has_action("dash") and Input.is_action_just_pressed("dash") and _dash_cd <= 0.0:
		_dash_left = dash_time
		_dash_cd = dash_cooldown
		_dash_dir = facing
		dashed.emit()
	if _dash_left > 0.0:
		_dash_left -= delta
		velocity = _dash_dir * dash_speed
	else:
		var top: float = speed * (sprint_multiplier if Input.is_action_pressed("sprint") else 1.0)
		if input != Vector2.ZERO:
			velocity = velocity.move_toward(input * top, acceleration * delta)
		else:
			velocity = velocity.move_toward(Vector2.ZERO, friction * delta)
	move_and_slide()


func take_damage(amount: float, source: Node = null) -> void:
	var health := get_node_or_null("Health")
	if health and health.has_method("damage"):
		health.damage(amount, source)


func respawn() -> void:
	global_position = get_meta("ms_checkpoint", _spawn)
	velocity = Vector2.ZERO
	respawned.emit()


func die() -> void:
	died.emit()
	respawn()
''', modes=("2d",), inputs=("move_left", "move_right", "move_up", "move_down", "sprint", "dash"), groups=("player",))

# ───────────────────────────── cameras ─────────────────────────────
add("camera_follow", "Smooth follow camera (2D look-ahead + limits / 3D offset chase) with built-in trauma shake.", '''extends Camera@@D@@
## Follows the first node in group `target_group` (default "player"). Call add_trauma(0..1) for screen shake.

@export var target_group: StringName = &"player"
@export var smoothing: float = 8.0
@export var max_shake: float = @@MAXSHAKE@@
@export var shake_decay: float = 1.6
##3D
@export var follow_offset: Vector3 = Vector3(0, 4.5, 7.0)
@export var look_at_target: bool = true
##END
##2D
@export var look_ahead: float = 60.0
@export var limit_rect: Rect2 = Rect2(0, 0, 0, 0)
##END

var target: Node@@D@@
var trauma: float = 0.0
var _noise := FastNoiseLite.new()
var _t: float = 0.0
##2D
var _ahead: float = 0.0
##END


func _ready() -> void:
	_noise.seed = randi()
	_noise.frequency = 2.0
	_find_target()
##2D
	if limit_rect.size != Vector2.ZERO:
		limit_left = int(limit_rect.position.x)
		limit_top = int(limit_rect.position.y)
		limit_right = int(limit_rect.end.x)
		limit_bottom = int(limit_rect.end.y)
##END


func _find_target() -> void:
	var found := get_tree().get_first_node_in_group(target_group)
	if found is Node@@D@@:
		target = found


func add_trauma(amount: float) -> void:
	trauma = clampf(trauma + amount, 0.0, 1.0)


func _process(delta: float) -> void:
	if not is_instance_valid(target):
		_find_target()
	var k: float = 1.0 - exp(-smoothing * delta)
	if is_instance_valid(target):
##3D
		var goal: Vector3 = target.global_position + follow_offset
		global_position = global_position.lerp(goal, k)
		if look_at_target:
			look_at(target.global_position + Vector3(0, 1.2, 0))
##END
##2D
		var vel: Vector2 = target.velocity if "velocity" in target else Vector2.ZERO
		_ahead = lerpf(_ahead, clampf(vel.x / 200.0, -1.0, 1.0) * look_ahead, k)
		global_position = global_position.lerp(target.global_position + Vector2(_ahead, 0.0), k)
##END
	if trauma > 0.0:
		_t += delta * 60.0
		var s: float = trauma * trauma
##3D
		h_offset = _noise.get_noise_2d(_t, 0.0) * max_shake * s
		v_offset = _noise.get_noise_2d(0.0, _t) * max_shake * s
##END
##2D
		offset = Vector2(_noise.get_noise_2d(_t, 0.0), _noise.get_noise_2d(0.0, _t)) * max_shake * s
		rotation = _noise.get_noise_2d(_t, _t) * 0.03 * s
##END
		trauma = maxf(trauma - shake_decay * delta, 0.0)
''', extra={"MAXSHAKE": ("0.5", "24.0")})

add("camera_shake", "Trauma-based screen shake component: add as a child of any Camera2D/Camera3D and call add_trauma().", '''extends Node
## Add as a child of a Camera2D or Camera3D. add_trauma(0.4) for small hits, 1.0 for explosions.

@export var max_offset: float = 0.35
@export var max_roll: float = 0.04
@export var decay: float = 1.5
@export var noise_speed: float = 60.0

var trauma: float = 0.0
var _cam: Node
var _noise := FastNoiseLite.new()
var _t: float = 0.0


func _ready() -> void:
	_cam = get_parent()
	_noise.seed = randi()
	_noise.frequency = 2.0


func add_trauma(amount: float) -> void:
	trauma = clampf(trauma + amount, 0.0, 1.0)


func _process(delta: float) -> void:
	if _cam == null:
		return
	if trauma <= 0.0:
		_apply(0.0, 0.0, 0.0)
		return
	_t += delta * noise_speed
	var s: float = trauma * trauma
	_apply(_noise.get_noise_2d(_t, 0.0) * s, _noise.get_noise_2d(0.0, _t) * s, _noise.get_noise_2d(_t, _t) * s)
	trauma = maxf(trauma - decay * delta, 0.0)


func _apply(x: float, y: float, r: float) -> void:
	if _cam is Camera3D:
		_cam.h_offset = x * max_offset
		_cam.v_offset = y * max_offset
		_cam.rotation.z = r * max_roll * 3.0
	elif _cam is Camera2D:
		_cam.offset = Vector2(x, y) * max_offset * 60.0
		_cam.rotation = r * max_roll
''')

# ───────────────────────────── health + damage ─────────────────────────────
add("health_component", "Reusable health Node: damage/heal/kill/revive, invulnerability frames, regen, signals.", '''extends Node
## Add as a child named "Health". The parent's take_damage(amount, source) forwards here (see the player/enemy kits).

signal health_changed(current: float, maximum: float)
signal damaged(amount: float, source: Node)
signal healed(amount: float)
signal died

@export var max_health: float = 100.0
@export var invulnerable_time: float = 0.0
@export var regen_per_second: float = 0.0
@export var free_parent_on_death: bool = false

var health: float = 0.0
var dead: bool = false
var _inv: float = 0.0


func _ready() -> void:
	health = max_health


func _process(delta: float) -> void:
	if _inv > 0.0:
		_inv -= delta
	if regen_per_second > 0.0 and not dead and health < max_health:
		heal(regen_per_second * delta)


func damage(amount: float, source: Node = null) -> void:
	if dead or _inv > 0.0 or amount <= 0.0:
		return
	health = maxf(health - amount, 0.0)
	_inv = invulnerable_time
	damaged.emit(amount, source)
	health_changed.emit(health, max_health)
	if health <= 0.0:
		dead = true
		died.emit()
		if free_parent_on_death and get_parent():
			get_parent().queue_free()


func heal(amount: float) -> void:
	if dead or amount <= 0.0:
		return
	var before := health
	health = minf(health + amount, max_health)
	if health > before:
		healed.emit(health - before)
		health_changed.emit(health, max_health)


func kill() -> void:
	damage(health + 1.0)


func revive(fraction: float = 1.0) -> void:
	dead = false
	health = clampf(max_health * fraction, 1.0, max_health)
	health_changed.emit(health, max_health)


func ratio() -> float:
	return health / maxf(max_health, 0.001)
''')

add("hitbox", "Damage-dealing Area (melee swing, explosion, trap): hits each target once per activation, optional knockback.", '''extends Area@@D@@
## Enable with activate(duration) (melee) or leave monitoring on (traps/explosions). Hits anything with take_damage(amount, source).

signal hit(target: Node)

@export var damage: float = 10.0
@export var knockback: float = 6.0
@export var target_group: StringName = &""
@export var one_shot: bool = false
@export var active_on_start: bool = true

var _hit: Array[Node] = []


func _ready() -> void:
	monitoring = active_on_start
	body_entered.connect(_on_body)
	area_entered.connect(_on_area)


func activate(duration: float = 0.15) -> void:
	_hit.clear()
	monitoring = true
	await get_tree().create_timer(duration).timeout
	monitoring = false


func _on_area(area: Area@@D@@) -> void:
	if area.has_method("receive_hit"):
		area.receive_hit(damage, global_position, owner if owner else self)
		hit.emit(area)


func _on_body(body: Node@@D@@) -> void:
	if body == owner or body in _hit:
		return
	if target_group != &"" and not body.is_in_group(target_group):
		return
	_hit.append(body)
	if body.has_method("take_damage"):
		body.take_damage(damage, owner if owner else self)
	if knockback > 0.0 and "velocity" in body:
		var away = (body.global_position - global_position)
##3D
		away.y = 0.0
##END
		body.velocity += away.normalized() * knockback
	hit.emit(body)
	if one_shot:
		queue_free()
''')

add("hurtbox", "Hurtbox Area that receives hits and forwards damage to its owner's Health/take_damage.", '''extends Area@@D@@
## Put on a child Area of a character. Hitboxes and projectiles call receive_hit(); damage goes to a sibling "Health" or the parent's take_damage().

signal hit_received(amount: float, from_position: @@V@@)

@export var damage_multiplier: float = 1.0
@export var health_path: NodePath = ^"../Health"


func receive_hit(amount: float, from_position: @@V@@, source: Node = null) -> void:
	hit_received.emit(amount, from_position)
	var final_amount: float = amount * damage_multiplier
	var health := get_node_or_null(health_path)
	if health and health.has_method("damage"):
		health.damage(final_amount, source)
	elif get_parent() and get_parent().has_method("take_damage"):
		get_parent().take_damage(final_amount, source)
''')


# ───────────────────────────── world objects ─────────────────────────────
add("collectible", "Pickup Area: bobs/spins, collected by the player (score, heal, key), tween-out + optional sound.", '''extends Area@@D@@
## Coin / health pickup / key. Collected when a body in group `collector_group` enters.

signal collected(value: int, kind: StringName)

@export var kind: StringName = &"coin"            ## coin, health, key, power
@export var value: int = 1
@export var collector_group: StringName = &"player"
@export var spin_speed: float = 2.5
@export var bob_height: float = @@BOB@@
@export var bob_speed: float = 3.0
@export var pickup_sound: AudioStream
@export var key_id: String = ""

var _base: @@V@@
var _t: float = 0.0
var _taken: bool = false


func _ready() -> void:
	add_to_group("coin" if kind == &"coin" else "pickup")
	_base = position
	_t = randf() * TAU
	body_entered.connect(_on_body)


func _process(delta: float) -> void:
	_t += delta
##3D
	rotate_y(spin_speed * delta)
##END
	position.y = _base.y + sin(_t * bob_speed) * bob_height


func _on_body(body: Node@@D@@) -> void:
	if _taken or not body.is_in_group(collector_group):
		return
	_taken = true
	match kind:
		&"health":
			var h := body.get_node_or_null("Health")
			if h and h.has_method("heal"):
				h.heal(value)
		&"key":
			var keys: Array = body.get_meta("keys", [])
			keys.append(key_id if key_id != "" else name)
			body.set_meta("keys", keys)
		_:
			var gm := get_node_or_null("/root/GameManager")
			if gm and gm.has_method("add_score"):
				gm.add_score(value)
	collected.emit(value, kind)
	if pickup_sound:
		var snd := AudioStreamPlayer@@D@@.new()
		snd.stream = pickup_sound
		get_tree().current_scene.add_child(snd)
		snd.global_position = global_position
		snd.finished.connect(snd.queue_free)
		snd.play()
	set_deferred("monitoring", false)
	var tw := create_tween().set_parallel(true)
	tw.tween_property(self, "scale", @@V@@.ONE * 0.01, 0.18).set_ease(Tween.EASE_IN)
	tw.chain().tween_callback(queue_free)
''', extra={"BOB": ("0.15", "5.0")}, groups=("coin",))

add("checkpoint", "Checkpoint Area: remembers the player's respawn point (meta ms_checkpoint) and lights up once.", '''extends Area@@D@@
## When the player enters, its respawn point is stored on the player (meta "ms_checkpoint") and in GameManager.checkpoint if that autoload exists.

signal activated(by: Node)

@export var player_group: StringName = &"player"
@export var one_time: bool = true
@export var active_color: Color = Color(0.3, 1.0, 0.5, 0.7)

var active: bool = false


func _ready() -> void:
	add_to_group("checkpoint")
	body_entered.connect(_on_body)


func _on_body(body: Node@@D@@) -> void:
	if not body.is_in_group(player_group) or (active and one_time):
		return
	active = true
	body.set_meta("ms_checkpoint", global_position + @@UP@@)
	var gm := get_node_or_null("/root/GameManager")
	if gm and "checkpoint" in gm:
		gm.checkpoint = global_position + @@UP@@
	for child in get_children():
		if child is @@MESH@@:
			child.modulate = active_color
	activated.emit(body)
''', extra={"UP": ("Vector3(0, 1.0, 0)", "Vector2(0, -24)"), "MESH": ("GeometryInstance3D", "CanvasItem")}, groups=("checkpoint",))

add("kill_zone", "Hazard Area (lava, pit, spikes): respawns the player, optionally damages instead, frees other bodies.", '''extends Area@@D@@
## Fall pits, lava, spikes. Player: respawn() (or take_damage if `damage` > 0). Others in `kill_group` are freed.

signal player_hit(body: Node)

@export var damage: float = 0.0                    ## 0 = instant respawn
@export var player_group: StringName = &"player"
@export var kill_group: StringName = &"enemy"
@export var repeat_interval: float = 0.5

var _cooldown: Dictionary = {}


func _ready() -> void:
	add_to_group("killzone")
	body_entered.connect(_on_body)


func _physics_process(delta: float) -> void:
	if damage <= 0.0:
		return
	for body in get_overlapping_bodies():
		if body.is_in_group(player_group) and body.has_method("take_damage"):
			var left: float = _cooldown.get(body, 0.0) - delta
			if left <= 0.0:
				body.take_damage(damage, self)
				left = repeat_interval
			_cooldown[body] = left


func _on_body(body: Node@@D@@) -> void:
	if body.is_in_group(player_group):
		player_hit.emit(body)
		if damage > 0.0 and body.has_method("take_damage"):
			body.take_damage(damage, self)
		elif body.has_method("respawn"):
			body.respawn()
		else:
			get_tree().call_deferred("reload_current_scene")
	elif body.is_in_group(kill_group):
		body.queue_free()
''', groups=("killzone",))

add("moving_platform", "Platform that glides between its start and start+travel using a looping tween (carries the player).", '''extends AnimatableBody@@D@@
## Moves from its start position by `travel` and back. sync_to_physics keeps riders attached.

@export var travel: @@V@@ = @@TRAVEL@@
@export var duration: float = 2.5
@export var pause_time: float = 0.4
@export var autostart: bool = true
@export var trans: Tween.TransitionType = Tween.TRANS_SINE

var _tween: Tween


func _ready() -> void:
	sync_to_physics = true
	if autostart:
		start()


func start() -> void:
	if _tween:
		_tween.kill()
	var from := position
	_tween = create_tween().set_loops()
	_tween.set_trans(trans).set_ease(Tween.EASE_IN_OUT)
	_tween.tween_property(self, "position", from + travel, duration).set_delay(pause_time)
	_tween.tween_property(self, "position", from, duration).set_delay(pause_time)


func stop() -> void:
	if _tween:
		_tween.kill()
''', extra={"TRAVEL": ("Vector3(6, 0, 0)", "Vector2(192, 0)")})

add("projectile", "Bullet / arrow / fireball Area: moves forward, damages what it hits, expires, optional pierce.", '''extends Area@@D@@
## Spawned by the shooter kit. Moves along `direction` (set by launch()). Hits bodies with take_damage() and areas with receive_hit().

signal hit(target: Node)

@export var speed: float = @@SPEED@@
@export var damage: float = 10.0
@export var lifetime: float = 3.0
@export var pierce: int = 0
@export var gravity_scale: float = 0.0
@export var ignore_group: StringName = &"player"
@export var impact_scene: PackedScene

var direction: @@V@@ = @@FWD@@
var shooter: Node
var _velocity: @@V@@
var _life: float = 0.0
var _hits: int = 0


func _ready() -> void:
	body_entered.connect(_on_body)
	area_entered.connect(_on_area)
	_velocity = direction * speed


func launch(dir: @@V@@, from: Node = null) -> void:
	direction = dir.normalized()
	shooter = from
	_velocity = direction * speed
##3D
	if direction.length() > 0.0 and absf(direction.dot(Vector3.UP)) < 0.99:
		look_at(global_position + direction, Vector3.UP)
##END
##2D
	rotation = direction.angle()
##END


func _physics_process(delta: float) -> void:
	_velocity += @@GRAV@@ * gravity_scale * delta
	global_position += _velocity * delta
	_life += delta
	if _life >= lifetime:
		queue_free()


func _on_body(body: Node@@D@@) -> void:
	if body == shooter or (ignore_group != &"" and body.is_in_group(ignore_group)):
		return
	if body.has_method("take_damage"):
		body.take_damage(damage, shooter if shooter else self)
	_impact(body)


func _on_area(area: Area@@D@@) -> void:
	if area.has_method("receive_hit") and area.get_parent() != shooter:
		area.receive_hit(damage, global_position, shooter if shooter else self)
		_impact(area)


func _impact(target: Node) -> void:
	hit.emit(target)
	if impact_scene:
		var fx := impact_scene.instantiate()
		get_tree().current_scene.add_child(fx)
		fx.global_position = global_position
	_hits += 1
	if _hits > pierce:
		queue_free()
''', extra={"SPEED": ("28.0", "520.0"), "FWD": ("Vector3(0, 0, -1)", "Vector2.RIGHT"), "GRAV": ("Vector3(0, -9.8, 0)", "Vector2(0, 980)")})

add("shooter", "Weapon component: fires `projectile_scene` on an action or automatically, with cooldown, spread and ammo.", '''extends Node@@D@@
## Child of a character (put it at the muzzle). Fires with the `fire_action` input or via fire().
## 3D: shoots along -Z of this node. 2D: toward the mouse when aim_at_mouse, else along +X of this node.

signal fired(projectile: Node)
signal ammo_changed(current: int, maximum: int)

@export var projectile_scene: PackedScene
@export var fire_action: StringName = &"attack"
@export var cooldown: float = 0.25
@export var auto_fire: bool = false
@export var burst: int = 1
@export_range(0.0, 45.0) var spread_degrees: float = 1.5
@export var max_ammo: int = 0                      ## 0 = unlimited
@export var aim_at_mouse: bool = true

var ammo: int = 0
var _cd: float = 0.0


func _ready() -> void:
	ammo = max_ammo


func _process(delta: float) -> void:
	_cd -= delta
	if InputMap.has_action(fire_action) and (Input.is_action_pressed(fire_action) if auto_fire else Input.is_action_just_pressed(fire_action)):
		fire()


func reload() -> void:
	ammo = max_ammo
	ammo_changed.emit(ammo, max_ammo)


func fire() -> void:
	if projectile_scene == null or _cd > 0.0 or (max_ammo > 0 and ammo <= 0):
		return
	_cd = cooldown
	for i in burst:
		var p := projectile_scene.instantiate()
		get_tree().current_scene.add_child(p)
		p.global_position = global_position
		var dir = _aim()
		var spread := deg_to_rad(spread_degrees)
##3D
		dir = (dir + global_transform.basis.x * randf_range(-spread, spread) + global_transform.basis.y * randf_range(-spread, spread)).normalized()
##END
##2D
		dir = dir.rotated(randf_range(-spread, spread))
##END
		if p.has_method("launch"):
			p.launch(dir, get_parent())
		fired.emit(p)
	if max_ammo > 0:
		ammo -= 1
		ammo_changed.emit(ammo, max_ammo)


func _aim():
##3D
	return -global_transform.basis.z
##END
##2D
	if aim_at_mouse:
		return (get_global_mouse_position() - global_position).normalized()
	return Vector2.RIGHT.rotated(global_rotation)
##END
''', inputs=("attack",))


add("enemy_ai", "Enemy CharacterBody with patrol / chase / attack states, health, contact damage and (3D) NavigationAgent3D pathing.", '''extends CharacterBody@@D@@
## States: PATROL -> CHASE (player within detect_range) -> ATTACK (within attack_range) -> back to PATROL when the player is lost.
## Implements take_damage(amount, source) so projectiles and hitboxes can hurt it. Add a child NavigationAgent@@D@@ for navmesh pathing.

signal died
signal state_changed(new_state: StringName)

enum State { PATROL, CHASE, ATTACK, DEAD }

@export var max_health: float = 30.0
@export var patrol_speed: float = @@PSPEED@@
@export var chase_speed: float = @@CSPEED@@
@export var detect_range: float = @@DETECT@@
@export var lose_range: float = @@LOSE@@
@export var attack_range: float = @@ARANGE@@
@export var attack_damage: float = 8.0
@export var attack_cooldown: float = 1.0
@export var patrol_radius: float = @@PRADIUS@@
@export var patrol_wait: float = 1.2
@export var target_group: StringName = &"player"
@export var drop_scene: PackedScene
##2D
@export var platformer: bool = true
##END

var health: float = 0.0
var state: State = State.PATROL
var _home: @@V@@
var _goal: @@V@@
var _wait: float = 0.0
var _cd: float = 0.0
var _target: Node@@D@@
var _agent: NavigationAgent@@D@@
var gravity: float = ProjectSettings.get_setting("physics/@@d@@/default_gravity")
##2D
var _dir: float = 1.0
##END


func _ready() -> void:
	add_to_group("enemy")
	health = max_health
	_home = global_position
	_goal = _home
	_agent = get_node_or_null("NavigationAgent@@D@@") as NavigationAgent@@D@@
	_target = get_tree().get_first_node_in_group(target_group) as Node@@D@@


func take_damage(amount: float, _source: Node = null) -> void:
	if state == State.DEAD:
		return
	health -= amount
	if health <= 0.0:
		_die()


func _die() -> void:
	state = State.DEAD
	died.emit()
	state_changed.emit(&"dead")
	if drop_scene:
		var drop := drop_scene.instantiate()
		get_parent().add_child(drop)
		drop.global_position = global_position
	queue_free()


func _set_state(s: State) -> void:
	if s != state and state != State.DEAD:
		state = s
		state_changed.emit(StringName(State.keys()[s].to_lower()))


func _physics_process(delta: float) -> void:
	if state == State.DEAD:
		return
	if not is_instance_valid(_target):
		_target = get_tree().get_first_node_in_group(target_group) as Node@@D@@
	_cd -= delta
	var dist: float = INF
	if is_instance_valid(_target):
		dist = global_position.distance_to(_target.global_position)
	match state:
		State.PATROL:
			if dist <= detect_range:
				_set_state(State.CHASE)
			else:
				_patrol(delta)
		State.CHASE:
			if dist > lose_range:
				_set_state(State.PATROL)
			elif dist <= attack_range:
				_set_state(State.ATTACK)
			else:
				_move_toward(_target.global_position, chase_speed, delta)
		State.ATTACK:
			if dist > attack_range * 1.25:
				_set_state(State.CHASE)
			else:
				_stop(delta)
				if _cd <= 0.0 and _target.has_method("take_damage"):
					_cd = attack_cooldown
					_target.take_damage(attack_damage, self)
##3D
	if not is_on_floor():
		velocity.y -= gravity * delta
##END
##2D
	if platformer and not is_on_floor():
		velocity.y += gravity * delta
##END
	move_and_slide()


func _stop(delta: float) -> void:
	velocity.x = move_toward(velocity.x, 0.0, 300.0 * delta)
##3D
	velocity.z = move_toward(velocity.z, 0.0, 300.0 * delta)
##END
##2D
	if not platformer:
		velocity.y = move_toward(velocity.y, 0.0, 300.0 * delta)
##END


func _patrol(delta: float) -> void:
##3D
	if _wait > 0.0:
		_wait -= delta
		_stop(delta)
		return
	if global_position.distance_to(_goal) < 0.8 or (_goal == _home and patrol_radius > 0.0):
		var a := randf() * TAU
		_goal = _home + Vector3(cos(a), 0.0, sin(a)) * randf_range(patrol_radius * 0.3, patrol_radius)
		_wait = patrol_wait
		return
	_move_toward(_goal, patrol_speed, delta)
##END
##2D
	if platformer:
		velocity.x = _dir * patrol_speed
		var ahead := global_transform.translated(Vector2(_dir * 14.0, 0.0))
		var ground_ahead := test_move(ahead, Vector2(0.0, 24.0))
		if is_on_wall() or (is_on_floor() and not ground_ahead):
			_dir = -_dir
			velocity.x = 0.0
	else:
		if _wait > 0.0:
			_wait -= delta
			_stop(delta)
			return
		if global_position.distance_to(_goal) < 6.0 or _goal == _home:
			_goal = _home + Vector2.from_angle(randf() * TAU) * randf_range(patrol_radius * 0.3, patrol_radius)
			_wait = patrol_wait
			return
		_move_toward(_goal, patrol_speed, delta)
##END


func _move_toward(point: @@V@@, speed: float, delta: float) -> void:
	var dest := point
	if _agent:
		_agent.target_position = point
		if not _agent.is_navigation_finished():
			dest = _agent.get_next_path_position()
	var dir := (dest - global_position)
##3D
	dir.y = 0.0
	dir = dir.normalized()
	velocity.x = move_toward(velocity.x, dir.x * speed, speed * 8.0 * delta)
	velocity.z = move_toward(velocity.z, dir.z * speed, speed * 8.0 * delta)
	if dir.length() > 0.1:
		rotation.y = lerp_angle(rotation.y, atan2(-dir.x, -dir.z), 1.0 - exp(-8.0 * delta))
##END
##2D
	if platformer:
		_dir = signf(dir.x) if absf(dir.x) > 1.0 else _dir
		velocity.x = move_toward(velocity.x, _dir * speed, speed * 8.0 * delta)
	else:
		velocity = velocity.move_toward(dir.normalized() * speed, speed * 8.0 * delta)
##END
''', extra={"PSPEED": ("2.0", "60.0"), "CSPEED": ("4.0", "110.0"), "DETECT": ("12.0", "260.0"), "LOSE": ("18.0", "380.0"), "ARANGE": ("1.8", "34.0"), "PRADIUS": ("6.0", "140.0")}, groups=("enemy",))

add("spawner", "Timed spawner: instances a scene at itself, in a radius or at marker groups, with max-alive and total limits.", '''extends Node@@D@@
## Spawns `scene` every `interval` seconds while fewer than `max_alive` are alive. Set `marker_group` (e.g. "enemy_spawn") to spawn at those markers instead.

signal spawned(node: Node)
signal limit_reached

@export var scene: PackedScene
@export var interval: float = 3.0
@export var max_alive: int = 5
@export var total_limit: int = 0                    ## 0 = unlimited
@export var spawn_radius: float = @@RADIUS@@
@export var marker_group: StringName = &""
@export var autostart: bool = true
@export var initial_burst: int = 0

var running: bool = false
var total_spawned: int = 0
var _alive: Array[Node] = []
var _timer: float = 0.0


func _ready() -> void:
	running = autostart
	for i in initial_burst:
		spawn()


func start() -> void:
	running = true


func stop() -> void:
	running = false


func alive_count() -> int:
	_alive = _alive.filter(func(n): return is_instance_valid(n))
	return _alive.size()


func spawn() -> Node:
	if scene == null or alive_count() >= max_alive:
		return null
	if total_limit > 0 and total_spawned >= total_limit:
		running = false
		limit_reached.emit()
		return null
	var node := scene.instantiate()
	get_parent().add_child(node)
	var pos: @@V@@ = global_position
	if marker_group != &"":
		var markers := get_tree().get_nodes_in_group(marker_group)
		if not markers.is_empty():
			pos = markers.pick_random().global_position
	elif spawn_radius > 0.0:
##3D
		var a := randf() * TAU
		pos += Vector3(cos(a), 0.0, sin(a)) * randf() * spawn_radius
##END
##2D
		pos += Vector2.from_angle(randf() * TAU) * randf() * spawn_radius
##END
	node.global_position = pos
	_alive.append(node)
	total_spawned += 1
	spawned.emit(node)
	return node


func _process(delta: float) -> void:
	if not running:
		return
	_timer += delta
	if _timer >= interval:
		_timer = 0.0
		spawn()
''', extra={"RADIUS": ("4.0", "96.0")})

add("level_rules", "Makes a blockout level playable: spawns the player, wires coins/killzones/checkpoints/goal groups, counts coins, loads the next level.", '''extends Node
## Drop this node into a scene built with ms_*_level_blockout. It looks for the blockout groups
## (player_spawn, coin, killzone, checkpoint, goal, enemy_spawn) and connects them. Coins use GameManager.add_score if present.

signal coin_collected(total: int, needed: int)
signal goal_reached
signal level_complete
signal player_spawned(player: Node)

@export var player_scene: PackedScene
@export var enemy_scene: PackedScene
@export var next_scene: String = ""
@export var coins_required: int = 0                 ## 0 = goal always open

var coins: int = 0
var player: Node
var finished: bool = false


func _ready() -> void:
	call_deferred("_setup")


func _setup() -> void:
	player = get_tree().get_first_node_in_group("player")
	var spawns := get_tree().get_nodes_in_group("player_spawn")
	if player == null and player_scene and not spawns.is_empty():
		player = player_scene.instantiate()
		get_parent().add_child(player)
		player.global_position = spawns[0].global_position
		player_spawned.emit(player)
	if enemy_scene:
		for marker in get_tree().get_nodes_in_group("enemy_spawn"):
			var e := enemy_scene.instantiate()
			get_parent().add_child(e)
			e.global_position = marker.global_position
	for a in get_tree().get_nodes_in_group("coin"):
		if a is Area@@D@@ and a.get_script() == null:
			a.body_entered.connect(_on_coin.bind(a))
	for a in get_tree().get_nodes_in_group("killzone"):
		if a is Area@@D@@ and a.get_script() == null:
			a.body_entered.connect(_on_killzone)
	for a in get_tree().get_nodes_in_group("checkpoint"):
		if a is Area@@D@@ and a.get_script() == null:
			a.body_entered.connect(_on_checkpoint.bind(a))
	for a in get_tree().get_nodes_in_group("goal"):
		if a is Area@@D@@:
			a.body_entered.connect(_on_goal)


func _on_coin(body: Node, coin: Node) -> void:
	if not body.is_in_group("player") or not is_instance_valid(coin):
		return
	coin.queue_free()
	coins += 1
	var gm := get_node_or_null("/root/GameManager")
	if gm and gm.has_method("add_score"):
		gm.add_score(1)
	coin_collected.emit(coins, coins_required)


func _on_killzone(body: Node) -> void:
	if body.is_in_group("player") and body.has_method("respawn"):
		body.respawn()


func _on_checkpoint(body: Node, point: Node) -> void:
	if body.is_in_group("player"):
		body.set_meta("ms_checkpoint", point.global_position + @@UP@@)


func _on_goal(body: Node) -> void:
	if finished or not body.is_in_group("player"):
		return
	goal_reached.emit()
	if coins < coins_required:
		return
	finished = true
	level_complete.emit()
	if next_scene != "" and ResourceLoader.exists(next_scene):
		get_tree().call_deferred("change_scene_to_file", next_scene)
''', extra={"UP": ("Vector3(0, 1.0, 0)", "Vector2(0, -24)")}, groups=("player_spawn", "coin", "killzone", "checkpoint", "goal", "enemy_spawn"))

add("interactable", "Interaction Area with prompt: shows a label while the player is near and emits `interacted` on the interact action.", '''extends Area@@D@@
## Add a child Label (Label3D in 3D) named "Prompt" to show/hide the text automatically. Connect `interacted` to anything (open a door, talk, pick up).

signal interacted(by: Node)
signal focus_changed(focused: bool)

@export var prompt_text: String = "Press E to interact"
@export var action: StringName = &"interact"
@export var player_group: StringName = &"player"
@export var one_shot: bool = false

var _inside: Node
var _prompt: Node


func _ready() -> void:
	body_entered.connect(_on_enter)
	body_exited.connect(_on_exit)
	_prompt = get_node_or_null("Prompt")
	if _prompt:
		_prompt.text = prompt_text
		_prompt.visible = false


func _on_enter(body: Node@@D@@) -> void:
	if body.is_in_group(player_group):
		_inside = body
		if _prompt:
			_prompt.visible = true
		focus_changed.emit(true)


func _on_exit(body: Node@@D@@) -> void:
	if body == _inside:
		_inside = null
		if _prompt:
			_prompt.visible = false
		focus_changed.emit(false)


func _unhandled_input(event: InputEvent) -> void:
	if _inside and event.is_action_pressed(action):
		interacted.emit(_inside)
		get_viewport().set_input_as_handled()
		if one_shot:
			set_deferred("monitoring", false)
			if _prompt:
				_prompt.visible = false
			_inside = null
''', inputs=("interact",))

add("door", "Sliding door (AnimatableBody) that opens by interaction or proximity; supports locked doors with a key id.", '''extends AnimatableBody@@D@@
## Child Area named "InteractArea" detects the player. Locked doors need the player's meta "keys" to contain `key_id` (see collectible kind=key).

signal opened
signal closed
signal locked_attempt

@export var open_offset: @@V@@ = @@OFFSET@@
@export var open_time: float = 0.6
@export var locked: bool = false
@export var key_id: String = ""
@export var auto_open: bool = false
@export var auto_close_after: float = 0.0
@export var player_group: StringName = &"player"
@export var interact_action: StringName = &"interact"

var is_open: bool = false
var _closed_pos: @@V@@
var _near: Node
var _tween: Tween


func _ready() -> void:
	sync_to_physics = true
	_closed_pos = position
	var area := get_node_or_null("InteractArea") as Area@@D@@
	if area:
		area.body_entered.connect(_on_enter)
		area.body_exited.connect(_on_exit)


func _on_enter(body: Node) -> void:
	if body.is_in_group(player_group):
		_near = body
		if auto_open:
			open(body)


func _on_exit(body: Node) -> void:
	if body == _near:
		_near = null
		if auto_open and is_open:
			close()


func _unhandled_input(event: InputEvent) -> void:
	if _near and not auto_open and InputMap.has_action(interact_action) and event.is_action_pressed(interact_action):
		toggle(_near)


func has_key(by: Node) -> bool:
	return key_id == "" or (by != null and key_id in by.get_meta("keys", []))


func toggle(by: Node = null) -> void:
	if is_open:
		close()
	else:
		open(by)


func open(by: Node = null) -> void:
	if is_open:
		return
	if locked and not has_key(by):
		locked_attempt.emit()
		return
	locked = false
	is_open = true
	_slide(_closed_pos + open_offset)
	opened.emit()
	if auto_close_after > 0.0:
		get_tree().create_timer(auto_close_after).timeout.connect(close)


func close() -> void:
	if not is_open:
		return
	is_open = false
	_slide(_closed_pos)
	closed.emit()


func _slide(to: @@V@@) -> void:
	if _tween:
		_tween.kill()
	_tween = create_tween().set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	_tween.tween_property(self, "position", to, open_time)
''', extra={"OFFSET": ("Vector3(0, 3.2, 0)", "Vector2(0, -96)")}, inputs=("interact",))

add("state_machine", "Node-based finite state machine: child nodes are states (enter/exit/update/physics_update), plus a State base script.", '''extends Node
## Put State nodes (script extends state.gd) as children. The first child (or `initial_state`) starts active.
## A state requests a change with: transition_requested.emit(&"run", {}) - or call change_state(&"run") from outside.

signal state_changed(from_state: StringName, to_state: StringName)

@export var initial_state: NodePath

var current: Node
var states: Dictionary = {}


func _ready() -> void:
	for child in get_children():
		states[StringName(child.name.to_lower())] = child
		if child.has_signal("transition_requested"):
			child.transition_requested.connect(change_state)
	var start: Node = get_node_or_null(initial_state) if not initial_state.is_empty() else null
	if start == null and get_child_count() > 0:
		start = get_child(0)
	if start:
		current = start
		current.enter({})
		state_changed.emit(&"", StringName(current.name.to_lower()))


func change_state(state_name: StringName, msg: Dictionary = {}) -> void:
	var next: Node = states.get(StringName(String(state_name).to_lower()))
	if next == null or next == current:
		return
	var previous := StringName(current.name.to_lower()) if current else &""
	if current:
		current.exit()
	current = next
	current.enter(msg)
	state_changed.emit(previous, StringName(current.name.to_lower()))


func _unhandled_input(event: InputEvent) -> void:
	if current and current.has_method("handle_input"):
		current.handle_input(event)


func _process(delta: float) -> void:
	if current and current.has_method("update"):
		current.update(delta)


func _physics_process(delta: float) -> void:
	if current and current.has_method("physics_update"):
		current.physics_update(delta)
''', files={"state.gd": '''extends Node
## Base class for states used by state_machine.gd. Override what you need.

signal transition_requested(state_name: StringName, msg: Dictionary)


func enter(_msg: Dictionary = {}) -> void:
	pass


func exit() -> void:
	pass


func update(_delta: float) -> void:
	pass


func physics_update(_delta: float) -> void:
	pass


func handle_input(_event: InputEvent) -> void:
	pass
'''})

add("inventory", "Inventory component: stackable items by id with capacity, signals and save/load (works with the saveable group).", '''extends Node
## Add as a child named "Inventory". Item ids are strings ("key_red", "potion"). Group `saveable` + save_data()/load_data() integrate with the save_system kit.

signal changed(item_id: StringName, count: int)
signal full(item_id: StringName)

@export var max_slots: int = 24
@export var stack_limit: int = 99

var items: Dictionary = {}


func _ready() -> void:
	add_to_group("saveable")


func count(item_id: StringName) -> int:
	return int(items.get(String(item_id), 0))


func has_item(item_id: StringName, amount: int = 1) -> bool:
	return count(item_id) >= amount


## Returns how many items did NOT fit.
func add_item(item_id: StringName, amount: int = 1) -> int:
	var key := String(item_id)
	if not items.has(key) and items.size() >= max_slots:
		full.emit(item_id)
		return amount
	var have: int = int(items.get(key, 0))
	var added: int = mini(stack_limit - have, amount)
	if added <= 0:
		full.emit(item_id)
		return amount
	items[key] = have + added
	changed.emit(item_id, items[key])
	return amount - added


func remove_item(item_id: StringName, amount: int = 1) -> bool:
	var key := String(item_id)
	if count(item_id) < amount:
		return false
	items[key] = int(items[key]) - amount
	if items[key] <= 0:
		items.erase(key)
		changed.emit(item_id, 0)
	else:
		changed.emit(item_id, items[key])
	return true


func save_data() -> Dictionary:
	return {"items": items.duplicate()}


func load_data(data: Dictionary) -> void:
	items = data.get("items", {}).duplicate()
	for key in items:
		changed.emit(StringName(key), int(items[key]))
''', groups=("saveable",))

add("day_night_cycle", "Day/night cycle: rotates the sun (3D DirectionalLight3D) or tints the scene (2D CanvasModulate) over a configurable day length.", '''extends @@NODE@@
## Attach to a @@NODE@@. time_of_day is 0-24; 6 = sunrise, 18 = sunset.

signal hour_changed(hour: int)
signal day_started
signal night_started

@export var day_length_seconds: float = 180.0
@export_range(0.0, 24.0) var time_of_day: float = 9.0
@export var running: bool = true
@export var day_color: Color = Color(1.0, 0.97, 0.9)
@export var dusk_color: Color = Color(1.0, 0.55, 0.3)
@export var night_color: Color = Color(0.12, 0.16, 0.34)
@export var max_energy: float = 1.2

var _last_hour: int = -1
var _was_day: bool = true


func _ready() -> void:
	_apply()


func _process(delta: float) -> void:
	if running:
		time_of_day = fposmod(time_of_day + delta * 24.0 / maxf(day_length_seconds, 1.0), 24.0)
	_apply()


func _apply() -> void:
	var t: float = (time_of_day - 6.0) / 12.0
	var daylight: float = clampf(sin(t * PI), 0.0, 1.0) if t >= 0.0 and t <= 1.0 else 0.0
	var dusk: float = clampf(1.0 - absf(daylight - 0.25) * 4.0, 0.0, 1.0) if daylight < 0.5 else 0.0
	var col: Color = night_color.lerp(day_color, clampf(daylight * 2.0, 0.0, 1.0)).lerp(dusk_color, dusk * 0.7)
##3D
	rotation_degrees.x = -(t * 180.0)
	light_color = col
	light_energy = max_energy * daylight + 0.03
##END
##2D
	color = col
##END
	var hour := int(time_of_day)
	if hour != _last_hour:
		_last_hour = hour
		hour_changed.emit(hour)
	var is_day: bool = daylight > 0.02
	if is_day != _was_day:
		_was_day = is_day
		if is_day:
			day_started.emit()
		else:
			night_started.emit()
''', extra={"NODE": ("DirectionalLight3D", "CanvasModulate")})

add("floating_text", "Floating damage/score number: rises, fades and frees itself. Call setup(text, color).", '''extends @@NODE@@
## Instance, add to the scene, set global_position and call setup("12", Color.RED).

@export var rise: float = @@RISE@@
@export var duration: float = 0.8


func setup(value: String, tint: Color = Color.WHITE) -> void:
	text = value
	modulate = tint
##3D
	billboard = BaseMaterial3D.BILLBOARD_ENABLED
	no_depth_test = true
	fixed_size = true
	pixel_size = 0.0015
##END
	var tw := create_tween().set_parallel(true)
	tw.tween_property(self, "position:y", position.y + rise, duration).set_ease(Tween.EASE_OUT)
	tw.tween_property(self, "modulate:a", 0.0, duration).set_delay(duration * 0.4)
	tw.chain().tween_callback(queue_free)
''', extra={"NODE": ("Label3D", "Label"), "RISE": ("1.2", "40.0")})

# ───────────────────────────── autoloads ─────────────────────────────
add("game_manager", "Autoload GameManager: score, lives, high score (persisted), checkpoint, level flow (change/restart/complete/game over).", '''extends Node
## Autoload "GameManager". Other kits call GameManager.add_score() and read GameManager.checkpoint when they exist.

signal score_changed(score: int)
signal lives_changed(lives: int)
signal high_score_changed(high_score: int)
signal level_completed(level_path: String)
signal game_over

const SAVE_PATH := "user://ms_progress.cfg"

var score: int = 0
var lives: int = 3
var start_lives: int = 3
var high_score: int = 0
var checkpoint = null
var current_level: String = ""
var is_game_over: bool = false


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	var cfg := ConfigFile.new()
	if cfg.load(SAVE_PATH) == OK:
		high_score = int(cfg.get_value("progress", "high_score", 0))
	var scene := get_tree().current_scene
	if scene:
		current_level = scene.scene_file_path


func add_score(points: int = 1) -> void:
	score += points
	score_changed.emit(score)
	if score > high_score:
		high_score = score
		high_score_changed.emit(high_score)
		_save()


func lose_life() -> void:
	lives = maxi(lives - 1, 0)
	lives_changed.emit(lives)
	if lives == 0:
		end_game()


func end_game() -> void:
	is_game_over = true
	game_over.emit()


func reset() -> void:
	score = 0
	lives = start_lives
	checkpoint = null
	is_game_over = false
	score_changed.emit(score)
	lives_changed.emit(lives)


func change_level(path: String) -> void:
	if not ResourceLoader.exists(path):
		push_warning("GameManager.change_level: missing scene " + path)
		return
	current_level = path
	checkpoint = null
	get_tree().paused = false
	get_tree().change_scene_to_file(path)


func restart_level() -> void:
	get_tree().paused = false
	get_tree().reload_current_scene()


func complete_level(next_path: String = "") -> void:
	level_completed.emit(current_level)
	if next_path != "":
		change_level(next_path)


func _save() -> void:
	var cfg := ConfigFile.new()
	cfg.set_value("progress", "high_score", high_score)
	cfg.save(SAVE_PATH)
''', autoload=True)

add("save_system", "Autoload SaveSystem: JSON save slots in user://, saveable-group nodes, plus a settings store (ConfigFile).", '''extends Node
## Autoload "SaveSystem". Nodes in group "saveable" implement save_data() -> Dictionary and load_data(Dictionary);
## their data is stored by node path. save_game(slot, extra) / load_game(slot) / has_save(slot) / delete_save(slot).

signal saved(slot: int)
signal loaded(slot: int)

const SAVE_DIR := "user://saves"
const SETTINGS_PATH := "user://settings.cfg"
const VERSION := 1

var extra_data: Dictionary = {}
var _settings := ConfigFile.new()


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	DirAccess.make_dir_recursive_absolute(SAVE_DIR)
	_settings.load(SETTINGS_PATH)


func _slot_path(slot: int) -> String:
	return "%s/slot_%d.json" % [SAVE_DIR, slot]


func has_save(slot: int = 1) -> bool:
	return FileAccess.file_exists(_slot_path(slot))


func save_game(slot: int = 1, extra: Dictionary = {}) -> bool:
	var nodes := {}
	for n in get_tree().get_nodes_in_group("saveable"):
		if n.has_method("save_data"):
			nodes[str(n.get_path())] = n.save_data()
	var scene_path := ""
	if get_tree().current_scene:
		scene_path = get_tree().current_scene.scene_file_path
	var payload := {"version": VERSION, "time": Time.get_unix_time_from_system(), "scene": scene_path, "extra": extra, "nodes": nodes}
	var file := FileAccess.open(_slot_path(slot), FileAccess.WRITE)
	if file == null:
		push_warning("SaveSystem: cannot write slot %d (error %d)" % [slot, FileAccess.get_open_error()])
		return false
	file.store_string(JSON.stringify(payload, "\\t"))
	file.close()
	saved.emit(slot)
	return true


func read_slot(slot: int = 1) -> Dictionary:
	if not has_save(slot):
		return {}
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(_slot_path(slot)))
	return parsed if parsed is Dictionary else {}


func load_game(slot: int = 1) -> bool:
	var data := read_slot(slot)
	if data.is_empty():
		return false
	extra_data = data.get("extra", {})
	var scene_path: String = data.get("scene", "")
	if scene_path != "" and get_tree().current_scene and scene_path != get_tree().current_scene.scene_file_path:
		get_tree().change_scene_to_file(scene_path)
		await get_tree().process_frame
		await get_tree().process_frame
	var nodes: Dictionary = data.get("nodes", {})
	for path in nodes:
		var n := get_node_or_null(NodePath(path))
		if n and n.has_method("load_data"):
			n.load_data(nodes[path])
	loaded.emit(slot)
	return true


func delete_save(slot: int = 1) -> void:
	if has_save(slot):
		DirAccess.remove_absolute(_slot_path(slot))


func get_setting(section: String, key: String, default = null):
	return _settings.get_value(section, key, default)


func set_setting(section: String, key: String, value) -> void:
	_settings.set_value(section, key, value)
	_settings.save(SETTINGS_PATH)
''', autoload=True)

add("scene_transition", "Autoload SceneTransition: fade-to-black scene changes (change_scene(path, duration)) built entirely in code.", '''extends CanvasLayer
## Autoload "SceneTransition". Usage: SceneTransition.change_scene("res://scenes/level_2.tscn")

signal finished

@export var color: Color = Color.BLACK
@export var default_duration: float = 0.45

var _rect: ColorRect
var _busy: bool = false


func _ready() -> void:
	layer = 100
	process_mode = Node.PROCESS_MODE_ALWAYS
	_rect = ColorRect.new()
	_rect.color = Color(color, 0.0)
	_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(_rect)


func change_scene(path: String, duration: float = -1.0) -> void:
	if _busy or not ResourceLoader.exists(path):
		return
	_busy = true
	var d: float = default_duration if duration < 0.0 else duration
	_rect.mouse_filter = Control.MOUSE_FILTER_STOP
	var tw := create_tween()
	tw.tween_property(_rect, "color:a", 1.0, d)
	await tw.finished
	get_tree().paused = false
	get_tree().change_scene_to_file(path)
	await get_tree().process_frame
	var tw2 := create_tween()
	tw2.tween_property(_rect, "color:a", 0.0, d)
	await tw2.finished
	_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_busy = false
	finished.emit()


func fade_out(duration: float = -1.0) -> void:
	var tw := create_tween()
	tw.tween_property(_rect, "color:a", 1.0, default_duration if duration < 0.0 else duration)
	await tw.finished


func fade_in(duration: float = -1.0) -> void:
	var tw := create_tween()
	tw.tween_property(_rect, "color:a", 0.0, default_duration if duration < 0.0 else duration)
	await tw.finished
''', autoload=True)
