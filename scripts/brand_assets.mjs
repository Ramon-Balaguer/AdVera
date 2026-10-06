// Renders the PNG brand assets of AdVera from the SVGs in docs/brand, with the Inter
// typeface and the triangles of the landing page. Run from the repository root:
//   node scripts/brand_assets.mjs
// It uses the Playwright of the frontend (cd frontend && npm install) and needs internet for
// the font.
import { createRequire } from "node:module";
import { copyFileSync, readFileSync, mkdirSync } from "node:fs";
import path from "node:path";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/(\w:)/, "$1")), "..");
const require = createRequire(path.join(root, "frontend", "package.json"));
const { chromium } = require("@playwright/test");
const brand = path.join(root, "docs", "brand");
mkdirSync(brand, { recursive: true });
const svg = (name) => readFileSync(path.join(brand, name), "utf8");
const dataUrl = (name) => "data:image/svg+xml;base64," + Buffer.from(svg(name)).toString("base64");

const FONT = '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;400;600&display=block" rel="stylesheet">';
// The drifting triangles of the landing page, frozen, with a seed so every render is the same.
const PARTICLES = `
<canvas id="bg"></canvas>
<script>
  const c = document.getElementById("bg"), g = c.getContext("2d");
  c.width = innerWidth * 2; c.height = innerHeight * 2; g.scale(2, 2);
  let seed = 11; const r = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const colors = ["#8052ff", "#ffb829", "#15846e", "#ff4fa3", "#3d8bff", "#a56bff", "#2fd6a5", "#ffd166"];
  const n = Math.round(innerWidth * innerHeight / 9000);
  for (let i = 0; i < n; i++) {
    const x = r() * innerWidth, y = r() * innerHeight, s = 1.6 + r() * 3.2, a = r() * 6.3;
    g.globalAlpha = 0.18 + r() * 0.3; g.strokeStyle = colors[i % colors.length]; g.lineWidth = 1;
    g.beginPath();
    for (let k = 0; k < 3; k++) { const t = a + k * 2.094; g[k ? "lineTo" : "moveTo"](x + Math.cos(t) * s, y + Math.sin(t) * s); }
    g.closePath(); g.stroke();
  }
</script>`;
const BASE = `*{box-sizing:border-box;margin:0}html,body{width:100%;height:100%;background:#000;color:#fff;font-family:Inter,sans-serif;overflow:hidden}
#bg{position:fixed;inset:0;width:100%;height:100%}main{position:relative;z-index:1;width:100%;height:100%}`;

function card({ w, h, title, sub, label, layout }) {
  return `<!doctype html><html><head><meta charset="utf-8">${FONT}<style>${BASE}
  main{display:flex;flex-direction:column;justify-content:space-between;padding:${layout.pad}px}
  .top{display:flex;align-items:center;gap:${layout.gap}px}
  .top img{width:${layout.mark}px;height:${layout.mark}px}
  .top span{font-size:${layout.name}px;font-weight:400;letter-spacing:-0.03em}
  .label{color:#ffb829;font-size:${layout.label}px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;margin-bottom:${layout.gap}px}
  h1{font-size:${layout.title}px;font-weight:400;line-height:1;letter-spacing:-0.045em;max-width:${layout.measure}px}
  p{margin-top:${layout.gap * 1.2}px;color:#bdbdbd;font-weight:200;font-size:${layout.sub}px;line-height:1.4;max-width:${layout.measure}px}
  </style></head><body>${PARTICLES}<main>
  <div class="top"><img src="${dataUrl("mark.svg")}" alt=""><span>AdVera</span></div>
  <div>${label ? `<div class="label">${label}</div>` : ""}<h1>${title}</h1>${sub ? `<p>${sub}</p>` : ""}</div>
  </main></body></html>`;
}

const plain = (inner, bg = "#000") => `<!doctype html><html><head><meta charset="utf-8">${FONT}<style>
*{margin:0}html,body{width:100%;height:100%;background:${bg};overflow:hidden}
body{display:flex;align-items:center;justify-content:center}img{display:block}</style></head><body>${inner}</body></html>`;

