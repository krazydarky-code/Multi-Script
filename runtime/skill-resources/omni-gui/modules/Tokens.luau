--!strict
-- OMNI-GUI Unified Design Tokens
-- THE ONLY PLACE COLORS/RADII/MOTION/VFX PARAMS LIVE
-- All other modules import from here

export type TokenTable = {
	Structure: StructureTokens,
	Colors: ColorTokens,
	Radii: RadiiTokens,
	Spacing: SpacingTokens,
	Type: TypeTokens,
	Motion: MotionTokens,
	VFX: VFXTokens,
	Animation: AnimationTokens,
}

export type StructureTokens = {
	StrokeWeight: number,
	CornerRadius: UDim,
	ShadowOffset: Vector2,
	PanelPadding: number,
	ElementGap: number,
	TouchTarget: number,
}

export type ColorTokens = {
	Background: Color3,
	Surface: Color3,
	SurfaceRaised: Color3,
	Primary: Color3,
	Secondary: Color3,
	Accent: Color3,
	TextPrimary: Color3,
	TextSecondary: Color3,
	Stroke: Color3,
	Success: Color3,
	Warning: Color3,
	Danger: Color3,
	Disabled: Color3,
}

export type RadiiTokens = {
	Small: UDim,
	Medium: UDim,
	Large: UDim,
	Panel: UDim,
	Button: UDim,
	Card: UDim,
}

export type SpacingTokens = {
	Tiny: number,
	Small: number,
	Medium: number,
	Large: number,
	Huge: number,
	PanelPadding: number,
	ElementGap: number,
	SectionGap: number,
}

export type TypeTokens = {
	FontFamily: string,
	FontFamilyBold: string,
	FontFamilyMono: string,
	Title: number,
	Heading: number,
	Body: number,
	Small: number,
	Numeric: number,
	Micro: number,
	Weights: { [string]: number },
	LetterSpacing: { [string]: number },
	StrokeWidth: number,
	StrokeColor: Color3,
}

export type MotionTokens = {
	HoverDuration: number,
	HoverScale: number,
	PressDuration: number,
	PressScale: number,
	PanelOpenDuration: number,
	PanelOpenEase: Enum.EasingStyle,
	PanelCloseDuration: number,
	PanelCloseEase: Enum.EasingStyle,
	StaggerDelay: number,
	ToastDuration: number,
	ToastSlideDuration: number,
	LoadingPulseDuration: number,
	ReducedMotion: {
		HoverDuration: number,
		HoverScale: number,
		PressDuration: number,
		PressScale: number,
		PanelOpenDuration: number,
		PanelCloseDuration: number,
		StaggerDelay: number,
	},
}

export type VFXTokens = {
	DefaultLifetime: number,
	QualityTiers: { [string]: number },
	LightEmission: { [string]: number },
	TextureMap: { [string]: string },
	Palette: {
		Core: Color3,
		Edge: Color3,
		Smoke: Color3,
		Glow: Color3,
	},
}

export type AnimationTokens = {
	DefaultFade: number,
	PriorityMap: { [string]: Enum.AnimationPriority },
	LocomotionSpeeds: { [string]: number },
	IKSmoothTime: number,
	CombatStyle: string,
}

-- Base structure tokens (theme-independent)
local Structure: StructureTokens = {
	StrokeWeight = 5,
	CornerRadius = UDim.new(0, 10),
	ShadowOffset = Vector2.new(0, 7),
	PanelPadding = 12,
	ElementGap = 8,
	TouchTarget = 88, -- px at 1280x720 reference
}

-- Theme-resolved at runtime by ThemeRegistry
local Colors: ColorTokens = {
	Background = Color3.fromRGB(13, 13, 13),
	Surface = Color3.fromRGB(26, 26, 26),
	SurfaceRaised = Color3.fromRGB(36, 36, 36),
	Primary = Color3.fromRGB(0, 212, 255),
	Secondary = Color3.fromRGB(102, 102, 102),
	Accent = Color3.fromRGB(255, 215, 0),
	TextPrimary = Color3.fromRGB(255, 255, 255),
	TextSecondary = Color3.fromRGB(170, 170, 170),
	Stroke = Color3.fromRGB(51, 51, 51),
	Success = Color3.fromRGB(0, 255, 136),
	Warning = Color3.fromRGB(255, 184, 0),
	Danger = Color3.fromRGB(255, 51, 51),
	Disabled = Color3.fromRGB(68, 68, 68),
}

local Radii: RadiiTokens = {
	Small = UDim.new(0, 4),
	Medium = UDim.new(0, 8),
	Large = UDim.new(0, 16),
	Panel = UDim.new(0, 8),
	Button = UDim.new(0, 8),
	Card = UDim.new(0, 12),
}

local Spacing: SpacingTokens = {
	Tiny = 4,
	Small = 8,
	Medium = 12,
	Large = 20,
	Huge = 28,
	PanelPadding = 12,
	ElementGap = 8,
	SectionGap = 24,
}

