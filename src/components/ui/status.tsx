import { CircleCheck, CircleHelp, CircleX, TriangleAlert } from "lucide-react";

import { strings } from "@/lib/strings";
import type { Tone } from "@/lib/types";

// Status is never color alone: every tone has an icon shape and a word (DESIGN.md, principle 2).
const ICONS = { ok: CircleCheck, warn: TriangleAlert, bad: CircleX, unknown: CircleHelp } as const;

export function toneFromBool(value: boolean | null | undefined): Tone {
  if (value === true) return "ok";
  if (value === false) return "bad";
  return "unknown";
}

export function upDownLabel(value: boolean | null | undefined): string {
  if (value === true) return strings.status.up;
  if (value === false) return strings.status.down;
  return strings.status.unknown;
}

export function StatusIcon({ tone, size = 16, label }: { tone: Tone; size?: number; label?: string }) {
  const Icon = ICONS[tone];
  return <Icon className={`icon-${tone}`} size={size} aria-label={label} aria-hidden={label ? undefined : true} strokeWidth={2.2} />;
}

export function StatusPill({ tone, children }: { tone: Tone | "accent"; children: React.ReactNode }) {
  return (
    <span className={`pill tone-${tone}`}>
      {tone === "accent" ? null : <StatusIcon tone={tone} size={13} />}
      {children}
    </span>
  );
}

export function StatusGlyph({ tone, size = "lg" }: { tone: Tone; size?: "lg" | "sm" }) {
  const Icon = ICONS[tone];
  return (
    <span className={`glyph tone-${tone} ${size === "sm" ? "glyph--sm" : ""}`} aria-hidden="true">
      <Icon size={size === "sm" ? 18 : 26} strokeWidth={2.2} />
    </span>
  );
}

export function Dot({ tone, live }: { tone: Tone; live?: boolean }) {
  return <span className={`dot dot--${tone} ${live ? "dot--live" : ""}`} aria-hidden="true" />;
}
