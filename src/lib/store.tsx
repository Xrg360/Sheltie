"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { ApiError, IS_DEMO, fetchSnapshot, runAction } from "./api";
import { DEMO_LAST_VISIT } from "./demo-data";
import { DEFAULT_PREFS, applyTheme, loadPrefs, read, savePrefs, storageKeys, write } from "./prefs";
import type { Prefs } from "./prefs";
import { strings } from "./strings";
import type { ActionResult, Snapshot, Tone } from "./types";

export type Connection = "connecting" | "live" | "stale" | "offline";

export type MetricPoint = { t: number; cpu: number; ram: number; disk: number; temp: number | null };

export type Toast = {
  id: number;
  tone: Tone | "info";
  title: string;
  body?: string;
  action?: { label: string; run: () => void };
};

export type ConfirmOptions = {
  title: string;
  body?: string;
  confirmLabel?: string;
  danger?: boolean;
};

type PendingConfirm = ConfirmOptions & { resolve: (value: boolean) => void };

type ActOptions = { quiet?: boolean; success?: string };

type StoreValue = {
  snapshot: Snapshot | null;
  connection: Connection;
  lastSuccess: number | null;
  now: number;
  refresh: () => Promise<void>;
  prefs: Prefs;
  setPrefs: (patch: Partial<Prefs>) => void;
  metrics: MetricPoint[];
  lastVisit: number | null;
  act: (path: string, body?: Record<string, unknown>, options?: ActOptions) => Promise<ActionResult | null>;
  toasts: Toast[];
  toast: (toast: Omit<Toast, "id">) => void;
  dismissToast: (id: number) => void;
  confirm: (options: ConfirmOptions) => Promise<boolean>;
  pendingConfirm: PendingConfirm | null;
  settleConfirm: (value: boolean) => void;
  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;
  shortcutsOpen: boolean;
  setShortcutsOpen: (open: boolean) => void;
  tokenRequest: { retry: (token: string) => void } | null;
  settleToken: (token: string | null) => void;
};

const StoreContext = createContext<StoreValue | null>(null);

const MAX_METRICS = 120;
const MAX_BACKOFF = 60_000;

function seedDemoMetrics(): MetricPoint[] {
  const now = Date.now();
  return Array.from({ length: 48 }, (_, index) => {
    const t = now - (48 - index) * 10_000;
    return {
      t,
      cpu: 22 + Math.sin(index / 5) * 8 + Math.sin(index / 1.7) * 3,
      ram: 60 + Math.sin(index / 12) * 2,
      disk: 78.4,
      temp: 51 + Math.sin(index / 8) * 2.5,
    };
  });
}

