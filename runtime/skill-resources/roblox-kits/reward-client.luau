-- daily reward client
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: daily reward (client).
local RS = game:GetService("ReplicatedStorage")
local claim = RS:WaitForChild("Remotes"):WaitForChild("DailyReward")
local gui = script.Parent
local win = gui:WaitForChild("Reward")
gui:WaitForChild("GiftButton").Activated:Connect(function() win.Visible = not win.Visible end)
win:WaitForChild("Close").Activated:Connect(function() win.Visible = false end)
win:WaitForChild("Claim").Activated:Connect(function()
	local ok, text = claim:InvokeServer()
	win.Info.Text = text
end)
