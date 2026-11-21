# Football prediction intelligence (Phases 9 and 10)

Forecasts for Premier League fixtures from three statistical models, a boosted-tree model and a calibrated ensemble, with leak-free backtesting, a reliability breakdown, a what-if simulator and tracked outcomes. It lives in **Sports, "Football intelligence"**, on top of the history imported in **Data, Historical Football Data** (see `DATA.md`).

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
| Model D: boosted trees (pure Python, multiclass softmax, `stratiq/football_gbm.py`) | Built (Phase 10). Leak-free features from results only; depth and number of rounds chosen on validation; final trees refitted on training + validation. |
| Model E: calibrated ensemble (`stratiq/football_ensemble.py`) | Built (Phase 10). Weighted average of Elo, Dixon-Coles and the boosted trees, weights and one temperature fitted on validation only. |
| Drift monitoring, retraining policy, scheduled cycle (`football_monitor.py`, `football_jobs.py`, `football_jobs_api.py`) | Built (Phase 10), but **no schedule is switched on**: see "Automation" below. |
| Player availability, squad strength, manager changes, weather and travel | **Not built.** They have no data source, so they read "unavailable" in every forecast. The `football_player_availability` table exists but nothing writes to it. |

## Boosted trees and the ensemble (Phase 10)

**Boosted trees.** Each round fits one depth-2 or depth-3 regression tree per outcome (home, draw, away) to the gradient of the log loss, with learning rate 0.08, an L2 penalty on leaf values, at least 25 matches per leaf, 60% row and 70% feature subsampling from a seeded generator (so the same data always gives the same model), and histogram split search over 12 quantile bins. Training stops adding rounds once validation log loss has not improved for 8 rounds. Features, all computed from matches before the fixture date: Elo rating gap, last-5 points per game and last-10 goals for and against for both clubs, home-only and away-only form, rest days, and two difference features. It does not use injuries, odds or expected goals, and it does not forecast goals, over 2.5 or both-teams-to-score (those come from the Poisson-family models).

**Ensemble.** Linear pool of Elo, Dixon-Coles and the boosted trees. The weights (multiples of 0.1) are the combination with the lowest validation log loss; then one temperature is fitted to correct over- or under-confidence. That is three numbers fitted on one season of matches, so the ensemble is only worth trusting if it also beats its members on the **test** period, and the performance tab reports exactly that (gain over Dixon-Coles, with a standard error). On the synthetic test data the ensemble collapses to a calibrated Elo because the data was generated that way; that says nothing about real football.

**What-if scenarios** change the Poisson inputs only, so the boosted trees and ensemble are not shown in a scenario.

## Monitoring and retraining

- **Drift** compares the last 60 tracked live forecasts that now have results with the backtest test period: log-loss z-score (using the test period's own spread) and home-win predicted-versus-actual. "Drifting" needs z of at least 3 **and** a log loss at least 0.03 worse; with fewer than 30 scored forecasts the status is "not enough results yet" and nothing is claimed.
- **Retraining is due** when there is no backtest, drift is flagged, 100 or more matches have been added since training, or the models are 90 days old with at least 20 new matches.
- **A retrain** runs a chronological backtest with the newest three seasons as validation and test (so the split moves forward as seasons are added). Its results replace the live models only if its validation log loss is not more than 0.005 worse than the previous run's; otherwise the run is kept for review with status `rejected` and the previous one stays live. The two validation periods differ, so this is a guard against a broken refit, not a like-for-like contest.

## Automation

Nothing runs by itself. The pieces are there:

- `POST /api/v1/football/jobs/monitor` and `/retrain` (signed-in users with write access), and `GET /api/v1/football/jobs/status`; the **Model operations** tab uses them.
- `GET|POST /api/v1/football/jobs/scheduled` runs one cycle for every workspace with match history: score finished forecasts, store a tracked forecast for each fixture in the next 14 days, check drift, retrain if due (at most one workspace per call, because a retrain takes tens of seconds). It exists only when the `CRON_SECRET` environment variable (16+ characters) is set, and requires `Authorization: Bearer <CRON_SECRET>`.
- To switch it on, set `CRON_SECRET` in the Vercel project and add a cron entry to `vercel.json`, for example `"crons": [{ "path": "/api/v1/football/jobs/scheduled", "schedule": "0 6 * * *" }]`. This was deliberately not added: it changes deployment configuration. A retrain can approach the 60-second function limit on ten seasons; on a long-lived host run the same cycle with a cron job that calls the endpoint.
- Every run is recorded in `football_job_runs` (migration `0011_football_jobs.sql`).

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
- A full backtest on ten seasons takes about 15 to 60 seconds and runs inside the request. The rolling-origin backtest covers the four statistical models only; the boosted trees and ensemble are in the chronological backtest.
- Kick-off times are not in the data, only dates.
