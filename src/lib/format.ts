import type { Site, SiteSample } from "./types";

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

export function toMillis(value: string | number | null | undefined): number | null {
  if (value == null || value === "") return null;
  if (typeof value === "number") return value < 1e12 ? value * 1000 : value;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

export function relativeTime(value: string | number | null | undefined, now = Date.now()): string {
  const ms = toMillis(value);
  if (ms == null) return "never";
  const diff = now - ms;
  const future = diff < 0;
  const abs = Math.abs(diff);
  let text: string;
  if (abs < 45_000) return future ? "in a moment" : "just now";
  if (abs < HOUR) text = `${Math.round(abs / MINUTE)}m`;
  else if (abs < DAY) text = `${Math.round(abs / HOUR)}h`;
  else text = `${Math.round(abs / DAY)}d`;
  return future ? `in ${text}` : `${text} ago`;
}

export function secondsAgo(ms: number | null, now = Date.now()): string {
  if (ms == null) return "never";
  const seconds = Math.max(0, Math.round((now - ms) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  return relativeTime(ms, now);
}

export function absoluteTime(value: string | number | null | undefined): string {
  const ms = toMillis(value);
  if (ms == null) return "";
  return new Date(ms).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function clockTime(value: string | number | null | undefined): string {
  const ms = toMillis(value);
  if (ms == null) return "";
  return new Date(ms).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function dayLabel(ms: number, now = Date.now()): string {
  const day = new Date(ms).toDateString();
  if (day === new Date(now).toDateString()) return "Today";
  if (day === new Date(now - DAY).toDateString()) return "Yesterday";
  return new Date(ms).toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
}

export function duration(ms: number): string {
  if (ms < MINUTE) return `${Math.max(1, Math.round(ms / 1000))}s`;
  if (ms < HOUR) return `${Math.round(ms / MINUTE)}m`;
  if (ms < DAY) {
    const hours = Math.floor(ms / HOUR);
    const minutes = Math.round((ms % HOUR) / MINUTE);
    return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
  }
  const days = Math.floor(ms / DAY);
  const hours = Math.round((ms % DAY) / HOUR);
  return hours ? `${days}d ${hours}h` : `${days}d`;
}

export function pct(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

export function ms(value: number | null | undefined): string {
  return value == null ? "—" : `${Math.round(value)} ms`;
}

export function samples(site: Site | null | undefined): SiteSample[] {
  return Array.isArray(site?.history) ? site.history : [];
}

export function uptime(site: Site | null | undefined): number | null {
  const history = samples(site);
  if (!history.length) return site ? (site.up ? 100 : 0) : null;
  return (history.filter((sample) => sample.up).length / history.length) * 100;
}

function latencies(site: Site | null | undefined): number[] {
  return samples(site)
    .map((sample) => sample.latency_ms)
    .filter((value): value is number => value != null);
}

export function averageLatency(site: Site | null | undefined): number | null {
  const values = latencies(site);
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export function percentileLatency(site: Site | null | undefined, percentile = 95): number | null {
  const values = latencies(site).sort((a, b) => a - b);
  if (!values.length) return null;
  const index = Math.min(values.length - 1, Math.ceil((percentile / 100) * values.length) - 1);
  return values[index];
}

/** Matches the Python side's safe_name() in monitors/sites.py. */
export function safeName(name: string): string {
  return (
    name
      .toLowerCase()
      .split("")
      .map((ch) => (/[a-z0-9]/.test(ch) ? ch : "_"))
      .join("")
      .replace(/^_+|_+$/g, "") || "site"
  );
}

export function hostFromUrl(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/** "https://blog.example.com/path" -> "Blog" */
export function nameFromUrl(url: string): string {
  try {
    const host = new URL(url).hostname.replace(/^www\./, "");
    const first = host.split(".")[0] || host;
    return first.charAt(0).toUpperCase() + first.slice(1);
  } catch {
    return "";
  }
}

export function isValidHttpUrl(value: string): boolean {
  if (!value || /\s/.test(value)) return false;
  try {
    const url = new URL(value);
    const hostOk = /^[a-z0-9.-]+$/i.test(url.hostname) || /^\[[0-9a-f:.]+\]$/i.test(url.hostname);
    return (url.protocol === "http:" || url.protocol === "https:") && hostOk && !url.hostname.startsWith(".");
  } catch {
    return false;
  }
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}
