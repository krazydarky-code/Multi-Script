-- character aura
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: player aura — every character gets a glowing particle aura.
local Players = game:GetService("Players")
local COLOR = Color3.fromHex({{COLOR}})
local function add(char)
	local root = char:WaitForChild("HumanoidRootPart", 10)
	if not root or root:FindFirstChild("BW_Aura") then return end
	local att = Instance.new("Attachment")
	att.Name = "BW_Aura"
	att.Parent = root
	local e = Instance.new("ParticleEmitter")
	e.Texture = "rbxasset://textures/particles/sparkles_main.dds"
	e.Color = ColorSequence.new(COLOR)
	e.LightEmission = 1
	e.Size = NumberSequence.new(0.6, 0)
	e.Lifetime = NumberRange.new(0.8, 1.4)
	e.Rate = 25
	e.Speed = NumberRange.new(0.5, 1.5)
	e.SpreadAngle = Vector2.new(180, 180)
	e.Parent = att
end
Players.PlayerAdded:Connect(function(p) p.CharacterAdded:Connect(add) end)
for _, p in ipairs(Players:GetPlayers()) do
	if p.Character then add(p.Character) end
	p.CharacterAdded:Connect(add)
end
