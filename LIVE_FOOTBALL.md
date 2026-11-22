# Live football intelligence — Phases 4A and 4B (fixture ingestion, versioned forecasts)

Status: **built and tested against mocked provider responses. Not yet tested against the real football-data.org API** (no API key has been supplied). Live connectivity is not claimed until `scripts`-free check below passes.

## Provider assessment (football-data.org)

Read from the provider's pricing, coverage and policy pages (API-Football's pages refused automated access, so it was not assessed).

| Need | football-data.org |
|---|---|
| Premier League fixtures, kickoff, status, scores | Free tier (10 requests/min). **Schedules and scores are delayed on the free tier.** €12/month adds undelayed live scores (20/min). |
| Standings | Free tier ("league tables") |
| Lineups, squads, cards | Paid tier from €29/month (30/min) |
| Pre-match odds | €15/month add-on |
| Per-match statistics | €15/month add-on |
| Injuries and suspensions | **No feed found.** The injury factor stays "unavailable" and nothing is invented. |
| Licence for commercial use, storing and redistributing | **Not found.** Its terms page returned 404 and the policy page is silent. Get written confirmation from the provider (contact on its pricing page) before charging for live data. |

## What was built

| Piece | Where |
|---|---|
| Migration | `supabase/migrations/0017_live_fixtures.sql` extends `football_fixtures` (kickoff UTC, status, venue, matchday, provider, scores, last sync) and adds `football_fixture_provider_mappings`, `football_fixture_status_history`, `football_sync_jobs`, `football_provider_health`, `football_provider_cache` |
| Adapter | `stratiq/football_provider.py`: normalisation, retries with exponential backoff and a time budget, key scrubbing |
| Sync | `stratiq/football_sync.py`: shared cache, atomic per-minute rate limit, failure pause, one running job per workspace, idempotent upsert, freshness |
| API | `stratiq/football_live_api.py`: `GET /api/v1/football/live/provider`, `/fixtures`, `/fixtures/{id}/history`; `POST /sync` |
| Scheduler | the existing scheduled job runs a sync first when a key is configured; an outage is reported and never stops the rest of the cycle |

## Rules the code enforces

* The key lives only in `FOOTBALL_DATA_API_KEY` on the server, is sent only as a request header, and is scrubbed from every stored or returned message.
* One provider fixture id is one fixture. A rescheduled match is updated in place; an uploaded fixture for the same teams and day is adopted, never duplicated.
* Postponed, suspended and cancelled fixtures are stored and visible with their status, but every existing forecast, watchlist, briefing, analyst and SimLab query now excludes them. The forecasting job also skips fixtures that are not `scheduled` or whose kickoff has passed.
* A failed, rate-limited or malformed provider response writes nothing. Stored fixtures stay, and the API reports `last_verified_at` and `stale`.
* Scores are stored only for finished matches with a valid full-time score. Unknown statuses and untrustworthy rows are skipped and counted, not guessed.
* Kickoff is stored in UTC and returned in the caller's IANA time zone; "today" and "tomorrow" start at the caller's midnight.
* Window synchronised: 7 days back (so final statuses and scores arrive) to 30 days ahead, from one request per season.

## Configuration

* `FOOTBALL_DATA_API_KEY` (server only), optional `FOOTBALL_DATA_RATE_PER_MINUTE` (default 10, the free tier).
* A scheduler (existing `CRON_SECRET` endpoint) must call `/api/v1/football/jobs/scheduled`. Vercel Hobby cron runs at most daily; the six-hourly cycle needs a paid Vercel plan or an external caller. This is Phase 4E.

## Verifying real connectivity (owner)

1. Create a football-data.org account and put the key in Vercel as `FOOTBALL_DATA_API_KEY`.
2. In the app, press the sync endpoint (`POST /api/v1/football/live/sync`) as a member.
3. `GET /api/v1/football/live/provider` should show a recent `last_success_at` and zero failures, and `/fixtures?window=month` should list real fixtures. Between seasons the provider may legitimately return none.


## Phase 4B: automated, versioned pre-match forecasts

Code: `stratiq/football_forecast.py`, migration `0018_prediction_versions.sql` (dev only), endpoints in `football_live_api.py`.

