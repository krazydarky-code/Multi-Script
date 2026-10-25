# SPDX-License-Identifier: GPL-3.0-or-later
"""GDScript controllers for ms_godot_ui_kit (tabs for indentation, Godot 4.x)."""

MAIN_MENU = '''extends Control
## Main menu controller. Connect to the signals or set play_scene to switch scenes directly.

signal play_pressed
signal settings_pressed
signal quit_pressed

@export_file("*.tscn") var play_scene: String = ""
@export_file("*.tscn") var settings_scene: String = ""

func _ready() -> void:
	for b in find_children("*Button", "Button", true, false):
		b.pressed.connect(_on_pressed.bind(b.name))
	var first := find_children("*Button", "Button", true, false)
	if first.size() > 0:
		(first[0] as Button).grab_focus()

func _on_pressed(button_name: StringName) -> void:
	var n := String(button_name).to_lower()
	if n.begins_with("play") or n.begins_with("start"):
		play_pressed.emit()
		if play_scene != "":
			get_tree().change_scene_to_file(play_scene)
	elif n.begins_with("settings") or n.begins_with("options"):
		settings_pressed.emit()
		if settings_scene != "":
			get_tree().change_scene_to_file(settings_scene)
	elif n.begins_with("quit") or n.begins_with("exit"):
		quit_pressed.emit()
		get_tree().quit()
'''

HUD = '''extends Control
## HUD controller: call set_health(), set_mana(), set_score(), select_slot() from gameplay code.

@onready var health_bar: ProgressBar = %HealthBar
@onready var mana_bar: ProgressBar = %ManaBar
@onready var score_label: Label = %ScoreLabel
var _score := 0

func set_health(value: float, max_value: float = -1.0) -> void:
	if max_value > 0.0:
		health_bar.max_value = max_value
	create_tween().tween_property(health_bar, "value", value, 0.2)

func set_mana(value: float, max_value: float = -1.0) -> void:
	if max_value > 0.0:
		mana_bar.max_value = max_value
	create_tween().tween_property(mana_bar, "value", value, 0.2)

func set_score(value: int) -> void:
	_score = value
	score_label.text = "SCORE %d" % value
	var tw := create_tween()
	score_label.pivot_offset = score_label.size * 0.5
	tw.tween_property(score_label, "scale", Vector2(1.15, 1.15), 0.08)
	tw.tween_property(score_label, "scale", Vector2.ONE, 0.12)

func add_score(amount: int) -> void:
	set_score(_score + amount)

func select_slot(index: int) -> void:
	var slots := %Hotbar.get_children()
	for i in slots.size():
		(slots[i] as Control).modulate = Color.WHITE if i == index else Color(1, 1, 1, 0.55)
'''

PAUSE = '''extends Control
## Pause menu. Toggles with the ui_cancel action (Esc) and pauses the tree. Runs while paused.

signal resumed
signal quit_to_menu

@export_file("*.tscn") var menu_scene: String = ""

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	visible = false
	for b in find_children("*Button", "Button", true, false):
		b.pressed.connect(_on_pressed.bind(b.name))

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		set_paused(not get_tree().paused)
		get_viewport().set_input_as_handled()

func set_paused(value: bool) -> void:
	get_tree().paused = value
	visible = value
	if value:
		var b := find_children("*Button", "Button", true, false)
		if b.size() > 0:
			(b[0] as Button).grab_focus()
	else:
		resumed.emit()

func _on_pressed(button_name: StringName) -> void:
	var n := String(button_name).to_lower()
	if n.begins_with("resume"):
		set_paused(false)
	elif n.begins_with("restart"):
		get_tree().paused = false
		get_tree().reload_current_scene()
	elif n.begins_with("menu") or n.begins_with("quittomenu"):
		get_tree().paused = false
		quit_to_menu.emit()
		if menu_scene != "":
			get_tree().change_scene_to_file(menu_scene)
	elif n.begins_with("quit"):
		get_tree().quit()
'''

SHOP = '''extends Control
## Shop window. Emits purchased(item, price); you decide how to pay (see try_buy for a coins example).

signal purchased(item_name: String, price: int)
signal closed

func _ready() -> void:
	for b in find_children("Buy_*", "Button", true, false):
		b.pressed.connect(_on_buy.bind(b))
	if has_node("%CloseButton"):
		%CloseButton.pressed.connect(close)

func _on_buy(button: Button) -> void:
	var item := String(button.name).trim_prefix("Buy_")
	var price := int(button.get_meta("price", 0))
	purchased.emit(item, price)

func close() -> void:
	visible = false
	closed.emit()

func open() -> void:
	visible = true

func try_buy(coins: int, price: int) -> bool:
	return coins >= price
'''

