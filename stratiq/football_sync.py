"""Fixture synchronisation: provider health, shared response cache, rate limiting, one-job-at-a-time locking, and the idempotent upsert.

Rules this module enforces:
  * A failed or partial provider response never changes stored fixtures. Rows are written only after a complete, valid response.
  * One provider fixture id is one fixture. A rescheduled match is updated in place; an uploaded fixture for the same teams and day is adopted, not duplicated.
  * A change of status or kickoff time is recorded in `football_fixture_status_history`. A re-run with nothing new changes nothing.
  * Provider health, the cache and the request window are shared by every workspace, so many workspaces cost one request.
  * Nothing is invented: when the provider is down, stored fixtures stay and are reported with `last_verified_at` and a stale flag.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from . import football_notify as notify
from . import football_provider as fp
from .football_history import season_label

PAST_DAYS = 7                 # recently played fixtures are refreshed so final statuses and scores arrive
WINDOW_DAYS = 30
CACHE_TTL = timedelta(minutes=10)
STALE_AFTER = timedelta(hours=12)
STALE_JOB_AFTER = timedelta(minutes=10)    # a "running" job older than this died without finishing
PAUSE_AFTER_FAILURES = 3
PAUSE_FOR = timedelta(minutes=5)
MIN_MANUAL_INTERVAL = timedelta(minutes=5)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---- provider health, cache, rate limit --------------------------------------------------------------------------------------------

def health(conn, provider: str = fp.PROVIDER) -> dict:
    r = conn.execute("select * from football_provider_health where provider=%s", (provider,)).fetchone()
    return r or {"provider": provider, "last_success_at": None, "last_failure_at": None, "consecutive_failures": 0, "last_error": None, "paused_until": None}


def record_success(conn, provider: str, now: datetime) -> None:
    conn.execute("""insert into football_provider_health (provider, last_success_at, consecutive_failures, last_error, paused_until, updated_at) values (%s,%s,0,null,null,%s)
                    on conflict (provider) do update set last_success_at=excluded.last_success_at, consecutive_failures=0, last_error=null, paused_until=null, updated_at=excluded.updated_at""",
                 (provider, now, now))


def record_failure(conn, provider: str, message: str, now: datetime) -> None:
    conn.execute("""insert into football_provider_health (provider, last_failure_at, consecutive_failures, last_error, updated_at) values (%s,%s,1,%s,%s)
                    on conflict (provider) do update set last_failure_at=excluded.last_failure_at, consecutive_failures=football_provider_health.consecutive_failures+1,
                      last_error=excluded.last_error, updated_at=excluded.updated_at,
                      paused_until=case when football_provider_health.consecutive_failures+1 >= %s then %s else football_provider_health.paused_until end""",
                 (provider, now, fp.scrub(message), now, PAUSE_AFTER_FAILURES, now + PAUSE_FOR))


def take_request_slot(conn, provider: str, now: datetime, limit: int) -> bool:
    """Atomically count one request in the current one-minute window across all server instances. False when the window is full."""
    conn.execute("insert into football_provider_health (provider) values (%s) on conflict do nothing", (provider,))
    r = conn.execute("""update football_provider_health set
                          window_count = case when window_start is null or window_start <= %s - interval '60 seconds' then 1 else window_count + 1 end,
                          window_start = case when window_start is null or window_start <= %s - interval '60 seconds' then %s else window_start end
                        where provider=%s and (window_start is null or window_start <= %s - interval '60 seconds' or window_count < %s) returning window_count""",
                     (now, now, now, provider, now, limit)).fetchone()
    return r is not None


def cache_get(conn, provider: str, key: str, now: datetime, allow_stale: bool = False):
    r = conn.execute("select body, fetched_at, expires_at from football_provider_cache where provider=%s and cache_key=%s", (provider, key)).fetchone()
    if not r or (not allow_stale and r["expires_at"] <= now):
        return None
    return r


def cache_put(conn, provider: str, key: str, body, now: datetime) -> None:
    conn.execute("""insert into football_provider_cache (provider, cache_key, body, fetched_at, expires_at) values (%s,%s,%s,%s,%s)
                    on conflict (provider, cache_key) do update set body=excluded.body, fetched_at=excluded.fetched_at, expires_at=excluded.expires_at""",
                 (provider, key, json.dumps(body), now, now + CACHE_TTL))


def fetch_season(conn, adapter: fp.FootballDataOrg, competition: str, year: int, now: datetime) -> tuple[list[dict], datetime]:
    """Matches for one season: from the shared cache when fresh, otherwise from the provider (rate limited, health recorded). Returns (matches, fetched_at)."""
    key = f"{competition}:{year}:matches"
    hit = cache_get(conn, fp.PROVIDER, key, now)
    if hit:
        return hit["body"], hit["fetched_at"]
    h = health(conn)
    if h["paused_until"] and h["paused_until"] > now:
        raise fp.ProviderError("The provider has failed several times in a row, so requests are paused briefly before trying again.", retryable=True)
    if not take_request_slot(conn, fp.PROVIDER, now, fp.per_minute_limit()):
        raise fp.ProviderError("The provider's request limit for this minute has been used. Try again shortly.", retryable=True)
    try:
        ms = adapter.season_matches(competition, year)
    except fp.ProviderError as e:
        if not isinstance(e, fp.NotConfigured):
            record_failure(conn, fp.PROVIDER, str(e), now)
        raise
    record_success(conn, fp.PROVIDER, now)
    cache_put(conn, fp.PROVIDER, key, ms, now)
    return ms, now


# ---- jobs --------------------------------------------------------------------------------------------------------------------------

def start_job(conn, workspace_id: str, trigger: str, frm: date, to: date, now: datetime) -> str | None:
    """None when another job is already running for this workspace. A running job older than STALE_JOB_AFTER is treated as dead and closed."""
    conn.execute("update football_sync_jobs set status='failed', error='Interrupted: the job did not finish.', finished_at=%s where workspace_id=%s and provider=%s and status='running' and started_at < %s",
                 (now, workspace_id, fp.PROVIDER, now - STALE_JOB_AFTER))
    r = conn.execute("""insert into football_sync_jobs (workspace_id, provider, trigger, window_from, window_to, started_at) values (%s,%s,%s,%s,%s,%s)
                        on conflict (workspace_id, provider) where status='running' do nothing returning id""", (workspace_id, fp.PROVIDER, trigger, frm, to, now)).fetchone()
    return str(r["id"]) if r else None


def finish_job(conn, job_id: str, status: str, counts: dict, detail: dict, error: str | None, now: datetime) -> None:
    conn.execute("""update football_sync_jobs set status=%s, fetched=%s, created=%s, updated=%s, unchanged=%s, skipped=%s, detail=%s, error=%s, finished_at=%s where id=%s""",
                 (status, counts["fetched"], counts["created"], counts["updated"], counts["unchanged"], counts["skipped"], json.dumps(detail, default=str), fp.scrub(error) if error else None, now, job_id))


# ---- the upsert --------------------------------------------------------------------------------------------------------------------

def _find(conn, wid: str, f: fp.Fixture):
    r = conn.execute("""select f.* from football_fixtures f join football_fixture_provider_mappings m on m.fixture_id=f.id
                        where m.workspace_id=%s and m.provider=%s and m.provider_fixture_id=%s""", (wid, fp.PROVIDER, f.provider_fixture_id)).fetchone()
    if r:
        return r, True
    # an uploaded fixture for the same teams on the same day is the same match: adopt it instead of adding a second one
    r = conn.execute("""select f.* from football_fixtures f where f.workspace_id=%s and f.competition=%s and f.fixture_date=%s and f.home_team=%s and f.away_team=%s
                        and not exists (select 1 from football_fixture_provider_mappings m where m.fixture_id=f.id and m.provider=%s)""",
                     (wid, f.competition, f.local_date, f.home, f.away, fp.PROVIDER)).fetchone()
    return r, False


def _differs(row, f: fp.Fixture) -> bool:
    return (row["kickoff_utc"] != f.kickoff_utc or row["status"] != f.status or row["fixture_date"] != f.local_date or row["home_team"] != f.home or row["away_team"] != f.away
            or row["home_goals"] != f.home_goals or row["away_goals"] != f.away_goals or row["venue"] != f.venue or row["matchday"] != f.matchday)


def upsert_fixture(conn, wid: str, f: fp.Fixture, job_id: str, now: datetime) -> str:
    """'created', 'updated' or 'unchanged'."""
    row, mapped = _find(conn, wid, f)
    if row is None:
        r = conn.execute("""insert into football_fixtures (workspace_id, competition, season, fixture_date, home_team, away_team, kickoff_utc, status, venue, matchday, provider,
                                provider_updated_at, last_synced_at, home_goals, away_goals) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                         (wid, f.competition, f.season, f.local_date, f.home, f.away, f.kickoff_utc, f.status, f.venue, f.matchday, fp.PROVIDER, f.provider_updated_at, now, f.home_goals, f.away_goals)).fetchone()
        fid = r["id"]
        conn.execute("insert into football_fixture_provider_mappings (workspace_id, fixture_id, provider, provider_fixture_id, raw_home, raw_away) values (%s,%s,%s,%s,%s,%s)",
                     (wid, fid, fp.PROVIDER, f.provider_fixture_id, f.raw_home, f.raw_away))
        conn.execute("insert into football_fixture_status_history (workspace_id, fixture_id, old_status, new_status, new_kickoff, sync_job_id, observed_at) values (%s,%s,null,%s,%s,%s,%s)",
                     (wid, fid, f.status, f.kickoff_utc, job_id, now))
        return "created"
    fid = row["id"]
    if not mapped:
        conn.execute("insert into football_fixture_provider_mappings (workspace_id, fixture_id, provider, provider_fixture_id, raw_home, raw_away) values (%s,%s,%s,%s,%s,%s)",
                     (wid, fid, fp.PROVIDER, f.provider_fixture_id, f.raw_home, f.raw_away))
    if not mapped or _differs(row, f):
        changed_kick = row["kickoff_utc"] != f.kickoff_utc
        if row["status"] != f.status or changed_kick:
            conn.execute("insert into football_fixture_status_history (workspace_id, fixture_id, old_status, new_status, old_kickoff, new_kickoff, sync_job_id, observed_at) values (%s,%s,%s,%s,%s,%s,%s,%s)",
                         (wid, fid, row["status"], f.status, row["kickoff_utc"], f.kickoff_utc, job_id, now))
        conn.execute("""update football_fixtures set season=%s, fixture_date=%s, home_team=%s, away_team=%s, kickoff_utc=%s, status=%s, venue=%s, matchday=%s, provider=%s,
                            provider_updated_at=%s, last_synced_at=%s, home_goals=%s, away_goals=%s where id=%s""",
                     (f.season, f.local_date, f.home, f.away, f.kickoff_utc, f.status, f.venue, f.matchday, fp.PROVIDER, f.provider_updated_at, now, f.home_goals, f.away_goals, fid))
        return "updated"
    conn.execute("update football_fixtures set last_synced_at=%s, provider_updated_at=%s where id=%s", (now, f.provider_updated_at, fid))
    return "unchanged"


