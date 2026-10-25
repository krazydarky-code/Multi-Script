> Adapted reference specification. Pseudocode, illustrative IDs and suggested budgets below are not installed components or verified assets. Use the reviewed modules / Forge where applicable; implement and test missing behavior in the actual project.

# OMNI-GUI Unified Composition Recipes

> Cross-domain compositions that synchronize Animation + UI + VFX into single timelines. The crown jewel of OMNI-GUI integration.

---

## COMPOSITION SPEC FORMAT

```json
{
  "name": "CompositionName",
  "theme": "theme_name",
  "duration": 3.2,
  "tracks": {
    "animation": { ... },
    "ui": { ... },
    "vfx": { ... }
  }
}
```

Each track defines its elements and a unified timeline drives all three in perfect sync.

---

## 1. ULTIMATE ABILITY — Fire Slash

```json
{
  "name": "Ultimate_Fire_Slash",
  "theme": "anime_fire",
  "description": "Charged fire ultimate: windup → cast bar → slash → explosion → cooldown",
  "duration": 3.2,
  "tracks": {
    "animation": {
      "character": "Fire_Slash_Ultimate",
      "priority": "Action3",
      "fadeIn": 0.05,
      "fadeOut": 0.15,
      "markers": {
        "ChargeStart": 0.00,
        "ChargeLoop": 0.40,
        "Release": 0.80,
        "Impact": 1.20,
        "RecoveryStart": 2.00,
        "RecoveryEnd": 2.80
      },
      "speed": 1.0
    },
    "ui": {
      "elements": [
        {
          "id": "chargeRing",
          "type": "ProgressRing",
          "anchor": "Character",
          "offset": { "x": 0, "y": 4 },
          "radius": 3,
          "duration": 0.80,
          "color": "Accent",
          "bgColor": "Surface",
          "thickness": 4,
          "direction": "CW",
          "ease": "QuartOut"
        },
        {
          "id": "castBar",
          "type": "ProgressBar",
          "anchor": "ScreenBottom",
          "offset": { "x": 0, "y": -120 },
          "width": 300,
          "height": 12,
          "duration": 0.80,
          "color": "Accent",
          "bgColor": "Surface",
          "label": "ULTIMATE",
          "ease": "Linear"
        },
        {
          "id": "impactFlash",
          "type": "ScreenFlash",
          "color": "Accent",
          "duration": 0.12,
          "ease": "QuadOut",
          "maxAlpha": 0.6
        },
        {
          "id": "screenShake",
          "type": "CameraShake",
          "magnitude": 8,
          "frequency": 20,
          "duration": 0.25,
          "ease": "QuadOut"
        },
        {
          "id": "cooldownOverlay",
          "type": "AbilityIconCooldown",
          "slot": 4,
          "duration": 12.0,
          "color": "Danger",
          "textColor": "TextPrimary",
          "showNumber": true
        },
        {
          "id": "ultimateName",
          "type": "FloatingText",
          "anchor": "Character",
          "offset": { "x": 0, "y": 8 },
          "text": "INFERNO SLASH",
          "fontSize": 24,
          "color": "Accent",
          "strokeColor": "Background",
          "strokeWidth": 2,
          "duration": 1.5,
          "motion": { "type": "RiseFade", "distance": 40, "ease": "QuartOut" }
        }
      ]
    },
    "vfx": {
      "elements": [
        {
          "id": "chargeParticles",
          "recipe": "Fire_ChargeUp",
          "anchor": "RightHand",
          "scale": 1.2,
          "colorMult": { "core": 1.0, "edge": 1.0, "smoke": 0.5 }
        },
        {
          "id": "chargeGlow",
          "recipe": "PointLight_Pulse",
          "anchor": "RightHand",
          "color": "#FF6B35",
          "range": 10,
          "brightness": 3,
          "pulseRate": 0.15
        },
        {
          "id": "groundSigil",
          "recipe": "Fire_Sigil",
          "anchor": "CharacterRoot",
          "offset": { "x": 0, "y": -3, "z": 2 },
          "scale": 1.5,
          "rotationSpeed": 30
        },
        {
          "id": "slashVFX",
          "recipe": "Anime_Fire_Slash",
          "anchor": "BladeTrail",
          "scale": 1.8,
          "colorMult": { "core": 1.2, "edge": 1.0 }
        },
        {
          "id": "impactExplosion",
          "recipe": "Fire_Explosion_Ground",
          "anchor": "TargetPoint",
          "scale": 2.2
        },
        {
          "id": "aftermathEmbers",
          "recipe": "Fire_Embers",
          "anchor": "ImpactPoint",
          "rateMult": 0.6,
          "lifetimeMult": 1.5
        },
        {
          "id": "screenFlashVFX",
          "recipe": "ScreenFlash_Color",
          "anchor": "Camera",
          "color": "#FF6B35",
          "duration": 0.08
        }
      ],
      "timeline": [
        { "t": 0.00, "id": "chargeParticles", "action": "enable", "params": { "on": true } },
        { "t": 0.00, "id": "chargeGlow", "action": "enable", "params": { "on": true } },
        { "t": 0.00, "id": "groundSigil", "action": "enable", "params": { "on": true } },
        { "t": 0.80, "id": "chargeParticles", "action": "enable", "params": { "on": false } },
        { "t": 0.80, "id": "chargeGlow", "action": "enable", "params": { "on": false } },
        { "t": 0.80, "id": "groundSigil", "action": "enable", "params": { "on": false } },
        { "t": 0.80, "id": "slashVFX", "action": "emit", "params": { "mult": 1.8 } },
        { "t": 1.20, "id": "slashVFX", "action": "destroy" },
        { "t": 1.20, "id": "impactExplosion", "action": "emit", "params": { "mult": 2.2 } },
        { "t": 1.20, "id": "screenFlashVFX", "action": "emit" },
        { "t": 1.50, "id": "aftermathEmbers", "action": "enable", "params": { "on": true } },
        { "t": 2.80, "id": "aftermathEmbers", "action": "enable", "params": { "on": false } }
      ]
    }
  },
  "syncPoints": [
    { "time": 0.80, "event": "Release", "animationMarker": "Release", "uiTrigger": "castBar.complete", "vfxTrigger": "slashVFX.emit" },
    { "time": 1.20, "event": "Impact", "animationMarker": "Impact", "uiTrigger": "impactFlash+screenShake", "vfxTrigger": "impactExplosion+screenFlash" },
    { "time": 2.00, "event": "RecoveryStart", "animationMarker": "RecoveryStart", "uiTrigger": "cooldownOverlay.start" },
    { "time": 2.80, "event": "RecoveryEnd", "animationMarker": "RecoveryEnd", "uiTrigger": "ultimateName.fadeOut" }
  ]
}
```

