"use client";

import { useMemo, useState } from "react";
import { BASELINE, MAJORITY, NATIONAL_NOISE, PARTIES, REGIONAL_NOISE, REGIONS, TURNOUT_ELASTICITY, project, type Scenario } from "@/lib/landing/politics";
import { ElectionMap } from "../visualizations/ElectionMap";
import { SeatChart } from "../visualizations/SeatChart";

const Tag = ({ tone, children }: { tone: "forecast" | "scenario" | "history"; children: string }) => (
  <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${tone === "forecast" ? "border-azure/50 bg-azure/10 text-blue-200" : tone === "scenario" ? "border-amber-300/50 bg-amber-300/10 text-amber-200" : "border-slate-400/40 bg-slate-400/10 text-slate-300"}`}>{children}</span>
);
const signed = (n: number) => (n > 0 ? `+${n}` : n < 0 ? `−${Math.abs(n)}` : "0");

/** The political demonstration for a fictional country: a baseline projection, your hypothetical adjustments, and a fictional previous election. */
export default function PoliticsPanel() {
  const [turnout, setTurnout] = useState(0);
  const [region, setRegion] = useState<string | null>(null);
  const [swing, setSwing] = useState(0);
  const [coalition, setCoalition] = useState<string[]>(BASELINE.coalition);
  const scenario: Scenario = useMemo(() => ({ turnoutShift: turnout, swingRegion: region, swing, coalition }), [turnout, region, swing, coalition]);
  const baseline = useMemo(() => project({ ...BASELINE, coalition }), [coalition]);
  const out = useMemo(() => project(scenario), [scenario]);
  const changed = turnout !== 0 || (region !== null && swing !== 0);
  const sel = region ? out.regions.find((r) => r.region.id === region) : null;
  const selBase = region ? baseline.regions.find((r) => r.region.id === region) : null;
  const nationalTurnout = REGIONS.reduce((s, r) => s + (r.turnout + turnout / 100) * r.seats, 0) / REGIONS.reduce((s, r) => s + r.seats, 0);
  const baseTurnout = REGIONS.reduce((s, r) => s + r.turnout * r.seats, 0) / REGIONS.reduce((s, r) => s + r.seats, 0);
  const toggle = (id: string) => setCoalition((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
  const reset = () => { setTurnout(0); setRegion(null); setSwing(0); };

  return (
    <div className="grid gap-5 lg:grid-cols-12">
      <div className="glass rounded-3xl p-5 lg:col-span-5">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-bold">Electoral map</h3><Tag tone={changed ? "scenario" : "forecast"}>{changed ? "Hypothetical scenario" : "Simulated forecast"}</Tag></div>
        <ElectionMap regions={out.regions} selected={region} onSelect={(id) => { setRegion(id); if (!id) setSwing(0); }} />
        <p className="mt-1 text-[11px] leading-relaxed text-muted">A schematic map of a fictional country. Colour shows the leading party and how strong its lead is; the letter and seat count are written in each region. Select a region to apply a swing to it.</p>
        <div className="mt-4 space-y-4 border-t border-line pt-4">
          <div>
            <label htmlFor="po-turnout" className="flex justify-between text-xs text-muted"><span>National turnout change</span><span className="font-mono text-ink">{signed(turnout)} pts → {(nationalTurnout * 100).toFixed(1)}%</span></label>
            <input id="po-turnout" type="range" min={-10} max={10} step={1} value={turnout} onChange={(e) => setTurnout(Number(e.target.value))} className="w-full accent-[#60A5FA]" />
            <p className="text-[11px] text-muted">Baseline turnout {(baseTurnout * 100).toFixed(1)}%. Assumption: each party&apos;s voters respond to turnout differently (elasticity A {TURNOUT_ELASTICITY[0]}, B {TURNOUT_ELASTICITY[1]}, C {TURNOUT_ELASTICITY[2]}, D {TURNOUT_ELASTICITY[3]}).</p>
          </div>
          <div>
            <label htmlFor="po-region" className="mb-1 block text-xs text-muted">Regional swing in</label>
            <select id="po-region" value={region ?? ""} onChange={(e) => { setRegion(e.target.value || null); if (!e.target.value) setSwing(0); }} className="w-full rounded-xl border border-line bg-night/70 px-3 py-2 text-sm focus:border-azure focus:outline-none focus:ring-2 focus:ring-azure/40">
              <option value="">No regional swing</option>
              {REGIONS.map((r) => <option key={r.id} value={r.id}>{r.name} ({r.seats} seats)</option>)}
            </select>
            <label htmlFor="po-swing" className="mt-3 flex justify-between text-xs text-muted"><span>Vote moving between Party A and Party B</span><span className="font-mono text-ink">{swing > 0 ? `${swing} pts A→B` : swing < 0 ? `${-swing} pts B→A` : "none"}</span></label>
            <input id="po-swing" type="range" min={-10} max={10} step={1} value={swing} disabled={!region} onChange={(e) => setSwing(Number(e.target.value))} className="w-full accent-[#60A5FA] disabled:opacity-40" />
          </div>
          <fieldset>
            <legend className="mb-1.5 text-xs text-muted">Coalition assumption</legend>
            <div className="flex flex-wrap gap-2">
              {PARTIES.map((p) => (
                <label key={p.id} className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-1.5 text-xs ${coalition.includes(p.id) ? "border-white/40 bg-white/10" : "border-line text-muted"}`}>
                  <input type="checkbox" checked={coalition.includes(p.id)} onChange={() => toggle(p.id)} className="accent-[#60A5FA]" />
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: p.colour }} aria-hidden="true" />{p.name}
                </label>
              ))}
            </div>
          </fieldset>
          <button type="button" onClick={reset} disabled={!changed} className="rounded-lg border border-line px-3 py-1.5 text-xs text-muted hover:text-ink disabled:opacity-40">Reset assumptions</button>
        </div>
      </div>

      <div className="space-y-5 lg:col-span-7">
        <div className="glass rounded-3xl p-5">
          <div className="mb-3 flex flex-wrap items-center gap-2"><h3 className="text-sm font-bold">Seat projection ({MAJORITY} of 100 needed)</h3></div>
          <div className="space-y-4" aria-live="polite">
            <div><div className="mb-1"><Tag tone="history">Fictional previous election</Tag></div><SeatChart seats={out.previous} label="Previous election (fictional)" /></div>
            <div><div className="mb-1"><Tag tone="forecast">Simulated baseline forecast</Tag></div><SeatChart seats={baseline.totals} label="Baseline forecast" /></div>
            {changed && <div><div className="mb-1"><Tag tone="scenario">Your hypothetical scenario</Tag></div><SeatChart seats={out.totals} label="Scenario" /></div>}
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-xs">
              <caption className="sr-only">Seats by party: previous election, baseline forecast with range, and scenario</caption>
              <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="font-normal">Party</th><th scope="col" className="font-normal">Previous (fictional)</th><th scope="col" className="font-normal">Baseline forecast</th><th scope="col" className="font-normal">Range (10th–90th)</th>{changed && <th scope="col" className="font-normal">Scenario</th>}</tr></thead>
              <tbody className="font-mono">
                {PARTIES.map((p, i) => (
                  <tr key={p.id} className="border-t border-line">
                    <th scope="row" className="py-1.5 text-left font-sans font-medium"><span className="mr-2 inline-block h-2.5 w-2.5 rounded-full" style={{ background: p.colour }} aria-hidden="true" />{p.name}</th>
                    <td>{out.previous[i]}</td><td>{baseline.totals[i]} <span className="text-muted">({signed(baseline.totals[i] - out.previous[i])})</span></td><td className="text-muted">{baseline.ranges[i].p10}–{baseline.ranges[i].p90}</td>
                    {changed && <td className="font-semibold">{out.totals[i]} <span className="font-normal text-muted">({signed(out.totals[i] - baseline.totals[i])})</span></td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-muted">Ranges come from 400 simulated elections with random shocks to each party nationally (±{NATIONAL_NOISE * 100}%) and in each region (±{REGIONAL_NOISE * 100}%), using a fixed seed so the page is repeatable. They show how sensitive the projection is to modest errors, not a probability of any real outcome.</p>
        </div>

        <div className="grid gap-5 md:grid-cols-2">
          <div className="glass rounded-3xl p-5">
            <div className="mb-2 flex items-center justify-between gap-2"><h3 className="text-sm font-bold">Coalition scenario</h3><Tag tone={changed ? "scenario" : "forecast"}>{changed ? "Hypothetical" : "Simulated forecast"}</Tag></div>
            {coalition.length === 0 ? <p className="text-sm text-muted">Choose at least one party above.</p> : (
              <>
                <p className="text-sm leading-relaxed" aria-live="polite">{coalition.map((id) => `Party ${id}`).join(" + ")} would hold <strong className="font-mono">{out.coalition.seats}</strong> of 100 seats ({out.coalition.hasMajority ? "a majority" : `${MAJORITY - out.coalition.seats} short of a majority`}).</p>
                <div className="mt-3 rounded-xl border border-line p-3 text-center"><div className="font-mono text-2xl font-bold">{Math.round(out.coalition.probabilityOfMajority * 100)}%</div><div className="text-[11px] text-muted">of the 400 simulated elections give this coalition a majority{changed ? ` (baseline ${Math.round(baseline.coalition.probabilityOfMajority * 100)}%)` : ""}</div></div>
              </>
            )}
          </div>
          <div className="glass rounded-3xl p-5">
            <h3 className="mb-2 text-sm font-bold">{sel ? `${sel.region.name}` : "Regional analysis"}</h3>
            {sel && selBase ? (
              <table className="w-full text-xs">
                <caption className="sr-only">Vote shares and seats in {sel.region.name}</caption>
                <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="font-normal">Party</th><th scope="col" className="font-normal">Baseline vote</th><th scope="col" className="font-normal">Scenario vote</th><th scope="col" className="font-normal">Seats</th></tr></thead>
                <tbody className="font-mono">
                  {PARTIES.map((p, i) => <tr key={p.id} className="border-t border-line"><th scope="row" className="py-1 text-left font-sans font-medium">{p.id}</th><td>{(selBase.shares[i] * 100).toFixed(1)}%</td><td>{(sel.shares[i] * 100).toFixed(1)}%</td><td>{sel.seats[i]} <span className="text-muted">({signed(sel.seats[i] - selBase.seats[i])})</span></td></tr>)}
                </tbody>
              </table>
            ) : <p className="text-xs leading-relaxed text-muted">Select a region on the map to see its vote shares and seats, and to apply a swing there.</p>}
          </div>
        </div>

        <div role="note" className="rounded-2xl border border-line bg-night2/60 p-4 text-xs leading-relaxed text-muted">
          <strong className="text-ink">Read this as an illustration.</strong> The country, regions, parties and every vote share are invented, and parties are neutral labels. Seats in each region are allocated by the D&apos;Hondt method. <strong className="text-ink">Historical facts:</strong> none are shown, because a fictional country has no election history; the &ldquo;previous election&rdquo; is also invented. Nothing here predicts or favours any real party or election.
        </div>
      </div>
    </div>
  );
}
