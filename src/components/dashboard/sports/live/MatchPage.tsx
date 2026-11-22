"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { call } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel, pct } from "../../ui";
import { field } from "../../analysis";
import { ModelBadge, ProbBar, StatusBadge } from "./Parts";
import { useZone } from "./useZone";
import { ZONES, kickoff, num, stamp, type Percent } from "./live";

type Kind = "historical" | "verified" | "model";
interface Rec { played: number; goals_for: number | null; goals_against: number | null; points_per_match: number | null }
interface Recent { date: string; opponent: string; venue: "H" | "A"; goals_for: number; goals_against: number; result: "W" | "D" | "L" }
interface Summary { matches_played: number | null; form_5: string | null; form_5_ppg: number | null; form_10_ppg: number | null; goals_for_avg: number | null; goals_against_avg: number | null; clean_sheet_rate: number | null; elo: number | null; rest_days: number | null; league_position: number | null; points: number | null }
interface Ver {
  id: string; version_no: number; official: boolean; generated_at: string; checkpoint: string; refresh_reason: string; model: string; goal_model: string; percent: Percent; probabilities: Percent;
  expected_goals: { home: number; away: number }; goals: { over_2_5: number | null; under_2_5: number | null; both_teams_to_score: number | null }; top_scorelines: { home: number; away: number; p: number }[];
  change_from_previous: { previous_version: number; max_abs_change: number; significant: boolean } | null; warnings: string[]; label: string;
  provider_refs: { fixture_provider: string | null; provider_fixture_id: string | null; results_history_as_of: string | null };
}
interface Evaluation { available: boolean; note: string; final_score?: { home: number; away: number }; outcome?: string; version_no?: number; most_likely?: string; most_likely_was_right?: boolean; probability_given_to_outcome?: number;
  log_loss?: number; brier?: number; over_2_5?: { happened: boolean; probability: number }; both_teams_to_score?: { happened: boolean; probability: number }; exact_score?: { in_top_five: boolean; probability: number | null } }
interface Match {
  kinds: Record<Kind, string>;
  fixture: { id: string; season: string; matchday: number | null; home_team: string; away_team: string; status: string; kickoff_utc: string | null; venue: string | null; source: string; provider_updated_at: string | null; last_synced_at: string | null; final_score: { home: number; away: number } | null; forecastable: boolean };
  forecast: { version: Ver | null; versions: number; no_forecast_reason: string | null; official_note: string };
  form: { cutoff: string; summary: { home: Summary; away: Summary } | null; recent: { home: Recent[]; away: Recent[] }; note: string };
  venue_performance: { home_team_at_home: Rec | null; home_team_away: Rec | null; away_team_at_home: Rec | null; away_team_away: Rec | null; note: string };
  head_to_head: { summary: { meetings: number; home_team_wins?: number; draws?: number; away_team_wins?: number; last_meeting?: string } | null; meetings: { date: string; season: string; home_team: string; away_team: string; home_goals: number; away_goals: number }[]; note: string };
  goals: { expected: { home: number; away: number } | null; score_grid: { max_goals: number; cells: number[][]; other: number } | null; top_scorelines: { home: number; away: number; p: number }[] | null; over_2_5: number | null; both_teams_to_score: number | null;
    provider_xg: { home: { matches: number; xg_for: number | null; xg_against: number | null }; away: { matches: number; xg_for: number | null; xg_against: number | null } } | null; note: string };
  availability: { status: string; reports: { team: string; player: string; status: string; from_date: string; to_date: string | null; reported_at: string }[]; note: string; source: string };
  drivers: { items: Record<string, unknown>[]; note: string };
  revisions: { versions: Ver[]; status_history: { old_status: string | null; new_status: string; old_kickoff: string | null; new_kickoff: string | null; observed_at: string }[] };
  result: { evaluation: Evaluation | null } | null;
  warnings: string[]; data_completeness: { available: number; partial: number; of: number; missing: string[] } | null;
}

