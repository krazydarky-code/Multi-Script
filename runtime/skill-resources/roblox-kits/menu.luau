-- main menu
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: main menu. Shown on join with a blurred world; Play hides it.
local Lighting = game:GetService("Lighting")
local TweenService = game:GetService("TweenService")
local gui = script.Parent
local menu = gui:WaitForChild("Menu")
local blur = Instance.new("BlurEffect")
blur.Size = 18
blur.Parent = Lighting
menu.Visible = true
local title = menu:FindFirstChild("GameTitle")
if title then
	task.spawn(function()
		local t = 0
		while menu.Visible and title.Parent do
			t += 0.03
			title.Rotation = math.sin(t * 2) * 2
			task.wait(0.03)
		end
	end)
end
menu:WaitForChild("Buttons"):WaitForChild("Play").Activated:Connect(function()
	TweenService:Create(blur, TweenInfo.new(0.4), { Size = 0 }):Play()
	menu.Visible = false
	game:GetService("Players").LocalPlayer:SetAttribute("InMenu", false) -- stops the menu_camera kit, if any
	task.delay(0.45, function() blur:Destroy() end)
end)
local settings = menu.Buttons:FindFirstChild("Settings")
if settings then
	settings.Activated:Connect(function()
		local s = gui.Parent:FindFirstChild("SettingsUI")
		if s and s:FindFirstChild("Settings") then s.Settings.Visible = true end
	end)
end
local shop = menu.Buttons:FindFirstChild("Shop")
if shop then
	shop.Activated:Connect(function()
		local s = gui.Parent:FindFirstChild("ShopUI")
		if s and s:FindFirstChild("ShopWindow") then menu.Visible = false blur:Destroy() s.ShopWindow.Visible = true end
	end)
end
