"""Multi-Script graph memory + sequential thinking.

Local, dependency-free, engine-agnostic memory for AI agent sessions.

* A *memory* is a named knowledge graph (e.g. "Roblox classic gui").
* Nodes are entities / facts / decisions / preferences / tasks / assets /
  episodes / notes / skills.  Edges are typed, weighted relations.
* Everything lives in plain JSON under ``runtime/memory`` (override with the
  ``ZS_MEMORY_DIR`` environment variable) and is written atomically.
* Recall is local: token scoring (name > tags > text) + importance + recency +
  usage + 1-2 hop graph expansion.  No network, no embeddings, no cloud.

The module exposes a small ``MemoryStore`` API plus ``TOOLS`` (MCP tool
descriptors) and ``call_tool`` so ``bridge.py`` can register them as built-ins.
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path

KINDS = ("entity", "fact", "decision", "preference", "task", "asset", "episode", "note", "skill", "thought")
DEFAULT_SETTINGS = {
    "autoRecall": True,       # inject relevant memory into new chats
    "autoCapture": True,      # let the extension journal turns automatically
    "maxContextChars": 3500,  # budget for the injected memory block
    "maxNodes": 4000,         # soft cap; lowest value unpinned nodes are pruned
    "recallLimit": 12,
    "includeEpisodes": True,
}
MAX_TEXT = 1800
STOP = set("""a an and are as at be but by for from has have i if in into is it its me my of on or our so that the their them
then there these they this to was we were will with you your can could should would just not no yes do does did how what when where
which who why also than too very more most some any all each other such only own same""".split())
_TOKEN = re.compile(r"[A-Za-z0-9_\u00C0-\uFFFF]+")


class MemoryError_(RuntimeError):
    pass


def _now() -> float:
    return round(time.time(), 3)


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
    return (s or "memory")[:48]


def _tokens(text: str) -> list:
    out = []
    for raw in _TOKEN.findall(str(text or "")):
        for piece in re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", raw).replace("_", " ").split():
            t = piece.lower()
            if len(t) > 1 and t not in STOP:
                out.append(t[:-1] if len(t) > 4 and t.endswith("s") and not t.endswith("ss") else t)
    return out


def _clip(text, n=MAX_TEXT) -> str:
    s = str(text or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _norm(text: str) -> str:
    return " ".join(_tokens(text))


def _jaccard(a, b) -> float:
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a and b else 0.0


class MemoryStore:
    def __init__(self, root=None):
        env = os.environ.get("ZS_MEMORY_DIR")
        self.root = Path(root or env or (Path(__file__).resolve().parent / "memory"))
        self.lock = threading.RLock()
        self._cache = {}
        self.active_id = None

    # ───────────────────────── persistence ─────────────────────────
    def _path(self, mid: str) -> Path:
        return self.root / f"{mid}.json"

    def _atomic_write(self, path: Path, data) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=str(self.root))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def _load(self, mid: str) -> dict:
        with self.lock:
            if mid in self._cache:
                return self._cache[mid]
            p = self._path(mid)
            if not p.exists():
                raise MemoryError_(f"memory '{mid}' does not exist")
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                bad = p.with_suffix(".corrupt.json")
                try:
                    p.replace(bad)
                except OSError:
                    pass
                raise MemoryError_(f"memory '{mid}' was unreadable; moved to {bad.name}")
            data.setdefault("nodes", {})
            data.setdefault("edges", {})
            data["settings"] = {**DEFAULT_SETTINGS, **(data.get("settings") or {})}
            self._cache[mid] = data
            return data

    def _save(self, mem: dict) -> None:
        mem["updated"] = _now()
        self._atomic_write(self._path(mem["id"]), mem)

    # ───────────────────────── memory management ─────────────────────────
    def list(self) -> list:
        with self.lock:
            rows = []
            if self.root.exists():
                for p in sorted(self.root.glob("*.json")):
                    if p.name.endswith(".corrupt.json"):
                        continue
                    try:
                        m = self._load(p.stem)
                    except MemoryError_:
                        continue
                    rows.append({
                        "id": m["id"], "name": m["name"], "description": m.get("description", ""),
                        "nodes": len(m["nodes"]), "edges": len(m["edges"]),
                        "created": m.get("created"), "updated": m.get("updated"),
                        "settings": m["settings"], "active": m["id"] == self.active_id,
                    })
            rows.sort(key=lambda r: -(r.get("updated") or 0))
            return rows

    def resolve(self, ref=None, create=False) -> dict:
        """Find a memory by id or (case-insensitive) name; fall back to the active one."""
        with self.lock:
            ref = str(ref or "").strip()
            if ref:
                rows = self.list()
                low = ref.lower()
                for r in rows:
                    if r["id"] == ref or r["name"].lower() == low or r["id"] == _slug(ref):
                        return self._load(r["id"])
                cand = [r for r in rows if low in r["name"].lower()]
                if len(cand) == 1:
                    return self._load(cand[0]["id"])
                if create:
                    return self.create(ref)
                raise MemoryError_(f"no memory named '{ref}'. Existing: " + (", ".join(r["name"] for r in rows) or "none"))
            if self.active_id:
                try:
                    return self._load(self.active_id)
                except MemoryError_:
                    self.active_id = None
            rows = self.list()
            if rows:
                return self._load(rows[0]["id"])
            return self.create("General")

    def create(self, name, description="", settings=None) -> dict:
        with self.lock:
            name = _clip(name, 80) or "Memory"
            base = _slug(name)
            mid, i = base, 2
            while self._path(mid).exists():
                mid = f"{base}-{i}"
                i += 1
            mem = {"id": mid, "name": name, "description": _clip(description, 300), "created": _now(), "updated": _now(),
                   "version": 1, "settings": {**DEFAULT_SETTINGS, **(settings or {})}, "nodes": {}, "edges": {}}
            self._cache[mid] = mem
            self._save(mem)
            return mem

    def rename(self, ref, new_name=None, description=None) -> dict:
        with self.lock:
            mem = self.resolve(ref)
            if new_name:
                mem["name"] = _clip(new_name, 80)
            if description is not None:
                mem["description"] = _clip(description, 300)
            self._save(mem)
            return mem

    def delete(self, ref) -> str:
        with self.lock:
            mem = self.resolve(ref)
            mid = mem["id"]
            self._cache.pop(mid, None)
            try:
                self._path(mid).unlink()
            except OSError:
                pass
            if self.active_id == mid:
                self.active_id = None
            return mid

    def activate(self, ref) -> dict:
        with self.lock:
            mem = self.resolve(ref, create=True)
            self.active_id = mem["id"]
            return mem

    def set_settings(self, ref, settings: dict) -> dict:
        with self.lock:
            mem = self.resolve(ref)
            for k, v in (settings or {}).items():
                if k in DEFAULT_SETTINGS:
                    d = DEFAULT_SETTINGS[k]
                    if isinstance(d, bool):
                        mem["settings"][k] = bool(v)
                    else:
                        mem["settings"][k] = max(200 if k == "maxContextChars" else 1, int(v))
            self._save(mem)
            return mem["settings"]

    # ───────────────────────── nodes & edges ─────────────────────────
    @staticmethod
    def _nid() -> str:
        return "n_" + uuid.uuid4().hex[:8]

    def _find_named(self, mem, name, kinds=None):
        low = str(name or "").strip().lower()
        if not low:
            return None
        for n in mem["nodes"].values():
            if n["name"].lower() == low and (not kinds or n["kind"] in kinds):
                return n
        return None

    def _find_ref(self, mem, ref):
        ref = str(ref or "").strip()
        if ref in mem["nodes"]:
            return mem["nodes"][ref]
        n = self._find_named(mem, ref)
        if n:
            return n
        toks = _tokens(ref)
        best, score = None, 0.0
        for n in mem["nodes"].values():
            s = _jaccard(toks, _tokens(n["name"]))
            if s > score:
                best, score = n, s
        return best if score >= 0.6 else None

    def _upsert_node(self, mem, kind, name, text="", tags=None, importance=None, pinned=None, source="model") -> tuple:
        kind = kind if kind in KINDS else "note"
        name = _clip(name, 120) or _clip(text, 60) or "untitled"
        text = _clip(text)
        tags = sorted({str(t).strip().lower()[:32] for t in (tags or []) if str(t).strip()})[:12]
        n = self._find_named(mem, name, None if kind in ("entity", "asset", "skill", "task") else (kind,))
        created = False
        if n is None and kind in ("fact", "decision", "preference", "note"):
            # near-duplicate detection on content
            probe = _tokens(name + " " + text)
            for cand in mem["nodes"].values():
                if cand["kind"] in ("fact", "decision", "preference", "note") and _jaccard(probe, _tokens(cand["name"] + " " + cand["text"])) >= 0.82:
                    n = cand
                    break
        if n is None:
            n = {"id": self._nid(), "kind": kind, "name": name, "text": text, "tags": tags,
                 "importance": 0.5 if importance is None else max(0.0, min(1.0, float(importance))),
                 "pinned": bool(pinned), "hits": 0, "created": _now(), "updated": _now(), "last_used": None, "source": source}
            mem["nodes"][n["id"]] = n
            created = True
        else:
            if text and text not in n["text"]:
                n["text"] = _clip((n["text"] + " | " + text) if n["text"] and len(n["text"]) + len(text) < MAX_TEXT else text)
            n["tags"] = sorted(set(n["tags"]) | set(tags))[:12]
            if importance is not None:
                n["importance"] = max(n["importance"], max(0.0, min(1.0, float(importance))))
            if pinned is not None:
                n["pinned"] = bool(pinned)
            n["updated"] = _now()
            n["hits"] += 1
        return n, created

    def _link(self, mem, a, b, rel="related_to", weight=1.0):
        if a == b or a not in mem["nodes"] or b not in mem["nodes"]:
            return None
        rel = re.sub(r"[^a-z0-9_]+", "_", str(rel or "related_to").lower()).strip("_")[:40] or "related_to"
        for e in mem["edges"].values():
            if e["a"] == a and e["b"] == b and e["rel"] == rel:
                e["weight"] = round(min(10.0, e["weight"] + 0.25), 3)
                e["updated"] = _now()
                return e
        e = {"id": "e_" + uuid.uuid4().hex[:8], "a": a, "b": b, "rel": rel, "weight": float(weight), "created": _now(), "updated": _now()}
        mem["edges"][e["id"]] = e
        return e

    def remember(self, ref=None, items=None, source="model") -> dict:
        """items: {entities:[{name,kind,text,tags}], facts:[{text,about:[...],tags,importance,kind}], relations:[{from,rel,to}],
        text/name/kind/tags/links for a single note}."""
        items = items or {}
        with self.lock:
            mem = self.resolve(ref)
            added, updated, links = [], [], 0

            def put(kind, name, text="", tags=None, importance=None, pinned=None, about=None):
                nonlocal links
                n, created = self._upsert_node(mem, kind, name, text, tags, importance, pinned, source)
                (added if created else updated).append(n["id"])
                for a in about or []:
                    target = self._find_named(mem, a) if isinstance(a, str) else None
                    if target is None and isinstance(a, str) and a.strip():
                        target, c2 = self._upsert_node(mem, "entity", a, "", None, None, None, source)
                        (added if c2 else updated).append(target["id"])
                    if target is not None and self._link(mem, n["id"], target["id"], "about"):
                        links += 1
                return n

            for e in items.get("entities") or []:
                if isinstance(e, str):
                    e = {"name": e}
                if isinstance(e, dict) and (e.get("name") or e.get("text")):
                    put(e.get("kind") or "entity", e.get("name") or e.get("text"), e.get("text", "") if e.get("name") else "",
                        e.get("tags"), e.get("importance"), e.get("pinned"))
            for f in items.get("facts") or []:
                if isinstance(f, str):
                    f = {"text": f}
                if isinstance(f, dict) and f.get("text"):
                    t = _clip(f["text"])
                    put(f.get("kind") if f.get("kind") in KINDS else "fact", _clip(t, 110), t if len(t) > 110 else "",
                        f.get("tags"), f.get("importance"), f.get("pinned"), f.get("about"))
            for r in items.get("relations") or []:
                if isinstance(r, dict):
                    a = r.get("from") or r.get("a")
                    b = r.get("to") or r.get("b")
                    if a and b:
                        na = self._find_named(mem, a) or put("entity", a)
                        nb = self._find_named(mem, b) or put("entity", b)
                        if self._link(mem, na["id"], nb["id"], r.get("rel") or r.get("relation") or "related_to", r.get("weight", 1.0)):
                            links += 1
            if items.get("text") or items.get("name"):
                n = put(items.get("kind") or ("note" if not items.get("name") else "entity"), items.get("name") or _clip(items.get("text"), 80),
                        items.get("text", ""), items.get("tags"), items.get("importance"), items.get("pinned"), items.get("about"))
                for l in items.get("links") or []:
                    if isinstance(l, dict) and l.get("to"):
                        tgt = self._find_named(mem, l["to"]) or put("entity", l["to"])
                        if self._link(mem, n["id"], tgt["id"], l.get("rel") or "related_to"):
                            links += 1
            self._prune(mem)
            self._save(mem)
            return {"memory": mem["name"], "added": len(added), "updated": len(updated), "links": links,
                    "ids": (added + updated)[:20], "nodes": len(mem["nodes"]), "edges": len(mem["edges"])}

    def _prune(self, mem) -> None:
        cap = int(mem["settings"].get("maxNodes", 4000))
        if len(mem["nodes"]) <= cap:
            return
        deg = self._degree(mem)
        now = _now()

        def keep_score(n):
            age_days = (now - (n.get("last_used") or n["updated"])) / 86400
            return n["importance"] * 2 + math.log1p(n["hits"]) + 0.3 * deg.get(n["id"], 0) - 0.02 * age_days + (100 if n["pinned"] else 0)
        order = sorted(mem["nodes"].values(), key=keep_score)
        for n in order[: len(mem["nodes"]) - cap]:
            self._drop(mem, n["id"])

    def _drop(self, mem, nid) -> None:
        mem["nodes"].pop(nid, None)
        for eid in [i for i, e in mem["edges"].items() if e["a"] == nid or e["b"] == nid]:
            mem["edges"].pop(eid, None)

    def _degree(self, mem) -> dict:
        d = {}
        for e in mem["edges"].values():
            d[e["a"]] = d.get(e["a"], 0) + 1
            d[e["b"]] = d.get(e["b"], 0) + 1
        return d

    def _adj(self, mem) -> dict:
        adj = {}
        for e in mem["edges"].values():
            adj.setdefault(e["a"], []).append((e["b"], e))
            adj.setdefault(e["b"], []).append((e["a"], e))
        return adj

    # ───────────────────────── recall ─────────────────────────
    def recall(self, ref=None, query="", limit=None, kinds=None, hops=1, touch=True) -> dict:
        with self.lock:
            mem = self.resolve(ref)
            limit = int(limit or mem["settings"].get("recallLimit", 12))
            q = _tokens(query)
            qset = set(q)
            now = _now()
            n_docs = max(1, len(mem["nodes"]))
            df = {}
            docs = {}
            for n in mem["nodes"].values():
                nt = _tokens(n["name"])
                tt = _tokens(" ".join(n["tags"]))
                bt = _tokens(n["text"])
                docs[n["id"]] = (nt, tt, bt)
                for t in set(nt) | set(tt) | set(bt):
                    df[t] = df.get(t, 0) + 1
            scored = {}
            for nid, n in mem["nodes"].items():
                if kinds and n["kind"] not in kinds:
                    continue
                nt, tt, bt = docs[nid]
                s = 0.0
                for t in qset:
                    idf = math.log(1 + n_docs / (1 + df.get(t, 0)))
                    s += idf * (3.0 * (t in nt) + 2.0 * (t in tt) + 1.0 * min(2, bt.count(t)) / (1 if t in bt else 1))
                if q and s <= 0:
                    # substring fallback for partial words
                    low = (n["name"] + " " + n["text"]).lower()
                    s = 0.4 * sum(1 for t in qset if len(t) > 3 and t in low)
                if q and s <= 0:
                    continue
                age_days = max(0.0, (now - (n.get("last_used") or n["updated"])) / 86400)
                base = 0.6 * n["importance"] + 0.25 * math.log1p(n["hits"]) + 0.5 * math.exp(-age_days / 30) + (0.8 if n["pinned"] else 0)
                scored[nid] = (s * (1 + 0.3 * n["importance"]) if q else 0) + base
            adj = self._adj(mem)
            seeds = sorted(scored.items(), key=lambda kv: -kv[1])[: max(3, limit)]
            if q and hops > 0:
                frontier = {nid: sc for nid, sc in seeds[: max(3, limit // 2)]}
                for hop in range(min(2, int(hops))):
                    nxt = {}
                    for nid, sc in frontier.items():
                        for other, e in adj.get(nid, []):
                            if other in scored and scored[other] >= sc:
                                continue
                            node = mem["nodes"].get(other)
                            if not node or (kinds and node["kind"] not in kinds):
                                continue
                            gain = sc * 0.45 / (hop + 1) * min(1.5, 0.6 + e["weight"] * 0.3)
                            nxt[other] = max(nxt.get(other, 0), gain)
                    for k, v in nxt.items():
                        scored[k] = max(scored.get(k, 0), v)
                    frontier = nxt
            ranked = sorted(scored.items(), key=lambda kv: -kv[1])[:limit]
            out = []
            for nid, sc in ranked:
                n = mem["nodes"][nid]
                if touch:
                    n["hits"] += 1
                    n["last_used"] = now
                out.append(self._view(mem, n, adj, round(sc, 3)))
            if touch and out:
                self._save(mem)
            return {"memory": mem["name"], "query": query, "count": len(out), "total": len(mem["nodes"]), "results": out}

    def _view(self, mem, n, adj=None, score=None) -> dict:
        adj = adj if adj is not None else self._adj(mem)
        rel = []
        for other, e in sorted(adj.get(n["id"], []), key=lambda t: -t[1]["weight"])[:8]:
            o = mem["nodes"].get(other)
            if o:
                rel.append(f"{n['name'] if e['a'] == n['id'] else o['name']} -{e['rel']}-> {o['name'] if e['a'] == n['id'] else n['name']}" if False else
                           (f"-{e['rel']}-> {o['name']}" if e["a"] == n["id"] else f"<-{e['rel']}- {o['name']}"))
        v = {"id": n["id"], "kind": n["kind"], "name": n["name"], "text": n["text"], "tags": n["tags"],
             "importance": round(n["importance"], 2), "pinned": n["pinned"], "links": rel}
        if score is not None:
            v["score"] = score
        return v

    # ───────────────────────── context packing ─────────────────────────
    def context(self, ref=None, query="", budget=None) -> dict:
        """Compact text block for injecting into a new chat."""
        with self.lock:
            mem = self.resolve(ref)
            s = mem["settings"]
            budget = int(budget or s.get("maxContextChars", 3500))
            lines, used, seen = [], 0, set()

            def add(n, prefix=""):
                nonlocal used
                if n["id"] in seen:
                    return
                body = n["name"] if not n["text"] or n["text"] == n["name"] else f"{n['name']}: {n['text']}"
                ln = f"- [{n['kind']}] {prefix}{_clip(body, 260)}"
                if used + len(ln) > budget:
                    return
                seen.add(n["id"])
                lines.append(ln)
                used += len(ln) + 1

            nodes = list(mem["nodes"].values())
            for n in sorted((n for n in nodes if n["pinned"]), key=lambda n: -n["importance"]):
                add(n)
            hits = self.recall(mem["id"], query, limit=14, touch=False)["results"] if query else []
            for r in hits:
                add(mem["nodes"][r["id"]])
            if not query:
                top = sorted((n for n in nodes if n["kind"] in ("preference", "decision", "entity", "fact", "task", "asset", "skill")),
                             key=lambda n: -(n["importance"] * 2 + math.log1p(n["hits"]) + (n["updated"] / 1e10)))
                for n in top[:14]:
                    add(n)
            if s.get("includeEpisodes", True):
                eps = sorted((n for n in nodes if n["kind"] == "episode"), key=lambda n: -n["created"])[:4]
                for n in eps:
                    add(n, "recent: ")
            return {"memory": mem["name"], "chars": used, "nodes": len(seen), "text": "\n".join(lines)}

    # ───────────────────────── graph views ─────────────────────────
    def graph(self, ref=None, action="overview", node=None, other=None, depth=2, limit=40) -> dict:
        with self.lock:
            mem = self.resolve(ref)
            action = str(action or "overview").lower()
            adj = self._adj(mem)
            deg = self._degree(mem)
            if action in ("overview", "stats"):
                kinds = {}
                for n in mem["nodes"].values():
                    kinds[n["kind"]] = kinds.get(n["kind"], 0) + 1
                rels = {}
                for e in mem["edges"].values():
                    rels[e["rel"]] = rels.get(e["rel"], 0) + 1
                hubs = sorted(mem["nodes"].values(), key=lambda n: -deg.get(n["id"], 0))[:10]
                return {"memory": mem["name"], "nodes": len(mem["nodes"]), "edges": len(mem["edges"]), "kinds": kinds,
                        "relations": dict(sorted(rels.items(), key=lambda kv: -kv[1])[:15]),
                        "hubs": [{"id": n["id"], "name": n["name"], "kind": n["kind"], "degree": deg.get(n["id"], 0)} for n in hubs if deg.get(n["id"], 0)],
                        "pinned": [n["name"] for n in mem["nodes"].values() if n["pinned"]][:20]}
            if action == "list":
                rows = sorted(mem["nodes"].values(), key=lambda n: -n["updated"])[: int(limit)]
                return {"memory": mem["name"], "nodes": [self._view(mem, n, adj) for n in rows]}
            if action in ("export", "snapshot", "all"):
                return {"memory": mem["name"], "nodes": list(mem["nodes"].values()), "edges": list(mem["edges"].values())}
            if action == "mermaid":
                ids = {nid: f"n{i}" for i, nid in enumerate(list(mem["nodes"])[: int(limit)])}
                out = ["graph LR"]
                for nid, k in ids.items():
                    out.append(f'  {k}["{mem["nodes"][nid]["name"][:40].replace(chr(34), chr(39))}"]')
                for e in mem["edges"].values():
                    if e["a"] in ids and e["b"] in ids:
                        out.append(f"  {ids[e['a']]} -->|{e['rel']}| {ids[e['b']]}")
                return {"memory": mem["name"], "mermaid": "\n".join(out)}
            n = self._find_ref(mem, node)
            if n is None:
                raise MemoryError_(f"graph action '{action}' needs an existing 'node' (id or name); got {node!r}")
            if action in ("neighbors", "subgraph"):
                seen, frontier = {n["id"]: 0}, [n["id"]]
                for d in range(1, max(1, min(4, int(depth))) + 1):
                    nxt = []
                    for nid in frontier:
                        for other_id, _e in adj.get(nid, []):
                            if other_id not in seen:
                                seen[other_id] = d
                                nxt.append(other_id)
                    frontier = nxt
                nodes = [dict(self._view(mem, mem["nodes"][i], adj), distance=d) for i, d in sorted(seen.items(), key=lambda kv: kv[1])][: int(limit)]
                edges = [{"from": mem["nodes"][e["a"]]["name"], "rel": e["rel"], "to": mem["nodes"][e["b"]]["name"], "weight": e["weight"]}
                         for e in mem["edges"].values() if e["a"] in seen and e["b"] in seen][: int(limit) * 2]
                return {"memory": mem["name"], "center": n["name"], "nodes": nodes, "edges": edges}
            if action == "path":
                m = self._find_ref(mem, other)
                if m is None:
                    raise MemoryError_("graph action 'path' needs 'other' (id or name)")
                prev, queue = {n["id"]: None}, [n["id"]]
                while queue and m["id"] not in prev:
                    cur = queue.pop(0)
                    for o, e in adj.get(cur, []):
                        if o not in prev:
                            prev[o] = (cur, e)
                            queue.append(o)
                if m["id"] not in prev:
                    return {"memory": mem["name"], "connected": False, "path": []}
                path, cur = [], m["id"]
                while prev[cur]:
                    p, e = prev[cur]
                    path.append({"from": mem["nodes"][p]["name"], "rel": e["rel"], "to": mem["nodes"][cur]["name"]})
                    cur = p
                return {"memory": mem["name"], "connected": True, "path": list(reversed(path))}
            raise MemoryError_(f"unknown graph action '{action}' (overview|stats|list|neighbors|subgraph|path|mermaid|export)")

    # ───────────────────────── edit / forget ─────────────────────────
    def update(self, ref=None, node=None, **fields) -> dict:
        with self.lock:
            mem = self.resolve(ref)
            n = self._find_ref(mem, node)
            if n is None:
                raise MemoryError_(f"no node matching {node!r}")
            for k in ("name", "text", "kind"):
                if fields.get(k) not in (None, ""):
                    n[k] = _clip(fields[k], 120 if k == "name" else MAX_TEXT) if k != "kind" else (fields[k] if fields[k] in KINDS else n["kind"])
            if fields.get("tags") is not None:
                n["tags"] = sorted({str(t).strip().lower()[:32] for t in fields["tags"] if str(t).strip()})[:12]
            if fields.get("importance") is not None:
                n["importance"] = max(0.0, min(1.0, float(fields["importance"])))
            if fields.get("pinned") is not None:
                n["pinned"] = bool(fields["pinned"])
            for l in fields.get("link") or []:
                if isinstance(l, dict) and l.get("to"):
                    tgt = self._find_named(mem, l["to"]) or self._upsert_node(mem, "entity", l["to"])[0]
                    self._link(mem, n["id"], tgt["id"], l.get("rel") or "related_to")
            for l in fields.get("unlink") or []:
                tgt = self._find_ref(mem, l if isinstance(l, str) else l.get("to"))
                if tgt:
                    for eid in [i for i, e in mem["edges"].items() if {e["a"], e["b"]} == {n["id"], tgt["id"]}]:
                        mem["edges"].pop(eid, None)
            if fields.get("merge_into"):
                tgt = self._find_ref(mem, fields["merge_into"])
                if tgt and tgt["id"] != n["id"]:
                    for e in mem["edges"].values():
                        if e["a"] == n["id"]:
                            e["a"] = tgt["id"]
                        if e["b"] == n["id"]:
                            e["b"] = tgt["id"]
                    for eid in [i for i, e in mem["edges"].items() if e["a"] == e["b"]]:
                        mem["edges"].pop(eid)
                    tgt["text"] = _clip((tgt["text"] + " | " + n["text"]).strip(" |"))
                    tgt["tags"] = sorted(set(tgt["tags"]) | set(n["tags"]))[:12]
                    tgt["importance"] = max(tgt["importance"], n["importance"])
                    mem["nodes"].pop(n["id"], None)
                    n = tgt
            n["updated"] = _now()
            self._save(mem)
            return self._view(mem, n)

    def forget(self, ref=None, node=None, query=None, kinds=None, older_than_days=None, confirm_all=False) -> dict:
        with self.lock:
            mem = self.resolve(ref)
            victims = []
            if node:
                n = self._find_ref(mem, node)
                if n:
                    victims.append(n["id"])
            if query:
                victims += [r["id"] for r in self.recall(mem["id"], query, limit=50, hops=0, touch=False)["results"] if not mem["nodes"][r["id"]]["pinned"]][:20]
            if kinds or older_than_days:
                cutoff = _now() - float(older_than_days or 0) * 86400
                for n in mem["nodes"].values():
                    if n["pinned"]:
                        continue
                    if (not kinds or n["kind"] in kinds) and (not older_than_days or n["updated"] < cutoff):
                        victims.append(n["id"])
            if confirm_all and not (node or query or kinds or older_than_days):
                victims = [i for i, n in mem["nodes"].items() if not n["pinned"]]
            victims = list(dict.fromkeys(victims))
            for v in victims:
                self._drop(mem, v)
            self._save(mem)
            return {"memory": mem["name"], "forgotten": len(victims), "nodes": len(mem["nodes"])}

    # ───────────────────────── automatic capture ─────────────────────────
    _PREF = re.compile(r"\b(?:i (?:prefer|like|want|need|always|never|usually)|please (?:always|never)|always use|never use|don'?t (?:use|ever)|remember (?:that|this|to)|from now on|my (?:style|name|project|game|studio) (?:is|are))\b[^.!?\n]{4,200}", re.I)
    _DECIDE = re.compile(r"\b(?:we(?:'ll| will)? (?:use|go with|decided|chose)|decided to|let'?s (?:use|go with)|going with|the plan is)\b[^.!?\n]{4,200}", re.I)
    _PATH = re.compile(r"(?:Workspace|ReplicatedStorage|ServerScriptService|StarterGui|StarterPlayer|ServerStorage|Lighting|SoundService)(?:[.\/][A-Za-z0-9_]+)+|(?:Assets|res:\/\/|Scenes|Scripts)[\/A-Za-z0-9_.\-]+\.[A-Za-z0-9]{2,5}")
    _TOOL = re.compile(r"\bms_[a-z0-9_]+\b")

    def observe(self, ref=None, user="", assistant="", tools=None, title="") -> dict:
        """Heuristic, model-free journaling of one conversational turn."""
        with self.lock:
            mem = self.resolve(ref)
            user, assistant = str(user or ""), str(assistant or "")
            if len(user) + len(assistant) < 12:
                return {"memory": mem["name"], "captured": 0}
            facts = []
            for src, text in (("user", user), ("assistant", assistant)):
                for rx, kind, imp in ((self._PREF, "preference", 0.8), (self._DECIDE, "decision", 0.65)):
                    if kind == "preference" and src != "user":
                        continue
                    for m in rx.finditer(text):
                        facts.append({"kind": kind, "text": _clip(m.group(0).strip(), 240), "importance": imp})
            entities = []
            for rx in (self._PATH,):
                for m in rx.finditer(user + "\n" + assistant):
                    entities.append({"name": m.group(0)[:100], "kind": "asset", "importance": 0.4})
            used = sorted({t for t in (tools or []) if str(t).startswith("ms_") or str(t)} )[:10]
            summary_bits = [b for b in (_clip(user, 220), _clip(assistant, 260)) if b]
            ep_name = _clip(title or user.split("\n")[0], 90) or "conversation"
            ep_text = _clip("User: " + summary_bits[0] + (" || Result: " + summary_bits[-1] if len(summary_bits) > 1 else "") + (" | tools: " + ", ".join(used) if used else ""), 700)
            res = self.remember(mem["id"], {"entities": entities[:8], "facts": facts[:6]}, source="auto")
            ep, _ = self._upsert_node(mem, "episode", ep_name, ep_text, ["auto"], 0.35, None, "auto")
            ep["last_used"] = None
            for e in entities[:8]:
                t = self._find_named(mem, e["name"])
                if t:
                    self._link(mem, ep["id"], t["id"], "touched")
            for f in facts[:6]:
                t = self._find_named(mem, _clip(f["text"], 110)) or None
                if t:
                    self._link(mem, ep["id"], t["id"], "produced")
            # forget oldest auto episodes beyond 60
            eps = sorted((n for n in mem["nodes"].values() if n["kind"] == "episode" and "auto" in n["tags"] and not n["pinned"]), key=lambda n: n["created"])
            for n in eps[:-60]:
                self._drop(mem, n["id"])
            self._save(mem)
            return {"memory": mem["name"], "captured": res["added"] + res["updated"] + 1, "facts": len(facts), "entities": len(entities)}

    # ───────────────────────── export / import ─────────────────────────
    def export(self, ref=None) -> dict:
        with self.lock:
            mem = self.resolve(ref)
            return json.loads(json.dumps(mem))

    def import_(self, data: dict, name=None, merge_into=None) -> dict:
        if not isinstance(data, dict) or not isinstance(data.get("nodes"), (dict, list)):
            raise MemoryError_("import needs an exported memory object with 'nodes'")
        with self.lock:
            nodes = data["nodes"] if isinstance(data["nodes"], dict) else {n["id"]: n for n in data["nodes"] if isinstance(n, dict) and n.get("id")}
            edges = data.get("edges") or {}
            edges = edges if isinstance(edges, dict) else {e["id"]: e for e in edges if isinstance(e, dict) and e.get("id")}
            mem = self.resolve(merge_into, create=True) if merge_into else self.create(name or data.get("name") or "Imported", data.get("description", ""), data.get("settings"))
            idmap = {}
            for old, n in nodes.items():
                if not isinstance(n, dict) or not n.get("name"):
                    continue
                new, _ = self._upsert_node(mem, n.get("kind", "note"), n["name"], n.get("text", ""), n.get("tags"), n.get("importance"), n.get("pinned"), "import")
                idmap[old] = new["id"]
            for e in edges.values():
                if isinstance(e, dict) and e.get("a") in idmap and e.get("b") in idmap:
                    self._link(mem, idmap[e["a"]], idmap[e["b"]], e.get("rel"), e.get("weight", 1.0))
            self._save(mem)
            return {"memory": mem["name"], "id": mem["id"], "nodes": len(mem["nodes"]), "edges": len(mem["edges"])}


# ═════════════════════════ sequential thinking ═════════════════════════
class ThinkingSessions:
    """Reference-compatible sequential thinking (MCP `sequentialthinking`) with
    extras: sessions, revisions/branches, summaries, optional memory capture."""

    def __init__(self):
        self.lock = threading.RLock()
        self.sessions = {}

    def step(self, a: dict, store: "MemoryStore | None" = None) -> dict:
        with self.lock:
            sid = str(a.get("session") or "default")[:60]
            if str(a.get("action") or "").lower() == "reset":
                self.sessions.pop(sid, None)
                return {"session": sid, "reset": True}
            s = self.sessions.setdefault(sid, {"thoughts": [], "branches": {}, "started": _now()})
            if str(a.get("action") or "").lower() in ("summary", "history"):
                return {"session": sid, "thoughtHistoryLength": len(s["thoughts"]),
                        "branches": {k: len(v) for k, v in s["branches"].items()},
                        "thoughts": [{"n": t["thoughtNumber"], "thought": _clip(t["thought"], 400), "revises": t.get("revisesThought"), "branch": t.get("branchId")} for t in s["thoughts"][-30:]]}
            thought = str(a.get("thought") or "").strip()
            if not thought:
                raise MemoryError_("'thought' is required")
            try:
                n = int(a.get("thoughtNumber") or (len(s["thoughts"]) + 1))
                total = int(a.get("totalThoughts") or max(n, 5))
            except (TypeError, ValueError):
                raise MemoryError_("thoughtNumber and totalThoughts must be integers")
            if n > total:
                total = n
            more = a.get("nextThoughtNeeded")
            more = True if more is None else (more if isinstance(more, bool) else str(more).lower() not in ("false", "0", "no"))
            rec = {"thought": thought, "thoughtNumber": n, "totalThoughts": total, "nextThoughtNeeded": more, "ts": _now()}
            for k in ("isRevision", "revisesThought", "branchFromThought", "branchId", "needsMoreThoughts"):
                if a.get(k) not in (None, "", False):
                    rec[k] = a[k]
            s["thoughts"].append(rec)
            if len(s["thoughts"]) > 200:
                s["thoughts"] = s["thoughts"][-200:]
            if rec.get("branchFromThought") and rec.get("branchId"):
                s["branches"].setdefault(str(rec["branchId"]), []).append(rec)
            out = {"session": sid, "thoughtNumber": n, "totalThoughts": total, "nextThoughtNeeded": more,
                   "branches": list(s["branches"].keys()), "thoughtHistoryLength": len(s["thoughts"])}
            if not more:
                out["hint"] = "Reasoning finished. State the conclusion, then act with the native tools and verify with a read-back."
                if a.get("save_to_memory") and store is not None:
                    chain = " -> ".join(_clip(t["thought"], 140) for t in s["thoughts"][-8:])
                    out["memory"] = store.remember(a.get("memory"), {"kind": "decision", "name": _clip(a.get("title") or thought, 100), "text": chain,
                                                                       "tags": ["reasoning"], "importance": 0.6})
            elif n >= total and not a.get("needsMoreThoughts"):
                out["hint"] = "You reached totalThoughts; raise totalThoughts or set nextThoughtNeeded=false."
            return out


STORE = MemoryStore()
THINK = ThinkingSessions()


# ═════════════════════════ MCP tool descriptors ═════════════════════════
_MEM_PROP = {"type": "string", "description": "Memory name or id. Optional: defaults to the memory the user enabled for this chat."}


def _obj(props, required=None):
    d = {"type": "object", "properties": props}
    if required:
        d["required"] = required
    return d


TOOLS = [
    {"name": "ms_memory_remember",
     "description": "Save durable knowledge to the user's local graph memory (preferences, decisions, facts, entities, assets, tasks, relations). Use it when the user states a lasting preference, a design decision is made, a reusable asset/path/ID appears, or a task is finished. Entities are merged by name; near-duplicate facts are merged automatically. Link things with relations so recall can walk the graph.",
     "inputSchema": _obj({
         "memory": _MEM_PROP,
         "text": {"type": "string", "description": "A single fact/note to store."},
         "name": {"type": "string", "description": "Short title/entity name for a single item."},
         "kind": {"type": "string", "enum": list(KINDS)},
         "tags": {"type": "array", "items": {"type": "string"}},
         "importance": {"type": "number", "description": "0-1; preferences/decisions ~0.8."},
         "pinned": {"type": "boolean", "description": "Always include in the injected context."},
         "about": {"type": "array", "items": {"type": "string"}, "description": "Entity names this item is about (creates edges)."},
         "entities": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "kind": {"type": "string"}, "text": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}}}},
         "facts": {"type": "array", "items": {"type": "object", "properties": {"text": {"type": "string"}, "kind": {"type": "string"}, "about": {"type": "array", "items": {"type": "string"}}, "importance": {"type": "number"}, "tags": {"type": "array", "items": {"type": "string"}}}}},
         "relations": {"type": "array", "items": {"type": "object", "properties": {"from": {"type": "string"}, "rel": {"type": "string"}, "to": {"type": "string"}}}},
     })},
    {"name": "ms_memory_recall",
     "description": "Search the local graph memory (keyword + importance + recency + graph expansion) and return the most relevant nodes with their links. Call it at the start of a task and whenever the user refers to earlier work ('like last time', 'my usual style').",
     "inputSchema": _obj({
         "memory": _MEM_PROP, "query": {"type": "string"}, "limit": {"type": "integer"},
         "kinds": {"type": "array", "items": {"type": "string", "enum": list(KINDS)}},
         "hops": {"type": "integer", "description": "Graph expansion depth 0-2 (default 1)."},
     }, ["query"])},
    {"name": "ms_memory_graph",
     "description": "Explore the memory graph: overview/stats, list, neighbors/subgraph around a node, shortest path between two nodes, mermaid diagram, or full export.",
     "inputSchema": _obj({
         "memory": _MEM_PROP,
         "action": {"type": "string", "enum": ["overview", "stats", "list", "neighbors", "subgraph", "path", "mermaid", "export"]},
         "node": {"type": "string"}, "other": {"type": "string"}, "depth": {"type": "integer"}, "limit": {"type": "integer"},
     })},
    {"name": "ms_memory_update",
     "description": "Edit one memory node: rename, rewrite text, change kind/tags/importance, pin/unpin, add or remove links, or merge it into another node.",
     "inputSchema": _obj({
         "memory": _MEM_PROP, "node": {"type": "string", "description": "Node id or name."},
         "name": {"type": "string"}, "text": {"type": "string"}, "kind": {"type": "string", "enum": list(KINDS)},
         "tags": {"type": "array", "items": {"type": "string"}}, "importance": {"type": "number"}, "pinned": {"type": "boolean"},
         "link": {"type": "array", "items": {"type": "object", "properties": {"to": {"type": "string"}, "rel": {"type": "string"}}}},
         "unlink": {"type": "array", "items": {"type": "string"}}, "merge_into": {"type": "string"},
     }, ["node"])},
    {"name": "ms_memory_forget",
     "description": "Delete memory nodes (and their edges): one node, everything matching a query, a kind, or older than N days. Pinned nodes are kept. Only forget when the user asks or information is plainly wrong.",
     "inputSchema": _obj({
         "memory": _MEM_PROP, "node": {"type": "string"}, "query": {"type": "string"},
         "kinds": {"type": "array", "items": {"type": "string", "enum": list(KINDS)}}, "older_than_days": {"type": "number"},
     })},
    {"name": "ms_memory_manage",
     "description": "Manage named memories: list, create, open (make active), rename, delete, settings, export, import, context (get the packed context block), stats.",
     "inputSchema": _obj({
         "action": {"type": "string", "enum": ["list", "create", "open", "rename", "delete", "settings", "export", "import", "context"]},
         "memory": _MEM_PROP, "name": {"type": "string"}, "description": {"type": "string"},
         "settings": {"type": "object"}, "data": {"type": "object", "description": "Exported memory JSON for action=import."},
         "query": {"type": "string", "description": "For action=context: bias the packed block towards this task."},
     }, ["action"])},
    {"name": "ms_sequential_thinking",
     "description": "Step-by-step reasoning scratchpad for complex, ambiguous or multi-stage work (architecture, debugging, level/UI/animation planning). Each call records one thought; you may revise earlier thoughts, branch alternatives, and adjust totalThoughts. Set nextThoughtNeeded=false only when the answer is verified. It does not execute anything; it keeps the plan explicit before native tool calls.",
     "inputSchema": _obj({
         "thought": {"type": "string", "description": "Your current thinking step."},
         "nextThoughtNeeded": {"type": "boolean"},
         "thoughtNumber": {"type": "integer"}, "totalThoughts": {"type": "integer"},
         "isRevision": {"type": "boolean"}, "revisesThought": {"type": "integer"},
         "branchFromThought": {"type": "integer"}, "branchId": {"type": "string"}, "needsMoreThoughts": {"type": "boolean"},
         "session": {"type": "string", "description": "Optional named thinking session (default 'default')."},
         "action": {"type": "string", "enum": ["step", "summary", "reset"]},
         "save_to_memory": {"type": "boolean", "description": "When finishing, store the reasoning chain as a decision in memory."},
         "memory": _MEM_PROP, "title": {"type": "string"},
     }, ["thought", "nextThoughtNeeded", "thoughtNumber", "totalThoughts"])},
]
TOOL_NAMES = {t["name"] for t in TOOLS}
MEMORY_TOOL_NAMES = {n for n in TOOL_NAMES if n.startswith("ms_memory_")}


def _json(obj) -> dict:
    return {"text": json.dumps(obj, indent=1, ensure_ascii=False), "images": []}


def call_tool(name: str, a: dict) -> dict:
    a = a or {}
    try:
        if name == "ms_memory_remember":
            keys = ("entities", "facts", "relations", "text", "name", "kind", "tags", "importance", "pinned", "about")
            return _json(STORE.remember(a.get("memory"), {k: a[k] for k in keys if k in a}))
        if name == "ms_memory_recall":
            return _json(STORE.recall(a.get("memory"), a.get("query", ""), a.get("limit"), a.get("kinds"), int(a.get("hops", 1))))
        if name == "ms_memory_graph":
            return _json(STORE.graph(a.get("memory"), a.get("action", "overview"), a.get("node"), a.get("other"), int(a.get("depth") or 2), int(a.get("limit") or 40)))
        if name == "ms_memory_update":
            f = {k: a[k] for k in ("name", "text", "kind", "tags", "importance", "pinned", "link", "unlink", "merge_into") if k in a}
            return _json(STORE.update(a.get("memory"), a.get("node"), **f))
        if name == "ms_memory_forget":
            return _json(STORE.forget(a.get("memory"), a.get("node"), a.get("query"), a.get("kinds"), a.get("older_than_days")))
        if name == "ms_memory_manage":
            return _json(manage(a))
        if name == "ms_sequential_thinking":
            return _json(THINK.step(a, STORE))
    except MemoryError_ as exc:
        raise RuntimeError(str(exc)) from None
    raise RuntimeError(f"unknown memory tool '{name}'")


def manage(a: dict) -> dict:
    act = str(a.get("action") or "list").lower()
    if act == "list":
        return {"memories": STORE.list()}
    if act == "create":
        m = STORE.create(a.get("name") or "Memory", a.get("description", ""), a.get("settings"))
        return {"created": {"id": m["id"], "name": m["name"]}}
    if act in ("open", "activate"):
        m = STORE.activate(a.get("memory") or a.get("name"))
        return {"active": {"id": m["id"], "name": m["name"], "nodes": len(m["nodes"]), "settings": m["settings"]}}
    if act == "rename":
        m = STORE.rename(a.get("memory"), a.get("name"), a.get("description"))
        return {"renamed": {"id": m["id"], "name": m["name"]}}
    if act == "delete":
        return {"deleted": STORE.delete(a.get("memory") or a.get("name"))}
    if act == "settings":
        if a.get("settings"):
            return {"settings": STORE.set_settings(a.get("memory"), a["settings"])}
        return {"settings": STORE.resolve(a.get("memory"))["settings"]}
    if act == "export":
        return STORE.export(a.get("memory"))
    if act == "import":
        return STORE.import_(a.get("data"), a.get("name"), a.get("merge_into"))
    if act == "context":
        return STORE.context(a.get("memory"), a.get("query", ""))
    if act == "stats":
        return STORE.graph(a.get("memory"), "overview")
    raise MemoryError_(f"unknown action '{act}'")


def ws_op(op: str, a: dict) -> dict:
    """Operations for the extension UI (not model-facing)."""
    a = a or {}
    try:
        if op == "observe":
            return {"ok": True, **STORE.observe(a.get("memory"), a.get("user", ""), a.get("assistant", ""), a.get("tools"), a.get("title", ""))}
        if op == "graph":
            return {"ok": True, **STORE.graph(a.get("memory"), a.get("action", "list"), a.get("node"), a.get("other"), int(a.get("depth") or 2), int(a.get("limit") or 60))}
        if op == "recall":
            return {"ok": True, **STORE.recall(a.get("memory"), a.get("query", ""), a.get("limit"), a.get("kinds"), int(a.get("hops", 1)), touch=False)}
        if op == "remember":
            return {"ok": True, **STORE.remember(a.get("memory"), a.get("items") or a)}
        if op == "update":
            f = {k: a[k] for k in ("name", "text", "kind", "tags", "importance", "pinned", "link", "unlink", "merge_into") if k in a}
            return {"ok": True, "node": STORE.update(a.get("memory"), a.get("node"), **f)}
        if op == "forget":
            return {"ok": True, **STORE.forget(a.get("memory"), a.get("node"), a.get("query"), a.get("kinds"), a.get("older_than_days"))}
        return {"ok": True, **manage({**a, "action": op})}
    except MemoryError_ as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # never crash the websocket loop
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
