// SPDX-License-Identifier: GPL-3.0-or-later
// core/main.js - the provider-agnostic agentic loop, UI and session state.
// Drives any AI chat site through the ZSProvider interface (providers/*.js):
// waits for the model's reply, parses Multi-Script commands (ZSParse), asks the
// background worker to execute them on the Roblox MCP bridge, and feeds the
// result back. Camouflages the system prompt ("Starting Up") and tool JSON
// behind animated chips, masks injected input, and exposes a Stop button.
// The model ALWAYS receives an output.
//
// This file must NEVER touch the host site's DOM directly - everything
// site-specific goes through P (the provider). Our OWN UI (panel, chips,
// banners…) is plain DOM we create ourselves and is allowed here.

(() => {
  "use strict";
  const P = ZSProvider;
  const T = P.timings;
  // Hidden tabs clamp page timers (1/s, then 1/min after ~5 min "intensive throttling"). The
  // agent keeps running while the browser is covered by Roblox Studio, so long waits in a hidden
  // tab are timed by the extension worker instead; its reply is a message, which is not throttled.
  const sleep = (ms) => new Promise((r) => {
    if (document.hidden && ms >= 150) {
      let settled = false;
      const fin = () => { if (!settled) { settled = true; r(); } };
      try { chrome.runtime.sendMessage({ type: "ms_sleep", ms: Math.min(ms, 60000) }, () => { void chrome.runtime.lastError; fin(); }); } catch { /* fall back below */ }
      setTimeout(fin, ms + 2500);   // worker unavailable: the ordinary (throttled) timer still ends the wait
      return;
    }
    setTimeout(r, ms);
  });
  // "Keep running when the browser is covered or in the background" (Agent settings, ON by default).
  // Chrome/Edge report a tab as hidden when ANOTHER window (Roblox Studio...) covers the browser, which
  // used to freeze the loop on "Paused" until the user came back. Only an explicit OFF restores that.
  let keepRunningHidden = true;
  try { chrome.storage.local.get("msKeepRunningHidden", (r) => { if (r && r.msKeepRunningHidden === false) keepRunningHidden = false; }); } catch {}
  const pageHidden = () => document.hidden && !keepRunningHidden;
  const log = (...a) => console.log("[zeroscript]", ...a);

  // Reply pacing limits extension traffic. Provider minimums and shared-tab
  // budgets remain enforced independently of user pacing preferences. Delays
  // cannot establish why an account was restricted or guarantee account access.
  let paceSettings = ZSPace.DEFAULT_SETTINGS;
  let resilienceSettings = ZSResilience.DEFAULT_SETTINGS;
  let autonomyLevel = "guided";
  // How the run behaves when a provider puts a bot-check in the way. This is an
  // ASSISTANT, never a bypass: it pauses, gets our own overlays out of the way,
  // can click the provider's own widget once, alerts loudly for an unattended
  // run, and slows subsequent sends so the check stops recurring. See
  // core/verification.js for the full reasoning and the hard limits.
  let verificationSettings = ZSVerify.DEFAULT_SETTINGS;
  // Live slowdown state (floorMs grows with each challenge, decays when clean)
  // and the challenge counter live on A - declared in the A literal below.
  // They must NOT be assigned here: `const A` is still in its temporal dead
  // zone at this point, so touching A.anything throws ReferenceError and the
  // whole content script dies before any UI can mount (6.17.3 regression).
  // Live pacing bookkeeping (A.sendIndex / A.lastSendAt / A.lastErrorAt live on A).
  const paceProfile = () => ZSPace.profileFor(paceSettings, P.id);
  const rlevel = () => P.recoveryLevel || ZSResilience.levelFor(resilienceSettings, P.id);
  const rbudgets = () => ZSResilience.budgets(rlevel());
  const vmode = () => ZSVerify.modeFor(verificationSettings, P.id);
  const getPaceSettings = () => paceSettings;
  const getResilienceSettings = () => resilienceSettings;
  const getVerificationSettings = () => verificationSettings;
  const getAutonomyLevel = () => autonomyLevel;
  function setPaceSettings(patch) {
    paceSettings = ZSPace.sanitize({ ...paceSettings, ...(patch || {}) });
    try { chrome.storage.local.set({ msPacingSettings: paceSettings }); } catch {}
    return paceSettings;
  }
  function setResilienceSettings(patch) {
    resilienceSettings = ZSResilience.sanitize({ ...resilienceSettings, ...(patch || {}) });
    try { chrome.storage.local.set({ msResilienceSettings: resilienceSettings }); } catch {}
    return resilienceSettings;
  }
  function setVerificationSettings(patch) {
    verificationSettings = ZSVerify.sanitize({ ...verificationSettings, ...(patch || {}) });
    try { chrome.storage.local.set({ msVerificationSettings: verificationSettings }); } catch {}
    return verificationSettings;
  }
  function setAutonomyLevel(level) {
    autonomyLevel = ZS.sanitizeAutonomy ? ZS.sanitizeAutonomy(level) : (level === "oneShot" ? "oneShot" : "guided");
    studioSettingsDirty = true;
    try { chrome.storage.local.set({ zsAutonomyLevel: autonomyLevel }); } catch {}
    return autonomyLevel;
  }
  // ── Prompt enhancer + media relay settings ───────────────────────────────
  // Both default OFF/ON safely: the enhancer rewrites the user's own words, so it
  // is opt-in; the relay only acts when the user drops a file, so it is on.
  let enhanceSettings = ZSEnhance.sanitize(null);
  const getEnhanceSettings = () => enhanceSettings;
  function setEnhanceSettings(patch) {
    enhanceSettings = ZSEnhance.sanitize({ ...enhanceSettings, ...(patch || {}) });
    try { chrome.storage.local.set({ msEnhanceSettings: enhanceSettings }); } catch {}
    return enhanceSettings;
  }
  // Provider-neutral execution effort. This is an instruction-layer harness,
  // not a hidden attempt to click a site's model/thinking controls. Every
  // provider receives the same semantics; Notion gets the same block inside its
  // prompt-only startup harness.
  const EXECUTION_EFFORTS = {
    adaptive: { label: "Adaptive", hint: "Match effort to task risk and complexity.", prompt: "Choose the lightest approach that can complete the task correctly. Escalate depth for ambiguity, broad changes, security, migrations, performance work, or failed verification." },
    quick: { label: "Quick", hint: "Fast path for small, reversible requests.", prompt: "Use a compact execution path. Avoid optional exploration, but still inspect before editing and verify the requested outcome." },
    standard: { label: "Standard", hint: "Balanced implementation and verification.", prompt: "Use normal implementation depth: inspect context, execute the coherent change, and run one meaningful verification pass." },
    deep: { label: "Deep", hint: "Broader reasoning, edge cases, and stronger evidence.", prompt: "Work deeply: inspect dependencies, consider important edge cases and integration effects, test the real result, and revise defects before finishing." },
    ultra: { label: "Ultra", hint: "Reference research, specialist methods, integrated builds and visual evidence.", prompt: "Use the full available tool catalogue relevant to this request. Research primary references and visual styles before a complex creative build; load the relevant skills and exact tool schemas, produce editable source assets, integrate into the real project, playtest or run the build, inspect captures/logs, then repair verified defects and recheck the affected result. Additional Critic passes follow the separate Critic setting. Use ms_screen_record for motion checks when available. Stop a repeated failing approach and investigate. Never claim research, imports or tests you did not perform. Do not expose private chain-of-thought; provide brief decisions and evidence." },
    maximum: { label: "Maximum", hint: "Highest practical rigor for complex builds.", prompt: "Use maximum practical rigor: map dependencies, coordinate relevant specialist skills and native tools, cover failure/platform/performance concerns, run iterative verification, and finish only with concrete read-back evidence." },
  };
  const EFFORT_ORDER = ["adaptive", "quick", "standard", "deep", "maximum", "ultra"];
  function sanitizeExecutionEffort(value) { return Object.prototype.hasOwnProperty.call(EXECUTION_EFFORTS,value) ? value : "adaptive"; }
  let executionEffort = "adaptive";
  let studioSettingsDirty = false;
  let criticSettings = typeof MSStudio !== "undefined" ? MSStudio.sanitizeCritic(null) : {enabled:true,passes:3};
  function setCriticSettings(patch) {
    criticSettings = MSStudio.sanitizeCritic({...criticSettings,...patch});
    studioSettingsDirty = true;
    try { chrome.storage.local.set({msCriticSettings:criticSettings}); } catch {}
    return criticSettings;
  }
  let taskLedger=null,runMonitor=null;
  try{taskLedger=typeof MSProgress!=='undefined'?MSProgress.restore(JSON.parse(sessionStorage.getItem('msTaskLedger')||'null')):null;}catch{}
  const progressContext=()=>P.id+'|'+(P.conversationKey()||location.href)+'|'+(A.software?softwareSettings.root:'chat');
  function readTaskProgress(){
    // A provider can assign the real conversation URL only after the first send.
    // Adopt that one transition using the same live-loop binding as session sync.
    if(taskLedger?.awaitingConversation&&(A.running||A.injecting)&&P.conversationKey()&&!P.chatIsEmpty()&&(!A.loopKey||A.loopKey===P.conversationKey())){taskLedger.context=progressContext();taskLedger.awaitingConversation=false;try{sessionStorage.setItem('msTaskLedger',JSON.stringify(taskLedger));}catch{}}
    return taskLedger?.context===progressContext()?taskLedger:null;
  }
  let savedTaskProgress='';
  function saveTaskProgress(){try{const value=JSON.stringify(taskLedger);if(value!==savedTaskProgress){sessionStorage.setItem('msTaskLedger',value);savedTaskProgress=value;}}catch{}runMonitor?.paint();}
  function beginTaskProgress(title){if(typeof MSProgress==='undefined')return;taskLedger=MSProgress.create(title,progressContext(),crypto.randomUUID());taskLedger.awaitingConversation=!P.conversationKey();saveTaskProgress();}
  function observeTaskProgress(event){const run=readTaskProgress();if(run){MSProgress.observe(run,event);saveTaskProgress();}}
  function taskProgressPrompt(){const run=readTaskProgress();return run&&typeof MSProgress!=='undefined'?MSProgress.prompt(run):'';}
  function taskPromptAddon(request) {
    const addon = typeof MSStudio !== "undefined" ? MSStudio.taskAddon(request, executionEffort, criticSettings, {engines:A.software||A.chatOnly?["workspace"]:connectedEngineIds(),skills:customSkills.length?activeCustomSkills():undefined,tools:sessionExecutionTools()}) : "";
    if (ultraStartPending && addon.includes("[ULTRA · STARTUP]")) ultraStartPending = false; // sent once per selection
    return [addon,taskProgressPrompt()].filter(Boolean).join("\n\n");
  }
  function skillScopeKey() { return A.software&&softwareSettings.root ? "workspace:"+softwareSettings.root.replace(/\\/g,"/").replace(/\/$/,"") : "chat:"+P.id+":"+(P.conversationKey()||location.href); }
  function activeCustomSkills() { return MSStudio.selectSkills(customSkills,{scope:skillScopeKey(),engines:A.software||A.chatOnly?["workspace"]:connectedEngineIds()}); }
  let customSkills = [];
  try { chrome.storage.local.get("msCustomSkills", r => { customSkills = Array.isArray(r.msCustomSkills) ? r.msCustomSkills.slice(0, 12) : []; }); } catch {}
  // ── Notion trial/credit estimator state (see core/notion-usage.js) ─────────
  // Lives at the top level because the send loop (counts prompts) and the UI
  // (shows the estimate) are different closures. Only Notion uses it.
  const NU = typeof ZSNotionUsage !== "undefined" ? ZSNotionUsage : null;
  let notionUsage = NU ? NU.defaults() : null;
  let onNotionUsageChange = null;
  let notionProbing = false; // true while we open Notion's own model picker on purpose
  function saveNotionUsage(next) {
    if (!NU) return;
    if (next) notionUsage = NU.sanitize(next);
    try { chrome.storage.local.set({ zsNotionUsage: notionUsage }); } catch {}
    try { if (onNotionUsageChange) onNotionUsageChange(); } catch {}
  }
  // One call per message actually sent to Notion (user prompt or tool-result turn).
  function noteNotionPrompt() {
    if (!NU || !notionUsage || ZSProvider.id !== "notion") return;
    saveNotionUsage(NU.recordPrompt(notionUsage, {}));
  }
  if (NU && ZSProvider.id === "notion") {
    try { chrome.storage.local.get("zsNotionUsage", (r) => { if (r && r.zsNotionUsage) { notionUsage = NU.sanitize(r.zsNotionUsage); if (onNotionUsageChange) onNotionUsageChange(); } }); } catch {}
  }
  // A single state-to-view path covers hydration, slider input, reset and import.
  // Global selection is required because some providers portal the bar outside root.
  function syncExecutionEffortUI() {
    try {
      document.documentElement.setAttribute("data-ms-effort", executionEffort);
      const active=executionEffort==="ultra";
      const label=document.getElementById("ms-effort-label");
      if(label){label.textContent=EXECUTION_EFFORTS[executionEffort].label;label.classList.toggle("ms-ultra-title",active);}
      const slider=document.getElementById("ms-effort-slider");
      if(slider){slider.value=String(EFFORT_ORDER.indexOf(executionEffort));slider.style.setProperty('--ms-effort-fill',String(EFFORT_ORDER.indexOf(executionEffort)*20)+'%');slider.setAttribute("aria-valuetext",EXECUTION_EFFORTS[executionEffort].label);}
      const hint=document.getElementById("ms-effort-hint");if(hint)hint.textContent=EXECUTION_EFFORTS[executionEffort].hint;
      const panel=document.getElementById("ms-ultra-summary");if(panel)panel.hidden=!active;
      const indicator=document.getElementById("ms-effort-indicator");if(indicator){indicator.hidden=false;indicator.textContent=EXECUTION_EFFORTS[executionEffort].label;indicator.classList.toggle('ms-ultra-title',active);indicator.setAttribute('aria-label',EXECUTION_EFFORTS[executionEffort].label+' execution effort');indicator.title=EXECUTION_EFFORTS[executionEffort].hint;}
      document.querySelectorAll(".ms-effort-ticks [data-effort-tick]").forEach(t=>{if(t.dataset.effortTick===executionEffort)t.setAttribute("aria-current","true");else t.removeAttribute("aria-current");});
    } catch {} // A disconnected provider document must not break saving settings.
  }
  let ultraStartPending = false;
  function setExecutionEffort(value) {
    const wasUltra = executionEffort === "ultra";
    executionEffort = sanitizeExecutionEffort(value);
    if (executionEffort === "ultra" && !wasUltra) ultraStartPending = true; else if (executionEffort !== "ultra") ultraStartPending = false;
    syncExecutionEffortUI();
    if(A.executionTrace&&typeof MSExecution!=='undefined'){const next=MSExecution.create(A.lastUserText,executionEffort,sessionExecutionTools(),{engineFree:A.chatOnly&&!A.software,workspace:A.software});A.executionTrace.effort=executionEffort;A.executionTrace.requireResearch=next.requireResearch;A.executionTrace.requireSkill=next.requireSkill;A.executionTrace.names=next.names;}
    studioSettingsDirty = true;
    try { chrome.storage.local.set({ msExecutionEffort: executionEffort }); } catch {}
    return executionEffort;
  }
  function executionEffortPrompt() {
    const e = EXECUTION_EFFORTS[executionEffort] || EXECUTION_EFFORTS.adaptive;
    return `━━━ EXECUTION EFFORT · ${e.label.toUpperCase()} ━━━\n${e.prompt}\nLatest user setting: EFFORT=${executionEffort}. This replaces earlier effort instructions; when not ultra, stop applying previous Ultra methods and research requirements.\nThis changes depth, not honesty, safety, tool availability, or the requirement to complete the real deliverable.`;
  }
  function blenderWorkspaceInstructions(){
    const workspace=(A.bridge?.engines||[]).find(e=>e.id==='blender'&&e.backend==='headless-workspace'&&e.enabled!==false&&!A.disabledEngines.has('blender'));
    if(!workspace||A.chatOnly&&!(A.software&&softwareSettings.addons?.engines))return '';
    if(workspace.connected!==true||workspace.alive===false)return '[BLENDER WORKSPACE]\nThe selected headless Blender project '+JSON.stringify(workspace.workspaceProject)+' is stopped or not responding. Its saved model remains in Blender Workspace. Resume or reopen that same project there, then recheck its status. Do not switch to desktop Blender or ask for a desktop MCP add-on; the selected AI target has not changed. Do not claim a working connection without a real successful response.';
    return '[BLENDER WORKSPACE]\nReal headless Blender is connected to project '+JSON.stringify(workspace.workspaceProject)+'. Use ms_blender_workspace status/snapshot/execute/render/export or existing ms_blender_* tools with target=workspace and workspace_project=current id. The .blend auto-saves; Three.js previews exported glTF animations. Use a real Blender render for exact material/effect evidence. Do not ask for a desktop Blender window or MCP add-on. Never switch to connected desktop Blender unless the user requests it. For a model or animation request, keep the saved scene focused on the requested asset. Do not add backdrops, studio floors, camera rigs or light sets, or substitute a render for the model, unless requested. Use scene inspection and the material viewport first; optional verification renders must not add permanent staging objects. For game assets, keep the connected game engine as the final destination: use action=handoff with project=current id, engine=roblox|unity|godot and a name. Unity/Godot require the explicit project_path first; assets are copied to their project, not marked imported/verified. Roblox receives an exported GLB for Studio Importer. After handoff, use the target engine tools to inspect the imported geometry, rig, materials, collisions and animation; only then claim in-engine success.';
  }
  async function prepareBlenderCompanion(alive){
    const engines=connectedEngineIds().filter(id=>['roblox','unity','godot'].includes(id));
    if(!A.bridge?.bridgeCapabilities?.blender_companion)return true;
    const setup=await bg({type:'ms_blender_companion',op:'ensure',engines});
    if(!alive()||A.stop)return false;
    if(!setup?.ok)throw Error(setup?.error||'The Blender companion could not be prepared.');
    if(!setup.required)return true;
    A.startPhase=setup.engines.every(e=>e==='blender')?'Starting Blender Workspace':'Starting Blender alongside '+setup.engines.join(' + ');ui.setStarting();
    while(alive()&&!A.stop){
      const status=await bg({type:'ms_blender_companion',op:'status'});
      if(!alive()||A.stop)return false;
      if(!status?.ok||status.job?.state==='error')throw Error(status?.error||status.job?.error||'Blender did not become ready. Open its workspace to retry.');
      if(status.running&&status.verified&&status.aiTarget&&status.job?.state!=='running'){
        ui.setStatus({...A.bridge,engines:status.engines,servers:status.servers||A.bridge.servers});return true;
      }
      A.startPhase=status.message||'Preparing Blender Workspace';ui.setStarting();await sleep(750);
    }
    return false;
  }
  function activeStudioInstructions(includeUltraMethods=true) {
    return "[MULTI-SCRIPT ACTIVE USER SETTINGS]\n" + executionEffortPrompt() + "\n" +
      (ZS.autonomyPrompt ? ZS.autonomyPrompt(autonomyLevel, P.displayName || P.id) : "") + "\n" +
      `Critic review is ${criticSettings.enabled ? "enabled: inspect the actual deliverable, repair verified defects and retest, up to " + criticSettings.passes + " passes" : "disabled; do not add Critic review passes"}. These are the latest user settings.` + "\n" + (typeof MSStudio!=="undefined"?MSStudio.installedSkillsPrompt(activeCustomSkills()):"") +
      (includeUltraMethods&&executionEffort==="ultra"&&typeof MSStudio!=="undefined"?"\n"+MSStudio.ultraMethodsPrompt(A.lastUserText,{engines:A.software||A.chatOnly?["workspace"]:connectedEngineIds()}):"")+"\n"+blenderWorkspaceInstructions();
  }
  let mediaSettings = ZSMediaRelay.sanitizeSettings(null);
  const getMediaSettings = () => mediaSettings;
  function setMediaSettings(patch) {
    mediaSettings = ZSMediaRelay.sanitizeSettings({ ...mediaSettings, ...(patch || {}) });
    try { chrome.storage.local.set({ msMediaSettings: mediaSettings }); } catch {}
    return mediaSettings;
  }
  // The last relay outcome, so the panel can tell the truth about what happened
  // without re-uploading anything.
  let lastRelay = null;
  const getLastRelay = () => lastRelay;
  function setLastRelay(v) { lastRelay = v || null; return lastRelay; }

  // ── Surface vision settings ────────────────────────────────────────────
  // Four independent grants, all defaulting on: seeing tabs, seeing windows,
  // reading a tab's text, and typing into a tab. Splitting read from write means
  // a cautious user can let the agent LOOK at everything while forbidding it
  // from touching anything. sanitize() coerces every field, so a corrupt or
  // partial stored object can never leave a malformed setting in place.
  const SURFACE_DEFAULTS = { tabs: true, windows: true, allowRead: true, allowType: true };
  function sanitizeSurfaceSettings(raw) {
    const r = raw && typeof raw === "object" ? raw : {};
    const out = {};
    for (const k of Object.keys(SURFACE_DEFAULTS)) out[k] = r[k] === undefined ? SURFACE_DEFAULTS[k] : !!r[k];
    return out;
  }
  let surfaceSettings = sanitizeSurfaceSettings(null);
  const getSurfaceSettings = () => surfaceSettings;
  function setSurfaceSettings(patch) {
    surfaceSettings = sanitizeSurfaceSettings({ ...surfaceSettings, ...(patch || {}) });
    try { chrome.storage.local.set({ msSurfaceSettings: surfaceSettings }); } catch {}
    return surfaceSettings;
  }

  // ── Graduated trust ─────────────────────────────────────────────────────
  // One ordered choice (sandbox < ask < full) replaces a pile of independent
  // switches. ZSTrust owns the semantics - this is only the storage edge, and it
  // deliberately does not re-implement sanitize(): a corrupt stored value must
  // fall back to the MOST restrictive level, and that rule lives in one place.
  let trustSettings = ZSTrust.sanitize(null);
  const getTrustSettings = () => trustSettings;
  function setTrustSettings(patch) {
    const next = { ...trustSettings, ...(patch || {}) };
    // Switching to the widest level requires the user to acknowledge it once.
    if (next.level === "full" && (patch || {}).acknowledgeFull === undefined && trustSettings.level !== "full") {
      next.acknowledgeFull = true;
    }
    trustSettings = ZSTrust.sanitize(next);
    try { chrome.storage.local.set({ msTrustSettings: trustSettings }); } catch {}
    return trustSettings;
  }
  // The single gate every consequential action goes through. Returns the policy
  // decision so a caller can report a refusal honestly instead of throwing.
  const canDo = (capability) => ZSTrust.can(trustSettings, capability);
  const trustSummary = () => ZSTrust.describe(trustSettings);
  try {
    chrome.storage.local.get(["msPacingSettings", "msResilienceSettings", "zsAutonomyLevel", "msVerificationSettings", "msEnhanceSettings", "msMediaSettings", "msSurfaceSettings", "msTrustSettings", "msExecutionEffort", "msRateFloor", "msCriticSettings"], (r) => {
      if (r && r.msRateFloor && typeof r.msRateFloor === "object") { const v = Number(r.msRateFloor[P.id]); if (Number.isFinite(v) && v > 0) A.rateFloorMs = Math.min(90000, v); }
      if (r && r.msPacingSettings) paceSettings = ZSPace.sanitize(r.msPacingSettings);
      if (r && r.msResilienceSettings) resilienceSettings = ZSResilience.sanitize(r.msResilienceSettings);
      if (r && r.msVerificationSettings) verificationSettings = ZSVerify.sanitize(r.msVerificationSettings);
      if (r && r.zsAutonomyLevel) autonomyLevel = ZS.sanitizeAutonomy ? ZS.sanitizeAutonomy(r.zsAutonomyLevel) : (r.zsAutonomyLevel === "oneShot" ? "oneShot" : "guided");
      if (r && r.msEnhanceSettings) enhanceSettings = ZSEnhance.sanitize(r.msEnhanceSettings);
      if (r && r.msMediaSettings) mediaSettings = ZSMediaRelay.sanitizeSettings(r.msMediaSettings);
      if (r && r.msSurfaceSettings) surfaceSettings = sanitizeSurfaceSettings(r.msSurfaceSettings);
      if (r && r.msTrustSettings) trustSettings = ZSTrust.sanitize(r.msTrustSettings);
      if (r && r.msExecutionEffort) { executionEffort = sanitizeExecutionEffort(r.msExecutionEffort); if (executionEffort === "ultra") ultraStartPending = true; }
      syncExecutionEffortUI();
      if (r && r.msCriticSettings && typeof MSStudio !== "undefined") criticSettings = MSStudio.sanitizeCritic(r.msCriticSettings);
      // Defensive: this runs asynchronously, so never let a diagnostic failure
      // escape into an unhandled rejection if the module is torn down early.
      try { diag("pacing.loaded", { pace: ZSPace.describe(paceSettings, P.id), recovery: ZSResilience.describe(resilienceSettings, P.id), autonomy: autonomyLevel, verification: ZSVerify.describe(verificationSettings, P.id), enhancer: ZSEnhance.describe(enhanceSettings), trust: ZSTrust.describe(trustSettings) }); } catch {}
    });
  } catch {}

  // Sleep that a user Stop can interrupt, so a long paced wait never delays the
  // Stop button. Returns false if we were stopped mid-wait.
  async function paceSleep(ms) {
    let left = Math.max(0, Math.round(ms || 0));
    while (left > 0) {
      if (A.stop) return false;
      const slice = Math.min(400, left);
      await sleep(slice);
      left -= slice;
    }
    return !A.stop;
  }

  // Wait out the paced interval before a send. `reason` is diagnostic only.
  async function paceBeforeSend(reason) {
    const now = Date.now();
    const plan = ZSPace.computeDelay(paceSettings, P.id, {
      sendIndex: A.sendIndex || 0,
      now,
      lastSendAt: A.lastSendAt || 0,
      lastErrorAt: A.lastErrorAt || 0,
    });
    // Adaptive verification slowdown: a challenge is the provider asking for
    // less traffic, so it raises a FLOOR on the gap. This is added on top of the
    // normal pacing rather than replacing it, so a fast user profile still gets
    // slowed down after a check, and recovers as the stretch stays clean.
    const vm = vmode();
    let verifyMs = 0;
    if (vm.adaptive) {
      verifyMs = ZSVerify.extraDelayMs(A.verifyState, now, verificationSettings);
      // A clean interval decays the floor back toward zero.
      if (!verifyMs) A.verifyState = ZSVerify.noteClean(A.verifyState, now);
    }
    // Site-refusal floor (6.28.3): after a "Messages too frequent" / 429 the gap
    // between two sends can never be shorter than the adaptive per-site floor,
    // and a provider may declare its own minimum (P.minSendGapMs). Applied even
    // when pacing is Off - it only ever waits out a limit the site itself set.
    const floorMs = Math.max(Number(A.rateFloorMs) || 0, Number(P.minSendGapMs) || 0, 900);
    const floorWait = A.lastSendAt ? Math.max(0, floorMs - (now - A.lastSendAt)) : 0;
    const totalMs = Math.max(plan.delayMs, verifyMs, floorWait);
    if (totalMs <= 0) return true;
    // Surface the wait so the user can SEE the pacing working (and so a long
    // long-pause never reads as a hang). A.pacingUntil drives the bar's text.
    A.pacingUntil = Date.now() + totalMs;
    A.pacingReason = floorWait >= totalMs && floorWait > plan.delayMs ? "site-rate-floor" : verifyMs > plan.delayMs ? "verification-slowdown" : plan.reason;
    diag("pace.wait", { ms: totalMs, reason: A.pacingReason, longPause: plan.longPause, cooldownMs: plan.cooldownMs, sendIndex: A.sendIndex || 0, verifyMs, why: reason });
    try {
      const ok = await paceSleep(totalMs);
      return ok;
    } finally {
      A.pacingUntil = 0;
    }
  }
  // The pacing engine's own preview line, shown in the menu.
  const paceDescription = () => ZSPace.describe(paceSettings, P.id);
  async function acquireProviderSend() {
    const owner=Date.now().toString(36)+"-"+Math.random().toString(36).slice(2);
    while (!A.stop) {
      const blocked=P.sendBlockNotice?.();
      if(blocked){await bg({type:"ms_provider_pacing",action:"notice",provider:P.id,owner,kind:blocked.kind,reason:blocked.text});A.lastSendError=blocked.text;ui.banner("warn",P.displayName+" sends paused",blocked.text);return false;}
      const r=await bg({type:"ms_provider_pacing",action:"acquire",provider:P.id,owner,gapMs:Math.max(5000,Number(P.minSendGapMs)||0,paceProfile().min||0)});
      // An old worker may be present briefly during an extension upgrade.
      if (!r || typeof r.granted!=="boolean" || (P.requireSharedPacing&&r.policyVersion!==2)) { diag("pace.sharedUnavailable");if(P.requireSharedPacing){A.lastSendError="Shared pacing is unavailable. Reload the extension and this tab before sending.";ui.banner("warn","Sending paused",A.lastSendError);return false;}return null; }
      if (r.granted) return owner;
      if (r.blocked) {
        A.lastSendError=r.reason||"Provider usage limit";A.sendBannerShown=true;
        ui.banner("warn","Provider sends are paused",A.lastSendError+". Check the provider's notice; submit a new prompt yourself after the limit is resolved.");
        return false;
      }
      const wait=Math.max(250,Number(r.waitMs)||1000);
      A.pacingUntil=Date.now()+wait;A.pacingReason="shared-provider-cooldown";
      try { if (!(await paceSleep(wait))) return false; } finally {A.pacingUntil=0;}
    }
    return false;
  }
  async function releaseProviderSend(owner,kind="",success=false) {
    if (!owner)return;
    const notice=siteNoticeHit()||P.sendBlockNotice?.();
    await bg({type:"ms_provider_pacing",action:"release",provider:P.id,owner,kind:(notice&&notice.kind)||kind||"",reason:notice&&notice.text,success,retryAfterMs:ZSResilience.retryAfterMs?ZSResilience.retryAfterMs(notice&&notice.text):0});
  }

  // ── Diagnostics ───────────────────────────────────────────────────────────
  // Persistent, lightweight breadcrumb log of the agentic loop's key decisions
  // (sends, response kinds, tool start/end, resumes, stops). Read back from the
  // console (filter "[zs-diag]") or window.__zsDiag (also mirrored onto a hidden
  // DOM node for a main-world inspector). Each entry carries a turn snapshot.
  const ZS_DIAG_MAX = 300;
  const _diag = [];
  function diag(event, data) {
    // diag() is handed to P.init() at load, BEFORE `const A` below is initialised.
    // Claude's init() logs the detected model straight away, which dereferenced A
    // in its temporal dead zone and aborted the whole content script on claude.ai
    // (no bar, no menu). Read A defensively so an early diag can never crash the load.
    let running = false, snapBase = {}, gen = false;
    try { running = A.running; } catch {}
    try { snapBase = P.snapshot(); gen = P.isGenerating(); } catch {}
    const snap = { ...snapBase, gen, run: running };
    const e = { t: Date.now(), iso: new Date().toISOString().slice(11, 23), event,
                data: data || null, snap };
    _diag.push(e);
    if (_diag.length > ZS_DIAG_MAX) _diag.shift();
    try { console.log("[zs-diag]", e.iso, event, JSON.stringify({ ...data, ...snap })); } catch {}
    try {
      let n = document.getElementById("zs-diag-log");
      if (!n) { n = document.createElement("script"); n.type = "application/json"; n.id = "zs-diag-log"; (document.body || document.documentElement).appendChild(n); }
      n.textContent = JSON.stringify(_diag);
    } catch {}
    try { window.__zsDiag = _diag; } catch {}
  }
  P.init({ diag });

  // ── [TRACE] Main-thread stall detector ─────────────────────────────────────
  // The reported bug ("tools spin 15-20s, the chip timer stops rising") can only
  // be a SYNCHRONOUS block of the page's main thread: an async bridge/network wait
  // yields, so the 200ms UI interval (and its chip timer) would keep ticking. This
  // fires every 250ms and, whenever the ACTUAL gap since the last tick is far more
  // than expected, logs the stall. A `stall.detected` with a big `ms` right when
  // the user sees the freeze = the smoking gun; correlate its timestamp with the
  // surrounding diag events (esp. code.snapAll / dom.read.slow) to see WHAT ran.
  {
    const EXPECT = 250, STALL = 800; // only log gaps beyond this many ms
    let _lastTick = Date.now();
    setInterval(() => {
      const now = Date.now();
      const gap = now - _lastTick;
      _lastTick = now;
      if (gap > STALL) {
        diag("stall.detected", { ms: gap, overBy: gap - EXPECT,
          toolRunning: A.toolRunning, running: A.running, injecting: A.injecting });
      }
    }, EXPECT);
  }

  // GitHub releases page - where users download the Bridge + Setup.bat.
  const GITHUB_URL = "https://github.com/sebattfg/ZeroScript-Free";
  // Shown in the panel instead of a static "Free" label, so a user's screenshot
  // alone tells us which build they're on for debugging. Pulled from
  // manifest.json (single source of truth) rather than duplicated here.
  const EXT_VERSION = chrome.runtime.getManifest().version;
  // YouTube tutorial - how to set up the Bridge.
  const VIDEO_URL = "https://youtu.be/kPKiZLZ9_Ps";
  // AI chat sites Multi-Script works on. Keep in sync with manifest.json
  // content_scripts and background.js PROVIDER_URLS when adding a provider.
  const AI_SITES = [
    { name: "DeepSeek", url: "https://chat.deepseek.com/" },
    { name: "ChatGPT", url: "https://chatgpt.com/" },
    { name: "Claude", url: "https://claude.ai/new" },
    { name: "Gemini", url: "https://gemini.google.com/app" },
    { name: "Kimi", url: "https://www.kimi.com/" },
    { name: "GLM", url: "https://chat.z.ai/" },
    { name: "Qwen", url: "https://chat.qwen.ai/" },
    { name: "Arena", group: "multi", url: "https://arena.ai/text/direct" },
    { name: "Meta AI", url: "https://www.meta.ai/" },
    { name: "PromptQL", url: "https://prompt.ql.app/", description: "open a project, then a bot chat; keep the @Bot chip on." },
    { name: "SuperApp", url: "https://superapp.chat/", description: "sign in once; SuperApp keeps the session as a cookie." },
    { name: "Vani", url: "https://c.vani.ai/chat", group: "multi", description: "Multi-model chat. For regular use, we recommend Vani Plus; compare the current plans first." },
    { name: "Venice", url: "https://venice.ai/chat/agent", group: "multi", description: "Private multi-model chat; use a model available on your account." },
    { name: "ClickUp", url: "https://app.clickup.com/", group: "multi", description: "Open a private Brain AI conversation; human team channels are never auto-selected." },
    { name: "Notion AI", group: "multi", url: "https://app.notion.com/chat", description: "opens the real Notion AI chat, not workspace Connectors." },
  ];

  let coworkQueue = null;
  const A = {
    running: false,
    stop: false,
    // stopping: the user clicked Stop and we are winding the loop down. Set the
    // instant the button is clicked so the bar can show immediate "Stopping…"
    // feedback and keep the button steady (no flicker) until the loop's finally
    // clears it - the live generation signal toggles off/on as the loop drains,
    // which otherwise made the Stop button vanish then reappear.
    stopping: false,
    // userStopped: the user deliberately halted generation - via our "■ Stop"
    // button OR the site's native stop. While set, the auto-resume watchdog
    // must NOT relaunch or re-run a tool from the halted turn.
    userStopped: false,
    // lastUserText: exactly what the user typed on their most recent send,
    // captured by the provider's send hook BEFORE the composer is cleared. The
    // prompt enhancer reads it once, at the top of agentLoop; it is never used
    // to rewrite anything the user can see.
    lastUserText: "",
    // lastGenAt: timestamp of the last moment the site was actively generating.
    // The auto-resume watchdog only acts on a tool call from a RECENT live
    // generation - never on a historical turn rendered by opening/scrolling.
    lastGenAt: 0,
    started: false,
    starting: false,
    software: false, // 6.26 Software Builder (W.I.P.) session - implies chatOnly
    chatOnly: false, // professional studio prompt/skills without requiring any MCP engine
    // The conversation a bootstrap belongs to + a generation counter. If the user
    // navigates to another chat mid/post-bootstrap, syncSessionState bumps the
    // counter (invalidating the in-flight startSession) and clears `starting`, so
    // the new chat shows its own state instead of a stale "Starting…".
    startingKey: null,
    startGen: 0,
    // The conversation a RUNNING loop is bound to. If the user opens a new, empty
    // chat via the site's own button, syncSessionState abandons the loop so the
    // fresh chat shows "Start", not a stale "Agent active".
    loopKey: null,
    // Identity of the assistant turn ALREADY present when the current session
    // started. A page reload can RESTORE an in-progress generation (e.g. an
    // execute_luau that was mid-stream in an A/B turn); that restored turn looks
    // like a fresh live tool finish to the auto-resume watchdog, which then ran it
    // into the NEW conversation the user had just opened (validated live, 2026-06).
    // autoResume never resumes the turn whose id matches this baseline.
    bootBaselineId: null,
    injecting: false,
    toolRunning: false,
    toolStart: 0,
    toolName: "",
    toolItem: null,
    toolArg: "",
    toolList: [],
    toolNames: new Set(),
    // Browser-side engine preference is authoritative even while an older
    // bridge is still connected. It also drives the standby button so an
    // engine switched off in Settings can never be offered as "Start …".
    disabledEngines: new Set(),
    // Verification assistant state (core/verification.js). verifyState is the
    // live slowdown bookkeeping - floorMs grows with each challenge and decays
    // proportionally once the provider stays clean. verifyCount is the number
    // of challenges seen this session (surfaced in diagnostics). Declared here,
    // never assigned before this point (see the note next to verificationSettings).
    verifyState: ZSVerify.initialState(),
    verifyCount: 0,
    // Studio ids learned from Roblox's own answers (list_roblox_studios,
    // get_studio_state, ...). Roblox's MCP requires `studio_id` on every
    // place-scoped command; with two Studios connected an omission is a hard
    // failure, and with one it is silently auto-selected - so we learn the id as
    // soon as any answer mentions it and inject it when the model forgets.
    // Empty means "not learned yet": we then tell the model to run
    // list_roblox_studios rather than guessing a value we do not have.
    studios: [],
    // Successful tool calls since the last command-list reminder. DeepSeek (and
    // others) can drift away from the exact command names over a long session,
    // so we re-inject the list every REMIND_TOOLS_EVERY calls (see agentLoop).
    toolCallsSinceReminder: 0,
    // When the system prompt was last re-stated. Diagnostic only - whether one
    // is OWED is derived from the conversation itself, never from a counter
    // (see sinceLastSys / sysResendDue).
    sysResendAt: 0,
    // This page outlived its extension build - nothing works until a reload.
    // Latched (never cleared): the context cannot come back. See bg().
    staleExtension: false,
    bridge: { connected: false, mcpAlive: false, tools: 0 },
    // Images from the most recent tool result, stashed by runTool for the
    // upcoming submitAndGetBase/typeAndSend call to attach as the LAST step
    // before sending (see the comment in runTool's r.images branch).
    pendingImages: null,
    // BARE names of tools observed to return images at least once this session.
    // For the KNOWN Roblox vision tool (screen_capture) toolCategory already
    // gives the "screen" chip optimistically at run time; a custom MCP tool's
    // name tells us nothing, so we can't predict it - but once we've SEEN it
    // return an image we can be optimistic on its NEXT call. Populated in the
    // agent loop's result branch when A.pendingImages lands.
    imageTools: new Set(),
    // True while the loop is parked waiting for this tab to come back to the
    // foreground (see waitVisible/parkHidden). Drives the bar's "Paused" state.
    parked: false,
    // True while parked waiting for the USER to clear a bot-check / human
    // verification. Drives the bar's "Verification needed" state.
    verifying: false,
    // Pacing bookkeeping. sendIndex counts turns sent in this session (drives
    // the periodic long pause), lastSendAt anchors the inter-turn gap, and
    // lastErrorAt arms the pacing engine's error cooldown so a retry storm can
    // never deepen a rate limit.
    sendIndex: 0,
    lastSendAt: 0,
    lastErrorAt: 0,
    pacingUntil: 0,
    pacingReason: "",
    // Timestamp of the last successful tool-catalogue refresh (see ensureTools).
    toolsAt: 0,
  };

  try {
    chrome.storage.local.get("msDisabledEngines", (r) => {
      A.disabledEngines = new Set(Array.isArray(r && r.msDisabledEngines) ? r.msDisabledEngines : []);
      try { ui.updateStartGate(); } catch {}
    });
  } catch {}

  // Engines the bridge reports as actually connected (editor attached and the MCP
  // server alive). Used to make the system prompt and the offline messages
  // engine-aware: a Godot-only session must not be told that "Roblox Studio is
  // always connected", and must not be sent looking for Roblox when something is
  // down. Returns [] when the bridge has not reported engines yet, which keeps the
  // legacy Roblox-first wording instead of wrongly claiming there is no engine.
  function connectedEngineIds() {
    const engines = (A.bridge && A.bridge.engines) || [];
    return engines
      .filter((e) => e && e.enabled !== false && !A.disabledEngines.has(String(e.id || "").toLowerCase()) && e.connected === true && e.alive !== false)
      .map((e) => String(e.id || "").toLowerCase())
      .filter(Boolean);
  }
  function activeEngineIds(){return A.chatOnly&&!(A.software&&softwareSettings.addons?.engines)?[]:connectedEngineIds();}
  function sessionExecutionTools(){return A.toolList.filter(t=>{
    const native=(A.bridge?.servers||[]).find(s=>s.id===t.server);
    if(t.server!=="zeroscript"&&native?.alive===false)return false;
    if(!A.software&&isSoftwareTool(t.name))return false;
    if(isLocalUltraTool(t.name)&&executionEffort!=="ultra")return false;
    if(A.chatOnly&&!A.software)return !ZSToolRouting.isEngineExecution(t.name,{},A.toolList);
    if(A.software)return isLocalProgressTool(t.name)||isLocalUltraTool(t.name)||isSoftwareTool(t.name)||softwareAllowsTool(t.name,t.server);
    const engine=t.server==='roblox-companion'?'roblox':t.server;
    return !['roblox','godot','unity','blender'].includes(engine)||activeEngineIds().includes(engine);
  });}
  const engineLabel = (id) => (ZSEngine && ZSEngine.displayName ? ZSEngine.displayName(id) : id);

  // The bridge-offline note names Roblox Studio because that is the usual cause.
  // With no Roblox connected it would send the user to check the wrong thing, so
  // name what is actually in use instead.
  function bridgeOfflineFeedback() {
    const ids = connectedEngineIds();
    if (!ids.length || ids.includes("roblox")) return ZS.FEEDBACK.bridgeOffline;
    return ZS.FEEDBACK.bridgeOffline +
      ` In this session the engines in use are ${ids.map(engineLabel).join(", ")} - Roblox Studio is NOT one of them, ` +
      `so do not tell the user to open Roblox Studio.`;
  }

  async function waitFor(pred, timeout) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeout) {
      if (pred()) return true;
      await sleep(120);
    }
    return false;
  }

  // Park until the AI tab is the FOREGROUND tab of its window again (or the user
  // halts). Deliberately has NO time cap: a tab minimized/backgrounded for an
  // hour must resume cleanly, not silently time out into a "could not send /
  // not run" failure. (A plain waitFor with a finite timeout returned false on a
  // long minimize, which broke the send loop and ended the agent loop.) Returns
  // false ONLY if the user stopped while we were parked, so callers can break.
  // EVENT-DRIVEN, not polled. A chained setTimeout loop is subject to Chrome's
  // "intensive throttling": once a tab has been hidden >5 min, chained timers are
  // clamped to ONE tick per minute, so a sleep(300) poll could take up to a full
  // minute to notice the tab came back - the user sees the bar sit on "Paused"
  // long after they returned. visibilitychange fires immediately on unhide, so we
  // race it against a slow stop-poll (the stop path is not latency-critical).
  async function waitVisible() {
    if (!pageHidden() || A.stop) return !A.stop;
    A.parked = true;
    try { ui.setStarting(); } catch {}
    try {
      await new Promise((resolve) => {
        const done = () => {
          document.removeEventListener("visibilitychange", onVis);
          clearInterval(iv);
          resolve();
        };
        const onVis = () => { if (!pageHidden()) done(); };
        document.addEventListener("visibilitychange", onVis);
        // Safety net only: covers a stop click while parked, and the (unlikely)
        // case of a missed visibilitychange event.
        const iv = setInterval(() => { if (A.stop || !pageHidden()) done(); }, 1000);
      });
    } finally {
      A.parked = false;
      try { ui.setStarting(); } catch {}
    }
    return !A.stop;
  }

  // Park while the tab is hidden and report how long we were parked, so callers
  // can slide their timers forward by that amount. Without this, every deadline
  // inside waitForResponse (inactivity timeout, warm-up, text-stability) keeps
  // ticking while nothing can be read - which is what turned "user switched to
  // Studio for 5 minutes" into "No response from <site>, the loop has stopped"
  // and left the pending command showing a grey "not run".
  async function parkHidden() {
    if (!pageHidden() || A.stop) return 0;
    const t0 = Date.now();
    await waitVisible();
    const parked = Date.now() - t0;
    diag("park.resumed", { parkedMs: parked });
    // Give the site a beat to repaint: a tab that was hidden has no layout, so
    // the first reads after unhide can come back stale/blank.
    if (!A.stop) await sleep(400);
    return parked;
  }

  // ── Human verification (bot-check) handling ───────────────────────────────
  // Some sites (Arena most often) answer an automated cadence with a Cloudflare
  // Turnstile / hCaptcha / reCAPTCHA / Arkose challenge. Multi-Script NEVER
  // solves, token-injects, outsources or otherwise bypasses such a challenge -
  // that is an anti-bot protection and defeating it would be both wrong and a
  // guaranteed ban. What the agent CAN do is behave like a well-mannered human:
  // notice the challenge, stop typing into the composer, get its own overlays
  // out of the way (see placeBar / inputCover, which hide while captchaPresent),
  // tell the user exactly what to do, and then RESUME ON ITS OWN the moment the
  // challenge clears - instead of dying with a "not run" chip.
  //
  // Returns true when the page is clear (or was already clear), false only when
  // the user pressed Stop or the wait cap elapsed.
  //
  // The escalation ladder lives in ZSVerify: banner -> our overlays off the
  // widget's hit area -> audible/title alert -> ONE trusted click on the
  // provider's own widget -> re-alert. Which steps actually fire depends on the
  // configured mode. The full wait is bounded by the longer of the recovery
  // budget and the user's own verification wait, so an unattended run parks
  // rather than dying.
  async function awaitHumanVerification(reason) {
    if (!(P.captchaPresent && P.captchaPresent())) return true;
    const mode = vmode();
    const cap = Math.max(rbudgets().verificationWaitMs, Number(verificationSettings.waitMs) || 0);
    const t0 = Date.now();
    A.verifying = true;
    A.verifyCount = (A.verifyCount || 0) + 1;
    // Record the challenge so the pacing floor widens: this provider is telling
    // us the current send rate is too aggressive.
    if (mode.adaptive) {
      A.verifyState = ZSVerify.noteChallenge(A.verifyState, t0);
      diag("verification.slowdown", { floorMs: A.verifyState.floorMs, streak: A.verifyState.streak });
    }
    const hint = P.verificationHint ? (P.verificationHint() || "") : "";
    diag("verification.pause", { reason, capMs: cap, hint, mode: mode.id });
    try { ui.banner("warn", ZSVerify.COPY.bannerTitle,
      ZSVerify.COPY.bannerBody +
      (hint ? `\n\nDetected: ${hint}` : "") +
      (A.verifyState.floorMs ? `\n\nSpacing messages ${Math.round(A.verifyState.floorMs / 1000)}s further apart afterwards.` : "")); } catch {}
    let applied = 0;
    // Alert: the human may be in another tab, so make the run noticeable.
    let alerted = false;
    let assisted = false;
    try {
      while (!A.stop && Date.now() - t0 < cap) {
        if (!P.captchaPresent()) break;
        const elapsed = Date.now() - t0;
        for (const step of ZSVerify.escalationActions(applied, elapsed, mode)) {
          applied = step.atMs;
          if (step.action === "cover") {
            try { ui.inputCover(true); } catch {}
          } else if (step.action === "alert" || step.action === "re-alert") {
            if (!alerted || step.action === "re-alert") {
              alerted = true;
              try { verificationAlert(step.action === "re-alert", elapsed); } catch {}
            }
          } else if (step.action === "assist-click") {
            if (!assisted && P.assistChallengeClick) {
              assisted = true;
              const r = P.assistChallengeClick();
              diag("verification.assist_click", { clicked: !!r.clicked, reason: r.reason || "", tag: r.tag || "" });
              if (r.clicked) { try { ui.toast(ZSVerify.COPY.assistNotice); } catch {} }
            }
          }
        }
        await sleep(700);
      }
    } finally {
      A.verifying = false;
      try { ui.inputCover(!!(A.running || A.starting)); } catch {}
      try { clearVerificationAlert(); } catch {}
    }
    const cleared = !P.captchaPresent();
    diag("verification.resume", { cleared, waitedMs: Date.now() - t0, reason, mode: mode.id, assisted });
    if (cleared) {
      // A cleared challenge is a fresh start for the retry budgets too: the
      // failures that preceded it were the challenge's fault, not the model's.
      A.lastErrorAt = 0;
      // Mark the moment so the settle taper and the adaptive decay are measured
      // from the clear, not from the challenge first appearing.
      A.verifyState = { ...A.verifyState, lastAt: Date.now() };
      try { ui.toast(ZSVerify.COPY.cleared); } catch {}
      if (A.verifyState.floorMs && mode.adaptive) {
        try { ui.toast(ZSVerify.COPY.slowed); } catch {}
      }
    } else if (!A.stop) {
      try { ui.banner("warn", "Still waiting on verification", ZSVerify.COPY.exhausted); } catch {}
    }
    return cleared;
  }

  // Make a parked run noticeable from another tab: an optional short tone
  // (WebAudio, no asset needed) plus a title prefix. Never throws - a browser
  // with autoplay blocked must not break the wait.
  let _verifyTitleBase = null;
  function verificationAlert(again, elapsedMs) {
    const s = verificationSettings || {};
    const mine = ZSVerify.modeFor(s, P.id);
    if (!s.audibleAlert || !mine.alert) return;
    try {
      if (_verifyTitleBase == null) _verifyTitleBase = document.title;
      const mins = Math.max(1, Math.round((elapsedMs || 0) / 60000));
      document.title = `⚠ Verification needed${again ? ` (${mins}m)` : ""} - ${_verifyTitleBase}`;
    } catch {}
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      const ctx = new AC();
      const now = ctx.currentTime;
      // Two short pings, higher and slightly longer on the repeat alert so the
      // two are distinguishable without looking at the screen.
      const freqs = again ? [880, 1175] : [660, 880];
      freqs.forEach((f, i) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = f;
        const start = now + i * 0.18;
        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.exponentialRampToValueAtTime(0.06, start + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.16);
        osc.connect(gain); gain.connect(ctx.destination);
        osc.start(start); osc.stop(start + 0.18);
      });
      setTimeout(() => { try { ctx.close(); } catch {} }, 800);
    } catch {}
  }
  function clearVerificationAlert() {
    if (_verifyTitleBase == null) return;
    try { document.title = _verifyTitleBase; } catch {}
    _verifyTitleBase = null;
  }

  // Submit `text` as a new turn, masking the input while we type. Returns the
  // assistant-item count BEFORE the reply (waitForResponse waits beyond it).
  // Snapshot the identity of the assistant turn present BEFORE we send. Paired
  // with waitForResponse, this lets "a new reply turn exists" be tested by node
  // identity rather than a raw count - the latter is unreliable on providers that
  // virtualize the message list, where the count stays flat as a new
  // turn appears and old ones detach. Captured at every send site (tool feedback,
  // user message, bootstrap). Providers without lastAssistantId fall back to count.
  function captureSendToken() {
    A.sendToken = P.lastAssistantId ? P.lastAssistantId() : undefined;
    A.sendReplyFingerprint = P.reusesTurnNodes ? String(P.readAssistant()?.reply||'').replace(/\s+/g,' ').trim() : null;
  }

  // ════════════════════════════════════════════════════════════════════════
  //  SITE NOTICE WATCHER (6.28.3) - rate limits, outages, usage caps
  // ════════════════════════════════════════════════════════════════════════
  // Sites report a refused/failed turn in many shapes: DeepSeek prints
  // "Messages too frequent. Try again later." under the user's message (no
  // assistant turn at all), others show a toast, an alert, or a short error
  // "reply". Watching only the assistant turn missed most of them, so the loop
  // read nothing, nudged, got refused again... (the reported storm). From each
  // send on, every SMALL node the site adds is classified; a hit makes the
  // watcher return kind "rate" / "busy" / "quota" and the loop waits the site
  // out and re-sends the SAME message (siteRecover).
  const NOTICE = { obs: null, hit: null, armedAt: 0, sent: "" };
  const OWN_UI_SEL = '#zs-root, #zs-input-cover, #zs-setup, #zs-diag-log, [class*="zs-"], [id^="zs-"], #rs-root';
  function noticeCandidate(el) {
    if (!el || el.nodeType !== 1 || NOTICE.hit) return;
    try {
      if (el.closest(OWN_UI_SEL) || el.closest("pre, code, textarea, [contenteditable='true']")) return;
      const ed = P.getEditor && P.getEditor();
      if (ed && (ed === el || ed.contains(el) || el.contains(ed))) return;
      const t = (el.textContent || "").replace(/\s+/g, " ").trim();
      if (t.length < 4 || t.length > 320) {
        if (t.length > 320 && el.childElementCount) {
          // A big subtree (a whole new turn) - look at its small leaves only.
          let n = 0;
          for (const c of el.querySelectorAll("p, span, div, li, [role='alert'], [role='status']")) {
            if (++n > 400 || NOTICE.hit) break;
            if (c.childElementCount > 4) continue;
            const ct = (c.textContent || "").trim();
            if (ct.length >= 4 && ct.length <= 320) noticeCandidate(c);
          }
        }
        return;
      }
      if (NOTICE.sent && NOTICE.sent.includes(t)) return; // our own message text
      const c = ZSResilience.classifyNotice(t);
      if (!c) return;
      if (!el.getClientRects().length) return; // hidden (e.g. camouflaged raw text)
      // Inside the model's reply: only the short whole-reply case counts, and
      // only for unambiguous site phrasing (rate / quota) - a model may well
      // write "something went wrong" in a normal answer.
      const la = P.lastAssistant && P.lastAssistant();
      if (la && la.contains(el)) {
        if (c.kind === "busy") return;
        const whole = (P.itemText ? P.itemText(la) : la.textContent || "").trim();
        if (whole.length > 320 || ZSParse.hasToolSignature(whole)) return;
        if (ZSResilience.isExplicitProviderLimit && !ZSResilience.isExplicitProviderLimit(whole)) return;
      }
      NOTICE.hit = { ...c, at: Date.now() };
      diag("site.notice", { kind: c.kind, text: c.text.slice(0, 120) });
    } catch {}
  }
  function armSiteNotice(sentText) {
    NOTICE.hit = null;
    NOTICE.armedAt = Date.now();
    NOTICE.sent = String(sentText || "").replace(/\s+/g, " ");
    if (NOTICE.obs || typeof MutationObserver === "undefined" || !document.body) return;
    try {
      NOTICE.obs = new MutationObserver((muts) => {
        if (NOTICE.hit || !(A.running || A.starting || A.injecting)) return;
        for (const m of muts) {
          if (m.type === "characterData") noticeCandidate(m.target && m.target.parentElement);
          else for (const n of m.addedNodes) noticeCandidate(n.nodeType === 3 ? n.parentElement : n);
          if (NOTICE.hit) break;
        }
      });
      NOTICE.obs.observe(document.body, { childList: true, subtree: true, characterData: true });
    } catch {}
  }
  const siteNoticeHit = () => NOTICE.hit;
  const SITE_KINDS = new Set(["busy", "rate", "quota"]);
  function saveRateFloor() {
    try {
      chrome.storage.local.get(["msRateFloor"], (r) => {
        const m = (r && r.msRateFloor && typeof r.msRateFloor === "object") ? r.msRateFloor : {};
        m[P.id] = Math.round(A.rateFloorMs || 0);
        chrome.storage.local.set({ msRateFloor: m });
      });
    } catch {}
  }
  // Wait the site out, then re-send the SAME message. Returns the new base, or
  // null when the budget is spent / the user stopped (caller reports honestly).
  async function siteRecover(res, attempt) {
    const kind = SITE_KINDS.has(res.kind) ? res.kind : "busy";
    A.lastErrorAt = Date.now();
    if (kind === "rate" || kind === "quota") await bg({type:"ms_provider_pacing",action:"notice",provider:P.id,owner:"site-notice",kind,reason:String(res.text||"").slice(0,200),retryAfterMs:ZSResilience.retryAfterMs?ZSResilience.retryAfterMs(res.text):0});
    if (kind === "rate") { A.rateFloorMs = ZSResilience.nextRateFloor(A.rateFloorMs); saveRateFloor(); }
    const last = A.lastOutbound || null;
    const d = ZSResilience.decide(rlevel(), kind, { attempt, raw: last && last.text ? last.text : "", notice:res.text, jitter: Math.random(), minDelayMs: kind === "rate" ? (A.rateFloorMs || 0) : 0 });
    diag("site.recover", { kind, action: d.action, reason: d.reason, attempt, delayMs: d.delayMs, floor: A.rateFloorMs || 0, text: String(res.text || "").slice(0, 80) });
    if (d.action !== "resend" && d.action !== "retry") return null;
    const label = kind === "rate" ? "is rate-limiting messages" : kind === "quota" ? "reports a usage limit" : "reported an error";
    ui.toast(`${P.displayName} ${label} · waiting ${Math.round(d.delayMs / 1000)}s, then re-sending (${attempt + 1}/${attempt + 1 + d.attemptsLeft})…`);
    A.pacingUntil = Date.now() + d.delayMs;
    A.pacingReason = "site-" + kind;
    let ok;
    try { ok = await paceSleep(d.delayMs); } finally { A.pacingUntil = 0; }
    if (!ok || A.stop) return null;
    if (pageHidden() && !(await waitVisible())) return null;
    if (d.action === "resend") return await submitAndGetBase(last.text, last.images, { ...(last.opts || {}), siteRetry: true });
    return await submitAndGetBase(d.feedback);
  }
  // waitForResponse + automatic site-refusal recovery. Used by the agent loop
  // and the startup handshake, so neither can be killed by one "too frequent".
  async function retryNativeResponse(res,attempt) {
    const decision=ZSResilience.decide(rlevel(),'native_response',{attempt});
    const item=res.item,chat=P.conversationKey(),stopAt=A.stopAt||0;
    const safe=()=>!!item?.isConnected&&!A.stop&&!A.userStopped&&!A.sendUnconfirmed&&P.conversationKey()===chat&&(A.stopAt||0)===stopAt&&!P.isGenerating()&&!P.editorText()?.trim()&&!P.captchaPresent?.()&&!P.waitingForUser?.()&&!P.sendBlockNotice?.()&&P.lastAssistant()===item&&!P.turnHalted(item)&&!isRememberedExecuted(item,P.itemText(item));
    const notice=ZSResilience.classifyNotice(res.text);
    if(decision.action!=='native-retry'||notice&&['rate','quota'].includes(notice.kind)||!safe())return false;
    const failure=()=>typeof MSStudio!=='undefined'?MSStudio.nativeResponseError(item):null;
    if(!failure()?.retryButton)return false;
    const run=readTaskProgress();
    if(run){MSProgress.activity(run,{kind:'recovery',title:'Recovering the provider response',detail:'Native Retry attempt '+(attempt+1)+'. Earlier local tool calls are not replayed.'});saveTaskProgress();}
    A.lastErrorAt=Date.now();A.pacingUntil=Date.now()+decision.delayMs;A.pacingReason='native-response-recovery';
    try{if(!await paceSleep(decision.delayMs))return false;}finally{A.pacingUntil=0;}
    if(!safe()||!await paceBeforeSend('native-response-retry')||!safe())return false;
    const owner=await acquireProviderSend();if(owner===false)return false;
    let clicked=false,ack=false;
    try{
      const button=failure()?.retryButton;
      if(!safe()||!button?.isConnected||button.disabled||button.getAttribute('aria-disabled')==='true'||!button.getClientRects().length)return false;
      const before=String(P.readAssistant().reply||'');
      // Retry only this failed, undispatched reply. Never resubmit its prompt,
      // clear a draft, or click an unrelated/historical Retry control.
      armSiteNotice('');clicked=true;button.click();A.lastSendAt=Date.now();A.sendIndex=(A.sendIndex||0)+1;
      const end=Date.now()+10000;
      while(Date.now()<end&&!A.stop&&P.conversationKey()===chat&&(A.stopAt||0)===stopAt){
        const current=P.readAssistant(),failed=(P.responseError&&P.responseError())||MSStudio.nativeResponseError(P.lastAssistant());
        if(P.isGenerating()||!failed&&current.reply&&(current.item!==item||String(current.reply)!==before)){ack=true;break;}
        await sleep(160);
      }
      diag('response.nativeRetry',{attempt:attempt+1,ack});
      return ack;
    }catch(error){diag('response.nativeRetryError',{error:String(error?.message||error)});return false;}finally{await releaseProviderSend(owner,'',ack);if(clicked&&!ack){A.sendUnconfirmed=true;A.lastSendError='Native Retry was clicked but a response was not acknowledged. Inspect the provider before retrying.';}}
  }
  async function waitSiteSafe(base) {
    let attempt = 0, nativeAttempts=0;
    for (;;) {
      const res = await waitForResponse(base);
      if(res.kind==='provider_error'&&!A.stop){if(await retryNativeResponse(res,nativeAttempts++))continue;return res;}
      if (!SITE_KINDS.has(res.kind) || A.stop) return res;
      const nb = await siteRecover(res, attempt++);
      if (nb === null || nb === undefined || A.lastSendOk === false) return res;
      base = nb;
    }
  }

  async function submitAndGetBase(text, images, opts) {
    // opts.visible: the turn is the USER's own message (an enhanced prompt) and
    // must stay visible - do not arm the injected-feedback pre-hide.
    const keepVisible = !!(opts && opts.visible);
    const sentSettingsKey=(opts&&opts.settingsKey)||A.pendingSettingsKey||null;
    A.pendingSettingsKey=null;
    captureSendToken();
    // Truthful outcome of THIS send, read by startSession. Before 6.25.1 a send the
    // site never accepted looked identical to one that worked: the bootstrap kept
    // waiting for a reply that could not exist and then declared the agent ready.
    A.lastSendOk = false;
    A.sendUnconfirmed = false;
    A.lastSendError = "";
    A.sendBannerShown = false;
    // Provider preference metadata is prepared once outside the retry
    // loop so a failed send never stacks duplicate routing signals.
    // A custom message cap applies to EVERY provider, including those with no truncateForSend of their own (Kimi, GLM, Meta).
    if (ZS.limits && ZS.limits.send().mode === "custom") { const o = ZS.limits.sendOverride(String(text)); if (o !== null) text = o; }
    A.lastOutbound = { text, images, opts: opts ? { visible: !!opts.visible, settingsKey:opts.settingsKey||sentSettingsKey } : sentSettingsKey?{settingsKey:sentSettingsKey}:undefined };
    const outboundText = P.prepareOutboundPrompt ? P.prepareOutboundPrompt(text) : text;
    armSiteNotice(outboundText);
    diag("send", { text: String(outboundText).slice(0, 60), busy: P.isBusyNow() });
    A.injecting = true;
    ui.inputCover(true);
    try {
      // Quick 2-point settle: sample the previous response's stream length before
      // and after a 200ms yield. A one-shot React batch flush (the common case)
      // shows no second growth and costs only 200ms. A genuinely still-generating
      // stream shows growth → fall back to the full idle wait.
      const _settleItem = P.lastAssistant();
      const _settleLen0 = _settleItem ? P.streamLen(_settleItem) : 0;
      await sleep(200);
      if(P.waitForSendReady){
        const blocked=P.sendBlockNotice?.();
        if(blocked){await bg({type:"ms_provider_pacing",action:"notice",provider:P.id,owner:"send-preflight",kind:blocked.kind,reason:blocked.text});A.lastSendError=blocked.text;ui.banner("warn",P.displayName+" sends paused",blocked.text);return P.assistantCount();}
        ui.setStarting();
        if(!await P.waitForSendReady({cancelled:()=>A.stop||!!(opts?.contextGuard&&!opts.contextGuard()),onWait:message=>ui.toast(message)})){A.lastSendOk=false;A.lastSendError='The provider is still responding or waiting for a response selection. No follow-up was sent.';if(!A.stop)ui.banner('warn','Provider is not ready for a follow-up',A.lastSendError);return P.assistantCount();}
        captureSendToken();
      }
      if (_settleItem && _settleItem === P.lastAssistant() &&
          P.streamLen(_settleItem) > _settleLen0) {
        await waitFor(() => !P.isGenerating(), 4000);
      }
      const base = P.assistantCount();
      const preUser = P.userCount();
      // Arm the optimistic pre-hide for the result turn we're about to inject:
      // the very next NEW user turn is ours, so preHideWholeItems can mask it on
      // creation instead of waiting for its "Output of '…'" caption to render
      // (which lands a tick after the node - especially with an attached image -
      // and would otherwise flash the raw output for the 200/700ms until a sweep
      // nudge catches it). See preHideWholeItems.
      A.injectPreUser = preUser;
      if (!keepVisible) A.injectHideUntil = Date.now() + 2500;
      // "Landed" = a new turn appeared in the DOM. In long chats, list
      // virtualisation can keep counts flat even when our message landed - the
      // textarea-cleared signal below is the primary fast gate.
      const landed = () => P.userCount() > preUser || P.assistantCount() > base;
      // CRITICAL: never type/send while the tab is HIDDEN. Background tabs throttle
      // rendering, which made the landed-check unreliable and caused the SAME
      // feedback to be sent several times. Send ONLY while visible.
      // A bot-check can appear at ANY moment (Arena re-issues one mid-session).
      // Never type into the composer while one is up: park until the user clears
      // it, then continue the same send.
      if (P.captchaPresent && P.captchaPresent()) {
        diag("send.verificationGate");
        if (!(await awaitHumanVerification("submit"))) return base;
      }
      let tries = 0;
      let messageSent = false;
      let wasBusyBeforeSend = false;
      let hardFails = 0; // typeAndSend threw (composer refused / not found)
      // The recovery level widens the send-retry budget: a swallowed send is the
      // cheapest failure to recover from (no model turn is burned), so a
      // persistent run simply tries harder before it gives up.
      const maxSendTries = 2; // bounded preflight retries; never replay an uncertain click
      while (!messageSent && !landed() && tries < maxSendTries && !A.stop) {
        if (pageHidden()) {
          diag("send.waitVisible", { tries });
          if (!(await waitVisible()) || A.stop) break; // park (no cap) until foreground; break only on user stop
        }
        // Enforce the configured gap and provider floor before delivery.
        if (!(await paceBeforeSend("submit"))) break;
        diag("submit.typeAndSend", { hasImages: !!(images && images.length) });
        // A provider's typeAndSend can legitimately refuse (Arena throws when a
        // bot-check appears mid-send). That must never escape as an "Internal loop
        // error" and kill the loop: treat it as a not-sent attempt, arm the error
        // cooldown, and let the retry loop / recovery policy decide what is next.
        let sendThrew = false;
        let noReplay = false,notSent=false;
        const permit=await acquireProviderSend();
        if (permit===false) break;
        try {
          if (A.stop) break;
          if(opts?.contextGuard&&!opts.contextGuard()){A.lastSendError="Chat or engine changed before delivery.";break;}
          await P.typeAndSend(outboundText, images, {cancelled:()=>A.stop||!!(opts?.contextGuard&&!opts.contextGuard()),referenceTask:keepVisible||!!images?.length});
        } catch (e) {
          sendThrew = true; hardFails++;
          noReplay = e.retryable===false || e.sendState==="unconfirmed";
          notSent=e.sendState==="not-sent";
          if (noReplay&&!notSent) A.sendUnconfirmed = true;
          A.lastErrorAt = Date.now();
          A.lastSendError = String((e && e.message) || e);
          diag("send.typeAndSendError", { tries, msg: String((e && e.message) || e).slice(0, 160) });
          if (P.captchaPresent && P.captchaPresent()) {
            if (!(await awaitHumanVerification("send"))) return base;
          }
        } finally {
          await releaseProviderSend(permit,noReplay&&!notSent?"unconfirmed":sendThrew?"busy":"",!sendThrew);
        }
        // A refused send must NEVER fall through to the "composer is empty, so it
        // was sent" check below: when the text never reached the editor the
        // composer is trivially empty, and that false positive is what left the
        // bar on "Starting…" with nothing in the chat.
        if (sendThrew && !landed()) {
          tries++;
          if (noReplay) break;
          { const h = siteNoticeHit(); if (h && h.kind === "rate") { A.rateFloorMs = ZSResilience.nextRateFloor(A.rateFloorMs); saveRateFloor(); if (!(await paceSleep(A.rateFloorMs))) break; NOTICE.hit = null; } }
          // During startup fail fast (2 refusals) instead of burning ~2 minutes
          // of retries + cooldowns on a composer that will not accept input.
          if (A.starting && hardFails >= 2) break;
          continue;
        }
        // Re-arm the pre-hide window NOW that typeAndSend has returned (the send
        // was just clicked, so our result turn is about to render). The initial
        // arm above can EXPIRE during an image upload - typeAndSend blocks ~3-6s
        // uploading the capture before the turn appears, past the 2.5s window - so
        // without this re-arm the raw "Output of…" + a still-loading (0-byte)
        // thumbnail flash for image feedbacks until a sweep chip lands. Safe: the
        // input is covered and the loop owns this send, so no user turn can slip
        // into the window, and the pre-hide is one-shot (consumes the first turn).
        if (!keepVisible) A.injectHideUntil = Date.now() + 2500;
        // The site clears the textarea as soon as the send is accepted - faster
        // and more reliable than waiting for a DOM turn count change.
        // How long to wait for the site to accept the message. A fixed 3.5 s was far too short: big messages
        // (the startup prompt carries the full standards) take a site many seconds to take in, and giving up early
        // shows "Message could not be sent" even though the send is still going through. Scales with size.
        const ackMs = Math.min(120000, Math.max(20000, 15000 + Math.round(String(outboundText || "").length / 2)));
        await waitFor(() => {
          if (P.editorText().trim() === "") messageSent = true;
          // Busy alone can be a previous response or a site notice; keep the
          // composer-cleared/new-turn acknowledgement instead.
          return messageSent || landed();
        }, ackMs);
        if (messageSent) noteNotionPrompt();
        tries++;
        if (!messageSent && !landed() && !A.stop) {
          A.sendUnconfirmed = true;
          A.lastSendError = "Send was attempted but no acknowledgement arrived; automatic replay paused.";
          break;
        }
      }
      A.lastSendOk = !!(messageSent || landed());
      if(A.lastSendOk && sentSettingsKey && sentSettingsKey===studioSettingsFingerprint()) studioSettingsDirty=false;
      if (A.lastSendOk) {
        // A turn actually left the composer: this is the anchor for the pacing
        // gap before the NEXT turn, and it advances the long-pause counter.
        A.lastSendAt = Date.now();
        A.sendIndex = (A.sendIndex || 0) + 1;
        diag("send.cleared", { tries, sendIndex: A.sendIndex });
      }
      // All retries exhausted with NO evidence the message landed (textarea never
      // cleared, no new turn). Silently returning here left the loop waiting for
      // a reply that will never come (~60s "empty" timeout) with zero explanation
      // - the reported "the tool result just never gets injected" symptom. Tell
      // the user what actually happened so they can nudge the conversation
      // themselves instead of watching a stuck bar.
      if (!messageSent && !landed() && !A.stop && !A.sendBannerShown) {
        // Arm the pacing engine's error cooldown so the NEXT attempt (the loop's
        // recovery resend, or the user's own nudge) waits a beat instead of
        // hammering a composer that just refused us.
        A.lastErrorAt = Date.now();
        const lvl = ZSResilience.policy(rlevel());
        let dg = "";
        try { if (P.sendDiagnostics) dg = JSON.stringify(P.sendDiagnostics()); } catch {}
        diag("send.failed", { tries, recovery: lvl.label, maxSendTries, dg });
        A.sendBannerShown = true;
        ui.banner("warn", "Message could not be sent",
          `${P.displayName}: ${A.sendUnconfirmed ? "send acknowledgement was not confirmed" : "the message was not accepted"} after ${tries} attempt${tries === 1 ? "" : "s"}. ` +
          (A.sendUnconfirmed
            ? `The message may have been accepted. Automatic replay stopped to prevent duplicates. Check the conversation before retrying. `
            : A.starting
            ? `Startup was cancelled instead of waiting for a reply that cannot arrive - click the composer once, then press Start again. `
            : `Automatic sending is paused. Check the provider notice and retry from the composer when ready. `) +
          (A.lastSendError ? `Reason: ${A.lastSendError.slice(0, 500)}. ` : ``) +
          (dg ? `Details: ${dg}` : ``));
      }
      return base;
    } finally {
      // During Starting Up / the agent loop, the bootstrap or loop owns the cover
      // for the whole phase, so don't lift it here between an injection and the
      // next waitForResponse - it stays up until the loop / bootstrap ends.
      if (!A.starting && !A.running) ui.inputCover(false);
      setTimeout(() => (A.injecting = false), 400);
      // Camouflage the turn we just injected without waiting on the rAF observer
      // (paused in a background tab). A couple of nudges cover the render.
      setTimeout(scheduleSweep, 200);
      setTimeout(scheduleSweep, 700);
    }
  }

  // ════════════════════════════════════════════════════════════════════════
  //  RESPONSE WATCHER  (generating-flag driven - robust to DOM churn)
  // ════════════════════════════════════════════════════════════════════════
  async function waitForResponse(base) {
    const t0 = Date.now();
    // INACTIVITY timeout (not total-elapsed): the loop only gives up after this
    // long with NO streaming AND no text change. lastActiveAt is refreshed every
    // tick the model is generating or the reply text grows, so an arbitrarily
    // LONG but still-active response never trips it (the old total-elapsed cap
    // wrongly fired "No response" while the model was still writing past 300s).
    const TIMEOUT = T.RESPONSE_TIMEOUT_MS;
    let lastActiveAt = Date.now(),lastGenerationActivityAt=Date.now(),lastGenerationText="",longWaitNoted=false;
    const STABLE_MS = T.STABLE_MS; // generating-flag stuck ON but text frozen → done
    let started = false, doneSince = 0, lastLimitScan = 0;
    let lastText = null, lastChangeAt = Date.now(), genFalseSince = 0;
    // ── DIAG: finalisation-latency instrumentation (multi_edit "slow" probe) ──
    // genOffFirstAt: the FIRST moment gen went false after streaming began (does
    // NOT reset on flicker, unlike genFalseSince). genFlickers: how many times gen
    // flipped back true after having been false - a high count means post-stop DOM
    // churn (or a wedged stop button) is what keeps the watcher alive. waitedBlock/
    // waitedFlicker: iterations spent waiting because effectiveBlock held vs because
    // gen was (re)true. These pinpoint which gate causes any tail latency.
    let genOffFirstAt = 0, genFlickers = 0, prevGen = null;
    let waitedBlock = 0, waitedFlicker = 0;
    const finalizeDiag = (kind) => {
      const now = Date.now();
      diag("stopGoneToResp", {
        kind,
        stopGoneToRespMs: genOffFirstAt ? now - genOffFirstAt : null,
        genStableForMs: genFalseSince ? now - genFalseSince : null,
        lastChangeAgoMs: now - lastChangeAt,
        genFlickers, waitedBlock, waitedFlicker,
        totalMs: now - t0,
      });
    };
    let preStartSilent = 0; // nothing produced AND not generating
    let curItem = null, sawContent = false, warmSince = 0; // per-turn "warming up"
    // Last NON-EMPTY reply read for the CURRENT turn. Sites re-render a turn's
    // subtree (React/Monaco churn) and a read can come back "" for a frame at
    // the exact moment the watcher finalizes - the turn then ended as
    // kind:"empty" even though a (possibly cut-off) command was sitting there a
    // tick earlier, leaving a DEAD turn: no parse_error feedback, and the
    // autoResume dedupe (zResume) blocks any later retry (validated live on a
    // Qwen post-stop regenerate, 2026-07). Classify on this fallback instead of
    // declaring empty. Reset whenever the turn NODE changes so a new turn can
    // never inherit the previous turn's text.
    let lastGoodReply = "";
    let reasonSince = 0; // reasoning written but no answer yet (loading phase)
    let noTurnSince = 0; // finalize attempted before this send's reply turn exists
    let unsettledSince = 0; // command-shaped reply whose read is not yet stable
    // Patience windows. The provider's calibrated base (T) is the floor; the
    // recovery level may WIDEN them, because a persistent/unattended run would
    // rather wait another minute for a slow engine than declare a dead turn and
    // burn a retry. Never narrowed - a fast session keeps its tight timings.
    const RB = rbudgets();
    const WARMUP_MS = Math.max(T.WARMUP_MS, RB.warmupMs);
    const REASON_NOREPLY_MS = Math.max(T.REASON_NOREPLY_MS, RB.reasonNoReplyMs);
    const PRE_START_SILENT_MS = RB.preStartSilentMs;
    const OPEN_BLOCK_GRACE_MS = RB.openBlockGraceMs;
    const NO_TURN_GRACE_MS = 30000;
    // Upper bound on holding off a parse verdict while a provider reports its
    // read is unsettled (Qwen A/B dual turn still landing). A genuinely stuck
    // read still resolves after this and is parsed as-is.
    const UNSETTLED_GRACE_MS = 8000;
    // Once the generating flag has been OFF this long, the model has clearly
    // stopped streaming - so an "open tool block" reading is a DOM-churn/parse
    // artifact, not live output, and must not keep the watcher waiting. Provider
    // -neutral: while a model is genuinely streaming, gen stays true and this is
    // never reached.
    const GEN_STOP_GRACE_MS = 2500;

    while (Date.now() - lastActiveAt < TIMEOUT) {
      if (A.stop) return { kind: "stopped" };
      // NEVER let a deadline expire while the tab is in the background. A hidden
      // tab has no layout (innerText reads come back "", getBoundingClientRect is
      // 0x0) and Chrome throttles its timers, so every read here is unreliable -
      // and the site may legitimately keep streaming for as long as the user is
      // away in Studio. Park until the tab is foreground again, then slide EVERY
      // deadline forward by the time we were parked so nothing that was mid-flight
      // when the user switched away expires the moment they come back. This is the
      // fix for "I switched to Studio, came back and the command says 'not run'":
      // the loop used to burn its 5-minute inactivity budget off-screen, end with
      // "No response from <site>", and orphan the pending command.
      if (pageHidden() && !A.stop) {
        const parked = await parkHidden();
        if (A.stop) return { kind: "stopped" };
        if (parked) {
          lastActiveAt += parked; lastChangeAt += parked;
          if (doneSince) doneSince += parked;
          if (genFalseSince) genFalseSince += parked;
          if (preStartSilent) preStartSilent += parked;
          if (warmSince) warmSince += parked;
          if (reasonSince) reasonSince += parked;
          lastGenerationActivityAt+=parked;
          if (noTurnSince) noTurnSince += parked;
          if (unsettledSince) unsettledSince += parked;
          if (genOffFirstAt) genOffFirstAt += parked;
        }
        continue; // re-read everything now that the tab has layout again
      }
      const gen = P.isGenerating();
      const nativeFailure=(P.responseError&&P.responseError())||(typeof MSStudio!=="undefined"?MSStudio.nativeResponseError(P.lastAssistant()):null);
      const currentResponse=P.assistantCount()>base||(P.lastAssistantId&&P.lastAssistantId()!==A.sendToken);
      if(nativeFailure&&currentResponse&&!gen){
        const run=readTaskProgress();if(run){MSProgress.activity(run,{kind:'provider-error',title:'Provider response failed',detail:nativeFailure.text});saveTaskProgress();}
        return {kind:"provider_error",text:nativeFailure.text,item:P.lastAssistant(),base};
      }

      if (gen) lastActiveAt = Date.now(); // actively generating ⇒ never time out
      const d = P.readAssistant();
      if(P.strictGeneration){const activity=String(d.reply||'')+"\n"+String(d.thinking||'');if(activity!==lastGenerationText){lastGenerationText=activity;lastGenerationActivityAt=Date.now();}}
      // A site refusal noticed anywhere on the page since this send (toast,
      // alert, a line under the user's message, a short error reply). Ignored
      // only while a real, long answer is still streaming.
      { const h = siteNoticeHit(); if (h && !(gen && (d.reply || "").length > 400)) { diag("response.siteNotice", { kind: h.kind }); return { kind: h.kind, text: h.text, item: d.item }; } }
      // Sites virtualize their lists, so the absolute assistant count can DROP
      // even as a new reply is added. A count increase still proves a new turn
      // appeared; the generating flag is the reliable "reply has begun" signal.
      // A new reply turn exists. Prefer node IDENTITY (virtualization-proof) when
      // the provider exposes it: the last assistant turn's id differs from the one
      // captured at send time. Fall back to the count test otherwise. Without this,
      // a provider's list virtualisation can keep assistantCount() <= base for a
      // fresh reply, so the reliableCounts gate below waits out the full NO_TURN_GRACE
      // (~30s) before finalising a multi_edit - the "input box stuck until I scroll
      // up" symptom (scrolling re-attached old turns and bumped the count).
      const curTok = P.lastAssistantId ? P.lastAssistantId() : undefined;
      // A NULL token means the provider could not read an identity for the
      // CURRENT last turn (not that the provider lacks ids - that's undefined).
      // Treating null as "no new reply" wedged the watcher on Qwen: a
      // REGENERATED turn is rebuilt WITHOUT the id attribute the normal turns
      // carry, so curTok stayed null, `started` never latched, and the loop
      // sat in the pre-start branch for the full 60s before ending "empty" -
      // the regenerated command (complete in the net tap) was never run and
      // zResume then blocked any retry (validated live via empty.why, 2026-07).
      // Fall back to the count test instead, exactly as for a provider with no
      // lastAssistantId at all.
      const identityAdvanced = (curTok !== undefined && curTok !== null)
        ? (curTok !== A.sendToken)
        : P.assistantCount() > base;
      const newReply=identityAdvanced||(P.reusesTurnNodes&&A.sendReplyFingerprint!==null&&A.sendReplyFingerprint!==undefined&&String(d.reply||'').replace(/\s+/g,' ').trim()!==A.sendReplyFingerprint&&!!d.reply);

      // Track whether the CURRENT turn has produced anything. Reset when the
      // turn node changes (the PREVIOUS turn's content never counts).
      if (d.item !== curItem) { curItem = d.item; sawContent = false; warmSince = 0; lastGoodReply = ""; }
      if ((d.reply && d.reply.length) || (d.thinking && d.thinking.length)) sawContent = true;
      if (d.reply && d.reply.length) lastGoodReply = d.reply;

      if (!started) {
        // CRITICAL: a bare count increase is NOT enough - the empty turn
        // CONTAINER can appear seconds before the first token. Require actual
        // CONTENT (or the generating flag).
        const hasText = !!((d.reply && d.reply.length) || (d.thinking && d.thinking.length));
        if (gen || (newReply && hasText)) { started = true; }
        else {
          // The site can be slow to even CREATE the reply turn. Keep waiting -
          // only give up after a long fully-silent window.
          if (!preStartSilent) preStartSilent = Date.now();
          // diag: WHICH empty-branch fired matters - a dead post-regenerate turn
          // on Qwen kept ending "empty" with a complete command in the net tap,
          // and without the branch name the cause was unfindable from the log.
          if (Date.now() - preStartSilent > PRE_START_SILENT_MS) { diag("empty.why", { branch: "preStart", rep: (d.reply||"").length }); return { kind: "empty" }; }
          await sleep(200);
          continue;
        }
      }

      // Track text stability (independent of the generating flag). Compare the
      // NORMALISED reply (collapsed whitespace) so cosmetic re-renders of a large
      // reply - React re-creating the hidden tool <pre>, syntax-highlight passes,
      // copy-bar text churn - don't count as real "changes" and keep resetting
      // lastChangeAt. A churn-poisoned lastChangeAt was stalling finalisation of
      // big multi_edit blocks ~30s (stuckDone never fired); this can only ever
      // reduce false changes, so short replies / other providers are unaffected.
      const replyNorm = (d.reply || "").replace(/\s+/g, " ").trim();
      if (replyNorm !== lastText) { lastText = replyNorm; lastChangeAt = Date.now(); lastActiveAt = Date.now(); }
      // How long the generating flag has been OFF. A mid-stream flicker resets
      // this the instant growth resumes and gen flips back on.
      if (gen) genFalseSince = 0; else if (!genFalseSince) genFalseSince = Date.now();
      // DIAG: first gen-off, and count flickers back to true after a gen-off.
      if (started && !gen && !genOffFirstAt) genOffFirstAt = Date.now();
      if (prevGen === false && gen && genOffFirstAt) genFlickers++;
      prevGen = gen;

      if (Date.now() - lastLimitScan > 1000) {
        lastLimitScan = Date.now();
        const ctx = P.scanError();
        if (ctx) return { kind: "context_limit", detail: ctx };
      }

      // Keep waiting while a tool command is still being streamed (opener written
      // but no end marker yet) so we never parse/finalize half a command.
      const blockActive = ZSParse.hasOpenToolBlock(d.reply) && Date.now() - lastChangeAt < OPEN_BLOCK_GRACE_MS;
      // ...but once generation has clearly stopped (stop indicator gone past the
      // grace window), stop honoring an "open block" - it is DOM churn, not live
      // streaming. Lets a finished big block finalise in seconds instead of
      // waiting out ~30s of re-render churn. Safe: real streaming keeps gen true.
      const genStopped = !gen && genFalseSince && Date.now() - genFalseSince > GEN_STOP_GRACE_MS;
      const effectiveBlock = blockActive && !genStopped;

      // Fallback: generating flag stuck ON (e.g. a wedged stop button - seen
      // live on Gemini after a mid-write halt) but the text has been frozen for
      // a while → stop waiting and finalize. This must BYPASS the gen branch
      // below entirely: falling through while gen stays true used to reset
      // doneSince every iteration, so the watcher never finalized at all.
      // ...but NEVER treat a still-OPEN command block as "done" while the site is
      // genuinely still generating. A model writing a big command (a 3799-char
      // execute_luau seen live on GLM) can pause >STABLE_MS between tokens - that
      // is a mid-write gap, NOT a wedged stop button on a COMPLETE reply. Firing
      // here parsed the half-written JSON and stamped a false "bad JSON" error
      // while GLM was still typing. RESPONSE_TIMEOUT still bounds a truly stuck one.
      if(P.strictGeneration&&gen&&!P.waitingForUser?.()&&!longWaitNoted&&Date.now()-lastGenerationActivityAt>Math.max(REASON_NOREPLY_MS,180000)){
        longWaitNoted=true;diag('response.longThinking',{provider:P.id});
        const run=readTaskProgress();if(run){MSProgress.activity(run,{kind:'waiting',title:'Provider is still thinking or writing',detail:'The native response is active. Waiting without interrupting it or sending another prompt.'});saveTaskProgress();}
      }
      const stuckDone = !P.strictGeneration && started && d.reply && Date.now() - lastChangeAt > STABLE_MS &&
        !(gen && ZSParse.hasOpenToolBlock(d.reply));
      if ((gen || effectiveBlock) && !stuckDone) {
        // DIAG: attribute this wait. genOffFirstAt set ⇒ we are PAST first stop,
        // so any wait here is tail latency: either gen flickered back on, or an
        // (effective) open-block reading is holding us.
        if (genOffFirstAt) { if (gen) waitedFlicker++; else if (effectiveBlock) waitedBlock++; }
        doneSince = 0;
        await sleep(160);
        continue;
      }
      if (stuckDone && gen) log("generating flag stuck - falling back to text stability");

      // On providers whose turn counts are RELIABLE (semantic elements, no
      // list virtualisation - Gemini), never finalize before the reply turn
      // for THIS send exists. The generating flag can flicker off in the gap
      // between the send and the new <model-response> node spawning, and the
      // watcher used to finalize on the PREVIOUS turn's stable text - a
      // premature loop.end rescued only by autoResume 30-45s later (diag
      // showed `response kind:text` ~2.4s after loop.start with rp unchanged).
      // Bounded so a genuinely dead send still ends the turn.
      if (P.reliableCounts && !newReply) {
        if (!noTurnSince) noTurnSince = Date.now();
        // [TRACE] This is the 30s NO_TURN_GRACE gate. If a Qwen tool turn sits here
        // ~30s EVERY turn, newReply is wrongly stuck false: log the identity values
        // that decide it so we can see whether curTok is null (id missing on the new
        // turn -> count fallback) or equal to sendToken (last turn not advancing).
        const _waited = Date.now() - noTurnSince;
        if (_waited > 800 && (!A._noTurnLoggedAt || Date.now() - A._noTurnLoggedAt > 3000)) {
          A._noTurnLoggedAt = Date.now();
          diag("noTurnGrace.wait", {
            waitedMs: _waited,
            curTok: (P.lastAssistantId ? P.lastAssistantId() : undefined),
            sendToken: A.sendToken,
            assistantCount: P.assistantCount ? P.assistantCount() : undefined,
            base, gen, started, replyLen: (d.reply || "").length });
        }
        if (Date.now() - noTurnSince < NO_TURN_GRACE_MS) { await sleep(200); continue; }
      } else {
        noTurnSince = 0;
        A._noTurnLoggedAt = 0;
      }

      if (!doneSince) doneSince = Date.now();
      if (Date.now() - doneSince < 500) {  // 500ms settle – DOM is stable
        await sleep(120);
        continue;
      }

      // A turn that has produced NOTHING yet is still warming up - never
      // finalize it as empty/truncated/text (a premature retry interrupts it).
      if (!sawContent) {
        if (!warmSince) warmSince = Date.now();
        if (Date.now() - warmSince < WARMUP_MS) { await sleep(200); continue; }
        diag("empty.why", { branch: "warmup", rep: (d.reply||"").length, lastGood: lastGoodReply.length });
        return { kind: "empty" };
      }

      // Still REASONING / loading: thinking written but no answer yet. Don't
      // finalize - wait for the reply, bounded. A manually-stopped turn is
      // exempt so a real stop still ends.
      if (d.thinking && d.thinking.length && !(d.reply && d.reply.length) && !P.turnHalted(d.item)) {
        if (!reasonSince) reasonSince = Date.now();
        if (Date.now() - reasonSince < REASON_NOREPLY_MS) { await sleep(200); continue; }
      } else {
        reasonSince = 0;
      }

      // Blank-read guard: if THIS read came back empty but the same turn had
      // real text a tick ago, classify that text - see lastGoodReply above.
      let r = d.reply;
      if (!r && lastGoodReply) { r = lastGoodReply; diag("reply.blankReadFallback", { len: r.length }); }
      // "Conversation too long" / "server busy" notices are always SHORT system
      // messages; gating on a short reply stops the model's own long output
      // (which may quote those phrases) from tripping them.
      if (r.length < 400 && P.isTooLongMsg(r)) return { kind: "too_long" };
      // The SITE reporting a transient outage ("server is busy", "please try
      // again") is NOT the model's answer. This used to fall through to
      // kind:"text" and end the loop as a normal terminal turn, which killed an
      // unattended run on a one-second hiccup - the commonest real failure on
      // DeepSeek at peak hours. Classify it as a recoverable "busy" instead.
      // Gates, so a normal answer that merely TELLS THE USER to try again is not
      // mistaken for a site outage: it must be SHORT, must not carry a command,
      // must not be our own injected feedback shape, and must match the
      // provider's own site-error phrasing (see providers/*.js RE.busy).
      if (r.length < 260 && !ZSParse.hasToolSignature(r) && !ZSParse.isInjectedFeedback(r)) {
        const cn = ZSResilience.classifyNotice(r);
        const explicitLimit = !ZSResilience.isExplicitProviderLimit || ZSResilience.isExplicitProviderLimit(r);
        if (P.isBusyMsg && P.isBusyMsg(r) && (!cn || cn.kind === "busy" || explicitLimit)) return { kind: cn ? cn.kind : "busy", text: r, item: d.item };
        if (cn && cn.kind !== "busy" && r.length < 200 && explicitLimit) return { kind: cn.kind, text: r, item: d.item };
      }
      // Hold off on any "unparseable command" verdict while the provider reports
      // this turn's text is not yet a settled read. Qwen's A/B "dual" turn is the
      // case: its network tap flips `done` the instant the SSE ends, but the
      // candidate-1 DOM we parse can still be mid-render, so a real command looks
      // half-written for a beat. Firing parse_error there sends an ERROR
      // mid-generation and nags a model that did nothing wrong. Only guard when
      // the reply already LOOKS like a command (so a plain-text answer is never
      // delayed) and bound it with UNSETTLED_GRACE_MS. No-op on providers that
      // don't implement replyUnsettled (DeepSeek/Gemini/GLM/Kimi/Arena).
      const cmdShaped = P.replyUnsettled && (
        ZSParse.hasToolSignature(r) ||
        (ZSParse.LUA_END_RE.test(r) && !ZSParse.LUA_START_RE.test(r)) ||
        (/"(?:datamodel_type|edits|old_string|new_string|file_path|target_file)"\s*:/.test(r) &&
          !/"command"\s*:/.test(r))
      );
      if (cmdShaped && P.replyUnsettled(d.item)) {
        if (!unsettledSince) unsettledSince = Date.now();
        if (Date.now() - unsettledSince < UNSETTLED_GRACE_MS) { await sleep(250); continue; }
      } else {
        unsettledSince = 0;
      }
      // A/B "carousel" turn (Qwen): while it is unresolved the site REMOVES the
      // composer from the DOM (validated live: getEditor() is null), so we can't
      // send the tool result until a candidate is picked - and the read reply is a
      // partial candidate, so a command there looks "cut off". Per the product rule
      // we use the FIRST candidate: wait for BOTH candidates to finish generating
      // (you can't select mid-stream), then auto-select Response 1. That collapses
      // the carousel to a normal turn - composer returns - and the normal parse/run
      // path below handles it. Never a parse_error here (the model didn't truncate).
      // No-op for every provider except Qwen. RESPONSE_TIMEOUT still bounds a truly
      // stuck carousel, so this cannot hang.
      if (P.isComparisonTurn && P.isComparisonTurn(d.item)) {
        if (P.isGenerating()) { await sleep(250); continue; }   // both still writing
        if (P.resolveComparison && P.resolveComparison()) {
          diag("carousel.resolved");
          await sleep(400); continue;                            // let it collapse, re-read
        }
        await sleep(250); continue;                              // button not ready yet
      }
      if (ZSParse.hasToolSignature(r)) {
        const calls = ZSParse.parseToolCalls(r);
        if (calls.length) { finalizeDiag("tool"); return { kind: "tool", calls, item: d.item }; }
        // A half-written command + the site's "Continue" button means the command
        // was truncated mid-stream → resume it rather than reporting bad JSON.
        if (P.findContinueBtn()) return { kind: "truncated", text: r, item: d.item };
        // DeepSeek's own tool-call markup (<|DSML|>...) that could not be turned into a
        // call (a bare <|DSML|>tool_calls>, no tool name, or a value cut off mid-way).
        // The marker never occurs in ordinary prose, so this is always a real attempt:
        // tell the model to resend it as the JSON command instead of ending the turn
        // silently (the dead "command ... not run" chip).
        if (ZSParse.DSML_RE.test(r)) return { kind: "parse_error", reason: "dsml", raw: r, item: d.item };
        // Only fire parse_error if explicit markers were present.
        if (r.includes(ZSParse.START_M) || ZSParse.LUA_START_RE.test(r)) return { kind: "parse_error", reason: "malformed", raw: r, item: d.item };
        // A command opener with no closer (a JSON object that never closed -
        // the model was halted mid-write and there is no Continue affordance):
        // ask the model to rewrite it instead of silently ending the turn.
        // ...unless ONLY the trailing closers were lost (the model hit its
        // output limit with the payload complete - seen live on Qwen: a big
        // multi_edit missing exactly one final "}"). salvageCutOff auto-closes
        // and runs it instead of burning a whole retry turn; it refuses any
        // cut that amputated real content (mid-string / deep deficit), which
        // still falls through to the parse_error feedback. Safe to run here:
        // generation has ended (the open-block branch above kept waiting
        // while it streamed).
        if (ZSParse.hasOpenToolBlock(r)) {
          const saved = (!ZS.limits || ZS.limits.salvageAllowed()) ? ZSParse.salvageCutOff(r) : null;
          if (saved) {
            diag("tool.salvaged", { name: saved.tool });
            finalizeDiag("tool");
            return { kind: "tool", calls: [saved], item: d.item };
          }
          return { kind: "parse_error", reason: "unclosed", raw: r, item: d.item };
        }
        // A closed-looking JSON command envelope that NAMES A REAL TOOL but failed
        // to parse - typically an unescaped " inside a code/string param broke the
        // JSON (seen live on Kimi's execute_blender_code: `name = "Camera_System"`
        // mid-code). Unlike execute_luau there is NO ###LUA### fallback, so the
        // command silently dropped and the loop finalized the turn as a plain-text
        // answer with no result and no error - a dead turn. Fire a parse_error so
        // the model can fix its JSON. GATED on a known command name so prose that
        // merely quotes {"command":"..."} (a DeepSeek-style explanation, or a
        // placeholder like "command_name") is NOT misread as a broken command and
        // looped on - only a real tool name means a genuine failed call.
        const nm = ZSParse.toolNameFromText(r);
        if (nm && nm !== "command" && (A.toolNames.has(nm) || A.toolNames.has(bareToolName(nm)))) {
          return { kind: "parse_error", reason: "malformed", raw: r, item: d.item };
        }
        // A reply that IS a command (it opens with {"command"/{"tool", optionally inside a
        // code fence) but cannot be read is a failed attempt even when the tool name is
        // unknown/mistyped - prose never starts that way. Without this the turn ended
        // silently with a "command ... not run" chip.
        if (/^\s*(?:```[a-z]*\s*)?\{\s*["\u201c]\s*(?:command|tool)\s*["\u201d]/i.test(r)) {
          return { kind: "parse_error", reason: "malformed", raw: r, item: d.item };
        }
      }
      // Malformed execute_luau: the model wrote the ###END_LUA### closer but
      // FORGOT the ###LUA### opener, so hasToolSignature missed it and the block
      // never ran (seen on Gemini). Don't silently treat it as a final answer -
      // nudge a rewrite instead of leaving the user stuck on a dead turn.
      if (ZSParse.LUA_END_RE.test(r) && !ZSParse.LUA_START_RE.test(r) && !r.includes(ZSParse.START_M)) {
        return { kind: "parse_error", reason: "luaOpener", raw: r, item: d.item };
      }
      // Malformed command: the model emitted a tool's RAW ARGUMENTS as a bare JSON
      // object (e.g. {"datamodel_type":...,"edits":[...],"file_path":...}) instead of
      // the required {"command":...,"params":...} envelope - it treated the tool as a
      // real callable function (seen on Gemini). Those argument keys never appear in a
      // normal prose answer, so nudge a rewrite rather than ending the turn silently.
      if (/"(?:datamodel_type|edits|old_string|new_string|file_path|target_file)"\s*:/.test(r) &&
          !/"command"\s*:/.test(r)) {
        return { kind: "parse_error", reason: "envelope", raw: r, item: d.item };
      }
      // Malformed command, function-calling flavour: the model named a REAL tool
      // but under the WRONG KEY - {"toolName": "get_studio_state", "studio_id": …}
      // instead of {"command": …, "params": {…}}. It reads as a deliberate call,
      // yet hasToolSignature never fires (no "command" key, no markers) and the
      // argument keys are the tool's own, so neither guard above catches it: the
      // turn finalized as a plain-text answer and the loop ENDED with the user
      // watching a dead agent (seen live on ChatGPT, long session, 2026-08).
      // GATED on the value being a tool we actually have - same reasoning as the
      // toolNameFromText gate above, so prose that merely mentions a tool name in
      // some JSON example is never looped on.
      const wrongKey = /"(?:toolName|tool_name|tool|name|function|action)"\s*:\s*"([A-Za-z0-9_.\/-]+)"/.exec(r);
      if (wrongKey && !/"command"\s*:/.test(r)) {
        const wk = wrongKey[1];
        const hit = knownTool(wk);
        // Log the miss too: the gate depends on how the bridge ADVERTISES names
        // (they can be prefixed per server on a collision), so a silent no-match
        // is exactly the case that is impossible to diagnose after the fact.
        diag("cmd.wrongKey", { name: wk, known: hit, catalogue: A.toolNames.size });
        if (hit) return { kind: "parse_error", reason: "toolKey", raw: r, item: d.item };
      }
      // NOTE: a site "server busy / something went wrong" notice IS now handled -
      // see the kind:"busy" classification above, which routes it through the
      // bounded recovery policy instead of ending the run. It used to fall
      // through to kind:"text" and simply END the loop as a final answer, on the
      // reasoning that retrying risked an infinite re-answer loop; the recovery
      // policy removes that risk (one retry, then stop), so the safer behaviour
      // for an unattended run is now to retry once.
      // The site caps output length and shows a native "Continue" button when it
      // truncates. We try clicking it directly (same turn) in the loop.
      if (P.findContinueBtn()) return { kind: "truncated", text: r, item: d.item };
      if (r === "") { diag("empty.why", { branch: "finalBlank" }); return { kind: "empty" }; }
      return { kind: "text", text: r };
    }
    return { kind: "timeout" };
  }

  // ════════════════════════════════════════════════════════════════════════
  //  TOOL EXECUTION  (always returns a feedback string for the model)
  // ════════════════════════════════════════════════════════════════════════
  // An ORPHANED content script: the extension was reloaded, updated or disabled
  // while this page stayed open, so the script still running here belongs to a
  // version of the extension that no longer exists. Chrome tears down its
  // messaging port, and every chrome.runtime call then fails INSTANTLY with
  // "Extension context invalidated".
  //
  // This must be told apart from a real bridge outage. They are opposite
  // problems with opposite fixes: a bridge outage is fixed by the terminal icon and
  // resolves itself, while this one can ONLY be fixed by reloading the page and
  // never recovers on its own. Lumping them together (the old behaviour) told
  // the model "the local Multi-Script bridge is unreachable", which sent the user
  // to check a bridge that was perfectly healthy. Diagnosed 2026-08-14 by the
  // giveaway timing: a genuine outage takes 8s (background.js `send` waits via
  // waitForConnection first), an invalidated context comes back in ~1ms.
  //
  // Every user meets this eventually - Chrome auto-updates extensions under
  // open tabs - so it is worth its own message.
  const isContextInvalidated = (m) =>
    /Extension context invalidated|Receiving end does not exist|message port closed/i.test(m || "");

  function bg(msg) {
    return new Promise((resolve) => {
      const fail = (m) => resolve({
        ok: false,
        kind: isContextInvalidated(m) ? "stale-extension" : "disconnected",
        error: m,
      });
      try {
        chrome.runtime.sendMessage(msg, (resp) => {
          if (chrome.runtime.lastError) fail(chrome.runtime.lastError.message);
          else resolve(resp || { ok: false, kind: "disconnected", error: "no response from background" });
        });
      } catch (e) {
        fail(String(e && e.message || e));
      }
    });
  }

  // 'subagent' is always blocked (long-running, hangs the loop). 'screen_capture'
  // is only blocked on providers whose underlying model can't see images
  // (P.supportsVision === false) - see providers/*.js for the per-site flag.
  // Both are filtered out of the advertised command list AND refused in runTool.
  // Addon servers (Blender, Sketchfab, ...) can ALSO ship an image-returning
  // tool under any name we don't know in advance - rather than guess names,
  // any tool result carrying images is caught generically at the point results
  // are handled (see the `r.images.length` branch) and turned into a plain
  // error on non-vision providers, so nothing needs to be predicted here.
  // Commands Multi-Script refuses outright. `subagent` is permanently disabled
  // (it is not routed here). The set is shared with core/config.js so the block
  // list and the refusal TEXT cannot drift apart - that drift is what produced
  // the old, false "it timed out" message for a command that never had a chance.
  const ALWAYS_BLOCKED_TOOLS = (ZS.PERMANENTLY_BLOCKED instanceof Set)
    ? ZS.PERMANENTLY_BLOCKED
    : new Set(["subagent"]);
  const VISION_TOOLS = new Set(["screen_capture"]);
  const bareToolName = (name) => (name && name.includes("/") ? name.split("/").pop() : name) || "";
  // Is `name` a tool we actually have? The bridge ADVERTISES names that may carry
  // a per-server prefix when two MCP servers expose the same tool (see
  // list_tools in bridge.py), while the model always writes the bare name - so a
  // plain `A.toolNames.has(bare)` misses, and so does bareToolName(bare), which
  // cannot re-add a prefix it never had. Compare bare-to-bare in BOTH directions.
  const bareKey = (n) => String(n || "").split("/").pop().split(".").pop();
  const isLocalProgressTool=n=>/^(?:(?:multiscript|zeroscript)[/.])?ms_task_progress$/.test(n||'');
  const isLocalUltraTool=n=>/^(?:(?:multiscript|zeroscript)[/.])?ms_ultra_manual$/.test(n||'');
  // Every script the AI runs or writes in Studio is checked by the bridge's Luau analyzer; problems are appended to the tool result.
  async function codeReviewNote(bareName,args){
    try{
      if(!knownTool('ms_roblox_docs'))return '';
      let payload=null;
      if(bareName==='execute_luau'&&typeof args.code==='string'&&args.code.length>=40)payload={code:args.code};
      else if(bareName==='msrb_replace_script'&&typeof args.source==='string'&&args.source.length>=40)payload={code:args.source,path:String(args.path||'')};
      else if((bareName==='multi_edit'||bareName==='msrb_patch_script')&&Array.isArray(args.edits)){
        const text=args.edits.map(e=>e&&typeof e==='object'?String(e.new_string??e.new_str??e.replace??''):'').join('\n');
        if(text.length>=40)payload={code:text,fragment:true,path:String(args.path||args.target_file||'')};
      }
      if(!payload)return '';
      const r=await bg({type:"call_tool",name:"ms_roblox_docs",arguments:{action:"review",...payload},timeout:8000});
      if(!r||!r.ok)return '';
      const j=JSON.parse(r.text||'{}');
      return j.note?'\n\n'+j.note:'';
    }catch{return '';}
  }
  // Forge is drawn in this extension, so it is always advertised here, even when an older bridge
  // does not list it. Without this the chat rejects ms_forge as an unknown command.
  const FORGE_TOOL={name:'ms_forge',description:'Forge: draws real game art (UI kits, VFX textures, backdrops) in the browser, uploads it through Studio and installs a ready Luau module in one call. action=ui_kit (art + optional ForgeKit integration), action=vfx (textures + optional ForgeVFX integration), action=backdrop (16:9 background). Options: style, pack (ui_kit defaults to essentials; pass pack=full for everything), colours, reference_image, install, demo.',inputSchema:{type:'object',properties:{action:{type:'string',enum:['ui_kit','vfx','backdrop','styles']},style:{type:'string'},pack:{type:'string'},install:{type:'boolean'},demo:{type:'boolean'},quick:{type:'boolean',description:'Legacy compatibility option. The selected pack always renders completely; choose a smaller pack for a smaller deliverable.'},reference_image:{type:'string'}},required:['action']}};
  const isForgeTool=n=>/^(?:(?:multiscript|zeroscript)[/.])?ms_forge$/.test(n||'');
  function knownTool(name) {
    if (!name || !A.toolNames.size) return false;
    if (A.toolNames.has(name) || A.toolNames.has(bareToolName(name))) return true;
    if (A.hiddenTools && (A.hiddenTools.has(name) || A.hiddenTools.has(bareToolName(name)))) return true;
    const b = bareKey(name);
    for (const t of A.toolNames) if (bareKey(t) === b) return true;
    return false;
  }
  const isBlockedTool = (name) => {
    const bare = bareToolName(name);
    if (ALWAYS_BLOCKED_TOOLS.has(bare)) return true;
    // screen_capture is no longer refused on text-only providers: runTool turns
    // the image into a text "visual digest" (ZS.imageDigest) instead.
    if (memToolHidden(bare)) return true;
    return false;
  };

  // ── Learned image tools (reload-proof "screen" chip) ──────────────────────
  // The known Roblox vision tool (screen_capture) is themed "screen" by name via
  // ZS.toolCategory. A custom MCP tool's NAME reveals nothing, so we learn which
  // ones return images and persist that across reloads: with it, a revisited or
  // reloaded conversation still shows the image-capture chip (not the generic
  // wrench), and the NEXT call of a known image tool is optimistic from the start.
  // The marker below is the exact tail runTool appends to a feedback that carries
  // an image (see runTool's r.images branch) - the reload-proof signal, readable
  // straight from the injected result turn's text even when no loop is running.
  const IMAGE_FEEDBACK_RE = /image is attached to THIS message/i;
  function rememberImageTool(name) {
    const bare = bareToolName(name);
    if (!bare || A.imageTools.has(bare)) return;
    A.imageTools.add(bare);
    diag("imageTool.remember", { name: bare, total: A.imageTools.size });
    try { chrome.storage.local.set({ zsImageTools: [...A.imageTools].slice(-200) }); } catch {}
  }
  try {
    chrome.storage.local.get("zsImageTools", (r) => {
      if (r && Array.isArray(r.zsImageTools)) for (const n of r.zsImageTools) A.imageTools.add(n);
      diag("imageTool.loaded", { tools: [...A.imageTools] });
    });
  } catch {}

  // How long a fetched catalogue stays good enough to reuse without a round trip.
  const TOOLS_TTL_MS = 30000;

  // Refresh the tool catalogue - but never pay for it twice in a row.
  //
  // DEGRADED MODE (Roblox Studio closed, running on an addon server like Blender)
  // is where this used to hurt: a list_tools whose Roblox half is dead blocks the
  // bridge until it gives up, and the extension waited the FULL background timeout
  // for it. The boot sequence calls this three times in a row - startSession(),
  // then the model's list_commands, then list_mcp_servers - so the user watched
  // ~a minute of dead air with the model's reply already finished on screen
  // ("the first commands take forever even though the model clearly stopped
  // writing"). A short TTL collapses those three calls into one, and the caller
  // keeps the catalogue it already has instead of stalling for a fresh one.
  // ── Graph memory (core/memory.js): per-chat ON/OFF + prompt + auto-capture ──
  const ZM = window.ZSMemory || null;
  const memCtrl = ZM ? new ZM.MemoryController({
    bg: (m) => bg(m),
    providerId: P.id,
    conversationKey: () => P.conversationKey(),
    onChange: () => { try { ui.memChanged(); } catch {} },
  }) : null;
  const memOn = () => !!(memCtrl && memCtrl.isOn());
  const memToolHidden = (name) => !!(ZM && ZM.isMemoryTool(name) && !memOn());
  // Keep the advertised tool list in step with the per-chat Memory switch.
  function memSyncTools() {
    A.toolsAt = 0;
    if (!memOn()) {
      A.toolList = A.toolList.filter((t) => !memToolHidden(t.name));
      A.toolNames = new Set(A.toolList.map((t) => t.name));
    } else {
      ensureTools(true).catch(() => {});
    }
  }
  function memStateChanged() {
    memSyncTools();
    // Turned ON in a chat that already started: the model has not been told yet.
    A.memAnnounce = !!(memOn() && A.started);
  }

  async function ensureTools(force) {
    if (!force && A.toolList.length && Date.now() - A.toolsAt < TOOLS_TTL_MS) {
      diag("tools.cached", { age: Date.now() - A.toolsAt, n: A.toolList.length });
      return A.toolList;
    }
    const t0 = Date.now();
    const r = await bg({ type: "list_tools" });
    diag("tools.fetched", { ms: Date.now() - t0, n: (r && r.tools && r.tools.length) || 0 });
    if (r && Array.isArray(r.tools)) {
      const tools = r.tools.filter((t) => !isBlockedTool(t.name) && !memToolHidden(t.name));
      if(typeof MSProgress!=='undefined'&&!tools.some(t=>t.name==='ms_task_progress'))tools.push(MSProgress.TOOL);
      if(typeof MSForge!=='undefined'&&!tools.some(t=>t.name==='ms_forge'))tools.push(FORGE_TOOL);
      if(executionEffort==='ultra'&&typeof MSUltraManuals!=='undefined'&&!tools.some(t=>t.name==='ms_ultra_manual'))tools.push(MSUltraManuals.TOOL);
      A.toolList = tools;
      A.toolNames = new Set(tools.map((t) => t.name));
      // Retired aliases are not advertised but stay callable (see bridge RETIRED_FROM_CATALOGUE).
      A.hiddenTools = new Set(Array.isArray(r.hidden) ? r.hidden : []);
      A.toolsAt = Date.now();
    }
    return A.toolList;
  }

  // ms_surface_list is answered by TWO processes: the bridge enumerates desktop
  // windows, the service worker enumerates browser tabs. Neither alone is a
  // useful answer to "what do I have open?", so we merge them into one payload
  // the model can reason about in a single step. Failure of either half degrades
  // that half to empty WITH an explicit note - never a silent blank that reads
  // as "nothing is open".
  function mergeSurfaceList(winHalf, tabHalf) {
    const out = { ok: true, tabs: [], tabCount: 0, windows: [], windowCount: 0, notes: [] };
    // Bridge half: { ok:true, text:"<json>" } where text is the JSON payload.
    if (winHalf && winHalf.ok !== false && typeof winHalf.text === "string") {
      try {
        const parsed = JSON.parse(winHalf.text);
        out.windows = Array.isArray(parsed.windows) ? parsed.windows : [];
        out.windowCount = typeof parsed.windowCount === "number" ? parsed.windowCount : out.windows.length;
        out.degraded = !!parsed.degraded;
        if (parsed.capabilities) out.capabilities = parsed.capabilities;
      } catch (_) {
        out.notes.push("The desktop-window half could not be parsed.");
      }
    } else {
      out.notes.push("Desktop windows are unavailable (the local bridge is not answering).");
    }
    // Extension half: the worker's surfaceList() reply, already plain JSON.
    if (tabHalf && tabHalf.ok !== false) {
      out.tabs = Array.isArray(tabHalf.tabs) ? tabHalf.tabs : [];
      out.tabCount = typeof tabHalf.count === "number" ? tabHalf.count : out.tabs.length;
      out.activeTabId = tabHalf.activeTabId === undefined ? null : tabHalf.activeTabId;
    } else {
      out.notes.push("Browser tabs are unavailable (the extension worker did not answer).");
    }
    out.note = "Tabs are addressed by integer tab_id; windows are addressed by handle or pid. Call ms_surface_read for a tab's text, ms_app_read_window for a window's text.";
    return { ok: true, text: JSON.stringify(out, null, 2) };
  }

  // ── Result paging (6.26) ────────────────────────────────────────────────
  // A provider that declares resultCharBudget/resultLineBudget gets long tool
  // results split into pages instead of having its adapter silently cut the
  // middle out. The model pulls the rest with {"command":"more_output"}.
  const PAGED = { name: "", pages: [] };
  const isSoftwareTool = (n) => typeof ZSExtras !== "undefined" && (/^ms_ws_/.test(bareToolName(n || "")) || ZSExtras.WS_TOOL_NAMES.has(bareToolName(n || "")));
  // 6.36: Code/Build sessions may opt in to add-ons (skills, engines, other MCP).
  const softwareAllowsTool = (n, server) => typeof ZSExtras !== "undefined" && ZSExtras.softwareAllows
    ? ZSExtras.softwareAllows(softwareSettings, bareToolName(n || ""), server || ((A.toolList || []).find((t) => bareToolName(t.name) === bareToolName(n || "")) || {}).server || "")
    : isSoftwareTool(n);
  function pageFooter(i) {
    const n = PAGED.pages.length;
    return `\n\n[Multi-Script: the output of '${PAGED.name}' was split into ${n} pages so it fits in this chat - this is page ${i}/${n}. Nothing was lost and nothing needs re-running. Retrieve another page only if it contains information still needed for the user's task; otherwise continue the work. For catalogue schemas, list_commands with names/query can retrieve just the needed tools.${i < n ? ` Next page: {"command":"more_output","params":{"page":${i + 1}}}` : " This is the last page."}]`;
  }
  function paginateResult(text, name) {
    let cap = Number(P.resultCharBudget) || 0, lineCap = Number(P.resultLineBudget) || 0;
    // Limits setting: "off" never pages; "custom" pages at the user's size on any provider.
    const lim = ZS.limits ? ZS.limits.result() : { mode: "auto" };
    if (lim.mode === "off") return text;
    if (ZS.limits) cap = ZS.limits.resultCap(cap, P.sendCharBudget);
    if (lim.mode === "custom") lineCap = 0;
    if (typeof text !== "string" || (!cap && !lineCap)) return text;
    const lines = text.split("\n");
    if ((!cap || text.length <= cap) && (!lineCap || lines.length <= lineCap)) return text;
    const maxC = cap ? Math.max(2000, cap - 600) : Infinity, maxL = lineCap ? Math.max(40, lineCap - 8) : Infinity;
    const pages = []; let cur = [], len = 0;
    const flush = () => { if (cur.length) pages.push(cur.join("\n")); cur = []; len = 0; };
    for (let ln of lines) {
      while (ln.length > maxC) { flush(); pages.push(ln.slice(0, maxC)); ln = ln.slice(maxC); }
      if (len + ln.length + 1 > maxC || cur.length >= maxL) flush();
      cur.push(ln); len += ln.length + 1;
    }
    flush();
    if (pages.length < 2) return text;
    PAGED.name = String(name || "command"); PAGED.pages = pages;
    diag("tool.paged", { name: PAGED.name, pages: pages.length, chars: text.length });
    return pages[0] + pageFooter(1);
  }
  // Fingerprint of an APPENDING multi_edit (some edit has an empty / missing old_string).
  // "" when the call is not that shape. Used by the replay guard in runTool.
  function appendEditFingerprint(name, args) {
    try {
      if (bareToolName(name) !== "multi_edit" || !args || typeof args !== "object") return "";
      const edits = Array.isArray(args.edits) ? args.edits : [args];
      if (!edits.some((e) => e && typeof e === "object" && (e.new_string != null) && !String(e.old_string || ""))) return "";
      const body = JSON.stringify([args.file_path || args.target_file || "", edits.map((e) => [String((e && e.old_string) || ""), String((e && e.new_string) || "")])]);
      let h = 5381;
      for (let i = 0; i < body.length; i++) h = ((h << 5) + h + body.charCodeAt(i)) | 0;
      return `${body.length}:${h}`;
    } catch { return ""; }
  }
  async function runTool(call, _depth = 0) {
    const nm = call && call.tool;
    if (nm === "more_output" || nm === "ms_more_output") {
      const a = (call && call.arguments) || {};
      if (!PAGED.pages.length) return `Output of 'more_output':\nERROR: there is no paged output waiting. Re-run the original command only if you really need it again.`;
      const page = Math.max(1, Math.min(PAGED.pages.length, Math.round(Number(a.page) || 2)));
      return `Output of '${PAGED.name}' (page ${page}/${PAGED.pages.length}):\n${PAGED.pages[page - 1]}${pageFooter(page)}`;
    }
    if (nm && bareToolName(nm) === "ms_workshop_connection") return "ERROR: Workshop connections are configured by the user in Settings, not by model commands.";
    // Software Builder tools exist only inside a "Build software" session, and
    // ms_ws_configure is the extension's own control channel - never a model's.
    if (nm && isSoftwareTool(nm)) {
      if (bareToolName(nm) === "ms_ws_configure") return "ERROR: ms_ws_configure is internal to the Multi-Script extension and cannot be called from chat.";
      if (!A.software) return `ERROR: '${nm}' belongs to the Software Builder / Code mode. It only works in a session started with the bar's "Build software" or "Code" button after enabling it in Settings → Software Builder.`;
    }
    // "Start without engine" is a hard execution boundary. Editors may remain
    // connected in the background, but this session cannot touch them.
    if (A.chatOnly) {
      if (A.software && !isLocalProgressTool(nm) && !isLocalUltraTool(nm) && !isSoftwareTool(nm) && !softwareAllowsTool(nm)) {
        return `ERROR: '${nm}' is unavailable in this ${softwareSettings.mode === "code" ? "Code mode" : "Software Builder"} session. It may use ms_ws_* workspace tools${softwareSettings.addons && softwareSettings.addons.skills ? " and Multi-Script's general skill tools" : ""}; the user can enable more add-ons (engines, other MCP servers) in Settings → Software Builder.`;
      }
      if (!A.software && typeof ZSToolRouting !== "undefined" &&
          ZSToolRouting.isEngineExecution(nm, (call && call.arguments) || {}, A.toolList)) {
        return `ERROR: '${nm}' was blocked because this chat was started without an engine. Open a new chat and press the engine Start button to change Roblox, Unity, Godot or Blender.`;
      }
    }
    const out = await runToolInner(call, _depth);
    return paginateResult(out, nm);
  }
  async function runToolInner(call, _depth = 0) {
    // JSON-ONLY robustness: models occasionally DOUBLE-WRAP the envelope, e.g.
    // {"command":"execute_luau","params":{"command":"execute_luau","params":{…}}}
    // or nest the real call one level down. The intent is unmistakable, so unwrap
    // (bounded, so a pathological payload can never recurse) instead of refusing
    // a call the model clearly meant to make.
    if (_depth < 3 && call && call.arguments && typeof call.arguments === "object" &&
        typeof call.arguments.command === "string" &&
        call.arguments.params && typeof call.arguments.params === "object") {
      diag("tool.unwrapEnvelope", { outer: call.tool, inner: call.arguments.command, depth: _depth });
      return runTool({ tool: call.arguments.command, arguments: call.arguments.params }, _depth + 1);
    }
    let name = call.tool;
    let args = call.arguments || {};
    if(bareToolName(name)==='ms_roblox_omni'&&args.action==='install'&&A.software&&!softwareSettings.addons?.engines)return 'ERROR: OMNI installation requires the engines add-on. Read-only library actions remain available with the skills add-on.';
    if (!name) return ZS.FEEDBACK.parseError("malformed");
    if(isLocalUltraTool(name)&&typeof MSUltraManuals!=='undefined'){
      if(executionEffort!=='ultra')return 'ERROR: Ultra specialist manuals are inactive. The user must select Ultra on the effort slider; lower effort does not apply these methods.';
      try{return "Output of 'ms_ultra_manual':\n"+JSON.stringify(MSUltraManuals.read({...args,engine:args.engine||(typeof MSUltraCraft!=='undefined'&&MSUltraCraft.target?.(A.lastUserText,{engines:A.software||A.chatOnly?['workspace']:connectedEngineIds()}))||undefined}));}catch(error){return 'ERROR ms_ultra_manual: '+error.message;}
    }
    if(isLocalProgressTool(name)&&typeof MSProgress!=='undefined'){
      try{const current=readTaskProgress(),next=MSProgress.apply(current,args);if(args.action!=='read'&&next!==current){taskLedger=next;saveTaskProgress();}return 'Output of ms_task_progress:\n'+JSON.stringify(MSProgress.receipt(next,args,next!==current&&args.action!=='read'));}
      catch(error){const current=readTaskProgress();return 'ERROR ms_task_progress: '+error.message+(current?' Current run_id: '+current.id+'. Read with {"action":"read"}; do not replay a report from an older task.':' No active task in this chat context.');}
    }
    // Forge draws game art here, in the browser canvas (no Python add-ons); the bridge stores and serves it.
    // With install (default when Roblox Studio is connected) MSForge.run also uploads, binds and installs in one call.
    if(isForgeTool(name)&&typeof MSForge!=='undefined'&&['ui_kit','vfx','backdrop'].includes(String(args.action||''))){
      const steps=[];
      const callBridge=async(tool,a,timeout=120000)=>{const r=await bg({type:"call_tool",name:tool,arguments:a,timeout});if(!r||!r.ok)throw new Error(String((r&&r.error)||'bridge offline'));return String(r.text||(r.result&&r.result.text)||'');};
      const studioCall=async(tool,a,timeout=180000)=>{
        const route=ZSToolRouting.resolve(tool,'',A.toolList);
        if(!route.ok)throw new Error(tool+' is not available; is Roblox Studio connected with its MCP server on?');
        const sid=args.studio_id||(A.studios&&A.studios[0]&&A.studios[0].id);
        const body={...a};if(sid&&body.studio_id==null)body.studio_id=sid;
        const r=await bg({type:"call_tool",name:route.name,arguments:body,timeout});
        if(!r||!r.ok)throw new Error(tool+': '+String((r&&r.error)||'no answer'));
        return String(r.text||'');
      };
      const studioReady=ZSToolRouting.resolve('upload_image','',A.toolList).ok&&ZSToolRouting.resolve('execute_luau','',A.toolList).ok;
      try{
        const done=await MSForge.run(args,{callBridge,studioCall,studioReady,steps});
        name="ms_forge";
        args={action:"report",name:done.name,report:JSON.stringify({steps,install:done.install})};
      }catch(error){return 'ERROR ms_forge: '+(error&&error.message||error)+(steps.length?' (done so far: '+steps.join('; ')+')':'');}
    }
    // ── Action-dispatch repair (Unity and any engine built the same way) ─────
    // Roblox Studio exposes one tool per action, so a model that has just worked
    // on Roblox writes the ACTION where the TOOL belongs: {"command":"get_hierarchy"}.
    // In an action-dispatch engine that name is not a tool at all, and the old code
    // answered "unknown command" - which reads to the model as "this engine cannot
    // do that" and derails the whole task. If the name is a known action of exactly
    // ONE advertised tool, rewrite the call in place. If several tools own it the
    // call is genuinely ambiguous and we refuse rather than guess.
    if (typeof ZSEngine !== "undefined" && ZSEngine.resolveAction) {
      const fix = ZSEngine.resolveAction(name, args, (n) => knownTool(n));
      if (fix.ok) {
        diag("tool.actionRepair", { from: name, to: fix.tool, action: fix.action });
        ui.toast(`'${name}' is a ${engineLabel(ZSEngine.engineOfTool(fix.tool))} action - running ${fix.tool}`);
        name = fix.tool;
        args = fix.params;
      } else if (fix.reason === "ambiguous") {
        return `ERROR: '${name}' is an ACTION, not a command, and ${fix.candidates.length} tools accept it: ` +
          `${fix.candidates.join(", ")}. Write the TOOL as "command" and the action inside params.action, e.g. ` +
          `{"command":"${fix.candidates[0]}","params":{"action":"${name}", ...}} - pick the tool that matches what you are trying to do.`;
      }
    }
    // A bare action can be rewritten to a real engine tool above. Re-check after
    // repair so aliases cannot bypass the engine-free session boundary.
    if (A.chatOnly && (!A.software||!softwareAllowsTool(name,args._server)) && typeof ZSToolRouting !== "undefined" &&
        ZSToolRouting.isEngineExecution(name, args, A.toolList)) {
      return `ERROR: '${name}' was blocked because this chat was started without an engine. Connected engines are intentionally isolated in this session.`;
    }
    // An action-dispatch tool whose schema REQUIRES params.action, called without
    // one, can only be a mistake - the server cannot guess the operation. Say which
    // actions exist instead of forwarding a call that returns a vague failure.
    if (typeof ZSEngine !== "undefined" && ZSEngine.toolSpec) {
      const spec = ZSEngine.toolSpec(name);
      if (spec && spec.dispatch && Array.isArray(spec.req) && spec.req.includes("action") && !args.action) {
        const acts = ZSEngine.actionsOf(name);
        return `ERROR: '${name}' needs params.action - it is ONE tool that performs many operations. ` +
          `Valid actions: ${acts.join(", ") || "(see list_commands)"}. ` +
          `Example: {"command":"${name}","params":{"action":"${acts[0] || "get"}", ...}}`;
      }
    }
    // ── Roblox studio_id fill-in ────────────────────────────────────────────
    // Roblox's Studio MCP requires `studio_id` on every place-scoped command.
    // With exactly ONE Studio open the proxy silently auto-selects it and the
    // omission looks harmless; with TWO or more connected every such command is
    // rejected outright ("parameters.studio_id is required" - recorded in this
    // repo's own bridge_debug.log). So when the model forgets it we fill it in
    // from the id we have learned, and when we CANNOT (nothing learned yet, or
    // several Studios and no way to tell which) we say so plainly and name the
    // fix instead of forwarding a call we know will fail.
    if (typeof ZSEngine !== "undefined" && ZSEngine.withStudioId) {
      const fill = ZSEngine.withStudioId(name, args, A.studios);
      if (fill.applied) {
        args = fill.params;
        diag("tool.studioId", { name, studioId: fill.studioId, source: "learned" });
      } else if (fill.reason === "ambiguous" || fill.reason === "none-known") {
        return ZS.FEEDBACK.studioId(name, "(no studio_id was supplied)",
          A.studios.map((s) => s.id),
          fill.reason === "ambiguous" ? fill.candidates : []);
      }
    }
    if(/^ms_roblox_gui_audit$/.test(bareToolName(name))&&!args.studio_id&&Array.isArray(A.studios)&&A.studios.length===1)args={...args,studio_id:A.studios[0].id};
    const capabilityCounts = () => ({
        direct: sessionExecutionTools().filter((t) => t.server === "zeroscript").length,
      skills: Number((A.bridge && A.bridge.skills) || 800),
      virtual: Number((A.bridge && A.bridge.virtualTools) || 300),
    });
    // NEVER execute while the AI tab is backgrounded/minimized. This is the single
    // choke point for ALL execution (agentLoop's tool dispatch AND the bootstrap's
    // list_commands), so it closes the hole the loop-entry gate alone left open:
    // the tab is foreground when a cycle starts, the model then generates for
    // 30-120s, the user minimizes MID-generation, and waitForResponse returns a
    // tool call that fired into Studio off-screen (observed live: GLM minimized
    // still ran execute_luau). Parking here (no time cap) means the call runs the
    // moment the tab is foreground again, instead of being lost or run blind.
    if (pageHidden() && !A.stop) {
      diag("tool.waitVisible", { name });
      // Only reachable via a user Stop while parked; agentLoop's post-runTool
      // A.stop check breaks the loop and discards this, so it just needs to be
      // a non-crashing, clearly-labelled string.
      if (!(await waitVisible()) || A.stop) return "ERROR: the command was not run - stopped by the user.";
    }
    // Blocked commands: refuse up-front with a clear, tailored error so the
    // model abandons it and continues instead of wasting/hanging a turn.
    //
    // The message must be TRUE for the reason it is blocked. The old fallback
    // told the model a permanently-disabled command "timed out", which is a lie:
    // it implies a retry might succeed, so the model burned turns retrying
    // `subagent` instead of routing around it. Three distinct reasons now get
    // three distinct, accurate messages (see core/config.js ZS.blockedFeedback).
    const bareName = bareToolName(name);
    if (isBlockedTool(name)) {
      if (memToolHidden(bareName)) return `ERROR: '${bareName}' is unavailable - Memory is OFF in this chat. Do NOT call it again; the user turns Memory on with the memory button in the Multi-Script bar. Continue without memory.`;
      if (ZS.blockedFeedback) return ZS.blockedFeedback(bareName, P);
      // Fallback kept only so a stale config.js cannot make this a hard crash.
      if (VISION_TOOLS.has(bareName)) {
        return `ERROR: '${bareName}' is unavailable here - this assistant cannot see images. Do NOT call it again. Inspect the place programmatically instead (e.g. inspect_instance, get_studio_state, search_game_tree, script_read).`;
      }
      return `ERROR: the '${bareName}' command is not available in this environment. Do NOT call it again - complete the task yourself using the other commands (execute_luau, multi_edit, etc.).`;
    }
    // First-class product capability index. This is deliberately compact and
    // appears before giant schemas so every provider sees the real Multi-Script
    // layer even when its context window truncates a long native catalogue.
    if (name === "list_multiscript_capabilities") {
      await ensureTools();
      const c = capabilityCounts();
      const servers = ((A.bridge && A.bridge.servers) || []).filter(x=>!A.chatOnly||!ZSToolRouting.isEngineExecution("catalog",{_server:x.id},A.toolList)||activeEngineIds().includes(x.id)).map((x) => ({ id:x.id, alive:!!x.alive, nativeTools:x.tools || 0 }));
      return `Output of 'list_multiscript_capabilities':
Multi-Script callable capability layer:
- ${c.direct} direct commands (server id: multiscript; callable through the local bridge)
- ${c.skills} reusable skills (discover with ms_list_skills / ms_recommend_skills; load with ms_get_skill). Main skills: code-quality, check-props, check-clean-ui, game-systems, npc-pathfinding, vfx-assets, fix-errors - if the user asks for your main skills, say these in plain words
- ${c.virtual} internal engine specialists (discover with ms_list_virtual_tools; coordinate with ms_studio_director)
- Native MCP servers: ${servers.map((x)=>`${x.id}=${x.nativeTools}${x.alive?" live":" offline"}`).join(", ") || "none"}
Use list_commands {"server":"multiscript"} for every direct command schema. For a real task, call ms_studio_director first so the relevant direct tools, skills, and specialists are selected without dumping all catalogues into context.`;
    }
    // Virtual command: list the MCP server(s) Multi-Script is currently connected
    // to, with each one's REAL per-server health (from the bridge, never the
    // merged tool count - a dead server must not borrow another's numbers).
    if (name === "list_mcp_servers") {
      await ensureTools();
      const servers = ((A.bridge && A.bridge.servers) || []).filter(x=>!A.chatOnly||!ZSToolRouting.isEngineExecution("catalog",{_server:x.id},A.toolList)||activeEngineIds().includes(x.id));
      const lines = servers.length
        ? servers.map((sv) => {
            const engine = ((A.bridge && A.bridge.engines) || []).find((e) => e.id === sv.id);
            const label = sv.id === "roblox" ? "Roblox Studio" : sv.id === "unity" ? "Unity" : `${sv.id} (addon)`;
            const connection = engine && engine.connected === true ? "connected" : engine && engine.connected === false ? "not connected to editor" : "connection unknown";
            return `- ${sv.id}: ${label} - ${sv.alive ? `${sv.tools || 0} commands available; ${connection}` : "offline (no tools)"}`;
          })
        : [A.chatOnly?"- No native engine is available in this session.":"- Native server health is unknown; discover the live catalog before claiming an engine is connected."];
      const c = capabilityCounts();
      const companionTools=sessionExecutionTools().filter(t=>t.server==="roblox-companion");
      if(companionTools.length)lines.push(`- roblox-companion: connected Studio plugin · ${companionTools.length} allowed companion commands. This connection is separate from native Roblox MCP above; use the advertised msrb_* schemas.`);
      const capabilityLine = `- multiscript: ${c.direct} direct commands + ${c.skills} skills + ${c.virtual} internal specialists - always available through the bridge`;
      return (
        `Output of 'list_mcp_servers':\n` +
        `Capability sources (${lines.length + 1}):\n${capabilityLine}\n${lines.join("\n")}\n` +
        `Native engine counts above are controlled by each MCP server and are NOT the whole product. Use list_commands {"server":"multiscript"} for Multi-Script direct schemas, list_multiscript_capabilities for the compact index, or list_commands with an engine id for native schemas.`
      );
    }
    // Virtual command: list available commands with full details. Defaults to
    // the primary Roblox server - a DIFFERENT server's tools only ever show up
    // if the model explicitly asks via {"server": "<id>"} (see list_mcp_servers).
    if(name === "ms_direct_tool_details") {
      await ensureTools();
      const target=String(args.tool||args.tool_name||args.name||args.command||"").trim().replace(/^ms_roblox_run_lua$/, "ms_roblox_run_luau"),server=String(args.server||"");
      if(!target)return 'ERROR: supply params.tool, for example {"command":"ms_direct_tool_details","params":{"tool":"execute_luau"}}. Read list_commands first; do not invent a tool name.';
      const tools=sessionExecutionTools().filter(t=>(t.name===target||bareToolName(t.name)===bareToolName(target))&&(!server||t.server===server));
      if(tools.length===1)return "Output of 'ms_direct_tool_details':\n"+JSON.stringify({available:true,status:"advertised for this session",tool:tools[0],executionRequired:true});
      return "Output of 'ms_direct_tool_details':\n"+JSON.stringify({available:false,status:tools.length?"ambiguous":"unavailable in this session",choices:tools.map(t=>({name:t.name,server:t.server})),mode:A.software?"Build software":A.chatOnly?"Chat studio (engine-free)":"Studio engine",next:"Use list_commands for the current catalog. To work in a live editor choose Studio engine mode. Enable msrb_* tools in the Studio plugin; native execute_luau requires Roblox's own MCP server."});
    }
    if (name === "list_commands" || name === "list_tools") {
      await ensureTools();
      const explicitServer = String(args.server || "").trim();
      if(A.chatOnly&&["roblox","godot","unity","blender"].includes(explicitServer)&&!activeEngineIds().includes(explicitServer))return "ERROR: this engine is isolated from the current Chat studio session. Use the general Multi-Script catalog.";
      const detected = ((A.bridge && A.bridge.engines) || []).filter((e) => activeEngineIds().includes(e.id) && e.connected === true && e.alive);
      const allServerIds = [...new Set(A.toolList.map((t)=>t.server).filter((x)=>x && x!=="zeroscript"))];
      const requestedIds = explicitServer === "multiscript" ? ["zeroscript"] : explicitServer === "all" ? allServerIds : explicitServer ? [explicitServer] : (detected.length ? detected.map((e) => e.id) : ["roblox"]);
      const requested = explicitServer === "multiscript" ? "Multi-Script" : explicitServer === "all" ? "all connected sources" : requestedIds.join(" + ");
      const offlineServerIds = new Set();
      // The MCP proxy keeps advertising Roblox's catalogue even with no Studio
      // attached, so list_commands would hand back the full command list and read
      // as "Roblox is fine" - then every command silently fails. When Roblox is
      // actually unusable, short-circuit the DEFAULT (roblox) listing into a plain
      // "Roblox is down" note that points the model at the other server(s), so it
      // can keep working in degraded mode instead of firing dead Roblox commands.
      if (requestedIds.length === 1 && requestedIds[0] === "roblox") {
        const s = A.bridge || {};
        const srv = s.servers || [];
        const rbx = srv.find((x) => x.id === "roblox");
        const rbxAlive = rbx ? !!rbx.alive : (!!s.mcpAlive || srv.some((x) => x.alive));
        const rbxUsable = !!s.connected && rbxAlive && s.studio !== false;
        if (!rbxUsable) {
          const others = srv.filter((x) => x.id !== "roblox" && x.alive && (x.tools || 0) > 0);
          const otherStr = others.length
            ? `Other connected MCP server(s): ${others.map((x) => x.id).join(", ")}. Call list_mcp_servers, then list_commands with a "server" param to use them for anything that does not need Roblox.`
            : `No other MCP server is connected right now.`;
          offlineServerIds.add("roblox");
          diag("commands.nativeOffline", { server:"roblox", alternatives:others.map((x)=>x.id) });
        }
      }
      const known = new Set(A.toolList.map((t) => t.server).filter(Boolean));
      // Tools from a bridge that doesn't tag "server" yet (old version) have no
      // .server field at all - treat those as the primary server rather than
      // hiding everything.
      // Built-in Multi-Script skills/critic tools are useful with every engine,
      // so include them beside the requested server's own catalogue.
      const scoped = sessionExecutionTools().filter((t) => {
        const server = t.server || "roblox";
        if(isLocalUltraTool(t.name)&&executionEffort!=="ultra")return false;
        if(A.chatOnly&&!A.software&&ZSToolRouting.isEngineExecution(t.name,{},A.toolList))return false;
        if (!A.software && isSoftwareTool(t.name)) return false;
        if (A.software) return isLocalProgressTool(t.name) || isLocalUltraTool(t.name) || (server === "zeroscript" && isSoftwareTool(t.name)) || softwareAllowsTool(t.name, server);
        return server === "zeroscript" || (server === "roblox-companion" && requestedIds.includes("roblox")) || (requestedIds.includes(server) && !offlineServerIds.has(server));
      });
      if (!A.toolList.length) return `Output of '${name}':\nNo commands available - the bridge or Roblox Studio may be offline.`;
      if (!scoped.length) {
        return `Output of '${name}':\nERROR: no server named "${requested}" is connected. Connected servers: ${[...known].join(", ") || "roblox"}. Call list_mcp_servers to check.`;
      }
      const fmtTool = (t) => {
        const props = (t.inputSchema && t.inputSchema.properties) || {};
        const req = new Set((t.inputSchema && t.inputSchema.required) || []);
        // Two buckets: simple scalar params get packed onto ONE compact line;
        // params that need real explanation (array-of-object shape, or a long
        // description) keep their own line so nothing structurally important
        // gets flattened away (that per-item shape is what fixed "Unknown …
        // action: nil" bugs on user_keyboard_input/user_mouse_input).
        const compact = [];
        const detailed = [];
        for (const [k, v] of Object.entries(props)) {
          const items = v.items && typeof v.items === "object" ? v.items : null;
          const itemProps = items && items.properties;
          const mark = req.has(k) ? "" : "?";
          if (v.type === "array" && itemProps) {
            const itemReq = new Set(items.required || []);
            const fields = Object.entries(itemProps).map(([ik, iv]) => {
              const en = Array.isArray(iv.enum) && iv.enum.length <= 12 ? `(${iv.enum.join("|")})` : (iv.type || "any");
              return `${ik}${itemReq.has(ik) ? "" : "?"}:${en}`;
            });
            detailed.push(`    ${k}${mark}: array [each item: {${fields.join(", ")}}]${v.description ? " - " + v.description : ""}`);
          } else if (v.description && v.description.length > 45) {
            detailed.push(`    ${k}${mark}: ${v.type || "any"} - ${v.description}`);
          } else {
            const ty = Array.isArray(v.enum) && v.enum.length <= 16 ? `(${v.enum.join("|")})` : (v.type || "any");
            compact.push(`${k}${mark}:${ty}${v.description ? ` "${v.description}"` : ""}`);
          }
        }
        const paramLines = [compact.length ? `    ${compact.join(", ")}` : "", ...detailed].filter(Boolean).join("\n");
        // Tested usage note for the error-prone commands - kept full-length
        // (these are validated fixes for real bugs, not filler).
        // Tested usage note for the command - the Roblox notes, or the engine
        // registry's notes for Godot/Unity/Blender/other (see ZS.toolNote).
        const note = ZS.toolNote ? ZS.toolNote(bareToolName(t.name)) : ZS.TOOL_NOTES[bareToolName(t.name)];
        const noteStr = note ? `\n    ⚠ ${note}` : "";
        const requiredLine = req.size ? `\n    REQUIRED params: ${[...req].join(", ")}. Include every one in params.` : "\n    No required params; optional fields use documented defaults.";
        return `${t.name}: ${(t.description || "").split("\n")[0]}${requiredLine}${paramLines ? "\n" + paramLines : ""}${noteStr}`;
      };
      // 6.26: filters + a compact direct-tool index. The full catalogue (241+
      // Multi-Script schemas + every native engine) is ~120k chars - more than
      // ChatGPT/Claude/Gemini accept in one message, so their adapters cut the
      // MIDDLE out (native engine schemas included). Providers that declare a
      // resultCharBudget, or any listing that would be enormous, now get every
      // native schema in full plus the direct tools as a names-only index; exact
      // schemas are one call away via "names" / "query".
      const wantNames = (Array.isArray(args.names) ? args.names : String(args.names || "").split(",")).map((x) => String(x).trim()).filter(Boolean);
      const query = String(args.query || "").trim().toLowerCase();
      let detailedTools = scoped;
      if (wantNames.length) detailedTools = scoped.filter((t) => wantNames.includes(t.name) || wantNames.includes(bareToolName(t.name)));
      else if (query) detailedTools = scoped.filter((t) => `${t.name} ${t.description || ""}`.toLowerCase().includes(query));
      if ((wantNames.length || query) && !detailedTools.length) {
        return `Output of '${name}':\nERROR: no command matched ${wantNames.length ? `names ${wantNames.join(", ")}` : `query "${query}"`} on ${requested}. Call list_commands without names/query to see the index.`;
      }
      let indexBlock = "";
      const fullLen = (!wantNames.length && !query) ? detailedTools.reduce((n, t) => n + 120 + JSON.stringify((t.inputSchema && t.inputSchema.properties) || {}).length, 0) : 0;
      const compactDirect = !wantNames.length && !query &&
        (Number(P.resultCharBudget) > 0 || fullLen > 16000);
      if (compactDirect) {
        // Bootstrap with discovery/retrieval schemas, not a mandatory workflow.
        // Every other direct tool stays in the index with exact schemas on demand.
        const ESSENTIAL = new Set(["ms_ultra_manual", "ms_roblox_docs", "ms_forge", "ms_roblox_omni", "ms_obsidian", "ms_find_tool", "ms_get_skill"]);
        const direct = detailedTools.filter((t) => t.server === "zeroscript");
        detailedTools = detailedTools.filter((t) => t.server !== "zeroscript" || ESSENTIAL.has(t.name));
        const groups = {};
        for (const t of direct) {
          if (ESSENTIAL.has(t.name)) continue;
          const m = /^ms_(roblox|unity|godot|blender|memory|native|surface|engine)_/.exec(t.name);
          const g = m ? m[1] : "general";
          (groups[g] = groups[g] || []).push(t.name);
        }
        indexBlock = `\n\nMULTI-SCRIPT DIRECT COMMAND INDEX (names only, so this result stays small). Not sure which command does what you need? Call ms_find_tool with {"query":"<what you want to do>"}. Get exact parameters before calling one: {"command":"list_commands","params":{"server":"multiscript","names":["ms_example_a","ms_example_b"]}} or {"command":"list_commands","params":{"server":"multiscript","query":"audio"}}.\n` +
          Object.entries(groups).map(([g, names]) => `- ${g} (${names.length}): ${names.join(", ")}`).join("\n");
      }
      const lines = detailedTools.map(fmtTool);
      const c = capabilityCounts();
      const directShown = scoped.filter((t)=>t.server === "zeroscript").length;
      const nativeShown = scoped.length - directShown;
      const offlineNote = offlineServerIds.size ? `\nNative unavailable now: ${[...offlineServerIds].join(", ")}; its cached commands were hidden to prevent false execution. Multi-Script direct commands remain callable.` : "";
      return `Output of '${name}':\nMULTI-SCRIPT CAPABILITY INDEX — ${c.direct} direct commands, ${c.skills} skills, ${c.virtual} internal specialists. These are real callable/retrievable capability layers and are separate from native MCP command counts. Use ms_studio_director for task-specific coordination, ms_list_skills/ms_get_skill for skills, and ms_list_virtual_tools for specialists.${offlineNote}\n\n${requested} catalogue: ${directShown} Multi-Script direct + ${nativeShown} live native = ${scoped.length} callable commands shown.\n\n${lines.join("\n\n")}${indexBlock}`;
    }
    if (A.toolNames.size && !knownTool(name)) {
      return ZS.FEEDBACK.unknownTool(name, [...A.toolNames]);
    }
    // The Roblox MCP REQUIRES datamodel_type on execute_luau (enum Edit/Client/
    // Server). The ###LUA### parser already fills it in, but the model may also
    // write the JSON form without it - default to "Edit" so the call never
    // soft-fails with "datamodel_type is required".
    if (bareName === "execute_luau" && !args.datamodel_type) args.datamodel_type = "Edit";
    // The player-input tools only run against the Client datamodel (play mode) and
    // "Client" is the sole allowed value, so default it when the model omits it -
    // it can only be right. (It still needs the game RUNNING; that's documented.)
    if ((bareName === "user_keyboard_input" || bareName === "user_mouse_input") && !args.datamodel_type)
      args.datamodel_type = "Client";
    const timeout = 120000; // Native writes may legitimately take longer than 20 seconds.
    // Hard watchdog: even if the background worker never answers, the loop
    // gets a definitive result and continues.
    const hardCap = new Promise((res) =>
      setTimeout(() => res({ ok: false, kind: "timeout", error: "no response from the extension worker" }), timeout + 30000));
    // Stop watcher: a blocking tool (e.g. wait_job_finished) would otherwise keep
    // the loop awaiting the bridge for up to minutes, leaving the input locked and
    // the Stop button stuck. When the user halts (A.stop), abandon the wait within
    // ~150ms so the loop breaks and its finally unlocks everything. The in-flight
    // bridge call may still finish in the background; its result is just ignored.
    let stopTimer;
    const stopWatch = new Promise((res) => {
      stopTimer = setInterval(() => { if (A.stop) res({ ok: false, kind: "stopped" }); }, 150);
    });
    const serverHint = String(args._server || "").trim();
    if (serverHint) delete args._server;
    const route = ZSToolRouting.resolve(name, serverHint, A.toolList);
    if (!route.ok && route.reason === "ambiguous") {
      return `ERROR: '${name}' exists on multiple engines. Retry with params._server set to one of: ${route.servers.join(", ")}.`;
    }
    if (!route.ok && route.reason === "server") {
      return `ERROR: '${name}' is not advertised by engine '${serverHint}'. Available on: ${route.servers.join(", ") || "none"}. Call list_commands for that server.`;
    }
    const routedName = route.ok ? route.name : name;
    // ── Surface vision: tools the EXTENSION must answer, not the bridge ──
    // ms_surface_read/type/open/focus need chrome.tabs + chrome.scripting, which
    // only the service worker has. They are advertised by the bridge (so the
    // model sees one coherent catalogue) but must never be forwarded to it. Also
    // ms_surface_list is special: the bridge answers the WINDOW half, and we
    // merge in the TAB half here so one call returns both.
    let r;
    if (routedName === "ms_surface_list") {
      const ss = getSurfaceSettings();
      const [winHalf, tabHalf] = await Promise.all([
        ss.windows
          ? Promise.race([bg({ type: "call_tool", name: "ms_surface_list", arguments: args, timeout }), hardCap])
          : Promise.resolve(null),
        ss.tabs
          ? bg({ type: "surface_list", host: args.host, include_icons: false })
          : Promise.resolve(null),
      ]);
      r = mergeSurfaceList(winHalf, tabHalf);
    } else if (routedName === "ms_surface_read" || routedName === "ms_surface_type" ||
               routedName === "ms_surface_open" || routedName === "ms_surface_focus" ||
               routedName === "ms_surface_close") {
      // Two layers, outermost first. The TRUST level decides whether this class
      // of action is reachable at all; the per-feature grants below then narrow
      // it. Enforced here, the single choke point every surface call passes.
      const verb = routedName.slice("ms_surface_".length);
      const trustCap = (verb === "read" || verb === "list") ? "browser.tabs.read" : "browser.tabs.drive";
      const trust = canDo(trustCap);
      if (!trust.allowed) {
        return `ERROR: refused by the trust level. ${trust.reason}. Raise the trust level in Multi-Script settings if you want this, then retry.`;
      }
      const ss = getSurfaceSettings();
      const needsRead = verb === "read";
      const needsType = verb === "type";
      const blocked =
        (needsRead && !ss.allowRead) ||
        (needsType && !ss.allowType) ||
        (!needsRead && !needsType && !ss.tabs);
      if (blocked) {
        const why = needsRead ? "reading a tab's text" : needsType ? "typing into a tab" : "seeing browser tabs";
        return `ERROR: the user has turned off "${why}" in Multi-Script settings, so this call is refused. Ask them to enable it in the Surface vision panel if they want it, then retry.`;
      }
      r = await Promise.race([bg({ type: `surface_${verb}`, ...args }), hardCap, stopWatch]);
      // bg() resolves with the worker's response object directly; wrap it in the
      // {ok,text} shape the rest of runTool expects so downstream formatting is
      // identical to a bridge result.
      if (r && r.ok !== false && r.error === undefined) {
        r = { ok: true, text: JSON.stringify(r, null, 2) };
      } else if (r) {
        r = { ok: false, error: r.error || "surface call failed" };
      }
    } else if (routedName === "ms_app_list" || routedName === "ms_app_snapshot" || routedName === "ms_app_read_window") {
      // Same two layers for the desktop half, which the bridge answers.
      const trust = canDo("desktop.read");
      if (!trust.allowed) {
        return `ERROR: refused by the trust level. ${trust.reason}. Raise the trust level in Multi-Script settings if you want this, then retry.`;
      }
      const ss = getSurfaceSettings();
      if (!ss.windows) {
        return `ERROR: the user has turned off desktop-window visibility in Multi-Script settings, so this call is refused. Ask them to enable it in the Surface vision panel if they want it, then retry.`;
      }
      r = await Promise.race([bg({ type: "call_tool", name: routedName, arguments: args, timeout, resultLimit: ZS.limits ? ZS.limits.bridgeLimit() : null }), hardCap, stopWatch]);
    } else {
      // Replay guard: an empty-old_string multi_edit APPENDS / creates, so applying the
      // very same call twice doubles the text ("print(1)print(1)"). If this exact call
      // succeeded moments ago, do not apply it again - say so instead.
      const editFp = appendEditFingerprint(routedName, args);
      if (editFp) {
        const seen = (A.recentEdits || {})[editFp];
        if (seen && Date.now() - seen < 60000) {
          clearInterval(stopTimer);
          diag("edit.replayBlocked", { name: routedName, agoMs: Date.now() - seen });
          return `Output of '${name}':\nSkipped: this exact edit (same file, same text, empty old_string) was already applied ${Math.round((Date.now() - seen) / 1000)}s ago, and applying it again would duplicate the content. Read the script (script_read) to confirm it is there. If you really want it twice, change the text.`;
        }
      }
      r = await Promise.race([bg({ type: "call_tool", name: routedName, arguments: args, timeout, resultLimit: ZS.limits ? ZS.limits.bridgeLimit() : null }), hardCap, stopWatch]);
      if (editFp && r && r.ok) { (A.recentEdits = A.recentEdits || {})[editFp] = Date.now(); }
    }
    clearInterval(stopTimer);
    if (r && r.kind === "stopped") return "(stopped by user)";
    if (!r) return bridgeOfflineFeedback();
    // Transport success is not execution success. Preserve explicit native
    // failure flags as ERROR feedback so the model must address the failure.
    if(r.ok&&(r.isError===true||(typeof MSStudio!=="undefined"&&MSStudio.structuredToolFailure(r.text)))) {
      r={...r,ok:false,error:"Tool reported execution failure: "+String(r.text||"native isError flag").slice(0,8000)};
    }
    // The MCP server answers SUCCESSFULLY (ok:true) when no Studio is attached
    // (Studio closed / no place / MCP option disabled) - with an explanatory
    // text instead of a result. Surface it as a proper environment ERROR so the
    // model stops and tells the user, instead of treating it as tool output.
    if (r.ok && /Unable to find an active Studio instance|previously active Studio has disconnected/i.test(r.text || "")) {
      ui.banner("warn", "Roblox Studio is not connected",
        "Open your place in Roblox Studio and enable the MCP server (Assistant AI → … → Manage MCP Servers → Enable Studio as MCP Server), then try again.");
      return ZS.FEEDBACK.studioOffline;
    }
    // The Roblox MCP reports missing/invalid required parameters as a SUCCESS
    // whose text is just the complaint (e.g. "datamodel_type is required").
    // Re-shape those into a real ERROR so the model corrects the call instead
    // of misreading it as tool output.
    if (r.ok && r.text && /^[\w .'"-]{0,60}\bis (required|not available|invalid)\b[\w .'"-]{0,80}$/i.test(r.text.trim())) {
      const complaint = r.text.trim();
      // studio_id deserves a bespoke answer. It is required on EVERY place-scoped
      // Roblox command, so pointing the model at list_commands (a giant catalogue
      // that gets truncated on arena.ai/DeepSeek) is what made it flail and start
      // emitting prose/markup - the non-JSON error in the user's screenshot. Name
      // the parameter, say WHY it only bites sometimes, and give the fix.
      if (/studio_id/i.test(complaint)) {
        return ZS.FEEDBACK.studioId(name, complaint, A.studios.map((s) => s.id), []);
      }
      return `ERROR calling '${name}': ${complaint}.\nA required or invalid parameter - check the command's parameters with list_commands, fix the call and retry.`;
    }
    // The Roblox MCP also reports Luau PARSE/RUNTIME errors as a SUCCESS whose
    // text is the executor's own stack trace ("…ExecuteLuauTool:139: …
    // CommandExecution:54: <real error>" - validated live). Genuine script
    // output never contains those internal paths. Re-shape into a real ERROR so
    // the model gets the fix-it hints below and the chip settles red, not ✓
    // green - and strip the internal frames so only the useful part remains.
    if (r.ok && bareName === "execute_luau" && r.text &&
        /\b(?:ExecuteLuauTool|CommandExecution):\d+:/.test(r.text)) {
      r = { ok: false, error: r.text.replace(/^(?:\S*(?:ExecuteLuauTool|CommandExecution):\d+:\s*)+/, "").trim() || r.text };
    }
    if(!r.ok && /(?:allows at most|code.{0,30}(?:too long|limit|exceed)|source.{0,30}(?:limit|exceed)|local registers|register limit|too many local)/i.test(String(r.error||r.text||""))) {
      return "ERROR calling '"+name+"': "+String(r.error||r.text)+"\nNo source should be clipped or arbitrary code split between executions. For persistent Roblox scripts use Full-tier msrb_replace_script; large sources are staged and committed once through the plugin. If source transfer is disabled, enable it in Studio → Multi-Script → Toolset. Native execute_luau limits remain controlled by Roblox. Compiler local/register limits require smaller functions or ModuleScripts, not retries of the same giant chunk.";
    }
    if (r.ok) {
      if (r.images && r.images.length && !P.supportsVision) {
        // This provider's model cannot take images. Instead of failing (the old
        // behaviour made screen_capture / frame / render tools useless on Notion
        // AI, ChatGPT-free, text-only Qwen/DeepSeek ...) show the capture to the
        // USER in the side popup and hand the model a text digest of it.
        try { ui.showImages(r.images, name); } catch {}
        rememberImageTool(name);
        let digest = "";
        try { digest = ZS.imageDigest ? await ZS.imageDigest(r.images) : ""; } catch {}
        diag("images.digest", { count: r.images.length, chars: digest.length });
        const cap = r.text && r.text.trim() ? r.text.trim() + "\n" : "";
        return `Output of '${name}':\n${cap}${digest || `${r.images.length} image(s) captured, but this assistant cannot view images and the image could not be summarised. Use a text command (inspect_instance, search_game_tree, get_console_output) for the same information.`}`;
      }
      if (r.images && r.images.length) {
        // Show the capture in a left-hand Multi-Script popup (from the in-memory
        // base64 - simple and reliable on every site; no DOM-embedded preview).
        ui.showImages(r.images, name);
        // Do NOT attach the image here: submitAndGetBase/typeAndSend types the
        // feedback text into the editor LATER, and on providers whose editor is
        // rebuilt via select-all + insertText (e.g. Gemini's setEditorText),
        // that wipe severs the site's internal binding between "pending upload"
        // and "message being composed" - the file then sits in the composer
        // forever while only the text goes out (validated live: Gemini kept
        // the file attached+unsent across the whole turn). Stash the images and
        // let the provider attach them as the LAST step, right before the send
        // click, so nothing mutates the editor afterward.
        A.pendingImages = r.images;
        diag("images.stashed", { count: r.images.length });
        const caption = r.text && r.text.trim()
          ? r.text.trim()
          : `${r.images.length} image(s) captured.`;
        return `Output of '${name}':\n${caption}\n(The image is attached to THIS message - you can see it directly. Analyse it and continue.)`;
      }
      const text = r.text && r.text.length ? r.text : "(tool returned an empty result)";
      // Learn the connected Studio ids from ANY answer that mentions them
      // (list_roblox_studios is the direct one; get_studio_state and others also
      // carry the id). Passive, so we never spend an extra turn asking, and it is
      // what lets the studio_id fill-in above work on the very next call.
      if (typeof ZSEngine !== "undefined" && ZSEngine.studiosFromBody) {
        const found = ZSEngine.studiosFromBody(text);
        if (found.length) {
          const before = A.studios.length;
          for (const s of found) if (!A.studios.some((x) => x.id === s.id)) A.studios.push(s);
          if (A.studios.length !== before) {
            diag("studios.learned", { ids: A.studios.map((s) => s.id) });
          }
        }
      }
      const reviewNote=await codeReviewNote(bareName,args);
      return `Output of '${name}':\n${text}${reviewNote}`;
    }
    // Orphaned content script - a page reload is the only cure, so say exactly
    // that instead of blaming the bridge (see bg / isContextInvalidated).
    if (r.kind === "stale-extension") {
      ui.banner("warn", "Reload this page",
        "Multi-Script was updated or reloaded while this tab was open, so this page is running an " +
        "old copy of it and commands can no longer run. Reload the page (F5) to reconnect - your " +
        "bridge and Roblox Studio are unaffected.");
      diag("bridge.staleExtension", { name, error: r.error });
      return ZS.FEEDBACK.staleExtension;
    }
    if (r.kind === "disconnected") return bridgeOfflineFeedback();
    if (r.kind === "timeout") {
      return `ERROR: tool '${name}' timed out after ${name === "execute_luau" ? 20 : 120}s.\n${r.error}\nTry a shorter/simpler call or check that Roblox Studio is open and responsive.`;
    }
    if (name === "execute_luau") {
      const err = r.error || "";
      // "Failed to parse command code" is StudioMCP's GENERIC parse rejection: an
      // empty/mis-marked block is only ONE of its causes. The others are ordinary
      // Luau syntax errors and - seen live on Meta AI 2026-08-13 - code that is
      // syntactically fine but too big for the parser: a `return 1+1+1+…` chain
      // ran at ~500 terms (1006 chars) and was rejected at ~1000 (2006 chars).
      // Telling the model its block was empty when we DID send it a full code
      // string sends it to fix something that isn't broken; it retries the same
      // payload and fails again (the reported spam of parse errors). Only give the
      // marker advice when the code we actually sent really was empty.
      const luaCode = args.code || "";
      const hint = /R255|G255|B255/.test(err)?"Color3 exposes R, G and B in 0–1. Use math.round(color.R * 255) etc. for integer channels; Color3.fromRGB accepts 0–255 input. Do not retry the invalid member.":
        /lacking capability|cannot (read|write).*Technology|RobloxScript/.test(err)?"This property is restricted in this execution context. Guard optional reads with pcall, omit the inaccessible field and preserve other observed results. Verify current LightingStyle/PrioritizeLightingQuality support in official docs. Do not bypass capabilities, retry the restricted access, or infer that the place is empty.":err.includes("Failed to parse command code")
        ? !luaCode.trim()
          ? "Your code block was empty or the marker was wrong. Use exactly ###LUA### (three hashes) - never ###LUA---. The code must be between ###LUA### and ###END_LUA###."
          : `Roblox refused to PARSE the code (${luaCode.length} chars sent, so it was not empty). Either the Luau syntax is invalid, or the code is too large/complex for the parser - a single huge expression or a very long script can be rejected outright. Check the syntax first; if it looks correct, split the work into several smaller calls.`
        : err.includes("attempt to") || err.includes("nil value")
          ? "Lua runtime error. Check that the API you are calling exists (use game:GetService() to access services). Make sure you use 'return' to output values, not 'print()'."
          : "Check your Lua syntax, make sure you use 'return' to output values (not 'print()'), and that all APIs you call exist in the current Roblox Studio context.";
      const reviewNote=await codeReviewNote('execute_luau',args);
      return `ERROR in execute_luau: ${err}\n\n${hint}${reviewNote}\n\nFix the code and retry.`;
    }
    // The BRIDGE's own schema validator rejected the arguments before the tool
    // ever ran. Its message is precise but easy to skim past, and it arrives as
    // ok:false - a DIFFERENT path from the server's ok:true complaint handled
    // above, which is why a bare "Read the error carefully" left the model going
    // in circles and producing malformed JSON instead of fixing one field.
    //
    // Seen live: "multi_edit: invalid parameters: parameters.edits[0].old_string
    // is required". The model needed three things it did not have: confirmation
    // that the tool name was fine, the exact nested PATH it dropped, and the full
    // required SHAPE to copy. Give it all three, plus the template we already ship
    // for that tool - the shape is what a model actually copies from.
    const vErr = String(r.error || "");
    // First line only: the bridge appends SIGNATURE / MINIMAL CALL lines after it.
    const badParam = /invalid parameters:\s*([^\n]+)/i.exec(vErr);
    if (badParam) {
      const detail = badParam[1].trim();
      // Greedy on purpose: the path can be long and dotted
      // ("parameters.edits[0].old_string"), and a lazy quantifier stops at the
      // first word boundary, truncating it to "parameters". Require the WHOLE
      // remainder of the message to be the "is required" clause so we never
      // swallow unrelated text.
      const missing = /^(.+?)\s+is required[.!]?$/i.exec(detail);
      const tpl = ZS.toolNote ? (typeof ZSEngine !== "undefined" && ZSEngine.templateFor
        ? ZSEngine.templateFor(bareToolName(name)) : "") : "";
      const shapeLine = tpl
        ? `\nThe required shape for '${bareToolName(name)}' is:\n${tpl}`
        : "";
      if (missing) {
        const path = missing[1].trim();
        // Name the exact missing field, and make the nested case explicit - a
        // model that omitted `edits[0].old_string` needs to know the field lives
        // INSIDE each object of the array, not at the top level.
        //
        // NOTE the regex is NOT anchored to the start of the path: the real
        // message is "parameters.edits[0].old_string is required", i.e. the
        // array access sits in the middle. A ^-anchored pattern silently failed
        // to recognise every genuine nested error (first shipped 6.17.1 and
        // caught by tests/test_required_param_contract.js).
        const nested = /(?:^|\.)([A-Za-z0-9_]+)\[\d+\]\.([A-Za-z0-9_]+)$/.exec(path);
        const where = nested
          ? `'${nested[2]}' must be present on EVERY object inside the '${nested[1]}' array - it is a nested field, not a top-level one.`
          : `'${path}' must be present.`;
        return `ERROR calling '${bareToolName(name)}': the command was NOT run - its arguments were rejected before execution ` +
          `because ${path} is required.\n${where}\n` +
          `Do NOT rename the command and do NOT change anything else: re-send the SAME command with '${path}' added to the ` +
          `params you already wrote (keep every other value as it was).${shapeLine}\n` +
          `Raw: ${vErr}`;
      }
      return `ERROR calling '${bareToolName(name)}': the command was NOT run - its arguments were rejected: ${detail}.\n` +
        `Fix only what the message names, then re-send the SAME command.${shapeLine}\nRaw: ${vErr}`;
    }
    return `ERROR calling '${name}': ${r.error}\nRead the error carefully, fix the call or try a different approach.`;
  }

  function argSummary(call) {
    if (!call) return "";
    if (call.tool === "execute_luau") {
      const code = (call.arguments && call.arguments.code) || "";
      const first = code.split("\n").map((s) => s.trim()).filter(Boolean)[0] || "";
      return first.slice(0, 46);
    }
    const a = call.arguments || {};
    const k = Object.keys(a)[0];
    if (!k) return "";
    let v = String(a[k]);
    if (v.length > 34) v = v.slice(0, 31) + "…";
    return `${k}: ${v}`;
  }

  // An MCP tool can report its OWN failure as a NORMAL result ("Output of '…':
  // Error executing code: …") instead of our ERROR wrapper - so a
  // startsWith("ERROR") test alone paints a FAILED call ✓ green and shows the
  // error as its summary (seen live on Blender's execute_blender_code, and it
  // will hit EVERY future MCP server the same way). Treat a result whose FIRST
  // line opens with an error lead-in as failed too. Deliberately PHRASE-based,
  // not the bare words "error"/"failed", so a genuine success line like
  // "Failed: 0" / "Error count: 0" is NOT misread as a failure.
  const BODY_ERR_RE =
    /^\s*(error executing|error:|erreur|exception|traceback|communication error|failed to|could ?not|cannot |unable to|fatal)\b/i;
  const stripOutputPrefix = (feedback) => feedback.replace(/^Output of '[^']*':\n?/, "");
  function bodyLooksFailed(feedback) {
    if (!feedback || feedback.startsWith("ERROR")) return false; // wrapper already flags it
    const body=stripOutputPrefix(feedback);
    const first = body.split("\n").map((s) => s.trim()).find(Boolean) || "";
    return BODY_ERR_RE.test(first)||(typeof MSStudio!=="undefined"&&MSStudio.structuredToolFailure(body));
  }
  // True failure = OUR wrapper prefix OR an MCP tool's in-body error lead-in.
  const zsCue = (kind) => { try { if (typeof ZSSound !== "undefined") ZSSound.play(kind); } catch (_) {} };
  const feedbackIsError = (feedback) => feedback.startsWith("ERROR") || bodyLooksFailed(feedback);

  // Some tools answer with raw JSON on one line, and a 44-char slice of it makes
  // a chip that says nothing: list_roblox_studios read
  // `{"studios":[{"id":"8521cfad-f8d9-46f4-8cbe-2`. Summarise the SHAPE instead,
  // in the same spirit as the boot chip's "25 commands". Returns null when the
  // body isn't JSON, so plain-text outputs keep their first line unchanged.
  function jsonSummary(body) {
    if (!/^[[{]/.test(body) || body.length > 200000) return null;
    let v;
    try { v = JSON.parse(body); } catch { return null; }
    if (Array.isArray(v)) return `${v.length} item${v.length === 1 ? "" : "s"}`;
    if (!v || typeof v !== "object") return null;
    const keys = Object.keys(v);
    // The common MCP shape: one wrapper key holding the list. Its name is already
    // plural ("studios", "scripts"), so it reads correctly as-is - just drop the
    // trailing "s" when there is exactly one, so it says "1 studio".
    if (keys.length === 1 && Array.isArray(v[keys[0]])) {
      const n = v[keys[0]].length;
      const word = n === 1 ? keys[0].replace(/s$/, "") : keys[0];
      return `${n} ${word}`;
    }
    // Otherwise show the scalar fields - that's what a human would read off.
    const scalars = keys
      .filter((k) => v[k] === null || typeof v[k] !== "object")
      .map((k) => `${k}: ${v[k]}`);
    if (scalars.length) return scalars.join(", ").slice(0, 44);
    return `${keys.length} field${keys.length === 1 ? "" : "s"}`;
  }

  function outSummary(feedback) {
    if (!feedback) return "";
    const isErr = feedbackIsError(feedback);
    const body = stripOutputPrefix(feedback).trim();
    if (!body) return "";
    // Errors are prose and read fine as-is; only reshape successful JSON.
    if (!isErr) { const j = jsonSummary(body); if (j) return j; }
    const all = body.split("\n").map((l) => l.trim()).filter(Boolean);
    const lines = all.length;
    // On SUCCESS, skip a leading non-fatal warning/note some MCP tools print
    // before the real status so the chip shows the useful line, not the noise.
    let first = all[0] || "";
    if (!isErr && lines > 1 && /^(warning|warn|note|deprecat|info)\b/i.test(first)) {
      first = all.find((l) => !/^(warning|warn|note|deprecat|info)\b/i.test(l)) || first;
    }
    first = first.slice(0, 44);
    if (isErr) return first;
    return lines > 1 ? `${first} · ${lines} lines` : first;
  }

  // Full args / code, shown in a tool chip's expandable body.
  function callBody(call) {
    const a = call.arguments || {};
    if (call.tool === "execute_luau") return (a.code || "").trim();
    try { return JSON.stringify(a, null, 2); } catch { return String(a); }
  }

  // ════════════════════════════════════════════════════════════════════════
  //  AGENTIC LOOP
  // ════════════════════════════════════════════════════════════════════════
  async function agentLoop(base,{preserveErrors=false}={}) {
    if (A.running) return;
    if(!readTaskProgress())beginTaskProgress(A.lastUserText||'Continue the current task');
    A.running = true;observeTaskProgress('start');
    A.executionTrace=typeof MSExecution!=='undefined'?MSExecution.create(A.lastUserText,executionEffort,sessionExecutionTools(),{engineFree:A.chatOnly&&!A.software,workspace:A.software}):null;
    if(!preserveErrors)A.taskToolErrors=0;A.taskOutcome="working";A.taskOutcomeChat=P.conversationKey();
    A.resumeArmed = false; // loop now owns the turn; drop the regenerate grace
    A.stop = false;
    A.stopping = false; // clean slate: never inherit a stale "Stopping…" from a
                        // Stop click that landed before this loop actually started
    A.loopKey = null; // pinned by syncSessionState once this chat has an id + content
    const memUser = String(A.lastUserText || A.memLastUser || "");
    A.memLastUser = "";
    const memTools = [];
    let truncCount = 0;
    let contextContinuations = 0;
    const MAX_TRUNC = 6;
    // ── Recovery bookkeeping (see ZSResilience) ─────────────────────────────
    // failAttempts counts retries already spent on the CURRENT failure streak;
    // failStreak counts consecutive failures of any kind. Both reset the moment
    // a turn produces something usable (a tool call or a real answer), so a
    // long healthy session never accumulates toward the give-up threshold.
    let failAttempts = 0;
    let failStreak = 0;
    const resetFails = () => { failAttempts = 0; failStreak = 0; };
    // Shared handler for a recoverable failure. Returns true when the loop
    // should continue (a retry was sent), false when it must stop.
    const recoverFrom = async (kind, extra = {}) => {
      const d = ZSResilience.decide(rlevel(), kind, { attempt: failAttempts, consecutive: failStreak, ...extra });
      diag("recover.decide", { kind, action: d.action, reason: d.reason, attempt: failAttempts, streak: failStreak, delayMs: d.delayMs, level: d.level });
      if (d.action !== "retry" && d.action !== "resend") return false;
      failAttempts++;
      failStreak++;
      A.lastErrorAt = Date.now(); // arms the pacing engine's error cooldown
      const label = kind === "parse_error" ? "Malformed command"
        : kind === "timeout" ? "No response"
        : kind === "busy" ? "Site busy"
        : "Empty reply";
      ui.toast(`${label} · recovering (${failAttempts}/${d.attemptsLeft + failAttempts})…`);
      if (d.delayMs > 0 && !(await paceSleep(d.delayMs))) return false;
      if (A.stop) return false;
      const text = d.action === "resend" ? (extra.raw != null ? extra.raw : "") : d.feedback;
      if (text) { base = await submitAndGetBase(text); return A.lastSendOk; }
      return false;
    };
    // Re-send the command list after this many successful tool calls. Kept high
    // so the reminder does not bloat the context too often.
    const REMIND_TOOLS_EVERY = 20;
    ui.showStop(true);
    P.setInputLock(true); // prevent user from typing while the agent is active
    ui.inputCover(true);  // keep the "Agent is working" cover up for the WHOLE loop
    diag("loop.start", { base });
    // ── Prompt enhancer ─────────────────────────────────────────────────────
    // The enhancer no longer sends a second "brief" after the user's message.
    // It gates the SEND itself (see gateEnhancedSend near installSendHooks): the
    // user's Enter/Send is held, they choose enhanced vs original, and exactly
    // one of the two is sent.
    try {
      while (!A.stop) {
        if (A.lastSendOk === false) { diag("loop.unsentTurn"); break; }
        // Gate the WHOLE cycle on tab visibility. We only advance - read the
        // reply, PARSE it, EXECUTE a tool, inject the result - while the AI tab
        // is the FOREGROUND tab of its Edge window. document.visibilityState
        // (mirrored by document.hidden) is the right signal, NOT window focus:
        //  - Edge loses OS focus but the AI tab stays the active tab (user is
        //    working in Roblox Studio) -> still "visible" -> the agent keeps
        //    running, exactly as wanted.
        //  - The AI tab is backgrounded (another tab in front) or the window is
        //    minimized -> "hidden" -> pause here. Background tabs throttle
        //    rendering/timers, which made DOM reads unreliable (misparse,
        //    duplicate sends - see the send-side guard in submitAndGetBase).
        // Parking here means we never START a parse/exec cycle off-screen; the
        // send step re-checks too, so a switch-away mid-generation is covered.
        if (pageHidden() && !A.stop) {
          diag("loop.waitVisible");
          ui.inputCover(true); // keep the "Agent is working" cover up while parked
          if (!(await waitVisible()) || A.stop) break; // park (no cap) until foreground; break only on user stop
          diag("loop.visibleAgain");
        }
        // A bot-check issued mid-session (Arena re-issues them) blocks the whole
        // page. Park here - the user clears it, and the loop continues on its own
        // instead of dying. See awaitHumanVerification.
        if (P.captchaPresent && P.captchaPresent() && !A.stop) {
          if (!(await awaitHumanVerification("loop"))) break;
          ui.inputCover(true);
        }
        const res = await waitSiteSafe(base);
        if(res.kind==="provider_error"){
          A.responseFailure={chat:P.conversationKey(),base,text:res.text};A.taskOutcome="provider-failed";A.lastSendOk=false;A.userStopped=true;
          coworkQueue?.pause("Provider response failed. Use the site's Retry, then Resume response in Multi-Script; queued requests remain paused.");
          ui.banner("warn",`${P.displayName} response failed · task unverified`,"The provider stopped generating. Earlier green chips describe individual tool calls, not completion of this task. Use the site's Retry; after it recovers, click Resume response. Multi-Script will not resend your prompt or replay prior tools automatically.");
          break;
        }

        diag("response", { kind: res.kind });
        if (A.stop || res.kind === "stopped") break;

        if (res.kind === "context_limit") {
          if (P.id === "superapp" && contextContinuations < 2 && P.clickContinueBtn?.()) {
            contextContinuations++;
            diag("context.continue", { attempt: contextContinuations });
            ui.toast("SuperApp context limit · continuing the current task…");
            if (!(await paceSleep(1500)) || A.stop) break;
            continue;
          }
          ui.banner("limit", `${P.displayName} reached its context limit`,
            (res.detail || "") + "  -  open a new chat to start fresh.");
          break;
        }
        if (res.kind === "too_long") {
          ui.banner("limit", "Conversation too long",
            `${P.displayName} reports the conversation is getting too long. Start a new session.`);
          break;
        }
        // ── Recoverable failures ────────────────────────────────────────────
        // A timeout or a dropped/empty turn used to end the loop outright. In an
        // unattended run that is the single most annoying failure: the site
        // hiccups for one turn and hours of work stop. ZSResilience decides
        // whether another attempt is worth it (bounded, with backoff, and never
        // more than a few in a row) and hands back the exact nudge to send.
        if (SITE_KINDS.has(res.kind)) {
          // waitSiteSafe already waited and re-sent as long as the recovery level
          // allows; reaching here means the site kept refusing.
          ui.banner("warn", res.kind === "quota" ? `${P.displayName} usage limit reached` : `${P.displayName} keeps refusing messages`,
            `${P.displayName} said: "${String(res.text || "").slice(0, 160)}". Multi-Script waited and re-sent the same message ` +
            `as many times as the Error recovery level allows (Settings → Agent), so nothing was lost or run twice. ` +
            (res.kind === "quota" ? `Wait for the limit to reset (or switch model/account), then press Start again.` : `Wait a minute, then press Start again - the last message will be re-sent.`));
          break;
        }
        if (res.kind === "timeout" || res.kind === "empty") {
          if (await recoverFrom(res.kind)) continue;
          if (res.kind === "timeout") {
            ui.banner("warn", `No response from ${P.displayName}`,
              `${P.displayName} did not respond in time and the recovery budget for this ` +
              `failure is spent after repeated attempts, so the loop paused. Press Start again to continue, or raise Error recovery to Persistent in Settings → Agent.`);
          } else if (res.kind === "busy") {
            ui.banner("warn", `${P.displayName} is busy`,
              `${P.displayName} reported it is temporarily busy or asked to try again, and the ` +
              `single retry did not clear it. Nothing was run. Press Start again in a moment, or ` +
              `reload the page.`);
          } else {
            ui.banner("warn", `${P.displayName} returned an empty reply`,
              `The turn produced no text and the automatic retries ran out, so the loop stopped. ` +
              `Nothing was run. Ask ${P.displayName} to continue, or press Start again.`);
          }
          break;
        }

        // The turn stopped with the site's "Continue" affordance.
        if (res.kind === "truncated") {
          if(P.autoContinue===false){ui.banner("warn","Reply needs manual continuation","The provider cut off this reply. No automatic Continue click or follow-up was sent; inspect the conversation before continuing.");break;}
          // If the turn carries the halted marker (a stop - user OR self-halt),
          // respect it and do NOT auto-resume.
          if (P.turnHalted(res.item)) { diag("truncated.halted"); break; }
          // Otherwise it truncated by length → continue the SAME turn. Prefer
          // the native Continue button; fall back to a continuation message.
          if (truncCount < MAX_TRUNC) {
            truncCount++;
            if (P.clickContinueBtn() && await waitFor(() => P.isGenerating(), 2500)) {
              diag("truncated.continued");
              continue; // same turn resumes (base unchanged)
            }
            diag("truncated.sendFallback");
            ui.toast("Reply was cut off, resuming…");
            base = await submitAndGetBase(ZS.FEEDBACK.truncated);
            continue;
          }
          if (res.text) break; // give up resuming; keep what we have as the answer
          ui.banner("warn", "Reply kept getting cut off",
            "The model repeatedly hit its length limit. Try a shorter request or start a new session.");
          break;
        }
        truncCount = 0;

        if (res.kind === "parse_error") {
          // The command turn ended in a parse error - it NEVER ran. Paint its chip
          // as an error (owned, so the sweep won't repaint it the green ✓ "done" it
          // stamps on any command-shaped turn once generation ends - the misleading
          // "chip says OK, result says error" state seen live on GLM's truncated
          // execute_blender_code).
          const failName = ZSParse.toolNameFromText(res.raw || "") || "command";
          try { const dg = ZSParse.diagnose(res.raw || ""); diag("parse.diagnose", { reason: res.reason, kind: dg.kind, name: failName, length: dg.length, depth: dg.depth, tail: String(dg.tail || "").slice(-60) }); } catch {}
          if (res.item) {
            const detail = res.reason === "unclosed" ? "cut off"
              : res.reason === "dsml" ? "wrong format"
              : res.reason === "luaOpener" ? "missing ###LUA###"
              : res.reason === "envelope" ? "bad format"
              : "bad JSON";
            decorate.toolBox(res.item, failName, "err", detail, true, "", ZS.toolCategory(failName));
          }
          // Pass the detected command name so the feedback only offers the
          // ###LUA### block when it actually applies (execute_luau) - never for a
          // truncated/broken execute_blender_code or other JSON-only command.
          // Bounded by the recovery level: a model that keeps emitting the same
          // malformed envelope gets a few corrected attempts, then the loop stops
          // honestly instead of looping on bad JSON forever.
          if (await recoverFrom("parse_error", { name: failName, feedback: ZS.FEEDBACK.parseError(res.reason, failName, res.raw) })) continue;
          ui.banner("warn", "Command could not be parsed",
            `The reply looked like a command but was not one complete JSON object, and the ` +
            `recovery budget is spent. Nothing was run - ask ${P.displayName} to re-send the ` +
            `command as exactly one plain-text JSON object.`);
          break;
        }
        if (res.kind === "text") { const missing=typeof MSExecution!=='undefined'?MSExecution.finalCheck(A.executionTrace):'';
          if(missing&&!A.executionTrace.finalReminder){A.executionTrace.finalReminder=true;base=await submitAndGetBase('[MULTI-SCRIPT VERIFICATION CHECK] '+missing+' Continue only the current task. Apply each complete implementation slice through one exact advertised command as ordinary reply JSON now; code pasted for the user is not an applied change. Never execute example/reference code outside the user scope. Report the precise blocker if execution is unavailable.\nOriginal user request:\n'+String(A.lastUserText||'').slice(0,6000));if(A.lastSendOk)continue;break;}
          if(missing)ui.banner('warn','Task execution unverified',missing);
          A.taskOutcome=A.taskToolErrors||missing?"review-results":"response-received";zsCue(A.taskToolErrors||missing?"error":"done");if(A.taskToolErrors)ui.banner("warn","Review tool results",`${A.taskToolErrors} tool call(s) failed during this run. A model saying it finished does not verify those failures were resolved. Inspect the returned errors and verification evidence.`); break; } // Critic is part of the task prompt, never an unsolicited extra turn.

        if (res.kind === "tool") {
          // A complete, parseable command came back: the session is healthy, so
          // the recovery streak resets (a failure much later starts from zero).
          resetFails();
          if (A.rateFloorMs) { A.rateFloorMs = ZSResilience.decayRateFloor(A.rateFloorMs); saveRateFloor(); }
          const calls = res.calls;
          if (calls.length > 1) {
            base = await submitAndGetBase(ZS.FEEDBACK.multiTool(calls.map((c) => c.tool || "?")));
            continue;
          }
          const call = calls[0];
          // A tool ALREADY seen to return an image this session gets the "screen"
          // chip optimistically at run time (parity with the known screen_capture),
          // even though its name alone wouldn't reveal it. First-ever call of an
          // unknown image tool stays generic here and upgrades at result time below.
          const learnedImg = A.imageTools.has(bareToolName(call.tool));
          const category = learnedImg ? "screen" : ZS.toolCategory(call.tool);
          diag("tool.runCat", { name: call.tool, learnedImg, category });

          // Park BEFORE painting the chip / stamping the clock / marking the turn
          // dispatched. runTool() gates on visibility too (it is the choke point
          // that also covers the bootstrap), but parking only there would leave
          // this block's side effects applied for the whole minimize:
          //   - the chip spins "running" while nothing actually runs, and
          //     elapsedOn(zsToolT0) counts the parked time, so a 20-min minimize
          //     renders a bogus "1200.0s" on the call;
          //   - rememberExecuted() would mark the turn dispatched before it ever
          //     ran, so a reload/close while parked loses the command for good -
          //     the auto-resume watchdog refuses to re-fire an "executed" turn.
          // Parking first keeps all of that truthful: we only commit once we are
          // foreground and about to really dispatch.
          if (pageHidden() && !A.stop) {
            diag("tool.parkBeforeDispatch", { name: call.tool });
            if (!(await waitVisible()) || A.stop) break;
          }
          // Loading chip with the real args (loop owns this item from here).
          decorate.toolBox(res.item, call.tool, "run", argSummary(call), true, callBody(call), category);
          A.toolSettle = null; // a fresh call: no settled outcome yet
          A.toolRunning = true;
          A.toolStart = Date.now();
          A.toolName = call.tool;
          A.toolItem = res.item;
          A.toolArg = argSummary(call);
          // Record this turn as dispatched OFF the DOM so the auto-resume
          // watchdog never re-fires it after a scroll re-render wipes the node's
          // zloop/zResume markers (see the `executed` map).
          rememberExecuted(res.item);
          diag("tool.start", { name: call.tool });
          const discipline=typeof MSExecution!=='undefined'?MSExecution.gate(A.executionTrace,call):{blocked:false};
          if(discipline.pause){A.toolRunning=false;decorate.toolBox(res.item,call.tool,'err','not run: repeated stall',true,discipline.feedback,category);A.userStopped=true;A.taskOutcome='review-results';coworkQueue?.pause('Repeated unchanged tool attempts. Inspect the cause before resuming.');ui.banner('warn','Run paused after repeated stalls',discipline.feedback);break;}
          const ledger=readTaskProgress();
          // Active tool is transient (restore clears it); persist once when its
          // actual result arrives instead of writing the full ledger twice.
          if(ledger&&!isLocalProgressTool(call.tool)&&!discipline.blocked){ledger.activeTool=call.tool;runMonitor?.paint();}
          const feedback = discipline.blocked?discipline.feedback:await runTool(call);
          if(!discipline.blocked&&typeof MSExecution!=='undefined')MSExecution.record(A.executionTrace,call,feedback,feedbackIsError(feedback));
          if(ledger&&ledger===readTaskProgress()&&!isLocalProgressTool(call.tool)){if(!discipline.blocked){ledger.calls++;if(feedbackIsError(feedback))ledger.errors++;}ledger.activeTool='';ledger.lastTool=call.tool;ledger.updated=Date.now();MSProgress.activity(ledger,{kind:feedbackIsError(feedback)?'tool-error':'tool',title:call.tool,detail:stripOutputPrefix(feedback).trim(),argument:argSummary(call)});saveTaskProgress();}
          A.toolRunning = false;
          diag("tool.done", { name: call.tool, ok: !feedbackIsError(feedback), out: feedback.slice(0, 50) });
          if (A.stop) {
            // User halted mid-tool: settle the spinning chip so it doesn't look
            // stuck loading forever, and MARK the turn so the sweep classifier
            // never repaints it ✓ done once generation ends (the real cause of a
            // stopped call still going green a moment later).
            if (res.item) { res.item.dataset.zStopped = "1"; rememberHalted(res.item); }
            decorate.toolBox(res.item, call.tool, "err", "stopped", true, "", category);
            break;
          }
          const isErr = feedbackIsError(feedback);
          if(isErr&&!discipline.blocked&&!isLocalProgressTool(call.tool))A.taskToolErrors=(A.taskToolErrors||0)+1;
          zsCue(isErr ? "error" : "command");
          const outBody = stripOutputPrefix(feedback);
          // Trace the chip's DERIVED phase vs summary. Blender (and any MCP whose
          // output leads with a warning/diagnostic line) resolves ✓ done - the
          // payload starts "Output of…", not "ERROR" - yet outSummary shows its
          // FIRST line, which is the warning. Captures firstLine vs a later
          // success line so we can see the mismatch without guessing.
          {
            const lns = outBody.split("\n").map((l) => l.trim()).filter(Boolean);
            diag("tool.result", { name: call.tool, isErr, phase: isErr ? "err" : "done",
              summary: outSummary(feedback), lineCount: lns.length,
              firstLine: (lns[0] || "").slice(0, 90), lastLine: (lns[lns.length - 1] || "").slice(0, 90) });
          }
          // A tool (Roblox OR any custom MCP server) that actually RETURNED an
          // image becomes a "screen" chip - even if its name never let us guess.
          // Reactive, not predictive: A.pendingImages is set by runTool before it
          // returns. Remember the name so its next call is optimistic (see above).
          const hasImages = !!(A.pendingImages && A.pendingImages.length);
          if (hasImages) rememberImageTool(call.tool);
          const resultCat = hasImages ? "screen" : category;
          decorate.toolBox(res.item, call.tool, isErr ? "err" : "done", outSummary(feedback),
            true, outBody, resultCat);
          // Snapshot the settled outcome. If the site swaps this turn's DOM node
          // while we wait for the model's next turn (wiping the chip AND the
          // zloop ownership dataset), the sweep re-owns the fresh node with this
          // outcome instead of letting branch-3 classification re-spin a "run"
          // chip on an already-executed call.
          A.toolSettle = {
            phase: isErr ? "err" : "done", detail: outSummary(feedback),
            body: outBody, category: resultCat, count: P.assistantCount(),
            // Node IDENTITY of the settled turn (virtualization-proof), when the
            // provider exposes it. The count guard alone misfires on Qwen: the
            // list virtualizes so assistantCount() doesn't grow for the model's
            // NEXT turn, and back-to-back calls to the SAME tool defeat the name
            // guard too - the sweep then re-owned the STREAMING next turn's chip
            // with the previous done/err outcome (seen live: 5x chip.reown with
            // gen:true, rp tiny).
            id: P.lastAssistantId ? P.lastAssistantId() : undefined,
          };

          // Re-inject the command list every REMIND_TOOLS_EVERY successful calls.
          // Appended UNDER the tool result and clearly marked as a reminder, so a
          // model that has drifted from the exact command names gets re-anchored
          // without it looking like a new result to act on. Errors don't count
          // (they already restate what's wrong) and list_commands is redundant.
          let toSend = feedback;
          memTools.push(call.tool);
          if (A.memAnnounce && memOn()) {
            A.memAnnounce = false;
            toSend += "\n\n" + ZM.RESEND_NOTE + "\n" + memCtrl.promptBlock();
          }
          if (!isErr && !isLocalProgressTool(call.tool) && !['list_commands','list_tools','more_output','ms_more_output'].includes(bareKey(call.tool)) && A.toolList.length) {
            A.toolCallsSinceReminder++;
            if (A.toolCallsSinceReminder >= REMIND_TOOLS_EVERY) {
              A.toolCallsSinceReminder = 0;
              // Scope the reminder to the primary Roblox server, exactly like
              // list_commands: re-injecting EVERY connected server's tools (Blender
              // etc.) merged flat would bloat the model's context - the opposite of
              // what the model gets when it lists commands itself. Anti-drift only
              // needs the primary Roblox set; addon commands were listed on demand
              // and the bridge routes by name regardless.
              const scoped = sessionExecutionTools();
              toSend += ZS.toolsReminder(scoped) + "\n" + (activeEngineIds().includes("roblox")?ZS.memoryNudge():"") + (memOn() ? "\n" + memCtrl.nudge() : "");
              diag("tools.reminder", { after: REMIND_TOOLS_EVERY });
            }
          }
          // This result becomes a turn, so it counts toward the re-statement
          // budget - context volume is what makes the site summarise, and the
          // volume is overwhelmingly tool results, not how often the user types.
          bumpSys("results");
          // Ride the system-prompt re-statement out on this result if one is due
          // and it fits (see withSysResend - the result itself is never trimmed).
          toSend = withSysResend(toSend);
          if (ZS.optimizeInjectedText && !A.pendingSettingsKey) toSend = ZS.optimizeInjectedText(toSend, ui.getUsageMode());
          const images = A.pendingImages;
          A.pendingImages = null;
          diag("images.consumed", { count: images ? images.length : 0 });
          if(coworkQueue) {
            try { base=await coworkQueue.withFeedback(toSend,async text=>{const result=await submitAndGetBase(text,images);if(!A.lastSendOk)throw Error(A.lastSendError||"Send not confirmed");return result;}); }
            catch { if(A.lastSendOk)throw Error("Co-work delivery failed"); }
          } else base = await submitAndGetBase(toSend, images);
        }
      }
    } catch (e) {
      diag("loop.error", { msg: String((e && e.message) || e) });
      ui.banner("warn", "Internal loop error", String((e && e.message) || e));
    } finally {
      observeTaskProgress(A.responseFailure?'error':A.userStopped?'stopped':A.taskOutcome==='review-results'?'review':A.taskOutcome==='response-received'?'response':'paused');
      A.running = false;
      A.stop = false;
      // Keep the "Stopping…" state while the site's stream is still draining
      // after a user stop: the loop often ends BEFORE the native stop takes
      // effect (loop.end fires with gen still true - seen live on DeepSeek),
      // and clearing the flag here let the next sweep restore a clickable
      // "■ Stop" for the last beat of the dying stream (the Stopping… → Stop →
      // gone bounce). The sweep's self-heal clears it - and retries the native
      // stop - once the site is actually quiet.
      const draining = A.stopping && A.started && P.isHardGenerating();
      if (A.stopping && draining) diag("stop.drain", { keptStopping: true });
      A.stopping = draining;
      A.toolRunning = false;
      A.toolSettle = null;
      A.loopKey = null;
      ui.showStop(false);
      ui.inputCover(false); // lift the "Agent is working" cover when the loop ends
      P.setInputLock(false); // always unlock, even on error or stop
      diag("loop.end");
      try {
        if (memOn() && memUser) {
          const it = P.lastAssistant();
          const reply = it ? String((P.itemText ? P.itemText(it) : it.textContent) || "") : "";
          memCtrl.observe({ user: memUser, assistant: reply, tools: memTools }).catch(() => {});
        }
      } catch {}
    }
  }

  // Mark the current assistant turn as user-halted so the sweep classifier shows
  // its command chip as "stopped" instead of repainting it ✓ done when
  // generation ends. Cleared on a deliberate resume (native Continue).
  //
  // The dataset marker alone is NOT enough: sites re-render the whole history
  // when the next user message lands (seen live on DeepSeek), replacing the
  // halted turn's node and wiping dataset.zStopped - and since a fresh user
  // message also clears the A.userStopped latch by design, nothing said
  // "stopped" anymore and the chip went ✓ green. So halted turns are ALSO
  // remembered here, keyed independently of the DOM node (conversation +
  // position among assistant turns + a text prefix), and the sweep re-stamps
  // the marker whenever the node was swapped.
  const halted = new Map(); // "conv|turnKey" → text prefix at halt time
  const assistantIdx = (item) => P.allItems().filter(P.isAssistantItem).indexOf(item);
  // Virtualization-stable map key for the off-DOM executed/halted memories.
  // assistantIdx is POSITIONAL within the currently-rendered window, so on a
  // virtualized list (DeepSeek/Qwen/GLM/Arena) scrolling up renders a different
  // set of turns and an OLD command turn takes a low index that COLLIDES with a
  // current turn's key - the dedupe then misses and the watchdog re-fires the
  // scrolled-back tool. Prefer the provider's stable per-turn id when it exposes
  // one (P.itemKey); fall back to the index for non-virtualized providers.
  const turnKey = (item) => {
    if (P.itemKey) {
      const k = P.itemKey(item);
      if (k != null) return `k${k}`;
    }
    return String(assistantIdx(item));
  };
  function rememberHalted(item) {
    try {
      if (!item || assistantIdx(item) < 0) return;
      const pref = (P.itemText(item) || "").slice(0, 60);
      // A stop during the REASONING phase leaves the answer text EMPTY - an
      // empty/short prefix would then startsWith-match ANY later turn at this
      // index (seen live: a fresh streaming command went red "stopped" on the
      // spot). Too little text to identify → rely on the dataset marker only.
      if (pref.trim().length < 12) return;
      halted.set(`${P.conversationKey()}|${turnKey(item)}`, pref);
    } catch {}
  }
  function forgetHalted(item) {
    if (!item || !halted.size) return;
    try { halted.delete(`${P.conversationKey()}|${turnKey(item)}`); } catch {}
  }
  // The halt was recorded MID-stream, so the stored text is a PREFIX of the
  // turn's final text - match on startsWith, never equality.
  function isRememberedHalted(item, txt) {
    if (!halted.size) return false;
    try {
      const pref = halted.get(`${P.conversationKey()}|${turnKey(item)}`);
      return pref != null && (txt || "").startsWith(pref);
    } catch { return false; }
  }
  function markStoppedTurn() {
    const it = P.lastAssistant();
    if (!it) return;
    it.dataset.zStopped = "1";
    rememberHalted(it);
  }

  // Off-DOM record of assistant turns whose command has ALREADY been dispatched
  // (by the normal loop OR the auto-resume watchdog). The dataset markers that
  // dedupe re-execution (zResume / zloop) live on the DOM NODE - but sites
  // virtualize long conversations, so scrolling up DESTROYS and RECREATES a
  // turn's node, wiping those markers. The fresh node then looks un-run, and the
  // watchdog can re-fire the turn's tool with no live generation at all (the
  // "tools execute when I scroll back" bug). Mirror the `halted` map exactly
  // (keyed by conversation + assistant index + a text prefix, NOT the node) so
  // the "already ran this" memory survives node recreation. This makes
  // re-execution IDEMPOTENT regardless of any isGenerating/lastGenAt heuristic
  // misfire - the hard part (is this a live turn?) can be wrong without harm.
  const executed = new Map(); // "conv|turnKey" → text prefix at dispatch time
  function rememberExecuted(item) {
    if (!item) return;
    try {
      if (assistantIdx(item) < 0) return;
      const pref = (P.itemText(item) || "").slice(0, 60);
      // Same guard as rememberHalted: too little text to identify the turn (a
      // command still streaming) would startsWith-match any later turn at this
      // index. Fall back to the dataset marker until there is enough text.
      if (pref.trim().length < 12) return;
      executed.set(`${P.conversationKey()}|${turnKey(item)}`, pref);
    } catch {}
  }
  function isRememberedExecuted(item, txt) {
    if (!executed.size) return false;
    try {
      const pref = executed.get(`${P.conversationKey()}|${turnKey(item)}`);
      return pref != null && (txt || "").startsWith(pref);
    } catch { return false; }
  }
  function stopLoop() {
    observeTaskProgress('stopped');
    if (A.stopping) return; // already winding down - ignore double-clicks
    if(A.starting){
      A.startGen++;A.starting=false;A.startingKey=null;
      if(A.bootstrapClaimKey)bootstrapClaims.delete(A.bootstrapClaimKey);
      P.setInputLock(false);ui.inputCover(false);ui.setStarting(false);
    }
    diag("stopLoop");
    coworkQueue?.pause("Stopped by you. Resume follow-ups when ready.");
    A.stop = true;
    A.stopping = true;
    A.stopAt = Date.now(); // grace anchor for the regenerate-as-resume gates
    // Baseline for the stop-retry growth gate (see the self-heal in the meter
    // loop): a retry is only allowed if the reply keeps growing PAST this,
    // proving the first stop click was swallowed. Without it, retries clicked a
    // wedged (already-stopped) stop button and Gemini killed the NEXT turn.
    A.stopStreamLen = P.streamLen ? P.streamLen() : 0;
    A.userStopped = true; // suppress auto-resume until the next user message
    A.resumeArmed = false; // a stop overrides any pending regenerate grace
    // Disarm any pending optimistic pre-hide (armed in submitAndGetBase for the
    // feedback turn we just sent - see the re-arm note there). The input unlocks
    // right after this function returns, but the window can still be open for a
    // couple more seconds (e.g. mid-image-upload); without this, a message the
    // user types fast right after Stop could be the "next new user turn" the
    // window masks by mistake, instead of the (now abandoned) feedback turn.
    A.injectHideUntil = 0;
    markStoppedTurn();
    // A tool's loading chip is only settled AFTER its `await runTool()` resolves
    // (the if(A.stop) branch in agentLoop). A long-running call (e.g. a big
    // multi_edit) leaves that await pending, so the chip would keep spinning for
    // seconds after the user pressed Stop. Settle it to the stopped state right
    // now; the loop's own settle on resolve is idempotent.
    if (A.toolRunning && A.toolItem) {
      A.toolItem.dataset.zStopped = "1";
      rememberHalted(A.toolItem);
      decorate.toolBox(A.toolItem, A.toolName, "err", "stopped", true, "", ZS.toolCategory(A.toolName));
    }
    ui.markStopping();    // instant feedback: button → "⏳ Stopping…", disabled
    P.stopGeneration();
    ui.toast("Stopping…");
  }

  // The full system prompt for the CURRENT provider and user settings. One
  // definition, used both by the bootstrap and by the periodic re-injection, so
  // the two can never drift apart.
  // BEGIN GENERATED STANDARDS (tools/build_standards_prompt.py)
  const MS_STANDARDS_FULL = [["check-clean-ui", "=== CHECK-CLEAN-UI - use for: Use when building, fixing, restyling or optimising any Roblox UI: menus, HUDs, shops, inventories, dialogue, quest logs, settings, leaderboards, notifications, loading screens, billboards, or on-part screens, in any style: cartoon, studded (Lego-brick), skeuomorphic, steampunk, comic, clay or candy, neumorphic, neubrutalist, Y2K, pixel, paper or sticker, blueprint or terminal, holographic, aurora, low-poly, dark mode, bento, anime or gacha, modern, glass, horror, sci-fi, fantasy, minimal, retro or realistic; or when the user names Check-UI or Check-Clean-UI; or when the UI should show 3D models, 3D icons, item or pet previews, or a studded simulator shop.\n- Mandatory standard for building ANY Roblox UI in any style: menus, HUDs, shops, inventories, dialogue, quest logs, settings, leaderboards, notifications, loading screens, minimaps, billboards and on-part screens. Built from the official Roblox UI docs (containers, layout, constraints, appearance modifiers, styling, input, gamepad, accessibility) plus community UI practice. The checks are internal; the player gets a short plain summary.\n- Keep this standard to yourself. Do not name the skill, its rules, check codes, colour values or asset ids to the user unless they ask. Apply it silently and tell them about the result, not the method.\n- Core: Style first. If the user names a style or a mood (sleek, modern, horror, sci-fi, fantasy, minimal, retro, pixel, realistic, tactical, glass, dark, pastel, anything else), build that, using its style section as a starting point and the user's words as the final say. If they show an existing UI in the project, match it. If they name nothing, use the Cartoon style. Never mix two style families in one screen.\n- Core: Plan before building: the screen's one main job, the one action that matters most, and what the player must see at a glance. Then pick the style, then the devices (phone, tablet, desktop, console) and build for all of them from the start.\n- Core: Structure: one `ScreenGui` per screen group with `ResetOnSpawn = false`, `ZIndexBehavior = Enum.ZIndexBehavior.Sibling`, a sensible `DisplayOrder`, then a `Root` frame, then Header, Body and Footer frames. Name every instance for what it is (`BuyButton`, not `Frame2`). Set properties first and `.Parent` last. UI scripts are LocalScripts on the client; the server validates every purchase, equip, claim or other action the UI asks for.\n- Core: Sizes: use Scale for layout and Offset only for borders, padding, icons and fixed-size controls. Add a `UIAspectRatioConstraint` to anything that must stay square or a set ratio, a `UISizeConstraint` for min and max size, and a `UITextSizeConstraint` when text uses `TextScaled`. Let layout objects position things (`UIListLayout`, `UIGridLayout`, `UIPageLayout`, `UITableLayout`, `UIPadding`); do not hand-place rows. Use `AutomaticSize` for content-driven sizes and `ScrollingFrame.AutomaticCanvasSize` for lists.\n- Core: Layout objects control Position and Size of their children, so a Tween on a child's Position inside a layout is overridden. Animate an inner wrapper, the child's `UIScale`, transparency or rotation instead. `UIFlexItem` (FlexMode Fill, Grow, Shrink or Custom) inside a `UIListLayout` lets one child take the leftover space.\n- Core: Clicks: connect `Activated` on buttons. It fires for mouse, touch and gamepad. Hover states use `MouseEnter` and `MouseLeave`, which never fire on touch, so every state change must also work without hover. A full-screen dim `Frame` with `Active = true` stops clicks reaching the game behind a modal.\n- Core: Do not cover the default Roblox controls: the menu and chat area at the top left, the thumbstick at the bottom left and the jump button at the bottom right on phones. Respect `ScreenGui.ScreenInsets` (`CoreUISafeInsets` is the default; `TopbarSafeInsets` and `DeviceSafeInsets` are the others) rather than hard-coding the top bar height. `IgnoreGuiInset = true` only for full-screen backgrounds.\n- Core: Replacing a default (backpack, health, player list, chat, emotes): turn it off with `StarterGui:SetCoreGuiEnabled(Enum.CoreGuiType.X, false)` inside a `pcall` retry loop, because it can fail early at startup, and rebuild its behaviour (a custom hotbar reads `Player.Backpack` and equips with `Humanoid:EquipTool`).\n- Core: Never invent `rbxassetid` numbers. Use an id only if it is in the project, the user gave it, or `search_asset` / the Creator Store returned it and you confirmed it loads. If an image fails, fall back to a plain solid fill, not an empty box.\n- Core: Check the real result: read properties back from Studio, then capture the screen at a phone size and a desktop size (the Device emulator). Look for clipped or overlapping text, controls under the top bar or thumbs, items too small to tap, low contrast, and anything that overflows. Fix every failure before replying.\n- Core: Treat these as failures to fix silently: text cut off or overflowing, controls under 40 px on a phone, text under 12 px, two overlapping interactive elements, a window that cannot be closed, a menu that stays open after its action, an empty ScrollingFrame that never shows a scrollbar when content is longer, a button with no pressed or disabled state, UI that only works with a mouse.\n- Core: UI facts (official): `UIScale` multiplies its parent's size. `UIGradient` affects only its own parent (one per object), is not supported on ScrollingFrame or TextBox, should not sit on text that has a `TextStrokeColor3`, and should keep colour sequences to six stops or fewer; animate `Offset` or `Rotation` instead of re-setting `Color`. `UICorner` cannot be applied to a ScrollingFrame, and a radius above half the shorter side makes a pill. `UIStroke` on text outlines the glyphs unless `ApplyStrokeMode` is `Border`; tweening `Thickness` on text can flicker, so tween the object's scale instead.\n- Core: Docs (look here before guessing an API; class pages are at https://create.roblox.com/docs/reference/engine/classes/<ClassName>): ScreenGui, GuiObject, UIListLayout, UIGridLayout, UIFlexItem, UIPadding, UIAspectRatioConstraint, UISizeConstraint, UITextSizeConstraint, UIScale, UIStroke, UIGradient, UICorner, CanvasGroup, ScrollingFrame, ImageLabel, TextLabel, GuiService, UserInputService, ContextActionService, TweenService, StyleSheet. Guides: https://create.roblox.com/docs/ui and https://create.roblox.com/docs/production/publishing/accessibility\n- Core: Pictures must be the right pictures and the finished screen must be looked at: search the Creator Store with several phrasings, look at the real thumbnails, reject mismatches, check the picture at its final size, and finish with a screen capture to look for empty boxes, blank or wrong images, clipped or misspelt text and low contrast. Never keep a bad match; draw it from shapes or Parts instead.\n- Core: A screen is finished only when it is full and checked: every tab and list filled with real entries (never an empty panel), the main button tied to a selected item, contrast measured (4.5:1 text, 3:1 large text and icons, inactive tabs still readable, never same-hue text on its plate), text fitted with no clipping, pictures that match, and a last capture reviewed. Fix every failure before replying.\n- Core: No emojis in any interface text, ever. Emoji characters render from the player's system font, so they show as empty boxes, change shape between phones, clash with the art style and break text fitting. Do not put them in titles, buttons, tabs, labels, prices, toasts, tooltips, notifications or placeholder text, and never use a special character for a currency, star, heart, lock, arrow or check. Use a real picture of the right thing (verified image asset), a shape drawn from Frames, `UICorner`, `UIStroke` and `UIGradient`, a small 3D model in a `ViewportFrame`, or one icon from the `BuilderIcons` font (`rbxasset://fonts/families/BuilderIcons.json`, monochrome, one size and weight) instead. Text says words; symbols are drawn.\n- Talking to the player: a short plain message about what you made or changed and where it is in Studio. Add only what needs their action or changes what they see, in everyday words (for example that the look needs their eyes in Studio, or that an image did not load and a plain fill was used). No check tables, codes, rule numbers, colour values, asset ids or instance names unless asked. Never say it works or looks good unless you measured it; the player decides whether the look is right.\n- Design system: Colour: pick one background family, one surface colour a step lighter, one accent for the main action, one warning colour and one success colour. Roughly 60% background, 30% surfaces, 10% accent. Limit a screen to one accent hue plus neutrals; semantic colours (green good, red danger, amber warning) keep their meaning everywhere.\n- Design system: Contrast: normal text against its background needs at least 4.5:1, large text (about 24 px, or 19 px bold) and control borders at least 3:1 (WCAG). Light grey on white and mid-grey on dark fail often. Do not rely on colour alone: pair it with an icon, shape or label.\n- Design system: Type: at most two fonts per game and three sizes per screen: title, body and caption. Titles are about 1.5 to 2 times body size. Body text at 16 px or more on desktop and not under 14 px on phones. Use weight and colour for emphasis before size. Left-align reading text; centre only short labels and numbers.\n- Design system: Spacing: use a 4/8 px rhythm (4, 8, 12, 16, 24, 32). Same padding inside every card, same gap between siblings, bigger gaps between groups than inside them. Related things sit close; unrelated things get air. Never let content touch a panel edge: use `UIPadding`.\n- Design system: Hierarchy: one focal point per screen (the main button or the key number), clearly bigger or brighter than the rest. Secondary actions are quieter (outline or muted fill). Destructive actions are separated and need a confirm. Show only what the player needs now; put the rest behind tabs, a scroll area or a detail view.\n- Design system: Shape language: pick one corner radius family for the whole game (square, small 4 to 8 px, large 12 to 20 px, or full pill) and one stroke weight. Icons share one style (all outline or all filled) and one visual size. Alignment grids beat decoration.\n- Design system: Touch targets: phone buttons at least 44 x 44 px with at least 8 px between neighbours (WCAG 2.2 sets 24 x 24 px as the absolute minimum). Put the primary action where a thumb reaches: lower half, right side. Make the clickable area the whole card, not only the label.\n- Design system: States: every interactive element has default, hover, pressed, selected (gamepad focus), disabled and, where it applies, loading. Disabled looks clearly inactive and says why when it can ('Need 50 more coins'). Show feedback within 0.1 s of a press.\n- Design system: Numbers and text: abbreviate big numbers (1.2K, 3.4M, 5.6B) with a helper, keep the full value in a tooltip or detail view; use `TextTruncate = Enum.TextTruncate.AtEnd` on names; keep labels to one to three words; use `RichText` for inline colour or bold. Always leave room for longer text in other languages.\n- Cartoon style: This is the default look when the user names no style (simulators, tycoons, obbies, clickers) and whenever they ask for cartoon, chunky, cute or colourful. One fixed look: use these recipes exactly. If the user names a different style, none of the Cartoon style rules apply; use that style's section instead and keep the Core and Design system rules.\n- Cartoon style: Font: every text object uses `Enum.Font.GothamBlack` with a black `UIStroke` of 2.0 to 3.5 px, scaled to the text size.\n- Cartoon style: Window canvas: solid `Color3.fromRGB(59,88,102)` (#3B5866), `BackgroundTransparency = 0`, `UICorner` 4 px, outer `UIStroke` 3.5 px `(24,30,34)` in Border mode. Never translucent.\n- Cartoon style: Header: 60 px tall, gradient from the archetype table. Under it a 2-tier divider: a 3 px bar in the archetype's divider-dark colour, then a 3 px solid black bar.\n- Cartoon style: Damier (checkerboard): `rbxassetid://385956923`, tiled, full height of the header or window, with a vertical `UIGradient` transparency of 1 > 0.82 > 0.35 > 0.10. No hard cutoff line.\n- Cartoon style: Icons: `ScaleType = Fit`. Never stretched.\n- Cartoon style: Interactive elements: `AnchorPoint = (0.5,0.5)` and a child `UIScale` named `ButtonScale`, so hover and click scale from the centre.\n- Cartoon style: Responsive: each window has a `UIScale` named `WindowScale`. Scale = `min(viewport.X/1050, viewport.Y/620)` from `camera.ViewportSize`, clamped to 0.52..1.18. Set it when the window opens and when `ViewportSize` changes.\n- Cartoon style: Archetypes: build every menu from one of five: Shop, Codes, Rebirth, Settings, Daily Rewards. For any other menu use the nearest one.\n- Cartoon style: Archetype headers (RGB): | Archetype | Gradient top > bottom | Top highlight | Damier | Divider dark |\n- Cartoon style: Archetype headers (RGB): | Shop | (255,20,150) > (225,0,25) | (255,200,225) | (150,0,20) | (125,0,18) |\n- Cartoon style: Archetype headers (RGB): | Codes | (0,205,255) > (0,130,245) | (180,240,255) | (0,75,150) | (0,50,110) |\n- Cartoon style: Archetype headers (RGB): | Settings | (255,255,255) > (215,222,232) | (255,255,255) | (110,120,135) | (90,100,112) |\n- Cartoon style: Archetype headers (RGB): | Rebirth | (160,0,255) > (96,0,200) | (224,160,255) | (96,0,144) | (80,0,120) |\n- Cartoon style: Archetype headers (RGB): | Daily Rewards | (152,255,0) > (80,208,0) | (224,255,176) | (53,128,0) | (37,96,0) |\n- Cartoon style: Panels: Card background (26,44,52). Card inner stroke (75,125,145), 1.2 px, transparency 0.4.\n- Cartoon style: Panels: Requirements box (20,34,42) with a 1.2 px stroke (85,140,160).\n- Cartoon style: Close button: 38x38 `ImageButton`, `AnchorPoint (0.5,0.5)`, position `(1,-34,0.5,-2)` in the header, `BackgroundColor3 (115,0,16)` (this is the bevel), black `UIStroke` 2.8 Border.\n- Cartoon style: Close button: `Face` Frame, size `(1,0,1,-4)` (so a 4 px bevel shows), gradient rotation 90 from (255,125,175) to (255,20,40).\n- Cartoon style: Close button: Inner highlight: a transparent Frame inset 1 px each side with a `UIStroke` (255,210,235), 1.2 px.\n- Cartoon style: Close button: 1 px separator Frame (70,0,10) at the bottom edge of the face.\n- Cartoon style: Close button: Label `X`, GothamBlack 29, white, black `UIStroke` 3.0, centred on the face.\n- Cartoon style: Close button: Child `UIScale` named `ButtonScale`.\n- Cartoon style: Iconless button: Any button without an icon uses this recipe and nothing else. Default size 176x55.\n- Cartoon style: Iconless button: `ImageButton`, `AnchorPoint (0.5,0.5)`, `ClipsDescendants = true`, `AutoButtonColor = false`. Sharp corners: no `UICorner`.\n- Cartoon style: Iconless button: `OuterStroke`: 3 px `(12,20,26)`, Border mode.\n- Cartoon style: Iconless button: `ButtonGradient`: rotation 90. Default (255,232,8) to (255,104,0), or the state colours below.\n- Cartoon style: Iconless button: `Checkerboard`: ImageLabel `rbxassetid://385956923`, tiled 19x19, black, with a 90 degree gradient transparency 0.91 > 0.62.\n- Cartoon style: Iconless button: `InnerHighlight1/2/3`: transparent Frames inset 2, 4 and 6 px, each with a white 1 px `UIStroke`, transparency 0.25, 0.45, 0.80.\n- Cartoon style: Iconless button: `Label`: GothamBlack, white, default size 36, position `(0.5,0,0.5,-1)`, `UIStroke` 3 px `(17,23,26)` in Contextual mode.\n- Cartoon style: Iconless button: `ButtonScale` UIScale.\n- Cartoon style: Button state colours (gradient top > bottom, damier colour): | State | Gradient | Damier | Bevel colour | Highlight |\n- Cartoon style: Button state colours (gradient top > bottom, damier colour): | Claim / Buy / Redeem (lime) | (180,255,25) > (105,225,0) | (40,160,20) | (15,120,15) | (235,255,130) |\n- Cartoon style: Button state colours (gradient top > bottom, damier colour): | Claimed / Disabled (silver) | (216,222,228) > (148,160,176) | (96,104,112) | (72,82,96) | (255,255,255) |\n- Cartoon style: Button state colours (gradient top > bottom, damier colour): | Locked / Destructive (red) | (255,32,80) > (208,0,32) | (144,0,24) | (112,0,16) | (255,176,200) |\n- Cartoon style: Button state colours (gradient top > bottom, damier colour): | Skip (amber) | (255,208,0) > (255,140,0) | (176,96,0) | (153,76,0) | (255,240,160) |\n- Cartoon style: Button state colours (gradient top > bottom, damier colour): | Music on (pink) | (255,20,128) > (212,0,85) | (160,0,64) | (120,10,45) | (255,176,208) |\n- Cartoon style: Button state colours (gradient top > bottom, damier colour): A button's state sets its gradient and damier colour. Claim, Claimed and Locked are the three states of one reward button.\n- Cartoon style: Progress bar: Trough (20,30,36) with a 2 px stroke (12,18,22), clipped. Fill gradient (255,200,0) > (255,106,0) with a 2 px bottom bevel (153,60,0). Label GothamBlack 22, white, stroke 2.6.\n- Cartoon style: Motion: Hover: `ButtonScale` to 1.05 over 0.08 s, Quad Out. Leave: back to 1.0.\n- Cartoon style: Motion: Press: 0.94 over 0.05 s. Release: back to hover scale over 0.12 s, Back Out.\n- Cartoon style: Motion: Sunbursts rotate 20 degrees per second only while their window is visible. Disconnect the update when the window is hidden or destroyed.\n- Cartoon style: Motion: Assert `AnchorPoint == Vector2.new(0.5,0.5)` before binding animations.\n- Cartoon style: Assets: Confirm that the damier id and any other `rbxassetid` you use load in this experience. Never invent ids. If one does not load, use a plain solid fill instead. Use `CheckUIIcons` only if that module exists in the project.\n- Cartoon style: Defaults where the source standard contradicted itself (apply silently): Claim, Skip and the other state buttons follow the iconless recipe (sharp corners, no bevel). The close button keeps its own 4 px bevel. The bevel and highlight colours in the state table are for a beveled variant, used only if the user asks.\n- Cartoon style: Defaults where the source standard contradicted itself (apply silently): Windows and headers use the 4-point damier fade. Buttons use the 2-point fade (0.91 > 0.62).\n- Cartoon style: Defaults where the source standard contradicted itself (apply silently): Skip uses the iconless recipe with the amber colours. There is no rounded Skip header button.\n- Internal checks (for you, never shown): After building, verify in your own notes only: style consistent; one clear main action; contrast ok; touch targets ok; no clipping at phone and desktop sizes; layout objects used; all states present; gamepad reaches every control; connections cleaned up; heavy lists pooled; assets load.\n- Internal checks (for you, never shown): Cartoon style only: font and stroke, solid canvas, header gradient and divider, damier fade, close button and iconless button recipes, state colours, Fit icons, ButtonScale and centred anchors, WindowScale, sunburst speed, archetype, assets, and a visual match that only the user can confirm.\n- Internal checks (for you, never shown): Fix every failure before replying. Do not stop at a failing check.\n- Official docs (offline): `ms_roblox_docs` holds the official Roblox Creator Docs and Luau docs offline (about 2,260 pages: every engine class, enum, datatype and library, plus the guides). Before using any UI class, property or enum you are not certain of (UIShadow, UIFlexItem, AutomaticSize, TextBounds, BuilderIcons, Enum.Font items), confirm it with action api; for layout rules read the guides (search kind guide, for example 'list flex layouts', 'size modifiers', 'appearance modifiers'). Check every UI script with action check before writing it.\n- Core: Replacing a default (backpack, health, player list, chat, emotes): turn it off with `StarterGui:SetCoreGuiEnabled(Enum.CoreGuiType.X, false)` inside a `pcall` retry loop, because it can fail early at startup, and rebuild its behaviour (a custom hotbar reads the player's `Backpack` child and equips with `Humanoid:EquipTool`).\n- Forge game art (ms_forge): When the look calls for illustrated game art (glossy simulator or cartoon buttons, rarity slots, ornate panels, neon frames) rather than flat Frames, call `ms_forge` action ui_kit once: it draws a matching set, uploads it through Studio, writes `ReplicatedStorage.ForgeKit` and builds a demo shop in `StarterGui.ForgeDemo`. Choose style (simulator, cartoon, glossy, candy, anime, glass, neon, fantasy, scifi, minimal, horror, pixel), pass the game's colours or `reference_image` (a PNG or JPG screenshot), and pick the smallest pack that covers the screen: hud, shop, inventory, settings, leaderboard, dialogue, rewards, essentials, or full (about 120 images). Look at the returned preview and screen_capture the demo; remake with tweaks if anything is off, then delete the demo.\n- Forge game art (ms_forge): Build the real screens from a LocalScript with ForgeKit: `Kit.screen` (auto-scaling, safe insets), `Kit.modal` (title or ribbon, close, pop animation), `Kit.button` (real hover and pressed art, optional icon), `Kit.iconButton`, `Kit.grid` and `Kit.list` (scrolling), `Kit.card` (complete shop card), `Kit.slot` (rarity, icon, count, locked), `Kit.bar` (progress, xp, hp, mana), `Kit.pill`, `Kit.priceTag`, `Kit.toggle`, `Kit.checkbox`, `Kit.radio`, `Kit.slider`, `Kit.input`, `Kit.tabs`, `Kit.badge`, `Kit.bubble`, `Kit.leaderboardRow`, `Kit.toast`, `Kit.tooltip`, `Kit.reward` (spinning rays pop-up after the server grants the reward), `Kit.billboard` (name tag and health over a character), `Kit.loading` and `Kit.icon` (30 icons). Every control is gamepad-selectable and 9-sliced at SliceScale 0.5. The result includes a usage example.\n- Forge game art (ms_forge): Ids come only from the upload Forge made; never type ids yourself. Uploaded images go to the user's Roblox account and through moderation; a rejected or pending image makes the kit warn in Output, and you say so in one sentence. Without Studio connected, Forge only draws (install=false) and returns urls for a manual upload plus bind. Purchases from Kit.card still go through a server-checked remote. Forge art does not relax these rules: text meets contrast with a dark UIStroke, every list is filled, gamepad and touch work, and the finished screen is captured and looked at.\n- UI inspector: After building or changing any screen, call `ms_roblox_gui_audit` (target starter, or player during a play test; root narrows it to one ScreenGui). It measures the real GUI for text that does not fit, tiny or low-contrast text, emoji, buttons under 36 px, off-screen or cut-off parts, empty lists and images that did not load. Fix everything it reports and run it again until clean, then screen_capture.\n- Other sections, loaded with ms_get_skill when the request needs them: Components, Sleek modern style, Glass style, Horror style, Sci-fi style, Fantasy style, Minimal style, Retro style, Realistic style, Studded style, Skeuomorphic style, Steampunk style, Comic style, Clay and candy style, Neumorphism style, Neubrutalism style, Y2K and retro OS style, Pixel style, Paper and sticker style, Blueprint and terminal style, Holographic and iridescent style, Aurora and gradient style, Low-poly and geometric style, Dark mode and bento layouts, Anime and gacha style, StyleSheet, 3D in UI, Studded shop screen, Complete screens and shops, Contrast check, Text fitting, Candy and sweets style, Final review, UI techniques, Interaction and widgets, Inventory and rarity, Feel and motion, Gamepad and console, Accessibility, World UI, UI performance, Assets and icons, Finding and checking assets. Style sections (sleek modern, glass, horror, sci-fi, fantasy, minimal, retro, realistic) replace the Cartoon style when the user asks for them."], ["check-props", "=== CHECK-PROPS - use for: Always use when making any physical thing in Roblox Studio from Parts, unions and Luau: a tree, rock, boat, tank, car, stick, weapon, building, furniture, machine or any other 3D object.\n- Standard: For props, furniture, plants, rocks, vehicles, weapons, machines and buildings made from Studio Parts, unions and Luau. Keep this to yourself: never name the skill, rules, checks, specs or budgets. Numbers marked (tune) are starting values.\n- Reply: When done, say it in one short normal line: that it is finished and where it is (for example 'Done, the crate is in Workspace.'). Do not list the props, parts, techniques, budgets or checks, and do not recap the build. Add one plain sentence only if something needs the user (a part that could not be built, or a choice they must make). Never claim the look is confirmed.\n- Plan first: Before building decide in your own notes: what it is, the one shape that makes it recognisable, style family (one only), size class, footprint and height, 3 to 6 colours, seed, collision (solid, walkable, pass-through), interaction (none, ProximityPrompt, click), and whether it floats on purpose. Block out the big masses first, check scale next to a default character, then add detail. Fix scale and layout before detailing so nothing is rebuilt.\n- Look: Shape comes first. Build in three passes: big masses (the 2 or 3 shapes that make the outline), medium shapes (legs, handles, lids, frames, trim), small details (straps, rivets, vents, bevels). Zoom out until the prop fills about a tenth of the screen; if you cannot tell what it is, fix the big shapes. Test the silhouette as a solid black shape. Put detail where the player looks (handles, doors, seats, screens), and skip tiny screws and hidden faces.\n- Look: Never ship a plain box, plain cylinder or all-default grey Plastic. Every prop has bevel or trim along main edges (strip 0.2 to 0.5 stud), a contrasting secondary material or colour, one off-axis or asymmetric detail, and purposeful wear. Use a few diagonals, tilts and wedges instead of everything at 90 degrees; stylised props are slightly chunkier with oversized handles and hinges. Layer window panes for a reflective look; frame windows and doors with trim.\n- Look: Be consistent: one grid, one detail level, one style family and one palette across the prop and the scene around it. In sets, vary size in groups of three, repeat motifs (same strap, trim colour, rivet) and leave rest areas. Reuse a few versatile pieces rather than many one-offs; for repeated kits keep one grid size (for example 16 studs for modules) and use even side lengths (4, 8, 16, 32) so pieces snap.\n- Colour and material: Palette of 3 to 6 colours: about 60 percent base, 30 percent secondary, 10 percent accent. Value ladder: darker low and in recesses, lighter on top and edges, strongest contrast where the player looks; value contrast matters more than hue. Shadows lean cooler, lights warmer. Avoid pure black and white except tiny edge highlights; blend colours by hand so neighbours look like one palette.\n- Colour and material: At most 2 or 3 materials per prop, chosen to fit (Wood, WoodPlanks, Metal, DiamondPlate, Concrete, Brick, Cobblestone, Slate, Fabric, Marble, SmoothPlastic for toys and sci-fi). A cartoon or low-poly look can use one or two materials throughout. Built-in materials cost less memory than custom textures. `Reflectance` only on glossy parts. Take every Color and Material from one palette table; never leave all parts on default.\n- Colour and material: Wear: lighten hard edges slightly, darken seams, and wear at most two faces or the parts people touch (handles, steps, seat edges). Patches are the same hue family, not a new colour. Glass: real frame plus a Glass pane at about 0.3 to 0.6 transparency; avoid other partial transparency (overdraw), use 0 or 1. Glow: Neon on a small part (under about 10 percent of visible surface) plus one light; never everything Neon.\n- Build rules: Build at edit time (Command Bar or plugin) or in a server Script; never in a LocalScript. Keep templates in ServerStorage and clone on the server; ReplicatedStorage only for props the client clones. One Model per prop, named `Prop_<Category>_<Name>`, sub-assemblies as child Models, parts named for what they are (`LegFrontLeft`, `Lid`). Folder for groups with no geometry.\n- Build rules: Pivot: build in local space with the origin at the bottom centre, lowest point at Y = 0 (organic props may bury up to 1 stud), set `WorldPivot` and place with `PivotTo` once at the end; no `PrimaryPart` on static props (only for constraint-held models). Build unparented and parent once. Never position parts one by one in world space. Rescale a finished prop with `ScaleTo`; verify size with `GetBoundingBox`.\n- Build rules: Grid: normal parts snap to 0.5 studs, detail parts (a side under 1 stud) to 0.1. Offset overlapping faces by 0.01 to stop z-fighting. Anchor every static part before parenting. Variation only through `Random.new(seed)` called in a fixed order; keep jitter small (a few percent size, a few degrees rotation, colour inside the palette). Tags: `Prop` on every clone, `Interactive` for props with a hitbox, `Fallback` for substitutes, nothing else. Scripts inside a prop only if it must run code.\n- Luau helpers and traps: Write tiny helpers once: `mk(parent, name, shape, size, cf, color, material)` (Anchored, Smooth surfaces, collision flags per the rules, returns the part), `mirrorX(cf)` for symmetric pairs, `ring(n, radius, fn)` for legs and spokes. Rotate with `CFrame.Angles`, not by setting `Rotation`.\n- Luau helpers and traps: A `Cylinder`'s long axis is X, so stand it up with `CFrame.Angles(0, 0, math.rad(90))` and remember Size.X is then its length. A `Ball` uses one size for all axes. Do not assume which way a `WedgePart` or `CornerWedgePart` slopes: place it, read which side is tall from a capture, and rotate until the slope faces the right way. Join two points (rope, strut, pipe) with `CFrame.lookAt(a, b) * CFrame.new(0, 0, -len/2)` and `Size = Vector3.new(t, t, len)`. Snap to the floor with a downward raycast that excludes the prop.\n- Collision, performance and scale: Decoration: `CanCollide = false, CanTouch = false, CanQuery = false`; meshes `CollisionFidelity = Box` (Hull for rounded, Default for semi-detailed, Precise only where needed) and `RenderFidelity = Automatic` or Performance. Keep `CanQuery = true` on clickable parts or raycast targets. Collision must match the visible shape; no big invisible boxes on small props. Massless on parts attached to moving objects. Static props anchored; props meant to fall or be pushed stay unanchored.\n- Collision, performance and scale: Budgets (tune), largest side / parts / triangles: tiny (to 1 stud) 8 / 500, small (to 3) 20 / 2,000, medium (to 6) 60 / 8,000, large 550 / 30,000. Repeated background props stay near 2,000 to 4,000 triangles, hero props up to about 10,000. A MeshPart is limited to 20,000 triangles. Lights, emitters and hitboxes count as parts; at most 1 light and 1 emitter per prop; at most 2 decals and 1 Texture. Fewest parts that hold the form; merge hidden details. Identical meshes with the same textures batch into one draw call, so reuse them. Design for low-end mobile.\n- Collision, performance and scale: Scale against a default character about 5 to 5.5 studs tall: doors at least 4 wide and 7 tall, clear ceiling 8 (never under 7), walkable gaps 3 wide, steps 1 stud tall or less and 2 deep, ramps up to 40 degrees, seats 1.5 to 2 high, tables and counters 3 to 3.5, overhangs over walkable ground at least 7 up. Place the prop next to a character; if it looks wrong it fails. Every part is supported within 0.1 stud of the ground or another part, or deliberately floating and anchored.\n- Collision, performance and scale: Interaction: prefer a `ProximityPrompt`. For click or touch use a separate invisible `Hitbox_<PropName>` part (`Transparency = 1`, `CanCollide = false`, about 0.5 stud larger each side, `CanQuery = true`, `CanTouch = true` only for touch).\n- Unions and meshes: Union with `GeometryService:UnionAsync(main, parts, {CollisionFidelity=..., RenderFidelity=..., SplitApart=false})` inside `pcall`, one group at a time and not in a burst. Inputs must be watertight primitive Parts or unions (no MeshParts, no Terrain); an empty or failed result is a failure. The result keeps the main part's Color, Material, Transparency and CanCollide; set its `CFrame` to the main part's before parenting and keep the originals until it passes. Unions use box-mapped UVs, so put textures on plain parts. A result over 20,000 triangles is simplified or errors, so keep well under. Negate with the `rbxNegate` tag. Use `CalculateConstraintsToPreserve` if the inputs had constraints. Do not cut doors with `SubtractAsync`; build wall segments around the opening. Prefer simple parts to unions where a smooth cut is not needed, since unions cost more.\n- Unions and meshes: Meshes and tools: for hard organic shapes you may use mesh generation or Creator Store search if available, verify the asset is the right thing and has no unexpected scripts, and apply the collision and render settings above. `SurfaceAppearance` only on MeshParts with UVs: ColorMap near-white so `Color` can tint, OpenGL normal map (flat is 127,127,255), roughness and metalness (glossy plastic 0.1, matte plastic 0.4, worn wood 0.7 to 0.9, leather 0.2 to 0.7, painted metal 0.3, pure metal 0.2 to 0.3 with metalness 1; metalness only on real metal). Texture 256 for small (about 5 studs), 512 medium, 1024 ceiling; bake ambient occlusion into the colour map; share one texture across similar props.\n- Style families: Pick exactly one. Organic: irregular overlapping Balls, Cylinders, tilted Blocks and Wedges, up to 15 degrees jitter, tapering trunks, pass-through canopies with the lowest edge above 7 studs. Material: simple forms, one primary material (max 2), bevelled edges, wear on at most 2 faces. Scientific: right angles and symmetry, white, grey and blue-grey plus one accent, SmoothPlastic, Metal, Glass. Technological: hard edges, layered panels, dark gunmetal plus one neon accent. Supernatural: asymmetry allowed, floating parts only if declared, one base and one glow colour, blocking solids at Transparency 0.5 or lower, at most 1 emitter and 1 light.\n- Recipes: Tree: tapered, slightly tilted trunk (stacked Cylinders), 3 to 5 branches at varied heights, canopy of 3 to 7 overlapping Balls or Blocks in 2 or 3 greens (darker below), roots; never one lollipop ball. Rock: 4 to 8 Blocks or Balls, random rotation, 20 to 30 percent sunk, 2 to 3 greys, one big mass with smaller companions. Crate and barrel: frame with plank panels, corner trim and a lighter lid; barrel body with 2 or 3 thin metal bands and a slight belly. Chair and table: tapered legs set in from the corners, an apron, a tilted backrest, a different cushion material. Lamp or torch: base, head with glass or Neon, one light, a cap. Fence, wall, bridge: a repeated unit with small height and tilt variation, posts taller than rails, bridge at least 3 wide with rails 3 to 3.5 high. Weapon or tool: clear silhouette, contrasting handle, guard, small accent, grip at the origin. Vehicle: chassis, body, Cylinder wheels with hubs, lights, trim, mirrored across the long axis plus 2 or 3 asymmetric details. Building: Shell, Openings, Interior (one per floor), Trim as child Models; plinth in a different material, window frames with sills, door with frame, roof overhang, chimney or vent; floors at least 1 stud thick, rooms at least 8 by 8, corridors at least 4 wide, exterior walls at least 1 thick, windows real openings, no roof gaps; walkable interiors `ModelStreamingMode = Atomic`, and lights inside.\n- Lighting check: Look at the prop in the place's lighting, not only in a bare baseplate: `ShadowMap` or Future shadows, a sky that suits the style, and subtle effects (Bloom, ColorCorrection, Atmosphere) change how colours and metals read. `EnvironmentSpecularScale` affects how reflective metal looks. Adjust the prop's colours, not the scene's global lighting, unless asked.\n- Failure handling: A missing palette entry, failed or empty union, missing seed, or a part, triangle, light or emitter count over budget is a failure: log a warning in the Output window with the prop name and reason, and place a plain box at the declared size tagged `Fallback`. Never place a broken or partial model silently.\n- Internal checks (for you, never shown): Before replying inspect the real model in Studio. Check: silhouette reads and it is not a plain box; bevel or trim, secondary material, limited palette with a value ladder, wear; correct wedge and cylinder orientation; pivot, grid, anchoring and collision per part type; part and triangle counts within budget; unions followed the rules; same seed gives the same prop; tags only as allowed; size class and scale against a character; doors, gaps, steps and ramps meet minimums; supported, no floating, sunk or clipping parts, no z-fighting; hitboxes; buildings follow the building rules.\n- Internal checks (for you, never shown): Capture it from four views (front, side, top, three-quarter), far away, and next to a default character, fix what you find, and do at least one improve pass. Fix every failure before replying. You cannot judge taste or run a playtest, so treat the look and walk-through as unconfirmed, but do not say so unless it matters to the user.\n- Official docs (offline): `ms_roblox_docs` holds the official Roblox Creator Docs and Luau docs offline (about 2,260 pages: every engine class, enum, datatype and library, plus the guides). Confirm part, material and enum names with action api before building (Enum.Material items, PartType, SurfaceAppearance, GeometryService), and run action check on the generator code first; an unknown enum item stops the whole script."], ["code-quality", "=== CODE-QUALITY - use for: Always use for any Roblox code: writing, fixing, refactoring or reviewing scripts, modules, remotes, data saving, purchases, player and character handling, structure and performance.\n- Mandatory standard for every Roblox script. Built from the official Roblox docs (security, remotes, type checking, native code generation, Parallel Luau, performance, player data and purchases) and community practice.\n- Architecture: The server owns game state, rules, progression, currency and rewards. The client renders and sends intent only.\n- Architecture: Server-only code and data go in ServerScriptService or ServerStorage, never ReplicatedStorage (every client downloads it and can decompile it).\n- Architecture: One script per job. Logic lives in ModuleScripts that return a table; scripts only wire modules together and connect events.\n- Architecture: Require modules in a serial context, never during a parallel phase. Avoid circular requires.\n- Architecture: Expose the minimum: keep helpers local, return only the public API.\n- Architecture: Read the existing scripts, naming and folder layout first and match them. Do not duplicate a system that already exists.\n- Types: Start every new script with --!strict. Use --!nonstrict only for old code that cannot be typed yet.\n- Types: Annotate all function parameters and returns and any shared table shape. Share types with export type in the module.\n- Types: Use ? for optional values and refine with an explicit nil or typeof check. Use :: casts only when verified; never cast to any to silence a warning.\n- Types: There is no table type: write {T} for lists, {[K]: V} for maps, {Field: T} for records. Never mix numeric and string keys in one table.\n- Types: Fix every Script Analysis warning you introduce.\n- Security: An exploiter can fire any remote at any rate with any arguments, fire Touched and ProximityPrompt at any range, own their character and unanchored parts, and read any replicated script.\n- Security: Every server remote handler, in order: check argument count and types with typeof, reject NaN and infinity, clamp or reject out-of-range numbers, validate enums and string length against an allow-list, confirm the player is allowed (alive, owns the item, has the level), confirm the action is possible (cooldown, range, state), then act.\n- Security: The client never sends prices, damage, rewards, results or other players' data. The server looks up the real values.\n- Security: Rate limit every remote per player (minimum interval or token bucket) and drop or kick on abuse. Keep a server cooldown even if the client has one.\n- Security: Validate distance and line of sight on the server before pickups, hits and interactions. Never trust a client-reported Touched on its own.\n- Security: WalkSpeed, JumpPower and similar humanoid properties are client-replicated and can be changed by the client. Never use them as security; sanity check position and speed on the server.\n- Security: Prefer RemoteEvent for one-way calls. Avoid server-to-client RemoteFunction calls (a client can error, disconnect or never return and stall the server thread); if unavoidable use pcall with a timeout path. Only one OnServerInvoke runs per RemoteFunction.\n- Security: Remote payloads: tables are copied, metatables stripped, functions arrive as nil, non-string keys become strings, nil inside tables breaks arrays, instances the receiver cannot see arrive as nil. Send plain arrays or plain dictionaries of simple values. Do not mix numeric and string keys.\n- Security: UnreliableRemoteEvent only for continuous, disposable data under about 1000 bytes, with a sequence number so old messages are ignored. Never for purchases, damage or required state changes.\n- Security: Hiding a UI or checking inside a LocalScript is not security. Never put secrets, keys or webhook URLs in client-visible code.\n- Memory and cleanup: Every Connect has an owner that disconnects it (a Maid, Janitor or Trove, or the project's helper), tied to Destroying, the player leaving or the character being removed.\n- Memory and cleanup: Clear per-player tables on PlayerRemoving and per-character state on removal or death. Destroy instances you create when finished. Cap every table or queue that can grow.\n- Modern API only: task.spawn, task.defer, task.delay, task.wait. Never wait, spawn or delay.\n- Modern API only: workspace:Raycast with RaycastParams, not FindPartOnRay. Animator:LoadAnimation, not Humanoid:LoadAnimation. Constraints (LinearVelocity, AlignPosition and so on), not BodyVelocity or BodyForce. TweenService, ContextActionService, UserInputService. PlayerAdded plus a loop over existing players so nobody is missed.\n- Modern API only: For OverlapParams use ExcludeInstances or IncludeInstances; FilterDescendantsInstances and FilterType are superseded.\n- Modern API only: Instance.new then set properties; do not pass a parent argument.\n- Modern API only: os.clock for timing, workspace:GetServerTimeNow for synchronised time. Do not trust os.time on the client for gameplay.\n- Modern API only: If unsure an API exists or its signature is right, look it up in the Roblox documentation first. Do not invent members. Mark anything unconfirmed.\n- Errors and style: Fail fast on programmer errors with assert or error and a clear message. Wrap I/O and external calls in pcall and handle the failure path explicitly. Never swallow an error silently. Use warn for recoverable problems; remove debug prints before finishing.\n- Errors and style: PascalCase for services, types, classes and public members; camelCase for locals, functions and private values; UPPER_SNAKE for constants. Early returns instead of deep nesting, small single-purpose functions, no magic numbers. Comments explain why. Match the project's StyLua and Selene settings if present.\n- Engineering: Work like a senior engineer: understand the request, read the existing code, change the smallest correct thing, make it readable, and prove it runs. Prefer boring, clear code over clever code. Every function does one job; every module has one reason to change; every name says what a thing is or does. Fix root causes, not symptoms.\n- Engineering: Before writing, state to yourself the inputs, outputs, failure cases and who owns the state (server or client). Handle the failure cases on purpose: a missing child, a player who left, a failed request, a nil result, an unexpected value.\n- Engineering: Remove duplication when the same logic appears three times, but do not abstract early. Delete dead code and unused variables. Keep functions short enough to read in one screen. Replace magic numbers with named constants or a Config module; keep tunable values in one place.\n- Engineering: Comment the why, not the what: intent, constraints, units, and surprising decisions. Use short doc comments on public module functions (purpose, parameters, return, errors). No commented-out code, no section banners; split the file instead.\n- Engineering: Definition of done: runs in Studio with a clean Output, server and client both tested (Test or Server and Clients mode), edge cases handled, no leaked connections or instances, no new Script Analysis warnings, matches the project's style, and anything not run is reported as untested.\n- Architecture and lifecycle: Use a small number of entry scripts (one server Script, one client LocalScript, or the project's existing ones) that require modules and start them in a fixed order. Give modules explicit lifecycle functions such as `Init` (create state, no cross-module calls) then `Start` (connect events, begin work); run `Init` for every module before any `Start` so dependency order never depends on require order. Isolate failures with `pcall` so one broken module does not stop startup, and log which one failed.\n- Architecture and lifecycle: Split by responsibility: services own server state and rules (data, economy, combat, spawning); controllers own client input, UI and presentation; shared modules hold types, config, constants and pure helpers. Reusable logic lives in plain modules and classes; services and controllers stay thin and wire things together.\n- Architecture and lifecycle: Pass dependencies in (as parameters or in a constructor) instead of reaching for globals. Avoid singletons everywhere: a module that is required once is already a shared instance, but heavy hidden global state makes code untestable. A service locator is acceptable only for truly ambient things like logging or audio, and a missing service must fail loudly in development.\n- Architecture and lifecycle: Organise by feature, 2 to 3 folder levels deep: server code in `ServerScriptService`, server-only data in `ServerStorage`, shared modules and types in `ReplicatedStorage`, client code in `StarterPlayerScripts`, UI in `StarterGui` by screen. Name instances for their role and use `CollectionService` tags for cross-cutting behaviour (Interactive, Enemy, Collectible) rather than scanning the tree.\n- Architecture and lifecycle: Separate pure logic (maths, rules, formulas, state transitions) from Roblox side effects (Instances, remotes, DataStores). Pure modules are easy to unit test (for example with Jest Roblox) and safe to reuse on the client and the server.\n- Architecture and lifecycle: Do not over-engineer: a small game does not need a framework. Add structure when a real problem appears (duplication, ordering bugs, hard-to-test code). If the project already uses a framework (Knit-style services, a custom loader, Matter, Vanguard), follow it instead of mixing in another. Note that Knit is archived and no longer updated.\n- Errors and results: Programmer errors (a bug, a broken contract) throw with a clear message (`assert`/`error`). Expected failures (a missing player, a rejected purchase, a failed request) return a result: a `success, value` tuple, a small `Result` type, or a Promise that rejects. Do not use errors for normal control flow.\n- Errors and results: Wrap every external or risky call (DataStore, HTTP, MarketplaceService, asset loading, `require` of optional modules) in `pcall` and handle the failure branch: retry with backoff for transient errors, fall back to a safe default, and show the player a plain message when it matters. Comment which errors you expect. Never swallow an error silently: at least `warn` with context (what failed, for whom, the message).\n- Errors and results: Roblox has no log levels. Use a tiny logger module (Debug, Info, Warn, Error) with a debug flag and a consistent prefix (`[Shop]`) so shipped games are quiet and bugs are traceable; use `warn` for recoverable problems and `error` for real faults; remove stray `print` debugging before finishing.\n- Errors and results: Defensive checks at boundaries only: validate arguments from remotes, players and data on the way in; trust validated values inside. Check `Parent`/`IsDescendantOf`/`Character` still exist after any yield, because a player can leave or respawn during `task.wait`, `WaitForChild` or an async call. Guard long operations with a token or a `player.Parent` check.\n- Events and lifecycle: Players: connect `Players.PlayerAdded` once, then run the same setup for `Players:GetPlayers()` so players already in the server are not missed. Connect `CharacterAdded` once per player, and inside it get the new `Humanoid` and connect `Died` for that character only. Do not connect a handler inside a repeating event (equipped, touched, characteradded) without disconnecting the previous one. Clean up on `PlayerRemoving`.\n- Events and lifecycle: Character order: `CharacterAdded` fires when the character model exists; its children may not all be there, so use `WaitForChild` with a timeout, or `CharacterAppearanceLoaded` for accessories. With `Players.CharacterAutoLoads = false` you call `LoadCharacter()` yourself. Turn on `Workspace.PlayerCharacterDestroyBehavior` (or destroy characters and players on removal) so old characters and their connections do not stay in memory.\n- Events and lifecycle: Deferred events (`Workspace.SignalBehavior = Deferred`, recommended and the default for new places): handlers run at the next resumption point, not at once. So never read a flag right after triggering an event expecting the handler already ran, read current state inside handlers rather than the state at the time of the event, use `Once()` for first-occurrence listeners, and do not depend on handler order. Events that keep firing each other stop at depth 10.\n- Events and lifecycle: `Connect` returns a connection; keep it if you must stop it. `Destroying`, `AncestryChanged` and `Changed` handlers see the world after the change. Destroying an instance cleans up connections to its own events; setting `Parent = nil` does not free it. Use `Destroy`, not `Parent = nil`. A reference to a destroyed instance stays valid as a variable but its children may be gone.\n- Events and lifecycle: Loops over players or instances must survive one entry failing: re-check the object inside the loop, and use `task.spawn` or `pcall` per item when one failure must not stop the rest. Snapshot first (`GetPlayers()`, `GetChildren()`), because the real set can change during yields.\n- Style and review: Follow the project's existing style first. Otherwise use the Roblox Lua style guide: tabs, 100 columns, double quotes, PascalCase for classes, enum-like objects and Roblox APIs, camelCase for locals, functions and members, `LOUD_SNAKE_CASE` for local constants, `_camelCase` for private members, files named after what they export, one statement per line, trailing commas in multi-line tables, no semicolons, no parentheses around conditions, `if` expressions instead of `a and b or c`, spell words out.\n- Style and review: File layout: a short purpose comment, services (`game:GetService`), requires (sorted, all at the top, variable named after the module), constants, types, module state, local helpers, the public API, then `return`. Non-member functions are `local function`. Keep argument counts small (one or two); pass a table for more.\n- Style and review: Use StyLua to format and Selene (or Studio's Script Analysis and Luau lint) to catch unused or shadowed variables, undefined globals, empty blocks and suspicious comparisons. Fix warnings you introduce. Run a self-review before finishing: read the diff top to bottom as a reviewer would.\n- Style and review: Code smells to fix on sight: a function over about 40 lines, deep nesting (use early returns), a boolean flag argument, repeated blocks, a module that knows about unrelated systems, long parameter lists, global mutable tables, unexplained numbers, mixed concerns in one script, and TODOs left behind.\n- Style and review: When changing existing code, keep the change small and local, keep behaviour the same unless asked, do not rename or reformat unrelated lines, and mention in one sentence anything you noticed but left alone.\n- Docs (look here before guessing an API; class pages are at https://create.roblox.com/docs/reference/engine/classes/<ClassName>): https://create.roblox.com/docs/scripting/security/security-tactics; https://create.roblox.com/docs/scripting/events/remote; https://create.roblox.com/docs/luau/type-checking; https://create.roblox.com/docs/luau/native-code-gen; https://create.roblox.com/docs/scripting/multithreading; https://create.roblox.com/docs/reference/engine/libraries/task; https://create.roblox.com/docs/workspace/raycasting; https://create.roblox.com/docs/reference/engine/classes/CollectionService; https://create.roblox.com/docs/workspace/streaming; https://create.roblox.com/docs/reference/engine/classes/ProximityPrompt; https://create.roblox.com/docs/cloud-services/data-stores/error-codes-and-limits; https://create.roblox.com/docs/cloud-services/data-stores/player-data-purchasing; https://create.roblox.com/docs/performance-optimization/design\n- Review and deprecated APIs: When reviewing code, go in severity order and report each finding with file and line, severity, what breaks and the fix. Critical: client-authoritative rewards, damage or currency; unvalidated remote arguments; purchases granted outside `ProcessReceipt` or not idempotent; shared saves without session locking; secrets in replicated code; unfiltered player text shown to others. High: data-loss paths (no `BindToClose`, defaults saved after a failed load), memory leaks, `InvokeClient`, per-frame remotes, infinite yields, streaming-unsafe client indexing. Medium: deprecated APIs, polling, server-side tweens, missing `pcall` on yielding calls, late-joiner and `CharacterAdded` races. Low: style and naming.\n- Review and deprecated APIs: Do not write deprecated members. Globals: `task.wait/spawn/delay` not `wait/spawn/delay`; no `getfenv/setfenv`; `workspace:Raycast` not `Ray.new/FindPartOnRay`; `GetPartBoundsInBox` not Region3. Physics: `LinearVelocity, AlignPosition, AlignOrientation, VectorForce, AngularVelocity` not Body movers; `AssemblyLinearVelocity` not `Velocity`; `Model:PivotTo/GetPivot` not `SetPrimaryPartCFrame`; collision groups via `workspace:RegisterCollisionGroup` and `BasePart.CollisionGroup` (string). Characters: `LoadCharacterAsync`, `Animator:LoadAnimation`, `IsInGroupAsync`, `GetMarkerReachedSignal`, `HasRobloxSubscription`.\n- Review and deprecated APIs: Services: `TeleportAsync` + `TeleportOptions` and `ReserveServerAsync`; `GetProductInfoAsync`, `UserOwnsGamePassAsync`, `AwardBadgeAsync`; `AnalyticsService:Log*Event`; `TextChatService` and `TextService:FilterStringAsync`; `PathfindingService:CreatePath` + `ComputeAsync`; `PreloadAsync`; `TweenService` not `TweenPosition`; `UIDragDetector` not `Draggable`; `Instance:Destroy()` not `Remove()`; `game:BindToClose` not `OnClose`; `CollectionService:GetInstanceAddedSignal/GetTagged`; `PrivateServerId` not `VIPServerId`; `Decal.ColorMapContent`; `Lighting.LightingStyle` not `Technology`; `Sound.PlaybackSpeed` and `RollOffMinDistance/RollOffMaxDistance`; `HttpService:RequestAsync` with a Secret instead of the old Open Cloud services. Modern UI and input: `BindAction` or the Input Action System, not `Mouse.KeyDown`.\n- Text safety and chat: Player-to-player chat goes through `TextChatService` channels (`TextChannel:SendAsync`, `ShouldDeliverCallback` on the server, `OnIncomingMessage` on the client; callbacks must not yield). Any text one player writes that another sees (pet names, signs, guild names, trade notes) is filtered on the server with `TextService:FilterStringAsync` before display and again when loaded later, after rate-limiting and a length cap, and it fails closed (show nothing or a placeholder). Public editable text needs a rate limit of at least a minute. Respect `CanUsersChatAsync`. Your own UI text and system messages need no filtering.\n- Talking to the player: The user wants plain input and plain output, like any player or developer: they ask for a thing, they get the thing. Never mention skills, standards, checks, rule codes, ids, budgets or internals.\n- Talking to the player: Reply in one to three short plain sentences: what is done and, only if needed, one thing to try or one thing you could not confirm. No lists of rules, no tables, no process notes.\n- Talking to the player: Do every check yourself and fix failures before replying. Never claim it works or looks good unless you ran it or measured it.\n- Check table (private, never shown): Run these yourself and fix every failure. Anything not run in Studio is reported as untested in one plain sentence.\n- Check table (private, never shown): COD-1 Reads the existing project first and fits it\n- Check table (private, never shown): COD-2 Strict typing, annotations, no new analysis warnings\n- Check table (private, never shown): COD-3 Server owns state; no secrets or privileged logic on the client\n- Check table (private, never shown): COD-4 Every remote handler validates types, ranges, NaN, permission and state, and is rate limited\n- Check table (private, never shown): COD-5 Remote payloads plain; unreliable remotes carry only disposable data\n- Check table (private, never shown): COD-6 Data: pcall, retries, load-failure protection, save on leave, loop and BindToClose\n- Check table (private, never shown): COD-7 Purchases idempotent and granted only after a successful save\n- Check table (private, never shown): COD-8 No polling loops, no per-frame waste, values cached\n- Check table (private, never shown): COD-9 Every connection and instance has a cleanup owner\n- Check table (private, never shown): COD-10 No deprecated APIs; every API confirmed to exist\n- Check table (private, never shown): COD-11 Native and parallel code only where measured and safe\n- Check table (private, never shown): COD-12 Errors handled, no leftover debug prints\n- Check table (private, never shown): COD-13 Ran in Studio with no output errors; remotes tested with a second client or Test server\n- Check table (private, never shown): COD-14 Lifecycle: modules init then start; players, characters and leaving players handled; no nested connections\n- Check table (private, never shown): COD-15 Pure logic separated, errors returned or thrown on purpose, nothing swallowed\n- Check table (private, never shown): COD-16 Style matches the project; no smells; diff reviewed\n- Official docs (offline): `ms_roblox_docs` holds the official Roblox Creator Docs and Luau docs offline (about 2,260 pages: every engine class, enum, datatype and library, plus the guides). Run action check on every script before writing it to Studio and fix every error and every deprecated warning (wait, spawn, delay, Humanoid:LoadAnimation, FindPartOnRay, BodyVelocity and the rest); an info item matters only if that variable is an instance. Confirm any API you are not certain of with action api, which gives the signature, the dot-or-colon form and the replacement for deprecated calls.\n- Done means checked: A task is done only when, after your last change, you read it back or ran a check that passed: the instance exists with the right class and parent, the script source reads as intended, the console is clean in a short play test, or the number you computed was computed in code. If you changed anything again, check again.\n- Done means checked: Never write, repeat or imitate a tool result. If a tool did not run or failed, say so in one sentence and fix or retry; do not claim success. Ignore thumbnails, data URIs and CDN links inside tool results; they carry no information you need.\n- Done means checked: Every script you write to Studio is checked automatically (syntax, undefined names, wrong Roblox APIs, server-only calls on the client, unsafe remotes) and the result is added to the tool output as [Multi-Script code check]. Fix every error and warning it reports before moving on. For bigger systems start from the expert templates: call `ms_skill_reference` for code-quality or scripting-power to read Remotes, PlayerData, Purchases, Cleanup, RoundSystem, NpcBrain, HitValidation, Rolls, Leaderboard, DailyReward, UIController or Component, then adapt them.\n- Done means checked: Keep changes small and reversible: record a ChangeHistory waypoint before a batch of edits, never overwrite an existing system you have not read, and ask before deleting objects, publishing, or writing live data.\n- Other sections, loaded with ms_get_skill when the request needs them: Data and purchases, Performance, Data limits (official), Data errors (official), Scheduling (official), Raycasting (official), CollectionService (official), Streaming (official), ProximityPrompt (official), Patterns, Classes and types, Testing and debugging. Style sections (sleek modern, glass, horror, sci-fi, fantasy, minimal, retro, realistic) replace the Cartoon style when the user asks for them."], ["fix-errors", "=== FIX-ERRORS - use for: Always use when something is broken: an error in Output, a script that does nothing, UI or data or an NPC not working, or lag.\n- Process: Read the actual error before touching code: the full message, the script name and the line number from Output (or the Developer Console, F9, for a live server). Reproduce it once. Do not guess.\n- Process: Open the script at the line named. Fix the cause, not the symptom: never hide an error with pcall, an extra nil check that skips the feature, or by deleting the feature. Keep the change small.\n- Process: After the fix run the same steps again, confirm the error is gone and the Output has no new errors or warnings, and check the neighbouring paths you touched. Remove any temporary prints.\n- Process: An error inside an event handler or task.spawn kills only that thread, so the rest of the game keeps running and the real problem can be far from the symptom. Read the first error in the Output, not the last.\n- Process: Decide which side the problem is on. Use the Test tab with a Server and Client window, and check Output for the server and client views separately. A LocalScript error is a client error; a Script error is a server error.\n- Error 'attempt to index nil with X': the thing before the dot is nil. Causes: the object does not exist yet (use WaitForChild, or on a client check streaming), wrong name or path, the character respawned, the object was destroyed, or FindFirstChild returned nil. Find which value is nil and why.\n- Error 'X is not a valid member of Y': wrong name or capitalisation, the child is not there yet (it has not replicated or streamed in), or it exists only on the other side (server-only objects such as ServerStorage contents never reach clients).\n- Error 'Infinite yield possible on WaitForChild': the child never appears. Check the exact name, the real parent, and whether the object is created on the other side. Add a timeout and handle the missing case.\n- Error 'attempt to call a nil value': the function does not exist. Check spelling, that the module returns it, and dot versus colon (obj:Method() passes self, obj.Method() does not).\n- Error 'attempt to compare number with nil' or 'perform arithmetic on nil': a value was never set. Check attribute and leaderstat names, default values, and load order (data not loaded yet).\n- Error 'Script timeout: exhausted allowed execution time': a loop without a yield. Add task.wait, or split the work across frames, or fix the loop condition.\n- Error 'Requested module was required recursively' or 'module experienced an error while loading': two modules require each other, or the module itself errors at the top level. Break the cycle by passing dependencies in or moving shared code to a third module.\n- Error 'Maximum event re-entrancy depth exceeded': a property or event handler changes the thing that fires it. Guard with a flag or disconnect first.\n- Error 'Studio access to API services is not enabled' (DataStore) or 'HttpService is not enabled': turn on the setting in Game Settings, Security, and publish the place first; Studio needs it.\n- Error 'DataStore request was throttled' or 'added to queue': too many requests. Reduce and batch requests and add backoff.\n- Error 'Failed to load sound/asset' or 'Asset is not trusted': the id is wrong, was moderated, or the experience is not allowed to use it. Say the asset needs replacing; never invent an id.\n- Error 'Unable to cast value to Object' or 'invalid argument #1 (number expected, got nil)': a wrong or missing argument. Print the type and value passed in.\n- No error but a script does nothing: a LocalScript only runs in places like StarterPlayerScripts, StarterGui, StarterCharacterScripts, the Backpack or ReplicatedFirst; a Script only runs in the Workspace or ServerScriptService (or with the right RunContext). Check Enabled/Disabled, the parent, and that it is not inside a Model that is never loaded.\n- No error but a remote does nothing: name mismatch, the remote is not in ReplicatedStorage, wrong direction (FireServer vs FireClient), the server handler was connected after the client fired, or the server rejected the request in its validation. Log on both sides.\n- No error but UI does not show: ScreenGui Enabled, Visible, size of 0, ZIndex or DisplayOrder, ResetOnSpawn clearing it, ClipsDescendants, transparency 1, or it was parented to the wrong place. Check AbsoluteSize and AbsolutePosition.\n- No error but data does not save: API services off in Studio, place not published, saving before the load finished, key mismatch, or BindToClose not waiting. Check Output for DataStore warnings.\n- No error but Touched or a prompt does not fire: CanTouch or CanCollide off, both parts anchored (Touched needs a moving physics part), ProximityPrompt not parented to a BasePart or Attachment, Enabled false, MaxActivationDistance or line of sight.\n- No error but an NPC does not move: anchored parts, no network ownership set, PathStatus not Success, wrong agent size, or the Humanoid is dead.\n- No error but an animation or sound does not play: the asset is not loaded or not permitted for this experience, the Animator is missing, or the track was not stored and was garbage collected.\n- Works in Studio but not live (or reverse): permissions and API services, StreamingEnabled, server versus client timing, unpublished changes, or a Team Create sync issue. Test with a real server and a second client.\n- Lag or stutter: use the MicroProfiler and Script Profiler to find the cost before changing anything. Common causes: per-frame loops, too many parts or particles, unbounded tables, connections that were never disconnected.\n- Verify: reproduce before, fix, reproduce after, and read the Output again. Report untested if you could not run it.\n- Output window (official): filter by type (Error, Warning), by context (Client, Server, User Plugin) and by text; Show Source adds the script name and line; Show Context tags each message as client or server; Ctrl+K (Cmd+K on Mac) clears it. Clear it, reproduce once, then read from the top.\n- DataStore codes (official): 403 API access not enabled in Studio; 301 to 306 request queue full (slow down and retry); 401 and 402 server shutting down (do not retry); 105 value over 4 MB; 101 and 102 empty or over-long key (max 50 characters); throttled errors retry with backoff.\n- A part or model is nil on a client only: streaming may not have sent it yet. For an Atomic model WaitForChild on the model itself; for Persistent models wait for Workspace.PersistentLoaded; do not expect ReplicatedStorage contents to stream; local-only changes are lost when something streams out.\n- A prompt does something it should not: Triggered fires on the server for any player who triggers it, even out of range, so add the distance, cooldown and state checks.\n- Docs (look here before guessing an API; class pages are at https://create.roblox.com/docs/reference/engine/classes/<ClassName>): https://create.roblox.com/docs/studio/output; https://create.roblox.com/docs/cloud-services/data-stores/error-codes-and-limits; https://create.roblox.com/docs/workspace/streaming; https://create.roblox.com/docs/reference/engine/classes/ProximityPrompt; https://create.roblox.com/docs/performance-optimization/design\n- Common errors and causes: `X is not a valid member of Y`: the child does not exist yet or is spelt differently; use `WaitForChild` (with a timeout) on the client, check the exact name and parent, and remember server-created objects may replicate late. `attempt to index nil with 'X'`: the thing before the dot is nil; find which variable is nil and why (a failed lookup, a response with a different shape, a player who left). `attempt to call a nil value`: calling a function or method that does not exist on that value (a table has no `:Destroy()`; a misspelt method).\n- Common errors and causes: `attempt to iterate over a nil value`: the list is nil; check the real shape of the data (print it) and that the request succeeded, because HTTP and DataStore results are often nested one level deeper or empty after a rate limit. `attempt to compare number with nil` or `attempt to perform arithmetic on a nil value`: a missing attribute, value or leaderstat. Assigning a wrong type to a property (a string to `Size`) errors; convert it. `Infinite yield possible on ...` is a warning that a `WaitForChild` is never satisfied: wrong name, wrong parent, or the object is created only on the other side.\n- Common errors and causes: Missing or extra `end`: count the blocks that open against the ends; the editor underline and the error line show where. A script in the wrong place does not run (server Scripts in ServerScriptService or Workspace, LocalScripts in StarterPlayerScripts, StarterGui or StarterCharacterScripts, ModuleScripts anywhere both sides can reach). `HttpService is not allowed` or HTTP 403, 429: enable HTTP requests in settings and back off on rate limits.\n- Remotes and networking: RemoteEvent not firing: (1) create remotes on the server and keep them where both sides can see them (ReplicatedStorage), (2) the same exact name on both sides, (3) the client uses `WaitForChild` and the server connects `OnServerEvent` before the client can fire (create the remote and connect first; for startup use a RemoteFunction handshake), (4) the server handler's first parameter is the player; do not pass LocalPlayer yourself, (5) the print after `FireServer` only proves the client ran, check the server output.\n- Remotes and networking: In Studio use Test with a server and clients (Server and Client windows); when a local server runs, server prints show in the server output, not the client's, which looks like the event never fired. Validate every argument on the server (type, range, ownership, cooldown). Tables sent through remotes lose metatables, non-string keys may change, and instances only arrive if they exist on the receiving side.\n- Debugging method: Reproduce first, then narrow. Use the debugger when a bug is not obvious: a breakpoint on the suspected line, a conditional breakpoint for a specific value (`id == 10`), a logpoint to print without editing code, and the Watch and Call Stack windows to see values and who called. Step Into F11, Step Over F10, Step Out Shift+F11. Set the breakpoint context (Client, Server, Edit) to match where the code runs.\n- Debugging method: Without the debugger: `print` at the start of the script, inside the branch and inside the loop to find where it stops; `warn` for non-fatal problems; `error` to stop on a missing requirement. Check the Developer Console (F9) for client and server logs, memory and network, and the MicroProfiler for slow frames. If nothing prints at all, the script is not running: check its location, whether it is disabled, its RunContext, and whether an earlier error stopped it.\n- Data and purchase errors: DataStore errors carry a code: 101 empty key, 102 key over 50 characters, 105 value over the size limit, 301 to 306 throttled (queue full: slow down and batch), 401 and 402 shutting down, 403 Studio API access off, 5xx server trouble (retry with a backoff). Always `pcall`, log the message, and never write default data after a failed read.\n- Data and purchase errors: Players charged but not rewarded almost always means two scripts set `ProcessReceipt`, the handler returned nothing for a missing player, or it errored; keep one handler, return `NotProcessedYet` when unsure and `PurchaseGranted` only after saving.\n- Silent failures: Animation does not play: the asset is not owned by or shared with the experience owner, the track was loaded on the wrong side, or the Animator is missing. Sound silent: audio permission error in the Output, started on the server in a part that streamed out, or wrong volume. Studio DataStore errors: API access is off. Remote works in Studio but not live: ordering at startup, or an instance the receiver cannot see (ServerStorage, not yet streamed). Scripts from free models doing odd things: check for hidden scripts. Fix the cause and re-run to confirm the Output is clean.\n- Talking to the player: the user wants plain input and plain output. Never mention skills, standards, checks, rule codes or internals. Reply in one to three short plain sentences: what was wrong, that it is fixed, and one thing to try. No lists, no tables.\n- Talking to the player: do every check yourself and fix failures first. Never say it is fixed unless you re-ran the same steps and the error is gone; if you could not run it, say so in one sentence."], ["game-systems", "=== GAME-SYSTEMS - use for: Always use for simulators, coin or collecting loops, tycoons, pets, rebirths, shops, quests, currency and horror structure.\n- Mandatory companion to code-quality for every economy, collecting and round-based game. Numbers marked (tune) are starting values, not facts.\n- Units and scale (official docs): 1 stud = 0.28 m (28 cm). Default gravity is 196.2 studs per second squared. 1 m/s = 3.57 studs/s.\n- Units and scale (official docs): Humanoid defaults: WalkSpeed 16 studs/s, JumpPower 50 (clamped 0 to 1000, affected by gravity), JumpHeight 7.2 studs (used when UseJumpPower is false), MaxSlopeAngle 89 degrees.\n- Units and scale (official docs): Design distances in studs against these numbers: a jump clears about 7 studs, so gaps, steps and pickup ranges are sized from that. Collect radius (tune) is about 4 to 8 studs; pickup magnet range (tune) about 12 to 20.\n- Units and scale (official docs): Physical property limits: density 0.0001 to 100, friction 0 to 2, elasticity 0 to 1.\n- Economy core: The server holds every currency, count, multiplier and unlock. The client sends intent only (collect, buy item X); the server decides amounts.\n- Economy core: One economy module owns all currency changes: Add, Spend, CanAfford. Spend checks the balance first and fails cleanly. No other script edits currency.\n- Economy core: Use integers where possible and cap values so numbers never overflow or become NaN. For idle games past about 1e15 use a big-number format.\n- Economy core: Items, pets, zones, rarities and prices live in data tables or ModuleScripts. The server looks up prices there; never read them from the client.\n- Economy core: Save through the proven data approach in code-quality with a schema version.\n- Economy core: Shown numbers use K, M, B, T, Qa suffixes: below 1000 show as is, otherwise floor, count digits, keep the leading 1 to 3 digits and a fixed precision (for example 2 decimals), and pick the suffix by exponent. Test boundaries: 999, 1000, 999999, 1000000, and anything above the table (fall back to scientific notation). Do not round up into the next suffix wrongly.\n- Coin and collectible loops: Collect, carry (capacity), sell, upgrade, repeat, then a bigger zone or a rebirth. Every step has feedback: a number popup, a sound, a small effect.\n- Coin and collectible loops: Coins and pickups are anchored and non-colliding so players pass through and they stay put.\n- Coin and collectible loops: Official beginner pattern uses Touched with a guard (an Enabled attribute or flag set false on collect) and a respawn cooldown with task.wait. It only connects coins that exist at startup, so connect new ones as they spawn (ChildAdded or a tagged-instance signal), and disconnect when removed.\n- Coin and collectible loops: Touched is unreliable for scale (it can fire several times or not at all). For many collectibles or magnet pickup prefer a server loop with workspace:GetPartBoundsInRadius around each player, with OverlapParams (set MaxParts, use IncludeInstances on the collectibles folder, reuse one OverlapParams object since it can be changed in place, never BruteForceAllSlow), run every 0.1 to 0.25 seconds (tune), and only for players that are near collectible zones.\n- Coin and collectible loops: Always validate on the server: the player is alive, the collectible still exists and is not already claimed (claim it first, then award), capacity is left, and distance is plausible. Claim-then-award stops double collection when two events race.\n- Coin and collectible loops: Spawn from server spawners with a cap and a respawn timer. For huge counts keep collectibles as data on the server and create visible ones on the client near the player, or use streaming, instead of thousands of server parts.\n- Coin and collectible loops: Multipliers stack in one function: base x pets x gamepass x rebirth x event, computed on the server so results are predictable and loggable.\n- Coin and collectible loops: Rebirth: clear requirement, a reset list (what resets and what stays), a permanent bonus, a confirmation, and a server-side check.\n- Coin and collectible loops: Pets and eggs: pet data (rarity, multiplier, id) in a table, equipped limit on the server, eggs roll a server-side weighted random with the odds in a table. Never roll on the client. Show the real odds.\n- Coin and collectible loops: Gamepasses and products are granted through ProcessReceipt or gamepass checks on the server per code-quality and re-checked on join.\n- Coin and collectible loops: Anti-exploit: rate limit collect, sell, buy and hatch; sanity check totals against time played; log and kick on impossible gains.\n- Currency display: leaderstats works for small boards. For richer HUDs replicate values with attributes or a remote that sends the number, and update UI from the change signal, never by polling. Initialise labels at startup so they do not show stale text.\n- Currency display: Animate counters with TweenService. Cap and pool popups so spam cannot create hundreds of GuiObjects.\n- Tycoon: A tycoon belongs to one player; ownership is stored on the server. Buttons validate cost, owner and unlock order. Save purchased items by id and rebuild on join.\n- Tycoon: Droppers and conveyors run on the server with caps on live parts and a lifetime for dropped parts; pool them when frequent.\n- Quests, shops, daily rewards: Quest and reward state is stored per player and checked on the server. Daily rewards use server time, a streak counter and a claim flag, never the client clock.\n- Quests, shops, daily rewards: Shops read the item list from data; the server checks cost and ownership, grants and saves.\n- Horror game structure: Round or level flow lives on the server: lobby, setup, objective, threat, win or lose, reset, with one state variable. Clients only display it.\n- Horror game structure: Objectives (keys, fuses, generators) have server-owned progress and clear hints.\n- Horror game structure: Lighting, Atmosphere and fog set the mood; flickering lights run from one shared tick over tagged lights, not a loop per light.\n- Horror game structure: Jump scares are rare and earned, triggered by the server with a cooldown and played on the client. Offer a reduce-flashing option and keep audio levels sane.\n- Horror game structure: NPC behaviour follows npc-pathfinding.\n- Interactions (official): buy, collect and open prompts use ProximityPrompt, whose Triggered(player) fires on the server but can be triggered by an exploiter from any range, so the handler re-checks distance to the prompt's parent, a per-player cooldown and the player's state before awarding anything.\n- Save budget (official): at most 4 MB per key per minute written, 4,194,304 characters per value and 50 characters per key; keep per-player data compact and write on a timer and on leave, not on every coin.\n- Tag collectibles, spawners and zones with CollectionService and manage them through the added signal plus GetTagged; clean up on the removed signal.\n- Docs (look here before guessing an API; class pages are at https://create.roblox.com/docs/reference/engine/classes/<ClassName>): https://create.roblox.com/docs/physics/units; https://create.roblox.com/docs/reference/engine/datatypes/OverlapParams; https://create.roblox.com/docs/reference/engine/classes/Humanoid; https://create.roblox.com/docs/reference/engine/classes/ProximityPrompt; https://create.roblox.com/docs/reference/engine/classes/CollectionService; https://create.roblox.com/docs/cloud-services/data-stores/error-codes-and-limits; https://create.roblox.com/docs/cloud-services/data-stores/player-data-purchasing\n- Purchases (developer products): Set `MarketplaceService.ProcessReceipt` in exactly one server Script. Only the last script that assigns it takes effect, so search the whole game for other assignments and merge them into one handler; a second handler silently breaks purchases and players are charged without getting the item.\n- Purchases (developer products): Handler order: find the player with `Players:GetPlayerByUserId(receipt.PlayerId)`; if they are not in the server return `Enum.ProductPurchaseDecision.NotProcessedYet` (Roblox retries when they rejoin) and never return nothing; look up the product id in a table of handlers (not a stack of ifs); run the grant inside `pcall`; write the receipt's `PurchaseId` to the player's saved data in the same step as the grant so the same receipt can never grant twice; return `PurchaseGranted` only after the grant and the record are saved or safely queued; return `NotProcessedYet` on any error.\n- Purchases (developer products): Grant functions that run inside an `UpdateAsync` callback must never yield. Do not grant in `PromptProductPurchaseFinished` (it fires when the prompt closes, not when the purchase is proven). Game passes are different: check ownership with `UserOwnsGamePassAsync` inside `pcall` on join, cache the result, and listen to `PromptGamePassPurchaseFinished` to unlock at once. Roblox keeps no per-user purchase history, so store what you need yourself.\n- Purchases (developer products): Client UI only asks to buy (`PromptProductPurchase` or `PromptGamePassPurchase`); the server decides what is granted. Show the real price from the product info, not a hard-coded number (prices can be personalised). Test in Studio with the purchase prompt, and report that live Robux purchases were not tested.\n- Saving data safely: Prefer a proven session-locking module (ProfileStore, or ProfileService) over hand-written DataStore code for player data. Session locking stops two servers editing the same player at once, which is what causes duplicated items after quick rejoins and trades. Template with defaults, `Reconcile()` to add new fields to old saves, one profile per player, release it on `PlayerRemoving`, kick the player if the session cannot start or ends elsewhere, and clear the cached profile.\n- Saving data safely: Never save data that has not loaded, and never fall back to a default template after a failed load and then save it, because the next save wipes the real data. If loading fails, keep the player out of write paths (or kick with a message) and retry. Save every player in `game:BindToClose` too (inside a loop, waiting for all saves), and autosave on a timer. Do not wait to bind `BindToClose` inside `PlayerRemoving`.\n- Saving data safely: If you write DataStore code yourself: wrap every call in `pcall`, retry with a short backoff (about 5 tries starting near 0.5 s, doubling), use `UpdateAsync` for changes that depend on the old value, use a session lock field (`game.JobId`), keep keys short (50 characters max) and values small (4 MB serialised max; stay far below), and write on events or a timer, not every frame. Per-key limits are 25 MB per minute read and 4 MB per minute write; write the same key no more than about once every 6 seconds.\n- Saving data safely: Request budgets per minute: experience-wide reads about 300 + 40 x concurrent users, writes 300 + 20 x CCU; per server reads 60 + 40 x players, writes 60 + 40 x players (ordered stores: writes 30 + 5 x players). Common error codes: 101 empty key, 102 key over 50 characters, 105 value too large, 301 to 306 request queue full (throttled: slow down), 401 and 402 server shutting down, 403 Studio API access off (turn on Enable Studio Access to API Services), 502 and 5xx retry later. Test saving in a published place or with API access on, and report it as untested otherwise.\n- Saving data safely: ProfileStore is for per-player data, not for leaderboards or global state, and not for rapid writes from many servers. Use `MessageAsync` to send things (gifts, trades) to a profile that may be offline, and never edit another player's profile directly from another server.\n- Simulator economy and progression: Design the loop on paper first: source (what earns), sink (what spends), gate (what unlocks next), reward (what the player sees). A simulator is one core action repeated (click, swing, collect), upgrades that make it stronger, zones that raise the rewards, rebirth that trades progress for a permanent multiplier, and collections (pets) for long-term goals. Every action needs instant feedback (sound, number pop, bar fill); a silent core action feels dead.\n- Simulator economy and progression: Costs grow exponentially: `cost(n) = base * growth^n`, with growth about 1.15 to 1.5 for upgrades (tune). Rewards should grow slower than cost so each step takes a little longer than the last (for example gains double while the cost triples). Aim the first upgrade at about 3 minutes of play after the tutorial, early items in minutes, mid items in hours, end items in days (tune). Draw the curve in a table and check the time per level before building.\n- Simulator economy and progression: Keep two or three currencies at most (main, premium, optionally event). Add sinks before the economy inflates: upgrades, eggs, repairs, consumables, cosmetics, rebirth costs. Premium must never make soft currency worthless or be strictly better; sell time-savers and cosmetics, keep everything reachable by playing. Do not put walls that force spending. A rebirth system prevents a hard ceiling.\n- Simulator economy and progression: Large numbers: store as numbers while they fit (doubles are exact to about 9e15; show suffixes K, M, B, T from a table), and switch to a big-number module only if values will really exceed 1e300. Format with a helper (`1.25M`), not raw floats. All earnings, costs and multipliers are calculated on the server; the client only displays. Cap rates and validate remote arguments.\n- Simulator economy and progression: Anti-cheat basics for economies: never trust a client number; clamp and rate-limit earn remotes; derive earnings on the server from what the player actually did; log unusual jumps. Monitor a trading economy for duplication and value manipulation.\n- Pets, eggs and luck: Roll on the server only. The server picks the result and sends the client an id; the client looks it up in a shared module for the name, model and rarity to show. Never let the client choose the result or write inventory.\n- Pets, eggs and luck: Weighted pick: give each item a weight (higher is more common), sum them, roll `Random.new():NextNumber() * total`, then walk the list subtracting weights until the roll is below zero. Return the last item as a fallback, guard against zero total, and never loop with `repeat ... until` on a roll that can fail. Create one `Random` object and reuse it instead of reseeding each time.\n- Pets, eggs and luck: Luck boosts: do not multiply the roll by luck (it can push the roll past 1 and cancels itself). Scale the weights instead: raise rare weights (for example `weight * (1 + luck * rarityIndex)` or divide the odds by luck so a 1 in 100 item becomes 1 in 10 at 10x), then renormalise. Test by rolling 100000 times and comparing results with the stated odds; show the real odds in the UI and make sure they match.\n- Pets, eggs and luck: Pity and guarantees (tune): count rolls without a rare drop and raise the odds, or guarantee one at a threshold, then reset when the rare drops. Keep the counter in saved data. Be honest in the UI about odds; some regions require showing them.\n- Pets, eggs and luck: Hatch flow: check the player owns enough eggs or currency and has space; take payment and add the pet in one server step that saves; then play the animation from the id. Equip limits, delete confirmations and favourites protect players from mistakes. Pets follow with a light server-validated position, and the client animates them.\n- Trading and duplication: Trades run on the server with a shared state both sides must confirm. Lock the offers when either side confirms; if anyone changes an offer after confirming, reset both confirmations. Re-check on the server at the end that both players still own every item, then swap in one saved step. Use session locking so a player cannot trade in two servers.\n- Trading and duplication: Never remove items from one profile and add to the other in separate unsaved steps; if the server crashes between them items vanish or duplicate. Log every trade with both user ids and the items. Add a short cooldown, a minimum account age or play time, and a confirmation screen showing exactly what each side gets.\n- Rounds, lobbies and teleports: Round games run as a server state machine: Intermission, Starting, InRound, Ending, with a timer owned by the server and replicated through a value or remote. Check the player count at each step, handle players leaving or joining mid-round, and reset the map and player state cleanly. Never trust the client for score, win or death.\n- Rounds, lobbies and teleports: Matchmaking across servers: put small tickets in a MemoryStore queue (short expiry, queues deliver at least once so processing must be idempotent), claim then validate before forming a match (players may have cancelled), reserve a server with `ReserveServerAsync`, and have each source server teleport only its own players to the reserved access code. MessagingService is only a wake-up signal because delivery is not guaranteed; keep the real assignment in shared state. Wrap `TeleportAsync` in `pcall` and also handle `TeleportInitFailed`; keep the ticket until the teleport succeeds so a failure can requeue. Never put secrets in teleport data. MemoryStore quotas scale with concurrent users; keep keys and values small. Reserved-server teleports only work in published places, not in plain Studio play tests.\n- Leaderboards: Use a separate `OrderedDataStore` for a leaderboard, with the user id as key and the number as value; do not mix it with the main save. Write from the server on a timer or on events, not every frame. Read pages with `GetSortedAsync(false, 100)` every minute or so, cache the result on the server, and send it to clients; do not make every player query it. Cache usernames and avatar headshots so you do not hit the Players service limits for every row. Ordered stores accept only integers and have lower write budgets; a single hot key can only be written about once every 6 seconds, so many votes on one key need batching.\n- Monetization: Product types: developer product (repeatable: currency, boosts, revives; `ProcessReceipt`), pass (once, permanent), subscription (monthly, revocable), rewarded video ad (granted through a developer product), private server. All granting is on the server. Prompt from the client UI; the server still grants.\n- Monetization: Passes: check `UserOwnsGamePassAsync` in `pcall` on join and listen to `PromptGamePassPurchaseFinished` for in-session buys; refunded passes lose ownership, so re-check instead of caching forever. Subscriptions: `GetUserSubscriptionStatusAsync` on join and on `UserSubscriptionStatusChanged`; perks must be revocable. Developer-product refunds are your job: keep each handled `PurchaseId` with what it granted so a refund can be reversed (Transaction Refunded webhook).\n- Monetization: Shops that sell: show live prices from `GetProductInfoAsync`, never hard-coded Robux numbers (regional and optimised pricing differ per user; `receipt.CurrencySpent` is what was paid). `RankProductsAsync` once on join (strict rate limit), `RecommendTopProductsAsync` inside `task.spawn`. Contextual offers (revive on death, boost when stuck) beat static menus. `MarketplaceService:OpenShop(player)` opens the Roblox Shop overlay.\n- Monetization: Compliance: paid random items (spins, eggs, loot boxes bought with Robux) must show odds before purchase and check `PolicyService:GetPolicyInfoForPlayerAsync` (`ArePaidRandomItemsRestricted` means offer a free path or direct purchase; `IsPaidItemTradingAllowed` false means disable trading of paid items). Gate gifting and trading of bought items with `GetUsersPriceLevelsAsync` if regional arbitrage is a risk. Rewarded video rewards are developer products, never random, and the character is protected while the ad plays. Perks stay cosmetic or convenience, not pay-to-win. `player:PromptAgeCheck()` at most once per 15 minutes and only on a deliberate action; never gate core gameplay on it.\n- Teleports and places: A universe shares DataStores, MemoryStores, MessagingService and products across all its places. Set Access Control for Places to 'Secure within universe only' so clients cannot teleport themselves into restricted places, and check eligibility on join.\n- Teleports and places: Use `TeleportService:TeleportAsync` with `TeleportOptions`: `ShouldReserveServer` for matches and parties, `ReservedServerAccessCode` to join one, `ServerInstanceId` for a specific public server. The old Teleport, TeleportToPlaceInstance and ReserveServer calls are deprecated. `TeleportData` is readable by clients and can be tampered with; never trust it for currency, items or permissions, and key real match data by `PrivateServerId` in a MemoryStore or DataStore written before the teleport.\n- Teleports and places: Handoff: end or save the player's profile before teleporting, load with session locking on arrival, keep a loading screen with `SetTeleportGui` and `ReplicatedFirst`. Server type: public has `PrivateServerId = ''`; reserved has an id and owner 0; private (VIP) has an id and an owner. A match server waits for expected players with a timeout, runs the round, saves results, then teleports everyone back. Server browsers heartbeat `{jobId, players, mode}` into a MemoryStore sorted map with a short TTL. Custom matchmaking signals (player and server attributes) suit skill-based public servers; reserved servers suit exact teams.\n- Live ops and analytics: Log from the server with `AnalyticsService` `LogEconomyEvent` (every source and sink, accurate ending balance), `LogProgressionEvent`, `LogFunnelStepEvent` and `LogCustomEvent`; the `Fire*` methods are deprecated. Keep event names and custom values low-cardinality (categories, not free text or user ids). Design funnels (onboarding, shop, first purchase) before building the feature.\n- Live ops and analytics: Live values: put balance numbers, feature flags and event toggles in experience configs read with `ConfigService` (always code a default; use `GetConfigForPlayerAsync` for targeted experiments, `SetTestingValue` in Studio). Timed events use UTC timestamps in a config compared with `os.time()` on the server, and clients count down from `workspace:GetServerTimeNow()`. Daily shops rotate with `math.floor(os.time() / 86400)`; daily rewards store `lastClaimDay` and a streak; seasons store claimed rewards per season id. Roll new content out behind a flag, validate with a small group, then ship to everyone.\n- Live ops and analytics: Badges: `AwardBadgeAsync` on the server in `pcall`, skip if already owned; good for onboarding and milestones. Re-engagement: ask for opt-in at a good moment with `ExperienceNotificationService:CanPromptOptInAsync()` then `PromptOptIn()`; notifications are sent from a backend and rate-limited.\n- Data extras: Version the save: a `version` field and ordered migration functions on load, then `Reconcile`. Never remove a field in the same release that stops writing it, and never reuse a field name for a new meaning. Restore from versions (`ListVersionsAsync`, `GetVersionAtTimeAsync`) instead of backup keys. Do not pre-compress data. Store only plain tables, numbers, strings, booleans and buffers; never Instances, CFrames or mixed tables.\n- Data extras: MemoryStore: sorted maps for rankings and server lists, queues for matchmaking and work (read, process, then remove by id; invisibility timeout is the crash safety), hash maps for counters. Everything expires (45 days at most), so it is never the only copy. MessagingService is at most 1 kB per message and best effort. Keys like `User_{UserId}` stay static so automated right-to-be-forgotten can delete them; link keys to user ids (`AddUserId`). Studio needs Enable Studio Access to API Services and a separate test universe or store name. Check `GetRequestBudgetForRequestType` before bulk work.\n- Combat and hit validation: Clients predict (play the swing or shot instantly) and send intent; the server owns cooldowns, range, ammo, hit validation and damage. For hit claims check the origin is near the shooter's server position (tolerance scaled by `player:GetNetworkPing()`), the target is alive and an enemy and in range, the claimed point is near the target's recent server position (keep about a second of position history), and a server raycast against static geometry finds no wall. Draw tracers and hit effects on clients from a minimal event.\n- Talking to the player: The user wants plain input and plain output, like any player or developer: they ask for a thing, they get the thing. Never mention skills, standards, checks, rule codes, ids, budgets or internals.\n- Talking to the player: Reply in one to three short plain sentences: what is done and, only if needed, one thing to try or one thing you could not confirm. No lists of rules, no tables, no process notes.\n- Talking to the player: Do every check yourself and fix failures before replying. Never claim it works or looks good unless you ran it or measured it.\n- Check table (private, never shown): SYS-1 Server owns currency and every multiplier through one module\n- Check table (private, never shown): SYS-2 Prices, odds and rewards come from server data tables\n- Check table (private, never shown): SYS-3 Collect, buy, sell, hatch and rebirth are validated, claim-first and rate limited\n- Check table (private, never shown): SYS-4 Collection uses a sound method for the scale (guarded Touched for few, spatial query for many)\n- Check table (private, never shown): SYS-5 Numbers are capped, integer safe, never NaN, and formatted correctly at boundaries\n- Check table (private, never shown): SYS-6 Saved, versioned and rebuilt on join\n- Check table (private, never shown): SYS-7 Spawners capped, collectibles cleaned up, popups pooled\n- Check table (private, never shown): SYS-8 Distances and speeds sized in studs against the defaults\n- Check table (private, never shown): SYS-9 Round and objective state lives on the server\n- Check table (private, never shown): SYS-10 Played in Studio: earn, spend, rejoin and confirm the data kept\n- Official docs (offline): `ms_roblox_docs` holds the official Roblox Creator Docs and Luau docs offline (about 2,260 pages: every engine class, enum, datatype and library, plus the guides). Before quoting a limit, a price rule or a purchase flow, search the guides (data stores, developer products, passes, subscriptions, teleports, MemoryStore, MessagingService) and cite the page; confirm MarketplaceService, DataStoreService and TeleportService calls with action api, and run action check on the scripts.\n- Ready-made systems: Before writing a common system from scratch, open the kit index with `ms_skill_reference` (skill_id game-systems, action index, then read INDEX.md). It lists tested starting scripts from Brickwire (MIT): obby stages and kill bricks, jump and speed pads, teleporters, coins, round loop, saved stats, daily reward, shop, inventory, HUD, menus, toasts, day and night, NPC dialog, VFX presets, camera fly-through and the cutscene module with case, egg, dice, event and story scenes.\n- Ready-made systems: Read the closest file, then adapt it: use the project's names, style, currency and data code, replace every {{KEY}} with a real value, and keep one system per job instead of adding a second copy. Never paste a kit unread, and never pretend a kit was run in Studio; it was only run in a Luau VM with a stubbed Roblox API.\n- Ready-made systems: Where a kit is simpler than these rules, the rules win and you upgrade it: UpdateAsync with session locking instead of Get/SetAsync for player data, an idempotent ProcessReceipt for real purchases, validated and rate-limited remotes. The shop kit moves in-game currency only.\n- Cutscenes and reveals (cases, eggs, dice, events, story): Decide the result on the server first (weighted roll with the reused Random, reward granted and saved), then send the result to the client, which only shows it. The show never decides anything and a skipped show still grants the reward.\n- Cutscenes and reveals (cases, eggs, dice, events, story): Build a timeline of beats: camera moves, subtitles, sound, shake, flash, colour, VFX. Store the original camera type, camera subject and control state before starting and restore them on finish, on Skip, on character death, on leaving, and on any error. Never leave the player stuck with a Scriptable camera or disabled controls.\n- Cutscenes and reveals (cases, eggs, dice, events, story): Always show a Skip button that works from the first frame and on touch and gamepad. Keep common results short (a few seconds); the rarer the result, the longer the pause and the stronger the shake, flash and light rays. Epic and above get a full-screen reveal; Mythic and above may use a false ending before the real one. Keep subtitles readable (contrast, size, safe area) and use only sound ids you can confirm play live.\n- Cutscenes and reveals (cases, eggs, dice, events, story): Read cutscene.luau, cut-client.luau and the matching scene file from the kit index instead of rebuilding the timeline; check the scene length, Skip, sounds, subtitle readability, camera restore and the server roll before saying it is done."], ["npc-pathfinding", "=== NPC-PATHFINDING - use for: Always use for NPCs, enemies, chasers, patrols, pets, followers and any pathfinding.\n- Server owns the NPC: Run NPC logic and movement on the server. Set network ownership of the NPC's parts to the server with SetNetworkOwner(nil) so a nearby player cannot take it over or exploit its physics. Never put NPC logic in client scripts.\n- Server owns the NPC: One manager module owns all NPCs with one shared update loop, not a while loop per NPC. Stagger path recomputes across frames.\n- Server owns the NPC: Use a state machine (Idle, Patrol, Investigate, Chase, Attack, Search, Flee) with explicit transitions and one active state.\n- PathfindingService (official docs): CreatePath takes AgentRadius (default 2), AgentHeight (default 5), AgentCanJump (default true), AgentCanClimb (default false), WaypointSpacing (default 4) and Costs. Set radius and height to the NPC's real size; a mismatch makes paths fail or clip walls.\n- PathfindingService (official docs): Call path:ComputeAsync(start, goal) inside pcall and use the path only when path.Status is Enum.PathStatus.Success. On failure fall back: wander, go to the last known position, or back off with a cooldown.\n- PathfindingService (official docs): Compute while the NPC is on the ground; computing mid-fall gives a wrong start position.\n- PathfindingService (official docs): Walk waypoints with Humanoid:MoveTo or Humanoid:Move, advance on MoveToFinished or a distance check, and when a waypoint Action is Jump make the humanoid jump. Give each waypoint a timeout (start around 2 seconds, tune it) so a stuck NPC recomputes.\n- PathfindingService (official docs): Connect path.Blocked, recompute only if the blocked index is at or ahead of the current waypoint, and disconnect the old connection before recomputing.\n- PathfindingService (official docs): Limits: start to goal direct distance at most 3000 studs, about 20000 node budget (huge open maps and mazes can fail), and conflicting settings fail (needing a jump with AgentCanJump false).\n- PathfindingService (official docs): Costs: Enum.Material names or PathfindingModifier labels as keys; math.huge blocks a material. PathfindingModifier on an anchored non-colliding part with PassThrough lets the NPC route through doors it can open. PathfindingLink between two Attachments handles ladders, vents and teleports; run custom logic when the waypoint label matches.\n- PathfindingService (official docs): In streaming games target parts that are loaded and wait for the area before pathing.\n- Performance and fairness: Do not recompute every frame. Recompute when the target moves more than a threshold (start around 6 studs) or on a timer (start around 0.25 to 0.5 seconds while chasing). Starting values, tune them.\n- Performance and fairness: Cap simultaneous path computations and queue the rest. Sleep NPCs far from every player.\n- Performance and fairness: On straight open ground with nothing in the way, move directly and skip the path.\n- Performance and fairness: Destroy the NPC and disconnect its connections and loops when it dies or is removed.\n- Perception: Sight: distance check, field-of-view angle using the dot product, then workspace:Raycast with RaycastParams that excludes the NPC and non-blocking parts. All on the server.\n- Perception: Hearing: sprinting, jumping and item use make noise; the NPC investigates the last noise position, not the player's live position.\n- Perception: Keep a last known position and a memory timer. After losing the player: go there, search, return to patrol. The NPC must not know the exact position through walls.\n- Horror NPCs: Fair threat: telegraph with sound, light flicker or animation before it reaches the player, and give the player a way to escape or hide (hiding spots, doors, broken line of sight). An unavoidable instant kill with no warning is a bug.\n- Horror NPCs: Pace tension: absence and patrol, then a hint, then a chase, then a cooldown. Add a grace period after a respawn and after a chase ends.\n- Horror NPCs: Chase speed at or slightly below player sprint, with stamina or doors creating tension. Speeds are named constants (the default walk speed is 16 studs per second).\n- Horror NPCs: Scare sounds and effects are triggered by the server through a rate-limited remote to the affected clients; the client plays them.\n- Horror NPCs: Never damage, kill or teleport a player on a client request. The server checks range, line of sight and a cooldown first.\n- Other NPC types: Pets and followers: follow at an offset behind the owner, teleport to the owner when the distance passes a limit (start around 40 studs), and tie lifetime to the owner.\n- Other NPC types: Shop and quest NPCs: ProximityPrompt interaction validated on the server (distance, quest state, inventory).\n- Other NPC types: Waves and spawners: cap alive count, spawn from fixed points with a cooldown, despawn on round end.\n- Raycast sight checks (official): the ray direction length sets the distance (max 15000 studs); a miss returns nil; RaycastParams uses FilterDescendantsInstances with Exclude or Include; parts with CanQuery false are ignored. Humanoid WalkSpeed is client-replicated, so for NPCs the server owns it and for players the server sanity checks speed.\n- Track NPCs with CollectionService tags (added signal plus GetTagged for existing ones) so a manager can find, update and clean them without scanning Workspace.\n- Docs (look here before guessing an API; class pages are at https://create.roblox.com/docs/reference/engine/classes/<ClassName>): https://create.roblox.com/docs/characters/pathfinding; https://create.roblox.com/docs/workspace/raycasting; https://create.roblox.com/docs/reference/engine/classes/Humanoid; https://create.roblox.com/docs/reference/engine/classes/CollectionService\n- Pathfinding setup: Create a path with `PathfindingService:CreatePath(params)`; `FindPathAsync` and the old compute methods are deprecated. Agent parameters and defaults: AgentRadius 2 (studs), AgentHeight 5, AgentCanJump true, AgentCanClimb false (truss), WaypointSpacing 4 (`math.huge` removes middle waypoints), Costs nil. Set radius and height from the real NPC (R15 around 2.75 and 5.25 with a bit of room); too small and it clips corners, too large and doorways fail.\n- Pathfinding setup: `path:ComputeAsync(start, goal)` yields; wrap it in `pcall` and check `path.Status == Enum.PathStatus.Success` before `path:GetWaypoints()`. Each waypoint has Position, Action (Walk or Jump) and Label. A failure usually means: distance over 3000 studs, the 20000 node budget used up (large open maps or mazes), a goal reachable only by jumping while AgentCanJump is false, an AgentHeight larger than the gaps, or a goal on a wall or inside a part. Compute from the ground, since a start in the air is moved to the nearest valid point.\n- Pathfinding setup: Visualise it: in Studio turn on Navigation mesh, Pathfinding modifiers and Pathfinding links in the visualisation options and look before guessing why an NPC will not go somewhere.\n- Costs, modifiers and links: Material costs: `Costs = {Water = math.huge, CrackedLava = 100}`. Every material is 1 by default; `math.huge` makes it forbidden; a large finite number (100 to 1000) makes it a last resort. For regions use an anchored, `CanCollide = false` part with a `PathfindingModifier` whose `Label` matches a key in Costs. Keep `CanQuery` true on that part or it is ignored. `PassThrough = true` on a modifier makes a part ignored so a path goes through it (a zombie that can hear the player behind a door).\n- Costs, modifiers and links: Links: a `PathfindingLink` joins two Attachments (`Attachment0`, `Attachment1`) that are otherwise unreachable (a boat, a teleporter, a ladder, a gap); set `Label`, give that label a cost in Costs, and in your move loop check `waypoint.Label` to run the custom action instead of walking. Ladders and truss need `AgentCanClimb` or a link. Do not rely on `AgentRadius` alone to keep NPCs out of narrow gaps; block them with a modifier.\n- Moving along a path: Move with `Humanoid:Move(direction)` or `MoveTo` per waypoint, treat a waypoint as reached when within about 2 to 3 studs horizontally (do not wait only for `MoveToFinished`, which can time out and stutter), jump when the waypoint Action is Jump, and add a stuck timeout per waypoint (about 2 to 3 seconds) that recomputes. Limit repaths: wait about 0.2 s before recomputing after an error, cap retries, and only recompute when the target moved a meaningful distance or the path is blocked, not every half second.\n- Moving along a path: Connect `path.Blocked` and recompute only if the blocked waypoint index is at or ahead of the current waypoint. Reuse one path object per NPC, remove debug parts from the loop, and skip the first one or two waypoints of a fresh path if the NPC steps backwards. If an NPC stutters: set network ownership to the server (`SetNetworkOwner(nil)` on the root part after it is assembled and welded), make sure the run animation loops, avoid `wait()` polling (use `task.wait()` or Heartbeat), and avoid heavy per-waypoint yielding. Use `Humanoid:Move` steering if `MoveTo` keeps pausing.\n- Moving along a path: Streaming enabled: a client script may fail to see a destination that is not streamed in; compute on the server, or target a part inside a persistent model and wait for `Workspace.PersistentLoaded`.\n- Senses and detection: Sight is four cheap tests in order: distance (magnitude), field of view (dot product of the NPC's `LookVector` and the unit direction to the target against `math.cos(math.rad(fov/2))`; do not mix degrees and radians), line of sight (a `workspace:Raycast` from the eyes to the target's head and torso with `RaycastParams` excluding the NPC), and only then react. A single ray to the root misses crouching or partly hidden players, so test two or three points. Avoid `Touched` for detection, it is unreliable.\n- Senses and detection: Throttle: sense a few times a second (every 0.1 to 0.25 s, staggered between NPCs), check distance first and skip far targets, and share one loop for all NPCs. Hearing: players make noise events (running, jumping, gunshots) with a radius; the NPC investigates the position, not the player. Memory: remember the last seen position and a timer so the NPC searches, then gives up.\n- State machines for NPCs: Use a table of states, each with Enter, Update(dt) and Exit, and one `transition(name)` function that calls Exit then Enter. Typical states: Idle, Patrol, Investigate, Chase, Attack, Search, Flee. Transitions come from events (saw player, lost player, took damage, reached point), with hysteresis (a longer range to lose a target than to gain it) so it does not flicker.\n- State machines for NPCs: Keep one manager updating all NPCs from one Heartbeat loop with a per-NPC budget; do not run a loop per NPC. For larger brains use a state machine for the main activity and a small behaviour tree or utility scoring inside a state. Clean up on death (disconnect events, cancel tasks, release the path). Add a debug text above the head showing the state while testing.\n- Horror and stalker AI: Split the brain in two. A director tracks the player and tension and decides when the monster may pressure, hunt or back off; the monster itself only reacts to senses (sight, sound, last known position). The monster must not cheat: it finds the player through the same senses the player can see and hear, and the player gets readable costs (running is loud, hiding works, light attracts).\n- Horror and stalker AI: Build tension in cycles of build-up, peak and release: after a peak give the player breathing room (the monster loses interest, retreats, or patrols elsewhere), never spam scares, vary patrol routes, and delay a blocked scare rather than cancel it. Telegraph danger with audio, light flicker and distant footsteps before contact. Never let the monster teleport onto a player or hit through walls. Test that a careful player can always escape or hide.\n- Scaling NPCs: Pool complex NPCs instead of creating and destroying them; reset all state on reuse (health, attributes, velocity, animations) and set `Humanoid.BreakJointsOnDeath = false` for pooled ones. Fewer Humanoids: use an `AnimationController` with anchored or CFrame movement for simple mobs, and disable unused Humanoid states (Climbing, Swimming, Ragdoll, FallingDown). Think at a fixed 5 to 10 Hz, staggered, and skip NPCs far from every player. Share a path between NPCs heading to the same goal; use flow fields or grids for hordes.\n- Scaling NPCs: Let clients animate NPCs (the server sets an attribute like `State = 'Run'` and clients play tracks). Fewer parts per NPC (MeshParts), no per-frame server property changes. Hundreds of purely cosmetic NPCs (crowds, ambient animals) are simulated on clients from a server seed; nothing gameplay-related may depend on them. Heavy steering or flocking math goes in `--!native` modules or Parallel Luau Actors (read-only in the desynchronised phase, write after `task.synchronize()`).\n- Talking to the player: The user wants plain input and plain output, like any player or developer: they ask for a thing, they get the thing. Never mention skills, standards, checks, rule codes, ids, budgets or internals.\n- Talking to the player: Reply in one to three short plain sentences: what is done and, only if needed, one thing to try or one thing you could not confirm. No lists of rules, no tables, no process notes.\n- Talking to the player: Do every check yourself and fix failures before replying. Never claim it works or looks good unless you ran it or measured it.\n- Check table (private, never shown): NPC-1 Server-owned with network owner set; no client authority\n- Check table (private, never shown): NPC-2 Agent size matches the model; path status checked\n- Check table (private, never shown): NPC-3 Blocked, stuck and no-path cases handled\n- Check table (private, never shown): NPC-4 Recompute throttled; far NPCs sleep; one shared loop\n- Check table (private, never shown): NPC-5 Perception uses server raycasts and last known position\n- Check table (private, never shown): NPC-6 State machine has clean transitions and cleanup\n- Check table (private, never shown): NPC-7 Horror threats are telegraphed and escapable; damage validated on the server\n- Check table (private, never shown): NPC-8 Watched in Studio: path, jump, blocked door, chase, lose player\n- Official docs (offline): `ms_roblox_docs` holds the official Roblox Creator Docs and Luau docs offline (about 2,260 pages: every engine class, enum, datatype and library, plus the guides). Confirm PathfindingService, Path, Humanoid and AnimationController members with action api (agent parameters, Costs, PathfindingModifier, PathfindingLink) and read the Pathfinding guide (search 'pathfinding') before tuning agents; run action check on NPC scripts."], ["vfx-assets", "=== VFX-ASSETS - use for: Always use when adding or improving visual effects, particles, beams, trails, explosions, hit effects, lighting, atmosphere, post-processing, camera shake, sound, or Toolbox and Creator Store assets in a Roblox game.\n- Mandatory standard for Roblox visual effects: particles, beams, trails, mesh effects, lights, lighting mood, post-processing, sky, camera feedback, sound and imported assets. Built from the official Roblox docs (particle emitters, beams, trails, lighting, atmosphere, post-processing, performance, audio) and community practice (DevForum VFX threads, lightning and shake modules, PartCache). The checks are internal; the player gets a short plain summary.\n- Core VFX: Effects are cosmetic and run on the client. The server sends one small, rate-limited event (effect name, position or target, maybe a seed) and each client builds the effect itself. No gameplay state depends on an effect. Never tween effect parts from the server (server tweens replicate every frame).\n- Core VFX: Design every effect in three beats: anticipation (a short telegraph or wind-up), the main hit (the biggest, brightest moment, usually under 0.3 s), and residue (a fading tail of smoke, sparks, glow or debris). Layer 3 to 5 simple elements (flash, core, sparks, smoke, light) rather than one complicated emitter. Vary lifetime, size, speed and rotation with ranges so no two particles match.\n- Core VFX: Readability first: the effect must show what happened (who, where, how big) without hiding the player's character, enemies or UI. Bright additive colours on dark scenes, darker or saturated colours on bright scenes. Keep one colour story per effect (two or three hues), brightest in the middle and dimmer at the edges.\n- Core VFX: Build from a template: put each effect in `ReplicatedStorage` as an `Attachment` (or a small part) with its emitters, beams, lights and sounds, set to `Enabled = false` or `Rate = 0`. At runtime clone it, place it, play it, and clean it up. Never build emitters property by property in a loop at runtime; changing emitter properties while playing can hurt performance (official).\n- Core VFX: One-shot effects use `emitter:Emit(count)` with the emitter's `Rate` at 0, and call `Debris:AddItem(clone, longest lifetime + 0.5)` (or `task.delay` then `Destroy`). Continuous effects use `Enabled`; to stop one, set `Enabled = false`, let existing particles finish (or `Clear()` for an instant stop), then destroy it. Pool anything that spawns more than a few times a second.\n- Core VFX: Scale with quality: `:Emit()` does not get Roblox's automatic graphics-level thinning, so for heavy bursts scale the count by the client's graphics level (read `settings().Rendering.QualityLevel` and map it to a 0.3 to 1 factor) and cap how many effects can play at once. Test every effect at the lowest and the highest Studio quality level.\n- Core VFX: Never invent `rbxassetid` numbers. Textures and sounds must come from the project, from the user, from `search_asset` / the Creator Store results you confirmed load, or from Roblox's own tutorial ids you re-confirm. If a texture does not load, fall back to the default sparkle texture or a plain shape, not an empty box.\n- Core VFX: Check the real result: play it in Studio (Play), look at it at a distance and close, with the camera moving, at day and night lighting, and read the Output. Anything you did not see run is reported as untested.\n- Toolbox and Creator Store assets (official guidance): Check the creator and rating, and inspect an asset before inserting it.\n- Toolbox and Creator Store assets (official guidance): Some assets include scripts that run on their own. Read every script in a model before use, delete scripts you do not need, or use Disable Scripts on the object.\n- Toolbox and Creator Store assets (official guidance): Prefer assets with no scripts and write the behaviour yourself following code-quality.\n- Toolbox and Creator Store assets (official guidance): Check part count and texture sizes before adding; heavy models cause lag.\n- Toolbox and Creator Store assets (official guidance): Never invent an asset id. If you cannot confirm an id loads, say so and use a placeholder.\n- Toolbox and Creator Store assets (official guidance): Store used models in ServerStorage (server only) or ReplicatedStorage (clients need them) and clone at runtime.\n- Docs (look here before guessing an API; class pages are at https://create.roblox.com/docs/reference/engine/classes/<ClassName>): ParticleEmitter, Beam, Trail, Attachment, Lighting, Atmosphere, Sky, Clouds, BloomEffect, ColorCorrectionEffect, DepthOfFieldEffect, SunRaysEffect, BlurEffect, PointLight, SpotLight, Highlight, Debris, Sound, SoundGroup, TweenService, RunService, ContentProvider, AnimationTrack, Camera, MaterialService; guides https://create.roblox.com/docs/effects/particle-emitters and https://create.roblox.com/docs/performance-optimization/improve\n- Audio: Two systems exist: the Audio API (`AudioPlayer` wired to `AudioEmitter` or `AudioDeviceOutput`, with effects such as `AudioReverb`, `AudioEqualizer`, `AudioCompressor` in the chain) and classic `Sound`. Follow what the project uses; do not mix both for one feature. For 3D put an `AudioEmitter` on the part; with `SoundService.AcousticSimulationEnabled` (Audio API) walls muffle sound and rooms reverb, and `BasePart.AudioCanCollide = false` stops a part blocking it.\n- Audio: Sounds started on the client are heard only by that client (UI clicks, music, feedback); sounds started on the server replicate to everyone, so prefer a remote telling clients to play locally, which also respects each player's volume. Preload only critical sounds with `ContentProvider:PreloadAsync`. Pool frequently played sounds. A sound in a part that streams out stops, so keep ambience in persistent models or `SoundService`. Give players separate Music and SFX volume sliders and a mute.\n- Audio: Audio assets must be owned by the experience owner or shared with it, or free-to-use Creator Store audio; otherwise they fail with permission errors in the Output. `AudioTextToSpeech.AutoLocalize` translates text per player; turn it off for names and chants.\n- Lighting and effects (engine facts): `Lighting.LightingStyle` is `Realistic` or `Soft` (stylised) and replaces the superseded `Technology`; `Atmosphere` replaces fog; animate `ClockTime` on each client from `workspace:GetServerTimeNow()` instead of replicating it. Limit shadow-casting lights; `Highlight` count is limited. `Explosion` sets off physics: for visual-only set `DestroyJointRadiusPercent = 0` and `BlastPressure = 0`. Spawn cosmetic effects on clients and destroy or pool them. `ParticleEmitter:Emit(n)` for bursts; `Beam` for lasers and ropes; `Trail` for swords and projectiles.\n- Talking to the player: The user wants plain input and plain output, like any player or developer: they ask for a thing, they get the thing. Never mention skills, standards, checks, rule codes, ids, budgets or internals.\n- Talking to the player: Reply in one to three short plain sentences: what is done and, only if needed, one thing to try or one thing you could not confirm. No lists of rules, no tables, no process notes.\n- Talking to the player: Do every check yourself and fix failures before replying. Never claim it works or looks good unless you ran it or measured it.\n- Check table (private, never shown): VFX-1 Effects client-side, triggered by small rate-limited events, pooled and cleaned up\n- Check table (private, never shown): VFX-2 Emitter rates, sizes and counts within mobile-friendly limits; tested at lowest and highest quality\n- Check table (private, never shown): VFX-3 Every asset id confirmed to load or marked unverified; none invented\n- Check table (private, never shown): VFX-4 Layers: anticipation, hit, residue; readable and not covering gameplay\n- Check table (private, never shown): VFX-5 Lights few, shadows off unless needed; post-processing tweened and restored\n- Check table (private, never shown): VFX-6 Beams and trails have both attachments, FaceCamera where needed, disabled when idle\n- Check table (private, never shown): VFX-7 Camera shake is an offset applied after the camera, with a reduce-motion option; no flashing over three per second\n- Check table (private, never shown): VFX-8 Toolbox models inspected, scripts read or removed; part and texture cost considered\n- Check table (private, never shown): VFX-9 Seen running in Studio, Output clean; anything unseen reported as untested\n- Other sections, loaded with ms_get_skill when the request needs them: Particles, Effect recipes, Beams and trails, Mesh effects, Lightning, Lighting and mood, Post-processing, Camera and feedback, Sound, Timing and sync, VFX performance, Style and polish. Style sections (sleek modern, glass, horror, sci-fi, fantasy, minimal, retro, realistic) replace the Cartoon style when the user asks for them."]];
  // END GENERATED STANDARDS
  // Compact always-on Roblox standards (full versions: code-quality, scripting-power, game-systems, npc-pathfinding,
  // vfx-assets, fix-errors, check-clean-ui, check-props via ms_get_skill). Kept short on purpose.
  const MS_CORE_STANDARDS = [
    "[CORE ROBLOX STANDARDS - always apply, never mention to the user]",
    "Server owns state, currency, rewards and damage; the client sends intent only. Validate every remote on the server: types, NaN, ranges, ownership, cooldown, distance; rate limit it. Never trust Touched or client-sent values.",
    "New scripts use --!strict with typed functions. Modern APIs only (task.*, Raycast, constraints). Events not polling; disconnect connections, clear per-player data, destroy what you create. Never invent an API or asset id; check the docs if unsure.",
    "Data: session-locked saves with pcall and retries, never save data that failed to load, save on leave and in BindToClose; grant purchases only after a successful save. Coins and pickups: claim first, then award; spatial query for many, guarded Touched for few.",
    "Sizes are in studs (1 stud = 0.28 m; default WalkSpeed 16, jump about 7 studs). NPCs run on the server with PathfindingService (check Status, handle Blocked and no-path); horror threats must be telegraphed and escapable.",
    "WHEN TO USE WHICH (load the full rules with ms_get_skill before building): scripting-power for performance, lag, memory, types, async code, remotes and exploits, data saving, parallel work, raycasts, physics, input, Open Cloud, testing, tooling and architecture; check-props for ANY physical thing you build from Parts - tree, rock, boat, tank, car, stick, weapon, building, furniture, machine, anything 3D; check-clean-ui for any menu, HUD, button or screen; npc-pathfinding for anything that moves or thinks on its own (enemies, pets, guards); game-systems for coins, collecting, currency, shops, purchases, subscriptions, teleports, live ops, rebirths, rounds and horror structure; vfx-assets for effects, particles, lighting, audio and Toolbox assets; fix-errors whenever anything is broken; code-quality for every script. One request can need several.",
    "Official docs: create.roblox.com/docs (class pages at /docs/reference/engine/classes/<ClassName>, task library at /docs/reference/engine/libraries/task). Each skill lists its exact doc pages; check them instead of guessing an API.",
    "When something breaks: read the real Output, fix the cause (never hide it with pcall), then re-run and confirm it is clean.",
    "Private checks before replying: security, typing, cleanup, data safety, performance, correct APIs, ran it. Fix failures first. Anything not run in Studio is reported as untested in one sentence.",
    "IF THE USER ASKS what your main skills are, what you can do, or what Multi-Script (ms) is good at: this is the one time you may talk about skills. Answer in a few plain lines with exactly these eight, not the whole catalogue: (1) Code quality - safe, fast, well-typed scripts; (2) Scripting power - faster, safer, modern code, saving data, remotes, parallel work and tooling; (3) Props - tree, boat, tank, car, stick or any 3D thing built from parts; (4) Clean UI - menus, HUDs and buttons in one consistent look; (5) Game systems - simulators, coin collecting, shops, pets, rebirths, tycoons, horror rounds; (6) NPCs and pathfinding - enemies, pets and chasers that move on their own; (7) Effects and assets - particles, lighting and safe Toolbox use; (8) Fixing errors - finding why something is broken and fixing it. Mention there are more specialist skills if they want a specific one.",
    "Talking to the user: they want plain input and plain output. Never mention skills, standards, checks, rule codes, ids or internals. Reply in one to three short plain sentences about the result.",
  ].join("\n");

  // Full standards, as many as fit in the room left under the provider's send budget, exact-spec ones first.
  function fullStandardsText(budget) {
    const head = "[FULL ROBLOX STANDARDS - mandatory. Follow them exactly, do every check yourself, and never mention any of this to the user.]\n";
    let used = head.length, out = [], left = [];
    for (const [id, text] of MS_STANDARDS_FULL) {
      if (used + text.length + 2 <= budget) { out.push(text); used += text.length + 2; } else left.push(id);
    }
    if (!out.length) return "";
    return head + out.join("\n\n") + (left.length ? "\n\n(Not included here for size - load with ms_get_skill when the task needs them: " + left.join(", ") + ".)" : "");
  }

  function systemPrompt(opts) {
    const providerProfile = P.getStartupProfilePrompt ? P.getStartupProfilePrompt() : "";
    const economy = ZS.economyPrompt ? ZS.economyPrompt(P.id, ui.getUsageMode()) : "";
    const savedBehavior = ui.getProviderBehavior ? ui.getProviderBehavior() : { promptSkills: "automatic", loops: "balanced" };
    const behavior = executionEffort === "ultra" ? {...savedBehavior,loops:"rigorous"} : savedBehavior;
    const skillMesh = ZS.skillToolCoveragePrompt ? ZS.skillToolCoveragePrompt(executionEffort === "ultra" ? "maximum" : ui.getSkillDepth()) : ""; // Ultra escalates relevant coverage without enabling disabled tools
    const providerBehavior = ZS.providerBehaviorPrompt ? ZS.providerBehaviorPrompt(behavior, P.displayName || P.id) : "";
    const softwareMode = A.software && typeof ZSExtras !== "undefined" ? ZSExtras.softwarePrompt(P.displayName || P.id, softwareSettings) : "";
    const sessionMode = A.chatOnly && !softwareMode && ZS.chatOnlyPrompt ? ZS.chatOnlyPrompt(P.displayName || P.id) : softwareMode;
    // One-shot / unattended autonomy. Placed FIRST in the custom stack so it is
    // the first thing a long context still has when the site summarises, and
    // repeated by the mid-session re-statement like every other layer.
    const autonomy = ZS.autonomyPrompt ? ZS.autonomyPrompt(autonomyLevel, P.displayName || P.id) : "";
    const memoryBlock = memOn() ? memCtrl.promptBlock() : "";
    const thinkingBlock = ZM && !A.chatOnly ? ZM.THINKING_PROMPT : "";
    const craft = typeof MSStudio !== "undefined" ? MSStudio.skillPrompt(A.lastUserText, executionEffort)+"\n\n"+MSStudio.installedSkillsPrompt(activeCustomSkills()) : "";
    const robloxOn = activeEngineIds().includes("roblox");
    // The full text goes in once, at startup; later re-statements carry only the short block (the director still loads full rules per task).
    const coreStandards = robloxOn ? (opts && opts.full && opts.fullBudget > 0 ? fullStandardsText(opts.fullBudget) + "\n\n" : "") + MS_CORE_STANDARDS : "";
    const custom = [autonomy, executionEffortPrompt(), coreStandards, MSStudio.criticPrompt(criticSettings), craft, sessionMode, blenderWorkspaceInstructions(), economy, skillMesh, providerBehavior, thinkingBlock, memoryBlock, ui.getCustomPrompt()].filter(Boolean).join("\n\n");
    const base = ZS.buildSystemPrompt({
      siteName: P.displayName,
      customPrompt: custom,
      providerNotes: P.promptExtra || "",
      // Engine-aware: the prompt's connection paragraph, project-memory section
      // and first-action instruction all depend on which engines are really here.
      engines: activeEngineIds(),
      engineAccess:!A.chatOnly||!!(A.software&&softwareSettings.addons?.engines),
    });
    // Keep saved Notion preference metadata near the top and the marker first for
    // session detection, then the minimal real-model request, then the complete
    // provider-agnostic Multi-Script tools/skills prompt.
    const prompt = providerProfile ? base.replace(`${ZS.SYS_MARKER}\n`, `${ZS.SYS_MARKER}\n${providerProfile}\n\n`) : base;
    return prompt;
  }

  function startupPrompt() {
    // A/B transport checks retain the compact handshake: full specialist rules
    // belong to the task that needs them, not an idle initialization turn.
    const prompt=systemPrompt()+"\n\n[STARTUP TRANSPORT CHECK]\nThis turn initializes Multi-Script; do not begin building, researching or critiquing anything yet. First emit exactly {\"command\":\"list_commands\",\"params\":{}}. After the real catalog result, acknowledge readiness and wait for the user's task. Keep every local command as ordinary reply JSON, never a native provider tool call.";
    const providerCap=P.startupCharBudget||P.sendCharBudget||50000;
    const cap=Math.min(providerCap,ZS.limits?ZS.limits.sendBudget(providerCap):providerCap);
    if(prompt.length>cap)throw Error(`Startup needs ${prompt.length.toLocaleString()} characters but this session allows ${cap.toLocaleString()}. Shorten custom instructions or reduce enabled startup context; raise a smaller custom message limit if applicable. Nothing was sent or silently cut.`);
    const lines=prompt.split("\n").length;if(P.startupLineBudget&&lines>P.startupLineBudget)throw Error(`Startup has ${lines} lines but this composer budget is ${P.startupLineBudget}. Shorten custom instructions; nothing was sent or silently cut.`);
    return prompt;
  }

  // ── Periodic system-prompt re-injection (opt-in, per provider) ────────────
  // Some sites aggressively summarise their own context mid-conversation. When
  // that happens the model keeps the gist of the task but loses the MECHANISM:
  // it forgets that an extension reads its replies and executes them, and starts
  // answering "I can't invoke those commands in this session" while the
  // extension sits there ready and waiting. Observed repeatedly on ChatGPT.
  //
  // The periodic tools reminder does NOT fix this: it re-anchors command NAMES,
  // but it never restates that the commands actually run. So providers that need
  // it set `resendSystemEvery`, and the whole prompt goes back in.
  //
  // Delivery rides on the next injected tool result rather than costing its own
  // message - free and invisible. But that channel dries up in exactly the case
  // this exists for (a model that has forgotten it can call tools stops calling
  // them, so no results flow), so a fallback sends it as its own masked turn
  // once the window has elapsed with nothing to piggyback on.
  const RESEND_SYS_EVERY = P.resendSystemEvery || 0;
  // Injected tool results get their own, larger budget (see sysResendDue).
  const RESEND_SYS_EVERY_RESULTS = 12;

  // How much conversation has accumulated since the operating instructions were
  // last stated. PERSISTED per conversation, because both simpler designs failed
  // in opposite directions - each caught live on 2026-08-14:
  //
  //  - An in-memory counter RESETS on every page reload, while the session
  //    itself survives one (A.started is persisted). After an F5, or a silent
  //    Chrome extension auto-update, the tally restarted and the re-statement
  //    could be postponed indefinitely.
  //  - Walking the DOM back to the last SYS_MARKER turn is reload-proof but
  //    UNDER-counts badly: these sites virtualize. Measured on a real ChatGPT
  //    session that had long passed the threshold - only 12 turns were rendered,
  //    the marker was not among them (so the walk silently counted from the top
  //    of the window) and it saw 5 injected results instead of the true total.
  //
  // Counting at INJECTION time and persisting sidesteps both: it is exact, and
  // virtualization cannot erase it. The DOM walk is kept as a floor, since a
  // conversation that visibly shows the threshold is due no matter what storage
  // says (e.g. a session adopted from another device, or storage cleared).
  const sysKey = () => `zsSys:${P.conversationKey() || "new"}`;
  let sysCount = { users: 0, results: 0 };
  let sysCountKey = "";

  // Hydrate from storage. Only meaningful at startup / on a conversation switch;
  // it never overwrites counts already accumulated in this tick's memory (a
  // bump that landed while the async read was in flight must not be lost).
  async function loadSysCount() {
    const k = sysKey();
    if (k === sysCountKey) return sysCount;
    sysCountKey = k;
    const local = sysCount;
    sysCount = { users: 0, results: 0 };
    try {
      const r = await new Promise((res) => chrome.storage.local.get(k, res));
      const saved = r && r[k];
      if (saved) sysCount = {
        users: Math.max(saved.users || 0, local.users || 0),
        results: Math.max(saved.results || 0, local.results || 0),
      };
    } catch {}
    return sysCount;
  }
  function saveSysCount() {
    try { chrome.storage.local.set({ [sysCountKey]: sysCount }); } catch {}
  }
  // Increment SYNCHRONOUSLY, persist asynchronously. sysResendDue() reads
  // sysCount in the same tick as the bump that should trip it, so deferring the
  // increment into the storage promise made the tally lag a full turn behind and
  // the threshold was never seen at the moment it mattered (caught live: 12 tool
  // results, counter still reading 11, no rider). Storage is a durability
  // mechanism here, not the source of truth for the current tick.
  function bumpSys(field) {
    if (!RESEND_SYS_EVERY) return;
    if (sysCountKey !== sysKey()) { sysCountKey = sysKey(); }
    sysCount[field]++;
    saveSysCount();
  }
  function resetSysCount() {
    sysCount = { users: 0, results: 0 };
    saveSysCount();
  }

  // Lower bound read straight from what is on screen (see above).
  function sinceLastSysInDom() {
    const items = P.allItems();
    let users = 0, results = 0;
    for (let i = items.length - 1; i >= 0; i--) {
      const it = items[i];
      const txt = P.classifyText(it, ".zs-chip");
      // The bootstrap turn and every rider both carry the marker - either one
      // means the rules were fully stated here, so stop counting.
      if (ZS.hasSysMarker(txt)) break;
      if (!P.isUserItem(it)) continue;
      if (ZSParse.isInjectedFeedback(txt)) results++;
      else users++;
    }
    return { users, results };
  }

  function sinceLastSys() {
    const dom = sinceLastSysInDom();
    return {
      users: Math.max(sysCount.users, dom.users),
      results: Math.max(sysCount.results, dom.results),
    };
  }

  // A re-statement is owed once EITHER budget is spent. Two triggers because
  // they measure different things: user turns track a long back-and-forth, while
  // injected results track context VOLUME - and volume is what actually makes
  // the site summarise. Measured live on 2026-08-14: in a real session 5 of the
  // 6 "user" turns were injected tool results and only ONE was typed by Seb, so
  // a user-turn-only trigger sat at 1/6 while five full tool payloads had
  // already landed. The results budget is the one that fires in practice.
  function sysResendDue() {
    if (!RESEND_SYS_EVERY) return false;
    const { users, results } = sinceLastSys();
    const due = users >= RESEND_SYS_EVERY || results >= RESEND_SYS_EVERY_RESULTS;
    // Logged sparsely on purpose: this is consulted on EVERY tool result, and an
    // entry each time would flush the 300-slot diag ring of everything else -
    // exactly the history you need when something goes wrong. The verdict turn
    // and every 4th result is enough to reconstruct the tally.
    if (due || results % 4 === 0) {
      diag("sys.tally", {
        users, results, due,
        mem: `${sysCount.users}/${sysCount.results}`,
        need: `${RESEND_SYS_EVERY}u ${RESEND_SYS_EVERY_RESULTS}r`,
      });
    }
    return due;
  }
  // Attach the prompt to an outgoing tool result IF it fits. The result is never
  // truncated to make room: the passenger is dropped and the flag stays raised,
  // so it rides the next result instead. A tool result the model is waiting on
  // is always worth more than a reminder.
  function withSysResend(text) {
    if (studioSettingsDirty) {
      const update = "\n\n" + activeStudioInstructions();
      const cap = ZS.limits ? ZS.limits.sendBudget(P.sendCharBudget) : (P.sendCharBudget || Infinity);
      if (text.length + update.length <= cap) { A.pendingSettingsKey=studioSettingsFingerprint(); return text + update; }
    }
    if (!sysResendDue()) return text;
    const economyMode = ui.getUsageMode();
    if (economyMode !== "off" && ZS.compactSystemReminder) {
      const compact = "\n\n────────────────────────────────\n" + ZS.compactSystemReminder(P.id, economyMode);
      const cap = ZS.limits ? ZS.limits.sendBudget(P.sendCharBudget) : (P.sendCharBudget || Infinity);
      if (text.length + compact.length > cap) return text;
      const spent = sinceLastSys(); resetSysCount(); A.sysResendAt = Date.now();
      diag("sys.resendCompact", { via: "toolResult", chars: compact.length, ...spent });
      return text + compact;
    }
    const prompt = systemPrompt();
    const rider =
      "\n\n────────────────────────────────\n" +
      ZS.RESEND_MARKER + "\n" +
      "(System note from Multi-Script - an automatic re-statement of your operating " +
      "instructions, NOT a new request and NOT something to reply to. This conversation " +
      "may have been summarised, which drops the part explaining how you actually run " +
      "commands. To be explicit: the Multi-Script extension IS running in this page right " +
      "now, it DOES read your replies, and the commands below DO execute for real - the " +
      "results you have been receiving are proof of it. Keep using them exactly as " +
      "described. Just carry on with the task; do not acknowledge this note.)\n" +
      prompt;
    const cap = ZS.limits ? ZS.limits.sendBudget(P.sendCharBudget) : (P.sendCharBudget || Infinity);
    if (text.length + rider.length > cap) {
      // Stays due - the next (smaller) result carries it.
      diag("sys.resendDeferred", { result: text.length, rider: rider.length, cap });
      return text;
    }
    const spent = sinceLastSys();
    resetSysCount();
    A.sysResendAt = Date.now();
    diag("sys.resend", { via: "toolResult", chars: rider.length, ...spent });
    return text + rider;
  }

  // One full bootstrap prompt per visible chat. A model/profile selection is a
  // preference for the NEXT empty chat; it never injects a second system prompt
  // into the conversation currently in progress.
  const bootstrapClaims = new Set();
  const failedStartups=new Set();
  function saveFailedStartups(){try{chrome.storage.local.set({zsFailedStartups:[...failedStartups].slice(-300)});}catch{}}
  const bootstrapClaimKey = () => `${P.id}|${P.conversationKey() || "new"}`;

  // ════════════════════════════════════════════════════════════════════════
  //  SESSION BOOTSTRAP  ("Starting Up" animated chip, shown in the conversation)
  // ════════════════════════════════════════════════════════════════════════
  const START_WATCHDOG_MS = 480000;
  // ── Software Builder (W.I.P., 6.26) ───────────────────────────────────────
  // An engine-free session whose model builds real programs through the local
  // bridge's ms_ws_* tools, jailed to one workspace folder the user picked.
  // Off unless enabled in Settings → W.I.P.
  let softwareSettings = typeof ZSExtras !== "undefined" ? ZSExtras.sanitizeSoftware({}) : { enabled: false };
  try { chrome.storage.local.get("msSoftwareBuilder", (r) => { if (r && r.msSoftwareBuilder && typeof ZSExtras !== "undefined") softwareSettings = ZSExtras.sanitizeSoftware(r.msSoftwareBuilder); try { ui.updateStartGate(); } catch {} }); } catch {}
  function saveSoftwareSettings(next) {
    softwareSettings = ZSExtras.sanitizeSoftware({ ...softwareSettings, ...next });
    try { chrome.storage.local.set({ msSoftwareBuilder: softwareSettings }); } catch {}
    try { ui.updateStartGate(); } catch {}
    return softwareSettings;
  }
  async function configureSoftwareBridge() {
    const ready = await softwareBridgeReadiness(true);
    if (!ready.ok) return ready;
    const s = softwareSettings;
    const a = { enabled: !!s.enabled, allow_run: !!s.allowRun, mode: s.mode === "code" ? "code" : "build" };
    if (s.rootMode === "path" && s.root) a.root = s.root;
    if (s.projectsDir) a.projects_dir = s.projectsDir;
    return bg({ type: "call_tool", name: "ms_ws_configure", arguments: a, timeout: 15000 });
  }
  async function softwareBridgeReadiness(refresh = false) {
    let tools = A.toolList || [];
    if (refresh || !tools.length) {
      const r = await bg({ type: "list_tools" }).catch(() => null);
      if (r && r.ok && Array.isArray(r.tools)) tools = r.tools;
    }
    const names = new Set(tools.map((t) => bareToolName(t && t.name)));
    if (names.has("ms_ws_configure") && names.has("ms_ws_pick_folder") && names.has("ms_ws_status")) {
      return { ok: true };
    }
    const [snap, host, st] = await Promise.all([
      bg({ type: "terminal_snapshot", since: 0, limit: 1 }).catch(() => null),
      bg({ type: "host_info" }).catch(() => null),
      bg({ type: "status" }).catch(() => null),
    ]);
    const version = String((snap && snap.service && snap.service.bridgeVersion) || (st && st.bridgeVersion) || (A.bridge && A.bridge.bridgeVersion) || "");
    const root = host && host.ok && host.root ? String(host.root) : "";
    const running = st && st.bridgeRoot ? String(st.bridgeRoot) : "";
    const mine = String((st && st.extensionVersion) || (host && host.expectedBridgeVersion) || "");
    const wrongFolder = !!(running && root && running.replace(/[\\/]+$/, "").toLowerCase() !== root.replace(/[\\/]+$/, "").toLowerCase());
    const up = st && st.lastUpgrade && !st.lastUpgrade.ok ? st.lastUpgrade : null;
    let why = `Connected${version ? ` to bridge v${version}` : " bridge"}${mine && version && version !== mine ? ` (this extension is v${mine})` : ""}, but this process does not expose the Software Builder tools.`;
    if (running) why += ` It is running from ${running}${wrongFolder ? " - not the folder your launcher is registered for" : ""}.`;
    if (root) why += ` Launcher folder: ${root}.`;
    if (up && up.error) why += ` Automatic replacement failed: ${up.error}`;
    why += " Press Restart below - it stops every Multi-Script bridge on this PC, including old copies from other folders, and starts the current one. If it still fails, run " + ZS.setupCommand() + " from this Multi-Script folder.";
    return { ok: false, code: "bridge_upgrade_required", version, root, running, error: why };
  }
  async function startSession({chatOnly=false, software=false} = {}) {
    if (A.running || A.starting) return;
    if(A.started){ui.toast("This chat already has a session. Open a new chat to change modes.");return;}
    A.chatOnly=!!chatOnly || !!software;
    A.software=!!software && !!softwareSettings.enabled;
    const claimKey = bootstrapClaimKey();
    A.bootstrapClaimKey=claimKey;
    if (A.started || bootstrapClaims.has(claimKey)) {
      ui.toast("This chat already received the Multi-Script startup prompt. Open a new chat to start again.");
      return;
    }
    let bootstrapAccepted = false,bootstrapReady=false;
    // "Start session" is allowed ONLY on a blank conversation. Opening an
    // EXISTING conversation must never trigger the bootstrap.
    if (!chatOnly && !P.chatIsEmpty() && !A.started) {
      ui.toast("Open a new, empty conversation to start a session.");
      return;
    }
    A.userStopped = false;
    A.stop = false;               // clear any halt left by a prior aborted bootstrap
    // Snapshot any turn already on screen at session start (normally none on a
    // clean new chat; on a reload-restored generation it's the stray turn). The
    // auto-resume watchdog refuses to run a tool from this baseline turn so a
    // restored execute_luau can't leak into the freshly started conversation.
    A.bootBaselineId = P.lastAssistantId ? P.lastAssistantId() : null;
    A.starting = true;A.startBeganAt=Date.now();A.startStage=1;A.startPhase="Connecting tools and preparing the composer";
    const myGen = ++A.startGen;   // identity of THIS bootstrap
    A.startingKey = null;          // unknown until the conversation gets an id
    const alive = () => A.startGen === myGen; // false once superseded/aborted
    A.toolCallsSinceReminder = 0; // fresh reminder cadence for the new session
    ui.setStarting(true);
    ui.updateStartGate(); // refresh the bar into its "starting" state
    P.setInputLock(true); // block user input during bootstrap
    ui.inputCover(true);  // cover the composer ("Working…") for the WHOLE Starting Up
    // Single teardown for BOTH the normal exit and the watchdog below, so the bar,
    // the composer cover and the input lock can never be left stuck on "Starting…".
    const endStarting = () => {
      A.starting = false;A.startPhase="";
      A.startingKey = null;
      ui.setStarting(false);
      ui.inputCover(false); // lift the Starting Up composer cover
      P.setInputLock(false); // always unlock after bootstrap
      decorate.sweep();
    };
    // Hard ceiling: whatever step stalls (composer lookup, bridge call, a reply that
    // never renders), Starting… ends and the user is told, instead of spinning forever.
    const startWatchdog = setTimeout(() => {
      if (!alive()) return;
      diag("start.watchdog", { afterMs: START_WATCHDOG_MS });
      A.startGen++;            // supersede this bootstrap so its late steps no-op
      A.stop = true;           // unblocks any loop still polling (re-cleared below)
      if (!A.sendUnconfirmed) bootstrapClaims.delete(claimKey);
      endStarting();
      setTimeout(() => { A.stop = false; }, 1500);
      ui.banner("warn", "Startup timed out",
        `${P.displayName} did not finish the Multi-Script startup within ${Math.round(START_WATCHDOG_MS / 1000)}s. ` +
        `Open a new chat (or reload the page) and press Start again.`);
    }, START_WATCHDOG_MS);
    try {
      await bg({type:"ms_provider_pacing",action:"resume",provider:P.id,owner:"user-start"});
      if(!alive()) return;
      if (A.software) {
        await ensureTools(true);
        if (!alive()) return;
        // Do not use A.toolList as the Software Builder availability gate.
        // That list is intentionally filtered for the active chat/engine mode,
        // so a healthy bridge can be online while its ms_ws_* tools are absent
        // from this UI-facing snapshot. configureSoftwareBridge performs a live,
        // unfiltered bridge capability check and returns the precise recovery
        // action when the connected launcher is actually old.
        const cfg = await configureSoftwareBridge();
        if (!alive()) return;
        if (!cfg || !cfg.ok) {
          ui.banner("warn", "Software Builder could not start", String((cfg && (cfg.error || cfg.text)) || "The bridge did not accept the workspace settings."));
          return;
        }
      } else if (!A.chatOnly) {
        if(!await prepareBlenderCompanion(alive))return;
        await ensureTools(true); // native-engine sessions require a fresh exact catalogue
        if (!alive()) return;
        if (memOn()) { try { await memCtrl.refresh(""); } catch {} if (!alive()) return; }
        if (!A.toolList.length) {
          ui.banner("warn", "Bridge or engine offline", "Could not fetch MCP tools. Connect Roblox Studio, Unity, Godot, Blender, or another configured MCP engine—or use Start without engine.");
          return;
        }
      }
      let modeState = await P.ensureComposerReady("startup");
      if (!alive()) return;
      // A bot-check at startup no longer aborts the bootstrap: park until the
      // user clears it, then re-check the composer and carry on with the SAME
      // Start press. Multi-Script never solves the challenge itself.
      if (!modeState.ready && modeState.humanVerificationRequired) {
        const cleared = await awaitHumanVerification("startup");
        if (!alive()) return;
        if (cleared) {
          modeState = await P.ensureComposerReady("startup");
          if (!alive()) return;
        }
      }
      if (!modeState.ready) {
        if (modeState.humanVerificationRequired) {
          ui.banner("warn", "Human verification required",
            `Complete ${P.displayName}'s CAPTCHA or bot-check manually, then press Start again. Multi-Script never bypasses verification challenges.`);
        } else {
          ui.banner("warn", `${P.displayName} mode not ready`,
            `Could not switch ${P.displayName} to the required mode. Start a new chat or reload the page, then try again.`);
        }
        return;
      }
      // Learn the connected Roblox Studio ids BEFORE the model's first command.
      //
      // Roblox's MCP needs studio_id on every place-scoped command, and the model
      // has no way to know the value until it asks. Relying on the model to call
      // list_roblox_studios first is exactly what failed on arena.ai/DeepSeek:
      // those models go straight to a command, drop studio_id, and - with two
      // Studios attached - get "parameters.studio_id is required" instead of work.
      // Probing here costs one cheap round trip on the BACKEND (no model turn, no
      // visible message) and turns the whole class of failures into a silent
      // auto-fill. Best-effort by design: any error is ignored, because the
      // prompt still tells the model to discover the id itself when this fails.
      A.studios = [];
      try {
        // Chat-only ("Start without engine") has no engine to probe, and the call
        // can sit for its full 15s timeout when the bridge is up but Studio is not.
        const probe = !activeEngineIds().includes("roblox") ? null : await bg({ type: "call_tool", name: "list_roblox_studios", arguments: {}, timeout: 15000 });
        if (probe && probe.ok && probe.text && typeof ZSEngine !== "undefined" && ZSEngine.studiosFromBody) {
          const found = ZSEngine.studiosFromBody(probe.text);
          if (found.length) {
            A.studios = found;
            diag("studios.bootProbe", { count: found.length, ids: found.map((s) => s.id) });
          }
        }
      } catch (e) { diag("studios.bootProbe.error", { error: String(e && e.message || e) }); }
      if (!alive()) return;
      A.startStage=2;A.startPhase=P.displayName+" is initializing the session";ui.setStarting();
      const prompt = startupPrompt();
      bootstrapClaims.add(claimKey);
      const base = await submitAndGetBase(prompt, undefined, {settingsKey:studioSettingsFingerprint()});
      if (!alive()) return;
      // The site never took the startup prompt: stop here. (Waiting for a reply and
      // then declaring the agent ready is how a dead send looked like a hang.)
      if (!A.lastSendOk) {
        if (!A.sendUnconfirmed) bootstrapClaims.delete(claimKey);
        diag("start.sendFailed", { err: String(A.lastSendError || "").slice(0, 160) });
        if (!A.stop) {
          // submitAndGetBase already showed the "Message could not be sent" banner
          // (with composer diagnostics) in the normal failure path.
          if (!A.sendBannerShown) {
            ui.banner("warn", "Startup prompt was not sent", String(A.lastSendError || `${P.displayName} did not accept the message.`));
          }
        }
        return;
      }
      bootstrapAccepted = true;
      // (syncSessionState pins A.startingKey to the conversation id once the chat
      // has content, and aborts this bootstrap if the user opens a new empty chat.)
      decorate.sweep(); // show the animated "Starting Up" chip immediately
      let startRes = await waitSiteSafe(base);
      if (!alive()) return;
      // A start-up turn that produced nothing at all (the site's agent stalled
      // in its own warm-up) gets ONE automatic short nudge in the same chat
      // instead of leaving the session in a half-started state.
      if ((startRes.kind === "empty" || startRes.kind === "timeout") && !A.stop) {
        diag("start.retryNudge", { kind: startRes.kind });
        ui.toast(`${P.displayName} did not answer the startup prompt - nudging once…`);
        const nb = await submitAndGetBase('Initialize the local extension with exactly {"command":"list_commands","params":{}}. Do not begin a user task yet.');
        if (!alive()) return;
        if (A.lastSendOk) startRes = await waitSiteSafe(nb);
        if (!alive()) return;
      }
      // The user halted the bootstrap (our Stop or the site's native stop). Do
      // NOT declare the session ready - abort quietly so "Start" stays available.
      if (A.stop || startRes.kind === "stopped") { diag("start.aborted", { kind: startRes.kind }); return; }

      // The initial response is not always list_commands: some models discover
      // skills or request the next catalog page first. Return a real result for
      // every allowed discovery call rather than silently abandoning that turn.
      const startupDiscovery = new Set(["list_commands","list_tools","list_mcp_servers","list_roblox_studios","more_output","ms_list_skills","ms_get_skill","ms_recommend_skills","ms_list_virtual_tools"]);
      const discoveryRounds=Math.max(1,Math.min(6,P.startupDiscoveryRounds||6));
      for (let round=0;startRes.kind==="tool"&&round<discoveryRounds;round++) {
        A.startStage=3;A.startPhase="Checking available tools · discovery "+(round+1);ui.setStarting();
        const calls=startRes.calls||[];
        const name=calls.length===1?bareToolName(calls[0].tool||""):"";
        let feedback;
        if (calls.length!==1) feedback=ZS.FEEDBACK.multiTool(calls.map(c=>c.tool||"?"));
        else if (!startupDiscovery.has(name)) {
          feedback="Startup has no user task yet. Do not edit files or execute a project action. Return exactly {\"command\":\"list_commands\",\"params\":{}} to discover the local tools, then acknowledge readiness.";
        } else {
          decorate.toolBox(startRes.item,name,"run","",true);
          feedback=await runTool(calls[0]);
          if (!alive()||A.stop) return;
          decorate.toolBox(startRes.item,name,feedbackIsError(feedback)?"err":"done",feedbackIsError(feedback)?outSummary(feedback):"discovery result returned",true);
          diag("start.discovery",{name,round:round+1});
        }
        const nextBase=await submitAndGetBase(feedback);
        if (!A.lastSendOk||!alive()||A.stop) return;
        A.startStage=3;A.startPhase="Tools checked · "+P.displayName+" is finishing setup";ui.setStarting();
        startRes=await waitSiteSafe(nextBase);
        if (!alive()||A.stop||startRes.kind==="stopped") return;
      }
      if (startRes.kind==="tool") {
        ui.banner("warn","Startup discovery did not finish","The model kept requesting discovery after "+discoveryRounds+" result(s). Automatic startup stopped. Check the conversation before sending another prompt.");
        return;
      }
      if(startRes.kind==="provider_error"||SITE_KINDS.has(startRes.kind)||startRes.kind==="too_long"){
        A.lastSendOk=false;A.taskOutcome="provider-failed";ui.banner("warn","Provider startup failed",String(startRes.text||"No usable startup response. Recover the provider before trying again."));return;
      }
      if (startRes.kind === "empty" || startRes.kind === "timeout") {
        // Delivery alone is not proof of a readable, usable provider session.
        A.lastSendOk=false;A.taskOutcome='provider-failed';
        ui.banner('warn','Startup could not be verified',`${P.displayName} received the prompt, but no readable reply was detected. Startup stopped. Use the provider's Retry or open a new chat; no task is marked complete.`);
        return;
      }
      bootstrapReady=true;failedStartups.delete(bootstrapClaimKey());saveFailedStartups();
      A.started = true;
      rememberSession(P.conversationKey()); // survives virtualization AND reloads
      ui.setStarted(true);
      ui.toast(A.software ? `${softwareSettings.mode === "code" ? "Code mode" : "Software Builder"} ready in ${P.displayName} · workspace tools enabled.` : A.chatOnly ? `Studio profile ready in ${P.displayName} · no engine connected.` : `Agent ready. Ask ${P.displayName} to build something.`);
    } catch (e) {
      if (!bootstrapAccepted) bootstrapClaims.delete(claimKey);
      if (alive()) ui.banner("warn", "Startup failed", String((e && e.message) || e));
    } finally {
      clearTimeout(startWatchdog);
      // Claims prevent two simultaneous bootstraps; they are not completed-chat
      // history. Several providers represent every blank conversation with the
      // same transient key ("provider|new"). Keeping a successful claim forever
      // therefore made the next genuinely new chat say it had already received
      // the startup prompt. A.started / startedSessions own completed-chat state.
      if (!A.sendUnconfirmed) bootstrapClaims.delete(claimKey);
      // Only tear down our OWN starting state. If we were superseded (the user
      // opened another chat), the newer flow / syncSessionState owns it now.
      if(alive()&&!bootstrapReady&&bootstrapAccepted){
        failedStartups.add(bootstrapClaimKey());saveFailedStartups();A.started=false;
        const path=P.conversationKey();startedSessions.delete(path);
        try{chrome.storage.local.set({zsStartedSessions:[...startedSessions].slice(-300)});}catch{}
      }
      if (alive()) endStarting();
    }
  }

  // ════════════════════════════════════════════════════════════════════════
  //  SVG ICON SET  (stroke = currentColor, inherits the chip's theme colour)
  // ════════════════════════════════════════════════════════════════════════
  const SVG = (p) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
  const ICONS = {
    screen:  SVG('<rect x="3" y="4" width="18" height="13" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>'),
    roblox:  SVG('<path d="M12 2 3 7v10l9 5 9-5V7z"/><path d="M3 7l9 5 9-5M12 12v10"/>'),
    read:    SVG('<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>'),
    edit:    SVG('<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>'),
    generate: SVG('<path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8"/>'),
    tool:    SVG('<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18v3h3l6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2-2z"/>'),
    result:  SVG('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>'),
    check:   SVG('<polyline points="20 6 9 17 4 12"/>'),
    // Bell - the mid-session system-prompt re-statement. Deliberately NOT the
    // gear: the gear means "the agent is starting up", and a reminder is the
    // opposite (a session already long enough to need re-anchoring).
    remind:  SVG('<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>'),
    error:   SVG('<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>'),
    gear:    SVG('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-2.82 1.17V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 8 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15H4.5a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 6 8a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 11 4.6h.09A1.65 1.65 0 0 0 12 3.09 2 2 0 0 1 16 3v.09A1.65 1.65 0 0 0 19 4.6l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 21.4 11h.1a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.5 1z"/>'),
  };
  const SPIN = '<span class="zs-spin"></span>';

  function iconFor(category, phase) {
    if (phase === "run") return SPIN;
    if (phase === "err") return ICONS.error;
    if (phase === "done") return ICONS.check;
    if (phase === "result") return ICONS.result;
    if (phase === "sys") return ICONS.gear;
    if (phase === "remind") return ICONS.remind;
    return ICONS[category] || ICONS.tool;
  }

  // ════════════════════════════════════════════════════════════════════════
  //  CAMOUFLAGE / DECORATION  (chips are real "tool cards": header + an
  //  expandable body, themed by tool category and execution state)
  // ════════════════════════════════════════════════════════════════════════

  // Strip every trace of our decoration from a node. Needed because sites
  // virtualize (recycle) turn nodes: a node that was a command/result card can
  // be reused to render unrelated text.
  function resetDecoration(item) {
    const chip = item.querySelector(".zs-chip");
    if (chip) chip.remove();
    item.classList.remove("zs-hidden");
    item.querySelectorAll(".zs-tool-hide").forEach((e) => e.classList.remove("zs-tool-hide"));
    item.querySelectorAll(".zs-cmd-mask").forEach((e) => e.classList.remove("zs-cmd-mask"));
    delete item.dataset.zs;
    delete item.dataset.zsig;
    delete item.dataset.zphase;
    delete item.dataset.zStopped;
    delete item.dataset.zRegenLen;
    delete item.dataset.zRegenAt;
    delete item.__zsChip;
  }

  const decorate = {
    // Core renderer. opts: {label, detail, body, category, phase, cls, whole}
    chip(item, opts) {
      const { label, detail = "", body = "", category = "tool", phase, cls, whole } = opts;
      let chip = item.querySelector(".zs-chip");
      const hasBody = !!body;
      // While a command streams, the site re-renders the raw block on every token
      // and we get called on nearly every sweep. If what we'd draw is identical,
      // we must NOT rebuild the chip's innerHTML: doing so re-creates the
      // <span class="zs-spin"> and restarts its CSS animation each time, so the
      // spinner looks frozen / stutters ("retry en rafale"). Rebuild the inner
      // markup ONLY when the rendered content actually changes; otherwise reuse
      // the existing element (and keep its expand/collapse state) so the spinner
      // keeps spinning smoothly. Re-anchoring + masking below still run each pass.
      const sig = `${category}|${phase}|${cls || ""}|${whole ? 1 : 0}|${label}|${detail}|${hasBody ? body.length : 0}`;
      if (!chip) chip = document.createElement("div");
      if (chip.dataset.csig !== sig) {
        chip.dataset.csig = sig;
        chip.className = `zs-chip cat-${category} ${cls || ""}`;
        chip.innerHTML =
          `<div class="zs-chip-head">` +
            `<span class="zs-chip-ic">${iconFor(category, phase)}</span>` +
            `<span class="zs-chip-tx"></span>` +
            `<span class="zs-chip-dt"></span>` +
            (hasBody ? `<span class="zs-chip-cv">${SVG('<polyline points="6 9 12 15 18 9"/>')}</span>` : "") +
          `</div>` +
          (hasBody ? `<div class="zs-chip-body"><pre></pre></div>` : "");
        chip.querySelector(".zs-chip-tx").textContent = label;
        if (detail) chip.querySelector(".zs-chip-dt").textContent = detail;
        if (hasBody) {
          chip.querySelector(".zs-chip-body pre").textContent = body;
          const head = chip.querySelector(".zs-chip-head");
          head.style.cursor = "pointer";
          head.onclick = () => chip.classList.toggle("open");
        }
      }

      if (whole) {
        // Fully injected turn (result / sys) → hide the whole item.
        if (chip.parentElement !== item) item.insertBefore(chip, item.firstChild);
        item.classList.add("zs-hidden");
      } else {
        item.classList.remove("zs-hidden");
        // findToolBlockSpot ALSO applies the .zs-tool-hide classes (its real job);
        // we call it for that even when we don't use its returned position.
        const spot = P.findToolBlockSpot(item, chip);
        if (P.chipAtItemLevel) {
          // Site re-renders the turn's content subtree (Angular/Gemini), which
          // wipes any chip placed INSIDE it. Anchor the chip at the turn-element
          // level instead, where it survives those re-renders; the hide classes
          // (re-applied by the sweep) handle masking the raw block.
          // A provider may supply chipAnchor(item) to redirect the chip into a
          // descendant (e.g. Kimi's turn is a flex ROW [avatar | content];
          // inserting at item.firstChild would make the chip the avatar's flex
          // sibling and shove the layout sideways, so it anchors in the content
          // column instead). Default: the turn root.
          const anchor = (P.chipAnchor && P.chipAnchor(item)) || item;
          // Default: pin the chip as the FIRST child - simple and immune to the
          // site re-appending fresh content later. A provider may opt into
          // `chipAppend` to place it LAST instead (reads in the model's actual
          // order: narration, then the tool call it wrote at the end of the
          // turn). `chipTrailRef(item)` lets it name a fixed trailing sibling
          // (e.g. Qwen's action-buttons row) the chip must stay BEFORE even
          // when "last" - see ensureOwnedChip's drift check for why this needs
          // upkeep that firstChild pinning never did.
          const wantLast = !!P.chipAppend;
          const trailRef = wantLast && P.chipTrailRef ? P.chipTrailRef(item) : null;
          const inPlace = chip.parentElement === anchor &&
            (wantLast ? chip.nextElementSibling === trailRef : anchor.firstElementChild === chip);
          if (!inPlace) {
            if (wantLast) anchor.insertBefore(chip, trailRef); // trailRef=null -> append
            else anchor.insertBefore(chip, anchor.firstChild);
          }
        } else if (spot) {
          spot.parent.insertBefore(chip, spot.ref);
        } else if (!chip.parentElement) {
          item.insertBefore(chip, item.firstChild);
        }
      }
      item.dataset.zs = cls || "1";
      // Remember the exact opts so a chip wiped by a site re-render can be
      // rebuilt identically (see ensureOwnedChip / the chipGone guards).
      item.__zsChip = { ...opts };
      return chip;
    },

    // Re-apply a loop-owned chip after a site re-render wiped it (chip removed
    // and/or the .zs-tool-hide classes stripped). The loop owns the label/phase,
    // so we rebuild from the stored opts rather than re-running classification.
    ensureOwnedChip(item) {
      const opts = item.__zsChip;
      if (!opts) return;
      const chipEl = item.querySelector(".zs-chip");
      const chipGone = !chipEl;
      let rawVisible = false;
      if (!opts.whole) {
        // NOTE the thinking exclusion: reasoning models QUOTE the command
        // JSON/###LUA### in their think area, which the camouflage never hides
        // (by design) - counting those as "raw block visible" made this
        // rebuild fire on EVERY sweep forever (60Hz spam, seen live).
        rawVisible = [...item.querySelectorAll("pre, p, [class*='code'], .cm-line")].some(
          (e) => !e.closest(".zs-tool-hide") && !e.closest(".zs-chip") &&
                 !(P.thinkingSel && e.closest(P.thinkingSel)) &&
                 // Some sites (Arena) wrap a code block in a bare outer <pre>
                 // that has no hide class of its own - the real content (and
                 // the .zs-tool-hide class) live on a child wrapper instead.
                 // closest() only checks ancestors, so without this the outer
                 // <pre> reads as "raw command visible" FOREVER (its own
                 // textContent includes the hidden child's text), causing an
                 // infinite rebuild loop (~60/s, seen live on Arena).
                 !e.querySelector(".zs-tool-hide") &&
                 ZSParse.hasCommandShape(e.textContent || ""));
      }
      // A provider opted into `chipAppend` (chip trails the reply text instead
      // of pinning first) has no equivalent of firstChild's immunity to churn:
      // a site re-render can re-append fresh reply content AFTER our chip,
      // silently shoving it back above the text it was meant to trail. Catch
      // that drift too, not just an outright wipe - it's cheap (one property
      // read) and only applies to opted-in providers (Qwen).
      let drifted = false;
      if (!opts.whole && !chipGone && P.chipAtItemLevel && P.chipAppend) {
        const anchor = (P.chipAnchor && P.chipAnchor(item)) || item;
        const trailRef = P.chipTrailRef ? P.chipTrailRef(item) : null;
        drifted = chipEl.parentElement === anchor && chipEl.nextElementSibling !== trailRef;
      }
      if (chipGone || rawVisible || drifted) {
        // Tracker: the site wiped a loop-owned chip (re-render/node churn).
        diag("chip.rebuild", { name: opts.label, phase: opts.phase, chipGone, rawVisible, drifted });
        this.chip(item, opts);
      }
    },

    // owned=true → the agentic loop manages this item; the observer backs off.
    toolBox(item, name, phase, detail, owned, body, category) {
      if (!item) return;
      // Tracker: every phase TRANSITION of a command chip, with who drove it.
      // "loop" = the agentic loop (authoritative), "sweep" = DOM classification.
      if (item.dataset.zphase !== phase) {
        diag("chip.phase", {
          name, from: item.dataset.zphase || "(new)", to: phase,
          by: owned ? "loop" : "sweep", detail: detail || "",
        });
      }
      const cls = phase === "run" ? "run" : phase === "err" ? "err" : phase === "idle" ? "idle" : "done";
      this.chip(item, {
        label: name, detail: detail || "", body: body || "",
        category: category || ZS.toolCategory(name), phase, cls,
      });
      item.dataset.zphase = phase;
      const settledChip=item.querySelector(".zs-chip");if(settledChip)settledChip.title=phase==="done"?"Individual tool call returned. This does not verify completion of the whole task.":phase==="err"?"This tool call failed or was stopped.":"Tool call is pending or running.";
      if (owned) item.dataset.zloop = "1";
    },

    classify(item, next) {
      if (item.dataset.zloop) { this.ensureOwnedChip(item); return; } // loop owns it
      const txt = P.classifyText(item, ".zs-chip"); // excludes thinking AND our chip

      // NOTE on the "needs re-apply" guards below: some sites (Gemini/Angular)
      // re-render a turn's CHILDREN on every update - our chip and the
      // .zs-tool-hide classes are wiped while the dataset flags on the turn
      // element itself survive. So "already decorated" must always be
      // double-checked against the chip actually being present in the DOM.
      const chipGone = !item.querySelector(".zs-chip");

      // 1a. A mid-session RE-STATEMENT of the system prompt. Checked before the
      //     bootstrap branch because it carries SYS_MARKER too (that marker is
      //     what hides it), and without this it inherited the bootstrap's
      //     "Starting Up" gear - which reads as if the agent restarted, exactly
      //     the confusion Seb reported. Never animated: nothing is starting.
      if (ZS.hasResendMarker(txt)) {
        if (item.dataset.zs !== "resend" || chipGone) {
          // The rider travels ON a tool result, so this one turn is both things.
          // Name the tool in the detail rather than dropping it - otherwise that
          // result is the only one in the conversation with no visible outcome.
          const m = txt.match(/Output of '?([A-Za-z_][\w.]*)'?\s*:/);
          this.chip(item, {
            label: "Reminder",
            detail: m ? `with ${m[1]} result` : "",
            category: "remind", phase: "remind", cls: "sys", whole: true,
          });
          item.dataset.zs = "resend";
          item.dataset.zphase = "remind";
        }
        return;
      }

      // 1. System-prompt bootstrap turn → animated while starting, gear when done.
      if (ZS.hasSysMarker(txt)) {
        const phase = A.starting ? "run" : "sys";
        if (item.dataset.zs !== "sys" || item.dataset.zphase !== phase || chipGone) {
          // Animated "Starting Up" only while the bootstrap is really running;
          // afterwards the same turn reads "Session ready" so a finished start
          // never looks stuck (reported on Notion AI).
          this.chip(item, { label: phase === "run" ? "Starting Up" : "Session ready", category: "tool", phase, cls: "sys", whole: true });
          item.dataset.zphase = phase;
        }
        return;
      }

      // 2. Injected result / ERROR / note turns. ALWAYS a user turn we sent,
      //    keyed off our fixed output shapes (never command keywords).
      if (P.isUserItem(item) && ZSParse.isInjectedFeedback(txt)) {
        const m = txt.match(/Output of '?([A-Za-z_][\w.]*)'?\s*:/);
        const isErr = /^\s*ERROR\b/.test(txt);
        // Reload-proof image detection: a feedback carrying an image ends with the
        // IMAGE_FEEDBACK_RE marker. Learn the tool (persisted) so its command turn
        // above AND its next call get the "screen" chip even with no loop running.
        const hasImg = !isErr && IMAGE_FEEDBACK_RE.test(txt);
        if (hasImg && m) rememberImageTool(m[1]);
        const sig = (m ? m[1] : "note") + "|" + (isErr ? "err" : hasImg ? "img" : "result");
        if (item.dataset.zsig !== sig || !item.classList.contains("zs-hidden") || chipGone) {
          this.chip(item, {
            label: m ? `${m[1]} · result` : "result",
            category: hasImg ? "screen" : m ? ZS.toolCategory(m[1]) : "tool",
            body: txt, phase: isErr ? "err" : "result",
            cls: isErr ? "err" : "result", whole: true,
          });
          item.dataset.zsig = sig;
        }
        return;
      }

      // 2b. FALLBACK for a command turn whose raw tool-call text is no longer
      // readable (e.g. Qwen disposes/never fully renders an off-screen Monaco
      // code block on a COLD page load - the dataset.zsCode cache only helps
      // WITHIN a session, since it needs to observe the block live to capture
      // it before disposal; reported live: every past tool-call chip vanished
      // after a page reload, leaving only its "· result" box). The turn's own
      // text no longer "looks like" a command, but the VERY NEXT turn being
      // our injected result (`Output of 'name'`) is definitive proof it WAS
      // one - settle it from that evidence instead of leaving the chip gone.
      if (P.isAssistantItem(item) && !ZSParse.hasCommandShape(txt) &&
          next && P.isUserItem(next)) {
        const nt = P.classifyText(next, ".zs-chip");
        const m = nt.match(/^\s*Output of '?([A-Za-z_][\w.]*)'?\s*:/);
        if (m) {
          const isErr = /^\s*ERROR\b/.test(nt);
          const phase = isErr ? "err" : "done";
          if (item.dataset.zphase !== phase || chipGone) {
            this.toolBox(item, m[1], phase, "", false);
          }
          return;
        }
      }

      // 3. Assistant command turns → live loading while streaming, ✓ when done.
      // ONLY in a real Multi-Script session (started or bootstrapping). Without
      // this gate, a plain never-started chat where the model merely EXPLAINS
      // the command format (a {"command":...} example in its answer) got the
      // example MASKED behind a tool chip - hiding genuine content the user
      // asked for. Same principle as domHasZsSignal: a command shape alone is
      // not proof of a session. (Branches 1/2 above key off OUR OWN injected
      // markers, which only exist in real sessions, so they need no gate.)
      if (P.isAssistantItem(item) && ZSParse.hasCommandShape(txt) &&
          (A.started || A.starting)) {
        // Regenerate transition (see zRegenLen capture in regenResume): the site is
        // still showing the OLD command text after a post-stop regenerate, before it
        // wipes and re-streams. Keep the coherent red "stopped" look instead of
        // re-animating the stale old call as a fresh "run" spinner. Clears the moment
        // the content is actually replaced (stream length drops below the captured
        // baseline) or a short safety window elapses, after which normal
        // classification paints the freshly regenerated command.
        if (item.dataset.zRegenLen) {
          const baseLen = Number(item.dataset.zRegenLen);
          const armedAt = Number(item.dataset.zRegenAt || 0);
          const replaced = txt.length < baseLen - 8;      // old content wiped
          const expired = Date.now() - armedAt > 6000;    // safety fallback
          if (!replaced && !expired) {
            const nm = ZSParse.toolNameFromText(txt) || "command";
            this.toolBox(item, nm, "err", "stopped", false);
            return;
          }
          delete item.dataset.zRegenLen;
          delete item.dataset.zRegenAt;
        }
        // A turn the user manually halted (Stop / native stop) stays "stopped" -
        // never let this sweep repaint it ✓ done (or worse, re-spin it) just
        // because generation is still settling. The dataset marker is set where we
        // halt, but on Arena the A/B carousel re-renders the turn node on every
        // token, wiping the marker - so the spinner came back even after Stop. Also
        // derive "stopped" from the userStopped latch (which survives node swaps)
        // for the last turn; it's cleared on the next user message / deliberate
        // resume, so a settled turn is never falsely frozen later.
        // A turn that is GENERATING again (or whose tool the loop is actively
        // running), with NO active user-stop latch, has been REGENERATED - it is no
        // longer the halted turn. Clear its stale halt so isRememberedHalted (index
        // + text-prefix based) can't keep repainting the FRESH command red: a Gemini
        // regenerate reuses the same assistant index and a similar opening prefix,
        // so the old halt otherwise matches and the running command shows "stopped"
        // (red) until it settles. Gated on !A.userStopped so a real Stop that is
        // still settling (isGenerating can lag true for a beat) is NEVER cleared.
        const regenerating = !A.userStopped && (
          (item === P.lastAssistant() && P.isGenerating()) ||
          (A.running && A.toolItem === item)
        );
        if (regenerating) { delete item.dataset.zStopped; forgetHalted(item); }
        const stopped = !regenerating && (
          item.dataset.zStopped === "1" ||
          (A.userStopped && item === P.lastAssistant()) ||
          isRememberedHalted(item, txt));
        // Self-heal: a site re-render that swapped this turn's node wiped the
        // dataset marker - re-stamp it so the stop survives the next wipe of
        // the A.userStopped latch (a fresh user message clears it by design).
        if (stopped && item.dataset.zStopped !== "1") {
          item.dataset.zStopped = "1";
          diag("chip.rehalt", { name: ZSParse.toolNameFromText(txt) });
        }
        // The loop already SETTLED this very call (tool finished, we're waiting
        // for the model's next turn) but the site swapped the turn's DOM node,
        // wiping the chip, the zloop ownership AND the __zsChip opts. Without
        // this, the fresh node re-classifies as a spinning "run" chip (A.running
        // is still true) on an already-executed call. Re-own it with the settled
        // outcome. The count guard skips this once the model's NEXT turn exists,
        // so a follow-up call to the same tool still classifies live.
        if (!stopped && A.running && !A.toolRunning && A.toolSettle &&
            // Same TURN check. Node identity when available (virtualization-proof:
            // on Qwen the count doesn't grow for a new turn, and a back-to-back
            // call to the same tool defeats the name guard - the old outcome then
            // repainted the STREAMING next turn's chip as done/err). Falls back to
            // the count guard for providers without lastAssistantId.
            (A.toolSettle.id !== undefined && P.lastAssistantId
              ? P.lastAssistantId() === A.toolSettle.id
              : A.toolSettle.count === P.assistantCount()) &&
            item === P.lastAssistant() &&
            ZSParse.toolNameFromText(txt) === A.toolName) {
          diag("chip.reown", { name: A.toolName, phase: A.toolSettle.phase });
          this.toolBox(item, A.toolName, A.toolSettle.phase, A.toolSettle.detail,
            true, A.toolSettle.body, A.toolSettle.category);
          return;
        }
        // Is this command turn the IN-FLIGHT call - the one a running loop or the
        // bootstrap is about to own? The tell: it has NO injected result turn after
        // it yet. Every ALREADY-EXECUTED command turn is followed by its injected
        // result (a user turn matching isInjectedFeedback), so keying off that,
        // rather than item === lastAssistant(), robustly separates the in-flight
        // turn from settled history. This gives us the best of both:
        //  - The Kimi/bootstrap flash fix: while a loop/bootstrap is active, the
        //    in-flight turn stays "run" in the window between generation ending and
        //    the loop painting its own chip, WITHOUT depending on the flickery
        //    lastAssistant() (Kimi's Vue swaps the node) - no premature green flash.
        //  - No re-spin on REVISIT: when a started chat is re-opened and the loop
        //    or bootstrap runs again, every PAST command turn already has its result
        //    below it, so it settles to "done" instead of every old chip re-loading
        //    to a blue spinner (the Arena "all chips restarted loading" report).
        const resultAfter = next && P.isUserItem(next) &&
          ZSParse.isInjectedFeedback(P.classifyText(next, ".zs-chip"));
        const inFlight = (A.running || A.starting) && !resultAfter;
        // Regenerate grace: keep the freshly-regenerated command turn "run" in the
        // gap between regenResume clearing the stop latch and the watchdog starting
        // the loop, so it never flashes a premature ✓ "done" (see regenResume). The
        // anchor slides with generation and expires ~2.5s after it truly stops.
        const resumeGrace = A.resumeArmed && item === P.lastAssistant() &&
          Date.now() - (A.resumeArmedAt || 0) < 2500;
        const live = !stopped && (
          inFlight || resumeGrace || (item === P.lastAssistant() && P.isGenerating())
        );
        // Orphaned command: a COMPLETE command turn that is the last assistant with
        // NO result below it, not live and not loop-owned, whose generation is now
        // stale (typically the page/extension was reloaded while this command sat
        // un-executed). The auto-resume watchdog deliberately refuses to run a
        // reload-restored generation (the "execute_luau leaked into the new chat"
        // leak guard - same lastGenAt staleness test used here), so it will NEVER
        // execute. Painting it a green ✓ "done" falsely implies the tool ran and
        // succeeded; show a neutral, greyed "not run" state instead (cosmetic only -
        // we intentionally do NOT auto-execute it).
        // A command turn we have no evidence ever executed: not loop-owned, no
        // injected result below it, and not in the off-DOM executed memory (the
        // memory keeps this virtualization-safe - a scrolled-back turn whose result
        // detached is still known-executed and never mislabelled).
        const neverRun = !item.dataset.zloop && !resultAfter &&
          !isRememberedExecuted(item, txt);
        // Superseded orphan: abandoned command - a NEWER assistant turn exists below
        // it yet it never ran (e.g. stopped then regenerated into a fresh turn on
        // Qwen). It will never execute, so it must show neither a green ✓ "done" NOR
        // a live spinner. inFlight is not turn-specific: with the loop running the
        // NEW turn, this old no-result turn would otherwise also read as "run" - the
        // "both the old and the new chip spinning at once" seen live.
        const supersededOrphan = neverRun && item !== P.lastAssistant();
        // Reload orphan: the LAST command turn, not live, whose generation is stale -
        // the page/extension was reloaded while it sat un-executed and the watchdog
        // refuses to run a reload-restored generation (leak guard). Also never a
        // false green ✓; show a neutral, greyed "not run" (we do NOT auto-execute it).
        // Tied to RESUME_FRESH_MS, never a separate literal: this must not paint
        // "not run" while the resume watchdog is still entitled to execute the
        // command. With the two numbers out of step (8s here vs the watchdog's
        // window) a command that WAS about to run got labelled dead first.
        const staleLastOrphan = neverRun && item === P.lastAssistant() && !live &&
          Date.now() - A.lastGenAt > RESUME_FRESH_MS;
        const orphanPending = !stopped && (supersededOrphan || staleLastOrphan);
        // Handoff window: a JUST-finished last-assistant command with no result yet
        // that the loop has not taken over (A.running not yet true, so `live` is
        // false). Without this it flashes a premature ✓ "done" for the frames
        // between generation ending and the loop starting, THEN re-spins when the
        // loop paints its own chip - most visible on the instant virtual commands
        // (list_mcp_servers/list_commands). Keep it spinning instead; staleLastOrphan
        // takes over after 8s if the loop genuinely never runs it.
        // Same window as the watchdog: while it can still fire, the honest state
        // is "waiting to run" (spinner), not a settled verdict either way.
        const pendingExec = !stopped && !orphanPending && !live &&
          neverRun && item === P.lastAssistant() && Date.now() - A.lastGenAt <= RESUME_FRESH_MS;
        let phase = stopped ? "err" : (orphanPending ? "idle" : ((live || pendingExec) ? "run" : "done"));
        let detail = stopped ? "stopped" : (orphanPending ? "not run" : "");
        // Error-aware settle: a command whose injected result RIGHT BELOW is an
        // ERROR must never wear a green ✓. The loop paints this correctly while
        // it owns the turn, but a revisited conversation (or a node swap that
        // dropped ownership) re-derives the phase here - from the conversation
        // itself, so it stays correct without any loop state.
        if (phase === "done" && next && P.isUserItem(next)) {
          const nt = P.classifyText(next, ".zs-chip");
          // feedbackIsError also catches an MCP tool's in-body error (the result
          // reads "Output of '…': Error executing code…", which our ERROR prefix
          // test would miss - the Blender case), so a revisited conversation
          // re-settles it red, matching what the loop painted live.
          if (ZSParse.isInjectedFeedback(nt) && feedbackIsError(nt)) {
            phase = "err"; detail = "error";
            if (item.dataset.zphase !== "err") diag("chip.errSettle", { name: ZSParse.toolNameFromText(txt) });
          }
        }
        // A command block that is VISIBLE right now (its hide classes live on
        // child nodes that sites like Gemini re-create on every update, and the
        // block may render only AFTER the chip was first placed mid-stream).
        // Excludes the reasoning area (P.thinkingSel) like ensureOwnedChip:
        // thinking-quoted commands otherwise keep this true forever, and the
        // forced repaint recomputes `live` each sweep - the chip then FLAPS
        // done→run→done with the generation flicker (seen live as a settled
        // green chip blinking back to a blue spinner).
        const rawVisible = [...item.querySelectorAll("pre, p, [class*='code'], .cm-line")].some(
          (e) => !e.classList.contains("zs-tool-hide") && !e.closest(".zs-tool-hide") &&
                 !e.closest(".zs-chip") && !(P.thinkingSel && e.closest(P.thinkingSel)) &&
                 // see ensureOwnedChip's matching guard: a bare outer <pre>
                 // wrapping a hidden child wrapper otherwise reads as visible
                 // forever (Arena code-block markup).
                 !e.querySelector(".zs-tool-hide") &&
                 ZSParse.hasCommandShape(e.textContent || ""));
        // A tool learned to return images gets the "screen" chip even though its
        // name alone wouldn't reveal it (parity with Roblox screen_capture). The
        // fact can land AFTER this turn first settled (imageTools loads from
        // storage async, or the result turn below is classified later the same
        // pass), so repaint when the current chip's category is stale too - the
        // phase-only guard would otherwise freeze it on the generic wrench.
        const nm = ZSParse.toolNameFromText(txt);
        const cat = A.imageTools.has(bareToolName(nm)) ? "screen" : undefined;
        const chipNow = item.querySelector(".zs-chip");
        const catStale = cat === "screen" && chipNow && !chipNow.classList.contains("cat-screen");
        // Chip drift for chipAppend providers (Kimi): the RUN chip is painted by
        // the SWEEP (owned=false, no zloop) until the loop takes over at
        // tool.start ~2s later, so ensureOwnedChip's drift fix (zloop-only) does
        // NOT run during that window. Meanwhile Vue mounts the copy/regenerate
        // toolbar (chipTrailRef) and inserts it ABOVE our chip node, flashing the
        // action buttons over the chip until something repaints it. Detect that
        // drift here too so the sweep re-seats the chip (chip() re-anchors before
        // trailRef) without waiting for the loop. Mirrors ensureOwnedChip.
        let drifted = false;
        if (P.chipAtItemLevel && P.chipAppend && chipNow) {
          const anchor = (P.chipAnchor && P.chipAnchor(item)) || item;
          const trailRef = P.chipTrailRef ? P.chipTrailRef(item) : null;
          drifted = chipNow.parentElement === anchor && chipNow.nextElementSibling !== trailRef;
        }
        if (item.dataset.zphase !== phase || chipGone || rawVisible || catStale || drifted) {
          // Tracker: WHY the sweep chose this phase (only when it changes -
          // chipGone/rawVisible repaints of the same phase stay silent).
          if (item.dataset.zphase !== phase) {
            // Extra suspicion flag: a command that settled ✓ done while it is
            // still the LAST assistant with NO injected result below it - the
            // exact shape of the "chip shows done but the model is still writing"
            // report. genDebug() (if the provider exposes it) breaks isGenerating
            // into its sub-signals so we can see WHICH one flickered false.
            const suspectDone = phase === "done" &&
              item === P.lastAssistant() && !resultAfter;
            diag("chip.why", {
              name: nm, to: phase,
              stopped, live, inFlight, resumeGrace, pendingExec,
              isLast: item === P.lastAssistant(), resultAfter,
              gen: P.isGenerating(), run: A.running, starting: A.starting,
              zStopped: item.dataset.zStopped === "1",
              remembered: isRememberedHalted(item, txt),
              lastGenAgoMs: Date.now() - A.lastGenAt,
              suspectDone,
              ...(P.genDebug ? { g: P.genDebug() } : {}),
            });
          }
          this.toolBox(item, nm, phase, detail, false, undefined, cat);
        }
        return;
      }

      // A user-halted turn whose CONTENT the site cleared. Arena's native stop
      // (which our Stop button clicks) empties the turn's .prose and shows
      // "Generation stopped" - so the command JSON vanishes, branch 3's command
      // shape no longer matches, and the empty-text guard just below would bail
      // every sweep, freezing a spinning "run" chip forever. Settle any lingering
      // run chip to "stopped" right here, BEFORE that guard. Idempotent: skips
      // once already at the err phase.
      const haltedTurn =
        item.dataset.zStopped === "1" ||
        (A.userStopped && item === P.lastAssistant());
      if (haltedTurn && P.isAssistantItem(item) && item.dataset.zphase !== "err"
          && item.querySelector(".zs-chip")) {
        const tx = item.querySelector(".zs-chip-tx");
        const name = ZSParse.toolNameFromText(txt) || (tx && tx.textContent) || "tool";
        this.toolBox(item, name, "err", "stopped", false);
        return;
      }

      // Transient empty render (Angular swaps a turn's subtree before refilling
      // it): the text vanishes for a frame. Never strip a decorated turn on
      // that - the next sweep re-evaluates it with real content.
      if (!txt.trim() && (item.dataset.zphase || item.dataset.zs)) return;

      // 4. Plain text turn. If this node still wears decoration (a recycled
      //    virtualized node), strip it so we never hide genuine content.
      if (item.dataset.zs || item.dataset.zphase || item.querySelector(".zs-chip")) {
        // Tracker: a decorated node re-classified as PLAIN TEXT (virtualized
        // node recycled, or the turn's command text vanished) - its decoration
        // (chip + zStopped marker) is stripped here. If a chip "un-settles"
        // mysteriously, this is the smoking gun to look for.
        diag("chip.reset", { was: item.dataset.zphase || item.dataset.zs || "chip-only" });
        resetDecoration(item);
      }
    },

    sweep(full = true) {
      // Pass each turn's FOLLOWING turn too: a command chip needs it to know
      // whether its injected result was an ERROR (error-aware settle above).
      // While a reply streams only the newest turns change, so quick sweeps look at the last few; the periodic
      // full sweep (every ~1.5 s) still repairs older turns. Re-reading every turn on every token made long chats lag.
      const items = !full&&P.recentItems?P.recentItems(4):P.allItems();
      for (let i = full ? 0 : Math.max(0, items.length - 4); i < items.length; i++) this.classify(items[i], items[i + 1] || null);
      // Safety net for stopped turns whose chip lives OUTSIDE the enumerated
      // message list. On Arena an A/B comparison renders each candidate as a
      // slide in the carousel's OWN nested <ol>, not the main flex-col-reverse
      // list - so allItems()/classify never see that node and a "run" spinner
      // left by a Stop would spin forever. zStopped is only ever set on a
      // deliberate halt, so settling any run-phase chip under such a node is
      // safe wherever it lives. Idempotent: skips once at the err phase.
      for (const chip of document.querySelectorAll(".zs-chip.run")) {
        let item = chip.parentElement;
        while (item && !(item.dataset && item.dataset.zStopped)) item = item.parentElement;
        if (item && item.dataset.zphase !== "err") {
          const tx = chip.querySelector(".zs-chip-tx");
          this.toolBox(item, (tx && tx.textContent) || "tool", "err", "stopped", false);
        }
      }
    },
  };

  // ════════════════════════════════════════════════════════════════════════
  //  UI  (control panel, onboarding, stop button, banners, toast, input cover)
  // ════════════════════════════════════════════════════════════════════════
  const ui = (() => {
    let softwareBtn; let root, bar, dot, brandEl, stateEl, actionBtn, chatOnlyBtn, stopBtn, switchBtn, supportBtn, bridgeBtn, bridgeRunBtn, modelChip, discordEl, menuEl, memBtn, memPanel, memCtl;
    let cover, coverRaf, barRaf;
    let openMenuFn = null; // set by build(); lets the popup force the panel open via runtime message
    let bridgeOk = false, studioDown = false, placeDown = false, appDown = false, addonOk = false, studioProcUp = false;
    let wasConnected = false, bridgeBannerEl = null;
    // ── Fazbear's Pizzeria (live theme, 6.28.2) ─────────────────────────────
    // Picking the "Fazbear's" theme draws a pizzeria behind the settings panel
    // (aligned black/white tile bands top and bottom, a drifting field of blurred
    // hand-drawn pizzas, a purple glow that deepens as you scroll to the lower
    // settings) and unlocks a hidden "Backstage" tab. All drawing is inline SVG/CSS
    // inside #zs-menu: no network, no images, nothing is added to the host page.
    const FNAF_HOUR_MS = 5 * 60 * 1000; // one in-game hour = 5 real minutes (6 AM after 30 min)
    // need = the Security Office nights you must have cleared; golden also opens via a 30-minute shift or the eyes.
    const FNAF_CAST = {
      freddy: { label: "Freddy", accent: "#c98a45" }, bonnie: { label: "Bonnie", accent: "#7c6cf2" },
      chica: { label: "Chica", accent: "#f2c230" }, foxy: { label: "Foxy", accent: "#e0503f" },
      mangle: { label: "Mangle", accent: "#f08fb0" }, puppet: { label: "Puppet", accent: "#b9b4e6", need: 2, hint: "Clear Night 2 in the Security Office" },
      springtrap: { label: "Springtrap", accent: "#9aa14a", need: 3, hint: "Clear Night 3 in the Security Office" },
      golden: { label: "Golden", accent: "#f6d365", hint: "Clear Night 1, survive a 30-minute shift, or find the eyes" },
      fredbear: { label: "Fredbear", accent: "#e9c46a", need: 5, hint: "Clear Night 5 in the Security Office" },
      none: { label: "My accent", accent: null },
    };
    const FNAF_ACH = {
      keycard: "Hello, hello?", first_night: "Clocked in", night_five: "Five nights", penny: "Penny pincher",
      close_call: "Cutting it close", knock: "Knock, knock", golden_eyes: "It's me", shift: "Night owl",
    };
    const FNAF_OFFICE_DEFAULTS = { cleared: 0, wins: 0, deaths: 0, ach: [] };
    const FNAF_DEFAULTS = { cast: "freddy", pizzas: 7, speed: 100, blur: 3, tile: 24, glow: 55, flicker: true, staticFx: false,
      spot: true, jumpscare: true, shift: false, nights: 0, calls: 0, golden: false, seen: false, visits: 0, office: FNAF_OFFICE_DEFAULTS };
    function fnafCastOpen(id, f) {
      const c = FNAF_CAST[id]; if (!c) return false;
      if (id === "golden") return !!f.golden;
      return !c.need || (f.office && f.office.cleared >= c.need);
    }
    function sanitizeFnaf(raw) {
      const src = raw && typeof raw === "object" ? raw : {}, out = { ...FNAF_DEFAULTS };
      const num = (k, lo, hi) => { const n = Number(src[k]); if (Number.isFinite(n)) out[k] = Math.max(lo, Math.min(hi, Math.round(n))); };
      num("pizzas", 0, 14); num("speed", 25, 200); num("blur", 0, 8); num("glow", 0, 100); num("nights", 0, 999); num("calls", 0, 9999); num("visits", 0, 9999);
      if ([18, 24, 32].includes(Number(src.tile))) out.tile = Number(src.tile);
      for (const k of ["flicker", "staticFx", "spot", "jumpscare", "shift", "golden", "seen"]) if (typeof src[k] === "boolean") out[k] = src[k];
      const so = src.office && typeof src.office === "object" ? src.office : {};
      const on = (k, hi) => { const n = Number(so[k]); return Number.isFinite(n) ? Math.max(0, Math.min(hi, Math.round(n))) : 0; };
      const ach = Array.isArray(so.ach) ? so.ach.filter((x, i, a) => typeof x === "string" && Object.prototype.hasOwnProperty.call(FNAF_ACH, x) && a.indexOf(x) === i) : [];
      out.office = { cleared: on("cleared", 5), wins: on("wins", 9999), deaths: on("deaths", 9999), ach };
      if (out.nights >= 1 || out.office.cleared >= 1) out.golden = true;
      if (Object.prototype.hasOwnProperty.call(FNAF_CAST, src.cast) && fnafCastOpen(src.cast, out)) out.cast = src.cast;
      return out;
    }
    const DEFAULT_MENU_PREFS = {
      accent: "#d8d8e2", accentUser: false, density: "comfortable", width: "medium", scale: "100", ultraPalette:"amethyst", ultraAnimation:"flow",
      radius: "soft", theme: "mono", font: "system", backdrop: "mesh", motion: "full",
      brandName: "Multi-Script", brandIcon: "✦", tagline: "Create without limits",
      showOverview: true, defaultTab: "home",
      // Chat bar customisation (6.25). dock: auto = the provider's own in-composer
      // mount; float = a free pill hugging the composer; window = a pill pinned to
      // the bottom of the window. hide = bar items the user switched off.
      barDock: "auto", barAlign: "left", barFit: "full", barSize: "regular", barStyle: "native",
      barStatus: "stacked", barTheme: "auto", barOffsetX: 0, barOffsetY: 0, barOffsetBy: {}, barHide: [],
      fnaf: sanitizeFnaf({})
    };
    const NUDGE_MAX = 240;
    let menuPrefs = { ...DEFAULT_MENU_PREFS };
    const MENU_WIDTHS = { small:500, medium:680, wide:800, studio:960 };
    const MENU_PREF_ENUMS = { density:["compact","comfortable","spacious"], width:["small","medium","wide","studio"], scale:["90","100","115"], radius:["sharp","soft","round"], theme:["auto","midnight","graphite","frost","mono","ink","synthwave","forest","roblox","robloxdark","terminal","sunset","ocean","paper","aurora","lava","sakura","crimson","nebula","matrix","fnaf","scream","myers","slender","jason","cobalt","porcelain","ember","tidal","starlight","daybreak"], font:["system","rounded","mono"], backdrop:["solid","glass","mesh"], motion:["full","reduced","none"], defaultTab:["home","bar","agent","notion","look","tools","engines","sites","ideas","software","workshop","cowork","flight","vani","help","setup","appearance","studio","interface"], barDock:["auto","float","window"], barAlign:["left","center","right"], barFit:["full","fit"], barSize:["compact","regular","roomy"], barStyle:["native","card","glass","minimal"], barStatus:["stacked","inline","hidden"], barTheme:["auto","midnight","graphite","frost","mono","ink","synthwave","forest","roblox","robloxdark","terminal","sunset","ocean","paper","aurora","lava","sakura","crimson","nebula","matrix","fnaf","scream","myers","slender","jason","cobalt","porcelain","ember","tidal","starlight","daybreak"] };
    const BAR_ITEMS = ["brand","status","chatOnly","ideas","studio","blender","progress","phone","models","discord","donate","support","memory","switch","terminal","running"];
    const TAB_ALIAS = { wip:"software", setup:"home", interface:"home", appearance:"look", studio:"agent" };
    function sanitizeMenuPrefs(raw) {
      const out={...DEFAULT_MENU_PREFS}, src=raw && typeof raw==="object" ? raw : {};
      for(const [key,allowed] of Object.entries({ultraPalette:['amethyst','rainbow','aurora','sunset'],ultraAnimation:['flow','breathe','still']}))if(allowed.includes(src[key]))out[key]=src[key];
      for(const [key,allowed] of Object.entries(MENU_PREF_ENUMS)) if(allowed.includes(String(src[key]))) out[key]=String(src[key]);
      if(/^#[0-9a-f]{6}$/i.test(src.accent||"")) out.accent=src.accent;
      if(typeof src.brandName==="string" && src.brandName.trim()) out.brandName=src.brandName.trim().slice(0,28);
      if(typeof src.brandIcon==="string" && src.brandIcon) out.brandIcon=src.brandIcon.slice(0,3);
      if(typeof src.tagline==="string") out.tagline=src.tagline.trim().slice(0,60);
      if(typeof src.showOverview==="boolean") out.showOverview=src.showOverview;
      if(TAB_ALIAS[out.defaultTab]) out.defaultTab=TAB_ALIAS[out.defaultTab];
      for(const k of ["barOffsetX","barOffsetY"]){ const n=Number(src[k]); out[k]=Number.isFinite(n)?Math.max(-NUDGE_MAX,Math.min(NUDGE_MAX,Math.round(n))):0; }
      // 6.28.2: nudges are remembered per AI site (every site lays its composer out differently).
      out.barOffsetBy={};
      if(src.barOffsetBy && typeof src.barOffsetBy==="object" && !Array.isArray(src.barOffsetBy)){
        for(const [site,v] of Object.entries(src.barOffsetBy).slice(0,40)){
          if(!/^[a-z0-9_-]{1,24}$/i.test(site) || !v || typeof v!=="object") continue;
          const nx=Number(v.x), ny=Number(v.y);
          const cl=(n)=>Number.isFinite(n)?Math.max(-NUDGE_MAX,Math.min(NUDGE_MAX,Math.round(n))):0;
          if(cl(nx)||cl(ny)) out.barOffsetBy[site]={x:cl(nx),y:cl(ny)};
        }
      }
      out.fnaf=sanitizeFnaf(src.fnaf);
      out.barHide=Array.isArray(src.barHide)?[...new Set(src.barHide.map(x=>String(x)==="studio"?"ideas":String(x)).filter((x)=>BAR_ITEMS.includes(x)))]:[];
      return out;
    }
    // Theme coherence. The menu theme (mono/ink/midnight…) and the page's own
    // light/dark mode used to be applied independently, so the default dark Mono
    // panel on a LIGHT page (Notion's light mode) got the light-mode TEXT colours
    // on a dark background - unreadable. One rule now decides both: Frost is
    // light, the explicit dark themes are dark, and Auto/Mono follow the page.
    const DARK_MENU_THEMES = ["midnight", "graphite", "ink", "synthwave", "forest", "robloxdark", "terminal", "sunset", "ocean", "aurora", "lava", "crimson", "nebula", "matrix", "fnaf", "scream", "myers", "slender", "jason", "cobalt", "ember", "tidal", "starlight"];
    const LIGHT_MENU_THEMES = ["frost", "roblox", "paper", "sakura", "porcelain", "daybreak"];
    let pageIsLight = false;
    function effectiveLight() {
      if (LIGHT_MENU_THEMES.includes(menuPrefs.theme)) return true;
      if (DARK_MENU_THEMES.includes(menuPrefs.theme)) return false;
      return pageIsLight;
    }
    // ── Custom background image / GIF (6.26) ───────────────────────────────
    // Stored apart from menuPrefs (it can be MBs, and settings backups must stay
    // small and secret-free). Rendered by CSS through custom properties, so it
    // auto-aligns (cover/contain/tile/stretch) to whatever size the menu is.
    let bgImage = "", bgPrefs = typeof ZSExtras !== "undefined" ? ZSExtras.sanitizeBackground({}) : { fit: "cover", opacity: 45, blur: 0, onBar: false };
    try { chrome.storage.local.get(["msBgImage", "msBgPrefs"], (r) => { if (r) { if (typeof r.msBgImage === "string" && /^data:image\/(png|jpeg|gif|webp);base64,/.test(r.msBgImage)) bgImage = r.msBgImage; if (r.msBgPrefs && typeof ZSExtras !== "undefined") bgPrefs = ZSExtras.sanitizeBackground(r.msBgPrefs); } applyCustomBackground(); }); } catch {}
    function applyCustomBackground() {
      if (!root) return;
      const on = !!bgImage;
      root.dataset.msBg = on ? (bgPrefs.onBar ? "all" : "menu") : "off";
      if (!on) { root.style.removeProperty("--ms-bg-url"); return; }
      root.style.setProperty("--ms-bg-url", `url("${bgImage}")`);
      root.style.setProperty("--ms-bg-opacity", String(bgPrefs.opacity / 100));
      root.style.setProperty("--ms-bg-blur", bgPrefs.blur + "px");
      const fit = { cover: ["cover", "no-repeat"], contain: ["contain", "no-repeat"], tile: ["auto", "repeat"], stretch: ["100% 100%", "no-repeat"] }[bgPrefs.fit] || ["cover", "no-repeat"];
      root.style.setProperty("--ms-bg-size", fit[0]);
      root.style.setProperty("--ms-bg-repeat", fit[1]);
    }
    function saveBg() { try { chrome.storage.local.set({ msBgImage: bgImage, msBgPrefs: bgPrefs }); } catch {} applyCustomBackground(); }
    let lastIdea = null; const ideaOpts = { engine: "auto", genre: "any", scope: "slice", twist: true, blender: false };
    function effectiveMenuTheme() {
      return (menuPrefs.theme === "mono" || menuPrefs.theme === "auto") && effectiveLight() ? "frost" : menuPrefs.theme;
    }
    // 6.28: the chat bar can carry its OWN theme ("auto" = follow the menu).
    // Judged on its own theme, not the menu's, so a ported bar (mounted inside
    // a provider composer, outside #zs-root) never inherits page colours.
    function effectiveBarTheme() {
      const t = menuPrefs.barTheme || "auto";
      const resolved = t === "auto" ? effectiveMenuTheme() : t;
      return (resolved === "mono" || resolved === "auto") ? (effectiveLight() ? "frost" : "mono") : resolved;
    }
    function effectiveBarLight() {
      const t = effectiveBarTheme();
      if (LIGHT_MENU_THEMES.includes(t)) return true;
      if (DARK_MENU_THEMES.includes(t)) return false;
      return effectiveLight();
    }
    function applyMenuPrefs() {
      if (!root) return;
      document.documentElement.dataset.msUltraPalette=menuPrefs.ultraPalette;
      document.documentElement.dataset.msUltraAnimation=menuPrefs.ultraAnimation;
      let accent = /^#[0-9a-f]{6}$/i.test(menuPrefs.accent || "") ? menuPrefs.accent : DEFAULT_MENU_PREFS.accent;
      if (menuPrefs.theme === "fnaf" && menuPrefs.fnaf && FNAF_CAST[menuPrefs.fnaf.cast] && FNAF_CAST[menuPrefs.fnaf.cast].accent) accent = FNAF_CAST[menuPrefs.fnaf.cast].accent;
      // Special (scene) themes bring a signature accent, but only as the
      // default: an accent the user picked always wins (6.35).
      const userAccent = /^#[0-9a-f]{6}$/i.test(menuPrefs.accent || "") &&
        (menuPrefs.accentUser === true || String(menuPrefs.accent).toLowerCase() !== DEFAULT_MENU_PREFS.accent);
      if (!userAccent && typeof MSThemes!=="undefined" && ["scream","myers","slender","jason","cobalt","porcelain","ember","tidal","starlight","daybreak"].includes(menuPrefs.theme)) accent=MSThemes.get(menuPrefs.theme).accent;
      const widths = MENU_WIDTHS;
      root.style.setProperty("--ms-accent", accent);
      root.style.setProperty("--ms-menu-width", (widths[menuPrefs.width] || widths.medium) + "px");
      root.style.setProperty("--ms-ui-scale", String((Number(menuPrefs.scale) || 100) / 100));
      root.style.setProperty("--ms-radius", menuPrefs.radius === "sharp" ? "4px" : menuPrefs.radius === "round" ? "16px" : "9px");
      root.dataset.msDensity = menuPrefs.density;
      root.dataset.msTheme = effectiveMenuTheme();
      applyCustomBackground();
      document.documentElement.classList.toggle("zs-light", effectiveLight());
      root.dataset.msFont = menuPrefs.font;
      root.dataset.msBackdrop = menuPrefs.backdrop;
      root.dataset.msMotion = menuPrefs.motion;
      syncExecutionEffortUI();
      root.dataset.msRadius = menuPrefs.radius;
      root.dataset.msBarDock = menuPrefs.barDock;
      root.dataset.msBarSize = menuPrefs.barSize;
      root.dataset.msBarStyle = menuPrefs.barStyle;
      root.dataset.msBarStatus = menuPrefs.barStatus;
      root.dataset.msHide = (menuPrefs.barHide || []).join(" ");
      // Automatic in-flow docks move #zs-bar into the provider's composer.
      // Mirror bar-specific preferences and variables onto that portal node;
      // otherwise #zs-root-scoped Studio UI rules stop applying and some host
      // styles turn the action cluster into a vertical stack.
      if (bar) {
        bar.dataset.msBarSize = menuPrefs.barSize;
        bar.dataset.msBarStyle = menuPrefs.barStyle;
        bar.dataset.msBarStatus = menuPrefs.barStatus;
        bar.dataset.msHide = (menuPrefs.barHide || []).join(" ");
        bar.dataset.msBarTheme = effectiveBarTheme();
        bar.dataset.msMotion = menuPrefs.motion;
        bar.style.setProperty("--ms-accent", !userAccent && typeof MSThemes!=="undefined" && ["scream","myers","slender","jason","cobalt","porcelain","ember","tidal","starlight","daybreak"].includes(effectiveBarTheme()) ? MSThemes.get(effectiveBarTheme()).accent : accent);
        const sv = menuPrefs.barSize === "compact" ? ["26px", "11px", "5px"]
          : menuPrefs.barSize === "roomy" ? ["36px", "13px", "8px"]
          : ["30px", "12px", "6px"];
        bar.style.setProperty("--zbh", sv[0]);
        bar.style.setProperty("--zbfs", sv[1]);
        bar.style.setProperty("--zb-gap", sv[2]);
        const lightBar = effectiveBarLight();
        bar.dataset.msBarLight=lightBar?"1":"0";
        // 6.35.1: a bar whose theme disagrees with the page (light theme on a dark
        // site or the reverse) must paint its own surface, or its ink lands on the
        // host composer colour and the chips/status fade out.
        bar.dataset.msBarClash = lightBar !== !!pageIsLight ? "1" : "0";
        bar.style.setProperty("--zb-surface", typeof MSThemes!=="undefined" && ["scream","myers","slender","jason","cobalt","porcelain","ember","tidal","starlight","daybreak"].includes(effectiveBarTheme()) ? MSThemes.get(effectiveBarTheme()).bg : lightBar ? "rgba(255,255,255,.94)" : "rgba(24,24,30,.92)");
        bar.style.setProperty("--zb-line", lightBar ? "rgba(0,0,0,.1)" : "rgba(255,255,255,.11)");
        bar.style.setProperty("--zb-ghost", lightBar ? "rgba(0,0,0,.045)" : "rgba(255,255,255,.055)");
        bar.style.setProperty("--zb-ghost-hover", lightBar ? "rgba(0,0,0,.09)" : "rgba(255,255,255,.115)");
        bar.style.setProperty("--zb-shadow", lightBar ? "0 10px 30px rgba(15,23,42,.14)" : "0 10px 32px rgba(0,0,0,.42)");
      }
      try { ensureFnafLayer(); } catch {}
      try { ensureSceneLayer(); ensureBarScene(); } catch {}
      if (brandEl) {
        brandEl.replaceChildren();
        const name=document.createElement('span');name.className='ms-brand-name';name.textContent=`${menuPrefs.brandIcon || "✦"} ${menuPrefs.brandName || "Multi-Script"}`;brandEl.appendChild(name);
        const effort=document.createElement("span");effort.id="ms-effort-indicator";effort.className=executionEffort==='ultra'?'ms-ultra-title':'';effort.textContent=EXECUTION_EFFORTS[executionEffort].label;effort.setAttribute("aria-label",effort.textContent+" execution effort");effort.title=EXECUTION_EFFORTS[executionEffort].hint;brandEl.appendChild(effort);
        const v=document.createElement("span"); v.className="zs-free"; v.textContent=`v${EXT_VERSION}`; brandEl.appendChild(v);
      }
    }
    // Ambient light: move the panel's own radial origin to follow the pointer.
    // Written straight to a custom property, so it costs one style write per
    // FRAME-COALESCED move and never touches layout. Skipped entirely when the
    // user chose reduced/none motion, since a moving highlight IS motion.
    function installAmbientLight() {
      let raf = 0, lastX = 0, lastY = 0;
      const apply = () => {
        raf = 0;
        if (!menuEl || !menuEl.offsetParent) return;
        const r = menuEl.getBoundingClientRect();
        if (!r.width || !r.height) return;
        const x = Math.max(0, Math.min(100, ((lastX - r.left) / r.width) * 100));
        const y = Math.max(0, Math.min(100, ((lastY - r.top) / r.height) * 100));
        menuEl.style.setProperty("--mono-mx", x.toFixed(1) + "%");
        menuEl.style.setProperty("--mono-my", y.toFixed(1) + "%");
      };
      document.addEventListener("mousemove", (e) => {
        if (menuPrefs.motion !== "full") return;
        if (!menuEl || menuEl.hidden) return;
        lastX = e.clientX; lastY = e.clientY;
        if (!raf) raf = requestAnimationFrame(apply);
      }, { passive: true });
    }
    installAmbientLight();
    // ── Fazbear's: scene layer, Backstage tab, night shift, Phone Guy ──────
    let fnafLayerEl = null, fnafTimer = 0, fnafShiftT0 = 0, fnafSave = 0, fnafSecretNew = false, fnafEgg = { n: 0, t: 0 }, fnafCallTimer = 0;
    let fnafGame = null, fnafOfficeNote = "", fnafFx = 0; // fnafGame = { s, last, timer } while a Security Office night is running
    const FNAF_TIPS = [
      "Hello? Hello, hello? Uh, welcome to your first night at Multi-Script. In the Chat bar tab you can nudge the bar anywhere - it remembers a position for each AI site.",
      "Uh, if the bar ever wanders off, press Reset nudge in the Chat bar tab. Classic. Happens to everyone.",
      "'Start without engine' lets you use this same bar for plain chat when no editor is connected. Handy on slow nights.",
      "The terminal icon in the bar opens the bridge log. If something is wrong, that is the first camera to check.",
      "Turn Memory on in the Agent tab and the AI keeps its decisions between turns. Uh, don't skip that one.",
      "In the Look tab the chat bar can wear its own theme - even a different one from this menu. Mix and match.",
      "The Game ideas tab writes a full brief from an engine, a genre and a twist. Insert it and let the night shift begin.",
      "Ask the AI to inspect the project first, then change things. Read before write. That's, uh, rule number one.",
      "Reply pacing in the Agent tab controls how fast tool calls are sent. If a model keeps repeating a failing call, slow it down.",
      "Back up your settings from the Help tab before you experiment. Fazbear Entertainment is not responsible for lost work.",
      "The Running list shows live tool calls. If a chain goes the wrong way, stop it there.",
      "Before a long job, glance at the bridge status dot. Green means the cameras are up.",
      "Uh, you can search every setting with the box at the top of this panel. Even the secret ones. Not that there are any.",
      "Don't forget to blink. That is not in the manual, but it is, uh, good advice. Phone Guy out.",
      "If a tool result is huge, Settings, then Limits, decides how it is split into pages. 'Reset to automatic' is the safe default. Uh, ask me how I know.",
      "Staging mode lets you review a change before it touches the project. Peek at the plan first. Always peek at the plan.",
      "You can switch the chat bar to its own theme. Even Fazbear's. Especially Fazbear's. It has tiles.",
      "Pro tip: the Skills panel has hundreds of recipes. Pick one before you start a long build and the AI stays on track.",
      "Uh, if you need a real break, the night shift clock in this tab counts thirty minutes. Reach 6 AM, stand up, drink some water.",
      "Whatever you hear from the vents, uh, it's probably the bridge. Probably.",
    ];
    // Phone Guy briefs you at the start of every Security Office night and ties it to a real feature.
    const FNAF_NIGHT_CALLS = [
      "Uh, hello? Welcome to your first night. Doors and lights cost power, so use them only when you must. Keys: A and D are the doors, Q and E the lights, C the camera. Bonnie comes down the left side, Chica the right. Check the light, close the door when someone's there. Real-world tip: you can nudge the chat bar anywhere from the Chat bar tab.",
      "Night two. Foxy gets restless when nobody is watching the Cove. Keep camera four on him now and then, and when he runs, shut the left door. Also, turn Memory on in the Agent tab so the AI remembers decisions, uh, between turns.",
      "Night three. Bonnie and Chica are moving faster, so don't leave a door shut for long. If the power dies, Freddy plays his little tune and, well. Back up your settings from the Help tab while you're thinking about it.",
      "Night four. Everything is quicker and the power is tighter. Cameras eat power too, so glance, don't stare. Reply pacing in the Agent tab helps when a model keeps hammering a failing call.",
      "Last night. Everyone is awake. Short, careful checks, doors only for a visitor. If you make it to 6 AM, the Fredbear costume is yours. And hey - uh - thanks for staying. Phone Guy out.",
    ];
    const FNAF_GREETINGS = [
      "Welcome back, night guard.", "Fazbear's is open. The party never ends.", "Smells like pizza... and static.",
      "Did you hear that? ...Probably the vents.", "Checking the cameras? Good idea.",
    ];
    function fnafPizzaSvg(rng, slice) {
      const jit = (v, a) => (v + (rng() - 0.5) * a).toFixed(1);
      if (slice) {
        const t = `M50 ${jit(8, 3)} C ${jit(66, 4)} ${jit(22, 4)}, ${jit(82, 4)} ${jit(52, 4)}, ${jit(88, 3)} ${jit(90, 2)} C ${jit(66, 4)} 96, ${jit(36, 4)} 96, ${jit(12, 3)} ${jit(90, 2)} C ${jit(18, 4)} ${jit(54, 4)}, ${jit(34, 4)} ${jit(22, 4)}, 50 ${jit(8, 3)} Z`;
        return `<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><path d="${t}" fill="#f2c24b" stroke="#5a3412" stroke-width="3.4" stroke-linejoin="round"/><path d="M14 88 C 36 98 64 98 86 88" fill="none" stroke="#c98a45" stroke-width="9" stroke-linecap="round"/><path d="M14 88 C 36 98 64 98 86 88" fill="none" stroke="#5a3412" stroke-width="1.6" stroke-linecap="round" opacity=".7"/><circle cx="${jit(50, 6)}" cy="${jit(40, 6)}" r="7.5" fill="#c8402f" stroke="#6e1d14" stroke-width="2"/><circle cx="${jit(38, 6)}" cy="${jit(66, 6)}" r="7" fill="#c8402f" stroke="#6e1d14" stroke-width="2"/><circle cx="${jit(63, 6)}" cy="${jit(68, 6)}" r="6.5" fill="#c8402f" stroke="#6e1d14" stroke-width="2"/><ellipse cx="${jit(52, 8)}" cy="${jit(58, 6)}" rx="3.4" ry="2.2" fill="#2d2d2d"/><path d="M44 28 q4 3 8 0" fill="none" stroke="#fff6c8" stroke-width="2" opacity=".6" stroke-linecap="round"/></svg>`;
      }
      const pts = []; for (let i = 0; i < 28; i++) { const a = (i / 28) * Math.PI * 2, r = 46 + (rng() - 0.5) * 2.4; pts.push(`${(50 + Math.cos(a) * r).toFixed(1)},${(50 + Math.sin(a) * r).toFixed(1)}`); }
      let top = "";
      const n = 6 + Math.floor(rng() * 3);
      for (let i = 0; i < n; i++) { const a = (i / n) * Math.PI * 2 + rng() * 0.5, r = 14 + rng() * 20; top += `<circle cx="${(50 + Math.cos(a) * r).toFixed(1)}" cy="${(50 + Math.sin(a) * r).toFixed(1)}" r="${(5.6 + rng() * 2.4).toFixed(1)}" fill="#c8402f" stroke="#6e1d14" stroke-width="1.8"/>`; }
      for (let i = 0; i < 5; i++) { const a = rng() * Math.PI * 2, r = 10 + rng() * 28; const x = (50 + Math.cos(a) * r).toFixed(1), y = (50 + Math.sin(a) * r).toFixed(1); top += i % 2 ? `<circle cx="${x}" cy="${y}" r="2.6" fill="none" stroke="#262626" stroke-width="1.6"/>` : `<path d="M${x} ${y} l5 -2 l1.5 4 z" fill="#4b9b45" stroke="#245c22" stroke-width="1"/>`; }
      return `<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><polygon points="${pts.join(" ")}" fill="#d9964a" stroke="#5a3412" stroke-width="3.4" stroke-linejoin="round"/><circle cx="50" cy="50" r="38" fill="#f4c542" stroke="#b97a22" stroke-width="2"/><path d="M50 50 L50 12 M50 50 L83 69 M50 50 L17 69" stroke="#b97a22" stroke-width="1.4" opacity=".55"/>${top}<path d="M30 24 q8 -6 18 -7" fill="none" stroke="#fff6c8" stroke-width="2.4" opacity=".55" stroke-linecap="round"/></svg>`;
    }
    function fnafRng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
    function fnafBuildPizzas(box, f) {
      box.textContent = "";
      const speed = Math.max(0.25, f.speed / 100);
      for (let i = 0; i < f.pizzas; i++) {
        const rng = fnafRng(1000 + i * 7919);
        const size = 46 + rng() * 76, el = document.createElement("div");
        el.className = "ms-fnaf-pz";
        const set = (k, v) => el.style.setProperty(k, v);
        set("--sz", size.toFixed(0) + "px"); set("--lx", (4 + rng() * 84).toFixed(1) + "%"); set("--ly", (6 + rng() * 80).toFixed(1) + "%");
        set("--dx", ((rng() - 0.5) * 2 * (50 + rng() * 110)).toFixed(0) + "px"); set("--dy", ((rng() - 0.5) * 2 * (36 + rng() * 90)).toFixed(0) + "px");
        set("--rot", (rng() < 0.5 ? -360 : 360) + "deg"); set("--dur", ((24 + rng() * 26) / speed).toFixed(1) + "s"); set("--delay", (-rng() * 40).toFixed(1) + "s");
        set("--blur", (f.blur * (size > 90 ? 1.35 : size < 62 ? 0.7 : 1)).toFixed(1) + "px"); set("--op", (0.55 + rng() * 0.3).toFixed(2));
        el.innerHTML = fnafPizzaSvg(rng, i % 4 === 3);
        box.appendChild(el);
      }
    }
    // 6.34 environment scenes: Woodsboro, Haddonfield, the Slender woods and
    // Camp Crystal Lake drawn live behind the menu (shared with the IDE).
    let sceneLayer = null, sceneKey = "";
    let barScene = null, barSceneKey = "";
    function ensureBarScene() {
      if (!bar || typeof MSScenes === "undefined") return;
      const id = effectiveBarTheme();
      const motion = menuPrefs.motion !== "full" ? menuPrefs.motion : (window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "reduced" : "full");
      const key = MSScenes.has(id) ? id + ":" + motion : "";
      if (key === barSceneKey && (!key || barScene?.root.parentNode === bar)) return;
      if (barScene) barScene.unmount();
      barScene = null; barSceneKey = key;
      bar.classList.toggle("ms-bar-scene-on", !!key);
      if (key) { barScene = MSScenes.mount(bar, id, { motion, caption: false, pointer: false }); barScene.root.classList.add("ms-bar-scene"); }
    }
    function ensureSceneLayer() {
      if (!menuEl) return;
      const id = menuPrefs.theme;
      const S = typeof MSScenes !== "undefined" ? MSScenes : null;
      const on = !!S && id !== "fnaf" && S.has(id) && menuPrefs.sceneOff !== true;
      const motion = menuPrefs.motion !== "full" ? menuPrefs.motion : (window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "reduced" : "full");
      const key = on ? id + ":" + motion : "";
      if (key === sceneKey && (!on || (sceneLayer && sceneLayer.root.parentNode === menuEl))) return;
      if (sceneLayer) { try { sceneLayer.unmount(); } catch {} sceneLayer = null; }
      sceneKey = key;
      menuEl.classList.toggle("ms-scene-on", on);
      if (!on) return;
      sceneLayer = S.mount(menuEl, id, { motion, caption: false, pointerHost: menuEl });
      if (sceneLayer) sceneLayer.root.classList.add("ms-menu-scene");
    }
    function ensureFnafLayer() {
      if (!menuEl) return;
      const f = menuPrefs.fnaf || FNAF_DEFAULTS;
      if (menuPrefs.theme !== "fnaf") {
        if (fnafLayerEl && fnafLayerEl.parentNode) fnafLayerEl.remove();
        menuEl.classList.remove("ms-fnaf-on", "ms-fnaf-static", "ms-fnaf-flicker", "ms-fnaf-spot-on");
        fnafOfficeStop();
        ["--fz-tile", "--fz-glow", "--fz-depth"].forEach((k) => menuEl.style.removeProperty(k));
        if (fnafTimer) { clearInterval(fnafTimer); fnafTimer = 0; }
        return;
      }
      menuEl.classList.add("ms-fnaf-on");
      menuEl.classList.toggle("ms-fnaf-static", !!f.staticFx);
      menuEl.classList.toggle("ms-fnaf-flicker", !!f.flicker);
      menuEl.classList.toggle("ms-fnaf-spot-on", !!f.spot);
      menuEl.style.setProperty("--fz-tile", f.tile + "px");
      menuEl.style.setProperty("--fz-glow", String(f.glow / 100));
      if (!fnafLayerEl) {
        fnafLayerEl = document.createElement("div");
        fnafLayerEl.className = "ms-fnaf-layer"; fnafLayerEl.setAttribute("aria-hidden", "true");
        fnafLayerEl.innerHTML = '<div class="ms-fnaf-wall"></div><div class="ms-fnaf-spot"></div><div class="ms-fnaf-pizzas"></div><div class="ms-fnaf-purple"></div><div class="ms-fnaf-top"></div><div class="ms-fnaf-bottom"></div><div class="ms-fnaf-static"></div>';
      }
      if (fnafLayerEl.parentNode !== menuEl || menuEl.firstChild !== fnafLayerEl) menuEl.insertBefore(fnafLayerEl, menuEl.firstChild);
      const key = [f.pizzas, f.speed, f.blur].join("|");
      if (fnafLayerEl.dataset.key !== key) { fnafLayerEl.dataset.key = key; fnafBuildPizzas(fnafLayerEl.querySelector(".ms-fnaf-pizzas"), f); }
      if (!menuEl._fnafScroll) {
        menuEl._fnafScroll = true;
        menuEl.addEventListener("scroll", (e) => {
          const t = e.target; if (!t || t.id !== "zs-pane") return;
          const max = Math.max(1, t.scrollHeight - t.clientHeight);
          menuEl.style.setProperty("--fz-depth", Math.max(0, Math.min(1, t.scrollTop / max)).toFixed(3));
        }, true);
      }
      const pane = menuEl.querySelector("#zs-pane");
      if (pane) { const max = Math.max(1, pane.scrollHeight - pane.clientHeight); menuEl.style.setProperty("--fz-depth", Math.max(0, Math.min(1, pane.scrollTop / max)).toFixed(3)); }
      else menuEl.style.setProperty("--fz-depth", "0");
      if (f.shift && !fnafTimer) { if (!fnafShiftT0) fnafShiftT0 = Date.now(); fnafTimer = setInterval(fnafShiftTick, 1000); }
      if (!f.shift && fnafTimer) { clearInterval(fnafTimer); fnafTimer = 0; fnafShiftT0 = 0; }
    }
    function fnafHourLabel(h) { return h === 0 ? "12 AM" : h + " AM"; }
    function fnafShiftTick() {
      const f = menuPrefs.fnaf;
      if (menuPrefs.theme !== "fnaf" || !f.shift) { clearInterval(fnafTimer); fnafTimer = 0; return; }
      const el = Date.now() - fnafShiftT0, hour = Math.min(6, Math.floor(el / FNAF_HOUR_MS));
      const clock = menuEl && menuEl.querySelector("#ms-fz-clock");
      if (clock) {
        clock.textContent = fnafHourLabel(hour);
        const bar = menuEl.querySelector("#ms-fz-clock-bar"); if (bar) bar.style.width = Math.min(100, (el / (FNAF_HOUR_MS * 6)) * 100).toFixed(1) + "%";
      }
      if (hour >= 6) {
        clearInterval(fnafTimer); fnafTimer = 0; fnafShiftT0 = 0;
        menuPrefs.fnaf = sanitizeFnaf({ ...f, shift: false, nights: f.nights + 1, golden: true, office: { ...f.office, ach: f.office.ach.includes("shift") ? f.office.ach : [...f.office.ach, "shift"] } });
        saveMenuPrefs();
        toast(`6 AM. Night ${menuPrefs.fnaf.nights} survived - stretch your legs! Golden is waiting backstage.`);
        if (menuEl && !menuEl.hidden) buildMenu();
      }
    }
    function setFnaf(patch, opts = {}) {
      menuPrefs.fnaf = sanitizeFnaf({ ...(menuPrefs.fnaf || FNAF_DEFAULTS), ...patch });
      if (opts.debounce) { applyMenuPrefs(); clearTimeout(fnafSave); fnafSave = setTimeout(() => { try { chrome.storage.local.set({ msMenuPreferences: menuPrefs }); } catch {} }, 250); }
      else saveMenuPrefs();
      if (opts.rebuild) { const keep = (menuEl.querySelector("#zs-pane") || {}).scrollTop || 0; buildMenu(); const pn = menuEl.querySelector("#zs-pane"); if (pn) pn.scrollTop = keep; }
    }
    // ── Security Office (the secret game) ───────────────────────────────────
    const FNAF_O = () => ZSExtras.FNAF_OFFICE;
    function fnafKeycard(f) { return f.calls >= 3 || f.golden || f.office.cleared >= 1; }
    function fnafMotionOk() {
      let reduce = false; try { reduce = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches); } catch {}
      return menuPrefs.motion === "full" && !reduce;
    }
    function fnafOfficeHtml(f) {
      if (!fnafKeycard(f)) {
        return `<div class="ms-fz-door"><div class="ms-fz-door-sign">STAFF ONLY</div><div class="ms-fz-door-note">Keycard required. Phone Guy has one - answer his calls below (${Math.min(3, f.calls)}/3), or find whatever is watching you from the monitor.</div></div>`;
      }
      const o = f.office, next = Math.min(FNAF_O().NIGHTS, o.cleared + 1);
      const nights = Array.from({ length: next }, (_, i) => `<option value="${i + 1}"${i + 1 === next ? " selected" : ""}>Night ${i + 1}${i + 1 <= o.cleared ? " (cleared)" : ""}</option>`).join("");
      const ctl = (id, label, key) => `<button type="button" class="ms-fz-ctl" data-fz-ctl="${id}" aria-pressed="false" disabled><b>${label}</b><kbd>${key}</kbd></button>`;
      const cams = FNAF_O().CAMS.map((c, i) => `<button type="button" class="ms-fz-camb" data-fz-cam="${c}" disabled>CAM ${i + 1}<small>${{ stage: "Stage", dining: "Dining", hall: "Hall", cove: "Cove" }[c]}</small></button>`).join("");
      const ach = Object.entries(FNAF_ACH).map(([id, name]) => `<span class="ms-fz-ach${o.ach.includes(id) ? " got" : ""}" title="${o.ach.includes(id) ? "Unlocked" : "Locked"}">${o.ach.includes(id) ? "★" : "☆"} ${name}</span>`).join("");
      return `<div class="ms-fz-office" id="ms-fz-office" tabindex="0" data-state="idle" aria-label="Security office game">
        <div class="ms-fz-hud"><b id="ms-fz-o-clock">12 AM</b><span id="ms-fz-o-night">Night ${next}</span><span id="ms-fz-o-power">Power 100%</span><span class="ms-fz-use" id="ms-fz-o-use" aria-label="Power usage"><i></i><i></i><i></i><i></i><i></i></span></div>
        <div class="ms-fz-screen" id="ms-fz-screen" aria-live="polite"><div class="ms-fz-view" id="ms-fz-o-view">Your keycard works. Press Start when you are ready.</div></div>
        <div class="ms-fz-cams">${cams}</div>
        <div class="ms-fz-ctls">${ctl("doorL", "Left door", "A")}${ctl("lightL", "Left light", "Q")}${ctl("cam", "Camera", "C")}${ctl("lightR", "Right light", "E")}${ctl("doorR", "Right door", "D")}</div>
        <div class="ms-fz-startrow"><select id="ms-fz-o-sel" class="zs-mcp-field" aria-label="Night">${nights}</select><button type="button" class="ms-fz-answer" id="ms-fz-o-start">▶ Start night</button><span id="ms-fz-o-stat">${o.cleared}/5 cleared · ${o.wins} win${o.wins === 1 ? "" : "s"} · ${o.deaths} loss${o.deaths === 1 ? "" : "es"}</span></div>
        <div class="ms-fz-msg" id="ms-fz-o-msg">${fnafOfficeNote || "Survive until 6 AM. Doors and lights drain power; cameras too. Keys: A/D doors, Q/E lights, C camera, 1-4 cameras."}</div>
        <div class="ms-fz-achs">${ach}</div>
      </div>`;
    }
    function fnafOfficeRender() {
      const g = fnafGame; if (!g || !menuEl) return;
      const s = g.s, q = (id) => menuEl.querySelector("#" + id), O = FNAF_O();
      const root = q("ms-fz-office"); if (!root) return;
      root.dataset.state = s.outcome || "run";
      const clock = q("ms-fz-o-clock"); if (clock) clock.textContent = fnafHourLabel(s.hour);
      const pw = q("ms-fz-o-power"); if (pw) { pw.textContent = "Power " + Math.ceil(s.power) + "%"; pw.classList.toggle("low", s.power < 20); }
      const use = O.usage(s); menuEl.querySelectorAll("#ms-fz-o-use i").forEach((el, i) => el.classList.toggle("on", i < use));
      menuEl.querySelectorAll("[data-fz-ctl]").forEach((b) => { const on = !!s[b.dataset.fzCtl]; b.classList.toggle("on", on); b.setAttribute("aria-pressed", String(on)); b.disabled = !!s.outcome || s.power <= 0; });
      menuEl.querySelectorAll("[data-fz-cam]").forEach((b) => { b.classList.toggle("on", s.cam && s.camSel === b.dataset.fzCam); b.disabled = !!s.outcome || s.power <= 0; });
      const v = O.view(s), view = q("ms-fz-o-view"), scr = q("ms-fz-screen");
      if (scr) scr.dataset.mode = v.mode;
      if (view) {
        const head = v.mode === "cam" ? `<small>CAM ${O.CAMS.indexOf(v.cam) + 1} - ${v.cam.toUpperCase()}</small>` : v.mode === "light" ? `<small>${v.side === "lightL" ? "LEFT" : "RIGHT"} HALLWAY LIGHT</small>` : v.mode === "dark" ? "<small>NO POWER</small>" : "<small>OFFICE</small>";
        const doors = `${s.doorL ? "Left door CLOSED" : "Left door open"} · ${s.doorR ? "Right door CLOSED" : "Right door open"}`;
        view.innerHTML = head + `<div class="ms-fz-viewmain">${(v.lines.length ? v.lines : [doors]).map((l) => `<span>${l.replace(/[<>&]/g, "")}</span>`).join("")}</div>`;
      }
    }
    function fnafOfficeStop() { if (fnafGame) { clearInterval(fnafGame.timer); fnafGame = null; } }
    function fnafOfficeStart(night) {
      fnafOfficeStop();
      const O = FNAF_O(), root = menuEl && menuEl.querySelector("#ms-fz-office"); if (!root) return;
      const s = O.create(night);
      fnafGame = { s, last: performance.now(), timer: 0 };
      const msg = menuEl.querySelector("#ms-fz-o-msg"); if (msg) msg.textContent = FNAF_NIGHT_CALLS[s.night - 1];
      const st = menuEl.querySelector("#ms-fz-o-start"); if (st) { st.textContent = "■ Abandon"; st.dataset.mode = "stop"; }
      const sel = menuEl.querySelector("#ms-fz-o-sel"); if (sel) sel.disabled = true;
      const n = menuEl.querySelector("#ms-fz-o-night"); if (n) n.textContent = "Night " + s.night;
      fnafOfficeRender(); try { root.focus({ preventScroll: true }); } catch {}
      const me = fnafGame;
      me.timer = setInterval(() => {
        if (fnafGame !== me) { clearInterval(me.timer); return; }
        if (!menuEl || menuEl.hidden || menuPrefs.theme !== "fnaf" || !menuEl.querySelector("#ms-fz-office")) { fnafOfficeStop(); return; }
        const now = performance.now(), dt = Math.min(250, Math.max(0, now - me.last)); me.last = now;
        O.step(me.s, dt, Math.random);
        for (const ev of me.s.events) if (ev.type === "knock") { const m = menuEl.querySelector("#ms-fz-o-msg"); if (m) m.textContent = "BANG! Foxy hit the door. Power -4%."; }
        fnafOfficeRender();
        if (me.s.outcome) fnafOfficeFinish(me.s);
      }, 100);
    }
    function fnafOfficeFinish(s) {
      fnafOfficeStop();
      const f = menuPrefs.fnaf, o = f.office, ach = new Set(o.ach);
      if (s.outcome === "dead") {
        const who = { bonnie: "Bonnie", chica: "Chica", foxy: "Foxy", freddy: "Freddy" }[s.killer] || "Someone";
        setFnaf({ office: { ...o, deaths: o.deaths + 1 } });
        const root = menuEl.querySelector("#ms-fz-office"), view = menuEl.querySelector("#ms-fz-o-view");
        if (view) view.innerHTML = `<small>GAME OVER</small><div class="ms-fz-viewmain ms-fz-scare"><span class="ms-fz-face">◉ ◉</span><span>${who} got you at ${fnafHourLabel(s.hour)}.</span></div>`;
        if (root && f.jumpscare && fnafMotionOk()) { root.classList.add("ms-fz-shake"); setTimeout(() => root.classList.remove("ms-fz-shake"), 700); }
        fnafOfficeEnd(`${who} got you at ${fnafHourLabel(s.hour)}. Close the door earlier next time - check the light first.`, false);
        return;
      }
      const sc = FNAF_O().score(s), cleared = Math.max(o.cleared, s.night), before = o.cleared;
      ach.add("first_night"); if (s.night >= 5) ach.add("night_five"); if (sc.power >= 40) ach.add("penny"); if (sc.power < 8) ach.add("close_call"); if (s.flags.foxyBlocked > 0) ach.add("knock");
      const unlocked = Object.entries(FNAF_CAST).filter(([id, c]) => c.need && c.need > before && c.need <= cleared).map(([, c]) => c.label);
      const goldenNew = !f.golden;
      setFnaf({ office: { ...o, cleared, wins: o.wins + 1, ach: [...ach] } });
      let note = `6 AM! Night ${s.night} survived with ${sc.power}% power.`;
      if (goldenNew) note += " Golden is waiting on the stage.";
      if (unlocked.length) note += " Unlocked: " + unlocked.join(", ") + ".";
      if (s.night >= 5) note += " That is every night - the party is yours.";
      fnafOfficeEnd(note, true);
    }
    function fnafOfficeEnd(note, win) {
      fnafOfficeNote = note;
      const f = menuPrefs.fnaf, o = f.office, q = (id) => menuEl.querySelector("#" + id), O = FNAF_O();
      const next = Math.min(O.NIGHTS, o.cleared + 1);
      const st = q("ms-fz-o-start"); if (st) { st.textContent = win && o.cleared < O.NIGHTS ? "▶ Next night" : "▶ Play again"; delete st.dataset.mode; }
      const sel = q("ms-fz-o-sel");
      if (sel) { sel.disabled = false; sel.innerHTML = Array.from({ length: next }, (_, i) => `<option value="${i + 1}"${i + 1 === next ? " selected" : ""}>Night ${i + 1}${i + 1 <= o.cleared ? " (cleared)" : ""}</option>`).join(""); }
      const stat = q("ms-fz-o-stat"); if (stat) stat.textContent = `${o.cleared}/5 cleared · ${o.wins} win${o.wins === 1 ? "" : "s"} · ${o.deaths} loss${o.deaths === 1 ? "" : "es"}`;
      const msg = q("ms-fz-o-msg"); if (msg) msg.textContent = note;
      const achs = menuEl.querySelector(".ms-fz-achs");
      if (achs) achs.innerHTML = Object.entries(FNAF_ACH).map(([id, name]) => `<span class="ms-fz-ach${o.ach.includes(id) ? " got" : ""}" title="${o.ach.includes(id) ? "Unlocked" : "Locked"}">${o.ach.includes(id) ? "★" : "☆"} ${name}</span>`).join("");
      if (win) { const v = q("ms-fz-o-view"); if (v) v.innerHTML = '<small>6 AM</small><div class="ms-fz-viewmain"><span>You made it. The sun is coming up.</span></div>'; }
      // refresh the cast grid so newly unlocked members open right away
      const grid = menuEl.querySelector(".ms-fz-cast-grid");
      if (grid) { const tmp = document.createElement("div"); tmp.innerHTML = fnafBackstageHtml(); const g2 = tmp.querySelector(".ms-fz-cast-grid"); if (g2) { grid.innerHTML = g2.innerHTML; bindFnafCast(); } }
      toast(win ? note : "The night ended early. Try again?");
      if (win) fnafConfetti();
    }
    function fnafConfetti() {
      if (!menuEl || !fnafMotionOk()) return;
      clearTimeout(fnafFx); menuEl.querySelectorAll(".ms-fnaf-confetti").forEach((e) => e.remove());
      const box = document.createElement("div"); box.className = "ms-fnaf-confetti"; box.setAttribute("aria-hidden", "true");
      const cols = ["#8b5cf6", "#e0503f", "#f2c230", "#2dd4bf", "#f08fb0"], rng = fnafRng(Date.now() & 0xffff);
      for (let i = 0; i < 26; i++) { const c = document.createElement("i"); c.style.cssText = `left:${(rng() * 100).toFixed(1)}%;background:${cols[i % cols.length]};--d:${(1.6 + rng() * 1.4).toFixed(2)}s;--w:${(-30 + rng() * 60).toFixed(0)}px;animation-delay:${(rng() * 0.5).toFixed(2)}s`; box.appendChild(c); }
      menuEl.appendChild(box); fnafFx = setTimeout(() => box.remove(), 3600);
    }
    // The "special" moment when the theme is picked: curtains part on a lit stage.
    function fnafPlayIntro() {
      if (!menuEl || !fnafMotionOk() || menuPrefs.theme !== "fnaf") return;
      menuEl.querySelectorAll(".ms-fnaf-intro").forEach((e) => e.remove());
      const el = document.createElement("div"); el.className = "ms-fnaf-intro"; el.setAttribute("aria-hidden", "true");
      el.innerHTML = '<i class="l"></i><i class="r"></i><div class="sign"><b>Welcome to</b><span>Fazbear\'s</span><small>Pizza &amp; Prize Corner</small></div>';
      menuEl.appendChild(el); setTimeout(() => el.remove(), 3200);
    }
    function fnafOnSelect() {
      const f = menuPrefs.fnaf, first = !f.seen;
      menuPrefs.fnaf = sanitizeFnaf({ ...f, seen: true, visits: f.visits + 1 });
      if (first) { fnafSecretNew = true; setTimeout(() => toast("Welcome to Fazbear's. Something is hiding backstage..."), 900); }
      else setTimeout(() => toast(FNAF_GREETINGS[menuPrefs.fnaf.visits % FNAF_GREETINGS.length]), 900);
      setTimeout(fnafPlayIntro, 60);
    }
    function bindFnafOffice() {
      if (!menuEl) return;
      const O = FNAF_O(), $ = (id) => menuEl.querySelector("#" + id), root = $("ms-fz-office");
      fnafOfficeStop(); // a fresh office DOM never keeps an old night running behind it
      if (!root) return;
      const start = $("ms-fz-o-start");
      if (start) start.addEventListener("click", () => {
        if (fnafGame) { fnafOfficeStop(); fnafOfficeNote = "You walked away from the office."; const w = $("ms-fz-office-wrap"); if (w) { w.innerHTML = fnafOfficeHtml(menuPrefs.fnaf); bindFnafOffice(); } return; }
        const sel = $("ms-fz-o-sel"); fnafOfficeNote = ""; fnafOfficeStart(O.clampNight(sel ? sel.value : 1));
      });
      const act = (what) => { if (!fnafGame) return; O.toggle(fnafGame.s, what); fnafOfficeRender(); };
      menuEl.querySelectorAll("[data-fz-ctl]").forEach((b) => b.addEventListener("click", () => act(b.dataset.fzCtl)));
      menuEl.querySelectorAll("[data-fz-cam]").forEach((b) => b.addEventListener("click", () => {
        if (!fnafGame || fnafGame.s.outcome || fnafGame.s.power <= 0) return;
        O.setCam(fnafGame.s, b.dataset.fzCam); if (!fnafGame.s.cam) O.toggle(fnafGame.s, "cam"); fnafOfficeRender();
      }));
      root.addEventListener("keydown", (e) => {
        if (!fnafGame || e.ctrlKey || e.metaKey || e.altKey) return;
        const k = String(e.key).toLowerCase(), map = { a: "doorL", d: "doorR", q: "lightL", e: "lightR", c: "cam", " ": "cam" };
        if (map[k]) { e.preventDefault(); e.stopPropagation(); act(map[k]); }
        else if (/^[1-4]$/.test(k)) { e.preventDefault(); e.stopPropagation(); const b = menuEl.querySelector(`[data-fz-cam="${O.CAMS[Number(k) - 1]}"]`); if (b) b.click(); }
      });
    }
    function bindFnafCast() {
      if (!menuEl) return;
      menuEl.querySelectorAll("[data-fz-cast]").forEach((b) => { if (b._fz) return; b._fz = true; b.addEventListener("click", () => setFnaf({ cast: b.dataset.fzCast }, { rebuild: true })); });
    }
    function fnafBackstageHtml() {
      const f = menuPrefs.fnaf || FNAF_DEFAULTS;
      const cast = Object.entries(FNAF_CAST).map(([id, c]) => {
        const locked = !fnafCastOpen(id, f);
        return `<button type="button" class="zs-pref-opt ms-fz-cast${f.cast === id ? " active" : ""}${locked ? " locked" : ""}" data-fz-cast="${id}"${locked ? ` disabled title="${c.hint || "Locked"}"` : ""}><i style="background:${c.accent || "linear-gradient(135deg,#999,#ddd)"}"></i>${locked ? "🔒 " : ""}${c.label}</button>`;
      }).join("");
      const slider = (id, label, min, max, step, val, unit) => `<div class="zs-slider-row"><span class="zs-slider-label">${label}</span><input id="${id}" type="range" min="${min}" max="${max}" step="${step}" value="${val}" aria-label="${label}"><b id="${id}-v">${val}${unit}</b></div>`;
      const tog = (key, label) => `<label class="zs-chip-toggle${f[key] ? " on" : ""}"><input type="checkbox" data-fz-toggle="${key}"${f[key] ? " checked" : ""}><span>${label}</span></label>`;
      const tileSeg = [[18, "Small"], [24, "Medium"], [32, "Large"]].map(([v, l]) => `<button type="button" class="zs-pref-opt${f.tile === v ? " active" : ""}" data-fz-tile="${v}">${l}</button>`).join("");
      return `<section class="zs-menu-sec ms-fz-sec" data-zs-tab="backstage">
        <div class="zs-sec-label"><span>After hours · ${f.nights} shift${f.nights === 1 ? "" : "s"} survived</span><span class="zs-provider-badge ms-fz-badge">secret</span></div>
        <div class="ms-fz-monitor"><span class="ms-fz-eyes" id="ms-fz-eyes" role="button" tabindex="0" aria-label="Two glowing eyes">◉ ◉</span><div><b>Fazbear Entertainment - after hours</b><span>This tab only exists while the Fazbear's theme is on. Everything here is cosmetic and local; nothing leaves your browser.</span></div></div>
        <div class="zs-setting-title">Security office</div>
        <div id="ms-fz-office-wrap">${fnafOfficeHtml(f)}</div>
        <div class="zs-setting-title">Stage cast</div>
        <div class="zs-menu-note">Pick who runs the stage: it sets the accent colour for the Fazbear's theme and the chat bar. Locked cast members are earned in the Security Office.</div>
        <div class="zs-pref-grid zs-pref-grid-3 ms-fz-cast-grid">${cast}</div>
        <div class="zs-setting-title">Pizza floor</div>
        ${slider("ms-fz-pizzas", "Pizzas", 0, 14, 1, f.pizzas, "")}
        ${slider("ms-fz-speed", "Drift speed", 25, 200, 5, f.speed, "%")}
        ${slider("ms-fz-blur", "Blur", 0, 8, 1, f.blur, " px")}
        <label class="zs-pref-label">Tile size</label><div class="zs-pref-grid zs-pref-grid-3">${tileSeg}</div>
        <div class="zs-setting-title">After hours</div>
        ${slider("ms-fz-glow", "Purple glow", 0, 100, 5, f.glow, "%")}
        <div class="zs-chip-toggles">${tog("flicker", "Lights flicker")}${tog("staticFx", "Camera static")}${tog("spot", "Stage spotlights")}${tog("jumpscare", "Jumpscare flash")}</div>
        <div class="zs-menu-note">The purple hue deepens as you scroll toward the lower settings.</div>
        <div class="zs-setting-title">Night shift</div>
        <div class="ms-fz-shift"><div class="ms-fz-clock"><b id="ms-fz-clock">${f.shift ? "12 AM" : "--"}</b><span>${f.nights} night${f.nights === 1 ? "" : "s"} survived</span></div><div class="ms-fz-clockbar"><i id="ms-fz-clock-bar" style="width:0%"></i></div></div>
        <div class="zs-chip-toggles">${tog("shift", "Start the night shift")}</div>
        <div class="zs-menu-note">A 30-minute work-session clock (one hour every five minutes). Reach 6 AM for a break reminder, a survived night and a hidden unlock.</div>
        <div class="zs-setting-title">Phone Guy</div>
        <div class="ms-fz-phone"><div class="ms-fz-call" id="ms-fz-call" aria-live="polite">Press the button to answer the call.</div><div class="ms-fz-phone-row"><button type="button" class="zs-btn ms-fz-answer" id="ms-fz-answer">☎ Answer call</button><span>${f.calls} call${f.calls === 1 ? "" : "s"} answered</span></div></div>
        <div class="ms-fz-foot"><button type="button" class="zs-linkbtn" id="ms-fz-reset">Reset Backstage</button></div>
      </section>`;
    }
    function bindFnafTab() {
      if (!menuEl || menuPrefs.theme !== "fnaf") return;
      const $ = (id) => menuEl.querySelector("#" + id);
      for (const [id, key, unit] of [["ms-fz-pizzas", "pizzas", ""], ["ms-fz-speed", "speed", "%"], ["ms-fz-blur", "blur", " px"], ["ms-fz-glow", "glow", "%"]]) {
        const r = $(id); if (!r) continue;
        r.addEventListener("input", () => { setFnaf({ [key]: Number(r.value) }, { debounce: true }); const v = $(id + "-v"); if (v) v.textContent = menuPrefs.fnaf[key] + unit; });
      }
      bindFnafCast(); bindFnafOffice();
      menuEl.querySelectorAll("[data-fz-tile]").forEach((b) => b.addEventListener("click", () => setFnaf({ tile: Number(b.dataset.fzTile) }, { rebuild: true })));
      menuEl.querySelectorAll("[data-fz-toggle]").forEach((c) => c.addEventListener("change", () => {
        const key = c.dataset.fzToggle; if (key === "shift") fnafShiftT0 = c.checked ? Date.now() : 0;
        setFnaf({ [key]: c.checked }); const lab = c.closest(".zs-chip-toggle"); if (lab) lab.classList.toggle("on", c.checked);
        if (key === "shift") { const clock = $("ms-fz-clock"); if (clock) clock.textContent = c.checked ? "12 AM" : "--"; if (!c.checked) { const b = $("ms-fz-clock-bar"); if (b) b.style.width = "0%"; } else toast("Night shift started. See you at 6 AM."); }
      }));
      const ans = $("ms-fz-answer");
      if (ans) ans.addEventListener("click", () => {
        const f = menuPrefs.fnaf, text = FNAF_TIPS[f.calls % FNAF_TIPS.length], box = $("ms-fz-call");
        clearInterval(fnafCallTimer); let i = 0; if (box) box.textContent = "";
        ans.disabled = true;
        const reduce = menuPrefs.motion === "none";
        fnafCallTimer = setInterval(() => { i = reduce ? text.length : i + 2; if (box) box.textContent = text.slice(0, i); if (i >= text.length) { clearInterval(fnafCallTimer); ans.disabled = false; } }, 24);
        const hadCard = fnafKeycard(f);
        menuPrefs.fnaf = sanitizeFnaf({ ...f, calls: f.calls + 1 }); clearTimeout(fnafSave);
        if (!hadCard && fnafKeycard(menuPrefs.fnaf)) {
          menuPrefs.fnaf = sanitizeFnaf({ ...menuPrefs.fnaf, office: { ...menuPrefs.fnaf.office, ach: [...menuPrefs.fnaf.office.ach, "keycard"] } });
          setTimeout(() => { toast("Keycard acquired. The Security Office is open."); const w = $("ms-fz-office-wrap"); if (w && !fnafGame) { w.innerHTML = fnafOfficeHtml(menuPrefs.fnaf); bindFnafOffice(); } }, text.length * 12 + 200);
        } fnafSave = setTimeout(() => { try { chrome.storage.local.set({ msMenuPreferences: menuPrefs }); } catch {} }, 250);
        const cnt = ans.nextElementSibling; if (cnt) cnt.textContent = `${menuPrefs.fnaf.calls} call${menuPrefs.fnaf.calls === 1 ? "" : "s"} answered`;
      });
      const eyes = $("ms-fz-eyes");
      if (eyes) eyes.addEventListener("click", () => {
        const now = Date.now(); fnafEgg.n = now - fnafEgg.t < 4000 ? fnafEgg.n + 1 : 1; fnafEgg.t = now;
        if (fnafEgg.n >= 5) {
          fnafEgg.n = 0;
          if (fnafMotionOk() && menuPrefs.fnaf.jumpscare) { menuEl.classList.add("ms-fnaf-jump"); setTimeout(() => menuEl.classList.remove("ms-fnaf-jump"), 1100); }
          toast("...it's me.");
          const o = menuPrefs.fnaf.office;
          setFnaf({ golden: true, cast: "golden", office: { ...o, ach: o.ach.includes("golden_eyes") ? o.ach : [...o.ach, "golden_eyes"] } }, { rebuild: true });
        }
      });
      const reset = $("ms-fz-reset");
      if (reset) reset.addEventListener("click", () => { fnafShiftT0 = 0; fnafOfficeStop(); fnafOfficeNote = ""; menuPrefs.fnaf = sanitizeFnaf({ seen: true }); saveMenuPrefs(); buildMenu(); toast("Backstage reset"); });
      if (fnafSecretNew) { const t = menuEl.querySelector('.zs-menu-tabs button[data-tab="backstage"]'); if (t) { t.classList.add("zs-secret-new"); t.addEventListener("click", () => { t.classList.remove("zs-secret-new"); fnafSecretNew = false; }, { once: true }); } }
    }
    // Provider composers are usually <form>s and some adapters dock the overlay
    // inside or next to that form. HTML buttons default to type=submit, so any
    // newly rendered overlay control without an explicit type can accidentally
    // send the chat instead of performing its own action. Normalize centrally:
    // individual panels no longer have to remember this provider-specific trap.
    function neutralizeFormButtons(scope) {
      if (!scope || !scope.querySelectorAll) return;
      scope.querySelectorAll("button:not([type])").forEach((b) => b.setAttribute("type", "button"));
    }
    function fmtNudge(n) { n = Math.round(Number(n) || 0); return (n > 0 ? "+" : "") + n + " px"; }
    function saveMenuPrefs() { try { chrome.storage.local.set({ msMenuPreferences: menuPrefs }); } catch {} applyMenuPrefs(); }
    try { chrome.storage.local.get("msMenuPreferences", (r) => { if (r && r.msMenuPreferences) menuPrefs = sanitizeMenuPrefs(r.msMenuPreferences); applyMenuPrefs(); if (menuEl && !menuEl.hidden) buildMenu(); }); } catch {}

    function build() {
      root = document.createElement("div");
      root.id = "zs-root";
      // One consolidated status bar, anchored just above the site's composer
      // (positioned every frame by placeBar). It carries everything: live status,
      // the primary action (Start / Stop) and a "more"
      // menu (other AI sites, custom prompt, support, Discord). No floating panel,
      // no overlay on the input - the composer stays fully usable for plain chat.
      root.innerHTML = `
        <div id="zs-bar">
          <div id="zs-id">
            <span id="zs-dot" class="off" title=""></span>
            <div id="zs-idtext">
              <span id="zs-brand">Multi-Script <span class="zs-free">v${EXT_VERSION}</span> <span id="ms-effort-indicator">${EXECUTION_EFFORTS[executionEffort].label}</span></span>
              <span id="zs-state"></span>
            </div>
          </div>
          <div id="zs-acts">
            <button id="zs-action"></button>
            <button id="zs-chat-only" title="Engine-free session: code, design and general tools in chat. Start agent in a fresh chat to edit Studio.">Chat studio</button>
            <button id="zs-software" class="zs-software-btn" title="Build, compile and package a real program in a folder you choose, using the local bridge" style="display:none">Build software</button>
            <button id="ms-blender-open" type="button" aria-label="Open Blender Workspace" title="Blender Workspace · model and animate locally"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m12 3 9 5v8l-9 5-9-5V8l9-5Zm0 9 9-4M3 8l9 4v9"/></svg></button>
            <button id="ms-new-idea" aria-label="New idea" title="New idea · generate directions for this conversation"><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18h6m-5 3h4M8 14a6 6 0 1 1 8 0c-1 1-1 2-1 2H9s0-1-1-2Z"/></svg></button>
            <button id="zs-stop" hidden>■ Stop</button>
            ${P.id === "notion" ? `<button id="zs-model" aria-label="Notion models and trial estimate" title="Notion models and trial estimate"><span id="zs-model-text">Models</span></button>` : ""}
            <span class="zs-acts-sep" aria-hidden="true"></span>
            <a id="zs-discord" href="https://discord.gg/5Q6vvNcpM6" target="_blank" rel="noopener" title="Need help? Join our Discord"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg"><path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/></svg></a>
            <button id="ms-task-chip" type="button" aria-label="Open task progress" title="Task progress"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m3 6 2 2 3-4M11 6h10M3 12h5m3 0h10M3 18h5m3 0h10"/></svg><span hidden></span></button>
            <button id="ms-phone-chip" type="button" aria-label="Open phone control" title="Phone control"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="6" y="2" width="12" height="20" rx="3"/><path d="M10 18h4"/></svg></button>
            <button id="zs-mem" aria-label="Memory" title="Memory: local graph memory for this chat" data-state="off"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="7" r="2.4"/><circle cx="18" cy="6" r="2.4"/><circle cx="12" cy="18" r="2.8"/><path d="M8 8.2l2.7 7.3M16.2 7.7l-3 8.2M8.3 6.8l7.3-.6"/></svg></button>
            <a id="ms-donate-bar" class="ms-donate-icon" href="https://ko-fi.com/multixscript" target="_blank" rel="noopener noreferrer" aria-label="Donate to Multi-Script on Ko-fi" title="Donate on Ko-fi"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/></svg></a>
            <button id="zs-switch" aria-label="Multi-Script settings and AI sites" title="Settings, AI sites, chat bar options"><span id="zs-switch-name"></span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg></button>
            <span class="zs-split" id="zs-bridge-split"><button id="zs-bridge" aria-label="Bridge terminal" title="Bridge terminal"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2.5" y="4" width="19" height="16" rx="2.5"/><polyline points="7 9.5 10 12 7 14.5"/><line x1="12.5" y1="14.5" x2="17" y2="14.5"/></svg></button><button id="zs-bridge-run" aria-label="What is running" title="What is running (bridge, engines, apps)"><svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg></button></span>
          </div>
        </div>
        <section id="ms-startup-info" aria-label="Startup progress" hidden><button id="ms-startup-close" type="button" aria-label="Close startup progress">×</button><b>Getting Multi-Script ready</b><ol><li data-stage="1">Connect local tools</li><li data-stage="2">Send the session instructions</li><li data-stage="3">Check tools and wait for the provider</li></ol><p id="ms-startup-detail"></p><small>Provider response times vary. Multi-Script waits for the current response to finish before continuing. You can cancel startup at any time.</small></section><div id="zs-menu" hidden></div>
      `;
      neutralizeFormButtons(root);
      if (P.id === "vani") setTimeout(() => toast("Vani: we recommend Plus for regular use. Compare current plans in the Vani settings tab."), 600);
      document.documentElement.appendChild(root);
      applyMenuPrefs();
      bar = root.querySelector("#zs-bar");
      dot = root.querySelector("#zs-dot");
      brandEl = root.querySelector("#zs-brand");
      applyMenuPrefs();
      stateEl = root.querySelector("#zs-state");
      const startupInfo=root.querySelector('#ms-startup-info');
      stateEl.addEventListener('click',()=>{if(A.starting){startupInfo.hidden=!startupInfo.hidden;stateEl.setAttribute('aria-expanded',String(!startupInfo.hidden));}});
      stateEl.addEventListener('keydown',e=>{if(A.starting&&['Enter',' '].includes(e.key)){e.preventDefault();startupInfo.hidden=!startupInfo.hidden;stateEl.setAttribute('aria-expanded',String(!startupInfo.hidden));}});
      root.querySelector('#ms-startup-close').onclick=()=>{startupInfo.hidden=true;stateEl.setAttribute('aria-expanded','false');stateEl.focus();};
      root.querySelector('#ms-blender-open').onclick=()=>void openBlenderWorkspace(root.querySelector('#ms-blender-open'));
      setInterval(()=>{if(A.starting)renderBar();},1000);
      actionBtn = root.querySelector("#zs-action");
      chatOnlyBtn = root.querySelector("#zs-chat-only");
      stopBtn = root.querySelector("#zs-stop");
      switchBtn = root.querySelector("#zs-switch");
      supportBtn = root.querySelector("#zs-support");
      bridgeBtn = root.querySelector("#zs-bridge");
      memBtn = root.querySelector("#zs-mem");
      if (memBtn) { ensureMem(); memBtn.addEventListener("click", (e) => { e.stopPropagation(); const m = ensureMem(); if (m && memPanel) { memPanel.toggle(); paintMem(); } }); }
      bridgeRunBtn = root.querySelector("#zs-bridge-run");
      modelChip = root.querySelector("#zs-model");
      discordEl = root.querySelector("#zs-discord");
      const swName = root.querySelector("#zs-switch-name");
      if (swName) swName.textContent = P.displayName || P.id;
      menuEl = root.querySelector("#zs-menu");
      bar.classList.add(`zs-prov-${P.id}`); // lets CSS tune per-site (e.g. font)
      // Provider hook on <html> so overlay.css can tune site-specific CHIP layout
      // (not just the bar). Meta's turn root is full-width with the reply in a
      // nested centered column, so whole-turn chips (result/sys) need re-centering.
      document.documentElement.classList.add(`zs-site-${P.id}`);

      actionBtn.addEventListener("click", onActionClick);
      chatOnlyBtn.addEventListener("click", () => startSession({chatOnly:true}));
      softwareBtn = root.querySelector("#zs-software");
      if (softwareBtn) softwareBtn.addEventListener("click", () => startSession({chatOnly:true, software:true}));
      stopBtn.addEventListener("click", stopLoop);
      buildMenu();
      // Both bar controls open the same panel; the heart lands on the Support
      // section (last), the model button opens at the top with Switch AI.
      let updateNotice=null;
      const toggleMenu = (toSupport, forceTab) => {
        updateNotice?.closed();
        menuEl.hidden = !menuEl.hidden;
        if (!menuEl.hidden) {
          if(runMonitor)runMonitor.panel.hidden=true;
          // Rebuild on every open, not just once at page load: the initial
          // buildMenu() call runs before the bridge status (server list/health)
          // has arrived, so the very first render always shows an empty/stale
          // MCP servers section otherwise - nothing ever refreshed it after.
          menuTab = TAB_ALIAS[menuPrefs.defaultTab] || menuPrefs.defaultTab || "home";
          if (toSupport) menuTab = "help";
          if (forceTab) menuTab = forceTab;
          buildMenu();
          syncMenuPrompt();
          refreshElevenLabsStatus(true);
          requestAnimationFrame(()=>updateNotice?.opened());
          // On a FRESH open, menuEl has no max-height yet - that's only applied by
          // placeBar()'s positioning pass, which runs on the next rAF tick (it's a
          // separate loop, not synchronous with this click). Without it the panel
          // has no overflow yet, so scrollHeight === clientHeight and setting
          // scrollTop here is a no-op - the "jump to Support" silently failed on
          // the very first open (reported live on Arena). Deferring one frame lets
          // placeBar's already-queued tick clip the box first, so there's real
          // scroll room by the time we set scrollTop.
          requestAnimationFrame(() => {
            if (menuEl.hidden) return;
            const pane = menuEl.querySelector("#zs-pane"); if (!pane) return;
            const sup = toSupport && [...pane.querySelectorAll(":scope > section")].find((x) => !x.hidden && /^Free Support/.test(labelOf(x)));
            if (sup) { sup.classList.remove("collapsed"); (accOpen.help || (accOpen.help = new Set())).add("Free Support"); pane.scrollTop = sup.offsetTop - 8; } else pane.scrollTop = 0;
          });
        }
      };
      updateNotice=MSUpdatePanel.notice({root,menu:menuEl,storage:chrome.storage.local,version:EXT_VERSION,send:msg=>bg({type:'ms_update_admin',...msg}),openSettings:()=>{if(menuEl.hidden)toggleMenu(false);}});
      switchBtn.addEventListener("click", (e) => { e.stopPropagation(); toggleMenu(false); });
      root.querySelector("#ms-new-idea").addEventListener("click", () => runStudioAction("idea"));
      supportBtn?.addEventListener("click", (e) => { e.stopPropagation(); toggleMenu(true); applyMenuTab("tools"); });
      if (bridgeBtn) bridgeBtn.addEventListener("click", (e) => { e.stopPropagation(); onBridgeClick(); });
      if (bridgeRunBtn) bridgeRunBtn.addEventListener("click", (e) => { e.stopPropagation(); onBridgeRunClick(); });
      if (modelChip) {
        modelChip.addEventListener("click", (e) => { e.stopPropagation(); toggleMenu(false, "notion"); });
        onNotionUsageChange = refreshModelChip;
        refreshModelChip();
        setInterval(notionPassiveTick, 15000);
        setTimeout(notionPassiveTick, 2500);
      }
      openMenuFn = (toSupport) => { if (menuEl.hidden) toggleMenu(toSupport); };
      // The "Running" list is a dropdown: it closes on an outside click or Escape.
      // The log view stays put so you can keep it open while the agent works.
      document.addEventListener("click", (e) => {
        if (notionProbing) return;
        if (termPanel && termPanel.isOpen() && termPanel.currentTab() === "running") {
          // Is the click inside the panel / its icons? Use the event's composed path
          // (fixed at dispatch time) AND the target's own ancestry: the Running list
          // re-renders itself, and a click on a node that was swapped out a moment
          // earlier has a DETACHED target. The old check read that as "outside" and
          // closed the panel under the user's finger.
          const path = typeof e.composedPath === "function" ? e.composedPath() : [];
          const hit = (n) => n && n.nodeType === 1 && (n.id === "zs-term" || n.id === "zs-bridge" || n.id === "zs-bridge-run" || n.id === "zs-bridge-split");
          const inside = path.some(hit) ||
            (e.target && e.target.closest && !!e.target.closest("#zs-term,#zs-bridge,#zs-bridge-run,#zs-bridge-split")) ||
            (e.target && e.target.nodeType === 1 && !e.target.isConnected);
          if (!inside) { termPanel.close(); bridgeIdlePaint(); }
        }
      }, true);
      document.addEventListener("click", (e) => {
        if (!memPanel || !memPanel.isOpen()) return;
        const path = typeof e.composedPath === "function" ? e.composedPath() : [];
        const inside = path.some((n) => n && n.nodeType === 1 && (n.id === "zs-mem-panel" || n.id === "zs-mem")) ||
          (e.target && e.target.closest && !!e.target.closest("#zs-mem-panel,#zs-mem")) ||
          (e.target && e.target.nodeType === 1 && !e.target.isConnected);
        if (!inside) memPanel.close();
      }, true);
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && memPanel && memPanel.isOpen()) { memPanel.close(); return; }
        if (e.key === "Escape" && termPanel && termPanel.isOpen()) { termPanel.close(); bridgeIdlePaint(); }
        else if (e.key === "Escape" && menuEl && !menuEl.hidden && !notionProbing) menuEl.hidden = true;
      }, true);
      document.addEventListener("click", (e) => {
        if (menuEl.hidden || notionProbing) return;
        if (!menuEl.contains(e.target) && !switchBtn.contains(e.target) && !(supportBtn && supportBtn.contains(e.target)) && !(modelChip && modelChip.contains(e.target)))
          menuEl.hidden = true;
      }, true);

      applyTheme();
      setInterval(applyTheme, 2000); // follow the host page toggling its theme
      renderBar();
      placeBar(); // start the per-frame anchoring loop
    }

    // The primary button does different things depending on the current state
    // (set by renderBar via actionBtn.dataset.kind).
    function onActionClick() {
      const kind = actionBtn.dataset.kind;
      if(kind==="resume-response"){
        if((P.responseError&&P.responseError())||MSStudio.nativeResponseError(P.lastAssistant())){toast("Use the site's Retry first. Resume after its error state clears.");return;}
        if(A.running||A.starting||P.editorText()?.trim()){toast("Wait for the current action and preserve your draft before resuming.");return;}
        const failure=A.responseFailure;if(!failure||failure.chat!==P.conversationKey())return;
        A.responseFailure=null;A.userStopped=false;A.lastSendOk=true;A.sendUnconfirmed=false;agentLoop(failure.base,{preserveErrors:true});renderBar();return;
      }
      if (kind === "start" || kind === "start-degraded") startSession();
      else if (kind === "open-provider" && P.openAIChat) {
        P.openAIChat().then((ok) => {
          if (!ok) toast("Open Notion AI/Ask AI, then Multi-Script will attach automatically.");
          renderBar();
        });
      }
    }

    // ── Custom prompt (persisted) ───────────────────────────────────────────
    // The user's extra instructions, persisted in chrome.storage.local and
    // appended UNDER the system prompt at session start. Cached here so
    // startSession can read it synchronously.
    let elevenLabsState = { configured:false, loading:true };
    async function refreshElevenLabsStatus(rebuild=true) {
      const r = await bg({ type:"elevenlabs_status" });
      elevenLabsState = r && r.ok && r.status ? { ...r.status, loading:false } : { configured:false, loading:false, error:(r && r.error) || "Bridge unavailable" };
      if (rebuild && menuEl && !menuEl.hidden) buildMenu();
      return elevenLabsState;
    }
    let customPrompt = "";
    let usageMode = "balanced";
    let skillDepth = "full";
    const DEFAULT_PROVIDER_BEHAVIOR = { promptSkills: "automatic", loops: "balanced", creativeSurface: "auto", creativeStyle: "auto", assetWorkflow: "auto", creativeFinish: "premium" };
    const PROVIDER_BEHAVIOR_ENUMS = { promptSkills:["off","suggest","automatic"], loops:["fast","balanced","rigorous"], creativeSurface:["auto","engine","figma","canvas"], creativeStyle:["auto","anime","stylized-fantasy","low-poly","realistic-pbr","cyberpunk","dark-gothic","cozy-handpainted","retro-pixel","minimal-modern","sci-fi-hard-surface","toy-cartoon","luxury-gold"], assetWorkflow:["auto","external-first","studio-first","hybrid"], creativeFinish:["production","premium","cinematic"] };
    function sanitizeProviderBehavior(raw) { const src=raw&&typeof raw==="object"?raw:{}; const out={...DEFAULT_PROVIDER_BEHAVIOR}; for(const [k,a] of Object.entries(PROVIDER_BEHAVIOR_ENUMS)) if(a.includes(src[k])) out[k]=src[k]; return out; }
    function sanitizeProviderBehaviorMap(raw) { const out={}; if(raw&&typeof raw==="object") for(const [id,v] of Object.entries(raw)) if(/^[a-z0-9_-]{1,40}$/i.test(id)) out[id]=sanitizeProviderBehavior(v); return out; }
    let providerBehaviorMap = {};
    function getProviderBehavior() { return sanitizeProviderBehavior(providerBehaviorMap[P.id]); }
    function setProviderBehavior(patch) {
      providerBehaviorMap[P.id] = { ...getProviderBehavior(), ...patch };
      try { chrome.storage.local.set({ msProviderBehavior: providerBehaviorMap }); } catch {}
    }
    try { chrome.storage.local.get("msProviderBehavior", (r) => { if (r && r.msProviderBehavior) { providerBehaviorMap = sanitizeProviderBehaviorMap(r.msProviderBehavior); if (menuEl && !menuEl.hidden) buildMenu(); } }); } catch {}
    try { chrome.storage.local.get("zsUsageOptimizer", (r) => { if (r && ["off","balanced","compact"].includes(r.zsUsageOptimizer)) { usageMode = r.zsUsageOptimizer; if (menuEl && !menuEl.hidden) buildMenu(); } }); } catch {}
    function getUsageMode() { return usageMode; }
    try { chrome.storage.local.get("zsSkillToolDepth", (r) => { if (r && ["focused","full","maximum"].includes(r.zsSkillToolDepth)) { skillDepth = r.zsSkillToolDepth; if (menuEl && !menuEl.hidden) buildMenu(); } }); } catch {}
    function getSkillDepth() { return skillDepth; }
    const SETTINGS_BACKUP_SCHEMA = 1;
    function buildSettingsBackup() {
      return { product:"Multi-Script", schema:SETTINGS_BACKUP_SCHEMA, exportedBy:EXT_VERSION, appearance:sanitizeMenuPrefs(menuPrefs), providerBehavior:sanitizeProviderBehaviorMap(providerBehaviorMap), usageOptimizer:usageMode, specialistDepth:skillDepth, customInstructions:customPrompt.slice(0,12000), promptEnhancer:ZSEnhance.sanitize(enhanceSettings), executionEffort, critic:MSStudio.sanitizeCritic(criticSettings), pacing:ZSPace.sanitize(paceSettings), errorRecovery:ZSResilience.sanitize(resilienceSettings), verification:ZSVerify.sanitize(verificationSettings), limits:ZS.limits.get(), autonomy:autonomyLevel, starterProfile:{provider:P.id,id:P.getAutoRoutingProfile?P.getAutoRoutingProfile():""}, notionPreferredModel:P.id==="notion"&&P.getAutoRoutingProfile?P.getAutoRoutingProfile():"", exclusions:["API keys","integration credentials","MCP launch commands","runtime state"] };
    }
    function applySettingsBackup(raw) {
      if(!raw||raw.product!=="Multi-Script"||raw.schema!==SETTINGS_BACKUP_SCHEMA) throw new Error("Unsupported Multi-Script settings backup");
      menuPrefs=sanitizeMenuPrefs(raw.appearance);
      providerBehaviorMap=sanitizeProviderBehaviorMap(raw.providerBehavior);
      usageMode=["off","balanced","compact"].includes(raw.usageOptimizer)?raw.usageOptimizer:"balanced";
      skillDepth=["focused","full","maximum"].includes(raw.specialistDepth)?raw.specialistDepth:"full";
      customPrompt=typeof raw.customInstructions==="string"?raw.customInstructions.slice(0,12000):"";
      if(raw.promptEnhancer) enhanceSettings=ZSEnhance.sanitize(raw.promptEnhancer);
      if(raw.executionEffort) executionEffort=sanitizeExecutionEffort(raw.executionEffort);
      if(raw.critic) criticSettings=MSStudio.sanitizeCritic(raw.critic);
      // Pacing / recovery / autonomy are optional in a backup (older exports do
      // not carry them) - absent means "keep what is already configured".
      if(raw.pacing) paceSettings=ZSPace.sanitize(raw.pacing);
      if(raw.errorRecovery) resilienceSettings=ZSResilience.sanitize(raw.errorRecovery);
      if(raw.verification) verificationSettings=ZSVerify.sanitize(raw.verification);
      if(raw.limits) ZS.limits.set(raw.limits);
      if(raw.autonomy) setAutonomyLevel(raw.autonomy);
      if(P.setAutoRoutingProfile){const id=raw.starterProfile&&raw.starterProfile.provider===P.id?raw.starterProfile.id:raw.notionPreferredModel;P.setAutoRoutingProfile(typeof id==="string"?id:"");}
      try{chrome.storage.local.set({msSettingsSchemaVersion:SETTINGS_BACKUP_SCHEMA,msMenuPreferences:menuPrefs,msProviderBehavior:providerBehaviorMap,zsUsageOptimizer:usageMode,zsSkillToolDepth:skillDepth,zsCustomPrompt:customPrompt,msEnhanceSettings:enhanceSettings,msExecutionEffort:executionEffort,msCriticSettings:criticSettings,msPacingSettings:paceSettings,msResilienceSettings:resilienceSettings,msVerificationSettings:verificationSettings,zsAutonomyLevel:autonomyLevel});}catch{}
      applyMenuPrefs();
      return true;
    }
    try {
      chrome.storage.local.get("zsCustomPrompt", (r) => {
        if (r && typeof r.zsCustomPrompt === "string") {
          customPrompt = r.zsCustomPrompt;
          syncMenuPrompt();
        }
      });
    } catch {}
    function getCustomPrompt() { return customPrompt; }
    // Reflect the saved value back into the menu textarea (unless being edited).
    function syncMenuPrompt() {
      const ta = root && root.querySelector("#zs-set-text");
      if (ta && document.activeElement !== ta) ta.value = customPrompt;
    }

    // ── Custom MCP servers (addons) ─────────────────────────────────────────
    // User-added MCP servers shown at the very bottom of the menu. These are
    // ADDONS: the Roblox server stays primary and is never in this list. Each
    // entry is { id, name, command } - `command` is the raw string the user
    // typed (split into command+args when sent to the bridge). The bridge writes
    // them to config.json and restarts to load them; this local list only drives
    // the menu UI and is kept in sync with the bridge's server health.
    let customMcpServers = [];
    try {
      chrome.storage.local.get("zsCustomMcpServers", (r) => {
        if (r && Array.isArray(r.zsCustomMcpServers)) {
          customMcpServers = r.zsCustomMcpServers;
          if (!menuEl.hidden) buildMenu();
        }
      });
    } catch {}
    function getCustomMcpServers() { return customMcpServers; }
    function saveCustomMcpServers() {
      try { chrome.storage.local.set({ zsCustomMcpServers: customMcpServers }); } catch {}
    }
    // The bridge (config.json + live health) is the SOURCE OF TRUTH for which
    // addon servers actually exist - chrome.storage.local is just a display-name
    // cache, and the two CAN drift (e.g. storage cleared, or config.json edited
    // by hand). Rendering from the bridge's live list means an addon never
    // "disappears" from the menu while still running - and self-heals the local
    // cache the moment we see a server it didn't know about.
    function mergedMcpServers() {
      const live = ((A.bridge && A.bridge.servers) || []).filter((sv) => sv.id !== "roblox");
      const byId = new Map(customMcpServers.map((s) => [s.id, s]));
      const merged = live.map((sv) => {
        const cached = byId.get(sv.id);
        return {
          id: sv.id, name: (cached && cached.name) || sv.id, command: cached && cached.command,
          alive: sv.alive, tools: sv.tools,
        };
      });
      // Self-heal: cache didn't know about a server the bridge actually has.
      let healed = false;
      for (const sv of live) {
        if (!byId.has(sv.id)) { customMcpServers.push({ id: sv.id, name: sv.id }); healed = true; }
      }
      if (healed) saveCustomMcpServers();
      // A server we just added/removed but the bridge hasn't reported back on
      // yet (mid-restart) - still show it, health unknown, so it doesn't blink
      // out of the list during the few seconds the bridge is restarting.
      for (const s of customMcpServers) {
        if (!merged.some((m) => m.id === s.id)) merged.push({ ...s, alive: undefined, tools: undefined });
      }
      return merged;
    }
    // Derive a config-safe server id from a display name (roblox is reserved).
    function mcpSlug(name) {
      let s = String(name || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
      if (!s || BUILTIN_SERVERS.has(s)) s = `addon-${s || "server"}`;
      let id = s, n = 2;
      while (customMcpServers.some((x) => x.id === id)) id = `${s}-${n++}`;
      return id;
    }
    // Split a raw "command with args" string into command + args (shell-lite:
    // whitespace-separated, honouring "double" and 'single' quotes).
    function splitCommand(raw) {
      const parts = String(raw || "").match(/"[^"]*"|'[^']*'|\S+/g) || [];
      const clean = parts.map((p) => p.replace(/^["']|["']$/g, ""));
      return { command: clean[0] || "", args: clean.slice(1) };
    }
    // Wait for the bridge to come back after its restart (config reload). Resolves
    // true once reconnected (optionally once `id` shows up in server health).
    async function waitForBridgeBack(id, timeoutMs = 15000) {
      const t0 = Date.now();
      // Give the bridge a moment to actually drop before we start polling, so we
      // don't instantly match the pre-restart "connected" state.
      await new Promise((r) => setTimeout(r, 1200));
      while (Date.now() - t0 < timeoutMs) {
        const s = await bg({ type: "status" });
        if (s && s.connected) {
          if (!id || (Array.isArray(s.servers) && s.servers.some((x) => x.id === id))) return true;
        }
        await new Promise((r) => setTimeout(r, 700));
      }
      return false;
    }

    let menuTab = "home";
    const BUILTIN_SERVERS = new Set(["roblox", "unity", "godot"]);

    // ── The "more" menu (⋯) ─────────────────────────────────────────────────
    // One popover holding every secondary control: other AI sites, the custom
    // prompt, and help. Opens above the bar.

    // ── Prompt enhancer panel ────────────────────────────────────────────
    // Every control re-renders the live preview from the ACTUAL enhancer, so the
    // user always sees the real output for the strength they picked - never a
    // marketing approximation of it.

    // ── Notion: chip, passive refresh, model/effort + trial controls ─────────
    function refreshModelChip() {
      if (!modelChip || !NU || !notionUsage) return;
      const label = NU.chipText(notionUsage) || (P.currentModelLabel && P.currentModelLabel()) || "Models";
      const el = modelChip.querySelector("#zs-model-text");
      if (el && el.textContent !== label) el.textContent = label;
      const est = NU.estimate(notionUsage);
      modelChip.title = [est.summary].concat(est.detail).join("\n") + "\nRough estimate from your own counts and readings. Click for details.";
    }
    let notionTickN = 0;
    function notionPassiveTick() {
      if (!NU || !notionUsage || notionProbing || document.hidden) return;
      try {
        const label = P.currentModelLabel ? P.currentModelLabel() : "";
        if (label && !/^models?$/i.test(label) && label !== notionUsage.selected.model) {
          const hit = NU.findModel(notionUsage.models, label, { enabledOnly: false });
          notionUsage = NU.sanitize({ ...notionUsage, selected: { model: hit ? hit.name : label, effort: notionUsage.selected.effort } });
          saveNotionUsage();
        }
        // Credits / trial days only when Notion actually shows them (~every 5 min).
        if (notionTickN++ % 20 === 0 && P.scanPageUsage) {
          const scan = P.scanPageUsage();
          if (scan && (scan.creditsRemaining != null || scan.daysLeft != null || scan.trialEndsAt != null)) saveNotionUsage(NU.applyScan(notionUsage, scan));
        }
      } catch {}
      refreshModelChip();
    }
    function notionTabMarkup() {
      if (P.id !== "notion" || !NU || !notionUsage) return "";
      const nesc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
      const u = NU.sanitize(notionUsage), est = NU.estimate(u), sel = u.selected || {};
      const selModel = u.models.find((m) => m.name === sel.model) || null;
      const effortList = selModel && selModel.efforts.length ? selModel.efforts : (u.models.find((m) => m.efforts.length) || { efforts: [] }).efforts;
      const label = (e) => ({ xhigh: "X-High" })[e] || e[0].toUpperCase() + e.slice(1);
      const find = (q) => NU.findModel(u.models, q, { enabledOnly: false });
      const flag = (q, name) => { if (!u.models.length) return ""; const m = find(q); return `<span class="zs-nm-flag ${m && m.enabled ? "ok" : "no"}">${name} ${m ? (m.enabled ? "enabled" : "locked") : "not listed"}</span>`; };
      const rows = u.models.map((m) => `<button class="zs-behavior-opt zs-nm-model${m.name === sel.model ? " active" : ""}" data-nm-model="${nesc(m.name)}" ${m.enabled ? "" : "disabled"}><b>${nesc(m.name)}${m.badge ? ` <i>${nesc(m.badge)}</i>` : ""}</b><span>${m.enabled ? nesc(m.vendor || "enabled in this workspace") : "not enabled for this workspace/plan"}</span></button>`).join("");
      const days = est.daysLeft !== null ? Math.ceil(est.daysLeft) : "";
      const cred = est.creditsLeft !== null ? Math.round(est.creditsLeft) : "";
      return `
        <section class="zs-menu-sec zs-notion-sec" data-zs-tab="notion">
          <div class="zs-sec-label"><span>Trial &amp; credits</span><span class="zs-provider-badge">rough estimate</span></div>
          <div class="zs-nu-summary" id="zs-nu-summary">${nesc(est.summary)}</div>
          ${est.detail.map((d) => `<div class="zs-menu-note">${nesc(d)}</div>`).join("")}
          <div class="zs-nu-grid">
            <label>Trial days left<input id="zs-nu-days" type="number" min="0" max="400" step="1" inputmode="numeric" value="${days}" placeholder="e.g. 9"></label>
            <label>Credits left<input id="zs-nu-credits" type="number" min="0" step="1" inputmode="numeric" value="${cred}" placeholder="from Notion"></label>
          </div>
          <div class="zs-menu-actions"><button id="zs-nu-save" class="zs-mini-action">Save</button><button id="zs-nu-scan" class="zs-mini-action">Read from page</button><button id="zs-nu-reset" class="zs-mini-action">Reset estimate</button></div>
          <div class="zs-menu-note">Notion does not publish a per-model price or an API for trial allowance. This counts the prompts sent from this browser and learns the credit cost per prompt each time you enter a new “credits left” reading — enter it twice and the number tightens. It is a guide, not Notion's billing.</div>
          <div id="zs-nu-status" class="zs-menu-note"></div>
        </section>
        <section class="zs-menu-sec zs-notion-sec" data-zs-tab="notion">
          <div class="zs-sec-label"><span>Models in agent mode</span><span class="zs-provider-badge">${u.modelsAt ? "detected" : "not detected yet"}</span></div>
          <div class="zs-nm-flags">${flag("opus 5.5", "Opus 5.5")}${flag("sonnet 5.5", "Sonnet 5.5")}</div>
          <div class="zs-menu-note">Notion turns models on per workspace and plan. Detect opens Notion's own model menu once, reads it and closes it again — it changes nothing. Selecting a model clicks that row in Notion's menu and then checks the label.</div>
          ${rows ? `<div class="zs-choice-stack">${rows}</div>` : ""}
          ${effortList.length ? `<div class="zs-sec-label zs-sub"><span>Effort</span></div><div class="zs-nm-efforts">${effortList.map((e) => `<button class="zs-mini-action zs-nm-effort${sel.effort === e ? " active" : ""}" data-nm-effort="${e}">${label(e)}</button>`).join("")}</div>` : (u.models.length ? `<div class="zs-menu-note">Notion's picker shows no effort levels for these models.</div>` : "")}
          <div class="zs-menu-actions"><button id="zs-nm-detect" class="zs-mini-action">${u.modelsAt ? "Re-detect models" : "Detect enabled models"}</button></div>
          <div id="zs-nm-status" class="zs-menu-note">${u.modelsAt ? `Last detected ${new Date(u.modelsAt).toLocaleString()}.` : "Open a Notion AI chat first so the model button is visible."}</div>
        </section>`;
    }

    async function openBlenderWorkspace(button,status){
      if(button?.disabled)return; if(button)button.disabled=true;
      if(status)status.textContent='Opening Blender Workspace…';
      try{const result=await bg({type:'ms_blender_workspace_open'});const message=result?.ok?'Opened in its own tab. Create or open a project, then start the Blender agent.':String(result?.error||'Start the bridge first.');if(status)status.textContent=message;else if(!result?.ok)toast(message);}
      finally{if(button)button.disabled=false;}
    }
    // Engines tab → Bridge: the same host calls the terminal icon uses.
    function bindBridgeSection() {
      const q = (sel) => menuEl.querySelector(sel);
      const say = (t) => { const el = q("#zs-br-status"); if (el) el.textContent = t; };
      const call = (type, extra) => new Promise((res) => { try { chrome.runtime.sendMessage({ type, ...(extra || {}) }, (r) => res(chrome.runtime.lastError ? { ok: false, error: chrome.runtime.lastError.message } : (r || { ok: false }))); } catch (e) { res({ ok: false, error: String(e) }); } });
      const companionToggles=[...menuEl.querySelectorAll('.ms-blender-companion')];
      const companionNote=q('#ms-blender-companion-note');
      if(companionToggles.length){
        let saved=[];
        const paint=()=>companionToggles.forEach(el=>{el.checked=saved.includes(el.value);});
        call('ms_blender_companion',{op:'status'}).then(r=>{if(r?.ok){saved=r.companion?.engines||[];paint();companionNote.textContent='Saved on this PC. The selected Blender project starts before the next game-engine session sends its instructions.';}else companionNote.textContent=r?.error||'Start the updated bridge to configure the Blender companion.';});
        companionToggles.forEach(el=>el.addEventListener('change',async()=>{
          companionToggles.forEach(x=>x.disabled=true);
          try{const r=await call('ms_blender_companion',{op:'companion',payload:{engines:companionToggles.filter(x=>x.checked).map(x=>x.value)}});if(!r?.ok)throw Error(r?.error||'Preference was not saved.');saved=r.companion.engines;companionNote.textContent='Saved. Use a fresh game-engine chat to apply this choice.';}
          catch(e){companionNote.textContent=e.message;}
          finally{paint();companionToggles.forEach(x=>x.disabled=false);}
        }));
      }
      const blenderWindow=q('#ms-blender-workspace-open');
      blenderWindow?.addEventListener('click',()=>void openBlenderWorkspace(blenderWindow,q('#ms-blender-workspace-status')));
      const blockbenchStatus=q('#ms-blockbench-status'),blockbenchPrepare=q('#ms-blockbench-prepare'),blockbenchRender=q('#ms-blockbench-render');
      const vaultStatus=q('#ms-vault-status'),vaultPath=q('#ms-vault-path'),vaultImport=q('#ms-vault-import-path'),vaultConnect=q('#ms-vault-connect'),vaultAdd=q('#ms-vault-import');
      if(vaultStatus){
        const paint=state=>{vaultStatus.textContent=!state?.ok?(state?.error||'Vault status unavailable.'):state.path?'Imported '+state.sourceName+' ('+Math.round(state.bytes/1024)+' KB). Stored outside extension code.':state.available?'Vault connected to the bridge: '+state.vault+'. Existing notes and imported files are preserved.':state.configured?'Vault folder unavailable. Reconnect the existing folder.':'Run Setup or connect the default vault below.';if(state?.vault&&vaultPath&&!vaultPath.value)vaultPath.value=state.vault;};
        void bg({type:'ms_obsidian_admin',op:'status'}).then(paint).catch(error=>paint({ok:false,error:String(error.message||error)}));
        for(const [button,op,input] of [[vaultConnect,'setup',vaultPath],[vaultAdd,'import',vaultImport]])button?.addEventListener('click',async event=>{
          if(!event.isTrusted)return;vaultConnect.disabled=true;vaultAdd.disabled=true;vaultStatus.textContent=op==='setup'?'Connecting the vault and seeding missing library files…':'Importing the original file without executing its contents…';
          try{paint(await bg({type:'ms_obsidian_admin',op,payload:{path:input?.value?.trim()||''}}));}
          catch(error){paint({ok:false,error:String(error.message||error)});}
          finally{vaultConnect.disabled=false;vaultAdd.disabled=false;}
        });
      }
      if(blockbenchStatus){
        const paint=state=>{blockbenchStatus.textContent=!state?.ok?(state?.error||'Blockbench status unavailable.'):state.connected?'Headless Blockbench connected · '+(state.nativeTools?.length||0)+' native tools · '+(state.renderPrepared?'render worker prepared':'render worker optional')+'. Models: '+state.workspace:state.prepared?'Runtime prepared. Connect it with Prepare Blockbench to advertise its native tools.':'Prepare when needed. No Blockbench editor window is required; models stay in a dedicated workspace.';};
        void bg({type:'ms_blockbench_admin',op:'status'}).then(paint).catch(error=>paint({ok:false,error:String(error.message||error)}));
        for(const [button,render] of [[blockbenchPrepare,false],[blockbenchRender,true]])button?.addEventListener('click',async event=>{
          if(!event.isTrusted)return;
          blockbenchPrepare.disabled=true;blockbenchRender.disabled=true;blockbenchStatus.textContent='Preparing verified Blockbench dependencies and connecting the file workspace…';
          try{paint(await bg({type:'ms_blockbench_admin',op:'prepare',render}));}
          catch(error){paint({ok:false,error:String(error.message||error)});}
          finally{blockbenchPrepare.disabled=false;blockbenchRender.disabled=false;}
        });
      }
      const open = q("#zs-br-open");
      if (open) open.addEventListener("click", () => { menuEl.hidden = true; const t = ensureTerm(); if (t) { t.openPanel("terminal"); bridgeIdlePaint(); } });
      for (const [id, type, doing] of [["#zs-br-start", "host_start", "Starting the bridge…"], ["#zs-br-restart", "host_restart", "Restarting the bridge…"], ["#zs-br-stop", "host_stop", "Stopping the bridge…"]]) {
        const b = q(id); if (!b) continue;
        b.addEventListener("click", async () => {
          say(doing); b.disabled = true;
          const r = await call(type);
          b.disabled = false;
          if (r.ok) say(type === "host_stop" ? "Stopped. Click Start to run it again." : "Running — the bar will turn green in a moment.");
          else if (r.code === "host_missing") say("One-time setup needed: run Setup.bat (Windows), MacOS_Setup.command (macOS) or bash Setup.sh (Linux), then reload this tab. Or run Start.bat / bash Start.sh to run the bridge right now.");
          else say(`Could not ${type.replace("host_", "")}: ${String(r.error || r.code || "unknown").slice(0, 120)}`);
        });
      }
      const auto = q("#zs-br-auto");
      if (auto) {
        call("host_prefs").then((r) => { auto.checked = r.autoStart !== false; });
        auto.addEventListener("change", () => call("host_prefs", { set: true, autoStart: auto.checked }).then(() => say(auto.checked ? "Auto-start on." : "Auto-start off — use Start when you need the bridge.")));
      }
    }

    // 6.27.1: engine setup guides (Settings -> Engines -> Engine setup guides).
    // Expand/collapse, copy a plain-text checklist, and one-click fill of the
    // add-on form with the bundled launcher command (the Blender easy path).
    function bindEngineGuides() {
      if (!menuEl || typeof ZSExtras === "undefined" || !Array.isArray(ZSExtras.ENGINE_GUIDES)) return;
      const guides = new Map(ZSExtras.ENGINE_GUIDES.map((g) => [g.id, g]));
      menuEl.querySelectorAll("[data-guide-toggle]").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.preventDefault(); e.stopPropagation();
          const body = menuEl.querySelector(`[data-guide-id="${btn.dataset.guideToggle}"] .zs-guide-body`);
          if (!body) return;
          const open = body.hidden;
          body.hidden = !open;
          btn.setAttribute("aria-expanded", open ? "true" : "false");
          const caret = btn.querySelector(".zs-guide-caret"); if (caret) caret.textContent = open ? "▾" : "▸";
        });
      });
      menuEl.querySelectorAll("[data-guide-fill]").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.preventDefault(); e.stopPropagation();
          const g = guides.get(btn.dataset.guideFill);
          if (!g || !g.fill) return;
          const name = menuEl.querySelector("#zs-mcp-name"), url = menuEl.querySelector("#zs-mcp-url");
          if (name) name.value = g.fill.name;
          if (url) url.value = g.fill.command;
          const st = menuEl.querySelector("#zs-mcp-status");
          if (st) st.textContent = `${g.name}: bundled launcher filled in - press "Add addon", then "Restart MCP servers".`;
          if (name) { try { name.scrollIntoView({ block: "center", behavior: "smooth" }); name.focus({ preventScroll: true }); } catch {} }
          toast(`${g.name} launcher filled in below`);
        });
      });
      menuEl.querySelectorAll("[data-guide-copy]").forEach((btn) => {
        btn.addEventListener("click", async (e) => {
          e.preventDefault(); e.stopPropagation();
          const g = guides.get(btn.dataset.guideCopy);
          if (!g) return;
          const text = [
            `Multi-Script setup: ${g.name}`,
            `You need: ${g.needs.join("; ")}.`,
            ...g.steps.map((s, i) => `${i + 1}. ${s}`),
            `Verify: ${g.verify}`,
            `Tip: ${g.tip}`,
          ].join("\n");
          try { await navigator.clipboard.writeText(text); toast(`${g.name} checklist copied`); } catch { toast("Could not copy checklist"); }
        });
      });
    }
    // Per-engine on/off switches (Settings -> Engines -> Active engines). The bridge saves the
    // choice (runtime/engine-prefs.json) and enforces it; this only shows and changes it.
    function bindEngineToggles() {
      const q = (sel) => menuEl.querySelector(sel);
      const boxes = Array.from(menuEl.querySelectorAll(".ms-eng-toggle"));
      if (!boxes.length) return;
      const say = (t, bad) => { const el = q("#ms-eng-status"); if (el) { el.textContent = t; el.style.color = bad ? "#e8a0a0" : ""; } };
      const call = (type, extra) => new Promise((res) => { try { chrome.runtime.sendMessage({ type, ...(extra || {}) }, (r) => res(chrome.runtime.lastError ? { ok: false, error: chrome.runtime.lastError.message } : (r || { ok: false }))); } catch (e) { res({ ok: false, error: String(e) }); } });
      const paint = (r) => {
        const off = new Set(r.disabled || []);
        A.disabledEngines = off;
        const list = new Map((r.engineList || []).map((e) => [e.id, e]));
        for (const b of boxes) {
          const id = b.dataset.engine;
          b.checked = !off.has(id);
          const note = menuEl.querySelector(`[data-note="${id}"]`);
          const e = list.get(id);
          if (note) note.textContent = off.has(id) ? " · off" : (e ? (e.alive ? ` · running, ${e.tools} tools` : (e.configured ? " · on, server not running" : " · on (no server configured)")) : "");
        }
      };
      call("engine_prefs").then((r) => {
        paint(r);
        if (r.offline) say("Bridge offline - showing the saved choice. Changes apply once the bridge is running.", false);
      });
      for (const b of boxes) {
        b.addEventListener("change", async () => {
          const id = b.dataset.engine, on = b.checked;
          boxes.forEach((x) => { x.disabled = true; });
          say(`${on ? "Switching on" : "Switching off"} ${id}…`);
          const r = await call("set_engine", { engine: id, enabled: on });
          boxes.forEach((x) => { x.disabled = false; });
          if (!r || r.ok === false) { b.checked = !on; say(`Could not change ${id}: ${String((r && r.error) || "bridge offline - start it first").slice(0, 140)}`, true); return; }
          paint(r);
          A.toolsAt = 0;
          try { ui.updateStartGate(); } catch {}
          say(r.localOnly
            ? `${id[0].toUpperCase() + id.slice(1)} is ${on ? "ON" : "OFF"} and enforced by the extension. Update the bridge with Setup to also ${on ? "start" : "stop"} its background process.`
            : `${id[0].toUpperCase() + id.slice(1)} is now ${on ? "ON" : "OFF"} (saved).${on ? "" : " Its tools are hidden from the AI."}`);
          toast(`${id} ${on ? "enabled" : "disabled"}`);
        });
      }
    }

    function bindNotionTab() {
      if (P.id !== "notion" || !NU) return;
      const q = (sel) => menuEl.querySelector(sel);
      const say = (id, t) => { const el = q(id); if (el) el.textContent = t; };
      const lock = (on) => menuEl.querySelectorAll("#zs-nm-detect,.zs-nm-model,.zs-nm-effort").forEach((b) => { b.disabled = on || (b.classList.contains("zs-nm-model") && b.dataset.locked === "1"); });
      async function probe(fn) {
        if (notionProbing) return;
        notionProbing = true; lock(true);
        try { return await fn(); } catch (e) { say("#zs-nm-status", `Could not talk to Notion's picker: ${String((e && e.message) || e).slice(0, 100)}`); } finally { notionProbing = false; lock(false); }
      }
      const detect = q("#zs-nm-detect");
      if (detect) detect.addEventListener("click", () => probe(async () => {
        say("#zs-nm-status", "Opening Notion's model menu…");
        const r = await P.detectModels();
        if (!r.ok) { say("#zs-nm-status", r.error || "Could not read the model menu."); return; }
        let next = NU.setModels(notionUsage, r.models);
        if (r.selectedEffort) next = NU.sanitize({ ...next, selected: { ...next.selected, effort: r.selectedEffort } });
        saveNotionUsage(next); buildMenu();
        const on = r.models.filter((m) => m.enabled).length;
        say("#zs-nm-status", `Found ${r.models.length} model${r.models.length === 1 ? "" : "s"} (${on} enabled)${r.efforts.length ? ` · effort levels: ${r.efforts.join(", ")}` : ""}.`);
      }));
      const pick = async (arg) => {
        say("#zs-nm-status", "Selecting in Notion…");
        const r = await P.selectModel(arg);
        if (r.picked || r.effort) saveNotionUsage(NU.sanitize({ ...notionUsage, selected: { model: r.picked || notionUsage.selected.model, effort: r.effort || notionUsage.selected.effort } }));
        buildMenu();
        say("#zs-nm-status", r.ok ? `Selected ${r.picked || ""}${r.picked && r.effort ? " · " : ""}${r.effort || ""}. Notion now shows “${r.label || "?"}”${r.verified ? " ✓" : " (could not verify the label)"}.` : (r.error || "Notion did not accept that choice."));
        toast(r.ok ? "Notion model updated" : (r.error || "Model not changed").slice(0, 110));
      };
      menuEl.querySelectorAll(".zs-nm-model").forEach((b) => {
        const m = notionUsage.models.find((x) => x.name === b.dataset.nmModel);
        if (m && !m.enabled) b.dataset.locked = "1";
        b.addEventListener("click", () => probe(() => pick({ model: b.dataset.nmModel, effort: m && m.efforts.includes(notionUsage.selected.effort) ? notionUsage.selected.effort : "" })));
      });
      menuEl.querySelectorAll(".zs-nm-effort").forEach((b) => b.addEventListener("click", () => probe(() => pick({ effort: b.dataset.nmEffort }))));
      const save = q("#zs-nu-save");
      if (save) save.addEventListener("click", () => {
        const dEl = q("#zs-nu-days"), cEl = q("#zs-nu-credits");
        const shownCred = NU.estimate(notionUsage).creditsLeft, shownDays = NU.estimate(notionUsage).daysLeft;
        let next = notionUsage;
        const d = parseFloat(dEl.value), c = parseFloat(cEl.value);
        if (Number.isFinite(d) && (shownDays === null || Math.ceil(shownDays) !== d)) next = NU.setTrial(next, { daysLeft: d });
        if (dEl.value === "" && shownDays !== null) next = NU.sanitize({ ...next, trialEndsAt: null });
        if (Number.isFinite(c) && (shownCred === null || Math.round(shownCred) !== c)) next = NU.observeCredits(next, c);
        saveNotionUsage(next); buildMenu();
        say("#zs-nu-status", "Saved. The estimate refines every time you enter a new credits reading.");
      });
      const scan = q("#zs-nu-scan");
      if (scan) scan.addEventListener("click", () => {
        const r = P.scanPageUsage ? P.scanPageUsage() : {};
        const found = r && (r.creditsRemaining != null || r.daysLeft != null || r.trialEndsAt != null);
        if (found) { saveNotionUsage(NU.applyScan(notionUsage, r)); buildMenu(); }
        say("#zs-nu-status", found ? `Read from the page:${r.creditsRemaining != null ? ` ${r.creditsRemaining} credits` : ""}${r.daysLeft != null ? ` ${r.daysLeft} trial day(s)` : ""}${r.trialEndsAt ? " trial end date" : ""}.` : "Nothing about credits or the trial is visible on this page. Open Notion's Settings → Plans, or type the numbers in.");
      });
      const reset = q("#zs-nu-reset");
      if (reset) reset.addEventListener("click", () => { const keep = notionUsage; saveNotionUsage({ ...NU.defaults(), models: keep.models, modelsAt: keep.modelsAt, selected: keep.selected }); buildMenu(); say("#zs-nu-status", "Estimate reset."); });
    }

    function bindEnhancePanel(scope) {
      const MODES = ["off", "light", "balanced", "thorough"];
      const slider = scope.querySelector("#ms-enhance-mode");
      const label = scope.querySelector("#ms-enhance-mode-label");
      const desc = scope.querySelector("#ms-enhance-desc");
      const preview = scope.querySelector("#ms-enhance-preview");
      const sample = "make the door open when the player touches it";

      function renderPreview() {
        const s = getEnhanceSettings();
        const facts = { engines: A.engines && A.engines.length ? A.engines : [] };
        const r = ZSEnhance.enhance(sample, facts, s);
        if (preview) {
          preview.classList.toggle("zs-enhance-off", !r.enhanced);
          const out = preview.querySelector(".zs-enhance-out pre");
          if (out) out.textContent = r.enhanced ? r.text : sample + "\n\n(the enhancer is off - this is sent as typed)";
        }
        if (label) label.textContent = (ZSEnhance.LEVELS[s.mode] || ZSEnhance.LEVELS.off).label;
        if (desc) desc.textContent = ZSEnhance.describe(s);
      }

      if (slider) slider.addEventListener("input", () => {
        const mode = MODES[Math.max(0, Math.min(MODES.length - 1, parseInt(slider.value, 10) || 0))];
        setEnhanceSettings({ mode });
        renderPreview();
      });
      const prev = scope.querySelector("#ms-enhance-preview-toggle");
      if (prev) prev.addEventListener("change", () => { setEnhanceSettings({ preview: prev.checked }); renderPreview(); });
      const ef = scope.querySelector("#ms-enhance-engine-facts");
      if (ef) ef.addEventListener("change", () => { setEnhanceSettings({ injectEngineFacts: ef.checked }); renderPreview(); });
      const tf = scope.querySelector("#ms-enhance-tool-facts");
      if (tf) tf.addEventListener("change", () => { setEnhanceSettings({ injectToolFacts: tf.checked }); renderPreview(); });
      const ap = scope.querySelector("#ms-enhance-approach");
      if (ap) ap.addEventListener("change", () => { setEnhanceSettings({ injectApproach: ap.checked }); renderPreview(); });
      const ba = scope.querySelector("#ms-enhance-blender");
      if (ba) ba.addEventListener("change", () => { setEnhanceSettings({ blenderAssist: ba.checked }); renderPreview(); });
      const of = scope.querySelector("#ms-enhance-original-first");
      if (of) of.addEventListener("change", () => { setEnhanceSettings({ keepOriginalFirst: of.checked }); renderPreview(); });
      renderPreview();
    }

    // ── Media relay panel ────────────────────────────────────────────────
    // Drop, paste or pick a file; relay it; then paste the result into the
    // provider's own composer. The provider's attachImages() already knows how
    // THIS site accepts an image, so the relay never re-implements that.
    function bindMediaPanel(scope) {
      const drop = scope.querySelector("#ms-media-drop");
      const input = scope.querySelector("#ms-media-input");
      const status = scope.querySelector("#ms-media-status");
      const pasteBtn = scope.querySelector("#ms-media-paste");
      const clearBtn = scope.querySelector("#ms-media-clear");

      function setStatus(text, tone) {
        if (!status) return;
        status.textContent = text;
        status.classList.remove("ok", "warn");
        if (tone) status.classList.add(tone);
      }

      async function run(file) {
        if (!file) return;
        const rejection = ZSMediaRelay.rejectionFor(file);
        if (rejection) { setStatus(rejection, "warn"); toast("Media relay: " + rejection); return; }
        setStatus("Reading " + (file.name || "the file") + "…");
        try {
          const result = await ZSMediaRelay.relayFile(file, {
            onStage: (info) => {
              if (info.phase === "uploading") setStatus("Sending " + ZSMediaRelay.formatBytes(info.bytes) + " to the local bridge…");
              else if (info.phase === "converting") setStatus(info.kind === "video" ? "Extracting frames from the clip…" : "Preparing the paste…");
            },
          });
          setLastRelay(result);
          setStatus(ZSMediaRelay.describeOutcome(result), result.ok ? "ok" : "warn");
          if (pasteBtn) pasteBtn.disabled = !result.ok;
          // Paste immediately: the user dropped a file to SHOW the model, so the
          // extra click would be ceremony. The button remains for a re-paste.
          if (result.ok) await pasteIntoComposer(result);
        } catch (e) {
          const msg = String((e && e.message) || e);
          setLastRelay({ ok: false, error: msg, payloads: [] });
          setStatus(msg, "warn");
          if (pasteBtn) pasteBtn.disabled = true;
        }
      }

      async function pasteIntoComposer(result) {
        if (!result || !result.ok || !result.payloads.length) return false;
        const attach = P.attachImages;
        // Text-only assistant (or a site with no attach path): hand the model what
        // it CAN use - a text digest of every frame plus the relay manifest - on
        // the clipboard, ready to paste into the message.
        const textFallback = async () => {
          try {
            const digest = ZS.imageDigest ? await ZS.imageDigest(result.payloads) : "";
            const text = [result.manifest || "", digest].filter(Boolean).join("\n\n");
            if (text && navigator.clipboard && navigator.clipboard.writeText) {
              await navigator.clipboard.writeText(text);
              setStatus("This assistant cannot take the image, so a text description of the " + (result.kind === "video" ? "frames" : "photo") + " was copied - paste it into your message.", "ok");
              return true;
            }
          } catch {}
          setStatus("Relayed, but this assistant cannot take images and the text description could not be copied.", "warn");
          return false;
        };
        if (typeof attach !== "function") return textFallback();
        setStatus("Pasting into the composer…");
        try {
          const ok2 = await attach(result.payloads);
          if (!ok2) return textFallback();
          setStatus("Pasted - it is in the composer, add your message and send.", "ok");
          if (getMediaSettings().releaseAfterSend && result.item) ZSMediaRelay.release(result.item.id);
          return ok2;
        } catch (e) {
          setStatus("The paste failed: " + String((e && e.message) || e), "warn");
          return textFallback();
        }
      }

      if (drop) {
        drop.addEventListener("click", () => input && input.click());
        drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("hot"); });
        drop.addEventListener("dragleave", () => drop.classList.remove("hot"));
        drop.addEventListener("drop", (e) => {
          e.preventDefault();
          drop.classList.remove("hot");
          const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
          if (f) run(f);
        });
      }
      if (input) input.addEventListener("change", () => { const f = input.files && input.files[0]; if (f) run(f); input.value = ""; });
      if (pasteBtn) pasteBtn.addEventListener("click", () => pasteIntoComposer(getLastRelay()));
      if (clearBtn) clearBtn.addEventListener("click", async () => {
        const r = getLastRelay();
        if (r && r.item) await ZSMediaRelay.release(r.item.id);
        setLastRelay(null);
        if (pasteBtn) pasteBtn.disabled = true;
        setStatus("No media relayed yet. Drop a photo or a video below.");
      });
      const man = scope.querySelector("#ms-media-manifest");
      if (man) man.addEventListener("change", () => setMediaSettings({ sendManifest: man.checked }));
      const rel = scope.querySelector("#ms-media-release");
      if (rel) rel.addEventListener("change", () => setMediaSettings({ releaseAfterSend: rel.checked }));
    }

    // ── Surface vision panel ─────────────────────────────────────────────
    // Refresh asks the worker for tabs and the bridge for windows, then prints
    // the two counts. It never renders tab titles into the page (they can carry
    // private information); it reports how MUCH is visible, not WHAT. The model
    // gets the detail through the tool call when it actually needs it.
    function bindSurfacePanel(scope) {
      const tabCount = scope.querySelector("#ms-surface-tabs");
      const winCount = scope.querySelector("#ms-surface-windows");
      const status = scope.querySelector("#ms-surface-status");
      const refresh = scope.querySelector("#ms-surface-refresh");
      const planBtn = scope.querySelector("#ms-surface-plan");

      function setStatus(text, tone) {
        if (!status) return;
        status.textContent = text;
        status.classList.remove("ok", "warn");
        if (tone) status.classList.add(tone);
      }

      async function scan() {
        setStatus("Scanning…");
        try {
          const tabs = await bg({ type: "surface_list", include_icons: false });
          if (tabCount) tabCount.textContent = tabs && tabs.ok !== false ? String(tabs.count || 0) : "–";
        } catch (_) {
          if (tabCount) tabCount.textContent = "–";
        }
        try {
          const w = await bg({ type: "call_tool", name: "ms_app_list", arguments: {}, timeout: 15000 });
          let n = null;
          if (w && w.ok !== false && typeof w.text === "string") {
            try { n = (JSON.parse(w.text).count | 0); } catch (_) { n = null; }
          }
          if (winCount) winCount.textContent = n === null ? "–" : String(n);
          if (n === null) setStatus("Tabs listed. Desktop windows need the local bridge running.", "warn");
          else setStatus(`Visible now: ${tabCount ? tabCount.textContent : "?"} tab(s), ${n} app(s).`, "ok");
        } catch (_) {
          if (winCount) winCount.textContent = "–";
          setStatus("Tabs listed. Desktop windows need the local bridge running.", "warn");
        }
      }

      if (refresh) refresh.addEventListener("click", scan);
      if (planBtn) planBtn.addEventListener("click", async () => {
        setStatus("Fetching the setup plan…");
        const r = await bg({ type: "call_tool", name: "ms_app_setup_plan", arguments: {}, timeout: 15000 });
        if (!r || r.ok === false || typeof r.text !== "string") {
          setStatus("The bridge is offline, so no plan is available right now.", "warn");
          return;
        }
        let plan = null;
        try { plan = JSON.parse(r.text); } catch (_) { plan = null; }
        if (!plan || !Array.isArray(plan.steps)) { setStatus("The bridge returned an unreadable plan.", "warn"); return; }
        const pending = plan.steps.filter((s) => !s.satisfied);
        if (!pending.length) { setStatus(`Full desktop vision is already available on ${plan.platform}.`, "ok"); return; }
        // Show the exact commands, never run them. The user copies what they want.
        setStatus(`${pending.length} optional step(s) available on ${plan.platform}. Nothing is installed automatically:\n` +
          pending.map((s) => `• ${s.label}\n  ${s.command}`).join("\n"), "warn");
      });

      const tT = scope.querySelector("#ms-surface-tabs-toggle");
      if (tT) tT.addEventListener("change", () => setSurfaceSettings({ tabs: tT.checked }));
      const tW = scope.querySelector("#ms-surface-windows-toggle");
      if (tW) tW.addEventListener("change", () => setSurfaceSettings({ windows: tW.checked }));
      const tR = scope.querySelector("#ms-surface-read-toggle");
      if (tR) tR.addEventListener("change", () => setSurfaceSettings({ allowRead: tR.checked }));
      const tY = scope.querySelector("#ms-surface-type-toggle");
      if (tY) tY.addEventListener("change", () => setSurfaceSettings({ allowType: tY.checked }));
    }

    // ── Menu information architecture (6.25) ─────────────────────────────────
    // Sections are authored where their logic lives, then ROUTED here into nine
    // categories, ordered, grouped under small headings, and (in the long tabs)
    // folded into accordions so a category reads as a short list instead of a
    // wall. Routing by label keeps every section's own markup and event wiring
    // untouched. Accordion state survives the many buildMenu() rebuilds.
    const SETTINGS_GROUPS = [
      ["Workspace",["home","software","workshop","cowork","ideas","flight"]],
      ["Agent",["agent","tools"]], ["Connections",["engines","sites","notion","vani"]],
      ["Appearance",["look","bar","backstage"]], ["Support",["help"]]
    ];
    const SETTINGS_PAGES={home:["Overview","Connections, session status and your next step."],software:["Code & Build","Choose a workspace and build with the local tools."],workshop:["Skills","Discover, adapt and manage project workflows."],cowork:["Co-work","Follow-ups, shared tasks and clear ownership."],ideas:["Game ideas","Explore a direction that fits your project."],flight:["Code Flight","Take a break in Multi-Script’s offline arcade."],agent:["Agent","Effort, prompt behavior and execution controls."],tools:["Tools & media","Inspect capabilities and configure media tools."],engines:["Engines & bridge","Connect editors, inspect status and manage servers."],sites:["AI providers","Choose a provider and inspect compatibility."],notion:["Notion","Provider model and usage settings."],vani:["Vani","Provider compatibility and diagnostics."],look:["Appearance","One consistent look, with independent chatbar styling."],bar:["Chatbar","Position, density, appearance and visible actions."],backstage:["Backstage","Fazbear theme controls."],help:["Help & maintenance","Setup, diagnostics, backup and support."]};
    function pageHeading(tab,query="",count=0){
      const host=menuEl.querySelector("#ms-settings-page");if(!host)return;
      const e=MSStudio.escape,meta=SETTINGS_PAGES[tab]||SETTINGS_PAGES.home,group=SETTINGS_GROUPS.find(x=>x[1].includes(tab))?.[0]||"Settings";
      const groups=[...new Set([...menuEl.querySelectorAll(`#zs-pane > section[data-zs-tab="${tab}"]`)].map(x=>x.dataset.zsGroup).filter(Boolean))];
      host.innerHTML=query?`<span class="ms-page-path">Settings search</span><h2>${count} matching sections</h2><p>Results for “${e(query)}” across all categories.</p><button type="button" id="ms-clear-search" class="zs-mini-action">Clear search</button>`:`<span class="ms-page-path">${e(group)} / ${e(meta[0])}</span><h2>${e(meta[0])}</h2><p>${e(meta[1])}</p>${groups.length>1?`<div class="ms-section-jumps">${groups.map(g=>`<button type="button" data-jump-group="${e(g)}">${e(g)}</button>`).join('')}</div>`:''}`;
      host.querySelector('#ms-clear-search')?.addEventListener('click',()=>{menuQuery='';menuEl.querySelector('#zs-menu-q').value='';applyMenuFilter();});
      host.querySelectorAll('[data-jump-group]').forEach(button=>button.onclick=()=>{const target=[...menuEl.querySelectorAll('#zs-pane > section')].find(x=>x.dataset.zsTab===tab&&x.dataset.zsGroup===button.dataset.jumpGroup);target?.scrollIntoView({block:'start'});});
      const pane=menuEl.querySelector('#zs-pane');pane.setAttribute('role','tabpanel');pane.setAttribute('aria-label',query?'Settings search results':meta[0]);
    }
    const MENU_ROUTES = [
      [(e) => !!e.querySelector(".zs-overview"), "home", ""],
      [/^Set up Multi-Script/, "home", ""],
      [/^Jump to/, "home", ""],
      [/^Position/, "bar", ""], [/^Look$/, "bar", ""], [/^Show on the bar/, "bar", ""],
      [/^Provider sessions/, "cowork", "Provider sessions"], [/^Skills library/, "workshop", "Library"], [/^Skill workshop/, "workshop", "Create & share"], [/^Follow-ups in this chat/, "cowork", "Live session"], [/^Co-work task board/, "cowork", "Shared tasks"],
      [/^Appearance studio/, "look", "Theme & layout"], [/^Sounds & alerts/, "look", "Sound"], [/^Custom background/, "look", "Background"],
      [/^Execution effort/, "agent", "Quality & effort"], [/^Critic review/, "agent", "Quality & effort"], [/^Notion AI behavior/, "agent", "Quality & effort"], [/^Creative output/, "agent", "Quality & effort"],
      [/^Studio skill coverage/, "agent", "Quality & effort"], [/^Usage optimizer/, "agent", "Quality & effort"],
      [/^Prompt enhancer/, "agent", "Prompting"], [/^Custom instructions/, "agent", "Prompting"],
      [/^Autonomy/, "agent", "Autonomy & safety"], [/^Verification handling/, "agent", "Autonomy & safety"], [/^Error recovery/, "agent", "Autonomy & safety"], [/^Reply pacing/, "agent", "Autonomy & safety"],
      [/^Trial & credits/, "notion", ""], [/^Models in agent mode/, "notion", ""], [/^Notion Auto preferred model/, "notion", ""],
      [/^Live capability inventory/, "tools", "Capabilities"], [/^Media relay/, "tools", "Media"], [/^Surface vision/, "tools", "Media"], [/^Audio generation/, "tools", "Media"],
      [/^Bridge$/, "engines", "Connection status"], [/^Engine setup guides/, "engines", "Setup"], [/^Engines & MCP/, "engines", "Servers"],
      [/^Switch AI/, "sites", ""], [/^Provider benchmarks/, "sites", ""],
      [/^Settings backup/, "help", "Maintenance"], [/^Troubleshooting/, "help", "Maintenance"],
      [/^Settings map/, "help", "Guide"], [/^[1-5] ·/, "help", "Guide"],
      [/^Free Support/, "help", "Support"], [/^Support with Robux/, "help", "Support"],
    ];
    const MENU_ACCORDION_TABS = new Set(["agent", "tools", "help"]);
    const accOpen = {};
    let menuQuery = "";
    function labelOf(sec) { const l = sec.querySelector(".zs-sec-label span"); return l ? l.textContent.trim() : ""; }
    function organizeMenu() {
      const pane = menuEl.querySelector("#zs-pane"); if (!pane) return;
      const secs = [...pane.querySelectorAll(":scope > section[data-zs-tab]")];
      const rank = new Map();
      secs.forEach((sec, i) => {
        const label = labelOf(sec);
        let idx = MENU_ROUTES.findIndex(([m]) => typeof m === "function" ? m(sec) : m.test(label));
        if (idx >= 0) { sec.dataset.zsTab = MENU_ROUTES[idx][1]; sec.dataset.zsGroup = MENU_ROUTES[idx][2] || ""; }
        else { if (TAB_ALIAS[sec.dataset.zsTab]) sec.dataset.zsTab = TAB_ALIAS[sec.dataset.zsTab]; idx = 900 + i; }
        if (sec.dataset.zsTab === "notion" && P.id !== "notion") sec.dataset.zsTab = "agent";
        rank.set(sec, idx);
      });
      secs.sort((a, b) => rank.get(a) - rank.get(b));
      const empty = pane.querySelector(".zs-empty");
      secs.forEach((sec) => pane.insertBefore(sec, empty));
      // group headings + accordions
      const seenGroup = {}, firstInTab = {};
      for (const sec of secs) {
        const tab = sec.dataset.zsTab, grp = sec.dataset.zsGroup || "";
        if (grp && !seenGroup[tab + "|" + grp]) {
          seenGroup[tab + "|" + grp] = true;
          const h = document.createElement("div"); h.className = "zs-group-head"; h.dataset.zsTab = tab; h.textContent = grp;
          pane.insertBefore(h, sec);
        }
        const label = labelOf(sec);
        if (MENU_ACCORDION_TABS.has(tab) && label && sec.querySelector(".zs-sec-label")) {
          if (firstInTab[tab] === undefined) firstInTab[tab] = label;
          const open = accOpen[tab] ? accOpen[tab].has(label) : label === firstInTab[tab];
          sec.classList.add("zs-acc"); sec.classList.toggle("collapsed", !open); sec.dataset.zsLabel = label;
          const head = sec.querySelector(".zs-sec-label");
          head.setAttribute("role", "button"); head.setAttribute("tabindex", "0"); head.setAttribute("aria-expanded", String(open));
        }
      }
      // seed per-tab accordion state with the default-open section so later toggles are additive
      for (const [tab, label] of Object.entries(firstInTab)) if (!accOpen[tab]) accOpen[tab] = new Set([label]);
      pane.querySelectorAll(".zs-acc > .zs-sec-label").forEach((head) => {
        const toggle = () => {
          const sec = head.parentElement, tab = sec.dataset.zsTab, label = sec.dataset.zsLabel;
          const set = accOpen[tab] || (accOpen[tab] = new Set());
          const nowCollapsed = !sec.classList.contains("collapsed");
          sec.classList.toggle("collapsed", nowCollapsed);
          head.setAttribute("aria-expanded", String(!nowCollapsed));
          if (nowCollapsed) set.delete(label); else set.add(label);
        };
        head.addEventListener("click", toggle);
        head.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
      });
    }
    function applyMenuFilter() {
      const pane = menuEl.querySelector("#zs-pane"); if (!pane) return;
      const q = menuQuery.trim().toLowerCase();
      menuEl.classList.toggle("zs-searching", !!q);
      if (!q) { applyMenuTab(menuTab, true); return; }
      let n = 0;
      pane.querySelectorAll(":scope > section[data-zs-tab]").forEach((sec) => {
        const hit = !sec.classList.contains("zs-quick-sec") && (sec.textContent || "").toLowerCase().includes(q);
        sec.hidden = !hit; if (hit) { n++;sec.querySelector(".zs-sec-label[aria-expanded]")?.setAttribute("aria-expanded","true"); }
      });
      pane.querySelectorAll(".zs-group-head").forEach((h) => { h.hidden = true; });
      const empty = pane.querySelector(".zs-empty"); if (empty) empty.hidden = n > 0;
      pageHeading(menuTab,q,n);
      menuEl.querySelectorAll(".zs-menu-tabs button").forEach((b) => { b.classList.remove("active"); b.setAttribute("aria-selected", "false"); });
      pane.scrollTop = 0;
    }
    function applyMenuTab(tab, keepScroll) {
      tab = TAB_ALIAS[tab] || tab || "home";
      if (tab === "notion" && P.id !== "notion") tab = "agent";
      if (menuEl && !menuEl.querySelector(`.zs-menu-tabs button[data-tab="${tab}"]`)) tab = "home";
      menuTab = tab;
      menuEl.querySelectorAll(".zs-acc").forEach(sec=>sec.querySelector(".zs-sec-label")?.setAttribute("aria-expanded",String(!sec.classList.contains("collapsed"))));
      menuEl.classList.remove("zs-searching");
      pageHeading(tab);
      if(tab==="workshop"&&!libraryLoaded)setTimeout(()=>menuEl.querySelector("#ms-library-load")?.click(),0);
      if(tab==='help')setTimeout(()=>menuEl.querySelector('#ms-update-check')?.dispatchEvent(new CustomEvent('ms-update-status')),0);
      if(tab==="cowork")setTimeout(()=>menuEl.querySelector("#ms-cowork-refresh")?.click(),0);
      const pane = menuEl.querySelector("#zs-pane");
      menuEl.querySelectorAll("#zs-pane > [data-zs-tab]").forEach((el) => { el.hidden = el.dataset.zsTab !== menuTab; });
      const empty = pane && pane.querySelector(".zs-empty"); if (empty) empty.hidden = true;
      menuEl.querySelectorAll(".zs-menu-tabs button").forEach((b) => {
        const active = b.dataset.tab === menuTab; b.classList.toggle("active", active); b.setAttribute("aria-selected", active ? "true" : "false");b.tabIndex=active?0:-1;
      });
      if (!keepScroll && pane) pane.scrollTop = 0;
      if (pane && !keepScroll) { pane.classList.remove("zs-pane-in"); void pane.offsetWidth; pane.classList.add("zs-pane-in"); }
    }
    // Chat bar tab: every control writes straight into menuPrefs and the bar on the
    // page re-places itself on the next animation frame - no rebuild, so dragging a
    // slider never loses its grip. Segmented buttons rebuild only to move the highlight.
    function bindBarPanel() {
      const msg = (t) => { const m = menuEl.querySelector("#ms-bar-msg"); if (m) m.textContent = t; };
      for (const key of ["dock", "align", "fit", "style", "size", "status"]) {
        menuEl.querySelectorAll(`[data-bar-${key}]`).forEach((b) => b.addEventListener("click", () => {
          menuPrefs["bar" + key[0].toUpperCase() + key.slice(1)] = b.dataset["bar" + key[0].toUpperCase() + key.slice(1)];
          saveMenuPrefs(); const keep = (menuEl.querySelector("#zs-pane") || {}).scrollTop || 0; buildMenu();
          const pane = menuEl.querySelector("#zs-pane"); if (pane) pane.scrollTop = keep;
        }));
      }
      menuEl.querySelectorAll("[data-bar-item]").forEach((c) => c.addEventListener("change", () => {
        const hide = new Set(menuPrefs.barHide || []);
        if (c.checked) hide.delete(c.dataset.barItem); else hide.add(c.dataset.barItem);
        menuPrefs.barHide = [...hide]; saveMenuPrefs();
        const lab = c.closest(".zs-chip-toggle"); if (lab) lab.classList.toggle("on", c.checked);
      }));
      const barThemeSel = menuEl.querySelector("#ms-bar-theme");
      if (barThemeSel) barThemeSel.addEventListener("change", () => {
        menuPrefs.barTheme = barThemeSel.value; saveMenuPrefs(); buildMenu();
        toast(barThemeSel.value === "auto" ? "Chat bar follows the menu theme" : `Chat bar theme: ${barThemeSel.options[barThemeSel.selectedIndex].text}`);
      });
      {
        // Nudge sliders: the value applies instantly (placeBar runs every frame) and the
        // menu fades while dragging. Storage is written once the drag settles.
        let nudgeSave = 0;
        const commit = (immediate) => {
          clearTimeout(nudgeSave);
          const run = () => { try { chrome.storage.local.set({ msMenuPreferences: menuPrefs }); } catch {} };
          if (immediate) run(); else nudgeSave = setTimeout(run, 200);
        };
        const setNudge = (axis, val) => {
          const cur = nudgeOf();
          const by = { ...(menuPrefs.barOffsetBy || {}) };
          const n = { x: cur.x, y: cur.y }; n[axis] = Math.max(-NUDGE_MAX, Math.min(NUDGE_MAX, Math.round(Number(val) || 0)));
          if (n.x || n.y) by[P.id] = n; else delete by[P.id];
          menuPrefs.barOffsetBy = by;
          // a per-site entry now owns this site; neutralise the legacy global so a reset really resets
          if (!by[P.id]) { menuPrefs.barOffsetX = 0; menuPrefs.barOffsetY = 0; }
        };
        const paint = () => {
          const n = nudgeOf();
          for (const [id, val] of [["ms-bar-ox", n.x], ["ms-bar-oy", n.y]]) {
            const r = menuEl.querySelector("#" + id), v = menuEl.querySelector("#" + id + "-v");
            if (r && Number(r.value) !== val) r.value = String(val);
            if (v) v.textContent = fmtNudge(val);
          }
        };
        const fade = (on) => { if (menuEl) menuEl.classList.toggle("zs-nudging", on); };
        for (const [id, axis] of [["ms-bar-ox", "x"], ["ms-bar-oy", "y"]]) {
          const r = menuEl.querySelector("#" + id);
          if (!r) continue;
          r.addEventListener("input", () => { setNudge(axis, r.value); paint(); commit(false); });
          r.addEventListener("pointerdown", () => fade(true));
          for (const ev of ["pointerup", "pointercancel", "lostpointercapture", "blur"]) r.addEventListener(ev, () => { fade(false); commit(true); });
          r.addEventListener("keydown", (e) => { if (e.key === "Home" || e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); setNudge(axis, 0); paint(); commit(false); } });
        }
        menuEl.querySelectorAll("[data-nudge-reset]").forEach((l) => l.addEventListener("dblclick", () => { setNudge(l.dataset.nudgeReset, 0); paint(); commit(true); }));
        const nr = menuEl.querySelector("#ms-bar-nudge-reset");
        if (nr) nr.addEventListener("click", () => {
          const by = { ...(menuPrefs.barOffsetBy || {}) }; delete by[P.id]; menuPrefs.barOffsetBy = by;
          menuPrefs.barOffsetX = 0; menuPrefs.barOffsetY = 0; paint(); commit(true); toast("Chat bar nudge reset");
        });
      }
      const realign = menuEl.querySelector("#ms-bar-realign");
      if (realign) realign.addEventListener("click", () => {
        clearAnchorPad(); if (bar) resetBarLayout(); try { P.resetLayoutCache && P.resetLayoutCache(); } catch {}
        msg("Re-measured the composer."); toast("Chat bar realigned");
      });
      const rep = menuEl.querySelector("#ms-bar-report");
      if (rep) rep.addEventListener("click", async () => {
        const br = bar ? bar.getBoundingClientRect() : null;
        const report = { provider: P.id, version: EXT_VERSION, dock: menuPrefs.barDock, bar: br ? [br.left, br.top, br.width, br.height].map(Math.round) : null, composer: P.layoutReport ? P.layoutReport() : null, viewport: [innerWidth, innerHeight] };
        try { await navigator.clipboard.writeText(JSON.stringify(report, null, 2)); msg("Layout report copied — paste it in a bug report."); }
        catch { msg(JSON.stringify(report)); }
      });
      const reset = menuEl.querySelector("#ms-bar-reset");
      if (reset) reset.addEventListener("click", () => {
        for (const k of ["barDock", "barAlign", "barFit", "barSize", "barStyle", "barStatus", "barTheme", "barOffsetX", "barOffsetY", "barOffsetBy", "barHide"]) menuPrefs[k] = Array.isArray(DEFAULT_MENU_PREFS[k]) ? [] : (DEFAULT_MENU_PREFS[k] && typeof DEFAULT_MENU_PREFS[k] === "object" ? {} : DEFAULT_MENU_PREFS[k]);
        saveMenuPrefs(); buildMenu(); toast("Chat bar reset");
      });
    }
    function bindExtrasSections() {
      if (!menuEl || typeof ZSExtras === "undefined") return;
      const $ = (id) => menuEl.querySelector("#" + id);
      // Game idea bot
      const out = $("ms-idea-out"), ttl = $("ms-idea-title");
      const eng = $("ms-idea-engine"), gen = $("ms-idea-genre"), tw = $("ms-idea-twist");
      if (eng) eng.addEventListener("change", () => { ideaOpts.engine = eng.value; });
      if (gen) gen.addEventListener("change", () => { ideaOpts.genre = gen.value; });
      if (tw) tw.addEventListener("change", () => { ideaOpts.twist = tw.checked; });
      const ib = $("ms-idea-blender");
      if (ib) ib.addEventListener("change", () => { ideaOpts.blender = ib.checked; });
      menuEl.querySelectorAll("[data-idea-scope]").forEach((b) => b.addEventListener("click", (e) => {
        e.preventDefault(); e.stopPropagation();
        ideaOpts.scope = b.dataset.ideaScope;
        menuEl.querySelectorAll("[data-idea-scope]").forEach((x) => x.classList.toggle("active", x === b));
      }));
      const go = $("ms-idea-go");
      if (go) go.addEventListener("click", (e) => {
        // The overlay can be docked inside a provider's <form>. A button with no
        // explicit type submits that form before this handler paints the idea,
        // which made Generate look completely dead on real provider layouts even
        // though the pure generator passed. Block provider submission twice:
        // type="button" in the markup and preventDefault here.
        e.preventDefault(); e.stopPropagation();
        const prior = go.textContent;
        go.disabled = true; go.textContent = "Generating…";
        if (ttl) ttl.textContent = "Creating a production-ready brief…";
        try {
          const connected = (() => { try { return connectedEngineIds(); } catch { return []; } })();
          const result = ZSExtras.gameIdea({ ...ideaOpts, engines: connected });
          if (!result || typeof result.prompt !== "string" || !result.prompt.trim() || !result.title) {
            throw new Error("generator returned an incomplete idea");
          }
          lastIdea = result;
          if (out) {
            out.value = result.prompt;
            out.textContent = result.prompt; // keeps value truthful across provider DOM reconciliation
            out.dispatchEvent(new Event("input", { bubbles: true }));
          }
          if (ttl) ttl.textContent = `${result.title} · ${result.engine === "generic" ? "engine-free" : result.engine} · ${result.genre}`;
          ["ms-idea-copy", "ms-idea-insert"].forEach((id) => { const b = $(id); if (b) b.disabled = false; });
        } catch (err) {
          lastIdea = null;
          const message = `Could not generate an idea: ${String((err && err.message) || err || "unknown error")}`;
          if (ttl) ttl.textContent = "Game Idea Bot error";
          if (out) { out.value = message; out.textContent = message; }
          ui.banner("warn", "Game Idea Bot could not generate", message + ". Reload the extension once; if it repeats, copy diagnostics from Help.");
          diag("idea.generate.error", { error: message });
        } finally {
          go.disabled = false; go.textContent = prior || "Generate idea";
        }
      });
      const cp = $("ms-idea-copy");
      if (cp) cp.addEventListener("click", async () => { if (!lastIdea) return; try { await navigator.clipboard.writeText(lastIdea.prompt); toast("Game idea prompt copied"); } catch { if (out) { out.select(); document.execCommand("copy"); toast("Game idea prompt copied"); } } });
      const ins = $("ms-idea-insert");
      if (ins) ins.addEventListener("click", () => {
        if (!lastIdea) return;
        const ed = P.getEditor && P.getEditor();
        if (!ed) { toast("No chat box found - use Copy prompt"); return; }
        try {
          ed.focus();
          if (ed.tagName === "TEXTAREA" || ed.tagName === "INPUT") {
            Object.getOwnPropertyDescriptor(ed.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, "value").set.call(ed, lastIdea.prompt);
            ed.dispatchEvent(new Event("input", { bubbles: true }));
          } else document.execCommand("insertText", false, lastIdea.prompt);
          menuEl.hidden = true; toast("Idea placed in the chat box - review it and press send");
        } catch { toast("Could not type into the chat box - use Copy prompt"); }
      });
      // Software Builder (W.I.P.)
      const swStatus = $("ms-sw-status");
      const showSwStatus = (text, state = "") => {
        if (!swStatus) return;
        swStatus.textContent = text;
        swStatus.dataset.state = state;
      };
      const swSave = () => {
        const next = saveSoftwareSettings({ enabled: !!($("ms-sw-enabled") || {}).checked, allowRun: !!($("ms-sw-run") || {}).checked,
          root: ($("ms-sw-root") || {}).value || "", projectsDir: ($("ms-sw-projects") || {}).value || "",
          addons: { skills: !!($("ms-sw-ad-skills") || {}).checked, engines: !!($("ms-sw-ad-engines") || {}).checked, mcp: !!($("ms-sw-ad-mcp") || {}).checked } });
        showSwStatus(next.enabled ? `Saved · ${next.allowRun ? "commands allowed" : "files only"} · ${next.rootMode === "path" && next.root ? next.root : next.rootMode === "create" ? "AI creates a project folder" : "folder chosen in-session"}` : "Disabled.", next.enabled ? "ok" : "");
        if (A.software) configureSoftwareBridge().catch(() => {});
      };
      ["ms-sw-enabled", "ms-sw-run", "ms-sw-ad-skills", "ms-sw-ad-engines", "ms-sw-ad-mcp"].forEach((id) => { const el = $(id); if (el) el.addEventListener("change", swSave); });
      menuEl.querySelectorAll("[data-sw-mode]").forEach((b) => b.addEventListener("click", () => {
        saveSoftwareSettings({ mode: b.dataset.swMode });
        if (b.dataset.swMode === "code" && softwareSettings.rootMode === "create") saveSoftwareSettings({ rootMode: "ask" });
        buildMenu();
        toast(b.dataset.swMode === "code" ? "Code mode: the bar shows Code on new chats" : "Software Builder: the bar shows Build software on new chats");
      }));
      const swSaveBtn = $("ms-sw-save"); if (swSaveBtn) swSaveBtn.addEventListener("click", swSave);
      menuEl.querySelectorAll("[data-sw-root]").forEach((b) => b.addEventListener("click", () => {
        saveSoftwareSettings({ rootMode: b.dataset.swRoot });
        menuEl.querySelectorAll("[data-sw-root]").forEach((x) => x.classList.toggle("active", x === b));
        const r = $("ms-sw-root"); if (r) r.hidden = b.dataset.swRoot !== "path";
        swSave();
      }));
      const pickBtn = $("ms-sw-pick");
      if (pickBtn) pickBtn.addEventListener("click", async () => {
        if (!softwareSettings.enabled) { toast("Enable Software Builder first"); return; }
        showSwStatus("Checking the local bridge…", "busy");
        const cfg = await configureSoftwareBridge().catch((e) => ({ ok: false, error: String(e) }));
        if (!cfg || !cfg.ok) { showSwStatus(String((cfg && cfg.error) || "The bridge could not be configured."), "error"); return; }
        showSwStatus("Folder picker opened on your PC — check the taskbar.", "busy");
        const r = await bg({ type: "call_tool", name: "ms_ws_pick_folder", arguments: { title: "Choose the Multi-Script Software Builder folder" }, timeout: 600000 });
        let root = "";
        try { root = JSON.parse((r && r.text) || "{}").root || ""; } catch {}
        if (root) { saveSoftwareSettings({ rootMode: "path", root }); buildMenu(); toast("Workspace folder set"); }
        else showSwStatus(r && r.ok === false ? `Bridge: ${r.error || "offline"}` : "No folder chosen.", r && r.ok === false ? "error" : "");
      });
      const swCheck = $("ms-sw-check");
      if (swCheck) swCheck.addEventListener("click", async () => {
        showSwStatus("Checking bridge capabilities…", "busy");
        const r = await softwareBridgeReadiness(true);
        showSwStatus(r.ok ? "Connected — Software Builder and PC folder access are ready." : r.error, r.ok ? "ok" : "error");
      });
      const swRepair = $("ms-sw-repair");
      if (swRepair) swRepair.addEventListener("click", async () => {
        showSwStatus("Restarting the registered bridge…", "busy");
        swRepair.disabled = true;
        const r = await bg({ type: "host_restart" }).catch((e) => ({ ok: false, error: String(e) }));
        await new Promise((resolve) => setTimeout(resolve, 1400));
        A.toolsAt = 0;
        const ready = r && r.ok ? await softwareBridgeReadiness(true) : r;
        swRepair.disabled = false;
        showSwStatus(ready && ready.ok ? "Reconnected — PC workspace tools are ready." : String((ready && (ready.error || ready.code)) || "Restart failed. Run " + ZS.setupCommand() + " from this Multi-Script folder."), ready && ready.ok ? "ok" : "error");
      });
      const swTerminal = $("ms-sw-terminal");
      if (swTerminal) swTerminal.addEventListener("click", () => { menuEl.hidden = true; const t = ensureTerm(); if (t) t.openPanel("running"); });
      // Custom background
      const drop = $("ms-bg-drop"), file = $("ms-bg-file");
      const takeFile = (f) => {
        if (!f) return;
        if (!ZSExtras.BG_TYPES.includes(f.type)) { toast("Use a PNG, JPG, GIF or WebP image"); return; }
        if (f.size > ZSExtras.BG_MAX_BYTES) { toast("Image is larger than 12 MB"); return; }
        const rd = new FileReader();
        rd.onload = () => { bgImage = String(rd.result || ""); saveBg(); buildMenu(); toast(f.type === "image/gif" ? "Animated background applied" : "Background applied"); };
        rd.readAsDataURL(f);
      };
      if (drop && file) {
        drop.addEventListener("click", () => file.click());
        file.addEventListener("change", () => takeFile(file.files && file.files[0]));
        drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
        drop.addEventListener("dragleave", () => drop.classList.remove("over"));
        drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); takeFile(e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]); });
      }
      menuEl.querySelectorAll("[data-bg-fit]").forEach((b) => b.addEventListener("click", () => { bgPrefs.fit = b.dataset.bgFit; saveBg(); menuEl.querySelectorAll("[data-bg-fit]").forEach((x) => x.classList.toggle("active", x === b)); }));
      const op = $("ms-bg-op"), bl = $("ms-bg-bl");
      if (op) op.addEventListener("input", () => { bgPrefs.opacity = Number(op.value); const v = $("ms-bg-op-v"); if (v) v.textContent = op.value + "%"; saveBg(); });
      if (bl) bl.addEventListener("input", () => { bgPrefs.blur = Number(bl.value); const v = $("ms-bg-bl-v"); if (v) v.textContent = bl.value + "px"; saveBg(); });
      const onBar = $("ms-bg-bar"); if (onBar) onBar.addEventListener("change", () => { bgPrefs.onBar = onBar.checked; saveBg(); });
      const clr = $("ms-bg-clear"); if (clr) clr.addEventListener("click", () => { bgImage = ""; saveBg(); buildMenu(); toast("Background removed"); });
      if (typeof ZSSound !== "undefined") {
        const sv = (k, v) => ZSSound.save({ [k]: v });
        [["ms-snd-on", "enabled"], ["ms-snd-done", "done"], ["ms-snd-command", "command"], ["ms-snd-error", "error"]].forEach(([id, k]) => { const el = $(id); if (el) el.addEventListener("change", () => { sv(k, el.checked); if (k === "enabled") { const bd = el.closest(".zs-sound-sec"); const bg = bd && bd.querySelector(".zs-provider-badge"); if (bg) bg.textContent = el.checked ? "On" : "Off"; if (el.checked) ZSSound.play("done", true); } }); });
        menuEl.querySelectorAll("[data-snd-style]").forEach((b) => b.addEventListener("click", () => { sv("style", b.dataset.sndStyle); menuEl.querySelectorAll("[data-snd-style]").forEach((x) => x.classList.toggle("active", x === b)); ZSSound.play("done", true); }));
        const vol = $("ms-snd-vol"); if (vol) { vol.addEventListener("input", () => { sv("volume", Number(vol.value) / 100); const v = $("ms-snd-vol-v"); if (v) v.textContent = vol.value + "%"; }); vol.addEventListener("change", () => ZSSound.play("command", true)); }
        menuEl.querySelectorAll("[data-snd-test]").forEach((b) => b.addEventListener("click", () => ZSSound.play(b.dataset.sndTest, true)));
      }
    }
    let hubGame = null, followupEditingId=null;
    let hubItems = [];
    let coworkTasks = [];
    const hubDrafts={};let libraryRows=[],libraryOffset=0,libraryTotal=0,librarySeq=0,libraryLoaded=false,coworkEditingId=null;
    let skillFavorites=[];try{chrome.storage.local.get("msSkillFavorites",r=>{skillFavorites=Array.isArray(r.msSkillFavorites)?r.msSkillFavorites.filter(x=>typeof x==="string").slice(0,200):[];});}catch{}
    let queueInitial={};try{queueInitial=JSON.parse(sessionStorage.getItem("msCoworkQueue")||"{}");}catch{}
    const coworkContext=()=>P.id+"|"+(P.conversationKey()||location.href)+"|"+activeEngineIds().slice().sort().join(",")+"|"+(A.software?softwareSettings.root:"chat");
    coworkQueue=MSStudio.createCoworkQueue({
      initial:queueInitial,
      fits:text=>text.length+4000<=(ZS.limits?ZS.limits.sendBudget(P.sendCharBudget||32000):(P.sendCharBudget||32000)),
      context:coworkContext,
      ready:()=>A.started&&!A.running&&!A.starting&&!A.injecting&&!A.enhanceBusy&&!A.userStopped&&A.lastSendOk!==false&&!P.isGenerating()&&!P.editorText()?.trim(),
      send:async text=>{const result=await runStudioPrompt(text,{resume:false,preserve:true});if(!result?.ok)throw Error("Follow-up was not accepted");return result.base;},
      changed:state=>{try{sessionStorage.setItem("msCoworkQueue",JSON.stringify(state));}catch{}paintFollowups();},
      delivered:texts=>{A.lastUserText=((A.lastUserText||"")+"\nAdditional user requests:\n"+texts.join("\n")).slice(-16000);}
    });
    setInterval(()=>{if(coworkQueue?.snapshot().pending.length)void coworkQueue.take();},2000);
    function paintFollowups(){
      if(!menuEl)return;const host=menuEl.querySelector("#ms-followup-list");if(!host)return;
      const state=coworkQueue.snapshot(),e=MSStudio.escape;
      const info=menuEl.querySelector("#ms-followup-state");info.textContent=state.paused?state.reason:state.sending?"Delivering at the next safe boundary…":state.enabled?"Ready · follow-ups join the next tool result or start when idle.":"Off · enable when you want to queue requests.";
      host.innerHTML=state.pending.map((x,i)=>`<article class="ms-work-card"><div class="ms-work-card-head"><b>${i+1}. ${e(x.kind==='correction'?'Correction':x.kind==='goal'?'Additional goal':'Follow-up')}</b><span class="ms-status-pill">${e(x.status)}</span></div><p>${e(x.text.slice(0,400))}</p><div class="ms-toolbar"><button type="button" class="zs-mini-action" data-followup-edit="${x.id}" ${x.status!=='queued'?'disabled':''}>Edit</button><button type="button" class="zs-mini-action" aria-label="Move request up" data-followup-up="${x.id}" ${i===0||state.sending||x.status!=='queued'?'disabled':''}>↑</button><button type="button" class="zs-mini-action" aria-label="Move request down" data-followup-down="${x.id}" ${i===state.pending.length-1||state.sending||x.status!=='queued'?'disabled':''}>↓</button><button type="button" class="zs-mini-action" data-followup-remove="${x.id}" ${x.status==='sending'?'disabled':''}>Remove</button></div></article>`).join('')||'<div class="ms-empty-state">No queued requests. Add a correction or another goal while the agent works.</div>';
      host.querySelectorAll('[data-followup-remove]').forEach(b=>b.onclick=()=>{const r=coworkQueue.remove(b.dataset.followupRemove);if(!r.ok)info.textContent=r.error;});
      host.querySelectorAll('[data-followup-up],[data-followup-down]').forEach(b=>b.onclick=()=>{const up=b.dataset.followupUp,r=coworkQueue.move(up||b.dataset.followupDown,up?-1:1);if(!r.ok)info.textContent=r.error;});
      host.querySelectorAll('[data-followup-edit]').forEach(b=>b.onclick=()=>{const item=coworkQueue.snapshot().pending.find(x=>x.id===Number(b.dataset.followupEdit));if(!item)return;coworkQueue.pause('Paused while editing. Save your request, then Resume when ready.');followupEditingId=item.id;for(const [id,value]of [['ms-followup-text',item.text],['ms-followup-kind',item.kind||'followup']]){menuEl.querySelector('#'+id).value=value;hubDrafts[id]=value;}menuEl.querySelector('#ms-followup-add').textContent='Save request';menuEl.querySelector('#ms-followup-cancel').hidden=false;menuEl.querySelector('#ms-followup-text').focus();});
      const receipt=menuEl.querySelector('#ms-followup-receipts');receipt.textContent=state.history.filter(x=>x.context===coworkContext()).slice(-10).reverse().map(x=>(x.sentAt?new Date(x.sentAt).toLocaleTimeString()+' · ':'')+'Delivered · '+x.text.slice(0,180)).join('\n\n')||'No confirmed deliveries in this chat yet.';
      receipt.title='A delivery receipt confirms sending, not task completion.';
    }

    let hubClient = "";
    let hubWorker = "";
    try { hubWorker=sessionStorage.getItem("msCoworkWorker")||crypto.randomUUID(); sessionStorage.setItem("msCoworkWorker",hubWorker); } catch { hubWorker="worker-"+Math.random().toString(36).slice(2); }
    try { chrome.storage.local.get("msWorkshopClient", r => { hubClient = r.msWorkshopClient || crypto.randomUUID(); chrome.storage.local.set({msWorkshopClient:hubClient}); }); } catch { hubClient = "local"; }
    async function hubCall(name, args = {}) {
      const r = await bg({type:"call_tool", name, arguments:args, timeout:20000});
      if (!r || !r.ok) throw Error(r?.error || "Bridge unavailable. Start it with the terminal button.");
      const raw = r.result || r;
      const data = typeof raw.text === "string" ? JSON.parse(raw.text) : raw;
      if (data.ok === false) throw Error(data.error || "Request failed");
      return data;
    }
    async function runStudioPrompt(text, {remember=true,resume=true,preserve=false} = {}) {
      if (A.running || A.starting || A.injecting) { toast("Wait for the current task or press Stop."); return; }
      if (!A.started) { toast("Start a Multi-Script session first, then press this action."); return; }
      if (P.editorText && P.editorText().trim()) { toast("Send or clear your draft first; it is still in the composer."); return; }
      A.stop=false; A.userStopped=false; A.stopping=false;
      if (remember) A.lastUserText=text;
      if(!preserve)beginTaskProgress(text);
      const actionChat=P.conversationKey(),actionContext=coworkContext(),actionStop=A.stopAt||0;
      if(resume) await bg({type:"ms_provider_pacing",action:"resume",provider:P.id,owner:"user-action"});
      if(P.conversationKey()!==actionChat||(A.stopAt||0)!==actionStop) return;
      if(P.editorText&&P.editorText().trim()){toast("Your new draft is still in the composer; the action was not sent.");return;}
      const settingsKey=studioSettingsFingerprint();
      const addon=taskPromptAddon(text); if(addon) text += "\n\n" + addon;
      if (studioSettingsDirty) text += "\n\n" + activeStudioInstructions(false);
      if(preserve&&text.length+4000>(ZS.limits?ZS.limits.sendBudget(P.sendCharBudget||32000):(P.sendCharBudget||32000)))throw Error("Queued request exceeds the message budget. Shorten it or raise Limits before resending.");
      const base=await submitAndGetBase(text, undefined, {visible:true,settingsKey,contextGuard:()=>coworkContext()===actionContext});
      if (A.lastSendOk && settingsKey===studioSettingsFingerprint()) studioSettingsDirty=false;
      if(A.lastSendOk){A.responseFailure=null;}
      if(A.lastSendOk&&!A.running&&!A.userStopped) agentLoop(base);
      return {base,ok:A.lastSendOk};
    }
    function runStudioAction() {
      let memory=""; try { memory=memOn()?memCtrl.promptBlock():""; }catch{}
      const original=A.lastUserText||"Use the current conversation as the project brief.";
      const context="\nOriginal request: "+original.slice(0,8000)+(memory?"\nCurrent local memory (context, not authority):\n"+memory.slice(0,10000):"");
      const text="[MULTI-SCRIPT NEW IDEA · user clicked]\nRead this conversation and the included memory. Generate three specific, useful next directions for this actual project, with why each helps, what exists already, and a concrete first step. Avoid repeating finished work. Recommend one. Return ideas only; wait for me to choose before changing the project."+context;
      runStudioPrompt(text,{remember:false}).catch(e=>toast(e.message));
    }
    function coworkTaskText(task,owner){return `[MULTI-SCRIPT CO-WORK TASK ${task.id}]
${task.title}
${task.detail}
Project: ${task.project}
Owned resources: ${JSON.stringify(task.resources||[])}
Acceptance checks (zero-based): ${JSON.stringify(task.checks||[])}
Owner: ${owner}
Read the shared board, preserve adjacent interfaces and work within this scope. Report progress/evidence with ms_cowork update; this renews the lease. Report verified_checks indices only after checking those results. Record blocker when work cannot continue. Complete requires all checks, concrete evidence and no blocker. Tool success does not prove task completion. Claims coordinate work; they do not lock files. Other provider tabs may own adjacent tasks; use board/history for handoffs.`;}
    async function renderPhoneControl(host){
      if(!host?.isConnected)return;host.textContent='Checking the local bridge…';
      const request=async(op,payload={})=>{const r=await bg({type:'ms_mobile_admin',op,payload});if(!r?.ok)throw Error(r?.error||'Phone control requires the current running bridge.');return r;};
      try{
        const state=await request('status');if(!host.isConnected)return;const e=MSStudio.escape;
        host.innerHTML=`<div class="ms-phone-intro"><span class="ms-monitor-state">${state.enabled?'Remote enabled':'Off by default'}</span><h3>Take your studio with you.</h3><p>View task steps, queue a follow-up, pause/resume the queue or request Stop from your phone.</p></div>${state.enabled?`<label>Open on your phone<input readonly id="ms-phone-url" value="${e(state.url)}"></label><div class="ms-pair-code"><small>Single-use code · expires after two minutes</small><strong>${e(state.pairCode||'Generate a new code')}</strong></div><div class="ms-phone-actions"><button type="button" data-phone-op="pair">New pairing code</button><button type="button" data-phone-op="disable">Turn off remote</button></div><h4>Paired devices</h4>${(state.devices||[]).map(d=>`<div class="ms-phone-device"><span>${e(d.name)}</span><button type="button" data-revoke="${e(d.id)}">Revoke</button></div>`).join('')||'<p>No devices paired yet.</p>'}`:`<label>Desktop network address<select id="ms-phone-host">${(state.addresses||[]).map(ip=>`<option value="${e(ip)}">${e(ip)}</option>`).join('')}</select></label><button type="button" data-phone-op="enable" ${state.addresses?.length?'':'disabled'}>Enable on this network</button>${state.addresses?.length?'':'<p>No private network address detected. Connect your computer to your local network, then refresh.</p>'}`}<button type="button" data-phone-op="status">Refresh connection</button><p class="ms-monitor-note">Use the same trusted Wi-Fi. This local HTTP connection is not encrypted; never port-forward it. Access expires after one hour. Keep the desktop browser open and PC awake. Hidden chats follow your background-running preference.</p><p class="ms-phone-result" role="status"></p>`;
        const act=async(event,op,payload)=>{if(!event.isTrusted)return;const button=event.currentTarget;button.disabled=true;try{await request(op,payload);await renderPhoneControl(host);}catch(error){const line=host.querySelector('.ms-phone-result');if(line)line.textContent=error.message;}finally{if(button.isConnected)button.disabled=false;}};
        host.querySelectorAll('[data-phone-op]').forEach(b=>b.onclick=event=>act(event,b.dataset.phoneOp,{host:host.querySelector('#ms-phone-host')?.value}));
        host.querySelectorAll('[data-revoke]').forEach(b=>b.onclick=event=>act(event,'revoke',{device:b.dataset.revoke}));
      }catch(error){if(host.isConnected)host.textContent=error.message+' Start or restart the bridge, then reopen this panel.';}
    }
    function coworkProbe(includeBrief=false){
      return {ok:true,provider:P.id,name:P.displayName,editorFound:!!P.getEditor(),context:coworkContext(),worker:P.id+':'+hubWorker,mode:A.software?'Workspace tools':A.chatOnly?'Chat studio · no engine tools':'Engine session',started:A.started,starting:A.starting,running:A.running||A.injecting,generating:P.isGenerating(),sendUnconfirmed:!!A.sendUnconfirmed,enhancing:!!A.enhanceBusy,hasDraft:!!P.editorText()?.trim(),bridge:!!A.bridge?.connected,engines:activeEngineIds(),blenderToolsAvailable:A.started&&activeEngineIds().includes('blender')&&A.toolList.some(t=>t.name==='ms_blender_workspace'),blenderWorkspaceProject:activeEngineIds().includes('blender')?(A.bridge?.engines||[]).find(e=>e.id==='blender'&&e.backend==='headless-workspace')?.workspaceProject||null:null,background:keepRunningHidden,queuePaused:coworkQueue.snapshot().paused,queuePending:coworkQueue.snapshot().pending.length,stopped:A.userStopped,providerFailed:!!A.responseFailure,progress:readTaskProgress()?{...readTaskProgress(),summary:MSProgress.summary(readTaskProgress(),{running:A.running,generating:P.isGenerating(),waitingForUser:!!P.waitingForUser?.(),stopped:A.userStopped,providerFailed:!!A.responseFailure})}:null,
        ...(includeBrief?{brief:{request:String(A.lastUserText||'').slice(0,1800),reply:String(P.readAssistant()?.reply||'').slice(0,1800)}}:{})};
    }
    const dispatchReceipts=new Map();try{for(const [id,value]of JSON.parse(sessionStorage.getItem('msCoworkDispatchReceipts')||'[]').slice(-60))dispatchReceipts.set(id,value);}catch{}
    function dispatchReceipt(id,value){dispatchReceipts.set(id,value);while(dispatchReceipts.size>60)dispatchReceipts.delete(dispatchReceipts.keys().next().value);try{sessionStorage.setItem('msCoworkDispatchReceipts',JSON.stringify([...dispatchReceipts]));}catch{}return value;}
    async function coworkAction(msg){
      if(msg.context!==coworkContext())throw Error('Target chat or project changed. Refresh sessions before acting.');
      if(typeof msg.requestId!=='string'||!/^[a-zA-Z0-9-]{8,80}$/.test(msg.requestId))throw Error('Missing dispatch receipt.');
      if(dispatchReceipts.has(msg.requestId))return {...dispatchReceipts.get(msg.requestId),duplicate:true};
      if(msg.action==='followup'){
        if(!A.started||A.starting||A.sendUnconfirmed)throw Error('Start this chat and resolve unconfirmed sends on the desktop first.');
        if(typeof msg.text!=='string'||!msg.text.trim()||msg.text.length>4000)throw Error('Use 1–4,000 characters.');
        if(!coworkQueue.snapshot().enabled)coworkQueue.setEnabled(true);
        const result=coworkQueue.enqueue(msg.text,msg.kind);if(!result.ok)throw Error(result.error);
        return dispatchReceipt(msg.requestId,{ok:true,queued:true,queueId:result.id});
      }
      if(msg.action==='resume'){const result=coworkQueue.resume();if(!result.ok)throw Error(result.error);return dispatchReceipt(msg.requestId,{ok:true,resumed:true});}
      if(msg.action==='pause'){coworkQueue.pause('Paused from the co-work session board.');return dispatchReceipt(msg.requestId,{ok:true,paused:true});}
      if(msg.action==='stop'){stopLoop();return dispatchReceipt(msg.requestId,{ok:true,stopped:true});}
      if(msg.action==='start'){
        if(A.started||A.starting||A.running||P.isGenerating()||P.editorText()?.trim())throw Error('Start requires an idle chat with no draft and no active session.');
        if(msg.background===true){keepRunningHidden=true;void chrome.storage.local.set({msKeepRunningHidden:true});}
        dispatchReceipt(msg.requestId,{ok:true,accepted:true,ready:false});void startSession({chatOnly:msg.chatOnly});return dispatchReceipts.get(msg.requestId);
      }
      if(msg.action!=='assign')throw Error('Unsupported session action.');
      if(!A.started||A.starting||A.running||A.injecting||A.enhanceBusy||A.sendUnconfirmed||P.isGenerating()||P.editorText()?.trim())throw Error('Assignment requires a ready, idle session with no draft or unconfirmed send.');
      if(typeof msg.taskId!=='string'||!/^[a-f0-9]{16}$/.test(msg.taskId))throw Error('Choose a shared task.');
      dispatchReceipt(msg.requestId,{ok:false,unconfirmed:true,taskId:msg.taskId,error:'Dispatch in progress. Inspect this tab; this receipt will never be replayed.'});
      const scope=coworkContext(),owner=P.id+':'+hubWorker;let claimed=false;
      try{
        const board=await hubCall('ms_cowork',{action:'list'}),task=board.tasks.find(x=>x.id===msg.taskId);
        if(!task||task.status==='done'||task.active||task.blockedBy?.length)throw Error('Task is completed, owned or waiting on dependencies. Refresh the board.');
        if(scope!==coworkContext())throw Error('Context changed before claim.');
        const result=await hubCall('ms_cowork',{action:'claim',id:task.id,owner});claimed=true;
        if(scope!==coworkContext())throw Error('Context changed before delivery.');
        if(msg.background===true){keepRunningHidden=true;await chrome.storage.local.set({msKeepRunningHidden:true});}
        const sent=await runStudioPrompt(coworkTaskText(result.task,owner),{preserve:true});
        if(!sent?.ok)throw Error('Task delivery was not confirmed. Inspect the target chat.');
        return dispatchReceipt(msg.requestId,{ok:true,delivered:true,taskId:task.id,owner,note:'Prompt delivery confirmed; execution/verification remain on the shared task board.'});
      }catch(error){
        if(claimed&&!A.sendUnconfirmed)try{await hubCall('ms_cowork',{action:'release',id:msg.taskId,owner,note:'Remote dispatch stopped before confirmed delivery.'});}catch{}
        return dispatchReceipt(msg.requestId,{ok:false,unconfirmed:!!A.sendUnconfirmed,error:String(error.message||error),taskId:msg.taskId});
      }
    }
    async function refreshCoworkSessions(){
      const host=menuEl?.querySelector('#ms-cowork-sessions');if(!host)return;
      try{const board=await hubCall('ms_cowork',{action:'list'});coworkTasks=board.tasks||[];}catch{coworkTasks=[];}
      const response=await bg({type:'ms_cowork_tabs',action:'list'});if(!host.isConnected)return;
      if(!response?.ok){host.textContent=response?.error||'Reload the extension to discover provider tabs.';return;}
      const e=MSStudio.escape,available=coworkTasks.filter(t=>(t.status==='open'||t.expired)&&!t.blockedBy?.length);
      host.innerHTML=(response.participants||[]).map(t=>`<article class="ms-session-card"><div class="ms-work-card-head"><b>${e(t.name||t.host)}</b><span class="ms-status-pill">${!t.ok?'Unavailable':t.starting?'Starting':t.running||t.generating?'Working':t.started?'Ready':'Not started'}</span></div><p>${e(t.title)}</p><small>${e(t.host)} · ${e(t.mode||'')} · ${t.background?'Background allowed':'Pauses when hidden'}${t.hasDraft?' · Draft protected':''}</small>${!t.ok?`<p>${e(t.error)}</p>`:`<div class="ms-toolbar"><button type="button" class="zs-mini-action" data-session-action="focus" data-tab-id="${t.tabId}">Open tab</button><button type="button" class="zs-mini-action" data-session-action="read" data-tab-id="${t.tabId}">Read brief</button>${!t.started&&!t.starting?`<button type="button" class="zs-mini-action" data-session-action="start" data-tab-id="${t.tabId}" ${!t.editorFound||t.running||t.generating||t.hasDraft?'disabled':''} data-session-mode="chat">Start chat studio</button>${t.engines?.length?`<button type="button" class="zs-mini-action" data-session-action="start" data-session-mode="engine" data-tab-id="${t.tabId}" ${!t.editorFound||t.running||t.generating||t.hasDraft?'disabled':''}>Start with engines</button>`:''}`:''}<button type="button" class="zs-mini-action" data-session-action="pause" data-tab-id="${t.tabId}">Pause queue</button><button type="button" class="zs-mini-action" data-session-action="stop" data-tab-id="${t.tabId}" ${!t.running&&!t.starting&&!t.generating?'disabled':''}>Stop run</button></div><div class="ms-session-assign"><select class="zs-mcp-field" data-session-task="${t.tabId}" aria-label="Task for ${e(t.name||t.host)}"><option value="">Choose a ready task</option>${available.map(task=>`<option value="${e(task.id)}">${e(task.project)} · ${e(task.title)}</option>`).join('')}</select><button type="button" class="zs-mini-action" data-session-action="assign" data-tab-id="${t.tabId}" ${!t.editorFound||!t.started||t.running||t.starting||t.generating||t.hasDraft||!available.length?'disabled':''}>Assign here</button></div><pre data-session-brief="${t.tabId}" hidden></pre>`}</article>`).join('')||'<div class="ms-empty-state">Open a supported provider chat in another tab, then refresh. Reload provider tabs after updating the extension.</div>';
      host.querySelectorAll('[data-session-action]').forEach(button=>button.onclick=async()=>{button.disabled=true;const tabId=Number(button.dataset.tabId),target=response.participants.find(t=>t.tabId===tabId),action=button.dataset.sessionAction,status=menuEl.querySelector('#ms-session-status');try{
        const taskId=host.querySelector(`[data-session-task="${tabId}"]`)?.value;if(action==='assign'&&!taskId)throw Error('Choose a ready task first.');
        const result=await bg({type:'ms_cowork_tabs',action,tabId,context:target.context,requestId:crypto.randomUUID(),taskId,chatOnly:button.dataset.sessionMode!=='engine',background:menuEl.querySelector('#ms-cowork-background')?.checked===true});
        if(!result?.ok)throw Error(result?.error||'No acknowledgement; inspect the target tab before retrying.');
        if(action==='read'){const preview=host.querySelector(`[data-session-brief="${tabId}"]`);preview.hidden=false;preview.textContent='Current request\n'+(result.brief?.request||'No task recorded.')+'\n\nLatest response (excerpt)\n'+(result.brief?.reply||'No readable response.');}
        else{status.textContent=action==='assign'?'Delivered to '+target.name+'. Completion is tracked by acceptance checks and evidence.':action==='start'?'Startup requested. Refresh to inspect readiness.':'Session action acknowledged.';if(action!=='focus')await refreshCoworkSessions();}
      }catch(error){status.textContent=error.message;}finally{if(button.isConnected)button.disabled=false;}});
    }

    function studioHubHtml() {
      const e=MSStudio.escape;
      const policy=typeof MSBuild!=="undefined"?MSBuild:{edition:"dev"};
      return `<section class="zs-menu-sec" data-zs-tab="tools">
        <div class="zs-sec-label"><span>Live capability inventory</span><span class="zs-provider-badge">${e(policy.edition)} edition</span></div>
        <div class="zs-menu-note">Tools below are advertised by the bridge; engine availability is shown by the connection status. Skills provide instructions; they are not independent agents or native engine commands.</div>
        <button id="ms-cap-refresh" class="zs-mini-action">Refresh tools &amp; skills</button><input id="ms-cap-filter" type="search" class="zs-mcp-field" placeholder="Filter names or descriptions" aria-label="Filter capabilities"><div id="ms-cap-list" class="ms-hub-list">Press Refresh to inspect the live catalog.</div>
      </section>
      <section class="zs-menu-sec ms-skills-library" data-zs-tab="workshop">
        <div class="zs-sec-label"><span>Skills library</span><span class="zs-provider-badge">241 built-in workflows</span></div>
        <p class="ms-section-intro">Find a method, inspect its checks and apply it to your project. Skills adapt to your code, engine and style.</p>
        <div class="ms-field-grid"><label>Search<input id="ms-library-search" type="search" class="zs-mcp-field" placeholder="UI, animation, saves, modeling…" value="${e(hubDrafts['ms-library-search']||'')}"></label><label>Engine<select id="ms-library-engine" class="zs-mcp-field">${['','general','roblox','unity','godot','blender','figma'].map(v=>`<option value="${v}" ${hubDrafts['ms-library-engine']===v?'selected':''}>${v||'All engines'}</option>`).join('')}</select></label></div>
        <div class="ms-toolbar"><button id="ms-library-load" class="zs-mini-action">Refresh library</button><label><input id="ms-library-favorites" type="checkbox"> Favorites</label><span id="ms-library-count" role="status"></span></div>
        <label class="zs-pref-label" for="ms-library-goal">Goal for this project</label><input id="ms-library-goal" maxlength="4000" class="zs-mcp-field" placeholder="Optional: what should this skill improve?" value="${e(hubDrafts['ms-library-goal']||'')}">
        <div id="ms-library-list" class="ms-skill-grid"><div class="ms-empty-state">Open the library to browse actual installed workflows.</div></div>
        <div class="ms-toolbar"><button id="ms-library-prev" class="zs-mini-action">Previous</button><button id="ms-library-next" class="zs-mini-action">Next</button></div>
        <details id="ms-library-detail"><summary>Selected workflow &amp; verification</summary><pre id="ms-library-preview">Choose Read on a skill.</pre></details>
        <div id="ms-library-status" class="zs-menu-note" role="status"></div>
      </section>
      <section class="zs-menu-sec" data-zs-tab="workshop">
        <div class="zs-sec-label"><span>Skill workshop</span><span class="zs-provider-badge">scope · adapt · verify</span></div>
        <div class="zs-menu-note">Create a reusable method or import Markdown, text or JSON. Enable it globally or just for this chat/workspace. Matching engines and project scope determine which installed skills reach each prompt. Candidate methods require validation; mark verified only after testing them yourself. Publishing stores instructions, never executable plug-ins. Local library works immediately; connect a hosted workshop for other people to browse, rate and leave feedback.</div>
        <div class="ms-field-grid"><label>Name<input id="ms-skill-name" class="zs-mcp-field" maxlength="100" placeholder="My project workflow"></label><label>Engine<select id="ms-skill-engine" class="zs-mcp-field">${['general','roblox','unity','godot','blender','figma'].map(v=>`<option>${v}</option>`).join('')}</select></label></div>
        <label class="zs-pref-label" for="ms-skill-instructions">Instructions</label><textarea id="ms-skill-instructions" rows="5" placeholder="When to use it, what to inspect, what to change, and how to verify the result."></textarea>
        <div class="ms-field-grid"><label>Use in<select id="ms-skill-scope" class="zs-mcp-field"><option value="project">This chat / workspace</option><option value="all">All matching projects</option></select></label><label class="zs-pref-row"><input id="ms-skill-confirmed" type="checkbox"> I tested this method successfully</label></div>
        <div class="ms-toolbar"><button id="ms-skill-create" class="zs-mini-action zs-primary-action">Install this workflow</button><label class="zs-mini-action ms-file-label">Import .md / .txt / .json<input id="ms-skill-file" type="file" accept=".md,.txt,.json,text/plain,application/json" hidden></label></div>
        <p id="ms-skill-selection" class="zs-menu-note" role="status"></p>
        <details class="ms-skill-import"><summary>Advanced JSON import / publish</summary>
        <label class="zs-pref-label" for="ms-skill-json">Skill JSON</label><textarea id="ms-skill-json" rows="8" spellcheck="false">${e(JSON.stringify({id:"my-studio-skill",name:"My studio skill",engine:"general",description:"When to use this skill",instructions:"Inspect the real project first. Implement the requested result with live tools. Verify the result and report concrete evidence."},null,2))}</textarea>
        <div class="zs-menu-actions"><button id="ms-skill-install" class="zs-mini-action">Install locally</button><button id="ms-skill-publish" class="zs-mini-action">Publish to workshop</button><button id="ms-workshop-refresh" class="zs-mini-action">Browse workshop</button></div>
        </details>
        <input id="ms-workshop-search" type="search" class="zs-mcp-field" placeholder="Search workshop" aria-label="Search workshop"><div id="ms-workshop-results" class="ms-hub-list"></div><div class="zs-menu-actions"><button id="ms-workshop-prev" class="zs-mini-action">Previous</button><button id="ms-workshop-next" class="zs-mini-action">Next</button></div>
        <div class="zs-setting-title">Installed in this browser</div><div id="ms-installed-skills">${customSkills.map(x=>`<div class="ms-hub-row"><b>${e(x.name)}</b><button class="zs-mini-action" data-uninstall-skill="${e(x.id)}">Remove</button></div>`).join("")||"No custom skills installed."}</div>
        <details><summary>Connect a community workshop</summary><input id="ms-workshop-url" type="url" class="zs-mcp-field" placeholder="https://your-workshop.example" aria-label="Workshop server URL"><input id="ms-workshop-token" type="password" class="zs-mcp-field" placeholder="Your individual access token" aria-label="Workshop access token" autocomplete="off"><div class="zs-menu-actions"><button id="ms-workshop-connect" class="zs-mini-action">Connect</button><button id="ms-workshop-local" class="zs-mini-action">Use local library</button></div><div class="zs-menu-note">The token stays in the local bridge connection file. It is excluded from exports and prompts. Server setup is included in docs/WORKSHOP.md.</div></details>
        <div id="ms-hub-status" class="zs-menu-note" role="status" aria-live="polite"></div>
      </section>
      <section class="zs-menu-sec ms-sessions-sec" data-zs-tab="cowork"><div class="zs-sec-label"><span>Provider sessions</span><span class="zs-provider-badge">multiple tabs · one board</span></div><p class="ms-section-intro">Connect your open AI provider tabs, read their current brief and assign disjoint shared tasks. Each tab uses its own selected model, session and tools.</p><div class="ms-toolbar"><button id="ms-sessions-refresh" class="zs-mini-action zs-primary-action">Discover provider tabs</button><label><input id="ms-cowork-background" type="checkbox" ${keepRunningHidden?'checked':''}> Allow assigned chats to work in background</label></div><p class="zs-menu-note">Start each chat, then assign a ready task explicitly. Existing drafts, active runs and unconfirmed sends are protected. Read brief displays bounded excerpts locally. Assignments require a confirmed receipt and do not mean the task is complete.</p><div id="ms-cowork-sessions" class="ms-session-grid"><div class="ms-empty-state">Discover open provider tabs to connect your workspace.</div></div><p id="ms-session-status" class="zs-menu-note" role="status"></p></section>
      <section class="zs-menu-sec ms-followup-sec" data-zs-tab="cowork">
        <div class="ms-toolbar"><button id="ms-open-progress" class="zs-mini-action">Run monitor</button><button id="ms-open-phone" class="zs-mini-action">Phone control</button></div>
        <div class="zs-sec-label"><span>Follow-ups in this chat</span><span class="zs-provider-badge">ordered · confirmed delivery</span></div>
        <p class="ms-section-intro">Keep working together while the agent runs. Queue a correction or another goal without replacing unfinished work.</p>
        <label class="zs-pref-row"><input id="ms-followup-enabled" type="checkbox" ${coworkQueue.snapshot().enabled?'checked':''}> Enable queued follow-ups</label>
        <label class="zs-pref-label" for="ms-followup-kind">Request type</label><select id="ms-followup-kind" class="zs-mcp-field"><option value="followup">Follow-up</option><option value="correction">Correction to current work</option><option value="goal">Additional goal</option></select><textarea id="ms-followup-text" rows="3" maxlength="16000" placeholder="Add a request for the next safe boundary…">${e(hubDrafts['ms-followup-text']||'')}</textarea>
        <div class="ms-toolbar"><button id="ms-followup-add" class="zs-mini-action zs-primary-action">Queue request</button><button id="ms-followup-cancel" class="zs-mini-action" hidden>Cancel edit</button><button id="ms-followup-pause" class="zs-mini-action">Pause</button><button id="ms-followup-resume" class="zs-mini-action">Resume</button></div>
        <p id="ms-followup-state" role="status" class="zs-menu-note"></p><div id="ms-followup-list"></div><details><summary>Recent delivery receipts</summary><pre id="ms-followup-receipts"></pre></details>
      </section>
      <section class="zs-menu-sec ms-cowork-sec" data-zs-tab="cowork">
        <div class="zs-sec-label"><span>Co-work task board</span><span class="zs-provider-badge">shared local workspace</span></div>
        <p class="ms-section-intro">One brief, clear ownership, visible proof. Coordinate provider tabs around the same project without losing the work in progress.</p><div class="ms-cowork-guide"><article><b>01 · Scope</b><span>Define the result, resources and acceptance checks.</span></article><article><b>02 · Own</b><span>Claim a ready task in an idle chat. Keep handoffs explicit.</span></article><article><b>03 · Prove</b><span>Record checks, evidence and blockers before completion.</span></article></div>
        <details id="ms-cowork-composer" open><summary>Create a task</summary>
          <input id="ms-cowork-title" class="zs-mcp-field" maxlength="160" placeholder="Task title" aria-label="Task title">
          <textarea id="ms-cowork-detail" rows="3" placeholder="Acceptance criteria and expected result" aria-label="Co-work task details"></textarea>
          <div class="ms-field-grid"><label>Project<input id="ms-cowork-project" class="zs-mcp-field" value="default" maxlength="120"></label><label>Priority<select id="ms-cowork-priority" class="zs-mcp-field"><option value="normal">Normal</option><option value="high">High</option><option value="low">Low</option></select></label></div>
          <label class="zs-pref-label" for="ms-cowork-checks">Acceptance checks, one per line</label><textarea id="ms-cowork-checks" rows="3" maxlength="3612" placeholder="Opens on phone and desktop&#10;Keyboard focus is visible&#10;Actual playtest completes without errors"></textarea><label class="zs-pref-label">Owned files / assets, one per line</label><textarea id="ms-cowork-resources" rows="2" placeholder="src/ui/&#10;Workspace/Shop"></textarea>
          <label class="zs-pref-label">Depends on task IDs, comma separated</label><input id="ms-cowork-deps" class="zs-mcp-field" placeholder="Optional dependencies">
          <div class="ms-toolbar"><button id="ms-cowork-add" class="zs-mini-action zs-primary-action">${coworkEditingId?"Save changes":"Add task"}</button><button type="button" id="ms-cowork-cancel-edit" class="zs-mini-action" ${coworkEditingId?"":"hidden"}>Cancel edit</button></div>
        </details>
        <div class="ms-toolbar ms-board-controls"><select id="ms-cowork-project-filter" class="zs-mcp-field" aria-label="Filter co-work project"><option value="">All projects</option></select><input id="ms-cowork-search" class="zs-mcp-field" type="search" placeholder="Filter this board" aria-label="Filter co-work tasks"><select id="ms-cowork-filter" class="zs-mcp-field" aria-label="Co-work task filter"><option value="all">All tasks</option><option value="mine">Assigned to me</option><option value="open">Ready / open</option><option value="done">Completed</option><option value="blocked">Blocked / waiting</option></select><select id="ms-cowork-sort" class="zs-mcp-field" aria-label="Sort co-work tasks"><option value="priority">Priority first</option><option value="updated">Recently updated</option><option value="title">Title</option></select><button id="ms-cowork-refresh" class="zs-mini-action">Refresh</button></div>
        <div id="ms-cowork-counts" class="ms-board-counts"></div><div id="ms-cowork-board" class="ms-task-board"></div><div id="ms-cowork-status" class="zs-menu-note" role="status"></div>
        <p class="zs-menu-note">Claims last 30 minutes; progress updates renew them. Resource checks coordinate claims and do not lock files. Each tab follows your background-running preference and shared provider pacing.</p>
      </section>
      <section class="zs-menu-sec ms-flight-page" data-zs-tab="flight">
        <div class="ms-flight-heading"><img src="${chrome.runtime.getURL('icon.png')}" width="40" height="40" alt="Multi-Script"><div><span class="ms-page-path">Multi-Script Arcade</span><h3>Code Flight</h3><p>One spark. An endless skyline.</p></div><span class="zs-provider-badge">offline</span></div>
        <div class="ms-flight-options"><label>World<select id="ms-flight-world" class="zs-mcp-field"><option value="terminal">Terminal horizon</option><option value="orbit">Orbital dusk</option><option value="dawn">Daybreak</option></select></label><label>Flight<select id="ms-flight-mode" class="zs-mcp-field"><option value="arcade">Arcade · rising challenge</option><option value="practice">Practice · gentle gates</option></select></label></div>
        <div class="ms-flight-stage"><canvas id="ms-code-flight" width="1040" height="600" tabindex="0" role="application" aria-label="Code Flight. Space, Up or tap to fly. P to pause. R to restart.">Fly the Multi-Script icon through code gates. Use Space or Up to fly.</canvas></div>
        <div class="ms-flight-footer"><div id="ms-flight-status" role="status" aria-live="polite">Ready to fly.</div><div class="ms-toolbar"><button id="ms-flight-launch" class="zs-mini-action zs-primary-action">Fly / boost</button><button id="ms-flight-pause" class="zs-mini-action">Pause</button><button id="ms-flight-restart" class="zs-mini-action">Restart</button></div></div>
        <p class="zs-menu-note">Space / ↑ / tap to boost · P to pause · R to restart. Clear code gates to score; center passes earn precision bonuses. Best scores stay on this device, separately for Arcade and Practice. Leaving this tab pauses your flight.</p>
      </section>
      ${P.id==="vani"?`<section class="zs-menu-sec" data-zs-tab="vani"><div class="zs-sec-label"><span>Vani compatibility</span></div><div class="zs-menu-note">Multi-Script executes local bridge JSON commands one at a time and returns their results in subsequent turns. This can continue across responses without relying on Vani's native per-response tool count. It does not change Vani quotas. Open c.vani.ai/chat. Guest chat redirects to /c and is text-only; sign in for saved conversations and account features.</div><div class="zs-menu-note">For regular use, we recommend Vani Plus. Check the <a href="https://vani.ai/#plans" target="_blank" rel="noopener">current plans</a> for your needs. Vani Chat and prepaid API billing are separate products.</div><button id="ms-vani-check" class="zs-mini-action">Check composer &amp; response detection</button><pre id="ms-vani-status"></pre></section>`:""}`;
    }
    let workshopOffset=0;
    function bindStudioHub() {
      const $=id=>menuEl.querySelector("#"+id);
      const status=(msg,id="ms-hub-status")=>{if($(id))$(id).textContent=msg;};
      const bind=(id,fn)=>$(id)?.addEventListener("click",async e=>{const button=e.currentTarget;button.disabled=true;try{await fn();}catch(err){status(err.message,id.startsWith("ms-cowork")?"ms-cowork-status":id.startsWith("ms-followup")?"ms-followup-state":id.startsWith("ms-library")?"ms-library-status":"ms-hub-status");toast(err.message);}finally{if(button.isConnected)button.disabled=false;}});
      if(hubGame)hubGame.destroy();
      if($("ms-code-flight"))hubGame=MSStudio.mountGame($("ms-code-flight"),$("ms-flight-status"),chrome.runtime.getURL("icon.png"));
      const install=async (skill,options={})=>{
        const clean=MSStudio.validateSkill({...skill,scope:options.scope??($("ms-skill-scope").value==="project"?skillScopeKey():""),confirmed:options.confirmed??$("ms-skill-confirmed").checked});const items=customSkills.filter(x=>x.id!==clean.id);
        if(items.length>=12)throw Error("Remove an installed skill first (maximum 12).");
        await hubCall("ms_workshop",{action:"install",skill:clean,client:hubClient});
        customSkills=[...items,clean];await chrome.storage.local.set({msCustomSkills:customSkills});
        studioSettingsDirty=true;
        paintInstalled();
        status("Installed. Matching enabled workflows are applied to the next task and instruction refresh.");
        if(A.started&&!A.running&&!A.starting){bumpSys("users");}
      };

      const guard=fn=>async()=>{try{await fn();}catch(err){status(err.message,"ms-library-status");}};
      async function skillData(id){return hubCall("ms_get_skill",{skill_id:id,objective:($("ms-library-goal").value||A.lastUserText||"").slice(0,4000)});}
      function renderLibrary(){
        const host=$("ms-library-list");if(!host)return;const e=MSStudio.escape;
        const rows=libraryRows.filter(x=>!$("ms-library-favorites").checked||skillFavorites.includes(x.id));
        host.innerHTML=rows.map(x=>`<article class="ms-work-card"><div class="ms-work-card-head"><b>${e(x.name)}</b><button type="button" class="ms-favorite" data-skill-favorite="${e(x.id)}" aria-label="Favorite ${e(x.name)}" aria-pressed="${skillFavorites.includes(x.id)}">${skillFavorites.includes(x.id)?'★':'☆'}</button></div><small>${e(x.engine||'general')} · ${e(x.category||'workflow')}</small><p>${e(x.description)}</p><div class="ms-toolbar"><button type="button" class="zs-mini-action" data-library-read="${e(x.id)}">Read</button><button type="button" class="zs-mini-action" data-library-apply="${e(x.id)}">Apply to project</button><button type="button" class="zs-mini-action" data-library-keep="${e(x.id)}">Keep for project</button></div></article>`).join('')||'<div class="ms-empty-state">No matching skills on this page. Adjust your filters or browse another page.</div>';
        $("ms-library-count").textContent=libraryTotal?`${libraryOffset+1}–${Math.min(libraryOffset+libraryRows.length,libraryTotal)} of ${libraryTotal}`:"0 matching skills";
        $("ms-library-prev").disabled=!libraryOffset;$("ms-library-next").disabled=libraryOffset+libraryRows.length>=libraryTotal;
        host.querySelectorAll('[data-skill-favorite]').forEach(b=>b.onclick=()=>{const id=b.dataset.skillFavorite;skillFavorites=skillFavorites.includes(id)?skillFavorites.filter(x=>x!==id):[...skillFavorites,id].slice(-200);chrome.storage.local.set({msSkillFavorites:skillFavorites});renderLibrary();});
        host.querySelectorAll('[data-library-keep]').forEach(b=>b.onclick=guard(async()=>{const context=coworkContext(),scope=skillScopeKey(),skill=await skillData(b.dataset.libraryKeep);if(context!==coworkContext())throw Error('Context changed; the workflow was not installed.');await install(MSStudio.adaptSkill(skill,scope),{scope,confirmed:false});status('Saved to your installed workflow stack. Enable, scope or inspect it below.','ms-library-status');}));
        host.querySelectorAll('[data-library-read]').forEach(b=>b.onclick=guard(async()=>{const skill=await skillData(b.dataset.libraryRead);$("ms-library-preview").textContent=JSON.stringify(skill,null,2);$("ms-library-detail").open=true;}));
        host.querySelectorAll('[data-library-apply]').forEach(b=>b.onclick=guard(async()=>{
          if(!A.started)throw Error('Start a Multi-Script session first.');
          const skillChat=coworkContext();const skill=await skillData(b.dataset.libraryApply);if(coworkContext()!==skillChat)throw Error('Chat changed; the skill was not applied.');const goal=$("ms-library-goal").value.trim()||A.lastUserText;
          if(!goal)throw Error('Enter a goal so the workflow can adapt to your project.');
          const text='[MULTI-SCRIPT SKILL · user selected]\nGoal: '+goal+'\nAdapt this reference workflow to the inspected project, preserve existing architecture/style and complete the requested result with actual tools.\n'+JSON.stringify({id:skill.id,name:skill.name,engine:skill.engine,executionWorkflow:skill.executionWorkflow,steps:(skill.steps||[]).slice(0,12).map(x=>String(x).slice(0,600)),more:"Use ms_get_skill with this id to read the complete workflow if needed."});
          if(A.running){const result=coworkQueue.enqueue(text);if(!result.ok)throw Error(result.error);status('Skill queued for the next safe boundary.','ms-library-status');}
          else await runStudioPrompt(text);
        }));
      }
      async function loadLibrary(){
        const seq=++librarySeq;const d=await hubCall('ms_list_skills',{query:$("ms-library-search").value,...($("ms-library-engine").value?{engine:$("ms-library-engine").value}:{}),...($('ms-library-favorites').checked?{ids:skillFavorites}:{}),offset:libraryOffset,limit:12});
        if(seq!==librarySeq)return;libraryRows=d.skills||[];libraryTotal=d.totalMatches||0;libraryLoaded=true;renderLibrary();
      }
      bind('ms-library-load',loadLibrary);bind('ms-library-prev',async()=>{libraryOffset=Math.max(0,libraryOffset-12);await loadLibrary();});bind('ms-library-next',async()=>{libraryOffset+=12;await loadLibrary();});
      let searchTimer;for(const id of ['ms-library-search','ms-library-engine'])$(id)?.addEventListener(id.endsWith('engine')?'change':'input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{libraryOffset=0;guard(loadLibrary)();},250);});
      $('ms-library-favorites')?.addEventListener('change',()=>{libraryOffset=0;guard(loadLibrary)();});if(libraryLoaded)renderLibrary();
      bind('ms-skill-create',async()=>{const name=$('ms-skill-name').value.trim(),instructions=$('ms-skill-instructions').value;const id='custom-'+(name.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,45)||'workflow');await install({id,name,instructions,engine:$('ms-skill-engine').value,description:instructions.slice(0,150)});});

      bind("ms-skill-install",()=>install(JSON.parse($("ms-skill-json").value)));
      bind("ms-skill-publish",async()=>{const skill=MSStudio.validateSkill(JSON.parse($("ms-skill-json").value));await hubCall("ms_workshop",{action:"publish",skill,client:hubClient});status("Published.");await browse();});
      async function browse(){const data=await hubCall("ms_workshop",{action:"list",query:$("ms-workshop-search").value,offset:workshopOffset,client:hubClient});hubItems=data.items||[];$("ms-workshop-results").innerHTML=hubItems.map((x,i)=>`<article class="ms-hub-card"><b>${MSStudio.escape(x.name)}</b><p>${MSStudio.escape(x.description)}</p><small>★ ${x.stars||0} · ${Number(x.rating||0).toFixed(1)}/5 (${x.ratings||0} ratings)</small><div class="zs-menu-actions"><button class="zs-mini-action" data-hub-install="${i}">Install</button><button class="zs-mini-action" data-hub-star="${i}">☆ Star</button><select aria-label="Rating for ${MSStudio.escape(x.name)}" data-hub-rating="${i}"><option value="">Rate</option>${[1,2,3,4,5].map(n=>`<option>${n}</option>`).join("")}</select></div><input data-hub-feedback="${i}" class="zs-mcp-field" maxlength="1000" placeholder="Feedback" aria-label="Feedback for ${MSStudio.escape(x.name)}"><button class="zs-mini-action" data-hub-send-feedback="${i}">Post feedback</button><details><summary>Read feedback &amp; instructions</summary><pre>${MSStudio.escape(x.instructions)}</pre>${(x.feedback||[]).map(f=>`<p>${MSStudio.escape(f.text)}</p>`).join("")}</details></article>`).join("")||"No skills found.";status(`${data.scope||"Local"} workshop · ${data.total||0} skills`);$("ms-workshop-prev").disabled=workshopOffset===0;$("ms-workshop-next").disabled=!data.hasMore;
        $("ms-workshop-results").querySelectorAll("[data-hub-install]").forEach(b=>b.addEventListener("click",()=>install(hubItems[Number(b.dataset.hubInstall)]).catch(e=>status(e.message))));
        const review=async(i,patch)=>{await hubCall("ms_workshop",{action:"review",id:hubItems[i].id,client:hubClient,...patch});await browse();};
        $("ms-workshop-results").querySelectorAll("[data-hub-star]").forEach(b=>b.addEventListener("click",()=>review(Number(b.dataset.hubStar),{star:true}).catch(e=>status(e.message))));
        $("ms-workshop-results").querySelectorAll("[data-hub-rating]").forEach(b=>b.addEventListener("change",()=>{if(b.value)review(Number(b.dataset.hubRating),{rating:Number(b.value)}).catch(e=>status(e.message));}));
        $("ms-workshop-results").querySelectorAll("[data-hub-send-feedback]").forEach(b=>b.addEventListener("click",()=>{const i=Number(b.dataset.hubSendFeedback);review(i,{feedback:$("ms-workshop-results").querySelector(`[data-hub-feedback="${i}"]`).value}).catch(e=>status(e.message));}));
      }
      bind("ms-workshop-refresh",async()=>{workshopOffset=0;await browse();});bind("ms-workshop-prev",async()=>{workshopOffset=Math.max(0,workshopOffset-20);await browse();});bind("ms-workshop-next",async()=>{workshopOffset+=20;await browse();});
      bind("ms-workshop-connect",async()=>{await hubCall("ms_workshop_connection",{url:$("ms-workshop-url").value,token:$("ms-workshop-token").value});$("ms-workshop-token").value="";await browse();});
      bind("ms-workshop-local",async()=>{await hubCall("ms_workshop_connection",{url:"",token:""});await browse();});
      function paintInstalled(){
        const host=$("ms-installed-skills");if(!host)return;const e=MSStudio.escape,active=activeCustomSkills();
        host.innerHTML=customSkills.map(x=>`<article class="ms-installed-card"><div class="ms-work-card-head"><label><input type="checkbox" data-skill-enabled="${e(x.id)}" ${x.enabled!==false?'checked':''}> <b>${e(x.name)}</b></label><span class="ms-status-pill">${x.confirmed?'User verified':'Candidate'}</span></div><small>${e(x.engine||'general')} · ${x.scope?(x.scope===skillScopeKey()?'This project':'Another project'):'All matching projects'} · ${active.some(a=>a.id===x.id)?'Applied to prompts':'Inactive here'}</small><p>${e(x.description||x.instructions.slice(0,160))}</p><div class="ms-toolbar"><button type="button" class="zs-mini-action" data-skill-preview="${e(x.id)}">Read / export</button><button type="button" class="zs-mini-action" data-skill-scope="${e(x.id)}">${x.scope?'Use globally':'Use here only'}</button><button type="button" class="zs-mini-action" data-skill-verified="${e(x.id)}">${x.confirmed?'Mark candidate':'Mark user verified'}</button><button type="button" class="zs-mini-action" data-uninstall-skill="${e(x.id)}">Remove</button></div></article>`).join("")||'<div class="ms-empty-state">Install a method for your project. Only enabled, matching skills are sent.</div>';
        $('ms-skill-selection').textContent=active.length+' of '+customSkills.length+' installed workflows match this context. These guide the model in context; they do not train its weights.';
        const save=async()=>{studioSettingsDirty=true;await chrome.storage.local.set({msCustomSkills:customSkills});paintInstalled();};
        host.querySelectorAll('[data-skill-enabled]').forEach(b=>b.onchange=async()=>{customSkills=customSkills.map(x=>x.id===b.dataset.skillEnabled?{...x,enabled:b.checked}:x);await save();});
        host.querySelectorAll('[data-skill-scope]').forEach(b=>b.onclick=async()=>{customSkills=customSkills.map(x=>x.id===b.dataset.skillScope?{...x,scope:x.scope?'':skillScopeKey()}:x);await save();});
        host.querySelectorAll('[data-skill-verified]').forEach(b=>b.onclick=async()=>{customSkills=customSkills.map(x=>x.id===b.dataset.skillVerified?{...x,confirmed:!x.confirmed}:x);await save();});
        host.querySelectorAll('[data-skill-preview]').forEach(b=>b.onclick=()=>{const skill=customSkills.find(x=>x.id===b.dataset.skillPreview);$('ms-skill-json').value=JSON.stringify({...skill,scope:''},null,2);hubDrafts['ms-skill-json']=$('ms-skill-json').value;menuEl.querySelector('.ms-skill-import').open=true;$('ms-skill-json').scrollIntoView({block:'center'});status('Copy the JSON to export. Local project identity is excluded.');});
        host.querySelectorAll("[data-uninstall-skill]").forEach(button=>button.onclick=async()=>{button.disabled=true;try{await hubCall("ms_workshop",{action:"uninstall",id:button.dataset.uninstallSkill,client:hubClient});customSkills=customSkills.filter(x=>x.id!==button.dataset.uninstallSkill);studioSettingsDirty=true;await chrome.storage.local.set({msCustomSkills:customSkills});paintInstalled();status("Removed. The next task receives the updated skill selection.");}catch(err){button.disabled=false;status(err.message);}});
      }
      paintInstalled();
      $('ms-skill-file')?.addEventListener('change',async event=>{try{const file=event.target.files?.[0];if(!file)return;if(file.size>32000)throw Error('Import one skill, up to 32 KB.');const skill=MSStudio.importSkill(await file.text(),file.name.replace(/\.[^.]+$/,''));$('ms-skill-name').value=skill.name;$('ms-skill-instructions').value=skill.instructions;$('ms-skill-engine').value=skill.engine;$('ms-skill-json').value=JSON.stringify(skill,null,2);for(const id of ['ms-skill-name','ms-skill-instructions','ms-skill-engine','ms-skill-json'])hubDrafts[id]=$(id).value;status('Imported for review. Choose a scope, then install explicitly.');}catch(err){status(err.message);}finally{event.target.value='';}});
      let capabilities=[];
      const renderCaps=()=>{const q=($("ms-cap-filter").value||"").toLowerCase();$("ms-cap-list").innerHTML=capabilities.filter(x=>(x.name+" "+x.description).toLowerCase().includes(q)).map(x=>`<div class="ms-hub-card"><b>${MSStudio.escape(x.name)}</b><small>${MSStudio.escape(x.kind)}</small><p>${MSStudio.escape(x.description)}</p></div>`).join("")||"No matching capabilities.";};
      bind("ms-cap-refresh",async()=>{const tools=await bg({type:"list_tools"});if(!tools?.ok)throw Error(tools?.error||"Bridge offline");const data=await hubCall("ms_capability_inventory");capabilities=[...(tools.tools||[]).map(t=>({name:t.name,description:t.description||"",kind:"tool · "+(t.server||"bridge")})),...(data.skills||[]).map(t=>({name:t.id+" · "+t.name,description:t.description||"",kind:"instruction skill · "+(t.engine||"general")}))];renderCaps();});$("ms-cap-filter")?.addEventListener("input",renderCaps);

      bind('ms-sessions-refresh',async()=>{await board();await refreshCoworkSessions();});
      const owner=()=>P.id+":"+hubWorker;
      function renderBoard(){
        const host=$('ms-cowork-board');if(!host)return;const e=MSStudio.escape,q=$('ms-cowork-search').value.toLowerCase(),filter=$('ms-cowork-filter').value;
        const project=$('ms-cowork-project-filter').value,sort=$('ms-cowork-sort').value;
        const rows=coworkTasks.filter(t=>(!project||t.project===project)&&(t.title+' '+t.detail+' '+t.note+' '+(t.blocker||'')).toLowerCase().includes(q)&&(filter==='all'||filter==='mine'&&t.owner===owner()||filter==='open'&&t.status==='open'||filter==='done'&&t.status==='done'||filter==='blocked'&&(t.blocker||t.blockedBy?.length)));
        const rank={high:0,normal:1,low:2};rows.sort((a,b)=>sort==='title'?a.title.localeCompare(b.title):sort==='updated'?b.updated-a.updated:(rank[a.priority]??1)-(rank[b.priority]??1)||b.updated-a.updated);
        const scoped=coworkTasks.filter(x=>!project||x.project===project),completed=scoped.filter(x=>x.status==='done').length,checks=scoped.reduce((n,x)=>n+(x.checks?.length||0),0),verified=scoped.reduce((n,x)=>n+(x.verified_checks?.length||0),0);
        $('ms-cowork-counts').innerHTML=`<div><b>${scoped.length-completed} task${scoped.length-completed===1?'':'s'} remaining</b><span>${completed} / ${scoped.length} completed</span></div><progress max="${Math.max(1,scoped.length)}" value="${completed}" aria-label="Completed shared tasks"></progress><small>${scoped.filter(x=>x.status==='working').length} in progress · ${scoped.filter(x=>x.blocker||x.blockedBy?.length).length} blocked / waiting · ${verified} / ${checks} acceptance checks reported. Completion is based on task evidence, not estimated AI progress.</small>`;
        host.innerHTML=['open','working','done'].map(state=>`<div class="ms-task-column"><h3>${({open:'Ready & waiting',working:'In progress',done:'Completed'})[state]}</h3>${rows.filter(t=>t.status===state).map(t=>{const mine=t.owner===owner(),blocked=t.blockedBy?.length,lease=t.active?Math.max(1,Math.ceil((t.lease-Date.now()/1000)/60)):0;return `<article class="ms-work-card" data-task-id="${e(t.id)}"><div class="ms-work-card-head"><b>${e(t.title)}</b><span class="ms-status-pill" data-priority="${e(t.priority||'normal')}">${e(t.priority||'normal')}</span></div><small>${e(t.project||'default')} · ${mine?'You':e(t.owner||'Unassigned')}${lease?' · '+lease+'m lease':t.expired?' · lease expired':''}</small><p>${e(t.detail)}</p>${(t.resources||[]).map(r=>`<code class="ms-resource-chip">${e(r)}</code>`).join('')||'<small>No explicit resource scope</small>'}${blocked?`<p class="ms-task-blocked">Waiting for ${blocked} dependency task(s): ${e(t.blockedBy.map(id=>coworkTasks.find(x=>x.id===id)?.title||id).join(', '))}</p>`:''}${t.blocker?`<p class="ms-task-blocked">Blocker: ${e(t.blocker)}</p>`:''}${t.checks?.length?`<div class="ms-task-check-summary">${(t.verified_checks||[]).length} / ${t.checks.length} acceptance checks reported</div>`:''}<details><summary>Progress, evidence &amp; history</summary><small>Task ID: ${e(t.id)}</small><p>${e(t.note||'No progress reported yet.')}</p>${(t.checks||[]).map((check,index)=>`<label class="ms-task-check"><input type="checkbox" data-task-check="${e(t.id)}" value="${index}" ${(hubDrafts['checks:'+t.id]||t.verified_checks||[]).includes(index)?'checked':''} ${!mine||!t.active?'disabled':''}><span>${e(check)}</span></label>`).join('')}<label class="zs-pref-label">Current blocker (clear when resolved)</label><input class="zs-mcp-field" data-task-blocker="${e(t.id)}" maxlength="2000" value="${e(hubDrafts['blocker:'+t.id]??t.blocker??'')}" ${!mine||!t.active?'disabled':''}><label class="zs-pref-label">Changes and verification evidence</label><textarea data-task-note="${e(t.id)}" rows="3" placeholder="What changed, verified evidence or a blocker">${e(hubDrafts['note:'+t.id]??t.note??'')}</textarea><div class="ms-toolbar"><button type="button" class="zs-mini-action" data-task-action="update" data-id="${e(t.id)}" ${!mine||!t.active?'disabled':''}>Save progress</button><button type="button" class="zs-mini-action" data-task-action="history" data-id="${e(t.id)}">History</button></div><pre data-task-history="${e(t.id)}"></pre></details><div class="ms-toolbar">${state==='done'?`<button type="button" class="zs-mini-action" data-task-action="reopen" data-id="${e(t.id)}">Reopen</button>`:`<button type="button" class="zs-mini-action" data-task-action="claim" data-id="${e(t.id)}" ${t.active||blocked?'disabled':''}>${t.expired?'Reclaim & work':'Claim & work here'}</button>${state==='open'?`<button type="button" class="zs-mini-action" data-task-action="edit" data-id="${e(t.id)}">Edit scope</button>`:''}<button type="button" class="zs-mini-action" data-task-action="complete" data-id="${e(t.id)}" ${!mine||!t.active?'disabled':''}>Complete</button><button type="button" class="zs-mini-action" data-task-action="release" data-id="${e(t.id)}" ${!mine||!t.active?'disabled':''}>Release</button>`}</div></article>`;}).join('')||'<div class="ms-empty-state">No tasks here.</div>'}</div>`).join('');
        host.querySelectorAll('[data-task-note]').forEach(input=>input.oninput=()=>hubDrafts['note:'+input.dataset.taskNote]=input.value);
        host.querySelectorAll('[data-task-blocker]').forEach(input=>input.oninput=()=>hubDrafts['blocker:'+input.dataset.taskBlocker]=input.value);
        host.querySelectorAll('[data-task-check]').forEach(input=>input.onchange=()=>{hubDrafts['checks:'+input.dataset.taskCheck]=[...host.querySelectorAll(`[data-task-check="${input.dataset.taskCheck}"]:checked`)].map(x=>Number(x.value));});
        host.querySelectorAll('[data-task-action]').forEach(button=>button.onclick=async()=>{button.disabled=true;try{
          const id=button.dataset.id,action=button.dataset.taskAction,task=coworkTasks.find(t=>t.id===id),note=host.querySelector(`[data-task-note="${id}"]`)?.value||'';
          if(action==='edit'){
            coworkEditingId=id;for(const [field,value]of [['title',task.title],['detail',task.detail],['project',task.project],['priority',task.priority],['resources',(task.resources||[]).join('\n')],['checks',(task.checks||[]).join('\n')],['deps',(task.depends_on||[]).join(', ')]]){$('ms-cowork-'+field).value=value;hubDrafts['ms-cowork-'+field]=value;}
            $('ms-cowork-add').textContent='Save changes';$('ms-cowork-cancel-edit').hidden=false;$('ms-cowork-composer').open=true;$('ms-cowork-composer').scrollIntoView({block:'start'});return;
          }
          if(action==='history'){const d=await hubCall('ms_cowork',{action,id});host.querySelector(`[data-task-history="${id}"]`).textContent=d.events.map(x=>new Date(x.at*1000).toLocaleString()+' · '+x.action+' · '+x.actor+'\n'+x.note).join('\n\n');return;}
          if(action==='complete'&&!note.trim()&&!task.note.trim())throw Error('Add progress/evidence before marking this task complete.');
          if(action==='claim'&&(!A.started||A.running||A.starting||A.injecting||P.editorText()?.trim()))throw Error('Start an idle session and clear its draft before claiming.');
          const claimChat=coworkContext();const proof=['update','complete','release'].includes(action)?{note,verified_checks:[...host.querySelectorAll(`[data-task-check="${id}"]:checked`)].map(x=>Number(x.value)),blocker:host.querySelector(`[data-task-blocker="${id}"]`)?.value||''}:{};const d=await hubCall('ms_cowork',{action,id,owner:owner(),...proof});
          if(['update','complete','release','reopen'].includes(action))for(const prefix of ['note:','checks:','blocker:'])delete hubDrafts[prefix+id];
          if(action==='claim'&&coworkContext()!==claimChat){await hubCall('ms_cowork',{action:'release',id,owner:owner(),note:'Chat changed before delivery.'});throw Error('Chat changed; claim released.');}
          if(action==='claim'){
            const taskChat=P.conversationKey();
            const result=await runStudioPrompt(`[MULTI-SCRIPT CO-WORK TASK ${id}]\n${d.task.title}\n${d.task.detail}\nProject: ${d.task.project}\nAcceptance checks (zero-based): ${JSON.stringify(d.task.checks)}\nOwned resources: ${JSON.stringify(d.task.resources)}\nOwner: ${owner()}\nRead the shared board, preserve adjacent interfaces, work within the assigned scope and report progress/evidence using ms_cowork update (this renews the lease). Supply verified_checks indices only after checking those results, and record blocker when work cannot continue. Complete requires all acceptance checks, a concrete evidence note and no blocker. Never infer overall completion from a successful tool chip. The task board is coordination, not a filesystem lock.`);
            if(!result?.ok){if(!A.sendUnconfirmed)await hubCall('ms_cowork',{action:'release',id,owner:owner(),note:'Task send was not accepted; released for retry.'});throw Error('Task delivery was not confirmed. Inspect this chat before retrying.');}
            if(P.conversationKey()!==taskChat)status('Task accepted in its original chat.','ms-cowork-status');
          }
          await board();status('Board updated.','ms-cowork-status');
        }catch(err){status(err.message,'ms-cowork-status');}finally{if(button.isConnected)button.disabled=false;}});
      }
      async function board(){const d=await hubCall('ms_cowork',{action:'list'});coworkTasks=d.tasks||[];const select=$('ms-cowork-project-filter'),selected=select.value||hubDrafts['ms-cowork-project-filter']||'',projects=[...new Set(coworkTasks.map(x=>x.project||'default'))].sort();select.innerHTML='<option value="">All projects</option>'+projects.map(x=>`<option value="${MSStudio.escape(x)}">${MSStudio.escape(x)}</option>`).join('');select.value=projects.includes(selected)?selected:'';renderBoard();}
      bind('ms-open-progress',()=>runMonitor?.open('progress'));bind('ms-open-phone',()=>runMonitor?.open('phone'));
      bind('ms-cowork-refresh',board);bind('ms-cowork-add',async()=>{await hubCall('ms_cowork',{action:coworkEditingId?'edit':'create',...(coworkEditingId?{id:coworkEditingId}:{}),title:$('ms-cowork-title').value,detail:$('ms-cowork-detail').value,project:$('ms-cowork-project').value,priority:$('ms-cowork-priority').value,checks:$('ms-cowork-checks').value.split('\n').map(x=>x.trim()).filter(Boolean),resources:$('ms-cowork-resources').value.split('\n').map(x=>x.trim()).filter(Boolean),depends_on:$('ms-cowork-deps').value.split(',').map(x=>x.trim()).filter(Boolean)});for(const id of ['ms-cowork-title','ms-cowork-detail','ms-cowork-resources','ms-cowork-deps','ms-cowork-checks']){$(id).value='';hubDrafts[id]='';}coworkEditingId=null;$('ms-cowork-add').textContent='Add task';$('ms-cowork-cancel-edit').hidden=true;$('ms-cowork-composer').open=false;await board();});
      bind('ms-cowork-cancel-edit',async()=>{coworkEditingId=null;for(const id of ['ms-cowork-title','ms-cowork-detail','ms-cowork-resources','ms-cowork-deps','ms-cowork-checks']){$(id).value='';hubDrafts[id]='';}$('ms-cowork-add').textContent='Add task';$('ms-cowork-cancel-edit').hidden=true;});
      for(const id of ['ms-cowork-project-filter','ms-cowork-sort'])$(id)?.addEventListener('change',renderBoard);$('ms-cowork-search')?.addEventListener('input',renderBoard);$('ms-cowork-filter')?.addEventListener('change',renderBoard);renderBoard();
      $('ms-followup-enabled')?.addEventListener('change',e=>coworkQueue.setEnabled(e.target.checked));
      bind('ms-followup-add',async()=>{const text=$('ms-followup-text').value,kind=$('ms-followup-kind').value;const result=followupEditingId?coworkQueue.edit(followupEditingId,text,kind):coworkQueue.enqueue(text,kind);if(!result.ok)throw Error(result.error);followupEditingId=null;$('ms-followup-text').value='';hubDrafts['ms-followup-text']='';$('ms-followup-add').textContent='Queue request';$('ms-followup-cancel').hidden=true;});
      bind('ms-followup-cancel',async()=>{followupEditingId=null;$('ms-followup-text').value='';hubDrafts['ms-followup-text']='';$('ms-followup-add').textContent='Queue request';$('ms-followup-cancel').hidden=true;});
      if(followupEditingId){$('ms-followup-add').textContent='Save request';$('ms-followup-cancel').hidden=false;}
      bind('ms-followup-pause',async()=>coworkQueue.pause());bind('ms-followup-resume',async()=>{const result=coworkQueue.resume();if(!result.ok)throw Error(result.error);});paintFollowups();
      for(const id of ['ms-followup-text','ms-followup-kind','ms-skill-scope','ms-library-search','ms-library-engine','ms-library-goal','ms-cowork-title','ms-cowork-detail','ms-cowork-checks','ms-cowork-project','ms-cowork-project-filter','ms-cowork-sort','ms-cowork-priority','ms-cowork-resources','ms-cowork-deps','ms-skill-name','ms-skill-engine','ms-skill-instructions','ms-skill-json']){
        const input=$(id);if(!input)continue;if(hubDrafts[id]!==undefined)input.value=hubDrafts[id];input.addEventListener('input',()=>hubDrafts[id]=input.value);input.addEventListener('change',()=>hubDrafts[id]=input.value);
      }
      bind("ms-vani-check",async()=>{$("ms-vani-status").textContent=JSON.stringify(P.selfTest?P.selfTest():{ready:!!P.getEditor()},null,2);});
    }

    function buildMenu() {
      const prevPane = menuEl && menuEl.querySelector ? menuEl.querySelector("#zs-pane") : null;
      const prevScroll = prevPane ? prevPane.scrollTop : 0;
      const prevFocusQ = !!(menuEl && menuEl.querySelector && document.activeElement && document.activeElement.id === "zs-menu-q");
      const here = (P.displayName || "").toLowerCase();
      const hostOf = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return ""; } };
      let sites = "";
      let siteGroup = "";
      for (const s of [...AI_SITES.filter(x => x.group !== "multi"), ...AI_SITES.filter(x => x.group === "multi")]) {
        const group = s.group === "multi" ? "Multi-model providers" : "AI providers";
        if (group !== siteGroup) { sites += `<div class="zs-setting-title">${group}</div>`; siteGroup = group; }
        const current = s.name.toLowerCase() === here;
        const bm = (ZS.PROVIDER_BENCHMARKS || []).find((b) => b.name.toLowerCase() === s.name.toLowerCase());
        const desc = s.description || (bm && bm.note) || "";
        const label = `<span class="zs-site-name"><span>${s.name}</span><span class="zs-site-host">${hostOf(s.url)}</span>${desc ? `<span class="zs-site-description">${desc}</span>` : ""}</span>`;
        sites += current
          ? `<div class="zs-site-opt zs-site-here">${label}<span class="zs-site-badge">active</span></div>`
          : `<button class="zs-site-opt" data-u="${s.url}">${label}<span class="zs-site-go">&rarr;</span></button>`;
      }
      const benchEscape=MSStudio.escape;
      const benchmarkRows = [...(ZS.PROVIDER_BENCHMARKS||[])].sort((a,b)=>(b.id===P.id)-(a.id===P.id)||a.name.localeCompare(b.name)).map(b=>`<article class="ms-bench-card${b.id===P.id?' active':''}" data-provider="${benchEscape(b.id)}" data-bench-name="${benchEscape((b.name+' '+b.id).toLowerCase())}"><div class="ms-bench-identity"><b>${benchEscape(b.name)}</b><small>${b.id===P.id?'Current provider':'Local JSON tool transport'}</small></div><span class="zs-provider-badge">Fixture checked</span><p>${benchEscape(b.note)}</p><details><summary>Evidence and limits</summary><p>${benchEscape(b.evidence)}. ${benchEscape(b.live)}</p></details></article>`).join('');
      const benchmarksHtml = `<section class="zs-menu-sec ms-provider-evidence" data-zs-tab="sites"><div class="zs-sec-label"><span>Provider benchmarks</span><span class="zs-provider-badge">Compatibility evidence</span></div><p class="ms-section-intro">Choose with evidence.</p><p class="zs-menu-note">Compare adapter coverage and check this chat’s readiness. Fixture results test the extension’s transport; they do not rank model intelligence or predict speed, quality, quotas or uptime.</p><div class="ms-bench-toolbar"><input id="ms-bench-search" class="zs-mcp-field" type="search" placeholder="Find a provider" aria-label="Find benchmark provider"><select id="ms-bench-filter" class="zs-mcp-field" aria-label="Filter benchmark providers"><option value="all">All providers</option><option value="current">Current provider</option></select></div><div class="ms-bench-local"><div><b>Check this chat</b><small>Composer, send control, context and bridge. Sends no message.</small></div><button id="ms-bench-check" type="button" class="zs-mini-action">Run local check</button></div><p id="ms-bench-result" class="zs-menu-note" role="status"></p><p id="ms-bench-count" class="zs-menu-note"></p><div class="ms-bench-list">${benchmarkRows}</div><p class="zs-menu-note">Live account coverage remains separate. Test the model and plan you actually use before relying on unattended work.</p></section>`;
      const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
      const mergedServers = mergedMcpServers();
      // Render every configured server from live bridge state. Bundled servers
      // are protected from accidental removal; addons retain a remove action.
      const liveServers = (A.bridge && A.bridge.servers) || [];
      const engineStates = (A.bridge && A.bridge.engines) || [];
      const allServers = [];
      const seenServers = new Set();
      for (const sv of liveServers) { allServers.push({ ...sv, name: (customMcpServers.find((x) => x.id === sv.id) || {}).name || sv.id }); seenServers.add(sv.id); }
      for (const sv of mergedServers) if (!seenServers.has(sv.id)) allServers.push(sv);
      if (!allServers.length) allServers.push({ id: "roblox", name: "Roblox Studio", alive: undefined, tools: 0 });
      let mcpList = "";
      allServers.forEach((sv) => {
        const engine = engineStates.find((e) => e.id === sv.id);
        const connected = engine && engine.connected;
        const healthClass = sv.enabled === false ? "off" : sv.alive === true ? (connected === false ? "warn" : "on") : sv.alive === false ? "off" : "unknown";
        const stateText = sv.enabled === false ? "switched off" : sv.alive === false ? "server offline" : connected === true ? "editor connected" : connected === false ? "editor not connected" : sv.alive === true ? "server ready" : "status unknown";
        const title = sv.id === "roblox" ? "Roblox Studio" : sv.id === "unity" ? "Unity" : sv.id === "godot" ? "Godot" : (sv.name || sv.id);
        const builtIn = BUILTIN_SERVERS.has(sv.id);
        mcpList += `<div class="zs-mcp-item${builtIn ? " zs-mcp-item-builtin" : ""}">
          <span class="zs-mcp-health zs-mcp-health-${healthClass}"></span>
          <div class="zs-mcp-info"><span class="zs-mcp-name">${esc(title)}${builtIn ? '<span class="zs-builtin-badge">built-in</span>' : ""}</span><span class="zs-mcp-url">${stateText} · ${sv.tools || 0} tools</span></div>
          ${builtIn ? "" : `<button class="zs-mcp-remove" data-id="${esc(sv.id)}" title="Remove addon">✕</button>`}
        </div>`;
      });
      const connectedNames = engineStates.filter((e) => e.connected === true).map((e) => e.id);
      // 6.27.1: per-engine setup guides rendered from ZSExtras.ENGINE_GUIDES.
      let engineGuidesHtml = `<div class="zs-menu-note">Setup guides unavailable - reload the extension once.</div>`;
      if (typeof ZSExtras !== "undefined" && Array.isArray(ZSExtras.ENGINE_GUIDES)) {
        engineGuidesHtml = ZSExtras.ENGINE_GUIDES.map((g) => `<div class="zs-guide" data-guide-id="${esc(g.id)}">
          <button type="button" class="zs-guide-head" data-guide-toggle="${esc(g.id)}" aria-expanded="false"><b>${esc(g.name)}</b><span class="zs-provider-badge">${esc(g.badge)}</span><span class="zs-guide-caret">▸</span></button>
          <div class="zs-guide-body" hidden>
            <div class="zs-menu-note">${esc(g.tagline)}</div>
            <div class="zs-guide-needs"><b>You need:</b><ul>${g.needs.map((n) => `<li>${esc(n)}</li>`).join("")}</ul></div>
            <ol class="zs-guide-steps">${g.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
            <div class="zs-menu-note"><b>Prove it works:</b> ${esc(g.verify)}</div>
            <div class="zs-menu-note"><b>Good to know:</b> ${esc(g.tip)}</div>
            <div class="zs-menu-actions">
              ${g.fill ? `<button type="button" class="zs-mini-action" data-guide-fill="${esc(g.id)}">Use bundled launcher</button>` : ""}
              <button type="button" class="zs-mini-action" data-guide-copy="${esc(g.id)}">Copy checklist</button>
            </div>
          </div>
        </div>`).join("");
      }
      const nextStep = !(A.bridge && A.bridge.connected) ? "Start the Multi-Script bridge, then refresh." : connectedNames.length ? "Everything is ready — start a new session or continue building." : "Bridge connected. Open Roblox Studio, Unity, or Godot to attach an editor.";
      const overviewHtml = `<section class="zs-menu-sec" data-zs-tab="interface">
        <div class="zs-overview">
          <div><span class="zs-overview-k">Provider</span><b>${esc(P.displayName || P.id)}</b></div>
          <div><span class="zs-overview-k">Bridge</span><b>${A.bridge && A.bridge.connected ? "Connected" : "Offline"}</b></div>
          <div><span class="zs-overview-k">Engines</span><b>${connectedNames.length ? esc(connectedNames.join(", ")) : "None"}</b></div>
          <div><span class="zs-overview-k">Tools</span><b>${A.toolList.length}</b></div>
        </div>
        <div class="zs-next-step"><b>Next step</b><span>${esc(nextStep)}</span></div>
      </section>`;
      const appearanceHtml = `<section class="zs-menu-sec zs-appearance-lab" data-zs-tab="appearance">
        <div class="zs-sec-label"><span>Appearance studio</span><span class="zs-provider-badge">live preview</span></div>
        <div class="zs-custom-preview"><span class="zs-custom-preview-icon">${esc(menuPrefs.brandIcon || "✦")}</span><div><b>${esc(menuPrefs.brandName || "Multi-Script")}</b><span>${esc(menuPrefs.tagline || "Create without limits")}</span></div><i></i></div>
        <div class="zs-setting-title">Identity</div>
        <div class="zs-brand-grid"><input id="ms-brand-icon" maxlength="3" value="${esc(menuPrefs.brandIcon || "✦")}" aria-label="Brand icon"><input id="ms-brand-name" maxlength="28" value="${esc(menuPrefs.brandName || "Multi-Script")}" placeholder="Menu name"><input id="ms-brand-tagline" maxlength="60" value="${esc(menuPrefs.tagline || "")}" placeholder="Personal tagline"></div>
        <div class="zs-setting-title">Theme</div>
        ${(()=>{const SPECIAL=["fnaf","scream","myers","slender","jason"];const all=[["auto","Auto"],["midnight","Midnight"],["graphite","Graphite"],["frost","Frost"],["mono","Mono"],["ink","Ink"],["synthwave","Synthwave"],["forest","Forest"],...(typeof ZSExtras!=="undefined"?ZSExtras.EXTRA_THEMES.map((t)=>[t[0],t[1]]):[])];const opt=([id,label])=>`<button class="zs-theme-opt${menuPrefs.theme===id?" active":""}" data-theme="${id}"><i></i><b>${label}</b></button>`;return `<div class="zs-theme-grid">${all.filter(([id])=>!SPECIAL.includes(id)).map(opt).join("")}</div><div class="zs-setting-title zs-special-title">Special themes <span class="zs-provider-badge">animated scenes</span></div><div class="zs-theme-grid zs-theme-grid-special">${all.filter(([id])=>SPECIAL.includes(id)).map(opt).join("")}</div>`;})()}
        <div class="zs-setting-title">Accent</div>
        <div class="zs-accent-grid">${["#f4f4f7","#d8d8e2","#a9a9b6","#7c6cf2","#2aa981","#3182ce","#d977a8","#e38b3c","#e05252","#22c7d6"].map((c) => `<button class="zs-accent-opt${menuPrefs.accent === c ? " active" : ""}" data-accent="${c}" style="--swatch:${c}" aria-label="Use ${c}"></button>`).join("")}<label class="zs-color-custom" title="Custom accent"><input id="ms-custom-accent" type="color" value="${esc(menuPrefs.accent)}"><span>+</span></label></div>
        <div class="zs-setting-title">Layout</div>
        <label class="zs-pref-label">Density</label><div class="zs-pref-grid zs-pref-grid-3">${[["compact","Compact"],["comfortable","Comfort"],["spacious","Spacious"]].map(([id,label]) => `<button class="zs-pref-opt${menuPrefs.density===id?" active":""}" data-density="${id}">${label}</button>`).join("")}</div>
        <label class="zs-pref-label">Width</label><div class="zs-pref-grid zs-pref-grid-4">${[["small","Small"],["medium","Medium"],["wide","Wide"],["studio","Studio"]].map(([id,label]) => `<button class="zs-pref-opt${menuPrefs.width===id?" active":""}" data-width="${id}">${label}</button>`).join("")}</div>
        <label class="zs-pref-label">Scale</label><div class="zs-pref-grid zs-pref-grid-3">${[["90","90%"],["100","100%"],["115","115%"]].map(([id,label]) => `<button class="zs-pref-opt${menuPrefs.scale===id?" active":""}" data-scale="${id}">${label}</button>`).join("")}</div>
        <div class="zs-setting-title">Personality</div>
        <div class="zs-pref-grid zs-pref-grid-3">${[["system","System"],["rounded","Rounded"],["mono","Mono"]].map(([id,label]) => `<button class="zs-pref-opt${menuPrefs.font===id?" active":""}" data-font="${id}">${label}</button>`).join("")}</div>
        <label class="zs-pref-label">Corners</label><div class="zs-pref-grid zs-pref-grid-3">${[["sharp","Sharp"],["soft","Soft"],["round","Round"]].map(([id,label]) => `<button class="zs-pref-opt${menuPrefs.radius===id?" active":""}" data-radius="${id}">${label}</button>`).join("")}</div>
        <label class="zs-pref-label">Backdrop</label><div class="zs-pref-grid zs-pref-grid-3">${[["solid","Solid"],["glass","Glass"],["mesh","Mesh"]].map(([id,label]) => `<button class="zs-pref-opt${menuPrefs.backdrop===id?" active":""}" data-backdrop="${id}">${label}</button>`).join("")}</div>
        <label class="zs-pref-label">Motion</label><div class="zs-pref-grid zs-pref-grid-3">${[["full","Full"],["reduced","Reduced"],["none","None"]].map(([id,label]) => `<button class="zs-pref-opt${menuPrefs.motion===id?" active":""}" data-motion="${id}">${label}</button>`).join("")}</div>
        <div class="zs-pref-row"><label><input id="ms-show-overview" type="checkbox" ${menuPrefs.showOverview ? "checked" : ""}> Show status overview</label><select id="ms-default-tab">${[["home","Home"],["bar","Chat bar"],["agent","Agent"],["look","Look"],["tools","Tools"],["engines","Engines"],["sites","AI sites"],["help","Help"]].concat(P.id === "notion" ? [["notion","Notion"]] : []).map(([v, l]) => `<option value="${v}">Open on ${l}</option>`).join("")}</select></div>
        <div class="zs-menu-actions"><button id="ms-save-identity" class="zs-mini-action">Save identity</button><button id="ms-reset-menu" class="zs-mini-action">Reset appearance</button></div>
      </section>`;
      // ── Prompt enhancer ────────────────────────────────────────────────
      // Local, deterministic, no API call. The panel shows a live preview of the
      // ACTUAL enhancement of the last request the user typed, so the toggle is
      // not a leap of faith - they see exactly what would be sent.
      const enh = enhanceSettings;
      const enhPreviewSample = `make the door open when the player touches it`;
      const enhPreview = ZSEnhance.enhance(enhPreviewSample, { engines: A.engines && A.engines.length ? A.engines : (A.bridge && A.bridge.connected ? [P.id] : []) }, enh);
      const enhanceHtml = `<section class="zs-menu-sec zs-enhance-sec" data-zs-tab="studio">
        <div class="zs-sec-label"><span>Prompt enhancer</span><span class="zs-provider-badge">local, no extra cost</span></div>
        <div class="zs-menu-note">Turns a short request into a precise brief ${esc(P.displayName || P.id)} can execute: the goal, the constraints your words imply, the connected-engine facts, and what "done" means. Your own wording is always kept and sent first - this only <b>adds</b> to it, offline, with rules.</div>
        <div class="zs-slider-row"><span class="zs-slider-label">Strength</span><input id="ms-enhance-mode" type="range" min="0" max="3" step="1" value="${["off","light","balanced","thorough"].indexOf(enh.mode) < 0 ? 0 : ["off","light","balanced","thorough"].indexOf(enh.mode)}"><b id="ms-enhance-mode-label">${esc((ZSEnhance.LEVELS[enh.mode] || ZSEnhance.LEVELS.off).label)}</b></div>
        <div class="zs-menu-note" id="ms-enhance-desc">${esc(ZSEnhance.describe(enh))}</div>
        <label class="zs-pref-label">Preview before sending</label>
        <div class="zs-enhance-preview" id="ms-enhance-preview">
          <div class="zs-enhance-orig"><span>You type</span><p>${esc(enhPreviewSample)}</p></div>
          <div class="zs-enhance-arrow">↓</div>
          <div class="zs-enhance-out"><span>Agent receives</span><pre>${esc(enhPreview.text)}</pre></div>
        </div>
        <div class="zs-pref-row"><label><input id="ms-enhance-preview-toggle" type="checkbox" ${enh.preview ? "checked" : ""}> Ask me before sending: choose the improved prompt or my original (only one is sent)</label></div>
        <div class="zs-pref-row"><label><input id="ms-enhance-engine-facts" type="checkbox" ${enh.injectEngineFacts ? "checked" : ""}> Include connected-engine facts</label></div>
        <div class="zs-pref-row"><label><input id="ms-enhance-tool-facts" type="checkbox" ${enh.injectToolFacts ? "checked" : ""}> Include live tool facts</label></div>
        <div class="zs-pref-row"><label><input id="ms-enhance-approach" type="checkbox" ${enh.injectApproach ? "checked" : ""}> Add a task-shaped execution approach</label></div>
        <div class="zs-pref-row"><label><input id="ms-enhance-blender" type="checkbox" ${enh.blenderAssist ? "checked" : ""}> Add Blender asset tasks - the brief also commissions the models/props as real Blender assets and imports them into the build</label></div>
        <div class="zs-pref-row"><label><input id="ms-enhance-original-first" type="checkbox" ${enh.keepOriginalFirst ? "checked" : ""}> Keep my wording first</label></div>
      </section>`;

      const effortHtml = `<section class="zs-menu-sec zs-effort-sec" data-zs-tab="studio">
        <div class="zs-sec-label"><span>Execution effort &amp; reasoning</span><span class="zs-provider-badge">all providers</span></div>
        <div class="zs-slider-row"><label for="ms-effort-slider">Effort</label><input id="ms-effort-slider" style="--ms-effort-fill:${EFFORT_ORDER.indexOf(executionEffort)*20}%" type="range" min="0" max="5" step="1" value="${EFFORT_ORDER.indexOf(executionEffort)}" aria-valuetext="${EXECUTION_EFFORTS[executionEffort].label}"><b id="ms-effort-label" class="${executionEffort==="ultra"?"ms-ultra-title":""}">${EXECUTION_EFFORTS[executionEffort].label}</b></div>
        <div class="ms-effort-direction"><span>Faster</span><span>Deeper</span></div>
        <div class="ms-effort-ticks">${EFFORT_ORDER.map(id => `<button type="button" data-effort="${id}" data-effort-tick="${id}" ${id===executionEffort?'aria-current="true"':""}>${EXECUTION_EFFORTS[id].label}</button>`).join("")}</div>
        <div class="zs-menu-note" id="ms-effort-hint">${esc(EXECUTION_EFFORTS[executionEffort].hint)}</div>
        <div class="ms-ultra-appearance"><label>Ultra colors<select id="ms-ultra-palette" class="zs-mcp-field">${[['amethyst','Amethyst'],['rainbow','Rainbow'],['aurora','Aurora'],['sunset','Sunset']].map(([v,l])=>`<option value="${v}" ${menuPrefs.ultraPalette===v?'selected':''}>${l}</option>`).join('')}</select></label><label>Animation<select id="ms-ultra-animation" class="zs-mcp-field">${[['flow','Live flow'],['breathe','Soft pulse'],['still','Static']].map(([v,l])=>`<option value="${v}" ${menuPrefs.ultraAnimation===v?'selected':''}>${l}</option>`).join('')}</select></label></div>
        <div id="ms-ultra-summary" ${executionEffort==="ultra"?"":"hidden"}>
          <div class="ms-ultra-heading"><b class="ms-ultra-title">Ultra active</b><span>12 specialist manuals</span></div><p class="zs-menu-note">GUI, animation/rigging, VFX, modeling, worlds, gameplay, audio, networking, performance, engineering, accessibility and QA. Relevant methods are applied together; full inspect/design/build/integrate/verify/recovery manuals are available through ms_ultra_manual. These guide the model in context.</p>
          <ol class="ms-ultra-stages"><li><b>Inspect &amp; research</b><span>Project context, game references and uncertain APIs</span></li><li><b>Build &amp; integrate</b><span>Task-specific code, UI, world and asset methods</span></li><li><b>Verify &amp; refine</b><span>Real builds, captures and focused defect repairs</span></li></ol>
          <details class="ms-ultra-contract"><summary>Delivery contract for this task</summary><div id="ms-ultra-plan">${MSStudio.executionBrief(A.lastUserText||'Build a game interface and world').stages.map((x,i)=>`<article><b>0${i+1} · ${esc(x.name)}</b><p>${esc(x.check)}</p></article>`).join('')}</div><p class="zs-menu-note">This is the execution brief sent with your prompt. Completion requires actual results; the plan itself is not a progress report.</p></details>
          <div class="zs-menu-note">Applies automatically to your prompts. Reuses valid evidence and loads only relevant methods. Critic remains your separate setting below; provider model and quotas remain unchanged.</div>
        </div>
      </section>`;

      const criticHtml = `<section class="zs-menu-sec zs-critic-sec" data-zs-tab="studio">
        <div class="zs-sec-label"><span>Critic review</span><span class="zs-provider-badge">prompt add-on</span></div>
        <div class="zs-pref-row"><label><input id="ms-critic-enabled" type="checkbox" ${criticSettings.enabled?"checked":""}> Review the work before finishing</label></div>
        <div class="zs-menu-note">Adds Critic instructions to the startup guidance and every task prompt, alongside your prompt enhancer. Inspect the real result, repair verified defects and retest. It preserves your request and does not send separate review prompts after completion.</div>
        <label class="zs-pref-label" for="ms-critic-passes">Maximum review passes</label><select id="ms-critic-passes" class="zs-mcp-field" ${criticSettings.enabled?"":"disabled"}>${[1,2,3].map(n=>`<option value="${n}" ${criticSettings.passes===n?"selected":""}>${n} ${n===1?"pass":"passes"}</option>`).join("")}</select>
      </section>`;
      // ── Media relay ────────────────────────────────────────────────────
      const med = mediaSettings;
      const relayLine = lastRelay ? esc(ZSMediaRelay.describeOutcome(lastRelay)) : "No media relayed yet. Drop a photo or a video below.";
      const relayOk = lastRelay && lastRelay.ok;
      const mediaHtml = `<section class="zs-menu-sec zs-media-sec" data-zs-tab="appearance">
        <div class="zs-sec-label"><span>Media relay</span><span class="zs-provider-badge">photo · video</span></div>
        <div class="zs-menu-note">Send a screenshot, a photo or a clip into ${esc(P.displayName || P.id)} even when this site has no upload button or refuses the file. The relay carries it as a real paste, and for a video it extracts a few frames so the model can actually see what happened.</div>
        <div class="zs-drop" id="ms-media-drop"><b>Drop a photo or video</b><span>or <u>choose a file</u> · png, jpg, gif, webp, bmp, mp4, webm, avi, mov</span></div>
        <input id="ms-media-input" type="file" accept="image/png,image/jpeg,image/gif,image/webp,image/bmp,video/mp4,video/webm,video/avi,video/quicktime" hidden>
        <div class="zs-media-status ${relayOk ? "ok" : lastRelay ? "warn" : ""}" id="ms-media-status">${relayLine}</div>
        <div class="zs-menu-actions"><button id="ms-media-paste" class="zs-mini-action" ${relayOk ? "" : "disabled"}>Paste into composer</button><button id="ms-media-clear" class="zs-mini-action">Clear</button></div>
        <div class="zs-pref-row"><label><input id="ms-media-manifest" type="checkbox" ${med.sendManifest ? "checked" : ""}> Tell the model what was attached</label></div>
        <div class="zs-pref-row"><label><input id="ms-media-release" type="checkbox" ${med.releaseAfterSend ? "checked" : ""}> Delete the file from the bridge after sending</label></div>
      </section>`;
      // ── Surface vision: tabs + desktop apps ───────────────────────────
      // The agent can enumerate browser tabs and desktop windows, read a tab's
      // text, and type into a tab. This panel is the user-facing half: it shows
      // a live count of what is visible and lets them opt out of desktop
      // scanning. Both toggles default ON because the capability is read-only
      // unless the model explicitly calls a writing verb, and every writing verb
      // is documented in its own tool description.
      const surface = getSurfaceSettings();
      const surfaceHtml = `<section class="zs-menu-sec zs-surface-sec" data-zs-tab="interface">
        <div class="zs-sec-label"><span>Surface vision</span><span class="zs-provider-badge">tabs · windows</span></div>
        <div class="zs-menu-note">${esc(P.displayName || P.id)} can look at your open browser tabs and your desktop windows, click between them, read a page, and type into a tab - so "fix the thing I have open" actually works. Reading is text only: no screenshots, no keystroke capture. Desktop windows come from the local bridge and are limited by what the OS exposes.</div>
        <div class="zs-surface-grid">
          <div class="zs-surface-stat"><b id="ms-surface-tabs">-</b><span>browser tabs</span></div>
          <div class="zs-surface-stat"><b id="ms-surface-windows">-</b><span>desktop windows</span></div>
        </div>
        <div class="zs-menu-actions"><button id="ms-surface-refresh" class="zs-mini-action">Refresh</button><button id="ms-surface-plan" class="zs-mini-action">Unlock full desktop vision</button></div>
        <div class="zs-media-status" id="ms-surface-status">Not scanned yet. Press Refresh to see what is open.</div>
        <div class="zs-pref-row"><label><input id="ms-surface-tabs-toggle" type="checkbox" ${surface.tabs ? "checked" : ""}> Let the agent see browser tabs</label></div>
        <div class="zs-pref-row"><label><input id="ms-surface-windows-toggle" type="checkbox" ${surface.windows ? "checked" : ""}> Let the agent see desktop windows</label></div>
        <div class="zs-pref-row"><label><input id="ms-surface-read-toggle" type="checkbox" ${surface.allowRead ? "checked" : ""}> Allow reading a tab's text (read-only)</label></div>
        <div class="zs-pref-row"><label><input id="ms-surface-type-toggle" type="checkbox" ${surface.allowType ? "checked" : ""}> Allow typing into a tab when asked</label></div>
      </section>`;

      const figmaServer = allServers.find((x) => /figma/i.test(String(x.id || x.name || "")));
      const providerBehavior = getProviderBehavior();
      const creativeSurfaceHtml = `<section class="zs-menu-sec" data-zs-tab="studio">
        <div class="zs-sec-label"><span>Creative output</span><span class="zs-provider-badge">saved per provider</span></div>
        <div class="zs-menu-note">Choose where ${esc(P.displayName || P.id)} creates designs. Auto skips Canvas whenever building directly in Roblox Studio or another engine will produce the better usable result.</div>
        <div class="zs-choice-stack">
          <button class="zs-behavior-opt${providerBehavior.creativeSurface === "auto" ? " active" : ""}" data-creative-surface="auto"><b>Auto — choose the best surface</b><span>Direct engine for usable runtime UI; Figma for design systems and review; Canvas/SVG for textures or quick visual drafts.</span></button>
          <button class="zs-behavior-opt${providerBehavior.creativeSurface === "engine" ? " active" : ""}" data-creative-surface="engine"><b>Direct in Roblox/engine</b><span>Skips Canvas and Figma drafts and builds the real UI immediately in the connected engine.</span></button>
          <button class="zs-behavior-opt${providerBehavior.creativeSurface === "figma" ? " active" : ""}" data-creative-surface="figma"><b>Figma first</b><span>Best for multi-screen exploration, reusable components, review, responsive variants, and prototype handoff.${figmaServer && figmaServer.alive ? " Figma MCP process online; verify file pairing and Edit permission." : " Figma MCP not currently connected."}</span></button>
          <button class="zs-behavior-opt${providerBehavior.creativeSurface === "canvas" ? " active" : ""}" data-creative-surface="canvas"><b>Canvas/SVG first</b><span>Best for textures, decals, icons, portable graphics, and fast importable mockups.</span></button>
        </div>
        <div class="zs-setting-title">Art direction <span class="zs-provider-badge">saved per provider</span></div>
        <div class="zs-menu-note">One consistent style profile is sent into ${esc(P.displayName || P.id)}'s production instructions for relevant UI, buildings, models, animation, VFX, icons and textures. Auto follows your project references.</div>
        <div class="zs-creative-style-grid">
          ${[["auto","Auto / project style"],["anime","Anime"],["stylized-fantasy","Stylized fantasy"],["low-poly","Low-poly"],["realistic-pbr","Realistic PBR"],["cyberpunk","Cyberpunk"],["dark-gothic","Dark gothic"],["cozy-handpainted","Cozy hand-painted"],["retro-pixel","Retro pixel"],["minimal-modern","Minimal modern"],["sci-fi-hard-surface","Sci-fi hard-surface"],["toy-cartoon","Toy / cartoon"],["luxury-gold","Luxury gold"]].map(([id,label]) => `<button class="zs-creative-style-opt${providerBehavior.creativeStyle === id ? " active" : ""}" data-creative-style="${id}">${label}</button>`).join("")}
        </div>
        <div class="zs-setting-title">Asset workflow</div>
        <div class="zs-choice-stack">
          <button class="zs-behavior-opt${providerBehavior.assetWorkflow === "auto" ? " active" : ""}" data-asset-workflow="auto"><b>Auto — best usable path</b><span>Chooses native engine work or real external assets based on the deliverable.</span></button>
          <button class="zs-behavior-opt${providerBehavior.assetWorkflow === "external-first" ? " active" : ""}" data-asset-workflow="external-first"><b>External assets first</b><span>Create real SVG/icon/texture files or use connected design/model tools, then import and wire them where supported.</span></button>
          <button class="zs-behavior-opt${providerBehavior.assetWorkflow === "studio-first" ? " active" : ""}" data-asset-workflow="studio-first"><b>Inside Studio / engine first</b><span>Build directly in the target project; create external files only when they improve fidelity.</span></button>
          <button class="zs-behavior-opt${providerBehavior.assetWorkflow === "hybrid" ? " active" : ""}" data-asset-workflow="hybrid"><b>Hybrid source + integration</b><span>Keep editable source assets and integrate the real result in the engine, with read-back verification.</span></button>
        </div>
        <div class="zs-setting-title">Finish level</div>
        <div class="zs-creative-finish-grid">
          ${[["production","Production"],["premium","Premium"],["cinematic","Cinematic"]].map(([id,label]) => `<button class="zs-creative-finish-opt${providerBehavior.creativeFinish === id ? " active" : ""}" data-creative-finish="${id}">${label}</button>`).join("")}
        </div>
        <div class="zs-menu-note"><b>Asset tools:</b> ${esc(providerBehavior.creativeStyle)} style · ${esc(providerBehavior.assetWorkflow)} workflow · ${esc(providerBehavior.creativeFinish)} finish. Real generated files and confirmed engine imports are separate deliverables; the agent must report which actually happened.</div>
      </section>`;
      const providerBehaviorHtml = `<section class="zs-menu-sec" data-zs-tab="studio">
        <div class="zs-sec-label"><span>${esc(P.displayName || P.id)} behavior</span><span class="zs-provider-badge">saved per provider</span></div>
        <div class="zs-setting-title">Prompt rewriting <span class="zs-provider-badge">skills always active</span></div>
        <div class="zs-choice-stack">
          <button class="zs-behavior-opt${providerBehavior.promptSkills === "off" ? " active" : ""}" data-prompt-skills="off"><b>Off — literal prompt</b><span>Keeps your exact wording. All relevant skills and tools still improve the actual execution.</span></button>
          <button class="zs-behavior-opt${providerBehavior.promptSkills === "suggest" ? " active" : ""}" data-prompt-skills="suggest"><b>Suggest rewrite</b><span>May offer an optional improved prompt without blocking work. Skills and tools remain active either way.</span></button>
          <button class="zs-behavior-opt${providerBehavior.promptSkills === "automatic" ? " active" : ""}" data-prompt-skills="automatic"><b>Automatic rewrite</b><span>Silently clarifies reversible missing details. Explicit intent stays binding and skills remain independently active.</span></button>
        </div>
        <div class="zs-menu-note"><b>Current behavior:</b> rewrite ${providerBehavior.promptSkills} · ${providerBehavior.loops} checks · ${providerBehavior.creativeSurface} creative routing · ${providerBehavior.creativeStyle} style · ${providerBehavior.assetWorkflow} assets · ${providerBehavior.creativeFinish} finish · ${skillDepth} specialist depth · ${usageMode} usage.</div>
        <div class="zs-setting-title">Production checks</div>
        <div class="zs-choice-stack">
          <button class="zs-behavior-opt${providerBehavior.loops === "fast" ? " active" : ""}" data-loop-mode="fast"><b>Fast — loops disabled</b><span>Skips workflow plans, critic loops, scorecards, and test matrices. Keeps only essential safety or compile checks.</span></button>
          <button class="zs-behavior-opt${providerBehavior.loops === "balanced" ? " active" : ""}" data-loop-mode="balanced"><b>Balanced</b><span>One focused verification and critic pass for meaningful changes; trivial edits finish immediately.</span></button>
          <button class="zs-behavior-opt${providerBehavior.loops === "rigorous" ? " active" : ""}" data-loop-mode="rigorous"><b>Rigorous</b><span>Plans, tests, gathers evidence, critiques, and revises for up to three rounds. Slowest, highest confidence.</span></button>
        </div>
        <div class="zs-menu-actions"><button id="ms-reset-agent-settings" class="zs-mini-action">Reset agent behavior</button></div>
      </section>`;
      const qualityHtml = `<section class="zs-menu-sec" data-zs-tab="studio">
        <div class="zs-sec-label"><span>Studio skill coverage</span></div>
        <div class="zs-menu-note">Controls how many specialized skills and tools work together on each result. They improve their own game-development aspects directly; no generic multiplier replaces them.</div>
        <div class="zs-quality-grid">
          ${[["focused","Focused"],["full","Full studio"],["maximum","Maximum detail"]].map(([id,label]) => `<button class="zs-quality-opt${skillDepth === id ? " active" : ""}" data-skill-depth="${id}">${label}</button>`).join("")}
        </div>
        <div class="zs-economy-note">${skillDepth === "maximum" ? "Broadest relevant specialist mesh and deep craft passes." : skillDepth === "focused" ? "Core disciplines plus every directly relevant specialist." : "Broad professional studio coverage for every request."}</div>
      </section>`;

      const usageHtml = `<section class="zs-menu-sec" data-zs-tab="studio">
        <div class="zs-sec-label"><span>Usage optimizer</span></div>
        <div class="zs-menu-note">Automatically improves Multi-Script startup prompts and injected tool feedback for ${esc(P.displayName || P.id)}. Balanced is the safe default; Compact additionally minifies lossless JSON results and uses short system reminders.</div>
        <div class="zs-economy-grid">
          ${[["off","Off"],["balanced","Balanced"],["compact","Compact"]].map(([id,label]) => `<button class="zs-economy-opt${usageMode === id ? " active" : ""}" data-economy="${id}">${label}</button>`).join("")}
        </div>
        <div class="zs-economy-note">${usageMode === "off" ? "No automatic optimization." : usageMode === "compact" ? "Lowest usage; correctness and full error evidence are preserved." : "Fewer repeated words and unnecessary calls, with normal detail when needed."}</div>
      </section>`;
      // ── Reply pacing / error recovery / autonomy ────────────────────────────
      // Three product behaviours, each with an honest one-line status so the
      // user can see exactly what the loop will do before leaving it alone.
      // Pacing can be scoped to THIS site only: the engine has always supported a
      // per-provider override, and this is what makes it reachable ("slow down on
      // the site that flags me, keep everything else instant").
      const paceOverride = (getPaceSettings().perProvider || {})[P.id] || null;
      const paceScoped = !!paceOverride;
      const paceEffMode = (paceOverride && paceOverride.mode) || getPaceSettings().mode;
      const pacingHtml = `<section class="zs-menu-sec" data-zs-tab="agent">
        <div class="zs-sec-label"><span>Reply pacing</span><span class="zs-provider-badge">anti-flag</span></div>
        <div class="zs-menu-note">Spaces extension-generated turns and adds cooldowns after errors. Provider minimums still apply when pacing is Off. Cross-tab coordination and failed-turn recovery follow the current provider's safeguards. Pacing cannot guarantee account access or prevent provider restrictions.</div>
        <div class="zs-choice-stack">
          ${ZSPace.MODE_IDS.map((id) => { const m = ZSPace.MODES[id]; const active = paceEffMode === id; return `<button class="zs-behavior-opt${active ? " active" : ""}" data-pace-mode="${id}"><b>${m.label}</b><span>${m.hint}</span></button>`; }).join("")}
        </div>
        <div class="zs-pref-row"><label><input id="ms-pace-scope" type="checkbox" ${paceScoped ? "checked" : ""}> Apply only to <b>${esc(P.displayName || P.id)}</b> — leave every other site on the global setting</label></div>
        <div class="zs-pref-row"><label><input id="ms-typing-sim" type="checkbox" ${getPaceSettings().typingSim ? "checked" : ""}> Simulate typing the composer fill (only takes effect in Cautious/Custom)</label></div>
        <div class="zs-economy-note">${esc(paceDescription())}${paceScoped ? " · scoped to this site" : " · global"}</div>
        <div class="zs-menu-actions"><button id="ms-pace-test" class="zs-mini-action">Test pacing</button></div>
      </section>`;

      const verificationHtml = `<section class="zs-menu-sec" data-zs-tab="agent">
        <div class="zs-sec-label"><span>Verification handling</span><span class="zs-provider-badge">no bypass</span></div>
        <div class="zs-menu-note">What the run does when the site puts a bot-check in the way. Multi-Script never solves, answers, token-injects or outsources a CAPTCHA - that is a bypass and risks the account. Instead it pauses, moves its own controls off the widget, can click the site's <b>own</b> widget once (exactly what a human does), alerts you if you are in another tab, resumes by itself when the check clears, and spaces later messages further apart so the check stops coming back.</div>
        <div class="zs-choice-stack">
          ${ZSVerify.MODE_IDS.map((id) => { const m = ZSVerify.MODES[id]; const active = vmode().id === id; return `<button class="zs-behavior-opt${active ? " active" : ""}" data-verify="${id}"><b>${m.label}</b><span>${m.describe}</span></button>`; }).join("")}
        </div>
        <div class="zs-economy-note">${esc(ZSVerify.describe(getVerificationSettings(), P.id))}</div>
        <label class="zs-menu-toggle"><input type="checkbox" id="zs-verify-audible" ${getVerificationSettings().audibleAlert ? "checked" : ""}> <span>Alert me when a check is waiting (tone + tab title)</span></label>
        <div class="zs-economy-note">${A.verifyState && A.verifyState.floorMs ? `Currently spacing messages ${Math.round(A.verifyState.floorMs / 1000)}s further apart after a check.` : esc(ZSVerify.COPY.whyManual)}</div>
      </section>`;

      const reliabilityHtml = `<section class="zs-menu-sec" data-zs-tab="agent">
        <div class="zs-sec-label"><span>Error recovery</span><span class="zs-provider-badge">unattended</span></div>
        <div class="zs-menu-note">What happens when a turn comes back empty, times out, or is not one valid command. Standard recovers from a one-off hiccup; Persistent keeps a long unattended run alive through repeated stalls and widens the patience windows. A retry only ever re-asks the model - it can never invent a result.</div>
        <div class="zs-choice-stack">
          ${ZSResilience.LEVEL_IDS.map((id) => { const l = ZSResilience.LEVELS[id]; const active = getResilienceSettings().level === id; return `<button class="zs-behavior-opt${active ? " active" : ""}" data-recovery="${id}"><b>${l.label}</b><span>${l.hint}</span></button>`; }).join("")}
        </div>
        <div class="zs-economy-note">${esc(ZSResilience.describe(getResilienceSettings(), P.id))}</div>
        <label class="zs-pref-row"><span><input id="ms-keep-hidden" type="checkbox" ${keepRunningHidden ? "checked" : ""}> Keep running when the browser is covered or in the background</span></label>
        <div class="zs-menu-note">Browsers report a tab as hidden when another window (Roblox Studio, Unity…) covers them. With this ON the agent keeps reading replies, running tools and sending results instead of waiting on "Paused". Turn it OFF only if a site misbehaves in a background tab.</div>
      </section>
      <section class="zs-menu-sec" data-zs-tab="agent">
        <div class="zs-sec-label"><span>Limits &amp; truncation</span><span class="zs-provider-badge">optional</span></div>
        <div class="zs-menu-note">Normally Multi-Script keeps each site's composer healthy: long tool results are split into pages, and the text typed into the chat box is clipped to a size that site is known to accept. Here you can raise, change or switch those limits off. Nothing is cut silently - a clip always leaves a visible note.</div>
        ${(() => { const L = ZS.limits.get(); const modeSel = (id, cur, chars) => `<div class="zs-pref-row" style="flex-direction:row;align-items:center;flex-wrap:wrap"><select id="${id}" class="zs-mcp-field" style="width:auto">${[["auto", "Automatic (per-site defaults)"], ["custom", "Custom size"], ["off", "No limit"]].map(([v, t]) => `<option value="${v}"${cur === v ? " selected" : ""}>${t}</option>`).join("")}</select> <input id="${id}-chars" type="number" min="${ZS.limits.MIN}" max="${ZS.limits.MAX}" step="1000" value="${chars}" class="zs-mcp-field" ${cur === "custom" ? "" : "disabled"} style="width:7.5em"> <span class="zs-menu-note" style="display:inline">characters</span></div>`;
          return `<div class="zs-menu-note"><b>Tool results</b> - larger results are split into pages the model reads with <code>more_output</code>.</div>${modeSel("ms-lim-result", L.resultMode, L.resultChars)}
          <div class="zs-menu-note"><b>Messages typed into the chat box</b> - the last clip before sending. "No limit" can make a very large paste slow or refuse to send on some sites.</div>${modeSel("ms-lim-send", L.sendMode, L.sendChars)}
          <label class="zs-pref-row"><span><input id="ms-lim-salvage" type="checkbox" ${L.salvage ? "checked" : ""}> Auto-close a command whose last closing braces were cut off by the site's output limit</span></label>
          <div id="ms-lim-summary" class="zs-economy-note">${ZS.limits.describe(L).map((d) => `<div${d.level === "warn" ? ' style="color:#ffb454"' : ""}>${d.level === "warn" ? "⚠ " : ""}${esc(d.text)}</div>`).join("")}</div>
          <div class="zs-pref-row"><button id="ms-lim-reset" class="zs-mini-action" type="button">Reset to automatic</button></div>`; })()}
        <div class="zs-menu-note">Tip: for very large scripts the model can upload code in pieces with <code>ms_stage_code</code> and run it with <code>ms_run_staged_luau</code> / <code>ms_write_staged</code>, so no single message has to carry it all.</div>
      </section>`;

      const autonomyHtml = `<section class="zs-menu-sec" data-zs-tab="agent">
        <div class="zs-sec-label"><span>Autonomy</span><span class="zs-provider-badge">saved globally</span></div>
        <div class="zs-menu-note">One-shot turns a pasted design specification into an uninterrupted build: no clarifying questions, no stopping at a checkpoint, and it keeps working through as many commands as the spec needs. It only stops for a choice that is destructive, costs money, needs credentials, or is genuinely contradictory.</div>
        <div class="zs-choice-stack">
          ${ZS.AUTONOMY_IDS.map((id) => { const a = ZS.AUTONOMY_LEVELS[id]; const active = getAutonomyLevel() === id; return `<button class="zs-behavior-opt${active ? " active" : ""}" data-autonomy="${id}"><b>${id==="oneShot"?"Sandbox":"Ask"}</b><span>${a.hint}</span></button>`; }).join("")}
        </div>
        <div class="zs-economy-note">${getAutonomyLevel() === "oneShot" ? "One-shot is on: the agent will not ask you anything it can decide itself." : "Guided: the agent may pause or ask about a real ambiguity."}</div>
      </section>`;

      const notionTabHtml = notionTabMarkup();
      const notionProfiles = P.autoRoutingProfiles ? P.autoRoutingProfiles() : [];
      const activeNotionProfile = P.getAutoRoutingProfile ? P.getAutoRoutingProfile() : "";
      const profileProviderLabel = P.id === "arena" ? "Arena Direct Max" : "Notion Auto";
      const profileBoundary = P.id === "arena" ? "Saved model preferences are metadata, not model selection. Arena’s own selector/router controls the actual backend. Choose the model on Arena when available. Off — Normal Arena removes the preference block. Exact tool feedback is never wrapped in a routing request, and no model identity or access is fabricated." : "Saved preferences do not choose a model. Use Notion’s own selector and your workspace’s eligible model controls. Multi-Script keeps the actual backend and local tool transport.";
      const notionProfileHtml = notionProfiles.length ?
        `<section class="zs-menu-sec zs-notion-model-sec" data-zs-tab="${P.id === "notion" ? "notion" : "agent"}">
          <div class="zs-sec-label"><span>${P.id === "arena" ? `${profileProviderLabel} routing profile` : `${profileProviderLabel} preferred model`}</span><span class="zs-provider-badge">prompt-only</span></div>
          <div class="zs-menu-note">${profileBoundary} ${P.id === "arena" ? "When enabled, the startup contract is placed once and compact targeting is sent each turn. When disabled, Arena starts normally like before while engine-connected and engine-free modes continue to work." : "The request is placed once at the top of each new chat; the full shared Multi-Script studio prompt follows unchanged. If unavailable, the provider must use its best legitimately available model without impersonation."}</div>
          <div class="zs-profile-grid">
            ${notionProfiles.map((x) => `<button class="zs-behavior-opt zs-profile-opt${activeNotionProfile === x.id ? " active" : ""}" data-profile="${x.id}"><b>${x.label}</b><span>${x.description}</span></button>`).join("")}
            <button class="zs-behavior-opt zs-profile-opt${!activeNotionProfile ? " active" : ""}" data-profile=""><b>${P.id === "arena" ? "Off — Normal Arena" : "Standard Auto"}</b><span>${P.id === "arena" ? "No model preference metadata. Keeps normal engine and engine-free startup." : "Use the provider’s standard automatic behavior."}</span></button>
          </div>
          <div class="zs-menu-actions"><button id="zs-check-profile" class="zs-mini-action">Check selection</button><button id="zs-copy-profile" class="zs-mini-action" ${activeNotionProfile ? "" : "disabled"}>Copy preference text</button></div>
          <div id="zs-profile-status" class="zs-menu-note"></div>
        </section>` : "";

      const setupEngines = (A.bridge && Array.isArray(A.bridge.engines) ? A.bridge.engines : []);
      const setupConnected = setupEngines.filter((x) => x && x.connected === true);
      const setupTutorialHtml = `
        <section class="zs-menu-sec zs-tutorial-hero" data-zs-tab="setup">
          <div class="zs-sec-label"><span>Set up Multi-Script</span><span class="zs-provider-badge">start here</span></div>
          <div class="zs-menu-note">Multi-Script is a browser control layer plus a local bridge. The AI chat writes one JSON command, the extension sends it to the bridge, and the bridge calls the real tools advertised by your connected MCP servers. It does not replace Notion with Connectors and it does not invent extra native tools.</div>
          <div class="zs-tutorial-status">
            <span class="${A.bridge && A.bridge.connected ? "ok" : ""}">${A.bridge && A.bridge.connected ? "✓ Bridge online" : "1 Bridge offline · click the terminal icon"}</span>
            <span class="${setupConnected.length ? "ok" : ""}">${setupConnected.length ? `✓ ${setupConnected.map((x) => esc(x.id || "engine")).join(" + ")} connected` : "2 Connect an editor"}</span>
            <span class="${P.getEditor && P.getEditor() ? "ok" : ""}">${P.getEditor && P.getEditor() ? `✓ ${esc(P.displayName || P.id)} composer found` : `3 Open ${esc(P.displayName || P.id)} chat`}</span>
          </div>
          <div class="zs-menu-actions"><button id="ms-setup-check" class="zs-mini-action">Run setup check</button><button id="ms-copy-setup" class="zs-mini-action">Copy checklist</button></div>
        </section>
        <section class="zs-menu-sec" data-zs-tab="setup">
          <div class="zs-sec-label"><span>1 · Install the complete release</span></div>
          <ol class="zs-tutorial-list">
            <li>Extract the full ZIP. Do not run it from inside the ZIP preview.</li>
            <li>Open <b>chrome://extensions</b> or <b>edge://extensions</b>, enable Developer mode, choose <b>Load unpacked</b>, and select the extracted <b>extension</b> folder.</li>
            <li>After updating Multi-Script, press <b>Reload</b> on its extension card. A new host such as <b>app.notion.com</b> needs the updated permission before injection can work.</li>
          </ol>
        </section>
        <section class="zs-menu-sec" data-zs-tab="setup">
          <div class="zs-sec-label"><span>2 · Start the local bridge</span></div>
          <ol class="zs-tutorial-list">
            <li><b>One time only:</b> double-click <b>Setup.bat</b> (Windows), run <b>MacOS_Setup.command</b> (macOS) or <code>bash Setup.sh</code> (Linux). It registers a tiny launcher with your browser.</li>
            <li>Fully restart the browser once. From then on the bridge starts <b>by itself</b> when a chat opens - or click the <b>terminal icon</b> in the bar.</li>
            <li>The icon's panel is the live terminal: log, Start / Stop / Restart, and a <b>Running</b> tab listing the bridge, engines and open apps.</li>
          </ol>
        </section>
        <section class="zs-menu-sec" data-zs-tab="setup">
          <div class="zs-sec-label"><span>3 · Connect your real editor or MCP server</span></div>
          <div class="zs-menu-note"><b>Roblox Studio:</b> open a place, then enable its MCP server from Studio’s Assistant/MCP settings. <b>Unity/Godot:</b> use the bundled launcher and open the target project. <b>Blender/Figma/other MCP:</b> copy the verified stdio launch command from that server’s documentation into the Engines category. The bridge exposes exactly what each live server advertises.</div>
          <div class="zs-menu-actions"><button class="zs-mini-action" data-go-tab="engines">Open Engines setup</button></div>
        </section>
        <section class="zs-menu-sec" data-zs-tab="setup">
          <div class="zs-sec-label"><span>4 · Open the correct AI chat</span></div>
          <div class="zs-menu-note">For Notion, use <b>https://app.notion.com/chat</b>. The old notion.so root can open workspace settings or Connectors, which is not the Multi-Script chat surface. In a fresh Notion chat, look for the <b>Ask anything</b> composer; Multi-Script should mount beside it after the extension is reloaded.</div>
          <button class="zs-tip-opt" data-u="https://app.notion.com/chat"><span>Open Notion AI chat</span><span class="zs-tip-sub">app.notion.com/chat</span></button>
        </section>
        <section class="zs-menu-sec" data-zs-tab="setup">
          <div class="zs-sec-label"><span>5 · Start and verify a session</span></div>
          <ol class="zs-tutorial-list">
            <li>Return to the chat and press <b>Start</b> in the Multi-Script bar.</li>
            <li>Choose the connected engine, or use engine-free Chat Studio for prompt-only work.</li>
            <li>Send a small read-only request first. Confirm the command chip, bridge result, and project read-back before a large build.</li>
          </ol>
        </section>
        <section class="zs-menu-sec" data-zs-tab="setup">
          <div class="zs-sec-label"><span>Settings map</span></div>
          <div class="zs-menu-note"><b>Agent</b> controls prompt enhancement, effort, autonomy, pacing, recovery, verification, tools and appearance. <b>Engines</b> manages bridge health and MCP launch commands. <b>AI sites</b> switches provider. <b>Help</b> contains backups, diagnostics and troubleshooting. Settings never add provider entitlements or bypass plan limits.</div>
        </section>`;

      // ── Chat bar customizer (6.25) ───────────────────────────────────────
      const seg = (key, opts, cols) => `<div class="zs-pref-grid zs-pref-grid-${cols || opts.length}">${opts.map(([id, label, hint]) => `<button class="zs-pref-opt${String(menuPrefs[key]) === id ? " active" : ""}" data-bar-${key.replace(/^bar/, "").toLowerCase()}="${id}"${hint ? ` title="${esc(hint)}"` : ""}>${label}</button>`).join("")}</div>`;
      const hidden = new Set(menuPrefs.barHide || []);
      const itemChip = ([id, label, only]) => (only && P.id !== only) ? "" : `<label class="zs-chip-toggle${hidden.has(id) ? "" : " on"}"><input type="checkbox" data-bar-item="${id}" ${hidden.has(id) ? "" : "checked"}><span>${label}</span></label>`;
      const free = menuPrefs.barDock !== "auto";
      const barHtml = `<section class="zs-menu-sec zs-bar-lab" data-zs-tab="bar">
        <div class="zs-sec-label"><span>Position</span><span class="zs-provider-badge">live</span></div>
        <div class="zs-menu-note">The bar you see on the page <b>is</b> the preview — every change applies instantly. <b>Auto</b> docks inside ${esc(P.displayName || P.id)}'s composer and lines up with its text. <b>Floating</b> hugs the composer from the outside. <b>Window</b> pins a pill to the bottom of the window and never depends on the site's layout — the safe choice if a site restyles itself.</div>
        ${seg("barDock", [["auto", "Auto dock"], ["float", "Floating"], ["window", "Window"]])}
        <div class="zs-bar-nudge">
          <div class="zs-slider-row"><span class="zs-slider-label" data-nudge-reset="x" title="Double-click to reset">Nudge ↔</span><input id="ms-bar-ox" type="range" min="-${NUDGE_MAX}" max="${NUDGE_MAX}" step="1" value="${nudgeOf().x}" aria-label="Nudge the chat bar horizontally"><b id="ms-bar-ox-v">${fmtNudge(nudgeOf().x)}</b></div>
          <div class="zs-slider-row"><span class="zs-slider-label" data-nudge-reset="y" title="Double-click to reset">Nudge ↕</span><input id="ms-bar-oy" type="range" min="-${NUDGE_MAX}" max="${NUDGE_MAX}" step="1" value="${nudgeOf().y}" aria-label="Nudge the chat bar vertically"><b id="ms-bar-oy-v">${fmtNudge(nudgeOf().y)}</b></div>
          <div class="zs-menu-note">Nudge works in every dock and is remembered for ${esc(P.displayName || P.id)}. While you drag, the panel fades so you can see the bar; the bar stops at the window edge. <button type="button" class="zs-linkbtn" id="ms-bar-nudge-reset">Reset nudge</button></div>
        </div>
        <div class="zs-bar-free-opts${free ? "" : " dim"}">
          <label class="zs-pref-label">Align</label>${seg("barAlign", [["left", "Left"], ["center", "Center"], ["right", "Right"]])}
          <label class="zs-pref-label">Width</label>${seg("barFit", [["full", "Match composer"], ["fit", "Fit content"]])}
        </div>
        <div class="zs-menu-note">Align and Width apply to Floating and Window.</div>
      </section>
      <section class="zs-menu-sec" data-zs-tab="bar">
        <div class="zs-sec-label"><span>Look</span></div>
        <label class="zs-pref-label">Style</label>${seg("barStyle", [["native", "Native"], ["card", "Card"], ["glass", "Glass"], ["minimal", "Minimal"]])}
        <label class="zs-pref-label">Theme</label><select id="ms-bar-theme" class="zs-mcp-field">${[["auto","Follow the menu theme"],["midnight","Midnight"],["graphite","Graphite"],["frost","Frost"],["mono","Mono"],["ink","Ink"],["synthwave","Synthwave"],["forest","Forest"],["roblox","Classic Roblox"],["robloxdark","Roblox 2017"],["terminal","Terminal"],["sunset","Sunset"],["ocean","Ocean"],["paper","Paper"],["aurora","Aurora (live)"],["lava","Lava (live)"],["sakura","Sakura"],["crimson","Crimson"],["nebula","Nebula (live)"],["matrix","Matrix (live)"],["fnaf","Fazbear's (live)"],["scream","Scream · Ghostface"],["myers","Michael Myers"],["slender","Slenderman"],["jason","Jason Voorhees"],["cobalt", "Cobalt Studio"],["porcelain", "Porcelain"],["ember", "Ember Studio"],["tidal", "Tidal (live)"],["starlight", "Starlight (live)"],["daybreak", "Daybreak (live)"]].map(([v,l]) => `<option value="${v}"${menuPrefs.barTheme===v?" selected":""}>${l}</option>`).join("")}</select>
        <div class="zs-menu-note">Give the chat bar its own theme - including a different one from the menu. It applies instantly wherever the bar is docked, and fixes light text on light surfaces when the bar sits inside a provider's composer.</div>
        <label class="zs-pref-label">Size</label>${seg("barSize", [["compact", "Compact"], ["regular", "Regular"], ["roomy", "Roomy"]])}
        <label class="zs-pref-label">Status line</label>${seg("barStatus", [["stacked", "Under name"], ["inline", "Inline"], ["hidden", "Hidden"]])}
      </section>
      <section class="zs-menu-sec" data-zs-tab="bar">
        <div class="zs-sec-label"><span>Show on the bar</span></div>
        <div class="zs-chip-toggles">${[["brand", "Name"], ["status", "Status"], ["chatOnly", "Start without engine"], ["ideas", "New idea"], ["blender", "Blender workspace"], ["progress", "Task progress"], ["phone", "Phone control"], ["models", "Models", "notion"], ["discord", "Discord"], ["donate", "Donate"], ["memory", "Memory"], ["switch", "Settings"], ["terminal", "Terminal"], ["running", "Running list"]].map(itemChip).join("")}</div>
        <div class="zs-menu-note">The primary Start / Stop button always stays. Hide <b>Settings</b> only if you open this menu another way — the extension popup can reopen it.</div>
        <div class="zs-menu-actions"><button id="ms-bar-realign" class="zs-mini-action">Realign now</button><button id="ms-bar-report" class="zs-mini-action">Copy layout report</button><button id="ms-bar-reset" class="zs-mini-action">Reset chat bar</button></div>
        <div id="ms-bar-msg" class="zs-menu-note"></div>
      </section>`;
      const quick = ([tab, icon, title, sub]) => `<button class="zs-quick" data-go-tab="${tab}"><span class="zs-quick-ic">${icon}</span><span class="zs-quick-tx"><b>${title}</b><i>${sub}</i></span></button>`;
      const homeQuickHtml = `<section class="zs-menu-sec" data-zs-tab="home" id="ms-mode-guide">
        <a id="ms-donate" class="ms-donate" href="https://ko-fi.com/multixscript" target="_blank" rel="noopener noreferrer" aria-label="Donate to Multi-Script on Ko-fi"><span aria-hidden="true">♡</span><span>Support Multi-Script<small>Donate on Ko-fi</small></span><span aria-hidden="true">↗</span></a>
        <div class="zs-sec-label"><span>Choose your workspace</span><span class="zs-provider-badge">${A.started?(A.software?"Build software":A.chatOnly?"Chat studio":"Studio engine"):"No session started"}</span></div>
        <div class="zs-menu-note"><b>Studio engine</b> edits a real connected Roblox, Godot, Unity or Blender project. Use <b>Start agent</b> in a fresh chat. Roblox’s native MCP and the plugin toolset are separate; each exposes its actual enabled commands.</div>
        <div class="zs-menu-note"><b>Chat studio</b> works without an engine: code, plans, design and general local tools. It intentionally cannot edit a globally connected Studio. Start a fresh engine session for project changes.</div>
        <div class="zs-menu-note"><b>Build software</b> edits files in your chosen desktop folder and runs builds/tests when allowed. Select a workspace in <b>Code &amp; Build</b>. Roblox is optional, via its explicit engine add-on.</div>
        <div class="zs-menu-note">Your first tool result is the available catalog. <b>Bridge online</b>, <b>native MCP attached</b> and <b>plugin tools enabled</b> are different states. The AI receives only the current session’s allowed tools. Open a new chat to change session mode.</div>
      </section><section class="zs-menu-sec zs-quick-sec" data-zs-tab="home">
        <div class="zs-sec-label"><span>Jump to</span></div>
        <div class="zs-quick-grid">${[
          ["bar", "▭", "Chat bar", "position, style, buttons"],
          ["look", "◐", "Look", "theme, accent, layout"],
          ["agent", "✦", "Agent", "effort, autonomy, pacing"],
          ["sites", "◎", "AI sites", "Notion, Claude, ChatGPT…"],
          ["engines", "⚙", "Engines", "bridge and MCP servers"],
          ["help", "?", "Help", "guide, backup, support"],
        ].map(quick).join("")}</div>
      </section>`;
      const X = typeof ZSExtras !== "undefined" ? ZSExtras : null;
      const engOpts = [["auto", "Auto (connected)"], ["roblox", "Roblox"], ["unity", "Unity"], ["godot", "Godot"], ["blender", "Blender (asset brief)"], ["generic", "Engine-free"]];
      const ideasHtml = X ? `<section class="zs-menu-sec zs-ideas-sec" data-zs-tab="ideas">
        <div class="zs-sec-label"><span>Game idea bot</span><span class="zs-provider-badge">offline · instant</span></div>
        <div class="zs-menu-note">Pumps out a fresh game idea as a copy-paste-ready build prompt. It adapts to the engine you have connected${connectedEngineIds().length ? ` (now: <b>${esc(connectedEngineIds().join(", "))}</b>)` : ""}: Roblox gets Luau/DataStore/RemoteEvent specifics, Unity gets C#/URP/Input System, Godot gets GDScript/scenes/signals, and Blender - which is not a game engine - gets a 3D asset brief instead.</div>
        <label class="zs-pref-label">Engine</label><select id="ms-idea-engine" class="zs-mcp-field">${engOpts.map(([v, l]) => `<option value="${v}"${ideaOpts.engine === v ? " selected" : ""}>${l}</option>`).join("")}</select>
        <label class="zs-pref-label">Genre</label><select id="ms-idea-genre" class="zs-mcp-field">${Object.entries(X.GENRES).map(([v, l]) => `<option value="${v}"${ideaOpts.genre === v ? " selected" : ""}>${l}</option>`).join("")}</select>
        <label class="zs-pref-label">Scope</label><div class="zs-pref-grid zs-pref-grid-3">${Object.entries(X.SCOPES).map(([v, o]) => `<button type="button" class="zs-pref-opt${ideaOpts.scope === v ? " active" : ""}" data-idea-scope="${v}">${o.label}</button>`).join("")}</div>
        <label class="zs-pref-row"><input id="ms-idea-twist" type="checkbox"${ideaOpts.twist ? " checked" : ""}> Add a bonus twist</label>
        <label class="zs-pref-row"><input id="ms-idea-blender" type="checkbox"${ideaOpts.blender ? " checked" : ""}> Include a Blender asset plan - the brief gains concrete tasks for generating the game's models in Blender and importing them</label>
        <div class="zs-menu-actions"><button type="button" id="ms-idea-go" class="zs-mini-action">Generate idea</button><button type="button" id="ms-idea-copy" class="zs-mini-action"${lastIdea ? "" : " disabled"}>Copy prompt</button><button type="button" id="ms-idea-insert" class="zs-mini-action"${lastIdea ? "" : " disabled"}>Put in chat box</button></div>
        <div class="zs-idea-title" id="ms-idea-title" role="status" aria-live="polite">${lastIdea ? esc(lastIdea.title) : ""}</div>
        <textarea id="ms-idea-out" class="zs-idea-out" rows="10" readonly placeholder="Press Generate idea">${lastIdea ? esc(lastIdea.prompt) : ""}</textarea>
      </section>` : "";
      const sw = softwareSettings;
      const wipHtml = X ? `<section class="zs-menu-sec zs-wip-sec" data-zs-tab="software">
        <div class="zs-sec-label"><span>Software Builder &amp; Code mode</span><span class="zs-provider-badge">${typeof MSBuild!=="undefined"?MSBuild.edition:"dev"}</span></div>
        <div class="zs-sw-intro"><span class="zs-sw-icon">⌘</span><div><b>${sw.mode === "code" ? "Code on your own files" : "Build real software on this PC"}</b><span>${sw.mode === "code" ? "Any provider becomes a coding agent for a folder on this PC: explore, edit, patch, refactor, test and commit - every change can be undone." : "Write, compile, test and package projects through the local bridge. Files stay inside the workspace you choose."}</span></div></div>
        <div class="zs-menu-note">${typeof MSBuild!=="undefined"&&MSBuild.edition==="public"?"Public limits: 256 KiB per edit/write payload, 60 seconds per command, and foreground commands only. Files, builds, tests and packaging remain available.":"Development edition: no added product limits. Workspace permissions and provider account quotas still apply."}</div>
        <label class="zs-pref-label">Mode</label>
        <div class="zs-pref-grid zs-pref-grid-2 zs-sw-modes">${[["build", "⚒", "Build software", "Scaffold, build and package a new app"], ["code", "‹›", "Code mode", "General coding on any local folder"]].map(([v, icon, l, d]) => `<button class="zs-pref-opt${sw.mode === v ? " active" : ""}" data-sw-mode="${v}" title="${d}"><b>${icon}</b><span>${l}</span></button>`).join("")}</div>
        <div class="zs-sw-toggles">
          <label class="zs-pref-row zs-toggle-card"><input id="ms-sw-enabled" type="checkbox"${sw.enabled ? " checked" : ""}><span><b>${sw.mode === "code" ? "Code mode" : "Software Builder"}</b><i>Show ${sw.mode === "code" ? "Code" : "Build software"} on new chats</i></span></label>
          <label class="zs-pref-row zs-toggle-card"><input id="ms-sw-run" type="checkbox"${sw.allowRun ? " checked" : ""}><span><b>Run commands</b><i>Build, test, lint, git commit, run</i></span></label>
        </div>
        <label class="zs-pref-label">Add-ons for this session type</label>
        <div class="zs-sw-toggles zs-sw-addons">
          <label class="zs-pref-row zs-toggle-card"><input id="ms-sw-ad-skills" type="checkbox"${sw.addons && sw.addons.skills ? " checked" : ""}><span><b>Skills &amp; review</b><i>Expert skills, critic review, memory</i></span></label>
          <label class="zs-pref-row zs-toggle-card"><input id="ms-sw-ad-engines" type="checkbox"${sw.addons && sw.addons.engines ? " checked" : ""}><span><b>Game engines</b><i>Also allow connected Roblox/Unity/Godot/Blender</i></span></label>
          <label class="zs-pref-row zs-toggle-card"><input id="ms-sw-ad-mcp" type="checkbox"${sw.addons && sw.addons.mcp ? " checked" : ""}><span><b>Other MCP servers</b><i>Any extra MCP you configured</i></span></label>
        </div>
        <label class="zs-pref-label">Workspace folder</label>
        <div class="zs-pref-grid zs-pref-grid-3 zs-sw-root-modes">${[["ask", "◉", "Ask / picker"], ["path", "⌂", "Use this folder"], ["create", "+", "Create project"]].map(([v, icon, l]) => `<button class="zs-pref-opt${sw.rootMode === v ? " active" : ""}" data-sw-root="${v}"><b>${icon}</b><span>${l}</span></button>`).join("")}</div>
        <input id="ms-sw-root" class="zs-mcp-field" placeholder="${ZS.hostPlatform() === 'windows' ? 'C:\\Users\\you\\Projects\\MyApp' : '~/Projects/MyApp'}" value="${esc(sw.root)}"${sw.rootMode === "path" ? "" : " hidden"}>
        <input id="ms-sw-projects" class="zs-mcp-field" placeholder="New projects go in (default: ~/Multi-Script Projects)" value="${esc(sw.projectsDir)}">
        <div class="zs-menu-actions zs-sw-actions"><button id="ms-sw-pick" class="zs-mini-action zs-primary-action">⌂ Pick folder on this PC</button><button id="ms-sw-save" class="zs-mini-action">Save settings</button></div>
        <div class="zs-sw-connection"><div><b>PC bridge</b><span>Folder access and project tools use the terminal launcher registered by Setup.</span></div><div class="zs-menu-actions"><button id="ms-sw-check" class="zs-mini-action">Check</button><button id="ms-sw-repair" class="zs-mini-action">Restart bridge</button><button id="ms-sw-terminal" class="zs-mini-action">Open terminal</button></div></div>
        <div id="ms-sw-status" class="zs-sw-status" data-state="${sw.enabled ? "ok" : ""}">${sw.enabled ? `Enabled · ${sw.allowRun ? "commands allowed" : "files only"} · ${sw.rootMode === "path" && sw.root ? esc(sw.root) : sw.rootMode === "create" ? "AI creates a project folder" : "folder chosen in-session"}` : "Disabled."}</div>
      </section>` : "";
      const sp = (typeof ZSSound !== "undefined") ? ZSSound.get() : null;
      const soundHtml = sp ? `<section class="zs-menu-sec zs-sound-sec" data-zs-tab="look">
        <div class="zs-sec-label"><span>Interface sounds &amp; alerts</span><span class="zs-provider-badge">${sp.enabled ? "On" : "Off"}</span></div>
        <div class="zs-menu-note">Interface notification tones only: a ping on the final response, a tick per tool call, and a low tone on errors. These do not generate or play audio in your game. Use the previews below to hear each cue.</div>
        <div class="zs-pref-grid zs-pref-grid-2">
          <label class="zs-pref-row zs-toggle-card"><input id="ms-snd-on" type="checkbox"${sp.enabled ? " checked" : ""}><span><b>Sounds</b><i>Master switch</i></span></label>
          <label class="zs-pref-row zs-toggle-card"><input id="ms-snd-done" type="checkbox"${sp.done ? " checked" : ""}><span><b>AI finished</b><i>Ping on the final answer</i></span></label>
          <label class="zs-pref-row zs-toggle-card"><input id="ms-snd-command" type="checkbox"${sp.command ? " checked" : ""}><span><b>Command ran</b><i>Tick per tool call</i></span></label>
          <label class="zs-pref-row zs-toggle-card"><input id="ms-snd-error" type="checkbox"${sp.error ? " checked" : ""}><span><b>Errors</b><i>Low tone on failure</i></span></label>
        </div>
        <label class="zs-pref-label">Style</label><div class="zs-pref-grid zs-pref-grid-3">${[["ping", "Ping"], ["soft", "Soft"], ["arcade", "Arcade"]].map(([v, l]) => `<button class="zs-pref-opt${sp.style === v ? " active" : ""}" data-snd-style="${v}">${l}</button>`).join("")}</div>
        <label class="zs-pref-label">Volume <b id="ms-snd-vol-v">${Math.round(sp.volume * 100)}%</b></label>
        <input id="ms-snd-vol" type="range" min="0" max="100" step="5" value="${Math.round(sp.volume * 100)}">
        <div class="zs-menu-actions"><button class="zs-mini-action" data-snd-test="done">▶ Finished</button><button class="zs-mini-action" data-snd-test="command">▶ Command</button><button class="zs-mini-action" data-snd-test="error">▶ Error</button></div>
      </section>` : "";
      const motionHelpHtml=`<section class="zs-menu-sec" data-zs-tab="look" id="ms-motion-guide"><div class="zs-sec-label"><span>Interface motion and game media</span></div><div class="zs-menu-note"><b>Motion settings and live themes</b> animate Multi-Script’s menu/chatbar. Reduced motion softens these effects; None stops them. They do not animate game characters.</div><div class="zs-menu-note"><b>Game animation</b> needs a real rig, clip/AnimationId, Animator or engine animation graph, and a runtime test. <b>Game audio</b> needs a generated/imported file or usable SoundId, configured playback and an in-engine check. Use <b>Tools → Audio generation</b> for local WAV/optional cloud generation; local files still need an actual engine import/upload.</div></section>`;
      const bgHtml = X ? `<section class="zs-menu-sec zs-bg-sec" data-zs-tab="look">
        <div class="zs-sec-label"><span>Custom background</span><span class="zs-provider-badge">PNG · JPG · GIF · WebP</span></div>
        <div class="zs-menu-note">Drop in any picture or animated GIF. It auto-aligns to the settings menu (and optionally the chat bar), with adjustable transparency and blur. Stored only in this browser.</div>
        <div class="zs-bg-drop" id="ms-bg-drop">${bgImage ? `<span class="zs-bg-thumb" style="background-image:url('${bgImage}')"></span>` : ""}<span>${bgImage ? "Click or drop to replace" : "Click or drop an image / GIF here"}</span><input id="ms-bg-file" type="file" accept="image/png,image/jpeg,image/gif,image/webp" hidden></div>
        <label class="zs-pref-label">Fit</label><div class="zs-pref-grid zs-pref-grid-4">${[["cover", "Fill"], ["contain", "Fit"], ["tile", "Tile"], ["stretch", "Stretch"]].map(([v, l]) => `<button class="zs-pref-opt${bgPrefs.fit === v ? " active" : ""}" data-bg-fit="${v}">${l}</button>`).join("")}</div>
        <label class="zs-pref-label">Visibility <b id="ms-bg-op-v">${bgPrefs.opacity}%</b></label><input id="ms-bg-op" type="range" min="5" max="100" value="${bgPrefs.opacity}">
        <label class="zs-pref-label">Blur <b id="ms-bg-bl-v">${bgPrefs.blur}px</b></label><input id="ms-bg-bl" type="range" min="0" max="20" value="${bgPrefs.blur}">
        <label class="zs-pref-row"><input id="ms-bg-bar" type="checkbox"${bgPrefs.onBar ? " checked" : ""}> Also show behind the chat bar</label>
        <div class="zs-menu-actions"><button id="ms-bg-clear" class="zs-mini-action"${bgImage ? "" : " disabled"}>Remove background</button></div>
      </section>` : "";
      const TAB_DEFS = [
        ["home", "Home", '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>'],
        ["bar", "Chat bar", '<rect x="3" y="9" width="18" height="7" rx="3"/><path d="M7 12.5h4"/>'],
        ["agent", "Agent", '<path d="M12 3l2.2 5.3L20 10l-5.8 1.7L12 17l-2.2-5.3L4 10l5.8-1.7z"/>'],
        ["notion", "Notion", '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 16V8l6 8V8"/>', "notion"],
        ["look", "Look", '<circle cx="12" cy="12" r="8"/><path d="M12 4v16" /><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/>'],
        ["tools", "Tools", '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z"/>'],
        ["engines", "Engines", '<rect x="5" y="5" width="14" height="14" rx="2"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>'],
        ["sites", "AI sites", '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>'],
        ["workshop", "Skills", '<path d="M4 4h16v16H4zM8 8h8M8 12h8M8 16h4"/>'],
        ["cowork", "Co-work", '<circle cx="8" cy="8" r="3"/><circle cx="17" cy="9" r="2"/><path d="M2 21v-3a6 6 0 0 1 12 0v3M15 15a4 4 0 0 1 7 3v3"/>'],
        ["vani", "Vani", '<path d="M3 4l9 16L21 4"/>', "vani"],
        ["flight", "Code Flight", '<path d="M3 15l18-11-6 17-4-7-8 1zM11 14l10-10"/>'],
        ["ideas", "Game ideas", '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.6.5 1 1.2 1 2V16h5.2v-.2c0-.8.4-1.5 1-2A6 6 0 0 0 12 3z"/>'],
        ["software", "Code & Build", '<path d="M2 20h20"/><path d="M5 20V9l7-5 7 5v11"/><path d="M9 20v-6h6v6"/>'],
        ["help", "Help", '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7"/><path d="M12 17h.01"/>'],
        ["backstage", "Backstage", '<circle cx="8.5" cy="12" r="2.6"/><circle cx="15.5" cy="12" r="2.6"/><path d="M3 12c2-5 16-5 18 0"/>', null, "fnaf"],
      ];
      menuEl.innerHTML =
        `<div class="zs-menu-head"><span class="zs-menu-logo">Multi-Script</span><span class="zs-menu-tag">v${EXT_VERSION}</span><span class="zs-menu-health ${A.bridge && A.bridge.connected ? "on" : "off"}">${A.bridge && A.bridge.connected ? "online" : "offline"}</span>
           <label class="zs-menu-search"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg><input id="zs-menu-q" type="search" placeholder="Search settings" autocomplete="off" spellcheck="false" aria-label="Search settings"></label>
           <button id="zs-menu-x" class="zs-menu-x" aria-label="Close settings" title="Close (Esc)">✕</button></div>
         <div class="zs-menu-body">
         <nav class="zs-menu-tabs" role="tablist" aria-label="Settings categories">${SETTINGS_GROUPS.map(([group,ids])=>{const tabs=ids.map(id=>TAB_DEFS.find(t=>t[0]===id)).filter(t=>t&&(!t[3]||t[3]===P.id)&&(!t[4]||(t[4]==="fnaf"&&menuPrefs.theme==="fnaf")));return tabs.length?`<span class="ms-nav-group">${group}</span>${tabs.map(([id,label,icon])=>`<button type="button" id="ms-nav-${id}" data-tab="${id}" role="tab" aria-controls="zs-pane" title="${label}"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${icon}</svg><span>${label}</span></button>`).join('')}`:'';}).join('')}</nav>
         <div class="zs-pane" id="zs-pane"><div id="ms-settings-page" class="ms-page-heading"></div>
         ${homeQuickHtml}
         ${barHtml}
         ${setupTutorialHtml}
         ${menuPrefs.showOverview ? overviewHtml : ""}
         ${appearanceHtml}
         ${menuPrefs.theme === "fnaf" ? fnafBackstageHtml() : ""}
         ${mediaHtml}
         ${effortHtml}${criticHtml}
         ${providerBehaviorHtml}
         ${creativeSurfaceHtml}
         ${qualityHtml}
         ${enhanceHtml}
         ${usageHtml}
         ${notionTabHtml}
         ${notionProfileHtml}
         ${autonomyHtml}
         ${verificationHtml}
         ${reliabilityHtml}
         ${pacingHtml}
         ${surfaceHtml}
         ${soundHtml}${motionHelpHtml}
         ${bgHtml}
         ${studioHubHtml()}
         ${ideasHtml}
         ${wipHtml}
         <section class="zs-menu-sec" data-zs-tab="sites">
           <div class="zs-sec-label"><span>Switch AI</span></div>
           ${sites}
         </section>
         ${benchmarksHtml}
         <section class="zs-menu-sec zs-elevenlabs-sec" data-zs-tab="interface">
           <div class="zs-sec-label"><span>Audio generation</span><span class="zs-secret-state ${elevenLabsState.configured ? "on" : "off"}">${elevenLabsState.loading ? "checking" : elevenLabsState.elevenLabsConfigured ? "local + cloud" : "local ready"}</span></div>
           <div class="zs-menu-note">Free local sound generation is ready without an account, network request, or API key. ElevenLabs remains an optional cloud-quality provider: if supplied, its key is sent only to the local bridge, stored in <b>runtime/.env</b> with private permissions, and never saved in browser storage, prompts, chats, diagnostics, or release ZIPs.</div>
           <div class="zs-secret-field"><input id="ms-elevenlabs-key" type="password" autocomplete="off" spellcheck="false" placeholder="Paste your own ElevenLabs API key"><button id="ms-elevenlabs-reveal" class="zs-mini-action" type="button">Show</button></div>
           <div class="zs-menu-actions"><button id="ms-elevenlabs-save" class="zs-mini-action">Save key locally</button><button id="ms-elevenlabs-remove" class="zs-mini-action" ${elevenLabsState.elevenLabsConfigured ? "" : "disabled"}>Remove key</button><button id="ms-elevenlabs-refresh" class="zs-mini-action">Refresh status</button></div>
           <div id="ms-elevenlabs-message" class="zs-menu-note">${elevenLabsState.error ? esc(elevenLabsState.error) : elevenLabsState.elevenLabsConfigured ? "Local audio and optional ElevenLabs cloud generation are ready." : "Local audio is ready now; an ElevenLabs key is optional for complex cloud-generated sounds."}</div>
         </section>
         <section class="zs-menu-sec" data-zs-tab="agent">
           <div class="zs-sec-label"><span>Custom instructions</span></div>
           <div class="zs-menu-note">Added below the system prompt on every new session. The built-in prompt can't be edited.</div>
           <textarea id="zs-set-text" rows="4" placeholder="e.g. Always comment your Luau code. Prefer small modular scripts."></textarea>
           <div class="zs-set-row"><button id="zs-set-save">Save</button><span id="zs-set-status"></span></div>
         </section>
         <section class="zs-menu-sec" data-zs-tab="engines">
           <div class="zs-sec-label"><span>Bridge</span><span class="zs-provider-badge" id="zs-br-badge">${A.bridge && A.bridge.connected ? "online" : "offline"}</span></div>
           <div class="zs-menu-note">The terminal icon in the chat bar runs the bridge for you — no .bat file to keep open. Its caret lists everything running (bridge, MCP servers, engine apps).</div>
           <div class="zs-menu-actions"><button id="zs-br-open" class="zs-mini-action">Open terminal</button><button id="zs-br-start" class="zs-mini-action">Start</button><button id="zs-br-restart" class="zs-mini-action">Restart</button><button id="zs-br-stop" class="zs-mini-action">Stop</button></div>
           <label class="zs-pref-row"><input id="zs-br-auto" type="checkbox"> Start it automatically when an AI site opens</label>
           <div id="zs-br-status" class="zs-menu-note"></div>
         </section>
         <section class="zs-menu-sec" data-zs-tab="engines">
           <div class="zs-sec-label"><span>Active engines</span><span class="zs-provider-badge" id="ms-eng-badge">saved</span></div>
           <div class="zs-menu-note">Choose which engines Multi-Script may use. A switched-off engine is not started, not probed, its tools are hidden from the AI and its calls are refused. The choice is saved on this PC and kept across restarts.</div>
           <div id="ms-engine-toggles" class="zs-pref-row">${["roblox", "unity", "godot", "blender"].map((id) => `<label><input type="checkbox" class="ms-eng-toggle" data-engine="${id}" checked> <span>${({ roblox: "Roblox Studio", unity: "Unity", godot: "Godot", blender: "Blender" })[id]}</span><i class="ms-eng-note" data-note="${id}"></i></label>`).join("")}</div>
           <div id="ms-eng-status" class="zs-menu-note"></div>
         </section>
         <section class="zs-menu-sec" data-zs-tab="engines">
           <div class="zs-sec-label"><span>Engine setup guides</span><span class="zs-provider-badge">step by step</span></div>
           <div class="zs-menu-note">Pick the card for the engine you want. Each guide lists exactly what to install, what to click, and ends with a one-line check you can paste into chat to prove the connection works.</div>
           ${engineGuidesHtml}
         </section>
         <section class="zs-menu-sec" data-zs-tab="engines">
           <div class="zs-sec-label"><span>Engines & MCP servers</span></div>
           <div class="zs-setting-title">Blender Workspace</div>
           <p class="zs-menu-note">A dedicated modeling and animation tab with a Three.js viewport, inspector and timeline, powered by real Blender in the background. Models, rigs and keyframes save to a local .blend. No Blender window or MCP add-on is needed. Setup prepares the portable runtime; the workspace can finish preparation if needed.</p>
           <div class="zs-setting-title">Include Blender with a game engine</div><p class="zs-menu-note">Switch this on once for the engines you use. Pressing Start for that connected engine also prepares the Blender workspace before the AI starts. Your game editor still needs its normal Multi-Script/MCP connection. Chat Studio stays engine-free.</p><div class="zs-pref-row">${[['roblox','Roblox Studio'],['unity','Unity'],['godot','Godot']].map(([id,label])=>`<label><input type="checkbox" class="ms-blender-companion" value="${id}"> ${label} + Blender</label>`).join('')}</div><p id="ms-blender-companion-note" class="zs-menu-note" role="status">Reading companion settings…</p><div class="zs-menu-actions"><button id="ms-blender-workspace-open" class="zs-mini-action zs-primary-action">Open Blender Workspace</button></div><p id="ms-blender-workspace-status" class="zs-menu-note" role="status">Open a project there, then use Start Blender agent here. Your existing desktop Blender connection stays available as a separate target.</p>
           <div class="zs-menu-note">Live status distinguishes a running MCP process from a connected editor. Bundled Roblox, Unity, and Godot entries are protected. Add Blender, Unreal, or another verified stdio MCP command below.</div>
           <div class="zs-setting-title">Blockbench assets</div>
           <p class="zs-menu-note">Create and edit .bbmodel assets, meshes, UVs, textures and animations through a headless file workspace. Preparation downloads pinned dependencies once. Rendering is optional and needs Node.js 24+ plus a compatible GPU. Your existing editors and models stay in place.</p>
           <div class="zs-menu-actions"><button id="ms-blockbench-prepare" type="button" class="zs-mini-action">Prepare Blockbench</button><button id="ms-blockbench-render" type="button" class="zs-mini-action">Prepare rendering</button></div>
           <p id="ms-blockbench-status" class="zs-menu-note" role="status" aria-live="polite">Reading Blockbench workspace status…</p>
           <div class="zs-setting-title">Obsidian memory vault</div>
           <p class="zs-menu-note">Setup creates Multi-Script Memory in this installation’s root folder and connects it to the bridge. Skills, tools, Ultra manuals and OMNI references are seeded there. Large archives, images and videos stay in the vault and are excluded from extension packages and updates. The file backend works without an Obsidian account or plugin. To use the Obsidian app, open this folder as a vault; sync is configured separately.</p>
           <input id="ms-vault-path" class="zs-mcp-field" aria-label="Obsidian vault folder" placeholder="Leave blank to use the installation’s Multi-Script Memory folder" />
           <div class="zs-menu-actions"><button id="ms-vault-connect" type="button" class="zs-mini-action">Connect / create vault</button></div>
           <input id="ms-vault-import-path" class="zs-mcp-field" aria-label="Reference file to import" placeholder="Full path to an OMNI archive, image, PDF or video" />
           <div class="zs-menu-actions"><button id="ms-vault-import" type="button" class="zs-mini-action">Import reference file</button></div>
           <p id="ms-vault-status" class="zs-menu-note" role="status" aria-live="polite">Reading vault connection…</p>
           ${mcpList}
           <div class="zs-mcp-sep"></div>
           <input id="zs-mcp-name" class="zs-mcp-field" placeholder="Name, e.g. Unity, Godot, Unreal or Blender" />
           <input id="zs-mcp-url" class="zs-mcp-field" placeholder="MCP start command from the server documentation" />
           <div class="zs-set-row"><button id="zs-mcp-add">Add addon</button><span id="zs-mcp-status"></span></div>
           <div class="zs-menu-actions"><button id="zs-refresh-bridge" class="zs-mini-action">Refresh status</button><button id="zs-restart-bridge" class="zs-mini-action">Restart MCP servers</button></div>
         </section>
         <section class="zs-menu-sec" data-zs-tab="help">
           <div class="zs-sec-label"><span>Updates</span><span class="zs-provider-badge">Dev channel</span></div>
           <div class="zs-menu-note">Signed updates download in the background when publisher hosting is configured. Stop active sessions, then apply and reload. Your browser settings and private project data stay in place.</div>
           <label class="zs-menu-note"><input type="checkbox" id="ms-update-auto" checked> Check and download updates automatically</label>
           <div class="zs-menu-actions"><button id="ms-update-check" class="zs-mini-action">Check for updates</button><button id="ms-update-apply" class="zs-mini-action" disabled>Apply &amp; reload extension</button></div>
           <div id="ms-update-status" class="zs-menu-note" role="status" aria-live="polite">Open this section to check update setup.</div>
           <progress id="ms-update-progress" max="100" hidden aria-label="Update progress" style="width:100%;height:8px;accent-color:var(--ms-accent,#8b7cf8)"></progress>
           <div id="ms-update-detail" class="zs-menu-note" style="overflow-wrap:anywhere"></div>
           <details class="zs-menu-note"><summary>Setup checklist &amp; manual download</summary><p>Load the extension folder from a permanent, complete Dev installation. Run Setup.bat (Windows), MacOS_Setup.command (macOS), or Setup.sh (Linux) from that same folder. Keep your existing browser profile and private runtime data.</p><p><a href="https://github.com/krazydarky-code/Multi-Script/releases/latest" target="_blank" rel="noopener noreferrer">Open official Dev downloads</a>. After an update, refresh provider tabs. Replace separately installed editor plugins when their version changes.</p></details>
         </section>
         <section class="zs-menu-sec" data-zs-tab="help">
           <div class="zs-sec-label"><span>Settings backup</span><span class="zs-provider-badge">validated</span></div>
           <div class="zs-menu-note">Copy or restore appearance, every provider’s behavior, specialist depth, usage optimization, custom instructions, and the Notion preferred-model request. Secrets, API keys, MCP launch commands, and runtime state are deliberately excluded.</div>
           <div class="zs-menu-actions"><button id="ms-copy-settings" class="zs-mini-action">Copy settings</button><button id="ms-import-settings" class="zs-mini-action">Import from clipboard</button></div>
         </section>
         <section class="zs-menu-sec" data-zs-tab="help">
           <div class="zs-sec-label"><span>Troubleshooting</span></div>
           <div class="zs-menu-note">Copy a privacy-safe snapshot of provider, bridge, engine, and tool status for bug reports.</div>
           <div class="zs-menu-actions"><button id="zs-provider-selftest" class="zs-mini-action">Test provider</button><button id="zs-copy-diagnostics" class="zs-mini-action">Copy diagnostics</button><button id="zs-reload-page" class="zs-mini-action">Reload page</button></div>
         </section>
         <div class="zs-empty" hidden>No settings match your search.</div>
         </div></div>`;
      neutralizeFormButtons(menuEl);
      organizeMenu();
      const open = (url) => { try { window.open(url, "_blank", "noopener"); } catch {} menuEl.hidden = true; };
      menuEl.querySelectorAll(".zs-menu-tabs button").forEach((b) => b.addEventListener("click", () => { menuQuery = ""; const q = menuEl.querySelector("#zs-menu-q"); if (q) q.value = ""; applyMenuTab(b.dataset.tab); }));
      menuEl.querySelector('.zs-menu-tabs')?.addEventListener('keydown',event=>{
        if(!['ArrowDown','ArrowUp','Home','End'].includes(event.key))return;
        const tabs=[...menuEl.querySelectorAll('.zs-menu-tabs button')],index=tabs.indexOf(document.activeElement);
        if(index<0)return;event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowDown'?1:-1)+tabs.length)%tabs.length;tabs[next].click();tabs[next].focus();
      });
      const searchBox = menuEl.querySelector("#zs-menu-q");
      if (searchBox) { searchBox.value = menuQuery; searchBox.addEventListener("input", () => { menuQuery = searchBox.value; applyMenuFilter(); }); }
      const closeBtn = menuEl.querySelector("#zs-menu-x"); if (closeBtn) closeBtn.addEventListener("click", () => { menuEl.hidden = true; });
      applyMenuTab(menuTab, true);
      if (menuQuery) applyMenuFilter();
      { const pn = menuEl.querySelector("#zs-pane"); if (pn && prevScroll) pn.scrollTop = prevScroll; const qi = menuEl.querySelector("#zs-menu-q"); if (qi && prevFocusQ) { qi.focus(); try { qi.setSelectionRange(qi.value.length, qi.value.length); } catch {} } }
      menuEl.querySelectorAll("[data-go-tab]").forEach((b) => b.addEventListener("click", () => { menuQuery = ""; const q = menuEl.querySelector("#zs-menu-q"); if (q) q.value = ""; applyMenuTab(b.dataset.goTab); }));
      bindNotionTab();
      bindBridgeSection();
      const updatePanel=MSUpdatePanel.mount(menuEl.querySelector('#ms-update-status')?.parentElement,{send:msg=>bg({type:'ms_update_admin',...msg})});
      if(menuTab==='help')void updatePanel.refresh();
      const benchSearch=menuEl.querySelector('#ms-bench-search'),benchFilter=menuEl.querySelector('#ms-bench-filter');
      const filterBench=()=>{let count=0;const query=(benchSearch?.value||'').trim().toLowerCase();menuEl.querySelectorAll('.ms-bench-card').forEach(card=>{card.hidden=!(card.dataset.benchName.includes(query)&&(benchFilter.value!=='current'||card.dataset.provider===P.id));if(!card.hidden)count++;});const label=menuEl.querySelector('#ms-bench-count');if(label)label.textContent=count+' of '+(ZS.PROVIDER_BENCHMARKS||[]).length+' providers';};
      benchSearch?.addEventListener('input',filterBench);benchFilter?.addEventListener('change',filterBench);filterBench();
      menuEl.querySelector('#ms-bench-check')?.addEventListener('click',()=>{const line=menuEl.querySelector('#ms-bench-result');try{const check=P.selfTest?.()||{ready:!!P.getEditor(),composer:!!P.getEditor()};line.textContent=(P.displayName||P.id)+': '+(check.ready?'composer ready':'needs attention')+' · '+(A.bridge?.connected?'bridge connected':'bridge offline')+' · '+(P.isGenerating()?'provider answering':'provider idle')+(check.warning?' · '+check.warning:'')+'. A local check does not certify a model response.';}catch(error){line.textContent='Check failed: '+error.message;}});
      bindEngineGuides();
      bindEngineToggles();
      bindExtrasSections();
      bindStudioHub();
      bindFnafTab();
      ensureFnafLayer();
      try { ensureSceneLayer(); ensureBarScene(); } catch {}
      const setupCheck = menuEl.querySelector("#ms-setup-check");
      if (setupCheck) setupCheck.addEventListener("click", async () => {
        setupCheck.disabled = true;
        const status = await bg({ type: "status" });
        const provider = P.selfTest ? P.selfTest() : { ready: !!(P.getEditor && P.getEditor()) };
        const engines = (status && Array.isArray(status.engines) ? status.engines : []).filter((x) => x && x.connected === true);
        const lines = [
          `Bridge: ${status && status.connected ? "online" : "offline — click the terminal icon in the bar to start it"}`,
          `Editor/MCP: ${engines.length ? engines.map((x) => x.id).join(", ") + " connected" : "none connected — open the editor and enable its MCP server"}`,
          `${P.displayName || P.id}: ${provider.ready ? "composer detected" : (provider.recommendation || "composer not detected")}`,
        ];
        ui.banner(status && status.connected && provider.ready ? "ok" : "warn", "Multi-Script setup check", lines.join("\n"));
        setupCheck.disabled = false;
      });
      const copySetup = menuEl.querySelector("#ms-copy-setup");
      if (copySetup) copySetup.addEventListener("click", async () => {
        const text = [
          "Multi-Script setup checklist",
          "1. Extract the full release ZIP.",
          "2. Load the extension folder at chrome://extensions or edge://extensions, then reload the extension after updates.",
          "3. One time only: run Setup.bat (Windows), MacOS_Setup.command (macOS) or bash Setup.sh (Linux) so the terminal icon can start the bridge. After that, just click the terminal icon in the chat bar.",
          "4. Open the target editor/project and enable its MCP server, or add its verified stdio command under Engines.",
          "5. For Notion AI open https://app.notion.com/chat — not workspace Connectors.",
          "6. Press Start in the Multi-Script bar and run a small read-only check first.",
        ].join("\n");
        try { await navigator.clipboard.writeText(text); toast("Setup checklist copied"); } catch { toast("Could not copy setup checklist"); }
      });
      const defaultTabSelect = menuEl.querySelector("#ms-default-tab");
      if (defaultTabSelect) { defaultTabSelect.value = menuPrefs.defaultTab; defaultTabSelect.addEventListener("change", () => { menuPrefs.defaultTab = defaultTabSelect.value; saveMenuPrefs(); }); }
      const showOverview = menuEl.querySelector("#ms-show-overview");
      if (showOverview) showOverview.addEventListener("change", () => { menuPrefs.showOverview = showOverview.checked; saveMenuPrefs(); buildMenu(); });
      menuEl.querySelectorAll(".zs-accent-opt").forEach((b) => b.addEventListener("click", () => { menuPrefs.accent = b.dataset.accent; menuPrefs.accentUser = true; saveMenuPrefs(); buildMenu(); }));
      menuEl.querySelectorAll("[data-density]").forEach((b) => b.addEventListener("click", () => { menuPrefs.density = b.dataset.density; saveMenuPrefs(); buildMenu(); }));
      menuEl.querySelectorAll("[data-width]").forEach((b) => b.addEventListener("click", () => { menuPrefs.width = b.dataset.width; saveMenuPrefs(); buildMenu(); }));
      menuEl.querySelectorAll("[data-theme]").forEach((b) => b.addEventListener("click", () => {
        const was = menuPrefs.theme; menuPrefs.theme = b.dataset.theme;
        if (was === "fnaf" && menuPrefs.theme !== "fnaf" && menuTab === "backstage") menuTab = "look";
        if (menuPrefs.theme === "fnaf" && was !== "fnaf") {
          fnafOnSelect();
        }
        saveMenuPrefs(); buildMenu();
      }));
      for (const key of ["scale","font","radius","backdrop","motion"]) menuEl.querySelectorAll(`[data-${key}]`).forEach((b) => b.addEventListener("click", () => { menuPrefs[key]=b.dataset[key]; saveMenuPrefs(); buildMenu(); }));
      const customAccent=menuEl.querySelector("#ms-custom-accent"); if(customAccent) customAccent.addEventListener("input",()=>{menuPrefs.accent=customAccent.value;menuPrefs.accentUser=true;saveMenuPrefs();});
      const saveIdentity=menuEl.querySelector("#ms-save-identity"); if(saveIdentity) saveIdentity.addEventListener("click",()=>{ menuPrefs.brandIcon=(menuEl.querySelector("#ms-brand-icon").value||"✦").slice(0,3); menuPrefs.brandName=(menuEl.querySelector("#ms-brand-name").value.trim()||"Multi-Script").slice(0,28); menuPrefs.tagline=menuEl.querySelector("#ms-brand-tagline").value.trim().slice(0,60); saveMenuPrefs(); buildMenu(); toast("Identity saved"); });
      const resetMenu = menuEl.querySelector("#ms-reset-menu");
      if (resetMenu) resetMenu.addEventListener("click", () => { menuPrefs = { ...DEFAULT_MENU_PREFS }; menuTab = "look"; saveMenuPrefs(); buildMenu(); toast("Appearance reset"); });
      bindEnhancePanel(menuEl);
      bindMediaPanel(menuEl);
      bindSurfacePanel(menuEl);
      bindBarPanel();
      const resetAgentSettings=menuEl.querySelector("#ms-reset-agent-settings");
      if(resetAgentSettings) resetAgentSettings.addEventListener("click",()=>{ providerBehaviorMap[P.id]={...DEFAULT_PROVIDER_BEHAVIOR}; skillDepth="full"; usageMode="balanced"; paceSettings=ZSPace.sanitize(ZSPace.DEFAULT_SETTINGS); resilienceSettings=ZSResilience.sanitize(ZSResilience.DEFAULT_SETTINGS); verificationSettings=ZSVerify.sanitize(ZSVerify.DEFAULT_SETTINGS); A.verifyState=ZSVerify.initialState(); autonomyLevel="guided"; criticSettings=MSStudio.sanitizeCritic(null); executionEffort="adaptive"; syncExecutionEffortUI(); studioSettingsDirty=true; try{chrome.storage.local.set({msCriticSettings:criticSettings,msExecutionEffort:executionEffort,msProviderBehavior:providerBehaviorMap,zsSkillToolDepth:skillDepth,zsUsageOptimizer:usageMode,msPacingSettings:paceSettings,msResilienceSettings:resilienceSettings,msVerificationSettings:verificationSettings,zsAutonomyLevel:autonomyLevel});}catch{} buildMenu(); toast(`${P.displayName||P.id}: agent behavior reset`); });
      menuEl.querySelectorAll("[data-creative-surface]").forEach((b) => b.addEventListener("click", () => {
        setProviderBehavior({ creativeSurface: b.dataset.creativeSurface }); buildMenu(); toast(`${P.displayName || P.id}: ${b.dataset.creativeSurface} creative routing`);
      }));
      menuEl.querySelectorAll("[data-creative-style]").forEach((b) => b.addEventListener("click", () => {
        setProviderBehavior({ creativeStyle: b.dataset.creativeStyle }); buildMenu(); toast(`${P.displayName || P.id}: ${b.textContent.trim()} art direction`);
      }));
      menuEl.querySelectorAll("[data-asset-workflow]").forEach((b) => b.addEventListener("click", () => {
        setProviderBehavior({ assetWorkflow: b.dataset.assetWorkflow }); buildMenu(); toast(`${P.displayName || P.id}: ${b.dataset.assetWorkflow} asset workflow`);
      }));
      menuEl.querySelectorAll("[data-creative-finish]").forEach((b) => b.addEventListener("click", () => {
        setProviderBehavior({ creativeFinish: b.dataset.creativeFinish }); buildMenu(); toast(`${P.displayName || P.id}: ${b.dataset.creativeFinish} finish`);
      }));
            menuEl.querySelectorAll("[data-prompt-skills]").forEach((b) => b.addEventListener("click", () => {
        setProviderBehavior({ promptSkills: b.dataset.promptSkills }); buildMenu(); toast(`${P.displayName || P.id}: prompt rewriting ${b.dataset.promptSkills}`);
      }));
      menuEl.querySelectorAll("[data-loop-mode]").forEach((b) => b.addEventListener("click", () => {
        setProviderBehavior({ loops: b.dataset.loopMode }); buildMenu(); toast(`${P.displayName || P.id}: ${b.dataset.loopMode} production`);
      }));
      menuEl.querySelectorAll(".zs-quality-opt").forEach((b) => b.addEventListener("click", () => {
        skillDepth = b.dataset.skillDepth || "full";
        try { chrome.storage.local.set({ zsSkillToolDepth: skillDepth }); } catch {}
        buildMenu(); toast(`Studio skill coverage: ${skillDepth}`);
      }));
      menuEl.querySelectorAll(".zs-economy-opt").forEach((b) => b.addEventListener("click", () => {
        usageMode = b.dataset.economy || "balanced";
        try { chrome.storage.local.set({ zsUsageOptimizer: usageMode }); } catch {}
        buildMenu(); toast(`Usage optimizer: ${usageMode}`);
      }));
      // Reply pacing: mode presets. Changing the mode re-derives the effective
      // profile for THIS provider immediately (no reload, no restart). When the
      // scope toggle is on, the choice is stored as a per-provider override so
      // the other sites keep the global setting.
      menuEl.querySelectorAll("[data-pace-mode]").forEach((b) => b.addEventListener("click", () => {
        const mode = b.dataset.paceMode;
        const s = getPaceSettings();
        const scoped = !!(s.perProvider || {})[P.id];
        if (scoped) setPaceSettings({ perProvider: { ...s.perProvider, [P.id]: { ...s.perProvider[P.id], mode } } });
        else setPaceSettings({ mode });
        buildMenu();
        toast(`Reply pacing: ${(ZSPace.MODES[mode] || {}).label || mode}${scoped ? ` (${P.displayName || P.id} only)` : ""}`);
      }));
      const paceScopeEl = menuEl.querySelector("#ms-pace-scope");
      if (paceScopeEl) paceScopeEl.addEventListener("change", () => {
        const s = getPaceSettings();
        const per = { ...(s.perProvider || {}) };
        if (paceScopeEl.checked) per[P.id] = { mode: s.mode === "custom" ? "human" : s.mode };
        else delete per[P.id];
        setPaceSettings({ perProvider: per });
        buildMenu();
        toast(paceScopeEl.checked
          ? `Pacing scoped to ${P.displayName || P.id} (other sites unchanged)`
          : "Pacing follows the global setting again");
      });
      const typingSimEl = menuEl.querySelector("#ms-typing-sim");
      if (typingSimEl) typingSimEl.addEventListener("change", () => {
        setPaceSettings({ typingSim: typingSimEl.checked });
        buildMenu();
      });
      // In-browser pacing check: runs the SAME engine the loop uses over a
      // simulated session and reports the real numbers, so "is the pacing
      // actually doing something on my machine" is answerable without reading
      // code or watching a live run.
      const paceTestEl = menuEl.querySelector("#ms-pace-test");
      if (paceTestEl) paceTestEl.addEventListener("click", () => {
        const s = getPaceSettings();
        const prof = ZSPace.profileFor(s, P.id);
        if (ZSPace.isOff(prof)) {
          ui.banner("warn", "Pacing is off",
            "Turns are sent immediately, as before. Pick Brisk, Human-like or Cautious to add a randomised gap, a periodic longer break and an error cooldown.");
          return;
        }
        const seq = ZSPace.planSequence(s, P.id, 30);
        const st = ZSPace.stats(seq);
        const secs = (ms) => `${(ms / 1000).toFixed(1)}s`;
        const mmss = (ms) => `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
        const longBreaks = seq.filter((_, i) => prof.longEvery > 0 && i > 0 && i % prof.longEvery === 0).length;
        const rl = ZSResilience.policy(rlevel());
        ui.banner("ok", `Pacing check · ${(ZSPace.MODES[s.mode] || {}).label || s.mode}`,
          `30 simulated turns → mean ${secs(st.mean)}, min ${secs(st.min)}, max ${secs(st.max)}, ` +
          `${longBreaks} longer break${longBreaks === 1 ? "" : "s"}.\n` +
          `A 30-step unattended run (≈60 sends) would add about ${mmss(st.totalMs * 2)}.\n` +
          `${prof.errorCooldownMs > 0 ? `After any error the next turn waits at least ${secs(prof.errorCooldownMs)}. ` : ""}` +
          `Error recovery: ${rl.label}${rl.maxRetries ? ` · up to ${rl.maxRetries} retries per failure, gives up after ${rl.maxConsecutive} in a row` : " · a failure ends the run"}.`);
      });
      {
        const wire = (id, modeKey, charsKey) => {
          const sel = menuEl.querySelector("#" + id), num = menuEl.querySelector("#" + id + "-chars");
          if (!sel || !num) return;
          const save = () => { ZS.limits.set({ [modeKey]: sel.value, [charsKey]: Number(num.value) }); num.disabled = sel.value !== "custom"; num.value = ZS.limits.get()[charsKey]; refreshLimitsSummary(); toast(`Limits saved: ${sel.value === "off" ? "no limit" : sel.value === "custom" ? num.value + " characters" : "automatic"}`); };
          sel.addEventListener("change", save); num.addEventListener("change", save);
        };
        const refreshLimitsSummary = () => {
          const box = menuEl.querySelector("#ms-lim-summary");
          if (box) box.innerHTML = ZS.limits.describe(ZS.limits.get()).map((d) => `<div${d.level === "warn" ? ' style="color:#ffb454"' : ""}>${d.level === "warn" ? "⚠ " : ""}${esc(d.text)}</div>`).join("");
        };
        wire("ms-lim-result", "resultMode", "resultChars"); wire("ms-lim-send", "sendMode", "sendChars");
        const sv = menuEl.querySelector("#ms-lim-salvage");
        if (sv) sv.addEventListener("change", () => { ZS.limits.set({ salvage: sv.checked }); refreshLimitsSummary(); toast(sv.checked ? "Cut-off commands are auto-closed" : "Cut-off commands are reported instead"); });
        const rs = menuEl.querySelector("#ms-lim-reset");
        if (rs) rs.addEventListener("click", () => {
          const D = ZS.limits.DEFAULTS; ZS.limits.set({ ...D });
          for (const [id, mk, ck] of [["ms-lim-result", "resultMode", "resultChars"], ["ms-lim-send", "sendMode", "sendChars"]]) {
            const a = menuEl.querySelector("#" + id), b = menuEl.querySelector("#" + id + "-chars");
            if (a) a.value = D[mk]; if (b) { b.value = D[ck]; b.disabled = true; }
          }
          if (sv) sv.checked = D.salvage;
          refreshLimitsSummary(); toast("Limits reset to automatic");
        });
      }
      const keepHid = menuEl.querySelector("#ms-keep-hidden");
      if (keepHid) keepHid.addEventListener("change", () => {
        keepRunningHidden = keepHid.checked;
        try { chrome.storage.local.set({ msKeepRunningHidden: keepRunningHidden }); } catch {}
        toast(keepRunningHidden ? "Agent keeps running in the background" : "Agent pauses while the tab is hidden");
      });
      // Error recovery level.
      menuEl.querySelectorAll("[data-recovery]").forEach((b) => b.addEventListener("click", () => {
        const level = b.dataset.recovery;
        setResilienceSettings({ level });
        buildMenu();
        toast(`Error recovery: ${(ZSResilience.LEVELS[level] || {}).label || level}`);
      }));
      // Verification handling mode. Selecting a mode that can activate the
      // assisted click also states the hard limit in the toast, so the boundary
      // is never a surprise later.
      menuEl.querySelectorAll("[data-verify]").forEach((b) => b.addEventListener("click", () => {
        const id = b.dataset.verify;
        const m = setVerificationSettings({ mode: id });
        const applied = ZSVerify.modeFor(m, P.id);
        if (applied.id === "assist" || applied.id === "unattended") {
          // Reset the adaptive floor when the user changes intent, so a previous
          // bad patch does not slow a deliberate new setting.
          A.verifyState = ZSVerify.initialState();
        }
        buildMenu();
        toast(`Verification: ${applied.label}${applied.assist ? " · clicks the site's own widget once, never solves it" : ""}`);
      }));
      const verifyAudible = menuEl.querySelector("#zs-verify-audible");
      if (verifyAudible) verifyAudible.addEventListener("change", () => {
        setVerificationSettings({ audibleAlert: !!verifyAudible.checked });
        toast(verifyAudible.checked ? "Verification alert: on" : "Verification alert: off");
      });
      // Autonomy. One-shot is only genuinely one-shot if it can survive stalls
      // and is not the thing that gets flagged, so selecting it raises those two
      // floors unless the user has deliberately chosen something else.
      menuEl.querySelectorAll("[data-autonomy]").forEach((b) => b.addEventListener("click", () => {
        const lvl = setAutonomyLevel(b.dataset.autonomy);
        if (lvl === "oneShot") {
          if (getResilienceSettings().level !== "persistent") setResilienceSettings({ level: "persistent" });
          if (getPaceSettings().mode === "off") setPaceSettings({ mode: "human" });
          toast("One-shot: no questions · persistent recovery · human pacing");
        } else {
          toast("Autonomy: guided");
        }
        buildMenu();
      }));
      menuEl.querySelector("#ms-critic-enabled")?.addEventListener("change", e => { setCriticSettings({enabled:e.target.checked}); buildMenu(); });
      menuEl.querySelector("#ms-critic-passes")?.addEventListener("change", e => { setCriticSettings({passes:Number(e.target.value)}); });
      const effortSlider = menuEl.querySelector("#ms-effort-slider");
      for(const [id,key] of [['ms-ultra-palette','ultraPalette'],['ms-ultra-animation','ultraAnimation']])menuEl.querySelector('#'+id)?.addEventListener('change',e=>{menuPrefs[key]=e.target.value;saveMenuPrefs();});
      if (effortSlider) effortSlider.addEventListener("input", () => {
        const id = setExecutionEffort(EFFORT_ORDER[Number(effortSlider.value)]);
        effortSlider.setAttribute("aria-valuetext", EXECUTION_EFFORTS[id].label);
        menuEl.querySelector("#ms-effort-label").textContent = EXECUTION_EFFORTS[id].label;
        menuEl.querySelector("#ms-effort-hint").textContent = EXECUTION_EFFORTS[id].hint;
      });
      menuEl.querySelectorAll("[data-effort]").forEach((b) => b.addEventListener("click", () => {
        const id = setExecutionEffort(b.dataset.effort);
        buildMenu();
        toast(`Execution effort: ${EXECUTION_EFFORTS[id].label}`);
      }));
      const checkProfile = menuEl.querySelector("#zs-check-profile");
      if (checkProfile) checkProfile.addEventListener("click", () => { const d=P.routingProfileDiagnostics ? P.routingProfileDiagnostics() : null; const st=menuEl.querySelector("#zs-profile-status"); if(st) st.textContent=d && d.promptReady ? (d.modelTargeted ? `Model-targeted routing ready · requests exact ${d.requestedModel} every turn · ${d.dynamicCapabilities.length} capability signals · no direct picker` : d.perTurnRouting ? `Untargeted Direct Max ready · re-evaluates every turn · no direct picker` : `Preference text ready · choose the actual model in the provider`) : "Standard Auto · no routing request"; });
            const copyProfile = menuEl.querySelector("#zs-copy-profile");
      if (copyProfile) copyProfile.addEventListener("click", async () => {
        const text = P.getStartupProfilePrompt ? P.getStartupProfilePrompt() : "";
        if (!text) return;
        try { await navigator.clipboard.writeText(text); toast("Starter prompt copied"); } catch { toast("Could not copy starter prompt"); }
      });
      const elKey=menuEl.querySelector("#ms-elevenlabs-key"),elMsg=menuEl.querySelector("#ms-elevenlabs-message"),elSave=menuEl.querySelector("#ms-elevenlabs-save"),elRemove=menuEl.querySelector("#ms-elevenlabs-remove"),elReveal=menuEl.querySelector("#ms-elevenlabs-reveal"),elRefresh=menuEl.querySelector("#ms-elevenlabs-refresh");
      if(elReveal) elReveal.addEventListener("click",()=>{elKey.type=elKey.type==="password"?"text":"password";elReveal.textContent=elKey.type==="password"?"Show":"Hide";});
      if(elSave) elSave.addEventListener("click",async()=>{const key=elKey.value.trim();if(!key){elMsg.textContent="Paste your own key first.";return;}elSave.disabled=true;elMsg.textContent="Saving securely to the local bridge…";const r=await bg({type:"elevenlabs_configure",api_key:key});elKey.value="";if(r&&r.ok){elevenLabsState={...r.status,loading:false};toast("ElevenLabs key saved locally");buildMenu();}else{elSave.disabled=false;elMsg.textContent=(r&&r.error)||"Could not save key";}});
      if(elRemove) elRemove.addEventListener("click",async()=>{elRemove.disabled=true;const r=await bg({type:"elevenlabs_clear"});if(r&&r.ok){elevenLabsState={...r.status,loading:false};toast("ElevenLabs key removed");buildMenu();}else{elRemove.disabled=false;elMsg.textContent=(r&&r.error)||"Could not remove key";}});
      if(elRefresh) elRefresh.addEventListener("click",async()=>{elRefresh.disabled=true;await refreshElevenLabsStatus(true);});
      const refreshBridge = menuEl.querySelector("#zs-refresh-bridge");
      if (refreshBridge) refreshBridge.addEventListener("click", async () => { refreshBridge.disabled = true; await ensureTools(true); buildMenu(); });
      const restartBridge = menuEl.querySelector("#zs-restart-bridge");
      if (restartBridge) restartBridge.addEventListener("click", async () => {
        restartBridge.disabled = true; restartBridge.textContent = "Restarting…";
        const r = await bg({ type: "restart_mcp" });
        if (!r || r.error) { toast((r && r.error) || "Restart failed"); buildMenu(); return; }
        await waitForBridgeBack(null, 20000); await ensureTools(true); buildMenu(); toast("MCP servers restarted");
      });
      const copySettings=menuEl.querySelector("#ms-copy-settings"),importSettings=menuEl.querySelector("#ms-import-settings");
      if(copySettings) copySettings.addEventListener("click",async()=>{try{await navigator.clipboard.writeText(JSON.stringify(buildSettingsBackup(),null,2));toast("Validated settings backup copied");}catch{toast("Could not copy settings");}});
      if(importSettings) importSettings.addEventListener("click",async()=>{try{const raw=JSON.parse(await navigator.clipboard.readText());applySettingsBackup(raw);menuTab="help";buildMenu();toast("Settings restored and validated");}catch(e){toast(`Settings import rejected: ${String(e&&e.message||e).slice(0,90)}`);}});
      const providerTest = menuEl.querySelector("#zs-provider-selftest");
      if (providerTest) providerTest.addEventListener("click", async () => {
        const result = P.selfTest ? P.selfTest() : { provider: P.id, ready: !!P.getEditor(), recommendation: "Basic editor check only." };
        try { await navigator.clipboard.writeText(JSON.stringify(result, null, 2)); } catch {}
        toast(result.ready ? "Provider ready · report copied" : "Provider needs attention · report copied");
      });
      const copyDiag = menuEl.querySelector("#zs-copy-diagnostics");
      if (copyDiag) copyDiag.addEventListener("click", async () => {
        const safe = { product:"Multi-Script", version:EXT_VERSION, zeroScriptBase:true, provider:P.id, urlHost:location.hostname, bridgeConnected:!!(A.bridge&&A.bridge.connected), servers:(A.bridge&&A.bridge.servers)||[], engines:(A.bridge&&A.bridge.engines)||[], advertisedTools:A.toolList.length, started:A.started, starting:A.starting, effectiveSettings:{ schema:SETTINGS_BACKUP_SCHEMA, providerBehavior:getProviderBehavior(), specialistDepth:skillDepth, usageOptimizer:usageMode, creativeSurface:getProviderBehavior().creativeSurface, promptEnhancer:ZSEnhance.sanitize(enhanceSettings), executionEffort, critic:MSStudio.sanitizeCritic(criticSettings), pacing:ZSPace.sanitize(paceSettings), pacingSummary:paceDescription(), errorRecovery:ZSResilience.sanitize(resilienceSettings), errorRecoverySummary:ZSResilience.describe(resilienceSettings, P.id), verification:ZSVerify.sanitize(verificationSettings), verificationSummary:ZSVerify.describe(verificationSettings, P.id), verificationSeen:A.verifyCount||0, autonomy:autonomyLevel, customInstructionsConfigured:!!customPrompt.trim(), appearance:{theme:menuPrefs.theme,density:menuPrefs.density,width:menuPrefs.width,scale:menuPrefs.scale,motion:menuPrefs.motion}, starterRouting:P.routingProfileDiagnostics?P.routingProfileDiagnostics():null, localAudioReady:!!elevenLabsState.configured, elevenLabsConfigured:!!elevenLabsState.elevenLabsConfigured, customMcpServerCount:customMcpServers.length } };
        try { await navigator.clipboard.writeText(JSON.stringify(safe, null, 2)); toast("Diagnostics copied"); } catch { toast("Could not copy diagnostics"); }
      });
      const reloadPage = menuEl.querySelector("#zs-reload-page");
      if (reloadPage) reloadPage.addEventListener("click", () => location.reload());
      menuEl.querySelectorAll("button.zs-site-opt, .zs-tip-opt").forEach((b) =>
        b.addEventListener("click", () => open(b.dataset.u)));
      menuEl.querySelectorAll(".zs-profile-opt").forEach((b) => b.addEventListener("click", () => {
        if (!P.setAutoRoutingProfile) return;
        const selected = P.setAutoRoutingProfile(b.dataset.profile || "");
        menuTab = P.id === "notion" ? "notion" : "agent";
        buildMenu();
        const st = menuEl.querySelector("#zs-profile-status");
        if (st) { const d=P.routingProfileDiagnostics ? P.routingProfileDiagnostics() : null; st.textContent = selected ? `Saved for the next new chat · ${d && d.requestedModel ? `preference: ${d.requestedModel}` : "routing request ready"} · sent once` : (P.id === "arena" ? "Direct Max routing is off · the next engine or engine-free chat starts normally." : "Standard Auto saved for the next new chat."); }
        toast(selected ? `${profileProviderLabel} starter profile: ${b.textContent}` : `${profileProviderLabel} starter profile disabled`);
      }));
      const ta = menuEl.querySelector("#zs-set-text");
      const saveBtn = menuEl.querySelector("#zs-set-save");
      const status = menuEl.querySelector("#zs-set-status");
      ta.value = customPrompt;
      saveBtn.addEventListener("click", () => {
        customPrompt = ta.value;
        try { chrome.storage.local.set({ zsCustomPrompt: customPrompt }); } catch {}
        status.textContent = "Saved ✓";
        setTimeout(() => { status.textContent = ""; }, 1600);
      });
      const mcpNameEl = menuEl.querySelector("#zs-mcp-name");
      const mcpUrlEl = menuEl.querySelector("#zs-mcp-url");
      const mcpStatus = menuEl.querySelector("#zs-mcp-status");
      const mcpAddBtn = menuEl.querySelector("#zs-mcp-add");
      // Disable every add/remove control and show the restart spinner. Adding or
      // removing a server rewrites config.json and restarts the whole bridge, so
      // no other server edit may run until it is back.
      let mcpBusy = false;
      function setMcpBusy(on, label) {
        mcpBusy = on;
        mcpAddBtn.disabled = on;
        menuEl.querySelectorAll(".zs-mcp-remove").forEach((b) => (b.disabled = on));
        mcpStatus.innerHTML = on
          ? `<span class="zs-mcp-spin-row"><span class="zs-mcp-spin"></span>${label || "Restarting bridge…"}</span>`
          : "";
      }

      menuEl.querySelectorAll(".zs-mcp-remove").forEach((b) =>
        b.addEventListener("click", async () => {
          if (mcpBusy) return;
          const id = b.dataset.id;
          if (!id) return;
          setMcpBusy(true, "Restarting bridge…");
          const r = await bg({ type: "remove_server", server_id: id });
          if (!r || !r.ok) {
            setMcpBusy(false);
            mcpStatus.textContent = (r && r.error) || "Couldn't remove server";
            setTimeout(() => { if (!mcpBusy) mcpStatus.textContent = ""; }, 2400);
            return;
          }
          customMcpServers = customMcpServers.filter((s) => s.id !== id);
          saveCustomMcpServers();
          await waitForBridgeBack(null);
          buildMenu(); // rebuilds with the spinner cleared
        }));

      mcpAddBtn.addEventListener("click", async () => {
        if (mcpBusy) return;
        const name = mcpNameEl.value.trim();
        const command = mcpUrlEl.value.trim();
        if (!name || !command) {
          mcpStatus.textContent = "Name and command required";
          setTimeout(() => { if (!mcpBusy) mcpStatus.textContent = ""; }, 1800);
          return;
        }
        const id = mcpSlug(name);
        const { command: cmd, args } = splitCommand(command);
        setMcpBusy(true, "Restarting bridge…");
        const r = await bg({ type: "add_server", server_id: id, command: cmd, args });
        if (!r || !r.ok) {
          setMcpBusy(false);
          mcpStatus.textContent = (r && r.error) || "Couldn't add server";
          setTimeout(() => { if (!mcpBusy) mcpStatus.textContent = ""; }, 2400);
          return;
        }
        customMcpServers.push({ id, name, command });
        saveCustomMcpServers();
        await waitForBridgeBack(id);
        buildMenu(); // rebuilds with the new server listed + spinner cleared
      });
    }

    // ── First-time onboarding card (bridge missing) ─────────────────────────
    let setupCard = null, setupSeen = false, setupRaf = null;
    try {
      chrome.storage.local.get("zsSetupSeen", (r) => {
        if (r && r.zsSetupSeen) setupSeen = true;
      });
    } catch {}

    function buildSetup() {
      setupCard = document.createElement("div");
      setupCard.id = "zs-setup";
      setupCard.hidden = true;
      const videoBtn = VIDEO_URL
        ? `<a id="zs-setup-video" href="${VIDEO_URL}" target="_blank" rel="noopener">▶︎ Watch tutorial</a>`
        : "";
      setupCard.innerHTML =
        `<div id="zs-setup-head"><span id="zs-setup-logo">Multi-Script</span><span id="zs-setup-tag">Setup</span></div>` +
        `<div id="zs-setup-sub">The <b>Bridge</b> connects supported AI chats to Roblox Studio, Unity, Godot, Blender, and other configured MCP tools. Three steps and you're running.</div>` +
        `<ol id="zs-setup-steps">` +
          `<li>Download the Bridge from GitHub</li>` +
          `<li>Run <code>${ZS.setupCommand()}</code> once, then click the terminal icon</li>` +
          `<li>Open a supported editor/MCP server, then click <b>Start agent</b></li>` +
        `</ol>` +
        `<div class="zs-setup-copy-row">` +
          `<input type="text" id="zs-setup-link" readonly value="${GITHUB_URL}">` +
          `<button id="zs-setup-copy">Copy</button>` +
        `</div>` +
        videoBtn +
        `<button id="zs-setup-dismiss">Got it</button>`;
      document.documentElement.appendChild(setupCard);

      setupCard.querySelector("#zs-setup-copy").addEventListener("click", () => {
        try { navigator.clipboard.writeText(GITHUB_URL); } catch {
          const inp = setupCard.querySelector("#zs-setup-link");
          inp.select(); try { document.execCommand("copy"); } catch {}
        }
        const btn = setupCard.querySelector("#zs-setup-copy");
        btn.textContent = "Copied!";
        setTimeout(() => { btn.textContent = "Copy"; }, 1600);
      });

      setupCard.querySelector("#zs-setup-dismiss").addEventListener("click", () => {
        setupSeen = true;
        try { chrome.storage.local.set({ zsSetupSeen: true }); } catch {}
        hideSetup();
      });
    }

    // The onboarding card is pinned to the top-right corner (via CSS), out of the
    // way of the composer; nothing to reposition per frame.
    function placeSetup() {}

    function showSetup() {
      if (!setupCard) buildSetup();
      if (setupCard.hidden) {
        setupCard.hidden = false;
        cancelAnimationFrame(setupRaf);
        placeSetup();
      }
    }

    function hideSetup() {
      if (setupCard) setupCard.hidden = true;
      cancelAnimationFrame(setupRaf);
    }

    function refreshSetup(bridgeConnected) {
      if (setupSeen || bridgeConnected) { hideSetup(); return; }
      // Bridge is down, but if the user is just READING an existing
      // conversation with no Multi-Script session (the "No agent here" state),
      // a "bridge down" onboarding popup is pure noise - they may not want an
      // agent here at all (user request). Keep it for the states where the
      // bridge actually matters: a fresh/empty chat (the Start affordance is
      // showing) or a conversation with a live/starting session.
      if (!A.started && !A.starting && !P.chatIsEmpty()) { hideSetup(); return; }
      showSetup();
    }

    // The single source of truth for the bar's content. Decides the dot tone,
    // the state line and the primary action from the live state:
    //  • starting        → spinner, "Starting the Roblox agent…"
    //  • session active   → live dot, "Agent active · N tools" (no action)
    //  • fresh blank chat → "Standby…" (or a bridge/Studio warning), action = Start
    //  • existing chat    → "No agent in this chat" (informs only, no action)
    function renderBar() {
      if(typeof MSProgress!=='undefined'&&!runMonitor&&root){runMonitor=MSProgress.mount({root,read:readTaskProgress,runtime:()=>({running:A.running,generating:P.isGenerating(),waitingForUser:!!P.waitingForUser?.(),stopped:A.userStopped,providerFailed:!!A.responseFailure}),phone:renderPhoneControl,onOpen:()=>{if(menuEl)menuEl.hidden=true;}});}
      runMonitor?.paint();
      if (!bar) return;
      // indicator = an optional leading dot/spinner; msg = the wrappable text.
      let toneClass = "standby", indicator = "", msg = "", label = "", kind = "", disabled = false, warn = false;
      // Orphaned page: check FIRST and return. Nothing below can be true any
      // more - the status poll is stopped, so every value it would render (the
      // green dot, "Agent active", the tool count) is a frozen snapshot of a
      // build this page no longer talks to. Leaving those up contradicted the
      // "reload this page" banner sitting right next to them, which is exactly
      // the confusing state Seb caught on 2026-08-14.
      // No action button here: the banner already carries the Reload one.
      if (A.staleExtension) {
        if (dot) dot.className = "off";
        toneClass = "warn"; warn = true;
        msg = `<b>Disconnected</b> · reload this page to reconnect`;
      }
      // Show "Starting…" for the whole bootstrap. If the user actually leaves for
      // a new (empty) chat, syncSessionState clears A.starting, so this naturally
      // falls back to that chat's own state - no fragile per-key check here (fresh
      // chats share a key, and the conversation id only appears mid-bootstrap).
      else if(A.started&&P.waitingForUser?.()){toneClass='warn';warn=true;msg='<b>Waiting for response selection</b> · choose a response on the provider page';}
      else if(A.responseFailure&&A.responseFailure.chat===P.conversationKey()){
        toneClass="warn";warn=true;const stillGenerating=P.isGenerating();msg=stillGenerating?`<b>Provider is still responding</b> · task unverified`:`<b>Paused · provider response failed</b> · task unverified`;label="Resume response";kind="resume-response";disabled=stillGenerating;
      }
      else if (A.starting) {
        toneClass = "starting";
        indicator = `<span class="zs-spin"></span>`;
        msg = A.software ? `Starting ${softwareSettings.mode === "code" ? "Code mode" : "the Software Builder"}…` : A.chatOnly ? `Starting the Multi-Script chat studio…` : `Starting the engine agent…`;
        if(A.startPhase)msg=MSStudio.escape(A.startPhase)+" · "+Math.max(0,Math.floor((Date.now()-(A.startBeganAt||Date.now()))/1000))+"s";
        label = "Starting…"; kind = "starting"; disabled = true;
      } else if (A.started) {
        // Prefer the ADVERTISED list length (A.toolList - the AGGREGATE catalogue
        // across every connected MCP server, already filtered by the vision/blocked
        // gate so it matches what the model actually has: e.g. screen_capture is
        // absent on non-vision providers like Kimi). After a page reload A.toolList
        // is empty until the next list_tools, so fall back to the sum of every
        // server's per-server health count (Roblox + addons like Blender) - NOT the
        // Roblox-only count, which made the total drop to just 27 after a reload.
        const healthTotal = A.bridge &&
          (A.bridge.servers || []).reduce((n, x) => n + (x.tools || 0), 0);
        const tools = A.toolList.length || healthTotal || (A.bridge && A.bridge.tools) || 0;
        // "N tools" only means StudioMCP itself is up - it advertises its full
        // catalogue even with no Studio/place attached (see probe_studio() in
        // bridge.py), so showing it while Studio/place isn't actually usable
        // reads as "everything's fine" when tool calls will just fail. Surface
        // the real blocker instead in that case.
        if (A.software) {
          toneClass = "active";
          const ad = softwareSettings.addons || {};
          const extra = [ad.skills && "skills", ad.engines && "engines", ad.mcp && "MCP"].filter(Boolean);
          msg = `<b>${softwareSettings.mode === "code" ? "Code mode" : "Software Builder"} active</b> · workspace tools${softwareSettings.allowRun ? " + commands" : " (commands off)"}${extra.length ? " · + " + extra.join(", ") : ""}`;
        } else if (A.chatOnly) {
          toneClass = "active";
          msg = `<b>Chat studio active</b> · skills and starter profile enabled · no engine execution`;
        } else if (A.bridge && A.bridge.connected === false) {
          // placeDown/appDown/studioDown are all false in this case (they're
          // only computed when the bridge IS connected - see setStatus), so
          // without this check the bridge dropping fell through to the
          // stale "N tools" text below, reading as if nothing was wrong.
          toneClass = "warn"; warn = true;
          msg = `<b>Agent active</b> · bridge offline, click the terminal icon to start it`;
        } else if ((placeDown || appDown || studioDown) && addonOk) {
          // DEGRADED session by CHOICE: the user started the agent with Roblox
          // down but other MCP server(s) alive (the "Start agent (Roblox
          // offline)" path) - they may only want the addon tools (e.g. Blender).
          // Keep the YELLOW dot as the honest health signal, but do NOT keep the
          // red imperative "open Roblox Studio" nag on screen for the whole
          // session (warn=false → no zs-state-warn red text). The full nag
          // still shows when NO server is usable (the branches below).
          toneClass = "warn";
          msg = `<b>Agent active</b>${tools ? ` · ${tools} tools` : ""} · Roblox offline`;
        } else if (placeDown) {
          toneClass = "warn"; warn = true;
          msg = `<b>Agent active</b> · open a place in Roblox Studio`;
        } else if (appDown || studioDown) {
          toneClass = "warn"; warn = true;
          msg = studioProcUp
            ? `<b>Agent active</b> · Studio is open but not connected - open <b>Assistant Settings &gt; MCP Servers</b> in Studio`
            : `<b>Agent active</b> · open Roblox Studio & enable its MCP server`;
        } else {
          toneClass = "active";
          // No inline dot here: the leading status dot already shows green, two
          // dots side by side looked cluttered. The green "Agent active" text
          // carries it.
          msg = `<b>Agent active</b>${tools ? ` · ${tools} tools` : ""}`;
        }
      } else if (P.isFreshChat() || P.chatIsEmpty()) {
        // Treat ANY empty chat (no turns yet) as the standby/start case - not just
        // the strict fresh-chat match. isFreshChat() also requires an exact root
        // path AND the editor already mounted; on a cold load (e.g. arriving from a
        // search-engine link) the SPA can show pathname/editor before they settle,
        // which used to drop into the discouraging "No agent here" branch on a page
        // that is actually empty and startable. "No agent here" is only correct for
        // an EXISTING conversation (one that has turns) we did not start.
        if (bridgeOk) {
          toneClass = "standby";
          const readyIds=((A.bridge&&A.bridge.engines)||[]).filter((e)=>e.connected===true&&e.alive&&!A.disabledEngines.has(String(e.id||"").toLowerCase())).map((e)=>e.id);
          const readyLabels=readyIds.map((id)=>id==="roblox"?"Roblox Studio":id==="unity"?"Unity":id==="godot"?"Godot":id==="blender"?"Blender":id);
          const companionPending=!readyIds.includes('blender')&&(A.bridge?.engines||[]).some(e=>readyIds.includes(e.id)&&e.blenderCompanion);
          const startLabels=[...readyLabels,...(companionPending?['Blender']:[])];
          msg = readyLabels.length ? `Standby · ${readyLabels.join(" + ")} ready. ${companionPending?'Blender will start with this session.':'Start with tools or without an engine.'}` : `Standby. Start the agent, or use the chat studio.`;
          label = readyIds.includes("roblox") ? "▶︎ Start Roblox Studio"+(companionPending?' + Blender':'') : startLabels.length ? `▶︎ Start ${startLabels.join(" + ")}` : "▶︎ Start engine agent"; kind = "start";
        } else if (addonOk) {
          // Roblox is down but another MCP server is live: allow a DEGRADED start
          // (yellow). The agent runs on the other server(s); Roblox tools stay
          // unavailable until Studio is back. Button enabled, but visibly warned.
          toneClass = "warn"; warn = true;
          msg = !A.bridge.connected
            ? `Click the <b>terminal icon</b> to start the bridge.`
            : studioProcUp
              ? `<b>Studio open but not connected</b> - open <b>Assistant Settings &gt; MCP Servers</b> in Studio, or start without it.`
              : `<b>Roblox Studio offline</b> - start with your other MCP server(s).`;
          const addonNames=((A.bridge&&A.bridge.engines)||[]).filter((e)=>e.id!=="roblox"&&e.connected===true&&e.alive&&!A.disabledEngines.has(String(e.id||"").toLowerCase())).map((e)=>e.id==="unity"?"Unity":e.id==="godot"?"Godot":e.id==="blender"?"Blender":e.id);
          label = addonNames.length ? `▶︎ Start ${addonNames.join(" + ")}` : "▶︎ Start available MCP tools"; kind = "start-degraded";
        } else {
          toneClass = "warn"; warn = true;
          msg = !A.bridge.connected
            ? `Click the <b>terminal icon</b> to start the bridge.`
            : placeDown
              ? `Open a <b>place</b> in Roblox Studio.`
              : (appDown || studioDown) && studioProcUp
                ? `Studio is open but not connected - open <b>Assistant Settings &gt; MCP Servers</b> in Studio.`
                : appDown
                  ? `Open <b>Roblox Studio</b> &amp; enable its MCP server.`
                  : studioDown
                    ? `Open <b>Roblox Studio</b> &amp; enable its MCP server.`
                    : `Open <b>Roblox Studio</b> for the tools.`;
          label = "▶︎ Start Roblox agent"; kind = "start";
        }
        disabled = !bridgeOk && !addonOk;
      } else {
        toneClass = "noagent";
        msg = `No agent here. Open a new chat to start one.`;
      }
      if(A.started&&!A.running&&!A.responseFailure&&A.taskOutcomeChat===P.conversationKey()&&A.taskOutcome==="review-results"){
        toneClass="warn";warn=true;msg=`<b>Response ended · review results</b> · ${A.taskToolErrors||0} failed tool call(s)`;
      }
      // Parked on visibility: the loop is alive but deliberately frozen because
      // this tab is not the foreground tab of its window. Say so explicitly -
      // otherwise the bar keeps claiming "Agent active" while nothing advances,
      // which reads as a hang (and is what users reported as "it died in the
      // background"). No red warn tone: this is a normal, recoverable pause.
      if (A.parked && (A.running || A.starting)) {
        toneClass = "warn"; warn = false;
        msg = `<b>Paused</b> · bring this tab to the front to continue`;
      }
      // A bot-check owns the page: say exactly what to do, and make it clear the
      // agent is waiting rather than dead. Takes priority over "Paused" because
      // it is the thing actually blocking progress.
      if (A.verifying) {
        toneClass = "warn"; warn = true;
        msg = `<b>Verification needed</b> · complete the human check in the page - the agent resumes by itself`;
      } else if (A.pacingUntil && Date.now() < A.pacingUntil && (A.running || A.starting)) {
        // Visible, honest pacing: the gap before the next turn is a deliberate
        // rate-limit guard, not a hang. Shown only while the agent is working.
        const secs = Math.max(1, Math.ceil((A.pacingUntil - Date.now()) / 1000));
        if (toneClass !== "warn") toneClass = "active";
        msg = `<b>Pacing</b> · next turn in ~${secs}s${A.pacingReason === "long-pause" ? " (reading break)" : A.pacingReason === "error-cooldown" ? " (after an error)" : ""}`;
      }
      // Provider mode guard: some sites (e.g. Arena) only work in one chat mode.
      // When the provider reports the current mode is unsupported, override the
      // bar into a visible warning and disable Start until the user switches back.
      // Skipped once a session is started/starting (the mode is fixed for the
      // conversation by then). Reactive: renderBar runs on every sweep, so the
      // warning appears/clears the instant the user changes the mode dropdown.
      if (!A.started && !A.starting && P.modeWarning) {
        const modeWarn = P.modeWarning();
        if (modeWarn) {
          toneClass = "warn"; warn = true; msg = modeWarn;
          if (kind === "start" || kind === "start-degraded") disabled = true;
        }
      }
      // Notion can land on a home/page route before its AI composer mounts. Keep
      // Multi-Script visible and actionable instead of disappearing completely.
      if (!P.getEditor() && P.persistentBarWhenNoEditor && !A.started && !A.starting) {
        toneClass = "warn"; warn = true;
        msg = P.noEditorMessage || (P.modeWarning&&P.modeWarning()) || `${P.displayName} chat is not open.`;
        label = `Open ${P.displayName} chat`; kind = "open-provider"; disabled = false;
      }
      // Only touch the DOM when something actually changed. renderBar runs on
      // every sweep; rewriting stateEl.innerHTML each time recreated the spinner
      // <span> and RESTARTED its CSS animation, so "Starting…" appeared to stutter.
      const busy = !stopBtn.hidden;
      const composerReady=!!P.getEditor();
      const freshChat=P.isFreshChat()||P.chatIsEmpty();
      const modeBlocked=!!(P.modeWarning&&P.modeWarning());
      const showChatOnly=!A.started&&!A.starting&&!busy;
      const canStartChatOnly=showChatOnly&&composerReady&&!modeBlocked;
      // Before a session is started, the bar stays minimal: only the Start action
      // + Discord (help). The AI selector and the tips/support menu appear once the
      // agent is actually running - so the pre-start bar isn't cluttered with
      // options that only matter mid-session. (A.started is ambiguous with `warn`
      // tone - which occurs both started-with-bridge-down and standby-with-bridge-
      // down - so it's tracked explicitly in the signature.)
      const showExtras = !!A.started;
      const sig = [toneClass, indicator, msg, label, kind, disabled, warn, busy, showExtras, composerReady, freshChat, modeBlocked, showChatOnly, softwareSettings.enabled].join("|");
      if (sig === lastBarSig) return;
      lastBarSig = sig;
      // Set the tone WITHOUT clobbering other classes (e.g. zs-bar-inline, which
      // placeBar adds for the in-flow mount - overwriting className broke the
      // layout, making the bar fall back to fixed positioning and overlap).
      bar.classList.remove("tone-standby", "tone-active", "tone-warn", "tone-noagent", "tone-starting");
      bar.classList.add(`tone-${toneClass}`);
      stateEl.innerHTML = indicator + `<span class="zs-state-txt">${msg}</span>`;
      stateEl.title = String(msg).replace(/<[^>]+>/g, "").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
      stateEl.classList.toggle("zs-state-warn", warn);
      stateEl.tabIndex=A.starting?0:-1;
      if(A.starting){stateEl.setAttribute('aria-controls','ms-startup-info');stateEl.setAttribute('aria-expanded',String(!root.querySelector('#ms-startup-info').hidden));stateEl.title+=' · Click for startup steps';}else{stateEl.removeAttribute('aria-controls');stateEl.removeAttribute('aria-expanded');}
      if(A.starting)stateEl.setAttribute('role','button');else stateEl.removeAttribute('role');
      const startup=root.querySelector('#ms-startup-info');
      if(startup){if(!A.starting)startup.hidden=true;else{startup.querySelector('#ms-startup-detail').textContent=A.startPhase+' · '+Math.max(0,Math.floor((Date.now()-(A.startBeganAt||Date.now()))/1000))+'s elapsed';startup.querySelectorAll('[data-stage]').forEach(el=>{el.dataset.state=Number(el.dataset.stage)<A.startStage?'done':Number(el.dataset.stage)===A.startStage?'current':'pending';});}}
      actionBtn.textContent = label;
      actionBtn.title = label;
      actionBtn.dataset.kind = kind;
      actionBtn.disabled = disabled;
      // The Stop button replaces the action button while the agent is busy.
      // With no kind (e.g. agent active, or an existing chat) there's no primary
      // action to offer, so the button is hidden entirely.
      actionBtn.style.display = (busy || !kind) ? "none" : "";
      chatOnlyBtn.style.display=showChatOnly?"":"none";
      chatOnlyBtn.title=canStartChatOnly?"Start a chat studio without an MCP engine":modeBlocked?"Switch to a supported chat mode":"Open the provider chat or sign in to enable this action";
      chatOnlyBtn.disabled=!canStartChatOnly;
      if (softwareBtn) {
        const sw = canStartChatOnly && !!softwareSettings.enabled; softwareBtn.style.display = sw ? "" : "none"; softwareBtn.disabled = !sw;
        const code = softwareSettings.mode === "code";
        const label = code ? "‹› Code" : "Build software";
        if (softwareBtn.textContent !== label) softwareBtn.textContent = label;
        softwareBtn.title = code ? "Code mode: a coding agent for a folder on this PC - explore, edit, test, git, undo" : "Build, compile and package a real program in a folder you choose, using the local bridge";
      }
      // AI selector + tips/support: only once a session is live. Discord stays
      // visible in every state (it's the help link).
      if (switchBtn) switchBtn.style.display = "";
      if (supportBtn) supportBtn.style.display = showExtras ? "" : "none";
    }
    let lastBarSig = "";
    // ── Bridge terminal panel ───────────────────────────────────────────────
    // The icon is a LIVE representation of the local bridge, not a decoration:
    // data-state is driven by the real socket state, so what the user sees is
    // what is true. Clicking it opens the terminal PANEL - a real view of the
    // bridge's log, its attached engines and its health - rather than a toast.
    // Colours come from CSS (theme-aware), so the icon and the panel follow the
    // user's accent / light-dark / backdrop with no JS involvement.
    let termPanel = null;
    function paintBridge(state, title) {
      if (!bridgeBtn) return;
      bridgeBtn.dataset.state = state;
      bridgeBtn.title = title;
      bridgeBtn.setAttribute("aria-label", title);
    }
    function bridgeIdlePaint() {
      if (!bridgeBtn) return;
      const up = !!(A.bridge && A.bridge.connected);
      paintBridge(up ? "live" : "down",
        up ? "Bridge running - click for the live terminal"
           : "Bridge not running - click to open the terminal and start it");
      if (termPanel && termPanel.busy) paintBridge("starting", `Bridge ${termPanel.busy}…`);
      bridgeBtn.setAttribute("aria-expanded", String(!!(termPanel && termPanel.isOpen())));
      if (bridgeRunBtn) bridgeRunBtn.setAttribute("aria-expanded", String(!!(termPanel && termPanel.isOpen() && termPanel.currentTab() === "running")));
    }
    // ── Graph memory (core/memory.js) ─────────────────────────────────────────
    function paintMem() {
      if (!memBtn) return;
      const on = !!(memCtl && memCtl.isOn());
      memBtn.dataset.state = on ? "on" : "off";
      memBtn.title = on ? `Memory ON: ${memCtl.name() || memCtl.memoryRef()} (click to manage)` : "Memory is off in this chat (click to choose or create a memory)";
      memBtn.setAttribute("aria-pressed", String(on));
    }
    function ensureMem() {
      if (!memCtl && window.ZSMemory) {
        memCtl = memCtrl;
        paintMem();
        memPanel = new window.ZSMemory.MemoryPanel({
          mount: root,
          controller: memCtl,
          anchor: () => memBtn,
          ui: { toast: (t) => toast(t), onChange: () => { paintMem(); memStateChanged(); } },
        });
      }
      return memCtl;
    }
    function ensureTerm() {
      if (!termPanel && window.ZSTerminal) {
        termPanel = new window.ZSTerminal.TerminalPanel({
          mount: root,
          bg: (msg) => bg(msg),
          getStatus: () => A.bridge || {},
          anchor: () => bridgeBtn,
          onNeedReconnect: () => {
            try { bg({ type: "reconnect" }); } catch {}
          },
          ui: { toast: (t) => toast(t), banner: (...a) => ui.banner(...a), onBusy: () => bridgeIdlePaint() },
        });
      }
      return termPanel;
    }
    // Icon: open / close the terminal. Caret: open straight onto "Running".
    function onBridgeClick() {
      const t = ensureTerm();
      if (!t) return;
      if (t.isOpen() && t.currentTab() === "log") t.close();
      else if (t.isOpen()) t.showTab("log");
      else t.openPanel("log");
      bridgeIdlePaint();
    }
    function onBridgeRunClick() {
      const t = ensureTerm();
      if (!t) return;
      if (t.isOpen() && t.currentTab() === "running") t.close();
      else if (t.isOpen()) t.showTab("running");
      else t.openPanel("running");
      bridgeIdlePaint();
    }

    // Thin wrappers kept for the core's call sites; the decision lives in renderBar.
    function setStarted() { renderBar(); }
    function setStarting() { renderBar();showStop(A.starting); }

    function setStatus(s) {
      A.bridge = s;
      // Keep the terminal icon truthful on every real status push. This is the
      // only place bridge connectivity becomes known, so it is the only place the
      // icon may be repainted from - anything else would be guessing.
      bridgeIdlePaint();
      if (!dot) return;
      const servers = s.servers || [];
      const engines = (s.engines || []).filter((e) => !A.disabledEngines.has(String(e.id || "").toLowerCase()));
      const connectedEngines = engines.filter((e) => e.connected === true && e.alive);
      const nonRobloxReady = connectedEngines.some((e) => e.id !== "roblox");
      // Multi-Script status tracks ONLY the primary Roblox MCP server. Every other
      // server is an addon and must NEVER make the dot/gate look connected while
      // Roblox itself is down. Old bridges don't send per-server health, so fall
      // back to the aggregate signals they do send (mcpAlive / total tools).
      const roblox = servers.find((x) => x.id === "roblox");
      const mcpUp = roblox ? !!roblox.alive : (!!s.mcpAlive || servers.some((x) => x.alive));
      // Roblox-only count drives the connectivity gate (the dot must never look
      // green off an addon while Roblox itself is down)...
      const robloxTools = roblox ? (roblox.tools || 0) : (s.tools || 0);
      const mcpOk = s.connected && (connectedEngines.length > 0 || mcpUp || robloxTools > 0);
      // ...but the DISPLAYED count is the aggregate across every server (Roblox +
      // addons like Blender), so it stays consistent with the bar and doesn't
      // under-report when addon servers are loaded.
      const totalTools = servers.reduce((n, x) => n + (x.tools || 0), 0) || s.tools || robloxTools;
      // studio === false means the MCP server answered but the Studio is not USABLE
      // (no place loaded). studioApp tells the two sub-cases apart:
      //   studioApp === false → no Studio connected at all (app closed OR its MCP
      //                         server option is disabled - indistinguishable).
      //   studioApp === true  → Studio open but no place loaded (home screen / place
      //                         closed mid-session). THIS is the case that used to
      //                         wrongly read "Connected".
      // null/undefined = unknown (old bridge / probe busy) → don't degrade.
      const companionReady=connectedEngines.some(e=>e.id==="roblox"&&e.companionConnected);
      const studioOff = mcpOk && !nonRobloxReady && !companionReady && s.studio === false;
      const noApp = studioOff && s.studioApp === false;
      const noPlace = studioOff && s.studioApp === true;
      const ok = mcpOk && !studioOff;
      dot.className = s.connected ? (ok ? "on" : "warn") : "off";
      // Studio PROCESS running on the machine (bridge-side tasklist check).
      // Splits noApp into its two truly different situations: Studio not
      // launched at all vs Studio OPEN but its MCP plugin never registered
      // with the bridge. The plugin only attempts to register ONCE (at Studio
      // boot or on a panel/toggle interaction) and never retries by itself,
      // so for the second case "open Roblox Studio" is dead-end advice - the
      // action that actually works (validated live 3x, 2026-07-11) is opening
      // Assistant Settings > MCP Servers inside the already-open Studio.
      const procUp = s.studioProc === true;
      let txt;
      if (!s.connected) txt = "Bridge offline - click the terminal icon to start it";
      else if (!mcpOk) txt = "Bridge OK, open Roblox Studio";
      else if (noPlace) txt = "Roblox Studio is open but no place is loaded - open a place";
      else if (noApp) txt = procUp
        ? "Studio is open but not connected - in Studio, open Assistant Settings > MCP Servers (or toggle its MCP server off/on)"
        : "Roblox Studio not connected - open it and enable its MCP server";
      else if (studioOff) txt = "Studio not connected, enable the MCP server in Roblox Studio";
      else {
        const names = connectedEngines.map((e) => e.id === "roblox" ? "Roblox Studio" : e.id === "unity" ? "Unity" : e.id);
        txt = `Connected${names.length ? " · " + names.join(" + ") : ""} · ${totalTools} tools ready`;
      }
      dot.title = txt; // full bridge detail on hover over the status dot
      bridgeOk = ok;
      studioDown = studioOff;
      placeDown = noPlace;
      appDown = noApp;
      studioProcUp = procUp;
      // A non-Roblox MCP (Blender, Sketchfab, ...) that is actually alive. When
      // Roblox itself is down but such a server is present, the session can still
      // start in a DEGRADED mode - the agent just can't touch Roblox until Studio
      // is back. Gated on s.connected so a dropped bridge never reads as usable.
      addonOk = !!s.connected && (nonRobloxReady || (!engines.length && servers.some((x) => x.id !== "roblox" && x.alive && (x.tools || 0) > 0)));
      // Bridge-drop alert: a clear, persistent red banner the moment a
      // previously-connected bridge goes offline. Clears on reconnect.
      if (wasConnected && !s.connected) bridgeAlert(true);
      if (s.connected) bridgeAlert(false);
      wasConnected = s.connected;
      // Once the bridge has connected at least once, onboarding is done: never
      // resurface the "download the bridge" setup card again (otherwise, if the
      // bridge later drops, it would reappear on top of the bridge-lost banner).
      if (s.connected && !setupSeen) {
        setupSeen = true;
        try { chrome.storage.local.set({ zsSetupSeen: true }); } catch {}
      }
      renderBar();
      refreshSetup(s.connected);
    }

    // The page outlived its extension build (reload / Chrome auto-update /
    // disable+enable). Distinct from bridgeAlert on purpose: opposite cause,
    // opposite fix, and this one NEVER self-heals, so the banner has no Close
    // button and offers the reload directly rather than telling the user to go
    // restart a bridge that was never down.
    function staleExtensionAlert() {
      // Latch it BEFORE painting, so the bar drops its frozen "Agent active ·
      // N tools" in the same pass and never contradicts the banner.
      A.staleExtension = true;
      renderBar();
      if (bridgeBannerEl) { bridgeBannerEl.remove(); bridgeBannerEl = null; }
      if (root.querySelector(".zs-banner.zs-stale")) return;
      const b = document.createElement("div");
      b.className = "zs-banner limit zs-stale";
      b.innerHTML = `<div class="zs-banner-t">⚠ Reload this page to reconnect Multi-Script</div>
        <div class="zs-banner-m">Multi-Script was updated or reloaded while this tab was open, so this page is still running the old copy and commands can no longer run. Your bridge and Roblox Studio are fine - only this page needs refreshing.</div>
        <div class="zs-banner-acts"><button class="zs-banner-reload">Reload page</button></div>`;
      b.querySelector(".zs-banner-reload").addEventListener("click", () => location.reload());
      root.appendChild(b);
      bridgeBannerEl = b;
    }

    // Show (on=true) / clear (on=false) the bridge-disconnected red banner.
    function bridgeAlert(on) {
      if (!on) {
        if (bridgeBannerEl) { bridgeBannerEl.remove(); bridgeBannerEl = null; }
        return;
      }
      if (bridgeBannerEl) return; // already shown
      const b = document.createElement("div");
      b.className = "zs-banner limit";
      // The setup tutorial lives INSIDE this banner (not as a separate card) so it
      // can never overlap the alert - the previous standalone onboarding card did.
      const videoLink = VIDEO_URL
        ? `<a class="zs-banner-video" href="${VIDEO_URL}" target="_blank" rel="noopener">▶︎ Watch setup tutorial</a>`
        : "";
      b.innerHTML = `<div class="zs-banner-t">⚠ Lost connection to Multi-Script</div>
        <div class="zs-banner-m">The Multi-Script bridge stopped on your PC. Restart it from the terminal icon in the chat bar (and keep Roblox Studio open): the agent will reconnect automatically as soon as it is detected again.</div>
        <div class="zs-banner-acts">${videoLink}<button class="zs-banner-x">Close</button></div>`;
      b.querySelector(".zs-banner-x").addEventListener("click", () => { b.remove(); if (bridgeBannerEl === b) bridgeBannerEl = null; });
      root.appendChild(b);
      bridgeBannerEl = b;
    }

    // Show (v=true) / hide the "■ Stop" button while the agent is busy. The
    // primary action button swaps out for it (handled in renderBar via busy).
    // Forced hidden during bootstrap (A.starting) so the bar stays on "Starting…"
    // (else it flickers Starting → Stop → Starting as generation toggles). The
    // caller decides the rest, including native-stop de-duplication.
    function showStop(v) {
      if (!stopBtn) return;
      // Stay visible while winding down (A.stopping), so the button doesn't blink
      // off when the live generation signal toggles as the loop drains.
      const allow = v || A.stopping || A.starting;
      const was = stopBtn.hidden;
      stopBtn.hidden = !allow;
      if(allow&&!A.stopping){stopBtn.textContent=A.starting?'Cancel startup':'■ Stop';stopBtn.disabled=false;}
      // Restore the normal, clickable Stop look whenever we're shown for a fresh
      // active turn (not a stop-in-progress).
      if (allow && !A.stopping && stopBtn.dataset.state === "stopping") {
        stopBtn.disabled = false;
        stopBtn.textContent = "■ Stop";
        delete stopBtn.dataset.state;
      }
      if (was !== stopBtn.hidden) renderBar(); // reflect the action/stop swap
    }

    // Instant feedback the moment the user clicks Stop: lock the button into a
    // disabled "⏳ Stopping…" state so they see it registered, even though the
    // loop takes a beat to actually wind down (finish the in-flight tool/await).
    function markStopping() {
      if (!stopBtn) return;
      stopBtn.hidden = false;
      stopBtn.disabled = true;
      stopBtn.dataset.state = "stopping";
      stopBtn.textContent = "⏳ Stopping…";
      renderBar();
    }

    // A gentle, one-time nudge: the user typed on a fresh chat without starting
    // the agent. We do NOT block the send (plain chat is fine) - we just point at
    // the Start button so they discover how to enable Roblox control.
    let nudged = false;
    function nudgeStart() {
      if (A.started || !P.isFreshChat()) return;
      if (!nudged) {
        nudged = true;
        toast("Tip: click “▶︎ Start Roblox agent” to let the AI control Roblox Studio.");
      }
      if (!actionBtn) return;
      actionBtn.classList.add("zs-flash");
      setTimeout(() => actionBtn.classList.remove("zs-flash"), 1200);
    }

    // ── Theme auto-detection (light / dark) ─────────────────────────────────
    // The panel and the in-conversation chips are dark-themed by default. On a
    // LIGHT host page the chips' light text on a near-transparent tint becomes
    // invisible, so we detect the page's effective background luminance and add
    // `.zs-light` to <html>; overlay.css then flips to readable light colours.
    // Most chat sites declare their theme EXPLICITLY (a `dark`/`light` class on
    // <html>/<body>, a data-theme attribute, or CSS color-scheme) - far more
    // reliable than luminance, since many (e.g. z.ai) leave <html>/<body> with a
    // transparent background and paint the theme on a deeper container. Returns
    // "light" | "dark" | null (no explicit signal).
    function pageThemeHint() {
      const de = document.documentElement, b = document.body;
      // Our own zs-* classes (zs-light!) must not count as a page hint (6.35.1).
      const cls = (de.className + " " + (b ? b.className : "")).toLowerCase().split(/\s+/).filter((c) => !/^zs-|^ms-/.test(c)).join(" ");
      if (/\bdark\b/.test(cls)) return "dark";
      if (/\blight\b/.test(cls)) return "light";
      const attr = (de.getAttribute("data-theme") || de.getAttribute("data-color-mode") ||
                    de.getAttribute("data-color-scheme") || "").toLowerCase();
      if (/dark/.test(attr)) return "dark";
      if (/light/.test(attr)) return "light";
      const cs = (getComputedStyle(de).colorScheme || "").toLowerCase();
      if (/dark/.test(cs) && !/light/.test(cs)) return "dark";
      if (/light/.test(cs) && !/dark/.test(cs)) return "light";
      return null;
    }
    // Fallback only: luminance of the first opaque background up the tree.
    function effectiveBg() {
      let n = document.body;
      while (n && n !== document.documentElement) {
        const c = getComputedStyle(n).backgroundColor;
        if (c && !/(transparent)/.test(c) && !/,\s*0\s*\)$/.test(c)) return c;
        n = n.parentElement;
      }
      return getComputedStyle(document.documentElement).backgroundColor || "rgb(255,255,255)";
    }
    function applyTheme() {
      let light;
      const hint = pageThemeHint();
      if (hint) {
        light = hint === "light";
      } else {
        const m = (effectiveBg().match(/\d+(?:\.\d+)?/g) || []).map(Number);
        if (m.length < 3) return;
        light = 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2] > 140;
      }
      pageIsLight = light;
      try { const zb = document.getElementById("zs-bar"); if (zb) zb.dataset.msBarClash = effectiveBarLight() !== light ? "1" : "0"; } catch {}
      document.documentElement.classList.toggle("zs-light", effectiveLight());
      if (root) root.dataset.msTheme = effectiveMenuTheme();
    }

    // Where the bar lives INSIDE the site's composer. We insert it as a real,
    // in-flow DOM node (between the model tabs and the input on DeepSeek), so it
    // takes the full composer width and never overlaps the site's own controls.
    // The mount point is derived from each provider's composerFrame()+getEditor(),
    // or a provider can override it via barMount(). Returns {parent, before}.
    // The provider decides the exact mount (it knows which element is the input
    // box and where a child reflows cleanly). If a provider doesn't supply one,
    // we fall back to the floating bar rather than risk overlapping its layout.
    function computeBarMount() {
      if (!P.barMount) return null;
      const m = P.barMount();
      return (m && m.parent && m.parent.isConnected) ? m : null;
    }

    // Floating fallback geometry (used only when no inline mount is available).
    const BAR_GAP = 8;

    // ── Menu (popover) placement ─────────────────────────────────────────────
    // ONE implementation, used by every branch of placeBar(). The menu is a
    // position:fixed popover (see overlay.css) inside #zs-root, so `right:` and
    // `bottom:` are distances to the VIEWPORT edges - exactly the space we have.
    //
    // The bug this replaces: each branch independently set
    // `menuEl.style.right = innerWidth - barRect.right`, i.e. it treated a
    // bar-relative offset as a viewport inset. On a wide composer the bar stops
    // well short of the right edge, so that delta is the page gutter (hundreds
    // of px) and the 370px-wide menu was pushed that far LEFT with nothing
    // stopping it - half of it left the screen.
    //
    // `anchorRight` / `anchorTop` are optional viewport coordinates we would
    // LIKE the menu's right edge and top edge to hug (normally the bar's right
    // edge and top edge). Both are clamped so the panel always stays fully
    // on-screen with a small gutter, and its height is capped to the space
    // actually available above the anchor.
    const MENU_GUTTER = 8, MENU_MIN_W = 240, MENU_MIN_H = 140;
    function placeMenu(anchorRight, anchorTop) {
      if (!menuEl || menuEl.hidden) return;
      const vw = window.innerWidth || document.documentElement.clientWidth || 0;
      const vh = window.innerHeight || document.documentElement.clientHeight || 0;
      if (!vw || !vh) return;

      // Preferred width: the configured menu width, never wider than the screen.
      const widths = MENU_WIDTHS;
      const wantW = Math.max(MENU_MIN_W, Math.min(widths[menuPrefs.width] || widths.medium, vw - MENU_GUTTER * 2));
      setS(menuEl, "width", Math.round(wantW) + "px");
      setS(menuEl, "maxWidth", "calc(100vw - " + MENU_GUTTER * 2 + "px)");

      // Horizontal: hug the anchor's right edge, then clamp BOTH edges into the
      // viewport. The clamp is what guarantees the panel can never slide off the
      // left edge, whatever the composer's geometry is.
      const right0 = (typeof anchorRight === "number" && isFinite(anchorRight))
        ? anchorRight
        : vw - MENU_GUTTER;
      const right = Math.max(MENU_GUTTER, Math.min(right0, vw - wantW - MENU_GUTTER));
      setS(menuEl, "right", Math.round(right) + "px");
      setS(menuEl, "left", "auto");

      // Vertical: sit just above the anchor's top edge, capped so the panel
      // always has at least MENU_MIN_H of room and never runs off the top.
      const bottomGap = MENU_GUTTER - 2; // 6px visual gap above the bar
      const baseTop = (typeof anchorTop === "number" && isFinite(anchorTop)) ? anchorTop : vh;
      const minRoom = Math.min(MENU_MIN_H, Math.max(0, vh - MENU_GUTTER * 2));
      const above = baseTop - bottomGap - MENU_GUTTER;
      const bottom = above >= minRoom ? Math.max(MENU_GUTTER, vh - baseTop + bottomGap) : MENU_GUTTER;
      const avail = Math.max(0, vh - bottom - MENU_GUTTER);
      setS(menuEl, "bottom", Math.round(bottom) + "px");
      setS(menuEl, "top", "auto");
      setS(menuEl, "maxHeight", Math.round(avail) + "px");
      // A fixed (but screen-capped) height keeps the panel from jumping as you move
      // between short and long categories; the pane scrolls inside it.
      setS(menuEl, "height", Math.round(Math.min(avail, 640)) + "px");
      const railMode = wantW < 500 ? "icons" : "full";
      if (menuEl.dataset.rail !== railMode) menuEl.dataset.rail = railMode;
    }

    // Anchored mode bookkeeping: the composer element whose top padding we are
    // borrowing to seat the bar (see the anchored branch below). Cleared when we
    // leave anchored mode so the site's composer returns to its normal layout.
    let anchorPadEl = null, anchorPadPrev = null;
    function clearAnchorPad() {
      if (anchorPadEl) {
        try {
          if (anchorPadPrev && anchorPadPrev.value) {
            anchorPadEl.style.setProperty("padding-top", anchorPadPrev.value, anchorPadPrev.priority || "");
          } else {
            anchorPadEl.style.removeProperty("padding-top");
          }
        } catch {}
        anchorPadEl = null; anchorPadPrev = null;
      }
    }

    // Write a style property only when it actually changes. placeBar runs every
    // animation frame; assigning identical values still invalidates style on some
    // engines and was the source of the bar "shimmering" during composer growth.
    const reserveBroken = { el: null, n: 0, on: false };
    function resetBarLayout(){
      if(!bar)return;
      const vars=[...bar.style].filter(k=>k.startsWith('--')).map(k=>[k,bar.style.getPropertyValue(k),bar.style.getPropertyPriority(k)]);
      bar.style.cssText='';for(const [k,v,p]of vars)bar.style.setProperty(k,v,p);
    }
    function setS(el, prop, val) { if (el && el.style[prop] !== val) el.style[prop] = val; }

    // Shared composer rectangle for the floating docks. Preference order: the
    // provider's validated geometry, its anchor element, its frame, its editor.
    function composerRect() {
      try {
        const g = (P.barGeometry && P.barGeometry()) || genericGeometry();
        if (g && g.width > 0) return { left: g.left, top: g.top, width: g.width, right: g.left + g.width };
        const el = (P.barAnchor && P.barAnchor()) || (P.composerFrame && P.composerFrame()) || (P.getEditor && P.getEditor());
        if (el && el.isConnected) { const r = el.getBoundingClientRect(); if (r.width > 0) return { left: r.left, top: r.top, width: r.width, right: r.right }; }
      } catch {}
      return null;
    }

    // Validated geometry for providers that only expose barAnchor() (Claude, Kimi,
    // Meta…). The anchor is trusted only while it plausibly IS the composer card:
    // not absurdly tall, and the editor sits near its top. Otherwise the bar docks
    // straight above the editor instead of floating in an unrelated wrapper.
    function genericGeometry() {
      const el = P.barAnchor && P.barAnchor();
      if (!el || !el.isConnected) return null;
      const r = el.getBoundingClientRect();
      if (!r.width) return null;
      let ed = null, er = null;
      try { ed = P.getEditor && P.getEditor(); er = ed && ed.getBoundingClientRect(); } catch {}
      if (er && er.width > 0 && (r.height > 460 || er.top - r.top > 160 || er.top < r.top - 6)) {
        const pad = 12;
        return { mode: "editor", el: ed, reserve: null, left: er.left - pad, top: er.top, width: er.width + pad * 2, height: er.height, inset: { left: pad, right: pad } };
      }
      let inset = (P.barInset && P.barInset()) || null;
      if (!inset && er && er.width > 0) {
        const l = er.left - r.left, rr = r.right - er.right;
        if (l >= 8 && l <= 56 && rr >= 8 && rr <= 56) inset = { left: Math.round(l), right: Math.round(rr) };
      }
      return { mode: "card", el, reserve: el, left: r.left, top: r.top, width: r.width, height: r.height, inset };
    }

    // ── Chat bar nudge (6.28.2) ─────────────────────────────────────────────
    // Offsets are remembered per AI site and work in EVERY dock. Free docks fold
    // them into left/top; the automatic docks apply them as a CSS `translate`, so
    // the host's layout (and the padding we reserve in it) never changes. The
    // open menu is always anchored to the UN-nudged bar position: before 6.28.2
    // the menu followed the bar, so dragging a slider moved the slider itself.
    function nudgeOf() {
      const site = (menuPrefs.barOffsetBy || {})[P.id];
      if (site) return { x: Number(site.x) || 0, y: Number(site.y) || 0 };
      return { x: Number(menuPrefs.barOffsetX) || 0, y: Number(menuPrefs.barOffsetY) || 0 };
    }
    const nudgeClamp = { x: false, y: false };
    function reportNudgeClamp(cx, cy) {
      if (nudgeClamp.x === cx && nudgeClamp.y === cy) return;
      nudgeClamp.x = cx; nudgeClamp.y = cy;
      if (!menuEl) return;
      const a = menuEl.querySelector("#ms-bar-ox"), b = menuEl.querySelector("#ms-bar-oy");
      if (a && a.closest(".zs-slider-row")) a.closest(".zs-slider-row").classList.toggle("zs-clamped", cx);
      if (b && b.closest(".zs-slider-row")) b.closest(".zs-slider-row").classList.toggle("zs-clamped", cy);
    }
    function currentTranslate() {
      const m = /^(-?[\d.]+)px(?:\s+(-?[\d.]+)px)?$/.exec(bar.style.translate || "");
      return m ? { x: parseFloat(m[1]), y: parseFloat(m[2]||"0") } : { x: 0, y: 0 };
    }
    // Automatic docks: nudge by translate, clamped so the bar can never leave the window.
    function applyVisualNudge() {
      const n = nudgeOf();
      let tx = n.x, ty = n.y, cx = false, cy = false;
      if (tx || ty) {
        const vw = window.innerWidth || 0, vh = window.innerHeight || 0;
        const r = bar.getBoundingClientRect();
        if (r.width && vw && vh) {
          const cur = currentTranslate();
          const bx = r.left - cur.x, by = r.top - cur.y;
          const nx = Math.max(8 - bx, Math.min(vw - 8 - (bx + r.width), tx));
          const ny = Math.max(8 - by, Math.min(vh - 8 - (by + r.height), ty));
          cx = Math.abs(nx - tx) > 0.5; cy = Math.abs(ny - ty) > 0.5; tx = nx; ty = ny;
        }
      }
      setS(bar, "translate", Math.round(ty) ? `${Math.round(tx)}px ${Math.round(ty)}px` : Math.round(tx) ? `${Math.round(tx)}px` : "");
      reportNudgeClamp(cx, cy);
    }

    // Free docks: "float" hugs the top of the composer, "window" pins a pill to the
    // bottom of the window. Both leave the site's DOM completely untouched (no
    // padding borrowed, nothing inserted), which is why they are also the safe
    // fallback whenever a site's layout confuses the automatic dock.
    function placeFreeBar(dock, forced = null) {
      clearAnchorPad();
      bar.classList.remove("zs-bar-inline", "zs-bar-inside", "zs-bar-anchored", "zs-bar-detached");
      bar.classList.add("zs-bar-free");
      if (root && bar.parentElement !== root) root.appendChild(bar);
      const vw = window.innerWidth || document.documentElement.clientWidth || 0;
      const vh = window.innerHeight || document.documentElement.clientHeight || 0;
      if (!vw || !vh) return;
      const ref = dock === "float" ? composerRect() : null;
      if (dock === "float" && !ref && !P.persistentBarWhenNoEditor) { setS(bar, "display", "none"); if (menuEl) menuEl.hidden = true; return; }
      setS(bar, "display", "flex");
      setS(bar, "paddingLeft", ""); setS(bar, "paddingRight", "");
      const fit = forced && typeof forced.fit === "boolean" ? forced.fit : menuPrefs.barFit === "fit";
      if (bar.classList.contains("zs-bar-fit") !== fit) bar.classList.toggle("zs-bar-fit", fit);
      const avail = Math.max(240, vw - 16);
      let w;
      // Use the preferred measured width independently of left-position changes,
      // so centering/nudging a fit bar cannot feed back into its own width.
      if (fit) w = Math.min(avail, barNaturalWidth || 700);
      else w = Math.round(Math.min(avail, ref ? ref.width : 640));
      setS(bar, "width", w + "px"); setS(bar, "maxWidth", avail + "px");
      const bh = bar.offsetHeight || 40;
      const area = ref || { left: 8, right: vw - 8, width: vw - 16, top: vh - 12 };
      const align = (forced && forced.align) || menuPrefs.barAlign;
      let x = align === "right" ? area.right - w : align === "center" ? area.left + (area.width - w) / 2 : area.left;
      let y = ref ? ref.top - bh - 8 : vh - bh - ((forced && forced.bottom) || 14);
      // Base (un-nudged) position: the open menu is anchored here so that dragging a
      // nudge slider never moves the slider itself.
      const x0 = Math.max(8, Math.min(x, vw - w - 8)), y0 = Math.max(8, Math.min(y, vh - bh - 8));
      const nd = nudgeOf();
      const xn = x0 + nd.x, yn = y0 + nd.y;
      x = Math.max(8, Math.min(xn, vw - w - 8)); y = Math.max(8, Math.min(yn, vh - bh - 8));
      reportNudgeClamp(Math.abs(x - xn) > 0.5, Math.abs(y - yn) > 0.5);
      setS(bar, "translate", "");
      setS(bar, "left", Math.round(x) + "px"); setS(bar, "top", Math.round(y) + "px");
      setS(bar, "right", "auto"); setS(bar, "bottom", "auto");
      syncBarFit(w);
      if (menuEl && !menuEl.hidden) placeMenu(vw - (x0 + w), y0);
    }

    // Responsive bar chrome is driven by the actual composer/bar width, not the
    // viewport. Fit actual visible controls against the measured anchor and
    // recover the selected size as soon as enough space becomes available.
    let barFitKey = "", barNaturalWidth = 0, barSizingContext;
    const effortLabelWidths = new Map();
    document.fonts?.addEventListener('loadingdone',()=>{barFitKey='';effortLabelWidths.clear();});
    function syncBarFit(width) {
      const w = Number(width) || 0, acts = bar.querySelector('#zs-acts');
      if (!w || !acts) return;
      const tiny = w < 480;
      if (bar.classList.contains('zs-bar-tiny') !== tiny) bar.classList.toggle('zs-bar-tiny',tiny);
      const key = JSON.stringify([Math.round(w),menuPrefs.barSize,menuPrefs.barStatus,menuPrefs.barStyle,menuPrefs.font,menuPrefs.scale,menuPrefs.barFit,bar.style.paddingLeft,bar.style.paddingRight,bar.dataset.msBarTheme,bar.dataset.msBarLight,bar.dataset.msBarClash,bar.dataset.msHide,bar.classList.contains('zs-bar-inline'),bar.classList.contains('zs-bar-free'),brandEl?.textContent,[...acts.children].map(e=>[e.id,e.textContent,e.style.display,e.hidden])]);
      if (key === barFitKey) return;
      barFitKey = key;
      for (const c of ['zs-bar-narrow','zs-bar-compact','zs-bar-tight']) bar.classList.remove(c);
      const preferred = menuPrefs.barSize === 'roomy' ? [36,13,8] : menuPrefs.barSize === 'compact' ? [26,11,5] : [30,12,6];
      const css = (name,value) => { if(bar.style.getPropertyValue(name)!==value)bar.style.setProperty(name,value); };
      const setDensity = (name,values) => {
        if(bar.dataset.msFitDensity!==name)bar.dataset.msFitDensity=name;
        css('--ms-fit-h',values[0]+'px');css('--ms-fit-fs',values[1]+'px');css('--ms-fit-gap',values[2]+'px');css('--ms-fit-bar-gap',name==='preferred'?'12px':'8px');
        if(acts.style.width)acts.style.width='';
      };
      const visible = e => getComputedStyle(e).display !== 'none' && !e.hidden;
      const identityMinimum = () => {
        const brand=bar.querySelector('#zs-brand'),dot=bar.querySelector('#zs-dot'),id=bar.querySelector('#zs-id');
        const children=brand&&visible(brand)?[...brand.children].filter(visible):[];
        const brandWidth=children.reduce((n,e)=>{
          let width=Math.max(e.scrollWidth,e.getBoundingClientRect().width);
          if(e.id==='ms-effort-indicator') {
            const s=getComputedStyle(e),font='800 '+s.fontSize+' '+s.fontFamily,k=font+'|'+s.letterSpacing;
            let maximum=effortLabelWidths.get(k);
            if(maximum===undefined){
              barSizingContext ||= document.createElement('canvas').getContext('2d');
              if(barSizingContext){barSizingContext.font=font;maximum=Math.max(...['Adaptive','Quick','Standard','Deep','Maximum','Ultra'].map(t=>barSizingContext.measureText(t).width+(parseFloat(s.letterSpacing)||0)*Math.max(0,t.length-1)));}
              else maximum=width;
              if(effortLabelWidths.size>64)effortLabelWidths.clear();effortLabelWidths.set(k,maximum);
            }
            width=Math.max(width,maximum+(parseFloat(s.paddingLeft)||0)+(parseFloat(s.paddingRight)||0)+(parseFloat(s.borderLeftWidth)||0)+(parseFloat(s.borderRightWidth)||0)+2);
          }
          return n+width;
        },0)+Math.max(0,children.length-1)*(parseFloat(getComputedStyle(brand).columnGap)||4);
        const min=brandWidth?brandWidth+(dot&&visible(dot)?dot.getBoundingClientRect().width:0)+(parseFloat(getComputedStyle(id).columnGap)||0)+10:(bar.querySelector('#zs-state')&&visible(bar.querySelector('#zs-state'))?110:20);
        css('--ms-bar-identity-min',Math.ceil(min)+'px');return Math.ceil(min);
      };
      const candidates=[['preferred',preferred],['snug',[preferred[0],preferred[1],2]]];
      if(menuPrefs.barSize!=='roomy') {
        if(preferred[0]>26)candidates.push(['compact',[26,11,2]]);
        candidates.push(['tight',[24,10.5,2]]);
      }
      for(const [name,values] of candidates) {
        setDensity(name,values);
        const style=getComputedStyle(bar),padding=(parseFloat(style.paddingLeft)||0)+(parseFloat(style.paddingRight)||0)+(parseFloat(style.borderLeftWidth)||0)+(parseFloat(style.borderRightWidth)||0),gap=parseFloat(style.columnGap)||0;
        const minimum=identityMinimum(),natural=acts.getBoundingClientRect().width;
        if(name==='preferred')barNaturalWidth=Math.ceil(natural+minimum+padding+gap);
        const available=w-padding-gap-minimum;
        if(natural<=available+.5)return;
        if(name!=='preferred'&&available>0) {
          let savings=0;
          for(const id of ['zs-action','zs-software','zs-model']) {
            const e=bar.querySelector('#'+id);if(!e||!visible(e))continue;
            savings+=Math.max(0,e.getBoundingClientRect().width-(parseFloat(getComputedStyle(e).minWidth)||0));
          }
          if(natural-savings<=available+.5) {
            acts.style.width=Math.floor(available)+'px';
            const right=acts.getBoundingClientRect().right;
            if([...acts.children].filter(visible).every(e=>e.getBoundingClientRect().right<=right+.75))return;
          }
        }
      }
      // Preserve explicitly Roomy controls. Stack only if their real contents
      // cannot fit beside the identity, rather than forcing rows by bar width.
      setDensity('stacked',menuPrefs.barSize==='roomy'?[36,13,2]:[24,10.5,2]);
      identityMinimum();
    }

    // Native model/effort menus must retain their click targets above the bar.
    // Visibility leaves the in-flow slot intact, avoiding a menu/toolbar jump.
    function yieldToNativePopup() {
      const targets=[bar,document.getElementById('zs-input-cover')].filter(Boolean);
      const rect=bar.getBoundingClientRect();
      const own='#zs-root,#zs-bar,[id^="zs-"],[id^="ms-"],.zs-chip';
      const selectors='[role="menu"],[role="listbox"],[role="dialog"],[popover]:popover-open,.cdk-overlay-pane,.ant-dropdown,.v-binder-follower-content,.mode-select-dropdown,[data-radix-popper-content-wrapper]';
      const overlaps=[...document.querySelectorAll(selectors)].some(el=>{
        if(el.closest(own)||el.contains(bar)||el.contains(P.getEditor?.())||el.closest('[hidden],[inert],[aria-hidden="true"]'))return false;
        const style=getComputedStyle(el);if(style.display==='none'||style.visibility==='hidden'||style.opacity==='0')return false;
        const r=el.getBoundingClientRect();return r.width>0&&r.height>0&&r.bottom>rect.top&&r.top<rect.bottom&&r.right>rect.left&&r.left<rect.right;
      });
      for(const target of targets)target.classList.toggle('zs-yield-native-popup',overlaps);
      if(overlaps&&menuEl&&!notionProbing)menuEl.hidden=true;
    }

    function placeBar() {
      barRaf = requestAnimationFrame(() => { placeBar(); yieldToNativePopup(); });
      if (!bar) return;

      // Self-heal: a SPA navigation or a full re-render on the host (seen on Arena
      // when the message frame jumps/teleports to the bottom) can detach our whole
      // #zs-root from <html>, taking the bar with it - and nothing re-adds it, so
      // the panel just vanishes. Re-append it whenever it's been detached; this
      // rAF loop is resilient (its next frame is scheduled before any body code),
      // so the panel reappears on the very next frame.
      if (root && !root.isConnected) {
        try { document.documentElement.appendChild(root); } catch {}
      }

      // While a bot-check challenge OR a blocking modal (login / consent) is on
      // screen, get fully out of the way: the (often transparent) anchored bar is
      // a real full-width element over the composer's top edge and would silently
      // intercept clicks on the challenge's / modal's buttons (e.g. "Continue with
      // Google" at sign-in). Hide the bar and drop the reserved padding strip; it
      // reappears on the next frame once the overlay clears.
      if (
        (P.captchaPresent && P.captchaPresent()) ||
        (P.overlayBlocking && P.overlayBlocking())
      ) {
        bar.style.display = "none";
        clearAnchorPad();
        if (menuEl) menuEl.hidden = true;
        return;
      }

      // User-chosen free dock (Chat bar tab): bypass every provider mount.
      const dock = menuPrefs.barDock || "auto";
      if (dock !== "auto") { placeFreeBar(dock); return; }
      if (bar.classList.contains("zs-bar-free")) {
        bar.classList.remove("zs-bar-free", "zs-bar-fit");
        resetBarLayout(); // drop the free-dock geometry before an automatic dock re-measures
      }

      // Preferred: in-flow mount inside the composer (no overlap, full width).
      const mount = computeBarMount();
      if (mount) {
        clearAnchorPad();
        bar.classList.remove('zs-bar-detached','zs-bar-anchored');
        if (bar.parentElement !== mount.parent || bar.nextElementSibling !== mount.before) {
          try { mount.parent.insertBefore(bar, mount.before || null); } catch {}
        }
        if (!bar.classList.contains("zs-bar-inline")) {
          bar.classList.add("zs-bar-inline");
          resetBarLayout(); // drop any leftover float positioning
        }
        // Transparent (blends in) when mounted INSIDE the input box; surface card
        // when mounted ABOVE it. The provider's barMount() signals which via .inside.
        bar.classList.toggle("zs-bar-inside", !!mount.inside);
        bar.style.display = "flex";
        if(mount.width){setS(bar,"width",Math.max(0,Math.min(mount.width,innerWidth-24))+"px");setS(bar,"maxWidth","100%");setS(bar,"flexShrink","0");}
        syncBarFit(bar.getBoundingClientRect().width);
        if (menuEl && !menuEl.hidden) {
          const br = bar.getBoundingClientRect(), tr = currentTranslate();
          placeMenu(window.innerWidth - (br.right - tr.x), br.top - tr.y);
        }
        applyVisualNudge();
        return;
      }

      // Anchored mode: the provider wants the integrated, in-composer LOOK but
      // its composer is a framework-reconciled subtree we must NOT insert our
      // node into (e.g. Kimi's Vue tree, Notion's React tree). So the bar lives in
      // our own #zs-root, position:fixed, hugging the composer's top edge at full
      // width, and RESERVES that strip with padding-top on the composer so it
      // reads as in-flow. A provider may supply barGeometry() (validated against
      // the editor's real rectangle - Notion does) or just barAnchor().
      const geo = (P.barGeometry && P.barGeometry()) || genericGeometry();
      const anchorEl = geo ? geo.el : ((P.barAnchor && P.barAnchor()) || null);
      if (anchorEl && anchorEl.isConnected) {
        bar.classList.remove("zs-bar-inline", "zs-bar-inside", "zs-bar-free", "zs-bar-detached");
        setS(bar,"right","");setS(bar,"bottom","");
        bar.classList.add("zs-bar-anchored");
        if (root && bar.parentElement !== root) root.appendChild(bar);
        const r = geo ? { left: geo.left, top: geo.top, width: geo.width } : anchorEl.getBoundingClientRect();
        const vh = window.innerHeight || document.documentElement.clientHeight || 0;
        if (!r.width) { setS(bar, "display", "none"); clearAnchorPad(); if (menuEl) menuEl.hidden = true; return; }
        // A composer scrolled completely out of view must not leave the bar
        // floating over unrelated content.
        const rb = geo ? geo.top + (geo.height || 0) : (anchorEl.getBoundingClientRect().bottom);
        if (vh && (rb < 0 || r.top > vh)) { setS(bar, "display", "none"); if (menuEl) menuEl.hidden = true; return; }
        setS(bar, "display", "flex");
        const bh = bar.offsetHeight || 34;
        const styled = menuPrefs.barStyle !== "native";
        const gap = styled ? 8 : 0; // styled bars float as a chip INSIDE the card edge
        // Reservation self-check: if the site refuses our padding-top (e.g. an
        // !important rule), the bar would sit ON the input. Detect "editor still
        // overlaps the bar" for several consecutive frames and dock above instead.
        let edEl = null; try { edEl = P.getEditor && P.getEditor(); } catch {}
        if (reserveBroken.el !== anchorEl) { reserveBroken.el = anchorEl; reserveBroken.n = 0; reserveBroken.on = false; }
        const editorMode = !!(geo && (geo.mode === "editor" || geo.dockOutside)) || reserveBroken.on;
        const reserveEl = reserveBroken.on ? null : (geo ? geo.reserve : anchorEl);
        if (reserveEl && edEl && !reserveBroken.on) {
          const ee = edEl.getBoundingClientRect();
          const overlaps = ee.width > 0 && ee.top < (r.top + gap + bh) - 3 && ee.bottom > r.top;
          reserveBroken.n = overlaps ? reserveBroken.n + 1 : 0;
          if (reserveBroken.n >= 8) { reserveBroken.on = true; }
        }
        if (reserveEl) {
          if (anchorPadEl && anchorPadEl !== reserveEl) clearAnchorPad();
          if (anchorPadEl !== reserveEl) {
            anchorPadEl = reserveEl;
            anchorPadPrev = {
              value: reserveEl.style.getPropertyValue("padding-top"),
              priority: reserveEl.style.getPropertyPriority("padding-top"),
            };
          }
          setS(reserveEl, "paddingTop", (bh + 6 + gap) + "px"); // reserve the strip the bar sits in (+gap)
        } else clearAnchorPad();
        const inset = (!styled && ((geo && geo.inset) || (P.barInset && P.barInset()))) || null;
        if (inset && (inset.left > 0 || inset.right > 0)) {
          setS(bar, "paddingLeft", Math.round(inset.left) + "px");
          setS(bar, "paddingRight", Math.round(inset.right) + "px");
        } else { setS(bar, "paddingLeft", ""); setS(bar, "paddingRight", ""); }
        // "editor" mode has nothing to reserve, so the bar sits directly ABOVE the input row
        const top = editorMode ? Math.max(4, (geo && geo.mode === "editor" ? r.top : r.top) - bh - 6) : r.top + gap;
        setS(bar, "left", Math.round(r.left + gap) + "px");
        setS(bar, "top", Math.round(top) + "px");
        setS(bar, "width", Math.round(r.width - gap * 2) + "px");
        bar.classList.toggle("zs-bar-above", editorMode);
        syncBarFit(r.width - gap * 2);
        if (menuEl && !menuEl.hidden) {
          bar.classList.remove("zs-bar-inline"); // ensure fixed geometry for menu math
          placeMenu(window.innerWidth - (r.left + r.width), top);
        }
        applyVisualNudge();
        return;
      }
      bar.classList.remove("zs-bar-anchored");
      clearAnchorPad();

      // Fallback: float just above the editor (fixed positioning), for sites
      // where no clean inline mount could be resolved.
      if (bar.classList.contains("zs-bar-inline")) {
        bar.classList.remove("zs-bar-inline");
        if (root && bar.parentElement !== root) root.appendChild(bar);
      }
      const f = (P.getEditor && P.getEditor()) || (P.composerFrame && P.composerFrame());
      if (!f) {
        if (P.persistentBarWhenNoEditor) {
          clearAnchorPad();
          bar.classList.remove("zs-bar-inline", "zs-bar-inside", "zs-bar-anchored");
          bar.classList.add("zs-bar-detached");
          if (root && bar.parentElement !== root) root.appendChild(bar);
          bar.style.display = "flex"; bar.style.width = "min(560px, calc(100vw - 32px))";
          syncBarFit(Math.min(560, Math.max(0, window.innerWidth - 32)));
          bar.style.left = "auto"; bar.style.right = "16px"; bar.style.top = "auto"; bar.style.bottom = "16px";
          if (menuEl && !menuEl.hidden) placeMenu(16, window.innerHeight - (bar.offsetHeight || 40) - 24);
          applyVisualNudge();
          return;
        }
        bar.style.display = "none"; if (menuEl) menuEl.hidden = true; return;
      }
      bar.classList.remove("zs-bar-detached"); bar.style.right = ""; bar.style.bottom = "";
      bar.style.display = "flex";
      const r = composerRect() || f.getBoundingClientRect();
      if (!r.width) { bar.style.display = "none"; return; }
      const w = Math.min(r.width, window.innerWidth-16);
      const left = Math.round(r.left + (r.width - w) / 2);
      const bh = bar.offsetHeight || 40;
      const top = Math.max(4, Math.round(r.top - bh - BAR_GAP));
      bar.style.width = w + "px";
      syncBarFit(w);
      bar.style.left = left + "px";
      bar.style.top = top + "px";
      // Keep the open "more" menu anchored to the bar, opening upward.
      if (menuEl && !menuEl.hidden) {
        const br = bar.getBoundingClientRect(), tr = currentTranslate();
        placeMenu(window.innerWidth - (br.right - tr.x), br.top - tr.y);
      }
      applyVisualNudge();
    }

    // Called by the core's sweep + after state changes: refresh the bar content.
    // (Positioning runs continuously in placeBar; this only updates what's shown.)
    function updateStartGate() { renderBar(); }

    // Masks the input box while the extension types/sends, so the copied text
    // and the submit aren't visible to the user.
    // Returns a FULLY OPAQUE colour that matches what is VISUALLY behind the cover.
    // The cover must hide the typed text, so it can't be translucent - but simply
    // returning the first solid ancestor is wrong when the composer surface itself
    // is translucent: Meta's card is rgba(56,56,56,0.8) over a dark page, so its
    // real on-screen colour is a BLEND (~rgb(50,50,50)), lighter than the bare page
    // (rgb(24,24,25)). Filling the cover with the page colour made it visibly
    // darker than the composer. So collect the background layers from `el` up to
    // the first opaque ancestor and FLATTEN them (alpha compositing) into one solid
    // colour that reproduces the composer's actual appearance.
    function opaqueBg(el) {
      const layers = [];
      let n = el;
      while (n) {
        const c = parseColor(getComputedStyle(n).backgroundColor);
        if (c && c.a > 0) {
          layers.push(c);
          if (c.a >= 0.999) break; // opaque base reached - nothing behind matters
        }
        n = n.parentElement;
      }
      // Guarantee an opaque base at the bottom of the stack.
      if (!layers.length || layers[layers.length - 1].a < 0.999) {
        const dark = getComputedStyle(document.documentElement).colorScheme.split(' ').includes('dark') || matchMedia('(prefers-color-scheme: dark)').matches;
        const base = { r: dark ? 24 : 255, g: dark ? 24 : 255, b: dark ? 24 : 255, a: 1 };
        layers.push({ r: base.r, g: base.g, b: base.b, a: 1 });
      }
      // We collected top-most (el) first, so composite from the opaque base (last)
      // upward toward el (first).
      let out = layers[layers.length - 1];
      for (let i = layers.length - 2; i >= 0; i--) out = blendOver(layers[i], out);
      return `rgb(${Math.round(out.r)}, ${Math.round(out.g)}, ${Math.round(out.b)})`;
    }
    // Parse an rgb()/rgba() computed colour into {r,g,b,a}. Returns null for
    // "transparent"/unparseable. getComputedStyle always yields rgb/rgba form.
    function parseColor(c) {
      if (!c || c === "transparent") return null;
      const m = c.match(/rgba?\(([^)]+)\)/i);
      if (!m) {
        // Resolve modern provider colors (oklch, color(srgb ...)) in the browser.
        try {
          const canvas=document.createElement('canvas');canvas.width=canvas.height=1;
          const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.clearRect(0,0,1,1);ctx.fillStyle=c;ctx.fillRect(0,0,1,1);
          const p=ctx.getImageData(0,0,1,1).data;
          return {r:p[0],g:p[1],b:p[2],a:p[3]/255};
        } catch { return null; }
      }
      const p = m[1].split(",").map((x) => parseFloat(x));
      return { r: p[0], g: p[1], b: p[2], a: p.length >= 4 ? p[3] : 1 };
    }
    // Source-over compositing of a (possibly translucent) fg onto an opaque bg.
    function blendOver(fg, bg) {
      const a = fg.a;
      return {
        r: fg.r * a + bg.r * (1 - a),
        g: fg.g * a + bg.g * (1 - a),
        b: fg.b * a + bg.b * (1 - a),
        a: 1,
      };
    }

    function inputCover(on) {
      const ed = P.getEditor();
      if (!on) {
        if (cover) { cover.style.display = "none"; cover.dataset.on = ""; }
        if (ed) ed.classList.remove("zs-typing");
        cancelAnimationFrame(coverRaf);
        return;
      }
      if (!ed) return;
      ed.classList.add("zs-typing"); // make the typed text itself invisible
      if (!cover) {
        cover = document.createElement("div");
        cover.id = "zs-input-cover";
        cover.innerHTML = `<span>Agent is working…</span>`;
        document.documentElement.appendChild(cover);
      }
      cover.dataset.on = "1"; // intent flag: keep the place() loop alive while set
      cover.style.display = "flex";
      const place = () => {
        // Loop runs while the cover is INTENDED on (dataset.on), not while it's
        // visible - so we can hide it for an overlay and still restore it after.
        if (!cover || cover.dataset.on !== "1") return;
        const e = P.getEditor();
        if (!e) { coverRaf = requestAnimationFrame(place); return; }
        // Re-assert the typing mask on the CURRENT editor node: sites that
        // recreate the editor on each inject/clear (Kimi's Vue) drop the class,
        // which would un-hide the raw text and un-cap its height. Cheap idempotent
        // add every frame keeps the mask + height cap glued to the live node.
        if (!e.classList.contains("zs-typing")) e.classList.add("zs-typing");
        // The cover is SIZED to coverTarget() when a provider supplies one, else
        // to the editor node itself. Some composers (Meta AI) make the editable a
        // tiny line inside a much larger rounded card - covering only the editor
        // left the rest of the card exposed and CLICKABLE (a careful click focused
        // the editor and let the user type behind the cover). Meta returns its
        // whole composer card so the cover blankets the entire input band and its
        // pointer-events:auto blocks every click. The typing mask above still lives
        // on the real editor node `e`.
        const covNode = (P.coverTarget && P.coverTarget()) || e;
        // While a blocking modal (login / consent) or bot-check is up, hide the
        // cover so it doesn't sit on top of the modal; it reappears once the
        // overlay clears (the loop keeps running).
        if (
          (P.overlayBlocking && P.overlayBlocking()) ||
          (P.captchaPresent && P.captchaPresent())
        ) {
          cover.style.display = "none";
          coverRaf = requestAnimationFrame(place);
          return;
        }
        cover.style.display = "flex";
        let r = covNode.getBoundingClientRect();
        // Clip the cover to the composer's VISIBLE band. Some composers grow the
        // inner editor node past a scrolling ancestor that clips it (Kimi's Vue
        // RECREATES .chat-input-editor on every inject/clear, dropping the
        // .zs-typing height cap, so the editor balloons to ~1500px while its
        // .chat-input-editor-container caps the visible box via overflow:auto).
        // Measuring the raw editor then centres the cover on the giant editor's
        // midpoint - far below the visible input - so it "vanishes" off the box.
        // Intersect with the nearest clipping ancestor to track what's on screen.
        // The SAME clipping applies horizontally, and for the same reason: a
        // composer whose editor is a flex item grows to its content width when a
        // long unbroken line is injected, while an ancestor with overflow-x:hidden
        // keeps the PAGE looking right. Seen on ChatGPT at Start, where the editor
        // is filled with the (large) system prompt: the inner
        // .prosemirror-parent widened past its `-my-2.5 flex overflow-x-hidden`
        // wrapper, so the cover - position:fixed and sized to the raw rect - stuck
        // out to the RIGHT of the composer card. Clip on each axis independently:
        // the ancestor that clips X is not always the one that clips Y.
        let clipY = false, clipX = false;
        for (let a = covNode.parentElement, i = 0; a && a !== document.body && i < 8 && !(clipX && clipY); a = a.parentElement, i++) {
          const st = getComputedStyle(a);
          const clips = (v) => v === "auto" || v === "scroll" || v === "hidden";
          const ar = a.getBoundingClientRect();
          if (!clipY && clips(st.overflowY)) {
            clipY = true;
            const top = Math.max(r.top, ar.top);
            const bottom = Math.min(r.bottom, ar.bottom);
            if (bottom > top) r = new DOMRect(r.left, top, r.width, bottom - top);
          }
          if (!clipX && clips(st.overflowX)) {
            clipX = true;
            const left = Math.max(r.left, ar.left);
            const right = Math.min(r.right, ar.right);
            if (right > left) r = new DOMRect(left, r.top, right - left, r.height);
          }
        }
        // Never paint outside the composer card. The cover is position:fixed and
        // re-placed every rAF from a freshly measured rect, which is correct while
        // the page is still - but a site that ANIMATES its composer updates layout
        // AFTER our callback, so for the whole animation the cover trails one frame
        // behind. Seen on ChatGPT at Start: injecting the system prompt grows the
        // composer 58px -> 156px, the page gains a scrollbar, the content column
        // narrows and the composer slides 29px left - while the cover kept the
        // previous coordinates and hung 28px past the card's right edge. It only
        // showed on the FIRST send, because afterwards the composer is already
        // docked at the bottom and stops moving. Clamping to the composer frame
        // makes a stale rect impossible to see: worst case the cover is briefly a
        // few px small, which reads as nothing.
        const frame = P.composerFrame && P.composerFrame();
        if (frame) {
          const fr = frame.getBoundingClientRect();
          // Only clamp to a frame that really wraps the cover target, so a provider
          // whose frame is narrower than its editor can never shrink the cover.
          const cx = r.left + r.width / 2;
          if (fr.width > 0 && fr.left <= cx && fr.right >= cx) {
            const left = Math.max(r.left, fr.left);
            const right = Math.min(r.right, fr.right);
            if (right - left > 40) r = new DOMRect(left, r.top, right - left, r.height);
          }
        }
        // Optionally overshoot the editor box by PAD px on every side. Some
        // composers (Gemini's Quill) keep typed text near rounded corners, so a
        // cover sized EXACTLY to the editor leaves slivers of text peeking; those
        // providers set coverPad to bleed past the edges. A native <textarea>
        // (DeepSeek) needs none - overshooting there just makes the cover overflow
        // the composer, so it defaults to 0.
        const PAD = P.coverPad || 0;
        // Optional vertical nudge: some composers (Gemini's Quill) report an
        // editor rect that sits a few px below the visual input box centre, so
        // the centred "Agent is working…" text looks low. A provider can shift it.
        const OFFY = P.coverOffsetY || 0;
        // Height is at least MIN_H so the label is readable even over a
        // single-line composer. CENTER the cover on the editor's vertical middle
        // rather than anchoring its TOP to the editor top: a short (e.g. 20px)
        // textarea bumped to 36px would otherwise grow only DOWNWARD, leaving the
        // "Agent is working…" label sitting high in the composer's input band
        // (seen on Cloudflare's 1-line textarea). For a composer already taller
        // than MIN_H the maths reduces to the old `r.top - PAD`, so DeepSeek/Gemini
        // are unchanged.
        // Hard ceiling: even though .zs-typing caps the editor's visual height
        // (see overlay.css), belt-and-suspenders clamp the cover so a composer
        // whose growing element escapes that CSS cap on some provider can never
        // turn the "Agent is working…" cover into a full-page white slab.
        const MAXH = P.coverMaxH || 200;
        const h = Math.min(Math.max(r.height + PAD * 2, 36), MAXH);
        const centerY = r.top + r.height / 2 + OFFY;
        cover.style.left = (r.left - PAD) + "px";
        cover.style.top = (centerY - h / 2) + "px";
        cover.style.width = (r.width + PAD * 2) + "px";
        cover.style.height = h + "px";
        // Composite the surface BEHIND the cover target so the fill matches what
        // the user sees (a translucent composer card blends over the page).
        cover.style.background = opaqueBg(covNode);
        // When the cover blankets a whole composer card (coverTarget), match its
        // corner radius so the cover's square corners don't poke past the card's
        // rounded ones. Editor-sized covers keep the CSS default.
        if (P.coverTarget) cover.style.borderRadius = getComputedStyle(covNode).borderRadius;
        coverRaf = requestAnimationFrame(place);
      };
      place();
    }

    function toast(msg) {
      const t = document.createElement("div");
      t.className = "zs-toast";
      t.textContent = msg;
      root.appendChild(t);
      setTimeout(() => t.classList.add("show"), 10);
      setTimeout(() => { t.classList.remove("show"); setTimeout(() => t.remove(), 300); }, 3500);
    }

    function banner(kind, title, msg) {
      const b = document.createElement("div");
      b.className = `zs-banner ${kind}`;
      b.innerHTML = `<div class="zs-banner-t"></div><div class="zs-banner-m"></div>
        <div class="zs-banner-acts">
          <button class="zs-banner-x">Close</button>
        </div>`;
      b.querySelector(".zs-banner-t").textContent = title;
      b.querySelector(".zs-banner-m").textContent = msg;
      b.querySelector(".zs-banner-x").addEventListener("click", () => b.remove());
      root.appendChild(b);
    }

    // Editable, provider-independent prompt review. Nothing has been sent yet:
    // the send is held until the user answers. "Send my original" sends the
    // untouched text; "Send improved prompt" sends the (editable) improved
    // version; closing / Esc sends nothing and leaves the text in the composer.
    function reviewEnhancedPrompt(original, result) {
      return new Promise((resolve) => {
        root.querySelectorAll(".zs-enhance-review").forEach((e) => e.remove());
        const shade = document.createElement("div");
        shade.className = "zs-enhance-review";
        shade.innerHTML = `<div class="zs-enhance-dialog" role="dialog" aria-modal="true" aria-labelledby="zs-enhance-review-title">
          <div class="zs-enhance-dialog-head"><div><b id="zs-enhance-review-title">Send the improved prompt?</b><span></span></div><button type="button" data-action="cancel" aria-label="Cancel - send nothing">×</button></div>
          <div class="zs-enhance-dialog-meta"></div>
          <label>Your original</label>
          <div class="zs-enhance-orig-box"></div>
          <label>Improved prompt (you can edit it)</label>
          <textarea spellcheck="true"></textarea>
          <div class="zs-enhance-dialog-actions"><button type="button" data-action="original">Send my original</button><button type="button" data-action="send" class="primary">Send improved prompt</button></div>
        </div>`;
        const ta = shade.querySelector("textarea");
        const meta = shade.querySelector(".zs-enhance-dialog-meta");
        const sub = shade.querySelector(".zs-enhance-dialog-head span");
        ta.value = String(result.text || "");
        sub.textContent = `${result.intent || "task"} · ${(result.added || []).join(" · ")}`;
        meta.textContent = `Nothing has been sent yet. Pick one: only that version goes to the chat. Closing this (Esc) sends nothing and keeps your text in the box.`;
        const origBox = shade.querySelector(".zs-enhance-orig-box");
        origBox.textContent = String(original || "");
        let done = false;
        const finish = (action) => {
          if (done) return;
          done = true;
          document.removeEventListener("keydown", onKey, true);
          shade.remove();
          resolve({ action, text: ta.value, originalText: String(result.text || ""), original });
        };
        const onKey = (e) => {
          if (e.key === "Escape") { e.preventDefault(); finish("cancel"); }
          if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); finish("send"); }
        };
        shade.addEventListener("click", (e) => {
          const action = e.target && e.target.dataset && e.target.dataset.action;
          if (action) finish(action);
          else if (e.target === shade) finish("cancel");
        });
        document.addEventListener("keydown", onKey, true);
        root.appendChild(shade);
        setTimeout(() => { try { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); } catch {} }, 0);
      });
    }

    // Left-hand Multi-Script popup showing the latest screen_capture. Fed from the
    // in-memory base64 (a data: URL always renders), so it works identically on
    // every provider and never touches the site's DOM. Only the most recent
    // capture is kept - a new one replaces the old.
    function showImages(images, toolName) {
      root.querySelectorAll(".zs-shot").forEach((e) => e.remove());
      const wrap = document.createElement("div");
      wrap.className = "zs-shot";
      const hdr = document.createElement("div");
      hdr.className = "zs-shot-hdr";
      const ttl = document.createElement("span");
      ttl.className = "zs-shot-ttl";
      ttl.textContent = `${toolName} · ${images.length} image${images.length > 1 ? "s" : ""}`;
      const close = document.createElement("button");
      close.className = "zs-shot-x";
      close.textContent = "✕";
      close.addEventListener("click", () => wrap.remove());
      hdr.appendChild(ttl);
      hdr.appendChild(close);
      wrap.appendChild(hdr);
      const body = document.createElement("div");
      body.className = "zs-shot-body";
      for (const img of images) {
        const el = document.createElement("img");
        el.className = "zs-shot-img";
        el.src = `data:${img.mimeType || "image/jpeg"};base64,${img.data}`;
        body.appendChild(el);
      }
      wrap.appendChild(body);
      root.appendChild(wrap);
    }

    build();
    return { coworkProbe,coworkAction,refreshCoworkSessions,memChanged: () => paintMem(), setStatus, staleExtensionAlert, setStarted, setStarting, showStop, markStopping, inputCover, toast, banner, reviewEnhancedPrompt, showImages, nudgeStart, updateStartGate, refreshSetup, getCustomPrompt, getUsageMode, getSkillDepth, getCustomMcpServers, buildSettingsBackup, applySettingsBackup, openMenu: (toSupport) => openMenuFn && openMenuFn(toSupport), ensureTerm: () => ensureTerm(), termPanel: () => termPanel, bridgeIdlePaint: () => bridgeIdlePaint() };
  })();

  // ── Live token + timer, shown ONLY on a tool call's chip detail. The
  //    elapsed-time ANCHOR is stored on the chip's DOM node (dataset) so the
  //    timer survives re-renders / conversation switches. ────────────────────
  const TOKEN_CHARS = 4;

  // 0-999 as-is; 1000+ compacted to 1k/1.1k/99k/1M... (one decimal below 10 of
  // the unit, none at/above it, trailing ".0" dropped) so a live token count
  // doesn't grow into a wide, jumpy number as the reply streams in.
  function formatCount(n) {
    if (n < 1000) return String(n);
    const units = [[1e9, "B"], [1e6, "M"], [1e3, "k"]];
    for (const [div, suf] of units) {
      if (n >= div) {
        const v = n / div;
        const rounded = v < 10 ? Math.round(v * 10) / 10 : Math.round(v);
        return rounded + suf;
      }
    }
    return String(n);
  }

  function setChipDetail(item, text) {
    const dt = item && item.querySelector(".zs-chip .zs-chip-dt");
    if (dt) dt.textContent = text;
  }

  // Update ONLY the chip's label text (no innerHTML rebuild), so live-correcting
  // the name mid-stream doesn't restart the spinner or wipe the token meter.
  function setChipLabel(item, text) {
    const tx = item && item.querySelector(".zs-chip .zs-chip-tx");
    if (tx && tx.textContent !== text) tx.textContent = text;
  }

  // Elapsed seconds since a per-item anchor (persisted on the node).
  function elapsedOn(item, key, fallbackStart) {
    if (!item) return 0;
    let t0 = Number(item.dataset[key] || 0);
    if (!t0) { t0 = fallbackStart || Date.now(); item.dataset[key] = String(t0); }
    return (Date.now() - t0) / 1000;
  }

  // Timestamp of the user's last REAL click on the site (trusted event, outside
  // Multi-Script's own UI). A genuine "regenerate ↻" is always such a click;
  // DeepSeek's post-stop phantom generations and stop-button re-mount flickers
  // never are - this is what tells them apart (seen live: two false regenResume
  // fired 8s/2s after a Stop with no user action, un-stopping the halted turn).
  let _userClickAt = 0;
  document.addEventListener("click", (e) => {
    if (e.isTrusted && !(e.target && e.target.closest && e.target.closest("#zs-root"))) {
      _userClickAt = Date.now();
    }
  }, true);

  let _prevHardGen = null, _prevSoftGen = null;
  setInterval(() => {
    const gen = P.isGenerating(); // growth-tolerant: used for the live token meter
    // Watchdog freshness clock. Growth-tolerant (not just the hard stop-button
    // signal): a SHORT command after a long reasoning phase shows its stop
    // square for only a frame or two - too briefly for this 200ms sampler.
    if (gen) A.lastGenAt = Date.now();
    // High-water mark of the newest turn id seen this session (virtualization-
    // safe). The auto-resume watchdog uses it to IGNORE a scrolled-back OLD turn:
    // on a virtualized list lastAssistant() is the last RENDERED turn, which when
    // scrolled up is old, and its injected-result row is off-screen/unrendered so
    // the "result below" guard can't see it. A numeric provider id (DeepSeek's
    // data-virtual-list-item-key) is monotonic per turn, so the max only grows at
    // the live bottom and a scrolled-back turn reads strictly below it.
    if (P.itemKey && P.lastAssistantId) {
      const nk = Number(P.lastAssistantId());
      if (Number.isFinite(nk) && (A.maxTurnId == null || nk > A.maxTurnId)) A.maxTurnId = nk;
    }
    // Slide the regenerate grace anchor while generation is still (intermittently)
    // active, so the chip stays "run" across gen-false blips right up to the moment
    // the watchdog re-owns the tool (see regenResume).
    if (A.resumeArmed && gen) A.resumeArmedAt = Date.now();
    const hardGen = A.started && P.isHardGenerating();

    // Regenerate-as-resume: after a manual stop (A.userStopped) the agent stays
    // dormant until fresh user intent. Typing a message or the native Continue
    // clears the latch, but clicking the site's "regenerate ↻" does not - and on
    // Qwen that control is unlabeled and indistinguishable from copy/like, so we
    // can't hook the button reliably. Detect the EFFECT instead: a brand-new
    // generation (gen false→true) while we are stopped and otherwise idle can only
    // come from a user action (there is no spontaneous generation). Treat it as
    // resume - clear the stop latch and drop the turn's stopped/no-resume markers
    // so the auto-resume watchdog can pick the regenerated reply's tool back up.
    // Providers with NO native "regenerate" control (e.g. ReidChat) can opt out
    // via hasRegenerate:false - for them a gen false→true blip while stopped is
    // only abort/caret churn, never a real regenerate, so honouring it would
    // spuriously clear the manual-stop latch and auto-resume against the user.
    // HARD edge only: the growth-tolerant `gen` blips false→true when the site
    // re-renders the HALTED turn after a stop (adding its "Stopped" marker grows
    // streamText, which counts as growth for 800ms) - that blip falsely cleared
    // the latch, repainted the stopped chip ✓ green and re-armed auto-resume. A
    // real regenerate always raises the site's stop control, so require it; on
    // DeepSeek (no stop control during reasoning) this merely delays the resume
    // to the answer phase, after which the watchdog acts anyway.
    // Tracker: a soft (growth-only) blip in the stopped-idle state - exactly the
    // false trigger the hard-edge gate above filters out. Log it so live tests
    // can SEE the old bug firing and being ignored.
    if (A.started && A.userStopped && !A.running && !A.injecting && !A.stopping &&
        gen && _prevSoftGen === false && !hardGen) {
      diag("regenBlip.ignored");
    }
    if (P.hasRegenerate !== false &&
        A.started && A.userStopped && !A.running && !A.injecting && !A.stopping &&
        hardGen && _prevHardGen === false) {
      // Gate on ACTUAL user intent: a real regenerate is always a trusted click
      // moments before the new generation, and never the Stop click itself.
      // Distinguish the two by ORDER, not a fixed delay: require the latest
      // trusted click to fall clearly AFTER the Stop (clickAfterStop). A native
      // stop click lands ~at A.stopAt, so it fails this and can't self-resume;
      // the extension's own "■ Stop" is inside #zs-root and never updates
      // _userClickAt at all, so only the later regenerate qualifies. This
      // replaces the old absolute `stopAge > 3000` grace, which also blocked a
      // user who regenerated quickly (~1.5s) after Stop - the real bug seen live.
      // DeepSeek's post-stop phantom generations carry no fresh trusted click,
      // so they still fail the gate.
      const clickAge = Date.now() - _userClickAt;
      const stopAge = Date.now() - (A.stopAt || 0);
      const clickAfterStop = _userClickAt - (A.stopAt || 0);
      if (clickAge < 2500 && clickAfterStop > 400) {
        A.userStopped = false;
        const it = P.lastAssistant();
        if (it) {
          delete it.dataset.zStopped; delete it.dataset.zResume;
          delete it.dataset.zResumeLen; delete it.dataset.zloop;
          forgetHalted(it);
          // Strip the OLD command's chip immediately. The regenerate reuses this
          // turn node, and without this the previous execute_luau chip (with its
          // spinner/settled state) lingers for ~200ms until the sweep repaints the
          // node - the visible "it keeps running the old call for a beat before
          // restarting" flash reported on Kimi. resetDecoration clears the chip and
          // every marker so the regenerated reply classifies fresh.
          resetDecoration(it);
          // Kimi (and other node-reusing sites) leave the OLD command text in the
          // reply DOM for ~2s after regenerate starts, before wiping it and
          // streaming the new reply. resetDecoration only removes OUR chip - the
          // sweep then re-derives a fresh "run" chip from that stale old command
          // (old token count and all) until the content is replaced: the "red
          // stopped chip turns into a grey spinner on the OLD call" flash reported
          // live. Capture the old text length so the sweep can tell the DOM still
          // holds the stale command and keep the coherent red "stopped" look until
          // Kimi actually replaces it (see the zRegenLen guard in classify).
          try {
            it.dataset.zRegenLen = String(P.classifyText(it, ".zs-chip").length);
            it.dataset.zRegenAt = String(Date.now());
          } catch {}
        }
        // Bridge the gap until the auto-resume watchdog (1s interval) re-owns the
        // tool: regenResume only CLEARS the stop latch, it does not start the loop
        // (the regenerated command hasn't finished streaming yet, so there's
        // nothing to dispatch). In that ~1s window A.running is still false and
        // Gemini's generation signal blips false between reasoning and command
        // settle, so the sweep painted the chip a premature ✓ "done" before the
        // real execution began. Arm a grace anchor the sweep honours as "live"; it
        // slides while generation blips (refreshed in the meter loop) and expires
        // shortly after generation truly stops, by which point the watchdog has
        // taken over (A.running) or the reply was plain text with no tool.
        A.resumeArmed = true;
        A.resumeArmedAt = Date.now();
        diag("regenResume", { clickAge, stopAge, clickAfterStop });
      } else {
        diag("regenEdge.ignored", { clickAge, stopAge, clickAfterStop });
      }
    }
    _prevHardGen = hardGen;
    _prevSoftGen = gen;
    // Our "■ Stop" button stays visible for the WHOLE active turn (generation,
    // reasoning, or a tool/wait running on the bridge). It is complete on its own
    // - stopLoop both halts our loop AND clicks the site's native stop - and the
    // site's native stop likewise halts our loop via onNativeStop, so either one
    // fully stops everything. Two stop buttons at once is fine.
    // The bare isHardGenerating() term is gated on a live Multi-Script session: on
    // a plain chat with no session, a user's own message makes the site generate,
    // and we must NOT briefly flash our Stop button over that.
    // Self-heal a stuck "Stopping…": if we flagged stopping but nothing is
    // actually busy anymore (the loop's finally never ran because the Stop landed
    // before a loop started, or a pending start was cancelled), release it so the
    // button doesn't freeze on "Stopping…". While the site is STILL streaming,
    // re-click its native stop (throttled) instead of releasing: the first click
    // sometimes gets swallowed by a re-render, and handing back a clickable
    // "■ Stop" the user has to press again is exactly the bounce we're killing.
    if (A.stopping && !A.running && !A.toolRunning) {
      if (A.started && P.isHardGenerating()) {
        // CRITICAL: only re-click the native stop if the reply has ACTUALLY kept
        // growing since the last stop click. On Gemini (and GLM) the stop button
        // WEDGES visible for up to ~10s after a successful stop, so the old
        // unconditional retry clicked a stop with NO live stream behind it -
        // and Gemini queues that stray abort against the conversation, then
        // KILLS THE NEXT reply the instant it starts ("Vous avez interrompu
        // cette réponse" on a message the user never stopped - validated live,
        // 2026-07: two stray stop.retry clicks after a ZS Stop made the next
        // two user turns die instantly; with no stray clicks the same flow
        // worked). A swallowed first click - the case this retry exists for -
        // always shows up as the stream STILL writing, i.e. growth past the
        // baseline captured at stop time (A.stopStreamLen, set in stopLoop /
        // onNativeStop and re-based after each retry so every retry needs
        // fresh growth of its own).
        const grown = (P.streamLen ? P.streamLen() : 0) > (A.stopStreamLen || 0) + 24;
        if (grown && Date.now() - (A.stopRetryAt || 0) > 800) {
          A.stopRetryAt = Date.now();
          A.stopStreamLen = P.streamLen ? P.streamLen() : 0;
          try { P.stopGeneration(); } catch {}
          diag("stop.retry");
        } else if (!grown && Date.now() - (A.stopAt || 0) > 2500) {
          // Wedged stop button on a dead stream (text frozen since the stop):
          // the site is effectively quiet - release "Stopping…" instead of
          // holding it for the whole wedge window.
          A.stopping = false;
          diag("stop.quiet", { wedged: true });
        }
      } else {
        A.stopping = false;
        diag("stop.quiet"); // drain over: site quiet, Stopping… released
      }
    }
    ui.showStop(A.running || A.toolRunning || A.stopping || (A.started && P.isHardGenerating()));

    // Tool is executing on the MCP → timer on its chip.
    if (A.toolRunning && A.toolItem) {
      const s = elapsedOn(A.toolItem, "zsToolT0", A.toolStart).toFixed(1);
      setChipDetail(A.toolItem, (A.toolArg ? A.toolArg + " · " : "") + `${s}s`);
      return;
    }
    // The site is streaming a tool call → token count + timer on its chip.
    if (gen) {
      const item = P.lastAssistant();
      const reply = item ? P.itemText(item) : ""; // non-thinking only
      const zphase = item && item.dataset.zphase;
      // Skip items already settled (done/err) - don't overwrite the finished chip.
      if (item && zphase !== "done" && zphase !== "err" && ZSParse.hasToolSignature(reply)) {
        // Live-correct the label as soon as the real name streams in.
        const name = ZSParse.toolNameFromText(reply);
        if (name && name !== "command") setChipLabel(item, name);
        const tokens = Math.floor(reply.length / TOKEN_CHARS);
        const s = Math.round(elapsedOn(item, "zsGenT0"));
        setChipDetail(item, `~${formatCount(tokens)} tokens · ${s}s`);
        return;
      }
    }
  }, 200);

  // ════════════════════════════════════════════════════════════════════════
  //  WIRING
  // ════════════════════════════════════════════════════════════════════════

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if(msg?.type==='ms-cowork-probe'){sendResponse(ui.coworkProbe(msg.includeBrief));return;}
    if(msg?.type==='ms-cowork-action'){ui.coworkAction(msg).then(sendResponse,error=>sendResponse({ok:false,error:String(error.message||error)}));return true;}
    if (msg && msg.type === "zs-status") {
      ui.setStatus({ connected: msg.connected, mcpAlive: msg.mcpAlive, studio: msg.studio, studioApp: msg.studioApp, studioProc: msg.studioProc, tools: msg.tools, servers: msg.servers, engines: msg.engines });
    }
    if (msg && msg.type === "zs-open-menu") {
      ui.openMenu(false); // from the popup's Settings button — opens at the top (Switch AI / custom prompt)
      sendResponse({ ok:true, provider:P.id, editorFound:!!P.getEditor() });
    }
    if (msg && msg.type === "zs-ping") sendResponse({ ok:true, provider:P.id, editorFound:!!P.getEditor() });
    // Live log frames from the worker. Routed straight into the panel, which
    // owns all rendering, so the worker stays a pure transport.
    if (msg && msg.type === "ms-log-push") {
      const termPanel = ui.termPanel();
      if (termPanel) termPanel.push(msg.lines);
      sendResponse({ ok: true });
    }
    // Auto-start progress from the worker (terminal launcher installed + bridge down).
    if (msg && msg.type === "bridge_host_event") {
      const t = ui.ensureTerm();
      if (t) t.hostEvent(msg);
      ui.bridgeIdlePaint();
      sendResponse({ ok: true });
    }
    if (msg && msg.type === "ms-log-cleared") {
      if (ui.termPanel()) ui.termPanel().cleared();
      sendResponse({ ok: true });
    }
    // A bridge restart invalidates every seq we have seen, so the panel drops its
    // cursor and re-reads the backlog. Without this it would keep requesting
    // `since=<stale high seq>` and the log would appear frozen.
    if (msg && msg.type === "ms-log-reset") {
      if (ui.termPanel()) ui.termPanel().reset();
      sendResponse({ ok: true });
    }
  });

  // Status poll. An orphaned content script (see bg / isContextInvalidated) gets
  // a failure object back whose `connected` is undefined, which setStatus would
  // read as "the bridge just dropped" and answer with the red "start the bridge"
  // banner - sending the user to fix a bridge that is perfectly healthy, with
  // the one thing that WOULD fix it (reload the page) never mentioned. Catch it
  // before setStatus, say the right thing, and stop polling: the context can
  // never come back, so every later tick would just repeat the same failure.
  let statusTimer = 0;
  function onStatus(s) {
    if (!s) return;
    if (s.kind === "stale-extension") {
      clearInterval(statusTimer);
      ui.staleExtensionAlert();
      diag("bridge.staleExtension", { via: "status", error: s.error });
      return;
    }
    ui.setStatus(s);
  }
  // Hydrate the persisted re-statement budget for this conversation up front, so
  // the first tool result after a reload already knows the real tally.
  loadSysCount();
  bg({ type: "status" }).then(onStatus);
  statusTimer = setInterval(() => bg({ type: "status" }).then(onStatus), 5000);

  // Session state is derived from the ACTUAL chat, but sites VIRTUALIZE their
  // message lists: the system-prompt turn is dropped from the DOM once it
  // scrolls out of the window. So we key "started" by conversation
  // (P.conversationKey()): once we have seen the marker for a key, we remember
  // it (persisted so it survives reloads). We never flip while busy.
  const startedSessions = new Set();
  let lastSyncPath = null;
  function rememberSession(path) {
    // A falsy key = a TRANSIENT conversation URL (e.g. Gemini's /app before an
    // id is assigned). Remembering it would mark every future fresh chat as
    // "already started" and kill the Start gate. The real key is remembered by
    // the next sync once the site assigns the conversation its id.
    if (!path) return;
    if (startedSessions.has(path)) return;
    startedSessions.add(path);
    try { if (memCtrl) memCtrl.bind(); } catch {}
    try { chrome.storage.local.set({ zsStartedSessions: [...startedSessions].slice(-300) }); } catch {}
  }
  // Load the persisted set once, then re-sync.
  try {
    chrome.storage.local.get(["zsStartedSessions","zsFailedStartups"], (r) => {
      if(Array.isArray(r?.zsFailedStartups))for(const key of r.zsFailedStartups)failedStartups.add(key);
      if (r && Array.isArray(r.zsStartedSessions)) {
        for (const p of r.zsStartedSessions) startedSessions.add(p);
        syncSessionState();
      }
    });
  } catch {}
  // A conversation IS a Multi-Script session if any rendered turn carries a
  // telltale artefact: the system-prompt marker, an injected tool-result /
  // system-note turn, or a Multi-Script command an assistant wrote. Works even
  // after a full cold start and regardless of scroll position.
  function domHasZsSignal() {
    for (const it of P.allItems()) {
      const txt = it.textContent || "";
      if (ZS.hasSysMarker(txt)) return true;
      if (/(^|\n)\s*Output of '[^']+':/.test(txt) || txt.includes("(System note:")) return true;
      // Deliberately NO bare command-shape test here. An assistant turn that
      // merely CONTAINS {"command":...} / ###LUA### is NOT proof of a session:
      // in a plain, never-started chat the model can simply EXPLAIN the format
      // (docs, examples, the user pasting our README) - that false positive
      // flipped A.started on, which armed the auto-resume watchdog, EXECUTED
      // the quoted JSON as a real command and injected its result into a chat
      // that had no agent at all (user-reported). A command only counts as a
      // session signal once it was actually RUN - and an executed command is
      // always followed by our injected "Output of '...'" feedback turn, which
      // the test above already catches. Virtualization (the marker turns
      // scrolling out of the DOM) is covered by the persisted per-conversation
      // key set (startedSessions / zsStartedSessions in rememberSession), not
      // by this heuristic.
    }
    return false;
  }
  function syncSessionState() {
    if (memCtrl) {
      const now = memOn();
      if (A.memSeen !== now) { const first = A.memSeen === undefined; A.memSeen = now; if (!first) memSyncTools(); }
    }
    // While a bootstrap runs, track its conversation. The bootstrap chat gets a
    // real id only AFTER the prompt lands (fresh "/app" → "/app/<id>"), so we pin
    // the id the first time the chat has content. A change to a DIFFERENT, EMPTY
    // chat means the user opened a new conversation → abort: bump the generation
    // (the in-flight startSession bails at its next checkpoint) and clear state so
    // the new chat shows its own status instead of a stale "Starting…".
    if (A.starting) {
      const key = P.conversationKey();
      if (A.startingKey == null) {
        if (key && !P.chatIsEmpty()) A.startingKey = key; // pin the stable id
      } else if (key !== A.startingKey && P.chatIsEmpty()) {
        A.startGen++;
        A.starting = false;
        A.startingKey = null;
        P.setInputLock(false);
        ui.setStarting(false);
        // CRITICAL: startSession's own finally is gated on `alive()` (this abandon
        // just invalidated it via startGen++), so it will NEVER run and never
        // lift the "Agent is working…" cover. Without this line the cover was
        // stuck forever on the fresh chat whenever the user opened a new,
        // empty conversation WHILE the bootstrap's tool call (list_commands) was
        // still in flight - validated live 2026-07 on Cloudflare AI Playground.
        ui.inputCover(false);
      }
    }
    // Same idea for a RUNNING loop: if the user opens a NEW, empty conversation
    // via the SITE's own new-chat (not Multi-Script's button), the loop is bound to
    // a chat the user left, so abandon it. Otherwise A.running keeps this function
    // early-returning below and the stale "Agent active" / Stop button lingers on
    // the fresh chat instead of "Start Roblox agent". The "/app" → "/app/<id>" id
    // assignment of the SAME chat is not a move (loopKey is pinned only once the
    // chat has both an id and content), so a normal session is never disturbed.
    if (A.running) {
      const key = P.conversationKey();
      if (A.loopKey == null) {
        if (key && !P.chatIsEmpty()) A.loopKey = key; // pin the loop's conversation
      } else if (key !== A.loopKey && P.chatIsEmpty()) {
        diag("loop.abandonedNewChat", { from: A.loopKey, to: key });
        A.stop = true;       // the loop breaks at its next checkpoint; its finally
        A.loopKey = null;    // resets A.running / cover / lock, then state recomputes
      }
    }
    if (A.starting || A.injecting || A.running) return;
    const path = P.conversationKey();
    if(failedStartups.has(bootstrapClaimKey())){if(A.started){A.started=false;ui.setStarted(false);}return;}
    const markerInDom = domHasZsSignal();
    if (markerInDom) rememberSession(path);
    let has;
    if (path && path === lastSyncPath) {
      // SAME, REAL conversation: never downgrade a known-started session just
      // because virtualization scrolled the marker out of the DOM. "started" is
      // sticky until the key actually changes (a different conversation).
      // NOTE: a falsy key ("" = a transient/fresh chat with no id yet) is NEVER
      // sticky - every fresh chat shares "", so a brief transient sweep during
      // navigation would otherwise PIN lastSyncPath="" with has=true and then keep
      // "Agent active" forever on the next empty chat (it would never recompute).
      has = A.started || markerInDom || (!!path && startedSessions.has(path));
    } else {
      // Different conversation → recompute from scratch.
      has = markerInDom || (!!path && startedSessions.has(path));
      lastSyncPath = path;
    }
    const failure=has&&((P.responseError&&P.responseError())||(typeof MSStudio!=="undefined"&&MSStudio.nativeResponseError(P.lastAssistant())));
    if(failure&&(!A.responseFailure||A.responseFailure.chat!==path||A.responseFailure.text!==failure.text)){
      A.responseFailure={chat:path,base:Math.max(0,P.assistantCount()-1),text:failure.text};A.taskOutcome='provider-failed';A.lastSendOk=false;A.userStopped=true;
      coworkQueue?.pause("Provider response failed. Use its Retry before resuming.");ui.updateStartGate();
    }
    if (has !== A.started) {
      A.started = has;
      ui.setStarted(has);
    }
  }

  // Schedule a debounced sweep. requestAnimationFrame is PAUSED in a background
  // tab, so when hidden we fall back to a timer (throttled, but it runs).
  let sweepScheduled = false;
  let lastSweepAt = 0;
  let fullSweepDue = true;
  function scheduleSweep() {
    if (sweepScheduled) return;
    sweepScheduled = true;
    const run = () => {
      sweepScheduled = false;
      syncSessionState();
      P.enforceComposer();  // keep the composer in the provider's required modes
      ui.updateStartGate(); // block the input until a session is started
      const full = fullSweepDue; fullSweepDue = false;
      decorate.sweep(full);
    };
    // Streaming makes the page mutate on every token. Sweeping the whole conversation that often made the site lag,
    // so sweeps are spaced at least 200 ms apart (camouflage still lands well within a blink).
    const wait = Math.max(0, 200 - (Date.now() - lastSweepAt));
    const go = () => { lastSweepAt = Date.now(); run(); };
    if (document.hidden) setTimeout(go, 100);
    else if (wait > 0) setTimeout(() => requestAnimationFrame(go), wait);
    else requestAnimationFrame(go);
  }
  // Synchronous pre-hide: MutationObserver callbacks run as a microtask BEFORE
  // the browser paints, but the debounced sweep above waits one extra rAF -
  // long enough for a freshly-sent system-prompt/injected-feedback turn's raw
  // text to paint for a single frame before decorate.sweep() builds its chip
  // and hides it (seen live on DeepSeek: "Starting Up" flashed the raw prompt
  // for an instant). Do the cheap whole-item hide test right here, synchronously,
  // so the class lands before that first paint; the full sweep still runs after
  // to build the actual chip.
  function preHideWholeItems() {
    const items = P.recentItems&&!(A.injectHideUntil&&Date.now()<A.injectHideUntil)?P.recentItems(4):P.allItems();
    // Optimistic pre-hide of a freshly injected result turn (armed in
    // submitAndGetBase). The text-based match below can only fire once the
    // "Output of '…'" caption has rendered, but the turn's NODE appears first
    // (with its attached image) and the caption fills a tick later - so the raw
    // output would flash until a post-send sweep nudge. We know the newest user
    // turn in this window is ours: hide it on sight (blank, no raw text), and let
    // the normal sweep swap in the real "· result" chip when the caption lands.
    if (A.injectHideUntil && Date.now() < A.injectHideUntil) {
      const users = items.filter((it) => P.isUserItem(it));
      const last = users[users.length - 1];
      if (last && !last.classList.contains("zs-hidden") &&
          users.length > (A.injectPreUser || 0)) {
        last.classList.add("zs-hidden");
        A.injectHideUntil = 0; // one-shot: this turn is now masked
        diag("result.prehide", { users: users.length });
      }
    }
    // Only the newest turns can be a brand-new system/result turn; the full sweep covers older ones. Reading the text
    // of every turn on every mutation is what made long chats lag.
    for (const item of items.slice(-4)) {
      if (item.classList.contains("zs-hidden")) continue;
      const txt = P.classifyText(item, ".zs-chip");
      if (ZS.hasSysMarker(txt) ||
          (P.isUserItem(item) && ZSParse.isInjectedFeedback(txt))) {
        item.classList.add("zs-hidden");
      }
    }
  }
  let preHideLast = 0, preHideTimer = 0;
  const mo = new MutationObserver(records => {
    // Our bar/monitor/chip text is not provider output. Watching our own paint
    // caused fresh sweeps to repaint the monitor, feeding another observation.
    // Native answer edits and remounts remain observable, including hidden source.
    if(records.length&&records.every(r=>{const e=r.target.nodeType===1?r.target:r.target.parentElement;return !!e?.closest('#zs-root,#zs-bar,#zs-input-cover,.zs-chip');}))return;
    // At most one pre-hide check per 50 ms (it runs on every token while a reply streams).
    const now = performance.now();
    if (now - preHideLast >= 50) { preHideLast = now; preHideWholeItems(); }
    else if (!preHideTimer) preHideTimer = setTimeout(() => { preHideTimer = 0; preHideLast = performance.now(); preHideWholeItems(); }, 50);
    scheduleSweep();
  });
  mo.observe(document.documentElement, { childList: true, subtree: true });
  // Belt-and-braces: a low-frequency sweep regardless of tab visibility or
  // mutation timing, so camouflage always converges.
  setInterval(() => { fullSweepDue = true; scheduleSweep(); }, 1500);
  // When the user returns to the tab, immediately refresh camouflage/state.
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { fullSweepDue = true; scheduleSweep(); } });

  syncSessionState();

  // ── Prompt enhancer: hold the send, ask, then send exactly ONE message ─────
  // Providers call onUserMessage from a capture-phase keydown/click listener on
  // `document`, BEFORE the site sees the event. A window-level capture listener
  // (which runs first) remembers that event, so onUserMessage can cancel it. The
  // user's original is therefore NOT sent: the review dialog opens first, and
  // only the chosen version (enhanced, edited, or original) is typed + sent.
  let sendEvt = null;
  function studioSettingsFingerprint() {
    return JSON.stringify([executionEffort,autonomyLevel,criticSettings,activeCustomSkills(),blenderWorkspaceInstructions()]);
  }
  const noteSendEvent = (e) => {
    sendEvt = e;
    setTimeout(() => { if (sendEvt === e) sendEvt = null; }, 0);
  };
  window.addEventListener("keydown", noteSendEvent, true);
  window.addEventListener("click", noteSendEvent, true);

  function enhanceFacts() {
    return {
      engines: activeEngineIds(),
      enginesChecked: true,
      studioIds: (A.studios || []).map((s) => s.id).filter(Boolean),
      toolCount: (A.toolList || []).length,
      toolNames: (A.toolList || []).map((t) => typeof t === "string" ? t : (t && t.name)).filter(Boolean),
    };
  }
  function swallowSendEvent(ev) {
    try { ev.preventDefault(); } catch {}
    try { ev.stopImmediatePropagation(); } catch {}
    try { ev.stopPropagation(); } catch {}
  }
  // Returns true when the send was taken over (the caller must not continue).
  function gateEnhancedSend(userText, event) {
    const ev = event || sendEvt;
    if (A.enhanceBusy) {            // a review is already open: never let a 2nd send slip past it
      if (ev && ev.cancelable) swallowSendEvent(ev);
      return true;
    }
    const es = getEnhanceSettings();
    const source = String(userText || "");
    if (!source.trim() || !ev || !ev.cancelable || ev.defaultPrevented) return false;
    if (ZSParse.isInjectedFeedback(source)) return false; // explicit retry of a prepared tool result
    let r;
    try { r = es.mode === "off" ? {text:source, enhanced:false, intent:"active studio settings", added:0} : ZSEnhance.enhance(source, enhanceFacts(), es); } catch (e) {
      diag("enhance.error", { error: String((e && e.message) || e) });
      return false;                 // optional layer: never block the user's own send
    }
    if (!r || !r.enhanced || !r.text) {

      r={text:source,enhanced:false,intent:"Agent instructions",added:0};
    }
    swallowSendEvent(ev);
    A.responseFailure=null;A.taskOutcome="working";
    A.enhanceBusy = true;
    runEnhancedSend(source, r)
      .catch((e) => {
        diag("enhance.error", { error: String((e && e.message) || e) });
        ui.toast("Prompt enhancer failed - your message is still in the box, press Send again");
      })
      .finally(() => { A.enhanceBusy = false; });
    return true;
  }
  const loadedResourceCache=new Map();
  async function preloadTaskResources(source) {
    if(typeof MSStudio==='undefined'||typeof MSStudio.resourcePlan!=='function')return '';
    const plan=MSStudio.resourcePlan(source,executionEffort,{engines:A.software||A.chatOnly?['workspace']:connectedEngineIds()});
    if(!plan)return '';
    const resourceTool=plan.visual?'ms_roblox_omni':'ms_obsidian';
    const available=A.toolList.some(t=>bareToolName(t.name)===resourceTool)&&!isBlockedTool(resourceTool)&&(!A.software||softwareAllowsTool(resourceTool));
    const root=A.software?softwareSettings.root:((A.studios||[])[0]?.placeId||(A.studios||[])[0]?.place_id||'');
    let hash=2166136261;for(const char of String(root)){hash^=char.charCodeAt(0);hash=Math.imul(hash,16777619);}
    const project=root?'project-'+(hash>>>0).toString(16):'default';
    const key=JSON.stringify([P.conversationKey(),studioSettingsFingerprint(),root,source]);
    const cached=loadedResourceCache.get(key);if(cached&&Date.now()-cached.at<30000)return cached.text;
    let data={available:false,reason:'The current filtered catalogue does not advertise '+resourceTool+'. Do not claim access; use advertised discovery if needed.'};
    if(available){
      let timer;
      try{
        const result=await Promise.race([bg({type:'call_tool',name:resourceTool,arguments:{action:'context',query:plan.query,project},timeout:2000}),new Promise(resolve=>{timer=setTimeout(()=>resolve(null),1800);})]);
        data=result?.ok?JSON.parse(result.text||result.result?.text||'{}'):{toolAdvertised:true,preloadComplete:false,reason:result?.error||'Optional preload timed out; retrieve relevant resources on demand. The original task is unchanged.',next:{command:resourceTool,params:{action:plan.visual?'references':'search',query:plan.query}}};
      }catch(error){data={toolAdvertised:true,preloadComplete:false,reason:String(error.message||error).slice(0,240)};}finally{clearTimeout(timer);}
    }
    const text=MSStudio.resourcePrompt(plan,data,typeof MSForge!=='undefined'?MSForge:null);
    if(loadedResourceCache.size>=8)loadedResourceCache.delete(loadedResourceCache.keys().next().value);
    loadedResourceCache.set(key,{at:Date.now(),text});return text;
  }
  async function runEnhancedSend(source, r) {
    // Keep a newer Stop or chat navigation binding while the review is open.
    // A stale halt from an earlier turn must not cancel this new user message.
    const reviewStopAt = A.stopAt || 0;
    const reviewChatKey = P.conversationKey();
    const es = getEnhanceSettings();
    let text = r.text, picked = "enhanced";
    if (r.enhanced && es.mode !== "off" && es.preview && ui.reviewEnhancedPrompt) {
      const choice = await ui.reviewEnhancedPrompt(source, r);
      if (!choice || choice.action === "cancel") {
        diag("enhance.review", { action: "cancel", intent: r.intent });
        ui.toast("Not sent - your message is still in the box");
        return;
      }
      if (choice.action === "original") { text = source; picked = "original"; }
      else if (choice.text && choice.text.trim()) text = choice.text.trim();
      diag("enhance.review", { action: picked, edited: picked === "enhanced" && text !== r.text });
    }
    if ((A.stopAt || 0) !== reviewStopAt || P.conversationKey() !== reviewChatKey) {
      ui.toast("Not sent - the task was stopped or the conversation changed during review");
      return;
    }
    if (A.running || A.starting) {
      ui.toast("Not sent - another task started. Your draft is still in the composer");
      return;
    }
    // submitAndGetBase runs BEFORE agentLoop (which normally resets stop).
    // Without this reset its retry loop makes zero attempts after an idle Stop.
    A.stop = false;
    A.stopping = false;
    A.userStopped = false;
    A.lastUserText = source; A.memLastUser = source;beginTaskProgress(source);
    const draftBeforeResume=P.editorText?P.editorText():null;
    await bg({type:"ms_provider_pacing",action:"resume",provider:P.id,owner:"user-submission"});
    if((A.stopAt||0)!==reviewStopAt||P.conversationKey()!==reviewChatKey){ui.toast("Not sent - the task was stopped or the conversation changed.");return;}
    if(draftBeforeResume!==null&&P.editorText()!==draftBeforeResume){ui.toast("Not sent - your newer draft is still in the composer.");return;}
    const settingsKey=studioSettingsFingerprint();
    bumpSys("users");
    diag("enhance.send", { picked, intent: r.intent, added: r.added, chars: text.length });
    ui.toast(!r.enhanced ? "Sending your prompt with Agent instructions" : picked === "enhanced" ? `Sending the enhanced prompt (${r.intent})` : "Sending your original prompt");
    // The user's actual task leads every enhanced/Ultra send. A rewrite may
    // add clarification below it, but cannot replace it with setup instructions.
    if(!String(text).startsWith(source))text=source+'\n\n[Task clarification — original request above remains binding]\n'+String(text);
    const resources=await preloadTaskResources(source);
    if(A.running||A.starting||A.userStopped||(A.stopAt||0)!==reviewStopAt||P.conversationKey()!==reviewChatKey||settingsKey!==studioSettingsFingerprint()||(draftBeforeResume!==null&&P.editorText()!==draftBeforeResume)){
      ui.toast('Not sent — the draft, task, conversation or settings changed while loading references.');return;
    }
    const addon=taskPromptAddon(source); if(addon) text += "\n\n" + addon;
    if(resources){const budget=Number(P.sendCharBudget)||50000;text += text.length+resources.length+2<=budget?'\n\n'+resources:'\n\nBundled resources: ms_roblox_omni (status, packages, references, preview, recipe, modules); ms_obsidian (context, search, read). Retrieve relevant items on demand; optional preload was omitted to preserve your complete request within the composer budget.';}
    if (studioSettingsDirty) text += "\n\n" + activeStudioInstructions(false);
    const base = await submitAndGetBase(text, undefined, { visible: true, settingsKey });
    if (!A.lastSendOk) return;             // submitAndGetBase already explained why
    if(settingsKey===studioSettingsFingerprint()) studioSettingsDirty = false;
    if (!A.running && !A.userStopped) agentLoop(base);
  }

  // User-send interception: the provider wires the site's composer events to
  // these callbacks.
  P.installSendHooks({
    isBlocked: () => A.injecting || A.running || A.starting,
    isStarted: () => A.started,
    onBlockedAttempt: () => ui.nudgeStart(),
    onUserMessage: (base, event) => {
      // A fresh user message = fresh intent: clear any previous manual stop so
      // the loop is allowed to run again.
      A.userStopped = false;A.responseFailure=null;A.taskOutcome="working";
      // Prompt enhancer: hold this send and let the user pick enhanced/original.
      try {
        let held = ""; try { held = (P.editorText && P.editorText()) || ""; } catch {}
        if (gateEnhancedSend(held,event)) return;
      } catch (e) { diag("enhance.error", { error: String((e && e.message) || e) }); }
      bg({type:"ms_provider_pacing",action:"resume",provider:P.id,owner:"native-user-submission"});
      A.lastSendOk = true; A.sendUnconfirmed = false; // a new native user submission resumes the paused send
      noteNotionPrompt();
      bumpSys("users");
      captureSendToken(); // identity of the assistant turn before this reply
      // Capture the user's OWN wording for the enhancer. This hook runs from the
      // provider's keydown/click interception BEFORE the site's framework clears
      // the composer, so editorText() still holds exactly what the user typed.
      // Read it once, here, and hand it to the loop - the loop cannot ask later
      // because the editor is empty by then.
      let userText = "";
      try { userText = (P.editorText && P.editorText()) || ""; } catch {}
      if (userText.trim() && !ZSParse.isInjectedFeedback(userText)) { A.lastUserText = userText.trim(); A.memLastUser = userText.trim();if(!taskLedger||!userText.includes('[MULTI-SCRIPT TASK CHECKLIST]')||!userText.includes(taskLedger.id))beginTaskProgress(userText.trim()); }
        // A Stop clicked during this 300ms window sets A.userStopped → honor it and
      // do NOT start the loop (otherwise the stop is silently ignored and the
      // freshly-started loop strands the "Stopping…" flag).
      setTimeout(() => { if (!A.running && !A.userStopped) agentLoop(base); }, 300);
    },
    onNativeStop: () => {
      // A click on the site's own stop = a deliberate manual stop → suppress
      // auto-resume.
      A.userStopped = true;
      A.stop = true;
      A.resumeArmed = false; // a stop overrides any pending regenerate grace
      A.stopAt = Date.now(); // grace anchor for the regenerate-as-resume gates
      // Same growth baseline as stopLoop: the stop-retry self-heal must only
      // re-click if the stream keeps writing past this point (see stop.retry).
      A.stopStreamLen = P.streamLen ? P.streamLen() : 0;
      // If our loop is live, mirror the same "Stopping…" feedback as our own
      // Stop button so the bar reflects the wind-down instead of flickering.
      if (A.running && !A.stopping) { A.stopping = true; ui.markStopping(); }
      markStoppedTurn();
      diag("nativeStop");
    },
    onNativeContinue: () => {
      // The site's "Continue" button = a clear intent to RESUME after a stop/
      // truncation. Clear the manual-stop latch so auto-resume can pick the
      // (resumed) turn's tool call back up cleanly.
      A.userStopped = false;
      A.stop = false;
      const it = P.lastAssistant();   // a real resume → drop the stopped marker
      if (it) { delete it.dataset.zStopped; forgetHalted(it); }
      diag("nativeContinue");
    },
  });

  // Auto-resume watchdog - the safety net that keeps the agentic loop alive when
  // a tool call finished AFTER the loop finalized early (huge multi_edit, tab
  // returning from background). It must NEVER fire on a tool call merely
  // PRESENT in the DOM without a fresh live generation. Guards:
  //   • A.userStopped - the user halted; never relaunch against their intent.
  //   • lastGenAt recency - only resume a turn from a generation in the last
  //     few seconds; a turn rendered by load/scroll has no recent generation.
  //   • turnHalted - the turn itself carries the site's "stopped" marker.
  // Each turn is still resumed at most once (zResume marker).
  // Freshness window for the resume watchdog. Widened from 8s to 3 minutes
  // (2026-08) because 8s was the ONLY thing standing between an orphaned command
  // and its execution, and it was firing on legitimate work: a long generation
  // (a Qwen reply seen live writing for 400s+) makes the loop finalize early, the
  // generation then genuinely ends, lastGenAt goes stale within 8s and the
  // completed command is stranded forever with a grey "not run" - the user's
  // whole point being that they wanted it to RUN. This is safe because every
  // guard below is independent of lastGenAt and covers the cases this window was
  // nominally protecting: bootBaselineId (a reload-restored generation),
  // maxTurnId (a scrolled-back old turn), the result-below settled-history test
  // (survives a reload, unlike the executed map), the `executed` map, the
  // zResume dedupe and A.userStopped. As the `executed` map's own comment puts
  // it, re-execution is idempotent regardless of any lastGenAt misfire - "the
  // hard part (is this a live turn?) can be wrong without harm". The window is
  // kept, rather than removed, so a tab left open for hours still never
  // spontaneously fires a command on some later unrelated DOM churn.
  const RESUME_FRESH_MS = 180000;
  setInterval(() => {
    if (!A.started || A.running || A.starting || A.injecting || A.lastSendOk === false) return;
    if (pageHidden()) return;                         // AI tab not foreground → don't parse/exec off-screen (agentLoop gates too)
    if (A.userStopped) return;                          // user halted → never relaunch
    if (P.isGenerating()) return;
    if (Date.now() - A.lastGenAt > RESUME_FRESH_MS) return; // not a fresh live turn
    const item = P.lastAssistant();
    if (!item || item.dataset.zloop) return;
    // Never resume the turn that already existed when this session started - it is
    // a reload-restored generation, not a reply to one of our sends (see
    // A.bootBaselineId). Guards the "execute_luau leaked into the new chat" bug.
    if (A.bootBaselineId && P.lastAssistantId && P.lastAssistantId() === A.bootBaselineId) return;
    if (P.turnHalted(item)) return;                     // this turn was stopped → leave it
    // Scrolled-back OLD turn guard (virtualization). lastAssistant() is the last
    // RENDERED turn; scrolling up makes it an old command whose id is below the
    // session's high-water mark. Its result row may be off-screen (unrendered), so
    // the result-below guard alone can miss it - this catches it directly. Only
    // applies when the provider exposes a numeric monotonic id (DeepSeek).
    const curId = P.itemKey ? Number(P.itemKey(item)) : NaN;
    if (Number.isFinite(curId) && A.maxTurnId != null && curId < A.maxTurnId) {
      // Log once per distinct turn, not every 1s tick while the user stays up.
      if (A._skipOldId !== curId) { A._skipOldId = curId; diag("resume.skipOld", { curId, maxTurnId: A.maxTurnId }); }
      return;
    }
    // Settled-history guard (survives a page reload, unlike the executed map).
    // A genuine resume target is a command whose tool NEVER produced a result;
    // it has NO injected-feedback turn after it. Every ALREADY-EXECUTED command
    // is followed by its injected result. On a virtualized list, scrolling up
    // makes lastAssistant() an OLD command turn AND flickers isGenerating() true
    // (sampleStream resets on the node change), refreshing lastGenAt - so the
    // freshness guard alone doesn't stop it, and after a reload the executed map
    // is empty. Keying off the result-below turn robustly separates the in-flight
    // command from settled history: a scrolled-back tool with its result already
    // present is never re-fired. (Confirmed live: same-conv reload + scroll up
    // re-executed a historical command.)
    const all = P.allItems();
    const after = all[all.indexOf(item) + 1];
    if (after && P.isUserItem(after) &&
        ZSParse.isInjectedFeedback(P.classifyText(after, ".zs-chip"))) return;
    const txt = P.itemText(item);
    if (!ZSParse.hasToolSignature(txt)) return;
    // Node-independent dedupe: this turn's command was already dispatched (by the
    // loop or a prior resume). The dataset guards below are wiped when the site
    // recreates the node on scroll, so without this off-DOM check the watchdog
    // re-runs a historical tool with no live generation. See the `executed` map.
    if (isRememberedExecuted(item, txt)) return;
    // Resume only when a COMPLETE, parseable command is present - and re-attempt
    // if the turn has GROWN since our last try.
    if (!ZSParse.parseToolCalls(txt).length) return;
    const len = txt.length;
    if (item.dataset.zResume && Number(item.dataset.zResumeLen || 0) >= len) return;
    item.dataset.zResume = "1";
    item.dataset.zResumeLen = String(len);
    rememberExecuted(item);
    diag("autoResume", { len });
    // The reply turn is ALREADY present - act on it immediately. Null token makes
    // the identity-based newReply test unconditionally true (any current id != null).
    A.sendToken = null;
    agentLoop(P.assistantCount() - 1);
  }, 1000);

  // ── System-prompt re-injection fallback ───────────────────────────────────
  // The piggyback path (withSysResend) is free but needs a tool result to ride
  // on, and the failure this feature exists for - the model forgetting it can
  // run commands at all - is precisely the state where no tool results are being
  // produced. So when a re-statement has been owed for a while and nothing has
  // carried it, send it as its own turn: masked exactly like the bootstrap (the
  // SYS_MARKER makes the camouflage sweep hide the whole item), so the user sees
  // nothing but ChatGPT's short acknowledgement.
  //
  // This costs one message from the site's quota, which is why it is a fallback
  // and not the primary path. Deliberately conservative about WHEN it may fire:
  // never mid-generation, never while the loop or bootstrap owns the composer,
  // and never while the user has text sitting in the composer (we would wipe
  // what they were typing).
  const SYS_FALLBACK_IDLE_MS = 20000;
  setInterval(async () => {
    if (!sysResendDue()) return;
    if (!A.started || A.running || A.starting || A.injecting || A.lastSendOk === false) return;
    if (pageHidden() || A.userStopped) return;
    if (P.isGenerating()) return;
    // The user is composing - their draft owns the editor, leave it alone.
    try { if ((P.editorText() || "").trim() !== "") return; } catch { return; }
    // Give the cheap path a fair chance first: only step in once the turn has
    // been settled and quiet for a while with no tool result to ride on.
    if (Date.now() - A.lastGenAt < SYS_FALLBACK_IDLE_MS) return;
    const spent = sinceLastSys();
    resetSysCount();
    A.sysResendAt = Date.now();
    diag("sys.resend", { via: "ownTurn", ...spent });
    try {
      const base = await submitAndGetBase(systemPrompt(), undefined, {settingsKey:studioSettingsFingerprint()});
      await waitForResponse(base);
    } catch (e) {
      diag("sys.resendFailed", { err: String(e && e.message || e) });
    }
  }, 5000);

  // Memory switched ON inside a chat that already started: tell the model once.
  // Rides the next tool result (free); if none flows, send it as a masked turn.
  setInterval(async () => {
    if (!A.memAnnounce || !memOn()) return;
    if (!A.started || A.running || A.starting || A.injecting || A.lastSendOk === false) return;
    if (pageHidden() || A.userStopped || P.isGenerating()) return;
    try { if ((P.editorText() || "").trim() !== "") return; } catch { return; }
    if (Date.now() - A.lastGenAt < 6000) return;
    A.memAnnounce = false;
    try {
      await memCtrl.refresh("");
      const base = await submitAndGetBase(ZS.RESEND_MARKER + "\n" + ZM.RESEND_NOTE + "\n" + memCtrl.promptBlock());
      await waitForResponse(base);
    } catch (e) {
      diag("mem.announceFailed", { err: String(e && e.message || e) });
    }
  }, 4000);

  log(`Multi-Script content script ready (provider: ${P.id})`);
})();
