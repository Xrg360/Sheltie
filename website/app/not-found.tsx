import Link from "next/link";

export default function NotFound() {
  return (
    <section className="section">
      <div className="container stack">
        <span className="eyebrow">404</span>
        <h1>This page wandered off.</h1>
        <p className="muted">Even a sheepdog can't round this page up. Try the home page or the docs.</p>
        <p className="hero__actions" style={{ justifyContent: "flex-start" }}>
          <Link className="btn btn--primary" href="/">
            Home
          </Link>
          <Link className="btn" href="/docs/">
            Docs
          </Link>
        </p>
      </div>
    </section>
  );
}
