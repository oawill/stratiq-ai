# Football prediction intelligence (Phase 9, first round)

Forecasts for Premier League fixtures from three statistical models, with leak-free backtesting, a reliability breakdown, a what-if simulator and tracked outcomes. It lives in **Sports, "Football intelligence"**, on top of the history imported in **Data, Historical Football Data** (see `DATA.md`).

**No performance number in this document is a real result.** The repository's tests use synthetic seasons (real club names, random scores). How accurate the models are on your ten real seasons is unmeasured until you import them and run the backtest; the page reports whatever it finds, including "no better than the baseline".

## What is built

| Part | Status |
|---|---|
| Feature snapshots (13 factor groups, availability, source, as-of) | Built |
| Model A Elo (home advantage, opponent strength, season regression, newcomer offset) | Built |
| Model B Poisson (time-weighted attack and defence, home advantage) | Built |
| Model C Dixon-Coles (low-score correction, rho fitted by maximum likelihood) | Built |
| Baselines: historical frequencies, and Elo as a baseline for the others | Built |
| Chronological backtest (training 2016/17 to 2022/23, validation 2023/24, test 2024/25 to 2025/26) and rolling-origin backtest | Built |
| Dashboard: today's matches, match intelligence, simulator, model performance, data and factors | Built |
| Five Data Workspace types, each with its own requirements (football results, football advanced statistics, market returns, party seats, numeric series) | Built |
| Tables: `football_data_sources`, `football_teams`, `football_fixtures`, `football_team_statistics`, `football_player_availability` (schema only), `football_feature_snapshots`, `football_model_versions`, `football_predictions`, `football_prediction_outcomes`, `football_backtest_runs` (migration `0010`); `match_history` is the matches table | Built |
| Model D (machine learning) and Model E (ensemble) | **Not built.** Agreed to come next, as pure-Python boosted trees, once the statistical models are measured. No ensemble weights exist, so none are claimed. |
| Scheduled daily, post-match and weekly jobs, drift monitoring, retraining policy | **Not built.** Importing a played match already scores stored forecasts; nothing runs on a schedule, and there is nothing to fetch (see below). |
| Player availability, squad strength, manager changes, weather and travel | **Not built.** They have no data source, so they read "unavailable" in every forecast. The `football_player_availability` table exists but nothing writes to it. |

## Data and licensing

VELQORIN fetches nothing. Match results, fixtures and advanced statistics are files people upload, and they are responsible for having the right to use them (football-data.co.uk, for example, allows private use only). Each upload records a `football_data_sources` row with its name, coverage and quality. Fixtures are future-dated rows in a results-layout file. Advanced statistics (expected goals, shots, corners, odds) are a dataset type of their own: every value optional, blanks stay blank, and post-match statistics count from the day after the match.

## Leakage rules

- A match counts for a forecast only if it was played **before** the fixture's date. Matches on the same date are never used for each other.
- Elo: all matches on a date are rated from the ratings at the start of that date.
- Poisson and Dixon-Coles: refitted each match week from matches before that week's first fixture (a conservative cutoff), warm-started from the previous fit.
- Tuning happens on the validation period only. The Elo probability mapping and Dixon-Coles rho for the test period are refitted on data before the test period. Tests prove that changing every test-period result leaves all tuning output unchanged, and that changing results from a date onward leaves every earlier forecast unchanged.
- Settings searched on validation: Elo K, season regression and newcomer offset (8 combinations); Poisson half-life (1, 2, 4 years) and prior strength (6 combinations).
- Rolling-origin uses fixed default settings, so it is out-of-sample by construction.

## What a forecast contains

Per fixture and model: home, draw, away probabilities (sum to 1), over 2.5, both teams to score, expected goals, likeliest scorelines (Poisson and Dixon-Coles; Elo gives home/draw/away only), key drivers, the model version, the data fingerprint and the generation time. Drivers for Poisson models are the exact multiplicative pieces of expected goals (league level, attack, opponent defence, home advantage); for Elo, the rating gap.

**Reliability is four separate things, never one score**: the model probability; data completeness (how many of the 13 factor groups are available); historical calibration (from the latest backtest, or "unknown" if none); and prediction uncertainty (disagreement between models, and the fewest earlier matches for either club). Warnings cover clubs with fewer than five earlier matches, newly promoted clubs, a very large rating gap, unavailable factors, and manager or squad changes that cannot be detected.

**Reproducibility:** a stored forecast keeps the exact inputs of its model, so the same probabilities can be recomputed from them (tested). Live forecasts also store a frozen feature snapshot. Backtest forecasts store model inputs and drivers but not a full snapshot per fixture (that would be about 1,000 snapshots per run).

## Simulator

Only inputs the models really use can change: home advantage, attack and defence strength of each side, Elo rating points, and percentages you assume for players who are absent (not estimated from data). Rest days and lineups are shown disabled: the models were not trained with them. A scenario is always labelled hypothetical and is never saved as a forecast.

## Metrics reported

Per model and period: log loss, Brier score, accuracy, calibration gap and a reliability table (home/draw/away); by season; by market (over 2.5, both teams score: log loss and accuracy; correct score: mean log probability and likeliest-score hit rate); and the average log-loss gain over the frequency baseline and over Elo, with a standard error ("clear" only beyond two).

## Limits worth knowing

- Results-only models cannot see injuries, tactics, transfers or managers; their forecasts are estimates, not certainties, and nothing here is betting or financial advice.
- Rest days count league matches only, so they are overstated for clubs in cups or Europe.
- Live forecasts use the settings of the latest chronological backtest (tuned on validation, mapping refitted on training and validation); if no backtest exists they use untuned defaults and say so.
- A full backtest on ten seasons takes about 15 to 60 seconds and runs inside the request.
- Kick-off times are not in the data, only dates.
