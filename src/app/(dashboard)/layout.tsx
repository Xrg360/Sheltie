import { AppShell } from "@/components/shell/app-shell";
import { LabwardenProvider } from "@/lib/store";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <LabwardenProvider>
      <AppShell>{children}</AppShell>
    </LabwardenProvider>
  );
}
