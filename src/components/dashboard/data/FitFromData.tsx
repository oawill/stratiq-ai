"use client";

import { useState } from "react";
import { post } from "@/lib/client";
import { field } from "../analysis";
import { useDatasets } from "./shared";

export interface FittedDist { dist: Record<string, number | string>; chosen: string; reason: string; note: string; stats: { n: number; mean: number; sd: number }; dataset: { name: string; sha256: string }; column: string }

/** Fits a probability distribution to one column of an uploaded series, for a SimLab input variable. */
export function FitFromData({ idPrefix, onFit }: { idPrefix: string; onFit: (f: FittedDist) => void }) {
  const { list } = useDatasets(["series", "market_returns"]);
  const [open, setOpen] = useState(false);
  const [dsId, setDsId] = useState("");
  const [col, setCol] = useState("");
  const [kind, setKind] = useState("auto");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  if (!list || list.length === 0) return null;
  const ds = list.find((d) => d.id === dsId);
  const cols = ds ? (ds.kind === "series" ? Object.keys(ds.summary.columns ?? {}) : ds.summary.assets ?? []) : [];

  async function fit() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await post<FittedDist>(`data/datasets/${dsId}/fit`, { column: col, distribution: kind });
      onFit(r);
      setMsg({ ok: true, text: `Fitted ${r.chosen} to ${r.stats.n} observations of “${r.column}” (mean ${r.stats.mean.toPrecision(4)}, sd ${r.stats.sd.toPrecision(4)}): ${r.reason}. ${r.note}` });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "Could not fit." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-2">
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="text-[11px] text-violet underline">{open ? "Hide data fitting" : "Fit to my data"}</button>
      {open && (
        <div className="mt-2 flex flex-wrap items-end gap-2 rounded-lg border border-line bg-bg/40 p-2">
          <div><label htmlFor={`${idPrefix}-ds`} className="mb-1 block text-[11px] text-muted">Dataset</label>
            <select id={`${idPrefix}-ds`} value={dsId} onChange={(e) => { setDsId(e.target.value); setCol(""); }} className={field}><option value="">Choose…</option>{list.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></div>
          <div><label htmlFor={`${idPrefix}-col`} className="mb-1 block text-[11px] text-muted">Column</label>
            <select id={`${idPrefix}-col`} value={col} disabled={!ds} onChange={(e) => setCol(e.target.value)} className={field}><option value="">Choose…</option>{cols.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
          <div><label htmlFor={`${idPrefix}-kind`} className="mb-1 block text-[11px] text-muted">Shape</label>
            <select id={`${idPrefix}-kind`} value={kind} onChange={(e) => setKind(e.target.value)} className={field}>
              <option value="auto">Choose for me</option><option value="normal">Normal</option><option value="lognormal">Lognormal</option><option value="triangular">Triangular</option></select></div>
          <button type="button" disabled={!ds || !col || busy} onClick={fit} className="rounded-lg border border-violet/60 px-3 py-2 text-xs font-semibold text-violet hover:bg-violet/10 disabled:opacity-50">{busy ? "Fitting…" : "Fit"}</button>
          {msg && <p role={msg.ok ? "status" : "alert"} className={`w-full text-[11px] leading-relaxed ${msg.ok ? "text-muted" : "text-red-300"}`}>{msg.text}</p>}
        </div>
      )}
    </div>
  );
}
