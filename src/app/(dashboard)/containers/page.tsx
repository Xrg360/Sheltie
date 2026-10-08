import type { Metadata } from "next";
import { Suspense } from "react";

import { ContainersPage } from "@/components/pages/containers";

export const metadata: Metadata = { title: "Containers" };

export default function Page() {
  return (
    <Suspense>
      <ContainersPage />
    </Suspense>
  );
}
