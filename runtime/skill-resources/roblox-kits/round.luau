-- lobby and arena round loop with winner reward
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: round system. Lobby → intermission → teleport to the arena → timer → back to lobby.
-- ReplicatedStorage.RoundStatus (StringValue) is shown by the timer_bar UI kit.
local Players = game:GetService("Players")
local RS = game:GetService("ReplicatedStorage")
local INTERMISSION, ROUND, MIN_PLAYERS = {{INTERMISSION}}, {{ROUND}}, {{MIN}}
local model = script.Parent
local lobby, arena = model:WaitForChild("LobbySpawn"), model:WaitForChild("ArenaFloor")
local status = RS:FindFirstChild("RoundStatus") or Instance.new("StringValue")
status.Name = "RoundStatus"
status.Parent = RS
local function alive(p)
	local h = p.Character and p.Character:FindFirstChildOfClass("Humanoid")
	return h and h.Health > 0
end
while true do
	while #Players:GetPlayers() < MIN_PLAYERS do
		status.Value = "Waiting for players (" .. #Players:GetPlayers() .. "/" .. MIN_PLAYERS .. ")"
		task.wait(1)
	end
	for t = INTERMISSION, 1, -1 do
		status.Value = "Round starts in " .. t
		task.wait(1)
	end
	local playing = {}
	for i, p in ipairs(Players:GetPlayers()) do
		if alive(p) then
			table.insert(playing, p)
			local a = (i / #Players:GetPlayers()) * math.pi * 2
			p.Character:PivotTo(arena.CFrame * CFrame.new(math.cos(a) * 12, 4, math.sin(a) * 12))
		end
	end
	for t = ROUND, 1, -1 do
		local left = {}
		for _, p in ipairs(playing) do if p.Parent and alive(p) then table.insert(left, p) end end
		playing = left
		status.Value = "Time left: " .. t .. "  ·  alive: " .. #playing
		if #playing <= 1 and MIN_PLAYERS > 1 then break end
		task.wait(1)
	end
	status.Value = (#playing == 1) and (playing[1].Name .. " wins!") or "Round over"
	for _, p in ipairs(playing) do
		local ls = p:FindFirstChild("leaderstats")
		local w = ls and ls:FindFirstChild("Wins")
		if w then w.Value += 1 end
		if p.Character then p.Character:PivotTo(lobby.CFrame + Vector3.new(0, 4, 0)) end
	end
	task.wait(3)
end