---

## 2. BOSS INTRO — Phase Transition

```json
{
  "name": "Boss_Intro_Phase2",
  "theme": "horror_tactical",
  "description": "Boss roars → arena darkens → UI warning → phase 2 abilities unlock",
  "duration": 5.0,
  "tracks": {
    "animation": {
      "character": "Boss_Roar_Phase2",
      "priority": "Action4",
      "fadeIn": 0.1,
      "fadeOut": 0.5,
      "markers": {
        "RoarStart": 0.00,
        "RoarPeak": 1.20,
        "RoarEnd": 2.50,
        "Stomp": 3.00,
        "AuraBurst": 3.50,
        "Idle2": 4.50
      }
    },
    "ui": {
      "elements": [
        {
          "id": "warningBanner",
          "type": "FullscreenBanner",
          "text": "⚠ PHASE TRANSITION ⚠",
          "fontSize": 48,
          "color": "Danger",
          "bgColor": "Background",
          "bgAlpha": 0.9,
          "duration": 3.0,
          "motion": { "type": "SlideDown", "distance": 200, "ease": "BackOut", "delay": 0.5 }
        },
        {
          "id": "healthBarTransform",
          "type": "HealthBarMorph",
          "newStyle": "Phase2",
          "duration": 1.0,
          "ease": "QuartInOut",
          "delay": 2.0
        },
        {
          "id": "abilityUnlock",
          "type": "AbilityUnlockToast",
          "abilities": ["Dark_Slash", "Void_Zone", "Summon_Minions"],
          "duration": 4.0,
          "delay": 3.0,
          "stagger": 0.3
        },
        {
          "id": "screenDesaturate",
          "type": "ColorCorrection",
          "saturation": 0.3,
          "contrast": 1.3,
          "duration": 2.0,
          "ease": "SineInOut",
          "delay": 1.0
        }
      ]
    },
    "vfx": {
      "elements": [
        {
          "id": "darkAura",
          "recipe": "Void_Aura",
          "anchor": "BossRoot",
          "scale": 3.0,
          "colorMult": { "core": 1.0, "edge": 0.8 }
        },
        {
          "id": "roarShockwave",
          "recipe": "Shockwave_Dark",
          "anchor": "BossMouth",
          "scale": 2.5,
          "direction": "Omni"
        },
        {
          "id": "groundCracks",
          "recipe": "Ground_Cracks_Radial",
          "anchor": "BossRoot",
          "scale": 4.0,
          "count": 8
        },
        {
          "id": "fallingDebris",
          "recipe": "Debris_Rain",
          "anchor": "ArenaCeiling",
          "area": { "x": 50, "z": 50 },
          "rate": 5,
          "duration": 3.0
        },
        {
          "id": "phaseParticles",
          "recipe": "Void_Motes",
          "anchor": "BossRoot",
          "scale": 2.0,
          "rateMult": 2.0
        }
      ],
      "timeline": [
        { "t": 0.00, "id": "darkAura", "action": "enable", "params": { "on": true, "fadeIn": 1.0 } },
        { "t": 1.00, "id": "roarShockwave", "action": "emit" },
        { "t": 1.20, "id": "groundCracks", "action": "emit" },
        { "t": 2.00, "id": "fallingDebris", "action": "enable", "params": { "on": true } },
        { "t": 3.00, "id": "phaseParticles", "action": "enable", "params": { "on": true } },
        { "t": 3.50, "id": "darkAura", "action": "pulse", "params": { "scale": 1.5, "duration": 0.5 } },
        { "t": 4.50, "id": "fallingDebris", "action": "enable", "params": { "on": false } },
        { "t": 5.00, "id": "phaseParticles", "action": "enable", "params": { "on": false, "fadeOut": 1.0 } }
      ]
    }
  },
  "syncPoints": [
    { "time": 1.20, "event": "RoarPeak", "animationMarker": "RoarPeak", "uiTrigger": "warningBanner.show", "vfxTrigger": "roarShockwave+groundCracks" },
    { "time": 3.00, "event": "Stomp", "animationMarker": "Stomp", "vfxTrigger": "groundCracks.pulse" },
    { "time": 3.50, "event": "AuraBurst", "animationMarker": "AuraBurst", "vfxTrigger": "darkAura.pulse+phaseParticles.enable" }
  ]
}
```

