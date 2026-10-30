// A believable homelab used by the public live demo, screenshots and UI development
// without a backend (NEXT_PUBLIC_SHELTIE_DEMO=1). The story: a power cut last night,
// an auto-healed container this morning, and the blog is down right now.

import { safeName } from "./format";
import type { AcRecoveryMode, ActionResult, Container, EventItem, NameCheck, NameRecord, NameTargets, Site, SiteSample, Snapshot } from "./types";

const MIN = 60_000;
const HOUR = 60 * MIN;

function seeded(seed: number) {
  let value = seed;
  return () => {
    value = (value * 16807) % 2147483647;
    return (value - 1) / 2147483646;
  };
}

const START = Date.now();
const random = seeded(42);

function history(base: number, jitter: number, downFrom?: number, flaps: number[] = []): SiteSample[] {
  const list: SiteSample[] = [];
  for (let index = 0; index < 80; index += 1) {
    const ts = Math.round((START - (79 - index) * 30_000) / 1000);
    const down = (downFrom != null && index >= downFrom) || flaps.includes(index);
    list.push({
      ts,
      up: !down,
      status_code: down ? 502 : 200,
      latency_ms: down ? Math.round(20 + random() * 30) : Math.round(base + (random() - 0.5) * jitter * 2),
    });
  }
  return list;
}

function site(name: string, url: string, base: number, jitter: number, downFrom?: number, flaps: number[] = []): Site {
  const samples = history(base, jitter, downFrom, flaps);
  const last = samples[samples.length - 1];
  return {
    name,
    url,
    up: last.up,
    status_code: last.status_code,
    latency_ms: last.latency_ms,
    error: last.up ? null : "502 Server Error: Bad Gateway for url: https://blog.example.com/",
    expected_status: [200],
    history: samples,
  };
}

function iso(offsetMs: number): string {
  return new Date(START - offsetMs).toISOString();
}

function clock(offsetMs: number): string {
  return new Date(START - offsetMs).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
}

type DemoState = {
  sites: Site[];
  containers: Container[];
  events: EventItem[];
  activeAlerts: string[];
  silencedUntil: number | null;
  silenced: boolean;
  acRecovery: AcRecoveryMode;
  names: NameRecord[];
  zone: { label: string; tld: string };
  tailnetOnly: boolean;
};

const DEMO_TAILNET_IP = "100.101.102.103";

function nameRecord(id: number, name: string, target: string, port: number | null, label: string, reachable: NameRecord["reachable"] = { ok: true, why: null }): NameRecord {
  const zone = "home.internals";
  return {
    id,
    name,
    fqdn: `${name}.${zone}`,
    kind: port ? "proxy" : "device",
    url: `http://${name}.${zone}`,
    points_to: port ? DEMO_TAILNET_IP : target,
    target_host: target,
    target_port: port,
    scheme: "http",
    websockets: true,
    source: port ? `container:${target}` : "device",
    label,
    synced: true,
    sync_error: null,
    created_at: Math.round((Date.now() - 30 * 24 * HOUR) / 1000),
    updated_at: Math.round((Date.now() - 30 * 24 * HOUR) / 1000),
    reachable,
  };
}

