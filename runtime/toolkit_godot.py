# SPDX-License-Identifier: GPL-3.0-or-later
"""Godot tools for engine_toolkit.

The official Godot MCP exposes 14 coarse tools. Most real Godot work is editing
project.godot, .tscn scenes, .gd scripts and .tres resources - all plain text. These tools
do that work bridge-side, with real parsing (not blind string pasting), so they work with
the editor closed, are instantly reversible with version control, and the editor
hot-reloads the files. Run/stop/debug use the native Godot MCP tools."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import time

from engine_toolkit import (tool, as_list, as_dict, num, boolean, ToolkitError, _need,
                            snapshot_store, snapshot_get, diff_maps)

G = "godot"
SCENE = {"type": "string", "description": "Scene path like res://scenes/Main.tscn (or a path relative to the project)."}
PROPS = {"type": "object", "description": "Property -> value. Use Godot literals as strings ('Vector2(10, 20)'), or JSON: {x,y}->Vector2, {x,y,z}->Vector3, {r,g,b,a}->Color, '#ff8800'->Color."}
_REMEMBER = {}


# ── project resolution ──────────────────────────────────────────────────────
def _proj(args, ctx):
    p = str(args.get("project_path") or "").strip()
    if p.startswith("res://"):
        p = ""
    p = p or _REMEMBER.get("p") or ctx.project_hint(G) or ""
    if not p:
        raise ToolkitError("project_path is required the first time", "Pass the absolute folder that contains project.godot (get_project_info / list_projects find it).")
    p = os.path.abspath(os.path.expanduser(p))
    if os.path.isfile(p) and os.path.basename(p) == "project.godot":
        p = os.path.dirname(p)
    if not os.path.isfile(os.path.join(p, "project.godot")):
        raise ToolkitError(f"no project.godot in {p}", "project_path must be the folder CONTAINING project.godot.")
    _REMEMBER["p"] = p
    try:
        ctx.remember_project(G, p)
    except Exception:
        pass
    return p


def _abs(proj, res):
    r = str(res or "").strip().replace("\\", "/")
    if r.startswith("res://"):
        r = r[6:]
    full = os.path.normpath(os.path.join(proj, r))
    if os.path.commonpath([os.path.abspath(proj), os.path.abspath(full)]) != os.path.abspath(proj):
        raise ToolkitError(f"path escapes the project: {res}")
    return full


def _res(proj, full):
    return "res://" + os.path.relpath(full, proj).replace("\\", "/")


def _read(path):
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        return fh.read()


def _write(path, text, args):
    if args.get("dry_run"):
        return False
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".ms-tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return True


def find_exe():
    try:
        import launch_godot_mcp
        return launch_godot_mcp.find_godot()
    except Exception:
        return shutil.which("godot") or shutil.which("godot4")


# ── Godot literals ──────────────────────────────────────────────────────────
_CTOR = re.compile(r"^(Vector[234]i?|Color|Rect2i?|Transform[23]D|Basis|Quaternion|AABB|Plane|NodePath|StringName|Array|Dictionary|Packed\w+Array|ExtResource|SubResource|Object|Callable|RID|Projection)\s*\(")
_VEC_KEYS = re.compile(r"(position|scale|size|offset|velocity|origin|pivot|gravity|direction|extents|rotation_degrees|anchor|separation|zoom|rect|region|texture_scale|scroll|linear_velocity|uv)", re.I)
_COL_KEYS = re.compile(r"(color|modulate|tint|albedo|emission)", re.I)


def fmt_num(x):
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, int):
        return str(x)
    s = repr(float(x))
    return s[:-2] if s.endswith(".0") else s


def lit(v, key=""):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return fmt_num(v)
    if isinstance(v, str):
        s = v.strip()
        if re.fullmatch(r"-?\d+(\.\d+)?", s):
            return s
        if s in ("true", "false", "null") or _CTOR.match(s) or s.startswith(("&\"", "^\"")):
            return s
        if re.fullmatch(r"#[0-9a-fA-F]{3,8}", s):
            return f'Color("{s}")'
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if isinstance(v, dict):
        low = {str(k).lower(): x for k, x in v.items()}
        if {"r", "g", "b"} <= set(low):
            return "Color(%s)" % ", ".join(fmt_num(low.get(c, 1.0 if c == "a" else 0)) for c in "rgba")
        if {"x", "y", "z"} <= set(low):
            return "Vector3(%s)" % ", ".join(fmt_num(low[c]) for c in "xyz")
        if {"x", "y"} <= set(low):
            return "Vector2(%s)" % ", ".join(fmt_num(low[c]) for c in "xy")
        return "{\n" + ",\n".join(f'"{k}": {lit(x)}' for k, x in v.items()) + "\n}"
    if isinstance(v, (list, tuple)):
        if v and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
            if _COL_KEYS.search(key) and len(v) in (3, 4):
                f = [float(x) for x in v]
                if max(f) > 1:
                    f = [x / 255.0 for x in f]
                return "Color(%s)" % ", ".join(fmt_num(x) for x in (f + [1.0])[:4])
            if len(v) == 2 and (_VEC_KEYS.search(key) or not key):
                return "Vector2(%s)" % ", ".join(fmt_num(x) for x in v)
            if len(v) == 3 and (_VEC_KEYS.search(key) or not key):
                return "Vector3(%s)" % ", ".join(fmt_num(x) for x in v)
        return "[" + ", ".join(lit(x) for x in v) + "]"
    return lit(str(v))


# ── tscn model (text-preserving) ────────────────────────────────────────────
def _split_header(line):
    """'[node name="A" groups=["x"]]' -> (kind, attrs) or None."""
    s = line.strip()
    if not (s.startswith("[") and s.endswith("]")):
        return None
    body = s[1:-1]
    m = re.match(r"(\w+)\s*", body)
    if not m:
        return None
    kind, rest = m.group(1), body[m.end():]
    attrs, i, n = {}, 0, len(rest)
    while i < n:
        while i < n and rest[i].isspace():
            i += 1
        j = i
        while j < n and rest[j] not in "= \t":
            j += 1
        key = rest[i:j]
        if not key or j >= n or rest[j] != "=":
            break
        j += 1
        start, depth, instr = j, 0, False
        while j < n:
            c = rest[j]
            if instr:
                if c == "\\":
                    j += 1
                elif c == '"':
                    instr = False
            elif c == '"':
                instr = True
            elif c in "[({":
                depth += 1
            elif c in "])}":
                depth -= 1
            elif c.isspace() and depth <= 0:
                break
            j += 1
        raw = rest[start:j]
        attrs[key] = raw[1:-1] if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"' else raw
        i = j
    return kind, attrs


class Scene:
    def __init__(self, text):
        self.nl = "\r\n" if "\r\n" in text else "\n"
        lines = text.replace("\r\n", "\n").split("\n")
        self.blocks = []
        cur = None
        for ln in lines:
            h = _split_header(ln) if ln.startswith("[") else None
            if h:
                cur = {"kind": h[0], "attrs": h[1], "header": ln, "body": []}
                self.blocks.append(cur)
            elif cur is None:
                cur = {"kind": "pre", "attrs": {}, "header": None, "body": [ln]}
                self.blocks.append(cur)
            else:
                cur["body"].append(ln)

    def text(self):
        out = []
        for b in self.blocks:
            if b["header"] is not None:
                out.append(b["header"])
            out.extend(b["body"])
        t = "\n".join(out)
        return t.replace("\n", self.nl) if self.nl != "\n" else t

    def of(self, kind):
        return [b for b in self.blocks if b["kind"] == kind]

    @staticmethod
    def key(b):
        a = b["attrs"]
        if "parent" not in a:
            return "."
        return a["name"] if a["parent"] == "." else a["parent"] + "/" + a["name"]

    def nodes(self):
        return [b for b in self.blocks if b["kind"] == "node"]

    def find(self, key):
        key = (key or ".").strip().strip("/")
        if key in ("", "root", "."):
            key = "."
        rootname = self.nodes()[0]["attrs"]["name"] if self.nodes() else ""
        if key.startswith(rootname + "/") and rootname:
            key = key[len(rootname) + 1:]
        elif key == rootname and rootname:
            key = "."
        for b in self.nodes():
            if self.key(b) == key:
                return b
        names = [self.key(b) for b in self.nodes()][:30]
        raise ToolkitError(f"no node '{key}' in the scene", "Nodes: " + ", ".join(names))

    def ext_id(self, path, typ):
        for b in self.of("ext_resource"):
            if b["attrs"].get("path") == path:
                return b["attrs"]["id"]
        n = len(self.of("ext_resource")) + 1
        eid = f"{n}_{hashlib.md5((path + str(n)).encode()).hexdigest()[:5]}"
        header = f'[ext_resource type="{typ}" path="{path}" id="{eid}"]'
        blk = {"kind": "ext_resource", "attrs": {"type": typ, "path": path, "id": eid}, "header": header, "body": []}
        idx = max([i for i, b in enumerate(self.blocks) if b["kind"] in ("gd_scene", "ext_resource")] or [0]) + 1
        self.blocks.insert(idx, blk)
        self._pad()
        self._steps()
        return eid

    def _pad(self):
        for i, b in enumerate(self.blocks[:-1]):
            if b["header"] is not None and not b["body"]:
                nxt = self.blocks[i + 1]
                if nxt["kind"] != "ext_resource" or b["kind"] != "ext_resource":
                    b["body"].append("")
            elif b["body"] and b["body"][-1].strip() != "":
                b["body"].append("")

    def _steps(self):
        head = next((b for b in self.blocks if b["kind"] == "gd_scene"), None)
        if head and "load_steps" in head["attrs"]:
            n = len(self.of("ext_resource")) + len(self.of("sub_resource")) + 1
            head["header"] = re.sub(r"load_steps=\d+", f"load_steps={n}", head["header"])
            head["attrs"]["load_steps"] = str(n)

    def descendants_end(self, key):
        """Index just after the last block belonging to node `key`'s subtree."""
        idx = None
        for i, b in enumerate(self.blocks):
            if b["kind"] != "node":
                continue
            k = self.key(b)
            if k == key or (key == "." and True) or k.startswith(key + "/"):
                idx = i
            elif idx is not None:
                pass
        return (idx if idx is not None else len(self.blocks) - 1) + 1

    def add_node(self, parent_key, name, ntype=None, props=None, groups=None, instance_path=None, script=None):
        par = self.find(parent_key)
        pk = self.key(par)
        for b in self.nodes():
            if b["attrs"].get("parent") == (pk if pk != "." else ".") and b["attrs"]["name"] == name:
                raise ToolkitError(f"'{pk}' already has a child named '{name}'")
        if instance_path:
            eid = self.ext_id(instance_path, "PackedScene")
            header = f'[node name="{name}" parent="{pk}" instance=ExtResource("{eid}")'
        else:
            header = f'[node name="{name}" type="{ntype or "Node"}" parent="{pk}"'
        if groups:
            header += " groups=[" + ", ".join(f'"{g}"' for g in groups) + "]"
        header += "]"
        body = []
        if script:
            sid = self.ext_id(script, "Script")
            body.append(f'script = ExtResource("{sid}")')
        for k, v in (props or {}).items():
            body.append(f"{k} = {lit(v, k)}")
        body.append("")
        blk = {"kind": "node", "attrs": {"name": name, "parent": pk, **({"type": ntype} if ntype else {})}, "header": header, "body": body}
        end = self._subtree_end(par)
        self.blocks.insert(end, blk)
        self._pad()
        return self.key(blk)

    def _subtree_end(self, par):
        pk = self.key(par)
        i0 = self.blocks.index(par)
        end = i0 + 1
        for i in range(i0 + 1, len(self.blocks)):
            b = self.blocks[i]
            if b["kind"] == "node":
                k = self.key(b)
                if pk == "." or k.startswith(pk + "/"):
                    end = i + 1
                else:
                    break
            elif b["kind"] in ("connection", "editable"):
                break
            else:
                end = i + 1
        return end

    def set_props(self, node, props, remove=()):
        body = node["body"]
        for k, v in props.items():
            new = f"{k} = {lit(v, k)}"
            i = next((j for j, l in enumerate(body) if re.match(rf"^{re.escape(k)}\s*=", l)), None)
            if i is None:
                at = len(body)
                while at > 0 and body[at - 1].strip() == "":
                    at -= 1
                body.insert(at, new)
            else:
                j = i + 1
                depth = _balance(body[i])
                while depth > 0 and j < len(body):
                    depth += _balance(body[j])
                    j += 1
                body[i:j] = [new]
        for k in remove:
            i = next((j for j, l in enumerate(body) if re.match(rf"^{re.escape(k)}\s*=", l)), None)
            if i is not None:
                j, depth = i + 1, _balance(body[i])
                while depth > 0 and j < len(body):
                    depth += _balance(body[j])
                    j += 1
                del body[i:j]

    def delete_node(self, key):
        node = self.find(key)
        k = self.key(node)
        if k == ".":
            raise ToolkitError("refusing to delete the root node")
        gone = [b for b in self.nodes() if self.key(b) == k or self.key(b).startswith(k + "/")]
        gone_keys = {self.key(b) for b in gone}
        removed_conn = 0
        keep = []
        for b in self.blocks:
            if b in gone:
                continue
            if b["kind"] == "connection":
                f, t = b["attrs"].get("from", "."), b["attrs"].get("to", ".")
                if f in gone_keys or t in gone_keys or any(f.startswith(g + "/") or t.startswith(g + "/") for g in gone_keys):
                    removed_conn += 1
                    continue
            keep.append(b)
        self.blocks = keep
        self._pad()
        return sorted(gone_keys), removed_conn

    def tree(self):
        rows = []
        scripts = {b["attrs"]["id"]: b["attrs"]["path"] for b in self.of("ext_resource")}
        for b in self.nodes():
            k = self.key(b)
            depth = 0 if k == "." else k.count("/") + 1
            row = {"path": k, "name": b["attrs"]["name"], "type": b["attrs"].get("type"), "depth": depth}
            if "instance" in b["attrs"]:
                m = re.search(r'ExtResource\("([^"]+)"\)', b["attrs"]["instance"])
                row["instance"] = scripts.get(m.group(1)) if m else None
            for l in b["body"]:
                m = re.match(r'^script\s*=\s*ExtResource\("([^"]+)"\)', l)
                if m:
                    row["script"] = scripts.get(m.group(1))
            if "groups" in b["attrs"]:
                row["groups"] = re.findall(r'"([^"]+)"', b["attrs"]["groups"])
            rows.append(row)
        return rows


