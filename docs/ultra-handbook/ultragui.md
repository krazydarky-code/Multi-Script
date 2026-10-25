# Interface architecture, interaction and visual craft

Detailed project-aware guidance, not weight training or permissions. Apply only relevant parts; preserve user scope, existing style and architecture. Inspect/review-only tasks remain read-only. Retrieve once, execute the authorized slice, reuse unchanged evidence and avoid guidance/discovery loops.

## Inspect

1. Trace the primary user journey from entry to successful action, including cancel, back, retry and return. List who owns each screen, its data and its navigation state before adding new UI.

2. Read actual component trees, tokens, fonts, icon families and layout rules. Measure the smallest supported viewport and available safe area; distinguish a compact visual glyph from the larger interactive target around it.

3. Make a state inventory for real content: empty, one item, many items, long names, overflow, loading, stale data, rejected actions, offline and permission loss. Record which states already exist and where the current implementation breaks.

4. Inspect event propagation, focus, pointer capture, scrolling, modals and gameplay input. Establish which layer consumes each action so decorative overlays cannot steal clicks or movement controls fire behind menus.

5. Check the actual design/runtime connection and edit permissions. Record whether you can author native controls, edit a Figma file, create an SVG mockup or only describe a handoff; these deliverables have different acceptance criteria.

6. Capture the existing screen and reproduce the reported interaction before restyling it. Separate spacing/hierarchy defects from missing data bindings, rendering problems and provider/bridge failures.

7. Study the supplied shop, pets, inventory, reward, equipment and racing screens as different solutions to hierarchy, not a combined template. Record title-to-panel proportion, icon-to-label balance, number of visible columns, close-button placement and the quiet area behind text. A reference's brand, asset IDs and prices are not project defaults.

8. Inventory the actual item data and transaction states before styling: stable item IDs, owned/equipped/locked flags, stock, price/currency, selected detail and pagination. Determine the longest real label, smallest safe viewport and gamepad route. Identify decorative textures, badges and glows separately from hit targets and data owners.

**Phase exit:** The actual journey, tree, data/input owners and supported viewport/state matrix are known.

## Design

1. Write a compact screen specification: user goal, primary action, visible information, secondary actions and recovery. Use progressive disclosure for secondary controls instead of adding a permanent button for every feature.

2. Define semantic tokens for surface, text, muted text, accent, danger, success, focus, spacing, radius and elevation. Reuse the project's type scale and icon family; reserve emphasis for decisions that need it.

3. Lay out the largest structural regions first, then content groups and individual controls. Specify min/max width, wrapping, intrinsic content size, scroll ownership and how the layout changes with actual content.

4. Define all interaction states before styling: default, hover where supported, focus, pressed, selected, disabled, pending, completed and failed. State must be visible without relying only on color or animation.

5. Specify navigation and modal focus behavior, Escape/back handling and focus restoration. Do not trap focus unless the surface is genuinely modal; preserve a user's draft while opening settings or changing a view.

6. Choose references by information density, camera/platform and interaction purpose. Extract a few concrete principles and translate them into the existing tokens; do not copy a screenshot's branding or invent reference evidence.

7. Extend the selected existing style with a component specification: panel shell, header, tab, item card, rarity badge, currency display, action button and progress rail. Define fill, outline, inset highlight, shadow offset, texture scale, typography and spacing as shared tokens. Start at one reference viewport, then specify how columns and detail panes reflow rather than shrinking every label.

8. For cartoon/studded interfaces, use bold silhouettes and high-value labels over quieter card interiors; reserve strong texture for headers, frames and broad surfaces. For tactical/minimal screens, use alignment, compact numeric groups and restrained callout lines. For luminous/holographic screens, keep readable solid cores and local glow accents. Preserve one dominant style across adjacent menus.

**Phase exit:** A coherent token/layout/state/focus specification exists for the requested screen.

## Build

