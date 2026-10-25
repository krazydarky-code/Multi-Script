> Adapted reference specification. Pseudocode, illustrative IDs and suggested budgets below are not installed components or verified assets. Use the reviewed modules / Forge where applicable; implement and test missing behavior in the actual project.

# OMNI-GUI Unified UI Recipes

> Merged from ProjectGUI, MultiVFX, and Animation Engineering skills. Each recipe is a parameterized component pattern, not a static copy-paste.

---

## 1. PANEL — Base Container

```lua
-- Creates a themed panel with optional texture overlay
function UIRecipes.Panel(props)
  -- props: { Name, Size, Position, AnchorPoint, Theme, Variant, Texture, Children }
  -- Theme tokens applied: Colors.Surface, Colors.Stroke, Radii.Panel, Spacing.PanelPadding
  -- Variants: "default" | "raised" | "header" | "card" | "modal"
  -- Texture: "stud" | "grain" | "wood" | "metal" | "holographic" | "none"
end
```

**Token Mapping:**
| Prop | Token |
|---|---|
| BackgroundColor3 | Theme.Colors.Surface (or SurfaceRaised for "raised") |
| Border (UIStroke) | Theme.Colors.Stroke, Theme.Radii.Panel, Theme.Spacing.PanelPadding |
| CornerRadius | Theme.Radii.Panel |
| Texture Overlay | Theme.Texture.Panel (type, tile_px, opacity, blend) |

**Variants:**
- `default` — Standard panel
- `raised` — SurfaceRaised + subtle shadow (offset frame)
- `header` — Theme.Colors.Primary background, Theme.Radii.Small
- `card` — Theme.Radii.Card, tighter padding
- `modal` — Theme.Radii.Large, max-width clamp, backdrop

---

## 2. BUTTON — Interactive Control

```lua
function UIRecipes.Button(props)
  -- props: { Name, Text, Icon, Size, Variant, State, OnActivated, Theme }
  -- Variants: "primary" | "secondary" | "destructive" | "ghost" | "icon" | "pill"
  -- States: "default" | "hover" | "press" | "disabled" | "loading"
end
```

**Token Mapping:**
| Prop | Token |
|---|---|
| BackgroundColor3 | Variant → Theme.Colors (Primary/Secondary/Danger/Transparent) |
| TextColor3 | Variant → Contrast color (TextPrimary/TextSecondary/Background) |
| UIStroke | Theme.Colors.Stroke (ghost/secondary) or Variant color |
| CornerRadius | Theme.Radii.Button |
| Size | Theme.Motion.HoverScale/PressScale for state transitions |
| Font | Theme.Type.FontFamilyBold, Theme.Type.Body |

**State Transitions (tweened):**
```lua
hover:  { BackgroundColor3 → lighten(10%), Scale → Theme.Motion.HoverScale, Duration → Theme.Motion.HoverDuration }
press:  { BackgroundColor3 → darken(10%), Scale → Theme.Motion.PressScale, Duration → Theme.Motion.PressDuration }
disabled: { BackgroundTransparency → 0.5, TextTransparency → 0.5, Active → false }
loading:  { Text → "", Spinner visible, AutoButtonColor → false }
```

---

## 3. CARD — Item/Content Display

```lua
function UIRecipes.Card(props)
  -- props: { Name, Layout, Image, Title, Subtitle, Stats, Actions, Rarity, Theme }
  -- Layouts: "grid" (square, image-focused) | "list" (horizontal, info-dense) | "compact" (minimal)
end
```

**Token Mapping:**
| Element | Token |
|---|---|
| Frame | Theme.Colors.Surface, Theme.Radii.Card, Theme.Colors.Stroke |
| Image | Theme.Spacing.ElementGap padding, AspectRatio from Variant |
| Title | Theme.Type.FontFamilyBold, Theme.Type.Heading, Theme.Colors.TextPrimary |
| Subtitle | Theme.Type.FontFamily, Theme.Type.Body, Theme.Colors.TextSecondary |
| Stats | Theme.Type.FontFamilyMono, Theme.Type.Numeric, Theme.Colors.TextPrimary |
| Rarity Badge | Theme.Colors (Success/Warning/Danger/Accent), Theme.Radii.Small |
| Action Buttons | UIRecipes.Button with "primary"/"ghost" variants |

**Rarity Color Mapping (theme-aware):**
```lua
Common    → Theme.Colors.TextSecondary
Uncommon  → Theme.Colors.Success
Rare      → Theme.Colors.Primary
Epic      → Theme.Colors.Accent
Legendary → Theme.Colors.Danger (or custom gradient)
Mythic    → Custom: Theme.Colors.Primary → Theme.Colors.Accent gradient
```

