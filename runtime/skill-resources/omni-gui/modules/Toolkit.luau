--!nonstrict
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Adapted OMNI UI/VFX primitives. Require is inert; create only requested work.
local Maid = require(script.Parent.Maid)
local Tokens = require(script.Parent.Tokens)
local TweenService = game:GetService("TweenService")
local GuiService = game:GetService("GuiService")
local Toolkit = {}; Toolkit.__index = Toolkit
local function corner(parent, radius)
 local item = Instance.new("UICorner"); item.CornerRadius = radius; item.Parent = parent
end
local function stroke(parent, color, width)
 local item = Instance.new("UIStroke"); item.Color = color; item.Thickness = width or 1; item.Parent = parent
end
function Toolkit.new(parent, options)
 options = options or {}
 assert(typeof(parent) == "Instance", "Explicit GUI parent required")
 local maid = Maid.new()
 local gui = Instance.new("ScreenGui"); gui.Name = options.name or "MultiScriptOmniUI"
 gui.ResetOnSpawn = options.resetOnSpawn == true; gui.IgnoreGuiInset = false
 gui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling; gui.DisplayOrder = options.displayOrder or 10
 gui:SetAttribute("MultiScriptOmni", "6.50.0"); gui.Parent = parent
 maid:GiveTask(gui)
 return setmetatable({Gui = gui, Maid = maid, ReducedMotion = options.reducedMotion == true, _destroyed = false}, Toolkit)
end
function Toolkit:Panel(parent, options)
 options = options or {}; assert(not self._destroyed, "UI destroyed")
 local panel = Instance.new("Frame"); panel.Name = options.name or "Panel"
 panel.Size = options.size or UDim2.fromOffset(400, 300); panel.Position = options.position or UDim2.new()
 panel.BackgroundColor3 = options.color or Tokens.Colors.Surface; panel.BorderSizePixel = 0
 corner(panel, options.radius or Tokens.Radii.Panel); stroke(panel, Tokens.Colors.Stroke, options.strokeWidth)
 local padding = Instance.new("UIPadding"); local amount = options.padding or Tokens.Spacing.PanelPadding
 padding.PaddingLeft = UDim.new(0, amount); padding.PaddingRight = padding.PaddingLeft
 padding.PaddingTop = padding.PaddingLeft; padding.PaddingBottom = padding.PaddingLeft; padding.Parent = panel
 panel.Parent = parent or self.Gui
 return panel
end
function Toolkit:Button(parent, options)
 options = options or {}; assert(not self._destroyed, "UI destroyed")
 local button = Instance.new("TextButton"); button.Name = options.name or "Button"
 button.Size = options.size or UDim2.fromOffset(160, 44); button.Position = options.position or UDim2.new()
 button.Text = tostring(options.text or "Button"); button.Font = Enum.Font.GothamBold
 button.TextSize = Tokens.Type.Body; button.TextWrapped = true; button.TextColor3 = Tokens.Colors.TextPrimary
 button.BackgroundColor3 = options.color or Tokens.Colors.Primary; button.BorderSizePixel = 0
 button.AutoButtonColor = false; button.Selectable = options.disabled ~= true
 button.Active = options.disabled ~= true; button.BackgroundTransparency = options.disabled and 0.5 or 0
 corner(button, Tokens.Radii.Button); stroke(button, Tokens.Colors.Stroke)
 local scale = Instance.new("UIScale"); scale.Parent = button
 local animation
 local function feedback(target)
  if animation then animation:Cancel(); animation:Destroy(); animation = nil end
  if self.ReducedMotion then scale.Scale = 1; return end
  animation = TweenService:Create(scale, TweenInfo.new(Tokens.Motion.HoverDuration), {Scale = target}); animation:Play()
 end
 local owned = Maid.LinkToInstance(button); self.Maid:GiveTask(owned)
 owned:GiveTask(function() if animation then animation:Cancel(); animation:Destroy() end end)
 if not options.disabled then
  owned:GiveTask(button.MouseEnter:Connect(function() feedback(Tokens.Motion.HoverScale) end))
  owned:GiveTask(button.MouseLeave:Connect(function() feedback(1) end))
  owned:GiveTask(button.SelectionGained:Connect(function() feedback(Tokens.Motion.HoverScale) end))
  owned:GiveTask(button.SelectionLost:Connect(function() feedback(1) end))
  owned:GiveTask(button.Activated:Connect(function(...) if options.onActivated then options.onActivated(...) end end))
 end
 button.Parent = parent or self.Gui
 return button
