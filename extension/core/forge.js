// SPDX-License-Identifier: GPL-3.0-or-later
// Multi-Script Forge: draws game art in the browser with the built-in Canvas (no Python add-ons).
// UI kits (9-slice ready), icons, VFX textures, 1024x1024 flipbooks and 16:9 backdrops.
// The bridge only stores the PNGs, serves them to Studio's upload_image and writes the Luau builders.
(function (g) {
  'use strict';
  const mkCanvas = (w, h) => {
    if (typeof OffscreenCanvas !== 'undefined') return new OffscreenCanvas(w, h);
    if (typeof document !== 'undefined') { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; }
    throw new Error('Forge needs a browser canvas.');
  };

  // ---------------------------------------------------------------- colour
  const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
  function hex(h) {
    let s = String(h || '').replace('#', '');
    if (s.length === 3) s = s.split('').map(c => c + c).join('');
    if (!/^[0-9a-fA-F]{6}$/.test(s)) throw new Error('Colours are hex like #ffb13b, got ' + h);
    return [0, 2, 4].map(i => parseInt(s.slice(i, i + 2), 16) / 255);
  }
  const toHex = c => '#' + c.map(v => Math.round(clamp(v) * 255).toString(16).padStart(2, '0')).join('');
  const css = (c, a = 1) => `rgba(${Math.round(clamp(c[0]) * 255)},${Math.round(clamp(c[1]) * 255)},${Math.round(clamp(c[2]) * 255)},${a})`;
  function toHsl([r, g2, b]) {
    const mx = Math.max(r, g2, b), mn = Math.min(r, g2, b), l = (mx + mn) / 2; let h = 0, s = 0;
    if (mx !== mn) { const d = mx - mn; s = l > .5 ? d / (2 - mx - mn) : d / (mx + mn);
      h = mx === r ? (g2 - b) / d + (g2 < b ? 6 : 0) : mx === g2 ? (b - r) / d + 2 : (r - g2) / d + 4; h /= 6; }
    return [h, s, l];
  }
  function fromHsl([h, s, l]) {
    if (!s) return [l, l, l];
    const q = l < .5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
    const f = t => { t = (t + 1) % 1; return t < 1 / 6 ? p + (q - p) * 6 * t : t < .5 ? q : t < 2 / 3 ? p + (q - p) * (2 / 3 - t) * 6 : p; };
    return [f(h + 1 / 3), f(h), f(h - 1 / 3)];
  }
  // f > 0 lightens toward white, f < 0 darkens (and saturates a little)
  function shade(c, f) {
    let [h, s, l] = toHsl(c);
    if (f >= 0) l = l + (1 - l) * f; else { l = l * (1 + f); s = clamp(s * (1 - f * .25)); }
    return fromHsl([h, s, l]);
  }
  const desat = (c, k = .8) => { const [h, s, l] = toHsl(c); return fromHsl([h, s * (1 - k), l]); };
  const lum = c => { const f = v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; const [r, g2, b] = c.map(f); return .2126 * r + .7152 * g2 + .0722 * b; };
  const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };

  // ---------------------------------------------------------------- styles
  // radius: fraction of the short side; ow outline px; lip 3D depth px; gloss/inner/shadow/glow strengths
  const STYLES = {
    simulator: { radius: .30, ow: 6, lip: 8, gloss: .34, grad: .22, inner: .55, shadow: .32, odark: .62, font: 'FredokaOne' },
    cartoon:   { radius: .42, ow: 7, lip: 7, gloss: .36, grad: .18, inner: .6, shadow: .26, odark: .7, font: 'FredokaOne' },
    glossy:    { radius: .48, ow: 4, lip: 5, gloss: .55, grad: .3, inner: .65, shadow: .3, odark: .55, font: 'GothamBlack' },
    candy:     { radius: .5, ow: 5, lip: 6, gloss: .45, grad: .25, inner: .7, shadow: .22, odark: .45, pattern: 'stripes', font: 'FredokaOne' },
    anime:     { radius: .22, ow: 4, lip: 3, gloss: .25, grad: .25, inner: .7, shadow: .25, odark: .4, glow: .35, font: 'GothamBlack' },
    glass:     { radius: .28, ow: 2, lip: 0, gloss: .22, grad: .1, inner: .55, shadow: .3, odark: -.45, alpha: .72, font: 'GothamMedium' },
    neon:      { radius: .24, ow: 4, lip: 0, gloss: 0, grad: .25, inner: 0, shadow: 0, odark: -.15, glow: .9, alpha: .92, hollow: true, font: 'GothamBold' },
    fantasy:   { radius: .12, ow: 5, lip: 4, gloss: .18, grad: .28, inner: .35, shadow: .35, odark: .7, trim: '#e3b85c', font: 'Fantasy' },
    scifi:     { radius: 0, ow: 3, lip: 0, gloss: .12, grad: .22, inner: .65, shadow: .3, odark: -.35, pattern: 'scan', glow: .35, chamfer: .3, font: 'Michroma' },
    minimal:   { radius: .22, ow: 0, lip: 0, gloss: 0, grad: .05, inner: 0, shadow: .18, odark: 0, font: 'BuilderSansBold' },
    horror:    { radius: .08, ow: 4, lip: 3, gloss: .05, grad: .35, inner: .18, shadow: .45, odark: .8, pattern: 'grime', font: 'Creepster' },
    pixel:     { radius: 0, ow: 6, lip: 6, gloss: 0, grad: 0, inner: .5, shadow: 0, odark: .75, chamfer: .18, pixel: true, font: 'Arcade' },
  };
  const PALETTES = {
    simulator: { primary: '#3fa9ff', secondary: '#ffb627', success: '#52d14b', danger: '#ff4a4a', panel: '#2e6fd8', panel2: '#1b3f8f', accent: '#ffe14d', text: '#ffffff' },
    cartoon:   { primary: '#ff8a1f', secondary: '#8b5cff', success: '#46d16a', danger: '#ff5470', panel: '#ffe7b0', panel2: '#f5b65b', accent: '#4fc3ff', text: '#ffffff' },
    glossy:    { primary: '#2f8cff', secondary: '#ff4fa3', success: '#2bd47d', danger: '#ff3b3b', panel: '#253049', panel2: '#151c2c', accent: '#ffd23f', text: '#ffffff' },
    candy:     { primary: '#ff6fb5', secondary: '#7fd7ff', success: '#7be36b', danger: '#ff5f6d', panel: '#ffd1ea', panel2: '#ff9fcf', accent: '#fff36b', text: '#ffffff' },
    anime:     { primary: '#ff5fa2', secondary: '#7a5cff', success: '#3ee08f', danger: '#ff4b6e', panel: '#2a2140', panel2: '#171229', accent: '#ffd84d', text: '#ffffff' },
    glass:     { primary: '#7aa8ff', secondary: '#b490ff', success: '#5fe3a1', danger: '#ff6b7a', panel: '#1f2438', panel2: '#12152a', accent: '#9ef0ff', text: '#ffffff' },
    neon:      { primary: '#00e5ff', secondary: '#ff2bd6', success: '#39ff88', danger: '#ff3355', panel: '#0b0f1f', panel2: '#05070f', accent: '#fff200', text: '#ffffff' },
    fantasy:   { primary: '#2f7d5b', secondary: '#7a3fa0', success: '#4f9d3a', danger: '#a83232', panel: '#3b2a1c', panel2: '#241811', accent: '#e3b85c', text: '#fff4d6' },
    scifi:     { primary: '#20b8ff', secondary: '#ff8a1f', success: '#2ee6a6', danger: '#ff3d57', panel: '#0f2234', panel2: '#08131f', accent: '#7ff6ff', text: '#e8fbff' },
    minimal:   { primary: '#2f6bff', secondary: '#e9edf5', success: '#1fb36b', danger: '#e5484d', panel: '#ffffff', panel2: '#eef1f6', accent: '#2f6bff', text: '#ffffff' },
    horror:    { primary: '#7a1d1d', secondary: '#3d3d3d', success: '#3f6b2f', danger: '#b3121b', panel: '#1c1716', panel2: '#0e0b0a', accent: '#c9b27a', text: '#e8dccb' },
    pixel:     { primary: '#3d7bff', secondary: '#ffb000', success: '#3ec43e', danger: '#e83b3b', panel: '#2b2f5a', panel2: '#1a1c3a', accent: '#ffe14d', text: '#ffffff' },
  };
  const RARITY = { common: '#b9c2cc', uncommon: '#5fd35f', rare: '#3fa0ff', epic: '#b05cff', legendary: '#ffb020', mythic: '#ff3f7f', secret: '#2a2a2a' };

  // ---------------------------------------------------------------- shapes
  function shapePath(kind, x, y, w, h, st) {
    const p = new Path2D(), short = Math.min(w, h);
    if (kind === 'circle') { p.arc(x + w / 2, y + h / 2, short / 2, 0, Math.PI * 2); return p; }
    if (kind === 'pill') { p.roundRect(x, y, w, h, short / 2); return p; }
    if (st.chamfer) {
      const c = Math.min(st.chamfer * short, 22);
      p.moveTo(x + c, y); p.lineTo(x + w - c, y); p.lineTo(x + w, y + c); p.lineTo(x + w, y + h - c);
      p.lineTo(x + w - c, y + h); p.lineTo(x + c, y + h); p.lineTo(x, y + h - c); p.lineTo(x, y + c); p.closePath(); return p;
    }
    p.roundRect(x, y, w, h, Math.max(0, Math.min(st.radius * short, short / 2))); return p;
  }
  const cornerOf = (kind, w, h, st) => kind === 'pill' ? Math.min(w, h) / 2 : kind === 'circle' ? Math.min(w, h) / 2 : st.chamfer ? Math.min(st.chamfer * Math.min(w, h), 22) : st.radius * Math.min(w, h);

  function patternFill(ctx, kind, w, h, seed = 7) {
    ctx.save();
    if (kind === 'stripes') { ctx.strokeStyle = 'rgba(255,255,255,.12)'; ctx.lineWidth = 7; for (let i = -h; i < w + h; i += 18) { ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i + h, h); ctx.stroke(); } }
    if (kind === 'scan') { ctx.fillStyle = 'rgba(255,255,255,.06)'; for (let y = 0; y < h; y += 4) ctx.fillRect(0, y, w, 2); }
    if (kind === 'grime') { const r = rng(seed); for (let i = 0; i < w * h / 60; i++) { ctx.fillStyle = `rgba(0,0,0,${r() * .25})`; ctx.fillRect(r() * w, r() * h, 2 + r() * 4, 2 + r() * 4); } }
    ctx.restore();
  }
  function rng(seed) { let s = (seed >>> 0) || 1; return () => { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; }; }

  // ---------------------------------------------------------------- UI element
  // Returns {canvas, slice:[x0,y0,x1,y1]|null, margin}
  function element(o) {
    const st = o.st, w = o.w, h = o.h, shape = o.shape || 'box', state = o.state || 'normal';
    let base = o.base;
    if (state === 'hover') base = shade(base, .12);
    if (state === 'disabled') base = desat(shade(base, -.05), .85);
    const pressed = state === 'pressed', inset = !!o.inset;
    const ow = st.ow, lip = inset ? 0 : (o.lip != null ? o.lip : st.lip), glow = st.glow || 0;
    const m = o.margin != null ? o.margin : Math.ceil(ow + lip + (glow ? 12 : 8) + 2);
    const c = mkCanvas(w, h), ctx = c.getContext('2d');
    if (st.pixel) ctx.imageSmoothingEnabled = false;
    const bx = m, bw = w - 2 * m, bh = h - 2 * m - lip;
    const topY = m + (pressed ? lip : 0), lipY = m + lip;
    const dark = o.outline || shade(base, -st.odark);
    const body = shapePath(shape, bx, topY, bw, bh, st);
    const bodyLip = shapePath(shape, bx, lipY, bw, bh, st);
    const grow = (y, d) => shapePath(shape, bx - d, y - d, bw + 2 * d, bh + 2 * d, { ...st, radius: st.radius ? (cornerOf(shape, bw, bh, st) + d) / Math.min(bw + 2 * d, bh + 2 * d) : 0 });
    // drop shadow + outline in one pass
    ctx.save();
    if (st.shadow > 0 && !inset) { ctx.shadowColor = `rgba(0,0,0,${st.shadow})`; ctx.shadowBlur = 8; ctx.shadowOffsetY = 4; }
    if (ow > 0 && st.alpha) { ctx.lineWidth = ow; ctx.strokeStyle = css(dark); ctx.stroke(grow(topY, ow / 2)); }
    else if (ow > 0) { ctx.fillStyle = css(dark); ctx.fill(grow(topY, ow)); if (lip && !pressed) ctx.fill(grow(lipY, ow)); }
    else if (st.shadow > 0) { ctx.fillStyle = css(base, st.alpha || 1); ctx.fill(body); }
    ctx.restore();
    if (glow > 0) { ctx.save(); ctx.shadowColor = css(shade(base, .25), glow); ctx.shadowBlur = 14; ctx.strokeStyle = css(shade(base, .25), glow); ctx.lineWidth = 2; ctx.stroke(grow(topY, ow * .5)); ctx.restore(); }
    // lip
    if (lip > 0 && !pressed) { ctx.fillStyle = css(shade(base, -.38)); ctx.fill(bodyLip); }
    // body gradient
    const fb = st.hollow ? shade(base, -.82) : base, gr = st.grad;
    const grad = ctx.createLinearGradient(0, topY, 0, topY + bh);
    grad.addColorStop(0, css(shade(fb, gr), o.alpha != null ? o.alpha : (st.alpha || 1)));
    grad.addColorStop(1, css(shade(fb, -gr * .6), o.alpha != null ? o.alpha : (st.alpha || 1)));
    ctx.fillStyle = grad; ctx.fill(body);
    ctx.save(); ctx.clip(body);
    if (inset) {
      ctx.shadowColor = css(shade(base, -.7), .7); ctx.shadowBlur = 10; ctx.shadowOffsetY = 5;
      ctx.lineWidth = 12; ctx.strokeStyle = css(shade(base, -.7), .7); ctx.stroke(shapePath(shape, bx - 6, topY - 6, bw + 12, bh + 12, st));
      ctx.shadowColor = 'transparent';
    }
    if (st.pattern) { ctx.translate(bx, topY); patternFill(ctx, st.pattern, bw, bh); ctx.setTransform(1, 0, 0, 1, 0, 0); }
    const trim = o.trim !== undefined ? o.trim : (st.trim && !inset && shape !== 'circle' ? st.trim : null);
    if (trim) {
      const tc = typeof trim === 'string' ? hex(trim) : trim;
      ctx.shadowColor = css(tc, .9); ctx.shadowBlur = 12; ctx.lineWidth = 7; ctx.strokeStyle = css(tc); ctx.stroke(body); ctx.shadowColor = 'transparent';
    }
    if (st.inner > 0 && !inset) {
      const ig = ctx.createLinearGradient(0, topY, 0, topY + bh);
      ig.addColorStop(0, css(shade(base, .6), st.inner)); ig.addColorStop(.55, css(shade(base, .6), 0));
      ctx.lineWidth = 5; ctx.strokeStyle = ig; ctx.stroke(shapePath(shape, bx + 1, topY + 1, bw - 2, bh - 2, st));
    }
    if (st.gloss > 0 && !inset) {
      const gh = bh * .5, gl = ctx.createLinearGradient(0, topY + 3, 0, topY + 3 + gh);
      const a = st.gloss * (pressed ? .7 : 1);
      gl.addColorStop(0, `rgba(255,255,255,${a})`); gl.addColorStop(1, `rgba(255,255,255,${bh > 150 ? 0 : a * .25})`);
      ctx.fillStyle = gl; ctx.fill(shapePath(shape === 'circle' ? 'pill' : shape, bx + 5, topY + 4, bw - 10, gh, { ...st, radius: st.radius ? Math.min(.5, cornerOf(shape, bw, bh, st) / Math.max(1, Math.min(bw - 10, gh))) : 0 }));
    }
    ctx.restore();
    if (o.glyph) glyph(ctx, o.glyph, bx + bw / 2, topY + bh / 2, Math.min(bw, bh) * .3, dark);
    // 9-slice centre: just inside the rounded corners
    let slice = null;
    if (shape !== 'circle' && !o.noSlice) {
      const r = cornerOf(shape, bw, bh, st);
      let x0 = Math.ceil(m + ow + r + 2), y0 = x0, x1 = w - x0, y1 = h - Math.ceil(m + ow + lip + r + 2);
      if (x1 - x0 < 2) { x0 = Math.floor(w / 2) - 1; x1 = x0 + 2; }
      if (y1 - y0 < 2) { y0 = Math.floor(h / 2) - 1; y1 = y0 + 2; }
      slice = [x0, y0, x1, y1];
    }
    return { canvas: c, slice, margin: m };
  }

  function glyph(ctx, kind, cx, cy, s, outline) {
    const p = new Path2D(), t = Math.max(3, s * .38);
    const L = (pts) => { p.moveTo(cx + pts[0][0] * s, cy + pts[0][1] * s); for (const q of pts.slice(1)) p.lineTo(cx + q[0] * s, cy + q[1] * s); };
    if (kind === 'x') { L([[-.7, -.7], [.7, .7]]); L([[.7, -.7], [-.7, .7]]); }
    else if (kind === 'plus') { L([[-.8, 0], [.8, 0]]); L([[0, -.8], [0, .8]]); }
    else if (kind === 'minus') L([[-.8, 0], [.8, 0]]);
    else if (kind === 'check') L([[-.75, 0], [-.2, .55], [.8, -.6]]);
    else if (kind === 'arrow') L([[-.3, -.7], [.4, 0], [-.3, .7]]);
    else if (kind === 'back') L([[.3, -.7], [-.4, 0], [.3, .7]]);
    else if (kind === 'down') L([[-.7, -.3], [0, .4], [.7, -.3]]);
    else if (kind === 'up') L([[-.7, .3], [0, -.4], [.7, .3]]);
    else if (kind === 'question') { p.arc(cx, cy - s * .25, s * .45, Math.PI * 1.1, Math.PI * 2.35); p.moveTo(cx + s * .1, cy + s * .2); p.lineTo(cx, cy + s * .3); }
    else return;
    ctx.save(); ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.lineWidth = t + 5; ctx.strokeStyle = css(outline); ctx.stroke(p);
    ctx.lineWidth = t; ctx.strokeStyle = '#ffffff'; ctx.stroke(p);
    if (kind === 'question') { ctx.fillStyle = css(outline); ctx.beginPath(); ctx.arc(cx, cy + s * .72, t * .62 + 2.5, 0, 7); ctx.fill(); ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(cx, cy + s * .72, t * .62, 0, 7); ctx.fill(); }
    ctx.restore();
  }

  // ---------------------------------------------------------------- icons (drawn in a 100 x 100 box)
  const ICON_COLORS = { coin: '#ffc21a', gem: '#3fd2ff', star: '#ffd43b', heart: '#ff4f6d', bolt: '#ffe14d', lock: '#b9c2cc', gift: '#ff5fa2', sword: '#cfd8e3', shield: '#3f8cff', potion: '#b05cff', trophy: '#ffc21a', crown: '#ffc21a', key: '#ffc21a', chest: '#b5702f', egg: '#f4ead2', paw: '#b07a4f', pickaxe: '#9aa6b2', gear: '#9aa6b2', cart: '#3fa9ff', bag: '#c98a4a', scroll: '#f1dfb0', clock: '#ffffff', skull: '#f1ede4', flame: '#ff8a1f', drop: '#3fb6ff', leaf: '#52d14b', ticket: '#ff5f6d', rebirth: '#7a5cff', speed: '#3fd2ff', ghost: '#e9ecff' };
  function P(fn) { const p = new Path2D(); fn(p); return p; }
  function star(p, cx, cy, r1, r2, n = 5, rot = -Math.PI / 2) { for (let i = 0; i < n * 2; i++) { const r = i % 2 ? r2 : r1, a = rot + i * Math.PI / n; i ? p.lineTo(cx + r * Math.cos(a), cy + r * Math.sin(a)) : p.moveTo(cx + r * Math.cos(a), cy + r * Math.sin(a)); } p.closePath(); }
  function poly(p, pts) { p.moveTo(pts[0][0], pts[0][1]); for (const q of pts.slice(1)) p.lineTo(q[0], q[1]); p.closePath(); }
  const ICONS = {
    coin: c => [[P(p => p.arc(50, 52, 38, 0, 7)), 0, { rimShade: -.35 }], [P(p => p.arc(50, 50, 26, 0, 7)), -.18, { stroke: true }], [P(p => star(p, 50, 50, 15, 7)), .45]],
    gem: c => [[P(p => poly(p, [[14, 38], [30, 18], [70, 18], [86, 38], [50, 88]])), 0], [P(p => poly(p, [[30, 18], [70, 18], [62, 38], [38, 38]])), .5], [P(p => poly(p, [[62, 38], [86, 38], [50, 88]])), -.35]],
    star: c => [[P(p => star(p, 50, 54, 44, 20)), 0]],
    heart: c => [[P(p => { p.moveTo(50, 86); p.bezierCurveTo(10, 60, 6, 32, 26, 22); p.bezierCurveTo(38, 16, 48, 24, 50, 32); p.bezierCurveTo(52, 24, 62, 16, 74, 22); p.bezierCurveTo(94, 32, 90, 60, 50, 86); p.closePath(); }), 0]],
    bolt: c => [[P(p => poly(p, [[58, 8], [22, 56], [46, 56], [38, 92], [78, 40], [54, 40]])), 0]],
    lock: c => [[P(p => { p.roundRect(20, 44, 60, 46, 10); }), 0], [P(p => { p.moveTo(32, 46); p.lineTo(32, 32); p.arc(50, 32, 18, Math.PI, 0); p.lineTo(68, 46); p.lineTo(60, 46); p.lineTo(60, 32); p.arc(50, 32, 10, 0, Math.PI, true); p.lineTo(40, 46); p.closePath(); }), -.05], [P(p => { p.arc(50, 62, 6, 0, 7); p.rect(47, 62, 6, 14); }), -.6]],
    gift: c => [[P(p => p.roundRect(16, 40, 68, 50, 6)), 0], [P(p => p.roundRect(12, 30, 76, 16, 5)), .12], [P(p => { p.rect(44, 30, 12, 60); }), 'ribbon'], [P(p => { p.ellipse(38, 24, 12, 8, -.4, 0, 7); p.ellipse(62, 24, 12, 8, .4, 0, 7); }), 'ribbon']],
    sword: c => [[P(p => poly(p, [[46, 66], [46, 14], [50, 6], [54, 14], [54, 66]])), 0], [P(p => p.roundRect(28, 64, 44, 9, 4)), 'gold'], [P(p => p.roundRect(45, 72, 10, 18, 3)), 'wood'], [P(p => p.arc(50, 92, 6, 0, 7)), 'gold']],
    shield: c => [[P(p => { p.moveTo(50, 8); p.lineTo(86, 20); p.bezierCurveTo(86, 58, 72, 80, 50, 94); p.bezierCurveTo(28, 80, 14, 58, 14, 20); p.closePath(); }), 0], [P(p => { p.moveTo(50, 20); p.lineTo(74, 28); p.bezierCurveTo(74, 56, 64, 72, 50, 82); p.bezierCurveTo(36, 72, 26, 56, 26, 28); p.closePath(); }), .25], [P(p => star(p, 50, 50, 14, 6)), 'gold']],
    potion: c => [[P(p => { p.moveTo(42, 10); p.lineTo(58, 10); p.lineTo(58, 34); p.bezierCurveTo(80, 42, 86, 60, 80, 74); p.bezierCurveTo(74, 90, 26, 90, 20, 74); p.bezierCurveTo(14, 60, 20, 42, 42, 34); p.closePath(); }), 'glass'], [P(p => { p.moveTo(22, 64); p.bezierCurveTo(40, 56, 60, 72, 78, 62); p.bezierCurveTo(80, 70, 76, 84, 50, 86); p.bezierCurveTo(26, 86, 20, 74, 22, 64); p.closePath(); }), 0], [P(p => p.roundRect(38, 4, 24, 10, 3)), 'wood']],
    trophy: c => [[P(p => { p.moveTo(26, 12); p.lineTo(74, 12); p.bezierCurveTo(74, 46, 62, 58, 50, 60); p.bezierCurveTo(38, 58, 26, 46, 26, 12); p.closePath(); }), 0], [P(p => { p.moveTo(26, 18); p.bezierCurveTo(8, 18, 10, 44, 30, 44); p.lineTo(32, 38); p.bezierCurveTo(18, 38, 18, 24, 27, 24); p.closePath(); p.moveTo(74, 18); p.bezierCurveTo(92, 18, 90, 44, 70, 44); p.lineTo(68, 38); p.bezierCurveTo(82, 38, 82, 24, 73, 24); p.closePath(); }), -.1], [P(p => { p.rect(44, 58, 12, 16); p.roundRect(30, 74, 40, 14, 4); }), -.15]],
    crown: c => [[P(p => poly(p, [[12, 78], [10, 30], [32, 50], [50, 18], [68, 50], [90, 30], [88, 78]])), 0], [P(p => p.roundRect(12, 74, 76, 12, 4)), -.15], [P(p => { p.arc(50, 60, 6, 0, 7); }), 'gem'], [P(p => { p.arc(28, 64, 4.5, 0, 7); p.moveTo(76.5, 64); p.arc(72, 64, 4.5, 0, 7); }), 'ruby']],
    key: c => [[P(p => { p.arc(30, 50, 20, 0, 7); }), 0], [P(p => { p.rect(44, 45, 46, 10); p.rect(76, 55, 8, 12); p.rect(64, 55, 8, 9); }), 0], [P(p => p.arc(30, 50, 8, 0, 7)), 'hole']],
    chest: c => [[P(p => p.roundRect(12, 44, 76, 44, 6)), 0], [P(p => { p.moveTo(12, 46); p.lineTo(12, 34); p.bezierCurveTo(12, 14, 88, 14, 88, 34); p.lineTo(88, 46); p.closePath(); }), .1], [P(p => { p.rect(12, 42, 76, 7); p.rect(22, 20, 7, 68); p.rect(71, 20, 7, 68); }), 'gold'], [P(p => p.roundRect(42, 44, 16, 18, 3)), 'gold']],
    egg: c => [[P(p => { p.moveTo(50, 8); p.bezierCurveTo(78, 8, 88, 52, 84, 66); p.bezierCurveTo(80, 86, 64, 94, 50, 94); p.bezierCurveTo(36, 94, 20, 86, 16, 66); p.bezierCurveTo(12, 52, 22, 8, 50, 8); p.closePath(); }), 0], [P(p => { p.arc(36, 46, 7, 0, 7); p.moveTo(70, 60); p.arc(64, 60, 6, 0, 7); p.moveTo(54, 80); p.arc(48, 80, 5, 0, 7); }), 'spots']],
    paw: c => [[P(p => { p.ellipse(50, 66, 22, 18, 0, 0, 7); }), 0], [P(p => { p.ellipse(24, 42, 9, 12, -.3, 0, 7); p.moveTo(48, 30); p.ellipse(40, 28, 9, 12, -.1, 0, 7); p.moveTo(68, 28); p.ellipse(60, 28, 9, 12, .1, 0, 7); p.moveTo(84, 42); p.ellipse(76, 42, 9, 12, .3, 0, 7); }), 0]],
    pickaxe: c => [[P(p => { p.moveTo(14, 34); p.bezierCurveTo(36, 10, 64, 10, 86, 34); p.lineTo(80, 38); p.bezierCurveTo(62, 24, 38, 24, 20, 38); p.closePath(); }), 0], [P(p => { p.moveTo(46, 24); p.lineTo(54, 24); p.lineTo(58, 92); p.lineTo(46, 92); p.closePath(); }), 'wood']],
    gear: c => [[P(p => { for (let i = 0; i < 16; i++) { const a = i * Math.PI / 8, r = i % 2 ? 32 : 42; const a2 = a + Math.PI / 8; i ? p.lineTo(50 + r * Math.cos(a), 50 + r * Math.sin(a)) : p.moveTo(50 + r * Math.cos(a), 50 + r * Math.sin(a)); p.lineTo(50 + r * Math.cos(a2 - .08), 50 + r * Math.sin(a2 - .08)); } p.closePath(); }), 0], [P(p => p.arc(50, 50, 13, 0, 7)), 'hole']],
    cart: c => [[P(p => { p.moveTo(8, 18); p.lineTo(22, 18); p.lineTo(32, 64); p.lineTo(80, 64); p.lineTo(90, 30); p.lineTo(26, 30); p.lineTo(24, 22); }), 'line'], [P(p => poly(p, [[27, 32], [88, 32], [79, 62], [33, 62]])), 0], [P(p => { p.arc(38, 80, 8, 0, 7); p.moveTo(82, 80); p.arc(74, 80, 8, 0, 7); }), -.5]],
    bag: c => [[P(p => { p.moveTo(22, 36); p.lineTo(78, 36); p.lineTo(86, 88); p.lineTo(14, 88); p.closePath(); }), 0], [P(p => { p.moveTo(36, 38); p.bezierCurveTo(36, 8, 64, 8, 64, 38); }), 'line'], [P(p => p.roundRect(40, 50, 20, 12, 3)), 'gold']],
    scroll: c => [[P(p => p.roundRect(22, 16, 56, 68, 4)), 0], [P(p => { p.roundRect(14, 10, 72, 14, 7); p.roundRect(14, 78, 72, 14, 7); }), -.15], [P(p => { for (let y = 34; y <= 66; y += 10) p.rect(32, y, 36, 4); }), 'ink']],
    clock: c => [[P(p => p.arc(50, 52, 40, 0, 7)), 0], [P(p => { p.moveTo(50, 52); p.lineTo(50, 26); p.moveTo(50, 52); p.lineTo(68, 60); }), 'hands']],
    skull: c => [[P(p => { p.moveTo(50, 8); p.bezierCurveTo(82, 8, 90, 34, 84, 54); p.lineTo(72, 64); p.lineTo(72, 84); p.lineTo(28, 84); p.lineTo(28, 64); p.lineTo(16, 54); p.bezierCurveTo(10, 34, 18, 8, 50, 8); p.closePath(); }), 0], [P(p => { p.ellipse(35, 44, 10, 12, 0, 0, 7); p.moveTo(75, 44); p.ellipse(65, 44, 10, 12, 0, 0, 7); poly(p, [[50, 56], [44, 68], [56, 68]]); }), 'hole']],
    flame: c => [[P(p => { p.moveTo(50, 6); p.bezierCurveTo(60, 30, 84, 40, 82, 64); p.bezierCurveTo(80, 84, 64, 94, 50, 94); p.bezierCurveTo(30, 94, 18, 80, 20, 62); p.bezierCurveTo(22, 46, 36, 40, 38, 24); p.bezierCurveTo(44, 32, 46, 38, 50, 6); p.closePath(); }), 0], [P(p => { p.moveTo(50, 46); p.bezierCurveTo(58, 58, 68, 64, 64, 78); p.bezierCurveTo(60, 88, 40, 88, 36, 78); p.bezierCurveTo(34, 66, 46, 60, 50, 46); p.closePath(); }), 'core']],
    drop: c => [[P(p => { p.moveTo(50, 6); p.bezierCurveTo(60, 30, 82, 48, 82, 64); p.bezierCurveTo(82, 82, 68, 94, 50, 94); p.bezierCurveTo(32, 94, 18, 82, 18, 64); p.bezierCurveTo(18, 48, 40, 30, 50, 6); p.closePath(); }), 0]],
    leaf: c => [[P(p => { p.moveTo(14, 86); p.bezierCurveTo(10, 40, 40, 12, 88, 12); p.bezierCurveTo(88, 60, 60, 90, 14, 86); p.closePath(); }), 0], [P(p => { p.moveTo(18, 82); p.bezierCurveTo(40, 60, 60, 40, 80, 20); }), 'vein']],
    ticket: c => [[P(p => { p.moveTo(10, 28); p.lineTo(90, 28); p.lineTo(90, 42); p.arc(90, 50, 8, -Math.PI / 2, Math.PI / 2, true); p.lineTo(90, 72); p.lineTo(10, 72); p.lineTo(10, 58); p.arc(10, 50, 8, Math.PI / 2, -Math.PI / 2, true); p.closePath(); }), 0], [P(p => { for (let y = 32; y < 70; y += 8) p.rect(64, y, 3, 4); }), -.4]],
    rebirth: c => [[P(p => { p.arc(50, 50, 34, -2.6, 2.2); p.lineTo(50 + 24 * Math.cos(2.2), 50 + 24 * Math.sin(2.2)); p.arc(50, 50, 24, 2.2, -2.6, true); p.closePath(); }), 0], [P(p => poly(p, [[22, 14], [24, 40], [46, 30]])), 0]],
    speed: c => [[P(p => { poly(p, [[30, 14], [62, 14], [52, 42], [76, 42], [34, 92], [44, 54], [22, 54]]); }), 0], [P(p => { p.rect(4, 30, 18, 6); p.rect(0, 46, 16, 6); p.rect(6, 62, 14, 6); }), -.2]],
    ghost: c => [[P(p => { p.moveTo(18, 90); p.lineTo(18, 46); p.bezierCurveTo(18, 4, 82, 4, 82, 46); p.lineTo(82, 90); p.lineTo(70, 80); p.lineTo(58, 90); p.lineTo(50, 80); p.lineTo(42, 90); p.lineTo(30, 80); p.closePath(); }), 0], [P(p => { p.ellipse(38, 44, 6, 9, 0, 0, 7); p.moveTo(68, 44); p.ellipse(62, 44, 6, 9, 0, 0, 7); }), 'hole']],
  };
  const SPECIAL = { gold: '#ffc21a', wood: '#8a5a2b', ribbon: '#fff1a0', ruby: '#ff3f5f', gem: '#3fd2ff', glass: '#cfe8ff', ink: '#8a6a3a', hands: '#333a44', spots: '#7fd27a', core: '#fff1a0', vein: '#2f8a2f', hole: '#22262e', line: '#333a44' };

  function icon(kind, size, color, st) {
    if (!ICONS[kind]) throw new Error('Unknown icon ' + kind);
    const c = mkCanvas(size, size), ctx = c.getContext('2d'), k = size / 100 * .86, off = size * .07;
    const base = hex(color || ICON_COLORS[kind]), dark = shade(base, -.62), ow = Math.max(2.5, 5 / k * (size / 128));
    ctx.translate(off, off); ctx.scale(k, k); ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    const parts = ICONS[kind](ctx);
    // outline pass under everything (keeps a clean silhouette)
    ctx.save(); ctx.shadowColor = 'rgba(0,0,0,.28)'; ctx.shadowBlur = 4 / k; ctx.shadowOffsetY = 2.5 / k;
    for (const [p, tone] of parts) { ctx.lineWidth = (tone === 'line' || tone === 'hands' || tone === 'vein') ? ow * 2.6 : ow * 2; ctx.strokeStyle = css(dark); if (tone !== 'hole' && tone !== 'ink') ctx.stroke(p); if (typeof tone === 'number' || tone === 'glass') { ctx.fillStyle = css(dark); ctx.fill(p); } }
    ctx.restore();
    for (const [p, tone, opt] of parts) {
      if (tone === 'line' || tone === 'hands' || tone === 'vein') { ctx.lineWidth = ow * 1.2; ctx.strokeStyle = css(tone === 'vein' ? shade(base, -.35) : hex(SPECIAL[tone] === '#333a44' ? toHex(shade(base, -.1)) : SPECIAL[tone])); if (tone === 'hands') ctx.strokeStyle = css(hex('#333a44')); ctx.stroke(p); continue; }
      let col;
      if (typeof tone === 'number') col = shade(base, tone);
      else if (tone === 'hole') { ctx.fillStyle = css(shade(base, -.75)); ctx.fill(p); continue; }
      else if (tone === 'ink') { ctx.fillStyle = css(hex(SPECIAL.ink), .8); ctx.fill(p); continue; }
      else col = hex(SPECIAL[tone]);
      if (opt && opt.stroke) { ctx.lineWidth = ow * .9; ctx.strokeStyle = css(shade(base, -.3)); ctx.stroke(p); continue; }
      const gr = ctx.createLinearGradient(0, 0, 0, 100);
      gr.addColorStop(0, css(shade(col, .35), tone === 'glass' ? .55 : 1)); gr.addColorStop(1, css(shade(col, -.2), tone === 'glass' ? .55 : 1));
      ctx.fillStyle = gr; ctx.fill(p);
      if (typeof tone !== 'number' && tone !== 'glass') { ctx.lineWidth = ow * .6; ctx.strokeStyle = css(shade(col, -.55)); ctx.stroke(p); }
    }
    // gloss highlight clipped to the first (main) shape
    ctx.save(); ctx.clip(parts[0][0]);
    const gl = ctx.createLinearGradient(0, 0, 0, 55); gl.addColorStop(0, 'rgba(255,255,255,.5)'); gl.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = gl; ctx.beginPath(); ctx.ellipse(40, 22, 34, 20, -.35, 0, 7); ctx.fill(); ctx.restore();
    return c;
  }

  // ---------------------------------------------------------------- noise (tileable value noise)
  function noiseField(w, h, cells, octaves, seed) {
    const out = new Float32Array(w * h); let amp = 1, tot = 0;
    for (let o = 0; o < octaves; o++) {
      const cx = Math.max(1, Math.round(cells * 2 ** o)), cy = Math.max(1, Math.round(cells * 2 ** o * h / w)), r = rng(seed + o * 977), lat = new Float32Array(cx * cy);
      for (let i = 0; i < lat.length; i++) lat[i] = r();
      for (let y = 0; y < h; y++) {
        const fy = (y + .5) / h * cy, y0 = Math.floor(fy), ty0 = fy - y0, ty = ty0 * ty0 * (3 - 2 * ty0), ya = (y0 % cy) * cx, yb = ((y0 + 1) % cy) * cx;
        for (let x = 0; x < w; x++) {
          const fx = (x + .5) / w * cx, x0 = Math.floor(fx), tx0 = fx - x0, tx = tx0 * tx0 * (3 - 2 * tx0), xa = x0 % cx, xb = (x0 + 1) % cx;
          const a = lat[ya + xa] + (lat[ya + xb] - lat[ya + xa]) * tx, b = lat[yb + xa] + (lat[yb + xb] - lat[yb + xa]) * tx;
          out[y * w + x] += (a + (b - a) * ty) * amp;
        }
      }
      tot += amp; amp *= .5;
    }
    for (let i = 0; i < out.length; i++) out[i] /= tot;
    return out;
  }
  // write an alpha field (0..1) as white pixels into ctx at (ox, oy)
  function putAlpha(ctx, a, w, h, ox = 0, oy = 0, rgb = [255, 255, 255]) {
    const img = ctx.createImageData(w, h), d = img.data;
    for (let i = 0; i < w * h; i++) { d[i * 4] = rgb[0]; d[i * 4 + 1] = rgb[1]; d[i * 4 + 2] = rgb[2]; d[i * 4 + 3] = Math.round(clamp(a[i]) * 255); }
    ctx.putImageData(img, ox, oy);
  }

  // ---------------------------------------------------------------- VFX textures (white on transparent: tint with Color)
  function glowStroke(ctx, path, width, blur, alpha = 1) {
    ctx.save(); ctx.strokeStyle = `rgba(255,255,255,${alpha})`; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.shadowColor = 'rgba(255,255,255,1)'; ctx.shadowBlur = blur; ctx.lineWidth = width; ctx.stroke(path); ctx.shadowBlur = blur * .4; ctx.stroke(path); ctx.restore();
  }
  function radial(ctx, cx, cy, r, stops) { const gr = ctx.createRadialGradient(cx, cy, 0, cx, cy, r); for (const [t, a] of stops) gr.addColorStop(t, `rgba(255,255,255,${a})`); ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(cx, cy, r, 0, 7); ctx.fill(); }
  const VFX_SINGLES = ['glow', 'orb', 'spark', 'star', 'twinkle', 'ring', 'shockwave', 'smoke', 'cloud', 'slash', 'crescent', 'flare', 'lightning', 'magic_circle', 'rune_ring', 'dust', 'heal_plus', 'bubble', 'snowflake', 'leaf', 'droplet', 'swirl', 'hit_star', 'feather', 'confetti', 'heart_glow', 'wisp'];
  function vfxSingle(kind, n = 256, seed = 1) {
    const c = mkCanvas(n, n), ctx = c.getContext('2d'), m = n / 2, r = rng(seed);
    const S = n / 256;
    switch (kind) {
      case 'glow': radial(ctx, m, m, m * .98, [[0, 1], [.25, .65], [.6, .18], [1, 0]]); break;
      case 'orb': radial(ctx, m, m, m * .95, [[0, 1], [.3, 1], [.36, .55], [.7, .12], [1, 0]]); break;
      case 'spark': { const gr = ctx.createLinearGradient(0, n * .05, 0, n * .95); gr.addColorStop(0, 'rgba(255,255,255,0)'); gr.addColorStop(.45, 'rgba(255,255,255,1)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
        ctx.save(); ctx.shadowColor = '#fff'; ctx.shadowBlur = 10 * S; ctx.fillStyle = gr; ctx.beginPath(); ctx.ellipse(m, m, 7 * S, n * .45, 0, 0, 7); ctx.fill(); ctx.restore(); radial(ctx, m, m * .95, 20 * S, [[0, 1], [1, 0]]); break; }
      case 'star': case 'twinkle': case 'hit_star': {
        const arms = kind === 'hit_star' ? 8 : 4, len = kind === 'twinkle' ? .48 : .46;
        for (let i = 0; i < arms; i++) { const a = i * Math.PI * 2 / arms, L = (i % 2 && arms > 4 ? .6 : 1) * n * len;
          ctx.save(); ctx.translate(m, m); ctx.rotate(a); const gr = ctx.createLinearGradient(0, 0, L, 0); gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
          ctx.fillStyle = gr; ctx.beginPath(); ctx.moveTo(0, -5 * S); ctx.lineTo(L, 0); ctx.lineTo(0, 5 * S); ctx.closePath(); ctx.fill(); ctx.restore(); }
        if (kind === 'twinkle') { ctx.save(); ctx.translate(m, m); ctx.rotate(Math.PI / 4); for (let i = 0; i < 4; i++) { ctx.rotate(Math.PI / 2); const gr = ctx.createLinearGradient(0, 0, n * .2, 0); gr.addColorStop(0, 'rgba(255,255,255,.6)'); gr.addColorStop(1, 'rgba(255,255,255,0)'); ctx.fillStyle = gr; ctx.beginPath(); ctx.moveTo(0, -3 * S); ctx.lineTo(n * .2, 0); ctx.lineTo(0, 3 * S); ctx.fill(); } ctx.restore(); }
        radial(ctx, m, m, n * .16, [[0, 1], [.4, .7], [1, 0]]); break; }
      case 'ring': glowStroke(ctx, P(p => p.arc(m, m, n * .38, 0, 7)), 7 * S, 10 * S); break;
      case 'shockwave': { const gr = ctx.createRadialGradient(m, m, n * .18, m, m, n * .48); gr.addColorStop(0, 'rgba(255,255,255,0)'); gr.addColorStop(.7, 'rgba(255,255,255,.55)'); gr.addColorStop(.92, 'rgba(255,255,255,1)'); gr.addColorStop(1, 'rgba(255,255,255,0)'); ctx.fillStyle = gr; ctx.fillRect(0, 0, n, n); break; }
      case 'smoke': case 'cloud': {
        const nz = noiseField(n, n, kind === 'cloud' ? 3 : 4, 5, seed), a = new Float32Array(n * n);
        for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) { const dx = (x - m) / m, dy = (y - m) / m, d = Math.hypot(dx, dy) * (kind === 'cloud' ? 1.1 : 1), body = Math.exp(-d * d * 2.4);
          a[y * n + x] = clamp((nz[y * n + x] * .9 + body * .95 - .78) * 2.6) * body ** .4 * (kind === 'cloud' ? 1 : .85); }
        putAlpha(ctx, a, n, n); break; }
      case 'slash': case 'crescent': {
        ctx.save(); ctx.translate(m, m * 1.08);
        const outer = n * .44, inner = n * (kind === 'slash' ? .36 : .3), sweep = kind === 'slash' ? 2.4 : 3.0;
        const p = new Path2D(); p.arc(0, 0, outer, -Math.PI / 2 - sweep / 2, -Math.PI / 2 + sweep / 2); p.arc(-n * .02, n * .05, inner, -Math.PI / 2 + sweep / 2 * .96, -Math.PI / 2 - sweep / 2 * .96, true); p.closePath();
        const gr = ctx.createLinearGradient(-outer, 0, outer, 0); gr.addColorStop(0, 'rgba(255,255,255,0)'); gr.addColorStop(.5, 'rgba(255,255,255,1)'); gr.addColorStop(1, 'rgba(255,255,255,.15)');
        ctx.shadowColor = '#fff'; ctx.shadowBlur = 14 * S; ctx.fillStyle = gr; ctx.fill(p); ctx.restore(); break; }
      case 'flare': radial(ctx, m, m, m * .9, [[0, 1], [.12, .9], [.4, .2], [1, 0]]);
        for (const [a, L, wd] of [[0, .49, 3], [Math.PI / 2, .3, 2.2], [Math.PI / 4, .2, 1.6], [-Math.PI / 4, .2, 1.6]]) { ctx.save(); ctx.translate(m, m); ctx.rotate(a); const gr = ctx.createLinearGradient(-n * L, 0, n * L, 0); gr.addColorStop(0, 'rgba(255,255,255,0)'); gr.addColorStop(.5, 'rgba(255,255,255,1)'); gr.addColorStop(1, 'rgba(255,255,255,0)'); ctx.fillStyle = gr; ctx.fillRect(-n * L, -wd * S, n * L * 2, wd * 2 * S); ctx.restore(); }
        break;
      case 'lightning': { const pts = [[m, n * .04], [m, n * .96]];
        let seg = pts; for (let d = 0; d < 6; d++) { const nx = []; for (let i = 0; i < seg.length - 1; i++) { nx.push(seg[i]); nx.push([(seg[i][0] + seg[i + 1][0]) / 2 + (r() - .5) * n * .28 / (d + 1), (seg[i][1] + seg[i + 1][1]) / 2]); } nx.push(seg[seg.length - 1]); seg = nx; }
        const p = new Path2D(); p.moveTo(seg[0][0], seg[0][1]); for (const q of seg) p.lineTo(q[0], q[1]);
        const br = new Path2D(); const k = Math.floor(seg.length * .4); br.moveTo(seg[k][0], seg[k][1]); let bx = seg[k][0], by = seg[k][1]; for (let i = 0; i < 8; i++) { bx += (r() * .5 + .3) * n * .03 * (r() > .5 ? 1 : -1) + n * .02; by += n * .03; br.lineTo(bx, by); }
        glowStroke(ctx, p, 3.5 * S, 12 * S); glowStroke(ctx, br, 2 * S, 8 * S, .8); break; }
      case 'magic_circle': case 'rune_ring': {
        ctx.save(); ctx.translate(m, m); ctx.strokeStyle = '#fff'; ctx.shadowColor = '#fff'; ctx.shadowBlur = 6 * S;
        const R = n * .46; for (const [rr, lw] of [[1, 3], [.92, 1.6], [.66, 2], [.4, 1.6]]) { if (kind === 'rune_ring' && rr < .9) continue; ctx.lineWidth = lw * S; ctx.beginPath(); ctx.arc(0, 0, R * rr, 0, 7); ctx.stroke(); }
        for (let i = 0; i < 48; i++) { const a = i * Math.PI / 24; ctx.lineWidth = 1.6 * S; ctx.beginPath(); ctx.moveTo(Math.cos(a) * R * .93, Math.sin(a) * R * .93); ctx.lineTo(Math.cos(a) * R * (i % 4 ? .97 : .99), Math.sin(a) * R * (i % 4 ? .97 : .99)); ctx.stroke(); }
        const glyphs = 12; for (let i = 0; i < glyphs; i++) { const a = i * Math.PI * 2 / glyphs; ctx.save(); ctx.rotate(a); ctx.translate(0, -R * .79); ctx.lineWidth = 2 * S; ctx.beginPath(); const gtype = i % 4; const q = 7 * S;
          if (gtype === 0) { ctx.moveTo(-q, q); ctx.lineTo(0, -q); ctx.lineTo(q, q); } else if (gtype === 1) { ctx.moveTo(-q, -q); ctx.lineTo(q, -q); ctx.moveTo(0, -q); ctx.lineTo(0, q); } else if (gtype === 2) { ctx.arc(0, 0, q * .8, 0, 7); ctx.moveTo(-q, q); ctx.lineTo(q, q); } else { ctx.moveTo(-q, 0); ctx.lineTo(q, 0); ctx.moveTo(-q * .5, -q); ctx.lineTo(q * .5, q); }
          ctx.stroke(); ctx.restore(); }
        if (kind === 'magic_circle') { const p = new Path2D(); star(p, 0, 0, R * .64, R * .25, 6); ctx.lineWidth = 2 * S; ctx.stroke(p); const t = new Path2D(); for (let k = 0; k < 2; k++) { poly(t, [0, 1, 2].map(i => { const a = -Math.PI / 2 + k * Math.PI / 3 + i * Math.PI * 2 / 3; return [Math.cos(a) * R * .4, Math.sin(a) * R * .4]; })); } ctx.stroke(t); }
        ctx.restore(); radial(ctx, m, m, n * .48, [[0, .12], [1, 0]]); break; }
      case 'dust': for (let i = 0; i < 9; i++) radial(ctx, m + (r() - .5) * n * .45, m + (r() - .5) * n * .45, n * (.08 + r() * .14), [[0, .5 + r() * .4], [1, 0]]); break;
      case 'heal_plus': ctx.save(); ctx.shadowColor = '#fff'; ctx.shadowBlur = 18 * S; ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.roundRect(m - n * .1, m - n * .32, n * .2, n * .64, n * .05); ctx.roundRect(m - n * .32, m - n * .1, n * .64, n * .2, n * .05); ctx.fill(); ctx.restore(); break;
      case 'bubble': { const gr = ctx.createRadialGradient(m, m, n * .3, m, m, n * .44); gr.addColorStop(0, 'rgba(255,255,255,.08)'); gr.addColorStop(.85, 'rgba(255,255,255,.55)'); gr.addColorStop(1, 'rgba(255,255,255,0)'); ctx.fillStyle = gr; ctx.beginPath(); ctx.arc(m, m, n * .44, 0, 7); ctx.fill(); ctx.fillStyle = 'rgba(255,255,255,.85)'; ctx.beginPath(); ctx.ellipse(m - n * .15, m - n * .18, n * .07, n * .04, -.6, 0, 7); ctx.fill(); break; }
      case 'snowflake': { ctx.save(); ctx.translate(m, m); ctx.strokeStyle = '#fff'; ctx.lineCap = 'round'; ctx.shadowColor = '#fff'; ctx.shadowBlur = 6 * S; ctx.lineWidth = 6 * S;
        for (let i = 0; i < 6; i++) { ctx.rotate(Math.PI / 3); ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(0, -n * .42); for (const t of [.18, .3]) { ctx.moveTo(0, -n * t); ctx.lineTo(n * .08, -n * (t + .08)); ctx.moveTo(0, -n * t); ctx.lineTo(-n * .08, -n * (t + .08)); } ctx.stroke(); } ctx.restore(); break; }
      case 'leaf': { ctx.save(); ctx.translate(m, m); ctx.rotate(-.6); ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.moveTo(0, -n * .4); ctx.bezierCurveTo(n * .3, -n * .2, n * .25, n * .25, 0, n * .4); ctx.bezierCurveTo(-n * .25, n * .25, -n * .3, -n * .2, 0, -n * .4); ctx.fill();
        ctx.globalCompositeOperation = 'destination-out'; ctx.lineWidth = 4 * S; ctx.beginPath(); ctx.moveTo(0, -n * .35); ctx.lineTo(0, n * .38); ctx.stroke(); ctx.restore(); break; }
      case 'droplet': ctx.save(); ctx.shadowColor = '#fff'; ctx.shadowBlur = 8 * S; ctx.fillStyle = 'rgba(255,255,255,.9)'; ctx.beginPath(); ctx.moveTo(m, n * .1); ctx.bezierCurveTo(m + n * .1, n * .35, m + n * .28, n * .5, m + n * .28, n * .64); ctx.bezierCurveTo(m + n * .28, n * .82, m + n * .12, n * .9, m, n * .9); ctx.bezierCurveTo(m - n * .12, n * .9, m - n * .28, n * .82, m - n * .28, n * .64); ctx.bezierCurveTo(m - n * .28, n * .5, m - n * .1, n * .35, m, n * .1); ctx.fill(); ctx.restore(); break;
      case 'swirl': { ctx.save(); ctx.translate(m, m); for (let k = 0; k < 3; k++) { ctx.rotate(Math.PI * 2 / 3); const p = new Path2D(); for (let i = 0; i <= 60; i++) { const t = i / 60, a = t * Math.PI * 1.6, rr = n * .06 + t * n * .38; i ? p.lineTo(Math.cos(a) * rr, Math.sin(a) * rr) : p.moveTo(Math.cos(a) * rr, Math.sin(a) * rr); } glowStroke(ctx, p, 6 * S, 10 * S, .9); } ctx.restore(); break; }
      case 'feather': { ctx.save(); ctx.translate(m, m); ctx.rotate(.5); ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.moveTo(0, -n * .44); ctx.bezierCurveTo(n * .16, -n * .2, n * .12, n * .2, 0, n * .36); ctx.bezierCurveTo(-n * .12, n * .2, -n * .16, -n * .2, 0, -n * .44); ctx.fill(); ctx.globalCompositeOperation = 'destination-out'; ctx.lineWidth = 2 * S; for (let i = -6; i < 7; i++) { ctx.beginPath(); ctx.moveTo(0, i * n * .05); ctx.lineTo((i % 2 ? 1 : -1) * n * .2, i * n * .05 - n * .06); ctx.stroke(); } ctx.restore(); break; }
      case 'confetti': for (let i = 0; i < 14; i++) { ctx.save(); ctx.translate(n * (.15 + r() * .7), n * (.15 + r() * .7)); ctx.rotate(r() * 6.3); ctx.fillStyle = `rgba(255,255,255,${.6 + r() * .4})`; ctx.fillRect(-n * .035, -n * .015, n * .07, n * .03); ctx.restore(); } break;
      case 'heart_glow': ctx.save(); ctx.translate(n * .08, n * .1); ctx.scale(n / 120, n / 120); ctx.shadowColor = '#fff'; ctx.shadowBlur = 14; ctx.fillStyle = '#fff'; ctx.fill(ICONS.heart()[0][0]); ctx.restore(); break;
      case 'wisp': { ctx.save(); ctx.shadowColor = '#fff'; ctx.shadowBlur = 22 * S; const gr = ctx.createLinearGradient(0, n * .1, 0, n * .9); gr.addColorStop(0, 'rgba(255,255,255,0)'); gr.addColorStop(.6, 'rgba(255,255,255,.75)'); gr.addColorStop(1, 'rgba(255,255,255,1)');
        ctx.fillStyle = gr; ctx.beginPath(); ctx.moveTo(m, n * .08); ctx.bezierCurveTo(m + n * .22, n * .35, m + n * .2, n * .62, m + n * .16, n * .74); ctx.arc(m, n * .74, n * .16, 0, Math.PI); ctx.bezierCurveTo(m - n * .2, n * .6, m - n * .06, n * .4, m, n * .08); ctx.fill(); ctx.restore(); radial(ctx, m, n * .74, n * .14, [[0, 1], [1, 0]]); break; }
      default: throw new Error('Unknown VFX texture ' + kind);
    }
    return c;
  }
  const VFX_STRIPS = ['trail', 'trail_sharp', 'beam_energy', 'beam_lightning', 'beam_chain', 'beam_wave'];
  function vfxStrip(kind, w = 512, h = 128, seed = 3) {
    const c = mkCanvas(w, h), ctx = c.getContext('2d');
    if (kind === 'trail' || kind === 'trail_sharp') {
      const nz = noiseField(w, h, 6, 4, seed), a = new Float32Array(w * h);
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { const u = x / w, v = (y / h - .5) / (kind === 'trail' ? .26 : .12); a[y * w + x] = Math.exp(-v * v) * (1 - u) ** 1.2 * (kind === 'trail' ? (.6 + .4 * nz[y * w + x]) : 1); }
      putAlpha(ctx, a, w, h);
    } else if (kind === 'beam_energy' || kind === 'beam_wave') {
      const p = new Path2D(); for (let x = 0; x <= w; x += 4) { const y = h / 2 + Math.sin(x / w * Math.PI * 2 * (kind === 'beam_wave' ? 2 : 3)) * h * .2; x ? p.lineTo(x, y) : p.moveTo(x, y); }
      const gr = ctx.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, 'rgba(255,255,255,0)'); gr.addColorStop(.5, 'rgba(255,255,255,.45)'); gr.addColorStop(1, 'rgba(255,255,255,0)'); ctx.fillStyle = gr; ctx.fillRect(0, 0, w, h);
      glowStroke(ctx, p, 7, 12);
    } else if (kind === 'beam_lightning') {
      const r = rng(seed); const p = new Path2D(); let y = h / 2; p.moveTo(0, y); for (let x = 8; x <= w; x += 8) { y = clamp(y + (r() - .5) * h * .35, h * .15, h * .85); p.lineTo(x, y); } p.lineTo(w, h / 2);
      glowStroke(ctx, p, 3, 10);
    } else if (kind === 'beam_chain') {
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 9; for (let x = 0; x < w; x += 64) { ctx.beginPath(); ctx.ellipse(x + 32, h / 2, 26, 15, 0, 0, 7); ctx.stroke(); } ctx.fillStyle = '#fff'; for (let x = 32; x < w; x += 64) ctx.fillRect(x + 22, h / 2 - 4, 22, 8);
    } else throw new Error('Unknown strip ' + kind);
    return c;
  }
  const VFX_FLIPBOOKS = { smoke_puff: 4, explosion: 4, impact_burst: 4, fire_loop: 4, sparkle: 2, portal_swirl: 4, splash: 4, electric_burst: 4 };
  function flipbook(kind, grid, seed = 5) {
    const size = 1024, cell = size / grid, pad = Math.max(8, Math.round(cell / 24)), inner = cell - 2 * pad;
    const c = mkCanvas(size, size), ctx = c.getContext('2d'), frames = grid * grid, m = inner / 2;
    const base = noiseField(inner, inner, 4, 5, seed), fine = noiseField(inner, inner, 8, 4, seed + 3), loop = kind === 'fire_loop' ? noiseField(inner, inner * 2, 5, 4, seed + 1) : null;
    for (let f = 0; f < frames; f++) {
      const t = f / (frames - 1), ox = (f % grid) * cell + pad, oy = Math.floor(f / grid) * cell + pad;
      if (['smoke_puff', 'explosion', 'fire_loop', 'splash'].includes(kind)) {
        const a = new Float32Array(inner * inner), off = Math.floor(f * inner / frames), shift = Math.floor(t * inner * .15);
        for (let y = 0; y < inner; y++) for (let x = 0; x < inner; x++) {
          const dx = (x - m) / m, dy = (y - m) / m, d = Math.hypot(dx, dy), i = y * inner + x; let v = 0;
          if (kind === 'smoke_puff') { const rad = .45 + .5 * t ** .7, body = Math.exp(-((d / rad) ** 2) * 2.2); v = clamp((base[((y + shift) % inner) * inner + x] * .9 + body * .9 - .55 - .45 * t ** 1.3) * 2.4) * body ** .5 * (1 - t ** 2.5); }
          else if (kind === 'explosion') { const rad = .3 + .62 * t ** .55, b = Math.exp(-((d / rad) ** 2) * 2); const w2 = fine[i] * .6 + base[((y + shift) % inner) * inner + x] * .4; v = clamp((w2 * 1.1 + b * .8 - .78 - .3 * t) * 3.4) * clamp(b * 3) * (1 - t ** 3) + Math.exp(-((d / (.18 + .25 * t)) ** 2)) * (1 - t) ** 1.6; }
          else if (kind === 'fire_loop') { const vv = (dy + 1) / 2, prof = clamp((vv - .06) / .8) ** .6 * .55 * Math.sqrt(clamp((.97 - vv) / .12)), shape = prof > 1e-3 ? clamp(1 - Math.abs(dx) / prof) : 0; const nz = loop[(y + inner - off) * inner + x]; v = clamp((nz * 1.1 + shape * .8 - (1 - vv) * .45 - .62) * 3) * clamp(shape * 2.5); }
          else if (kind === 'splash') { const ang = Math.atan2(dy, dx), crown = (Math.cos(ang * 9 + seed) * .5 + .5) ** 3; const rr = .2 + .6 * t ** .6; v = clamp((1 - Math.abs(d - rr) / (.12 * (1 - t) + .04)) * (.5 + crown) * (dy < .3 ? 1 : .4)) * (1 - t ** 2) + clamp((fine[i] - .6) * 3) * clamp(1 - d) * (1 - t) * .5; }
          a[i] = v;
        }
        putAlpha(ctx, a, inner, inner, ox, oy);
      } else {
        const sub = mkCanvas(inner, inner), sx = sub.getContext('2d'), s = inner / 256;
        if (kind === 'impact_burst') { const rad = inner * (.12 + .38 * t ** .5); sx.translate(m, m); for (let k = 0; k < 14; k++) { const a = k * Math.PI * 2 / 14 + seed; const L = rad * (.75 + ((k * 37) % 10) / 25); sx.save(); sx.rotate(a); const gr = sx.createLinearGradient(rad * .3, 0, L, 0); gr.addColorStop(0, `rgba(255,255,255,0)`); gr.addColorStop(.7, `rgba(255,255,255,${1 - t})`); gr.addColorStop(1, 'rgba(255,255,255,0)'); sx.fillStyle = gr; sx.beginPath(); sx.moveTo(rad * .3, -6 * s * (1 - t * .7)); sx.lineTo(L, 0); sx.lineTo(rad * .3, 6 * s * (1 - t * .7)); sx.fill(); sx.restore(); } sx.setTransform(1, 0, 0, 1, 0, 0); radial(sx, m, m, inner * .2 * (1 - t) + 1, [[0, (1 - t) ** 2], [1, 0]]); }
        else if (kind === 'sparkle') { const k = Math.sin(t * Math.PI); sx.globalAlpha = .3 + .7 * k; const one = vfxSingle('twinkle', inner, seed); sx.translate(m, m); sx.scale(.5 + .5 * k, .5 + .5 * k); sx.rotate(t * .6); sx.drawImage(one, -m, -m); }
        else if (kind === 'portal_swirl') { sx.translate(m, m); sx.rotate(t * Math.PI * 2 / 3 * (frames / (frames - 1))); for (let a = 0; a < 3; a++) { sx.rotate(Math.PI * 2 / 3); const p = new Path2D(); for (let i = 0; i <= 50; i++) { const u = i / 50, ang = u * Math.PI * 1.8, rr = inner * (.05 + u * .4); i ? p.lineTo(Math.cos(ang) * rr, Math.sin(ang) * rr) : p.moveTo(Math.cos(ang) * rr, Math.sin(ang) * rr); } glowStroke(sx, p, 6 * s, 10 * s, .85); } sx.setTransform(1, 0, 0, 1, 0, 0); radial(sx, m, m, inner * .25, [[0, .9], [1, 0]]); }
        else if (kind === 'electric_burst') { const r2 = rng(seed + f * 13); sx.translate(m, m); for (let k = 0; k < 6; k++) { let x = 0, y = 0; const a = r2() * 6.3, L = inner * (.2 + .25 * t); const p = new Path2D(); p.moveTo(0, 0); for (let j = 1; j <= 6; j++) { x = Math.cos(a) * L * j / 6 + (r2() - .5) * inner * .06; y = Math.sin(a) * L * j / 6 + (r2() - .5) * inner * .06; p.lineTo(x, y); } glowStroke(sx, p, 2.5 * s, 8 * s, 1 - t * .8); } sx.setTransform(1, 0, 0, 1, 0, 0); radial(sx, m, m, inner * .18, [[0, 1 - t], [1, 0]]); }
        else throw new Error('Unknown flipbook ' + kind);
        ctx.drawImage(sub, ox, oy);
      }
    }
    return c;
  }

  // Particle presets (property names checked in the Roblox API reference)
  const VFX_PRESETS = {
    hit_sparks: { tex: 'spark', color: '#ffd166', emit: 18, lifetime: [.18, .35], speed: [28, 45], spread: [180, 180], size: [[0, .35], [1, 0]], transp: [[0, 0], [.7, .1], [1, 1]], light: 1, drag: 6, orient: 'VelocityParallel', accel: [0, -30, 0] },
    hit_star: { tex: 'hit_star', color: '#ffffff', emit: 1, lifetime: [.15, .15], speed: [0, 0], size: [[0, 1], [.3, 3.2], [1, 2.4]], transp: [[0, 0], [1, 1]], light: 1, rot: [0, 360] },
    impact_ring: { tex: 'ring', color: '#ffffff', emit: 1, lifetime: [.25, .25], speed: [0, 0], size: [[0, .5], [1, 6]], transp: [[0, .1], [1, 1]], light: 1 },
    shockwave: { tex: 'shockwave', color: '#bfe6ff', emit: 1, lifetime: [.4, .4], speed: [0, 0], size: [[0, 1], [1, 14]], transp: [[0, .2], [1, 1]], light: .8 },
    impact_burst: { tex: 'impact_burst', color: '#fff3c4', emit: 1, lifetime: [.35, .35], speed: [0, 0], size: [[0, 4], [1, 7]], transp: [[0, 0], [1, .4]], light: 1, flip: ['Grid4x4', 'OneShot'], rot: [0, 360] },
    burst_glow: { tex: 'glow', color: '#ffe28a', emit: 2, lifetime: [.15, .2], speed: [0, 0], size: [[0, 2], [1, 5]], transp: [[0, .2], [1, 1]], light: 1 },
    explosion: { tex: 'explosion', color: ['#fff3b0', '#ff9a2e', '#5a4a44'], emit: 6, lifetime: [.7, 1], speed: [4, 10], spread: [180, 180], size: [[0, 3], [1, 9]], transp: [[0, 0], [.8, .2], [1, 1]], light: .6, flip: ['Grid4x4', 'OneShot'], rot: [0, 360] },
    smoke_puff: { tex: 'smoke_puff', color: '#cfcfcf', emit: 8, lifetime: [1, 1.6], speed: [2, 5], spread: [180, 180], size: [[0, 2], [1, 6]], transp: [[0, .3], [1, 1]], light: 0, flip: ['Grid4x4', 'OneShot'], rot: [0, 360], rotspeed: [-30, 30], accel: [0, 2, 0] },
    ambient_smoke: { tex: 'smoke', color: '#9aa0a6', rate: 4, lifetime: [3, 5], speed: [.5, 1.5], spread: [20, 20], size: [[0, 3], [1, 8]], transp: [[0, 1], [.2, .6], [1, 1]], light: 0, rot: [0, 360], rotspeed: [-10, 10] },
    fire: { tex: 'fire_loop', color: ['#fff1a8', '#ff8a1f', '#ff3d1f'], rate: 14, lifetime: [.6, .9], speed: [2, 4], spread: [10, 10], size: [[0, 2.2], [1, .6]], transp: [[0, .15], [.8, .35], [1, 1]], light: 1, flip: ['Grid4x4', 'Loop'], framerate: [18, 24], accel: [0, 4, 0] },
    sparkle_aura: { tex: 'sparkle', color: '#fff6c2', rate: 6, lifetime: [.6, 1], speed: [.5, 1.5], spread: [180, 180], size: [[0, .3], [.5, .7], [1, 0]], transp: [[0, 0], [1, 1]], light: 1, flip: ['Grid2x2', 'OneShot'] },
    magic_circle: { tex: 'magic_circle', color: '#9b7bff', emit: 1, lifetime: [1.2, 1.2], speed: [0, 0], size: [[0, 0], [.15, 8], [1, 8.5]], transp: [[0, .2], [.75, .3], [1, 1]], light: 1, orient: 'VelocityPerpendicular', rotspeed: [40, 40] },
    portal: { tex: 'portal_swirl', color: ['#c38bff', '#5f7bff'], rate: 2, lifetime: [1.2, 1.2], speed: [0, 0], size: [[0, 6], [1, 6]], transp: [[0, 1], [.2, .1], [.8, .1], [1, 1]], light: 1, flip: ['Grid4x4', 'Loop'], framerate: [16, 16] },
    heal: { tex: 'heal_plus', color: '#6dff8a', rate: 8, lifetime: [.8, 1.2], speed: [2, 4], spread: [25, 25], size: [[0, .6], [1, .2]], transp: [[0, 0], [1, 1]], light: 1, accel: [0, 3, 0] },
    slash: { tex: 'slash', color: '#e8f6ff', emit: 1, lifetime: [.18, .18], speed: [0, 0], size: [[0, 5], [1, 6]], transp: [[0, 0], [1, 1]], light: 1, rot: [-20, 20] },
    lightning: { tex: 'lightning', color: '#9fdcff', emit: 3, lifetime: [.08, .14], speed: [0, 0], size: [[0, 6], [1, 6]], transp: [[0, 0], [1, 1]], light: 1, rot: [0, 360] },
    electric: { tex: 'electric_burst', color: '#8fd8ff', emit: 1, lifetime: [.3, .3], speed: [0, 0], size: [[0, 4], [1, 6]], transp: [[0, 0], [1, .5]], light: 1, flip: ['Grid4x4', 'OneShot'], rot: [0, 360] },
    splash: { tex: 'splash', color: '#bfe9ff', emit: 1, lifetime: [.5, .5], speed: [0, 0], size: [[0, 3], [1, 6]], transp: [[0, 0], [1, .4]], light: .3, flip: ['Grid4x4', 'OneShot'], orient: 'FacingCameraWorldUp' },
    dust_kick: { tex: 'dust', color: '#c9b48f', emit: 10, lifetime: [.5, .9], speed: [3, 7], spread: [70, 70], size: [[0, 1], [1, 3]], transp: [[0, .4], [1, 1]], light: 0, drag: 4, rot: [0, 360] },
    coin_twinkle: { tex: 'twinkle', color: '#ffe066', rate: 3, lifetime: [.4, .6], speed: [0, 0], spread: [180, 180], size: [[0, 0], [.5, .8], [1, 0]], transp: [[0, 0], [1, 1]], light: 1, rotspeed: [-90, 90] },
    level_up: { tex: 'star', color: ['#fff3a0', '#ffd23f'], emit: 24, lifetime: [.8, 1.2], speed: [6, 12], spread: [35, 35], size: [[0, .8], [1, 0]], transp: [[0, 0], [1, 1]], light: 1, drag: 2, accel: [0, -6, 0], rotspeed: [-180, 180] },
    confetti: { tex: 'confetti', color: ['#ff5f6d', '#ffd23f', '#3fd2ff', '#7be36b'], emit: 30, lifetime: [1.5, 2.5], speed: [12, 20], spread: [40, 40], size: [[0, 1.2], [1, 1.2]], transp: [[0, 0], [.85, 0], [1, 1]], light: 0, drag: 1.5, accel: [0, -18, 0], rot: [0, 360], rotspeed: [-360, 360] },
    snow: { tex: 'snowflake', color: '#ffffff', rate: 12, lifetime: [6, 9], speed: [2, 3], spread: [10, 10], size: [[0, .4], [1, .4]], transp: [[0, 1], [.1, .1], [.9, .1], [1, 1]], light: .3, rotspeed: [-40, 40] },
    leaves: { tex: 'leaf', color: ['#7bd36b', '#e0b24a'], rate: 3, lifetime: [5, 8], speed: [1, 2], spread: [45, 45], size: [[0, .7], [1, .7]], transp: [[0, 1], [.1, 0], [.9, 0], [1, 1]], light: 0, rot: [0, 360], rotspeed: [-60, 60], accel: [1, -2, 0] },
    bubbles: { tex: 'bubble', color: '#cfefff', rate: 6, lifetime: [2, 3], speed: [2, 4], spread: [15, 15], size: [[0, .3], [1, .6]], transp: [[0, .2], [.9, .3], [1, 1]], light: .4, accel: [0, 1, 0] },
    ghost_wisp: { tex: 'wisp', color: '#b8c8ff', rate: 2, lifetime: [2, 3], speed: [1, 2], spread: [30, 30], size: [[0, 1.5], [1, 3]], transp: [[0, 1], [.3, .4], [1, 1]], light: 1, accel: [0, 1.5, 0] },
    hearts: { tex: 'heart_glow', color: '#ff7a9a', rate: 4, lifetime: [1, 1.5], speed: [2, 3], spread: [25, 25], size: [[0, .6], [1, .2]], transp: [[0, 0], [1, 1]], light: 1, accel: [0, 2, 0] },
  };

  // ---------------------------------------------------------------- backdrops (16:9)
  const BACKDROPS = ['burst', 'clouds', 'space', 'dungeon', 'sparkles', 'stripes', 'grid', 'sunset'];
  function backdrop(kind, pal, w, h, seed = 9) {
    const c = mkCanvas(w, h), ctx = c.getContext('2d'), cx = w / 2, cy = h * .55, R = Math.hypot(w, h) * .6, r = rng(seed);
    const prim = hex(pal.primary), sec = hex(pal.secondary), acc = hex(pal.accent), p2 = hex(pal.panel2);
    const dark = ['space', 'dungeon', 'grid'].includes(kind);
    const inner = dark ? shade(prim, -.62) : kind === 'sunset' ? shade(sec, .2) : shade(prim, .25), outer = dark ? [.02, .02, .04] : kind === 'sunset' ? shade(prim, -.45) : shade(p2, -.35);
    let gr = kind === 'sunset' ? ctx.createLinearGradient(0, 0, 0, h) : ctx.createRadialGradient(cx, cy, 0, cx, cy, R);
    if (kind === 'sunset') { gr.addColorStop(0, css(outer)); gr.addColorStop(.6, css(inner)); gr.addColorStop(1, css(shade(acc, .2))); } else { gr.addColorStop(0, css(inner)); gr.addColorStop(1, css(outer)); }
    ctx.fillStyle = gr; ctx.fillRect(0, 0, w, h);
    if (kind === 'burst' || kind === 'sparkles' || kind === 'clouds') {
      ctx.save(); ctx.translate(cx, cy); ctx.fillStyle = 'rgba(255,255,255,.09)';
      for (let i = 0; i < 18; i++) { ctx.rotate(Math.PI / 9); ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(R, -R * .09); ctx.lineTo(R, R * .09); ctx.fill(); } ctx.restore();
      const g2 = ctx.createRadialGradient(cx, cy, 0, cx, cy, h * .45); g2.addColorStop(0, css(shade(prim, .65), .7)); g2.addColorStop(1, css(shade(prim, .65), 0)); ctx.fillStyle = g2; ctx.fillRect(0, 0, w, h);
    }
    if (kind === 'clouds' || kind === 'sunset') {
      const cw = Math.round(w / 4), ch = Math.round(h / 4), nz = noiseField(cw, ch, 5, 5, seed), a = new Float32Array(cw * ch);
      for (let y = 0; y < ch; y++) for (let x = 0; x < cw; x++) a[y * cw + x] = clamp((nz[y * cw + x] - .45) * 4) * clamp((y / ch - (kind === 'sunset' ? .55 : .62)) / .22) * .95;
      const t = mkCanvas(cw, ch); putAlpha(t.getContext('2d'), a, cw, ch, 0, 0, kind === 'sunset' ? [255, 220, 200] : [255, 255, 255]); ctx.imageSmoothingQuality = 'high'; ctx.drawImage(t, 0, 0, w, h);
      if (kind === 'sunset') { const s = ctx.createRadialGradient(cx, h * .58, 0, cx, h * .58, h * .2); s.addColorStop(0, 'rgba(255,250,220,1)'); s.addColorStop(.5, css(shade(acc, .4), .9)); s.addColorStop(1, css(acc, 0)); ctx.fillStyle = s; ctx.beginPath(); ctx.arc(cx, h * .58, h * .2, 0, 7); ctx.fill(); }
    }
    if (kind === 'space') {
      const cw = Math.round(w / 4), ch = Math.round(h / 4);
      for (const [col, sd, k] of [[sec, seed, .5], [prim, seed + 11, .4]]) { const nz = noiseField(cw, ch, 3, 5, sd), a = new Float32Array(cw * ch); for (let i = 0; i < a.length; i++) a[i] = clamp((nz[i] - .5) * 3) * k; const t = mkCanvas(cw, ch); putAlpha(t.getContext('2d'), a, cw, ch, 0, 0, shade(col, -.1).map(v => v * 255)); ctx.drawImage(t, 0, 0, w, h); }
      for (let i = 0; i < 320; i++) { const s = r() * 1.8 + .4; ctx.fillStyle = `rgba(255,255,255,${.4 + r() * .6})`; ctx.beginPath(); ctx.arc(r() * w, r() * h, s, 0, 7); ctx.fill(); }
    }
    if (kind === 'dungeon') {
      const cw = Math.round(w / 4), ch = Math.round(h / 4), nz = noiseField(cw, ch, 4, 5, seed), a = new Float32Array(cw * ch);
      for (let y = 0; y < ch; y++) for (let x = 0; x < cw; x++) a[y * cw + x] = clamp((nz[y * cw + x] - .5) * 2) * .4 * clamp(y / ch * 1.5 - .3);
      const t = mkCanvas(cw, ch); putAlpha(t.getContext('2d'), a, cw, ch, 0, 0, [190, 190, 205]); ctx.drawImage(t, 0, 0, w, h);
    }
    if (kind === 'stripes') { ctx.save(); ctx.fillStyle = 'rgba(255,255,255,.08)'; for (let x = -h; x < w; x += 90) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x + 45, 0); ctx.lineTo(x + 45 + h, h); ctx.lineTo(x + h, h); ctx.fill(); } ctx.restore(); }
    if (kind === 'grid') { ctx.save(); ctx.strokeStyle = css(prim, .35); ctx.lineWidth = 2; const hz = h * .55;
      for (let i = -20; i <= 20; i++) { ctx.beginPath(); ctx.moveTo(cx + i * 40, hz); ctx.lineTo(cx + i * 260, h); ctx.stroke(); }
      for (let k = 0; k < 14; k++) { const y = hz + (h - hz) * (k / 14) ** 1.8; ctx.globalAlpha = .2 + .8 * k / 14; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }
      ctx.restore(); const hg = ctx.createLinearGradient(0, hz - 60, 0, hz + 10); hg.addColorStop(0, css(prim, 0)); hg.addColorStop(1, css(prim, .45)); ctx.fillStyle = hg; ctx.fillRect(0, hz - 60, w, 70); }
    if (kind === 'sparkles' || kind === 'burst') { for (let i = 0; i < 26; i++) { const s = 6 + r() * 14, x = r() * w, y = r() * h * .85; ctx.save(); ctx.globalAlpha = .4 + r() * .5; ctx.translate(x, y); ctx.drawImage(vfxSingle('twinkle', 64, i), -s * 2, -s * 2, s * 4, s * 4); ctx.restore(); } }
    const v = ctx.createRadialGradient(cx, h / 2, Math.min(w, h) * .35, cx, h / 2, Math.hypot(w, h) * .62); v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(0,0,0,.55)'); ctx.fillStyle = v; ctx.fillRect(0, 0, w, h);
    return c;
  }

  // ---------------------------------------------------------------- special UI shapes
  function custom(kind, w, h, base, st, extra = {}) {
    const c = mkCanvas(w, h), ctx = c.getContext('2d'), dark = shade(base, -Math.max(.5, st.odark)), ow = Math.max(3, st.ow);
    const fillBody = (p, b = base) => { const gr = ctx.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, css(shade(b, st.grad || .15))); gr.addColorStop(1, css(shade(b, -(st.grad || .15) * .6))); ctx.fillStyle = gr; ctx.fill(p); };
    const outline = p => { ctx.save(); if (st.shadow) { ctx.shadowColor = `rgba(0,0,0,${st.shadow})`; ctx.shadowBlur = 8; ctx.shadowOffsetY = 4; } ctx.lineJoin = 'round'; ctx.lineWidth = ow * 2; ctx.strokeStyle = css(dark); ctx.stroke(p); ctx.restore(); };
    const gloss = p => { if (!st.gloss) return; ctx.save(); ctx.clip(p); const gl = ctx.createLinearGradient(0, 0, 0, h * .55); gl.addColorStop(0, `rgba(255,255,255,${st.gloss})`); gl.addColorStop(1, 'rgba(255,255,255,0)'); ctx.fillStyle = gl; ctx.fillRect(0, 0, w, h * .55); ctx.restore(); };
    let p, slice = null;
    if (kind === 'ribbon') { // banner with folded tails; 9-slice stretches the middle
      const m = 14, tail = 36, y0 = 18, y1 = h - 22;
      const tails = P(q => { poly(q, [[m, y0 + 14], [m + tail + 10, y0 + 14], [m + tail + 10, y1 + 10], [m, y1 + 10], [m + 16, (y0 + y1) / 2 + 12]]); poly(q, [[w - m, y0 + 14], [w - m - tail - 10, y0 + 14], [w - m - tail - 10, y1 + 10], [w - m, y1 + 10], [w - m - 16, (y0 + y1) / 2 + 12]]); });
      p = P(q => q.roundRect(m + tail, y0, w - 2 * (m + tail), y1 - y0, 6));
      outline(tails); fillBody(tails, shade(base, -.3)); outline(p); fillBody(p); gloss(p);
      slice = [m + tail + 14, y0 + 12, w - m - tail - 14, y1 - 12];
    } else if (kind === 'bubble') { // speech bubble, tail inside the bottom-left corner zone
      const m = 12, r = 28, tailH = 26;
      p = P(q => { q.roundRect(m, m, w - 2 * m, h - 2 * m - tailH, r); q.moveTo(m + 30, h - m - tailH - 2); q.lineTo(m + 26, h - m); q.lineTo(m + 62, h - m - tailH - 2); q.closePath(); });
      outline(p); fillBody(p); gloss(p);
      slice = [m + 70, m + r + 4, w - m - r - 4, h - m - tailH - r - 4];
    } else if (kind === 'price_tag') {
      const m = 12, nt = 22;
      p = P(q => { poly(q, [[m + nt, m], [w - m - 8, m], [w - m, m + 8], [w - m, h - m - 8], [w - m - 8, h - m], [m + nt, h - m], [m, h / 2]]); });
      outline(p); fillBody(p); gloss(p);
      ctx.save(); ctx.globalCompositeOperation = 'destination-out'; ctx.beginPath(); ctx.arc(m + nt + 2, h / 2, 6, 0, 7); ctx.fill(); ctx.restore();
      ctx.lineWidth = 3; ctx.strokeStyle = css(dark); ctx.beginPath(); ctx.arc(m + nt + 2, h / 2, 7.5, 0, 7); ctx.stroke();
      slice = [m + nt + 18, m + 12, w - m - 14, h - m - 12];
    } else if (kind === 'corner_ribbon') { // diagonal ribbon for a card's top-right corner
      p = P(q => poly(q, [[w * .28, 0], [w * .56, 0], [w, h * .44], [w, h * .72]]));
      outline(p); fillBody(p); gloss(p);
    } else if (kind === 'selection') { // gamepad selection ring (used as SelectionImageObject)
      p = P(q => q.roundRect(10, 10, w - 20, h - 20, Math.min(w, h) * .22));
      ctx.save(); ctx.shadowColor = css(base); ctx.shadowBlur = 14; ctx.lineWidth = 7; ctx.strokeStyle = css(shade(base, .4)); ctx.stroke(p); ctx.restore(); ctx.lineWidth = 3; ctx.strokeStyle = '#ffffff'; ctx.stroke(p);
      const r = Math.min(w, h) * .22 + 10; slice = [r + 4, r + 4, w - r - 4, h - r - 4];
    } else if (kind === 'glyph') { // a standalone white glyph with dark outline
      glyph(ctx, extra.glyph, w / 2, h / 2, w * .32, dark);
    } else throw new Error('Unknown shape ' + kind);
    return { canvas: c, slice };
  }

  // ---------------------------------------------------------------- the kit
  // Upload packs: only what a screen type needs (fewer uploads, faster install). 'full' is everything.
  const BASE_PACK = ['button_primary', 'button_success', 'button_danger', 'icon_close', 'panel', 'header', 'selection', 'toast', 'item_coin'];
  const PACKS = {
    full: [],
    essentials: [...BASE_PACK, 'button_secondary', 'icon_back', 'icon_plus', 'panel_inner', 'card', 'ribbon', 'slot_', 'tab_', 'progress_track', 'progress_fill', 'xp_fill', 'pill', 'price_tag', 'badge', 'toggle_', 'tooltip', 'glyph_down', 'rays', 'glow', 'item_gem', 'item_star', 'item_lock', 'item_gift'],
    hud: [...BASE_PACK, 'button_secondary', 'icon_plus', 'pill', 'badge', 'progress_track', 'progress_fill', 'xp_fill', 'hp_fill', 'mana_fill', 'item_gem', 'item_heart', 'item_bolt', 'item_star', 'item_cart', 'item_bag', 'item_gear', 'rays', 'glow'],
    shop: [...BASE_PACK, 'button_secondary', 'icon_back', 'icon_plus', 'card', 'ribbon', 'slot_', 'tab_', 'pill', 'price_tag', 'corner_ribbon', 'badge', 'item_gem', 'item_cart', 'item_gift', 'item_lock', 'item_star', 'item_ticket', 'rays', 'glow'],
    inventory: [...BASE_PACK, 'button_secondary', 'icon_back', 'panel_inner', 'slot_', 'tab_', 'tooltip', 'input', 'badge', 'item_lock', 'item_bag', 'item_star'],
    settings: [...BASE_PACK, 'button_secondary', 'icon_back', 'panel_inner', 'toggle_', 'checkbox_', 'radio_', 'slider_', 'input', 'tab_', 'divider', 'glyph_down', 'item_gear'],
    leaderboard: [...BASE_PACK, 'leaderboard_', 'tab_', 'pill', 'item_trophy', 'item_crown', 'item_star'],
    dialogue: [...BASE_PACK, 'button_secondary', 'icon_next', 'bubble', 'ribbon', 'item_scroll', 'item_star'],
    rewards: [...BASE_PACK, 'button_secondary', 'ribbon', 'rays', 'glow', 'slot_', 'pill', 'item_gem', 'item_gift', 'item_star', 'item_chest', 'item_egg', 'item_trophy', 'item_crown'],
  };
  function resolveStyle(args, refPalette) {
    const style = String(args.style || 'simulator').toLowerCase();
    if (!STYLES[style]) throw new Error('style is one of ' + Object.keys(STYLES).join(', '));
    const st = { ...STYLES[style] }, pal = { ...PALETTES[style] };
    if (refPalette) for (const k of ['primary', 'secondary', 'panel', 'panel2', 'accent']) if (refPalette[k]) pal[k] = refPalette[k];
    for (const [k, v] of Object.entries(args.colors || {})) if (k in pal) { hex(v); pal[k] = v; }
    const tw = args.tweaks || {};
    for (const k of ['radius', 'gloss', 'shadow', 'glow']) if (typeof tw[k] === 'number') st[k] = clamp(tw[k]);
    for (const k of ['ow', 'lip']) if (typeof tw[k] === 'number') st[k] = Math.round(clamp(tw[k], 0, 16));
    return { style, st, pal };
  }
  function buildKit(args, refPalette) {
    const { style, st, pal } = resolveStyle(args, refPalette), C = {};
    for (const [k, v] of Object.entries(pal)) C[k] = hex(v);
    const out = {}, add = (k, draw, meta) => { out[k] = { draw, meta }; };
    const pst = { ...st, lip: Math.min(st.lip, 6), gloss: st.gloss * .35, radius: st.radius > .3 ? st.radius * .55 : st.radius };
    for (const v of ['primary', 'secondary', 'success', 'danger']) for (const s of ['normal', 'hover', 'pressed', 'disabled']) add(`button_${v}_${s}`, () => (element({ w: 240, h: 104, base: C[v], st, state: s })), { kind: 'button', variant: v, state: s });
    for (const [n, b, gl] of [['close', 'danger', 'x'], ['back', 'secondary', 'back'], ['plus', 'success', 'plus'], ['minus', 'danger', 'minus'], ['next', 'primary', 'arrow'], ['confirm', 'success', 'check'], ['help', 'primary', 'question']]) for (const s of ['normal', 'hover', 'pressed']) add(`icon_${n}_${s}`, () => (element({ w: 112, h: 112, base: C[b], st, shape: 'circle', state: s, glyph: gl })), { kind: 'icon_button', state: s });
    add('panel', () => (element({ w: 256, h: 256, base: C.panel, st: pst })), { kind: 'panel' });
    add('panel_inner', () => (element({ w: 192, h: 192, base: C.panel2, st: { ...pst, lip: 0 }, inset: true })), { kind: 'panel_inner' });
    add('card', () => (element({ w: 224, h: 256, base: shade(C.panel, .08), st: { ...pst, lip: Math.min(st.lip, 5) } })), { kind: 'card' });
    add('header', () => (element({ w: 256, h: 96, base: C.primary, st: { ...st, radius: Math.min(.5, st.radius) } })), { kind: 'header' });
    add('ribbon', () => (custom('ribbon', 384, 112, C.primary, st)), { kind: 'ribbon' });
    const sst = { ...st, lip: 0, radius: Math.min(st.radius, .22) };
    for (const [rk, col] of Object.entries(RARITY)) add(`slot_${rk}`, () => (element({ w: 128, h: 128, base: C.panel2, st: sst, inset: true, trim: col })), { kind: 'slot', rarity: rk });
    add('slot_selected', () => (element({ w: 128, h: 128, base: C.panel2, st: sst, inset: true, trim: C.accent })), { kind: 'slot', rarity: 'selected' });
    const tst = { ...st, lip: Math.min(st.lip, 5) };
    add('tab_active', () => (element({ w: 208, h: 88, base: C.primary, st: tst })), { kind: 'tab', state: 'active' });
    add('tab_inactive', () => (element({ w: 208, h: 88, base: shade(C.panel2, .1), st: tst, state: 'disabled' })), { kind: 'tab', state: 'inactive' });
    const bar = { ...st, lip: 0 };
    let track; const getTrack = () => track || (track = element({ w: 256, h: 56, base: C.panel2, st: bar, shape: 'pill', inset: true })); add('progress_track', () => (getTrack()), { kind: 'progress', part: 'track' });
    for (const [k, col] of [['progress_fill', C.success], ['xp_fill', C.accent], ['hp_fill', C.danger], ['mana_fill', hex('#3f8cff')]]) add(k, () => (element({ w: 256, h: 56, base: col, st: bar, shape: 'pill', margin: getTrack().margin })), { kind: 'progress', part: 'fill' });
    add('pill', () => (element({ w: 232, h: 80, base: C.panel2, st: bar, shape: 'pill' })), { kind: 'pill' });
    add('price_tag', () => (custom('price_tag', 208, 80, C.success, st)), { kind: 'price_tag' });
    add('badge', () => (element({ w: 72, h: 72, base: C.danger, st: { ...st, lip: 0 }, shape: 'circle' })), { kind: 'badge' });
    add('toggle_on', () => (element({ w: 136, h: 72, base: C.success, st: bar, shape: 'pill' })), { kind: 'toggle', state: 'on' });
    add('toggle_off', () => (element({ w: 136, h: 72, base: desat(C.panel2, .6), st: bar, shape: 'pill', inset: true })), { kind: 'toggle', state: 'off' });
    add('toggle_knob', () => (element({ w: 72, h: 72, base: [1, 1, 1], st: { ...st, lip: 0, odark: .35 }, shape: 'circle' })), { kind: 'toggle', state: 'knob' });
    add('checkbox_off', () => (element({ w: 72, h: 72, base: shade(C.panel2, .15), st: { ...sst, radius: .22 }, inset: true })), { kind: 'checkbox', state: 'off' });
    add('checkbox_on', () => (element({ w: 72, h: 72, base: C.success, st: { ...st, lip: 0, radius: .22 }, glyph: 'check' })), { kind: 'checkbox', state: 'on' });
    add('radio_off', () => (element({ w: 72, h: 72, base: shade(C.panel2, .15), st: sst, shape: 'circle', inset: true })), { kind: 'radio', state: 'off' });
    add('radio_on', () => (element({ w: 72, h: 72, base: C.primary, st: { ...st, lip: 0 }, shape: 'circle' })), { kind: 'radio', state: 'on' });
    add('slider_track', () => (element({ w: 256, h: 40, base: C.panel2, st: bar, shape: 'pill', inset: true })), { kind: 'slider', part: 'track' });
    add('slider_fill', () => (element({ w: 256, h: 40, base: C.primary, st: bar, shape: 'pill' })), { kind: 'slider', part: 'fill' });
    add('slider_knob', () => (element({ w: 72, h: 72, base: [1, 1, 1], st: { ...st, lip: 0, odark: .35 }, shape: 'circle' })), { kind: 'slider', part: 'knob' });
    add('input', () => (element({ w: 256, h: 80, base: shade(C.panel2, .35), st: { ...sst, radius: Math.min(.3, st.radius) }, inset: true })), { kind: 'input' });
    add('scroll_track', () => (element({ w: 32, h: 160, base: C.panel2, st: bar, shape: 'pill', inset: true, margin: 4 })), { kind: 'scroll', part: 'track' });
    add('scroll_thumb', () => (element({ w: 32, h: 160, base: shade(C.panel, .3), st: { ...bar, ow: 2 }, shape: 'pill', margin: 4 })), { kind: 'scroll', part: 'thumb' });
    add('tooltip', () => (element({ w: 208, h: 104, base: shade(C.panel2, -.1), st: { ...pst, lip: 0 } })), { kind: 'tooltip' });
    add('bubble', () => (custom('bubble', 320, 176, [1, 1, 1], { ...st, grad: .06, gloss: st.gloss * .4, odark: .7 })), { kind: 'bubble' });
    add('toast', () => (element({ w: 320, h: 96, base: shade(C.panel2, -.15), st: { ...pst, lip: 0 }, trim: null })), { kind: 'toast' });
    for (const [k, col] of [['row_gold', hex('#ffc21a')], ['row_silver', hex('#c9d2dc')], ['row_bronze', hex('#d08a4a')], ['row', shade(C.panel2, .12)]]) add(`leaderboard_${k}`, () => (element({ w: 448, h: 88, base: col, st: { ...st, lip: Math.min(st.lip, 4), gloss: st.gloss * .6 } })), { kind: 'leaderboard_row' });
    add('corner_ribbon', () => (custom('corner_ribbon', 128, 128, C.danger, st)), { kind: 'corner_ribbon' });
    add('selection', () => (custom('selection', 128, 128, C.accent, st)), { kind: 'selection' });
    for (const gk of ['down', 'up', 'arrow', 'back', 'check', 'x']) add(`glyph_${gk}`, () => (custom('glyph', 64, 64, C.panel2, st, { glyph: gk })), { kind: 'glyph' });
    add('rays', () => ((() => { const c = mkCanvas(256, 256), x = c.getContext('2d'); x.translate(128, 128); for (let i = 0; i < 16; i++) { x.rotate(Math.PI / 8); const g = x.createLinearGradient(0, 0, 128, 0); g.addColorStop(0, 'rgba(255,255,255,.9)'); g.addColorStop(1, 'rgba(255,255,255,0)'); x.fillStyle = g; x.beginPath(); x.moveTo(0, 0); x.lineTo(128, -16); x.lineTo(128, 16); x.closePath(); x.fill(); } return c; })()), { kind: 'rays' });
    add('glow', () => (vfxSingle('glow', 256, 1)), { kind: 'glow' });
    add('divider', () => (element({ w: 256, h: 16, base: C.accent, st: { ...bar, ow: 0, shadow: 0, gloss: 0 }, shape: 'pill', margin: 2 })), { kind: 'divider' });
    const icons = Array.isArray(args.icons) && args.icons.length ? args.icons : Object.keys(ICON_COLORS);
    for (const k of icons) { if (!ICONS[k]) throw new Error('Unknown icon ' + k + '; choose from ' + Object.keys(ICONS).join(', ')); add(`item_${k}`, () => (icon(k, 128, (args.icon_colors || {})[k], st)), { kind: 'icon' }); }
    let keys = Object.keys(out);
    // Build a complete essentials pack by default. Full and task-specific packs remain explicit.
    const pack = String(args.pack || 'essentials');
    if (!PACKS[pack]) throw new Error('pack is one of ' + Object.keys(PACKS).join(', '));
    if (pack !== 'full' && !(Array.isArray(args.elements) && args.elements.length)) keys = keys.filter(k => PACKS[pack].some(p => k === p || k.startsWith(p + '_') || k.startsWith(p)));
    if (Array.isArray(args.elements) && args.elements.length) { keys = keys.filter(k => args.elements.some(p => k.startsWith(p))); if (!keys.length) throw new Error('No element matched those prefixes.'); }
    // Filter before invoking draw factories. Return the complete requested pack;
    // silently truncating to five buttons breaks downstream UI builders.
    const text = hex(pal.text);
    const theme = { style, pack, palette: pal, font: 'Enum.Font.' + st.font, text: pal.text, textStroke: toHex(shade(C.primary, -.72)), textContrastOnPrimary: +contrast(text, C.primary).toFixed(2), sliceScale: .5, artScale: 2 };
    return { items: Object.fromEntries(keys.map(k => { const r = out[k].draw(); return [k, {canvas: r.canvas || r, slice: r.slice || null, meta: out[k].meta}]; })), theme };
  }

  // ---------------------------------------------------------------- preview sheet + encoding
  function sheet(canvases, bg = '#2a2d38', cols = 8, maxW = 1400, cellMax = 192) {
    const cells = canvases.map(c => { const s = Math.min(1, cellMax / Math.max(c.width, c.height)); return { c, w: Math.round(c.width * s), h: Math.round(c.height * s) }; });
    const cw = Math.max(...cells.map(x => x.w)) + 14, ch = Math.max(...cells.map(x => x.h)) + 14;
    cols = Math.max(1, Math.min(cols, cells.length, Math.floor(maxW / cw) || 1));
    const rows = Math.ceil(cells.length / cols), out = mkCanvas(cols * cw, rows * ch), ctx = out.getContext('2d');
    ctx.fillStyle = bg; ctx.fillRect(0, 0, out.width, out.height);
    cells.forEach((x, i) => ctx.drawImage(x.c, (i % cols) * cw + (cw - x.w) / 2, Math.floor(i / cols) * ch + (ch - x.h) / 2, x.w, x.h));
    return out;
  }
  // PNG encoder with edge bleed: fully transparent pixels next to the art take the art's colour at alpha 1/255,
  // so Roblox's filtering does not pull black into the edges (dark fringes on scaled images).
  const CRC = (() => { const tb = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; tb[n] = c >>> 0; } return tb; })();
  const crc32 = (bytes) => { let c = 0xffffffff; for (let i = 0; i < bytes.length; i++) c = CRC[(c ^ bytes[i]) & 255] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
  function bleed(d, w, h, passes = 3) {
    let filled = new Uint8Array(w * h);
    for (let i = 0; i < w * h; i++) if (d[i * 4 + 3] > 0) filled[i] = 1;
    for (let pass = 0; pass < passes; pass++) {
      const next = filled.slice(), upd = [];
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
        const i = y * w + x; if (filled[i]) continue;
        let r = 0, g2 = 0, b = 0, n = 0;
        for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) { const xx = x + dx, yy = y + dy; if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue; const j = yy * w + xx; if (filled[j]) { r += d[j * 4]; g2 += d[j * 4 + 1]; b += d[j * 4 + 2]; n++; } }
        if (n) { upd.push(i, r / n, g2 / n, b / n); next[i] = 1; }
      }
      for (let k = 0; k < upd.length; k += 4) { const i = upd[k]; d[i * 4] = upd[k + 1]; d[i * 4 + 1] = upd[k + 2]; d[i * 4 + 2] = upd[k + 3]; if (pass < 2) d[i * 4 + 3] = 1; }
      filled = next;
    }
  }
  async function deflate(bytes) {
    const cs = new CompressionStream('deflate'), wr = cs.writable.getWriter(); wr.write(bytes); wr.close();
    return new Uint8Array(await new Response(cs.readable).arrayBuffer());
  }
  async function encodePng(c, cleanEdges) {
    const w = c.width, h = c.height, d = c.getContext('2d').getImageData(0, 0, w, h).data;
    if (cleanEdges) bleed(d, w, h);
    const raw = new Uint8Array((w * 4 + 1) * h);
    for (let y = 0; y < h; y++) { raw[y * (w * 4 + 1)] = 0; raw.set(d.subarray(y * w * 4, (y + 1) * w * 4), y * (w * 4 + 1) + 1); }
    const idat = await deflate(raw), chunks = [];
    const chunk = (type, data) => { const out = new Uint8Array(12 + data.length), dv = new DataView(out.buffer); dv.setUint32(0, data.length); for (let i = 0; i < 4; i++) out[4 + i] = type.charCodeAt(i); out.set(data, 8); dv.setUint32(8 + data.length, crc32(out.subarray(4, 8 + data.length))); chunks.push(out); };
    const hdr = new Uint8Array(13), hv = new DataView(hdr.buffer); hv.setUint32(0, w); hv.setUint32(4, h); hdr[8] = 8; hdr[9] = 6;
    chunk('IHDR', hdr); chunk('IDAT', idat); chunk('IEND', new Uint8Array(0));
    const sig = [137, 80, 78, 71, 13, 10, 26, 10], total = 8 + chunks.reduce((s, x) => s + x.length, 0), png = new Uint8Array(total); png.set(sig, 0); let o = 8; for (const x of chunks) { png.set(x, o); o += x.length; }
    return png;
  }
  async function toBase64(c, cleanEdges = true) {
    let buf;
    if (typeof CompressionStream !== 'undefined') buf = await encodePng(c, cleanEdges);
    else {
      const blob = c.convertToBlob ? await c.convertToBlob({ type: 'image/png' }) : await new Promise((res, rej) => c.toBlob(b => b ? res(b) : rej(new Error('PNG encode failed')), 'image/png'));
      buf = new Uint8Array(await blob.arrayBuffer());
    }
    let s = '';
    for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    return btoa(s);
  }
  async function paletteFromImage(b64) {
    const bytes = Uint8Array.from(atob(b64), ch => ch.charCodeAt(0));
    const bmp = await createImageBitmap(new Blob([bytes]));
    const n = 64, c = mkCanvas(n, n), ctx = c.getContext('2d'); ctx.drawImage(bmp, 0, 0, n, n);
    const d = ctx.getImageData(0, 0, n, n).data, px = [];
    for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 200) px.push([d[i] / 255, d[i + 1] / 255, d[i + 2] / 255]);
    if (px.length < 20) throw new Error('The reference picture has too few solid pixels.');
    const k = 6, r = rng(1); let cent = Array.from({ length: k }, () => px[Math.floor(r() * px.length)].slice()); let lab = new Array(px.length).fill(0);
    for (let it = 0; it < 12; it++) {
      for (let i = 0; i < px.length; i++) { let best = 0, bd = 9; for (let j = 0; j < k; j++) { const dd = (px[i][0] - cent[j][0]) ** 2 + (px[i][1] - cent[j][1]) ** 2 + (px[i][2] - cent[j][2]) ** 2; if (dd < bd) { bd = dd; best = j; } } lab[i] = best; }
      for (let j = 0; j < k; j++) { const mem = px.filter((_, i) => lab[i] === j); if (mem.length) cent[j] = [0, 1, 2].map(q => mem.reduce((s, p) => s + p[q], 0) / mem.length); }
    }
    const counts = cent.map((_, j) => lab.filter(x => x === j).length);
    const order = cent.map((c2, j) => [c2, counts[j]]).sort((a, b) => b[1] - a[1]);
    const sat = c2 => { const [, s, l] = toHsl(c2); return s * (1 - Math.abs(l - .5) * 1.2); };
    const panel = order[0][0], vivid = order.map(x => x[0]).filter(c2 => contrast(c2, panel) > 1.3).sort((a, b) => sat(b) - sat(a));
    const primary = vivid[0] || order[1][0], secondary = vivid.find(c2 => Math.abs(toHsl(c2)[0] - toHsl(primary)[0]) > .08) || shade(primary, .3);
    const accent = order.map(x => x[0]).sort((a, b) => lum(b) * (.3 + sat(b)) - lum(a) * (.3 + sat(a)))[0];
    return { primary: toHex(primary), secondary: toHex(secondary), panel: toHex(panel), panel2: toHex(shade(panel, -.35)), accent: toHex(accent), extracted: order.map(x => toHex(x[0])) };
  }

  // ---------------------------------------------------------------- public: render one set
  async function render(args, refB64) {
    const action = String(args.action || '');
    const name = String(args.name || action || 'forge').replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^[-.]+|[-.]+$/g, '').slice(0, 60) || 'forge';
    let items = {}, manifest = { type: action, name }, previewCanvases = [], bg = '#2a2d38';
    if (action === 'ui_kit') {
      const ref = refB64 ? await paletteFromImage(refB64) : null;
      const kit = buildKit(args, ref);
      items = kit.items; manifest.theme = kit.theme; if (ref) manifest.theme.reference = ref;
    } else if (action === 'vfx') {
      const all = [...VFX_SINGLES, ...VFX_STRIPS, ...Object.keys(VFX_FLIPBOOKS)];
      const want = Array.isArray(args.textures) && args.textures.length ? args.textures : all;
      for (const k of want) if (!all.includes(k)) throw new Error('textures come from: ' + all.join(', '));
      const seed = Number.isInteger(args.seed) ? args.seed : 1;
      for (const k of want) {
        if (VFX_SINGLES.includes(k)) items[k] = { canvas: vfxSingle(k, ['magic_circle', 'rune_ring', 'lightning', 'flare', 'smoke', 'cloud'].includes(k) ? 512 : 256, seed), meta: { kind: 'single' } };
        else if (VFX_STRIPS.includes(k)) items[k] = { canvas: vfxStrip(k, 512, 128, seed + 2), meta: { kind: 'strip' } };
        else items[k] = { canvas: flipbook(k, VFX_FLIPBOOKS[k], seed + 4), meta: { kind: 'flipbook', layout: `Grid${VFX_FLIPBOOKS[k]}x${VFX_FLIPBOOKS[k]}` } };
      }
      manifest.presets = Object.fromEntries(Object.entries(VFX_PRESETS).filter(([, p]) => items[p.tex]));
      bg = '#101219';
    } else if (action === 'backdrop') {
      const { pal } = resolveStyle(args, refB64 ? await paletteFromImage(refB64) : null);
      const kind = String(args.kind || 'burst'); if (!BACKDROPS.includes(kind)) throw new Error('kind is one of ' + BACKDROPS.join(', '));
      const use = args.use === 'ingame' ? 'ingame' : 'thumbnail', [w, h] = use === 'thumbnail' ? [1920, 1080] : [1024, 576];
      items[`${kind}_${use}`] = { canvas: backdrop(kind, pal, w, h, Number.isInteger(args.seed) ? args.seed : 9), meta: { kind: 'backdrop', use } };
      manifest.palette = pal;
    } else throw new Error('Forge renders ui_kit, vfx or backdrop.');
    const files = {}, entries = {};
    for (const [k, it] of Object.entries(items)) { files[k] = await toBase64(it.canvas, action !== 'backdrop'); entries[k] = { size: [it.canvas.width, it.canvas.height], slice: it.slice || null, ...it.meta }; previewCanvases.push(it.canvas); }
    manifest[action === 'vfx' ? 'textures' : action === 'backdrop' ? 'files' : 'elements'] = entries;
    const prev = action === 'backdrop' ? (() => { const c = Object.values(items)[0].canvas, s = mkCanvas(960, Math.round(960 * c.height / c.width)); s.getContext('2d').drawImage(c, 0, 0, s.width, s.height); return s; })() : sheet(previewCanvases, bg, action === 'vfx' ? 7 : 9);
    return { name, manifest, files, preview: await toBase64(prev, false) };
  }


  // ---------------------------------------------------------------- public: draw, store and (optionally) install in one call
  // deps: {callBridge(tool,args,timeout), studioCall(tool,args,timeout), studioReady:boolean, steps:[]}
  async function run(args, deps) {
    const { callBridge, studioCall, studioReady } = deps, steps = deps.steps || [];
        let ref=null;
    if(args.reference_image){ref=JSON.parse(await callBridge("ms_forge",{action:"reference",path:String(args.reference_image)},30000)||'{}').data||null;}
    const drawn=await render(args,ref);
    // Every generation gets its own files and default Studio objects. Reusing a
    // human-readable theme name must never erase an earlier useful set.
    const generation=crypto.randomUUID().replace(/-/g,'').slice(0,12);
    drawn.name=drawn.name.slice(0,45)+'-'+generation;
    steps.push('drawn: '+Object.keys(drawn.files).length+' images');
    const keys=Object.keys(drawn.files),batches=[];let cur={},size=0;
    for(const k of keys){const n=drawn.files[k].length;if(size&&size+n>6e6){batches.push(cur);cur={};size=0;}cur[k]=drawn.files[k];size+=n;}
    batches.push(cur);
    let saved='';
    for(let i=0;i<batches.length;i++){
      const last=i===batches.length-1;
      saved=await callBridge("ms_forge",{action:"save",name:drawn.name,part:batches.length===1?"only":i===0?"first":last?"last":"more",files:batches[i],...(last?{manifest:drawn.manifest,preview:drawn.preview}:{})});
    }
    const brief=JSON.parse(saved||'{}');
    const install=args.install===false?false:(args.install===true||studioReady);
    let installInfo={installed:false,reason:install?'':'install=false or Roblox Studio is not connected; follow next steps by hand'};
    if(install){
      if(!studioReady)throw new Error('install needs Roblox Studio connected (upload_image and execute_luau). Draw with install=false, or connect Studio.');
      const urls=brief.urls||[],amap={};
      for(let i=0;i<urls.length;i+=20){
        const text=await studioCall('upload_image',{imagePaths:urls.slice(i,i+20)});
        const re=/"(https?:\/\/[^"]+)"\s*:\s*"?(?:rbxassetid:\/\/)?(\d+)"?/g;let m;while((m=re.exec(text)))amap[m[1]]='rbxassetid://'+m[2];
      }
      const got=Object.keys(amap).length;steps.push('uploaded: '+got+' of '+urls.length);
      if(!got)throw new Error('upload_image returned no asset ids. Its answer was not understood; upload the urls by hand and call ms_forge action=bind.');
      if(drawn.manifest.type==='backdrop'){
        // Write the uploaded ids into Studio so they can be used (ReplicatedStorage.ForgeBackdrops.<key> = StringValue with the id).
        const rows=Object.entries(amap).map(([u,id])=>{const key=String(u).split('/').pop().replace(/\.png$/,'').replace(/[^A-Za-z0-9_]/g,'');return `do local v = Instance.new("StringValue") v.Name = "${key}" v.Value = "${id}" v.Parent = folder end`;}).join('\n');
        const folderName='ForgeBackdrops_'+generation;
        const code=`local RS = game:GetService("ReplicatedStorage")\nassert(not RS:FindFirstChild("${folderName}"), "Forge generation already exists")\nlocal folder = Instance.new("Folder") folder.Name = "${folderName}" folder:SetAttribute("MultiScriptForge", "${drawn.name}") folder.Parent = RS\n${rows}\nprint("FORGE_INSTALLED")`;
        const out1=await studioCall('execute_luau',{code});
        if(!/FORGE_INSTALLED/.test(out1))throw new Error('writing the backdrop ids did not confirm: '+out1.slice(0,400));
        steps.push('backdrop ids in ReplicatedStorage.'+folderName+' ('+Object.keys(amap).length+')');
        installInfo={installed:true,module:'ReplicatedStorage.'+folderName,assets:amap};
      }
      else{
        const bound=JSON.parse(await callBridge("ms_forge",{action:"bind",name:drawn.name,asset_map:amap})||'{}');
        if(bound.missing?.length)throw new Error('Asset upload is incomplete; '+bound.missing.length+' images have no returned asset id. Saved files are retained; install only after resolving missing uploads.');
        const moduleName=String(args.module||(bound.module+'_'+generation)).replace(/[^A-Za-z0-9_]/g,'')||bound.module+'_'+generation;
        const src=String(bound.source||'');let lvl='';while(src.includes(']'+lvl+']'))lvl+='=';
        const installCode=`local RS = game:GetService("ReplicatedStorage")\nassert(not RS:FindFirstChild("${moduleName}"), "Existing module preserved; choose an unused module name")\nlocal m = Instance.new("ModuleScript") m.Name = "${moduleName}"\nlocal src = [${lvl}[\n${src}\n]${lvl}]\nlocal ok = pcall(function() game:GetService("ScriptEditorService"):UpdateSourceAsync(m, function() return src end) end)\nif not ok then m.Source = src end\nassert(m.Source == src, "Forge source readback differs")\nm:SetAttribute("MultiScriptForge", "${drawn.name}")\nm.Parent = RS\nprint("FORGE_INSTALLED ${moduleName} " .. #m.Source)`;
        const out1=await studioCall('execute_luau',{code:installCode});
        if(!/FORGE_INSTALLED/.test(out1))throw new Error('writing the ModuleScript did not confirm: '+out1.slice(0,400));
        steps.push('installed ReplicatedStorage.'+moduleName+' ('+(bound.bound||0)+' ids bound'+(bound.missing&&bound.missing.length?', '+bound.missing.length+' missing':'')+')');
        installInfo={installed:true,module:'ReplicatedStorage.'+moduleName,bound:bound.bound,missing:bound.missing||[],example:String(bound.example||'').split(bound.module).join(moduleName)};
        if(args.demo===true){
          const demo=drawn.manifest.type==='ui_kit'?
`local SG = game:GetService("StarterGui")
assert(not SG:FindFirstChild("ForgeDemo_${generation}"), "Existing preview preserved")
local fresh = game:GetService("ReplicatedStorage"):WaitForChild("${moduleName}"):Clone()
fresh.Name = "${moduleName}_ForgePreview"
fresh.Parent = game:GetService("ReplicatedStorage")
local Kit = require(fresh)
fresh:Destroy()
local gui = Kit.screen("ForgeDemo_${generation}", {parent = SG})
local function try(f) local ok, e = pcall(f) if not ok then warn("ForgeDemo: " .. tostring(e)) end end
local shop
try(function()
	shop = Kit.modal(gui, {title = "SHOP", ribbon = Kit.Assets.ribbon ~= nil and Kit.Assets.ribbon ~= "", size = UDim2.fromOffset(600, 430)})
	shop.Open(true)
	local grid = Kit.grid(shop.Content, {cellSize = UDim2.fromOffset(150, 190)})
	local rar = {"common", "rare", "epic", "legendary", "mythic", "uncommon"}
	local icons = {"gem", "star", "gift", "egg", "crown", "sword"}
	for i = 1, 6 do Kit.card(grid, {title = "Item " .. i, icon = icons[i], price = i * 150, rarity = rar[i], layoutOrder = i, badge = i == 1 and "NEW" or nil}) end
end)
try(function() Kit.pill(gui, {icon = "coin", text = "12,450", position = UDim2.fromOffset(16, 16), onPlus = function() end}) end)
try(function() Kit.pill(gui, {icon = "gem", text = "320", position = UDim2.fromOffset(200, 16)}) end)
try(function() Kit.button(gui, {text = "PLAY", variant = "success", anchor = Vector2.new(0.5, 1), position = UDim2.new(0.5, 0, 1, -20)}) end)
try(function() Kit.button(gui, {text = "SHOP", icon = "cart", variant = "secondary", anchor = Vector2.new(0, 1), position = UDim2.new(0, 16, 1, -20)}) end)
try(function() Kit.bar(gui, {kind = "xp", value = 0.62, showText = true, anchor = Vector2.new(0.5, 0), position = UDim2.new(0.5, 0, 0, 20), size = UDim2.fromOffset(360, 30)}) end)
print("FORGE_DEMO ok")`:
`assert(not workspace:FindFirstChild("ForgeVFX_Showroom_${generation}"), "Existing showroom preserved")
local fresh = game:GetService("ReplicatedStorage"):WaitForChild("${moduleName}"):Clone()
fresh.Name = "${moduleName}_ForgePreview"
fresh.Parent = game:GetService("ReplicatedStorage")
local VFX = require(fresh)
fresh:Destroy()
local folder = Instance.new("Folder") folder.Name = "ForgeVFX_Showroom_${generation}" folder.Parent = workspace
local cam = workspace.CurrentCamera
local origin = cam and (cam.CFrame.Position + cam.CFrame.LookVector * 40) or Vector3.new(0, 10, 0)
local i = 0
for name, p in pairs(VFX.Presets) do
	if p.Rate then
		local part = Instance.new("Part")
		part.Name = name part.Anchored = true part.CanCollide = false part.Transparency = 1 part.Size = Vector3.new(1, 1, 1)
		part.Position = origin + Vector3.new((i % 6) * 9 - 22, 0, math.floor(i / 6) * 9)
		part.Parent = folder
		local ok, e = pcall(VFX.attach, part, name)
		if not ok then warn("ForgeVFX showroom " .. name .. ": " .. tostring(e)) end
		i += 1
	end
end
print("FORGE_SHOWROOM " .. i)`;
          const out2=await studioCall('execute_luau',{code:demo});
          const verified=drawn.manifest.type==='ui_kit'?/FORGE_DEMO ok/.test(out2):/FORGE_SHOWROOM \d+/.test(out2);
          steps.push('preview: '+(verified?'creation confirmed':'unverified; inspect Studio Output'));
          installInfo.demoVerified=verified;
          if(verified)installInfo.demo=drawn.manifest.type==='ui_kit'?'StarterGui.ForgeDemo_'+generation:'workspace.ForgeVFX_Showroom_'+generation;
        }
      }
    }
    return { name: drawn.name, install: installInfo };
  }

  const api = { run, render, buildKit, PACKS: Object.keys(PACKS), element, icon, vfxSingle, vfxStrip, flipbook, backdrop, sheet, toBase64, paletteFromImage,
    STYLES, PALETTES, RARITY, ICONS: Object.keys(ICONS), VFX_SINGLES, VFX_STRIPS, VFX_FLIPBOOKS, VFX_PRESETS, BACKDROPS };
  g.MSForge = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
