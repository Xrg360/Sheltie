"use client";

import { Bell, BellOff, BookOpen, ChevronDown, Ellipsis, RefreshCw, Search, Star } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { CommandPalette } from "./command-palette";
import { ConfirmDialog, ShortcutsDialog, Toasts, TokenDialog } from "./overlays";
import { Dialog } from "@/components/ui/dialog";
import { Logo } from "@/components/ui/logo";
import { Dot } from "@/components/ui/status";
import { IS_DEMO } from "@/lib/api";
import { clockTime, secondsAgo } from "@/lib/format";
import { problems } from "@/lib/insights";
import { DOCS_URL, NAV, REPO_URL, isActive } from "@/lib/nav";
import { useMeerkat } from "@/lib/store";
import { strings } from "@/lib/strings";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() || "/";
  const router = useRouter();
  const { snapshot, setPaletteOpen, setShortcutsOpen, paletteOpen } = useMeerkat();
  const [moreOpen, setMoreOpen] = useState(false);
  const pendingG = useRef<number | null>(null);

  // Global keyboard shortcuts. Ignored while typing in a field.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable);
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(!paletteOpen);
        return;
      }
      if (typing || event.metaKey || event.ctrlKey || event.altKey || document.querySelector("dialog[open]")) return;
      if (event.key === "/") {
        event.preventDefault();
        setPaletteOpen(true);
      } else if (event.key === "?") {
        setShortcutsOpen(true);
      } else if (event.key === "g") {
        pendingG.current = window.setTimeout(() => (pendingG.current = null), 1200);
      } else if (pendingG.current) {
        const item = NAV.find((entry) => entry.key === event.key);
        window.clearTimeout(pendingG.current);
        pendingG.current = null;
        if (item) router.push(item.href);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [paletteOpen, router, setPaletteOpen, setShortcutsOpen]);

  useEffect(() => setMoreOpen(false), [pathname]);

  const issueCount = problems(snapshot).length;
  const downSites = snapshot?.sites?.down ?? 0;
  const counts: Record<string, number> = { "/": issueCount, "/monitors": downSites };

  return (
    <>
      <a className="skip-link" href="#content">
        {strings.app.skip}
      </a>
      <div className="shell">
        <aside className="sidebar" aria-label="Main">
          <Link className="brand" href="/" aria-label={`${strings.app.name} home`}>
            <Logo size={36} />
            <span>
              <span className="brand__name">{strings.app.name}</span>
              <span className="brand__tag">{strings.app.tagline}</span>
            </span>
          </Link>
          <nav className="nav" aria-label="Pages">
            {NAV.map((item) => {
              const Icon = item.icon;
              const count = counts[item.href];
              return (
                <Link key={item.href} href={item.href} className="nav__item" aria-current={isActive(pathname, item.href) ? "page" : undefined}>
                  <Icon size={18} aria-hidden="true" />
                  {item.label}
                  {count ? (
                    <span className="pill tone-bad nav__count" aria-label={`${count} need attention`}>
                      {count}
                    </span>
                  ) : null}
                </Link>
              );
            })}
          </nav>
          <div className="sidebar__footer">
            <a href={DOCS_URL} target="_blank" rel="noreferrer">
              <BookOpen size={14} aria-hidden="true" />
              {strings.nav.docs}
            </a>
            <a href={REPO_URL} target="_blank" rel="noreferrer">
              <Star size={14} aria-hidden="true" />
              {strings.nav.star}
            </a>
            <span>
              {strings.app.name} {snapshot?.status?.version ?? ""}
              {IS_DEMO ? ` · ${strings.connection.demo}` : ""}
            </span>
          </div>
        </aside>

        <div className="main">
          <header className="topbar">
            <Link className="brand topbar__brand" href="/" aria-label={`${strings.app.name} home`}>
              <Logo size={30} />
              <span className="brand__name">{strings.app.name}</span>
            </Link>
            <button type="button" className="search-trigger" onClick={() => setPaletteOpen(true)} aria-label={strings.search.trigger}>
              <Search size={16} aria-hidden="true" />
              <span className="search-trigger__text">{strings.search.trigger}</span>
              <kbd>⌘K</kbd>
            </button>
            <span className="topbar__spacer" />
            <ConnectionIndicator />
            <SilenceMenu />
          </header>
          <ConnectionBanner />
          <main id="content" className="page" tabIndex={-1}>
            {children}
          </main>
        </div>
      </div>

      <nav className="bottom-tabs" aria-label="Pages">
        {NAV.filter((item) => item.mobile).map((item) => {
          const Icon = item.icon;
          return (
            <Link key={item.href} href={item.href} aria-current={isActive(pathname, item.href) ? "page" : undefined}>
              <Icon size={20} aria-hidden="true" />
              {item.label}
            </Link>
          );
        })}
        <button type="button" onClick={() => setMoreOpen(true)} aria-current={NAV.some((item) => !item.mobile && isActive(pathname, item.href)) ? "page" : undefined}>
          <Ellipsis size={20} aria-hidden="true" />
          {strings.nav.more}
        </button>
      </nav>

      <Dialog open={moreOpen} onClose={() => setMoreOpen(false)} title={strings.nav.more} variant="sheet" labelledBy="more-title">
        <nav className="nav" aria-label="More pages">
          {NAV.filter((item) => !item.mobile).map((item) => {
            const Icon = item.icon;
            return (
              <Link key={item.href} href={item.href} className="nav__item" aria-current={isActive(pathname, item.href) ? "page" : undefined}>
                <Icon size={18} aria-hidden="true" />
                {item.label}
              </Link>
            );
          })}
          <a className="nav__item" href={DOCS_URL} target="_blank" rel="noreferrer">
            <BookOpen size={18} aria-hidden="true" />
            {strings.nav.docs}
          </a>
          <a className="nav__item" href={REPO_URL} target="_blank" rel="noreferrer">
            <Star size={18} aria-hidden="true" />
            {strings.nav.star}
          </a>
        </nav>
      </Dialog>

      <CommandPalette />
      <ShortcutsDialog />
      <ConfirmDialog />
      <TokenDialog />
      <Toasts />
    </>
  );
}

