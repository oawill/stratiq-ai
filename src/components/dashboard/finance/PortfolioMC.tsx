"use client";

import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Loader2, Plus, X } from "lucide-react";
import { post } from "@/lib/client";
import type { FinAnalytics, FinMonteCarlo } from "@/lib/types";
import { Badge, ErrorPanel, Panel } from "../ui";
import { ScenarioSaveBar, field, num, pc, useAnalysis } from "../analysis";

export interface PortfolioDraft {
  assets: { name: string; weight: string; mu: string; sigma: string }[]; // percents
  corr: string[][];
  initial: string;
}
export interface McDraft {
  horizon: string; steps: "4" | "12" | "52"; iterations: string; rebalance: "every_step" | "none"; tails: "normal" | "student_t"; df: string;
  seed: string; conf: { c90: boolean; c95: boolean; c99: boolean }; lossThreshold: string; ddThreshold: string;
}

// Illustrative assumptions only. They are not forecasts and not market data.
export const defaultPortfolio = (): PortfolioDraft => ({
  assets: [
    { name: "Equities", weight: "60", mu: "7", sigma: "18" },
    { name: "Bonds", weight: "30", mu: "3", sigma: "6" },
    { name: "Cash", weight: "10", mu: "1", sigma: "0.5" },
  ],
  corr: [["1", "0.2", "0"], ["0.2", "1", "0.1"], ["0", "0.1", "1"]],
  initial: "100000",
});
export const defaultMc = (): McDraft => ({
  horizon: "10", steps: "12", iterations: "5000", rebalance: "every_step", tails: "normal", df: "5", seed: "",
  conf: { c90: false, c95: true, c99: true }, lossThreshold: "20", ddThreshold: "25",
});

export function portfolioBody(d: PortfolioDraft) {
  const assets = d.assets.map((a) => ({ name: a.name.trim(), weight: num(a.weight) / 100, mu: num(a.mu) / 100, sigma: num(a.sigma) / 100 }));
  if (assets.some((a) => !a.name || !(a.weight >= 0) || !Number.isFinite(a.mu) || !(a.sigma >= 0)) || new Set(assets.map((a) => a.name)).size !== assets.length) return null;
  if (Math.abs(assets.reduce((s, a) => s + a.weight, 0) - 1) > 1e-6) return null;
  const correlation = d.corr.map((r) => r.map(num));
  if (correlation.some((r) => r.some((x) => !(x >= -1 && x <= 1)))) return null;
  const initial = num(d.initial);
  if (!(initial > 0)) return null;
  return { assets, correlation, initial_value: initial };
}

export function portfolioProblem(d: PortfolioDraft): string | null {
  const names = d.assets.map((a) => a.name.trim());
  if (names.some((n) => !n)) return "Name every asset.";
  if (new Set(names).size !== names.length) return "Asset names must be different.";
  if (d.assets.some((a) => !(num(a.weight) >= 0))) return "Weights must be numbers of at least 0 (long-only).";
  const sum = d.assets.reduce((s, a) => s + num(a.weight), 0);
  if (Math.abs(sum - 100) > 1e-4) return `Weights add up to ${+sum.toFixed(4)}%, not 100%. Use “Normalise weights”.`;
  if (d.assets.some((a) => !Number.isFinite(num(a.mu)) || !(num(a.sigma) >= 0))) return "Expected returns must be numbers and volatilities 0 or more.";
  if (d.corr.some((r) => r.some((x) => !(num(x) >= -1 && num(x) <= 1)))) return "Correlations must be numbers between -1 and 1.";
  if (!(num(d.initial) > 0)) return "Starting value must be positive.";
  return null;
}

