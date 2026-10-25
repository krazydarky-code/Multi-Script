-- cutscene server head (server-side roll)
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
local Players = game:GetService("Players")
local RS = game:GetService("ReplicatedStorage")
local Cutscene = require(RS:WaitForChild("BrickwireCutscene"))
local function find(path)
	local cur = game
	for seg in string.gmatch(path, "[^%.]+") do
		if cur == game and seg == "Workspace" then cur = workspace else cur = cur and cur:WaitForChild(seg, 20) end
	end
	return cur ~= game and cur or nil
end
local PRICE, CURRENCY = {{PRICE}}, {{CURRENCY}}
-- pays PRICE of leaderstats[CURRENCY] (free when PRICE = 0 or the stat does not exist)
local function pay(player)
	if PRICE <= 0 then return true end
	local ls = player:FindFirstChild("leaderstats")
	local stat = ls and ls:FindFirstChild(CURRENCY)
	if not stat then return true end
	if stat.Value < PRICE then return false end
	stat.Value -= PRICE
	return true
end
-- gives the reward (Inventory folder of StringValues; plug in your own inventory / DataStore here)
local function grant(player, item)
	local inv = player:FindFirstChild("Inventory")
	if not inv then
		inv = Instance.new("Folder")
		inv.Name = "Inventory"
		inv.Parent = player
	end
	local v = Instance.new("StringValue")
	v.Name = (item.mutation and (item.mutation .. " ") or "") .. item.name
	v.Value = item.rarity
	v.Parent = inv
end
local busy = setmetatable({}, { __mode = "k" })
