"use client";

import Link from "next/link";
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { post } from "@/lib/client";
import type { SportsOutputs } from "@/lib/types";
import { Badge, Empty, ErrorPanel, Panel, dt, pct } from "../ui";
import { field } from "../analysis";
import { useDatasets } from "../data/shared";
import { Outcomes, Plain } from "./Projection";

interface Forecast {
  id: string | null;
  created_at: string | null;
  feature_cutoff: string;
  model: { name: string; version: string };
  inputs: { matches_used: number; home_team_matches: number; away_team_matches: number; dataset: string; dataset_sha256: string; fit_converged: boolean };
  outputs: SportsOutputs;
}

interface Backtest {
  sample_size: number;
  matches: number;
  min_train: number;
  first_scored: string;
  last_scored: string;
  brier: number;
  baseline_brier: number;
  log_loss: number;
  baseline_log_loss: number;
  log_loss_gain: number;
  log_loss_gain_se: number;
  gain_is_clear: boolean;
  accuracy: number;
  baseline_accuracy: number;
  reliability: { low: number; high: number; count: number; mean_predicted: number; observed: number }[];
}

/** Reads the backtest numbers in plain words, without claiming more than the sample supports. */
function verdict(b: Backtest): string {
  if (b.gain_is_clear) return `On these ${b.sample_size} matches the model beat the simple baseline by a margin larger than chance alone would usually explain.`;
  if (b.log_loss_gain > 0) return `The model scored slightly better than the baseline on these ${b.sample_size} matches, but the gap is small enough that luck could explain it. Treat it as unproven.`;
  return `The model did not beat the baseline on these ${b.sample_size} matches. On this data its forecasts add nothing over the overall home, draw and away rates.`;
}

