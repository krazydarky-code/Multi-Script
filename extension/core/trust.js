// SPDX-License-Identifier: GPL-3.0-or-later
// core/trust.js - the graduated permission model.
//
// WHY THIS EXISTS
// Multi-Script can do increasingly consequential things: read a page, drive a
// browser tab, type into someone's composer, enumerate their desktop windows,
// write files, run commands. Expressing that as a pile of independent booleans
// forces the user to reason about six switches at once and gives them no way to
// say "keep it contained" in one move.
//
// This module turns the whole surface into ONE ordered choice - sandbox, ask,
// full - and derives every individual grant from it. The capability list is
// explicit, so a new capability must be DECLARED here rather than quietly
// defaulting to whatever the old code did.
//
// The ordering is the safety property: sandbox < ask < full. A level can never
// imply a grant that a LOWER level would refuse, and `levelFor` can be used to
// display which level a given set of grants corresponds to.
//
// Pure logic: no DOM, no chrome APIs, no I/O. Unit-tested directly.

const ZSTrust = (() => {
  // Ordered from most restrictive to least. The array order IS the trust order
  // and is relied on by levelFor() - do not reorder without updating that.
  const LEVELS = ["sandbox", "ask", "full"];

  const LEVEL_META = {
    sandbox: {
      id: "sandbox",
      label: "Sandbox",
      tagline: "Engine and project folder only",
      description: "The agent can work inside the connected engine and the project folder it was given, and look at things, but cannot touch anything else on this machine.",
      detail: "Reads stay on. Anything that writes outside the project, runs a command, or reaches the wider PC is refused before it starts.",
    },
    ask: {
      id: "ask",
      label: "Ask",
      tagline: "Confirm each write or run",
      description: "Everything sandbox allows, plus the wider PC - but each individual write or command run is confirmed by you first.",
      detail: "Nothing consequential happens silently. A refusal is reported back to the agent as a refusal, not as an error to retry around.",
    },
    full: {
      id: "full",
      label: "Full",
      tagline: "All PC files and processes",
      description: "The agent may read and change anything on this machine and run commands without asking each time. Intended for a machine you are actively supervising.",
      detail: "Still bounded by the hard limits below, which no level can lift.",
    },
  };

  // Every capability the agent can request, declared explicitly. `writes` marks
  // the ones that can change something a user would care about; `outsideProject`
  // marks the ones that reach beyond the folder Multi-Script was pointed at.
  const CAPABILITIES = {
    "engine.read":        { writes: false, outsideProject: false, label: "Read the connected engine" },
    "engine.write":       { writes: true,  outsideProject: false, label: "Build and change things in the engine" },
    "project.read":       { writes: false, outsideProject: false, label: "Read the project folder" },
    "project.write":      { writes: true,  outsideProject: false, label: "Write inside the project folder" },
    "browser.tabs.read":  { writes: false, outsideProject: true,  label: "See and read browser tabs" },
    "browser.tabs.drive": { writes: true,  outsideProject: true,  label: "Click and type in browser tabs" },
    "desktop.read":       { writes: false, outsideProject: true,  label: "See desktop apps and windows" },
    "desktop.control":    { writes: true,  outsideProject: true,  label: "Click and type in other apps" },
    "media.relay":        { writes: false, outsideProject: true,  label: "Carry a photo or video into a chat" },
    "fs.read.any":        { writes: false, outsideProject: true,  label: "Read any file on this PC" },
    "fs.write.any":       { writes: true,  outsideProject: true,  label: "Write any file on this PC" },
    "process.list":       { writes: false, outsideProject: true,  label: "List running processes" },
    "process.spawn":      { writes: true,  outsideProject: true,  label: "Run commands on this PC" },
  };

  // Hard limits that NO level may lift. These are not permissions - they are the
  // things Multi-Script will not do at all, and keeping them here (rather than in
  // each call site) means there is exactly one place to audit.
  const HARD_LIMITS = [
    "It will never send your files, source, keys or screenshots anywhere by itself.",
    "It will never read credentials, tokens or password stores.",
    "It will never act on an external service (email, social, purchases) without you asking it to.",
    "Opening a URL is restricted to http and https; executable and local-file schemes are refused at every level.",
  ];

  // What each level grants. Read as: at this level, these capabilities are ON.
  // Sandbox deliberately allows browser/desktop READ - looking is not the risk,
  // acting is - but nothing that writes outside the project.
  const GRANTS = {
    sandbox: [
      "engine.read", "engine.write", "project.read", "project.write",
      "browser.tabs.read", "desktop.read", "media.relay", "process.list",
    ],
    ask: [
      "engine.read", "engine.write", "project.read", "project.write",
      "browser.tabs.read", "browser.tabs.drive", "desktop.read", "desktop.control",
      "media.relay", "fs.read.any", "fs.write.any", "process.list", "process.spawn",
    ],
    full: [
      "engine.read", "engine.write", "project.read", "project.write",
      "browser.tabs.read", "browser.tabs.drive", "desktop.read", "desktop.control",
      "media.relay", "fs.read.any", "fs.write.any", "process.list", "process.spawn",
    ],
  };

  const DEFAULT_LEVEL = "sandbox";

  function isLevel(v) {
    return typeof v === "string" && LEVELS.indexOf(v) !== -1;
  }

  // Coerce anything into a valid settings object. A corrupt value must never
  // leave the extension in an unknown trust state, so an unrecognised level
  // falls back to the MOST restrictive one, not the most permissive.
  function sanitize(raw) {
    const r = raw && typeof raw === "object" ? raw : {};
    const level = isLevel(r.level) ? r.level : DEFAULT_LEVEL;
    return {
      level,
      // User-visible acknowledgement that they chose the widest level. Not a
      // security boundary - the level is - but it prevents an accidental switch
      // to full from going unnoticed.
      acknowledgeFull: r.acknowledgeFull === undefined ? false : !!r.acknowledgeFull,
      // Per-capability overrides on top of the level, so a user can go narrower
      // without dropping a whole level.
      denied: Array.isArray(r.denied) ? r.denied.filter((c) => c in CAPABILITIES) : [],
    };
  }

  /**
   * Can this settings object use a capability?
   * Returns { allowed, reason, needsConfirm } - never a bare boolean, because the
   * caller has to distinguish "refused" from "allowed but must ask first".
   */
  function can(settings, capability) {
    const s = sanitize(settings);
    if (!(capability in CAPABILITIES)) {
      // An undeclared capability is a programming error, and the safe reading of
      // an unknown permission is "no".
      return { allowed: false, needsConfirm: false, reason: `'${capability}' is not a declared capability` };
    }
    if (s.denied.indexOf(capability) !== -1) {
      return { allowed: false, needsConfirm: false, reason: `you turned off "${CAPABILITIES[capability].label}"` };
    }
    const granted = GRANTS[s.level].indexOf(capability) !== -1;
    if (!granted) {
      const meta = LEVEL_META[s.level];
      return {
        allowed: false,
        needsConfirm: false,
        reason: `"${CAPABILITIES[capability].label}" needs a higher trust level than ${meta.label}`,
      };
    }
    // At 'ask', every consequential act is confirmed - whether it writes or
    // merely reads outside the project. Two exceptions, both deliberate:
    //   - media.relay only carries a file the user already handed over, into a
    //     chat the user already opened; prompting for it is pure friction.
    //   - a capability sandbox already allows outright AND that only looks at
    //     something (browser.tabs.read, desktop.read, process.list) is not a new
    //     reach at all. "Looking is not the risk, acting is" - so it is not
    //     re-confirmed just because a higher level could act on it.
    // Everything ask ADDS over sandbox is new, and a new reach named in a
    // requirement is precisely what a prompt is for.
    const cap = CAPABILITIES[capability];
    const newAtLevel = GRANTS[LEVELS[0]].indexOf(capability) === -1;
    const justLooking = !cap.writes && GRANTS[LEVELS[0]].indexOf(capability) !== -1;
    const consequential = newAtLevel || cap.writes;
    const needsConfirm = s.level === "ask"
      && consequential
      && !justLooking
      && capability !== "media.relay";
    return { allowed: true, needsConfirm, reason: needsConfirm ? "allowed, but this level confirms each write or run" : "" };
  }

  /** Every capability's state at the current settings, for the UI to render. */
  function matrix(settings) {
    return Object.keys(CAPABILITIES).map((id) => {
      const r = can(settings, id);
      return {
        id,
        label: CAPABILITIES[id].label,
        writes: !!CAPABILITIES[id].writes,
        outsideProject: !!CAPABILITIES[id].outsideProject,
        allowed: r.allowed,
        needsConfirm: !!r.needsConfirm,
        reason: r.reason,
      };
    });
  }

  /**
   * The narrowest level that can PERFORM every capability in `grants` without
   * interrupting for confirmation.
   *
   * Note the subtlety this handles: 'ask' and 'full' grant the same SET of
   * capabilities - they differ only in whether consequential ones are confirmed.
   * Comparing grant sets alone would therefore always answer 'ask' for a full
   * request, which is wrong. So a caller naming a consequential capability is
   * asking to do it unconfirmed, and that requires 'full'.
   *
   * Returns the level id, or null when the request is not expressible.
   */
  /**
   * The lowest level that permits this set of grants at all.
   *
   * Note this answers "can it happen here", not "does it happen silently here".
   * A level that permits something by confirming it first still permits it - so
   * naming `fs.write.any` resolves to `ask`, not `full`. Use `matrix()` when you
   * need to show the user which acts would prompt; use `levelFor` when you only
   * need the floor.
   */
  function levelFor(grants) {
    const want = Array.isArray(grants) ? grants.filter((g) => g in CAPABILITIES) : [];
    if (!want.length) return LEVELS[0];
    for (const lvl of LEVELS) {
      if (want.every((g) => can({ level: lvl }, g).allowed)) return lvl;
    }
    return null;
  }

  function describe(raw) {
    const s = sanitize(raw);
    const meta = LEVEL_META[s.level];
    const rows = matrix(s);
    const on = rows.filter((r) => r.allowed && !r.needsConfirm).length;
    const ask = rows.filter((r) => r.allowed && r.needsConfirm).length;
    const off = rows.filter((r) => !r.allowed).length;
    return `${meta.label} - ${meta.tagline}. ${on} allowed outright, ${ask} confirmed each time, ${off} refused.`;
  }

  return {
    LEVELS, LEVEL_META, CAPABILITIES, HARD_LIMITS, GRANTS, DEFAULT_LEVEL,
    isLevel, sanitize, can, matrix, levelFor, describe,
  };
})();
