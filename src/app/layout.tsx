import type { Metadata, Viewport } from "next";

import "@/styles/tokens.css";
import "@/styles/base.css";
import "@/styles/components.css";
import { AppInstall } from "@/components/shell/pwa";
import { THEME_BOOTSTRAP } from "@/lib/prefs";

const IS_DEMO = process.env.NEXT_PUBLIC_SHELTIE_DEMO === "1";
// The public demo is served under a base path; files in public/ need it spelled out.
const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export const metadata: Metadata = {
  title: { default: "Sheltie", template: "%s · Sheltie" },
  description: "Sheltie keeps watch over your homelab: uptime, Docker, network and host health, and what happened while you were away.",
  applicationName: "Sheltie",
  manifest: `${BASE}/manifest.webmanifest`,
  icons: { apple: `${BASE}/icons/apple-touch-icon.png` },
  appleWebApp: { capable: true, title: "Sheltie", statusBarStyle: "default" },
  robots: IS_DEMO ? { index: false, follow: true } : { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fffaf0" },
    { media: "(prefers-color-scheme: dark)", color: "#0c0c0d" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
      </head>
      <body>
        {children}
        <AppInstall />
      </body>
    </html>
  );
}
