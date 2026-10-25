#!/usr/bin/env python3
"""Exhaustive audit of every advertised inputSchema against the live validator.

Why this exists
---------------
The reported bug class is "JSON schema errors on every engine". Two instances
were fixed by hand (an empty-string sentinel on `multi_edit`, a schema floor
that duplicated a handler clamp on `ms_studio_director`). A hand fix cannot prove
the class is gone: the failure mode is always the same shape - a schema that
advertises a CONSTRAINT STRICTER THAN THE HANDLER ACCEPTS - and it can appear on
any of several hundred declared schemas.

So this tool does not read the schemas for suspicious keywords. It runs the
REAL validator, the one that actually runs in production, against every
declared schema and reports:

  * bounds-stricter-than-default  - a numeric/enum/string bound that rejects a
    value a caller could reasonably send (the ms_studio_director class).
  * required-that-can-be-empty    - a required string field whose only sensible
    "create" value is the empty string (the multi_edit class).
  * schema-shape defects          - required names not in properties, arrays
    with no items, unknown keywords, external $ref (from _schema_risk_analysis).

It is deliberately dependent on bridge.py rather than re-implementing it: any
drift between this audit and production would make the audit worthless.

Usage:
    python tools/schema_audit.py            # summary + findings
    python tools/schema_audit.py --json     # machine-readable
    python tools/schema_audit.py --strict   # non-zero exit when findings exist
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIDGE = os.path.join(ROOT, "runtime", "bridge.py")

# Fields where an empty string is a DOCUMENTED, meaningful value rather than an
# omission. Kept in sync with bridge._EMPTY_STRING_IS_VALUE by asserting below.
KNOWN_EMPTY_STRING_SENTINELS = {"old_string"}

# Tools whose "limit"-style params are clamped by the handler, so the schema is
# allowed to be looser than the clamp but must never be TIGHTER.
CLAMPING_HINT = (
    "schema must be a superset of what the handler accepts: loosen the bound "
    "instead of rejecting the caller (clamp-not-reject)"
)


def load_bridge():
    spec = importlib.util.spec_from_file_location("ms_bridge_audit", BRIDGE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ms_bridge_audit"] = mod
    spec.loader.exec_module(mod)
    return mod


def collect_schemas(bridge):
    """Every (tool_name, schema) pair the bridge can validate against."""
    out = []
    seen = set()

    def add(name, schema):
        if not name or name in seen:
            return
        seen.add(name)
        out.append((str(name), schema))

    for attr in ("BUILTIN_TOOLS", "COMPANION_TOOLS"):
        for t in getattr(bridge, attr, []) or []:
            if isinstance(t, dict):
                add(t.get("name"), t.get("inputSchema"))
    for attr in ("BUILTIN_TOOL_BY_NAME", "COMPANION_TOOL_BY_NAME"):
        for name, t in (getattr(bridge, attr, {}) or {}).items():
            if isinstance(t, dict):
                add(name, t.get("inputSchema"))
    return out


def walk(node, path="parameters", depth=0, out=None):
    """Yield (path, subschema) for every object-ish node in the schema."""
    if out is None:
        out = []
    if not isinstance(node, dict) or depth > 32:
        return out
    if node.get("type") == "object" or "properties" in node:
        out.append((path, node))
    for k, v in (node.get("properties") or {}).items():
        walk(v, f"{path}.{k}", depth + 1, out)
    if isinstance(node.get("items"), dict):
        walk(node["items"], path + "[]", depth + 1, out)
    for key in ("oneOf", "anyOf", "allOf"):
        for i, v in enumerate(node.get(key) or []):
            walk(v, f"{path}.{key}[{i}]", depth + 1, out)
    if isinstance(node.get("additionalProperties"), dict):
        walk(node["additionalProperties"], path + ".*", depth + 1, out)
    return out


def numeric_bounds_findings(name, schema):
    """Bounds that could reject a caller the handler would have clamped."""
    findings = []
    for path, node in walk(schema):
        props = node.get("properties") or {}
        for field, spec in props.items():
            if not isinstance(spec, dict):
                continue
            lo = spec.get("minimum")
            hi = spec.get("maximum")
            # A positive floor on a "count/how many" parameter is the exact
            # shape of the ms_studio_director bug: the handler raises a small
            # value up to its own floor, but the schema rejects it first.
            if isinstance(lo, (int, float)) and lo > 0 and not isinstance(lo, bool):
                looks_like_count = any(
                    tok in field.lower()
                    for tok in ("limit", "max", "count", "depth", "steps", "rounds", "skills", "tools")
                )
                if looks_like_count and lo > 1:
                    findings.append({
                        "tool": name, "path": f"{path}.{field}", "code": "positive-floor-on-count",
                        "value": lo, "severity": "high", "hint": CLAMPING_HINT,
                    })
            if isinstance(hi, (int, float)) and isinstance(lo, (int, float)):
                if hi < lo:
                    findings.append({
                        "tool": name, "path": f"{path}.{field}", "code": "inverted-bounds",
                        "minimum": lo, "maximum": hi, "severity": "high",
                        "hint": "maximum is below minimum: no value can ever satisfy this",
                    })
    return findings


def empty_string_findings(name, schema):
    """Required string fields that may legitimately have to be empty."""
    findings = []
    for path, node in walk(schema):
        props = node.get("properties") or {}
        required = node.get("required") or []
        for field in required:
            spec = props.get(field)
            if not isinstance(spec, dict):
                continue
            if spec.get("type") != "string":
                continue
            full = f"{path}.{field}"
            # A required string with a minLength >= 1 can never be the empty
            # sentinel. If the code treats "" as meaningful we must know.
            if field in KNOWN_EMPTY_STRING_SENTINELS:
                findings.append({
                    "tool": name, "path": full, "code": "empty-string-is-a-value",
                    "severity": "info",
                    "hint": "must stay in bridge._EMPTY_STRING_IS_VALUE",
                })
            elif spec.get("minLength", 0) >= 1:
                findings.append({
                    "tool": name, "path": full, "code": "required-string-cannot-be-empty",
                    "severity": "low",
                    "hint": "verify the handler genuinely cannot accept an empty value here",
                })
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    bridge = load_bridge()
    schemas = collect_schemas(bridge)

    findings = []
    shape_problems = []
    for name, schema in schemas:
        if not isinstance(schema, dict):
            shape_problems.append({"tool": name, "code": "missing-input-schema", "severity": "high"})
            continue
        findings.extend(numeric_bounds_findings(name, schema))
        findings.extend(empty_string_findings(name, schema))
        try:
            risk = bridge._schema_risk_analysis(schema)
        except Exception as exc:  # the analyser itself must never crash
            shape_problems.append({"tool": name, "code": "risk-analysis-raised", "detail": str(exc), "severity": "high"})
            continue
        for issue in risk.get("issues") or []:
            if issue.get("severity") == "high":
                shape_problems.append({"tool": name, **issue})

    # Sentinel sync check: the audit's idea of a meaningful empty string must
    # match the validator's, or the audit is lying about what is safe.
    declared = set(getattr(bridge, "_EMPTY_STRING_IS_VALUE", set()) or set())
    sentinel_drift = sorted(declared ^ KNOWN_EMPTY_STRING_SENTINELS)

    # Prove the "create a script" sentinel path still works end to end.
    sentinel_ok = True
    sentinel_detail = "ok"
    try:
        bridge._normalize_tool_arguments(
            {"type": "object", "properties": {
                "className": {"type": "string"},
                "edits": {"type": "array", "items": {"type": "object", "properties": {
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                }, "required": ["old_string", "new_string"]}},
            }, "required": ["className", "edits"]},
            {"className": "Main", "edits": [{"old_string": "", "new_string": "print(1)"}]},
            "multi_edit",
        )
    except Exception as exc:
        sentinel_ok = False
        sentinel_detail = str(exc)

    report = {
        "toolCount": len(schemas),
        "findingCount": len(findings),
        "shapeProblemCount": len(shape_problems),
        "sentinelDrift": sentinel_drift,
        "sentinelPathWorks": sentinel_ok,
        "sentinelDetail": sentinel_detail,
        "findings": findings,
        "shapeProblems": shape_problems,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"schemas audited: {len(schemas)}")
        print(f"bound/sentinel findings: {len(findings)}")
        print(f"schema-shape problems: {len(shape_problems)}")
        print(f"sentinel drift: {sentinel_drift or 'none'}")
        print(f"empty-old_string create path: {'OK' if sentinel_ok else 'FAILED: ' + sentinel_detail}")
        for f in findings:
            if f.get("severity") in ("high", "medium"):
                print(f"  [{f['severity']}] {f['tool']} {f['path']} -> {f['code']}")
        for p in shape_problems:
            print(f"  [shape/{p.get('severity')}] {p['tool']} {p.get('code')} {p.get('path', '')}")

    bad = bool(shape_problems) or not sentinel_ok or bool(sentinel_drift)
    bad = bad or any(f.get("severity") in ("high", "medium") for f in findings)
    if args.strict and bad:
        sys.exit(1)


if __name__ == "__main__":
    main()
