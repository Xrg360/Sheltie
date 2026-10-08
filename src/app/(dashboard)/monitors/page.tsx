import type { Metadata } from "next";
import { Suspense } from "react";

import { MonitorsPage } from "@/components/pages/monitors";

export const metadata: Metadata = { title: "Monitors" };

export default function Page() {
  return (
    <Suspense>
      <MonitorsPage />
    </Suspense>
  );
}
