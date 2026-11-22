"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { call } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel, pct } from "../../ui";
import { field } from "../../analysis";
import { MODEL_LABEL, stamp } from "./live";

interface Agg { n: number; log_loss?: number; brier?: number; rps?: number; accuracy?: number; beats_no_information?: boolean; enough_matches_to_judge?: boolean; vs_no_information?: { log_loss: number; brier: number; rps: number } }
interface Perf {
  days: number | null; overall: Agg; by_model: Record<string, Agg>; home_win_calibration: { low: number; high: number; n: number; mean_forecast: number | null; home_win_rate: number | null }[];
  best: { fixture_id: string; match: string; date: string; log_loss: number }[]; worst: { fixture_id: string; match: string; date: string; log_loss: number }[];
  corrections: number; voided_matches: number; result_conflicts: number; baseline: { description: string; log_loss: number; brier: number }; note: string;
}
interface Report { id: string; period: "daily" | "weekly"; window_start: string; window_end: string; summary: { overall: Agg }; created_at: string }
const f3 = (x?: number) => (x === undefined ? "n/a" : x.toFixed(3));

/** How the official pre-kickoff forecasts have scored against verified results, with the honest caveat about small samples. */
export function LiveRecord({ tz }: { tz: string }) {
  const [days, setDays] = useState(0);
  const [p, setP] = useState<Perf | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([call<Perf>(`football/live/performance?days=${days}`), call<{ reports: Report[] }>("football/live/performance/reports?limit=5")]).then(([a, b]) => { if (live) { setP(a); setReports(b.reports); setErr(null); } },
      (e) => { if (live) setErr(e instanceof Error ? e.message : "Could not load the live record."); });
    return () => { live = false; };
  }, [days]);

  if (err) return <ErrorPanel message={err} />;
  if (!p) return <p className="text-sm text-muted" aria-busy="true">Loading the live record…</p>;
  const o = p.overall;
  return (
    <Panel title="Live forecast record" badge={<Badge tone="muted">Official pre-kickoff forecasts only</Badge>}>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <p className="text-xs text-muted">Each completed match is scored once, against the last forecast made before kickoff.</p>
        <div><label htmlFor="rec-days" className="mr-2 text-xs text-muted">Period</label><select id="rec-days" value={days} onChange={(e) => setDays(Number(e.target.value))} className={field}><option value={0}>All time</option><option value={30}>Last 30 days</option><option value={7}>Last 7 days</option></select></div>
      </div>
      {o.n === 0 ? <Empty>No completed matches have been scored yet. A match is scored automatically after the provider reports a verified full-time result.</Empty> : (
        <div className="space-y-4">
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
            <div><dt className="text-xs text-muted">Matches scored</dt><dd className="font-mono">{o.n}</dd></div>
            <div><dt className="text-xs text-muted">Right result most likely</dt><dd className="font-mono">{o.accuracy !== undefined ? pct(o.accuracy, 0) : "n/a"}</dd></div>
            <div><dt className="text-xs text-muted">Log loss</dt><dd className="font-mono">{f3(o.log_loss)}</dd></div>
            <div><dt className="text-xs text-muted">Brier score</dt><dd className="font-mono">{f3(o.brier)}</dd></div>
            <div><dt className="text-xs text-muted">Ranked probability</dt><dd className="font-mono">{f3(o.rps)}</dd></div>
          </dl>
          <p className="text-sm">
            {o.beats_no_information ? "On log loss these forecasts have so far done better than a forecast of one third each, which carries no information." : "On log loss these forecasts have so far not done better than a forecast of one third each, which carries no information."}
            {" "}<span className="text-muted">(That forecast scores {p.baseline.log_loss.toFixed(3)} log loss and {p.baseline.brier.toFixed(3)} Brier; lower is better for all three scores.)</span>
          </p>
          <p className={`text-xs ${o.enough_matches_to_judge ? "text-muted" : "text-amber-200"}`}>{p.note}</p>
          {Object.keys(p.by_model).length > 0 && (
            <div className="overflow-x-auto"><table className="w-full text-xs sm:text-sm"><caption className="sr-only">Scores by model</caption>
              <thead><tr className="text-left text-xs text-muted"><th scope="col" className="py-1 font-normal">Model</th><th scope="col" className="font-normal">Matches</th><th scope="col" className="font-normal">Log loss</th><th scope="col" className="font-normal">Brier</th><th scope="col" className="font-normal">Right</th></tr></thead>
              <tbody>{Object.entries(p.by_model).map(([m, a]) => <tr key={m} className="border-t border-line"><th scope="row" className="py-1.5 pr-3 text-left font-normal">{MODEL_LABEL[m] ?? m}</th><td className="font-mono">{a.n}</td><td className="font-mono">{f3(a.log_loss)}</td><td className="font-mono">{f3(a.brier)}</td><td className="font-mono">{a.accuracy !== undefined ? pct(a.accuracy, 0) : "n/a"}</td></tr>)}</tbody></table></div>
          )}
          <details>
            <summary className="cursor-pointer text-xs font-semibold text-violet">Calibration, best and worst forecasts</summary>
            <div className="mt-3 space-y-3">
              <div className="overflow-x-auto"><table className="w-full text-xs"><caption className="mb-1 text-left text-muted">When the home-win forecast was in each range, how often the home side won</caption>
                <thead><tr className="text-left text-muted"><th scope="col" className="font-normal">Forecast range</th><th scope="col" className="font-normal">Matches</th><th scope="col" className="font-normal">Average forecast</th><th scope="col" className="font-normal">Home won</th></tr></thead>
                <tbody>{p.home_win_calibration.map((b) => <tr key={b.low} className="border-t border-line"><th scope="row" className="py-1 text-left font-normal">{pct(b.low, 0)}–{pct(b.high, 0)}</th><td className="font-mono">{b.n}</td><td className="font-mono">{b.mean_forecast === null ? "–" : pct(b.mean_forecast, 0)}</td><td className="font-mono">{b.home_win_rate === null ? "–" : pct(b.home_win_rate, 0)}</td></tr>)}</tbody></table></div>
              {p.best.length > 0 && <p className="text-xs">Best: {p.best.map((x, i) => <span key={x.fixture_id}>{i ? "; " : ""}<Link href={`/dashboard/sports/football/matches/${x.fixture_id}`} className="text-violet underline">{x.match}</Link> ({x.log_loss})</span>)}</p>}
              {p.worst.length > 0 && <p className="text-xs">Worst: {p.worst.map((x, i) => <span key={x.fixture_id}>{i ? "; " : ""}<Link href={`/dashboard/sports/football/matches/${x.fixture_id}`} className="text-violet underline">{x.match}</Link> ({x.log_loss})</span>)}</p>}
              <p className="text-xs text-muted">{p.corrections} score correction{p.corrections === 1 ? "" : "s"} from the provider, {p.voided_matches} match{p.voided_matches === 1 ? "" : "es"} withdrawn, {p.result_conflicts} result conflict{p.result_conflicts === 1 ? "" : "s"} with uploaded data awaiting a person&apos;s check.</p>
            </div>
          </details>
        </div>
      )}
      {reports.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-1 text-xs font-semibold text-muted">Recent reports</h3>
          <ul className="space-y-1 text-xs" aria-label="Performance reports">{reports.map((r) => <li key={r.id}><span className="capitalize">{r.period}</span> to {stamp(r.window_end, tz)}: {r.summary.overall.n} match{r.summary.overall.n === 1 ? "" : "es"} scored, log loss {f3(r.summary.overall.log_loss)}, right result most likely {r.summary.overall.accuracy !== undefined ? pct(r.summary.overall.accuracy, 0) : "n/a"}.</li>)}</ul>
        </div>
      )}
      <p className="mt-3 text-[11px] text-muted">For thousands of past matches, with leak-free testing, see the <Link href="/dashboard/sports?tab=football" className="text-violet underline">Model performance laboratory</Link>.</p>
    </Panel>
  );
}
