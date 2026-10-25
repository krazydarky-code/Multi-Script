> Adapted reference specification. Pseudocode, illustrative IDs and suggested budgets below are not installed components or verified assets. Use the reviewed modules / Forge where applicable; implement and test missing behavior in the actual project.

# OMNI-GUI Unified Animation Pose Recipes

> Merged from Animation Engineering, ProjectGUI, and MultiVFX skills. Each recipe defines key poses, timing, and marker placement for procedural generation or Animation Editor authoring.

---

## 1. LOCOMOTION POSES

### 1.1 Idle (Breathing)
```json
{
  "name": "Idle_Breathing",
  "loop": true,
  "duration": 4.0,
  "priority": "Idle",
  "poses": [
    { "time": 0.00, "description": "Inhale start - chest expanded, shoulders up" },
    { "time": 1.00, "description": "Inhale peak - maximum chest expansion" },
    { "time": 1.50, "description": "Hold - subtle tension in core" },
    { "time": 2.00, "description": "Exhale start - chest compresses, shoulders drop" },
    { "time": 3.00, "description": "Exhale peak - relaxed, slight forward lean" },
    { "time": 3.50, "description": "Hold - moment of stillness" },
    { "time": 4.00, "description": "Match pose 0.00 for seamless loop" }
  ],
  "joints": {
    "Spine": { "rx": [-2, 2], "ry": [-1, 1] },
    "Neck": { "rx": [-3, 1] },
    "Shoulders": { "rx": [-5, 5] },
    "Hips": { "ry": [-2, 2] }
  },
  "markers": [
    { "name": "InhalePeak", "time": 1.0 },
    { "name": "ExhalePeak", "time": 3.0 }
  ],
  "styleVariants": {
    "bouncy": { "verticalBob": 0.15, "ease": "SineInOut" },
    "weighted": { "verticalBob": 0.05, "ease": "QuadInOut", "breathingDepth": 0.6 },
    "tactical": { "verticalBob": 0.02, "ease": "Linear", "weaponSway": true },
    "horror": { "verticalBob": 0.03, "ease": "SineInOut", "jitter": 0.5, "unevenShoulders": true }
  }
}
```

### 1.2 Walk Cycle
```json
{
  "name": "Walk",
  "loop": true,
  "duration": 1.0,
  "priority": "Movement",
  "speed": 8,
  "poses": [
    { "time": 0.00, "description": "Contact - right heel strike, left toe off" },
    { "time": 0.12, "description": "Down - right knee flexed, weight transfer" },
    { "time": 0.25, "description": "Passing - right leg vertical, left swinging through" },
    { "time": 0.37, "description": "Up - right leg pushing, body rising" },
    { "time": 0.50, "description": "Contact - left heel strike (mirror of 0.00)" },
    { "time": 0.62, "description": "Down - left knee flexed" },
    { "time": 0.75, "description": "Passing - left leg vertical" },
    { "time": 0.87, "description": "Up - left leg pushing" },
    { "time": 1.00, "description": "Match 0.00" }
  ],
  "armSwing": { "amplitude": 30, "phaseOffset": 0.5 },
  "spineRotation": { "amplitude": 4, "phaseOffset": 0.0 },
  "verticalBob": { "amplitude": 0.08, "frequency": 2 },
  "markers": [
    { "name": "Footstep", "time": 0.00, "param": "Right" },
    { "name": "Footstep", "time": 0.50, "param": "Left" }
  ],
  "styleVariants": {
    "bouncy": { "strideLength": 1.15, "armSwing": 1.3, "verticalBob": 0.12, "kneeLift": 1.2, "ease": "BackOut" },
    "weighted": { "strideLength": 0.95, "armSwing": 0.9, "verticalBob": 0.05, "kneeLift": 0.8, "footPlacementIK": true },
    "tactical": { "strideLength": 1.0, "armSwing": 0.7, "verticalBob": 0.03, "weaponReady": true },
    "horror": { "strideLength": 0.9, "armSwing": 0.6, "verticalBob": 0.04, "limp": { "leg": "Left", "severity": 0.3 } },
    "creature_quadruped": { "gait": "trot", "phaseOffsets": [0.0, 0.5, 0.25, 0.75], "spineWave": 0.15 }
  }
}
```

