-- UI hover, press and pop animations
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire UI juice: hover/press bounce on buttons (BW_Juice), pop-in for windows (BW_Window), spinning rays (BW_Spin),
-- animated toggles (On attribute), optional click sound (attribute BW_ClickSound = "rbxassetid://…" on the button or the ScreenGui).
local TweenService = game:GetService("TweenService")
local RunService = game:GetService("RunService")
local gui = script.Parent
local function tw(o, t, goal, style, dir)
	TweenService:Create(o, TweenInfo.new(t, style or Enum.EasingStyle.Quad, dir or Enum.EasingDirection.Out), goal):Play()
end
local function scaleOf(o)
	local s = o:FindFirstChild("BW_Scale")
	if not s then
		s = Instance.new("UIScale")
		s.Name = "BW_Scale"
		s.Parent = o
	end
	return s
end
local function click(b)
	local id = b:GetAttribute("BW_ClickSound") or gui:GetAttribute("BW_ClickSound")
	if type(id) ~= "string" or id == "" then return end
	local snd = Instance.new("Sound")
	snd.SoundId = id
	snd.Volume = 0.5
	snd.Parent = gui
	snd:Play()
	game:GetService("Debris"):AddItem(snd, 3)
end
local function toggleLook(b)
	local knob = b:FindFirstChild("Knob")
	if not knob or b:GetAttribute("On") == nil then return end
	local on = b:GetAttribute("On")
	tw(knob, 0.18, { Position = UDim2.new(on and 0.94 or 0.06, 0, 0.5, 0), AnchorPoint = Vector2.new(on and 1 or 0, 0.5) }, Enum.EasingStyle.Back)
	tw(b, 0.18, { BackgroundColor3 = on and Color3.fromRGB(47, 214, 123) or Color3.fromRGB(90, 96, 120) })
end
local function juice(b)
	if not b:IsA("GuiButton") or b:GetAttribute("BW_JuiceOn") then return end
	b:SetAttribute("BW_JuiceOn", true)
	local s = scaleOf(b)
	b.MouseEnter:Connect(function() tw(s, 0.12, { Scale = 1.06 }) end)
	b.MouseLeave:Connect(function() tw(s, 0.12, { Scale = 1 }) end)
	b.MouseButton1Down:Connect(function() tw(s, 0.07, { Scale = 0.92 }) end)
	b.MouseButton1Up:Connect(function() tw(s, 0.25, { Scale = 1 }, Enum.EasingStyle.Back) end)
	b.Activated:Connect(function() click(b) end)
	if b:GetAttribute("On") ~= nil then
		b:GetAttributeChangedSignal("On"):Connect(function() toggleLook(b) end)
	end
end
local function pop(w)
	if not w:IsA("GuiObject") or w:GetAttribute("BW_PopOn") then return end
	w:SetAttribute("BW_PopOn", true)
	local s = scaleOf(w)
	w:GetPropertyChangedSignal("Visible"):Connect(function()
		if w.Visible then
			s.Scale = 0.82
			tw(s, 0.28, { Scale = 1 }, Enum.EasingStyle.Back)
		end
	end)
end
local spinners = {}
local function scan(d)
	if d:GetAttribute("BW_Juice") then juice(d) end
	if d:GetAttribute("BW_Window") then pop(d) end
	if d:GetAttribute("BW_Spin") and d:IsA("GuiObject") then table.insert(spinners, d) end
end
for _, d in ipairs(gui:GetDescendants()) do scan(d) end
gui.DescendantAdded:Connect(scan)
RunService.Heartbeat:Connect(function(dt)
	for _, d in ipairs(spinners) do
		if d.Parent and d.Visible then d.Rotation = (d.Rotation + (d:GetAttribute("BW_Spin") or 0) * dt) % 360 end
	end
end)
