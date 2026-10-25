# SPDX-License-Identifier: GPL-3.0-or-later
"""schema_repair.py - self-healing tool-argument repair for Multi-Script.

WHY THIS EXISTS
A web chat model writes tool calls from memory. It sends "3" for an integer,
`{"x":1,"y":2,"z":3}` for a Vector3 array, `"true"` for a boolean, a snake_case
key where the server wants camelCase, an enum in the wrong case, a stringified
JSON object, or an extra helper key the server's `additionalProperties:false`
refuses. A strict validator turns every one of those into a "JSON schema error"
and the model burns a turn (or a free-trial prompt) fixing a typo the machine
could have fixed in microseconds.

This module is the machine fixing it. It takes the live schema an engine
advertised and a best-effort argument object and returns:

    (repaired_arguments, notes)

`notes` lists every change made, so nothing is silent - the bridge appends them
to the tool result and the model learns the right shape for the next call.

WHAT IT WILL NOT DO
It never invents a value for a required parameter it cannot derive (no guessing
a file path, a node name or a studio id), never loosens an `enum` to something
the server does not list, and never touches a value that already satisfies the
schema. When a call genuinely cannot be repaired, `describe()` produces the
exact signature and a copy-ready example for the error message instead.

Pure stdlib. No I/O. Deterministic.
"""
import ast
import difflib
import json
import re

MAX_DEPTH = 32

# Groups of parameter names that mean the same thing across the engines' MCP
# servers (Roblox Studio, Unity, Godot, Blender, Figma ...). Keys are
# NORMALISED (lower-case, alphanumerics only). A group is only ever used to
# rename an UNKNOWN key into a MISSING declared property, never to override
# something the caller already supplied correctly.
_SYNONYM_GROUPS = [
    {"path", "filepath", "file", "filename", "targetfile", "scriptpath", "assetpath", "resourcepath", "respath"},
    {"code", "source", "script", "luau", "lua", "gdscript", "csharp", "python", "content", "body", "snippet", "contents", "text"},
    {"name", "title", "label", "displayname"},
    {"query", "keywords", "search", "searchterm", "term", "q", "keyword"},
    {"classname", "class", "instanceclass", "classtype", "nodetype", "componenttype"},
    {"position", "pos", "location", "translation", "origin", "coords", "coordinates"},
    {"rotation", "rot", "euler", "eulerangles", "orientation"},
    {"scale", "scaling"},
    {"parent", "parentpath", "parentname", "parentnode", "parentid"},
    {"value", "val", "newvalue"},
    {"instancepath", "target", "targetpath", "node", "nodepath", "object", "objectpath", "objectname", "gameobject", "gameobjectpath", "instance", "path"},
    {"projectpath", "project", "projectdir", "projectroot", "projectfolder"},
    {"scenepath", "scene", "scenefile"},
    {"property", "prop", "propertyname", "propname"},
    {"properties", "props", "attributes", "propertyvalues"},
    {"action", "operation", "op", "subcommand"},
    {"oldstring", "find", "search", "before", "oldtext", "old"},
    {"newstring", "replace", "replacement", "after", "newtext", "new"},
    {"assetid", "assetids", "asset"},
    {"timeout", "timeoutms", "timeoutseconds"},
    {"limit", "maxresults", "count", "max", "top", "n"},
    {"width", "w"}, {"height", "h"},
    {"datamodeltype", "datamodel", "dmtype"},
    {"studioid", "studio"},
    {"objectname", "blenderobject", "obj", "object"},
]
_SYN = {}
for _g in _SYNONYM_GROUPS:
    for _k in _g:
        _SYN.setdefault(_k, set()).update(_g)

_WRAPPER_KEYS = ("arguments", "params", "parameters", "args", "input", "payload", "data")
_TRUE = {"true", "1", "yes", "y", "on", "enabled", "enable", "t"}
_FALSE = {"false", "0", "no", "n", "off", "disabled", "disable", "f", "none", "null", ""}
_AXES = ("x", "y", "z", "w")


def _norm(key):
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _resolve_ref(root, ref):
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return {}
    node = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return {}
        node = node[part]
    return node if isinstance(node, dict) else {}