const state: DemoState = {
  sites: [
    site("Nextcloud", "https://cloud.home.example", 118, 30),
    site("Jellyfin", "https://media.home.example", 84, 20),
    site("Home Assistant", "https://ha.home.example", 58, 12),
    site("Vaultwarden", "https://vault.home.example", 44, 10),
    site("Immich", "https://photos.home.example", 205, 60, undefined, [21, 22]),
    site("Grafana", "https://grafana.home.example", 138, 35),
    site("Blog", "https://blog.example.com", 96, 20, 66),
    site("Status page", "https://status.example.com", 32, 8),
  ],
  containers: [
    { name: "nextcloud", status: "running", image: "nextcloud:29-apache" },
    { name: "nextcloud-db", status: "running", image: "postgres:16" },
    { name: "jellyfin", status: "running", image: "jellyfin/jellyfin:10.9" },
    { name: "homeassistant", status: "running", image: "ghcr.io/home-assistant/home-assistant:stable" },
    { name: "vaultwarden", status: "running", image: "vaultwarden/server:1.32" },
    { name: "immich-server", status: "running", image: "ghcr.io/immich-app/immich-server:release" },
    { name: "immich-ml", status: "running", image: "ghcr.io/immich-app/immich-machine-learning:release" },
    { name: "grafana", status: "running", image: "grafana/grafana:11.2" },
    { name: "prometheus", status: "running", image: "prom/prometheus:v2.54" },
    { name: "blog", status: "exited", image: "ghost:5-alpine" },
    { name: "cloudflared", status: "running", image: "cloudflare/cloudflared:2024.9" },
    { name: "minecraft", status: "exited", image: "itzg/minecraft-server:java21", user_stopped: true },
    { name: "sheltie", status: "running", image: "ghcr.io/xrg360/sheltie:0.2.0", blocked: true },
  ].map((container) => ({
    ...container,
    auto_heal_tracked: !container.user_stopped && !container.blocked,
  })),
  events: [
    {
      ts: iso(6 * MIN),
      alert_id: "site.blog.down",
      source: "site",
      severity: "critical",
      status: "active",
      title: "Site down: Blog",
      body: "Site: Blog\nURL: https://blog.example.com\nExpected: 200\nStatus: 502\nLatency: 31ms",
    },
    {
      ts: iso(7 * MIN),
      alert_id: "docker.blog.die",
      source: "docker",
      severity: "critical",
      status: "event",
      title: "Container died",
      body: `Container: blog\nEvent: died\nTime: ${clock(7 * MIN)}`,
    },
    {
      ts: iso(3 * HOUR),
      alert_id: "auto_heal.container.immich-ml",
      source: "auto_heal",
      severity: "info",
      status: "event",
      title: "Container auto-heal",
      body: "Container: immich-ml\nPrevious status: exited\nResult: Container started: immich-ml",
    },
    {
      ts: iso(3 * HOUR + 4 * MIN),
      alert_id: "docker.immich-ml.die",
      source: "docker",
      severity: "critical",
      status: "event",
      title: "Container died",
      body: `Container: immich-ml\nEvent: died\nTime: ${clock(3 * HOUR + 4 * MIN)}`,
    },
    {
      ts: iso(8 * HOUR + 52 * MIN),
      alert_id: "internet.down",
      source: "internet",
      severity: "info",
      status: "recovered",
      title: "Internet lost recovered",
      body: "At least one probe is reachable: 1.1.1.1, 8.8.8.8",
    },
    {
      ts: iso(9 * HOUR + 5 * MIN),
      alert_id: "sheltie.boot",
      source: "sheltie",
      severity: "info",
      status: "event",
      title: "Sheltie booted",
      body: "Docker container started and monitoring is active.",
    },
    {
      ts: iso(11 * HOUR + 20 * MIN),
      alert_id: "internet.down",
      source: "internet",
      severity: "critical",
      status: "active",
      title: "Internet lost",
      body: "All probes failed: 1.1.1.1, 8.8.8.8",
    },
    {
      ts: iso(25 * HOUR),
      alert_id: "disk.root.high",
      source: "disk",
      severity: "info",
      status: "recovered",
      title: "Disk usage high recovered",
      body: "Filesystem: /\nUsage: 78%",
    },
    {
      ts: iso(26 * HOUR + 30 * MIN),
      alert_id: "disk.root.high",
      source: "disk",
      severity: "warning",
      status: "active",
      title: "Disk usage high",
      body: "Filesystem: /\nUsage: 92%\nThreshold: 90%",
    },
    {
      ts: iso(29 * HOUR),
      alert_id: "network.route",
      source: "network",
      severity: "info",
      status: "changed",
      title: "Active route changed",
      body: "Current default route: enp2s0",
    },
    {
      ts: iso(29 * HOUR + 12 * MIN),
      alert_id: "network.route",
      source: "network",
      severity: "info",
      status: "changed",
      title: "Active route changed",
      body: "Current default route: wlp1s0",
    },
    {
      ts: iso(29 * HOUR + 12 * MIN + 30_000),
      alert_id: "network.ethernet",
      source: "network",
      severity: "warning",
      status: "changed",
      title: "Ethernet disconnected",
      body: "Interface: enp2s0\nState: down\nCarrier: False\nIPv4: False\nUsing Wi-Fi",
    },
  ],
  activeAlerts: ["site.blog.down"],
  silencedUntil: null,
  silenced: false,
  // The demo server came back by itself after last night's power cut, so power-on with AC is on.
  acRecovery: "on",
  names: [
    nameRecord(1, "cloud", "nextcloud", 80, "nextcloud"),
    nameRecord(2, "media", "jellyfin", 8096, "jellyfin"),
    nameRecord(3, "ha", "homeassistant", 8123, "homeassistant"),
    nameRecord(4, "blog", "blog", 2368, "blog", { ok: false, why: "Nothing answered on blog:2368" }),
    nameRecord(5, "nas", "100.88.12.40", null, "nas (Tailscale device)"),
  ],
  zone: { label: "home", tld: "internals" },
  tailnetOnly: true,
};

