"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Download, Trash2 } from "lucide-react";
import { call } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel, dt } from "../ui";
import { field } from "../analysis";
import { DOMAIN_LABELS } from "../control/ControlCenter";

interface Item { type: string; id: string; title: string; created_at: string; domain: string | null; owner: string | null; can_delete: boolean; href: string; delete_path: string | null; export_path: string | null; note: string | null }
interface Lib { items: Item[]; total: number; counts: Record<string, number>; note: string }
const TYPES: [string, string][] = [["prediction", "Predictions"], ["forecast", "Football forecasts"], ["simulation", "Simulations"], ["scenario", "Scenarios"], ["conversation", "Analyst conversations"], ["briefing", "Briefings"]];
const LABEL = Object.fromEntries(TYPES);
const PAGE = 15;

/** One searchable list of everything saved. Conversations and briefings are only the signed-in person's; permanent forecast records cannot be deleted. */
export function LibraryClient() {
  const [lib, setLib] = useState<Lib | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [sort, setSort] = useState("newest");
  const [offset, setOffset] = useState(0);

  const load = useCallback(() => {
    const qs = new URLSearchParams({ limit: String(PAGE), offset: String(offset), sort });
    if (type) qs.set("types", type);
    if (q.trim()) qs.set("q", q.trim());
    return call<Lib>(`saved-intelligence?${qs}`).then((x) => { setLib(x); setErr(null); }, (e) => setErr(e instanceof Error ? e.message : "Could not load your library."));
  }, [q, type, sort, offset]);
  useEffect(() => { const t = setTimeout(load, q ? 250 : 0); return () => clearTimeout(t); }, [load, q]);

  async function remove(it: Item) {
    if (!it.delete_path || !window.confirm(`Delete "${it.title}"? This cannot be undone.`)) return;
    setErr(null);
    try { await call(it.delete_path, { method: "DELETE" }); await load(); } catch (e) { setErr(e instanceof Error ? e.message : "Could not delete."); }
  }

  if (!lib) return err ? <ErrorPanel message={err} /> : <p className="text-sm text-muted" aria-busy="true">Loading your library…</p>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3" role="search" aria-label="Filter saved intelligence">
        <div><label htmlFor="lib-q" className="mb-1 block text-xs text-muted">Search titles</label><input id="lib-q" type="search" value={q} maxLength={80} onChange={(e) => { setQ(e.target.value); setOffset(0); }} className={`${field} w-56`} /></div>
        <div><label htmlFor="lib-t" className="mb-1 block text-xs text-muted">Type</label>
          <select id="lib-t" value={type} onChange={(e) => { setType(e.target.value); setOffset(0); }} className={field}><option value="">All types</option>{TYPES.map(([id, label]) => <option key={id} value={id}>{label} ({lib.counts[id] ?? 0})</option>)}</select></div>
        <div><label htmlFor="lib-s" className="mb-1 block text-xs text-muted">Sort</label>
          <select id="lib-s" value={sort} onChange={(e) => { setSort(e.target.value); setOffset(0); }} className={field}><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="title">Title</option></select></div>
      </div>
      {err && <p role="alert" className="text-sm text-red-300">{err}</p>}
      <Panel title="Saved intelligence" badge={<Badge tone="muted">{lib.total} item{lib.total === 1 ? "" : "s"}</Badge>}>
        {lib.items.length === 0 ? <Empty>{q || type ? "Nothing matches those filters." : "Nothing is saved yet. Forecasts, simulations, scenarios, Analyst conversations and briefings you save will appear here."}</Empty> : (
          <ul className="divide-y divide-line" aria-label="Saved intelligence">
            {lib.items.map((it) => (
              <li key={it.type + it.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
                <div className="min-w-0 flex-1">
                  <Link href={it.href} className="font-medium hover:text-violet">{it.title}</Link>
                  <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted"><Badge tone="violet">{LABEL[it.type] ?? it.type}</Badge>{it.domain && <Badge tone="muted">{DOMAIN_LABELS[it.domain] ?? it.domain}</Badge>}{dt(it.created_at)}{it.owner && ` · ${it.owner}`}{it.note && ` · ${it.note}`}</div>
                </div>
                {it.export_path && <a href={`/app-api/${it.export_path}`} aria-label={`Export ${it.title}`} className="rounded-lg p-1.5 text-muted hover:text-ink"><Download className="h-4 w-4" aria-hidden="true" /></a>}
                {it.can_delete && <button type="button" onClick={() => remove(it)} aria-label={`Delete ${it.title}`} className="rounded-lg p-1.5 text-muted hover:text-red-300"><Trash2 className="h-4 w-4" aria-hidden="true" /></button>}
              </li>
            ))}
          </ul>
        )}
        {lib.total > PAGE && (
          <div className="mt-3 flex items-center justify-between text-sm">
            <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))} className="rounded-lg border border-line px-3 py-1.5 disabled:opacity-40">Previous</button>
            <span className="text-xs text-muted">{offset + 1}–{Math.min(offset + PAGE, lib.total)} of {lib.total}</span>
            <button type="button" disabled={offset + PAGE >= lib.total} onClick={() => setOffset(offset + PAGE)} className="rounded-lg border border-line px-3 py-1.5 disabled:opacity-40">Next</button>
          </div>
        )}
        <p className="mt-3 text-[11px] text-muted">{lib.note}</p>
      </Panel>
    </div>
  );
}
