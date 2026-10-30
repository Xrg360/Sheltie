"use client";

import { useEffect, useSyncExternalStore } from "react";

// Installing Sheltie as an app: registers the service worker and keeps the browser's install
// prompt (beforeinstallprompt), which fires once, early, before Settings is likely to be open.

type InstallPromptEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: "accepted" | "dismissed" }> };

let deferred: InstallPromptEvent | null = null;
let installed = false;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((listener) => listener());

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export type InstallState = "installed" | "available" | "insecure" | "manual";

function snapshot(): InstallState {
  if (installed || window.matchMedia("(display-mode: standalone)").matches) return "installed";
  if (deferred) return "available";
  // Browsers only install apps served over https (or from localhost).
  return window.isSecureContext ? "manual" : "insecure";
}

/** Whether Sheltie can be installed from here, and a function that shows the browser's install prompt. */
export function useInstall(): { state: InstallState; install: () => Promise<void> } {
  const state = useSyncExternalStore(subscribe, snapshot, () => "manual" as InstallState);
  return {
    state,
    install: async () => {
      const event = deferred;
      if (!event) return;
      await event.prompt();
      const { outcome } = await event.userChoice;
      deferred = null;
      installed = outcome === "accepted";
      notify();
    },
  };
}

/** Mounted once in the root layout. Renders nothing. */
export function AppInstall() {
  useEffect(() => {
    const onPrompt = (event: Event) => {
      event.preventDefault(); // Show our own Install button in Settings instead of the mini-infobar.
      deferred = event as InstallPromptEvent;
      notify();
    };
    const onInstalled = () => {
      installed = true;
      deferred = null;
      notify();
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    // `next dev` rebuilds files constantly; a service worker there would only serve stale code.
    if (process.env.NODE_ENV === "production" && "serviceWorker" in navigator) {
      const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
      navigator.serviceWorker.register(`${base}/sw.js`, { scope: `${base}/` }).catch(() => undefined);
    }
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);
  return null;
}
