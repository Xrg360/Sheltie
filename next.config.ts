import type { NextConfig } from "next";

// MEERKAT_STATIC_EXPORT=1 builds the dashboard as static files with demo data (the public live demo).
// The API proxy lives in route.api.ts, which only the normal server build picks up.
const staticExport = process.env.MEERKAT_STATIC_EXPORT === "1";
const basePath = process.env.MEERKAT_BASE_PATH || "";

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
        env: { NEXT_PUBLIC_MEERKAT_DEMO: "1", NEXT_PUBLIC_BASE_PATH: basePath },
      }
    : {}),
};

export default nextConfig;