def _balance(line):
    d, instr, i = 0, False, 0
    while i < len(line):
        c = line[i]
        if instr:
            if c == "\\":
                i += 1
            elif c == '"':
                instr = False
        elif c == '"':
            instr = True
        elif c in "[{(":
            d += 1
        elif c in "]})":
            d -= 1
        i += 1
    return d


# ── project.godot ───────────────────────────────────────────────────────────
def parse_project(text):
    """-> list of entries {section,key,raw,start,end} (line indexes, end exclusive)."""
    lines = text.replace("\r\n", "\n").split("\n")
    out, sec, i = [], "", 0
    while i < len(lines):
        ln = lines[i]
        m = re.match(r"^\[([^\]]+)\]\s*$", ln)
        if m:
            sec = m.group(1)
        else:
            km = re.match(r"^([^=;\s][^=]*?)=(.*)$", ln)
            if km:
                j, depth = i + 1, _balance(km.group(2))
                while depth > 0 and j < len(lines):
                    depth += _balance(lines[j])
                    j += 1
                out.append({"section": sec, "key": km.group(1).strip(), "raw": "\n".join([km.group(2)] + lines[i + 1:j]), "start": i, "end": j})
                i = j
                continue
        i += 1
    return out, lines


def get_setting(text, path):
    sec, _, key = path.rpartition("/")
    entries, _ = parse_project(text)
    for e in entries:
        if (e["section"] + "/" + e["key"] if e["section"] else e["key"]) == path or (e["section"] == sec and e["key"] == key):
            return e["raw"]
    return None


