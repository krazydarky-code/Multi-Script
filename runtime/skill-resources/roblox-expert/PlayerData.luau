--!strict
-- PlayerData: session-locked player saves with UpdateAsync, retries, migration, autosave and safe shutdown.
-- ModuleScript in ServerScriptService (server only). One server owns a player's data at a time, so two
-- servers can never overwrite each other, and data that failed to load is never saved over the real data.
--
--   local PlayerData = require(ServerScriptService.PlayerData)
--   PlayerData.Loaded:Connect(function(player, data) ... end)   -- fires once the data is ready
--   local data = PlayerData.get(player)                           -- nil until loaded
--   PlayerData.update(player, function(data) data.Coins += 10 end)
--   local saved = PlayerData.saveNow(player)                       -- use before granting paid items
local DataStoreService = game:GetService("DataStoreService")
local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local CONFIG = {
	StoreName = "PlayerData_v1",
	Version = 1,
	AutosaveSeconds = 120,
	StaleLockSeconds = 1800, -- a lock older than this belongs to a crashed server and may be taken over
	LockWaitTries = 6, -- waits for another server that is still saving this player
	Template = {
		Coins = 0,
		Gems = 0,
		Inventory = {},
		Stats = {},
		Purchases = {}, -- receipt ids already granted (used by Purchases)
		Daily = {Day = 0, Streak = 0},
	},
}

type Profile = {Data: any, Key: string, Loaded: boolean, Released: boolean, NoSave: boolean, Saving: boolean}

local PlayerData = {}
local store = DataStoreService:GetDataStore(CONFIG.StoreName)
local SESSION = if game.JobId ~= "" then game.JobId else "studio-" .. HttpService:GenerateGUID(false)
local profiles: {[Player]: Profile} = {}
local loadedEvent = Instance.new("BindableEvent")
PlayerData.Loaded = loadedEvent.Event

-- ------------------------------------------------------------------ helpers
local function deepCopy(value: any): any
	if type(value) ~= "table" then
		return value
	end
	local copy = {}
	for k, v in pairs(value) do
		copy[k] = deepCopy(v)
	end
	return copy
end

-- Adds keys the template has and the saved data lacks (new features), without touching existing values.
local function reconcile(data: any, template: any)
	for key, value in pairs(template) do
		if data[key] == nil then
			data[key] = deepCopy(value)
		elseif type(value) == "table" and type(data[key]) == "table" and next(value) ~= nil then
			reconcile(data[key], value)
		end
	end
end

-- Upgrade old saves here, one version step at a time.
local function migrate(data: any, fromVersion: number): any
	local version = fromVersion
	-- if version < 2 then data.Gems = data.Diamonds or 0; data.Diamonds = nil; version = 2 end
	if version > CONFIG.Version then
		warn("PlayerData: save is from a newer version", version)
	end
	return data
end

local function retry<T>(fn: () -> T, tries: number): (boolean, T?)
	local delay = 0.5
	local lastError: any = nil
	for attempt = 1, tries do
		local ok, result = pcall(fn)
		if ok then
			return true, result
		end
		lastError = result
		if attempt < tries then
			task.wait(delay)
			delay = math.min(delay * 2, 8)
		end
	end
	warn("PlayerData: request failed:", lastError)
	return false, nil
end

local function keyFor(player: Player): string
	return "u_" .. player.UserId
end