function wave(period: number, phase = 0): number {
  return Math.sin((Date.now() / period) * Math.PI * 2 + phase);
}

function pushEvent(event: Omit<EventItem, "ts">) {
  state.events.unshift({ ...event, ts: new Date().toISOString() });
}

export function demoSnapshot(): Snapshot {
  if (state.silencedUntil && Date.now() / 1000 >= state.silencedUntil) {
    state.silenced = false;
    state.silencedUntil = null;
  }
  const up = state.sites.filter((entry) => entry.up).length;
  const cpu = 22 + wave(90_000) * 9 + wave(17_000, 1) * 4;
  const ram = 61 + wave(240_000) * 3;
  return {
    fetchedAt: Date.now(),
    status: {
      version: "0.2.0",
      started_at: iso(9 * HOUR + 5 * MIN),
      telegram_enabled: true,
      alerts_silenced: state.silenced,
      alerts_silenced_until: state.silencedUntil,
      internet_up: true,
      ethernet_up: true,
      wifi_up: true,
      default_route: "enp2s0",
      default_route_label: "wired/eth (enp2s0)",
      auto_heal: {
        enabled: true,
        interval: 300,
        active_containers: state.containers.filter((entry) => entry.auto_heal_tracked).map((entry) => entry.name),
        active_network_interfaces: ["enp2s0", "wlp1s0"],
      },
      active_alerts: [...state.activeAlerts],
      recent_events: state.events.slice(0, 20),
    },
    health: {
      cpu_percent: Math.max(3, cpu),
      ram_percent: ram,
      disk_percent: 78.4,
      disk_path: "/",
      cpu_temperature: 51 + wave(120_000, 2) * 3,
      load_average: [0.82 + wave(60_000) * 0.2, 0.74, 0.69],
    },
    network: {
      interfaces: {
        ethernet: { name: "enp2s0", operstate: "up", carrier: true, has_ip: true, up: true },
        wifi: { name: "wlp1s0", operstate: "up", carrier: true, has_ip: true, up: true },
      },
      default_route: "enp2s0",
      default_route_label: "wired/eth (enp2s0)",
      internet_up: true,
    },
    docker: { available: true, containers: state.containers.map((entry) => ({ ...entry })) },
    sites: { total: state.sites.length, up, down: state.sites.length - up, sites: state.sites.map((entry) => ({ ...entry })) },
    events: [...state.events],
    power: {
      vendor: "Dell Inc.",
      model: "OptiPlex 3070 Micro",
      ac_online: true,
      battery_percent: null,
      battery_status: null,
      ac_recovery: { supported: true, mode: state.acRecovery, modes: ["off", "last", "on"], method: "dell-smbios", reason: null },
    },
    names: {
      enabled: true,
      zone: demoZone(),
      domain: { ...state.zone },
      server: { name: "homelab", ip: DEMO_TAILNET_IP, dns_name: "homelab.tail1234.ts.net", error: null },
      records: state.names.map((entry) => ({ ...entry, fqdn: `${entry.name}.${demoZone()}`, url: `http://${entry.name}.${demoZone()}` })),
      tailnet_only: state.tailnetOnly,
      npm_configured: true,
      last_sync: { at: Math.round(Date.now() / 1000) - 120, ok: true, error: null },
    },
  };
}

