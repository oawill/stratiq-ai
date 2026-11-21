"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, Plus, RotateCcw, Trash2 } from "lucide-react";
import { call, post } from "@/lib/client";
import { Badge, ErrorPanel, Panel, dt, pct } from "../ui";
import { field } from "../analysis";
import { NoHistory, ProbBar } from "../sports/FootballMatch";

export interface Adj { key: string; label: string; min: number; max: number; neutral: number; meaning: string }
interface Ctx { has_history: boolean; teams: string[]; fixtures: { date: string; home: string; away: string }[]; settings_tuned: boolean; history_through: string | null }
interface AdjInfo { adjustments: Adj[]; documentation: string; model_version: string; max_scenarios: number }
interface Score { name: string; percent: number[]; probs: number[]; expected_goals: number[]; p_over_2_5: number; p_btts: number; top_scorelines: { home: number; away: number; p: number }[]; score_grid: number[][]; grid_tail: number; grid_goals: number }
export interface ScenarioOut extends Score { adjustments: Record<string, number>; changed: string[]; delta_vs_baseline: { p_home: number; p_draw: number; p_away: number; expected_goals_home: number; expected_goals_away: number; p_over_2_5: number; p_btts: number } }
export interface SimResult {
  id: string; title: string; version: number; scenario_key: string; created_at: string;
  matchup: { home: string; away: string; scheduled: boolean; fixture_date: string | null; label: string };
  baseline: Score & { status: string }; scenarios: ScenarioOut[];
  calibrated_parameters: { name: string; value: number | string }[];
  provenance: { model: string; model_version: string; base_model: string; settings_tuned: boolean; data_sha256: string; training_cutoff: string; data_through: string; matches_used: number; generated_at: string; deterministic: boolean; random_seed: number | null };
  documentation: string; validation_status: string; label: string;
}

const GROUPS: { title: string; note: string; keys: string[] }[] = [
  { title: "Team strength", note: "Multipliers on the strengths the model estimated from the data.", keys: ["home_attack_multiplier", "away_attack_multiplier", "home_defence_multiplier", "away_defence_multiplier", "home_advantage_multiplier"] },
  { title: "Game state", note: "How open the game is.", keys: ["tempo_multiplier"] },
  { title: "Availability (your assumption)", note: "Shares of attack or defence you assume are missing. These are guesses, not estimates from data.", keys: ["home_missing_attack_loss", "away_missing_attack_loss", "home_missing_defence_loss", "away_missing_defence_loss"] },
];
const fmtVal = (a: Adj, v: number) => (a.max <= 0.5 ? `${(v * 100).toFixed(0)}%` : `${v.toFixed(2)}×`);
const signed = (v: number, d = 1) => `${v >= 0 ? "+" : ""}${v.toFixed(d)}`;

/** The score distribution as a table: every cell is the probability of that exact scoreline. Shading follows the number, it is not decoration. */
export function ScoreGrid({ s, home, away }: { s: Score; home: string; away: string }) {
  const max = Math.max(...s.score_grid.flat());
  return (
    <div className="overflow-x-auto">
      <table className="border-separate border-spacing-0.5 text-center text-[11px]">
        <caption className="mb-1 text-left text-xs text-muted">Chance of each exact score: {home} goals down, {away} goals across. The remaining {pct(s.grid_tail, 2)} is spread over higher scores.</caption>
        <thead><tr><td />{s.score_grid[0].map((_, a) => <th key={a} scope="col" className="px-1 font-normal text-muted">{a}</th>)}</tr></thead>
        <tbody>{s.score_grid.map((row, h) => (
          <tr key={h}><th scope="row" className="pr-1 text-right font-normal text-muted">{h}</th>
            {row.map((v, a) => <td key={a} title={`${home} ${h} – ${a} ${away}: ${pct(v, 2)}`} className="h-8 w-11 rounded font-mono" style={{ background: `rgba(0,229,255,${(0.04 + 0.6 * (v / max)).toFixed(3)})` }}>{(v * 100).toFixed(1)}</td>)}</tr>
        ))}</tbody>
      </table>
    </div>
  );
}

