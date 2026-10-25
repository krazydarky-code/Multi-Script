# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender "pro" tools for engine_toolkit: animation, rigging, shape keys, procedural materials,
scattering, terrain, particle VFX, curves, mesh cleanup, studio/turntable setup, buildings, level
blockout and physics. Each compiles to one Python program run through blender-mcp's
`execute_blender_code` and verified against a real headless Blender (see tests/test_native_pro_tools.py)."""
from engine_toolkit import tool, as_list, as_dict, vec3, num, boolean, ToolkitError
from toolkit_blender import _exec, _names, OBJ, VEC, NAMES

B = "blender"
EASING = ["LINEAR", "BEZIER", "SINE", "QUAD", "CUBIC", "QUART", "EXPO", "ELASTIC", "BOUNCE", "BACK", "CONSTANT"]
MOTIONS = ["bounce", "spin", "bob", "pulse", "shake", "orbit", "pendulum", "pop_in", "float", "wobble", "slide", "swing_door"]


def _norm(args, **defaults):
    a = dict(args)
    for k, v in defaults.items():
        if a.get(k) is None:
            a[k] = v
    return a


# ─────────────────────────────── animation ───────────────────────────────
@tool(B, "ms_blender_motion_preset",
      "Animate objects with a named motion preset in one call (keyframes + interpolation + optional looping): bounce, spin, bob, pulse, shake, orbit, "
      "pendulum, pop_in (overshoot scale-in), float, wobble, slide, swing_door. Handles staggering many objects, easing, amplitude and axis. "
      "Great for props, logos, pickups, UI-in-3D and turntables. Replaces existing keys on the touched channels unless clear_existing=false.",
      {"objects": NAMES, "preset": {"type": "string", "enum": MOTIONS}, "start_frame": {"type": "integer"},
       "duration_frames": {"type": "integer", "minimum": 2, "maximum": 5000, "description": "Length of ONE cycle (default 48)."},
       "loops": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Repeat count baked as keys; with cyclic=true it repeats forever instead."},
       "cyclic": {"type": "boolean", "description": "Add a Cycles F-modifier so the motion loops forever (default true for looping presets)."},
       "amplitude": {"type": "number", "description": "Distance (m) / angle (deg) / scale factor depending on the preset (default per preset)."},
       "axis": {"type": "string", "enum": ["x", "y", "z"], "description": "Axis for spin/bob/pendulum/slide (default z; pendulum default x)."},
       "easing": {"type": "string", "enum": EASING}, "stagger_frames": {"type": "integer", "description": "Frame offset between successive objects."},
       "center": VEC, "seed": {"type": "integer"}, "clear_existing": {"type": "boolean"}, "set_frame_range": {"type": "boolean"}},
      ["objects", "preset"], writes=True)
def motion_preset(args, ctx):
    a = _norm(args, start_frame=1, duration_frames=48, loops=1, easing="BEZIER", seed=1)
    a["objects"] = _names(a, "objects", "object", "names")
    a["preset"] = str(a.get("preset") or "").lower()
    if a["preset"] not in MOTIONS:
        raise ToolkitError(f"unknown preset '{a['preset']}'", "Use one of: " + ", ".join(MOTIONS))
    if not a["objects"]:
        raise ToolkitError("objects is required")
    return _exec(ctx, a, '''
        import random
        P = A["preset"]; start = int(A["start_frame"]); dur = max(2, int(A["duration_frames"])); loops = max(1, int(A["loops"]))
        ease = str(A.get("easing") or "BEZIER").upper()
        axis = {"x": 0, "y": 1, "z": 2}[str(A.get("axis") or ("x" if P == "pendulum" else "z")).lower()]
        defaults = {"bounce": 0.6, "bob": 0.15, "float": 0.2, "spin": 360.0, "pulse": 0.25, "shake": 0.05, "orbit": 1.5,
                    "pendulum": 25.0, "pop_in": 1.15, "wobble": 8.0, "slide": 2.0, "swing_door": 100.0}
        amp = float(A["amplitude"]) if A.get("amplitude") is not None else defaults[P]
        cyc = A.get("cyclic")
        cyc = (P in ("spin", "bob", "float", "pulse", "orbit", "pendulum", "wobble", "shake")) if cyc is None else bool(cyc)
        rng = random.Random(int(A["seed"]))
        touched = []
        def key(o, path, idx, f, val):
            if path == "location": o.location[idx] = val
            elif path == "rotation_euler": o.rotation_euler[idx] = val
            elif path == "scale": o.scale[idx] = val
            o.keyframe_insert(data_path=path, index=idx, frame=f)
        def finish(o, channels):
            ad = o.animation_data
            for fc in _fcurves(ad.action if ad else None):
                if (fc.data_path, fc.array_index) not in channels: continue
                for kp in fc.keyframe_points:
                    if P in ("spin", "slide", "orbit", "swing_door") and ease in ("BEZIER",):
                        kp.interpolation = "LINEAR" if P in ("spin", "orbit") else "BEZIER"
                    elif ease == "LINEAR": kp.interpolation = "LINEAR"
                    elif ease == "CONSTANT": kp.interpolation = "CONSTANT"
                    elif ease == "BEZIER": kp.interpolation = "BEZIER"
                    else:
                        kp.interpolation = ease
                        kp.easing = "EASE_IN_OUT"
                if cyc:
                    if not any(m.type == "CYCLES" for m in fc.modifiers): fc.modifiers.new("CYCLES")
                fc.update()
        for n, name in enumerate(A["objects"]):
            o = _obj(name)
            off = start + n * int(A.get("stagger_frames") or 0)
            loc0 = o.location.copy(); rot0 = o.rotation_euler.copy(); sc0 = o.scale.copy()
            if A.get("clear_existing", True) and o.animation_data and o.animation_data.action:
                ch = {"bounce": ["location"], "bob": ["location"], "float": ["location", "rotation_euler"], "slide": ["location"], "orbit": ["location"],
                      "spin": ["rotation_euler"], "pendulum": ["rotation_euler"], "swing_door": ["rotation_euler"], "wobble": ["rotation_euler"],
                      "pulse": ["scale"], "pop_in": ["scale"], "shake": ["location"]}[P]
                for fc in list(_fcurves(o.animation_data.action)):
                    if fc.data_path in ch:
                        try: o.animation_data.action.fcurves.remove(fc)
                        except Exception:
                            try: fc.keyframe_points.clear()
                            except Exception: pass
            steps = max(8, min(96, dur // 2)) if P not in ("spin", "slide", "swing_door", "pop_in") else 2
            chan = set()
            total = dur * (1 if cyc else loops)
            def sample(fn, path, idxs):
                for L in range(1 if cyc else loops):
                    for s in range(steps + 1):
                        if L > 0 and s == 0: continue
                        t = s / steps
                        f = off + L * dur + round(t * dur)
                        for i in idxs:
                            key(o, path, i, f, fn(t, i))
                for i in idxs: chan.add((path, i))
            if P == "bounce":
                sample(lambda t, i: loc0[2] + amp * abs(math.sin(math.pi * t)), "location", [2])
                # squash/stretch hint: tiny scale change at contact
                sample(lambda t, i: sc0[i] * (1.0 + 0.12 * (1 - abs(math.sin(math.pi * t))) * (1 if i != 2 else -1)), "scale", [0, 1, 2])
            elif P == "bob":
                sample(lambda t, i: loc0[axis] + amp * math.sin(2 * math.pi * t), "location", [axis])
            elif P == "float":
                sample(lambda t, i: loc0[2] + amp * math.sin(2 * math.pi * t), "location", [2])
                sample(lambda t, i: rot0[i] + math.radians(3.0) * math.sin(2 * math.pi * t + i), "rotation_euler", [0, 1])
            elif P == "spin":
                for L in range(1 if cyc else loops):
                    key(o, "rotation_euler", axis, off + L * dur, rot0[axis] + math.radians(amp) * L)
                    key(o, "rotation_euler", axis, off + (L + 1) * dur, rot0[axis] + math.radians(amp) * (L + 1))
                chan.add(("rotation_euler", axis))
            elif P == "pulse":
                sample(lambda t, i: sc0[i] * (1 + amp * 0.5 * (1 - math.cos(2 * math.pi * t))), "scale", [0, 1, 2])
            elif P == "shake":
                cache = {}
                def shk(t, i):
                    k = (round(t * steps), i)
                    if t >= 1.0 or k[0] == 0: return loc0[i]
                    if k not in cache: cache[k] = loc0[i] + rng.uniform(-amp, amp)
                    return cache[k]
                sample(shk, "location", [0, 1, 2])
            elif P == "orbit":
                c = A.get("center")
                cx, cy = (c[0], c[1]) if c else (loc0[0], loc0[1])
                cz = c[2] if c else loc0[2]
                def orb(t, i):
                    a0 = 2 * math.pi * t
                    return [cx + amp * math.cos(a0), cy + amp * math.sin(a0), cz][i]
                steps = max(steps, 24); sample(orb, "location", [0, 1, 2])
            elif P == "pendulum":
                sample(lambda t, i: rot0[axis] + math.radians(amp) * math.sin(2 * math.pi * t), "rotation_euler", [axis])
            elif P == "wobble":
                sample(lambda t, i: rot0[i] + math.radians(amp) * math.sin(2 * math.pi * t + i * 1.7), "rotation_euler", [0, 1])
            elif P == "pop_in":
                for i in range(3):
                    key(o, "scale", i, off, 0.0)
                    key(o, "scale", i, off + max(1, int(dur * 0.6)), sc0[i] * amp)
                    key(o, "scale", i, off + dur, sc0[i])
                    chan.add(("scale", i))
            elif P == "slide":
                key(o, "location", axis, off, loc0[axis]); key(o, "location", axis, off + dur, loc0[axis] + amp); chan.add(("location", axis))
            elif P == "swing_door":
                key(o, "rotation_euler", 2, off, rot0[2]); key(o, "rotation_euler", 2, off + dur, rot0[2] + math.radians(amp)); chan.add(("rotation_euler", 2))
            finish(o, chan)
            touched.append({"name": o.name, "frames": [off, off + total], "channels": sorted({c[0] for c in chan})})
        last = max(t["frames"][1] for t in touched)
        if A.get("set_frame_range", True):
            sc = bpy.context.scene
            sc.frame_start = min(sc.frame_start, start); sc.frame_end = max(last, sc.frame_start + 1)
        bpy.context.scene.frame_set(start)
        R["preset"] = P; R["cyclic"] = cyc; R["objects"] = touched
        R["frame_range"] = [bpy.context.scene.frame_start, bpy.context.scene.frame_end]
    ''', "motion preset " + a["preset"])


@tool(B, "ms_blender_animation_actions",
      "Manage animation Actions and NLA: action=list|create|assign|unassign|rename|duplicate|delete|fake_user|frame_range|cyclic|nla_push|nla_list|bake. "
      "Use it to organise clips (idle/walk/run), assign one to an object, push clips to NLA tracks for blending/export, loop them, or bake constraints/physics to keys.",
      {"action": {"type": "string", "enum": ["list", "create", "assign", "unassign", "rename", "duplicate", "delete", "fake_user", "frame_range", "cyclic", "nla_push", "nla_list", "bake"]},
       "object": OBJ, "action_name": {"type": "string"}, "new_name": {"type": "string"}, "frame_start": {"type": "integer"}, "frame_end": {"type": "integer"},
       "track": {"type": "string", "description": "NLA track name for nla_push."}, "value": {"type": "boolean", "description": "fake_user / cyclic value (default true)."}},
      ["action"], writes=True)
def animation_actions(args, ctx):
    a = _norm(args, value=True)
    a["action"] = str(a.get("action") or "list").lower()
    return _exec(ctx, a, '''
        act = A["action"]; name = A.get("action_name")
        def get_action(n):
            x = bpy.data.actions.get(n)
            if x is None: raise ValueError("no action %r (actions: %s)" % (n, ", ".join(bpy.data.actions.keys()) or "none"))
            return x
        def rng(x):
            try: return [round(x.frame_range[0], 2), round(x.frame_range[1], 2)]
            except Exception: return None
        def row(x):
            return {"name": x.name, "users": x.users, "fake_user": x.use_fake_user, "fcurves": len(_fcurves(x)), "frame_range": rng(x), "loop": bool(getattr(x, "use_cyclic", False))}
        if act == "list":
            R["actions"] = [row(x) for x in bpy.data.actions]
            R["assigned"] = {o.name: o.animation_data.action.name for o in bpy.data.objects if o.animation_data and o.animation_data.action}
        elif act == "create":
            if not name: raise ValueError("action_name is required")
            x = bpy.data.actions.new(name); x.use_fake_user = True
            if A.get("object"):
                o = _obj(A["object"]); o.animation_data_create(); o.animation_data.action = x
            R["created"] = row(x)
        elif act == "assign":
            o = _obj(A.get("object")); o.animation_data_create(); o.animation_data.action = get_action(name); R["assigned"] = row(o.animation_data.action)
        elif act == "unassign":
            o = _obj(A.get("object"))
            if o.animation_data: o.animation_data.action = None
            R["unassigned"] = o.name
        elif act == "rename":
            x = get_action(name); x.name = A["new_name"]; R["renamed"] = x.name
        elif act == "duplicate":
            x = get_action(name).copy()
            if A.get("new_name"): x.name = A["new_name"]
            x.use_fake_user = True; R["duplicate"] = row(x)
        elif act == "delete":
            x = get_action(name); bpy.data.actions.remove(x); R["deleted"] = name
        elif act == "fake_user":
            x = get_action(name); x.use_fake_user = bool(A.get("value", True)); R["action"] = row(x)
        elif act == "frame_range":
            x = get_action(name)
            if A.get("frame_start") is not None and A.get("frame_end") is not None:
                x.use_frame_range = True; x.frame_start = A["frame_start"]; x.frame_end = A["frame_end"]
            R["action"] = row(x)
        elif act == "cyclic":
            x = get_action(name or (_obj(A["object"]).animation_data.action.name))
            try: x.use_cyclic = bool(A.get("value", True))
            except Exception: pass
            for fc in _fcurves(x):
                has = [m for m in fc.modifiers if m.type == "CYCLES"]
                if A.get("value", True) and not has: fc.modifiers.new("CYCLES")
                if not A.get("value", True):
                    for m in has: fc.modifiers.remove(m)
            R["action"] = row(x)
        elif act == "nla_push":
            o = _obj(A.get("object")); ad = o.animation_data
            if ad is None: raise ValueError("object has no animation data")
            x = get_action(name) if name else ad.action
            if x is None: raise ValueError("no action to push")
            tr = ad.nla_tracks.new(); tr.name = A.get("track") or x.name
            start = int(A.get("frame_start") if A.get("frame_start") is not None else (rng(x) or [1])[0])
            st = tr.strips.new(x.name, start, x)
            if ad.action == x: ad.action = None
            R["track"] = tr.name; R["strip"] = {"name": st.name, "frame_start": st.frame_start, "frame_end": st.frame_end}
        elif act == "nla_list":
            rows = []
            for o in bpy.data.objects:
                if o.animation_data:
                    for t in o.animation_data.nla_tracks:
                        rows.append({"object": o.name, "track": t.name, "strips": [{"name": s.name, "start": s.frame_start, "end": s.frame_end} for s in t.strips]})
            R["tracks"] = rows
        elif act == "bake":
            o = _obj(A.get("object")); _select([o], o); sc = bpy.context.scene
            fs = int(A.get("frame_start") if A.get("frame_start") is not None else sc.frame_start); fe = int(A.get("frame_end") if A.get("frame_end") is not None else sc.frame_end)
            with bpy.context.temp_override(selected_objects=[o], active_object=o, object=o):
                bpy.ops.nla.bake(frame_start=fs, frame_end=fe, only_selected=True, visual_keying=True, clear_constraints=False, use_current_action=True, bake_types={"OBJECT"})
            R["baked"] = o.name; R["frames"] = [fs, fe]
        else:
            raise ValueError("unknown action " + act)
    ''', "animation actions " + a["action"])


@tool(B, "ms_blender_shape_keys",
      "Shape keys (blend shapes / morph targets): action=list|add|set|keyframe|remove|range|mute. `add` creates the Basis if missing and optionally copies the current mix; "
      "`set` writes values {key: 0..1}; `keyframe` inserts keys on those values at a frame (blink, smile, jaw-open timelines).",
      {"action": {"type": "string", "enum": ["list", "add", "set", "keyframe", "remove", "range", "mute"]}, "object": OBJ,
       "name": {"type": "string"}, "from_mix": {"type": "boolean"}, "values": {"type": "object", "description": "{shape_key_name: value}"},
       "frame": {"type": "integer"}, "slider_min": {"type": "number"}, "slider_max": {"type": "number"}, "value": {"type": "boolean"}},
      ["action", "object"], writes=True)
def shape_keys(args, ctx):
    a = _norm(args, action="list")
    return _exec(ctx, a, '''
        o = _obj(A["object"]); act = str(A["action"]).lower()
        if o.type not in ("MESH", "CURVE", "SURFACE", "LATTICE"): raise ValueError("shape keys need a mesh/curve/lattice object")
        def rows():
            sk = o.data.shape_keys
            if not sk: return []
            return [{"name": k.name, "value": round(k.value, 4), "min": k.slider_min, "max": k.slider_max, "mute": k.mute, "relative_to": k.relative_key.name} for k in sk.key_blocks]
        if act == "add":
            if not o.data.shape_keys: o.shape_key_add(name="Basis", from_mix=False)
            nm = A.get("name") or "Key %d" % len(o.data.shape_keys.key_blocks)
            o.shape_key_add(name=nm, from_mix=bool(A.get("from_mix", False)))
            R["added"] = nm
        elif act in ("set", "keyframe"):
            sk = o.data.shape_keys
            if not sk: raise ValueError("object has no shape keys")
            for k, v in (A.get("values") or {}).items():
                kb = sk.key_blocks.get(k)
                if kb is None: raise ValueError("no shape key %r (keys: %s)" % (k, ", ".join(sk.key_blocks.keys())))
                kb.value = float(v)
                if act == "keyframe": kb.keyframe_insert("value", frame=int(A.get("frame", bpy.context.scene.frame_current)))
            R["frame"] = A.get("frame")
        elif act == "remove":
            sk = o.data.shape_keys; kb = sk.key_blocks.get(A.get("name")) if sk else None
            if kb is None: raise ValueError("no such shape key")
            o.shape_key_remove(kb); R["removed"] = A.get("name")
        elif act == "range":
            kb = o.data.shape_keys.key_blocks.get(A.get("name"))
            if kb is None: raise ValueError("no such shape key")
            if A.get("slider_min") is not None: kb.slider_min = float(A["slider_min"])
            if A.get("slider_max") is not None: kb.slider_max = float(A["slider_max"])
        elif act == "mute":
            kb = o.data.shape_keys.key_blocks.get(A.get("name"))
            if kb is None: raise ValueError("no such shape key")
            kb.mute = bool(A.get("value", True))
        R["shape_keys"] = rows()
    ''', "shape keys " + str(a["action"]))


_HUMANOID = [  # name, head(x,y,z) tail, parent  (unit = fraction of height; +x = character's left; -y = forward)
    ("hips", (0, 0, .52), (0, 0, .58), None), ("spine", (0, 0, .58), (0, 0, .68), "hips"), ("chest", (0, 0, .68), (0, 0, .80), "spine"),
    ("neck", (0, 0, .80), (0, 0, .86), "chest"), ("head", (0, 0, .86), (0, 0, .98), "neck"),
    ("shoulder.L", (.02, 0, .79), (.07, 0, .79), "chest"), ("upper_arm.L", (.07, 0, .79), (.20, 0, .79), "shoulder.L"),
    ("forearm.L", (.20, 0, .79), (.33, 0, .79), "upper_arm.L"), ("hand.L", (.33, 0, .79), (.40, 0, .79), "forearm.L"),
    ("thigh.L", (.05, 0, .52), (.05, 0, .28), "hips"), ("shin.L", (.05, 0, .28), (.05, 0, .05), "thigh.L"),
    ("foot.L", (.05, 0, .05), (.05, -.12, .0), "shin.L"), ("toe.L", (.05, -.12, .0), (.05, -.17, .0), "foot.L"),
]
_PRESET_RIGS = {
    "humanoid": _HUMANOID,
    "spine_chain": [("spine.%03d" % i, (0, 0, i * .1), (0, 0, (i + 1) * .1), None if i == 0 else "spine.%03d" % (i - 1)) for i in range(8)],
    "tail": [("tail.%03d" % i, (0, i * .12, 0), (0, (i + 1) * .12, 0), None if i == 0 else "tail.%03d" % (i - 1)) for i in range(6)],
    "quadruped": [("hips", (0, .35, .55), (0, .2, .55), None), ("spine", (0, .2, .55), (0, -.1, .58), "hips"), ("chest", (0, -.1, .58), (0, -.35, .6), "spine"),
                  ("neck", (0, -.35, .6), (0, -.5, .75), "chest"), ("head", (0, -.5, .75), (0, -.65, .75), "neck"), ("tail", (0, .35, .55), (0, .65, .5), "hips"),
                  ("front_leg.L", (.1, -.3, .55), (.1, -.3, .3), "chest"), ("front_lower.L", (.1, -.3, .3), (.1, -.3, 0), "front_leg.L"),
                  ("back_leg.L", (.1, .3, .55), (.1, .33, .3), "hips"), ("back_lower.L", (.1, .33, .3), (.1, .3, 0), "back_leg.L")],
}


@tool(B, "ms_blender_armature_rig",
      "Rigging in one call: action=create|list|pose|bind|ik|mirror|remove. `create` builds an Armature from preset (humanoid, spine_chain, tail, quadruped) "
      "or an explicit `bones` list [{name, head, tail, parent, roll}], scaled to `height`; `bind` parents meshes with automatic weights; `pose` sets bone rotations (deg) "
      "and optionally keyframes them; `ik` adds an IK constraint (chain_count, optional pole); `mirror` symmetrises .L bones to .R.",
      {"action": {"type": "string", "enum": ["create", "list", "pose", "bind", "ik", "mirror", "remove"]}, "name": {"type": "string", "description": "Armature object name."},
       "preset": {"type": "string", "enum": sorted(_PRESET_RIGS)}, "bones": {"type": "array", "items": {"type": "object"}}, "height": {"type": "number", "description": "Total height in metres for presets (default 1.8)."},
       "location": VEC, "bind_to": NAMES, "pose": {"type": "object", "description": "{bone: [rx, ry, rz] degrees}"}, "frame": {"type": "integer", "description": "Keyframe the pose at this frame."},
       "bone": {"type": "string"}, "target": {"type": "string", "description": "IK target object name (an empty is created when omitted)."}, "chain_count": {"type": "integer"},
       "pole": {"type": "string"}, "relative": {"type": "boolean", "description": "pose: add to the rest pose (default true)."}},
      ["action"], writes=True)
def armature_rig(args, ctx):
    a = _norm(args, action="create", name="Armature", height=1.8)
    a["action"] = str(a["action"]).lower()
    if a["action"] == "create":
        pr = str(a.get("preset") or ("humanoid" if not a.get("bones") else "")).lower()
        if pr and pr not in _PRESET_RIGS:
            raise ToolkitError(f"unknown preset {pr}", "Use: " + ", ".join(sorted(_PRESET_RIGS)))
        a["_bones"] = [{"name": n, "head": h, "tail": t, "parent": p} for n, h, t, p in _PRESET_RIGS[pr]] if pr and not a.get("bones") else None
        a["_unit"] = float(a["height"]) if pr in ("humanoid",) else (float(a["height"]) / 1.8 if pr else 1.0)
    return _exec(ctx, a, '''
        act = A["action"]
        def arm_obj():
            o = bpy.data.objects.get(A.get("name"))
            if o is None or o.type != "ARMATURE": raise ValueError("no armature object named %r" % A.get("name"))
            return o
        if act == "create":
            bones = A.get("_bones") or A.get("bones")
            if not bones: raise ValueError("give a preset or a bones list")
            unit = float(A.get("_unit") or 1.0) if A.get("_bones") else 1.0
            _mode_object()
            data = bpy.data.armatures.new(A["name"]); obj = bpy.data.objects.new(A["name"], data)
            bpy.context.scene.collection.objects.link(obj)
            obj.location = _v(A.get("location"))
            bpy.context.view_layer.objects.active = obj; _select([obj], obj)
            bpy.ops.object.mode_set(mode="EDIT")
            eb = data.edit_bones
            for b in bones:
                e = eb.new(b["name"]); e.head = [c * unit for c in b["head"]]; e.tail = [c * unit for c in b["tail"]]
                if b.get("roll") is not None: e.roll = math.radians(b["roll"])
            for b in bones:
                if b.get("parent"):
                    p = eb.get(b["parent"])
                    if p is None: raise ValueError("bone %r: unknown parent %r" % (b["name"], b["parent"]))
                    eb[b["name"]].parent = p
                    eb[b["name"]].use_connect = (eb[b["name"]].head - p.tail).length < 1e-4
            bpy.ops.object.mode_set(mode="OBJECT")
            obj.show_in_front = True
            R["armature"] = obj.name; R["bones"] = [b.name for b in data.bones]
            if A.get("bind_to"):
                meshes = [_obj(n) for n in A["bind_to"]]
                _select(meshes + [obj], obj)
                with bpy.context.temp_override(selected_objects=meshes + [obj], active_object=obj, object=obj):
                    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
                R["bound"] = [m.name for m in meshes]; R["vertex_groups"] = {m.name: len(m.vertex_groups) for m in meshes}
        elif act == "list":
            rows = []
            for o in bpy.data.objects:
                if o.type == "ARMATURE":
                    rows.append({"name": o.name, "bones": [{"name": b.name, "parent": b.parent.name if b.parent else None, "head": [round(c, 3) for c in b.head_local], "tail": [round(c, 3) for c in b.tail_local]} for b in o.data.bones]})
            R["armatures"] = rows
        elif act == "bind":
            obj = arm_obj(); meshes = [_obj(n) for n in (A.get("bind_to") or [])]
            if not meshes: raise ValueError("bind_to (mesh names) is required")
            _select(meshes + [obj], obj)
            with bpy.context.temp_override(selected_objects=meshes + [obj], active_object=obj, object=obj):
                bpy.ops.object.parent_set(type="ARMATURE_AUTO")
            R["bound"] = [m.name for m in meshes]; R["vertex_groups"] = {m.name: len(m.vertex_groups) for m in meshes}
        elif act == "pose":
            obj = arm_obj(); done = []
            for bn, rot in (A.get("pose") or {}).items():
                pb = obj.pose.bones.get(bn)
                if pb is None: raise ValueError("no bone %r (bones: %s)" % (bn, ", ".join(obj.pose.bones.keys())))
                pb.rotation_mode = "XYZ"
                e = _rad(rot)
                pb.rotation_euler = e
                if A.get("frame") is not None: pb.keyframe_insert("rotation_euler", frame=int(A["frame"]))
                done.append(bn)
            R["posed"] = done
        elif act == "ik":
            obj = arm_obj(); bone = obj.pose.bones.get(A.get("bone"))
            if bone is None: raise ValueError("bone is required (the end of the chain)")
            tgt = bpy.data.objects.get(A.get("target")) if A.get("target") else None
            if tgt is None:
                tgt = bpy.data.objects.new((A.get("bone") or "ik") + "_IK", None); bpy.context.scene.collection.objects.link(tgt)
                tgt.empty_display_type = "SPHERE"; tgt.empty_display_size = 0.1
                tgt.location = obj.matrix_world @ bone.tail
            c = bone.constraints.new("IK"); c.target = tgt; c.chain_count = int(A.get("chain_count") or 2)
            if A.get("pole"):
                c.pole_target = _obj(A["pole"])
            R["ik_target"] = tgt.name; R["chain_count"] = c.chain_count
        elif act == "mirror":
            obj = arm_obj(); _select([obj], obj); bpy.ops.object.mode_set(mode="EDIT")
            eb = obj.data.edit_bones; made = []
            for b in list(eb):
                if b.name.endswith(".L") and eb.get(b.name[:-2] + ".R") is None:
                    n = eb.new(b.name[:-2] + ".R"); n.head = (-b.head.x, b.head.y, b.head.z); n.tail = (-b.tail.x, b.tail.y, b.tail.z); n.roll = -b.roll; made.append((n.name, b.parent.name if b.parent else None))
            for n, p in made:
                if p:
                    pn = p[:-2] + ".R" if p.endswith(".L") else p
                    if eb.get(pn): eb[n].parent = eb[pn]
            bpy.ops.object.mode_set(mode="OBJECT"); R["created"] = [m[0] for m in made]
        elif act == "remove":
            obj = arm_obj(); bpy.data.objects.remove(obj, do_unlink=True); R["removed"] = A.get("name")
        else:
            raise ValueError("unknown action " + act)
    ''', "armature " + a["action"])


# ─────────────────────────────── materials ───────────────────────────────
MATERIALS = ["wood", "marble", "brick", "brushed_metal", "gold", "copper", "chrome", "rock", "concrete", "grass", "sand", "snow", "water", "lava",
             "glass", "neon", "toon", "plastic", "fabric", "rubber", "ice", "leather"]


@tool(B, "ms_blender_procedural_material",
      "Create a ready-to-render PROCEDURAL material (no image files) from a preset: wood, marble, brick, brushed_metal, gold, copper, chrome, rock, concrete, grass, sand, snow, "
      "water, lava, glass, neon, toon, plastic, fabric, rubber, ice, leather. Builds the node tree (texture coordinates, noise/voronoi/wave/brick, colour ramps, bump, Principled BSDF), "
      "and optionally assigns it to objects. Tune with color, color2, scale, roughness, bump and seed.",
      {"preset": {"type": "string", "enum": MATERIALS}, "name": {"type": "string"}, "assign_to": NAMES, "replace_slots": {"type": "boolean", "description": "Replace existing slots instead of appending (default true)."},
       "color": {"type": ["string", "array"], "description": "Main colour: #rrggbb or [r,g,b,(a)] 0-1."}, "color2": {"type": ["string", "array"], "description": "Second colour (veins, mortar, tint)."},
       "scale": {"type": "number", "description": "Texture scale (default 5)."}, "roughness": {"type": "number", "minimum": 0, "maximum": 1}, "bump": {"type": "number", "minimum": 0, "maximum": 3},
       "emission_strength": {"type": "number"}, "seed": {"type": "number"}},
      ["preset"], writes=True)
def procedural_material(args, ctx):
    a = _norm(args)
    a["preset"] = str(a.get("preset") or "").lower().replace(" ", "_")
    if a["preset"] not in MATERIALS:
        raise ToolkitError(f"unknown preset '{a['preset']}'", "Use: " + ", ".join(MATERIALS))
    a["assign_to"] = _names(a, "assign_to", "objects", "object")
    for k in ("color", "color2"):
        if a.get(k) is not None:
            from engine_toolkit import color4
            a[k] = list(color4(a[k]))
    return _exec(ctx, a, '''
        P = A["preset"]; name = A.get("name") or ("MS_" + P.title().replace("_", ""))
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        try: mat.use_nodes = True
        except Exception: pass
        nt = mat.node_tree
        for n in list(nt.nodes): nt.nodes.remove(n)
        N = nt.nodes; L = nt.links
        def node(t, x, y, **kw):
            n = N.new(t); n.location = (x, y)
            for k, v in kw.items(): setattr(n, k, v)
            return n
        def sock(n, *names):
            for nm in names:
                if nm in n.inputs: return n.inputs[nm]
            raise KeyError(names)
        def setv(n, names, v):
            for nm in names:
                if nm in n.inputs:
                    try: n.inputs[nm].default_value = v
                    except Exception: pass
                    return True
            return False
        def link(a, b): L.new(a, b)
        def ramp(stops, x=0, y=0):
            r = node("ShaderNodeValToRGB", x, y)
            el = r.color_ramp.elements
            while len(el) < len(stops): el.new(0.5)
            for e, (pos, col) in zip(el, stops):
                e.position = pos; e.color = col
            return r
        def rgba(c, d): return tuple(c) if c else d
        scale = float(A.get("scale") or 5.0); bump_s = float(A.get("bump") if A.get("bump") is not None else 0.3)
        seed = float(A.get("seed") or 0.0)
        out = node("ShaderNodeOutputMaterial", 900, 0)
        bsdf = node("ShaderNodeBsdfPrincipled", 600, 0)
        link(bsdf.outputs["BSDF"], out.inputs["Surface"])
        tc = node("ShaderNodeTexCoord", -900, 0); mp = node("ShaderNodeMapping", -700, 0)
        link(tc.outputs["Object"], mp.inputs["Vector"])
        if seed: mp.inputs["Location"].default_value = (seed, seed * 1.7, seed * 0.3)
        c1 = A.get("color"); c2 = A.get("color2")
        rough = A.get("roughness")
        def add_bump(fac_socket, strength, dist=0.1):
            b = node("ShaderNodeBump", 300, -250); b.inputs["Strength"].default_value = strength; b.inputs["Distance"].default_value = dist
            link(fac_socket, b.inputs["Height"]); link(b.outputs["Normal"], bsdf.inputs["Normal"]); return b
        def noise(sc, detail=5.0, rough_=0.55, x=-450, y=0, dim="3D"):
            n = node("ShaderNodeTexNoise", x, y); n.inputs["Scale"].default_value = sc; n.inputs["Detail"].default_value = detail; n.inputs["Roughness"].default_value = rough_
            link(mp.outputs["Vector"], n.inputs["Vector"]); return n
        R_ = 0.5
        if P == "wood":
            w = node("ShaderNodeTexWave", -450, 100, wave_type="RINGS", rings_direction="Z", wave_profile="SIN")
            w.inputs["Scale"].default_value = scale * 0.6; w.inputs["Distortion"].default_value = 6.0; w.inputs["Detail"].default_value = 3.0; w.inputs["Detail Scale"].default_value = 1.5
            link(mp.outputs["Vector"], w.inputs["Vector"])
            rp = ramp([(0.0, rgba(c2, (0.12, 0.06, 0.02, 1))), (1.0, rgba(c1, (0.45, 0.25, 0.1, 1)))], -150, 100)
            link(w.outputs["Color"], rp.inputs["Fac"]); link(rp.outputs["Color"], bsdf.inputs["Base Color"]); add_bump(w.outputs["Fac"], bump_s, 0.02); R_ = 0.55
        elif P == "marble":
            n = noise(scale * 0.8, 8.0, 0.6)
            w = node("ShaderNodeTexWave", -450, 200, wave_type="BANDS", bands_direction="DIAGONAL")
            w.inputs["Scale"].default_value = 2.0; w.inputs["Distortion"].default_value = 12.0; w.inputs["Detail"].default_value = 4.0
            link(mp.outputs["Vector"], w.inputs["Vector"])
            rp = ramp([(0.35, rgba(c1, (0.93, 0.92, 0.9, 1))), (0.62, rgba(c2, (0.2, 0.2, 0.24, 1)))], -150, 100)
            link(w.outputs["Fac"], rp.inputs["Fac"]); link(rp.outputs["Color"], bsdf.inputs["Base Color"]); R_ = 0.12; add_bump(n.outputs["Fac"], bump_s * 0.3, 0.01)
        elif P == "brick":
            b = node("ShaderNodeTexBrick", -450, 100)
            b.inputs["Scale"].default_value = scale * 0.8; b.inputs["Mortar Size"].default_value = 0.02; b.inputs["Brick Width"].default_value = 0.5; b.inputs["Row Height"].default_value = 0.25
            b.inputs["Color1"].default_value = rgba(c1, (0.45, 0.14, 0.09, 1)); b.inputs["Color2"].default_value = (0.36, 0.1, 0.07, 1); b.inputs["Mortar"].default_value = rgba(c2, (0.6, 0.58, 0.55, 1))
            link(mp.outputs["Vector"], b.inputs["Vector"]); link(b.outputs["Color"], bsdf.inputs["Base Color"])
            n = noise(scale * 8, 6.0)
            mix = node("ShaderNodeMath", -150, -200, operation="MULTIPLY"); link(b.outputs["Fac"], mix.inputs[0]); link(n.outputs["Fac"], mix.inputs[1])
            add_bump(mix.outputs[0], bump_s * 2.0, 0.05); R_ = 0.85
        elif P in ("brushed_metal", "chrome", "gold", "copper"):
            base = {"brushed_metal": (0.72, 0.73, 0.75, 1), "chrome": (0.9, 0.9, 0.92, 1), "gold": (1.0, 0.77, 0.34, 1), "copper": (0.95, 0.53, 0.38, 1)}[P]
            bsdf.inputs["Base Color"].default_value = rgba(c1, base); setv(bsdf, ["Metallic"], 1.0)
            if P != "chrome":
                mp.inputs["Scale"].default_value = (1.0, 80.0, 1.0)
                n = noise(scale * 6, 4.0, 0.7); add_bump(n.outputs["Fac"], bump_s * 0.4, 0.003)
            R_ = {"brushed_metal": 0.35, "chrome": 0.03, "gold": 0.25, "copper": 0.3}[P]
        elif P in ("rock", "concrete"):
            v = node("ShaderNodeTexVoronoi", -450, 150); v.inputs["Scale"].default_value = scale * (1.0 if P == "rock" else 3.0); link(mp.outputs["Vector"], v.inputs["Vector"])
            n = noise(scale * 4, 10.0, 0.65, -450, -100)
            mix = node("ShaderNodeMix", -200, 0, data_type="FLOAT"); mix.inputs[0].default_value = 0.5
            link(v.outputs["Distance"], mix.inputs[2]); link(n.outputs["Fac"], mix.inputs[3])
            dark = (0.1, 0.095, 0.09, 1) if P == "rock" else (0.35, 0.35, 0.34, 1); light = (0.42, 0.4, 0.37, 1) if P == "rock" else (0.6, 0.6, 0.58, 1)
            rp = ramp([(0.25, rgba(c2, dark)), (0.75, rgba(c1, light))], 0, 0)
            link(mix.outputs[1] if len(mix.outputs) > 1 else mix.outputs[0], rp.inputs["Fac"]); link(rp.outputs["Color"], bsdf.inputs["Base Color"])
            add_bump(mix.outputs[1] if len(mix.outputs) > 1 else mix.outputs[0], bump_s * (3.0 if P == "rock" else 0.8), 0.1); R_ = 0.9
        elif P in ("grass", "sand", "snow"):
            n = noise(scale * 10, 6.0)
            cols = {"grass": ((0.05, 0.18, 0.03, 1), (0.28, 0.5, 0.08, 1)), "sand": ((0.55, 0.42, 0.22, 1), (0.8, 0.68, 0.42, 1)), "snow": ((0.8, 0.85, 0.92, 1), (1, 1, 1, 1))}[P]
            rp = ramp([(0.3, rgba(c2, cols[0])), (0.7, rgba(c1, cols[1]))], -150, 0)
            link(n.outputs["Fac"], rp.inputs["Fac"]); link(rp.outputs["Color"], bsdf.inputs["Base Color"]); add_bump(n.outputs["Fac"], bump_s * 0.5, 0.02); R_ = {"grass": 0.9, "sand": 0.95, "snow": 0.6}[P]
            if P == "snow": setv(bsdf, ["Subsurface Weight", "Subsurface"], 0.2)
        elif P in ("water", "ice", "glass"):
            bsdf.inputs["Base Color"].default_value = rgba(c1, {"water": (0.1, 0.35, 0.5, 1), "ice": (0.75, 0.9, 1, 1), "glass": (1, 1, 1, 1)}[P])
            setv(bsdf, ["Transmission Weight", "Transmission"], 1.0); setv(bsdf, ["IOR"], {"water": 1.333, "ice": 1.31, "glass": 1.45}[P])
            if P != "glass":
                n = noise(scale * 2, 3.0, 0.5); add_bump(n.outputs["Fac"], bump_s * (0.4 if P == "water" else 0.8), 0.01)
            R_ = {"water": 0.02, "ice": 0.12, "glass": 0.03}[P]
            try: mat.blend_method = "BLEND"
            except Exception: pass
        elif P == "lava":
            n = noise(scale, 8.0, 0.7); v = node("ShaderNodeTexVoronoi", -450, -200); v.inputs["Scale"].default_value = scale * 0.7; link(mp.outputs["Vector"], v.inputs["Vector"])
            mix = node("ShaderNodeMix", -200, 0, data_type="FLOAT"); mix.inputs[0].default_value = 0.5; link(n.outputs["Fac"], mix.inputs[2]); link(v.outputs["Distance"], mix.inputs[3])
            rp = ramp([(0.2, (0.02, 0.0, 0.0, 1)), (0.5, rgba(c2, (1.0, 0.25, 0.0, 1))), (0.85, rgba(c1, (1.0, 0.85, 0.2, 1)))], 0, 0)
            link(mix.outputs[1] if len(mix.outputs) > 1 else mix.outputs[0], rp.inputs["Fac"]); link(rp.outputs["Color"], bsdf.inputs["Base Color"])
            link(rp.outputs["Color"], sock(bsdf, "Emission Color", "Emission")); setv(bsdf, ["Emission Strength"], float(A.get("emission_strength") or 3.0)); R_ = 0.6
        elif P == "neon":
            col = rgba(c1, (0.1, 0.9, 1.0, 1)); bsdf.inputs["Base Color"].default_value = col
            setv(bsdf, ["Emission Color", "Emission"], col); setv(bsdf, ["Emission Strength"], float(A.get("emission_strength") or 8.0)); R_ = 0.3
        elif P == "toon":
            diff = node("ShaderNodeBsdfDiffuse", 300, 200); diff.inputs["Color"].default_value = rgba(c1, (0.9, 0.35, 0.2, 1))
            s2r = node("ShaderNodeShaderToRGB", 450, 200); rp = ramp([(0.0, (0.25, 0.25, 0.25, 1)), (0.45, (0.6, 0.6, 0.6, 1)), (0.7, (1, 1, 1, 1))], 600, 200)
            for e in rp.color_ramp.elements: pass
            rp.color_ramp.interpolation = "CONSTANT"
            mulc = node("ShaderNodeMix", 750, 200, data_type="RGBA", blend_type="MULTIPLY"); mulc.inputs[0].default_value = 1.0
            mulc.inputs[7 if len(mulc.inputs) > 7 else 6].default_value = rgba(c1, (0.9, 0.35, 0.2, 1))
            link(diff.outputs["BSDF"], s2r.inputs["Shader"]); link(s2r.outputs["Color"], rp.inputs["Fac"])
            link(rp.outputs["Color"], mulc.inputs[6]); em = node("ShaderNodeEmission", 900, 200); link(mulc.outputs[2], em.inputs["Color"]); link(em.outputs["Emission"], out.inputs["Surface"])
        elif P in ("plastic", "rubber"):
            bsdf.inputs["Base Color"].default_value = rgba(c1, (0.8, 0.1, 0.1, 1)); R_ = 0.25 if P == "plastic" else 0.85
            setv(bsdf, ["Coat Weight", "Clearcoat"], 0.5 if P == "plastic" else 0.0)
        elif P == "fabric":
            bsdf.inputs["Base Color"].default_value = rgba(c1, (0.25, 0.3, 0.55, 1))
            w1 = node("ShaderNodeTexWave", -450, 100, wave_type="BANDS"); w1.inputs["Scale"].default_value = scale * 12; w1.inputs["Distortion"].default_value = 0.0; link(mp.outputs["Vector"], w1.inputs["Vector"])
            w2 = node("ShaderNodeTexWave", -450, -150, wave_type="BANDS", bands_direction="Y"); w2.inputs["Scale"].default_value = scale * 12; w2.inputs["Distortion"].default_value = 0.0; link(mp.outputs["Vector"], w2.inputs["Vector"])
            add_ = node("ShaderNodeMath", -200, 0, operation="ADD"); link(w1.outputs["Fac"], add_.inputs[0]); link(w2.outputs["Fac"], add_.inputs[1])
            add_bump(add_.outputs[0], bump_s * 0.6, 0.004); setv(bsdf, ["Sheen Weight", "Sheen"], 0.6); R_ = 0.9
        elif P == "leather":
            v = node("ShaderNodeTexVoronoi", -450, 0); v.inputs["Scale"].default_value = scale * 12; v.feature = "DISTANCE_TO_EDGE"; link(mp.outputs["Vector"], v.inputs["Vector"])
            bsdf.inputs["Base Color"].default_value = rgba(c1, (0.22, 0.1, 0.05, 1)); add_bump(v.outputs["Distance"], bump_s * 1.2, 0.01); R_ = 0.55
        if A.get("roughness") is not None: R_ = float(A["roughness"])
        setv(bsdf, ["Roughness"], R_)
        if P not in ("wood", "marble", "brick", "rock", "concrete", "grass", "sand", "snow", "lava", "toon", "water", "ice", "glass", "neon", "plastic", "rubber", "fabric", "leather") and c1:
            bsdf.inputs["Base Color"].default_value = tuple(c1)
        if P in ("plastic", "rubber", "fabric", "leather") and False: pass
        for o in [ _obj(n) for n in (A.get("assign_to") or []) ]:
            if o.type not in ("MESH", "CURVE", "SURFACE", "FONT", "META"): continue
            if A.get("replace_slots", True): o.data.materials.clear()
            o.data.materials.append(mat)
        R["material"] = mat.name; R["nodes"] = len(nt.nodes); R["links"] = len(nt.links); R["assigned"] = A.get("assign_to") or []
    ''', "procedural material " + a["preset"])


# ─────────────────────────────── scatter / terrain ───────────────────────────────
@tool(B, "ms_blender_scatter",
      "Scatter linked instances of a source object over the surface of a target mesh (trees, rocks, grass, debris): area-weighted random sampling, scale/rotation jitter, "
      "align to surface normal, slope and height limits, minimum spacing, into a named collection. Instances share mesh data so scenes stay light.",
      {"source": OBJ, "target": {"type": "string", "description": "Surface mesh object to scatter on."}, "count": {"type": "integer", "minimum": 1, "maximum": 20000},
       "seed": {"type": "integer"}, "scale_min": {"type": "number"}, "scale_max": {"type": "number"}, "random_z_rotation": {"type": "boolean"}, "align_to_normal": {"type": "boolean"},
       "max_slope_degrees": {"type": "number", "description": "Skip faces steeper than this (0 = flat, 90 = vertical)."}, "min_height": {"type": "number"}, "max_height": {"type": "number"},
       "min_distance": {"type": "number", "description": "Minimum spacing between instances (m)."}, "collection": {"type": "string"}, "hide_source": {"type": "boolean"}},
      ["source", "target"], writes=True)
def scatter(args, ctx):
    a = _norm(args, count=100, seed=1, scale_min=0.8, scale_max=1.2, random_z_rotation=True, align_to_normal=False, max_slope_degrees=90, collection="MS_Scatter")
    a["count"] = num(a.get("count"), 100, 1, 20000, True)
    return _exec(ctx, a, '''
        import random
        from mathutils import Vector, Quaternion, Matrix
        src = _obj(A["source"]); tgt = _obj(A["target"])
        if tgt.type != "MESH": raise ValueError("target must be a mesh")
        rng = random.Random(int(A["seed"]))
        me = tgt.data; me.calc_loop_triangles(); mw = tgt.matrix_world; nm = mw.to_3x3().inverted_safe().transposed()
        tris = []; total = 0.0
        maxs = math.radians(float(A["max_slope_degrees"]))
        for t in me.loop_triangles:
            vs = [mw @ me.vertices[i].co for i in t.vertices]
            n = (nm @ t.normal).normalized()
            if math.acos(max(-1.0, min(1.0, n.z))) > maxs: continue
            area = ((vs[1] - vs[0]).cross(vs[2] - vs[0])).length * 0.5
            if area <= 1e-9: continue
            tris.append((vs, n, area)); total += area
        if not tris: raise ValueError("no faces pass the slope filter")
        cum = []; s = 0.0
        for t in tris: s += t[2]; cum.append(s)
        import bisect
        col = bpy.data.collections.get(A["collection"]) or bpy.data.collections.new(A["collection"])
        if col.name not in bpy.context.scene.collection.children: bpy.context.scene.collection.children.link(col)
        placed = []; tries = 0; mind = float(A.get("min_distance") or 0.0); made = []
        while len(placed) < int(A["count"]) and tries < int(A["count"]) * 30:
            tries += 1
            vs, n, _a = tris[min(bisect.bisect_left(cum, rng.random() * s), len(tris) - 1)]
            u, v = rng.random(), rng.random()
            if u + v > 1: u, v = 1 - u, 1 - v
            p = vs[0] + (vs[1] - vs[0]) * u + (vs[2] - vs[0]) * v
            if A.get("min_height") is not None and p.z < float(A["min_height"]): continue
            if A.get("max_height") is not None and p.z > float(A["max_height"]): continue
            if mind > 0 and any((p - q).length < mind for q in placed[-400:]): continue
            sc = rng.uniform(float(A["scale_min"]), float(A["scale_max"]))
            rot = Quaternion((0, 0, 1), rng.uniform(0, math.tau)) if A.get("random_z_rotation", True) else Quaternion()
            if A.get("align_to_normal"): rot = Vector((0, 0, 1)).rotation_difference(n) @ rot
            inst = src.copy(); inst.name = src.name + "_s"
            if src.data is not None: inst.data = src.data
            inst.location = p; inst.rotation_mode = "QUATERNION"; inst.rotation_quaternion = rot; inst.scale = (sc, sc, sc) if True else inst.scale
            for c in list(inst.users_collection): c.objects.unlink(inst)
            col.objects.link(inst); placed.append(p); made.append(inst)
        if A.get("hide_source"): src.hide_set(True); src.hide_render = True
        R["placed"] = len(placed); R["requested"] = int(A["count"]); R["collection"] = col.name; R["attempts"] = tries
        if placed:
            R["bounds"] = {"min": [round(min(p[i] for p in placed), 3) for i in range(3)], "max": [round(max(p[i] for p in placed), 3) for i in range(3)]}
    ''', "scatter")


@tool(B, "ms_blender_terrain",
      "Generate a heightfield TERRAIN mesh: fractal noise (fBm / ridged), island falloff, smoothing passes, optional water plane and a height-based material "
      "(sand -> grass -> rock -> snow). Deterministic by seed. Returns min/max height and vertex count.",
      {"name": {"type": "string"}, "size": {"type": "number", "description": "Edge length in metres (default 100)."}, "resolution": {"type": "integer", "minimum": 8, "maximum": 512, "description": "Quads per side (default 96)."},
       "height": {"type": "number", "description": "Maximum relief in metres (default 12)."}, "noise_scale": {"type": "number", "description": "Larger = broader hills (default 40 m features)."},
       "octaves": {"type": "integer", "minimum": 1, "maximum": 10}, "roughness": {"type": "number"}, "ridged": {"type": "boolean"}, "island": {"type": "boolean", "description": "Fade the edges below sea level."},
       "smooth_passes": {"type": "integer", "minimum": 0, "maximum": 10}, "seed": {"type": "integer"}, "water": {"type": "boolean"}, "water_level": {"type": "number"}, "material": {"type": "boolean"},
       "location": VEC},
      writes=True)
def terrain(args, ctx):
    a = _norm(args, name="Terrain", size=100, resolution=96, height=12, noise_scale=40, octaves=5, roughness=0.5, seed=1, material=True)
    a["resolution"] = num(a.get("resolution"), 96, 8, 512, True)
    return _exec(ctx, a, '''
        import bmesh
        from mathutils import noise as mn, Vector
        size = float(A["size"]); res = int(A["resolution"]); H = float(A["height"]); ns = max(0.001, float(A["noise_scale"]))
        oct_ = int(A["octaves"]); rough = float(A["roughness"]); sd = float(A["seed"]) * 17.31
        def fbm(x, y):
            amp = 1.0; fr = 1.0 / ns; tot = 0.0; norm = 0.0
            for o in range(oct_):
                v = mn.noise(Vector((x * fr + sd, y * fr - sd, o * 3.7)))
                if A.get("ridged"): v = 1.0 - abs(v) * 2.0
                tot += v * amp; norm += amp; amp *= rough * 2 if rough < 0.5 else rough; fr *= 2.0
            return tot / norm
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=res, y_segments=res, size=size / 2.0)
        bm.verts.ensure_lookup_table()
        zs = []
        for v in bm.verts:
            h = fbm(v.co.x, v.co.y)
            if A.get("ridged"): h = (h + 1.0) * 0.5
            else: h = (h + 1.0) * 0.5
            if A.get("island"):
                d = max(abs(v.co.x), abs(v.co.y)) / (size / 2.0)
                h = h * max(0.0, min(1.0, 1.0 - (d - 0.55) / 0.45)) - 0.12 * (d > 0.9)
            zs.append(h)
        for _ in range(int(A.get("smooth_passes") or 0)):
            nz = zs[:]
            for v in bm.verts:
                nb = [zs[e.other_vert(v).index] for e in v.link_edges]
                if nb: nz[v.index] = (zs[v.index] + sum(nb) / len(nb)) * 0.5
            zs = nz
        lo = min(zs); hi = max(zs)
        for v, z in zip(bm.verts, zs): v.co.z = (z - lo) / max(1e-9, hi - lo) * H
        for f in bm.faces: f.smooth = True
        bm.normal_update()
        me = bpy.data.meshes.new(A["name"]); bm.to_mesh(me); bm.free()
        obj = bpy.data.objects.new(A["name"], me); bpy.context.scene.collection.objects.link(obj)
        obj.location = _v(A.get("location"))
        for p in me.polygons: p.use_smooth = True
        if A.get("material", True):
            mat = bpy.data.materials.new(A["name"] + "_Mat")
            try: mat.use_nodes = True
            except Exception: pass
            nt = mat.node_tree; b = nt.nodes.get("Principled BSDF")
            geo = nt.nodes.new("ShaderNodeNewGeometry"); sep = nt.nodes.new("ShaderNodeSeparateXYZ"); mr = nt.nodes.new("ShaderNodeMapRange")
            cr = nt.nodes.new("ShaderNodeValToRGB")
            nt.links.new(geo.outputs["Position"], sep.inputs[0]); nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
            mr.inputs["From Min"].default_value = 0.0; mr.inputs["From Max"].default_value = H; mr.inputs["To Min"].default_value = 0.0; mr.inputs["To Max"].default_value = 1.0
            nt.links.new(mr.outputs["Result"], cr.inputs["Fac"])
            el = cr.color_ramp.elements
            while len(el) < 5: el.new(0.5)
            for e, (pos, c) in zip(el, [(0.0, (0.55, 0.45, 0.28, 1)), (0.12, (0.2, 0.42, 0.1, 1)), (0.5, (0.15, 0.3, 0.07, 1)), (0.72, (0.38, 0.35, 0.32, 1)), (0.92, (0.95, 0.96, 1.0, 1))]):
                e.position = pos; e.color = c
            nt.links.new(cr.outputs["Color"], b.inputs["Base Color"]); b.inputs["Roughness"].default_value = 0.92
            me.materials.append(mat)
        R["object"] = obj.name; R["vertices"] = len(me.vertices); R["height_range"] = [round(min(v.co.z for v in me.vertices), 3), round(max(v.co.z for v in me.vertices), 3)]
        if A.get("water"):
            lvl = float(A["water_level"]) if A.get("water_level") is not None else H * 0.18
            bpy.ops.mesh.primitive_plane_add(size=size, location=(obj.location.x, obj.location.y, obj.location.z + lvl))
            w = bpy.context.active_object; w.name = A["name"] + "_Water"
            wm = bpy.data.materials.new(A["name"] + "_WaterMat")
            try: wm.use_nodes = True
            except Exception: pass
            wb = wm.node_tree.nodes.get("Principled BSDF"); wb.inputs["Base Color"].default_value = (0.05, 0.25, 0.4, 1); wb.inputs["Roughness"].default_value = 0.05
            for nm in ("Transmission Weight", "Transmission"):
                if nm in wb.inputs: wb.inputs[nm].default_value = 0.9; break
            w.data.materials.append(wm); R["water"] = w.name; R["water_level"] = round(lvl, 3)
    ''', "terrain")


# ─────────────────────────────── VFX / curves / cleanup ───────────────────────────────
VFX = ["fire", "smoke", "sparks", "magic", "rain", "snow", "dust", "embers", "fountain", "fireflies"]


@tool(B, "ms_blender_vfx_preset",
      "Create a particle VFX emitter from a preset: fire, smoke, sparks, magic, rain, snow, dust, embers, fountain, fireflies. Builds the emitter, ParticleSettings "
      "(count, lifetime, velocity, gravity, size, randomness) and an emissive instance object, in a VFX collection. Tune count/size/color/lifetime and the frame range; "
      "the system plays on the timeline and can be baked or rendered.",
      {"preset": {"type": "string", "enum": VFX}, "name": {"type": "string"}, "location": VEC, "count": {"type": "integer", "minimum": 1, "maximum": 200000},
       "size": {"type": "number", "description": "Particle size multiplier."}, "color": {"type": ["string", "array"]}, "lifetime": {"type": "number", "description": "Frames."},
       "emitter_size": {"type": "number"}, "frame_start": {"type": "integer"}, "frame_end": {"type": "integer"}, "seed": {"type": "integer"}},
      ["preset"], writes=True)
def vfx_preset(args, ctx):
    a = _norm(args)
    a["preset"] = str(a.get("preset") or "").lower()
    if a["preset"] not in VFX:
        raise ToolkitError(f"unknown preset '{a['preset']}'", "Use: " + ", ".join(VFX))
    if a.get("color") is not None:
        from engine_toolkit import color4
        a["color"] = list(color4(a["color"]))
    return _exec(ctx, a, '''
        P = A["preset"]
        # preset: count, life, normal vel, gravity (z), size, emitter shape, base color, emission strength, rand vel, shape of instance
        S = {"fire": (400, 28, 1.2, -0.25, 0.22, "plane", (1.0, 0.35, 0.05, 1), 12, 0.5),
             "smoke": (220, 90, 0.5, -0.05, 0.5, "plane", (0.25, 0.25, 0.25, 1), 0.3, 0.3),
             "sparks": (260, 30, 5.0, 1.0, 0.05, "ico", (1.0, 0.8, 0.3, 1), 18, 1.5),
             "magic": (300, 70, 1.2, -0.1, 0.07, "ico", (0.5, 0.3, 1.0, 1), 14, 0.8),
             "rain": (2500, 40, 0.0, 1.8, 0.03, "plane", (0.6, 0.75, 1.0, 1), 2, 0.05),
             "snow": (1800, 220, 0.0, 0.08, 0.05, "plane", (1, 1, 1, 1), 1.5, 0.15),
             "dust": (350, 160, 0.1, 0.0, 0.04, "plane", (0.8, 0.7, 0.55, 1), 0.5, 0.2),
             "embers": (200, 120, 0.8, -0.15, 0.04, "plane", (1.0, 0.45, 0.1, 1), 14, 0.5),
             "fountain": (900, 70, 4.5, 1.1, 0.06, "ico", (0.5, 0.75, 1.0, 1), 2, 0.6),
             "fireflies": (60, 240, 0.1, 0.0, 0.05, "plane", (0.8, 1.0, 0.3, 1), 20, 0.3)}[P]
        count, life, vel, grav, psize, shape, col, emis, rnd = S
        count = int(A.get("count") or count); life = float(A.get("lifetime") or life); psize *= float(A.get("size") or 1.0)
        if A.get("color"): col = tuple(A["color"])
        name = A.get("name") or ("VFX_" + P.title())
        size = float(A.get("emitter_size") or (6.0 if P in ("rain", "snow", "dust", "fireflies") else 0.5))
        loc = list(_v(A.get("location")))
        if P in ("rain", "snow"): loc[2] += 6.0
        if shape == "plane": bpy.ops.mesh.primitive_plane_add(size=size, location=loc)
        else: bpy.ops.mesh.primitive_ico_sphere_add(radius=size * 0.5, subdivisions=2, location=loc)
        em = bpy.context.active_object; em.name = name
        col_vfx = bpy.data.collections.get("MS_VFX") or bpy.data.collections.new("MS_VFX")
        if col_vfx.name not in bpy.context.scene.collection.children: bpy.context.scene.collection.children.link(col_vfx)
        # particle (instance) object: tiny emissive sphere
        bpy.ops.mesh.primitive_ico_sphere_add(radius=1.0, subdivisions=1, location=(0, 0, -1000))
        part = bpy.context.active_object; part.name = name + "_Particle"
        if P in ("rain",): part.scale = (0.06, 0.06, 0.9)
        pm = bpy.data.materials.new(name + "_Mat")
        try: pm.use_nodes = True
        except Exception: pass
        bsdf = pm.node_tree.nodes.get("Principled BSDF"); bsdf.inputs["Base Color"].default_value = col
        for nm in ("Emission Color", "Emission"):
            if nm in bsdf.inputs: bsdf.inputs[nm].default_value = col; break
        if "Emission Strength" in bsdf.inputs: bsdf.inputs["Emission Strength"].default_value = emis
        part.data.materials.append(pm)
        for o in (part,):
            for c in list(o.users_collection): c.objects.unlink(o)
            col_vfx.objects.link(o)
        try: bpy.context.view_layer.layer_collection.children[col_vfx.name].exclude = False
        except Exception: pass
        part.hide_render = False
        _select([em], em)
        ps_mod = em.modifiers.new(name + "_Particles", "PARTICLE_SYSTEM")
        ps = ps_mod.particle_system
        st = ps.settings; st.name = name + "_Settings"
        st.count = count; st.frame_start = int(A.get("frame_start") or bpy.context.scene.frame_start); st.frame_end = int(A.get("frame_end") or bpy.context.scene.frame_end)
        st.lifetime = max(1.0, life); st.lifetime_random = 0.4
        st.normal_factor = vel; st.factor_random = rnd; st.use_dynamic_rotation = False
        st.render_type = "OBJECT"; st.instance_object = part; st.particle_size = psize; st.size_random = 0.5
        st.effector_weights.gravity = abs(grav) if grav > 0 else 1.0
        st.physics_type = "NEWTON"; st.mass = 1.0
        # gravity: positive grav = fall (rain, fountain), negative = rise (fire, smoke)
        st.effector_weights.gravity = 1.0 if grav > 0.5 else 0.0
        if grav < 0 or 0 < grav <= 0.5:
            st.object_align_factor = (0.0, 0.0, grav * -1.0)
        st.use_rotations = P in ("sparks", "magic", "dust")
        if P in ("rain", "snow"): st.normal_factor = 0.0; st.object_align_factor = (0.0, 0.0, -vel) if P == "snow" else (0.0, 0.0, -2.0)
        if P in ("rain", "snow", "fountain", "sparks"): st.effector_weights.gravity = 1.0 if P != "snow" else 0.05
        try: st.seed = int(A.get("seed") or 1)
        except Exception: pass
        em.show_instancer_for_render = False; em.show_instancer_for_viewport = P not in ("rain", "snow")
        R["emitter"] = em.name; R["particle_object"] = part.name; R["settings"] = {"count": st.count, "lifetime": st.lifetime, "frames": [st.frame_start, st.frame_end]}
    ''', "vfx " + a["preset"])


@tool(B, "ms_blender_curve_path",
      "Create a curve from points (Bezier/NURBS/Poly) with optional tube bevel, cyclic closure and smoothing; optionally make objects FOLLOW the path "
      "(Follow Path constraint + animated progress over a duration, looping). Use for rails, pipes, ropes, roads, camera dollies and fly-throughs.",
      {"points": {"type": "array", "items": VEC, "minItems": 2}, "name": {"type": "string"}, "kind": {"type": "string", "enum": ["BEZIER", "NURBS", "POLY"]}, "closed": {"type": "boolean"},
       "bevel_depth": {"type": "number", "description": "Tube radius (0 = flat line)."}, "resolution": {"type": "integer"}, "followers": NAMES, "duration_frames": {"type": "integer"},
       "start_frame": {"type": "integer"}, "loop": {"type": "boolean"}, "forward_axis": {"type": "string", "enum": ["FORWARD_X", "FORWARD_Y", "FORWARD_Z", "TRACK_NEGATIVE_X", "TRACK_NEGATIVE_Y", "TRACK_NEGATIVE_Z"]},
       "use_follow": {"type": "boolean", "description": "Rotate followers along the path tangent (default true)."}, "location": VEC},
      ["points"], writes=True)
def curve_path(args, ctx):
    a = _norm(args, name="Path", kind="BEZIER", closed=False, bevel_depth=0.0, resolution=12, duration_frames=120, start_frame=1, loop=True, use_follow=True, forward_axis="FORWARD_Y")
    pts = [vec3(p) for p in as_list(a.get("points"))]
    if len(pts) < 2:
        raise ToolkitError("points needs at least two [x,y,z] entries")
    a["points"] = [list(p) for p in pts]
    a["followers"] = _names(a, "followers", "objects")
    a["kind"] = str(a["kind"]).upper()
    return _exec(ctx, a, '''
        pts = A["points"]; kind = A["kind"]
        cu = bpy.data.curves.new(A["name"], "CURVE"); cu.dimensions = "3D"; cu.resolution_u = int(A["resolution"]); cu.bevel_depth = float(A["bevel_depth"])
        if cu.bevel_depth > 0: cu.use_fill_caps = True
        sp = cu.splines.new("NURBS" if kind == "NURBS" else ("POLY" if kind == "POLY" else "BEZIER"))
        if kind == "BEZIER":
            sp.bezier_points.add(len(pts) - 1)
            for bp, p in zip(sp.bezier_points, pts):
                bp.co = p; bp.handle_left_type = "AUTO"; bp.handle_right_type = "AUTO"
        else:
            sp.points.add(len(pts) - 1)
            for sp_p, p in zip(sp.points, pts): sp_p.co = (p[0], p[1], p[2], 1.0)
            if kind == "NURBS": sp.order_u = min(4, len(pts)); sp.use_endpoint_u = True
        sp.use_cyclic_u = bool(A.get("closed"))
        obj = bpy.data.objects.new(A["name"], cu); bpy.context.scene.collection.objects.link(obj); obj.location = _v(A.get("location"))
        R["curve"] = obj.name; R["points"] = len(pts)
        fol = [_obj(n) for n in (A.get("followers") or [])]
        if fol:
            dur = int(A["duration_frames"]); st = int(A["start_frame"])
            cu.use_path = True; cu.path_duration = dur
            if not A.get("loop", True) and False: pass
            cu.eval_time = 0.0; cu.keyframe_insert("eval_time", frame=st)
            cu.eval_time = float(dur); cu.keyframe_insert("eval_time", frame=st + dur)
            for fc in _fcurves(cu.animation_data.action if cu.animation_data else None):
                for kp in fc.keyframe_points: kp.interpolation = "LINEAR"
                if A.get("loop", True) and not any(m.type == "CYCLES" for m in fc.modifiers): fc.modifiers.new("CYCLES")
            for f in fol:
                c = f.constraints.new("FOLLOW_PATH"); c.target = obj; c.use_curve_follow = bool(A.get("use_follow", True)); c.forward_axis = A["forward_axis"]; c.use_fixed_location = False
            sc = bpy.context.scene; sc.frame_end = max(sc.frame_end, st + dur)
            R["followers"] = [f.name for f in fol]; R["duration_frames"] = dur
    ''', "curve path")


@tool(B, "ms_blender_mesh_cleanup",
      "Clean and optimise meshes for export or rendering in one pass: merge by distance, recalculate normals, remove loose geometry, dissolve degenerate faces, fill holes, "
      "triangulate / tris-to-quads, apply transforms, shade smooth/flat/auto (by angle), decimate to a ratio. Reports before/after vertex, face and loose counts.",
      {"objects": NAMES, "merge_distance": {"type": "number"}, "recalc_normals": {"type": "boolean"}, "remove_loose": {"type": "boolean"}, "dissolve_degenerate": {"type": "boolean"},
       "fill_holes": {"type": "integer", "description": "Fill holes up to this many sides (0 = off)."}, "triangulate": {"type": "boolean"}, "tris_to_quads": {"type": "boolean"},
       "apply_transforms": {"type": "boolean"}, "shade": {"type": "string", "enum": ["smooth", "flat", "auto"]}, "auto_angle_degrees": {"type": "number"},
       "decimate_ratio": {"type": "number", "minimum": 0.01, "maximum": 1}},
      ["objects"], writes=True)
def mesh_cleanup(args, ctx):
    a = _norm(args, merge_distance=0.0001, recalc_normals=True, remove_loose=True, dissolve_degenerate=True, auto_angle_degrees=35.0)
    a["objects"] = _names(a, "objects", "object", "names")
    return _exec(ctx, a, '''
        import bmesh
        report = []; warnings = []
        for name in A["objects"]:
            o = _obj(name)
            if o.type != "MESH": report.append({"name": name, "skipped": "not a mesh"}); continue
            me = o.data; before = {"vertices": len(me.vertices), "faces": len(me.polygons), "edges": len(me.edges)}
            if A.get("apply_transforms"):
                _select([o], o)
                with bpy.context.temp_override(selected_objects=[o], active_object=o, object=o):
                    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
            bm = bmesh.new(); bm.from_mesh(me)
            if A.get("merge_distance") and float(A["merge_distance"]) > 0:
                bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=float(A["merge_distance"]))
            if A.get("dissolve_degenerate", True):
                bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges[:])
            if A.get("remove_loose", True):
                loose = [v for v in bm.verts if not v.link_edges]
                bmesh.ops.delete(bm, geom=loose, context="VERTS")
            if int(A.get("fill_holes") or 0) > 0:
                bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=int(A["fill_holes"]))
            if A.get("recalc_normals", True) and bm.faces:
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
            if A.get("tris_to_quads"):
                bmesh.ops.join_triangles(bm, faces=bm.faces[:], angle_face_threshold=math.radians(40), angle_shape_threshold=math.radians(40))
            if A.get("triangulate"):
                bmesh.ops.triangulate(bm, faces=bm.faces[:])
            bm.to_mesh(me); bm.free(); me.update()
            if A.get("decimate_ratio") is not None:
                if me.shape_keys:
                    warnings.append("%s: decimate skipped (mesh has shape keys; remove them or apply the decimate manually)" % name)
                else:
                    md = o.modifiers.new("MS_Decimate", "DECIMATE"); md.ratio = float(A["decimate_ratio"])
                    try:
                        with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o]):
                            bpy.ops.object.modifier_apply(modifier=md.name)
                    except Exception as _e:
                        o.modifiers.remove(md); warnings.append("%s: decimate failed: %s" % (name, str(_e).strip()[:120]))
            sh = A.get("shade")
            if sh == "smooth":
                for p in me.polygons: p.use_smooth = True
            elif sh == "flat":
                for p in me.polygons: p.use_smooth = False
            elif sh == "auto":
                _select([o], o)
                try:
                    with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o]):
                        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(float(A["auto_angle_degrees"])))
                except Exception:
                    for p in me.polygons: p.use_smooth = True
            after = {"vertices": len(me.vertices), "faces": len(me.polygons), "edges": len(me.edges)}
            report.append({"name": name, "before": before, "after": after})
        R["objects"] = report
        if warnings: R["warnings"] = warnings
    ''', "mesh cleanup")


# ─────────────────────────────── studio / architecture ───────────────────────────────
LIGHTS = ["three_point", "product", "dramatic", "soft", "rim", "sunset", "night", "none"]


@tool(B, "ms_blender_scene_studio",
      "Set up a render/presentation studio around objects: lighting rig (three_point, product, dramatic, soft, rim, sunset, night), optional cyclorama backdrop, camera framed "
      "on the subject (lens, distance, height), world gradient colour, render engine/resolution/samples, and an optional looping TURNTABLE (camera rig orbits, N frames).",
      {"targets": NAMES, "lighting": {"type": "string", "enum": LIGHTS}, "backdrop": {"type": "boolean"}, "backdrop_color": {"type": ["string", "array"]},
       "world_color": {"type": ["string", "array"]}, "camera_lens_mm": {"type": "number"}, "camera_distance_scale": {"type": "number", "description": "Multiplier on the auto-fit distance (default 1)."},
       "camera_elevation_degrees": {"type": "number"}, "turntable": {"type": "boolean"}, "turntable_frames": {"type": "integer"},
       "render": {"type": "object", "description": "{engine: EEVEE|CYCLES|WORKBENCH, width, height, samples, transparent}"}},
      writes=True)
def scene_studio(args, ctx):
    a = _norm(args, lighting="three_point", backdrop=False, camera_lens_mm=55, camera_distance_scale=1.0, camera_elevation_degrees=18, turntable=False, turntable_frames=120)
    a["targets"] = _names(a, "targets", "objects", "object")
    from engine_toolkit import color4
    for k in ("backdrop_color", "world_color"):
        if a.get(k) is not None:
            a[k] = list(color4(a[k]))
    return _exec(ctx, a, '''
        from mathutils import Vector
        objs = [_obj(n) for n in (A.get("targets") or [])] or [o for o in bpy.context.scene.objects if o.type in ("MESH", "CURVE", "SURFACE", "FONT")]
        if not objs: raise ValueError("no objects to frame; pass targets")
        pts = []
        for o in objs:
            if o.type in ("MESH", "CURVE", "SURFACE", "FONT", "META"):
                pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
            else: pts.append(o.matrix_world.translation.copy())
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))); hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        center = (lo + hi) / 2; dims = hi - lo; radius = max(dims.length / 2, 0.25)
        sc = bpy.context.scene
        col = bpy.data.collections.get("MS_Studio") or bpy.data.collections.new("MS_Studio")
        if col.name not in sc.collection.children: sc.collection.children.link(col)
        for o in list(col.objects):
            if o.name.startswith("MS_"): bpy.data.objects.remove(o, do_unlink=True)
        def add_light(name, kind, loc, energy, color=(1, 1, 1), size=None, aim=center):
            ld = bpy.data.lights.new(name, kind); ld.energy = energy; ld.color = color
            if size is not None:
                if kind == "AREA": ld.size = size
                elif kind == "SUN": ld.angle = math.radians(size)
            lo_ = bpy.data.objects.new(name, ld); col.objects.link(lo_); lo_.location = loc
            d = aim - Vector(loc); lo_.rotation_euler = d.to_track_quat("-Z", "Y").to_euler(); return lo_
        L = A["lighting"]; r = radius * 3.0; c = center
        rigs = {
          "three_point": [("MS_Key", "AREA", (c.x + r, c.y - r, c.z + r), 900 * radius ** 2, (1, 0.96, 0.9), r), ("MS_Fill", "AREA", (c.x - r * 1.2, c.y - r * 0.6, c.z + r * 0.3), 300 * radius ** 2, (0.85, 0.92, 1), r * 1.4), ("MS_Back", "AREA", (c.x - r * 0.3, c.y + r, c.z + r * 1.1), 600 * radius ** 2, (1, 1, 1), r * 0.6)],
          "product": [("MS_Top", "AREA", (c.x, c.y, c.z + r * 1.6), 1200 * radius ** 2, (1, 1, 1), r * 1.6), ("MS_SideL", "AREA", (c.x - r * 1.5, c.y - r * 0.4, c.z + r * 0.4), 500 * radius ** 2, (1, 1, 1), r), ("MS_SideR", "AREA", (c.x + r * 1.5, c.y - r * 0.4, c.z + r * 0.4), 500 * radius ** 2, (1, 1, 1), r)],
          "dramatic": [("MS_Key", "SPOT", (c.x + r, c.y - r * 0.5, c.z + r * 0.8), 2500 * radius ** 2, (1, 0.8, 0.6), None), ("MS_Rim", "AREA", (c.x - r * 0.4, c.y + r * 1.3, c.z + r * 0.6), 900 * radius ** 2, (0.5, 0.65, 1), r * 0.6)],
          "soft": [("MS_Softbox", "AREA", (c.x, c.y - r * 1.6, c.z + r), 1000 * radius ** 2, (1, 1, 1), r * 3), ("MS_Bounce", "AREA", (c.x, c.y + r, c.z - radius * 0.5), 200 * radius ** 2, (1, 0.97, 0.94), r * 2)],
          "rim": [("MS_RimL", "AREA", (c.x - r, c.y + r, c.z + r * 0.5), 1200 * radius ** 2, (0.7, 0.8, 1), r * 0.6), ("MS_RimR", "AREA", (c.x + r, c.y + r, c.z + r * 0.5), 1200 * radius ** 2, (1, 0.8, 0.7), r * 0.6), ("MS_Fill", "AREA", (c.x, c.y - r * 1.5, c.z + r * 0.2), 150 * radius ** 2, (1, 1, 1), r * 2)],
          "sunset": [("MS_Sun", "SUN", (c.x + r, c.y - r, c.z + r * 0.35), 4.0, (1.0, 0.55, 0.28), 2.0), ("MS_Sky", "AREA", (c.x - r, c.y - r * 0.5, c.z + r), 150 * radius ** 2, (0.5, 0.6, 1.0), r * 2)],
          "night": [("MS_Moon", "SUN", (c.x - r, c.y - r, c.z + r), 0.8, (0.55, 0.65, 1.0), 1.0), ("MS_Warm", "POINT", (c.x + r * 0.6, c.y - r * 0.6, c.z + r * 0.3), 400 * radius ** 2, (1, 0.6, 0.3), None)],
          "none": []}[L]
        made = []
        for nm, kind, loc, energy, colr, size in rigs:
            o = add_light(nm, kind, loc, energy, colr, size); made.append(o.name)
        if A.get("backdrop"):
            h = max(dims.x, dims.y) * 3 + 2
            bpy.ops.mesh.primitive_plane_add(size=h * 2, location=(c.x, c.y + h * 0.6, lo.z))
            bd = bpy.context.active_object; bd.name = "MS_Backdrop"
            # cyclorama: bend the back half up
            import bmesh
            bm = bmesh.new(); bm.from_mesh(bd.data); bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=24, use_grid_fill=True)
            for v in bm.verts:
                dy = v.co.y - 0.0
                if dy > h * 0.3:
                    t = min(1.0, (dy - h * 0.3) / (h * 0.5)); v.co.z += math.sin(t * math.pi / 2) * h * 0.9; v.co.y = h * 0.3 + (v.co.y - h * 0.3) * (1 - 0.5 * t)
            bm.to_mesh(bd.data); bm.free()
            for p in bd.data.polygons: p.use_smooth = True
            bm_ = bpy.data.materials.new("MS_BackdropMat")
            try: bm_.use_nodes = True
            except Exception: pass
            bm_.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = tuple(A.get("backdrop_color") or (0.8, 0.8, 0.82, 1)); bm_.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
            bd.data.materials.append(bm_)
            for cc in list(bd.users_collection): cc.objects.unlink(bd)
            col.objects.link(bd); made.append(bd.name)
        # world
        if A.get("world_color") or L == "night" or L == "sunset":
            w = sc.world or bpy.data.worlds.new("World"); sc.world = w
            try: w.use_nodes = True
            except Exception: pass
            bg = w.node_tree.nodes.get("Background")
            if bg: bg.inputs["Color"].default_value = tuple(A.get("world_color") or ((0.02, 0.03, 0.06, 1) if L == "night" else (0.9, 0.45, 0.25, 1))); bg.inputs["Strength"].default_value = 0.6 if L in ("night", "sunset") else 1.0
        # camera
        cam_d = bpy.data.cameras.new("MS_Camera"); cam_d.lens = float(A["camera_lens_mm"]); cam_d.sensor_width = 36
        cam = bpy.data.objects.new("MS_Camera", cam_d); col.objects.link(cam)
        fov = 2 * math.atan(36 / (2 * cam_d.lens))
        dist = radius / math.sin(fov / 2) * 1.15 * float(A["camera_distance_scale"])
        el = math.radians(float(A["camera_elevation_degrees"]))
        cam.location = (c.x, c.y - dist * math.cos(el), c.z + dist * math.sin(el))
        tgt = bpy.data.objects.new("MS_Target", None); tgt.location = c; col.objects.link(tgt)
        tc = cam.constraints.new("TRACK_TO"); tc.target = tgt; tc.track_axis = "TRACK_NEGATIVE_Z"; tc.up_axis = "UP_Y"
        sc.camera = cam; made += [cam.name, tgt.name]
        if A.get("turntable"):
            rig = bpy.data.objects.new("MS_TurntableRig", None); rig.location = c; col.objects.link(rig)
            cam.parent = rig; cam.matrix_parent_inverse = rig.matrix_world.inverted()
            n = int(A["turntable_frames"]); sc.frame_start = 1; sc.frame_end = n
            rig.rotation_euler = (0, 0, 0); rig.keyframe_insert("rotation_euler", index=2, frame=1)
            rig.rotation_euler = (0, 0, math.tau); rig.keyframe_insert("rotation_euler", index=2, frame=n + 1)
            for fc in _fcurves(rig.animation_data.action):
                for kp in fc.keyframe_points: kp.interpolation = "LINEAR"
            made.append(rig.name); R["turntable"] = {"frames": n, "rig": rig.name}
        rs = A.get("render") or {}
        if rs:
            eng = str(rs.get("engine") or "").upper()
            if eng:
                for cand in {"EEVEE": ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"), "CYCLES": ("CYCLES",), "WORKBENCH": ("BLENDER_WORKBENCH",)}.get(eng, (eng,)):
                    try: sc.render.engine = cand; break
                    except Exception: continue
            if rs.get("width"): sc.render.resolution_x = int(rs["width"])
            if rs.get("height"): sc.render.resolution_y = int(rs["height"])
            if rs.get("transparent") is not None: sc.render.film_transparent = bool(rs["transparent"])
            if rs.get("samples"):
                try:
                    if sc.render.engine == "CYCLES": sc.cycles.samples = int(rs["samples"])
                    else: sc.eevee.taa_render_samples = int(rs["samples"])
                except Exception: pass
        R["created"] = made; R["subject"] = {"center": [round(x, 3) for x in c], "size": [round(x, 3) for x in dims], "camera_distance": round(dist, 3)}
        R["render_engine"] = sc.render.engine
    ''', "scene studio")


@tool(B, "ms_blender_building",
      "Generate a parametric BUILDING mesh: footprint, floors, floor height, window grid, door, roof (flat/gabled/hip/none), style (modern, classic, industrial, tower) with "
      "separate material slots (walls, glass, trim, roof, door). Real geometry (bmesh), origin on the ground centre, ready for UVs/export.",
      {"name": {"type": "string"}, "width": {"type": "number"}, "depth": {"type": "number"}, "floors": {"type": "integer", "minimum": 1, "maximum": 80}, "floor_height": {"type": "number"},
       "style": {"type": "string", "enum": ["modern", "classic", "industrial", "tower"]}, "roof": {"type": "string", "enum": ["flat", "gabled", "hip", "none"]},
       "window_columns": {"type": "integer", "minimum": 0, "maximum": 30}, "door": {"type": "boolean"}, "location": VEC, "wall_color": {"type": ["string", "array"]}, "seed": {"type": "integer"}},
      writes=True)
def building(args, ctx):
    a = _norm(args, name="Building", width=10, depth=8, floors=3, floor_height=3.2, style="modern", roof="flat", window_columns=4, door=True, seed=1)
    from engine_toolkit import color4
    if a.get("wall_color") is not None:
        a["wall_color"] = list(color4(a["wall_color"]))
    return _exec(ctx, a, '''
        import bmesh, random
        W = float(A["width"]); D = float(A["depth"]); F = int(A["floors"]); FH = float(A["floor_height"]); style = A["style"]
        cols = int(A["window_columns"]); roof = A["roof"]; rng = random.Random(int(A["seed"]))
        bm = bmesh.new()
        mats = ["Wall", "Glass", "Trim", "Roof", "Door"]
        def box(cx, cy, cz, sx, sy, sz, mi):
            r = bmesh.ops.create_cube(bm, size=1.0)
            vs = r["verts"]
            for v in vs: v.co = (v.co.x * sx + cx, v.co.y * sy + cy, v.co.z * sz + cz)
            for f in {f for v in vs for f in v.link_faces}: f.material_index = mi
        wall_t = 0.25 if style != "tower" else 0.15
        # walls per floor with window openings (as separate wall segments) + glass panes
        glass_depth = 0.05
        for fl in range(F):
            z0 = fl * FH
            box(0, 0, z0 + 0.06, W, D, 0.12, 2)             # floor slab / trim band
            for side in range(4):
                horizontal = side in (0, 1)
                L = W if horizontal else D
                sgn = 1 if side in (0, 2) else -1
                ox = 0.0; oy = 0.0
                n = max(0, cols if horizontal else max(1, round(cols * D / max(W, 0.01))))
                if n == 0:
                    if horizontal: box(0, sgn * (D / 2 - wall_t / 2), z0 + FH / 2, W, wall_t, FH, 0)
                    else: box(sgn * (W / 2 - wall_t / 2), 0, z0 + FH / 2, wall_t, D, FH, 0)
                    continue
                cell = L / n
                ww = cell * (0.55 if style != "tower" else 0.8); wh = FH * (0.5 if style != "tower" else 0.7); sill = (FH - wh) * 0.45
                door_here = bool(A.get("door")) and fl == 0 and side == 0
                for k in range(n):
                    c0 = -L / 2 + cell * (k + 0.5)
                    is_door = door_here and k == n // 2
                    openh = (FH * 0.78) if is_door else wh
                    z_open0 = 0.12 if is_door else sill
                    # pier left/right of the opening + lintel + sill
                    pw = (cell - ww) / 2 if not is_door else (cell - ww * 0.7) / 2
                    ow = ww if not is_door else ww * 0.7
                    def put(c, wlen, zc, zh, mi, thick=wall_t):
                        if wlen <= 0 or zh <= 0: return
                        if horizontal: box(c, sgn * (D / 2 - thick / 2), z0 + zc, wlen, thick, zh, mi)
                        else: box(sgn * (W / 2 - thick / 2), c, z0 + zc, thick, wlen, zh, mi)
                    put(c0 - cell / 2 + pw / 2, pw, FH / 2, FH, 0); put(c0 + cell / 2 - pw / 2, pw, FH / 2, FH, 0)
                    put(c0, ow, z_open0 / 2, z_open0, 0) if not is_door else None
                    top = FH - (z_open0 + openh)
                    put(c0, ow, z_open0 + openh + top / 2, top, 0)
                    if is_door: put(c0, ow * 0.95, z_open0 + openh / 2, openh, 4, 0.08)
                    else: put(c0, ow, z_open0 + openh / 2, openh, 1, glass_depth)
        box(0, 0, F * FH + 0.08, W + 0.3, D + 0.3, 0.16, 2)  # parapet slab / cornice
        top = F * FH + 0.16
        if roof == "flat" and style != "tower":
            box(0, 0, top + 0.2, W - 0.2, D - 0.2, 0.4, 3)
        elif roof in ("gabled", "hip"):
            h = min(W, D) * 0.35
            # prism: two slopes
            bm2 = bmesh.new()
            hx, hy = W / 2 + 0.2, D / 2 + 0.2
            if roof == "gabled":
                v = [bm.verts.new(p) for p in [(-hx, -hy, top), (hx, -hy, top), (hx, hy, top), (-hx, hy, top), (-hx, 0, top + h), (hx, 0, top + h)]]
                faces = [(0, 1, 5, 4), (3, 4, 5, 2), (0, 4, 3), (1, 2, 5), (0, 3, 2, 1)]
            else:
                inset = min(hx, hy) * 0.5
                v = [bm.verts.new(p) for p in [(-hx, -hy, top), (hx, -hy, top), (hx, hy, top), (-hx, hy, top), (-hx + inset, -hy + inset, top + h), (hx - inset, -hy + inset, top + h), (hx - inset, hy - inset, top + h), (-hx + inset, hy - inset, top + h)]]
                faces = [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7), (3, 2, 1, 0)]
            bm2.free()
            for fi in faces:
                f = bm.faces.new([v[i] for i in fi]); f.material_index = 3
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        me = bpy.data.meshes.new(A["name"]); bm.to_mesh(me); bm.free()
        palette = {"Wall": tuple(A.get("wall_color") or {"modern": (0.82, 0.83, 0.85, 1), "classic": (0.72, 0.55, 0.42, 1), "industrial": (0.45, 0.45, 0.47, 1), "tower": (0.55, 0.62, 0.7, 1)}[style]),
                   "Glass": (0.25, 0.45, 0.6, 1), "Trim": (0.2, 0.2, 0.22, 1), "Roof": (0.25, 0.12, 0.1, 1), "Door": (0.18, 0.1, 0.06, 1)}
        for nm in mats:
            m = bpy.data.materials.new("%s_%s" % (A["name"], nm))
            try: m.use_nodes = True
            except Exception: pass
            b = m.node_tree.nodes.get("Principled BSDF"); b.inputs["Base Color"].default_value = palette[nm]; b.inputs["Roughness"].default_value = 0.15 if nm == "Glass" else 0.8
            if nm == "Glass":
                for k in ("Transmission Weight", "Transmission"):
                    if k in b.inputs: b.inputs[k].default_value = 0.6; break
            me.materials.append(m)
        obj = bpy.data.objects.new(A["name"], me); bpy.context.scene.collection.objects.link(obj); obj.location = _v(A.get("location"))
        R["object"] = obj.name; R["vertices"] = len(me.vertices); R["faces"] = len(me.polygons); R["height"] = round(F * FH + 0.16, 2); R["materials"] = [m.name for m in me.materials]
    ''', "building")


@tool(B, "ms_blender_level_blockout",
      "Build a 3D level BLOCKOUT from an ASCII map: '#' wall, '.' floor, ' ' empty, 'D' doorway, 'W' window wall, 'P' pillar, 'S' stairs-up marker (a ramp), 'C' crate, 'E' empty marker "
      "object for spawns. One mesh per material group (floor/walls/props) so it stays light, ready to replace with final art. Cell size, wall height and floor thickness are parameters.",
      {"rows": {"type": "array", "items": {"type": "string"}, "description": "Map rows, top to bottom (north to south)."}, "cell_size": {"type": "number"}, "wall_height": {"type": "number"},
       "floor_thickness": {"type": "number"}, "name": {"type": "string"}, "location": VEC, "merge_walls": {"type": "boolean"}},
      ["rows"], writes=True)
def level_blockout(args, ctx):
    a = _norm(args, cell_size=2.0, wall_height=3.0, floor_thickness=0.2, name="Blockout", merge_walls=True)
    rows = [str(r) for r in as_list(a.get("rows")) if str(r) != ""]
    if not rows:
        raise ToolkitError("rows is required (list of strings)")
    if sum(len(r) for r in rows) > 40000:
        raise ToolkitError("map too large (max 40000 cells)")
    a["rows"] = rows
    return _exec(ctx, a, '''
        import bmesh
        rows = A["rows"]; cs = float(A["cell_size"]); wh = float(A["wall_height"]); ft = float(A["floor_thickness"])
        H = len(rows); Wd = max(len(r) for r in rows)
        grid = [list(r.ljust(Wd)) for r in rows]
        groups = {"Floor": bmesh.new(), "Walls": bmesh.new(), "Props": bmesh.new()}
        def box(g, cx, cy, cz, sx, sy, sz):
            r = bmesh.ops.create_cube(groups[g], size=1.0)
            for v in r["verts"]: v.co = (v.co.x * sx + cx, v.co.y * sy + cy, v.co.z * sz + cz)
        def pos(x, y): return ((x + 0.5) * cs, -(y + 0.5) * cs)
        counts = {"floor": 0, "wall": 0, "door": 0, "prop": 0}; markers = []
        used = set()
        # merge horizontal runs of wall cells
        for y in range(H):
            x = 0
            while x < Wd:
                ch = grid[y][x]
                if ch in "#W" and A.get("merge_walls", True):
                    x2 = x
                    while x2 + 1 < Wd and grid[y][x2 + 1] in "#W": x2 += 1
                    n = x2 - x + 1; cx = (x + n / 2.0) * cs; cy = -(y + 0.5) * cs
                    box("Walls", cx, cy, wh / 2, n * cs, cs, wh); counts["wall"] += n; x = x2 + 1; continue
                px, py = pos(x, y)
                if ch in "#W": box("Walls", px, py, wh / 2, cs, cs, wh); counts["wall"] += 1
                elif ch == "D":
                    box("Walls", px, py, wh - (wh * 0.25) / 2, cs, cs, wh * 0.25); counts["door"] += 1
                    box("Floor", px, py, -ft / 2, cs, cs, ft)
                elif ch == "P": box("Props", px, py, wh / 2, cs * 0.3, cs * 0.3, wh); counts["prop"] += 1
                elif ch == "C": box("Props", px, py, cs * 0.25, cs * 0.5, cs * 0.5, cs * 0.5); counts["prop"] += 1
                elif ch == "S":
                    box("Props", px, py, cs * 0.25, cs, cs, cs * 0.5); counts["prop"] += 1
                if ch not in " #W":
                    if ch not in "D": box("Floor", px, py, -ft / 2, cs, cs, ft); counts["floor"] += 1
                if ch == "E": markers.append((px, py))
                x += 1
        col = bpy.data.collections.get(A["name"]) or bpy.data.collections.new(A["name"])
        if col.name not in bpy.context.scene.collection.children: bpy.context.scene.collection.children.link(col)
        made = []
        colors = {"Floor": (0.45, 0.45, 0.48, 1), "Walls": (0.75, 0.72, 0.68, 1), "Props": (0.6, 0.42, 0.25, 1)}
        for g, bm in groups.items():
            if not bm.verts: bm.free(); continue
            bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0005); bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
            me = bpy.data.meshes.new("%s_%s" % (A["name"], g)); bm.to_mesh(me); bm.free()
            m = bpy.data.materials.get("BO_" + g) or bpy.data.materials.new("BO_" + g)
            try: m.use_nodes = True
            except Exception: pass
            m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = colors[g]; me.materials.append(m)
            o = bpy.data.objects.new("%s_%s" % (A["name"], g), me); col.objects.link(o); o.location = _v(A.get("location")); made.append(o.name)
        for i, (px, py) in enumerate(markers):
            e = bpy.data.objects.new("%s_Marker%d" % (A["name"], i + 1), None); e.empty_display_type = "ARROWS"; e.location = (px + (A.get("location") or [0, 0, 0])[0], py + (A.get("location") or [0, 0, 0])[1], (A.get("location") or [0, 0, 0])[2] + 0.1); col.objects.link(e); made.append(e.name)
        R["objects"] = made; R["counts"] = counts; R["size_m"] = [Wd * cs, H * cs]
    ''', "level blockout")


@tool(B, "ms_blender_physics",
      "Add physics in one call: kind=rigid_body (active/passive, mass, friction, bounciness, shape), collision (for cloth/soft body/particles), cloth (cotton/silk/leather/rubber presets, "
      "optional pin vertex group), soft_body, force_field (wind/vortex/turbulence/force/drag), or remove; optionally set the simulation frame range. Does not bake unless bake=true.",
      {"kind": {"type": "string", "enum": ["rigid_body", "collision", "cloth", "soft_body", "force_field", "remove"]}, "objects": NAMES, "body_type": {"type": "string", "enum": ["ACTIVE", "PASSIVE"]},
       "mass": {"type": "number"}, "friction": {"type": "number"}, "bounciness": {"type": "number"}, "shape": {"type": "string", "enum": ["BOX", "SPHERE", "CAPSULE", "CONVEX_HULL", "MESH"]},
       "preset": {"type": "string", "enum": ["cotton", "silk", "leather", "rubber", "denim"]}, "pin_group": {"type": "string"}, "field_type": {"type": "string", "enum": ["WIND", "VORTEX", "TURBULENCE", "FORCE", "DRAG"]},
       "strength": {"type": "number"}, "frame_start": {"type": "integer"}, "frame_end": {"type": "integer"}, "bake": {"type": "boolean"},
       "location": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3, "description": "force_field: where to place the field [x, y, z]."}},
      ["kind"], writes=True)
def physics(args, ctx):
    a = _norm(args, body_type="ACTIVE", mass=1.0, friction=0.5, bounciness=0.1, shape="CONVEX_HULL", preset="cotton", field_type="WIND", strength=1.0)
    a["objects"] = _names(a, "objects", "object", "names")
    return _exec(ctx, a, '''
        K = A["kind"]; sc = bpy.context.scene; done = []
        if A.get("frame_start") is not None: sc.frame_start = int(A["frame_start"])
        if A.get("frame_end") is not None: sc.frame_end = int(A["frame_end"])
        if K == "force_field":
            bpy.ops.object.effector_add(type=A["field_type"], location=_v(A.get("location")))
            e = bpy.context.active_object; e.field.strength = float(A["strength"]); done.append(e.name)
        else:
            objs = [_obj(n) for n in A["objects"]]
            if not objs: raise ValueError("objects is required")
            for o in objs:
                _select([o], o)
                with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o]):
                    if K == "rigid_body":
                        if sc.rigidbody_world is None: bpy.ops.rigidbody.world_add()
                        bpy.ops.rigidbody.object_add(type=A["body_type"])
                        rb = o.rigid_body; rb.mass = float(A["mass"]); rb.friction = float(A["friction"]); rb.restitution = float(A["bounciness"]); rb.collision_shape = A["shape"]
                    elif K == "collision":
                        bpy.ops.object.modifier_add(type="COLLISION")
                    elif K == "cloth":
                        bpy.ops.object.modifier_add(type="CLOTH"); cm = o.modifiers["Cloth"]; s = cm.settings
                        pr = {"cotton": (0.3, 5, 5, 5, 0.5), "silk": (0.15, 2, 2, 1, 0.2), "leather": (0.4, 80, 80, 25, 1), "rubber": (1.0, 15, 15, 25, 5), "denim": (0.4, 40, 40, 25, 1.5)}[A["preset"]]
                        s.mass, s.tension_stiffness, s.compression_stiffness, s.bending_stiffness, s.air_damping = pr
                        if A.get("pin_group") and A["pin_group"] in o.vertex_groups: s.vertex_group_mass = A["pin_group"]
                    elif K == "soft_body":
                        bpy.ops.object.modifier_add(type="SOFT_BODY")
                    elif K == "remove":
                        for m in list(o.modifiers):
                            if m.type in ("CLOTH", "SOFT_BODY", "COLLISION"): o.modifiers.remove(m)
                        if o.rigid_body: bpy.ops.rigidbody.object_remove()
                done.append(o.name)
        if A.get("bake") and K in ("cloth", "soft_body"):
            with bpy.context.temp_override(scene=sc):
                try: bpy.ops.ptcache.bake_all(bake=True)
                except Exception as e: R["bake_error"] = str(e)
        R["applied"] = done; R["kind"] = K; R["frames"] = [sc.frame_start, sc.frame_end]
    ''', "physics " + a["kind"])
