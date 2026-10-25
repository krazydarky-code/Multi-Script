-- daily reward server
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: daily reward (server). One claim per 24 h, stored in a DataStore, amount decided by the server.
local RS = game:GetService("ReplicatedStorage")
local DSS = game:GetService("DataStoreService")
local store = DSS:GetDataStore("DailyReward_v1")
local claim = RS:WaitForChild("Remotes"):WaitForChild("DailyReward")
local AMOUNT, CURRENCY = {{AMOUNT}}, {{CURRENCY}}
local busy = {}
claim.OnServerInvoke = function(player)
	if busy[player] then return false, "Please wait" end
	busy[player] = true
	local key = "u_" .. player.UserId
	local ok, last = pcall(function() return store:GetAsync(key) end)
	local result, text = false, "Try again later"
	if ok then
		local now = os.time()
		if type(last) == "number" and now - last < 86400 then
			local h = math.ceil((86400 - (now - last)) / 3600)
			text = "Come back in " .. h .. " h"
		else
			local saved = pcall(function() store:SetAsync(key, now) end)
			local ls = player:FindFirstChild("leaderstats")
			local cur = ls and ls:FindFirstChild(CURRENCY)
			if saved and cur then
				cur.Value += AMOUNT
				result, text = true, "+" .. AMOUNT .. " " .. CURRENCY .. "!"
			end
		end
	end
	busy[player] = nil
	return result, text
end