function demoZone(): string {
  return `${state.zone.label}.${state.zone.tld}`;
}

export function demoNameTargets(): NameTargets {
  const apps = [
    ["nextcloud", 80],
    ["jellyfin", 8096],
    ["homeassistant", 8123],
    ["vaultwarden", 80],
    ["immich-server", 2283],
    ["grafana", 3000],
    ["blog", 2368],
  ] as const;
  return {
    server: { name: "homelab", ip: DEMO_TAILNET_IP },
    apps: apps.map(([name, port]) => ({
      id: `container:${name}:${port}`,
      source: `container:${name}`,
      name,
      label: `${name} · port ${port} on the homelab network`,
      host: name,
      port,
      detail: `port ${port} on the homelab network`,
      disabled: false,
      state: state.containers.find((entry) => entry.name === name)?.status ?? "running",
    })),
    ports: [{ id: "port:22", source: "port:22", name: "SSH", label: "SSH · port 22", host: DEMO_TAILNET_IP, port: 22, detail: "port 22", disabled: false }],
    devices: [
      { name: "homelab", dns_name: "homelab.tail1234.ts.net", ip: DEMO_TAILNET_IP, os: "linux", online: true, is_self: true },
      { name: "nas", dns_name: "nas.tail1234.ts.net", ip: "100.88.12.40", os: "linux", online: true, is_self: false },
      { name: "priya-phone", dns_name: "priya-phone.tail1234.ts.net", ip: "100.70.176.88", os: "android", online: false, is_self: false },
    ],
    errors: {},
  };
}

export function demoNameChecks(): NameCheck[] {
  const zone = demoZone();
  return [
    { id: "tailscale", title: "Tailscale", ok: true, detail: `This server is homelab (${DEMO_TAILNET_IP}).`, fix: null },
    { id: "dns", title: "DNS server", ok: true, detail: `Answering for *.${zone} on ${DEMO_TAILNET_IP}.`, fix: null },
    { id: "split_dns", title: "Tailscale split DNS", ok: true, detail: `Your devices ask ${DEMO_TAILNET_IP} about ${zone}.`, fix: null },
    { id: "npm", title: "Nginx Proxy Manager", ok: true, detail: "Connected as sheltie@example.com (Nginx Proxy Manager 2.12.1).", fix: null },
    { id: "docker", title: "App discovery", ok: true, detail: "Reading the container list.", fix: null },
  ];
}

function demoNameAction(action: string, body: Record<string, unknown>): ActionResult {
  const zone = demoZone();
  if (action === "add" || action === "update") {
    const name = String(body.name || "").trim().toLowerCase();
    if (!/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(name)) return { ok: false, error: "Name can use only a-z, 0-9 and hyphens, and can't start or end with a hyphen.", field: "name" };
    const id = action === "add" ? Math.max(0, ...state.names.map((entry) => entry.id)) + 1 : Number(body.id);
    if (state.names.some((entry) => entry.name === name && entry.id !== id)) return { ok: false, error: `${name}.${zone} already exists.`, field: "name" };
    const port = body.port ? Number(body.port) : null;
    const record = nameRecord(id, name, String(body.host || ""), port, String(body.label || body.host || ""));
    state.names = [...state.names.filter((entry) => entry.id !== id), record].sort((a, b) => a.name.localeCompare(b.name));
    return { ok: true, message: `${name}.${zone} ${action === "add" ? "added" : "saved"}`, record };
  }
  if (action === "remove") {
    const record = state.names.find((entry) => entry.id === Number(body.id));
    if (!record) return { ok: false, error: "That name doesn't exist any more." };
    state.names = state.names.filter((entry) => entry !== record);
    return { ok: true, message: `${record.name}.${zone} removed` };
  }
  if (action === "domain") {
    state.zone = { label: String(body.label || "").toLowerCase(), tld: String(body.tld || "").toLowerCase() };
    return { ok: true, message: `Names now end in .${demoZone()}`, zone: demoZone() };
  }
  if (action === "access") {
    state.tailnetOnly = body.tailnet_only === true;
    return { ok: true, message: state.tailnetOnly ? "Only Tailscale devices can open names" : "Names open from any network that reaches the proxy" };
  }
  if (action === "sync") return { ok: true, message: "DNS and proxy are up to date" };
  return { ok: false, error: `Unknown action: names/${action}` };
}

