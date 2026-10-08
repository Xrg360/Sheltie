import type { Metadata } from "next";
import { Suspense } from "react";

import { HostPage } from "@/components/pages/host";

export const metadata: Metadata = { title: "Host" };

export default function Page() {
  return (
    <Suspense>
      <HostPage />
    </Suspense>
  );
}