---

## 3. LEVEL UP — Celebration

```json
{
  "name": "Level_Up",
  "theme": "cartoony_fantasy",
  "description": "Joyful celebration: burst → stats rise → confetti → ability unlock",
  "duration": 3.5,
  "tracks": {
    "animation": {
      "character": "LevelUp_Celebration",
      "priority": "Action2",
      "fadeIn": 0.05,
      "fadeOut": 0.3,
      "markers": {
        "Jump": 0.00,
        "Spin": 0.30,
        "Land": 0.80,
        "Pose": 1.20,
        "FloatDown": 2.00,
        "Idle": 3.00
      }
    },
    "ui": {
      "elements": [
        {
          "id": "levelUpBanner",
          "type": "CenterBanner",
          "title": "LEVEL UP!",
          "subtitle": "Level {newLevel}",
          "titleSize": 56,
          "subtitleSize": 28,
          "titleColor": "Accent",
          "subtitleColor": "TextPrimary",
          "bgColor": "Surface",
          "bgAlpha": 0.95,
          "duration": 3.0,
          "motion": { "type": "ScaleInBounce", "peakScale": 1.15, "ease": "BackOut" }
        },
        {
          "id": "statRollover",
          "type": "StatRollover",
          "stats": ["Health", "Mana", "Attack", "Defense", "Speed"],
          "duration": 1.5,
          "delay": 0.5,
          "stagger": 0.15,
          "ease": "QuartOut",
          "sound": "LevelUp_StatTick"
        },
        {
          "id": "confettiBurst",
          "type": "ConfettiCanvas",
          "colors": ["Accent", "Primary", "Success", "Warning"],
          "count": 100,
          "duration": 2.5,
          "gravity": 0.5,
          "wind": 2
        },
        {
          "id": "xpBarFill",
          "type": "XPBarComplete",
          "duration": 0.8,
          "ease": "QuartOut",
          "glow": true
        }
      ]
    },
    "vfx": {
      "elements": [
        {
          "id": "burstRing",
          "recipe": "Magic_BurstRing",
          "anchor": "CharacterRoot",
          "scale": 1.5,
          "color": "Accent"
        },
        {
          "id": "risingStars",
          "recipe": "Magic_RisingStars",
          "anchor": "CharacterRoot",
          "count": 20,
          "height": 10,
          "duration": 2.0
        },
        {
          "id": "levelNumber",
          "recipe": "TextParticles_3D",
          "anchor": "CharacterRoot",
          "text": "{newLevel}",
          "fontSize": 4,
          "color": "Accent",
          "duration": 1.5,
          "motion": { "type": "RiseExpandFade", "height": 8 }
        },
        {
          "id": "groundGlow",
          "recipe": "Magic_GroundGlow",
          "anchor": "CharacterRoot",
          "radius": 4,
          "duration": 2.5,
          "pulse": true
        }
      ],
      "timeline": [
        { "t": 0.00, "id": "burstRing", "action": "emit" },
        { "t": 0.10, "id": "risingStars", "action": "enable", "params": { "on": true } },
        { "t": 0.30, "id": "levelNumber", "action": "emit" },
        { "t": 0.50, "id": "groundGlow", "action": "enable", "params": { "on": true } },
        { "t": 2.50, "id": "risingStars", "action": "enable", "params": { "on": false } },
        { "t": 3.00, "id": "groundGlow", "action": "enable", "params": { "on": false, "fadeOut": 0.5 } }
      ]
    }
  },
  "syncPoints": [
    { "time": 0.00, "event": "Jump", "animationMarker": "Jump", "uiTrigger": "levelUpBanner.show", "vfxTrigger": "burstRing" },
    { "time": 0.80, "event": "Land", "animationMarker": "Land", "uiTrigger": "statRollover.start+confettiBurst", "vfxTrigger": "groundGlow" },
    { "time": 1.20, "event": "Pose", "animationMarker": "Pose", "uiTrigger": "xpBarFill" }
  ]
}
```

