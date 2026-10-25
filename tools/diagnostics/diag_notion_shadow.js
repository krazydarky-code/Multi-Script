// Diagnostic: reproduce test_notion_always_on's shadow-DOM scene and print the
// score every candidate gets, so we can see why the shadow composer is rejected.
const pw = require("../tests/playwright-env");
const fs = require("fs");
(async () => {
  const browser = await pw.launch();
  if (!browser) { console.log("no chromium"); return; }
  const page = await browser.newPage();
  await page.setContent('<button id="open" aria-label="Open Notion AI">Ask AI</button><div id="shadow-host"></div>');
  await page.evaluate(() => {
    document.getElementById("open").onclick = () => {
      const sr = document.getElementById("shadow-host").attachShadow({ mode: "open" });
      sr.innerHTML = '<style>#ed{display:block;width:500px;height:50px}</style><form data-testid="ai-composer"><div id="ed" role="textbox" contenteditable="plaintext-only" aria-label="Message Notion AI"></div><button type="submit">Send</button></form>';
    };
  });
  const code = fs.readFileSync("extension/providers/notion.js", "utf8") + "\nwindow.__P=ZSProvider;";
  await page.addScriptTag({ content: code });
  const out = await page.evaluate(async () => {
    const P = window.__P;
    const log = {};
    log.route = location.pathname;
    log.surface = P.isAiSurface ? P.isAiSurface() : "n/a";
    log.hashEmpty = !location.search && !location.hash;
    log.editorBefore = !!P.getEditor();
    log.selfBefore = P.selfTest();
    document.getElementById("open").click();
    await new Promise((r) => setTimeout(r, 300));
    log.afterClickEditor = P.getEditor() ? P.getEditor().id : null;
    log.selfAfter = P.selfTest();
    // Reach into internals via the exported hooks if present.
    const sr = document.getElementById("shadow-host").shadowRoot;
    log.shadowEditorExists = !!sr.querySelector("#ed");
    log.shadowEditorVisible = (() => { const e = sr.querySelector("#ed"); if (!e) return null; const r = e.getBoundingClientRect(); return { w: r.width, h: r.height }; })();
    return log;
  });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
