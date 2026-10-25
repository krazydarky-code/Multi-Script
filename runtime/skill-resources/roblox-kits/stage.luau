-- obby stage / checkpoint script
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: obby checkpoints. Every SpawnLocation named StageN in this model is a checkpoint.
local Players = game:GetService("Players")
local model = script.Parent
local stages = {}
for _, d in ipairs(model:GetDescendants()) do
	local n = d:IsA("SpawnLocation") and tonumber(string.match(d.Name, "^Stage(%d+)$"))
	if n then stages[n] = d end
end
local function stat(player)
	local ls = player:FindFirstChild("leaderstats")
	if not ls then
		ls = Instance.new("Folder")
		ls.Name = "leaderstats"
		ls.Parent = player
	end
	local s = ls:FindFirstChild("Stage")
	if not s then
		s = Instance.new("IntValue")
		s.Name = "Stage"
		s.Value = 1
		s.Parent = ls
	end
	return s
end
Players.PlayerAdded:Connect(function(player)
	local s = stat(player)
	player.CharacterAdded:Connect(function(char)
		task.wait()
		local cp = stages[s.Value]
		if cp then char:PivotTo(cp.CFrame + Vector3.new(0, 4, 0)) end
	end)
end)
for n, cp in pairs(stages) do
	cp.Touched:Connect(function(hit)
		local player = Players:GetPlayerFromCharacter(hit.Parent)
		if not player then return end
		local s = stat(player)
		if n == s.Value + 1 then s.Value = n end
	end)
end
