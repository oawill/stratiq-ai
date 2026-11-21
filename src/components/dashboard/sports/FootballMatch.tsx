"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { call, post } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel, pct } from "../ui";
import { field } from "../analysis";

export interface Forecast {
  name: string; p_home: number; p_draw: number; p_away: number; p_over_2_5: number | null; p_btts: number | null; expected_goals: [number, number] | null;
  top_scorelines: { home: number; away: number; p: number }[] | null;
  drivers: { factor: string; effect_home?: number; effect_away?: number; points?: number }[] | null;
}
interface Avail { status: "available" | "partial" | "unavailable"; source: string; as_of: string | null; coverage: string | null; note: string }
export interface Intel {
  home: string; away: string; kickoff: string; cutoff: string; generated_at: string; data_sha256: string; label: string;
  model_version: { version: string; tuned: boolean; note: string };
  forecasts: Record<string, Forecast>; warnings: string[];
  snapshot: { features: Record<string, unknown> & { head_to_head: { meetings: number; home_team_wins?: number; draws?: number; away_team_wins?: number; last_meeting?: string } }; availability: Record<string, Avail>; history_as_of: string | null; sha256: string };
  reliability: {
    model_probability: string;
    data_completeness: { available: number; partial: number; unavailable: number; of: number; share_available: number; missing: string[] };
    historical_calibration: { note?: string; model?: string; period?: string; matches?: number; calibration_error?: number; log_loss?: number };
    model_disagreement: { home_win_spread: number; note: string } | null;
    sample_size: { fewest_earlier_matches_for_a_team: number; note: string };
  };
  scenario?: { hypothetical: true; adjustments: Record<string, number>; forecasts: Record<string, Forecast>; note: string };
  saved?: { prediction_ids: Record<string, string> };
}

export const FACTOR_NAMES: Record<string, string> = {
  historical_performance: "Historical performance", home_away: "Home and away advantage", team_strength: "Team strength", head_to_head: "Head to head", goals: "Goals",
  expected_goals: "Expected goals", player_availability: "Player availability", squad_strength: "Squad strength", rest_fatigue: "Rest and fatigue", match_context: "Match context",
  managerial: "Managerial changes", betting_markets: "Betting markets", venue_conditions: "Venue and conditions",
};

export function useClubs() {
  const [clubs, setClubs] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    call<{ clubs: string[] }>("football/summary").then((s) => live && setClubs(s.clubs), (e) => live && setError(e instanceof Error ? e.message : "Could not load clubs."));
    return () => { live = false; };
  }, []);
  return { clubs, error };
}

export function NoHistory() {
  return <Empty>No match history yet. <Link href="/dashboard/data" className="text-violet underline">Import Premier League results</Link> on the Data page (Historical Football Data) to use football intelligence.</Empty>;
}

export function ProbBar({ h, d, a, home, away }: { h: number; d: number; a: number; home: string; away: string }) {
  return (
    <div>
      <div role="img" aria-label={`${home} ${pct(h)}, draw ${pct(d)}, ${away} ${pct(a)}`} className="flex h-3 overflow-hidden rounded-full bg-line">
        <div style={{ width: `${h * 100}%` }} className="bg-primary" /><div style={{ width: `${d * 100}%` }} className="bg-muted/60" /><div style={{ width: `${a * 100}%` }} className="bg-violet" />
      </div>
      <div className="mt-1 flex justify-between font-mono text-xs"><span>{home} {pct(h)}</span><span>Draw {pct(d)}</span><span>{away} {pct(a)}</span></div>
    </div>
  );
}

