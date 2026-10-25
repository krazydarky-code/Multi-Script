# SPDX-License-Identifier: GPL-3.0-or-later
# form_craft.py - which form a modelled feature is actually made of.
#
# WHY THIS EXISTS
# Multi-Script drives Blender through natural language. When a model is asked to
# "make a robotic arm" or "a horse", the cheapest technically-valid way to put
# geometry in the scene is to add a UV sphere and scale it. Nothing in the old
# prompts forbade that: the guidance said "block primary forms" and "topology
# must be clean", which a scaled sphere satisfies. So the output arrived as a
# pile of balls - recognisably wrong to a human, invisible to a text-only gate.
#
# The fix is not "never use a sphere". A sphere is the CORRECT primitive for an
# eyeball, a ball joint, a planet, a berry. The fix is to make the choice of
# primitive a deliberate decision per feature, and to encode the default that
# gets it right: REACH FOR THE BOX/CYLINDER/CURVE FIRST, and treat a sphere as
# the narrow exception it is.
#
# This module is pure data + pure logic - no Blender, no bpy, no I/O - so it can
# be unit-tested directly and shipped into the extension prompt as text.

# ── Form vocabulary ──────────────────────────────────────────────────────
# id -> (label, when it is right, how to build it)
# `build` is deliberately concrete: it names the Blender operator or the node
# the model should reach for, because vague advice is what produced spheres.
FORMS = {
    "box": (
        "Box / beveled box",
        "Anything manufactured, mechanical or architectural: armour plates, crates, "
        "machinery housings, walls, screens, vehicles, robot limbs, hardware.",
        "Add a cube, then subdivide and bevel the silhouette edges. Bevel (modifier "
        "or Ctrl+B) is what stops a box reading as programmer art - a hard 90-degree "
        "corner catches no light.",
    ),
    "cylinder": (
        "Cylinder / tapered cylinder",
        "Limbs, shafts, pipes, columns, barrels, wheels, necks, fingers, tree "
        "trunks, lamp posts, most organic segments.",
        "Add a cylinder, then use Simple Deform or a taper (scale the top loop) to "
        "get the taper. Real limbs are wider at one end, not uniform.",
    ),
    "curve_to_mesh": (
        "Curve swept to mesh",
        "Anything that follows a path: cables, hoses, ropes, vines, rails, "
        "piping, tails, tentacles, greebles along an edge, hair strands.",
        "Draw a Bezier/NURBS curve, set a bevel object or bevel depth for the "
        "thickness profile, then convert to mesh. This is the single most-skipped "
        "tool and the one that most often replaces a wrong sphere.",
    ),
    "extruded_profile": (
        "Extruded 2D profile",
        "Anything that is a shape pulled along an axis: beams, gears, brackets, "
        "keys, footprints, blade cross-sections, wall sections, wheel arches.",
        "Model the outline as a flat polygon, then extrude. Reach for this before "
        "any primitive when the object's identity lives in its outline.",
    ),
    "sphere": (
        "Sphere",
        "ONLY for things that are genuinely spherical: eyeballs, ball joints, "
        "planets/moons, balls, berries, bubbles, knobs, rounded rivets, pebbles.",
        "Add a UV sphere (or an Ico sphere when topology matters). If you are "
        "scaling it on one axis to fake a different shape, that is the tell that "
        "you picked the wrong primitive - use a cylinder or a box instead.",
    ),
    "torus": (
        "Torus",
        "Rings, tyres, handles, hoops, donuts, belts, rope loops, chain links "
        "(stretched), lenses in a rim.",
        "Add a torus. For a tyre, flatten it and add tread as a separate band.",
    ),
    "cone": (
        "Cone",
        "Tapers, spikes, funnels, volcanoes, tree crowns, hats, nozzles, horns, "
        "thorns, drill bits.",
        "Add a cone; for a soft taper, prefer a cylinder with a scaled top loop so "
        "you keep quad topology.",
    ),
    "metaball_or_sculpt": (
        "Metaball / sculpted base",
        "Soft organic masses where you will retopologise anyway: body masses, "
        "blobs that become creatures, cloth piles, muscle groups.",
        "Metaballs for quick massing, then remesh and retopologise. Do not ship "
        "the metaball result - it is a blocking tool, not a final asset.",
    ),
    "flat_plane": (
        "Plane / card",
        "Foliage, cloth, decals, signage, water surfaces, ground, hair cards, "
        "UI panels, glass.",
        "Add a plane and give it thickness with a Solidify modifier when it needs "
        "to read as a solid from the side.",
    ),
}

