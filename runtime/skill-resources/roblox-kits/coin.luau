-- coins: spin, touch, leaderstats, respawn
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: collectable coins. Every part named Coin* in this model: +VALUE coins, respawns after RESPAWN s.
local Players = game:GetService("Players")
local VALUE, RESPAWN = {{VALUE}}, {{RESPAWN}}
local model = script.Parent
local function coins(player)
	local ls = player:FindFirstChild("leaderstats")
	if not ls then
		ls = Instance.new("Folder")
		ls.Name = "leaderstats"
		ls.Parent = player
	end
	local c = ls:FindFirstChild("Coins")
	if not c then
		c = Instance.new("IntValue")
		c.Name = "Coins"
		c.Parent = ls
	end
	return c
end
Players.PlayerAdded:Connect(coins)
for _, p in ipairs(Players:GetPlayers()) do coins(p) end
for _, coin in ipairs(model:GetChildren()) do
	if coin:IsA("BasePart") and string.find(coin.Name, "^Coin") then
		local taken = false
		coin.Touched:Connect(function(hit)
			if taken then return end
			local player = Players:GetPlayerFromCharacter(hit.Parent)
			if not player then return end
			taken = true
			coins(player).Value += VALUE
			coin.Transparency = 1
			coin.CanTouch = false
			task.delay(RESPAWN, function()
				coin.Transparency = 0
				coin.CanTouch = true
				taken = false
			end)
		end)
	end
end
-- spin (server-side, cheap)
local RunService = game:GetService("RunService")
local angle = 0
RunService.Heartbeat:Connect(function(dt)
	angle = (angle + dt * 120) % 360
	for _, coin in ipairs(model:GetChildren()) do
		if coin:IsA("BasePart") and string.find(coin.Name, "^Coin") then
			local base = coin:GetAttribute("BaseCFrame")
			if not base then
				coin:SetAttribute("BaseCFrame", coin.CFrame)
				base = coin.CFrame
			end
			coin.CFrame = base * CFrame.Angles(0, math.rad(angle), 0)
		end
	end
end)
