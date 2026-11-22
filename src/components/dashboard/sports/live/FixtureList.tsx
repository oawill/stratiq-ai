"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { call } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel } from "../../ui";
import { field } from "../../analysis";
import { FreshnessBanner, ModelBadge, ProbBar, StatusBadge } from "./Parts";
import { STATUS_LABEL, kickoff, type Fixture, type FixtureList as List } from "./live";

type Mode = "today" | "upcoming" | "completed";
interface Filters { day: string; team: string; status: string; model: string; forecast: string; range: string }
const PAGE = 15;
const STATUS_CHOICES: Record<Mode, string[]> = {
  today: ["scheduled", "in_play", "paused", "finished", "postponed", "cancelled"],
  upcoming: ["scheduled", "postponed", "suspended", "cancelled"],
  completed: ["completed", "finished", "awarded"],
};

function Row({ f, tz }: { f: Fixture; tz: string }) {
  const score = f.final_score;
  const rc = f.result_check;
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold">{f.home_team} <span className="font-normal text-muted">v</span> {f.away_team}</span>
            {score && <span className="font-mono text-sm" aria-label={`Final score ${score.home} ${score.away}`}>{score.home}–{score.away}</span>}
            <StatusBadge status={f.status} />
          </div>
          <p className="mt-0.5 text-xs text-muted">{kickoff(f.kickoff_utc, tz)}{f.matchday ? ` · Matchday ${f.matchday}` : ""}{f.venue ? ` · ${f.venue}` : ""}</p>
        </div>
        <Link href={`/dashboard/sports/football/matches/${f.id}`} className="shrink-0 text-xs font-semibold text-violet underline" aria-label={`Match intelligence for ${f.home_team} v ${f.away_team}`}>Match intelligence</Link>
      </div>
      {f.forecast ? (
        <div className="mt-2 max-w-md">
          <ProbBar percent={f.forecast.percent} home={f.home_team} away={f.away_team} compact />
          <p className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted"><ModelBadge model={f.forecast.model} />{f.forecast.official ? <Badge tone="green">Official forecast</Badge> : <Badge tone="muted">Version {f.forecast.version_no}</Badge>}</p>
        </div>
      ) : (
        <p className="mt-1 text-xs text-muted">{f.forecastable ? "No forecast yet." : f.status === "scheduled" ? "No forecast." : `No forecast: the match is ${(STATUS_LABEL[f.status] ?? f.status).toLowerCase()}.`}</p>
      )}
      {rc && (
        <p className="mt-1 text-xs">
          {rc.available
            ? <>Result: {rc.outcome === "draw" ? "draw" : `${rc.outcome} win`}. The forecast&apos;s most likely outcome was {rc.most_likely === "draw" ? "a draw" : rc.most_likely === "away" ? "an away win" : "a home win"} ({rc.most_likely_was_right ? "right" : "wrong"}); it gave the actual result {Math.round((rc.probability_given_to_outcome ?? 0) * 100)}%. <span className="text-muted">{rc.note}</span></>
            : <span className="text-muted">{rc.note}</span>}
        </p>
      )}
    </li>
  );
}

