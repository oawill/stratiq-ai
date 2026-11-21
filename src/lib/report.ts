// The workspace evidence report: its shape (as returned by /api/v1/reports/evidence) and a Markdown rendering of it.
// The renderer only formats what it is given. A part with no records says so; it never fills in a figure.

export interface MetricRow { model: string; matches: number; log_loss: number; brier: number; accuracy: number | null; calibration_gap: number | null; gain_vs_frequency: number | null; gain_standard_error: number | null; gain_clear: boolean | null }
export interface Evidence {
  workspace: string | null;
  generated_at: string;
  data: { matches: number; seasons: string[]; first: string | null; last: string | null; data_sha256: string | null;
    sources: { kind: string; name: string; provider: string; reference: string | null; licence_note: string; created_at: string }[];
    uploads: { kind: string; name: string; row_count: number; sha256: string; created_at: string }[] };
  historical_evaluation: {
    chronological: null | { run_id: string; created_at: string; matches: number; data_sha256: string; history_changed_since: boolean; split: Record<string, string[]> | null; model_version: string | null;
      test: MetricRow[]; validation: MetricRow[]; warnings: string[]; versions: { name: string; version: string; trained_through: string | null }[] };
    rolling: null | { run_id: string; created_at: string; matches: number; seasons_predicted: string[] | null; results: MetricRow[]; warnings: string[] };
  };
  forecasts: { scored: { model: string; version: string; n: number; log_loss: number; brier: number; accuracy: number; first: string; last: string }[]; waiting_for_results: number; note: string };
  saved_work: { predictions: number; scenarios: number; simulations: number };
  statements: string[];
}

const f3 = (v: number | null | undefined) => (v === null || v === undefined ? "n/a" : v.toFixed(3));
const pc = (v: number | null | undefined) => (v === null || v === undefined ? "n/a" : `${(v * 100).toFixed(1)}%`);
const day = (s: string | null | undefined) => (s ? s.slice(0, 10) : "n/a");

function metricTable(rows: MetricRow[]): string[] {
  if (rows.length === 0) return ["_No results recorded._", ""];
  return [
    "| Model | Matches | Log loss | Brier | Right result | Calibration gap | Log-loss gain over frequency baseline |",
    "|---|---|---|---|---|---|---|",
    ...rows.map((r) => `| ${r.model} | ${r.matches} | ${f3(r.log_loss)} | ${f3(r.brier)} | ${pc(r.accuracy)} | ${r.calibration_gap === null ? "n/a" : `${(r.calibration_gap * 100).toFixed(1)} pts`} | ${r.gain_vs_frequency === null ? "n/a" : `${r.gain_vs_frequency >= 0 ? "+" : ""}${f3(r.gain_vs_frequency)} ± ${f3(r.gain_standard_error)}${r.gain_clear ? " (clear)" : ""}`} |`),
    "",
  ];
}

export function evidenceToMarkdown(e: Evidence): string {
  const L: string[] = [];
  L.push(`# Evidence report${e.workspace ? `: ${e.workspace}` : ""}`, "", `Generated ${e.generated_at}.`, "");
  L.push("## 1. Data and provenance", "");
  if (e.data.matches === 0) L.push("No match history has been imported.", "");
  else L.push(`- ${e.data.matches.toLocaleString("en-US")} Premier League matches, seasons ${e.data.seasons[0]} to ${e.data.seasons[e.data.seasons.length - 1]} (${e.data.seasons.length} seasons), ${day(e.data.first)} to ${day(e.data.last)}.`, `- Data fingerprint (SHA-256): \`${e.data.data_sha256}\``, "");
  if (e.data.sources.length) L.push("| Source | Kind | Provider | Reference | Added |", "|---|---|---|---|---|", ...e.data.sources.map((s) => `| ${s.name} | ${s.kind} | ${s.provider} | ${s.reference ?? "n/a"} | ${day(s.created_at)} |`), "", `Licence note: ${e.data.sources[0].licence_note}`, "");
  if (e.data.uploads.length) L.push("Datasets in the Data workspace:", "", ...e.data.uploads.map((u) => `- ${u.name} (${u.kind}, ${u.row_count.toLocaleString("en-US")} rows, sha256 \`${u.sha256.slice(0, 12)}…\`, ${day(u.created_at)})`), "");

  L.push("## 2. Historical evaluation (backtests on past matches)", "");
  const c = e.historical_evaluation.chronological;
  if (!c) L.push("No chronological backtest has been run, so there are no accuracy figures to report.", "");
  else {
    L.push(`Run ${day(c.created_at)} on ${c.matches.toLocaleString("en-US")} matches${c.model_version ? `, model version ${c.model_version}` : ""}.`);
    if (c.split) L.push(`Training ${c.split.training?.[0]} to ${c.split.training?.slice(-1)[0]}; validation ${c.split.validation?.join(", ")}; test ${c.split.test?.join(", ")}.`);
    L.push(c.history_changed_since ? "**The imported history has changed since this run: re-run the backtest before relying on it.**" : "The imported history is unchanged since this run.", "", "### Test period (never used to choose settings)", "", ...metricTable(c.test), "### Validation period (used to choose settings)", "", ...metricTable(c.validation));
    if (c.versions.length) L.push("Model versions: " + c.versions.map((v) => `${v.name}@${v.version}${v.trained_through ? ` (trained through ${day(v.trained_through)})` : ""}`).join(", "), "");
    for (const w of c.warnings) L.push(`- ${w}`);
    if (c.warnings.length) L.push("");
  }
  const r = e.historical_evaluation.rolling;
  if (r) L.push("### Rolling-origin backtest", "", `Run ${day(r.created_at)}; seasons predicted: ${(r.seasons_predicted ?? []).join(", ") || "n/a"}.`, "", ...metricTable(r.results));

  L.push("## 3. Forecasts (made before a match, scored after it)", "", e.forecasts.note, "");
  if (e.forecasts.scored.length === 0) L.push(`No tracked forecast has been scored yet. ${e.forecasts.waiting_for_results} are waiting for results.`, "");
  else L.push("| Model | Version | Scored | Log loss | Brier | Right result | Fixtures from | to |", "|---|---|---|---|---|---|---|---|", ...e.forecasts.scored.map((s) => `| ${s.model} | ${s.version} | ${s.n} | ${f3(s.log_loss)} | ${f3(s.brier)} | ${pc(s.accuracy)} | ${day(s.first)} | ${day(s.last)} |`), "", `${e.forecasts.waiting_for_results} more are waiting for results.`, "");

  L.push("## 4. Saved work", "", `${e.saved_work.predictions} saved forecasts, ${e.saved_work.scenarios} saved scenarios, ${e.saved_work.simulations} simulation runs.`, "", "## Notes", "", ...e.statements.map((s) => `- ${s}`), "");
  return L.join("\n");
}
