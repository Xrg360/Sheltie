"use client";

import { Cpu, Eraser, HardDrive, MemoryStick, Plug, Thermometer } from "lucide-react";
import type { ReactNode } from "react";

import { Meter, Sparkline, Stat } from "@/components/ui/data";
import { Card, PageHeader, SkeletonRows } from "@/components/ui/layout";
import { StatusPill } from "@/components/ui/status";
import { meterTone } from "@/lib/insights";
import { useSheltie } from "@/lib/store";
import { strings } from "@/lib/strings";
import type { AcRecoveryMode, PowerPayload, Tone } from "@/lib/types";

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

const p = t.power;

function recoveryState(power: PowerPayload): { tone: Tone; label: string; explain: string } {
  const recovery = power.ac_recovery;
  if (!recovery.supported) return { tone: "unknown", label: p.notSupported, explain: recovery.reason || p.explainUnknown };
  if (recovery.mode === "on") return { tone: "ok", label: p.on, explain: p.explainOn };
  if (recovery.mode === "last") return { tone: "ok", label: p.last, explain: p.explainLast };
  if (recovery.mode === "off") return { tone: "warn", label: p.off, explain: p.explainOff };
  return { tone: "unknown", label: p.unknown, explain: recovery.reason || p.explainUnknown };
}

function PowerCard({ power }: { power: PowerPayload }) {
  const { act, confirm } = useSheltie();
  const recovery = power.ac_recovery;
  const state = recoveryState(power);
  const machine = [power.vendor, power.model].filter(Boolean).join(" ");
  const source = power.ac_online === true ? p.mains : power.ac_online === false ? p.battery : p.unknownSource;

  async function change(mode: AcRecoveryMode) {
    const on = mode !== "off";
    const ok = await confirm({ title: on ? p.turnOnTitle : p.turnOffTitle, body: on ? p.turnOnBody : p.turnOffBody, confirmLabel: on ? p.turnOn : p.turnOff, danger: !on });
    if (ok) await act("actions/power/ac-recovery", { mode }, { success: on ? p.turnedOn : p.turnedOff });
  }

  return (
    <Card
      title={p.title}
      icon={<Plug size={16} aria-hidden="true" />}
      tone={recovery.supported && recovery.mode === "off" ? "warn" : undefined}
      action={power.ac_online === false ? <StatusPill tone="warn">{p.onBattery}</StatusPill> : undefined}
    >
      <div className="stack">
        <dl className="kv">
          <dt>{p.autoOn}</dt>
          <dd>
            <StatusPill tone={state.tone}>{state.label}</StatusPill>
          </dd>
          <dt>{p.source}</dt>
          <dd>{source}</dd>
          {power.battery_percent != null ? (
            <>
              <dt>{p.battery}</dt>
              <dd>{p.batteryLevel(power.battery_percent, power.battery_status)}</dd>
            </>
          ) : null}
          {machine ? (
            <>
              <dt>{p.machine}</dt>
              <dd>{machine}</dd>
            </>
          ) : null}
        </dl>
        <p className="subtle">{state.explain}</p>
        {recovery.supported && recovery.mode === "off" && recovery.modes.includes("on") ? (
          <div>
            <button type="button" className="btn btn--primary" onClick={() => change("on")}>
              {p.turnOn}
            </button>
          </div>
        ) : null}
        {recovery.supported && (recovery.mode === "on" || recovery.mode === "last") && recovery.modes.includes("off") ? (
          <div>
            <button type="button" className="btn" onClick={() => change("off")}>
              {p.turnOff}
            </button>
          </div>
        ) : null}
      </div>
    </Card>
  );
}

export function HostPage() {
  const { snapshot, metrics, act, confirm } = useSheltie();
  const health = snapshot?.health ?? null;
  const power = snapshot?.power ?? null;

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
          {power ? <PowerCard power={power} /> : null}
        </>
      )}
    </>
  );
}
