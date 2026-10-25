# SPDX-License-Identifier: GPL-3.0-or-later
"""schema_perfect.py - publish-time JSON Schema normaliser (6.36).

Every tool schema the bridge advertises - Multi-Script's own direct tools, the
engine toolkits, the Software Builder, and the LIVE schemas that Roblox Studio,
Unity, Godot, Blender or any MCP server report - passes through `perfect()`
before a model sees it. It fixes the constructs that make function-calling
providers reject a whole tool list or make models guess:

  * `array` (or a type list containing it) with no `items`   -> OpenAI 400s
  * a property with no `type` at all                          -> models guess
  * legacy type names (int, float, bool, str, dict, list)     -> invalid schema
  * draft-3 `"required": true` on a property                 -> lifted to parent
  * `required` names that are not declared properties         -> dropped
  * duplicate enum values / required names, min > max         -> repaired
  * a root that is not `type: object` with `properties`       -> wrapped

It never removes a declared property, never loosens an `enum`, and never
changes a value that already conforms. Pure stdlib, deterministic, no I/O.
"""
import json
import re

ALIASES = {"int": "integer", "float": "number", "double": "number", "bool": "boolean", "str": "string",
           "dict": "object", "map": "object", "list": "array", "tuple": "array", "none": "null", "any": None}
VALID = {"string", "number", "integer", "boolean", "object", "array", "null"}
_COLOR = re.compile(r"(^|_)(colou?r\d*|tint|accent|albedo|emission|rgb|rgba)($|_)", re.I)
_VEC3 = re.compile(r"(^|_)(position|pos|rotation|rot|scale|size|offset|direction|dir|origin|target_pos|velocity|vec3?|euler|extents?|normal)($|_)", re.I)
_VEC2 = re.compile(r"(^|_)(uv|vec2|anchor|pivot|resolution|viewport|screen_pos|tile)($|_)", re.I)
_LISTY = re.compile(r"(names|ids|paths|files|tags|targets|items|list|keys|values|platforms|constraints|metrics|notes|evidence|checks|parts|steps|commands)$", re.I)
SCALAR_UNION = ["string", "number", "boolean"]


def _items_for(name):
    n = str(name or "")
    if _COLOR.search(n):
        return {"type": "number", "description": "Colour channel: 0-1 (0-255 is accepted and converted)."}, {"minItems": 3, "maxItems": 4}
    if _VEC3.search(n):
        return {"type": "number"}, {"minItems": 1, "maxItems": 3}
    if _VEC2.search(n):
        return {"type": "number"}, {"minItems": 2, "maxItems": 2}
    if _LISTY.search(n):
        return {"type": "string"}, {}
    return {"type": SCALAR_UNION + ["object"]}, {}


