/* Render an isolated, faithful preview of the Settings theme grid using the
 * REAL rules extracted from extension/overlay.css. Used to visually verify the
 * 6.18.0 legibility fix without launching Chrome.
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const css = fs.readFileSync(path.join(ROOT, "extension/overlay.css"), "utf8");

const THEMES = ["auto", "midnight", "graphite", "frost", "mono", "ink", "synthwave", "forest"];
const LABELS = {
  auto: "Auto", midnight: "Midnight", graphite: "Graphite", frost: "Frost",
  mono: "Mono", ink: "Ink", synthwave: "Synthwave", forest: "Forest",
};

const buttons = (active) =>
  THEMES.map(
    (t) =>
      `<button class="zs-theme-opt${t === active ? " active" : ""}" data-theme="${t}"><i></i><b>${LABELS[t]}</b></button>`
  ).join("");

/* ── Extract the real rules, by exact anchor ───────────────────────────── */

// The early appearance-studio block: grid + pill + chip + per-theme chips.
const earlyMatch = css.match(
  /\.zs-theme-grid\{[^}]*\}[\s\S]*?\.zs-theme-opt\[data-theme="forest"\] i\{[^}]*\}/
);
if (!earlyMatch) throw new Error("could not extract the early theme block");
const early = earlyMatch[0];

// The grouped "choice / option controls" rule (the block that caused the bug).
// Anchor on its banner comment, which is unique.
const gBanner = css.indexOf("/* ── Choice / option controls");
if (gBanner === -1) throw new Error("could not find the grouped block banner");
const gStart = css.indexOf(".zs-pref-opt,", gBanner);
const gEnd = css.indexOf(".zs-profile-opt {", gStart) + ".zs-profile-opt {".length;
if (gStart === -1 || gEnd < gStart) throw new Error("could not extract the grouped block");
const grouped =
  css.slice(gStart, gEnd) +
  "\n  border: 1px solid var(--mono-line);border-radius: 9px;" +
  "background: rgba(255,255,255,0.028);color: var(--mono-ink-3);" +
  "transition: background .15s ease,border-color .15s ease,color .15s ease;}\n";

// The late re-assert: everything from the theme-swatch comment to the .active
// rule. That span is exactly what makes the fix work, so it is quoted verbatim.
const rBanner = css.indexOf("/* Theme swatches carry their own");
if (rBanner === -1) throw new Error("could not find the late re-assert banner");
const rStart = rBanner;
const rEnd = css.indexOf(".zs-behavior-opt.active b", rStart);
if (rStart === -1 || rEnd < rStart) throw new Error("could not extract the late re-assert block");
const late = css.slice(rStart, rEnd);

const VARS =
  "--mono-ink:#f4f4f7;--mono-ink-2:#c9c9d2;--mono-ink-3:#9494a2;--mono-ink-4:#6a6a78;" +
  "--mono-line:rgba(255,255,255,.085);--mono-line-strong:rgba(255,255,255,.16);--ms-accent:#f2f2f6;";

const before = [
  "body{margin:0;background:#0d0d11}",
  ":root{" + VARS + "}",
  ".demo{font-family:system-ui;padding:26px}",
  ".cap{color:#9494a2;font:700 9px system-ui;letter-spacing:.6px;text-transform:uppercase;margin:0 0 10px}",
  ".note{color:#8a8a96;font:10px system-ui;margin-top:14px;line-height:1.55;max-width:420px}",
  ".row{display:flex;gap:44px;align-items:flex-start}",
  ".panel{width:470px}",
  // Reproduce the reported state faithfully: the grouped rule stamped ink-4
  // onto the label, and the chip's old flat gradient (#252631 -> accent) was
  // near-invisible on the dark panel. What the user saw was a row of empty
  // dark ovals with only the two selected pills readable.
  ".old .zs-theme-opt{color:#6a6a78;background:rgba(255,255,255,.028);border:1px solid rgba(255,255,255,.085)}",
  ".old .zs-theme-opt.active{color:#f4f4f7;background:linear-gradient(180deg,rgba(255,255,255,.13),rgba(255,255,255,.05))}",
  ".old .zs-theme-opt i{background:linear-gradient(135deg,#252631,#f2f2f6)}",
].join("\n");

const html = [
  "<!doctype html><meta charset=utf-8>",
  "<title>Theme grid \u2014 6.18.0 fix</title>",
  "<style>",
  before,
  early,
  grouped,
  late,
  "</style>",
  '<div class="demo"><div class="row">',
  // BEFORE — the reported symptom.
  '<div class="panel old"><div class="cap">Before 6.18.0</div>',
  '<div class="zs-theme-grid">' + buttons("graphite") + "</div>",
  '<div class="note">What the screenshot showed: a row of near-empty dark ovals. Only the two ' +
    "selected pills (<b>Graphite</b>, <b>Ink</b>) read, because <code>.active</code> forced " +
    "--mono-ink with !important.</div></div>",
  // AFTER — the fix.
  '<div class="panel"><div class="cap">After 6.18.0</div>',
  '<div class="zs-theme-grid">' + buttons("graphite") + "</div>",
  '<div class="note">All eight are legible, and each chip previews its own palette.</div></div>',
  "</div></div>",
].join("\n");

const OUT = process.argv[2] || path.join(ROOT, "..", "..", "..", "..", "theme_picker_preview.html");
fs.writeFileSync(OUT, html, "utf8");
console.log("wrote " + OUT);
console.log("  bytes=" + html.length);
console.log("  early block chars=" + early.length);
console.log("  grouped block chars=" + grouped.length);
console.log("  late re-assert chars=" + late.length);
console.log("  theme buttons=" + THEMES.length);
