import { AppShell } from "@/components/shell/app-shell";
import { MeerkatProvider } from "@/lib/store";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <MeerkatProvider>
      <AppShell>{children}</AppShell>
    </MeerkatProvider>
  );
}
