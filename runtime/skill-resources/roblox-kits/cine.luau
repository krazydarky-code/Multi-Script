-- cinematic runner
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire cinematic (client). Plays the shot list below with BrickwireCinema. Edit the shots freely —
-- every shot: type, time, fov, ease, roll, cut="fade"; see the header of ReplicatedStorage.BrickwireCinema.
local Players = game:GetService("Players")
local Cinema = require(game:GetService("ReplicatedStorage"):WaitForChild("BrickwireCinema"))
local SHOTS = {{SHOTS}}
local MODE, TRIGGER, ONCE = {{MODE}}, {{TRIGGER}}, {{ONCE}}
local OPTS = { letterbox = {{LETTERBOX}}, skip = {{SKIP}}, fadeIn = 0.8, fadeOut = 0.6, dof = {{DOF}}, loop = MODE == "menu" }
local player = Players.LocalPlayer
if MODE == "join" then
	if not game:IsLoaded() then game.Loaded:Wait() end
	task.wait(1)
	Cinema.play(SHOTS, OPTS)
elseif MODE == "menu" then
	-- background camera for a main menu: loops until something sets the player attribute InMenu = false
	local h = Cinema.play(SHOTS, { letterbox = false, skip = false, loop = true, dof = true })
	player:SetAttribute("InMenu", true)
	player:GetAttributeChangedSignal("InMenu"):Connect(function() if player:GetAttribute("InMenu") == false then h.stop() end end)
elseif MODE == "trigger" then
	local part = game
	for seg in string.gmatch(TRIGGER, "[^%.]+") do
		if part == game and seg == "Workspace" then part = workspace else part = part and part:WaitForChild(seg, 30) end
	end
	if part == game then part = nil end
	local playing, seen = false, false
	if part then
		part.Touched:Connect(function(hit)
			if playing or (ONCE and seen) then return end
			local char = player.Character
			if not char or not hit:IsDescendantOf(char) then return end
			playing, seen = true, true
			Cinema.play(SHOTS, { letterbox = OPTS.letterbox, skip = OPTS.skip, fadeIn = 0.4, fadeOut = 0.4, dof = OPTS.dof, onDone = function() playing = false end })
		end)
	end
end
