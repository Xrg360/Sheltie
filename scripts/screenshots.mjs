// Generates README/website screenshots and social images from the demo export.
// Usage: npm run build:demo && node scripts/screenshots.mjs
// Set PW_CHROMIUM_PATH to use an existing Chromium instead of Playwright's download.
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import { setTimeout as sleep } from "node:timers/promises";

import { chromium } from "@playwright/test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const outDir = `${root}docs/assets/screenshots`;
mkdirSync(outDir, { recursive: true });

const server = spawn("node", ["scripts/serve-demo.mjs"], { cwd: root, env: { ...process.env, PORT: "4173" }, stdio: "ignore" });
await sleep(800);

const browser = await chromium.launch(process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH, args: ["--no-sandbox"] } : {});
const base = "http://localhost:4173/demo/";

const shots = [
  { name: "overview-light", path: "", width: 1440, height: 900, scheme: "light" },
  { name: "overview-dark", path: "", width: 1440, height: 900, scheme: "dark" },
  { name: "monitors-light", path: "monitors/?site=Blog", width: 1440, height: 900, scheme: "light" },
  { name: "containers-light", path: "containers/", width: 1440, height: 900, scheme: "light" },
  { name: "network-dark", path: "network/", width: 1440, height: 900, scheme: "dark" },
  { name: "incidents-light", path: "incidents/", width: 1440, height: 900, scheme: "light" },
  { name: "overview-mobile", path: "", width: 390, height: 844, scheme: "light", mobile: true },
  { name: "monitors-mobile-dark", path: "monitors/", width: 390, height: 844, scheme: "dark", mobile: true },
];

try {
  for (const shot of shots) {
    const page = await browser.newPage({ viewport: { width: shot.width, height: shot.height }, colorScheme: shot.scheme, deviceScaleFactor: shot.mobile ? 2 : 1, isMobile: Boolean(shot.mobile), hasTouch: Boolean(shot.mobile) });
    await page.goto(base + shot.path, { waitUntil: "networkidle" });
    await page.waitForTimeout(700);
    await page.screenshot({ path: `${outDir}/${shot.name}.png` });
    await page.close();
    console.log(`saved ${shot.name}.png`);
  }

  // Social images: logo, tagline and the Overview screenshot on the Ink & Cream canvas.
  const tokens = readFileSync(`${root}src/styles/tokens.css`, "utf8");
  const icon = readFileSync(`${root}src/app/icon.svg`, "utf8");
  const shot = readFileSync(`${outDir}/overview-light.png`).toString("base64");
  for (const [file, width, height] of [["og.png", 1200, 630], ["social-preview.png", 1280, 640]]) {
    const page = await browser.newPage({ viewport: { width, height }, colorScheme: "light" });
    await page.setContent(`<!doctype html><html><head><style>${tokens}
      body{margin:0;width:${width}px;height:${height}px;background:var(--bg);font-family:var(--font-sans);color:var(--text);display:grid;grid-template-columns:44% 56%;overflow:hidden}
      .l{padding:64px 0 64px 64px;display:flex;flex-direction:column;justify-content:center;gap:24px}
      .b{display:flex;align-items:center;gap:16px;font-size:34px;font-weight:var(--weight-display);letter-spacing:var(--tracking-display)}
      .b svg{width:64px;height:64px}
      h1{margin:0;font-size:52px;line-height:1.04;letter-spacing:-.04em;font-weight:var(--weight-display)}
      p{margin:0;font-size:22px;color:var(--text-2);line-height:1.4}
      .f{align-self:flex-start;padding:4px 14px;border-radius:var(--radius-full);background:var(--accent-soft);color:var(--text-2);font-size:16px;font-weight:600}
      .r{position:relative}
      .r img{position:absolute;left:48px;top:64px;width:1100px;border-radius:var(--radius-xl);border:1px solid var(--border);box-shadow:var(--shadow-2)}
    </style></head><body><div class="l"><div class="b">${icon}<span>Sheltie</span></div>
      <h1>Know what happened while you were offline.</h1>
      <p>Open-source monitoring for Docker homelabs: uptime, containers, network, auto-heal and Telegram alerts.</p>
      <span class="f">Formerly Meerkat</span></div>
      <div class="r"><img src="data:image/png;base64,${shot}"></div></body></html>`);
    await page.screenshot({ path: `${root}docs/assets/${file}` });
    await page.close();
    console.log(`saved ${file}`);
  }
} finally {
  await browser.close();
  server.kill();
}
