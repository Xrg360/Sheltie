import { CircleCheck } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { GitHubMark } from "@/components/chrome";
import { JsonLd } from "@/components/json-ld";
import { COMPARISONS, REPO_URL, SITE_URL } from "@/lib/site";

export const dynamicParams = false;

export function generateStaticParams() {
  return COMPARISONS.map((comparison) => ({ slug: comparison.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const comparison = COMPARISONS.find((item) => item.slug === slug);
  if (!comparison) return {};
  return {
    title: `Sheltie vs ${comparison.name}: a ${comparison.name} alternative for homelabs`,
    description: `An honest comparison of Sheltie and ${comparison.name}: what each does best, when to choose which, and how to run them together.`,
    alternates: { canonical: `/compare/${slug}/` },
  };
}

export default async function ComparePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const comparison = COMPARISONS.find((item) => item.slug === slug);
  if (!comparison) notFound();
  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "BreadcrumbList",
          itemListElement: [
            { "@type": "ListItem", position: 1, name: "Sheltie", item: SITE_URL },
            { "@type": "ListItem", position: 2, name: `Sheltie vs ${comparison.name}`, item: `${SITE_URL}/compare/${slug}/` },
          ],
        }}
      />
      <section className="section">
        <div className="container stack">
          <span className="eyebrow">Compare</span>
          <h1>Sheltie vs {comparison.name}</h1>
          <p className="hero__lead">{comparison.summary}</p>
          <nav className="hero__actions" aria-label="Other comparisons" style={{ justifyContent: "flex-start" }}>
            {COMPARISONS.filter((item) => item.slug !== slug).map((item) => (
              <Link key={item.slug} className="btn btn--sm" href={`/compare/${item.slug}/`}>
                vs {item.name}
              </Link>
            ))}
          </nav>
        </div>
      </section>
      <section className="section section--alt">
        <div className="container grid grid--2">
          <article className="card">
            <h2>
              <a href={comparison.url}>{comparison.name}</a> is great at
            </h2>
            <ul className="check-list">
              {comparison.theyAreGreatAt.map((item) => (
                <li key={item}>
                  <CircleCheck size={18} aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </article>
          <article className="card">
            <h2>Sheltie adds</h2>
            <ul className="check-list">
              {comparison.sheltieAdds.map((item) => (
                <li key={item}>
                  <CircleCheck size={18} aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </article>
        </div>
      </section>
      <section className="section">
        <div className="container grid grid--3">
          <article className="card">
            <h3>Choose {comparison.name} if…</h3>
            <p className="muted">{comparison.chooseThem}</p>
          </article>
          <article className="card">
            <h3>Choose Sheltie if…</h3>
            <p className="muted">{comparison.chooseSheltie}</p>
          </article>
          <article className="card">
            <h3>Or run both</h3>
            <p className="muted">{comparison.together}</p>
          </article>
        </div>
      </section>
      <section className="section">
        <div className="container">
          <div className="cta">
            <h2>See the difference in 30 seconds.</h2>
            <p>The live demo runs the real Sheltie dashboard with a simulated homelab: a power cut last night, a healed container and a site that is down right now.</p>
            <div className="hero__actions">
              <a className="btn btn--primary" href="/demo/">
                Open the live demo
              </a>
              <a className="btn" href={REPO_URL}>
                <GitHubMark /> Star on GitHub
              </a>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
