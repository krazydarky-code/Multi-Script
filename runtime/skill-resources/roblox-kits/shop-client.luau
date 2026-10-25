-- shop client UI
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: shop window (client). Prices live on the SERVER; the client only asks to buy an item id.
local RS = game:GetService("ReplicatedStorage")
local buy = RS:WaitForChild("Remotes"):WaitForChild("ShopBuy")
local gui = script.Parent
local win = gui:WaitForChild("ShopWindow")
local toggle = gui:WaitForChild("ShopButton")
local msg = win:WaitForChild("Message")
toggle.Activated:Connect(function() win.Visible = not win.Visible end)
win:WaitForChild("Close").Activated:Connect(function() win.Visible = false end)
for _, card in ipairs(win:WaitForChild("Grid"):GetChildren()) do
	local b = card:FindFirstChild("Buy")
	if b then
		b.Activated:Connect(function()
			local ok, text = buy:InvokeServer(card.Name)
			msg.Text = text
			msg.TextColor3 = ok and Color3.fromRGB(47, 214, 123) or Color3.fromRGB(255, 92, 108)
		end)
	end
end