function BacktestPanel({ dsId, adv }: { dsId: string; adv: boolean }) {
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<Backtest | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [forId, setForId] = useState(dsId);
  if (forId !== dsId) { setForId(dsId); setRes(null); setErr(null); }

  async function run() {
    setBusy(true);
    setErr(null);
    try {
      setRes(await post<Backtest>(`data/datasets/${dsId}/backtest`, {}));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not run the test.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel title="How accurate is it on your data?" badge={<Badge tone="muted">Backtest</Badge>}>
      <p className="text-xs leading-relaxed text-muted">
        Replays your most recent matches one by one: each is predicted using only the matches before it, then compared with what happened. The model is scored against a baseline that only knows the overall home, draw and away rates.
      </p>
      <button type="button" disabled={busy} onClick={run} className="mt-3 inline-flex items-center gap-2 rounded-xl border border-violet/60 px-4 py-2 text-sm font-semibold text-violet hover:bg-violet/10 disabled:opacity-50">
        {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Test on my data
      </button>
      {err && <p role="alert" className="mt-3 text-sm text-red-300">{err}</p>}
      {res && (
        <div className="mt-4 space-y-4" aria-live="polite">
          <p className="text-sm leading-relaxed">{verdict(res)}</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Backtest scores, model against baseline</caption>
              <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="pr-3 font-normal">Measure</th><th scope="col" className="pr-3 font-normal">Model</th><th scope="col" className="pr-3 font-normal">Baseline</th><th scope="col" className="font-normal">Better is</th></tr></thead>
              <tbody className="font-mono">
                <tr><th scope="row" className="pr-3 text-left font-sans font-normal">Log loss</th><td className="pr-3">{res.log_loss.toFixed(3)}</td><td className="pr-3">{res.baseline_log_loss.toFixed(3)}</td><td className="font-sans text-xs text-muted">lower</td></tr>
                <tr><th scope="row" className="pr-3 text-left font-sans font-normal">Brier score</th><td className="pr-3">{res.brier.toFixed(3)}</td><td className="pr-3">{res.baseline_brier.toFixed(3)}</td><td className="font-sans text-xs text-muted">lower</td></tr>
                <tr><th scope="row" className="pr-3 text-left font-sans font-normal">Right result called</th><td className="pr-3">{pct(res.accuracy)}</td><td className="pr-3">{pct(res.baseline_accuracy)}</td><td className="font-sans text-xs text-muted">higher</td></tr>
              </tbody>
            </table>
          </div>
          {res.reliability.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="mb-1 text-left text-xs text-muted">When the model gave an outcome this chance, how often it happened</caption>
                <thead><tr className="text-left text-[11px] text-muted"><th scope="col" className="pr-3 font-normal">Model said</th><th scope="col" className="pr-3 font-normal">Average said</th><th scope="col" className="pr-3 font-normal">Happened</th><th scope="col" className="font-normal">Cases</th></tr></thead>
                <tbody className="font-mono">
                  {res.reliability.map((r) => (
                    <tr key={r.low}><th scope="row" className="pr-3 text-left font-sans font-normal">{pct(r.low)} to {pct(r.high)}</th><td className="pr-3">{pct(r.mean_predicted)}</td><td className="pr-3">{pct(r.observed)}</td><td>{r.count}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-xs leading-relaxed text-muted">
            Scored {res.sample_size} matches from {res.first_scored} to {res.last_scored}, each with at least {res.min_train} earlier matches to learn from. A few hundred matches can only show large differences, and a good score on past matches does not guarantee future ones. This tests the model on your data; it is not a promise about any league, and it is not betting or financial advice.
          </p>
          {adv && <p className="font-mono text-xs text-muted">log-loss gain {res.log_loss_gain.toFixed(4)} ± {res.log_loss_gain_se.toFixed(4)} (1 s.e.) · n={res.sample_size} of {res.matches}</p>}
        </div>
      )}
    </Panel>
  );
}

/** Forecasts from the user's own uploaded results: ratings are fitted on exactly those matches. */
export function DataForecastTab({ adv }: { adv: boolean }) {
  const { list, error } = useDatasets(["sports_results"]);
  const [dsId, setDsId] = useState("");
  const [home, setHome] = useState("");
  const [away, setAway] = useState("");
  const [busy, setBusy] = useState<"run" | "save" | null>(null);
  const [res, setRes] = useState<Forecast | null>(null);
  const [err, setErr] = useState<string | null>(null);

  if (error) return <ErrorPanel message={error} />;
  if (!list) return <p className="text-sm text-muted" aria-busy="true">Loading…</p>;
  if (list.length === 0) {
    return <Empty>No sports data yet. <Link href="/dashboard/data" className="text-violet underline">Upload your match results</Link> (a CSV of dates, teams and goals) to forecast with your own data.</Empty>;
  }
  const ds = list.find((d) => d.id === dsId);
  const teams = Object.keys(ds?.summary.team_matches ?? {});

  async function run(save: boolean) {
    setBusy(save ? "save" : "run");
    setErr(null);
    try {
      setRes(await post<Forecast>(`data/datasets/${dsId}/forecast`, { home, away, save }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not forecast.");
    } finally {
      setBusy(null);
    }
  }
  const reset = () => { setRes(null); setErr(null); };

  return (
    <div className="space-y-4">
      <Panel title="Forecast from your data" badge={<Badge tone="amber">User-supplied · unverified</Badge>}>
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label htmlFor="df-ds" className="mb-1 block text-xs text-muted">Dataset</label>
            <select id="df-ds" value={dsId} onChange={(e) => { setDsId(e.target.value); setHome(""); setAway(""); reset(); }} className={`${field} w-full`}>
              <option value="">Choose…</option>
              {list.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="df-home" className="mb-1 block text-xs text-muted">Home team</label>
            <select id="df-home" value={home} disabled={!ds} onChange={(e) => { setHome(e.target.value); reset(); }} className={`${field} w-full`}>
              <option value="">Choose…</option>{teams.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="df-away" className="mb-1 block text-xs text-muted">Away team</label>
            <select id="df-away" value={away} disabled={!ds} onChange={(e) => { setAway(e.target.value); reset(); }} className={`${field} w-full`}>
              <option value="">Choose…</option>{teams.filter((t) => t !== home).map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </div>
        <button type="button" disabled={!ds || !home || !away || busy !== null} onClick={() => run(false)} className="mt-4 inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
          {busy === "run" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Forecast
        </button>
        {err && <p role="alert" className="mt-3 text-sm text-red-300">{err}</p>}
      </Panel>

      {res && (
        <Panel title={`${home} vs ${away}`} badge={<Badge tone={res.id ? "green" : "muted"}>{res.id ? "Saved" : "Model projection · not saved"}</Badge>}>
          <div className="space-y-4">
            <Outcomes o={res.outputs} home={home} away={away} />
            <Plain o={res.outputs} home={home} away={away} />
            <div className="grid grid-cols-3 gap-3 text-center text-sm">
              <div className="rounded-xl border border-line p-2"><div className="text-[11px] text-muted">Expected goals</div><div className="font-mono font-bold">{res.outputs.home_xg.toFixed(2)} – {res.outputs.away_xg.toFixed(2)}</div></div>
              <div className="rounded-xl border border-line p-2"><div className="text-[11px] text-muted">Both teams score</div><div className="font-mono font-bold">{pct(res.outputs.p_btts)}</div></div>
              <div className="rounded-xl border border-line p-2"><div className="text-[11px] text-muted">Over 2.5 goals</div><div className="font-mono font-bold">{pct(res.outputs.p_over_2_5)}</div></div>
            </div>
            <p className="text-xs leading-relaxed text-muted">
              Ratings fitted on {res.inputs.matches_used} matches from “{res.inputs.dataset}” ({res.inputs.home_team_matches} for {home}, {res.inputs.away_team_matches} for {away}); fit {res.inputs.fit_converged ? "converged" : "did not converge"}.
              Dataset fingerprint <span className="font-mono">{res.inputs.dataset_sha256.slice(0, 12)}</span>. With few matches a team&apos;s rating is uncertain, and this model uses nothing beyond past scores. Use “Test on my data” below to see how it has done on your past matches.
            </p>
            {adv && <p className="text-xs text-muted">Cutoff {dt(res.feature_cutoff)} · {res.model.name}@{res.model.version}</p>}
            {res.id ? (
              <p role="status" className="text-sm text-success">Saved at {dt(res.created_at!)}. <Link href="/dashboard/history" className="underline">View history</Link></p>
            ) : (
              <button type="button" disabled={busy !== null} onClick={() => run(true)} className="inline-flex items-center gap-2 rounded-xl border border-violet/60 px-4 py-2 text-sm font-semibold text-violet hover:bg-violet/10 disabled:opacity-50">
                {busy === "save" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Save forecast
              </button>
            )}
          </div>
        </Panel>
      )}

      {ds && <BacktestPanel dsId={ds.id} adv={adv} />}
    </div>
  );
}
