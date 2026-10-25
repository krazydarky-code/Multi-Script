# SPDX-License-Identifier: GPL-3.0-or-later
"""assist_tools.py - discoverability + performance helpers that sit beside the catalogue.

  ms_find_tool   Ranked search over EVERY tool the model can call right now (Multi-Script
                 direct tools, native engine toolkits, live engine MCP servers, companion
                 tools). Returns the best matches with required parameters and a
                 copy-ready call, so a model never has to read the ~120k-character
                 catalogue to find "the tool that does X".
  ms_tool_stats  Per-tool call count / error rate / latency measured by this bridge, so
                 slow or failing tools are visible instead of guessed at.

Pure stdlib. The bridge passes in the live tool list; nothing here touches an engine.
"""
from __future__ import annotations

import json
import re
import threading
import time

try:  # optional: the bridge ships it, but never hard-require it
    import schema_repair as _repair
except Exception:  # pragma: no cover
    _repair = None

DEFINITIONS = [
    {
        "name": "ms_find_tool",
        "description": ("Find the right tool fast: ranked search across every tool available right now (direct tools, "
                        "native engine tools, live engine servers). Give a plain-language goal like 'bevel edges', "
                        "'move a part', 'take a screenshot' and get the best matches with required parameters and a "
                        "copy-ready call. Use this instead of reading the whole catalogue."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What you want to do, in plain words."},
                "engine": {"type": "string", "description": "Optional filter: roblox, unity, godot, blender, or general."},
                "limit": {"type": "integer", "description": "Max matches (default 8, max 25)."},
                "writes_only": {"type": "boolean", "description": "Only tools that change things."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "ms_tool_stats",
        "description": ("Show measured performance of tools called through this bridge: calls, failures, average and "
                        "slowest latency, last error. Use it to avoid slow/failing tools and to explain lag."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sort": {"type": "string", "description": "slowest | failing | busiest (default slowest)."},
                "limit": {"type": "integer", "description": "How many tools to list (default 10)."},
                "reset": {"type": "boolean", "description": "Clear the statistics after reading."},
            },
        },
    },
]
DEFINITIONS += [
    {
        "name": "ms_stage_code",
        "description": ("Upload BIG code or text in small pieces so no single command is too long for the chat to carry. "
                        "Call it repeatedly with the same `name`: each call appends one `chunk` (keep chunks under ~2000 "
                        "characters, cut at line boundaries). Then run it with ms_run_staged_luau or save it with "
                        "ms_write_staged. `reset:true` starts the buffer over; `action:\"show\"` reports size and the last "
                        "lines; `action:\"clear\"` deletes it."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Buffer name, e.g. \"shop_ui\"."},
                "chunk": {"type": "string", "description": "The next piece of text (appended exactly as given)."},
                "reset": {"type": "boolean", "description": "Clear the buffer before appending this chunk."},
                "action": {"type": "string", "description": "append (default) | show | clear"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "ms_run_staged_luau",
        "description": ("Run the Luau staged under `name` (see ms_stage_code) in Roblox Studio exactly as assembled, then "
                        "clear the buffer unless keep:true. Same result as execute_luau, without a giant command."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Buffer name used with ms_stage_code."},
                "datamodel_type": {"type": "string", "description": "Edit (default), Server or Client."},
                "studio_id": {"type": "string", "description": "Roblox Studio id (from list_roblox_studios) when more than one is open."},
                "keep": {"type": "boolean", "description": "Keep the buffer after running (default false)."},
                "timeout_seconds": {"type": "integer", "description": "Default 120."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "ms_write_staged",
        "description": ("Save the text staged under `name` into a Roblox script with the native multi_edit: creates the "
                        "script when it does not exist, or replaces `old_string` (default empty = create/append) with the "
                        "staged text. The buffer is cleared after a successful write unless keep:true. Applied ONCE - "
                        "repeat calls are refused for 60 seconds so an empty old_string cannot double the content."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Buffer name used with ms_stage_code."},
                "file_path": {"type": "string", "description": "Script path, e.g. game.ServerScriptService.Main"},
                "old_string": {"type": "string", "description": "Text to replace; empty creates the script / inserts at the start."},
                "datamodel_type": {"type": "string", "description": "Edit (default)."},
                "studio_id": {"type": "string"},
                "keep": {"type": "boolean"},
            },
            "required": ["name", "file_path"],
        },
    },
]
DEFINITIONS += [
    {
        "name": "ms_request_blueprint",
        "description": ("Turn even a very short or messy request into an execution-ready blueprint without replacing the "
                        "user's words or inventing hard requirements. Produces reversible defaults, risks, phases and "
                        "observable acceptance criteria tailored to the selected engine."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "request": {"type": "string", "description": "The user's request, preserved verbatim."},
                "engine": {"type": "string", "enum": ["roblox", "unity", "godot", "blender", "general"],
                           "description": "Target engine, or general when not known."},
                "project_context": {"type": "string", "description": "Known project conventions or current state."},
                "constraints": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
                "quality": {"type": "string", "enum": ["functional", "polished", "portfolio"],
                            "description": "Desired finish; default polished."},
            },
            "required": ["request"],
        },
    },
    {
        "name": "ms_tool_workflow",
        "description": ("Build a dependency-safe workflow from tools that are genuinely advertised right now. Returns "
                        "copy-ready inspect, implement and verify calls; it never invents a tool name. Use after "
                        "ms_request_blueprint or whenever a model is unsure which commands should do the work."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string", "description": "What the finished work must accomplish."},
                "engine": {"type": "string", "enum": ["roblox", "unity", "godot", "blender", "general"]},
                "max_steps": {"type": "integer", "minimum": 3, "maximum": 12, "description": "Default 7."},
                "include_read_only": {"type": "boolean", "description": "Include discovery/read-back calls; default true."},
            },
            "required": ["objective"],
        },
    },
    {
        "name": "ms_completion_gate",
        "description": ("Strictly check whether observable evidence covers every acceptance criterion. It refuses vague "
                        "'done/works/passed' claims, reports uncovered requirements and gives the next verification action. "
                        "This is an evidence gate, not a substitute for running native tests."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string"},
                "criteria": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 40},
                "evidence": {"type": "array", "items": {"type": "string"}, "maxItems": 80,
                             "description": "Concrete read-backs, test output, captures, paths or measurements."},
                "known_issues": {"type": "array", "items": {"type": "string"}, "maxItems": 40},
                "require_clean_run": {"type": "boolean", "description": "Require explicit clean log/build evidence."},
            },
            "required": ["criteria"],
        },
    },
]
# 6.27: presentation quality tools. The most common weak-provider failure is a
# technically-correct but visually empty result (flat baseplate, default
# lighting, no landmark). These two tools make "looks finished" concrete and
# checkable without inventing an art direction for the user.
DEFINITIONS += [
    {
        "name": "ms_presentation_pass",
        "description": ("Turn 'the world looks flat/empty' into a concrete, engine-aware presentation pass: terrain and "
                        "height variation, first-view landmark composition, lighting + sky + atmosphere values to set, "
                        "dressing density and scale rules, a low-tier fallback, and a camera-verified acceptance gate. "
                        "It never picks an art style for the user; it lists the decisions that must be made and states "
                        "who owns them. Use before claiming any world, map, scene or environment is finished."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "scene": {"type": "string", "description": "What the world/scene is, in the user's own words."},
                "engine": {"type": "string", "enum": ["roblox", "unity", "godot", "blender", "general"]},
                "focus": {"type": "array", "maxItems": 9,
                          "items": {"type": "string", "enum": ["terrain", "lighting", "sky", "landmark", "dressing", "scale", "color", "audio", "camera"]},
                          "description": "Limit the pass to these aspects; default covers all."},
                "quality_tier": {"type": "string", "enum": ["low", "balanced", "high"],
                                 "description": "Weakest target device tier; default balanced."},
            },
            "required": ["scene"],
        },
    },
    {
        "name": "ms_vertical_slice_gate",
        "description": ("Check a game build or plan for a COMPLETE playable loop before adding breadth. Matches the "
                        "request and the listed features against the loop elements (entry, objective, interaction, "
                        "feedback, success, failure, reward, restart) and reports exactly which are missing or only "
                        "stubbed, in fix order. A world with no loop is a diorama, not a game."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "request": {"type": "string", "description": "The user's request, preserved verbatim."},
                "features": {"type": "array", "items": {"type": "string"}, "maxItems": 60,
                             "description": "Systems/features built or planned so far, one short phrase each."},
                "engine": {"type": "string", "enum": ["roblox", "unity", "godot", "blender", "general"]},
            },
            "required": ["request"],
        },
    },
]
NAMES = {d["name"] for d in DEFINITIONS}

