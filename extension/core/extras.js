// SPDX-License-Identifier: GPL-3.0-or-later
// core/extras.js - provider-agnostic extras added in 6.26.0:
//   * Game Idea Bot      - an offline, engine-aware generator that writes a
//                          ready-to-paste build prompt (no network, no AI call).
//   * Software Builder   - the W.I.P. prompt contract for engine-free sessions
//                          that build real programs through the local bridge.
//   * Theme metadata     - the extra stylised / animated themes and the custom
//                          background-image settings sanitizer.
// Pure logic only: no DOM queries, no site names. core/main.js owns the UI.
// eslint-disable-next-line no-unused-vars
const ZSExtras = (() => {
  "use strict";

  // ── Seeded RNG so "Regenerate" is random but a seed reproduces an idea ──
  function rng(seed) {
    let h = 1779033703 ^ String(seed).length;
    for (const ch of String(seed)) { h = Math.imul(h ^ ch.charCodeAt(0), 3432918353); h = (h << 13) | (h >>> 19); }
    return () => { h = Math.imul(h ^ (h >>> 16), 2246822507); h = Math.imul(h ^ (h >>> 13), 3266489909); h ^= h >>> 16; return (h >>> 0) / 4294967296; };
  }
  const pick = (r, a) => a[Math.floor(r() * a.length)];
  const pickN = (r, a, n) => { const c = [...a], out = []; while (c.length && out.length < n) out.push(c.splice(Math.floor(r() * c.length), 1)[0]); return out; };

  // ── Content pools ─────────────────────────────────────────────────────
  const GENRES = {
    any: "Any genre",
    platformer: "Platformer", obby: "Obstacle course (obby)", tycoon: "Tycoon / idle", simulator: "Simulator",
    horror: "Horror", roguelike: "Roguelike", survival: "Survival / crafting", shooter: "Shooter",
    puzzle: "Puzzle", racing: "Racing", towerdefense: "Tower defense", rpg: "RPG", fighting: "Fighting",
    stealth: "Stealth", rhythm: "Rhythm", sandbox: "Sandbox / building", party: "Party / minigames",
  };
  const SCOPES = {
    jam: { label: "Game-jam weekend", time: "a 48-hour jam", content: "one polished level / arena, 1 core mechanic, 1 twist" },
    slice: { label: "Vertical slice", time: "about two weeks", content: "one complete loop with 3 areas or waves, progression and a boss or finale" },
    full: { label: "Full release", time: "a multi-month project", content: "3+ biomes or chapters, meta-progression, save data, settings, onboarding and live-ops hooks" },
  };
  const SETTINGS = ["a floating archipelago held together by old chains", "a flooded shopping mall at night", "the inside of a giant clockwork whale",
    "a cozy village built on a sleeping dragon", "a neon city where rain is currency", "an abandoned research station on a frozen moon",
    "a candy factory that went rogue", "a haunted lighthouse that moves between islands", "a desert of glass dunes and buried robots",
    "a jungle that regrows every night", "a miniature world on a kitchen table", "a sky-high skyscraper construction site",
    "a carnival that only opens during eclipses", "a library where books are doors", "a volcanic forge city", "a post-apocalyptic suburb overrun by plants", "a night market built inside a beached leviathan", "a hotel where every floor is a different decade", "a mushroom metropolis under a fallen tree", "a train that never stops circling a sleeping city"];
  const HOOKS = ["time rewinds by 5 seconds whenever you take damage", "gravity flips each time you jump", "every enemy you defeat becomes a tool you can place",
    "the level is rebuilt from what other players left behind", "light is your health bar", "you can only see what your companion's lantern lights up",
    "sound attracts everything - silence is your weapon", "you shrink every time you collect a coin", "the map rotates 90° every minute",
    "each room remembers how you solved it last time", "your shadow is a second playable character", "weather changes the physics",
    "you build the track while you race on it", "trading items with NPCs reshapes the world", "the floor is a rhythm grid that pulses with the music",
    "you control two characters with mirrored inputs", "the boss learns from your last attempt", "your score is a living pet that grows or withers", "doors only exist while someone is looking at them", "your inventory is a physical backpack you can drop", "every respawn swaps one world rule", "the music is the minimap - melodies point the way"];
  const LOOPS = {
    platformer: "run → jump → collect → reach checkpoint → unlock new movement",
    obby: "attempt stage → fail fast → retry → checkpoint → stage-skip & cosmetics",
    tycoon: "earn → buy droppers/upgrades → automate → rebirth for multipliers",
    simulator: "gather → sell → upgrade tool/backpack → unlock zone → rebirth",
    horror: "explore → find key item → evade threat → solve escape puzzle",
    roguelike: "enter run → fight rooms → pick upgrades → die or win → unlock meta perks",
    survival: "gather → craft → build shelter → survive night event → expand",
    shooter: "spawn → fight → earn score/loot → upgrade loadout → next wave/match",
    puzzle: "read room → experiment → solve → unlock harder rule combo",
    racing: "race → earn currency → tune vehicle → unlock tracks/leagues",
    towerdefense: "place towers → survive wave → earn → upgrade/merge → boss wave",
    rpg: "quest → explore → fight → loot → level up → story beat",
    fighting: "pick fighter → duel → learn combos → rank up → unlock fighters",
    stealth: "scout → plan route → infiltrate → steal objective → escape",
    rhythm: "hit notes on beat → build combo → unlock songs → master difficulty",
    sandbox: "gather materials → build freely → share creation → earn likes/unlocks",
    party: "vote minigame → play 60s round → earn points → crown winner",
  };
  const ART = ["low-poly with soft gradients", "chunky voxel", "cel-shaded with bold outlines", "realistic PBR with moody lighting",
    "pastel toy-like plastic", "retro PS1 with vertex jitter", "hand-painted storybook", "neon synthwave with bloom", "monochrome with one accent colour",
    "papercraft / cardboard diorama", "pixel art with dynamic lighting", "claymation with fingerprint smudges", "ink-wash with splashes of gold", "isometric diorama with tilt-shift depth", "embroidered patchwork with stitched outlines"];
  const AUDIO = ["lo-fi beats that react to the action", "orchestral swells on milestones", "chiptune with layered stems", "ambient drones and sharp Foley",
    "funky bass-heavy grooves", "silence broken by spatial creature sounds"];
  const MONET = ["cosmetic trails & skins only (no pay-to-win)", "battle-pass style seasonal cosmetics", "one-time premium unlock", "optional supporter pack with cosmetics"];
  // 6.28.0: proper ideation pools. The brief previously randomised a fixed
  // skeleton, so every idea read the same. These pools let the generator
  // compose an actual premise: protagonist + threat + signature action fused
  // with the setting and hook, plus combinatorial titles.
  const PROTAGONISTS = ["a courier with a cursed compass", "the last lighthouse keeper", "a swarm of polite drones sharing one mind",
    "a gardener who plants doors", "a retired monster hired as a bouncer", "a cartographer mapping places that move",
    "a ghost who pays rent by haunting", "a kid with a walkie-talkie that reaches yesterday", "a chef cooking for creatures that eat sounds",
    "a beekeeper herding storm clouds", "a plumber for a city's dream-pipes", "a knight whose armour is alive and opinionated", "a translator for a city's arguing statues", "a fireworks smith in a town that banned light", "a taxi driver for migrating castles", "a librarian reshelving borrowed memories"];
  const THREATS = ["the tide is erasing places nobody photographs", "something is buying up all the echoes", "the night shift never clocked out",
    "the map is slowly filling with someone else's memories", "every door now leads somewhere slightly worse", "the weather has started hunting specific people",
    "the town's reflections are unionising", "a quiet signal is teaching machines to dream", "the sun keeps arriving one minute later",
    "the lost-and-found has begun claiming people back", "an old debt is collecting itself in daylight", "the border between play and not-play is thinning", "the stars are being switched off one by one", "yesterday is arriving early and unfinished", "the rivers have started flowing uphill", "every mirror shows the room five minutes from now"];
  const SIGNATURE_ACTIONS = ["grapple and swing", "rewind single objects", "paint surfaces into physics", "possess machinery",
    "whistle commands to a loyal swarm", "fold space along drawn lines", "bargain with animated objects", "surf rails of light",
    "transmute held items once per room", "freeze time for whatever you touch", "conduct the environment like an orchestra", "dig through layers of the same place", "swap places with anything you throw", "grow plants into living platforms", "record and replay your own shadow", "charge objects with borrowed weather"];
  const ECONOMIES = ["two currencies: one earned by skill, one by kindness", "a barter web where every NPC values different junk",
    "upgrades that are visible places in the world, not menu rows", "a risk vault: bank your run's winnings or carry them and lose double",
    "scrap that remembers what it used to be", "favours that compound across sessions", "no shop: everything is crafted from what the world drops",
    "a living market whose prices follow player behaviour", "memories as currency - spend them and lose the tutorial they held", "a reputation web where factions trade in promises, not coins"];
  const TITLE_PATTERNS = [
    (r) => `${pick(r, ["Last", "Tiny", "Neon", "Hollow", "Clockwork", "Lucky", "Broken", "Endless", "Secret", "Wild", "Silent", "Stellar"])} ${pick(r, ["Lantern", "Tide", "Circuit", "Garden", "Signal", "Crown", "Engine", "Echo", "Harbor", "Orbit", "Vault", "Hive"])}`,
    (r) => `${pick(r, ["The", "A"])} ${pick(r, ["Singing", "Drowning", "Wandering", "Borrowed", "Electric", "Paper", "Hungering", "Floating"])} ${pick(r, ["City", "Forest", "Machine", "Sea", "Market", "Library", "Mountain", "Station"])}`,
    (r) => `${pick(r, ["Echo", "Salt", "Rust", "Bloom", "Static", "Honey", "Ash", "Glass"])} ${pick(r, ["&", "and"])} ${pick(r, ["Ember", "Thunder", "Ivy", "Smoke", "Gold", "Frost", "Static", "Rain"])}`,
    (r) => `${pick(r, ["Don't", "Never", "Always", "Please"])} ${pick(r, ["Feed", "Trust", "Follow", "Wake", "Water", "Answer"])} the ${pick(r, ["Lighthouse", "Garden", "Machine", "Tide", "Archive", "Choir", "Bridge", "Furnace"])}`,
  ];
  const FANTASIES = [
    "master a risky movement skill and visibly improve each run",
    "turn a fragile outpost into a thriving machine",
    "outsmart a world that changes its rules around you",
    "coordinate distinct roles so a team succeeds together",
    "discover secrets that permanently change how the world is understood",
    "build a personal collection that changes moment-to-moment strategy",
  ];
  const DIFFERENTIATORS = [
    "the signature mechanic changes traversal, combat and progression instead of appearing in one scripted room",
    "every upgrade creates a visible new option, not only a larger number",
    "the environment communicates rules through shape, light, sound and motion before text",
    "failures resolve quickly into an informed retry with a changed decision",
    "players can express a personal style without buying power",
    "the first minute contains a safe version of the same decision the finale tests under pressure",
  ];
  const ACCESSIBILITY = [
    "full remapping, controller focus, touch-safe targets and prompts that follow the active input",
    "contrast-safe critical information, scalable text and no color-only state",
    "captions/subtitles, separate music/SFX controls and visual equivalents for essential audio",
    "reduced motion/camera shake plus hold/toggle and timing assists that never remove core agency",
  ];

  // Engine-specific craft notes. Blender is NOT a game engine, so it gets an
  // asset/scene brief instead of a game.
  const ENGINE_NOTES = {
    roblox: {
      name: "Roblox Studio",
      tech: ["Luau with strict type annotations; ModuleScripts in ReplicatedStorage for shared logic, server logic in ServerScriptService",
        "server-authoritative gameplay with validated RemoteEvents/RemoteFunctions (never trust the client)",
        "DataStoreService with session locking + retry/backoff for saves; ProfileService-style structure",
        "mobile, console and PC input via ContextActionService, UI built with ScreenGui + UIScale/UIAspectRatioConstraint",
        "StreamingEnabled-friendly world layout, CollectionService tags for interactive parts, TweenService for juice"],
      verify: "playtest in Studio (Play + Run), read the Output console for errors, test with 2 players in a local server",
      genres: ["obby", "tycoon", "simulator", "horror", "towerdefense", "fighting", "party", "sandbox", "roguelike", "survival"],
    },
    unity: {
      name: "Unity",
      tech: ["C# with assembly definitions; ScriptableObjects for data (weapons, enemies, waves)",
        "new Input System with rebindable actions, Cinemachine cameras, URP with a post-processing volume",
        "prefabs + object pooling for spawned things, an event bus for decoupled systems",
        "save system with JSON + versioning, scene loading with an additive bootstrap scene",
        "Play Mode tests for the core loop, Profiler pass on target hardware"],
      verify: "enter Play Mode, check the Console for errors/warnings, run Edit/Play Mode tests, capture the Game view",
      genres: ["shooter", "platformer", "roguelike", "survival", "racing", "rpg", "horror", "stealth", "puzzle", "rhythm"],
    },
    godot: {
      name: "Godot 4",
      tech: ["GDScript 2.0 with static typing; small reusable scenes composed into levels",
        "signals for decoupling, Autoload singletons only for truly global state (GameState, Audio, Save)",
        "CharacterBody2D/3D movement with coyote time + jump buffering, AnimationPlayer/AnimationTree for states",
        "Resources (.tres) for data-driven items/enemies, TileMapLayer or GridMap for level building",
        "InputMap actions for keyboard + gamepad, a Theme resource for consistent UI"],
      verify: "run the project, read the debugger output for errors, exercise the loop, then stop the project cleanly",
      genres: ["platformer", "puzzle", "roguelike", "rpg", "towerdefense", "stealth", "rhythm", "survival", "racing", "party"],
    },
    generic: {
      name: "any engine (engine-free design brief)",
      tech: ["clean separation of data, game logic and presentation", "a state machine for game flow (menu → play → pause → win/lose → restart)",
        "data-driven content tables", "save/load with versioned data", "rebindable input with keyboard, mouse and gamepad"],
      verify: "write a test plan for the core loop and a 5-minute playtest script",
      genres: Object.keys(LOOPS),
    },
  };

  const BLENDER_KINDS = [
    { kind: "hero prop", items: ["an ornate steampunk lantern", "a sci-fi cargo crate with hazard decals", "a fantasy sword with runic engravings", "a retro arcade cabinet", "a cozy wooden market cart"] },
    { kind: "character", items: ["a chunky robot mascot", "a mushroom knight", "a stylised fox adventurer", "a deep-sea diver with a glowing helmet", "a tiny golem made of bricks"] },
    { kind: "environment kit", items: ["a modular dungeon wall/floor/door kit", "a modular sci-fi corridor kit", "a low-poly forest kit (trees, rocks, bushes)", "a medieval village house kit", "a neon street-food stall kit"] },
    { kind: "animated scene", items: ["a looping campfire night scene", "a rotating product turntable of a gadget", "a little robot waving hello", "a floating island with waterfalls", "a rainy window with a cat"] },
  ];

  function engineKey(engines) {
    const list = (Array.isArray(engines) ? engines : [engines]).filter(Boolean).map(String);
    for (const k of ["roblox", "unity", "godot"]) if (list.includes(k)) return k;
    if (list.includes("blender")) return "blender";
    return "generic";
  }

  // 6.28.0: anti-repetition for casual use. Seeded runs stay perfectly
  // deterministic (regenerate-from-seed is a feature); unseeded "Generate"
  // clicks skip whatever the last few clicks produced, so the button feels
  // like it is actually generating ideas instead of reshuffling one template.
  const _recent = new Map();
  const pickFresh = (r, arr, key, seeded) => {
    if (seeded || arr.length < 4) return pick(r, arr);
    const seen = _recent.get(key) || [];
    const fresh = arr.filter((x) => !seen.includes(x));
    const v = pick(r, fresh.length ? fresh : arr);
    seen.push(v); while (seen.length > Math.min(4, arr.length - 2)) seen.shift();
    _recent.set(key, seen);
    return v;
  };

  function gameIdea(opts = {}) {
    const seeded = !!opts.seed;
    const seed = opts.seed || `${Date.now()}-${Math.random()}`;
    const r = rng(seed);
    const engines = Array.isArray(opts.engines) ? opts.engines : [];
    const chosen = opts.engine && opts.engine !== "auto" ? opts.engine : engineKey(engines);
    // 6.28.1: `blender` is a user-facing option in the ideas panel. Enabling
    // it enlarges the brief with a concrete Blender asset plan (models built
    // in Blender, then imported) even when Blender is not currently connected.
    const wantBlender = opts.blender === true;
    const withBlender = chosen !== "blender" && (engines.includes("blender") || wantBlender);
    if (chosen === "blender") return blenderIdea(r, seed, opts);
    const E = ENGINE_NOTES[chosen] || ENGINE_NOTES.generic;
    const genre = opts.genre && opts.genre !== "any" && LOOPS[opts.genre] ? opts.genre : pick(r, E.genres);
    const scope = SCOPES[opts.scope] || SCOPES.slice;
    const setting = pickFresh(r, SETTINGS, "setting", seeded), hook = pickFresh(r, HOOKS, "hook", seeded);
    const art = pick(r, ART), audio = pick(r, AUDIO);
    const protagonist = pickFresh(r, PROTAGONISTS, "protagonist", seeded);
    const threat = pickFresh(r, THREATS, "threat", seeded);
    const action = pickFresh(r, SIGNATURE_ACTIONS, "action", seeded);
    const economy = pick(r, ECONOMIES);
    const title = pick(r, TITLE_PATTERNS)(r);
    const tech = pickN(r, E.tech, 4);
    const fantasy = pick(r, FANTASIES);
    const differentiator = pick(r, DIFFERENTIATORS);
    const access = pickN(r, ACCESSIBILITY, 2);
    const pillars = [
      `Readable mastery: ${fantasy}.`,
      `Systemic identity: ${differentiator}.`,
      "Finish before breadth: every included system must support the playable loop and its feedback.",
    ];
    const twist = opts.twist === false ? "" : pick(r, ["a co-op mode where two players share one ability set", "a daily seeded challenge with a leaderboard",
      "a photo mode that saves shareable postcards", "a speedrun timer with ghost replays", "an accessibility-first difficulty slider (assist mode)",
      "an in-world tutorial with no text popups", "a dynamic soundtrack that layers per combo"]);
    // Concrete Blender production tasks derived from THIS idea's own content,
    // so enabling the option visibly enlarges and grounds the prompt.
    const blenderPlan = wantBlender && chosen !== "blender" ? [
      `Model the hero subject (${protagonist}) in Blender as a game-ready asset: clean topology, applied transforms, origin at the base.`,
      `Build a modular environment kit for ${setting} - pieces that snap together, so areas are assembled from reusable parts instead of hand-placed one by one.`,
      `Model the signature-action prop and its key visual states (the player should ${action} with something that reads at a glance).`,
      `Export glTF/FBX from Blender, import into ${E.name}, and verify scale, orientation, materials and pivots after re-import - fix problems in Blender, not with engine-side scale hacks.`,
      `Render one neutral-light preview of each finished asset for the review pass.`,
    ] : null;
    const prompt = [
      `Build "${title}" - a ${GENRES[genre] || genre} game in ${E.name}${chosen === "generic" ? "" : " using the connected Multi-Script tools"}.`,
      ``,
      `PREMISE: you are ${protagonist}, in ${setting} - and ${threat}. You survive and progress by learning to ${action}.`,
      `PITCH: set in ${setting}. Signature hook: ${hook}. The hook is not a gimmick: it reshapes how every stage of the loop is played.`,
      `SIGNATURE ACTION: ${action} - teach it in the first minute, then keep deepening it instead of adding unrelated verbs.`,
      `PLAYER FANTASY: ${fantasy}.`,
      `CORE LOOP: ${LOOPS[genre]} - with the signature hook changing the decision at each stage.`,
      `PROGRESSION & ECONOMY: ${economy}.`,
      `SCOPE: ${scope.label} (${scope.time}) - ${scope.content}.`,
      `DESIGN PILLARS:`,
      ...pillars.map((x) => `- ${x}`),
      `LOOK & FEEL: ${art} art, ${audio}, juicy feedback on every action (hit-stop, particles, camera shake, sound).`,
      twist ? `EXTRA: ${twist}.` : null,
      `MONETISATION (if any): ${pick(r, MONET)}.`,
      ``,
      `FIRST 10 MINUTES:`,
      `- 0-60s: teach the signature action safely through the world, not a wall of text.`,
      `- 1-5m: combine it with one clear obstacle/enemy and give a meaningful first reward.`,
      `- 5-10m: present a choice that changes the next attempt, then deliver a small climax and a reason to return.`,
      ``,
      `SYSTEMS & CONTENT:`,
      `- A state-driven game flow (boot → menu → onboarding → play → result → retry/continue).`,
      `- Data-driven tuning for rewards, difficulty and content; save versioning with a safe failure path.`,
      `- One authored vertical slice first; reuse modular pieces for later breadth.`,
      `- Instrument the onboarding completion, first failure, first reward and session-end reason.`,
      ``,
      blenderPlan ? `BLENDER ASSET PLAN (models generated in Blender):` : null,
      ...(blenderPlan ? blenderPlan.map((x) => `- ${x}`) : []),
      blenderPlan ? `` : null,
      `TECH (${E.name}):`,
      ...tech.map((t) => `- ${t}`),
      withBlender ? `- author hero meshes in the connected Blender (clean topology, UVs, PBR textures), export glTF/FBX and import into ${E.name}` : null,
      ``,
      `UX & ACCESSIBILITY:`,
      ...access.map((x) => `- ${x}.`),
      `- Main menu, pause/settings, clear objective feedback, win/lose + restart, save status, and responsive safe-area-aware UI.`,
      ``,
      `SCOPE CONTROL: if time slips, cut extra content, cosmetics and secondary progression in that order. Never cut the complete core loop, onboarding, required feedback, save safety or verification.`,
      ``,
      `ACCEPTANCE TESTS:`,
      `- A new player can understand the goal and perform the signature action within 60 seconds without external explanation.`,
      `- The loop is playable from entry to result and immediate retry with no dead end or manual editor step.`,
      `- Keyboard/mouse plus the primary alternate input complete the critical path; smallest supported screen remains readable.`,
      `- Save/load, pause/resume and one forced failure/recovery path behave predictably.`,
      `- ${E.verify}; capture concrete logs/read-back and one representative image.`,
      `DONE WHEN: every acceptance test above passes in the real project, the weakest quality issue has been fixed, and remaining limitations are stated honestly.`,
    ].filter((x) => x !== null).join("\n");
    return {
      title, engine: chosen, genre, scope: opts.scope || "slice", seed: String(seed), prompt,
      concept: { setting, hook, fantasy, differentiator, pillars, art, audio },
      production: { acceptanceTests: 5, scopeCutOrder: ["extra content", "cosmetics", "secondary progression"], blenderAssetPlan: blenderPlan ? blenderPlan.length : 0 },
    };
  }

  function blenderIdea(r, seed, opts) {
    const k = pick(r, BLENDER_KINDS), item = pick(r, k.items), art = pick(r, ART);
    const target = pick(r, ["Roblox (MeshPart, ≤10k tris, 1024² textures)", "Unity URP (FBX, LOD0-2)", "Godot 4 (glTF 2.0)", "a portfolio render (Cycles)"]);
    const title = item.replace(/^an? /, "").replace(/\b\w/g, (c) => c.toUpperCase());
    const prompt = [
      `Blender is a 3D creation tool, not a game engine - so here is an ASSET brief, not a game.`,
      ``,
      `Create ${item} as ${/^[aeiou]/.test(k.kind) ? "an" : "a"} ${k.kind} in Blender using the connected Multi-Script tools.`,
      `STYLE: ${art}. Silhouette must read clearly at thumbnail size.`,
      `TARGET: ${target}.`,
      `FORM: choose primitives per feature (cylinders for shafts/limbs, beveled boxes for panels, swept curves for cables) - run ms_form_guidance audit before modelling.`,
      `TOPOLOGY: clean quads where it deforms, sensible triangle budget, applied scale/rotation, origin at the base.`,
      `UV + MATERIALS: non-overlapping UVs (or trim sheet), PBR material (base colour, roughness, metallic, normal), consistent texel density.`,
      k.kind === "character" ? `RIG: simple armature with weight paint, plus an idle and a wave animation (looping, 24 fps).` : null,
      k.kind === "animated scene" ? `ANIMATION: a seamless 4-8 second loop, three-point lighting, camera with depth of field, render a preview frame.` : null,
      k.kind === "environment kit" ? `KIT RULES: pieces snap on a 1 m / 4-stud grid, shared materials, 6-10 pieces that combine into a full room or street.` : null,
      ``,
      `PRODUCTION WORKFLOW: reference → silhouette blockout → proportion review → clean construction → UV/material pass → target-engine validation → presentation.`,
      `QUALITY GATES: silhouette reads at thumbnail size; scale/transforms/origin are correct; normals and deformation topology are clean; UVs and texel density are intentional; materials remain readable under neutral light; names and collections are export-safe.`,
      `SCOPE CONTROL: finish one hero-quality asset/kit before variants. If time slips, cut secondary accessories and presentation flourishes before topology, UVs, target validation or export integrity.`,
      `DONE WHEN: capture a viewport and a neutral-light preview, report dimensions/tri count/materials, validate the exported file after re-import, and disclose any remaining target-engine limitation.`,
    ].filter((x) => x !== null).join("\n");
    return {
      title, engine: "blender", genre: k.kind, scope: opts.scope || "slice", seed: String(seed), prompt,
      concept: { kind: k.kind, item, art, target },
      production: { stages: 7, reimportRequired: true },
    };
  }

  // ── Software Builder (W.I.P.) ─────────────────────────────────────────
  // 6.36: two modes share the workspace tools - "build" (new software) and
  // "code" (a general coding agent on any local folder) - plus opt-in add-ons.
  const SOFTWARE_DEFAULTS = { enabled: false, allowRun: false, rootMode: "ask", root: "", projectsDir: "", mode: "build",
    addons: { skills: true, engines: false, mcp: false } };
  function sanitizeSoftware(raw) {
    const s = { ...SOFTWARE_DEFAULTS, addons: { ...SOFTWARE_DEFAULTS.addons } }, src = raw && typeof raw === "object" ? raw : {};
    s.enabled = src.enabled === true;
    s.allowRun = src.allowRun === true;
    s.rootMode = ["ask", "path", "create"].includes(src.rootMode) ? src.rootMode : "ask";
    s.root = typeof src.root === "string" ? src.root.trim().slice(0, 400) : "";
    s.projectsDir = typeof src.projectsDir === "string" ? src.projectsDir.trim().slice(0, 400) : "";
    s.mode = src.mode === "code" ? "code" : "build";
    const ad = src.addons && typeof src.addons === "object" ? src.addons : {};
    for (const k of Object.keys(s.addons)) if (typeof ad[k] === "boolean") s.addons[k] = ad[k];
    return s;
  }
  const WS_TOOLS = [
    ["ms_ws_status", "{}", "root, mode, toolchains, git state, project recipes - call first"],
    ["ms_ws_pick_folder", '{"title":"Choose a folder"}', "native folder picker on the user's PC"],
    ["ms_ws_create_project", '{"name":"My App","template":"python-gui"}', "new folder + template (empty, python-cli, python-gui, node-cli, web-static, electron-app, csharp-console, cpp-cmake, rust-cli, go-cli, pygame-game)"],
    ["ms_ws_tree", '{"path":".","depth":4}', "list files"],
    ["ms_ws_glob", '{"pattern":"src/**/*.ts"}', "find files by pattern"],
    ["ms_ws_read", '{"path":"src/main.py","start_line":1,"end_line":200}', "line-numbered read"],
    ["ms_ws_read_many", '{"paths":["a.py","b.py"]}', "read related files together"],
    ["ms_ws_outline", '{"path":"src/main.py"}', "classes/functions with line numbers"],
    ["ms_ws_search", '{"query":"TODO","glob":"*.py","context":1}', "grep the project"],
    ["ms_ws_write", '{"path":"src/main.py","content":"...","mode":"overwrite"}', "write a whole file (new files)"],
    ["ms_ws_edit", '{"path":"src/main.py","edits":[{"old_string":"exact old","new_string":"new"}]}', "targeted edits; or {start_line,end_line,new_string}; dry_run for a diff"],
    ["ms_ws_patch", '{"patch":"--- a/x.py\\n+++ b/x.py\\n@@ ...","dry_run":true}', "apply a unified diff (multi-file)"],
    ["ms_ws_replace", '{"query":"oldName","replacement":"newName","glob":"*.ts","dry_run":true}', "project-wide rename"],
    ["ms_ws_move", '{"from_path":"a.txt","to_path":"docs/a.txt"}', "move/rename"],
    ["ms_ws_delete", '{"path":"old.txt","confirm":true}', "delete (never the root)"],
    ["ms_ws_undo", '{"steps":1}', "revert your last file changes"],
    ["ms_ws_diff", "{}", "what changed (git diff or undo journal)"],
    ["ms_ws_git", '{"action":"status|diff|log|add|commit","message":"..."}', "git"],
    ["ms_ws_build", '{"step":"detect|install|build|test|run|package|lint|format|typecheck"}', "auto-detected recipes"],
    ["ms_ws_check", "{}", "typecheck + lint + test in one call - run before saying done"],
    ["ms_ws_run", '{"command":"npm test","timeout_s":180}', "run a command (background:true for servers/GUIs)"],
    ["ms_ws_process", '{"action":"list|output|stop","id":"p123"}', "background processes"],
    ["ms_ws_http", '{"url":"http://localhost:3000/api"}', "test a local server"],
    ["ms_ws_plan", '{"action":"set","items":[{"text":"step 1"}]}', "visible task plan"],
    ["ms_ws_snapshot", '{"action":"create|list|restore","label":"before-refactor"}', "zip backups"],
    ["ms_ws_package_zip", '{"name":"MyApp"}', "zip the source into dist/"],
  ];
  const WS_TOOL_NAMES = new Set(WS_TOOLS.map((t) => t[0]).concat(["ms_ws_configure"]));
  const ENGINE_NAME_RX = /(^|_)(roblox|studio|unity|godot|blender|figma|luau|gdscript)(_|$)/i;
  // Multi-Script direct tools that are useful for ANY coding task (skills,
  // critic loop, memory) - the "skills" add-on. Engine-specific ones stay out.
  function isGeneralDirectTool(name) {
    const n = String(name || "").split("/").pop();
    return /^ms_/.test(n) && !/^ms_ws_/.test(n) && !ENGINE_NAME_RX.test(n);
  }
  function softwareAllows(s, tool, server) {
    const n = String(tool || "").split("/").pop();
    if (/^ms_ws_/.test(n)) return n !== "ms_ws_configure";
    const ad = (s && s.addons) || {};
    const srv = String(server || "");
    if (["list_commands", "list_mcp_servers", "more_output", "ms_more_output", "ms_get_skill", "ms_list_skills", "ms_recommend_skills"].includes(n)) return true;
    if (ad.skills && (srv === "zeroscript" || srv === "") && isGeneralDirectTool(n)) return true;
    const engineSrv = ["roblox", "unity", "godot", "blender", "figma", "roblox-companion"].includes(srv);
    if (ad.engines && (engineSrv || (srv === "zeroscript" && ENGINE_NAME_RX.test(n)))) return true;
    if (ad.mcp && srv && srv !== "zeroscript" && !engineSrv) return true;
    return false;
  }
  function softwarePrompt(providerName, s) {
    const root = s && s.root ? s.root : "";
    const code = s && s.mode === "code";
    const ad = (s && s.addons) || {};
    const first = root ? `The workspace folder is already set to: ${root}. Your first command is {"command":"ms_ws_status","params":{}}.`
      : s && s.rootMode === "create" && !code ? `No folder yet: when the user describes the app, create one with ms_ws_create_project (pick the best template).`
      : `No folder yet: when the user is ready, call ms_ws_pick_folder so they choose one on their PC${code ? "" : ", or ms_ws_create_project to make a fresh project folder"}.`;
    const extras = [
      ad.skills ? "SKILLS ADD-ON: Multi-Script's general direct tools (skills, critic review, memory, planning) are available - list_commands shows them; use ms_recommend_skills {\"objective\":\"...\"} then ms_get_skill for expert checklists." : "",
      ad.engines ? "ENGINES ADD-ON: connected game-engine tools (Roblox/Unity/Godot/Blender) are ALSO allowed in this session - use them only when the task needs the engine; list_commands {\"server\":\"<engine>\"} shows them." : "",
      ad.mcp ? "MCP ADD-ON: other connected MCP servers are allowed - list_mcp_servers shows them." : "",
    ].filter(Boolean).join("\n");
    const head = code
      ? `[MULTI-SCRIPT CODE MODE — LOCAL FILES — GENERAL CODING AGENT]
You are a senior software engineer working directly in a folder on the user's own computer through the local Multi-Script bridge. Any language, any task: features, bug fixes, refactors, reviews, tests, docs, scripts, data. This OVERRIDES the earlier list_commands first action and the game-engine rules${ad.engines ? " (engine tools are an optional add-on below)" : ""}.`
      : `[MULTI-SCRIPT SOFTWARE BUILDER — BUILD NEW SOFTWARE ON THIS PC]
This session builds real, runnable software on the user's own computer through the local Multi-Script bridge. This OVERRIDES the earlier list_commands first action and the game-engine rules${ad.engines ? " (engine tools are an optional add-on below)" : ""}.`;
    const workflow = code
      ? `WORKFLOW: 1) ms_ws_status, then explore with ms_ws_tree/ms_ws_glob/ms_ws_search/ms_ws_outline - find the code that matters before changing anything. 2) For multi-step work keep an ms_ws_plan and update it as you go. 3) Read every file before editing it (ms_ws_read / ms_ws_read_many). 4) Make the smallest correct change: ms_ws_edit for targeted edits, ms_ws_patch for multi-file diffs, ms_ws_replace (dry_run first) for renames, ms_ws_write only for new files. Match the project's existing style, imports and conventions. 5) Verify: ms_ws_check (typecheck + lint + test), fix every failure, re-run. 6) Report: what changed (ms_ws_diff), why, and how it was verified.`
      : `WORKFLOW: understand the request → pick a stack the user's machine actually has (ms_ws_status lists toolchains) → ms_ws_plan the steps → scaffold (ms_ws_create_project) or inspect → write complete, runnable files (no placeholders, no "TODO: implement") → build → ms_ws_check → fix every error you see → package if asked → report what was built, where it is, and how to run it.`;
    return `${head}
Use these commands, one plain JSON object per reply, exactly as in the main contract:
${WS_TOOLS.filter(([n]) => !(code && n === "ms_ws_create_project")).map(([n, ex, d]) => `- {"command":"${n}","params":${ex}} — ${d}`).join("\n")}
${workflow}
RULES: all paths are relative to the workspace root and cannot leave it. Never paste line-number prefixes ("  12| ") into edits. Every file change is journaled - if a change was wrong, ms_ws_undo it instead of hand-reverting. Take an ms_ws_snapshot before large refactors. ${s && s.allowRun ? "Commands are ALLOWED: verify with real builds/tests; use background:true for servers and GUI apps, test them with ms_ws_http, then stop them." : "Running commands is OFF in the user's settings: write the files, then tell the user the exact commands to run (or ask them to enable 'Run commands'). Read-only git (status/diff/log) still works."} Never install global software or touch files outside the workspace without asking. Never claim a build or test passed without its real exit code. If a tool returns ok:false, read its error/hint and fix the call - do not repeat the same call unchanged.
${extras ? extras + "\n" : ""}${first}
Reply once in one short sentence that ${code ? "Code mode" : "the Software Builder"} is ready, then wait for the user's request. Provider: ${providerName}.`;
  }

  // ── Engine setup guides (6.28.0) ───────────────────────────────────────
  // Accurate, provider-neutral setup tutorials shown in Settings → Engines.
  // Pure data: core/main.js renders them and wires the copy/fill buttons.
  // Keep every step truthful about what the bundled launchers actually do.
  const ENGINE_GUIDES = [
    {id:"figma",name:"Figma",badge:"native companion",tagline:"Create and edit native frames, text, components, vectors and Auto Layout on the current page.",needs:["Figma desktop app and an editable Design file","The bundled figma-plugin folder","The running Multi-Script bridge"],steps:["Use bundled launcher below, press Add addon, then restart the bridge/MCP servers.","In Figma desktop: Plugins → Development → Import plugin from manifest. Select figma-plugin/manifest.json from this Dev package, then run Multi-Script Figma Companion.","Open Multi-Script's bridge terminal and copy the one-use Figma pairing code (valid five minutes). Enter it in the Figma plugin.","Select Read only or Read and edit current page, then Connect this file. Keep the plugin open.","Ask the agent to call figma_status and figma_get_document. Enable Edit in the plugin before creating native content."],verify:"Ask the AI: create a small native frame and text label, read their real node IDs back, export the frame and inspect it in Figma.",tip:"MCP process alive is not proof of a paired editable file. This companion uses only the current page; official Figma remote MCP tools/seat permissions are a separate connection.",fill:{name:"Figma",command:"launch_figma_mcp.py"}},
    {
      id: "roblox", name: "Roblox Studio", badge: "built-in launcher",
      tagline: "Studio's own MCP server plus the optional Multi-Script companion plugin.",
      needs: ["Windows or macOS (Roblox Studio has no Linux version)", "Roblox Studio installed and updated", "A place open in Studio"],
      steps: [
        "Open Roblox Studio and load the place you want the AI to work in. Studio's MCP server only runs while an editor is open.",
        "In Studio, enable the MCP server from Studio's Assistant / MCP settings. Multi-Script's bundled launcher automatically finds the NEWEST StudioMCP.exe across installed Studio versions, so Studio updates cannot strand the connection.",
        "Recommended: install the Multi-Script companion plugin - copy roblox-plugin/MultiScriptCompanion.server.lua into Studio's Plugins folder. It adds 24 read/project tools with explicit permission tiers (execution is OFF until you allow it in the plugin).",
        "Start or restart the bridge (terminal icon in the chat bar), then press Refresh status below: roblox should appear with a live tool count.",
      ],
      verify: "Ask the AI: run bridge_status - roblox should be listed with live tools.",
      tip: "On Linux the Roblox engine ships switched off; enable it in Active engines only if you run Studio some other way and set ZS_STUDIO_MCP_PATH.",
      fill: null,
    },
    {
      id: "unity", name: "Unity", badge: "built-in launcher · pinned v10.2.0",
      tagline: "The CoplayDev MCP-for-Unity package inside your project, plus a pinned Python server.",
      needs: ["A Unity project open in the editor", "uv installed (provides uvx - see the one-liner below)", "The MCP for Unity package added to that project"],
      steps: [
        "Setup already tries to install uv (which provides uvx) for you. If it could not: Windows PowerShell - irm https://astral.sh/uv/install.ps1 | iex - macOS/Linux - curl -LsSf https://astral.sh/uv/install.sh | sh. Set ZS_UVX_PATH if it is still not found.",
        "In Unity: Package Manager → + → Add package from git URL, using the URL from the CoplayDev MCP-for-Unity documentation. Then open the package's window (Window menu) and start the in-editor MCP server.",
        "Keep the Unity project open. The bridge launches the pinned server (v10.2.0) through the bundled launch_unity_mcp.py - no command to paste.",
        "Press Restart MCP servers below, then Refresh status: unity should appear with its tools.",
      ],
      verify: "Ask the AI: read the open Unity scene hierarchy and name the root objects.",
      tip: "Only set ZS_UNITY_MCP_VERSION when deliberately testing a different server release; the pin exists so upstream changes cannot silently break your setup.",
      fill: { name: "Unity", command: "launch_unity_mcp.py" },
    },
    {
      id: "godot", name: "Godot 4", badge: "built-in launcher",
      tagline: "The pinned godot-mcp server, auto-detecting your Godot binary.",
      needs: ["Godot 4 installed", "Node.js installed (provides npx)", "A project folder containing project.godot, opened once in the editor"],
      steps: [
        "Install Node.js from nodejs.org so npx is available. If npx is installed but not found, set ZS_NPX_PATH to its full path.",
        "Open your Godot project (the folder with project.godot) in the Godot editor at least once and leave it open while you work.",
        "The bundled launcher auto-detects the Godot binary in the standard install locations. If detection fails, set ZS_GODOT_PATH (or GODOT_PATH) to the Godot executable.",
        "Press Restart MCP servers below, then Refresh status: godot should appear with its tools.",
      ],
      verify: "Ask the AI: show this Godot project's scene tree and main scripts.",
      tip: "Pin a different server release with ZS_GODOT_MCP_VERSION only when testing; stdout of the launcher is reserved for the protocol, so diagnostics always appear on the bridge's own log.",
      fill: { name: "Godot", command: "launch_godot_mcp.py" },
    },
    {
      id: "blender", name: "Blender", badge: "one-click below",
      tagline: "The BlenderMCP add-on inside Blender talking to the bundled launcher.",
      needs: ["Blender 3.x or newer", "uv installed (provides uvx - see the one-liner below)", "addon.py from the BlenderMCP (blender-mcp) project"],
      steps: [
        "Setup already tries to install uv (which provides uvx) AND downloads the BlenderMCP add-on for you - look for runtime/addons/blender-mcp-addon.py in your Multi-Script folder. If it is not there: Windows PowerShell - irm https://astral.sh/uv/install.ps1 | iex - macOS/Linux - curl -LsSf https://astral.sh/uv/install.sh | sh, and get addon.py from the blender-mcp project.",
        "In Blender: Edit → Preferences → Add-ons → Install… → choose the downloaded blender-mcp-addon.py, then tick the checkbox to enable BlenderMCP.",
        "In Blender's 3D viewport press N to open the side panel → BlenderMCP tab → Connect to MCP server (default 127.0.0.1:9876). Keep Blender open while you work.",
        "Click \"Use bundled launcher\" on this card - it fills the add-on form for you - then press Add addon and Restart MCP servers.",
      ],
      verify: "Ask the AI: run ms_blender_scene_summary and describe what is in this .blend file.",
      tip: "Blender is a 3D creation tool, not a game engine: the Game Idea Bot deliberately gives it asset briefs with re-import validation instead of fake game plans.",
      fill: { name: "Blender", command: "launch_blender_mcp.py" },
    },
  ];

  // ── Themes ─────────────────────────────────────────────────────────────
  // [id, label, light?, animated?]
  const EXTRA_THEMES = [
    ["roblox", "Classic Roblox", true, false],
    ["robloxdark", "Roblox 2017", false, false],
    ["terminal", "Terminal", false, false],
    ["sunset", "Sunset", false, false],
    ["ocean", "Ocean", false, false],
    ["paper", "Paper", true, false],
    ["aurora", "Aurora (live)", false, true],
    ["lava", "Lava (live)", false, true],
    // 6.28: four more, two of them live.
    ["sakura", "Sakura", true, false],
    ["crimson", "Crimson", false, false],
    ["nebula", "Nebula (live)", false, true],
    ["matrix", "Matrix (live)", false, true],
    // 6.28.2: Fazbear's Pizzeria - tiles, drifting pizzas and a hidden Backstage tab.
    ["fnaf", "Fazbear (live)", false, true],
    ["scream", "Scream · Ghostface", false, false],
    ["myers", "Michael Myers", false, false],
    ["slender", "Slenderman", false, false],
    ["jason", "Jason Voorhees", false, false],
    ["cobalt", "Cobalt Studio", false, false],
    ["porcelain", "Porcelain", true, false],
    ["ember", "Ember Studio", false, false],
    ["tidal", "Tidal (live)", false, true],
    ["starlight", "Starlight (live)", false, true],
    ["daybreak", "Daybreak (live)", true, true],
  ];
  const BG_DEFAULTS = { fit: "cover", opacity: 45, blur: 0, onBar: false };
  function sanitizeBackground(raw) {
    const s = { ...BG_DEFAULTS }, src = raw && typeof raw === "object" ? raw : {};
    if (["cover", "contain", "tile", "stretch"].includes(src.fit)) s.fit = src.fit;
    const op = Number(src.opacity); if (Number.isFinite(op)) s.opacity = Math.max(5, Math.min(100, Math.round(op)));
    const bl = Number(src.blur); if (Number.isFinite(bl)) s.blur = Math.max(0, Math.min(20, Math.round(bl)));
    s.onBar = src.onBar === true;
    return s;
  }
  const BG_MAX_BYTES = 12 * 1024 * 1024;
  const BG_TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp"];

  // ── 6.28.2 Fazbear's "Security Office": a tiny, pure, deterministic night-shift game ──
  // The hidden Backstage tab runs this. No DOM, no timers, no network: main.js feeds it
  // elapsed milliseconds and an RNG, then renders the returned state. One night is six
  // in-game hours of 14 s each (84 s). Bonnie and Chica walk Stage > Dining > Hall > Door,
  // Foxy sprints once he leaves the Cove unwatched, and Freddy only comes when the power dies.
  const FNAF_OFFICE = (() => {
    const HOUR_MS = 14000, NIGHT_MS = HOUR_MS * 6, NIGHTS = 5, DRAIN = 0.5; // % per second per usage unit
    const ROOMS = ["stage", "dining", "hall", "door"];
    const CAMS = ["stage", "dining", "hall", "cove"];
    const AI = { // 0-20 aggression per night (index = night - 1)
      bonnie: [3, 5, 7, 9, 12], chica: [2, 4, 6, 9, 12], foxy: [1, 3, 5, 8, 11], freddy: [0, 0, 1, 2, 3],
    };
    const clampNight = (n) => Math.max(1, Math.min(NIGHTS, Math.round(Number(n)) || 1));
    function create(night) {
      const n = clampNight(night);
      return { night: n, t: 0, hour: 0, power: 100, doorL: false, doorR: false, lightL: false, lightR: false, cam: false, camSel: "stage",
        pos: { bonnie: 0, chica: 0 }, wait: { bonnie: 0, chica: 0 }, door: { bonnie: 0, chica: 0 },
        foxy: { stage: 0, wait: 0, rush: 0 }, freddy: { ms: 0 }, outcome: null, killer: null, events: [],
        flags: { foxyBlocked: 0, blocked: 0, minPower: 100, blackout: false } };
    }
    function usage(s) { return 1 + (s.doorL ? 1 : 0) + (s.doorR ? 1 : 0) + (s.lightL ? 1 : 0) + (s.lightR ? 1 : 0) + (s.cam ? 1 : 0); }
    function ai(night, who) { return (AI[who] || [0])[clampNight(night) - 1] || 0; }
    const interval = (n) => Math.max(2200, 5400 - n * 520);
    const window_ = (n) => Math.max(1900, 3600 - n * 260);
    function toggle(s, what) {
      if (!s || s.outcome) return s;
      if (s.power <= 0) return s; // dark: nothing works
      if (what === "doorL") s.doorL = !s.doorL;
      else if (what === "doorR") s.doorR = !s.doorR;
      else if (what === "lightL") { s.lightL = !s.lightL; if (s.lightL) s.lightR = false; }
      else if (what === "lightR") { s.lightR = !s.lightR; if (s.lightR) s.lightL = false; }
      else if (what === "cam") { s.cam = !s.cam; if (s.cam) { s.lightL = false; s.lightR = false; } }
      return s;
    }
    function setCam(s, id) { if (s && CAMS.includes(id)) s.camSel = id; return s; }
    function kill(s, who) { s.outcome = "dead"; s.killer = who; s.events.push({ type: "dead", who }); }
    function step(s, dtMs, rnd) {
      if (!s || s.outcome) return s;
      const r = typeof rnd === "function" ? rnd : Math.random;
      let dt = Math.max(0, Math.min(1000, Number(dtMs) || 0));
      s.events = [];
      s.t += dt; s.hour = Math.min(6, Math.floor(s.t / HOUR_MS));
      if (s.power > 0) {
        s.power = Math.max(0, s.power - usage(s) * DRAIN * dt / 1000);
        if (s.power <= 0) { s.power = 0; s.doorL = s.doorR = s.lightL = s.lightR = s.cam = false; s.flags.blackout = true; s.events.push({ type: "blackout" }); }
      }
      s.flags.minPower = Math.min(s.flags.minPower, s.power);
      const n = s.night;
      // Bonnie (left) and Chica (right) walk toward the door; a closed door sends them back.
      for (const [who, doorKey] of [["bonnie", "doorL"], ["chica", "doorR"]]) {
        if (s.pos[who] < 3) {
          s.wait[who] += dt;
          if (s.wait[who] >= interval(n)) {
            s.wait[who] = 0;
            if (r() * 20 < ai(n, who)) { s.pos[who] += 1; s.door[who] = 0; s.events.push({ type: "moved", who, to: ROOMS[s.pos[who]] }); }
          }
        } else {
          s.door[who] += dt;
          if (s[doorKey]) {
            if (s.door[who] >= 1800) { s.pos[who] = 1; s.door[who] = 0; s.wait[who] = 0; s.flags.blocked += 1; s.events.push({ type: "blocked", who }); }
          } else if (s.door[who] >= window_(n)) { kill(s, who); return s; }
        }
      }
      // Foxy: leaves the Cove while nobody watches it, then sprints at the left door.
      const f = s.foxy, watching = s.cam && s.camSel === "cove";
      if (f.stage < 3) {
        if (!watching) f.wait += dt;
        if (f.wait >= Math.max(2600, 6400 - n * 600)) {
          f.wait = 0;
          if (r() * 20 < ai(n, "foxy")) { f.stage += 1; s.events.push({ type: "foxy", stage: f.stage }); }
        }
      } else {
        f.rush += dt;
        if (f.rush >= 3200) {
          if (s.doorL) { s.power = Math.max(0, s.power - 4); s.flags.foxyBlocked += 1; s.events.push({ type: "knock" }); f.stage = 0; f.rush = 0; f.wait = 0; }
          else { kill(s, "foxy"); return s; }
        }
      }
      // Freddy waits for the lights to go out.
      if (s.power <= 0) {
        s.freddy.ms += dt;
        if (s.freddy.ms >= 4500 + (6 - n) * 600) { kill(s, "freddy"); return s; }
      }
      if (s.t >= NIGHT_MS) { s.outcome = "won"; s.hour = 6; s.events.push({ type: "won" }); }
      return s;
    }
    // What the player can see right now: camera feed, or the door light, or nothing.
    function view(s) {
      if (!s) return { mode: "off", lines: [] };
      if (s.power <= 0) return { mode: "dark", lines: ["Power out.", "It is very quiet..."] };
      if (s.cam) {
        const here = [];
        if (s.camSel === "cove") here.push(s.foxy.stage >= 3 ? "Cove curtain open - Foxy is gone!" : s.foxy.stage ? "Foxy peeks out (stage " + s.foxy.stage + "/3)" : "Cove curtain closed");
        else for (const who of ["bonnie", "chica"]) if (ROOMS[s.pos[who]] === s.camSel) here.push(who === "bonnie" ? "Bonnie" : "Chica");
        if (s.camSel === "stage" && !here.length) here.push("The stage is empty");
        return { mode: "cam", cam: s.camSel, lines: here.length ? here : ["Nothing here"] };
      }
      for (const [side, who, name] of [["lightL", "bonnie", "Bonnie"], ["lightR", "chica", "Chica"]]) {
        if (s[side]) return { mode: "light", side, lines: s.pos[who] === 3 ? [name + " is at the door!"] : ["Empty hallway"] };
      }
      return { mode: "office", lines: [] };
    }
    function score(s) { return { power: Math.round(s.power), blocked: s.flags.blocked + s.flags.foxyBlocked }; }
    return { HOUR_MS, NIGHT_MS, NIGHTS, DRAIN, ROOMS, CAMS, AI, create, step, toggle, setCam, usage, view, ai, score, clampNight };
  })();

  return { GENRES, SCOPES, gameIdea, engineKey, sanitizeSoftware, SOFTWARE_DEFAULTS, softwarePrompt, softwareAllows, isGeneralDirectTool, WS_TOOLS, WS_TOOL_NAMES,
    EXTRA_THEMES, sanitizeBackground, BG_DEFAULTS, BG_MAX_BYTES, BG_TYPES, ENGINE_GUIDES, FNAF_OFFICE };
})();
if (typeof module !== "undefined") module.exports = ZSExtras;

