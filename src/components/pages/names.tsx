"use client";

import { ExternalLink, Globe2, Pencil, Plus, RefreshCw, Settings2, ShieldCheck, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { CopyText } from "@/components/ui/copy";
import { Dialog } from "@/components/ui/dialog";
import { Card, EmptyState, SkeletonRows } from "@/components/ui/layout";
import { StatusPill, toneFromBool } from "@/components/ui/status";
import { TimeAgo } from "./shared";
import { fetchNameChecks, fetchNameTargets } from "@/lib/api";
import { REPO_URL } from "@/lib/nav";
import { useSheltie } from "@/lib/store";
import { strings } from "@/lib/strings";
import type { NameCheck, NameRecord, NamesPayload, NameTargets } from "@/lib/types";

const t = strings.names;
type EnabledNames = Extract<NamesPayload, { enabled: true }>;

/** Whether a record was made by picking a Tailscale device (DNS only, or through the proxy when it has a port). */
function recordMode(record: NameRecord): "app" | "device" {
  return record.kind === "device" || record.source === "device" ? "device" : "app";
}

function recordTarget(record: NameRecord): string {
  const where = record.target_host + (record.target_port ? `:${record.target_port}` : "");
  return record.label && record.label !== record.target_host ? `${record.label} (${where})` : where;
}

/** Names and their problems, shown on the Network page. Off unless the backend has names turned on. */
export function NamesSection() {
  const { snapshot } = useSheltie();
  const names = snapshot?.names;
  const [editing, setEditing] = useState<NameRecord | "new" | null>(null);

  if (names === undefined || names === null) {
    return (
      <Card title={t.title} icon={<Globe2 size={16} aria-hidden="true" />} id="names">
        <SkeletonRows rows={2} />
      </Card>
    );
  }
  if (!names.enabled) {
    return (
      <Card title={t.title} icon={<Globe2 size={16} aria-hidden="true" />} id="names">
        <EmptyState
          title={t.off}
          action={
            <a className="btn" href={`${REPO_URL}#dns-names`} target="_blank" rel="noreferrer">
              {t.offLink}
            </a>
          }
        >
          {t.offBody}
        </EmptyState>
      </Card>
    );
  }
  return (
    <>
      <NamesList names={names} onAdd={() => setEditing("new")} onEdit={setEditing} />
      <div className="grid-2">
        <SetupCard zone={names.zone} />
        <DomainCard names={names} />
      </div>
      <NameSheet names={names} editing={editing} onClose={() => setEditing(null)} />
    </>
  );
}

function NamesList({ names, onAdd, onEdit }: { names: EnabledNames; onAdd: () => void; onEdit: (record: NameRecord) => void }) {
  const { act, confirm, toast } = useSheltie();
  const [busy, setBusy] = useState(false);
  const problems = names.records.filter((record) => record.reachable.ok === false || record.sync_error).length;

  async function remove(record: NameRecord) {
    const ok = await confirm({ title: t.removeTitle(record.fqdn), body: t.removeBody, confirmLabel: t.remove, danger: true });
    if (!ok) return;
    const result = await act("actions/names/remove", { id: record.id }, { quiet: true });
    if (result?.ok) {
      toast({
        tone: "ok",
        title: t.removed(record.fqdn),
        action: {
          label: t.undo,
          run: () =>
            void act(
              "actions/names/add",
              { name: record.name, mode: recordMode(record), host: record.target_host, port: record.target_port, scheme: record.scheme, websockets: record.websockets, source: record.source, label: record.label },
              { success: t.form.added(record.fqdn) },
            ),
        },
      });
    }
  }

  async function retry() {
    setBusy(true);
    await act("actions/names/sync");
    setBusy(false);
  }

  return (
    <Card
      title={t.title}
      icon={<Globe2 size={16} aria-hidden="true" />}
      id="names"
      tone={problems ? "bad" : undefined}
      action={
        <button type="button" className="btn btn--primary btn--sm" onClick={onAdd}>
          <Plus size={14} aria-hidden="true" />
          {t.add}
        </button>
      }
    >
      <p className="muted">
        {t.meta(names.zone)} · {t.summary(names.records.length, problems)}
      </p>
      {names.last_sync && !names.last_sync.ok ? (
        <div className="switch-row" role="alert">
          <span className="cluster">
            <StatusPill tone="warn">{t.proxyProblem}</StatusPill>
            <span className="subtle">{names.last_sync.error}</span>
          </span>
          <button type="button" className="btn btn--sm" onClick={retry} disabled={busy}>
            <RefreshCw size={13} aria-hidden="true" />
            {t.retrySync}
          </button>
        </div>
      ) : null}
      {names.records.length ? (
        <ul className="list" aria-label={t.title}>
          {names.records.map((record) => {
            const tone = record.sync_error ? "warn" : toneFromBool(record.reachable.ok);
            return (
              <li key={record.id} className="row row--wrap">
                <div className="row__main">
                  <a className="row__title link" href={record.url} target="_blank" rel="noreferrer">
                    {record.fqdn}
                  </a>
                  <span className="row__sub">{record.kind === "device" ? `${t.via(recordTarget(record))} · ${t.deviceOnly}` : t.via(recordTarget(record))}</span>
                  {record.sync_error ? <span className="row__sub">{record.sync_error}</span> : record.reachable.why ? <span className="row__sub">{record.reachable.why}</span> : null}
                </div>
                <div className="cluster">
                  <StatusPill tone={tone}>{record.sync_error ? t.proxyProblem : record.reachable.ok === true ? t.up : record.reachable.ok === false ? t.down : t.unknown}</StatusPill>
                  <a className="btn btn--ghost btn--sm btn--icon" href={record.url} target="_blank" rel="noreferrer" aria-label={`${t.open} ${record.fqdn}`}>
                    <ExternalLink size={14} aria-hidden="true" />
                  </a>
                  <button type="button" className="btn btn--sm" onClick={() => onEdit(record)} aria-label={`${t.edit} ${record.fqdn}`}>
                    <Pencil size={13} aria-hidden="true" />
                    {t.edit}
                  </button>
                  <button type="button" className="btn btn--ghost btn--sm btn--icon" onClick={() => remove(record)} aria-label={`${t.remove} ${record.fqdn}`}>
                    <Trash2 size={14} aria-hidden="true" />
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <EmptyState title={t.empty}>{t.emptyBody}</EmptyState>
      )}
      {names.last_sync?.ok ? (
        <p className="subtle">
          {t.lastSync} <TimeAgo value={names.last_sync.at} />
        </p>
      ) : null}
    </Card>
  );
}

function SetupCard({ zone }: { zone: string }) {
  const [checks, setChecks] = useState<NameCheck[] | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setChecks(await fetchNameChecks());
      setFailed(null);
    } catch (error) {
      setFailed(error instanceof Error ? error.message : String(error));
    } finally {
      setLoading(false);
    }
  }, []);

  // Re-check when the domain changes: split DNS and the DNS server answer for the zone.
  useEffect(() => {
    void load();
  }, [load, zone]);

  const left = checks?.filter((check) => !check.ok).length ?? 0;
  return (
    <Card
      title={t.setup}
      icon={<ShieldCheck size={16} aria-hidden="true" />}
      id="names-setup"
      tone={left ? "warn" : undefined}
      action={
        <button type="button" className="btn btn--sm" onClick={load} disabled={loading}>
          <RefreshCw size={13} aria-hidden="true" />
          {loading ? t.checking : t.checkAgain}
        </button>
      }
    >
      {failed ? (
        <p className="subtle" role="alert">
          {failed}
        </p>
      ) : !checks ? (
        <SkeletonRows rows={3} />
      ) : (
        <>
          <p className="muted">{left ? t.setupProblems(left) : t.setupOk}</p>
          <ul className="stack plain-list" aria-label={t.setup}>
            {checks.map((check) => (
              <li key={check.id} className="stack stack--sm">
                <span className="cluster">
                  <StatusPill tone={check.ok ? "ok" : "bad"}>{check.title}</StatusPill>
                </span>
                <span className="subtle">{check.detail}</span>
                {check.fix ? (
                  <div className="stack stack--sm">
                    <ol className="stack stack--sm steps">
                      {check.fix.steps.map((step) => (
                        <li key={step}>{step}</li>
                      ))}
                    </ol>
                    {check.fix.copy
                      ? Object.entries(check.fix.copy).map(([label, value]) => (
                          <span key={label} className="cluster">
                            <span className="label">{label}</span>
                            <CopyText text={value} what={label.toLowerCase()} />
                          </span>
                        ))
                      : null}
                    {check.fix.link ? (
                      <span>
                        <a className="btn btn--sm" href={check.fix.link} target="_blank" rel="noreferrer">
                          <ExternalLink size={13} aria-hidden="true" />
                          {t.openConsole}
                        </a>
                      </span>
                    ) : null}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

function DomainCard({ names }: { names: EnabledNames }) {
  const { act, confirm } = useSheltie();
  const [label, setLabel] = useState(names.domain.label);
  const [tld, setTld] = useState(names.domain.tld);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setLabel(names.domain.label);
    setTld(names.domain.tld);
  }, [names.domain.label, names.domain.tld]);

  const next = `${label.trim().toLowerCase()}.${tld.trim().toLowerCase()}`;
  const changed = next !== names.zone;

  async function saveDomain(event: React.FormEvent) {
    event.preventDefault();
    if (!changed) return;
    const ok = await confirm({ title: t.domainTitle(next), body: t.domainBody, confirmLabel: t.domainSave });
    if (!ok) return;
    setBusy(true);
    await act("actions/names/domain", { label, tld });
    setBusy(false);
  }

  async function setAccess(on: boolean) {
    if (!on) {
      const ok = await confirm({ title: t.accessOffTitle, body: t.accessOffBody, confirmLabel: t.accessOffConfirm, danger: true });
      if (!ok) return;
    }
    await act("actions/names/access", { tailnet_only: on });
  }

  return (
    <Card title={t.settings} icon={<Settings2 size={16} aria-hidden="true" />} id="names-settings">
      <form className="stack" onSubmit={saveDomain}>
        <fieldset className="field fieldset">
          <legend className="label">{t.domain}</legend>
          <span className="cluster">
            <input className="input mono" aria-label={t.domainLabel} value={label} onChange={(event) => setLabel(event.target.value)} autoComplete="off" spellCheck={false} />
            <span aria-hidden="true">.</span>
            <input className="input mono" aria-label={t.domainTld} value={tld} onChange={(event) => setTld(event.target.value)} autoComplete="off" spellCheck={false} />
          </span>
          <span className="hint">{t.domainHint}</span>
        </fieldset>
        <div>
          <button type="submit" className="btn" disabled={!changed || busy}>
            {t.domainSave}
          </button>
        </div>
      </form>
      <label className="switch-row">
        <span className="stack stack--sm">
          <span>{t.access}</span>
          <span className="subtle">{t.accessHint}</span>
        </span>
        <input className="switch" type="checkbox" role="switch" checked={names.tailnet_only} onChange={(event) => void setAccess(event.target.checked)} />
      </label>
    </Card>
  );
}

const MANUAL = "manual";

function suggestName(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);
}

function NameSheet({ names, editing, onClose }: { names: EnabledNames; editing: NameRecord | "new" | null; onClose: () => void }) {
  const { act } = useSheltie();
  const f = t.form;
  const open = editing !== null;
  const record = editing === "new" ? null : editing;
  const [targets, setTargets] = useState<NameTargets | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [mode, setMode] = useState<"app" | "device">("app");
  const [choice, setChoice] = useState("");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("");
  const [https, setHttps] = useState(false);
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [error, setError] = useState<{ field?: string; message: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setLoadError(null);
    setTargets(null);
    setName(record?.name ?? "");
    setNameTouched(Boolean(record));
    setMode(record ? recordMode(record) : "app");
    setHost(record?.target_host ?? "");
    setPort(record?.target_port ? String(record.target_port) : "");
    setHttps(record?.scheme === "https");
    setChoice(record ? (recordMode(record) === "device" ? record.target_host : MANUAL) : "");
    fetchNameTargets()
      .then((result) => {
        setTargets(result);
        if (record && recordMode(record) === "app") {
          const match = [...result.apps, ...result.ports].find((target) => target.host === record.target_host && target.port === record.target_port);
          setChoice(match ? match.id : MANUAL);
        }
      })
      .catch((reason) => setLoadError(reason instanceof Error ? reason.message : String(reason)));
  }, [open, record]);

  const appTargets = useMemo(() => [...(targets?.apps ?? []), ...(targets?.ports ?? [])], [targets]);
  const picked = mode === "app" ? appTargets.find((target) => target.id === choice) : undefined;
  const device = mode === "device" ? targets?.devices.find((entry) => entry.ip === choice) : undefined;

  function pick(value: string) {
    setChoice(value);
    const target = appTargets.find((entry) => entry.id === value);
    if (target) {
      setHost(target.host);
      setPort(target.port ? String(target.port) : "");
      if (!nameTouched) setName(suggestName(target.name));
    }
    const dev = targets?.devices.find((entry) => entry.ip === value);
    if (dev) {
      setHost(dev.ip);
      if (!nameTouched) setName(suggestName(dev.name));
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const label = picked ? picked.name : device ? `${device.name} (Tailscale device)` : host;
    const source = picked ? picked.source : mode === "device" ? "device" : "manual";
    const body = { id: record?.id, name: name.trim().toLowerCase(), mode, host: host.trim(), port: port.trim() || null, scheme: https ? "https" : "http", websockets: true, source, label };
    const fqdn = `${body.name}.${names.zone}`;
    setBusy(true);
    const result = await act(record ? "actions/names/update" : "actions/names/add", body, { success: record ? f.saved(fqdn) : f.added(fqdn) });
    setBusy(false);
    if (!result) return;
    if (!result.ok) {
      setError({ field: typeof result.field === "string" ? result.field : undefined, message: result.error || strings.actions.failed });
      return;
    }
    onClose();
  }

  const fieldError = (field: string) => (error?.field === field ? error.message : null);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={record ? f.editTitle(record.fqdn) : f.addTitle}
      variant="sheet"
      labelledBy="name-sheet-title"
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            {f.cancel}
          </button>
          <button type="submit" form="name-form" className="btn btn--primary" disabled={busy}>
            {record ? f.save : t.add}
          </button>
        </>
      }
    >
      <form id="name-form" className="stack" onSubmit={submit} noValidate>
        <fieldset className="field fieldset">
          <legend className="label">{f.pointsTo}</legend>
          <div role="radiogroup" className="stack stack--sm">
            <label className="cluster">
              <input type="radio" name="name-mode" checked={mode === "app"} onChange={() => { setMode("app"); setChoice(""); }} />
              {f.app}
            </label>
            <label className="cluster">
              <input type="radio" name="name-mode" checked={mode === "device"} onChange={() => { setMode("device"); setChoice(""); setPort(""); }} />
              {f.device}
            </label>
          </div>
        </fieldset>

        {loadError ? (
          <p className="subtle" role="alert">
            {f.loadFailed}: {loadError}
          </p>
        ) : !targets ? (
          <p className="subtle" aria-busy="true">
            {f.loading}
          </p>
        ) : mode === "app" ? (
          <div className="field">
            <label className="label" htmlFor="name-target">
              {f.app}
            </label>
            <select id="name-target" className="select" value={choice} onChange={(event) => pick(event.target.value)} aria-invalid={Boolean(fieldError("host"))}>
              <option value="" disabled>
                {f.pick}
              </option>
              {targets.apps.length ? (
                <optgroup label={f.apps}>
                  {targets.apps.map((target) => (
                    <option key={target.id} value={target.id} disabled={target.disabled}>
                      {target.label}
                    </option>
                  ))}
                </optgroup>
              ) : null}
              {targets.ports.length ? (
                <optgroup label={f.otherPorts}>
                  {targets.ports.map((target) => (
                    <option key={target.id} value={target.id}>
                      {target.label}
                    </option>
                  ))}
                </optgroup>
              ) : null}
              <option value={MANUAL}>{f.manual}</option>
            </select>
            {!targets.apps.length ? <span className="hint">{f.noApps}</span> : null}
          </div>
        ) : (
          <div className="field">
            <label className="label" htmlFor="name-device">
              {f.device}
            </label>
            <select id="name-device" className="select" value={choice} onChange={(event) => pick(event.target.value)} aria-invalid={Boolean(fieldError("host"))}>
              <option value="" disabled>
                {f.pick}
              </option>
              {targets.devices.map((entry) => (
                <option key={entry.ip} value={entry.ip}>
                  {entry.name} · {entry.ip}
                  {entry.is_self ? ` (${f.thisServer})` : entry.online ? "" : ` (${f.offline})`}
                </option>
              ))}
            </select>
          </div>
        )}

        {mode === "app" && choice === MANUAL ? (
          <div className="grid-2">
            <div className="field">
              <label className="label" htmlFor="name-host">
                {f.host}
              </label>
              <input id="name-host" className="input mono" value={host} onChange={(event) => setHost(event.target.value)} autoComplete="off" spellCheck={false} aria-describedby="name-host-hint" aria-invalid={Boolean(fieldError("host"))} />
              <span id="name-host-hint" className="hint">
                {f.hostHint}
              </span>
            </div>
            <div className="field">
              <label className="label" htmlFor="name-port">
                {f.port}
              </label>
              <input id="name-port" className="input mono" inputMode="numeric" value={port} onChange={(event) => setPort(event.target.value)} aria-invalid={Boolean(fieldError("port"))} />
            </div>
          </div>
        ) : null}

        {mode === "device" ? (
          <div className="field">
            <label className="label" htmlFor="name-device-port">
              {f.devicePort}
            </label>
            <input id="name-device-port" className="input mono" inputMode="numeric" value={port} onChange={(event) => setPort(event.target.value)} aria-describedby="name-device-port-hint" aria-invalid={Boolean(fieldError("port"))} />
            <span id="name-device-port-hint" className="hint">
              {f.devicePortHint}
            </span>
          </div>
        ) : null}

        {mode === "app" || port.trim() ? (
          <label className="switch-row">
            <span>{f.https}</span>
            <input className="switch" type="checkbox" role="switch" checked={https} onChange={(event) => setHttps(event.target.checked)} />
          </label>
        ) : null}

        <div className="field">
          <label className="label" htmlFor="name-name">
            {f.name}
          </label>
          <input
            id="name-name"
            className="input mono"
            value={name}
            onChange={(event) => {
              setName(event.target.value);
              setNameTouched(true);
            }}
            autoComplete="off"
            spellCheck={false}
            aria-describedby="name-name-hint"
            aria-invalid={Boolean(fieldError("name"))}
          />
          <span id="name-name-hint" className="hint">
            {name.trim() ? `${name.trim().toLowerCase()}.${names.zone}` : f.nameHint(names.zone)}
          </span>
        </div>

        {error ? (
          <p className="subtle" role="alert">
            <StatusPill tone="bad">{strings.actions.failed}</StatusPill> {error.message}
          </p>
        ) : null}
      </form>
    </Dialog>
  );
}