1. Implement one complete reusable control family first, including label, icon, target area, focus and disabled/pending behavior. Verify it with real data before multiplying it into a full screen.

2. Use the target's native layout system and content sizing. Put animation inside a stable layout wrapper when the layout engine owns the outer transform, and keep decorative layers outside input hit testing.

3. Bind real data through existing view models/controllers. Use stable item identities when lists update so selection, focus, scroll position and drafts do not jump to another row.

4. Keep icon stroke/weight, baseline alignment, corner treatment and optical sizing consistent. Use actual bundled fonts and assets with fallbacks; inspect the resulting text rather than assuming a font loaded.

5. Implement pending and failure states on the same action path as success. Preserve entered data on failure, prevent duplicate consequential submissions and surface a useful retry state without a modal for every transient event.

6. Build tooltips and secondary panels so they fit the viewport and remain reachable without hover. Anchor them to the intended control, dismiss them predictably and avoid covering native provider menus.

7. Handle long localized text, missing thumbnails, unusually large numbers and empty results through layout rules. Do not patch each overflow with a smaller font or clipped label.

8. Keep the requested scope: a menu redesign should not silently replace networking, business logic or the whole design system. Preserve component APIs and document the smallest necessary migration.

9. Build the existing shop/inventory as reusable data-bound cards: icon well, readable item name, explicit rarity, quantity or stock, price and one primary action. Separate search/sort/category controls from the scrolling item area. When width is constrained, reduce column count and move selection detail below the grid; keep filters, close and action controls reachable without covering cards.

10. Translate the same tokens through the actual engine's layout and material primitives. In Roblox, combine frames, verified images, UIStroke, UICorner, UIGradient, padding and managed grid/list layout; do not invent CSS-only properties or texture IDs. Keep pattern layers beneath labels, avoid nested clipping that cuts strokes, and give icons consistent optical scale rather than identical untrimmed image bounds.

**Phase exit:** Reusable controls and required states exist with real content and bounded ownership.

## Integrate

1. Trace each visible control through handler, validation, state update and visible feedback. Remove placeholder click handlers and labels that imply functionality without a real action.

2. Separate optimistic presentation from committed server state for purchases, rewards and inventory. Reconcile rejected or late results without double-applying the action or losing a user's selection.

3. Integrate global shortcuts, keyboard/controller traversal and touch scrolling with the existing input owner. Test opening a menu during movement and returning control after dismissal.

4. Preserve draft text, selected items, scroll position and focus across panel refreshes and provider remounts. Cancel stale async responses when the screen or selected object changes.

5. Centralize owned subscriptions, animation handles and temporary overlays. Dispose them on close, scene unload or owner destruction so repeated opens do not create duplicate actions.

6. Keep an explicit handoff between design artifacts and native runtime controls. Verify imported scale, fonts, asset paths and behavior after the handoff instead of counting an exported SVG as playable UI.

7. Drive selection, equip, lock, merge, purchase and claim states from stable item IDs and returned authoritative state. Closing or sorting a panel must not retarget an in-flight action to the newly displayed index. Restore focus to the invoking control, retain the search query, and show pending/failure/retry states without inventing a successful purchase or reward.

8. Connect the existing animation and VFX owners to explicit UI state changes: hover/focus, press, pending, confirmed result and dismissal. Cancel the old transition when a new state replaces it, and keep panel input disabled only for the relevant transition. Decorative shimmer, floating icons and confetti stop when the panel is hidden or reduced effects is selected.

**Phase exit:** Each visible action reaches the intended handler/state and lifecycle cleanup is connected.

## Verify

1. Run the primary journey using real data and then keyboard only. Where supported, repeat with controller and touch; list devices or accessibility software you could not test.

2. Inspect actual captures at the narrowest supported width and representative desktop aspect ratios. Compare hierarchy, alignment, whitespace, clipping, target size and scroll ownership with the specification.

