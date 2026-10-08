"use client";

import { Bell, BookOpen, Info, KeyRound, Keyboard, Monitor, Moon, Palette, Pin, Star, Sun } from "lucide-react";
import { useEffect, useState } from "react";

import { TimeAgo } from "./shared";
import { Card, PageHeader, Segmented } from "@/components/ui/layout";
import { StatusPill } from "@/components/ui/status";
import { IS_DEMO } from "@/lib/api";
import { DOCS_URL, REPO_URL } from "@/lib/nav";
import type { ThemePref } from "@/lib/prefs";
import { useMeerkat } from "@/lib/store";
import { strings } from "@/lib/strings";

const t = strings.settings;

export function SettingsPage() {
  const { prefs, setPrefs, snapshot, toast, setShortcutsOpen } = useMeerkat();
  const [token, setToken] = useState(prefs.token);
  const [permission, setPermission] = useState<NotificationPermission | "unsupported">("default");

  useEffect(() => setToken(prefs.token), [prefs.token]);
  useEffect(() => setPermission("Notification" in window ? Notification.permission : "unsupported"), []);

  async function enableDesktop() {
    if (!("Notification" in window)) return;
    const result = await Notification.requestPermission();
    setPermission(result);
    setPrefs({ desktop: result === "granted" });
  }

  function saveToken(event: React.FormEvent) {
    event.preventDefault();
    setPrefs({ token: token.trim() });
    toast({ tone: "ok", title: token.trim() ? t.tokenSaved : t.tokenCleared });
  }

  function togglePin(name: string) {
    setPrefs({ pinned: prefs.pinned.includes(name) ? prefs.pinned.filter((item) => item !== name) : [...prefs.pinned, name] });
  }

  return (
    <>
      <PageHeader eyebrow={t.eyebrow} headline={t.headline} meta={t.meta} />
      <div className="grid-2">
        <Card title={t.appearance} icon={<Palette size={16} aria-hidden="true" />} id="appearance">
          <div className="field">
            <span className="label" id="theme-label">
              {t.theme}
            </span>
            <Segmented<ThemePref>
              label={t.theme}
              value={prefs.theme}
              onChange={(theme) => setPrefs({ theme })}
              options={[
                { value: "system", label: t.system },
                { value: "light", label: t.light },
                { value: "dark", label: t.dark },
              ]}
            />
          </div>
          <div className="field">
            <label className="label" htmlFor="refresh-select">
              {t.refresh}
            </label>
            <select id="refresh-select" className="select" value={prefs.refreshMs} onChange={(event) => setPrefs({ refreshMs: Number(event.target.value) })}>
              <option value={5000}>5 seconds</option>
              <option value={10000}>10 seconds</option>
              <option value={30000}>30 seconds</option>
              <option value={60000}>1 minute</option>
            </select>
          </div>
          <p className="subtle cluster">
            <Monitor size={13} aria-hidden="true" /> <Sun size={13} aria-hidden="true" /> <Moon size={13} aria-hidden="true" /> System follows your device setting.
          </p>
        </Card>

        <Card title={t.notifications} icon={<Bell size={16} aria-hidden="true" />} id="notifications">
          <label className="switch-row">
            <span>{t.popups}</span>
            <input className="switch" type="checkbox" role="switch" checked={prefs.popups} onChange={(event) => setPrefs({ popups: event.target.checked })} />
          </label>
          <div className="switch-row">
            <span className="stack stack--sm">
              <span>{t.desktop}</span>
              <span className="subtle">{t.desktopHint}</span>
            </span>
            {permission === "granted" ? (
              <input className="switch" type="checkbox" role="switch" aria-label={t.desktop} checked={prefs.desktop} onChange={(event) => setPrefs({ desktop: event.target.checked })} />
            ) : permission === "denied" ? (
              <StatusPill tone="warn">{t.blocked}</StatusPill>
            ) : permission === "unsupported" ? (
              <StatusPill tone="unknown">{strings.host.unavailable}</StatusPill>
            ) : (
              <button type="button" className="btn btn--sm" onClick={enableDesktop}>
                {t.enable}
              </button>
            )}
          </div>
          <div className="switch-row">
            <span>{t.telegram}</span>
            <StatusPill tone={snapshot?.status?.telegram_enabled ? "ok" : "unknown"}>{snapshot?.status?.telegram_enabled ? t.connected : t.notConnected}</StatusPill>
          </div>
        </Card>

        <Card title={t.token} icon={<KeyRound size={16} aria-hidden="true" />} id="token">
          <form className="stack" onSubmit={saveToken}>
            <div className="field">
              <label className="label" htmlFor="token-setting">
                {t.token}
              </label>
              <input id="token-setting" className="input mono" value={token} onChange={(event) => setToken(event.target.value)} autoComplete="off" spellCheck={false} aria-describedby="token-hint" />
              <span id="token-hint" className="hint">
                {t.tokenHint}
              </span>
            </div>
            <div>
              <button type="submit" className="btn btn--primary">
                {t.tokenSave}
              </button>
            </div>
          </form>
        </Card>

        <Card title={t.pins} icon={<Pin size={16} aria-hidden="true" />} id="pins">
          <p className="muted">{t.pinsHint}</p>
          {(snapshot?.sites?.sites ?? []).length ? (
            <div className="stack stack--sm">
              {(snapshot?.sites?.sites ?? []).map((site) => (
                <label key={site.name} className="switch-row">
                  <span>{site.name}</span>
                  <input className="switch" type="checkbox" role="switch" checked={prefs.pinned.includes(site.name)} onChange={() => togglePin(site.name)} />
                </label>
              ))}
            </div>
          ) : (
            <p className="subtle">{strings.monitors.empty}</p>
          )}
        </Card>

        <Card title={t.shortcuts} icon={<Keyboard size={16} aria-hidden="true" />} id="shortcuts">
          <p className="muted">
            Press <kbd>⌘</kbd> <kbd>K</kbd> anywhere to search and run commands, or <kbd>?</kbd> for the full list.
          </p>
          <div>
            <button type="button" className="btn" onClick={() => setShortcutsOpen(true)}>
              {strings.shortcuts.title}
            </button>
          </div>
        </Card>

        <Card title={t.about} icon={<Info size={16} aria-hidden="true" />} id="about">
          <dl className="kv">
            <dt>{t.version}</dt>
            <dd>
              {snapshot?.status?.version ?? "—"}
              {IS_DEMO ? ` (${strings.connection.demo})` : ""}
            </dd>
            <dt>{t.started}</dt>
            <dd>{snapshot?.status?.started_at ? <TimeAgo value={snapshot.status.started_at} /> : "—"}</dd>
          </dl>
          <div className="cluster">
            <a className="btn" href={DOCS_URL} target="_blank" rel="noreferrer">
              <BookOpen size={15} aria-hidden="true" />
              {strings.nav.docs}
            </a>
            <a className="btn" href={REPO_URL} target="_blank" rel="noreferrer">
              <Star size={15} aria-hidden="true" />
              {strings.nav.star}
            </a>
          </div>
        </Card>
      </div>
    </>
  );
}
