--!strict
-- DailyReward: once-per-UTC-day rewards with a streak, decided on the server. Needs PlayerData
-- (its template has Daily = {Day = 0, Streak = 0}). ModuleScript in ServerScriptService.
--
--   local Daily = require(ServerScriptService.DailyReward)
--   Daily.setRewards({ {Coins = 100}, {Coins = 150}, {Coins = 200}, {Gems = 5}, {Coins = 300}, {Coins = 400}, {Gems = 20} })
--   Remotes.onServer("ClaimDaily", {}, function(player)
--       local ok, day, reward = Daily.claim(player)
--       if ok then Remotes.fire(player, "DailyClaimed", day, reward) end
--   end, {rate = 1, burst = 2})
--   Daily.status(player)  -- {canClaim, streak, nextDay, secondsUntilNext} for the UI
local ServerScriptService = game:GetService("ServerScriptService")
local PlayerData = require(ServerScriptService:WaitForChild("PlayerData"))

local DAY = 86400
local Daily = {}
local rewards: {{[string]: number}} = {{Coins = 100}}

function Daily.setRewards(list: {{[string]: number}})
	assert(#list > 0, "need at least one reward")
	rewards = list
end

local function today(): number
	return math.floor(os.time() / DAY) -- UTC day number from the server clock
end

function Daily.status(player: Player)
	local data = PlayerData.get(player)
	if data == nil then
		return nil
	end
	local d = data.Daily
	local t = today()
	local canClaim = d.Day < t
	local streak = if d.Day == t - 1 or d.Day == t then d.Streak else 0
	return {
		canClaim = canClaim,
		streak = streak,
		nextDay = (streak % #rewards) + 1,
		secondsUntilNext = if canClaim then 0 else (t + 1) * DAY - os.time(),
	}
end

-- Returns ok, the day number in the cycle (1..#rewards) and the reward table.
function Daily.claim(player: Player): (boolean, number?, {[string]: number}?)
	local data = PlayerData.get(player)
	if data == nil then
		return false, nil, nil
	end
	local d = data.Daily
	local t = today()
	if d.Day >= t then
		return false, nil, nil -- already claimed today
	end
	local streak = if d.Day == t - 1 then d.Streak + 1 else 1
	local index = ((streak - 1) % #rewards) + 1
	local reward = rewards[index]
	for currency, amount in pairs(reward) do
		data[currency] = (data[currency] or 0) + amount
	end
	d.Day = t
	d.Streak = streak
	return true, index, reward
end

return Daily
