"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

// The old "/monitoring" page moved to "/monitors". Keep old bookmarks working.
export default function MonitoringRedirect() {
  const router = useRouter();
  useEffect(() => router.replace("/monitors"), [router]);
  return (
    <main className="page">
      <p>
        This page moved to <Link href="/monitors">Monitors</Link>.
      </p>
    </main>
  );
}