---

## 4. DEATH SEQUENCE — Player

```json
{
  "name": "Death_Sequence_Player",
  "theme": "horror_survival",
  "description": "Visceral death: hit → ragdoll → fade → respawn UI",
  "duration": 4.0,
  "tracks": {
    "animation": {
      "character": "Death_Heavy",
      "priority": "Action4",
      "fadeIn": 0.0,
      "fadeOut": 0.0,
      "markers": {
        "Impact": 0.00,
        "Ragdoll": 0.10,
        "GroundContact": 0.50,
        "FinalBreath": 1.50,
        "FadeStart": 2.50
      }
    },
    "ui": {
      "elements": [
        {
          "id": "deathScreen",
          "type": "DeathScreen",
          "title": "YOU DIED",
          "subtitle": "Press [R] to respawn",
          "titleSize": 64,
          "subtitleSize": 20,
          "titleColor": "Danger",
          "subtitleColor": "TextSecondary",
          "bgColor": "Background",
          "bgAlpha": 0.0,
          "fadeInDuration": 1.5,
          "vignette": true,
          "vignetteColor": "Danger",
          "vignetteAlpha": 0.6
        },
        {
          "id": "killerInfo",
          "type": "KillerInfo",
          "showKiller": true,
          "showWeapon": true,
          "duration": 3.0,
          "delay": 2.0
        },
        {
          "id": "respawnTimer",
          "type": "RespawnCountdown",
          "duration": 5.0,
          "startDelay": 2.5,
          "color": "TextPrimary",
          "bgColor": "Background",
          "bgAlpha": 0.7
        }
      ]
    },
    "vfx": {
      "elements": [
        {
          "id": "bloodMist",
          "recipe": "Blood_Mist",
          "anchor": "HitPoint",
          "scale": 1.0
        },
        {
          "id": "bodyImpact",
          "recipe": "Heavy_Impact",
          "anchor": "CharacterRoot",
          "scale": 0.8
        },
        {
          "id": "soulParticles",
          "recipe": "Soul_Release",
          "anchor": "CharacterRoot",
          "count": 15,
          "duration": 2.0,
          "color": "TextSecondary"
        },
        {
          "id": "screenBlood",
          "recipe": "Screen_BloodSplatter",
          "anchor": "Camera",
          "intensity": 0.4,
          "duration": 1.0
        }
      ],
      "timeline": [
        { "t": 0.00, "id": "bloodMist", "action": "emit" },
        { "t": 0.10, "id": "bodyImpact", "action": "emit" },
        { "t": 0.50, "id": "screenBlood", "action": "emit" },
        { "t": 1.50, "id": "soulParticles", "action": "enable", "params": { "on": true } },
        { "t": 3.50, "id": "soulParticles", "action": "enable", "params": { "on": false } }
      ]
    }
  },
  "syncPoints": [
    { "time": 0.00, "event": "Impact", "animationMarker": "Impact", "vfxTrigger": "bloodMist" },
    { "time": 0.10, "event": "Ragdoll", "animationMarker": "Ragdoll", "vfxTrigger": "bodyImpact" },
    { "time": 0.50, "event": "GroundContact", "animationMarker": "GroundContact", "vfxTrigger": "screenBlood" },
    { "time": 1.50, "event": "FinalBreath", "animationMarker": "FinalBreath", "vfxTrigger": "soulParticles", "uiTrigger": "deathScreen.fadeIn" },
    { "time": 2.50, "event": "FadeStart", "animationMarker": "FadeStart", "uiTrigger": "killerInfo+respawnTimer" }
  ]
}
```

