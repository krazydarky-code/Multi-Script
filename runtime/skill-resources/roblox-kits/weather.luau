-- weather effects
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: weather emitter follows the local camera so it rains/snows everywhere the player looks.
local RunService = game:GetService("RunService")
local part = workspace:WaitForChild({{PART}})
RunService.RenderStepped:Connect(function()
	local cam = workspace.CurrentCamera
	if cam then part.CFrame = CFrame.new(cam.CFrame.Position + Vector3.new(0, 30, 0)) end
end)
