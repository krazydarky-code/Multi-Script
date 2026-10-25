-- day and night cycle
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: day/night cycle. One full day = DAY_MINUTES real minutes.
local Lighting = game:GetService("Lighting")
local DAY_MINUTES = {{MINUTES}}
local RunService = game:GetService("RunService")
RunService.Heartbeat:Connect(function(dt)
	Lighting.ClockTime = (Lighting.ClockTime + dt * 24 / (DAY_MINUTES * 60)) % 24
end)
