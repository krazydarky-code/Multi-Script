> Adapted reference specification. Pseudocode, illustrative IDs and suggested budgets below are not installed components or verified assets. Use the reviewed modules / Forge where applicable; implement and test missing behavior in the actual project.

# OMNI-GUI Unified VFX Recipes

> Merged from MultiVFX, Animation Engineering, and ProjectGUI skills. Each recipe is a layered composition with quality tiers, not a single emitter.

---

## LAYER ARCHITECTURE

Every VFX recipe follows the **5-layer hierarchy**:

```
1. SILHOUETTE     — Primary recognizable shape (ring, crescent, sphere, bolt)
2. CORE           — Bright central accent (flash, hot center, glare)
3. MOTION         — Directional detail (sparks, streaks, filaments, debris)
4. ATMOSPHERE     — Environmental feel (smoke, mist, motes, embers, dust)
5. IMPACT         — Contact confirmation (shockwave, decal, fragments, ripple)
```

**Quality Tiers** scale particle counts, lifetime, and complexity:
- **Low** (0.4-0.5x) — Mobile, low-end, 30+ players
- **Medium** (1.0x) — Default, balanced
- **High** (1.5-2.0x) — PC, cinematic, <10 players

---

## 1. FIRE & EXPLOSION

### 1.1 Fire_Impact
```json
{
  "name": "Fire_Impact",
  "category": "Fire",
  "duration": 1.8,
  "anchor": "WorldPosition",
  "layers": [
    {
      "id": "core_flash",
      "type": "ParticleEmitter",
      "role": "CORE",
      "texture": "sparkles_main.dds",
      "lifetime": { "min": 0.1, "max": 0.25 },
      "size": { "start": 3, "end": 0 },
      "rate": 0,
      "burst": { "Low": 4, "Medium": 8, "High": 12 },
      "color": { "keypoints": [ { "t": 0, "c": "#FFF2BE" }, { "t": 1, "c": "#FF9436" } ] },
      "lightEmission": 0.9,
      "speed": 0,
      "spread": 0
    },
    {
      "id": "flame_tongues",
      "type": "ParticleEmitter",
      "role": "SILHOUETTE",
      "texture": "fire_main.dds",
      "lifetime": { "min": 0.4, "max": 1.0 },
      "size": { "start": 2.5, "end": 0.3 },
      "rate": 0,
      "burst": { "Low": 10, "Medium": 20, "High": 35 },
      "color": { "keypoints": [ { "t": 0, "c": "#FF9436" }, { "t": 0.5, "c": "#FF6B00" }, { "t": 1, "c": "#AE2D19" } ] },
      "lightEmission": 0.5,
      "speed": { "min": 5, "max": 15 },
      "spread": 60,
      "acceleration": { "y": 20 },
      "drag": 0.3
    },
    {
      "id": "smoke_column",
      "type": "ParticleEmitter",
      "role": "ATMOSPHERE",
      "texture": "smoke_main.dds",
      "lifetime": { "min": 1.0, "max": 2.5 },
      "size": { "start": 3, "end": 10 },
      "rate": 0,
      "burst": { "Low": 5, "Medium": 10, "High": 18 },
      "color": { "keypoints": [ { "t": 0, "c": "#3D1A0F" }, { "t": 1, "c": "#1A0A05" } ] },
      "lightEmission": 0.05,
      "speed": { "min": 2, "max": 6 },
      "spread": 45,
      "drag": 0.5,
      "acceleration": { "y": 8 }
    },
    {
      "id": "embers",
      "type": "ParticleEmitter",
      "role": "MOTION",
      "texture": "sparkles_main.dds",
      "lifetime": { "min": 1.5, "max": 3.0 },
      "size": { "start": 0.4, "end": 0 },
      "rate": 0,
      "burst": { "Low": 6, "Medium": 12, "High": 20 },
      "color": { "keypoints": [ { "t": 0, "c": "#AE2D19" }, { "t": 1, "c": "#5A1005" } ] },
      "lightEmission": 0.4,
      "speed": { "min": 8, "max": 25 },
      "spread": 180,
      "drag": 0.1
    },
    {
      "id": "ground_flash",
      "type": "PointLight",
      "role": "IMPACT",
      "range": 15,
      "brightness": { "Low": 2, "Medium": 4, "High": 6 },
      "color": "#FF9436",
      "lifetime": 0.15,
      "tween": { "property": "Brightness", "ease": "QuadOut" }
    }
  ],
  "timeline": [
    { "t": 0.00, "id": "core_flash", "action": "emit" },
    { "t": 0.00, "id": "flame_tongues", "action": "emit" },
    { "t": 0.05, "id": "smoke_column", "action": "emit" },
    { "t": 0.08, "id": "embers", "action": "emit" },
    { "t": 0.00, "id": "ground_flash", "action": "enable" },
    { "t": 0.15, "id": "ground_flash", "action": "disable" }
  ]
}
```