---

## 4. BAR — Progress/Resource Display

```lua
function UIRecipes.Bar(props)
  -- props: { Name, Current, Max, Variant, ShowText, Animated, Theme }
  -- Variants: "health" | "mana" | "stamina" | "xp" | "shield" | "custom"
end
```

**Token Mapping:**
| Prop | Token |
|---|---|
| Background (track) | Variant → Theme.Colors (Surface + variant bg) |
| Fill | Variant → Theme.Colors (Danger/Primary/Warning/Accent) |
| Height | Theme.Spacing.Tiny (4) to Theme.Spacing.Small (8) |
| CornerRadius | Theme.Radii.Small |
| Text (optional) | Theme.Type.FontFamilyMono, Theme.Type.Small, Theme.Colors.TextPrimary |
| Animation | Theme.Motion.PanelOpenDuration, Theme.Motion.PanelOpenEase |

**Behavior:**
- Clamp ratio: `math.clamp(Current/Max, 0, 1)`
- Tween fill width on value change (cancel previous tween)
- Flash on critical (<20%): pulse fill color with Theme.Motion.LoadingPulseDuration

---

## 5. GRID — Repeating Layout

```lua
function UIRecipes.Grid(props)
  -- props: { Name, CellTemplate, Data, Columns, Gap, AspectRatio, Theme }
  -- Auto-calculates cell size from container width / columns - gap
end
```

**Token Mapping:**
| Prop | Token |
|---|---|
| CellPadding | Theme.Spacing.ElementGap |
| CellSize | Calculated or Theme.ComponentOverrides.Grid.default.CellSize |
| MaxColumns | Theme.ComponentOverrides.Grid[Variant].MaxColumns |
| UIGridLayout | FillDirection=Horizontal, HorizontalAlignment=Center, VerticalAlignment=Top |

**Responsive Breakpoints (auto-applied):**
| Viewport Width | Columns (shop) | Columns (inventory) |
|---|---|---|
| ≥1280 | 5 | 8 |
| ≥1024 | 4 | 6 |
| ≥768 | 3 | 5 |
| <768 | 2 | 4 |

---

## 6. TOAST — Transient Notification

```lua
function UIRecipes.Toast(props)
  -- props: { Message, Variant, Duration, Action, Theme }
  -- Variants: "success" | "warning" | "error" | "info" | "custom"
  -- Auto-queued, max 5 visible, slide-in from top-right
end
```

**Token Mapping:**
| Prop | Token |
|---|---|
| Background | Variant → Theme.Colors (Success/Warning/Danger/Primary) |
| Text | Theme.Colors.TextPrimary (or Background for high-contrast variants) |
| CornerRadius | Theme.Radii.Medium |
| Padding | Theme.Spacing.Medium |
| Slide Animation | Theme.Motion.ToastSlideDuration, ExpoOut |
| Auto-dismiss | Theme.Motion.ToastDuration (or Variant override) |
| Icon | Lucide/FontAwesome mapping per variant |

---

## 7. MODAL — Blocking Dialog

```lua
function UIRecipes.Modal(props)
  -- props: { Title, Body, Buttons, Variant, OnClose, Theme }
  -- Variants: "confirm" | "alert" | "prompt" | "custom"
  -- Blocks background input, traps focus, handles Escape/B button
end
```

**Token Mapping:**
| Prop | Token |
|---|---|
| Backdrop | Theme.Colors.Background, Transparency=0.5 (Theme.ComponentOverrides.Modal.default.BackdropTransparency) |
| Panel | Theme.Colors.Surface, Theme.Radii.Large, Theme.Spacing.Large padding |
| Title | Theme.Type.FontFamilyBold, Theme.Type.Heading, Theme.Colors.TextPrimary |
| Body | Theme.Type.FontFamily, Theme.Type.Body, Theme.Colors.TextPrimary |
| Buttons | UIRecipes.Button array, primary action = "primary" variant |
| MaxWidth | Theme.ComponentOverrides.Modal.default.MaxWidth |
| Focus Trap | GuiService.SelectedObject management |

---

## 8. HOTBAR — Ability/Item Slots

```lua
function UIRecipes.Hotbar(props)
  -- props: { Slots, SelectedIndex, OnSlotActivated, Orientation, Theme }
  -- Slots: array of { Icon, Cooldown, Count, Keybind, Enabled }
end
```

