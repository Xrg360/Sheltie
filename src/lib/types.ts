// Payloads served by the Python API (monitors/status.py). Keep in sync with the backend.

export type Severity = "info" | "warning" | "critical" | "emergency" | string;

export type EventItem = {
  ts: string;
  alert_id: string;
  source: string;
  severity: Severity;
  status: "active" | "recovered" | "changed" | "event" | string;
  title: string;
  body: string;
};

export type StatusPayload = {
  version?: string;
  started_at?: string;
  telegram_enabled?: boolean;
  alerts_silenced: boolean;
  alerts_silenced_until?: number | null;
  internet_up: boolean | null;
  ethernet_up: boolean | null;
  wifi_up: boolean | null;
  default_route?: string | null;
  default_route_label?: string;
  auto_heal?: {
    enabled: boolean;
    interval: number | string;
    active_containers: string[];
    active_network_interfaces: string[];
  };
  active_alerts: string[];
  recent_events: EventItem[];
};

export type HealthPayload = {
  cpu_percent: number;
  ram_percent: number;
  disk_percent: number;
  disk_path?: string;
  cpu_temperature: number | null;
  load_average?: [number, number, number] | null;
};

export type InterfaceInfo = {
  name: string;
  operstate: string;
  carrier: boolean;
  has_ip: boolean;
  up: boolean;
};

export type NetworkPayload = {
  interfaces: Record<string, InterfaceInfo>;
  default_route: string | null;
  default_route_label: string;
  internet_up: boolean | null;
};

export type Container = {
  name: string;
  status: string;
  image: string;
  blocked?: boolean;
  user_stopped?: boolean;
  auto_heal_tracked?: boolean;
};

export type DockerPayload = {
  available: boolean;
  error?: string;
  containers: Container[];
};

export type SiteSample = {
  ts: number;
  up: boolean;
  status_code: number | null;
  latency_ms: number | null;
};

export type Site = {
  name: string;
  url: string;
  up: boolean;
  status_code: number | null;
  latency_ms: number | null;
  error: string | null;
  expected_status?: number[];
  history?: SiteSample[];
};

export type SitesPayload = {
  total: number;
  up: number;
  down: number;
  sites: Site[];
};

export type AcRecoveryMode = "on" | "off" | "last";

/** BIOS "AC power recovery": whether the machine powers on by itself when mains power returns. */
export type AcRecovery = {
  supported: boolean;
  mode: AcRecoveryMode | null;
  modes: AcRecoveryMode[];
  method?: string | null;
  reason?: string | null;
  checked_at?: string;
};

export type PowerPayload = {
  vendor?: string | null;
  model?: string | null;
  ac_online: boolean | null;
  battery_percent: number | null;
  battery_status: string | null;
  ac_recovery: AcRecovery;
};

/** A friendly name on the tailnet, e.g. sheltie.home.internals (monitors/names/service.py). */
export type NameRecord = {
  id: number;
  name: string;
  fqdn: string;
  /** "proxy": through Nginx Proxy Manager to an app's port. "device": DNS only, straight to a Tailscale device. */
  kind: "proxy" | "device";
  url: string;
  points_to: string;
  target_host: string;
  target_port: number | null;
  scheme: "http" | "https";
  websockets: boolean;
  source: string;
  label: string;
  synced: boolean;
  sync_error: string | null;
  created_at: number;
  updated_at: number;
  reachable: { ok: boolean | null; why: string | null };
};

export type NamesSync = { at: number; ok: boolean; error: string | null };

export type NamesPayload =
  | { enabled: false }
  | {
      enabled: true;
      zone: string;
      domain: { label: string; tld: string };
      server: { name: string; ip: string; dns_name: string; error: string | null };
      records: NameRecord[];
      tailnet_only: boolean;
      npm_configured: boolean;
      last_sync: NamesSync | null;
    };

/** Something a name can point at, from GET /api/names/targets. */
export type NameTarget = {
  id: string;
  source: string;
  name: string;
  label: string;
  host: string;
  port: number | null;
  detail: string;
  disabled: boolean;
  state?: string;
};

export type NameDevice = { name: string; dns_name: string; ip: string; os: string; online: boolean; is_self: boolean };

export type NameTargets = {
  server: { name: string; ip: string };
  apps: NameTarget[];
  ports: NameTarget[];
  devices: NameDevice[];
  errors: Record<string, string>;
};

export type NameCheck = {
  id: "tailscale" | "dns" | "split_dns" | "npm" | "docker" | string;
  title: string;
  ok: boolean;
  detail: string;
  fix: { steps: string[]; link: string | null; copy: Record<string, string> | null } | null;
};

export type Snapshot = {
  status: StatusPayload | null;
  health: HealthPayload | null;
  network: NetworkPayload | null;
  docker: DockerPayload | null;
  sites: SitesPayload | null;
  /** Missing in snapshots cached by older versions. */
  power?: PowerPayload | null;
  /** Missing in snapshots cached by older versions. */
  names?: NamesPayload | null;
  events: EventItem[] | null;
  fetchedAt: number;
};

export type ActionResult = {
  ok: boolean;
  message?: string;
  error?: string;
  [key: string]: unknown;
};

export type Tone = "ok" | "warn" | "bad" | "unknown";
