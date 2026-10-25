/* 6.18.0 — theme picker legibility regression.
 *
 * History: the 6.17.6 monochrome layer added a late `.zs-theme-opt` grouped
 * rule that set `color: var(--mono-ink-4)` (#6a6a78). Because it came AFTER
 * the original appearance-studio rule, it won on source order and every
 * unselected theme pill rendered as a near-empty dark oval. Only the two
 * `.active` pills (forced to --mono-ink via !important) stayed readable.
 *
 * These assertions pin the fix: the theme grid stays multi-column, the ink
 * ramp stays legible, and each chip previews its own palette.
 */
const fs = require("fs");
const path = require("path");
const root = path.resolve(__dirname, "..");
const css = fs.readFileSync(path.join(root, "extension/overlay.css"), "utf8");
const main = fs.readFileSync(path.join(root, "extension/core/main.js"), "utf8");

/* ── 1. Grid keeps the 8 themes in a multi-column layout ─────────────────── */
const grid = css.match(/\.zs-theme-grid\{([^}]*)\}/);
if (!grid) throw new Error("missing .zs-theme-grid rule");
const cols = grid[1].match(/grid-template-columns:repeat\((\d+),1fr\)/);
if (!cols) throw new Error("theme grid must use a repeat(n,1fr) track list");
if (Number(cols[1]) < 3) throw new Error("theme grid collapsed to " + cols[1] + " column(s) — pills will stack");
if (Number(cols[1]) > 4) throw new Error("theme grid too dense to read at " + cols[1] + " columns");

/* ── 2. Labels stay on one line inside their column ──────────────────────── */
if (!/\.zs-theme-opt b\{[^}]*text-overflow:ellipsis/.test(css))
  throw new Error("theme labels need ellipsis so long names cannot force wrap/overflow");
if (!/\.zs-theme-opt\{[^}]*min-width:0/.test(css))
  throw new Error("theme options need min-width:0 or grid children refuse to shrink");

/* ── 3. The late monochrome block must NOT re-darken the theme pill ──────── */
// Isolate the grouped "Choice / option controls" block: it is the only place
// that groups .zs-profile-opt with the other pill families.
const groupedStart = css.indexOf(".zs-profile-opt {");
if (groupedStart === -1) throw new Error("could not locate the choice/option control block");
const grouped = css.slice(groupedStart, groupedStart + 900);
if (/\.zs-theme-opt,[^]*?color:\s*var\(--mono-ink-4\)/.test(grouped))
  throw new Error("the grouped rule still lumps .zs-theme-opt back onto --mono-ink-4 (invisible)");

/* ── 4. A legible ink value is asserted for the theme pill itself ────────── */
const own = css.match(/\.zs-theme-opt\s*\{[^}]*color:\s*([^;]+);/g) || [];
if (!own.length) throw new Error("no explicit colour declared for .zs-theme-opt");
const usesLegible = own.some((r) => /--mono-ink(-2|-3)?\b\s*;?$|#b9b9c4/.test(r.replace(/\s+/g, " ").trim()));
if (!usesLegible) throw new Error("theme pill colour is not from the legible ink ramp (2/3)");

/* ── 5. --mono-ink-4 must never be the sole body colour of a pickable pill ─ */
const ink4 = "#6a6a78";
if (new RegExp("\\.zs-theme-opt[^{]*\\{[^}]*" + ink4).test(css))
  throw new Error("theme pill bound to the near-invisible --mono-ink-4 (" + ink4 + ")");

/* ── 6. Every advertised theme has a preview chip ────────────────────────── */
const themes = ["auto", "midnight", "graphite", "frost", "mono", "ink", "synthwave", "forest"];
for (const t of themes) {
  if (!main.includes('["' + t + '","'))
    throw new Error("theme '" + t + "' is no longer offered by the picker");
  if (!css.includes('.zs-theme-opt[data-theme="' + t + '"] i{background:'))
    throw new Error("theme '" + t + "' has no palette preview chip");
}

/* ── 7. The chip swatch is visible: sized, rounded, bordered ─────────────── */
const chip = css.match(/\.zs-theme-opt i\{([^}]*)\}/);
if (!chip) throw new Error("missing chip rule for .zs-theme-opt i");
const cs = chip[1].replace(/\s+/g, " ");
if (!/width:\s*1[01]px/.test(cs) || !/height:\s*1[01]px/.test(cs))
  throw new Error("theme chip must be 10–11px to read at 9.5px label scale");
if (!cs.includes("flex:0 0 auto"))
  throw new Error("theme chip must not flex-shrink or it vanishes in narrow columns");

console.log("PASS 6.18.0 theme picker: 8 legible multi-column options, per-theme palette chips, no ink-4 regression");
