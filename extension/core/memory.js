// memory.js - graph memory for the chat bar (Memory button + Memory menu).
//
// WHAT THIS IS
// A named, local, graph-shaped memory ("Roblox classic gui", "Blender hero"...)
// that can be switched ON per chat session. While ON:
//   * the memory's most relevant nodes are injected into the system prompt, so a
//     brand-new chat starts already knowing what earlier chats learned;
//   * the model is given the ms_memory_* tools (recall / remember / graph /
//     update / forget) and told how to use them;
//   * after each finished agent turn the bridge journals the exchange
//     (preferences, decisions, asset paths, an episode) when auto-capture is on.
// Everything is stored in extension-local browser storage. It works with the
// terminal bridge online, offline, or temporarily out of date, and never leaves
// this browser profile.
//
// This file owns: per-session ON/OFF state, the prompt block, auto-capture and
// the Memory menu (list / create / rename / delete / settings / browse / graph /
// import / export). main.js only wires the button, the prompt and the tool filter.

(() => {
  "use strict";

  const STORE_KEY = "msMemoryState";
  const MEMORY_TOOLS = /^ms_memory_(remember|recall|graph|update|forget|manage)$/;
  const isMemoryTool = (name) => MEMORY_TOOLS.test(String(name || "").split("/").pop().split(".").pop());

  const THINKING_PROMPT =
    "━━━ SEQUENTIAL THINKING ━━━\n" +
    "For complex, ambiguous or multi-stage work (architecture, debugging, level / UI / animation / VFX planning), call `ms_sequential_thinking` first: one thought per call, " +
    "revise earlier thoughts or branch when you find a mistake, raise totalThoughts if the problem is bigger than expected, and finish with nextThoughtNeeded=false only after the plan is checked. " +
    "It executes nothing - follow it with the native engine tools and verify with a read-back. Skip it for trivial one-step requests.";

  function memoryPrompt(name, contextText) {
    const q = JSON.stringify(name);
    return (
      `━━━ GRAPH MEMORY: ${q} (ON) ━━━\n` +
      "The user switched on a persistent local graph memory. It survives new chats and other AI sites, and it grows as you work. " +
      "Tools: `ms_memory_recall` (search), `ms_memory_remember` (save), `ms_memory_graph` (explore links), `ms_memory_update`, `ms_memory_forget`. " +
      `Pass memory=${q} on every memory call.\n` +
      "- Start of a task: if the notes below do not already cover it, call ms_memory_recall with the user's goal and the key nouns.\n" +
      "- Save only durable things: user preferences, design decisions (and why), reusable asset / script / node paths and IDs, conventions, finished milestones, known gotchas. " +
      "Use `entities` + `relations` so related things are linked (e.g. MainMenu -opens-> SettingsPanel). Never save secrets, API keys or unverified guesses.\n" +
      "- Memory can be stale: verify a recalled path or value against the real project before relying on it, and correct it with ms_memory_update when it is wrong.\n" +
      "- Do not narrate memory calls to the user unless it matters; just use them.\n" +
      (contextText ? `Remembered so far:\n${contextText}` : "Remembered so far: (nothing yet - this memory is new.)")
    );
  }

  function memoryNudge(name) {
    return `(Memory ${JSON.stringify(name)} is ON: save new durable preferences, decisions and asset paths with ms_memory_remember; recall before repeating work.)`;
  }

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ───────────────────────── controller ─────────────────────────
  class MemoryController {
    constructor({ bg, providerId, conversationKey, onChange }) {
      this.bg = bg;
      this.providerId = providerId;
      this.conversationKey = conversationKey || (() => "");
      this.onChange = onChange || (() => {});
      this.state = { pending: { on: false, memory: null }, sessions: {}, lastMemory: null };
      this.ctx = { name: "", text: "", at: 0 };
      this.loaded = false;
      this._load();
    }
    _key() {
      const k = this.conversationKey();
      return k ? `${this.providerId}|${k}` : "";
    }
    _load() {
      try {
        chrome.storage.local.get(STORE_KEY, (r) => {
          const s = r && r[STORE_KEY];
          if (s && typeof s === "object") {
            this.state = {
              pending: s.pending && typeof s.pending === "object" ? s.pending : { on: false, memory: null },
              sessions: s.sessions && typeof s.sessions === "object" ? s.sessions : {},
              lastMemory: s.lastMemory || null,
            };
          }
          this.loaded = true;
          this.onChange();
        });
      } catch { this.loaded = true; }
    }
    _save() {
      const keys = Object.keys(this.state.sessions);
      if (keys.length > 250) for (const k of keys.slice(0, keys.length - 250)) delete this.state.sessions[k];
      try { chrome.storage.local.set({ [STORE_KEY]: this.state }); } catch {}
    }
    // The state that applies to the chat in front of the user right now.
    current() {
      const k = this._key();
      if (k && this.state.sessions[k]) return this.state.sessions[k];
      return this.state.pending;
    }
    isOn() { const c = this.current(); return !!(c && c.on && c.memory); }
    memoryRef() { const c = this.current(); return (c && c.memory) || null; }
    name() { return this.ctx.name || this.memoryRef() || ""; }
    setState(on, memory) {
      const k = this._key();
      const next = { on: !!on, memory: memory || this.memoryRef() || this.state.lastMemory || null };
      if (next.memory) this.state.lastMemory = next.memory;
      if (k) this.state.sessions[k] = next;
      else this.state.pending = next;
      this._save();
      this.onChange();
    }
    // A fresh chat gets its real id only after the first message; carry the
    // pending choice over to it so "memory ON" follows the session.
    bind() {
      const k = this._key();
      if (!k || this.state.sessions[k]) return;
      if (this.state.pending && this.state.pending.on) {
        this.state.sessions[k] = { ...this.state.pending };
        this.state.pending = { on: false, memory: this.state.pending.memory };
        this._save();
      }
    }
    async call(op, args) {
      try {
        const r = await this.bg({ type: "memory", op, args: args || {} });
        return r || { ok: false, error: "no response from the extension worker" };
      } catch (e) {
        return { ok: false, error: String((e && e.message) || e) };
      }
    }
    // Pull the context block for the prompt (and make this memory the bridge's default).
    async refresh(query) {
      const ref = this.memoryRef();
      if (!ref) { this.ctx = { name: "", text: "", at: 0 }; return this.ctx; }
      const opened = await this.call("open", { memory: ref });
      if (!opened.ok) { this.ctx = { name: ref, text: "", at: Date.now(), error: opened.error }; return this.ctx; }
      const settings = (opened.active && opened.active.settings) || null;
      const c = await this.call("context", { memory: ref, query: query || "" });
      const recallOn = !(settings && settings.autoRecall === false);
      this.ctx = { name: (opened.active && opened.active.name) || ref, text: c.ok && recallOn ? String(c.text || "") : "", at: Date.now(), error: c.ok ? "" : c.error };
      return this.ctx;
    }
    promptBlock() {
      if (!this.isOn()) return "";
      return memoryPrompt(this.name() || this.memoryRef(), this.ctx.text);
    }
    nudge() { return this.isOn() ? memoryNudge(this.name() || this.memoryRef()) : ""; }
    async autoCaptureEnabled() {
      if (!this.isOn()) return false;
      const r = await this.call("settings", { memory: this.memoryRef() });
      return !!(r.ok && r.settings && r.settings.autoCapture !== false);
    }
    async observe({ user, assistant, tools }) {
      if (!this.isOn()) return null;
      if (!(await this.autoCaptureEnabled())) return null;
      return this.call("observe", { memory: this.memoryRef(), user: String(user || "").slice(0, 4000), assistant: String(assistant || "").slice(0, 6000), tools: tools || [] });
    }
  }

  // ───────────────────────── menu / panel ─────────────────────────
  class MemoryPanel {
    constructor({ mount, controller, anchor, ui }) {
      this.mount = mount;
      this.c = controller;
      this.anchor = anchor || (() => null);
      this.ui = ui || {};
      this.el = null;
      this.open = false;
      this.tab = "memories";
      this.list = [];
      this.sel = null;       // id of the memory shown in Browse / Graph
      this.q = "";
      this.msg = "";
      this._raf = 0;
    }
    isOpen() { return this.open; }
    close() { if (this.el) this.el.hidden = true; this.open = false; if (this._raf) cancelAnimationFrame(this._raf); this._raf = 0; }
    toggle() { this.open ? this.close() : this.openPanel(); }
    async openPanel(tab) {
      if (!this.el) this._build();
      if (tab) this.tab = tab;
      this.el.hidden = false;
      this.open = true;
      this.el.classList.remove("zs-mem-enter"); void this.el.offsetWidth; this.el.classList.add("zs-mem-enter");
      const tick = () => { if (!this.open) return; this._place(); this._raf = requestAnimationFrame(tick); };
      this._raf = requestAnimationFrame(tick);
      this._place();
      this._paint();
      await this._reload();
    }
    _build() {
      const el = document.createElement("div");
      el.id = "zs-mem-panel";
      el.hidden = true;
      el.setAttribute("role", "dialog");
      el.setAttribute("aria-label", "Memory");
      el.addEventListener("click", (e) => this._onClick(e));
      el.addEventListener("input", (e) => this._onInput(e));
      el.addEventListener("change", (e) => this._onChange(e));
      this.mount.appendChild(el);
      this.el = el;
    }
    _place() {
      const el = this.el;
      if (!el || el.hidden) return;
      const a = this.anchor();
      const r = a && a.getBoundingClientRect ? a.getBoundingClientRect() : null;
      const vw = window.innerWidth, vh = window.innerHeight, margin = 10, gap = 8;
      const width = Math.max(300, Math.min(520, vw - margin * 2));
      if (!r || (!r.width && !r.height)) {
        Object.assign(el.style, { width: width + "px", left: Math.max(margin, (vw - width) / 2) + "px", top: "auto", bottom: margin + "px", maxHeight: Math.min(560, vh - margin * 2) + "px" });
        return;
      }
      const below = vh - r.bottom - gap - margin, above = r.top - gap - margin;
      const prev = el.dataset.dir;
      let down;
      if (prev === "down") down = below >= 240 || below >= above;
      else if (prev === "up") down = !(above >= 240 || above >= below);
      else down = below >= Math.min(420, above) || below >= 420;
      const avail = Math.max(200, down ? below : above);
      const left = Math.min(Math.max(margin, r.right - width), Math.max(margin, vw - width - margin));
      const set = { width: width + "px", left: Math.round(left) + "px", maxHeight: Math.min(560, avail) + "px" };
      if (down) { set.top = Math.round(r.bottom + gap) + "px"; set.bottom = "auto"; }
      else { set.bottom = Math.round(vh - r.top + gap) + "px"; set.top = "auto"; }
      Object.assign(el.style, set);
      el.dataset.dir = down ? "down" : "up";
    }
    async _reload() {
      const r = await this.c.call("list", {});
      if (!this.open) return;
      if (!r.ok) {
        this.list = [];
        this.msg = r.error ? `Memory could not load: ${r.error}` : "Memory could not load. Reload the extension and try again.";
        this._paint();
        return;
      }
      this.msg = "";
      this.list = r.memories || [];
      if (!this.sel || !this.list.some((m) => m.id === this.sel)) this.sel = this.c.memoryRef() || (this.list[0] && this.list[0].id) || null;
      this._paint();
      if (this.tab === "browse" || this.tab === "graph") this._loadGraph();
    }
    async _loadGraph() {
      if (!this.sel) return;
      const r = await this.c.call("graph", { memory: this.sel, action: "list", limit: 80 });
      if (!this.open) return;
      this.nodes = r.ok ? r.nodes || [] : [];
      const g = await this.c.call("graph", { memory: this.sel, action: "export" });
      this.full = g.ok ? { nodes: g.nodes || [], edges: g.edges || [] } : { nodes: [], edges: [] };
      this._paint();
    }
    _paint() {
      if (!this.el) return;
      const on = this.c.isOn();
      const cur = this.c.memoryRef();
      const tabs = [["memories", "Memories"], ["settings", "Settings"], ["browse", "Browse"], ["graph", "Graph"]];
      const sel = this.list.find((m) => m.id === this.sel) || null;
      let body = "";
      if (this.tab === "memories") {
        body = `<div class="zs-mem-new"><input type="text" data-f="newname" maxlength="60" placeholder="New memory name, e.g. Roblox classic gui" value="${esc(this._newName || "")}"><button data-act="create" class="zs-mem-btn zs-mem-primary">Create</button></div>` +
          (this.list.length ? `<div class="zs-mem-list">${this.list.map((m) => `
            <div class="zs-mem-card${m.id === cur ? " is-cur" : ""}${m.id === this.sel ? " is-sel" : ""}" data-id="${esc(m.id)}">
              <div class="zs-mem-card-main" data-act="select" data-id="${esc(m.id)}"><b>${esc(m.name)}</b><i>${m.nodes} nodes · ${m.edges} links${m.description ? " · " + esc(m.description) : ""}</i></div>
              <button class="zs-mem-btn${m.id === cur && on ? " zs-mem-primary" : ""}" data-act="use" data-id="${esc(m.id)}" title="Turn memory ON for this chat using ${esc(m.name)}">${m.id === cur && on ? "In use" : "Use here"}</button>
            </div>`).join("")}</div>` : `<div class="zs-mem-empty">No memories yet. Create one above - give it a name that describes the work (a game, a style, an asset pack).</div>`) +
          `<div class="zs-mem-note">A memory is a private local knowledge graph. Turn it ON and the agent recalls it, saves durable preferences, decisions and assets, and brings them into your next chat. Stored in this browser profile, so it works even when the terminal bridge is offline.</div>`;
      } else if (this.tab === "settings") {
        const s = (sel && sel.settings) || {};
        body = !sel ? `<div class="zs-mem-empty">Select a memory first.</div>` : `
          <div class="zs-mem-sethead"><b>${esc(sel.name)}</b><span>${sel.nodes} nodes · ${sel.edges} links</span></div>
          ${[["autoRecall", "Recall into new chats", "Inject the most relevant notes into the prompt when this memory is ON."],
             ["autoCapture", "Auto-save highlights", "After each agent turn, save preferences, decisions, asset paths and a short episode."],
             ["includeEpisodes", "Include recent episodes", "Show the last few auto-journalled sessions in the injected notes."]]
            .map(([k, t, d]) => `<label class="zs-mem-row"><input type="checkbox" data-set="${k}" ${s[k] !== false ? "checked" : ""}><span><b>${t}</b><i>${d}</i></span></label>`).join("")}
          <label class="zs-mem-row"><span><b>Injected context size</b><i>Characters of notes put into the prompt.</i></span><input type="number" data-set="maxContextChars" min="500" max="20000" step="500" value="${esc(s.maxContextChars || 3500)}"></label>
          <label class="zs-mem-row"><span><b>Max nodes</b><i>Lowest-value unpinned notes are pruned beyond this.</i></span><input type="number" data-set="maxNodes" min="100" max="50000" step="100" value="${esc(s.maxNodes || 4000)}"></label>
          <div class="zs-mem-actions">
            <button class="zs-mem-btn" data-act="rename">Rename</button>
            <button class="zs-mem-btn" data-act="export">Export</button>
            <button class="zs-mem-btn" data-act="import">Import</button>
            <button class="zs-mem-btn zs-mem-danger" data-act="delete">Delete</button>
          </div>`;
      } else if (this.tab === "browse") {
        const q = this.q.trim().toLowerCase();
        const nodes = (this.nodes || []).filter((n) => !q || (n.name + " " + n.text + " " + n.kind + " " + (n.tags || []).join(" ")).toLowerCase().includes(q));
        body = !sel ? `<div class="zs-mem-empty">Select a memory first.</div>` :
          `<input type="search" data-f="q" class="zs-mem-search" placeholder="Filter notes…" value="${esc(this.q)}">` +
          (nodes.length ? `<div class="zs-mem-nodes">${nodes.map((n) => `
            <div class="zs-mem-node" data-id="${esc(n.id)}"><span class="zs-mem-kind k-${esc(n.kind)}">${esc(n.kind)}</span>
              <div><b>${esc(n.name)}</b>${n.text && n.text !== n.name ? `<p>${esc(n.text.slice(0, 220))}</p>` : ""}${(n.links || []).length ? `<small>${esc(n.links.slice(0, 3).join(" · "))}</small>` : ""}</div>
              <span class="zs-mem-node-acts"><button class="zs-mem-ico" data-act="pin" data-id="${esc(n.id)}" data-pinned="${n.pinned ? 1 : 0}" title="${n.pinned ? "Unpin" : "Pin: always include"}">${n.pinned ? "★" : "☆"}</button><button class="zs-mem-ico" data-act="del" data-id="${esc(n.id)}" title="Forget this note">✕</button></span></div>`).join("")}</div>` : `<div class="zs-mem-empty">Nothing here yet.</div>`);
      } else {
        body = !sel ? `<div class="zs-mem-empty">Select a memory first.</div>` : `<div class="zs-mem-graph" data-graph></div><div class="zs-mem-note">Larger dots are better-connected notes. Click a dot in Browse to pin or forget it.</div>`;
      }
      this.el.innerHTML = `
        <div class="zs-mem-head">
          <div class="zs-mem-title"><span class="zs-mem-dot" data-on="${on ? 1 : 0}"></span><b>Memory</b><span class="zs-mem-cur">${on && cur ? esc((this.list.find((m) => m.id === cur) || {}).name || cur) : "off in this chat"}</span><span class="zs-mem-local">local</span></div>
          <label class="zs-mem-switch" title="Turn memory on or off for this chat"><input type="checkbox" data-act="toggle" ${on ? "checked" : ""}><span></span></label>
          <button class="zs-mem-x" data-act="close" aria-label="Close memory">✕</button>
        </div>
        <div class="zs-mem-tabs" role="tablist">${tabs.map(([id, l]) => `<button class="zs-mem-tab${id === this.tab ? " is-on" : ""}" data-tab="${id}" role="tab">${l}</button>`).join("")}</div>
        ${this.msg ? `<div class="zs-mem-msg">${esc(this.msg)}</div>` : ""}
        <div class="zs-mem-body">${body}</div>`;
      // Provider composer roots are often <form>s. Memory controls are UI
      // actions, never chat submissions.
      this.el.querySelectorAll("button").forEach((b) => { b.type = "button"; });
      if (this.tab === "graph" && sel) this._drawGraph();
      const ae = document.activeElement;
      void ae;
    }
    _drawGraph() {
      const host = this.el.querySelector("[data-graph]");
      if (!host || !this.full) return;
      const deg = {};
      for (const e of this.full.edges) { deg[e.a] = (deg[e.a] || 0) + 1; deg[e.b] = (deg[e.b] || 0) + 1; }
      const nodes = [...this.full.nodes].sort((a, b) => (deg[b.id] || 0) - (deg[a.id] || 0) || b.importance - a.importance).slice(0, 60);
      if (!nodes.length) { host.innerHTML = `<div class="zs-mem-empty">Empty graph.</div>`; return; }
      const W = 480, H = 320, idx = new Map(nodes.map((n, i) => [n.id, i]));
      const P = nodes.map((n, i) => { const a = (i / nodes.length) * Math.PI * 2; const rad = 40 + (i / nodes.length) * 100; return { x: W / 2 + Math.cos(a) * rad, y: H / 2 + Math.sin(a) * rad, vx: 0, vy: 0 }; });
      const E = this.full.edges.filter((e) => idx.has(e.a) && idx.has(e.b)).map((e) => [idx.get(e.a), idx.get(e.b), e.rel]);
      for (let it = 0; it < 90; it++) {
        for (let i = 0; i < P.length; i++) for (let j = i + 1; j < P.length; j++) {
          let dx = P[i].x - P[j].x, dy = P[i].y - P[j].y; const d2 = Math.max(60, dx * dx + dy * dy), f = 1800 / d2, d = Math.sqrt(d2);
          dx /= d; dy /= d; P[i].vx += dx * f; P[i].vy += dy * f; P[j].vx -= dx * f; P[j].vy -= dy * f;
        }
        for (const [a, b] of E) {
          const dx = P[b].x - P[a].x, dy = P[b].y - P[a].y, d = Math.max(1, Math.hypot(dx, dy)), f = (d - 60) * 0.02;
          P[a].vx += dx / d * f; P[a].vy += dy / d * f; P[b].vx -= dx / d * f; P[b].vy -= dy / d * f;
        }
        for (const p of P) { p.vx += (W / 2 - p.x) * 0.004; p.vy += (H / 2 - p.y) * 0.004; p.x = Math.min(W - 14, Math.max(14, p.x + p.vx * 0.6)); p.y = Math.min(H - 14, Math.max(14, p.y + p.vy * 0.6)); p.vx *= 0.7; p.vy *= 0.7; }
      }
      const lines = E.map(([a, b]) => `<line x1="${P[a].x.toFixed(1)}" y1="${P[a].y.toFixed(1)}" x2="${P[b].x.toFixed(1)}" y2="${P[b].y.toFixed(1)}"/>`).join("");
      const dots = nodes.map((n, i) => `<g><circle class="k-${esc(n.kind)}" cx="${P[i].x.toFixed(1)}" cy="${P[i].y.toFixed(1)}" r="${3 + Math.min(7, deg[n.id] || 0)}"><title>${esc(n.kind)}: ${esc(n.name)}</title></circle>${(deg[n.id] || 0) >= 2 || nodes.length < 16 ? `<text x="${(P[i].x + 6).toFixed(1)}" y="${(P[i].y - 6).toFixed(1)}">${esc(n.name.slice(0, 22))}</text>` : ""}</g>`).join("");
      host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Memory graph"><g class="zs-mem-edges">${lines}</g>${dots}</svg>`;
    }
    async _onClick(e) {
      const t = e.target.closest("[data-act],[data-tab]");
      if (!t) return;
      if (t.dataset.tab) { this.tab = t.dataset.tab; this._paint(); if (this.tab === "browse" || this.tab === "graph") this._loadGraph(); return; }
      const act = t.dataset.act, id = t.dataset.id;
      if (act === "close") return this.close();
      if (act === "toggle") return; // handled on change
      if (act === "select") { this.sel = id; this._paint(); return; }
      if (act === "use") {
        this.c.setState(true, id);
        await this.c.refresh("");
        this.msg = "";
        this.ui.toast && this.ui.toast(`Memory "${(this.list.find((m) => m.id === id) || {}).name || id}" is ON for this chat`);
        this.sel = id; this._paint(); this.ui.onChange && this.ui.onChange();
        return;
      }
      if (act === "create") {
        const name = (this._newName || "").trim();
        if (!name) { this.msg = "Give the memory a name first."; this._paint(); return; }
        const r = await this.c.call("create", { name });
        if (!r.ok) { this.msg = r.error || "Could not create the memory."; this._paint(); return; }
        this._newName = "";
        this.sel = r.created.id;
        this.msg = "";
        await this._reload();
        return;
      }
      if (!this.sel) return;
      if (act === "rename") {
        const cur = this.list.find((m) => m.id === this.sel);
        const name = window.prompt("Rename memory", cur ? cur.name : "");
        if (name && name.trim()) { await this.c.call("rename", { memory: this.sel, name: name.trim() }); await this._reload(); }
        return;
      }
      if (act === "delete") {
        const cur = this.list.find((m) => m.id === this.sel);
        if (window.confirm(`Delete memory "${cur ? cur.name : this.sel}" and all of its notes? This cannot be undone.`)) {
          await this.c.call("delete", { memory: this.sel });
          if (this.c.memoryRef() === this.sel) this.c.setState(false, null);
          this.sel = null;
          await this._reload();
        }
        return;
      }
      if (act === "export") {
        const r = await this.c.call("export", { memory: this.sel });
        if (!r.ok) { this.msg = r.error || "Export failed"; this._paint(); return; }
        const { ok, ...data } = r; void ok;
        const blob = new Blob([JSON.stringify(data, null, 1)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `${(data.id || "memory")}.memory.json`;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
        return;
      }
      if (act === "import") {
        const inp = document.createElement("input");
        inp.type = "file"; inp.accept = ".json,application/json";
        inp.onchange = async () => {
          try {
            const text = await inp.files[0].text();
            const data = JSON.parse(text);
            const r = await this.c.call("import", { data });
            this.msg = r.ok ? `Imported "${r.memory}" (${r.nodes} nodes).` : (r.error || "Import failed");
          } catch (err) { this.msg = "That file is not a valid memory export."; }
          this.tab = "memories"; await this._reload();
        };
        inp.click();
        return;
      }
      if (act === "pin") { await this.c.call("update", { memory: this.sel, node: id, pinned: t.dataset.pinned !== "1" }); await this._loadGraph(); return; }
      if (act === "del") { await this.c.call("forget", { memory: this.sel, node: id }); await this._loadGraph(); await this._reload(); return; }
    }
    _onInput(e) {
      const t = e.target;
      if (t.dataset.f === "newname") this._newName = t.value;
      if (t.dataset.f === "q") { this.q = t.value; const pos = t.selectionStart; this._paint(); const n = this.el.querySelector('[data-f="q"]'); if (n) { n.focus(); n.setSelectionRange(pos, pos); } }
    }
    async _onChange(e) {
      const t = e.target;
      if (t.dataset.act === "toggle") {
        if (t.checked) {
          const ref = this.c.memoryRef() || this.sel || (this.list[0] && this.list[0].id);
          if (!ref) {
            let r = await this.c.call("create", { name: "General" });
            if (r.ok) this.c.setState(true, r.created.id);
            else {
              this.c.setState(false, null);
              this.msg = r.error || "Could not create a local memory.";
              this._paint();
              return;
            }
          } else this.c.setState(true, ref);
          await this.c.refresh("");
        } else this.c.setState(false, this.c.memoryRef());
        this.ui.onChange && this.ui.onChange();
        await this._reload();
        return;
      }
      if (t.dataset.set && this.sel) {
        const v = t.type === "checkbox" ? t.checked : Number(t.value);
        await this.c.call("settings", { memory: this.sel, settings: { [t.dataset.set]: v } });
        await this._reload();
      }
    }
  }

  const RESEND_NOTE = "(System note from Multi-Script - the user just switched Memory on for this chat. This is NOT a new request and NOT something to reply to; carry on with the task and use the memory tools described below from now on.)";
  window.ZSMemory = { RESEND_NOTE, MemoryController, MemoryPanel, isMemoryTool, memoryPrompt, memoryNudge, THINKING_PROMPT, MEMORY_TOOLS };
})();