end
function Toolkit:Modal(options)
 options = options or {}; assert(not self._destroyed, "UI destroyed")
 local layer = Instance.new("Frame"); layer.Name = options.name or "ModalLayer"; layer.Size = UDim2.fromScale(1, 1)
 layer.BackgroundColor3 = Color3.new(); layer.BackgroundTransparency = 0.5; layer.Visible = false
 layer.ZIndex = options.zIndex or 100; layer.Parent = self.Gui
 local blocker = Instance.new("TextButton"); blocker.Name = "Backdrop"; blocker.Size = UDim2.fromScale(1, 1)
 blocker.BackgroundTransparency = 1; blocker.Text = ""; blocker.AutoButtonColor = false; blocker.Selectable = false
 blocker.ZIndex = layer.ZIndex; blocker.Parent = layer
 local panel = self:Panel(layer, {name = "Content", size = options.size or UDim2.fromScale(0.85, 0.7)})
 panel.AnchorPoint = Vector2.new(0.5, 0.5); panel.Position = UDim2.fromScale(0.5, 0.5); panel.ZIndex = layer.ZIndex + 1
 local limit = Instance.new("UISizeConstraint"); limit.MaxSize = options.maxSize or Vector2.new(680, 600); limit.Parent = panel
 local focus = nil; local handle = {Layer = layer, Content = panel}
 function handle:Open(firstControl)
  if layer.Visible then return end
  focus = GuiService.SelectedObject; layer.Visible = true
  if firstControl then assert(firstControl:IsDescendantOf(panel), "Modal focus must belong to content"); GuiService.SelectedObject = firstControl end
 end
 function handle:Close()
  if not layer.Visible then return end
  layer.Visible = false
  if GuiService.SelectedObject and GuiService.SelectedObject:IsDescendantOf(layer) then
   GuiService.SelectedObject = focus and focus.Parent and focus or nil
  end
 end
 self.Maid:GiveTask(blocker.Activated:Connect(function() if options.closeOnBackdrop ~= false then handle:Close() end end))
 self.Maid:GiveTask(function() handle:Close() end)
 return handle
end
function Toolkit:Progress(parent, options)
 options = options or {}
 local track = self:Panel(parent, {name = options.name or "Progress", size = options.size or UDim2.fromOffset(240, 20), padding = 0})
 track.ClipsDescendants = true
 local fill = Instance.new("Frame"); fill.Name = "Fill"; fill.BackgroundColor3 = options.color or Tokens.Colors.Primary
 fill.BorderSizePixel = 0; fill.Parent = track
 local handle = {Track = track}
 function handle:Set(value)
  assert(type(value) == "number" and value == value, "Numeric progress required")
  fill.Size = UDim2.fromScale(math.clamp(value, 0, 1), 1)
 end
 handle:Set(options.value or 0); return handle
end
function Toolkit:Destroy()
 if self._destroyed then return end
 self._destroyed = true; self.Maid:Destroy()
end
-- Explicit, finite cosmetic bursts only. The caller supplies a verified texture
-- or uses Roblox's documented built-in sparkles. No damage/remotes are created.
function Toolkit.Burst(parent, options)
 options = options or {}; assert(parent:IsA("BasePart") or parent:IsA("Attachment"), "Burst parent must be a part or attachment")
 local tier = options.quality or "Medium"; local factors = {Low = 0.5, Medium = 1, High = 1.5}
 assert(factors[tier], "Unknown quality tier")
 local count = math.clamp(math.floor((options.count or 20) * factors[tier]), 0, 200)
 local lifetime = math.clamp(options.lifetime or 0.6, 0.05, 5)
 local maid = Maid.new(); local emitter = Instance.new("ParticleEmitter")
 emitter.Texture = options.texture or "rbxasset://textures/particles/sparkles_main.dds"
 emitter.Rate = 0; emitter.Enabled = false; emitter.Lifetime = NumberRange.new(lifetime * 0.5, lifetime)
 emitter.Speed = NumberRange.new(options.speed or 8); emitter.SpreadAngle = Vector2.new(35, 35)
 emitter.Color = ColorSequence.new(options.color or Color3.new(1, 1, 1)); emitter.Parent = parent
 maid:GiveTask(emitter); emitter:Emit(count)
 maid:GiveTask(task.delay(lifetime + 0.1, function() maid:Destroy() end))
 return maid
end
return Toolkit