def set_setting(text, section, key, raw):
    entries, lines = parse_project(text)
    nl = "\r\n" if "\r\n" in text else "\n"
    for e in entries:
        if e["section"] == section and e["key"] == key:
            lines[e["start"]:e["end"]] = [f"{key}={raw}"]
            return nl.join(lines)
    # append to the section
    sec_start = next((i for i, l in enumerate(lines) if l.strip() == f"[{section}]"), None)
    if sec_start is None:
        while lines and lines[-1].strip() == "":
            lines.pop()
        lines += ["", f"[{section}]", "", f"{key}={raw}", ""]
        return nl.join(lines)
    j = sec_start + 1
    last = sec_start
    while j < len(lines) and not re.match(r"^\[[^\]]+\]\s*$", lines[j]):
        if lines[j].strip():
            last = j
        j += 1
    lines.insert(last + 1, f"{key}={raw}")
    return nl.join(lines)


def remove_setting(text, section, key):
    entries, lines = parse_project(text)
    for e in entries:
        if e["section"] == section and e["key"] == key:
            del lines[e["start"]:e["end"]]
            return ("\r\n" if "\r\n" in text else "\n").join(lines), True
    return text, False


def _split_path(path):
    path = str(path).strip().strip("/")
    sec, _, key = path.rpartition("/")
    if not sec:
        return "", key
    # Godot nests keys: section = first part, key = the rest ("display/window/size/viewport_width" -> display / window/size/viewport_width)
    parts = path.split("/")
    return parts[0], "/".join(parts[1:])


@tool(G, "ms_godot_project_overview",
      "Read a Godot project from disk (editor can be closed): name, Godot version/features, main scene, autoloads, input actions, window size, layer names, "
      "file counts (scenes/scripts/resources/assets), addons and export presets - plus whether a Godot executable was found for headless checks.",
      {}, local=True)
def project_overview(args, ctx):
    p = _proj(args, ctx)
    text = _read(os.path.join(p, "project.godot"))
    entries, _ = parse_project(text)
    by = {(e["section"], e["key"]): e["raw"] for e in entries}
    info = {"project_path": p, "name": (by.get(("application", "config/name")) or "").strip('"'),
            "main_scene": (by.get(("application", "run/main_scene")) or "").strip('"'),
            "features": re.findall(r'"([^"]+)"', by.get(("application", "config/features")) or ""),
            "config_version": next((e["raw"] for e in entries if e["key"] == "config_version"), None)}
    info["autoloads"] = {e["key"]: e["raw"].strip('"') for e in entries if e["section"] == "autoload"}
    info["input_actions"] = [e["key"] for e in entries if e["section"] == "input"]
    info["window"] = {"width": by.get(("display", "window/size/viewport_width")), "height": by.get(("display", "window/size/viewport_height")),
                      "stretch": (by.get(("display", "window/stretch/mode")) or "").strip('"')}
    info["layer_names"] = {e["key"]: e["raw"].strip('"') for e in entries if e["section"] == "layer_names"}
    counts = {}
    for dp, dn, fn in os.walk(p):
        dn[:] = [d for d in dn if d not in (".git", ".godot", ".import", "node_modules")]
        for f in fn:
            ext = os.path.splitext(f)[1].lower()
            if ext in (".tscn", ".scn"):
                k = "scenes"
            elif ext == ".gd":
                k = "scripts"
            elif ext in (".tres", ".res"):
                k = "resources"
            elif ext in (".png", ".jpg", ".jpeg", ".webp", ".svg", ".ogg", ".wav", ".mp3", ".glb", ".gltf", ".fbx", ".obj"):
                k = "assets"
            else:
                continue
            counts[k] = counts.get(k, 0) + 1
    info["file_counts"] = counts
    addons = os.path.join(p, "addons")
    info["addons"] = sorted(os.listdir(addons)) if os.path.isdir(addons) else []
    ep = os.path.join(p, "export_presets.cfg")
    info["export_presets"] = re.findall(r'^name="([^"]+)"', _read(ep), re.M) if os.path.isfile(ep) else []
    info["godot_executable"] = find_exe()
    return info


# ── scenes ──────────────────────────────────────────────────────────────────
def _scene_path(proj, args, key="scene_path"):
    sp = str(args.get(key) or "").strip()
    if not sp:
        raise ToolkitError(f"`{key}` is required")
    if not sp.endswith((".tscn", ".scn")):
        sp += ".tscn"
    return _abs(proj, sp)


@tool(G, "ms_godot_scene_tree", "Show a scene's node tree (names, types, scripts, instanced scenes, groups) parsed from the .tscn file. Read-only.",
      {"scene_path": SCENE}, ["scene_path"], local=True)
def scene_tree(args, ctx):
    p = _proj(args, ctx)
    full = _scene_path(p, args)
    if not os.path.isfile(full):
        raise ToolkitError(f"scene not found: {_res(p, full)}")
    sc = Scene(_read(full))
    rows = sc.tree()
    return {"scene": _res(p, full), "node_count": len(rows), "nodes": rows,
            "connections": [b["attrs"] for b in sc.of("connection")],
            "text_tree": "\n".join("  " * r["depth"] + f"{r['name']} ({r.get('type') or 'instance'})" + (f" [{r['script']}]" if r.get("script") else "") for r in rows)}


def _build_nodes(sc, parent_key, specs, created):
    for spec in specs:
        spec = as_dict(spec)
        name = str(spec.get("name") or spec.get("type") or "Node")
        key = sc.add_node(parent_key, name, spec.get("type") or ("Node" if not spec.get("instance") else None), as_dict(spec.get("properties")),
                          [str(g) for g in as_list(spec.get("groups"))], spec.get("instance"), spec.get("script"))
        created.append(key)
        _build_nodes(sc, key, as_list(spec.get("children")), created)


@tool(G, "ms_godot_scene_create",
      "Create a .tscn scene from a JSON spec: root type/name plus nested `children` [{name,type,properties,script,groups,children,instance}]. Property values use Godot "
      "literals or the JSON conveniences ({x,y}->Vector2, '#hex'->Color). Refuses to overwrite unless overwrite=true.",
      {"scene_path": SCENE, "root_type": {"type": "string", "description": "Root node class (Node2D, Node3D, Control, CharacterBody2D...)."}, "root_name": {"type": "string"},
       "root_properties": PROPS, "root_script": {"type": "string", "description": "res:// path of a script to attach to the root."},
       "children": {"type": "array", "items": {"type": "object"}}, "overwrite": {"type": "boolean"}}, ["scene_path", "root_type"], writes=True, local=True)
def scene_create(args, ctx):
    p = _proj(args, ctx)
    full = _scene_path(p, args)
    if os.path.exists(full) and not boolean(args.get("overwrite"), False):
        raise ToolkitError(f"{_res(p, full)} already exists", "Pass overwrite=true or choose another path.")
    rname = str(args.get("root_name") or os.path.splitext(os.path.basename(full))[0].replace(" ", "_") or "Root")
    head = f'[gd_scene load_steps=1 format=3]\n\n[node name="{rname}" type="{args.get("root_type")}"]\n'
    sc = Scene(head)
    root = sc.nodes()[0]
    props = as_dict(args.get("root_properties"))
    if args.get("root_script"):
        sid = sc.ext_id(str(args["root_script"]), "Script")
        root["body"].insert(0, f'script = ExtResource("{sid}")')
    if props:
        sc.set_props(root, props)
    created = []
    _build_nodes(sc, ".", as_list(args.get("children")), created)
    sc._pad()
    sc._steps()
    text = sc.text().rstrip("\n") + "\n"
    wrote = _write(full, text, args)
    return {"scene": _res(p, full), "written": wrote, "nodes": [rname] + created, **({"preview": text[:3000]} if args.get("dry_run") else {})}