---

## 5. DASH COMBO — Movement + Attack

```json
{
  "name": "Dash_Combo",
  "theme": "anime_tactical",
  "description": "Dash through enemy → slash on exit → slow-mo moment",
  "duration": 1.5,
  "tracks": {
    "animation": {
      "character": "Dash_Slash_Combo",
      "priority": "Action2",
      "markers": {
        "DashStart": 0.00,
        "DashEnd": 0.30,
        "SlashRelease": 0.35,
        "SlashImpact": 0.45,
        "Recovery": 0.80
      }
    },
    "ui": {
      "elements": [
        {
          "id": "dashTrailUI",
          "type": "ScreenTrail",
          "anchor": "Character",
          "color": "Primary",
          "width": 8,
          "duration": 0.30,
          "fadeOut": 0.15
        },
        {
          "id": "slowmoIndicator",
          "type": "SlowmoVignette",
          "duration": 0.20,
          "delay": 0.35,
          "intensity": 0.3,
          "color": "Accent"
        },
        {
          "id": "hitConfirm",
          "type": "HitMarker",
          "style": "Cross",
          "color": "Success",
          "size": 32,
          "duration": 0.3,
          "delay": 0.45
        }
      ]
    },
    "vfx": {
      "elements": [
        {
          "id": "dashAfterimage",
          "recipe": "Dash_Afterimage",
          "anchor": "Character",
          "scale": 1.0
        },
        {
          "id": "exitSlash",
          "recipe": "Anime_Slash",
          "anchor": "BladeTrail",
          "scale": 1.3
        },
        {
          "id": "timeDilation",
          "recipe": "TimeDilation_Ripple",
          "anchor": "ImpactPoint",
          "scale": 2.0,
          "duration": 0.15
        }
      ],
      "timeline": [
        { "t": 0.00, "id": "dashAfterimage", "action": "enable", "params": { "on": true } },
        { "t": 0.30, "id": "dashAfterimage", "action": "enable", "params": { "on": false } },
        { "t": 0.35, "id": "exitSlash", "action": "emit", "params": { "mult": 1.3 } },
        { "t": 0.45, "id": "timeDilation", "action": "emit" }
      ]
    }
  },
  "syncPoints": [
    { "time": 0.00, "event": "DashStart", "animationMarker": "DashStart", "vfxTrigger": "dashAfterimage", "uiTrigger": "dashTrailUI" },
    { "time": 0.35, "event": "SlashRelease", "animationMarker": "SlashRelease", "vfxTrigger": "exitSlash", "uiTrigger": "slowmoIndicator" },
    { "time": 0.45, "event": "SlashImpact", "animationMarker": "SlashImpact", "vfxTrigger": "timeDilation", "uiTrigger": "hitConfirm" }
  ]
}
```

---

## 6. ITEM PICKUP — UI + VFX + Anim

