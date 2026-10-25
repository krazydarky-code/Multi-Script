# SPDX-License-Identifier: GPL-3.0-or-later
"""Godot "pro" tools for engine_toolkit: animation, particles, UI kits + themes, shaders, level blockouts, terrain,
gameplay scripts, environments, audio buses, export presets, sprite sheets, scene audit and a headless GDScript runner.

Like the rest of the Godot toolkit these work on the project's plain-text files (.tscn/.tres/.gd/.gdshader/.cfg), so they
need no running editor. Every generated scene/script/resource is loaded by a real headless Godot in the test-suite."""
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import tempfile

from engine_toolkit import tool, as_list, as_dict, num, boolean, ToolkitError
from toolkit_godot import (_proj, _abs, _res, _read, _write, find_exe, Scene, SCENE, G, fmt_num,
                           parse_project, get_setting, set_setting)

OVERWRITE = {"type": "boolean", "description": "Replace files that already exist (default false)."}
INTO = {"type": "string", "description": "Optional existing scene (res://...tscn) to merge the result into instead of creating a new scene."}
PARENT = {"type": "string", "description": "Node path inside `into_scene` to attach to ('.' = root)."}


# ───────────────────────── literal helpers ─────────────────────────
def f(x):
    return fmt_num(float(x)) if not isinstance(x, bool) else ("1" if x else "0")


def V2(x, y):
    return "Vector2(%s, %s)" % (f(x), f(y))


def V3(x, y, z):
    return "Vector3(%s, %s, %s)" % (f(x), f(y), f(z))


def hex_rgba(c, default="#ffffff"):
    """'#rrggbb[aa]' / [r,g,b(,a)] (0-1 or 0-255) -> (r,g,b,a) floats."""
    if c is None:
        c = default
    if isinstance(c, str):
        s = c.strip().lstrip("#")
        if re.fullmatch(r"[0-9a-fA-F]{3}", s):
            s = "".join(ch * 2 for ch in s)
        if re.fullmatch(r"[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", s):
            v = [int(s[i:i + 2], 16) / 255.0 for i in range(0, len(s), 2)]
            return tuple((v + [1.0])[:4])
        return hex_rgba(default)
    if isinstance(c, (list, tuple)) and len(c) >= 3:
        v = [float(x) for x in c]
        if max(v) > 1.0:
            v = [x / 255.0 for x in v]
        return tuple((v + [1.0])[:4])
    return hex_rgba(default)


def C(c, default="#ffffff", alpha=None):
    r, g, b, a = hex_rgba(c, default)
    if alpha is not None:
        a = alpha
    return "Color(%s, %s, %s, %s)" % (f(round(r, 4)), f(round(g, 4)), f(round(b, 4)), f(round(a, 4)))


def lerp_col(a, b, t):
    ca, cb = hex_rgba(a), hex_rgba(b)
    return tuple(ca[i] + (cb[i] - ca[i]) * t for i in range(4))


def Cx(t):
    return "Color(%s, %s, %s, %s)" % tuple(f(round(x, 4)) for x in t)


