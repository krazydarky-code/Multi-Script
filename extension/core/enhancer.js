// SPDX-License-Identifier: GPL-3.0-or-later
//
// Auto prompt enhancer: turn a short, casual request into a precise brief the
// agent loop can actually execute against.
//
// ── Why this exists ──────────────────────────────────────────────────────
//
// The loop is driven by a plain-text JSON protocol. A vague user turn ("make me
// a sword" / "fix the lighting") forces the model to guess the DELIVERABLE, the
// ENGINE, the CONSTRAINTS and the DEFINITION OF DONE - and a guess made in the
// first turn propagates through every later turn. The most common real failure
// is not a bad model; it is a one-line request that never said what "done"
// means, so the loop produces something plausible and stops.
//
// The enhancer does NOT change the user's intent and does NOT invent
// requirements. It restates what the user already implied, makes the implicit
// explicit, and attaches the facts the agent needs but the user should not have
// to type (which engine is connected, which tools exist, what must be verified).
//
// ── Design rules ─────────────────────────────────────────────────────────
//
//   1. NEVER contradict the user. The original request is always preserved
//      verbatim inside the output. Enhancement is additive.
//   2. NEVER invent specifics. If the user did not say "low-poly", the
//      enhancer must not add a polygon budget. It may ask the model to CHOOSE
//      and state its choice, which is different and is honest.
//   3. Deterministic and offline. No network, no model call, no randomness.
//   4. Idempotent-ish: enhancing an already-enhanced prompt must not pile up
//      layers. Detected via the marker and skipped.
//   5. Cheap in tokens. The added text is capped; a 6-word request must not
//      turn into 900 tokens of ceremony.
const ZSEnhance = (() => {
  "use strict";

  // Recognisable in an already-enhanced prompt so a second pass is a no-op.
  const MARKER = "ENHANCED BRIEF";

  // ── Settings ────────────────────────────────────────────────────────────
  // `strength` controls how much is ADDED, never how much of the user survives.
  const LEVELS = {
    off: {
      id: "off", label: "Off",
      describe: "Send your request exactly as typed.",
      addGoal: false, addConstraints: false, addEngine: false, addDone: false,
      addFormat: false, maxExtra: 0,
    },
    light: {
      id: "light", label: "Light",
      describe: "Adds the goal and the definition of done. Nothing else.",
      addGoal: true, addConstraints: false, addEngine: false, addDone: true,
      addFormat: false, maxExtra: 700,
    },
    balanced: {
      id: "balanced", label: "Balanced",
      describe: "Goal, constraints, connected-engine facts and done-criteria.",
      addGoal: true, addConstraints: true, addEngine: true, addDone: true,
      // 6.27.1: raised from 1100 - the cap must fit this level's own full
      // section set, otherwise the smart-defaults are silently cut mid-list.
      addFormat: false, maxExtra: 1500,
    },
    thorough: {
      id: "thorough", label: "Thorough",
      describe: "Everything in Balanced, plus output format and verification.",
      addGoal: true, addConstraints: true, addEngine: true, addDone: true,
      // 6.27.1: raised from 1600 so the quality gate's last line and the
      // report-back section survive instead of being truncated away.
      addFormat: true, maxExtra: 2100,
    },
  };

  const DEFAULT_SETTINGS = {
    // Off by default: this rewrites the user's own words, so it is opt-in.
    mode: "off",
    // When you press Send, hold it and ask: improved prompt or original (never both).
    preview: true,
    // Per-engine extras the user can toggle independently of strength.
    injectEngineFacts: true,
    injectToolFacts: true,
    // Add a compact task-shaped execution strategy. This is provider-neutral:
    // it describes the work, never a model- or website-specific capability.
    injectApproach: true,
    // Keep the user's own wording at the top so nothing feels rewritten.
    keepOriginalFirst: true,
    // 6.28.1: opt-in Blender production tasks. When enabled, the brief also
    // tells the agent to produce the request's meshes/props as real Blender
    // assets and import them, instead of settling for engine primitives.
    // Off by default - it commits the run to a heavier asset pipeline.
    blenderAssist: false,
  };

  // Extra output budget granted on top of the level cap when Blender tasks
  // are enabled, so the asset section is never truncated mid-line.
  const BLENDER_BONUS = 800;

  function sanitize(raw) {
    const s = Object.assign({}, DEFAULT_SETTINGS, raw && typeof raw === "object" ? raw : {});
    if (!LEVELS[s.mode]) s.mode = DEFAULT_SETTINGS.mode;
    s.preview = !!s.preview;
    s.injectEngineFacts = !!s.injectEngineFacts;
    s.injectToolFacts = !!s.injectToolFacts;
    s.injectApproach = !!s.injectApproach;
    s.keepOriginalFirst = !!s.keepOriginalFirst;
    s.blenderAssist = !!s.blenderAssist;
    return s;
  }

  // ── Intent classification ───────────────────────────────────────────────
  // A small, transparent rule set. It does not try to be clever; it tries to be
  // right about the handful of distinctions that change what "done" means.
  // NOTE on the regexes: a trailing \b would break every stem ("optimis" would
  // not match "optimise", "lag" would not match "laggy"), so each alternative is
  // written as a PREFIX and only the leading \b is asserted. The trailing
  // boundary is deliberately omitted - a stem must match its inflections.
  const VERBS = [
    ["build", /\b(build|make|creat|add|generat|spawn|model|craft|construct|design|set ?up)/i],
    ["fix", /\b(fix|repair|debug|broken|not work|doesn'?t work|error|issue|crash|bug)/i],
    ["change", /\b(change|updat|modif|adjust|edit|tweak|renam|move|replac|swap)/i],
    ["explain", /\b(explain|what is|what'?s|how does|why|tell me about|describ)/i],
    ["find", /\b(find|search|locat|where is|list|show me)/i],
    ["review", /\b(review|audit|check|inspect|analys|analyz|evaluat|critiqu)/i],
    ["optimise", /\b(optimis|optimiz|speed up|faster|performance|lag|reduce|improve)/i],
    ["test", /\b(test|verif|validat|prove|confirm)/i],
    ["refactor", /\b(refactor|clean up|restructur|reorganis|reorganiz|tidy|rewrit)/i],
  ];

  function classifyIntent(text) {
    const hits = VERBS.filter(([, re]) => re.test(text)).map(([id]) => id);
    if (!hits.length) return "build"; // the loop's default assumption
    // Fix before build: "fix the sword I made" contains no build verb, but a
    // "make it stop crashing" contains both and is really a fix.
    const order = ["fix", "optimise", "refactor", "test", "review", "find", "explain", "change", "build"];
    for (const k of order) if (hits.includes(k)) return k;
    return hits[0];
  }

  // What "done" means, per intent. Phrased as an instruction to the model, not
  // as an assumption about the user's world.
  const DONE = {
    build: "The thing exists in the project, is reachable in the scene/tree, and its key properties were read back to confirm the values that were set.",
    fix: "The original failure no longer reproduces, and the evidence is a real read-back (console output, a fresh inspection) rather than a claim.",
    change: "The specific value/structure the user named is different now, and reading it back shows the new value.",
    explain: "The answer cites what is actually in the project (real paths, real values) rather than a generic description.",
    find: "The exact location(s) are named with full paths, and the search that found them is stated so it can be repeated.",
    review: "Each finding names a real location and says why it matters; nothing is reported that was not actually observed.",
    optimise: "The change is made and a before/after measurement is reported in the same units.",
    test: "The test is run and the actual pass/fail result is reported, including any failure output verbatim.",
    refactor: "Behaviour is unchanged and the structure is demonstrably cleaner; anything that could break was re-checked.",
  };

  // Constraints the user is likely to have meant but not typed.
  // Prefix convention, same as VERBS: leading \b only, no trailing \b (a stem
  // must match its inflections - "secur" needs to match "security").
  const CONSTRAINT_RULES = [
    [/\b(ui|gui|hud|menu|button|screen|interface)/i,
      "UI work: state the target resolution/device the layout must hold at, and check it on at least one other size."],
    [/\b(multiplayer|server|client|replicat|network|remote|sync|shared|player)/i,
      "Networking: say which side owns the authority, and never trust a client-supplied value on the server."],
    [/\b(save|data|database|datastore|persist|profile)/i,
      "Persistence: handle the failure path (no data, stale data, save error) explicitly, not just the happy path."],
    [/\b(mobile|phone|touch|controller|gamepad|console)/i,
      "Cross-input: the result must be usable without a mouse and keyboard, not merely not-crash."],
    [/\b(performance|fps|lag|optimis|optimiz|memory)/i,
      "Performance: measure before and after; do not claim an improvement that was not measured."],
    [/\b(animat|tween|motion|move|orbit|swing|bounce)/i,
      "Motion: say what drives it (frame time vs. fixed step) and confirm it looks right over a full cycle, not one frame."],
    [/\b(secur|exploit|hack|vulnerab|sanitiz|validat)/i,
      "Security: assume the input is hostile; validate on the authority side and say what happens on rejection."],
    // 6.28: audio is the most commonly forgotten layer entirely.
    [/\b(sound|audio|music|sfx|ambien)/i,
      "Audio: loops must be seamless, ambience mixed under UI and gameplay feedback, and volume/mute settings respected."],
    [/\b(scal|responsive|resiz)/i,
      "Scaling: the layout must hold from the smallest supported size to the largest, tested at both ends."],
    // 6.27.1: subjective quality words are the #1 source of disappointing
    // builds - the model is free to interpret "cool" as "nothing changes".
    [/\b(cool|awesome|epic|amazing|nicer?|prettier|beautiful|better looking|good looking|prettier|fancier)/i,
      "Subjective quality word detected: translate it into observable, checkable properties (what the player sees, hears or can do differently) before building, and state that translation once."],
  ];

  // Words that mean the user already gave us a hard number or a hard choice.
  // When one of these is present we do NOT ask the model to choose it.
  const SPECIFIC = /\b(\d+\s*(px|studs?|seconds?|ms|fps|%|x|by|units?)|#[0-9a-f]{3,8}|rgb\(|(red|green|blue|yellow|black|white|orange|purple|pink|grey|gray|brown|gold|silver)\b)/i;

  // Task domains change the safest useful approach, but not the user's requested
  // outcome. Multiple domains may match; that is intentional for full-stack work.
  const DOMAIN_RULES = [
    ["code", /\b(code|script|function|class|module|api|bug|refactor|compile|runtime|exception)/i,
      "Inspect the existing implementation and its callers before editing; make the smallest coherent change and run the nearest real validation."],
    ["ui", /\b(ui|ux|gui|hud|menu|button|screen|interface|layout|form|dialog|modal)/i,
      "Preserve the existing visual language, complete every interactive state, and verify keyboard, focus, resize and error behavior."],
    ["data", /\b(data|database|schema|migration|query|save|datastore|persist|cache)/i,
      "Inspect the live schema and existing data path first; preserve compatibility and verify both success and failure paths."],
    ["media", /\b(image|texture|video|audio|sound|music|animation|vfx|shader|material|mesh|model)/i,
      "Create or modify the real asset, integrate it at its use site, and validate it in the target runtime rather than stopping at an exported file."],
    ["world", /\b(scene|level|map|world|terrain|lighting|environment|camera)/i,
      "Inspect the current scene hierarchy and conventions first; integrate the change and validate it from the intended player or camera view."],
    // 6.27: gameplay was referenced by the weak-prompt defaults below but no
    // domain rule ever produced it, so "make me a game" never got the
    // playable-loop guidance. Keep the word list tight on purpose: it must not
    // fire on "score" or "player" alone (those are covered by networking).
    ["gameplay", /\b(game|gameplay|obby|tycoon|simulator|quest|dungeon|boss|enem|npc|puzzle|platformer|shooter|racer|spawn|collect|powerup|power-up|leaderboard|win condition)/i,
      "Build one complete playable loop first - entry, objective, interaction, feedback, success/failure and restart - and only then add secondary systems."],
    ["network", /\b(multiplayer|server|client|network|remote|replicat|sync|online)/i,
      "Keep authority explicit, validate untrusted input on the authority side, and test late-join, disconnect and retry behavior where relevant."],
    ["research", /\b(research|compare|investigat|source|citation|evidence|latest|current)/i,
      "Use authoritative sources, distinguish observed facts from inference, and attach evidence to each conclusion that depends on a source."],
  ];

  function classifyDomains(text) {
    return DOMAIN_RULES.filter(([, re]) => re.test(text)).map(([id]) => id);
  }

  function approachBlock(text, intent, enabled) {
    if (!enabled || intent === "explain" || intent === "find") return [];
    const lines = DOMAIN_RULES.filter(([, re]) => re.test(text)).map(([, , line]) => line);
    if (!lines.length && ["build", "change", "fix", "refactor", "optimise", "test"].includes(intent)) {
      lines.push("Inspect the current state before changing it, use the smallest sufficient tool sequence, then read the result back from the real target.");
    }
    const picked = lines.slice(0, 2);
    // 6.27.1: multi-discipline builds fail by doing everything at once. When
    // three or more domains match a build-type request, add the sequencing
    // rule that keeps the work ordered and each step checkable.
    if (lines.length >= 3 && ["build", "change", "refactor"].includes(intent)) {
      picked.push("Several disciplines are involved: sequence the work inspect → core system → integrate → present → verify, and keep each step independently checkable.");
    }
    return picked;
  }

  // ── Fact gathering ──────────────────────────────────────────────────────
  // Everything here is supplied by the caller from live state. Nothing is
  // invented; a missing fact means the line is omitted.
  function engineBlock(facts, settings) {
    const f = facts || {};
    const lines = [];
    if (f.engines && f.engines.length) {
      lines.push("Connected engin" + (f.engines.length === 1 ? "e" : "es") + ": " + f.engines.join(", ") + ".");
      lines.push("Use only that engine's real commands - never a command from a different engine.");
    } else if (f.enginesChecked) {
      lines.push("No engine is connected right now. If the task needs one, say so instead of writing code that cannot run.");
    }
    if (f.studioIds && f.studioIds.length) {
      lines.push("Known Studio id(s): " + f.studioIds.map((s) => JSON.stringify(s)).join(", ") +
        " - pass that exact value as studio_id on every place-scoped Roblox command.");
    }
    if (settings.injectToolFacts && f.toolCount) {
      lines.push("The live tool surface advertises " + f.toolCount + " command(s); confirm a command exists before using it.");
    }
    if (settings.injectToolFacts && Array.isArray(f.toolNames) && f.toolNames.length) {
      lines.push("Relevant live commands already discovered: " + f.toolNames.slice(0, 8).join(", ") + ".");
    }
    return lines;
  }

  function constraintBlock(text, settings) {
    if (!settings.addConstraints) return [];
    const out = [];
    if (!SPECIFIC.test(text)) {
      out.push("Where a measurable choice is required (a size, a count, a colour, a duration) and the request does not state one, pick a sensible value, state it, and keep it consistent for the whole task.");
    }
    for (const [re, line] of CONSTRAINT_RULES) {
      if (re.test(text)) out.push(line);
    }
    // Cap it. A pile of generic advice is worse than two relevant lines.
    return out.slice(0, 3);
  }

  // Short prompts need structure, not invented content. These defaults tell the
  // model HOW to make missing decisions safely while keeping WHAT to build owned
  // by the user's original words. They are deliberately reversible and
  // project-aware, so "make the UI better" can become excellent without the
  // enhancer silently choosing a visual style, price, size or architecture.
  function weakPromptBlock(text, intent, domains, level) {
    const words = text.trim().split(/\s+/).filter(Boolean);
    if (!level.addConstraints || (words.length >= 14 && text.length >= 100)) return [];
    const out = [
      "Inspect the existing project and preserve its established architecture, naming and visual language before choosing defaults.",
      "Where the request is silent, choose the smallest reversible default that completes the main user journey; state the choice once and keep it consistent - ask one short question only when a missing choice is irreversible or destructive.",
    ];
    if (domains.includes("ui")) {
      out.push("Complete the interaction states and responsive/focus behavior that make the requested UI usable; do not redesign unrelated screens.");
    } else if (domains.includes("gameplay") || domains.includes("world")) {
      out.push("Finish one playable vertical slice with entry, feedback, success/failure and restart instead of scattering unfinished systems.");
    } else if (intent === "fix") {
      out.push("Reproduce first, fix the narrowest root cause, then re-run the same reproduction plus one adjacent regression check.");
    } else {
      out.push("Finish the requested path end-to-end, including its nearest failure/recovery state, before adding optional extras.");
    }
    return out.slice(0, 3);
  }

  function qualityBlock(domains, level) {
    if (!level.addFormat) return [];
    const out = [
      "No placeholders, disconnected demos or success claims without native read-back.",
      "Fix correctness and usability failures before visual extras; then improve the weakest remaining quality dimension once.",
    ];
    if (domains.includes("ui")) out.push("Check contrast, focus visibility, touch target size, localization growth and reduced motion.");
    // 6.27: the flat-baseplate failure. World/gameplay builds must be judged
    // from the player's first view, not the editor's top view.
    if (domains.includes("world") || domains.includes("gameplay")) out.push("Compose the player's first view deliberately: terrain or height variation rather than one flat slab, one clear landmark, tuned lighting with sky and atmosphere or fog, and dressing that sells scale - then verify from the real player camera.");
    if (domains.includes("network") || domains.includes("data")) out.push("Exercise malformed input, authority, retry, disconnect and compatibility paths.");
    if (domains.includes("performance")) out.push("Set a target-tier budget and report a before/after measurement in the same units.");
    return out.slice(0, 3);
  }

  // 6.28.1: opt-in Blender asset-production tasks. Same honesty rules as the
  // rest of the enhancer: these lines describe HOW to use Blender for the
  // work the user already requested - they never invent an art direction, a
  // measurement or a colour. Skipped for pure question/lookup intents, where
  // commissioning assets would change what the user asked for.
  function blenderBlock(text, intent, domains, facts) {
    if (intent === "explain" || intent === "find") return [];
    const f = facts && typeof facts === "object" ? facts : {};
    const connected = Array.isArray(f.engines) && f.engines.includes("blender");
    const lines = [
      connected
        ? "Blender is connected: model the meshes and props this request needs as real Blender assets (clean construction, applied scale and rotation, sensible origins) instead of settling for plain engine primitives."
        : "Model the meshes and props this request needs as real Blender assets (clean construction, applied scale and rotation, sensible origins) instead of settling for plain engine primitives. Blender is not connected right now: connect it (Multi-Script Settings > Engines) before the asset work, or say why it was skipped.",
    ];
    if (domains.includes("world") || domains.includes("gameplay")) {
      lines.push("Assemble environments from a small modular kit built in Blender (walls, props, terrain dressing) so the world reads as constructed, not blocked out.");
    }
    if (domains.includes("media") || domains.includes("gameplay")) {
      lines.push("Keep every asset export-ready: consistent naming, intentional UVs, and materials that survive re-import.");
    }
    lines.push("Export each finished asset, import it into the target engine, and verify scale, orientation and placement from the intended player or camera view - fix problems in Blender, not with engine-side scale hacks.");
    return lines.slice(0, 4);
  }

  // ── The enhancer ────────────────────────────────────────────────────────
  //
  // enhance(text, facts, rawSettings) -> {
  //   text:      the string to send
  //   enhanced:  whether anything was added
  //   intent:    the classified intent
  //   added:     []string, the sections that were appended (for the preview UI)
  //   skipped:   reason when nothing was added
  // }
  function enhance(text, facts, rawSettings) {
    const original = String(text == null ? "" : text);
    const settings = sanitize(rawSettings);
    const level = LEVELS[settings.mode] || LEVELS.off;
    const trimmed = original.trim();

    if (!trimmed) return { text: original, enhanced: false, intent: "", added: [], skipped: "empty" };
    if (settings.mode === "off") return { text: original, enhanced: false, intent: "", added: [], skipped: "off" };
    if (trimmed.includes(MARKER)) {
      // Already enhanced. Do not stack a second brief on top of the first.
      return { text: original, enhanced: false, intent: "", added: [], skipped: "already-enhanced" };
    }
    // A long, already-structured request gains nothing from a rewrite and the
    // added ceremony would just dilute it.
    if (trimmed.length >= 1400) {
      return { text: original, enhanced: false, intent: "", added: [], skipped: "already-detailed" };
    }

    const intent = classifyIntent(trimmed);
    const domains = classifyDomains(trimmed);
    const f = facts && typeof facts === "object" ? facts : {};
    const sections = [];
    const added = [];

    if (level.addGoal) {
      sections.push("GOAL: " + trimmed);
      added.push("goal");
    }

    const approach = approachBlock(trimmed, intent, settings.injectApproach);
    if (approach.length) {
      sections.push("EXECUTION APPROACH:\n" + approach.map((c, i) => (i + 1) + ". " + c).join("\n"));
      added.push("approach");
    }

    const constraints = constraintBlock(trimmed, level);
    if (constraints.length) {
      sections.push("CONSTRAINTS:\n" + constraints.map((c) => "- " + c).join("\n"));
      added.push("constraints");
    }

    const smartDefaults = weakPromptBlock(trimmed, intent, domains, level);
    if (smartDefaults.length) {
      sections.push("SAFE SMART DEFAULTS:\n" + smartDefaults.map((c) => "- " + c).join("\n"));
      added.push("smart-defaults");
    }

    if (level.addEngine && settings.injectEngineFacts) {
      const eng = engineBlock(f, settings);
      if (eng.length) {
        sections.push("ENVIRONMENT:\n" + eng.map((c) => "- " + c).join("\n"));
        added.push("environment");
      }
    }

    if (settings.blenderAssist) {
      const bl = blenderBlock(trimmed, intent, domains, f);
      if (bl.length) {
        sections.push("BLENDER ASSET TASKS:\n" + bl.map((c) => "- " + c).join("\n"));
        added.push("blender");
      }
    }

    if (level.addDone) {
      const done = DONE[intent];
      if (done) {
        sections.push("DONE MEANS: " + done);
        added.push("done");
      }
    }

    const quality = qualityBlock(domains, level);
    if (quality.length) {
      sections.push("QUALITY GATE:\n" + quality.map((c) => "- " + c).join("\n"));
      added.push("quality-gate");
    }

    if (level.addFormat && settings.addFormat !== false) {
      sections.push("REPORT BACK: what you changed (with real paths), what you verified and how, and anything you could not do - in that order, briefly.");
      added.push("report");
    }

    if (!added.length) {
      return { text: original, enhanced: false, intent, added: [], skipped: "nothing-to-add" };
    }

    let body = MARKER + "\n" + sections.join("\n\n");
    // Hard ceiling on the added text, measured on the addition only so a long
    // original is never truncated by the enhancer. The opt-in Blender section
    // gets its own bonus budget so it is never cut off mid-task.
    const cap = level.maxExtra + (settings.blenderAssist ? BLENDER_BONUS : 0);
    if (body.length > cap) {
      body = body.slice(0, cap).replace(/\n[^\n]*$/, "");
    }

    // The user's own words stay visible and stay first. The brief is READ as an
    // expansion of them, not as a replacement.
    const text2 = settings.keepOriginalFirst
      ? trimmed + "\n\n---\n" + body
      : body + "\n\n---\n" + trimmed;

    return {
      text: text2, enhanced: true, intent, domains, added, skipped: "",
      requestProfile: {
        weak: trimmed.split(/\s+/).filter(Boolean).length < 8 || trimmed.length < 48,
        hasSpecifics: SPECIFIC.test(trimmed),
        engineKnown: !!(f.engines && f.engines.length),
      },
    };
  }

  // A short, honest one-liner for the settings panel and diagnostics.
  function describe(rawSettings) {
    const s = sanitize(rawSettings);
    const level = LEVELS[s.mode] || LEVELS.off;
    if (s.mode === "off") return "Off - requests are sent exactly as typed.";
    return level.label + " - " + level.describe + (s.blenderAssist ? " Blender asset tasks are added on top." : "") + (s.preview ? " You review each one before it sends: you are asked whether to send the improved prompt or your original, and only one is sent." : " Sends automatically - the improved prompt is sent instead of your original.");
  }

  return {
    MARKER, LEVELS, DEFAULT_SETTINGS, BLENDER_BONUS,
    sanitize, classifyIntent, classifyDomains, enhance, describe,
    // Exposed for tests and for the panel's live preview.
    DONE, CONSTRAINT_RULES, DOMAIN_RULES, blenderBlock,
  };
})();
