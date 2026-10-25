--!strict
-- Leaderboard: a global top list on an OrderedDataStore with throttled writes, cached reads and names.
-- ModuleScript in ServerScriptService. The top list is published as a JSON attribute on
-- ReplicatedStorage.Leaderboards.<name> so every client UI can read it without a remote.
--
--   local Leaderboard = require(ServerScriptService.Leaderboard)
--   local wins = Leaderboard.new("Wins", function(player) return (PlayerData.get(player) or {}).Wins end, {size = 50})
--   wins:start()
local HttpService = game:GetService("HttpService")
local DataStoreService = game:GetService("DataStoreService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

type Options = {size: number?, refreshSeconds: number?, writeSeconds: number?}

local Leaderboard = {}
Leaderboard.__index = Leaderboard

local nameCache: {[number]: string} = {}
local folder = ReplicatedStorage:FindFirstChild("Leaderboards") or Instance.new("Folder")
folder.Name = "Leaderboards"
folder.Parent = ReplicatedStorage

local function nameOf(userId: number): string
	if nameCache[userId] then
		return nameCache[userId]
	end
	local player = Players:GetPlayerByUserId(userId)
	if player then
		nameCache[userId] = player.Name
		return player.Name
	end
	local ok, name = pcall(Players.GetNameFromUserIdAsync, Players, userId)
	if ok and type(name) == "string" then
		nameCache[userId] = name
		return name
	end
	return "Player"
end

-- valueOf(player) returns the number to rank by (or nil when not loaded).
function Leaderboard.new(name: string, valueOf: (Player) -> number?, options: Options?)
	local opts = options or {}
	local self = setmetatable({}, Leaderboard)
	self.name = name
	self.valueOf = valueOf
	self.size = math.clamp(opts.size or 50, 1, 100)
	self.refreshSeconds = math.max(opts.refreshSeconds or 120, 60)
	self.writeSeconds = math.max(opts.writeSeconds or 180, 60)
	self.store = DataStoreService:GetOrderedDataStore("LB_" .. name)
	self.lastWritten = {} :: {[number]: number}
	self.holder = folder:FindFirstChild(name) or Instance.new("Configuration")
	self.holder.Name = name
	self.holder.Parent = folder
	return self
end

function Leaderboard.write(self: any, player: Player)
	local value = self.valueOf(player)
	if type(value) ~= "number" or value ~= value then
		return
	end
	value = math.floor(math.clamp(value, 0, 2 ^ 52))
	if self.lastWritten[player.UserId] == value then
		return
	end
	local ok, err = pcall(self.store.SetAsync, self.store, tostring(player.UserId), value)
	if ok then
		self.lastWritten[player.UserId] = value
	else
		warn("Leaderboard", self.name, "write failed:", err)
	end
end

function Leaderboard.refresh(self: any)
	local ok, pages = pcall(self.store.GetSortedAsync, self.store, false, self.size)
	if not ok then
		warn("Leaderboard", self.name, "read failed:", pages)
		return
	end
	local rows = {}
	for rank, entry in ipairs(pages:GetCurrentPage()) do
		local userId = tonumber(entry.key)
		if userId then
			table.insert(rows, {rank = rank, userId = userId, name = nameOf(userId), value = entry.value})
		end
	end
	self.holder:SetAttribute("Top", HttpService:JSONEncode(rows))
	self.holder:SetAttribute("Updated", os.time())
end

function Leaderboard.start(self: any)
	task.spawn(function()
		while true do
			for _, player in ipairs(Players:GetPlayers()) do
				self:write(player)
				task.wait(1)
			end
			task.wait(self.writeSeconds)
		end
	end)
	task.spawn(function()
		while true do
			self:refresh()
			task.wait(self.refreshSeconds)
		end
	end)
	Players.PlayerRemoving:Connect(function(player)
		self:write(player)
		self.lastWritten[player.UserId] = nil
	end)
end

return Leaderboard
