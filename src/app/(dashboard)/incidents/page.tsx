import type { Metadata } from "next";
import { Suspense } from "react";

import { IncidentsPage } from "@/components/pages/incidents";

export const metadata: Metadata = { title: "Incidents" };

export default function Page() {
  return (
    <Suspense>
      <IncidentsPage />
    </Suspense>
  );
}