/** First functional SimLab model: change assumptions about a fixture and see what the Poisson-family model would say, next to the data-calibrated baseline. */
export function SportsSimulator({ onSaved }: { onSaved?: () => void }) {
  const [ctx, setCtx] = useState<Ctx | null>(null);
  const [info, setInfo] = useState<AdjInfo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [mode, setMode] = useState<"hypothetical" | "fixture">("hypothetical");
  const [home, setHome] = useState("");
  const [away, setAway] = useState("");
  const [fixture, setFixture] = useState("");
  const [title, setTitle] = useState("");
  const [scen, setScen] = useState<{ name: string; vals: Record<string, number> }[]>([{ name: "Scenario 1", vals: {} }]);
  const [result, setResult] = useState<SimResult | null>(null);
  const [asVersion, setAsVersion] = useState(true);
  const [view, setView] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    Promise.all([call<Ctx>("simlab/sports/context"), call<AdjInfo>("simlab/sports/adjustments")]).then(([c, a]) => { if (live) { setCtx(c); setInfo(a); } }, (e) => live && setErr(e instanceof Error ? e.message : "Could not load the simulator."));
    return () => { live = false; };
  }, []);
  const byKey = useMemo(() => Object.fromEntries((info?.adjustments ?? []).map((a) => [a.key, a])), [info]);

  if (err && !ctx) return <ErrorPanel message={err} />;
  if (!ctx || !info) return <p className="text-sm text-muted" aria-busy="true">Loading the simulator…</p>;
  if (!ctx.has_history) return <NoHistory />;

  const pickedFixture = ctx.fixtures.find((f) => `${f.date}|${f.home}|${f.away}` === fixture);
  const chosenHome = mode === "fixture" ? pickedFixture?.home : home;
  const chosenAway = mode === "fixture" ? pickedFixture?.away : away;
  const ready = !!chosenHome && !!chosenAway && chosenHome !== chosenAway;

  async function run() {
    setBusy(true); setErr(null);
    try {
      const body = {
        title: title.trim() || undefined, home: chosenHome, away: chosenAway, fixture_date: mode === "fixture" ? pickedFixture?.date : undefined,
        based_on: asVersion && result && result.matchup.home === chosenHome && result.matchup.away === chosenAway ? result.id : undefined,
        scenarios: scen.map((s) => ({ name: s.name.trim() || "Scenario", adjustments: s.vals })),
      };
      const r = await post<SimResult>("simlab/sports/run", body);
      setResult(r); setView(0); onSaved?.();
    } catch (e) { setErr(e instanceof Error ? e.message : "The simulation failed."); } finally { setBusy(false); }
  }
  const setVal = (i: number, key: string, v: number) => setScen((all) => all.map((s, j) => (j === i ? { ...s, vals: { ...s.vals, [key]: v } } : s)));
  const changedKeys = (vals: Record<string, number>) => Object.keys(vals).filter((k) => byKey[k] && vals[k] !== byKey[k].neutral);

  return (
    <div className="space-y-4">
      <Panel title="Sports simulator" badge={<Badge tone="amber">Hypothetical, not a forecast</Badge>}>
        <p className="text-xs leading-relaxed text-muted">{info.documentation}</p>
        <div className="mt-3 inline-flex rounded-xl border border-line p-1 text-sm" role="radiogroup" aria-label="Matchup type">
          {([["hypothetical", "Hypothetical matchup"], ["fixture", "Imported upcoming fixture"]] as const).map(([id, label]) => (
            <button key={id} type="button" role="radio" aria-checked={mode === id} onClick={() => { setMode(id); setResult(null); }} className={`rounded-lg px-3 py-1.5 font-semibold ${mode === id ? "bg-primary text-white" : "text-muted hover:text-ink"}`}>{label}</button>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          {mode === "hypothetical" ? (
            <>
              <div><label htmlFor="sl-home" className="mb-1 block text-xs text-muted">Home club</label><select id="sl-home" value={home} onChange={(e) => { setHome(e.target.value); setResult(null); }} className={field}><option value="">Choose…</option>{ctx.teams.map((t) => <option key={t} value={t}>{t}</option>)}</select></div>
              <div><label htmlFor="sl-away" className="mb-1 block text-xs text-muted">Away club</label><select id="sl-away" value={away} onChange={(e) => { setAway(e.target.value); setResult(null); }} className={field}><option value="">Choose…</option>{ctx.teams.filter((t) => t !== home).map((t) => <option key={t} value={t}>{t}</option>)}</select></div>
            </>
          ) : (
            <div><label htmlFor="sl-fixture" className="mb-1 block text-xs text-muted">Upcoming fixture</label>
              <select id="sl-fixture" value={fixture} onChange={(e) => { setFixture(e.target.value); setResult(null); }} className={field} disabled={ctx.fixtures.length === 0}><option value="">{ctx.fixtures.length === 0 ? "No upcoming fixtures imported" : "Choose a fixture…"}</option>{ctx.fixtures.map((f) => <option key={`${f.date}|${f.home}|${f.away}`} value={`${f.date}|${f.home}|${f.away}`}>{f.home} v {f.away} ({f.date})</option>)}</select></div>
          )}
          <div><label htmlFor="sl-title" className="mb-1 block text-xs text-muted">Name this simulation (optional)</label><input id="sl-title" value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} className={field} placeholder={chosenHome && chosenAway ? `${chosenHome} v ${chosenAway}` : ""} /></div>
        </div>
        <p className="mt-2 text-xs text-muted">{mode === "hypothetical" ? "A hypothetical matchup is any pairing of clubs in your imported history. It is not presented as a scheduled match." : "Only fixtures from fixtures files you imported are listed."} The baseline uses matches up to {ctx.history_through}, {ctx.settings_tuned ? "with settings tuned by your latest backtest." : "with default settings (no backtest has been run, so nothing is tuned)."}</p>
      </Panel>

      {scen.map((s, i) => (
        <Panel key={i} title={`Scenario ${i + 1}`} badge={<Badge tone="amber">Speculative assumptions</Badge>}>
          <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
            <div><label htmlFor={`sc-name-${i}`} className="mb-1 block text-xs text-muted">Scenario name</label><input id={`sc-name-${i}`} value={s.name} maxLength={60} onChange={(e) => setScen((all) => all.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} className={field} /></div>
            <div className="flex gap-2">
              <button type="button" onClick={() => setScen((all) => all.map((x, j) => (j === i ? { ...x, vals: {} } : x)))} className="inline-flex items-center gap-1 rounded-lg border border-line px-3 py-1.5 text-xs text-muted hover:text-ink"><RotateCcw className="h-3.5 w-3.5" aria-hidden="true" /> Reset</button>
              {scen.length > 1 && <button type="button" onClick={() => setScen((all) => all.filter((_, j) => j !== i))} aria-label={`Remove scenario ${i + 1}`} className="inline-flex items-center gap-1 rounded-lg border border-line px-3 py-1.5 text-xs text-muted hover:text-red-300"><Trash2 className="h-3.5 w-3.5" aria-hidden="true" /> Remove</button>}
            </div>
          </div>
          <div className="space-y-4">
            {GROUPS.map((g) => (
              <fieldset key={g.title} className="rounded-lg border border-line p-3">
                <legend className="px-1 text-xs font-semibold">{g.title}</legend>
                <p className="mb-2 text-[11px] text-muted">{g.note}</p>
                <div className="grid gap-3 sm:grid-cols-2">
                  {g.keys.map((k) => { const a = byKey[k]; if (!a) return null; const v = s.vals[k] ?? a.neutral;
                    return (
                      <div key={k}>
                        <label htmlFor={`sc-${i}-${k}`} className="flex justify-between text-xs text-muted"><span>{a.label}</span><span className={`font-mono ${v !== a.neutral ? "text-amber-200" : "text-ink"}`}>{fmtVal(a, v)}</span></label>
                        <input id={`sc-${i}-${k}`} type="range" min={a.min} max={a.max} step={a.max <= 0.5 ? 0.05 : 0.05} value={v} aria-valuetext={fmtVal(a, v)} onChange={(e) => setVal(i, k, Number(e.target.value))} className="w-full" />
                        <p className="text-[11px] text-muted">{a.meaning}</p>
                      </div>
                    ); })}
                </div>
              </fieldset>
            ))}
          </div>
          <p className="mt-2 text-xs text-muted">{changedKeys(s.vals).length === 0 ? "No assumption changed: this scenario will equal the baseline." : `${changedKeys(s.vals).length} assumption${changedKeys(s.vals).length === 1 ? "" : "s"} changed from neutral. Nothing about these changes has been validated.`}</p>
        </Panel>
      ))}

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" disabled={!ready || busy} onClick={run} className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Run simulation</button>
        {scen.length < info.max_scenarios && <button type="button" onClick={() => setScen((all) => [...all, { name: `Scenario ${all.length + 1}`, vals: {} }])} className="inline-flex items-center gap-2 rounded-xl border border-violet/60 px-4 py-2.5 text-sm font-semibold text-violet hover:bg-violet/10"><Plus className="h-4 w-4" aria-hidden="true" /> Add a scenario ({scen.length} of {info.max_scenarios})</button>}
        {result && <label className="inline-flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={asVersion} onChange={(e) => setAsVersion(e.target.checked)} /> Save as a new version of the last run</label>}
        {!ready && <span className="text-xs text-muted">Choose two different clubs{mode === "fixture" ? " (or a fixture)" : ""} to run.</span>}
      </div>
      {err && <p role="alert" className="text-sm text-red-300">{err}</p>}
      {result && <Results r={result} view={view} setView={setView} />}
    </div>
  );
}

function Results({ r, view, setView }: { r: SimResult; view: number; setView: (n: number) => void }) {
  const all: (Score & { delta?: ScenarioOut["delta_vs_baseline"]; changed?: string[]; adjustments?: Record<string, number> })[] = [{ ...r.baseline }, ...r.scenarios.map((s) => ({ ...s, delta: s.delta_vs_baseline }))];
  const sel = all[view] ?? all[0];
  const { home, away } = r.matchup;
  return (
    <div className="space-y-4" aria-live="polite">
      <Panel title={`${home} v ${away}`} badge={<Badge tone={r.matchup.scheduled ? "green" : "violet"}>{r.matchup.scheduled ? `Scheduled fixture ${r.matchup.fixture_date}` : "Hypothetical matchup"}</Badge>}>
        <p className="text-xs text-muted">{r.matchup.label} Saved as “{r.title}”, version {r.version}, {dt(r.created_at)}.</p>
        <div className="mt-3 space-y-3">
          <div><p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Baseline: calibrated from your data</p><ProbBar h={r.baseline.probs[0]} d={r.baseline.probs[1]} a={r.baseline.probs[2]} home={home} away={away} /></div>
          {r.scenarios.map((s) => (
            <div key={s.name} className="rounded-xl border-2 border-dashed border-amber-400/60 p-3">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-amber-200">{s.name}: hypothetical, not a forecast</p>
              <ProbBar h={s.probs[0]} d={s.probs[1]} a={s.probs[2]} home={home} away={away} />
              <p className="mt-1 font-mono text-xs">{home} win {signed(s.delta_vs_baseline.p_home)} · draw {signed(s.delta_vs_baseline.p_draw)} · {away} win {signed(s.delta_vs_baseline.p_away)} percentage points vs baseline</p>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Scenario vs baseline">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Outcome probabilities, expected goals and markets for the baseline and each scenario</caption>
            <thead><tr className="text-left text-[11px] text-muted">{["", `${home} win`, "Draw", `${away} win`, `xG ${home}`, `xG ${away}`, "Over 2.5", "Both score"].map((h, i) => <th key={i} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
            <tbody className="font-mono">
              {all.map((s, i) => (
                <tr key={s.name} className="border-t border-line">
                  <th scope="row" className="py-1.5 pr-3 text-left font-sans font-medium">{s.name}</th>
                  {s.percent.map((p, k) => <td key={k} className="pr-3">{p.toFixed(1)}%{s.delta && <span className="ml-1 text-[10px] text-muted">({signed([s.delta.p_home, s.delta.p_draw, s.delta.p_away][k])})</span>}</td>)}
                  <td className="pr-3">{s.expected_goals[0].toFixed(2)}{s.delta && <span className="ml-1 text-[10px] text-muted">({signed(s.delta.expected_goals_home, 2)})</span>}</td>
                  <td className="pr-3">{s.expected_goals[1].toFixed(2)}{s.delta && <span className="ml-1 text-[10px] text-muted">({signed(s.delta.expected_goals_away, 2)})</span>}</td>
                  <td className="pr-3">{pct(s.p_over_2_5)}</td><td>{pct(s.p_btts)}</td>
                  <td className="sr-only">{i === 0 ? "baseline" : "scenario"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-muted">Changes are in percentage points (goals for expected goals). Probabilities add to 100% in every row.</p>
      </Panel>

      <Panel title="Score distribution">
        <div className="mb-3"><label htmlFor="sl-view" className="mb-1 block text-xs text-muted">Show</label>
          <select id="sl-view" value={view} onChange={(e) => setView(Number(e.target.value))} className={field}>{all.map((s, i) => <option key={s.name} value={i}>{s.name}</option>)}</select></div>
        <ScoreGrid s={sel} home={home} away={away} />
        <p className="mt-3 text-xs text-muted">Likeliest scores: {sel.top_scorelines.map((t) => `${t.home}–${t.away} (${pct(t.p)})`).join(", ")}.</p>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Calibrated from data" badge={<Badge tone="green">Estimated from results</Badge>}>
          <dl className="space-y-1 text-sm">{r.calibrated_parameters.map((c) => <div key={c.name} className="flex justify-between gap-3"><dt className="text-muted">{c.name}</dt><dd className="font-mono">{typeof c.value === "number" ? (Number.isInteger(c.value) ? c.value : c.value.toFixed(3)) : c.value}</dd></div>)}</dl>
        </Panel>
        <Panel title="Speculative assumptions" badge={<Badge tone="amber">Not validated</Badge>}>
          {r.scenarios.every((s) => s.changed.length === 0) ? <p className="text-sm text-muted">No assumption was changed in any scenario.</p> : (
            <ul className="space-y-2 text-sm">{r.scenarios.map((s) => <li key={s.name}><span className="font-semibold">{s.name}</span>: {s.changed.length === 0 ? "nothing changed" : s.changed.map((k) => `${k.replace(/_/g, " ")} = ${s.adjustments[k]}`).join("; ")}</li>)}</ul>
          )}
          <p className="mt-3 text-xs leading-relaxed text-muted">{r.validation_status}</p>
        </Panel>
      </div>

      <Panel title="Model, provenance and export">
        <details><summary className="cursor-pointer text-sm font-semibold">How the model works</summary><p className="mt-2 text-xs leading-relaxed text-muted">{r.documentation}</p></details>
        <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
          <div className="flex justify-between gap-3"><dt className="text-muted">Model</dt><dd className="font-mono">{r.provenance.model}@{r.provenance.model_version} on {r.provenance.base_model}</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-muted">Training cutoff</dt><dd className="font-mono">{r.provenance.training_cutoff}</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-muted">Data through</dt><dd className="font-mono">{r.provenance.data_through} ({r.provenance.matches_used} matches)</dd></div>
          <div className="flex justify-between gap-3"><dt className="text-muted">Random seed</dt><dd className="font-mono">{r.provenance.random_seed === null ? "none (deterministic)" : r.provenance.random_seed}</dd></div>
          <div className="flex justify-between gap-3 sm:col-span-2"><dt className="text-muted">Data fingerprint</dt><dd className="break-all font-mono">{r.provenance.data_sha256}</dd></div>
        </dl>
        <div className="mt-3 flex flex-wrap gap-2 text-sm">
          {(["csv", "html", "json"] as const).map((f) => <a key={f} href={`/app-api/simlab/runs/${r.id}/export?format=${f}`} download className="rounded-lg border border-line px-3 py-1.5 font-semibold hover:bg-white/5">{f === "html" ? "Printable page (save as PDF)" : f.toUpperCase()}</a>)}
        </div>
        <p className="mt-2 text-xs text-muted">{r.label}</p>
      </Panel>
    </div>
  );
}
