# SPDX-License-Identifier: GPL-3.0-or-later
"""engine_toolkit.py - native, typed, verified tools for Blender, Roblox Studio, Unity and Godot.

WHY
The four engines expose very different (and mostly small) MCP surfaces: Blender is
"run this Python", Roblox is "run this Luau" + a few readers, Unity is a set of
action-dispatch tools, Godot is 14 coarse project tools. A model asked to "add a
bevel modifier and export a GLB" has to hand-write correct engine code every time.

This module gives every engine a catalogue of typed, intention-level tools
(`ms_blender_add_modifier`, `ms_roblox_set_properties`, `ms_unity_create_object`,
`ms_godot_add_autoload` ...). Each tool compiles to the engine's REAL native call:

  Blender / Roblox  -> a generated, argument-safe Python / Luau program that is sent
                       through the engine's own execute tool and prints one JSON line;
  Unity             -> the exact advertised CoplayDev unity-mcp tool calls, in order;
  Godot             -> bridge-side project-file work (project.godot, .tscn, .gd) plus
                       the native run/stop/debug tools, so it works without an editor.

Arguments never get spliced into code as text: they travel as base64 JSON (Python) or
a long-bracket JSON string (Luau), so quotes/newlines in a model's arguments cannot
break the program - the bug class behind most "JSON schema" failures on code engines.

Everything here is pure stdlib and has no import-time side effects. The bridge injects
a `Ctx` that knows how to call a connected MCP server.
"""
from __future__ import annotations

import base64
import json
import os
import re
import textwrap
import time

TOOLKIT_VERSION = "1.0"
MARKER = "MS_RESULT:"
ENGINES = ("blender", "roblox", "unity", "godot")
REGISTRY = {}


class ToolkitError(Exception):
    """A normal, reportable failure (bad target, engine not connected, ...)."""

    def __init__(self, message, hint=""):
        super().__init__(message)
        self.hint = hint


# ── registry ────────────────────────────────────────────────────────────────
_COMMON = {
    "blender": {
        "target": {"type":"string","enum":["auto","connected","workspace"],"default":"auto","description":"auto follows the user's Blender Workspace AI-target switch; connected uses the existing desktop MCP, workspace uses real headless Blender."},
        "workspace_project": {"type":"string","description":"Expected headless project id, from ms_blender_workspace status. Rejects a project switched by another window."},
    },
    "roblox": {
        "studio_id": {"type": "string", "description": "Exact Studio id from list_roblox_studios. Optional when only one Studio is connected."},
        "mode": {"type": "string", "enum": ["Edit", "Server", "Client"], "description": "Which DataModel to act in (default Edit)."},
    },
    "unity": {},
    "godot": {
        "project_path": {"type": "string", "description": "Absolute folder containing project.godot. Remembered after the first successful call."},
    },
}
_ALWAYS = {
    "dry_run": {"type": "boolean", "description": "Return the exact native code/calls that WOULD run, without running anything."},
}


def _perfect_schema(schema, name):
    try:
        import schema_perfect
        return schema_perfect.perfect(schema, name)[0]
    except Exception:
        return schema


def register(engine, name, description, props, required=(), handler=None, writes=False, local=False):
    assert engine in ENGINES, engine
    schema_props = {}
    schema_props.update(props)
    if not local:
        schema_props.update(_COMMON[engine])
    elif engine == "godot":
        schema_props.update(_COMMON["godot"])
    schema_props.update(_ALWAYS)
    REGISTRY[name] = {
        "name": name,
        "engine": engine,
        "description": description.strip(),
        "inputSchema": _perfect_schema({"type": "object", "properties": schema_props, "required": list(required)}, name),
        "handler": handler,
        "writes": bool(writes),
        "local": bool(local),
    }
    return REGISTRY[name]


def tool(engine, name, description, props, required=(), writes=False, local=False):
    """Decorator form of register()."""
    def deco(fn):
        register(engine, name, description, props, required, fn, writes, local)
        return fn
    return deco


def is_toolkit_tool(name):
    return name in REGISTRY


def engine_of(name):
    return (REGISTRY.get(name) or {}).get("engine")