def _fix(spec, name, fixes, path, depth=0):
    if depth > 24 or not isinstance(spec, dict):
        return spec if isinstance(spec, dict) else {"type": "string"}
    s = dict(spec)
    t = s.get("type")
    if isinstance(t, str) and t.lower() in ALIASES and t not in VALID:
        nt = ALIASES[t.lower()]
        fixes.append(f"{path}: type {t!r} -> {nt or 'any'}")
        if nt:
            s["type"] = t = nt
        else:
            s.pop("type"); t = None
    elif isinstance(t, list):
        nl = []
        for x in t:
            x2 = ALIASES.get(str(x).lower(), x) if x not in VALID else x
            if x2 in VALID and x2 not in nl:
                nl.append(x2)
        if nl != t:
            fixes.append(f"{path}: type list cleaned")
        s["type"] = t = (nl[0] if len(nl) == 1 else nl) if nl else None
        if t is None:
            s.pop("type")
    combin = any(k in s for k in ("anyOf", "oneOf", "allOf", "$ref", "const", "not"))
    if t is None and not combin:
        if "enum" in s and s["enum"]:
            kinds = {("boolean" if isinstance(v, bool) else "integer" if isinstance(v, int) else "number" if isinstance(v, float) else "string" if isinstance(v, str) else "x") for v in s["enum"]}
            if len(kinds) == 1 and "x" not in kinds:
                s["type"] = t = kinds.pop()
        elif "properties" in s:
            s["type"] = t = "object"
        elif "items" in s:
            s["type"] = t = "array"
        else:
            s["type"] = t = SCALAR_UNION + ["array", "object"]
            s.setdefault("description", "Any JSON value.")
        fixes.append(f"{path}: missing type -> {t}")
    ts = t if isinstance(t, list) else [t] if t else []
    if "enum" in s:
        e = s["enum"] if isinstance(s["enum"], list) else [s["enum"]]
        seen, out = set(), []
        for v in e:
            k = json.dumps(v, sort_keys=True)
            if k not in seen:
                seen.add(k); out.append(v)
        if len(out) != len(s["enum"] if isinstance(s["enum"], list) else [1, 2]):
            fixes.append(f"{path}: enum de-duplicated")
        if out:
            s["enum"] = out
        else:
            s.pop("enum")
        if "default" in s and "enum" in s and s["default"] not in s["enum"]:
            s.pop("default"); fixes.append(f"{path}: default not in enum removed")
    for lo, hi in (("minimum", "maximum"), ("minItems", "maxItems"), ("minLength", "maxLength"), ("exclusiveMinimum", "exclusiveMaximum")):
        if isinstance(s.get(lo), (int, float)) and isinstance(s.get(hi), (int, float)) and not isinstance(s.get(lo), bool) and s[lo] > s[hi]:
            s[lo], s[hi] = s[hi], s[lo]; fixes.append(f"{path}: {lo}/{hi} swapped")
    if "object" in ts or "properties" in s:
        props = s.get("properties")
        if not isinstance(props, dict):
            props = {}
        req = s.get("required")
        req = [r for r in req if isinstance(r, str)] if isinstance(req, list) else []
        newp = {}
        for k, v in props.items():
            if isinstance(v, dict) and isinstance(v.get("required"), bool):
                v = dict(v)
                if v.pop("required"):
                    req.append(k)
                fixes.append(f"{path}.{k}: draft-3 required lifted")
            newp[k] = _fix(v, k, fixes, f"{path}.{k}", depth + 1)
        if "properties" in s or ts == ["object"]:
            s["properties"] = newp
        open_obj = s.get("additionalProperties") is True or (isinstance(s.get("additionalProperties"), dict))
        clean, seen = [], set()
        for r in req:
            if r in seen:
                continue
            seen.add(r)
            if r in newp or open_obj:
                clean.append(r)
            else:
                fixes.append(f"{path}: required {r!r} is not a property - dropped")
        if clean or "required" in s:
            s["required"] = clean
        ap = s.get("additionalProperties")
        if isinstance(ap, dict):
            s["additionalProperties"] = _fix(ap, name, fixes, path + ".<additional>", depth + 1)
    if "array" in ts:
        it = s.get("items")
        if isinstance(it, list):  # draft-4 tuple form -> first item schema + length
            s["items"] = _fix(it[0] if it else {}, name, fixes, path + "[]", depth + 1)
            if it:
                s.setdefault("minItems", len(it)); s.setdefault("maxItems", len(it))
            fixes.append(f"{path}: tuple items normalised")
        elif not isinstance(it, dict) or not it:
            items, bounds = _items_for(name)
            s["items"] = items
            for k, v in bounds.items():
                s.setdefault(k, v)
            fixes.append(f"{path}: array items added ({items['type']})")
        else:
            s["items"] = _fix(it, name, fixes, path + "[]", depth + 1)
    for k in ("anyOf", "oneOf", "allOf"):
        if isinstance(s.get(k), list):
            s[k] = [_fix(x, name, fixes, f"{path}.{k}[{i}]", depth + 1) for i, x in enumerate(s[k])]
    return s


def perfect(schema, tool_name="tool", fixes=None):
    """Return (normalised_schema, fixes). Input is never mutated."""
    fixes = [] if fixes is None else fixes
    if not isinstance(schema, dict):
        fixes.append("$: schema missing -> empty object")
        return {"type": "object", "properties": {}, "required": []}, fixes
    s = json.loads(json.dumps(schema, default=str))
    if s.get("type") != "object":
        if "properties" in s or not s.get("type"):
            s["type"] = "object"
            fixes.append("$: root type -> object")
        else:
            s = {"type": "object", "properties": {"value": s}, "required": ["value"]}
            fixes.append("$: non-object root wrapped as {value}")
    s.setdefault("properties", {})
    return _fix(s, tool_name, fixes, "$"), fixes