# ── staged buffers ───────────────────────────────────────────────────────────
_STAGE: dict = {}
_STAGE_LOCK = threading.Lock()
_STAGE_MAX = 2_000_000
_STAGE_TTL = 3600
_WRITTEN: dict = {}   # (name, file_path, sha) -> time, to refuse accidental double application


def _stage_gc() -> None:
    now = time.time()
    for k in [k for k, v in _STAGE.items() if now - v["at"] > _STAGE_TTL]:
        _STAGE.pop(k, None)
    for k in [k for k, t in _WRITTEN.items() if now - t > 120]:
        _WRITTEN.pop(k, None)


def _sha(text: str) -> str:
    import hashlib
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:8]


def _stage_key(args: dict) -> str:
    n = re.sub(r"[^A-Za-z0-9_.-]", "_", str(args.get("name") or "").strip())[:60]
    if not n:
        raise RuntimeError("give a buffer `name`, e.g. {\"name\":\"main\",\"chunk\":\"...\"}")
    return n


def _flag(v) -> bool:
    return v in (True, "true", "True", "TRUE", 1, "1", "yes")


def _stage(args: dict) -> dict:
    key = _stage_key(args)
    action = str(args.get("action") or "append").lower()
    with _STAGE_LOCK:
        _stage_gc()
        if action == "clear":
            existed = _STAGE.pop(key, None) is not None
            return {"name": key, "cleared": existed}
        buf = _STAGE.setdefault(key, {"text": "", "parts": 0, "at": time.time()})
        if _flag(args.get("reset")):
            buf.update(text="", parts=0)
        if action == "show":
            tail = buf["text"].splitlines()[-5:]
            return {"name": key, "chars": len(buf["text"]), "lines": buf["text"].count("\n") + (1 if buf["text"] else 0),
                    "parts": buf["parts"], "sha": _sha(buf["text"]), "last_lines": tail}
        chunk = args.get("chunk")
        if chunk is None:
            lines = args.get("lines")
            chunk = "\n".join(str(x) for x in lines) + "\n" if isinstance(lines, list) else ""
        chunk = str(chunk)
        if not chunk:
            raise RuntimeError("`chunk` is empty - send the next piece of text")
        if len(buf["text"]) + len(chunk) > _STAGE_MAX:
            raise RuntimeError(f"buffer would exceed {_STAGE_MAX} characters")
        buf["text"] += chunk
        buf["parts"] += 1
        buf["at"] = time.time()
        return {"name": key, "added": len(chunk), "chars": len(buf["text"]), "parts": buf["parts"], "sha": _sha(buf["text"]),
                "next": "Send the next chunk, or run it with ms_run_staged_luau / save it with ms_write_staged."}


