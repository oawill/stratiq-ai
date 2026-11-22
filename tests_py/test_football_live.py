"""Phase 4A: live fixture ingestion. Every provider response here is MOCKED (httpx.MockTransport); no network is used.
Real connectivity to football-data.org is checked separately and is not claimed by these tests."""
from datetime import datetime, timedelta, timezone

import httpx
import psycopg
import pytest

from stratiq import football_provider as fp
from stratiq import football_sync as sync

from .conftest import hdr, make_user

KEY = "k" * 32
RealAdapter = fp.FootballDataOrg          # tests replace fp.FootballDataOrg, so keep the real class for building mocked adapters
NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)


def match(mid, home="Arsenal FC", away="Chelsea FC", kick=None, status="TIMED", hg=None, ag=None, **extra):
    kick = kick or (NOW + timedelta(days=2)).replace(hour=15, minute=0)
    m = {"id": mid, "utcDate": kick.strftime("%Y-%m-%dT%H:%M:%SZ"), "status": status, "matchday": 12, "homeTeam": {"name": home}, "awayTeam": {"name": away},
         "score": {"fullTime": {"home": hg, "away": ag}}, "lastUpdated": "2026-11-22T10:00:00Z"}
    m.update(extra)
    return m


class Provider:
    """A scripted football-data.org: returns `matches` for any season request, or the queued failures first."""

    def __init__(self, matches=(), failures=()):
        self.matches, self.failures, self.calls, self.headers = list(matches), list(failures), 0, []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        self.headers.append(request.headers.get("x-auth-token"))
        if self.failures:
            f = self.failures.pop(0)
            return f if isinstance(f, httpx.Response) else (_ for _ in ()).throw(f)
        return httpx.Response(200, json={"matches": self.matches})

    def adapter(self, sleeps=None):
        return RealAdapter(KEY, httpx.Client(transport=httpx.MockTransport(self.handler)), sleep=(sleeps.append if sleeps is not None else (lambda s: None)), jitter=lambda: 0.0)


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_API_KEY", KEY)
    monkeypatch.setenv("FOOTBALL_DATA_RATE_PER_MINUTE", "10")


@pytest.fixture()
def ws(conn):
    uid, wid = make_user(conn)
    return uid, wid


def run(conn, wid, provider, now=NOW, **kw):
    return sync.sync_workspace(conn, wid, adapter=provider.adapter(), now=now, **kw)


def rows(conn, wid):
    return conn.execute("select * from football_fixtures where workspace_id=%s order by kickoff_utc, home_team", (wid,)).fetchall()


# ---- normalisation ------------------------------------------------------------------------------------------------------------------

def test_normalisation_maps_provider_names_status_and_season():
    f = fp.normalise_match(match(1, "Brighton & Hove Albion FC", "Manchester United FC", NOW + timedelta(days=1)))
    assert (f.home, f.away) == ("Brighton & Hove Albion", "Manchester United") and f.status == "scheduled" and f.season == "2026/27" and f.provider_fixture_id == "1"
    assert f.warnings == [] and f.home_goals is None


def test_unknown_club_is_kept_as_written_with_a_warning():
    f = fp.normalise_match(match(2, "Brand New Town FC"))
    assert f.home == "Brand New Town" and any("Brand New Town" in w for w in f.warnings)


@pytest.mark.parametrize("raw,ours", [("SCHEDULED", "scheduled"), ("TIMED", "scheduled"), ("IN_PLAY", "in_play"), ("PAUSED", "paused"), ("FINISHED", "finished"), ("POSTPONED", "postponed"),
                                      ("SUSPENDED", "suspended"), ("CANCELLED", "cancelled"), ("CANCELED", "cancelled"), ("AWARDED", "awarded")])
def test_every_provider_status_maps(raw, ours):
    assert fp.normalise_match(match(3, status=raw, hg=1, ag=0)).status == ours


@pytest.mark.parametrize("bad", [{"id": None}, {"status": "MYSTERY"}, {"utcDate": "not a date"}, {"homeTeam": {"name": ""}}, {"awayTeam": {"name": "Arsenal FC"}}])
def test_untrustworthy_matches_are_rejected_not_guessed(bad):
    assert fp.normalise_match(match(4, **bad)) is None


