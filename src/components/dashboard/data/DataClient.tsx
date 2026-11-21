"use client";

import { useState } from "react";
import { Loader2, Trash2, Upload } from "lucide-react";
import { call, post } from "@/lib/client";
import { Badge, Empty, ErrorPanel, Panel, dt } from "../ui";
import { field } from "../analysis";
import { KIND_LABEL, useDatasets, type DataKind, type DatasetRow } from "./shared";

const FORMAT: Record<DataKind, { columns: string; example: string; note: string }> = {
  sports_results: {
    columns: "date, home_team, away_team, home_goals, away_goals (football-data.co.uk files work as they are: Date, HomeTeam, AwayTeam, FTHG, FTAG; other columns are ignored)",
    example: "2024-01-06,Ash,Birch,2,1",
    note: "Played matches only (dates as YYYY-MM-DD or day-first DD/MM/YYYY, whole-number goals). At least 30 matches and 4 teams. Team ratings are fitted on these results.",
  },
  market_returns: {
    columns: "date (optional), then one column per asset",
    example: "2024-01-31,1.2,-0.4",
    note: "Per-period returns or prices, oldest first, up to 10 assets and at least 20 observations. Prices are converted to simple returns.",
  },
  political_seats: {
    columns: "party, seats, position (optional)",
    example: "Alpha,40,1",
    note: "Two to twelve parties with whole-number seat counts. Position is an optional left-right score for ordering.",
  },
  series: {
    columns: "date (optional), then one column per variable",
    example: "2024-01-31,102.5,11.2",
    note: "At least 20 numeric observations per column. Use a series to fit a probability distribution for a SimLab variable.",
  },
};

interface Preview { ok: boolean; errors?: string[]; row_count?: number; summary?: Record<string, unknown>; warnings?: string[]; sha256?: string }

function summaryLine(d: DatasetRow): string {
  const s = d.summary as Record<string, unknown>;
  if (d.kind === "sports_results") return `${s.matches} matches · ${s.teams} teams · ${s.first_date} to ${s.last_date}`;
  if (d.kind === "market_returns") return `${s.observations} observations · ${(s.assets as string[]).join(", ")}${s.first_date ? ` · ${s.first_date} to ${s.last_date}` : ""}`;
  if (d.kind === "political_seats") return `${s.parties} parties · ${s.total_seats} seats`;
  return `${s.observations} observations · ${Object.keys(s.columns as object).join(", ")}`;
}

function PreviewSummary({ kind, p }: { kind: DataKind; p: Preview }) {
  const s = (p.summary ?? {}) as Record<string, unknown>;
  const rows: [string, string][] = [["Rows", String(p.row_count)]];
  if (kind === "sports_results") rows.push(["Teams", String(s.teams)], ["Dates", `${s.first_date} to ${s.last_date}`], ["Goals per match", String(s.mean_goals_per_match)]);
  if (kind === "market_returns") rows.push(["Assets", (s.assets as string[]).join(", ")], ["Frequency", s.periods_per_year ? `${s.periods_per_year} periods per year` : "unknown (no dates)"]);
  if (kind === "political_seats") rows.push(["Parties", String(s.parties)], ["Total seats", String(s.total_seats)]);
  if (kind === "series") rows.push(["Columns", Object.keys(s.columns as object).join(", ")]);
  return (
    <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
      {rows.map(([k, v]) => <div key={k} className="flex gap-2"><dt className="text-muted">{k}</dt><dd className="font-medium">{v}</dd></div>)}
    </dl>
  );
}

