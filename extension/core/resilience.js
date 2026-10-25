// SPDX-License-Identifier: GPL-3.0-or-later
// core/resilience.js - provider-agnostic ERROR-RECOVERY policy for the loop.
//
// WHY THIS EXISTS
// The agentic loop is meant to be left alone. Historically a single hiccup - the
// site dropping a reply, a 5-minute inactivity timeout, a swallowed send, a
// half-written command - ended the loop with a banner and a greyed "not run"
// chip, and the user had to notice and re-prompt by hand. That is fine for an
// attended session and useless for an unattended one.
//
// This module is the DECISION layer: given what just went wrong and how many
// times it has already gone wrong, it says whether to retry (and after how
// long), to keep waiting, or to give up honestly. It never decides WHAT to send
// - the caller supplies the feedback text - so correctness is untouched: a
// retry can only ever re-ask, never fake a result.
//
// It is deliberately PURE (no DOM, no timers, no chrome.*) so the whole policy
// is unit-testable in plain node (see tests/test_error_recovery.js).
// eslint-disable-next-line no-unused-vars
const ZSResilience = (() => {
  "use strict";

  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const num = (v, f) => { const n = Number(v); return Number.isFinite(n) ? n : f; };

  // ── Levels ────────────────────────────────────────────────────────────────
  // maxRetries      : per-failure retry budget (resets when a turn succeeds).
  // maxConsecutive  : give up once this many failures happen back-to-back, so a
  //                   genuinely broken session stops instead of burning quota.
  // backoffMs       : delay before retry N (last value repeats).
  const LEVELS = {
    off: {
      label: "Off", hint: "A failure ends the loop, as before.",
      maxRetries: 0, maxConsecutive: 0, backoffMs: [],
      retrySilence: false, retryParse: false, retrySend: false, autoContinue: false,
    },
    standard: {
      label: "Standard", hint: "Recovers from the common one-off hiccups.",
      maxRetries: 4, maxConsecutive: 8, backoffMs: [2000, 4000, 8000, 15000],
      retrySilence: true, retryParse: true, retrySend: true, autoContinue: false,
    },
    persistent: {
      label: "Persistent", hint: "Keeps a long unattended run alive through repeated stalls.",
      maxRetries: 10, maxConsecutive: 20,
      backoffMs: [2000, 5000, 10000, 15000, 25000, 40000, 60000],
      retrySilence: true, retryParse: true, retrySend: true, autoContinue: true,
    },
  };
  const LEVEL_IDS = Object.keys(LEVELS);

  // Persistent by default: a long run should ride through repeated site hiccups and a model that
  // keeps mis-formatting a command, instead of stopping with "recovery budget spent" after 2 tries.
  const DEFAULT_SETTINGS = { level: "persistent", perProvider: {} };

  function sanitize(raw) {
    const src = raw && typeof raw === "object" ? raw : {};
    const out = { level: LEVEL_IDS.includes(src.level) ? src.level : DEFAULT_SETTINGS.level, perProvider: {} };
    if (src.perProvider && typeof src.perProvider === "object") {
      for (const [id, v] of Object.entries(src.perProvider)) {
        if (!/^[a-z0-9_-]{1,40}$/i.test(id)) continue;
        if (LEVEL_IDS.includes(v)) out.perProvider[id] = v;
      }
    }
    return out;
  }

  function levelFor(settings, providerId) {
    const s = settings && typeof settings === "object" ? settings : DEFAULT_SETTINGS;
    const per = s.perProvider && providerId ? s.perProvider[providerId] : null;
    if (per && LEVEL_IDS.includes(per)) return per;
    return LEVEL_IDS.includes(s.level) ? s.level : DEFAULT_SETTINGS.level;
  }
  const policy = (level) => LEVELS[level] || LEVELS.standard;

  // ── Feedback text ─────────────────────────────────────────────────────────
  // Injected as a normal (camouflaged) turn. Every one of them is explicit that
  // nothing was run, so a model can never read a recovery nudge as a result.
  const FEEDBACK = {
    silence: (why) =>
      "(System note: your previous turn produced no readable text - " + why + ". " +
      "Nothing from it was executed. Do not apologise, do not repeat earlier context, and do not " +
      "restate the plan. Continue the task from where you stopped: if a command was still pending, " +
      "write it again as exactly ONE plain-text JSON object; otherwise continue the work or give the " +
      "final answer.)",
    parse: (name) =>
      "(System note: your previous reply looked like a Multi-Script command but was not one complete " +
      "plain-text JSON object, so it was NOT executed. " +
      (name && name !== "command" ? `The command name detected was "${name}". ` : "") +
      'Write it again as exactly {"command": "exact_name", "params": { ...all parameters... }} - ' +
      "no code fences, no XML-like tags, no special markers, one command only.)",
    send: () =>
      "(System note: the extension could not hand its previous message to the composer, so the model " +
      "never received it. This is a local hiccup, not a mistake by the model. The message is being " +
      "sent again now.)",
    busy: () =>
      "(System note: the site itself reported a transient problem - it was busy or asked to try again - " +
      "so your previous turn was not a real answer and NOTHING from it was executed. The site is being " +
      "retried now. Do not apologise and do not explain the outage. Continue the task from where you " +
      "stopped: if a command was still pending, write it again as exactly ONE plain-text JSON object; " +
      "otherwise continue the work or give the final answer.)",
  };

  // ── Site notices (rate limits / outages / caps) ──────────────────────────
  // Short texts the SITE shows when it refuses or fails a turn. Used by the
  // core on (a) a short reply, (b) any small notice/toast that appears after a
  // send. Order matters: quota before rate before busy.
  const QUOTA_RE = /usage (limit|cap) (has been )?(reached|exceeded|hit)|you(?:'|’| ha)?ve (reached|hit|used up) (your|the) (\w+ ){0,2}(limit|cap|quota)|(daily|hourly|message|free) (limit|cap|quota) (reached|exceeded|hit)|out of (free )?(messages|credits|tokens)|quota (exceeded|reached)|insufficient (balance|credits)|upgrade (your plan )?to (continue|keep chatting|send more)|额度(已)?用(完|尽)|次数(已)?用(完|尽)|余额不足/i;
  const RATE_RE = /messages? (are |is )?(sent )?too (frequent|fast|quickly)|too many (requests|messages|attempts)|rate[ -]?limit(ed|ing)?|request(s)? (are |is )?too frequent|sending (messages )?too (fast|quickly|frequently)|you(?:'|’| a)?re (sending|going|typing) too fast|slow down|try again (later|in (a|\d+) ?(moment|few|bit|min|minute|second|sec|s)\w*)|wait (a (moment|minute|few|bit)|\d+ ?(s|sec|seconds|min|minutes)) (and|then|before)|请求(过于|太)频繁|(发送|消息|操作|访问)(过于|太|过)频繁|频繁|请求太多|稍后(再)?(重)?试|请稍候再试|trop de (requ[êe]tes|messages)|r[ée]essayez plus tard|demasiadas (solicitudes|peticiones)|zu viele anfragen|muitas solicita/i;
  const BUSY_RE = /server(s)? (is |are )?(busy|overloaded|at capacity|unavailable)|system is (currently )?busy|(high|heavy) (demand|traffic)|temporarily unavailable|service unavailable|overloaded|at capacity|something went wrong|network error|connection (error|lost|interrupted|failed)|failed to (send|fetch|generate|get (a )?response)|an (unexpected |unknown )?error (has )?occurred|error (generating|getting) (a |the )?response|request failed|internal server error|bad gateway|gateway time-?out|(502|503|504)\b|服务器繁忙|系统繁忙|服务繁忙|网络(错误|异常)|serveur (est )?occup|une erreur s.est produite|ha ocurrido un error/i;
  function classifyNotice(text) {
    const t = String(text || "").replace(/\s+/g, " ").trim();
    if (t.length < 4 || t.length > 320) return null;
    if (QUOTA_RE.test(t) || /account.{0,24}(suspended|banned|disabled|restricted)|access.{0,12}(denied|blocked)/i.test(t)) return { kind: "quota", text: t.slice(0, 200) };
    if (RATE_RE.test(t)) return { kind: "rate", text: t.slice(0, 200) };
    if (BUSY_RE.test(t)) return { kind: "busy", text: t.slice(0, 200) };
    return null;
  }
  function isExplicitProviderLimit(text) {
    // Assistant advice such as "slow down decorative motion" is ordinary task
    // output. It must not trigger a resend just because a UI toast could use
    // those same words to announce a rate limit.
    return /too many (requests|messages|attempts)|messages?.{0,24}too (frequent|fast)|rate[ -]?limit.{0,32}(exceeded|reached|error|try again|wait)|(?:reached|exceeded|used up).{0,48}(limit|quota)|(?:usage|daily|message|free)\s+(?:limit|cap|quota).{0,16}(reached|exceeded|hit)|out of (free )?(messages|credits|tokens)|quota (exceeded|reached)|insufficient (balance|credits)|upgrade.{0,24}(continue|send more)|account.{0,24}(suspended|banned|disabled|restricted)|请求.{0,16}频繁|额度(已)?用(完|尽)|次数(已)?用(完|尽)|余额不足/i.test(String(text||''));
  }
  // Backoff ladders (ms) for site refusals. A rate limit needs real time to
  // clear; an outage usually clears fast; a usage cap needs a long wait.
  const SITE_BACKOFF = {
    rate:  [20000, 40000, 70000, 110000, 160000, 220000, 300000],
    busy:  [6000, 12000, 25000, 45000, 75000, 120000, 180000],
    quota: [300000, 600000, 900000],
  };
  const SITE_RETRIES = {
    off:        { rate: 0, busy: 0, quota: 0 },
    standard:   { rate: 3, busy: 3, quota: 0 },
    persistent: { rate: 5, busy: 5, quota: 0 },
  };
  // Adaptive per-site minimum gap between sends. Each rate limit doubles it
  // (8 s → 90 s cap); every clean send decays it ~12 % until it vanishes.
  function nextRateFloor(prevMs) {
    const p = Math.max(0, num(prevMs, 0));
    return clamp(p ? Math.round(p * 2) : 8000, 8000, 90000);
  }
  function decayRateFloor(prevMs) {
    const p = Math.max(0, num(prevMs, 0));
    const n = Math.round(p * 0.88);
    return n < 2500 ? 0 : n;
  }
  function retryAfterMs(text) {
    const m=String(text||'').match(/(?:try again|retry|wait)(?:\s+(?:after|in|for))?\s+(\d+(?:\.\d+)?)\s*(seconds?|secs?|s\b|minutes?|mins?|m\b|hours?|hrs?|h\b)/i);
    return m ? Math.min(86400000,Number(m[1])*(/^h/i.test(m[2])?3600000:/^m/i.test(m[2])?60000:1000)) : 0;
  }

  // ── The decision ──────────────────────────────────────────────────────────
  // kind: "empty" | "timeout" | "parse_error" | "send_failed" | "verification"
  //       | "bridge_offline" | "terminal"
  // ctx : { attempt, consecutive, feedback, name }
  //   attempt     - retries ALREADY spent on this same failure (0 on the first).
  //   consecutive - failures in a row, across kinds (resets on any success).
  //   feedback    - the caller's text (e.g. ZS.FEEDBACK.parseError); optional.
  // Returns { action, delayMs, feedback, reason, attemptsLeft, level }
  //   action: "retry"  → send `feedback` as a new turn after delayMs
  //           "resend" → send the SAME outbound text again after delayMs
  //           "wait"   → park and re-check (verification / bridge); no send
  //           "stop"   → end the loop and report honestly
  function decide(level, kind, ctx = {}) {
    const L = policy(level);
    const attempt = Math.max(0, Math.round(num(ctx.attempt, 0)));
    const consecutive = Math.max(0, Math.round(num(ctx.consecutive, 0)));
    const delayFor = (i) => (L.backoffMs.length ? L.backoffMs[Math.min(i, L.backoffMs.length - 1)] : 0);
    const out = (action, delayMs, feedback, reason) => ({
      action, delayMs, feedback: feedback || "", reason, level,
      attemptsLeft: Math.max(0, L.maxRetries - attempt),
    });
    const budgetSpent = () => attempt >= L.maxRetries;
    const tooMany = () => L.maxConsecutive > 0 && consecutive >= L.maxConsecutive;

    switch (kind) {
      case "verification":
        // Never a retry: the user must clear it. The loop parks and re-checks,
        // which is exactly what "wait" means here.
        return out("wait", 0, "", "human-verification");
      case "bridge_offline":
        // The bridge or the editor is down; it is not the model's fault and
        // re-prompting cannot help. Park and re-check.
        return out("wait", 0, "", "environment-offline");
      case "terminal":
        return out("stop", 0, "", "terminal");
      case "native_response": {
        const budget=L===LEVELS.persistent?3:L===LEVELS.standard?1:0;
        if(attempt>=budget||tooMany())return out('stop',0,'','native-retry-budget-spent');
        return {...out('native-retry',Math.max(2000,delayFor(attempt)),'','native-response'),attemptsLeft:budget-attempt-1};
      }
      case "empty":
      case "timeout": {
        if (!L.retrySilence) return out("stop", 0, "", "recovery-off");
        if (budgetSpent()) return out("stop", 0, "", "silence-retry-budget-spent");
        if (tooMany()) return out("stop", 0, "", "too-many-consecutive-failures");
        const why = kind === "timeout"
          ? "the site stopped responding in time"
          : "the reply was empty or the site dropped it";
        return out("retry", delayFor(attempt), FEEDBACK.silence(why), kind);
      }
      case "busy":
      case "rate":
      case "quota": {
        // The SITE refused or failed the turn ("Messages too frequent", "server
        // busy", "something went wrong", a usage cap). The model never saw our
        // message (or never answered it), so the right move is to WAIT the site
        // out and re-send the SAME message - never a new nudge, which is itself
        // another message and deepens a rate limit (the 6.28 DeepSeek storm).
        // Own budget and backoff ladder, independent of the consecutive cap.
        if (kind === "quota") return out("stop",0,"","provider-quota-or-access-limit");
        if (!L.retrySilence) return out("stop", 0, "", "recovery-off");
        const ladder = SITE_BACKOFF[kind] || SITE_BACKOFF.busy;
        const budget = (SITE_RETRIES[level] || SITE_RETRIES.standard)[kind] ?? 0;
        if (attempt >= budget) return out("stop", 0, "", kind + "-retry-budget-spent");
        const base = ladder[Math.min(attempt, ladder.length - 1)];
        const jitter = Math.round(base * 0.15 * clamp(num(ctx.jitter, 0.5), 0, 1));
        const delay = Math.max(base + jitter, num(ctx.minDelayMs, 0), retryAfterMs(ctx.notice));
        if (ctx.raw) return { ...out("resend", delay, "", kind), attemptsLeft: Math.max(0, budget - attempt - 1) };
        return { ...out("retry", delay, FEEDBACK.busy(), kind), attemptsLeft: Math.max(0, budget - attempt - 1) };
      }
      case "parse_error": {
        if (!L.retryParse) return out("stop", 0, "", "recovery-off");
        if (budgetSpent()) return out("stop", 0, "", "parse-retry-budget-spent");
        if (tooMany()) return out("stop", 0, "", "too-many-consecutive-failures");
        return out("retry", delayFor(attempt), ctx.feedback || FEEDBACK.parse(ctx.name), "parse_error");
      }
      case "send_failed": {
        if (!L.retrySend) return out("stop", 0, "", "recovery-off");
        if (budgetSpent()) return out("stop", 0, "", "send-retry-budget-spent");
        if (tooMany()) return out("stop", 0, "", "too-many-consecutive-failures");
        return out("resend", delayFor(attempt), ctx.feedback || "", "send_failed");
      }
      default:
        return out("stop", 0, "", "unknown");
    }
  }

  // Budgets the caller uses to widen its own timers. A persistent run gets a
  // longer patience for a slow reply and for a still-open command block.
  function budgets(level) {
    const L = policy(level);
    const persistent = L === LEVELS.persistent;
    return {
      level,
      // Extra patience folded into waitForResponse's pre-start silent window.
      preStartSilentMs: persistent ? 120000 : 60000,
      // Extra patience before a warm, content-free turn is declared empty.
      warmupMs: persistent ? 75000 : 45000,
      // Extra patience for a reasoning phase with no answer yet.
      reasonNoReplyMs: persistent ? 150000 : 90000,
      // Extra patience for an open (still-streaming) command block.
      openBlockGraceMs: persistent ? 12000 : 6000,
      // How long to keep waiting for the user to clear a bot-check.
      verificationWaitMs: persistent ? 900000 : 600000,
      autoContinue: !!L.autoContinue,
    };
  }

  function describe(settings, providerId) {
    const level = levelFor(settings, providerId);
    const L = policy(level);
    if (L.maxRetries === 0) return "Recovery off · a failure ends the run";
    return `${L.label} · up to ${L.maxRetries} retries per failure · gives up after ${L.maxConsecutive} failures in a row`;
  }

  return {
    LEVELS, LEVEL_IDS, DEFAULT_SETTINGS, FEEDBACK,
    sanitize, levelFor, policy, decide, budgets, describe,
    classifyNotice, isExplicitProviderLimit, retryAfterMs, nextRateFloor, decayRateFloor, SITE_BACKOFF, SITE_RETRIES,
  };
})();
