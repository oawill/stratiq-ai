"use client";

import { useMemo, useState } from "react";
import { DEFENSIVE, MONTHS, RISKS, SCENARIOS, candles, distribution, fan, portfolio, regimes, stress, type Months, type RiskId, type ScenarioId } from "@/lib/landing/markets";
import { MarketChart, REGIME_COLOUR } from "../visualizations/MarketChart";
import { FanChart, RiskDistribution } from "../visualizations/RiskDistribution";

const usd = (v: number) => `$${v.toFixed(0)}`;
const pc = (v: number, d = 0) => `${(v * 100).toFixed(d)}%`;
const select = "w-full rounded-xl border border-line bg-night/70 px-3 py-2 text-sm focus:border-emerald-400 focus:outline-none focus:ring-2 focus:ring-emerald-400/40";

/** Market risk demonstration: a SIMULATED price series, regimes, and scenario-based risk analysis from an explicit lognormal model. */
export default function MarketsPanel() {
  const [sc, setSc] = useState<ScenarioId>("base");
  const [risk, setRisk] = useState<RiskId>("balanced");
  const [months, setMonths] = useState<Months>(3);
  const series = useMemo(() => candles(), []);
  const reg = useMemo(() => regimes(series), [series]);
  const d = useMemo(() => distribution(sc, risk, months), [sc, risk, months]);
  const points = useMemo(() => fan(sc, risk, months), [sc, risk, months]);
  const p = portfolio(sc, risk);
  const scenario = SCENARIOS.find((s) => s.id === sc)!;
  const riskInfo = RISKS.find((r) => r.id === risk)!;
  const stresses = stress(risk);
  const now = reg[reg.length - 1];
  const stretch = reg.map((r, i) => (r.regime === "High volatility" ? i + 1 : 0)).filter(Boolean);

  return (
    <div className="grid gap-5 lg:grid-cols-12">
      <div className="glass space-y-5 rounded-3xl p-5 lg:col-span-4">
        <div>
          <label htmlFor="mk-scenario" className="mb-1 block text-xs text-muted">Market scenario</label>
          <select id="mk-scenario" value={sc} onChange={(e) => setSc(e.target.value as ScenarioId)} className={select}>{SCENARIOS.map((s) => <option key={s.id} value={s.id}>{s.label} case</option>)}</select>
          <p className="mt-1 text-[11px] text-muted">{scenario.blurb}</p>
        </div>
        <div>
          <label htmlFor="mk-risk" className="mb-1 block text-xs text-muted">Risk tolerance</label>
          <select id="mk-risk" value={risk} onChange={(e) => setRisk(e.target.value as RiskId)} className={select}>{RISKS.map((r) => <option key={r.id} value={r.id}>{r.label} ({Math.round(r.equity * 100)}% equities)</option>)}</select>
        </div>
        <fieldset>
          <legend className="mb-1 text-xs text-muted">Time horizon</legend>
          <div className="inline-flex rounded-xl border border-line p-0.5" role="radiogroup">
            {MONTHS.map((m) => (
              <label key={m} className={`cursor-pointer rounded-lg px-3 py-1.5 text-sm ${months === m ? "bg-emerald-400/20 text-emerald-100" : "text-muted hover:text-ink"}`}>
                <input type="radio" name="mk-horizon" className="sr-only" checked={months === m} onChange={() => setMonths(m)} />{m === 12 ? "12 months" : `${m} month${m > 1 ? "s" : ""}`}
              </label>
            ))}
          </div>
        </fieldset>
        <div role="note" className="rounded-xl border border-line bg-night2/60 p-3 text-[11px] leading-relaxed text-muted">
          <strong className="text-ink">Assumptions shown:</strong> equities drift {pc(scenario.mu)} a year with {pc(scenario.sigma)} volatility ({scenario.label.toLowerCase()} case); the defensive part drifts {pc(DEFENSIVE.mu)} with {pc(DEFENSIVE.sigma)} volatility and a {DEFENSIVE.rho} correlation to equities. Portfolio: {pc(riskInfo.equity)} equities, giving {pc(p.mu, 1)} drift and {pc(p.sigma, 1)} volatility. Value after T years is lognormal, starting at 100. These are assumptions for illustration, not forecasts.
        </div>
      </div>

      <div className="space-y-5 lg:col-span-8">
        <div className="glass rounded-3xl p-5">
          <p role="status" aria-live="polite" className="mb-4 rounded-xl border border-emerald-400/40 bg-emerald-400/10 p-3 text-sm leading-relaxed">
            Under these assumptions, a {riskInfo.label.toLowerCase()} portfolio of 100 would have a middle estimate of <strong className="font-mono">{usd(d.quantiles.q50)}</strong> after {months === 12 ? "12 months" : `${months} month${months > 1 ? "s" : ""}`}. About 9 in 10 simulated outcomes fall between <strong className="font-mono">{usd(d.quantiles.q05)}</strong> and <strong className="font-mono">{usd(d.quantiles.q95)}</strong>, and the chance of finishing below 100 is <strong className="font-mono">{pc(d.lossProbability)}</strong>. These are scenarios, not predictions or guaranteed returns.
          </p>
          <div className="grid gap-6 md:grid-cols-2">
            <div>
              <h3 className="mb-1 text-sm font-bold">Risk distribution</h3>
              <RiskDistribution d={d} />
              <dl className="mt-2 grid grid-cols-3 gap-2 text-center text-xs">
                <div className="rounded-lg border border-line p-2"><dt className="text-muted">Chance of loss</dt><dd className="font-mono font-bold">{pc(d.lossProbability)}</dd></div>
                <div className="rounded-lg border border-line p-2"><dt className="text-muted">5th percentile</dt><dd className="font-mono font-bold">{usd(d.quantiles.q05)}</dd></div>
                <div className="rounded-lg border border-line p-2"><dt className="text-muted">Worst 5% average</dt><dd className="font-mono font-bold">{usd(d.worstFivePercentAverage)}</dd></div>
              </dl>
            </div>
            <div>
              <h3 className="mb-1 text-sm font-bold">Probability range over time</h3>
              <FanChart points={points} />
              <p className="mt-1 text-[11px] text-muted">Dark band: middle half of outcomes. Light band: 5th to 95th percentile. Line: median.</p>
            </div>
          </div>
        </div>

        <div className="grid gap-5 md:grid-cols-2">
          <div className="glass rounded-3xl p-5">
            <h3 className="mb-1 text-sm font-bold">Bull, base and bear compared</h3>
            <table className="w-full text-xs">
              <caption className="sr-only">Outcome ranges for each scenario at the chosen risk level and horizon</caption>
              <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="font-normal">Case</th><th scope="col" className="font-normal">Median</th><th scope="col" className="font-normal">5th–95th</th><th scope="col" className="font-normal">Loss chance</th></tr></thead>
              <tbody className="font-mono">
                {SCENARIOS.map((s) => { const x = distribution(s.id, risk, months); return (
                  <tr key={s.id} className={`border-t border-line ${s.id === sc ? "text-ink" : "text-muted"}`}><th scope="row" className="py-1.5 text-left font-sans font-medium">{s.label}{s.id === sc ? " ●" : ""}</th><td>{usd(x.quantiles.q50)}</td><td>{usd(x.quantiles.q05)}–{usd(x.quantiles.q95)}</td><td>{pc(x.lossProbability)}</td></tr>
                ); })}
              </tbody>
            </table>
            <h3 className="mb-1 mt-5 text-sm font-bold">Portfolio stress test</h3>
            <table className="w-full text-xs">
              <caption className="sr-only">Instant portfolio change under hypothetical shocks</caption>
              <tbody className="font-mono">
                {stresses.map((s) => <tr key={s.label} className="border-t border-line"><th scope="row" className="py-1.5 pr-2 text-left font-sans font-normal text-muted">{s.label}</th><td className={`text-right ${s.impact < 0 ? "text-rose-200" : "text-emerald-200"}`}>{s.impact < 0 ? "−" : "+"}{pc(Math.abs(s.impact), 1)}</td></tr>)}
              </tbody>
            </table>
            <p className="mt-1 text-[11px] text-muted">Hypothetical one-off shocks applied to a {pc(riskInfo.equity)} equity portfolio: equity weight × equity shock + defensive weight × defensive shock.</p>
          </div>
          <div className="glass rounded-3xl p-5">
            <div className="mb-1 flex items-center justify-between gap-2"><h3 className="text-sm font-bold">Simulated price and regimes</h3><span className="rounded-full border px-2 py-0.5 text-[10px] font-semibold" style={{ borderColor: REGIME_COLOUR[now.regime], color: REGIME_COLOUR[now.regime] }}>Now: {now.regime}</span></div>
            <MarketChart candles={series} regimes={reg} />
            <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted">
              {(Object.keys(REGIME_COLOUR) as (keyof typeof REGIME_COLOUR)[]).map((k) => <li key={k} className="flex items-center gap-1.5"><span className="h-2 w-3 rounded-sm" style={{ background: REGIME_COLOUR[k] }} aria-hidden="true" />{k}</li>)}
            </ul>
            <p className="mt-2 text-[11px] leading-relaxed text-muted">A <strong className="text-ink">simulated</strong> random-walk series, generated in your browser with a fixed seed, with a volatile stretch around days {stretch[0] ?? "–"}–{stretch[stretch.length - 1] ?? "–"} built in. Regimes are labelled from the last 10 days: high volatility when realised volatility is well above its median, otherwise by trend. It is not market data and not a historical record.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