@tool(G, "ms_godot_node_add",
      "Add a node (or an instanced scene via `instance`) to an existing .tscn under `parent` (node path, '.' for the root), with properties, groups and an optional script.",
      {"scene_path": SCENE, "parent": {"type": "string", "description": "Parent node path relative to the scene root ('.' = root)."}, "name": {"type": "string"},
       "type": {"type": "string"}, "instance": {"type": "string", "description": "res:// path of a scene to instance instead of `type`."},
       "properties": PROPS, "groups": {"type": "array", "items": {"type": "string"}}, "script": {"type": "string"}}, ["scene_path", "name"], writes=True, local=True)
def node_add(args, ctx):
    p = _proj(args, ctx)
    full = _scene_path(p, args)
    sc = Scene(_read(full))
    if not args.get("type") and not args.get("instance"):
        raise ToolkitError("give `type` (or `instance`)")
    key = sc.add_node(args.get("parent") or ".", str(args["name"]), args.get("type"), as_dict(args.get("properties")), [str(g) for g in as_list(args.get("groups"))],
                      args.get("instance"), args.get("script"))
    sc._steps()
    wrote = _write(full, sc.text(), args)
    return {"scene": _res(p, full), "added": key, "written": wrote}


@tool(G, "ms_godot_node_edit",
      "Edit an existing node in a .tscn: set `properties`, `remove_properties`, attach a `script`, change groups, rename, or `delete` the node (and its subtree and signal connections).",
      {"scene_path": SCENE, "node": {"type": "string", "description": "Node path relative to the root ('.' = root)."}, "properties": PROPS,
       "remove_properties": {"type": "array", "items": {"type": "string"}}, "script": {"type": "string"}, "groups": {"type": "array", "items": {"type": "string"}},
       "new_name": {"type": "string"}, "delete": {"type": "boolean"}}, ["scene_path", "node"], writes=True, local=True)
def node_edit(args, ctx):
    p = _proj(args, ctx)
    full = _scene_path(p, args)
    sc = Scene(_read(full))
    out = {"scene": _res(p, full)}
    if boolean(args.get("delete"), False):
        gone, conns = sc.delete_node(args.get("node"))
        out.update(deleted=gone, connections_removed=conns)
    else:
        node = sc.find(args.get("node"))
        props = as_dict(args.get("properties"))
        if args.get("script"):
            sid = sc.ext_id(str(args["script"]), "Script")
            props = dict({"script": f'ExtResource("{sid}")'}, **props)
        sc.set_props(node, props, [str(x) for x in as_list(args.get("remove_properties"))])
        if args.get("groups") is not None:
            gl = [str(g) for g in as_list(args.get("groups"))]
            h = re.sub(r"\s+groups=\[[^\]]*\]", "", node["header"])
            if gl:
                h = h[:-1] + " groups=[" + ", ".join(f'"{g}"' for g in gl) + "]]"
            node["header"] = h
        if args.get("new_name"):
            old = sc.key(node)
            new = str(args["new_name"])
            if old == ".":
                node["header"] = re.sub(r'name="[^"]*"', f'name="{new}"', node["header"], count=1)
            else:
                par, _, base = old.rpartition("/")
                node["header"] = re.sub(r'name="[^"]*"', f'name="{new}"', node["header"], count=1)
                node["attrs"]["name"] = new
                newkey = (par + "/" if par else "") + new
                for b in sc.blocks:
                    if b["kind"] == "node" and b is not node and b["attrs"].get("parent", "").startswith(old):
                        b["attrs"]["parent"] = newkey + b["attrs"]["parent"][len(old):]
                        b["header"] = re.sub(r'parent="[^"]*"', f'parent="{b["attrs"]["parent"]}"', b["header"], count=1)
                    if b["kind"] == "connection":
                        for fld in ("from", "to"):
                            v = b["attrs"].get(fld, "")
                            if v == old or v.startswith(old + "/"):
                                nv = newkey + v[len(old):]
                                b["attrs"][fld] = nv
                                b["header"] = re.sub(rf'{fld}="[^"]*"', f'{fld}="{nv}"', b["header"], count=1)
        out["edited"] = args.get("node")
    sc._steps()
    out["written"] = _write(full, sc.text(), args)
    return out


@tool(G, "ms_godot_signals",
      "Signal connections stored in a scene: action=list|connect|disconnect. connect adds [connection signal from to method] so the editor wires it on load.",
      {"scene_path": SCENE, "action": {"type": "string", "enum": ["list", "connect", "disconnect"]}, "signal": {"type": "string"}, "from_node": {"type": "string"},
       "to_node": {"type": "string"}, "method": {"type": "string"}}, ["scene_path", "action"], writes=True, local=True)
def signals(args, ctx):
    p = _proj(args, ctx)
    full = _scene_path(p, args)
    sc = Scene(_read(full))
    act = str(args.get("action") or "list").lower()
    if act in ("connect", "disconnect"):
        for need in ("signal", "from_node", "to_node", "method"):
            if not args.get(need):
                raise ToolkitError(f"`{need}` is required")
        f, t = sc.key(sc.find(args["from_node"])), sc.key(sc.find(args["to_node"]))
        hdr = f'[connection signal="{args["signal"]}" from="{f}" to="{t}" method="{args["method"]}"]'
        existing = [b for b in sc.of("connection") if b["attrs"].get("signal") == args["signal"] and b["attrs"].get("from") == f and b["attrs"].get("to") == t and b["attrs"].get("method") == args["method"]]
        if act == "connect" and not existing:
            sc.blocks.append({"kind": "connection", "attrs": {"signal": args["signal"], "from": f, "to": t, "method": args["method"]}, "header": hdr, "body": [""]})
        if act == "disconnect":
            sc.blocks = [b for b in sc.blocks if b not in existing]
        sc._pad()
        _write(full, sc.text().rstrip("\n") + "\n", args)
    return {"scene": _res(p, full), "connections": [b["attrs"] for b in sc.of("connection")]}


