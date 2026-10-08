import Link from "next/link";

export default function NotFound() {
  return (
    <main className="page">
      <section className="card">
        <div className="card__body">
          <h1 className="card__title">Page not found</h1>
          <p className="muted">That page doesn&apos;t exist. It may have moved in a recent update.</p>
          <div>
            <Link className="btn btn--primary" href="/">
              Go to Overview
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
