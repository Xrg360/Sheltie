import { demoAction, demoSnapshot } from "./demo-data";
import type { ActionResult, DockerPayload, EventItem, HealthPayload, NetworkPayload, SitesPayload, Snapshot, StatusPayload } from "./types";

export const IS_DEMO = process.env.NEXT_PUBLIC_LABWARDEN_DEMO === "1";

const BASE = "/api/labwarden";
const TIMEOUT_MS = 8_000;

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(`${BASE}/${path}`, { cache: "no-store", ...init, signal: controller.signal });
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    const body = (payload ?? {}) as { ok?: boolean; error?: string };
    if (!response.ok) throw new ApiError(body.error || `Request failed (${response.status})`, response.status);
    return payload as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(error instanceof Error ? error.message : "Network error", 0);
  } finally {
    window.clearTimeout(timer);
  }
}

/** Fetches everything the UI needs. Throws only if the API is completely unreachable. */
export async function fetchSnapshot(): Promise<Snapshot> {
  if (IS_DEMO) return demoSnapshot();

  const [status, health, network, docker, sites, events] = await Promise.allSettled([
    request<StatusPayload>("status"),
    request<HealthPayload>("health"),
    request<NetworkPayload>("network"),
    request<DockerPayload>("docker"),
    request<SitesPayload>("sites"),
    request<{ events: EventItem[] }>("events"),
  ]);

  const all = [status, health, network, docker, sites, events];
  if (all.every((result) => result.status === "rejected")) {
    const reason = (status as PromiseRejectedResult).reason;
    throw reason instanceof Error ? reason : new ApiError("Labwarden API unavailable", 0);
  }

  const value = <T,>(result: PromiseSettledResult<T>): T | null => (result.status === "fulfilled" ? result.value : null);
  return {
    status: value(status),
    health: value(health),
    network: value(network),
    docker: value(docker),
    sites: value(sites),
    events: value(events)?.events ?? null,
    fetchedAt: Date.now(),
  };
}

/** Runs an action endpoint. Throws ApiError(403) when the action token is missing or wrong. */
export async function runAction(path: string, body: Record<string, unknown>, token: string): Promise<ActionResult> {
  if (IS_DEMO) {
    await new Promise((resolve) => window.setTimeout(resolve, 350));
    return demoAction(path, body);
  }
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["X-Labwarden-Action-Token"] = token;
  try {
    return await request<ActionResult>(path, { method: "POST", headers, body: JSON.stringify(body) });
  } catch (error) {
    if (error instanceof ApiError && error.status === 400) return { ok: false, error: error.message };
    throw error;
  }
}
