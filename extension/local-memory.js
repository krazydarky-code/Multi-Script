// SPDX-License-Identifier: GPL-3.0-or-later
// Browser-local Graph Memory backend. Canonical for the extension so Memory
// keeps working even when the terminal bridge is offline or from an older copy.
(() => {
  "use strict";
  const ROOT = typeof self !== "undefined" ? self : globalThis;
  const KEY = "msGraphMemoryV2";
  const SETTINGS = { autoRecall: true, autoCapture: true, includeEpisodes: true, maxContextChars: 3500, maxNodes: 4000 };
  const KINDS = ["preference", "decision", "fact", "entity", "asset", "task", "episode", "gotcha"];
  const now = () => new Date().toISOString();
  const clip = (v, n = 8000) => String(v == null ? "" : v).trim().slice(0, n);
  const slug = (v) => clip(v, 80).toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "memory";
  const uid = (p = "n") => `${p}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 9)}`;
  const words = (v) => new Set(clip(v, 10000).toLowerCase().match(/[a-z0-9_./-]{2,}/g) || []);
  const clone = (v) => JSON.parse(JSON.stringify(v));
  const getStore = () => new Promise((resolve) => {
    try { chrome.storage.local.get(KEY, (r) => resolve(r && r[KEY] && typeof r[KEY] === "object" ? r[KEY] : { version: 2, activeId: null, memories: {} })); }
    catch { resolve({ version: 2, activeId: null, memories: {} }); }
  });
  const putStore = (s) => new Promise((resolve) => {
    try { chrome.storage.local.set({ [KEY]: s }, resolve); } catch { resolve(); }
  });
  const findMemory = (s, ref) => {
    ref = clip(ref || s.activeId, 100);
    if (ref && s.memories[ref]) return s.memories[ref];
    const low = ref.toLowerCase();
    return Object.values(s.memories).find((m) => m.name.toLowerCase() === low) || null;
  };
  const summary = (m) => ({ id: m.id, name: m.name, description: m.description || "", nodes: Object.keys(m.nodes || {}).length, edges: (m.edges || []).length, created: m.created, updated: m.updated, settings: { ...SETTINGS, ...(m.settings || {}) } });
  const findNode = (m, ref) => {
    ref = clip(ref, 200); if (!ref) return null;
    if (m.nodes[ref]) return m.nodes[ref];
    const low = ref.toLowerCase();
    return Object.values(m.nodes).find((n) => n.name.toLowerCase() === low) || null;
  };
  const ensureNode = (m, raw = {}) => {
    const name = clip(raw.name || raw.text || "Note", 140);
    const text = clip(raw.text || raw.name || "", 8000);
    const kind = KINDS.includes(raw.kind) ? raw.kind : "fact";
    const existing = Object.values(m.nodes).find((n) => n.kind === kind && (n.name.toLowerCase() === name.toLowerCase() || (text && n.text.toLowerCase() === text.toLowerCase())));
    const t = now();
    if (existing) {
      if (text.length > existing.text.length) existing.text = text;
      existing.tags = [...new Set([...(existing.tags || []), ...((raw.tags || []).map((x) => clip(x, 50)).filter(Boolean))])].slice(0, 20);
      existing.importance = Math.max(Number(existing.importance) || 0.5, Math.max(0, Math.min(1, Number(raw.importance) || 0.5)));
      if (raw.pinned != null) existing.pinned = !!raw.pinned;
      existing.updated = t; return existing;
    }
    const n = { id: uid("n"), kind, name, text, tags: (raw.tags || []).map((x) => clip(x, 50)).filter(Boolean).slice(0, 20), importance: Math.max(0, Math.min(1, Number(raw.importance) || 0.55)), pinned: !!raw.pinned, created: t, updated: t, accesses: 0 };
    m.nodes[n.id] = n; return n;
  };
  const addEdge = (m, a, b, rel = "related") => {
    if (!a || !b || a.id === b.id) return;
    if (!(m.edges || []).some((e) => e.a === a.id && e.b === b.id && e.rel === rel)) m.edges.push({ a: a.id, b: b.id, rel: clip(rel, 60) || "related", created: now() });
  };
  const prune = (m) => {
    const max = Math.max(100, Math.min(50000, Number((m.settings || {}).maxNodes) || 4000));
    const ns = Object.values(m.nodes);
    if (ns.length <= max) return;
    ns.filter((n) => !n.pinned).sort((a, b) => (Number(a.importance) || 0) - (Number(b.importance) || 0) || String(a.updated).localeCompare(String(b.updated))).slice(0, ns.length - max).forEach((n) => delete m.nodes[n.id]);
    m.edges = m.edges.filter((e) => m.nodes[e.a] && m.nodes[e.b]);
  };
  async function call(op, a = {}) {
    const s = await getStore(); let m = findMemory(s, a.memory); const finish = async (out, dirty = false) => { if (dirty) await putStore(s); return { storage: "browser", ...out }; };
    if (op === "list") return finish({ ok: true, memories: Object.values(s.memories).map(summary).sort((x, y) => y.updated.localeCompare(x.updated)), active: s.activeId });
    if (op === "create") {
      const name = clip(a.name, 60); if (!name) return finish({ ok: false, error: "Give the memory a name." });
      let id = slug(name), i = 2; while (s.memories[id]) id = `${slug(name)}-${i++}`;
      const t = now(); m = s.memories[id] = { id, name, description: clip(a.description, 300), created: t, updated: t, settings: { ...SETTINGS }, nodes: {}, edges: [] }; s.activeId = id;
      return finish({ ok: true, created: summary(m) }, true);
    }
    if (op === "import") {
      const d = a.data && typeof a.data === "object" ? clone(a.data) : null; if (!d) return finish({ ok: false, error: "Invalid memory export." });
      const name = clip(d.name || "Imported memory", 60); let id = slug(d.id || name), i = 2; while (s.memories[id]) id = `${slug(d.id || name)}-${i++}`;
      const t = now(); m = s.memories[id] = { id, name, description: clip(d.description, 300), created: d.created || t, updated: t, settings: { ...SETTINGS, ...(d.settings || {}) }, nodes: {}, edges: [] };
      for (const raw of Array.isArray(d.nodes) ? d.nodes : Object.values(d.nodes || {})) { const n = ensureNode(m, raw); if (raw.id) { delete m.nodes[n.id]; n.id = clip(raw.id, 160); m.nodes[n.id] = n; } }
      m.edges = (d.edges || []).filter((e) => m.nodes[e.a] && m.nodes[e.b]).map((e) => ({ a: e.a, b: e.b, rel: clip(e.rel, 60) || "related", created: e.created || t })); s.activeId = id;
      return finish({ ok: true, memory: id, nodes: Object.keys(m.nodes).length }, true);
    }
    if (!m) return finish({ ok: false, error: "Memory not found. Create or select one first." });
    s.activeId = m.id;
    if (op === "open") return finish({ ok: true, active: summary(m) }, true);
    if (op === "rename") { const name = clip(a.name, 60); if (!name) return finish({ ok: false, error: "Name cannot be empty." }); m.name = name; m.updated = now(); return finish({ ok: true, memory: summary(m) }, true); }
    if (op === "delete") { delete s.memories[m.id]; if (s.activeId === m.id) s.activeId = Object.keys(s.memories)[0] || null; return finish({ ok: true, deleted: m.id }, true); }
    if (op === "settings") { if (a.settings && typeof a.settings === "object") { const x = a.settings; for (const k of ["autoRecall", "autoCapture", "includeEpisodes"]) if (k in x) m.settings[k] = !!x[k]; if ("maxContextChars" in x) m.settings.maxContextChars = Math.max(500, Math.min(20000, Number(x.maxContextChars) || 3500)); if ("maxNodes" in x) m.settings.maxNodes = Math.max(100, Math.min(50000, Number(x.maxNodes) || 4000)); m.updated = now(); prune(m); return finish({ ok: true, settings: { ...SETTINGS, ...m.settings } }, true); } return finish({ ok: true, settings: { ...SETTINGS, ...m.settings } }); }
    if (op === "remember") {
      const made = []; const primary = (a.text || a.name) ? ensureNode(m, a) : null; if (primary) made.push(primary);
      for (const e of a.entities || []) made.push(ensureNode(m, { ...e, kind: e.kind || "entity", importance: e.importance || 0.6 }));
      for (const f of a.facts || []) made.push(ensureNode(m, f));
      const byName = (name) => findNode(m, name) || ensureNode(m, { name, kind: "entity", importance: 0.45 });
      if (primary) for (const name of a.about || []) addEdge(m, primary, byName(name), "about");
      for (const r of a.relations || []) addEdge(m, byName(r.from), byName(r.to), r.rel);
      m.updated = now(); prune(m); return finish({ ok: true, memory: m.id, saved: made.map((n) => ({ id: n.id, name: n.name, kind: n.kind })), count: made.length }, true);
    }
    const ranked = (query, limit = 12, kinds = null) => {
      const q = words(query); const all = Object.values(m.nodes).filter((n) => !kinds || !kinds.length || kinds.includes(n.kind));
      return all.map((n) => { const nw = words(`${n.name} ${n.text} ${(n.tags || []).join(" ")}`); let hit = 0; for (const w of q) if (nw.has(w)) hit++; const score = (q.size ? hit / q.size : 0.12) * 5 + (Number(n.importance) || 0.5) + (n.pinned ? 3 : 0) + Math.min(0.5, (Number(n.accesses) || 0) / 20); return { n, score }; }).filter((x) => !q.size || x.score > 0.5).sort((a, b) => b.score - a.score).slice(0, Math.max(1, Math.min(100, Number(limit) || 12))).map((x) => x.n);
    };
    if (op === "recall" || op === "context") {
      const ns = ranked(a.query || "", a.limit || 16, a.kinds); for (const n of ns) { n.accesses = (n.accesses || 0) + 1; }
      const linked = (n) => m.edges.filter((e) => e.a === n.id || e.b === n.id).slice(0, 4).map((e) => { const other = m.nodes[e.a === n.id ? e.b : e.a]; return other ? `${e.rel} → ${other.name}` : ""; }).filter(Boolean);
      if (op === "recall") return finish({ ok: true, memory: m.id, results: ns.map((n) => ({ ...n, links: linked(n) })) }, true);
      const max = Math.max(500, Math.min(20000, Number(m.settings.maxContextChars) || 3500)); let text = "";
      for (const n of ns) { if (n.kind === "episode" && m.settings.includeEpisodes === false) continue; const line = `- [${n.kind}] ${n.name}: ${n.text}${linked(n).length ? ` (${linked(n).join("; ")})` : ""}\n`; if ((text + line).length > max) break; text += line; }
      return finish({ ok: true, memory: m.id, text: text.trim(), nodes: ns.length }, true);
    }
    if (op === "graph") {
      const action = a.action || "overview"; const node = findNode(m, a.node); let nodes = Object.values(m.nodes), edges = m.edges;
      if (["neighbors", "subgraph"].includes(action) && node) { const ids = new Set([node.id]); for (const e of edges) if (e.a === node.id || e.b === node.id) { ids.add(e.a); ids.add(e.b); } nodes = nodes.filter((n) => ids.has(n.id)); edges = edges.filter((e) => ids.has(e.a) && ids.has(e.b)); }
      if (action === "list") nodes = ranked(a.query || "", a.limit || 80, a.kinds);
      return finish({ ok: true, memory: m.id, nodes: nodes.slice(0, Number(a.limit) || 500).map((n) => ({ ...n, links: m.edges.filter((e) => e.a === n.id || e.b === n.id).slice(0, 5).map((e) => { const o = m.nodes[e.a === n.id ? e.b : e.a]; return o ? `${e.rel} → ${o.name}` : ""; }).filter(Boolean) })), edges, stats: { nodes: Object.keys(m.nodes).length, edges: m.edges.length } });
    }
    if (op === "update") { const n = findNode(m, a.node); if (!n) return finish({ ok: false, error: "Memory node not found." }); for (const k of ["name", "text", "kind"]) if (a[k] != null) n[k] = clip(a[k], k === "text" ? 8000 : 140); if (a.tags) n.tags = a.tags.map((x) => clip(x, 50)).filter(Boolean); if (a.importance != null) n.importance = Math.max(0, Math.min(1, Number(a.importance))); if (a.pinned != null) n.pinned = !!a.pinned; n.updated = m.updated = now(); return finish({ ok: true, node: n }, true); }
    if (op === "forget") { let doomed = []; if (a.node) { const n = findNode(m, a.node); if (n) doomed = [n]; } else { const q = words(a.query || ""); doomed = Object.values(m.nodes).filter((n) => !n.pinned && (!a.kinds || !a.kinds.length || a.kinds.includes(n.kind)) && (!q.size || [...q].some((w) => words(`${n.name} ${n.text}`).has(w)))); } for (const n of doomed) delete m.nodes[n.id]; const ids = new Set(doomed.map((n) => n.id)); m.edges = m.edges.filter((e) => !ids.has(e.a) && !ids.has(e.b)); m.updated = now(); return finish({ ok: true, forgotten: doomed.length }, true); }
    if (op === "observe") { const text = `${clip(a.user, 2000)}\n${clip(a.assistant, 3000)}`; const facts = []; const pref = text.match(/\b(?:i prefer|please always|i like|use|avoid|don't use)\b[^.!?\n]{3,180}/ig) || []; for (const x of pref.slice(0, 4)) facts.push({ kind: "preference", name: clip(x, 90), text: clip(x, 220), importance: 0.78 }); const paths = text.match(/(?:[A-Za-z]:\\|\.?\.?\/|res:\/\/|[\w.-]+\/)[\w .()\-\\/]+\.[A-Za-z0-9]{1,8}/g) || []; for (const x of paths.slice(0, 8)) facts.push({ kind: "asset", name: clip(x.split(/[\\/]/).pop(), 100), text: clip(x, 400), tags: ["path"], importance: 0.7 }); if (text.trim()) facts.push({ kind: "episode", name: clip(a.user || "Work session", 100), text: clip(`User: ${a.user}\nResult: ${a.assistant}`, 1200), tags: (a.tools || []).slice(0, 8), importance: 0.35 }); for (const f of facts) ensureNode(m, f); m.updated = now(); prune(m); return finish({ ok: true, captured: facts.length }, true); }
    if (op === "export") return finish({ ok: true, ...clone(m), nodes: Object.values(m.nodes) });
    return finish({ ok: false, error: `Unknown memory operation: ${op}` });
  }
  const TOOLS = [
    ["ms_memory_remember", "Save durable preferences, decisions, facts, assets and linked entities to the active browser-local graph memory.", { memory:{type:"string"}, text:{type:"string"}, name:{type:"string"}, kind:{type:"string",enum:KINDS}, tags:{type:"array",items:{type:"string"}}, importance:{type:"number"}, pinned:{type:"boolean"}, about:{type:"array",items:{type:"string"}}, entities:{type:"array",items:{type:"object"}}, facts:{type:"array",items:{type:"object"}}, relations:{type:"array",items:{type:"object"}} }],
    ["ms_memory_recall", "Recall relevant knowledge from the active browser-local graph memory.", { memory:{type:"string"}, query:{type:"string"}, limit:{type:"integer"}, kinds:{type:"array",items:{type:"string"}}, hops:{type:"integer"} }, ["query"]],
    ["ms_memory_graph", "Explore or export the browser-local graph memory.", { memory:{type:"string"}, action:{type:"string",enum:["overview","stats","list","neighbors","subgraph","path","mermaid","export"]}, node:{type:"string"}, other:{type:"string"}, depth:{type:"integer"}, limit:{type:"integer"} }],
    ["ms_memory_update", "Update or pin one browser-local memory node.", { memory:{type:"string"}, node:{type:"string"}, name:{type:"string"}, text:{type:"string"}, kind:{type:"string"}, tags:{type:"array",items:{type:"string"}}, importance:{type:"number"}, pinned:{type:"boolean"} }, ["node"]],
    ["ms_memory_forget", "Delete selected browser-local memory nodes.", { memory:{type:"string"}, node:{type:"string"}, query:{type:"string"}, kinds:{type:"array",items:{type:"string"}}, older_than_days:{type:"number"} }],
    ["ms_memory_manage", "Create, select, configure, import or export named browser-local memories.", { action:{type:"string"}, memory:{type:"string"}, name:{type:"string"}, description:{type:"string"}, settings:{type:"object"}, data:{type:"object"}, query:{type:"string"} }, ["action"]]
  ].map(([name, description, properties, required]) => ({ name, server:"multiscript-local", description, inputSchema:{ type:"object", properties, ...(required ? {required} : {}) } }));
  async function tool(name, args = {}) { const bare = String(name || "").split("/").pop().split(".").pop(); const map = { ms_memory_remember:"remember", ms_memory_recall:"recall", ms_memory_graph:"graph", ms_memory_update:"update", ms_memory_forget:"forget" }; const op = bare === "ms_memory_manage" ? String(args.action || "list") : map[bare]; if (!op) return { ok:false, error:`Unknown local memory tool: ${bare}` }; const r = await call(op, args); return r.ok ? { ok:true, text:JSON.stringify(r, null, 2), local:true } : { ok:false, error:r.error || "Memory operation failed", local:true }; }
  ROOT.MSLocalMemory = { KEY, SETTINGS, KINDS, TOOLS, call, tool };
  if (typeof module !== "undefined" && module.exports) module.exports = ROOT.MSLocalMemory;
})();
