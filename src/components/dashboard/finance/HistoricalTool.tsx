"use client";

import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Loader2 } from "lucide-react";
import { call } from "@/lib/client";
import type { FinDataSources, FinHistorical } from "@/lib/types";
import { Badge, ErrorPanel, Panel } from "../ui";
import { ScenarioSaveBar, field, num, pc, useAnalysis } from "../analysis";

export interface HistDraft {
  text: string;
  unit: "percent" | "decimal";
  ppy: string;
  weights: Record<string, string>; // percent, by series name
  conf: { c95: boolean; c99: boolean };
}
export const defaultHist = (): HistDraft => ({ text: "", unit: "percent", ppy: "12", weights: {}, conf: { c95: true, c99: false } });

/** A synthetic series generated in the browser for trying the tool. It is random numbers, not market data. */
export function syntheticCsv(): string {
  let a = 0x9e3779b9;
  const rnd = () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const gauss = () => Math.sqrt(-2 * Math.log(1 - rnd())) * Math.cos(2 * Math.PI * rnd());
  const rows = ["SynthEquity,SynthBonds,SynthBlend"];
  for (let i = 0; i < 120; i++) {
    const e = 0.6 + 4.5 * gauss(), b = 0.25 + 0.4 * (-0.3 * gauss()) + 1.3 * gauss();
    rows.push(`${e.toFixed(2)},${b.toFixed(2)},${(0.5 * e + 0.5 * b).toFixed(2)}`);
  }
  return rows.join("\n");
}

type Parsed = { series: Record<string, number[]>; names: string[] } | { error: string } | null;

export function parseReturns(text: string, unit: HistDraft["unit"]): Parsed {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (lines.length === 0) return null;
  const delim = lines[0].includes("\t") ? "\t" : lines[0].includes(";") ? ";" : ",";
  const cells = (l: string) => l.split(delim).map((c) => c.trim());
  let head = cells(lines[0]);
  const dateCol = /^(date|time|period|month|day|year)$/i.test(head[0]) ? 1 : 0;
  head = head.slice(dateCol);
  if (head.length < 1 || head.length > 10) return { error: "Use between 1 and 10 columns of returns, with the asset names in the first row." };
  if (head.some((h) => !h || h.length > 40)) return { error: "Every column needs a name of 40 characters or fewer in the first row." };
  if (new Set(head).size !== head.length) return { error: "Column names must be different." };
  if (head.some((h) => Number.isFinite(Number(h)))) return { error: "The first row must be asset names, not numbers." };
  const series: Record<string, number[]> = Object.fromEntries(head.map((h) => [h, [] as number[]]));
  const div = unit === "percent" ? 100 : 1;
  for (let r = 1; r < lines.length; r++) {
    const row = cells(lines[r]).slice(dateCol);
    if (row.length !== head.length) return { error: `Line ${r + 1} has ${row.length} values but there are ${head.length} columns.` };
    for (let c = 0; c < head.length; c++) {
      const v = Number(row[c].replace(/%$/, ""));
      if (row[c] === "" || !Number.isFinite(v)) return { error: `Line ${r + 1}, column “${head[c]}”: “${row[c]}” is not a number.` };
      if (v / div <= -1) return { error: `Line ${r + 1}, column “${head[c]}”: a return of -100% or worse is not allowed.` };
      series[head[c]].push(v / div);
    }
  }
  const n = lines.length - 1;
  if (n < 20) return { error: `Only ${n} data row(s) found. At least 20 observations are needed.` };
  if (n > 5000) return { error: "At most 5000 rows are supported." };
  return { series, names: head };
}

export function histBody(d: HistDraft, parsed: Parsed) {
  if (!parsed || "error" in parsed) return null;
  const n = parsed.names.length;
  const w = parsed.names.map((nm) => (d.weights[nm] === undefined ? 100 / n : num(d.weights[nm])));
  if (w.some((x) => !(x >= 0)) || Math.abs(w.reduce((s, x) => s + x, 0) - 100) > 1e-4) return null;
  const confidences = [d.conf.c95 && 0.95, d.conf.c99 && 0.99].filter(Boolean) as number[];
  const ppy = num(d.ppy);
  if (!confidences.length || !Number.isInteger(ppy) || ppy < 1 || ppy > 366) return null;
  return { series: parsed.series, weights: Object.fromEntries(parsed.names.map((nm, i) => [nm, w[i] / 100])), periods_per_year: ppy, confidences };
}

