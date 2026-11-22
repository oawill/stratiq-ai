"""Phase 4E: scheduled refresh of live forecasts. History is SYNTHETIC; provider responses are MOCKED."""
import json
import pathlib
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from stratiq import football_forecast as ff
from stratiq import football_provider as fp
from stratiq import football_refresh as fr

from .conftest import hdr, make_user
from .test_football import five_csv
from .test_football_forecast import AWAY, HOME, OTHERS, add_fixture, versions, ws  # noqa: F401  (ws is a fixture)
from .test_football_intel import post
from .test_football_live import KEY, Provider
from .test_football_live import match as provider_match

NOW = datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture(autouse=True)
def no_provider(monkeypatch):
    monkeypatch.delenv("FOOTBALL_DATA_API_KEY", raising=False)       # ticks in these tests never reach a provider unless a test installs a mock


def runs(conn, fid):
    return conn.execute("select checkpoint_minutes, outcome, attempts, version_no from football_refresh_runs where fixture_id=%s order by checkpoint_minutes desc", (fid,)).fetchall()


def new_results(client, h, days_ago=1):
    """A result dated before today, so a forecast made afterwards legitimately knows about it."""
    assert post(client, h, "import", {"filename": "E0.csv", "combined": True, "csv": five_csv([(NOW.date() - timedelta(days=days_ago), HOME, OTHERS[0], 5, 0)])}).status_code == 200


# ---- pure rules ---------------------------------------------------------------------------------------------------------------------

def test_checkpoint_validation_and_wording():
    assert fr.validate_checkpoints([60, 2880, 360]) == [2880, 360, 60]
    for bad in ([], [10], [20000], [60, 60], [1.5], ["60"], [True], list(range(60, 60 + 9 * 60, 60)), "60"):
        with pytest.raises(ValueError):
            fr.validate_checkpoints(bad)
    assert [fr.describe(m) for m in (2880, 1440, 360, 60, 90, 15)] == ["2 days", "1 day", "6 hours", "1 hour", "90 minutes", "15 minutes"]


def test_the_checkpoint_closest_to_kickoff_is_the_one_that_is_due():
    ko = NOW + timedelta(hours=10)
    cps = [2880, 1440, 360, 60]
    assert fr.passed_checkpoints(ko, NOW, cps) == [1440, 2880]                           # 6h has not arrived yet, 24h and 48h have; the nearest is 24h
    assert fr.passed_checkpoints(ko, ko - timedelta(minutes=59), cps) == [60, 360, 1440, 2880]
    assert fr.passed_checkpoints(ko, ko, cps) == [] and fr.passed_checkpoints(ko, ko + timedelta(minutes=1), cps) == []     # nothing at or after kickoff
    assert fr.next_checkpoint(ko, NOW, cps, {1440, 2880}) == (360, ko - timedelta(hours=6))
    assert fr.next_checkpoint(ko, NOW, cps, set(cps)) is None


def test_the_sync_interval_is_never_shorter_than_the_shared_cache(monkeypatch):
    monkeypatch.setenv("FOOTBALL_LIVE_INTERVAL_MINUTES", "1")
    monkeypatch.setenv("FOOTBALL_SYNC_INTERVAL_MINUTES", "garbage")
    normal, live = fr.sync_intervals()
    assert live >= timedelta(minutes=10) and normal == timedelta(minutes=360)


# ---- checkpoint refresh -------------------------------------------------------------------------------------------------------------

def test_a_checkpoint_stores_a_new_version_only_when_something_changed(client, conn, ws):  # noqa: F811
    h, wid = ws
    fx = add_fixture(conn, wid, kick=NOW + timedelta(days=3))
    ff.generate_version(conn, fx, "discovery", "First.", NOW)
    at = fx["kickoff_utc"] - timedelta(hours=23)                           # the 24h checkpoint has arrived; so has 48h
    r = fr.refresh_checkpoints(conn, wid, at, [2880, 1440, 360, 60])
    assert (r["created"], r["unchanged"], r["skipped_late"]) == (0, 1, 0) and len(versions(conn, fx["id"])) == 1           # nothing new was known
    assert [(x["checkpoint_minutes"], x["outcome"]) for x in runs(conn, fx["id"])] == [(2880, "skipped_late"), (1440, "unchanged")]
    new_results(client, h)
    at2 = fx["kickoff_utc"] - timedelta(hours=5)                           # 6h arrived
    r = fr.refresh_checkpoints(conn, wid, at2, [2880, 1440, 360, 60])
    assert r["created"] == 1
    vs = versions(conn, fx["id"])
    assert len(vs) == 2 and vs[1]["checkpoint"] == "h6" and vs[1]["refresh_reason"] == "6 hours before kickoff." and vs[1]["generated_at"] == at2 and vs[1]["is_official"] and not vs[0]["is_official"]


