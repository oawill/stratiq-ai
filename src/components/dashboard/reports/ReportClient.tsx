"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Download, Printer } from "lucide-react";
import { call } from "@/lib/client";
import { evidenceToMarkdown, type Evidence, type MetricRow } from "@/lib/report";
import { Badge, Empty, ErrorPanel, Panel, Stat, dt, pct } from "../ui";

const f3 = (v: number | null) => (v === null ? "n/a" : v.toFixed(3));

function MetricTable({ rows, caption }: { rows: MetricRow[]; caption: string }) {
  if (rows.length === 0) return <p className="text-sm text-muted">No results recorded.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead><tr className="text-left text-[11px] text-muted">{["Model", "Matches", "Log loss", "Brier", "Right result", "Calibration gap", "Gain over frequency baseline"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
        <tbody className="font-mono">{rows.map((r) => (
          <tr key={r.model} className="border-t border-line"><th scope="row" className="py-1.5 pr-3 text-left font-sans font-medium">{r.model}</th><td className="pr-3">{r.matches}</td><td className="pr-3">{f3(r.log_loss)}</td><td className="pr-3">{f3(r.brier)}</td>
            <td className="pr-3">{r.accuracy === null ? "n/a" : pct(r.accuracy)}</td><td className="pr-3">{r.calibration_gap === null ? "n/a" : `${(r.calibration_gap * 100).toFixed(1)} pts`}</td>
            <td className="text-xs">{r.gain_vs_frequency === null ? "n/a" : `${r.gain_vs_frequency >= 0 ? "+" : ""}${f3(r.gain_vs_frequency)} ± ${f3(r.gain_standard_error)}${r.gain_clear ? " (clear)" : ""}`}</td></tr>
        ))}</tbody>
      </table>
    </div>
  );
}

/** The evidence report: provenance, historical evaluation and tracked forecasts in three separate sections, straight from stored records. */
export function ReportClient() {
  const [e, setE] = useState<Evidence | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => call<Evidence>("reports/evidence").then((d) => { setE(d); setErr(null); }, (x) => setErr(x instanceof Error ? x.message : "Could not build the report.")), []);
  useEffect(() => { const t = setTimeout(load, 0); return () => clearTimeout(t); }, [load]);

  if (err) return <ErrorPanel message={err} />;
  if (!e) return <p className="text-sm text-muted" aria-busy="true">Building the report from your stored records…</p>;
  const c = e.historical_evaluation.chronological;
  const rolling = e.historical_evaluation.rolling;
  const download = () => {
    const url = URL.createObjectURL(new Blob([evidenceToMarkdown(e)], { type: "text/markdown" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `evidence-report-${e.generated_at.slice(0, 10)}.md` });
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="space-y-4 print:space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 print:hidden">
        <p className="text-xs text-muted">Generated {dt(e.generated_at)}. Every figure below is read from stored records; nothing is estimated for the report.</p>
        <div className="flex gap-2">
          <button type="button" onClick={download} className="inline-flex items-center gap-2 rounded-xl border border-violet/60 px-3 py-2 text-sm font-semibold text-violet hover:bg-violet/10"><Download className="h-4 w-4" aria-hidden="true" /> Download Markdown</button>
          <button type="button" onClick={() => window.print()} className="inline-flex items-center gap-2 rounded-xl border border-line px-3 py-2 text-sm font-semibold text-muted hover:text-ink"><Printer className="h-4 w-4" aria-hidden="true" /> Print</button>
        </div>
      </div>

      <Panel title="1. Data and provenance" badge={<Badge tone="muted">Where it came from</Badge>}>
        {e.data.matches === 0 ? <Empty>No match history has been imported. <Link href="/dashboard/data" className="text-violet underline">Import Premier League results</Link> to begin.</Empty> : (
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-4">
              <Stat label="Matches" value={e.data.matches.toLocaleString()} />
              <Stat label="Seasons" value={`${e.data.seasons.length}`} hint={`${e.data.seasons[0]} to ${e.data.seasons[e.data.seasons.length - 1]}`} />
              <Stat label="First match" value={e.data.first ?? "n/a"} />
              <Stat label="Last match" value={e.data.last ?? "n/a"} />
            </div>
            <p className="break-all font-mono text-xs text-muted">SHA-256 of the stored matches: {e.data.data_sha256}</p>
          </div>
        )}
        {e.data.sources.length > 0 && (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm"><caption className="sr-only">Data sources</caption>
              <thead><tr className="text-left text-[11px] text-muted">{["Source", "Kind", "Provider", "Reference", "Added"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
              <tbody>{e.data.sources.map((s, i) => <tr key={i} className="border-t border-line"><th scope="row" className="py-1.5 pr-3 text-left font-medium">{s.name}</th><td className="pr-3">{s.kind}</td><td className="pr-3">{s.provider}</td><td className="pr-3 font-mono text-xs">{s.reference ?? "n/a"}</td><td>{dt(s.created_at)}</td></tr>)}</tbody>
            </table>
            <p className="mt-2 text-xs text-muted">{e.data.sources[0].licence_note}</p>
          </div>
        )}
        {e.data.uploads.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-muted">{e.data.uploads.map((u) => <li key={u.sha256 + u.created_at}>{u.name}: {u.kind}, {u.row_count.toLocaleString()} rows, {dt(u.created_at)}</li>)}</ul>}
      </Panel>

      <Panel title="2. Historical evaluation" badge={<Badge tone="muted">Backtests on past matches</Badge>}>
        {!c ? <Empty>No chronological backtest has been run, so there are no accuracy figures to report. Run one in Sports, Football intelligence, Model performance.</Empty> : (
          <div className="space-y-4">
            <p className="text-xs leading-relaxed text-muted">Run {dt(c.created_at)} on {c.matches.toLocaleString()} matches{c.model_version ? `, model version ${c.model_version}` : ""}.{c.split && ` Training ${c.split.training?.[0]} to ${c.split.training?.slice(-1)[0]}; validation ${c.split.validation?.join(", ")}; test ${c.split.test?.join(", ")}.`}</p>
            {c.history_changed_since && <p role="alert" className="rounded-xl border border-amber-300/40 bg-amber-300/10 p-3 text-sm text-amber-200">The imported history has changed since this run. Re-run the backtest before relying on these figures.</p>}
            <div><h3 className="mb-2 text-sm font-semibold">Test period (never used to choose settings)</h3><MetricTable rows={c.test} caption="Test period results by model" /></div>
            <div><h3 className="mb-2 text-sm font-semibold">Validation period (used to choose settings)</h3><MetricTable rows={c.validation} caption="Validation period results by model" /></div>
            {c.versions.length > 0 && <p className="text-xs text-muted">Model versions: {c.versions.map((v) => `${v.name}@${v.version}${v.trained_through ? ` (trained through ${v.trained_through})` : ""}`).join(", ")}.</p>}
            {c.warnings.length > 0 && <ul className="list-disc space-y-1 pl-5 text-xs text-muted">{c.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
          </div>
        )}
        {rolling && <div className="mt-4"><h3 className="mb-2 text-sm font-semibold">Rolling-origin backtest ({dt(rolling.created_at)})</h3><MetricTable rows={rolling.results} caption="Rolling-origin results by model" /></div>}
      </Panel>

      <Panel title="3. Forecasts" badge={<Badge tone="amber">Made before the match, scored after</Badge>}>
        <p className="text-xs text-muted">{e.forecasts.note}</p>
        {e.forecasts.scored.length === 0 ? <p className="mt-2 text-sm">No tracked forecast has been scored yet. {e.forecasts.waiting_for_results} are waiting for results.</p> : (
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-sm"><caption className="sr-only">Scored tracked forecasts by model</caption>
              <thead><tr className="text-left text-[11px] text-muted">{["Model", "Version", "Scored", "Log loss", "Brier", "Right result", "Fixtures"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
              <tbody className="font-mono">{e.forecasts.scored.map((s) => <tr key={s.model + s.version} className="border-t border-line"><th scope="row" className="py-1.5 pr-3 text-left font-sans font-medium">{s.model}</th><td className="pr-3">{s.version}</td><td className="pr-3">{s.n}</td><td className="pr-3">{f3(s.log_loss)}</td><td className="pr-3">{f3(s.brier)}</td><td className="pr-3">{pct(s.accuracy)}</td><td className="text-xs">{s.first} to {s.last}</td></tr>)}</tbody>
            </table>
            <p className="mt-2 text-xs text-muted">{e.forecasts.waiting_for_results} more are waiting for results.</p>
          </div>
        )}
      </Panel>

      <Panel title="4. Saved work">
        <p className="text-sm">{e.saved_work.predictions} saved forecasts · {e.saved_work.scenarios} saved scenarios · {e.saved_work.simulations} simulation runs. <Link href="/dashboard/workspace" className="text-violet underline print:hidden">Open the library</Link></p>
      </Panel>
      <ul className="list-disc space-y-1 pl-5 text-xs text-muted">{e.statements.map((s) => <li key={s}>{s}</li>)}</ul>
    </div>
  );
}
