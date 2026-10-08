"use client";

import { ExternalLink, Info, RotateCcw } from "lucide-react";
import Link from "next/link";

import { StatusIcon } from "@/components/ui/status";
import { absoluteTime, relativeTime } from "@/lib/format";
import { eventTone } from "@/lib/insights";
import type { Problem } from "@/lib/insights";
import { useSheltie } from "@/lib/store";
import { strings } from "@/lib/strings";
import type { EventItem } from "@/lib/types";

export function TimeAgo({ value }: { value: string | number | null | undefined }) {
  useSheltie(); // re-render with the shared 1s clock so relative times stay honest
  if (value == null) return null;
  const iso = typeof value === "number" ? new Date(value < 1e12 ? value * 1000 : value).toISOString() : value;
  return (
    <time dateTime={iso} title={absoluteTime(value)}>
      {relativeTime(value)}
    </time>
  );
}

export function EventRow({ event, compact }: { event: EventItem; compact?: boolean }) {
  const tone = eventTone(event);
  const lines = event.body.split("\n").filter(Boolean);
  return (
    <article className={`event ${compact ? "event--compact" : ""}`}>
      {tone === "unknown" ? (
        <Info className="icon-unknown" size={18} aria-label="Info" />
      ) : (
        <StatusIcon tone={tone} size={18} label={tone === "ok" ? "Resolved" : tone === "bad" ? "Problem" : "Warning"} />
      )}
      <div className="stack stack--sm">
        <h3 className="event__title">{event.title}</h3>
        <p className="event__body">{compact ? lines.join(" · ") : lines.join("\n")}</p>
      </div>
      <span className="event__time">
        <TimeAgo value={event.ts} />
      </span>
    </article>
  );
}

export function ProblemItem({ problem }: { problem: Problem }) {
  const { act, confirm } = useSheltie();
  return (
    <div className="attention">
      <StatusIcon tone={problem.tone} size={22} label={problem.tone === "bad" ? "Problem" : "Warning"} />
      <div className="attention__text">
        <h3 className="attention__title">{problem.title}</h3>
        {problem.body ? <p className="muted">{problem.body}</p> : null}
        {problem.since ? (
          <p className="subtle">
            Since <TimeAgo value={problem.since} />
          </p>
        ) : null}
      </div>
      <div className="attention__actions">
        {problem.actions.map((action) => {
          if (action.kind === "link") {
            return (
              <Link key={action.label} className="btn btn--sm" href={action.href}>
                {action.label}
              </Link>
            );
          }
          if (action.kind === "external") {
            return (
              <a key={action.label} className="btn btn--sm" href={action.href} target="_blank" rel="noreferrer">
                {action.label}
                <ExternalLink size={13} aria-hidden="true" />
              </a>
            );
          }
          return (
            <button
              key={action.label}
              type="button"
              className="btn btn--sm btn--primary"
              onClick={async () => {
                const ok = await confirm({ title: strings.containers.restartTitle(action.container), body: strings.containers.restartBody, confirmLabel: action.label });
                if (ok) await act("actions/docker/restart", { container: action.container });
              }}
            >
              <RotateCcw size={13} aria-hidden="true" />
              {action.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
