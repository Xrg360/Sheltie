import type { Metadata, Viewport } from "next";

import "@/styles/tokens.css";
import "@/styles/base.css";
import "@/styles/components.css";
import { THEME_BOOTSTRAP } from "@/lib/prefs";

const IS_DEMO = process.env.NEXT_PUBLIC_LABWARDEN_DEMO === "1";

export const metadata: Metadata = {
  title: { default: "Labwarden", template: "%s · Labwarden" },
  description: "Labwarden keeps watch over your homelab: uptime, Docker, network and host health, and what happened while you were away.",
  applicationName: "Labwarden",
  robots: IS_DEMO ? { index: false, follow: true } : { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fffaf0" },
    { media: "(prefers-color-scheme: dark)", color: "#081414" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
