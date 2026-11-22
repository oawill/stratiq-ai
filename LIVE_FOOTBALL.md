# Live football intelligence — Phase 4A (provider and fixture ingestion)

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

## Not included yet

Automated pre-match predictions and refresh checkpoints (4B, 4E), the Live Predictions dashboard and match pages (4C, 4D), result reconciliation (4F), notifications, email and push (4G), lineups, odds, injuries and advanced statistics.
