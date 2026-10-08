// Verifies that Savanna token pairs meet WCAG 2.2 AA contrast in both themes.
// Usage: node scripts/check-contrast.mjs
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/styles/tokens.css", import.meta.url), "utf8");

function block(selector) {
  const start = css.indexOf(selector);
  if (start === -1) throw new Error(`selector not found: ${selector}`);
  const open = css.indexOf("{", start);
  let depth = 1;
  let index = open + 1;
  while (depth > 0) {
    if (css[index] === "{") depth += 1;
    if (css[index] === "}") depth -= 1;
    index += 1;
  }
  const vars = {};
  for (const match of css.slice(open + 1, index - 1).matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)) vars[match[1]] = match[2];
  return vars;
}

const light = block(":root {");
const dark = { ...light, ...block(':root[data-theme="dark"]') };

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function ratio(a, b) {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

// [foreground, background, minimum] - 4.5 for text, 3 for icons, borders of controls and graphics.
const pairs = [
  ...["bg", "surface", "surface-2"].flatMap((bg) => [
    ["text", bg, 4.5],
    ["text-2", bg, 4.5],
    ["text-3", bg, 4.5],
    ["accent-text", bg, 4.5],
    ["ok", bg, 3],
    ["warn", bg, 3],
    ["bad", bg, 3],
    ["unknown", bg, 3],
  ]),
  ["accent", "surface", 3],
  ["on-accent", "accent", 4.5],
  ["accent-text", "accent-soft", 4.5],
  ["ok-text", "ok-soft", 4.5],
  ["warn-text", "warn-soft", 4.5],
  ["bad-text", "bad-soft", 4.5],
  ["unknown-text", "unknown-soft", 4.5],
  ["ok-text", "surface", 4.5],
  ["warn-text", "surface", 4.5],
  ["bad-text", "surface", 4.5],
];

let failed = 0;
for (const [name, theme] of [["light", light], ["dark", dark]]) {
  for (const [fg, bg, min] of pairs) {
    const value = ratio(theme[fg], theme[bg]);
    if (value < min) {
      failed += 1;
      console.error(`FAIL ${name}: --${fg} on --${bg} = ${value.toFixed(2)} (needs ${min})`);
    }
  }
}

if (failed) process.exit(1);
console.log(`Contrast OK: ${pairs.length * 2} token pairs meet WCAG AA in light and dark themes.`);