### 1.3 Run Cycle
```json
{
  "name": "Run",
  "loop": true,
  "duration": 0.65,
  "priority": "Movement",
  "speed": 16,
  "poses": [
    { "time": 0.00, "description": "Flight phase start - both feet off ground" },
    { "time": 0.10, "description": "Right contact - high impact, knee drive" },
    { "time": 0.20, "description": "Right mid-stance - maximum compression" },
    { "time": 0.30, "description": "Right toe-off - explosive extension" },
    { "time": 0.35, "description": "Flight phase - both feet off" },
    { "time": 0.45, "description": "Left contact (mirror)" },
    { "time": 0.55, "description": "Left mid-stance" },
    { "time": 0.65, "description": "Left toe-off" },
    { "time": 1.00, "description": "Match 0.00" }
  ],
  "armSwing": { "amplitude": 45, "phaseOffset": 0.5, "elbowFlex": 90 },
  "spineRotation": { "amplitude": 6 },
  "verticalBob": { "amplitude": 0.12, "frequency": 2 },
  "markers": [
    { "name": "Footstep", "time": 0.10, "param": "Right" },
    { "name": "Footstep", "time": 0.45, "param": "Left" }
  ],
  "styleVariants": {
    "bouncy": { "flightTime": 0.15, "kneeDrive": 1.3, "armPump": 1.4, "ease": "BackOut" },
    "weighted": { "flightTime": 0.08, "kneeDrive": 1.0, "armPump": 1.0, "impactAbsorption": true },
    "anime": { "flightTime": 0.20, "kneeDrive": 1.5, "armPump": 1.6, "speedLines": true }
  }
}
```

### 1.4 Sprint
```json
{
  "name": "Sprint",
  "loop": true,
  "duration": 0.5,
  "priority": "Action",
  "speed": 24,
  "poses": [
    { "time": 0.00, "description": "Full extension - maximum stride" },
    { "time": 0.15, "description": "Contact - violent impact, forward lean 15°" },
    { "time": 0.30, "description": "Push-off - triple extension" },
    { "time": 0.40, "description": "Recovery - aggressive knee drive" },
    { "time": 0.50, "description": "Match 0.00" }
  ],
  "forwardLean": 15,
  "armSwing": { "amplitude": 60, "fixedElbow": 90 },
  "markers": [
    { "name": "Footstep", "time": 0.15, "param": "Right" },
    { "name": "Footstep", "time": 0.40, "param": "Left" },
    { "name": "HeavyBreathing", "time": 0.0 }
  ],
  "styleVariants": {
    "tactical": { "weaponLowReady": true, "controlledBreathing": true },
    "horror": { "panicked": true, "armsWide": true, "stumbleChance": 0.1 }
  }
}
```

### 1.5 Jump / Fall / Land
```json
{
  "name": "Jump",
  "loop": false,
  "duration": 0.5,
  "priority": "Movement",
  "phases": {
    "anticipation": { "duration": 0.10, "pose": "crouch", "compression": 0.4 },
    "takeoff": { "duration": 0.08, "pose": "explosive_extension", "armSwing": "up" },
    "airborne": { "duration": "variable", "pose": "tuck", "control": "minimal" },
    "landing": { "duration": 0.15, "pose": "absorb", "compression": 0.5 },
    "recovery": { "duration": 0.20, "pose": "stand" }
  },
  "markers": [
    { "name": "JumpVFX", "time": 0.10 },
    { "name": "LandVFX", "time": "landing_start" },
    { "name": "Land", "time": "recovery_end" }
  ],
  "styleVariants": {
    "bouncy": { "squash": 0.7, "stretch": 1.3, "landingBounce": 0.15 },
    "weighted": { "squash": 0.5, "stretch": 1.1, "landingAbsorb": 0.3, "ikFeet": true },
    "tactical": { "tacticalRoll": { "trigger": "height>10", "duration": 0.6 } }
  }
}
```

---

## 2. COMBAT POSES