def _flatten(spec, root, depth=0):
    """Resolve $ref and merge allOf into one spec dict (best effort)."""
    if not isinstance(spec, dict) or depth > MAX_DEPTH:
        return {}
    if "$ref" in spec:
        merged = dict(_resolve_ref(root, spec["$ref"]))
        merged.update({k: v for k, v in spec.items() if k != "$ref"})
        spec = merged
    if isinstance(spec.get("allOf"), list):
        out = {k: v for k, v in spec.items() if k != "allOf"}
        props = dict(out.get("properties") or {})
        req = list(out.get("required") or [])
        for branch in spec["allOf"]:
            b = _flatten(branch, root, depth + 1)
            props.update(b.get("properties") or {})
            req.extend(b.get("required") or [])
            for k, v in b.items():
                if k not in ("properties", "required"):
                    out.setdefault(k, v)
        if props:
            out["properties"] = props
        if req:
            out["required"] = list(dict.fromkeys(req))
        spec = out
    return spec


def _type_of(spec):
    t = spec.get("type")
    if isinstance(t, list):
        non_null = [x for x in t if x != "null"]
        return non_null[0] if len(non_null) == 1 else (non_null or [None])
    if t:
        return t
    if "properties" in spec:
        return "object"
    if "items" in spec:
        return "array"
    if "enum" in spec and spec["enum"] and all(isinstance(x, str) for x in spec["enum"]):
        return "string"
    return None


def _fits(value, spec, root, depth=0):
    """Cheap structural check: could `value` already be valid for `spec`?"""
    spec = _flatten(spec, root)
    if depth > 8:
        return True
    for key in ("anyOf", "oneOf"):
        if isinstance(spec.get(key), list):
            return any(_fits(value, b, root, depth + 1) for b in spec[key])
    t = spec.get("type")
    types = t if isinstance(t, list) else ([t] if t else [])
    if value is None:
        return "null" in types or spec.get("nullable") or not types
    if "enum" in spec:
        return any(value == e and type(value) is type(e) for e in spec["enum"])
    if not types:
        types = [_type_of(spec)] if _type_of(spec) else []
        types = [x for x in types if isinstance(x, str)]
    if not types:
        return True
    ok = False
    for typ in types:
        if typ == "string" and isinstance(value, str): ok = True
        elif typ == "integer" and isinstance(value, int) and not isinstance(value, bool): ok = True
        elif typ == "number" and isinstance(value, (int, float)) and not isinstance(value, bool): ok = True
        elif typ == "boolean" and isinstance(value, bool): ok = True
        elif typ == "array" and isinstance(value, list): ok = True
        elif typ == "object" and isinstance(value, dict):
            req = spec.get("required") or []
            ok = all(k in value for k in req)
        elif typ == "null" and value is None: ok = True
    return ok


