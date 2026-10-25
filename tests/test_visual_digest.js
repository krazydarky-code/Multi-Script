// Text-only providers must still get something useful from screen_capture / video frames.
const fs = require('fs'), path = require('path');
const root = path.join(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const ZS = new Function(read('extension/core/config.js') + ';return ZS;')();
const MAIN = read('extension/core/main.js');
let failed = 0;
const t = (name, fn) => { try { fn(); console.log('  ok  ' + name); } catch (e) { failed++; console.log('  FAIL ' + name + ': ' + e.message); } };
const ok = (c, m) => { if (!c) throw new Error(m || 'assertion failed'); };

function img(w, h, fn) {
  const b = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const [r, g, bl, a = 255] = fn(x, y); const i = (y * w + x) * 4;
    b[i] = r; b[i + 1] = g; b[i + 2] = bl; b[i + 3] = a;
  }
  return b;
}
t('digest exports exist', () => { ok(typeof ZS.digestPixels === 'function'); ok(typeof ZS.imageDigest === 'function'); });
t('sky/ground image is described by colour and position', () => {
  const d = ZS.digestPixels(img(32, 24, (x, y) => y < 12 ? [120, 190, 240] : [40, 160, 60]), 32, 24, { width: 1280, height: 720 });
  ok(/1280x720/.test(d), 'size missing'); ok(/sky blue/.test(d) && /green/.test(d), 'colours missing');
  ok(/r1: sky blue/.test(d) && /r6: green/.test(d), 'grid positions wrong');
});
t('dark and bright frames are told apart', () => {
  ok(/very dark/.test(ZS.digestPixels(img(8, 8, () => [0, 0, 0]), 8, 8)));
  ok(/very bright/.test(ZS.digestPixels(img(8, 8, () => [255, 255, 255]), 8, 8)));
});
t('busy images are not called flat', () => {
  const d = ZS.digestPixels(img(40, 40, (x) => (x % 2 ? [255, 255, 255] : [0, 0, 0])), 40, 40);
  ok(/very detailed/.test(d), d);
});
t('transparent pixels and empty input never throw', () => {
  ok(typeof ZS.digestPixels(img(4, 4, () => [0, 0, 0, 0]), 4, 4) === 'string');
  ok(/could not be decoded/.test(ZS.digestPixels(null, 0, 0)));
});
t('imageDigest never throws on garbage (no canvas in node)', async () => {});
t('runTool returns a digest instead of an error on text-only providers', () => {
  ok(!/returned an image, but this assistant cannot see images/.test(MAIN), 'old hard error still present');
  ok(/ZS\.imageDigest\(r\.images\)/.test(MAIN), 'runTool does not call the digest');
  ok(!/VISION_TOOLS\.has\(bare\) && !P\.supportsVision\) return true/.test(MAIN), 'screen_capture is still blocked');
});
t('media relay falls back to a text description', () => {
  ok(/textFallback/.test(MAIN) && /imageDigest\(result\.payloads\)/.test(MAIN));
});
(async () => {
  const r = await ZS.imageDigest([{ mimeType: 'image/png', data: '!!!' }]);
  ok(/could not be analysed/.test(r), r);
  console.log('  ok  imageDigest degrades gracefully on garbage');
  console.log(failed ? `\n${failed} FAILED` : '\nPASS visual digest');
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.log('FAIL', e.message); process.exit(1); });