### 1.2 Fireball_Projectile
```json
{
  "name": "Fireball_Projectile",
  "category": "Fire",
  "duration": "variable",
  "anchor": "Attachment:ProjectileCore",
  "follows": true,
  "layers": [
    {
      "id": "core_glow",
      "type": "ParticleEmitter",
      "role": "CORE",
      "texture": "sparkles_main.dds",
      "lifetime": 0.3,
      "size": 2,
      "rate": 30,
      "color": "#FFF2BE",
      "lightEmission": 0.8,
      "speed": 0,
      "lockedToPart": true,
      "velocityInheritance": 1
    },
    {
      "id": "trail_flames",
      "type": "Trail",
      "role": "SILHOUETTE",
      "attachment0": "TrailStart",
      "attachment1": "TrailEnd",
      "lifetime": 0.4,
      "width": 1.5,
      "color": { "keypoints": [ { "t": 0, "c": "#FF9436" }, { "t": 1, "c": "#AE2D19" } ] },
      "transparency": { "keypoints": [ { "t": 0, "c": 0.1 }, { "t": 1, "c": 1 } ] },
      "lightEmission": 0.4
    },
    {
      "id": "trailing_embers",
      "type": "ParticleEmitter",
      "role": "MOTION",
      "texture": "sparkles_main.dds",
      "lifetime": 0.8,
      "size": { "start": 0.5, "end": 0 },
      "rate": 20,
      "color": "#FF6B00",
      "lightEmission": 0.5,
      "speed": 0,
      "lockedToPart": true,
      "drag": 0.5
    }
  ]
}
```

### 1.3 Explosion_Ground
```json
{
  "name": "Explosion_Ground",
  "category": "Explosion",
  "duration": 2.5,
  "anchor": "WorldPosition",
  "layers": [
    {
      "id": "shockwave_ring",
      "type": "MeshPart",
      "role": "SILHOUETTE",
      "mesh": "RingMesh",
      "size": { "start": { "x": 1, "y": 0.1, "z": 1 }, "end": { "x": 25, "y": 0.1, "z": 25 } },
      "lifetime": 0.5,
      "color": "#FF9436",
      "transparency": { "start": 0.2, "end": 1 },
      "tween": { "property": "Size", "ease": "QuadOut" }
    },
    {
      "id": "debris_rocks",
      "type": "ParticleEmitter",
      "role": "MOTION",
      "texture": "rock_debris.png",
      "lifetime": 2.0,
      "size": { "start": 1, "end": 0.2 },
      "rate": 0,
      "burst": { "Low": 15, "Medium": 30, "High": 50 },
      "color": "#554433",
      "lightEmission": 0.1,
      "speed": { "min": 15, "max": 40 },
      "spread": 180,
      "acceleration": { "y": -196 },
      "rotationSpeed": 360
    },
    {
      "id": "dust_cloud",
      "type": "ParticleEmitter",
      "role": "ATMOSPHERE",
      "texture": "smoke_main.dds",
      "lifetime": 3.0,
      "size": { "start": 5, "end": 20 },
      "rate": 0,
      "burst": { "Low": 8, "Medium": 15, "High": 25 },
      "color": "#887766",
      "lightEmission": 0.05,
      "speed": { "min": 1, "max": 5 },
      "spread": 360,
      "drag": 0.3
    }
  ]
}
```

---

## 2. SLASH & MELEE

