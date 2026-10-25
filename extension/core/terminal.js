// terminal.js - the in-extension terminal panel.
//
// WHAT THIS IS
// The chat bar's terminal icon opens a live terminal that RUNS the local bridge
// and shows everything around it: the log stream, which engines are attached,
// which desktop apps are open, and the actions to start / stop / restart it.
// The icon's caret opens the same panel on its "Running" tab - a top-down list of
// every process Multi-Script has going.
//
// HOW IT RUNS THE BRIDGE
// A web page cannot spawn a process, and it should not be able to. The one
// browser-sanctioned route is a Native Messaging host the user registered once
// (runtime/install_native_host.py). The service worker talks to it; this panel
// only asks the worker (host_start / host_stop / host_restart / host_processes).
// If the host is not installed the panel says so plainly and shows the exact
// one-line setup command - it never claims to have started something it did not.
//
// THEME
// Every colour comes from the same CSS custom properties the chat bar uses, so
// the panel follows the user's accent, light/dark mode and backdrop live with no
// JS involvement at all. Nothing here hardcodes a colour.

(() => {
  "use strict";

  const MAX_LINES = 900;   // hard cap on rendered rows; older lines are dropped
  const POLL_MS = 2500;    // fallback poll when the socket is down
  const RUN_POLL_MS = 7000; // "Running" tab: each poll costs a launcher process, keep it gentle
  const TAIL_EVERY_MS = 20000; // how often a dead bridge's stdout file may be re-read

  class TerminalPanel {
    constructor({ mount, bg, getStatus, onNeedReconnect, ui, anchor }) {
      this.mount = mount;              // element the panel is appended to
      this.anchor = anchor || null;    // () => the terminal icon; the panel docks to it
      this.bg = bg;                    // () => Promise, the worker channel
      this.getStatus = getStatus;      // () => the live status object
      this.onNeedReconnect = onNeedReconnect || (() => {});
      this.ui = ui || {};
      this.el = null;
      this.open = false;
      this.lines = [];                 // {seq,t,level,msg}
      this.seen = new Set();           // seqs already rendered (dedupe push+backlog)
      this.cursor = 0;                 // highest seq rendered; polls ask for > this
      this.service = null;             // last service snapshot from the bridge
      this.filter = "all";
      this.autoscroll = true;
      this.pollTimer = 0;
      this.pending = null;             // in-flight snapshot request
      this.unread = 0;
      this.tab = "log";                // "log" | "running"
      this.busy = null;                // "starting" | "stopping" | "restarting" | null
      this.host = { known: false, installed: null, info: null, prefs: null };
      this.procs = null;               // last host_processes reply
      this.onBusy = (ui && ui.onBusy) || (() => {});
      this.runTimer = 0;
      // Repaint guards: a view is only rebuilt when what it shows has CHANGED.
      // Rebuilding identical DOM every poll was the "terminal keeps refreshing"
      // flicker (scroll jumped, hover/focus lost, buttons swapped under the mouse).
      this._sigLines = "";
      this._sigRun = "";
      this._sigSvc = "";
      this._lastLocal = "";
    }

    // ── construction ───────────────────────────────────────────────────────
    build() {
      if (this.el) return this.el;
      const wrap = document.createElement("div");
      wrap.id = "zs-term";
      wrap.className = "zs-term";
      wrap.hidden = true;
      wrap.setAttribute("role", "dialog");
      wrap.setAttribute("aria-label", "Multi-Script bridge terminal");
      wrap.innerHTML = this._markup();
      this.mount.appendChild(wrap);
      this.el = wrap;

      this.body = wrap.querySelector(".zs-term-body");
      this.runView = wrap.querySelector(".zs-term-run");
      this.countEl = wrap.querySelector(".zs-term-count");
      this.headState = wrap.querySelector(".zs-term-state");
      this.headMeta = wrap.querySelector(".zs-term-meta");
      this.pill = wrap.querySelector(".zs-term-pill");
      this.services = wrap.querySelector(".zs-term-services");

      this._wire();
      return wrap;
    }

    _markup() {
      // Static chrome only. Every dynamic value is written by _paint* so the
      // markup cannot drift from the state it claims to show.
      return `
        <div class="zs-term-head">
          <div class="zs-term-title">
            <span class="zs-term-dot" data-state="down"></span>
            <span class="zs-term-name">Bridge</span>
            <span class="zs-term-pill" data-state="down">offline</span>
            <span class="zs-term-state">connecting…</span>
          </div>
          <div class="zs-term-meta"></div>
          <button class="zs-term-x" type="button" title="Close" aria-label="Close terminal">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg>
          </button>
        </div>

        <div class="zs-term-tabs" role="tablist">
          <button type="button" class="zs-term-tab is-on" data-tab="log" role="tab">Terminal</button>
          <button type="button" class="zs-term-tab" data-tab="running" role="tab">Running <b class="zs-term-count"></b></button>
        </div>

        <div class="zs-term-bar" data-pane="log">
          <div class="zs-term-filters" role="tablist">
            <button type="button" class="zs-term-filter is-on" data-level="all">All</button>
            <button type="button" class="zs-term-filter" data-level="info">Info</button>
            <button type="button" class="zs-term-filter" data-level="ok">OK</button>
            <button type="button" class="zs-term-filter" data-level="warn">Warn</button>
            <button type="button" class="zs-term-filter" data-level="error">Error</button>
          </div>
          <div class="zs-term-tools">
            <button type="button" class="zs-term-tool" data-act="copy" title="Copy the visible log">Copy</button>
            <button type="button" class="zs-term-tool" data-act="clear" title="Clear this view (the log file is untouched)">Clear</button>
            <button type="button" class="zs-term-tool" data-act="follow" title="Follow new lines" data-on="1">Follow</button>
          </div>
        </div>

        <div class="zs-term-body" data-pane="log" tabindex="0" aria-live="polite"></div>
        <div class="zs-term-run" data-pane="running" hidden></div>

        <div class="zs-term-foot">
          <div class="zs-term-services"></div>
          <div class="zs-term-acts">
            <button type="button" class="zs-term-btn zs-term-btn-primary" data-act="start" hidden>Start bridge</button>
            <button type="button" class="zs-term-btn" data-act="restart" hidden>Restart</button>
            <button type="button" class="zs-term-btn zs-term-btn-danger" data-act="stop" hidden>Stop</button>
            <button type="button" class="zs-term-btn" data-act="reconnect" hidden>Reconnect</button>
            <button type="button" class="zs-term-btn" data-act="help">Help</button>
          </div>
        </div>
      `;
    }

    _wire() {
      const q = (sel) => this.el.querySelector(sel);
      q(".zs-term-x").addEventListener("click", (e) => { e.stopPropagation(); this.close(); });

      this.el.querySelectorAll(".zs-term-tab").forEach((b) => {
        b.addEventListener("click", () => this.showTab(b.dataset.tab));
      });

      this.el.querySelectorAll(".zs-term-filter").forEach((b) => {
        b.addEventListener("click", () => {
          this.filter = b.dataset.level;
          this.el.querySelectorAll(".zs-term-filter").forEach((o) =>
            o.classList.toggle("is-on", o === b));
          this._paintLines();
        });
      });

      this.el.querySelectorAll(".zs-term-tool").forEach((b) => {
        b.addEventListener("click", () => this._tool(b.dataset.act, b));
      });

      this.el.querySelectorAll(".zs-term-btn[data-act]").forEach((b) => {
        b.addEventListener("click", () => this._act(b.dataset.act));
      });

      // Autoscroll is a property of the USER's reading position, not of the
      // data: scrolling up to read history must not be yanked back down by the
      // next line, so we only follow while they are already at the bottom.
      this.body.addEventListener("scroll", () => {
        const atBottom = this.body.scrollHeight - this.body.scrollTop - this.body.clientHeight < 24;
        this.autoscroll = atBottom;
        const follow = this.el.querySelector('[data-act="follow"]');
        if (follow) follow.dataset.on = atBottom ? "1" : "0";
      });

      // Clicks inside the panel must not reach the page/composer underneath.
      this.el.addEventListener("mousedown", (e) => e.stopPropagation());
      this.el.addEventListener("click", (e) => e.stopPropagation());
      this.el.addEventListener("keydown", (e) => e.stopPropagation());
    }

    // ── lifecycle ──────────────────────────────────────────────────────────
    toggle() { return this.open ? this.close() : this.openPanel(); }

    async openPanel(tab) {
      this.build();
      this.el.hidden = false;
      this.open = true;
      this._enter();
      this.unread = 0;
      this.showTab(tab || this.tab, true);
      this._startPlace();
      this._paintHead();
      this._paintServices();
      this._loadHost();
      // Paint the backlog immediately, even before the first response, so the
      // panel is never an empty box while a request is in flight.
      this._paintLines();
      await this.refresh();
      this._startPoll();
    }

    // The slide-in plays only when the panel is OPENED. It used to be a plain CSS
    // animation on #zs-term, so anything that re-attached the node (the host page
    // re-rendering, the bar re-docking) or flipped it above/below the icon replayed
    // it - which read as the panel "refreshing" or closing and reopening.
    _enter() {
      const el = this.el;
      if (!el) return;
      el.classList.remove("zs-term-enter");
      void el.offsetWidth;
      el.classList.add("zs-term-enter");
      clearTimeout(this._enterT);
      this._enterT = setTimeout(() => el.classList.remove("zs-term-enter"), 260);
    }

    close() {
      if (!this.el) return;
      this.el.hidden = true;
      this.open = false;
      this._stopPoll();
      this._stopRun();
      this._stopPlace();
    }

    // ── placement ─────────────────────────────────────────────────────────
    // The panel is position:fixed and DOCKED to the terminal icon. It opens
    // downward when there is room and flips upward when there is not - the chat
    // bar sits just above a composer at the bottom of the viewport on most sites
    // (Notion especially), so "always drop down" put it off-screen. It re-docks
    // every frame while open because the bar itself is re-anchored every frame.
    _startPlace() {
      this._stopPlace();
      const tick = () => {
        if (!this.open) return;
        this._place();
        this._raf = requestAnimationFrame(tick);
      };
      this._raf = requestAnimationFrame(tick);
      this._place();
    }
    _stopPlace() { if (this._raf) cancelAnimationFrame(this._raf); this._raf = 0; }
    _place() {
      const el = this.el;
      if (!el || el.hidden) return;
      const a = this.anchor && this.anchor();
      const r = a && a.getBoundingClientRect ? a.getBoundingClientRect() : null;
      const vw = window.innerWidth, vh = window.innerHeight;
      const margin = 10, gap = 8;
      const width = Math.max(300, Math.min(560, vw - margin * 2));
      if (!r || (!r.width && !r.height)) {   // no anchor: centre it low, never off-screen
        Object.assign(el.style, { width: width + "px", left: Math.max(margin, (vw - width) / 2) + "px", top: "auto", bottom: margin + "px", maxHeight: Math.min(460, vh - margin * 2) + "px" });
        el.dataset.dir = "up";
        return;
      }
      const below = vh - r.bottom - gap - margin;
      const above = r.top - gap - margin;
      const want = 400;
      // Hysteresis: once docked above/below, stay there unless it clearly no longer
      // fits. Re-deciding from scratch every frame flipped the panel back and
      // forth when the two sides were about equal.
      const prev = el.dataset.dir;
      let down;
      if (prev === "down") down = below >= 220 || below >= above;
      else if (prev === "up") down = !(above >= 220 || above >= below);
      else down = below >= Math.min(want, above) || below >= want;
      const avail = Math.max(180, down ? below : above);
      const left = Math.min(Math.max(margin, r.right - width), Math.max(margin, vw - width - margin));
      const set = { width: width + "px", left: Math.round(left) + "px", maxHeight: Math.min(460, avail) + "px" };
      if (down) { set.top = Math.round(r.bottom + gap) + "px"; set.bottom = "auto"; }
      else { set.bottom = Math.round(vh - r.top + gap) + "px"; set.top = "auto"; }
      Object.assign(el.style, set);
      el.dataset.dir = down ? "down" : "up";
    }

    isOpen() { return this.open; }
    currentTab() { return this.tab; }

    // Switch between the log and the "Running" overview. The caret next to the
    // terminal icon opens straight onto "running".
    showTab(tab, quiet) {
      this.tab = tab === "running" ? "running" : "log";
      if (!this.el) return;
      this.el.querySelectorAll(".zs-term-tab").forEach((b) => b.classList.toggle("is-on", b.dataset.tab === this.tab));
      this.el.querySelectorAll("[data-pane]").forEach((n) => { n.hidden = n.dataset.pane !== this.tab; });
      this.el.dataset.tab = this.tab;
      if (this.tab === "running") { this._startRun(); this._paintRunning(); }
      else { this._stopRun(); if (this.body && this.autoscroll) this.body.scrollTop = this.body.scrollHeight; }
      if (!quiet) this._paintHead();
    }

    // ── native host (the launcher) ────────────────────────────────────────
    async _loadHost() {
      try {
        const [info, prefs] = await Promise.all([
          this.bg({ type: "host_info" }).catch(() => null),
          this.bg({ type: "host_prefs" }).catch(() => null),
        ]);
        this.host.known = true;
        this.host.installed = !!(info && info.ok);
        this.host.info = info && info.ok ? info : null;
        this.host.prefs = prefs && prefs.ok ? prefs : null;
        if (!this.host.installed && info && info.extensionId) this.host.extensionId = info.extensionId;
        if (prefs && prefs.extensionId) this.host.extensionId = prefs.extensionId;
      } catch {
        this.host.known = true;
        this.host.installed = false;
      }
      this._paintHead();
      if (this.tab === "running") this._paintRunning();
    }

    _setBusy(v) {
      this.busy = v;
      try { this.onBusy(v); } catch {}
      this._paintHead();
      if (this.tab === "running") this._paintRunning();
    }

    // Run a host action through the worker. Returns the reply; never throws.
    async _hostAct(kind) {
      const type = { start: "host_start", stop: "host_stop", restart: "host_restart" }[kind];
      if (!type || this.busy) return null;
      this._setBusy({ start: "starting", stop: "stopping", restart: "restarting" }[kind]);
      this._appendLocal(`${{ start: "Starting", stop: "Stopping", restart: "Restarting" }[kind]} the bridge…`);
      let r;
      try { r = await this.bg({ type }); } catch (e) { r = { ok: false, error: String((e && e.message) || e) }; }
      this._setBusy(null);
      if (r && r.ok) {
        this.host.installed = true;
        if (kind === "stop") {
          this._appendLocal(r.already ? "The bridge was not running." : "Bridge stopped. It will stay stopped until you start it again.");
          if (this.ui.toast) this.ui.toast("Bridge stopped.");
        } else {
          this._appendLocal(r.already ? "The bridge is already running." : (r.listening ? "Bridge is up." : "Bridge process started - still booting its engines…"));
          if (this.ui.toast) this.ui.toast(r.already ? "Bridge already running." : "Bridge started.");
          this.cursor = 0; this.seen.clear();
        }
        setTimeout(() => this.refresh(), 700);
        if (this.tab === "running") this._refreshProcs();
        return r;
      }
      this._hostFailed(r || {});
      return r;
    }

    _hostFailed(r, auto) {
      if (r.code === "host_missing" || r.code === "host_forbidden") {
        this.host.installed = false;
        if (r.extensionId) this.host.extensionId = r.extensionId;
        const id = this.host.extensionId || "<your extension id>";
        const cmd = `python runtime/install_native_host.py --extension-id ${id}`;
        if (!auto) copyText(cmd);
        this._appendLocal([
          r.code === "host_forbidden"
            ? "The launcher is installed, but for a different extension ID."
            : "One-time setup needed - the launcher is not installed yet.",
          "",
          "A browser extension cannot start programs by itself. The launcher is a tiny",
          "helper you register once; after that this terminal starts, stops and watches",
          "the bridge for you - no launcher script to keep open.",
          "",
          "  Windows : double-click  Setup.bat   in the Multi-Script folder",
          "  macOS   : run  MacOS_Setup.command   (or: bash Setup.sh)",
          "  Linux   : run  bash Setup.sh",
          "  or run  : " + cmd,
          auto ? "" : "            (copied to your clipboard)",
          "",
          "Then fully restart the browser once and click Start again.",
          "No time for setup? Double-click  Start.bat  (macOS: MacOS_Start.command) -",
          "it runs the same bridge in its own window and this panel connects to it.",
        ].join("\n"));
        if (this.ui.banner && !auto) this.ui.banner("warn", "One-time setup needed", "Run " + ZS.setupCommand() + " once (or " + ZS.startCommand() + " to run the bridge right now); then this terminal starts the bridge for you.");
      } else {
        const lines = ["Could not start the bridge: " + (r.error || r.code || "unknown error")];
        if (Array.isArray(r.tail) && r.tail.length) lines.push("", "Last output from the bridge:", ...r.tail.slice(-14));
        this._appendLocal(lines.join("\n"));
        if (this.ui.toast) this.ui.toast("Could not start the bridge - see the terminal.");
      }
    }

    // ── "Running" overview ────────────────────────────────────────────────
    _startRun() {
      this._stopRun();
      this._refreshProcs();
      this.runTimer = setInterval(() => { if (this.open && this.tab === "running" && !document.hidden) this._refreshProcs(); }, RUN_POLL_MS);
    }
    _stopRun() { if (this.runTimer) clearInterval(this.runTimer); this.runTimer = 0; }

    async _refreshProcs() {
      if (this._procPending) return;
      this._procPending = true;
      try {
        const [r] = await Promise.all([
          this.bg({ type: "host_processes" }).catch(() => null),
          this.refresh().catch(() => null),
        ]);
        this.procs = r && r.ok ? r : null;
        if (r && r.ok) this.host.installed = true;
        else if (r && (r.code === "host_missing" || r.code === "host_forbidden")) {
          this.host.installed = false;
          if (r.extensionId) this.host.extensionId = r.extensionId;
        }
      } finally {
        this._procPending = false;
      }
      if (this.tab === "running") this._paintRunning();
      this._paintCount();
    }

    _paintCount() {
      if (!this.countEl) return;
      const svc = this.service || {};
      const up = (Array.isArray(svc.servers) ? svc.servers : []).filter((x) => x.alive).length;
      const bridge = (this.getStatus() || {}).connected ? 1 : 0;
      const apps = this.procs && Array.isArray(this.procs.apps) ? this.procs.apps.length : 0;
      const n = bridge + up + apps;
      this.countEl.textContent = n ? String(n) : "";
    }

    _paintRunning(force) {
      if (!this.runView) return;
      const st = this.getStatus() || {};
      const svc = this.service || {};
      const up = !!st.connected;
      // Nothing to show has changed -> keep the existing DOM. Also never rebuild
      // under the user's pointer/keyboard: swapping a button between mousedown and
      // mouseup drops the click (and the page-level outside-click handler used to
      // read the detached target as "clicked outside" and close the panel).
      const sig = JSON.stringify([
        up, this.busy, this._transport, this.tab, this.host.installed, this.host.prefs && this.host.prefs.autoStart,
        this.host.info && this.host.info.hostVersion, svc.bridgeVersion, svc.port, svc.clients,
        up && svc.uptimeSeconds != null ? Math.floor(svc.uptimeSeconds / 15) : null,
        svc.environment ? [svc.environment.python, !!svc.environment.uvx, !!svc.environment.npx, !!svc.environment.blenderAddon] : null,
        Array.isArray(svc.servers) ? svc.servers.map((x) => [x.id, !!x.alive, x.tools]) : null,
        this.procs ? [(this.procs.processes || []).map((p) => [p.pid, p.label]), (this.procs.apps || []).map((a) => [a.label, a.pid])] : null,
      ]);
      if (!force && sig === this._sigRun && this.runView.childNodes.length) return;
      const ae = document.activeElement;
      const touching = this.runView.matches(":hover") && this.runView.querySelector("button:active");
      if (!force && touching) return;
      if (!force && ae && this.runView.contains(ae) && ae.tagName === "INPUT" && this.runView.childNodes.length) {
        this._sigRun = sig;   // a checkbox has focus: only skip the rebuild, state is saved on change
        return;
      }
      this._sigRun = sig;
      const scrollTop = this.runView.scrollTop;
      const frag = document.createDocumentFragment();

      const section = (title) => {
        const sec = document.createElement("div");
        sec.className = "zs-run-sec";
        const h = document.createElement("div");
        h.className = "zs-run-h";
        h.textContent = title;
        sec.appendChild(h);
        frag.appendChild(sec);
        return sec;
      };
      const row = (sec, { state, name, detail, badge }) => {
        const r = document.createElement("div");
        r.className = "zs-run-row";
        const d = document.createElement("i");
        d.className = "zs-run-dot";
        d.dataset.state = state || "off";
        const n = document.createElement("span");
        n.className = "zs-run-name";
        n.textContent = name;
        const t = document.createElement("span");
        t.className = "zs-run-detail";
        t.textContent = detail || "";
        r.append(d, n, t);
        if (badge) {
          const b = document.createElement("b");
          b.className = "zs-run-badge";
          b.textContent = badge;
          r.appendChild(b);
        }
        sec.appendChild(r);
        return r;
      };

      // Bridge
      const s1 = section("Bridge");
      const bits = [];
      if (svc.bridgeVersion) bits.push("v" + svc.bridgeVersion);
      if (svc.port) bits.push(":" + svc.port);
      if (up && svc.uptimeSeconds != null) bits.push(fmtUp(svc.uptimeSeconds));
      if (up && svc.clients != null) bits.push(`${svc.clients} tab${svc.clients === 1 ? "" : "s"}`);
      const bpid = this.procs && (this.procs.processes || []).find((p) => p.role === "bridge");
      if (bpid) bits.push("pid " + bpid.pid);
      row(s1, {
        state: this.busy ? "busy" : (up ? "on" : (this._transport === "http" ? "warn" : "off")),
        name: "Multi-Script bridge",
        detail: this.busy ? this.busy + "…" : (up ? bits.join(" · ") : (this._transport === "http" ? "process up · socket reconnecting" : "not running")),
      });
      // 6.28: stale bridge warning. An old bridge keeps holding the port after
      // an update, silently serving last version's tools - say so out loud.
      const extVer = String(st.extensionVersion || "");
      if (up && svc.bridgeVersion && extVer && String(svc.bridgeVersion) !== extVer) {
        row(s1, {
          state: "warn",
          name: "Update pending",
          detail: `bridge is v${svc.bridgeVersion}, extension is v${extVer} - press Restart (or run Setup once) to switch to the new bridge`,
        });
      }
      // 6.28: environment diagnostics - "why is my engine down" answered at a
      // glance (uvx missing => Unity/Blender can't start, npx => Godot).
      const env = svc.environment;
      if (env && up) {
        const eb = [`Python ${env.python}`];
        eb.push(env.uvx ? "uvx ✓" : "uvx ✗ needed by Unity/Blender");
        eb.push(env.npx ? "npx ✓" : "npx ✗ needed by Godot");
        eb.push(env.blenderAddon ? "Blender add-on ✓" : "Blender add-on ✗ run Setup");
        row(s1, { state: env.uvx && env.npx ? "idle" : "warn", name: "This PC", detail: eb.join(" · ") });
      }

      // Engines (MCP servers the bridge supervises)
      const s2 = section("Engines & MCP servers");
      const servers = Array.isArray(svc.servers) ? svc.servers : [];
      if (!servers.length) row(s2, { state: "off", name: up ? "No engines attached" : "Waiting for the bridge", detail: "" });
      for (const sv of servers) {
        const n = Number(sv.tools) || 0;
        if (sv.enabled === false) { row(s2, { state: "idle", name: String(sv.id), detail: "switched off in Settings → Engines" }); continue; }
        row(s2, { state: sv.alive ? "on" : "off", name: String(sv.id), detail: sv.alive ? (n ? `${n} native tools` : "connected") : "down", badge: n ? String(n) : "" });
      }

      // Desktop apps (only knowable through the launcher)
      const s3 = section("Apps on this PC");
      if (this.procs && Array.isArray(this.procs.apps)) {
        const names = ["Roblox Studio", "Unity Editor", "Godot", "Blender"];
        const found = new Map(this.procs.apps.map((a) => [a.label, a]));
        for (const nme of names) {
          const a = found.get(nme);
          row(s3, { state: a ? "on" : "idle", name: nme, detail: a ? "running" : "not detected" });
        }
        for (const a of this.procs.apps) if (!names.includes(a.label)) row(s3, { state: "on", name: a.label, detail: "running" });
      } else {
        row(s3, { state: "idle", name: this.host.installed === false ? "Install the launcher to see open apps" : "Checking…", detail: "" });
      }

      // Processes (from the launcher)
      const mcpProcs = this.procs && (this.procs.processes || []).filter((p) => p.role === "mcp");
      if (mcpProcs && mcpProcs.length) {
        const s4 = section("Processes");
        for (const p of mcpProcs.slice(0, 8)) row(s4, { state: "on", name: p.label, detail: "pid " + p.pid });
      }

      // Launcher
      const s5 = section("Launcher");
      const inst = this.host.installed;
      row(s5, {
        state: inst ? "on" : (inst === false ? "warn" : "idle"),
        name: inst ? "Terminal launcher installed" : (inst === false ? "Not installed (one-time setup)" : "Checking…"),
        detail: inst && this.host.info ? "v" + this.host.info.hostVersion + " · Python " + this.host.info.pythonVersion : "",
      });
      const auto = document.createElement("label");
      auto.className = "zs-run-toggle";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = !(this.host.prefs && this.host.prefs.autoStart === false);
      cb.addEventListener("change", async () => {
        try { this.host.prefs = await this.bg({ type: "host_prefs", set: true, autoStart: cb.checked }); } catch {}
        if (this.ui.toast) this.ui.toast(cb.checked ? "Bridge will start automatically." : "Auto-start off.");
      });
      const lbl = document.createElement("span");
      lbl.textContent = "Start the bridge automatically when a chat opens";
      auto.append(cb, lbl);
      s5.appendChild(auto);

      const acts = document.createElement("div");
      acts.className = "zs-run-acts";
      const mk = (label, cls, fn, disabled) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "zs-term-btn " + (cls || "");
        b.textContent = label;
        b.disabled = !!disabled;
        b.addEventListener("click", fn);
        acts.appendChild(b);
      };
      if (!up && !(this._transport === "http")) mk("Start bridge", "zs-term-btn-primary", () => this._hostAct("start"), !!this.busy);
      else { mk("Restart", "", () => this._hostAct("restart"), !!this.busy); mk("Stop", "zs-term-btn-danger", () => this._hostAct("stop"), !!this.busy); }
      if (inst === false) mk("Copy setup command", "", () => this._copySetup());
      frag.appendChild(acts);

      this.runView.replaceChildren(frag);
      this.runView.scrollTop = scrollTop;
    }

    async _copySetup() {
      const id = this.host.extensionId || "<your extension id>";
      const ok = await copyText(`python runtime/install_native_host.py --extension-id ${id}`);
      if (this.ui.toast) this.ui.toast(ok ? "Setup command copied." : "Could not copy - see the terminal tab.");
    }

    // ── data ───────────────────────────────────────────────────────────────
    async refresh() {
      // Re-entrancy guard. `openPanel()` awaits a refresh while the poll timer
      // is already running, so two snapshots can otherwise be in flight at once
      // - and they would resolve out of order, letting the older one overwrite
      // the newer cursor. The in-flight promise is returned to callers instead,
      // and cleared only when the request actually settles.
      if (this.pending) return this.pending;
      const p = (async () => {
        let r;
        try {
          // Ask only for what we do not have. `this.cursor` is the highest seq
          // rendered so far, so an idle poll is a tiny no-op instead of
          // re-sending the whole ring every 2.5s. The `seen` Set stays as a
          // belt-and-braces guard for a push racing this snapshot.
          r = await this.bg({ type: "terminal_snapshot", since: this.cursor, limit: 400 });
        } catch (e) {
          r = { ok: false, error: String((e && e.message) || e) };
        }
        if (r && r.ok) {
          this._ingest(r.lines || []);
          if (typeof r.newest === "number") this.cursor = Math.max(this.cursor, r.newest);
          if (r.service) this.service = r.service;
          this._transport = r.via || "ws";
        } else {
          this._transport = "down";
          if (this.host.installed) await this._showCrashTail();
        }
        this._paintHead();
        this._paintServices();
        this._paintLines();
        return r;
      })();
      this.pending = p;
      try {
        return await p;
      } finally {
        if (this.pending === p) this.pending = null;
      }
    }

    // The bridge is not answering: its own stdout file (written by the launcher)
    // is the only place a startup crash - a Python traceback - is visible.
    async _showCrashTail() {
      if (this._tailAt && Date.now() - this._tailAt < TAIL_EVERY_MS) return;
      this._tailAt = Date.now();
      let r;
      try { r = await this.bg({ type: "host_tail", lines: 40 }); } catch { return; }
      if (!r || !r.ok || !Array.isArray(r.lines) || !r.lines.length) return;
      const text = r.lines.join("\n");
      if (text === this._tailText) return;
      this._tailText = text;
      this._appendLocal("Last output while the bridge was not running:\n" + text);
    }

    // A pushed line (the socket sends these unprompted while the panel is open).
    push(lines) {
      if (!Array.isArray(lines) || !lines.length) return;
      const added = this._ingest(lines);
      // Keep the cursor ahead of the push, so the next poll does not re-ask for
      // lines the socket has already delivered.
      for (const ln of lines) {
        const s = Number(ln && ln.seq) || 0;
        if (s > this.cursor) this.cursor = s;
      }
      if (!this.open) { if (added) this.unread += added; return; }
      this._paintLines();
      this._paintHead();
    }

    cleared() {
      this.lines = [];
      this._sigLines = "";
      this.seen.clear();
      // NOTE: the cursor is deliberately NOT reset. The bridge clears its ring but
      // keeps counting seq upward, so restarting from 0 would re-fetch lines that
      // still exist in the file and re-render them as if they were new.
      this._paintLines();
    }

    // The bridge process restarted: its seq counter began again at 1, so every
    // cursor we hold now points past the end of the new ring. Forget everything
    // and re-read - this is the one case where resetting the cursor is correct.
    reset() {
      this.lines = [];
      this._sigLines = "";
      this._sigRun = "";
      this._sigSvc = "";
      this.seen.clear();
      this.cursor = 0;
      this.service = null;
      this._paintLines();
      if (this.open) {
        this._paintHead();
        this._paintServices();
        this.refresh();
      }
    }

    _ingest(lines) {
      let added = 0;
      for (const ln of lines) {
        if (!ln || typeof ln.msg !== "string") continue;
        const seq = Number(ln.seq) || 0;
        // Dedupe by seq: a push can race the snapshot that contains the same
        // line, and showing it twice looks like the bridge repeated itself.
        if (seq && this.seen.has(seq)) continue;
        if (seq) this.seen.add(seq);
        this.lines.push({ seq, t: ln.t || "", level: ln.level || "info", msg: ln.msg });
        added++;
      }
      if (added) this._sigLines = "";   // content changed: the next paint must run
      if (this.lines.length > MAX_LINES) {
        const drop = this.lines.length - MAX_LINES;
        for (const l of this.lines.slice(0, drop)) if (l.seq) this.seen.delete(l.seq);
        this.lines = this.lines.slice(drop);
      }
      return added;
    }

    _startPoll() {
      this._stopPoll();
      // Polling is a fallback, not the mechanism: while the socket is live the
      // pushes keep the panel current, so we only poll when it is not.
      this.pollTimer = setInterval(() => {
        if (!this.open) return;
        const st = this.getStatus() || {};
        if (this._transport === "ws" && st.connected) return;
        this.refresh();
      }, POLL_MS);
    }

    _stopPoll() {
      if (this.pollTimer) clearInterval(this.pollTimer);
      this.pollTimer = 0;
    }

    // ── painting ───────────────────────────────────────────────────────────
    _paintHead() {
      if (!this.el) return;
      const st = this.getStatus() || {};
      const up = !!st.connected;
      const reachable = this._transport === "http";
      const state = up ? "live" : (reachable ? "partial" : "down");
      const dot = this.el.querySelector(".zs-term-dot");
      if (dot) dot.dataset.state = state;

      const text = this.busy
        ? this.busy + "…"
        : up
          ? "connected"
          : (reachable ? "process up · socket reconnecting" : "not running");
      if (this.headState) this.headState.textContent = text;

      const svc = this.service || {};
      const bits = [];
      if (svc.bridgeVersion) bits.push(`v${svc.bridgeVersion}`);
      if (svc.port) bits.push(`:${svc.port}`);
      if (svc.uptimeSeconds != null && up) bits.push(`${Math.round(svc.uptimeSeconds)}s up`);
      if (svc.clients != null && up) bits.push(`${svc.clients} client${svc.clients === 1 ? "" : "s"}`);
      if (this.unread && !this.open) bits.push(`${this.unread} new`);
      if (this.headMeta) this.headMeta.textContent = bits.join(" · ");

      // Only offer actions that are actually meaningful in this state.
      const start = this.el.querySelector('[data-act="start"]');
      const rec = this.el.querySelector('[data-act="reconnect"]');
      const stop = this.el.querySelector('[data-act="stop"]');
      const restart = this.el.querySelector('[data-act="restart"]');
      if (start) { start.hidden = up || reachable; start.disabled = !!this.busy; }
      if (rec) rec.hidden = up;
      if (stop) { stop.hidden = !(up || reachable) || this.host.installed === false; stop.disabled = !!this.busy; }
      if (restart) { restart.hidden = !(up || reachable) || this.host.installed === false; restart.disabled = !!this.busy; }
      this._paintCount();

      if (this.pill) {
        this.pill.dataset.state = this.busy ? "partial" : state;
        this.pill.textContent = this.busy ? "busy" : (up ? "live" : (reachable ? "partial" : "offline"));
      }
    }

    _paintServices() {
      if (!this.el || !this.services) return;
      const svc = this.service || {};
      const servers = Array.isArray(svc.servers) ? svc.servers : [];
      const sig = JSON.stringify(servers.map((x) => [x.id, !!x.alive, x.tools]));
      if (sig === this._sigSvc && this.services.childNodes.length) return;
      this._sigSvc = sig;
      if (!servers.length) {
        this.services.innerHTML = `<span class="zs-term-svc zs-term-svc-none">no engines attached</span>`;
        return;
      }
      this.services.innerHTML = servers.map((s) => {
        const cls = s.alive ? "is-up" : "is-down";
        const n = Number(s.tools) || 0;
        return `<span class="zs-term-svc ${cls}" title="${escapeAttr(s.id)} — ${s.alive ? "alive" : "down"}${n ? `, ${n} tools` : ""}">
          <i></i>${escapeHtml(s.id)}${n ? `<b>${n}</b>` : ""}</span>`;
      }).join("");
    }

    _paintLines() {
      if (!this.body) return;
      const rows = this.filter === "all"
        ? this.lines
        : this.lines.filter((l) => l.level === this.filter);

      // Skip identical repaints (the 2.5s offline poll used to rebuild the whole
      // log every tick, snapping the scroll position and killing text selection).
      const last = rows.length ? rows[rows.length - 1] : null;
      const sig = this.filter + "|" + rows.length + "|" + (rows.length ? rows[0].seq + ":" + rows[0].msg.length : "") + "|" +
        (last ? last.seq + ":" + last.msg.length : "") + "|" + this.lines.length;
      if (sig === this._sigLines && this.body.childNodes.length) return;
      this._sigLines = sig;
      const keepTop = this.body.scrollTop;

      if (!rows.length) {
        this.body.innerHTML = `<div class="zs-term-empty">${
          this.lines.length ? "No lines match this filter." : "Waiting for the bridge…"
        }</div>`;
        return;
      }

      // Build with textContent, never innerHTML: log lines contain model and
      // engine output, and rendering them as markup would be an injection path
      // straight from a tool result into the page.
      const frag = document.createDocumentFragment();
      for (const l of rows) {
        const row = document.createElement("div");
        row.className = "zs-term-line";
        row.dataset.level = l.level;
        const t = document.createElement("span");
        t.className = "zs-term-t";
        t.textContent = l.t || "";
        const m = document.createElement("span");
        m.className = "zs-term-m";
        m.textContent = l.msg;
        row.appendChild(t);
        row.appendChild(m);
        frag.appendChild(row);
      }
      this.body.replaceChildren(frag);
      if (this.autoscroll) this.body.scrollTop = this.body.scrollHeight;
      else this.body.scrollTop = keepTop;
    }

    // ── tools ──────────────────────────────────────────────────────────────
    async _tool(act, btn) {
      if (act === "copy") {
        const rows = this.filter === "all" ? this.lines : this.lines.filter((l) => l.level === this.filter);
        const text = rows.map((l) => `${l.t} ${l.msg}`).join("\n");
        const ok = await copyText(text);
        if (this.ui.toast) this.ui.toast(ok ? "Log copied to the clipboard." : "Could not copy - select the text instead.");
        return;
      }
      if (act === "clear") {
        // Clear the VIEW. The file keeps everything; the panel says so when the
        // bridge confirms, so a user is never misled into thinking history is gone.
        this.lines = [];
        this._sigLines = "";
        this.seen.clear();
        this._paintLines();
        try {
          const r = await this.bg({ type: "terminal_clear" });
          if (this.ui.toast) this.ui.toast(r && r.local
            ? "View cleared. (The bridge is offline; the log file is untouched.)"
            : "View cleared. The log file on disk is untouched.");
        } catch {
          if (this.ui.toast) this.ui.toast("View cleared.");
        }
        return;
      }
      if (act === "follow") {
        this.autoscroll = btn.dataset.on !== "1";
        btn.dataset.on = this.autoscroll ? "1" : "0";
        if (this.autoscroll) this.body.scrollTop = this.body.scrollHeight;
        return;
      }
    }

    async _act(act) {
      if (act === "reconnect") {
        this.onNeedReconnect();
        if (this.ui.toast) this.ui.toast("Reconnecting…");
        setTimeout(() => this.refresh(), 900);
        return;
      }
      if (act === "start" || act === "stop" || act === "restart") return this._hostAct(act);
      if (act === "help") return this._help();
    }

    // The bridge answered after a start: confirm it once, quietly.
    noteStarted() { this._appendLocal("Bridge connected."); }

    // Surfaced by the worker when auto-start fires ("bridge_host_event").
    hostEvent(msg) {
      if (!msg) return;
      if (msg.event === "starting") { this._setBusy("starting"); this._appendLocal("Bridge was offline - starting it automatically…"); }
      else if (msg.event === "upgrading") { this._setBusy("starting"); this._appendLocal("Bridge v" + (msg.from || "?") + (msg.folder ? " (running from " + msg.folder + ")" : "") + " is older than the extension (v" + (msg.to || "?") + ") - replacing it…"); }
      else if (msg.event === "upgraded") { this._setBusy(null); this._appendLocal("Bridge replaced with the current version."); setTimeout(() => this.refresh(), 800); }
      else if (msg.event === "started") { this._setBusy(null); this._appendLocal("Bridge started."); setTimeout(() => this.refresh(), 600); }
      else if (msg.event === "failed") {
        this._setBusy(null);
        const r = msg.result || {};
        if (r.code === "host_missing" || r.code === "host_forbidden") { if (this.open) this._hostFailed(r, true); }
        else this._hostFailed(r, true);
      }
    }

    async _help() {
      this.showTab("log");
      this._appendLocal([
        "HOW THIS TERMINAL WORKS",
        "",
        "bridge      runtime/bridge.py - listens on ws://127.0.0.1:17613 and serves",
        "            http://127.0.0.1:17614 for diagnostics and this panel.",
        "launcher    a one-time-registered helper (Setup.bat / MacOS_Setup.command / Setup.sh).",
        "            Start / Stop / Restart here go through it. No launcher = no",
        "            buttons that work, and this panel tells you so.",
        "Start.bat   fallback: runs the same bridge in its own window (macOS:",
        "            MacOS_Start.command). This panel connects to it just the same.",
        "engines     Roblox Studio, Unity, Godot and Blender attach over MCP.",
        "            The Running tab shows which are alive right now.",
        "colours     Green = connected. Amber = process up, socket reconnecting.",
        "            Red = nothing on the port.",
        "log file    Every line is also written to runtime/logs/bridge_debug.log.",
      ].join("\n"));
    }

    // Local, clearly-marked notes so a user can tell OUR explanation apart from
    // real bridge output at a glance.
    _appendLocal(lines) {
      const text = Array.isArray(lines) ? lines.join("\n") : String(lines);
      // The same note twice in a row is noise (e.g. an auto-start retry repeating
      // "One-time setup needed"); show it once until something else is said.
      if (text === this._lastLocal && this.lines.length && this.lines[this.lines.length - 1].level === "note") return;
      this._lastLocal = text;
      this._ingest([{ seq: 0, t: "", level: "note", msg: text }]);
      this._paintLines();
    }
  }

  // ── helpers ──────────────────────────────────────────────────────────────
  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }
  function escapeAttr(s) { return escapeHtml(s); }
  function fmtUp(sec) {
    sec = Math.max(0, Math.round(Number(sec) || 0));
    if (sec < 90) return sec + "s up";
    if (sec < 5400) return Math.round(sec / 60) + "m up";
    return (sec / 3600).toFixed(1) + "h up";
  }

  async function copyText(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch {}
    // Fallback for a page that blocks the async clipboard API.
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    } catch { return false; }
  }

  window.ZSTerminal = { TerminalPanel };
})();
