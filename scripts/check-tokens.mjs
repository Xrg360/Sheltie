// Fails when a color literal appears outside src/styles/tokens.css (DESIGN.md invariant: tokens are the only color source).
// Brand image assets (src/app/icon.svg) are exempt because SVG files cannot read CSS variables.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../src", import.meta.url));
const allowed = new Set(["styles/tokens.css", "app/icon.svg", "app/layout.tsx"]);
const pattern = /#[0-9a-fA-F]{3,8}\b(?![\w-])|\brgba?\(\s*\d|\bhsla?\(\s*\d/g;

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const problems = [];
for (const file of walk(root)) {
  const rel = relative(root, file).split(sep).join("/");
  if (allowed.has(rel) || !/\.(css|tsx?|svg)$/.test(rel)) continue;
  readFileSync(file, "utf8")
    .split("\n")
    .forEach((line, index) => {
      if (line.trim().startsWith("//") || line.trim().startsWith("*")) return;
      for (const match of line.matchAll(pattern)) problems.push(`${rel}:${index + 1}: ${match[0]}`);
    });
}

if (problems.length) {
  console.error("Color literals found outside src/styles/tokens.css. Use a token from DESIGN.md instead:\n" + problems.join("\n"));
  process.exit(1);
}
console.log("Token check OK: no color literals outside tokens.css.");
