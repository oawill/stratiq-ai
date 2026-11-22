"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Loader2, Pencil, Trash2 } from "lucide-react";
import { call, post } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel, pct } from "../ui";
import { field } from "../analysis";

interface TeamStatus { played: number; elo: number | null; points_per_match: number | null; goals_for_per_match: number | null; goals_against_per_match: number | null; recent: { date: string; opponent: string; venue: string; score: string; result: "W" | "D" | "L" }[]; next_fixture: { date: string; opponent: string; venue: string } | null; as_of: string | null }
interface FixtureStatus { date?: string; model?: string; p_home?: number; p_draw?: number; p_away?: number; tuned?: boolean; note?: string; result?: string }
interface CompStatus { competition?: string; matches?: number; seasons?: number; last_match?: string; stale?: boolean; upcoming_fixtures?: number; note?: string }
interface NoFeed { feed?: "none"; note?: string }
type Status = TeamStatus & FixtureStatus & CompStatus & NoFeed;
type Domain = "sports" | "business" | "politics" | "markets";
interface Item { id: string; domain: Domain; kind: string; label: string; created_at: string; status: Status | null; note?: string | null; user_note: string | null; group: string | null }
interface Options { has_history: boolean; teams: string[]; fixtures: { date: string; home: string; away: string }[]; kinds: Record<Domain, string[]> }
interface List { items: Item[]; total: number; page_size: number; offset: number; limit: number; groups: string[]; domain_counts: Record<string, number>; as_of: string | null }

const RESULT_TONE = { W: "text-emerald-300", D: "text-amber-200", L: "text-red-300" } as const;
const DOMAINS: { id: Domain; label: string }[] = [{ id: "sports", label: "Sports" }, { id: "business", label: "Business" }, { id: "politics", label: "Politics" }, { id: "markets", label: "Markets" }];
const KIND_LABEL: Record<string, string> = { team: "Club", fixture: "Fixture", competition: "Competition", company: "Company", indicator: "Indicator", election: "Election", instrument: "Instrument" };
const PAGE = 12;

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

function CompetitionCard({ s }: { s: CompStatus }) {
  return (
    <div className="space-y-1 text-sm">
      <p><span className="font-mono">{s.matches}</span> matches over <span className="font-mono">{s.seasons}</span> seasons. Last result {s.last_match ?? "n/a"}{s.stale ? " (may be out of date)" : ""}. {s.upcoming_fixtures ?? 0} upcoming fixtures imported.</p>
      <p className="text-xs text-muted">{s.note}</p>
    </div>
  );
}

function Body({ it }: { it: Item }) {
  const s = it.status;
  if (s === null) return <p className="text-sm text-muted">{it.note ?? "No status available."}</p>;
  if (s.feed === "none") return <p className="text-sm text-muted">{s.note}</p>;
  if (it.kind === "team") return <TeamCard s={s as TeamStatus} />;
  if (it.kind === "competition") return <CompetitionCard s={s} />;
  return <FixtureCard s={s} note={it.note} />;
}

