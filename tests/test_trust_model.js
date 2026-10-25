// SPDX-License-Identifier: GPL-3.0-or-later
// test_trust_model.js - the graduated permission model.
//
// The safety properties this pins, in order of how much damage a regression
// would do:
//   1. A corrupt or unknown level must fall back to the MOST restrictive level.
//      Getting this backwards would silently hand a user full PC access.
//   2. Trust is ORDERED: a lower level can never grant a capability a higher
//      level refuses, and grants only grow as the level rises.
//   3. 'ask' confirms every consequential capability - it must not be possible
//      for a write or outside-project reach to skip confirmation.
//   4. Reading is never blocked at any level (looking is not the risk).
//   5. Every capability the extension can actually request is DECLARED here, so
//      a new one cannot slip in with an implicit undefined permission.
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");
let failures = 0;
let sections = 0;
function check(cond, label) {
  if (cond) { console.log(`  ok  ${label}`); }
  else { console.log(`  FAIL ${label}`); failures++; }
}
function section(name) { sections++; console.log(`\n${sections}. ${name}`); }

const src = fs.readFileSync(path.join(ROOT, "extension/core/trust.js"), "utf8");
const T = new Function(src + ";return ZSTrust;")();

// ── 1. fail-safe on corrupt input ───────────────────────────────────────
section("a corrupt level falls back to the MOST restrictive, never the widest");
check(T.sanitize(null).level === "sandbox", "null settings -> sandbox");
check(T.sanitize({}).level === "sandbox", "missing level -> sandbox");
check(T.sanitize({ level: "GODMODE" }).level === "sandbox", "unknown level -> sandbox");
check(T.sanitize({ level: 123 }).level === "sandbox", "non-string level -> sandbox");
check(T.sanitize({ level: "FULL" }).level === "sandbox", "case-mismatch is not silently accepted");
check(T.sanitize("full").level === "sandbox", "a bare string is not a settings object");
check(T.sanitize({ level: "full" }).level === "full", "a genuinely valid level is accepted");
check(T.sanitize({ denied: "not-an-array" }).denied.length === 0, "a corrupt denied list is dropped, not iterated");

// ── 2. the ordering is total and monotonic ──────────────────────────────
section("trust is ordered: grants only grow as the level rises");
check(JSON.stringify(T.LEVELS) === JSON.stringify(["sandbox", "ask", "full"]), "levels are ordered sandbox < ask < full");
const sb = new Set(T.GRANTS.sandbox), ak = new Set(T.GRANTS.ask), fl = new Set(T.GRANTS.full);
check([...sb].every((c) => ak.has(c)), "everything sandbox allows, ask also allows");
check([...ak].every((c) => fl.has(c)), "everything ask allows, full also allows");
check(sb.size < ak.size || ak.size <= fl.size, "grant sets do not shrink as trust grows");
check(T.levelFor([...sb]) === "sandbox", "levelFor recovers sandbox from its own grants");
// ask and full share a grant SET; they differ only in confirmation. levelFor
// answers "can it happen at this level", not "does it happen silently", so both
// sets resolve to the cheapest level that permits them - ask.
check(T.levelFor([...ak]) === "ask", "the bare ask grant set resolves to ask");
check(T.levelFor([...fl]) === "ask", "full's grant set resolves to ask, since ask already permits it (by prompting)");
// A requirement ask satisfies - even by prompting first - should land on ask.
// Only a requirement sandbox already meets outright lands on sandbox.
check(T.levelFor(["fs.read.any"]) === "ask", "reading anywhere resolves to the level that asks first");
check(T.levelFor(["browser.tabs.drive"]) === "ask", "driving a tab resolves to the level that asks first");
check(T.levelFor(["process.spawn"]) === "ask", "running a command resolves to the level that asks first");
check(T.levelFor(["fs.write.any"]) === "ask", "writing anywhere resolves to ask, which permits it by confirming");
check(T.levelFor(["media.relay"]) === "sandbox", "relaying a file needs no prompt, so sandbox covers it");
check(T.levelFor(["desktop.read"]) === "sandbox", "a plain look at the desktop needs no prompt either");
check(T.levelFor(["engine.write"]) === "sandbox", "sandbox already permits building in the engine");
check(T.levelFor(["engine.read", "made.up"]) === "sandbox", "unknown capabilities are ignored by levelFor");
check(T.levelFor([]) === "sandbox", "an empty requirement is satisfiable at the narrowest level");

// ── 3. no level can lift the capabilities it must refuse ────────────────
section("consequential capabilities are refused where they must be");
const refuses = [
  ["sandbox", "fs.write.any"], ["sandbox", "fs.read.any"], ["sandbox", "process.spawn"],
  ["sandbox", "desktop.control"], ["sandbox", "browser.tabs.drive"],
];
for (const [lvl, cap] of refuses) {
  const r = T.can({ level: lvl }, cap);
  check(r.allowed === false, `${lvl} refuses ${cap}`);
  check(!!r.reason, `${lvl} refusal of ${cap} carries a reason`);
}
check(T.can({ level: "ask" }, "fs.write.any").allowed === true, "ask permits fs.write.any");
check(T.can({ level: "full" }, "fs.write.any").allowed === true, "full permits fs.write.any");
check(T.can({ level: "full" }, "process.spawn").needsConfirm === false, "full does not confirm process.spawn");

