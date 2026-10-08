"use client";

import { Cable, Globe, Router, Server, Wifi } from "lucide-react";
import type { ReactNode } from "react";

import { Card, EmptyState, PageHeader, SkeletonRows } from "@/components/ui/layout";
import { StatusPill, toneFromBool, upDownLabel } from "@/components/ui/status";
import { useSheltie } from "@/lib/store";
import { strings } from "@/lib/strings";
import type { InterfaceInfo, Tone } from "@/lib/types";

const t = strings.network;

function ifaceLabel(label: string) {
  return label === "wifi" ? "Wi-Fi" : label === "ethernet" ? "Ethernet" : label;
}

function PathNode({ icon, name, detail, tone }: { icon: ReactNode; name: string; detail?: string; tone: Tone }) {
  return (
    <div className={`path__node ${tone === "bad" ? "path__node--bad" : tone === "warn" ? "path__node--warn" : ""}`}>
      {icon}
      <span className="path__name">{name}</span>
      {detail ? <span className="subtle">{detail}</span> : null}
      <StatusPill tone={tone}>{tone === "ok" ? strings.status.up : tone === "bad" ? strings.status.down : strings.status.unknown}</StatusPill>
    </div>
  );
}

function Link({ tone }: { tone: Tone }) {
  return <span className={`path__link ${tone === "bad" ? "path__link--bad" : tone === "unknown" ? "path__link--unknown" : ""}`} aria-hidden="true" />;
}

export function NetworkPage() {
  const { snapshot } = useSheltie();
  const network = snapshot?.network ?? null;
  const internet = network?.internet_up ?? snapshot?.status?.internet_up ?? null;
  const interfaces = Object.entries(network?.interfaces ?? {});
  const active = interfaces.find(([, iface]) => iface.name === network?.default_route);
  const routeTone: Tone = network?.default_route ? (active ? toneFromBool(active[1].up) : "ok") : "bad";
  const internetTone = toneFromBool(internet);

  const headline = !snapshot ? t.headlineUnknown : internet === false ? t.headlineDown : internet ? t.headlineOk : t.headlineUnknown;

  return (
    <>
      <PageHeader
        eyebrow={t.eyebrow}
        headline={headline}
        tone={snapshot ? internetTone : undefined}
        meta={network?.default_route_label ? t.viaRoute(network.default_route_label) : undefined}
      />
      <Card title={t.path} id="path">
        {!network ? (
          <SkeletonRows rows={1} />
        ) : (
          <div className="path" role="group" aria-label={t.path}>
              <PathNode icon={<Server size={22} aria-hidden="true" />} name={t.host} tone="ok" />
            <Link tone={routeTone} />
              <PathNode
                icon={active?.[0] === "wifi" ? <Wifi size={22} aria-hidden="true" /> : <Cable size={22} aria-hidden="true" />}
                name={active ? ifaceLabel(active[0]) : t.route}
                detail={network.default_route ?? "none"}
                tone={routeTone}
              />
            <Link tone={routeTone === "bad" ? "bad" : internetTone} />
              <PathNode icon={<Router size={22} aria-hidden="true" />} name="Router" detail={network.default_route_label} tone={routeTone} />
            <Link tone={internetTone} />
              <PathNode icon={<Globe size={22} aria-hidden="true" />} name={t.internet} tone={internetTone} />
          </div>
        )}
      </Card>
      <section className="stack" aria-labelledby="interfaces-title">
        <h2 className="card__title" id="interfaces-title">
          {t.interfaces}
        </h2>
        {!network ? (
          <SkeletonRows rows={2} />
        ) : interfaces.length ? (
          <div className="grid-2">
            {interfaces.map(([label, iface]) => (
              <InterfaceCard key={label} label={label} iface={iface} isRoute={iface.name === network.default_route} />
            ))}
          </div>
        ) : (
          <Card>
            <EmptyState title={t.noInterfaces} />
          </Card>
        )}
      </section>
    </>
  );
}

function InterfaceCard({ label, iface, isRoute }: { label: string; iface: InterfaceInfo; isRoute: boolean }) {
  return (
    <Card
      title={
        <>
          {label === "wifi" ? <Wifi size={16} aria-hidden="true" /> : <Cable size={16} aria-hidden="true" />}
          {ifaceLabel(label)}
        </>
      }
      action={<StatusPill tone={toneFromBool(iface.up)}>{upDownLabel(iface.up)}</StatusPill>}
    >
      <dl className="kv">
        <dt>Interface</dt>
        <dd className="mono">{iface.name}</dd>
        <dt>{t.state}</dt>
        <dd>{iface.operstate}</dd>
        <dt>{t.carrier}</dt>
        <dd>{iface.carrier ? t.yes : t.no}</dd>
        <dt>{t.ipv4}</dt>
        <dd>{iface.has_ip ? t.yes : t.no}</dd>
        <dt>{t.route}</dt>
        <dd>{isRoute ? t.yes : t.no}</dd>
      </dl>
    </Card>
  );
}
