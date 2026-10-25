--!strict
-- UIController: opens and closes screens one at a time on the client, with gamepad focus, a Back
-- button (B on gamepad, Escape is left to Roblox), open/close animation and input-type awareness.
-- ModuleScript in ReplicatedStorage; use it from LocalScripts only.
--
--   local UI = require(ReplicatedStorage.UIController)
--   UI.register("Shop", shopFrame, {focus = shopFrame.Buy})   -- a GuiObject that starts hidden
--   UI.open("Shop")      -- closes whatever else was open
--   UI.close()           -- closes the current screen
--   UI.toggle("Shop")
--   UI.InputChanged:Connect(function(kind) end)              -- "Gamepad", "Touch" or "KeyboardAndMouse"
local ContextActionService = game:GetService("ContextActionService")
local GuiService = game:GetService("GuiService")
local TweenService = game:GetService("TweenService")
local UserInputService = game:GetService("UserInputService")

type Screen = {frame: GuiObject, focus: GuiObject?, onOpen: (() -> ())?, onClose: (() -> ())?, scale: UIScale}

local UI = {}
local screens: {[string]: Screen} = {}
local current: string? = nil
local OPEN = TweenInfo.new(0.2, Enum.EasingStyle.Back, Enum.EasingDirection.Out)
local CLOSE = TweenInfo.new(0.12, Enum.EasingStyle.Quad, Enum.EasingDirection.In)
local inputChanged = Instance.new("BindableEvent")
UI.InputChanged = inputChanged.Event

local function inputKind(): string
	local last = UserInputService:GetLastInputType()
	if last.Name:find("Gamepad") then
		return "Gamepad"
	elseif last == Enum.UserInputType.Touch then
		return "Touch"
	end
	return "KeyboardAndMouse"
end

local lastKind = inputKind()
UserInputService.LastInputTypeChanged:Connect(function()
	local kind = inputKind()
	if kind ~= lastKind then
		lastKind = kind
		inputChanged:Fire(kind)
		if kind == "Gamepad" and current and screens[current].focus then
			GuiService.SelectedObject = screens[current].focus
		end
	end
end)

function UI.inputKind(): string
	return lastKind
end

function UI.register(name: string, frame: GuiObject, options: {focus: GuiObject?, onOpen: (() -> ())?, onClose: (() -> ())?}?)
	local opts = options or {}
	local scale = frame:FindFirstChildOfClass("UIScale") or Instance.new("UIScale")
	scale.Parent = frame
	frame.Visible = false
	screens[name] = {frame = frame, focus = opts.focus, onOpen = opts.onOpen, onClose = opts.onClose, scale = scale}
end

local function back(_action: string, state: Enum.UserInputState): Enum.ContextActionResult
	if state == Enum.UserInputState.Begin and current then
		UI.close()
		return Enum.ContextActionResult.Sink
	end
	return Enum.ContextActionResult.Pass
end

function UI.close()
	local name = current
	if name == nil then
		return
	end
	local s = screens[name]
	current = nil
	ContextActionService:UnbindAction("UIControllerBack")
	if GuiService.SelectedObject and GuiService.SelectedObject:IsDescendantOf(s.frame) then
		GuiService.SelectedObject = nil
	end
	local tween = TweenService:Create(s.scale, CLOSE, {Scale = 0.85})
	tween:Play()
	tween.Completed:Once(function()
		if current ~= name then
			s.frame.Visible = false
		end
	end)
	if s.onClose then
		task.spawn(s.onClose)
	end
end

function UI.open(name: string)
	local s = screens[name]
	assert(s, "UIController: no screen named " .. name)
	if current == name then
		return
	end
	UI.close()
	current = name
	s.frame.Visible = true
	s.scale.Scale = 0.85
	TweenService:Create(s.scale, OPEN, {Scale = 1}):Play()
	ContextActionService:BindActionAtPriority("UIControllerBack", back, false, Enum.ContextActionPriority.High.Value, Enum.KeyCode.ButtonB)
	if lastKind == "Gamepad" and s.focus then
		GuiService.SelectedObject = s.focus
	end
	if s.onOpen then
		task.spawn(s.onOpen)
	end
end

function UI.toggle(name: string)
	if current == name then
		UI.close()
	else
		UI.open(name)
	end
end

function UI.current(): string?
	return current
end

return UI
