"use client";

import { Cpu, Eraser, HardDrive, MemoryStick, Thermometer } from "lucide-react";
import type { ReactNode } from "react";

import { Meter, Sparkline, Stat } from "@/components/ui/data";
import { Card, PageHeader, SkeletonRows } from "@/components/ui/layout";
import { meterTone } from "@/lib/insights";
import { useLabwarden } from "@/lib/store";
import { strings } from "@/lib/strings";

const t = strings.host;

function MetricCard({ title, icon, value, series, suffix = "%", max = 100, warn = 75, bad = 90 }: { title: string; icon: ReactNode; value: number | null | undefined; series: number[]; suffix?: string; max?: number; warn?: number; bad?: number }) {
  return (
    <Card title={title} icon={icon}>
      <Meter label={title} value={value} suffix={suffix} max={max} warn={warn} bad={bad} />
      <Sparkline values={series} max={max} tone={meterTone(value, warn, bad)} label={`${title} trend`} />
      <p className="subtle">{t.trend}</p>
    </Card>
  );
}

export function HostPage() {
  const { snapshot, metrics, act, confirm } = useLabwarden();
  const health = snapshot?.health ?? null;

  const busy = health
    ? [
        health.cpu_percent >= 75 ? t.cpu : null,
        health.ram_percent >= 75 ? t.ram : null,
        health.disk_percent >= 90 ? `${t.disk} ${health.disk_path ?? "/"}` : null,
        health.cpu_temperature != null && health.cpu_temperature >= 70 ? t.temp : null,
      ].filter(Boolean)
    : [];
  const tone = !health ? undefined : busy.some((item) => item === t.temp || item?.startsWith(t.disk)) ? "bad" : busy.length ? "warn" : "ok";

  async function clearCache() {
    const ok = await confirm({ title: t.clearCacheTitle, body: t.clearCacheBody, confirmLabel: t.clearCache });
    if (ok) await act("actions/clear-ram-cache");
  }

  return (
    <>
      <PageHeader
        eyebrow={t.eyebrow}
        headline={!health ? strings.connection.connecting : busy.length ? t.headlineBusy(String(busy[0])) : t.headlineOk}
        tone={tone}
        actions={
          <button type="button" className="btn" onClick={clearCache}>
            <Eraser size={15} aria-hidden="true" />
            {t.clearCache}
          </button>
        }
      />
      {!health ? (
        <SkeletonRows rows={4} />
      ) : (
        <>
          <div className="grid-2">
            <MetricCard title={t.cpu} icon={<Cpu size={16} aria-hidden="true" />} value={health.cpu_percent} series={metrics.map((m) => m.cpu)} />
            <MetricCard title={t.ram} icon={<MemoryStick size={16} aria-hidden="true" />} value={health.ram_percent} series={metrics.map((m) => m.ram)} />
            <MetricCard title={`${t.disk} ${health.disk_path ?? "/"}`} icon={<HardDrive size={16} aria-hidden="true" />} value={health.disk_percent} series={metrics.map((m) => m.disk)} warn={80} bad={90} />
            {health.cpu_temperature != null ? (
              <MetricCard title={t.temp} icon={<Thermometer size={16} aria-hidden="true" />} value={health.cpu_temperature} series={metrics.map((m) => m.temp ?? 0)} suffix="°C" max={100} warn={70} bad={80} />
            ) : (
              <Card title={t.temp} icon={<Thermometer size={16} aria-hidden="true" />}>
                <p className="muted">{t.unavailable}</p>
              </Card>
            )}
          </div>
          {health.load_average ? (
            <div className="grid-tiles">
              {health.load_average.map((value, index) => (
                <Stat key={index} label={`${t.load} · ${[1, 5, 15][index]} min`} value={value.toFixed(2)} />
              ))}
            </div>
          ) : null}
        </>
      )}
    </>
  );
}
