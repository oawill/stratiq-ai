export interface ScorelineP { home: number; away: number; p: number }

export interface SportsOutputs {
  home_xg: number;
  away_xg: number;
  p_home: number;
  p_draw: number;
  p_away: number;
  p_btts: number;
  p_over_2_5: number;
  top_scorelines: ScorelineP[];
  scoreline_grid: number[][];
  grid_tail_mass_removed: number;
}

export interface SportsInputs {
  home_team: string;
  away_team: string;
  home_name?: string;
  away_name?: string;
  feature_cutoff: string;
  dataset: string;
  matches_used: number;
  matches_used_digest: string;
  home_team_matches: number;
  away_team_matches: number;
  league_mean_goals: number;
  home_advantage: number;
  home_attack: number;
  home_defence: number;
  away_attack: number;
  away_defence: number;
  fit_iterations: number;
  fit_converged: boolean;
  retrospective?: boolean;
  fixture_id?: number | null;
}

export interface ModelRow { id: string; domain: string; name: string; version: string; description: string; status: string }
export interface MetricRow { name: string; version: string; domain: string; metric: string; value: number; sample_size: number; dataset: string }
export interface PredictionRow {
  id: string;
  created_at: string;
  feature_cutoff: string;
  inputs: SportsInputs;
  outputs: SportsOutputs;
  model_name: string;
  model_version: string;
}
export interface ActivityRow { id: number; kind: string; summary: string; ref_type: string | null; ref_id: string | null; created_at: string }

export interface Overview {
  models: ModelRow[];
  recent_predictions: PredictionRow[];
  saved_simulations: { id: string; domain: string; status: string; created_at: string }[];
  saved_scenarios: number | string;
  metrics: MetricRow[];
  activity: ActivityRow[];
  counts: { predictions: number | string; simulations: number | string };
}

export interface Fixture {
  id: number;
  league_id: string;
  kickoff: string;
  status: "scheduled" | "finished";
  home_goals: number | null;
  away_goals: number | null;
  home_team_id: string;
  home_name: string;
  away_team_id: string;
  away_name: string;
}
export interface League { id: string; name: string; country: string; is_fictional: boolean; teams: number | string; finished: number | string; scheduled: number | string }
export interface TeamRating { id: string; name: string; attack: number; defence: number; matches: number }
export interface ResultRow { id: number; kickoff: string; home_goals: number; away_goals: number; home_name: string; away_name: string; home_team_id?: string }
export interface Compare {
  home: { id: string; name: string };
  away: { id: string; name: string };
  ratings: SportsInputs;
  projection: SportsOutputs;
  home_form: ResultRow[];
  away_form: ResultRow[];
  head_to_head: ResultRow[];
}
export interface SportsModelInfo {
  model: { name: string; version: string; description: string; status: string; assumptions: string[]; limitations: string[] };
  metrics: MetricRow[];
}

// ---- Business Strategy ----
export interface Cell { row: number; col: number }
export interface Dominance {
  strictly_dominant: number | null;
  weakly_dominant: number | null;
  strictly_dominated: { strategy: number; by: number }[];
  weakly_dominated: { strategy: number; by: number }[];
}
export interface GameAnalysis {
  pure_nash: (Cell & { payoffs: [number, number] })[];
  best_responses: { row_to_col: number[][]; col_to_row: number[][] };
  dominance: { row: Dominance; col: Dominance };
  iterated_elimination: { steps: { player: "row" | "col"; eliminated: number; by: number }[]; remaining_rows: number[]; remaining_cols: number[] };
  mixed_2x2: { row_probs: number[]; col_probs: number[]; row_probs_exact: string[]; col_probs_exact: string[]; expected_payoffs: number[] } | null;
  pareto_optimal: Cell[];
  max_welfare: { value: number; cells: Cell[] };
  notes: string[];
}
export interface SensitivityResult {
  player: "row" | "col";
  cell: Cell;
  range: [number, number];
  thresholds: number[];
  segments: { from: number; to: number; pure_nash: Cell[] }[];
  at_points: { value: number; pure_nash: Cell[] }[];
}
export interface ScenarioListRow { id: string; title: string; created_at: string; created_by_name: string; players: string[]; rows_n: number; cols_n: number; nash_n: number | null }
export interface ScenarioFull {
  id: string; title: string; created_at: string; notes: string | null; players: string[];
  row_strategies: string[]; col_strategies: string[]; payoffs: number[][][]; analysis: GameAnalysis;
}
export interface CompareRow {
  id: string; title: string; players: string[]; row_strategies: string[]; col_strategies: string[];
  pure_nash: { row: string; col: string; payoffs: [number, number] }[];
  row_dominant: string | null; col_dominant: string | null;
  max_welfare: { value: number; cells: { row: string; col: string }[] };
  mixed_2x2: GameAnalysis["mixed_2x2"]; notes: string[];
}

