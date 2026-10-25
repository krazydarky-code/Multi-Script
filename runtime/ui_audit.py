# SPDX-License-Identifier: GPL-3.0-or-later
"""Studio UI inspector: measures a real GUI inside Roblox Studio and reports what a player would see wrong.

The bridge runs AUDIT_LUAU through Studio's execute_luau and turns the JSON it returns into findings:
text that does not fit, tiny text, low text contrast, emoji in text, buttons too small to tap,
things off screen or cut off by the screen edge, zero-size objects, empty or non-scrolling lists,
images that did not load, and buttons that overlap each other.
"""
import json, re

AUDIT_LUAU = r'''
local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local StarterGui = game:GetService("StarterGui")
local TARGET, ROOTPATH, MAXN = "__TARGET__", "__ROOT__", 120

local function resolve(path)
	local node = game
	for part in string.gmatch(path, "[^%.]+") do
		if node == game and part == "game" then
			continue
		end
		local child = node:FindFirstChild(part)
		if child == nil and node == game then
			local ok, svc = pcall(function() return game:GetService(part) end)
			if ok then child = svc end
		end
		if child == nil then
			return nil
		end
		node = child
	end
	return node
end

local root
if ROOTPATH ~= "" then
	root = resolve(ROOTPATH)
elseif TARGET == "player" and Players.LocalPlayer then
	root = Players.LocalPlayer:FindFirstChildOfClass("PlayerGui")
else
	root = StarterGui
end
if root == nil then
	return HttpService:JSONEncode({error = "GUI root not found: " .. (ROOTPATH ~= "" and ROOTPATH or TARGET)})
end

local cam = workspace.CurrentCamera
local vp = cam and cam.ViewportSize or Vector2.new(1280, 720)
local findings, counts = {}, {objects = 0, texts = 0, buttons = 0, images = 0, lists = 0}

local function add(sev, obj, msg)
	if #findings < MAXN then
		table.insert(findings, {severity = sev, path = obj:GetFullName(), message = msg})
	end
end

local function shown(obj)
	local o = obj
	while o and o ~= root and o ~= game do
		if o:IsA("GuiObject") and not o.Visible then return false end
		if o:IsA("LayerCollector") and not o.Enabled then return false end
		o = o.Parent
	end
	return true
end

local function lum(c)
	local function ch(v)
		return if v <= 0.04045 then v / 12.92 else ((v + 0.055) / 1.055) ^ 2.4
	end
	return 0.2126 * ch(c.R) + 0.7152 * ch(c.G) + 0.0722 * ch(c.B)
end

local function ratio(a, b)
	local la, lb = lum(a), lum(b)
	if la < lb then la, lb = lb, la end
	return (la + 0.05) / (lb + 0.05)
end

local function backgroundOf(obj)
	local o = obj
	while o and o:IsA("GuiObject") do
		if o.BackgroundTransparency < 0.5 then
			return o.BackgroundColor3
		end
		if (o:IsA("ImageLabel") or o:IsA("ImageButton")) and o.Image ~= "" and o.ImageTransparency < 0.5 then
			return nil -- an image behind the text: colour unknown, judge by eye
		end
		o = o.Parent
	end
	return nil
end

local function hasEmoji(text)
	local ok, result = pcall(function()
		for _, cp in utf8.codes(text) do
			if cp >= 0x1F000 or (cp >= 0x2600 and cp <= 0x27BF) or (cp >= 0x2B00 and cp <= 0x2BFF) or cp == 0xFE0F then
				return true
			end
		end
		return false
	end)
	return ok and result
end

local buttons = {}
for _, obj in ipairs(root:GetDescendants()) do
	if obj:IsA("GuiObject") and shown(obj) then
		counts.objects += 1
		local size, pos = obj.AbsoluteSize, obj.AbsolutePosition
		local hasContent = #obj:GetChildren() > 0 or obj:IsA("TextLabel") or obj:IsA("TextButton") or obj:IsA("ImageLabel") or obj:IsA("ImageButton")
		if (size.X < 1 or size.Y < 1) and hasContent then
			add("warning", obj, "has zero size, so it is invisible")
		elseif pos.X + size.X < 0 or pos.Y + size.Y < 0 or pos.X > vp.X or pos.Y > vp.Y then
			add("error", obj, "is completely off screen")
		elseif pos.X < -4 or pos.Y < -4 or pos.X + size.X > vp.X + 4 or pos.Y + size.Y > vp.Y + 4 then
			add("warning", obj, "is cut off by the edge of the screen")
		end
		if obj:IsA("TextLabel") or obj:IsA("TextButton") or obj:IsA("TextBox") then
			counts.texts += 1
			local text = obj.Text
			if text ~= "" and obj.TextTransparency < 0.9 then
				if not obj.TextFits then
					add("warning", obj, "text does not fit its box (\"" .. string.sub(text, 1, 40) .. "\")")
				end
				if obj.TextBounds.Y > 0 and obj.TextBounds.Y < 11 then
					add("warning", obj, "text is very small (" .. math.floor(obj.TextBounds.Y) .. " px tall); hard to read on phones")
				end
				if hasEmoji(text) then
					add("error", obj, "text contains emoji or symbol characters; use an image icon instead")
				end
				local bg = backgroundOf(obj)
				if bg then
					local r = ratio(obj.TextColor3, bg)
					local stroke = obj:FindFirstChildOfClass("UIStroke")
					if stroke and stroke.Enabled and stroke.Thickness >= 1 and stroke.Transparency < 0.5 then
						r = math.max(r, ratio(obj.TextColor3, stroke.Color))
					end
					if r < 3 then
						add(if r < 2 then "error" else "warning", obj, string.format("text contrast is low (%.1f:1); aim for 4.5:1, or add a dark UIStroke", r))
					end
				end
			end
		end
		if obj:IsA("GuiButton") then
			counts.buttons += 1
			if size.X > 0 and size.Y > 0 and math.min(size.X, size.Y) < 36 then
				add("warning", obj, string.format("button is small to tap (%dx%d px); aim for at least 44 px", size.X, size.Y))
			end
			table.insert(buttons, obj)
		end
		if (obj:IsA("ImageLabel") or obj:IsA("ImageButton")) and obj.Image ~= "" then
			counts.images += 1
			if not obj.IsLoaded then
				add("warning", obj, "image has not loaded (" .. obj.Image .. "); check the id, its moderation and permissions")
			end
		end
		if obj:IsA("ScrollingFrame") then
			counts.lists += 1
			local items = 0
			for _, c in ipairs(obj:GetChildren()) do
				if c:IsA("GuiObject") then items += 1 end
			end
			if items == 0 then
				add("warning", obj, "list is empty; fill it or show an empty-state message")
			elseif obj.AutomaticCanvasSize == Enum.AutomaticSize.None and obj.CanvasSize.Y.Offset == 0 and obj.CanvasSize.Y.Scale <= 1 then
				local layout = obj:FindFirstChildWhichIsA("UIGridStyleLayout")
				if layout and layout.AbsoluteContentSize.Y > obj.AbsoluteSize.Y then
					add("warning", obj, "content is taller than the list but the canvas does not grow; set AutomaticCanvasSize to Y")
				end
			end
		end
	end
end

for i = 1, math.min(#buttons, 200) do
	local a = buttons[i]
	for j = i + 1, math.min(#buttons, 200) do
		local b = buttons[j]
		if not a:IsDescendantOf(b) and not b:IsDescendantOf(a) and a.ZIndex == b.ZIndex then
			local ap, as, bp, bs = a.AbsolutePosition, a.AbsoluteSize, b.AbsolutePosition, b.AbsoluteSize
			local w = math.min(ap.X + as.X, bp.X + bs.X) - math.max(ap.X, bp.X)
			local h = math.min(ap.Y + as.Y, bp.Y + bs.Y) - math.max(ap.Y, bp.Y)
			local smaller = math.min(as.X * as.Y, bs.X * bs.Y)
			if w > 0 and h > 0 and smaller > 0 and w * h > 0.4 * smaller then
				add("warning", a, "overlaps button " .. b:GetFullName() .. "; one of them may be impossible to press")
			end
		end
	end
end

return HttpService:JSONEncode({root = root:GetFullName(), viewport = {vp.X, vp.Y}, counts = counts, findings = findings})
'''