### 2.1 Sword_Slash (Universal)
```json
{
  "name": "Sword_Slash",
  "category": "Slash",
  "duration": 0.4,
  "anchor": "Attachment:BladeTrail",
  "layers": [
    {
      "id": "crescent_mesh",
      "type": "MeshPart",
      "role": "SILHOUETTE",
      "mesh": "SlashCrescent",
      "size": { "start": { "x": 0.5, "y": 8, "z": 0.1 }, "end": { "x": 3, "y": 15, "z": 0.1 } },
      "lifetime": 0.25,
      "color": "#FFFFFF",
      "transparency": { "start": 0.3, "end": 1 },
      "tween": { "property": "Size", "ease": "QuadOut" },
      "rotation": { "z": 90 }
    },
    {
      "id": "core_streak",
      "type": "Trail",
      "role": "CORE",
      "attachment0": "BladeTip",
      "attachment1": "BladeBase",
      "lifetime": 0.15,
      "width": 2,
      "color": "#FFFFFF",
      "transparency": { "keypoints": [ { "t": 0, "c": 0.05 }, { "t": 1, "c": 1 } ] },
      "lightEmission": 0.6
    },
    {
      "id": "slash_sparks",
      "type": "ParticleEmitter",
      "role": "MOTION",
      "texture": "sparkle.png",
      "lifetime": 0.3,
      "size": { "start": 0.6, "end": 0 },
      "rate": 0,
      "burst": { "Low": 6, "Medium": 12, "High": 20 },
      "color": "#FFFFFF",
      "lightEmission": 0.7,
      "speed": { "min": 20, "max": 40 },
      "spread": 30,
      "drag": 0.8
    }
  ],
  "timeline": [
    { "t": 0.00, "id": "crescent_mesh", "action": "enable" },
    { "t": 0.00, "id": "core_streak", "action": "enable" },
    { "t": 0.02, "id": "slash_sparks", "action": "emit" },
    { "t": 0.25, "id": "crescent_mesh", "action": "disable" },
    { "t": 0.30, "id": "core_streak", "action": "disable" }
  ]
}
```

### 2.2 Anime_Slash (Stylized Crescent)
```json
{
  "name": "Anime_Slash",
  "category": "Slash",
  "duration": 0.5,
  "anchor": "Attachment:BladeTrail",
  "layers": [
    {
      "id": "crescent_beam",
      "type": "Beam",
      "role": "SILHOUETTE",
      "attachment0": "SlashStart",
      "attachment1": "SlashEnd",
      "width0": 0.5,
      "width1": 5,
      "color": { "keypoints": [ { "t": 0, "c": "#00FFFF" }, { "t": 1, "c": "#0088FF" } ] },
      "texture": "slash_crescent.png",
      "textureSpeed": 2,
      "lightEmission": 0.8,
      "lifetime": 0.3
    },
    {
      "id": "streak_trail",
      "type": "Trail",
      "role": "CORE",
      "attachment0": "BladeTip",
      "attachment1": "BladeBase",
      "lifetime": 0.12,
      "width": 3,
      "color": "#FFFFFF",
      "lightEmission": 0.5
    },
    {
      "id": "motion_sparks",
      "type": "ParticleEmitter",
      "role": "MOTION",
      "texture": "sparkle.png",
      "lifetime": 0.4,
      "size": 0.8,
      "rate": 0,
      "burst": { "Low": 10, "Medium": 20, "High": 35 },
      "color": "#00FFAA",
      "lightEmission": 0.6,
      "speed": 30,
      "spread": 45
    },
    {
      "id": "afterimage",
      "type": "MeshPart",
      "role": "IMPACT",
      "mesh": "SlashAfterimage",
      "size": { "x": 4, "y": 12, "z": 0.1 },
      "lifetime": 0.2,
      "color": "#0088FF",
      "transparency": { "start": 0.4, "end": 1 },
      "tween": { "ease": "QuadOut" }
    }
  ]
}
```

### 2.3 Ground_Slam
```json
{
  "name": "Ground_Slam",
  "category": "Impact",
  "duration": 1.2,
  "anchor": "WorldPosition",
  "layers": [
    {
      "id": "shockwave_ring",
      "type": "MeshPart",
      "role": "SILHOUETTE",
      "mesh": "RingMesh",
      "size": { "start": { "x": 2, "y": 0.2, "z": 2 }, "end": { "x": 30, "y": 0.2, "z": 30 } },
      "lifetime": 0.6,
      "color": "#FFFFFF",
      "transparency": { "start": 0.1, "end": 1 },
      "tween": { "ease": "QuadOut" }
    },
    {
      "id": "radial_spikes",
      "type": "ParticleEmitter",
      "role": "MOTION",
      "texture": "spike_particle.png",
      "lifetime": 0.8,
      "size": { "start": 3, "end": 0 },
      "rate": 0,
      "burst": { "Low": 12, "Medium": 24, "High": 40 },
      "color": "#CCCCCC",
      "lightEmission": 0.3,
      "speed": 25,
      "spread": 10,
      "emissionDirection": "Back"
    },
    {
      "id": "ground_dust",
      "type": "ParticleEmitter",
      "role": "ATMOSPHERE",
      "texture": "smoke_main.dds",
      "lifetime": 2.0,
      "size": { "start": 4, "end": 15 },
      "rate": 0,
      "burst": { "Low": 10, "Medium": 20, "High": 35 },
      "color": "#888888",
      "lightEmission": 0.05,
      "speed": { "min": 2, "max": 8 },
      "spread": 360,
      "drag": 0.4
    },
    {
      "id": "impact_flash",
      "type": "PointLight",
      "role": "CORE",
      "range": 25,
      "brightness": 5,
      "color": "#FFFFFF",
      "lifetime": 0.1,
      "tween": { "ease": "QuadOut" }
    }
  ]
}
```

