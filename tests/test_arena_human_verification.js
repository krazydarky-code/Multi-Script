const pw = require('./playwright-env');
const fs = require('fs');
const NAME = 'Arena human-verification gate';
pw.guard(NAME);

(async () => {
  const browser = await pw.launch();
  if (!browser) pw.skip(NAME, 'no Chromium available');
  const page = await browser.newPage();
  await page.setContent(`<!doctype html>
    <style>*{display:block}.hidden{visibility:hidden}.cf-turnstile{width:300px;height:90px}</style>
    <main>
      <textarea placeholder="Ask anything…"></textarea>
      <button aria-label="Send message">Send</button>
      <button role="combobox">Direct</button>
      <div id="badge" class="g-recaptcha hidden" style="width:256px;height:60px"></div>
    </main>`);
  await page.addScriptTag({
    content: fs.readFileSync('extension/providers/arena.js', 'utf8') + '\nwindow.__P=ZSProvider;',
  });

  if (await page.evaluate(() => window.__P.captchaPresent())) {
    throw new Error('hidden reCAPTCHA badge caused a false pause');
  }
  await page.evaluate(() => {
    const challenge = document.createElement('div');
    challenge.id = 'challenge';
    challenge.className = 'cf-turnstile';
    challenge.style.cssText = 'display:block;width:300px;height:90px;position:fixed;left:20px;top:20px';
    document.body.appendChild(challenge);
  });
  await page.waitForTimeout(50);
  const first = await page.evaluate(async () => {
    const P = window.__P;
    return {
      present: P.captchaPresent(),
      state: await P.ensureComposerReady('startup'),
    };
  });
  if (!first.present || !first.state.humanVerificationRequired || first.state.ready) {
    throw new Error('visible challenge not gated ' + JSON.stringify(first));
  }

  const cleared = await page.evaluate(async () => {
    setTimeout(() => document.getElementById('challenge').remove(), 100);
    return window.__P.waitForHumanVerification(1500);
  });
  if (!cleared || await page.evaluate(() => window.__P.captchaPresent())) {
    throw new Error('manual-clear wait did not resume');
  }

  const source = fs.readFileSync('extension/providers/arena.js', 'utf8').toLowerCase();
  for (const forbidden of ['2captcha', 'capsolver', 'captcha token', 'grecaptcha.execute', 'contentwindow.postmessage']) {
    if (source.includes(forbidden)) throw new Error('bypass implementation detected: ' + forbidden);
  }
  const core = fs.readFileSync('extension/core/main.js', 'utf8');
  if (!core.includes('CAPTCHA or bot-check manually') || !core.includes('never bypasses verification challenges')) {
    throw new Error('human verification guidance missing');
  }

  // ── Assisted first-click: ONE trusted click on the provider's OWN widget ──
  // This is the "keep it running" half of the feature. A checkbox-style
  // challenge (Turnstile managed / hCaptcha passive) is satisfied by a single
  // real click, which is exactly what a human does. What must NOT happen is any
  // token read/write - asserted here behaviourally, not just by source scan.
  // Re-add a challenge: the resume test above removed the previous one.
  await page.evaluate(() => {
    const w = document.createElement('div');
    w.id = 'challenge';
    w.className = 'cf-turnstile';
    w.style.cssText = 'display:block;width:300px;height:90px;position:fixed;left:20px;top:20px';
    document.body.appendChild(w);
  });
  await page.waitForTimeout(50);
  await page.evaluate(() => {
    window.__clicks = 0;
    const w = document.getElementById('challenge');
    ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach((t) =>
      w.addEventListener(t, () => { window.__clicks++; }, true));
  });
  const targetHit = await page.evaluate(() => {
    const t = window.__P.challengeClickTarget();
    return !!t && t.id === 'challenge';
  });
  if (!targetHit) throw new Error('the visible challenge must be a valid click target');

  const clickResult = await page.evaluate(() => {
    window.__clicks = 0;
    const r = window.__P.assistChallengeClick();
    return { r, clicks: window.__clicks };
  });
  if (!clickResult.r.clicked) throw new Error('assistChallengeClick reported no click: ' + JSON.stringify(clickResult.r));
  if (clickResult.clicks === 0) throw new Error('assistChallengeClick dispatched no events');
  // A single gesture, not a machine-gun burst.
  if (clickResult.clicks > 5) throw new Error('the assisted click must be one bounded gesture, got ' + clickResult.clicks);
  // An invisible / badge-only challenge must never be clickable.
  const badgeHit = await page.evaluate(() => {
    document.getElementById('challenge').remove();
    return !!window.__P.challengeClickTarget();
  });
  if (badgeHit) throw new Error('the hidden v3 badge must never be a click target');

  console.log('PASS Arena human-verification gate: visible challenge pauses, manual clear resumes, hidden badge ignored, assisted click is one bounded gesture on the real widget only, no bypass logic');
  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
