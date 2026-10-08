import type { Metadata } from "next";
import { Suspense } from "react";

import { NetworkPage } from "@/components/pages/network";

export const metadata: Metadata = { title: "Network" };

export default function Page() {
  return (
    <Suspense>
      <NetworkPage />
    </Suspense>
  );
}
