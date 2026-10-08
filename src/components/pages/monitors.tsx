"use client";

import { Activity, ExternalLink, Plus, Trash2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { TimeAgo } from "./shared";
import { LatencyChart, Stat, UptimeBars, percent } from "@/components/ui/data";
import { Dialog } from "@/components/ui/dialog";
import { Card, EmptyState, PageHeader, SearchInput, Segmented, SkeletonRows } from "@/components/ui/layout";
import { StatusPill } from "@/components/ui/status";
import { averageLatency, hostFromUrl, isValidHttpUrl, ms, nameFromUrl, percentileLatency, samples, uptime } from "@/lib/format";
import { useSheltie } from "@/lib/store";
import { strings } from "@/lib/strings";
import type { Site } from "@/lib/types";

const t = strings.monitors;
type Filter = "all" | "down" | "up";

export function MonitorsPage() {
  const { snapshot, act, confirm, toast } = useSheltie();
  const router = useRouter();
  const params = useSearchParams();
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(params.get("site"));
  const [adding, setAdding] = useState(params.get("add") === "1");
  const [detailOpen, setDetailOpen] = useState(false);
  const sites = useMemo(() => snapshot?.sites?.sites ?? null, [snapshot]);

  useEffect(() => {
    const site = params.get("site");
    if (site) setSelected(site);
    if (params.get("add") === "1") setAdding(true);
  }, [params]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (sites ?? [])
      .filter((site) => (filter === "down" ? !site.up : filter === "up" ? site.up : true))
      .filter((site) => !needle || `${site.name} ${site.url}`.toLowerCase().includes(needle))
      .sort((a, b) => Number(a.up) - Number(b.up) || a.name.localeCompare(b.name));
  }, [sites, filter, query]);

  const current = sites?.find((site) => site.name === selected) ?? filtered[0] ?? null;

  function select(site: Site) {
    setSelected(site.name);
    if (window.matchMedia("(max-width: 1100px)").matches) setDetailOpen(true);
    router.replace(`/monitors?site=${encodeURIComponent(site.name)}`, { scroll: false });
  }

  async function remove(site: Site) {
    const ok = await confirm({ title: t.removeTitle(site.name), body: t.removeBody, confirmLabel: t.remove, danger: true });
    if (!ok) return;
    const result = await act("actions/sites/remove", { name: site.name }, { quiet: true });
    if (result?.ok) {
      setSelected(null);
      setDetailOpen(false);
      toast({
        tone: "ok",
        title: t.removed(site.name),
        action: {
          label: t.undo,
          run: () => void act("actions/sites/add", { name: site.name, url: site.url, expected_status: site.expected_status ?? [200] }, { success: t.form.added(site.name) }),
        },
      });
    }
  }

  function closeAdd() {
    setAdding(false);
    if (params.get("add")) router.replace("/monitors", { scroll: false });
  }

  const up = snapshot?.sites?.up ?? 0;
  const total = snapshot?.sites?.total ?? 0;
  const down = total - up;

  return (
    <>
      <PageHeader
        eyebrow={t.eyebrow}
        headline={sites ? t.headline(up, total) : strings.connection.connecting}
        tone={sites ? (down ? "bad" : total ? "ok" : undefined) : undefined}
        meta={down ? `${down} ${strings.status.down.toLowerCase()}` : undefined}
        actions={
          <button type="button" className="btn btn--primary" onClick={() => setAdding(true)}>
            <Plus size={16} aria-hidden="true" />
            {t.add}
          </button>
        }
      />
      {sites && sites.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={<Activity size={22} />}
            title={t.empty}
            action={
              <button type="button" className="btn btn--primary" onClick={() => setAdding(true)}>
                <Plus size={16} aria-hidden="true" />
                {t.add}
              </button>
            }
          >
            {t.emptyBody}
          </EmptyState>
        </div>
      ) : (
        <div className="split">
          <div className="stack">
            <div className="toolbar">
              <SearchInput value={query} onChange={setQuery} label={t.search} />
            </div>
            <Segmented<Filter>
              label="Filter monitors"
              value={filter}
              onChange={setFilter}
              options={[
                { value: "all", label: t.filterAll, count: total },
                { value: "down", label: t.filterDown, count: down },
                { value: "up", label: t.filterUp, count: up },
              ]}
            />
            <div className="card">
              {!sites ? (
                <div className="card__body">
                  <SkeletonRows rows={4} />
                </div>
              ) : filtered.length ? (
                <ul className="list" aria-label="Monitors">
                  {filtered.map((site) => (
                    <li key={site.name}>
                      <button type="button" className="row row--button" aria-current={current?.name === site.name ? "true" : undefined} onClick={() => select(site)}>
                        <div className="row__main">
                          <span className="row__title">{site.name}</span>
                          <span className="row__sub">{hostFromUrl(site.url)}</span>
                          <UptimeBars site={site} count={30} />
                        </div>
                        <StatusPill tone={site.up ? "ok" : "bad"}>{site.up ? strings.status.up : strings.status.down}</StatusPill>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState title={t.noMatch} />
              )}
            </div>
          </div>
          <div className="desktop-only">{current ? <MonitorDetail site={current} onRemove={remove} /> : <Card>{t.select}</Card>}</div>
        </div>
      )}

      <Dialog open={detailOpen && Boolean(current)} onClose={() => setDetailOpen(false)} title={current?.name ?? ""} variant="sheet" labelledBy="monitor-sheet-title">
        {current ? <MonitorDetail site={current} onRemove={remove} compact /> : null}
      </Dialog>

      <AddMonitorSheet open={adding} onClose={closeAdd} onAdded={(name) => setSelected(name)} />
    </>
  );
}

function MonitorDetail({ site, onRemove, compact }: { site: Site; onRemove: (site: Site) => void; compact?: boolean }) {
  const history = samples(site);
  const lastCheck = history.length ? history[history.length - 1].ts : null;
  const body = (
    <>
      <div className="cluster cluster--between">
        <div className="stack stack--sm">
          {compact ? null : <h2 className="card__title">{site.name}</h2>}
          <a className="link truncate" href={site.url} target="_blank" rel="noreferrer">
            {site.url}
          </a>
        </div>
        <StatusPill tone={site.up ? "ok" : "bad"}>{site.up ? strings.status.up : strings.status.down}</StatusPill>
      </div>
      <UptimeBars site={site} count={60} large />
      <p className="subtle">
        {t.lastChecks(history.length)}
        {lastCheck ? (
          <>
            {" "}
            · latest <TimeAgo value={lastCheck} />
          </>
        ) : null}
      </p>
      <div className="grid-tiles">
        <Stat label={t.uptime} value={percent(uptime(site))} />
        <Stat label={t.response} value={ms(site.latency_ms)} />
        <Stat label={t.average} value={ms(averageLatency(site))} />
        <Stat label={t.p95} value={ms(percentileLatency(site))} />
      </div>
      {!site.up ? (
        <dl className="kv">
          <dt>{t.statusCode}</dt>
          <dd>{site.status_code ?? "—"}</dd>
          {site.error ? (
            <>
              <dt>{t.lastError}</dt>
              <dd className="mono">{site.error}</dd>
            </>
          ) : null}
        </dl>
      ) : null}
      <div>
        <h3 className="label">{t.responseTime}</h3>
        <LatencyChart site={site} />
      </div>
      <div className="cluster">
        <a className="btn" href={site.url} target="_blank" rel="noreferrer">
          <ExternalLink size={15} aria-hidden="true" />
          {t.open}
        </a>
        <button type="button" className="btn btn--ghost" onClick={() => onRemove(site)}>
          <Trash2 size={15} aria-hidden="true" />
          {t.remove}
        </button>
      </div>
    </>
  );
  return compact ? <div className="stack">{body}</div> : <Card>{body}</Card>;
}

function AddMonitorSheet({ open, onClose, onAdded }: { open: boolean; onClose: () => void; onAdded: (name: string) => void }) {
  const { act } = useSheltie();
  const f = t.form;
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [expected, setExpected] = useState("200");
  const [keyword, setKeyword] = useState("");
  const [timeout, setTimeoutValue] = useState("10");
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setUrl("");
      setName("");
      setNameTouched(false);
      setExpected("200");
      setKeyword("");
      setTimeoutValue("10");
      setSubmitted(false);
    }
  }, [open]);

  const normalizedUrl = url.trim() && !/^https?:\/\//i.test(url.trim()) ? `https://${url.trim()}` : url.trim();
  const urlValid = isValidHttpUrl(normalizedUrl);
  const suggested = urlValid ? nameFromUrl(normalizedUrl) : "";
  const finalName = (nameTouched ? name : name || suggested).trim();
  const showUrlError = (submitted || url.length > 8) && !urlValid;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitted(true);
    if (!urlValid || !finalName) return;
    setBusy(true);
    const codes = expected
      .split(/[\s,]+/)
      .map((code) => Number(code))
      .filter((code) => Number.isInteger(code) && code >= 100 && code < 600);
    const result = await act(
      "actions/sites/add",
      { name: finalName, url: normalizedUrl, expected_status: codes.length ? codes : [200], keyword: keyword.trim() || undefined, timeout: Number(timeout) || 10 },
      { success: f.added(finalName) },
    );
    setBusy(false);
    if (result?.ok) {
      onAdded(finalName);
      onClose();
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={f.title}
      variant="sheet"
      labelledBy="add-monitor-title"
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            {f.cancel}
          </button>
          <button type="submit" form="add-monitor-form" className="btn btn--primary" disabled={busy}>
            {f.submit}
          </button>
        </>
      }
    >
      <form id="add-monitor-form" className="stack" onSubmit={submit} noValidate>
        <div className="field">
          <label className="label" htmlFor="monitor-url">
            {f.url}
          </label>
          <input
            id="monitor-url"
            className="input"
            type="url"
            inputMode="url"
            autoComplete="url"
            placeholder="https://"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            aria-invalid={showUrlError}
            aria-describedby="monitor-url-hint"
            autoFocus
            required
          />
          <span id="monitor-url-hint" className={`hint ${showUrlError ? "hint--error" : ""}`}>
            {showUrlError ? f.urlError : f.urlHint}
          </span>
        </div>
        <div className="field">
          <label className="label" htmlFor="monitor-name">
            {f.name}
          </label>
          <input
            id="monitor-name"
            className="input"
            value={nameTouched ? name : name || suggested}
            placeholder={suggested || "Blog"}
            onChange={(event) => {
              setNameTouched(true);
              setName(event.target.value);
            }}
            aria-describedby="monitor-name-hint"
            aria-invalid={submitted && !finalName}
          />
          <span id="monitor-name-hint" className="hint">
            {f.nameHint}
          </span>
        </div>
        <details className="advanced">
          <summary>{f.advanced}</summary>
          <div className="stack">
            <div className="field">
              <label className="label" htmlFor="monitor-expected">
                {f.expected}
              </label>
              <input id="monitor-expected" className="input" value={expected} onChange={(event) => setExpected(event.target.value)} aria-describedby="monitor-expected-hint" />
              <span id="monitor-expected-hint" className="hint">
                {f.expectedHint}
              </span>
            </div>
            <div className="field">
              <label className="label" htmlFor="monitor-keyword">
                {f.keyword}
              </label>
              <input id="monitor-keyword" className="input" value={keyword} onChange={(event) => setKeyword(event.target.value)} aria-describedby="monitor-keyword-hint" />
              <span id="monitor-keyword-hint" className="hint">
                {f.keywordHint}
              </span>
            </div>
            <div className="field">
              <label className="label" htmlFor="monitor-timeout">
                {f.timeout}
              </label>
              <input id="monitor-timeout" className="input" type="number" min={1} max={60} value={timeout} onChange={(event) => setTimeoutValue(event.target.value)} />
            </div>
          </div>
        </details>
      </form>
    </Dialog>
  );
}
