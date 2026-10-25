// SPDX-License-Identifier: GPL-3.0-or-later
// Refusal-feedback honesty.
//
// Every message the extension returns to the model is an instruction. A message
// that states a FALSE cause makes the model act on a false premise. The bug this
// pins: `subagent` is permanently disabled, but it was refused with "the command
// TIMED OUT and is unavailable in this environment" - which implies a retry
// could succeed, so the model retried instead of routing around it.
//
// The contract now: one accurate message per real reason, and never a claim of
// a cause we cannot actually know.
const fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const ok = (c, m) => { if (!c) throw new Error(m); };

let passed = 0;
const t = (name, fn) => { fn(); passed++; console.log('  ok  ' + name); };

const ZS = new Function(read('extension/core/config.js') + ';return ZS;')();
const MAIN = read('extension/core/main.js');

// ── 1. blockedFeedback exists and is exported ────────────────────────────
t('ZS.blockedFeedback is exported and total', () => {
  ok(typeof ZS.blockedFeedback === 'function', 'ZS.blockedFeedback is not a function');
  ok(ZS.PERMANENTLY_BLOCKED instanceof Set, 'ZS.PERMANENTLY_BLOCKED is not a Set');
  ok(ZS.PERMANENTLY_BLOCKED.has('subagent'), 'subagent is no longer declared permanently blocked');
  // Total: never throws, always returns a non-empty string, for any input.
  for (const bad of ['', 'subagent', 'screen_capture', 'unknown_thing', null, undefined, 0]) {
    const s = ZS.blockedFeedback(bad, { supportsVision: false });
    ok(typeof s === 'string' && s.length > 20, `blockedFeedback(${JSON.stringify(bad)}) returned nothing useful`);
  }
});

// ── 2. a permanently-blocked command is not described as a timeout ───────
t('a permanently-disabled command is never described as "timed out"', () => {
  const s = ZS.blockedFeedback('subagent', { supportsVision: false });
  ok(!/timed out|timeout/i.test(s), 'subagent is still described as a timeout (false cause)');
  ok(/permanently disabled|never run/i.test(s), 'subagent message does not say it is permanently disabled');
  ok(/do not call it again/i.test(s), 'subagent message does not tell the model to stop retrying');
});

// ── 3. the no-vision refusal names the real limitation + an alternative ──
t('the vision refusal states the real limitation and a workaround', () => {
  const s = ZS.blockedFeedback('screen_capture', { supportsVision: false });
  ok(/image/i.test(s), 'vision refusal does not mention images');
  ok(!/timed out|timeout/i.test(s), 'vision refusal claims a timeout (false cause)');
  // It must route the model to programmatic alternatives, not just refuse.
  for (const alt of ['inspect_instance', 'search_game_tree', 'script_read', 'get_console_output']) {
    ok(s.includes(alt), `vision refusal does not offer ${alt} as the alternative`);
  }
});

// ── 4. a provider WITH vision is not refused for vision reasons ──────────
// Guards the "we refuse something the provider can actually do" over-block.
t('screen_capture is not refused for image reasons when the provider supports vision', () => {
  const s = ZS.blockedFeedback('screen_capture', { supportsVision: true });
  ok(!/no image input|cannot see images/i.test(s),
    'screen_capture was refused for image reasons even though the provider supports vision');
});

// ── 5. an unmodelled block does not invent a cause ───────────────────────
t('an unknown block reason does not fabricate a timeout', () => {
  const s = ZS.blockedFeedback('mystery_tool', { supportsVision: false });
  ok(!/timed out|timeout/i.test(s), 'unknown blocked tool is described as a timeout (fabricated cause)');
});

// ── 6. main.js delegates to it (no drifting duplicate) ───────────────────
// The whole bug was the message and the block list living in two places and
// drifting. main.js must call the shared helper, not re-spell the text.
t('main.js delegates refusal text to the shared helper', () => {
  ok(/ZS\.blockedFeedback\s*\(/.test(MAIN), 'main.js does not call ZS.blockedFeedback');
  // The old false-cause sentence must be gone from main.js entirely.
  ok(!/command timed out and is unavailable in this environment/.test(MAIN),
    'main.js still contains the old "timed out" refusal text');
  // And the block set must come from config, not a second hardcoded literal.
  ok(/ZS\.PERMANENTLY_BLOCKED/.test(MAIN),
    'main.js does not source the permanently-blocked set from core/config.js');
});

// ── 7. the fallback path in main.js is still truthful ────────────────────
// If a stale config.js lacks blockedFeedback, main.js falls back inline. That
// fallback must ALSO avoid the false timeout claim.
t('main.js inline fallback does not claim a timeout', () => {
  const i = MAIN.indexOf('if (isBlockedTool(name))');
  ok(i > 0, 'could not locate the block handler');
  const block = MAIN.slice(i, i + 1600);
  ok(!/timed out/.test(block), 'the inline fallback still claims a timeout');
});

console.log(`\ntest_refusal_feedback: ${passed} sections passed`);
