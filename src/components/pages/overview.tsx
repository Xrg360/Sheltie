"use client";

import { Activity, Boxes, CheckCircle2, Circle, Clock, Cpu, Globe, HardDrive, MemoryStick, Network, Pin, Thermometer } from "lucide-react";
import Link from "next/link";

import { EventRow, ProblemItem, TimeAgo } from "./shared";
import { Meter, Sparkline, Stat, UptimeBars, percent } from "@/components/ui/data";
import { Card, EmptyState, PageHeader, Skeleton, SkeletonRows } from "@/components/ui/layout";
import { StatusPill, toneFromBool, upDownLabel } from "@/components/ui/status";
import { clockTime, uptime } from "@/lib/format";
import { healthyChecks, lastIncidentAge, meterTone, overallTone, problems, sinceLastVisit } from "@/lib/insights";
import { useMeerkat } from "@/lib/store";
import { strings } from "@/lib/strings";
import type { EventItem } from "@/lib/types";

const t = strings.overview;

export function OverviewPage() {
  const { snapshot, connection, lastVisit, prefs } = useMeerkat();
  const list = problems(snapshot);
  const tone = snapshot ? overallTone(list) : "unknown";
  const events = snapshot?.events ?? snapshot?.status?.recent_events ?? null;
  const silenced = snapshot?.status?.alerts_silenced;
  const until = snapshot?.status?.alerts_silenced_until;

  const headline = !snapshot
    ? connection === "offline"
      ? strings.connection.offline
      : strings.connection.connecting
    : list.length
      ? strings.status.problems(list.length)
      : strings.status.allGood;

  const lastIncident = lastIncidentAge(events);
  const meta = snapshot ? (
    <>
      {strings.status.checks(healthyChecks(snapshot))} · {lastIncident ? strings.status.lastIncident(lastIncident) : strings.status.noIncidents}
      {silenced ? ` · ${until ? strings.status.silencedUntil(clockTime(until)) : strings.status.silenced}` : ""}
    </>
  ) : null;

  return (
    <>
      <PageHeader eyebrow={t.eyebrow} headline={headline} tone={snapshot ? tone : undefined} meta={meta} />
      {list.length ? null : <SetupChecklist />}
      <div className="grid-main">
        <div className="stack">
          <Card title={t.attention} id="attention" flush tone={list.some((problem) => problem.tone === "bad") ? "bad" : list.length ? "warn" : undefined}>
            {!snapshot ? (
              <div className="card__body">
                <SkeletonRows rows={2} />
              </div>
            ) : list.length ? (
              <div>
                {list.map((problem) => (
                  <ProblemItem key={problem.id} problem={problem} />
                ))}
              </div>
            ) : (
              <EmptyState icon={<CheckCircle2 size={22} />} title={t.attentionEmpty} />
            )}
          </Card>
          <SinceLastVisit events={events} lastVisit={lastVisit} />
        </div>
        <div className="stack">
          <Card title={t.vitals} id="vitals">
            {snapshot ? (
              <>
                <div className="grid-tiles">
                  <Stat label={strings.network.internet} icon={<Globe size={14} aria-hidden="true" />} value={<StatusPill tone={toneFromBool(snapshot.status?.internet_up)}>{upDownLabel(snapshot.status?.internet_up)}</StatusPill>} sub={snapshot.network?.default_route_label ?? snapshot.status?.default_route_label} href="/network" />
                  <Stat
                    label={strings.nav.monitors}
                    icon={<Activity size={14} aria-hidden="true" />}
                    value={`${snapshot.sites?.up ?? 0}/${snapshot.sites?.total ?? 0}`}
                    sub={snapshot.sites?.down ? `${snapshot.sites.down} ${strings.status.down.toLowerCase()}` : strings.status.up}
                    href="/monitors"
                  />
                  <Stat
                    label={strings.nav.containers}
                    icon={<Boxes size={14} aria-hidden="true" />}
                    value={snapshot.docker?.available ? `${snapshot.docker.containers.filter((c) => c.status === "running").length}/${snapshot.docker.containers.length}` : "—"}
                    sub={snapshot.docker?.available ? strings.status.running : strings.containers.unavailable}
                    href="/containers"
                  />
                  <Stat label={strings.nav.network} icon={<Network size={14} aria-hidden="true" />} value={`${Object.values(snapshot.network?.interfaces ?? {}).filter((i) => i.up).length}/${Object.keys(snapshot.network?.interfaces ?? {}).length}`} sub="interfaces up" href="/network" />
                </div>
                <HostVitals />
              </>
            ) : (
              <SkeletonRows rows={4} />
            )}
          </Card>
          <PinnedMonitors pinned={prefs.pinned} />
        </div>
      </div>
      {list.length ? <SetupChecklist /> : null}
    </>
  );
}

