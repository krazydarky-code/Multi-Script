// Diagnostic: reproduce test_notion_dom's synthetic agent panel and report why
// (or whether) the composer resolves.
const pw = require("../tests/playwright-env");
const fs = require("fs");
(async () => {
  const browser = await pw.launch();
  if (!browser) { console.log("no chromium"); return; }
  const page = await browser.newPage();
  await page.setContent(`<!doctype html><style>body{margin:0}main{height:900px}.page-editor,.agent{display:block;width:700px;height:100px}.agent{position:fixed;bottom:0;left:100px;height:300px}.composer{position:absolute;bottom:10px;width:600px;height:60px}</style>
 <main><div class="page-editor" contenteditable="true" role="textbox">ordinary page</div></main>
 <aside class="agent" data-testid="notion-agent-panel"><div data-testid="user-message" data-message-id="u1">hello</div><div data-testid="agent-message" data-message-id="a1"><p>hi there</p></div>
 <button id="model" aria-label="Model selector">Auto</button><form class="composer" data-testid="agent-composer"><div id="agent-editor" contenteditable="true" data-placeholder="Do anything with AI&#8230;"></div><button id="send" type="submit" aria-label="Send message">Send</button></form></aside>`);
  const code = fs.readFileSync("extension/providers/notion.js", "utf8") + "\nwindow.__P=ZSProvider;";
  await page.addScriptTag({ content: code });
  const out = await page.evaluate(() => {
    const P = window.__P;
    P.init();
    const cands = P.selfTest();
    return {
      self: cands,
      editor: P.getEditor() ? P.getEditor().id : null,
      getEditorRaw: P.getEditorRaw ? (P.getEditorRaw() ? P.getEditorRaw().id : null) : "n/a",
      hasIsAiSurface: typeof P.isAiSurface,
      route: location.pathname,
    };
  });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