SPHERE_FEATURES = {
    "eyeball", "eye", "eyes", "eyeballs", "pupil", "iris", "ball joint", "balljoint",
    "planet", "moon", "sphere", "orb", "ball", "bead", "berry", "berries", "bubble",
    "pebble", "rivet head", "knob", "dome", "globe", "balloon", "marble",
}

# ── The rule that fixes the reported bug ─────────────────────────────────
# Stated as an explicit, checkable prohibition rather than a preference, because
# a preference is what the model already ignored.
CORE_RULE = (
    "A sphere is the WRONG default. Before adding any primitive, decide what the "
    "feature IS, then pick the form from the table. Concretely: a limb, shaft, "
    "pipe, neck or finger is a CYLINDER; a plate, housing, screen, crate or "
    "machine part is a BOX; anything that follows a path (cable, hose, vine, "
    "tail) is a SWEPT CURVE; anything defined by its outline is an EXTRUDED "
    "PROFILE. Use a sphere only for the short list of genuinely round things "
    "(eyeballs, ball joints, planets, balls, berries, knobs). Scaling one sphere "
    "on one axis to imitate a limb is the specific failure this rule exists to "
    "prevent - it produces visible faceting, impossible topology and a model "
    "that reads as a placeholder."
)

# ── Feature -> form ──────────────────────────────────────────────────────
# Keyword -> form id. Ordered longest-first at match time so "ball joint" wins
# over "ball". Deliberately generous: the cost of a false positive here is a
# slightly different (still valid) primitive, the cost of a miss is another ball.
FEATURE_FORMS = {
    # cylindrical family
    "limb": "cylinder", "arm": "cylinder", "upper arm": "cylinder", "forearm": "cylinder",
    "thigh": "cylinder", "shin": "cylinder", "leg": "cylinder", "calf": "cylinder",
    "finger": "cylinder", "thumb": "cylinder", "toe": "cylinder",
    "neck": "cylinder", "torso": "cylinder", "waist": "cylinder",
    "shaft": "cylinder", "pipe": "cylinder", "tube": "cylinder", "rod": "cylinder",
    "column": "cylinder", "pillar": "cylinder", "post": "cylinder", "pole": "cylinder",
    "barrel": "cylinder", "wheel": "cylinder", "tyre": "torus", "tire": "torus",
    "axle": "cylinder", "piston": "cylinder", "barrel shroud": "cylinder",
    "trunk": "cylinder", "branch": "cylinder", "log": "cylinder", "stem": "cylinder",
    "handle": "cylinder", "grip": "cylinder", "grip segment": "cylinder",
    "candle": "cylinder", "bottle": "cylinder", "can": "cylinder", "cup": "cylinder",
    "barrel body": "cylinder", "telescope barrel": "cylinder", "gun barrel": "cylinder",
    # curve family
    "cable": "curve_to_mesh", "wire": "curve_to_mesh", "hose": "curve_to_mesh",
    "rope": "curve_to_mesh", "chain": "curve_to_mesh", "vine": "curve_to_mesh",
    "rail": "curve_to_mesh", "piping": "curve_to_mesh", "tubing": "curve_to_mesh",
    "antenna": "curve_to_mesh", "tail": "curve_to_mesh", "tentacle": "curve_to_mesh",
    "tendril": "curve_to_mesh", "hair": "curve_to_mesh", "strand": "curve_to_mesh",
    "spline": "curve_to_mesh", "coil": "curve_to_mesh", "spring": "curve_to_mesh",
    # box family
    "plate": "box", "armour": "box", "armor": "box", "housing": "box",
    "crate": "box", "chest": "box", "box": "box", "wall": "box", "floor": "box",
    "roof": "box", "door": "box", "window frame": "box", "screen": "box",
    "monitor": "box", "console": "box", "keyboard": "box", "book": "box",
    "shelf": "box", "cabinet": "box", "table": "box", "bench": "box",
    "sign": "box", "brick": "box", "block": "box", "chassis": "box", "hull": "box",
    "cockpit": "box", "wing": "box", "fin": "box", "panel": "box", "sled": "box",
    "muzzle": "box", "magazine": "box", "stock": "box", "receiver": "box",
    "grip panel": "box", "boot": "box", "shoe": "box", "helmet": "box",
    "backpack": "box", "satchel": "box", "barrel guard": "box",
    # extruded profile family
    "gear": "extruded_profile", "cog": "extruded_profile", "bracket": "extruded_profile",
    "beam": "extruded_profile", "i-beam": "extruded_profile", "rail section": "extruded_profile",
    "blade": "extruded_profile", "sword": "extruded_profile", "axe head": "extruded_profile",
    "key": "extruded_profile", "footprint": "extruded_profile", "wall section": "extruded_profile",
    "wheel arch": "extruded_profile", "trigger guard": "extruded_profile",
    "armour skirt": "extruded_profile", "armor skirt": "extruded_profile",
    "tread": "extruded_profile", "teeth": "extruded_profile", "crown": "extruded_profile",
    # cone family
    "spike": "cone", "horn": "cone", "antler": "cone", "thorn": "cone",
    "funnel": "cone", "nozzle": "cone", "cone": "cone", "volcano": "cone",
    "crown canopy": "cone", "tree crown": "cone", "roof peak": "cone",
    "drill": "cone", "drill bit": "cone", "claw": "cone", "talon": "cone",
    "hat": "cone", "hat brim": "flat_plane",
    # flat family
    "leaf": "flat_plane", "leaves": "flat_plane", "foliage": "flat_plane",
    "grass": "flat_plane", "cloth": "flat_plane", "fabric": "flat_plane",
    "cape": "flat_plane", "banner": "flat_plane", "flag": "flat_plane",
    "decal": "flat_plane", "glass": "flat_plane", "water": "flat_plane",
    "ground": "flat_plane", "terrain card": "flat_plane", "card": "flat_plane",
    "poster": "flat_plane", "page": "flat_plane", "paper": "flat_plane",
    # soft organic
    "body mass": "metaball_or_sculpt", "torso mass": "metaball_or_sculpt",
    "muscle": "metaball_or_sculpt", "flesh": "metaball_or_sculpt",
    "cloud": "metaball_or_sculpt", "slime": "metaball_or_sculpt",
    "cloth pile": "metaball_or_sculpt", "blob": "metaball_or_sculpt",
    # genuine spheres - keep this list short, it is the exception set
    "eyeball": "sphere", "eye": "sphere", "pupil": "sphere", "iris": "sphere",
    "ball joint": "sphere", "planet": "sphere", "moon": "sphere", "orb": "sphere",
    "ball": "sphere", "bead": "sphere", "berry": "sphere", "bubble": "sphere",
    "pebble": "sphere", "knob": "sphere", "dome": "sphere", "globe": "sphere",
    "marble": "sphere", "balloon": "sphere",
}