def test_running_the_same_checkpoint_twice_does_nothing_the_second_time(client, conn, ws):  # noqa: F811
    h, wid = ws
    fx = add_fixture(conn, wid, kick=NOW + timedelta(days=3))
    ff.generate_version(conn, fx, "discovery", "First.", NOW)
    new_results(client, h)
    at = fx["kickoff_utc"] - timedelta(hours=5)
    assert fr.refresh_checkpoints(conn, wid, at, [360])["created"] == 1
    again = fr.refresh_checkpoints(conn, wid, at + timedelta(minutes=2), [360])
    assert (again["created"], again["unchanged"]) == (0, 0) and len(versions(conn, fx["id"])) == 2 and len(runs(conn, fx["id"])) == 1


def test_a_late_scheduler_acts_only_on_the_latest_checkpoint(client, conn, ws):  # noqa: F811
    h, wid = ws
    fx = add_fixture(conn, wid, kick=NOW + timedelta(days=3))
    ff.generate_version(conn, fx, "discovery", "First.", NOW)
    new_results(client, h)
    r = fr.refresh_checkpoints(conn, wid, fx["kickoff_utc"] - timedelta(minutes=30), [2880, 1440, 360, 60])     # the scheduler was away until 30 minutes before kickoff
    assert r["created"] == 1
    assert [(x["checkpoint_minutes"], x["outcome"]) for x in runs(conn, fx["id"])] == [(2880, "skipped_late"), (1440, "skipped_late"), (360, "skipped_late"), (60, "created")]
    assert versions(conn, fx["id"])[-1]["checkpoint"] == "h1"


def test_nothing_is_generated_at_or_after_kickoff(client, conn, ws):  # noqa: F811
    h, wid = ws
    fx = add_fixture(conn, wid, kick=NOW + timedelta(hours=3))
    ff.generate_version(conn, fx, "discovery", "First.", NOW)
    new_results(client, h)
    for t in (fx["kickoff_utc"], fx["kickoff_utc"] + timedelta(minutes=5)):
        assert fr.refresh_checkpoints(conn, wid, t, [60])["considered"] == 0
    assert len(versions(conn, fx["id"])) == 1 and runs(conn, fx["id"]) == []


def test_a_rescheduled_match_gets_its_checkpoints_again(client, conn, ws):  # noqa: F811
    h, wid = ws
    fx = add_fixture(conn, wid, kick=NOW + timedelta(days=3))
    ff.generate_version(conn, fx, "discovery", "First.", NOW)
    new_results(client, h)
    fr.refresh_checkpoints(conn, wid, fx["kickoff_utc"] - timedelta(hours=5), [360])
    moved = fx["kickoff_utc"] + timedelta(days=1)
    conn.execute("update football_fixtures set kickoff_utc=%s, fixture_date=%s where id=%s", (moved, moved.date(), fx["id"]))
    r = fr.refresh_checkpoints(conn, wid, moved - timedelta(hours=5), [360])
    assert r["considered"] == 1 and r["created"] + r["unchanged"] == 1
    assert {x["kickoff_utc"] for x in conn.execute("select kickoff_utc from football_refresh_runs where fixture_id=%s", (fx["id"],)).fetchall()} == {fx["kickoff_utc"], moved}