def perfect_tool(tool):
    """Copy of an MCP tool dict with its inputSchema normalised (cached)."""
    if not isinstance(tool, dict):
        return tool
    key = "inputSchema" if "inputSchema" in tool else "input_schema" if "input_schema" in tool else "inputSchema"
    raw = tool.get(key)
    ck = (tool.get("name"), tool.get("server"), json.dumps(raw, sort_keys=True, default=str) if raw is not None else "")
    hit = _CACHE.get(ck)
    if hit is None:
        hit = document(perfect(raw, tool.get("name") or "tool")[0], tool)
        if len(_CACHE) > 4000:
            _CACHE.clear()
        _CACHE[ck] = hit
    out = dict(tool)
    out[key] = json.loads(json.dumps(hit))
    if not str(out.get("description") or "").strip():
        out["description"] = f"{out.get('name', 'tool')} (no description was provided by its server)."
    return out


# ── engine-aware parameter documentation (6.36) ─────────────────────────────
# Filled in ONLY where a schema gives a parameter no description and no enum,
# so models get the right units / axes / formats for the engine they target.
ENGINE_FACTS = {
    "roblox": {"unit": "studs", "up": "Y-up", "rot": "degrees", "path": "an Instance path such as Workspace.Map.Door", "color": "#rrggbb or [r,g,b] (0-1 or 0-255) -> Color3"},
    "unity": {"unit": "Unity units (metres)", "up": "Y-up, left-handed", "rot": "Euler degrees", "path": "an Assets/... path or a hierarchy path such as Root/Child", "color": "#rrggbb(aa) or [r,g,b,(a)] 0-1"},
    "godot": {"unit": "metres", "up": "Y-up", "rot": "degrees", "path": "a res:// path or a NodePath relative to the scene root", "color": "#rrggbb(aa) or [r,g,b,(a)] 0-1"},
    "blender": {"unit": "metres (Blender units)", "up": "Z-up", "rot": "degrees", "path": "an object name or a file path", "color": "#rrggbb(aa) or [r,g,b,(a)] 0-1 (linear)"},
    "figma": {"unit": "pixels", "up": "Y-down", "rot": "degrees", "path": "a node id or page/frame name", "color": "#rrggbb or [r,g,b] 0-1"},
}
PARAM_DOCS = {
    "position": "Position [x, y, z] in {unit}, {up}.", "location": "Location [x, y, z] in {unit}, {up}.", "center": "Centre point [x, y, z] in {unit}.",
    "origin": "Origin [x, y, z] in {unit}.", "offset": "Offset [x, y, z] in {unit}.", "spacing": "Spacing between copies in {unit} (number or [x, y, z]).",
    "rotation": "Rotation [x, y, z] in {rot}.", "rotation_deg": "Rotation [x, y, z] in degrees.", "rotation_y": "Yaw around the up axis in degrees.",
    "yaw": "Yaw in degrees (or true to randomise, where the tool says so).", "degrees": "Angle in degrees.",
    "scale": "Scale factor (number) or per-axis [x, y, z].", "size": "Size in {unit} (number or [x, y, z]).", "radius": "Radius in {unit}.",
    "width": "Width ({unit} for world objects, pixels for images/UI).", "height": "Height ({unit} for world objects, pixels for images/UI).",
    "depth": "Depth in {unit}.", "thickness": "Thickness in {unit}.", "wall_height": "Wall height in {unit}.", "wall_thickness": "Wall thickness in {unit}.",
    "floor_height": "Height of one floor in {unit}.", "floor_thickness": "Floor slab thickness in {unit}.", "floors": "Number of floors (integer >= 1).",
    "water_level": "Water surface height in {unit}.", "min_distance": "Minimum distance between placed items in {unit}.",
    "max_slope_degrees": "Steepest ground slope (degrees) an item may be placed on.", "scale_min": "Smallest random scale factor.", "scale_max": "Largest random scale factor.",
    "color": "Colour: {color}.", "color2": "Secondary colour: {color}.", "wall_color": "Wall colour: {color}.", "roof_color": "Roof colour: {color}.",
    "trim_color": "Trim colour: {color}.", "accent": "Accent colour: {color}.", "background": "Background colour: {color}.",
    "roughness": "PBR roughness 0 (mirror) - 1 (matte).", "emission_strength": "Emission strength (0 = off).", "strength": "Effect strength (tool-specific scale, 0 = none).",
    "material": "Material name (existing material or engine preset).", "name": "Name for the created/target object.", "new_name": "New name.",
    "path": "Target: {path}.", "paths": "List of targets: {path}.", "parent": "Parent: {path}.", "target": "Target: {path}.", "targets": "Targets: {path}.",
    "scene_path": "Scene file: {path}.", "script_path": "Script file: {path}.", "prefab_path": "Prefab asset path (Assets/....prefab).",
    "names": "Object names to act on.", "name_contains": "Case-insensitive substring filter on names.", "class_name": "Exact class/type name to filter or create.",
    "count": "How many to create/process (integer).", "rows": "Number of rows (integer).", "columns": "Number of columns (integer).", "limit": "Maximum results to return.",
    "seed": "Random seed - same seed, same result.", "loop": "Loop playback (true/false).", "speed": "Speed multiplier (1 = normal).", "fps": "Frames per second.",
    "frame": "Frame number.", "frame_start": "First frame.", "frame_end": "Last frame (inclusive).", "start_frame": "Frame to start at.", "seconds": "Duration in seconds.",
    "smooth": "Smooth shading/interpolation (true/false).", "closed": "Close the path/loop (true/false).", "apply": "Apply the change now instead of previewing.",
    "overwrite": "Replace an existing item with the same name/path.", "clear_existing": "Remove previously generated items first.", "clear": "Clear before writing.",
    "random_yaw": "Randomise rotation around the up axis.", "align_to_normal": "Tilt items to the surface normal.", "snap_to_ground": "Drop items onto the ground below.",
    "anchored": "Anchor parts so physics does not move them.", "lit_windows": "Add emissive lit windows.", "include_transform": "Include position/rotation/scale in the output.",
    "relative": "Interpret values as relative to the current ones.", "axis": "Axis name: x, y or z.", "grid": "Grid counts [x, y(, z)].", "resolution": "Resolution in pixels or cells.",
    "properties": "Property name -> value object.", "attributes": "Attribute name -> value object.", "changes": "Changes to apply (name -> value).",
    "tags": "Tag strings.", "tag": "Tag string.", "label": "Short human-readable label.", "title": "Title text.", "text": "Text content.", "lines": "Source lines (no newline escaping needed).",
    "studio_id": "Exact Studio id from list_roblox_studios; omit when one Studio is connected.", "server": "MCP server id (roblox, unity, godot, blender, figma ...).",
    "tool": "Exact tool name.", "arguments": "Arguments object for that tool.", "query": "Search text.", "cursor": "Pagination cursor from the previous page.",
    "refresh": "Re-read live state instead of the cache.", "timeout_seconds": "Max seconds to wait.", "timeout_s": "Max seconds to wait.", "page_size": "Items per page.",
    "engine": "Engine id: roblox, unity, godot, blender, figma or general.", "feature": "The feature or system this is for (one sentence).",
    "context": "Extra context (current state, constraints already known).", "platforms": "Target platforms (e.g. pc, mobile, console, web, vr).",
    "constraints": "Hard constraints to respect.", "metrics": "Metrics that define success (e.g. frame time, memory, load time).",
    "target_tier": "Target hardware tier (e.g. low-end mobile, mid PC, high-end PC).", "style": "Visual/art style keywords.", "objective": "The goal, in one sentence.",
    "request": "The user's request, verbatim or summarised.", "evidence": "Verification evidence strings (logs, read-backs, test results).",
    "start_line": "First line (1-based).", "end_line": "Last line (1-based, inclusive).", "from_path": "Current path.", "to_path": "New path.",
    "edits": "Edits to apply in order.", "find": "Text to find.", "replace_with": "Replacement text.", "value": "New value (any JSON type the property accepts).",
    "enabled": "On/off.", "type": "Kind/type of the item.", "id": "Identifier returned by an earlier call.", "source": "Source code or source path.", "script": "Script source code.",
}


def _engine_for(tool):
    n = str(tool.get("name") or "").lower()
    for e in ENGINE_FACTS:
        if n.startswith(f"ms_{e}_") or n.startswith(f"{e}_"):
            return e
    sv = str(tool.get("server") or "").lower()
    return sv if sv in ENGINE_FACTS else None


def document(schema, tool):
    """Fill missing top-level parameter descriptions (in place) - engine-aware."""
    eng = _engine_for(tool)
    facts = ENGINE_FACTS.get(eng) or {"unit": "the engine's world units", "up": "engine up-axis", "rot": "degrees", "path": "a path/name as the tool expects", "color": "#rrggbb or [r,g,b] 0-1"}
    props = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(props, dict):
        return schema
    for k, v in props.items():
        if isinstance(v, dict) and not v.get("description") and not v.get("enum"):
            base = PARAM_DOCS.get(k)
            if base:
                v["description"] = base.format(**facts)
    return schema


_CACHE = {}