const lockup = (bg, ink) => plain(
  `<div style="display:flex;align-items:center;gap:40px"><img src="${dataUrl("mark.svg")}" width="200" height="200">` +
    `<span style="font-family:Inter;font-size:150px;font-weight:400;letter-spacing:-0.04em;color:${ink}">AdVera</span></div>`,
  bg,
);

const jobs = [
  // Icons
  ...[16, 32, 48, 180, 192, 512].map((s) => ({ file: `favicon-${s}.png`, w: s, h: s, transparent: true, html: plain(`<img src="${dataUrl("favicon.svg")}" width="${s}" height="${s}">`, "transparent") })),
  { file: "apple-touch-icon.png", w: 180, h: 180, html: plain(`<img src="${dataUrl("favicon.svg")}" width="180" height="180">`) },
  // Logos
  { file: "mark-512.png", w: 512, h: 512, transparent: true, html: plain(`<img src="${dataUrl("mark.svg")}" width="512" height="512">`, "transparent") },
  // The name is real Inter text here (a font cannot load inside an SVG drawn as an image).
  { file: "logo-dark.png", w: 1200, h: 256, html: lockup("#000", "#fff") },
  { file: "logo-light.png", w: 1200, h: 256, html: lockup("#fff", "#0a0a0a") },
  { file: "avatar.png", w: 400, h: 400, html: plain(`<img src="${dataUrl("mark.svg")}" width="260" height="260">`) },
  // Marketing cards
  { file: "og-image.png", w: 1200, h: 630, html: card({ w: 1200, h: 630, label: "Self-hosted · AI-first meeting manager", title: "Every meeting, verifiable knowledge.", sub: "Everything is recorded, and everything can be checked.", layout: { pad: 72, gap: 18, mark: 56, name: 34, label: 18, title: 84, sub: 26, measure: 980 } }) },
  { file: "og-image-es.png", w: 1200, h: 630, html: card({ w: 1200, h: 630, label: "Autoalojado · Gestor de reuniones con IA", title: "Cada reunión, conocimiento verificable.", sub: "Todo queda grabado, y todo se puede comprobar.", layout: { pad: 72, gap: 18, mark: 56, name: 34, label: 18, title: 76, sub: 26, measure: 1000 } }) },
  { file: "github-social.png", w: 1280, h: 640, html: card({ w: 1280, h: 640, label: "Self-hosted · open to your own model", title: "Every meeting, verifiable knowledge.", sub: "Record, transcribe in around 100 languages, summarise and search every meeting, with citations to the second of audio.", layout: { pad: 80, gap: 18, mark: 56, name: 34, label: 18, title: 84, sub: 24, measure: 1040 } }) },
  { file: "square-post.png", w: 1080, h: 1080, html: card({ w: 1080, h: 1080, label: "Self-hosted · AI-first meeting manager", title: "Every meeting, verifiable knowledge.", sub: "Every summary, decision and answer links back to the second of audio that supports it.", layout: { pad: 90, gap: 24, mark: 72, name: 42, label: 22, title: 118, sub: 32, measure: 900 } }) },
];

const browser = await chromium.launch();
for (const job of jobs) {
  const page = await browser.newPage({ viewport: { width: job.w, height: job.h }, deviceScaleFactor: 1 });
  await page.setContent(job.html, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: path.join(brand, job.file), omitBackground: Boolean(job.transparent) });
  await page.close();
  console.log("wrote", job.file);
}
await browser.close();

// The landing page is published on its own (only landingpage/ goes to GitHub Pages), so the
// icons and the link preview it uses are copied next to it.
const landing = path.join(root, "landingpage", "assets");
mkdirSync(landing, { recursive: true });
for (const file of ["og-image.png", "favicon-32.png", "apple-touch-icon.png"]) {
  copyFileSync(path.join(brand, file), path.join(landing, file));
  console.log("copied", file, "to landingpage/assets");
}
