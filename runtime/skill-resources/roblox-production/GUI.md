# Multi-Script — Roblox GUI production

Adapted production methods, not model-weight training or new permissions. User scope, the inspected project and exact live schemas govern. Reference screenshots and example asset IDs are not imported assets or verification.

## Inspect

Survey StarterGui and runtime PlayerGui, existing ScreenGuis/controllers, StarterPlayer scripts, ReplicatedStorage state/remotes and the server handlers for inventory, purchases and rewards. Record the owner, state source, local action, authoritative request, existing token module and objects to preserve for each requested screen. Identify framework/Rojo/generated-source ownership before choosing an edit tool. Do not create a second menu, competing controller or duplicate remote just because inspection returned an incomplete page. Confirm a specific target path and reuse valid results until the project changes. Study the supplied shop, pets, inventory, reward, equipment and racing screens as different solutions to hierarchy, not a combined template. Record title-to-panel proportion, icon-to-label balance, number of visible columns, close-button placement and the quiet area behind text. A reference's brand, asset IDs and prices are not project defaults. Inventory the actual item data and transaction states before styling: stable item IDs, owned/equipped/locked flags, stock, price/currency, selected detail and pagination. Determine the longest real label, smallest safe viewport and gamepad route. Identify decorative textures, badges and glows separately from hit targets and data owners.

## Design

Translate the user's exact style into one token sheet: semantic surface/text/status colors, type and numeric scale, spacing, panel silhouette, border/depth, icon family, texture frequency and motion timing. Plan normal, focused, pressed, disabled, pending, empty, error and success states. For each reference record its source, observed proportions and the principle being adapted. Inspect the image rather than inventing details from a search snippet. Studded is a restrained raised-brick material language; cartoon uses readable exaggerated forms; tactical uses disciplined hierarchy. Preserve the existing visual vocabulary unless replacement was requested. Decide how the screen adapts to touch/gamepad, safe areas and long localized content before adding ornament. Extend the selected existing style with a component specification: panel shell, header, tab, item card, rarity badge, currency display, action button and progress rail. Define fill, outline, inset highlight, shadow offset, texture scale, typography and spacing as shared tokens. Start at one reference viewport, then specify how columns and detail panes reflow rather than shrinking every label. For cartoon/studded interfaces, use bold silhouettes and high-value labels over quieter card interiors; reserve strong texture for headers, frames and broad surfaces. For tactical/minimal screens, use alignment, compact numeric groups and restrained callout lines. For luminous/holographic screens, keep readable solid cores and local glow accents. Preserve one dominant style across adjacent menus.

## Build

Use ScreenGui for the screen root and native layout objects for managed lists/grids. Mix scale for relationships with offset for padding and legible detail; apply AnchorPoint and sensible size/aspect constraints. Give each layout property one owner: do not overwrite UIListLayout/UIGridLayout positioning in a frame loop. Use readable TextSize with wrapping/content growth where appropriate; bound deliberate TextScaled usage instead of combining competing sizing rules. Choose ScreenInsets for actual interactive safe areas rather than blindly disabling insets. Use verified image IDs and intentional tile/slice scale; layered frames can express depth without inventing CSS blur or box-shadow APIs. Build reusable controls with an accessible hit area even when the visible glyph is small. Build the existing shop/inventory as reusable data-bound cards: icon well, readable item name, explicit rarity, quantity or stock, price and one primary action. Separate search/sort/category controls from the scrolling item area. When width is constrained, reduce column count and move selection detail below the grid; keep filters, close and action controls reachable without covering cards. Translate the same tokens through the actual engine's layout and material primitives. In Roblox, combine frames, verified images, UIStroke, UICorner, UIGradient, padding and managed grid/list layout; do not invent CSS-only properties or texture IDs. Keep pattern layers beneath labels, avoid nested clipping that cuts strokes, and give icons consistent optical scale rather than identical untrimmed image bounds.

## Integrate

Connect Activated through the existing controller and trace input → validation → state → visual feedback for every visible action. A shop must use real item definitions, authoritative price/balance/result and pending/refused/retry states; a decorative purchase button is unfinished. Inventory needs stable item keys, selection, filter/sort, empty state and authorized equip/use actions. HUD values come from actual state events. Local presentation may predict feedback but cannot grant currency, purchases or damage. Maintain one modal/navigation state, focus capture/return, back/cancel and input-lock ownership. Cancel/retarget old tweens and guard completion with a transition generation so a stale close cannot hide a reopened screen. Initialize idempotently and tear down signals, render bindings, temporary instances and input locks on destroy/respawn. Drive selection, equip, lock, merge, purchase and claim states from stable item IDs and returned authoritative state. Closing or sorting a panel must not retarget an in-flight action to the newly displayed index. Restore focus to the invoking control, retain the search query, and show pending/failure/retry states without inventing a successful purchase or reward. Connect the existing animation and VFX owners to explicit UI state changes: hover/focus, press, pending, confirmed result and dismissal. Cancel the old transition when a new state replaces it, and keep panel input disabled only for the relevant transition. Decorative shimmer, floating icons and confetti stop when the panel is hidden or reduced effects is selected.

