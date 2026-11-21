import { describe, expect, it } from "vitest";
import { evidenceToMarkdown, type Evidence } from "./report";

const empty: Evidence = {
  workspace: "Test workspace", generated_at: "2026-01-01T00:00:00Z",
  data: { matches: 0, seasons: [], first: null, last: null, data_sha256: null, sources: [], uploads: [] },
  historical_evaluation: { chronological: null, rolling: null },
  forecasts: { scored: [], waiting_for_results: 0, note: "Forecasts made before a match and scored after it." },
  saved_work: { predictions: 0, scenarios: 0, simulations: 0 },
  statements: ["This is analysis, not betting, financial or legal advice."],
};

const full: Evidence = {
  ...empty,
  data: { matches: 3800, seasons: ["2016/17", "2017/18", "2018/19"], first: "2016-08-13", last: "2019-05-12", data_sha256: "a".repeat(64),
    sources: [{ kind: "match_results", name: "EPL.csv", provider: "user_upload", reference: "EPL.csv sha256:abc", licence_note: "Supplied by the user.", source_url: "https://example.org/epl.csv", source_licence: "Personal use only", retrieved_on: "2026-01-01", dataset_version: "2026-01", created_at: "2026-01-01T10:00:00Z" }], uploads: [] },
  historical_evaluation: {
    chronological: { run_id: "r1", created_at: "2026-01-02T10:00:00Z", matches: 3800, data_sha256: "a".repeat(64), history_changed_since: true, split: { training: ["2016/17"], validation: ["2017/18"], test: ["2018/19"] }, model_version: "1.1.0",
      test: [{ model: "Dixon-Coles", matches: 380, log_loss: 1.0439, brier: 0.6, accuracy: 0.5, calibration_gap: 0.02, gain_vs_frequency: 0.0186, gain_standard_error: 0.004, gain_clear: true }],
      validation: [], warnings: ["Settings were chosen on the validation period only."], versions: [{ name: "elo", version: "1.1.0", trained_through: "2019-05-12" }] },
    rolling: null,
  },
};

describe("evidenceToMarkdown", () => {
  it("claims nothing for a workspace with no records", () => {
    const md = evidenceToMarkdown(empty);
    expect(md).toContain("No match history has been imported.");
    expect(md).toContain("No chronological backtest has been run, so there are no accuracy figures to report.");
    expect(md).toContain("No tracked forecast has been scored yet. 0 are waiting for results.");
    expect(md).not.toMatch(/\d\.\d{3}/);          // no figure of any kind appears
  });

  it("reports recorded figures exactly, keeps evaluation and forecasts in separate sections, and flags changed history", () => {
    const md = evidenceToMarkdown(full);
    expect(md).toContain("3,800 Premier League matches, seasons 2016/17 to 2018/19 (3 seasons)");
    expect(md).toContain("`" + "a".repeat(64) + "`");
    expect(md).toContain("| EPL.csv | match_results | user_upload | https://example.org/epl.csv | Personal use only | 2026-01-01 | 2026-01 | 2026-01-01 |");
    expect(md).toContain("| Dixon-Coles | 380 | 1.044 | 0.600 | 50.0% | 2.0 pts | +0.019 ± 0.004 (clear) |");
    expect(md).toContain("The imported history has changed since this run");
    expect(md.indexOf("## 2. Historical evaluation")).toBeLessThan(md.indexOf("## 3. Forecasts"));
    expect(md).toContain("Training 2016/17 to 2016/17; validation 2017/18; test 2018/19.");
    expect(md).toContain("No tracked forecast has been scored yet.");              // evaluation figures never leak into the forecasts section
    expect(md).toContain("elo@1.1.0 (trained through 2019-05-12)");
  });

  it("shows n/a for missing values instead of inventing them", () => {
    const md = evidenceToMarkdown({ ...full, historical_evaluation: { ...full.historical_evaluation, chronological: { ...full.historical_evaluation.chronological!, history_changed_since: false, test: [{ model: "Elo rating", matches: 10, log_loss: 1, brier: 0.5, accuracy: null, calibration_gap: null, gain_vs_frequency: null, gain_standard_error: null, gain_clear: null }] } } });
    expect(md).toContain("| Elo rating | 10 | 1.000 | 0.500 | n/a | n/a | n/a |");
    expect(md).toContain("The imported history is unchanged since this run.");
  });
});
