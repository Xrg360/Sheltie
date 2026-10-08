"use client";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="page">
      <section className="card">
        <div className="card__body">
          <h1 className="card__title">Something went wrong in the dashboard</h1>
          <p className="muted">{error.message}</p>
          <div>
            <button type="button" className="btn btn--primary" onClick={reset}>
              Try again
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}
