// SPDX-License-Identifier: GPL-3.0-or-later
// Multi-Script environment scenes: animated, layered backdrops for the horror
// themes, drawn entirely in code (SVG + CSS, no network assets). Shared by the
// browser extension (menu panel) and Multi-Script IDE (whole window).
//   MSScenes.mount(container, themeId, { motion: "full"|"reduced"|"none", pointer: true })
//   -> returns { unmount() } or null when the theme has no scene.
(function (g) {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const rng = (seed) => {
    let a = seed >>> 0;
    return () => {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  };
  const f1 = (n) => Math.round(n * 10) / 10;
  const svg = (body, vb = "0 0 1600 900", par = "xMidYMax slice", cls = "") =>
    `<svg xmlns="${NS}" class="${cls}" viewBox="${vb}" preserveAspectRatio="${par}" aria-hidden="true">${body}</svg>`;

  function stars(seed, n, h = 520, w = 1600) {
    const r = rng(seed);
    let s = "";
    for (let i = 0; i < n; i++) {
      const x = f1(r() * w),
        y = f1(r() * h * r()),
        rad = f1(0.5 + r() * 1.3);
      const o = (0.25 + r() * 0.7).toFixed(2);
      s += `<circle cx="${x}" cy="${y}" r="${rad}" fill="#fff" opacity="${o}"${i % 7 === 0 ? ' class="sc-twinkle" style="animation-delay:' + (r() * 6).toFixed(1) + 's"' : ""}/>`;
    }
    return s;
  }
  function moon(cx, cy, r, color = "#f3eedf", glow = "rgba(240,235,210,.35)") {
    return `<defs><radialGradient id="mg${cx}" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="${glow}"/><stop offset="1" stop-color="rgba(0,0,0,0)"/></radialGradient>
      <radialGradient id="mf${cx}" cx="40%" cy="38%" r="70%"><stop offset="0" stop-color="#fffdf4"/><stop offset=".7" stop-color="${color}"/><stop offset="1" stop-color="#cfc6b0"/></radialGradient></defs>
      <circle cx="${cx}" cy="${cy}" r="${r * 4}" fill="url(#mg${cx})"/>
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="url(#mf${cx})"/>
      <g fill="#bdb39c" opacity=".35"><circle cx="${cx - r * 0.3}" cy="${cy - r * 0.2}" r="${r * 0.16}"/><circle cx="${cx + r * 0.25}" cy="${cy + r * 0.25}" r="${r * 0.22}"/><circle cx="${cx + r * 0.35}" cy="${cy - r * 0.35}" r="${r * 0.09}"/></g>`;
  }
  // Pine treeline along a baseline: individual layered conifers + ground fill.
  function pines(seed, y, h, color, density = 38, w = 1600, jitter = 0.5) {
    const r = rng(seed);
    const base = y + h;
    let out = `<path d="M-40 ${base - h * 0.12} H${w + 40} V900 H-40Z" fill="${color}"/>`;
    let x = -30;
    while (x < w + 40) {
      const th = h * (0.6 + r() * jitter);
      const tw = (w / density) * (0.8 + r() * 0.7);
      const cx = x + tw / 2;
      const tiers = 5 + Math.floor(r() * 3);
      const tierH = (th * 0.92) / tiers;
      const L = [],
        R = [];
      for (let k = 0; k < tiers; k++) {
        const yb = base - th * 0.08 - k * tierH;
        const half = (tw / 2) * (1 - k / (tiers + 0.6)) * (0.9 + r() * 0.2);
        L.push(
          `${f1(cx - half)} ${f1(yb)}`,
          `${f1(cx - half * 0.42)} ${f1(yb - tierH * 0.7)}`,
        );
        R.unshift(
          `${f1(cx + half * 0.42)} ${f1(yb - tierH * 0.7)}`,
          `${f1(cx + half)} ${f1(yb)}`,
        );
      }
      out += `<path d="M${f1(cx - tw * 0.06)} ${base} L${L.join(" L")} L${f1(cx)} ${f1(base - th)} L${R.join(" L")} L${f1(cx + tw * 0.06)} ${base}Z" fill="${color}"/>`;
      x += tw * (0.55 + r() * 0.35);
    }
    return out;
  }
  // Bare branching tree (recursive)
  function bareTree(seed, x, y, len, ang, width, color, depth = 7) {
    const r = rng(seed);
    let out = "";
    const grow = (x0, y0, l, a, w, d) => {
      if (d <= 0 || l < 4) return;
      const x1 = x0 + Math.cos(a) * l,
        y1 = y0 + Math.sin(a) * l;
      out += `<path d="M${f1(x0)} ${f1(y0)} L${f1(x1)} ${f1(y1)}" stroke="${color}" stroke-width="${f1(w)}" stroke-linecap="round"/>`;
      const n = d > 5 ? 2 : 2 + (r() < 0.4 ? 1 : 0);
      for (let i = 0; i < n; i++) {
        const na = a + (r() - 0.5) * 1.1 + (i - (n - 1) / 2) * 0.45;
        grow(x1, y1, l * (0.66 + r() * 0.16), na, w * 0.68, d - 1);
      }
    };
    grow(x, y, len, ang, width, depth);
    return `<g fill="none">${out}</g>`;
  }
  function trunks(seed, n, color, opts = {}) {
    const r = rng(seed);
    const {
      minW = 10,
      maxW = 40,
      branch = 0.5,
      top = -40,
      w = 1600,
      bottom = 900,
    } = opts;
    let s = "";
    for (let i = 0; i < n; i++) {
      const x = ((i + r() * 0.8) / n) * w;
      const tw = minW + r() * (maxW - minW);
      const lean = (r() - 0.5) * 30;
      s += `<path d="M${f1(x - tw / 2)} ${bottom} C${f1(x - tw / 2.4)} ${bottom * 0.6} ${f1(x - tw / 3 + lean)} ${bottom * 0.3} ${f1(x - tw / 4 + lean)} ${top} L${f1(x + tw / 4 + lean)} ${top} C${f1(x + tw / 3 + lean)} ${bottom * 0.3} ${f1(x + tw / 2.4)} ${bottom * 0.6} ${f1(x + tw / 2)} ${bottom}Z" fill="${color}"/>`;
      if (r() < branch) {
        const by = 120 + r() * 380,
          dir = r() < 0.5 ? -1 : 1;
        s += `<path d="M${f1(x + lean * 0.6)} ${f1(by)} q${f1(dir * 50)} -${f1(20 + r() * 30)} ${f1(dir * (90 + r() * 70))} -${f1(50 + r() * 40)}" stroke="${color}" stroke-width="${f1(tw / 5)}" fill="none" stroke-linecap="round"/>`;
      }
    }
    return s;
  }
  const windowGlow = (x, y, w, h, color = "#ffc36b", cls = "") =>
    `<g class="${cls}"><rect x="${x - 6}" y="${y - 6}" width="${w + 12}" height="${h + 12}" fill="${color}" opacity=".18" rx="4"/><rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${color}"/><path d="M${x + w / 2} ${y}v${h}M${x} ${y + h / 2}h${w}" stroke="rgba(0,0,0,.55)" stroke-width="2"/></g>`;

  // ------------------------------------------------------------- scenes
  const SCENES = {};

  // Scream: Woodsboro, a farmhouse on a quiet street at night.
  SCENES.scream = {
    label: "WOODSBORO, CALIFORNIA",
    sub: "What's your favorite scary movie?",
    build(L) {
      L("sky");
      L(
        "svg",
        svg(
          stars(11, 120, 460) +
            moon(1240, 170, 54, "#f1ece6", "rgba(235,84,101,.16)"),
        ),
        "sc-sky-svg",
      );
      L("clouds", "<i></i><i></i><i></i>");
      const house = `
        <path d="M0 640 Q300 600 620 628 T1600 610 V900 H0Z" fill="#120f1b"/>
        ${pines(5, 520, 120, "#0e0c16", 30)}
        <g fill="#0b0a12">
          <path d="M360 700 V500 L520 400 L680 500 V700Z"/>
          <path d="M680 700 V540 L760 490 L900 490 L960 540 V700Z"/>
          <rect x="600" y="410" width="26" height="70"/>
          <path d="M330 700 V600 H720 V700Z"/>
          <path d="M320 600 H730 L700 575 H350Z"/>
          <rect x="980" y="600" width="170" height="100"/>
          <path d="M965 600 L1065 545 L1165 600Z"/>
        </g>
        ${windowGlow(400, 520, 46, 58)}
        ${windowGlow(560, 520, 46, 58, "#9fc4ff", "sc-tv")}
        ${windowGlow(470, 438, 36, 40, "#ffcf86")}
        ${windowGlow(790, 560, 50, 52, "#ffb85c", "sc-flicker")}
        <rect x="486" y="612" width="46" height="88" fill="#ffd59a" opacity=".16"/><rect x="494" y="620" width="30" height="80" fill="#1a1520"/><path d="M494 620 h12 v80 h-12z" fill="#ffd59a" opacity=".8"/>
        <rect x="995" y="618" width="140" height="82" fill="#16131e"/><path d="M995 638h140M995 658h140M995 678h140" stroke="#0b0a12" stroke-width="3"/>
        <g fill="#0a0910"><path d="M1250 700 C1240 560 1256 470 1262 420 L1282 420 C1290 480 1300 580 1296 700Z"/>
          <ellipse cx="1270" cy="380" rx="190" ry="120"/><ellipse cx="1170" cy="420" rx="110" ry="70"/><ellipse cx="1390" cy="410" rx="120" ry="80"/>
          <path d="M1270 470 L1150 455" stroke="#0a0910" stroke-width="14"/></g>
        <g class="sc-swing" style="transform-origin:1190px 458px"><path d="M1172 458 V610 M1208 458 V610" stroke="#2b2733" stroke-width="3"/><rect x="1162" y="606" width="56" height="10" rx="2" fill="#2b2733"/></g>
        <g fill="#0f0d16">${Array.from({ length: 64 }, (_, i) => `<path d="M${i * 26} 760 v-58 l7 -10 l7 10 v58z"/>`).join("")}<rect x="0" y="716" width="1664" height="8"/><rect x="0" y="742" width="1664" height="8"/></g>
        <path d="M0 760 H1600 V900 H0Z" fill="#08070d"/>`;
      L("svg", svg(house), "sc-land");
      L("headlights");
      L("fog");
      L(
        "hud",
        `<div class="sc-call"><b>☎</b><span><em>INCOMING CALL</em>UNKNOWN NUMBER</span></div>`,
      );
    },
  };

  // Halloween: Haddonfield, Illinois — Lampkin Lane on Halloween night.
  SCENES.myers = {
    label: "HADDONFIELD, ILLINOIS",
    sub: "Lampkin Lane · October 31, 1978",
    build(L) {
      L("sky");
      L(
        "svg",
        svg(
          stars(23, 70, 330) +
            `<path d="M1210 140 a48 48 0 1 0 34 82 a40 40 0 1 1 -34 -82z" fill="#f6e3c0" opacity=".9"/>`,
        ),
        "sc-sky-svg",
      );
      const houses = `
        <path d="M0 560 H1600 V900 H0Z" fill="#0d0b12"/>
        <g fill="#100d16">
          <path d="M-20 600 V470 L80 400 L180 470 V600Z"/><path d="M190 600 V500 L270 450 L350 500 V600Z"/>
          <path d="M1270 600 V480 L1360 420 L1450 480 V600Z"/><path d="M1460 600 V500 L1540 455 L1640 500 V600Z"/>
        </g>
        ${windowGlow(40, 500, 30, 34, "#f7b25e")}${windowGlow(250, 525, 26, 30, "#f0a24a")}${windowGlow(1330, 505, 30, 34, "#f7b25e")}${windowGlow(1500, 530, 26, 30, "#e99a45")}
        <g fill="#0a0810">
          <path d="M520 640 V420 L640 330 L760 420 V640Z"/>
          <path d="M760 640 V460 L840 400 L940 460 V640Z"/>
          <rect x="690" y="340" width="24" height="70"/>
          <path d="M480 640 V560 H980 V640Z"/><path d="M470 560 H990 L960 532 H500Z"/>
          <path d="M600 420 L640 380 L680 420Z" fill="#0d0b13"/>
        </g>
        <rect x="625" y="390" width="30" height="26" fill="#3a2a1e" opacity=".8"/>
        ${windowGlow(560, 450, 40, 50, "#5b4a3a")}${windowGlow(690, 450, 40, 50, "#2f2a2a")}
        ${windowGlow(820, 480, 40, 46, "#ffb35a", "sc-flicker")}
        <rect x="660" y="580" width="40" height="60" fill="#1b1410"/>
        ${bareTree(7, 380, 640, 120, -1.62, 16, "#08070c")}
        ${bareTree(9, 1120, 640, 130, -1.5, 18, "#08070c")}
        ${bareTree(13, 1560, 610, 100, -1.7, 12, "#09080d", 6)}
        <g><rect x="1010" y="380" width="8" height="300" fill="#141117"/><path d="M1014 384 h46 v10 h-46z" fill="#141117"/><path d="M1046 394 h30 l-6 12 h-18z" fill="#2a2018"/></g>
        <g transform="translate(300 540)"><rect x="0" y="0" width="6" height="140" fill="#18141a"/><rect x="-34" y="-2" width="74" height="18" rx="2" fill="#1d4d2b"/><text x="3" y="12" fill="#e7f0e2" font-size="11" font-family="Arial,Helvetica,sans-serif" font-weight="700" text-anchor="middle">LAMPKIN LN</text></g>
        <g fill="#0e0b12">${Array.from({ length: 40 }, (_, i) => `<path d="M${i * 22 - 10} 700 v-40 l6 -8 l6 8 v40z"/>`).join("")}<rect x="-10" y="672" width="890" height="6"/></g>
        <path d="M0 700 H1600 V722 H0Z" fill="#17131b"/><path d="M0 722 H1600 V900 H0Z" fill="#0a0910"/>
        <path d="M0 800 H1600" stroke="#3a2e1c" stroke-width="3" stroke-dasharray="40 46" opacity=".5"/>
        <g class="sc-pumpkins">
          ${[
            [600, 690, 1],
            [740, 692, 0.85],
            [540, 712, 1.25],
            [812, 714, 1],
          ]
            .map(
              ([x, y, s], i) => `
            <g transform="translate(${x} ${y}) scale(${s})" class="sc-jack" style="animation-delay:${i * 0.7}s">
              <ellipse cx="0" cy="0" rx="34" ry="34" fill="#ff8a1d" opacity=".25"/>
              <ellipse cx="0" cy="2" rx="22" ry="17" fill="#d4650f"/><path d="M-12 2 a12 16 0 0 1 24 0" fill="none" stroke="#a84c0a" stroke-width="2"/>
              <rect x="-2" y="-20" width="4" height="7" fill="#3c4a1c"/>
              <path d="M-12 -3 l5 -6 l5 6z M2 -3 l5 -6 l5 6z M-12 8 q12 8 24 0 l-4 -2 l-3 3 l-3 -3 l-3 3 l-3 -3 l-3 3z" fill="#ffd36b"/>
            </g>`,
            )
            .join("")}
        </g>`;
      L("svg", svg(houses), "sc-land");
      L("lamp");
      L(
        "leaves",
        Array.from(
          { length: 22 },
          (_, i) =>
            `<i style="--x:${(i * 47) % 100}%;--d:${9 + (i % 7) * 1.7}s;--dl:${-(i * 1.3).toFixed(1)}s;--s:${0.6 + (i % 5) * 0.18};--h:${[18, 28, 8, 35, 0][i % 5]}"></i>`,
        ).join(""),
      );
      L("fog");
    },
  };

  // Slender: the woods at night; eight pages, a flashlight, and something tall.
  SCENES.slender = {
    label: "OAKSIDE PARK · THE WOODS",
    sub: "Pages collected: 3 / 8",
    pointer: true,
    build(L) {
      L("sky");
      L(
        "svg",
        svg(
          `<rect width="1600" height="900" fill="url(#fogg)"/><defs><radialGradient id="fogg" cx="50%" cy="70%" r="70%"><stop offset="0" stop-color="#213029"/><stop offset="1" stop-color="#050807"/></radialGradient></defs>` +
            trunks(31, 26, "#1a2621", { minW: 6, maxW: 16, branch: 0.3 }),
        ),
        "sc-far sc-blur2",
      );
      L(
        "figure",
        svg(
          `<g transform="translate(980 360)"><ellipse cx="0" cy="0" rx="13" ry="18" fill="#d6ddd8"/><path d="M-16 20 L-20 240 L-8 240 L-3 120 L3 120 L8 240 L20 240 L16 20 Q0 12 -16 20Z" fill="#050706"/><path d="M-4 20 L0 60 L4 20Z" fill="#e8ece6"/><path d="M-1 24 L0 56 L1 24Z" fill="#7e1520"/><path d="M-16 26 C-40 80 -46 120 -50 180 M16 26 C40 80 46 120 50 180" stroke="#050706" stroke-width="5" fill="none"/></g>`,
        ),
        "sc-figure",
      );
      L(
        "svg",
        svg(trunks(37, 16, "#0c1310", { minW: 14, maxW: 34, branch: 0.5 })),
        "sc-mid sc-blur1",
      );
      L("fog");
      const pages = [
        [300, 430, -6, "NO NO NO"],
        [1240, 380, 5, "ALWAYS WATCHES"],
        [760, 470, -3, "DON'T LOOK"],
      ];
      L(
        "svg",
        svg(
          trunks(41, 7, "#030504", { minW: 40, maxW: 80, branch: 0.6 }) +
            pages
              .map(
                ([x, y, rot, t]) =>
                  `<g transform="translate(${x} ${y}) rotate(${rot})"><rect x="-26" y="-34" width="52" height="66" fill="#e9e6da"/><path d="M-18 -18 h36 M-18 -8 h30 M-18 2 h34" stroke="#2a2a2a" stroke-width="1.6" opacity=".5"/><text x="0" y="22" text-anchor="middle" font-family="Courier New,monospace" font-size="7.5" font-weight="700" fill="#1a1a1a">${t}</text><circle cx="0" cy="-30" r="2.4" fill="#7e1520"/></g>`,
              )
              .join("") +
            `<path d="M0 820 Q400 790 800 812 T1600 800 V900 H0Z" fill="#020303"/>`,
        ),
        "sc-near",
      );
      L("flashlight");
      L("static");
      L("hud", `<div class="sc-pages"><b>PAGES</b> 3/8</div>`);
    },
  };

  // Friday the 13th: Camp Crystal Lake at night.
  SCENES.jason = {
    label: "CAMP CRYSTAL LAKE",
    sub: "Friday the 13th · Cabin lights out at 10",
    build(L) {
      L("sky");
      L(
        "svg",
        svg(
          stars(53, 150, 470) +
            moon(1150, 150, 62, "#f2f1e4", "rgba(210,230,240,.22)"),
        ),
        "sc-sky-svg",
      );
      L(
        "svg",
        svg(
          pines(57, 430, 110, "#0b171b", 46) +
            pines(59, 470, 80, "#081115", 60),
        ),
        "sc-far",
      );
      L(
        "lake",
        `<div class="sc-water"></div><div class="sc-reflect">${Array.from({ length: 16 }, (_, i) => `<i style="--y:${f1(i * 6.2 + (i % 3) * 1.3)}%;--w:${f1((30 - i * 1.4) * (0.6 + ((i * 7) % 5) / 6))}%;--o:${((i * 13) % 9) - 4}%;--dl:${-(i * 0.37).toFixed(2)}s"></i>`).join("")}</div>`,
      );
      const shore = `
        <path d="M0 700 Q200 664 420 676 L560 690 L560 900 H0Z" fill="#060c0e"/>
        <path d="M1600 690 Q1400 660 1180 676 L1100 700 V900 H1600Z" fill="#060c0e"/>
        <g fill="#0a1214"><path d="M190 700 V610 L270 560 L350 610 V700Z"/><path d="M360 690 V625 L415 590 L470 625 V690Z"/><rect x="250" y="660" width="26" height="40" fill="#05090b"/></g>
        ${windowGlow(300, 625, 26, 26, "#ffc06b", "sc-flicker")}${windowGlow(405, 640, 22, 22, "#f2a95a")}
        <g fill="#2a1f17"><rect x="560" y="686" width="420" height="10"/>${[580, 660, 740, 820, 900, 970].map((x) => `<rect x="${x}" y="694" width="7" height="44"/>`).join("")}</g>
        <path d="M1000 735 q60 14 130 0 q-10 12 -65 14 q-55 -2 -65 -14z" fill="#1f1812"/>
        <g transform="translate(560 600)"><rect x="0" y="0" width="7" height="100" fill="#2c2118"/><rect x="150" y="0" width="7" height="100" fill="#2c2118"/><rect x="-14" y="-8" width="186" height="48" rx="3" fill="#3a2a1d"/><rect x="-14" y="-8" width="186" height="48" rx="3" fill="none" stroke="#1d150f" stroke-width="3"/><text x="79" y="12" text-anchor="middle" font-family="Georgia,serif" font-size="13" font-weight="700" fill="#e9d6b1">CAMP</text><text x="79" y="31" text-anchor="middle" font-family="Georgia,serif" font-size="14" font-weight="700" fill="#e9d6b1">CRYSTAL LAKE</text></g>
        ${pines(61, 380, 340, "#03070a", 5, 190, 0.6)}
        <g transform="translate(1290 0)">${pines(67, 360, 360, "#03070a", 7, 320, 0.6)}</g>
        <path d="M0 860 H1600 V900 H0Z" fill="#020405"/>`;
      L("svg", svg(shore), "sc-land");
      L("mist");
      L(
        "flies",
        Array.from(
          { length: 14 },
          (_, i) =>
            `<i style="--x:${(i * 37 + 9) % 100}%;--y:${58 + ((i * 13) % 30)}%;--d:${4 + (i % 5)}s;--dl:${-(i * 0.9).toFixed(1)}s"></i>`,
        ).join(""),
      );
    },
  };

  // Five Nights at Freddy's: the show stage at Freddy Fazbear's Pizza.
  SCENES.fnaf = {
    label: "FREDDY FAZBEAR'S PIZZA",
    sub: "● REC  CAM 1A · SHOW STAGE",
    build(L) {
      L("wall");
      L(
        "svg",
        svg(`
        <g transform="translate(150 230)"><rect width="190" height="250" rx="6" fill="#efe3c8"/><rect x="10" y="10" width="170" height="40" fill="#c0392b"/><text x="95" y="38" font-family="Impact,Arial Black,sans-serif" font-size="26" fill="#fff4d6" text-anchor="middle">CELEBRATE!</text>
          <g transform="translate(95 150)"><circle cx="-48" cy="0" r="26" fill="#6b4ea8"/><circle cx="0" cy="-6" r="30" fill="#8a5a2b"/><circle cx="48" cy="0" r="26" fill="#e6b52c"/><rect x="-14" y="-52" width="28" height="22" fill="#1b1416"/><path d="M-64 -24 l6 -26 l8 24z M-38 -24 l4 -28 l8 24z" fill="#6b4ea8"/></g></g>
        <g transform="translate(1260 250)"><rect width="170" height="120" rx="4" fill="#1d1426"/><rect x="8" y="8" width="154" height="104" fill="#2a1d36"/><text x="85" y="52" font-family="Courier New,monospace" font-size="15" fill="#d8b4fe" text-anchor="middle">RULES</text><path d="M28 70 h114 M28 84 h96 M28 98 h106" stroke="#a78bdb" stroke-width="3" opacity=".6"/></g>`),
        "sc-posters",
      );
      const stage = `
        <defs><linearGradient id="cur" x1="0" x2="1"><stop offset="0" stop-color="#2a0f3d"/><stop offset=".5" stop-color="#4c1d6e"/><stop offset="1" stop-color="#2a0f3d"/></linearGradient></defs>
        <path d="M430 300 Q480 520 440 720 H560 Q520 520 560 300Z" fill="url(#cur)"/><path d="M1170 300 Q1120 520 1160 720 H1040 Q1080 520 1040 300Z" fill="url(#cur)"/>
        <g fill="#f2c230" opacity=".7">${[
          [470, 380],
          [500, 470],
          [470, 560],
          [480, 650],
          [1130, 380],
          [1100, 470],
          [1130, 560],
          [1120, 650],
        ]
          .map(
            ([x, y]) =>
              `<path d="M${x} ${y - 8} l2.4 5.6 6 .5 -4.6 4 1.4 6 -5.2 -3.2 -5.2 3.2 1.4 -6 -4.6 -4 6 -.5z"/>`,
          )
          .join("")}</g>
        <rect x="410" y="286" width="780" height="22" fill="#3a1650"/>
        <g class="sc-band">
          <g transform="translate(640 560)"><path d="M-46 160 L-40 40 Q0 18 40 40 L46 160Z" fill="#2c2140"/><ellipse cx="0" cy="0" rx="42" ry="40" fill="#3a2b5a"/><path d="M-30 -30 L-38 -110 L-14 -34Z M30 -30 L38 -110 L14 -34Z" fill="#3a2b5a"/><ellipse cx="0" cy="18" rx="24" ry="14" fill="#4a3a6c"/><circle class="sc-eye" cx="-14" cy="-4" r="5"/><circle class="sc-eye" cx="14" cy="-4" r="5"/><path d="M60 40 l40 -60 l8 4 l-38 62z" fill="#a8242c"/></g>
          <g transform="translate(800 540)"><path d="M-56 180 L-50 46 Q0 20 50 46 L56 180Z" fill="#4a2f17"/><ellipse cx="0" cy="0" rx="50" ry="46" fill="#6b4422"/><circle cx="-40" cy="-38" r="15" fill="#5a3a1c"/><circle cx="40" cy="-38" r="15" fill="#5a3a1c"/><rect x="-22" y="-82" width="44" height="34" fill="#141014"/><rect x="-32" y="-52" width="64" height="8" fill="#141014"/><ellipse cx="0" cy="22" rx="28" ry="16" fill="#8a5a2b"/><path d="M-14 56 l14 8 14 -8 v12 l-14 -8 -14 8z" fill="#141014"/><circle class="sc-eye" cx="-16" cy="-6" r="5.5"/><circle class="sc-eye" cx="16" cy="-6" r="5.5"/><path d="M-80 40 l-6 46 M-86 40 a8 6 0 1 0 12 0" stroke="#1a1a1a" stroke-width="4" fill="#1a1a1a"/></g>
          <g transform="translate(960 560)"><path d="M-46 160 L-40 40 Q0 18 40 40 L46 160Z" fill="#8f6e14"/><ellipse cx="0" cy="0" rx="40" ry="40" fill="#c99a1e"/><path d="M-6 -40 l6 -16 6 16z M-12 -38 l4 -12 4 12z" fill="#c99a1e"/><path d="M-22 10 L0 34 L22 10 Q0 18 -22 10Z" fill="#e8702a"/><path d="M-34 70 h68 v44 h-68z" fill="#efe6d2"/><text x="0" y="98" font-family="Arial Black,sans-serif" font-size="11" text-anchor="middle" fill="#c0392b">LET'S EAT!</text><circle class="sc-eye" cx="-14" cy="-6" r="5"/><circle class="sc-eye" cx="14" cy="-6" r="5"/><g transform="translate(66 60)"><rect x="-14" y="-10" width="28" height="22" rx="4" fill="#e9a3b8"/><circle cx="-6" cy="-14" r="3" fill="#fff"/><circle cx="6" cy="-14" r="3" fill="#fff"/></g></g>
        </g>
        <path d="M400 720 H1200 L1230 760 H370Z" fill="#2a1a12"/><path d="M370 760 H1230 V780 H370Z" fill="#160d09"/>`;
      L("svg", svg(stage), "sc-land");
      L("spots");
      L(
        "pizzas",
        Array.from(
          { length: 9 },
          (_, i) =>
            `<i style="--x:${(i * 41 + 5) % 96}%;--y:${(i * 29 + 8) % 70}%;--s:${34 + (i % 4) * 14}px;--d:${16 + (i % 5) * 4}s;--dl:${-(i * 2.3).toFixed(1)}s;--r:${i % 2 ? 360 : -360}deg"></i>`,
        ).join(""),
      );
      L("tiles");
      L("bunting");
      L("purple");
      L("cctv");
    },
  };

  // Shared ambient scenes: the same DOM mounts in a menu or a portalled bar.
  for (const [id,label] of [["aurora","Aurora"],["lava","Lava"],["nebula","Nebula"],["matrix","Matrix"]]) {
    SCENES[id]={label,sub:"Live ambient scene",build(L){
      if(id==="matrix") L("code-rain", Array.from({length:18},(_,i)=>`<i style="--x:${i*6}%;--d:${3+(i%5)}s;--dl:${-i*.7}s">01<br>{}<br>10<br>&lt;/&gt;<br>01<br>101</i>`).join(""));
      else L("ambient", Array.from({length:4},(_,i)=>`<i style="--i:${i};--dl:${-i*3}s"></i>`).join(""));
    }};
  }

  // Original procedural scenes shared by the full menu and compact chatbar.
  SCENES.tidal={label:"Tidal",sub:"Quiet water, moving light",build(L){
    L("tidal-light","<i></i><i></i><i></i>");
    L("tidal-water",svg('<path d="M-200 660Q100 580 400 660T1000 660T1800 660V1000H-200Z" fill="#3aabb8" opacity=".18"/><path d="M-200 740Q100 660 400 740T1000 740T1800 740V1000H-200Z" fill="#67e3df" opacity=".13"/>'));
  }};
  SCENES.starlight={label:"Starlight",sub:"A studio after dark",build(L){
    L("starlight-sky",svg(stars(642,85,900)+moon(1250,230,78,"#d2c5ff","#ab8bff30")));
    L("starlight-orbit","<i></i><i></i><i></i>");
  }};
  SCENES.daybreak={label:"Daybreak",sub:"Warm light, a fresh canvas",build(L){
    L("daybreak-sun",svg('<defs><radialGradient id="daybreak-glow"><stop stop-color="#f4ba7e" stop-opacity=".65"/><stop offset="1" stop-color="#f4ba7e" stop-opacity="0"/></radialGradient></defs><circle cx="1200" cy="630" r="500" fill="url(#daybreak-glow)"/><circle cx="1200" cy="630" r="135" fill="#f8d9a4"/><path d="M0 780Q400 600 800 790T1800 720V1000H0Z" fill="#ce8f7f" opacity=".2"/>'));
    L("daybreak-cloud","<i></i><i></i><i></i>");
  }};

  function mount(container, themeId, opts = {}) {
    const def = SCENES[themeId];
    if (!container || !def) return null;
    const root = document.createElement("div");
    root.className = "ms-scene";
    root.dataset.scene = themeId;
    root.dataset.motion = opts.motion || "full";
    root.setAttribute("aria-hidden", "true");
    const L = (kind, html = "", extra = "") => {
      const d = document.createElement("div");
      d.className = "sc-" + kind + (extra ? " " + extra : "");
      if (html) d.innerHTML = html;
      root.append(d);
      return d;
    };
    def.build(L);
    if (opts.caption !== false) {
      const cap = document.createElement("div");
      cap.className = "sc-caption";
      cap.innerHTML = `<b></b><span></span>`;
      cap.firstChild.textContent = def.label;
      cap.lastChild.textContent = def.sub;
      root.append(cap);
    }
    container.prepend(root);
    let off = null;
    if (def.pointer && opts.pointer !== false) {
      const host = opts.pointerHost || window;
      let raf = 0;
      const mv = (e) => {
        if (raf) return;
        raf = requestAnimationFrame(() => {
          raf = 0;
          const b = root.getBoundingClientRect();
          root.style.setProperty(
            "--mx",
            ((e.clientX - b.left) / Math.max(1, b.width)) * 100 + "%",
          );
          root.style.setProperty(
            "--my",
            ((e.clientY - b.top) / Math.max(1, b.height)) * 100 + "%",
          );
        });
      };
      host.addEventListener("pointermove", mv, { passive: true });
      off = () => host.removeEventListener("pointermove", mv);
    }
    return {
      root,
      unmount() {
        off && off();
        root.remove();
      },
    };
  }

  const api = {
    mount,
    has: (id) => !!SCENES[id],
    ids: Object.keys(SCENES),
    info: (id) =>
      SCENES[id] && { label: SCENES[id].label, sub: SCENES[id].sub },
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  g.MSScenes = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