def _take(args: dict) -> tuple:
    key = _stage_key(args)
    with _STAGE_LOCK:
        _stage_gc()
        buf = _STAGE.get(key)
        if not buf or not buf["text"]:
            raise RuntimeError(f"nothing is staged under '{key}' - call ms_stage_code first")
        return key, buf["text"]


def _release(key: str, args: dict) -> None:
    if not _flag(args.get("keep")):
        with _STAGE_LOCK:
            _STAGE.pop(key, None)

# ── call statistics ──────────────────────────────────────────────────────────
_LOCK = threading.Lock()
_STATS: dict = {}


def record(name: str, ms: float, ok: bool, error: str = "") -> None:
    try:
        with _LOCK:
            s = _STATS.setdefault(name, {"calls": 0, "errors": 0, "total_ms": 0.0, "max_ms": 0.0, "last_error": ""})
            s["calls"] += 1
            s["total_ms"] += ms
            s["max_ms"] = max(s["max_ms"], ms)
            if not ok:
                s["errors"] += 1
                s["last_error"] = str(error)[:200]
    except Exception:
        pass


def _stats(args: dict) -> dict:
    sort = str(args.get("sort") or "slowest").lower()
    try:
        limit = max(1, min(50, int(args.get("limit") or 10)))
    except Exception:
        limit = 10
    with _LOCK:
        rows = [dict(name=n, calls=s["calls"], errors=s["errors"],
                     avg_ms=round(s["total_ms"] / max(1, s["calls"]), 1), max_ms=round(s["max_ms"], 1),
                     last_error=s["last_error"]) for n, s in _STATS.items()]
        if args.get("reset"):
            _STATS.clear()
    key = {"failing": lambda r: (-r["errors"], -r["calls"]),
           "busiest": lambda r: -r["calls"]}.get(sort, lambda r: -r["avg_ms"])
    rows.sort(key=key)
    total = sum(r["calls"] for r in rows)
    return {"tools_measured": len(rows), "total_calls": total, "sorted_by": sort if sort in ("failing", "busiest") else "slowest",
            "tools": rows[:limit],
            "tip": "Slow tools: batch work (ms_native_batch / multi_edit) or narrow the query. Failing tools: read last_error, then ms_native_debug."}


# ── search ───────────────────────────────────────────────────────────────────
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"a", "an", "the", "to", "of", "for", "and", "or", "in", "on", "with", "my", "me", "i", "it", "is", "do", "how",
         "can", "you", "want", "need", "please", "make", "use", "that", "this", "from", "into"}
# Plain-words → vocabulary the tool names actually use.
_SYNONYMS = {
    "screenshot": ["screen", "capture", "screenshot", "viewport", "render"], "picture": ["screenshot", "capture", "image"],
    "image": ["screenshot", "capture", "texture"], "photo": ["screenshot", "capture"],
    "move": ["move", "transform", "position", "translate"], "rotate": ["transform", "rotate"],
    "delete": ["delete", "remove"], "remove": ["delete", "remove"], "create": ["create", "add", "spawn", "build"],
    "spawn": ["create", "spawn", "instance"], "script": ["script", "code", "luau", "gdscript", "csharp"],
    "code": ["script", "run", "execute"], "run": ["run", "execute", "play"], "test": ["playtest", "test", "verify"],
    "fast": ["optimize", "performance", "profiler"], "lag": ["optimize", "performance", "profiler", "frame"],
    "slow": ["optimize", "performance", "profiler"], "performance": ["optimize", "profiler", "budget"],
    "ui": ["gui", "ui", "interface", "canvas"], "gui": ["gui", "ui"], "menu": ["ui", "gui"],
    "light": ["lighting", "light"], "sound": ["audio", "sound"], "music": ["audio"],
    "animate": ["animation", "keyframe", "tween"], "anim": ["animation"], "rig": ["armature", "rig", "skeleton"],
    "terrain": ["terrain", "generate"], "map": ["level", "terrain", "blockout"], "level": ["level", "blockout"],
    "error": ["console", "debug", "error", "diagnose"], "bug": ["console", "debug", "triage"],
    "undo": ["undo", "history", "checkpoint"], "save": ["export", "snapshot", "checkpoint"],
    "export": ["export"], "import": ["import", "asset"], "asset": ["asset", "insert"],
    "find": ["find", "search", "list"], "search": ["search", "find"], "read": ["read", "get", "inspect"],
    "inspect": ["inspect", "properties", "get"], "edit": ["edit", "set", "modify", "patch"],
    "rename": ["rename"], "copy": ["clone", "duplicate"], "clone": ["clone", "duplicate"],
    "material": ["material", "texture", "pbr"], "color": ["material", "color"], "particle": ["particle", "vfx"],
    "camera": ["camera"], "physics": ["physics", "collision", "constraint"], "npc": ["npc", "ai", "pathfinding"],
    "movement": ["movement", "locomotion", "character", "controller", "gameplay", "move"],
    "character": ["character", "controller", "rig"], "file": ["file", "workspace", "read", "write"],
    "project": ["project", "workspace"], "build": ["build", "package", "create"],
    "cool": ["polish", "style", "feedback", "art", "quality"], "better": ["polish", "quality", "improve", "usability"],
    "pretty": ["visual", "polish", "style", "material"], "professional": ["production", "quality", "verify", "polish"],
    "game": ["gameplay", "level", "player", "scene"], "idea": ["concept", "blueprint", "design"],
    "everything": ["project", "audit", "quality", "production"], "accessible": ["accessibility", "input", "contrast", "focus"],
}


