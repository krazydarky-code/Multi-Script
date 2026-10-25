# SPDX-License-Identifier: GPL-3.0-or-later
"""Luau builders written by Forge's bind step. Every class, property, enum and method used here
was checked against the offline Roblox API reference (ms_roblox_docs)."""

UI_USAGE = '''-- LocalScript in StarterPlayerScripts
local Kit = require(game:GetService("ReplicatedStorage"):WaitForChild("ForgeKit"))
local gui = Kit.screen("Shop")
local shop = Kit.modal(gui, {title = "SHOP", ribbon = true, size = UDim2.fromOffset(560, 420)})
local grid = Kit.grid(shop.Content, {cellSize = UDim2.fromOffset(150, 190)})
local items = {
	{name = "Speed Coil", price = 250, icon = "speed", rarity = "rare"},
	{name = "Golden Egg", price = 900, icon = "egg", rarity = "legendary", badge = "NEW"},
}
for i, item in ipairs(items) do
	Kit.card(grid, {title = item.name, icon = item.icon, price = item.price, rarity = item.rarity, badge = item.badge, layoutOrder = i, onBuy = function()
		-- fire a RemoteEvent; the server checks the price and the player's currency
	end})
end
local _, coins = Kit.pill(gui, {icon = "coin", text = "1,250", position = UDim2.new(0, 16, 0, 16)})
Kit.button(gui, {text = "SHOP", icon = "cart", variant = "secondary", anchor = Vector2.new(0, 1), position = UDim2.new(0, 16, 1, -16), onClick = shop.Open})
Kit.toast(gui, "Welcome back!", {icon = "star"})
'''

VFX_USAGE = '''-- LocalScript: play effects on this client after the server confirms the event
local VFX = require(game:GetService("ReplicatedStorage"):WaitForChild("ForgeVFX"))
VFX.combo(hitPosition, {"burst_glow", "hit_sparks", "impact_ring"})
VFX.burst(position, "explosion")
local aura = VFX.attach(character.HumanoidRootPart, "sparkle_aura")
-- later: VFX.stop(aura)
'''

