"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowDown, ArrowRight, ArrowUp, Loader2, RotateCcw, SlidersHorizontal } from "lucide-react";
import { call } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel, dt } from "../ui";

export const WIDGET_LABELS: Record<string, string> = {
  brief: "Intelligence brief",
  tracked: "Tracked items",
  changes: "What changed",
  alerts: "Alerts",
  predictions: "Recent predictions",
  scenarios: "Saved scenarios",
  quick_actions: "Quick actions",
};
export const DOMAIN_LABELS: Record<string, string> = { sports: "Sports", business: "Business", politics: "Politics", markets: "Markets" };

interface Layout { id: string; visible: boolean }
interface Dash { widgets: Layout[]; domains: string[]; density: "comfortable" | "compact" }
interface Item { id: string; label: string; domain: string; kind: string; status: { feed?: string; note?: string; played?: number; competition?: string; matches?: number } | null }
interface Ev { type: string; domain: string; title: string; detail: string; at: string; href: string }
interface Pred { title: string; date: string | null; status: string; at: string; href: string }
interface Scen { id: string; title: string; domain: string; version: number; at: string; href: string; kind: string }
interface Note { id: string; title: string; body: string; at: string; read: boolean }
interface Hl { text: string; type: string }
interface CC {
  user: { name: string | null }; workspace: string | null; role: string; generated_at: string; preferences: Dash; domains: string[]; layout: Layout[];
  widgets: {
    tracked?: { items: Item[]; total: number; empty: boolean; hint: string };
    changes?: { events: Ev[]; empty: boolean; hint: string };
    alerts?: { unread: number; rules_enabled: number; latest: Note[]; empty: boolean; hint: string };
    predictions?: { recent: Pred[]; empty: boolean; hidden_by_domains: boolean; hint: string };
    scenarios?: { recent: Scen[]; empty: boolean; hint: string };
    brief?: { latest: { id: string; period: string; created_at: string; has_changes: boolean; message: string | null; highlights: Hl[] } | null; frequency: string; generated_now: boolean; empty: boolean; hint: string };
    quick_actions?: { actions: { id: string; label: string; href: string }[] };
  };
}

function trackedStatus(i: Item) {
  const s = i.status;
  if (!s) return "No status";
  if (s.feed === "none") return "Your own note. No data feed.";
  if (s.competition) return `${s.matches} matches imported`;
  if (typeof s.played === "number") return `${s.played} matches in your data`;
  return s.note ?? "";
}

