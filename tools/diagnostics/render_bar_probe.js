/* Reproduce the #zs-bar layout at the composer widths the providers actually
 * have, to find where the chip row breaks down. Uses the REAL bar rules from
 * extension/overlay.css. Writes one page showing the bar at several widths.
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const css = fs.readFileSync(path.join(ROOT, "extension/overlay.css"), "utf8");

// Pull the bar-related rules verbatim.
const wanted = [
  /#zs-root\s*\{[^}]*\}/,
  /#zs-bar\s*\{[^}]*\}/,
  /#zs-bar\.zs-bar-inline\s*\{[^}]*\}/,
  /#zs-bar\.zs-bar-inline\.zs-bar-inside\s*\{[^}]*\}/,
  /#zs-bar\.zs-bar-anchored\s*\{[^}]*\}/,
  /#zs-brand\s*\{[^}]*\}/,
  /\.zs-free\s*\{[^}]*\}/,
  /#zs-state\s*\{[^}]*\}/,
  /\.zs-state-txt\s*\{[^}]*\}/,
  /#zs-state b\s*\{[^}]*\}/,
  /#zs-dot\s*\{[^}]*\}/,
];
let barCss = "";
for (const re of wanted) {
  const m = css.match(re);
  if (m) barCss += m[0] + "\n";
}
if (!/#zs-bar\s*\{/.test(barCss)) throw new Error("failed to extract #zs-bar rules");

const stateText = "Chat studio active · skills and starter profile enabled · no engine execution";

const barHtml = (extraClass, label) => `
<div class="case">
  <div class="lbl">${label}</div>
  <div id="zs-bar-wrap">
    <div id="zs-bar" class="${extraClass}">
      <span id="zs-dot" class="on"></span>
      <span id="zs-brand">Multi-Script <span class="zs-free">v6.18.0</span></span>
      <span id="zs-state"><span class="zs-live-dot"></span><span class="zs-state-txt">${stateText}</span></span>
      <button id="zs-switch">DeepSeek ▾</button>
    </div>
  </div>
</div>`;

// Widths seen live: Gemini's composer is the narrowest of the set.
const cases = [
  [720, "zs-bar-inline zs-bar-inside", "DeepSeek-class (720px) — reference, known good"],
  [560, "zs-bar-anchored", "Anchored @560px"],
  [480, "zs-bar-anchored", "Anchored @480px"],
  [400, "zs-bar-anchored", "Anchored @400px (Gemini-class narrow)"],
];

const html = `<!doctype html><meta charset=utf-8><title>zs-bar width probe</title>
<style>
body{margin:0;background:#0d0d11;font-family:system-ui;color:#ddd;padding:22px}
${barCss}
#zs-bar{position:static!important;left:auto!important;top:auto!important;right:auto!important}
.case{margin-bottom:26px}
.lbl{color:#9494a2;font:700 10px system-ui;letter-spacing:.5px;text-transform:uppercase;margin-bottom:8px}
#zs-bar-wrap{background:#15151c;border:1px solid rgba(255,255,255,.07);border-radius:14px;padding:10px}
#zs-switch{border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#c9c9d2;border-radius:7px;padding:3px 8px;font:600 10px system-ui;flex:none}
#zs-dot{width:7px;height:7px;border-radius:50%;flex:none}
#zs-dot.on{background:#43c38b}
</style>
${cases.map(([w, cls, label]) =>
  `<div style="width:${w}px">${barHtml(cls, label + " — width " + w + "px")}</div>`
).join("\n")}
`;

const OUT = process.argv[2] || path.join(ROOT, "..", "..", "..", "..", "bar_width_probe.html");
fs.writeFileSync(OUT, html, "utf8");
console.log("wrote " + OUT);
console.log("bar rules extracted: " + barCss.split("\n").filter(Boolean).length + " rules");
