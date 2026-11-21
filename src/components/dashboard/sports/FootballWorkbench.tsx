"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { call } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel, Stat, dt, pct } from "../ui";
import { field } from "../analysis";
import { NoHistory } from "./FootballMatch";

// ------------------------------------------------------------------ data freshness banner (shown above every football tab)
interface Fresh { has_history: boolean; stale: boolean; off_season?: boolean; note: string; last_match?: string; days_since_last_match?: number; upcoming_fixtures: number; last_import_at: string | null; current_season?: { season: string; matches_stored: number; note: string } }

export function FreshnessBanner() {
  const [f, setF] = useState<Fresh | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    call<Fresh>("football/intel/freshness").then((d) => live && setF(d), () => live && setFailed(true));
    return () => { live = false; };
  }, []);
  if (failed) return <p role="status" className="mb-3 rounded-lg border border-line p-2 text-xs text-muted">Data freshness could not be checked.</p>;
  if (!f || !f.has_history) return null;
  return (
    <div role="status" className={`mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border p-2.5 text-xs ${f.stale ? "border-amber-300/40 bg-amber-300/10 text-amber-200" : "border-line bg-white/5 text-muted"}`}>
      <Badge tone={f.stale ? "amber" : "green"}>{f.stale ? "Stale data" : "Data current"}</Badge>
      <span>{f.note}</span>
      {f.current_season && <span>Current season {f.current_season.season}: {f.current_season.matches_stored} matches stored separately from the completed seasons.</span>}
      {f.stale && <Link href="/dashboard/data" className="font-semibold underline">Import the latest results</Link>}
    </div>
  );
}

// ------------------------------------------------------------------ team intelligence
interface Venue { played: number; wins: number; draws: number; losses: number; goals_for_per_match: number | null; goals_against_per_match: number | null }
interface Form { matches: number; results: string; points_per_match: number | null }
interface Team {
  team: string; as_of: string | null; played: number; wins?: number; draws?: number; losses?: number; win_rate?: number; draw_rate?: number; loss_rate?: number; points_per_match?: number;
  goals_for_per_match?: number; goals_against_per_match?: number; average_goals_per_match?: number; clean_sheet_rate?: number; failed_to_score_rate?: number;
  home: Venue; away: Venue; form_last_5: Form; form_last_10: Form; elo: number; attack_strength?: number; defence_strength?: number; goal_rate_note?: string;
  coverage?: { first_match: string; last_match: string; matches: number; note: string }; days_since_last_match?: number; sample_note: string;
}

const dash = (v: number | null | undefined, d = 2) => (v === null || v === undefined ? "n/a" : v.toFixed(d));

function FormStrip({ results }: { results: string }) {
  return <span className="inline-flex gap-1 font-mono" aria-label={`Results, oldest to newest: ${results.split("").join(", ")}`}>{results.split("").map((c, i) => <span key={i} className={`inline-block w-5 rounded text-center text-xs font-bold ${c === "W" ? "bg-emerald-400/20 text-emerald-300" : c === "D" ? "bg-amber-300/20 text-amber-200" : "bg-red-400/20 text-red-300"}`}>{c}</span>)}</span>;
}