function Widget({ id, d, busy, onGenerate }: { id: string; d: CC; busy: boolean; onGenerate: () => void }) {
  const w = d.widgets;
  if (id === "brief" && w.brief) {
    const b = w.brief;
    return (
      <Panel title="Intelligence brief" badge={<Badge tone={b.frequency === "off" ? "muted" : "green"}>{b.frequency === "off" ? "Manual" : `${b.frequency} briefings`}</Badge>}>
        {!b.latest ? <Empty>{b.hint}</Empty> : (
          <div className="space-y-2 text-sm">
            <p className="text-xs text-muted">{b.latest.period} briefing generated {dt(b.latest.created_at)}</p>
            {b.latest.has_changes ? (
              <ul className="space-y-1.5">{b.latest.highlights.map((h, i) => <li key={i} className="flex gap-2"><Badge tone={h.type === "forecast" ? "violet" : "cyan"}>{h.type}</Badge><span>{h.text}</span></li>)}</ul>
            ) : <p className="text-muted">{b.latest.message}</p>}
          </div>
        )}
        <div className="mt-3 flex flex-wrap gap-3 text-xs">
          <button type="button" onClick={onGenerate} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg border border-violet/60 px-3 py-1.5 font-semibold text-violet hover:bg-violet/10 disabled:opacity-50">
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />} Generate a briefing now
          </button>
          <Link href="/dashboard/reports?tab=briefings" className="py-1.5 text-violet underline">All briefings</Link>
        </div>
      </Panel>
    );
  }
  if (id === "tracked" && w.tracked) {
    const t = w.tracked;
    return (
      <Panel title="Tracked items" badge={<Link href="/dashboard/watchlists" className="text-xs text-violet underline">Manage</Link>}>
        {t.empty ? <Empty>{t.hint}</Empty> : (
          <ul className="divide-y divide-line">{t.items.map((i) => (
            <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <span className="font-medium">{i.label} <Badge tone="muted">{DOMAIN_LABELS[i.domain] ?? i.domain}</Badge></span>
              <span className="text-xs text-muted">{trackedStatus(i)}</span>
            </li>))}</ul>
        )}
        {!t.empty && t.total > t.items.length && <p className="mt-2 text-xs text-muted">Showing {t.items.length} of {t.total}.</p>}
      </Panel>
    );
  }
  if (id === "changes" && w.changes) {
    const c = w.changes;
    return (
      <Panel title="What changed" badge={<Badge tone="muted">From your records</Badge>}>
        {c.empty ? <Empty>{c.hint}</Empty> : (
          <ul className="divide-y divide-line">{c.events.map((e, i) => (
            <li key={i} className="py-2 text-sm">
              <Link href={e.href} className="font-medium hover:text-violet">{e.title}</Link>
              <div className="text-[11px] text-muted">{e.detail} · {dt(e.at)}</div>
            </li>))}</ul>
        )}
      </Panel>
    );
  }
  if (id === "alerts" && w.alerts) {
    const a = w.alerts;
    return (
      <Panel title="Alerts" badge={a.unread > 0 ? <Badge tone="amber">{a.unread} unread</Badge> : <Link href="/dashboard/notifications" className="text-xs text-violet underline">Notifications</Link>}>
        {a.empty ? <Empty>{a.hint}</Empty> : a.latest.length === 0 ? <p className="text-sm text-muted">No notifications yet. {a.rules_enabled} alert rule{a.rules_enabled === 1 ? " is" : "s are"} on and watching your records.</p> : (
          <ul className="space-y-2">{a.latest.map((n) => (
            <li key={n.id} className="text-sm"><span className={n.read ? "text-muted" : "font-semibold"}>{n.title}</span><div className="text-[11px] text-muted">{dt(n.at)}</div></li>))}</ul>
        )}
        {a.unread > 0 && <Link href="/dashboard/notifications" className="mt-3 inline-block text-xs text-violet underline">Open notifications</Link>}
      </Panel>
    );
  }
  if (id === "predictions" && w.predictions) {
    const p = w.predictions;
    return (
      <Panel title="Recent predictions" badge={<Link href="/dashboard/history" className="text-xs text-violet underline">History</Link>}>
        {p.hidden_by_domains ? <Empty>Sports is not one of your chosen domains, so forecasts are hidden. Change this in Customize.</Empty> : p.empty ? <Empty>{p.hint}</Empty> : (
          <ul className="divide-y divide-line">{p.recent.map((r, i) => (
            <li key={i} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"><span className="font-medium">{r.title}</span><span className="text-xs text-muted">{r.status} · {dt(r.at)}</span></li>))}</ul>
        )}
      </Panel>
    );
  }
  if (id === "scenarios" && w.scenarios) {
    const s = w.scenarios;
    return (
      <Panel title="Saved scenarios" badge={<Link href="/dashboard/reports?tab=library" className="text-xs text-violet underline">Library</Link>}>
        {s.empty ? <Empty>{s.hint}</Empty> : (
          <ul className="divide-y divide-line">{s.recent.map((r) => (
            <li key={r.kind + r.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <Link href={r.href} className="font-medium hover:text-violet">{r.title}</Link>
              <span className="text-xs text-muted"><Badge tone="muted">{DOMAIN_LABELS[r.domain] ?? r.domain}</Badge> v{r.version} · {dt(r.at)}</span>
            </li>))}</ul>
        )}
        <p className="mt-2 text-[11px] text-muted">Scenarios are hypothetical, built from numbers someone entered.</p>
      </Panel>
    );
  }
  if (id === "quick_actions" && w.quick_actions) {
    return (
      <Panel title="Quick actions">
        <div className="grid gap-2 sm:grid-cols-2">
          {w.quick_actions.actions.map((a) => (
            <Link key={a.id} href={a.href} className="flex items-center gap-2 rounded-xl border border-line bg-white/5 p-3 text-sm font-medium hover:border-violet/50">{a.label}<ArrowRight className="ml-auto h-4 w-4" aria-hidden="true" /></Link>
          ))}
        </div>
      </Panel>
    );
  }
  return null;
}

function Customize({ initial, onSaved }: { initial: Dash; onSaved: () => void }) {
  const [d, setD] = useState<Dash>(initial);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const move = (i: number, dir: -1 | 1) => setD((x) => {
    const w = [...x.widgets];
    const j = i + dir;
    if (j < 0 || j >= w.length) return x;
    [w[i], w[j]] = [w[j], w[i]];
    return { ...x, widgets: w };
  });
  const toggleW = (id: string) => setD((x) => ({ ...x, widgets: x.widgets.map((w) => (w.id === id ? { ...w, visible: !w.visible } : w)) }));
  const toggleD = (id: string) => setD((x) => {
    const has = x.domains.includes(id);
    if (has && x.domains.length === 1) return x;
    return { ...x, domains: has ? x.domains.filter((v) => v !== id) : Object.keys(DOMAIN_LABELS).filter((v) => v === id || x.domains.includes(v)) };
  });

  async function save() {
    setBusy(true); setErr(null); setMsg(null);
    try {
      await call("preferences", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dashboard: d }) });
      setMsg("Layout saved."); onSaved();
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not save."); } finally { setBusy(false); }
  }
  async function reset() {
    setBusy(true); setErr(null); setMsg(null);
    try {
      const r = await call<{ dashboard: Dash }>("preferences", { method: "DELETE" });
      setD(r.dashboard); setMsg("Default layout restored."); onSaved();
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not restore."); } finally { setBusy(false); }
  }

  return (
    <Panel title="Customize your overview" badge={<Badge tone="muted">Saved to your account</Badge>}>
      <div className="grid gap-6 md:grid-cols-2">
        <fieldset>
          <legend className="mb-2 text-xs text-muted">Sections: show, hide and reorder</legend>
          <ol className="space-y-1.5">
            {d.widgets.map((w, i) => (
              <li key={w.id} className="flex items-center gap-2 rounded-lg border border-line px-3 py-1.5 text-sm">
                <input id={`cw-${w.id}`} type="checkbox" checked={w.visible} onChange={() => toggleW(w.id)} className="h-4 w-4 accent-violet" />
                <label htmlFor={`cw-${w.id}`} className="flex-1">{WIDGET_LABELS[w.id] ?? w.id}</label>
                <button type="button" onClick={() => move(i, -1)} disabled={i === 0} aria-label={`Move ${WIDGET_LABELS[w.id]} up`} className="rounded p-1 text-muted hover:text-ink disabled:opacity-30"><ArrowUp className="h-4 w-4" aria-hidden="true" /></button>
                <button type="button" onClick={() => move(i, 1)} disabled={i === d.widgets.length - 1} aria-label={`Move ${WIDGET_LABELS[w.id]} down`} className="rounded p-1 text-muted hover:text-ink disabled:opacity-30"><ArrowDown className="h-4 w-4" aria-hidden="true" /></button>
              </li>
            ))}
          </ol>
        </fieldset>
        <div className="space-y-5">
          <fieldset>
            <legend className="mb-2 text-xs text-muted">Preferred domains (at least one)</legend>
            <div className="flex flex-wrap gap-3">
              {Object.entries(DOMAIN_LABELS).map(([id, label]) => (
                <label key={id} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={d.domains.includes(id)} onChange={() => toggleD(id)} className="h-4 w-4 accent-violet" />{label}</label>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend className="mb-2 text-xs text-muted">Density</legend>
            <div className="flex gap-4 text-sm">
              {(["comfortable", "compact"] as const).map((v) => (
                <label key={v} className="flex items-center gap-2 capitalize"><input type="radio" name="density" checked={d.density === v} onChange={() => setD({ ...d, density: v })} className="accent-violet" />{v}</label>
              ))}
            </div>
          </fieldset>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button type="button" onClick={save} disabled={busy} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Save layout</button>
        <button type="button" onClick={reset} disabled={busy} className="inline-flex items-center gap-2 rounded-xl border border-line px-4 py-2 text-sm font-semibold hover:bg-white/5 disabled:opacity-50"><RotateCcw className="h-4 w-4" aria-hidden="true" /> Restore default</button>
        {msg && <p role="status" className="text-sm text-emerald-300">{msg}</p>}
        {err && <p role="alert" className="text-sm text-red-300">{err}</p>}
      </div>
    </Panel>
  );
}

/** The personalised overview: every widget is read from this person's own records, and each says plainly when it has nothing to show. */
export function ControlCenter() {
  const [d, setD] = useState<CC | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [custom, setCustom] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => call<CC>("control-center").then((x) => { setD(x); setErr(null); }, (e) => setErr(e instanceof Error ? e.message : "Could not load your overview.")), []);
  useEffect(() => { const t = setTimeout(load, 0); return () => clearTimeout(t); }, [load]);

  async function generate() {
    setBusy(true);
    try {
      await call("briefings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ period: "daily" }) });
      await load();
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not generate a briefing."); } finally { setBusy(false); }
  }

  if (err && !d) return <ErrorPanel message={err} />;
  if (!d) return <p className="text-sm text-muted" aria-busy="true">Loading your overview…</p>;
  const compact = d.preferences.density === "compact";
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted">{d.workspace} · {d.role} · {d.domains.map((x) => DOMAIN_LABELS[x]).join(", ")}. Updated {dt(d.generated_at)}. Everything here is read from your own records; nothing is estimated.</p>
        <button type="button" onClick={() => setCustom((v) => !v)} aria-expanded={custom} className="inline-flex items-center gap-2 rounded-xl border border-line px-3 py-2 text-sm font-semibold hover:bg-white/5"><SlidersHorizontal className="h-4 w-4" aria-hidden="true" /> Customize</button>
      </div>
      {err && <p role="alert" className="text-sm text-red-300">{err}</p>}
      {custom && <Customize initial={d.preferences} onSaved={load} />}
      {d.layout.length === 0 ? <Empty>All sections are hidden. Use Customize to show some.</Empty> : (
        <div className={`grid gap-4 md:grid-cols-2 ${compact ? "text-[13px] [&_section]:!p-3" : ""}`}>
          {d.layout.map((l) => <Widget key={l.id} id={l.id} d={d} busy={busy} onGenerate={generate} />)}
        </div>
      )}
    </div>
  );
}
