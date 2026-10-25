-- kill brick touch handler
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: every part named Kill/Lava inside this model kills on touch (debounced per character).
local model = script.Parent
local touched = {}
local function hook(p)
	if not p:IsA("BasePart") then return end
	if not (string.find(p.Name, "^Kill") or string.find(p.Name, "^Lava")) then return end
	p.Touched:Connect(function(hit)
		local hum = hit.Parent and hit.Parent:FindFirstChildOfClass("Humanoid")
		if hum and hum.Health > 0 and not touched[hum] then
			touched[hum] = true
			hum.Health = 0
			task.delay(1, function() touched[hum] = nil end)
		end
	end)
end
for _, d in ipairs(model:GetDescendants()) do hook(d) end
