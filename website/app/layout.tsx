import type { Metadata, Viewport } from "next";

import "./site.css";
import { Footer, Header } from "@/components/chrome";
import { DESCRIPTION, REPO_URL, SEO_TITLE, SITE_URL, TAGLINE } from "@/lib/site";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: `Labwarden — ${SEO_TITLE}`, template: "%s · Labwarden" },
  description: DESCRIPTION,
  applicationName: "Labwarden",
  keywords: ["labwarden", "meerkat homelab monitor", "homelab monitoring", "self-hosted monitoring", "uptime monitor", "docker monitoring", "uptime kuma alternative", "telegram alerts", "raspberry pi monitoring", "auto-heal docker", "open source"],
  authors: [{ name: "xrg360", url: REPO_URL }],
  alternates: { canonical: "/" },
  openGraph: { type: "website", siteName: "Labwarden", title: `Labwarden — ${TAGLINE}`, description: DESCRIPTION, url: SITE_URL, images: [{ url: "/og.png", width: 1200, height: 630, alt: "Labwarden dashboard" }] },
  twitter: { card: "summary_large_image", title: `Labwarden — ${TAGLINE}`, description: DESCRIPTION, images: ["/og.png"] },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fffaf0" },
    { media: "(prefers-color-scheme: dark)", color: "#081414" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        <Header />
        <main id="main">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
