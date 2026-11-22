"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { call } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel, pct } from "../../ui";
import { field } from "../../analysis";
import { ModelBadge, ProbBar, StatusBadge } from "./Parts";
import { STATUS_LABEL, kickoff, num, stamp, type Fixture, type FixtureList, type Percent } from "./live";

interface Version {
  id: string; version_no: number; official: boolean; generated_at: string; kickoff_utc: string; checkpoint: string; refresh_reason: string; model: string; goal_model: string;
  probabilities: Percent; percent: Percent; expected_goals: { home: number; away: number }; goals: { over_2_5: number | null; under_2_5: number | null; both_teams_to_score: number | null };
  top_scorelines: { home: number; away: number; p: number }[]; drivers: Record<string, unknown>[]; warnings: string[];
  data_completeness: { available: number; partial: number; unavailable: number; of: number; share_available: number; missing: string[] };
  provider_refs: { fixture_provider: string | null; provider_fixture_id: string | null; provider_updated_at: string | null; fixture_last_synced_at: string | null; results_history_as_of: string | null }; label: string;
}
interface Side { matches_played: number; form_5: string | null; form_5_ppg: number | null; form_10_ppg: number | null; goals_for_avg: number | null; goals_against_avg: number | null; clean_sheet_rate: number | null; over_2_5_rate: number | null; btts_rate: number | null; rest_days: number | null; league_position: number | null; points: number | null; elo: number | null }
interface Snapshot { cutoff: string; home: Side; away: Side; elo_difference: number | null; head_to_head: { meetings: number; home_team_wins?: number; draws?: number; away_team_wins?: number; last_meeting?: string } | null; factors: Record<string, { status: string; note: string; source: string }>; note: string }
interface Detail { fixture_id: string; status: string; snapshot: Snapshot | null; latest: Version | null; official: Version | null; versions: number; no_forecast_reason: string | null; official_note: string }

const COMPARE: [string, keyof Side, (v: number | string | null) => string][] = [
  ["League position", "league_position", (v) => (v === null ? "n/a" : String(v))], ["Points", "points", (v) => (v === null ? "n/a" : String(v))],
  ["Elo rating", "elo", (v) => num(v as number | null, 0)], ["Form, last 5", "form_5", (v) => (v ? String(v) : "n/a")],
  ["Points per match, last 5", "form_5_ppg", (v) => num(v as number | null)], ["Points per match, last 10", "form_10_ppg", (v) => num(v as number | null)],
  ["Goals scored per match", "goals_for_avg", (v) => num(v as number | null)], ["Goals conceded per match", "goals_against_avg", (v) => num(v as number | null)],
  ["Clean sheets", "clean_sheet_rate", (v) => (v === null ? "n/a" : pct(v as number, 0))], ["Over 2.5 goals", "over_2_5_rate", (v) => (v === null ? "n/a" : pct(v as number, 0))],
  ["Both teams scored", "btts_rate", (v) => (v === null ? "n/a" : pct(v as number, 0))], ["Days since last match", "rest_days", (v) => (v === null ? "n/a" : String(v))],
  ["Matches in the data", "matches_played", (v) => String(v ?? "n/a")],
];

function Driver({ d }: { d: Record<string, unknown> }) {
  const factor = String(d.factor ?? "Factor");
  if (typeof d.effect_home === "number") return <li className="flex justify-between gap-3"><span>{factor}</span><span className="font-mono text-xs text-muted">home {Number(d.effect_home) >= 0 ? "+" : ""}{Number(d.effect_home).toFixed(2)} · away {Number(d.effect_away) >= 0 ? "+" : ""}{Number(d.effect_away).toFixed(2)}</span></li>;
  if (typeof d.points === "number") return <li className="flex justify-between gap-3"><span>{factor}</span><span className="font-mono text-xs text-muted">{d.points >= 0 ? "+" : ""}{d.points.toFixed(0)} points</span></li>;
  if (typeof d.share === "number") return <li className="flex justify-between gap-3"><span>{factor}</span><span className="font-mono text-xs text-muted">{pct(d.share, 0)} of the model</span></li>;
  return <li>{factor}</li>;
}

