// SPDX-License-Identifier: GPL-3.0-or-later
const SUPPORTED_HOSTS = ["vani.ai", "www.vani.ai","c.vani.ai", "venice.ai", "www.venice.ai", "app.clickup.com",
  "chat.deepseek.com", "deepseek.com", "chatgpt.com", "chat.openai.com", "claude.ai", "www.claude.ai", "claude.com", "www.claude.com",
  "gemini.google.com", "www.kimi.ai", "kimi.ai", "www.kimi.com", "kimi.com",
  "chat.z.ai", "chat.qwen.ai", "arena.ai", "www.meta.ai", "meta.ai", "prompt.ql.app", "superapp.chat", "www.superapp.chat",
  "notion.ai", "www.notion.ai", "notion.com", "www.notion.com", "app.notion.com", "notion.so", "www.notion.so",
];
const DEFAULT_AI_URL = "https://chat.deepseek.com/";
document.getElementById('blender-workspace').addEventListener('click',async e=>{
  const button=e.currentTarget;button.disabled=true;
  try{const result=await chrome.runtime.sendMessage({type:'ms_blender_workspace_open'});button.textContent=result?.ok?'Workspace opened':String(result?.error||'Start the bridge first.');}
  catch{button.textContent='Reload Multi-Script, then try again.';}
  finally{button.disabled=false;}
});

// The exact script list a Notion tab needs, taken from the MANIFEST rather than
// hand-copied. The repair path below exists to fix a tab that never received the
// content script; if this list drifts from content_scripts (as it did when new
// core modules were added), the injected main.js throws on load and the "repair"
// leaves the tab MORE broken than it found it - with no error the user can see.
// Falls back to the known order only if the manifest shape ever changes.
function notionInjection() {
  const fallback = {
    js: ["core/engines.js", "core/config.js", "core/parser.js", "providers/notion.js", "core/tool-routing.js", "core/pacing.js", "core/resilience.js", "core/main.js"],
    css: ["overlay.css"],
  };
  try {
    const sections = chrome.runtime.getManifest().content_scripts || [];
    const hit = sections.find((s) => (s.js || []).includes("providers/notion.js"));
    if (hit && Array.isArray(hit.js) && hit.js.length) {
      return { js: hit.js.slice(), css: (hit.css || fallback.css).slice() };
    }
  } catch {}
  return fallback;
}

document.getElementById("ver").textContent = `v${chrome.runtime.getManifest().version}`;

function render(s) {
  const dot = document.getElementById("dot"), state = document.getElementById("state");
  const tools = document.getElementById("tools"), servers = document.getElementById("servers");
  const list = s.servers || [], engines = s.engines || [];
  const connected = engines.filter((e) => e.connected === true && e.alive);
  const anyServer = list.some((x) => x.alive && (x.tools || 0) > 0);
  const ready = !!s.connected && connected.length > 0;
  const partial = !!s.connected && (anyServer || s.tools > 0);
  dot.className = "dot " + (ready ? "on" : partial ? "warn" : "");
  const names = connected.map((e) => e.id === "roblox" ? "Roblox" : e.id === "unity" ? "Unity" : e.id === "godot" ? "Godot" : e.id);
  state.textContent = !s.connected ? "Bridge offline" : ready ? `Ready · ${names.join(" + ")}` : partial ? "Bridge online · connect an editor" : "MCP servers offline";
  tools.textContent = s.connected ? `${s.tools || 0} tools available` : "Run bridge.py";
  servers.textContent = s.connected ? list.map((x) => {
    const e = engines.find((v) => v.id === x.id);
    const suffix = e && e.connected === true ? "connected" : e && e.connected === false ? "editor offline" : x.alive ? "server ready" : "down";
    return `${x.alive ? "●" : "○"} ${x.id} · ${x.tools || 0} tools · ${suffix}`;
  }).join("\n") : "";
}

function refresh() {
  chrome.runtime.sendMessage({ type: "status" }, (s) => s && render(s));
}

document.getElementById("reconnect").addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "reconnect" }, () => setTimeout(refresh, 600));
});
document.getElementById("restart").addEventListener("click", (e) => {
  e.target.textContent = "Restarting…";
  chrome.runtime.sendMessage({ type: "restart_mcp" }, () => {
    e.target.textContent = "⟳ Restart MCP servers";
    setTimeout(refresh, 600);
  });
});
document.getElementById("settings").addEventListener("click", () => {
  // Uses chrome.tabs and tries the in-page
  // panel on an already-open supported AI tab first, so opening it doesn't
  // require a conversation to already be started there.
  chrome.tabs.query({}, (tabs) => {
    const active = tabs.find((t) => t.active && t.url && SUPPORTED_HOSTS.some((h) => t.url.includes(h)));
    const anySupported = active || tabs.find((t) => t.url && SUPPORTED_HOSTS.some((h) => t.url.includes(h)));
    if (anySupported) {
      chrome.tabs.sendMessage(anySupported.id, { type: "zs-open-menu" }, async () => {
        // A Notion SPA tab may have survived an extension update or redirected
        // notion.ai -> notion.com before Chrome registered the content script.
        // Repair that exact missing-injection case without making the user hunt
        // through chrome://extensions. Existing scripts answer normally and are
        // never injected twice.
        if (!chrome.runtime.lastError) return;
        let host = "";
        try { host = new URL(anySupported.url).hostname; } catch {}
        if (!/(^|\.)notion\.(ai|so|com)$/.test(host) && host !== "app.notion.com") return;
        try {
          const inject = notionInjection();
          if (inject.css.length) await chrome.scripting.insertCSS({ target:{ tabId:anySupported.id }, files:inject.css });
          await chrome.scripting.executeScript({ target:{ tabId:anySupported.id }, files:inject.js });
          chrome.tabs.sendMessage(anySupported.id, { type:"zs-open-menu" });
        } catch (e) { console.warn("Multi-Script Notion repair failed", e); }
      });
      chrome.tabs.update(anySupported.id, { active: true });
    } else {
      chrome.tabs.create({ url: DEFAULT_AI_URL });
    }
  });
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "zs-status") render(msg);
});
refresh();
setInterval(refresh, 2000);
