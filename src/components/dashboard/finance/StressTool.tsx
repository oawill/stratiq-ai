"use client";

import { useMemo } from "react";
import { Loader2, Plus, X } from "lucide-react";
import type { FinStress } from "@/lib/types";
import { Badge, ErrorPanel, Panel } from "../ui";
import { ScenarioSaveBar, field, num, pc, useAnalysis } from "../analysis";
import type { PortfolioDraft } from "./PortfolioMC";

export interface StressDraft {
  assets: { name: string; weight: string }[]; // weight in percent
  initial: string;
  scenarios: { name: string; shocks: string[] }[]; // percent shock per asset ("" = 0)
  reverse: string; // percent target loss, optional
}

const money = (x: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(x);

export const stressFromPortfolio = (pd: PortfolioDraft, keep?: StressDraft): StressDraft => ({
  assets: pd.assets.map((a) => ({ name: a.name, weight: a.weight })),
  initial: pd.initial,
  scenarios: keep && keep.scenarios.length ? keep.scenarios.map((s) => ({ ...s, shocks: pd.assets.map((_, i) => s.shocks[i] ?? "") })) : defaultScenarios(pd.assets.length),
  reverse: keep?.reverse ?? "15",
});

// Hypothetical shocks for demonstration. They are not predictions and do not describe any past event.
function defaultScenarios(n: number) {
  const shock = (vals: number[]) => Array.from({ length: n }, (_, i) => (vals[i] === undefined ? "" : String(vals[i])));
  return [{ name: "Hypothetical equity sell-off", shocks: shock([-30, 3, 0]) }, { name: "Hypothetical rates shock", shocks: shock([-10, -8, 0]) }];
}

export function stressBody(d: StressDraft) {
  const assets = d.assets.map((a) => ({ name: a.name.trim(), weight: num(a.weight) / 100 }));
  if (assets.some((a) => !a.name || !(a.weight >= 0)) || new Set(assets.map((a) => a.name)).size !== assets.length) return null;
  if (Math.abs(assets.reduce((s, a) => s + a.weight, 0) - 1) > 1e-6) return null;
  const initial = num(d.initial);
  if (!(initial > 0) || d.scenarios.length === 0) return null;
  const scenarios = [];
  for (const sc of d.scenarios) {
    if (!sc.name.trim()) return null;
    const shocks: Record<string, number> = {};
    for (let i = 0; i < assets.length; i++) {
      const raw = sc.shocks[i] ?? "";
      if (raw.trim() === "") continue;
      const v = num(raw) / 100;
      if (!(v >= -1)) return null;
      shocks[assets[i].name] = v;
    }
    scenarios.push({ name: sc.name.trim(), shocks });
  }
  if (new Set(scenarios.map((s) => s.name)).size !== scenarios.length) return null;
  const rt = d.reverse.trim() === "" ? null : num(d.reverse) / 100;
  if (rt !== null && !(rt > 0 && rt < 1)) return null;
  return { assets, initial_value: initial, scenarios, reverse_target_loss: rt };
}

export function StressTool({ d, set, pd, adv, onSaved }: { d: StressDraft; set: (d: StressDraft) => void; pd: PortfolioDraft; adv: boolean; onSaved: () => void }) {
  const body = useMemo(() => stressBody(d), [d]);
  const a = useAnalysis<FinStress>("finance/stress", body);
  const sum = d.assets.reduce((s, x) => s + (Number.isFinite(num(x.weight)) ? num(x.weight) : 0), 0);
  const setSc = (i: number, v: Partial<StressDraft["scenarios"][number]>) => set({ ...d, scenarios: d.scenarios.map((s, j) => (j === i ? { ...s, ...v } : s)) });
  const setShock = (i: number, k: number, v: string) => setSc(i, { shocks: d.scenarios[i].shocks.map((x, j) => (j === k ? v : x)) });
  const addUniform = () => {
    const v = window.prompt("Uniform shock to every asset, in % (for example -15):", "-15");
    if (v === null || !Number.isFinite(Number(v)) || Number(v) < -100) return;
    set({ ...d, scenarios: [...d.scenarios, { name: `Hypothetical ${v}% across all assets`, shocks: d.assets.map(() => v) }] });
  };
  const problem = !body
    ? Math.abs(sum - 100) > 1e-4 ? `Asset weights add up to ${+sum.toFixed(4)}%, not 100%. Edit them in the portfolio builder and press “Use assets from the portfolio builder”.`
      : "Check the scenario names (unique, non-empty), shocks (numbers of at least -100) and the reverse-stress target (between 0 and 100)."
    : null;
  return (
    <div className="space-y-4">
      <Panel title="1 · Portfolio and hypothetical shocks" badge={<Badge tone="amber">Hypothetical, not predictions</Badge>}>
        <p className="mb-3 text-xs leading-relaxed text-muted">A stress test asks: <em>if each asset suddenly moved by this much, what happens to the portfolio?</em> Shocks are instant revaluations of your current weights. Leave a cell empty for no change.</p>
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <button type="button" onClick={() => set(stressFromPortfolio(pd, d))} className="rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:border-violet/60">Use assets from the portfolio builder</button>
          <div><label htmlFor="st-init" className="sr-only">Starting value</label><input id="st-init" inputMode="decimal" aria-label="Starting value in dollars" value={d.initial} onChange={(e) => set({ ...d, initial: e.target.value })} className={`${field} w-32 font-mono`} /></div>
          <span className="text-xs text-muted">starting value ($)</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm">
            <caption className="sr-only">Hypothetical shocks by scenario and asset, in percent</caption>
            <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="font-normal">Scenario</th>{d.assets.map((x, k) => <th key={k} scope="col" className="font-normal">{x.name} <span className="font-mono">({x.weight}%)</span> shock %</th>)}<th /></tr></thead>
            <tbody>
              {d.scenarios.map((s, i) => (
                <tr key={i}>
                  <td className="pr-2 pb-1"><input aria-label={`Scenario ${i + 1} name`} value={s.name} maxLength={40} onChange={(e) => setSc(i, { name: e.target.value })} className={`${field} w-56`} /></td>
                  {d.assets.map((x, k) => <td key={k} className="pr-2 pb-1"><input aria-label={`${s.name}: shock to ${x.name} percent`} inputMode="decimal" value={s.shocks[k] ?? ""} placeholder="0" onChange={(e) => setShock(i, k, e.target.value)} className={`${field} w-24 font-mono`} /></td>)}
                  <td>{d.scenarios.length > 1 && <button type="button" aria-label={`Remove scenario ${s.name}`} onClick={() => set({ ...d, scenarios: d.scenarios.filter((_, j) => j !== i) })} className="rounded p-1.5 text-muted hover:text-red-300"><X className="h-4 w-4" /></button>}</td>
                </tr>))}
            </tbody>
          </table>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {d.scenarios.length < 20 && <button type="button" onClick={() => set({ ...d, scenarios: [...d.scenarios, { name: `Scenario ${d.scenarios.length + 1}`, shocks: d.assets.map(() => "") }] })} className="inline-flex items-center gap-1 rounded-lg border border-dashed border-line px-3 py-1.5 text-xs text-muted hover:text-ink"><Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add scenario</button>}
          {d.scenarios.length < 20 && <button type="button" onClick={addUniform} className="inline-flex items-center gap-1 rounded-lg border border-dashed border-line px-3 py-1.5 text-xs text-muted hover:text-ink"><Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add uniform shock</button>}
        </div>
        <div className="mt-4 max-w-xs"><label htmlFor="st-rev" className="mb-1 block text-xs text-muted">Reverse stress: target portfolio loss (%)</label><input id="st-rev" inputMode="decimal" value={d.reverse} placeholder="optional" onChange={(e) => set({ ...d, reverse: e.target.value })} className={`${field} w-full font-mono`} /></div>
      </Panel>

      <Panel title="2 · Results" badge={<Badge tone="green">Exact</Badge>}>
        <div aria-live="polite">
          {problem ? <p className="text-sm text-amber-300">{problem}</p> : a.loading ? <p className="flex items-center gap-2 text-sm text-muted"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Calculating…</p>
            : a.error ? <ErrorPanel message={a.error} /> : a.data && (
              <div className="space-y-4">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[460px] text-sm"><caption className="sr-only">Portfolio impact by scenario</caption>
                    <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="font-normal">Scenario</th><th scope="col" className="font-normal">Portfolio return</th><th scope="col" className="font-normal">Gain / loss</th><th scope="col" className="font-normal">Value after</th>{a.data.reverse_target !== null && <th scope="col" className="font-normal">Scale for {pc(a.data.reverse_target, 0)} loss</th>}</tr></thead>
                    <tbody className="font-mono">
                      {a.data.scenarios.map((s) => (
                        <tr key={s.name} className="border-t border-line">
                          <th scope="row" className="py-2 pr-3 text-left font-sans font-semibold">{s.name}{s.name === a.data!.worst && a.data!.scenarios.length > 1 && <span className="ml-2"><Badge tone="amber">Worst</Badge></span>}</th>
                          <td className={s.portfolio_return < 0 ? "text-red-300" : "text-success"}>{s.portfolio_return >= 0 ? "+" : ""}{pc(s.portfolio_return)}</td>
                          <td>{s.pnl >= 0 ? "+" : "−"}{money(Math.abs(s.pnl))}</td><td>{money(s.value_after)}</td>
                          {a.data!.reverse_target !== null && <td>{s.scale_to_target == null ? "n/a (no loss)" : `×${s.scale_to_target.toFixed(2)}`}</td>}
                        </tr>))}
                    </tbody>
                  </table>
                </div>
                {a.data.reverse_target !== null && <p className="text-xs text-muted">Reverse stress: multiplying a scenario&apos;s shocks by the factor shown would produce a loss equal to your target. A factor below 1 means the scenario already exceeds the target.</p>}
                {adv && (
                  <div className="grid gap-3 sm:grid-cols-2">
                    {a.data.scenarios.map((s) => (
                      <div key={s.name} className="rounded-xl border border-line p-3">
                        <h3 className="mb-1 text-sm font-semibold">{s.name}: where the loss comes from</h3>
                        <ul className="space-y-1 text-sm">{s.contributions.filter((c) => c.shock !== 0).map((c) => <li key={c.asset} className="flex justify-between gap-2"><span>{c.asset} <span className="text-muted">({c.shock >= 0 ? "+" : ""}{pc(c.shock, 0)})</span></span><span className="font-mono">{c.pnl >= 0 ? "+" : "−"}{money(Math.abs(c.pnl))}</span></li>)}</ul>
                      </div>))}
                  </div>)}
                <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted">{a.data.notes.map((n) => <li key={n}>{n}</li>)}</ul>
              </div>)}
        </div>
      </Panel>
      <Panel title="Save this scenario"><ScenarioSaveBar endpoint="finance/scenarios" kind="stress" inputs={body} valid={!!body && !a.error} onSaved={onSaved} /></Panel>
    </div>
  );
}
