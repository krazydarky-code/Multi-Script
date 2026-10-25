// SPDX-License-Identifier: GPL-3.0-or-later
// core/pacing.js - provider-agnostic AUTO-REPLY PACING engine.
//
// Automated tool-result turns need bounded spacing and independent cooldowns.
// This engine reduces traffic bursts, lets the provider finish a response, and
// avoids immediate retries after errors. The worker also coordinates tabs.
// Delays do not bypass account restrictions or change provider quotas.
//
// DESIGN RULES
//  - PURE: no DOM, no chrome.*, no timers. Every function is a decision, so the
//    whole engine is unit-testable in plain node (see tests/test_pacing_engine.js).
//    main.js owns the actual sleeping.
//  - The RNG is INJECTED (opts.rng) so tests are deterministic; the default is
//    Math.random.
//  - Nothing here changes WHAT is sent or WHETHER a command is correct - pacing
//    only changes WHEN a turn is sent. Slowing down can never lower correctness.
//  - OFF is a real mode: delay 0, no long pauses, no cooldown. The previous
//    behaviour is one setting away.
// eslint-disable-next-line no-unused-vars
const ZSPace = (() => {
  "use strict";

  // ── Mode presets ──────────────────────────────────────────────────────────
  // min/max          : the randomised band for the gap before each send (ms).
  // longEvery        : add a long break every Nth send (0 = never).
  // longMin/longMax  : the randomised band for that long break (ms).
  // typingCps        : simulated typing speed in characters/second for the
  //                    composer fill (0 = fill instantly, the old behaviour).
  // errorCooldownMs  : minimum gap enforced after ANY error/throttle signal.
  const MODES = {
    off: {
      label: "Off", hint: "Send immediately (the original behaviour).",
      min: 0, max: 0, longEvery: 0, longMin: 0, longMax: 0, typingCps: 0, errorCooldownMs: 0,
    },
    brisk: {
      label: "Brisk", hint: "Short gaps for light tasks; error cooldowns still apply.",
      min: 400, max: 1400, longEvery: 14, longMin: 2500, longMax: 6000, typingCps: 0, errorCooldownMs: 4000,
    },
    human: {
      label: "Balanced", hint: "Space automated turns and back off after errors.",
      min: 1500, max: 4500, longEvery: 8, longMin: 5000, longMax: 15000, typingCps: 0, errorCooldownMs: 8000,
    },
    cautious: {
      label: "Cautious", hint: "Longer gaps and breaks for conservative request pacing.",
      min: 3000, max: 9000, longEvery: 5, longMin: 10000, longMax: 30000, typingCps: 14, errorCooldownMs: 20000,
    },
    custom: {
      label: "Custom", hint: "Your own numbers.",
      min: 1500, max: 4500, longEvery: 8, longMin: 5000, longMax: 15000, typingCps: 0, errorCooldownMs: 8000,
    },
  };

  const MODE_IDS = Object.keys(MODES);
  // Hard ceilings so a bad import can never wedge the loop for hours.
  const LIMITS = {
    min: [0, 120000], max: [0, 180000], longEvery: [0, 200],
    longMin: [0, 300000], longMax: [0, 600000], typingCps: [0, 120], errorCooldownMs: [0, 600000],
  };

  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const num = (v, fallback) => {
    const n = Number(v);
    return Number.isFinite(n) ? n : fallback;
  };
  function clampField(key, v, fallback) {
    const [lo, hi] = LIMITS[key];
    return clamp(Math.round(num(v, fallback)), lo, hi);
  }

  // A full, validated numeric profile. Any field may come from a preset, from
  // the user's custom block, or from a per-provider override.
  function normalizeProfile(raw, base) {
    const src = raw && typeof raw === "object" ? raw : {};
    const b = base || MODES.human;
    const out = {};
    for (const key of Object.keys(LIMITS)) out[key] = clampField(key, src[key], b[key]);
    // A band is meaningless inverted - swap rather than silently returning 0.
    if (out.max < out.min) { const t = out.max; out.max = out.min; out.min = t; }
    if (out.longMax < out.longMin) { const t = out.longMax; out.longMax = out.longMin; out.longMin = t; }
    // A long break can never be shorter than the ordinary gap.
    if (out.longEvery > 0 && out.longMax > 0 && out.longMax < out.max) out.longMax = out.max;
    return out;
  }

  const DEFAULT_SETTINGS = {
    mode: "human",
    typingSim: false,
    // Per-provider override: { <providerId>: { mode?: id, min?, max?, ... } }
    perProvider: {},
    custom: normalizeProfile(MODES.human, MODES.human),
  };

  function sanitize(raw) {
    const src = raw && typeof raw === "object" ? raw : {};
    const out = {
      mode: MODE_IDS.includes(src.mode) ? src.mode : DEFAULT_SETTINGS.mode,
      typingSim: !!src.typingSim,
      perProvider: {},
      custom: normalizeProfile(src.custom, MODES.human),
    };
    if (src.perProvider && typeof src.perProvider === "object") {
      for (const [id, v] of Object.entries(src.perProvider)) {
        if (!/^[a-z0-9_-]{1,40}$/i.test(id)) continue;
        const e = v && typeof v === "object" ? v : {};
        const entry = {};
        if (MODE_IDS.includes(e.mode)) entry.mode = e.mode;
        for (const key of Object.keys(LIMITS)) {
          if (e[key] != null) entry[key] = clampField(key, e[key], DEFAULT_SETTINGS.custom[key]);
        }
        if (Object.keys(entry).length) out.perProvider[id] = entry;
      }
    }
    return out;
  }

  // The effective numeric profile for a provider: preset (or the user's custom
  // numbers) then any per-provider override layered on top.
  function profileFor(settings, providerId) {
    const s = settings && typeof settings === "object" ? settings : DEFAULT_SETTINGS;
    const mode = MODE_IDS.includes(s.mode) ? s.mode : DEFAULT_SETTINGS.mode;
    let profile;
    if (mode === "custom") profile = normalizeProfile(s.custom, MODES.custom);
    else profile = normalizeProfile(MODES[mode], MODES.human);
    const over = s.perProvider && providerId ? s.perProvider[providerId] : null;
    if (over) {
      const merged = { ...profile, ...(over.mode && MODE_IDS.includes(over.mode) && over.mode !== "custom"
        ? normalizeProfile(MODES[over.mode], profile) : {}) };
      for (const key of Object.keys(LIMITS)) if (over[key] != null) merged[key] = over[key];
      profile = normalizeProfile(merged, profile);
    }
    // Cautious is the floor for a provider the user explicitly marked as
    // sensitive, even when the global mode is Off - the whole point of the
    // per-provider entry is "this site flags me, slow down HERE".
    if (over && over.mode === "cautious" && profile.min === 0 && profile.max === 0) {
      profile = normalizeProfile(MODES.cautious, MODES.cautious);
    }
    return profile;
  }

  const isOff = (profile) => !profile || (profile.min === 0 && profile.max === 0 && profile.longEvery === 0);

  // ── The decision ──────────────────────────────────────────────────────────
  // Returns { delayMs, base, longPause, cooldownMs, reason }.
  //  - delayMs    : how long to wait before this send (>= 0).
  //  - longPause  : true when a periodic break was folded in.
  //  - cooldownMs : the remaining error cooldown, when one applied.
  // opts: { rng, sendIndex, now, lastErrorAt, lastSendAt }
  function computeDelay(settings, providerId, opts = {}) {
    const rng = typeof opts.rng === "function" ? opts.rng : Math.random;
    const now = num(opts.now, Date.now());
    const sendIndex = Math.max(0, Math.round(num(opts.sendIndex, 0)));
    const profile = profileFor(settings, providerId);
    if (isOff(profile)) return { delayMs: 0, base: 0, longPause: false, cooldownMs: 0, reason: "off" };

    const base = Math.round(profile.min + rng() * (profile.max - profile.min));
    let delayMs = base;
    let longPause = false;
    // Every Nth send gets a longer break. Keyed on the send index so it is
    // reproducible (and so a reload does not reset the rhythm to "always fast").
    if (profile.longEvery > 0 && sendIndex > 0 && sendIndex % profile.longEvery === 0) {
      delayMs += Math.round(profile.longMin + rng() * (profile.longMax - profile.longMin));
      longPause = true;
    }

    // Error cooldown: after a failure/throttle, guarantee at least
    // errorCooldownMs of quiet measured from the error, never from "now" - so a
    // retry that arrives late still honours the full quiet period.
    let cooldownMs = 0;
    if (profile.errorCooldownMs > 0 && opts.lastErrorAt) {
      const since = now - num(opts.lastErrorAt, 0);
      if (since >= 0 && since < profile.errorCooldownMs) cooldownMs = profile.errorCooldownMs - since;
    }
    // delayMs is a GAP SINCE THE LAST SEND, not a "sleep this long now". A
    // caller that already spent time waiting (a parked tab, an image upload, a
    // long reply) must not be made to wait the full gap all over again - so
    // subtract whatever has already elapsed. This is what keeps a slow reply
    // from being double-taxed while still guaranteeing the rhythm on a fast one.
    if (opts.lastSendAt) {
      const gap = now - num(opts.lastSendAt, 0);
      if (gap >= delayMs) delayMs = 0;
      else if (gap > 0) delayMs -= gap;
    }
    // Cooldown is measured from the ERROR, not from the preceding send. A slow
    // response may already have spent the normal interval, but must never spend
    // a cooldown that only began when that response failed.
    delayMs = Math.max(delayMs, cooldownMs);
    return { delayMs: Math.max(0, Math.round(delayMs)), base, longPause, cooldownMs: Math.round(cooldownMs), reason: cooldownMs >= delayMs && cooldownMs > 0 ? "error-cooldown" : longPause ? "long-pause" : "interval" };
  }

  // Typing cadence for the composer fill. Returns how long to spend "typing"
  // `charCount` characters, or 0 when simulation is off. Bounded to 12s so a
  // huge injected tool result can never look like a hang.
  function typingDelay(settings, providerId, charCount, opts = {}) {
    const rng = typeof opts.rng === "function" ? opts.rng : Math.random;
    const s = settings && typeof settings === "object" ? settings : DEFAULT_SETTINGS;
    const profile = profileFor(s, providerId);
    if (!s.typingSim || !profile.typingCps) return 0;
    const chars = Math.max(0, Math.round(num(charCount, 0)));
    const ms = (chars / profile.typingCps) * 1000;
    const jitter = 0.85 + rng() * 0.3; // ±15%
    return clamp(Math.round(ms * jitter), 0, 12000);
  }

  // Split a typing budget into a small number of chunk delays, so main.js can
  // fill the composer progressively instead of one long stall.
  function typingChunks(ms, parts = 4) {
    const total = Math.max(0, Math.round(num(ms, 0)));
    const n = Math.max(1, Math.min(12, Math.round(num(parts, 4))));
    if (!total) return [];
    const out = [];
    let left = total;
    for (let i = 0; i < n && left > 0; i++) {
      const take = i === n - 1 ? left : Math.round(left / (n - i));
      out.push(take);
      left -= take;
    }
    return out;
  }

  // Simulate a whole run without sleeping - used by tests and by the menu's
  // "preview" line so a user can see the real rhythm they just selected.
  function planSequence(settings, providerId, count, opts = {}) {
    const rng = typeof opts.rng === "function" ? opts.rng : Math.random;
    const n = Math.max(0, Math.min(1000, Math.round(num(count, 10))));
    const gaps = [];
    for (let i = 0; i < n; i++) gaps.push(computeDelay(settings, providerId, { rng, sendIndex: i, now: 0 }).delayMs);
    return gaps;
  }

  function stats(seq) {
    if (!seq.length) return { count: 0, min: 0, max: 0, mean: 0, totalMs: 0 };
    const total = seq.reduce((a, b) => a + b, 0);
    return {
      count: seq.length,
      min: Math.min(...seq),
      max: Math.max(...seq),
      mean: Math.round(total / seq.length),
      totalMs: total,
    };
  }

  function describe(settings, providerId) {
    const s = settings && typeof settings === "object" ? settings : DEFAULT_SETTINGS;
    const profile = profileFor(s, providerId);
    if (isOff(profile)) return "Pacing off · turns send immediately";
    const band = `${(profile.min / 1000).toFixed(1)}–${(profile.max / 1000).toFixed(1)}s`;
    const parts = [`${band} between turns`];
    if (profile.longEvery > 0) parts.push(`longer break every ${profile.longEvery}`);
    if (profile.errorCooldownMs > 0) parts.push(`${Math.round(profile.errorCooldownMs / 1000)}s cooldown after errors`);
    if (s.typingSim && profile.typingCps) parts.push(`typing ~${profile.typingCps} chars/s`);
    return parts.join(" · ");
  }

  return {
    MODES, MODE_IDS, LIMITS, DEFAULT_SETTINGS,
    sanitize, normalizeProfile, profileFor, isOff,
    computeDelay, typingDelay, typingChunks, planSequence, stats, describe,
  };
})();
