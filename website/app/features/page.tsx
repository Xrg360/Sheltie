import type { Metadata } from "next";

import { FeatureGrid } from "@/components/features";
import { FEATURES } from "@/lib/site";

export const metadata: Metadata = {
  title: "Features",
  description: "Everything Labwarden does for your homelab: answer-first dashboard, since-your-last-visit, Docker auto-heal, network failover, website checks, host health, Telegram chat-ops, and what is planned next.",
  alternates: { canonical: "/features/" },
};

export default function FeaturesPage() {
  const shipped = FEATURES.filter((feature) => !feature.status);
  const planned = FEATURES.filter((feature) => feature.status === "planned");
  return (
    <>
      <section className="section">
        <div className="container">
          <div className="section__head">
            <span className="eyebrow">Features</span>
            <h1>Everything Labwarden does today</h1>
            <p className="muted">One small container watches your websites, containers, network and host, and turns it all into plain answers.</p>
          </div>
          <FeatureGrid features={shipped} />
        </div>
      </section>
      <section className="section section--alt">
        <div className="container">
          <div className="section__head">
            <span className="eyebrow">Roadmap</span>
            <h2>Coming next</h2>
            <p className="muted">
              These are planned and tracked in the <a href="/docs/roadmap/">public roadmap</a>. Many are good first issues if you want to help build them.
            </p>
          </div>
          <FeatureGrid features={planned} />
        </div>
      </section>
    </>
  );
}
