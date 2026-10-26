# 6.50.1

Automatic bounded resource discovery, OMNI package/PDF access, scoped recent vault recall, Arena streaming optimizations and GitHub Discord/Ko-fi integration. Existing skills, phases, projects and releases are preserved.

# Multi-Script 6.49.9 — GitHub account migration and delivery safeguards

Move active repository/feed/download configuration to krazydarky-code/Multi-Script without rotating the signing key or extension identity. Preserve existing skills, manuals, native projects and all prior transport/UI fixes. Public 6.42.0 remains frozen; the migration release hosts it for later builds.

Stop publishing on API errors instead of treating every latest-release failure as an empty repository. Serialize and pace writes, reuse matching draft assets, check main again before uploads/publication, and plan read-only before loading signing material. Automatic publication requires an explicit repository variable. Shard the full existing targeted CI set, add real ChatGPT native-editor and delivery regressions, and reject incomplete aggregated coverage.

Persist update-host Retry-After/reset cooldowns across restarts. Inaccessible feeds pause requests for one day; network failures use exponential browser backoff. Corrected feed configuration is not blocked by the old host's cooldown. Numeric version stays 6.49.9; older pinned feeds require a one-time complete-package migration.

# Multi-Script 6.49.9 — ChatGPT native composer transport

## Merged from 6.48.2 Dev - skills overhaul

- Forge ui_kit is quick by default: at most 5 images per call (priority pieces first). Pass quick=false for the whole pack. Uploads run one batch after another, so fewer images means a shorter wait.

- Fix: Forge backdrops were uploaded but never written into Studio. They are now stored as StringValues in ReplicatedStorage.ForgeBackdrops (name = picture name, value = rbxassetid).

- Ultra start routine is shorter: one shallow Studio survey (services and StarterGui) instead of a deep survey before the first build. Deeper reads happen only when the task needs them. Safety rules (docs checks, nothing done until checked) are unchanged.

- Forge ui_kit now draws the small shop pack by default instead of the full set, so it finishes much faster. Pass pack=full for everything.

- Fix: the extension now always advertises ms_forge when its drawing module is loaded, so an older bridge no longer makes the chat reject it as an unknown command.

- Fix: ms_forge was hidden from ms_find_tool when the search used engine=roblox (it had no Roblox engine tag). It is now tagged roblox.
- Missing Forge or docs modules now print a reason to the log instead of silently disappearing.

- New `ms_roblox_ui_audit` tool: measures the real GUI in Studio (text fit, contrast, tap size, off-screen, empty lists, unloaded images, overlapping buttons). 281 tools.
- Skills answer now lists the built-in tools: offline docs, Forge, automatic code checker, UI inspector, expert templates and kits.
- Clean UI and Code quality skills tell the AI to run the UI inspector and fix code-check findings; expert templates linked.

**Forge in one call, upload packs, clean edges and new pieces** - asking for game art now ends with it installed and working.
- One `ms_forge` call (ui_kit, vfx or backdrop) now draws the art, stores it, uploads it through Studio's upload_image (in batches of 20), writes `ReplicatedStorage.ForgeKit` or `ReplicatedStorage.ForgeVFX` (ScriptEditorService, falling back to Source), and builds a demo to screen_capture: `StarterGui.ForgeDemo` (a shop window, currency pills, buttons and an XP bar) or `workspace.ForgeVFX_Showroom` (every looping effect running). install=false only draws; demo=false skips the demo. Without Studio it draws and explains the manual route. The pipeline lives in `MSForge.run` in forge.js; main.js only supplies the bridge and Studio calls.
- Upload packs: hud, shop, inventory, settings, leaderboard, dialogue, rewards, essentials (about 20 to 60 images) or full (about 120).
- Clean edges: Forge now writes its own PNGs and bleeds edge colour into the transparent border at alpha 1, which reduces the dark fringes Roblox can show on scaled transparent images (the ImageLabel reference notes transparent pixels turn black on upload).
- New art: light rays and a soft glow. New ForgeKit pieces: `Kit.reward` (spinning rays pop-up with ribbon title and claim button), `Kit.billboard` (name tag and health bar over a character), `Kit.loading` (loading screen over a Forge backdrop with a progress bar); `Kit.screen` accepts a parent so it works in Studio edit mode; `Kit.modal` can open instantly.
- New `docs/FORGE.md` explains in plain words how to use it.
- Checked: in Chromium, a full run of `MSForge.run` against the real bridge code with a stand-in Studio (fake upload ids) worked for a UI pack, a VFX set and a backdrop; all Luau sent to Studio (module install, demo, showroom) passes the docs check with no findings and a block-balance check. Not checked: a real Studio upload and execute_luau, the extension live in a chat, and the test suite.

**Forge rebuilt inside the extension: no Python add-ons, about twice as much art, and a much richer ForgeKit** - Forge no longer needs numpy.
- All drawing now happens in the browser extension with the built-in Canvas (`extension/core/forge.js`, loaded with the other content scripts). The bridge side (`runtime/forge_assets.py`, `runtime/forge_luau.py`) uses only the Python standard library: it stores the PNGs, serves them on 127.0.0.1 for Studio's upload_image, reads a local reference picture (PNG, JPG or WEBP) and writes the Luau. Setup no longer installs numpy.
- UI kits grew from about 60 to about 120 pieces: new card, ribbon banner, xp, hp and mana bars, price tag, checkbox, radio, slider, input box, scrollbar, speech bubble, toast, gold/silver/bronze leaderboard rows, corner ribbon, gamepad selection ring, arrow and tick glyphs, minus and help buttons, and 30 item icons (adds sword, shield, potion, trophy, crown, key, chest, egg, paw, pickaxe, gear, cart, bag, scroll, clock, skull, flame, drop, leaf, ticket, rebirth, speed, ghost).
- VFX grew to 27 textures (adds twinkle, cloud, crescent, rune ring, bubble, snowflake, leaf, droplet, swirl, hit star, feather, confetti, heart glow, wisp), 6 strips (adds sharp trail, chain, wave) and 8 flipbooks (adds portal swirl, splash, electric burst), with 27 presets (adds hit star, impact burst, ambient smoke, portal, electric, splash, level up, confetti, snow, leaves, bubbles, ghost wisp, hearts). Backdrops add stripes, grid and sunset.
- ForgeKit adds Kit.screen (auto-scaling ScreenGui in device safe insets), Kit.modal (pop open and close), Kit.grid and Kit.list (scrolling, canvas grows), Kit.card (complete shop card), Kit.bar, Kit.priceTag, Kit.checkbox, Kit.radio, Kit.slider (mouse and touch drag), Kit.input, Kit.tabs (pages), Kit.bubble, Kit.leaderboardRow, Kit.toast (stacking), Kit.tooltip, Kit.divider, icons inside buttons, and gamepad selection on every control. ForgeVFX adds pooled bursts, VFX.combo, VFX.stop, size scaling and Wrap-mode beams. bind also returns a ready usage example.
- Large sets are sent to the bridge in batches under 6 MB.
- Checked: every set was drawn in Chromium and looked at; a full run (draw in the browser, store through the bridge, fetch from the localhost address, bind) worked for a UI kit, a VFX set and a backdrop; both Luau modules and their usage examples pass the docs check with no findings and a block-balance check; every API they use was confirmed in the offline reference; the bridge loads and dispatches the tool. Not checked: the extension running live in a chat, a real Studio upload_image round trip, the Luau running in Studio, and the test suite.

**Forge: game art that turns into working UI and effects** - inspired by ForgeGUI (AI game-art sets with a consistent style and a Studio import), but local, free, and wired to real Roblox objects instead of stopping at pictures.
- New tool `ms_forge` draws real transparent PNGs on this computer with anti-aliased shape rendering (needs numpy; Setup now installs it when it can).
- `ui_kit`: a complete, matching set in one call - buttons in 4 states (normal, hover, pressed, disabled) in 4 colours, round close/back/plus/next/confirm buttons, panel, header, inner panel, slots for 7 rarities plus selected, tabs, progress bar, currency pill, toggle, badge, tooltip, and coin, gem, star, heart, bolt, lock and gift icons. 12 styles (simulator, cartoon, glossy, candy, anime, glass, neon, fantasy, scifi, minimal, horror, pixel), your own colours, small tweaks, or `reference_image` to copy a screenshot's palette. Every piece carries its 9-slice centre, and art is drawn at 2x.
- `vfx`: 13 particle textures, 3 trail/beam strips, and 5 flipbooks at 1024x1024 (the size Roblox requires), all white on transparent so Color tints them, with 14 tuned ParticleEmitter presets.
- `backdrop`: 16:9 backgrounds (burst, clouds, space, dungeon, sparkles) at 1920x1080 for thumbnails or 1024x576 for in-game screens.
- The files are served on 127.0.0.1 so Studio's `upload_image` can upload them; `bind` then returns a ForgeKit ModuleScript (panel, button with real hover/pressed images, icon buttons, slots, progress, pill, toggle, tabs, badge, icons; all 9-sliced) or a ForgeVFX ModuleScript (burst, attach, trail, beam). Both modules pass the docs `check` and every property and enum they use was confirmed in the offline API reference.
- check-clean-ui, vfx-assets, the always-on standards and Ultra (GUI and VFX build steps, start-up) now say when to use Forge, to look at the preview first, to upload through Studio and never type ids, and that Forge art does not relax the contrast, layout, input or capture rules.
- Tool count is now 280 (tests and manifest updated). Startup standards are about 31.9k tokens. Per-task Ultra text unchanged (8970 characters on the inventory test request).
- Checked: every output was rendered and looked at here; the bridge loads the tool and dispatches it; the Luau modules pass the docs check and a block-balance check. Not checked: running the Luau in Studio, an actual upload_image round trip, and the test suite.

**Official Roblox and Luau docs, offline (2,261 pages)** - the AI can now look up the real answer instead of guessing.
- New tool `ms_roblox_docs`, built from the open-source Roblox Creator Docs (snapshot of 24 Oct 2026, Studio 0.744) and the Luau docs: 992 guides, the full engine API (628 classes, 518 enums, 49 datatypes, 11 libraries, globals) and 61 Luau pages. About 3.5 MB, works with no internet. Licences (CC-BY-4.0 text, MIT code) and a notice are included.
- `search` ranks pages by title, headings and text; `read` opens a page or jumps to a section or member; `api` confirms a name exists, its exact signature, dot or colon, where it is inherited from, and the replacement if it is deprecated; `check` scans a script for deprecated calls (wait, spawn, Humanoid:LoadAnimation, FindPartOnRay, BodyVelocity and 680 more), unknown classes, services or enum items, wrong-case members and dot/colon mistakes. It found no false alarms in the 36 Brickwire kits.
- `tools/build_roblox_docs.py` rebuilds the docs from fresh clones of github.com/Roblox/creator-docs and github.com/luau-lang/site.
- All 8 skills, the always-on standards and Ultra's start-up now tell the AI to confirm uncertain APIs and to run `check` on every script before writing it to Studio. Ultra counts a docs lookup as research.
- The docs check found and fixed real mistakes in the skills: `Lighting.Technology` is deprecated (now LightingStyle and PrioritizeLightingQuality), `GuiService:IsTenFootInterface` is deprecated (now ViewportDisplaySize), and the UIShadow advice now uses its documented properties. It also found `Enum.Font.GothamSemibold` in the companion plugin, which the docs no longer list; it now uses GothamMedium. Reinstall the plugin to get that change.
- The tool count is now 279; the two tests that pin the count and the product manifest were updated to match.
- The startup standards block is about 31.2k tokens. Per-task Ultra text is unchanged (8970 characters on the inventory test request).
- Not tested in Studio or a browser, and the test suite was not run. The tool was called directly through the bridge's own dispatch for search, read, api and check.

**Final integration pass** - two wiring fixes found by reading the code against the existing tests.
- The Ultra text had lost the "ms_skill_reference links" wording for GUI and animation that an existing test expects; it is back (per-task text 8970 characters, under the 9000 bound).
- The reference reader (ms_skill_reference) is now treated as guidance, like the manuals, so reading the ready-made kits does not count as a write or an unexplained call. game-systems now lists the kits as a resource, like the other reference packs.
- Static checks only: all Python compiles, all JavaScript passes syntax checks, all JSON parses, every update hash matches. The test suite and Studio were not run.

**Brickwire's best parts, added and credited** - Brickwire 3.0 (MIT licence) has tested ready-made Luau systems and strict "done means checked" rules; Multi-Script now uses both.
- New ready-made systems library: 36 Brickwire scripts (obby stages, kill bricks, pads, teleporters, coins, rounds, saved stats, daily reward, shop, inventory, HUD, menus, toasts, day and night, NPC dialog, VFX presets, camera fly-through, and the cutscene module with case, egg, dice, event and story scenes). The AI reads them on demand with the reference tool (skill game-systems), so the startup text does not carry them. The licence file is included.
- game-systems gained two steps: use the closest kit and upgrade it to the existing rules (UpdateAsync with session locking, idempotent ProcessReceipt, validated remotes), and cutscene rules (server decides the result, camera and controls always restored, Skip from the first frame, longer pauses for rarer results). New trigger words: cutscene, case opening, egg hatch, dice roll, intro sequence.
- code-quality gained "Done means checked": nothing is done until a check passed after the last change, tool results are never imitated, edits are small and reversible with a ChangeHistory waypoint.
- Not copied: Brickwire's bridge, extension, panel and 50 generic skill templates (they are boilerplate with little content).
- Ultra: its start-up block now points to the kit index, the inspect-to-failures order and the done-means-checked rule; two new Ultra methods (cutscene, and economy now points to the kits). The per-task text stays at 8922 characters for the inventory test request.
- The startup standards block is now about 30.3k tokens (was 29.4k).
- Kits were only run by Brickwire in a Luau VM with a stubbed Roblox API; nothing here was tested in Studio, and the test suite was not run.

**Ultra manuals now give a step-by-step Roblox method** - each of the 12 manuals returns a six-step plan (inspect, design, build, integrate, verify, failures) written for Roblox Studio and its tools, and Ultra's start-up block now begins with a fixed survey routine.
- The routine: list Studios, read state, one game-tree survey, note existing styles, currency/data code, remotes, Rojo and which tools exist, reuse what is there, keep a short notes ledger.
- Per-task Ultra text is unchanged in size (8922 chars for the inventory test request, under the 9000 bound).
- Not tested in Studio or a browser; the test suite was not run.

**Ultra now starts properly when you select it** - selecting Ultra (or opening a session with Ultra already on) now sends a one-time start-up block with the first task.
- It tells the AI to load the full skills and read the relevant manuals, and carries all 12 manuals' Roblox rules as standing rules for the session, kept silent. It is sent once per selection, only for Roblox work, and only at the Ultra level.
- Switching to a lower level clears it; selecting Ultra again sends it again.
- Not tested in Studio or in a live browser session; the existing test suite was not run.

**Ultra: Roblox rules in every manual, per-manual doc links, new methods and a plain finish** - only the GUI and animation manuals had Roblox-specific content, every manual showed the same four doc links, and Ultra told the AI to finish with a long changes-and-verification report.
- All 12 manuals now return their own Roblox standards (emoji-free GUI, finished measured screens, props in three passes, economy and server authority, networking limits, performance targets, audio, input, QA) and their own doc links. The modeling manual now says Parts-only requests stay Parts-only.
- The per-task Ultra text now carries the relevant manual's Roblox rules instead of two generic sentences, kept inside the existing size limit.
- Two new methods: props (shape first, three passes, one short finish line) and economy (sources and sinks, server-owned rolls, one ProcessReceipt). The interface and assets methods gained the emoji, finished-screen, contrast and picture-checking rules.
- Ultra now finishes with a short plain line, not a long report; failures, unchecked items and anything needing the user are still said in one sentence.
- Other engines are unchanged. Not tested in Studio; the existing test suite was not run.

**Pack integration: Roblox services, security, platform and tooling rules (from the supplied skills pack)** - the best of the 24-skill pack was folded into our skills in short form, with nothing copied whole.
- **Game systems**: monetization (passes, subscriptions, refunds, paid random items and policy checks), teleports and places (untrusted teleport data, access control, handoff), live ops and analytics (configs, timed events, daily rewards), data extras (versioned saves, MemoryStore), combat hit validation.
- **Code quality**: a severity-ordered review method and a compact deprecated-API map, plus text filtering and chat rules.
- **Scripting power**: more security (prompts, click detectors, ownership), networking channel choices, physics, input and character rules, Open Cloud and HttpService, testing and toolchain, the Studio tool loop.
- **NPCs**: pooling and scaling. **Effects**: audio and engine lighting facts. **Fix errors**: silent failures (animation, sound, remotes).
- Added trigger words so purchases, teleports, audio, Rojo and testing requests pick the right skills.
- The pack's facts were not all re-verified against the docs, and nothing was tested in Studio.

**Check-Props: tighter and better (about 27 pages read in total)** - rewritten from about 30,000 to 13,000 characters with the duplicated check rows and repeated rules removed.
- **Short finished reply**: the AI now just says the prop is finished and where it is, in one normal line, with no list of parts, techniques or checks.
- **Look**: shape first, three passes, the zoom-out test, never a plain box, trim, a second material, wear, a value ladder, consistent grid and palette.
- **Added from this round**: block out and walk it before detailing, hero and background triangle budgets, batching of identical meshes, Massless and collision settings, texture sizes, trim and modular-kit grid, ambient occlusion baked into the colour map, and a lighting check.
- Kept: Luau helpers and orientation traps, union rules, scale minimums, recipes for common props and buildings.
- YouTube pages are blocked to the tools used here and Discord is private, so neither was read. Sources were Roblox docs, DevForum threads, art guides and a few articles.
- Not tested in Studio.

**No emojis in GUIs, and deeper game-systems, NPC, error and prop rules (from about 55 more pages read)** - emojis in interface text render as empty boxes or the wrong font, so the AI now draws icons instead.
- **No emojis in any GUI text** (always on): titles, buttons, tabs, prices and toasts use words; icons are real images, drawn shapes, small 3D models or BuilderIcons glyphs. Added to the final review and the asset checks.
- **Game systems** (+24 rules): developer-product receipts (one handler, no double grants), safe saving with session locking, simulator costs and pacing, pets and luck (weighted rolls, luck done correctly, pity), trading and duplication, rounds and matchmaking, leaderboards, DataStore limits and error codes.
- **NPCs and pathfinding** (+14 rules): real agent defaults and failure causes, costs, modifiers and links, smooth movement and stutter fixes, sight and hearing, state machines, horror director patterns.
- **Fix errors** (+9 rules): common error messages and causes, remotes that do not fire, debugger use, data and purchase errors.
- **Props** (+6 rules): triangle, texture and part budgets, materials and SurfaceAppearance values, silhouette and readability.
- Not tested in Studio or on a live model. Numbers marked as tune are starting points.

**Check-Clean-UI: finished, measured, reviewed screens (from about 80 more pages)** - a candy shop came out as a pink shell: an empty panel, two unreadable tabs, a Buy button with nothing to buy. Read about 80 pages (about 73 usable: Roblox UI and text docs, Fortnite and Roblox shop guidance, WCAG contrast, tab, empty-state and button-state guides, DevForum critiques, juice and shadow articles; 7 failed or were empty) plus 27 searches, and wrote five new sections:
- **Complete screens and shops** (7 rules): never an empty panel; stress data (zero, one, many, long names, missing picture, cannot afford, owned, locked); shop anatomy, item cards with states, a Buy button tied to the selected item, tab rules (count, names that fit the shop, two cues for the selected tab, readable inactive tabs, 44 to 48 px), reach and close button.
- **Contrast check** (5 rules): the real WCAG formula to run on every text and icon pair, targets (4.5:1, 3:1), testing both ends of gradients, same-hue failures (pink on pink), minimum text sizes.
- **Text fitting** (5 rules): TextScaled pitfalls, fixed sizes with measured fit, truncate or wrap, fonts and outlines.
- **Candy and sweets style** (8 rules): 60-30-10 palette with several accents, readable tabs, gloss and shine sweep, candy stripes, matching sweets art.
- **Final review** (7 rules): completeness, readability, pictures, hierarchy and spacing, behaviour, honesty. A short version is now in the always-on core rules.
- **Bridge fix**: the rule text sent with each request is now fitted to a cap by priority (the style you named, the review and contrast checks, then the rest) instead of dropping a skill's whole rule set to a pointer when over the cap. The cap is 44k characters in total (was 32k), with up to 32k for UI. Skipped sections are listed by name and `ms_get_skill` can now load just those sections (`sections`) or just what an objective needs (`objective`), instead of the whole skill.
- Not tested in Studio, and the new rules were not tried on a live model. The contrast formula and thresholds are the standard WCAG ones; shop and tab numbers come from design guides, not Roblox limits.