def _tokens(text: str) -> list:
    return [w for w in _WORD.findall(str(text or "").lower().replace("_", " ")) if w not in _STOP and len(w) > 1]


def _expand(tokens: list) -> dict:
    out = {}
    for t in tokens:
        out[t] = max(out.get(t, 0), 3.0)
        for s in _SYNONYMS.get(t, []):
            out[s] = max(out.get(s, 0), 1.5)
        if t.endswith("s") and len(t) > 3:
            out[t[:-1]] = max(out.get(t[:-1], 0), 2.5)
    return out


def _engine_of(tool: dict) -> str:
    name = str(tool.get("name") or "")
    m = re.match(r"(?:ms_)?(roblox|unity|godot|blender)_", name)
    if m:
        return m.group(1)
    srv = str(tool.get("server") or "")
    return srv if srv in ("roblox", "unity", "godot", "blender") else "general"


def _summary(tool: dict) -> str:
    d = str(tool.get("description") or "").strip().split("\n")[0]
    d = re.sub(r"^\[[^\]]*\]\s*", "", d)
    return (d[:140] + "…") if len(d) > 141 else d


def _call_template(tool: dict) -> dict:
    schema = tool.get("inputSchema")
    try:
        ex = _repair.example(schema) if (_repair is not None and isinstance(schema, dict)) else {}
    except Exception:
        ex = {}
    return {"command": tool.get("name"), "params": ex}


def find(tools: list, args: dict) -> dict:
    query = str(args.get("query") or "").strip()
    if not query:
        raise RuntimeError("ms_find_tool needs a 'query', e.g. {\"query\":\"take a screenshot\"}")
    try:
        limit = max(1, min(25, int(args.get("limit") or 8)))
    except Exception:
        limit = 8
    want_engine = str(args.get("engine") or "").strip().lower()
    writes_only = args.get("writes_only") in (True, "true", "True", 1, "1")
    weights = _expand(_tokens(query))
    qnorm = " ".join(_tokens(query))
    scored = []
    seen = set()
    for t in tools:
        name = str(t.get("name") or "")
        if not name or name in seen or name in NAMES:
            continue
        seen.add(name)
        eng = _engine_of(t)
        if want_engine and want_engine != eng:
            continue
        desc = str(t.get("description") or "")
        if writes_only and "read-only" in desc.lower().split("]")[0]:
            continue
        ntoks = set(_tokens(name))
        dtoks = set(_tokens(desc))
        props = " ".join(((t.get("inputSchema") or {}).get("properties") or {}).keys()) if isinstance(t.get("inputSchema"), dict) else ""
        ptoks = set(_tokens(props))
        score = 0.0
        for w, wt in weights.items():
            if w in ntoks: score += 4 * wt
            elif any(w in x or x in w for x in ntoks if len(x) > 3 and len(w) > 3): score += 2 * wt
            if w in dtoks: score += 1.2 * wt
            if w in ptoks: score += 0.5 * wt
        if qnorm and qnorm.replace(" ", "_") in name: score += 12
        if score <= 0:
            continue
        if re.search(r"\b(player|character|locomotion)\b",query,re.I) and re.search(r"\b(movement|move|feel|controller)\b",query,re.I) and re.search(r"_(?:move_file|file|ws_move)$",name):
            score *= 0.1
        # prefer concrete engine tools over generic planners for an action request
        if name.startswith("ms_") and eng == "general" and re.search(r"(plan|director|polish|audit|production|studio)$", name):
            score *= 0.8
        scored.append((score, t, eng))
    scored.sort(key=lambda x: (-x[0], str(x[1].get("name"))))
    matches = []
    for score, t, eng in scored[:limit]:
        schema = t.get("inputSchema") if isinstance(t.get("inputSchema"), dict) else {}
        matches.append({
            "name": t.get("name"), "engine": eng, "server": t.get("server") or "zeroscript",
            "does": _summary(t), "required": list(schema.get("required") or []),
            "call": _call_template(t), "score": round(score, 1),
        })
    out = {"query": query, "searched": len(seen), "matches": matches}
    if not matches:
        out["hint"] = ("Nothing matched. Try fewer/other words, drop the engine filter, or call list_commands with "
                       "{\"query\":\"...\"}. Disabled engines (Settings → Engines) are not searched.")
    return out