# ── scripts ─────────────────────────────────────────────────────────────────
_TEMPLATES = {
    "empty": "extends {base}\n\n\nfunc _ready() -> void:\n\tpass\n",
    "platformer_2d": '''extends CharacterBody2D

@export var speed: float = 220.0
@export var jump_velocity: float = -420.0
@export var coyote_time: float = 0.10
var _gravity: float = ProjectSettings.get_setting("physics/2d/default_gravity")
var _coyote := 0.0


func _physics_process(delta: float) -> void:
	if is_on_floor():
		_coyote = coyote_time
	else:
		_coyote -= delta
		velocity.y += _gravity * delta
	if Input.is_action_just_pressed("jump") and _coyote > 0.0:
		velocity.y = jump_velocity
		_coyote = 0.0
	var dir := Input.get_axis("move_left", "move_right")
	velocity.x = move_toward(velocity.x, dir * speed, speed * 8.0 * delta)
	move_and_slide()
''',
    "topdown_2d": '''extends CharacterBody2D

@export var speed: float = 180.0


func _physics_process(_delta: float) -> void:
	var dir := Input.get_vector("move_left", "move_right", "move_up", "move_down")
	velocity = dir * speed
	move_and_slide()
''',
    "fps_3d": '''extends CharacterBody3D

@export var speed: float = 5.0
@export var jump_velocity: float = 4.5
@export var mouse_sensitivity: float = 0.002
@onready var head: Node3D = $Head
var _gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")


func _ready() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-event.relative.x * mouse_sensitivity)
		head.rotate_x(-event.relative.y * mouse_sensitivity)
		head.rotation.x = clamp(head.rotation.x, deg_to_rad(-89), deg_to_rad(89))
	if event.is_action_pressed("ui_cancel"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func _physics_process(delta: float) -> void:
	if not is_on_floor():
		velocity.y -= _gravity * delta
	elif Input.is_action_just_pressed("jump"):
		velocity.y = jump_velocity
	var input := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var dir := (transform.basis * Vector3(input.x, 0, input.y)).normalized()
	velocity.x = dir.x * speed if dir else move_toward(velocity.x, 0, speed)
	velocity.z = dir.z * speed if dir else move_toward(velocity.z, 0, speed)
	move_and_slide()
''',
    "health_component": '''class_name HealthComponent
extends Node

signal health_changed(current: int, maximum: int)
signal died

@export var max_health: int = 100
var health: int = max_health


func _ready() -> void:
	health = max_health


func damage(amount: int) -> void:
	health = clampi(health - amount, 0, max_health)
	health_changed.emit(health, max_health)
	if health == 0:
		died.emit()


func heal(amount: int) -> void:
	health = clampi(health + amount, 0, max_health)
	health_changed.emit(health, max_health)
''',
    "state_machine": '''class_name StateMachine
extends Node

signal state_changed(from_state: StringName, to_state: StringName)

@export var initial_state: Node
var current: Node


func _ready() -> void:
	await owner.ready
	if initial_state:
		transition(initial_state.name)


func _process(delta: float) -> void:
	if current and current.has_method("update"):
		current.update(delta)


func _physics_process(delta: float) -> void:
	if current and current.has_method("physics_update"):
		current.physics_update(delta)


func transition(state_name: StringName) -> void:
	var next := get_node_or_null(NodePath(state_name))
	if next == null or next == current:
		return
	var prev := current.name if current else &""
	if current and current.has_method("exit"):
		current.exit()
	current = next
	if current.has_method("enter"):
		current.enter()
	state_changed.emit(prev, state_name)
''',
    "game_manager_autoload": '''extends Node
## Autoload singleton: add with ms_godot_autoload (name GameManager).

signal score_changed(score: int)
signal game_over

var score: int = 0
var paused: bool = false


func add_score(points: int) -> void:
	score += points
	score_changed.emit(score)


func reset() -> void:
	score = 0
	score_changed.emit(score)


func end_game() -> void:
	game_over.emit()
	get_tree().paused = true
''',
    "camera_follow_2d": '''extends Camera2D

@export var target: Node2D
@export var smoothing: float = 8.0


func _process(delta: float) -> void:
	if target:
		global_position = global_position.lerp(target.global_position, 1.0 - exp(-smoothing * delta))
''',
    "ui_menu": '''extends Control

@export_file("*.tscn") var game_scene: String


func _ready() -> void:
	$VBoxContainer/Start.pressed.connect(_on_start)
	$VBoxContainer/Quit.pressed.connect(get_tree().quit)
	$VBoxContainer/Start.grab_focus()


func _on_start() -> void:
	if game_scene != "":
		get_tree().change_scene_to_file(game_scene)
''',
    "spawner": '''extends Node2D

@export var scene: PackedScene
@export var interval: float = 2.0
@export var max_alive: int = 10
var _timer := 0.0


func _process(delta: float) -> void:
	_timer += delta
	if _timer >= interval and get_child_count() < max_alive and scene:
		_timer = 0.0
		var inst := scene.instantiate()
		add_child(inst)
		inst.global_position = global_position
''',
}


@tool(G, "ms_godot_script_create",
      "Create a GDScript (Godot 4) file from a template - " + ", ".join(sorted(_TEMPLATES)) + " - or from your own `lines`/`source`. Optionally attach it to a node in a scene and "
      "run a headless syntax check when a Godot executable is available.",
      {"path": {"type": "string", "description": "res://scripts/Player.gd"}, "template": {"type": "string", "enum": sorted(_TEMPLATES)}, "extends": {"type": "string"},
       "class_name": {"type": "string"}, "source": {"type": "string"}, "lines": {"type": "array", "items": {"type": "string"}},
       "attach_scene": SCENE, "attach_node": {"type": "string"}, "overwrite": {"type": "boolean"}}, ["path"], writes=True, local=True)
def script_create(args, ctx):
    p = _proj(args, ctx)
    path = str(args.get("path") or "")
    if not path.endswith(".gd"):
        path += ".gd"
    full = _abs(p, path)
    if os.path.exists(full) and not boolean(args.get("overwrite"), False):
        raise ToolkitError(f"{_res(p, full)} already exists", "Pass overwrite=true, or use ms_godot_script_edit.")
    if args.get("lines"):
        src = "\n".join(str(x) for x in as_list(args["lines"]))
    elif args.get("source"):
        src = str(args["source"])
    else:
        src = _TEMPLATES.get(str(args.get("template") or "empty"), _TEMPLATES["empty"]).replace("{base}", str(args.get("extends") or "Node"))
    if args.get("class_name") and not re.search(r"^class_name\s", src, re.M):
        src = f"class_name {args['class_name']}\n" + src
    if not src.endswith("\n"):
        src += "\n"
    out = {"script": _res(p, full), "written": _write(full, src, args), "lines": src.count("\n")}
    if args.get("attach_scene"):
        sp = _scene_path(p, args, "attach_scene")
        sc = Scene(_read(sp))
        node = sc.find(args.get("attach_node") or ".")
        sid = sc.ext_id(_res(p, full), "Script")
        sc.set_props(node, {"script": f'ExtResource("{sid}")'})
        sc._steps()
        _write(sp, sc.text(), args)
        out["attached_to"] = f"{_res(p, sp)}::{args.get('attach_node') or '.'}"
    if not args.get("dry_run"):
        out["static_check"] = _static_gd(src)
    return out


_GD3 = [(r"\byield\s*\(", "yield() is Godot 3 - use await"), (r"^\s*export\s*\(|^\s*export\s+var", "`export var` is Godot 3 - use @export var"),
        (r"^\s*onready\s+var", "`onready var` is Godot 3 - use @onready var"), (r"\.connect\(\s*\"[^\"]+\"\s*,\s*(self|[A-Za-z_]+)\s*,\s*\"", "connect(signal, target, \"method\") is Godot 3 - use signal.connect(callable)"),
        (r"\bKinematicBody", "KinematicBody* is Godot 3 - use CharacterBody2D/3D"), (r"\bsetget\b", "setget is Godot 3 - use property setters (set/get blocks)"),
        (r"\btool\b\s*$", "`tool` is Godot 3 - use @tool"), (r"\bmaster\s+func|\bpuppet\s+func|\bremote\s+func", "master/puppet/remote are Godot 3 - use @rpc")]


def _static_gd(src):
    issues = []
    lines = src.split("\n")
    tabs = sum(1 for l in lines if l.startswith("\t"))
    spaces = sum(1 for l in lines if l.startswith("    "))
    if tabs and spaces:
        issues.append("mixed tab and space indentation (Godot requires one style per file)")
    if not re.search(r"^\s*extends\b", src, re.M) and not re.search(r"^class_name\b", src, re.M):
        issues.append("no `extends` line - the script extends RefCounted by default")
    for pat, msg in _GD3:
        if re.search(pat, src, re.M):
            issues.append(msg)
    if _balance(src.replace("#", "\n#")) not in (0,) and False:
        pass
    return {"ok": not issues, "issues": issues}


@tool(G, "ms_godot_script_edit",
      "Edit a GDScript file: `edits` run in order - {op:'replace_text', find, replace_with, count?}, {op:'insert_after', find, text}, {op:'insert_before', find, text}, "
      "{op:'append', text}, {op:'prepend', text}, {op:'replace_function', name, body} (body includes the whole `func` block). Fails atomically (nothing written) if any edit does not match.",
      {"path": {"type": "string"}, "edits": {"type": "array", "items": {"type": "object"}}}, ["path", "edits"], writes=True, local=True)