---

## 3. ELEMENTAL MAGIC

### 3.1 Ice_Burst
```json
{
  "name": "Ice_Burst",
  "category": "Ice",
  "duration": 1.5,
  "anchor": "WorldPosition",
  "palette": { "core": "#E8F4FF", "edge": "#88CCFF", "shard": "#FFFFFF", "mist": "#AADDFF" },
  "layers": [
    {
      "id": "shard_explosion",
      "type": "ParticleEmitter",
      "role": "SILHOUETTE",
      "texture": "ice_shard.png",
      "lifetime": { "min": 0.8, "max": 1.5 },
      "size": { "start": 2, "end": 0 },
      "rate": 0,
      "burst": { "Low": 15, "Medium": 30, "High": 50 },
      "color": "#FFFFFF",
      "lightEmission": 0.3,
      "speed": { "min": 10, "max": 30 },
      "spread": 180,
      "acceleration": { "y": -20 },
      "rotationSpeed": 720
    },
    {
      "id": "frost_mist",
      "type": "ParticleEmitter",
      "role": "ATMOSPHERE",
      "texture": "smoke_main.dds",
      "lifetime": 3.0,
      "size": { "start": 5, "end": 12 },
      "rate": 0,
      "burst": { "Low": 8, "Medium": 15, "High": 25 },
      "color": "#AADDFF",
      "lightEmission": 0.1,
      "speed": { "min": 1, "max": 4 },
      "spread": 360,
      "drag": 0.3
    },
    {
      "id": "core_flash",
      "type": "ParticleEmitter",
      "role": "CORE",
      "texture": "sparkles_main.dds",
      "lifetime": 0.15,
      "size": 4,
      "rate": 0,
      "burst": { "Low": 6, "Medium": 10, "High": 15 },
      "color": "#E8F4FF",
      "lightEmission": 0.9
    }
  ]
}
```

### 3.2 Lightning_Strike
```json
{
  "name": "Lightning_Strike",
  "category": "Lightning",
  "duration": 0.3,
  "anchor": "WorldPosition (start) → WorldPosition (end)",
  "palette": { "core": "#FFFFFF", "edge": "#88CCFF", "branch": "#4488FF", "glow": "#AAEEFF" },
  "procedural": true,
  "layers": [
    {
      "id": "main_bolt",
      "type": "Beam",
      "role": "SILHOUETTE",
      "segments": 8,
      "width0": 1.5,
      "width1": 1.5,
      "color": "#FFFFFF",
      "texture": "lightning.png",
      "textureSpeed": 5,
      "lightEmission": 1.0,
      "curve": "jagged",
      "lifetime": 0.15
    },
    {
      "id": "glow_layer",
      "type": "Beam",
      "role": "CORE",
      "segments": 8,
      "width0": 6,
      "width1": 6,
      "color": "#AAEEFF",
      "texture": "lightning_glow.png",
      "lightEmission": 0.5,
      "lifetime": 0.2
    },
    {
      "id": "branch_sparks",
      "type": "ParticleEmitter",
      "role": "MOTION",
      "texture": "sparkle.png",
      "lifetime": 0.1,
      "size": 0.5,
      "rate": 0,
      "burst": { "Low": 20, "Medium": 50, "High": 100 },
      "color": "#4488FF",
      "lightEmission": 0.7,
      "speed": 40,
      "spread": 60
    },
    {
      "id": "ground_contact",
      "type": "ParticleEmitter",
      "role": "IMPACT",
      "texture": "sparkles_main.dds",
      "lifetime": 0.3,
      "size": 1,
      "rate": 0,
      "burst": { "Low": 8, "Medium": 15, "High": 25 },
      "color": "#FFFFFF",
      "lightEmission": 0.6,
      "speed": 15,
      "spread": 180
    }
  ]
}
```