def test_a_failing_fixture_does_not_stop_the_others_and_is_retried_up_to_three_times(client, conn, ws, monkeypatch):  # noqa: F811
    h, wid = ws
    bad = add_fixture(conn, wid, kick=NOW + timedelta(days=3))
    good = add_fixture(conn, wid, home=OTHERS[0], away=OTHERS[1], kick=NOW + timedelta(days=3, hours=1))
    for f in (bad, good):
        ff.generate_version(conn, f, "discovery", "First.", NOW)
    new_results(client, h)
    real = ff.generate_version

    def flaky(conn_, fx, *a, **k):
        if fx["id"] == bad["id"]:
            raise RuntimeError("boom")
        return real(conn_, fx, *a, **k)
    monkeypatch.setattr(ff, "generate_version", flaky)
    at = bad["kickoff_utc"] - timedelta(hours=5)
    r = fr.refresh_checkpoints(conn, wid, at, [360])
    assert r["failed"] == 1 and r["created"] + r["unchanged"] == 1
    assert [(x["outcome"], x["attempts"]) for x in runs(conn, bad["id"])] == [("failed", 1)]
    for attempt in (2, 3):
        fr.refresh_checkpoints(conn, wid, at + timedelta(minutes=attempt), [360])
        assert runs(conn, bad["id"])[0]["attempts"] == attempt
    fr.refresh_checkpoints(conn, wid, at + timedelta(minutes=9), [360])
    assert runs(conn, bad["id"])[0]["attempts"] == 3                       # three attempts, then it is left alone
    monkeypatch.setattr(ff, "generate_version", real)
    assert len(versions(conn, bad["id"])) == 1                             # nothing half-written


def test_a_dead_runs_claim_is_taken_over_but_a_live_one_is_not(conn, ws):  # noqa: F811
    _, wid = ws
    fx = add_fixture(conn, wid, kick=NOW + timedelta(days=3))
    t = fx["kickoff_utc"] - timedelta(hours=5)
    assert fr._claim(conn, wid, fx, 360, t)
    assert fr._claim(conn, wid, fx, 360, t + timedelta(minutes=2)) is None                 # still being handled
    assert fr._claim(conn, wid, fx, 360, t + fr.CLAIM_STALE + timedelta(minutes=1))        # the first run died


def test_deferred_work_is_counted_not_dropped(conn, ws):  # noqa: F811
    _, wid = ws
    fx = add_fixture(conn, wid, kick=NOW + timedelta(days=3))
    ff.generate_version(conn, fx, "discovery", "First.", NOW)
    r = fr.refresh_checkpoints(conn, wid, fx["kickoff_utc"] - timedelta(hours=5), [360], limit=0)
    assert r["deferred"] == 1 and runs(conn, fx["id"]) == []              # left for the next tick


# ---- reschedule, first forecasts, the tick ------------------------------------------------------------------------------------------

def test_a_provider_reschedule_triggers_a_forecast_in_the_same_tick(conn, ws, monkeypatch):  # noqa: F811
    _, wid = ws
    monkeypatch.setenv("FOOTBALL_DATA_API_KEY", KEY)
    kick = (NOW + timedelta(days=4)).replace(hour=15, minute=0, second=0)
    p1 = Provider([provider_match(7001, HOME + " FC", AWAY + " FC", kick)])
    real = fp.FootballDataOrg
    monkeypatch.setattr(fp, "FootballDataOrg", lambda: real(KEY, __import__("httpx").Client(transport=__import__("httpx").MockTransport(p1.handler)), sleep=lambda s: None, jitter=lambda: 0.0))
    first = fr.tick_workspace(conn, wid, NOW)
    assert first["sync"]["status"] == "complete" and first["first_forecasts"]["created"] == 1 and first["status"] == "acted"
    fid = conn.execute("select id from football_fixtures where workspace_id=%s", (wid,)).fetchone()["id"]
    p1.matches[0] = provider_match(7001, HOME + " FC", AWAY + " FC", kick + timedelta(days=1))        # the provider moves the match
    again = fr.tick_workspace(conn, wid, NOW + timedelta(hours=7))                                    # the six-hour interval has passed and the cache has expired
    assert again["sync"]["updated"] == 1 and again["rescheduled"]["created"] == 1
    vs = versions(conn, fid)
    assert [v["checkpoint"] for v in vs] == ["discovery", "reschedule"] and vs[1]["kickoff_utc"] == kick + timedelta(days=1)
    assert conn.execute("select count(*) n from football_job_runs where workspace_id=%s and kind='live'", (wid,)).fetchone()["n"] == 2


def test_an_idle_tick_costs_nothing_and_records_nothing(conn, ws):  # noqa: F811
    _, wid = ws
    out = fr.tick_workspace(conn, wid, NOW)
    assert out["status"] == "idle" and conn.execute("select count(*) n from football_job_runs where workspace_id=%s and kind='live'", (wid,)).fetchone()["n"] == 0


