// Copies shared assets from the main repo so the website never drifts from the product:
// design tokens, the logo, docs markdown, screenshots and the social image.
import { copyFileSync, existsSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const site = join(dirname(fileURLToPath(import.meta.url)), "..");
const repo = join(site, "..");

function copy(from, to) {
  mkdirSync(dirname(to), { recursive: true });
  copyFileSync(from, to);
}

copy(join(repo, "src/styles/tokens.css"), join(site, "styles/tokens.css"));
copy(join(repo, "src/app/icon.svg"), join(site, "app/icon.svg"));

for (const file of ["README.md", "DESIGN.md", "CONTRIBUTING.md", "SECURITY.md", "AGENTS.md"]) copy(join(repo, file), join(site, "content", file));
for (const file of readdirSync(join(repo, "docs")).filter((name) => name.endsWith(".md"))) copy(join(repo, "docs", file), join(site, "content/docs", file));

const shots = join(repo, "docs/assets/screenshots");
if (existsSync(shots)) for (const file of readdirSync(shots)) copy(join(shots, file), join(site, "public/screenshots", file));
const og = join(repo, "docs/assets/og.png");
if (existsSync(og)) copy(og, join(site, "public/og.png"));

console.log("Synced tokens, logo, docs and screenshots from the main repo.");