UI_LUAU = r'''-- ForgeKit: builds live, scaling Roblox UI from a Multi-Script Forge art set (style: __STYLE__).
-- ModuleScript in ReplicatedStorage; require it from a LocalScript. Art is 2x; SliceScale 0.5 keeps 9-slice edges crisp.
local Players = game:GetService("Players")
local TweenService = game:GetService("TweenService")
local UserInputService = game:GetService("UserInputService")

local Kit = {}
Kit.Assets = __ASSETS__
Kit.Slices = __SLICES__
Kit.Theme = {
	Font = __FONT__,
	Text = Color3.fromHex("__TEXT__"),
	Stroke = Color3.fromHex("__STROKE__"),
	Accent = Color3.fromHex("__ACCENT__"),
	SliceScale = 0.5,
	DesignSize = Vector2.new(1280, 720),
}

local PRESS = TweenInfo.new(0.08, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)
local SLIDE = TweenInfo.new(0.18, Enum.EasingStyle.Quint, Enum.EasingDirection.Out)
local POP = TweenInfo.new(0.22, Enum.EasingStyle.Back, Enum.EasingDirection.Out)
local CLOSE = TweenInfo.new(0.14, Enum.EasingStyle.Quad, Enum.EasingDirection.In)
local selectionRing = nil

local function img(key)
	local id = Kit.Assets[key]
	if id == nil or id == "" then
		warn("ForgeKit: no asset id for " .. key .. "; run the Forge bind step")
		return ""
	end
	return id
end

local function slice(gui, key)
	local s = Kit.Slices[key]
	if s then
		gui.ScaleType = Enum.ScaleType.Slice
		gui.SliceCenter = Rect.new(s[1], s[2], s[3], s[4])
		gui.SliceScale = Kit.Theme.SliceScale
	else
		gui.ScaleType = Enum.ScaleType.Fit
	end
end

local function make(className, parent, props)
	local o = Instance.new(className)
	if o:IsA("GuiObject") then
		o.BackgroundTransparency = 1
		o.BorderSizePixel = 0
	end
	for k, v in pairs(props or {}) do
		o[k] = v
	end
	o.Parent = parent
	return o
end

local function place(o, opts)
	if opts.size then o.Size = opts.size end
	if opts.position then o.Position = opts.position end
	if opts.anchor then o.AnchorPoint = opts.anchor end
	if opts.name then o.Name = opts.name end
	if opts.layoutOrder then o.LayoutOrder = opts.layoutOrder end
	if opts.zIndex then o.ZIndex = opts.zIndex end
end

local function pad(o, l, r, t, b)
	return make("UIPadding", o, {PaddingLeft = UDim.new(l, 0), PaddingRight = UDim.new(r, 0), PaddingTop = UDim.new(t, 0), PaddingBottom = UDim.new(b, 0)})
end

-- Gamepad: every Forge button is selectable and shows the Forge selection ring.
local function selectable(button)
	button.Selectable = true
	if selectionRing == nil and Kit.Assets.selection and Kit.Assets.selection ~= "" then
		selectionRing = Instance.new("ImageLabel")
		selectionRing.Name = "ForgeSelection"
		selectionRing.BackgroundTransparency = 1
		selectionRing.Image = Kit.Assets.selection
		selectionRing.Size = UDim2.new(1, 16, 1, 16)
		selectionRing.Position = UDim2.fromOffset(-8, -8)
		slice(selectionRing, "selection")
	end
	if selectionRing then button.SelectionImageObject = selectionRing end
end

local function pressFeedback(button)
	local scale = make("UIScale", button, {Scale = 1})
	button.MouseButton1Down:Connect(function()
		TweenService:Create(scale, PRESS, {Scale = 0.94}):Play()
	end)
	local function release()
		TweenService:Create(scale, PRESS, {Scale = 1}):Play()
	end
	button.MouseButton1Up:Connect(release)
	button.MouseLeave:Connect(release)
	selectable(button)
	return scale
end

-- A ScreenGui in the local player's PlayerGui that scales with the screen and keeps out of notches.
function Kit.screen(name, opts)
	opts = opts or {}
	local parent = opts.parent or Players.LocalPlayer:WaitForChild("PlayerGui")
	local gui = Instance.new("ScreenGui")
	gui.Name = name or "ForgeUI"
	gui.ResetOnSpawn = false
	gui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
	gui.ScreenInsets = Enum.ScreenInsets.DeviceSafeInsets
	gui.DisplayOrder = opts.displayOrder or 0
	local scale = make("UIScale", gui, {Name = "AutoScale"})
	local camera = workspace.CurrentCamera
	local function rescale()
		local v = camera.ViewportSize
		local s = math.min(v.X / Kit.Theme.DesignSize.X, v.Y / Kit.Theme.DesignSize.Y)
		scale.Scale = math.clamp(s, opts.minScale or 0.6, opts.maxScale or 1.4)
	end
	camera:GetPropertyChangedSignal("ViewportSize"):Connect(rescale)
	rescale()
	gui.Parent = parent
	return gui
end

function Kit.label(parent, text, opts)
	opts = opts or {}
	local l = make("TextLabel", parent, {
		Text = text or "",
		TextScaled = true,
		TextWrapped = opts.wrap == true,
		RichText = opts.rich == true,
		FontFace = Font.fromEnum(opts.font or Kit.Theme.Font),
		TextColor3 = opts.color or Kit.Theme.Text,
		Size = UDim2.fromScale(1, 1),
		TextXAlignment = opts.align or Enum.TextXAlignment.Center,
		Name = "Label",
	})
	place(l, opts)
	make("UITextSizeConstraint", l, {MaxTextSize = opts.maxSize or 34, MinTextSize = opts.minSize or 9})
	if opts.stroke ~= false then
		make("UIStroke", l, {Color = opts.strokeColor or Kit.Theme.Stroke, Thickness = opts.strokeThickness or 2.5})
	end
	return l
end

-- kind: coin gem star heart bolt lock gift sword shield potion trophy crown key chest egg paw pickaxe gear cart bag scroll clock skull flame drop leaf ticket rebirth speed ghost
function Kit.icon(parent, kind, opts)
	opts = opts or {}
	local i = make("ImageLabel", parent, {Image = img("item_" .. kind), ScaleType = Enum.ScaleType.Fit, Size = UDim2.fromOffset(40, 40), Name = kind})
	place(i, opts)
	return i
end

-- variant: "primary" | "secondary" | "success" | "danger"
function Kit.button(parent, opts)
	opts = opts or {}
	local v = opts.variant or "primary"
	local key = "button_" .. v .. "_"
	local b = make("ImageButton", parent, {
		Size = UDim2.fromOffset(200, 72),
		AutoButtonColor = false,
		Image = img(key .. "normal"),
		HoverImage = img(key .. "hover"),
		PressedImage = img(key .. "pressed"),
		Name = opts.text or "Button",
	})
	place(b, opts)
	slice(b, key .. "normal")
	pad(b, 0.1, 0.1, 0.16, 0.26)
	if opts.icon then
		Kit.icon(b, opts.icon, {anchor = Vector2.new(0, 0.5), position = UDim2.fromScale(0, 0.5), size = UDim2.fromScale(0.3, 1.1)})
		Kit.label(b, opts.text or "", {anchor = Vector2.new(1, 0.5), position = UDim2.fromScale(1, 0.5), size = UDim2.fromScale(0.68, 1)})
	else
		Kit.label(b, opts.text or "Button")
	end
	pressFeedback(b)
	b:SetAttribute("ForgeVariant", v)
	if opts.onClick then
		b.Activated:Connect(function()
			if b:GetAttribute("ForgeDisabled") then return end
			opts.onClick()
		end)
	end
	if opts.disabled then Kit.setEnabled(b, false) end
	return b
end

function Kit.setEnabled(button, enabled)
	local v = button:GetAttribute("ForgeVariant") or "primary"
	local key = "button_" .. v .. "_"
	button:SetAttribute("ForgeDisabled", not enabled)
	button.Image = img(key .. (enabled and "normal" or "disabled"))
	button.HoverImage = enabled and img(key .. "hover") or ""
	button.PressedImage = enabled and img(key .. "pressed") or ""
end

-- kind: "close" | "back" | "plus" | "minus" | "next" | "confirm" | "help"
function Kit.iconButton(parent, kind, opts)
	opts = opts or {}
	local key = "icon_" .. kind .. "_"
	local b = make("ImageButton", parent, {
		Size = UDim2.fromOffset(56, 56),
		AutoButtonColor = false,
		ScaleType = Enum.ScaleType.Fit,
		Image = img(key .. "normal"),
		HoverImage = img(key .. "hover"),
		PressedImage = img(key .. "pressed"),
		Name = kind,
	})
	place(b, opts)
	make("UIAspectRatioConstraint", b, {AspectRatio = 1})
	pressFeedback(b)
	if opts.onClick then b.Activated:Connect(opts.onClick) end
	return b
end

-- Returns the panel and a padded content frame.
function Kit.panel(parent, opts)
	opts = opts or {}
	local art = opts.art or "panel"
	local p = make("ImageLabel", parent, {Image = img(art), Size = UDim2.fromOffset(420, 320), Name = "Panel"})
	place(p, opts)
	slice(p, art)
	local content = make("Frame", p, {Size = UDim2.fromScale(1, 1), Name = "Content"})
	pad(content, 0.05, 0.05, opts.title and 0.15 or 0.06, 0.07)
	if opts.title then
		local headerArt = opts.ribbon and "ribbon" or "header"
		local h = make("ImageLabel", p, {
			Image = img(headerArt),
			AnchorPoint = Vector2.new(0.5, 0.5),
			Position = UDim2.fromScale(0.5, 0.02),
			Size = UDim2.new(opts.ribbon and 0.8 or 0.62, 0, 0, opts.ribbon and 64 or 58),
			ZIndex = p.ZIndex + 2,
			Name = "Header",
		})
		slice(h, headerArt)
		pad(h, opts.ribbon and 0.16 or 0.08, opts.ribbon and 0.16 or 0.08, 0.16, 0.3)
		Kit.label(h, opts.title, {maxSize = 30, zIndex = p.ZIndex + 3})
	end
	if opts.onClose then
		Kit.iconButton(p, "close", {anchor = Vector2.new(0.5, 0.5), position = UDim2.new(1, -8, 0, 8), size = UDim2.fromOffset(52, 52), zIndex = p.ZIndex + 3, onClick = opts.onClose})
	end
	return p, content
end

-- A centred window that pops open and closed. Returns {Frame, Content, Open, Close, IsOpen}.
function Kit.modal(parent, opts)
	opts = opts or {}
	local m = {}
	local scale
	m.Close = function()
		if not m.Frame.Visible then return end
		local t = TweenService:Create(scale, CLOSE, {Scale = 0.85})
		t:Play()
		t.Completed:Wait()
		m.Frame.Visible = false
		if opts.onClose then opts.onClose() end
	end
	local frame, content = Kit.panel(parent, {
		title = opts.title, ribbon = opts.ribbon, size = opts.size or UDim2.fromOffset(520, 380),
		anchor = Vector2.new(0.5, 0.5), position = opts.position or UDim2.fromScale(0.5, 0.5), name = opts.name or "Modal",
		onClose = function() m.Close() end,
	})
	scale = make("UIScale", frame, {Scale = 0.85})
	frame.Visible = false
	m.Frame, m.Content = frame, content
	m.Open = function(instant)
		frame.Visible = true
		if instant == true then
			scale.Scale = 1
			return
		end
		scale.Scale = 0.85
		TweenService:Create(scale, POP, {Scale = 1}):Play()
	end
	m.IsOpen = function() return frame.Visible end
	return m
end

function Kit.inner(parent, opts)
	opts = opts or {}
	local f = make("ImageLabel", parent, {Image = img("panel_inner"), Size = UDim2.fromScale(1, 1), Name = "Inner"})
	place(f, opts)
	slice(f, "panel_inner")
	return f
end

-- A scrolling grid; the canvas grows with its children.
function Kit.grid(parent, opts)
	opts = opts or {}
	local s = make("ScrollingFrame", parent, {
		Size = UDim2.fromScale(1, 1), CanvasSize = UDim2.new(), AutomaticCanvasSize = Enum.AutomaticSize.Y,
		ScrollBarThickness = 8, ScrollBarImageColor3 = Kit.Theme.Accent, ScrollingDirection = Enum.ScrollingDirection.Y, Name = "Grid",
	})
	place(s, opts)
	make("UIGridLayout", s, {CellSize = opts.cellSize or UDim2.fromOffset(110, 110), CellPadding = opts.cellPadding or UDim2.fromOffset(10, 10), SortOrder = Enum.SortOrder.LayoutOrder, HorizontalAlignment = Enum.HorizontalAlignment.Center})
	make("UIPadding", s, {PaddingTop = UDim.new(0, 6), PaddingBottom = UDim.new(0, 6), PaddingLeft = UDim.new(0, 6), PaddingRight = UDim.new(0, 14)})
	return s
end

-- A scrolling vertical list (leaderboards, quests, settings).
function Kit.list(parent, opts)
	opts = opts or {}
	local s = make("ScrollingFrame", parent, {
		Size = UDim2.fromScale(1, 1), CanvasSize = UDim2.new(), AutomaticCanvasSize = Enum.AutomaticSize.Y,
		ScrollBarThickness = 8, ScrollBarImageColor3 = Kit.Theme.Accent, ScrollingDirection = Enum.ScrollingDirection.Y, Name = "List",
	})
	place(s, opts)
	make("UIListLayout", s, {Padding = UDim.new(0, opts.gap or 8), SortOrder = Enum.SortOrder.LayoutOrder, HorizontalAlignment = Enum.HorizontalAlignment.Center})
	make("UIPadding", s, {PaddingTop = UDim.new(0, 6), PaddingBottom = UDim.new(0, 6), PaddingRight = UDim.new(0, 12)})
	return s
end

-- rarity: common | uncommon | rare | epic | legendary | mythic | secret | selected
function Kit.slot(parent, opts)
	opts = opts or {}
	local key = "slot_" .. (opts.rarity or "common")
	local s = make("ImageButton", parent, {Image = img(key), Size = UDim2.fromOffset(84, 84), AutoButtonColor = false, Name = "Slot"})
	place(s, opts)
	slice(s, key)
	make("UIAspectRatioConstraint", s, {AspectRatio = 1})
	if opts.icon then
		local icon = opts.icon
		if Kit.Assets["item_" .. icon] then icon = Kit.Assets["item_" .. icon] end
		make("ImageLabel", s, {Image = icon, AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.47), Size = UDim2.fromScale(0.66, 0.66), ScaleType = Enum.ScaleType.Fit, Name = "Icon"})
	end
	if opts.count then
		Kit.label(s, "x" .. tostring(opts.count), {anchor = Vector2.new(1, 1), position = UDim2.fromScale(0.94, 0.96), size = UDim2.fromScale(0.6, 0.3), align = Enum.TextXAlignment.Right, maxSize = 22})
	end
	if opts.locked then Kit.icon(s, "lock", {anchor = Vector2.new(0.5, 0.5), position = UDim2.fromScale(0.5, 0.5), size = UDim2.fromScale(0.5, 0.5)}) end
	pressFeedback(s)
	if opts.onClick then s.Activated:Connect(opts.onClick) end
	return s
end

function Kit.setSlotRarity(slot, rarity)
	slot.Image = img("slot_" .. rarity)
	slice(slot, "slot_" .. rarity)
end

-- A shop card: card art, a rarity slot with the icon, the title and a buy button with the price.
function Kit.card(parent, opts)
	opts = opts or {}
	local c = make("ImageLabel", parent, {Image = img("card"), Size = UDim2.fromOffset(150, 190), Name = opts.title or "Card"})
	place(c, opts)
	slice(c, "card")
	pad(c, 0.07, 0.07, 0.06, 0.08)
	Kit.slot(c, {rarity = opts.rarity or "common", icon = opts.icon, size = UDim2.fromScale(0.62, 0.62), anchor = Vector2.new(0.5, 0), position = UDim2.fromScale(0.5, 0)})
	Kit.label(c, opts.title or "", {anchor = Vector2.new(0.5, 0), position = UDim2.fromScale(0.5, 0.5), size = UDim2.fromScale(1, 0.15), maxSize = 22})
	local buy = Kit.button(c, {text = opts.price and tostring(opts.price) or "BUY", icon = opts.priceIcon or "coin", variant = opts.variant or "success",
		anchor = Vector2.new(0.5, 1), position = UDim2.fromScale(0.5, 1), size = UDim2.fromScale(1, 0.3), onClick = opts.onBuy})
	if opts.badge then Kit.cornerRibbon(c, opts.badge) end
	return c, buy
end

-- kind: "progress" | "xp" | "hp" | "mana". Returns the bar and set(value 0..1, text).
function Kit.bar(parent, opts)
	opts = opts or {}
	local fillKey = (opts.kind == nil or opts.kind == "progress") and "progress_fill" or (opts.kind .. "_fill")
	local track = make("ImageLabel", parent, {Image = img("progress_track"), Size = UDim2.fromOffset(260, 30), Name = "Bar"})
	place(track, opts)
	slice(track, "progress_track")
	local clip = make("Frame", track, {Size = UDim2.fromScale(0, 1), ClipsDescendants = true, Name = "Clip"})
	local fill = make("ImageLabel", clip, {Image = img(fillKey), Size = UDim2.fromScale(1, 1), Name = "Fill"})
	slice(fill, fillKey)
	local label = opts.showText and Kit.label(track, "", {maxSize = 20}) or nil
	local function apply(value, instant, text)
		value = math.clamp(value, 0, 1)
		local clipGoal = UDim2.fromScale(value, 1)
		local fillGoal = UDim2.fromScale(value > 0 and 1 / value or 1, 1)
		if instant then
			clip.Size = clipGoal
			fill.Size = fillGoal
		else
			TweenService:Create(clip, SLIDE, {Size = clipGoal}):Play()
			TweenService:Create(fill, SLIDE, {Size = fillGoal}):Play()
		end
		if label then label.Text = text or string.format("%d%%", math.floor(value * 100 + 0.5)) end
	end
	apply(opts.value or 0, true)
	return track, function(value, text) apply(value, false, text) end
end
Kit.progress = Kit.bar

-- Currency or stat pill; returns the pill and its text label.
function Kit.pill(parent, opts)
	opts = opts or {}
	local p = make("ImageLabel", parent, {Image = img("pill"), Size = UDim2.fromOffset(170, 52), Name = "Pill"})
	place(p, opts)
	slice(p, "pill")
	make("ImageLabel", p, {Image = img("item_" .. (opts.icon or "coin")), AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.new(0, 6, 0.5, 0), Size = UDim2.fromScale(1.15, 1.15), SizeConstraint = Enum.SizeConstraint.RelativeYY, ScaleType = Enum.ScaleType.Fit, ZIndex = p.ZIndex + 1, Name = "Icon"})
	local text = Kit.label(p, opts.text or "0", {anchor = Vector2.new(1, 0.5), position = UDim2.new(1, -14, 0.46, 0), size = UDim2.new(1, -46, 0.62, 0), align = Enum.TextXAlignment.Right, maxSize = 28})
	if opts.onPlus then Kit.iconButton(p, "plus", {anchor = Vector2.new(0.5, 0.5), position = UDim2.new(1, 4, 0.5, 0), size = UDim2.fromOffset(34, 34), onClick = opts.onPlus}) end
	return p, text
end

function Kit.priceTag(parent, opts)
	opts = opts or {}
	local t = make("ImageLabel", parent, {Image = img("price_tag"), Size = UDim2.fromOffset(130, 48), Name = "Price"})
	place(t, opts)
	slice(t, "price_tag")
	pad(t, 0.2, 0.08, 0.12, 0.12)
	Kit.icon(t, opts.icon or "coin", {anchor = Vector2.new(0, 0.5), position = UDim2.fromScale(0, 0.5), size = UDim2.fromScale(0.3, 1.2)})
	local l = Kit.label(t, tostring(opts.price or 0), {anchor = Vector2.new(1, 0.5), position = UDim2.fromScale(1, 0.5), size = UDim2.fromScale(0.68, 1), maxSize = 24})
	return t, l
end

-- Returns the toggle and set(on).
function Kit.toggle(parent, opts)
	opts = opts or {}
	local on = opts.on == true
	local t = make("ImageButton", parent, {Size = UDim2.fromOffset(68, 36), AutoButtonColor = false, Name = "Toggle"})
	place(t, opts)
	make("UIAspectRatioConstraint", t, {AspectRatio = 136 / 72})
	local knob = make("ImageLabel", t, {Image = img("toggle_knob"), ScaleType = Enum.ScaleType.Fit, AnchorPoint = Vector2.new(0.5, 0.5), Size = UDim2.fromScale(0.5, 0.94), Name = "Knob"})
	local function set(value, instant)
		on = value
		t.Image = img(on and "toggle_on" or "toggle_off")
		slice(t, on and "toggle_on" or "toggle_off")
		local goal = UDim2.fromScale(on and 0.72 or 0.28, 0.5)
		if instant then knob.Position = goal else TweenService:Create(knob, SLIDE, {Position = goal}):Play() end
	end
	t.Activated:Connect(function()
		set(not on)
		if opts.onChanged then opts.onChanged(on) end
	end)
	selectable(t)
	set(on, true)
	return t, set
end

-- Returns the checkbox row and set(checked).
function Kit.checkbox(parent, opts)
	opts = opts or {}
	local checked = opts.checked == true
	local row = make("ImageButton", parent, {Size = UDim2.fromOffset(220, 36), AutoButtonColor = false, Name = "Checkbox"})
	place(row, opts)
	local box = make("ImageLabel", row, {ScaleType = Enum.ScaleType.Fit, Size = UDim2.fromScale(1, 1), SizeConstraint = Enum.SizeConstraint.RelativeYY, Name = "Box"})
	Kit.label(row, opts.text or "", {anchor = Vector2.new(1, 0.5), position = UDim2.fromScale(1, 0.5), size = UDim2.new(1, -44, 0.8, 0), align = Enum.TextXAlignment.Left, maxSize = 24})
	local function set(v)
		checked = v
		box.Image = img(checked and "checkbox_on" or "checkbox_off")
	end
	row.Activated:Connect(function()
		set(not checked)
		if opts.onChanged then opts.onChanged(checked) end
	end)
	selectable(row)
	set(checked)
	return row, set
end

-- Radio group: options = {"Low", "Medium", "High"}. Returns the frame and set(index).
function Kit.radio(parent, opts)
	opts = opts or {}
	local options = opts.options or {}
	local f = make("Frame", parent, {Size = UDim2.fromOffset(220, 36 * #options), Name = "Radio"})
	place(f, opts)
	make("UIListLayout", f, {Padding = UDim.new(0, 6), SortOrder = Enum.SortOrder.LayoutOrder})
	local dots = {}
	local function set(i)
		for j, d in ipairs(dots) do d.Image = img(j == i and "radio_on" or "radio_off") end
	end
	for i, text in ipairs(options) do
		local row = make("ImageButton", f, {Size = UDim2.new(1, 0, 0, 30), AutoButtonColor = false, LayoutOrder = i, Name = text})
		dots[i] = make("ImageLabel", row, {ScaleType = Enum.ScaleType.Fit, Size = UDim2.fromScale(1, 1), SizeConstraint = Enum.SizeConstraint.RelativeYY, Name = "Dot"})
		Kit.label(row, text, {anchor = Vector2.new(1, 0.5), position = UDim2.fromScale(1, 0.5), size = UDim2.new(1, -40, 0.8, 0), align = Enum.TextXAlignment.Left, maxSize = 22})
		row.Activated:Connect(function()
			set(i)
			if opts.onChanged then opts.onChanged(i, text) end
		end)
		selectable(row)
	end
	set(opts.selected or 1)
	return f, set
end

-- Draggable slider for mouse and touch. Returns the slider and set(value 0..1).
function Kit.slider(parent, opts)
	opts = opts or {}
	local track = make("ImageButton", parent, {Image = img("slider_track"), Size = UDim2.fromOffset(240, 22), AutoButtonColor = false, Name = "Slider"})
	place(track, opts)
	slice(track, "slider_track")
	local clip = make("Frame", track, {Size = UDim2.fromScale(0, 1), ClipsDescendants = true, Name = "Clip"})
	local fill = make("ImageLabel", clip, {Image = img("slider_fill"), Size = UDim2.fromScale(1, 1), Name = "Fill"})
	slice(fill, "slider_fill")
	local knob = make("ImageLabel", track, {Image = img("slider_knob"), ScaleType = Enum.ScaleType.Fit, AnchorPoint = Vector2.new(0.5, 0.5), Size = UDim2.fromScale(1.7, 1.7), SizeConstraint = Enum.SizeConstraint.RelativeYY, ZIndex = track.ZIndex + 2, Name = "Knob"})
	local function set(v, fire)
		v = math.clamp(v, 0, 1)
		clip.Size = UDim2.fromScale(v, 1)
		fill.Size = UDim2.fromScale(v > 0 and 1 / v or 1, 1)
		knob.Position = UDim2.fromScale(v, 0.5)
		if fire and opts.onChanged then opts.onChanged(v) end
	end
	local dragging = false
	local function fromInput(input)
		set((input.Position.X - track.AbsolutePosition.X) / math.max(track.AbsoluteSize.X, 1), true)
	end
	track.InputBegan:Connect(function(input)
		if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
			dragging = true
			fromInput(input)
		end
	end)
	UserInputService.InputChanged:Connect(function(input)
		if dragging and (input.UserInputType == Enum.UserInputType.MouseMovement or input.UserInputType == Enum.UserInputType.Touch) then
			fromInput(input)
		end
	end)
	UserInputService.InputEnded:Connect(function(input)
		if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
			dragging = false
		end
	end)
	selectable(track)
	set(opts.value or 0.5, false)
	return track, set
end

-- Text input; returns the frame and its TextBox.
function Kit.input(parent, opts)
	opts = opts or {}
	local f = make("ImageLabel", parent, {Image = img("input"), Size = UDim2.fromOffset(240, 52), Name = "Input"})
	place(f, opts)
	slice(f, "input")
	local box = make("TextBox", f, {
		Size = UDim2.new(1, -28, 0.7, 0), Position = UDim2.fromScale(0.5, 0.5), AnchorPoint = Vector2.new(0.5, 0.5),
		Text = opts.text or "", PlaceholderText = opts.placeholder or "", ClearTextOnFocus = false, TextScaled = true,
		FontFace = Font.fromEnum(Kit.Theme.Font), TextColor3 = Color3.fromRGB(255, 255, 255), PlaceholderColor3 = Color3.fromRGB(190, 196, 210),
		TextXAlignment = Enum.TextXAlignment.Left, Name = "Box",
	})
	make("UITextSizeConstraint", box, {MaxTextSize = 26})
	if opts.onSubmit then
		box.FocusLost:Connect(function(enterPressed)
			if enterPressed then opts.onSubmit(box.Text) end
		end)
	end
	return f, box
end

function Kit.setTab(tab, active)
	tab.Image = img(active and "tab_active" or "tab_inactive")
	slice(tab, active and "tab_active" or "tab_inactive")
end

function Kit.tab(parent, opts)
	opts = opts or {}
	local t = make("ImageButton", parent, {Size = UDim2.fromOffset(130, 52), AutoButtonColor = false, Name = opts.text or "Tab"})
	place(t, opts)
	pad(t, 0.1, 0.1, 0.16, 0.24)
	Kit.label(t, opts.text or "Tab", {maxSize = 24})
	Kit.setTab(t, opts.active == true)
	pressFeedback(t)
	if opts.onClick then t.Activated:Connect(opts.onClick) end
	return t
end

-- Tabs that switch pages: names = {"Items", "Pets"}. Returns tabs, pages (frames to fill) and select(i).
function Kit.tabs(parent, names, opts)
	opts = opts or {}
	local bar = make("Frame", parent, {Size = UDim2.new(1, 0, 0, 52), Name = "Tabs"})
	make("UIListLayout", bar, {FillDirection = Enum.FillDirection.Horizontal, Padding = UDim.new(0, 8), SortOrder = Enum.SortOrder.LayoutOrder})
	local tabs, pages = {}, {}
	local function selectTab(i)
		for j, t in ipairs(tabs) do
			Kit.setTab(t, j == i)
			pages[j].Visible = j == i
		end
		if opts.onChanged then opts.onChanged(i) end
	end
	for i, n in ipairs(names) do
		tabs[i] = Kit.tab(bar, {text = n, layoutOrder = i, onClick = function() selectTab(i) end})
		pages[i] = make("Frame", parent, {Size = UDim2.new(1, 0, 1, -60), Position = UDim2.fromOffset(0, 60), Visible = false, Name = n .. "Page"})
	end
	selectTab(opts.selected or 1)
	return tabs, pages, selectTab
end

function Kit.badge(parent, text)
	local b = make("ImageLabel", parent, {Image = img("badge"), ScaleType = Enum.ScaleType.Fit, AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.92, 0.1), Size = UDim2.fromOffset(30, 30), ZIndex = parent.ZIndex + 4, Name = "Badge"})
	Kit.label(b, text or "!", {maxSize = 18, zIndex = parent.ZIndex + 5})
	return b
end

function Kit.cornerRibbon(parent, text)
	local r = make("ImageLabel", parent, {Image = img("corner_ribbon"), ScaleType = Enum.ScaleType.Fit, AnchorPoint = Vector2.new(1, 0), Position = UDim2.new(1, 6, 0, -6), Size = UDim2.fromOffset(64, 64), ZIndex = parent.ZIndex + 3, Name = "Ribbon"})
	local l = Kit.label(r, text or "NEW", {anchor = Vector2.new(0.5, 0.5), position = UDim2.fromScale(0.62, 0.38), size = UDim2.fromScale(0.75, 0.24), maxSize = 16, zIndex = parent.ZIndex + 4})
	l.Rotation = 45
	return r
end

-- Speech bubble for NPC dialogue and hints. Returns the bubble and its label.
function Kit.bubble(parent, text, opts)
	opts = opts or {}
	local b = make("ImageLabel", parent, {Image = img("bubble"), Size = UDim2.fromOffset(300, 140), Name = "Bubble"})
	place(b, opts)
	slice(b, "bubble")
	pad(b, 0.07, 0.07, 0.1, 0.3)
	local l = Kit.label(b, text or "", {wrap = true, color = opts.color or Color3.fromRGB(40, 44, 56), stroke = false, maxSize = 26})
	return b, l
end

-- Leaderboard row: ranks 1 to 3 get gold, silver and bronze art.
function Kit.leaderboardRow(parent, rank, name, value, opts)
	opts = opts or {}
	local art = rank == 1 and "leaderboard_row_gold" or rank == 2 and "leaderboard_row_silver" or rank == 3 and "leaderboard_row_bronze" or "leaderboard_row"
	local r = make("ImageLabel", parent, {Image = img(art), Size = UDim2.new(1, -8, 0, 46), LayoutOrder = rank, Name = "Row" .. rank})
	place(r, opts)
	slice(r, art)
	pad(r, 0.03, 0.04, 0.12, 0.2)
	Kit.label(r, "#" .. rank, {anchor = Vector2.new(0, 0.5), position = UDim2.fromScale(0, 0.5), size = UDim2.fromScale(0.14, 1), maxSize = 26})
	Kit.label(r, name or "", {anchor = Vector2.new(0, 0.5), position = UDim2.fromScale(0.16, 0.5), size = UDim2.fromScale(0.54, 0.9), align = Enum.TextXAlignment.Left, maxSize = 24})
	Kit.label(r, tostring(value or ""), {anchor = Vector2.new(1, 0.5), position = UDim2.fromScale(1, 0.5), size = UDim2.fromScale(0.28, 0.9), align = Enum.TextXAlignment.Right, maxSize = 24})
	return r
end

-- Toasts stack at the top centre and fade away.
local toastHolders = {}
function Kit.toast(gui, text, opts)
	opts = opts or {}
	local holder = toastHolders[gui]
	if holder == nil or holder.Parent == nil then
		holder = make("Frame", gui, {AnchorPoint = Vector2.new(0.5, 0), Position = UDim2.new(0.5, 0, 0, 12), Size = UDim2.fromOffset(340, 400), Name = "Toasts"})
		make("UIListLayout", holder, {Padding = UDim.new(0, 8), HorizontalAlignment = Enum.HorizontalAlignment.Center, SortOrder = Enum.SortOrder.LayoutOrder})
		toastHolders[gui] = holder
	end
	local t = make("ImageLabel", holder, {Image = img("toast"), Size = UDim2.fromOffset(320, 64), ImageTransparency = 1, Name = "Toast"})
	slice(t, "toast")
	pad(t, 0.05, 0.05, 0.14, 0.18)
	local l
	if opts.icon then
		Kit.icon(t, opts.icon, {anchor = Vector2.new(0, 0.5), position = UDim2.fromScale(0, 0.5), size = UDim2.fromScale(0.14, 1)})
		l = Kit.label(t, text, {anchor = Vector2.new(1, 0.5), position = UDim2.fromScale(1, 0.5), size = UDim2.fromScale(0.84, 1), align = Enum.TextXAlignment.Left, maxSize = 22})
	else
		l = Kit.label(t, text, {maxSize = 22})
	end
	l.TextTransparency = 1
	TweenService:Create(t, SLIDE, {ImageTransparency = 0}):Play()
	TweenService:Create(l, SLIDE, {TextTransparency = 0}):Play()
	task.delay(opts.duration or 2.5, function()
		if t.Parent == nil then return end
		TweenService:Create(t, SLIDE, {ImageTransparency = 1}):Play()
		local fade = TweenService:Create(l, SLIDE, {TextTransparency = 1})
		fade:Play()
		fade.Completed:Wait()
		t:Destroy()
	end)
	return t
end

-- A tooltip shown on hover and on gamepad selection.
function Kit.tooltip(target, text, opts)
	opts = opts or {}
	local tip = make("ImageLabel", target, {Image = img("tooltip"), AnchorPoint = Vector2.new(0.5, 1), Position = UDim2.new(0.5, 0, 0, -6), Size = opts.size or UDim2.fromOffset(200, 60), Visible = false, ZIndex = target.ZIndex + 10, Name = "Tooltip"})
	slice(tip, "tooltip")
	pad(tip, 0.06, 0.06, 0.12, 0.12)
	Kit.label(tip, text, {wrap = true, maxSize = 20, zIndex = target.ZIndex + 11})
	target.MouseEnter:Connect(function() tip.Visible = true end)
	target.MouseLeave:Connect(function() tip.Visible = false end)
	target.SelectionGained:Connect(function() tip.Visible = true end)
	target.SelectionLost:Connect(function() tip.Visible = false end)
	return tip
end

-- Reward pop-up: spinning light rays and a glow behind the item, a ribbon title and a claim button.
-- Returns {Frame, Close}. The reward itself must already be granted by the server.
function Kit.reward(gui, opts)
	opts = opts or {}
	local holder = make("Frame", gui, {Size = UDim2.fromScale(1, 1), BackgroundTransparency = 0.45, BackgroundColor3 = Color3.new(0, 0, 0), ZIndex = 50, Name = "Reward"})
	holder.BackgroundTransparency = 0.45
	local rays = make("ImageLabel", holder, {Image = img("rays"), ImageColor3 = opts.rayColor or Kit.Theme.Accent, AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.45), Size = UDim2.fromOffset(420, 420), ScaleType = Enum.ScaleType.Fit, ZIndex = 51, Name = "Rays"})
	make("ImageLabel", holder, {Image = img("glow"), ImageColor3 = opts.rayColor or Kit.Theme.Accent, AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.45), Size = UDim2.fromOffset(300, 300), ScaleType = Enum.ScaleType.Fit, ZIndex = 52, Name = "Glow"})
	local slot = Kit.slot(holder, {rarity = opts.rarity or "legendary", icon = opts.icon or "gift", anchor = Vector2.new(0.5, 0.5), position = UDim2.fromScale(0.5, 0.45), size = UDim2.fromOffset(150, 150), zIndex = 53})
	slot.ZIndex = 53
	local title = make("ImageLabel", holder, {Image = img("ribbon"), AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.2), Size = UDim2.fromOffset(380, 70), ZIndex = 54, Name = "Title"})
	slice(title, "ribbon")
	pad(title, 0.16, 0.16, 0.16, 0.3)
	Kit.label(title, opts.title or "YOU GOT", {maxSize = 32, zIndex = 55})
	Kit.label(holder, opts.text or "", {anchor = Vector2.new(0.5, 0.5), position = UDim2.fromScale(0.5, 0.66), size = UDim2.fromOffset(420, 44), maxSize = 34, zIndex = 55})
	local r = {}
	local spinning = true
	r.Frame = holder
	r.Close = function()
		spinning = false
		holder:Destroy()
		if opts.onClose then opts.onClose() end
	end
	local claim = Kit.button(holder, {text = opts.button or "CLAIM", variant = "success", anchor = Vector2.new(0.5, 0.5), position = UDim2.fromScale(0.5, 0.8), size = UDim2.fromOffset(220, 74), onClick = r.Close})
	claim.ZIndex = 55
	local pop = make("UIScale", slot, {Scale = 0.2})
	TweenService:Create(pop, POP, {Scale = 1}):Play()
	task.spawn(function()
		while spinning and rays.Parent do
			rays.Rotation = (rays.Rotation + 0.6) % 360
			task.wait()
		end
	end)
	return r
end

-- Name tag and health bar over a character or part. Returns the BillboardGui, its name label and set(health 0..1).
function Kit.billboard(adornee, opts)
	opts = opts or {}
	local b = Instance.new("BillboardGui")
	b.Name = "ForgeTag"
	b.Adornee = adornee
	b.Size = UDim2.fromOffset(opts.width or 180, opts.showHealth == false and 34 or 56)
	b.StudsOffset = opts.offset or Vector3.new(0, 3, 0)
	b.AlwaysOnTop = opts.alwaysOnTop == true
	b.MaxDistance = opts.maxDistance or 80
	b.LightInfluence = 0
	b.ResetOnSpawn = false
	local name = Kit.label(b, opts.text or adornee.Name, {size = UDim2.new(1, 0, 0, 30), maxSize = 26})
	local set = nil
	if opts.showHealth ~= false then
		local _, setter = Kit.bar(b, {kind = "hp", value = opts.health or 1, position = UDim2.fromOffset(0, 32), size = UDim2.new(1, 0, 0, 20)})
		set = setter
	end
	b.Parent = opts.parent or adornee
	return b, name, set
end

-- Loading screen over everything; pass a backdrop asset id from Forge backdrop. Returns {Frame, Set(progress), Finish()}.
function Kit.loading(gui, opts)
	opts = opts or {}
	local f = make("ImageLabel", gui, {Size = UDim2.fromScale(1, 1), Image = opts.backdrop or "", ScaleType = Enum.ScaleType.Crop, BackgroundTransparency = 0, BackgroundColor3 = Color3.fromRGB(16, 18, 26), ZIndex = 100, Name = "Loading"})
	f.BackgroundTransparency = opts.backdrop and 1 or 0
	local title = Kit.label(f, opts.title or "LOADING", {anchor = Vector2.new(0.5, 0.5), position = UDim2.fromScale(0.5, 0.42), size = UDim2.fromScale(0.6, 0.12), maxSize = 64, zIndex = 101})
	local _, set = Kit.bar(f, {kind = "progress", value = 0, anchor = Vector2.new(0.5, 0.5), position = UDim2.fromScale(0.5, 0.58), size = UDim2.fromOffset(420, 34), showText = true, zIndex = 101})
	local l = {Frame = f, Title = title, Set = set}
	l.Finish = function()
		local fade = TweenService:Create(f, SLIDE, {ImageTransparency = 1, BackgroundTransparency = 1})
		fade:Play()
		fade.Completed:Wait()
		f:Destroy()
	end
	return l
end

function Kit.divider(parent, opts)
	opts = opts or {}
	local d = make("ImageLabel", parent, {Image = img("divider"), Size = UDim2.new(1, 0, 0, 6), Name = "Divider"})
	place(d, opts)
	slice(d, "divider")
	return d
end

return Kit
'''