### 3.3 Healing_Pulse
```json
{
  "name": "Healing_Pulse",
  "category": "Healing",
  "duration": 2.0,
  "anchor": "Attachment:CharacterRoot",
  "palette": { "core": "#00FF88", "edge": "#00CC66", "mote": "#88FFCC", "ray": "#AAFFAA" },
  "layers": [
    {
      "id": "expanding_ring",
      "type": "MeshPart",
      "role": "SILHOUETTE",
      "mesh": "RingMesh",
      "size": { "start": { "x": 1, "y": 0.1, "z": 1 }, "end": { "x": 15, "y": 0.1, "z": 15 } },
      "lifetime": 1.0,
      "color": "#00FF88",
      "transparency": { "start": 0.3, "end": 1 },
      "tween": { "ease": "QuadOut" }
    },
    {
      "id": "rising_motes",
      "type": "ParticleEmitter",
      "role": "MOTION",
      "texture": "sparkles_main.dds",
      "lifetime": 2.5,
      "size": { "start": 0.5, "end": 0 },
      "rate": 8,
      "color": "#88FFCC",
      "lightEmission": 0.5,
      "speed": { "min": 2, "max": 8 },
      "spread": 20,
      "emissionDirection": "Top",
      "acceleration": { "y": 5 },
      "drag": 0.2
    },
    {
      "id": "vertical_rays",
      "type": "Beam",
      "role": "CORE",
      "attachment0": "RayStart",
      "attachment1": "RayEnd",
      "width0": 0.5,
      "width1": 0.1,
      "color": "#AAFFAA",
      "lightEmission": 0.7,
      "lifetime": 1.5,
      "segments": 1,
      "faceCamera": true
    }
  ]
}
```

---

## 4. AURA & PORTAL

### 4.1 Golden_Aura
```json
{
  "name": "Golden_Aura",
  "category": "Aura",
  "duration": "looping",
  "anchor": "Attachment:CharacterRoot",
  "palette": { "core": "#FFD700", "edge": "#FFA500", "particle": "#FFFF00" },
  "layers": [
    {
      "id": "ground_ring",
      "type": "MeshPart",
      "role": "SILHOUETTE",
      "mesh": "RingMesh",
      "size": { "x": 8, "y": 0.2, "z": 8 },
      "color": "#FFD700",
      "transparency": 0.3,
      "rotation": { "y": 30 }, -- rpm
      "loop": true
    },
    {
      "id": "rising_particles",
      "type": "ParticleEmitter",
      "role": "MOTION",
      "texture": "sparkles_main.dds",
      "lifetime": 2.0,
      "size": { "start": 0.5, "end": 0 },
      "rate": 10,
      "color": "#FFFF00",
      "lightEmission": 0.7,
      "speed": { "min": 1, "max": 5 },
      "spread": 15,
      "emissionDirection": "Top",
      "shape": "Disc",
      "shapeRadius": 4
    },
    {
      "id": "energy_spikes",
      "type": "ParticleEmitter",
      "role": "ATMOSPHERE",
      "texture": "energy_spike.png",
      "lifetime": 1.0,
      "size": { "start": 2, "end": 0 },
      "rate": 5,
      "color": "#FFA500",
      "lightEmission": 0.4,
      "speed": { "min": 8, "max": 15 },
      "spread": 30,
      "emissionDirection": "Top"
    }
  ]
}
```

