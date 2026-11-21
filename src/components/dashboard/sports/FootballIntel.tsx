"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { call, post } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel, dt, pct } from "../ui";
import { field } from "../analysis";
import { FACTOR_NAMES, MatchTab, NoHistory, ProbBar, SimulatorTab, type Forecast } from "./FootballMatch";

// ------------------------------------------------------------------ A. today's matches
interface Fixture { date: string; home: string; away: string; forecasts?: Record<string, Forecast>; warnings?: string[]; error?: string; tracked?: boolean }

function TodayTab({ onOpen }: { onOpen: (f: { home: string; away: string; kickoff: string }) => void }) {
  const [days, setDays] = useState(14);
  const [model, setModel] = useState("dixon_coles");
  const [data, setData] = useState<{ fixtures: Fixture[]; note?: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    call<{ fixtures: Fixture[]; note?: string }>(`football/intel/fixtures?days=${days}`).then((d) => live && (setData(d), setErr(null)), (e) => live && setErr(e instanceof Error ? e.message : "Could not load fixtures."));
    return () => { live = false; };
  }, [days]);
  if (err) return /Import some match history/.test(err) ? <NoHistory /> : <ErrorPanel message={err} />;
  if (!data) return <p className="text-sm text-muted" aria-busy="true">Loading fixtures and forecasts…</p>;
  return (
    <div className="space-y-4">
      <Panel title="Today's matches and upcoming fixtures" badge={<Badge tone="amber">Model forecasts</Badge>}>
        <div className="flex flex-wrap items-end gap-3">
          <div><label htmlFor="td-days" className="mb-1 block text-xs text-muted">Show the next</label>
            <select id="td-days" value={days} onChange={(e) => setDays(Number(e.target.value))} className={field}>{[1, 7, 14, 30].map((d) => <option key={d} value={d}>{d === 1 ? "day (today)" : `${d} days`}</option>)}</select></div>
          <div><label htmlFor="td-model" className="mb-1 block text-xs text-muted">Model</label>
            <select id="td-model" value={model} onChange={(e) => setModel(e.target.value)} className={field}><option value="dixon_coles">Dixon-Coles</option><option value="poisson">Time-weighted Poisson</option><option value="elo">Elo rating</option></select></div>
        </div>
        <p className="mt-2 text-xs text-muted">Fixtures come from fixtures files you import (future-dated rows). Kickoff times are not in the data, only dates. Each forecast is stored and scored against the real result once it is imported.</p>
      </Panel>
      {data.fixtures.length === 0 ? <Empty>{data.note ?? "No upcoming fixtures."}</Empty> : (
        <ul className="space-y-3" aria-label="Upcoming fixtures">
          {data.fixtures.map((f) => {
            const fc = f.forecasts?.[model];
            return (
              <li key={`${f.date}${f.home}${f.away}`} className="glass rounded-2xl p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2"><p className="font-semibold">{f.home} vs {f.away}</p><p className="text-xs text-muted">{f.date}</p></div>
                {f.error ? <p className="mt-2 text-sm text-amber-200">{f.error}</p> : fc && (
                  <div className="mt-3 space-y-2">
                    <ProbBar h={fc.p_home} d={fc.p_draw} a={fc.p_away} home={f.home} away={f.away} />
                    <p className="font-mono text-xs text-muted">{fc.p_over_2_5 !== null ? `Over 2.5 ${pct(fc.p_over_2_5)} · Both score ${pct(fc.p_btts ?? 0)}` : "Over/under and both-teams-to-score are not available from the Elo model."}{fc.top_scorelines?.[0] ? ` · likeliest score ${fc.top_scorelines[0].home}–${fc.top_scorelines[0].away}` : ""}</p>
                    <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
                      {f.warnings && f.warnings.length > 0 && <span>{f.warnings.length} warning(s)</span>}
                      <button type="button" onClick={() => onOpen({ home: f.home, away: f.away, kickoff: f.date })} className="text-violet underline">Open match intelligence</button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ D. model performance
interface Metric { n: number; log_loss?: number; brier?: number; accuracy?: number; calibration_error?: number; mean_log_probability?: number; top_scoreline_hit_rate?: number; reliability?: { low: number; high: number; count: number; mean_predicted: number; observed: number }[] }
interface Gain { log_loss_gain?: number; standard_error?: number; clear?: boolean; n: number }
interface ModelRes { "1x2": Metric; over_2_5?: Metric; btts?: Metric; correct_score?: Metric; by_season: Record<string, Metric>; gain?: Record<string, Gain> }
type PeriodRes = Record<string, ModelRes>;
interface Run { id: string; mode: string; created_at: string; matches: number; config: { split?: Record<string, string[]>; periods?: Record<string, { matches: number; first: string; last: string }>; seasons_predicted?: string[] }; results: Record<string, PeriodRes>; tuning?: { elo?: { chosen: Record<string, number> }; poisson?: { chosen: Record<string, number> }; dixon_coles?: { rho_test: number } }; warnings: string[] }
interface Perf { chronological: Run | null; rolling: Run | null; live: { scored: { model: string; n: number; log_loss: number; brier: number; accuracy: number }[]; waiting_for_results: number }; models: Record<string, string> }

const f3 = (v?: number) => (v === undefined || v === null ? "—" : v.toFixed(3));

function gainText(g: Gain | undefined, base: string): string {
  if (!g || g.log_loss_gain === undefined) return "—";
  return `${g.log_loss_gain >= 0 ? "+" : ""}${g.log_loss_gain.toFixed(3)} ± ${(g.standard_error ?? 0).toFixed(3)}${g.clear ? " (clear)" : ""}`.replace("vs", base);
}

function verdictFor(name: string, g: Gain | undefined): string {
  if (!g || g.log_loss_gain === undefined) return "";
  if (g.clear) return `${name} clearly beat the frequency baseline.`;
  return g.log_loss_gain > 0 ? `${name} was slightly better than the frequency baseline, not by enough to rule out luck.` : `${name} was no better than the frequency baseline.`;
}

function PerformanceTab({ names }: { names: Record<string, string> }) {
  const [perf, setPerf] = useState<Perf | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [period, setPeriod] = useState("test");
  const [calModel, setCalModel] = useState("dixon_coles");
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    call<Perf>("football/intel/performance").then((d) => live && (setPerf(d), setErr(null)), (e) => live && setErr(e instanceof Error ? e.message : "Could not load performance."));
    return () => { live = false; };
  }, [tick]);

  async function run(mode: "chronological" | "rolling") {
    setBusy(mode); setErr(null);
    try { await post("football/intel/backtest", { mode }); setTick((t) => t + 1); } catch (e) { setErr(e instanceof Error ? e.message : "The backtest failed."); } finally { setBusy(null); }
  }
  if (!perf) return err ? <ErrorPanel message={err} /> : <p className="text-sm text-muted" aria-busy="true">Loading…</p>;
  const c = perf.chronological;
  const res = c?.results[period];
  const modelOrder = Object.keys(names);
  return (
    <div className="space-y-4">
      <Panel title="Model performance" badge={<Badge tone="muted">Measured on past matches</Badge>}>
        <p className="text-xs leading-relaxed text-muted">Every forecast in a backtest uses only matches played before that fixture. Settings are chosen on a validation period; the test period is never used to choose anything. Models are compared with a baseline that only knows how often home wins, draws and away wins happened before, and with a plain Elo rating.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" disabled={busy !== null} onClick={() => run("chronological")} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy === "chronological" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Run chronological backtest</button>
          <button type="button" disabled={busy !== null} onClick={() => run("rolling")} className="inline-flex items-center gap-2 rounded-xl border border-violet/60 px-4 py-2 text-sm font-semibold text-violet hover:bg-violet/10 disabled:opacity-50">{busy === "rolling" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Run rolling-origin backtest</button>
        </div>
        {busy && <p role="status" className="mt-2 text-xs text-muted">Replaying every fixture from the information available before it. This can take up to a minute on ten seasons.</p>}
        {err && <p role="alert" className="mt-3 text-sm text-red-300">{err}</p>}
      </Panel>

      {!c && !perf.rolling && <Empty>No backtest has been run yet. Import ten seasons of results, then run a chronological backtest (training 2016/17 to 2022/23, validation 2023/24, test 2024/25 to 2025/26).</Empty>}

      {c && res && (
        <>
          <Panel title="Chronological backtest" badge={<Badge tone="muted">{dt(c.created_at)}</Badge>}>
            <p className="text-xs text-muted">
              {c.matches.toLocaleString()} matches. Training {c.config.split?.training?.[0]} to {c.config.split?.training?.slice(-1)[0]} ({c.config.periods?.training.matches.toLocaleString()} matches) · validation {c.config.split?.validation?.join(", ")} · test {c.config.split?.test?.join(", ")}.
              {c.tuning?.elo && ` Elo K ${c.tuning.elo.chosen.k}, season regression ${c.tuning.elo.chosen.regress}; Poisson half-life ${c.tuning.poisson?.chosen.half_life_days} days; Dixon-Coles rho ${c.tuning.dixon_coles?.rho_test.toFixed(3)}. All chosen on validation only.`}
            </p>
            <div className="mt-3 flex flex-wrap items-end gap-3">
              <div><label htmlFor="pf-period" className="mb-1 block text-xs text-muted">Period</label>
                <select id="pf-period" value={period} onChange={(e) => setPeriod(e.target.value)} className={field}><option value="validation">Validation</option><option value="test">Test (never used to tune)</option></select></div>
            </div>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Home, draw, away performance by model</caption>
                <thead><tr className="text-left text-[11px] text-muted">{["Model", "Matches", "Log loss", "Brier", "Right result", "Calibration gap", "Log-loss gain over frequency", "over Elo"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
                <tbody className="font-mono">
                  {modelOrder.filter((k) => res[k]).map((k) => (
                    <tr key={k} className="border-t border-line"><th scope="row" className="py-1.5 pr-3 text-left font-sans font-medium">{names[k]}</th>
                      <td className="pr-3">{res[k]["1x2"].n}</td><td className="pr-3">{f3(res[k]["1x2"].log_loss)}</td><td className="pr-3">{f3(res[k]["1x2"].brier)}</td>
                      <td className="pr-3">{res[k]["1x2"].accuracy !== undefined ? pct(res[k]["1x2"].accuracy!) : "—"}</td><td className="pr-3">{res[k]["1x2"].calibration_error !== undefined ? `${(res[k]["1x2"].calibration_error! * 100).toFixed(1)} pts` : "—"}</td>
                      <td className="pr-3 text-xs">{gainText(res[k].gain?.vs_frequency, "")}</td><td className="text-xs">{gainText(res[k].gain?.vs_elo, "")}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">{["elo", "poisson", "dixon_coles"].filter((k) => res[k]).map((k) => <li key={k}>{verdictFor(names[k], res[k].gain?.vs_frequency)}</li>)}</ul>
            <p className="mt-2 text-xs text-muted">Lower log loss and Brier are better. A gain is the average log-loss improvement per match with one standard error; it is called clear only beyond two standard errors.</p>
          </Panel>

          <Panel title="By prediction market">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Performance by market and model</caption>
                <thead><tr className="text-left text-[11px] text-muted">{["Model", "1X2 log loss", "Over 2.5 log loss", "Over 2.5 right", "Both score log loss", "Both score right", "Correct score: mean log probability", "Likeliest score hit"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
                <tbody className="font-mono">
                  {modelOrder.filter((k) => res[k]).map((k) => (
                    <tr key={k} className="border-t border-line"><th scope="row" className="py-1.5 pr-3 text-left font-sans font-medium">{names[k]}</th>
                      <td className="pr-3">{f3(res[k]["1x2"].log_loss)}</td><td className="pr-3">{f3(res[k].over_2_5?.log_loss)}</td><td className="pr-3">{res[k].over_2_5?.accuracy !== undefined ? pct(res[k].over_2_5!.accuracy!) : "n/a"}</td>
                      <td className="pr-3">{f3(res[k].btts?.log_loss)}</td><td className="pr-3">{res[k].btts?.accuracy !== undefined ? pct(res[k].btts!.accuracy!) : "n/a"}</td>
                      <td className="pr-3">{f3(res[k].correct_score?.mean_log_probability)}</td><td>{res[k].correct_score?.top_scoreline_hit_rate !== undefined ? pct(res[k].correct_score!.top_scoreline_hit_rate!) : "n/a"}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-muted">The Elo model forecasts home, draw and away only. The frequency baseline&apos;s over/under and both-score figures are the plain historical rates.</p>
          </Panel>

          <Panel title="By season (log loss, 1X2)">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Log loss by season and model</caption>
                <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="pr-3 font-normal">Season</th>{modelOrder.filter((k) => res[k]).map((k) => <th key={k} scope="col" className="pr-3 font-normal">{names[k]}</th>)}</tr></thead>
                <tbody className="font-mono">
                  {Object.keys(res[modelOrder.find((k) => res[k]) ?? "elo"].by_season).map((s) => (
                    <tr key={s} className="border-t border-line"><th scope="row" className="py-1.5 pr-3 text-left font-sans font-medium">{s}</th>{modelOrder.filter((k) => res[k]).map((k) => <td key={k} className="pr-3">{f3(res[k].by_season[s]?.log_loss)}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="Calibration">
            <div className="mb-3"><label htmlFor="pf-cal" className="mb-1 block text-xs text-muted">Model</label>
              <select id="pf-cal" value={calModel} onChange={(e) => setCalModel(e.target.value)} className={field}>{modelOrder.filter((k) => res[k]).map((k) => <option key={k} value={k}>{names[k]}</option>)}</select></div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Predicted against observed frequency</caption>
                <thead><tr className="text-left text-[11px] text-muted">{["Model said", "Average said", "Actually happened", "Cases"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
                <tbody className="font-mono">{(res[calModel]?.["1x2"].reliability ?? []).map((r) => <tr key={r.low} className="border-t border-line"><th scope="row" className="py-1 pr-3 text-left font-sans font-normal">{pct(r.low, 0)} to {pct(r.high, 0)}</th><td className="pr-3">{pct(r.mean_predicted)}</td><td className="pr-3">{pct(r.observed)}</td><td>{r.count}</td></tr>)}</tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-muted">A well-calibrated model&apos;s &ldquo;average said&rdquo; and &ldquo;actually happened&rdquo; match. Bands with few cases are noisy.</p>
          </Panel>
          {c.warnings.length > 0 && <ul className="list-disc space-y-1 pl-5 text-xs text-muted">{c.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
        </>
      )}

      {perf.rolling && (
        <Panel title="Rolling-origin backtest" badge={<Badge tone="muted">{dt(perf.rolling.created_at)}</Badge>}>
          <p className="text-xs text-muted">Fixed default settings, each season predicted from all earlier seasons. Nothing is tuned, so every season is an out-of-sample check.</p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Rolling-origin log loss by season and model</caption>
              <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="pr-3 font-normal">Season</th>{modelOrder.map((k) => <th key={k} scope="col" className="pr-3 font-normal">{names[k]}</th>)}</tr></thead>
              <tbody className="font-mono">
                {(perf.rolling.config.seasons_predicted ?? []).map((s) => <tr key={s} className="border-t border-line"><th scope="row" className="py-1.5 pr-3 text-left font-sans font-medium">{s}</th>{modelOrder.map((k) => <td key={k} className="pr-3">{f3(perf.rolling!.results.rolling[k]?.by_season[s]?.log_loss)}</td>)}</tr>)}
                <tr className="border-t border-line font-semibold"><th scope="row" className="py-1.5 pr-3 text-left font-sans">All</th>{modelOrder.map((k) => <td key={k} className="pr-3">{f3(perf.rolling!.results.rolling[k]?.["1x2"].log_loss)}</td>)}</tr>
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      <Panel title="Tracked live forecasts">
        {perf.live.scored.length === 0 ? <p className="text-sm text-muted">No stored forecast has been scored yet. {perf.live.waiting_for_results} are waiting for results. Forecasts for upcoming fixtures are scored automatically when you import the played match.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Live forecasts scored against real results</caption>
              <thead><tr className="text-left text-[11px] text-muted">{["Model", "Scored", "Log loss", "Brier", "Right result"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
              <tbody className="font-mono">{perf.live.scored.map((s) => <tr key={s.model} className="border-t border-line"><th scope="row" className="py-1.5 pr-3 text-left font-sans font-medium">{names[s.model]}</th><td className="pr-3">{s.n}</td><td className="pr-3">{f3(s.log_loss)}</td><td className="pr-3">{f3(s.brier)}</td><td>{pct(s.accuracy)}</td></tr>)}</tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}

// ------------------------------------------------------------------ data sources and factors
interface Factors { factors: { key: string; name: string; detail: string; source: string; rule: string; status: "available" | "unavailable" }[]; data: { matches: number; first: string | null; last: string | null; statistics_rows: number; xg_rows: number; odds_rows: number; upcoming_fixtures: number }; sources: { kind: string; name: string; provider: string; licence_note: string; created_at: string; coverage: Record<string, unknown> }[]; notes: string[] }

function SourcesTab() {
  const [d, setD] = useState<Factors | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    call<Factors>("football/intel/factors").then((x) => live && setD(x), (e) => live && setErr(e instanceof Error ? e.message : "Could not load."));
    return () => { live = false; };
  }, []);
  if (err) return <ErrorPanel message={err} />;
  if (!d) return <p className="text-sm text-muted" aria-busy="true">Loading…</p>;
  return (
    <div className="space-y-4">
      <Panel title="Factors and data sources" badge={<Badge tone="muted">Nothing is filled in</Badge>}>
        <p className="text-xs leading-relaxed text-muted">{d.notes.join(" ")} Upload football match results, advanced statistics and fixtures on the <Link href="/dashboard/data" className="text-violet underline">Data page</Link>.</p>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
          {([["Matches", d.data.matches], ["With xG", d.data.xg_rows], ["With odds", d.data.odds_rows], ["Upcoming fixtures", d.data.upcoming_fixtures]] as const).map(([k, v]) => <div key={k} className="rounded-xl border border-line p-2"><dt className="text-[11px] text-muted">{k}</dt><dd className="font-mono font-bold">{v.toLocaleString()}</dd></div>)}
        </dl>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Factor groups, sources and availability</caption>
            <thead><tr className="text-left text-[11px] text-muted">{["Factor", "In this workspace", "Source", "When it counts"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
            <tbody>{d.factors.map((f) => (
              <tr key={f.key} className="border-t border-line align-top"><th scope="row" className="py-1.5 pr-3 text-left font-medium">{FACTOR_NAMES[f.key] ?? f.name}<div className="text-[11px] font-normal text-muted">{f.detail}</div></th>
                <td className="pr-3"><Badge tone={f.status === "available" ? "green" : "muted"}>{f.status === "available" ? "Data present" : "Unavailable"}</Badge></td><td className="pr-3 text-xs text-muted">{f.source}</td><td className="text-xs text-muted">{f.rule}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </Panel>
      {d.sources.length > 0 && (
        <Panel title="Sources you have supplied">
          <ul className="space-y-2 text-sm">{d.sources.map((s) => <li key={s.kind} className="rounded-xl border border-line p-3"><p className="font-medium">{s.name} <span className="text-xs font-normal text-muted">({s.kind.replace("_", " ")}, {s.provider.replace("_", " ")}, {dt(s.created_at)})</span></p><p className="text-xs text-muted">{s.licence_note}</p></li>)}</ul>
        </Panel>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ shell
const TABS = [["today", "Today's matches"], ["match", "Match intelligence"], ["simulator", "Simulator"], ["performance", "Model performance"], ["sources", "Data & factors"]] as const;
type TabId = (typeof TABS)[number][0];
const NAMES: Record<string, string> = { frequency: "Historical frequencies", elo: "Elo rating", poisson: "Time-weighted Poisson", dixon_coles: "Dixon-Coles" };

export function FootballIntel() {
  const [tab, setTab] = useState<TabId>("today");
  const [open, setOpen] = useState<{ home: string; away: string; kickoff?: string } | null>(null);
  const onKey = useCallback((e: React.KeyboardEvent) => {
    const i = TABS.findIndex((t) => t[0] === tab);
    if (e.key === "ArrowRight") setTab(TABS[(i + 1) % TABS.length][0]);
    if (e.key === "ArrowLeft") setTab(TABS[(i + TABS.length - 1) % TABS.length][0]);
  }, [tab]);
  return (
    <div>
      <p className="mb-3 text-xs leading-relaxed text-muted">Forecasts from three statistical models (Elo, time-weighted Poisson, Dixon-Coles) built on the Premier League results you imported. They use match results only: anything else (injuries, expected goals, odds) is shown as unavailable unless you upload it. Probabilities are estimates, never guarantees.</p>
      <div role="tablist" aria-label="Football intelligence" onKeyDown={onKey} className="mb-4 inline-flex max-w-full overflow-x-auto rounded-xl border border-line bg-bg/60 p-1">
        {TABS.map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} tabIndex={tab === id ? 0 : -1} onClick={() => setTab(id)} className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-semibold ${tab === id ? "bg-primary text-white" : "text-muted hover:text-ink"}`}>{label}</button>)}
      </div>
      <div role="tabpanel">
        {tab === "today" && <TodayTab onOpen={(f) => { setOpen(f); setTab("match"); }} />}
        {tab === "match" && <MatchTab key={open ? `${open.home}${open.away}${open.kickoff}` : "free"} initial={open} />}
        {tab === "simulator" && <SimulatorTab />}
        {tab === "performance" && <PerformanceTab names={NAMES} />}
        {tab === "sources" && <SourcesTab />}
      </div>
    </div>
  );
}