### 2.1 Light Attack (1-2-3 Combo)
```json
{
  "name": "LightAttack_1",
  "loop": false,
  "duration": 0.6,
  "priority": "Action",
  "phases": {
    "anticipation": { "time": 0.00, "duration": 0.10, "pose": "chamber", "shoulder": -30, "elbow": 90 },
    "active": { "time": 0.10, "duration": 0.12, "pose": "extend", "shoulder": 80, "elbow": 160, "wrist": -20 },
    "followThrough": { "time": 0.22, "duration": 0.10, "pose": "overshoot", "shoulder": 100, "elbow": 170 },
    "recovery": { "time": 0.32, "duration": 0.28, "pose": "return_to_guard" }
  },
  "hitbox": { "activeStart": 0.10, "activeEnd": 0.22, "range": 6, "angle": 60 },
  "markers": [
    { "name": "Swing", "time": 0.10 },
    { "name": "Impact", "time": 0.16 },
    { "name": "ComboWindow", "time": 0.35 }
  ],
  "combo": { "next": "LightAttack_2", "window": [0.35, 0.55] },
  "styleVariants": {
    "bouncy": { "overshoot": 15, "recoilBounce": true, "speed": 1.2 },
    "anime": { "chamber": 0.15, "flashStep": { "distance": 4, "time": 0.05 }, "impactFreeze": 0.08 },
    "tactical": { "chamber": 0.08, "minimalWindup": true, "recoveryCancel": 0.20 },
    "horror": { "chamber": 0.20, "heavy": true, "staggerOnHit": true }
  }
}
```

### 2.2 Heavy Attack
```json
{
  "name": "HeavyAttack",
  "loop": false,
  "duration": 1.2,
  "priority": "Action2",
  "phases": {
    "windup": { "time": 0.00, "duration": 0.35, "pose": "full_body_windup", "rotation": -90, "weightShift": "back" },
    "commit": { "time": 0.35, "duration": 0.05, "pose": "point_of_no_return" },
    "swing": { "time": 0.40, "duration": 0.18, "pose": "maximum_extension", "rotation": 120 },
    "impact": { "time": 0.58, "duration": 0.10, "pose": "hit_stop", "freeze": 0.08 },
    "followThrough": { "time": 0.68, "duration": 0.20, "pose": "carry_through", "rotation": 150 },
    "recovery": { "time": 0.88, "duration": 0.32, "pose": "vulnerable_recovery" }
  },
  "hitbox": { "activeStart": 0.40, "activeEnd": 0.68, "range": 7, "angle": 90, "damageMult": 2.5 },
  "markers": [
    { "name": "WindupStart", "time": 0.00 },
    { "name": "SwingVFX", "time": 0.35 },
    { "name": "Impact", "time": 0.58 },
    { "name": "RecoveryStart", "time": 0.88 }
  ],
  "styleVariants": {
    "anime": { "windup": 0.50, "chargeParticles": true, "screenShake": 0.15, "timeDilation": 0.1 },
    "visceral": { "fullBodyCommit": true, "weightShift": 1.0, "groundCrackVFX": true },
    "exaggerated": { "rotation": 150, "followThrough": 0.30, "secondaryMotion": "hair_cloth" }
  }
}
```

### 2.3 Hit React (Stagger)
```json
{
  "name": "HitReact_Stagger",
  "loop": false,
  "duration": 0.8,
  "priority": "Action3",
  "directional": true,
  "poses": [
    { "time": 0.00, "description": "Impact frame - snap to hit direction" },
    { "time": 0.05, "description": "Maximum displacement - spine curved, arms flung" },
    { "time": 0.15, "description": "Rebound - elastic return begins" },
    { "time": 0.40, "description": "Overshoot - slight opposite lean" },
    { "time": 0.60, "description": "Settle - return to guard" },
    { "time": 0.80, "description": "Ready" }
  ],
  "blendFrom": "any",
  "invincibilityFrames": 0.3,
  "markers": [
    { "name": "HitVFX", "time": 0.00 },
    { "name": "HitSound", "time": 0.00 },
    { "name": "InvincibilityEnd", "time": 0.30 }
  ],
  "styleVariants": {
    "anime": { "hitPause": 0.12, "speedLines": true, "flashWhite": 0.05 },
    "visceral": { "ragdollBlend": 0.3, "bloodSpurt": true, "slowRecovery": 1.2 },
    "tactical": { "flinchOnly": { "threshold": "damage<15", "duration": 0.15 }, "armorAbsorb": true },
    "horror": { "jitter": true, "glitchFrames": 3, "audioDistort": true }
  }
}
```

