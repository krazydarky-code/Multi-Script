-- shop server purchase handler
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: shop (server). Validates EVERYTHING: item exists, player can afford it, not owned yet.
local RS = game:GetService("ReplicatedStorage")
local buy = RS:WaitForChild("Remotes"):WaitForChild("ShopBuy")
local ITEMS = {{ITEMS}} -- id = {price, stat}
local CURRENCY = {{CURRENCY}}
buy.OnServerInvoke = function(player, itemId)
	if typeof(itemId) ~= "string" then return false, "Bad request" end
	local item = ITEMS[itemId]
	if not item then return false, "Unknown item" end
	local ls = player:FindFirstChild("leaderstats")
	local money = ls and ls:FindFirstChild(CURRENCY)
	if not money then return false, "No " .. CURRENCY end
	local owned = player:FindFirstChild("Owned") or Instance.new("Folder")
	owned.Name = "Owned"
	owned.Parent = player
	if owned:FindFirstChild(itemId) then return false, "Already owned" end
	if money.Value < item.price then return false, "Not enough " .. CURRENCY end
	money.Value -= item.price
	local flag = Instance.new("BoolValue")
	flag.Name = itemId
	flag.Parent = owned
	return true, "Bought " .. itemId .. "!"
end
