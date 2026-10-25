// SPDX-License-Identifier: GPL-3.0-or-later
// Verification-assistant regression (core/verification.js + its wiring).
//
// WHY THIS FILE EXISTS
// The request was "auto-complete captchas on arena.ai, not exactly a bypass,
// but something to keep it running too". Those are two different things and the
// boundary between them is the entire point of this file:
//
//   KEEP IT RUNNING  = notice the check, stop automating, alert the human, click
//                      the provider's OWN widget once if allowed, resume by
//                      itself, and slow later sends so it stops recurring.
//   BYPASS           = solve it, answer it, forge or harvest a token, call a
//                      solving service, or postMessage into the challenge.
//
// The first is legitimate and is what ships. The second is asserted ABSENT here,
// in the provider source, so it can never be added by accident - and the
// user-facing copy is asserted to say plainly that no bypass happens, so we can
// never quietly claim otherwise.

const fs = require("fs"), path = require("path");
const root = path.resolve(__dirname, "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const ok = (c, m) => { if (!c) throw new Error(m); };

const ZSVerify = new Function(read("extension/core/verification.js") + ";return ZSVerify;")();
const arenaSrc = read("extension/providers/arena.js");
const mainSrc = read("extension/core/main.js");
const manifest = JSON.parse(read("extension/manifest.json"));

// ── 1. NO BYPASS, anywhere ──────────────────────────────────────────────
// Each of these is a concrete way a real captcha bypass is implemented.
// If one ever appears in the shipped CODE, this test fails loudly.
//
// Comments are stripped first: several of these names are deliberately listed
// in the prose explaining what this module refuses to do, and a comment that
// says "we never call grecaptcha.execute" must not trip the check that the
// comment is describing. Strip line and block comments, then look for CODE.
function stripComments(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, " ")   // /* block */
    .replace(/^\s*\/\/.*$/gm, " ")        // whole-line //
    .replace(/([^:"'`\\])\/\/[^\n"'`]*/g, "$1 "); // trailing //
}
const FORBIDDEN = [
  "2captcha", "anti-captcha", "anticaptcha", "capsolver", "capmonster",
  "rucaptcha", "deathbycaptcha", "solve.captcha", "captcha solver",
  "grecaptcha.execute", "grecaptcha.getresponse", "grecaptcha.ready",
  "hcaptcha.execute", "turnstile.render(", "turnstile.getresponse",
  "g-recaptcha-response", "h-captcha-response", "cf-turnstile-response",
  "contentwindow.postmessage", "postmessage(", "sitekey:",
];
const shipped = stripComments([arenaSrc, mainSrc, read("extension/core/verification.js")].join("\n")).toLowerCase();
for (const bad of FORBIDDEN) {
  ok(!shipped.includes(bad), `bypass implementation detected in code: "${bad}"`);
}
// The scanner must actually be looking at code, or all of the above is vacuous.
ok(!stripComments("// we never call grecaptcha.execute\n").includes("grecaptcha.execute"),
  "the comment stripper must remove a whole-line comment");
ok(stripComments("x = grecaptcha.execute();").includes("grecaptcha.execute"),
  "the comment stripper must KEEP real code - the check above must not be vacuous");
// The one place we intentionally interact: a single click, and no token read.
ok(/function assistChallengeClick/.test(arenaSrc), "the assisted click must exist");
const clickFn = arenaSrc.slice(arenaSrc.indexOf("function assistChallengeClick"));
const clickBody = clickFn.slice(0, clickFn.indexOf("\n  }\n"));
ok(!/value\s*=/.test(clickBody), "the assisted click must never WRITE a value (token injection)");
ok(!/\.value/.test(clickBody), "the assisted click must never READ a value (token harvesting)");
ok(!/querySelector\([^)]*response/i.test(clickBody), "the assisted click must never look for a response field");
// It must be exactly one click per call - no loop, no retry.
const dispatchCount = (clickBody.match(/dispatchEvent\(/g) || []).length;
ok(dispatchCount <= 5 && dispatchCount >= 1,
  `the assisted click must be a single bounded gesture (got ${dispatchCount} dispatches)`);
ok(!/setInterval|setTimeout|for\s*\(|while\s*\(/.test(clickBody),
  "the assisted click must never loop or retry - a repeat click is what looks scripted");

// ── 2. The mode ladder is honest ────────────────────────────────────────
ok(ZSVerify.MODE_IDS.length === 4, `expected 4 modes, got ${ZSVerify.MODE_IDS.length}`);
ok(ZSVerify.MODE_IDS.join(",") === "off,watch,assist,unattended",
  "mode ids must stay stable (saved settings reference them)");
// Only the modes that claim assistance may assist.
for (const id of ["off", "watch"]) {
  ok(!ZSVerify.MODES[id].assist, `${id} must NOT click the widget`);
  ok(!ZSVerify.MODES[id].adaptive, `${id} must NOT slow the run down`);
}
for (const id of ["assist", "unattended"]) {
  ok(ZSVerify.MODES[id].assist, `${id} must allow the single assisted click`);
  ok(ZSVerify.MODES[id].adaptive, `${id} must slow the run down after a check`);
}
// Every mode that can click must also alert, so an unattended click is never
// silent (the human must be able to find out what happened).
for (const id of ZSVerify.MODE_IDS) {
  const m = ZSVerify.MODES[id];
  if (m.assist) ok(m.alert, `${id} clicks the widget, so it MUST alert the user`);
}
// Off is the historical behaviour: pause and resume only.
ok(!ZSVerify.MODES.off.alert && !ZSVerify.MODES.off.assist,
  "Off must be pure observe-and-resume");

// ── 3. sanitize is total and clamps ─────────────────────────────────────
const junk = ZSVerify.sanitize({ mode: "nope", waitMs: -5, settleMs: 9e9, audibleAlert: "x", perProvider: { arena: { mode: "assist" }, "BAD ID!": { mode: "off" } } });
ok(ZSVerify.MODE_IDS.includes(junk.mode), "an unknown mode must fall back to a real one");
ok(junk.waitMs === 60000, `waitMs must clamp low (got ${junk.waitMs})`);
ok(junk.settleMs === 600000, `settleMs must clamp high (got ${junk.settleMs})`);
ok(junk.audibleAlert === true, "a truthy audibleAlert must survive");
ok(junk.perProvider.arena && junk.perProvider.arena.mode === "assist", "a valid provider override must survive");
ok(!junk.perProvider["BAD ID!"], "a malformed provider id must be dropped");
ok(ZSVerify.sanitize(null).mode === ZSVerify.DEFAULT_SETTINGS.mode, "sanitize(null) must be safe");
ok(ZSVerify.sanitize("nonsense").mode === ZSVerify.DEFAULT_SETTINGS.mode, "sanitize(a string) must be safe");

// ── 4. Per-provider override resolution ─────────────────────────────────
const s = ZSVerify.sanitize({ mode: "watch", perProvider: { arena: { mode: "unattended" } } });
ok(ZSVerify.modeFor(s, "arena").id === "unattended", "a provider override must win");
ok(ZSVerify.modeFor(s, "deepseek").id === "watch", "other providers must keep the global mode");
ok(ZSVerify.modeFor(s, null).id === "watch", "a null provider must use the global mode");
ok(ZSVerify.describe(s, "arena").includes("Unattended"), "describe must name the effective mode");

// ── 5. Adaptive slowdown: grows, caps, decays ───────────────────────────
let st = ZSVerify.initialState();
ok(st.floorMs === 0 && st.streak === 0, "a fresh state must impose no delay");
// First challenge: one step of floor.
let t = 1_000_000;
st = ZSVerify.noteChallenge(st, t);
const one = st.floorMs;
ok(one === ZSVerify.SLOWDOWN.stepMs, `one challenge must add exactly one step (got ${one})`);
ok(st.streak === 1, "a first challenge starts a streak of 1");
// A REPEAT inside the window escalates FASTER than a one-off.
st = ZSVerify.noteChallenge(st, t + 60000);
ok(st.floorMs > one * 2, `a repeat challenge must escalate faster (got ${st.floorMs})`);
ok(st.streak === 2, "a repeat within the window must extend the streak");
// An isolated challenge long afterwards resets the streak.
let st2 = ZSVerify.noteChallenge(ZSVerify.initialState(), t);
st2 = ZSVerify.noteChallenge(st2, t + ZSVerify.SLOWDOWN.repeatWindowMs + 1);
ok(st2.streak === 1, "a challenge outside the repeat window must restart the streak");
// The floor is capped, so a run can never be slowed into uselessness.
let capped = ZSVerify.initialState();
for (let i = 0; i < 60; i++) capped = ZSVerify.noteChallenge(capped, t + i * 1000);
ok(capped.floorMs === ZSVerify.SLOWDOWN.maxMs, `the floor must cap (got ${capped.floorMs})`);
// Decay: a clean stretch releases the floor, but only after a good window.
let d = ZSVerify.noteChallenge(ZSVerify.initialState(), t);
const held = ZSVerify.noteClean(d, t + 1000);
ok(held.floorMs === d.floorMs, "a short clean gap must NOT release the floor");
let released = d;
for (let i = 0; i < 4; i++) released = ZSVerify.noteClean(released, t + (i + 1) * ZSVerify.SLOWDOWN.decayAfterMs);
ok(released.floorMs < d.floorMs, "a long clean stretch must release the floor");
ok(ZSVerify.noteClean(ZSVerify.initialState(), t).floorMs === 0, "decay on a zero floor stays zero");
// Release must be PROPORTIONAL, not a fixed step: a bigger floor sheds more per
// interval, which is what keeps recovery from a heavy patch bounded in time.
const small = ZSVerify.noteChallenge(ZSVerify.initialState(), t);
let big = small;
for (let i = 0; i < 12; i++) big = ZSVerify.noteChallenge(big, t + (i + 1) * 1000);
ok(big.floorMs > small.floorMs, "the test needs a heavier floor to compare");
function shedOnce(from) {
  let x = ZSVerify.noteClean(from, t + 1000);            // start the clock
  const before = x.floorMs;
  x = ZSVerify.noteClean(x, t + ZSVerify.SLOWDOWN.decayAfterMs + 2000);
  return before - x.floorMs;
}
ok(shedOnce(big) > shedOnce(small), "a heavier floor must shed MORE per interval (proportional decay)");
// Recovery from the CEILING must be bounded in a sane number of clean intervals.
let ceilState = ZSVerify.initialState();
for (let i = 0; i < 40; i++) ceilState = ZSVerify.noteChallenge(ceilState, t + i * 1000);
ok(ceilState.floorMs === ZSVerify.SLOWDOWN.maxMs, "the ceiling must be reachable");
let wt = t, n = 0;
while (ceilState.floorMs > 0 && n < 200) { wt += ZSVerify.SLOWDOWN.decayAfterMs; ceilState = ZSVerify.noteClean(ceilState, wt); n++; }
ok(ceilState.floorMs === 0, "decay must reach EXACTLY zero (no asymptotic residue)");
ok(n <= 20, `recovery from the ceiling must be bounded (took ${n} clean intervals)`);
// The minimum shed guarantees progress even for a tiny floor.
ok(ZSVerify.SLOWDOWN.decayMinMs > 0, "decay must always shed a minimum, so it cannot stall");

// ── 6. extraDelayMs: the settle taper ───────────────────────────────────
const set = ZSVerify.sanitize({ settleMs: 60000 });
let cs = ZSVerify.noteChallenge(ZSVerify.initialState(), t);
cs = { ...cs, lastAt: t }; // as if it just cleared
const immediate = ZSVerify.extraDelayMs(cs, t, set);
const midway = ZSVerify.extraDelayMs(cs, t + 30000, set);
const after = ZSVerify.extraDelayMs(cs, t + 60001, set);
ok(immediate > midway && midway > after, "the settle taper must decrease over its window");
ok(after === cs.floorMs, "once the settle window ends only the floor remains");
ok(ZSVerify.extraDelayMs(ZSVerify.initialState(), t, set) === 0, "a clean state must demand no extra delay");

// ── 7. Escalation ladder respects the mode ──────────────────────────────
// Off: only the banner/cover steps, never an alert, never a click.
const offSteps = ZSVerify.escalationActions(-1, 600000, ZSVerify.MODES.off).map((x) => x.action);
ok(!offSteps.includes("alert") && !offSteps.includes("re-alert"), "Off must never alert");
ok(!offSteps.includes("assist-click"), "Off must never click");
// Assist: the click step appears, but only once, and late (after the alert).
const aSteps = ZSVerify.escalationActions(-1, 600000, ZSVerify.MODES.assist).map((x) => x.action);
ok(aSteps.includes("assist-click"), "Assist must schedule the assisted click");
ok(aSteps.filter((x) => x === "assist-click").length === 1, "the assisted click must fire exactly once");
const alertIdx = aSteps.indexOf("alert"), clickIdx = aSteps.indexOf("assist-click");
ok(alertIdx >= 0 && alertIdx < clickIdx, "the alert must come BEFORE the click (the human gets first refusal)");
// The click is deliberately NOT immediate: we do not touch the widget on sight.
const firstClick = ZSVerify.escalationActions(0, 30000, ZSVerify.MODES.assist).map((x) => x.action);
ok(!firstClick.includes("assist-click"), "the assisted click must NOT fire in the first 30s");
// Watch: alerts but never clicks.
const wSteps = ZSVerify.escalationActions(-1, 600000, ZSVerify.MODES.watch).map((x) => x.action);
ok(wSteps.includes("alert") && !wSteps.includes("assist-click"), "Watch must alert but never click");
// Steps already applied must not re-fire.
ok(ZSVerify.escalationActions(600000, 600000, ZSVerify.MODES.unattended).length === 0,
  "already-applied steps must not be returned again");

// ── 8. The copy says plainly that nothing is bypassed ───────────────────
const copy = Object.values(ZSVerify.COPY).join(" ").toLowerCase();
ok(copy.includes("does not solve or bypass"), "the banner must state the boundary");
ok(copy.includes("will not answer it for you"), "the assist notice must hand the rest to the human");
ok(/never solves or bypasses|not.*bypass/.test(copy), "a bypass disclaimer must exist in the copy");
// It must never over-promise.
for (const claim of ["solved", "bypassed the captcha", "automatically completes the captcha", "we solve"]) {
  ok(!copy.includes(claim), `the copy must not claim: "${claim}"`);
}

// ── 9. Wiring: manifest, provider export, core orchestration ────────────
// The module must actually load, and BEFORE main.js which uses it. Only blocks
// that load the core need it: some blocks are single-file early injections
// (a pre-load shim) and load no core module at all.
let mainBlocks = 0;
for (const cs of manifest.content_scripts || []) {
  const js = cs.js || [];
  if (!js.includes("core/main.js")) continue;
  mainBlocks++;
  const vi = js.indexOf("core/verification.js");
  const mi = js.indexOf("core/main.js");
  ok(vi >= 0, "core/verification.js must be listed in every block that loads core/main.js");
  ok(vi < mi, "core/verification.js must load BEFORE core/main.js");
}
ok(mainBlocks >= 8, `expected the core in every provider block (found ${mainBlocks})`);
// Every core module must appear together, so no block silently loses one.
for (const cs of manifest.content_scripts || []) {
  const js = cs.js || [];
  if (!js.includes("core/main.js")) continue;
  for (const mod of ["core/engines.js", "core/config.js", "core/parser.js", "core/tool-routing.js", "core/pacing.js", "core/resilience.js", "core/verification.js"]) {
    ok(js.includes(mod), `a core block is missing ${mod}`);
  }
}
// Provider surface.
ok(/captchaPresent, waitForHumanVerification, overlayBlocking/.test(arenaSrc), "the arena provider must still export its verification helpers");
ok(/assistChallengeClick,/.test(arenaSrc), "arena must export the assisted click");
ok(/challengeClickTarget/.test(arenaSrc), "arena must expose the click-target finder");
ok(/reallyVisible\(el\)/.test(arenaSrc.slice(arenaSrc.indexOf("function challengeClickTarget"))),
  "the click target must be a really-visible element (never an invisible badge)");
// The click target must skip the always-present reCAPTCHA v3 badge.
const targetFn = arenaSrc.slice(arenaSrc.indexOf("function challengeClickTarget"));
const targetBody = targetFn.slice(0, targetFn.indexOf("\n  }\n"));
ok(/grecaptcha-badge/.test(targetBody), "the click target must exclude the reCAPTCHA v3 badge");
ok(/closest\("#zs-root"\)/.test(targetBody), "the click target must never be our own UI");
// Core orchestration.
ok(/ZSVerify\.modeFor/.test(mainSrc), "core must resolve the verification mode");
ok(/ZSVerify\.noteChallenge/.test(mainSrc), "core must record challenges for the slowdown");
ok(/ZSVerify\.extraDelayMs/.test(mainSrc), "core must apply the adaptive delay");
ok(/ZSVerify\.escalationActions/.test(mainSrc), "core must drive the escalation ladder");
ok(/P\.assistChallengeClick/.test(mainSrc), "core must use the provider's assisted click");
ok(/verification-slowdown/.test(mainSrc), "the slowdown must be visible as a pacing reason");
ok(/clearVerificationAlert/.test(mainSrc), "the alert must be cleared on resume");
// The adaptive delay must be folded into the pacing decision, not bypass it.
const paceFn = mainSrc.slice(mainSrc.indexOf("async function paceBeforeSend"));
const paceBody = paceFn.slice(0, paceFn.indexOf("\n  }"));
ok(/Math\.max\(plan\.delayMs, verifyMs[,)]/.test(paceBody),
  "the verification floor must extend the paced delay, never replace it");
// Reset must clear the new setting too.
ok(/verificationSettings=ZSVerify\.sanitize\(ZSVerify\.DEFAULT_SETTINGS\)/.test(mainSrc),
  "the agent-behavior reset must reset verification handling");
// Backup/restore + diagnostics must carry it.
ok(/verification:ZSVerify\.sanitize\(verificationSettings\)/.test(mainSrc),
  "the settings backup must include verification handling");
ok(/if\(raw\.verification\)/.test(mainSrc), "settings restore must read verification handling");
ok(/verificationSummary:ZSVerify\.describe/.test(mainSrc), "diagnostics must summarise verification handling");
// The menu must offer it.
ok(/data-verify=/.test(mainSrc), "the menu must render the verification modes");
ok(/zs-verify-audible/.test(mainSrc), "the menu must expose the audible-alert toggle");

// ── 10. The pre-existing gate still holds ───────────────────────────────
// The original guarantee - a hidden badge causes no pause, a visible challenge
// does - must be untouched by any of this.
ok(/function reallyVisible/.test(arenaSrc), "reallyVisible must survive");
ok(/grecaptcha-badge/.test(arenaSrc.slice(arenaSrc.indexOf("const CAPTCHA_SEL"))),
  "the v3 badge must still be excluded from detection");
ok(/CHALLENGE_TEXT_RE/.test(arenaSrc), "the independent text probe must survive");
ok(/does not bypass verification challenges/.test(arenaSrc),
  "the provider's own no-bypass error text must survive");

console.log("PASS verification assistant: no bypass anywhere, 4 honest modes, escalating slowdown that caps and decays, a single bounded click on the provider's own widget that alerts first and never reads or writes a token, and the whole path wired through manifest, provider, core, menu, backup and diagnostics");
