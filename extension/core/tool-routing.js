// SPDX-License-Identifier: GPL-3.0-or-later
// Pure exact-server tool-name routing shared by every provider.
// eslint-disable-next-line no-unused-vars
const ZSToolRouting = (() => {
  "use strict";
  const bare = (name) => String(name || "").split("/").pop().split(".").pop();
  function resolve(name, serverHint, tools) {
    const list = Array.isArray(tools) ? tools : [];
    const exact = list.find((t) => t && t.name === name);
    const matches = list.filter((t) => t && bare(t.name) === bare(name));
    if (serverHint) {
      const selected = matches.find((t) => t.server === serverHint);
      if (selected) return { ok: true, name: selected.name, server: selected.server, exact: false };
      return { ok: false, reason: "server", servers: [...new Set(matches.map((t) => t.server).filter(Boolean))] };
    }
    if (exact) return { ok: true, name: exact.name, server: exact.server || null, exact: true };
    if (matches.length === 1) return { ok: true, name: matches[0].name, server: matches[0].server || null, exact: false };
    if (matches.length > 1) return { ok: false, reason: "ambiguous", servers: [...new Set(matches.map((t) => t.server).filter(Boolean))] };
    return { ok: false, reason: "unknown", servers: [] };
  }
  const ENGINE_IDS = new Set(["roblox", "unity", "godot", "blender"]);
  const ENGINE_BRIDGES = new Set(["ms_call_engine_tool", "ms_parallel_tools", "ms_native_read", "ms_native_write", "ms_native_verify"]);
  function isEngineExecution(name, args, tools) {
    const n = bare(name);
    const a = args && typeof args === "object" ? args : {};
    const hint = String(a._server || "").trim().toLowerCase();
    if (hint === "roblox-companion" || ENGINE_IDS.has(hint)) return true;
    const route = resolve(name, hint, tools);
    if (route.ok && (route.server === "roblox-companion" || ENGINE_IDS.has(String(route.server || "").toLowerCase()))) return true;
    if (/^msrb_/.test(n) || /^ms_(roblox|unity|godot|blender)_/.test(n)) return true;
    if (ENGINE_BRIDGES.has(n)) {
      const target = String(a.server || a.engine || "").trim().toLowerCase();
      return !target || ENGINE_IDS.has(target);
    }
    return false;
  }
  return { bare, resolve, isEngineExecution };
})();