function Card({ it, busy, onRemove, onSaved }: { it: Item; busy: boolean; onRemove: () => void; onSaved: () => void }) {
  const [edit, setEdit] = useState(false);
  const [note, setNote] = useState(it.user_note ?? "");
  const [group, setGroup] = useState(it.group ?? "");
  const [err, setErr] = useState<string | null>(null);
  async function save() {
    setErr(null);
    try {
      await call(`watchlists/${it.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note: note.trim() || undefined, group: group.trim() || undefined, clear_note: !note.trim(), clear_group: !group.trim() }) });
      setEdit(false); onSaved();
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not save."); }
  }
  return (
    <li className="glass rounded-2xl p-4">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold">{it.label}</p>
          <div className="mt-1 flex flex-wrap gap-1.5"><Badge tone={it.domain === "sports" ? "cyan" : "violet"}>{KIND_LABEL[it.kind] ?? it.kind}</Badge><Badge tone="muted">{it.domain}</Badge>{it.group && <Badge tone="green">{it.group}</Badge>}</div>
        </div>
        <div className="flex">
          <button type="button" onClick={() => setEdit((v) => !v)} aria-expanded={edit} aria-label={`Edit note and group for ${it.label}`} className="rounded-lg p-2 text-muted hover:text-ink"><Pencil className="h-4 w-4" aria-hidden="true" /></button>
          <button type="button" onClick={onRemove} disabled={busy} aria-label={`Remove ${it.label} from watchlist`} className="rounded-lg p-2 text-muted hover:text-red-300 disabled:opacity-50"><Trash2 className="h-4 w-4" aria-hidden="true" /></button>
        </div>
      </div>
      <Body it={it} />
      {it.user_note && !edit && <p className="mt-3 rounded-lg border border-line bg-white/5 px-3 py-2 text-xs">Your note: {it.user_note}</p>}
      {edit && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <div><label htmlFor={`n-${it.id}`} className="mb-1 block text-xs text-muted">Note</label><input id={`n-${it.id}`} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} className={`${field} w-full`} /></div>
          <div><label htmlFor={`g-${it.id}`} className="mb-1 block text-xs text-muted">Group</label><input id={`g-${it.id}`} value={group} maxLength={40} onChange={(e) => setGroup(e.target.value)} className={`${field} w-full`} /></div>
          <div className="flex items-center gap-3 sm:col-span-2"><button type="button" onClick={save} className="rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-white">Save</button>{err && <span role="alert" className="text-xs text-red-300">{err}</span>}</div>
        </div>
      )}
    </li>
  );
}

/** Watchlists across all four domains. Sports items are computed from imported data; business, politics and markets items are the person's own notes
 *  and say plainly that no data feed is connected. */
export function WatchlistClient() {
  const [list, setList] = useState<List | null>(null);
  const [opts, setOpts] = useState<Options | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [team, setTeam] = useState("");
  const [fixture, setFixture] = useState("");
  const [domain, setDomain] = useState<Domain | "">("");
  const [q, setQ] = useState("");
  const [group, setGroup] = useState("");
  const [offset, setOffset] = useState(0);
  const [nd, setNd] = useState<Exclude<Domain, "sports">>("business");
  const [nk, setNk] = useState("company");
  const [nl, setNl] = useState("");

  const load = useCallback(async () => {
    const qs = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
    if (domain) qs.set("domain", domain);
    if (q.trim()) qs.set("q", q.trim());
    if (group) qs.set("group", group);
    try {
      const [l, o] = await Promise.all([call<List>(`watchlists?${qs}`), call<Options>("watchlists/options")]);
      setList(l); setOpts(o); setErr(null);
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not load your watchlist."); }
  }, [domain, q, group, offset]);
  useEffect(() => { const t = setTimeout(load, q ? 250 : 0); return () => clearTimeout(t); }, [load, q]);

  async function add(body: Record<string, string>) {
    setBusy(true); setErr(null);
    try { await post("watchlists", body); setTeam(""); setFixture(""); setNl(""); await load(); } catch (e) { setErr(e instanceof Error ? e.message : "Could not add that."); } finally { setBusy(false); }
  }
  async function remove(id: string) {
    setBusy(true); setErr(null);
    try { await call(`watchlists/${id}`, { method: "DELETE" }); await load(); } catch (e) { setErr(e instanceof Error ? e.message : "Could not remove that."); } finally { setBusy(false); }
  }

  if (!list || !opts) return err ? <ErrorPanel message={err} /> : <p className="text-sm text-muted" aria-busy="true">Loading your watchlist…</p>;
  const total = Object.values(list.domain_counts).reduce((a, b) => a + b, 0);
  const watchedTeams = new Set(list.items.filter((i) => i.kind === "team").map((i) => i.label));
  const fixtureKey = (f: { date: string; home: string; away: string }) => `${f.date}|${f.home}|${f.away}`;
  const filtered = !!(domain || q.trim() || group);
  const nonSportsKinds = opts.kinds[nd] ?? [];
  return (
    <div className="space-y-4">
      <Panel title="Add to your watchlist" badge={<Badge tone="muted">Private to you</Badge>}>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Sports (from your imported results)</h3>
        {!opts.has_history && <p className="mb-2 text-xs text-muted">No match history yet. <Link href="/dashboard/data" className="text-violet underline">Import Premier League results</Link> on the Data page to watch clubs and fixtures.</p>}
        <div className="flex flex-wrap items-end gap-3">
          <div><label htmlFor="wl-team" className="mb-1 block text-xs text-muted">Club</label>
            <select id="wl-team" value={team} onChange={(e) => setTeam(e.target.value)} className={field} disabled={!opts.has_history}><option value="">Choose a club…</option>{opts.teams.filter((t) => !watchedTeams.has(t)).map((t) => <option key={t} value={t}>{t}</option>)}</select></div>
          <button type="button" disabled={busy || !team} onClick={() => add({ kind: "team", team })} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Watch club</button>
          <button type="button" disabled={busy || !opts.has_history} onClick={() => add({ kind: "competition" })} className="rounded-xl border border-line px-4 py-2 text-sm font-semibold hover:bg-white/5 disabled:opacity-50">Watch the Premier League</button>
        </div>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <div><label htmlFor="wl-fixture" className="mb-1 block text-xs text-muted">Upcoming fixture</label>
            <select id="wl-fixture" value={fixture} onChange={(e) => setFixture(e.target.value)} className={field} disabled={opts.fixtures.length === 0}><option value="">{opts.fixtures.length === 0 ? "No upcoming fixtures imported" : "Choose a fixture…"}</option>{opts.fixtures.map((f) => <option key={fixtureKey(f)} value={fixtureKey(f)}>{f.home} vs {f.away} ({f.date})</option>)}</select></div>
          <button type="button" disabled={busy || !fixture} onClick={() => { const [date, home, away] = fixture.split("|"); add({ kind: "fixture", date, home, away }); }} className="inline-flex items-center gap-2 rounded-xl border border-violet/60 px-4 py-2 text-sm font-semibold text-violet hover:bg-violet/10 disabled:opacity-50">Watch fixture</button>
        </div>

        <h3 className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wider text-muted">Business, politics and markets (your own notes)</h3>
        <div className="flex flex-wrap items-end gap-3">
          <div><label htmlFor="wl-nd" className="mb-1 block text-xs text-muted">Domain</label>
            <select id="wl-nd" value={nd} onChange={(e) => { const v = e.target.value as Exclude<Domain, "sports">; setNd(v); setNk(opts.kinds[v][0]); }} className={field}>{DOMAINS.filter((d) => d.id !== "sports").map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}</select></div>
          <div><label htmlFor="wl-nk" className="mb-1 block text-xs text-muted">Type</label>
            <select id="wl-nk" value={nk} onChange={(e) => setNk(e.target.value)} className={field}>{nonSportsKinds.map((k) => <option key={k} value={k}>{KIND_LABEL[k] ?? k}</option>)}</select></div>
          <div><label htmlFor="wl-nl" className="mb-1 block text-xs text-muted">Name</label>
            <input id="wl-nl" value={nl} maxLength={80} onChange={(e) => setNl(e.target.value)} placeholder="e.g. a company or indicator" className={`${field} w-56`} /></div>
          <button type="button" disabled={busy || !nl.trim()} onClick={() => add({ domain: nd, kind: nk, label: nl.trim() })} className="rounded-xl border border-violet/60 px-4 py-2 text-sm font-semibold text-violet hover:bg-violet/10 disabled:opacity-50">Add to watchlist</button>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-muted">Sports statuses are calculated from the results and fixtures you imported, as of {list.as_of ?? "no data"}; this is not a live feed. No data feed is connected for business, politics or markets: those items are your own notes and never update by themselves. Up to {list.limit} items.</p>
        {err && <p role="alert" className="mt-3 text-sm text-red-300">{err}</p>}
      </Panel>

      {total > 0 && (
        <div className="flex flex-wrap items-end gap-3" role="search" aria-label="Filter watchlist">
          <div><label htmlFor="wl-q" className="mb-1 block text-xs text-muted">Search</label><input id="wl-q" type="search" value={q} maxLength={80} onChange={(e) => { setQ(e.target.value); setOffset(0); }} placeholder="Name or note" className={`${field} w-52`} /></div>
          <div><label htmlFor="wl-dom" className="mb-1 block text-xs text-muted">Domain</label>
            <select id="wl-dom" value={domain} onChange={(e) => { setDomain(e.target.value as Domain | ""); setOffset(0); }} className={field}><option value="">All ({total})</option>{DOMAINS.map((d) => <option key={d.id} value={d.id}>{d.label} ({list.domain_counts[d.id] ?? 0})</option>)}</select></div>
          {list.groups.length > 0 && <div><label htmlFor="wl-grp" className="mb-1 block text-xs text-muted">Group</label>
            <select id="wl-grp" value={group} onChange={(e) => { setGroup(e.target.value); setOffset(0); }} className={field}><option value="">All groups</option>{list.groups.map((g) => <option key={g} value={g}>{g}</option>)}</select></div>}
        </div>
      )}

      {list.items.length === 0 ? <Empty>{filtered && total > 0 ? "Nothing matches those filters." : "Your watchlist is empty. Add a club, a fixture, or a note about a company, indicator, election or instrument above."}</Empty> : (
        <ul className="grid gap-4 lg:grid-cols-2" aria-label="Watchlist">
          {list.items.map((it) => <Card key={it.id} it={it} busy={busy} onRemove={() => remove(it.id)} onSaved={load} />)}
        </ul>
      )}

      {list.total > PAGE && (
        <nav className="flex items-center justify-between text-sm" aria-label="Watchlist pages">
          <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))} className="rounded-lg border border-line px-3 py-1.5 disabled:opacity-40">Previous</button>
          <span className="text-xs text-muted">{offset + 1}–{Math.min(offset + PAGE, list.total)} of {list.total}</span>
          <button type="button" disabled={offset + PAGE >= list.total} onClick={() => setOffset(offset + PAGE)} className="rounded-lg border border-line px-3 py-1.5 disabled:opacity-40">Next</button>
        </nav>
      )}
    </div>
  );
}
