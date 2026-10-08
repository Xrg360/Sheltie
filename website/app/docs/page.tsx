import type { Metadata } from "next";
import Link from "next/link";

import { DOCS } from "@/lib/docs";

export const metadata: Metadata = {
  title: "Documentation",
  description: "Install, configure and extend Labwarden: setup guide, architecture, roadmap, design system and contributing guide.",
  alternates: { canonical: "/docs/" },
};

export default function DocsIndex() {
  return (
    <section className="section">
      <div className="container">
        <div className="section__head">
          <span className="eyebrow">Documentation</span>
          <h1>Labwarden docs</h1>
          <p className="muted">Everything here is generated from the Markdown files in the repository, so it always matches the code.</p>
        </div>
        <div className="grid grid--3">
          {DOCS.map((doc) => (
            <Link className="card" key={doc.slug} href={`/docs/${doc.slug}/`}>
              <h2 className="card__title-sm">{doc.title}</h2>
              <p className="muted">{doc.description}</p>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