def script_edit(args, ctx):
    p = _proj(args, ctx)
    full = _abs(p, args.get("path"))
    if not os.path.isfile(full):
        raise ToolkitError(f"not found: {_res(p, full)}")
    src = _read(full).replace("\r\n", "\n")
    before = src
    applied = []
    for i, e in enumerate(as_list(args.get("edits"))):
        e = as_dict(e)
        op = str(e.get("op") or "replace_text").lower()
        if op == "append":
            src = src.rstrip("\n") + "\n" + str(e.get("text", "")) + "\n"
        elif op == "prepend":
            src = str(e.get("text", "")) + "\n" + src
        elif op in ("replace_text", "insert_after", "insert_before"):
            find = str(e.get("find") or "")
            if not find or find not in src:
                raise ToolkitError(f"edit {i}: text not found: {find[:80]!r}", "Read the file again (ms_godot_script_read) and copy the text exactly, including tabs.")
            if op == "replace_text":
                src = src.replace(find, str(e.get("replace_with", "")), int(e.get("count") or -1))
            elif op == "insert_after":
                src = src.replace(find, find + str(e.get("text", "")), 1)
            else:
                src = src.replace(find, str(e.get("text", "")) + find, 1)
        elif op == "replace_function":
            name = re.escape(str(e.get("name") or ""))
            m = re.search(rf"^(static\s+)?func\s+{name}\s*\(.*?(?=^\S|\Z)", src, re.M | re.S)
            if not m:
                raise ToolkitError(f"edit {i}: function '{e.get('name')}' not found")
            src = src[:m.start()] + str(e.get("body", "")).rstrip("\n") + "\n\n" + src[m.end():].lstrip("\n")
        else:
            raise ToolkitError(f"edit {i}: unknown op '{op}'")
        applied.append(op)
    src = src.rstrip("\n") + "\n"
    out = {"script": _res(p, full), "applied": applied, "changed": src != before, "written": _write(full, src, args), "static_check": _static_gd(src)}
    return out


@tool(G, "ms_godot_script_read", "Read a GDScript/scene/resource text file (with line numbers) so edits can be exact. Read-only.",
      {"path": {"type": "string"}, "start_line": {"type": "integer", "minimum": 1}, "end_line": {"type": "integer", "minimum": 1}}, ["path"], local=True)
def script_read(args, ctx):
    p = _proj(args, ctx)
    full = _abs(p, args.get("path"))
    if not os.path.isfile(full):
        raise ToolkitError(f"not found: {_res(p, full)}")
    lines = _read(full).replace("\r\n", "\n").split("\n")
    a, b = num(args.get("start_line"), 1, 1, None, True), num(args.get("end_line"), len(lines), 1, None, True)
    return {"path": _res(p, full), "total_lines": len(lines), "text": "\n".join(f"{i}: {l}" for i, l in enumerate(lines[a - 1:b], a))[:60000]}


@tool(G, "ms_godot_script_check",
      "Check GDScript files: static Godot-3-vs-4 and indentation issues for every .gd under a folder (or one file), plus a real headless parse when a Godot executable is "
      "found. Read-only.",
      {"path": {"type": "string", "description": "A .gd file or a folder (default res://)."}, "headless": {"type": "boolean"}}, [], local=True)
def script_check(args, ctx):
    p = _proj(args, ctx)
    target = _abs(p, args.get("path") or "")
    files = [target] if os.path.isfile(target) else [os.path.join(dp, f) for dp, dn, fn in os.walk(target) if not any(x in dp for x in (".godot", ".git", "addons")) for f in fn if f.endswith(".gd")]
    rows, bad = [], 0
    for f in files[:400]:
        res = _static_gd(_read(f))
        if not res["ok"]:
            bad += 1
            rows.append({"file": _res(p, f), "issues": res["issues"]})
    out = {"scripts_checked": len(files), "scripts_with_issues": bad, "files": rows}
    exe = find_exe()
    if exe and boolean(args.get("headless"), True) and files:
        errs = []
        for f in files[:25]:
            try:
                r = subprocess.run([exe, "--headless", "--path", p, "--check-only", "--script", _res(p, f)], capture_output=True, text=True, timeout=45)
                txt = (r.stdout + r.stderr)
                if r.returncode != 0 or re.search(r"SCRIPT ERROR|Parse Error", txt):
                    errs.append({"file": _res(p, f), "output": txt[-600:]})
            except Exception as exc:
                errs.append({"file": _res(p, f), "output": f"{type(exc).__name__}: {exc}"})
                break
        out["headless_parse"] = {"executable": exe, "errors": errs, "ok": not errs}
    else:
        out["headless_parse"] = {"executable": exe, "skipped": "no Godot executable found - set GODOT_PATH for real parse checks" if not exe else "disabled"}
    out["verdict"] = "clean" if not bad and not (out["headless_parse"].get("errors")) else "issues found"
    return out


# ── project settings ────────────────────────────────────────────────────────
@tool(G, "ms_godot_project_setting",
      "Read or write any project.godot setting by path (e.g. display/window/size/viewport_width, application/run/main_scene, rendering/renderer/rendering_method). "
      "action=get|set|remove. Values use Godot literals or plain JSON.",
      {"action": {"type": "string", "enum": ["get", "set", "remove"]}, "setting": {"type": "string", "description": "section/key path."}, "value": {"description": "New value."}}, ["action", "setting"], writes=True, local=True)
def project_setting(args, ctx):
    p = _proj(args, ctx)
    f = os.path.join(p, "project.godot")
    text = _read(f)
    act = str(args.get("action") or "get").lower()
    path = str(args.get("setting") or "").strip()
    if act == "get":
        return {"setting": path, "value": get_setting(text, path)}
    sec, key = _split_path(path)
    if not key:
        raise ToolkitError("setting must look like section/key, e.g. display/window/size/viewport_width")
    if act == "remove":
        new, hit = remove_setting(text, sec, key)
        return {"setting": path, "removed": hit, "written": _write(f, new, args) if hit else False}
    if args.get("value") is None:
        raise ToolkitError("set needs `value`")
    raw = lit(args.get("value"), key)
    if path == "application/run/main_scene" and isinstance(args.get("value"), str) and not str(args["value"]).startswith("res://"):
        raw = lit("res://" + str(args["value"]).lstrip("/"))
    new = set_setting(text, sec, key, raw)
    return {"setting": path, "value": raw, "written": _write(f, new, args)}


@tool(G, "ms_godot_autoload", "Manage autoload singletons: action=list|add|remove. add registers `name` -> script/scene path (enabled with the * prefix).",
      {"action": {"type": "string", "enum": ["list", "add", "remove"]}, "name": {"type": "string"}, "path": {"type": "string"}, "singleton": {"type": "boolean"}}, ["action"], writes=True, local=True)
def autoload(args, ctx):
    p = _proj(args, ctx)
    f = os.path.join(p, "project.godot")
    text = _read(f)
    act = str(args.get("action") or "list").lower()
    if act == "add":
        if not args.get("name") or not args.get("path"):
            raise ToolkitError("add needs `name` and `path`")
        res = str(args["path"]) if str(args["path"]).startswith("res://") else "res://" + str(args["path"]).lstrip("/")
        if not os.path.exists(_abs(p, res)):
            raise ToolkitError(f"{res} does not exist yet", "Create the script/scene first.")
        text = set_setting(text, "autoload", str(args["name"]), '"' + ("*" if boolean(args.get("singleton"), True) else "") + res + '"')
        _write(f, text, args)
    elif act == "remove":
        text, _ = remove_setting(text, "autoload", str(args.get("name") or ""))
        _write(f, text, args)
    entries, _l = parse_project(text)
    return {"autoloads": {e["key"]: e["raw"].strip('"') for e in entries if e["section"] == "autoload"}}


_KEYS = {"space": 32, "enter": 4194309, "return": 4194309, "escape": 4194305, "esc": 4194305, "tab": 4194306, "backspace": 4194308, "left": 4194319, "up": 4194320,
         "right": 4194321, "down": 4194322, "shift": 4194325, "ctrl": 4194326, "control": 4194326, "alt": 4194328, "delete": 4194312, "home": 4194317, "end": 4194318}
for _i in range(1, 13):
    _KEYS[f"f{_i}"] = 4194331 + _i
_PAD = {"a": 0, "b": 1, "x": 2, "y": 3, "back": 4, "start": 6, "lb": 9, "rb": 10, "dpad_up": 11, "dpad_down": 12, "dpad_left": 13, "dpad_right": 14}