def definitions():
    """MCP-shaped tool dicts (name/description/inputSchema), safe to publish."""
    out = []
    for t in REGISTRY.values():
        out.append({
            "name": t["name"],
            "description": f"[{t['engine']} native" + (" · writes" if t["writes"] else " · read-only") + "] " + t["description"],
            "inputSchema": json.loads(json.dumps(t["inputSchema"])),
        })
    return out


def counts():
    c = {e: 0 for e in ENGINES}
    for t in REGISTRY.values():
        c[t["engine"]] += 1
    return c


# ── argument helpers ────────────────────────────────────────────────────────
def vec3(v, default=None):
    """[x,y,z] from a list / {x,y,z} / 'x,y,z' / JSON string, or `default`."""
    if v is None or v == "":
        return default
    if isinstance(v, str):
        s = v.strip()
        try:
            return vec3(json.loads(s), default)
        except Exception:
            parts = [p for p in re.split(r"[\s,;]+", s.strip("[]() ")) if p]
            v = parts
    if isinstance(v, dict):
        low = {str(k).lower(): x for k, x in v.items()}
        v = [low.get("x"), low.get("y"), low.get("z")]
    if isinstance(v, (int, float)):
        return [float(v)] * 3
    if isinstance(v, (list, tuple)) and len(v) >= 3:
        try:
            return [float(v[0]), float(v[1]), float(v[2])]
        except Exception:
            return default
    return default