# ── weak-prompt → verified execution helpers ───────────────────────────────
_DOMAIN_RULES = [
    ("ui", re.compile(r"\b(ui|ux|gui|hud|menu|shop|button|screen|interface|layout)\b", re.I)),
    ("gameplay", re.compile(r"\b(game|player|combat|movement|obby|level|enemy|quest|inventory)\b", re.I)),
    ("code", re.compile(r"\b(code|script|function|module|bug|error|crash|refactor)\b", re.I)),
    ("world", re.compile(r"\b(scene|map|world|terrain|lighting|environment|camera)\b", re.I)),
    ("art", re.compile(r"\b(model|mesh|texture|material|shader|vfx|animation|rig|art)\b", re.I)),
    ("network", re.compile(r"\b(multiplayer|server|client|remote|network|replicat|sync)\b", re.I)),
    ("data", re.compile(r"\b(save|data|database|datastore|profile|migration)\b", re.I)),
    ("performance", re.compile(r"\b(lag|fps|performance|memory|optim|slow|fast)\w*", re.I)),
]


def _domains_for(text: str) -> list:
    found = [name for name, rx in _DOMAIN_RULES if rx.search(text)]
    return found or ["gameplay"]


def _engine_defaults(engine: str) -> dict:
    return {
        "roblox": {
            "architecture": "server-authoritative Luau modules; validate every remote and persistent write",
            "targets": "phone, keyboard/mouse and controller; StreamingEnabled-safe",
            "proof": "Studio Play/Run, two-player local server where relevant, Output clean, native read-back",
        },
        "unity": {
            "architecture": "small C# components, prefabs and data assets following the existing project architecture",
            "targets": "the project's configured platforms and input actions",
            "proof": "compile, relevant Edit/Play Mode tests, Play Mode exercise, Console clean, final scene read-back",
        },
        "godot": {
            "architecture": "typed GDScript, composed scenes/resources and signals; avoid unnecessary globals",
            "targets": "the project's configured desktop/mobile/web targets",
            "proof": "project run, debugger clean, focused scene exercise and final file/tree read-back",
        },
        "blender": {
            "architecture": "non-destructive modifiers where useful, named collections and export-safe transforms",
            "targets": "the stated destination engine/render target with explicit scale and budget",
            "proof": "viewport/render capture plus scale, topology, UV/material and export validation",
        },
        "general": {
            "architecture": "match existing conventions; separate data, behavior and presentation",
            "targets": "the weakest intended device and all required input methods",
            "proof": "real build/test output, exercised critical path and final artifact read-back",
        },
    }[engine]


def _request_blueprint(args: dict) -> dict:
    request = str(args.get("request") or "").strip()
    if not request:
        raise RuntimeError("ms_request_blueprint needs `request`")
    engine = str(args.get("engine") or "general").lower()
    if engine not in ("roblox", "unity", "godot", "blender", "general"):
        engine = "general"
    quality = str(args.get("quality") or "polished").lower()
    if quality not in ("functional", "polished", "portfolio"):
        quality = "polished"
    domains = _domains_for(request)
    weak = len(_tokens(request)) < 8 or len(request) < 48
    defaults = _engine_defaults(engine)
    criteria = [
        "The requested outcome exists in the real project and is reachable from its intended entry point.",
        "The primary user journey works from start to finish, including empty, loading, failure and recovery states where relevant.",
        f"Validation is concrete: {defaults['proof']}.",
        "No new errors, warnings that indicate breakage, placeholders or disconnected demo-only pieces remain.",
    ]
    if "ui" in domains:
        criteria.append("Layout, focus, readable contrast and interaction targets work at the smallest and largest supported sizes.")
    if "network" in domains or "data" in domains:
        criteria.append("Authority, malformed input, retry/failure and compatibility behavior are explicitly exercised.")
    if "performance" in domains or quality == "portfolio":
        criteria.append("A target-tier budget is stated and the dominant cost is measured rather than guessed.")
    phases = [
        {"phase": "discover", "action": "Inspect the real project, live schemas, conventions and current failure/state before editing."},
        {"phase": "define", "action": "Convert the request into a smallest complete vertical slice and state only reversible assumptions."},
        {"phase": "implement", "action": f"Build the integrated result using {defaults['architecture']}."},
        {"phase": "integrate", "action": "Connect navigation, data, input, feedback and lifecycle instead of leaving an isolated artifact."},
        {"phase": "verify", "action": defaults["proof"] + "."},
        {"phase": "critic-fix", "action": "Score the weakest quality dimension, fix it, then repeat verification once."},
    ]
    return {
        "originalRequest": request,
        "engine": engine,
        "quality": quality,
        "weakPrompt": weak,
        "domains": domains,
        "projectContext": str(args.get("project_context") or ""),
        "explicitConstraints": [str(x) for x in (args.get("constraints") or []) if str(x).strip()],
        "safeDefaults": {
            "decisionPolicy": "Preserve every explicit requirement; inspect before assuming; choose reversible defaults only when needed and state them.",
            "architecture": defaults["architecture"],
            "targetCoverage": defaults["targets"],
            "scopePolicy": "Finish one coherent vertical slice before optional breadth; never hide missing work behind placeholders.",
        },
        "phases": phases,
        "acceptanceCriteria": criteria,
        "next": "Call ms_tool_workflow with this request and engine, execute the real calls, then pass the criteria and evidence to ms_completion_gate.",
    }


