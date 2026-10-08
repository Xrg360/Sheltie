"use client";

import { History, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { EventRow } from "./shared";
import { EmptyState, PageHeader, SearchInput, Segmented, SkeletonRows } from "@/components/ui/layout";
import { dayLabel, toMillis } from "@/lib/format";
import { eventKind } from "@/lib/insights";
import { useSheltie } from "@/lib/store";
import { strings } from "@/lib/strings";
import type { EventItem } from "@/lib/types";

const t = strings.incidents;
type Filter = "all" | "problem" | "recovery" | "repair";

export function IncidentsPage() {
  const { snapshot, act, confirm } = useSheltie();
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const events = useMemo(() => snapshot?.events ?? snapshot?.status?.recent_events ?? null, [snapshot]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (events ?? []).filter((event) => {
      if (filter !== "all" && eventKind(event) !== filter) return false;
      if (!needle) return true;
      return `${event.title} ${event.body} ${event.source}`.toLowerCase().includes(needle);
    });
  }, [events, filter, query]);

  const groups = useMemo(() => {
    const map = new Map<string, EventItem[]>();
    for (const event of filtered) {
      const label = dayLabel(toMillis(event.ts) ?? 0);
      map.set(label, [...(map.get(label) ?? []), event]);
    }
    return [...map.entries()];
  }, [filtered]);

  const counts = useMemo(() => {
    const result = { all: events?.length ?? 0, problem: 0, recovery: 0, repair: 0 };
    for (const event of events ?? []) {
      const kind = eventKind(event);
      if (kind !== "info") result[kind] += 1;
    }
    return result;
  }, [events]);

  async function clearHistory() {
    const ok = await confirm({ title: t.clearTitle, body: t.clearBody, confirmLabel: t.clear, danger: true });
    if (ok) await act("actions/events/clear");
  }

  return (
    <>
      <PageHeader
        eyebrow={t.eyebrow}
        headline={events ? t.headline(events.length) : strings.connection.connecting}
        meta={t.meta}
        actions={
          events?.length ? (
            <button type="button" className="btn" onClick={clearHistory}>
              <Trash2 size={15} aria-hidden="true" />
              {t.clear}
            </button>
          ) : null
        }
      />
      <div className="toolbar">
        <SearchInput value={query} onChange={setQuery} label={t.search} />
        <Segmented<Filter>
          label="Filter incidents"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: t.all, count: counts.all },
            { value: "problem", label: t.problems, count: counts.problem },
            { value: "recovery", label: t.recoveries, count: counts.recovery },
            { value: "repair", label: t.repairs, count: counts.repair },
          ]}
        />
      </div>
      {!events ? (
        <SkeletonRows rows={5} />
      ) : groups.length ? (
        <div className="timeline">
          {groups.map(([label, items]) => (
            <section key={label} className="timeline__day" aria-label={label}>
              <h2 className="timeline__date">{label}</h2>
              {items.map((event) => (
                <EventRow key={`${event.ts}-${event.alert_id}-${event.status}`} event={event} />
              ))}
            </section>
          ))}
        </div>
      ) : (
        <div className="card">
          <EmptyState icon={<History size={22} />} title={t.empty} />
        </div>
      )}
    </>
  );
}