def test_scores_only_for_finished_matches_with_a_valid_full_time_score():
    assert fp.normalise_match(match(5, status="FINISHED", hg=2, ag=1)).home_goals == 2
    assert fp.normalise_match(match(6, status="TIMED", hg=2, ag=1)).home_goals is None            # a score on an unfinished match is ignored
    f = fp.normalise_match(match(7, status="FINISHED", hg=None, ag=None))
    assert f.home_goals is None and any("full-time score" in w for w in f.warnings)
    assert fp.normalise_match(match(8, status="FINISHED", hg=-1, ag=2)).home_goals is None


# ---- adapter: key handling, retries, backoff ----------------------------------------------------------------------------------------

def test_key_is_sent_only_as_a_header_and_never_appears_in_errors():
    p = Provider(failures=[httpx.Response(403, text=f"forbidden {KEY}")])
    with pytest.raises(fp.ProviderError) as e:
        p.adapter().season_matches("EPL", 2026)
    assert p.headers == [KEY] and KEY not in str(e.value) and not e.value.retryable
    assert KEY not in fp.scrub(f"X-Auth-Token: {KEY} and {KEY}")


def test_missing_key_is_reported_not_sent():
    with pytest.raises(fp.NotConfigured):
        fp.FootballDataOrg("", httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))).season_matches("EPL", 2026)


def test_server_errors_are_retried_with_exponential_backoff_then_succeed():
    sleeps = []
    p = Provider([match(1)], failures=[httpx.Response(503), httpx.Response(500)])
    assert len(p.adapter(sleeps).season_matches("EPL", 2026)) == 1
    assert p.calls == 3 and sleeps == [1.0, 2.0]


def test_network_errors_are_retried_and_give_up_after_three_attempts():
    sleeps = []
    p = Provider(failures=[httpx.ConnectError("boom")] * 3)
    with pytest.raises(fp.ProviderError) as e:
        p.adapter(sleeps).season_matches("EPL", 2026)
    assert p.calls == 3 and e.value.retryable and len(sleeps) == 2


def test_rate_limit_response_honours_retry_after():
    sleeps = []
    p = Provider([match(1)], failures=[httpx.Response(429, headers={"retry-after": "7"})])
    p.adapter(sleeps).season_matches("EPL", 2026)
    assert sleeps == [7.0]


@pytest.mark.parametrize("resp", [httpx.Response(401), httpx.Response(404), httpx.Response(400)])
def test_client_errors_are_not_retried(resp):
    p = Provider(failures=[resp])
    with pytest.raises(fp.ProviderError):
        p.adapter().season_matches("EPL", 2026)
    assert p.calls == 1


def test_garbage_response_is_a_retryable_error_not_data():
    p = Provider(failures=[httpx.Response(200, text="<html>"), httpx.Response(200, json=["not", "an", "object"]), httpx.Response(200, json={"nope": 1})])
    with pytest.raises(fp.ProviderError):
        p.adapter().season_matches("EPL", 2026)


# ---- synchronisation ----------------------------------------------------------------------------------------------------------------

def test_sync_creates_fixtures_mappings_and_history(conn, ws):
    _, wid = ws
    r = run(conn, wid, Provider([match(101), match(102, "Liverpool FC", "Everton FC", NOW + timedelta(days=4))]))
    assert r["status"] == "complete" and (r["created"], r["updated"], r["unchanged"]) == (2, 0, 0)
    fx = rows(conn, wid)
    assert [f["home_team"] for f in fx] == ["Arsenal", "Liverpool"] and all(f["provider"] == fp.PROVIDER and f["status"] == "scheduled" for f in fx)
    assert conn.execute("select count(*) n from football_fixture_provider_mappings where workspace_id=%s", (wid,)).fetchone()["n"] == 2
    h = conn.execute("select old_status, new_status from football_fixture_status_history where workspace_id=%s", (wid,)).fetchall()
    assert len(h) == 2 and all(x["old_status"] is None and x["new_status"] == "scheduled" for x in h)
    job = conn.execute("select status, created, finished_at from football_sync_jobs where workspace_id=%s", (wid,)).fetchone()
    assert job["status"] == "complete" and job["created"] == 2 and job["finished_at"]