// ---- Simulation Lab ----
export type DistType = "normal" | "lognormal" | "uniform" | "triangular" | "beta" | "bernoulli" | "binomial" | "poisson" | "constant" | "discrete";
export interface OutputStats {
  mean: number; sd: number; min: number; max: number; p05: number; p25: number; p50: number; p75: number; p95: number;
  se_mean: number; ci95_mean: [number, number];
}
export interface SimOutput {
  expr: string;
  stats: OutputStats;
  histogram: { edges: number[]; counts: number[] };
  prob_above: { threshold: number; p: number; se: number } | null;
  sensitivity: { variable: string; spearman: number }[];
  convergence: { n: number; mean: number }[];
}
export interface SimResult {
  engine_version: string; python_version: string; iterations: number; seed: number; result_hash: string; runtime_ms: number;
  outputs: Record<string, SimOutput>;
  inputs: Record<string, { dist: Record<string, unknown>; realised_mean: number; realised_sd: number; realised_min: number; realised_max: number }>;
}
export type RunStatus = "queued" | "running" | "completed" | "failed" | "cancelled";
export interface SimRunRow { id: string; title: string; domain: string; status: RunStatus; progress: number; iterations: number; seed: number; created_at: string; finished_at: string | null; created_by_name: string }
export interface SimRun extends SimRunRow {
  config: { variables: { name: string; dist: Record<string, unknown> }[]; outputs: { name: string; expr: string; threshold?: number | null }[]; notes?: string | null };
  result: SimResult | null; error: string | null; started_at: string | null;
}
export interface SimCompare {
  outputs: {
    output: string;
    runs: ({ title: string; iterations: number; seed: number; mean: number; sd: number; p05: number; p50: number; p95: number; se_mean: number; prob_above: { threshold: number; p: number } | null } | null)[];
    diff_vs_first: ({ mean_diff: number; se: number; ci95: [number, number] } | null)[];
  }[];
  runs: { id: string; title: string; domain: string; iterations: number; seed: number; histograms: Record<string, { edges: number[]; counts: number[] }> }[];
}

// ---- Political Intelligence ----
export interface PolParty {
  name: string; seats: number; seat_share: number; shapley_shubik: number; shapley_shubik_exact: string;
  banzhaf_raw_swings: number; banzhaf_normalised: number; banzhaf_probability: number;
  is_dictator: boolean; is_veto: boolean; is_dummy: boolean;
}
export interface PolCoalition {
  total_seats: number; quota_fraction: number; seats_needed: number; parties: PolParty[];
  winning_coalitions: number; minimal_winning_count: number;
  minimal_winning: { parties: number[]; seats: number; surplus: number; size: number; ideological_range: number | null; connected: boolean | null }[];
  connected_minimal_winning: number | null; single_party_majority: string[]; notes: string[]; notice: string;
}
export interface PolAllocate { parties: { name: string; votes: number; vote_share: number; seats: number; seat_share: number }[] }
export interface PolSimulation {
  seed: number; iterations: number; seats_needed: number; p_no_single_party_majority: number; note: string;
  parties: { name: string; mean_seats: number; p05_seats: number; p95_seats: number; p_largest: number; p_single_party_majority: number; p_decisive_in_some_coalition: number; p_veto: number }[];
  candidates: { parties: number[]; p_winning: number; p_minimal_winning: number }[];
}
export interface PolEval { votes: number[]; vote_share: number[]; seats: number[]; largest: string; majority_party: string | null; turnout_overall: number }
export interface PolTurnout {
  parties: string[]; baseline: PolEval; notice: string;
  sweep?: { mode: string; bloc: number | null; range: [number, number]; curve: { x: number; overall_turnout: number; vote_share: number[]; seats: number[] }[]; changes: { at: number; what: string[]; seats_before: number[]; seats_after: number[] }[]; note: string };
}
export interface PolPolicy {
  weights_normalised: number[]; ranking: string[]; seed: number; samples: number; notes: string[]; notice: string;
  alternatives: { name: string; normalised: number[]; weighted_score: number; rank: number; pareto_optimal: boolean; rank_probabilities: number[]; p_top: number; expected_rank: number }[];
  weight_sensitivity: { criterion: string; current_weight: number; segments: { from: number; to: number; top: string[] }[]; stable_range: [number, number] | null; note?: string }[];
}
export type PolKind = "coalition" | "turnout" | "policy";
export interface PolScenarioRow { id: string; title: string; created_at: string; created_by_name: string; kind: PolKind }
export interface PolScenarioFull { id: string; title: string; kind: PolKind; notes: string | null; inputs: Record<string, unknown> }
export interface PolCompare { kind: PolKind; scenarios: { id: string; title: string; summary: Record<string, any> }[] } // eslint-disable-line @typescript-eslint/no-explicit-any