local Type: TypeTokens = {
	FontFamily = "Gotham",
	FontFamilyBold = "GothamBold",
	FontFamilyMono = "RobotoMono",
	Title = 28,
	Heading = 22,
	Body = 16,
	Small = 13,
	Numeric = 18,
	Micro = 11,
	Weights = { Regular = 400, Medium = 500, Bold = 700 },
	LetterSpacing = { Normal = 0, Wide = 0.5, Tight = -0.3 },
	StrokeWidth = 1,
	StrokeColor = Color3.fromRGB(0, 0, 0),
}

local Motion: MotionTokens = {
	HoverDuration = 0.10,
	HoverScale = 1.02,
	PressDuration = 0.06,
	PressScale = 0.98,
	PanelOpenDuration = 0.18,
	PanelOpenEase = Enum.EasingStyle.Quart,
	PanelCloseDuration = 0.15,
	PanelCloseEase = Enum.EasingStyle.Quart,
	StaggerDelay = 0.03,
	ToastDuration = 3.0,
	ToastSlideDuration = 0.25,
	LoadingPulseDuration = 1.2,
	ReducedMotion = {
		HoverDuration = 0.01,
		HoverScale = 1.0,
		PressDuration = 0.01,
		PressScale = 1.0,
		PanelOpenDuration = 0.05,
		PanelCloseDuration = 0.05,
		StaggerDelay = 0,
	},
}

local VFX: VFXTokens = {
	DefaultLifetime = 1.5,
	QualityTiers = { Low = 0.5, Medium = 1.0, High = 1.5 },
	LightEmission = { Glow = 0.7, Normal = 0.3, Subtle = 0.1 },
	TextureMap = {
		Spark = "rbxasset://textures/particles/sparkles_main.dds",
		Fire = "rbxasset://textures/particles/fire_main.dds",
		Smoke = "rbxasset://textures/particles/smoke_main.dds",
		Explosion = "rbxasset://textures/explosion.png",
		SharpSpark = "",
		SlashCrescent = "",
		IceShard = "",
		Lightning = "",
	},
	Palette = {
		Core = Color3.fromRGB(255, 255, 255),
		Edge = Color3.fromRGB(136, 204, 255),
		Smoke = Color3.fromRGB(51, 51, 51),
		Glow = Color3.fromRGB(255, 255, 0),
	},
}

local Animation: AnimationTokens = {
	DefaultFade = 0.15,
	PriorityMap = {
		Idle = Enum.AnimationPriority.Idle,
		Walk = Enum.AnimationPriority.Movement,
		Run = Enum.AnimationPriority.Movement,
		Sprint = Enum.AnimationPriority.Action,
		Jump = Enum.AnimationPriority.Movement,
		Fall = Enum.AnimationPriority.Movement,
		LightAttack = Enum.AnimationPriority.Action,
		HeavyAttack = Enum.AnimationPriority.Action2,
		Ultimate = Enum.AnimationPriority.Action3,
		HitReact = Enum.AnimationPriority.Action3,
		Knockdown = Enum.AnimationPriority.Action3,
		Stagger = Enum.AnimationPriority.Action3,
		Parry = Enum.AnimationPriority.Action4,
		Cinematic = Enum.AnimationPriority.Action4,
		UI_Modal = Enum.AnimationPriority.Action,
		UI_Toast = Enum.AnimationPriority.Idle,
		UI_Transition = Enum.AnimationPriority.Idle,
		Equip = Enum.AnimationPriority.Action,
		Unequip = Enum.AnimationPriority.Action,
		Emote = Enum.AnimationPriority.Action2,
	},
	LocomotionSpeeds = { Walk = 8, Run = 16, Sprint = 24 },
	IKSmoothTime = 0.08,
	CombatStyle = "balanced",
}

local Tokens: TokenTable = {
	Structure = Structure,
	Colors = Colors,
	Radii = Radii,
	Spacing = Spacing,
	Type = Type,
	Motion = Motion,
	VFX = VFX,
	Animation = Animation,
}

local function deepCopy(value)
 if type(value) ~= "table" then return value end
 local result = {}
 for key, item in pairs(value) do result[key] = deepCopy(item) end
 return result
end
local defaults = deepCopy(Tokens)

-- Runtime mutation functions (called by ThemeRegistry)
function Tokens.ApplyTheme(theme: TokenTable)
	for key, value in pairs(theme) do
		if Tokens[key] and type(value) == "table" then
			for k, v in pairs(value) do
				Tokens[key][k] = v
			end
		end
	end
end

function Tokens.ResetToDefaults()
 for key, value in pairs(defaults) do Tokens[key] = deepCopy(value) end
end

function Tokens.GetColor(role: string): Color3
	return Tokens.Colors[role] or Tokens.Colors.TextPrimary
end

function Tokens.GetRadius(role: string): UDim
	return Tokens.Radii[role] or Tokens.Radii.Medium
end

function Tokens.GetSpacing(role: string): number
	return Tokens.Spacing[role] or Tokens.Spacing.Medium
end

function Tokens.GetMotion(role: string): any
	return Tokens.Motion[role]
end

function Tokens.GetVFXTexture(name: string): string
	return Tokens.VFX.TextureMap[name] or Tokens.VFX.TextureMap.Spark
end

function Tokens.GetAnimationPriority(action: string): Enum.AnimationPriority
	return Tokens.Animation.PriorityMap[action] or Enum.AnimationPriority.Action
end

return Tokens