function Forecast({ v, f, tz, title }: { v: Version; f: Fixture; tz: string; title: string }) {
  return (
    <Panel title={title} badge={<span className="flex gap-1.5"><ModelBadge model={v.model} />{v.official ? <Badge tone="green">Official</Badge> : <Badge tone="muted">Version {v.version_no}</Badge>}</span>}>
      <ProbBar percent={v.percent} home={f.home_team} away={f.away_team} />
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div><dt className="text-xs text-muted">Expected goals</dt><dd className="font-mono">{num(v.expected_goals.home)} – {num(v.expected_goals.away)}</dd></div>
        <div><dt className="text-xs text-muted">Over / under 2.5</dt><dd className="font-mono">{v.goals.over_2_5 === null ? "n/a" : `${pct(v.goals.over_2_5, 0)} / ${pct(v.goals.under_2_5 ?? 0, 0)}`}</dd></div>
        <div><dt className="text-xs text-muted">Both teams score</dt><dd className="font-mono">{v.goals.both_teams_to_score === null ? "n/a" : pct(v.goals.both_teams_to_score, 0)}</dd></div>
        <div><dt className="text-xs text-muted">Made</dt><dd className="text-xs">{stamp(v.generated_at, tz)}</dd></div>
      </dl>
      <div className="mt-4">
        <h3 className="mb-1 text-xs font-semibold text-muted">Five most likely scores ({f.home_team} first)</h3>
        <ol className="flex flex-wrap gap-2" aria-label="Most likely scores">{v.top_scorelines.map((s) => <li key={`${s.home}-${s.away}`} className="rounded-lg border border-line px-2 py-1 font-mono text-xs">{s.home}–{s.away} <span className="text-muted">{pct(s.p)}</span></li>)}</ol>
        <p className="mt-1 text-[11px] text-muted">Goal markets and scores come from {v.goal_model === "dixon_coles" ? "the Dixon-Coles model" : v.goal_model}.</p>
      </div>
    </Panel>
  );
}

