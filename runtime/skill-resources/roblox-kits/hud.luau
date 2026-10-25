-- stat and health HUD
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: HUD — coins counter bound to leaderstats (with a bump on change) + health bar bound to the Humanoid.
local Players = game:GetService("Players")
local TweenService = game:GetService("TweenService")
local player = Players.LocalPlayer
local gui = script.Parent
local coins = gui:WaitForChild("Coins")
local coinsLabel = coins:WaitForChild("Amount")
local bar = gui:WaitForChild("Health"):WaitForChild("Fill")
local STAT = {{STAT}}
local function short(n)
	if n >= 1e9 then return string.format("%.1fB", n / 1e9) elseif n >= 1e6 then return string.format("%.1fM", n / 1e6) elseif n >= 1e4 then return string.format("%.1fK", n / 1e3) end
	return tostring(n)
end
local function bindStat()
	local ls = player:WaitForChild("leaderstats", 30)
	local v = ls and ls:WaitForChild(STAT, 30)
	if not v then return end
	local scale = coins:FindFirstChild("Bump") or Instance.new("UIScale")
	scale.Name = "Bump"
	scale.Parent = coins
	local function show()
		coinsLabel.Text = short(tonumber(v.Value) or 0)
		scale.Scale = 1.12
		TweenService:Create(scale, TweenInfo.new(0.25, Enum.EasingStyle.Back), { Scale = 1 }):Play()
	end
	v.Changed:Connect(show)
	show()
end
task.spawn(bindStat)
local function bindHealth(char)
	local hum = char:WaitForChild("Humanoid")
	local function upd()
		TweenService:Create(bar, TweenInfo.new(0.2), { Size = UDim2.new(math.clamp(hum.Health / hum.MaxHealth, 0, 1), 0, 1, 0) }):Play()
	end
	hum.HealthChanged:Connect(upd)
	upd()
end
if player.Character then bindHealth(player.Character) end
player.CharacterAdded:Connect(bindHealth)
