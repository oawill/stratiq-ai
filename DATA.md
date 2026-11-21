# Bring your own data (Phase 6)

People upload CSV files; VELQORIN validates them, stores them privately in the workspace, and runs the existing models on them. **No data is supplied, scraped or licensed by VELQORIN**: uploads are the user's responsibility, and the Data page says so. Nothing is invented, repaired or imputed.

## What can be uploaded

| Kind | Columns | Used in |
|---|---|---|
| Sports results | `date, home_team, away_team, home_goals, away_goals` (aliases: `home`, `away`, `HomeTeam`, `AwayTeam`, `home_score`, `away_score`, `FTHG`, `FTAG`). Dates as `YYYY-MM-DD` or day-first `DD/MM/YYYY`. Files in the football-data.co.uk layout work as they are: up to 200 columns are accepted and only these five are used | **Sports, "Your data" tab**: team ratings are fitted on the uploaded matches and any pairing can be forecast |
| Market prices or returns | optional `date`, then one column per asset (up to 10); prices are converted to simple returns | **Markets, Historical returns**: "Use this data" fills the risk tool (VaR, expected shortfall, drawdown, backtest) |
| Party seats | `party, seats`, optional `position` (2 to 12 parties) | **Politics, Coalitions**: fills the party table (voting power, veto players, coalitions) |
| Numeric series | optional `date`, then up to 12 numeric columns | **SimLab**: "Fit to my data" on a variable fits a normal, lognormal or triangular distribution to a column |

Strategy (game theory) has no dataset type of its own: a series can inform the numbers you type into a payoff matrix, but payoffs are not fitted automatically.

## Validation

Every file is checked before it can be saved ("Check the file" shows a summary or a list of up to 20 line-numbered problems):
- size at most 2 MB, 20,000 rows, 12 columns; comma, semicolon or tab separated; a first row of unique column names
- dates in `YYYY-MM-DD` (sports files also accept day-first `DD/MM/YYYY` and `DD/MM/YY`, with a warning so a wrong guess is visible), strictly increasing for time series, and no future dates for match results
- every cell present and numeric where a number is expected (blank, `NaN` and infinity are rejected, never filled in)
- sports: whole-number goals 0 to 30, different home and away teams, at least 30 matches and 4 teams (teams with fewer than 5 matches are flagged); returns: at least 20 observations, no return of -100% or worse, prices above zero
- rows with the wrong number of values are rejected

The stored copy is the **validated, normalized content** (not the raw file) with a SHA-256 fingerprint. A forecast made from a dataset records the dataset id and fingerprint, so a saved forecast says exactly which data it came from. Saved forecasts are immutable, so deleting a dataset later does not change them.

## Fitting distributions (SimLab)

"Auto" picks lognormal for strictly positive, right-skewed data (skewness above 0.5) and normal otherwise; triangular uses the sample minimum, median and maximum. Parameters are matched to the sample's mean and standard deviation. The fit describes the past sample, not the future, and the interface says so; it is not a goodness-of-fit test. The fitted values appear in the variable's fields where they can be edited before running.

## Backtesting the Sports model (Phase 7)

Sports, "Your data", **Test on my data** (`POST /api/v1/data/datasets/{id}/backtest`) replays the most recent matches of an upload (up to 400, each with more than 100 earlier matches available, so a file needs at least 101 matches). Every match is predicted from **strictly earlier matches only**, then compared with the real result. Nothing is saved, and the same file always gives the same numbers.

It reports:
- **Log loss and Brier score**, for the model and for a baseline that only knows the earlier home, draw and away rates (Laplace-smoothed). Lower is better. The baseline is the bar the model has to clear to be adding anything.
- **Right result called**: how often the most likely outcome happened, for the model and the baseline.
- **A paired log-loss gain with one standard error.** The page says "clearly better" only when the gain is more than two standard errors above zero; a smaller positive gap is shown as unproven, and a negative one as "adds nothing". Hundreds of matches can only reveal large differences, and the page says that.
- **A reliability table**: for each probability band, the average chance the model gave and how often it happened.

Limits: it tests the model on that file, not on other leagues or future seasons; there is no tuning, so numbers are not inflated by fitting the test; it does not compare against betting markets, and it is not betting or financial advice. For reference, the existing seeded development data is simulated from the model's own assumptions, so its backtest only checks the code, while on one uploaded real Premier League season (380 matches, 280 scored) the model beat the baseline on log loss (1.064 against 1.102) and called 45% of results against 40%, but by a gain of 0.039 ± 0.023, under two standard errors, so it is unproven, and it was overconfident in the 60-80% band (said about 67%, happened 49%). One season cannot settle it.

## Historical football data (Premier League)

The Data page has a **Historical Football Data** section for ten seasons of English Premier League results. **VELQORIN does not download data from any provider.** The preferred public archive, football-data.co.uk, states that its data is for private individuals only and not for commercial products or automated bots, scrapers or AI, and VELQORIN has paid plans, so a server fetching and re-serving those files would go against that. People import files they are entitled to use (one file per season, or one combined file) and the provider's own terms apply to them. Moving to a licensed API later only needs a new source feeding the same `read_source` validation.

