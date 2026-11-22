"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Check, Loader2, Trash2 } from "lucide-react";
import { call, post } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel, dt } from "../ui";
import { field } from "../analysis";

interface Note { id: string; kind: string; title: string; body: string; source: { href?: string; retrieved_at?: string | null; type?: string } | null; created_at: string; read: boolean }
interface NList { notifications: Note[]; total: number; unread: number; held_for_quiet_hours: number; rules_enabled: number; retention_days: number }
interface Rule { id: string; kind: string; label: string; config: { days?: number }; enabled: boolean }
interface Kind { kind: string; label: string; description: string; needs: string; config: Record<string, { min: number; max: number; default: number }> }
interface Rules { rules: Rule[]; kinds: Kind[]; suggested: string[]; channels: { note: string } }
const PAGE = 15;
const json = (b: unknown): RequestInit => ({ headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) });

/** Notification inbox plus the alert rules that produce it. Rules are opt-in; the inbox is only ever the signed-in person's. */
export function NotificationsClient() {
  const [n, setN] = useState<NList | null>(null);
  const [r, setR] = useState<Rules | null>(null);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [offset, setOffset] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [a, b] = await Promise.all([call<NList>(`notifications?limit=${PAGE}&offset=${offset}${unreadOnly ? "&unread=true" : ""}`), call<Rules>("alert-rules")]);
      setN(a); setR(b); setErr(null);
    } catch (e) { setErr(e instanceof Error ? e.message : "Could not load notifications."); }
  }, [offset, unreadOnly]);
  useEffect(() => { const t = setTimeout(load, 0); return () => clearTimeout(t); }, [load]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true); setErr(null);
    try { await fn(); await load(); window.dispatchEvent(new Event("notifications-changed")); } catch (e) { setErr(e instanceof Error ? e.message : "That did not work."); } finally { setBusy(false); }
  }

  if (!n || !r) return err ? <ErrorPanel message={err} /> : <p className="text-sm text-muted" aria-busy="true">Loading notifications…</p>;
  const ruleOf = (k: string) => r.rules.find((x) => x.kind === k);
  return (
    <div className="space-y-4">
      {err && <p role="alert" className="text-sm text-red-300">{err}</p>}
      <Panel title="Inbox" badge={<Badge tone={n.unread ? "amber" : "muted"}>{n.unread} unread</Badge>}>
        <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={unreadOnly} onChange={(e) => { setUnreadOnly(e.target.checked); setOffset(0); }} className="h-4 w-4 accent-violet" /> Unread only</label>
          <button type="button" disabled={busy || n.unread === 0} onClick={() => act(() => post("notifications/read", { all: true }))} className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:bg-white/5 disabled:opacity-40"><Check className="h-3.5 w-3.5" aria-hidden="true" /> Mark all read</button>
          <button type="button" disabled={busy || n.total === 0} onClick={() => act(() => call("notifications", { method: "DELETE" }))} className="rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:bg-white/5 disabled:opacity-40">Clear read</button>
        </div>
        {n.notifications.length === 0 ? (
          <Empty>{n.rules_enabled === 0 ? "No alerts are switched on, so there is nothing here. Choose what to be told about below." : unreadOnly ? "No unread notifications." : "Nothing has happened yet. Your alerts are on and will appear here when something in your records changes."}</Empty>
        ) : (
          <ul className="divide-y divide-line" aria-label="Notifications">
            {n.notifications.map((x) => (
              <li key={x.id} className="flex items-start gap-3 py-3">
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${x.read ? "bg-transparent" : "bg-cyan"}`} aria-hidden="true" />
                <div className="min-w-0 flex-1 text-sm">
                  <p className={x.read ? "text-muted" : "font-semibold"}>{x.title}{!x.read && <span className="sr-only"> (unread)</span>}</p>
                  <p className="text-xs text-muted">{x.body}</p>
                  <p className="mt-1 text-[11px] text-muted">{dt(x.created_at)}{x.source?.href && <> · <Link href={x.source.href} className="text-violet underline">Open</Link></>}</p>
                </div>
                <button type="button" disabled={busy} onClick={() => act(() => call(`notifications/${x.id}`, { method: "PATCH", ...json({ read: !x.read }) }))} className="rounded-lg px-2 py-1 text-xs text-violet hover:bg-white/5">{x.read ? "Mark unread" : "Mark read"}</button>
                <button type="button" disabled={busy} onClick={() => act(() => call(`notifications/${x.id}`, { method: "DELETE" }))} aria-label={`Delete notification: ${x.title}`} className="rounded-lg p-1.5 text-muted hover:text-red-300"><Trash2 className="h-4 w-4" aria-hidden="true" /></button>
              </li>
            ))}
          </ul>
        )}
        {n.total > PAGE && (
          <div className="mt-3 flex items-center justify-between text-sm">
            <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))} className="rounded-lg border border-line px-3 py-1.5 disabled:opacity-40">Previous</button>
            <span className="text-xs text-muted">{offset + 1}–{Math.min(offset + PAGE, n.total)} of {n.total}</span>
            <button type="button" disabled={offset + PAGE >= n.total} onClick={() => setOffset(offset + PAGE)} className="rounded-lg border border-line px-3 py-1.5 disabled:opacity-40">Next</button>
          </div>
        )}
        {n.held_for_quiet_hours > 0 && <p className="mt-3 text-xs text-muted">{n.held_for_quiet_hours} notification{n.held_for_quiet_hours === 1 ? " is" : "s are"} being held until your quiet hours end.</p>}
        <p className="mt-3 text-[11px] text-muted">Notifications are kept for {n.retention_days} days. Quiet hours and the in-app switch are in <Link href="/dashboard/settings" className="text-violet underline">Settings</Link>.</p>
      </Panel>

      <Panel title="Alert rules" badge={<Badge tone="muted">Opt-in</Badge>}>
        <p className="mb-3 text-xs text-muted">{r.channels.note}</p>
        {r.rules.length === 0 && (
          <button type="button" disabled={busy} onClick={() => act(() => post("alert-rules/suggested", {}))} className="mb-4 inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Switch on the suggested alerts</button>
        )}
        <ul className="divide-y divide-line">
          {r.kinds.map((k) => {
            const rule = ruleOf(k.kind);
            const on = !!rule?.enabled;
            return (
              <li key={k.kind} className="flex flex-wrap items-start gap-3 py-3 text-sm">
                <input id={`rule-${k.kind}`} type="checkbox" checked={on} disabled={busy} onChange={(e) => act(() => rule ? call(`alert-rules/${rule.id}`, { method: "PATCH", ...json({ enabled: e.target.checked }) }) : post("alert-rules", { kind: k.kind }))} className="mt-1 h-4 w-4 accent-violet" />
                <div className="min-w-0 flex-1">
                  <label htmlFor={`rule-${k.kind}`} className="font-medium">{k.label}</label>
                  <p className="text-xs text-muted">{k.description} Needs: {k.needs}</p>
                </div>
                {k.kind === "fixture_soon" && rule && (
                  <div className="flex items-center gap-2 text-xs"><label htmlFor="rule-days" className="text-muted">Within</label>
                    <select id="rule-days" value={rule.config.days ?? k.config.days.default} disabled={busy} onChange={(e) => act(() => call(`alert-rules/${rule.id}`, { method: "PATCH", ...json({ config: { days: Number(e.target.value) } }) }))} className={field}>
                      {[1, 2, 3, 5, 7, 14].map((d) => <option key={d} value={d}>{d} day{d === 1 ? "" : "s"}</option>)}
                    </select></div>
                )}
              </li>
            );
          })}
        </ul>
      </Panel>
    </div>
  );
}