* **Which model.** The production model is the calibrated ensemble when the latest backtest produced one, otherwise Dixon-Coles. Goal markets (expected goals, over/under 2.5, both teams to score, the five most likely scores) always come from Dixon-Coles and say so (`goal_model`). Without a backtest the settings are untuned defaults and every forecast carries that warning.
* **Outputs per version.** Home, draw and away probabilities (and display percentages that add up to exactly 100.0), expected goals, over/under 2.5, both teams to score, top five scorelines, drivers, data-quality warnings, data completeness out of the thirteen factors, provider references (provider fixture id, provider update time, last sync, results history date), the linked frozen feature snapshot and the exact model version.
* **Versioning.** Every change makes a new row; nothing is overwritten. A database trigger rejects any edit of a stored version except the official marker, and a check constraint rejects a version stamped at or after kickoff. A forecast whose inputs (data snapshot, model, kickoff time) are identical to the last one is not stored again.
* **Official forecast.** The latest version made before kickoff is marked official (one per fixture). It freezes at kickoff because nothing can be generated after it.
* **Information boundary.** Forecasts are made only for `scheduled` fixtures before kickoff, from results dated before today. A result dated today or later changes nothing.
* **No forecast without evidence.** A club that is not in the imported history, or has fewer than five earlier matches, or a postponed, cancelled, live or finished match, gets no forecast and a stated reason.
* **Scheduler.** The scheduled cycle syncs fixtures, then creates a first forecast for scheduled fixtures in the next 14 days that have none (at most 10 per run and 40 seconds, the rest wait for the next run). Refresh checkpoints (48h, 24h, 6h, 1h) and refresh-on-change are Phase 4E; the checkpoint labels already exist in the schema.
* **API.** `GET /api/v1/football/live/fixtures/{id}/forecast` (latest, official, why there is none), `/forecasts` (all versions), `POST .../forecast` (members; stores a version only if something changed). The fixtures list has a `forecast` summary and a `forecast=yes|no` filter.
* **Existing forecast tracking** (`football_predictions`, drift monitoring) still runs unchanged. Scoring the official version against the final result is Phase 4F.

## Phase 4C: Live Predictions dashboard

Route `/dashboard/sports/live` (sidebar: Live Predictions, directly under Sports; the sidebar now highlights only the most specific entry). Code in `src/components/dashboard/sports/live/`.