function HostVitals() {
  const { snapshot, metrics } = useMeerkat();
  const health = snapshot?.health;
  if (!health) return null;
  const rows = [
    { label: strings.host.cpu, icon: <Cpu size={14} aria-hidden="true" />, value: health.cpu_percent },
    { label: strings.host.ram, icon: <MemoryStick size={14} aria-hidden="true" />, value: health.ram_percent },
    { label: `${strings.host.disk} ${health.disk_path ?? "/"}`, icon: <HardDrive size={14} aria-hidden="true" />, value: health.disk_percent },
  ];
  return (
    <div className="stack">
      {rows.map((row) => (
        <Meter key={row.label} label={row.label} icon={row.icon} value={row.value} />
      ))}
      {health.cpu_temperature != null ? <Meter label={strings.host.temp} icon={<Thermometer size={14} aria-hidden="true" />} value={health.cpu_temperature} suffix="°C" warn={70} bad={80} /> : null}
      <Sparkline values={metrics.map((m) => m.cpu)} tone={meterTone(health.cpu_percent)} label={`CPU trend, now ${Math.round(health.cpu_percent)}%`} />
      <Link className="btn btn--ghost btn--sm" href="/host">
        {strings.problems.viewHost}
      </Link>
    </div>
  );
}

function SinceLastVisit({ events, lastVisit }: { events: EventItem[] | null; lastVisit: number | null }) {
  const summary = sinceLastVisit(events, lastVisit);
  const title = lastVisit ? t.sinceVisit : t.recentActivity;
  return (
    <Card
      title={title}
      icon={<Clock size={16} aria-hidden="true" />}
      id="since-visit"
      action={
        <Link className="btn btn--ghost btn--sm" href="/incidents">
          {t.viewAll}
        </Link>
      }
    >
      {events == null ? (
        <SkeletonRows rows={3} />
      ) : summary.events.length ? (
        <>
          {lastVisit && summary.away ? <p className="muted">{t.sinceVisitSummary(summary.events.length, summary.away)}</p> : null}
          <div className="stack stack--sm">
            {summary.events.slice(0, 6).map((event) => (
              <EventRow key={`${event.ts}-${event.alert_id}-${event.status}`} event={event} compact />
            ))}
          </div>
        </>
      ) : (
        <p className="muted">
          {lastVisit ? (
            <>
              {t.sinceVisitEmpty("")}
              <TimeAgo value={lastVisit} />
            </>
          ) : (
            strings.incidents.headline(0)
          )}
        </p>
      )}
    </Card>
  );
}

function PinnedMonitors({ pinned }: { pinned: string[] }) {
  const { snapshot } = useMeerkat();
  const sites = snapshot?.sites?.sites;
  const chosen = sites ? (pinned.length ? sites.filter((site) => pinned.includes(site.name)) : [...sites].sort((a, b) => Number(a.up) - Number(b.up)).slice(0, 4)) : null;
  return (
    <Card
      title={t.pinned}
      icon={<Pin size={16} aria-hidden="true" />}
      id="pinned"
      flush
      action={
        <Link className="btn btn--ghost btn--sm" href="/settings#pins">
          Edit
        </Link>
      }
    >
      {!chosen ? (
        <div className="card__body">
          <Skeleton height={44} />
        </div>
      ) : chosen.length ? (
        <ul className="list">
          {chosen.map((site) => (
            <li key={site.name}>
              <Link className="row row--button row--link" href={`/monitors?site=${encodeURIComponent(site.name)}`}>
                <div className="row__main">
                  <span className="row__title">{site.name}</span>
                  <span className="row__sub">{percent(uptime(site))} uptime</span>
                </div>
                <div className="row__bars">
                  <UptimeBars site={site} count={24} />
                </div>
                <StatusPill tone={site.up ? "ok" : "bad"}>{site.up ? strings.status.up : strings.status.down}</StatusPill>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState icon={<Activity size={22} />} title={strings.monitors.empty} action={<Link className="btn btn--primary btn--sm" href="/monitors?add=1">{strings.monitors.add}</Link>}>
          {t.pinnedHint}
        </EmptyState>
      )}
    </Card>
  );
}

function SetupChecklist() {
  const { snapshot, prefs } = useMeerkat();
  if (!snapshot?.status) return null;
  const notificationsOn = typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted" && prefs.desktop;
  const steps = [
    { done: (snapshot.sites?.total ?? 0) > 0, label: t.setupSteps.monitor, href: "/monitors?add=1" },
    { done: Boolean(snapshot.status.telegram_enabled), label: t.setupSteps.telegram, href: "https://meerkat.simplewebsite.in/docs/readme/#telegram-botfather-commands" },
    { done: Boolean(prefs.token), label: t.setupSteps.token, href: "/settings#token" },
    { done: notificationsOn, label: t.setupSteps.notify, href: "/settings#notifications" },
  ];
  const done = steps.filter((step) => step.done).length;
  // Only the first two steps matter for a working setup; hide once those are complete.
  if (steps[0].done && steps[1].done) return null;
  return (
    <Card title={t.setup} id="setup" action={<span className="subtle">{t.setupProgress(done, steps.length)}</span>}>
      <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={steps.length} aria-valuenow={done} aria-label={t.setupProgress(done, steps.length)}>
        <span style={{ width: `${(done / steps.length) * 100}%` }} />
      </div>
      <ul className="checklist">
        {steps.map((step) => (
          <li key={step.label} className={step.done ? "is-done" : ""}>
            {step.done ? <CheckCircle2 className="icon-ok" size={18} aria-label="Done" /> : <Circle className="icon-unknown" size={18} aria-label="To do" />}
            <span className="checklist__text">{step.label}</span>
            {step.done ? null : step.href.startsWith("http") ? (
              <a className="btn btn--sm" href={step.href} target="_blank" rel="noreferrer">
                How
              </a>
            ) : (
              <Link className="btn btn--sm" href={step.href}>
                Set up
              </Link>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
