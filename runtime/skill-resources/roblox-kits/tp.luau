-- linked teleporter pads with cooldown
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: two-way teleporter. Touch PadA → arrive on PadB and back (per-player cooldown).
local Players = game:GetService("Players")
local model = script.Parent
local a, b = model:WaitForChild("PadA"), model:WaitForChild("PadB")
local busy = {}
local function link(from, to)
	from.Touched:Connect(function(hit)
		local player = Players:GetPlayerFromCharacter(hit.Parent)
		if not player or busy[player] then return end
		busy[player] = true
		hit.Parent:PivotTo(to.CFrame + Vector3.new(0, 4, 0))
		task.delay(2, function() busy[player] = nil end)
	end)
end
link(a, b)
link(b, a)
