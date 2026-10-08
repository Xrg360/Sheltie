import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { JsonLd } from "@/components/json-ld";
import { Mermaid } from "@/components/mermaid";
import { DOCS, renderDoc } from "@/lib/docs";
import { REPO_URL, SITE_URL } from "@/lib/site";

export const dynamicParams = false;

export function generateStaticParams() {
  return DOCS.map((doc) => ({ slug: doc.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const doc = DOCS.find((item) => item.slug === slug);
  if (!doc) return {};
  return { title: doc.title, description: doc.description, alternates: { canonical: `/docs/${slug}/` } };
}

export default async function DocPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const doc = DOCS.find((item) => item.slug === slug);
  if (!doc) notFound();
  const { html, hasMermaid } = renderDoc(doc);
  return (
    <div className="container docs">
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "BreadcrumbList",
          itemListElement: [
            { "@type": "ListItem", position: 1, name: "Docs", item: `${SITE_URL}/docs/` },
            { "@type": "ListItem", position: 2, name: doc.title, item: `${SITE_URL}/docs/${slug}/` },
          ],
        }}
      />
      <nav className="docs-nav" aria-label="Documentation">
        {DOCS.map((item) => (
          <Link key={item.slug} href={`/docs/${item.slug}/`} aria-current={item.slug === slug ? "page" : undefined}>
            {item.title}
          </Link>
        ))}
      </nav>
      <article className="prose">
        <div dangerouslySetInnerHTML={{ __html: html }} />
        <p className="subtle">
          <a href={`${REPO_URL}/edit/master/${doc.file}`}>Edit this page on GitHub</a>
        </p>
      </article>
      {hasMermaid ? <Mermaid /> : null}
    </div>
  );
}