def test_second_identical_sync_changes_nothing(conn, ws):
    _, wid = ws
    p = Provider([match(101)])
    run(conn, wid, p)
    r = run(conn, wid, p, now=NOW + timedelta(hours=11))
    assert (r["created"], r["updated"], r["unchanged"]) == (0, 0, 1)
    assert len(rows(conn, wid)) == 1
    assert conn.execute("select count(*) n from football_fixture_status_history where workspace_id=%s", (wid,)).fetchone()["n"] == 1


def test_duplicate_provider_ids_in_one_response_make_one_fixture(conn, ws):
    _, wid = ws
    r = run(conn, wid, Provider([match(101), match(101)]))
    assert r["created"] == 1 and len(rows(conn, wid)) == 1


def test_reschedule_updates_the_same_fixture_and_records_history(conn, ws):
    _, wid = ws
    run(conn, wid, Provider([match(101)]))
    first = rows(conn, wid)[0]
    moved = NOW + timedelta(days=5, hours=3)
    r = run(conn, wid, Provider([match(101, kick=moved)]), now=NOW + timedelta(hours=7))
    assert r["updated"] == 1 and r["created"] == 0
    f = rows(conn, wid)
    assert len(f) == 1 and f[0]["id"] == first["id"] and f[0]["kickoff_utc"] == moved and f[0]["fixture_date"] == moved.date()
    h = conn.execute("select old_kickoff, new_kickoff from football_fixture_status_history where fixture_id=%s order by observed_at, id", (first["id"],)).fetchall()
    assert len(h) == 2 and h[1]["old_kickoff"] == first["kickoff_utc"] and h[1]["new_kickoff"] == moved


def test_postponed_and_cancelled_matches_are_stored_but_never_forecast(conn, ws):
    from stratiq import football_jobs
    _, wid = ws
    run(conn, wid, Provider([match(101), match(102, "Liverpool FC", "Everton FC", status="POSTPONED"), match(103, "Fulham FC", "Wolverhampton Wanderers FC", status="CANCELLED")]))
    by = {f["home_team"]: f for f in rows(conn, wid)}
    assert by["Liverpool"]["status"] == "postponed" and by["Fulham"]["status"] == "cancelled" and by["Fulham"]["away_team"] == "Wolves"
    # the existing forecasting job only considers scheduled fixtures that have not kicked off
    seen = []
    import stratiq.football_intel_api as api
    orig = api._intelligence
    api._intelligence = lambda c, p, h, a, *x: seen.append((h, a)) or (_ for _ in ()).throw(__import__("fastapi").HTTPException(422, "stub"))
    try:
        out = football_jobs.forecast_upcoming(conn, wid, today=NOW.date(), days=10)
    finally:
        api._intelligence = orig
    assert out["fixtures"] == 1 and seen == [("Arsenal", "Chelsea")]


def test_postponed_then_rescheduled_returns_to_scheduled_with_history(conn, ws):
    _, wid = ws
    run(conn, wid, Provider([match(101, status="POSTPONED")]))
    new = NOW + timedelta(days=9)
    run(conn, wid, Provider([match(101, kick=new, status="TIMED")]), now=NOW + timedelta(hours=7))
    f = rows(conn, wid)[0]
    assert f["status"] == "scheduled" and f["kickoff_utc"] == new
    assert [h["new_status"] for h in conn.execute("select new_status from football_fixture_status_history where fixture_id=%s order by observed_at, id", (f["id"],)).fetchall()] == ["postponed", "scheduled"]


def test_uploaded_fixture_for_the_same_match_is_adopted_not_duplicated(conn, ws):
    _, wid = ws
    d = (NOW + timedelta(days=2)).date()
    conn.execute("insert into football_fixtures (workspace_id, competition, season, fixture_date, home_team, away_team) values (%s,'EPL','2026/27',%s,'Arsenal','Chelsea')", (wid, d))
    r = run(conn, wid, Provider([match(101)]))
    assert r["updated"] == 1 and r["created"] == 0 and len(rows(conn, wid)) == 1
    assert rows(conn, wid)[0]["kickoff_utc"] is not None


def test_finished_match_stores_the_full_time_score(conn, ws):
    _, wid = ws
    played = NOW - timedelta(days=2)
    run(conn, wid, Provider([match(101, kick=played, status="TIMED")]))
    run(conn, wid, Provider([match(101, kick=played, status="FINISHED", hg=3, ag=1)]), now=NOW + timedelta(hours=7))
    f = rows(conn, wid)[0]
    assert (f["status"], f["home_goals"], f["away_goals"]) == ("finished", 3, 1)


