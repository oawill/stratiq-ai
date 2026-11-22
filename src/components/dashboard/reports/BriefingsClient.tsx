"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import { call } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel, dt } from "../ui";
import { field } from "../analysis";
import { DOMAIN_LABELS } from "../control/ControlCenter";

interface Row { id: string; period: "daily" | "weekly"; domains: string[]; created_at: string; window_start: string; window_end: string; has_changes: boolean }
interface List { briefings: Row[]; total: number; frequency: string; retention_days: number }
interface Item { text: string; type: "observed" | "forecast" | "note"; watched?: boolean; citation: { source: string; retrieved_at: string; window: string | null; href: string } }
interface Detail { id: string; title: string; generated_at: string; window: { start: string; end: string }; domains: string[]; sections: { id: string; domain: string; title: string; items: Item[] }[]; empty: boolean; message: string | null; legend: Record<string, string> }
const TONE = { observed: "cyan", forecast: "violet", note: "muted" } as const;

function View({ b }: { b: Detail }) {
  return (
    <div className="space-y-4">
      <p className="text-xs text-muted">{b.title} · covers {dt(b.window.start)} to {dt(b.window.end)} · domains: {b.domains.map((d) => DOMAIN_LABELS[d]).join(", ")}</p>
      {b.empty && <Empty>{b.message}</Empty>}
      <dl className="flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-muted">
        {Object.entries(b.legend).map(([k, v]) => <div key={k} className="flex gap-1.5"><dt><Badge tone={TONE[k as keyof typeof TONE] ?? "muted"}>{k}</Badge></dt><dd>{v}</dd></div>)}
      </dl>
      {b.sections.map((s) => (
        <Panel key={s.id} title={s.title} badge={<Badge tone="muted">{DOMAIN_LABELS[s.domain] ?? s.domain}</Badge>}>
          <ul className="space-y-3">
            {s.items.map((i, k) => (
              <li key={k} className="text-sm">
                <div className="flex gap-2"><Badge tone={TONE[i.type]}>{i.type}</Badge><span>{i.text}{i.watched && <span className="text-xs text-cyan"> (you watch this)</span>}</span></div>
                <p className="ml-1 mt-1 text-[11px] text-muted">Source: {i.citation.source}{i.citation.window ? ` · ${i.citation.window}` : ""} · retrieved {dt(i.citation.retrieved_at)} · <Link href={i.citation.href} className="text-violet underline">Open</Link></p>
              </li>
            ))}
          </ul>
        </Panel>
      ))}
    </div>
  );
}

/** Daily and weekly briefings built from the person's own records. Each line is labelled observed, forecast or note and cites its record. */
export function BriefingsClient() {
  const [l, setL] = useState<List | null>(null);
  const [open, setOpen] = useState<Detail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [period, setPeriod] = useState<"daily" | "weekly">("daily");

  const load = useCallback(() => call<List>("briefings").then((x) => { setL(x); setErr(null); }, (e) => setErr(e instanceof Error ? e.message : "Could not load briefings.")), []);
  useEffect(() => { const t = setTimeout(load, 0); return () => clearTimeout(t); }, [load]);

  async function generate() {
    setBusy(true); setErr(null);
    try {
      const b = await call<Detail>("briefings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ period }) });
      setOpen(b); await load(); window.dispatchEvent(new Event("notifications-changed"));
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not generate a briefing."); } finally { setBusy(false); }
  }
  async function show(id: string) {
    setErr(null);
    try { setOpen(await call<Detail>(`briefings/${id}`)); } catch (e) { setErr(e instanceof Error ? e.message : "Could not open that briefing."); }
  }
  async function remove(id: string) {
    setErr(null);
    try { await call(`briefings/${id}`, { method: "DELETE" }); if (open?.id === id) setOpen(null); await load(); } catch (e) { setErr(e instanceof Error ? e.message : "Could not delete."); }
  }

  if (!l) return err ? <ErrorPanel message={err} /> : <p className="text-sm text-muted" aria-busy="true">Loading briefings…</p>;
  return (
    <div className="space-y-4">
      <Panel title="Generate a briefing" badge={<Badge tone={l.frequency === "off" ? "muted" : "green"}>{l.frequency === "off" ? "Automatic briefings off" : `Automatic: ${l.frequency}`}</Badge>}>
        <div className="flex flex-wrap items-end gap-3">
          <div><label htmlFor="bp" className="mb-1 block text-xs text-muted">Period</label><select id="bp" value={period} onChange={(e) => setPeriod(e.target.value as "daily" | "weekly")} className={field}><option value="daily">Last 24 hours</option><option value="weekly">Last 7 days</option></select></div>
          <button type="button" onClick={generate} disabled={busy} className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Generate briefing</button>
        </div>
        <p className="mt-2 text-xs text-muted">A briefing only reports what is in your records. If nothing changed it says so. Choose automatic daily or weekly briefings and their domains in <Link href="/dashboard/settings" className="text-violet underline">Settings</Link>. Kept for {l.retention_days} days.</p>
        {err && <p role="alert" className="mt-2 text-sm text-red-300">{err}</p>}
      </Panel>

      {open && <Panel title={open.title} badge={<button type="button" onClick={() => setOpen(null)} className="text-xs text-violet underline">Close</button>}><View b={open} /></Panel>}

      <Panel title="Your briefings">
        {l.briefings.length === 0 ? <Empty>No briefings yet. Generate one above.</Empty> : (
          <ul className="divide-y divide-line" aria-label="Briefings">
            {l.briefings.map((b) => (
              <li key={b.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
                <button type="button" onClick={() => show(b.id)} className="font-medium capitalize text-violet hover:underline">{b.period} briefing</button>
                <span className="text-xs text-muted">{dt(b.created_at)}</span>
                <Badge tone={b.has_changes ? "cyan" : "muted"}>{b.has_changes ? "Had changes" : "Nothing new"}</Badge>
                <button type="button" onClick={() => remove(b.id)} aria-label={`Delete ${b.period} briefing from ${dt(b.created_at)}`} className="ml-auto rounded-lg p-1.5 text-muted hover:text-red-300"><Trash2 className="h-4 w-4" aria-hidden="true" /></button>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