### 4.2 Portal_Effect
```json
{
  "name": "Portal_Effect",
  "category": "Portal",
  "duration": "looping",
  "anchor": "WorldPosition",
  "palette": { "core": "#FFD700", "edge": "#FF8800", "particle": "#FFFF00" },
  "layers": [
    {
      "id": "outer_ring",
      "type": "MeshPart",
      "role": "SILHOUETTE",
      "mesh": "RingMesh",
      "size": { "x": 10, "y": 0.5, "z": 10 },
      "color": "#FFD700",
      "transparency": 0.2,
      "rotation": { "y": -20 },
      "loop": true
    },
    {
      "id": "inner_ring",
      "type": "MeshPart",
      "role": "CORE",
      "mesh": "RingMesh",
      "size": { "x": 6, "y": 0.3, "z": 6 },
      "color": "#FFFF00",
      "transparency": 0.1,
      "rotation": { "y": 30 },
      "loop": true
    },
    {
      "id": "orbiting_particles",
      "type": "ParticleEmitter",
      "role": "MOTION",
      "texture": "ring_particle.png",
      "lifetime": 3.0,
      "size": 0.8,
      "rate": 30,
      "color": "#FFFF00",
      "lightEmission": 0.6,
      "speed": 0,
      "shape": "Disc",
      "shapeRadius": 5,
      "lockedToPart": true
    },
    {
      "id": "central_motes",
      "type": "ParticleEmitter",
      "role": "ATMOSPHERE",
      "texture": "sparkles_main.dds",
      "lifetime": 2.0,
      "size": { "start": 0.3, "end": 0 },
      "rate": 15,
      "color": "#FFD700",
      "lightEmission": 0.8,
      "speed": { "min": 0.5, "max": 2 },
      "shape": "Sphere",
      "shapeRadius": 3
    }
  ]
}
```

---

## 5. MOVEMENT & TRAVERSAL

### 5.1 Dash_Afterimage
```json
{
  "name": "Dash_Afterimage",
  "category": "Movement",
  "duration": 0.4,
  "anchor": "Character",
  "layers": [
    {
      "id": "afterimage_clones",
      "type": "MeshPart",
      "role": "SILHOUETTE",
      "mesh": "CharacterSilhouette",
      "count": 4,
      "lifetime": 0.3,
      "color": "#00FFFF",
      "transparency": { "start": 0.5, "end": 1 },
      "tween": { "ease": "QuadOut" },
      "spawnInterval": 0.05
    },
    {
      "id": "motion_streak",
      "type": "Trail",
      "role": "CORE",
      "attachment0": "RootFront",
      "attachment1": "RootBack",
      "lifetime": 0.2,
      "width": 2,
      "color": "#00FFFF",
      "lightEmission": 0.6,
      "transparency": { "keypoints": [ { "t": 0, "c": 0.2 }, { "t": 1, "c": 1 } ] }
    },
    {
      "id": "dust_kickup",
      "type": "ParticleEmitter",
      "role": "IMPACT",
      "texture": "smoke_main.dds",
      "lifetime": 0.8,
      "size": { "start": 1, "end": 4 },
      "rate": 0,
      "burst": { "Low": 5, "Medium": 10, "High": 15 },
      "color": "#888888",
      "lightEmission": 0.05,
      "speed": { "min": 3, "max": 10 },
      "spread": 90,
      "emissionDirection": "Bottom"
    }
  ]
}
```

### 5.2 Teleport_Entry
```json
{
  "name": "Teleport_Entry",
  "category": "Movement",
  "duration": 0.8,
  "anchor": "WorldPosition",
  "phases": {
    "anticipation": { "duration": 0.3, "effect": "converging_particles" },
    "dissolve": { "duration": 0.1, "effect": "character_fade" },
    "travel": { "duration": 0.0, "effect": "instant" },
    "reappear": { "duration": 0.1, "effect": "character_fade_in" },
    "arrival": { "duration": 0.3, "effect": "burst_ring" }
  },
  "layers": [
    {
      "id": "converge_motes",
      "type": "ParticleEmitter",
      "phase": "anticipation",
      "texture": "sparkles_main.dds",
      "lifetime": 0.5,
      "size": { "start": 0.5, "end": 0 },
      "rate": 50,
      "color": "#00FFFF",
      "lightEmission": 0.7,
      "speed": 10,
      "shape": "Sphere",
      "shapeRadius": 5,
      "acceleration": { "center": true, "magnitude": 20 }
    },
    {
      "id": "arrival_ring",
      "type": "MeshPart",
      "phase": "arrival",
      "mesh": "RingMesh",
      "size": { "start": { "x": 1, "y": 0.1, "z": 1 }, "end": { "x": 12, "y": 0.1, "z": 12 } },
      "lifetime": 0.5,
      "color": "#00FFFF",
      "transparency": { "start": 0.2, "end": 1 }
    }
  ]
}
```

---

## 6. SHIELD & DEFENSIVE

