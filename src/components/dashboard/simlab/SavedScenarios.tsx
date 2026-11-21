"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { call, post } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel, dt } from "../ui";
import { field } from "../analysis";
import { ScoreGrid, type SimResult } from "./SportsSimulator";

interface Row { source: "run" | "scenario"; id: string; domain: string; kind: string; title: string; scenario_key: string; version: number; engine: string | null; created_at: string; created_by_name: string; baseline_percent?: number[] | null; scenarios?: number | null; scheduled?: boolean | null; gross_profit?: number | null }
const signed = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}`;
const DOMAIN_LABEL: Record<string, string> = { sports: "Sports", business: "Business", politics: "Politics", markets: "Markets" };
const DOMAIN_TONE: Record<string, "cyan" | "violet" | "green" | "amber"> = { sports: "cyan", business: "violet", politics: "amber", markets: "green" };

function describe(r: Row): string {
  if (r.source === "run" && r.domain === "business") return `base-case gross profit ${r.gross_profit == null ? "n/a" : Math.round(r.gross_profit).toLocaleString("en-US")} (hypothetical)`;
  if (r.source === "run") return `${r.scenarios ?? 0} scenario${r.scenarios === 1 ? "" : "s"} · baseline ${r.baseline_percent ? r.baseline_percent.map((p) => p.toFixed(0)).join(" / ") : "n/a"} % · ${r.scheduled ? "scheduled fixture" : "hypothetical matchup"}`;
  return r.kind === "payoff game" ? "payoff game" : r.kind;
}

/** Saved simulations and scenarios from every domain, grouped by scenario with their version chain. Sports and pricing runs, and political, financial and strategy scenarios. */
export function SavedTab({ tick, onOpen }: { tick: number; onOpen: (id: string, source: "run" | "scenario") => void }) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [n, setN] = useState(0);
  const [domain, setDomain] = useState("");
  useEffect(() => {
    let live = true;
    call<{ runs: Row[] }>(`simlab/saved?limit=200${domain ? `&domain=${domain}` : ""}`).then((d) => live && (setRows(d.runs), setErr(null)), (e) => live && setErr(e instanceof Error ? e.message : "Could not load saved scenarios."));
    return () => { live = false; };
  }, [tick, n, domain]);
  async function remove(r: Row) {
    try { await call(r.source === "run" ? `simlab/runs/${r.id}` : `simlab/scenarios/${r.id}`, { method: "DELETE" }); setN((x) => x + 1); } catch (e) { setErr(e instanceof Error ? e.message : "Could not delete that."); }
  }
  if (err && !rows) return <ErrorPanel message={err} />;
  if (!rows) return <p className="text-sm text-muted" aria-busy="true">Loading saved scenarios…</p>;
  const groups = new Map<string, Row[]>();
  for (const r of rows) groups.set(r.scenario_key, [...(groups.get(r.scenario_key) ?? []), r]);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <div><label htmlFor="sv-domain" className="mb-1 block text-xs text-muted">Show</label>
          <select id="sv-domain" value={domain} onChange={(e) => setDomain(e.target.value)} className={field}><option value="">All domains</option>{Object.entries(DOMAIN_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
        <p className="text-xs text-muted">Sports and pricing runs are stored by SimLab; political, financial and strategy scenarios are stored with the workspace library. All carry a version and where available their provenance.</p>
      </div>
      {err && <p role="alert" className="text-sm text-red-300">{err}</p>}
      {rows.length === 0 ? <Empty>Nothing is saved{domain ? ` for ${DOMAIN_LABEL[domain]}` : ""} yet. Run a simulation, or save a scenario from Politics, Markets or Strategy: it appears here with its version and provenance.</Empty> : (
        <ul className="space-y-3" aria-label="Saved scenarios">
          {[...groups.values()].map((g) => {
            const latest = g.reduce((a, b) => (b.version > a.version ? b : a));
            return (
              <li key={latest.scenario_key} className="glass rounded-2xl p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold">{latest.title} <Badge tone={DOMAIN_TONE[latest.domain] ?? "cyan"}>{DOMAIN_LABEL[latest.domain] ?? latest.domain}</Badge></p>
                  <span className="text-xs text-muted">{g.length} version{g.length === 1 ? "" : "s"} · latest {dt(latest.created_at)}</span>
                </div>
                <ul className="mt-2 divide-y divide-line text-sm">
                  {[...g].sort((a, b) => b.version - a.version).map((r) => (
                    <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                      <span><span className="font-mono text-xs">v{r.version}</span> · {describe(r)} · {r.created_by_name}{r.engine && <> · <span className="font-mono text-xs text-muted">{r.engine}</span></>}</span>
                      <span className="flex gap-3"><button type="button" onClick={() => onOpen(r.id, r.source)} className="text-xs text-violet underline">Open</button>
                        <button type="button" onClick={() => remove(r)} aria-label={`Delete ${r.title} version ${r.version}`} className="text-muted hover:text-red-300"><Trash2 className="h-4 w-4" aria-hidden="true" /></button></span>
                    </li>
                  ))}
                </ul>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

const flatten = (v: unknown, prefix = "", out: [string, unknown][] = []): [string, unknown][] => {
  if (Array.isArray(v)) v.forEach((x, i) => flatten(x, `${prefix}[${i}]`, out));
  else if (v && typeof v === "object") Object.entries(v).forEach(([k, x]) => flatten(x, prefix ? `${prefix}.${k}` : k, out));
  else out.push([prefix, v]);
  return out;
};
const show = (v: unknown) => (typeof v === "number" ? (Number.isInteger(v) ? String(v) : v.toFixed(4)) : v === null || v === undefined ? "n/a" : String(v));

interface ScenarioFull { id: string; domain: string; kind: string; title: string; version: number; created_at: string; created_by_name: string; notes: string | null; summary: Record<string, unknown> | null; provenance: { engine: string; engine_version: string; random_seed: number | null; generated_at: string; input_data: string } | null; notice: string; module_href: string }

/** A political, financial or strategy scenario opened from the saved list: its stored summary, provenance, notice and where to continue working on it. */
export function ScenarioViewer({ id }: { id: string }) {
  const [s, setS] = useState<ScenarioFull | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    call<ScenarioFull>(`simlab/scenarios/${id}`).then((d) => live && (setS(d), setErr(null)), (e) => live && setErr(e instanceof Error ? e.message : "Could not open that scenario."));
    return () => { live = false; };
  }, [id]);
  if (err) return <ErrorPanel message={err} />;
  if (!s) return <p className="text-sm text-muted" aria-busy="true">Opening…</p>;
  const rows = s.summary ? flatten(s.summary) : [];
  return (
    <Panel title={`${s.title} · version ${s.version}`} badge={<Badge tone="muted">{dt(s.created_at)} · {s.created_by_name}</Badge>}>
      <p className="text-xs text-muted">{s.notice}</p>
      {s.notes && <p className="mt-2 text-sm">Notes: {s.notes}</p>}
      {rows.length === 0 ? <p className="mt-3 text-sm text-muted">This kind of scenario keeps its full analysis in its own workspace. <Link href={s.module_href} className="text-violet underline">Open it there</Link>.</p> : (
        <div className="mt-3 max-h-80 overflow-auto"><table className="w-full text-sm"><caption className="sr-only">Stored summary of the scenario</caption>
          <tbody className="font-mono text-xs">{rows.map(([k, v]) => <tr key={k} className="border-t border-line"><th scope="row" className="py-1 pr-3 text-left font-normal text-muted">{k}</th><td>{show(v)}</td></tr>)}</tbody></table></div>
      )}
      <p className="mt-3 text-xs text-muted">{s.provenance ? `Provenance: ${s.provenance.engine}@${s.provenance.engine_version}, ${dt(s.provenance.generated_at)}, random seed ${s.provenance.random_seed === null ? "none" : s.provenance.random_seed}. Inputs: ${s.provenance.input_data}.` : "This scenario was saved before provenance was recorded."}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
        <Link href={s.module_href} className="rounded-lg border border-line px-3 py-1.5 font-semibold hover:bg-white/5">Open in {s.domain === "markets" ? "Markets" : s.domain === "politics" ? "Politics" : "Strategy"}</Link>
        {s.summary && (["csv", "json"] as const).map((f) => <a key={f} href={`/app-api/simlab/scenarios/${s.id}/export?format=${f}`} download className="rounded-lg border border-line px-3 py-1.5 font-semibold hover:bg-white/5">{f.toUpperCase()}</a>)}
      </div>
    </Panel>
  );
}

/** Opens one saved run in full. */
export function RunViewer({ id }: { id: string }) {
  const [r, setR] = useState<(SimResult & { versions: { id: string; version: number }[]; created_by_name: string }) | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    call<SimResult & { versions: { id: string; version: number }[]; created_by_name: string }>(`simlab/runs/${id}`).then((d) => live && (setR(d), setErr(null)), (e) => live && setErr(e instanceof Error ? e.message : "Could not open that run."));
    return () => { live = false; };
  }, [id]);
  if (err) return <ErrorPanel message={err} />;
  if (!r) return <p className="text-sm text-muted" aria-busy="true">Opening…</p>;
  const biz = r as unknown as { domain?: string; base?: { units: number; revenue: number; gross_profit: number; price: number }; scenarios: { name: string; price: number; units: number; revenue: number; gross_profit: number }[]; label: string; validation_status: string };
  if (biz.domain === "business" && biz.base) {
    return (
      <Panel title={`${r.title} · version ${r.version}`} badge={<Badge tone="amber">Hypothetical</Badge>}>
        <p className="text-xs text-muted">{biz.label}</p>
        <div className="mt-3 overflow-x-auto"><table className="w-full text-sm"><caption className="sr-only">Saved business simulation results</caption>
          <thead><tr className="text-left text-[11px] text-muted">{["", "Price", "Units", "Revenue", "Gross profit"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
          <tbody className="font-mono">{[{ name: "Base case", ...biz.base }, ...biz.scenarios].map((x) => <tr key={x.name} className="border-t border-line"><th scope="row" className="py-1.5 pr-3 text-left font-sans font-medium">{x.name}</th><td className="pr-3">{x.price}</td><td className="pr-3">{Math.round(x.units).toLocaleString("en-US")}</td><td className="pr-3">{Math.round(x.revenue).toLocaleString("en-US")}</td><td>{Math.round(x.gross_profit).toLocaleString("en-US")}</td></tr>)}</tbody></table></div>
        <p className="mt-2 text-xs text-muted">{biz.validation_status}</p>
        <div className="mt-3 flex flex-wrap gap-2 text-sm">{(["csv", "json"] as const).map((f) => <a key={f} href={`/app-api/simlab/runs/${r.id}/export?format=${f}`} download className="rounded-lg border border-line px-3 py-1.5 font-semibold hover:bg-white/5">{f.toUpperCase()}</a>)}</div>
      </Panel>
    );
  }
  return (
    <Panel title={`${r.title} · version ${r.version}`} badge={<Badge tone="muted">{dt(r.created_at)} · {r.created_by_name}</Badge>}>
      <p className="text-xs text-muted">{r.matchup.label} {r.label}</p>
      <div className="mt-3 overflow-x-auto"><table className="w-full text-sm"><caption className="sr-only">Saved results</caption>
        <thead><tr className="text-left text-[11px] text-muted">{["", `${r.matchup.home} win`, "Draw", `${r.matchup.away} win`, "xG home", "xG away"].map((h, i) => <th key={i} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
        <tbody className="font-mono">{[r.baseline, ...r.scenarios].map((s) => <tr key={s.name} className="border-t border-line"><th scope="row" className="py-1.5 pr-3 text-left font-sans font-medium">{s.name}</th>{s.percent.map((p, k) => <td key={k} className="pr-3">{p.toFixed(1)}%</td>)}<td className="pr-3">{s.expected_goals[0].toFixed(2)}</td><td>{s.expected_goals[1].toFixed(2)}</td></tr>)}</tbody></table></div>
      <div className="mt-3"><ScoreGrid s={r.baseline} home={r.matchup.home} away={r.matchup.away} /></div>
      <p className="mt-2 text-xs text-muted">{r.validation_status}</p>
      <div className="mt-3 flex flex-wrap gap-2 text-sm">{(["csv", "html", "json"] as const).map((f) => <a key={f} href={`/app-api/simlab/runs/${r.id}/export?format=${f}`} download className="rounded-lg border border-line px-3 py-1.5 font-semibold hover:bg-white/5">{f === "html" ? "Printable page (save as PDF)" : f.toUpperCase()}</a>)}</div>
    </Panel>
  );
}

/** Side-by-side comparison of two saved runs (for example two versions of one scenario, or two fixtures). */
export function CompareTab({ tick }: { tick: number }) {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [ra, setRa] = useState<SimResult | null>(null);
  const [rb, setRb] = useState<SimResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    call<{ runs: Row[] }>("simlab/runs?domain=sports&limit=100").then((d) => live && setRows(d.runs), (e) => live && setErr(e instanceof Error ? e.message : "Could not load saved scenarios."));
    return () => { live = false; };
  }, [tick]);
  const load = useCallback(async (id: string, set: (r: SimResult | null) => void) => {
    if (!id) return set(null);
    try { set(await call<SimResult>(`simlab/runs/${id}`)); setErr(null); } catch (e) { setErr(e instanceof Error ? e.message : "Could not open that run."); }
  }, []);
  if (err && !rows) return <ErrorPanel message={err} />;
  if (!rows) return <p className="text-sm text-muted" aria-busy="true">Loading…</p>;
  if (rows.length < 2) return <div className="space-y-4"><Empty>Comparing sports simulations needs at least two saved runs. Run another scenario, or save a new version of one you already have.</Empty><CompareScenarios tick={tick} /></div>;
  const label = (r: Row) => `${r.title} v${r.version} (${new Date(r.created_at).toISOString().slice(0, 16).replace("T", " ")})`;
  const lines = (r: SimResult | null) => (r ? [r.baseline, ...r.scenarios].map((s) => ({ name: s.name, percent: s.percent, xg: s.expected_goals })) : []);
  return (
    <div className="space-y-4">
      <Panel title="Compare saved simulations" badge={<Badge tone="muted">Sports</Badge>}>
        <div className="flex flex-wrap gap-3">
          {([["Simulation A", a, setA, setRa], ["Simulation B", b, setB, setRb]] as const).map(([lab, val, setV, setR]) => (
            <div key={lab}><label htmlFor={`cmp-${lab}`} className="mb-1 block text-xs text-muted">{lab}</label>
              <select id={`cmp-${lab}`} value={val} onChange={(e) => { setV(e.target.value); load(e.target.value, setR); }} className={field}><option value="">Choose…</option>{rows.map((r) => <option key={r.id} value={r.id}>{label(r)}</option>)}</select></div>
          ))}
        </div>
        {err && <p role="alert" className="mt-3 text-sm text-red-300">{err}</p>}
      </Panel>
      {ra && rb && (
        <Panel title="Side by side">
          <div className="overflow-x-auto"><table className="w-full text-sm"><caption className="sr-only">Home, draw and away percentages for each saved simulation</caption>
            <thead><tr className="text-left text-[11px] text-muted">{["Simulation", "Scenario", "Home", "Draw", "Away", "xG home", "xG away"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
            <tbody className="font-mono">{[[`A: ${ra.title} v${ra.version}`, lines(ra)], [`B: ${rb.title} v${rb.version}`, lines(rb)]].flatMap(([t, ls]) => (ls as ReturnType<typeof lines>).map((l, i) => (
              <tr key={`${t}${l.name}`} className="border-t border-line"><th scope="row" className="py-1.5 pr-3 text-left font-sans font-medium">{i === 0 ? (t as string) : ""}</th><td className="pr-3 font-sans">{l.name}</td>{l.percent.map((p, k) => <td key={k} className="pr-3">{p.toFixed(1)}%</td>)}<td className="pr-3">{l.xg[0].toFixed(2)}</td><td>{l.xg[1].toFixed(2)}</td></tr>
            )))}</tbody></table></div>
          <p className="mt-3 font-mono text-xs">Baseline difference (B minus A): home {signed(rb.baseline.percent[0] - ra.baseline.percent[0])} · draw {signed(rb.baseline.percent[1] - ra.baseline.percent[1])} · away {signed(rb.baseline.percent[2] - ra.baseline.percent[2])} percentage points</p>
          <p className="mt-2 text-xs text-muted">A baseline can differ between runs because the data, the cutoff or the club pairing differ: check the provenance of each (data through {ra.provenance.data_through} for A, {rb.provenance.data_through} for B). Scenario rows are hypothetical.</p>
        </Panel>
      )}
      <CompareScenarios tick={tick} />
    </div>
  );
}


/** Compare 2 to 4 saved scenarios of the same kind from Politics or Markets, side by side, using each module's own comparison. */
export function CompareScenarios({ tick }: { tick: number }) {
  const [domain, setDomain] = useState<"politics" | "markets">("politics");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [kind, setKind] = useState("");
  const [sel, setSel] = useState<string[]>([]);
  const [out, setOut] = useState<{ kind: string; notice: string; scenarios: { id: string; title: string; summary: Record<string, unknown> }[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    call<{ runs: Row[] }>(`simlab/saved?domain=${domain}&limit=200`).then((d) => live && (setRows(d.runs.filter((r) => r.source === "scenario")), setErr(null)), (e) => live && setErr(e instanceof Error ? e.message : "Could not load saved scenarios."));
    return () => { live = false; };
  }, [domain, tick]);
  const kinds = [...new Set((rows ?? []).map((r) => r.kind))];
  const shown = (rows ?? []).filter((r) => !kind || r.kind === kind);
  async function compare() {
    setErr(null);
    try { setOut(await post(`${domain === "politics" ? "politics" : "finance"}/compare`, { ids: sel })); } catch (e) { setOut(null); setErr(e instanceof Error ? e.message : "Could not compare those."); }
  }
  const flat = out ? out.scenarios.map((s) => Object.fromEntries(flatten(s.summary).filter(([, v]) => typeof v !== "object"))) : [];
  const keys = [...new Set(flat.flatMap((f) => Object.keys(f)))];
  return (
    <Panel title="Compare political or financial scenarios" badge={<Badge tone="muted">Same type, 2 to 4</Badge>}>
      <div className="flex flex-wrap items-end gap-3">
        <div><label htmlFor="cs-domain" className="mb-1 block text-xs text-muted">Domain</label>
          <select id="cs-domain" value={domain} onChange={(e) => { setDomain(e.target.value as "politics" | "markets"); setSel([]); setOut(null); setKind(""); }} className={field}><option value="politics">Politics</option><option value="markets">Markets</option></select></div>
        <div><label htmlFor="cs-kind" className="mb-1 block text-xs text-muted">Type</label>
          <select id="cs-kind" value={kind} onChange={(e) => { setKind(e.target.value); setSel([]); setOut(null); }} className={field}><option value="">All types</option>{kinds.map((k) => <option key={k} value={k}>{k}</option>)}</select></div>
      </div>
      {!rows ? <p className="mt-3 text-sm text-muted" aria-busy="true">Loading…</p> : shown.length < 2 ? <p className="mt-3 text-sm text-muted">Comparing needs at least two saved {DOMAIN_LABEL[domain].toLowerCase()} scenarios of the same type. Save scenarios from the {DOMAIN_LABEL[domain]} workspace.</p> : (
        <fieldset className="mt-3"><legend className="mb-1 text-xs text-muted">Choose 2 to 4 of the same type</legend>
          <ul className="space-y-1">{shown.map((r) => (
            <li key={r.id}><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={sel.includes(r.id)} disabled={!sel.includes(r.id) && sel.length >= 4} onChange={(e) => { setOut(null); setSel((x) => (e.target.checked ? [...x, r.id] : x.filter((i) => i !== r.id))); }} />
              {r.title} <span className="font-mono text-xs text-muted">v{r.version} · {r.kind}</span></label></li>
          ))}</ul>
          <button type="button" disabled={sel.length < 2} onClick={compare} className="mt-3 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Compare {sel.length || ""} selected</button>
        </fieldset>
      )}
      {err && <p role="alert" className="mt-3 text-sm text-red-300">{err}</p>}
      {out && (
        <div className="mt-4 overflow-x-auto"><table className="w-full text-xs"><caption className="sr-only">Stored summaries of the compared scenarios</caption>
          <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="pr-3 font-normal">Field</th>{out.scenarios.map((s) => <th key={s.id} scope="col" className="pr-3 font-normal">{s.title}</th>)}</tr></thead>
          <tbody className="font-mono">{keys.map((k) => <tr key={k} className="border-t border-line"><th scope="row" className="py-1 pr-3 text-left font-normal text-muted">{k}</th>{flat.map((f, i) => <td key={i} className="pr-3">{k in f ? show(f[k]) : "—"}</td>)}</tr>)}</tbody></table>
          <p className="mt-2 text-xs text-muted">{out.notice}</p></div>
      )}
    </Panel>
  );
}