```json
{
  "name": "Item_Pickup_Rare",
  "theme": "fantasy_rpg",
  "description": "Character reaches → item floats → UI toast + stat preview",
  "duration": 2.0,
  "tracks": {
    "animation": {
      "character": "Interact_Pickup",
      "priority": "Action",
      "markers": {
        "Reach": 0.20,
        "Grasp": 0.35,
        "Lift": 0.45,
        "Inspect": 0.60
      }
    },
    "ui": {
      "elements": [
        {
          "id": "pickupToast",
          "type": "ItemToast",
          "rarity": "Rare",
          "itemName": "{itemName}",
          "icon": "{itemIcon}",
          "stats": "{itemStats}",
          "duration": 4.0,
          "delay": 0.5,
          "motion": { "type": "SlideInBounce", "ease": "BackOut" }
        },
        {
          "id": "rarityGlow",
          "type": "RarityGlow",
          "anchor": "ItemModel",
          "rarity": "Rare",
          "duration": 1.5,
          "pulse": true
        }
      ]
    },
    "vfx": {
      "elements": [
        {
          "id": "pickupSparkle",
          "recipe": "Magic_PickupSparkle",
          "anchor": "ItemModel",
          "scale": 1.0,
          "color": "Rare"
        },
        {
          "id": "itemFloat",
          "recipe": "Item_Levitate",
          "anchor": "ItemModel",
          "height": 1.5,
          "duration": 0.5,
          "bob": true
        }
      ],
      "timeline": [
        { "t": 0.20, "id": "pickupSparkle", "action": "emit" },
        { "t": 0.35, "id": "itemFloat", "action": "enable", "params": { "on": true } },
        { "t": 0.50, "id": "rarityGlow", "action": "enable", "params": { "on": true } }
      ]
    }
  },
  "syncPoints": [
    { "time": 0.35, "event": "Grasp", "animationMarker": "Grasp", "vfxTrigger": "pickupSparkle+itemFloat", "uiTrigger": "rarityGlow" },
    { "time": 0.60, "event": "Inspect", "animationMarker": "Inspect", "uiTrigger": "pickupToast" }
  ]
}
```

---

## COMPOSITION PLAYER API

```lua
-- VFXController.PlayComposition(spec)
-- Spec can be:
--  1. String name (loads from compositions/ folder)
--  2. Full CompositionSpec table
--  3. CompositionSpec with runtime overrides

-- Returns a CompositionHandle:
CompositionHandle = {
  Name = "Ultimate_Fire_Slash",
  Duration = 3.2,
  Elapsed = 0,
  IsPlaying = true,
  SyncPoints = { ... },

  -- Control
  Pause = function(self) end,
  Resume = function(self) end,
  Stop = function(self, fadeOut) end,
  Seek = function(self, time) end,
  SetSpeed = function(self, speed) end,

  -- Events
  OnSyncPoint = Signal.new(), -- fires(name, time, data)
  OnComplete = Signal.new(),

  -- State
  GetTrackState = function(self, trackName) end, -- "animation" | "ui" | "vfx"
}
```

---

## SYNC POINT SYSTEM

Sync points are the glue that ensures frame-perfect coordination:

```lua
-- Defined in composition spec
SyncPoint = {
  Time = 1.20,           -- Absolute time in composition
  Event = "Impact",      -- Human-readable name
  AnimationMarker = "Impact",  -- Animation marker that triggers this
  UITrigger = "impactFlash+screenShake",  -- UI element IDs (comma-separated)
  VFXTrigger = "impactExplosion+screenFlash", -- VFX element IDs
  Tolerance = 0.016,     -- Frame tolerance (1 frame at 60fps)
  Callback = function() end -- Optional custom logic
}

-- Runtime: OMNIController monitors animation markers and triggers sync
AnimationController.OnMarker("Impact", function(markerName, param)
  local sync = CompositionPlayer.FindSyncPoint(markerName)
  if sync then
    CompositionPlayer.TriggerSync(sync)
  end
end)
```

---

## STYLE VARIANT OVERRIDES

Each composition can have style-specific overrides:

```json
{
  "name": "Ultimate_Fire_Slash",
  "baseTheme": "anime_fire",
  "styleOverrides": {
    "horror": {
      "animation": { "character": "Fire_Slash_Ultimate_Horror", "priority": "Action3" },
      "ui": { "impactFlash": { "color": "Danger", "duration": 0.2 }, "screenShake": { "magnitude": 12 } },
      "vfx": { "slashVFX": { "recipe": "Horror_Fire_Slash" }, "impactExplosion": { "recipe": "Fire_Explosion_Ground_Horror" } }
    },
    "tactical": {
      "animation": { "character": "Fire_Slash_Ultimate_Tactical", "priority": "Action2" },
      "ui": { "castBar": { "style": "Tactical" }, "cooldownOverlay": { "style": "Tactical" } },
      "vfx": { "slashVFX": { "recipe": "Tactical_Fire_Slash", "scale": 1.2 } }
    }
  }
}
```

---

*Compositions are the "secret sauce" — one authoring, three systems in perfect sync. This is what makes OMNI-GUI unique.*
