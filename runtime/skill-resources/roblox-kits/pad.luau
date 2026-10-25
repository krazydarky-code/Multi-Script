-- jump / speed pad
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: pads. JumpPad = launch up, SpeedPad = temporary speed boost.
local Players = game:GetService("Players")
local pad = script.Parent
local KIND, POWER, BOOST, TIME = {{KIND}}, {{POWER}}, {{BOOST}}, {{TIME}}
local cooldown = {}
pad.Touched:Connect(function(hit)
	local char = hit.Parent
	local hum = char and char:FindFirstChildOfClass("Humanoid")
	local root = char and char:FindFirstChild("HumanoidRootPart")
	if not (hum and root) or cooldown[char] then return end
	cooldown[char] = true
	if KIND == "jump" then
		root.AssemblyLinearVelocity = Vector3.new(root.AssemblyLinearVelocity.X, POWER, root.AssemblyLinearVelocity.Z)
	else
		local normal = hum:GetAttribute("BaseSpeed") or hum.WalkSpeed
		hum:SetAttribute("BaseSpeed", normal)
		hum.WalkSpeed = BOOST
		task.delay(TIME, function() if hum.Parent then hum.WalkSpeed = normal end end)
	end
	task.delay(0.6, function() cooldown[char] = nil end)
end)