**Import** (`POST /api/v1/football/import`, Members and above; "Check only" validates without saving): reads the football-data layout (`Date, HomeTeam, AwayTeam, FTHG, FTAG`, other columns ignored, day-first dates) or the five-column format. Full-time scores only; half-time columns are never used. Each row is accepted or rejected on its own with a line number and reason, and the report always gives exact counts:
- **accepted** (new or already stored), **rejected**, **duplicate** (the same fixture repeated with the same score, dropped), **conflicting** (the same fixture with different scores, in the file or against what is stored: neither is accepted and nothing is overwritten), **missing** (fixtures a season lacks), and **not yet played** (future-dated rows, skipped).
- Dates must be valid and not in the future; goals whole numbers 0 to 30; a past-dated row with no score is rejected, not filled in; a `Div` column other than `E0` is rejected; a row from another season than the file's is rejected (tick "Combined file" for multi-season files).
- Club names go through one dictionary (`stratiq/football_teams.py`) covering all 34 clubs of 2016/17 to 2025/26. An unknown name is kept exactly as written with a warning, never guessed or merged, so a new club or a new spelling shows up in the report (and as an incomplete season) instead of silently becoming a different team. New clubs need adding to the dictionary.
- Importing is idempotent: stored rows are unique on workspace, competition, season, date, home and away, so repeating a file adds nothing. To correct a score, remove the season (admins and owners) and import the corrected file.
- Limits: 2 MB and 20,000 rows per file, at most 200 columns in a source file, and 20,000 stored matches per workspace.

**Seasons are only called complete when every check passes:** 20 clubs, 380 matches, 38 for every club (19 home, 19 away), every pair meeting once at each ground, no repeated fixtures, and all dates inside the season (a season runs from August to the following July; 2019/20 finished on 26 July 2020). The season in progress (2026/27 today) is shown as "In progress" and is left out of the completeness checks. The report names missing fixtures and flags clubs with the wrong number of matches, which is how a misspelt club shows up.

**Use it:** download the five-column CSV (`date,home_team,away_team,home_goals,away_goals`, oldest first, about 170 KB for ten seasons), view and filter matches, read the validation report, or "Create dataset" to save the history as a normal sports dataset that the Sports "Your data" tab can forecast and backtest. Season and source stay in the database (`match_history`, migration `0009_match_history.sql`) and are not in the export.

**Prediction features** (`stratiq/football_features.py`, endpoints `team`, `fixture`, `evaluation`): win/draw/loss rates, home and away splits, goals for and against, average goals, clean-sheet rate, rolling 5- and 10-match form, head to head, an Elo-style rating (K 20, home advantage 65 points, goal-difference multiplier), attack and defence strength, and Poisson score probabilities. Goal rates are estimated from results and are labelled as such; they are not provider expected goals. Every figure takes a date and uses only matches played strictly before it. `evaluation` splits matches by time (first 60% to learn from, next 20% validation, last 20% test), scores the model on the last two against the base-rate baseline, and reports log loss, Brier score, hit rate and a reliability table. Nothing is tuned on either period.

Football forecasting on top of this history (Elo, Poisson, Dixon-Coles, backtesting, dashboard) is described in `FOOTBALL.md`. Future-dated rows in a results file are stored as upcoming fixtures, and a new dataset type, **Football advanced statistics** (`date, home_team, away_team` plus any of `home_xg, away_xg, home_shots, away_shots, home_shots_on_target, away_shots_on_target, home_corners, away_corners, odds_home, odds_draw, odds_away`), carries expected goals and odds. The sports results type is now labelled "Football match results".

Not built: scheduled or automated synchronization (there is nothing to fetch), other competitions, and provider expected-goals data. The current season is kept up to date by importing its newer file again.

## Plans and permissions

- Members and above can upload; viewers can read and use datasets but not add them; the uploader, admins and the owner can delete.
- Datasets are private to the workspace and visible to everyone in it. Uploads appear in the activity feed and the audit log.
- Plan limits (enforced only when `BILLING_ENFORCED=1`): Explorer 1 dataset, Sports Pro 3, Strategy Pro 20.

## Limits worth knowing

- Sports ratings use only past scores (the existing Poisson model). Its accuracy is measured per upload by the backtest below, never assumed; a good result on one file says nothing about other leagues or future seasons.
- Market analysis is on past returns of what was uploaded. It says nothing about the future and is not investment advice.
- Data is stored as JSON in Postgres, which is fine at this size but not meant for large time series.
- There is no live data feed and no scheduled refresh; re-upload to update.
- Datasets cannot be edited, only replaced (upload again and delete the old one).

## Database

Migration `0008_datasets.sql` adds the `datasets` table (applied to production). Migration `0009_match_history.sql` adds `match_history` and `match_imports` (applied to production). Migration `0010_football_intelligence.sql` adds the football intelligence tables and allows the `football_stats` dataset kind; it is additive and applied to the development database only. **Apply it to production before using Football intelligence there** (`node scripts/migrate.mjs` with production credentials).
