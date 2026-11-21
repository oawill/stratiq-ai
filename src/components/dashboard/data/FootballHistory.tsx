"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { call, post } from "@/lib/client";
import { Badge, ErrorPanel, Panel, Stat, dt, pct } from "../ui";
import { field } from "../analysis";

interface Check { name: string; ok: boolean; detail: string }
interface SeasonRow { season: string; status: "complete" | "incomplete" | "in_progress"; matches: number; clubs: number; checks: Check[]; missing_fixtures: string[]; missing_count: number }
interface Summary {
  total_matches: number; total_seasons: number; unique_clubs: number; clubs: string[]; earliest: string | null; latest: string | null;
  completed_seasons: string[]; incomplete_seasons: string[]; expected_seasons: string[]; not_imported: string[]; active_season: string;
  quality: "empty" | "good" | "needs_review"; seasons: SeasonRow[]; last_import: { created_at: string; status: string; filename: string | null } | null;
}
interface ImportReport {
  filename: string | null; dry_run: boolean; rows_read: number; valid: number; new: number; unchanged: number; rejected: number; rejected_rows: { line: number; reason: string }[];
  duplicates: number; conflicts: number; conflict_rows: { season: string; date: string; home: string; away: string; found: string[] }[]; unplayed_skipped: number;
  unknown_clubs: string[]; warnings: string[]; seasons: SeasonRow[]; missing: number; status?: string;
}
interface FileState { name: string; state: "waiting" | "working" | "done" | "failed"; message?: string; report?: ImportReport }
interface MatchRow { season: string; match_date: string; home_team: string; away_team: string; home_goals: number; away_goals: number }
interface Period { name: string; matches: number; first: string; last: string; scored?: number; log_loss?: number; baseline_log_loss?: number; brier?: number; baseline_brier?: number; accuracy?: number; baseline_accuracy?: number; log_loss_gain?: number; log_loss_gain_se?: number; gain_is_clear?: boolean; reliability?: { mean_predicted: number; observed: number; count: number }[] }
interface Evaluation { periods: Period[]; note: string; matches: number }
interface Fixture {
  as_of: string; matches_used: number; elo_difference: number; projection_note: string;
  home: Profile; away: Profile; head_to_head: { meetings: number; wins_a: number; wins_b: number; draws: number; recent: { date: string; home: string; away: string; score: string }[] };
  projection: { home_xg: number; away_xg: number; p_home: number; p_draw: number; p_away: number };
}
interface Profile { team: string; played: number; elo: number; win_rate?: number; goals_for_per_match?: number; goals_against_per_match?: number; clean_sheet_rate?: number; form_last_5: { results: string; points_per_match: number | null }; attack_strength?: number; defence_strength?: number }

const STATUS_TONE = { complete: "green", incomplete: "amber", in_progress: "muted" } as const;
const STATUS_LABEL = { complete: "Complete", incomplete: "Incomplete", in_progress: "In progress" } as const;
const QUALITY_LABEL = { empty: "Nothing imported", good: "Good", needs_review: "Needs review" } as const;
const btn = "inline-flex items-center gap-2 rounded-xl border border-violet/60 px-3 py-2 text-xs font-semibold text-violet hover:bg-violet/10 disabled:opacity-50";
const primary = "inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50";

function Spin({ on }: { on: boolean }) {
  return on ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null;
}

