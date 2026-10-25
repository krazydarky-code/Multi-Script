# Multi-Script 6.42.1 Dev verification

All **16 targeted suites passed**, with no environment skips in this run. This
release changes theme presentation, release versions and packaging policy. The
full 160-suite baseline from 6.42.0 remains historical evidence; it was not
relabelled as a new complete run. [Machine-readable results](verification-results-6.42.1.json).

## New theme coverage

- Cobalt, Porcelain, Ember, Tidal, Starlight and Daybreak: **324**
  browser appearance cases across independent menu/bar combinations, Auto/Window
  docks, simulated composer portals, 390px phone layouts and both Notion/Claude
  content-script fixtures. Theme choices persist through fresh initialization.
- **18762** computed text/control contrast checks, with translucent
  backgrounds composited through ancestor surfaces; CSS `color(srgb ...)` is
  normalized correctly. Checked text/control cases meet 4.5:1.
- **228** actual compositor-pixel contrast checks sample beneath
  temporarily hidden chatbar text/icons, retaining real scenes and pseudo-element
  overlays. These catch painted layers that a CSS-color-only check misses.
- **42** live-scene checks cover full/reduced/no motion, OS reduced
  motion, both menu and bar scene mounts, and scene cleanup when switching themes.
- The complete settings sweep exercises 496 controls, all 31 themes at small and
  studio sizes/scales across all tabs, bar options, resets, invalid stored values
  and narrow viewports. [Settings log](verification-6.42.1/test_settings_sweep.js.txt).
- Existing Fazbear scene behavior, chatbar layout, content-script initialization,
  portable preferences, Ultra/demotion, forced colors and workspace features pass
  targeted regression checks. Version-consistency checks cover bridge, product,
  adapter, generated asset manifest and companion plugin.

## Corrected issues

New palettes now supply their muted text ramp with enough specificity to override
the generic light theme. Setting headings, labels, helper text, placeholders and
light-theme health badges use readable colors. Daybreak no longer inherits dark
live-menu panels or the dark chatbar scrim. Reading surfaces stay translucent so
the scene is visible. Independent chatbar status/actions follow the bar's palette
even under a different menu or outside the extension root. Ultra's animated text
gradient follows the bar's own lightness. The menu's lower outer shadow is clipped
before the chatbar, preserving the original control stacking and click behavior.

## Release policy and archives

Dev **6.42.1** is the current primary build. Public **6.42.0** is a frozen older
companion. [Release policy](RELEASE_POLICY.md) and `release-policy.json` make this
persistent: the builder generates Dev only, requires Dev to be newer, checks the
Public version/edition/checksum/stable identity and bundles Public unchanged.

Real temporary-archive tests cover deterministic builds, nested bundle bytes,
sanitized configuration, excluded private/generated data and rejection of missing,
changed, equal/newer-version, wrong-edition, wrong-identity or conflicting Public
archives. Final ZIP CRC/SHA/source comparisons are performed after packaging and
recorded in the delivered release manifest and package-check report.

## Evidence and limits

Desktop and mobile screenshots for each new theme are in
`docs/verification-6.42.1/`. For example: [Daybreak desktop](verification-6.42.1/daybreak-desktop.png),
[Tidal desktop](verification-6.42.1/tidal-desktop.png), [Daybreak mobile](verification-6.42.1/daybreak-mobile.png).
The browser checks use real extension code and deterministic local provider DOM
fixtures in headless Chrome; composer-portal cases explicitly move the bar for
style verification. This run does not certify all authenticated provider layouts,
paid models, other operating systems or native editor playtests. Previous live
provider observations remain in [provider QA](PROVIDER_QA_6.41.md). No claim of zero
bugs or new all-provider live coverage is made.
