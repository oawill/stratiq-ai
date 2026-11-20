"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Download, Loader2, Plus } from "lucide-react";
import { call, post } from "@/lib/client";
import type { LibraryItem, WorkspaceRow } from "@/lib/types";
import { Badge, Empty, ErrorPanel, Panel, dt } from "../ui";
import { field } from "../analysis";
import { ExplainToggle } from "../assistant/AssistantPanel";
import { CommentsToggle } from "../team/Comments";

const MODULE: Record<string, { label: string; href: string }> = {
  sports: { label: "Sports", href: "/dashboard/history" }, business: { label: "Business", href: "/dashboard/business" }, politics: { label: "Politics", href: "/dashboard/politics" },
  finance: { label: "Finance", href: "/dashboard/finance" }, simulation: { label: "Simulation", href: "/dashboard/simulations" },
};
const KIND: Record<string, string> = { prediction: "Forecast", business: "Game", coalition: "Coalition", turnout: "Turnout", policy: "Policy", montecarlo: "Monte Carlo", stress: "Stress test", historical: "Historical", monte_carlo: "Simulation run" };

function Workspaces() {
  const [list, setList] = useState<WorkspaceRow[] | null>(null);
  const [current, setCurrent] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    call<{ workspaces: WorkspaceRow[]; current: string }>("workspaces").then((d) => { if (live) { setList(d.workspaces); setCurrent(d.current); } }).catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, []);
  async function switchTo(id: string) {
    setBusy(id); setErr(null);
    try { await post("workspaces/activate", { workspace_id: id }); window.location.reload(); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); setBusy(null); }
  }
  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy("new"); setErr(null);
    try { await post("workspaces", { name: name.trim() }); window.location.reload(); } catch (er) { setErr(er instanceof Error ? er.message : "Failed"); setBusy(null); }
  }
  return (
    <Panel title="Your workspaces" badge={<span className="text-xs text-muted">Work saved in one workspace is invisible from the others</span>}>
      {err && <div className="mb-3"><ErrorPanel message={err} /></div>}
      {list === null && !err ? <p className="text-sm text-muted" aria-busy="true">Loading…</p> : (
        <ul className="divide-y divide-line">
          {list?.map((w) => (
            <li key={w.id} className="flex flex-wrap items-center gap-3 py-2.5">
              <div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold">{w.name}</div><div className="text-[11px] text-muted">{w.role} · created {dt(w.created_at)}</div></div>
              {w.id === current ? <Badge tone="green">Current</Badge> : (
                <button type="button" onClick={() => switchTo(w.id)} disabled={busy !== null} className="rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:border-violet/60 disabled:opacity-60">{busy === w.id ? "Switching…" : "Switch to this"}</button>)}
            </li>))}
        </ul>)}
      <form onSubmit={create} className="mt-4 flex flex-wrap items-end gap-2">
        <div className="min-w-48 flex-1"><label htmlFor="new-ws" className="mb-1 block text-xs text-muted">Create a new workspace</label><input id="new-ws" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder="e.g. Q3 pricing study" className={`${field} w-full`} /></div>
        <button type="submit" disabled={busy !== null || !name.trim()} className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy === "new" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Plus className="h-4 w-4" aria-hidden="true" />} Create</button>
      </form>
    </Panel>
  );
}

function Library({ canWrite }: { canWrite: boolean }) {
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [items, setItems] = useState<LibraryItem[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      const qs = new URLSearchParams(); if (q.trim()) qs.set("q", q.trim()); if (type) qs.set("type", type);
      call<{ items: LibraryItem[] }>(`library/items?${qs}`).then((d) => { if (live) { setItems(d.items); setErr(null); } }).catch((e) => live && setErr(e.message));
    }, 250);
    return () => { live = false; clearTimeout(t); };
  }, [q, type]);
  return (
    <Panel title="Library" badge={<a href="/app-api/library/export" download className="inline-flex items-center gap-1 rounded-lg border border-line px-3 py-1.5 text-xs font-semibold hover:border-violet/60"><Download className="h-3.5 w-3.5" aria-hidden="true" /> Export whole workspace (JSON)</a>}>
      <p className="mb-3 text-xs text-muted">Everything saved in this workspace: forecasts, scenarios and simulation runs. Open the assistant on any item for a plain-language explanation and a printable report.</p>
      <div className="mb-3 flex flex-wrap gap-2">
        <div className="min-w-48 flex-1"><label htmlFor="lib-q" className="sr-only">Search the library</label><input id="lib-q" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by title…" className={`${field} w-full`} /></div>
        <div><label htmlFor="lib-type" className="sr-only">Type</label><select id="lib-type" value={type} onChange={(e) => setType(e.target.value)} className={field}><option value="">All types</option><option value="prediction">Forecasts</option><option value="scenario">Scenarios</option><option value="simulation">Simulation runs</option></select></div>
      </div>
      {err ? <ErrorPanel message={err} /> : items === null ? <p className="text-sm text-muted" aria-busy="true">Loading…</p> : items.length === 0 ? <Empty>{q || type ? "Nothing matches." : "Nothing saved yet. Build something in one of the modules and save it."}</Empty> : (
        <ul className="divide-y divide-line">
          {items.map((it) => {
            const m = MODULE[it.module] ?? { label: it.module, href: "/dashboard" };
            return (
              <li key={`${it.type}:${it.id}`} className="flex flex-wrap items-center gap-3 py-2.5">
                <Badge tone="violet">{m.label}</Badge>
                <div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold">{it.title}</div><div className="text-[11px] text-muted">{KIND[it.kind] ?? it.kind} · {it.created_by_name} · {dt(it.created_at)}{it.type === "simulation" && ` · ${it.status}`}</div></div>
                <Link href={m.href} className="text-xs text-violet underline">Open module</Link>
                {(it.type !== "simulation" || it.status === "completed") && <ExplainToggle type={it.type} id={it.id} title={it.title} />}
                <CommentsToggle type={it.type} id={it.id} canWrite={canWrite} />
              </li>);
          })}
        </ul>)}
    </Panel>
  );
}

export function LibraryClient({ role }: { role: string }) {
  return <div className="mt-4 space-y-4"><Workspaces /><Library canWrite={role !== "viewer"} /></div>;
}
