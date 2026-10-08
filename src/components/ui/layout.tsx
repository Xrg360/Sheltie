"use client";

import { Search } from "lucide-react";
import type { ReactNode } from "react";

import { StatusGlyph } from "./status";
import type { Tone } from "@/lib/types";

/** Every page starts with an answer: eyebrow + headline sentence + meta (DESIGN.md invariant 1). */
export function PageHeader({ eyebrow, headline, tone, meta, actions }: { eyebrow: string; headline: ReactNode; tone?: Tone; meta?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-header">
      <div className="page-header__text">
        <span className="eyebrow">{eyebrow}</span>
        <h1 className="headline">
          {tone ? <StatusGlyph tone={tone} /> : null}
          <span>{headline}</span>
        </h1>
        {meta ? <p className="page-meta">{meta}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

export function Card({
  title,
  icon,
  action,
  children,
  flush,
  tone,
  id,
}: {
  title?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  flush?: boolean;
  tone?: "bad" | "warn";
  id?: string;
}) {
  return (
    <section className={`card ${tone ? `card--tone-${tone}` : ""}`} aria-labelledby={id && title ? `${id}-title` : undefined}>
      {title ? (
        <div className="card__head">
          <h2 className="card__title" id={id ? `${id}-title` : undefined}>
            {icon}
            {title}
          </h2>
          {action}
        </div>
      ) : null}
      <div className={`card__body ${flush ? "card__body--flush" : ""}`}>{children}</div>
    </section>
  );
}

export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      {icon ? <span className="empty__icon">{icon}</span> : null}
      <p className="empty__title">{title}</p>
      {children ? <p>{children}</p> : null}
      {action}
    </div>
  );
}

export function Skeleton({ height = 14, width = "100%" }: { height?: number; width?: number | string }) {
  return <div className="skeleton" style={{ height, width }} aria-hidden="true" />;
}

export function SkeletonRows({ rows = 3 }: { rows?: number }) {
  return (
    <div className="stack" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} height={44} />
      ))}
    </div>
  );
}

export function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: Array<{ value: T; label: string; count?: number }>; onChange: (value: T) => void; label: string }) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button key={option.value} type="button" aria-pressed={value === option.value} onClick={() => onChange(option.value)}>
          {option.label}
          {option.count != null ? <span className="subtle">{option.count}</span> : null}
        </button>
      ))}
    </div>
  );
}

export function SearchInput({ value, onChange, label }: { value: string; onChange: (value: string) => void; label: string }) {
  return (
    <div className="search">
      <Search size={16} aria-hidden="true" />
      <input className="input" type="search" value={value} placeholder={label} aria-label={label} onChange={(event) => onChange(event.target.value)} />
    </div>
  );
}
