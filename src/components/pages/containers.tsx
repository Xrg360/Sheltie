"use client";

import { Boxes, Lock, Play, RotateCcw } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Card, EmptyState, PageHeader, SearchInput, Segmented, SkeletonRows } from "@/components/ui/layout";
import { StatusPill } from "@/components/ui/status";
import { useMeerkat } from "@/lib/store";
import { strings } from "@/lib/strings";
import type { Container, Tone } from "@/lib/types";

const t = strings.containers;
type Filter = "all" | "running" | "stopped";

function containerTone(container: Container): Tone {
  if (container.status === "running") return "ok";
  if (container.user_stopped) return "unknown";
  if (container.status === "restarting" || container.status === "paused") return "warn";
  return container.auto_heal_tracked ? "bad" : "unknown";
}

function statusLabel(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export function ContainersPage() {
  const { snapshot, act, confirm } = useMeerkat();
  const params = useSearchParams();
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [filter, setFilter] = useState<Filter>("all");
  const [busy, setBusy] = useState<string | null>(null);
  const docker = snapshot?.docker ?? null;

  useEffect(() => {
    const q = params.get("q");
    if (q) setQuery(q);
  }, [params]);

  const containers = useMemo(() => docker?.containers ?? [], [docker]);
  const running = containers.filter((container) => container.status === "running").length;
  const unexpected = containers.filter((container) => containerTone(container) === "bad").length;
  const tracked = containers.filter((container) => container.auto_heal_tracked).length;

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return containers
      .filter((container) => (filter === "running" ? container.status === "running" : filter === "stopped" ? container.status !== "running" : true))
      .filter((container) => !needle || `${container.name} ${container.image}`.toLowerCase().includes(needle))
      .sort((a, b) => {
        const rank = (container: Container) => ({ bad: 0, warn: 1, unknown: 2, ok: 3 })[containerTone(container)];
        return rank(a) - rank(b) || a.name.localeCompare(b.name);
      });
  }, [containers, filter, query]);

  async function restart(container: Container) {
    const verb = container.status === "running" ? t.restart : t.start;
    const ok = await confirm({ title: t.restartTitle(container.name), body: t.restartBody, confirmLabel: verb });
    if (!ok) return;
    setBusy(container.name);
    await act("actions/docker/restart", { container: container.name });
    setBusy(null);
  }

  const headline = !snapshot ? strings.connection.connecting : docker?.available === false ? t.unavailable : t.headline(running, containers.length);
  const tone: Tone | undefined = !snapshot ? undefined : docker?.available === false ? "unknown" : unexpected ? "bad" : "ok";

  return (
    <>
      <PageHeader
        eyebrow={t.eyebrow}
        headline={headline}
        tone={tone}
        meta={docker?.available ? [unexpected ? strings.status.problems(unexpected) : null, t.watching(tracked)].filter(Boolean).join(" · ") : undefined}
      />
      {docker?.available === false ? (
        <Card>
          <EmptyState icon={<Boxes size={22} />} title={t.unavailable}>
            {t.unavailableBody}
            {docker.error ? <span className="mono subtle"> ({docker.error})</span> : null}
          </EmptyState>
        </Card>
      ) : (
        <>
          <div className="toolbar">
            <SearchInput value={query} onChange={setQuery} label={t.search} />
            <Segmented<Filter>
              label="Filter containers"
              value={filter}
              onChange={setFilter}
              options={[
                { value: "all", label: t.all, count: containers.length },
                { value: "running", label: t.running, count: running },
                { value: "stopped", label: t.stopped, count: containers.length - running },
              ]}
            />
          </div>
          <div className="card">
            {!docker ? (
              <div className="card__body">
                <SkeletonRows rows={6} />
              </div>
            ) : filtered.length ? (
              <table className="table table--responsive">
                <thead>
                  <tr>
                    <th scope="col">Name</th>
                    <th scope="col">Status</th>
                    <th scope="col" className="hide-sm">
                      Image
                    </th>
                    <th scope="col">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((container) => {
                    const tone = containerTone(container);
                    return (
                      <tr key={container.name}>
                        <td>
                          <div className="stack stack--sm">
                            <strong>{container.name}</strong>
                            {container.user_stopped ? (
                              <span>
                                <span className="pill">{t.userStopped}</span>
                              </span>
                            ) : null}
                          </div>
                        </td>
                        <td>
                          <StatusPill tone={tone}>{statusLabel(container.status)}</StatusPill>
                        </td>
                        <td className="hide-sm">
                          <span className="mono muted">{container.image || "—"}</span>
                        </td>
                        <td className="actions">
                          {container.blocked ? (
                            <span className="subtle cluster" title={t.blocked}>
                              <Lock size={13} aria-hidden="true" />
                              {t.protected}
                            </span>
                          ) : (
                            <button type="button" className={`btn btn--sm ${tone === "bad" ? "btn--primary" : ""}`} disabled={busy === container.name} onClick={() => restart(container)}>
                              {container.status === "running" ? <RotateCcw size={13} aria-hidden="true" /> : <Play size={13} aria-hidden="true" />}
                              {container.status === "running" ? t.restart : t.start}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <EmptyState title={t.empty} />
            )}
          </div>
        </>
      )}
    </>
  );
}
