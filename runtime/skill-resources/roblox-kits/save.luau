-- leaderstats DataStore save and load with retries, autosave, BindToClose
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: leaderstats that SAVE (DataStore with retries, autosave and BindToClose).
local Players = game:GetService("Players")
local DSS = game:GetService("DataStoreService")
local store = DSS:GetDataStore({{STORE}})
local STATS = {{STATS}}
local function retry(fn)
	for i = 1, 3 do
		local ok, res = pcall(fn)
		if ok then return true, res end
		warn("DataStore attempt " .. i .. " failed: " .. tostring(res))
		task.wait(i)
	end
	return false
end
local function load(player)
	local ls = Instance.new("Folder")
	ls.Name = "leaderstats"
	for name, start in pairs(STATS) do
		local v = Instance.new("IntValue")
		v.Name = name
		v.Value = start
		v.Parent = ls
	end
	ls.Parent = player
	local ok, data = retry(function() return store:GetAsync("p_" .. player.UserId) end)
	if ok and type(data) == "table" then
		for name, val in pairs(data) do
			local v = ls:FindFirstChild(name)
			if v and type(val) == "number" then v.Value = val end
		end
	end
	player:SetAttribute("DataLoaded", ok)
end
local function save(player)
	if not player:GetAttribute("DataLoaded") then return end -- never overwrite with defaults after a failed load
	local ls = player:FindFirstChild("leaderstats")
	if not ls then return end
	local data = {}
	for _, v in ipairs(ls:GetChildren()) do if v:IsA("IntValue") or v:IsA("NumberValue") then data[v.Name] = v.Value end end
	retry(function() store:SetAsync("p_" .. player.UserId, data) end)
end
Players.PlayerAdded:Connect(load)
Players.PlayerRemoving:Connect(save)
for _, p in ipairs(Players:GetPlayers()) do task.spawn(load, p) end
game:BindToClose(function()
	for _, p in ipairs(Players:GetPlayers()) do save(p) end
end)
task.spawn(function()
	while true do
		task.wait(120)
		for _, p in ipairs(Players:GetPlayers()) do save(p) end
	end
end)