VFX_LUAU = r'''-- ForgeVFX: particle presets for Multi-Script Forge VFX textures.
-- ModuleScript in ReplicatedStorage; call it on the client for cosmetic effects after the server decides the outcome.
local Debris = game:GetService("Debris")

local VFX = {}
VFX.Textures = __TEXTURES__
VFX.Presets = __PRESETS__

local pool = {}

local function seq(points)
	local kps = {}
	for _, p in ipairs(points) do
		table.insert(kps, NumberSequenceKeypoint.new(p[1], p[2]))
	end
	return NumberSequence.new(kps)
end

local function colors(c)
	if typeof(c) == "Color3" then return ColorSequence.new(c) end
	if typeof(c) == "ColorSequence" then return c end
	if type(c) == "string" then return ColorSequence.new(Color3.fromHex(c)) end
	if #c == 1 then return ColorSequence.new(Color3.fromHex(c[1])) end
	local kps = {}
	for i, hex in ipairs(c) do
		table.insert(kps, ColorSequenceKeypoint.new((i - 1) / (#c - 1), Color3.fromHex(hex)))
	end
	return ColorSequence.new(kps)
end

local function range(r)
	return NumberRange.new(r[1], r[2])
end

local function configure(e, name, color, sizeScale)
	local p = VFX.Presets[name]
	assert(p, "ForgeVFX: unknown preset " .. tostring(name))
	e.Name = name
	e.Texture = VFX.Textures[p.Texture] or ""
	e.Color = colors(color or p.Color)
	e.LightEmission = p.LightEmission or 0
	e.LightInfluence = (p.LightEmission or 0) > 0 and 0 or 1
	e.Lifetime = range(p.Lifetime)
	e.Speed = range(p.Speed)
	local size = p.Size
	if sizeScale and sizeScale ~= 1 then
		size = {}
		for i, k in ipairs(p.Size) do
			size[i] = {k[1], k[2] * sizeScale}
		end
	end
	e.Size = seq(size)
	e.Transparency = seq(p.Transparency)
	e.SpreadAngle = p.Spread and Vector2.new(p.Spread[1], p.Spread[2]) or Vector2.zero
	e.Rotation = p.Rotation and range(p.Rotation) or NumberRange.new(0)
	e.RotSpeed = p.RotSpeed and range(p.RotSpeed) or NumberRange.new(0)
	e.Drag = p.Drag or 0
	e.Acceleration = p.Acceleration and Vector3.new(p.Acceleration[1], p.Acceleration[2], p.Acceleration[3]) or Vector3.zero
	e.Orientation = Enum.ParticleOrientation[p.Orientation or "FacingCamera"]
	if p.Flipbook then
		e.FlipbookLayout = Enum.ParticleFlipbookLayout[p.Flipbook[1]]
		e.FlipbookMode = Enum.ParticleFlipbookMode[p.Flipbook[2]]
		if p.Framerate then e.FlipbookFramerate = range(p.Framerate) end
	else
		e.FlipbookLayout = Enum.ParticleFlipbookLayout.None
	end
	e.Rate = p.Rate or 0
	e.Enabled = false
	return p
end

-- Creates a configured ParticleEmitter under parent (an Attachment or BasePart).
function VFX.emitter(parent, name, color, sizeScale)
	local e = Instance.new("ParticleEmitter")
	local p = configure(e, name, color, sizeScale)
	e.Enabled = p.Rate ~= nil
	e.Parent = parent
	return e
end

-- One-shot effect at a world position. Attachments are pooled, so frequent hits stay cheap.
function VFX.burst(position, name, color, count, sizeScale)
	local p = VFX.Presets[name]
	assert(p, "ForgeVFX: unknown preset " .. tostring(name))
	local entry = table.remove(pool)
	if entry == nil then
		local att = Instance.new("Attachment")
		att.Name = "ForgeBurst"
		local emitter = Instance.new("ParticleEmitter")
		emitter.Parent = att
		entry = {att = att, emitter = emitter}
	end
	configure(entry.emitter, name, color, sizeScale)
	entry.att.Parent = workspace.Terrain
	entry.att.WorldPosition = position
	entry.emitter:Emit(count or p.Emit or 10)
	task.delay(p.Lifetime[2] + 0.2, function()
		entry.emitter:Clear()
		entry.att.Parent = nil
		if #pool < 32 then
			table.insert(pool, entry)
		else
			entry.att:Destroy()
		end
	end)
	return entry.emitter
end

-- Several presets at once, for example VFX.combo(pos, {"burst_glow", "hit_sparks", "impact_ring"}).
function VFX.combo(position, names, color, sizeScale)
	for _, n in ipairs(names) do
		VFX.burst(position, n, color, nil, sizeScale)
	end
end

-- Continuous effect on a part (aura, fire, heal). Returns the emitter.
function VFX.attach(part, name, color, sizeScale)
	local att = Instance.new("Attachment")
	att.Name = "ForgeVFX_" .. name
	att.Parent = part
	local e = VFX.emitter(att, name, color, sizeScale)
	if e.Rate == 0 then e.Rate = 10 end
	e.Enabled = true
	return e
end

-- Stops a looping effect and removes it once its last particles fade.
function VFX.stop(emitter)
	if emitter == nil or emitter.Parent == nil then return end
	emitter.Enabled = false
	Debris:AddItem(emitter.Parent, emitter.Lifetime.Max + 0.2)
end

-- Sword or projectile trail between two attachments on the same part.
function VFX.trail(att0, att1, textureKey, color)
	local t = Instance.new("Trail")
	t.Attachment0 = att0
	t.Attachment1 = att1
	t.Texture = VFX.Textures[textureKey or "trail"] or ""
	t.Color = colors(color or "#ffffff")
	t.LightEmission = 1
	t.Lifetime = 0.22
	t.Transparency = seq({{0, 0.1}, {1, 1}})
	t.WidthScale = seq({{0, 1}, {1, 0}})
	t.FaceCamera = true
	t.Parent = att0.Parent
	return t
end

-- Beam (laser, lightning, chain) between two attachments.
function VFX.beam(att0, att1, textureKey, color, width)
	local b = Instance.new("Beam")
	b.Attachment0 = att0
	b.Attachment1 = att1
	b.Texture = VFX.Textures[textureKey or "beam_energy"] or ""
	b.Color = colors(color or "#9fdcff")
	b.LightEmission = 1
	b.TextureMode = Enum.TextureMode.Wrap
	b.TextureSpeed = 2
	b.TextureLength = 4
	b.Width0 = width or 1
	b.Width1 = width or 1
	b.FaceCamera = true
	b.Parent = att0.Parent
	return b
end

return VFX
'''
