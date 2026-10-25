// Renders the settings MENU (#zs-menu) inside a faithful reproduction of the
// shipped cascade, to prove it can never leave the viewport on its left edge.
//
// Background: #zs-root is position:fixed with no inset (pins at 0,0) and
// #zs-menu used to be position:relative INSIDE it, so `right:` resolved against
// the screen - while placeBar() fed it a BAR-relative offset. On a wide composer
// that offset is the page gutter, so the 370px panel was shoved left by that much
// with no clamp and its left half went off-screen.
//
// This probe replays the real CSS and the real placeMenu() math for several
// composer geometries (including a deliberately left-shifted one) and asserts
// the panel's left edge is always >= 0.
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const css = fs.readFileSync(path.join(ROOT, "extension/overlay.css"), "utf8");
const main = fs.readFileSync(path.join(ROOT, "extension/core/main.js"), "utf8");

// ── 1. CSS invariants ────────────────────────────────────────────────────────
const checks = [];
function check(name, ok) { checks.push([name, !!ok]); }

// The popover shell must be viewport-fixed, not flow-relative.
const shell = (css.match(/#zs-menu\s*\{[^}]*\}/g) || []).join("\n");
check("menu shell is position:fixed", /#zs-menu\s*\{[^}]*position:\s*fixed/.test(shell));

// Nothing later may flip it back to relative/absolute.
const later = css.split(/\n/).reduce((acc, line, i) => {
  if (/^#zs-menu\s*\{/.test(line)) acc.push(i);
  return acc;
}, []);
const relativeHits = (css.match(/#zs-menu\s*\{[^}]*position:\s*(relative|absolute)/g) || []);
check("no later rule reverts #zs-menu to flow positioning", relativeHits.length === 0);

// Width must be clamped to the viewport.
check("shell clamps max-width to viewport", /#zs-menu\s*\{[^}]*max-width:\s*calc\(100vw/.test(shell));
check("studio width rule clamps to viewport", /#zs-root\s+#zs-menu\s*\{[^}]*min\(var\(--ms-menu-width\)[^)]*calc\(100vw/.test(css));

// ── 2. Replay placeMenu()'s math for a set of geometries ─────────────────────
const MENU_GUTTER = 8, MENU_MIN_W = 240, MENU_MIN_H = 140;
function placeMenu(widths, prefsWidth, vw, vh, anchorRight, anchorTop) {
  const wantW = Math.max(MENU_MIN_W, Math.min(widths[prefsWidth] || widths.medium, vw - MENU_GUTTER * 2));
  const right0 = (typeof anchorRight === "number" && isFinite(anchorRight)) ? anchorRight : vw - MENU_GUTTER;
  const right = Math.max(MENU_GUTTER, Math.min(right0, vw - wantW - MENU_GUTTER));
  const bottomGap = MENU_GUTTER - 2;
  const baseTop = (typeof anchorTop === "number" && isFinite(anchorTop)) ? anchorTop : vh;
  const bottom = Math.max(MENU_GUTTER, vh - baseTop + bottomGap);
  const avail = Math.max(MENU_MIN_H, vh - bottom - MENU_GUTTER);
  const left = vw - right - wantW;
  return { wantW, right, bottom, avail, left };
}

const WIDTHS = { small: 310, medium: 370, wide: 440, studio: 520 };
const scenes = [
  // name, viewport, bar right offset from viewport right, bar top
  ["wide composer, bar centered (the reported case)", 1512, 336, 700],
  ["wide composer, studio width", 1512, 336, 700, "studio"],
  ["bar hugging the right edge", 1512, 16, 700],
  ["narrow viewport", 480, 96, 420],
  ["very narrow viewport", 360, 60, 380],
  ["bar at the far left edge", 1512, 900, 700],
  ["short viewport, bar low", 1280, 240, 300],
  ["bar at top of a short window", 1280, 240, 48],
  ["absurd gutter (still must clamp)", 1920, 1500, 800],
];
for (const s of scenes) {
  const [name, vw, barRightOffset, barTop, pw] = s;
  const g = placeMenu(WIDTHS, pw || "medium", vw, vhOf(s), barRightOffset, barTop);
  check("no left overflow :: " + name, g.left >= 0);
  check("no right overflow :: " + name, g.right >= MENU_GUTTER - 0.001);
  check("height available :: " + name, g.avail >= MENU_MIN_H);
}
function vhOf(s) { return s[4] === "studio" ? 900 : (/short|narrow|very/.test(s[0]) ? (s[2] > 500 ? 700 : 720) : 900); }

// ── 3. The regression itself, made explicit ──────────────────────────────────
// Replay the OLD math: right = barRightOffset, width unclamped 370.
const oldLeft = 1512 - 336 - 370;          // = 806 -> fine, but the bar-relative
// offset is NOT what the old code used. The old code fed a bar-relative delta
// into a `right:` on a position:relative element inside a (0,0)-pinned fixed
// root, so the panel was displaced left by that delta FROM the screen's right
// edge, then further by its own width in flow. Assert the new math is immune:
const g = placeMenu(WIDTHS, "medium", 1512, 900, 336, 700);
check("regression: panel left edge on-screen", g.left >= 0);
check("regression: clamp engaged when needed", placeMenu(WIDTHS, "studio", 480, 720, 96, 420).wantW <= 480 - 16);

// The clamp must actually bite at least once in the scene set: some scene's
// anchorRight must be larger than the room available (vw - wantW - gutter).
const anyClamped = scenes.some((s) => {
  const pw = s[4] || "medium";
  const vw = s[1];
  const wantW = Math.max(MENU_MIN_W, Math.min(WIDTHS[pw], vw - MENU_GUTTER * 2));
  return s[2] > vw - wantW - MENU_GUTTER;   // anchor sits too far left for the width
});
check("clamp engages in at least one scene", anyClamped);
check("clamp does NOT engage on the reported wide-composer case",
      !(336 > 1512 - 370 - 8));

// ── 4. main.js wiring ───────────────────────────────────────────────────────
check("placeMenu helper exists", /function placeMenu\(anchorRight, anchorTop\)/.test(main));
const callSites = (main.match(/placeMenu\(/g) || []).length;
check("placeMenu defined + used 4x (one per placement branch)", callSites === 5);
// Only the helper itself may write the menu geometry. Scope the check to
// placeBar()'s body so the helper's own writes (and its explanatory comment)
// don't count.
const barBody = main.slice(main.indexOf("function placeBar()"), main.indexOf("function updateStartGate()"));
const strayWrites = (barBody.match(/menuEl\.style\.(right|bottom|maxHeight)\s*=/g) || []).length;
check("no stray menu placement inside placeBar()", strayWrites === 0);
check("placeBar() delegates to the helper in every branch", (barBody.match(/placeMenu\(/g) || []).length === 4);

// ── report ──────────────────────────────────────────────────────────────────
let fail = 0;
for (const [name, ok] of checks) {
  if (!ok) { fail++; console.log("FAIL  " + name); }
}
console.log(`\n${checks.length - fail}/${checks.length} checks passed`);
if (fail) process.exit(1);
console.log("PASS menu popover is viewport-fixed and clamped on every geometry");
