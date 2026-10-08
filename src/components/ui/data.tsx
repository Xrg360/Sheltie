"use client";

import Link from "next/link";
import { useMemo, useRef, useState } from "react";

import { clockTime, ms, pct, samples } from "@/lib/format";
import { meterTone } from "@/lib/insights";
import type { Site, SiteSample, Tone } from "@/lib/types";

/** Heartbeat bars: one bar per check, red and taller when down. */
export function UptimeBars({ site, count = 30, large }: { site: Site | null | undefined; count?: number; large?: boolean }) {
  const history = samples(site).slice(-count);
  const padded: Array<SiteSample | null> = [...Array(Math.max(0, count - history.length)).fill(null), ...history];
  const down = history.filter((sample) => !sample.up).length;
  const label = history.length ? `${history.length - down} of ${history.length} recent checks up` : "No checks yet";
  return (
    <div className={`bars ${large ? "bars--lg" : ""}`} role="img" aria-label={label}>
      {padded.map((sample, index) => (
        <span
          key={index}
          className={!sample ? "is-empty" : sample.up ? "" : "is-down"}
          title={sample ? `${clockTime(sample.ts)} · ${sample.up ? "up" : "down"} · ${ms(sample.latency_ms)}` : undefined}
        />
      ))}
    </div>
  );
}

/** Tiny trend line. Neutral unless the latest value crosses a threshold. */
export function Sparkline({ values, max = 100, tone = "ok", label }: { values: number[]; max?: number; tone?: Tone; label: string }) {
  const path = useMemo(() => {
    if (values.length < 2) return null;
    const top = Math.max(max, ...values);
    const step = 100 / (values.length - 1);
    const points = values.map((value, index) => [index * step, 36 - (value / top) * 32 - 2] as const);
    const line = points.map(([x, y], index) => `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
    return { line, area: `${line} L100,36 L0,36 Z` };
  }, [values, max]);
  return (
    <svg className={`spark ${tone === "warn" ? "spark--warn" : tone === "bad" ? "spark--bad" : ""}`} viewBox="0 0 100 36" preserveAspectRatio="none" role="img" aria-label={label}>
      {path ? (
        <>
          <path className="area" d={path.area} />
          <path className="line" d={path.line} />
        </>
      ) : null}
    </svg>
  );
}

/** Labelled meter with warn/bad thresholds. */
export function Meter({
  label,
  icon,
  value,
  suffix = "%",
  max = 100,
  warn = 75,
  bad = 90,
}: {
  label: string;
  icon?: React.ReactNode;
  value: number | null | undefined;
  suffix?: string;
  max?: number;
  warn?: number;
  bad?: number;
}) {
  const tone = meterTone(value, warn, bad);
  const width = value == null ? 0 : Math.max(0, Math.min(100, (value / max) * 100));
  const text = value == null ? "—" : `${Math.round(value)}${suffix}`;
  return (
    <div className="meter">
      <div className="meter__row">
        <span className="meter__label">
          {icon}
          {label}
        </span>
        <span className="meter__value">
          {text}
          {tone === "bad" ? <span className="sr-only"> (critical)</span> : tone === "warn" ? <span className="sr-only"> (high)</span> : null}
        </span>
      </div>
      <div className="meter__track" role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={max} aria-valuenow={value == null ? undefined : Math.round(value)}>
        <div className={`meter__fill ${tone === "warn" ? "meter__fill--warn" : tone === "bad" ? "meter__fill--bad" : ""}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

/** Response-time chart with a hover/touch cursor. Down checks are marked in red along the baseline. */
export function LatencyChart({ site }: { site: Site | null }) {
  const data = samples(site);
  const [hover, setHover] = useState<number | null>(null);
  const ref = useRef<SVGSVGElement>(null);
  const width = 640;
  const height = 220;
  const pad = { left: 44, right: 12, top: 14, bottom: 26 };
  const values = data.map((sample) => sample.latency_ms ?? 0);
  const top = Math.max(50, ...values) * 1.15;
  const step = data.length > 1 ? (width - pad.left - pad.right) / (data.length - 1) : 0;
  const x = (index: number) => pad.left + index * step;
  const y = (value: number) => pad.top + (1 - value / top) * (height - pad.top - pad.bottom);

  if (data.length < 2) {
    return <div className="empty">No response data yet. The first checks appear within a minute.</div>;
  }

  const line = data.map((sample, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(sample.latency_ms ?? 0).toFixed(1)}`).join(" ");
  const area = `${line} L${x(data.length - 1)},${height - pad.bottom} L${pad.left},${height - pad.bottom} Z`;
  const ticks = [0, 0.5, 1].map((fraction) => Math.round(top * fraction));

  function onMove(event: React.PointerEvent<SVGSVGElement>) {
    const box = ref.current?.getBoundingClientRect();
    if (!box) return;
    const localX = ((event.clientX - box.left) / box.width) * width;
    setHover(Math.max(0, Math.min(data.length - 1, Math.round((localX - pad.left) / (step || 1)))));
  }

  const point = hover != null ? data[hover] : null;
  const avg = values.reduce((sum, value) => sum + value, 0) / values.length;

  return (
    <div className="chart">
      <svg
        ref={ref}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Response time for the last ${data.length} checks, average ${Math.round(avg)} milliseconds`}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {ticks.map((tick) => (
          <g key={tick}>
            <line className="grid-line" x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} />
            <text className="axis-label" x={4} y={y(tick) + 4}>
              {tick} ms
            </text>
          </g>
        ))}
        <path className="area" d={area} />
        <path className="line" d={line} />
        {data.map((sample, index) => (sample.up ? null : <rect key={index} className="down-mark" x={x(index) - 2} y={height - pad.bottom - 4} width={4} height={6} rx={1} />))}
        {point && hover != null ? (
          <>
            <line className="cursor" x1={x(hover)} x2={x(hover)} y1={pad.top} y2={height - pad.bottom} />
            <circle className="cursor-dot" cx={x(hover)} cy={y(point.latency_ms ?? 0)} r={4} />
          </>
        ) : null}
        <text className="axis-label" x={pad.left} y={height - 6}>
          {clockTime(data[0].ts)}
        </text>
        <text className="axis-label" x={width - pad.right} y={height - 6} textAnchor="end">
          {clockTime(data[data.length - 1].ts)}
        </text>
      </svg>
      {point && hover != null ? (
        <div className="chart__tip" style={{ left: `${(x(hover) / width) * 100}%` }}>
          <strong>{point.up ? ms(point.latency_ms) : "Down"}</strong> · {clockTime(point.ts)}
          {point.status_code ? ` · HTTP ${point.status_code}` : ""}
        </div>
      ) : null}
    </div>
  );
}

export function Stat({ label, icon, value, sub, href }: { label: string; icon?: React.ReactNode; value: React.ReactNode; sub?: React.ReactNode; href?: string }) {
  const content = (
    <>
      <span className="stat__label">
        {icon}
        {label}
      </span>
      <span className="stat__value">{value}</span>
      {sub ? <span className="stat__sub">{sub}</span> : null}
    </>
  );
  return href ? (
    <Link className="stat" href={href}>
      {content}
    </Link>
  ) : (
    <div className="stat">{content}</div>
  );
}

export function percent(value: number | null | undefined) {
  return pct(value, value != null && value < 99.95 && value > 0 ? 1 : 0);
}
