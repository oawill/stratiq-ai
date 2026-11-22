"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { call } from "@/lib/client";
import { Badge, ErrorPanel, Panel } from "../ui";
import { field } from "../analysis";
import { DOMAIN_LABELS } from "../control/ControlCenter";

interface Quiet { enabled: boolean; start: string; end: string; utc_offset_minutes: number }
interface Prefs { notifications: { in_app: boolean; quiet_hours: Quiet }; briefing: { frequency: "off" | "daily" | "weekly"; domains: string[] }; channels: { note: string } }

/** Notification, quiet-hours and briefing preferences. Everything starts off or neutral; nothing is sent outside the app. */
export function PreferencesPanel() {
  const [p, setP] = useState<Prefs | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => call<Prefs>("preferences").then((x) => { setP(x); setErr(null); }, (e) => setErr(e instanceof Error ? e.message : "Could not load preferences.")), []);
  useEffect(() => { const t = setTimeout(load, 0); return () => clearTimeout(t); }, [load]);

  async function save() {
    if (!p) return;
    setBusy(true); setErr(null); setMsg(null);
    try {
      const r = await call<Prefs>("preferences", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ notifications: { in_app: p.notifications.in_app, quiet_hours: p.notifications.quiet_hours }, briefing: p.briefing }) });
      setP({ ...r, channels: r.channels ?? p.channels }); setMsg("Preferences saved.");
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not save."); } finally { setBusy(false); }
  }

  if (!p) return err ? <ErrorPanel message={err} /> : <p className="text-sm text-muted" aria-busy="true">Loading preferences…</p>;
  const q = p.notifications.quiet_hours;
  const setQ = (x: Partial<Quiet>) => setP({ ...p, notifications: { ...p.notifications, quiet_hours: { ...q, ...x } } });
  const bd = p.briefing.domains;
  const toggleDomain = (id: string) => {
    const has = bd.includes(id);
    if (has && bd.length === 1) return;
    setP({ ...p, briefing: { ...p.briefing, domains: Object.keys(DOMAIN_LABELS).filter((d) => d === id ? !has : bd.includes(d)) } });
  };
  return (
    <>
      <Panel title="Notifications" badge={<Badge tone="muted">In-app only</Badge>}>
        <div className="space-y-4 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={p.notifications.in_app} onChange={(e) => setP({ ...p, notifications: { ...p.notifications, in_app: e.target.checked } })} className="h-4 w-4 accent-violet" /> Show in-app notifications</label>
          <fieldset>
            <legend className="mb-2 font-medium">Quiet hours</legend>
            <label className="flex items-center gap-2"><input type="checkbox" checked={q.enabled} onChange={(e) => setQ({ enabled: e.target.checked })} className="h-4 w-4 accent-violet" /> Hold notifications back during these hours</label>
            <div className="mt-2 flex flex-wrap items-end gap-3">
              <div><label htmlFor="qh-start" className="mb-1 block text-xs text-muted">From</label><input id="qh-start" type="time" value={q.start} disabled={!q.enabled} onChange={(e) => setQ({ start: e.target.value })} className={field} /></div>
              <div><label htmlFor="qh-end" className="mb-1 block text-xs text-muted">Until</label><input id="qh-end" type="time" value={q.end} disabled={!q.enabled} onChange={(e) => setQ({ end: e.target.value })} className={field} /></div>
              <div><label htmlFor="qh-off" className="mb-1 block text-xs text-muted">Your time zone</label>
                <select id="qh-off" value={q.utc_offset_minutes} disabled={!q.enabled} onChange={(e) => setQ({ utc_offset_minutes: Number(e.target.value) })} className={field}>
                  {Array.from({ length: 27 }, (_, i) => (i - 12) * 60).concat([330, 345, 570]).sort((a, b) => a - b).map((m) => <option key={m} value={m}>UTC{m < 0 ? "-" : "+"}{String(Math.floor(Math.abs(m) / 60)).padStart(2, "0")}:{String(Math.abs(m) % 60).padStart(2, "0")}</option>)}
                </select></div>
            </div>
            <p className="mt-2 text-xs text-muted">Notifications created during quiet hours are not lost. They appear when the quiet period ends.</p>
          </fieldset>
          <p className="text-xs text-muted">{p.channels.note}</p>
        </div>
      </Panel>

      <Panel title="Briefings" badge={<Badge tone="muted">Off by default</Badge>}>
        <div className="space-y-4 text-sm">
          <div><label htmlFor="bf" className="mb-1 block text-xs text-muted">Generate a briefing automatically</label>
            <select id="bf" value={p.briefing.frequency} onChange={(e) => setP({ ...p, briefing: { ...p.briefing, frequency: e.target.value as Prefs["briefing"]["frequency"] } })} className={field}>
              <option value="off">Never (generate manually)</option><option value="daily">Daily</option><option value="weekly">Weekly</option>
            </select></div>
          <fieldset>
            <legend className="mb-2 text-xs text-muted">Domains to include</legend>
            <div className="flex flex-wrap gap-3">{Object.entries(DOMAIN_LABELS).map(([id, label]) => <label key={id} className="flex items-center gap-2"><input type="checkbox" checked={bd.includes(id)} onChange={() => toggleDomain(id)} className="h-4 w-4 accent-violet" />{label}</label>)}</div>
          </fieldset>
          <p className="text-xs text-muted">Briefings are built from your own records when you open your overview. They separate what happened from model forecasts, cite the record behind each line, and say so when nothing changed.</p>
        </div>
      </Panel>

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={save} disabled={busy} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Save preferences</button>
        {msg && <p role="status" className="text-sm text-emerald-300">{msg}</p>}
        {err && <p role="alert" className="text-sm text-red-300">{err}</p>}
      </div>
    </>
  );
}