**Token Mapping:**
| Prop | Token |
|---|---|
| Slot Frame | Theme.Colors.Surface, Theme.Radii.Medium, Theme.Colors.Stroke |
| Slot Size | Theme.ComponentOverrides.Hotbar.default.SlotSize (64 desktop, 72 mobile) |
| Slot Gap | Theme.ComponentOverrides.Hotbar.default.SlotGap |
| Selected | Theme.Colors.Primary stroke (3px), Scale 1.05 |
| Cooldown Overlay | Radial wipe (ImageLabel radial), Theme.Colors.Background @ 0.7 opacity |
| Keybind Label | Theme.Type.FontFamilyMono, Theme.Type.Micro, Theme.Colors.TextSecondary |
| Count Badge | Theme.Radii.Small, Theme.Colors.Danger background, Theme.Type.Numeric |

**Input:**
- Desktop: 1-9 keys → Slot index
- Gamepad: D-pad Left/Right → Navigate, A → Activate
- Touch: Tap slot → Activate

---

## 9. DIALOGUE — Conversation System

```lua
function UIRecipes.Dialogue(props)
  -- props: { Speaker, Portrait, Lines, Choices, OnChoice, Theme }
  -- Lines: array of { Text, Delay, AutoAdvance }
  -- Choices: array of { Text, Callback }
end
```

**Token Mapping:**
| Prop | Token |
|---|---|
| Panel | Theme.Colors.Surface, Theme.Radii.Large, Theme.Spacing.Large |
| Portrait | Theme.ComponentOverrides.Dialogue.default.PortraitSize (80), Theme.Radii.Large |
| Name | Theme.Type.FontFamilyBold, Theme.Type.Heading, Theme.Colors.Primary |
| Text | Theme.Type.FontFamily, Theme.Type.Body, Theme.Colors.TextPrimary |
| Typewriter | Theme.ComponentOverrides.Dialogue.default.TypewriterSpeed (0.03s/char) |
| Choices | UIRecipes.Button "ghost" variant, vertical list, Theme.Spacing.ChoicesGap |

**Behavior:**
- Typewriter effect with RichText support
- Auto-advance after Delay if AutoAdvance=true
- Choice selection: Mouse/Touch click, Gamepad A, Keyboard 1-9

---

## 10. NOTIFICATION — Persistent Alert

```lua
function UIRecipes.Notification(props)
  -- props: { Title, Body, Variant, Persistent, Actions, Theme }
  -- Variants: "info" | "warning" | "critical" | "achievement"
  -- Stacks vertically, oldest at top, slide-in from right
end
```

**Token Mapping:**
| Prop | Token |
|---|---|
| Background | Variant → Theme.Colors (Primary/Warning/Danger/Accent) |
| Slide Distance | Theme.ComponentOverrides.Notification.default.SlideDistance |
| Stack Gap | Theme.ComponentOverrides.Notification.default.StackGap |
| Max Visible | Theme.ComponentOverrides.Notification.default.MaxVisible |
| Icon | Variant-specific (info/warning/critical/star) |
| Close Button | UIRecipes.Button "ghost" small (24x24) |

---

## 11. LEADERBOARD — Score/Rank Display

```lua
function UIRecipes.Leaderboard(props)
  -- props: { Data, Columns, SortColumn, SortDirection, Theme }
  -- Data: array of { Rank, Name, Score, [ExtraColumns...] }
end
```

**Token Mapping:**
| Prop | Token |
|---|---|
| Header | Theme.Colors.SurfaceRaised, Theme.Type.FontFamilyBold, Theme.Type.Small |
| Row | Theme.Colors.Surface (alternating), Theme.Type.FontFamily, Theme.Type.Body |
| Row Height | Theme.ComponentOverrides.Leaderboard.default.RowHeight |
| Columns | Theme.ComponentOverrides.Leaderboard.default.Columns |
| Highlight (local player) | Theme.Colors.Primary background @ 0.15 opacity |
| Scroll | ScrollingFrame with AutomaticCanvasSize=Y |

---

## 12. SETTINGS — Configuration Panel

```lua
function UIRecipes.Settings(props)
  -- props: { Categories, OnChanged, Theme }
  -- Categories: array of { Name, Controls }
  -- Controls: { Type="toggle"|"slider"|"dropdown"|"keybind", Key, Label, Min, Max, Options, Default }
end
```

**Token Mapping:**
| Prop | Token |
|---|---|
| Category Header | Theme.Type.FontFamilyBold, Theme.Type.Heading, Theme.Colors.TextPrimary |
| Control Height | Theme.ComponentOverrides.Settings.default.ControlHeight |
| Slider Width | Theme.ComponentOverrides.Settings.default.SliderWidth |
| Toggle | Custom: Knob (Theme.Colors.Primary) + Track (Theme.Colors.SurfaceRaised) |
| Dropdown | UIRecipes.Button "secondary" + popup list |
| Keybind | UIRecipes.Button "ghost" → enters capture mode on click |
| Category Gap | Theme.ComponentOverrides.Settings.default.CategoryGap |