-- ------------------------------------------------------------------ load
local function load(player: Player)
	local key = keyFor(player)
	local loadedData: any = nil
	for _ = 1, CONFIG.LockWaitTries do
		local lockedByOther = false
		local ok = retry(function()
			return store:UpdateAsync(key, function(old: any)
				old = old or {}
				local lock = old.Lock
				if lock and lock.Session ~= SESSION and os.time() - (lock.Time or 0) < CONFIG.StaleLockSeconds then
					lockedByOther = true
					return nil -- leave the record alone; the other server is still using it
				end
				old.Lock = {Session = SESSION, Time = os.time()}
				old.Version = old.Version or CONFIG.Version
				loadedData = old
				return old
			end)
		end, 5)
		if not ok then
			break
		end
		if not lockedByOther then
			break
		end
		loadedData = nil
		task.wait(6)
	end

	if player.Parent ~= Players then
		return -- left while loading; the lock expires on its own
	end
	if loadedData == nil then
		if RunService:IsStudio() then
			warn("PlayerData: could not load (is Studio Access to API Services on?). Using temporary data that will not save.")
			local temp = deepCopy(CONFIG.Template)
			profiles[player] = {Data = temp, Key = key, Loaded = true, Released = false, NoSave = true, Saving = false}
			loadedEvent:Fire(player, temp)
			return
		end
		player:Kick("Your data could not be loaded right now. Please rejoin in a moment; nothing was lost.")
		return
	end

	local data = migrate(loadedData.Data or {}, loadedData.Version or CONFIG.Version)
	reconcile(data, CONFIG.Template)
	profiles[player] = {Data = data, Key = key, Loaded = true, Released = false, NoSave = false, Saving = false}
	loadedEvent:Fire(player, data)
end

-- ------------------------------------------------------------------ save
local function save(player: Player, release: boolean): boolean
	local profile = profiles[player]
	if profile == nil or not profile.Loaded or profile.NoSave or profile.Released then
		return profile ~= nil and profile.NoSave
	end
	while profile.Saving do
		task.wait(0.1)
	end
	profile.Saving = true
	local lockLost = false
	local ok = retry(function()
		return store:UpdateAsync(profile.Key, function(old: any)
			old = old or {}
			if old.Lock and old.Lock.Session ~= SESSION then
				lockLost = true
				return nil
			end
			return {
				Data = profile.Data,
				Version = CONFIG.Version,
				Lock = if release then nil else {Session = SESSION, Time = os.time()},
			}
		end)
	end, 5)
	profile.Saving = false
	if release then
		profile.Released = true
	end
	if lockLost then
		warn("PlayerData: another server took over", player.Name, "- this server stops saving them")
		profile.NoSave = true
		if player.Parent == Players then
			player:Kick("You joined from another server.")
		end
		return false
	end
	return ok
end

-- ------------------------------------------------------------------ public API
function PlayerData.get(player: Player): any?
	local p = profiles[player]
	return if p and p.Loaded then p.Data else nil
end

function PlayerData.waitFor(player: Player, timeout: number?): any?
	local deadline = os.clock() + (timeout or 30)
	while player.Parent == Players and os.clock() < deadline do
		local data = PlayerData.get(player)
		if data then
			return data
		end
		task.wait(0.1)
	end
	return nil
end

-- Changes data through one function so every change is in one place. Returns false when not loaded.
function PlayerData.update(player: Player, change: (data: any) -> ()): boolean
	local data = PlayerData.get(player)
	if data == nil then
		return false
	end
	change(data)
	return true
end

-- Saves immediately and returns true only when the save reached the DataStore.
function PlayerData.saveNow(player: Player): boolean
	return save(player, false)
end

-- ------------------------------------------------------------------ lifecycle
Players.PlayerAdded:Connect(load)
for _, player in ipairs(Players:GetPlayers()) do
	task.spawn(load, player)
end

Players.PlayerRemoving:Connect(function(player)
	save(player, true)
	profiles[player] = nil
end)

task.spawn(function()
	while true do
		task.wait(CONFIG.AutosaveSeconds)
		for _, player in ipairs(Players:GetPlayers()) do
			task.spawn(save, player, false)
			task.wait(0.5) -- spread requests out
		end
	end
end)

game:BindToClose(function()
	local pending = 0
	for player in pairs(profiles) do
		pending += 1
		task.spawn(function()
			save(player, true)
			pending -= 1
		end)
	end
	local deadline = os.clock() + 25
	while pending > 0 and os.clock() < deadline do
		task.wait(0.1)
	end
end)

return PlayerData
