"use client";

import { useMemo, useState } from "react";
import { PRICES, PRICE_NAMES, SCENARIOS, analyse, type ScenarioId } from "@/lib/landing/strategy";
import { DecisionTree } from "../visualizations/DecisionTree";
import { OutcomeChart } from "../visualizations/OutcomeChart";
import { PayoffMatrix } from "../visualizations/PayoffMatrix";

const money = (v: number) => `${v < 0 ? "−" : ""}$${Math.abs(v).toLocaleString()}`;
const price = (i: number) => `${PRICE_NAMES[i]} ($${PRICES[i]})`;

/** The interactive game-theory demonstration, computed live from lib/landing/strategy (which reuses the Strategy simulator's demand model). */
export default function StrategyPanel() {
  const [id, setId] = useState<ScenarioId>("rival-lowers");
  const a = useMemo(() => analyse(id), [id]);
  const committed = a.scenario.rivalCommits;

  let summary: string;
  if (committed !== undefined && a.bestRow !== null) {
    summary = `With the rival fixed at ${price(committed)}, our best reply is ${price(a.bestRow)}, earning ${money(a.outcomes[a.bestRow].profit)} a period.`;
  } else if (a.nash.length) {
    const e = a.nash[0];
    const delta = a.baseline.nashProfit === null ? null : a.outcomes[e.row].profit - a.baseline.nashProfit;
    summary = `Pure Nash equilibrium: we price ${price(e.row)} and the rival prices ${price(e.col)}; our profit is ${money(a.outcomes[e.row].profit)}${delta === null ? "" : `, ${delta >= 0 ? "up" : "down"} ${money(Math.abs(delta))} from the baseline equilibrium (${money(a.baseline.nashProfit!)})`}.`;
  } else {
    summary = "This game has no pure-strategy Nash equilibrium: whichever prices are chosen, one firm would gain by switching. A mixed strategy would be needed.";
  }

  return (
    <div className="grid gap-5 lg:grid-cols-12">
      <div className="glass space-y-5 rounded-3xl p-5 lg:col-span-4">
        <fieldset>
          <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Choose a business scenario</legend>
          <div className="grid gap-2">
            {SCENARIOS.map((s) => (
              <label key={s.id} className={`flex cursor-pointer items-start gap-2.5 rounded-xl border p-3 text-sm transition-colors ${id === s.id ? "border-royal/70 bg-royal/10" : "border-line hover:bg-white/5"}`}>
                <input type="radio" name="st-scenario" value={s.id} checked={id === s.id} onChange={() => setId(s.id)} className="mt-1 accent-[#8B5CF6]" />
                <span><span className="font-semibold">{s.label}</span><span className="mt-0.5 block text-xs text-muted">{s.blurb}</span></span>
              </label>
            ))}
          </div>
        </fieldset>
        <div>
          <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">Assumptions in this scenario</h3>
          <ul className="space-y-1 text-xs text-muted">
            {a.scenario.assumptions.map((x) => <li key={x} className="flex gap-2"><span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-royal" aria-hidden="true" />{x}</li>)}
          </ul>
        </div>
        <div role="note" className="rounded-xl border border-line bg-night2/60 p-3 text-[11px] leading-relaxed text-muted">
          <strong className="text-ink">The model:</strong> our share = 0.5 + shift + 0.06 × (rival price − our price), clamped to 0–100%; demand = 1,000 × (1.6 − average price ÷ 20); profit = quantity × (price − $5) − fixed cost ($1,500). The same demand model powers the Strategy simulator in the app. The numbers are assumptions for illustration, not forecasts of any real market.
        </div>
      </div>

      <div className="space-y-5 lg:col-span-8">
        <div className="glass rounded-3xl p-5">
          <p role="status" aria-live="polite" className="mb-4 rounded-xl border border-royal/40 bg-royal/10 p-3 text-sm leading-relaxed">{summary}</p>
          <div className="grid gap-6 md:grid-cols-2">
            <div>
              <h3 className="mb-2 text-sm font-bold">Payoff matrix and equilibrium</h3>
              <PayoffMatrix game={a.game} nash={a.nash} committedCol={committed} bestRow={a.bestRow} />
              <p className="mt-2 text-[11px] leading-relaxed text-muted">
                <strong className="text-ink">NE</strong> = pure Nash equilibrium: neither firm gains by changing only its own price. <strong className="text-ink">BR</strong> = our best reply to the rival&apos;s committed price. {a.nash.length === 0 ? "No pure equilibrium exists here." : `${a.nash.length} equilibri${a.nash.length === 1 ? "um" : "a"} found.`}
              </p>
            </div>
            <div>
              <h3 className="mb-2 text-sm font-bold">Outcome by our price</h3>
              <p className="mb-2 text-[11px] text-muted">{a.referenceLabel}</p>
              {a.bestRow !== null ? <OutcomeChart rows={a.outcomes.map((o) => ({ label: o.label, value: o.profit, best: o.best }))} caption={`Our profit by price. ${a.referenceLabel}.`} /> : <p className="text-xs text-muted">No single reference outcome, so no comparison is drawn.</p>}
              <h3 className="mb-1.5 mt-5 text-sm font-bold">Sensitivity to customer price-sensitivity</h3>
              <table className="w-full text-xs">
                <caption className="sr-only">Our reference profit at different values of price sensitivity</caption>
                <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="font-normal">Share shift per $1 price gap</th><th scope="col" className="text-right font-normal">Our profit</th></tr></thead>
                <tbody className="font-mono">
                  {a.sensitivity.map((s) => <tr key={s.sensitivity} className={`border-t border-line ${s.sensitivity === 0.06 ? "text-ink" : "text-muted"}`}><th scope="row" className="py-1 text-left font-normal">{(s.sensitivity * 100).toFixed(0)} points{s.sensitivity === 0.06 ? " (assumed)" : ""}</th><td className="text-right">{s.profit === null ? "no equilibrium" : money(s.profit)}</td></tr>)}
                </tbody>
              </table>
            </div>
          </div>
        </div>
        <div className="glass rounded-3xl p-5">
          <h3 className="mb-1 text-sm font-bold">Competitor response model: if we move first</h3>
          <p className="mb-3 text-xs text-muted">We pick a price, then the rival replies with whatever maximises its own profit. {PRICE_NAMES[a.tree.best]} (${PRICES[a.tree.best]}) is our best opening move in this sequential view.</p>
          <DecisionTree branches={a.tree.branches} best={a.tree.best} />
        </div>
      </div>
    </div>
  );
}
