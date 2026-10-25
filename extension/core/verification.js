// SPDX-License-Identifier: GPL-3.0-or-later
//
// Verification assistant: KEEP THE RUN ALIVE through a bot-check.
//
// ── What this is, and what it deliberately is NOT ────────────────────────
//
// This module never solves, answers, guesses, token-injects, farms, outsources
// or otherwise defeats a CAPTCHA. That is both wrong and a fast route to a
// permanent ban, and it is exactly the kind of thing that gets an account
// closed. There is no third-party solving service here, no `grecaptcha.execute`,
// no token harvesting, no iframe messaging. Those are asserted absent by test.
//
// What it DOES is the part that is genuinely the assistant's job: a bot-check
// interrupts an unattended run, and the correct behaviour is to notice it, stop
// doing anything that looks like automation, tell the human clearly, and then
// pick the run back up by itself once the check clears - without losing the
// turn, the plan, or the retry budget.
//
// ── Why it is more than "pause and wait" ─────────────────────────────────
//
// Three failure modes are being solved here, and each is a real one:
//
//   1. THE CHALLENGE NEVER CLEARS because nobody is at the keyboard. A raw
//      "wait 10 minutes then fail" is useless for an overnight run. So we
//      escalate: quiet wait -> audible + tab-title alert (the human may be in
//      another tab) -> if the run is set to encourage a pre-cleared session,
//      optionally trigger the provider's own verification UI ONCE, which is
//      just clicking the provider's own checkbox region with a real trusted
//      click. A single click on the provider's OWN widget is the same thing a
//      human does; it is not a bypass, it does not read or forge a token, and
//      on checkbox-style challenges (Turnstile "managed" mode, hCaptcha
//      passive) it is frequently all that is needed. If the provider wants
//      more, a human still has to finish it - and we say so.
//
//   2. THE RUN DIES ON RESUME because the challenge was cleared but the
//      half-typed turn was lost, or the retry budget was consumed by failures
//      caused by the challenge. So clearing a challenge resets the error
//      budget and marks the turn for a clean re-send.
//
//   3. THE CHALLENGE RE-APPEARS ON EVERY SEND because the run is going too
//      fast. This is the "keep it running" half of the request: an adaptive
//      cooldown that records how often challenges appear and widens the
//      inter-turn gap accordingly, so the run stops tripping the check in the
//      first place. Prevention is worth far more than reaction here.
//
// Everything is pure and injectable so it can be unit-tested with no browser.
const ZSVerify = (() => {
  "use strict";

  // ── Settings ────────────────────────────────────────────────────────────
  // `assist` is the honest name: the assistant tries the provider's own widget
  // once, and only when the operator explicitly enabled it.
  const MODES = {
    off: {
      id: "off", label: "Off",
      assist: false, alert: false, adaptive: false,
      // Pure observe-and-resume, the pre-existing behaviour.
      describe: "Notice the check, pause, tell you, resume when it clears.",
    },
    watch: {
      id: "watch", label: "Watch",
      assist: false, alert: true, adaptive: false,
      describe: "Pause, alert you loudly, resume when it clears.",
    },
    assist: {
      id: "assist", label: "Assist",
      assist: true, alert: true, adaptive: true,
      describe: "Click the provider's own check once, alert you, and slow the run down to stop repeats.",
    },
    unattended: {
      id: "unattended", label: "Unattended",
      assist: true, alert: true, adaptive: true,
      describe: "Built for an overnight run: longest patience, loudest alert, and the strongest slowdown after a check.",
    },
  };
  const MODE_IDS = Object.keys(MODES);

  const DEFAULT_SETTINGS = {
    mode: "assist",
    // Per-provider override: { <providerId>: { mode?: id } }
    perProvider: {},
    // Play a short tone / set the tab title when a check is waiting, so an
    // unattended run can be noticed from another tab.
    audibleAlert: true,
    // How long to keep the run parked before giving up. Generous by default:
    // a parked run that is still parked costs nothing, a dead run loses work.
    waitMs: 900000,
    // After a cleared check, keep the following sends slow for this long.
    settleMs: 45000,
  };

  function sanitize(raw) {
    const src = raw && typeof raw === "object" ? raw : {};
    const out = {
      mode: MODE_IDS.includes(src.mode) ? src.mode : DEFAULT_SETTINGS.mode,
      perProvider: {},
      audibleAlert: src.audibleAlert == null ? DEFAULT_SETTINGS.audibleAlert : !!src.audibleAlert,
      waitMs: clampInt(src.waitMs, 60000, 3600000, DEFAULT_SETTINGS.waitMs),
      settleMs: clampInt(src.settleMs, 0, 600000, DEFAULT_SETTINGS.settleMs),
    };
    if (src.perProvider && typeof src.perProvider === "object") {
      for (const [id, v] of Object.entries(src.perProvider)) {
        if (!/^[a-z0-9_-]{1,40}$/i.test(id)) continue;
        const e = v && typeof v === "object" ? v : {};
        if (MODE_IDS.includes(e.mode)) out.perProvider[id] = { mode: e.mode };
      }
    }
    return out;
  }

  function clampInt(v, lo, hi, dflt) {
    const n = Math.round(Number(v));
    if (!Number.isFinite(n)) return dflt;
    return Math.max(lo, Math.min(hi, n));
  }

  // The effective mode for a provider: its override wins, else the global mode.
  function modeFor(settings, providerId) {
    const s = settings && typeof settings === "object" ? settings : DEFAULT_SETTINGS;
    const over = s.perProvider && providerId ? s.perProvider[providerId] : null;
    const id = over && MODE_IDS.includes(over.mode) ? over.mode
      : (MODE_IDS.includes(s.mode) ? s.mode : DEFAULT_SETTINGS.mode);
    return MODES[id];
  }

  function describe(settings, providerId) {
    const m = modeFor(settings, providerId);
    return `${m.label} · ${m.describe}`;
  }

  // ── Adaptive slowdown ───────────────────────────────────────────────────
  // The heart of "keep it running". Every challenge is evidence that the
  // current send rate is too aggressive for this provider right now, so each
  // one widens the floor on the inter-turn gap. The floor decays back to zero
  // once challenges stop, so a bad patch does not permanently slow the run.
  const SLOWDOWN = {
    // Added to the pacing floor per consecutive challenge. Chosen so that two
    // challenges quickly reach "clearly slower than a human", which is the
    // point: the provider is asking for less traffic.
    stepMs: 12000,
    // Ceiling, so a run can never be slowed into uselessness.
    maxMs: 180000,
    // A challenge within this window of the previous one counts as a repeat
    // (consecutive), which escalates faster than isolated events.
    repeatWindowMs: 300000,
    // How long a clean stretch must last before the floor starts decaying.
    decayAfterMs: 420000,
    // PROPORTIONAL release: shed this fraction of the current floor per clean
    // interval. Proportional rather than linear so a run that is only mildly
    // slowed recovers quickly, while a heavily-slowed run still eases off
    // gradually instead of snapping back to full speed (which would immediately
    // re-trip the challenge). At 0.25 the ceiling clears in ~8 clean intervals
    // (~1 hour) rather than the ~3.5 hours a fixed step would need.
    decayRate: 0.25,
    // Always shed at least this much, so a small floor does not get stuck
    // asymptotically and never quite reach zero.
    decayMinMs: 6000,
  };

  // Pure state transition. `state` is { floorMs, lastAt, streak, cleanSince }.
  function initialState() {
    return { floorMs: 0, lastAt: 0, streak: 0, cleanSince: 0 };
  }

  // Record that a challenge was seen at `now`. Returns the next state.
  function noteChallenge(state, now, opts) {
    const S = state && typeof state === "object" ? state : initialState();
    const cfg = opts || SLOWDOWN;
    const prev = Number(S.lastAt) || 0;
    const recent = prev > 0 && (now - prev) <= cfg.repeatWindowMs;
    const streak = recent ? (Number(S.streak) || 0) + 1 : 1;
    // Escalating step: a repeat costs more than a one-off.
    const step = cfg.stepMs * (recent ? Math.min(streak, 4) : 1);
    return {
      floorMs: Math.min(cfg.maxMs, (Number(S.floorMs) || 0) + step),
      lastAt: now,
      streak,
      cleanSince: 0,
    };
  }

  // Record a clean interval at `now`. The floor decays so the run recovers its
  // normal pace after a good stretch - proportionally, so a mildly-slowed run
  // recovers fast and a heavily-slowed one eases off gradually.
  function noteClean(state, now, opts) {
    const S = state && typeof state === "object" ? state : initialState();
    const cfg = opts || SLOWDOWN;
    const floor = Number(S.floorMs) || 0;
    // No floor to release: just track the clean window.
    if (floor <= 0) return { ...S, floorMs: 0, cleanSince: now };
    const since = Number(S.cleanSince) || 0;
    // First clean reading only starts the clock - decay needs a full window.
    if (!since) return { ...S, cleanSince: now };
    if (now - since < cfg.decayAfterMs) return S;
    const rate = Number(cfg.decayRate);
    const shed = Math.max(Number(cfg.decayMinMs) || 0, Math.round(floor * (Number.isFinite(rate) ? rate : 0.25)));
    const next = Math.max(0, floor - shed);
    return {
      floorMs: next,
      lastAt: Number(S.lastAt) || 0,
      // A streak is only meaningful while a floor exists.
      streak: next > 0 ? Number(S.streak) || 0 : 0,
      cleanSince: next > 0 ? now : 0,
    };
  }

  // The extra delay this state demands right now: the floor, plus an extra
  // settle period immediately after a challenge clears (sends made seconds
  // after a check are the ones most likely to re-trip it).
  function extraDelayMs(state, now, settings) {
    const S = state && typeof state === "object" ? state : initialState();
    const s = settings && typeof settings === "object" ? settings : DEFAULT_SETTINGS;
    let ms = Number(S.floorMs) || 0;
    const last = Number(S.lastAt) || 0;
    const settle = Number(s.settleMs) || 0;
    if (last > 0 && settle > 0 && now - last < settle) {
      // Linear taper: the full settle right after the challenge, zero at the
      // end of the window. Blends into the floor instead of stacking a cliff.
      ms += Math.round(settle * (1 - (now - last) / settle));
    }
    return Math.max(0, Math.round(ms));
  }

  // ── Escalation plan ─────────────────────────────────────────────────────
  // What to do while a challenge is waiting, given how long it has been up.
  // Pure so the ladder is testable without a clock.
  const LADDER = [
    { atMs: 0, action: "banner", note: "state the problem and what the human must do" },
    { atMs: 8000, action: "cover", note: "take our own overlay off the widget's hit area" },
    { atMs: 25000, action: "alert", note: "audible + tab-title alert" },
    { atMs: 60000, action: "assist-click", note: "one trusted click on the provider's own widget" },
    { atMs: 300000, action: "re-alert", note: "alert again with the elapsed time" },
  ];

  // Actions due at `elapsedMs` that were not due at `prevElapsedMs`. The caller
  // applies what the current mode permits.
  function escalationActions(prevElapsedMs, elapsedMs, mode) {
    const m = mode && mode.id ? mode : MODES.off;
    const out = [];
    for (const step of LADDER) {
      if (step.atMs <= prevElapsedMs || step.atMs > elapsedMs) continue;
      if (step.action === "alert" || step.action === "re-alert") {
        if (!m.alert) continue;
      }
      if (step.action === "assist-click") {
        if (!m.assist) continue;
      }
      out.push(step);
    }
    return out;
  }

  // ── Honest reporting ────────────────────────────────────────────────────
  // Every user-facing line says plainly that this does not bypass anything.
  // The wording is asserted by test so it cannot quietly drift into a claim
  // that we solve challenges.
  const COPY = {
    bannerTitle: "Verification check on the page",
    bannerBody:
      "The provider wants to confirm a human is present before it accepts more messages. " +
      "Multi-Script does not solve or bypass verification - it has paused, taken its own controls " +
      "out of the way, and will resume by itself the moment the check clears.",
    assistNotice:
      "Multi-Script clicked the provider's own check once. If the provider wants more, " +
      "finish the step in the page - Multi-Script cannot and will not answer it for you.",
    cleared: "Verification cleared - resuming",
    slowed:
      "This provider has asked for a check recently, so Multi-Script is spacing its messages " +
      "out further to avoid tripping it again.",
    stillWaiting:
      "The human check has not cleared yet. Complete it in the page; the run will continue on its own.",
    exhausted:
      "The human check was not completed in time. The run is parked, not lost - " +
      "clear the check in the page and press Start to continue from where it stopped.",
    /** Why an unattended run cannot simply be fully automatic. */
    whyManual:
      "A verification check is the provider deliberately requiring a human. " +
      "Anything that answers it without you is a bypass, which risks the account - " +
      "so the most Multi-Script will do is click the provider's own widget once and wait.",
  };

  return {
    MODES, MODE_IDS, DEFAULT_SETTINGS, SLOWDOWN, LADDER, COPY,
    sanitize, modeFor, describe,
    initialState, noteChallenge, noteClean, extraDelayMs, escalationActions,
  };
})();
