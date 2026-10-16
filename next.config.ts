import type { NextConfig } from "next";
import { PHASE_PRODUCTION_BUILD } from "next/constants";

// `next build` always writes static files to ./out: production runs no Node server. The Python
// process serves them on PORT and proxies /api/sheltie/* to the API (monitors/web.py).
// SHELTIE_STATIC_EXPORT=1 builds the same files with demo data (the public live demo).
// `next dev` keeps the API proxy in route.api.ts, which only the dev server picks up.
// Sheltie was called Meerkat before 0.3: MEERKAT_* variables still work as a fallback.
const env = (name: string) => process.env[`SHELTIE_${name}`] ?? process.env[`MEERKAT_${name}`];

export default function nextConfig(phase: string): NextConfig {
  const demo = env("STATIC_EXPORT") === "1";
  const basePath = demo ? env("BASE_PATH") || "" : "";
  const staticExport = demo || phase === PHASE_PRODUCTION_BUILD;

  return {
    reactStrictMode: true,
    poweredByHeader: false,
    pageExtensions: staticExport ? ["tsx", "ts"] : ["api.ts", "tsx", "ts"],
    ...(staticExport
      ? {
          output: "export",
          basePath,
          trailingSlash: true,
          images: { unoptimized: true },
          env: demo ? { NEXT_PUBLIC_SHELTIE_DEMO: "1", NEXT_PUBLIC_BASE_PATH: basePath } : {},
        }
      : {
          // Scripts and bookmarks that still call the pre-0.3 proxy path keep working.
          async rewrites() {
            return [{ source: "/api/meerkat/:path*", destination: "/api/sheltie/:path*" }];
          },
        }),
  };
}
