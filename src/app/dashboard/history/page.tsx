import type { Metadata } from "next";
import { requireSession } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import type { PredictionRow } from "@/lib/types";
import { Badge, Empty, ErrorPanel, PageTitle, dt, pct } from "@/components/dashboard/ui";

export const metadata: Metadata = { title: "Prediction History" };

export default async function Page() {
  const s = await requireSession();
  let rows: PredictionRow[];
  try {
    rows = (await apiFetch<{ predictions: PredictionRow[] }>(s, "sports/predictions?limit=100")).predictions;
  } catch (e) {
    return (<><PageTitle title="Prediction History" /><ErrorPanel message={e instanceof Error ? e.message : "Unavailable"} /></>);
  }
  return (
    <>
      <PageTitle title="Prediction History" sub="Saved forecasts are immutable records: each keeps its model version, feature cutoff and assumptions exactly as produced." />
      {rows.length === 0 ? <Empty>No saved forecasts yet.</Empty> : (
        <ul className="space-y-3">
          {rows.map((p) => (
            <li key={p.id}>
              <details className="glass rounded-2xl p-4">
                <summary className="flex cursor-pointer flex-wrap items-center justify-between gap-2">
                  <span className="font-semibold">{p.inputs.home_name} vs {p.inputs.away_name}</span>
                  <span className="flex items-center gap-2 text-xs text-muted">
                    {p.inputs.retrospective && <Badge tone="amber">Retrospective</Badge>}
                    {dt(p.created_at)}
                  </span>
                </summary>
                <div className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
                  <dl className="space-y-1">
                    <div className="flex justify-between"><dt className="text-muted">Home win</dt><dd className="font-mono">{pct(p.outputs.p_home)}</dd></div>
                    <div className="flex justify-between"><dt className="text-muted">Draw</dt><dd className="font-mono">{pct(p.outputs.p_draw)}</dd></div>
                    <div className="flex justify-between"><dt className="text-muted">Away win</dt><dd className="font-mono">{pct(p.outputs.p_away)}</dd></div>
                    <div className="flex justify-between"><dt className="text-muted">Expected goals</dt><dd className="font-mono">{p.outputs.home_xg.toFixed(2)} – {p.outputs.away_xg.toFixed(2)}</dd></div>
                  </dl>
                  <dl className="space-y-1 text-xs">
                    <div className="flex justify-between gap-3"><dt className="text-muted">Model</dt><dd className="font-mono">{p.model_name}@{p.model_version}</dd></div>
                    <div className="flex justify-between gap-3"><dt className="text-muted">Feature cutoff</dt><dd className="font-mono">{dt(p.feature_cutoff)}</dd></div>
                    <div className="flex justify-between gap-3"><dt className="text-muted">Matches used</dt><dd className="font-mono">{p.inputs.matches_used}</dd></div>
                    <div className="flex justify-between gap-3"><dt className="text-muted">Dataset</dt><dd className="font-mono">{p.inputs.dataset}</dd></div>
                    <div className="flex justify-between gap-3"><dt className="text-muted">Record id</dt><dd className="truncate font-mono">{p.id}</dd></div>
                  </dl>
                </div>
              </details>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