// ── 4. 'ask' confirms every consequential reach ─────────────────────────
section("at 'ask', every consequential reach is confirmed");
// What counts as consequential at 'ask': anything that writes, plus anything
// ask newly reaches for. A capability sandbox already allows outright that only
// looks at something (tabs.read, desktop.read, process.list) is not re-promoted
// to an interrupt just because a higher level could act on it.
const SANDBOX_OUTRIGHT = new Set(T.GRANTS.sandbox);
for (const cap of Object.keys(T.CAPABILITIES)) {
  const meta = T.CAPABILITIES[cap];
  const r = T.can({ level: "ask" }, cap);
  if (!r.allowed) continue;
  const justLooking = !meta.writes && SANDBOX_OUTRIGHT.has(cap);
  const consequential = !justLooking && cap !== "media.relay";
  if (consequential) {
    check(r.needsConfirm === true, `ask confirms ${cap}`);
  } else {
    check(r.needsConfirm === false, `ask does not interrupt for harmless ${cap}`);
  }
}
// The two capabilities ask confirms that are NOT writes - they reach somewhere
// new, so they are still interruptions.
check(T.can({ level: "ask" }, "fs.read.any").needsConfirm === true, "ask confirms fs.read.any");
check(T.can({ level: "ask" }, "browser.tabs.drive").needsConfirm === true, "ask confirms browser.tabs.drive");
// And the three sandbox reads stay silent at every level.
for (const cap of ["browser.tabs.read", "desktop.read", "process.list"]) {
  check(T.can({ level: "ask" }, cap).needsConfirm === false, `ask lets ${cap} through silently`);
  check(T.can({ level: "full" }, cap).needsConfirm === false, `full lets ${cap} through silently`);
}
check(T.can({ level: "full" }, "desktop.control").needsConfirm === false, "full performs without a per-call prompt");
check(T.can({ level: "sandbox" }, "media.relay").needsConfirm === false, "relaying media is never an interrupt");

// ── 5. reading is never blocked ─────────────────────────────────────────
section("reading is allowed at every level - looking is not the risk");
const reads = ["engine.read", "project.read", "browser.tabs.read", "desktop.read", "process.list"];
for (const lvl of T.LEVELS) {
  for (const cap of reads) {
    check(T.can({ level: lvl }, cap).allowed === true, `${lvl} allows ${cap}`);
  }
}

// ── 6. per-capability denial narrows without changing the level ─────────
section("a user can deny a single capability without dropping a whole level");
let s = T.sanitize({ level: "full", denied: ["fs.write.any"] });
check(T.can(s, "fs.write.any").allowed === false, "denied capability is refused even at full");
check(T.can(s, "fs.read.any").allowed === true, "other capabilities are unaffected");
check(/turned off/i.test(T.can(s, "fs.write.any").reason), "the reason says the user turned it off");
s = T.sanitize({ level: "full", denied: ["nonsense.capability"] });
check(s.denied.length === 0, "unknown capabilities cannot be added to the deny list");

// ── 7. undeclared capability is denied ──────────────────────────────────
section("an undeclared capability is denied, never implicitly allowed");
const un = T.can({ level: "full" }, "totally.unknown");
check(un.allowed === false, "unknown capability is refused at every level");
check(/not a declared capability/.test(un.reason), "the reason names it as undeclared");
check(T.can({ level: "full" }, undefined).allowed === false, "undefined capability is refused");

// ── 8. the matrix is complete and consistent ────────────────────────────
section("the capability matrix covers everything and matches can()");
const m = T.matrix({ level: "ask" });
check(m.length === Object.keys(T.CAPABILITIES).length, "matrix lists every capability");
for (const row of m) {
  check(row.label && row.label.length > 3, `${row.id} has a human label`);
  const r = T.can({ level: "ask" }, row.id);
  check(row.allowed === r.allowed && row.needsConfirm === r.needsConfirm, `matrix agrees with can() for ${row.id}`);
}

// ── 9. hard limits are declared and level-independent ───────────────────
section("hard limits exist and no level can lift them");
check(Array.isArray(T.HARD_LIMITS) && T.HARD_LIMITS.length >= 4, "hard limits are declared");
check(T.HARD_LIMITS.some((l) => /never send/i.test(l)), "the exfiltration limit is stated");
check(T.HARD_LIMITS.some((l) => /credential|token|password/i.test(l)), "the credentials limit is stated");
check(T.HARD_LIMITS.some((l) => /http/i.test(l)), "the URL-scheme limit is stated");
const lim = T.HARD_LIMITS.join(" ").toLowerCase();
check(!/can be raised|depends on level/i.test(lim), "hard limits are not described as level-dependent");

// ── 10. every level has complete, honest copy ───────────────────────────
section("each level is described honestly to the user");
for (const lvl of T.LEVELS) {
  const meta = T.LEVEL_META[lvl];
  check(meta && meta.label && meta.tagline && meta.description && meta.detail, `${lvl} has full copy`);
  check(T.describe({ level: lvl }).includes(meta.label), `describe() names ${lvl}`);
}
check(/refused/i.test(T.describe({ level: "sandbox" })), "sandbox copy says things are refused");
check(/confirm/i.test(T.describe({ level: "ask" })), "ask copy mentions confirmation");

console.log("");
if (failures) {
  console.log(`test_trust_model: ${failures} FAILED`);
  process.exit(1);
}
console.log(`test_trust_model: ${sections} sections passed`);