export function TeamTab() {
  const [clubs, setClubs] = useState<string[] | null>(null);
  const [team, setTeam] = useState("");
  const [data, setData] = useState<Team | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let live = true;
    call<{ clubs: string[] }>("football/summary").then((s) => { if (live) { setClubs(s.clubs); setErr(null); } }, (e) => live && setErr(e instanceof Error ? e.message : "Could not load clubs."));
    return () => { live = false; };
  }, []);
  async function pick(name: string) {
    setTeam(name); setData(null); setErr(null);
    if (!name) return;
    setLoading(true);
    try { setData(await call<Team>(`football/team?team=${encodeURIComponent(name)}`)); } catch (e) { setErr(e instanceof Error ? e.message : "Could not load that club."); } finally { setLoading(false); }
  }
  if (!clubs) return err ? <ErrorPanel message={err} /> : <p className="text-sm text-muted" aria-busy="true">Loading clubs…</p>;
  if (clubs.length === 0) return <NoHistory />;
  return (
    <div className="space-y-4">
      <Panel title="Team intelligence" badge={<Badge tone="muted">From your imported matches</Badge>}>
        <div><label htmlFor="ti-team" className="mb-1 block text-xs text-muted">Club</label>
          <select id="ti-team" value={team} onChange={(e) => pick(e.target.value)} className={field}><option value="">Choose a club…</option>{clubs.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
        <p className="mt-2 text-xs leading-relaxed text-muted">Everything here is calculated from the matches you imported, using only matches before the as-of date. Sample sizes are shown beside the rates: a rate from few matches is uncertain.</p>
        {err && <p role="alert" className="mt-3 text-sm text-red-300">{err}</p>}
      </Panel>
      {loading && <p className="text-sm text-muted" aria-busy="true">Calculating…</p>}
      {!team && !loading && <Empty>Choose a club to see its form, goals, home and away record, clean sheets and strength.</Empty>}
      {data && (
        <>
          <Panel title={data.team} badge={<Badge tone="muted">{data.played} matches · as of {data.as_of ?? "now"}</Badge>}>
            <div className="grid gap-3 sm:grid-cols-4">
              <Stat label="Elo rating" value={data.elo.toFixed(0)} hint="Results-based rating; 1500 is the starting level" />
              <Stat label="Points per match" value={dash(data.points_per_match)} hint={`${data.wins}W ${data.draws}D ${data.losses}L`} />
              <Stat label="Goals for / against" value={`${dash(data.goals_for_per_match)} / ${dash(data.goals_against_per_match)}`} hint="per match" />
              <Stat label="Days since last match" value={data.days_since_last_match ?? "n/a"} hint="league matches only" />
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-4">
              <Stat label="Clean sheets" value={data.clean_sheet_rate === undefined ? "n/a" : pct(data.clean_sheet_rate)} hint={`of ${data.played} matches`} />
              <Stat label="Failed to score" value={data.failed_to_score_rate === undefined ? "n/a" : pct(data.failed_to_score_rate)} hint={`of ${data.played} matches`} />
              <Stat label="Average total goals" value={dash(data.average_goals_per_match)} hint="both teams, per match" />
              <Stat label="Win / draw / loss" value={data.win_rate === undefined ? "n/a" : `${pct(data.win_rate, 0)} / ${pct(data.draw_rate ?? 0, 0)} / ${pct(data.loss_rate ?? 0, 0)}`} />
            </div>
          </Panel>

          <Panel title="Recent form" badge={<Badge tone="muted">Oldest to newest</Badge>}>
            <dl className="grid gap-3 sm:grid-cols-2 text-sm">
              <div><dt className="text-xs text-muted">Last 5 ({data.form_last_5.matches} matches, {dash(data.form_last_5.points_per_match)} points per match)</dt><dd><FormStrip results={data.form_last_5.results} /></dd></div>
              <div><dt className="text-xs text-muted">Last 10 ({data.form_last_10.matches} matches, {dash(data.form_last_10.points_per_match)} points per match)</dt><dd><FormStrip results={data.form_last_10.results} /></dd></div>
            </dl>
          </Panel>

          <Panel title="Home and away">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Home and away record with sample sizes</caption>
                <thead><tr className="text-left text-[11px] text-muted">{["Venue", "Matches", "Won", "Drawn", "Lost", "Goals for", "Goals against"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
                <tbody className="font-mono">{([["Home", data.home], ["Away", data.away]] as const).map(([name, v]) => (
                  <tr key={name} className="border-t border-line"><th scope="row" className="py-1.5 pr-3 text-left font-sans font-medium">{name}</th><td className="pr-3">{v.played}</td><td className="pr-3">{v.wins}</td><td className="pr-3">{v.draws}</td><td className="pr-3">{v.losses}</td><td className="pr-3">{dash(v.goals_for_per_match)}</td><td>{dash(v.goals_against_per_match)}</td></tr>
                ))}</tbody>
              </table>
            </div>
          </Panel>

          <Panel title="Strength, adjusted for opponents" badge={<Badge tone="muted">Fitted estimate</Badge>}>
            <div className="grid gap-3 sm:grid-cols-2">
              <Stat label="Attack strength" value={dash(data.attack_strength, 2)} hint="1.00 is the league average; above scores more" />
              <Stat label="Defensive weakness" value={dash(data.defence_strength, 2)} hint="1.00 is average; below concedes fewer" />
            </div>
            <p className="mt-2 text-xs leading-relaxed text-muted">These come from the same time-weighted model as the forecasts, which accounts for who each side played, so a club that scored many goals against weak opponents is not rated like one that scored them against strong ones. They are estimates with uncertainty, pulled toward average when a club has few matches. {data.goal_rate_note}</p>
          </Panel>

          <p className="text-xs leading-relaxed text-muted">{data.sample_note} {data.coverage && `Coverage: ${data.coverage.matches} matches from ${data.coverage.first_match} to ${data.coverage.last_match}. ${data.coverage.note}`}</p>
        </>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ fixtures and results
interface Schedule { results: { season: string; date: string; home: string; away: string; score: string }[]; fixtures: { season: string; date: string; home: string; away: string; tracked: boolean }[]; today: string }

export function ScheduleTab({ onOpen }: { onOpen: (f: { home: string; away: string; kickoff: string }) => void }) {
  const [d, setD] = useState<Schedule | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [days, setDays] = useState(30);
  useEffect(() => {
    let live = true;
    call<Schedule>(`football/intel/schedule?results=25&days=${days}`).then((s) => live && (setD(s), setErr(null)), (e) => live && setErr(e instanceof Error ? e.message : "Could not load fixtures and results."));
    return () => { live = false; };
  }, [days]);
  if (err) return /Import some match history/.test(err) ? <NoHistory /> : <ErrorPanel message={err} />;
  if (!d) return <p className="text-sm text-muted" aria-busy="true">Loading fixtures and results…</p>;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel title="Upcoming fixtures" badge={<Badge tone="muted">From fixtures files you imported</Badge>}>
        <div className="mb-3"><label htmlFor="sc-days" className="mb-1 block text-xs text-muted">Show the next</label>
          <select id="sc-days" value={days} onChange={(e) => setDays(Number(e.target.value))} className={field}>{[7, 14, 30, 60].map((n) => <option key={n} value={n}>{n} days</option>)}</select></div>
        {d.fixtures.length === 0 ? <Empty>No upcoming fixtures are imported for the next {days} days. Import a fixtures file (future-dated rows in the same layout as results) on the Data page.</Empty> : (
          <ul className="divide-y divide-line" aria-label="Upcoming fixtures">
            {d.fixtures.map((f) => (
              <li key={`${f.date}${f.home}${f.away}`} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                <span><span className="font-mono text-xs text-muted">{f.date}</span> {f.home} v {f.away}</span>
                <span className="flex items-center gap-3">{f.tracked && <Badge tone="violet">Forecast saved</Badge>}<button type="button" onClick={() => onOpen({ home: f.home, away: f.away, kickoff: f.date })} className="text-xs text-violet underline">Match intelligence</button></span>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-xs text-muted">Kick-off times are not in the data, only dates. No forecast is made on this tab.</p>
      </Panel>
      <Panel title="Latest results" badge={<Badge tone="muted">Newest first</Badge>}>
        {d.results.length === 0 ? <Empty>No results are stored.</Empty> : (
          <ul className="divide-y divide-line" aria-label="Latest results">
            {d.results.map((r) => <li key={`${r.date}${r.home}${r.away}`} className="flex flex-wrap justify-between gap-2 py-2 text-sm"><span><span className="font-mono text-xs text-muted">{r.date}</span> {r.home} <span className="font-mono font-semibold">{r.score}</span> {r.away}</span><span className="text-xs text-muted">{r.season}</span></li>)}
          </ul>
        )}
        <p className="mt-2 text-xs text-muted"><Link href="/dashboard/data" className="text-violet underline">Open the Historical Data Manager</Link> to browse every season, validate or export.</p>
      </Panel>
    </div>
  );
}

// ------------------------------------------------------------------ saved predictions
interface SavedForecast { id: string; model: string; key: string; version: string; made_at: string; training_cutoff: string; data_sha256: string; p_home: number; p_draw: number; p_away: number; expected_goals: number[] | null; log_loss: number | null; correct: boolean | null }
interface SavedFixture { date: string; home: string; away: string; status: "scored" | "waiting"; result: string | null; outcome: number | null; forecasts: SavedForecast[] }
interface Saved { total: number; limit: number; offset: number; fixtures: SavedFixture[]; note: string }
const OUTCOME = ["home win", "draw", "away win"];

export function SavedTab() {
  const [page, setPage] = useState(0);
  const [d, setD] = useState<Saved | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const size = 10;
  useEffect(() => {
    let live = true;
    call<Saved>(`football/intel/saved?limit=${size}&offset=${page * size}`).then((s) => live && (setD(s), setErr(null)), (e) => live && setErr(e instanceof Error ? e.message : "Could not load saved predictions."));
    return () => { live = false; };
  }, [page]);
  if (err) return /Import some match history/.test(err) ? <NoHistory /> : <ErrorPanel message={err} />;
  if (!d) return <p className="text-sm text-muted" aria-busy="true">Loading saved predictions…</p>;
  return (
    <div className="space-y-4">
      <Panel title="Saved predictions" badge={<Badge tone="amber">Made before the match</Badge>}>
        <p className="text-xs leading-relaxed text-muted">{d.note} Backtests (replays of past matches) are on the Model performance tab, not here.</p>
      </Panel>
      {d.fixtures.length === 0 ? <Empty>No forecast has been saved yet. Open Match intelligence for a fixture and save the forecast, or open Today&apos;s matches: forecasts for upcoming imported fixtures are stored there automatically.</Empty> : (
        <ul className="space-y-3" aria-label="Saved predictions">
          {d.fixtures.map((f) => (
            <li key={`${f.date}${f.home}${f.away}`}>
              <details className="glass rounded-2xl p-4">
                <summary className="flex cursor-pointer flex-wrap items-center justify-between gap-2">
                  <span className="font-semibold">{f.home} v {f.away} <span className="font-mono text-xs font-normal text-muted">{f.date}</span></span>
                  <span className="flex items-center gap-2 text-xs">{f.status === "scored" ? <><Badge tone="green">Result {f.result}</Badge></> : <Badge tone="muted">Waiting for the result</Badge>}</span>
                </summary>
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-sm">
                    <caption className="sr-only">Forecasts saved for {f.home} v {f.away}</caption>
                    <thead><tr className="text-left text-[11px] text-muted">{["Model", "Version", "Home", "Draw", "Away", "Made", "Training cutoff", "Scored"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
                    <tbody className="font-mono">{f.forecasts.map((x) => (
                      <tr key={x.id} className="border-t border-line"><th scope="row" className="py-1.5 pr-3 text-left font-sans font-medium">{x.model}</th><td className="pr-3">{x.version}</td><td className="pr-3">{pct(x.p_home)}</td><td className="pr-3">{pct(x.p_draw)}</td><td className="pr-3">{pct(x.p_away)}</td>
                        <td className="pr-3 text-xs">{dt(x.made_at)}</td><td className="pr-3 text-xs">{x.training_cutoff}</td>
                        <td className="text-xs">{x.log_loss === null ? "n/a" : `${x.correct ? "right" : "wrong"} result, log loss ${x.log_loss.toFixed(3)}`}</td></tr>
                    ))}</tbody>
                  </table>
                </div>
                <p className="mt-2 text-xs text-muted">{f.status === "scored" && f.outcome !== null ? `The match ended ${f.result}: a ${OUTCOME[f.outcome]}. One match says little about a model; judge it on the Model performance tab.` : "Scored automatically when the played match is imported."}</p>
              </details>
            </li>
          ))}
        </ul>
      )}
      {d.total > size && (
        <div className="flex items-center justify-between text-sm">
          <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)} className="rounded-lg border border-line px-3 py-1.5 disabled:opacity-40">Newer</button>
          <span className="text-xs text-muted">{page * size + 1} to {Math.min((page + 1) * size, d.total)} of {d.total} fixtures</span>
          <button type="button" disabled={(page + 1) * size >= d.total} onClick={() => setPage(page + 1)} className="rounded-lg border border-line px-3 py-1.5 disabled:opacity-40">Older</button>
        </div>
      )}
    </div>
  );
}
