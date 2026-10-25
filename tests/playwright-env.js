// SPDX-License-Identifier: GPL-3.0-or-later
// Shared Playwright bootstrap for the browser-based regression tests.
//
// These tests used to hardcode `executablePath: '/usr/local/bin/chromium'`, which
// exists on exactly one custom CI image: on plain ubuntu-latest, on macOS and on
// any Windows dev machine `chromium.launch()` threw, so the whole gate was red for
// a reason that had nothing to do with the product. This resolves a browser from
// the environment first and only then falls back to Playwright's own bundled
// build, and it SKIPS cleanly (exit 0, loud message) when Playwright is not
// installed at all, instead of reporting a product failure that is not one.
const fs = require('fs');

let chromium = null;
try { ({ chromium } = require('playwright')); } catch { /* not installed */ }

const CANDIDATES = [
  process.env.CHROMIUM_PATH,
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
  '/usr/local/bin/chromium',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
  '/usr/bin/google-chrome',
  '/snap/bin/chromium',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
].filter(Boolean);

function executablePath() {
  for (const p of CANDIDATES) {
    try { if (fs.existsSync(p)) return p; } catch {}
  }
  return null; // → let Playwright use its own bundled browser
}

function launchOptions(extra = {}) {
  const exe = executablePath();
  const opts = { headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'], ...extra };
  if (exe) opts.executablePath = exe;
  return opts;
}

// Returns a Browser, or null when no browser is usable (environment problem).
async function launch(extra) {
  if (!chromium) return null;
  try {
    return await chromium.launch(launchOptions(extra));
  } catch (e) {
    const msg = String((e && e.message) || e);
    if (/Executable doesn't exist|playwright install|Failed to launch/i.test(msg)) return null;
    throw e;
  }
}

function skip(name, why) {
  console.log(`SKIP ${name}: ${why}`);
  process.exit(0);
}

// Call at the top of a test: exits 0 with a clear reason when Playwright is absent.
function guard(name) {
  if (!chromium) {
    skip(name, 'playwright is not installed (npm i -D playwright && npx playwright install chromium)');
  }
}

module.exports = { chromium, launch, skip, guard, executablePath, launchOptions };