export function ForecastTable({ forecasts, home, away }: { forecasts: Record<string, Forecast>; home: string; away: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">Forecasts by model for {home} against {away}</caption>
        <thead><tr className="text-left text-[11px] text-muted">{["Model", `${home} win`, "Draw", `${away} win`, "Over 2.5", "Both score", "Expected goals"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
        <tbody className="font-mono">
          {Object.entries(forecasts).map(([k, f]) => (
            <tr key={k} className="border-t border-line">
              <th scope="row" className="py-1.5 pr-3 text-left font-sans font-medium">{f.name}</th>
              <td className="pr-3">{pct(f.p_home)}</td><td className="pr-3">{pct(f.p_draw)}</td><td className="pr-3">{pct(f.p_away)}</td>
              <td className="pr-3">{f.p_over_2_5 === null ? "n/a" : pct(f.p_over_2_5)}</td><td className="pr-3">{f.p_btts === null ? "n/a" : pct(f.p_btts)}</td>
              <td>{f.expected_goals ? `${f.expected_goals[0].toFixed(2)} – ${f.expected_goals[1].toFixed(2)}` : "n/a"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const STATUS_TONE = { available: "green", partial: "amber", unavailable: "muted" } as const;
const num = (v: unknown, d = 2) => (typeof v === "number" ? v.toFixed(d) : "—");

/** Team comparison, drivers, availability, reliability and warnings for one fixture. */
export function IntelDetails({ m }: { m: Intel }) {
  const f = m.snapshot.features as Record<string, unknown>;
  const dc = m.forecasts.dixon_coles ?? m.forecasts.poisson;
  const rel = m.reliability;
  const h2h = m.snapshot.features.head_to_head;
  const rec = (k: string) => (f[k] as { played: number; goals_for: number | null; goals_against: number | null } | undefined);
  const rows: [string, unknown, unknown][] = [
    ["Elo-style rating", f.elo_home, f.elo_away], ["Last 5 results", f.home_form_5 || "—", f.away_form_5 || "—"], ["Points per match, last 5", f.home_form_5_ppg, f.away_form_5_ppg],
    ["Points per match, last 10", f.home_form_10_ppg, f.away_form_10_ppg], ["Goals scored per match", f.home_goals_for_avg, f.away_goals_for_avg], ["Goals conceded per match", f.home_goals_against_avg, f.away_goals_against_avg],
    ["Clean-sheet rate", f.home_clean_sheet_rate, f.away_clean_sheet_rate], ["Over 2.5 goals rate", f.home_over_2_5_rate, f.away_over_2_5_rate], ["Both teams scored rate", f.home_btts_rate, f.away_btts_rate],
    ["Attack strength", f.attack_home, f.attack_away], ["Defence (concession multiplier)", f.defence_home, f.defence_away],
    ["League position", f.home_league_position, f.away_league_position], ["Points this season", f.home_points, f.away_points], ["Days since last match", f.home_rest_days, f.away_rest_days],
  ];
  return (
    <div className="space-y-4">
      <Panel title="Most likely scorelines and expected goals" badge={<Badge tone="muted">{dc.name}</Badge>}>
        <div className="flex flex-wrap gap-2">
          {(dc.top_scorelines ?? []).map((s) => <span key={`${s.home}-${s.away}`} className="rounded-lg border border-line px-3 py-1.5 font-mono text-sm">{s.home}–{s.away} <span className="text-muted">{pct(s.p)}</span></span>)}
        </div>
        {dc.expected_goals && <p className="mt-2 text-sm">Expected goals: {m.home} {dc.expected_goals[0].toFixed(2)}, {m.away} {dc.expected_goals[1].toFixed(2)}. <span className="text-xs text-muted">Estimated from match results, not provider expected goals.</span></p>}
      </Panel>

      <Panel title="Team comparison">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">{m.home} compared with {m.away}</caption>
            <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="pr-3 font-normal">Measure</th><th scope="col" className="pr-3 font-normal">{m.home} (home)</th><th scope="col" className="font-normal">{m.away} (away)</th></tr></thead>
            <tbody className="font-mono">
              {rows.map(([label, a, b]) => <tr key={label} className="border-t border-line"><th scope="row" className="py-1 pr-3 text-left font-sans font-normal">{label}</th><td className="pr-3">{typeof a === "number" ? num(a, Number.isInteger(a) ? 0 : 2) : String(a ?? "—")}</td><td>{typeof b === "number" ? num(b, Number.isInteger(b) ? 0 : 2) : String(b ?? "—")}</td></tr>)}
              <tr className="border-t border-line"><th scope="row" className="py-1 pr-3 text-left font-sans font-normal">Home record (goals for / against)</th><td className="pr-3">{rec("home_home_record")?.played ?? 0} played · {num(rec("home_home_record")?.goals_for)} / {num(rec("home_home_record")?.goals_against)}</td><td>—</td></tr>
              <tr className="border-t border-line"><th scope="row" className="py-1 pr-3 text-left font-sans font-normal">Away record (goals for / against)</th><td className="pr-3">—</td><td>{rec("away_away_record")?.played ?? 0} played · {num(rec("away_away_record")?.goals_for)} / {num(rec("away_away_record")?.goals_against)}</td></tr>
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-sm">Head to head: {h2h.meetings ? `${h2h.meetings} earlier meeting(s): ${m.home} ${h2h.home_team_wins}, drawn ${h2h.draws}, ${m.away} ${h2h.away_team_wins}; last ${h2h.last_meeting}.` : "no earlier meetings in the imported matches."}</p>
        <p className="mt-1 text-sm">Player availability: <Badge tone="muted">Unavailable</Badge> <span className="text-xs text-muted">No injury or suspension data has been supplied, so absences are not reflected.</span></p>
      </Panel>

      <Panel title="Key prediction drivers" badge={<Badge tone="muted">{dc.name}</Badge>}>
        <p className="mb-2 text-xs text-muted">How each part of the model scales each side&apos;s expected goals (1.00 = no effect). These multiply together to give the expected goals above.</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Multipliers on expected goals</caption>
            <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="pr-3 font-normal">Factor</th><th scope="col" className="pr-3 font-normal">{m.home}</th><th scope="col" className="font-normal">{m.away}</th></tr></thead>
            <tbody className="font-mono">
              {(dc.drivers ?? []).filter((d) => d.effect_home !== undefined).map((d) => <tr key={d.factor} className="border-t border-line"><th scope="row" className="py-1 pr-3 text-left font-sans font-normal">{d.factor}</th><td className="pr-3">×{Math.exp(d.effect_home ?? 0).toFixed(2)}</td><td>×{Math.exp(d.effect_away ?? 0).toFixed(2)}</td></tr>)}
            </tbody>
          </table>
        </div>
        {m.forecasts.elo?.drivers?.[0]?.points !== undefined && <p className="mt-2 text-xs text-muted">Elo: rating gap including home advantage is {m.forecasts.elo.drivers![0].points!.toFixed(0)} points in {m.home}&apos;s favour (negative favours {m.away}).</p>}
      </Panel>

      <Panel title="How reliable is this forecast?" badge={<Badge tone="amber">Four separate measures</Badge>}>
        <dl className="space-y-3 text-sm">
          <div><dt className="font-semibold">Model probability</dt><dd className="text-muted">{rel.model_probability}</dd></div>
          <div><dt className="font-semibold">Data completeness</dt><dd className="text-muted">{rel.data_completeness.available} of {rel.data_completeness.of} factors available, {rel.data_completeness.partial} partly, {rel.data_completeness.unavailable} unavailable{rel.data_completeness.missing.length ? ` (${rel.data_completeness.missing.join(", ")})` : ""}.</dd></div>
          <div><dt className="font-semibold">Historical calibration</dt><dd className="text-muted">{rel.historical_calibration.note ?? `${rel.historical_calibration.model} on its ${rel.historical_calibration.period} period (${rel.historical_calibration.matches} matches): average gap between predicted and observed frequencies ${((rel.historical_calibration.calibration_error ?? 0) * 100).toFixed(1)} percentage points.`}</dd></div>
          <div><dt className="font-semibold">Prediction uncertainty</dt><dd className="text-muted">{rel.model_disagreement ? `Models differ on the home win by ${(rel.model_disagreement.home_win_spread * 100).toFixed(1)} points. ` : ""}Fewest earlier matches for either club: {rel.sample_size.fewest_earlier_matches_for_a_team}. {rel.sample_size.note}</dd></div>
        </dl>
      </Panel>

      <Panel title="Which factors were used">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Factor availability for this fixture</caption>
            <thead><tr className="text-left text-[11px] text-muted">{["Factor", "Status", "Source", "Note"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
            <tbody>
              {Object.entries(m.snapshot.availability).map(([k, a]) => (
                <tr key={k} className="border-t border-line align-top"><th scope="row" className="py-1.5 pr-3 text-left font-medium">{FACTOR_NAMES[k] ?? k}</th><td className="pr-3"><Badge tone={STATUS_TONE[a.status]}>{a.status === "available" ? "Available" : a.status === "partial" ? "Partial" : "Unavailable"}</Badge></td><td className="pr-3 text-xs text-muted">{a.source}{a.as_of ? ` · data to ${a.as_of}` : ""}</td><td className="text-xs text-muted">{a.note}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {m.warnings.length > 0 && (
        <div role="note" className="rounded-xl border border-amber-400/40 bg-amber-400/10 p-3 text-sm text-amber-200">
          <p className="font-semibold">Warnings</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">{m.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        </div>
      )}
      <p className="text-xs leading-relaxed text-muted">
        {m.label} Model version {m.model_version.version}: {m.model_version.note} Generated {new Date(m.generated_at).toLocaleString()}; information up to {m.cutoff}; kickoff date {m.kickoff}. Data fingerprint <span className="font-mono">{m.data_sha256.slice(0, 12)}</span>.
      </p>
    </div>
  );
}

/** Pick two clubs and (optionally) a kickoff date; shows everything known before that fixture. */
export function MatchTab({ initial }: { initial?: { home: string; away: string; kickoff?: string } | null }) {
  const { clubs, error } = useClubs();
  const [home, setHome] = useState(initial?.home ?? "");
  const [away, setAway] = useState(initial?.away ?? "");
  const [kickoff, setKickoff] = useState(initial?.kickoff ?? "");
  const [m, setM] = useState<Intel | null>(null);
  const [busy, setBusy] = useState<"run" | "save" | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function run(save: boolean) {
    setBusy(save ? "save" : "run"); setErr(null);
    try { setM(await post<Intel>("football/intel/match", { home, away, kickoff: kickoff || null, save })); } catch (e) { setErr(e instanceof Error ? e.message : "Could not build the forecast."); } finally { setBusy(null); }
  }
  useEffect(() => {
    if (initial?.home && initial?.away) {
      let live = true;
      post<Intel>("football/intel/match", { home: initial.home, away: initial.away, kickoff: initial.kickoff || null, save: false }).then((r) => live && setM(r), (e) => live && setErr(e instanceof Error ? e.message : "Could not build the forecast."));
      return () => { live = false; };
    }
  }, [initial]);

  if (error) return <ErrorPanel message={error} />;
  if (!clubs) return <p className="text-sm text-muted" aria-busy="true">Loading…</p>;
  if (!clubs.length) return <NoHistory />;
  return (
    <div className="space-y-4">
      <Panel title="Match intelligence" badge={<Badge tone="amber">Model forecast</Badge>}>
        <div className="flex flex-wrap items-end gap-3">
          <div><label htmlFor="fi-home" className="mb-1 block text-xs text-muted">Home team</label>
            <select id="fi-home" value={home} onChange={(e) => { setHome(e.target.value); setM(null); }} className={field}><option value="">Choose…</option>{clubs.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
          <div><label htmlFor="fi-away" className="mb-1 block text-xs text-muted">Away team</label>
            <select id="fi-away" value={away} onChange={(e) => { setAway(e.target.value); setM(null); }} className={field}><option value="">Choose…</option>{clubs.filter((c) => c !== home).map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
          <div><label htmlFor="fi-ko" className="mb-1 block text-xs text-muted">Kickoff date (optional)</label>
            <input id="fi-ko" type="date" value={kickoff} onChange={(e) => { setKickoff(e.target.value); setM(null); }} className={field} /></div>
          <button type="button" disabled={!home || !away || busy !== null} onClick={() => run(false)} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
            {busy === "run" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Analyse match
          </button>
        </div>
        <p className="mt-2 text-xs text-muted">Leave the date empty for today. A past date shows exactly what was known before that match, which is how history is tested without hindsight.</p>
        {err && <p role="alert" className="mt-3 text-sm text-red-300">{err}</p>}
      </Panel>
      {m && (
        <>
          <Panel title={`${m.home} vs ${m.away}`} badge={<Badge tone="muted">{m.model_version.tuned ? "Tuned settings" : "Default settings"}</Badge>}>
            <div className="space-y-4" aria-live="polite">
              <ProbBar h={(m.forecasts.dixon_coles ?? m.forecasts.poisson).p_home} d={(m.forecasts.dixon_coles ?? m.forecasts.poisson).p_draw} a={(m.forecasts.dixon_coles ?? m.forecasts.poisson).p_away} home={m.home} away={m.away} />
              <ForecastTable forecasts={m.forecasts} home={m.home} away={m.away} />
              {m.saved ? <p role="status" className="text-sm text-success">Saved. It will be scored against the real result once that result is imported.</p> : (
                <button type="button" disabled={busy !== null} onClick={() => run(true)} className="inline-flex items-center gap-2 rounded-xl border border-violet/60 px-4 py-2 text-sm font-semibold text-violet hover:bg-violet/10 disabled:opacity-50">
                  {busy === "save" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Save forecast
                </button>
              )}
            </div>
          </Panel>
          <IntelDetails m={m} />
        </>
      )}
    </div>
  );
}

const SLIDERS: { key: string; label: string; min: number; max: number; step: number; neutral: number; fmt: (v: number) => string }[] = [
  { key: "home_advantage_multiplier", label: "Home advantage", min: 0.5, max: 1.5, step: 0.05, neutral: 1, fmt: (v) => `×${v.toFixed(2)}` },
  { key: "home_attack_multiplier", label: "Home attack strength", min: 0.5, max: 1.5, step: 0.05, neutral: 1, fmt: (v) => `×${v.toFixed(2)}` },
  { key: "home_defence_multiplier", label: "Home goals conceded", min: 0.5, max: 1.5, step: 0.05, neutral: 1, fmt: (v) => `×${v.toFixed(2)}` },
  { key: "away_attack_multiplier", label: "Away attack strength", min: 0.5, max: 1.5, step: 0.05, neutral: 1, fmt: (v) => `×${v.toFixed(2)}` },
  { key: "away_defence_multiplier", label: "Away goals conceded", min: 0.5, max: 1.5, step: 0.05, neutral: 1, fmt: (v) => `×${v.toFixed(2)}` },
  { key: "home_missing_attack_loss", label: "Home: attack lost to absent key players (your assumption)", min: 0, max: 0.5, step: 0.05, neutral: 0, fmt: (v) => `${Math.round(v * 100)}%` },
  { key: "away_missing_attack_loss", label: "Away: attack lost to absent key players (your assumption)", min: 0, max: 0.5, step: 0.05, neutral: 0, fmt: (v) => `${Math.round(v * 100)}%` },
  { key: "home_missing_defence_loss", label: "Home: extra goals conceded without key players (your assumption)", min: 0, max: 0.5, step: 0.05, neutral: 0, fmt: (v) => `+${Math.round(v * 100)}%` },
  { key: "away_missing_defence_loss", label: "Away: extra goals conceded without key players (your assumption)", min: 0, max: 0.5, step: 0.05, neutral: 0, fmt: (v) => `+${Math.round(v * 100)}%` },
  { key: "home_rating_points", label: "Home Elo rating change (points)", min: -200, max: 200, step: 10, neutral: 0, fmt: (v) => `${v > 0 ? "+" : ""}${v}` },
  { key: "away_rating_points", label: "Away Elo rating change (points)", min: -200, max: 200, step: 10, neutral: 0, fmt: (v) => `${v > 0 ? "+" : ""}${v}` },
];

/** What-if scenarios. Clearly hypothetical, built only from inputs the models actually have. */
export function SimulatorTab() {
  const { clubs, error } = useClubs();
  const [home, setHome] = useState("");
  const [away, setAway] = useState("");
  const [vals, setVals] = useState<Record<string, number>>({});
  const [m, setM] = useState<Intel | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const changed = Object.fromEntries(SLIDERS.filter((s) => vals[s.key] !== undefined && vals[s.key] !== s.neutral).map((s) => [s.key, vals[s.key]]));

  async function run() {
    setBusy(true); setErr(null);
    try { setM(await post<Intel>("football/intel/match", { home, away, adjust: changed })); } catch (e) { setErr(e instanceof Error ? e.message : "Could not recalculate."); } finally { setBusy(false); }
  }
  if (error) return <ErrorPanel message={error} />;
  if (!clubs) return <p className="text-sm text-muted" aria-busy="true">Loading…</p>;
  if (!clubs.length) return <NoHistory />;
  const sc = m?.scenario;
  const base = m ? (m.forecasts.dixon_coles ?? m.forecasts.poisson) : null;
  const hyp = sc ? (sc.forecasts.dixon_coles ?? sc.forecasts.poisson) : null;
  return (
    <div className="space-y-4">
      <Panel title="Prediction simulator" badge={<Badge tone="amber">Hypothetical, not a forecast</Badge>}>
        <p className="mb-3 text-xs leading-relaxed text-muted">Change the assumptions and see what the models would say if they were true. Only inputs the models actually use can be changed. Missing-player effects are percentages you choose; they are not estimated from data.</p>
        <div className="flex flex-wrap items-end gap-3">
          <div><label htmlFor="sim-home" className="mb-1 block text-xs text-muted">Home team</label>
            <select id="sim-home" value={home} onChange={(e) => { setHome(e.target.value); setM(null); }} className={field}><option value="">Choose…</option>{clubs.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
          <div><label htmlFor="sim-away" className="mb-1 block text-xs text-muted">Away team</label>
            <select id="sim-away" value={away} onChange={(e) => { setAway(e.target.value); setM(null); }} className={field}><option value="">Choose…</option>{clubs.filter((c) => c !== home).map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {SLIDERS.map((s) => (
            <div key={s.key}>
              <label htmlFor={`sim-${s.key}`} className="flex justify-between text-xs text-muted"><span>{s.label}</span><span className="font-mono text-ink">{s.fmt(vals[s.key] ?? s.neutral)}</span></label>
              <input id={`sim-${s.key}`} type="range" min={s.min} max={s.max} step={s.step} value={vals[s.key] ?? s.neutral} onChange={(e) => { setVals({ ...vals, [s.key]: Number(e.target.value) }); }} className="w-full accent-[#8055f6]" />
            </div>
          ))}
          {["Rest days", "Expected lineups"].map((l) => (
            <div key={l} className="opacity-60">
              <label htmlFor={`sim-${l}`} className="flex justify-between text-xs text-muted"><span>{l}</span><span>not supported</span></label>
              <input id={`sim-${l}`} type="range" disabled className="w-full" />
              <p className="text-[11px] text-muted">The models were not trained with {l.toLowerCase()}, so changing them would be a guess. Shown for transparency.</p>
            </div>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" disabled={!home || !away || busy} onClick={run} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Recalculate</button>
          <button type="button" onClick={() => { setVals({}); setM(null); }} className="rounded-xl border border-line px-4 py-2 text-sm text-muted hover:text-ink">Reset assumptions</button>
        </div>
        {err && <p role="alert" className="mt-3 text-sm text-red-300">{err}</p>}
      </Panel>
      {m && base && (
        <Panel title={`${m.home} vs ${m.away}`}>
          <div className="space-y-4" aria-live="polite">
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Forecast from the data</p>
              <ProbBar h={base.p_home} d={base.p_draw} a={base.p_away} home={m.home} away={m.away} />
            </div>
            {hyp && sc ? (
              <div className="rounded-xl border-2 border-dashed border-amber-400/60 p-3">
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-amber-200">Hypothetical scenario (not a forecast)</p>
                <ProbBar h={hyp.p_home} d={hyp.p_draw} a={hyp.p_away} home={m.home} away={m.away} />
                <p className="mt-2 font-mono text-xs">Change in {m.home} win: {((hyp.p_home - base.p_home) * 100).toFixed(1)} points · draw: {((hyp.p_draw - base.p_draw) * 100).toFixed(1)} · {m.away} win: {((hyp.p_away - base.p_away) * 100).toFixed(1)}</p>
                <div className="mt-3"><ForecastTable forecasts={sc.forecasts} home={m.home} away={m.away} /></div>
                <p className="mt-2 text-xs text-amber-200">{sc.note}</p>
              </div>
            ) : <p className="text-sm text-muted">No assumptions changed, so there is no scenario: this is the forecast from the data.</p>}
          </div>
        </Panel>
      )}
    </div>
  );
}
