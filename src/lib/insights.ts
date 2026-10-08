// Turns raw payloads into answers: "what is wrong, how bad, and what can I do?"
// DESIGN.md principle 1 (answer before data) and 3 (every problem has a next step).

import { duration, relativeTime, safeName, toMillis } from "./format";
import { strings } from "./strings";
import type { EventItem, Snapshot, Tone } from "./types";

export type ProblemAction =
  | { kind: "link"; label: string; href: string }
  | { kind: "external"; label: string; href: string }
  | { kind: "restart"; label: string; container: string };

export type Problem = {
  id: string;
  tone: "bad" | "warn";
  title: string;
  body: string;
  since?: string | null;
  actions: ProblemAction[];
};

const s = strings.problems;

function firstLine(text: string | null | undefined, max = 140): string {
  const line = (text || "").split("\n")[0].trim();
  return line.length > max ? `${line.slice(0, max - 1)}…` : line;
}

function activeSince(events: EventItem[] | null, alertId: string): string | null {
  const match = (events || []).find((event) => event.alert_id === alertId && event.status === "active");
  return match?.ts ?? null;
}

export function problems(snapshot: Snapshot | null): Problem[] {
  if (!snapshot) return [];
  const list: Problem[] = [];
  const active = new Set(snapshot.status?.active_alerts ?? []);
  const events = snapshot.events ?? snapshot.status?.recent_events ?? [];
  const handled = new Set<string>();

  if (snapshot.status?.internet_up === false || active.has("internet.down")) {
    list.push({
      id: "internet.down",
      tone: "bad",
      title: s.internetDown,
      body: s.internetDownBody,
      since: activeSince(events, "internet.down"),
      actions: [{ kind: "link", label: s.viewNetwork, href: "/network" }],
    });
    handled.add("internet.down");
  }

  for (const site of snapshot.sites?.sites ?? []) {
    const id = `site.${safeName(site.name)}.down`;
    if (site.up && !active.has(id)) continue;
    const detail = site.error ? firstLine(site.error) : site.status_code ? `${strings.monitors.statusCode} ${site.status_code}` : "";
    list.push({
      id,
      tone: "bad",
      title: s.siteDown(site.name),
      body: s.siteDownBody(detail),
      since: activeSince(events, id),
      actions: [
        { kind: "link", label: s.viewMonitor, href: `/monitors?site=${encodeURIComponent(site.name)}` },
        { kind: "external", label: s.openSite, href: site.url },
      ],
    });
    handled.add(id);
  }

  for (const container of snapshot.docker?.containers ?? []) {
    if (container.status === "running" || container.user_stopped || container.blocked || !container.auto_heal_tracked) continue;
    list.push({
      id: `container.${container.name}`,
      tone: "bad",
      title: s.containerStopped(container.name),
      body: s.containerStoppedBody(container.status),
      actions: [{ kind: "restart", label: strings.containers.start, container: container.name }],
    });
  }

  for (const [label, iface] of Object.entries(snapshot.network?.interfaces ?? {})) {
    const id = `network.${label}`;
    if (iface.up) continue;
    // Only a problem if the interface was up before (auto-heal tracks those).
    const tracked = snapshot.status?.auto_heal?.active_network_interfaces?.includes(iface.name);
    if (!tracked) continue;
    list.push({
      id,
      tone: "warn",
      title: s.interfaceDown(label === "wifi" ? "Wi-Fi" : "Ethernet"),
      body: `${iface.name}: ${iface.operstate}${iface.carrier ? "" : ", no link"}`,
      actions: [{ kind: "link", label: s.viewNetwork, href: "/network" }],
    });
  }

  for (const id of active) {
    if (handled.has(id)) continue;
    const since = activeSince(events, id);
    if (id === "cpu.high") list.push({ id, tone: "warn", title: s.cpuHigh, body: "", since, actions: [{ kind: "link", label: s.viewHost, href: "/host" }] });
    else if (id === "ram.high") list.push({ id, tone: "warn", title: s.ramHigh, body: "", since, actions: [{ kind: "link", label: s.viewHost, href: "/host" }] });
    else if (id === "temperature.cpu.high") list.push({ id, tone: "bad", title: s.tempHigh, body: "", since, actions: [{ kind: "link", label: s.viewHost, href: "/host" }] });
    else if (id.startsWith("disk.")) {
      const path = snapshot.health?.disk_path || "/";
      list.push({ id, tone: "warn", title: s.diskHigh(path), body: "", since, actions: [{ kind: "link", label: s.viewHost, href: "/host" }] });
    } else if (!id.startsWith("site.")) {
      list.push({ id, tone: "warn", title: s.generic(id), body: "", since, actions: [{ kind: "link", label: s.viewIncidents, href: "/incidents" }] });
    }
  }

  return list.sort((a, b) => (a.tone === b.tone ? 0 : a.tone === "bad" ? -1 : 1));
}

export function healthyChecks(snapshot: Snapshot | null): number {
  if (!snapshot) return 0;
  let count = 0;
  count += snapshot.sites?.sites.filter((site) => site.up).length ?? 0;
  count += snapshot.docker?.containers.filter((container) => container.status === "running").length ?? 0;
  count += Object.values(snapshot.network?.interfaces ?? {}).filter((iface) => iface.up).length;
  if (snapshot.status?.internet_up) count += 1;
  if (snapshot.health) {
    count += [snapshot.health.cpu_percent < 90, snapshot.health.ram_percent < 90, snapshot.health.disk_percent < 90].filter(Boolean).length;
  }
  return count;
}

export function overallTone(list: Problem[]): Tone {
  if (list.some((problem) => problem.tone === "bad")) return "bad";
  if (list.length) return "warn";
  return "ok";
}

export function lastIncidentAge(events: EventItem[] | null): string | null {
  const incident = (events || []).find((event) => ["warning", "critical", "emergency"].includes(event.severity));
  return incident ? relativeTime(incident.ts) : null;
}

export type VisitSummary = { events: EventItem[]; away: string | null };

export function sinceLastVisit(events: EventItem[] | null, lastVisit: number | null): VisitSummary {
  if (!lastVisit) return { events: (events || []).slice(0, 5), away: null };
  const fresh = (events || []).filter((event) => (toMillis(event.ts) ?? 0) > lastVisit);
  return { events: fresh, away: duration(Date.now() - lastVisit) };
}

export function eventTone(event: EventItem): Tone {
  if (event.status === "recovered") return "ok";
  if (event.severity === "critical" || event.severity === "emergency") return "bad";
  if (event.severity === "warning") return "warn";
  if (event.source === "auto_heal") return "ok";
  return "unknown";
}

export function eventKind(event: EventItem): "problem" | "recovery" | "repair" | "info" {
  if (event.source === "auto_heal") return "repair";
  if (event.status === "recovered") return "recovery";
  if (["warning", "critical", "emergency"].includes(event.severity)) return "problem";
  return "info";
}

export function meterTone(value: number | null | undefined, warn = 75, bad = 90): Tone {
  if (value == null) return "unknown";
  if (value >= bad) return "bad";
  if (value >= warn) return "warn";
  return "ok";
}