def _key_event(name):
    k = name.strip().lower()
    if k.startswith("mouse_"):
        btn = {"left": 1, "right": 2, "middle": 3}.get(k[6:], 1)
        return f'Object(InputEventMouseButton,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"button_mask":0,"position":Vector2(0, 0),"global_position":Vector2(0, 0),"factor":1.0,"button_index":{btn},"canceled":false,"pressed":false,"double_click":false,"script":null)'
    if k.startswith("pad_"):
        idx = _PAD.get(k[4:])
        if idx is None:
            raise ToolkitError(f"unknown gamepad button '{name}'", "pad_a, pad_b, pad_x, pad_y, pad_start, pad_back, pad_lb, pad_rb, pad_dpad_up/down/left/right")
        return f'Object(InputEventJoypadButton,"resource_local_to_scene":false,"resource_name":"","device":-1,"button_index":{idx},"pressure":0.0,"pressed":false,"script":null)'
    if k in _KEYS:
        code = _KEYS[k]
    elif len(k) == 1 and k.isalpha():
        code = ord(k.upper())
    elif len(k) == 1 and k.isdigit():
        code = ord(k)
    else:
        raise ToolkitError(f"unknown key '{name}'", "Use letters, digits, space, enter, escape, tab, arrows (left/up/right/down), shift, ctrl, alt, f1-f12, mouse_left/right/middle, pad_a/b/x/y.")
    return f'Object(InputEventKey,"resource_local_to_scene":false,"resource_name":"","device":-1,"window_id":0,"alt_pressed":false,"shift_pressed":false,"ctrl_pressed":false,"meta_pressed":false,"pressed":false,"keycode":0,"physical_keycode":{code},"key_label":0,"unicode":0,"echo":false,"script":null)'


@tool(G, "ms_godot_input_map",
      "Input actions in project.godot: action=list|set|remove. set defines an action with `keys` (w, space, left, shift, f5, mouse_left, pad_a ...) and deadzone - works "
      "for keyboard, mouse and gamepad buttons. Existing actions are replaced.",
      {"action": {"type": "string", "enum": ["list", "set", "remove"]}, "name": {"type": "string"}, "keys": {"type": "array", "items": {"type": "string"}}, "deadzone": {"type": "number", "minimum": 0, "maximum": 1},
       "actions": {"type": "array", "items": {"type": "object"}, "description": "Batch for set: [{name, keys, deadzone}]."}}, ["action"], writes=True, local=True)
def input_map(args, ctx):
    p = _proj(args, ctx)
    f = os.path.join(p, "project.godot")
    text = _read(f)
    act = str(args.get("action") or "list").lower()
    if act == "set":
        batch = [as_dict(x) for x in as_list(args.get("actions"))] or [{"name": args.get("name"), "keys": args.get("keys"), "deadzone": args.get("deadzone")}]
        for b in batch:
            if not b.get("name") or not as_list(b.get("keys")):
                raise ToolkitError("each action needs `name` and `keys`")
            events = ", ".join(_key_event(str(k)) for k in as_list(b["keys"]))
            raw = '{\n"deadzone": %s,\n"events": [%s]\n}' % (fmt_num(num(b.get("deadzone"), 0.5, 0, 1)), events)
            text = set_setting(text, "input", str(b["name"]), raw)
        _write(f, text, args)
    elif act == "remove":
        text, hit = remove_setting(text, "input", str(args.get("name") or ""))
        _write(f, text, args)
    entries, _l = parse_project(text)
    acts = {}
    for e in entries:
        if e["section"] == "input":
            acts[e["key"]] = {"keycodes": [int(x) for x in re.findall(r'"physical_keycode":(\d+)', e["raw"]) if int(x)], "mouse_buttons": re.findall(r'"button_index":(\d+)', e["raw"]) if "MouseButton" in e["raw"] else [],
                              "joypad": "InputEventJoypadButton" in e["raw"]}
    return {"actions": acts}


@tool(G, "ms_godot_layer_names", "Name physics/render/navigation layers (project.godot [layer_names]): kind=2d_physics|3d_physics|2d_render|3d_render|2d_navigation|3d_navigation|avoidance, names = {1:'Player',2:'Enemy'}.",
      {"kind": {"type": "string", "enum": ["2d_physics", "3d_physics", "2d_render", "3d_render", "2d_navigation", "3d_navigation", "avoidance"]}, "names": {"type": "object"}}, ["kind", "names"], writes=True, local=True)
def layer_names(args, ctx):
    p = _proj(args, ctx)
    f = os.path.join(p, "project.godot")
    text = _read(f)
    kind = str(args.get("kind") or "")
    names = as_dict(args.get("names"))
    if not names:
        raise ToolkitError("`names` must be an object like {\"1\": \"Player\"}")
    for k, v in names.items():
        n = int(k)
        if not 1 <= n <= 32:
            raise ToolkitError("layer numbers are 1-32")
        text = set_setting(text, "layer_names", f"{kind}/layer_{n}", lit(str(v)))
    return {"kind": kind, "set": names, "written": _write(f, text, args)}


# ── resources & files ───────────────────────────────────────────────────────
@tool(G, "ms_godot_resource_create",
      "Create a .tres resource of any type (StandardMaterial3D, ORMMaterial3D, Gradient, LabelSettings, Theme, custom Resource script, ...) with typed properties; a script-backed resource can reference `script`.",
      {"path": {"type": "string", "description": "res://materials/Red.tres"}, "type": {"type": "string"}, "properties": PROPS, "script": {"type": "string"}, "overwrite": {"type": "boolean"}}, ["path", "type"], writes=True, local=True)
def resource_create(args, ctx):
    p = _proj(args, ctx)
    path = str(args.get("path") or "")
    if not path.endswith(".tres"):
        path += ".tres"
    full = _abs(p, path)
    if os.path.exists(full) and not boolean(args.get("overwrite"), False):
        raise ToolkitError(f"{_res(p, full)} exists", "Pass overwrite=true.")
    head = [f'[gd_resource type="{args["type"]}" load_steps={2 if args.get("script") else 1} format=3]', ""]
    body = []
    if args.get("script"):
        head.insert(1, '[ext_resource type="Script" path="%s" id="1_script"]' % args["script"])
        body.append('script = ExtResource("1_script")')
    for k, v in as_dict(args.get("properties")).items():
        body.append(f"{k} = {lit(v, k)}")
    text = "\n".join(head + ["[resource]"] + body) + "\n"
    return {"resource": _res(p, full), "written": _write(full, text, args)}


@tool(G, "ms_godot_list_files", "List project files under a folder, filtered by extension, with sizes. Skips .godot/.git. Read-only.",
      {"folder": {"type": "string"}, "extensions": {"type": "array", "items": {"type": "string"}}, "limit": {"type": "integer", "minimum": 1, "maximum": 2000}}, [], local=True)
def list_files(args, ctx):
    p = _proj(args, ctx)
    base = _abs(p, args.get("folder") or "")
    exts = {("." + str(e).lstrip(".")).lower() for e in as_list(args.get("extensions"))}
    lim = num(args.get("limit"), 300, 1, 2000, True)
    rows = []
    for dp, dn, fn in os.walk(base):
        dn[:] = sorted(d for d in dn if d not in (".godot", ".git", ".import"))
        for f in sorted(fn):
            if f.endswith((".import", ".uid")) or (exts and os.path.splitext(f)[1].lower() not in exts):
                continue
            fp = os.path.join(dp, f)
            rows.append({"path": _res(p, fp), "bytes": os.path.getsize(fp)})
            if len(rows) >= lim:
                return {"count": len(rows), "truncated": True, "files": rows}
    return {"count": len(rows), "files": rows}


_TEXT_EXT = (".tscn", ".tres", ".gd", ".godot", ".cfg", ".gdshader", ".import", ".json", ".md")


def _refs(proj, res_path):
    hits = []
    for dp, dn, fn in os.walk(proj):
        dn[:] = [d for d in dn if d not in (".godot", ".git")]
        for f in fn:
            if f.endswith(_TEXT_EXT) and not f.endswith(".md"):
                fp = os.path.join(dp, f)
                try:
                    t = _read(fp)
                except Exception:
                    continue
                if res_path in t:
                    hits.append((fp, t.count(res_path)))
    return hits


