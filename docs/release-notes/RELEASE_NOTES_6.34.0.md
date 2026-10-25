# Multi-Script 6.34.0 — living environment themes

- Scream, Michael Myers, Slenderman and Jason Voorhees are now animated environments drawn behind the menu, in the same style as Fazbear's Pizzeria: the Woodsboro farmhouse at night, Haddonfield's Lampkin Lane at dusk, the Slender woods with a flashlight that follows the mouse, and Camp Crystal Lake with cabins, dock and mist.
- New shared scene engine (`core/scenes.js` + `core/scenes.css`), also used by Multi-Script IDE 5.2. All drawing is code-only SVG/CSS, with no network assets; all selectors are scoped to `.ms-scene`; and it respects `prefers-reduced-motion`.
- The Fazbear's Pizzeria layer is unchanged.
- Verified headlessly: all 25 themes are applied in Chromium against a mock provider page with 0 page errors, and the scene mounts into `#zs-menu` for the four Halloween themes.