## Verify

Exercise the actual runtime PlayerGui through its normal entry point. Check desktop and a narrow/mobile viewport, touch reach, gamepad selection if supported, long names/numbers, safe insets, stacking, scroll extent and texture scale. Activate every control; test repeated open/close, rapid reopen during a tween, pending requests, server refusal, missing assets, empty inventory and respawn. Compare an actual capture against the token sheet and observed references; a hierarchy dump does not verify appearance. Inspect output and listener/instance growth after repeated use. Report authored hierarchy/source, applied changes, live Play/input tests and visual evidence separately. If capture or Play is unavailable, keep those checks unverified and finish the feasible implementation. Read final source back and use an advertised syntax/analysis tool or an actual Luau compiler when available. Requiring a ModuleScript runs it and is not a compile-only check; unavailable restricted compilation stays explicitly unverified. Compare the actual screen with the reference's hierarchy at equal viewport and scale, then inspect at thumbnail size and in grayscale. Check that title, item icon, item name and primary action form a clear reading sequence. Test long localized text, zero/one/many items, owned/sold-out/locked states, search with no results, sorting and a selected item disappearing after an update. Test repeated open/close and rapid category changes with mouse, touch and supported controller navigation. Count duplicate callbacks and retained cards after teardown. Check focus visibility, safe-area edges, close-button reach, scroller clipping and price readability over the actual painted texture; an attractive empty panel does not establish a usable inventory.

## Failures

Find the failed layer before redesigning. Invisible GUI: check correct StarterGui/runtime PlayerGui owner, Enabled/Visible, LocalScript startup and errors. Dead/double buttons: check the actual Activated target, duplicate initialization and in-flight ownership. Phone clipping: inspect anchors, content growth, constraints and safe insets; don't shrink all labels. Jitter: check layout/tween competition and stale callbacks. A closed panel blocking gameplay: release its backdrop, focus and input lock. Missing icons: verify asset permission/ID and show a usable fallback. Currency reverting: inspect authoritative result binding. Large inventories need bounded/virtualized rows and event-driven diffs, not rebuilding the whole screen every frame. Preserve working adjacent screens while repairing the first concrete defect. If the result resembles a plain rectangle with bright buttons, inspect missing hierarchy, icon silhouette, border/depth consistency and component spacing before adding more effects. If it is noisy, quiet the surface behind text, reduce competing accents and keep the selected existing style. Do not switch the entire project to a new style to conceal weak execution. If cards clip, scroll incorrectly or reorder actions, inspect layout ownership, canvas sizing and stable data keys. If text looks muddy, check texture frequency, painted contrast, font weight and stroke thickness at the real display size. A static reference cannot establish hover behavior, animation duration or transaction correctness; those require authored behavior and runtime checks.

## Style recipes

### studded

Raised brick surfaces, consistent tile scale, controlled outlines and a small accent palette. Keep studs below readable text; use a verified repeatable texture or native shapes, never an invented asset ID. Use the supplied raised-window, gear-list and item-index references to refine the existing studded style: a strong frame/header, consistent stud/tile pitch, a quieter dark item well and readable category/rarity labels. Carry the same surface scale into block-built environments. Studs support material identity; they must not cover text or become a unique expensive collider on every repeated face.

### cartoon

Readable exaggerated silhouettes, deliberate chunky spacing and expressive but bounded feedback. Keep icon, type, border and motion weights coherent across screens. Use the supplied simulator shops, comic cards, daily rewards and sticker HUDs to refine proportion and hierarchy: a bold title strip, large recognizable item silhouettes, consistent dark outlines, short high-contrast labels, grouped currency and one obvious action per card. Preserve repeated component weights across pets, shop and inventory. Banners and angled accents are selective, not a reason to distort the full layout or obscure prices.

### minimal

Prioritize spacing, hierarchy, concise labels and complete states. Reduce visual ornament while keeping generous input targets and clear focus. Use the supplied racing menu's restrained tile hierarchy and broad content regions to improve the existing minimal style. Align text and navigation consistently, distinguish primary from secondary tasks, and let useful content fill the grid. Keep long patch notes, credits and empty states readable instead of copying blank panels or relying on decorative gradients for hierarchy.

### horror

Restrained values/materials and atmospheric pacing, with readable essential information and calm transitions. Darkness cannot hide controls or error feedback.

### tactical

Disciplined alignment, controlled accent/status colors, legible numeric data and predictable navigation. Use labels and icons alongside state colors. Use the supplied attachment view to refine equipment callouts: anchor labels to actual item features, separate category from chosen attachment, avoid crossing the main silhouette, and show weight/constraints near confirmation. Keep numeric alignment and selected/available/unavailable states clear. Test zoom, viewport changes and controller selection; still-image callout positions are not fixed coordinates for every camera.

