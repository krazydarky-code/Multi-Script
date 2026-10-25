-- NPC dialog with ProximityPrompt and UI
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: NPC dialog. ProximityPrompt → server sends lines to the client (DialogUI kit shows them).
local RS = game:GetService("ReplicatedStorage")
local remotes = RS:WaitForChild("Remotes")
local show = remotes:WaitForChild("ShowDialog")
local npc = script.Parent
local prompt = npc:FindFirstChildWhichIsA("ProximityPrompt", true)
local LINES = {{LINES}}
prompt.Triggered:Connect(function(player)
	show:FireClient(player, npc.Name, LINES)
end)