### 6.1 Shield_Block
```json
{
  "name": "Shield_Block",
  "category": "Defensive",
  "duration": 0.5,
  "anchor": "Attachment:ShieldCenter",
  "palette": { "core": "#00FFFF", "edge": "#0088FF", "ripple": "#FFFFFF" },
  "layers": [
    {
      "id": "barrier_dome",
      "type": "MeshPart",
      "role": "SILHOUETTE",
      "mesh": "DomeMesh",
      "size": { "x": 6, "y": 6, "z": 6 },
      "lifetime": 0.4,
      "color": "#00FFFF",
      "transparency": { "start": 0.7, "end": 1 },
      "tween": { "ease": "QuadOut" }
    },
    {
      "id": "impact_ripple",
      "type": "MeshPart",
      "role": "IMPACT",
      "mesh": "RingMesh",
      "size": { "start": { "x": 4, "y": 0.1, "z": 4 }, "end": { "x": 8, "y": 0.1, "z": 8 } },
      "lifetime": 0.3,
      "color": "#FFFFFF",
      "transparency": { "start": 0.3, "end": 1 },
      "tween": { "ease": "QuadOut" }
    },
    {
      "id": "block_sparks",
      "type": "ParticleEmitter",
      "role": "MOTION",
      "texture": "sparkle.png",
      "lifetime": 0.2,
      "size": 0.5,
      "rate": 0,
      "burst": { "Low": 8, "Medium": 15, "High": 25 },
      "color": "#00FFFF",
      "lightEmission": 0.7,
      "speed": 20,
      "spread": 60
    }
  ]
}
```

### 6.2 Shield_Parry (Perfect)
```json
{
  "name": "Shield_Parry",
  "category": "Defensive",
  "duration": 0.6,
  "anchor": "Attachment:ShieldCenter",
  "layers": [
    {
      "id": "parry_flash",
      "type": "ParticleEmitter",
      "role": "CORE",
      "texture": "sparkles_main.dds",
      "lifetime": 0.1,
      "size": 3,
      "rate": 0,
      "burst": { "Low": 10, "Medium": 20, "High": 30 },
      "color": "#FFFFFF",
      "lightEmission": 1.0
    },
    {
      "id": "directional_burst",
      "type": "ParticleEmitter",
      "role": "IMPACT",
      "texture": "slash_streak.png",
      "lifetime": 0.15,
      "size": { "start": 5, "end": 0 },
      "rate": 0,
      "burst": { "Low": 5, "Medium": 10, "High": 15 },
      "color": "#00FFFF",
      "lightEmission": 0.8,
      "speed": 40,
      "spread": 20,
      "emissionDirection": "Front"
    }
  ]
}
```

---

## 7. ENVIRONMENTAL AMBIENCE

### 7.1 Ambient_Motes
```json
{
  "name": "Ambient_Motes",
  "category": "Environment",
  "duration": "looping",
  "anchor": "WorldVolume",
  "palette": { "mote": "#FFFFAA" },
  "layers": [
    {
      "id": "floating_motes",
      "type": "ParticleEmitter",
      "role": "ATMOSPHERE",
      "texture": "sparkles_main.dds",
      "lifetime": { "min": 5, "max": 15 },
      "size": { "start": 0.2, "end": 0.1 },
      "rate": 2,
      "color": "#FFFFAA",
      "lightEmission": 0.4,
      "speed": { "min": 0.1, "max": 0.5 },
      "spread": 360,
      "shape": "Box",
      "shapeSize": { "x": 50, "y": 30, "z": 50 }
    }
  ]
}
```

### 7.2 Fire_Ambient
```json
{
  "name": "Fire_Ambient",
  "category": "Environment",
  "duration": "looping",
  "anchor": "Attachment:FireSource",
  "palette": { "flame": "#FF9436", "smoke": "#3D1A0F", "ember": "#AE2D19" },
  "layers": [
    {
      "id": "flame",
      "type": "ParticleEmitter",
      "role": "SILHOUETTE",
      "texture": "fire_main.dds",
      "lifetime": { "min": 0.5, "max": 1.2 },
      "size": { "start": 1.5, "end": 0.2 },
      "rate": 15,
      "color": "#FF9436",
      "lightEmission": 0.4,
      "speed": { "min": 2, "max": 8 },
      "spread": 30,
      "emissionDirection": "Top",
      "acceleration": { "y": 10 },
      "drag": 0.3
    },
    {
      "id": "smoke",
      "type": "ParticleEmitter",
      "role": "ATMOSPHERE",
      "texture": "smoke_main.dds",
      "lifetime": { "min": 2, "max": 4 },
      "size": { "start": 2, "end": 6 },
      "rate": 5,
      "color": "#3D1A0F",
      "lightEmission": 0.05,
      "speed": { "min": 1, "max": 3 },
      "spread": 45,
      "drag": 0.4
    },
    {
      "id": "embers",
      "type": "ParticleEmitter",
      "role": "MOTION",
      "texture": "sparkles_main.dds",
      "lifetime": { "min": 1, "max": 3 },
      "size": 0.3,
      "rate": 3,
      "color": "#AE2D19",
      "lightEmission": 0.3,
      "speed": { "min": 1, "max": 5 },
      "spread": 180
    }
  ]
}
```