def gstr(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def SNAME(s):
    return '&"' + re.sub(r'[^\w .-]', "", str(s)) + '"'


def PF32(xs):
    return "PackedFloat32Array(" + ", ".join(f(x) for x in xs) + ")"


def fill(template, **vals):
    for k, v in vals.items():
        template = template.replace("@@" + k + "@@", str(v))
    left = re.findall(r"@@(\w+)@@", template)
    if left:
        raise ToolkitError("internal template placeholder left unfilled: " + ", ".join(sorted(set(left))))
    return template


def ident(s, default="x"):
    s = re.sub(r"[^0-9A-Za-z_]+", "_", str(s or "")).strip("_")
    return s or default


# ───────────────────────── scene snippet builder ─────────────────────────
def set_raw(sc, block, key, raw):
    """Set `key = raw` on a node block without any literal conversion (raw is already Godot text)."""
    sc.set_props(block, {}, remove=[key])
    body = block["body"]
    at = len(body)
    while at > 0 and body[at - 1].strip() == "":
        at -= 1
    body.insert(at, "%s = %s" % (key, raw))


class SB:
    """Builds a .tscn snippet (ext/sub resources + node tree) that can be saved as a scene or merged into an existing one."""

    def __init__(self, root_name, root_type, tag="ms"):
        self.tag = tag
        self.ext, self.subs, self.nodes = [], [], []
        self._n = 0
        self.root = self.node(root_name, root_type, parent=None)

    def _id(self, kind):
        self._n += 1
        return "%s_%s" % (ident(kind), hashlib.md5(("%s|%s|%d" % (self.tag, kind, self._n)).encode()).hexdigest()[:5])

    def ext_res(self, path, typ):
        for e in self.ext:
            if e["path"] == path:
                return e["id"]
        eid = "%d_%s" % (len(self.ext) + 1, hashlib.md5(path.encode()).hexdigest()[:5])
        self.ext.append({"type": typ, "path": path, "id": eid})
        return eid

    def sub(self, typ, props=None, lines=None, hint=None):
        sid = self._id(hint or typ)
        body = list(lines or [])
        for k, v in (props or {}).items():
            body.append("%s = %s" % (k, v))
        self.subs.append({"type": typ, "id": sid, "body": body})
        return sid

    def node(self, name, typ=None, parent=".", props=None, groups=None, script=None, instance=None):
        name = str(name)
        body = []
        if script:
            body.append('script = ExtResource("%s")' % self.ext_res(script, "Script"))
        for k, v in (props or {}).items():
            body.append("%s = %s" % (k, v))
        key = "." if parent is None else (name if parent == "." else parent + "/" + name)
        self.nodes.append({"name": name, "type": typ, "parent": parent, "groups": list(groups or []), "body": body,
                           "instance": self.ext_res(instance, "PackedScene") if instance else None, "key": key})
        return key

    def render(self):
        out = ["[gd_scene load_steps=%d format=3]" % (len(self.ext) + len(self.subs) + 1), ""]
        for e in self.ext:
            out.append('[ext_resource type="%s" path="%s" id="%s"]' % (e["type"], e["path"], e["id"]))
        if self.ext:
            out.append("")
        for s in self.subs:
            out.append('[sub_resource type="%s" id="%s"]' % (s["type"], s["id"]))
            out.extend(s["body"])
            out.append("")
        for n in self.nodes:
            out.append(self._node_header(n, n["parent"]))
            out.extend(n["body"])
            out.append("")
        return "\n".join(out).rstrip("\n") + "\n"

    @staticmethod
    def _node_header(n, parent):
        h = '[node name="%s"' % n["name"]
        if n["instance"]:
            h += ' parent="%s" instance=ExtResource("%s")' % (parent, n["instance"])
        else:
            h += ' type="%s"' % n["type"]
            if parent is not None:
                h += ' parent="%s"' % parent
        if n["groups"]:
            h += " groups=[" + ", ".join('"%s"' % g for g in n["groups"]) + "]"
        return h + "]"

    def merge_resources(self, sc, before=None):
        """Insert ext/sub resources into an existing Scene (ids remapped). Returns the id map."""
        used = {b["attrs"].get("id") for b in sc.blocks if b["kind"] in ("ext_resource", "sub_resource")}
        idmap = {}
        for e in self.ext:
            idmap[e["id"]] = sc.ext_id(e["path"], e["type"])
        for s in self.subs:
            sid = s["id"]
            while sid in used:
                sid += "x"
            used.add(sid)
            idmap[s["id"]] = sid
        def remap(line):
            return re.sub(r'(ExtResource|SubResource)\("([^"]+)"\)', lambda m: '%s("%s")' % (m.group(1), idmap.get(m.group(2), m.group(2))), line)
        first_node = next((i for i, b in enumerate(sc.blocks) if b["kind"] == "node"), len(sc.blocks))
        at = sc.blocks.index(before) if before is not None else first_node
        for s in self.subs:
            blk = {"kind": "sub_resource", "attrs": {"type": s["type"], "id": idmap[s["id"]]}, "header": '[sub_resource type="%s" id="%s"]' % (s["type"], idmap[s["id"]]),
                   "body": [remap(l) for l in s["body"]] + [""]}
            sc.blocks.insert(at, blk)
            at += 1
        return idmap, remap

    def merge_into(self, sc, parent_key):
        """Insert this snippet under `parent_key` of an existing Scene. Returns the new top node's path."""
        par = sc.find(parent_key)
        pk = sc.key(par)
        idmap, remap = self.merge_resources(sc)
        top = None
        for i, n in enumerate(self.nodes):
            if n["parent"] is None:
                parent = pk
            elif n["parent"] == ".":
                parent = top
            else:
                parent = (top + "/" + n["parent"]) if top else n["parent"]
            parent = parent if parent != "." or pk != "." else "."
            h = self._node_header(n, parent)
            if n["instance"]:
                h = h.replace('ExtResource("%s")' % n["instance"], 'ExtResource("%s")' % idmap[n["instance"]])
            key_parent = parent
            blk = {"kind": "node", "attrs": {"name": n["name"], "parent": key_parent, **({"type": n["type"]} if n["type"] else {})}, "header": h,
                   "body": [remap(l) for l in n["body"]] + [""]}
            if any(sc.key(b) == sc.key(blk) for b in sc.nodes()):
                raise ToolkitError("'%s' already has a child named '%s'" % (key_parent, n["name"]), "Pick another `name`.")
            parent_blk = sc.find(key_parent)
            sc.blocks.insert(sc._subtree_end(parent_blk), blk)
            if top is None:
                top = sc.key(blk)
        sc._pad()
        sc._steps()
        return top


# ───────────────────────── file output ─────────────────────────
class Out:
    def __init__(self, proj, args):
        self.p, self.args, self.recs, self.previews = proj, args, [], {}
        self.overwrite = boolean(args.get("overwrite"), False)

    def put(self, res_path, text, what="file", allow_overwrite=None):
        full = _abs(self.p, res_path)
        ow = self.overwrite if allow_overwrite is None else allow_overwrite
        if os.path.exists(full) and not ow:
            raise ToolkitError("%s already exists" % _res(self.p, full), "Pass overwrite=true or choose another name/path.")
        wrote = _write(full, text, self.args)
        self.recs.append({"path": _res(self.p, full), "kind": what, "bytes": len(text.encode("utf-8")), "written": wrote})
        if self.args.get("dry_run"):
            self.previews[_res(self.p, full)] = text[:2500]
        return _res(self.p, full)

    def done(self, **extra):
        d = dict(extra)
        d["files"] = self.recs
        if self.args.get("dry_run"):
            d["dryRun"] = True
            d["preview"] = self.previews
        return d


def norm_res(path, ext, default_dir="res://"):
    s = str(path or "").strip().replace("\\", "/")
    if not s.startswith("res://"):
        base = default_dir if default_dir.endswith("://") else default_dir.rstrip("/") + "/"
        s = base + s.lstrip("/")
    if not s.endswith(ext):
        s += ext
    return s


def target_scene(p, args, sb, default_path, out, parent_key=None):
    """Save the snippet as a new scene, or merge it into `into_scene`. Returns (res_path, top_node_path)."""
    into = args.get("into_scene")
    if into:
        full = _abs(p, norm_res(into, ".tscn"))
        if not os.path.isfile(full):
            raise ToolkitError("scene not found: %s" % into)
        sc = Scene(_read(full))
        top = sb.merge_into(sc, str(args.get("parent") or parent_key or "."))
        text = sc.text().rstrip("\n") + "\n"
        out.put(_res(p, full), text, "scene (merged)", allow_overwrite=True)
        return _res(p, full), top
    path = norm_res(args.get("scene_path") or default_path, ".tscn", "res://scenes")
    out.put(path, sb.render(), "scene")
    return path, "."


# ───────────────────────── headless Godot ─────────────────────────
def godot_run(proj, script_text, timeout=60, extra=()):
    exe = find_exe()
    if not exe:
        raise ToolkitError("no Godot executable found", "Set GODOT_PATH to your Godot 4 binary (or install godot in PATH).")
    d = tempfile.mkdtemp(prefix="ms_gd_")
    try:
        sp = os.path.join(d, "ms_task.gd")
        with open(sp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(script_text)
        try:
            r = subprocess.run([exe, "--headless", "--path", proj, "--script", sp] + list(extra), capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
            return r.returncode, r.stdout or "", r.stderr or "", False
        except subprocess.TimeoutExpired as e:
            return -9, (e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")), (e.stderr.decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")), True
    finally:
        shutil.rmtree(d, ignore_errors=True)


_RUN_WRAP = '''extends SceneTree
# Generated by Multi-Script (ms_godot_run_gdscript). Runs once, headless, then quits.
var R := {}
@@HELPERS@@
func _init():
	_ms_main()
	print("MS_RESULT:" + JSON.stringify(R))
	quit(0)

func _ms_main():
@@BODY@@
'''


def indent(code, n=1):
    pad = "\t" * n
    lines = str(code).replace("\r\n", "\n").split("\n")
    return "\n".join((pad + ln) if ln.strip() else ln for ln in lines) or (pad + "pass")


def parse_gd_marker(text):
    last = None
    for ln in str(text).splitlines():
        if ln.startswith("MS_RESULT:"):
            try:
                last = json.loads(ln[len("MS_RESULT:"):])
            except Exception:
                pass
    return last


@tool(G, "ms_godot_run_gdscript",
      "Run GDScript statements headless inside your project and get back the `R` dictionary (e.g. R[\"nodes\"] = n). The code runs in a SceneTree script, so you can load scenes, "
      "instantiate them, call methods, inspect resources or batch-edit assets, then it quits. Use `lines`/`code` for the body and `helpers` for extra functions.",
      {"code": {"type": "string", "description": "GDScript statements (indented with tabs automatically)."}, "lines": {"type": "array", "items": {"type": "string"}},
       "helpers": {"type": "string", "description": "Extra func/var declarations placed before _init."}, "timeout_seconds": {"type": "integer"}},
      [], writes=True, local=True)
def run_gdscript(args, ctx):
    proj = _proj(args, ctx)
    code = "\n".join(str(x) for x in as_list(args.get("lines"))) if args.get("lines") else str(args.get("code") or "")
    if not code.strip():
        raise ToolkitError("give `code` or `lines`")
    script = fill(_RUN_WRAP, HELPERS=str(args.get("helpers") or ""), BODY=indent(code))
    if args.get("dry_run"):
        return {"dryRun": True, "code": script}
    rc, so, se, timed = godot_run(proj, script, num(args.get("timeout_seconds"), 60, 5, 600, True))
    res = parse_gd_marker(so)
    out_lines = [ln for ln in so.splitlines() if not ln.startswith("MS_RESULT:") and not ln.startswith("Godot Engine v") and ln.strip()]
    errs = [ln for ln in (so + "\n" + se).splitlines() if re.search(r"SCRIPT ERROR|Parse Error|ERROR:", ln) and not re.search(r"leaked at exit|still in use at exit|ObjectDB instances leaked|Pages in use exist at exit|RID allocations|resources still in use", ln)]
    ok = res is not None and not timed and not errs
    out = {"ok": ok, "result": res, "output": out_lines[-40:]}
    if errs:
        out["errors"] = errs[:15]
    if timed:
        out["error"] = "timed out - the script probably waits for something; scripts must finish on their own"
    elif res is None and not errs:
        out["error"] = "the script produced no result line (parse error?)"
        out["stderr"] = se[-800:]
    return out


# ───────────────────────── environment ─────────────────────────
ENV_PRESETS = {
    # sky_top, sky_horizon, ground, sun_color, sun_energy, ambient_energy, fog (None or (color, density)), tonemap, glow, saturation, default_hour
    "day": ("#3d7bd9", "#bcd9f0", "#8a8f94", "#fff4e0", 1.1, 1.0, None, 3, 0.15, 1.05, 12),
    "sunset": ("#2f3a6b", "#ff9a5a", "#3b2f3a", "#ffb070", 1.0, 0.8, ("#ff9a6a", 0.004), 3, 0.35, 1.15, 18.4),
    "night": ("#05060f", "#16213d", "#0a0a0f", "#a8c0ff", 0.25, 0.35, None, 3, 0.4, 0.95, 1),
    "foggy": ("#8a96a3", "#c5ccd2", "#7d8388", "#dfe4e8", 0.6, 1.0, ("#c5ccd2", 0.03), 3, 0.1, 0.85, 9),
    "overcast": ("#7f8c99", "#b8c1ca", "#77797c", "#d8dde2", 0.5, 1.1, ("#b8c1ca", 0.006), 3, 0.05, 0.8, 13),
    "space": ("#000005", "#05051a", "#000000", "#ffffff", 1.6, 0.15, None, 3, 0.8, 1.1, 12),
    "cartoon": ("#4aa8ff", "#d6f0ff", "#a8d672", "#fff9e0", 1.2, 1.2, None, 1, 0.25, 1.3, 12),
    "horror": ("#0b0d10", "#1a1f1c", "#050505", "#7a8a80", 0.2, 0.2, ("#101614", 0.05), 3, 0.2, 0.6, 23),
    "desert": ("#4f8fd9", "#f2d9a8", "#c9a66b", "#fff0c8", 1.4, 1.1, ("#f2d9a8", 0.002), 3, 0.2, 1.1, 14),
    "underwater": ("#0a5a88", "#2aa0c0", "#07324a", "#9fe0ff", 0.7, 1.0, ("#1a7fa0", 0.06), 3, 0.3, 1.0, 12),
}


@tool(G, "ms_godot_environment",
      "Add a ready-made 3D (or 2D) lighting setup: WorldEnvironment with procedural sky, ambient, tonemap, glow, fog, SSAO and a shadowed DirectionalLight3D whose angle follows `hour`. "
      "Presets: day, sunset, night, foggy, overcast, space, cartoon, horror, desert, underwater. Creates a scene or merges into an existing one.",
      {"preset": {"type": "string", "enum": sorted(ENV_PRESETS)}, "hour": {"type": "number", "description": "0-24; moves the sun."}, "mode": {"type": "string", "enum": ["3d", "2d"]},
       "scene_path": SCENE, "into_scene": INTO, "parent": PARENT, "compatibility_renderer": {"type": "boolean", "description": "Skip SSAO/volumetric fog (not supported by the Compatibility renderer)."},
       "fog_density": {"type": "number"}, "shadows": {"type": "boolean"}, "overwrite": OVERWRITE}, ["preset"], writes=True, local=True)
def environment(args, ctx):
    p = _proj(args, ctx)
    name = str(args.get("preset") or "").lower()
    if name not in ENV_PRESETS:
        raise ToolkitError("unknown preset '%s'" % name, "Presets: " + ", ".join(sorted(ENV_PRESETS)))
    top, hor, gnd, sun, sun_e, amb, fog, tone, glow, sat, hour0 = ENV_PRESETS[name]
    hour = num(args.get("hour"), hour0, 0, 24)
    mode = str(args.get("mode") or "3d").lower()
    compat = boolean(args.get("compatibility_renderer"), False)
    sb = SB("MS_Environment_" + name, "Node3D" if mode == "3d" else "Node2D", "env" + name)
    envp = {"glow_enabled": "true", "glow_intensity": f(glow * 2), "glow_bloom": f(glow * 0.3), "tonemap_mode": str(tone), "adjustment_enabled": "true", "adjustment_saturation": f(sat)}
    if mode == "2d":
        envp.update({"background_mode": "3"})
        env = sb.sub("Environment", envp, hint="Environment")
        sb.node("WorldEnvironment", "WorldEnvironment", ".", {"environment": 'SubResource("%s")' % env})
        dark = 1.0 if name in ("day", "cartoon", "desert") else (0.55 if name in ("sunset", "overcast", "foggy") else 0.3)
        sb.node("CanvasModulate", "CanvasModulate", ".", {"color": Cx(tuple(lerp_col("#ffffff", sun, 0.5 if dark < 1 else 0.25)[:3]) + (1.0,))})
    else:
        psm = sb.sub("ProceduralSkyMaterial", {"sky_top_color": C(top), "sky_horizon_color": C(hor), "ground_horizon_color": C(hor), "ground_bottom_color": C(gnd),
                                                 "sky_energy_multiplier": f(0.3 if name == "night" else 1.0), "sun_angle_max": "30.0"}, hint="ProceduralSkyMaterial")
        sky = sb.sub("Sky", {"sky_material": 'SubResource("%s")' % psm}, hint="Sky")
        envp.update({"background_mode": "2", "sky": 'SubResource("%s")' % sky, "ambient_light_source": "3", "ambient_light_energy": f(amb), "reflected_light_source": "2"})
        if name == "space":
            envp["background_mode"] = "1"
            envp["background_color"] = C("#000004")
            envp["ambient_light_source"] = "2"
            envp["ambient_light_color"] = C("#202840")
        fd = num(args.get("fog_density"), fog[1] if fog else 0.0, 0, 1)
        if fd > 0:
            envp.update({"fog_enabled": "true", "fog_light_color": C(fog[0] if fog else hor), "fog_density": f(fd), "fog_sky_affect": "0.6"})
        if not compat:
            envp.update({"ssao_enabled": "true", "ssao_intensity": "1.6"})
            if name in ("horror", "foggy", "underwater"):
                envp.update({"volumetric_fog_enabled": "true", "volumetric_fog_density": f(max(0.005, fd * 0.4)), "volumetric_fog_albedo": C(fog[0] if fog else hor)})
        env = sb.sub("Environment", envp, hint="Environment")
        sb.node("WorldEnvironment", "WorldEnvironment", ".", {"environment": 'SubResource("%s")' % env})
        elev = math.sin((hour - 6.0) / 12.0 * math.pi)  # 1 at noon, <0 at night
        elev_deg = max(-10.0, elev * 80.0 + 5.0 if elev > 0 else elev * 20.0)
        azim = (hour / 24.0) * 360.0 - 90.0
        warm = max(0.0, 1.0 - abs(elev))
        sc = lerp_col(sun, "#ff8f4a", min(1.0, warm * 0.6)) if elev > 0 else hex_rgba(sun)
        sb.node("Sun", "DirectionalLight3D", ".", {"rotation": V3(round(-math.radians(max(elev_deg, 2.0)), 4), round(math.radians(azim), 4), 0),
                                                     "light_color": Cx(sc), "light_energy": f(sun_e * (max(0.05, elev) if elev > 0 else 0.15)),
                                                     "shadow_enabled": "true" if boolean(args.get("shadows"), True) else "false", "directional_shadow_mode": "2", "directional_shadow_max_distance": "120.0"})
    out = Out(p, args)
    path, top_key = target_scene(p, args, sb, "MS_Environment_%s.tscn" % name, out)
    return out.done(scene=path, node=top_key, preset=name, mode=mode, hour=hour if mode == "3d" else None,
                    hint="Instance this scene in your level or use into_scene. Only one WorldEnvironment should be active per scene.")


# ───────────────────────── audio buses ─────────────────────────
AUDIO_EFFECTS = {
    "reverb": ("AudioEffectReverb", {"room_size": "0.6", "damping": "0.5", "wet": "0.25"}),
    "cave_reverb": ("AudioEffectReverb", {"room_size": "0.95", "damping": "0.3", "wet": "0.45", "predelay_msec": "80.0"}),
    "compressor": ("AudioEffectCompressor", {"threshold": "-14.0", "ratio": "3.0", "attack_us": "20.0", "release_ms": "250.0"}),
    "limiter": ("AudioEffectLimiter", {"ceiling_db": "-0.5", "threshold_db": "-3.0"}),
    "lowpass": ("AudioEffectLowPassFilter", {"cutoff_hz": "1800.0"}),
    "highpass": ("AudioEffectHighPassFilter", {"cutoff_hz": "250.0"}),
    "delay": ("AudioEffectDelay", {"dry": "0.8", "tap1_active": "true", "tap1_delay_ms": "250.0", "tap1_level_db": "-6.0"}),
    "chorus": ("AudioEffectChorus", {"dry": "0.8", "wet": "0.3"}),
    "eq": ("AudioEffectEQ6", {}),
    "distortion": ("AudioEffectDistortion", {"drive": "0.3"}),
    "phaser": ("AudioEffectPhaser", {"depth": "1.0"}),
    "amplify": ("AudioEffectAmplify", {"volume_db": "3.0"}),
}
BUS_PRESETS = {
    "standard": [("Music", -6.0, ["limiter"]), ("SFX", 0.0, ["compressor"]), ("UI", -4.0, []), ("Ambience", -8.0, []), ("Voice", 0.0, ["compressor"])],
    "cinematic": [("Music", -4.0, ["reverb", "limiter"]), ("SFX", 0.0, ["compressor"]), ("Ambience", -6.0, ["reverb"]), ("Voice", 0.0, ["compressor", "highpass"]), ("UI", -6.0, [])],
    "retro": [("Music", -5.0, ["lowpass"]), ("SFX", -2.0, ["distortion"]), ("UI", -4.0, [])],
    "minimal": [("Music", -6.0, []), ("SFX", 0.0, [])],
}
_AUDIO_MANAGER = '''extends Node
## Autoload helper for the bus layout made by Multi-Script. Register it as "Audio" (Project Settings > Autoload).
## Audio.play_sfx(stream), Audio.play_music(stream), Audio.set_volume("Music", 0.5), Audio.mute("SFX", true)

var _music: AudioStreamPlayer
var _pool: Array[AudioStreamPlayer] = []

func _ready() -> void:
\t_music = AudioStreamPlayer.new()
\t_music.bus = "Music"
\tadd_child(_music)
\tfor i in 8:
\t\tvar p := AudioStreamPlayer.new()
\t\tp.bus = "SFX"
\t\tadd_child(p)
\t\t_pool.append(p)

func play_sfx(stream: AudioStream, volume_db: float = 0.0, pitch_variation: float = 0.05, bus: String = "SFX") -> void:
\tfor p in _pool:
\t\tif not p.playing:
\t\t\tp.stream = stream
\t\t\tp.bus = bus
\t\t\tp.volume_db = volume_db
\t\t\tp.pitch_scale = 1.0 + randf_range(-pitch_variation, pitch_variation)
\t\t\tp.play()
\t\t\treturn

func play_music(stream: AudioStream, fade_seconds: float = 1.0) -> void:
\tif _music.stream == stream and _music.playing:
\t\treturn
\tvar tw := create_tween()
\tif _music.playing:
\t\ttw.tween_property(_music, "volume_db", -40.0, fade_seconds * 0.5)
\t\ttw.tween_callback(func(): _swap(stream))
\telse:
\t\t_swap(stream)
\ttw.tween_property(_music, "volume_db", 0.0, fade_seconds * 0.5)

func _swap(stream: AudioStream) -> void:
\t_music.stream = stream
\t_music.play()

func set_volume(bus: String, linear: float) -> void:
\tvar i := AudioServer.get_bus_index(bus)
\tif i >= 0:
\t\tAudioServer.set_bus_volume_db(i, linear_to_db(clampf(linear, 0.0, 1.0)))

func get_volume(bus: String) -> float:
\tvar i := AudioServer.get_bus_index(bus)
\treturn db_to_linear(AudioServer.get_bus_volume_db(i)) if i >= 0 else 0.0

func mute(bus: String, muted: bool) -> void:
\tvar i := AudioServer.get_bus_index(bus)
\tif i >= 0:
\t\tAudioServer.set_bus_mute(i, muted)
'''


@tool(G, "ms_godot_audio_bus_layout",
      "Create default_bus_layout.tres with named buses, volumes and effects (preset standard / cinematic / retro / minimal, or your own `buses` [{name, volume_db, effects:[reverb, cave_reverb, compressor, limiter, lowpass, highpass, "
      "delay, chorus, eq, distortion, phaser, amplify]}]), register it in project.godot and optionally write an Audio autoload helper (play_sfx, play_music, set_volume).",
      {"preset": {"type": "string", "enum": sorted(BUS_PRESETS)}, "buses": {"type": "array", "items": {"type": "object"}}, "path": {"type": "string"},
       "register": {"type": "boolean", "description": "Set audio/buses/default_bus_layout in project.godot (default true)."}, "manager_script": {"type": "boolean"}, "overwrite": OVERWRITE}, [], writes=True, local=True)
def audio_bus_layout(args, ctx):
    p = _proj(args, ctx)
    buses = []
    for b in as_list(args.get("buses")):
        b = as_dict(b)
        if not b.get("name"):
            raise ToolkitError("every bus needs a name")
        buses.append((str(b["name"]), num(b.get("volume_db"), 0, -80, 24), [str(x).lower() for x in as_list(b.get("effects"))]))
    if not buses:
        preset = str(args.get("preset") or "standard").lower()
        if preset not in BUS_PRESETS:
            raise ToolkitError("unknown preset '%s'" % preset, "Presets: " + ", ".join(sorted(BUS_PRESETS)))
        buses = BUS_PRESETS[preset]
    subs, lines = [], []
    n_sub = 0
    for i, (bname, vol, effs) in enumerate(buses, start=1):
        lines += ['bus/%d/name = &"%s"' % (i, re.sub(r'[^\w .-]', "", bname)), "bus/%d/solo = false" % i, "bus/%d/mute = false" % i, "bus/%d/bypass_fx = false" % i,
                  "bus/%d/volume_db = %s" % (i, f(vol)), 'bus/%d/send = &"Master"' % i]
        for k, e in enumerate(effs):
            if e not in AUDIO_EFFECTS:
                raise ToolkitError("unknown effect '%s'" % e, "Effects: " + ", ".join(sorted(AUDIO_EFFECTS)))
            n_sub += 1
            sid = "%s_%s" % (AUDIO_EFFECTS[e][0], hashlib.md5(("%d%s%d" % (i, e, k)).encode()).hexdigest()[:5])
            subs.append((AUDIO_EFFECTS[e][0], sid, AUDIO_EFFECTS[e][1]))
            lines += ['bus/%d/effect/%d/effect = SubResource("%s")' % (i, k, sid), "bus/%d/effect/%d/enabled = true" % (i, k)]
    text = ["[gd_resource type=\"AudioBusLayout\" load_steps=%d format=3]" % (len(subs) + 1), ""]
    for typ, sid, pr in subs:
        text.append('[sub_resource type="%s" id="%s"]' % (typ, sid))
        text += ["%s = %s" % (k, v) for k, v in pr.items()]
        text.append("")
    text += ["[resource]"] + lines
    out = Out(p, args)
    path = out.put(norm_res(args.get("path") or "default_bus_layout.tres", ".tres"), "\n".join(text) + "\n", "AudioBusLayout")
    registered = False
    if boolean(args.get("register"), True):
        pj = os.path.join(p, "project.godot")
        t = _read(pj)
        new = set_setting(t, "audio", "buses/default_bus_layout", '"%s"' % path)
        registered = _write(pj, new, args) if new != t else False
    if boolean(args.get("manager_script"), False):
        out.put("res://autoload/audio.gd", _AUDIO_MANAGER, "GDScript")
    return out.done(layout=path, buses=[b[0] for b in buses], registered=registered, effects=len(subs),
                    hint="Add the Audio helper as an autoload named Audio (ms_godot_autoload) to use Audio.play_sfx()." if args.get("manager_script") else "")


# ───────────────────────── export presets ─────────────────────────
EXPORT_TARGETS = {
    "windows": ("Windows Desktop", "build/windows/{name}.exe", {"binary_format/embed_pck": "true", "binary_format/architecture": '"x86_64"', "application/modify_resources": "true"}),
    "linux": ("Linux", "build/linux/{name}.x86_64", {"binary_format/embed_pck": "true", "binary_format/architecture": '"x86_64"'}),
    "macos": ("macOS", "build/macos/{name}.zip", {"binary_format/architecture": '"universal"', "application/bundle_identifier": '"com.example.{ident}"'}),
    "web": ("Web", "build/web/index.html", {"variant/thread_support": "false", "html/export_icon": "true", "html/canvas_resize_policy": "2"}),
    "android": ("Android", "build/android/{name}.apk", {"package/unique_name": '"com.example.{ident}"', "package/name": '"{name}"', "gradle_build/export_format": "0", "architectures/arm64-v8a": "true"}),
}


@tool(G, "ms_godot_export_presets",
      "Create or extend export_presets.cfg with ready export presets for windows, linux, macos, web and android (output paths under build/, embedded PCK, sensible options). Existing presets are kept; "
      "same-named ones are skipped unless overwrite=true. Export itself needs the Godot export templates installed.",
      {"platforms": {"type": "array", "items": {"type": "string", "enum": sorted(EXPORT_TARGETS)}}, "game_name": {"type": "string"}, "export_filter": {"type": "string", "enum": ["all_resources", "scenes", "selected_scenes"]},
       "exclude_filter": {"type": "string", "description": "e.g. docs/*, *.md"}, "overwrite": OVERWRITE}, [], writes=True, local=True)
def export_presets(args, ctx):
    p = _proj(args, ctx)
    plats = [str(x).lower() for x in as_list(args.get("platforms"))] or ["windows", "linux", "web"]
    for x in plats:
        if x not in EXPORT_TARGETS:
            raise ToolkitError("unknown platform '%s'" % x, "Platforms: " + ", ".join(sorted(EXPORT_TARGETS)))
    pj = _read(os.path.join(p, "project.godot"))
    gname = str(args.get("game_name") or get_setting(pj, "application/config/name") or os.path.basename(p) or "game").strip('"')
    safe = re.sub(r"[^\w.-]+", "_", gname) or "game"
    path = os.path.join(p, "export_presets.cfg")
    existing = _read(path) if os.path.isfile(path) else ""
    have = set(re.findall(r'^name="([^"]+)"', existing, re.M))
    blocks = re.split(r"(?m)^(?=\[preset\.\d+\]\s*$)", existing) if existing.strip() else []
    kept = [b for b in blocks if re.match(r"\[preset\.\d+\]\s*\n", b) and not b.startswith("[preset.%s.options" % "")]
    # keep existing text verbatim, append new presets after it
    next_idx = max([int(m) for m in re.findall(r"(?m)^\[preset\.(\d+)\]\s*$", existing)] + [-1]) + 1
    added, skipped = [], []
    new_text = existing.rstrip("\n") + ("\n\n" if existing.strip() else "")
    for plat in plats:
        pname, out_tpl, opts = EXPORT_TARGETS[plat]
        if pname in have and not boolean(args.get("overwrite"), False):
            skipped.append(pname)
            continue
        i = next_idx
        next_idx += 1
        body = ["[preset.%d]" % i, "", 'name="%s"' % pname, 'platform="%s"' % pname, "runnable=%s" % ("true" if plat in ("windows", "linux", "web") else "false"), "advanced_options=false", "dedicated_server=false",
                'custom_features=""', 'export_filter="%s"' % (args.get("export_filter") or "all_resources"), 'include_filter=""', 'exclude_filter="%s"' % str(args.get("exclude_filter") or "").replace('"', ""),
                'export_path="%s"' % out_tpl.format(name=safe), 'encryption_include_filters=""', 'encryption_exclude_filters=""', "encrypt_pck=false", "encrypt_directory=false", "script_export_mode=2", "",
                "[preset.%d.options]" % i, ""]
        for k, v in opts.items():
            body.append("%s=%s" % (k, v.format(name=gname, ident=safe.lower())))
        new_text += "\n".join(body) + "\n\n"
        added.append(pname)
    wrote = _write(path, new_text.rstrip("\n") + "\n", args) if added else False
    out = {"file": "res://export_presets.cfg", "added": added, "skipped_existing": skipped, "written": wrote,
           "hint": "Install export templates (Editor > Manage Export Templates), then: godot --headless --export-release \"<preset name>\"."}
    if args.get("dry_run"):
        out["dryRun"] = True
        out["preview"] = new_text[:2500]
    return out


# ───────────────────────── sprite sheets ─────────────────────────
def png_size(path):
    try:
        with open(path, "rb") as fh:
            head = fh.read(32)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", head[16:24])
    except OSError:
        pass
    return None


@tool(G, "ms_godot_sprite_animation",
      "Turn a sprite sheet into a SpriteFrames .tres (AtlasTexture frames) with named animations - {name, frames:[from,to] or a list, fps, loop} - using frame size or columns/rows (PNG size is read automatically). "
      "Optionally adds an AnimatedSprite2D with autoplay to a scene.",
      {"texture": {"type": "string", "description": "res://art/hero.png"}, "frame_size": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}, "columns": {"type": "integer"}, "rows": {"type": "integer"},
       "animations": {"type": "array", "items": {"type": "object"}}, "path": {"type": "string", "description": "Output .tres (default next to the texture)."}, "into_scene": INTO, "parent": PARENT,
       "node_name": {"type": "string"}, "autoplay": {"type": "string"}, "centered": {"type": "boolean"}, "position": {"type": "array", "items": {"type": "number"}}, "overwrite": OVERWRITE}, ["texture"], writes=True, local=True)
def sprite_animation(args, ctx):
    p = _proj(args, ctx)
    tex = norm_res(args.get("texture"), "")
    tfull = _abs(p, tex)
    if not os.path.isfile(tfull):
        raise ToolkitError("texture not found: %s" % tex)
    fs = [num(x, 0, 1, 16384) for x in as_list(args.get("frame_size"))]
    size = png_size(tfull)
    cols, rows = int(num(args.get("columns"), 0, 0, 512)), int(num(args.get("rows"), 0, 0, 512))
    if len(fs) == 2:
        fw, fh = fs
        if size:
            cols, rows = max(1, int(size[0] // fw)), max(1, int(size[1] // fh))
        elif not (cols and rows):
            raise ToolkitError("cannot read the image size: pass columns and rows as well")
    elif cols and rows and size:
        fw, fh = size[0] / cols, size[1] / rows
    else:
        raise ToolkitError("give `frame_size` [w,h] or `columns`+`rows` (PNG textures only for columns/rows)")
    total = cols * rows
    anims = [as_dict(a) for a in as_list(args.get("animations"))] or [{"name": "default", "frames": [0, total - 1], "fps": 8, "loop": True}]
    atlas, anim_txt, used = [], [], {}
    sub_lines = []
    for a in anims:
        fr = as_list(a.get("frames"))
        if len(fr) == 2 and all(isinstance(x, (int, float)) for x in fr) and a.get("range", True) and int(fr[1]) >= int(fr[0]):
            idxs = list(range(int(fr[0]), int(fr[1]) + 1))
        else:
            idxs = [int(x) for x in fr] or [0]
        idxs = [i for i in idxs if 0 <= i < total]
        if not idxs:
            raise ToolkitError("animation '%s' has no frames inside 0..%d" % (a.get("name"), total - 1))
        frames = []
        for i in idxs:
            if i not in used:
                sid = "AtlasTexture_%s" % hashlib.md5(("%s%d" % (tex, i)).encode()).hexdigest()[:5]
                used[i] = sid
                col, row = i % cols, i // cols
                sub_lines += ['[sub_resource type="AtlasTexture" id="%s"]' % sid, 'atlas = ExtResource("1_tex")', "region = Rect2(%s, %s, %s, %s)" % (f(col * fw), f(row * fh), f(fw), f(fh)), ""]
            frames.append('{\n"duration": 1.0,\n"texture": SubResource("%s")\n}' % used[i])
        anim_txt.append('{\n"frames": [%s],\n"loop": %s,\n"name": %s,\n"speed": %s\n}' % (", ".join(frames), "true" if boolean(a.get("loop"), True) else "false", SNAME(a.get("name") or "default"), f(num(a.get("fps"), 8, 0.1, 120))))
    text = ['[gd_resource type="SpriteFrames" load_steps=%d format=3]' % (len(used) + 2), "", '[ext_resource type="Texture2D" path="%s" id="1_tex"]' % tex, ""] + sub_lines + ["[resource]", "animations = [" + ", ".join(anim_txt) + "]"]
    out = Out(p, args)
    base = os.path.splitext(tex)[0] + "_frames.tres"
    path = out.put(norm_res(args.get("path") or base, ".tres"), "\n".join(text) + "\n", "SpriteFrames")
    node = None
    if args.get("into_scene"):
        sb = SB(str(args.get("node_name") or "AnimatedSprite2D"), "AnimatedSprite2D", "spr")
        sid = sb.ext_res(path, "SpriteFrames")
        root = sb.nodes[0]
        root["body"] += ['sprite_frames = ExtResource("%s")' % sid, "animation = %s" % SNAME(args.get("autoplay") or anims[0].get("name") or "default"), 'autoplay = "%s"' % (args.get("autoplay") or anims[0].get("name") or "default")]
        if len(as_list(args.get("position"))) == 2:
            root["body"].append("position = " + V2(*as_list(args.get("position"))))
        if not boolean(args.get("centered"), True):
            root["body"].append("centered = false")
        _scene, node = target_scene(p, args, sb, "unused.tscn", out)
    return out.done(sprite_frames=path, frame_size=[fw, fh], columns=cols, rows=rows, frames_total=total, animations=[a.get("name") or "default" for a in anims], node=node)


# ───────────────────────── animation ─────────────────────────
ANIM_PRESETS = ["bob", "sway", "spin", "pulse", "slide", "door_open", "flicker", "fade_in", "fade_out", "shake", "color_pulse", "pop_in", "float_spin", "custom"]
_CTRL_TYPES = {"Control", "Button", "Label", "Panel", "PanelContainer", "TextureRect", "ColorRect", "TextureButton", "RichTextLabel", "LineEdit", "ProgressBar", "TextureProgressBar", "NinePatchRect",
               "VBoxContainer", "HBoxContainer", "GridContainer", "MarginContainer", "CenterContainer", "ScrollContainer", "TabContainer", "CheckBox", "CheckButton", "HSlider", "VSlider", "OptionButton"}


def node_kind(ntype, override=None):
    if override in ("3d", "2d", "ui"):
        return override
    t = ntype or ""
    if t in _CTRL_TYPES or t.endswith("Container"):
        return "ui"
    if t.endswith("3D") or t.startswith("CSG") or t in ("Node3D", "Skeleton3D", "MeshInstance3D"):
        return "3d"
    return "2d"


def read_vec(block, key, n, default):
    for ln in block["body"]:
        m = re.match(r"^%s\s*=\s*Vector%d\(([^)]*)\)" % (key, n), ln)
        if m:
            try:
                v = [float(x) for x in m.group(1).split(",")]
                if len(v) == n:
                    return v
            except ValueError:
                pass
    if key == "position" and n == 3:
        for ln in block["body"]:
            m = re.match(r"^transform\s*=\s*Transform3D\(([^)]*)\)", ln)
            if m:
                v = [float(x) for x in m.group(1).split(",")]
                if len(v) == 12:
                    return v[9:12]
    return list(default)


class AnimBuilder:
    def __init__(self, kind, base_pos, base_scale, duration, amp, axis, loop):
        self.kind, self.pos, self.scale, self.d, self.amp, self.axis, self.loop = kind, base_pos, base_scale, duration, amp, axis, loop
        self.tracks = []

    def vec(self, v):
        return V3(*v) if self.kind == "3d" else V2(*v[:2])

    def track(self, path, times, values, interp=1, update=0, ttype="value", transitions=None):
        self.tracks.append({"type": ttype, "path": path, "times": times, "values": values, "interp": interp, "update": update, "transitions": transitions or [1.0] * len(times)})


def build_preset(name, kind, tpath, pos, scale, dur, amp, axis, color_a, color_b, light=False, seed=3):
    """Returns (tracks, loop_mode, note). Positions follow the engine's up axis: 3D y is up, 2D/UI y is down."""
    import random
    rnd = random.Random(seed)
    up = 1.0 if kind == "3d" else -1.0
    ax = {"x": 0, "y": 1, "z": 2}.get(axis, 1)
    B = AnimBuilder(kind, pos, scale, dur, amp, axis, True)
    P = lambda p: "%s:%s" % (tpath, p)
    def offs(delta):
        v = list(pos) + [0.0] * (3 - len(pos))
        v = v[:3] if kind == "3d" else v[:2]
        v[min(ax, len(v) - 1)] += delta
        return v
    loop = 1
    def rot_val(deg_axis):
        # rotation property: float (radians) for 2D/UI, Vector3 for 3D
        if kind == "3d":
            v = [0.0, 0.0, 0.0]
            v[deg_axis] = 1.0
            return v
        return None
    def rot_values(angles_deg, a3=1):
        if kind == "3d":
            out = []
            for a in angles_deg:
                v = [0.0, 0.0, 0.0]
                v[a3] = math.radians(a)
                out.append(V3(*[round(x, 5) for x in v]))
            return out
        return [f(round(math.radians(a), 5)) for a in angles_deg]
    if name == "bob":
        a = amp * (0.3 if kind == "3d" else 12.0)
        B.track(P("position"), [0, dur / 2, dur], [B.vec(offs(0) if ax != 1 else offs(0)), B.vec(_shift(pos, 1, up * a, kind)), B.vec(offs(0))], interp=2)
    elif name == "sway":
        a = amp * 12.0
        B.track(P("rotation"), [0, dur / 4, dur * 3 / 4, dur], rot_values([0, a, -a, 0], 2), interp=2)
    elif name == "spin":
        B.track(P("rotation"), [0, dur], rot_values([0, 360], 1 if kind == "3d" else 0), interp=1)
    elif name == "pulse":
        s = amp * 0.15
        B.track(P("scale"), [0, dur / 2, dur], [B.vec([x for x in scale]), B.vec([x * (1 + s) for x in scale]), B.vec([x for x in scale])], interp=2)
    elif name == "slide":
        dist = amp * (2.0 if kind == "3d" else 100.0)
        B.track(P("position"), [0, dur / 2, dur], [B.vec(_shift(pos, 0, 0, kind)), B.vec(_shift(pos, ax if ax != 1 else 0, dist, kind)), B.vec(_shift(pos, 0, 0, kind))], interp=2)
    elif name == "door_open":
        loop = 0
        B.track(P("rotation"), [0, dur], rot_values([0, 90 * amp], 1 if kind == "3d" else 0), interp=2)
    elif name == "flicker":
        times = [round(i * dur / 12.0, 4) for i in range(13)]
        if light:
            vals = [f(round(0.6 + rnd.random() * 0.8, 3)) for _ in times]
            vals[-1] = vals[0]
            B.track(P("light_energy"), times, vals, interp=1)
        else:
            vals = [f(round(0.55 + rnd.random() * 0.45, 3)) for _ in times]
            vals[-1] = vals[0]
            B.track(P("modulate:a"), times, vals, interp=1)
    elif name in ("fade_in", "fade_out"):
        loop = 0
        a0, a1 = (0.0, 1.0) if name == "fade_in" else (1.0, 0.0)
        if kind == "3d":
            B.track(P("transparency"), [0, dur], [f(1 - a0), f(1 - a1)], interp=1)
        else:
            B.track(P("modulate:a"), [0, dur], [f(a0), f(a1)], interp=1)
    elif name == "shake":
        loop = 0
        n = 10
        times = [round(i * dur / n, 4) for i in range(n + 1)]
        vals = []
        for i, _ in enumerate(times):
            fall = 1 - i / n
            dx, dy = (rnd.random() - 0.5) * 2 * amp * fall, (rnd.random() - 0.5) * 2 * amp * fall
            vals.append(B.vec(_shift2(pos, dx * (0.2 if kind == "3d" else 12), dy * (0.2 if kind == "3d" else 12), kind) if i < n else pos))
        B.track(P("position"), times, vals, interp=1)
    elif name == "color_pulse":
        prop = "light_color" if light else "modulate"
        B.track(P(prop), [0, dur / 2, dur], [C(color_a, "#ffffff"), C(color_b, "#ff5533"), C(color_a, "#ffffff")], interp=1)
    elif name == "pop_in":
        loop = 0
        B.track(P("scale"), [0, dur * 0.6, dur], [B.vec([0.001] * len(scale)), B.vec([x * 1.2 for x in scale]), B.vec(list(scale))], interp=2)
    elif name == "float_spin":
        a = amp * (0.3 if kind == "3d" else 12.0)
        B.track(P("position"), [0, dur / 2, dur], [B.vec(_shift(pos, 1, 0, kind)), B.vec(_shift(pos, 1, up * a, kind)), B.vec(_shift(pos, 1, 0, kind))], interp=2)
        B.track(P("rotation"), [0, dur], rot_values([0, 360], 1 if kind == "3d" else 0), interp=1)
    else:
        raise ToolkitError("unknown preset '%s'" % name)
    return B.tracks, loop


def _shift(pos, idx, delta, kind):
    v = list(pos) + [0.0] * 3
    v = v[:3] if kind == "3d" else v[:2]
    idx = min(idx, len(v) - 1)
    v[idx] += delta
    return v


def _shift2(pos, dx, dy, kind):
    v = list(pos) + [0.0] * 3
    v = v[:3] if kind == "3d" else v[:2]
    v[0] += dx
    v[1] += dy
    return v


def anim_sub_lines(name, length, loop_mode, tracks):
    lines = ['resource_name = "%s"' % name, "length = %s" % f(length), "loop_mode = %d" % loop_mode, 'step = 0.05']
    for i, t in enumerate(tracks):
        pre = "tracks/%d/" % i
        lines += ['%stype = "%s"' % (pre, t["type"]), pre + "imported = false", pre + "enabled = true", '%spath = NodePath("%s")' % (pre, t["path"]), "%sinterp = %d" % (pre, t["interp"]), pre + "loop_wrap = true"]
        if t["type"] == "value":
            lines.append('%skeys = {\n"times": %s,\n"transitions": %s,\n"update": %d,\n"values": [%s]\n}' % (pre, PF32(t["times"]), PF32(t["transitions"]), t["update"], ", ".join(t["values"])))
        else:
            lines.append('%skeys = {\n"times": %s,\n"transitions": %s,\n"values": [%s]\n}' % (pre, PF32(t["times"]), PF32(t["transitions"]), ", ".join(t["values"])))
    return lines


def custom_tracks(specs, tpath):
    from toolkit_godot import lit
    out = []
    for sp in specs:
        sp = as_dict(sp)
        path = str(sp.get("path") or "")
        if not path:
            raise ToolkitError("every custom track needs a `path` like 'Sprite2D:position'")
        if ":" not in path and (sp.get("type") or "value") == "value":
            path = "%s:%s" % (tpath, path)
        ttype = str(sp.get("type") or "value").lower()
        keys = as_list(sp.get("keys"))
        if not keys:
            raise ToolkitError("track '%s' has no keys" % path)
        if ttype == "method":
            times, vals = [], []
            for k in keys:
                k = as_dict(k)
                times.append(num(k.get("time"), 0, 0, 3600))
                vals.append('{\n"args": [%s],\n"method": %s\n}' % (", ".join(lit(x) for x in as_list(k.get("args"))), SNAME(k.get("method") or "queue_free")))
            out.append({"type": "method", "path": path if ":" not in path else path.split(":")[0], "times": times, "values": vals, "interp": 1, "update": 0, "transitions": [1.0] * len(times)})
            continue
        times = [num(k[0] if isinstance(k, (list, tuple)) else as_dict(k).get("time"), 0, 0, 3600) for k in keys]
        vals = [lit(k[1] if isinstance(k, (list, tuple)) else as_dict(k).get("value"), path.split(":")[-1]) for k in keys]
        interp = {"nearest": 0, "linear": 1, "cubic": 2}.get(str(sp.get("interp") or "linear").lower(), 1)
        out.append({"type": "value", "path": path, "times": times, "values": vals, "interp": interp, "update": 1 if sp.get("discrete") else 0, "transitions": [1.0] * len(times)})
    return out


@tool(G, "ms_godot_animation_create",
      "Add an animation to a node in an existing .tscn: presets bob, sway, spin, pulse, slide, door_open, flicker, fade_in, fade_out, shake, color_pulse, pop_in, float_spin (2D, 3D and UI aware) or custom tracks "
      "(value / method, keys [[time, value]], interp). Reuses the scene's AnimationPlayer or creates one, sets loop mode and optional autoplay.",
      {"scene_path": SCENE, "target": {"type": "string", "description": "Node path inside the scene to animate ('.' = root)."}, "preset": {"type": "string", "enum": ANIM_PRESETS},
       "name": {"type": "string", "description": "Animation name (default = preset)."}, "duration": {"type": "number"}, "amplitude": {"type": "number"}, "axis": {"type": "string", "enum": ["x", "y", "z"]},
       "loop": {"type": "boolean"}, "tracks": {"type": "array", "items": {"type": "object"}, "description": "[{path:'Mesh:position', keys:[[0,[0,0,0]],[1,[0,2,0]]], interp:'cubic'}, {type:'method', path:'.', keys:[{time:1, method:'queue_free'}]}]"},
       "player_name": {"type": "string"}, "autoplay": {"type": "boolean"}, "color_a": {"type": ["string", "array"]}, "color_b": {"type": ["string", "array"]}, "kind": {"type": "string", "enum": ["3d", "2d", "ui"]},
       "overwrite": OVERWRITE}, ["scene_path"], writes=True, local=True)
def animation_create(args, ctx):
    p = _proj(args, ctx)
    full = _abs(p, norm_res(args.get("scene_path"), ".tscn"))
    if not os.path.isfile(full):
        raise ToolkitError("scene not found: %s" % args.get("scene_path"), "Create it first with ms_godot_scene_create.")
    sc = Scene(_read(full))
    target = str(args.get("target") or ".")
    tb = sc.find(target)
    tkey = sc.key(tb)
    ntype = tb["attrs"].get("type")
    kind = node_kind(ntype, args.get("kind"))
    preset = str(args.get("preset") or ("custom" if args.get("tracks") else "bob")).lower()
    if preset not in ANIM_PRESETS:
        raise ToolkitError("unknown preset '%s'" % preset, "Presets: " + ", ".join(ANIM_PRESETS))
    name = ident(args.get("name") or preset)
    dur = num(args.get("duration"), 1.0, 0.05, 600)
    amp = num(args.get("amplitude"), 1.0, 0.01, 1000)
    axis = str(args.get("axis") or "").lower() or ("y" if preset in ("bob",) else "x" if preset == "slide" else "y")
    pos = read_vec(tb, "position", 3 if kind == "3d" else 2, [0, 0, 0] if kind == "3d" else [0, 0])
    scl = read_vec(tb, "scale", 3 if kind == "3d" else 2, [1, 1, 1] if kind == "3d" else [1, 1])
    tpath = "." if tkey == "." else tkey
    is_light = (ntype or "").endswith("Light3D") or (ntype or "").endswith("Light2D")
    loop = boolean(args.get("loop"), preset in ("bob", "sway", "spin", "pulse", "slide", "flicker", "color_pulse", "float_spin"))
    if preset == "custom":
        tracks = custom_tracks(as_list(args.get("tracks")), tpath)
        loop_mode = 1 if loop else 0
        length = max([max(t["times"]) for t in tracks] + [dur])
    else:
        tracks, default_loop = build_preset(preset, kind, tpath, pos, scl, dur, amp, axis, args.get("color_a"), args.get("color_b"), light=is_light)
        loop_mode = 1 if (loop and default_loop) else 0
        length = dur
        if args.get("tracks"):
            tracks += custom_tracks(as_list(args.get("tracks")), tpath)
    if not tracks:
        raise ToolkitError("nothing to animate")
    pname = str(args.get("player_name") or "AnimationPlayer")
    sb = SB("tmp", "Node", "anim_" + name)
    asub = sb.sub("Animation", lines=anim_sub_lines(name, length, loop_mode, tracks), hint="Animation")
    existing = next((b for b in sc.nodes() if b["attrs"].get("name") == pname and b["attrs"].get("type") == "AnimationPlayer"), None)
    created_player = False
    if existing is not None:
        lib_id = None
        for ln in existing["body"]:
            m = re.search(r'"": SubResource\("([^"]+)"\)', ln)
            if m:
                lib_id = m.group(1)
        lib = next((b for b in sc.of("sub_resource") if b["attrs"].get("id") == lib_id), None) if lib_id else None
        idmap, remap = sb.merge_resources(sc, before=lib)
        new_id = idmap[asub]
        if lib is None:
            lsub = SB("tmp2", "Node", "lib_" + name)
            lid = lsub.sub("AnimationLibrary", {"_data": '{\n%s: SubResource("%s")\n}' % (SNAME(name), new_id)}, hint="AnimationLibrary")
            lmap, _ = lsub.merge_resources(sc)
            set_raw(sc, existing, "libraries", '{\n"": SubResource("%s")\n}' % lmap[lid])
        else:
            body = lib["body"]
            if any(("&\"%s\":" % name) in ln for ln in body) and not boolean(args.get("overwrite"), False):
                raise ToolkitError("animation '%s' already exists in %s" % (name, pname), "Pass overwrite=true or choose another name.")
            body[:] = [ln for ln in body if ("&\"%s\":" % name) not in ln]
            close = max(i for i, ln in enumerate(body) if ln.strip() == "}")
            prev = max(i for i in range(close) if body[i].strip())
            if body[prev].strip() not in ("{", "_data = {") and not body[prev].rstrip().endswith(","):
                body[prev] = body[prev].rstrip() + ","
            body.insert(close, '%s: SubResource("%s")' % (SNAME(name), new_id))
    else:
        created_player = True
        lib_sub = sb.sub("AnimationLibrary", {"_data": '{\n%s: SubResource("%s")\n}' % (SNAME(name), asub)}, hint="AnimationLibrary")
        props = {"libraries": '{\n"": SubResource("%s")\n}' % lib_sub}
        if boolean(args.get("autoplay"), False):
            props["autoplay"] = gstr(name)
        sb.node(pname, "AnimationPlayer", None, props)
        # attach the player to the scene root
        sb.nodes[-1]["parent"] = None
        # first node placeholder "tmp" is dropped; only the player is merged
        sb.nodes = [sb.nodes[-1]]
        sb.merge_into(sc, ".")
    if existing is not None and boolean(args.get("autoplay"), False):
        set_raw(sc, existing, "autoplay", gstr(name))
    out = Out(p, args)
    out.put(_res(p, full), sc.text().rstrip("\n") + "\n", "scene (animation added)", allow_overwrite=True)
    return out.done(scene=_res(p, full), animation=name, player=pname, created_player=created_player, kind=kind, tracks=len(tracks), length=length, loop=bool(loop_mode),
                    play="$%s.play(\"%s\")" % (pname, name))


# ───────────────────────── particles ─────────────────────────
# amount, lifetime, one_shot, explosiveness, shape, shape_size, direction, spread, vel(min,max), gravity, scale(min,max), scale_curve, colors, additive, damping, turbulence, hue, size, light
FX = {
    "fire": dict(amount=40, lifetime=1.1, shape=("sphere", 0.15), direction=(0, 1, 0), spread=12, vel=(0.8, 1.6), gravity=(0, 0.6, 0), scale=(0.5, 1.0), curve="shrink", additive=True, size=0.7,
                 colors=[(0, "#fff2a0ff"), (0.35, "#ff8a1fe0"), (0.75, "#d62a0f80"), (1, "#30101000")], light="#ff8a30"),
    "smoke": dict(amount=24, lifetime=3.5, shape=("sphere", 0.2), direction=(0, 1, 0), spread=18, vel=(0.4, 0.9), gravity=(0.15, 0.2, 0), scale=(0.8, 1.6), curve="grow", additive=False, size=1.2,
                  colors=[(0, "#55555500"), (0.2, "#6a6a6a90"), (1, "#8a8a8a00")], turbulence=0.35),
    "sparks": dict(amount=36, lifetime=0.8, shape=("point", 0), direction=(0, 1, 0), spread=60, vel=(3.0, 6.5), gravity=(0, -9.8, 0), scale=(0.1, 0.25), curve="shrink", additive=True, size=0.25,
                   colors=[(0, "#fff7c0ff"), (0.5, "#ffb030ff"), (1, "#ff300000")], damping=(0.3, 0.8)),
    "magic": dict(amount=48, lifetime=2.0, shape=("ring", 0.8), direction=(0, 1, 0), spread=15, vel=(0.4, 1.0), gravity=(0, 0.3, 0), scale=(0.2, 0.5), curve="pop", additive=True, size=0.4,
                  colors=[(0, "#b070ff00"), (0.25, "#d9a0ffff"), (0.7, "#60c0ffc0"), (1, "#4060ff00")], orbit=0.4, light="#a070ff"),
    "snow": dict(amount=200, lifetime=8.0, shape=("box", (12, 0.2, 12)), direction=(0, -1, 0), spread=12, vel=(0.5, 1.0), gravity=(0.2, -0.3, 0), scale=(0.15, 0.35), curve=None, additive=False, size=0.3,
                 colors=[(0, "#ffffff00"), (0.1, "#ffffffff"), (0.9, "#ffffffff"), (1, "#ffffff00")], turbulence=0.2, height=8),
    "rain": dict(amount=400, lifetime=1.2, shape=("box", (14, 0.2, 14)), direction=(0, -1, 0), spread=2, vel=(14, 18), gravity=(0, -10, 0), scale=(0.05, 0.08), curve=None, additive=False, size=(0.04, 0.6),
                 colors=[(0, "#a8c8ff80"), (1, "#a8c8ff40")], height=10, stretch=True),
    "explosion": dict(amount=60, lifetime=1.0, one_shot=True, explosiveness=1.0, shape=("sphere", 0.2), direction=(0, 1, 0), spread=180, vel=(4, 9), gravity=(0, -2, 0), scale=(0.6, 1.4), curve="shrink", additive=True,
                      size=1.0, colors=[(0, "#fff2c0ff"), (0.25, "#ff9a30ff"), (0.6, "#802010a0"), (1, "#20101000")], damping=(2, 5), light="#ff9040"),
    "dust": dict(amount=30, lifetime=2.5, shape=("box", (3, 0.1, 3)), direction=(0, 1, 0), spread=60, vel=(0.1, 0.4), gravity=(0, 0.05, 0), scale=(0.3, 0.9), curve="grow", additive=False, size=0.8,
                 colors=[(0, "#c8b89000"), (0.3, "#c8b89060"), (1, "#c8b89000")], turbulence=0.25),
    "leaves": dict(amount=40, lifetime=6.0, shape=("box", (8, 0.2, 8)), direction=(0, -1, 0), spread=30, vel=(0.4, 1.0), gravity=(0.3, -0.8, 0), scale=(0.25, 0.5), curve=None, additive=False, size=0.4,
                   colors=[(0, "#6fa83000"), (0.1, "#8bc34aff"), (0.9, "#c0842cff"), (1, "#c0842c00")], turbulence=0.4, height=6, spin=(-180, 180)),
    "heal": dict(amount=30, lifetime=1.6, shape=("ring", 0.6), direction=(0, 1, 0), spread=5, vel=(0.8, 1.6), gravity=(0, 0.4, 0), scale=(0.15, 0.35), curve="shrink", additive=True, size=0.35,
                 colors=[(0, "#7dffb000"), (0.2, "#a8ffd0ff"), (1, "#30e07000")], light="#60ffa0"),
    "portal": dict(amount=90, lifetime=1.8, shape=("ring", 1.2), direction=(0, 0, 0), spread=0, vel=(0.0, 0.2), gravity=(0, 0, 0), scale=(0.15, 0.4), curve="pop", additive=True, size=0.35,
                   colors=[(0, "#40a0ff00"), (0.3, "#80d0ffff"), (0.7, "#a050ffc0"), (1, "#a050ff00")], orbit=0.6, radial=-0.6, light="#6090ff"),
    "fountain": dict(amount=120, lifetime=2.0, shape=("sphere", 0.05), direction=(0, 1, 0), spread=10, vel=(5.5, 7.0), gravity=(0, -9.8, 0), scale=(0.15, 0.3), curve=None, additive=False, size=0.3,
                     colors=[(0, "#bfe4ff00"), (0.1, "#bfe4ffd0"), (1, "#80c0ff40")]),
    "fireflies": dict(amount=24, lifetime=4.0, shape=("box", (6, 2, 6)), direction=(0, 1, 0), spread=180, vel=(0.1, 0.4), gravity=(0, 0, 0), scale=(0.08, 0.16), curve="pop", additive=True, size=0.2,
                      colors=[(0, "#d8ff6000"), (0.3, "#e8ff80ff"), (0.7, "#a8ff40ff"), (1, "#a8ff4000")], turbulence=0.5),
    "bubbles": dict(amount=40, lifetime=3.5, shape=("box", (1.5, 0.1, 1.5)), direction=(0, 1, 0), spread=10, vel=(0.5, 1.0), gravity=(0, 0.5, 0), scale=(0.1, 0.3), curve="grow", additive=False, size=0.3,
                    colors=[(0, "#d0f0ff00"), (0.15, "#d0f0ff90"), (1, "#d0f0ff00")], turbulence=0.2),
    "muzzle_flash": dict(amount=12, lifetime=0.12, one_shot=True, explosiveness=1.0, shape=("point", 0), direction=(0, 0, -1), spread=25, vel=(3, 8), gravity=(0, 0, 0), scale=(0.3, 0.7), curve="shrink", additive=True,
                         size=0.5, colors=[(0, "#fff7d0ff"), (0.5, "#ffb040ff"), (1, "#ff300000")], light="#ffc060"),
    "hit_impact": dict(amount=14, lifetime=0.45, one_shot=True, explosiveness=1.0, shape=("sphere", 0.05), direction=(0, 1, 0), spread=180, vel=(2, 5), gravity=(0, -6, 0), scale=(0.1, 0.25), curve="shrink", additive=True,
                       size=0.25, colors=[(0, "#ffffffff"), (0.4, "#ffd060ff"), (1, "#ff602000")]),
}


def _curve_points(kind):
    return {"shrink": [(0, 1.0), (1, 0.0)], "grow": [(0, 0.4), (1, 1.0)], "pop": [(0, 0.0), (0.2, 1.0), (1, 0.0)]}[kind]


def _curve_lines(points):
    parts = []
    for i, (x, y) in enumerate(points):
        parts.append("Vector2(%s, %s), 0.0, 0.0, 0, 0" % (f(x), f(y)))
    return ["_data = [%s]" % ", ".join(parts), "point_count = %d" % len(points)]


def _grad_lines(stops):
    offs = [s[0] for s in stops]
    cols = []
    for _o, h in stops:
        r, g, b, a = hex_rgba(h)
        cols += [r, g, b, a]
    return ["offsets = " + PF32(offs), "colors = PackedColorArray(" + ", ".join(f(round(x, 4)) for x in cols) + ")"]


@tool(G, "ms_godot_particles",
      "Add a GPU particle effect to a scene: fire, smoke, sparks, magic, snow, rain, explosion, dust, leaves, heal, portal, fountain, fireflies, bubbles, muzzle_flash, hit_impact. Builds the ParticleProcessMaterial, "
      "colour ramp, size curve, soft sprite and additive/billboard material for 3D or 2D, with an optional matching light. New scene or merged into an existing one.",
      {"preset": {"type": "string", "enum": sorted(FX)}, "mode": {"type": "string", "enum": ["3d", "2d"]}, "position": {"type": "array", "items": {"type": "number"}}, "name": {"type": "string"},
       "color": {"type": ["string", "array"], "description": "Tint multiplied into the colour ramp."}, "intensity": {"type": "number", "description": "Scales particle count (default 1)."},
       "size_scale": {"type": "number"}, "light": {"type": "boolean"}, "scene_path": SCENE, "into_scene": INTO, "parent": PARENT, "overwrite": OVERWRITE}, ["preset"], writes=True, local=True)
def particles(args, ctx):
    p = _proj(args, ctx)
    name_p = str(args.get("preset") or "").lower()
    if name_p not in FX:
        raise ToolkitError("unknown preset '%s'" % name_p, "Presets: " + ", ".join(sorted(FX)))
    d = FX[name_p]
    mode = str(args.get("mode") or "3d").lower()
    d3 = mode == "3d"
    k_int = num(args.get("intensity"), 1.0, 0.05, 20)
    ssc = num(args.get("size_scale"), 1.0, 0.05, 50)
    tint = hex_rgba(args.get("color"), "#ffffff") if args.get("color") else None
    nm = ident(args.get("name") or "Fx_" + name_p)
    sb = SB(nm, "GPUParticles3D" if d3 else "GPUParticles2D", "fx_" + name_p)
    ramp_stops = []
    for off, hx in d["colors"]:
        r, g, b, a = hex_rgba(hx)
        if tint:
            r, g, b = r * tint[0], g * tint[1], b * tint[2]
        ramp_stops.append((off, (round(r, 4), round(g, 4), round(b, 4), a)))
    grad = sb.sub("Gradient", lines=["offsets = " + PF32([o for o, _ in ramp_stops]), "colors = PackedColorArray(" + ", ".join(f(x) for _o, c in ramp_stops for x in c) + ")"], hint="Gradient")
    ramp = sb.sub("GradientTexture1D", {"gradient": 'SubResource("%s")' % grad}, hint="GradientTexture1D")
    pm = {}
    shp, shp_size = d["shape"]
    S = 1.0 if d3 else 100.0
    shape_id = {"point": 0, "sphere": 1, "box": 3, "ring": 6}[shp]
    pm["emission_shape"] = str(shape_id)
    if shp == "sphere":
        pm["emission_sphere_radius"] = f(shp_size * S)
    elif shp == "box":
        ex = [x * S for x in shp_size]
        pm["emission_box_extents"] = V3(*ex)
    elif shp == "ring":
        pm["emission_ring_axis"] = V3(0, 0, 1) if not d3 or name_p == "portal" else V3(0, 1, 0)
        pm["emission_ring_height"] = "0.05"
        pm["emission_ring_radius"] = f(shp_size * S)
        pm["emission_ring_inner_radius"] = f(shp_size * S * 0.85)
        if not d3:
            pm["emission_ring_axis"] = V3(0, 0, 1)
    dx, dy, dz = d["direction"]
    if not d3:
        dy, dz = -dy, 0
    pm["direction"] = V3(dx, dy, dz)
    pm["spread"] = f(d["spread"])
    pm["initial_velocity_min"] = f(d["vel"][0] * S)
    pm["initial_velocity_max"] = f(d["vel"][1] * S)
    gx, gy, gz = d["gravity"]
    pm["gravity"] = V3(gx * S, (gy * S) if d3 else -gy * S, 0 if not d3 else gz)
    smin, smax = d["scale"]
    f2 = 1.0 if d3 else 1.6
    pm["scale_min"] = f(smin * ssc * f2)
    pm["scale_max"] = f(smax * ssc * f2)
    if d.get("curve"):
        cv = sb.sub("Curve", lines=_curve_lines(_curve_points(d["curve"])), hint="Curve")
        ct = sb.sub("CurveTexture", {"curve": 'SubResource("%s")' % cv}, hint="CurveTexture")
        pm["scale_curve"] = 'SubResource("%s")' % ct
    pm["color_ramp"] = 'SubResource("%s")' % ramp
    if d.get("damping"):
        pm["damping_min"] = f(d["damping"][0] * S)
        pm["damping_max"] = f(d["damping"][1] * S)
    if d.get("turbulence"):
        pm["turbulence_enabled"] = "true"
        pm["turbulence_noise_strength"] = f(d["turbulence"] * (1 if d3 else 5))
        pm["turbulence_noise_scale"] = "2.5"
    if d.get("orbit"):
        pm["orbit_velocity_min"] = f(d["orbit"] * 0.8)
        pm["orbit_velocity_max"] = f(d["orbit"])
    if d.get("radial"):
        pm["radial_accel_min"] = f(d["radial"] * S)
        pm["radial_accel_max"] = f(d["radial"] * S)
    if d.get("spin"):
        pm["angle_min"] = f(d["spin"][0])
        pm["angle_max"] = f(d["spin"][1])
        pm["angular_velocity_min"] = f(d["spin"][0])
        pm["angular_velocity_max"] = f(d["spin"][1])
    if not d3:
        pm["particle_flag_disable_z"] = "true"
    pmat = sb.sub("ParticleProcessMaterial", pm, hint="ParticleProcessMaterial")
    soft = sb.sub("Gradient", lines=["offsets = " + PF32([0, 0.4, 1]), "colors = PackedColorArray(1, 1, 1, 1, 1, 1, 1, 0.55, 1, 1, 1, 0)"], hint="SoftGradient")
    stex = sb.sub("GradientTexture2D", {"gradient": 'SubResource("%s")' % soft, "width": "64", "height": "64", "fill": "1", "fill_from": V2(0.5, 0.5), "fill_to": V2(1, 0.5)}, hint="SoftTexture")
    amount = max(1, int(round(d["amount"] * k_int)))
    props = {"emitting": "true", "amount": str(amount), "lifetime": f(d["lifetime"]), "process_material": 'SubResource("%s")' % pmat}
    if d.get("one_shot"):
        props["one_shot"] = "true"
    if d.get("explosiveness"):
        props["explosiveness"] = f(d["explosiveness"])
    if not d.get("one_shot"):
        props["preprocess"] = f(min(d["lifetime"], 4.0) * 0.5)
    pos = [num(x, 0, -100000, 100000) for x in as_list(args.get("position"))]
    if d3:
        sz = d["size"] if isinstance(d["size"], tuple) else (d["size"], d["size"])
        mat = sb.sub("StandardMaterial3D", {"transparency": "1", "blend_mode": "1" if d["additive"] else "0", "shading_mode": "0", "vertex_color_use_as_albedo": "true", "albedo_texture": 'SubResource("%s")' % stex,
                                            "billboard_mode": "3", "billboard_keep_scale": "true", "disable_receive_shadows": "true"}, hint="ParticleMaterial")
        quad = sb.sub("QuadMesh", {"material": 'SubResource("%s")' % mat, "size": V2(sz[0] * ssc, sz[1] * ssc)}, hint="QuadMesh")
        props["draw_pass_1"] = 'SubResource("%s")' % quad
        ext = max(4.0, d.get("height", 4.0) + 2.0)
        props["visibility_aabb"] = "AABB(%s, %s, %s, %s, %s, %s)" % tuple(f(x) for x in (-ext, -ext, -ext, ext * 2, ext * 2, ext * 2))
        if len(pos) == 3:
            props["position"] = V3(*pos)
    else:
        props["texture"] = 'SubResource("%s")' % stex
        props["visibility_rect"] = "Rect2(-400, -400, 800, 800)"
        if d["additive"]:
            cim = sb.sub("CanvasItemMaterial", {"blend_mode": "1", "particles_animation": "false"}, hint="CanvasItemMaterial")
            props["material"] = 'SubResource("%s")' % cim
        if len(pos) >= 2:
            props["position"] = V2(pos[0], pos[1])
    root = sb.nodes[0]
    for k, v in props.items():
        root["body"].append("%s = %s" % (k, v))
    if boolean(args.get("light"), bool(d.get("light"))) and d.get("light"):
        lc = C(args.get("color") or d["light"])
        if d3:
            sb.node("Glow", "OmniLight3D", ".", {"light_color": lc, "light_energy": "1.6", "omni_range": "5.0", "shadow_enabled": "false"})
        else:
            sb.node("Glow", "PointLight2D", ".", {"color": lc, "energy": "1.2", "texture_scale": "3.0", "texture": 'SubResource("%s")' % stex})
    out = Out(p, args)
    path, top = target_scene(p, args, sb, "Fx_%s_%s.tscn" % (name_p, mode), out)
    return out.done(scene=path, node=top, preset=name_p, mode=mode, amount=amount,
                    hint="Instance the scene where the effect should play. One-shot effects restart with `restart()`; looping ones run while `emitting` is true.")


# ───────────────────────── ui kit + theme ─────────────────────────
GUI_SCREENS = ["main_menu", "hud", "pause", "shop", "dialog", "toast", "settings", "inventory"]
GUI_THEMES = {  # bg, panel, accent, text, muted, button, corner radius, border
    "classic": ("#14161c", "#2b2f3a", "#e0a82e", "#f4f4f4", "#9aa0ad", "#3b4252", 6, 2),
    "modern_dark": ("#0e1116", "#171b22", "#4c8bf5", "#eef1f6", "#8b93a3", "#222834", 12, 0),
    "glass": ("#0b1220", "#1a2740", "#7fd1ff", "#ffffff", "#a4b4cc", "#27385c", 16, 1),
    "neon": ("#07040f", "#150d2b", "#ff2ea6", "#f5ecff", "#a58cd9", "#241446", 8, 2),
    "pastel": ("#f7efe8", "#ffffff", "#ff8fab", "#4a3f45", "#9a8a92", "#ffe3ea", 18, 0),
    "retro_terminal": ("#020a04", "#06200c", "#3dff6a", "#c8ffd6", "#4aa862", "#0a3315", 0, 2),
}
_FULL = {"layout_mode": "3", "anchors_preset": "15", "anchor_right": "1.0", "anchor_bottom": "1.0", "grow_horizontal": "2", "grow_vertical": "2"}


def theme_resource(theme_name):
    bg, panel, acc, txt, mut, btn, rad, bw = GUI_THEMES[theme_name]
    subs = []

    def box(name, color, border=None, radius=rad, margins=(18, 10), shadow=0, bwidth=None):
        b = {"bg_color": C(color), "corner_radius_top_left": str(radius), "corner_radius_top_right": str(radius), "corner_radius_bottom_right": str(radius), "corner_radius_bottom_left": str(radius),
             "content_margin_left": str(margins[0]), "content_margin_right": str(margins[0]), "content_margin_top": str(margins[1]), "content_margin_bottom": str(margins[1])}
        w = bw if bwidth is None else bwidth
        if border and w:
            b.update({"border_color": C(border), "border_width_left": str(w), "border_width_top": str(w), "border_width_right": str(w), "border_width_bottom": str(w)})
        if shadow:
            b.update({"shadow_color": "Color(0, 0, 0, 0.35)", "shadow_size": str(shadow), "shadow_offset": "Vector2(0, 3)"})
        subs.append((name, b))
        return name
    box("btn_normal", btn, mut)
    box("btn_hover", lerp_hex(btn, acc, 0.35), acc)
    box("btn_pressed", lerp_hex(btn, "#000000", 0.25), acc)
    box("btn_disabled", lerp_hex(btn, bg, 0.6), None)
    box("btn_focus", btn, acc, bwidth=max(2, bw))
    subs[-1][1]["draw_center"] = "false"
    box("panel", panel, lerp_hex(panel, acc, 0.5), margins=(24, 20), shadow=12)
    box("bar_bg", bg, mut, radius=max(0, rad // 2), margins=(0, 0))
    box("bar_fill", acc, None, radius=max(0, rad // 2), margins=(0, 0))
    box("slider_bg", bg, None, radius=4, margins=(0, 2))
    box("slider_fill", acc, None, radius=4, margins=(0, 2))
    box("line_edit", bg, mut, margins=(12, 8))
    sb_ids = {}
    out = []
    ids = {}
    for name, props in subs:
        ids[name] = "StyleBoxFlat_%s_%s" % (name, hashlib.md5((theme_name + name).encode()).hexdigest()[:4])
    for name, props in subs:
        out.append('[sub_resource type="StyleBoxFlat" id="%s"]' % ids[name])
        out += ["%s = %s" % (k, v) for k, v in props.items()]
        out.append("")
    S = lambda n: 'SubResource("%s")' % ids[n]
    res = ["default_font_size = 22",
           "Button/colors/font_color = " + C(txt), "Button/colors/font_hover_color = " + C(txt), "Button/colors/font_pressed_color = " + C(acc), "Button/colors/font_disabled_color = " + C(mut),
           "Button/font_sizes/font_size = 24", "Button/styles/normal = " + S("btn_normal"), "Button/styles/hover = " + S("btn_hover"), "Button/styles/pressed = " + S("btn_pressed"),
           "Button/styles/disabled = " + S("btn_disabled"), "Button/styles/focus = " + S("btn_focus"),
           "CheckButton/colors/font_color = " + C(txt), "CheckBox/colors/font_color = " + C(txt),
           "Label/colors/font_color = " + C(txt), "Label/font_sizes/font_size = 22,",
           "RichTextLabel/colors/default_color = " + C(txt),
           "Panel/styles/panel = " + S("panel"), "PanelContainer/styles/panel = " + S("panel"),
           "ProgressBar/styles/background = " + S("bar_bg"), "ProgressBar/styles/fill = " + S("bar_fill"), "ProgressBar/colors/font_color = " + C(txt),
           "HSlider/styles/slider = " + S("slider_bg"), "HSlider/styles/grabber_area = " + S("slider_fill"), "HSlider/styles/grabber_area_highlight = " + S("slider_fill"),
           "LineEdit/styles/normal = " + S("line_edit"), "LineEdit/colors/font_color = " + C(txt)]
    res[res.index("Label/font_sizes/font_size = 22,")] = "Label/font_sizes/font_size = 22"
    text = ['[gd_resource type="Theme" load_steps=%d format=3]' % (len(subs) + 1), ""] + out + ["[resource]"] + res
    return "\n".join(text) + "\n"


def lerp_hex(a, b, t):
    r, g, bl, al = lerp_col(a, b, t)
    return "#%02x%02x%02x" % (int(round(r * 255)), int(round(g * 255)), int(round(bl * 255)))


def _ov(size=None, color=None, sep=None):
    d = {}
    if size:
        d["theme_override_font_sizes/font_size"] = str(size)
    if color:
        d["theme_override_colors/font_color"] = color
    if sep is not None:
        d["theme_override_constants/separation"] = str(sep)
    return d


def build_screen(screen, theme, title, labels, items, root_name):
    from godot_ui_scripts import SCRIPTS
    bg, panel, acc, txt, mut, btn, rad, bw = GUI_THEMES[theme]
    sb = SB(root_name, "Control", "ui_" + screen)
    root = sb.nodes[0]
    root["body"] += ["%s = %s" % (k, v) for k, v in _FULL.items()]
    root["body"].append("mouse_filter = 2" if screen in ("hud", "toast") else "mouse_filter = 0")

    def N(name, typ, parent, props=None, unique=False, groups=None):
        pr = dict(props or {})
        if unique:
            pr["unique_name_in_owner"] = "true"
        return sb.node(name, typ, parent, pr, groups)
    def centered(parent="."):
        return N("Center", "CenterContainer", parent, dict(_FULL))
    def dim(parent=".", alpha=0.62):
        N("Dim", "ColorRect", parent, dict(_FULL, color=Cx((*hex_rgba(bg)[:3], alpha))))
    cont = lambda extra=None: dict({"layout_mode": "2"}, **(extra or {}))
    if screen == "main_menu":
        N("Background", "ColorRect", ".", dict(_FULL, color=C(bg)))
        c = centered()
        v = N("Menu", "VBoxContainer", c, cont(_ov(sep=16)))
        N("Title", "Label", v, cont(dict(text=gstr(title or "MY GAME"), horizontal_alignment="1", **_ov(84, C(txt)))))
        N("Subtitle", "Label", v, cont(dict(text=gstr(items[0] if items else "A Multi-Script game"), horizontal_alignment="1", **_ov(26, C(mut)))))
        N("Spacer", "Control", v, cont({"custom_minimum_size": V2(0, 28)}))
        for i, lab in enumerate(labels):
            N(ident(lab) + "Button", "Button", v, cont({"custom_minimum_size": V2(340, 62), "text": gstr(lab)}), unique=True)
    elif screen == "pause":
        dim()
        c = centered()
        pc = N("Panel", "PanelContainer", c, cont({"custom_minimum_size": V2(460, 0)}))
        v = N("Menu", "VBoxContainer", pc, cont(_ov(sep=14)))
        N("Title", "Label", v, cont(dict(text=gstr(title or "PAUSED"), horizontal_alignment="1", **_ov(52, C(txt)))))
        for lab in labels:
            N(ident(lab) + "Button", "Button", v, cont({"custom_minimum_size": V2(0, 58), "text": gstr(lab)}), unique=True)
    elif screen == "hud":
        m = N("Margin", "MarginContainer", ".", dict(_FULL, mouse_filter="2", **{"theme_override_constants/margin_left": "32", "theme_override_constants/margin_top": "28", "theme_override_constants/margin_right": "32", "theme_override_constants/margin_bottom": "28"}))
        v = N("Layout", "VBoxContainer", m, {"layout_mode": "2", "mouse_filter": "2"})
        top = N("Top", "HBoxContainer", v, {"layout_mode": "2", "mouse_filter": "2"})
        left = N("Bars", "VBoxContainer", top, {"layout_mode": "2", "mouse_filter": "2", **_ov(sep=8)})
        hb = N("HealthBar", "ProgressBar", left, {"custom_minimum_size": V2(360, 30), "layout_mode": "2", "value": "80.0", "show_percentage": "false", "mouse_filter": "2"}, unique=True)
        mb = N("ManaBar", "ProgressBar", left, {"custom_minimum_size": V2(280, 22), "layout_mode": "2", "value": "60.0", "show_percentage": "false", "mouse_filter": "2"}, unique=True)
        N("Gap", "Control", top, {"layout_mode": "2", "size_flags_horizontal": "3", "mouse_filter": "2"})
        N("ScoreLabel", "Label", top, {"layout_mode": "2", "text": gstr(labels[0] if labels else "SCORE 0"), "horizontal_alignment": "2", "mouse_filter": "2", **_ov(40, C(txt))}, unique=True)
        N("Fill", "Control", v, {"layout_mode": "2", "size_flags_vertical": "3", "mouse_filter": "2"})
        bot = N("Bottom", "CenterContainer", v, {"layout_mode": "2", "mouse_filter": "2"})
        hot = N("Hotbar", "HBoxContainer", bot, {"layout_mode": "2", "mouse_filter": "2", **_ov(sep=10)}, unique=True)
        for i in range(max(1, min(10, len(items) or 5))):
            s = N("Slot%d" % (i + 1), "PanelContainer", hot, {"custom_minimum_size": V2(78, 78), "layout_mode": "2", "mouse_filter": "2"})
            N("Key", "Label", s, {"layout_mode": "2", "text": gstr(items[i] if i < len(items) else str(i + 1)), "horizontal_alignment": "1", "vertical_alignment": "1", "mouse_filter": "2", **_ov(22, C(mut))})
    elif screen == "shop":
        dim()
        c = centered()
        pc = N("Panel", "PanelContainer", c, cont({"custom_minimum_size": V2(960, 560)}))
        v = N("Layout", "VBoxContainer", pc, cont(_ov(sep=18)))
        top = N("Top", "HBoxContainer", v, cont())
        N("Title", "Label", top, cont(dict(text=gstr(title or "SHOP"), size_flags_horizontal="3", **_ov(48, C(txt)))))
        N("CloseButton", "Button", top, cont({"text": gstr("X"), "custom_minimum_size": V2(56, 56)}), unique=True)
        g = N("Items", "GridContainer", v, cont({"columns": "4", "theme_override_constants/h_separation": "16", "theme_override_constants/v_separation": "16"}))
        for it in (items or ["Sword:100", "Shield:80", "Potion:25", "Boots:60"]):
            nm, _, price = str(it).partition(":")
            card = N("Item_" + ident(nm), "PanelContainer", g, cont({"custom_minimum_size": V2(200, 0)}))
            cv = N("Box", "VBoxContainer", card, cont(_ov(sep=8)))
            N("Icon", "ColorRect", cv, cont({"custom_minimum_size": V2(0, 110), "color": C(acc, alpha=0.85)}))
            N("Name", "Label", cv, cont(dict(text=gstr(nm), horizontal_alignment="1", **_ov(24, C(txt)))))
            N("Buy_" + ident(nm), "Button", cv, cont({"text": gstr("Buy  " + price if price else "Buy"), "metadata/price": str(int(float(price)) if re.fullmatch(r"\d+(\.\d+)?", price or "") else 0)}))
    elif screen == "dialog":
        pc = N("Panel", "PanelContainer", ".", {"layout_mode": "1", "anchors_preset": "12", "anchor_top": "1.0", "anchor_right": "1.0", "anchor_bottom": "1.0", "offset_left": "48.0", "offset_top": "-270.0",
                                               "offset_right": "-48.0", "offset_bottom": "-32.0", "grow_horizontal": "2", "grow_vertical": "0"})
        v = N("Box", "VBoxContainer", pc, cont(_ov(sep=10)))
        N("NameLabel", "Label", v, cont(dict(text=gstr(title or "Narrator"), **_ov(30, C(acc)))), unique=True)
        N("Body", "RichTextLabel", v, cont({"size_flags_vertical": "3", "bbcode_enabled": "true", "text": gstr(items[0] if items else "Hello, traveller. It is dangerous to go alone."), "theme_override_font_sizes/normal_font_size": "26"}), unique=True)
        ch = N("Choices", "HBoxContainer", v, cont({"alignment": "2", **_ov(sep=12)}), unique=True)
        for i in range(max(1, min(4, len(labels) or 2))):
            N("Choice%d" % (i + 1), "Button", ch, cont({"custom_minimum_size": V2(220, 48), "text": gstr(labels[i] if i < len(labels) else "Continue")}))
    elif screen == "toast":
        m = N("Margin", "MarginContainer", ".", dict(_FULL, mouse_filter="2", **{"theme_override_constants/margin_top": "24", "theme_override_constants/margin_right": "24", "theme_override_constants/margin_left": "24", "theme_override_constants/margin_bottom": "24"}))
        N("ToastList", "VBoxContainer", m, {"layout_mode": "2", "size_flags_horizontal": "8", "size_flags_vertical": "0", "mouse_filter": "2", **_ov(sep=8)}, unique=True)
    elif screen == "settings":
        dim(alpha=0.8)
        c = centered()
        pc = N("Panel", "PanelContainer", c, cont({"custom_minimum_size": V2(620, 0)}))
        v = N("Layout", "VBoxContainer", pc, cont(_ov(sep=16)))
        N("Title", "Label", v, cont(dict(text=gstr(title or "SETTINGS"), horizontal_alignment="1", **_ov(48, C(txt)))))
        g = N("Grid", "GridContainer", v, cont({"columns": "2", "theme_override_constants/h_separation": "24", "theme_override_constants/v_separation": "14"}))
        for lab in (labels or ["Master", "Music", "SFX"]):
            N(ident(lab) + "Label", "Label", g, cont({"text": gstr(lab)}))
            N(ident(lab) + "Slider", "HSlider", g, cont({"size_flags_horizontal": "3", "size_flags_vertical": "4", "max_value": "1.0", "step": "0.01", "value": "0.8", "custom_minimum_size": V2(280, 24)}))
        N("FullscreenCheck", "CheckButton", v, cont({"text": gstr("Fullscreen")}), unique=True)
        N("VSyncCheck", "CheckButton", v, cont({"text": gstr("VSync"), "button_pressed": "true"}), unique=True)
        N("BackButton", "Button", v, cont({"text": gstr("Back"), "custom_minimum_size": V2(0, 56)}), unique=True)
    elif screen == "inventory":
        dim()
        c = centered()
        pc = N("Panel", "PanelContainer", c, cont())
        v = N("Layout", "VBoxContainer", pc, cont(_ov(sep=14)))
        N("Title", "Label", v, cont(dict(text=gstr(title or "INVENTORY"), **_ov(44, C(txt)))))
        g = N("Grid", "GridContainer", v, cont({"columns": "6", "theme_override_constants/h_separation": "10", "theme_override_constants/v_separation": "10"}), unique=True)
        total = max(12, ((len(items) + 5) // 6) * 6) if items else 24
        for i in range(total):
            s = N("Slot%d" % (i + 1), "PanelContainer", g, cont({"custom_minimum_size": V2(92, 92)}))
            N("Label", "Label", s, cont(dict(text=gstr(items[i] if i < len(items) else ""), horizontal_alignment="1", vertical_alignment="1", **_ov(18, C(txt)))))
    return sb, SCRIPTS[screen]


@tool(G, "ms_godot_ui_kit",
      "Build a themed Control screen: main_menu, hud (bars, score, hotbar), pause, shop, dialog (typewriter + choices), toast, settings (audio-bus sliders, fullscreen, vsync) or inventory. Writes the scene (responsive containers), "
      "a Theme .tres (classic, modern_dark, glass, neon, pastel, retro_terminal) and a GDScript controller with signals. Buttons use unique names (%PlayButton).",
      {"screen": {"type": "string", "enum": GUI_SCREENS}, "theme": {"type": "string", "enum": sorted(GUI_THEMES)}, "title": {"type": "string"},
       "buttons": {"type": "array", "items": {"type": "string"}, "description": "Button labels / choices / slider names / score text."},
       "items": {"type": "array", "items": {"type": "string"}, "description": "shop 'Name:Price', inventory items, dialog text, hotbar labels, menu subtitle."},
       "scene_path": SCENE, "script": {"type": "boolean", "description": "Write and attach the controller (default true)."}, "theme_path": {"type": "string"}, "overwrite": OVERWRITE}, ["screen"], writes=True, local=True)
def ui_kit(args, ctx):
    p = _proj(args, ctx)
    screen = str(args.get("screen") or "").lower()
    if screen not in GUI_SCREENS:
        raise ToolkitError("unknown screen '%s'" % screen, "Screens: " + ", ".join(GUI_SCREENS))
    theme = str(args.get("theme") or "modern_dark").lower()
    if theme not in GUI_THEMES:
        raise ToolkitError("unknown theme '%s'" % theme, "Themes: " + ", ".join(sorted(GUI_THEMES)))
    default_btns = {"main_menu": ["Play", "Settings", "Quit"], "pause": ["Resume", "Restart", "Quit"], "dialog": ["Yes", "No"]}
    labels = [str(x)[:40] for x in as_list(args.get("buttons"))][:12] or default_btns.get(screen, [])
    items = [str(x)[:120] for x in as_list(args.get("items"))][:60]
    root_name = ident(screen.title().replace("_", ""), "Screen")
    sb, script_src = build_screen(screen, theme, str(args.get("title") or ""), labels, items, root_name)
    out = Out(p, args)
    theme_path = norm_res(args.get("theme_path") or "ms_%s" % theme, ".tres", "res://themes")
    theme_full = _abs(p, theme_path)
    if not os.path.exists(theme_full) or boolean(args.get("overwrite"), False):
        out.put(theme_path, theme_resource(theme), "Theme", allow_overwrite=True)
    root = sb.nodes[0]
    root["body"].insert(0, 'theme = ExtResource("%s")' % sb.ext_res(theme_path, "Theme"))
    script_path = None
    if boolean(args.get("script"), True):
        script_path = norm_res("scripts/ui/%s.gd" % screen, ".gd")
        sid = sb.ext_res(script_path, "Script")
        root["body"].insert(0, 'script = ExtResource("%s")' % sid)
        out.put(script_path, script_src, "GDScript")
    if screen in ("pause", "dialog", "shop") and screen != "dialog":
        root["body"].append("visible = %s" % ("false" if screen == "pause" else "true"))
    scene_path = norm_res(args.get("scene_path") or "%s.tscn" % screen, ".tscn", "res://scenes/ui")
    out.put(scene_path, sb.render(), "scene")
    return out.done(scene=scene_path, theme=theme_path, script=script_path, ui_theme=theme, buttons=[n["name"] for n in sb.nodes if n["type"] == "Button"][:20],
                    hint="Instance the scene under a CanvasLayer. Pause menu uses the ui_cancel action (Esc) and works while the tree is paused.")


# ───────────────────────── shaders ─────────────────────────
import godot_shaders as _gs  # noqa: E402

SHADER_NAMES = sorted(_gs.SHADERS)
_UNI = re.compile(r"^uniform\s+(\w+)\s+(\w+)\s*(?::\s*([^=;]+))?(?:=\s*(.*?))?;", re.M)


def shader_uniforms(code):
    out = {}
    for m in _UNI.finditer(code):
        out[m.group(2)] = {"type": m.group(1), "hint": (m.group(3) or "").strip(), "default": (m.group(4) or "").strip()}
    return out


def uniform_literal(info, value):
    t, hint = info["type"], info["hint"]
    if t in ("float", "int"):
        return f(num(value, 0, -1e9, 1e9)) if t == "float" else str(int(num(value, 0, -1e9, 1e9)))
    if t == "bool":
        return "true" if boolean(value, False) else "false"
    if t in ("vec4", "vec3") and "source_color" in hint:
        return C(value)
    if t == "vec2":
        v = as_list(value)
        return V2(*(v + [0, 0])[:2])
    if t == "vec3":
        v = as_list(value)
        return V3(*(v + [0, 0, 0])[:3])
    if t == "vec4":
        v = as_list(value)
        return "Vector4(%s)" % ", ".join(f(x) for x in (v + [0, 0, 0, 1])[:4])
    raise ToolkitError("cannot set a `%s` uniform from JSON" % t, "Textures: assign them in the editor (sampler2D) or pass a res:// path via `textures`.")


@tool(G, "ms_godot_shader_create",
      "Write a ready-made Godot 4 shader + ShaderMaterial: toon, outline, dissolve, hologram, water, rim_glow, wind_sway, grid (3D); outline_2d, flash_white, dissolve_2d, pixelate, wave_2d, scroll_uv, glow_pulse, vignette, crt, "
      "color_grade (2D/screen), or `custom` with your own `code`. Set uniforms with `params`, add an outline pass with `with_outline`, and assign the material to a node in a scene with `assign_to`.",
      {"shader": {"type": "string", "enum": SHADER_NAMES + ["custom"]}, "name": {"type": "string"}, "code": {"type": "string", "description": "Shader source when shader=custom."},
       "params": {"type": "object", "description": "Uniform name -> value ({'dissolve': 0.5, 'edge_color': '#ff8800'})."}, "textures": {"type": "object", "description": "Sampler uniform -> res:// texture path."},
       "with_outline": {"type": "boolean", "description": "3D only: add an outline material as next_pass."}, "outline_color": {"type": ["string", "array"]}, "outline_width": {"type": "number"},
       "assign_to": {"type": "object", "description": "{scene_path, node} to set material_override (3D) / material (2D) on that node."}, "list": {"type": "boolean"}, "overwrite": OVERWRITE}, [], writes=True, local=True)
def shader_create(args, ctx):
    if boolean(args.get("list"), False) or not args.get("shader"):
        return {"shaders": [{"shader": k, "type": v["type"], "summary": v["summary"], "uniforms": list(shader_uniforms(v["code"]))} for k, v in sorted(_gs.SHADERS.items())]}
    p = _proj(args, ctx)
    key = str(args.get("shader") or "").lower()
    if key == "custom":
        code = str(args.get("code") or "")
        if "shader_type" not in code:
            raise ToolkitError("custom shaders need `code` starting with shader_type spatial|canvas_item|particles|sky|fog;")
        kind = re.search(r"shader_type\s+(\w+)", code).group(1)
    elif key in _gs.SHADERS:
        code, kind = _gs.SHADERS[key]["code"], _gs.SHADERS[key]["type"]
    else:
        raise ToolkitError("unknown shader '%s'" % key, "Shaders: " + ", ".join(SHADER_NAMES) + ", custom")
    base = ident(args.get("name") or key)
    unis = shader_uniforms(code)
    params = as_dict(args.get("params"))
    for k in params:
        if k not in unis:
            raise ToolkitError("shader '%s' has no uniform '%s'" % (key, k), "Uniforms: " + ", ".join(unis))
    out = Out(p, args)
    sh_path = out.put("res://shaders/%s.gdshader" % base, code, "Shader")
    lines_ext = [(sh_path, "Shader")]
    mat_lines = ["shader = ExtResource(\"1_shader\")"]
    for k, v in params.items():
        mat_lines.append("shader_parameter/%s = %s" % (k, uniform_literal(unis[k], v)))
    tex_i = 1
    for k, v in as_dict(args.get("textures")).items():
        if k not in unis or unis[k]["type"] != "sampler2D":
            raise ToolkitError("'%s' is not a sampler2D uniform of this shader" % k)
        tex_i += 1
        lines_ext.append((norm_res(v, ""), "Texture2D"))
        mat_lines.append('shader_parameter/%s = ExtResource("%d_tex")' % (k, tex_i))
    ol_path = None
    if boolean(args.get("with_outline"), False) and kind == "spatial":
        ocode = _gs.SHADERS["outline"]["code"]
        osh = out.put("res://shaders/%s_outline.gdshader" % base, ocode, "Shader")
        omat = ["[gd_resource type=\"ShaderMaterial\" load_steps=2 format=3]", "", '[ext_resource type="Shader" path="%s" id="1_shader"]' % osh, "", "[resource]", 'shader = ExtResource("1_shader")',
                "shader_parameter/outline_color = " + C(args.get("outline_color"), "#000000"), "shader_parameter/outline_width = " + f(num(args.get("outline_width"), 0.03, 0, 0.2))]
        ol_path = out.put("res://materials/%s_outline.tres" % base, "\n".join(omat) + "\n", "ShaderMaterial")
        lines_ext.append((ol_path, "Material"))
        mat_lines.append('next_pass = ExtResource("%d_outline")' % (len(lines_ext)))
    head = ['[gd_resource type="ShaderMaterial" load_steps=%d format=3]' % (len(lines_ext) + 1), ""]
    for i, (path, typ) in enumerate(lines_ext, start=1):
        suffix = "shader" if i == 1 else ("outline" if path == ol_path else "tex")
        ident_id = "1_shader" if i == 1 else "%d_%s" % (i, suffix)
        head.append('[ext_resource type="%s" path="%s" id="%s"]' % (typ, path, ident_id))
    mat_path = out.put("res://materials/%s.tres" % base, "\n".join(head + ["", "[resource]"] + mat_lines) + "\n", "ShaderMaterial")
    assigned = None
    at = as_dict(args.get("assign_to"))
    if at:
        sp = _abs(p, norm_res(at.get("scene_path") or "", ".tscn"))
        if not os.path.isfile(sp):
            raise ToolkitError("scene not found: %s" % at.get("scene_path"))
        sc = Scene(_read(sp))
        node = sc.find(str(at.get("node") or "."))
        eid = sc.ext_id(mat_path, "Material")
        ntype = node["attrs"].get("type") or ""
        prop = "material_override" if (ntype.endswith("3D") or ntype.startswith("CSG")) else "material"
        set_raw(sc, node, prop, 'ExtResource("%s")' % eid)
        out.put(_res(p, sp), sc.text().rstrip("\n") + "\n", "scene (material assigned)", allow_overwrite=True)
        assigned = {"node": sc.key(node), "property": prop}
    usage = {"spatial": "Assign the material to MeshInstance3D.material_override (or a surface material).", "canvas_item": "Assign to a CanvasItem's `material` (Sprite2D, TextureRect, ColorRect for screen effects)."}.get(kind, "")
    return out.done(shader=sh_path, material=mat_path, shader_type=kind, uniforms=list(unis), assigned=assigned, hint=usage)