// ZSSound (6.30.0) - tiny WebAudio cues: AI finished, command ran, error.
// Synthesised on the fly (no audio files, no network). Never throws.
const ZSSound = (() => {
  const KEY = "msSound";
  const DEFAULTS = { enabled: true, volume: 0.5, done: true, command: true, error: true, style: "ping" };
  let prefs = Object.assign({}, DEFAULTS);
  let ctx = null, lastAt = {};
  const STYLES = {
    ping:   { wave: "sine",     done: [[880, 0], [1320, 0.11]], command: [[1560, 0]], error: [[440, 0], [294, 0.14]] },
    soft:   { wave: "triangle", done: [[660, 0], [990, 0.14]],  command: [[1046, 0]], error: [[330, 0], [247, 0.16]] },
    arcade: { wave: "square",   done: [[523, 0], [659, 0.07], [784, 0.14]], command: [[1318, 0]], error: [[196, 0], [147, 0.12]] }
  };
  function sanitize(p) {
    const o = Object.assign({}, DEFAULTS, p && typeof p === "object" ? p : {});
    o.enabled = o.enabled !== false; o.done = o.done !== false; o.command = o.command !== false; o.error = o.error !== false;
    o.volume = Math.max(0, Math.min(1, Number(o.volume))); if (!isFinite(o.volume)) o.volume = DEFAULTS.volume;
    if (!STYLES[o.style]) o.style = DEFAULTS.style;
    return o;
  }
  function load() {
    try {
      if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
        chrome.storage.local.get(KEY, (r) => { try { prefs = sanitize(r && r[KEY]); } catch (_) {} });
        if (chrome.storage.onChanged) chrome.storage.onChanged.addListener((ch, area) => { if (area === "local" && ch[KEY]) prefs = sanitize(ch[KEY].newValue); });
      }
    } catch (_) {}
  }
  function save(next) {
    prefs = sanitize(Object.assign({}, prefs, next || {}));
    try { if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) chrome.storage.local.set({ [KEY]: prefs }); } catch (_) {}
    return prefs;
  }
  function audio() {
    try {
      if (!ctx) { const AC = (typeof window !== "undefined") && (window.AudioContext || window.webkitAudioContext); if (!AC) return null; ctx = new AC(); }
      if (ctx.state === "suspended" && ctx.resume) ctx.resume().catch(() => {});
      return ctx;
    } catch (_) { return null; }
  }
  // kind: "done" | "command" | "error". force=true ignores per-event toggles (Test buttons).
  function play(kind, force) {
    try {
      if (!force && (!prefs.enabled || !prefs[kind])) return false;
      const now = Date.now(); if (!force && lastAt[kind] && now - lastAt[kind] < 250) return false; lastAt[kind] = now;
      const st = STYLES[prefs.style] || STYLES.ping, notes = st[kind]; if (!notes) return false;
      const ac = audio(); if (!ac) return false;
      const vol = prefs.volume * (st.wave === "square" ? 0.12 : 0.3);
      if (vol <= 0) return false;
      const t0 = ac.currentTime + 0.01, dur = kind === "command" ? 0.09 : 0.22;
      for (const [f, off] of notes) {
        const o = ac.createOscillator(), g = ac.createGain();
        o.type = st.wave; o.frequency.setValueAtTime(f, t0 + off);
        g.gain.setValueAtTime(0.0001, t0 + off);
        g.gain.exponentialRampToValueAtTime(vol, t0 + off + 0.012);
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + off + dur);
        o.connect(g); g.connect(ac.destination); o.start(t0 + off); o.stop(t0 + off + dur + 0.03);
      }
      return true;
    } catch (_) { return false; }
  }
  load();
  return { KEY, DEFAULTS, STYLES, sanitize, play, save, get: () => Object.assign({}, prefs) };
})();
if (typeof module !== "undefined") module.exports.ZSSound = ZSSound;
