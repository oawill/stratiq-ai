"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { call } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel } from "../../ui";
import { kickoff, stamp } from "./live";

interface Settings { checkpoint_minutes: number[]; auto_forecast: boolean; default: boolean }
interface Schedule {
  settings: Settings; upcoming: { fixture_id: string; home_team: string; away_team: string; kickoff_utc: string; next_refresh_at: string | null; next_refresh_label: string | null }[];
  last_run: { at: string; status: string } | null; scheduler_configured: boolean; provider_configured: boolean; fixture_sync_every_minutes: { normal: number; around_kickoff: number }; note: string;
}
const PRESETS = [2880, 1440, 720, 360, 180, 60, 30];
const label = (m: number) => (m % 1440 === 0 ? `${m / 1440} day${m > 1440 ? "s" : ""}` : m % 60 === 0 ? `${m / 60} hour${m > 60 ? "s" : ""}` : `${m} minutes`);
const every = (m: number) => (m % 60 === 0 ? `${m / 60} hours` : `${m} minutes`);

/** What refreshes forecasts automatically, when it runs next, and the checkpoints a member can choose. Honest about whether anything is actually scheduled. */
export function Automation({ tz }: { tz: string }) {
  const [s, setS] = useState<Schedule | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<number[]>([]);
  const [auto, setAuto] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(() => call<Schedule>("football/live/schedule").then((x) => { setS(x); setSel(x.settings.checkpoint_minutes); setAuto(x.settings.auto_forecast); setErr(null); }, (e) => setErr(e instanceof Error ? e.message : "Could not load the automation status.")), []);
  useEffect(() => { const t = setTimeout(load, 0); return () => clearTimeout(t); }, [load]);

  async function save() {
    setBusy(true); setMsg(null);
    try {
      await call("football/live/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ checkpoint_minutes: sel, auto_forecast: auto }) });
      setMsg("Saved."); await load();
    } catch (e) { setMsg(e instanceof Error ? e.message : "Could not save."); } finally { setBusy(false); }
  }
  const toggle = (m: number) => setSel((cur) => (cur.includes(m) ? cur.filter((x) => x !== m) : [...cur, m].sort((a, b) => b - a)));

  if (err) return <ErrorPanel message={err} />;
  if (!s) return <p className="text-sm text-muted" aria-busy="true">Loading automation…</p>;
  const options = [...new Set([...PRESETS, ...s.settings.checkpoint_minutes])].sort((a, b) => b - a);
  const dirty = auto !== s.settings.auto_forecast || sel.join() !== s.settings.checkpoint_minutes.join();
  return (
    <Panel title="Automatic forecasts" badge={<Badge tone={s.scheduler_configured ? "green" : "amber"}>{s.scheduler_configured ? "Scheduler configured" : "No scheduler running"}</Badge>}>
      <div className="space-y-4 text-sm">
        <p className="text-xs text-muted">{s.note} Fixtures are synchronised about every {every(s.fixture_sync_every_minutes.normal)}, and every {every(s.fixture_sync_every_minutes.around_kickoff)} around kickoff.{s.provider_configured ? "" : " No fixture provider key is configured, so only forecasts for fixtures already stored are refreshed."} {s.last_run ? `Last automatic run ${stamp(s.last_run.at, tz)} (${s.last_run.status}).` : "No automatic run has happened yet."}</p>
        <fieldset>
          <legend className="mb-2 font-medium">Refresh a forecast this long before kickoff</legend>
          <div className="flex flex-wrap gap-x-5 gap-y-2">
            {options.map((m) => <label key={m} className="flex items-center gap-2"><input type="checkbox" checked={sel.includes(m)} onChange={() => toggle(m)} className="h-4 w-4 accent-violet" />{label(m)}</label>)}
          </div>
          <p className="mt-2 text-xs text-muted">A new version is stored only if something the forecast depends on has changed. Earlier versions are kept. Lineup changes cannot trigger a refresh because the fixture provider plan in use supplies no lineups; a moved kickoff does.</p>
        </fieldset>
        <label className="flex items-center gap-2"><input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} className="h-4 w-4 accent-violet" /> Forecast new fixtures automatically</label>
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" onClick={save} disabled={busy || !dirty || sel.length === 0} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Save</button>
          {sel.length === 0 && <p role="alert" className="text-xs text-amber-200">Choose at least one checkpoint.</p>}
          {msg && <p role="status" className="text-xs text-muted">{msg}</p>}
        </div>
        <div>
          <h3 className="mb-1 text-xs font-semibold text-muted">Next refreshes (matches in the next 7 days)</h3>
          {s.upcoming.length === 0 ? <Empty>No scheduled matches in the next 7 days.</Empty> : (
            <ul className="divide-y divide-line text-xs" aria-label="Next refreshes">{s.upcoming.map((u) => <li key={u.fixture_id} className="flex flex-wrap justify-between gap-2 py-1.5"><span>{u.home_team} v {u.away_team} <span className="text-muted">({kickoff(u.kickoff_utc, tz)})</span></span><span className="text-muted">{u.next_refresh_at ? `${stamp(u.next_refresh_at, tz)}: ${u.next_refresh_label}` : "no checkpoint left"}</span></li>)}</ul>
          )}
        </div>
      </div>
    </Panel>
  );
}