def test_matches_outside_the_window_and_malformed_matches_are_skipped(conn, ws):
    _, wid = ws
    r = run(conn, wid, Provider([match(1), match(2, kick=NOW + timedelta(days=60)), match(3, kick=NOW - timedelta(days=40)), match(4, status="MYSTERY")]))
    assert r["created"] == 1 and r["skipped"] == 1


def test_provider_outage_leaves_stored_data_untouched_and_recovers(conn, ws):
    _, wid = ws
    run(conn, wid, Provider([match(101)]))
    before = rows(conn, wid)
    later = NOW + timedelta(hours=11)                   # the shared cache (10 minutes) has expired
    down = Provider([match(101, status="POSTPONED")], failures=[httpx.Response(503)] * 3)
    r = run(conn, wid, down, now=later)
    assert r["status"] == "failed" and r["retryable"] and "problems" in r["message"]
    assert rows(conn, wid) == before                                                    # nothing changed
    fr = sync.freshness(conn, wid, later)
    assert fr["provider_failing"] and fr["stale"] is True and fr["last_verified_at"] == NOW and "last verified" in fr["message"]
    h = sync.health(conn)
    assert h["consecutive_failures"] == 1 and h["last_error"]
    ok = run(conn, wid, Provider([match(101, status="POSTPONED")]), now=later + timedelta(minutes=2))
    assert ok["status"] == "complete" and rows(conn, wid)[0]["status"] == "postponed"
    assert sync.health(conn)["consecutive_failures"] == 0 and not sync.freshness(conn, wid, later + timedelta(minutes=2))["provider_failing"]


def test_repeated_failures_pause_requests_briefly(conn, ws):
    _, wid = ws
    p = Provider(failures=[httpx.Response(503)] * 20)
    t = NOW
    for _ in range(3):
        assert run(conn, wid, p, now=t)["status"] == "failed"
        t += timedelta(seconds=30)
    calls = p.calls
    r = run(conn, wid, p, now=t)
    assert r["status"] == "failed" and "paused" in r["message"] and p.calls == calls          # no request was made while paused
    assert run(conn, wid, Provider([match(1)]), now=t + sync.PAUSE_FOR + timedelta(seconds=1))["status"] == "complete"


def test_failed_job_after_partial_write_is_impossible_because_writes_follow_every_fetch(conn, ws):
    # the window crosses a season boundary (two requests); if the second fails nothing from the first is stored
    _, wid = ws
    now = datetime(2026, 7, 25, 12, tzinfo=timezone.utc)
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json={"matches": [match(1, kick=now + timedelta(days=1))]}) if calls["n"] == 1 else httpx.Response(500)
    ad = fp.FootballDataOrg(KEY, httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None, jitter=lambda: 0.0)
    r = sync.sync_workspace(conn, wid, adapter=ad, now=now)
    assert r["status"] == "failed" and rows(conn, wid) == []


def test_shared_cache_serves_other_workspaces_without_another_request(conn):
    (_, w1), (_, w2) = make_user(conn), make_user(conn)
    p = Provider([match(101)])
    run(conn, w1, p)
    run(conn, w2, p, now=NOW + timedelta(minutes=1))
    assert p.calls == 1 and len(rows(conn, w1)) == 1 and len(rows(conn, w2)) == 1


