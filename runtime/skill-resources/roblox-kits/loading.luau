-- loading screen
-- Source: Brickwire (MIT). Adapt to the project; {{KEY}} placeholders are option values to replace. Not tested in real Studio.
-- Brickwire kit: loading screen. Waits for the game to load (max 8 s), animates the bar + percent, then fades out.
local ContentProvider = game:GetService("ContentProvider")
local TweenService = game:GetService("TweenService")
local gui = script.Parent
local screen = gui:WaitForChild("Loading")
local bar = screen:WaitForChild("Bar")
local fill = bar:WaitForChild("Fill")
local pct = bar:FindFirstChild("Label")
screen.Visible = true
local function set(a)
	fill.Size = UDim2.new(a, 0, 1, 0)
	if pct then pct.Text = math.floor(a * 100) .. "%" end
end
local start = os.clock()
while not game:IsLoaded() and os.clock() - start < 8 do
	set(math.min(0.9, (os.clock() - start) / 8))
	task.wait(0.1)
end
pcall(function() ContentProvider:PreloadAsync({ workspace }) end)
set(1)
task.wait(0.3)
for _, d in ipairs(screen:GetDescendants()) do
	if d:IsA("GuiObject") then TweenService:Create(d, TweenInfo.new(0.5), { BackgroundTransparency = 1 }):Play() end
	if d:IsA("TextLabel") then TweenService:Create(d, TweenInfo.new(0.5), { TextTransparency = 1 }):Play() end
end
TweenService:Create(screen, TweenInfo.new(0.6), { BackgroundTransparency = 1 }):Play()
task.wait(0.6)
screen.Visible = false