/** One fixture list for Today's matches, Upcoming fixtures and Completed matches, with the shared filters. */
export function FixtureList({ mode, tz }: { mode: Mode; tz: string }) {
  const [flt, setFlt] = useState<Filters>({ day: "", team: "", status: "", model: "", forecast: "", range: mode === "upcoming" ? "week" : "" });
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<List | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (p: Partial<Filters>) => { setFlt((f) => ({ ...f, ...p })); setOffset(0); };

  const load = useCallback(() => {
    const window = mode === "today" ? "today" : mode === "completed" ? "recent" : flt.range || "week";
    const qs = new URLSearchParams({ window, tz, limit: String(PAGE), offset: String(offset) });
    if (mode === "completed" && !flt.status) qs.set("status", "completed");
    if (flt.status) qs.set("status", flt.status);
    if (flt.day) qs.set("day", flt.day);
    if (flt.team.trim()) qs.set("team", flt.team.trim());
    if (flt.model) qs.set("model", flt.model);
    if (flt.forecast) qs.set("forecast", flt.forecast);
    setBusy(true);
    return call<List>(`football/live/fixtures?${qs}`).then((x) => { setData(x); setErr(null); }, (e) => setErr(e instanceof Error ? e.message : "Could not load fixtures.")).finally(() => setBusy(false));
  }, [mode, tz, flt, offset]);
  useEffect(() => { const t = setTimeout(load, flt.team ? 300 : 0); return () => clearTimeout(t); }, [load, flt.team]);

  const id = (k: string) => `fx-${mode}-${k}`;
  return (
    <div className="space-y-4">
      <form role="search" aria-label="Filter fixtures" onSubmit={(e) => e.preventDefault()} className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <div><label htmlFor={id("comp")} className="mb-1 block text-xs text-muted">Competition</label><select id={id("comp")} className={`${field} w-full`} defaultValue="EPL"><option value="EPL">Premier League</option></select></div>
        {mode === "upcoming" && <div><label htmlFor={id("range")} className="mb-1 block text-xs text-muted">Period</label><select id={id("range")} value={flt.range} onChange={(e) => set({ range: e.target.value, day: "" })} className={`${field} w-full`}><option value="week">Next 7 days</option><option value="month">Next 30 days</option></select></div>}
        {mode !== "today" && <div><label htmlFor={id("day")} className="mb-1 block text-xs text-muted">Date</label><input id={id("day")} type="date" value={flt.day} onChange={(e) => set({ day: e.target.value })} className={`${field} w-full`} /></div>}
        <div><label htmlFor={id("team")} className="mb-1 block text-xs text-muted">Team</label><input id={id("team")} type="search" maxLength={60} value={flt.team} onChange={(e) => set({ team: e.target.value })} className={`${field} w-full`} placeholder="Any team" /></div>
        <div><label htmlFor={id("status")} className="mb-1 block text-xs text-muted">Match status</label>
          <select id={id("status")} value={flt.status} onChange={(e) => set({ status: e.target.value })} className={`${field} w-full`}><option value="">Any</option>{STATUS_CHOICES[mode].map((s) => <option key={s} value={s}>{s === "completed" ? "Completed" : STATUS_LABEL[s]}</option>)}</select></div>
        <div><label htmlFor={id("model")} className="mb-1 block text-xs text-muted">Model</label>
          <select id={id("model")} value={flt.model} onChange={(e) => set({ model: e.target.value })} className={`${field} w-full`}><option value="">Any</option><option value="ensemble">Calibrated ensemble</option><option value="dixon_coles">Dixon-Coles</option></select></div>
        <div><label htmlFor={id("fc")} className="mb-1 block text-xs text-muted">Forecast</label>
          <select id={id("fc")} value={flt.forecast} onChange={(e) => set({ forecast: e.target.value })} className={`${field} w-full`}><option value="">Any</option><option value="yes">Has a forecast</option><option value="no">No forecast</option></select></div>
      </form>

      {err && <ErrorPanel message={err} />}
      {!data && !err && <p className="text-sm text-muted" aria-busy="true">Loading fixtures…</p>}
      {data && (
        <Panel title={mode === "today" ? "Today" : mode === "completed" ? "Last 30 days" : flt.range === "month" ? "Next 30 days" : "Next 7 days"} badge={<Badge tone="muted">{data.total} match{data.total === 1 ? "" : "es"}</Badge>}>
          <div aria-busy={busy}>
            {data.fixtures.length === 0 ? <Empty>{data.note}</Empty> : <ul className="divide-y divide-line" aria-label="Fixtures">{data.fixtures.map((f) => <Row key={f.id} f={f} tz={tz} />)}</ul>}
          </div>
          {data.total > PAGE && (
            <div className="mt-3 flex items-center justify-between text-sm">
              <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))} className="rounded-lg border border-line px-3 py-1.5 disabled:opacity-40">Previous</button>
              <span className="text-xs text-muted">{offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}</span>
              <button type="button" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)} className="rounded-lg border border-line px-3 py-1.5 disabled:opacity-40">Next</button>
            </div>
          )}
          <div className="mt-3"><FreshnessBanner f={data.freshness} tz={tz} /></div>
        </Panel>
      )}
    </div>
  );
}