def test_request_window_enforces_the_per_minute_limit(conn, ws, monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_RATE_PER_MINUTE", "2")
    for i in range(2):
        assert sync.take_request_slot(conn, fp.PROVIDER, NOW + timedelta(seconds=i), 2)
    assert not sync.take_request_slot(conn, fp.PROVIDER, NOW + timedelta(seconds=30), 2)
    assert sync.take_request_slot(conn, fp.PROVIDER, NOW + timedelta(seconds=61), 2)          # a new minute


def test_rate_limited_sync_reports_it_and_stores_nothing(conn, ws, monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_RATE_PER_MINUTE", "1")
    _, wid = ws
    conn.execute("insert into football_provider_health (provider, window_start, window_count) values (%s,%s,1) on conflict (provider) do update set window_start=excluded.window_start, window_count=1", (fp.PROVIDER, NOW))
    p = Provider([match(1)])
    r = run(conn, wid, p)
    assert r["status"] == "failed" and "limit" in r["message"] and p.calls == 0 and rows(conn, wid) == []


def test_only_one_sync_runs_per_workspace_and_a_dead_job_is_taken_over(conn, ws):
    _, wid = ws
    first = sync.start_job(conn, wid, "manual", NOW.date(), NOW.date(), NOW)
    assert first and sync.start_job(conn, wid, "manual", NOW.date(), NOW.date(), NOW + timedelta(minutes=1)) is None
    assert run(conn, wid, Provider([match(1)]), now=NOW + timedelta(minutes=2))["status"] == "already_running"
    later = NOW + sync.STALE_JOB_AFTER + timedelta(minutes=1)
    assert sync.start_job(conn, wid, "manual", NOW.date(), NOW.date(), later)
    assert conn.execute("select status, error from football_sync_jobs where id=%s", (first,)).fetchone()["status"] == "failed"


def test_not_configured_is_reported_without_touching_anything(conn, ws, monkeypatch):
    monkeypatch.delenv("FOOTBALL_DATA_API_KEY")
    _, wid = ws
    r = sync.sync_workspace(conn, wid, now=NOW)
    assert r["status"] == "not_configured" and "Uploaded fixtures still work" in r["message"]
    assert conn.execute("select count(*) n from football_sync_jobs where workspace_id=%s", (wid,)).fetchone()["n"] == 0


def test_scheduled_cycle_includes_the_sync_and_survives_an_outage(conn, ws, monkeypatch):
    from stratiq import football_jobs
    _, wid = ws
    down = Provider(failures=[httpx.Response(500)] * 3)
    monkeypatch.setattr(fp, "FootballDataOrg", lambda: down.adapter())
    out = football_jobs.run_workspace(conn, wid, "schedule", allow_retrain=False, today=NOW.date())
    assert out["live_sync"]["status"] == "failed" and "error" not in out


# ---- API ----------------------------------------------------------------------------------------------------------------------------

@pytest.fixture()
def live(conn, client, ws, monkeypatch):
    """Fixtures synchronised through the API against a mocked provider, relative to the real clock."""
    uid, wid = ws
    now = datetime.now(timezone.utc)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    ms = [match(1, kick=day + timedelta(hours=1)),                                             # 01:00 UTC today (or already played: still today)
          match(2, "Liverpool FC", "Everton FC", day + timedelta(days=1, hours=23, minutes=30)),        # 23:30 UTC tomorrow
          match(3, "Fulham FC", "Brentford FC", day + timedelta(days=5, hours=14), status="POSTPONED"),
          match(4, "Leeds United FC", "Burnley FC", day + timedelta(days=20, hours=14))]
    p = Provider(ms)
    monkeypatch.setattr(fp, "FootballDataOrg", lambda: p.adapter())
    h = hdr(uid, wid, exp_in=900)
    r = client.post("/api/v1/football/live/sync", headers=h)
    assert r.status_code == 200, r.text
    return h, wid, p, day


def test_sync_endpoint_and_throttle(client, live):
    h, wid, p, _ = live
    again = client.post("/api/v1/football/live/sync", headers=h).json()
    assert again["status"] == "recent" and p.calls == 1


def test_viewer_cannot_sync_but_can_read(client, conn, live):
    h, wid, _, _ = live
    vh = hdr(make_user(conn, role="viewer", workspace_id=wid)[0], wid, exp_in=900)
    assert client.post("/api/v1/football/live/sync", headers=vh).status_code == 403
    assert client.get("/api/v1/football/live/fixtures?window=month", headers=vh).status_code == 200


def test_kickoff_times_follow_the_selected_time_zone(client, live):
    h, _, _, day = live
    r = client.get("/api/v1/football/live/fixtures?window=month&tz=Asia/Tokyo&limit=100", headers=h).json()
    liv = next(f for f in r["fixtures"] if f["home_team"] == "Liverpool")
    assert liv["kickoff_utc"].startswith((day + timedelta(days=1, hours=23, minutes=30)).strftime("%Y-%m-%dT23:30")) and liv["time_zone"] == "Asia/Tokyo"
    assert liv["kickoff_local"].startswith((day + timedelta(days=2)).strftime("%Y-%m-%dT08:30")) and liv["kickoff_local"].endswith("+09:00")


def test_tomorrow_window_depends_on_the_callers_midnight(client, live):
    h, _, _, _ = live
    utc = {f["home_team"] for f in client.get("/api/v1/football/live/fixtures?window=tomorrow&tz=UTC", headers=h).json()["fixtures"]}
    tokyo = {f["home_team"] for f in client.get("/api/v1/football/live/fixtures?window=tomorrow&tz=Asia/Tokyo", headers=h).json()["fixtures"]}
    assert "Liverpool" in utc and "Liverpool" not in tokyo         # 23:30 UTC tomorrow is already the day after in Tokyo


def test_windows_status_and_team_filters_and_postponed_flag(client, live):
    h, _, _, _ = live
    g = lambda q: client.get("/api/v1/football/live/fixtures?" + q, headers=h).json()  # noqa: E731
    assert {f["home_team"] for f in g("window=month")["fixtures"]} == {"Arsenal", "Liverpool", "Fulham", "Leeds United"}
    post = g("window=all&status=postponed")["fixtures"]
    assert [f["home_team"] for f in post] == ["Fulham"] and post[0]["forecastable"] is False
    assert [f["home_team"] for f in g("window=all&team=everton")["fixtures"]] == ["Liverpool"]
    assert g("window=all&team=%25")["total"] == 0                       # a wildcard is literal text
    assert g("window=all&limit=2")["total"] == 4 and len(g("window=all&limit=2")["fixtures"]) == 2


def test_validation_and_freshness_fields(client, live):
    h, _, _, _ = live
    assert client.get("/api/v1/football/live/fixtures?tz=Mars/Base", headers=h).status_code == 422
    assert client.get("/api/v1/football/live/fixtures?window=decade", headers=h).status_code == 422
    assert client.get("/api/v1/football/live/fixtures?status=exploded", headers=h).status_code == 422
    fr = client.get("/api/v1/football/live/fixtures", headers=h).json()["freshness"]
    assert fr["stale"] is False and fr["last_verified_at"]


def test_workspaces_do_not_see_each_others_fixtures(client, conn, live):
    _, wid, _, _ = live
    ou, ow = make_user(conn)
    other = hdr(ou, ow, exp_in=900)
    r = client.get("/api/v1/football/live/fixtures?window=all", headers=other).json()
    assert r["total"] == 0 and "never been fetched" in r["note"]
    assert client.get("/api/v1/football/live/fixtures").status_code in (401, 403)


def test_provider_status_never_exposes_the_key(client, live):
    h, _, _, _ = live
    r = client.get("/api/v1/football/live/provider", headers=h)
    assert KEY not in r.text and r.json()["configured"] is True
    caps = r.json()["capabilities"]
    assert caps["injuries_suspensions"] is False and r.json()["health"]["consecutive_failures"] == 0


def test_status_history_endpoint(client, live):
    h, wid, _, _ = live
    fid = client.get("/api/v1/football/live/fixtures?window=all&status=postponed", headers=h).json()["fixtures"][0]["id"]
    hist = client.get(f"/api/v1/football/live/fixtures/{fid}/history", headers=h).json()["history"]
    assert [x["new_status"] for x in hist] == ["postponed"]
    assert client.get("/api/v1/football/live/fixtures/not-a-uuid/history", headers=h).status_code == 404


# ---- schema -------------------------------------------------------------------------------------------------------------------------

def test_schema_enforces_identity_and_valid_values(conn, ws):
    _, wid = ws
    run(conn, wid, Provider([match(101)]))
    fid = rows(conn, wid)[0]["id"]
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute("insert into football_fixture_provider_mappings (workspace_id, fixture_id, provider, provider_fixture_id, raw_home, raw_away) values (%s,%s,%s,'101','a','b')", (wid, fid, fp.PROVIDER))
    conn.rollback()


def test_schema_rejects_an_invalid_status_and_a_second_running_job(conn, ws):
    _, wid = ws
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("insert into football_fixtures (workspace_id, competition, season, fixture_date, home_team, away_team, status) values (%s,'EPL','2026/27','2026-12-01','A','B','exploded')", (wid,))
    conn.rollback()
    _, wid = make_user(conn)
    sync.start_job(conn, wid, "manual", NOW.date(), NOW.date(), NOW)
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute("insert into football_sync_jobs (workspace_id, provider, trigger, window_from, window_to) values (%s,%s,'manual',%s,%s)", (wid, fp.PROVIDER, NOW.date(), NOW.date()))
    conn.rollback()
