import { Activity, Boxes, Cpu, History, LayoutDashboard, Network, Settings } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { strings } from "./strings";

// Navigation order is a DESIGN.md invariant. Do not reorder without a design review.
export type NavItem = { href: string; label: string; icon: LucideIcon; key: string; mobile: boolean };

export const NAV: NavItem[] = [
  { href: "/", label: strings.nav.overview, icon: LayoutDashboard, key: "o", mobile: true },
  { href: "/incidents", label: strings.nav.incidents, icon: History, key: "i", mobile: true },
  { href: "/monitors", label: strings.nav.monitors, icon: Activity, key: "m", mobile: true },
  { href: "/containers", label: strings.nav.containers, icon: Boxes, key: "c", mobile: true },
  { href: "/network", label: strings.nav.network, icon: Network, key: "n", mobile: false },
  { href: "/host", label: strings.nav.host, icon: Cpu, key: "h", mobile: false },
  { href: "/settings", label: strings.nav.settings, icon: Settings, key: "s", mobile: false },
];

export const REPO_URL = "https://github.com/xrg360/meerkat";
export const DOCS_URL = "https://meerkat.simplewebsite.in/docs/";

export function isActive(pathname: string, href: string): boolean {
  const path = pathname.replace(/\/$/, "") || "/";
  return href === "/" ? path === "/" : path === href || path.startsWith(`${href}/`);
}
