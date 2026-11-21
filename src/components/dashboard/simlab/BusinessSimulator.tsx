"use client";

import { useEffect, useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { call, post } from "@/lib/client";
import { Badge, ErrorPanel, Panel, Stat, dt } from "../ui";
import { field } from "../analysis";

interface InputInfo { key: string; label: string; meaning: string; min: number; max: number }
interface Info { inputs: InputInfo[]; documentation: string; model_version: string }
interface Outcome { price: number; units: number; revenue: number; gross_profit: number; gross_margin: number | null }
interface Optimal { exists: boolean; price: number | null; note: string }
interface Sens { key: string; label: string; base_value: number; low: { value: number; revenue_change: number; gross_profit_change: number } | null; high: { value: number; revenue_change: number; gross_profit_change: number } | null }
export interface BizResult {
  id: string; title: string; version: number; created_at: string; label: string; documentation: string; validation_status: string; effective_elasticity: number;
  inputs: Record<string, number>; base: Outcome & { name: string; optimal_price: Optimal };
  scenarios: (Outcome & { name: string; overrides: Record<string, number>; optimal_price: Optimal; change_vs_base: { units: number; revenue: number; gross_profit: number } })[];
  price_sweep: Outcome[]; sensitivity: Sens[]; provenance: { model: string; model_version: string; generated_at: string; random_seed: number | null };
}

const DEFAULTS: Record<string, string> = { market_size: "10000", adoption_rate: "0.2", reference_price: "50", price: "50", unit_cost: "20", demand_sensitivity: "2", competitor_reaction: "0" };
const money = (v: number) => v.toLocaleString("en-US", { maximumFractionDigits: 0 });
const signed = (v: number) => `${v >= 0 ? "+" : "−"}${money(Math.abs(v))}`;

/** Price versus revenue and gross profit across 50% to 150% of the price. Every point is computed by the model from your inputs. */
function SweepChart({ sweep, price, optimal }: { sweep: Outcome[]; price: number; optimal: Optimal }) {
  const W = 560, H = 220, L = 54, B = 28, T = 10, R = 12;
  const xs = sweep.map((s) => s.price), x0 = Math.min(...xs), x1 = Math.max(...xs);
  const ys = sweep.flatMap((s) => [s.revenue, s.gross_profit]), y0 = Math.min(0, ...ys), y1 = Math.max(...ys);
  const X = (v: number) => L + ((v - x0) / (x1 - x0)) * (W - L - R), Y = (v: number) => T + (1 - (v - y0) / (y1 - y0 || 1)) * (H - T - B);
  const line = (k: "revenue" | "gross_profit") => sweep.map((s, i) => `${i ? "L" : "M"}${X(s.price).toFixed(1)} ${Y(s[k]).toFixed(1)}`).join(" ");
  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Revenue and gross profit at prices from half to one and a half times your price" className="w-full">
        <line x1={L} x2={W - R} y1={Y(0)} y2={Y(0)} stroke="rgba(148,163,184,0.4)" />
        <path d={line("revenue")} fill="none" stroke="#60A5FA" strokeWidth="2" />
        <path d={line("gross_profit")} fill="none" stroke="#34D399" strokeWidth="2" />
        <line x1={X(price)} x2={X(price)} y1={T} y2={H - B} stroke="#F8FAFC" strokeDasharray="4 4" />
        {optimal.exists && optimal.price !== null && optimal.price >= x0 && optimal.price <= x1 && <line x1={X(optimal.price)} x2={X(optimal.price)} y1={T} y2={H - B} stroke="#34D399" strokeDasharray="2 3" />}
        {[x0, price, x1].map((v) => <text key={v} x={X(v)} y={H - 8} fill="#94A3B8" fontSize="11" textAnchor="middle">{money(v)}</text>)}
        {[y0, y1].map((v) => <text key={v} x={L - 6} y={Y(v) + 4} fill="#94A3B8" fontSize="11" textAnchor="end">{money(v)}</text>)}
      </svg>
      <figcaption className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted"><span><span className="text-[#60A5FA]">━</span> revenue</span><span><span className="text-[#34D399]">━</span> gross profit</span><span>┆ your price{optimal.exists ? " · dotted green: gross-profit-maximising price in this model" : ""}</span></figcaption>
    </figure>
  );
}

/** Pricing scenarios from market size, adoption, price, unit cost, demand sensitivity and competitor reaction. Every input is a hypothetical assumption. */
export function BusinessSimulator({ onSaved }: { onSaved?: () => void }) {
  const [info, setInfo] = useState<Info | null>(null);
  const [vals, setVals] = useState<Record<string, string>>(DEFAULTS);
  const [title, setTitle] = useState("");
  const [scen, setScen] = useState<{ name: string; over: Record<string, string> }[]>([{ name: "Scenario 1", over: {} }]);
  const [result, setResult] = useState<BizResult | null>(null);
  const [asVersion, setAsVersion] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    call<Info>("simlab/business/inputs").then((d) => live && setInfo(d), (e) => live && setErr(e instanceof Error ? e.message : "Could not load the simulator."));
    return () => { live = false; };
  }, []);
  if (!info) return err ? <ErrorPanel message={err} /> : <p className="text-sm text-muted" aria-busy="true">Loading…</p>;

  const num = (s: string) => (s.trim() === "" ? NaN : Number(s));
  async function run() {
    setBusy(true); setErr(null);
    try {
      const inputs = Object.fromEntries(Object.entries(vals).map(([k, v]) => [k, num(v)]));
      if (Object.values(inputs).some((v) => !Number.isFinite(v))) throw new Error("Every input must be a number.");
      const scenarios = scen.map((s) => ({ name: s.name.trim() || "Scenario", overrides: Object.fromEntries(Object.entries(s.over).filter(([, v]) => v.trim() !== "").map(([k, v]) => [k, num(v)])) }));
      const r = await post<BizResult>("simlab/business/run", { title: title.trim() || undefined, inputs, scenarios, based_on: asVersion && result ? result.id : undefined });
      setResult(r); onSaved?.();
    } catch (e) { setErr(e instanceof Error ? e.message : "The simulation failed."); } finally { setBusy(false); }
  }
  const all = result ? [{ ...result.base, change_vs_base: null as null | { units: number; revenue: number; gross_profit: number }, overrides: {} as Record<string, number> }, ...result.scenarios] : [];
  const maxSens = result ? Math.max(1, ...result.sensitivity.flatMap((s) => [s.low, s.high]).map((x) => Math.abs(x?.gross_profit_change ?? 0))) : 1;

  return (
    <div className="space-y-4">
      <Panel title="Business pricing simulator" badge={<Badge tone="amber">Hypothetical: every input is your assumption</Badge>}>
        <p className="text-xs leading-relaxed text-muted">{info.documentation}</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {info.inputs.map((i) => (
            <div key={i.key}><label htmlFor={`bz-${i.key}`} className="mb-1 block text-xs text-muted">{i.label}</label>
              <input id={`bz-${i.key}`} inputMode="decimal" value={vals[i.key]} onChange={(e) => setVals({ ...vals, [i.key]: e.target.value })} className={field} />
              <p className="mt-0.5 text-[11px] text-muted">{i.meaning} ({i.min} to {i.max})</p></div>
          ))}
          <div><label htmlFor="bz-title" className="mb-1 block text-xs text-muted">Name this simulation (optional)</label><input id="bz-title" maxLength={120} value={title} onChange={(e) => setTitle(e.target.value)} className={field} placeholder="Pricing scenario" /></div>
        </div>
      </Panel>

      {scen.map((s, i) => (
        <Panel key={i} title={`Alternative ${i + 1}`} badge={<Badge tone="amber">Overrides the base case</Badge>}>
          <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
            <div><label htmlFor={`bz-sc-${i}`} className="mb-1 block text-xs text-muted">Scenario name</label><input id={`bz-sc-${i}`} value={s.name} maxLength={60} onChange={(e) => setScen((all) => all.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} className={field} /></div>
            <button type="button" onClick={() => setScen((all) => all.filter((_, j) => j !== i))} disabled={scen.length === 1} aria-label={`Remove alternative ${i + 1}`} className="inline-flex items-center gap-1 rounded-lg border border-line px-3 py-1.5 text-xs text-muted hover:text-red-300 disabled:opacity-40"><Trash2 className="h-3.5 w-3.5" aria-hidden="true" /> Remove</button>
          </div>
          <p className="mb-2 text-[11px] text-muted">Fill in only the inputs this scenario changes; blank fields keep the base-case value.</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {info.inputs.map((inp) => <div key={inp.key}><label htmlFor={`bz-sc-${i}-${inp.key}`} className="mb-1 block text-xs text-muted">{inp.label}</label><input id={`bz-sc-${i}-${inp.key}`} inputMode="decimal" value={s.over[inp.key] ?? ""} placeholder={vals[inp.key]} onChange={(e) => setScen((all) => all.map((x, j) => (j === i ? { ...x, over: { ...x.over, [inp.key]: e.target.value } } : x)))} className={field} /></div>)}
          </div>
        </Panel>
      ))}

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" disabled={busy} onClick={run} className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Run business simulation</button>
        {scen.length < 3 && <button type="button" onClick={() => setScen((a) => [...a, { name: `Scenario ${a.length + 1}`, over: {} }])} className="inline-flex items-center gap-2 rounded-xl border border-violet/60 px-4 py-2.5 text-sm font-semibold text-violet hover:bg-violet/10"><Plus className="h-4 w-4" aria-hidden="true" /> Add an alternative ({scen.length} of 3)</button>}
        {result && <label className="inline-flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={asVersion} onChange={(e) => setAsVersion(e.target.checked)} /> Save as a new version of the last run</label>}
      </div>
      {err && <p role="alert" className="text-sm text-red-300">{err}</p>}

      {result && (
        <div className="space-y-4" aria-live="polite">
          <Panel title="Base case" badge={<Badge tone="muted">Saved “{result.title}”, version {result.version}</Badge>}>
            <div className="grid gap-3 sm:grid-cols-4">
              <Stat label="Units" value={money(result.base.units)} hint={`at price ${result.base.price}`} />
              <Stat label="Revenue" value={money(result.base.revenue)} />
              <Stat label="Gross profit" value={money(result.base.gross_profit)} />
              <Stat label="Gross margin" value={result.base.gross_margin === null ? "n/a" : `${(result.base.gross_margin * 100).toFixed(1)}%`} />
            </div>
            <p className="mt-3 text-xs text-muted">Effective elasticity {result.effective_elasticity.toFixed(2)}. {result.base.optimal_price.note}{result.base.optimal_price.exists && result.base.optimal_price.price !== null ? ` Best price in this model: ${result.base.optimal_price.price.toFixed(2)}.` : ""}</p>
          </Panel>

          <Panel title="Scenario comparison">
            <div className="overflow-x-auto"><table className="w-full text-sm"><caption className="sr-only">Units, revenue and gross profit for the base case and each alternative</caption>
              <thead><tr className="text-left text-[11px] text-muted">{["", "Price", "Units", "Revenue", "Gross profit", "Margin", "Assumptions changed"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
              <tbody className="font-mono">{all.map((s) => (
                <tr key={s.name} className="border-t border-line"><th scope="row" className="py-1.5 pr-3 text-left font-sans font-medium">{s.name}</th><td className="pr-3">{s.price}</td>
                  <td className="pr-3">{money(s.units)}{s.change_vs_base && <span className="ml-1 text-[10px] text-muted">({signed(s.change_vs_base.units)})</span>}</td>
                  <td className="pr-3">{money(s.revenue)}{s.change_vs_base && <span className="ml-1 text-[10px] text-muted">({signed(s.change_vs_base.revenue)})</span>}</td>
                  <td className="pr-3">{money(s.gross_profit)}{s.change_vs_base && <span className="ml-1 text-[10px] text-muted">({signed(s.change_vs_base.gross_profit)})</span>}</td>
                  <td className="pr-3">{s.gross_margin === null ? "n/a" : `${(s.gross_margin * 100).toFixed(1)}%`}</td>
                  <td className="font-sans text-xs text-muted">{Object.keys(s.overrides).length ? Object.entries(s.overrides).map(([k, v]) => `${k.replace(/_/g, " ")} = ${v}`).join("; ") : s.name === "Base case" ? "none" : "none (equals the base case)"}</td></tr>
              ))}</tbody></table></div>
          </Panel>

          <Panel title="Price sweep"><SweepChart sweep={result.price_sweep} price={result.base.price} optimal={result.base.optimal_price} /></Panel>

          <Panel title="What moves gross profit most" badge={<Badge tone="muted">Each input ±10%, one at a time</Badge>}>
            <ul className="space-y-2 text-sm" aria-label="Sensitivity">
              {result.sensitivity.map((s) => (
                <li key={s.key}>
                  <div className="flex justify-between gap-3"><span>{s.label} <span className="font-mono text-xs text-muted">(base {s.base_value})</span></span>
                    <span className="font-mono text-xs">{s.low ? `${signed(s.low.gross_profit_change)} at −10%` : "no change possible down"} · {s.high ? `${signed(s.high.gross_profit_change)} at +10%` : "no change possible up"}</span></div>
                  <div className="mt-1 flex h-2 gap-0.5" aria-hidden="true"><div className="flex w-1/2 justify-end"><div className="h-2 rounded-l bg-violet/70" style={{ width: `${(Math.abs(s.low?.gross_profit_change ?? 0) / maxSens) * 100}%` }} /></div><div className="flex w-1/2"><div className="h-2 rounded-r bg-cyan/70" style={{ width: `${(Math.abs(s.high?.gross_profit_change ?? 0) / maxSens) * 100}%` }} /></div></div>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-muted">Change in gross profit. An input at a limit (for example adoption at 100%) can only move one way. Demand sensitivity has no effect while the price equals the reference price.</p>
          </Panel>

          <Panel title="Model, status and export">
            <p className="text-xs leading-relaxed text-muted">{result.validation_status}</p>
            <p className="mt-2 text-xs text-muted">{result.label} {result.provenance.model}@{result.provenance.model_version}, run {dt(result.created_at)}, random seed: none (deterministic).</p>
            <div className="mt-3 flex flex-wrap gap-2 text-sm">{(["csv", "json"] as const).map((f) => <a key={f} href={`/app-api/simlab/runs/${result.id}/export?format=${f}`} download className="rounded-lg border border-line px-3 py-1.5 font-semibold hover:bg-white/5">{f.toUpperCase()}</a>)}</div>
          </Panel>
        </div>
      )}
    </div>
  );
}