def sync_workspace(conn, workspace_id: str, trigger: str = "manual", competition: str = "EPL", adapter: fp.FootballDataOrg | None = None, now: datetime | None = None) -> dict:
    """Fetch the seasons covering [today - 7 days, today + 30 days] and upsert them. Never raises for provider trouble: the outcome is in the result and the job row."""
    now = now or utcnow()
    today = now.date()
    frm, to = today - timedelta(days=PAST_DAYS), today + timedelta(days=WINDOW_DAYS)
    if not fp.configured() and adapter is None:
        return {"status": "not_configured", "message": "No football-data.org key is configured on the server, so no fixtures can be fetched. Uploaded fixtures still work.", "window": [str(frm), str(to)]}
    job = start_job(conn, workspace_id, trigger, frm, to, now)
    if job is None:
        return {"status": "already_running", "message": "A synchronisation is already running for this workspace.", "window": [str(frm), str(to)]}
    adapter = adapter or fp.FootballDataOrg()
    counts = {"fetched": 0, "created": 0, "updated": 0, "unchanged": 0, "skipped": 0}
    warnings: list[str] = []
    years = sorted({fp.season_start_year(frm), fp.season_start_year(to)})
    try:
        matches, fetched_at = [], now
        for y in years:                                   # all requests first: nothing is written unless every one succeeded
            ms, at = fetch_season(conn, adapter, competition, y, now)
            matches += ms
            fetched_at = min(fetched_at, at)
        seen: set[str] = set()
        for m in matches:
            f = fp.normalise_match(m, competition)
            if f is None:
                counts["skipped"] += 1
                continue
            if not (frm <= f.kickoff_utc.date() <= to) or f.provider_fixture_id in seen:
                continue
            seen.add(f.provider_fixture_id)
            counts["fetched"] += 1
            warnings += f.warnings
            counts[upsert_fixture(conn, workspace_id, f, job, now)] += 1
    except fp.ProviderError as e:
        finish_job(conn, job, "failed", counts, {"warnings": warnings[:20]}, str(e), now)
        h = health(conn)
        if h["consecutive_failures"] >= PAUSE_AFTER_FAILURES:
            with notify.guard(conn, "provider_failing"):
                notify.provider_failing(conn, workspace_id, h["consecutive_failures"], h["last_success_at"], fp.scrub(str(e)), now)
        return {"status": "failed", "message": fp.scrub(str(e)), "retryable": e.retryable, "window": [str(frm), str(to)], **counts, "job_id": job}
    finish_job(conn, job, "complete", counts, {"warnings": sorted(set(warnings))[:20], "seasons": years, "data_fetched_at": fetched_at.isoformat()}, None, now)
    with notify.guard(conn, "sync_events"):
        fresh = conn.execute("""select f.id, f.home_team, f.away_team, f.fixture_date from football_fixture_status_history h join football_fixtures f on f.id=h.fixture_id
                                where h.sync_job_id=%s and h.old_status is null and f.status='scheduled' and f.kickoff_utc > %s order by f.kickoff_utc""", (job, now)).fetchall()
        notify.new_fixtures(conn, workspace_id, fresh, job, now)
        names = sorted({w.split(": ", 1)[1] for w in warnings if w.startswith("Unrecognised club name: ")})
        if names:
            notify.data_issue(conn, workspace_id, "unknown_clubs:" + ",".join(names)[:200], "Club names not recognised",
                              f"The fixture provider used names that are not in the club dictionary: {', '.join(names)}. Those fixtures cannot be forecast until the names are mapped.", now=now)
    return {"status": "complete", "window": [str(frm), str(to)], **counts, "warnings": sorted(set(warnings))[:20], "data_fetched_at": fetched_at, "job_id": job,
            "note": None if counts["fetched"] else "The provider returned no fixtures in this window (for example between seasons)."}