const KIND: Record<Kind, { label: string; tone: "cyan" | "green" | "violet" }> = { historical: { label: "Historical statistics", tone: "cyan" }, verified: { label: "Current verified information", tone: "green" }, model: { label: "Model estimate", tone: "violet" } };
const CHECKPOINT: Record<string, string> = { discovery: "First forecast", h48: "48 hours before", h24: "24 hours before", h6: "6 hours before", h1: "1 hour before", reschedule: "Kickoff changed", lineup: "Lineup change", manual: "Requested" };
const RESULT_TONE = { W: "text-emerald-300", D: "text-amber-200", L: "text-red-300" } as const;
const OUTCOME_TEXT = (o?: string) => (o === "draw" ? "a draw" : o === "away" ? "an away win" : "a home win");

function Section({ id, title, kind, children, right }: { id: string; title: string; kind: Kind; children: ReactNode; right?: ReactNode }) {
  return (
    <section aria-labelledby={id} className="glass min-w-0 rounded-2xl p-4 sm:p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 id={id} className="text-sm font-semibold">{title}</h2>
        <span className="flex items-center gap-2">{right}<Badge tone={KIND[kind].tone}>{KIND[kind].label}</Badge></span>
      </div>
      {children}
    </section>
  );
}

const Note = ({ children }: { children: ReactNode }) => <p className="mt-2 text-[11px] text-muted">{children}</p>;

function Driver({ d }: { d: Record<string, unknown> }) {
  const factor = String(d.factor ?? "Factor");
  const sign = (n: number) => `${n >= 0 ? "+" : ""}${n.toFixed(2)}`;
  if (typeof d.effect_home === "number") return <li className="flex justify-between gap-3"><span>{factor}</span><span className="font-mono text-xs text-muted">home {sign(d.effect_home)} · away {sign(Number(d.effect_away))}</span></li>;
  if (typeof d.points === "number") return <li className="flex justify-between gap-3"><span>{factor}</span><span className="font-mono text-xs text-muted">{d.points >= 0 ? "+" : ""}{d.points.toFixed(0)} points</span></li>;
  if (typeof d.share === "number") return <li className="flex justify-between gap-3"><span>{factor}</span><span className="font-mono text-xs text-muted">{pct(d.share, 0)} of the model</span></li>;
  return <li>{factor}</li>;
}

function Recents({ team, rows }: { team: string; rows: Recent[] }) {
  return (
    <div>
      <h3 className="mb-1 text-xs font-semibold text-muted">{team}: last five (newest first)</h3>
      {rows.length === 0 ? <p className="text-xs text-muted">No earlier matches in the imported results.</p> : (
        <ol className="space-y-1 text-xs" aria-label={`${team} recent results`}>{rows.map((r) => <li key={r.date + r.opponent} className="flex gap-2"><span className={`w-4 font-bold ${RESULT_TONE[r.result]}`}>{r.result}</span><span className="font-mono">{r.goals_for}–{r.goals_against}</span><span>{r.venue === "H" ? "vs" : "at"} {r.opponent}</span><span className="ml-auto text-muted">{r.date}</span></li>)}</ol>
      )}
    </div>
  );
}

function RecordRow({ label, r }: { label: string; r: Rec | null }) {
  return <tr className="border-t border-line"><th scope="row" className="py-1.5 pr-3 text-left font-normal">{label}</th>{r ? <><td className="font-mono">{r.played}</td><td className="font-mono">{num(r.goals_for)}</td><td className="font-mono">{num(r.goals_against)}</td><td className="font-mono">{num(r.points_per_match)}</td></> : <td colSpan={4} className="text-muted">No matches</td>}</tr>;
}

function Grid({ g, home, away }: { g: NonNullable<Match["goals"]["score_grid"]>; home: string; away: string }) {
  const n = g.cells.length;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-center text-[11px] sm:text-xs">
        <caption className="mb-1 text-left text-xs text-muted">Chance of each final score. Rows: {home} goals. Columns: {away} goals.</caption>
        <thead><tr><td /><th scope="col" colSpan={n} className="pb-1 font-normal text-muted">{away} goals</th></tr><tr><th scope="col" className="w-10 font-normal text-muted">{home}</th>{Array.from({ length: n }, (_, a) => <th key={a} scope="col" className="font-mono font-normal">{a}</th>)}</tr></thead>
        <tbody>{g.cells.map((row, h) => (
          <tr key={h}><th scope="row" className="font-mono font-normal">{h}</th>{row.map((p, a) => (
            <td key={a} className="relative border border-line/40 p-0 font-mono"><span aria-hidden="true" className="absolute inset-0 bg-violet" style={{ opacity: Math.min(0.55, p * 5) }} /><span className="relative block py-1">{(p * 100).toFixed(1)}</span></td>
          ))}</tr>
        ))}</tbody>
      </table>
      <p className="mt-1 text-[11px] text-muted">Percentages. Scores above {g.cells.length - 1} goals for either side add up to {(g.other * 100).toFixed(1)}%.</p>
    </div>
  );
}