* **Tabs:** Today's matches, Upcoming fixtures (next 7 or 30 days), Match intelligence, Prediction history, Completed matches (last 30 days), and a Model performance link to the existing performance laboratory (`/dashboard/sports?tab=football`).
* **Filters:** competition (Premier League is the only supported one), date, team, match status, model, forecast availability. Team search treats `%` and `_` literally.
* **Time zone:** kickoffs are formatted in the chosen IANA zone (default: the browser's, remembered in local storage). "Today" and "tomorrow" on the server start at that zone's midnight.
* **Honesty:** the header says whether a provider key is configured and when the last successful fetch was. With no fixtures it says so and nothing is invented. A stale or failing provider shows a banner with the last verified time. Completed matches compare the result with the official pre-kickoff forecast as a plain comparison (not a stored score; scoring is Phase 4F) and say so when no forecast or no verified score exists.
* **Match intelligence:** overview, probabilities (with numbers beside the colours), expected goals, over/under 2.5, both teams to score, five likeliest scores, drivers, historical team comparison and head to head, player availability (reported unavailable, nothing assumed), data-quality warnings, version and provider references.
* **API added:** `window=recent`, `day=YYYY-MM-DD`, `status=completed`, `model`, `GET /football/live/forecast-history`, and a `snapshot` comparison in the forecast detail.
* **Not yet:** the dedicated match page (4D), live in-play updates (status only changes when fixtures are synchronised, and free-plan scores are delayed).

## Phase 4D: match intelligence page

Route `/dashboard/sports/football/matches/[fixtureId]` (the suggested public-style path `/sports/football/matches/[id]` redirects to it, and the dashboard enforces sign-in). Code: `stratiq/football_match.py`, `GET /api/v1/football/live/fixtures/{id}/match`, `MatchPage.tsx`.

* **Sections A to J:** overview, home/draw/away forecast, team form comparison (with each side's last five results), home and away performance, head-to-head (summary and the meetings themselves), expected goals and score distribution (a 6 by 6 table of scoreline chances rebuilt from the stored expected goals and the model's recorded dependence setting), player availability, key drivers with data-quality warnings, forecast revision history (every version plus fixture status and kickoff changes), and final result and evaluation.
* **Three labels on every section:** *Historical statistics* (computed from imported results dated before the forecast's cutoff), *Current verified information* (supplied by the provider or a dated upload) and *Model estimate*. A legend sits at the top of the page.
* **Availability:** reports are shown only from a dated upload that was already known (`available_at` not in the future); otherwise the page says none exists and assumes nothing.
* **Evaluation:** for a finished match with a verified score and an official forecast, the page shows the outcome, the probability the forecast gave it, log loss, Brier score, over 2.5, both teams to score and the exact score. These are arithmetic on stored values for one match, are not stored, and the page says one match says little about a model. With no official forecast or no verified score it says so instead.
* **Themes:** the application itself has only a dark theme (`color-scheme: dark`); there is no Light or System switch in this codebase, so none of this work can be checked in them. Adding themes would be its own piece of work.

## Phase 4E: scheduling and refresh

Code: `stratiq/football_refresh.py`, migration `0019_live_automation.sql` (dev only), `vercel.json`, `Automation.tsx`.

* **Architecture (checked, not assumed).** The Vercel team is on Pro. Vercel's cron documentation says Pro runs crons as often as once a minute with per-minute precision, Hobby only once a day (and may fire anywhere in the hour), cron sends `GET` with `Authorization: Bearer <CRON_SECRET>`, does not retry a failed run, can overlap runs, may rarely deliver a run twice, and uses normal function duration limits. So the design is a cheap, idempotent, overlap-safe **tick** every 10 minutes plus the existing heavy daily cycle at 04:00 UTC, both declared in `vercel.json`. They only take effect on the next deploy, and only exist once `CRON_SECRET` is set (it is **not** set in production today, nor is `FOOTBALL_DATA_API_KEY`). Nothing depends on a browser tab.
* **The tick** (`GET|POST /api/v1/football/jobs/tick`, scheduler secret only) visits each workspace with match history, within a 45-second budget, and does only what is due: fixture sync when the interval has passed (6 hours normally, 15 minutes within two hours before to three hours after a kickoff, never faster than the 10-minute shared cache, configurable by `FOOTBALL_SYNC_INTERVAL_MINUTES` and `FOOTBALL_LIVE_INTERVAL_MINUTES`; never retried within five minutes of an attempt); a re-forecast of any match whose kickoff moved; a first forecast for new fixtures; and checkpoint refreshes. Idle ticks cost one cheap query and record nothing.
* **Checkpoints** are configurable per workspace (1 to 8 values from 15 minutes to 10 days; defaults 48h, 24h, 6h, 1h) through `GET|PUT /api/v1/football/live/settings` and the Automation panel on the Live Predictions page. Each is claimed with a unique row per fixture, kickoff time and checkpoint, so repeated or overlapping runs cannot do it twice, a moved match gets its checkpoints again, a failed attempt is retried up to three times, and a dead run's claim is taken over after ten minutes. A late scheduler acts only on the closest checkpoint that has passed and marks earlier ones skipped. Nothing is generated at or after kickoff.
* **"Changed?"** A new version is stored only if the results used, the uploaded statistics used, the model version or the kickoff time changed. The calendar day deliberately does not count: otherwise every daily refresh would store a near-identical forecast.
* **Not available, and not faked:** lineup-triggered refresh (the provider plan supplies no lineups), and live in-play updates beyond fixture status (free-plan scores are delayed).
* **Observability:** one structured JSON log line per non-idle tick and per failure; non-idle ticks are recorded as `live` job runs; the schedule endpoint (`GET /api/v1/football/live/schedule`) shows each fixture's next refresh, the last run and whether a scheduler is configured.

## Phase 4F: result reconciliation and performance

Code: `stratiq/football_results.py`, `stratiq/football_performance.py`, migration `0020_result_reconciliation.sql` (dev only), the scheduled tick, `Record.tsx`.

* **What reconciliation does,** once per fixture and score, when the provider reports a fixture `finished` with a full-time score: records the score in `football_result_history`; adds the match to `match_history` (source `football-data.org`) so every later forecast, rating and the performance laboratory use it; scores the official pre-kickoff forecast in `football_prediction_evaluations` (log loss, Brier, ranked probability score, whether the likeliest result happened, over 2.5, both teams to score, exact score, goal error); feeds the same forecast and result into the existing tracking tables (`football_predictions` and outcomes) so drift monitoring and the laboratory see them; and refreshes the club registry. Ratings are recomputed from `match_history` at forecast time, so nothing separate is stored.
* **What it refuses to score:** scheduled, live, postponed, suspended and cancelled matches; "awarded" results (decided off the pitch, not played); finished matches with no verified score; and a result reported finished less than an hour after kickoff.
* **Idempotent.** One evaluation per forecast version; running again changes nothing. A fixture records the score it was last reconciled with, so only new or changed results are processed.
* **Corrections.** If the provider changes a score, the change is a new revision in the result history, the match is re-scored (same evaluation row, correction count up by one), `match_history` is updated, and the tracking tables are re-scored, not duplicated. If a different score for the same match is already stored from an upload, nothing is overwritten or scored; the fixture is flagged for a person. If the provider withdraws a result (the match is no longer finished) the evaluation is voided, the provider-sourced history row and tracking outcome are removed, and a later reinstatement scores it again.
* **No official forecast:** the result still reaches the match history, but nothing is scored.
* **Live record** (`GET /api/v1/football/live/performance`, shown on the Completed matches tab): overall and per-model scores, calibration of the home-win forecast, best and worst forecasts, and a comparison with a forecast of one third each (log loss ln 3 = 1.099, Brier 0.667; the ranked probability score of that forecast depends on the results, so it is compared per match). With fewer than 30 matches it says that very little can be concluded.
* **Reports.** A daily summary (last full UTC day) and a weekly report (last full Monday to Sunday) are created once, only if something was scored, by the scheduled tick (`GET /api/v1/football/live/performance/reports`). They are stored in-app; notification of them is Phase 4G.
* **Manual check:** `POST /api/v1/football/live/fixtures/{id}/reconcile` (members).
* **Not done:** a result reaching `match_history` does not itself force an immediate re-forecast of upcoming matches involving those clubs; they pick it up at their next checkpoint.

## Not included yet

Notifications (new fixtures, new predictions, significant probability changes, results, evaluations, provider failures, data-quality issues) with optional email and push adapters (4G); lineups, odds, injuries and advanced statistics from the provider.
