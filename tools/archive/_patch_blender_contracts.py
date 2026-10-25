import io, json

p = 'runtime/bridge.py'
src = io.open(p, encoding='utf-8').read()

GEO = {
    "description": "Blender specialist for Geometry Nodes interfaces, fields, simulation, instances, determinism and performance. Prefers instancing real modelled assets over scattering generated primitives.",
    "category": "quality",
    "engine": "blender",
    "stages": [
        "Define the requested result and acceptance criteria for the node system",
        "Inspect the existing node graph, its inputs, dependencies and the mesh data it consumes",
        "Design the graph around named Group Inputs so it is reusable and stays readable",
        "Build with fields (per-element data flow) rather than a mesh-in/mesh-out chain where the logic is per-point",
        "Instance real geometry rather than generating it in-node: point-instance a modelled asset instead of scattering spheres as \"rocks\"",
        "Drive all variation from explicit, seeded parameters so two runs produce identical output (determinism)",
        "Keep evaluation cheap: realize instances only when required, cap density, and avoid per-frame simulation on large counts",
        "Verify with the node graph read back, a vertex/instance count, and a re-evaluation that matches the first run",
    ],
    "qualityGates": [
        "Graph is driven by named parameters, not hardcoded values",
        "Per-element logic uses fields correctly",
        "Scattered/instanced geometry reuses real modelled assets with correct forms",
        "Deterministic: the same seed gives the same result across runs",
        "Instance and vertex counts are within the stated budget",
        "No unintentional realization of large instance sets",
        "Graph is readable and labelled for handoff",
        "Re-evaluation output matches the validated first run",
    ],
}

RIG = {
    "description": "Blender specialist for rig hierarchy, deformation, controls, actions, NLA, retargeting and export. Requires a correctly formed mesh before it will rig it.",
    "category": "quality",
    "engine": "blender",
    "stages": [
        "Define the rig scope, bone-count budget and the target engine's skeleton conventions",
        "Inspect the mesh first: confirm loops exist where joints will bend, and that each limb is a properly formed cylinder-like volume - a scaled sphere cannot deform cleanly",
        "Build the armature with a readable hierarchy: a clear root, spine and limb chains, and controls separated from deform bones",
        "Bind with deliberate weights and correct bone envelopes; check the shoulder, elbow, hip and knee individually rather than trusting an automatic bind",
        "Add constraints (IK, limits, drivers) and keep them on control bones, never on deform bones",
        "Author actions with usable naming and NLA strips so clips layer and blend predictably",
        "Set up retargeting/export mappings and verify axis and scale conventions for the target engine",
        "Read the pose and skin deformation back, and confirm the rest pose is preserved",
    ],
    "qualityGates": [
        "Deform geometry supports the intended range of motion",
        "Rig hierarchy is readable and roles are separated",
        "Weights hold through extreme poses without collapse or pinching",
        "Controls are usable and constrained sensibly",
        "Actions and NLA strips are named and layer predictably",
        "Retarget/export preserves scale, axes and roll",
        "Rest pose is intact after export",
        "Deformation is checked in poses, not only at rest",
    ],
}

# Insert both inside ENGINE_PRO_V3_CONTRACTS, just before the topology entry.
anchor = "'ms_blender_topology_modifier_pipeline'"
assert src.count(anchor) == 1, src.count(anchor)
inject = (
    "'ms_blender_geometry_nodes_pipeline': " + json.dumps(GEO, ensure_ascii=False) + ", "
    + "'ms_blender_rig_animation_pipeline': " + json.dumps(RIG, ensure_ascii=False) + ", "
)
src = src.replace(anchor, inject + anchor, 1)

io.open(p, 'w', encoding='utf-8', newline='\n').write(src)
print("injected geometry_nodes + rig_animation")
