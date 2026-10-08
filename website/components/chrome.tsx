import { BookOpen, Star } from "lucide-react";
import Link from "next/link";

import { Logo } from "./logo";
import { REPO_URL, SLOGAN, VERSION } from "@/lib/site";

function GitHubMark({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

export function Header() {
  return (
    <header className="site-header">
      <div className="container site-header__inner">
        <Link href="/" className="brand" aria-label="Sheltie home">
          <Logo size={32} />
          <span className="brand__name">Sheltie</span>
        </Link>
        <nav className="site-nav" aria-label="Main">
          <Link href="/features/">Features</Link>
          <Link href="/compare/uptime-kuma/">Compare</Link>
          <Link href="/docs/">Docs</Link>
          <a href="/demo/">Live demo</a>
        </nav>
        <a className="btn btn--sm" href={REPO_URL}>
          <GitHubMark />
          <span className="hide-sm">Star on GitHub</span>
        </a>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="container site-footer__inner">
        <div className="stack stack--sm">
          <span className="brand">
            <Logo size={24} />
            <span className="brand__name">Sheltie</span>
          </span>
          <p className="muted">{SLOGAN} Open-source homelab monitoring that tells you what happened while you were offline.</p>
          <p className="subtle">
            v{VERSION} · Apache-2.0 · No telemetry · Formerly Meerkat
          </p>
        </div>
        <nav className="footer-links" aria-label="Footer">
          <div className="stack stack--sm">
            <strong>Product</strong>
            <Link href="/features/">Features</Link>
            <a href="/demo/">Live demo</a>
            <Link href="/docs/roadmap/">Roadmap</Link>
          </div>
          <div className="stack stack--sm">
            <strong>Compare</strong>
            <Link href="/compare/uptime-kuma/">vs Uptime Kuma</Link>
            <Link href="/compare/beszel/">vs Beszel</Link>
            <Link href="/compare/netdata/">vs Netdata</Link>
          </div>
          <div className="stack stack--sm">
            <strong>Community</strong>
            <a href={REPO_URL}>
              <Star size={13} aria-hidden="true" /> GitHub
            </a>
            <Link href="/docs/contributing/">
              <BookOpen size={13} aria-hidden="true" /> Contributing
            </Link>
            <Link href="/docs/security/">Security</Link>
          </div>
        </nav>
      </div>
    </footer>
  );
}

export { GitHubMark };