def freshness(conn, workspace_id: str, now: datetime | None = None) -> dict:
    """When this workspace's provider fixtures were last verified, and whether that is too old to treat as current."""
    now = now or utcnow()
    r = conn.execute("select max(finished_at) t from football_sync_jobs where workspace_id=%s and provider=%s and status='complete'", (workspace_id, fp.PROVIDER)).fetchone()
    last = r["t"] if r else None
    h = health(conn)
    failing = h["consecutive_failures"] > 0 and (h["last_success_at"] is None or (h["last_failure_at"] and h["last_failure_at"] > h["last_success_at"]))
    stale = last is None or now - last > STALE_AFTER or bool(failing)
    return {"last_verified_at": last, "stale": stale, "provider_failing": bool(failing), "last_error": h["last_error"] if failing else None,
            "message": ("Fixtures have never been fetched from the provider." if last is None else
                        ("The provider is failing; showing the last verified fixtures." if failing else ("These fixtures have not been refreshed recently." if stale else None)))}


def recently_synced(conn, workspace_id: str, now: datetime) -> bool:
    r = conn.execute("select 1 from football_sync_jobs where workspace_id=%s and provider=%s and status='complete' and finished_at > %s limit 1", (workspace_id, fp.PROVIDER, now - MIN_MANUAL_INTERVAL)).fetchone()
    return r is not None


def season_of(d: date) -> str:
    return season_label(d)