function startContainer(name: string): ActionResult {
  const container = state.containers.find((entry) => entry.name === name);
  if (!container) return { ok: false, error: `No such container: ${name}` };
  if (container.blocked) return { ok: false, error: `container restart is blocked: ${name}` };
  container.status = "running";
  container.user_stopped = false;
  container.auto_heal_tracked = true;
  pushEvent({ alert_id: `docker.${name}.start`, source: "docker", severity: "info", status: "event", title: "Container started", body: `Container: ${name}\nEvent: started` });
  if (name === "blog") {
    const blog = state.sites.find((entry) => entry.name === "Blog");
    if (blog) {
      blog.up = true;
      blog.status_code = 200;
      blog.error = null;
      blog.latency_ms = 92;
      blog.history = [...(blog.history ?? []).slice(1), { ts: Math.round(Date.now() / 1000), up: true, status_code: 200, latency_ms: 92 }];
    }
    state.activeAlerts = state.activeAlerts.filter((id) => id !== "site.blog.down");
    pushEvent({ alert_id: "site.blog.down", source: "site", severity: "info", status: "recovered", title: "Site down: Blog recovered", body: "Site: Blog\nURL: https://blog.example.com\nStatus: 200" });
  }
  return { ok: true, message: `Container restarted: ${name}` };
}

export function demoAction(path: string, body: Record<string, unknown>): ActionResult {
  if (path.startsWith("actions/names/")) return demoNameAction(path.slice("actions/names/".length), body);
  switch (path) {
    case "actions/docker/restart":
      return startContainer(String(body.container || ""));
    case "actions/sites/add": {
      const name = String(body.name || "").trim();
      const url = String(body.url || "").trim();
      if (!name || !url) return { ok: false, error: "site name is required" };
      state.sites = state.sites.filter((entry) => entry.name.toLowerCase() !== name.toLowerCase());
      state.sites.push(site(name, url, 60 + random() * 120, 15));
      return { ok: true, message: `Site monitor saved: ${name}` };
    }
    case "actions/sites/remove": {
      const name = String(body.name || "");
      const before = state.sites.length;
      state.sites = state.sites.filter((entry) => entry.name !== name);
      state.activeAlerts = state.activeAlerts.filter((id) => id !== `site.${safeName(name)}.down`);
      return before === state.sites.length ? { ok: false, error: `runtime site not found: ${name}` } : { ok: true, message: `Site monitor removed: ${name}` };
    }
    case "actions/alerts/silence": {
      const minutes = body.minutes ? Number(body.minutes) : null;
      state.silenced = true;
      state.silencedUntil = minutes ? Date.now() / 1000 + minutes * 60 : null;
      return { ok: true, message: minutes ? `Alerts silenced for ${minutes} minutes` : "Alerts silenced until resumed", silenced_until: state.silencedUntil };
    }
    case "actions/alerts/resume":
      state.silenced = false;
      state.silencedUntil = null;
      return { ok: true, message: "Alerts resumed" };
    case "actions/events/clear":
      state.events = [];
      return { ok: true, message: "Recent events cleared" };
    case "actions/power/ac-recovery": {
      const mode = String(body.mode || "") as AcRecoveryMode;
      if (!["on", "off", "last"].includes(mode)) return { ok: false, error: "mode must be one of: on, off, last" };
      state.acRecovery = mode;
      pushEvent({ alert_id: "power.ac_recovery", source: "power", severity: "info", status: "event", title: `Power on with AC turned ${mode}`, body: `BIOS AC power recovery is now ${mode}.` });
      return { ok: true, message: `Power on with AC set to ${mode}` };
    }
    case "actions/clear-ram-cache":
      return { ok: true, message: "Linux page cache, dentries, and inodes were dropped" };
    default:
      return { ok: false, error: `Unknown action: ${path}` };
  }
}

/** In the demo, pretend the visitor was last here before last night's power cut. */
export const DEMO_LAST_VISIT = START - 12 * HOUR;