DIALOG = '''extends Control
## Dialogue box with typewriter text and choices.
## show_line("Elder", "Welcome!", ["Hello", "Goodbye"]) then await choice_made / line_finished.

signal line_finished
signal choice_made(index: int)

@export var chars_per_second: float = 45.0
@onready var name_label: Label = %NameLabel
@onready var body: RichTextLabel = %Body
@onready var choices: HBoxContainer = %Choices
var _tween: Tween

func _ready() -> void:
	body.bbcode_enabled = true
	for i in choices.get_child_count():
		(choices.get_child(i) as Button).pressed.connect(_on_choice.bind(i))
		(choices.get_child(i) as Button).visible = false

func show_line(speaker: String, text: String, options: Array = []) -> void:
	visible = true
	name_label.text = speaker
	body.text = text
	body.visible_ratio = 0.0
	if _tween:
		_tween.kill()
	_tween = create_tween()
	_tween.tween_property(body, "visible_ratio", 1.0, maxf(0.05, text.length() / chars_per_second))
	_tween.finished.connect(func():
		line_finished.emit()
		for i in choices.get_child_count():
			var btn := choices.get_child(i) as Button
			btn.visible = i < options.size()
			if i < options.size():
				btn.text = str(options[i])
	)

func skip() -> void:
	if _tween:
		_tween.kill()
	body.visible_ratio = 1.0
	line_finished.emit()

func _unhandled_input(event: InputEvent) -> void:
	if visible and event.is_action_pressed("ui_accept") and body.visible_ratio < 1.0:
		skip()
		get_viewport().set_input_as_handled()

func _on_choice(index: int) -> void:
	choice_made.emit(index)
'''

SETTINGS = '''extends Control
## Settings panel: volume sliders drive audio buses by name, plus fullscreen and vsync toggles.

signal back_pressed

func _ready() -> void:
	for s in find_children("*Slider", "HSlider", true, false):
		var bus := String(s.name).trim_suffix("Slider")
		var idx := AudioServer.get_bus_index(bus)
		if idx >= 0:
			s.value = db_to_linear(AudioServer.get_bus_volume_db(idx))
		s.value_changed.connect(_on_volume.bind(bus))
	if has_node("%FullscreenCheck"):
		%FullscreenCheck.toggled.connect(func(on: bool): DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN if on else DisplayServer.WINDOW_MODE_WINDOWED))
	if has_node("%VSyncCheck"):
		%VSyncCheck.toggled.connect(func(on: bool): DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ENABLED if on else DisplayServer.VSYNC_DISABLED))
	if has_node("%BackButton"):
		%BackButton.pressed.connect(func(): back_pressed.emit())

func _on_volume(value: float, bus: String) -> void:
	var idx := AudioServer.get_bus_index(bus)
	if idx >= 0:
		AudioServer.set_bus_volume_db(idx, linear_to_db(maxf(value, 0.0001)))
		AudioServer.set_bus_mute(idx, value <= 0.001)
'''

INVENTORY = '''extends Control
## Grid inventory. set_item(slot, "Sword", icon) fills a slot; clear_slot(slot) empties it.

signal slot_pressed(index: int)

func _ready() -> void:
	var slots := %Grid.get_children()
	for i in slots.size():
		(slots[i] as Control).gui_input.connect(_on_slot_input.bind(i))

func set_item(index: int, item_name: String, icon: Texture2D = null) -> void:
	var slot := %Grid.get_child(index) as Control
	slot.get_node("Label").text = item_name
	if slot.has_node("Icon"):
		(slot.get_node("Icon") as TextureRect).texture = icon

func clear_slot(index: int) -> void:
	set_item(index, "")

func _on_slot_input(event: InputEvent, index: int) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		slot_pressed.emit(index)
'''

TOAST = '''extends Control
## Toast notifications. Toast.show_toast("Checkpoint saved") from anywhere you hold a reference.

@export var seconds: float = 2.5

func show_toast(text: String, duration: float = -1.0) -> void:
	var panel := PanelContainer.new()
	var label := Label.new()
	label.text = text
	panel.add_child(label)
	%ToastList.add_child(panel)
	panel.modulate.a = 0.0
	var tw := create_tween()
	tw.tween_property(panel, "modulate:a", 1.0, 0.2)
	tw.tween_interval(duration if duration > 0.0 else seconds)
	tw.tween_property(panel, "modulate:a", 0.0, 0.4)
	tw.tween_callback(panel.queue_free)
'''

SCRIPTS = {"main_menu": MAIN_MENU, "hud": HUD, "pause": PAUSE, "shop": SHOP, "dialog": DIALOG, "settings": SETTINGS, "inventory": INVENTORY, "toast": TOAST}
