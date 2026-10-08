// Fails when any dashboard route's first-load JavaScript exceeds the DESIGN.md budget.
// Run after `npm run build:demo` (it measures the static export in ./out).
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";
import { fileURLToPath } from "node:url";

const BUDGET_KB = 250;
const out = fileURLToPath(new URL("../out", import.meta.url));
if (!existsSync(out)) {
  console.error("No ./out directory. Run `npm run build:demo` first.");
  process.exit(1);
}

const pages = readdirSync(out)
  .filter((name) => statSync(join(out, name)).isDirectory() && existsSync(join(out, name, "index.html")))
  .map((name) => join(name, "index.html"));
pages.unshift("index.html");

let failed = false;
for (const page of pages) {
  const html = readFileSync(join(out, page), "utf8");
  const scripts = new Set([...html.matchAll(/src="[^"]*?(\/_next\/static\/[^"]+\.js)"/g)].map((match) => match[1]));
  const kb = [...scripts].reduce((sum, src) => sum + gzipSync(readFileSync(join(out, src))).length, 0) / 1024;
  const ok = kb <= BUDGET_KB;
  if (!ok) failed = true;
  console.log(`${ok ? "ok  " : "FAIL"} ${kb.toFixed(1).padStart(6)} KB  /${page.replace(/index\.html$/, "")}`);
}
if (failed) {
  console.error(`First-load JS budget is ${BUDGET_KB} KB gzipped per route (DESIGN.md section 11).`);
  process.exit(1);
}
