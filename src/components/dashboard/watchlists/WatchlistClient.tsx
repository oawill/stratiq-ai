"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import { call, post } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel, pct } from "../ui";
import { field } from "../analysis";

interface TeamStatus { played: number; elo: number | null; points_per_match: number | null; goals_for_per_match: number | null; goals_against_per_match: number | null; recent: { date: string; opponent: string; venue: string; score: string; result: "W" | "D" | "L" }[]; next_fixture: { date: string; opponent: string; venue: string } | null; as_of: string | null }
interface FixtureStatus { date?: string; model?: string; p_home?: number; p_draw?: number; p_away?: number; tuned?: boolean; note?: string; result?: string }
interface Item { id: string; kind: "team" | "fixture"; label: string; created_at: string; status: (TeamStatus & FixtureStatus) | null; note?: string | null }
interface Options { has_history: boolean; teams: string[]; fixtures: { date: string; home: string; away: string }[] }
interface List { items: Item[]; limit: number; generated_at: string; as_of: string | null }

const RESULT_TONE = { W: "text-emerald-300", D: "text-amber-200", L: "text-red-300" } as const;

function TeamCard({ s }: { s: TeamStatus }) {
  return (
    <div className="space-y-3 text-sm">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div><dt className="text-xs text-muted">Elo rating</dt><dd className="font-mono">{s.elo ?? "n/a"}</dd></div>
        <div><dt className="text-xs text-muted">Points per match</dt><dd className="font-mono">{s.points_per_match ?? "n/a"}</dd></div>
        <div><dt className="text-xs text-muted">Goals for / against</dt><dd className="font-mono">{s.goals_for_per_match ?? "n/a"} / {s.goals_against_per_match ?? "n/a"}</dd></div>
        <div><dt className="text-xs text-muted">Matches in the data</dt><dd className="font-mono">{s.played}</dd></div>
      </dl>
      <div>
        <p className="mb-1 text-xs text-muted">Last five results (newest first)</p>
        <ol className="flex flex-wrap gap-2" aria-label="Last five results">
          {s.recent.map((r) => <li key={r.date + r.opponent} className="rounded-lg border border-line px-2 py-1 text-xs"><span className={`font-bold ${RESULT_TONE[r.result]}`}>{r.result}</span> {r.venue === "H" ? "vs" : "at"} {r.opponent} <span className="font-mono text-muted">{r.score}</span></li>)}
        </ol>
      </div>
      <p className="text-xs text-muted">{s.next_fixture ? `Next imported fixture: ${s.next_fixture.venue === "H" ? "home to" : "away at"} ${s.next_fixture.opponent} on ${s.next_fixture.date}.` : "No upcoming fixture is imported for this club."} Calculated from your imported matches up to {s.as_of}.</p>
    </div>
  );
}

function FixtureCard({ s, note }: { s: FixtureStatus; note?: string | null }) {
  if (s.result) return <p className="text-sm">Played. Result <span className="font-mono">{s.result}</span>.</p>;
  if (s.p_home === undefined) return <p className="text-sm text-muted">{note ?? "No status."}</p>;
  return (
    <div className="space-y-2 text-sm">
      <p className="font-mono">Home {pct(s.p_home)} · Draw {pct(s.p_draw ?? 0)} · Away {pct(s.p_away ?? 0)}</p>
      <p className="text-xs text-muted">{s.model} forecast. {s.note}</p>
    </div>
  );
}