/** Historical Premier League results: import season files, check them, browse, export, and see what the model learns from them. */
export function FootballHistory() {
  const [sum, setSum] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [season, setSeason] = useState("all");
  const [files, setFiles] = useState<File[]>([]);
  const [combined, setCombined] = useState(false);
  const [checkOnly, setCheckOnly] = useState(false);
  const [progress, setProgress] = useState<FileState[]>([]);
  const [importing, setImporting] = useState(false);
  const [view, setView] = useState<"matches" | "report" | "tools" | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    call<Summary>("football/summary").then(
      (s) => { if (live) { setSum(s); setError(null); } },
      (e) => live && setError(e instanceof Error ? e.message : "Could not load match history."),
    );
    return () => { live = false; };
  }, [tick]);
  const refresh = useCallback(() => setTick((t) => t + 1), []);
  const seasonParam = season === "all" ? "" : `season=${encodeURIComponent(season)}`;

  async function runImport() {
    setImporting(true); setErr(null); setNote(null);
    const state: FileState[] = files.map((f) => ({ name: f.name, state: "waiting" }));
    setProgress([...state]);
    for (let i = 0; i < files.length; i++) {
      state[i] = { ...state[i], state: "working" };
      setProgress([...state]);
      try {
        if (files[i].size > 2_000_000) throw new Error("That file is larger than 2 MB. Split it into one file per season.");
        const report = await post<ImportReport>("football/import", { filename: files[i].name, csv: await files[i].text(), combined, dry_run: checkOnly });
        state[i] = { name: files[i].name, state: "done", report };
      } catch (e) {
        state[i] = { name: files[i].name, state: "failed", message: e instanceof Error ? e.message : "Import failed." };
      }
      setProgress([...state]);
    }
    setImporting(false);
    setFiles([]);
    if (!checkOnly) refresh();
  }

  async function download() {
    setBusy("download"); setErr(null);
    try {
      const x = await call<{ filename: string; csv: string; rows: number }>(`football/export${seasonParam ? `?${seasonParam}` : ""}`);
      const url = URL.createObjectURL(new Blob([x.csv], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url; a.download = x.filename; a.click();
      URL.revokeObjectURL(url);
      setNote(`Downloaded ${x.filename} (${x.rows.toLocaleString()} matches, five columns).`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not export.");
    } finally {
      setBusy(null);
    }
  }

  async function remove(s: string) {
    if (!window.confirm(`Remove all stored matches for ${s}? You can import the file again afterwards.`)) return;
    setErr(null);
    try {
      await call(`football/seasons?season=${encodeURIComponent(s)}`, { method: "DELETE" });
      setNote(`Removed ${s}.`);
      refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not remove the season.");
    }
  }

  if (error) return <section aria-labelledby="fh-title" className="mt-8"><h2 id="fh-title" className="sr-only">Historical Football Data</h2><ErrorPanel message={error} /></section>;
  const seasonOptions = sum ? Array.from(new Set([...sum.expected_seasons, ...sum.seasons.map((s) => s.season)])).sort() : [];

  return (
    <section aria-labelledby="fh-title" className="mt-8 space-y-4">
      <div>
        <h2 id="fh-title" className="font-display text-xl font-bold">Historical Football Data</h2>
        <p className="mt-1 text-sm text-muted">
          Import season results files for the English Premier League. Every row is checked, every season is tested for completeness, and the data stays private to this workspace.
          VELQORIN does not download data from any provider: you import files you are allowed to use, and a provider&apos;s own terms apply to them. For example, football-data.co.uk allows private use only, not commercial products.
        </p>
      </div>

      <Panel title="Your match history" badge={sum ? <Badge tone={sum.quality === "good" ? "green" : sum.quality === "needs_review" ? "amber" : "muted"}>Data quality: {QUALITY_LABEL[sum.quality]}</Badge> : undefined}>
        {!sum ? <p className="text-sm text-muted" aria-busy="true">Loading…</p> : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Matches imported" value={sum.total_matches.toLocaleString()} />
              <Stat label="Seasons" value={sum.total_seasons} />
              <Stat label="Unique clubs" value={sum.unique_clubs} />
              <Stat label="Completed seasons" value={`${sum.completed_seasons.length} of ${sum.expected_seasons.length}`} hint={sum.expected_seasons.length ? `${sum.expected_seasons[0]} to ${sum.expected_seasons[sum.expected_seasons.length - 1]}` : undefined} />
              <Stat label="Earliest match" value={sum.earliest ?? "—"} />
              <Stat label="Latest match" value={sum.latest ?? "—"} />
              <Stat label="Last import" value={sum.last_import ? dt(sum.last_import.created_at) : "Never"} hint={sum.last_import?.filename ?? undefined} />
              <Stat label="Season in progress" value={sum.active_season} hint="not part of the completeness checks" />
            </div>

            <div className="mt-4 flex flex-wrap items-end gap-3">
              <div>
                <label htmlFor="fh-comp" className="mb-1 block text-xs text-muted">Competition</label>
                <select id="fh-comp" className={field} defaultValue="EPL"><option value="EPL">English Premier League</option></select>
              </div>
              <div>
                <label htmlFor="fh-season" className="mb-1 block text-xs text-muted">Season</label>
                <select id="fh-season" value={season} onChange={(e) => setSeason(e.target.value)} className={field}>
                  <option value="all">All seasons</option>
                  {seasonOptions.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <button type="button" onClick={refresh} className={btn}>Refresh Data</button>
              <button type="button" onClick={download} disabled={busy !== null || sum.total_matches === 0} className={btn}><Spin on={busy === "download"} /> Download CSV</button>
              <button type="button" onClick={() => setView(view === "matches" ? null : "matches")} aria-pressed={view === "matches"} disabled={sum.total_matches === 0} className={btn}>View Matches</button>
              <button type="button" onClick={() => setView(view === "report" ? null : "report")} aria-pressed={view === "report"} className={btn}>Data Validation Report</button>
              <button type="button" onClick={() => setView(view === "tools" ? null : "tools")} aria-pressed={view === "tools"} disabled={sum.total_matches === 0} className={btn}>Use in forecasts</button>
            </div>
            {note && <p role="status" className="mt-3 text-sm text-success">{note}</p>}
            {err && <p role="alert" className="mt-3 text-sm text-red-300">{err}</p>}

            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="mb-1 text-left text-xs text-muted">Seasons and the result of their completeness checks</caption>
                <thead><tr className="text-left text-[11px] text-muted">{["Season", "Matches", "Clubs", "Status", ""].map((h) => <th key={h || "x"} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
                <tbody>
                  {sum.seasons.map((s) => (
                    <tr key={s.season} className="border-t border-line">
                      <th scope="row" className="py-1.5 pr-3 text-left font-medium">{s.season}</th>
                      <td className="pr-3 font-mono">{s.matches}</td>
                      <td className="pr-3 font-mono">{s.clubs}</td>
                      <td className="pr-3"><Badge tone={STATUS_TONE[s.status]}>{STATUS_LABEL[s.status]}</Badge>{s.status === "incomplete" && <span className="ml-2 text-xs text-muted">{s.checks.filter((c) => !c.ok).map((c) => c.name).join("; ")}</span>}</td>
                      <td><button type="button" onClick={() => remove(s.season)} className="text-xs text-muted underline hover:text-ink" aria-label={`Remove season ${s.season}`}>Remove</button></td>
                    </tr>
                  ))}
                  {sum.not_imported.map((s) => (
                    <tr key={s} className="border-t border-line text-muted"><th scope="row" className="py-1.5 pr-3 text-left font-normal">{s}</th><td className="pr-3">0</td><td className="pr-3">0</td><td className="pr-3" colSpan={2}>Not imported yet</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Panel>

      <Panel title="Import Historical Data" badge={<Badge tone="muted">Private to this workspace</Badge>}>
        <div role="note" className="rounded-lg border border-line bg-bg/60 p-3 text-xs leading-relaxed text-muted">
          <p>Choose one results file per season (football-data layout: <code className="font-mono">Date, HomeTeam, AwayTeam, FTHG, FTAG</code>, extra columns ignored; or the five columns <code className="font-mono">date, home_team, away_team, home_goals, away_goals</code>). Full-time scores only. Club names are standardised, and a season is only called complete when it has 20 clubs, 380 matches and 38 for every club.</p>
          <p className="mt-1">Importing is safe to repeat: a match already stored is never duplicated, and a stored match whose score differs is reported rather than overwritten. To update the current season, import its newer file again.</p>
        </div>
        <div className="mt-3">
          <label htmlFor="fh-files" className="mb-1 block text-xs text-muted">Season files (each up to 2 MB)</label>
          <input id="fh-files" type="file" multiple accept=".csv,.tsv,.txt,text/csv,text/plain" onChange={(e) => { setFiles(Array.from(e.target.files ?? [])); setProgress([]); }}
            className="block w-full text-sm file:mr-3 file:rounded-lg file:border file:border-line file:bg-white/5 file:px-3 file:py-1.5 file:text-xs file:font-semibold" />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
          <label className="inline-flex items-center gap-2"><input type="checkbox" checked={combined} onChange={(e) => setCombined(e.target.checked)} /> Combined file (several seasons in one file)</label>
          <label className="inline-flex items-center gap-2"><input type="checkbox" checked={checkOnly} onChange={(e) => setCheckOnly(e.target.checked)} /> Check only, do not save</label>
        </div>
        <button type="button" disabled={files.length === 0 || importing} onClick={runImport} className={`${primary} mt-4`}>
          <Spin on={importing} /> {checkOnly ? "Check the files" : "Import Historical Data"}
        </button>
        <ol aria-live="polite" className="mt-4 space-y-3">
          {progress.map((p) => (
            <li key={p.name} className="rounded-xl border border-line p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{p.name}</span>
                <Badge tone={p.state === "done" ? (p.report?.status === "needs_review" || (p.report?.rejected ?? 0) > 0 ? "amber" : "green") : p.state === "failed" ? "amber" : "muted"}>
                  {p.state === "waiting" ? "Waiting" : p.state === "working" ? "Checking…" : p.state === "failed" ? "Not imported" : p.report?.dry_run ? "Checked, not saved" : "Imported"}
                </Badge>
              </div>
              {p.state === "failed" && <p role="alert" className="mt-2 text-xs text-red-300">{p.message}</p>}
              {p.report && <ReportBody r={p.report} />}
            </li>
          ))}
        </ol>
      </Panel>

      {view === "matches" && sum && <MatchesPanel season={season} clubs={sum.clubs} />}
      {view === "report" && <ReportPanel tick={tick} />}
      {view === "tools" && sum && <ToolsPanel season={season} clubs={sum.clubs} />}
    </section>
  );
}

function ReportBody({ r }: { r: ImportReport }) {
  return (
    <div className="mt-2 space-y-2 text-xs">
      <p className="text-muted">
        {r.rows_read.toLocaleString()} rows read · <strong className="text-ink">{r.valid.toLocaleString()} accepted</strong> ({r.new.toLocaleString()} new, {r.unchanged.toLocaleString()} already stored) · {r.rejected} rejected · {r.duplicates} duplicate · {r.conflicts} conflicting · {r.missing} missing · {r.unplayed_skipped} not yet played
      </p>
      {r.seasons.map((s) => <p key={s.season}><Badge tone={STATUS_TONE[s.status]}>{s.season} {STATUS_LABEL[s.status]}</Badge> <span className="text-muted">{s.matches} matches, {s.clubs} clubs{s.missing_count ? `, missing: ${s.missing_fixtures.slice(0, 3).join(", ")}${s.missing_count > 3 ? ` and ${s.missing_count - 3} more` : ""}` : ""}</span></p>)}
      {r.warnings.map((w) => <p key={w} className="text-amber-200">{w}</p>)}
      {r.rejected_rows.length > 0 && (
        <details><summary className="cursor-pointer text-muted">Rejected rows ({r.rejected})</summary>
          <ul className="mt-1 list-disc pl-5 text-red-200">{r.rejected_rows.slice(0, 20).map((x) => <li key={x.line}>Line {x.line}: {x.reason}</li>)}</ul></details>
      )}
      {r.conflict_rows.length > 0 && (
        <details><summary className="cursor-pointer text-muted">Conflicting results ({r.conflicts})</summary>
          <ul className="mt-1 list-disc pl-5 text-amber-200">{r.conflict_rows.slice(0, 20).map((x) => <li key={`${x.date}${x.home}${x.away}`}>{x.date} {x.home} v {x.away}: {x.found.join(" vs ")}</li>)}</ul></details>
      )}
    </div>
  );
}

function ReportPanel({ tick }: { tick: number }) {
  const [data, setData] = useState<{ overview: Summary; imports: { id: string; created_at: string; filename: string | null; status: string; report: ImportReport; created_by_name: string | null }[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    call<NonNullable<typeof data>>("football/report").then((d) => live && setData(d), (e) => live && setErr(e instanceof Error ? e.message : "Could not load the report."));
    return () => { live = false; };
  }, [tick]);
  if (err) return <ErrorPanel message={err} />;
  if (!data) return <p className="text-sm text-muted" aria-busy="true">Loading the report…</p>;
  return (
    <Panel title="Data validation report">
      <div className="space-y-4">
        {data.overview.seasons.length === 0 && <p className="text-sm text-muted">Nothing has been imported yet.</p>}
        {data.overview.seasons.map((s) => (
          <div key={s.season} className="rounded-xl border border-line p-3 text-sm">
            <p className="font-medium">{s.season} <Badge tone={STATUS_TONE[s.status]}>{STATUS_LABEL[s.status]}</Badge></p>
            <ul className="mt-2 grid gap-1 text-xs sm:grid-cols-2">
              {s.checks.map((c) => <li key={c.name}><span aria-hidden="true">{c.ok ? "✓" : "✗"}</span><span className="sr-only">{c.ok ? "Passed:" : "Failed:"}</span> {c.name} <span className="text-muted">({c.detail})</span></li>)}
            </ul>
            {s.missing_count > 0 && <p className="mt-2 text-xs text-amber-200">Missing ({s.missing_count}): {s.missing_fixtures.join(", ")}{s.missing_count > s.missing_fixtures.length ? "…" : ""}</p>}
          </div>
        ))}
        {data.imports.length > 0 && <h3 className="text-sm font-semibold">Recent imports</h3>}
        {data.imports.map((i) => (
          <div key={i.id} className="rounded-xl border border-line p-3 text-sm">
            <p className="font-medium">{i.filename ?? "Import"} <span className="text-xs font-normal text-muted">{dt(i.created_at)}{i.created_by_name ? ` · ${i.created_by_name}` : ""}</span></p>
            <ReportBody r={i.report} />
          </div>
        ))}
      </div>
    </Panel>
  );
}

function MatchesPanel({ season, clubs }: { season: string; clubs: string[] }) {
  const [team, setTeam] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ total: number; matches: MatchRow[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [forKey, setForKey] = useState("");
  const key = `${season}|${team}`;
  if (forKey !== key) { setForKey(key); setOffset(0); }
  useEffect(() => {
    let live = true;
    const q = new URLSearchParams({ limit: "50", offset: String(offset) });
    if (season !== "all") q.set("season", season);
    if (team) q.set("team", team);
    call<{ total: number; matches: MatchRow[] }>(`football/matches?${q}`).then((d) => live && setData(d), (e) => live && setErr(e instanceof Error ? e.message : "Could not load matches."));
    return () => { live = false; };
  }, [season, team, offset]);
  return (
    <Panel title="Matches">
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="fh-team" className="mb-1 block text-xs text-muted">Club</label>
          <select id="fh-team" value={team} onChange={(e) => setTeam(e.target.value)} className={field}>
            <option value="">All clubs</option>{clubs.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <p className="text-xs text-muted">{season === "all" ? "All seasons" : season}{data ? ` · ${data.total.toLocaleString()} matches` : ""}</p>
      </div>
      {err && <p role="alert" className="text-sm text-red-300">{err}</p>}
      {data && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Imported matches, newest first</caption>
              <thead><tr className="text-left text-[11px] text-muted">{["Date", "Home", "Score", "Away", "Season"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
              <tbody>{data.matches.map((m) => (
                <tr key={`${m.match_date}${m.home_team}${m.away_team}`} className="border-t border-line">
                  <td className="py-1 pr-3 font-mono text-xs">{m.match_date}</td><td className="pr-3">{m.home_team}</td>
                  <td className="pr-3 font-mono">{m.home_goals}–{m.away_goals}</td><td className="pr-3">{m.away_team}</td><td className="text-xs text-muted">{m.season}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <div className="mt-3 flex items-center gap-3 text-xs">
            <button type="button" className={btn} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Newer</button>
            <span className="text-muted">{data.total ? `${offset + 1}–${Math.min(offset + 50, data.total)} of ${data.total.toLocaleString()}` : "No matches"}</span>
            <button type="button" className={btn} disabled={offset + 50 >= data.total} onClick={() => setOffset(offset + 50)}>Older</button>
          </div>
        </>
      )}
    </Panel>
  );
}

function verdict(p: Period): string {
  if (p.log_loss === undefined || p.baseline_log_loss === undefined) return "";
  if (p.gain_is_clear) return "Clearly better than the baseline in this period.";
  return (p.log_loss_gain ?? 0) > 0 ? "Slightly better than the baseline, but not by enough to rule out luck." : "No better than the baseline in this period.";
}

function ToolsPanel({ season, clubs }: { season: string; clubs: string[] }) {
  const [name, setName] = useState("Premier League results");
  const [busy, setBusy] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [evalRes, setEvalRes] = useState<Evaluation | null>(null);
  const [home, setHome] = useState("");
  const [away, setAway] = useState("");
  const [asOf, setAsOf] = useState("");
  const [fix, setFix] = useState<Fixture | null>(null);

  async function run<T>(label: string, fn: () => Promise<T>, then: (x: T) => void) {
    setBusy(label); setErr(null);
    try { then(await fn()); } catch (e) { setErr(e instanceof Error ? e.message : "Something went wrong."); } finally { setBusy(null); }
  }
  return (
    <Panel title="Use this history in forecasts" badge={<Badge tone="muted">Earlier matches only</Badge>}>
      <div className="space-y-6">
        <div>
          <h3 className="text-sm font-semibold">Save as a sports dataset</h3>
          <p className="mt-1 text-xs text-muted">Creates a regular sports dataset ({season === "all" ? "all stored seasons" : season}) that the Sports &ldquo;Your data&rdquo; tab can forecast and test. It counts toward your dataset allowance.</p>
          <div className="mt-2 flex flex-wrap items-end gap-3">
            <div>
              <label htmlFor="fh-dsname" className="mb-1 block text-xs text-muted">Dataset name for forecasts</label>
              <input id="fh-dsname" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} className={field} />
            </div>
            <button type="button" className={btn} disabled={busy !== null || !name.trim()} onClick={() => run("save", () => post<{ name: string; row_count: number }>("football/dataset", { name, seasons: season === "all" ? null : [season] }), (r) => setSaved(`Saved “${r.name}” (${r.row_count.toLocaleString()} matches).`))}>
              <Spin on={busy === "save"} /> Create dataset
            </button>
          </div>
          {saved && <p role="status" className="mt-2 text-sm text-success">{saved} <Link href="/dashboard/sports" className="underline">Open Sports</Link></p>}
        </div>

        <div>
          <h3 className="text-sm font-semibold">What the model sees before a fixture</h3>
          <p className="mt-1 text-xs text-muted">Form, head-to-head, Elo-style rating and the Poisson projection, using only matches played before the date. Goal rates are estimated from results, not provider expected goals.</p>
          <div className="mt-2 flex flex-wrap items-end gap-3">
            <div><label htmlFor="fh-home" className="mb-1 block text-xs text-muted">Home club</label>
              <select id="fh-home" value={home} onChange={(e) => { setHome(e.target.value); setFix(null); }} className={field}><option value="">Choose…</option>{clubs.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
            <div><label htmlFor="fh-away" className="mb-1 block text-xs text-muted">Away club</label>
              <select id="fh-away" value={away} onChange={(e) => { setAway(e.target.value); setFix(null); }} className={field}><option value="">Choose…</option>{clubs.filter((c) => c !== home).map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
            <div><label htmlFor="fh-asof" className="mb-1 block text-xs text-muted">As of (optional)</label>
              <input id="fh-asof" type="date" value={asOf} onChange={(e) => { setAsOf(e.target.value); setFix(null); }} className={field} /></div>
            <button type="button" className={btn} disabled={busy !== null || !home || !away}
              onClick={() => run("fixture", () => call<Fixture>(`football/fixture?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}${asOf ? `&before=${asOf}` : ""}`), setFix)}>
              <Spin on={busy === "fixture"} /> Show
            </button>
          </div>
          {fix && (
            <div className="mt-3 space-y-3 text-sm" aria-live="polite">
              <div className="grid gap-3 sm:grid-cols-2">
                {[fix.home, fix.away].map((t, i) => (
                  <div key={t.team} className="rounded-xl border border-line p-3">
                    <p className="font-medium">{t.team} <span className="text-xs font-normal text-muted">{i === 0 ? "home" : "away"}</span></p>
                    <dl className="mt-1 grid grid-cols-2 gap-x-3 text-xs">
                      <dt className="text-muted">Elo-style rating</dt><dd className="font-mono">{t.elo}</dd>
                      <dt className="text-muted">Last 5</dt><dd className="font-mono">{t.form_last_5.results || "—"}{t.form_last_5.points_per_match !== null ? ` (${t.form_last_5.points_per_match} pts/match)` : ""}</dd>
                      <dt className="text-muted">Win rate</dt><dd className="font-mono">{t.win_rate !== undefined ? pct(t.win_rate) : "—"}</dd>
                      <dt className="text-muted">Goals for / against</dt><dd className="font-mono">{t.goals_for_per_match ?? "—"} / {t.goals_against_per_match ?? "—"}</dd>
                      <dt className="text-muted">Clean sheets</dt><dd className="font-mono">{t.clean_sheet_rate !== undefined ? pct(t.clean_sheet_rate) : "—"}</dd>
                      <dt className="text-muted">Attack / defence</dt><dd className="font-mono">{t.attack_strength ?? "—"} / {t.defence_strength ?? "—"}</dd>
                    </dl>
                  </div>
                ))}
              </div>
              <p>Head to head: {fix.head_to_head.meetings} meeting(s), {fix.home.team} won {fix.head_to_head.wins_a}, {fix.away.team} won {fix.head_to_head.wins_b}, {fix.head_to_head.draws} drawn{fix.head_to_head.recent[0] ? `; latest ${fix.head_to_head.recent[0].date} ${fix.head_to_head.recent[0].home} ${fix.head_to_head.recent[0].score} ${fix.head_to_head.recent[0].away}` : ""}.</p>
              <p>Model projection: {fix.home.team} {pct(fix.projection.p_home)}, draw {pct(fix.projection.p_draw)}, {fix.away.team} {pct(fix.projection.p_away)} (estimated goals {fix.projection.home_xg.toFixed(2)} to {fix.projection.away_xg.toFixed(2)}).</p>
              <p className="text-xs text-muted">Built from {fix.matches_used.toLocaleString()} matches played before {fix.as_of}. {fix.projection_note}</p>
            </div>
          )}
        </div>

        <div>
          <h3 className="text-sm font-semibold">How well does the model do over time?</h3>
          <p className="mt-1 text-xs text-muted">Splits all stored matches by date (first 60% to learn from, next 20% validation, last 20% test) and scores the model on the last two against a baseline that only knows the overall home, draw and away rates. Takes about 15 seconds on ten seasons.</p>
          <button type="button" className={`${btn} mt-2`} disabled={busy !== null} onClick={() => run("eval", () => post<Evaluation>("football/evaluation", {}), setEvalRes)}><Spin on={busy === "eval"} /> Test by period</button>
          {evalRes && (
            <div className="mt-3 space-y-3" aria-live="polite">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <caption className="sr-only">Model and baseline scores by period</caption>
                  <thead><tr className="text-left text-[11px] text-muted">{["Period", "Dates", "Scored", "Log loss (model / baseline)", "Brier (model / baseline)", "Right result (model / baseline)"].map((h) => <th key={h} scope="col" className="pr-3 font-normal">{h}</th>)}</tr></thead>
                  <tbody className="font-mono">
                    {evalRes.periods.map((p) => (
                      <tr key={p.name} className="border-t border-line align-top">
                        <th scope="row" className="py-1.5 pr-3 text-left font-sans font-medium capitalize">{p.name}</th>
                        <td className="pr-3 text-xs">{p.first} to {p.last}</td>
                        <td className="pr-3">{p.scored ?? "learn only"}</td>
                        <td className="pr-3">{p.log_loss !== undefined ? `${p.log_loss.toFixed(3)} / ${p.baseline_log_loss!.toFixed(3)}` : "—"}</td>
                        <td className="pr-3">{p.brier !== undefined ? `${p.brier.toFixed(3)} / ${p.baseline_brier!.toFixed(3)}` : "—"}</td>
                        <td className="pr-3">{p.accuracy !== undefined ? `${pct(p.accuracy)} / ${pct(p.baseline_accuracy!)}` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {evalRes.periods.filter((p) => p.log_loss !== undefined).map((p) => <p key={p.name} className="text-sm"><strong className="capitalize">{p.name}:</strong> {verdict(p)}</p>)}
              <p className="text-xs leading-relaxed text-muted">{evalRes.note} Nothing was tuned on the validation or test period. A few hundred scored matches can only show large differences, and good past scores do not guarantee future ones. This is not betting or financial advice.</p>
            </div>
          )}
        </div>
        {err && <p role="alert" className="text-sm text-red-300">{err}</p>}
      </div>
    </Panel>
  );
}