---

## 13. LOADING SCREEN — Entry/Transition

```lua
function UIRecipes.LoadingScreen(props)
  -- props: { Logo, Progress, Tips, Theme }
  -- Progress: 0-1 or "indeterminate"
  -- Tips: array of strings, rotate every Theme.ComponentOverrides.LoadingScreen.default.TipInterval
end
```

**Token Mapping:**
| Prop | Token |
|---|---|
| Background | Theme.Colors.Background |
| Logo Size | Theme.ComponentOverrides.LoadingScreen.default.LogoSize |
| Bar Width/Height | Theme.ComponentOverrides.LoadingScreen.default.BarWidth/BarHeight |
| Bar Colors | Track: Theme.Colors.Surface, Fill: Theme.Colors.Primary |
| Tip Text | Theme.Type.FontFamily, Theme.Type.Small, Theme.Colors.TextSecondary |
| Tip Interval | Theme.ComponentOverrides.LoadingScreen.default.TipInterval (seconds) |
| Indeterminate | Animated shimmer (UIGradient rotation) |

---

## 14. TOOLTIP — Contextual Hint

```lua
function UIRecipes.Tooltip(props)
  -- props: { Text, Target, Position, Theme }
  -- Position: "top" | "bottom" | "left" | "right" | "cursor"
  -- Shows on hover/focus, hides on leave/blur
end
```

**Token Mapping:**
| Prop | Token |
|---|---|
| Background | Theme.Colors.SurfaceRaised |
| Text | Theme.Type.FontFamily, Theme.Type.Small, Theme.Colors.TextPrimary |
| CornerRadius | Theme.Radii.Small |
| Padding | Theme.Spacing.Small |
| Arrow | 8px triangle pointing to target |
| Delay | 0.5s show, 0.1s hide |
| MaxWidth | 280px |

---

## 15. DROPDOWN — Selection Menu

```lua
function UIRecipes.Dropdown(props)
  -- props: { Options, Selected, OnChanged, Placeholder, Theme }
  -- Options: array of { Value, Label, Icon }
end
```

**Token Mapping:**
| Prop | Token |
|---|---|
| Trigger Button | UIRecipes.Button "secondary" with chevron icon |
| Popup Panel | Theme.Colors.Surface, Theme.Radii.Medium, Theme.Colors.Stroke |
| Option Height | 36px |
| Option Hover | Theme.Colors.Primary @ 0.15 |
| Selected Option | Theme.Colors.Primary text, check icon |
| Max Height | 200px (scrollable) |
| ZIndex | 1000 (above modals) |

---

## RESPONSIVE TOKEN OVERRIDES

```lua
-- Applied automatically by UIController based on viewport
ResponsiveTokens = {
  Desktop = { Scale = 1.0, TouchTarget = 44 },
  Tablet  = { Scale = 0.95, TouchTarget = 56 },
  Mobile  = { Scale = 0.9, TouchTarget = 64 },
  Console = { Scale = 1.1, TouchTarget = 88, FocusScale = 1.08 }
}
```

**Application:**
- All sizes multiplied by Scale
- TouchTarget = minimum hit area for buttons/interactables
- Console: FocusScale applied to selected element

---

## THEME VARIANT EXAMPLES

### Studded Variant Overrides
```lua
Studded = {
  Panel = { Texture = "stud", CornerRadius = "Small", StrokeWeight = 5 },
  Button = { Texture = "stud", CornerRadius = "Small", PressPop = true },
  Card = { Texture = "stud", Layout = "grid", AspectRatio = 1.0 },
  Bar = { Texture = "stud", Height = 10 }
}
```

### Cartoony Variant Overrides
```lua
Cartoony = {
  Panel = { CornerRadius = "Large", StrokeWeight = 4, Gradient = "top_lit" },
  Button = { CornerRadius = "Large", PressPop = true, HoverGlow = true, Shape = "chunky" },
  Card = { CornerRadius = "Large", Layout = "grid", Gap = "Medium" },
  Toast = { CornerRadius = "Large", SlideBounce = true }
}
```

### Horror Variant Overrides
```lua
Horror = {
  Panel = { Texture = "grain", CornerRadius = "None", StrokeWeight = 2, Alpha = 0.9 },
  Button = { CornerRadius = "None", PressPop = false, HoverColorShift = true },
  Card = { Layout = "list", Density = "high", Stats = "detailed" },
  Motion = { OpenDuration = 0.3, Flicker = true, NoPressPop = true }
}
```

---

*Each recipe is a function that reads from Theme tokens — change the theme, the entire UI system re-styles automatically.*