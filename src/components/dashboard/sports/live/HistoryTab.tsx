"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { call } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel } from "../../ui";
import { field } from "../../analysis";
import { ModelBadge, ProbBar, StatusBadge } from "./Parts";
import { stamp, type Percent } from "./live";

interface Row {
  id: string; version_no: number; official: boolean; generated_at: string; kickoff_utc: string; checkpoint: string; refresh_reason: string; model: string; percent: Percent;
  change_from_previous: { previous_version: number; max_abs_change: number; significant: boolean } | null; fixture_id: string; home_team: string; away_team: string; fixture_status: string;
  final_score: { home: number; away: number } | null;
}
interface Hist { versions: Row[]; total: number }
const PAGE = 15;
const CHECKPOINT: Record<string, string> = { discovery: "First forecast", h48: "48 hours before", h24: "24 hours before", h6: "6 hours before", h1: "1 hour before", reschedule: "Kickoff changed", lineup: "Lineup change", manual: "Requested" };

/** Every stored forecast version, newest first. Versions are never edited or removed; the official one is the last before kickoff. */
export function HistoryTab({ tz, fixtureId }: { tz: string; fixtureId?: string }) {
  const [data, setData] = useState<Hist | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [team, setTeam] = useState("");
  const [model, setModel] = useState("");
  const [offset, setOffset] = useState(0);

  const load = useCallback(() => {
    const qs = new URLSearchParams({ tz, limit: String(PAGE), offset: String(offset) });
    if (team.trim()) qs.set("team", team.trim());
    if (model) qs.set("model", model);
    if (fixtureId) qs.set("fixture_id", fixtureId);
    return call<Hist>(`football/live/forecast-history?${qs}`).then((x) => { setData(x); setErr(null); }, (e) => setErr(e instanceof Error ? e.message : "Could not load the history."));
  }, [tz, team, model, offset, fixtureId]);
  useEffect(() => { const t = setTimeout(load, team ? 300 : 0); return () => clearTimeout(t); }, [load, team]);

  return (
    <div className="space-y-4">
      <form role="search" aria-label="Filter forecast history" onSubmit={(e) => e.preventDefault()} className="flex flex-wrap items-end gap-3">
        <div><label htmlFor="h-team" className="mb-1 block text-xs text-muted">Team</label><input id="h-team" type="search" maxLength={60} value={team} onChange={(e) => { setTeam(e.target.value); setOffset(0); }} className={`${field} w-48`} placeholder="Any team" /></div>
        <div><label htmlFor="h-model" className="mb-1 block text-xs text-muted">Model</label><select id="h-model" value={model} onChange={(e) => { setModel(e.target.value); setOffset(0); }} className={field}><option value="">Any</option><option value="ensemble">Calibrated ensemble</option><option value="dixon_coles">Dixon-Coles</option></select></div>
        {fixtureId && <p className="text-xs text-muted">Showing one match. <Link href="/dashboard/sports/live?tab=history" className="text-violet underline">Show all</Link></p>}
      </form>
      {err && <ErrorPanel message={err} />}
      {!data && !err && <p className="text-sm text-muted" aria-busy="true">Loading history…</p>}
      {data && (
        <Panel title="Stored forecasts" badge={<Badge tone="muted">{data.total} version{data.total === 1 ? "" : "s"}</Badge>}>
          {data.versions.length === 0 ? <Empty>No forecasts have been stored yet. They are created automatically for scheduled fixtures once fixtures are synchronised and results history is imported.</Empty> : (
            <ul className="divide-y divide-line" aria-label="Forecast versions">
              {data.versions.map((v) => (
                <li key={v.id} className="py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link href={`/dashboard/sports/live?tab=intel&fixture=${v.fixture_id}`} className="font-semibold hover:text-violet">{v.home_team} v {v.away_team}</Link>
                    {v.final_score && <span className="font-mono text-sm">{v.final_score.home}–{v.final_score.away}</span>}
                    <StatusBadge status={v.fixture_status} />
                    <Badge tone="muted">Version {v.version_no}</Badge>{v.official && <Badge tone="green">Official</Badge>}<ModelBadge model={v.model} />
                  </div>
                  <p className="mt-0.5 text-xs text-muted">{stamp(v.generated_at, tz)} · {CHECKPOINT[v.checkpoint] ?? v.checkpoint}: {v.refresh_reason}</p>
                  <div className="mt-2 max-w-md"><ProbBar percent={v.percent} home={v.home_team} away={v.away_team} compact /></div>
                  {v.change_from_previous && <p className="mt-1 text-[11px] text-muted">Largest move since version {v.change_from_previous.previous_version}: {(v.change_from_previous.max_abs_change * 100).toFixed(1)} points{v.change_from_previous.significant ? " (significant)" : ""}.</p>}
                </li>
              ))}
            </ul>
          )}
          {data.total > PAGE && (
            <div className="mt-3 flex items-center justify-between text-sm">
              <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))} className="rounded-lg border border-line px-3 py-1.5 disabled:opacity-40">Previous</button>
              <span className="text-xs text-muted">{offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}</span>
              <button type="button" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)} className="rounded-lg border border-line px-3 py-1.5 disabled:opacity-40">Next</button>
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}
