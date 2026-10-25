-- cutscene play helper
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire cutscene (client): plays the timeline below with BrickwireCutscene. Events: camera, say/speaker, title/sub,
-- sound/music, vfx/where, tween/goal, shake, flash, fov, blur, color, dim, letterbox, fire — see ReplicatedStorage.BrickwireCutscene.
local Players = game:GetService("Players")
local Cutscene = require(game:GetService("ReplicatedStorage"):WaitForChild("BrickwireCutscene"))
local TIMELINE = {{TIMELINE}}
local MODE, TRIGGER, ONCE = {{MODE}}, {{TRIGGER}}, {{ONCE}}
local player = Players.LocalPlayer
if MODE == "join" then
	if not game:IsLoaded() then game.Loaded:Wait() end
	task.wait(1)
	Cutscene.play(TIMELINE)
elseif MODE == "trigger" then
	local part = Cutscene.resolve(TRIGGER)
	local playing, seen = false, false
	if part then
		part.Touched:Connect(function(hit)
			if playing or (ONCE and seen) then return end
			local char = player.Character
			if not char or not hit:IsDescendantOf(char) then return end
			playing, seen = true, true
			Cutscene.play(TIMELINE, { onDone = function() playing = false end })
		end)
	end
end