def test_a_provider_outage_is_recorded_and_leaves_forecasting_running(conn, ws, monkeypatch):  # noqa: F811
    import httpx
    _, wid = ws
    monkeypatch.setenv("FOOTBALL_DATA_API_KEY", KEY)
    fx = add_fixture(conn, wid, kick=NOW + timedelta(days=3))
    down = Provider(failures=[httpx.Response(503)] * 3)
    real = fp.FootballDataOrg
    monkeypatch.setattr(fp, "FootballDataOrg", lambda: real(KEY, httpx.Client(transport=httpx.MockTransport(down.handler)), sleep=lambda s: None, jitter=lambda: 0.0))
    out = fr.tick_workspace(conn, wid, NOW)
    assert out["status"] == "failed" and out["sync"]["status"] == "failed" and out["first_forecasts"]["created"] == 1          # the stored fixture still gets its forecast
    assert len(versions(conn, fx["id"])) == 1
    assert "sync" not in fr.tick_workspace(conn, wid, NOW + timedelta(minutes=2))                  # no second attempt within five minutes of a failure


def test_sync_is_due_by_interval_and_never_retried_within_five_minutes(conn, ws):  # noqa: F811
    _, wid = ws
    assert fr.sync_due(conn, wid, NOW)                                        # never synchronised
    conn.execute("insert into football_sync_jobs (workspace_id, provider, trigger, status, window_from, window_to, started_at, finished_at) values (%s,%s,'schedule','complete',%s,%s,%s,%s)",
                 (wid, fp.PROVIDER, NOW.date(), NOW.date(), NOW, NOW))
    assert not fr.sync_due(conn, wid, NOW + timedelta(hours=1))               # inside the normal interval
    assert fr.sync_due(conn, wid, NOW + timedelta(hours=7))
    add_fixture(conn, wid, kick=NOW + timedelta(hours=2))                      # a match near kickoff shortens the interval
    assert not fr.sync_due(conn, wid, NOW + timedelta(minutes=4)) and fr.sync_due(conn, wid, NOW + timedelta(minutes=20))


def test_automatic_forecasting_can_be_switched_off(client, conn, ws):  # noqa: F811
    h, wid = ws
    fx = add_fixture(conn, wid, kick=NOW + timedelta(days=3))
    fr.save_settings(conn, wid, None, [360], False)
    out = fr.tick_workspace(conn, wid, NOW)
    assert "first_forecasts" not in out and versions(conn, fx["id"]) == []


def test_a_custom_checkpoint_is_labelled_and_worded_plainly(client, conn, ws):  # noqa: F811
    h, wid = ws
    fx = add_fixture(conn, wid, kick=NOW + timedelta(days=3))
    ff.generate_version(conn, fx, "discovery", "First.", NOW)
    new_results(client, h)
    fr.save_settings(conn, wid, None, [90], True)
    out = fr.tick_workspace(conn, wid, fx["kickoff_utc"] - timedelta(minutes=80))
    assert out["checkpoints"]["created"] == 1
    v = versions(conn, fx["id"])[-1]
    assert v["checkpoint"] == "scheduled" and v["refresh_reason"] == "90 minutes before kickoff."


def test_overlapping_ticks_are_refused_while_one_holds_the_lock(conn, ws):  # noqa: F811
    from stratiq.db import database_url
    _, wid = ws
    other = psycopg.connect(database_url(), autocommit=True)
    try:
        other.execute("select pg_advisory_lock(hashtext(%s))", (f"football-tick:{wid}",))
        assert fr.tick_workspace(conn, wid, NOW)["status"] == "busy"
        other.execute("select pg_advisory_unlock(hashtext(%s))", (f"football-tick:{wid}",))
        assert fr.tick_workspace(conn, wid, NOW)["status"] != "busy"
    finally:
        other.close()


def test_tick_all_isolates_failures_and_respects_its_budget(conn, ws, monkeypatch):  # noqa: F811
    _, wid = ws
    seen = []

    def fake(conn_, w, now=None, deadline=None):
        seen.append(w)
        if w == wid:
            raise RuntimeError("boom")
        return {"workspace_id": w, "status": "idle"}
    monkeypatch.setattr(fr, "tick_workspace", fake)
    out = fr.tick_all(conn, NOW)
    mine = next(r for r in out["results"] if r["workspace_id"] == wid)
    assert mine["status"] == "error" and mine["error"] == "RuntimeError" and wid in seen and out["workspaces"] == len(out["results"]) + out["deferred"]
    seen.clear()
    slow = fr.tick_all(conn, NOW, budget=-1)
    assert slow["results"] == [] and slow["deferred"] == slow["workspaces"] and seen == []