def color4(v, default=None):
    """[r,g,b,a] floats 0..1 from hex / name / list (0..1 or 0..255) / dict."""
    names = {"red": "#ff0000", "green": "#00ff00", "blue": "#0000ff", "white": "#ffffff", "black": "#000000",
             "yellow": "#ffff00", "orange": "#ff8800", "purple": "#8000ff", "pink": "#ff66aa", "cyan": "#00ffff",
             "magenta": "#ff00ff", "gray": "#808080", "grey": "#808080", "brown": "#8b5a2b"}
    if v is None or v == "":
        return default
    if isinstance(v, str):
        s = v.strip().lower()
        s = names.get(s, s)
        if re.fullmatch(r"#?[0-9a-f]{3}", s):
            s = "".join(c * 2 for c in s.lstrip("#"))
        if re.fullmatch(r"#?[0-9a-f]{6}([0-9a-f]{2})?", s):
            s = s.lstrip("#")
            r, g, b = (int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
            a = int(s[6:8], 16) / 255.0 if len(s) == 8 else 1.0
            return [r, g, b, a]
        try:
            return color4(json.loads(s), default)
        except Exception:
            return default
    if isinstance(v, dict):
        low = {str(k).lower(): x for k, x in v.items()}
        v = [low.get("r"), low.get("g"), low.get("b"), low.get("a", 1)]
    if isinstance(v, (list, tuple)) and len(v) >= 3:
        try:
            f = [float(x) for x in v[:4]]
        except Exception:
            return default
        if len(f) == 3:
            f.append(1.0)
        if max(f) > 1.0:
            f = [x / 255.0 for x in f]
        return [max(0.0, min(1.0, x)) for x in f]
    return default


def num(v, default=None, lo=None, hi=None, integer=False):
    try:
        if v is None or v == "":
            return default
        x = float(v)
    except Exception:
        return default
    if lo is not None:
        x = max(lo, x)
    if hi is not None:
        x = min(hi, x)
    return int(round(x)) if integer else x


def boolean(v, default=False):
    if isinstance(v, bool):
        return v
    if v is None or v == "":
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def as_list(v):
    if v is None or v == "":
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("["):
            try:
                x = json.loads(s)
                if isinstance(x, list):
                    return x
            except Exception:
                pass
        return [p.strip() for p in re.split(r"[,\n]", s) if p.strip()]
    return [v]


def as_dict(v):
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v.strip().startswith("{"):
        try:
            x = json.loads(v)
            if isinstance(x, dict):
                return x
        except Exception:
            pass
    return {}


def b64json(obj):
    return base64.b64encode(json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")).decode("ascii")


def long_bracket(text):
    """A Luau long-bracket string literal that can hold `text` verbatim."""
    level = 2
    while ("]" + "=" * level + "]") in text:
        level += 1
    eq = "=" * level
    return f"[{eq}[{text}]{eq}]"


# ── code generation: Blender (Python) ───────────────────────────────────────
_PY_PRELUDE = '''\
import bpy, json, base64, math, traceback
A = json.loads(base64.b64decode("%(b64)s").decode("utf-8"))
R = {}
def _obj(n):
    o = bpy.data.objects.get(n)
    if o is None:
        raise ValueError("no object named %%r (objects: %%s)" %% (n, ", ".join(sorted(bpy.data.objects.keys())[:40]) or "none"))
    return o
def _v(x, d=(0.0, 0.0, 0.0)):
    return tuple(x) if x else tuple(d)
def _rad(x):
    return tuple(math.radians(a) for a in x)
def _select(objs, active=None):
    for o in bpy.context.view_layer.objects:
        try: o.select_set(False)
        except Exception: pass
    for o in objs:
        try: o.select_set(True)
        except Exception: pass
    if active is not None: bpy.context.view_layer.objects.active = active
def _mode_object():
    try:
        if bpy.context.object and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
    except Exception: pass
def _info(o):
    d = {"name": o.name, "type": o.type, "location": [round(c, 4) for c in o.location],
         "rotation_deg": [round(math.degrees(c), 3) for c in o.rotation_euler], "scale": [round(c, 4) for c in o.scale]}
    if o.parent: d["parent"] = o.parent.name
    if o.type == "MESH" and o.data:
        d["vertices"] = len(o.data.vertices); d["faces"] = len(o.data.polygons)
    d["materials"] = [s.material.name for s in o.material_slots if s.material]
    d["modifiers"] = [m.type for m in getattr(o, "modifiers", [])]
    d["collections"] = [c.name for c in o.users_collection]
    return d
def _fcurves(action):
    """F-curves of an action on every Blender version (5.0 removed Action.fcurves in favour of layers/strips/channelbags)."""
    if action is None: return []
    fc = getattr(action, "fcurves", None)
    if fc is not None: return list(fc)
    out = []
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for cb in getattr(strip, "channelbags", []):
                out.extend(cb.fcurves)
    return out
_mode_object_done = False
try:
%(body)s
    R.setdefault("ok", True)
except Exception as _e:
    R = {"ok": False, "error": type(_e).__name__ + ": " + str(_e), "trace": traceback.format_exc()[-700:]}
print("%(marker)s" + json.dumps(R, default=str))
'''


def blender_code(body, args):
    """Wrap `body` (python using A for arguments and R for the result) into a program."""
    clean = {k: v for k, v in (args or {}).items() if k not in ("dry_run", "timeout_seconds")}
    return _PY_PRELUDE % {"b64": b64json(clean), "body": textwrap.indent(textwrap.dedent(body).strip("\n"), "    "), "marker": MARKER}


# ── code generation: Roblox (Luau) ──────────────────────────────────────────
_LUAU_PRELUDE = '''\
local HttpService = game:GetService("HttpService")
local A = HttpService:JSONDecode(%(lit)s)
local R = {}
local CHS = game:GetService("ChangeHistoryService")
local function ser(v)
    local t = typeof(v)
    if t == "Vector3" then return {x = v.X, y = v.Y, z = v.Z}
    elseif t == "Vector2" then return {x = v.X, y = v.Y}
    elseif t == "Color3" then return "#" .. v:ToHex()
    elseif t == "CFrame" then local rx, ry, rz = v:ToEulerAnglesXYZ(); return {pos = {x = v.X, y = v.Y, z = v.Z}, rot_deg = {x = math.deg(rx), y = math.deg(ry), z = math.deg(rz)}}
    elseif t == "UDim2" then return {xs = v.X.Scale, xo = v.X.Offset, ys = v.Y.Scale, yo = v.Y.Offset}
    elseif t == "UDim" then return {s = v.Scale, o = v.Offset}
    elseif t == "EnumItem" then return tostring(v)
    elseif t == "Instance" then return v:GetFullName()
    elseif t == "BrickColor" then return v.Name
    elseif t == "NumberRange" then return {min = v.Min, max = v.Max}
    elseif t == "Rect" then return {minx = v.Min.X, miny = v.Min.Y, maxx = v.Max.X, maxy = v.Max.Y}
    elseif t == "number" or t == "string" or t == "boolean" or t == "nil" then return v
    elseif t == "table" then return "<table>"
    end
    return tostring(v)
end
local function split(path)
    local parts = {}
    for p in string.gmatch(path, "[^%%.]+") do table.insert(parts, p) end
    return parts
end
local function resolve(path)
    if path == nil or path == "" then error("a path is required") end
    path = tostring(path)
    path = string.gsub(path, "^game%%.", "")
    path = string.gsub(path, "^game/", "")
    path = string.gsub(path, "/", ".")
    local cur = game
    local parts = split(path)
    for i, name in ipairs(parts) do
        local nxt = nil
        if cur == game then
            local ok, svc = pcall(function() return game:GetService(name) end)
            if ok and svc then nxt = svc end
        end
        if not nxt then nxt = cur:FindFirstChild(name) end
        if not nxt then
            local kids = {}
            for _, c in ipairs(cur:GetChildren()) do table.insert(kids, c.Name); if #kids >= 25 then break end end
            error("cannot find '" .. name .. "' under " .. cur:GetFullName() .. " (children: " .. table.concat(kids, ", ") .. ")")
        end
        cur = nxt
    end
    return cur
end
local function vec3(t) return Vector3.new(t[1] or t.x or 0, t[2] or t.y or 0, t[3] or t.z or 0) end
local function col3(c)
    if type(c) == "string" then return Color3.fromHex(c) end
    if type(c) == "table" then
        local r, g, b = c[1] or c.r or 0, c[2] or c.g or 0, c[3] or c.b or 0
        if r > 1 or g > 1 or b > 1 then return Color3.fromRGB(r, g, b) end
        return Color3.new(r, g, b)
    end
    return c
end
local function coerce(inst, prop, v)
    local cur = nil
    local okc = pcall(function() cur = inst[prop] end)
    if not okc then error("'" .. tostring(prop) .. "' is not a property of " .. inst.ClassName) end
    local t = typeof(cur)
    if t == "Vector3" and type(v) == "table" then return vec3(v)
    elseif t == "Vector2" and type(v) == "table" then return Vector2.new(v[1] or v.x or 0, v[2] or v.y or 0)
    elseif t == "Color3" then return col3(v)
    elseif t == "BrickColor" then return BrickColor.new(v)
    elseif t == "UDim2" and type(v) == "table" then
        if v.xs ~= nil or v.xo ~= nil then return UDim2.new(v.xs or 0, v.xo or 0, v.ys or 0, v.yo or 0) end
        return UDim2.new(v[1] or 0, v[2] or 0, v[3] or 0, v[4] or 0)
    elseif t == "UDim" and type(v) == "table" then return UDim.new(v.s or v[1] or 0, v.o or v[2] or 0)
    elseif t == "CFrame" and type(v) == "table" then
        local p = v.pos or v
        local cf = CFrame.new(p[1] or p.x or 0, p[2] or p.y or 0, p[3] or p.z or 0)
        local r = v.rot_deg
        if r then cf = cf * CFrame.Angles(math.rad(r.x or r[1] or 0), math.rad(r.y or r[2] or 0), math.rad(r.z or r[3] or 0)) end
        return cf
    elseif t == "EnumItem" then
        local ename = tostring(cur.EnumType)
        local key = tostring(v):gsub("^Enum%%.%%w+%%.", "")
        local item = Enum[ename][key]
        if item == nil then error("'" .. tostring(v) .. "' is not a valid " .. ename) end
        return item
    elseif t == "NumberRange" and type(v) == "table" then return NumberRange.new(v.min or v[1] or 0, v.max or v[2] or v.min or v[1] or 0)
    elseif t == "number" and type(v) == "string" then return tonumber(v)
    elseif t == "boolean" and type(v) == "string" then return v == "true"
    end
    return v
end
local function setprops(inst, props)
    local applied = {}
    for k, v in pairs(props or {}) do
        inst[k] = coerce(inst, k, v)
        table.insert(applied, k)
    end
    return applied
end
local function brief(i)
    local d = {name = i.Name, class = i.ClassName, path = i:GetFullName()}
    if i:IsA("BasePart") then d.position = ser(i.Position); d.size = ser(i.Size); d.anchored = i.Anchored end
    return d
end
local function waypoint(name) pcall(function() CHS:SetWaypoint("MS: " .. name) end) end
local ok, err = xpcall(function()
%(body)s
end, function(e) return tostring(e) .. "\\n" .. string.sub(debug.traceback(), 1, 500) end)
if not ok then R = {ok = false, error = err} elseif R.ok == nil then R.ok = true end
local out = "%(marker)s" .. HttpService:JSONEncode(R)
print(out)
return out
'''


def luau_code(body, args):
    clean = {k: v for k, v in (args or {}).items() if k not in ("dry_run", "timeout_seconds", "studio_id", "mode")}
    lit = long_bracket(json.dumps(clean, ensure_ascii=False, default=str))
    return _LUAU_PRELUDE % {"lit": lit, "body": textwrap.indent(textwrap.dedent(body).strip("\n"), "    "), "marker": MARKER}


# ── result parsing ──────────────────────────────────────────────────────────
def extract_result(text):
    """Pull the MS_RESULT JSON back out of an engine's raw output."""
    if not text:
        return None
    idx = str(text).rfind(MARKER)
    if idx < 0:
        return None
    rest = str(text)[idx + len(MARKER):]
    line = rest.split("\n", 1)[0].strip()
    try:
        return json.loads(line)
    except Exception:
        # some servers wrap the output in quotes/escapes
        try:
            return json.loads(line.rstrip('"\''))
        except Exception:
            pass
        dec = json.JSONDecoder()
        try:
            obj, _ = dec.raw_decode(rest.strip())
            return obj
        except Exception:
            return None


# ── execution ───────────────────────────────────────────────────────────────
class Ctx:
    """Interface the bridge implements. Tests provide fakes."""

    def call(self, server, tool, arguments, timeout=120):  # -> {"text": str, "images": []}
        raise NotImplementedError

    def advertised(self, server):  # -> set[str] | None
        raise NotImplementedError

    def studio_id(self, args):  # -> (id, reason)
        return str((args or {}).get("studio_id") or ""), "given"

    def project_hint(self, engine):
        return ""

    def remember_project(self, engine, path):
        pass


def _need(ctx, server, *candidates):
    adv = ctx.advertised(server)
    if adv is None:
        raise ToolkitError(f"the '{server}' MCP server is not connected",
                           f"Start the {server} editor/server, then run ms_native_capabilities with refresh=true.")
    for c in candidates:
        if c in adv:
            return c
    raise ToolkitError(f"the '{server}' server does not advertise any of: {', '.join(candidates)}",
                       "Run ms_native_capabilities to see what this connection exposes; this tool needs " + candidates[0] + ".")


def run_code(ctx, engine, body, args, timeout=120, label=""):
    """Compile `body` for the engine and execute it natively. Returns (result_dict, native_call)."""
    if engine == "blender":
        tool_name = _need(ctx, "blender", "execute_blender_code")
        code = blender_code(body, args)
        call = {"tool": tool_name, "arguments": {"code": code}}
    elif engine == "roblox":
        tool_name = _need(ctx, "roblox", "execute_luau")
        code = luau_code(body, args)
        stud, why = ctx.studio_id(args)
        if why == "ambiguous":
            raise ToolkitError("more than one Roblox Studio is connected", "Pass studio_id (see list_roblox_studios).")
        call = {"tool": tool_name, "arguments": {"code": code, "datamodel_type": str(args.get("mode") or "Edit")}}
        if stud:
            call["arguments"]["studio_id"] = stud
    else:
        raise ToolkitError(f"{engine} does not run generated code")
    call["label"] = label
    if args.get("dry_run"):
        return {"dryRun": True, "code": code}, call
    raw = ctx.call(engine, call["tool"], call["arguments"], timeout)
    text = str((raw or {}).get("text") or "")
    res = extract_result(text)
    if res is None:
        low = text.lower()
        failed = any(w in low for w in ("traceback", "error", "exception", "failed", "attempt to"))
        res = {"ok": not failed, "raw": text[:2500], "note": "the engine did not return the structured result line"}
    return res, call


def run(name, args, ctx):
    """Execute one toolkit tool. Always returns {"text": json, "images": []} and never raises."""
    t0 = time.time()
    spec = REGISTRY.get(name)
    if spec is None:
        return {"text": json.dumps({"ok": False, "error": f"unknown toolkit tool {name}"}), "images": []}
    args = dict(args or {})
    env = {"ok": False, "tool": name, "engine": spec["engine"]}
    images = []
    try:
        out = spec["handler"](args, ctx)
        if isinstance(out, tuple):
            out, images = out[0], out[1]
        out = out if isinstance(out, dict) else {"result": out}
        ok = out.pop("ok", True)
        env.update({"ok": bool(ok)})
        env.update(out)
        if spec["writes"] and env["ok"] and not args.get("dry_run"):
            env.setdefault("next", "Read it back (the matching ms_*_list / get tool or ms_native_read) before telling the user it worked.")
    except ToolkitError as exc:
        env.update({"ok": False, "error": str(exc), "hint": exc.hint})
    except Exception as exc:  # engine/transport errors become a structured failure
        env.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    env["ms"] = int((time.time() - t0) * 1000)
    text = json.dumps(env, indent=2, ensure_ascii=False, default=str)
    # MS_TOOL_RESULT_LIMIT: characters kept from one native result (default 60000;
    # 0 = never clip). Matches the optional "Limits" setting in the extension menu.
    try:
        _limit = int(os.environ.get("MS_TOOL_RESULT_LIMIT", "60000"))
    except ValueError:
        _limit = 60000
    if _limit > 0 and len(text) > _limit:
        text = text[:_limit] + "\n... [truncated at %d characters by the bridge - Settings > Limits > Tool results > No limit (or MS_TOOL_RESULT_LIMIT=0) removes this]" % _limit
    return {"text": text, "images": images}


# ── bridge-side snapshots (diff what changed, including the user's own edits) ──
_SNAPSHOTS = {}


def snapshot_store(engine, label, data):
    _SNAPSHOTS[(engine, label)] = {"at": time.time(), "data": data}


def snapshot_get(engine, label):
    return _SNAPSHOTS.get((engine, label))


def diff_maps(before, after):
    """Structured diff of two {key: {prop: value}} maps."""
    added = sorted(k for k in after if k not in before)
    removed = sorted(k for k in before if k not in after)
    changed = {}
    for k in before:
        if k in after and before[k] != after[k]:
            b, a = before[k], after[k]
            if isinstance(b, dict) and isinstance(a, dict):
                props = {p: {"from": b.get(p), "to": a.get(p)} for p in sorted(set(b) | set(a)) if b.get(p) != a.get(p)}
            else:
                props = {"value": {"from": b, "to": a}}
            changed[k] = props
    return {"added": added, "removed": removed, "changed": changed,
            "summary": f"{len(added)} added, {len(removed)} removed, {len(changed)} changed"}


# load engine modules (each registers its tools on import)
PRO_ERRORS = {}


def _load_all():
    import importlib
    for mod in ("toolkit_blender", "toolkit_roblox", "toolkit_unity", "toolkit_godot"):
        importlib.import_module(mod)
    # "Pro" packs add tools only; a failure in one must never take the base tools down.
    for mod in ("toolkit_blender_pro", "toolkit_roblox_pro", "toolkit_roblox_audio_npc", "toolkit_unity_pro", "toolkit_godot_pro", "toolkit_godot_world", "toolkit_godot_game", "toolkit_godot_build", "toolkit_godot_audio_npc", "toolkit_blender_props"):
        try:
            importlib.import_module(mod)
        except ModuleNotFoundError as exc:
            if exc.name != mod:
                PRO_ERRORS[mod] = repr(exc)
        except Exception as exc:  # pragma: no cover - import-time only
            PRO_ERRORS[mod] = repr(exc)


_loaded = False


def ensure_loaded():
    global _loaded
    if not _loaded:
        _loaded = True
        _load_all()
    return REGISTRY
