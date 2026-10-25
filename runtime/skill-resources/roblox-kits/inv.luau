-- inventory grid UI
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: inventory grid. Toggle with the bag button or the G key; shows the player's Backpack tools.
local Players = game:GetService("Players")
local UIS = game:GetService("UserInputService")
local player = Players.LocalPlayer
local gui = script.Parent
local win = gui:WaitForChild("Inventory")
local grid = win:WaitForChild("Grid")
local function refresh()
	for _, s in ipairs(grid:GetChildren()) do
		local l = s:FindFirstChild("Label")
		if l then l.Text = "" end
	end
	local i = 0
	for _, tool in ipairs(player:WaitForChild("Backpack"):GetChildren()) do
		i += 1
		local slot = grid:FindFirstChild("Slot" .. i)
		if slot and slot:FindFirstChild("Label") then slot.Label.Text = tool.Name end
	end
end
gui:WaitForChild("BagButton").Activated:Connect(function() win.Visible = not win.Visible refresh() end)
win:WaitForChild("Close").Activated:Connect(function() win.Visible = false end)
UIS.InputBegan:Connect(function(input, processed)
	if not processed and input.KeyCode == Enum.KeyCode.G then win.Visible = not win.Visible refresh() end
end)
player:WaitForChild("Backpack").ChildAdded:Connect(refresh)
