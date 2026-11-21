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
              Dataset fingerprint <span className="font-mono">{res.inputs.dataset_sha256.slice(0, 12)}</span>. With few matches a team&apos;s rating is uncertain, and this model uses nothing beyond past scores. Its accuracy on your league has not been measured.
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
    </div>
  );
}