---

## 8. UI FEEDBACK VFX

### 8.1 UI_Hover_Glow
```json
{
  "name": "UI_Hover_Glow",
  "category": "UI_Feedback",
  "duration": 0.2,
  "anchor": "GuiObject",
  "screenSpace": true,
  "layers": [
    {
      "id": "glow_pulse",
      "type": "ImageLabel",
      "role": "CORE",
      "image": "radial_gradient.png",
      "size": { "start": { "x": 1, "y": 1 }, "end": { "x": 1.2, "y": 1.2 } },
      "lifetime": 0.2,
      "color": "#FFFFFF",
      "transparency": { "start": 0.7, "end": 1 },
      "tween": { "ease": "QuadOut" }
    }
  ]
}
```

### 8.2 UI_Click_Burst
```json
{
  "name": "UI_Click_Burst",
  "category": "UI_Feedback",
  "duration": 0.3,
  "anchor": "GuiObject",
  "screenSpace": true,
  "layers": [
    {
      "id": "burst_particles",
      "type": "ParticleEmitter",
      "role": "MOTION",
      "texture": "sparkle.png",
      "lifetime": 0.3,
      "size": { "start": 8, "end": 0 },
      "rate": 0,
      "burst": { "Low": 6, "Medium": 12, "High": 18 },
      "color": "#FFFFFF",
      "lightEmission": 0.6,
      "speed": 100,
      "spread": 360
    }
  ]
}
```

### 8.3 UI_Error_Shake
```json
{
  "name": "UI_Error_Shake",
  "category": "UI_Feedback",
  "duration": 0.4,
  "anchor": "GuiObject",
  "screenSpace": true,
  "procedural": true,
  "shake": { "magnitude": 10, "frequency": 30, "duration": 0.3, "ease": "QuadOut" },
  "flash": { "color": "#FF3333", "duration": 0.1 }
}
```

---

## QUALITY TIER SCALING

```lua
-- Applied automatically by VFXController based on user settings / device tier
QualityTierMultipliers = {
  Low = {
    particleCount = 0.4,
    lifetime = 0.7,
    lightCount = 0,
    meshComplexity = 0.5,
    enableTrails = false,
    enableBeams = true,
    maxConcurrentEffects = 20
  },
  Medium = {
    particleCount = 1.0,
    lifetime = 1.0,
    lightCount = 1,
    meshComplexity = 1.0,
    enableTrails = true,
    enableBeams = true,
    maxConcurrentEffects = 50
  },
  High = {
    particleCount = 1.8,
    lifetime = 1.3,
    lightCount = 2,
    meshComplexity = 1.5,
    enableTrails = true,
    enableBeams = true,
    maxConcurrentEffects = 100
  }
}
```

---

## STYLE VARIANT PALETTES

| Style | Fire Core | Fire Edge | Slash Core | Slash Edge | Magic Core | Impact Core |
|---|---|---|---|---|---|---|
| **Cartoony** | #FFD700 | #FF6B35 | #FFFFFF | #FF6B35 | #4ECDC4 | #FFD700 |
| **Anime** | #FF4444 | #FF8800 | #00FFFF | #0088FF | #FF006E | #FFFFFF |
| **Horror** | #4AFF00 | #228800 | #FF3333 | #8B0000 | #9B59B6 | #4AFF00 |
| **Tactical** | #FF8800 | #CC4400 | #FFFFFF | #00B4D8 | #00B4D8 | #FFFFFF |
| **Fantasy** | #FFD700 | #F39C12 | #FFD700 | #9B59B6 | #9B59B6 | #FFD700 |
| **Sci-Fi** | #00FFFF | #0088FF | #00FFFF | #FF00FF | #00FFFF | #FFFFFF |
| **Minimal** | #FFFFFF | #CCCCCC | #FFFFFF | #000000 | #00D4FF | #FFFFFF |

---

*Each recipe includes: layered composition, quality tiers, timeline, style palettes, and anchor specs. Ready for VFXController.Spawn() or CompositionPlayer.*