class _Repairer:
    def __init__(self, root):
        self.root = root if isinstance(root, dict) else {}
        self.notes = []

    def note(self, path, msg):
        if len(self.notes) < 40:
            self.notes.append(f"{path}: {msg}")

    # ---- entry -----------------------------------------------------------
    def run(self, arguments):
        value = arguments
        if isinstance(value, str):
            value = self._parse_container(value, "parameters", want="object")
        if value is None:
            value = {}
        if not isinstance(value, dict):
            self.note("parameters", f"expected an object, got {type(value).__name__}; sent as {{}}")
            value = {}
        return self.value(value, self.root or {"type": "object"}, "parameters", 0)

    # ---- helpers ---------------------------------------------------------
    def _parse_container(self, text, path, want):
        s = text.strip()
        if not s:
            return None
        # models love fenced JSON
        s = re.sub(r"^```(?:json|JSON)?\s*|\s*```$", "", s).strip()
        if s[:1] in "[{":
            for attempt in (lambda: json.loads(s), lambda: ast.literal_eval(s), lambda: json.loads(re.sub(r",\s*([}\]])", r"\1", s))):
                try:
                    out = attempt()
                    self.note(path, "parsed a stringified JSON value")
                    return out
                except Exception:
                    pass
        return text

    def _enum_pick(self, value, enum, path):
        if any(value == e and type(value) is type(e) for e in enum):
            return value
        sval = str(value)
        strs = [e for e in enum if isinstance(e, str)]
        n = _norm(sval)
        for e in strs:
            if e == sval:
                return e
        for e in strs:
            if e.lower() == sval.lower():
                self.note(path, f"matched enum '{e}' case-insensitively")
                return e
        for e in strs:
            if _norm(e) == n and n:
                self.note(path, f"matched enum '{e}' ignoring separators")
                return e
        close = difflib.get_close_matches(n, [_norm(e) for e in strs], n=2, cutoff=0.84)
        if len(close) == 1 or (len(close) == 2 and close[0] != close[1]):
            for e in strs:
                if _norm(e) == close[0]:
                    self.note(path, f"enum '{sval}' -> closest valid '{e}'")
                    return e
        for e in enum:
            if not isinstance(e, str):
                try:
                    if str(e).lower() == sval.lower():
                        self.note(path, f"matched enum {e!r}")
                        return e
                except Exception:
                    pass
        return value

    @staticmethod
    def _to_number(value):
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            s = value.strip().replace(",", "").replace("_", "")
            m = re.fullmatch(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?", s)
            if m:
                return float(s)
            m = re.match(r"\s*([+-]?(?:\d+\.?\d*|\.\d+))\s*(?:[a-zA-Z%\u00b0]{0,8})\s*$", value)
            if m:
                return float(m.group(1))
        return None

    # ---- recursion -------------------------------------------------------
    def value(self, value, spec, path, depth):
        if depth > MAX_DEPTH:
            return value
        spec = _flatten(spec, self.root)
        for key in ("oneOf", "anyOf"):
            alts = spec.get(key)
            if isinstance(alts, list) and alts:
                if any(_fits(value, b, self.root) for b in alts):
                    for b in alts:
                        if _fits(value, b, self.root):
                            return self.value(value, b, path, depth + 1)
                # nothing fits as-is: repair against each, prefer one that fits afterwards
                best = None
                for b in alts:
                    sub = _Repairer(self.root)
                    cand = sub.value(_deepcopy(value), b, path, depth + 1)
                    if _fits(cand, b, self.root):
                        best = (cand, sub.notes)
                        break
                if best:
                    self.notes.extend(best[1])
                    return best[0]
                non_null = [b for b in alts if _flatten(b, self.root).get("type") != "null"]
                return self.value(value, (non_null or alts)[0], path, depth + 1)
        typ = _type_of(spec)
        if isinstance(typ, list):  # multiple non-null types
            for t in typ:
                if _fits(value, {**spec, "type": t}, self.root):
                    return self.value(value, {**spec, "type": t}, path, depth + 1)
            typ = typ[0]
        if value is None:
            return None
        if "const" in spec:
            if value != spec["const"]:
                self.note(path, f"set to the schema constant {spec['const']!r}")
            return spec["const"]
        if typ == "string":
            if isinstance(value, bool):
                value = "true" if value else "false"
                self.note(path, "boolean sent as string")
            elif isinstance(value, (int, float)):
                value = str(value)
                self.note(path, "number sent as string")
            elif isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
                self.note(path, "structure serialised to a JSON string")
            if isinstance(value, str):
                if "enum" in spec:
                    value = self._enum_pick(value, spec["enum"], path)
                ml = spec.get("maxLength")
                if isinstance(ml, int) and len(value) > ml:
                    # Never silently execute a clipped script, SVG or exact edit.
                    # Preserve it so strict validation reports the real limit.
                    self.note(path, f"exceeds maxLength {ml}; value preserved, not truncated")
                fmt = spec.get("format")
                if fmt in ("uri", "url") and value and "://" not in value and re.match(r"^[\w.-]+\.[a-z]{2,}", value):
                    value = "https://" + value
                    self.note(path, "added https:// scheme")
            return value
        if typ in ("integer", "number"):
            if isinstance(value, bool):
                value = int(value)
                self.note(path, "boolean sent as number")
            else:
                num = self._to_number(value)
                if num is None:
                    if "enum" in spec:
                        return self._enum_pick(value, spec["enum"], path)
                    return value
                if isinstance(value, str):
                    self.note(path, "numeric string converted")
                value = num
            if typ == "integer":
                if isinstance(value, float):
                    if not value.is_integer():
                        self.note(path, f"rounded {value} to an integer")
                    value = int(round(value))
            elif isinstance(value, float) and value.is_integer() and "enum" in spec:
                value = int(value)
            lo, hi = spec.get("minimum"), spec.get("maximum")
            if spec.get("exclusiveMinimum") is not None and value <= spec["exclusiveMinimum"]:
                lo = spec["exclusiveMinimum"] + (1 if typ == "integer" else 1e-9)
            if spec.get("exclusiveMaximum") is not None and value >= spec["exclusiveMaximum"]:
                hi = spec["exclusiveMaximum"] - (1 if typ == "integer" else 1e-9)
            if lo is not None and value < lo:
                self.note(path, f"clamped {value} up to minimum {lo}")
                value = lo
            if hi is not None and value > hi:
                self.note(path, f"clamped {value} down to maximum {hi}")
                value = hi
            if "enum" in spec:
                value = self._enum_pick(value, spec["enum"], path)
            return value
        if typ == "boolean":
            if isinstance(value, str):
                low = value.strip().lower()
                if low in _TRUE:
                    self.note(path, "boolean word converted")
                    return True
                if low in _FALSE:
                    self.note(path, "boolean word converted")
                    return False
            elif isinstance(value, (int, float)) and value in (0, 1):
                self.note(path, "number sent as boolean")
                return bool(value)
            return value
        if typ == "array":
            return self._array(value, spec, path, depth)
        if typ == "object":
            return self._object(value, spec, path, depth)
        if "enum" in spec and isinstance(value, (str, int, float)):
            return self._enum_pick(value, spec["enum"], path)
        return value

    def _array(self, value, spec, path, depth):
        items = _flatten(spec.get("items"), self.root) if isinstance(spec.get("items"), dict) else {}
        item_type = _type_of(items) if items else None
        if isinstance(value, str):
            parsed = self._parse_container(value, path, "array")
            if isinstance(parsed, (list, dict)):
                value = parsed
            else:
                s = value.strip()
                if not s:
                    value = []
                    self.note(path, "empty string became an empty array")
                elif item_type in (None, "string", "integer", "number"):
                    value = [x.strip() for x in re.split(r"[,\n;]+|\s{2,}", s) if x.strip()] if re.search(r"[,\n;]", s) or item_type in ("integer", "number") else [s]
                    if item_type in ("integer", "number") and len(value) == 1:
                        value = [x for x in re.split(r"\s+", s) if x]
                    self.note(path, "delimited string split into an array")
                else:
                    value = [value]
        if isinstance(value, dict):
            axes = [a for a in _AXES if a in {str(k).lower() for k in value}]
            if axes and item_type in ("number", "integer") and len(axes) == len(value):
                lower = {str(k).lower(): v for k, v in value.items()}
                value = [lower[a] for a in axes]
                self.note(path, "{x,y,z} object converted to a vector array")
            else:
                value = [value]
                self.note(path, "single object wrapped in an array")
        elif value is not None and not isinstance(value, list):
            value = [value]
            self.note(path, "single value wrapped in an array")
        if value is None:
            return None
        out = [self.value(x, items, f"{path}[{i}]", depth + 1) if items else x for i, x in enumerate(value)]
        mx, mn = spec.get("maxItems"), spec.get("minItems")
        if isinstance(mx, int) and len(out) > mx:
            self.note(path, f"trimmed to maxItems {mx}")
            out = out[:mx]
        if spec.get("uniqueItems"):
            seen, uniq = set(), []
            for x in out:
                k = json.dumps(x, sort_keys=True, default=str)
                if k not in seen:
                    seen.add(k)
                    uniq.append(x)
            if len(uniq) != len(out):
                self.note(path, "removed duplicate items")
            out = uniq
        if isinstance(mn, int) and len(out) < mn and item_type in ("number", "integer") and mn == (mx or mn) and mn <= 4:
            out = out + [0 if item_type == "integer" else 0.0] * (mn - len(out))
            self.note(path, f"padded vector to {mn} components with 0")
        return out

    def _object(self, value, spec, path, depth):
        if isinstance(value, str):
            parsed = self._parse_container(value, path, "object")
            value = parsed if isinstance(parsed, dict) else value
        if isinstance(value, list) and value and all(isinstance(p, (list, tuple)) and len(p) == 2 for p in value):
            value = {str(k): v for k, v in value}
            self.note(path, "pair list converted to an object")
        if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
            value = value[0]
            self.note(path, "single-item array unwrapped to an object")
        if not isinstance(value, dict):
            return value
        props = spec.get("properties") or {}
        out = dict(value)
        # unwrap {"arguments": {...}} style envelopes when nothing declared matches
        if props and not any(k in props for k in out):
            for wk in _WRAPPER_KEYS:
                hit = next((k for k in out if str(k).lower() == wk and isinstance(out[k], (dict, str))), None)
                if hit and wk not in props and len(out) == 1:
                    inner = out[hit]
                    if isinstance(inner, str):
                        inner = self._parse_container(inner, path, "object")
                    if isinstance(inner, dict):
                        out = dict(inner)
                        self.note(path, f"unwrapped the '{hit}' envelope")
                        break
        if props:
            out = self._remap_keys(out, props, spec, path)
        for k in list(out.keys()):
            if k in props:
                out[k] = self.value(out[k], props[k], f"{path}.{k}", depth + 1)
        # optional fields sent as null / "" / "none": drop instead of failing
        required = set(spec.get("required") or [])
        for k in list(out.keys()):
            if k in required or k not in props:
                continue
            ps = _flatten(props[k], self.root)
            ptype = _type_of(ps)
            allows_null = ps.get("nullable") or (isinstance(ps.get("type"), list) and "null" in ps["type"])
            if out[k] is None and not allows_null:
                del out[k]
                self.note(f"{path}.{k}", "dropped null for an optional field")
            elif isinstance(out[k], str) and out[k].strip() == "" and (ptype in ("integer", "number", "boolean", "array", "object") or "enum" in ps):
                del out[k]
                self.note(f"{path}.{k}", "dropped an empty value for an optional field")
        # additionalProperties
        extra = spec.get("additionalProperties", True)
        unknown = [k for k in out if k not in props]
        if isinstance(extra, dict):
            for k in unknown:
                out[k] = self.value(out[k], extra, f"{path}.{k}", depth + 1)
        elif extra is False and unknown and props:
            for k in unknown:
                del out[k]
            self.note(path, "dropped unsupported parameter(s): " + ", ".join(sorted(map(str, unknown))))
        # required that can be derived
        for k in spec.get("required") or []:
            if k in out and out[k] is not None:
                continue
            ps = _flatten(props.get(k) or {}, self.root)
            if "const" in ps:
                out[k] = ps["const"]
                self.note(f"{path}.{k}", "filled schema constant")
            elif "default" in ps:
                out[k] = ps["default"]
                self.note(f"{path}.{k}", "filled schema default")
            elif isinstance(ps.get("enum"), list) and len(ps["enum"]) == 1:
                out[k] = ps["enum"][0]
                self.note(f"{path}.{k}", "filled the only allowed value")
        return out

    def _remap_keys(self, obj, props, spec, path):
        declared = list(props.keys())
        declared_norm = {}
        for d in declared:
            declared_norm.setdefault(_norm(d), d)
        out = {}
        pending = []
        for k, v in obj.items():
            if k in props:
                out[k] = v
            else:
                pending.append((k, v))
        required = list(spec.get("required") or [])
        for k, v in pending:
            nk = _norm(k)
            target = declared_norm.get(nk)
            if target and out.get(target) is None:
                out[target] = v
                self.note(path, f"renamed '{k}' to '{target}'")
                continue
            if target is None:
                # synonym -> a declared name that is still missing
                cands = [d for d in declared if out.get(d) is None and _norm(d) in _SYN.get(nk, ())]
                if len(cands) > 1:
                    pref = [d for d in cands if d in required] or cands
                    cands = pref[:1]
                if len(cands) == 1:
                    out[cands[0]] = v
                    self.note(path, f"renamed '{k}' to '{cands[0]}'")
                    continue
                # close spelling
                free = [d for d in declared if out.get(d) is None]
                m = difflib.get_close_matches(nk, [_norm(d) for d in free], n=1, cutoff=0.86)
                if m:
                    d = next(x for x in free if _norm(x) == m[0])
                    out[d] = v
                    self.note(path, f"renamed '{k}' to '{d}'")
                    continue
            out[k] = v
        return out


def _deepcopy(v):
    try:
        return json.loads(json.dumps(v))
    except Exception:
        return v


def repair_arguments(schema, arguments, tool_name="tool"):
    """Return (repaired_arguments, notes). Never raises."""
    try:
        root = schema if isinstance(schema, dict) else {"type": "object", "properties": {}}
        r = _Repairer(root)
        out = r.run(_deepcopy(arguments) if not isinstance(arguments, str) else arguments)
        return out, r.notes
    except Exception as exc:  # pragma: no cover - defensive; repair must never break a call
        return arguments if isinstance(arguments, dict) else {}, [f"repair skipped: {type(exc).__name__}"]


# ---- error enrichment ------------------------------------------------------
def _short_type(spec, root, depth=0):
    spec = _flatten(spec, root)
    for key in ("oneOf", "anyOf"):
        if isinstance(spec.get(key), list):
            return "|".join(dict.fromkeys(_short_type(b, root, depth + 1) for b in spec[key]))[:60]
    if "enum" in spec and spec["enum"]:
        vals = [json.dumps(e) if not isinstance(e, str) else e for e in spec["enum"]]
        return "enum(" + "|".join(vals[:8]) + ("|..." if len(vals) > 8 else "") + ")"
    t = _type_of(spec)
    if t == "array":
        it = spec.get("items")
        return f"array<{_short_type(it, root, depth + 1) if isinstance(it, dict) and depth < 3 else 'any'}>"
    if isinstance(t, list):
        return "|".join(str(x) for x in t)
    return str(t or "any")


def signature(schema, tool_name="tool"):
    root = schema if isinstance(schema, dict) else {}
    spec = _flatten(root, root)
    props = spec.get("properties") or {}
    req = set(spec.get("required") or [])
    if not props:
        return f"{tool_name}()"
    parts = []
    for k, ps in list(props.items())[:24]:
        parts.append(f"{k}{'' if k in req else '?'}: {_short_type(ps, root)}")
    more = f", +{len(props) - 24} more" if len(props) > 24 else ""
    return f"{tool_name}({', '.join(parts)}{more})  [? = optional]"


def example(schema, depth=0):
    root = schema if isinstance(schema, dict) else {}

    def make(spec, d):
        spec = _flatten(spec, root)
        if d > 4:
            return None
        if "default" in spec:
            return spec["default"]
        if "const" in spec:
            return spec["const"]
        if spec.get("enum"):
            return spec["enum"][0]
        for key in ("oneOf", "anyOf"):
            if isinstance(spec.get(key), list) and spec[key]:
                return make(spec[key][0], d + 1)
        t = _type_of(spec)
        if isinstance(t, list):
            t = t[0]
        if t == "string": return "<text>"
        if t == "integer": return spec.get("minimum", 0) if isinstance(spec.get("minimum"), int) else 0
        if t == "number": return spec.get("minimum", 0.0)
        if t == "boolean": return False
        if t == "array":
            it = spec.get("items")
            n = max(1, int(spec.get("minItems") or 1))
            return [make(it, d + 1) for _ in range(min(n, 3))] if isinstance(it, dict) else []
        if t == "object" or "properties" in spec:
            props = spec.get("properties") or {}
            req = spec.get("required") or []
            return {k: make(props.get(k) or {}, d + 1) for k in req}
        return None

    out = make(root, depth)
    return out if isinstance(out, dict) else {}


def describe(schema, tool_name="tool"):
    """Two compact lines appended to a validation error: the signature and a
    copy-ready minimal call. Safe on any schema."""
    try:
        sig = signature(schema, tool_name)
        ex = json.dumps(example(schema), ensure_ascii=False)
        if len(ex) > 400:
            ex = ex[:400] + "..."
        return f"SIGNATURE: {sig}\nMINIMAL CALL: {ex}"
    except Exception:
        return ""


# ───────────────────────────────────────────────────────────────────────────
# Code transport repair
# ───────────────────────────────────────────────────────────────────────────
# "Script transfer" failures all look the same from the chat: the model's program
# text reaches the engine altered. The usual alterations, all machine-fixable:
#   * the code arrived as ONE line full of literal backslash-n (the JSON escaping was
#     applied twice, so Lua sees `\n` characters and fails with "unexpected symbol");
#   * the code is wrapped in a ```lua fence, or still carries the ###LUA### markers;
#   * the code came as an array of lines (or `lines`) instead of one string;
#   * a BOM / zero-width characters / CRLF from the chat renderer.
# repair_code_text() fixes those and nothing else: code that is already fine is returned
# unchanged, and the heuristics only fire when the text has NO real newline at all.

_CODE_KEYS = ("code", "source", "script", "luau", "lua", "python", "gdscript", "csharp", "source_code")
_CODE_TOOL = re.compile(r"(execute|run_|_run|script|luau|python|eval|code)", re.I)
_ZW = dict.fromkeys(map(ord, "\ufeff\u200b\u200c\u200d\u2060"), None)
_FENCE = re.compile(r"^\s*```[A-Za-z0-9_+-]*[ \t]*\r?\n(.*?)\r?\n?```\s*$", re.S)
_MARK_OPEN = re.compile(r"^\s*###\s*(?:LUA|lua)(?:[_-]?(?:EDIT|SERVER|CLIENT|PLUGIN))?\s*###\s*", re.M)
_MARK_END = re.compile(r"\s*###\s*END[_-]?LUA\s*###\s*$", re.I)


_STMT_BREAK = re.compile(r"(?:\)|\}|\]|\bend|;|[\"'])\\n\s*(?:local\b|end\b|if\b|for\b|while\b|return\b|function\b|repeat\b|until\b|else|print\b|--|[A-Za-z_][\w.:]*\s*[=(.:\[])")


def _looks_double_escaped(t):
    """True when a one-line program is clearly JSON-escaped twice: a backslash sits OUTSIDE
    any string literal (never valid Lua/Python/GDScript), or a literal \\n sits where a
    statement ends. A legitimate one-liner like print("a\\nb\\nc") is NOT touched."""
    if _STMT_BREAK.search(t):
        return True
    q = None
    i, n = 0, len(t)
    while i < n:
        c = t[i]
        if q:
            if c == "\\":
                i += 2
                continue
            if c == q:
                q = None
        elif c in "\"'":
            q = c
        elif c == "\\":
            return True
        elif c == "#" or (c == "-" and t[i:i + 2] == "--"):
            return False  # a comment may swallow the rest of a one-liner; do not guess
        i += 1
    return False


def repair_code_text(text):
    """-> (fixed_text, [notes]). Never raises; identical text and [] when nothing is wrong."""
    if not isinstance(text, str) or not text:
        return text, []
    notes = []
    t = text.translate(_ZW)
    if t != text:
        notes.append("removed invisible characters")
    m = _FENCE.match(t)
    if m:
        t = m.group(1)
        notes.append("removed the markdown code fence")
    if "###" in t:
        t2 = _MARK_END.sub("", _MARK_OPEN.sub("", t, count=1)).strip("\r\n")
        if t2 != t:
            t = t2
            notes.append("removed ###LUA### markers")
    if "\r" in t:
        t = t.replace("\r\n", "\n").replace("\r", "\n")
    # Double-escaped newlines: a long single line with several literal \n and no real newline.
    if "\n" not in t.strip("\n") and len(t) > 30 and t.count("\\n") >= 2 and _looks_double_escaped(t):
        fixed = t.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
        if t.count('\\"') >= 1:
            fixed = fixed.replace('\\"', '"')
        notes.append("decoded double-escaped \\n sequences into real line breaks")
        t = fixed
    return t, notes


def repair_code_arguments(tool_name, arguments):
    """Apply repair_code_text to the program-text arguments of a code-running tool.
    -> (new_arguments, notes). Accepts `lines` / list values and joins them."""
    if not isinstance(arguments, dict) or not _CODE_TOOL.search(str(tool_name or "")):
        return arguments, []
    out = dict(arguments)
    notes = []
    if "lines" in out and not any(k in out for k in _CODE_KEYS) and isinstance(out["lines"], list):
        out["code"] = "\n".join(str(x) for x in out.pop("lines"))
        notes.append("joined `lines` into `code`")
    for key in _CODE_KEYS:
        v = out.get(key)
        if isinstance(v, list) and v and all(isinstance(x, str) for x in v):
            v = "\n".join(v)
            notes.append(f"joined the `{key}` array into one string")
        if isinstance(v, str):
            fixed, n = repair_code_text(v)
            if fixed != arguments.get(key) or n:
                out[key] = fixed
                notes += [f"{key}: {x}" for x in n]
    return (out if notes else arguments), notes
