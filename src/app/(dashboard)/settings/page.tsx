import type { Metadata } from "next";
import { Suspense } from "react";

import { SettingsPage } from "@/components/pages/settings";

export const metadata: Metadata = { title: "Settings" };

export default function Page() {
  return (
    <Suspense>
      <SettingsPage />
    </Suspense>
  );
}
