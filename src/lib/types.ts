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

export type Snapshot = {
  status: StatusPayload | null;
  health: HealthPayload | null;
  network: NetworkPayload | null;
  docker: DockerPayload | null;
  sites: SitesPayload | null;
  /** Missing in snapshots cached by older versions. */
  power?: PowerPayload | null;
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