def _tool_workflow(tools: list, args: dict) -> dict:
    objective = str(args.get("objective") or "").strip()
    if not objective:
        raise RuntimeError("ms_tool_workflow needs `objective`")
    engine = str(args.get("engine") or "").strip().lower()
    if engine == "general":
        engine = ""
    try:
        cap = max(3, min(12, int(args.get("max_steps") or 7)))
    except Exception:
        cap = 7
    queries = [
        ("inspect", "inspect read current state " + objective),
        ("implement", objective),
        ("verify", "test verify screenshot console read back " + objective),
    ]
    chosen, seen = [], set()
    quotas = {
        "inspect": max(1, cap // 3),
        "verify": max(1, cap // 3),
    }
    quotas["implement"] = max(1, cap - quotas["inspect"] - quotas["verify"])
    ranked={phase:find(tools,{"query":query,"engine":engine,"limit":25})["matches"] for phase,query in queries}
    # Reserve a first choice for every phase before filling extras. A greedy
    # inspection quota used to consume implementation/verification tools first.
    for round_index in range(max(quotas.values())):
        for phase,_ in queries:
            if round_index>=quotas[phase] or len(chosen)>=cap: continue
            if args.get("include_read_only") is False and phase=="inspect": continue
            match=next((m for m in ranked[phase] if m.get("name") and m["name"] not in seen),None)
            if match:
                seen.add(match["name"]);chosen.append({"phase":phase,**match})
    chosen.sort(key=lambda step:("inspect","implement","verify").index(step["phase"]))
    phases_present = {x["phase"] for x in chosen}
    return {
        "objective": objective,
        "engine": engine or "any connected engine",
        "liveCatalogueOnly": True,
        "steps": chosen,
        "coverage": {p: p in phases_present for p in ("inspect", "implement", "verify")},
        "executionRules": [
            "Read before mutating and use the exact advertised schema in each returned call.",
            "After an error, change the call based on the exact failure; never repeat an unchanged failed mutation.",
            "Read back the final native state and retain concrete output for ms_completion_gate.",
        ],
        "warning": ("No matching live tools were found. Refresh the bridge/engine catalogue or broaden the engine filter." if not chosen else
                    "Implementation coverage is unavailable in this catalogue. Connect the target editor and refresh its live tools before attempting changes." if "implement" not in phases_present else ""),
    }


def _completion_gate(args: dict) -> dict:
    criteria = [str(x).strip() for x in (args.get("criteria") or []) if str(x).strip()]
    evidence = [str(x).strip() for x in (args.get("evidence") or []) if str(x).strip()]
    issues = [str(x).strip() for x in (args.get("known_issues") or []) if str(x).strip()]
    if not criteria:
        raise RuntimeError("ms_completion_gate needs at least one acceptance criterion")
    vague = {"ok", "done", "works", "working", "passed", "looks good", "fixed", "complete"}
    usable = [e for e in evidence if len(e) >= 12 and e.lower().strip(".!") not in vague]
    coverage = []
    for criterion in criteria:
        words = {w for w in _tokens(criterion) if len(w) > 3}
        best, best_score = "", 0
        for item in usable:
            iw = set(_tokens(item))
            score = len(words & iw)
            if score > best_score:
                best, best_score = item, score
        covered = best_score >= (1 if len(words) < 5 else 2)
        coverage.append({"criterion": criterion, "covered": covered, "evidence": best if covered else ""})
    clean_required = _flag(args.get("require_clean_run"))
    clean = any(re.search(r"\b(0 errors?|zero errors?|exit code 0|build succeeded|tests? passed|console clean|output clean)\b", e, re.I) for e in usable)
    missing = [x["criterion"] for x in coverage if not x["covered"]]
    if clean_required and not clean:
        missing.append("Provide explicit clean build/test/log evidence (for example exit code 0 or zero errors).")
    passed = not missing and not issues
    return {
        "objective": str(args.get("objective") or ""),
        "verdict": "pass" if passed else "revise",
        "criteria": coverage,
        "usableEvidence": len(usable),
        "vagueEvidenceRejected": len(evidence) - len(usable),
        "knownIssues": issues,
        "missing": missing,
        "next": "Report the verified result." if passed else "Run the missing native checks, fix known issues, then call ms_completion_gate again with the new evidence.",
    }


# ── presentation pass (6.27) ───────────────────────────────────────────────
_PRESENTATION_LIGHTING = {
    "roblox": ("Lighting service: set a deliberate ClockTime, Brightness and ExposureCompensation; add an Atmosphere "
               "(density, haze, tint), a Sky, and at most two post effects (SunRays, Bloom or ColorCorrection); keep "
               "GlobalShadows on and verify the frame still meets budget on the weakest tier"),
    "unity": ("a Volume profile: sky and fog, exposure, one color-grading pass and at most two post effects; baked or "
              "mixed lighting with light/reflection probes on static geometry"),
    "godot": ("a WorldEnvironment: procedural or panoramic sky, fog or volumetric fog, tonemap and restrained glow; "
              "bake light for static geometry where the target allows"),
    "blender": ("a World shader plus key/fill/rim lights with one dominant direction; match Eevee/Cycles settings to "
                "the export or render target"),
    "general": ("one dominant key-light direction, ambient fill, a sky and fog/atmosphere treatment, and one "
                "restrained post pass"),
}

_PRESENTATION_CHECKS = {
    "terrain": {
        "risk": "Play area is one perfectly flat slab",
        "fix": ("Add height variation with the terrain editor or procedural placement: gentle rolls in open areas, "
                "raised edges or a valley to frame the play space, and ramps - not jumps - where the player must cross"),
        "verify": "From the player spawn camera, the horizon is not a single straight line in any direction.",
    },
    "landmark": {
        "risk": "No focal point; the eye lands nowhere",
        "fix": ("Build one clear landmark visible from spawn (a tower, tree, gate or hero prop sized well above "
                "surroundings) and align the main path or sightline toward it"),
        "verify": "A first-time player can name where to go within three seconds of spawning.",
    },
    "sky": {
        "risk": "Default or empty sky",
        "fix": "Set a sky that matches the chosen mood and time of day, with horizon haze so ground meets sky softly.",
        "verify": "Sky, fog and ground share a coherent value range at the horizon line.",
    },
    "lighting": {
        "risk": "Flat default lighting: no shadows, no mood, washed-out colors",
        "fix": None,  # filled per engine below
        "verify": "Key props cast readable shadows and the scene reads at a glance in a small screenshot.",
    },
    "dressing": {
        "risk": "Empty ground or evenly scattered props",
        "fix": ("Cluster dressing at decision points and sightline anchors (path forks, doorways, the landmark base); "
                "leave breathing room between clusters; vary rotation, scale and tint on every repeated prop"),
        "verify": "No two adjacent prop clusters are identical, and open sightlines to the landmark stay clear.",
    },
    "scale": {
        "risk": "Scale is unreadable - props could be toys or mountains",
        "fix": ("Include consistent human-scale references (doors, rails, crates, steps) and size every prop against "
                "the avatar or a stated unit before placing it"),
        "verify": "Doorways, steps and rails match the character's dimensions when walked through in play mode.",
    },
    "color": {
        "risk": "Every object a different saturated color",
        "fix": ("Preserve the project's existing palette; if there is none, choose one dominant color family plus one "
                "accent, state the choice, and keep interactive objects on the accent so they read as usable"),
        "verify": "Interactive objects are identifiable by color/shape alone in a grayscale screenshot.",
    },
    "audio": {
        "risk": "Silent world",
        "fix": ("Add one looping ambient bed matched to the environment and positional accents at interactive or "
                "landmark spots, with volumes mixed under UI sounds"),
        "verify": "Ambient audio loops without a seam and positional sources are located where they appear.",
    },
    "camera": {
        "risk": "Verified only from the editor's top view",
        "fix": ("Frame the player's actual first view (spawn camera, default FOV) and compose terrain, landmark and "
                "dressing for that frame before anywhere else"),
        "verify": "A capture from the real spawn camera at the target FOV is the reference screenshot for the pass.",
    },
}

_PRESENTATION_ORDER = ["camera", "terrain", "landmark", "sky", "lighting", "dressing", "scale", "color", "audio"]


def _presentation_pass(args: dict) -> dict:
    scene = str(args.get("scene") or "").strip()
    if not scene:
        raise RuntimeError("ms_presentation_pass needs `scene` - what is the world, in the user's words")
    engine = str(args.get("engine") or "general").lower()
    if engine not in _PRESENTATION_LIGHTING:
        engine = "general"
    tier = str(args.get("quality_tier") or "balanced").lower()
    if tier not in ("low", "balanced", "high"):
        tier = "balanced"
    focus = [str(x) for x in (args.get("focus") or []) if str(x) in _PRESENTATION_CHECKS]
    aspects = focus or list(_PRESENTATION_ORDER)
    aspects = [a for a in _PRESENTATION_ORDER if a in aspects]
    checks = []
    for a in aspects:
        c = _PRESENTATION_CHECKS[a]
        fix = c["fix"] if c["fix"] is not None else "Implement " + _PRESENTATION_LIGHTING[engine] + "."
        checks.append({"aspect": a, "flatSceneRisk": c["risk"], "pass": fix, "verifiedWhen": c["verify"]})
    budgets = {
        "low": "weakest tier: shadows and at most one post effect; reduce dressing density before cutting the landmark",
        "balanced": "balanced tier: shadows on, at most two post effects, full dressing at authored density",
        "high": "high tier: full effects allowed, but the low-tier fallback must still hold the art direction",
    }
    return {
        "scene": scene,
        "engine": engine,
        "qualityTier": tier,
        "decisionPolicy": ("Preserve the project's existing art direction and palette. Where none exists, choose the "
                           "simplest coherent option, state it once, and keep it consistent - never silently adopt a style."),
        "passes": checks,
        "performanceBudget": budgets[tier],
        "acceptanceCriteria": [
            "No perfectly flat play area remains: height variation is visible from the player camera.",
            "One landmark anchors the first view and the main route reads without instructions.",
            "Lighting, sky and atmosphere/fog are set deliberately and read back from the live scene, not assumed.",
            "Dressing is clustered with variation; scale references prove human scale in play mode.",
            "A capture from the real spawn camera at the weakest target tier is attached as evidence.",
        ],
        "next": "Apply the passes through native engine tools, read back the live scene properties, then call ms_completion_gate with the acceptance criteria and capture evidence.",
    }


# ── vertical slice gate (6.27) ─────────────────────────────────────────────
_LOOP_ELEMENTS = [
    ("entry", re.compile(r"\b(spawn|start|join|lobby|entry|begin|intro|tutorial)\b", re.I),
     "the player enters and knows what to do first"),
    ("objective", re.compile(r"\b(goal|objective|quest|target|win|score|collect|reach|defeat|deliver|escape)\b", re.I),
     "a clear goal the player can state in one sentence"),
    ("interaction", re.compile(r"\b(move|walk|jump|click|press|tool|ability|drive|shoot|build|interact|button|prompt)\b", re.I),
     "the verb the player performs to pursue the goal"),
    ("feedback", re.compile(r"\b(sound|sfx|vfx|particle|hud|message|animation|effect|flash|shake|popup|notification)\b", re.I),
     "every action produces visible/audible feedback"),
    ("success", re.compile(r"\b(win|complete|success|finish|victory|cleared|solved)\b", re.I),
     "a defined success state"),
    ("failure", re.compile(r"\b(lose|fail|failure|death|damage|game ?over|hazard|kill|timeout|miss)\b", re.I),
     "a defined failure state with a consequence"),
    ("reward", re.compile(r"\b(reward|xp|currency|coin|stud|point|level ?up|unlock|progress|badge|loot|shop|upgrade)\b", re.I),
     "success produces progress the player keeps"),
    ("restart", re.compile(r"\b(restart|respawn|reset|replay|again|next round|loop|continue)\b", re.I),
     "the loop returns to the start without rejoining"),
]
_STUB = re.compile(r"\b(placeholder|todo|later|wip|stub|dummy|temp(orary)?|not implemented)\b", re.I)


def _vertical_slice_gate(args: dict) -> dict:
    request = str(args.get("request") or "").strip()
    if not request:
        raise RuntimeError("ms_vertical_slice_gate needs `request`")
    engine = str(args.get("engine") or "general").lower()
    if engine not in ("roblox", "unity", "godot", "blender", "general"):
        engine = "general"
    features = [str(x).strip() for x in (args.get("features") or []) if str(x).strip()][:60]
    hay = request + "\n" + "\n".join(features)
    stubbed = [f for f in features if _STUB.search(f)]
    elements = []
    missing = []
    for name, rx, means in _LOOP_ELEMENTS:
        covered = bool(rx.search(hay))
        elements.append({"element": name, "means": means, "covered": covered})
        if not covered:
            missing.append(name)
    return {
        "request": request,
        "engine": engine,
        "featuresCounted": len(features),
        "loop": elements,
        "stubbedFeatures": stubbed,
        "verdict": "pass" if not missing and not stubbed else "incomplete",
        "missingInFixOrder": missing,
        "rule": ("Finish the loop before breadth: a small world with a complete loop beats a large world that does "
                 "nothing. Do not report done while any element is missing or stubbed."),
        "next": ("Loop is complete - verify it end to end in a real play session and pass the evidence to "
                 "ms_completion_gate." if not missing and not stubbed else
                 "Implement the missing elements in the listed order through native engine tools, replace stubbed "
                 "features with real ones, then run this gate again."),
    }


def run(name: str, args: dict, tools: list, host=None) -> dict:
    """`host` is a small object from the bridge: call(tool, args, timeout) and studio_id(args)."""
    args = args if isinstance(args, dict) else {}
    if name == "ms_find_tool":
        res = find(tools, args)
    elif name == "ms_tool_stats":
        res = _stats(args)
    elif name == "ms_request_blueprint":
        res = _request_blueprint(args)
    elif name == "ms_tool_workflow":
        res = _tool_workflow(tools, args)
    elif name == "ms_completion_gate":
        res = _completion_gate(args)
    elif name == "ms_presentation_pass":
        res = _presentation_pass(args)
    elif name == "ms_vertical_slice_gate":
        res = _vertical_slice_gate(args)
    elif name == "ms_stage_code":
        res = _stage(args)
    elif name == "ms_run_staged_luau":
        if host is None:
            raise RuntimeError("not available without the bridge")
        key, code = _take(args)
        call = {"code": code, "mode": str(args.get("datamodel_type") or "Edit")}
        if args.get("studio_id"):
            call["studio_id"] = str(args["studio_id"])
        if args.get("timeout_seconds"):
            call["timeout_seconds"] = args["timeout_seconds"]
        out = host.call("ms_roblox_run_luau", call, 600)
        _release(key, args)
        return out
    elif name == "ms_write_staged":
        if host is None:
            raise RuntimeError("not available without the bridge")
        key, text = _take(args)
        path = str(args.get("file_path") or "").strip()
        old_s = str(args.get("old_string") or "")
        guard = (key, path, _sha(text + "\0" + old_s))
        with _STAGE_LOCK:
            _stage_gc()
            if guard in _WRITTEN:
                raise RuntimeError("this exact staged text was already written to that script less than 2 minutes ago - "
                                   "refusing to apply it twice. Read the script (script_read) to check; to write it "
                                   "again on purpose, stage a changed text or clear it first.")
        call = {"file_path": path, "datamodel_type": str(args.get("datamodel_type") or "Edit"),
                "edits": [{"old_string": old_s, "new_string": text}]}
        sid, _why = host.studio_id(args)
        if sid:
            call["studio_id"] = sid
        out = host.call("multi_edit", call, 180)
        with _STAGE_LOCK:
            _WRITTEN[guard] = time.time()
        _release(key, args)
        return out
    else:
        raise RuntimeError(f"unknown assist tool '{name}'")
    return {"text": json.dumps(res, indent=2), "images": []}