def _ordered_keys():
    """Longest keyword first, so 'ball joint' is tested before 'ball'."""
    return sorted(FEATURE_FORMS, key=lambda k: (-len(k), k))


_ORDERED = _ordered_keys()


def classify(feature):
    """
    Which form should this feature be built from?
    Returns {form, label, why, build, keyword} - or a box fallback with
    matched=False when nothing matches, because box is the safest general
    primitive and silently defaulting to sphere is what we are removing.
    """
    text = str(feature or "").strip().lower()
    if not text:
        return {
            "form": "box", "label": FORMS["box"][0], "matched": False,
            "why": FORMS["box"][1], "build": FORMS["box"][2], "keyword": None,
            "note": "No feature given - defaulting to a beveled box, which is the safe "
                    "general primitive. Name the feature to get a sharper answer.",
        }
    for kw in _ORDERED:
        if kw in text:
            form = FEATURE_FORMS[kw]
            label, why, build = FORMS[form]
            return {
                "form": form, "label": label, "matched": True, "keyword": kw,
                "why": why, "build": build,
                "note": ("" if form != "sphere" else
                         "This is one of the few genuine spheres - scaling it into a "
                         "limb or plate would still be wrong."),
            }
    label, why, build = FORMS["box"]
    return {
        "form": "box", "label": label, "matched": False, "keyword": None,
        "why": why, "build": build,
        "note": "Nothing in the name matched a known feature. Start from a beveled box "
                "and cut into it, rather than adding a sphere and scaling it.",
    }


