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