3. Exercise empty/loading/error/offline/permission-denied states and rapid repeated actions. Check that the UI preserves inputs, communicates pending work and recovers without duplicate commits.

4. Open, close and reopen modals while using Tab, Shift+Tab, Escape/back and nested menus. Confirm focus reaches the intended surface, stays visible and returns to a valid control after dismissal.

5. Test long text, text scaling, high content density, missing assets and reduced motion. Inspect painted contrast against actual backgrounds rather than only comparing token values.

6. Trigger provider layout changes, browser resize, scene reload or data refresh while the panel is open. Confirm docking, z-order and hit testing remain correct without covering native settings.

7. Compare the final artifact to one captured baseline and repair the most consequential mismatch first. Rerun changed states instead of repeatedly recapturing an unchanged whole screen.

8. Report separately which controls are authored, wired, visually inspected and exercised in the target runtime. A successful create-node call proves only that node creation returned.

9. Compare the actual screen with the reference's hierarchy at equal viewport and scale, then inspect at thumbnail size and in grayscale. Check that title, item icon, item name and primary action form a clear reading sequence. Test long localized text, zero/one/many items, owned/sold-out/locked states, search with no results, sorting and a selected item disappearing after an update.

10. Test repeated open/close and rapid category changes with mouse, touch and supported controller navigation. Count duplicate callbacks and retained cards after teardown. Check focus visibility, safe-area edges, close-button reach, scroller clipping and price readability over the actual painted texture; an attractive empty panel does not establish a usable inventory.

**Phase exit:** Real layouts and input/error/lifecycle paths satisfy the screen acceptance criteria.

## Failures

1. If a button looks correct but does nothing, inspect hit testing, event propagation, disabled state and handler ownership before changing its visual styling.

2. If a list jumps on updates, inspect unstable keys, recreated containers and focus/scroll restoration. Preserve item identity rather than adding arbitrary wait timers.

3. If text clips only at narrow sizes, measure intrinsic width, min-size rules, parent clipping and localization expansion. Fix the layout constraint instead of hiding the symptom with unreadably small text.

4. If animation moves the wrong element, identify whether layout owns its transform and animate an inner wrapper or supported property. Cancel superseded animations so old completion callbacks cannot restore stale state.

5. If a native provider menu is obscured, compare geometry and stacking contexts and yield the extension surface only while necessary. Do not globally raise every z-index or disable the provider's menu.

6. If the connection is read-only or assets cannot be imported, preserve an editable artifact and state the exact handoff boundary. Do not label a design preview as a deployed interface.

7. If the result resembles a plain rectangle with bright buttons, inspect missing hierarchy, icon silhouette, border/depth consistency and component spacing before adding more effects. If it is noisy, quiet the surface behind text, reduce competing accents and keep the selected existing style. Do not switch the entire project to a new style to conceal weak execution.

8. If cards clip, scroll incorrectly or reorder actions, inspect layout ownership, canvas sizing and stable data keys. If text looks muddy, check texture frequency, painted contrast, font weight and stroke thickness at the real display size. A static reference cannot establish hover behavior, animation duration or transaction correctness; those require authored behavior and runtime checks.

**Phase exit:** The supported cause is repaired or the exact access/import/device boundary is explicit.

## Engine application

### roblox

Inspect the actual PlayerGui/StarterGui ownership and client controller. Use native layouts, constraints and input/focus behavior; animate a child wrapper when a layout owns Position. Repeated open/respawn must not duplicate connections. Verify the actual rendered ScreenGui in Play at representative safe insets, not only Edit hierarchy creation.

Existing candidate skills: check-clean-ui, roblox-responsive-ui, roblox-native-ui-kit-screens. Load the smallest relevant set through the live skill tool.

### godot

Inspect the Control tree, Containers, size flags/minimum sizes, anchors, theme and focus neighbors. Containers own child layout; avoid competing direct positioning. Preserve mouse_filter/input ownership and scene teardown. Test keyboard/controller, long localization and actual viewport stretch rather than only the editor preview.

