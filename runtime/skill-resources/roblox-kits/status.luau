-- status effects display
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: round status bar (shows ReplicatedStorage.RoundStatus).
local RS = game:GetService("ReplicatedStorage")
local label = script.Parent:WaitForChild("Status"):WaitForChild("Text")
local v = RS:WaitForChild("RoundStatus", 60)
if not v then return end
local function show() label.Text = v.Value end
v.Changed:Connect(show)
show()