def build_code(target, root):
    target = 'player' if target == 'player' else 'starter'
    root = re.sub(r'[^A-Za-z0-9_. ]', '', str(root or ''))[:200]
    return AUDIT_LUAU.replace('__TARGET__', target).replace('__ROOT__', root)

def parse(text):
    if not isinstance(text, str): return None
    m = re.search(r'\{.*\}', text, re.S)
    if not m: return None
    raw = m.group(0)
    for candidate in (raw, raw.replace('\\"', '"')):
        try: return json.loads(candidate)
        except Exception: pass
    return None

def summarize(result):
    if not isinstance(result, dict):
        return {'ok': False, 'error': 'The audit returned nothing readable. Check that the GUI exists and Studio is in the expected mode.'}
    if result.get('error'): return {'ok': False, 'error': result['error']}
    f = result.get('findings') or []
    counts = {k: sum(1 for x in f if x.get('severity') == k) for k in ('error', 'warning')}
    return {'ok': True, 'root': result.get('root'), 'viewport': result.get('viewport'), 'objects': result.get('counts'),
            'problems': counts, 'clean': not f, 'findings': f,
            'next': ('Fix every error and warning, run the audit again until it is clean, then screen_capture at phone and desktop sizes. '
                     'It cannot judge colours under images, visual style or whether the layout looks good; look at a capture for that.')}