function Result({ m }: { m: Match }) {
  const ev = m.result?.evaluation;
  if (!ev) return null;
  return (
    <Section id="sec-result" title="J. Final result and evaluation" kind="verified">
      {ev.final_score && <p className="text-lg font-bold">{m.fixture.home_team} <span className="font-mono">{ev.final_score.home}–{ev.final_score.away}</span> {m.fixture.away_team}</p>}
      {!ev.available ? <p className="mt-1 text-sm text-muted">{ev.note}</p> : (
        <>
          <p className="mt-1 text-sm">The result was {OUTCOME_TEXT(ev.outcome)}. The official forecast (version {ev.version_no}, made before kickoff) thought {OUTCOME_TEXT(ev.most_likely)} most likely, so it was {ev.most_likely_was_right ? "right" : "wrong"} about the likeliest result, and it gave what happened {pct(ev.probability_given_to_outcome ?? 0, 0)}.</p>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div><dt className="text-xs text-muted">Log loss</dt><dd className="font-mono">{num(ev.log_loss, 3)}</dd></div>
            <div><dt className="text-xs text-muted">Brier score</dt><dd className="font-mono">{num(ev.brier, 3)}</dd></div>
            {ev.over_2_5 && <div><dt className="text-xs text-muted">Over 2.5 goals</dt><dd className="text-xs">{ev.over_2_5.happened ? "happened" : "did not happen"}; the forecast gave that {pct(ev.over_2_5.probability, 0)}</dd></div>}
            {ev.both_teams_to_score && <div><dt className="text-xs text-muted">Both teams scored</dt><dd className="text-xs">{ev.both_teams_to_score.happened ? "yes" : "no"}; the forecast gave that {pct(ev.both_teams_to_score.probability, 0)}</dd></div>}
            {ev.exact_score && <div className="col-span-2"><dt className="text-xs text-muted">Exact score</dt><dd className="text-xs">{ev.exact_score.in_top_five ? "was among the five likeliest scores" : "was not among the five likeliest scores"}{ev.exact_score.probability !== null ? `; the forecast gave it ${pct(ev.exact_score.probability, 1)}` : ""}</dd></div>}
          </dl>
          <Note>{ev.note}</Note>
        </>
      )}
    </Section>
  );
}

