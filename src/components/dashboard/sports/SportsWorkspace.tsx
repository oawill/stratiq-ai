"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Loader2, Save } from "lucide-react";
import type { Compare, Fixture, League, ResultRow, SportsInputs, SportsModelInfo, SportsOutputs, TeamRating } from "@/lib/types";
import { Badge, Empty, ErrorPanel, Panel, dt, pct } from "../ui";
import { useAdvanced } from "../useAdvanced";
import { DataForecastTab } from "./DataForecastTab";
import { GoalsChart, Heatmap, Outcomes, Plain, RatingsTable } from "./Projection";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/app-api/${path}`, init);
  const j = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof j.detail === "string" ? j.detail : "Request failed");
  return j as T;
}
const post = <T,>(path: string, body: unknown) =>
  call<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

interface Saved { id: string; created_at: string; feature_cutoff: string; model: { name: string; version: string }; inputs: SportsInputs; outputs: SportsOutputs }

function ScoreLine({ r, team }: { r: ResultRow; team?: string }) {
  return (
    <li className="flex items-center justify-between gap-2 py-1.5 text-sm">
      <span className="truncate">{r.home_name} <span className="font-mono font-bold">{r.home_goals}–{r.away_goals}</span> {r.away_name}</span>
      <span className="shrink-0 text-[11px] text-muted">{new Date(r.kickoff).toISOString().slice(0, 10)}{team ? "" : ""}</span>
    </li>
  );
}

function SaveBar({ saving, saved, error, onSave, label }: { saving: boolean; saved: Saved | null; error: string | null; onSave: () => void; label: string }) {
  return (
    <div className="mt-4 rounded-xl border border-line bg-bg/50 p-3">
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={onSave} disabled={saving} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-[#9168ff] disabled:opacity-60">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Save className="h-4 w-4" aria-hidden="true" />} {label}
        </button>
        <span className="text-xs text-muted">Saves an immutable record with model version, feature cutoff and assumptions.</span>
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-red-300">{error}</p>}
      {saved && (
        <p role="status" className="mt-2 text-sm text-success">
          Saved at {dt(saved.created_at)} · cutoff {dt(saved.feature_cutoff)} · {saved.model.name}@{saved.model.version}.{" "}
          <Link href="/dashboard/history" className="underline">View history</Link>
        </p>
      )}
    </div>
  );
}

function Projection({ c, adv, saveBody, retrospective }: { c: Compare; adv: boolean; saveBody: object; retrospective?: boolean }) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<Saved | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const o = c.projection, i = c.ratings;
  async function save() {
    setSaving(true); setErr(null);
    try { setSaved(await post<Saved>("sports/predictions", saveBody)); } catch (e) { setErr(e instanceof Error ? e.message : "Could not save"); } finally { setSaving(false); }
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="amber">Fictional dataset</Badge>
        <Badge tone="muted">Model projection · not saved</Badge>
      </div>
      <Outcomes o={o} home={c.home.name} away={c.away.name} />
      <Plain o={o} home={c.home.name} away={c.away.name} retrospective={retrospective} />
      <div className="grid grid-cols-3 gap-3 text-center text-sm">
        <div className="rounded-xl border border-line p-2"><div className="text-[11px] text-muted">Expected goals</div><div className="font-mono font-bold">{o.home_xg.toFixed(2)} – {o.away_xg.toFixed(2)}</div></div>
        <div className="rounded-xl border border-line p-2"><div className="text-[11px] text-muted">Both teams score</div><div className="font-mono font-bold">{pct(o.p_btts)}</div></div>
        <div className="rounded-xl border border-line p-2"><div className="text-[11px] text-muted">Over 2.5 goals</div><div className="font-mono font-bold">{pct(o.p_over_2_5)}</div></div>
      </div>
      {adv && (
        <div className="space-y-4 border-t border-line pt-4">
          <div><h3 className="mb-2 text-sm font-semibold">Scoreline distribution</h3><Heatmap grid={o.scoreline_grid} home={c.home.name} away={c.away.name} /></div>
          <div><h3 className="mb-1 text-sm font-semibold">Goal-count probabilities</h3><GoalsChart grid={o.scoreline_grid} home={c.home.name} away={c.away.name} /></div>
          <div>
            <h3 className="mb-2 text-sm font-semibold">Most likely scorelines</h3>
            <ul className="flex flex-wrap gap-2">{o.top_scorelines.map((s) => <li key={`${s.home}-${s.away}`} className="rounded-lg border border-line px-2 py-1 font-mono text-xs">{s.home}–{s.away} · {pct(s.p)}</li>)}</ul>
          </div>
          <div>
            <h3 className="mb-2 text-sm font-semibold">Fitted ratings</h3>
            <RatingsTable i={i} home={c.home.name} away={c.away.name} />
            <p className="mt-2 text-[11px] leading-relaxed text-muted">
              League mean goals {i.league_mean_goals.toFixed(3)} · home advantage ×{i.home_advantage.toFixed(3)} · {i.matches_used} matches used (cutoff {dt(i.feature_cutoff)}) ·
              fit {i.fit_converged ? "converged" : "did not converge"} in {i.fit_iterations} iterations · tail mass removed {o.grid_tail_mass_removed.toExponential(1)}
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div><h3 className="mb-1 text-sm font-semibold">{c.home.name}: last results</h3><ul className="divide-y divide-line">{c.home_form.map((r) => <ScoreLine key={r.id} r={r} />)}</ul></div>
            <div><h3 className="mb-1 text-sm font-semibold">{c.away.name}: last results</h3><ul className="divide-y divide-line">{c.away_form.map((r) => <ScoreLine key={r.id} r={r} />)}</ul></div>
          </div>
          <div><h3 className="mb-1 text-sm font-semibold">Head to head</h3>{c.head_to_head.length ? <ul className="divide-y divide-line">{c.head_to_head.map((r) => <ScoreLine key={r.id} r={r} />)}</ul> : <p className="text-sm text-muted">No previous meetings in the dataset.</p>}</div>
        </div>
      )}
      <SaveBar saving={saving} saved={saved} error={err} onSave={save} label="Save forecast" />
    </div>
  );
}

function RetroPanel({ f, adv }: { f: Fixture; adv: boolean }) {
  const [res, setRes] = useState<Saved | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function run() {
    setBusy(true); setErr(null);
    try { setRes(await post<Saved>("sports/predictions", { fixture_id: f.id })); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); } finally { setBusy(false); }
  }
  const actual = f.home_goals! > f.away_goals! ? "home win" : f.home_goals === f.away_goals ? "draw" : "away win";
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-line p-4 text-center">
        <div className="text-xs text-muted">Final result · {new Date(f.kickoff).toISOString().slice(0, 10)}</div>
        <div className="mt-1 text-lg font-bold">{f.home_name} <span className="font-mono">{f.home_goals}–{f.away_goals}</span> {f.away_name}</div>
        <div className="text-xs text-muted">Outcome: {actual}</div>
      </div>
      <p className="text-sm text-muted">Run a retrospective forecast: the model refits using only matches played <em>before</em> this kickoff (no look-ahead) and the record is saved flagged as retrospective.</p>
      <button type="button" onClick={run} disabled={busy} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
        {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Run retrospective forecast
      </button>
      {err && <p role="alert" className="text-sm text-red-300">{err}</p>}
      {res && (
        <div className="space-y-3">
          <Badge tone="amber">Retrospective · saved</Badge>
          <Outcomes o={res.outputs} home={f.home_name} away={f.away_name} />
          <Plain o={res.outputs} home={f.home_name} away={f.away_name} retrospective />
          <p className="text-xs text-muted">{res.inputs.matches_used} earlier matches used · cutoff {dt(res.feature_cutoff)}</p>
          {adv && <Heatmap grid={res.outputs.scoreline_grid} home={f.home_name} away={f.away_name} />}
        </div>
      )}
    </div>
  );
}

function FixtureList({ leagueId, status, sel, onSelect }: { leagueId: string; status: "scheduled" | "finished"; sel: Fixture | null; onSelect: (f: Fixture) => void }) {
  const [list, setList] = useState<Fixture[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    call<{ fixtures: Fixture[] }>(`sports/fixtures?league_id=${leagueId}&status=${status}&limit=${status === "scheduled" ? 30 : 40}`)
      .then((d) => live && setList(d.fixtures)).catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, [leagueId, status]);
  if (err) return <ErrorPanel message={err} />;
  if (list === null) return <p className="text-sm text-muted" aria-busy="true">Loading fixtures…</p>;
  if (list.length === 0) return <Empty>No fixtures.</Empty>;
  return (
    <ul className="max-h-[32rem] space-y-1 overflow-auto pr-1">
      {list.map((f) => (
        <li key={f.id}>
          <button type="button" onClick={() => onSelect(f)} aria-pressed={sel?.id === f.id} className={`w-full rounded-xl border p-2.5 text-left text-sm transition-colors ${sel?.id === f.id ? "border-primary bg-primary/15" : "border-line hover:border-violet/50"}`}>
            <div className="flex items-center justify-between gap-2"><span className="truncate">{f.home_name}</span>{f.status === "finished" && <span className="font-mono font-bold">{f.home_goals}</span>}</div>
            <div className="flex items-center justify-between gap-2"><span className="truncate">{f.away_name}</span>{f.status === "finished" && <span className="font-mono font-bold">{f.away_goals}</span>}</div>
            <div className="mt-1 text-[11px] text-muted">{dt(f.kickoff)}</div>
          </button>
        </li>
      ))}
    </ul>
  );
}

function LiveProjection({ f, adv }: { f: Fixture; adv: boolean }) {
  const [cmp, setCmp] = useState<Compare | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    call<Compare>(`sports/compare?home_team_id=${encodeURIComponent(f.home_team_id)}&away_team_id=${encodeURIComponent(f.away_team_id)}`)
      .then((d) => live && setCmp(d)).catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, [f]);
  if (err) return <ErrorPanel message={err} />;
  if (!cmp) return <p className="flex items-center gap-2 text-sm text-muted" aria-busy="true"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Fitting model…</p>;
  return <Projection key={f.id} c={cmp} adv={adv} saveBody={{ fixture_id: f.id }} />;
}

function FixturesTab({ leagueId, adv }: { leagueId: string; adv: boolean }) {
  const [status, setStatus] = useState<"scheduled" | "finished">("scheduled");
  const [sel, setSel] = useState<Fixture | null>(null);
  const pick = (s: "scheduled" | "finished") => { setStatus(s); setSel(null); };
  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <Panel className="lg:col-span-2" title="Fixture browser">
        <div role="group" aria-label="Fixture type" className="mb-3 inline-flex rounded-lg border border-line p-0.5 text-xs">
          {(["scheduled", "finished"] as const).map((s) => (
            <button key={s} type="button" aria-pressed={status === s} onClick={() => pick(s)} className={`rounded-md px-3 py-1.5 font-semibold ${status === s ? "bg-primary text-white" : "text-muted"}`}>{s === "scheduled" ? "Upcoming" : "Results"}</button>
          ))}
        </div>
        <FixtureList key={`${leagueId}:${status}`} leagueId={leagueId} status={status} sel={sel} onSelect={setSel} />
      </Panel>
      <Panel className="lg:col-span-3" title={sel ? `${sel.home_name} vs ${sel.away_name}` : "Match prediction"}>
        {!sel ? <Empty>Select a fixture to see the model&apos;s probabilities.</Empty>
          : sel.status === "finished" ? <RetroPanel key={sel.id} f={sel} adv={adv} />
          : <LiveProjection key={sel.id} f={sel} adv={adv} />}
      </Panel>
    </div>
  );
}

function CompareResult({ home, away, adv }: { home: string; away: string; adv: boolean }) {
  const [cmp, setCmp] = useState<Compare | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    call<Compare>(`sports/compare?home_team_id=${encodeURIComponent(home)}&away_team_id=${encodeURIComponent(away)}`)
      .then((d) => live && setCmp(d)).catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, [home, away]);
  if (err) return <ErrorPanel message={err} />;
  if (!cmp) return <p className="flex items-center gap-2 text-sm text-muted" aria-busy="true"><Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Calculating…</p>;
  return <Projection c={cmp} adv={adv} saveBody={{ home_team_id: home, away_team_id: away }} />;
}

function CompareTab({ leagueId, adv, initialTeam }: { leagueId: string; adv: boolean; initialTeam?: string }) {
  const [data, setData] = useState<{ teams: TeamRating[]; league_mean_goals: number; home_advantage: number } | null>(null);
  const [homeSel, setHome] = useState<string | null>(null);
  const [awaySel, setAway] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    call<{ teams: TeamRating[]; league_mean_goals: number; home_advantage: number }>(`sports/teams?league_id=${leagueId}`)
      .then((d) => live && setData(d)).catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, [leagueId]);

  if (err) return <ErrorPanel message={err} />;
  if (!data) return <p className="text-sm text-muted" aria-busy="true">Loading teams…</p>;
  const teams = data.teams;
  const pre = initialTeam && teams.some((t) => t.id === initialTeam) ? initialTeam : teams[0]?.id ?? "";
  const home = homeSel ?? pre;
  const away = awaySel ?? teams.find((t) => t.id !== pre)?.id ?? "";
  const sel = "w-full rounded-xl border border-line bg-bg/70 px-3 py-2 text-sm focus:border-violet focus:outline-none focus:ring-2 focus:ring-violet/40";
  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <Panel className="lg:col-span-2" title="Team comparison">
        <div className="space-y-3">
          <div><label htmlFor="cmp-home" className="mb-1 block text-xs text-muted">Home team</label>
            <select id="cmp-home" value={home} onChange={(e) => setHome(e.target.value)} className={sel}>{teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></div>
          <div><label htmlFor="cmp-away" className="mb-1 block text-xs text-muted">Away team</label>
            <select id="cmp-away" value={away} onChange={(e) => setAway(e.target.value)} className={sel}>{teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></div>
          {home === away && <p role="alert" className="text-sm text-amber-300">Choose two different teams.</p>}
        </div>
        {adv && (
          <div className="mt-5">
            <h3 className="mb-1 text-sm font-semibold">League ratings</h3>
            <table className="w-full text-xs">
              <thead><tr className="text-left text-muted"><th scope="col" className="font-normal">Team</th><th scope="col" className="font-normal">Att ×</th><th scope="col" className="font-normal">Def ×</th></tr></thead>
              <tbody className="font-mono">{teams.map((t) => <tr key={t.id}><td className="py-0.5 font-sans">{t.name}</td><td>{t.attack.toFixed(2)}</td><td>{t.defence.toFixed(2)}</td></tr>)}</tbody>
            </table>
            <p className="mt-2 text-[11px] text-muted">Attack above 1 scores more than average; defence above 1 concedes more. League mean {data.league_mean_goals.toFixed(2)} goals, home advantage ×{data.home_advantage.toFixed(2)}.</p>
          </div>
        )}
      </Panel>
      <Panel className="lg:col-span-3" title="Match prediction details">
        {home === away || !home ? <Empty>Pick two different teams.</Empty> : <CompareResult key={`${home}:${away}`} home={home} away={away} adv={adv} />}
      </Panel>
    </div>
  );
}

function MethodologyTab() {
  const [d, setD] = useState<SportsModelInfo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { call<SportsModelInfo>("sports/model").then(setD).catch((e) => setErr(e.message)); }, []);
  if (err) return <ErrorPanel message={err} />;
  if (!d) return <p className="text-sm text-muted" aria-busy="true">Loading…</p>;
  const g = (k: string) => d.metrics.find((m) => m.metric === k);
  const b = g("brier"), bb = g("baseline_brier"), l = g("log_loss"), bl = g("baseline_log_loss");
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel title={`${d.model.name}@${d.model.version}`} badge={<Badge tone="amber">{d.model.status}</Badge>}>
        <p className="text-sm text-muted">{d.model.description}</p>
        <h3 className="mb-1 mt-4 text-sm font-semibold">Model</h3>
        <p className="rounded-lg bg-bg/60 p-3 font-mono text-xs leading-relaxed">home_xg = μ · attack[home] · defence[away] · γ<br />away_xg = μ · attack[away] · defence[home]<br />P(h,a) = Poisson(h; home_xg) · Poisson(a; away_xg)</p>
        <h3 className="mb-1 mt-4 text-sm font-semibold">Assumptions</h3>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted">{d.model.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
      </Panel>
      <div className="space-y-4">
        <Panel title="Performance" badge={<Badge tone="amber">Fictional data only</Badge>}>
          {b && bb && l && bl ? (
            <>
              <table className="w-full text-sm">
                <thead><tr className="text-left text-xs text-muted"><th scope="col" className="font-normal">Metric</th><th scope="col" className="font-normal">Model</th><th scope="col" className="font-normal">Base-rate baseline</th></tr></thead>
                <tbody className="font-mono"><tr><td className="py-1 font-sans">Brier score</td><td>{b.value.toFixed(4)}</td><td>{bb.value.toFixed(4)}</td></tr>
                  <tr><td className="py-1 font-sans">Log loss</td><td>{l.value.toFixed(4)}</td><td>{bl.value.toFixed(4)}</td></tr></tbody>
              </table>
              <p className="mt-3 text-xs leading-relaxed text-muted">Rolling-origin backtest: n = {b.sample_size} matches from {b.dataset}; each match is predicted from strictly earlier matches only. Lower is better. Because this data was <strong>simulated from a Poisson process</strong>, the model is expected to do well; this validates the code, <strong>not</strong> real-world accuracy.</p>
            </>
          ) : <Empty>Evaluation in progress. No validated metrics yet.</Empty>}
        </Panel>
        <Panel title="Limitations">
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted">{d.model.limitations.map((a) => <li key={a}>{a}</li>)}</ul>
        </Panel>
      </div>
    </div>
  );
}

export function SportsWorkspace({ leagues, initialLeague, initialTeam }: { leagues: League[]; initialLeague?: string; initialTeam?: string }) {
  const [leagueId, setLeagueId] = useState(leagues.find((l) => l.id === initialLeague)?.id ?? leagues[0]?.id ?? "");
  const [tab, setTab] = useState<"fixtures" | "compare" | "data" | "method">(initialTeam ? "compare" : "fixtures");
  const [adv, setAdv] = useAdvanced();
  const league = leagues.find((l) => l.id === leagueId);
  const TABS = [["fixtures", "Fixtures"], ["compare", "Team comparison"], ["data", "Your data"], ["method", "Methodology & performance"]] as const;
  const onKey = useCallback((e: React.KeyboardEvent) => {
    const idx = TABS.findIndex((t) => t[0] === tab);
    if (e.key === "ArrowRight") setTab(TABS[(idx + 1) % TABS.length][0]);
    if (e.key === "ArrowLeft") setTab(TABS[(idx + TABS.length - 1) % TABS.length][0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  if (!leagues.length) return <Empty>No leagues are loaded. Run the seed script to load the development dataset.</Empty>;
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div>
          <label htmlFor="league" className="sr-only">League</label>
          <select id="league" value={leagueId} onChange={(e) => setLeagueId(e.target.value)} className="rounded-xl border border-line bg-bg/70 px-3 py-2 text-sm focus:border-violet focus:outline-none focus:ring-2 focus:ring-violet/40">
            {leagues.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </div>
        {league?.is_fictional && <Badge tone="amber">Fictional development data</Badge>}
        <label className="ml-auto flex cursor-pointer items-center gap-2 text-sm">
          <input type="checkbox" checked={adv} onChange={(e) => setAdv(e.target.checked)} className="h-4 w-4 accent-[#8055f6]" />
          Advanced analytics
        </label>
      </div>
      <div role="tablist" aria-label="Sports modules" onKeyDown={onKey} className="mb-4 inline-flex max-w-full overflow-x-auto rounded-xl border border-line bg-bg/60 p-1">
        {TABS.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} tabIndex={tab === id ? 0 : -1} onClick={() => setTab(id)} className={`whitespace-nowrap rounded-lg px-4 py-2 text-sm font-semibold ${tab === id ? "bg-primary text-white" : "text-muted hover:text-ink"}`}>{label}</button>
        ))}
      </div>
      <div role="tabpanel">
        {tab === "fixtures" && <FixturesTab key={leagueId} leagueId={leagueId} adv={adv} />}
        {tab === "compare" && <CompareTab key={leagueId} leagueId={leagueId} adv={adv} initialTeam={initialTeam} />}
        {tab === "data" && <DataForecastTab adv={adv} />}
        {tab === "method" && <MethodologyTab />}
      </div>
    </div>
  );
}