# ---- API ----------------------------------------------------------------------------------------------------------------------------

def test_settings_api_defaults_validation_and_permissions(client, conn, ws):  # noqa: F811
    h, wid = ws
    g = client.get("/api/v1/football/live/settings", headers=h).json()
    assert g["checkpoint_minutes"] == [2880, 1440, 360, 60] and g["default"] is True and g["auto_forecast"] is True and "no lineups" in g["lineup_refresh"]
    put = lambda body, hh=h: client.put("/api/v1/football/live/settings", json=body, headers=hh)  # noqa: E731
    ok = put({"checkpoint_minutes": [60, 720], "auto_forecast": False})
    assert ok.status_code == 200 and ok.json()["checkpoint_minutes"] == [720, 60] and ok.json()["auto_forecast"] is False
    assert client.get("/api/v1/football/live/settings", headers=h).json()["default"] is False
    for bad in ({"checkpoint_minutes": []}, {"checkpoint_minutes": [5]}, {"checkpoint_minutes": [60, 60]}, {"checkpoint_minutes": [99999]}, {"checkpoint_minutes": list(range(60, 600, 60))}, {"checkpoint_minutes": ["x"]}):
        assert put(bad).status_code == 422
    assert conn.execute("select count(*) n from audit_logs where workspace_id=%s and action='football.live_settings'", (wid,)).fetchone()["n"] == 1
    viewer = hdr(make_user(conn, role="viewer", workspace_id=wid)[0], wid, exp_in=900)
    assert put({"checkpoint_minutes": [60]}, viewer).status_code == 403 and client.get("/api/v1/football/live/settings", headers=viewer).status_code == 200
    ou, ow = make_user(conn)
    assert client.get("/api/v1/football/live/settings", headers=hdr(ou, ow, exp_in=900)).json()["default"] is True        # another workspace has its own


def test_schedule_endpoint_shows_the_next_refresh_per_fixture(client, conn, ws, monkeypatch):  # noqa: F811
    h, wid = ws
    monkeypatch.setenv("CRON_SECRET", "s" * 20)
    fx = add_fixture(conn, wid, kick=NOW + timedelta(days=3))
    add_fixture(conn, wid, home=OTHERS[0], away=OTHERS[1], kick=NOW + timedelta(days=20))        # beyond seven days
    s = client.get("/api/v1/football/live/schedule", headers=h).json()
    assert len(s["upcoming"]) == 1 and s["upcoming"][0]["fixture_id"] == str(fx["id"]) and s["upcoming"][0]["next_refresh_label"] == "2 days before kickoff"
    assert s["scheduler_configured"] is True and s["provider_configured"] is False and s["last_run"] is None and s["fixture_sync_every_minutes"]["around_kickoff"] >= 10
    monkeypatch.delenv("CRON_SECRET")
    assert client.get("/api/v1/football/live/schedule", headers=h).json()["scheduler_configured"] is False


def test_the_tick_endpoint_is_only_for_the_scheduler(client, conn, monkeypatch):
    monkeypatch.setattr(fr, "tick_all", lambda c: {"workspaces": 0, "deferred": 0, "results": []})
    url = "/api/v1/football/jobs/tick"
    monkeypatch.delenv("CRON_SECRET", raising=False)
    assert client.get(url).status_code == 404 and client.post(url).status_code == 404            # it does not exist until a secret is configured
    monkeypatch.setenv("CRON_SECRET", "s" * 20)
    assert client.get(url).status_code == 401 and client.post(url, headers={"Authorization": "Bearer wrong-wrong-wrong-wrong"}).status_code == 401
    ok = {"Authorization": "Bearer " + "s" * 20}
    assert client.get(url, headers=ok).status_code == 200 and client.post(url, headers=ok).json() == {"workspaces": 0, "deferred": 0, "results": []}


def test_vercel_cron_schedule_is_declared_for_the_light_tick_and_the_daily_cycle():
    cfg = json.loads((pathlib.Path(__file__).resolve().parent.parent / "vercel.json").read_text(encoding="utf-8"))
    crons = {c["path"]: c["schedule"] for c in cfg["crons"]}
    assert crons["/api/v1/football/jobs/tick"] == "*/10 * * * *" and crons["/api/v1/football/jobs/scheduled"] == "0 4 * * *"
