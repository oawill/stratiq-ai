"use client";

import { useEffect, useState } from "react";
import { brand } from "@/lib/brand";
import { Loader2, Trash2 } from "lucide-react";
import { call, post } from "@/lib/client";
import type { FinCompare, FinKind, FinScenarioFull, FinScenarioRow } from "@/lib/types";
import { Badge, Empty, ErrorPanel, Panel, dt } from "../ui";
import { CompareExplain, ExplainToggle } from "../assistant/AssistantPanel";
import { useAdvanced } from "../useAdvanced";
import { pc } from "../analysis";
import { HistoricalTool, defaultHist, type HistDraft } from "./HistoricalTool";
import { PortfolioMC, defaultMc, defaultPortfolio, type McDraft, type PortfolioDraft } from "./PortfolioMC";
import { StressTool, stressFromPortfolio, type StressDraft } from "./StressTool";

type Tab = "mc" | "stress" | "historical" | "saved";
const TABS: [Tab, string][] = [["mc", "Portfolio & Monte Carlo"], ["stress", "Stress tests"], ["historical", "Historical returns"], ["saved", "Saved & compare"]];
const KIND_LABEL: Record<FinKind, string> = { montecarlo: "Monte Carlo", stress: "Stress", historical: "Historical" };
const money = (x: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(x);
const pct = (x: number) => String(+(x * 100).toFixed(6));

/* eslint-disable @typescript-eslint/no-explicit-any */
function mcFrom(i: any): { pd: PortfolioDraft; mc: McDraft } {
  const base = defaultMc();
  const near = (v: number) => (["1000", "5000", "10000", "20000"].includes(String(v)) ? String(v) : "5000");
  return {
    pd: { assets: i.assets.map((a: any) => ({ name: a.name, weight: pct(a.weight), mu: pct(a.mu), sigma: pct(a.sigma) })), corr: i.correlation.map((r: number[]) => r.map(String)), initial: String(i.initial_value) },
    mc: { ...base, horizon: String(i.horizon_years), steps: String(i.steps_per_year) as McDraft["steps"], iterations: near(i.iterations), rebalance: i.rebalance, tails: i.tails, df: String(i.df),
      seed: i.seed == null ? "" : String(i.seed), conf: { c90: i.confidences.includes(0.9), c95: i.confidences.includes(0.95), c99: i.confidences.includes(0.99) },
      lossThreshold: i.loss_threshold == null ? "" : pct(i.loss_threshold), ddThreshold: i.drawdown_threshold == null ? "" : pct(i.drawdown_threshold) },
  };
}
function stressFrom(i: any): StressDraft {
  return {
    assets: i.assets.map((a: any) => ({ name: a.name, weight: pct(a.weight) })), initial: String(i.initial_value),
    scenarios: i.scenarios.map((s: any) => ({ name: s.name, shocks: i.assets.map((a: any) => (s.shocks[a.name] === undefined ? "" : pct(s.shocks[a.name]))) })),
    reverse: i.reverse_target_loss == null ? "" : pct(i.reverse_target_loss),
  };
}
function histFrom(i: any): HistDraft {
  const names = Object.keys(i.series);
  const n = i.series[names[0]].length;
  const rows = [names.join(",")];
  for (let t = 0; t < n; t++) rows.push(names.map((nm) => +(i.series[nm][t] * 100).toFixed(6)).join(","));
  return { text: rows.join("\n"), unit: "percent", ppy: String(i.periods_per_year), weights: Object.fromEntries(names.map((nm) => [nm, pct(i.weights[nm])])), conf: { c95: i.confidences.includes(0.95), c99: i.confidences.includes(0.99) } };
}

function CompareTable({ data }: { data: FinCompare }) {
  const th = "px-3 py-1 text-left text-[11px] font-normal text-muted";
  const td = "border-t border-line px-3 py-1.5 font-mono text-sm";
  const lbl = `${td} font-sans text-muted`;
  const heads = data.scenarios.map((s) => <th key={s.id} scope="col" className={th}>{s.title}</th>);
  const row = (label: string, f: (s: any) => React.ReactNode) => <tr key={label}><th scope="row" className={lbl}>{label}</th>{data.scenarios.map((s) => <td key={s.id} className={td}>{f(s.summary)}</td>)}</tr>;
  if (data.kind === "montecarlo") {
    const confs = [...new Set(data.scenarios.flatMap((s) => s.summary.risk.map((r: any) => r.confidence as number)))].sort();
    return (
      <div className="overflow-x-auto"><table className="w-full min-w-[520px]"><caption className="sr-only">Monte Carlo scenario comparison</caption><thead><tr><th scope="col" className={th}>&nbsp;</th>{heads}</tr></thead>
        <tbody>
          {row("Assets", (s) => s.assets.map((a: any) => `${a.name} ${pc(a.weight, 0)}`).join(", "))}
          {row("Horizon", (s) => `${s.horizon_years.toFixed(1)} years`)}
          {row("Assumed return / volatility", (s) => `${pc(s.expected_return)} / ${pc(s.volatility)}`)}
          {row("Median final value", (s) => money(s.median_value))}
          {row("5th – 95th percentile", (s) => `${money(s.p5_value)} – ${money(s.p95_value)}`)}
          {row("Chance of ending lower", (s) => pc(s.p_loss))}
          {row("Average worst drawdown", (s) => pc(s.max_drawdown_mean))}
          {confs.map((c) => row(`VaR / ES at ${pc(c, 0)}`, (s) => { const r = s.risk.find((x: any) => x.confidence === c); return r ? `${pc(r.var)} / ${pc(r.es)}` : "—"; }))}
          {row("Model", (s) => `${s.model.tails}${s.model.df ? ` (df ${s.model.df})` : ""}, ${s.model.rebalance === "none" ? "buy & hold" : "rebalanced"}, seed ${s.seed}`)}
        </tbody></table>
        {new Set(data.scenarios.map((s) => s.summary.seed)).size > 1 && <p className="mt-2 text-[11px] text-amber-200">These runs used different random seeds, so part of each difference is simulation noise. Save both with the same seed for a like-for-like comparison.</p>}
      </div>
    );
  }
  if (data.kind === "stress") {
    const names = [...new Set(data.scenarios.flatMap((s) => s.summary.scenarios.map((x: any) => x.name as string)))];
    return (
      <div className="overflow-x-auto"><table className="w-full min-w-[520px]"><caption className="sr-only">Stress scenario comparison</caption><thead><tr><th scope="col" className={th}>Shock scenario</th>{heads}</tr></thead>
        <tbody>
          {names.map((n) => row(n, (s) => { const x = s.scenarios.find((y: any) => y.name === n); return x ? `${x.portfolio_return >= 0 ? "+" : ""}${pc(x.portfolio_return)} (${x.pnl >= 0 ? "+" : "−"}${money(Math.abs(x.pnl))})` : "—"; }))}
          {row("Worst scenario", (s) => s.worst)}
        </tbody></table></div>
    );
  }
  const confs = [...new Set(data.scenarios.flatMap((s) => s.summary.risk.map((r: any) => r.confidence as number)))].sort();
  return (
    <div className="overflow-x-auto"><table className="w-full min-w-[520px]"><caption className="sr-only">Historical scenario comparison</caption><thead><tr><th scope="col" className={th}>&nbsp;</th>{heads}</tr></thead>
      <tbody>
        {row("Series", (s) => s.assets.map((a: string, i: number) => `${a} ${pc(s.weights[i], 0)}`).join(", "))}
        {row("Periods", (s) => s.periods)}{row("CAGR", (s) => pc(s.cagr))}{row("Annualised volatility", (s) => pc(s.annualised_vol))}{row("Max drawdown", (s) => pc(s.max_drawdown))}
        {confs.map((c) => row(`Historical VaR / ES at ${pc(c, 0)}`, (s) => { const r = s.risk.find((x: any) => x.confidence === c); return r ? `${pc(r.var, 2)} / ${pc(r.es, 2)}` : "—"; }))}
      </tbody></table></div>
  );
}

function SavedPanel({ onOpen }: { onOpen: (s: FinScenarioFull) => void }) {
  const [list, setList] = useState<FinScenarioRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<string[]>([]);
  const [cmp, setCmp] = useState<FinCompare | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    call<{ scenarios: FinScenarioRow[] }>("finance/scenarios").then((d) => live && setList(d.scenarios)).catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, [tick]);
  const kindOf = (id: string) => list?.find((s) => s.id === id)?.kind;
  const toggle = (id: string) => { setCmp(null); setErr(null); setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length >= 4 ? s : s.length && kindOf(s[0]) !== kindOf(id) ? [id] : [...s, id])); };
  async function open(id: string) { setBusy(id); setErr(null); try { onOpen(await call<FinScenarioFull>(`finance/scenarios/${id}`)); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); } finally { setBusy(null); } }
  async function remove(s: FinScenarioRow) {
    if (!window.confirm(`Delete "${s.title}"? This cannot be undone.`)) return;
    setBusy(s.id);
    try { await call(`finance/scenarios/${s.id}`, { method: "DELETE" }); setSel((x) => x.filter((i) => i !== s.id)); setCmp(null); setTick((n) => n + 1); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); } finally { setBusy(null); }
  }
  async function compare() { setBusy("cmp"); setErr(null); try { setCmp(await post<FinCompare>("finance/compare", { ids: sel })); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); } finally { setBusy(null); } }
  return (
    <div className="space-y-4">
      <Panel title="Saved financial scenarios" badge={<span className="text-xs text-muted">Compare 2–4 of the same type</span>}>
        {err && <div className="mb-3"><ErrorPanel message={err} /></div>}
        {list === null && !err ? <p className="text-sm text-muted" aria-busy="true">Loading…</p> : list && list.length === 0 ? <Empty>No saved scenarios yet. Build one in a tool and press Save.</Empty> : (
          <ul className="divide-y divide-line">{list?.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-3 py-2.5">
              <input type="checkbox" checked={sel.includes(s.id)} onChange={() => toggle(s.id)} aria-label={`Select ${s.title} for comparison`} className="h-4 w-4 accent-[#8055f6]" />
              <div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold">{s.title}</div><div className="text-[11px] text-muted">{s.created_by_name} · {dt(s.created_at)}</div></div>
              <Badge tone="violet">{KIND_LABEL[s.kind]}</Badge>
              <button type="button" onClick={() => open(s.id)} disabled={busy === s.id} className="rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:border-violet/60 disabled:opacity-60">Open</button>
              <button type="button" onClick={() => remove(s)} disabled={busy === s.id} aria-label={`Delete ${s.title}`} className="rounded-lg p-1.5 text-muted hover:text-red-300 disabled:opacity-60"><Trash2 className="h-4 w-4" /></button>
            <ExplainToggle type="scenario" id={s.id} title={s.title} />
              </li>))}</ul>)}
        <div className="mt-3"><button type="button" onClick={compare} disabled={sel.length < 2 || busy === "cmp"} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy === "cmp" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Compare selected ({sel.length})</button></div>
        {sel.length >= 2 && <CompareExplain key={sel.join(",")} type="scenario" ids={sel} />}
      </Panel>
      {cmp && <Panel title={`${KIND_LABEL[cmp.kind]} scenario comparison`}><CompareTable data={cmp} /><p className="mt-2 text-[11px] text-muted">Educational scenario analysis. Not investment advice, not a forecast, and not connected to any broker.</p></Panel>}
    </div>
  );
}

