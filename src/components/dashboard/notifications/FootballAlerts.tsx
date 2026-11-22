"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { call } from "@/lib/client";
import { Badge, ErrorPanel, Panel } from "../ui";
import { field } from "../analysis";

interface Cat { id: string; label: string; description: string; available: boolean; unavailable_reason?: string; team_scoped: boolean }
interface Settings {
  categories: string[]; competitions: string[]; teams: string[]; channels: { email: boolean; push: boolean }; configured: boolean; catalogue: Cat[];
  channel_status: Record<string, { available: boolean; reason: string }>; teams_available: string[]; note: string;
}

/** Football alert choices. Everything starts off; alerts appear in the notifications above and nothing leaves the app. */
export function FootballAlerts() {
  const [s, setS] = useState<Settings | null>(null);
  const [cats, setCats] = useState<string[]>([]);
  const [teams, setTeams] = useState<string[]>([]);
  const [pick, setPick] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => call<Settings>("football/live/alert-settings").then((x) => { setS(x); setCats(x.categories); setTeams(x.teams); setErr(null); }, (e) => setErr(e instanceof Error ? e.message : "Could not load football alert settings.")), []);
  useEffect(() => { const t = setTimeout(load, 0); return () => clearTimeout(t); }, [load]);

  async function save() {
    setBusy(true); setMsg(null);
    try {
      await call("football/live/alert-settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ categories: cats, teams, competitions: ["EPL"], channels: { email: false, push: false } }) });
      setMsg("Saved."); await load();
    } catch (e) { setMsg(e instanceof Error ? e.message : "Could not save."); } finally { setBusy(false); }
  }
  const toggle = (id: string) => setCats((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));

  if (err) return <ErrorPanel message={err} />;
  if (!s) return <p className="text-sm text-muted" aria-busy="true">Loading football alerts…</p>;
  const dirty = cats.slice().sort().join() !== s.categories.slice().sort().join() || teams.slice().sort().join() !== s.teams.slice().sort().join();
  const addable = s.teams_available.filter((t) => !teams.includes(t));
  return (
    <Panel title="Football alerts" badge={<Badge tone={s.categories.length ? "green" : "muted"}>{s.categories.length ? `${s.categories.length} on` : "All off"}</Badge>}>
      <div className="space-y-4 text-sm">
        <p className="text-xs text-muted">{s.note}</p>
        <fieldset>
          <legend className="mb-2 font-medium">Tell me about</legend>
          <ul className="space-y-2">
            {s.catalogue.map((c) => (
              <li key={c.id}>
                <label className={`flex items-start gap-2 ${c.available ? "" : "opacity-60"}`}>
                  <input type="checkbox" className="mt-0.5 h-4 w-4 accent-violet" checked={cats.includes(c.id)} disabled={!c.available} onChange={() => toggle(c.id)} />
                  <span><span className="font-medium">{c.label}</span> <span className="text-xs text-muted">{c.description}{!c.available && c.unavailable_reason ? ` Not available: ${c.unavailable_reason}` : ""}</span></span>
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
        <fieldset>
          <legend className="mb-1 font-medium">Only for these clubs <span className="text-xs font-normal text-muted">(leave empty for every club; provider and data alerts ignore this)</span></legend>
          <div className="flex flex-wrap items-center gap-2">
            {teams.map((t) => <button key={t} type="button" onClick={() => setTeams(teams.filter((x) => x !== t))} aria-label={`Remove ${t}`} className="rounded-full border border-line px-2.5 py-1 text-xs hover:border-red-400">{t} ×</button>)}
            <label htmlFor="fa-team" className="sr-only">Add a club</label>
            <select id="fa-team" value={pick} onChange={(e) => { if (e.target.value && teams.length < 20) setTeams([...teams, e.target.value]); setPick(""); }} className={field}>
              <option value="">Add a club…</option>{addable.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        </fieldset>
        <p className="text-xs text-muted">Competition: Premier League. Email: {s.channel_status.email.reason} Push: {s.channel_status.push.reason}</p>
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" onClick={save} disabled={busy || !dirty} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Save football alerts</button>
          {msg && <p role="status" className="text-xs text-muted">{msg}</p>}
        </div>
      </div>
    </Panel>
  );
}
