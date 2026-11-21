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

## Plans and permissions

- Members and above can upload; viewers can read and use datasets but not add them; the uploader, admins and the owner can delete.
- Datasets are private to the workspace and visible to everyone in it. Uploads appear in the activity feed and the audit log.
- Plan limits (enforced only when `BILLING_ENFORCED=1`): Explorer 1 dataset, Sports Pro 3, Strategy Pro 20.

## Limits worth knowing

- Sports ratings use only past scores (the existing Poisson model). Its accuracy on a user's league is **not measured**, and the page says so; backtesting on uploaded data is not built.
- Market analysis is on past returns of what was uploaded. It says nothing about the future and is not investment advice.
- Data is stored as JSON in Postgres, which is fine at this size but not meant for large time series.
- There is no live data feed and no scheduled refresh; re-upload to update.
- Datasets cannot be edited, only replaced (upload again and delete the old one).

## Database

Migration `0008_datasets.sql` adds the `datasets` table. It is additive and applied to the development database; **apply it to production before using the Data page there** (`node scripts/migrate.mjs` with production credentials).