function ConnectionIndicator() {
  const { connection, lastSuccess, now } = useMeerkat();
  const tone = connection === "live" ? "ok" : connection === "offline" ? "bad" : connection === "stale" ? "warn" : "unknown";
  const label = IS_DEMO
    ? strings.connection.demo
    : connection === "live"
      ? strings.connection.live
      : connection === "offline"
        ? strings.connection.offline
        : connection === "stale"
          ? strings.connection.stale
          : strings.connection.connecting;
  return (
    <span className="conn" role="status" title={lastSuccess ? strings.connection.updated(secondsAgo(lastSuccess, now)) : undefined}>
      <Dot tone={tone} live={connection === "live"} />
      <span className="conn__text">
        {label}
        {lastSuccess ? ` · ${secondsAgo(lastSuccess, now)}` : ""}
      </span>
      <span className="sr-only">{lastSuccess ? strings.connection.updated(secondsAgo(lastSuccess, now)) : ""}</span>
    </span>
  );
}

function ConnectionBanner() {
  const { connection, lastSuccess, now, refresh } = useMeerkat();
  if (connection !== "offline" && connection !== "stale") return null;
  const tone = connection === "offline" ? "bad" : "warn";
  const text = lastSuccess ? strings.connection.offlineBanner(secondsAgo(lastSuccess, now)) : strings.connection.neverBanner;
  return (
    <div className={`banner banner--${tone}`} role="alert">
      <span>{text}</span>
      <button type="button" className="btn btn--sm" onClick={() => void refresh()}>
        <RefreshCw size={14} aria-hidden="true" />
        {strings.connection.retry}
      </button>
    </div>
  );
}

function SilenceMenu() {
  const { snapshot, act } = useMeerkat();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const silenced = Boolean(snapshot?.status?.alerts_silenced);
  const until = snapshot?.status?.alerts_silenced_until;

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !ref.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const run = (path: string, body: Record<string, unknown>, success: string) => {
    setOpen(false);
    void act(path, body, { success });
  };

  return (
    <div className="menu" ref={ref}>
      <button
        type="button"
        className={`btn btn--sm ${silenced ? "tone-warn" : ""}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={silenced ? `${strings.silence.silencedButton}${until ? ` until ${clockTime(until)}` : ""}` : strings.silence.button}
        onClick={() => setOpen((value) => !value)}
        title={silenced ? (until ? strings.status.silencedUntil(clockTime(until)) : strings.status.silenced) : undefined}
      >
        {silenced ? <BellOff size={15} aria-hidden="true" /> : <Bell size={15} aria-hidden="true" />}
        <span className="conn__text">{silenced ? `${strings.silence.silencedButton}${until ? ` · ${clockTime(until)}` : ""}` : strings.silence.button}</span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open ? (
        <div className="menu__list" role="menu">
          {silenced ? (
            <button type="button" role="menuitem" className="menu__item" onClick={() => run("actions/alerts/resume", {}, strings.silence.resumed)}>
              <Bell size={15} aria-hidden="true" />
              {strings.silence.resume}
            </button>
          ) : null}
          <button type="button" role="menuitem" className="menu__item" onClick={() => run("actions/alerts/silence", { minutes: 60 }, strings.silence.done)}>
            <BellOff size={15} aria-hidden="true" />
            {strings.silence.oneHour}
          </button>
          <button type="button" role="menuitem" className="menu__item" onClick={() => run("actions/alerts/silence", { minutes: 240 }, strings.silence.done)}>
            <BellOff size={15} aria-hidden="true" />
            {strings.silence.fourHours}
          </button>
          <button type="button" role="menuitem" className="menu__item" onClick={() => run("actions/alerts/silence", {}, strings.silence.done)}>
            <BellOff size={15} aria-hidden="true" />
            {strings.silence.untilResumed}
          </button>
        </div>
      ) : null}
    </div>
  );
}