@tool(G, "ms_godot_find_references", "Find every file that references a resource path (scenes, scripts, resources, project.godot) - check before deleting or moving. Read-only.",
      {"path": {"type": "string"}}, ["path"], local=True)
def find_references(args, ctx):
    p = _proj(args, ctx)
    full = _abs(p, args.get("path"))
    rp = _res(p, full)
    hits = [h for h in _refs(p, rp) if os.path.normpath(h[0]) != os.path.normpath(full)]
    return {"path": rp, "exists": os.path.exists(full), "referenced_by": [{"file": _res(p, f), "count": c} for f, c in hits], "safe_to_delete": not hits}


@tool(G, "ms_godot_move_file", "Move/rename a project file and rewrite every res:// reference to it (scenes, scripts, resources, project settings), keeping .import/.uid sidecars with it.",
      {"from_path": {"type": "string"}, "to_path": {"type": "string"}}, ["from_path", "to_path"], writes=True, local=True)
def move_file(args, ctx):
    p = _proj(args, ctx)
    src, dst = _abs(p, args.get("from_path")), _abs(p, args.get("to_path"))
    if not os.path.exists(src):
        raise ToolkitError(f"not found: {_res(p, src)}")
    if os.path.exists(dst):
        raise ToolkitError(f"destination exists: {_res(p, dst)}")
    old, new = _res(p, src), _res(p, dst)
    refs = _refs(p, old)
    if args.get("dry_run"):
        return {"would_move": [old, new], "references_to_rewrite": [{"file": _res(p, f), "count": c} for f, c in refs]}
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.replace(src, dst)
    for ext in (".import", ".uid"):
        if os.path.exists(src + ext):
            os.replace(src + ext, dst + ext)
    fixed = []
    for fp, c in refs:
        if os.path.normpath(fp) == os.path.normpath(src):
            fp = dst
        if not os.path.exists(fp):
            continue
        t = _read(fp)
        _write(fp, t.replace(old, new), {})
        fixed.append({"file": _res(p, fp), "count": c})
    return {"moved": [old, new], "references_rewritten": fixed}


@tool(G, "ms_godot_validate_project",
      "Whole-project health check from disk: missing ext_resource files, scenes pointing at deleted scripts, missing main scene/autoloads, Godot-3 syntax in scripts, "
      "empty scenes. Read-only; run it after big edits and before exporting.",
      {}, local=True)
def validate_project(args, ctx):
    p = _proj(args, ctx)
    problems, scenes, scripts = [], 0, 0
    text = _read(os.path.join(p, "project.godot"))
    entries, _l = parse_project(text)
    ms = next((e["raw"].strip('"') for e in entries if e["key"] == "run/main_scene"), "")
    if not ms:
        problems.append({"kind": "no_main_scene", "detail": "application/run/main_scene is not set"})
    elif not os.path.exists(_abs(p, ms)):
        problems.append({"kind": "missing_main_scene", "detail": ms})
    for e in entries:
        if e["section"] == "autoload":
            ap = e["raw"].strip('"').lstrip("*")
            if not os.path.exists(_abs(p, ap)):
                problems.append({"kind": "missing_autoload", "detail": f"{e['key']} -> {ap}"})
    for dp, dn, fn in os.walk(p):
        dn[:] = [d for d in dn if d not in (".godot", ".git", ".import", "addons")]
        for f in fn:
            fp = os.path.join(dp, f)
            if f.endswith((".tscn", ".tres")):
                scenes += 1
                try:
                    sc = Scene(_read(fp))
                except Exception:
                    problems.append({"kind": "unreadable", "detail": _res(p, fp)})
                    continue
                for b in sc.of("ext_resource"):
                    rp = b["attrs"].get("path", "")
                    if rp.startswith("res://") and not os.path.exists(_abs(p, rp)):
                        problems.append({"kind": "missing_resource", "file": _res(p, fp), "detail": rp})
                if f.endswith(".tscn") and not sc.nodes():
                    problems.append({"kind": "empty_scene", "detail": _res(p, fp)})
            elif f.endswith(".gd"):
                scripts += 1
                r = _static_gd(_read(fp))
                if not r["ok"]:
                    problems.append({"kind": "script_issues", "file": _res(p, fp), "detail": r["issues"]})
    return {"scenes_and_resources_scanned": scenes, "scripts_scanned": scripts, "problems": problems[:200], "problem_count": len(problems),
            "verdict": "clean" if not problems else f"{len(problems)} problem(s)"}


@tool(G, "ms_godot_changes",
      "See which project files changed since a checkpoint - including edits the USER made in the Godot editor. action=checkpoint hashes scenes/scripts/resources/project.godot; action=diff lists added/removed/modified files.",
      {"action": {"type": "string", "enum": ["checkpoint", "diff"]}, "label": {"type": "string"}}, ["action"], local=True)
def changes(args, ctx):
    p = _proj(args, ctx)
    label = f"{p}:{args.get('label') or 'default'}"
    snap = {}
    for dp, dn, fn in os.walk(p):
        dn[:] = [d for d in dn if d not in (".godot", ".git", ".import", "node_modules")]
        for f in fn:
            if f.endswith((".gd", ".tscn", ".tres", ".godot", ".gdshader", ".cfg")):
                fp = os.path.join(dp, f)
                try:
                    snap[_res(p, fp)] = {"sha": hashlib.sha1(open(fp, "rb").read()).hexdigest()[:12], "bytes": os.path.getsize(fp)}
                except Exception:
                    pass
    act = str(args.get("action") or "diff").lower()
    if act == "checkpoint":
        snapshot_store(G, label, snap)
        return {"label": label.split(":", 1)[1], "files": len(snap)}
    prev = snapshot_get(G, label)
    if not prev:
        raise ToolkitError("no checkpoint yet", "Call with action=checkpoint first.")
    out = diff_maps(prev["data"], snap)
    out["since_seconds"] = int(time.time() - prev["at"])
    return out


# ── native: run / debug ─────────────────────────────────────────────────────
@tool(G, "ms_godot_playtest",
      "Play-test loop on the native Godot MCP: run the project (or one scene), wait `seconds`, read the debug output, stop it, and return a PASS/WARN/FAIL verdict with the errors.",
      {"scene": {"type": "string", "description": "Optional res:// scene to run instead of the main scene."}, "seconds": {"type": "integer", "minimum": 1, "maximum": 120}, "stop_after": {"type": "boolean"}}, [], writes=True)
def playtest(args, ctx):
    p = _proj(args, ctx)
    run_t = _need(ctx, G, "run_project")
    dbg_t = _need(ctx, G, "get_debug_output")
    stop_t = _need(ctx, G, "stop_project")
    secs = num(args.get("seconds"), 6, 1, 120, True)
    a = {"projectPath": p}
    if args.get("scene"):
        a["scene"] = str(args["scene"])
    if args.get("dry_run"):
        return {"dryRun": True, "plan": [{"tool": run_t, "arguments": a}, {"wait_seconds": secs}, {"tool": dbg_t}, {"tool": stop_t}]}
    ctx.call(G, run_t, a, 60)
    time.sleep(secs)
    out = ctx.call(G, dbg_t, {}, 60)
    text = str((out or {}).get("text") or "")
    stopped = False
    if boolean(args.get("stop_after"), True):
        try:
            ctx.call(G, stop_t, {}, 60)
            stopped = True
        except Exception as exc:
            text += f"\n[could not stop: {exc}]"
    lines = [l for l in text.splitlines() if l.strip()]
    errs = [l for l in lines if re.search(r"SCRIPT ERROR|ERROR:|Parse Error|Invalid (get|set|call)|Null instance|Nonexistent", l)]
    warns = [l for l in lines if "WARNING" in l and l not in errs]
    return {"verdict": "FAIL" if errs else ("WARN" if warns else "PASS"), "ran_seconds": secs, "stopped": stopped, "errors": errs[:30], "warnings": warns[:20],
            "output_tail": lines[-40:], "next": "Fix every error, then run ms_godot_playtest again until PASS."}
