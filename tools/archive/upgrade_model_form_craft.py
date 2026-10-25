# SPDX-License-Identifier: GPL-3.0-or-later
"""
Give the engine modelling virtual-specialists real form craft.

The problem this fixes: virtual-tools.json contains 300 entries, and 200 of them
carry the literal identical 8-stage boilerplate with only the domain name
substituted. For a MODELLING specialist that is worse than useless - "block
primary forms" tells the model to put geometry in the scene and nothing about
which geometry, so it reaches for a UV sphere. That is the reported bug.

This script rewrites the stages/qualityGates of every modelling-domain entry
(modeling, art3d) for each engine with form-craft content that is actually
engine-specific. It is idempotent: running it twice produces the same file.
"""
import io
import json

PATH = "runtime/virtual-tools.json"

FORM_STAGE = (
    "Decide the FORM of every distinct feature before adding geometry: a limb, shaft, pipe, neck, "
    "finger, column or barrel is a CYLINDER (tapered - real limbs are not uniform); a plate, housing, "
    "crate, panel, screen or machine part is a BOX with subdivided, beveled edges; anything that "
    "follows a path (cable, hose, rope, vine, tail, antenna) is a swept curve or oriented segments "
    "along a spline; anything whose identity lives in its outline (gear, bracket, beam, blade, key, "
    "tread) is an extruded 2D profile. A sphere is reserved for genuinely round parts only - eyeball, "
    "ball joint, planet, ball, berry, knob, dome."
)

BLOCKOUT_STAGE = (
    "Block the primary forms with those correct primitives, then establish proportion, composition and "
    "value structure - bevel silhouette edges and taper cylinders so the blockout already reads as the "
    "final object rather than as placeholder primitives."
)

AUDIT_GATE = "Every part uses a form appropriate to what it is - no sphere standing in for a limb, plate or cable"
READ_GATE = "The blockout reads as the intended object before any detail or material is added"

# Per-engine wording for the craft stages that follow the shared blockout.
ENGINE_TAIL = {
    "blender": {
        "refine": "Refine topology, deformation, UVs, pivots and modular boundaries with quad flow that follows the form",
        "detail": "Author coherent materials, textures and a controlled detail hierarchy from the real UVs",
        "finish": "Export and integrate correct scale, axes, collisions, LODs and shaders, then validate from gameplay view",
    },
    "roblox": {
        "refine": "Refine against Roblox part/mesh limits: keep unions minimal, weld on the intended grid, and set pivots so the asset snaps into place",
        "detail": "Author SurfaceAppearance/PBR materials and textures within the platform's texture and memory budget",
        "finish": "Integrate with correct scale, CanCollide/Massless flags and collision fidelity, and validate in the live place with the gameplay camera",
    },
    "unity": {
        "refine": "Refine topology for the target render pipeline: correct lightmap UVs on static geometry, and clean normals/tangents for the shader in use",
        "detail": "Author materials as URP/HDRP shader graphs with textures packed to the platform's compression format",
        "finish": "Configure import settings (scale factor, mesh compression, LOD group, colliders) and validate the imported asset in a scene",
    },
    "godot": {
        "refine": "Refine topology and set the mesh's import flags deliberately (scale, normals, tangents) rather than accepting defaults",
        "detail": "Author StandardMaterial3D/shader materials with textures in the project's import presets",
        "finish": "Set up collision shapes, LODs where the renderer supports them, and validate the imported scene in the running project",
    },
}


def build_stages(engine, dom):
    tail = ENGINE_TAIL.get(engine)
    if not tail:
        tail = {
            "refine": "Refine topology, deformation, UVs, pivots and modular boundaries",
            "detail": "Author coherent materials, textures and a controlled detail hierarchy",
            "finish": "Export and integrate correct scale, axes, collisions, LODs and shaders, then validate in the target engine",
        }
    return [
        "Define art direction, references, scale and gameplay silhouette",
        "Inspect the target engine metrics, camera distance and asset budget",
        FORM_STAGE,
        BLOCKOUT_STAGE,
        tail["refine"],
        tail["detail"],
        tail["finish"],
        "Validate from gameplay view and optimize without losing the art target",
    ]


def build_gates(engine):
    tail = ENGINE_TAIL.get(engine, {})
    gates = [
        AUDIT_GATE,
        READ_GATE,
        "Silhouette and focal hierarchy read at gameplay distance",
        "Topology, normals and UVs are technically clean",
        "Material response is coherent under representative lighting",
        "Scale, pivot, collision and orientation import correctly",
        "Asset matches the surrounding project art language",
        "Final engine capture meets the reference bar",
    ]
    if engine == "roblox":
        gates.insert(6, "Part count, union complexity and collisions stay within the platform budget")
    elif engine in ("unity", "godot", "blender"):
        gates.insert(6, "LOD chain and texture compression preserve quality within the stated budget")
    return gates


def main():
    data = json.load(io.open(PATH, encoding="utf-8"))
    tools = data["tools"]
    touched = []
    for tid, item in tools.items():
        dom = str(item.get("domain") or "").lower()
        if dom not in ("modeling", "art3d"):
            continue
        engine = str(item.get("engine") or "").lower()
        item["stages"] = build_stages(engine, dom)
        item["qualityGates"] = build_gates(engine)
        touched.append(tid)
    io.open(PATH, "w", encoding="utf-8", newline="\n").write(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    )
    print(f"rewrote form craft for {len(touched)} modelling specialists")
    for t in sorted(touched):
        print("  ", t)


if __name__ == "__main__":
    main()