export function MeerkatProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [lastSuccess, setLastSuccess] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [prefs, setPrefsState] = useState<Prefs>(DEFAULT_PREFS);
  const [prefsLoaded, setPrefsLoaded] = useState(false);
  const [metrics, setMetrics] = useState<MetricPoint[]>([]);
  const [lastVisit, setLastVisit] = useState<number | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [tokenRequest, setTokenRequest] = useState<{ retry: (token: string) => void } | null>(null);

  const failures = useRef(0);
  const seen = useRef<Set<string> | null>(null);
  const prefsRef = useRef(prefs);
  prefsRef.current = prefs;
  const timer = useRef<number | null>(null);

  const dismissToast = useCallback((id: number) => setToasts((list) => list.filter((item) => item.id !== id)), []);

  const toast = useCallback(
    (item: Omit<Toast, "id">) => {
      const id = Date.now() + Math.random();
      setToasts((list) => [...list.slice(-3), { ...item, id }]);
      window.setTimeout(() => dismissToast(id), item.tone === "bad" ? 10_000 : 6_000);
    },
    [dismissToast],
  );

  const notifyNewProblems = useCallback(
    (next: Snapshot) => {
      const events = next.events ?? next.status?.recent_events ?? [];
      const keys = events.map((event) => `${event.ts}|${event.alert_id}|${event.status}`);
      if (!seen.current) {
        // First load: everything already recorded counts as seen. "Since your last visit" covers it.
        seen.current = new Set([...read<string[]>(storageKeys.seen, []), ...keys]);
        write(storageKeys.seen, [...seen.current].slice(-300));
        return;
      }
      events.forEach((event, index) => {
        const key = keys[index];
        if (seen.current?.has(key)) return;
        seen.current?.add(key);
        const serious = ["warning", "critical", "emergency"].includes(event.severity) && event.status !== "recovered";
        if (!serious) return;
        if (prefsRef.current.popups) toast({ tone: event.severity === "warning" ? "warn" : "bad", title: event.title, body: event.body.split("\n")[0] });
        if (prefsRef.current.desktop && "Notification" in window && Notification.permission === "granted") {
          new Notification(event.title, { body: event.body });
        }
      });
      write(storageKeys.seen, [...(seen.current ?? [])].slice(-300));
    },
    [toast],
  );

  const refresh = useCallback(async () => {
    try {
      const next = await fetchSnapshot();
      failures.current = 0;
      setSnapshot(next);
      setLastSuccess(next.fetchedAt);
      setConnection("live");
      write(storageKeys.snapshot, next);
      if (next.health) {
        const health = next.health;
        setMetrics((list) => [
          ...list.slice(-(MAX_METRICS - 1)),
          { t: next.fetchedAt, cpu: health.cpu_percent, ram: health.ram_percent, disk: health.disk_percent, temp: health.cpu_temperature },
        ]);
      }
      notifyNewProblems(next);
    } catch {
      failures.current += 1;
      setConnection((current) => (current === "connecting" && failures.current < 2 ? "connecting" : "offline"));
    }
  }, [notifyNewProblems]);

  // Load preferences, cached snapshot and visit history once.
  useEffect(() => {
    const loaded = loadPrefs();
    setPrefsState(loaded);
    setPrefsLoaded(true);
    const cached = read<Snapshot | null>(storageKeys.snapshot, null);
    if (cached && !IS_DEMO) {
      setSnapshot(cached);
      setLastSuccess(cached.fetchedAt);
    }
    if (IS_DEMO) setMetrics(seedDemoMetrics());
    const previous = IS_DEMO ? DEMO_LAST_VISIT : read<number | null>(storageKeys.visit, null);
    setLastVisit(previous);
    const markVisit = () => write(storageKeys.visit, Date.now());
    markVisit();
    const visitTimer = window.setInterval(markVisit, 60_000);
    window.addEventListener("pagehide", markVisit);
    return () => {
      window.clearInterval(visitTimer);
      window.removeEventListener("pagehide", markVisit);
    };
  }, []);

  useEffect(() => {
    if (!prefsLoaded) return;
    applyTheme(prefs.theme);
    savePrefs(prefs);
  }, [prefs, prefsLoaded]);

  // Polling: pauses while the tab is hidden, backs off while the API is down.
  useEffect(() => {
    if (!prefsLoaded) return;
    let cancelled = false;
    const schedule = () => {
      if (cancelled) return;
      const base = prefsRef.current.refreshMs;
      const delay = failures.current ? Math.min(MAX_BACKOFF, base * 2 ** (failures.current - 1)) : base;
      timer.current = window.setTimeout(tick, delay);
    };
    const tick = async () => {
      if (document.hidden) {
        schedule();
        return;
      }
      await refresh();
      schedule();
    };
    tick();
    const onVisible = () => {
      if (!document.hidden) {
        if (timer.current) window.clearTimeout(timer.current);
        tick();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      if (timer.current) window.clearTimeout(timer.current);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [prefsLoaded, prefs.refreshMs, refresh]);

  // A 1s clock keeps every "updated Xs ago" honest, and flags stale data.
  useEffect(() => {
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(clock);
  }, []);

  useEffect(() => {
    if (connection === "live" && lastSuccess && now - lastSuccess > prefs.refreshMs * 3 + 5000) setConnection("stale");
  }, [now, lastSuccess, connection, prefs.refreshMs]);

  const setPrefs = useCallback((patch: Partial<Prefs>) => setPrefsState((current) => ({ ...current, ...patch })), []);

  const confirm = useCallback((options: ConfirmOptions) => new Promise<boolean>((resolve) => setPendingConfirm({ ...options, resolve })), []);

  const settleConfirm = useCallback(
    (value: boolean) => {
      pendingConfirm?.resolve(value);
      setPendingConfirm(null);
    },
    [pendingConfirm],
  );

  const settleToken = useCallback(
    (token: string | null) => {
      if (token) {
        setPrefs({ token });
        tokenRequest?.retry(token);
      }
      setTokenRequest(null);
    },
    [setPrefs, tokenRequest],
  );

  const act = useCallback(
    async (path: string, body: Record<string, unknown> = {}, options: ActOptions = {}): Promise<ActionResult | null> => {
      const attempt = async (token: string): Promise<ActionResult | null> => {
        try {
          const result = await runAction(path, body, token);
          if (result.ok) {
            if (!options.quiet) toast({ tone: "ok", title: options.success || result.message || strings.actions.done });
          } else {
            toast({ tone: "bad", title: strings.actions.failed, body: result.error });
          }
          await refresh();
          return result;
        } catch (error) {
          if (error instanceof ApiError && (error.status === 403 || error.status === 401)) {
            return new Promise((resolve) => setTokenRequest({ retry: (next) => resolve(attempt(next)) }));
          }
          toast({ tone: "bad", title: strings.actions.failed, body: error instanceof Error ? error.message : String(error) });
          return null;
        }
      };
      return attempt(prefsRef.current.token);
    },
    [refresh, toast],
  );

  const value = useMemo<StoreValue>(
    () => ({
      snapshot,
      connection,
      lastSuccess,
      now,
      refresh,
      prefs,
      setPrefs,
      metrics,
      lastVisit,
      act,
      toasts,
      toast,
      dismissToast,
      confirm,
      pendingConfirm,
      settleConfirm,
      paletteOpen,
      setPaletteOpen,
      shortcutsOpen,
      setShortcutsOpen,
      tokenRequest,
      settleToken,
    }),
    [snapshot, connection, lastSuccess, now, refresh, prefs, setPrefs, metrics, lastVisit, act, toasts, toast, dismissToast, confirm, pendingConfirm, settleConfirm, paletteOpen, shortcutsOpen, tokenRequest, settleToken],
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useMeerkat(): StoreValue {
  const value = useContext(StoreContext);
  if (!value) throw new Error("useMeerkat must be used inside <MeerkatProvider>");
  return value;
}