/** Personal watchlist of imported Premier League clubs and upcoming fixtures. Statuses are computed from the workspace's own imported data. */
export function WatchlistClient() {
  const [list, setList] = useState<List | null>(null);
  const [opts, setOpts] = useState<Options | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [team, setTeam] = useState("");
  const [fixture, setFixture] = useState("");

  const load = useCallback(async () => {
    try {
      const [l, o] = await Promise.all([call<List>("watchlists"), call<Options>("watchlists/options")]);
      setList(l); setOpts(o); setErr(null);
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not load your watchlist."); }
  }, []);
  useEffect(() => { const t = setTimeout(load, 0); return () => clearTimeout(t); }, [load]);

  async function add(body: Record<string, string>) {
    setBusy(true); setErr(null);
    try { await post("watchlists", body); setTeam(""); setFixture(""); await load(); } catch (e) { setErr(e instanceof Error ? e.message : "Could not add that."); } finally { setBusy(false); }
  }
  async function remove(id: string) {
    setBusy(true); setErr(null);
    try { await call(`watchlists/${id}`, { method: "DELETE" }); await load(); } catch (e) { setErr(e instanceof Error ? e.message : "Could not remove that."); } finally { setBusy(false); }
  }

  if (!list || !opts) return err ? <ErrorPanel message={err} /> : <p className="text-sm text-muted" aria-busy="true">Loading your watchlist…</p>;
  if (!opts.has_history && list.items.length === 0) {
    return <Empty>No match history yet, so there is nothing to watch. <Link href="/dashboard/data" className="text-violet underline">Import Premier League results</Link> on the Data page first.</Empty>;
  }
  const watchedTeams = new Set(list.items.filter((i) => i.kind === "team").map((i) => i.label));
  const fixtureKey = (f: { date: string; home: string; away: string }) => `${f.date}|${f.home}|${f.away}`;
  return (
    <div className="space-y-4">
      <Panel title="Add to your watchlist" badge={<Badge tone="muted">Private to you</Badge>}>
        <div className="flex flex-wrap items-end gap-3">
          <div><label htmlFor="wl-team" className="mb-1 block text-xs text-muted">Club</label>
            <select id="wl-team" value={team} onChange={(e) => setTeam(e.target.value)} className={field}><option value="">Choose a club…</option>{opts.teams.filter((t) => !watchedTeams.has(t)).map((t) => <option key={t} value={t}>{t}</option>)}</select></div>
          <button type="button" disabled={busy || !team} onClick={() => add({ kind: "team", team })} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Watch club</button>
        </div>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <div><label htmlFor="wl-fixture" className="mb-1 block text-xs text-muted">Upcoming fixture</label>
            <select id="wl-fixture" value={fixture} onChange={(e) => setFixture(e.target.value)} className={field} disabled={opts.fixtures.length === 0}><option value="">{opts.fixtures.length === 0 ? "No upcoming fixtures imported" : "Choose a fixture…"}</option>{opts.fixtures.map((f) => <option key={fixtureKey(f)} value={fixtureKey(f)}>{f.home} vs {f.away} ({f.date})</option>)}</select></div>
          <button type="button" disabled={busy || !fixture} onClick={() => { const [date, home, away] = fixture.split("|"); add({ kind: "fixture", date, home, away }); }} className="inline-flex items-center gap-2 rounded-xl border border-violet/60 px-4 py-2 text-sm font-semibold text-violet hover:bg-violet/10 disabled:opacity-50">Watch fixture</button>
        </div>
        <p className="mt-2 text-xs leading-relaxed text-muted">Clubs and fixtures come from the Premier League results and fixtures files you imported on the Data page. This is not a live feed: statuses are calculated from that data, as of {list.as_of ?? "no data"}. Up to {list.limit} items.</p>
        {err && <p role="alert" className="mt-3 text-sm text-red-300">{err}</p>}
      </Panel>

      {list.items.length === 0 ? <Empty>Your watchlist is empty. Add a club or an upcoming fixture above.</Empty> : (
        <ul className="grid gap-4 lg:grid-cols-2" aria-label="Watchlist">
          {list.items.map((it) => (
            <li key={it.id} className="glass rounded-2xl p-4">
              <div className="mb-3 flex items-start justify-between gap-2">
                <div><p className="font-semibold">{it.label}</p><Badge tone={it.kind === "team" ? "cyan" : "violet"}>{it.kind === "team" ? "Club" : "Fixture"}</Badge></div>
                <button type="button" onClick={() => remove(it.id)} disabled={busy} aria-label={`Remove ${it.label} from watchlist`} className="rounded-lg p-2 text-muted hover:text-red-300 disabled:opacity-50"><Trash2 className="h-4 w-4" aria-hidden="true" /></button>
              </div>
              {it.status === null ? <p className="text-sm text-muted">{it.note ?? "No status available."}</p> : it.kind === "team" ? <TeamCard s={it.status as TeamStatus} /> : <FixtureCard s={it.status} note={it.note} />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
