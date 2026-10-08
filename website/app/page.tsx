import { ArrowRight, CircleCheck, CloudOff, PlugZap, ServerCrash } from "lucide-react";
import Link from "next/link";

import { GitHubMark } from "@/components/chrome";
import { FeatureGrid } from "@/components/features";
import { JsonLd } from "@/components/json-ld";
import { COMPARISONS, DESCRIPTION, FAQ, FEATURES, QUICK_START, REPO_URL, SITE_URL, TAGLINE, VERSION } from "@/lib/site";

const STORIES = [
  {
    icon: CloudOff,
    title: "Your ISP drops for two hours",
    today: "Meerkat records when the internet went down and when it came back. Open the dashboard later and “Since your last visit” tells you the whole story.",
    next: "Planned: alerts queue up during the outage and arrive as one digest when you are back online.",
  },
  {
    icon: PlugZap,
    title: "The power goes out overnight",
    today: "When the host comes back, Meerkat announces it booted, restarts containers that crashed, and leaves the ones you stopped on purpose alone.",
    next: "Planned: on boot it will say whether it was a power cut, a crash or a reboot, and for how long.",
  },
  {
    icon: ServerCrash,
    title: "The server itself goes dark",
    today: "Pair Meerkat with an external push monitor (for example Uptime Kuma or healthchecks.io) to be told when the whole host stops answering.",
    next: "Planned: a built-in heartbeat and an off-site Meerkat Sentinel with the last known state of your lab.",
  },
];

export default function Home() {
  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "SoftwareApplication",
          name: "Meerkat",
          applicationCategory: "DeveloperApplication",
          operatingSystem: "Linux (Docker), amd64 and arm64",
          softwareVersion: VERSION,
          description: DESCRIPTION,
          url: SITE_URL,
          downloadUrl: REPO_URL,
          license: "https://www.apache.org/licenses/LICENSE-2.0",
          isAccessibleForFree: true,
          offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
          image: `${SITE_URL}/og.png`,
        }}
      />
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "FAQPage",
          mainEntity: FAQ.map((item) => ({ "@type": "Question", name: item.q, acceptedAnswer: { "@type": "Answer", text: item.a } })),
        }}
      />

      <section className="hero">
        <div className="container hero__inner">
          <span className="pill pill--accent">Open source · Self-hosted · v{VERSION}</span>
          <h1>{TAGLINE}</h1>
          <p className="hero__lead">
            Meerkat keeps watch over your Docker homelab: websites, containers, network failover and host health. It tells you in plain words what is wrong, fixes what it
            safely can, and shows what happened while you were away.
          </p>
          <div className="hero__actions">
            <a className="btn btn--primary" href="/demo/">
              Try the live demo <ArrowRight size={16} aria-hidden="true" />
            </a>
            <a className="btn" href={REPO_URL}>
              <GitHubMark /> Star on GitHub
            </a>
          </div>
          <p className="subtle">Free under Apache-2.0 · No telemetry · Runs on a Raspberry Pi</p>
          <figure className="shot">
            <img src="/screenshots/overview-light.png" width={1440} height={900} alt="Meerkat Overview: “2 problems need attention”, with a down blog and a stopped container, each with a fix-it button, plus a summary of events since your last visit." />
          </figure>
        </div>
      </section>

      <section className="section section--alt" aria-labelledby="stories">
        <div className="container">
          <div className="section__head">
            <span className="eyebrow">Built for the bad days</span>
            <h2 id="stories">Other dashboards go blank when things break. Meerkat is built for exactly that moment.</h2>
          </div>
          <div className="grid grid--3">
            {STORIES.map((story) => (
              <article className="card story" key={story.title}>
                <span className="card__icon" aria-hidden="true">
                  <story.icon size={20} />
                </span>
                <h3>{story.title}</h3>
                <p>{story.today}</p>
                <p className="subtle">{story.next}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section" aria-labelledby="features">
        <div className="container">
          <div className="section__head">
            <span className="eyebrow">Features</span>
            <h2 id="features">Calm for beginners. Fast for experts.</h2>
            <p className="muted">Everything a homelab needs to stay watched, in one small container.</p>
          </div>
          <FeatureGrid features={FEATURES.filter((feature) => !feature.status).slice(0, 9)} />
          <p className="more-link">
            <Link href="/features/">
              See every feature and what is planned <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </p>
        </div>
      </section>

      <section className="section section--alt" aria-labelledby="mobile">
        <div className="container split">
          <div className="stack">
            <span className="eyebrow">On your phone</span>
            <h2 id="mobile">Check your lab from the train.</h2>
            <ul className="check-list">
              {["One sentence tells you if anything is wrong", "Bottom tabs and sheets designed for thumbs", "Start a crashed container with one tap, after a confirmation", "Silence alerts for an hour while you work on something", "Two-way Telegram commands when you don't want to open a browser"].map((item) => (
                <li key={item}>
                  <CircleCheck size={18} aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <figure className="shot shot--phone">
            <img src="/screenshots/overview-mobile.png" width={390} height={844} alt="Meerkat on a phone: the Overview with problems and a bottom tab bar." />
          </figure>
        </div>
      </section>

      <section className="section" aria-labelledby="install">
        <div className="container split">
          <div className="stack">
            <span className="eyebrow">Quick start</span>
            <h2 id="install">Running in under a minute.</h2>
            <p className="muted">One container with host networking and read-only Docker socket access. Add Telegram later with two environment variables.</p>
            <p>
              <Link href="/docs/readme/">Read the full setup guide</Link>
            </p>
          </div>
          <pre className="code">
            <code>{QUICK_START}</code>
          </pre>
        </div>
      </section>

      <section className="section section--alt" aria-labelledby="compare">
        <div className="container">
          <div className="section__head">
            <span className="eyebrow">Compare</span>
            <h2 id="compare">Works alongside the tools you already love.</h2>
          </div>
          <div className="grid grid--3">
            {COMPARISONS.map((comparison) => (
              <Link className="card" key={comparison.slug} href={`/compare/${comparison.slug}/`}>
                <h3>Meerkat vs {comparison.name}</h3>
                <p className="muted">{comparison.chooseMeerkat}</p>
                <span>
                  Read the comparison <ArrowRight size={14} aria-hidden="true" />
                </span>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="section" aria-labelledby="faq">
        <div className="container">
          <div className="section__head">
            <span className="eyebrow">FAQ</span>
            <h2 id="faq">Questions</h2>
          </div>
          <div className="faq stack">
            {FAQ.map((item) => (
              <details key={item.q}>
                <summary>{item.q}</summary>
                <p>{item.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      <section className="section" aria-labelledby="cta">
        <div className="container">
          <div className="cta">
            <h2 id="cta">Give your homelab a lookout.</h2>
            <p>Meerkat is built in the open. Star the repo to follow along, or pick a good first issue and add the monitor you wish existed.</p>
            <div className="hero__actions">
              <a className="btn btn--primary" href={REPO_URL}>
                <GitHubMark /> Star on GitHub
              </a>
              <Link className="btn" href="/docs/contributing/">
                Contribute
              </Link>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