/** Detailed forecast for one fixture: probabilities, drivers, team comparison and what data was missing. */
export function MatchIntel({ tz, fixtureId }: { tz: string; fixtureId?: string }) {
  const [list, setList] = useState<Fixture[] | null>(null);
  const [sel, setSel] = useState(fixtureId ?? "");
  const [fixture, setFixture] = useState<Fixture | null>(null);
  const [d, setD] = useState<Detail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    call<FixtureList>(`football/live/fixtures?window=month&tz=${encodeURIComponent(tz)}&limit=100`).then((x) => { if (live) setList(x.fixtures); }, (e) => { if (live) setErr(e instanceof Error ? e.message : "Could not load fixtures."); });
    return () => { live = false; };
  }, [tz]);

  useEffect(() => {
    if (!sel) return;
    let live = true;
    Promise.all([call<Detail>(`football/live/fixtures/${sel}/forecast`), call<FixtureList>(`football/live/fixtures?window=all&limit=100&tz=${encodeURIComponent(tz)}`)]).then(([detail, all]) => {
      if (!live) return;
      setD(detail); setErr(null); setFixture(all.fixtures.find((x) => x.id === sel) ?? null);
    }, (e) => { if (live) { setD(null); setErr(e instanceof Error ? e.message : "Could not load this match."); } });
    return () => { live = false; };
  }, [sel, tz]);

  async function request() {
    setBusy(true); setMsg(null);
    try {
      const r = await call<{ status: string; message?: string; version_no?: number }>(`football/live/fixtures/${sel}/forecast`, { method: "POST" });
      setMsg(r.status === "created" ? `Stored forecast version ${r.version_no}.` : r.message ?? "Nothing has changed.");
      setD(await call<Detail>(`football/live/fixtures/${sel}/forecast`));
    } catch (e) { setMsg(e instanceof Error ? e.message : "Could not generate a forecast."); } finally { setBusy(false); }
  }

  const fx = fixture ?? list?.find((x) => x.id === sel) ?? null;
  const s = d?.snapshot;
  return (
    <div className="space-y-4">
      <div className="max-w-xl">
        <label htmlFor="mi-fixture" className="mb-1 block text-xs text-muted">Choose a match</label>
        <select id="mi-fixture" value={sel} onChange={(e) => { setSel(e.target.value); setD(null); setMsg(null); }} className={`${field} w-full`}>
          <option value="">{list === null ? "Loading…" : list.length ? "Select an upcoming match" : "No fixtures in the next 30 days"}</option>
          {sel && !list?.some((x) => x.id === sel) && fx && <option value={sel}>{fx.home_team} v {fx.away_team}</option>}
          {list?.map((x) => <option key={x.id} value={x.id}>{x.home_team} v {x.away_team}, {kickoff(x.kickoff_utc, tz)}</option>)}
        </select>
      </div>
      {err && <ErrorPanel message={err} />}
      {!sel && !err && <Empty>Select a match to see its forecast, drivers and team comparison. You can also open one from Today&apos;s matches or Upcoming fixtures.</Empty>}
      {sel && !d && !err && <p className="text-sm text-muted" aria-busy="true">Loading match…</p>}
      {d && fx && (
        <>
          <Panel title="Match overview" badge={<StatusBadge status={fx.status} />}>
            <p className="text-lg font-bold">{fx.home_team} <span className="font-normal text-muted">v</span> {fx.away_team}{fx.final_score && <span className="ml-2 font-mono">{fx.final_score.home}–{fx.final_score.away}</span>}</p>
            <p className="text-sm text-muted">{kickoff(fx.kickoff_utc, tz)} · Premier League {fx.season}{fx.matchday ? ` · Matchday ${fx.matchday}` : ""}{fx.venue ? ` · ${fx.venue}` : ""}</p>
            <p className="mt-1 text-xs text-muted">Fixture data: {fx.source}, last verified {stamp(fx.last_synced_at, tz)}. {d.versions} forecast version{d.versions === 1 ? "" : "s"} stored.</p>
          </Panel>

          {d.latest ? <Forecast v={d.latest} f={fx} tz={tz} title={d.latest.official ? "Forecast (official)" : "Latest forecast"} /> : (
            <Panel title="Forecast"><Empty>{d.no_forecast_reason}</Empty></Panel>
          )}
          {d.official && d.latest && d.official.id !== d.latest.id && <Forecast v={d.official} f={fx} tz={tz} title="Official evaluation forecast" />}
          <div className="flex flex-wrap items-center gap-3">
            {fx.forecastable && <button type="button" onClick={request} disabled={busy} className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? "Working…" : d.latest ? "Check for a newer forecast" : "Generate forecast"}</button>}
            {msg && <p role="status" className="text-sm text-muted">{msg}</p>}
            <p className="text-xs text-muted">{d.official_note}</p>
          </div>

          {d.latest && (
            <Panel title="Prediction drivers">
              <ul className="space-y-1.5 text-sm" aria-label="Prediction drivers">{d.latest.drivers.map((x, i) => <Driver key={i} d={x} />)}</ul>
              <p className="mt-2 text-[11px] text-muted">Drivers describe how the model arrived at its numbers (effects on log expected goals, rating points or model weights). They are not causes in the real world.</p>
            </Panel>
          )}

          {s && (
            <Panel title="Team comparison" badge={<Badge tone="muted">Historical, to {s.cutoff}</Badge>}>
              <div className="overflow-x-auto">
                <table className="w-full text-xs sm:text-sm">
                  <caption className="sr-only">Historical comparison of {fx.home_team} and {fx.away_team}</caption>
                  <thead><tr className="text-left text-xs text-muted"><th scope="col" className="py-1 font-normal">Measure</th><th scope="col" className="py-1 font-normal">{fx.home_team}</th><th scope="col" className="py-1 font-normal">{fx.away_team}</th></tr></thead>
                  <tbody>{COMPARE.map(([label, key, fmt]) => <tr key={key} className="border-t border-line"><th scope="row" className="py-1.5 pr-3 text-left font-normal">{label}</th><td className="py-1.5 font-mono">{fmt(s.home[key] as number | string | null)}</td><td className="py-1.5 font-mono">{fmt(s.away[key] as number | string | null)}</td></tr>)}</tbody>
                </table>
              </div>
              {s.head_to_head && (
                <p className="mt-3 text-sm">Head to head: {s.head_to_head.meetings ? `${s.head_to_head.meetings} earlier meeting${s.head_to_head.meetings === 1 ? "" : "s"}, ${fx.home_team} ${s.head_to_head.home_team_wins}, drawn ${s.head_to_head.draws}, ${fx.away_team} ${s.head_to_head.away_team_wins}.` : "no earlier meetings in the imported results."}</p>
              )}
              <p className="mt-2 text-[11px] text-muted">{s.note}</p>
            </Panel>
          )}

          {s && (
            <Panel title="Player availability" badge={<Badge tone={s.factors.player_availability?.status === "unavailable" ? "amber" : "green"}>{s.factors.player_availability?.status ?? "unavailable"}</Badge>}>
              <p className="text-sm">{s.factors.player_availability?.status === "unavailable" ? "Injury, suspension and lineup information is not available for this match, so it is not used in the forecast and nothing is assumed about who will play." : s.factors.player_availability?.note}</p>
              <p className="mt-1 text-xs text-muted">Source: {s.factors.player_availability?.source}</p>
            </Panel>
          )}

          {d.latest && (
            <Panel title="Data quality">
              <p className="text-sm">{d.latest.data_completeness.available} of {d.latest.data_completeness.of} data factors available, {d.latest.data_completeness.partial} partly.</p>
              {d.latest.warnings.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-amber-200">{d.latest.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
              <p className="mt-2 text-[11px] text-muted">Version {d.latest.version_no}, {d.latest.checkpoint}: {d.latest.refresh_reason} Fixture from {d.latest.provider_refs.fixture_provider ?? "an uploaded file"}{d.latest.provider_refs.provider_fixture_id ? ` (id ${d.latest.provider_refs.provider_fixture_id})` : ""}; results history as of {d.latest.provider_refs.results_history_as_of ?? "unknown"}. {d.latest.label}</p>
            </Panel>
          )}
          <p className="text-xs text-muted">Status: {STATUS_LABEL[d.status] ?? d.status}. <Link href={`/dashboard/sports/live?tab=history&fixture=${d.fixture_id}`} className="text-violet underline">See every stored version</Link></p>
        </>
      )}
    </div>
  );
}
