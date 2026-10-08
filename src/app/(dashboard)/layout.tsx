import { AppShell } from "@/components/shell/app-shell";
import { SheltieProvider } from "@/lib/store";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <SheltieProvider>
      <AppShell>{children}</AppShell>
    </SheltieProvider>
  );
}
