--!strict
-- Purchases: the one ProcessReceipt for the game, idempotent, plus cached game pass ownership.
-- ModuleScript in ServerScriptService; require it once from a server Script. Needs PlayerData.
-- A developer product is granted at most once per receipt, and only reported as granted after the
-- grant is saved, so a crash or a retry can never double-grant or lose a purchase.
--
--   local Purchases = require(ServerScriptService.Purchases)
--   Purchases.product(123456, function(player, data) data.Coins += 500 end)
--   Purchases.gamePass(654321, function(player) -- give the pass perk (runs on join and on purchase)
--   end)
--   if Purchases.ownsPass(player, 654321) then ... end
local MarketplaceService = game:GetService("MarketplaceService")
local Players = game:GetService("Players")
local ServerScriptService = game:GetService("ServerScriptService")

local PlayerData = require(ServerScriptService:WaitForChild("PlayerData"))

local MAX_RECEIPTS_KEPT = 50

local Purchases = {}
local productHandlers: {[number]: (Player, any) -> ()} = {}
local passHandlers: {[number]: (Player) -> ()} = {}
local passCache: {[Player]: {[number]: boolean}} = {}

-- grant(player, data) changes the player's data; it must not yield.
function Purchases.product(productId: number, grant: (Player, any) -> ())
	productHandlers[productId] = grant
end

function Purchases.gamePass(passId: number, onOwned: (Player) -> ())
	passHandlers[passId] = onOwned
	for _, player in ipairs(Players:GetPlayers()) do
		task.spawn(function()
			if Purchases.ownsPass(player, passId) then
				onOwned(player)
			end
		end)
	end
end

function Purchases.ownsPass(player: Player, passId: number): boolean
	local cache = passCache[player]
	if cache == nil then
		cache = {}
		passCache[player] = cache
	end
	if cache[passId] ~= nil then
		return cache[passId]
	end
	local ok, owns = pcall(MarketplaceService.UserOwnsGamePassAsync, MarketplaceService, player.UserId, passId)
	if ok then
		cache[passId] = owns == true
		return owns == true
	end
	return false -- unknown right now; do not cache a failure
end

local function processReceipt(receipt: any): Enum.ProductPurchaseDecision
	local player = Players:GetPlayerByUserId(receipt.PlayerId)
	if player == nil then
		return Enum.ProductPurchaseDecision.NotProcessedYet -- Roblox retries when they rejoin
	end
	local data = PlayerData.waitFor(player, 15)
	if data == nil then
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end
	local history: {string} = data.Purchases
	if table.find(history, receipt.PurchaseId) then
		return Enum.ProductPurchaseDecision.PurchaseGranted -- already granted earlier
	end
	local grant = productHandlers[receipt.ProductId]
	if grant == nil then
		warn("Purchases: no handler for product", receipt.ProductId)
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end
	local ok, err = pcall(grant, player, data)
	if not ok then
		warn("Purchases: grant failed", err)
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end
	table.insert(history, receipt.PurchaseId)
	while #history > MAX_RECEIPTS_KEPT do
		table.remove(history, 1)
	end
	if not PlayerData.saveNow(player) then
		-- not saved: undo nothing in memory, but tell Roblox to retry; the receipt id makes the retry a no-op
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end
	return Enum.ProductPurchaseDecision.PurchaseGranted
end

-- Assigned exactly once in the whole game: only the last assignment of ProcessReceipt takes effect.
MarketplaceService.ProcessReceipt = processReceipt

MarketplaceService.PromptGamePassPurchaseFinished:Connect(function(player, passId, purchased)
	if not purchased then
		return
	end
	local cache = passCache[player]
	if cache then
		cache[passId] = true
	end
	local onOwned = passHandlers[passId]
	if onOwned then
		onOwned(player)
	end
end)

Players.PlayerAdded:Connect(function(player)
	for passId, onOwned in pairs(passHandlers) do
		task.spawn(function()
			if Purchases.ownsPass(player, passId) then
				onOwned(player)
			end
		end)
	end
end)

Players.PlayerRemoving:Connect(function(player)
	passCache[player] = nil
end)

return Purchases