def audit(features):
    """
    Audit a proposed part list before it is built. `features` is a list of names
    (or of {name/part/feature} dicts).

    Returns {verdict, sphereCount, total, parts[], advice[]}. verdict is
    'ok' | 'review' | 'sphere-heavy'. A sphere-heavy part list is the exact
    symptom the user reported, so it is called out by name.
    """
    parts, advice = [], []
    for raw in (features or []):
        if isinstance(raw, dict):
            name = raw.get("name") or raw.get("part") or raw.get("feature") or ""
            proposed = raw.get("form") or raw.get("primitive")
        else:
            name, proposed = raw, None
        c = classify(name)
        entry = {"name": str(name), "recommended": c["form"], "label": c["label"],
                 "matched": c["matched"]}
        if proposed:
            p = str(proposed).strip().lower()
            entry["proposed"] = p
            # The reported failure, caught mechanically: a non-spherical feature
            # proposed as a sphere.
            entry["mismatch"] = (p == "sphere" and c["form"] != "sphere")
            if entry["mismatch"]:
                advice.append(
                    f"'{name}' is proposed as a sphere but should be a {c['label']} - "
                    f"{c['build'].split('.')[0]}. {CORE_RULE}"
                )
        parts.append(entry)

    total = len(parts)
    spheres = sum(1 for p in parts if p["recommended"] == "sphere")
    mismatches = sum(1 for p in parts if p.get("mismatch"))
    if not total:
        verdict = "ok"
    elif mismatches:
        verdict = "sphere-heavy"
    elif total >= 4 and spheres > max(1, total // 3):
        verdict = "review"
    else:
        verdict = "ok"
    if verdict == "sphere-heavy":
        advice.insert(0, "At least one part is a sphere that should not be. This is the "
                         "classic placeholder look - rebuild those parts from the "
                         "recommended forms before adding detail or materials.")
    return {"verdict": verdict, "sphereCount": spheres, "mismatchCount": mismatches,
            "total": total, "parts": parts, "advice": advice}


def guidance(engine="blender"):
    """
    A compact, prompt-ready block of form guidance. Kept tight on purpose: a wall
    of text gets skimmed, while the table plus one rule survives.
    """
    rows = [f"  - {label}: {why}" for _, (label, why, _) in sorted(FORMS.items())]
    return "\n".join(
        ["FORM SELECTION - pick the primitive per feature, never by habit:",
         CORE_RULE,
         "Available forms:"] + rows +
        ["If you catch yourself scaling a sphere on one axis to make it look like "
         "something else, stop and switch to the right form."]
    )


def describe():
    """One-line summary, for a tool listing."""
    sphereish = sum(1 for f in FEATURE_FORMS.values() if f == "sphere")
    return (f"{len(FORMS)} forms, {len(FEATURE_FORMS)} mapped features, "
            f"{sphereish} of them genuinely spherical")