### 2.4 Parry / Perfect Block
```json
{
  "name": "Parry",
  "loop": false,
  "duration": 0.6,
  "priority": "Action4",
  "phases": {
    "preparation": { "time": 0.00, "duration": 0.05, "pose": "guard_up" },
    "active": { "time": 0.05, "duration": 0.15, "pose": "deflect", "weaponAngle": 45 },
    "success": { "time": 0.20, "duration": 0.10, "pose": "counter_ready", "flash": true },
    "recovery": { "time": 0.30, "duration": 0.30, "pose": "advantage_state" }
  },
  "parryWindow": [0.05, 0.20],
  "markers": [
    { "name": "ParryVFX", "time": 0.10 },
    { "name": "ParrySound", "time": 0.10 },
    { "name": "CounterWindow", "time": 0.20 }
  ],
  "styleVariants": {
    "anime": { "sparkBurst": true, "timeStop": 0.06, "cameraZoom": 1.1 },
    "tactical": { "minimalFlash": true, "audioCue": "metallic_clang", "riposteReady": true }
  }
}
```

---

## 3. INTERACTION POSES

### 3.1 Equip / Unequip
```json
{
  "name": "Equip_Sword",
  "loop": false,
  "duration": 0.7,
  "priority": "Action",
  "phases": {
    "reach": { "time": 0.00, "duration": 0.15, "pose": "hand_to_hip", "ikTarget": "Sheath" },
    "draw": { "time": 0.15, "duration": 0.15, "pose": "pull_out", "weaponTrail": true },
    "ready": { "time": 0.30, "duration": 0.20, "pose": "guard_stance", "bothHands": true },
    "settle": { "time": 0.50, "duration": 0.20, "pose": "idle_armed" }
  },
  "markers": [
    { "name": "EquipVFX", "time": 0.15 },
    { "name": "WeaponVisible", "time": 0.20 },
    { "name": "EquipSound", "time": 0.15 },
    { "name": "Ready", "time": 0.50 }
  ],
  "unequip": { "reverse": true, "duration": 0.5, "markers": ["UnequipVFX", "WeaponHidden"] }
}
```

### 3.2 Interact / Use Item
```json
{
  "name": "Interact_Pickup",
  "loop": false,
  "duration": 0.8,
  "priority": "Action",
  "phases": {
    "approach": { "time": 0.00, "duration": 0.20, "pose": "step_forward", "ikFoot": "target" },
    "reach": { "time": 0.20, "duration": 0.15, "pose": "extend_arm", "ikHand": "item" },
    "grasp": { "time": 0.35, "duration": 0.10, "pose": "close_hand", "attachItem": true },
    "lift": { "time": 0.45, "duration": 0.15, "pose": "stand_up", "itemFollows": true },
    "inspect": { "time": 0.60, "duration": 0.20, "pose": "hold_up", "cameraFocus": "item" }
  },
  "markers": [
    { "name": "GraspVFX", "time": 0.35 },
    { "name": "PickupSound", "time": 0.40 }
  ]
}
```

---

## 4. CINEMATIC / EMOTE POSES

### 4.1 Emote Wave
```json
{
  "name": "Emote_Wave",
  "loop": false,
  "duration": 2.0,
  "priority": "Action2",
  "poses": [
    { "time": 0.00, "description": "Raise arm" },
    { "time": 0.20, "description": "Wave peak - wrist rotation" },
    { "time": 0.40, "description": "Wave down" },
    { "time": 0.60, "description": "Wave peak" },
    { "time": 0.80, "description": "Wave down" },
    { "time": 1.00, "description": "Lower arm" },
    { "time": 2.00, "description": "Return to idle" }
  ],
  "markers": [
    { "name": "WaveVFX", "time": 0.20 },
    { "name": "WaveVFX", "time": 0.60 }
  ]
}
```

### 4.2 Cinematic Look At
```json
{
  "name": "Cinematic_LookAt",
  "loop": false,
  "duration": "variable",
  "priority": "Action4",
  "procedural": true,
  "ikTargets": {
    "Head": { "weight": 1.0, "smoothTime": 0.15, "clampYaw": 80, "clampPitch": 45 },
    "Spine": { "weight": 0.3, "smoothTime": 0.25 },
    "Eyes": { "weight": 1.0, "smoothTime": 0.05 }
  },
  "markers": [
    { "name": "FocusTarget", "time": 0.0 }
  ]
}
```

---

## 5. CREATURE POSES

### 5.1 Quadruped Walk
```json
{
  "name": "Creature_Walk",
  "loop": true,
  "duration": 1.2,
  "priority": "Movement",
  "gait": "walk",
  "legPhases": { "FL": 0.0, "FR": 0.5, "BL": 0.25, "BR": 0.75 },
  "spineWave": { "amplitude": 8, "frequency": 1, "phase": 0 },
  "headBob": { "amplitude": 0.05, "frequency": 2 },
  "tailFollow": { "segments": 8, "delay": 0.05, "stiffness": 0.7 },
  "markers": [
    { "name": "Footstep", "time": 0.00, "param": "FL" },
    { "name": "Footstep", "time": 0.25, "param": "BL" },
    { "name": "Footstep", "time": 0.50, "param": "FR" },
    { "name": "Footstep", "time": 0.75, "param": "BR" }
  ]
}
```

