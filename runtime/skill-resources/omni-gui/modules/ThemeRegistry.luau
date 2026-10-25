--!nonstrict
-- SPDX-License-Identifier: GPL-3.0-or-later
-- Explicit registration: no global storage searches, remotes or invented themes.
local Tokens = require(script.Parent.Tokens)
local Signal = require(script.Parent.Signal)
local Registry = {OnThemeChanged = Signal.new()}
local themes = {}; local current = nil
local function copy(value)
 if type(value) ~= "table" then return value end
 local result = {}; for key, item in pairs(value) do result[key] = copy(item) end
 return result
end
local function merge(target, source)
 for key, item in pairs(source) do
  if type(item) == "table" and type(target[key]) == "table" then merge(target[key], item) else target[key] = copy(item) end
 end
 return target
end
local neutral = {}
for _, key in ipairs({"Structure", "Colors", "Radii", "Spacing", "Type", "Motion", "VFX", "Animation"}) do neutral[key] = copy(Tokens[key]) end
neutral.name = "neutral"; themes.neutral = neutral
function Registry.Register(name, overrides)
 assert(type(name) == "string" and #name > 0 and type(overrides) == "table", "Theme name and overrides required")
 local theme = merge(copy(neutral), overrides); theme.name = name; themes[name] = theme
 return copy(theme)
end
function Registry.Load(name)
 local theme = copy(themes[name] or themes.neutral)
 current = theme; Tokens.ResetToDefaults(); Tokens.ApplyTheme(theme)
 Registry.OnThemeChanged:Fire(copy(theme)); return copy(theme)
end
function Registry.GetCurrentTheme() return copy(current or themes.neutral) end
function Registry.GetCurrentThemeName() return (current or themes.neutral).name end
function Registry.CreateHybrid(primary, secondary, tertiary, overrides)
 assert(themes[primary], "Register primary theme first")
 local result = copy(themes[primary])
 -- Structural primary stays coherent; accents are deliberately selected fields.
 if secondary then assert(themes[secondary], "Register secondary theme first"); result.Texture = copy(themes[secondary].Texture or {}) end
 if tertiary then assert(themes[tertiary], "Register tertiary theme first"); result.VFX = copy(themes[tertiary].VFX) end
 return Registry.Register(primary .. "_hybrid", merge(result, overrides or {}))
end
return Registry