/** The dedicated page for one fixture. Every section says whether it shows historical statistics, current verified information or a model estimate. */
export function MatchPage({ fixtureId }: { fixtureId: string }) {
  const [tz, setTz] = useZone();
  const [m, setM] = useState<Match | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    call<Match>(`football/live/fixtures/${fixtureId}/match`).then((x) => { if (live) { setM(x); setErr(null); } }, (e) => { if (live) setErr(e instanceof Error ? e.message : "Could not load this match."); });
    return () => { live = false; };
  }, [fixtureId]);

  async function request() {
    setBusy(true); setMsg(null);
    try {
      const r = await call<{ status: string; message?: string; version_no?: number }>(`football/live/fixtures/${fixtureId}/forecast`, { method: "POST" });
      setMsg(r.status === "created" ? `Stored forecast version ${r.version_no}.` : r.message ?? "Nothing has changed.");
      setM(await call<Match>(`football/live/fixtures/${fixtureId}/match`));
    } catch (e) { setMsg(e instanceof Error ? e.message : "Could not generate a forecast."); } finally { setBusy(false); }
  }

  if (err) return <><ErrorPanel message={err} /><p className="mt-3"><Link href="/dashboard/sports/live" className="text-sm text-violet underline">Back to Live Predictions</Link></p></>;
  if (!m) return <p className="text-sm text-muted" aria-busy="true">Loading match…</p>;
  const { fixture: f, forecast: fc, form, goals, availability: av } = m;
  const v = fc.version;
  const zones = ZONES.includes(tz) ? ZONES : [tz, ...ZONES];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link href="/dashboard/sports/live" className="text-sm text-violet underline">← Live Predictions</Link>
        <div><label htmlFor="mp-tz" className="mr-2 text-xs text-muted">Time zone</label><select id="mp-tz" value={tz} onChange={(e) => setTz(e.target.value)} className={field}>{zones.map((z) => <option key={z} value={z}>{z.replace(/_/g, " ")}</option>)}</select></div>
      </div>
      <dl className="flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-muted" aria-label="What the labels mean">
        {(Object.keys(KIND) as Kind[]).map((k) => <div key={k} className="flex gap-1.5"><dt><Badge tone={KIND[k].tone}>{KIND[k].label}</Badge></dt><dd>{m.kinds[k].split(": ")[1]}</dd></div>)}
      </dl>

      <Section id="sec-overview" title="A. Match overview" kind="verified" right={<StatusBadge status={f.status} />}>
        <p className="text-xl font-bold">{f.home_team} <span className="font-normal text-muted">v</span> {f.away_team}{f.final_score && <span className="ml-2 font-mono">{f.final_score.home}–{f.final_score.away}</span>}</p>
        <p className="text-sm text-muted">{kickoff(f.kickoff_utc, tz)} · Premier League {f.season}{f.matchday ? ` · Matchday ${f.matchday}` : ""}{f.venue ? ` · ${f.venue}` : ""}</p>
        <p className="mt-1 text-xs text-muted">Source: {f.source}.{f.provider_updated_at ? ` Provider data updated ${stamp(f.provider_updated_at, tz)}.` : ""} Last verified {stamp(f.last_synced_at, tz)}.</p>
        {!f.forecastable && f.status !== "finished" && f.status !== "awarded" && <p className="mt-2 text-sm text-amber-200">This match is {f.status.replace("_", " ")}, so it has no active forecast.</p>}
      </Section>

      <Section id="sec-forecast" title="B. Home, draw and away forecast" kind="model" right={v ? <ModelBadge model={v.model} /> : undefined}>
        {v ? (
          <>
            <ProbBar percent={v.percent} home={f.home_team} away={f.away_team} />
            <p className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">{v.official ? <Badge tone="green">Official forecast</Badge> : <Badge tone="muted">Version {v.version_no}</Badge>} Made {stamp(v.generated_at, tz)} · {CHECKPOINT[v.checkpoint] ?? v.checkpoint}: {v.refresh_reason}</p>
            <Note>{v.label}</Note>
          </>
        ) : <Empty>{fc.no_forecast_reason}</Empty>}
        <div className="mt-3 flex flex-wrap items-center gap-3">
          {f.forecastable && <button type="button" onClick={request} disabled={busy} className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? "Working…" : v ? "Check for a newer forecast" : "Generate forecast"}</button>}
          {msg && <p role="status" className="text-sm text-muted">{msg}</p>}
        </div>
        <Note>{fc.official_note}</Note>
      </Section>

      <Section id="sec-form" title="C. Team form comparison" kind="historical" right={<span className="text-[11px] text-muted">to {form.cutoff}</span>}>
        {form.summary ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs sm:text-sm">
              <caption className="sr-only">Form of {f.home_team} and {f.away_team}</caption>
              <thead><tr className="text-left text-xs text-muted"><th scope="col" className="py-1 font-normal">Measure</th><th scope="col" className="font-normal">{f.home_team}</th><th scope="col" className="font-normal">{f.away_team}</th></tr></thead>
              <tbody>{([["League position", "league_position", 0], ["Points", "points", 0], ["Elo rating", "elo", 0], ["Form, last 5", "form_5", -1], ["Points per match, last 5", "form_5_ppg", 2], ["Points per match, last 10", "form_10_ppg", 2], ["Goals scored per match", "goals_for_avg", 2], ["Goals conceded per match", "goals_against_avg", 2], ["Clean sheets", "clean_sheet_rate", -2], ["Days since last match", "rest_days", 0], ["Matches in the data", "matches_played", 0]] as [string, keyof Summary, number][]).map(([label, k, d]) => {
                const fmt = (x: number | string | null) => (x === null || x === undefined ? "n/a" : d === -1 ? String(x) : d === -2 ? pct(Number(x), 0) : Number(x).toFixed(d));
                return <tr key={k} className="border-t border-line"><th scope="row" className="py-1.5 pr-3 text-left font-normal">{label}</th><td className="font-mono">{fmt(form.summary!.home[k])}</td><td className="font-mono">{fmt(form.summary!.away[k])}</td></tr>;
              })}</tbody>
            </table>
          </div>
        ) : <Empty>No forecast has been made, so there is no frozen snapshot of form to show.</Empty>}
        <div className="mt-4 grid gap-4 sm:grid-cols-2"><Recents team={f.home_team} rows={form.recent.home} /><Recents team={f.away_team} rows={form.recent.away} /></div>
        <Note>{form.note}</Note>
      </Section>

      <Section id="sec-venue" title="D. Home and away performance" kind="historical">
        <div className="overflow-x-auto">
          <table className="w-full text-xs sm:text-sm">
            <caption className="sr-only">Home and away records</caption>
            <thead><tr className="text-left text-xs text-muted"><th scope="col" className="py-1 font-normal">Record</th><th scope="col" className="font-normal">Played</th><th scope="col" className="font-normal">Scored</th><th scope="col" className="font-normal">Conceded</th><th scope="col" className="font-normal">Points</th></tr></thead>
            <tbody>
              <RecordRow label={`${f.home_team} at home`} r={m.venue_performance.home_team_at_home} /><RecordRow label={`${f.home_team} away`} r={m.venue_performance.home_team_away} />
              <RecordRow label={`${f.away_team} at home`} r={m.venue_performance.away_team_at_home} /><RecordRow label={`${f.away_team} away`} r={m.venue_performance.away_team_away} />
            </tbody>
          </table>
        </div>
        <Note>Goals and points are per match. {m.venue_performance.note}</Note>
      </Section>

      <Section id="sec-h2h" title="E. Head-to-head results" kind="historical">
        {m.head_to_head.meetings.length === 0 ? <Empty>No earlier meetings in the imported results.</Empty> : (
          <>
            {m.head_to_head.summary && <p className="mb-2 text-sm">{m.head_to_head.summary.meetings} meetings: {f.home_team} won {m.head_to_head.summary.home_team_wins}, drawn {m.head_to_head.summary.draws}, {f.away_team} won {m.head_to_head.summary.away_team_wins}.</p>}
            <ul className="divide-y divide-line text-sm" aria-label="Earlier meetings">{m.head_to_head.meetings.map((x) => <li key={x.date} className="flex flex-wrap justify-between gap-2 py-1.5"><span>{x.home_team} <span className="font-mono">{x.home_goals}–{x.away_goals}</span> {x.away_team}</span><span className="text-xs text-muted">{x.date} · {x.season}</span></li>)}</ul>
          </>
        )}
        <Note>{m.head_to_head.note}</Note>
      </Section>

      <Section id="sec-goals" title="F. Expected goals and score distribution" kind="model">
        {goals.expected && v ? (
          <>
            <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <div><dt className="text-xs text-muted">Expected goals</dt><dd className="font-mono">{num(goals.expected.home)} – {num(goals.expected.away)}</dd></div>
              <div><dt className="text-xs text-muted">Over / under 2.5</dt><dd className="font-mono">{goals.over_2_5 === null ? "n/a" : `${pct(goals.over_2_5, 0)} / ${pct(1 - goals.over_2_5, 0)}`}</dd></div>
              <div><dt className="text-xs text-muted">Both teams score</dt><dd className="font-mono">{goals.both_teams_to_score === null ? "n/a" : pct(goals.both_teams_to_score, 0)}</dd></div>
              <div><dt className="text-xs text-muted">Likeliest scores</dt><dd className="font-mono text-xs">{goals.top_scorelines?.map((s) => `${s.home}–${s.away}`).join("  ")}</dd></div>
            </dl>
            {goals.score_grid && <div className="mt-4"><Grid g={goals.score_grid} home={f.home_team} away={f.away_team} /></div>}
          </>
        ) : <Empty>No forecast has been made, so there is no expected-goals estimate.</Empty>}
        {goals.provider_xg && (
          <p className="mt-3 text-xs">Measured expected goals from your uploaded statistics (historical, last matches): {f.home_team} {num(goals.provider_xg.home.xg_for)} for / {num(goals.provider_xg.home.xg_against)} against; {f.away_team} {num(goals.provider_xg.away.xg_for)} for / {num(goals.provider_xg.away.xg_against)} against.</p>
        )}
        <Note>{goals.note}</Note>
      </Section>

      <Section id="sec-avail" title="G. Player availability" kind="verified" right={<Badge tone={av.status === "unavailable" ? "amber" : "green"}>{av.status}</Badge>}>
        {av.reports.length > 0 ? (
          <ul className="space-y-1 text-sm" aria-label="Availability reports">{av.reports.map((r) => <li key={r.team + r.player}>{r.player} ({r.team}): {r.status}, from {r.from_date}{r.to_date ? ` to ${r.to_date}` : ""}. <span className="text-xs text-muted">Reported {stamp(r.reported_at, tz)}.</span></li>)}</ul>
        ) : <p className="text-sm">{av.note}</p>}
        <Note>Source: {av.source}.{av.reports.length > 0 ? ` ${av.note}` : ""}</Note>
      </Section>

      <Section id="sec-drivers" title="H. Key prediction drivers" kind="model">
        {m.drivers.items.length ? <ul className="space-y-1.5 text-sm" aria-label="Prediction drivers">{m.drivers.items.map((d, i) => <Driver key={i} d={d} />)}</ul> : <Empty>No forecast has been made.</Empty>}
        <Note>{m.drivers.note} Effects are on log expected goals.</Note>
        {m.warnings.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-amber-200" aria-label="Data-quality warnings">{m.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
        {m.data_completeness && <Note>{m.data_completeness.available} of {m.data_completeness.of} data factors available, {m.data_completeness.partial} partly.</Note>}
      </Section>

      <Section id="sec-revisions" title="I. Forecast revision history" kind="model" right={<span className="text-[11px] text-muted">{fc.versions} version{fc.versions === 1 ? "" : "s"}</span>}>
        {m.revisions.versions.length === 0 ? <Empty>No forecast versions have been stored.</Empty> : (
          <ol className="divide-y divide-line" aria-label="Forecast versions, newest first">{m.revisions.versions.map((x) => (
            <li key={x.id} className="py-3">
              <div className="flex flex-wrap items-center gap-2 text-sm"><Badge tone="muted">Version {x.version_no}</Badge>{x.official && <Badge tone="green">Official</Badge>}<ModelBadge model={x.model} /><span className="text-xs text-muted">{stamp(x.generated_at, tz)}</span></div>
              <p className="mt-0.5 text-xs text-muted">{CHECKPOINT[x.checkpoint] ?? x.checkpoint}: {x.refresh_reason}</p>
              <div className="mt-2 max-w-md"><ProbBar percent={x.percent} home={f.home_team} away={f.away_team} compact /></div>
              {x.change_from_previous && <p className="mt-1 text-[11px] text-muted">Largest move since version {x.change_from_previous.previous_version}: {(x.change_from_previous.max_abs_change * 100).toFixed(1)} points{x.change_from_previous.significant ? " (significant)" : ""}.</p>}
            </li>
          ))}</ol>
        )}
        {m.revisions.status_history.length > 0 && (
          <div className="mt-3"><h3 className="mb-1 text-xs font-semibold text-muted">Fixture changes seen by the provider</h3>
            <ul className="space-y-1 text-xs" aria-label="Fixture status and kickoff changes">{m.revisions.status_history.map((h, i) => <li key={i}>{stamp(h.observed_at, tz)}: {h.old_status ? `${h.old_status} → ` : "first seen as "}{h.new_status}{h.old_kickoff && h.new_kickoff && h.old_kickoff !== h.new_kickoff ? `, kickoff moved from ${kickoff(h.old_kickoff, tz)} to ${kickoff(h.new_kickoff, tz)}` : ""}</li>)}</ul></div>
        )}
        <Note>Earlier versions are never edited or removed. {v ? `Fixture reference: ${v.provider_refs.fixture_provider ?? "uploaded file"}${v.provider_refs.provider_fixture_id ? ` id ${v.provider_refs.provider_fixture_id}` : ""}; results history as of ${v.provider_refs.results_history_as_of ?? "unknown"}.` : ""}</Note>
      </Section>

      <Result m={m} />
      <Panel><p className="text-xs text-muted">Forecasts are model estimates made before kickoff and are not certainties or betting or financial advice. <Link href={`/dashboard/sports/live?tab=history&fixture=${f.id}`} className="text-violet underline">Open this match in Prediction history</Link></p></Panel>
    </div>
  );
}