### 5.2 Quadruped Run (Gallop)
```json
{
  "name": "Creature_Gallop",
  "loop": true,
  "duration": 0.7,
  "priority": "Movement",
  "gait": "gallop",
  "legPhases": { "FL": 0.0, "FR": 0.05, "BL": 0.5, "BR": 0.55 },
  "spineExtension": { "gather": 0.15, "extend": 0.25 },
  "airTime": 0.20,
  "markers": [
    { "name": "Footstep", "time": 0.00, "param": "FL" },
    { "name": "Footstep", "time": 0.05, "param": "FR" },
    { "name": "Footstep", "time": 0.50, "param": "BL" },
    { "name": "Footstep", "time": 0.55, "param": "BR" }
  ]
}
```

---

## 6. FACIAL POSES (Dynamic Head)

### 6.1 Expression Library
```json
{
  "expressions": {
    "neutral": { "JawDrop": 0, "LeftEyeClosed": 0, "RightEyeClosed": 0, "Brows": 0 },
    "happy": { "JawDrop": 0.1, "LeftEyeClosed": 0.1, "RightEyeClosed": 0.1, "LeftBrowRaiser": 0.5, "RightBrowRaiser": 0.5, "MouthSmile": 0.8 },
    "angry": { "JawDrop": 0.1, "LeftEyeClosed": 0.3, "RightEyeClosed": 0.3, "LeftBrowLowerer": 0.8, "RightBrowLowerer": 0.8, "MouthFrown": 0.6 },
    "surprised": { "JawDrop": 0.7, "LeftEyeClosed": -0.3, "RightEyeClosed": -0.3, "LeftBrowRaiser": 1.0, "RightBrowRaiser": 1.0 },
    "fear": { "JawDrop": 0.3, "LeftEyeClosed": 0.1, "RightEyeClosed": 0.1, "LeftBrowRaiser": 0.7, "RightBrowRaiser": 0.7, "EyeWide": 0.5 },
    "disgust": { "JawDrop": 0.1, "LeftEyeClosed": 0.2, "RightEyeClosed": 0.2, "NoseWrinkle": 0.6, "MouthUpperLipRaise": 0.5 },
    "sad": { "JawDrop": 0.1, "LeftEyeClosed": 0.4, "RightEyeClosed": 0.4, "LeftBrowLowerer": 0.3, "RightBrowLowerer": 0.3, "MouthFrown": 0.7 },
    "combat_focus": { "JawDrop": 0.05, "LeftEyeClosed": 0.2, "RightEyeClosed": 0.2, "LeftBrowLowerer": 0.4, "RightBrowLowerer": 0.4 },
    "pain": { "JawDrop": 0.5, "LeftEyeClosed": 0.7, "RightEyeClosed": 0.7, "LeftBrowLowerer": 0.6, "RightBrowLowerer": 0.6 },
    "dead": { "JawDrop": 0.3, "LeftEyeClosed": 1.0, "RightEyeClosed": 1.0, "LeftBrowLowerer": 0, "RightBrowLowerer": 0 }
  },
  "transitions": {
    "default": 0.3,
    "combat": 0.1,
    "cinematic": 0.5
  }
}
```

---

## 7. ANIMATION GRAPH PARAMETERS

