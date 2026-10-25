-- dialog box UI
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: dialog box. Server: Remotes.ShowDialog:FireClient(player, "Speaker", {"line 1", "line 2"}).
local RS = game:GetService("ReplicatedStorage")
local show = RS:WaitForChild("Remotes"):WaitForChild("ShowDialog")
local gui = script.Parent
local box = gui:WaitForChild("Dialog")
local nameL, textL, nextB = box:WaitForChild("Speaker"), box:WaitForChild("Text"), box:WaitForChild("Next")
local queue, typing = {}, false
local function typeLine(line)
	typing = true
	for i = 1, #line do
		textL.Text = string.sub(line, 1, i)
		task.wait(0.02)
		if not typing then textL.Text = line break end
	end
	typing = false
end
local function nextLine()
	if typing then typing = false return end
	local line = table.remove(queue, 1)
	if not line then box.Visible = false return end
	task.spawn(typeLine, line)
end
show.OnClientEvent:Connect(function(speaker, lines)
	if type(lines) ~= "table" then return end
	local l = nameL:FindFirstChild("Label")
	if l then l.Text = tostring(speaker) else nameL.Text = tostring(speaker) end
	queue = table.clone(lines)
	box.Visible = true
	nextLine()
end)
nextB.Activated:Connect(nextLine)
