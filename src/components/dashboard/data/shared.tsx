"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { call } from "@/lib/client";
import { field } from "../analysis";

export type DataKind = "sports_results" | "football_stats" | "market_returns" | "political_seats" | "series";

export const KIND_LABEL: Record<DataKind, string> = {
  sports_results: "Football match results",
  football_stats: "Football advanced statistics",
  market_returns: "Market prices / returns",
  political_seats: "Party seats",
  series: "Numeric series",
};

export interface DatasetRow {
  id: string;
  kind: DataKind;
  name: string;
  description: string | null;
  row_count: number;
  summary: Record<string, unknown> & {
    team_matches?: Record<string, number>;
    assets?: string[];
    columns?: Record<string, unknown>;
    periods_per_year?: number | null;
  };
  sha256: string;
  created_at: string;
  created_by_name: string | null;
}

/** Loads the workspace's datasets (optionally of some kinds). `null` while loading. */
export function useDatasets(kinds?: DataKind[], reload = 0) {
  const [list, setList] = useState<DatasetRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const key = (kinds ?? []).join(",");
  useEffect(() => {
    let live = true;
    call<{ datasets: DatasetRow[] }>("data/datasets").then(
      (d) => {
        if (!live) return;
        setList(key ? d.datasets.filter((x) => key.split(",").includes(x.kind)) : d.datasets);
        setError(null);
      },
      (e) => live && setError(e instanceof Error ? e.message : "Could not load datasets."),
    );
    return () => {
      live = false;
    };
  }, [key, reload]);
  return { list, error };
}

/** "Load from a dataset" control: pick one of the workspace's datasets of a kind and hand its id to the caller. */
export function DatasetPicker({ kind, label, onPick, id }: { kind: DataKind; label: string; onPick: (d: DatasetRow) => Promise<void> | void; id: string }) {
  const { list, error } = useDatasets([kind]);
  const [sel, setSel] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (error) return <p role="alert" className="text-xs text-red-300">{error}</p>;
  if (!list) return null;
  if (list.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-line px-3 py-2 text-xs text-muted">
        Have your own {KIND_LABEL[kind].toLowerCase()}? Upload a CSV on the <Link href="/dashboard/data" className="text-violet underline">Data page</Link> and use it here.
      </p>
    );
  }
  const chosen = list.find((d) => d.id === sel);
  return (
    <div className="flex flex-wrap items-end gap-2 rounded-lg border border-line bg-bg/40 p-3">
      <div className="min-w-48 flex-1">
        <label htmlFor={id} className="mb-1 block text-xs text-muted">{label}</label>
        <select id={id} value={sel} onChange={(e) => setSel(e.target.value)} className={`${field} w-full`}>
          <option value="">Choose a dataset…</option>
          {list.map((d) => <option key={d.id} value={d.id}>{d.name} · {d.row_count.toLocaleString()} rows</option>)}
        </select>
      </div>
      <button
        type="button"
        disabled={!chosen || busy}
        onClick={async () => {
          if (!chosen) return;
          setBusy(true);
          setErr(null);
          try {
            await onPick(chosen);
          } catch (e) {
            setErr(e instanceof Error ? e.message : "Could not load the dataset.");
          } finally {
            setBusy(false);
          }
        }}
        className="rounded-lg border border-violet/60 px-3 py-2 text-xs font-semibold text-violet hover:bg-violet/10 disabled:opacity-50"
      >
        {busy ? "Loading…" : "Use this data"}
      </button>
      {err && <p role="alert" className="w-full text-xs text-red-300">{err}</p>}
    </div>
  );
}