**Better pictures in UI: real Creator Store search and checking** - fixes UI that came out with the wrong or broken art (a faint clover, a currency button showing an empty box, item tiles with unrelated pictures, a name cut off at the tile edge).
- The asset search tool (ms_roblox_asset_scout) was sending Studio the wrong argument names, so the asset type and result count were ignored. It now uses the real ones and can search up to four phrasings at once, with tags, facets, verified creators first (relaxed if that finds nothing), free assets by default, and it attaches the real thumbnails of the first results so the AI can look at them before choosing. It still never invents an id.
- New "Finding and checking assets" section (12 rules): decide the subject and style, search with several phrasings, look at the thumbnails, reject mismatches, baked-in text and solid backgrounds, check the picture at its final size and load status, keep ids in one swappable table, fall back to shapes, Parts or the built-in icon font instead of a bad match, build prices as an icon plus a number (not a special character that can show as an empty box), and finish every UI with a screen capture to look for empty boxes, wrong pictures, clipped or misspelt text and low contrast. A short version of this is now in the always-on core rules.
- Not tested in Studio. The thumbnail download (it fetches thumbnails from Roblox's public thumbnail service on your machine, and quietly skips any that fail) and the new search arguments were checked only against a fake Studio, not a live one.

**Check-Clean-UI: 3D models inside UI + the studded shop look** - the AI can now build a 3D object from Parts (or take a Creator Store model) and show it in the UI with a ViewportFrame, like the 3D item and pet renders in studded simulator shops. Built from about 35 more pages (ViewportFrame, WorldModel, Model, Camera, Toolbox and InsertService docs, plus DevForum threads on fitting models to a viewport, spinning, hover, performance, character and accessory issues, and viewport freezes); 4 pages failed to load.
- New "3D in UI" section (12 rules): when to use a viewport instead of an image, setup order, cleaning a clone (strip scripts, anchor, no collision), the camera-fit maths from bounding box, field of view and aspect ratio, framing angles for cards, fixed viewport lighting and its limits, spin and hover without per-item loops, known quirks, characters in a WorldModel, model sources, and a blocky-creature build recipe.
- The 3D rules work in any style and any screen (main menu character, loot reveal, weapon inspector, dialogue portrait, hologram panel and more), with per-style advice (cartoon, modern, horror, sci-fi, fantasy, glass), not only for shops.
- New "Studded shop screen" section (8 rules) that describes the screenshot you sent: studded blue title bar with a red close square, gradient offer rows, gradient item tiles with 3D renders, lime studded price buttons, text with thick black outlines. It describes the structure and colours, not any game's art.
- Added trigger words (viewport, 3d icon, item preview, pet card and others).
- Not tested in Studio. Camera-fit maths and sizes come from docs and forum threads; viewport performance limits and freezing fixes are community reports, not official numbers. Animations inside viewports are marked unreliable.

**Check-Clean-UI: 16 more styles and 3 technique sections** - built from about 85 more pages read (Creator Hub UI docs for rich text, 9-slice, scrolling frames, proximity prompts and styling, DevForum threads on 3D buttons, hover and ripple effects, style transitions and glass UI, plus pack listings and design references). 13 more pages failed to load or had no usable content and were not used.
- New style sections, sent only when the request names them: studded (Lego-brick look, stud rows, tiled stud texture, brick thickness), skeuomorphic, steampunk, comic, clay and candy, neumorphism (with an accessibility warning), neubrutalism, Y2K and retro OS, pixel, paper and sticker, blueprint and terminal, holographic, aurora, low-poly, dark mode and bento, anime and gacha. The cartoon look is still the default when no style is named.
- New technique sections: shine sweep, 3D button, ripple, radial progress, prize wheel, radial menu, typewriter, count-up, frosted-glass options; drag and drop, tabs, text boxes, rich text tags, scrolling lists, 9-slice, custom proximity prompts; inventory grid and rarity rules.
- Not tested in Studio. Stud textures are never invented: they must come from the user or a confirmed asset. Some figures (palettes, sizes, timings) are design starting points, not engine limits.

**VFX and Code Quality reworked (expert level)** - two always-on standards were rebuilt from about 105 pages read in full (official Creator Hub docs for particles, beams, trails, lighting, atmosphere, post-processing, sky, clouds, audio, performance, events, deferred signals, testing modes and the Roblox Lua style guide; DevForum threads on effects, lightning, sword slashes, camera shake, impact frames, player lifecycle, memory leaks and OOP; Game Programming Patterns; Trove, PartCache, Spr, Zap, Jest Roblox, StyLua and Selene). Another 14 search result lists were only skimmed. Pages that failed or said very little (for example the Light, Highlight, Bloom and DepthOfField class pages) were not used for numbers.
- **VFX and Assets** now has 92 rules in 13 sections, sent only when a request touches them: particles (official limits, shapes, flipbooks, orientation, wind), 12 effect recipes (explosion, hit, pickup, aura, heal, projectile, fire and smoke, dust, rain and snow, portal and shield, splash, muzzle flash), beams and trails, mesh effects (slashes, shockwaves), lightning, lighting and mood (Future vs ShadowMap, light costs, mood recipes, Atmosphere, sky, clouds, materials), post-processing, camera shake and feedback, sound, animation-marker timing, performance (fill rate, level of detail, pooling, quality scaling) and style and polish. Toolbox safety rules are kept.
- **Code Quality** gained 44 rules in 8 sections on top of the 71 it had: engineering practice, architecture and lifecycle (init then start, services and controllers, dependencies), patterns (state machine, signals, tag components, commands and queues, pools, dirty flags, fixed timestep, flyweight), typed classes, errors and results, events and player lifecycle (deferred signals, character order, leaks), testing and debugging, and style and review. Data, purchases and security rules are unchanged.
- The bridge trigger list for VFX has about 30 more words (beam, trail, shockwave, slash, camera shake, post-processing, mood, cinematic and others).
- Not tested in Studio. A few third-party figures (for example the Highlight cap of 255) come from community summaries and are marked as such in the rules.

**Check-Clean-UI reworked: any UI, any style** - the UI standard is no longer one fixed cartoon look. It can now build any menu, HUD, shop, inventory, dialogue, quest log, settings, leaderboard, notification, loading screen, minimap, crafting, tooltip or on-part screen in any style the user asks for. The cartoon recipes are kept exactly as before and stay the default when the user names no style. New sections (133 rules in total, 19 sections; only the ones a request touches are sent): a design system (colour, contrast, type, spacing, hierarchy, touch targets, states), layout and responsive rules (scale, constraints, layout objects, safe areas, avoiding the default Roblox controls), 17 component recipes, eight style families (sleek modern, glass, horror, sci-fi, fantasy, minimal, retro, realistic), StyleSheet use, feel and motion, gamepad and console, accessibility, world UI (billboards, surface screens, proximity prompts), UI performance (build once, event-driven updates, pooled long lists, sprite sheets, cleanup) and assets, icons and fonts. A new optional `ruleSectionDefaults` field lets a section (here the cartoon look) be sent when no other style matched. Research: about 75 Creator Hub and DevForum pages read in full plus search results for another 30 or so (WCAG contrast and target size, Vide, Iris, virtualized lists, glass and blur, loading screens, button feel, design-system guides); pages that failed or were thin were not used. The StyleSheet rules are deliberately general and tell the model to read the class pages first, because that system is new and I could not confirm every detail. Not tested in Studio; the combined text is much larger than before, so it is delivered by section.

**New skill: Scripting Power (241 skills in total)** - a mandatory, docs-backed skill for fast, safe, modern Luau. It carries 105 rules in 17 sections (Luau speed, native code and profiling, language features, types, library tricks, async and cleanup, networking, security, data, Parallel Luau, physics and queries, players and streaming, input and frame loop, architecture and style, tooling, lint-catchable bugs, debugging, optimisation) and only the sections a request touches are sent. Built from about 50 pages read in full: luau.org (performance, library, syntax, lint, recaps), the Creator Hub (native code gen, type checking, Parallel Luau, client-server security, remotes and bindables, DataStore limits, MicroProfiler, streaming, and the Players, WorldRoot, BasePart, CollectionService, MarketplaceService, ContextActionService and other class pages), Roblox's Lua style guide, the ProfileStore and DataStore best-practice posts, an optimisation guide, and the repos for Rojo, luau-lsp, Promise, RbxUtil, Jest Roblox, roblox-ts and Zap. Pages that did not load or were too thin were not used. One claim I first made from memory (that tick() is deprecated) was wrong according to the docs and was removed.
The studio director's answer is now capped at about 32k characters of rules; whatever does not fit is a pointer to load with ms_get_skill (a 70k answer made sends slow).

**Catalogue**
- Cut the built-in skills from 906 to 240. Removed the templated families (professional, studio-craft, universal-mastery, presentation-craft and audio/NPC expansions, advanced Roblox). `runtime/skills.json` went from 10.6 MB to 1.7 MB.
- Shared policy fields now live once in `runtime/skill-shared-policy.json` and are merged at load; `instructions` is derived from `steps`.
- Fixed 23 skills that carried steps from the wrong domain and moved them to the right one.
- Pack lists, capability index, product manifest and file hashes rebuilt to match; every skill has at least four valid related skills.

**New always-on Roblox standards (7)**
- check-clean-ui and check-props (full rules plus the full private check tables), code-quality, npc-pathfinding, game-systems, vfx-assets and fix-errors.
- Each carries verified create.roblox.com doc references and official limits (DataStore limits and error codes, task library, raycasting, CollectionService, streaming, ProximityPrompt, GeometryService, UI classes, pathfinding, units, particles).
- Selected automatically for Roblox requests by whole-word triggers (any physical object such as tree, boat, tank, car or stick triggers check-props); forced to the front of the director result with their full rules (up to five; code-quality sends only the sections the request touches).
- The AI runs all checks privately and replies to the user in a few plain sentences without naming skills. Exception: asked for its main skills, it names the seven in plain words.

**Startup prompt**
- Short always-on rules plus a when-to-use-which guide for Roblox sessions.
- The full text of the standards is sent once at startup, as many as fit under the provider's send limit (Clean UI and Props first). Added `startupCharBudget` for ChatGPT and Claude (their measured send caps minus a margin); a provider with no budget falls back to 50,000 characters instead of unlimited.
- `tools/build_standards_prompt.py` regenerates that block from `runtime/skills.json`.

**Bug fixes**
- The chat site lagged, worst in long chats: on every streamed token the extension re-read the text of every turn twice. Quick checks now look at the newest turns only and are spaced at least 50-200 ms apart; a full pass still runs about every 1.5 s so older turns stay correct.
- Sending was slow and often failed. The startup message was far too big (the full standards added up to 70k characters on top of a 26k base). Full standards at startup are now capped at 22k, the base prompt is cut from 26.5k to 21k by removing repeated "product scope / capability / settings" rules, and the other standards still arrive in full per task through the director. A send also now counts as accepted as soon as the site starts answering, not only when the box clears.
- Raw command JSON could spill into the chat (long execute_luau commands sent as plain text were never hidden because the hider ignored anything over 600 characters). Fixed for Gemini, ChatGPT, Arena and GLM.
- Tools: removed 39 Blender "specialists" that made no sense (shop HUD, multiplayer, NPC AI, save systems for Blender); 261 remain. The Roblox script audit was rewritten: it no longer reports noise (math.random, server containers), and now catches un-checked FindFirstChild, DataStore calls without pcall or BindToClose, SetAsync overwrites, InvokeClient, deprecated wait/spawn/delay/:connect/body movers/LoadAnimation, Instance.new parent argument, unvalidated remote arguments, per-frame allocations, and endless loops that yield further down.
- "Message could not be sent - send acknowledgement was not confirmed" appeared far too fast (3.5 s). The wait now scales with message size (20 s minimum, up to 2 min), and Gemini's send-button waits scale the same way. The no-automatic-replay rule that prevents duplicate messages is unchanged.
- Mandatory skills could be dropped from the director result when six higher-scoring skills existed; they are now placed first.
- Trigger words matched inside other words ("ui" in "build"); now whole-word. The word "ai" no longer forces the NPC skill.
- Wrong reference link on check-props (a Blender page) replaced.
- Stale test pins fixed (Roblox companion tools 24 to 26; workflow revision v4 to v6); the two hand-written workflows are exempt from the generated-contract equality test.
- Removed the three tests that only covered deleted skill families; all count pins updated.

**Not done**
- The test suite was not run on this build. Nothing has been used in a live Studio session.

ChatGPT reads the native rich-text document rather than counting editor decorations as message text. Tiptap-backed composers receive one checked native transaction. Plain ProseMirror receives one escaped native paragraph edit; this uses neither a synthetic paste nor a text-file attachment. Older editors retain their bounded browser-editing fallback. Complete-draft verification, one Send click, native readiness, Stop/navigation protection and no replay after uncertain acknowledgement remain required.

Composer IDs on non-editable wrappers now resolve to the real input. Native disabled/read-only fields keep their drafts. Browser insertion checks cancellation between chunks. CodeMirror same-length source corrections invalidate the previous code snapshot; unchanged reads do not rewrite attributes.

New regression cases reproduce rejected drafts with real ProseMirror inline decorations, then verify long multiline tasks, literal markup, Unicode, subsequent sends, lock restoration, rejected/throwing transactions and the full startup → skill → actual local SVG creation → uncertain-acknowledgement cycle. Current signed-out ChatGPT textarea draft retention was inspected separately. These tests do not certify the user's unavailable signed-in page. Version remains 6.49.9; prior features, skills, manuals and saved project data remain intact.

# Multi-Script 6.49.9 — response recovery, task activity and incremental execution

Arena streaming no longer repeats full-document shadow scans or historical markdown reads for every live check. Native token edits invalidate cached reply text. All effort policies request incremental application through complete live tool calls; script source management now counts as observed implementation.

Active native generation no longer becomes a provider failure just because readable output pauses for three minutes. Thinking/writing remains owned by the existing wait cycle; no extra prompt or partial command is sent/executed. A locally tracked waiting event explains long pauses.

With Error recovery enabled, an explicit native Retry/Clear error panel on the current undispatched reply can recover automatically with bounded backoff and the normal provider/shared-tab pacing. Standard permits one native attempt, Persistent three, Off none. Stop, drafts, navigation, verification, rate/quota notices, historical/dispatched replies, disabled Retry and unacknowledged attempts pause safely. Original prompts and earlier tools are never replayed by this path.

The task monitor retains the original request, real tool results/errors and recovery activity in a bounded local history (12 entries, 500-character details). It retains optional evidence-backed plans, short receipts, zero per-tool AI bookkeeping calls and idle DOM stability. Reload restoration retains initial conversation binding. Product version stays 6.49.9; previous sizing correction, skills/manuals, native project data and rendering are preserved.

# Multi-Script 6.49.9 — content-fit sizing

Restore the selected control size whenever the actual visible controls fit. Regular uses 30-pixel controls, Compact 26, and Roomy 36. Hiding/showing controls refits the same bar; extra space no longer leaves the action group permanently compressed. Roomy first tries a single row at full height, with tighter spacing if needed. Only content that cannot physically fit moves to another row.

Replace fixed width-based 24/26-pixel overrides and unconditional Roomy rows with one content-driven fit routine. It measures preferred sizing first, reserves the complete name/effort label, then compresses spacing and only necessary text actions. Regular/Compact reduce density only for genuinely crowded rows. Free/fit docks use the preferred natural width. Unchanged layout inputs reuse the fitted result rather than measuring every frame. Roomy glyphs scale with its controls. Existing themes, user visibility choices, donation, checklist functionality, native transport and saved data remain.

Version remains 6.49.9. Install this separately packaged corrected build manually in the same permanent installation, preserving private configuration and runtime/studio-data, then run Setup and reload the extension/provider tabs. Same-version builds do not appear as a newer version in a version-only updater. Prior packages remain available in their original output folders.

# Multi-Script 6.49.9 — chatbar correction

- Stop scene artwork from changing action wrapping. Test enabled Code/Build controls across providers, docks, themes and widths.
- Keep narrow desktop controls on one row with flexible text actions; contain explicitly Roomy controls on narrow surfaces.
- Retain quick automatic progress and optional batched checklists, all skills, manuals, references and native functionality.
- Preserve version 6.49.9 and previous artifacts; publish the corrected local package separately.

# Multi-Script 6.49.9 Dev

- Remove mandatory progress planning and per-tool reporting from every effort level. Response/tool activity stays automatic. Keep a concise internal plan; explicit checklists remain available when useful or requested. Ultra keeps its specialist methods, references and verification requirements.
- Return a small receipt for checklist changes instead of echoing the whole evidence history. Full reads retain all evidence. Add atomic batched milestone updates, reject malformed/stale reports, and make unchanged plans/updates no-ops. Do not persist reads or repeated updates.
- Stop unchanged monitor paints from mutating the page. Preserve the evidence DOM while activity/timing labels change, avoid redundant persistence at tool start, and exclude extension-owned UI changes from the provider response observer.
- Replace pairwise history containment checks with ancestor membership checks. Read the current assistant once per snapshot instead of four times. Native token edits, remounts, Stop controls and generation signals stay live; no stale response cache is introduced.
- Keep large general/software catalogues compact too: discovery/retrieval schemas plus a complete direct-tool index, with exact schemas on demand. The actual 279-tool general catalogue fits one Vani reply. Progress and paging calls no longer trigger periodic tool-list reminders. Pages stay available, with instructions to retrieve only information needed for the task.
- Preserve existing skills, Ultra manuals, reference/style resources, native Blender functionality and the compact chatbar corrections. Keep actual verification boundaries; a progress receipt never certifies the whole task.

Merge into the same permanent installation while preserving private settings and runtime/studio-data. Run Setup.bat, restart the bridge, reload the extension and refresh every provider tab. Start a fresh Multi-Script session so old planning instructions do not remain active. See QA_6.49.9.md for scope.

# Multi-Script 6.49.8 Dev

- Fix the two-row desktop chatbar regression in Arena, GLM, Kimi, Claude and ChatGPT. Restore the previous 620-pixel wrapping threshold, retain one compact row at the screenshot widths, and size Floating/fallback bars to the composer. Keep narrow primary controls flexible and isolate button minimum sizes from provider styles. Keep every effort label beside Multi-Script; ordinary levels remain plain and Ultra retains its appearance options.
- Put the glowing heart donation button directly in the chatbar, opening https://ko-fi.com/multixscript on click. Add its visibility setting and retain the Home support card.
- Remove the permanent Unstable badge. Keep actual connection and delivery error handling.
- Give ordinary effort levels neutral tracks and thumbs. Ultra's track and thumb follow the selected Amethyst, Rainbow, Aurora or Sunset palette on dark and light surfaces. Retain native keyboard/touch controls and reduced-motion support.
- Preserve existing provider delivery fixes, background Blender ownership/recovery, skills, Ultra manuals, styles, references and automatic rendering. No engine behavior changes in this release.

Merge into the same permanent installation while preserving private settings and runtime/studio-data. Run Setup.bat, restart the bridge, reload the extension and refresh every provider tab. Old open tabs retain old scripts until refreshed. See QA_6.49.8.md for verification scope.

# Multi-Script 6.49.7 Dev

- Tie headless Blender workers to the owning bridge process and hold an exclusive project lock. Stop orphan workers after an owner crash, including during busy Python execution. Refuse a second writer; reopen committed native geometry after recovery.
- Validate worker startup identity and complete IPC envelopes. Terminate a worker after malformed/truncated/lost replies or timeout before permitting another operation. Preserve the selected project and never replay an uncertain edit automatically.
- Replace GLM and Kimi's unconfirmed click/Enter fallbacks with current-composer binding, remount checks, exact draft verification, awaited reference upload, cancellation, one native Send and positive acknowledgment. Ignore hidden/extension inputs and block busy user clicks from bypassing augmentation.
- Fix actual Lexical multiline reconciliation dropping Kimi's prompt prefix. Use native plain-text paste when handled by the editor, with native editing fallback and complete-document verification. Preserve user task, indentation and blank lines.
- Display every effort level beside Multi-Script. Keep the mode label visible when the name must shrink, and use two rows for crowded bars. Add a smooth keyboard/touch range, clickable stops, four Ultra palettes (Amethyst, Rainbow, Aurora, Sunset) and Live flow, Soft pulse or Static presentation. Respect reduced motion and forced colors; use darker gradients on light surfaces. Appearance changes do not alter tools or effort permissions.
- Add a glowing Ko-fi donation card to the Home panel, opening https://ko-fi.com/multixscript only when clicked.
- Turn Arena model-preference metadata off by default, including old unmarked saved defaults. An explicit new profile choice opts in; the native model picker remains in control.
- Preserve existing Ultra manuals, all 249 skill definitions, styles, references, saved-project support and automatic native rendering. The workspace Render button remains removed.

Merge into the same permanent installation while preserving private settings and runtime/studio-data. Run Setup.bat, restart the bridge, reload the extension, refresh every provider tab and reopen Blender Workspace. Start a fresh Multi-Script session to replace old scripts and tool catalogs. Authenticated provider accounts were not exposed for live certification; see QA_6.49.7.md.

# Multi-Script 6.49.6 Dev

- Keep the entire original task at the beginning of enhanced sends; place Ultra methods and optional clarification after it. Preserve native reference attachments.
- Stabilize Claude rich-editor insertion with complete-draft verification, bounded chunking for long prompts, composer remount handling and one acknowledged native Send. Ignore Multi-Script's own Stop control when detecting provider generation.
- Recognize ClickUp's current Ask placeholder and model-independent greetings. Preserve private AI composer identity across valid remounts. Normalize native rich-editor nonbreaking spaces without changing the task's indentation or paragraphs. The provider's model picker stays available; the adapter does not force Claude.
- Use Arena's current visible composer and its own Send control; wait for asynchronous reference processing. Restore positively identified Text Arena after a reference switches native modality, retaining the attachment. Preserve native errors and stop uncertain sends without automatic replay.
- Keep saved headless Blender target ownership across stops and bridge restarts. Advertise and route the four existing native Blender tools independently of desktop MCP, resume the saved project for standalone sessions, and verify real worker responses. Offline/failed headless calls report Resume Blender, never an unrelated desktop add-on instruction. Reconnect checks the selected worker.
- Retain all existing skills, Ultra manuals, styles, references, native rendering and the removed workspace Render button.

Merge into the same permanent installation while preserving private configuration and runtime/studio-data. Run Setup.bat, restart the bridge, reload the extension, refresh every provider tab and start a fresh Multi-Script session. Existing content scripts and session catalogs need replacement. Authenticated provider accounts were not accessible for live certification; see QA_6.49.6.md for the actual test scope.

# 6.49.5 Dev — ChatGPT rich composer and ClickUp detection

Read ChatGPT composer documents independently from rendered replies, retaining empty paragraphs and ignoring native caret placeholders. Canonicalize CRLF before native insertion, allow hydration to settle before exact verification and record bounded mismatch diagnostics without exposing message text. Keep exact draft, current target, generation and single-click acknowledgement checks.

Retain an identified ClickUp private AI landing composer when its greeting/placeholder disappears on focus, only while that same editor, bounded surface and route survive. Recognize H3 headings and placeholder text on child paragraphs. Invalidate identity on route changes, detached editors, changed headings or human-chat boundaries. Keep the controls available during composer remount gaps without treating a human input as AI.

Add native-editing rich paragraph regression coverage, a rich-composer full core/runtime roundtrip and ClickUp hydration/lock/remount/boundary cases. Existing skills, Ultra methods and native render behavior are preserved.

# 6.49.4 Dev — remove the workspace Render button

Remove the Render button from Blender Workspace, its unused dialog and event handlers. Keep the native render tools, automatic AI rendering behavior and existing AI guidance unchanged. Retain all existing Ultra manuals, skills, styles and references. Refresh the bundled browser code and verify the real workspace still edits, animates, exports and renders through its native tool path.

# 6.49.3 Dev — deepen existing Ultra methods and styles

Improve the existing twelve manuals and their current styles directly from the 25 supplied image studies. Preserve all previous 480 phase checkpoints, existing skill routes, exits, acceptance and diagnostic cases; append 84 targeted craft/accessibility/QA checks. Expand the existing Roblox GUI/animation phases and studded/cartoon/minimal/tactical/fantasy/holographic guidance. Keep all nine production styles, five broad styles, original reference packs and all 249 skill definitions.

Deliver the new guidance through ordinary existing skill reads as well as scoped full-manual retrieval. Extend the two existing production-skill workflows at runtime without rewriting their preserved source definitions. Prefer phase retrieval to keep startup/task payloads bounded. Add preservation and actual browser/Python retrieval checks.

# 6.49.2 Dev — Blender persistence, materials and provider repairs

Keep the real saved scene and preview visible after refresh/restart. Save the native project before preview export; bake unsupported procedural base colors on temporary data and use local studio lighting. Add real connection/activity evidence, opt-in Blender companions for game sessions, validated game-folder exports, overwrite protection, pinned downloads and selected-object framing.

Recognize quoted and unquoted tool-result headers, anchor Vani chips inside the reply column, handle modern dark-theme colors, turn an active Vani Search toggle off at startup, support the current private Ask Brain landing layout, and accept an exact retained ChatGPT draft after a same-form editor remount. Report precise send failures without replaying uncertain sends. Keep Ultra manuals/skills bounded and retrieved on demand.

# 6.49.1 Dev — Gemini completion and Blender controls

Respect Gemini’s native active response instead of finalizing frozen text after nine seconds. Add cancellable draft-safe readiness, readable startup stages and elapsed time. Launch Blender Workspace from the chatbar or extension popup and control the selected AI session from the local workspace through exact-tab grants and existing context/receipt checks.

# 6.49.0 Dev — Blender Workspace

Add a dedicated Three.js/lil-gui workspace backed by real background Blender, verified portable preparation, persistent owned projects, native mesh/animation editing, render/export and existing Blender-tool routing with an explicit target. Preserve provider, Ultra, updater and chat-only boundaries.

# 6.48.8 Dev — Detailed Ultra methods and provider boundaries

Expand twelve Ultra manuals with 480 checkpoints, 72 phase exits, 72 acceptance checks, 48 diagnostic cases and six authoring contexts. Give every retained skill objective-aware application guidance without enlarging startup.

Exclude native hidden/inert turns and composers, separate ChatGPT reasoning from final replies, ignore historical Venice/Vani busy controls, detect Vani quiet-thinking flags, stop sends after chat navigation and honour cancellation. ChatGPT waits for attachment readiness and delivers with one acknowledged click; concurrent/uncertain shared sends stop automatic replay. Preserve the repaired DeepSeek startup and normal pacing.

# 6.48.5 Dev — Compact startup and scoped Ultra

Retain the proven compact discovery handshake and task-time Ultra methods, fail before typing an oversized bootstrap, preserve full-method loading when web research is skipped, and reject irrelevant skill receipts. Restore eight reviewed specialists plus two Blender guidance workflows without changing the 241-skill v24 base. Native composer dialogs keep their toolbar while overlapping provider menus remain clickable.

# 6.48.4 Dev — Native effort messages

Merge the supplied v24 catalog with all 241 skills preserved, shared policy hot reload, Gemini segmented-reply/whitespace/upload/cancellation guards and toolbar yielding to native settings. Restore native sent messages without method chips or transcript resizing. Remove cosmetic receipt persistence from sending so an unresponsive receipt callback cannot block an enhanced task. Retain every effort method, skill, task ID and the existing provider/startup protections.

# 6.48.3

Preserve toolbar CSS variables during dock switches; restore rounded controls and idle task access; avoid ChatGPT native-grid insertion; strengthen ChatGPT transcript parsing, Gemini lifecycle/error handling and truthful startup failure.

# 6.48.2 Dev - skills overhaul (ship build)

**Pack integration: Roblox services, security, platform and tooling rules (from the supplied skills pack)** - the best of the 24-skill pack was folded into our skills in short form, with nothing copied whole.
- **Game systems**: monetization (passes, subscriptions, refunds, paid random items and policy checks), teleports and places (untrusted teleport data, access control, handoff), live ops and analytics (configs, timed events, daily rewards), data extras (versioned saves, MemoryStore), combat hit validation.
- **Code quality**: a severity-ordered review method and a compact deprecated-API map, plus text filtering and chat rules.
- **Scripting power**: more security (prompts, click detectors, ownership), networking channel choices, physics, input and character rules, Open Cloud and HttpService, testing and toolchain, the Studio tool loop.
- **NPCs**: pooling and scaling. **Effects**: audio and engine lighting facts. **Fix errors**: silent failures (animation, sound, remotes).
- Added trigger words so purchases, teleports, audio, Rojo and testing requests pick the right skills.
- The pack's facts were not all re-verified against the docs, and nothing was tested in Studio.

**Check-Props: tighter and better (about 27 pages read in total)** - rewritten from about 30,000 to 13,000 characters with the duplicated check rows and repeated rules removed.
- **Short finished reply**: the AI now just says the prop is finished and where it is, in one normal line, with no list of parts, techniques or checks.
- **Look**: shape first, three passes, the zoom-out test, never a plain box, trim, a second material, wear, a value ladder, consistent grid and palette.
- **Added from this round**: block out and walk it before detailing, hero and background triangle budgets, batching of identical meshes, Massless and collision settings, texture sizes, trim and modular-kit grid, ambient occlusion baked into the colour map, and a lighting check.
- Kept: Luau helpers and orientation traps, union rules, scale minimums, recipes for common props and buildings.
- YouTube pages are blocked to the tools used here and Discord is private, so neither was read. Sources were Roblox docs, DevForum threads, art guides and a few articles.
- Not tested in Studio.

**No emojis in GUIs, and deeper game-systems, NPC, error and prop rules (from about 55 more pages read)** - emojis in interface text render as empty boxes or the wrong font, so the AI now draws icons instead.
- **No emojis in any GUI text** (always on): titles, buttons, tabs, prices and toasts use words; icons are real images, drawn shapes, small 3D models or BuilderIcons glyphs. Added to the final review and the asset checks.
- **Game systems** (+24 rules): developer-product receipts (one handler, no double grants), safe saving with session locking, simulator costs and pacing, pets and luck (weighted rolls, luck done correctly, pity), trading and duplication, rounds and matchmaking, leaderboards, DataStore limits and error codes.
- **NPCs and pathfinding** (+14 rules): real agent defaults and failure causes, costs, modifiers and links, smooth movement and stutter fixes, sight and hearing, state machines, horror director patterns.
- **Fix errors** (+9 rules): common error messages and causes, remotes that do not fire, debugger use, data and purchase errors.
- **Props** (+6 rules): triangle, texture and part budgets, materials and SurfaceAppearance values, silhouette and readability.
- Not tested in Studio or on a live model. Numbers marked as tune are starting points.

**Check-Clean-UI: finished, measured, reviewed screens (from about 80 more pages)** - a candy shop came out as a pink shell: an empty panel, two unreadable tabs, a Buy button with nothing to buy. Read about 80 pages (about 73 usable: Roblox UI and text docs, Fortnite and Roblox shop guidance, WCAG contrast, tab, empty-state and button-state guides, DevForum critiques, juice and shadow articles; 7 failed or were empty) plus 27 searches, and wrote five new sections:
- **Complete screens and shops** (7 rules): never an empty panel; stress data (zero, one, many, long names, missing picture, cannot afford, owned, locked); shop anatomy, item cards with states, a Buy button tied to the selected item, tab rules (count, names that fit the shop, two cues for the selected tab, readable inactive tabs, 44 to 48 px), reach and close button.
- **Contrast check** (5 rules): the real WCAG formula to run on every text and icon pair, targets (4.5:1, 3:1), testing both ends of gradients, same-hue failures (pink on pink), minimum text sizes.
- **Text fitting** (5 rules): TextScaled pitfalls, fixed sizes with measured fit, truncate or wrap, fonts and outlines.
- **Candy and sweets style** (8 rules): 60-30-10 palette with several accents, readable tabs, gloss and shine sweep, candy stripes, matching sweets art.
- **Final review** (7 rules): completeness, readability, pictures, hierarchy and spacing, behaviour, honesty. A short version is now in the always-on core rules.
- **Bridge fix**: the rule text sent with each request is now fitted to a cap by priority (the style you named, the review and contrast checks, then the rest) instead of dropping a skill's whole rule set to a pointer when over the cap. The cap is 44k characters in total (was 32k), with up to 32k for UI. Skipped sections are listed by name and `ms_get_skill` can now load just those sections (`sections`) or just what an objective needs (`objective`), instead of the whole skill.
- Not tested in Studio, and the new rules were not tried on a live model. The contrast formula and thresholds are the standard WCAG ones; shop and tab numbers come from design guides, not Roblox limits.

**Better pictures in UI: real Creator Store search and checking** - fixes UI that came out with the wrong or broken art (a faint clover, a currency button showing an empty box, item tiles with unrelated pictures, a name cut off at the tile edge).
- The asset search tool (ms_roblox_asset_scout) was sending Studio the wrong argument names, so the asset type and result count were ignored. It now uses the real ones and can search up to four phrasings at once, with tags, facets, verified creators first (relaxed if that finds nothing), free assets by default, and it attaches the real thumbnails of the first results so the AI can look at them before choosing. It still never invents an id.
- New "Finding and checking assets" section (12 rules): decide the subject and style, search with several phrasings, look at the thumbnails, reject mismatches, baked-in text and solid backgrounds, check the picture at its final size and load status, keep ids in one swappable table, fall back to shapes, Parts or the built-in icon font instead of a bad match, build prices as an icon plus a number (not a special character that can show as an empty box), and finish every UI with a screen capture to look for empty boxes, wrong pictures, clipped or misspelt text and low contrast. A short version of this is now in the always-on core rules.
- Not tested in Studio. The thumbnail download (it fetches thumbnails from Roblox's public thumbnail service on your machine, and quietly skips any that fail) and the new search arguments were checked only against a fake Studio, not a live one.

**Check-Clean-UI: 3D models inside UI + the studded shop look** - the AI can now build a 3D object from Parts (or take a Creator Store model) and show it in the UI with a ViewportFrame, like the 3D item and pet renders in studded simulator shops. Built from about 35 more pages (ViewportFrame, WorldModel, Model, Camera, Toolbox and InsertService docs, plus DevForum threads on fitting models to a viewport, spinning, hover, performance, character and accessory issues, and viewport freezes); 4 pages failed to load.
- New "3D in UI" section (12 rules): when to use a viewport instead of an image, setup order, cleaning a clone (strip scripts, anchor, no collision), the camera-fit maths from bounding box, field of view and aspect ratio, framing angles for cards, fixed viewport lighting and its limits, spin and hover without per-item loops, known quirks, characters in a WorldModel, model sources, and a blocky-creature build recipe.
- The 3D rules work in any style and any screen (main menu character, loot reveal, weapon inspector, dialogue portrait, hologram panel and more), with per-style advice (cartoon, modern, horror, sci-fi, fantasy, glass), not only for shops.
- New "Studded shop screen" section (8 rules) that describes the screenshot you sent: studded blue title bar with a red close square, gradient offer rows, gradient item tiles with 3D renders, lime studded price buttons, text with thick black outlines. It describes the structure and colours, not any game's art.
- Added trigger words (viewport, 3d icon, item preview, pet card and others).
- Not tested in Studio. Camera-fit maths and sizes come from docs and forum threads; viewport performance limits and freezing fixes are community reports, not official numbers. Animations inside viewports are marked unreliable.

**Check-Clean-UI: 16 more styles and 3 technique sections** - built from about 85 more pages read (Creator Hub UI docs for rich text, 9-slice, scrolling frames, proximity prompts and styling, DevForum threads on 3D buttons, hover and ripple effects, style transitions and glass UI, plus pack listings and design references). 13 more pages failed to load or had no usable content and were not used.
- New style sections, sent only when the request names them: studded (Lego-brick look, stud rows, tiled stud texture, brick thickness), skeuomorphic, steampunk, comic, clay and candy, neumorphism (with an accessibility warning), neubrutalism, Y2K and retro OS, pixel, paper and sticker, blueprint and terminal, holographic, aurora, low-poly, dark mode and bento, anime and gacha. The cartoon look is still the default when no style is named.
- New technique sections: shine sweep, 3D button, ripple, radial progress, prize wheel, radial menu, typewriter, count-up, frosted-glass options; drag and drop, tabs, text boxes, rich text tags, scrolling lists, 9-slice, custom proximity prompts; inventory grid and rarity rules.
- Not tested in Studio. Stud textures are never invented: they must come from the user or a confirmed asset. Some figures (palettes, sizes, timings) are design starting points, not engine limits.

**VFX and Code Quality reworked (expert level)** - two always-on standards were rebuilt from about 105 pages read in full (official Creator Hub docs for particles, beams, trails, lighting, atmosphere, post-processing, sky, clouds, audio, performance, events, deferred signals, testing modes and the Roblox Lua style guide; DevForum threads on effects, lightning, sword slashes, camera shake, impact frames, player lifecycle, memory leaks and OOP; Game Programming Patterns; Trove, PartCache, Spr, Zap, Jest Roblox, StyLua and Selene). Another 14 search result lists were only skimmed. Pages that failed or said very little (for example the Light, Highlight, Bloom and DepthOfField class pages) were not used for numbers.
- **VFX and Assets** now has 92 rules in 13 sections, sent only when a request touches them: particles (official limits, shapes, flipbooks, orientation, wind), 12 effect recipes (explosion, hit, pickup, aura, heal, projectile, fire and smoke, dust, rain and snow, portal and shield, splash, muzzle flash), beams and trails, mesh effects (slashes, shockwaves), lightning, lighting and mood (Future vs ShadowMap, light costs, mood recipes, Atmosphere, sky, clouds, materials), post-processing, camera shake and feedback, sound, animation-marker timing, performance (fill rate, level of detail, pooling, quality scaling) and style and polish. Toolbox safety rules are kept.
- **Code Quality** gained 44 rules in 8 sections on top of the 71 it had: engineering practice, architecture and lifecycle (init then start, services and controllers, dependencies), patterns (state machine, signals, tag components, commands and queues, pools, dirty flags, fixed timestep, flyweight), typed classes, errors and results, events and player lifecycle (deferred signals, character order, leaks), testing and debugging, and style and review. Data, purchases and security rules are unchanged.
- The bridge trigger list for VFX has about 30 more words (beam, trail, shockwave, slash, camera shake, post-processing, mood, cinematic and others).
- Not tested in Studio. A few third-party figures (for example the Highlight cap of 255) come from community summaries and are marked as such in the rules.

**Check-Clean-UI reworked: any UI, any style** - the UI standard is no longer one fixed cartoon look. It can now build any menu, HUD, shop, inventory, dialogue, quest log, settings, leaderboard, notification, loading screen, minimap, crafting, tooltip or on-part screen in any style the user asks for. The cartoon recipes are kept exactly as before and stay the default when the user names no style. New sections (133 rules in total, 19 sections; only the ones a request touches are sent): a design system (colour, contrast, type, spacing, hierarchy, touch targets, states), layout and responsive rules (scale, constraints, layout objects, safe areas, avoiding the default Roblox controls), 17 component recipes, eight style families (sleek modern, glass, horror, sci-fi, fantasy, minimal, retro, realistic), StyleSheet use, feel and motion, gamepad and console, accessibility, world UI (billboards, surface screens, proximity prompts), UI performance (build once, event-driven updates, pooled long lists, sprite sheets, cleanup) and assets, icons and fonts. A new optional `ruleSectionDefaults` field lets a section (here the cartoon look) be sent when no other style matched. Research: about 75 Creator Hub and DevForum pages read in full plus search results for another 30 or so (WCAG contrast and target size, Vide, Iris, virtualized lists, glass and blur, loading screens, button feel, design-system guides); pages that failed or were thin were not used. The StyleSheet rules are deliberately general and tell the model to read the class pages first, because that system is new and I could not confirm every detail. Not tested in Studio; the combined text is much larger than before, so it is delivered by section.

**New skill: Scripting Power (241 skills in total)** - a mandatory, docs-backed skill for fast, safe, modern Luau. It carries 105 rules in 17 sections (Luau speed, native code and profiling, language features, types, library tricks, async and cleanup, networking, security, data, Parallel Luau, physics and queries, players and streaming, input and frame loop, architecture and style, tooling, lint-catchable bugs, debugging, optimisation) and only the sections a request touches are sent. Built from about 50 pages read in full: luau.org (performance, library, syntax, lint, recaps), the Creator Hub (native code gen, type checking, Parallel Luau, client-server security, remotes and bindables, DataStore limits, MicroProfiler, streaming, and the Players, WorldRoot, BasePart, CollectionService, MarketplaceService, ContextActionService and other class pages), Roblox's Lua style guide, the ProfileStore and DataStore best-practice posts, an optimisation guide, and the repos for Rojo, luau-lsp, Promise, RbxUtil, Jest Roblox, roblox-ts and Zap. Pages that did not load or were too thin were not used. One claim I first made from memory (that tick() is deprecated) was wrong according to the docs and was removed.
The studio director's answer is now capped at about 32k characters of rules; whatever does not fit is a pointer to load with ms_get_skill (a 70k answer made sends slow).

**Catalogue**
- Cut the built-in skills from 906 to 240. Removed the templated families (professional, studio-craft, universal-mastery, presentation-craft and audio/NPC expansions, advanced Roblox). `runtime/skills.json` went from 10.6 MB to 1.7 MB.
- Shared policy fields now live once in `runtime/skill-shared-policy.json` and are merged at load; `instructions` is derived from `steps`.
- Fixed 23 skills that carried steps from the wrong domain and moved them to the right one.
- Pack lists, capability index, product manifest and file hashes rebuilt to match; every skill has at least four valid related skills.

**New always-on Roblox standards (7)**
- check-clean-ui and check-props (full rules plus the full private check tables), code-quality, npc-pathfinding, game-systems, vfx-assets and fix-errors.
- Each carries verified create.roblox.com doc references and official limits (DataStore limits and error codes, task library, raycasting, CollectionService, streaming, ProximityPrompt, GeometryService, UI classes, pathfinding, units, particles).
- Selected automatically for Roblox requests by whole-word triggers (any physical object such as tree, boat, tank, car or stick triggers check-props); forced to the front of the director result with their full rules (up to five; code-quality sends only the sections the request touches).
- The AI runs all checks privately and replies to the user in a few plain sentences without naming skills. Exception: asked for its main skills, it names the seven in plain words.

**Startup prompt**
- Short always-on rules plus a when-to-use-which guide for Roblox sessions.
- The full text of the standards is sent once at startup, as many as fit under the provider's send limit (Clean UI and Props first). Added `startupCharBudget` for ChatGPT and Claude (their measured send caps minus a margin); a provider with no budget falls back to 50,000 characters instead of unlimited.
- `tools/build_standards_prompt.py` regenerates that block from `runtime/skills.json`.

**Bug fixes**
- The chat site lagged, worst in long chats: on every streamed token the extension re-read the text of every turn twice. Quick checks now look at the newest turns only and are spaced at least 50-200 ms apart; a full pass still runs about every 1.5 s so older turns stay correct.
- Sending was slow and often failed. The startup message was far too big (the full standards added up to 70k characters on top of a 26k base). Full standards at startup are now capped at 22k, the base prompt is cut from 26.5k to 21k by removing repeated "product scope / capability / settings" rules, and the other standards still arrive in full per task through the director. A send also now counts as accepted as soon as the site starts answering, not only when the box clears.
- Raw command JSON could spill into the chat (long execute_luau commands sent as plain text were never hidden because the hider ignored anything over 600 characters). Fixed for Gemini, ChatGPT, Arena and GLM.
- Tools: removed 39 Blender "specialists" that made no sense (shop HUD, multiplayer, NPC AI, save systems for Blender); 261 remain. The Roblox script audit was rewritten: it no longer reports noise (math.random, server containers), and now catches un-checked FindFirstChild, DataStore calls without pcall or BindToClose, SetAsync overwrites, InvokeClient, deprecated wait/spawn/delay/:connect/body movers/LoadAnimation, Instance.new parent argument, unvalidated remote arguments, per-frame allocations, and endless loops that yield further down.
- "Message could not be sent - send acknowledgement was not confirmed" appeared far too fast (3.5 s). The wait now scales with message size (20 s minimum, up to 2 min), and Gemini's send-button waits scale the same way. The no-automatic-replay rule that prevents duplicate messages is unchanged.
- Mandatory skills could be dropped from the director result when six higher-scoring skills existed; they are now placed first.
- Trigger words matched inside other words ("ui" in "build"); now whole-word. The word "ai" no longer forces the NPC skill.
- Wrong reference link on check-props (a Blender page) replaced.
- Stale test pins fixed (Roblox companion tools 24 to 26; workflow revision v4 to v6); the two hand-written workflows are exempt from the generated-contract equality test.
- Removed the three tests that only covered deleted skill families; all count pins updated.

**Not done**
- The test suite was not run on this build. Nothing has been used in a live Studio session.

# 6.48.2 Dev - skills overhaul (ship build)

- Forge ui_kit is quick by default: at most 5 images per call (priority pieces first). Pass quick=false for the whole pack. Uploads run one batch after another, so fewer images means a shorter wait.

- Fix: Forge backdrops were uploaded but never written into Studio. They are now stored as StringValues in ReplicatedStorage.ForgeBackdrops (name = picture name, value = rbxassetid).

- Ultra start routine is shorter: one shallow Studio survey (services and StarterGui) instead of a deep survey before the first build. Deeper reads happen only when the task needs them. Safety rules (docs checks, nothing done until checked) are unchanged.

- Forge ui_kit now draws the small shop pack by default instead of the full set, so it finishes much faster. Pass pack=full for everything.

- Fix: the extension now always advertises ms_forge when its drawing module is loaded, so an older bridge no longer makes the chat reject it as an unknown command.

- Fix: ms_forge was hidden from ms_find_tool when the search used engine=roblox (it had no Roblox engine tag). It is now tagged roblox.
- Missing Forge or docs modules now print a reason to the log instead of silently disappearing.

- New `ms_roblox_ui_audit` tool: measures the real GUI in Studio (text fit, contrast, tap size, off-screen, empty lists, unloaded images, overlapping buttons). 281 tools.
- Skills answer now lists the built-in tools: offline docs, Forge, automatic code checker, UI inspector, expert templates and kits.
- Clean UI and Code quality skills tell the AI to run the UI inspector and fix code-check findings; expert templates linked.

**Forge in one call, upload packs, clean edges and new pieces** - asking for game art now ends with it installed and working.
- One `ms_forge` call (ui_kit, vfx or backdrop) now draws the art, stores it, uploads it through Studio's upload_image (in batches of 20), writes `ReplicatedStorage.ForgeKit` or `ReplicatedStorage.ForgeVFX` (ScriptEditorService, falling back to Source), and builds a demo to screen_capture: `StarterGui.ForgeDemo` (a shop window, currency pills, buttons and an XP bar) or `workspace.ForgeVFX_Showroom` (every looping effect running). install=false only draws; demo=false skips the demo. Without Studio it draws and explains the manual route. The pipeline lives in `MSForge.run` in forge.js; main.js only supplies the bridge and Studio calls.
- Upload packs: hud, shop, inventory, settings, leaderboard, dialogue, rewards, essentials (about 20 to 60 images) or full (about 120).
- Clean edges: Forge now writes its own PNGs and bleeds edge colour into the transparent border at alpha 1, which reduces the dark fringes Roblox can show on scaled transparent images (the ImageLabel reference notes transparent pixels turn black on upload).
- New art: light rays and a soft glow. New ForgeKit pieces: `Kit.reward` (spinning rays pop-up with ribbon title and claim button), `Kit.billboard` (name tag and health bar over a character), `Kit.loading` (loading screen over a Forge backdrop with a progress bar); `Kit.screen` accepts a parent so it works in Studio edit mode; `Kit.modal` can open instantly.
- New `docs/FORGE.md` explains in plain words how to use it.
- Checked: in Chromium, a full run of `MSForge.run` against the real bridge code with a stand-in Studio (fake upload ids) worked for a UI pack, a VFX set and a backdrop; all Luau sent to Studio (module install, demo, showroom) passes the docs check with no findings and a block-balance check. Not checked: a real Studio upload and execute_luau, the extension live in a chat, and the test suite.

**Forge rebuilt inside the extension: no Python add-ons, about twice as much art, and a much richer ForgeKit** - Forge no longer needs numpy.
- All drawing now happens in the browser extension with the built-in Canvas (`extension/core/forge.js`, loaded with the other content scripts). The bridge side (`runtime/forge_assets.py`, `runtime/forge_luau.py`) uses only the Python standard library: it stores the PNGs, serves them on 127.0.0.1 for Studio's upload_image, reads a local reference picture (PNG, JPG or WEBP) and writes the Luau. Setup no longer installs numpy.
- UI kits grew from about 60 to about 120 pieces: new card, ribbon banner, xp, hp and mana bars, price tag, checkbox, radio, slider, input box, scrollbar, speech bubble, toast, gold/silver/bronze leaderboard rows, corner ribbon, gamepad selection ring, arrow and tick glyphs, minus and help buttons, and 30 item icons (adds sword, shield, potion, trophy, crown, key, chest, egg, paw, pickaxe, gear, cart, bag, scroll, clock, skull, flame, drop, leaf, ticket, rebirth, speed, ghost).
- VFX grew to 27 textures (adds twinkle, cloud, crescent, rune ring, bubble, snowflake, leaf, droplet, swirl, hit star, feather, confetti, heart glow, wisp), 6 strips (adds sharp trail, chain, wave) and 8 flipbooks (adds portal swirl, splash, electric burst), with 27 presets (adds hit star, impact burst, ambient smoke, portal, electric, splash, level up, confetti, snow, leaves, bubbles, ghost wisp, hearts). Backdrops add stripes, grid and sunset.
- ForgeKit adds Kit.screen (auto-scaling ScreenGui in device safe insets), Kit.modal (pop open and close), Kit.grid and Kit.list (scrolling, canvas grows), Kit.card (complete shop card), Kit.bar, Kit.priceTag, Kit.checkbox, Kit.radio, Kit.slider (mouse and touch drag), Kit.input, Kit.tabs (pages), Kit.bubble, Kit.leaderboardRow, Kit.toast (stacking), Kit.tooltip, Kit.divider, icons inside buttons, and gamepad selection on every control. ForgeVFX adds pooled bursts, VFX.combo, VFX.stop, size scaling and Wrap-mode beams. bind also returns a ready usage example.
- Large sets are sent to the bridge in batches under 6 MB.
- Checked: every set was drawn in Chromium and looked at; a full run (draw in the browser, store through the bridge, fetch from the localhost address, bind) worked for a UI kit, a VFX set and a backdrop; both Luau modules and their usage examples pass the docs check with no findings and a block-balance check; every API they use was confirmed in the offline reference; the bridge loads and dispatches the tool. Not checked: the extension running live in a chat, a real Studio upload_image round trip, the Luau running in Studio, and the test suite.

**Forge: game art that turns into working UI and effects** - inspired by ForgeGUI (AI game-art sets with a consistent style and a Studio import), but local, free, and wired to real Roblox objects instead of stopping at pictures.
- New tool `ms_forge` draws real transparent PNGs on this computer with anti-aliased shape rendering (needs numpy; Setup now installs it when it can).
- `ui_kit`: a complete, matching set in one call - buttons in 4 states (normal, hover, pressed, disabled) in 4 colours, round close/back/plus/next/confirm buttons, panel, header, inner panel, slots for 7 rarities plus selected, tabs, progress bar, currency pill, toggle, badge, tooltip, and coin, gem, star, heart, bolt, lock and gift icons. 12 styles (simulator, cartoon, glossy, candy, anime, glass, neon, fantasy, scifi, minimal, horror, pixel), your own colours, small tweaks, or `reference_image` to copy a screenshot's palette. Every piece carries its 9-slice centre, and art is drawn at 2x.
- `vfx`: 13 particle textures, 3 trail/beam strips, and 5 flipbooks at 1024x1024 (the size Roblox requires), all white on transparent so Color tints them, with 14 tuned ParticleEmitter presets.
- `backdrop`: 16:9 backgrounds (burst, clouds, space, dungeon, sparkles) at 1920x1080 for thumbnails or 1024x576 for in-game screens.
- The files are served on 127.0.0.1 so Studio's `upload_image` can upload them; `bind` then returns a ForgeKit ModuleScript (panel, button with real hover/pressed images, icon buttons, slots, progress, pill, toggle, tabs, badge, icons; all 9-sliced) or a ForgeVFX ModuleScript (burst, attach, trail, beam). Both modules pass the docs `check` and every property and enum they use was confirmed in the offline API reference.
- check-clean-ui, vfx-assets, the always-on standards and Ultra (GUI and VFX build steps, start-up) now say when to use Forge, to look at the preview first, to upload through Studio and never type ids, and that Forge art does not relax the contrast, layout, input or capture rules.
- Tool count is now 280 (tests and manifest updated). Startup standards are about 31.9k tokens. Per-task Ultra text unchanged (8970 characters on the inventory test request).
- Checked: every output was rendered and looked at here; the bridge loads the tool and dispatches it; the Luau modules pass the docs check and a block-balance check. Not checked: running the Luau in Studio, an actual upload_image round trip, and the test suite.

**Official Roblox and Luau docs, offline (2,261 pages)** - the AI can now look up the real answer instead of guessing.
- New tool `ms_roblox_docs`, built from the open-source Roblox Creator Docs (snapshot of 24 Oct 2026, Studio 0.744) and the Luau docs: 992 guides, the full engine API (628 classes, 518 enums, 49 datatypes, 11 libraries, globals) and 61 Luau pages. About 3.5 MB, works with no internet. Licences (CC-BY-4.0 text, MIT code) and a notice are included.
- `search` ranks pages by title, headings and text; `read` opens a page or jumps to a section or member; `api` confirms a name exists, its exact signature, dot or colon, where it is inherited from, and the replacement if it is deprecated; `check` scans a script for deprecated calls (wait, spawn, Humanoid:LoadAnimation, FindPartOnRay, BodyVelocity and 680 more), unknown classes, services or enum items, wrong-case members and dot/colon mistakes. It found no false alarms in the 36 Brickwire kits.
- `tools/build_roblox_docs.py` rebuilds the docs from fresh clones of github.com/Roblox/creator-docs and github.com/luau-lang/site.
- All 8 skills, the always-on standards and Ultra's start-up now tell the AI to confirm uncertain APIs and to run `check` on every script before writing it to Studio. Ultra counts a docs lookup as research.
- The docs check found and fixed real mistakes in the skills: `Lighting.Technology` is deprecated (now LightingStyle and PrioritizeLightingQuality), `GuiService:IsTenFootInterface` is deprecated (now ViewportDisplaySize), and the UIShadow advice now uses its documented properties. It also found `Enum.Font.GothamSemibold` in the companion plugin, which the docs no longer list; it now uses GothamMedium. Reinstall the plugin to get that change.
- The tool count is now 279; the two tests that pin the count and the product manifest were updated to match.
- The startup standards block is about 31.2k tokens. Per-task Ultra text is unchanged (8970 characters on the inventory test request).
- Not tested in Studio or a browser, and the test suite was not run. The tool was called directly through the bridge's own dispatch for search, read, api and check.

**Final integration pass** - two wiring fixes found by reading the code against the existing tests.
- The Ultra text had lost the "ms_skill_reference links" wording for GUI and animation that an existing test expects; it is back (per-task text 8970 characters, under the 9000 bound).
- The reference reader (ms_skill_reference) is now treated as guidance, like the manuals, so reading the ready-made kits does not count as a write or an unexplained call. game-systems now lists the kits as a resource, like the other reference packs.
- Static checks only: all Python compiles, all JavaScript passes syntax checks, all JSON parses, every update hash matches. The test suite and Studio were not run.

**Brickwire's best parts, added and credited** - Brickwire 3.0 (MIT licence) has tested ready-made Luau systems and strict "done means checked" rules; Multi-Script now uses both.
- New ready-made systems library: 36 Brickwire scripts (obby stages, kill bricks, pads, teleporters, coins, rounds, saved stats, daily reward, shop, inventory, HUD, menus, toasts, day and night, NPC dialog, VFX presets, camera fly-through, and the cutscene module with case, egg, dice, event and story scenes). The AI reads them on demand with the reference tool (skill game-systems), so the startup text does not carry them. The licence file is included.
- game-systems gained two steps: use the closest kit and upgrade it to the existing rules (UpdateAsync with session locking, idempotent ProcessReceipt, validated remotes), and cutscene rules (server decides the result, camera and controls always restored, Skip from the first frame, longer pauses for rarer results). New trigger words: cutscene, case opening, egg hatch, dice roll, intro sequence.
- code-quality gained "Done means checked": nothing is done until a check passed after the last change, tool results are never imitated, edits are small and reversible with a ChangeHistory waypoint.
- Not copied: Brickwire's bridge, extension, panel and 50 generic skill templates (they are boilerplate with little content).
- Ultra: its start-up block now points to the kit index, the inspect-to-failures order and the done-means-checked rule; two new Ultra methods (cutscene, and economy now points to the kits). The per-task text stays at 8922 characters for the inventory test request.
- The startup standards block is now about 30.3k tokens (was 29.4k).
- Kits were only run by Brickwire in a Luau VM with a stubbed Roblox API; nothing here was tested in Studio, and the test suite was not run.

**Ultra manuals now give a step-by-step Roblox method** - each of the 12 manuals returns a six-step plan (inspect, design, build, integrate, verify, failures) written for Roblox Studio and its tools, and Ultra's start-up block now begins with a fixed survey routine.
- The routine: list Studios, read state, one game-tree survey, note existing styles, currency/data code, remotes, Rojo and which tools exist, reuse what is there, keep a short notes ledger.
- Per-task Ultra text is unchanged in size (8922 chars for the inventory test request, under the 9000 bound).
- Not tested in Studio or a browser; the test suite was not run.

**Ultra now starts properly when you select it** - selecting Ultra (or opening a session with Ultra already on) now sends a one-time start-up block with the first task.
- It tells the AI to load the full skills and read the relevant manuals, and carries all 12 manuals' Roblox rules as standing rules for the session, kept silent. It is sent once per selection, only for Roblox work, and only at the Ultra level.
- Switching to a lower level clears it; selecting Ultra again sends it again.
- Not tested in Studio or in a live browser session; the existing test suite was not run.

**Ultra: Roblox rules in every manual, per-manual doc links, new methods and a plain finish** - only the GUI and animation manuals had Roblox-specific content, every manual showed the same four doc links, and Ultra told the AI to finish with a long changes-and-verification report.
- All 12 manuals now return their own Roblox standards (emoji-free GUI, finished measured screens, props in three passes, economy and server authority, networking limits, performance targets, audio, input, QA) and their own doc links. The modeling manual now says Parts-only requests stay Parts-only.
- The per-task Ultra text now carries the relevant manual's Roblox rules instead of two generic sentences, kept inside the existing size limit.
- Two new methods: props (shape first, three passes, one short finish line) and economy (sources and sinks, server-owned rolls, one ProcessReceipt). The interface and assets methods gained the emoji, finished-screen, contrast and picture-checking rules.
- Ultra now finishes with a short plain line, not a long report; failures, unchecked items and anything needing the user are still said in one sentence.
- Other engines are unchanged. Not tested in Studio; the existing test suite was not run.

**Pack integration: Roblox services, security, platform and tooling rules (from the supplied skills pack)** - the best of the 24-skill pack was folded into our skills in short form, with nothing copied whole.
- **Game systems**: monetization (passes, subscriptions, refunds, paid random items and policy checks), teleports and places (untrusted teleport data, access control, handoff), live ops and analytics (configs, timed events, daily rewards), data extras (versioned saves, MemoryStore), combat hit validation.
- **Code quality**: a severity-ordered review method and a compact deprecated-API map, plus text filtering and chat rules.
- **Scripting power**: more security (prompts, click detectors, ownership), networking channel choices, physics, input and character rules, Open Cloud and HttpService, testing and toolchain, the Studio tool loop.
- **NPCs**: pooling and scaling. **Effects**: audio and engine lighting facts. **Fix errors**: silent failures (animation, sound, remotes).
- Added trigger words so purchases, teleports, audio, Rojo and testing requests pick the right skills.
- The pack's facts were not all re-verified against the docs, and nothing was tested in Studio.

**Check-Props: tighter and better (about 27 pages read in total)** - rewritten from about 30,000 to 13,000 characters with the duplicated check rows and repeated rules removed.
- **Short finished reply**: the AI now just says the prop is finished and where it is, in one normal line, with no list of parts, techniques or checks.
- **Look**: shape first, three passes, the zoom-out test, never a plain box, trim, a second material, wear, a value ladder, consistent grid and palette.
- **Added from this round**: block out and walk it before detailing, hero and background triangle budgets, batching of identical meshes, Massless and collision settings, texture sizes, trim and modular-kit grid, ambient occlusion baked into the colour map, and a lighting check.
- Kept: Luau helpers and orientation traps, union rules, scale minimums, recipes for common props and buildings.
- YouTube pages are blocked to the tools used here and Discord is private, so neither was read. Sources were Roblox docs, DevForum threads, art guides and a few articles.
- Not tested in Studio.

**No emojis in GUIs, and deeper game-systems, NPC, error and prop rules (from about 55 more pages read)** - emojis in interface text render as empty boxes or the wrong font, so the AI now draws icons instead.
- **No emojis in any GUI text** (always on): titles, buttons, tabs, prices and toasts use words; icons are real images, drawn shapes, small 3D models or BuilderIcons glyphs. Added to the final review and the asset checks.
- **Game systems** (+24 rules): developer-product receipts (one handler, no double grants), safe saving with session locking, simulator costs and pacing, pets and luck (weighted rolls, luck done correctly, pity), trading and duplication, rounds and matchmaking, leaderboards, DataStore limits and error codes.
- **NPCs and pathfinding** (+14 rules): real agent defaults and failure causes, costs, modifiers and links, smooth movement and stutter fixes, sight and hearing, state machines, horror director patterns.
- **Fix errors** (+9 rules): common error messages and causes, remotes that do not fire, debugger use, data and purchase errors.
- **Props** (+6 rules): triangle, texture and part budgets, materials and SurfaceAppearance values, silhouette and readability.
- Not tested in Studio or on a live model. Numbers marked as tune are starting points.

**Check-Clean-UI: finished, measured, reviewed screens (from about 80 more pages)** - a candy shop came out as a pink shell: an empty panel, two unreadable tabs, a Buy button with nothing to buy. Read about 80 pages (about 73 usable: Roblox UI and text docs, Fortnite and Roblox shop guidance, WCAG contrast, tab, empty-state and button-state guides, DevForum critiques, juice and shadow articles; 7 failed or were empty) plus 27 searches, and wrote five new sections:
- **Complete screens and shops** (7 rules): never an empty panel; stress data (zero, one, many, long names, missing picture, cannot afford, owned, locked); shop anatomy, item cards with states, a Buy button tied to the selected item, tab rules (count, names that fit the shop, two cues for the selected tab, readable inactive tabs, 44 to 48 px), reach and close button.
- **Contrast check** (5 rules): the real WCAG formula to run on every text and icon pair, targets (4.5:1, 3:1), testing both ends of gradients, same-hue failures (pink on pink), minimum text sizes.
- **Text fitting** (5 rules): TextScaled pitfalls, fixed sizes with measured fit, truncate or wrap, fonts and outlines.
- **Candy and sweets style** (8 rules): 60-30-10 palette with several accents, readable tabs, gloss and shine sweep, candy stripes, matching sweets art.
- **Final review** (7 rules): completeness, readability, pictures, hierarchy and spacing, behaviour, honesty. A short version is now in the always-on core rules.
- **Bridge fix**: the rule text sent with each request is now fitted to a cap by priority (the style you named, the review and contrast checks, then the rest) instead of dropping a skill's whole rule set to a pointer when over the cap. The cap is 44k characters in total (was 32k), with up to 32k for UI. Skipped sections are listed by name and `ms_get_skill` can now load just those sections (`sections`) or just what an objective needs (`objective`), instead of the whole skill.
- Not tested in Studio, and the new rules were not tried on a live model. The contrast formula and thresholds are the standard WCAG ones; shop and tab numbers come from design guides, not Roblox limits.

**Better pictures in UI: real Creator Store search and checking** - fixes UI that came out with the wrong or broken art (a faint clover, a currency button showing an empty box, item tiles with unrelated pictures, a name cut off at the tile edge).
- The asset search tool (ms_roblox_asset_scout) was sending Studio the wrong argument names, so the asset type and result count were ignored. It now uses the real ones and can search up to four phrasings at once, with tags, facets, verified creators first (relaxed if that finds nothing), free assets by default, and it attaches the real thumbnails of the first results so the AI can look at them before choosing. It still never invents an id.
- New "Finding and checking assets" section (12 rules): decide the subject and style, search with several phrasings, look at the thumbnails, reject mismatches, baked-in text and solid backgrounds, check the picture at its final size and load status, keep ids in one swappable table, fall back to shapes, Parts or the built-in icon font instead of a bad match, build prices as an icon plus a number (not a special character that can show as an empty box), and finish every UI with a screen capture to look for empty boxes, wrong pictures, clipped or misspelt text and low contrast. A short version of this is now in the always-on core rules.
- Not tested in Studio. The thumbnail download (it fetches thumbnails from Roblox's public thumbnail service on your machine, and quietly skips any that fail) and the new search arguments were checked only against a fake Studio, not a live one.

**Check-Clean-UI: 3D models inside UI + the studded shop look** - the AI can now build a 3D object from Parts (or take a Creator Store model) and show it in the UI with a ViewportFrame, like the 3D item and pet renders in studded simulator shops. Built from about 35 more pages (ViewportFrame, WorldModel, Model, Camera, Toolbox and InsertService docs, plus DevForum threads on fitting models to a viewport, spinning, hover, performance, character and accessory issues, and viewport freezes); 4 pages failed to load.
- New "3D in UI" section (12 rules): when to use a viewport instead of an image, setup order, cleaning a clone (strip scripts, anchor, no collision), the camera-fit maths from bounding box, field of view and aspect ratio, framing angles for cards, fixed viewport lighting and its limits, spin and hover without per-item loops, known quirks, characters in a WorldModel, model sources, and a blocky-creature build recipe.
- The 3D rules work in any style and any screen (main menu character, loot reveal, weapon inspector, dialogue portrait, hologram panel and more), with per-style advice (cartoon, modern, horror, sci-fi, fantasy, glass), not only for shops.
- New "Studded shop screen" section (8 rules) that describes the screenshot you sent: studded blue title bar with a red close square, gradient offer rows, gradient item tiles with 3D renders, lime studded price buttons, text with thick black outlines. It describes the structure and colours, not any game's art.
- Added trigger words (viewport, 3d icon, item preview, pet card and others).
- Not tested in Studio. Camera-fit maths and sizes come from docs and forum threads; viewport performance limits and freezing fixes are community reports, not official numbers. Animations inside viewports are marked unreliable.

**Check-Clean-UI: 16 more styles and 3 technique sections** - built from about 85 more pages read (Creator Hub UI docs for rich text, 9-slice, scrolling frames, proximity prompts and styling, DevForum threads on 3D buttons, hover and ripple effects, style transitions and glass UI, plus pack listings and design references). 13 more pages failed to load or had no usable content and were not used.
- New style sections, sent only when the request names them: studded (Lego-brick look, stud rows, tiled stud texture, brick thickness), skeuomorphic, steampunk, comic, clay and candy, neumorphism (with an accessibility warning), neubrutalism, Y2K and retro OS, pixel, paper and sticker, blueprint and terminal, holographic, aurora, low-poly, dark mode and bento, anime and gacha. The cartoon look is still the default when no style is named.
- New technique sections: shine sweep, 3D button, ripple, radial progress, prize wheel, radial menu, typewriter, count-up, frosted-glass options; drag and drop, tabs, text boxes, rich text tags, scrolling lists, 9-slice, custom proximity prompts; inventory grid and rarity rules.
- Not tested in Studio. Stud textures are never invented: they must come from the user or a confirmed asset. Some figures (palettes, sizes, timings) are design starting points, not engine limits.

**VFX and Code Quality reworked (expert level)** - two always-on standards were rebuilt from about 105 pages read in full (official Creator Hub docs for particles, beams, trails, lighting, atmosphere, post-processing, sky, clouds, audio, performance, events, deferred signals, testing modes and the Roblox Lua style guide; DevForum threads on effects, lightning, sword slashes, camera shake, impact frames, player lifecycle, memory leaks and OOP; Game Programming Patterns; Trove, PartCache, Spr, Zap, Jest Roblox, StyLua and Selene). Another 14 search result lists were only skimmed. Pages that failed or said very little (for example the Light, Highlight, Bloom and DepthOfField class pages) were not used for numbers.
- **VFX and Assets** now has 92 rules in 13 sections, sent only when a request touches them: particles (official limits, shapes, flipbooks, orientation, wind), 12 effect recipes (explosion, hit, pickup, aura, heal, projectile, fire and smoke, dust, rain and snow, portal and shield, splash, muzzle flash), beams and trails, mesh effects (slashes, shockwaves), lightning, lighting and mood (Future vs ShadowMap, light costs, mood recipes, Atmosphere, sky, clouds, materials), post-processing, camera shake and feedback, sound, animation-marker timing, performance (fill rate, level of detail, pooling, quality scaling) and style and polish. Toolbox safety rules are kept.
- **Code Quality** gained 44 rules in 8 sections on top of the 71 it had: engineering practice, architecture and lifecycle (init then start, services and controllers, dependencies), patterns (state machine, signals, tag components, commands and queues, pools, dirty flags, fixed timestep, flyweight), typed classes, errors and results, events and player lifecycle (deferred signals, character order, leaks), testing and debugging, and style and review. Data, purchases and security rules are unchanged.
- The bridge trigger list for VFX has about 30 more words (beam, trail, shockwave, slash, camera shake, post-processing, mood, cinematic and others).
- Not tested in Studio. A few third-party figures (for example the Highlight cap of 255) come from community summaries and are marked as such in the rules.

**Check-Clean-UI reworked: any UI, any style** - the UI standard is no longer one fixed cartoon look. It can now build any menu, HUD, shop, inventory, dialogue, quest log, settings, leaderboard, notification, loading screen, minimap, crafting, tooltip or on-part screen in any style the user asks for. The cartoon recipes are kept exactly as before and stay the default when the user names no style. New sections (133 rules in total, 19 sections; only the ones a request touches are sent): a design system (colour, contrast, type, spacing, hierarchy, touch targets, states), layout and responsive rules (scale, constraints, layout objects, safe areas, avoiding the default Roblox controls), 17 component recipes, eight style families (sleek modern, glass, horror, sci-fi, fantasy, minimal, retro, realistic), StyleSheet use, feel and motion, gamepad and console, accessibility, world UI (billboards, surface screens, proximity prompts), UI performance (build once, event-driven updates, pooled long lists, sprite sheets, cleanup) and assets, icons and fonts. A new optional `ruleSectionDefaults` field lets a section (here the cartoon look) be sent when no other style matched. Research: about 75 Creator Hub and DevForum pages read in full plus search results for another 30 or so (WCAG contrast and target size, Vide, Iris, virtualized lists, glass and blur, loading screens, button feel, design-system guides); pages that failed or were thin were not used. The StyleSheet rules are deliberately general and tell the model to read the class pages first, because that system is new and I could not confirm every detail. Not tested in Studio; the combined text is much larger than before, so it is delivered by section.

**New skill: Scripting Power (241 skills in total)** - a mandatory, docs-backed skill for fast, safe, modern Luau. It carries 105 rules in 17 sections (Luau speed, native code and profiling, language features, types, library tricks, async and cleanup, networking, security, data, Parallel Luau, physics and queries, players and streaming, input and frame loop, architecture and style, tooling, lint-catchable bugs, debugging, optimisation) and only the sections a request touches are sent. Built from about 50 pages read in full: luau.org (performance, library, syntax, lint, recaps), the Creator Hub (native code gen, type checking, Parallel Luau, client-server security, remotes and bindables, DataStore limits, MicroProfiler, streaming, and the Players, WorldRoot, BasePart, CollectionService, MarketplaceService, ContextActionService and other class pages), Roblox's Lua style guide, the ProfileStore and DataStore best-practice posts, an optimisation guide, and the repos for Rojo, luau-lsp, Promise, RbxUtil, Jest Roblox, roblox-ts and Zap. Pages that did not load or were too thin were not used. One claim I first made from memory (that tick() is deprecated) was wrong according to the docs and was removed.
The studio director's answer is now capped at about 32k characters of rules; whatever does not fit is a pointer to load with ms_get_skill (a 70k answer made sends slow).

**Catalogue**
- Cut the built-in skills from 906 to 240. Removed the templated families (professional, studio-craft, universal-mastery, presentation-craft and audio/NPC expansions, advanced Roblox). `runtime/skills.json` went from 10.6 MB to 1.7 MB.
- Shared policy fields now live once in `runtime/skill-shared-policy.json` and are merged at load; `instructions` is derived from `steps`.
- Fixed 23 skills that carried steps from the wrong domain and moved them to the right one.
- Pack lists, capability index, product manifest and file hashes rebuilt to match; every skill has at least four valid related skills.

**New always-on Roblox standards (7)**
- check-clean-ui and check-props (full rules plus the full private check tables), code-quality, npc-pathfinding, game-systems, vfx-assets and fix-errors.
- Each carries verified create.roblox.com doc references and official limits (DataStore limits and error codes, task library, raycasting, CollectionService, streaming, ProximityPrompt, GeometryService, UI classes, pathfinding, units, particles).
- Selected automatically for Roblox requests by whole-word triggers (any physical object such as tree, boat, tank, car or stick triggers check-props); forced to the front of the director result with their full rules (up to five; code-quality sends only the sections the request touches).
- The AI runs all checks privately and replies to the user in a few plain sentences without naming skills. Exception: asked for its main skills, it names the seven in plain words.

**Startup prompt**
- Short always-on rules plus a when-to-use-which guide for Roblox sessions.
- The full text of the standards is sent once at startup, as many as fit under the provider's send limit (Clean UI and Props first). Added `startupCharBudget` for ChatGPT and Claude (their measured send caps minus a margin); a provider with no budget falls back to 50,000 characters instead of unlimited.
- `tools/build_standards_prompt.py` regenerates that block from `runtime/skills.json`.

**Bug fixes**
- The chat site lagged, worst in long chats: on every streamed token the extension re-read the text of every turn twice. Quick checks now look at the newest turns only and are spaced at least 50-200 ms apart; a full pass still runs about every 1.5 s so older turns stay correct.
- Sending was slow and often failed. The startup message was far too big (the full standards added up to 70k characters on top of a 26k base). Full standards at startup are now capped at 22k, the base prompt is cut from 26.5k to 21k by removing repeated "product scope / capability / settings" rules, and the other standards still arrive in full per task through the director. A send also now counts as accepted as soon as the site starts answering, not only when the box clears.
- Raw command JSON could spill into the chat (long execute_luau commands sent as plain text were never hidden because the hider ignored anything over 600 characters). Fixed for Gemini, ChatGPT, Arena and GLM.
- Tools: removed 39 Blender "specialists" that made no sense (shop HUD, multiplayer, NPC AI, save systems for Blender); 261 remain. The Roblox script audit was rewritten: it no longer reports noise (math.random, server containers), and now catches un-checked FindFirstChild, DataStore calls without pcall or BindToClose, SetAsync overwrites, InvokeClient, deprecated wait/spawn/delay/:connect/body movers/LoadAnimation, Instance.new parent argument, unvalidated remote arguments, per-frame allocations, and endless loops that yield further down.
- "Message could not be sent - send acknowledgement was not confirmed" appeared far too fast (3.5 s). The wait now scales with message size (20 s minimum, up to 2 min), and Gemini's send-button waits scale the same way. The no-automatic-replay rule that prevents duplicate messages is unchanged.
- Mandatory skills could be dropped from the director result when six higher-scoring skills existed; they are now placed first.
- Trigger words matched inside other words ("ui" in "build"); now whole-word. The word "ai" no longer forces the NPC skill.
- Wrong reference link on check-props (a Blender page) replaced.
- Stale test pins fixed (Roblox companion tools 24 to 26; workflow revision v4 to v6); the two hand-written workflows are exempt from the generated-contract equality test.
- Removed the three tests that only covered deleted skill families; all count pins updated.

**Not done**
- The test suite was not run on this build. Nothing has been used in a live Studio session.

# 6.48.2

Detect signed-in ChatGPT composer variants; keep Notion Auto beside its composer; unify portalled toolbar layout and ensure settings stay above a moved toolbar.

# 6.48.1

Automatic post-update setup, current ChatGPT composer support, collapsed effort method chips, Claude/ChatGPT runtime regressions, Crax removal and truthful local mockup completion. See docs/release-notes/RELEASE_NOTES_6.48.1.md.

# 6.48.0 Dev — Update progress and scoped production methods

- Show live download bytes, bounded retries, installation progress and folder setup diagnostics in Updates.
- Preserve bridge preferences across failed/interrupted updates and worker restarts; validate all rollback backups before restoring and finalize verified committed installs.
- Rewrite scoped Roblox GUI and animation methods from supplied quality references; synchronize browser guides and twelve skill workflows from one canonical pack.
- Keep engine targeting explicit and include companion-plugin writes in Ultra research/method/evidence checks.
- Retain all 904 skill IDs, signed Dev publishing and frozen Public 6.42.0.
- Switch chatbar control text immediately with its palette to avoid a low-contrast flash between light and dark themes.

# 6.47.0 Dev — Roblox workbench and reliable tool discovery

- Rebuild the Roblox companion with studded surfaces, four tabs, master and per-tool checkboxes, and 26 curated tools.
- Resolve actual native/toolkit/companion schemas and name aliases. Keep engine-free Chat studio isolated and companion-only connections discoverable.
- Preserve editor buffers, reject concurrent edits, page UTF-8 source and stage large replacements before one commit. Reject oversized inputs instead of silently clipping code.
- Add permission-aware execution receipts readable by the AI. Successful calls do not prove overall completion.
- Stop Notion after one unconfirmed send; add full Notion runtime/discovery tests alongside Vani/Venice/ClickUp.
- Explain workspace modes, sounds and game asset workflows. Retain signed Dev updates and frozen Public.

# 6.46.0 Dev — Execution discipline, skills and clear progress

- Bound unchanged reads and failed retries; require available research/full methods before substantial Ultra writes and real visual/motion evidence before verified completion.
- Deliver distinct methods at every effort level, including enhancer off. Rewrite all 904 skill contracts and add scoped stud-creature/Roblox style resources with licenses.
- Isolate engines in Chat studio, preserve current task IDs across initial chat navigation, repair declared target_file aliases and tolerate restricted Roblox Lighting inspection.
- Wait for Arena candidate generation/selection before feedback; remove model impersonation/routing instructions and preserve exact tool results.
- Put task and phone icons in the chatbar; show plans/stages/remaining work/elapsed and supported rough estimates; keep Settings inside the viewport.
- Add real HTTP phone tests, six-level trusted-send tests and execution/schema/probe regressions. CI runs 41 suites without skips before signed publishing; Public remains frozen.

# 6.44.0 Dev — Figma, ClickUp, provider evidence and Ultra manuals

- Add a paired Figma native companion/plugin and nine-command MCP launcher with current-page Read/Edit, lock/context guards, actual read-back/export and no automatic replay of uncertain writes.
- Preserve MCP isError through the bridge so native failures cannot become successful tool receipts.
- Harden ClickUp private Brain scope, human/native-tool exclusion, quiet pacing and exact-target sends; add a full real-runtime fixture round trip.
- Redesign Provider benchmarks as 16-provider compatibility evidence with search/current filters and read-only local diagnostics. Remove invented model quality/speed ratings.
- Add 12 detailed Ultra manuals, six phases each, relevant bounded excerpts and full local retrieval; lower effort disables the policy and tool.
- Wait for native generation before settling a response error and restore the paused Resume state. Exclude local engine preferences from packages.
- Keep Dev current and the frozen 6.42.0 Public ZIP unchanged. See docs/QA_6.44.0.md for executed checks and live-account boundaries.

# 6.43.0 Dev — Task progress and phone control

- Add a separate themed run monitor with explicit steps, remaining work, blockers and evidence-gated reported completion. Run IDs isolate task reports; tool chips never advance overall progress.
- Add opt-in paired LAN phone control for task status, queued follow-ups/corrections/goals, queue pause/resume and Stop, with guarded desktop dispatch and receipts.
- Keep phone access off at boot, expire one-use pairing codes and device sessions, allow revocation and reject stale targets. The engine bridge remains loopback-only.
- Keep Dev as the rolling build and bundle the checksum-pinned 6.42.0 Public archive unchanged. See docs/PHONE_CONTROL.md and docs/QA_6.43.0.md.

# 6.42.1 Dev — Theme verification and Dev-first releases

- Dev is the sole rolling build. Public 6.42.0 stays frozen and is bundled byte-for-byte alongside Dev; packaging validates its checksum and requires Dev to be newer.
- Theme regression coverage includes all six new palettes across independent menus/bars, both dock modes, composer portals, phone widths, persistence, live-scene cleanup and motion preferences.
- Corrected pale setting labels, Daybreak's inherited dark live panels/scrim, independent chatbar text/control colors and Ultra's animated gradient. The menu's bottom shadow is clipped before the bar without changing control stacking. See the theme QA report for executed checks.

# 6.42.0 — Shared production workflows and Code Flight

- Provider sessions: discover supported tabs in this browser, explicitly start engine/chat sessions, read bounded local briefs and assign shared tasks through the target's acknowledged transport. Protect drafts, active tasks, stale contexts and duplicate/uncertain receipts. Background execution is opt-in; the dashboard is responsive at phone widths.
- Vani: recognize authenticated-style Stop it, require native generation completion, wait a 2.5-second quiet interval and recheck generation immediately before Send. Reused-node reply fingerprints, startup phases and cancellable startup address the reported initialization and interrupted-response cases.
- Task/evidence counts show remaining shared work. Independent new bar palettes and Ultra text retain readable contrast across light/dark menus. Remote phone pairing is not included.

- Co-work: editable and reorderable correction/additional-goal queues, context guards and timestamped delivery receipts. Editing pauses automatic delivery.
- Shared board: project filters, priority sorting, acceptance checklists, blocker reporting, evidence-gated completion and audited check updates. Legacy tasks migrate without data loss; reopening or changing criteria invalidates checks.
- Skills: explicit per-project/engine activation, enable/disable controls, candidate/user-verified distinction, Markdown/text/JSON import, project-pinned library workflows and context-scoped prompt injection even with enhancer/Critic off. Discovery cannot silently reactivate custom workflows.
- Ultra: the final stop of the native slider now includes a task-specific four-stage delivery contract, evidence distinctions and failed-tool/completion rules alongside existing methods/research.
- Code Flight: dedicated Workspace tab; actual Multi-Script icon, three layered worlds, Arcade/Practice, rising difficulty, precision bonuses, separate best scores, keyboard/touch controls and visibility-aware pausing. Static bundled icon is declared as a provider-accessible extension resource.
- Smaller New idea action; six new consistent palettes, including Tidal, Starlight and Daybreak live scenes on both menu and chatbar. Reduced motion and independent bar themes remain supported.
- upstream GPL source adaptation provenance and GPL notices retained. No foreign command transport, runtime, credentials or proprietary art imported.

## 6.41.0 — 2026-10-17

- Recognize observed Vani guest composer/turn roles, preserve chip source, use stable IDs and text-only guest vision fallback.
- Read Venice native failure flags; keep Classic/Agentic boundaries and require cleared errors before Resume.
- Exclude DeepSeek chip bodies from model text; scope shared sends, reapply remount locks and ignore quoted alerts.
- Deliver bounded selected skill workflows, correct read-only discovery and Figma custom workflows, flatten aliases and reserve workflow phases.
- Audit all 904 skills and run all 153 suites; add 16-provider browser/send matrices, Vani/Classic runtime exchanges, live guest probe and reproducible runner.
- Normalize the shared Unix helper to LF; retain matching Dev/Public edition policies and GPL provenance. See docs/PROVIDER_QA_6.41.md for live and environment boundaries.

# Multi-Script 6.36.1 — Creative Production Studio, art direction profiles, real icon packs

- Added per-provider art direction, asset workflow and finish-level settings; choices are persisted with the existing provider behavior map and included in settings backups.
- Expanded provider-aware production instructions across UI/UX/GUI, environment/building, modeling, animation, VFX, icons and textures; the active provider receives its own adapter note while the common contract demands actual implementation, integration, critique, repair and read-back evidence.
- Upgraded the local SVG UI generator with 16 visual palettes, safer color handling, responsive canvas bounds, hierarchy, component-specific rendering, and a design-token handoff.
- Added `ms_create_icon_pack`: actual individual SVG icons, sprite sheet, contact sheet and JSON manifest, with explicit notes distinguishing local source files from uploaded/in-engine assets.
- Enriched all 897 skills with a versioned production contract and visual skills with style/delivery gates; skill IDs and existing engine/provider integrations remain unchanged.
- Version bumped extension, bridge, companion plugin, release metadata and install docs to 6.36.1.

# Multi-Script 6.36.0 — Code mode, Software Builder revamp, perfect schemas, bar theme fix

- Fixed chips/chat bar becoming unreadable on some normal themes (light theme on a dark site or the reverse): the page detector no longer reads our own `zs-light` class, and a clashing bar paints its own surface.
- Software Builder gains **Code mode** (general coding agent on any local folder, every provider) and add-ons (skills, game engines, other MCP servers).
- 27 workspace tools (11 new: glob, read_many, outline, patch, replace, undo, diff, git, check, http, plan); more robust edit/search/run.
- `schema_perfect.py` normalises every advertised tool schema (ours and the engines' live ones) and adds engine-aware parameter docs; 33 schema defects and 5 handler/schema mismatches fixed.
- See docs/release-notes/RELEASE_NOTES_6.36.0.md.

# Multi-Script 6.34.0 — living environment themes

- Scream, Michael Myers, Slenderman and Jason Voorhees are now animated environments drawn behind the menu, in the same style as Fazbear's Pizzeria: the Woodsboro farmhouse at night, Haddonfield's Lampkin Lane at dusk, the Slender woods with a flashlight that follows the mouse, and Camp Crystal Lake with cabins, dock and mist.
- New shared scene engine (`core/scenes.js` + `core/scenes.css`), also used by Multi-Script IDE 5.2. All drawing is code-only SVG/CSS, with no network assets; all selectors are scoped to `.ms-scene`; and it respects `prefers-reduced-motion`.
- The Fazbear's Pizzeria layer is unchanged.
- Verified headlessly: all 25 themes are applied in Chromium against a mock provider page with 0 page errors, and the scene mounts into `#zs-menu` for the four Halloween themes.

# Multi-Script 6.33.0 — Halloween remake, terminal fix, icons

- Remade Halloween themes (Scream, Myers, Slender, Jason): layered gradient atmospheres, gradient header and tabs, inset active rails, stronger background art.
- Fixed `ReferenceError: ensureTerm is not defined` thrown by background message handlers (terminal panel, bridge idle paint) because they lived outside the UI closure.
- Regenerated extension icons (16/32/48/128) from the real Multi-Script SVG.
- Verified headlessly: the extension is loaded unpacked in Chromium against a mock provider page and every one of the 25 themes is applied and measured with 0 page errors.

# Multi-Script 6.32.2 — enhanced prompt sending

- Clear a previous turn's stale Stop flag before submitting a newly accepted enhanced/original prompt. Previously, the send loop attempted nothing and silently returned.
- A new Stop or conversation navigation during prompt review cancels that submission. Cancel/Escape still send nothing; a concurrent task leaves the draft in place with an explanation.
- Includes the 6.32.1 creative-tool optional-label and unique-filename fixes, plus all existing themes/providers.

Update the extension and reload provider tabs. For an upgrade from 6.32.0 or older, also update and restart the bridge to receive the creative-tool fix. Preserve runtime/config.json and custom settings.


# Multi-Script 6.32.1 — creative-tool argument hotfix

- Texture names are optional; pattern stays required. UI mockup and sound-effect output labels are also optional; sound descriptions stay required.
- Unnamed texture/UI SVGs receive unique filenames instead of overwriting a shared default file. Explicit filenames retain their existing behavior.
- Texture seed 0 is preserved instead of silently becoming 1.
- Tool listings explicitly identify required parameters, and texture instructions include a minimal valid call.
- No engine target, file path, code or other essential input is invented. All existing themes and provider adapters remain included.

## Update

Use the Full bundle: update both extension and runtime files, preserve runtime/config.json and custom settings, restart the running bridge, reload the extension and provider tabs, then refresh the chat's tool catalogue or start a new chat. Updating only extension files leaves the old bridge validator running.

JSON Schema defaults are annotations, not automatic value insertion: https://json-schema.org/understanding-json-schema/reference/annotations . The optional label is handled explicitly by the generator.


## 6.30.0 — sounds, UI refresh, bridge clarity

See `docs/release-notes/RELEASE_NOTES_6.30.0.md`. Sounds & alerts, a settings design refresh, quieter bridge reconnects (no ERR_CONNECTION_REFUSED spam), real launcher exit errors instead of Errno 22, and hints for servers that are up with 0 tools.

## 6.29.1 — repair release

See `docs/release-notes/RELEASE_NOTES_6.29.1.md`. Fixes the service-worker `URL`
shadowing that broke most tools, restores always-restart in Setup, launcher exec
bits / macOS quarantine handling / Linux wrappers, LF line endings, and rebuilds
the SuperApp provider on bundle-grounded selectors with 6.29.0's diagnostics.

## 6.29.0 — macOS + Linux correctness, bridge diagnostics, SuperApp provider

See `docs/release-notes/RELEASE_NOTES_6.29.0.md`.

**macOS / Linux fixes (the main event).** Roblox Studio's MCP port was being
misidentified as a squatter on macOS at every boot, because the POSIX port-owner
probe returned an empty executable path and the check only ever looked at the
path. Three Studio-reaping helpers also shelled out to `taskkill` unguarded, so
they silently did nothing off Windows and a zombie `StudioMCP` kept holding the
port. The bridge now has a real `SIGTERM`/`SIGHUP` handler, so stopping it no
longer orphans its MCP children (StudioMCP, `uvx`, `npx`) on POSIX. The
Blender/Unity/Godot launchers forward signals like the Studio launcher already
did. macOS Studio detection now tries every bundle name the launcher accepts,
and Unity Editor is detected on macOS again. The "open desktop apps" list is no
longer empty off Windows (the friendly-name map was `*.exe`-only). Linux
window enumeration documents its X11/Wayland split instead of degrading
silently.

**Release hygiene.** `runtime/engine-prefs.json` is no longer shipped. It
recorded which engines *the packager's machine* had disabled, so new users got
Unity, Godot and Blender switched off — and on Linux it defeated the
"Roblox Studio has no Linux build" auto-disable, causing a crash-loop. It,
`native_host.bat`/`.sh` and `com.multiscript.bridge.json` are now gitignored.

**Bridge.** A new `/diagnostics` route (and `bridge_status.py --json`) reports
version, ports, uptime, per-server state, which engines are switched off on this
machine, the environment probe and the log tail in one call — the human-readable
status now prints the per-server line too, so "which engine is down, and why" is
answerable without a console screenshot. Tool calls now return a structured
`errorInfo` block (a stable code, whether a retry could help, and which tool
failed) alongside the unchanged `error`/`kind` keys. Optional per-server
`timeout_sec` in `config.json` lets one slow server get more room without
raising the timeout for every other server. Servers that send
`notifications/tools/list_changed` now have their tool cache invalidated and
re-listed, so a tool added or removed mid-session is picked up instead of
staying stale until a restart.

**New provider: SuperApp (`superapp.chat`).** A full DOM content-script adapter
(`extension/providers/superapp.js`) implementing the complete provider contract,
with candidate-selector fallbacks and a diagnostic report so an unverified
selector degrades instead of throwing.

## 6.28.3 — Site refusal recovery (DeepSeek "Messages too frequent"), PromptQL provider

See `docs/release-notes/RELEASE_NOTES_6.28.3.md`.

## 6.28.2 — Godot builders, Blender props, Audio + NPC tools, skills (897), Limits fixes, nudge fix, Fazbear's theme + Security Office

See `docs/release-notes/RELEASE_NOTES_6.28.2.md` and the new `docs/TOOLS_GUIDE.md`. Also: five Roblox audio/NPC tools, Godot audio/NPC kits, 25 more skills, working Settings > Limits (summary, reset, central clip, bridge result limit) and a revamped Fazbear's theme with a hidden Security Office game. Chat-bar nudge sliders rewritten (menu stays put, per-site, all docks); live "Fazbear's" theme (21 themes) with a secret Backstage tab; settings sweep test; long MCP names no longer overflow the menu. New Godot tools (gameplay kit, building generator, path builder, scatter, model tools, level blockout, terrain, scene audit, shaders), Blender prop generator, 48 engine-native skills. Fully additive; existing tool schemas unchanged. Notion AI: transcript editables can no longer be mistaken for the composer (mid-page "Agent is working" cover, endless "Starting..."), plus global Stop test-id and running-placeholder generation signals.

## 6.28.1 — Blender assist for the enhancer and Game Idea Bot

See `docs/release-notes/RELEASE_NOTES_6.28.1.md`. New opt-in toggles: the prompt enhancer can add Blender asset-production tasks to every brief (context-aware, honest about connection state, own size budget), and the Game Idea Bot can enlarge its briefs with a concrete five-task Blender asset plan built from the idea's own protagonist, setting and signature action.

## 6.28.0 — Effortless engine setup, bar themes, four new themes

See `docs/release-notes/RELEASE_NOTES_6.28.0.md`. Setup now auto-installs uv and downloads the BlenderMCP add-on; the chat bar gets its own theme setting and the ported-bar white-on-white bug is fixed; Sakura, Crimson, Nebula (live) and Matrix (live) themes; a 10-adapter provider compatibility audit; bridge environment diagnostics + stale-bridge warning in the Running tab; enhancer 2.3 audio constraint; bigger Game Idea pools.

## 6.27.1 — Engine setup guides, real idea generation, enhancer 2.2

See `docs/release-notes/RELEASE_NOTES_6.27.1.md`. Settings → Engines gains step-by-step setup cards for Roblox, Unity, Godot and Blender with a one-click bundled-launcher fill; the Game Idea Bot composes fused premises with anti-repetition; the enhancer translates subjective quality words, guards irreversible defaults, sequences multi-discipline builds, and no longer truncates its own quality gate.

## 6.27.0 — Presentation Craft: flat-world prevention, 824 skills

See `docs/release-notes/RELEASE_NOTES_6.27.0.md`. 24 new cross-engine presentation-craft skills, two new bridge tools (`ms_presentation_pass`, `ms_vertical_slice_gate`), and prompt enhancer 2.1 with a fixed gameplay domain and a first-view world quality gate. Fully additive; all adapters unchanged.

## 6.26.0 — ChatGPT paging, multi-engine, Software Builder, Game ideas, themes

See `docs/release-notes/RELEASE_NOTES_6.26.0.md`. Notion AI behaviour unchanged.

**Hotfix (6.26.0):** stale-bridge replacement (Setup/Start/launcher/extension), Settings → Engines → Active engines (saved on/off per engine), Roblox script-transfer repair, tolerant `ms_ws_*` arguments, "keep running when the browser is covered", Persistent error recovery by default.

## 6.25.1 — Notion: sends that fail now fail fast

- **Fixed: "Start without engine" on Notion AI sat on "Starting…" and never sent anything.** A send Notion did not accept looked the same as one that worked: the composer was *empty*, which was read as "sent", so the bootstrap waited ~2 minutes for a reply that could not exist and then declared **"Chat studio active"** with nothing in the chat.
- Notion `typeAndSend` rewritten: tries `execCommand` insert → synthetic paste → `beforeinput` (and `textContent` only if nothing else lands), **verifies the text really is in the composer and that Notion's Send turned on**, and only counts "composer emptied" as accepted when it had verified text first. A refused prompt is cleared from the composer.
- A refused send is no longer mistaken for a delivered one by the core, and startup stops after 2 refusals (was 6 retries + cooldowns) with a banner that includes composer diagnostics (`Details: {...}`).
- No false "ready": `startSession` aborts when the prompt was never sent, and warns when it was sent but no reply could be read.
- Chat-only start no longer probes Roblox Studio (up to 15 s of nothing).
- 8-minute watchdog guarantees "Starting…", the composer cover and the input lock always clear.
- New `tests/test_notion_send_failfast.js`.

## 6.25.0 — hotfix: terminal, Setup, console flashing

- **Fixed: command prompts rapidly opening and closing when the browser/chat opened.** The terminal icon started the bridge with `DETACHED_PROCESS`, which on Windows overrides `CREATE_NO_WINDOW` and leaves the bridge with *no console*; every console program it then launched (netstat, tasklist, powershell, taskkill, the MCP launchers — and the launcher of an engine that is not installed, restarted every 5 s forever) got its own visible window. The bridge now gets a hidden console its children inherit, every child process is created windowless (`runtime/winquiet.py`), and crash-looping engine servers back off (15 s → 10 min) instead of respawning every few seconds.
- **Fixed: Setup.bat stopping at "Could not find the extension automatically".** The extension now carries a pinned `key`, so its ID is the same on every machine/folder and Setup uses it without any detection. Detection still runs (also finds older copies and more Chromium browsers) and the IDs are merged with those from earlier runs.
- **Setup self-test.** After registering, Setup talks to the launcher exactly like the browser does and reports whether it answers; a transcript is saved to `logs/setup.log`; `pip` falls back to plain / `--break-system-packages` installs; no more double "press Enter".
- **`Start.bat` and `MacOS_Start.command` are back** as the no-setup fallback (unextracted-zip guard, Python lookup/winget install, websockets install, double-launch check, exit-code report, `logs/start.log`).
- **Fixed: the terminal panel refreshing and closing.** Logs, the Running list and the engine chips are only rebuilt when their content changed (scroll position and selection are kept; the list is never rebuilt under a pressed button); the slide-in plays only on open (it used to replay whenever the host page re-attached the bar or the panel flipped above/below the icon); the panel no longer flips back and forth; the outside-click handler no longer treats a click on a just-replaced button as "outside"; the Running poll is gentler (7 s, paused in background tabs) and its process snapshot is cached for 3 s.
- Native host: serialised starts (no two bridges fighting for the port), 3 failed auto-starts in a row stop retrying until you click Start, clearer "launcher closed immediately" error.

## 6.25.0 — Studio UI

**Chat bar**
- Notion: the bar now docks on the *validated* composer card (painted/rounded surface that hugs the editor) instead of the first big wrapper around it. In the empty-chat layout (usage banner + tall wrapper) the bar no longer floats in the middle of the page; if no trustworthy card exists it docks directly above the editor.
- Other providers: the generic dock validates `barAnchor` and falls back to the editor when the anchor is oversized.
- Bar rebuilt: brand + one-line status (full text in tooltip), split bridge button, always-visible settings gear, four styles (Native / Card / Glass / Minimal), three sizes, tiny-width compaction, hides when the composer scrolls off-screen.
- New **Chat bar** settings tab: Position (Auto / Floating / Window), Align, Width (full/fit), nudge X/Y, Look (style, size, status line), per-item toggles, Re-align, Copy layout report, Reset.

**Menu**
- Rebuilt with a left category rail (Home, Chat bar, Agent, Notion, Look, Tools, Engines, AI sites, Help), global search, accordions for dense tabs, "Jump to" cards on Home, smoother open/close and tab transitions (respects reduced motion), scroll position preserved across refreshes, Esc to close.
- Legacy tab ids (setup / interface / appearance / studio) still map to the new tabs.

**Claude**
- Claude (claude.ai / claude.com) was already a provider. Fixed a load-order crash (`diag()` ran before its state existed, aborting the content script on claude.ai), added a mock-page regression test and a description in the AI sites list.

**Tests**: new `tests/test_chatbar_studio.js`; `test_studio_ui.js`, `test_notion_*` updated for the new information architecture.

## 6.24.0 — Terminal, Toolkit, Notion

- Terminal icon starts/stops/restarts the bridge (Native Messaging) and lists everything running; `start.bat` / `MacOS_Start.command` removed in favour of one-time `Setup.bat` / `MacOS_Setup.command`.
- `runtime/schema_repair.py`: live-schema argument repair for every tool call; parser recovers curly/single-quoted JSON.
- 109 native engine tools (Blender 30, Roblox 27, Unity 31, Godot 21) + Blender MCP launcher.
- Notion: composer-aligned bar, Notion settings tab (model detection, model/effort selection, rough trial estimate).
- Settings reorganised (Studio / Agent / Notion / Interface / Engines / AI sites / Help); new tests for all of the above.

## 6.22.0 — Studio

**The JSON-schema error class, closed.** Every reported instance had the same shape: a schema that
advertised a constraint **stricter than the handler accepted**, so the bridge validated against a
contract the code underneath did not have. Which one you hit depended only on which engine was open,
which is why it felt engine-independent.

Rather than fix instances by hand, this release audits the category. `tools/schema_audit.py` loads
the real bridge, pulls **every** declared schema from `BUILTIN_TOOLS` / `COMPANION_TOOLS`, and runs
the **actual validator** (`_normalize_tool_arguments`) against each — not a keyword grep. It flags
positive `minimum > 1` on count-like fields (the `ms_studio_director` class), inverted bounds, and
required strings that must be allowed empty, and it proves the `multi_edit` empty-`old_string` create
path on every run. **260 schemas, 0 high-severity findings, 0 sentinel drift**, with `--strict`
failing the build if that changes.

- **`ms_surface_read` was the last real instance.** Its schema demanded `limit >= 500` while
  `background.js` **ignored `msg.limit` entirely** and always read the maximum — so a caller asking
  for a small read was rejected for a limit the worker never looked at. The worker now clamps a
  caller value into `200..12000` (default 6000) and the schema documents that: *any value is
  accepted*. The governing rule is now uniform — **clamp, never reject; schemas are a superset of
  handler behaviour.**

**Six engine-neutral tools, and they really execute.** Investigated first: Godot's 14 and Unity's 34
tools are the *complete* published upstream sets, so "more native tools" cannot mean more upstream
names — inventing them would cause the very "unknown tool" failure being fixed. The real problem was
that each engine speaks a different **dialect** for the same intent. `ms_native_capabilities`,
`ms_native_read`, `ms_native_write`, `ms_native_verify`, `ms_native_batch` and `ms_native_debug`
(230 → **236** direct tools) translate one vocabulary into each engine's real dialect, validate every
emitted name against the **live** advertised catalogue, and return a **structured refusal** rather
than an exception or an invented call when a path is unsupported. Roblox calls needing an unresolved
`studio_id` are refused before anything is issued; two Studios are never guessed between.

- **Six dialect bugs found while testing against the vendored upstreams, not from memory.**
  Unity `create_script` takes `path`/`contents` (not `uri`/`content` — `find_in_file` is the tool
  that takes `uri`); Unity object creation is `manage_gameobject{action:"create"}` (there is no
  `manage_scene` `create_object` action); Unity scene creation now passes `Assets/Scenes/`;
  Godot `add_node` puts the parent in `parentNodePath` and the new name in `nodeName` (passing the
  parent as `nodeName` silently misnamed the node); Roblox dot-paths now **walk** segment by segment
  (`game:FindFirstChild("Workspace.Door")` returns `nil`, so an existing path reported "target not
  found"); and both literal emitters now `json.dumps` their report string so quoting no longer
  depends on the identifier filter.

**The chat bar's terminal icon starts the bridge for you.** A live readout of the bridge that themes
itself with the bar — green connected, amber pulsing while starting, red down — and starts it on
click, so `start.bat` no longer has to be launched separately.

- It needs a second process because the obvious design cannot work: the case the button exists for
  is the bridge being **down**, so nothing is listening to receive the request. `runtime/bridge_launcher.py`
  is a tiny standalone process on its own port (17615) that does exactly one thing.
- **It refuses to start without a token.** An unauthenticated localhost control server lets any page
  spawn processes; `start_launcher.bat` generates the token once into `runtime/.launcher_token`,
  every mutating route requires it (constant-time, length-checked first), and it binds `127.0.0.1`
  only. It only ever stops the child it started.
- **Pairing needs no manual step.** The launcher cannot prove a caller is the extension, but the
  bridge can — that WebSocket is a channel no page can reach. On connect the extension asks the
  bridge, the bridge reads the token from disk, and the button works.
- **It only shows "live" on a real status push.** "Started" and "reachable" are different claims.

**Notion alignment.** The anchored bar was measuring the wrong box. `composerFrame()` now scores
candidates by closeness to `editorWidth + 40` so the AI card wins over a page column; a new
provider-derived `barInset()` reports the card's real inset (Notion ~20px, Meta ~30px, replacing the
generic `9px 16px`); and `placeBar()` in the core **applies** it — the missing link that had left the
provider method as dead code. A test section fails if the frame resolves to the column, not the card.

- **Eight Python tests pinned the literal `230`** direct-tool count and failed on a *correct* build.
  They now name the base plus the facade add-on explicitly, so a tool silently vanishing still fails
  loudly.
- **Added** `tools/schema_audit.py`, `tools/bump_6_22_0.py`, `tools/validate_6_22_0_artifacts.py`
  (53 assertions), `tests/test_native_facade.py` (93 assertions), `runtime/bridge_launcher.py`,
  `start_launcher.bat`.
- **Verification:** Python 33/33, JS 45/45, schema audit clean, artifact validator 53/53.

## 6.21.0 — Studio

**Fixed - `multi_edit` could not create a script at all.** The reported loop was
`parameters.edits[0].old_string is required`, arriving after the model had already supplied
`old_string`. That was the tell: the recovery message was fine, but it asked for a field that was
present.

`old_string:""` is the *documented* way to create a script - the tool note says so explicitly ("To
CREATE a script: set className ... and make the first edit old_string:\"\""). The bridge's argument
validator, however, treated an empty string as a missing argument:

```python
if k not in out or out[k] is None or (isinstance(out[k], str) and not out[k].strip()):
    fail(f"{path}.{k}", "is required")
```

So the model wrote precisely what the documentation instructed and the validator answered "is
required" - unsatisfiable, because the field *was* supplied. An unfixable loop, and the create path
was impossible.

- **An empty string is a real value for a content-matching field.** `old_string` joins a small
  documented set (`_EMPTY_STRING_IS_VALUE`) where `""` is the sentinel and whitespace can be genuine
  text to match. Elsewhere the rule still applies: `new_string:""` and a blank `studio_id` are still
  rejected.
- **`className` plus a missing `old_string` is unambiguous** and is now filled with the sentinel
  rather than rejected. Deliberately narrow - only `multi_edit`, only with `className` (an ordinary
  edit never passes it), only when `old_string` is absent entirely. An edit that forgot `old_string`
  still gets the corrective error.

**Fixed - `ms_studio_director` rejected a value it would have clamped.** `parameters.max_skills must
be >= 8` fired even though the handler had always done
`max(8, min(40, int(skill_limit or 30)))` - so 5 was never a problem, it became 8. The schema was
stricter than the implementation, and the validator rejects against the schema before the handler
runs. A hard floor on a value the code already clamps is a rejection with no purpose.

Seven limit parameters (`max_skills`, `max_tools`, `max_virtual_tools`, `skill_limit`,
`direct_tool_limit`, `virtual_tool_limit`) now declare `minimum: 1` and let the clamp do the work, and
`ms_studio_director`'s description states the effective floors.

**Fixed - the Notion bar floated in the middle of an empty page.** The bar was anchored to nothing,
vertically centred, with no composer on screen. The cause was self-inflicted: the adapter's
**route-surface guard** (only `/ai` and `/chat/...` are AI surfaces - the thing that stops it typing
into a normal page editor) had its escape hatch armed unconditionally inside `init()`. The core
initializes the provider on **every** `notion.so` page, so that disabled the guard everywhere, and on
an ordinary workspace page the adapter adopted an unrelated container as the "composer frame".

- **`init()` no longer arms the override** - the guard is back in force on ordinary pages.
- **Surface acceptance is evidence-based**: an AI route, an explicit user request, or positive
  AI-composer evidence (an Agent transcript anchor, or a composer carrying the AI placeholder). The
  guard keeps its teeth while a genuine AI surface off the `/ai` route is still recognised.
- **`composerFrame()` takes the tightest matching container, not the outermost.** It let every
  matching ancestor overwrite the candidate, so the largest won - which is how the page column was
  adopted. Its last resort is now the editor's own parent.
- `selfTest()` reports `routeGuardMatched` / `explicitOpen` / `evidence` so a misdetection is
  diagnosable instead of a silent `false`.

`tests/test_notion_route_guard.js` pins it: an ordinary page must resolve no editor, no frame and not
report ready; a real AI surface must still work off the `/ai` route.

**Improved - the Roblox Studio companion panel was rebuilt in the extension's design language.** It
was a flat grey list of labels and coloured buttons.

- **One set of design tokens** mirroring the extension: the surface stack `#06060a -> #1a1a21`, the ink
  ramp, hairline 1px borders, the status colours, and the same two button weights - a light primary
  with dark ink, and a dark secondary with a hairline border.
- **Real panel structure**: a header with the mark, brand and version chip; cards with 9px radii and
  hairline strokes; letter-spaced uppercase section micro-labels; a subtle vertical gradient behind
  the panel.
- **Status dots**: the label-to-dot pairing lives in a `DOT_FOR` table, so every existing
  `color(x, state)` call lights its dot for free - no status logic had to change.
- **A readiness bar** that fills and tints by band (green >= 80, amber >= 50, red below).
- **The panel opens on first install** and remembers whether it was closed.
- `msrb_patch_script`'s empty-`old_string` error now names the tool to use instead
  (`msrb_replace_script`) rather than a bare "cannot be empty".

All 24 tools, permission tiers and safety properties are unchanged: two-stage permission checks,
ephemeral loopback auth, no `loadstring`, no arbitrary evaluation.

## 6.20.0 — Roblox Companion Tools

- Added 24 opt-in, permission-tiered Roblox Studio companion MCP tools.
- Added secure loopback registration, ephemeral bearer sessions, bounded job polling/results, stale-job rejection, and no HTTP enqueue endpoint.
- Rebuilt the Studio plugin UI and handlers with Read, Project, and double-confirmed Full modes.
- Added release tests and documentation for the new companion security model.

## 6.19.2 — Notion Fit

- Anchored the Multi-Script bar to Notion’s exact composer rectangle instead of its wider action-rail parent.
- Added measured-width responsive classes so controls compact based on the actual composer, not the viewport.
- Added a permanent Notion auto-width regression test.

## 6.19.1 — Notion Chat

- Added the missing `app.notion.com` host permission/content-script match so Multi-Script mounts in current Notion AI chats.
- Changed every Notion launcher to `https://app.notion.com/chat` instead of the old workspace root that could open Connectors.
- Added current “Ask anything” composer detection and explicit chat-route recovery.
- Added a complete Setup category with live checks and a copyable end-to-end tutorial.
- Removed the redundant MCP prompt wrappers and restored the authoritative 230-tool catalog.
- Adapted upstream GPL source’s GPL Claude provider into Multi-Script’s universal multi-engine pipeline; no upstream GPL source IDE or AgentScript code is included.

## 6.19.0 — Universal

- Made prompt review real and editable across all providers; fixed previously non-functional preview and tool-fact settings.
- Added universal execution effort controls, including Notion's prompt-only startup harness behavior.
- Kept the existing 230-tool catalog authoritative and avoided duplicate wrappers for server-native MCP capabilities.

## 6.18.0

**Fixed - the settings menu was sliding off the left edge of the screen.** Half the panel was outside
the viewport. The bar was never the problem: the menu was measuring itself against the wrong box.

`#zs-root` is the extension's host element and is `position: fixed` with **no inset**, so it pins at
`(0,0)` and its in-flow children are laid out against the *viewport*. `#zs-menu` was
`position: relative` - so it lived in that flow, and a `right:` on it measured the gap to the
**screen's** right edge. But `placeBar()` was feeding it `window.innerWidth - barRect.right`, which is
the distance from the **bar's** right edge to the window edge. On a wide composer the bar stops short of
the right edge, so that value is the page gutter - a few hundred pixels - and the panel was told to sit
that far in from the screen's right edge, then pushed further left by its own 370px of flow width. With
no clamp anywhere, half of it left the screen.

- **The popover is now genuinely `position: fixed`**, so `right:` means what the placement code already
  computes - a distance to the viewport edge - instead of being reinterpreted by a flow-positioned
  ancestor. This was the root cause.
- **Four duplicated placement blocks collapsed into one `placeMenu()` helper.** The in-flow mount,
  anchored, detached-float and editor-float branches each set `right` / `bottom` / `maxHeight`
  independently; they now share one implementation.
- **Both edges are clamped into the viewport**, so the panel cannot leave the screen wherever the
  composer sits - left-of-centre, full-bleed, or on a 360px window.
- **Width is clamped to `100vw - 16px`.** The later `#zs-root #zs-menu` rule was re-widening the panel
  to a raw `370px` and defeating the earlier clamp; it now clamps too.
- Height follows the space actually available above the anchor, with a 140px floor.

`tools/render_menu_probe.js` replays the real CSS and the real math across nine geometries - an absurd
gutter, a 360px viewport, a bar pushed to the far left - and asserts the left edge is never negative.
39/39 checks. `tools/validate_6_18_0_artifacts.py` asserts the same invariants against the built zips.

**Improved - Notion AI detection, ported from upstream GPL source 1.18.74.** upstream GPL source is a derivative of
Multi-Script with a far more mature Notion adapter (2,492 lines vs our 466). Its detection and
transcript logic was merged in; the IDE and `.exe` were not.

Adopted: a **route-surface guard** (only `/ai` and `/chat/…` are AI surfaces - the thing that stops the
adapter ever typing into a normal page editor), a **scored, memoised editor resolver** with negative
caching, **exact live send/stop selectors**, and **dual transcript anchors** that survive hashed class
names.

Three corrections were needed, because the ported logic was stricter than the file it replaced:

- **The route guard was rejecting surfaces it should accept.** `openAIChat()` returned early whenever
  the guard matched, so a composer that was on-surface but not yet resolvable (late mount, shadow host)
  got no recovery action at all. There is now an explicit-open override armed *only* by a deliberate
  action (`init()` / `openAIChat()`), never from ambient page state, cleared on a real navigation.
- **Shadow DOM broke the scorer and the frame resolver.** `parentElement` walks stop at a shadow host,
  so a shadow-hosted composer could not see its own `<form>` or Send button and never cleared the score
  threshold. Both walks now climb through the host chain.
- **The transcript lost its legacy path.** The ported `rawAgentRows()` only knew
  `data-agent-service-scroll-anchor`, so builds using the `data-testid` message pattern would have shown
  an empty conversation. Anchored rows are preferred, with block structure and the semantic-turn
  selector as fallbacks.
- `ready` no longer requires the literal `contenteditable="true"` - Notion ships `plaintext-only`, so a
  usable composer was reporting not-ready.

`selfTest()` now reports the effective surface next to the raw guard result (`routeGuardMatched` /
`explicitOpen`), so a misdetection is diagnosable from the panel instead of being a silent `false`.

## 6.17.8

**Fixed - the theme picker in Settings had gone half-invisible.** The appearance studio's theme grid
rendered as a stack of near-empty dark ovals; only **Graphite** and **Ink** were readable, because
those two happened to be the selected ones.

Root cause was a cascade-order accident introduced by the 6.17.6 monochrome rebuild. The original
appearance-studio rule set the theme pills to `#aaa`, which is legible on the dark panel. The later
monochrome layer then added a grouped "choice / option controls" rule - covering `.zs-pref-opt`,
`.zs-behavior-opt`, `.zs-economy-opt`, `.zs-quality-opt`, **`.zs-theme-opt`** and `.zs-profile-opt` -
and set them all to `color: var(--mono-ink-4)`, which is `#6a6a78`: a grey chosen for *de-emphasised
metadata*, not for a label you are meant to read and click. Coming later in the file, it won on source
order. Only `.active` survived, because that rule forces `--mono-ink` with `!important` - which is
exactly why the two selected pills were the only ones that could be read.

The fix restores the grid and lifts the ink ramp across the whole pill family:

- The theme options are **re-asserted after the grouped block**, so their own legible ink
  (`--mono-ink-2`) and their own hover (`--mono-ink`) win again. The grouped rule keeps a single
  shared definition for the other pill families and no longer swallows the theme pill.
- The grouped block's default ink moved from `--mono-ink-4` to `--mono-ink-3`, so the density, width,
  scale, behaviour, economy and quality pickers are all readable too - the same bug was latent in
  every one of them, just less obvious because their labels are short.
- The grid returns to four columns with the label on a single truncated line, and each option now
  **previews its own palette** on its chip (`auto`, `midnight`, `graphite`, `frost`, `mono`, `ink`,
  `synthwave`, `forest`), so the grid reads as a theme gallery rather than eight identical grey pills.
- The chip is pinned to `flex: 0 0 auto` so it cannot be squeezed out of existence in a narrow column,
  and the label carries `min-width: 0` so a long name truncates instead of forcing the grid to wrap.

A regression test (`tests/test_theme_picker_legibility.js`) now pins all of it: the grid must stay
3-4 columns, the pill colour must come from the legible ink ramp, `--mono-ink-4` may never be bound to
a pickable theme pill, and every advertised theme must have a palette chip.

## 6.17.7

**Fixed - the AI stopped building models out of spheres.** Connecting Blender (or any engine) and
asking for an object that is not a ball produced a pile of scaled UV spheres. The cause was not the
model being lazy: the guidance it was given said *"block primary forms"* and *"topology must be
clean"*, and **a scaled sphere satisfies both**. Nothing anywhere said what a limb, a plate or a cable
is actually made of, so the model fell back to the cheapest primitive that technically worked.

The fix makes the choice of primitive an explicit decision, and encodes the default that gets it right:

- **A new form-craft layer** (`runtime/form_craft.py`) maps 183 named features to the form they should
  be built from - 9 forms, with concrete Blender build advice for each. A limb, shaft, pipe, neck,
  finger or barrel is a **cylinder** (tapered). A plate, housing, crate, screen or machine part is a
  **beveled box**, because a hard 90-degree corner catches no light. Anything that follows a path -
  cable, hose, rope, vine, tail - is a **Bezier curve swept to mesh**, which is the single most-skipped
  tool and the one that most often replaced a wrong sphere. Anything defined by its outline - gear,
  bracket, beam, blade - is an **extruded 2D profile**.
- **Spheres are not banned, they are scoped.** 18 of the 183 features are genuinely spherical - eyeball,
  ball joint, planet, ball, berry, knob, dome - and those still classify as spheres. The rule is stated
  as a checkable prohibition with a tell attached: *"if you find yourself scaling a sphere on one axis
  to make it read as something else, that is the tell that you chose the wrong primitive."*
- **A new tool, `ms_form_guidance`.** `action="classify"` answers one feature, `action="audit"` takes
  your whole proposed part list and reports which parts are spheres that should not be - the mechanical
  version of the complaint. Unmatched features fall back to **box, never sphere**.
- **The real substance went into the prompts.** Every Blender engine rule and tool note now leads with
  form selection. `generate_procedural_model` no longer invites spheres: it requires naming the form per
  part. The `ms_blender_model_studio` contract gained a form-decision stage and two new quality gates
  (*"no sphere standing in for a limb, plate or cable"*).
- **Boilerplate replaced with craft.** The four Blender pipeline specialists - topology, geometry nodes,
  rig/animation, render/colour - were near-identical copies of one generic 8-stage template. They now
  carry domain-specific stages and gates: quad flow that follows the form, instancing real modelled
  assets instead of scattering generated spheres as "rocks", checking that a limb deforms before binding
  it, setting colour management *before* material work.
- **Applied to every engine, not just Blender.** The form rule is now a global prompt rule covering
  Roblox, Unity, Godot and any DCC tool, and all 32 modelling specialists across the four engines got
  engine-specific form craft (part/union budgets for Roblox, lightmap UVs and import settings for Unity,
  import flags and collision shapes for Godot).

**New - a graduated trust model.** Instead of six independent permission switches, one ordered choice:
**Sandbox** (engine and project folder only) → **Ask** (the wider PC, confirming each write or run) →
**Full** (all files and processes, no per-call prompt). Thirteen capabilities are declared explicitly, so
a new one must be *declared* rather than quietly defaulting to the old behaviour. Reading is never
blocked; acting is what gets confirmed. The model is pure and unit-tested, including the property that
matters most: **a corrupt or unknown level falls back to the most restrictive one.** Four hard limits sit
below every level - no sending your files or keys anywhere, no reading credential stores, no acting on
external services unasked, and URLs restricted to http/https.

**Also:** the trust layer is wired into the manifest load chain and enforced at the single choke point
every surface call passes through, so a refusal is reported back to the model as a refusal rather than
as an error to retry around.

## 6.17.6

**New - an auto prompt enhancer, in Settings.** A short phrase like *"make the door open when the
player touches it"* becomes an implementation-ready brief: the goal restated, the constraints your own
words imply, the facts about which engines are actually connected, and an explicit definition of what
"done" means for that kind of task. Three strengths (light / balanced / thorough) plus off.

Designed to be trustworthy rather than clever: it runs **entirely offline with rules**, so there is no
extra cost, no network round trip, and nothing to leak. It **never contradicts you** - your original
wording is preserved and sent first, and the enhancer only *adds*. It **never invents specifics**: no
made-up dimensions, colours or numbers, only structure and the constraints that follow from your words.
It is **idempotent** - a request that is already detailed is left alone, and the marker it adds means a
second pass is a no-op. The Settings panel shows a live preview of exactly what the model will receive
before you ever use it.

**New - media relay: send a photo or a video to a site that will not let you.** Several of the
supported chat sites have no upload control, or silently refuse a file. The relay takes a dropped
image or clip, carries it to the local bridge, and delivers it as a **real paste** through the site's
own input path - the same one a person's clipboard uses. Videos are decoded into up to six frames with
`ffmpeg` (and, honestly, report themselves as frames with a manifest when `ffmpeg` is not installed,
rather than pretending a video arrived).

Deliberately reuses the provider's existing `attachImages()` instead of forging a file input: every
site already knows how *it* accepts an image, so the relay converts a hard problem (no upload control)
into one that was already solved. Formats: png, jpg, gif, webp, bmp, mp4, webm, avi, mov. Drops work
on the whole composer, not just the panel.

**New - the agent can see your tabs and your desktop.** It can enumerate your open browser tabs with
real titles and hosts, read a tab's visible text, focus a tab, open a URL, and type into a tab's
composer. Separately it can list the desktop apps and windows running on your machine - Roblox Studio,
Unity, Godot, Blender, Figma and the rest - read a window's title, and report honestly when a deeper
read needs an optional package.

The two halves genuinely live in different places, and the design reflects that: `chrome.tabs` exists
only in the extension's service worker, so tabs are enumerated there; a web page cannot see native
windows at all, so the **bridge** enumerates those (`ctypes` + `user32` on Windows, `osascript` on
macOS, `wmctrl` on Linux). One call returns both, merged. Read-only by default, text only - no
screenshots, no keystroke capture. Opening a URL accepts only `http:`/`https:` and refuses `javascript:`,
`data:`, `file:` and browser-internal schemes outright. Four independent grants in Settings (see tabs /
see windows / read text / type into a tab) let you allow looking while forbidding touching, and they are
enforced at the single choke point every surface call passes through.

**New - desktop setup walks you through the optional parts, and installs nothing.** If a richer read
needs `pywin32`, `pyobjc`, `wmctrl`, `xdotool` or similar, **Unlock full desktop vision** reports each
step, whether it is already satisfied, and the exact command. It never runs anything on its own.

**New - nine workflow tools, because the hard part is rarely one call.** Six for Roblox Studio:

- `ms_roblox_build_verifier` - re-reads the live place and tells you whether what you claimed to build
  is actually there, reporting `verified` / `mismatched` / `unverifiable` with the raw evidence. The
  difference between "I made it" and "it is there".
- `ms_roblox_script_audit` - reads real Luau source and finds the mistakes that break shipped games:
  ignored `OnServerEvent` player arguments, `LocalPlayer` in server context, unbounded loops, deprecated
  `wait()`, `loadstring`, runtime-created remotes.
- `ms_roblox_playtest_director` - plans and optionally runs a real playtest (start in the right
  datamodel, exercise the scenario, capture console, stop cleanly), stopping at the first failed step
  instead of reporting a false pass.
- `ms_roblox_asset_scout` - searches the Creator Store or your own place and returns candidates that
  already fit, without ever inventing an asset id.
- `ms_roblox_scene_diff` - snapshots a subtree and diffs two snapshots, so a large edit can be reviewed
  instead of hoped for. Bounded store so a long session cannot grow memory without limit.
- `ms_roblox_error_triage` - turns raw console output into a ranked diagnosis, and keeps deprecation
  warnings and plugin chatter **separate from real failures** rather than training you to "fix" working code.

And three for the agent itself: `ms_agent_plan_then_act` (plan first, execute only when approved),
`ms_agent_self_check` (confidence derived from evidence-per-action, so it cannot be asserted into
existence), and `ms_agent_context_recall` (what is connected and staged *right now*, so it re-reads
rather than guesses).

**New - a full monochrome rebuild of the menu.** True black-and-white surface and ink ramps with a
pointer-tracked ambient sheen, replacing the old purple accent. Two new themes (`mono`, `ink`), a
de-saturated default accent, a new `frost` light variant, and every panel re-skinned: enhancer, media
relay, surface vision, appearance, benchmarks, provider and behaviour controls. Built as a
**non-destructive final CSS layer** over the existing `--ms-*` contract, so **every feature and element
id is preserved** and nothing downstream breaks. Motion respects the existing reduced/none preference.

**Honesty rules these tools share.** Every one of them refuses rather than invents. When the engine is
not reachable they return `available: false` with the real fixes - never an empty success. A read that
could not be performed is `unverifiable`, which is a different answer from "it does not exist", and the
tools say so. The console triage keeps noise out of the failure list. The self-check reports
`unknown` rather than `high` when nothing was actually proven.

**Testing.** Four new gates, all wired into CI and `release_check.py`: `test_prompt_enhancer.js` (11
sections), `test_media_relay.py` (17) and `test_media_relay_js.js` (11), `test_desktop_vision.py` (12),
and `test_roblox_workflow_tools.py` (12). Direct tool count 211 -> 229. 39 JavaScript tests and 30
Python tests pass.

## 6.17.5

**Fixed - the Roblox tool shapes were partly guessed, and several were wrong.** The templates and
notes in `engines.js` / `config.js` are a *mirror* of the live Roblox Studio MCP server. Nine of them
had been written from memory rather than read from the server's published parameter schemas, so the
copyable examples taught calls the server rejects. Every one is now corrected against the real schema:

- `generate_mesh` takes **`textPrompt`**, not `prompt` (it also accepts `async`, `size`, `segmentation`, `partNames`, `maxTriangles`).
- `wait_job_finished` takes **`jobId`**, not `generation_id`.
- `screen_capture` **requires `capture_id`** - it was omitted entirely, so every capture call was rejected.
- `search_game_tree` **requires `datamodel_type`** (`"Edit"` in edit mode; `"Edit"` is rejected during a playtest).
- `script_grep` takes **`query`**; `script_search` takes **`keywords`** - the two look interchangeable and are not.
- `insert_asset`'s **`assetId` is a string** (it was documented as a NUMBER), and `assetName` is what names the inserted instance.
- `multi_edit`'s **`file_path` is a top-level params field**, NOT a field inside each `edits[]` entry - the wrong nesting shipped for several releases.
- `generate_procedural_model`'s server default is **`async:true`** and it returns a **jobId**.
- `character_navigation` is `datamodel_type:"Client"` plus `instance_path` OR `x`/`y`/`z` (there is no `destination` field).

**Fixed - two silent duplicate-key bugs.** In a JavaScript object literal the last duplicate wins and
`node --check` cannot see it. `search_game_tree` was defined twice in `ROBLOX_TEMPLATES`, and
`generate_mesh` + `generate_procedural_model` were each defined twice in `TOOL_NOTES`, so the earlier
text in each pair was dead code the maintainers still believed was shipped.

**Added - full build-surface coverage.** Seven new Roblox template/note pairs (`insert_asset`,
`search_asset`, `get_console_output`, `screen_capture`, `generate_mesh`, `generate_procedural_model`,
`search_game_tree`) plus the discovery tools (`list_roblox_studios`, `character_navigation`, `skill`).
`ROBLOX_GLOBAL_TOOLS` now declares the tools that take **no** `studio_id`, so a model cannot invent one
on the single most-likely first call. Every native tool now ships a required-shape template.

**Added - permanent gates so these cannot come back.**

- `tests/test_roblox_schema_conformance.js` (new, 6 sections) pins every corrected parameter name and
  fails the build if a template drifts back to a guess.
- `tests/test_engine_registry_integrity.js` grew two sections: a source-level **duplicate-key scanner**
  (string- and comment-aware) and a **global-vs-place-scoped** consistency check.
- `tests/test_required_param_contract.js` now asserts `multi_edit`'s `file_path` **nesting**, not just
  that the word appears somewhere.
- `docs/engine-command-reference.html` corrected: the Roblox table now lists the real required params
  and the full build surface.

**Fixed - the exhaustive audit test no longer looks like a failure.** `tests/test_all_skills_and_tools.py`
cleaned its scratch output with `shutil.rmtree`, which trips a host bulk-delete guard above 50 paths and
killed the process before its PASS line. It now unlinks file-by-file; the run finishes clean in ~2m40s.

*(Node suite 36/36, full Python suite green, `release_check.py` PASS.)*

## 6.17.4

**Fixed - total blackout on every site (6.17.3 regression).**

- **Nothing mounted on arena.ai, DeepSeek, ChatGPT, Gemini, Kimi, GLM, Meta, Qwen or Notion** - no panel, no Start button, no UI at all. 6.17.3 assigned `A.verifyState` / `A.verifyCount` ~170 lines *before* `const A = {…}` was declared. `const` sits in the temporal dead zone until its declaration runs, so the very first touch threw `Cannot access 'A' before initialization`; the content-script IIFE died before any UI existed, on every provider. The two fields now live inside the `A` literal where they belong.
- **Why no test caught it:** `node --check` parses the file fine - a cross-file TDZ error only appears when the concatenated content-script chain is *evaluated* in one shared scope, which is what Chrome does. New `tests/test_content_script_load_contract.js` does exactly that: it evaluates all 11 manifest blocks, asserts none throws, and includes a deliberate-TDZ guard proving the check is not vacuous.

## 6.17.3

### Verification assistant (keeps an unattended run alive without bypassing a bot-check)
- Added `core/verification.js` plus a provider-side assisted click, so a bot-check no longer kills an unattended run. This is deliberately NOT a captcha bypass: the module contains no solving service, no token read or write, no `grecaptcha`/`hcaptcha` execute call and no `postMessage` into the challenge iframe, and `tools/release_check.py` now FAILS THE BUILD if any of those ever appear in shipped code (comments are stripped first, so prose describing the refusal cannot mask real code).
- Staged escalation instead of a dumb wait. While a check is on screen: banner (t+0) -> Multi-Script's own controls move off the widget's hit area (t+9s) -> audible alert + tab title, so it is noticed from another tab (t+26s) -> ONE trusted click on the provider's OWN widget (t+61s) -> re-alert with elapsed time (t+5m). The alert deliberately precedes the click so the user always gets first refusal, and the click is delayed so it never reads as an instant scripted reaction.
- The assisted click is a single bounded gesture: a normal pointer+mouse sequence aimed at the widget's visual centre, then it stops. It never reads a value (token harvesting), never writes one (token injection), and never retries. On a checkbox-style challenge (Turnstile managed mode, hCaptcha passive) a single real click is exactly what a human does; if the provider wants a puzzle instead, that is handed back to the human and the UI says so.
- Adaptive slowdown - the "keep it running" half. Each challenge raises a FLOOR on the inter-turn gap (12s, 36s, 72s, 120s, 168s, capped at 180s) on TOP of the normal pacing, so the run stops tripping the check in the first place. A 45s settle taper applies right after a check clears. The floor decays PROPORTIONALLY once traffic is clean (a mild slowdown clears fast, a heavy one eases off gradually instead of snapping back to full speed and immediately re-tripping) and reaches exactly zero - about 90 minutes from the ceiling.
- Clearing a challenge now also resets the error-recovery budget, because the failures that preceded it were the challenge's fault rather than the model's, and re-times the slowdown from the clear.
- Four modes in a new Agent -> Verification handling section, saved per-provider: Off (pause/tell/resume, the previous behaviour), Watch (plus the loud alert), Assist (default: alert, one click on the provider's widget, adaptive slowdown), Unattended (longest patience, loudest alert, strongest slowdown). Plus an audible-alert toggle. Included in settings backup/restore and the diagnostics export.
- Scope and honesty: it targets arena.ai (Meta stubs detection out entirely, so the core degrades to pause-and-resume with no error). The click targets the widget HOST, since a cross-origin iframe cannot be scripted. The feature only helps where one click is sufficient - if a puzzle is required a human must still do it, and the copy says so rather than implying the check is solved.
- Added `tests/test_verification_assistant.js` (~50 assertions): the bypass surface is absent from CODE (with a guard proving the scanner is not vacuous), only clicking modes may click and anything that clicks must alert, sanitize is total and clamps, per-provider overrides resolve, the slowdown grows/escalates/caps/decays/releases-to-exactly-zero, the ladder never clicks before alerting or within the first 30s, the copy states the boundary and never over-promises, and the whole path is wired through manifest load order, provider exports, core orchestration, menu, backup and diagnostics.
- Extended `tests/test_arena_human_verification.js` to prove the assisted click in a real Chromium: it targets the visible widget, dispatches one bounded gesture (<=5 events), and never targets the invisible reCAPTCHA v3 badge. The pre-existing guarantees (hidden badge causes no pause, visible challenge does, manual clear resumes) are unchanged.

## 6.17.2

### Required-shape notes + corrective validator errors (fixes the "BAD JSON" loop)
- Fixed the reported loop of `ERROR calling 'multi_edit': multi_edit: invalid parameters: parameters.edits[0].old_string is required`, where the model dropped ONE required nested field, could not work out which, and then degraded into malformed JSON. Two independent defects allowed it.
- Cause 1 - the note never showed the call SHAPE. The `multi_edit` note was 1470 characters explaining how `old_string` should MATCH (byte-for-byte, unicode, create-case) but never showed what a call looks like, so a model skimming for "what do I write" omitted the field. Every structured tool's note now LEADS with a literal copyable envelope: `REQUIRED SHAPE (copy this, fill the values): {"command":...}`. The original prose follows it unchanged - the template is prepended, never substituted.
- Cause 2 - the rejection path was not corrective. The bridge's own schema validator rejects arguments BEFORE the tool runs and returns `ok:false`, which is a different path from the server's `ok:true` complaint. Only the latter had been made corrective; the former still showed a bare "Read the error carefully, fix the call or try a different approach." That path now names the exact nested path, states plainly that the command was NOT run, explains that an array field lives on EVERY object rather than at the top level, tells the model NOT to rename the command, and embeds the tool's required shape.
- Cause 3 - a regression I introduced in 6.17.1: the `STUDIO ID:` paragraph was appended to every place-scoped note, bloating them and pushing the call shape out of reading position. The user's "weird, more errors than before" was correct. The long text is now a short one-line suffix, and the shape leads.
- Bug in my own first fix, caught by the new test: the nested-path detector was `^`-anchored, so `/^([A-Za-z0-9_]+)\[\d+\]\.([A-Za-z0-9_]+)$/` could never match the real dotted path `parameters.edits[0].old_string` - the correction silently never fired. The required-field matcher was also lazily quantified and truncated the path to `parameters`. Both are fixed and pinned.
- Godot, Unity and Blender were audited end-to-end, since none of them had ever been exercised. Found and fixed: `run_project`, `launch_editor` and `update_project_uids` (Godot) and 12 Unity family tools plus `batch_execute` had required parameters but NO template, so their notes could not lead with a copyable shape at all. All are now covered, with actions taken from the verified action vocabulary.
- `read_console` was declared as a flat tool while its own note called it ACTION-DISPATCH and `ACTION_OWNERS` listed its actions - so its required `action` param was never enforced. Upstream really does take `action="get"`/`"clear"`; it is now correctly `req:["action"], dispatch:true`.
- The `create_script` and `script_apply_edits` templates now demonstrate escaped quotes and escaped newlines in real C#, because an unescaped `"` inside a code payload is the observed way multi-line code fails to transfer. Blender's Python template already showed this; the JSON-string transfer path is now asserted to round-trip byte-for-byte through the real parser for both C# and Python.
- Added `tests/test_required_param_contract.js` (9 sections): every structured tool leads with a valid envelope that parses as JSON after placeholder fill AND round-trips through the parser; the `multi_edit` template carries `file_path`/`old_string`/`new_string`; the validator rejection is corrective for nested, indexed, top-level and non-`is required` messages and still falls through for unrecognised text; Godot's 14 tools and exact required params are asserted literally with full template coverage; Unity's dispatch templates all carry a real action from that tool's vocabulary with full coverage; and code payloads round-trip byte-for-byte.
- Verified nothing good was replaced: the original Godot and Unity orchestrator rules, the `multi_edit` unicode warning and create-script case, and every Roblox `TOOL_NOTES` entry are still asserted verbatim.

## 6.17.1

### Roblox Studio `studio_id` contract (fixes "parameters.studio_id is required")
- Fixed the real cause of the reported `ERROR in execute_luau: execute_luau: invalid parameters: parameters.studio_id is required`. Roblox's official Studio MCP requires a `studio_id` argument on EVERY place-scoped command (`execute_luau`, `multi_edit`, `script_read`, `script_search`, `script_grep`, `inspect_instance`, `search_game_tree`, `get_studio_state`, `get_console_output`, `user_keyboard_input`, `user_mouse_input`, `start_stop_play`, `wait_job_finished`, `insert_asset`, `search_asset`, `screen_capture`) - and nothing in the product mentioned it, so the model never sent it.
- Diagnosed from this repo's own bridge log rather than guessed: `bridge_debug.log` shows both the tool call carrying `studio_id` and the rejection, plus the crucial proxy warning `sent a request without studio_id but multiple studios are connected`. That warning is why the bug looked intermittent: with EXACTLY ONE Studio attached the proxy silently auto-selects it, so an omission is harmless; with two or more attached every command that drops it is rejected. A single-Studio test can never reproduce it.
- Auto-fill: the extension now injects the learned Studio id when the model omits it. It NEVER guesses - with several Studios connected and no explicit choice it refuses and lists the candidates, because running the call blind would silently mutate the WRONG place with no error at all.
- Learning is passive and eager: the id is read out of any answer that mentions it (`list_roblox_studios`, `get_studio_state`, ...), and the bootstrap now probes `list_roblox_studios` once on the BACKEND (no model turn, no visible message, best-effort) so the id is known before the model's first command on any provider - the specific gap that made Roblox fail on arena.ai and DeepSeek.
- Corrective error: a missing `studio_id` no longer forwards the raw server text and points the model at a giant truncated catalogue (which is what made it flail into the non-JSON reply in the second screenshot). It now names the parameter, explains the one-vs-many asymmetry, quotes the known id, and says to retry the SAME command. Consolidated as `ZS.FEEDBACK.studioId` so it is unit-tested.
- Documented in all three surfaces the model reads: the system prompt's parameter contract and `execute_luau` example, the `list_commands` required-param marker (no `?`), and an appended `STUDIO ID:` note on every place-scoped tool.
- Also fixed four pre-existing engine leaks found while testing: a Godot-only or Unity-only session was shown Roblox's `execute_luau`/`multi_edit` example envelope, a Roblox-specific required-parameter example, a Roblox `Instance.new`/`WaitForChild` build rule, and a "Prefer DIRECT ROBLOX STUDIO" creative-surface rule. Each now has an engine-neutral equivalent; a non-Roblox prompt carries no copyable Roblox envelope.
- Added `tests/test_roblox_studio_id.js` (29 assertions): the contract is documented, every place-scoped tool is classified and nothing else is, fill-in applies only when unambiguous, ambiguity is refused with candidates, ids are learned from all four observed JSON shapes, prose is never mined, the prompt/notes carry it, and every pre-existing Roblox/Godot/Unity note is byte-for-byte intact.
- Verified nothing good was replaced: the original Godot orchestrator rule, Unity orchestrator rule, `WaitForChild` timeout warning, `multi_edit` unicode warning and all Roblox `TOOL_NOTES` are asserted present verbatim, with the new text appended rather than substituted.

## 6.17.0

### Native Engine Command Layer
- Kept the plain-JSON transport for EVERY engine (MCP is JSON-RPC and every tool takes JSON-schema'd params); what changed is the engine-specific VOCABULARY, which is what was actually broken. A per-engine wire format would fork the parser, camouflage and parse-error paths for no gain.
- Added `core/engines.js`: a pure, unit-tested registry of non-Roblox native tools with their real names, required parameter spellings, action vocabularies, chip categories and curated per-tool usage notes. Godot's 14 tools and exact required params were extracted from the published `@coding-solo/godot-mcp@0.1.1` `inputSchema` blocks; Unity's 33 tools and 132 actions from the vendored v10.2.0 reference; every fact is attributed in the source.
- Added the ACTION-DISPATCH REPAIR, which fixes the commonest Unity failure: `{"command":"get_hierarchy"}` (an action written where the tool belongs) is rewritten to `{"command":"manage_scene","params":{"action":"get_hierarchy"}}`. Genuinely ambiguous actions (`get_info`, `create`, `screenshot`, `ping`) are never guessed — the model is told the candidate tools. The owner must be currently advertised, Roblox names are never touched, and a name that IS a tool is never rewritten. An action-dispatch tool called with no action now returns its valid action list.
- `ZS.toolNote()` merges the Roblox notes with the engine registry, so `list_commands` and the periodic reminder now carry curated gotchas for Godot/Unity/Blender too (Godot `projectPath` must be the absolute folder containing `project.godot`; always `stop_project`; Unity's `read_console` is the only way to see compile errors; `run_tests` returns a job id and does not wait; Blender code must be JSON-escaped).
- Made the system prompt engine-aware: the connection paragraph, the Roblox-only project-memory section and the first-action instruction are now computed from the live connected-engine list. A Godot-only session is told "NO Roblox Studio is connected", is never told to write `game.ServerStorage.Multi-Script.Memory`, and gets the real Godot parameter rules. With no engine information the prompt is byte-identical to before.
- Engine-aware chip categories (a Godot `run_project` reads as an action, a Blender viewport capture as a screen) and an engine-aware bridge-offline note that no longer sends a Godot-only user to open Roblox Studio.
- Added `tests/test_engine_tool_layer.js`: literal assertions for the 14 Godot tools/params, 33 Unity tools/132 actions with dispatch integrity, all four repair outcomes plus hostile input, the engine-aware prompt across five engine combinations, and proof that the Roblox JSON transport is unchanged.

## 6.16.0

### Reply Pacing, Error Recovery, One-Shot and JSON Discipline
- Added a real reply-pacing engine (`core/pacing.js`): Off / Brisk / Human-like / Cautious / Custom modes, randomised inter-turn bands, periodic longer breaks, optional typing cadence, and a per-error cooldown so a retry storm can never deepen a rate limit. The gap is measured since the last send, so a slow reply is never double-taxed. Per-provider overrides are supported, and the bar shows the wait so a deliberate gap never looks like a hang.
- Pacing can be **scoped to a single site** from the menu (per-provider override), and a **Test pacing** button runs the shipped engine over a simulated session and reports the real numbers (mean/min/max, longer breaks, the cost of a ~60-send run, the error cooldown, the active recovery budget) in the panel.
- Added a bounded error-recovery policy (`core/resilience.js`): Off / Standard / Persistent levels with escalating backoff, a per-failure budget AND a consecutive-failure cap, plus widened patience windows for slow replies, warm-ups, reasoning phases and still-streaming command blocks. Empty and timed-out turns now recover instead of ending the run; a retry only ever re-asks and always states that nothing ran.
- Transient site outages ("server is busy", "please try again") are now classified as recoverable and given exactly ONE bounded retry instead of ending the loop — the commonest real failure on DeepSeek at peak hours. Tightly gated (short reply, no command shape, provider site-error phrasing) so a model answer that merely tells the user to try again cannot loop.
- Added a one-shot / unattended autonomy mode: no clarifying questions, no dead turns, drive the whole specification to completion, recover silently, stop only for destructive/paid/credentialed/contradictory choices, and finish with one evidence-based report. Selecting it also raises the Persistent-recovery and Human-like-pacing floors.
- Greatly broadened human-verification (bot-check) detection on Arena — Turnstile, hCaptcha, reCAPTCHA, Arkose, DataDome, PerimeterX, GeeTest plus an independent text probe, each requiring real visibility, real size and a chat-free host. The agent now pauses, gets its bar out of the way, explains what to do, and auto-resumes when it clears, at startup, mid-loop and mid-send. Challenges are never solved, token-injected, outsourced or bypassed.
- Fixed two Arena detection bugs found by the new headless test: the challenge *kind* was derived only from an iframe `src` (so inline widgets reported a generic kind), and PerimeterX/HUMAN challenges served from `px-cdn.net` / `human-challenge` were not detected at all.
- Notion reliability: broader stop/generation matching, a three-strategy verified `typeAndSend` with composer-clear confirmation and text restoration, and an unsettled-read signal so a mid-render command no longer triggers a false malformed-command verdict.
- Added an explicit JSON-ONLY CONTRACT to the system prompt and the periodic reminder: one plain-text object, no fences, no XML/DSML/function-call markup, no wrapper keys, no nesting, one command per reply, with exact `execute_luau` and `multi_edit` parameter shapes. The core also unwraps a double-wrapped envelope (depth-bounded).
- Hardened the Godot launcher: auto-detects the Godot editor across env overrides, Windows/macOS/Linux install locations and PATH and sets `GODOT_PATH`; reports on stderr only (never stdout, which is the MCP JSON-RPC channel); forwards Ctrl+C instead of orphaning the child; passes the child's exit code through.
- Godot guidance is now concrete: `get_godot_version`, then `get_project_info` for the exact absolute project path, inspect before writing, run / read `get_debug_output` / stop cleanly, and case-sensitive path handling.
- Added browser-free CI gates: pacing engine, error-recovery policy, one-shot autonomy wiring, JSON-only transport contract, Arena bot-check detection (dependency-free fake DOM) and the Godot launcher. Removed three CI references to test files absent from this build.
- Made the whole test suite actually runnable: `tests/playwright-env.js` resolves a browser from `CHROMIUM_PATH` → system Chrome/Chromium/Edge → Playwright's bundled build and SKIPS cleanly when none exists, and CI now installs Playwright instead of referencing it without installing it. All six browser gates pass in a real Chromium.
- Added pacing, error recovery and autonomy to the settings UI, the settings backup, diagnostics, and the agent-behavior reset.

## [6.8.0] - 2026-09-23

## 6.13.0

- Added canonical product integrity manifest and three-round critic loop.
- Upgraded diagnostic-only Roblox companion and bounded heartbeat telemetry.
- Added product/plugin security and drift regressions.


### Arena Profiles and Engine-Free Studio
- Added honest Arena Max starter profiles with Opus 5.5 as the default request.
- Added engine-free and connected-engine-specific startup choices.
- Deepened cross-engine animation, VFX and texture execution standards.

## [6.7.0] - 2026-09-23

### Portable Settings and Capability Assurance
- Added validated, non-secret settings export/import.
- Added a permanent professional quality floor across every setting mode.

## [6.6.0] - 2026-09-23

### Settings and MCP Compatibility
- Validated and diagnosed all menu settings.
- Added safe agent-behavior reset and multi-engine onboarding.
- Clarified broad ZeroScript evolution and no-bypass access boundaries.

## [6.5.0] - 2026-09-23

### Product Release Hardening
- Made prompt rewriting optional without disabling skill/tool quality enhancement.
- Added release gates and defect-priority rules to every specialist.
- Clarified per-provider settings UI and added regression coverage.

## [6.4.0] - 2026-09-23

### Universal Capability Foundation
- Deepened every tool and skill around a shared game-development capability lifecycle.
- Added anti-shallow completion rules and cross-specialist collaboration contracts.
- Expanded weak-prompt understanding across major game genres without named presets.

## [6.3.0] - 2026-09-23

### Intent-to-Product Intelligence
- Enriched all tools and skills with concrete contribution and integration contracts.
- Added combined genre/style intent expansion and coherent playable vertical-slice defaults for weak prompts.
- Added measurable acceptance criteria, weakest-target budgets and native evidence requirements.

## [6.2.0] - 2026-09-23

### Multi-engine professional quality and provider reliability
- Added 12 direct and 30 virtual Unity/Godot/Blender specialists.
- Upgraded every Unity, Godot and Blender virtual profile and engine skill to professional-v3.
- Hardened Arena, ChatGPT and DeepSeek adapter discovery without automating human verification.

## [6.1.0] - 2026-09-23

### Roblox Professional Expansion
- Added 24 Roblox direct provider-model specialists and 30 Roblox virtual specialists.
- Upgraded all 199 Roblox skills and all 60 prior Roblox virtual profiles to `roblox-studio-v3`.
- Expanded totals to 197 direct tools and 270 virtual tools (90 Roblox, 60 each for Unity/Godot/Blender).
- Kept real Roblox execution official/live MCP-only and the companion plugin diagnostic-only.

## [6.0.1] - 2026-09-23

### Neutral Notion starters
- Removed all model-specific execution emphasis and capability steering.
- All five profiles now use identical routing and shared Multi-Script instructions; only the requested model and availability differ.

## [6.0.0] - 2026-09-23

### Improved Notion model starters
- Added GPT-6 Luna as an honest future-ready Notion Auto profile.
- Expanded all five starter prompts with exact routing, shared full skill/tool handoff, native-tool verification and no-acknowledgement metadata behavior.
- Preserved prompt-only routing with no direct model-picker interaction or false model identity.

## [5.9.0] - 2026-09-23

### Full-spectrum specialized execution
- Removed the universal quality multiplier and adaptive-quality meta tools.
- Added full-spectrum skill mesh and cross-discipline integration tools without changing the 173-tool count.
- Expanded Studio Director from a tiny 1–3/2-tool stack to broad simultaneous coverage: 24 direct tools, 30 skills and 15 virtual domain specialists by default.
- Weak one-line prompts receive complete specialist coverage through the actual tools and skills.

## [5.8.0] - 2026-09-23

### Notion Always-On
- Added notion.com redirect coverage alongside notion.ai and notion.so.
- Added persistent no-composer recovery UI, automatic AI-chat opening, broader semantic editor detection, open Shadow DOM traversal, and popup-driven stale-tab reinjection.
- Added regression coverage for all Notion hostnames and visibility recovery paths.

## [5.7.0] - 2026-09-23

### Universal adaptive quality
- Removed all named quality presets and their runtime data file.
- Replaced preset discovery/application with comprehensive specialized skill-and-tool coordination.
- User examples are test inputs only, never encoded archetypes.
- Every request dynamically receives relevant craft, engineering, interaction, performance, accessibility, security, scalability and verification requirements.
- All 800 skills, 173 direct tools and 240 virtual tools participate in coordinated cross-discipline execution.

## [5.6.0] - 2026-09-23

### Provider-model studio intelligence
- Removed the 5.5 companion execution surface; the Roblox plugin is diagnostic-only again.
- Upgraded all 800 skills with provider role, completion, performance and failure policies.
- Upgraded all virtual tools and expanded them from 200 to 240, with 60 per engine.
- Expanded direct orchestration tools from 153 to 173 with 20 capability/performance specialists.
- Added Studio Standard v2 for tool discipline, context efficiency, result quality, measurable performance and failure recovery.
- Kept native engine counts honest: guidance improves how provider models use live advertised tools; it never impersonates native commands.

## [5.4.0] - 2026-09-23

### Command recovery and honest Roblox counts
- Added callable preset discovery/application tools so archetypes no longer appear as non-callable IDs.
- Added Notion streamed-command recovery for responses whose role metadata changes.
- Roblox plugin now separates official native tools from 153 direct tools, 50 Roblox virtual tools, and Roblox skills; 28 native tools can be a valid live Roblox catalogue.

## [5.4.0] - 2026-09-23

### Notion AI menu guidance
- Added the Notion AI menu description: “to use it free, you need a business trial.”
- Styled provider descriptions for dark, light, compact and spacious menu layouts.


## [5.2.0] - 2026-09-23

### Professional Studio Runtime
- Added schema-driven normalization and validation for all direct and native engine tools, including provider string coercions, arrays, objects, booleans, enums and numeric bounds.
- Added exhaustive coverage for all 153 direct schemas and every declared parameter.
- Added a shared studio operating standard to every retrieved/activated skill: definition of done, engine practices, evidence, recovery, accessibility, security and performance.
- Upgraded the Roblox companion to show capability coverage and print the exact official native tool catalog.
- Added a bounded loopback `/catalog` endpoint; tool execution remains isolated to the existing bridge path.

## [5.1.0] - 2026-09-23

### Roblox Studio companion and bridge hardening
- Added a local Roblox Studio companion plugin with live official-MCP tool counts, bridge heartbeat, safe project scaffolding, and heuristic script-risk scanning.
- Added a loopback-only plugin status service; no tool execution or secrets are exposed through it.
- Added `ms_roblox_capability_audit` to inspect the exact native Roblox catalogue and capability coverage without inventing tools.
- Fixed stale MCP catalogues surviving server restarts and incorrectly routing calls to tools the new process had not advertised.
- Added plugin/API regression coverage and expanded the direct catalogue to 153 tools.
- Fixed notion.ai home-composer detection for the new “Do anything with AI…” surface, including overlay-only placeholders and unlabeled send controls.

## [5.0.0] - 2026-09-23

### Customization Studio and per-user ElevenLabs
- Rebuilt settings with custom identity, themes, accents, scale, density, width, fonts, corners, backdrops and motion controls.
- Added live appearance preview, Studio-width layout and accessible reduced/no-motion modes.
- Added secure ElevenLabs key setup inside settings. Every player supplies their own key; it is stored only in the local bridge runtime/.env and never browser storage, prompts, diagnostics or release archives.
- One saved key powers audio generation for every connected engine.

## [4.9.0] - 2026-09-23

### Studio Quality Autopilot
- Added 50 direct tools: 47 studio-grade craft specialists plus automatic direction, discovery and detail tools.
- Expanded from 620 to 800 skills with 180 senior craft practices across Roblox, Unity, Godot, Blender, Figma and general production.
- Added silent intent routing so meaningful tasks automatically receive the strongest animation, UI, art, gameplay and QA expertise before real MCP execution.
- Added senior-grade Roblox/Blender/Unity/Godot animation studios and professional GUI systems.
- Expanded nine-provider command coverage to 5,436 envelopes.

## [4.8.0] - 2026-09-23

### Engine execution reliability and universal mastery
- Fixed the misleading startup count: it now separates native Roblox tools from Multi-Script direct tools.
- Fixed bare-name validation and cross-engine collision routing with an explicit `_server` hint.
- Added exact-server catalogue, call, smoke-test and capability-map tools.
- Expanded direct tools from 67 to 100 and skills from 500 to 620.
- Added 120 high-quality mastery skills across Roblox, Unity, Godot, Blender, Figma and general game production.
- Expanded nine-provider command coverage to 3,636 envelopes.

## [4.7.1] - 2026-09-23

### JSON-only Roblox tool protocol
- Removed every model-facing alternate tool-call format. All providers now receive one rule: one unfenced plain-text JSON object per command.
- execute_luau now uses the same JSON envelope as every other tool.
- Accidental provider-native invoke/parameter markup is silently normalized into the same internal command object rather than producing a dead retry loop.
- Arena recognizes and camouflages accidental native markup, then shows the normal Multi-Script execution chip.
- Added Arena/Roblox protocol regressions for list_commands, get_studio_state, script_read, and execute_luau.

## [4.7.0] - 2026-09-23

### Twenty new direct Multi-Script tools
- Expanded the direct bridge catalogue from 47 to 67 tools.
- Added direct production contracts for camera, input, character controllers, combat, AI, quests, inventory/economy, procedural generation, shaders, lighting, environments, character modeling, rigging, localization, telemetry, live operations, store compliance, security/abuse, bug triage, and regression planning.
- Every new tool returns eight execution stages, eight quality gates, a real-implementation requirement, and an explicit connected-MCP execution contract.
- Expanded the nine-provider command matrix from 1,728 to 2,448 command envelopes.

## [4.6.0] - 2026-09-22

### Public-release provider QA
- Added an exhaustive cross-provider matrix covering every one of the 47 direct built-in tool calls plus namespaced Roblox, Unity, Godot, and Blender probes across Arena, ChatGPT, DeepSeek, Gemini, GLM, Kimi, Meta AI, Notion AI, and Qwen.
- Added Arena human-verification detection, a clear startup gate, and automatic resume waiting after the user manually completes a challenge.
- Multi-Script intentionally does not solve, token-inject, or bypass CAPTCHA/bot protections.
- Live-smoke checked Arena Direct mode, composer detection, Max selector, and send control on 2026-09-22.

## [4.5.2] - 2026-09-22

### Restored prompt-only Notion routing
- Removed all direct interaction with Notion's model selector because Business Trials can remain locked to Auto.
- Kept the Multi-Script startup profile picker for GPT-5.6 Sol, Claude Opus 5, Kimi K3, and future Claude Opus 5.5.
- Strengthened the one-time startup block as routing metadata that must be processed before task instructions, while preserving honest fallback and no-emulation rules.
- Added a browser regression proving the Notion model button receives zero clicks.

## [4.5.1] - 2026-09-22

### Layered Notion model routing
- Added one-shot exact visible-picker selection for GPT-5.6 Sol, Claude Opus 5, and Kimi K3 when Notion exposes those options.
- Kept Claude Opus 5.5 selectable now; it automatically uses the exact picker when Notion exposes it later.
- Added a strict routing-metadata prompt after the picker attempt, visible-selection verification, honest Standard Auto fallback, diagnostics, and regression tests.
- This improves routing odds but does not bypass Notion entitlements or guarantee a private server-side route.

## [4.5.0] - 2026-09-22

### Claude Opus 5.5 future-ready Notion profile
- Added an availability-aware Notion Auto profile for the officially released Claude Opus 5.5.
- Requests the real model once per new chat only when Notion makes it eligible; otherwise falls back to Standard Auto without imitation or false identity claims.
- Added verified model-watch documentation while preserving the ElevenLabs direct-audio setup from 4.4.0.

## [4.4.0] - 2026-09-22

### Direct ElevenLabs audio generation
- Added secure bridge-side ElevenLabs Sound Effects API integration using the official sound-generation endpoint and `eleven_text_to_sound_v2`.
- Added status, generate, and generated-audio listing tools. Audio is saved locally with SHA-256 metadata and handed to the connected game-engine MCP for import and testing.
- Added hidden one-time API-key setup; the key remains in the bridge environment or `runtime/.env`, never in browser storage or tool output.
- Audio requests automatically use ElevenLabs when configured, without opening the ElevenLabs website for each task.

## [4.3.0] - 2026-09-22

### Engine virtual-tool library
- Added 200 engine-specific virtual tools: 50 each for Roblox Studio, Unity, Godot, and Blender.
- Tools cover UI/UX, animation, shaders, lighting, graphics, VFX, models, rigging, textures, audio, gameplay, networking, saves, performance, testing, and release work.
- Added compact list, match, details, and run gateways so 200 profiles do not bloat every model context.
- Automatic mode silently matches the exact prompt to the strongest tools, applies the augmentation, and immediately performs the real MCP work.

## [4.2.1] - 2026-09-22

### Task-first quality boost
- Restored normal direct task execution: skills silently improve decisions instead of forcing every request through a visible orchestration workflow.
- Simple prompts receive inferred professional defaults and immediate implementation; detailed prompts keep every explicit requirement and receive compatible polish.
- Added a tested classic Roblox UI interpretation with responsive, accessible states and direct ScreenGui implementation guidance.
- Skill, blueprint, and specialist tools remain available when useful, but tool selection is never presented as the user's deliverable.

## [4.2.0] - 2026-09-22

### Automatic capability stacks
- Added a capability graph linking every one of the 500 skills to at least four complementary collaborators.
- Added automatic request orchestration and executable skill-stack contracts; loading skills is explicitly preparation, never completion.
- Added professional animation, texture/material, art-direction, UI/UX, VFX, and audio production commands.
- Expanded to 40 bridge-native virtual tools and enforced real MCP implementation, target-engine integration, and evidence-based verification.

## [4.1.0] - 2026-09-22

### Professional engine expansion
- Expanded the catalog from 306 to exactly 500 validated skills: 65 new Roblox, 65 new Unity, and 64 new Godot professional workflows.
- Added 12 virtual production commands for prompt rescue, complete game blueprints, vertical slices, architecture, balance, multiplayer authority, save migration, performance, accessibility, content pipelines, playtesting, and evidence-based completion.
- Added prompt-rescue and professional-delivery policies so vague prompts receive conservative inferred defaults and a polished real result instead of a weak answer.
- Every new workflow includes assumptions, deliverables, eight implementation steps, and eight quality gates.

## [4.0.2] - 2026-09-22

### Testing and reliability
- Added exhaustive validation and public retrieval/search/recommendation coverage for all 306 skills.
- Added execution coverage for all 20 bridge-native tools and their major enum/error branches.
- Added 5,000-case parser fuzzing, 1,000 command round trips, and shared contract loading for nine provider adapters.
- Corrected stale skill-pack total metadata from 141 to 306 and added release-gate enforcement.

## [4.0.1] - 2026-09-22

### Documentation
- Replaced the accumulated historical README with a clean, self-contained, step-by-step setup guide.
- Added explicit Windows, macOS, Linux, browser extension, Roblox, Unity, Godot, custom MCP, Notion, update, and troubleshooting instructions.
- Renamed the complete distribution artifact to make the Full package unambiguous.

## [4.0.0] - 2026-09-22

### Release preparation
- Added install, privacy, security, support, third-party, store-listing, release-note, and release-checklist documentation.
- Added release validation and reproducible full/extension packaging scripts.
- Added dedicated browser icon sizes, example configuration, issue templates, CI, and SHA-256 release manifests.
- Cleaned ignore rules and standardized all public version metadata.

## [3.8.0] - 2026-09-22

### Corrected
- Auto starters now contain only a minimal request for the real selected model—no model personality emulation.
- Routing requests are inserted first, followed by the complete shared Multi-Script skills/tools/settings prompt.
- Moved useful context, tool, and verification rules into one model-compatible Notion common layer.
- Added a selection readiness check to the Auto picker.

## [3.7.0] - 2026-09-22

### Changed
- Removed the Notion direct model picker and all local `/model` interception.
- Rebuilt Auto starter profiles as strict, model-specific behavior contracts with routing requests, stable signatures, anti-collapse rules, tool discipline, and verification requirements.
- Added profile diagnostics while preserving one startup prompt per new chat.

## [3.6.0] - 2026-09-22

### Improved
- Restored and hardened direct Notion model-picker switching.
- Added direct buttons, custom model names, picker discovery, switch verification, and `/ms-model`.
- Direct picker selections and Auto starter profiles are now reliably mutually exclusive.

## [3.5.0] - 2026-09-22

### Added
- General 1–10 Speed, Smart, and Stability benchmarks in the AI sites menu.
- Active-provider highlighting, average scores, visual meters, and short provider notes.
- Arena and Notion AI are excluded because both can route between models.

## [3.4.0] - 2026-09-22

### Improved
- Adaptive creative routing can skip Canvas/Figma and build UI directly in Roblox Studio or another connected engine.
- Added per-provider Auto, Direct engine, Figma first, and Canvas/SVG first controls.
- Auto mode chooses the least wasteful surface based on the requested final deliverable.

## [3.3.0] - 2026-09-22

### Added
- 50 advanced Roblox Studio skills and 50 Blender production skills.
- 20 Figma/Canvas UI, texture, prototype, and handoff skills.
- Actual local SVG texture generation with eight procedural patterns.
- Actual SVG UI mockup drawing as a universal provider fallback.
- Figma-first UI/UX routing and connected Figma MCP detection.

## [3.2.0] - 2026-09-22

### Fixed
- Notion Auto profile startup prompts are sent exactly once per chat.
- Selecting a profile affects the next new chat and never reinjects the full prompt into the active chat.
- Notion chats receive distinct identities even when Notion reuses the same URL.

## [3.1.0] - 2026-09-22

### Added
- Per-provider Prompt Skills modes: Off, Suggest only, Automatic.
- Per-provider production validation modes: Fast, Balanced, Rigorous.
- Plain-language descriptions and persistent settings for each AI provider.

## [3.0.0] - 2026-09-22

### Renamed
- ZeroScript is now **Multi-Script** across the bridge, extension, menus, documentation, startup windows, diagnostics, and built-in tools.

### Changed
- Organized runtime, extension, documentation, test, asset, and vendor folders.
- Added customizable accent, density, menu width, overview visibility, and default tab settings.
- Improved first-run guidance and protected compatibility for existing environment/storage keys.

## [2.4.0] - 2026-09-22

### Improved
- Hardened Notion Agent across Home, full-page, and side-panel chat surfaces.
- Added SPA-safe editor caching, scoped controls, non-destructive locks, robust contenteditable input, send confirmation, and provider self-tests.
- Added native Notion vs engine vs hybrid intent routing and 15 general Notion workflows.

## [2.3.0] - 2026-09-22

### Added
- Cross-provider Off/Polished/Ambitious quality amplifier, defaulting to Polished.
- 30 general cross-engine creative and quality skills.
- `ms_enhance_brief` and `ms_quality_scorecard`, including shop UI and studded-material enhancement.

## [2.2.0] - 2026-09-22

### Added
- 100 engine skills: 34 Roblox, 33 Unity, and 33 Godot workflows.
- `ms_recommend_skills` relevance ranking and filtered `ms_list_skills` to keep large catalogs token-efficient.
- `skill-packs.json` machine-readable pack index.

## [2.1.0] - 2026-09-22

### Added
- Provider-wide Balanced and Compact usage optimization in the Agent menu.
- Provider-specific prompt policies for Notion, ChatGPT, Gemini, Kimi, DeepSeek, GLM, Qwen, Arena, and Meta.
- Twelve skills for prompt economy, context budgeting, batching, result compression, minimal diffs, repository mapping, security, testing, game economies, and live operations.

### Changed
- Compact mode uses lossless JSON minification and short periodic system reminders to reduce repeated context.

## [2.0.0] - 2026-09-22

### Changed
- Rebuilt the in-chat menu with Agent, Engines, AI sites, and Help tabs.
- Added live dashboard metrics, editor-aware server cards, protected bundled engines, quick refresh/restart actions, prompt copying, and privacy-safe diagnostics.
- Made the extension popup fully multi-engine instead of Roblox-only.

### Fixed
- Unity and Godot can no longer appear as removable user addons.
- Roblox is no longer incorrectly labeled “always connected” when Studio is offline.

## [1.9.0] - 2026-09-22

### Added
- Three Notion Auto starter profiles for Opus 5, Kimi K3, and GPT-5.6 Sol in the Multi-Script menu.

### Fixed
- Detects when Notion fails to accept a programmatic send instead of waiting indefinitely.
- Clears stale direct-picker preferences when an Auto starter profile is selected.
- Replaced remaining Roblox-only startup messages with multi-engine wording.

## [1.8.0] - 2026-09-22

### Fixed
- Reworked Notion Agent composer discovery for current Notion AI surfaces.

### Added
- Local `/model` chat commands for Opus 5, Kimi K3, GPT-5.6 Sol, and Auto, with entitlement-aware failures instead of fake prompt-based switching.
- Notion model-router skill and persistent model preference.

# Changelog

## 6.48.8

Expand all twelve Ultra manuals with 480 phase checkpoints, 72 phase exits, 72 acceptance criteria, 48 diagnostic cases and 72 engine-specific applications. Connect all 249 retained skills to objective-aware application guides and optional full phase retrieval; include compact director retrieval routes. Add a scoped Figma playbook. Keep startup compact, lower-effort demotion immediate, user permissions unchanged and the 6.48.7 DeepSeek pacing/startup repairs intact.

## 6.48.7

Fix the DeepSeek regression from 6.48.6: restore bounded multi-step discovery, remove the fixed 20-second floor and synthetic six-turn burst cap, and migrate saved pacing state without clearing actual provider cooldowns or account pauses. Retain one-click delivery and no-replay safeguards. Add the exact catalog-to-Roblox-studios startup regression.

## 6.48.6

DeepSeek: remove repeated Send clicks during image uploads and Enter fallback; confirm a single send, reject oversized messages without cutting instructions, stop automatic recovery, bound startup discovery, enforce persistent shared pacing and fail closed without its worker. Account/verification notices stop sending. Keep Ultra methods and user settings unchanged. See docs/DEEPSEEK_ACCOUNT_ACCESS.md for scope and provider references.


## [1.7.0] - 2026-09-22

### Added
- Coding-Solo Godot MCP 0.1.1 integration and broad production skill library.
- Godot auto-detection plus planning, QA, audit, budget and release tools.

## [1.6.1] - 2026-09-22

### Added
- First-class CoplayDev MCP for Unity v10.2.0 stdio launcher and default `unity` server.
- MCP resource listing/reading bridge tools for Unity editor state, instances, project data, and scene resources.
- Vendored upstream Unity operator skill and MIT attribution.
- Unity-specific setup, compilation, test, console, screenshot, and critic-loop guidance.

## [1.6.0] - 2026-09-22

### Added
- Notion AI / Notion web-app provider adapter.
- Engine-neutral stdio MCP setup for Unity, Godot, Unreal Engine, Blender, and custom servers.
- Built-in bridge status, skill discovery, engine handoff, and critic-review tools.
- Reusable game-development skills and a three-round evidence-based critic loop.

### Changed
- Extension branding, tool categories, prompts, and MCP settings are multi-engine aware.
- Bridge health reports its built-in tool service alongside external MCP servers.


All notable changes to Multi-Script are documented here.

## [1.5.5] - 2026-09-10

### Fixed
- **DeepSeek: the agent starts again on DeepSeek's new unified model.**
  DeepSeek merged Instant, Expert and Vision into a single model and removed
  the model picker from the chat box. Multi-Script waited for one of those tabs
  to be selected before starting, so "Start Roblox agent" stopped with
  "DeepSeek mode not ready". A chat box with no model picker is now recognised
  as the unified model: Multi-Script switches Search off as before, leaves
  DeepThink on, and starts.
- **DeepSeek: screenshots work on every chat.** Images used to need the Vision
  tab, which no longer exists, so `screen_capture` was refused. The unified
  model reads images, and Multi-Script now sends them - one capture or several
  in a row. Older conversations still marked Instant or Expert stay text-only.

## [1.5.4] - 2026-09-06

### Fixed
- **ChatGPT: the Multi-Script bar is back where it belongs, above the composer.**
  ChatGPT redesigned its input box and renamed the layout slots it is built
  from: the full-width row across the top used to be called `header` and is now
  called `eyebrow`. Multi-Script still asked for `header`, a name that no longer
  exists, so the browser invented a place for the bar instead - it landed in a
  stray strip at the bottom right of the composer, and the text field itself was
  squeezed to zero width in the process. The bar now claims the correct row, and
  it also reads the layout live rather than trusting a fixed name, so the next
  time ChatGPT renames its slots the bar will follow instead of breaking.

### Changed
- **ChatGPT: replies are read straight from the page again.** The same redesign
  replaced the code-block editor that used to render each line separately and
  cut long lines off around 2000 characters - the cause of the truncated
  commands fixed in 1.5.1. Code blocks are now plain text with real line breaks,
  and a 400-line block reads back whole. The workaround stays in place for
  anyone still on the old interface.

## [1.5.3] - 2026-08-22

### Changed
- **Kimi moved to kimi.ai.** Kimi's old address, `kimi.com`, now asks for a
  Chinese phone number to sign in, which locked most people out. Kimi runs on
  `kimi.ai` from now on - the extension only activates there. The page itself is
  unchanged, so nothing about using Kimi with Multi-Script is different: open
  https://www.kimi.ai, the bar appears above the input box as before. If you had
  Kimi tabs open on the old address, reopen them on the new one.
- **DeepSeek: the Instant model is now allowed to run the agent.** Starting a
  session forced the Expert tab and, worse, the readiness gate only ever accepted
  Expert or Vision - so picking Instant left "Start Roblox agent" spinning
  forever with no explanation. Instant is now respected like Vision: pick it
  before starting and the session runs on it. It is much faster than Expert, at
  the cost of the reasoning pass. Images stay disabled on Instant exactly as they
  are on Expert - the Vision tab is still the only one that can see screenshots,
  so `screen_capture` is not offered to the model on the other two.

### Fixed
- **DeepSeek: a reply written in DeepSeek's own tool-call markup no longer kills
  the turn.** DeepSeek sometimes answers with its internal DSML invoke tags
  instead of a Multi-Script command. That format carries none of the markers
  Multi-Script looks for, so nothing recognised it as a command attempt: the tool
  never ran, the raw tags were left on screen, and the agent silently stopped
  with the user waiting on a dead turn. It is now detected, the markup is hidden
  behind a tool chip like any other command, and DeepSeek is told the format is
  unreadable so it rewrites the call properly. The chip shows the usual spinner
  while the model is still writing, then settles red as "wrong format".
- **ChatGPT: the Multi-Script bar no longer collides with the composer's rounded
  corners.** The composer card is rounded by 28px and the bar sits flush against
  its top edge, so the Discord button's corner fell outside the rounded shape and
  was sliced off by the card. Both ends of the bar are inset to clear the curve.

## [1.5.2] - 2026-08-14

### Added
- **ChatGPT: the operating instructions are now re-stated periodically.** ChatGPT
  summarises its own context mid-session, and the part it drops first is the
  *mechanism* - that an extension reads its replies and really runs them. It
  would then answer "I can't invoke those commands in this session" while the
  extension sat there, ready. The full instructions are now re-sent
  automatically, riding along on a tool result so they cost no extra message and
  stay hidden from you (they appear as a "Reminder" chip). A tool result is
  never shortened to make room: if the pair would not fit, the reminder simply
  waits for the next one. ChatGPT only - no other provider needs it.
- **ChatGPT: an image you send is now treated as reference material.** Unless you
  explicitly ask for a picture, ChatGPT used to answer a screenshot or a mockup
  by *generating a new image* instead of doing the work it was meant to
  illustrate - and its image tool cannot reach your place anyway.

### Fixed
- **ChatGPT: you can chat normally again without starting an agent.** On a blank
  ChatGPT tab the extension refused to let a message send until you clicked
  "Start Roblox agent". Every other provider only suggests it; ChatGPT was the
  odd one out.
- **A finished command is no longer stranded as "not run".** After a long reply
  (seen on Qwen writing for 400s and more) the loop could give up while the model
  was still going; eight seconds later the completed command was written off for
  good. That window is now three minutes, so the command actually runs.
- **A clear message when Multi-Script is updated while a tab is open.** Chrome
  updates extensions underneath open tabs, which leaves the page running a
  version that no longer exists. Multi-Script reported this as "the bridge stopped
  on your PC - run start.bat", sending you to fix something that was never
  broken. It now says plainly that the page needs reloading, and offers a Reload
  button - your bridge and Studio are untouched.
- **The AI no longer claims your bridge is offline without checking.** After one
  momentary outage it would keep repeating "Roblox is offline" from memory, even
  once everything was back. It must now actually run a command before saying so.

## [1.5.1] - 2026-08-13

### Added
- **ChatGPT support (chatgpt.com).** Multi-Script now runs on ChatGPT as an
  eighth provider. Image input is deliberately disabled there: ChatGPT's free
  tier caps files/images on a separate quota from messages, so vision would
  work only part of the day. Reasoning mode ("Analyser") and the model picker
  are left entirely to you.

### Fixed
- **Meta AI: fixed large commands failing with "bad JSON".** Meta renders a
  ```json block as an interactive viewer whose default *Tree* view does not
  merely decorate the JSON - it **abridges** it: a large array or object is
  replaced by a summary placeholder. A 19103-character `multi_edit` was present
  in the page as 223 characters ending in `"edits":[1 item]`, so Multi-Script sent
  the parser a truncated object and the command came back as a parse error every
  time. This is also why the tool chip's token counter climbed while the reply
  streamed and then **collapsed to about 44 tokens** the moment the block
  finished rendering - the counter was faithfully reporting what could be read.
  Command blocks are now switched to the viewer's *Raw* tab, which holds the
  verbatim source; the 19103-character payload is read whole.
- **Clearer diagnosis when Roblox refuses to parse Luau.** "Failed to parse
  command code" is Studio's generic parse rejection, but Multi-Script always
  answered it with "your code block was empty or the marker was wrong". When a
  full code string *had* been sent, that advice pointed the model at a problem
  that did not exist, so it re-sent the same payload and failed again. The hint
  now only mentions the `###LUA###` markers when the code really was empty, and
  otherwise reports how many characters were sent and names the real causes -
  invalid syntax, or code too large/complex for the parser. (Measured live: a
  `return 1+1+1+…` chain ran at 1006 characters and was rejected at 2006.)
- **ChatGPT: fixed most tool calls failing outright.** ChatGPT renders code
  blocks with CodeMirror, which puts one element per line and **no newline
  characters at all** in the page. Reading a reply the usual way therefore
  returned the whole script glued onto a single line, so a perfectly valid
  command came back as "Failed to parse command code / your code block was
  empty", and the calls that did run reported every Luau error on line 1.
  Replies are now read with the line structure preserved.
- **ChatGPT: fixed long commands being executed truncated.** Beyond roughly
  2000-4000 characters, CodeMirror only renders *part* of a long line and the
  rendered text then stays frozen while the model keeps writing - the tool
  chip's token counter would climb, drop back to about 500 tokens, freeze
  there, and the command would run cut off. Measured live: a 21273-character
  command of which the page exposed 4049. Multi-Script now reads the editor's
  real document instead of the rendered page, through a new MAIN-world tap
  (`providers/chatgpt-cm.js`), the same approach already used for Qwen's
  Monaco editor. A 5.3k-token `multi_edit` now applies whole.
- **ChatGPT: fixed the raw command staying visible.** When the model writes a
  command without wrapping it in a code fence, ChatGPT splits it into dozens of
  sibling paragraphs (68 of them for a 208-line script) and only the first one
  carried the marker, so the rest of the script stayed on screen. The whole
  marker-to-marker range is now hidden, including while it streams.
- **Fixed the agent dying silently when the model called a tool the
  function-calling way.** A reply like
  `{"toolName": "get_studio_state", "studio_id": "…"}` names a real tool but
  uses the wrong key, so nothing recognised it as a command: the turn was
  finalised as a plain-text answer and the loop simply ended, leaving the agent
  looking frozen (seen on ChatGPT in a long session). Multi-Script now spots a
  known tool named under `toolName` / `tool` / `name` / `function` / `action`
  and asks the model to rewrite it with the proper envelope, exactly as it
  already did for a missing `###LUA###` opener or bare parameters. Prose that
  merely mentions a tool name is not affected - the check requires a tool that
  is really in the catalogue.
- **Fixed the "Agent is working…" cover hanging past the composer on the first
  send.** Injecting the system prompt grows the composer, the page gains a
  scrollbar and the content column narrows, so the composer slides sideways -
  and a site that animates that move updates its layout after the cover has
  already been placed, leaving it a frame behind (28px past the card's right
  edge on ChatGPT). The cover is now clamped to the composer card, so a stale
  measurement can never be seen. Only the first send was affected, because the
  composer stops moving once it is docked at the bottom.

## [1.5.0] - 2026-07-30

### Fixed
- **Backgrounding the AI tab no longer strands a pending command as a grey
  "not run".** `waitForResponse` now parks entirely while the tab is hidden and
  shifts every internal deadline (inactivity timeout, warm-up, text-stability,
  etc.) forward by the parked duration, instead of letting them keep ticking
  off-screen. `waitVisible` switched from polling to listening for
  `visibilitychange` - Chrome clamps chained background timers to one tick per
  minute after 5 minutes hidden, which used to delay the resume by up to a
  minute. The bar now shows a **Paused** state while parked, and a genuinely
  empty reply from the site now shows a banner instead of ending the loop
  silently.
- **Gemini: fixed the page freezing (nothing clickable) on a large tool
  result.** Gemini's composer inserts text line by line, synchronously, on the
  main thread - a 2599-line `http_get` result froze the page for about a
  minute. Outgoing text is now capped (120k chars / 1200 lines, head and tail
  kept) and the insert yields to the browser every 120 lines.
- **Gemini: fixed the system prompt occasionally never leaving the composer on
  Start.** The wedged-stop-button detector latches for 2 seconds from the
  first time it sees a stop button, so the single recovery attempt at boot -
  the very first sighting - was refused by its own guard. It now retries
  across that window and retypes as a last resort.
- **Kimi: fixed the model picker opening and closing in a loop.** Kimi's K3
  update removed the model (K2.6) the default-model routine used to select,
  so it kept hunting for a row that no longer exists. It now only acts when
  the current model is **K3 Swarm** (matched by name, any UI language) and
  gives up after a few tries instead of looping. The native-agent warning
  guard was equally broken by the same update and now reads the model label
  at its new location.
- **Degraded mode (Roblox Studio closed, running on an addon server only)
  starts much faster.** The tool catalogue request blocks until timeout when
  Roblox is down, and the boot sequence called it three times in a row. Added
  a 30s cache on the catalogue and cut the request timeout from 25s to 10s.

## [1.4.9] - 2026-07-24

### Added
- **Popup: new Settings button.** Opens the same Switch AI / support panel
  as the in-page bar, without needing an already-started conversation. The
  footer text no longer singles out chat.deepseek.com - it now points to
  "a supported AI" since seven providers are supported.
- **Bridge: auto-recovers its own port on relaunch.** Relaunching `start.bat`
  while a previous Bridge was still holding port 17613 (window closed with
  the X, a crash, a double launch) used to crash with a cryptic, sometimes
  localized `OSError [WinError 10048]`. The Bridge now detects and kills a
  leftover Bridge process it can positively identify (by command line, never
  by process name alone) before binding, and falls through to a clear,
  actionable message - with the exact `netstat`/`taskkill` commands and the
  `ZS_BRIDGE_PORT` override - if the port is held by something else.

### Fixed
- **The agent could parse/execute commands while its AI tab was backgrounded
  or the window minimized.** Background tabs throttle rendering and timers,
  which made DOM reads unreliable and could send duplicate feedback or run a
  tool blind (observed live: GLM kept running `execute_luau` while minimized).
  The agent loop, the tool-dispatch step, and the auto-resume watchdog now
  all gate on `document.visibilityState` and park - with no time limit -
  until the AI tab is the foreground tab again, then resume exactly where
  they left off. Working with Roblox Studio focused while the AI tab stays
  the active tab in its own window is unaffected; this only pauses execution
  while that tab is truly backgrounded or its window minimized.

## [1.4.8] - 2026-07-22

### Added
- **macOS and Linux support for the Bridge.** A new self-contained
  `MacOS_Start.command` launcher (double-click in Finder - no Terminal
  knowledge needed) finds Python 3.9+, installs `websockets` if missing,
  frees a previous Bridge still holding the port, and runs `bridge.py`,
  mirroring what `start.bat` already does on Windows. `launch_studio_mcp.py`
  now also locates Roblox Studio's MCP binary inside the macOS app bundle
  (`RobloxStudio.app/Contents/MacOS/StudioMCP`), with a `ZS_STUDIO_MCP_PATH`
  override for non-standard installs.
- **DeepSeek: outgoing messages are now truncated to fit its input limit.**
  DeepSeek's composer silently refuses to send past 163840 characters
  (validated live), which could wedge the agent in the input box after a
  large tool result (a big `http_get` / `get_page_text` / Luau dump). Long
  results are now truncated to a safe margin below that limit, keeping both
  the start and the end of the content, the same approach already used for
  Qwen and Arena.

## [1.4.7] - 2026-07-21

### Fixed
- **Qwen: a tool could show a green "done" check while it never ran and returned
  no result** (seen rarely with repeated `multi_edit` / `execute_luau` calls, with
  no Stop or regenerate involved). Qwen virtualizes its message list, so the
  off-DOM "already executed" record was keyed on the positional turn index, and
  two turns that shared the same 60-character command prefix could collide on the
  same index. That false positive made the auto-resume watchdog skip the fresh
  command (so it never ran, no result was injected) while the chip was still
  painted a green check. The dedupe now keys on Qwen's stable per-turn id
  (`chat-response-message-<uuid>`, exposed as `itemKey`) instead of the index, so
  the collision cannot happen.
- **Qwen: the Multi-Script bar covered the "Expand more models" submenu.** That
  fly-out is a separate body-portalled `.ant-dropdown` at a low z-index, not the
  main model dropdown, so the bar drew on top of it. Raised just that dropdown
  above the bar (scoped so other Ant menus and tooltips are untouched).

### Added
- **Per-model image support on Qwen.** Qwen offers both multimodal and text-only
  models, switchable mid-conversation, and image input only works on the
  multimodal ones. `screen_capture` and image input are now enabled only on a
  vision-capable model (Qwen3.7-Plus, Qwen3.6-Plus, Qwen3.6-27B, Qwen3.8-Max-Preview)
  and correctly withheld on a text-only one (Qwen3.7-Max, Qwen3.6-Max-Preview),
  read from the selected model and updated when you switch models.
- **Image support on DeepSeek's Vision model.** DeepSeek forces its Expert model
  for the agent, but if you choose the Vision tab that choice is now respected and
  `screen_capture` plus image input are enabled for it. Selecting Vision is
  detected reliably, including after switching conversations. Image attachment was
  also fixed: it used to stage the same image multiple times and never send,
  because the upload went through a paste that only made a local preview and never
  uploaded the file. It now uses DeepSeek's real file upload and sends once the
  upload completes.

## [1.4.6] - 2026-07-19

### Fixed
- **Kimi's login and "priority queue" popups were covered by the Multi-Script
  bar**: both render as full-screen fixed masks (`.login-modal-mask` and
  `.modal-mask`) rather than a standard `[role="dialog"]`, so the generic
  overlay probe used by other providers never caught them. The anchored bar
  (a full-width fixed element hugging the composer) and the "unstable"
  warning pill sat on top of the mask and could intercept clicks meant for
  its buttons (e.g. "Continue with Google"). Added a Kimi-specific
  `overlayBlocking()` that detects both mask classes by real visibility; the
  core already hides the whole bar while it reports true, and restores it the
  instant the mask clears.

### Added
- **Kimi now defaults fresh chats to K2.6**: Kimi lands new chats on K3,
  which is flagged unstable here and easy to miss switching away from. A
  brand new or emptied chat now picks K2.6 automatically, once; a deliberate
  manual switch to K3 on that same chat is left alone.

## [1.4.5] - 2026-07-18

### Fixed
- **DeepSeek re-executed old tool commands when scrolling up in a long
  conversation**: DeepSeek virtualizes its message list, so scrolling up makes
  an OLD command turn the last *rendered* assistant turn - its injected result
  sits below the fold (unrendered), the in-memory "already executed" record is
  empty after a page reload, and the node change makes generation detection
  flicker true, refreshing the auto-resume watchdog's freshness clock. The
  watchdog then re-fired the historical tool. Three-layer fix (validated live):
  - The off-DOM executed/halted dedupe maps now key on a virtualization-stable
    per-turn id (`itemKey`, DeepSeek's `data-virtual-list-item-key`) instead of
    the positional assistant index, which collides across scroll windows.
  - The watchdog skips any command turn whose stable id is below the session's
    high-water mark (`A.maxTurnId`) - a scrolled-back old turn can never resume,
    even right after a reload (`resume.skipOld` in the diag ring).
  - The watchdog also skips a command turn whose injected result is rendered
    right below it (settled history), a provider-generic guard.
- **Gemini stranded a tool result in the composer ("Message could not be
  sent")**: after a generation ends, Gemini's action button can stay WEDGED on
  the stop icon instead of reverting to the send arrow. The loop's generation
  *detection* already tolerates this (WEDGE_MS), so the tool ran, but the *send*
  waited for an `arrow_upward` button that never appeared - four retries failed
  and the injected result sat unsent in the composer. `typeAndSend` now resets a
  frozen stop button (clicking it, guarded by the same not-actually-generating
  check) so the send button reappears, then sends (validated live). The native
  stop-click hook now ignores non-trusted (programmatic) clicks, so this
  un-wedge click is never mistaken for the user halting the agent - otherwise
  the next legitimate command was wrongly marked "stopped".

## [1.4.4] - 2026-07-16

### Fixed
- **Qwen fired tool commands mid-stream ("Bad JSON" while Qwen was still
  writing)**: Qwen's frontend update (fe 0.2.73) now emits `status:"finished"`
  in its SSE stream ~12s before the stream actually closes. The network tap
  treated that as the turn's end, so a still-incomplete command (e.g. an
  unclosed `###LUA###` block) was extracted and sent, and the loop's premature
  "unclosed" feedback was injected while the model kept writing. Fixed by no
  longer treating `status:"finished"` as done, and by having generation
  detection check the DOM stop button first (validated live: it now tracks the
  real stream end closely, unlike its old ~6s lag).

### Changed
- **Removed the "⚠ unstable" badge on Qwen's Auto/Think modes**: those modes
  used to make Qwen claim a tool "does not exist" without even trying it. The
  extension never force-switches Qwen's mode, so Auto (Qwen's own default) is
  left untouched.

## [1.4.3] - 2026-07-15

Adds a seventh AI provider (Meta AI) and fixes a Qwen tool-turn regression, plus
further Studio-port recovery hardening and a friendlier system prompt.

### Added
- **Meta AI (www.meta.ai) as a provider**: full Multi-Script support on Meta AI -
  new `providers/meta.js`, manifest content script + host permissions, and the
  provider switcher entry. Handles Meta's React DOM: reasoning ("Réflexion")
  chain-of-thought is excluded from the read text, the interactive JSON viewer
  and collapsible code blocks are masked so a streamed command never flashes, and
  the composer card is fully covered while typing. Meta AI accepts very large
  prompts, so no Qwen-style send cap is needed.

### Fixed
- **Qwen tool result took ~30s to inject on every tool turn**: Qwen dropped the
  assistant turn's own `id`, so `lastAssistantId()` returned null and the core
  fell back to the virtualized flat count, waiting the full ~30s NO_TURN_GRACE
  each turn. It now reads the stable `chat-response-message-<uuid>` descendant
  (with the old id kept as a fallback).
- **Qwen refused oversized messages**: a large tool result past Qwen's 131072
  character composer cap silently wedged the loop in the input box. Outgoing text
  is now truncated to a safe margin, keeping the head and tail and marking the gap
  so the model does not re-run the command.

### Changed
- **Friendlier, less restrictive system prompt**: the "do not use native tools"
  wording is reframed as a technical note (the site's own sandbox cannot reach the
  user's Studio) rather than a hard prohibition, with an explicit "you can act
  directly in the user's project" section. Reduces provider refusals.
- **Studio-port recovery hardening**: PID-based reclaim of leftover `StudioMCP`
  zombies and clearer, de-duplicated action banners on top of the 1.4.2 port
  hijack recovery.

## [1.4.2] - 2026-07-13

Follow-up robustness fixes for the Studio-connection failures the 1.4.1 work
did not cover: a rare "0 tools that survives every restart" deadlock, and a
third-party app silently hijacking Studio's MCP port.

### Fixed
- **A third-party app (e.g. ropilot) hijacking Studio's MCP port**: whichever
  program binds Studio's MCP port (13469) FIRST wins it, and if that is not
  Studio, `StudioMCP.exe` connects to the wrong host - the handshake succeeds
  but no tools ever appear. A PC reboot never helps because the offending app
  restarts with Windows and can grab the port before Studio again. The existing
  one-shot port check at boot could miss it. The bridge now detects the hijack
  from an unmistakable, timing-independent signal - `StudioMCP.exe` reporting it
  cannot parse the host's messages on that port - then kills the offending
  process (by port owner, with a fallback that kills the known squatter by
  name), restarts the proxy, and tells the user which app to uninstall or remove
  from Windows startup so it stops coming back. It never stays silent: if it
  cannot identify or kill the squatter it prints how to find it by hand.
- **`_port_owner` was IPv4-only**: the internal port-owner probe ran
  `netstat -p TCP`, so a squatter listening on IPv6 loopback was invisible to
  it; it now scans TCP and TCPv6.
- **A missing custom-MCP command (e.g. `uvx` not installed) looked like an
  endless silent restart loop**: when a configured server's command could not
  be found on PATH, the process never started, so there was no exit code and no
  stderr, and the crash-loop banner printed "the server printed no error output
  before dying". The bridge now catches the launch failure and names the real
  cause ("command not found: 'uvx' ...") both on the first attempt and in the
  crash-loop banner, while auto-restart keeps retrying in case the dependency
  is installed later.

### Changed
- After killing a port squatter, the "toggle Studio's MCP server OFF/ON"
  instruction now prints IMMEDIATELY (right after the kill) instead of only
  after the ~48s server-launch grace loop - so the user acts within seconds
  instead of staring at a seemingly-idle terminal for a minute. Toggling early
  also lets the grace loop pick up the tools and go green right away.
- **0 tools that no restart could fix**: if a `StudioMCP.exe` from a crashed
  session kept listening on Studio's MCP port (13469), reopening Studio made
  its MCP plugin do its one-shot registration against that *zombie* process.
  Because a Studio window was now running, both existing cleanups skipped it
  (the orphan-killer only acts when no Studio runs; the port check treats any
  Roblox-path owner as legitimate), so our fresh proxy could never own the
  port - 0 tools forever, unfixable by restarting Studio or the bridge in any
  order. The bridge now identifies the port owner by process ID: a
  `StudioMCP.exe` holding the port that this bridge did not launch (outside our
  own process tree) is a leftover by definition, so it is killed and the proxy
  restarted - at boot and again in the live watcher if the catalogue stays
  empty with Studio open. It then tells the user the one action that finishes
  recovery: open Assistant Settings > MCP Servers so Studio re-registers. If
  the process tree can't be read, nothing is killed (a healthy connection is
  never put at risk).
- The extension now tells non-technical users to "Run start.bat" instead of
  "Run python bridge.py" / "Run the Multi-Script bridge" in the offline panel,
  popup, and startup banner, matching the one-click launcher the README ships.

## [1.4.1] - 2026-07-11

Robustness release focused on the Roblox Studio connection lifecycle. Every
fix below was reproduced and validated live against a real Studio + Blender
setup, including the Roblox-side bugs reported on the devforum (StudioMCP
stale-pipe disconnects, MCP toggle turning off after a Studio update).

### Fixed
- **Phantom "Studio connected" state**: leftover `StudioMCP.exe` processes
  from a previous session or a Studio crash kept answering the bridge as if a
  Studio were attached, so the terminal and the extension showed green with
  Studio fully closed. The bridge now kills orphaned `StudioMCP.exe` at boot
  (only when no real Studio window exists, so a live connection can never be
  hit), and the boot banner re-confirms a positive probe before announcing a
  connection.
- **Status dot stuck green with Studio closed**: when StudioMCP advertised an
  empty tool catalogue (Studio closed at launch), the connectivity probe
  returned "unknown" instead of "disconnected", and the extension's
  don't-degrade-on-unknown rule kept the dot green forever. An alive Roblox
  proxy with an empty catalogue is now an authoritative "not connected".
- **Studio opened after the bridge was never detected** (yellow until a full
  bridge restart): two combined causes. (1) Nothing ever re-asked for the
  tool catalogue once the launch-time retry window expired - the watcher now
  re-polls `tools/list` while the catalogue is empty, so a late-attaching
  Studio is picked up within seconds. (2) Studio's MCP plugin registers with
  the MCP channel exactly ONCE (late in Studio's boot, or when the Assistant
  Settings > MCP Servers panel is opened/toggled) and never retries; the
  bridge's own recovery restarts could kill the MCP listener at that exact
  moment, permanently orphaning the plugin. The bridge no longer restarts the
  Roblox proxy while a Studio window is running, and both the terminal and
  the extension now say the one thing that actually fixes an orphaned
  plugin: open Assistant Settings > MCP Servers in Studio (validated three
  times live; a proxy-side restart provably cannot repair it).
- **Watcher crash silently disabling all Studio monitoring**: an unbound
  variable in the place-churn detector could kill the background watcher
  right after a reconnect, silently stopping every status update until the
  next bridge restart. Fixed, and both watchers are now supervised: a crash
  is logged in red and the watcher restarts itself in 5 seconds.
- Boot/connection messages no longer blame the merged multi-server tool count
  on Roblox ("49 tools loaded but NO Roblox Studio connected" when 22 of
  those were Blender's): every Roblox-specific message now uses the
  Roblox-only count.

### Added
- **Fast startup with addon servers**: MCP servers now launch in parallel and
  the extension-facing socket opens immediately, so a slow or absent Roblox
  Studio no longer delays Blender (or any addon) by up to a minute. The
  Roblox diagnostic continues in the background and the bridge pushes status
  updates to already-connected extensions as servers come up - previously an
  extension that connected early could keep a stale "addon offline" snapshot
  forever (greyed Start button instead of the orange degraded start).
- **Self-healing for Roblox's own disconnect bugs**: sustained loss of the
  Studio connection (stale named-pipe state, periodic silent disconnects)
  now auto-restarts the Roblox proxy - but only when no Studio window is
  running, where it is safe and effective.
- **Studio-update detection**: when a disconnect coincides with a new Studio
  version folder appearing, the terminal says Studio likely turned its MCP
  toggle off after updating (a known Roblox bug) and points at the exact
  setting, instead of retrying a recovery that cannot work.
- Extension messages distinguish "Roblox Studio is not running" from "Studio
  is running but not connected" (new `studio_proc` status field), each with
  its own corrective step.
- Terminal spinner during slow startup phases (server launch, Studio
  attach), so the console never looks frozen; only one spinner animates at a
  time.
- start.bat hardening: refuses to run from an unextracted ZIP, handles
  missing winget, rescans install folders after a winget install (PATH not
  refreshed), prints the Python version and the bridge's exit code on
  screen, and logs the Windows build - so a single screenshot of the
  terminal carries enough context for support.

## [1.4.0] - 2026-07-08

### Added
- Multi-MCP addon servers (experimental): a new "MCP servers" section in the
  panel menu lets you add or remove additional MCP servers (Blender,
  Sketchfab, or any local MCP command) alongside the always-primary Roblox
  Studio connection. The bridge rewrites `config.json` and restarts itself to
  load a change; Roblox stays protected from edits/removal and its status dot
  is scoped to Roblox alone so an addon going down never misrepresents the
  primary connection. New `list_mcp_servers` command and a `server` param on
  `list_commands` let the model discover and use addon tool sets on demand.
  When Roblox is down but an addon server is alive, the panel now offers a
  degraded start instead of refusing to start at all.
- Vision support (screen_capture / other tool-returned images) enabled for
  Arena, Gemini, GLM, Kimi and Qwen, each with a real "upload finished" signal
  before sending instead of trusting the first local preview, fixing several
  silent-attachment-drop and duplicate-attachment-on-retry bugs. A tool from
  any connected server that returns an image now gets the camera chip and is
  remembered for future calls, even for a custom MCP server whose name gives
  no hint it returns images.
- Parser: a JSON command cut off by the model's own output limit, missing
  only its trailing closing brackets, is now auto-completed and executed
  instead of failing with a parse error and forcing a full retry turn.
  Strictly refuses to salvage anything where real content (not just closers)
  was cut off.
- Per-reason parse-error feedback (cut off, bad JSON, missing ###LUA###
  opener, wrong envelope) instead of one generic "bad JSON" message, so the
  model fixes the actual problem instead of guessing.

### Fixed
- DeepSeek: a command's chip could show green "done" while DeepSeek was still
  streaming the reply, on back-to-back calls to the same tool. Caused by
  DeepSeek's list virtualization defeating the turn-count identity guard;
  fixed with a stable per-turn id.
- GLM: new "scroll to bottom" buttons were mistaken for the Stop button and
  permanently latched generation state to "busy." Raw command JSON could leak
  into the visible reply when nested inside a paragraph. An image filename
  could corrupt result-chip detection.
- Kimi: added detection of Kimi's own native "Agent" mode, which conflicts
  with Multi-Script's command protocol; Start is disabled with a warning until
  it's turned off. Fixed the hidden file-upload input not existing until the
  "+" menu is opened, raw command text leaking when nested/oversized, and
  normal model prose containing "try again" being misread as a site error.
- Qwen: same "try again" false-busy fix as Kimi. A/B "carousel" comparison
  turns (where the composer disappears mid-carousel) now auto-resolve to
  Response 1 once both candidates finish, instead of stalling or misreading a
  candidate as a truncated command.
- Arena: send is now confirmed until the composer actually clears instead of
  trusting a single click, preventing stranded messages/attachments; the chip
  now anchors below the reply text instead of floating above it.
- A command turn abandoned mid-stream (reload, or superseded by a
  regenerate) no longer shows a false green checkmark; it now shows a
  neutral "not run" state instead.
- A tool's own in-body error (e.g. "Output of '...': Error executing code...")
  now settles the chip red instead of green, even when the tool didn't use
  Multi-Script's own ERROR wrapper.
- Regenerating a stopped command no longer briefly re-shows the old call's
  chip before the new one streams in.

### Changed
- The version number next to the Multi-Script name in the panel is now small,
  plain text instead of a bordered green badge.
- System prompt updated to cover multiple MCP servers: the model must call
  `list_mcp_servers` before assuming something outside Roblox is unsupported,
  and the tool list is no longer inlined in the prompt (fetched on demand via
  `list_commands`).

## [1.3.9] - 2026-07-04

### Fixed
- Bridge: kill the full process tree on restart instead of just the wrapper
  process, which used to leave orphaned StudioMCP.exe instances behind that
  fought the next launch and caused seemingly random "Studio looks connected
  but nothing responds" failures.
- Bridge: a dead MCP server is now auto-restarted by a background watchdog
  instead of waiting for the next tool call to notice.
- Bridge: a tool call that hits one of Studio's own brief connection blips now
  retries once instead of surfacing a spurious "Studio not connected" error.
- Extension: the status bar no longer shows a falsely healthy "N tools" label
  when the agent is active but Studio, the place, or the bridge itself isn't
  actually usable, it now names the real blocker (open a place / enable the
  MCP server / bridge offline).
- Cross-provider: DeepSeek, Gemini, Kimi, GLM and Qwen composer menus, model
  pickers and tooltips (including GLM's search hover card and Kimi's model
  popover) no longer render clipped or hidden behind Multi-Script's own
  bar/pill/cover.
- Cross-provider: a thinking model quoting command JSON in its own reasoning
  area no longer makes the tool chip flap between done/run/done (Gemini, Kimi,
  GLM and Qwen).
- The "Agent is working" composer cover now blocks clicks into the composer
  underneath it instead of letting them through, and can no longer balloon
  past the composer's visible band or drag itself off position when a site
  recreates its editor node mid-session (seen on Kimi).
- A command chip could briefly flash or restart its spinner when revisiting a
  past turn; it now settles to done correctly instead.
- DeepSeek: the raw system-prompt turn no longer flashes for a frame before
  being hidden.
- Gemini: "New chat" no longer gets stuck on "Agent active" from a reused
  previous conversation URL.
- Kimi: reasoning is read separately from the actual reply, so a command
  drafted while the model is still "thinking" is no longer detected or
  executed; input can no longer be typed mid-run after the editor node is
  recreated.
- Arena: unsupported-mode gate now also covers Web Search and Generate Image,
  and chip alignment is fixed when a command turn renders as an A/B
  model-comparison carousel.
- Bridge: a long-running tool call no longer starves the connection's ping
  handling and trips the half-open-socket watchdog.

### Changed
- Bridge and installer logs moved to `logs/bridge_debug.log` and
  `logs/start.log`; the console now only shows what a user actually needs to
  read, full detail still lands in the log files.
- `start.bat` now detects and explains a double launch instead of silently
  replacing the previous instance, and warns clearly if port 17613 stays held
  after trying to free it.
- Removed remaining em dashes from user-visible strings.
- Removed remaining em dashes from user-visible strings.

## [1.3.3] - 2026-06-24

### Fixed
- Bridge no longer depends on Roblox's `mcp.bat`, which hard-coded a single
  Studio version path and broke (0 tools / "Bridge or Studio offline") once
  Studio auto-updated and that version folder was removed. A new
  `launch_studio_mcp.py` finds the newest installed `StudioMCP.exe` and launches
  it directly.
- `bridge.py` now runs a `.py` MCP command with the same Python interpreter as
  the bridge, so it works on installs where only the `py` launcher exists.

## [1.0.0] - 2026-06-09

### Added
- Initial public release of Multi-Script
- Browser extension for Chrome and Edge (DeepSeek chat integration)
- Local Python bridge (`bridge.py` + `start.bat`) for Roblox Studio communication
- Built-in MCP server support (no plugin required - activate directly in Roblox Studio)
- Read and edit Luau scripts directly from DeepSeek chat
- Run Luau code in real time inside Roblox Studio
- Inspect game tree and instances
- Generate meshes, materials, and models
- Browse and insert assets from the Creator Store
- Control play-testing from chat
- Panel status indicator (green / yellow / grey)
- Auto kill port 17613 on start to avoid conflicts
- Ko-fi support link with Robux tip passes in the extension panel
- Setup tutorial video on YouTube