// ---- Financial Intelligence ----
export interface FinAnalytics {
  expected_return: number; volatility: number; diversification_ratio: number; notice: string; notes: string[];
  assets: { name: string; weight: number; risk_contribution: number; stand_alone_vol: number }[];
}
export interface FinMonteCarlo {
  engine_version: string; python_version: string; seed: number; iterations: number; steps: number; horizon_years: number; result_hash: string; runtime_ms: number;
  initial_value: number; notice: string; notes: string[];
  model: { rebalance: string; tails: string; df: number | null };
  analytics: FinAnalytics;
  terminal: { mean_value: number; se_mean_value: number; analytic_mean_value: number | null; median_value: number; p5_value: number; p95_value: number;
    return: { mean: number; sd: number; min: number; max: number; p05: number; p25: number; p50: number; p75: number; p95: number };
    histogram: { edges: number[]; counts: number[] } };
  p_loss: number;
  p_loss_exceeds: { threshold: number; p: number } | null;
  max_drawdown: { mean: number; p95: number; p_exceeds: { threshold: number; p: number } | null };
  risk: { confidence: number; mc_var: number; mc_es: number; tail_observations: number; approx_normal_var: number; approx_normal_es: number }[];
  fan: { t: number; p05: number; p25: number; p50: number; p75: number; p95: number }[];
}
export interface FinStress {
  worst: string; reverse_target: number | null; notice: string; notes: string[];
  scenarios: { name: string; portfolio_return: number; pnl: number; value_after: number; scale_to_target?: number | null;
    contributions: { asset: string; shock: number; contribution: number; pnl: number }[] }[];
}
export interface FinSeriesStats {
  periods: number; mean_period: number; vol_period: number; annualised_mean: number; annualised_vol: number; total_return: number; cagr: number;
  max_drawdown: number; skewness: number; excess_kurtosis: number; best_period: number; worst_period: number;
}
export interface FinHistorical {
  periods_per_year: number; names: string[]; weights: number[]; assets: Record<string, FinSeriesStats>; correlation: number[][]; portfolio: FinSeriesStats;
  provenance: string; notice: string; notes: string[];
  risk: { confidence: number; tail_observations: number; warning: string | null; historical: { var: number; es: number }; parametric_normal: { var: number; es: number };
    kupiec_parametric: { exceedances: number; observations: number; expected: number; lr: number; p_value: number } }[];
  growth: { t: number; value: number; drawdown: number }[];
}
export type FinKind = "montecarlo" | "stress" | "historical";
export interface FinScenarioRow { id: string; title: string; created_at: string; created_by_name: string; kind: FinKind }
export interface FinScenarioFull { id: string; title: string; kind: FinKind; notes: string | null; inputs: Record<string, unknown> }
export interface FinCompare { kind: FinKind; scenarios: { id: string; title: string; summary: Record<string, any> }[] } // eslint-disable-line @typescript-eslint/no-explicit-any
export interface FinDataSources { configured: boolean; requested_provider: string | null; message: string }
