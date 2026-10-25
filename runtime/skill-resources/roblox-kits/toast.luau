-- toast notifications
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: notifications. Server: Remotes.Notify:FireClient(player, "text", "good"|"warn"|"bad"|"info").
local RS = game:GetService("ReplicatedStorage")
local TweenService = game:GetService("TweenService")
local notify = RS:WaitForChild("Remotes"):WaitForChild("Notify")
local gui = script.Parent
local stack = gui:WaitForChild("Stack")
local template = stack:WaitForChild("Template")
template.Visible = false
local COLORS = {{COLORS}}
local n = 0
notify.OnClientEvent:Connect(function(text, kind)
	n += 1
	local t = template:Clone()
	t.Name = "Toast" .. n
	t.LayoutOrder = n
	t.Text.Text = tostring(text)
	t.Bar.BackgroundColor3 = COLORS[kind] or COLORS.info
	t.Position = UDim2.new(1.2, 0, 0, 0)
	t.Visible = true
	t.Parent = stack
	local s = Instance.new("UIScale")
	s.Scale = 0.6
	s.Parent = t
	TweenService:Create(s, TweenInfo.new(0.3, Enum.EasingStyle.Back), { Scale = 1 }):Play()
	task.delay(4, function()
		TweenService:Create(s, TweenInfo.new(0.25), { Scale = 0 }):Play()
		task.wait(0.25)
		t:Destroy()
	end)
end)