### 7.1 Locomotion Graph
```json
{
  "graphName": "LocomotionGraph",
  "parameters": [
    { "name": "Speed", "type": "float", "range": [0, 24], "default": 0 },
    { "name": "Direction", "type": "float", "range": [-180, 180], "default": 0 },
    { "name": "Grounded", "type": "bool", "default": true },
    { "name": "Injured", "type": "bool", "default": false },
    { "name": "WeaponEquipped", "type": "bool", "default": false },
    { "name": "Crouching", "type": "bool", "default": false }
  ],
  "nodes": {
    "Idle": { "clip": "Idle_Breathing", "conditions": "Speed < 1" },
    "Walk": { "clip": "Walk", "conditions": "Speed >= 1 && Speed < 10", "speedParam": "Speed" },
    "Run": { "clip": "Run", "conditions": "Speed >= 10 && Speed < 20", "speedParam": "Speed" },
    "Sprint": { "clip": "Sprint", "conditions": "Speed >= 20", "speedParam": "Speed" },
    "JumpStart": { "clip": "Jump_Anticipation", "conditions": "!Grounded && Speed > 0" },
    "JumpAir": { "clip": "Jump_Airborne", "conditions": "!Grounded" },
    "Land": { "clip": "Jump_Land", "conditions": "Grounded && prev:!Grounded" }
  },
  "transitions": {
    "Idle→Walk": { "duration": 0.2, "sync": true },
    "Walk→Run": { "duration": 0.15, "sync": true },
    "Run→Sprint": { "duration": 0.1, "sync": true },
    "Any→Jump": { "duration": 0.05 },
    "Land→Idle": { "duration": 0.2 }
  }
}
```

### 7.2 Combat Graph
```json
{
  "graphName": "CombatGraph",
  "parameters": [
    { "name": "AttackPhase", "type": "int", "range": [0, 3], "default": 0 },
    { "name": "ComboStep", "type": "int", "range": [0, 3], "default": 0 },
    { "name": "HitReacting", "type": "bool", "default": false },
    { "name": "Stamina", "type": "float", "range": [0, 100], "default": 100 }
  ],
  "nodes": {
    "CombatIdle": { "clip": "Combat_Idle", "conditions": "AttackPhase==0 && !HitReacting" },
    "Light1": { "clip": "LightAttack_1", "conditions": "AttackPhase==1 && ComboStep==0" },
    "Light2": { "clip": "LightAttack_2", "conditions": "AttackPhase==1 && ComboStep==1" },
    "Light3": { "clip": "LightAttack_3", "conditions": "AttackPhase==1 && ComboStep==2" },
    "Heavy": { "clip": "HeavyAttack", "conditions": "AttackPhase==2" },
    "HitReact": { "clip": "HitReact_Stagger", "conditions": "HitReacting" },
    "Parry": { "clip": "Parry", "conditions": "AttackPhase==3" }
  }
}
```

---

## 8. PROCEDURAL LAYER SPECS

### 8.1 Head Look-at (IK)
```lua
-- Applied in PreSimulation after Animator evaluation
HeadLookAt = {
  target = "LookTarget", -- Attachment or Part
  weight = 1.0,
  smoothTime = 0.08,
  clampYaw = 80,
  clampPitch = 45,
  eyeWeight = 1.0,
  spineWeight = 0.3,
  spineSmoothTime = 0.2
}
```

### 8.2 Weapon Recoil (Spring)
```lua
WeaponRecoil = {
  impulse = { pitch = -3, yaw = 1, roll = 0 }, -- degrees
  frequency = 12, -- Hz
  damping = 0.8,
  maxRecoil = { pitch = 15, yaw = 8 },
  recoveryTime = 0.3
}
```

### 8.3 Breathing Idle (Additive)
```lua
BreathingIdle = {
  spineAmplitude = 0.02, -- radians
  chestAmplitude = 0.05,
  frequency = 0.25, -- Hz (4 second cycle)
  phaseOffset = 0
}
```

---

## STYLE VARIANT SUMMARY

| Style | Locomotion | Combat | Idle | HitReact | Facial |
|---|---|---|---|---|---|
| **Bouncy/Cartoony** | BackOut ease, 1.2x stride, high arm swing | Exaggerated, overshoot, bounce | High vertical bob, 4s cycle | Hit pause, speed lines, squash | Expressive, large eyes |
| **Weighted/Realistic** | QuadInOut, IK feet, 0.95 stride | Visceral, full body, slow recovery | Low bob, breathing, subtle sway | Ragdoll blend, blood, slow | Micro-expressions only |
| **Anime** | Long flight, 1.5x knee drive | Charge time, flash step, time dilation | Subtle, occasional blink | Hit pause 0.12s, flash white | Sharp, dramatic |
| **Tactical** | Controlled, weapon ready | Minimal windup, cancel windows | Still, tactical breathing | Flinch threshold, armor absorb | Focused, narrowed eyes |
| **Horror** | Uneven, limp, stumble | Heavy, delayed, stagger | Jitter, uneven, glitch | Jitter, glitch frames, audio distort | Fear/pain, wide eyes |

---

*Each pose recipe includes: keyframes, joint ranges, timing, markers, hitboxes, and style variants. Feed to Animation Editor or procedural generator.*