// 6.30.0: sound cues are wired and never throw.
const assert = require("assert"), fs = require("fs"), path = require("path");
const X = require("../extension/core/extras.js"); const S = X.ZSSound;
assert(S && typeof S.play === "function");
assert.strictEqual(S.play("done"), false, "no AudioContext in node -> false, no throw");
const s = S.sanitize({ volume: 7, style: "nope", done: false });
assert.strictEqual(s.volume, 1); assert.strictEqual(s.style, "ping"); assert.strictEqual(s.done, false);
for (const st of Object.values(S.STYLES)) for (const k of ["done", "command", "error"]) assert(st[k].length);
const main = fs.readFileSync(path.join(__dirname, "../extension/core/main.js"), "utf8");
assert(main.includes('zsCue(A.taskToolErrors||missing?"error":"done")'), "terminal cue reflects actual tool failures");
assert(/zsCue\(isErr \? "error" : "command"\)/.test(main), "command/error cue");
assert(main.includes('id="ms-snd-on"') && main.includes("data-snd-test"), "settings section");
console.log("PASS sounds");
