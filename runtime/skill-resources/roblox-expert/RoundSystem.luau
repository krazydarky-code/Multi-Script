--!strict
-- RoundSystem: a server-authoritative round loop (Waiting -> Intermission -> Playing -> Ended).
-- ModuleScript in ServerScriptService; start it from a server Script. Clients read the state from
-- attributes on ReplicatedStorage.RoundState (State, TimeLeft, Alive, Winner), so UI never asks the server.
--
--   local Rounds = require(ServerScriptService.RoundSystem)
--   Rounds.start({
--       minPlayers = 2, intermission = 15, roundTime = 120,
--       arenaSpawns = workspace.Arena.Spawns, lobbySpawn = workspace.Lobby.Spawn,
--       onRoundStart = function(players) end,
--       onRoundEnd = function(winners) for _, p in ipairs(winners) do ... end end,
--   })
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

type Config = {
	minPlayers: number?, intermission: number?, roundTime: number?, endScreen: number?,
	arenaSpawns: Instance, lobbySpawn: BasePart,
	onRoundStart: ((players: {Player}) -> ())?, onRoundEnd: ((winners: {Player}) -> ())?,
}

local RoundSystem = {}
local state = ReplicatedStorage:FindFirstChild("RoundState") or Instance.new("Configuration")
state.Name = "RoundState"
state.Parent = ReplicatedStorage

local alive: {[Player]: boolean} = {}
local running = false

local function setState(name: string, timeLeft: number)
	state:SetAttribute("State", name)
	state:SetAttribute("TimeLeft", math.max(0, math.floor(timeLeft)))
end

local function countAlive(): number
	local n = 0
	for player, isAlive in pairs(alive) do
		if isAlive and player.Parent == Players then
			n += 1
		end
	end
	state:SetAttribute("Alive", n)
	return n
end

local function teleport(player: Player, target: BasePart)
	local character = player.Character
	if character and character.PrimaryPart then
		character:PivotTo(target.CFrame + Vector3.new(0, 4, 0))
	end
end

local function countdown(name: string, seconds: number, stopEarly: (() -> boolean)?)
	local endsAt = os.clock() + seconds
	while os.clock() < endsAt do
		setState(name, endsAt - os.clock())
		if stopEarly and stopEarly() then
			return
		end
		task.wait(0.25)
	end
	setState(name, 0)
end

local function playRound(config: Config)
	local spawns = config.arenaSpawns:GetChildren()
	local players = Players:GetPlayers()
	table.clear(alive)
	local connections: {RBXScriptConnection} = {}
	for i, player in ipairs(players) do
		local character = player.Character
		local humanoid = character and character:FindFirstChildOfClass("Humanoid")
		if humanoid and humanoid.Health > 0 then
			alive[player] = true
			local spawnPart = spawns[((i - 1) % #spawns) + 1]
			if spawnPart and spawnPart:IsA("BasePart") then
				teleport(player, spawnPart)
			end
			table.insert(connections, humanoid.Died:Connect(function()
				alive[player] = false
				countAlive()
			end))
		end
	end
	table.insert(connections, Players.PlayerRemoving:Connect(function(player)
		alive[player] = nil
		countAlive()
	end))
	if config.onRoundStart then
		task.spawn(config.onRoundStart, players)
	end
	countAlive()
	countdown("Playing", config.roundTime or 120, function()
		return countAlive() <= 1
	end)
	for _, c in ipairs(connections) do
		c:Disconnect()
	end
	local winners = {}
	for player, isAlive in pairs(alive) do
		if isAlive and player.Parent == Players then
			table.insert(winners, player)
		end
	end
	state:SetAttribute("Winner", if #winners == 1 then winners[1].Name else "")
	if config.onRoundEnd then
		task.spawn(config.onRoundEnd, winners)
	end
	setState("Ended", config.endScreen or 5)
	task.wait(config.endScreen or 5)
	for _, player in ipairs(Players:GetPlayers()) do
		teleport(player, config.lobbySpawn)
	end
	table.clear(alive)
end

function RoundSystem.start(config: Config)
	assert(not running, "RoundSystem already started")
	assert(config.arenaSpawns and config.lobbySpawn, "RoundSystem needs arenaSpawns and lobbySpawn")
	running = true
	task.spawn(function()
		while running do
			if #Players:GetPlayers() < (config.minPlayers or 2) then
				setState("Waiting", 0)
				task.wait(1)
			else
				countdown("Intermission", config.intermission or 15)
				if #Players:GetPlayers() >= (config.minPlayers or 2) then
					local ok, err = pcall(playRound, config)
					if not ok then
						warn("RoundSystem: round failed:", err)
						task.wait(2)
					end
				end
			end
		end
	end)
end

function RoundSystem.stop()
	running = false
end

function RoundSystem.isAlive(player: Player): boolean
	return alive[player] == true
end

return RoundSystem
