import { readFileSync } from "node:fs";
import { join } from "node:path";

import { Marked } from "marked";

import { REPO_URL } from "./site";

export type Doc = { slug: string; file: string; title: string; description: string };

// Order here is the order in the docs sidebar.
export const DOCS: Doc[] = [
  { slug: "readme", file: "README.md", title: "Getting started", description: "Install Meerkat with Docker, configure monitors and Telegram, and use the API." },
  { slug: "architecture", file: "docs/ARCHITECTURE.md", title: "Architecture", description: "How Meerkat works today and the outage-resilient architecture it is moving towards." },
  { slug: "roadmap", file: "docs/ROADMAP.md", title: "Roadmap", description: "Known issues, the resilience plan, the contributor backlog and the release timeline." },
  { slug: "design", file: "DESIGN.md", title: "Design system", description: "Meerkat's UX principles, invariants, Savanna tokens and component rules." },
  { slug: "competitive-analysis", file: "docs/COMPETITIVE_ANALYSIS.md", title: "Feature comparison", description: "How Meerkat compares with Uptime Kuma, Beszel, Gatus, Netdata and healthchecks.io." },
  { slug: "ux-competitive-analysis", file: "docs/UX_COMPETITIVE_ANALYSIS.md", title: "UX comparison", description: "How Meerkat's user experience compares with other homelab monitoring tools." },
  { slug: "contributing", file: "CONTRIBUTING.md", title: "Contributing", description: "Set up a development environment and send your first pull request." },
  { slug: "agents", file: "AGENTS.md", title: "Rules for AI agents", description: "What automated coding agents must and must not change in Meerkat." },
  { slug: "security", file: "SECURITY.md", title: "Security", description: "How to report vulnerabilities and harden your Meerkat install." },
];

const bySource = new Map(DOCS.map((doc) => [doc.file, doc.slug]));

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/<[^>]+>/g, "")
    .replace(/[^\w\s-]/g, "")
    .trim()
    .replace(/\s/g, "-");
}

/** Maps repo-relative links (docs/ROADMAP.md#x, ../DESIGN.md) to website routes, everything else to GitHub. */
function rewriteHref(href: string, sourceFile: string): string {
  if (/^(https?:|mailto:|#)/.test(href)) return href;
  const [path, hash] = href.split("#");
  const base = sourceFile.includes("/") ? sourceFile.slice(0, sourceFile.lastIndexOf("/") + 1) : "";
  const parts = (base + path).split("/");
  const stack: string[] = [];
  for (const part of parts) {
    if (part === "..") stack.pop();
    else if (part && part !== ".") stack.push(part);
  }
  const resolved = stack.join("/");
  const slug = bySource.get(resolved);
  if (slug) return `/docs/${slug}/${hash ? `#${hash}` : ""}`;
  return `${REPO_URL}/blob/master/${resolved}${hash ? `#${hash}` : ""}`;
}

export function renderDoc(doc: Doc): { html: string; headings: Array<{ id: string; text: string; depth: number }>; hasMermaid: boolean } {
  const source = readFileSync(join(process.cwd(), "content", doc.file), "utf8");
  const headings: Array<{ id: string; text: string; depth: number }> = [];
  const seen = new Map<string, number>();
  let hasMermaid = false;
  const marked = new Marked({
    gfm: true,
    renderer: {
      heading({ tokens, depth }) {
        const text = this.parser.parseInline(tokens);
        let id = slugify(text);
        const count = seen.get(id) ?? 0;
        seen.set(id, count + 1);
        if (count) id = `${id}-${count}`;
        if (depth <= 3) headings.push({ id, text: text.replace(/<[^>]+>/g, ""), depth });
        return `<h${depth} id="${id}"><a class="anchor" href="#${id}" aria-hidden="true">#</a>${text}</h${depth}>\n`;
      },
      link({ href, title, tokens }) {
        const text = this.parser.parseInline(tokens);
        const target = rewriteHref(href, doc.file);
        const external = target.startsWith("http");
        return `<a href="${target}"${title ? ` title="${title}"` : ""}${external ? ' rel="noreferrer"' : ""}>${text}</a>`;
      },
      code({ text, lang }) {
        if (lang === "mermaid") {
          hasMermaid = true;
          return `<pre class="mermaid">${text.replace(/</g, "&lt;")}</pre>\n`;
        }
        const escaped = text.replace(/&/g, "&amp;").replace(/</g, "&lt;");
        return `<pre><code${lang ? ` class="language-${lang}"` : ""}>${escaped}</code></pre>\n`;
      },
    },
  });
  const html = marked.parse(source, { async: false }) as string;
  return { html, headings, hasMermaid };
}