const money = (x: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(x);
const tip = { background: "#17213a", border: "1px solid #334155", borderRadius: 8 };
const axis = { fill: "#94a3b8", fontSize: 11 };

function Builder({ d, set }: { d: PortfolioDraft; set: (d: PortfolioDraft) => void }) {
  const n = d.assets.length;
  const setA = (i: number, v: Partial<PortfolioDraft["assets"][number]>) => set({ ...d, assets: d.assets.map((a, j) => (j === i ? { ...a, ...v } : a)) });
  const setC = (i: number, j: number, v: string) => set({ ...d, corr: d.corr.map((r, a) => r.map((x, b) => ((a === i && b === j) || (a === j && b === i) ? v : x))) });
  const add = () => set({ ...d, assets: [...d.assets, { name: `Asset ${n + 1}`, weight: "0", mu: "5", sigma: "15" }], corr: [...d.corr.map((r) => [...r, "0"]), [...Array(n).fill("0"), "1"]] });
  const del = (i: number) => set({ ...d, assets: d.assets.filter((_, j) => j !== i), corr: d.corr.filter((_, j) => j !== i).map((r) => r.filter((_, j) => j !== i)) });
  const normalise = () => {
    const ws = d.assets.map((a) => num(a.weight));
    const s = ws.reduce((x, y) => x + (Number.isFinite(y) ? y : 0), 0);
    if (s > 0) set({ ...d, assets: d.assets.map((a, i) => ({ ...a, weight: String(+(((Number.isFinite(ws[i]) ? ws[i] : 0) / s) * 100).toFixed(4)) })) });
  };
  const sum = d.assets.reduce((s, a) => s + (Number.isFinite(num(a.weight)) ? num(a.weight) : 0), 0);
  return (
    <Panel title="1 · Portfolio assumptions" badge={<Badge tone="amber">Illustrative, not forecasts</Badge>}>
      <p className="mb-3 text-xs leading-relaxed text-muted">Expected returns, volatilities and correlations are <strong>your assumptions</strong>. The starting values are made up to show how the tools work. Portfolios are long-only and fully invested (no leverage, no shorting).</p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <caption className="sr-only">Assets and assumptions</caption>
          <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="font-normal">Asset</th><th scope="col" className="font-normal">Weight %</th><th scope="col" className="font-normal">Expected return % / yr</th><th scope="col" className="font-normal">Volatility % / yr</th><th /></tr></thead>
          <tbody>
            {d.assets.map((a, i) => (
              <tr key={i}>
                <td className="pr-2 pb-1"><input aria-label={`Asset ${i + 1} name`} value={a.name} maxLength={40} onChange={(e) => setA(i, { name: e.target.value })} className={`${field} w-full`} /></td>
                <td className="pr-2 pb-1"><input aria-label={`${a.name} weight percent`} inputMode="decimal" value={a.weight} onChange={(e) => setA(i, { weight: e.target.value })} className={`${field} w-24 font-mono`} /></td>
                <td className="pr-2 pb-1"><input aria-label={`${a.name} expected return percent`} inputMode="decimal" value={a.mu} onChange={(e) => setA(i, { mu: e.target.value })} className={`${field} w-28 font-mono`} /></td>
                <td className="pr-2 pb-1"><input aria-label={`${a.name} volatility percent`} inputMode="decimal" value={a.sigma} onChange={(e) => setA(i, { sigma: e.target.value })} className={`${field} w-28 font-mono`} /></td>
                <td>{n > 1 && <button type="button" aria-label={`Remove ${a.name}`} onClick={() => del(i)} className="rounded p-1.5 text-muted hover:text-red-300"><X className="h-4 w-4" /></button>}</td>
              </tr>))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        {n < 10 && <button type="button" onClick={add} className="inline-flex items-center gap-1 rounded-lg border border-dashed border-line px-3 py-1.5 text-xs text-muted hover:text-ink"><Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add asset</button>}
        <span className={`font-mono text-xs ${Math.abs(sum - 100) > 1e-4 ? "text-amber-300" : "text-muted"}`}>Total weight {+sum.toFixed(4)}%</span>
        {Math.abs(sum - 100) > 1e-4 && <button type="button" onClick={normalise} className="rounded border border-line px-2 py-1 text-xs hover:border-violet/60">Normalise weights</button>}
      </div>
      {n > 1 && (
        <div className="mt-4">
          <h3 className="mb-1 text-sm font-semibold">Correlations</h3>
          <div className="overflow-x-auto">
            <table className="text-sm"><caption className="sr-only">Correlation matrix (symmetric: edit either triangle)</caption>
              <thead><tr><th />{d.assets.map((a, j) => <th key={j} scope="col" className="px-1 text-[11px] font-normal text-muted">{a.name}</th>)}</tr></thead>
              <tbody>{d.assets.map((a, i) => (
                <tr key={i}><th scope="row" className="pr-2 text-right text-[11px] font-normal text-muted">{a.name}</th>
                  {d.assets.map((_, j) => <td key={j} className="p-0.5">{i === j ? <span className="block w-16 text-center font-mono text-muted">1</span> : <input aria-label={`Correlation ${a.name} and ${d.assets[j].name}`} inputMode="decimal" value={d.corr[i][j]} onChange={(e) => setC(i, j, e.target.value)} className={`${field} w-16 text-center font-mono`} />}</td>)}</tr>))}</tbody>
            </table>
          </div>
        </div>
      )}
      <div className="mt-4 max-w-xs"><label htmlFor="pf-init" className="mb-1 block text-xs text-muted">Starting value ($)</label><input id="pf-init" inputMode="decimal" value={d.initial} onChange={(e) => set({ ...d, initial: e.target.value })} className={`${field} w-full font-mono`} /></div>
    </Panel>
  );
}

function Analytics({ d }: { d: PortfolioDraft }) {
  const prob = portfolioProblem(d);
  const body = useMemo(() => (prob ? null : portfolioBody(d)), [d, prob]);
  const a = useAnalysis<FinAnalytics>("finance/portfolio", body);
  return (
    <Panel title="2 · Portfolio analytics" badge={<Badge tone="green">Exact</Badge>}>
      <div aria-live="polite">
        {prob ? <p className="text-sm text-amber-300">{prob}</p> : a.loading ? <p className="flex items-center gap-2 text-sm text-muted"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Calculating…</p>
          : a.error ? <ErrorPanel message={a.error} /> : a.data && (
            <div className="space-y-4">
              <dl className="grid grid-cols-3 gap-3">
                {([["Expected return (assumed)", pc(a.data.expected_return)], ["Volatility", pc(a.data.volatility)], ["Diversification ratio", a.data.diversification_ratio.toFixed(2)]] as const).map(([k, v]) => (
                  <div key={k} className="rounded-xl border border-line bg-card/60 p-3"><dt className="text-[11px] text-muted">{k}</dt><dd className="font-mono text-xl font-bold">{v}</dd></div>))}
              </dl>
              <div>
                <h3 className="mb-2 text-sm font-semibold">Where the risk comes from <span className="font-normal text-muted">(share of portfolio volatility vs share of money)</span></h3>
                <ul className="space-y-1.5">
                  {a.data.assets.map((x) => (
                    <li key={x.name} className="grid grid-cols-[6rem_1fr_9rem] items-center gap-2 text-sm">
                      <span className="truncate">{x.name}</span>
                      <div className="relative h-3 rounded bg-white/5" role="img" aria-label={`${x.name}: ${pc(x.weight, 0)} of money, ${pc(x.risk_contribution, 0)} of risk`}>
                        <div className="absolute inset-y-0 left-0 rounded bg-cyan/40" style={{ width: `${x.weight * 100}%` }} />
                        <div className="absolute inset-y-1 left-0 rounded bg-primary" style={{ width: `${Math.max(0, x.risk_contribution) * 100}%` }} />
                      </div>
                      <span className="font-mono text-xs text-muted">{pc(x.weight, 0)} money · {pc(x.risk_contribution, 0)} risk</span>
                    </li>))}
                </ul>
                <p className="mt-1 text-[11px] text-muted">Light bar: share of money. Dark bar: share of portfolio volatility (Euler risk contribution). Diversification ratio = weighted average stand-alone volatility ÷ portfolio volatility.</p>
              </div>
            </div>)}
      </div>
    </Panel>
  );
}

function ReturnHistogram({ h }: { h: FinMonteCarlo["terminal"]["histogram"] }) {
  const total = h.counts.reduce((a, b) => a + b, 0);
  const data = h.counts.map((c, i) => ({ x: +(((h.edges[i] + h.edges[i + 1]) / 2) * 100).toFixed(1), pct: (c / total) * 100 }));
  return (
    <div className="h-48" role="img" aria-label="Histogram of terminal portfolio returns">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} barCategoryGap={1}>
          <CartesianGrid vertical={false} stroke="rgba(148,163,184,0.12)" />
          <XAxis dataKey="x" tick={axis} axisLine={false} tickLine={false} unit="%" interval="preserveStartEnd" minTickGap={30} />
          <YAxis hide />
          <Tooltip cursor={{ fill: "rgba(255,255,255,0.04)" }} contentStyle={tip} formatter={(v) => [`${Number(v).toFixed(2)}% of runs`, ""]} labelFormatter={(l) => `Return ≈ ${l}%`} />
          <Bar dataKey="pct" fill="#8055f6" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function McPanel({ pd, mc, setMc, adv, onSaved }: { pd: PortfolioDraft; mc: McDraft; setMc: (m: McDraft) => void; adv: boolean; onSaved: () => void }) {
  const [res, setRes] = useState<FinMonteCarlo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ranKey, setRanKey] = useState<string | null>(null);
  const pf = useMemo(() => (portfolioProblem(pd) ? null : portfolioBody(pd)), [pd]);
  const confs = ([["c90", 0.9], ["c95", 0.95], ["c99", 0.99]] as const).filter(([k]) => mc.conf[k]).map(([, v]) => v);
  const optPct = (s: string) => (s.trim() === "" ? null : num(s) / 100);
  const seed = mc.seed.trim() === "" ? null : num(mc.seed);
  const body = pf && confs.length && Number.isFinite(num(mc.horizon)) && Number.isFinite(num(mc.iterations)) && (seed === null || (Number.isInteger(seed) && seed >= 0))
    ? { ...pf, horizon_years: num(mc.horizon), steps_per_year: Number(mc.steps), iterations: num(mc.iterations), rebalance: mc.rebalance, tails: mc.tails, df: num(mc.df) || 5, seed,
        confidences: confs, loss_threshold: optPct(mc.lossThreshold), drawdown_threshold: optPct(mc.ddThreshold) } : null;

  async function run() {
    if (!body) return;
    setBusy(true); setErr(null);
    try { setRes(await post<FinMonteCarlo>("finance/montecarlo", body)); setRanKey(JSON.stringify(body)); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); setRes(null); } finally { setBusy(false); }
  }
  const stale = !!res && ranKey !== JSON.stringify(body);
  return (
    <>
      <Panel title="3 · Monte Carlo risk simulation">
        <p className="mb-3 text-xs leading-relaxed text-muted">Simulates many possible futures under your assumptions (lognormal returns, constant volatility and correlation) and reports the spread of outcomes. Same seed, same results.</p>
        <div className="grid gap-3 sm:grid-cols-4">
          <div><label htmlFor="mc-h" className="mb-1 block text-xs text-muted">Horizon (years)</label><input id="mc-h" inputMode="decimal" value={mc.horizon} onChange={(e) => setMc({ ...mc, horizon: e.target.value })} className={`${field} w-full font-mono`} /></div>
          <div><label htmlFor="mc-steps" className="mb-1 block text-xs text-muted">Steps per year</label><select id="mc-steps" value={mc.steps} onChange={(e) => setMc({ ...mc, steps: e.target.value as McDraft["steps"] })} className={`${field} w-full`}><option value="4">4 (quarterly)</option><option value="12">12 (monthly)</option><option value="52">52 (weekly)</option></select></div>
          <div><label htmlFor="mc-it" className="mb-1 block text-xs text-muted">Simulations</label><select id="mc-it" value={mc.iterations} onChange={(e) => setMc({ ...mc, iterations: e.target.value })} className={`${field} w-full`}>{["1000", "5000", "10000", "20000"].map((v) => <option key={v} value={v}>{Number(v).toLocaleString()}</option>)}</select></div>
          <div><label htmlFor="mc-seed" className="mb-1 block text-xs text-muted">Seed</label><input id="mc-seed" inputMode="numeric" value={mc.seed} placeholder="random (recorded)" onChange={(e) => setMc({ ...mc, seed: e.target.value })} className={`${field} w-full font-mono`} /></div>
          <div><label htmlFor="mc-reb" className="mb-1 block text-xs text-muted">Rebalancing</label><select id="mc-reb" value={mc.rebalance} onChange={(e) => setMc({ ...mc, rebalance: e.target.value as McDraft["rebalance"] })} className={`${field} w-full`}><option value="every_step">Back to target weights each step</option><option value="none">Buy and hold</option></select></div>
          <div><label htmlFor="mc-tails" className="mb-1 block text-xs text-muted">Shock distribution</label><select id="mc-tails" value={mc.tails} onChange={(e) => setMc({ ...mc, tails: e.target.value as McDraft["tails"] })} className={`${field} w-full`}><option value="normal">Normal</option><option value="student_t">Fat-tailed (Student-t)</option></select></div>
          {mc.tails === "student_t" && <div><label htmlFor="mc-df" className="mb-1 block text-xs text-muted">Degrees of freedom (3–100)</label><input id="mc-df" inputMode="decimal" value={mc.df} onChange={(e) => setMc({ ...mc, df: e.target.value })} className={`${field} w-full font-mono`} /></div>}
          <div><label htmlFor="mc-loss" className="mb-1 block text-xs text-muted">Track P(loss &gt; …%)</label><input id="mc-loss" inputMode="decimal" value={mc.lossThreshold} placeholder="optional" onChange={(e) => setMc({ ...mc, lossThreshold: e.target.value })} className={`${field} w-full font-mono`} /></div>
          <div><label htmlFor="mc-dd" className="mb-1 block text-xs text-muted">Track P(drawdown &gt; …%)</label><input id="mc-dd" inputMode="decimal" value={mc.ddThreshold} placeholder="optional" onChange={(e) => setMc({ ...mc, ddThreshold: e.target.value })} className={`${field} w-full font-mono`} /></div>
        </div>
        <fieldset className="mt-3"><legend className="mb-1 text-xs text-muted">VaR / ES confidence levels</legend>
          <div className="flex gap-4 text-sm">{([["c90", "90%"], ["c95", "95%"], ["c99", "99%"]] as const).map(([k, l]) => <label key={k} className="flex items-center gap-2"><input type="checkbox" checked={mc.conf[k]} onChange={(e) => setMc({ ...mc, conf: { ...mc.conf, [k]: e.target.checked } })} className="h-4 w-4 accent-[#8055f6]" />{l}</label>)}</div></fieldset>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button type="button" onClick={run} disabled={!body || busy} className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Run simulation</button>
          {!pf && <span className="text-xs text-amber-300">Fix the portfolio above first.</span>}
          {!confs.length && <span className="text-xs text-amber-300">Choose at least one confidence level.</span>}
        </div>
        {err && <div className="mt-3"><ErrorPanel message={err} /></div>}
      </Panel>

      {res && (
        <Panel title="4 · Results" badge={<Badge tone="amber">Scenario, not a forecast</Badge>}>
          <div className="space-y-5">
            {stale && <p role="status" className="rounded-lg border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-sm text-amber-200">Your inputs have changed since this run. Press “Run simulation” to refresh these results.</p>}
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {([["Median value", money(res.terminal.median_value)], ["5th – 95th percentile", `${money(res.terminal.p5_value)} – ${money(res.terminal.p95_value)}`], ["Chance of ending lower", pc(res.p_loss)], ["Average worst drawdown", pc(res.max_drawdown.mean)]] as const).map(([k, v]) => (
                <div key={k} className="rounded-xl border border-line bg-card/60 p-3"><dt className="text-[11px] text-muted">{k}</dt><dd className="font-mono text-base font-bold sm:text-lg">{v}</dd></div>))}
            </dl>
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <h3 className="mb-1 text-sm font-semibold">Range of portfolio values over time</h3>
                <div className="h-56" role="img" aria-label="Fan chart of the 5th, 25th, 50th, 75th and 95th percentile portfolio value over time">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={res.fan}>
                      <CartesianGrid vertical={false} stroke="rgba(148,163,184,0.12)" />
                      <XAxis dataKey="t" type="number" domain={[0, "dataMax"]} tick={axis} axisLine={false} tickLine={false} tickFormatter={(v) => `${Number(v).toFixed(1)}y`} />
                      <YAxis tick={axis} axisLine={false} tickLine={false} width={56} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                      <Tooltip contentStyle={tip} formatter={(v, n) => [money(Number(v)), String(n)]} labelFormatter={(l) => `Year ${Number(l).toFixed(2)}`} />
                      <Line dataKey="p95" name="95th" stroke="#22d3ee" strokeWidth={1.5} dot={false} />
                      <Line dataKey="p75" name="75th" stroke="#22d3ee" strokeOpacity={0.5} strokeWidth={1} dot={false} />
                      <Line dataKey="p50" name="median" stroke="#a78bfa" strokeWidth={2.5} dot={false} />
                      <Line dataKey="p25" name="25th" stroke="#f59e0b" strokeOpacity={0.6} strokeWidth={1} dot={false} />
                      <Line dataKey="p05" name="5th" stroke="#f59e0b" strokeWidth={1.5} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
              <div><h3 className="mb-1 text-sm font-semibold">Distribution of final returns</h3><ReturnHistogram h={res.terminal.histogram} /></div>
            </div>
            <div className="overflow-x-auto">
              <h3 className="mb-1 text-sm font-semibold">Value at Risk and Expected Shortfall <span className="font-normal text-muted">(loss over the whole {res.horizon_years.toFixed(1)}-year horizon, as % and $ of the starting value)</span></h3>
              <table className="w-full min-w-[460px] text-sm"><caption className="sr-only">Value at Risk and Expected Shortfall</caption>
                <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="font-normal">Confidence</th><th scope="col" className="font-normal">VaR</th><th scope="col" className="font-normal">Expected Shortfall</th>{adv && <><th scope="col" className="font-normal">Normal approx. VaR</th><th scope="col" className="font-normal">Normal approx. ES</th><th scope="col" className="font-normal">Tail runs</th></>}</tr></thead>
                <tbody className="font-mono">{res.risk.map((r) => (
                  <tr key={r.confidence} className="border-t border-line"><td className="py-1 font-sans">{pc(r.confidence, 0)}</td>
                    <td>{pc(r.mc_var)} <span className="text-[11px] text-muted">{money(r.mc_var * res.initial_value)}</span></td><td>{pc(r.mc_es)} <span className="text-[11px] text-muted">{money(r.mc_es * res.initial_value)}</span></td>
                    {adv && <><td>{pc(r.approx_normal_var)}</td><td>{pc(r.approx_normal_es)}</td><td>{r.tail_observations}</td></>}</tr>))}</tbody></table>
              <p className="mt-2 text-[11px] leading-relaxed text-muted">VaR: the loss exceeded in only (1 − confidence) of simulated futures. Expected Shortfall: the average loss in those worst futures. Both describe your assumed model, so they are only as good as those assumptions.</p>
            </div>
            {(res.p_loss_exceeds || res.max_drawdown.p_exceeds) && (
              <p className="text-sm text-muted">
                {res.p_loss_exceeds && <>Chance of ending more than <strong className="text-ink">{pc(res.p_loss_exceeds.threshold, 0)}</strong> below the start: <strong className="text-ink">{pc(res.p_loss_exceeds.p)}</strong>. </>}
                {res.max_drawdown.p_exceeds && <>Chance of a drawdown deeper than <strong className="text-ink">{pc(res.max_drawdown.p_exceeds.threshold, 0)}</strong> at some point: <strong className="text-ink">{pc(res.max_drawdown.p_exceeds.p)}</strong>.</>}
              </p>)}
            <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted">{res.notes.map((n) => <li key={n}>{n}</li>)}</ul>
            {adv && (
              <div className="space-y-2 border-t border-line pt-4 text-xs text-muted">
                <p>Model check: {res.terminal.analytic_mean_value === null ? "exact expected value is not defined for fat-tailed shocks." : <>exact expected final value {money(res.terminal.analytic_mean_value)}; simulated mean {money(res.terminal.mean_value)} ± {money(1.96 * res.terminal.se_mean_value)} (95%).</>}</p>
                <p>Provenance: seed {res.seed} · {res.iterations.toLocaleString()} simulations × {res.steps} steps · engine {res.engine_version} on Python {res.python_version} · {res.runtime_ms} ms · hash {res.result_hash.slice(0, 16)}…</p>
              </div>)}
          </div>
        </Panel>
      )}
      <Panel title="Save this scenario"><ScenarioSaveBar endpoint="finance/scenarios" kind="montecarlo" inputs={body} valid={!!body} onSaved={onSaved} /></Panel>
    </>
  );
}

export function PortfolioMC({ pd, setPd, mc, setMc, adv, onSaved }: { pd: PortfolioDraft; setPd: (d: PortfolioDraft) => void; mc: McDraft; setMc: (m: McDraft) => void; adv: boolean; onSaved: () => void }) {
  return (
    <div className="space-y-4">
      <Builder d={pd} set={setPd} />
      <Analytics d={pd} />
      <McPanel pd={pd} mc={mc} setMc={setMc} adv={adv} onSaved={onSaved} />
    </div>
  );
}
