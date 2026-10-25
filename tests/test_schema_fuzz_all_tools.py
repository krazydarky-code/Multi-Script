#!/usr/bin/env python3
"""Fuzz EVERY advertised tool schema with the slips models actually make.

For each tool we build a valid call from the schema, then mangle it (stringified
numbers/booleans/JSON, shouted enums, renamed keys, wrapper envelopes, extra keys,
nulls for optional fields) and require the production repair path
(`bridge._resilient_arguments`) to accept the result. A failure here is the
"JSON schema error" class the user reported, for a specific tool + mutation.
"""
import copy, importlib.util, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools")); sys.path.insert(0, os.path.join(ROOT, "runtime"))
import schema_audit
import schema_repair

bridge = schema_audit.load_bridge()
schemas = schema_audit.collect_schemas(bridge)
seen = {n for n, _ in schemas}
def add_more(items, label):
    n = 0
    for t in items or []:
        if isinstance(t, dict) and t.get("name") and t["name"] not in seen:
            seen.add(t["name"]); schemas.append((t["name"], t.get("inputSchema") or t.get("parameters"))); n += 1
    print(f"  + {n} {label} schemas")
if getattr(bridge, "_TOOLKIT", None) is not None:
    add_more(bridge._TOOLKIT.definitions(), "engine-toolkit")
if getattr(bridge, "ASSIST", None) is not None:
    add_more(bridge.ASSIST.DEFINITIONS, "assist")
if getattr(bridge, "WORKSPACE", None) is not None:
    add_more(getattr(bridge.WORKSPACE, "TOOLS", []), "software-workspace")

def stringify(v):
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, (int, float)): return str(v)
    return v
def deep_str(v):
    if isinstance(v, dict): return {k: deep_str(x) for k, x in v.items()}
    if isinstance(v, list): return [deep_str(x) for x in v]
    return stringify(v)
def top_json(v):
    return {k: (json.dumps(x) if isinstance(x, (dict, list)) else x) for k, x in v.items()}
def shout(v):
    return {k: (x.upper() if isinstance(x, str) and k not in () else x) for k, x in v.items()}
def camel(k):
    p = k.split("_"); return p[0] + "".join(w.title() for w in p[1:])
def renamed(v, fn):
    return {fn(k): x for k, x in v.items()}

def with_null_optionals(schema):
    def f(v):
        props = (schema.get("properties") or {})
        extra = {k: None for k in props if k not in v}
        return {**v, **extra}
    return f
def extreme(v):
    def x(n):
        if isinstance(n, bool): return n
        if isinstance(n, int): return 10**9
        if isinstance(n, float): return 1e9
        if isinstance(n, dict): return {k: x(i) for k, i in n.items()}
        if isinstance(n, list): return [x(i) for i in n]
        return n
    return x(v)

MUTATIONS = {
    "extreme-numbers": extreme,
    "stringified-scalars": deep_str,
    "json-string-containers": top_json,
    "camelCase-keys": lambda v: renamed(v, camel),
    "UPPER-keys": lambda v: renamed(v, str.upper),
    "kebab-keys": lambda v: renamed(v, lambda k: k.replace("_", "-")),
    "null-optionals": lambda v: v,
    "extra-unknown-key": lambda v: {**v, "zz_unknown_extra": 1},
    "wrap-arguments": lambda v: {"arguments": v},
    "wrap-params": lambda v: {"params": v},
    "wrap-input": lambda v: {"input": v},
    "whole-json-string": lambda v: json.dumps(v),
}

failures, checked = [], 0
for name, schema in schemas:
    if not isinstance(schema, dict):
        continue
    base = schema_repair.example(schema)
    try:
        bridge._resilient_arguments(schema, copy.deepcopy(base), name)
    except Exception as e:
        failures.append((name, "base-example", str(e)[:160])); continue
    for label, fn in MUTATIONS.items():
        try:
            mutated = fn(copy.deepcopy(base))
            if label == "null-optionals": mutated = with_null_optionals(schema)(copy.deepcopy(base))
        except Exception:
            continue
        if label.startswith(("camel", "UPPER", "kebab")) and not base:
            continue
        if label.startswith("wrap-") and label[5:] in (schema.get("properties") or {}):
            continue  # the wrapper key IS a real parameter of this tool
        checked += 1
        try:
            bridge._resilient_arguments(schema, mutated, name)
        except Exception as e:
            failures.append((name, label, str(e)[:160]))

print(f"fuzzed {len(schemas)} tool schemas, {checked} mutated calls")
by = {}
for n, l, m in failures: by.setdefault(l, []).append((n, m))
for l, items in sorted(by.items()):
    print(f"  {l}: {len(items)} failing")
    for n, m in items[:6]: print(f"      {n}: {m}")
print("failed:", len(failures))
sys.exit(1 if failures else 0)