const tip = { background: "#17213a", border: "1px solid #334155", borderRadius: 8 };
const axis = { fill: "#94a3b8", fontSize: 11 };

export function HistoricalTool({ d, set, adv, onSaved }: { d: HistDraft; set: (d: HistDraft) => void; adv: boolean; onSaved: () => void }) {
  const [src, setSrc] = useState<FinDataSources | null>(null);
  useEffect(() => { let live = true; call<FinDataSources>("finance/data-sources").then((s) => live && setSrc(s)).catch(() => {}); return () => { live = false; }; }, []);
  const parsed = useMemo(() => parseReturns(d.text, d.unit), [d.text, d.unit]);
  const body = useMemo(() => histBody(d, parsed), [d, parsed]);
  const a = useAnalysis<FinHistorical>("finance/historical", body, 500);
  const names = parsed && !("error" in parsed) ? parsed.names : [];
  const wsum = names.reduce((s, nm) => s + (d.weights[nm] === undefined ? 100 / names.length : num(d.weights[nm]) || 0), 0);

  return (
    <div className="space-y-4">
      <Panel title="1 · Your return series" badge={<Badge tone="amber">User-supplied · unverified</Badge>}>
        <div role="note" className="mb-3 rounded-lg border border-line bg-bg/60 p-3 text-xs leading-relaxed text-muted">
          <strong className="text-ink">{src?.message ?? "Data source status unavailable."}</strong>{" "}
          Paste periodic returns below: one row per period, with the asset names in the first row.
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="sm:col-span-3"><label htmlFor="h-text" className="mb-1 block text-xs text-muted">Returns (CSV, tab or semicolon separated; an optional first “Date” column is ignored)</label>
            <textarea id="h-text" rows={7} value={d.text} onChange={(e) => set({ ...d, text: e.target.value, weights: {} })} placeholder={"Fund A,Fund B\n1.2,0.4\n-0.8,0.3\n…"} className={`${field} w-full font-mono text-xs`} /></div>
          <div><label htmlFor="h-unit" className="mb-1 block text-xs text-muted">Values are</label><select id="h-unit" value={d.unit} onChange={(e) => set({ ...d, unit: e.target.value as HistDraft["unit"] })} className={`${field} w-full`}><option value="percent">percentages (1.2 = 1.2%)</option><option value="decimal">decimals (0.012 = 1.2%)</option></select></div>
          <div><label htmlFor="h-ppy" className="mb-1 block text-xs text-muted">Periods per year</label><select id="h-ppy" value={d.ppy} onChange={(e) => set({ ...d, ppy: e.target.value })} className={`${field} w-full`}><option value="252">252 (daily)</option><option value="52">52 (weekly)</option><option value="12">12 (monthly)</option><option value="4">4 (quarterly)</option><option value="1">1 (yearly)</option></select></div>
          <div className="flex items-end"><button type="button" onClick={() => set({ ...d, text: syntheticCsv(), unit: "percent", ppy: "12", weights: {} })} className="w-full rounded-lg border border-line px-3 py-2 text-xs font-semibold hover:border-violet/60">Insert synthetic example (NOT market data)</button></div>
        </div>
        {parsed && "error" in parsed && <p role="alert" className="mt-3 text-sm text-amber-300">{parsed.error}</p>}
        {names.length > 0 && (
          <div className="mt-4">
            <h3 className="mb-1 text-sm font-semibold">Portfolio weights <span className="font-normal text-muted">(constant weights, rebalanced every period)</span></h3>
            <div className="flex flex-wrap items-end gap-3">
              {names.map((nm) => (
                <div key={nm}><label htmlFor={`hw-${nm}`} className="mb-1 block text-[11px] text-muted">{nm} %</label><input id={`hw-${nm}`} inputMode="decimal" value={d.weights[nm] ?? String(+(100 / names.length).toFixed(4))} onChange={(e) => set({ ...d, weights: { ...Object.fromEntries(names.map((x) => [x, d.weights[x] ?? String(+(100 / names.length).toFixed(4))])), [nm]: e.target.value } })} className={`${field} w-24 font-mono`} /></div>))}
              <span className={`pb-2 font-mono text-xs ${Math.abs(wsum - 100) > 1e-4 ? "text-amber-300" : "text-muted"}`}>Total {+wsum.toFixed(4)}%</span>
              <fieldset><legend className="mb-1 text-[11px] text-muted">VaR/ES levels</legend><div className="flex gap-3 text-sm">{([["c95", "95%"], ["c99", "99%"]] as const).map(([k, l]) => <label key={k} className="flex items-center gap-1.5"><input type="checkbox" checked={d.conf[k]} onChange={(e) => set({ ...d, conf: { ...d.conf, [k]: e.target.checked } })} className="h-4 w-4 accent-[#8055f6]" />{l}</label>)}</div></fieldset>
            </div>
            {Math.abs(wsum - 100) > 1e-4 && <p className="mt-1 text-xs text-amber-300">Weights must add up to 100%.</p>}
          </div>)}
      </Panel>

      <Panel title="2 · Historical analysis" badge={<Badge tone="green">Computed from your data</Badge>}>
        <div aria-live="polite">
          {!parsed ? <p className="text-sm text-muted">Paste a return series (or insert the synthetic example) to begin.</p>
            : "error" in parsed ? <p className="text-sm text-amber-300">Fix the data above first.</p>
            : !body ? <p className="text-sm text-amber-300">Check the weights (100% total, no negatives), periods per year and confidence levels.</p>
            : a.loading ? <p className="flex items-center gap-2 text-sm text-muted"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Analysing…</p>
            : a.error ? <ErrorPanel message={a.error} />
            : a.data && (
              <div className="space-y-5">
                <p className="text-xs text-muted">{a.data.provenance} {a.data.portfolio.periods} periods at {a.data.periods_per_year} per year.</p>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[620px] text-sm"><caption className="sr-only">Return statistics by asset and for the portfolio</caption>
                    <thead><tr className="text-left text-[11px] text-muted">{["", "CAGR", "Ann. volatility", "Total return", "Max drawdown", "Worst period", ...(adv ? ["Skew", "Excess kurtosis"] : [])].map((h, i) => <th key={i} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
                    <tbody className="font-mono">
                      {[...a.data.names.map((nm) => [nm, a.data!.assets[nm]] as const), ["Portfolio", a.data.portfolio] as const].map(([nm, s]) => (
                        <tr key={nm} className={`border-t border-line ${nm === "Portfolio" ? "font-bold" : ""}`}><th scope="row" className="py-1.5 pr-3 text-left font-sans font-semibold">{nm}</th><td>{pc(s.cagr)}</td><td>{pc(s.annualised_vol)}</td><td>{pc(s.total_return)}</td><td>{pc(s.max_drawdown)}</td><td>{pc(s.worst_period)}</td>{adv && <><td>{s.skewness.toFixed(2)}</td><td>{s.excess_kurtosis.toFixed(2)}</td></>}</tr>))}
                    </tbody>
                  </table>
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                  <div><h3 className="mb-1 text-sm font-semibold">Growth of 1</h3>
                    <div className="h-44" role="img" aria-label="Portfolio growth of one unit over the period"><ResponsiveContainer width="100%" height="100%"><LineChart data={a.data.growth}><CartesianGrid vertical={false} stroke="rgba(148,163,184,0.12)" /><XAxis dataKey="t" tick={axis} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={40} /><YAxis domain={["auto", "auto"]} tick={axis} axisLine={false} tickLine={false} width={42} tickFormatter={(v) => Number(v).toFixed(2)} /><Tooltip contentStyle={tip} formatter={(v) => [Number(v).toFixed(3), "value"]} labelFormatter={(l) => `Period ${l}`} /><Line dataKey="value" stroke="#8055f6" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></div></div>
                  <div><h3 className="mb-1 text-sm font-semibold">Drawdown from the previous peak</h3>
                    <div className="h-44" role="img" aria-label="Portfolio drawdown over the period"><ResponsiveContainer width="100%" height="100%"><LineChart data={a.data.growth.map((g) => ({ t: g.t, dd: -g.drawdown * 100 }))}><CartesianGrid vertical={false} stroke="rgba(148,163,184,0.12)" /><XAxis dataKey="t" tick={axis} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={40} /><YAxis tick={axis} axisLine={false} tickLine={false} width={42} unit="%" /><Tooltip contentStyle={tip} formatter={(v) => [`${Number(v).toFixed(1)}%`, "drawdown"]} labelFormatter={(l) => `Period ${l}`} /><Line dataKey="dd" stroke="#f59e0b" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></div></div>
                </div>
                <div className="overflow-x-auto">
                  <h3 className="mb-1 text-sm font-semibold">Value at Risk and Expected Shortfall <span className="font-normal text-muted">(loss in a single period, % of portfolio value)</span></h3>
                  <table className="w-full min-w-[560px] text-sm"><caption className="sr-only">Historical and normal VaR and Expected Shortfall</caption>
                    <thead><tr className="text-left text-[11px] text-muted">{["Confidence", "Historical VaR", "Historical ES", "Normal VaR", "Normal ES", "Tail obs.", ...(adv ? ["Normal-VaR backtest"] : [])].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
                    <tbody className="font-mono">{a.data.risk.map((r) => (
                      <tr key={r.confidence} className="border-t border-line"><td className="py-1.5 font-sans">{pc(r.confidence, 0)}</td><td>{pc(r.historical.var, 2)}</td><td>{pc(r.historical.es, 2)}</td><td>{pc(r.parametric_normal.var, 2)}</td><td>{pc(r.parametric_normal.es, 2)}</td><td>{r.tail_observations}</td>
                        {adv && <td className="font-sans text-xs">{r.kupiec_parametric.exceedances} exceedances vs {r.kupiec_parametric.expected.toFixed(1)} expected (Kupiec p = {r.kupiec_parametric.p_value.toFixed(3)}){r.kupiec_parametric.p_value < 0.05 ? <span className="ml-1 text-amber-300">· normal VaR fits poorly</span> : ""}</td>}</tr>))}</tbody></table>
                  {a.data.risk.filter((r) => r.warning).map((r) => <p key={r.confidence} role="note" className="mt-2 text-xs text-amber-300">{pc(r.confidence, 0)}: {r.warning}</p>)}
                  <p className="mt-2 text-[11px] leading-relaxed text-muted">Historical VaR is the loss exceeded in only (1 − confidence) of past periods; ES is the average loss in those periods. They describe the past you supplied, not the future.</p>
                </div>
                {adv && (
                  <div className="overflow-x-auto"><h3 className="mb-1 text-sm font-semibold">Correlation</h3>
                    <table className="text-sm"><caption className="sr-only">Correlation matrix</caption><thead><tr><th />{a.data.names.map((n) => <th key={n} scope="col" className="px-2 text-[11px] font-normal text-muted">{n}</th>)}</tr></thead>
                      <tbody className="font-mono">{a.data.names.map((n, i) => <tr key={n}><th scope="row" className="pr-2 text-right text-[11px] font-normal text-muted">{n}</th>{a.data!.correlation[i].map((c, j) => <td key={j} style={{ background: `rgba(${c >= 0 ? "128,85,246" : "34,211,238"},${Math.abs(c) * 0.55})` }} className="px-2 py-1 text-center">{c.toFixed(2)}</td>)}</tr>)}</tbody></table></div>)}
                <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted">{a.data.notes.map((n) => <li key={n}>{n}</li>)}</ul>
              </div>)}
        </div>
      </Panel>
      <Panel title="Save this scenario"><ScenarioSaveBar endpoint="finance/scenarios" kind="historical" inputs={body} valid={!!body && !a.error} onSaved={onSaved} /></Panel>
    </div>
  );
}