function UploadPanel({ onSaved }: { onSaved: () => void }) {
  const [kind, setKind] = useState<DataKind>("sports_results");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [csv, setCsv] = useState("");
  const [fileName, setFileName] = useState("");
  const [values, setValues] = useState<"returns" | "prices">("returns");
  const [unit, setUnit] = useState<"percent" | "decimal">("percent");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState<"preview" | "save" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const options = kind === "market_returns" ? { values, unit } : {};

  const reset = () => { setPreview(null); setDone(null); setErr(null); };

  async function onFile(f: File | undefined) {
    reset();
    if (!f) return;
    if (f.size > 2_000_000) { setErr("That file is larger than 2 MB. Remove columns or split it."); return; }
    setFileName(f.name);
    setCsv(await f.text());
    if (!name) setName(f.name.replace(/\.[^.]+$/, "").slice(0, 120));
  }

  async function run(mode: "preview" | "save") {
    setBusy(mode); setErr(null); setDone(null);
    try {
      if (mode === "preview") {
        setPreview(await post<Preview>("data/preview", { kind, csv, options }));
      } else {
        const r = await post<{ name: string; row_count: number }>("data/datasets", { kind, name, description: description || null, csv, options });
        setDone(`Saved “${r.name}” (${r.row_count.toLocaleString()} rows).`);
        setPreview(null); setCsv(""); setFileName(""); setName(""); setDescription("");
        onSaved();
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(null);
    }
  }

  const f = FORMAT[kind];
  return (
    <Panel title="Upload a dataset" badge={<Badge tone="muted">Private to this workspace</Badge>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="ds-kind" className="mb-1 block text-xs text-muted">What is it?</label>
          <select id="ds-kind" value={kind} onChange={(e) => { setKind(e.target.value as DataKind); reset(); }} className={`${field} w-full`}>
            {(Object.keys(KIND_LABEL) as DataKind[]).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="ds-name" className="mb-1 block text-xs text-muted">Name</label>
          <input id="ds-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} className={`${field} w-full`} placeholder="e.g. Premier season 2023/24" />
        </div>
      </div>
      <div role="note" className="mt-3 rounded-lg border border-line bg-bg/60 p-3 text-xs leading-relaxed text-muted">
        <p><strong className="text-ink">Columns:</strong> {f.columns}. Example row: <code className="font-mono">{f.example}</code></p>
        <p className="mt-1">{f.note} The first row must be column names. Files are checked line by line; nothing is guessed or filled in. Only upload data you are allowed to use.</p>
      </div>
      {kind === "market_returns" && (
        <div className="mt-3 flex flex-wrap gap-3">
          <div>
            <label htmlFor="ds-values" className="mb-1 block text-xs text-muted">The numbers are</label>
            <select id="ds-values" value={values} onChange={(e) => { setValues(e.target.value as typeof values); setPreview(null); }} className={field}>
              <option value="returns">Returns per period</option><option value="prices">Prices (convert to returns)</option>
            </select>
          </div>
          {values === "returns" && (
            <div>
              <label htmlFor="ds-unit" className="mb-1 block text-xs text-muted">Returns are written as</label>
              <select id="ds-unit" value={unit} onChange={(e) => { setUnit(e.target.value as typeof unit); setPreview(null); }} className={field}>
                <option value="percent">Percent (1.2 means 1.2%)</option><option value="decimal">Decimal (0.012 means 1.2%)</option>
              </select>
            </div>
          )}
        </div>
      )}
      <div className="mt-3">
        <label htmlFor="ds-file" className="mb-1 block text-xs text-muted">CSV file (up to 2 MB, 20,000 rows)</label>
        <input id="ds-file" type="file" accept=".csv,.tsv,.txt,text/csv,text/plain" onChange={(e) => onFile(e.target.files?.[0])} className="block w-full text-sm file:mr-3 file:rounded-lg file:border file:border-line file:bg-white/5 file:px-3 file:py-1.5 file:text-xs file:font-semibold" />
        {fileName && <p className="mt-1 text-xs text-muted">{fileName} · {csv.length.toLocaleString()} characters</p>}
      </div>
      <div className="mt-3">
        <label htmlFor="ds-desc" className="mb-1 block text-xs text-muted">Source or notes (optional)</label>
        <input id="ds-desc" value={description} maxLength={500} onChange={(e) => setDescription(e.target.value)} className={`${field} w-full`} placeholder="Where the data came from and any licence terms" />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" disabled={!csv || busy !== null} onClick={() => run("preview")} className="inline-flex items-center gap-1.5 rounded-xl border border-violet/60 px-4 py-2 text-sm font-semibold text-violet hover:bg-violet/10 disabled:opacity-50">
          {busy === "preview" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />} Check the file
        </button>
        <button type="button" disabled={!csv || !name.trim() || busy !== null || preview?.ok === false} onClick={() => run("save")} className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
          {busy === "save" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Upload className="h-4 w-4" aria-hidden="true" />} Save dataset
        </button>
      </div>
      {err && <p role="alert" className="mt-3 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">{err}</p>}
      {done && <p role="status" className="mt-3 rounded-lg border border-success/40 bg-success/10 px-3 py-2 text-sm text-success">{done}</p>}
      {preview && !preview.ok && (
        <div role="alert" className="mt-3 rounded-lg border border-amber-400/40 bg-amber-400/10 p-3 text-sm text-amber-200">
          <p className="font-semibold">Fix these problems and check again:</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">{(preview.errors ?? []).map((m) => <li key={m}>{m}</li>)}</ul>
          {(preview.errors?.length ?? 0) >= 20 && <p className="mt-1 text-xs">Only the first 20 problems are shown.</p>}
        </div>
      )}
      {preview?.ok && (
        <div role="status" className="mt-3 rounded-lg border border-success/40 bg-success/5 p-3">
          <p className="mb-2 text-sm font-semibold text-success">The file is valid.</p>
          <PreviewSummary kind={kind} p={preview} />
          {(preview.warnings ?? []).length > 0 && <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-amber-200">{preview.warnings!.map((w) => <li key={w}>{w}</li>)}</ul>}
        </div>
      )}
    </Panel>
  );
}

export function DataClient() {
  const [tick, setTick] = useState(0);
  const { list, error } = useDatasets(undefined, tick);
  const [err, setErr] = useState<string | null>(null);

  async function remove(d: DatasetRow) {
    if (!confirm(`Delete “${d.name}”? Forecasts already saved from it keep their own record of the inputs.`)) return;
    setErr(null);
    try {
      await call(`data/datasets/${d.id}`, { method: "DELETE" });
      setTick((t) => t + 1);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not delete.");
    }
  }

  return (
    <div className="space-y-4">
      <UploadPanel onSaved={() => setTick((t) => t + 1)} />
      <Panel title="Your datasets">
        {err && <p role="alert" className="mb-2 text-sm text-red-300">{err}</p>}
        {error ? <ErrorPanel message={error} /> : list === null ? <p className="text-sm text-muted" aria-busy="true">Loading…</p> : list.length === 0 ? (
          <Empty>No datasets yet. Upload a CSV above, then use it in Sports, Markets, Politics or SimLab.</Empty>
        ) : (
          <ul className="divide-y divide-line" aria-label="Datasets">
            {list.map((d) => (
              <li key={d.id} className="flex flex-wrap items-center gap-3 py-3">
                <Badge tone="violet">{KIND_LABEL[d.kind]}</Badge>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold">{d.name}</div>
                  <div className="truncate text-xs text-muted">{summaryLine(d)}</div>
                  <div className="text-[11px] text-muted">{d.created_by_name} · {dt(d.created_at)} · fingerprint <span className="font-mono">{d.sha256.slice(0, 12)}</span></div>
                  {d.description && <div className="text-xs text-muted">{d.description}</div>}
                </div>
                <button type="button" onClick={() => remove(d)} aria-label={`Delete ${d.name}`} className="rounded-lg border border-line p-2 text-muted hover:border-red-400/60 hover:text-red-300"><Trash2 className="h-4 w-4" aria-hidden="true" /></button>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
