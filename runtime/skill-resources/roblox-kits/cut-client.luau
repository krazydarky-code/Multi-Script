-- cutscene client player
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire cutscene client (StarterPlayerScripts): plays every scene the server sends — case, egg, dice, event, story.
-- Look: Cutscene.defaultStyle = "animedice" | "clean". The dice ROLL / AUTO buttons appear when this script has attribute DiceUI = true.
local Players = game:GetService("Players")
local RS = game:GetService("ReplicatedStorage")
local Cutscene = require(RS:WaitForChild("BrickwireCutscene"))
Cutscene.defaultStyle = {{STYLE}}
local player = Players.LocalPlayer
local auto, busy = false, false
local autoBtn
local function roll()
	if busy then return end
	busy = true
	Cutscene.request("roll")
	task.delay(8, function() busy = false end)
end
local handlers = {}
function handlers.dice(data)
	data.opts = data.opts or {}
	data.opts.auto = auto
	data.opts.rollAgain = roll
	data.opts.onDone = function()
		busy = false
		if auto then task.delay(0.2, roll) end
	end
	local ok, err = pcall(Cutscene.run, "dice", data)
	if not ok then busy = false warn("dice: " .. tostring(err)) end
end
Cutscene.listen(handlers)
if script:GetAttribute("DiceUI") then
	local gui = Instance.new("ScreenGui")
	gui.Name = "BrickwireDiceUI"
	gui.ResetOnSpawn = false
	local function button(name, label, color, x, w)
		local b = Instance.new("TextButton")
		b.Name = name
		b.Text = label
		b.Font = Enum.Font.FredokaOne
		b.TextScaled = true
		b.TextColor3 = Color3.new(1, 1, 1)
		b.BackgroundColor3 = Color3.fromHex(color)
		b.AnchorPoint = Vector2.new(0.5, 1)
		b.Position = UDim2.new(x, 0, 1, -24)
		b.Size = UDim2.new(w, 0, 0.09, 0)
		local c = Instance.new("UICorner")
		c.CornerRadius = UDim.new(0.3, 0)
		c.Parent = b
		local s = Instance.new("UIStroke")
		s.Thickness = 3
		s.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
		s.Parent = b
		local ts = Instance.new("UIStroke")
		ts.Thickness = 2.5
		ts.Parent = b
		local lim = Instance.new("UISizeConstraint")
		lim.MinSize = Vector2.new(110, 46)
		lim.Parent = b
		b.Parent = gui
		return b
	end
	local rollBtn = button("Roll", "ROLL", "#7B4DFF", 0.5, 0.16)
	autoBtn = button("Auto", "AUTO: OFF", "#3A3A4A", 0.66, 0.12)
	rollBtn.Activated:Connect(roll)
	autoBtn.Activated:Connect(function()
		auto = not auto
		autoBtn.Text = auto and "AUTO: ON" or "AUTO: OFF"
		autoBtn.BackgroundColor3 = Color3.fromHex(auto and "#3CCB4A" or "#3A3A4A")
		if auto then roll() end
	end)
	gui.Parent = player:WaitForChild("PlayerGui")
end
