import type { MetadataRoute } from "next";

import { DOCS } from "@/lib/docs";
import { COMPARISONS, SITE_URL } from "@/lib/site";

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return [
    { url: `${SITE_URL}/`, lastModified: now, changeFrequency: "weekly", priority: 1 },
    { url: `${SITE_URL}/features/`, lastModified: now, changeFrequency: "monthly", priority: 0.8 },
    { url: `${SITE_URL}/docs/`, lastModified: now, changeFrequency: "weekly", priority: 0.8 },
    ...COMPARISONS.map((item) => ({ url: `${SITE_URL}/compare/${item.slug}/`, lastModified: now, changeFrequency: "monthly" as const, priority: 0.7 })),
    ...DOCS.map((doc) => ({ url: `${SITE_URL}/docs/${doc.slug}/`, lastModified: now, changeFrequency: "weekly" as const, priority: 0.6 })),
  ];
}