Existing candidate skills: godot-control-ui, godot-accessibility. Load the smallest relevant set through the live skill tool.

### unity

Inspect whether the project uses uGUI or UI Toolkit, its event/input system, scale and sorting model. Reuse that system rather than mixing a parallel framework accidentally. Bind/unbind callbacks with the owning view lifecycle and test actual navigation, clipping, text wrapping and Play/build behavior.

Existing candidate skills: unity-ui-toolkit, unity-ugui. Load the smallest relevant set through the live skill tool.

### blender

Treat Blender as an authoring/preview surface for UI assets unless a real target runtime or Figma connection is available. Preserve editable vector/texture/scene sources and specify target dimensions, alpha/color space and handoff. A plane with a UI render is not an interactive game screen.

Existing candidate skills: studio-practical-ui-ux, canvas-svg-ui. Load the smallest relevant set through the live skill tool.

### workspace

Use the actual application framework/design system and semantic controls. Trace event, state, data and focus ownership; preserve drafts across remounts. Test real browser/desktop views at supported sizes and inputs, using native dialogs and reduced-motion settings rather than treating an SVG preview as a wired application.

Existing candidate skills: ui-ux-production, general-component-states, general-responsive-design. Load the smallest relevant set through the live skill tool.

### figma

Read the actual editable file, component/variant system, variables, typography and Auto Layout. Plan hug/fill/fixed sizing and wrapping from real content. Verify prototype permissions and inspect the resulting native frames; exported SVG does not preserve all interactive runtime behavior.

Existing candidate skills: figma-auto-layout, figma-components, figma-prototyping. Load the smallest relevant set through the live skill tool.

## Acceptance evidence

- Every required action has a verified handler and visible result or an explicit blocked state.
- Primary content fits supported narrow and desktop viewports without accidental clipping or overlapping controls.
- Keyboard focus, close/back behavior and repeated opening work without losing drafts or duplicating handlers.
- Loading, empty, failure and disabled states preserve useful context and do not imply an uncommitted action succeeded.
- Style tokens, icon treatment, typography and motion agree with adjacent screens.
- Evidence identifies the actual rendered artifact, viewport, state and input path tested.

## Diagnosis

### Invisible control

Probe: Inspect ancestor clipping, alpha, bounds and stacking context.

Repair: Correct the owning layout/state property.

Recheck: Capture the same viewport and activate the control.

### Double purchase

Probe: Trace repeated handlers and request identities.

Repair: Keep one owner and reconcile committed state.

Recheck: Exercise rapid repeats and a delayed rejection.

### Lost draft

Probe: Compare remount keys and editor ownership.

Repair: Preserve draft state across the remount boundary.

Recheck: Type, open settings, resize and return.

### Stuck focus

Probe: Inspect modal state and traversal targets.

Repair: Restore valid focus and correct modal semantics.

Recheck: Traverse forward/back, dismiss and reopen.

## Deliverables

- Native component/view files and reusable token definitions.
- State/action map showing real data and consequential action ownership.
- Representative captures and interaction results with viewport/input context.
- Known import, service or device boundaries with a usable handoff.

## Source guidance

- [Roblox UI animation](https://create.roblox.com/docs/ui/animation): Reviewed official indexed guidance; adapt to the existing native layout.
- [Figma Auto Layout](https://help.figma.com/hc/en-us/articles/360040451373-Guide-to-auto-layout-in-Figma): Reviewed official help; actual edit/prototype capabilities depend on the connection.
- [Unity 6 UI Toolkit callbacks](https://docs.unity3d.com/6000.0/Documentation/Manual/UIE-Events-Handling.html): Reviewed official Unity 6.0 page; not a promise for every Unity version.
- [W3C APG modal dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/): Reviewed interaction guidance; it does not certify runtime accessibility.

## Expanded supplied-reference study

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
