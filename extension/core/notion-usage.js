// SPDX-License-Identifier: GPL-3.0-or-later
// core/notion-usage.js - Notion AI model catalog + trial/credit ESTIMATOR.
//
// HONESTY FIRST. Notion publishes no per-model credit price and no API for a
// trial's remaining allowance, so nothing here is a measurement of Notion's
// billing. It is a calculator with three inputs the user can verify:
//   1. what Notion shows on screen (credits left / trial days left) - read from
//      the page when it is visible, or typed in by the user;
//   2. the prompts THIS extension actually sent (counted locally);
//   3. relative model weights (Opus costs more than Haiku) that the estimator
//      LEARNS from the user's own credit readings instead of trusting a table.
// Every figure is labelled "rough" in the UI and carries a confidence level.
//
// PURE: no DOM, no chrome.*, no timers. State in, state out, so the whole thing
// is unit-testable in plain node (tests/test_notion_usage.js).
const ZSNotionUsage = (() => {
  "use strict";
  const DAY = 86400000;
  const MAX_PROMPTS = 600, MAX_OBS = 60;

  // Relative weight of one agent run, in "units". Defaults only - the estimator
  // rescales them from observed credit drops (see observeCredits).
  const MODEL_CLASSES = [
    { id: "opus", re: /opus/i, weight: 5, vendor: "Anthropic" },
    { id: "sonnet", re: /sonnet/i, weight: 2.5, vendor: "Anthropic" },
    { id: "haiku", re: /haiku/i, weight: 0.7, vendor: "Anthropic" },
    { id: "claude", re: /claude/i, weight: 3, vendor: "Anthropic" },
    { id: "gpt-mini", re: /(gpt|o\d).*(mini|nano)|(mini|nano).*(gpt)/i, weight: 0.8, vendor: "OpenAI" },
    { id: "gpt", re: /gpt|\bo[134]\b|codex|sol\b|luna\b/i, weight: 3, vendor: "OpenAI" },
    { id: "gemini-flash", re: /gemini.*(flash|lite)/i, weight: 0.8, vendor: "Google" },
    { id: "gemini", re: /gemini/i, weight: 2.5, vendor: "Google" },
    { id: "kimi", re: /kimi/i, weight: 1.2, vendor: "Moonshot" },
    { id: "deepseek", re: /deepseek/i, weight: 0.8, vendor: "DeepSeek" },
    { id: "auto", re: /\bauto\b/i, weight: 1.5, vendor: "Notion" },
  ];
  const EFFORTS = { low: 0.6, medium: 1, high: 1.6, xhigh: 2.4, max: 3 };
  const EFFORT_ORDER = ["low", "medium", "high", "xhigh", "max"];

  const num = (v, d = null) => { const n = typeof v === "string" ? parseFloat(v.replace(/[,\s]/g, "")) : v; return Number.isFinite(n) ? n : d; };
  const clamp = (n, a, b) => Math.min(b, Math.max(a, n));

  function normEffort(text) {
    const t = String(text || "").toLowerCase().replace(/[^a-z ]/g, " ").replace(/\s+/g, " ").trim();
    if (!t) return null;
    if (/\b(x ?high|extra high|ultra|extended)\b/.test(t)) return "xhigh";
    if (/\bmax(imum)?\b/.test(t)) return "max";
    if (/\bhigh\b/.test(t)) return "high";
    if (/\b(med|medium|standard|balanced|normal)\b/.test(t)) return "medium";
    if (/\b(low|minimal|fast|quick|light)\b/.test(t)) return "low";
    return null;
  }
  function classify(name) {
    const n = String(name || "");
    for (const c of MODEL_CLASSES) if (c.re.test(n)) return { id: c.id, weight: c.weight, vendor: c.vendor };
    return { id: "other", weight: 2, vendor: "" };
  }
  const effortFactor = (e) => EFFORTS[normEffort(e) || ""] || 1;
  const promptWeight = (model, effort) => classify(model).weight * (effort ? effortFactor(effort) : 1);

  // ── state ────────────────────────────────────────────────────────────────
  function defaults() {
    return { v: 1, plan: "unknown", trialEndsAt: null, creditsRemaining: null, creditsAsOf: null, creditsTotal: null,
      unit: 1, unitSamples: 0, prompts: [], obs: [], models: [], modelsAt: null, selected: { model: "", effort: "" } };
  }
  function sanitize(raw) {
    const d = defaults();
    if (!raw || typeof raw !== "object") return d;
    d.plan = ["trial", "paid", "unknown"].includes(raw.plan) ? raw.plan : "unknown";
    d.trialEndsAt = num(raw.trialEndsAt); d.creditsRemaining = num(raw.creditsRemaining); d.creditsAsOf = num(raw.creditsAsOf);
    d.creditsTotal = num(raw.creditsTotal);
    d.unit = clamp(num(raw.unit, 1), 0.01, 10000); d.unitSamples = clamp(num(raw.unitSamples, 0) | 0, 0, 1000);
    d.prompts = (Array.isArray(raw.prompts) ? raw.prompts : []).filter((p) => p && num(p.t) !== null)
      .map((p) => ({ t: num(p.t), model: String(p.model || "").slice(0, 80), effort: normEffort(p.effort) || "", w: clamp(num(p.w, 1), 0.01, 100) })).slice(-MAX_PROMPTS);
    d.obs = (Array.isArray(raw.obs) ? raw.obs : []).filter((o) => o && num(o.t) !== null && num(o.remaining) !== null)
      .map((o) => ({ t: num(o.t), remaining: num(o.remaining) })).slice(-MAX_OBS);
    d.models = (Array.isArray(raw.models) ? raw.models : []).slice(0, 40).map(cleanModel).filter(Boolean);
    d.modelsAt = num(raw.modelsAt);
    const s = raw.selected || {};
    d.selected = { model: String(s.model || "").slice(0, 80), effort: normEffort(s.effort) || "" };
    return d;
  }
  function cleanModel(m) {
    if (!m || !m.name) return null;
    return { name: String(m.name).slice(0, 80), enabled: m.enabled !== false, selected: !!m.selected, badge: String(m.badge || "").slice(0, 24),
      note: String(m.note || "").slice(0, 80), efforts: (Array.isArray(m.efforts) ? m.efforts : []).map(normEffort).filter(Boolean).filter((e, i, a) => a.indexOf(e) === i),
      vendor: classify(m.name).vendor };
  }

  function recordPrompt(state, { model = "", effort = "", now = Date.now() } = {}) {
    const s = sanitize(state);
    const m = model || s.selected.model, e = effort || s.selected.effort;
    s.prompts.push({ t: now, model: m, effort: normEffort(e) || "", w: promptWeight(m, e) });
    s.prompts = s.prompts.slice(-MAX_PROMPTS);
    return s;
  }
  // The user (or the page scan) reports "N credits left". If we counted prompts
  // since the last reading, the drop calibrates how many credits one weight-unit
  // costs. Exponential average so one odd reading cannot wreck the estimate.
  function observeCredits(state, remaining, now = Date.now(), total = null) {
    const s = sanitize(state);
    const r = num(remaining);
    if (r === null || r < 0) return s;
    const prev = s.obs[s.obs.length - 1];
    if (prev && prev.remaining >= r) {
      const spent = prev.remaining - r;
      const units = s.prompts.filter((p) => p.t > prev.t && p.t <= now).reduce((a, p) => a + p.w, 0);
      if (spent > 0 && units > 0) {
        const sample = spent / units;
        s.unit = s.unitSamples ? clamp(s.unit * 0.6 + sample * 0.4, sample / 8, sample * 8) : sample;
        s.unitSamples = Math.min(s.unitSamples + 1, 1000);
      }
    }
    s.obs.push({ t: now, remaining: r }); s.obs = s.obs.slice(-MAX_OBS);
    s.creditsRemaining = r; s.creditsAsOf = now;
    if (num(total) !== null) s.creditsTotal = num(total);
    return s;
  }
  function setTrial(state, { daysLeft = null, endsAt = null, now = Date.now() } = {}) {
    const s = sanitize(state);
    if (num(endsAt) !== null) s.trialEndsAt = num(endsAt);
    else if (num(daysLeft) !== null) s.trialEndsAt = now + clamp(num(daysLeft), 0, 400) * DAY;
    else s.trialEndsAt = null;
    s.plan = s.trialEndsAt ? "trial" : s.plan;
    return s;
  }
  const daysLeft = (state, now = Date.now()) => {
    const t = num(state && state.trialEndsAt); return t === null ? null : Math.max(0, (t - now) / DAY);
  };

  // Prompts per day over the last 7 days (at least one day of history is used
  // as the divisor so a burst right after install does not look like 200/day).
  function rate(state, now = Date.now()) {
    const s = sanitize(state);
    const since = now - 7 * DAY, recent = s.prompts.filter((p) => p.t >= since);
    if (!recent.length) return { perDay: 0, avgWeight: 0, samples: 0 };
    const first = Math.min(...recent.map((p) => p.t));
    const days = clamp((now - first) / DAY, 1, 7);
    return { perDay: recent.length / days, avgWeight: recent.reduce((a, p) => a + p.w, 0) / recent.length, samples: recent.length };
  }
  const creditsNow = (s, now) => {
    if (s.creditsRemaining === null) return null;
    const used = s.prompts.filter((p) => p.t > (s.creditsAsOf || 0) && p.t <= now).reduce((a, p) => a + p.w, 0) * s.unit;
    return Math.max(0, s.creditsRemaining - used);
  };

  function estimate(state, now = Date.now(), selection = null) {
    const s = sanitize(state);
    const sel = selection || s.selected || {};
    const w = promptWeight(sel.model || s.selected.model, sel.effort || s.selected.effort);
    const out = { creditsLeft: creditsNow(s, now), daysLeft: daysLeft(s, now), perPromptCredits: null, byCredits: null, byTime: null,
      promptsLeft: null, limitedBy: "unknown", confidence: "none", perDay: 0, selectionWeight: w, summary: "", detail: [] };
    const r = rate(s, now); out.perDay = r.perDay;
    if (out.creditsLeft !== null) {
      out.perPromptCredits = Math.max(0.0001, s.unit * w);
      out.byCredits = Math.floor(out.creditsLeft / out.perPromptCredits);
    }
    if (out.daysLeft !== null && r.perDay > 0) out.byTime = Math.floor(r.perDay * out.daysLeft);
    const have = [out.byCredits, out.byTime].filter((x) => x !== null);
    if (have.length) {
      out.promptsLeft = Math.min(...have);
      out.limitedBy = out.byCredits !== null && (out.byTime === null || out.byCredits <= out.byTime) ? "credits" : "time";
    }
    // Confidence: learned unit cost from several readings > a single typed
    // figure > a pure pace projection.
    if (out.byCredits !== null) out.confidence = s.unitSamples >= 3 ? "medium" : "low";
    else if (out.byTime !== null) out.confidence = "low";
    const low = out.promptsLeft === null ? null : Math.floor(out.promptsLeft * (out.confidence === "medium" ? 0.8 : 0.6));
    const high = out.promptsLeft === null ? null : Math.ceil(out.promptsLeft * (out.confidence === "medium" ? 1.25 : 1.6));
    out.range = low === null ? null : [low, high];
    if (out.promptsLeft === null) {
      out.summary = out.daysLeft !== null ? `${Math.ceil(out.daysLeft)} trial day${Math.ceil(out.daysLeft) === 1 ? "" : "s"} left · send a few prompts so I can learn your pace`
        : "Add your credits or trial end date for an estimate";
    } else {
      out.summary = `~${out.promptsLeft} prompt${out.promptsLeft === 1 ? "" : "s"} left (rough ${low}–${high})${out.limitedBy === "time" ? " at your pace until the trial ends" : " on credits"}`;
    }
    if (out.creditsLeft !== null) out.detail.push(`${Math.round(out.creditsLeft).toLocaleString("en-US")} credits left (as of your last reading, minus prompts sent since)`);
    if (out.perPromptCredits !== null) out.detail.push(`≈${out.perPromptCredits < 10 ? out.perPromptCredits.toFixed(1) : Math.round(out.perPromptCredits)} credits per prompt for ${sel.model || s.selected.model || "this model"}${sel.effort || s.selected.effort ? ` · ${sel.effort || s.selected.effort}` : ""}${s.unitSamples ? ` (learned from ${s.unitSamples} reading${s.unitSamples === 1 ? "" : "s"})` : " (default weight — enter credits twice to calibrate)"}`);
    if (out.daysLeft !== null) out.detail.push(`${out.daysLeft < 1 ? "<1" : Math.ceil(out.daysLeft)} day(s) of trial left${r.perDay ? ` · you send ≈${r.perDay.toFixed(1)}/day` : ""}`);
    return out;
  }

  // ── reading what Notion shows ────────────────────────────────────────────
  const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
  function scanText(text, now = Date.now()) {
    const t = String(text || "").replace(/\s+/g, " ");
    const out = {};
    let m = /(\d[\d,]*(?:\.\d+)?)\s*(?:AI\s+)?credits?\s*(?:left|remaining|available)/i.exec(t) || /credits?\s*(?:left|remaining|available)\s*[:\-]?\s*(\d[\d,]*(?:\.\d+)?)/i.exec(t);
    if (m) out.creditsRemaining = num(m[1]);
    m = /(\d[\d,]*)\s*(?:\/|of)\s*(\d[\d,]*)\s*(?:AI\s+)?credits/i.exec(t);
    if (m) { out.creditsTotal = num(m[2]); if (out.creditsRemaining === undefined) out.creditsRemaining = Math.max(0, num(m[2]) - num(m[1])); }
    m = /(?:trial\s+(?:ends|expires)\s+in|ends\s+in)\s*(\d+)\s*days?/i.exec(t) || /(\d+)\s*days?\s*(?:left|remaining)\s*(?:in|of|on)?\s*(?:your\s*)?(?:free\s*)?trial/i.exec(t) || /(\d+)\s*days?\s*(?:left|remaining)/i.exec(t);
    if (m) out.daysLeft = num(m[1]);
    else {
      m = /trial\s+(?:ends|expires)\s+(?:on\s+)?([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:,?\s*(\d{4}))?/i.exec(t);
      if (m) {
        const mi = MONTHS.indexOf(m[1].slice(0, 3).toLowerCase());
        if (mi >= 0) {
          const y = m[3] ? +m[3] : new Date(now).getUTCFullYear();
          let d = Date.UTC(y, mi, +m[2], 23, 59, 59);
          if (!m[3] && d < now - DAY) d = Date.UTC(y + 1, mi, +m[2], 23, 59, 59);
          out.trialEndsAt = d;
        }
      }
    }
    return out;
  }
  function applyScan(state, scan, now = Date.now()) {
    let s = sanitize(state);
    if (!scan) return s;
    if (scan.trialEndsAt != null) s = setTrial(s, { endsAt: scan.trialEndsAt, now });
    else if (scan.daysLeft != null) s = setTrial(s, { daysLeft: scan.daysLeft, now });
    if (scan.creditsRemaining != null && scan.creditsRemaining !== s.creditsRemaining) s = observeCredits(s, scan.creditsRemaining, now, scan.creditsTotal);
    return s;
  }

  // ── the model picker ─────────────────────────────────────────────────────
  const BADGES = /\b(new|beta|preview|recommended|default|upgrade|admin|locked|soon)\b/gi;
  const LOCKED = /upgrade|locked|contact (an )?admin|ask (an )?admin|not available|disabled by|unavailable|coming soon|business plan|enterprise plan/i;
  function cleanName(text) {
    let t = String(text || "").replace(/\s+/g, " ").trim();
    t = t.replace(/\s*[✓✔]\s*$/, "");
    // The name is the first line / segment; descriptions follow a dash or newline.
    t = t.split(/\s[-–—·|]\s|\n/)[0].trim();
    return t.replace(BADGES, " ").replace(/\s+/g, " ").trim().slice(0, 80);
  }
  // items: [{text, selected, disabled}] straight from the picker's DOM rows.
  function parseModels(items) {
    const out = [], seen = new Set();
    for (const it of Array.isArray(items) ? items : []) {
      const raw = String((it && it.text) || "");
      const name = cleanName(raw);
      if (!name || name.length < 2 || seen.has(name.toLowerCase())) continue;
      if (/^(more models|models?|search|settings|learn more|custom agent|personalization)$/i.test(name)) continue;
      const locked = !!(it && it.disabled) || LOCKED.test(raw);
      const badge = (raw.match(BADGES) || [])[0] || "";
      seen.add(name.toLowerCase());
      out.push(cleanModel({ name, enabled: !locked, selected: !!(it && it.selected), badge, note: locked ? "not enabled for this workspace/plan" : "" }));
    }
    return out;
  }
  const tokens = (s) => String(s || "").toLowerCase().replace(/\bclaude\b|\bgpt\b(?=-?\d)/g, (m) => m === "claude" ? "" : m).replace(/[^a-z0-9.]+/g, " ").trim().split(" ").filter(Boolean);
  // "opus 5.5" must pick Opus 5.5, never Opus 5; whole tokens only.
  function findModel(models, query, { enabledOnly = true } = {}) {
    const q = tokens(query); if (!q.length) return null;
    let best = null, bestScore = -1;
    for (const m of Array.isArray(models) ? models : []) {
      if (enabledOnly && m.enabled === false) continue;
      const t = tokens(m.name);
      if (!q.every((x) => t.includes(x))) continue;
      const score = 100 - (t.length - q.length);
      if (score > bestScore) { best = m; bestScore = score; }
    }
    return best;
  }
  function pickEffort(efforts, wanted) {
    const list = (Array.isArray(efforts) ? efforts : []).map(normEffort).filter(Boolean);
    const w = normEffort(wanted);
    if (!w || !list.length) return null;
    if (list.includes(w)) return w;
    // Nearest available level, preferring the higher one on a tie (deeper work).
    const idx = EFFORT_ORDER.indexOf(w);
    return list.slice().sort((a, b) => Math.abs(EFFORT_ORDER.indexOf(a) - idx) - Math.abs(EFFORT_ORDER.indexOf(b) - idx) || EFFORT_ORDER.indexOf(b) - EFFORT_ORDER.indexOf(a))[0];
  }
  function setModels(state, models, now = Date.now()) {
    const s = sanitize(state);
    s.models = (Array.isArray(models) ? models : []).map(cleanModel).filter(Boolean).slice(0, 40);
    s.modelsAt = now;
    const cur = s.models.find((m) => m.selected);
    if (cur) s.selected = { model: cur.name, effort: s.selected.effort };
    return s;
  }
  function chipText(state, now = Date.now()) {
    const s = sanitize(state), e = estimate(s, now);
    const model = s.selected.model ? s.selected.model.replace(/^claude\s+/i, "") : "";
    const parts = [];
    if (model) parts.push(model);
    if (s.selected.effort) parts.push(({ xhigh: "X-High" })[s.selected.effort] || s.selected.effort[0].toUpperCase() + s.selected.effort.slice(1));
    if (e.promptsLeft !== null) parts.push(`~${e.promptsLeft} left`);
    else if (e.daysLeft !== null) parts.push(`${Math.ceil(e.daysLeft)}d trial`);
    return parts.join(" · ");
  }

  return { DAY, EFFORTS, EFFORT_ORDER, MODEL_CLASSES, normEffort, classify, effortFactor, promptWeight, defaults, sanitize,
    recordPrompt, observeCredits, setTrial, daysLeft, rate, estimate, scanText, applyScan, parseModels, findModel, pickEffort,
    setModels, chipText, cleanName };
})();
