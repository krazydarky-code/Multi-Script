-- settings panel
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: settings panel. Toggles are stored as player attributes (Setting_<Name>) — read them in your scripts.
local Players = game:GetService("Players")
local Lighting = game:GetService("Lighting")
local player = Players.LocalPlayer
local gui = script.Parent
local win = gui:WaitForChild("Settings")
win:WaitForChild("Close").Activated:Connect(function() win.Visible = false end)
gui:WaitForChild("SettingsButton").Activated:Connect(function() win.Visible = not win.Visible end)
for _, row in ipairs(win:WaitForChild("Rows"):GetChildren()) do
	local t = row:FindFirstChild("Toggle")
	if t then
		local key = "Setting_" .. row.Name
		local on = row:GetAttribute("Default") ~= false
		local function show()
			t:SetAttribute("On", on) -- UIJuice animates the knob + colour
			player:SetAttribute(key, on)
			if row.Name == "Shadows" then Lighting.GlobalShadows = on end
		end
		t.Activated:Connect(function() on = not on show() end)
		show()
	end
end