export function FinanceWorkspace() {
  const [tab, setTab] = useState<Tab>("mc");
  const [adv, setAdv] = useAdvanced();
  const [pd, setPd] = useState<PortfolioDraft>(defaultPortfolio);
  const [mc, setMc] = useState<McDraft>(defaultMc);
  const [stress, setStress] = useState<StressDraft>(() => stressFromPortfolio(defaultPortfolio()));
  const [hist, setHist] = useState<HistDraft>(defaultHist);
  const [version, setVersion] = useState(0);
  const bump = () => setVersion((v) => v + 1);

  function open(s: FinScenarioFull) {
    if (s.kind === "montecarlo") { const r = mcFrom(s.inputs); setPd(r.pd); setMc(r.mc); setTab("mc"); }
    else if (s.kind === "stress") { setStress(stressFrom(s.inputs)); setTab("stress"); }
    else { setHist(histFrom(s.inputs)); setTab("historical"); }
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div role="tablist" aria-label={`${brand.products.markets.name} tools`} className="inline-flex max-w-full overflow-x-auto rounded-xl border border-line bg-bg/60 p-1"
          onKeyDown={(e) => { const i = TABS.findIndex((t) => t[0] === tab); if (e.key === "ArrowRight") setTab(TABS[(i + 1) % TABS.length][0]); if (e.key === "ArrowLeft") setTab(TABS[(i + TABS.length - 1) % TABS.length][0]); }}>
          {TABS.map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} tabIndex={tab === id ? 0 : -1} onClick={() => setTab(id)} className={`whitespace-nowrap rounded-lg px-4 py-2 text-sm font-semibold ${tab === id ? "bg-primary text-white" : "text-muted hover:text-ink"}`}>{label}</button>)}
        </div>
        <Badge tone="amber">Educational · not investment advice</Badge>
        <label className="ml-auto flex cursor-pointer items-center gap-2 text-sm"><input type="checkbox" checked={adv} onChange={(e) => setAdv(e.target.checked)} className="h-4 w-4 accent-[#8055f6]" /> Advanced analytics</label>
      </div>
      <div role="tabpanel">
        {tab === "mc" && <PortfolioMC pd={pd} setPd={setPd} mc={mc} setMc={setMc} adv={adv} onSaved={bump} />}
        {tab === "stress" && <StressTool d={stress} set={setStress} pd={pd} adv={adv} onSaved={bump} />}
        {tab === "historical" && <HistoricalTool d={hist} set={setHist} adv={adv} onSaved={bump} />}
        {tab === "saved" && <SavedPanel key={version} onOpen={open} />}
      </div>
    </div>
  );
}
