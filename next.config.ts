import type { NextConfig } from "next";

// SHELTIE_STATIC_EXPORT=1 builds the dashboard as static files with demo data (the public live demo).
// The API proxy lives in route.api.ts, which only the normal server build picks up.
// Sheltie was called Meerkat before 0.3: MEERKAT_* variables still work as a fallback.
const env = (name: string) => process.env[`SHELTIE_${name}`] ?? process.env[`MEERKAT_${name}`];
const staticExport = env("STATIC_EXPORT") === "1";
const basePath = env("BASE_PATH") || "";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  pageExtensions: staticExport ? ["tsx", "ts"] : ["api.ts", "tsx", "ts"],
  ...(staticExport
    ? {
        output: "export",
        basePath,
        trailingSlash: true,
        images: { unoptimized: true },
        env: { NEXT_PUBLIC_SHELTIE_DEMO: "1", NEXT_PUBLIC_BASE_PATH: basePath },
      }
    : {
        // Scripts and bookmarks that still call the pre-0.3 proxy path keep working.
        async rewrites() {
          return [{ source: "/api/meerkat/:path*", destination: "/api/sheltie/:path*" }];
        },
      }),
};

export default nextConfig;