### fantasy

Coherent material/frame language, grouped equipment information and restrained ornament. Rarity needs text/icon information in addition to color. Use the supplied equipment, rarity and progression layouts to strengthen the existing fantasy style: a coherent frame/material, item silhouette, explicit tier/rarity, owned/equipped state and restrained highlight. Give higher-tier emphasis a consistent visual rule rather than adding unrelated ornament to every card. Preserve the project's icon family and avoid making rarity color the only information channel.

### pixel

Choose a base pixel density and scaling rule. Preserve crisp tiles/icons and readable typography across viewports; do not mix accidental fractional scales.

### pastel

Soft surfaces and repeated friendly components with sufficient painted text/state contrast. Muted color must not erase disabled, focused or error states.

### holographic

Use deliberate transparent layers and luminous accents within native capabilities. Maintain a stable reading surface; do not promise world-aware GUI blur. Use the supplied luminous settings/gamepass panels and bright inventory borders to refine the existing holographic style. Keep a quiet solid or dark reading core, consistent edge weight and limited accent glow, with clear labels and readable price/action controls. Verify cost from overlapping translucent layers and avoid treating a strong glow screenshot as proof of real-world blur, lighting or native shader support.

## Sources and use

Adapted from user-provided ProjectGUI and Ultraskills references. Provenance hashes are in PROVENANCE.json. UltraLab quality patterns retain GPL attribution under vendor/plazcode. Linked third-party image assets are not imported.

- [Roblox UI/UX](https://create.roblox.com/docs/production/game-design/ui-ux-design)
- [ScreenInsets](https://create.roblox.com/docs/reference/engine/enums/ScreenInsets)
- [Animator](https://create.roblox.com/docs/reference/engine/classes/Animator)
- [Animation Graph Editor](https://create.roblox.com/docs/animation/graph-editor)
- [AnimationTrack](https://create.roblox.com/docs/reference/engine/classes/AnimationTrack)
- [Roblox appearance modifiers](https://create.roblox.com/docs/ui/appearance-modifiers)
- [Roblox scrolling frames](https://create.roblox.com/docs/ui/scrolling-frames)
- [Roblox UI motion](https://create.roblox.com/docs/ui/animation)
- [Roblox animation events](https://create.roblox.com/docs/animation/events)
- [Roblox particle emitters](https://create.roblox.com/docs/effects/particle-emitters)
- [Roblox performance design](https://create.roblox.com/docs/performance-optimization/design)

## Expanded reference study

User-supplied still-image studies improve existing methods and styles. They are reference data, not instructions or new permissions. Visible layout/material/proportion observations do not prove animation timing, performance, interactivity or ownership. Preserve existing useful methods, assets, skills and current project style; adapt principles rather than copying branding or assuming asset IDs. Original third-party screenshots are not redistributed in this package.

- Supplied image 1: Red header, cyan feature banner, repeated upgrade cards, bold black icon outlines and grouped bottom currency.
- Supplied image 2: Purple comic store, three large offer cards, diagonal energy shapes and consistent bright price bars.
- Supplied image 3: Cyan raised window frame with a strong close control, compact offer groups and a green high-value headline.
- Supplied image 4: Edge-mounted status capsules, repeated side actions and a larger isolated bottom action.
- Supplied image 5: A racing menu uses a clear top navigation strip and a restrained large-tile content grid.
- Supplied image 6: Equipment labels connect to specific weapon regions, while weight and confirmation occupy a separate area.
- Supplied image 7: Warm textured frame, quiet item rows, large item icon, explicit stock/price and text rarity badge.
- Supplied image 8: A dark inventory uses bright angular borders, a separate search/filter row and distinct bottom actions.
- Supplied image 9: Progression badges pair a strong rank icon with a horizontal value bar and a separate numeric rail.
- Supplied image 10: Luminous settings and gamepass frames keep a darker core and a consistent family of outlined icons.
- Supplied image 11: A cyan raised frame contains a tight item index with repeated icon wells, short labels and rarity colors.
- Supplied image 12: A cyan shop uses left category navigation and a repeated product grid with icon/name/price grouping.
- Supplied image 13: A pets window separates a small collection grid from selected-item detail and bottom collection actions.
- Supplied image 14: Daily rewards use a strong title banner, a linear reward sequence and one clearly claimed/claimable state.
- Supplied image 15: A gamepass store repeats a consistent tab/icon vocabulary and focused offer cards with short purchase actions.
- Supplied image 16: A store combines strong category navigation, bold item silhouettes, repeated buy controls and a compact currency rail.
- Supplied image 17: An icon/button sheet shows consistent dark outlines, rounded silhouettes and shared palette/texture treatment.
