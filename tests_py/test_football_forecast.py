"""Phase 4B: automated, versioned pre-match forecasts. Match history is SYNTHETIC (real club names, random scores); provider data is mocked.
Nothing here says anything about real forecasting accuracy."""
import random
from datetime import datetime, timedelta, timezone

import psycopg
import pytest

from stratiq import football_forecast as ff
from stratiq import football_provider as fp

from .conftest import hdr, make_user
from .test_football import five_csv
from .test_football_intel import post
from .test_football_provenance import ROWS, do_import

HOME, AWAY = ROWS[0][1], ROWS[0][2]
OTHERS = sorted({t for m in ROWS for t in (m[1], m[2])} - {HOME, AWAY})
NOW = datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture()
def ws(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid, exp_in=900)
    assert do_import(client, h).status_code == 200
    return h, wid


def add_fixture(conn, wid, home=HOME, away=AWAY, kick=None, status="scheduled", competition="EPL"):
    kick = kick or NOW + timedelta(days=3)
    r = conn.execute("""insert into football_fixtures (workspace_id, competition, season, fixture_date, home_team, away_team, kickoff_utc, status, provider)
                        values (%s,%s,'2026/27',%s,%s,%s,%s,%s,'football-data.org') returning *""", (wid, competition, kick.date(), home, away, kick, status)).fetchone()
    return r


def versions(conn, fid):
    return conn.execute("select * from football_prediction_versions where fixture_id=%s order by version_no", (fid,)).fetchall()


# ---- the forecast itself ------------------------------------------------------------------------------------------------------------

def test_a_forecast_has_every_required_output(conn, ws):
    _, wid = ws
    fx = add_fixture(conn, wid)
    conn.execute("insert into football_fixture_provider_mappings (workspace_id, fixture_id, provider, provider_fixture_id, raw_home, raw_away) values (%s,%s,'football-data.org','555','a','b')", (wid, fx["id"]))
    r = ff.generate_version(conn, fx, "discovery", "First forecast.", NOW)
    assert r["status"] == "created" and r["version_no"] == 1
    v = ff.present(versions(conn, fx["id"])[0])
    pr = v["probabilities"]
    assert abs(pr["home"] + pr["draw"] + pr["away"] - 1) < 1e-6
    assert round(sum(v["percent"].values()), 1) == 100.0
    assert v["expected_goals"]["home"] > 0 and v["expected_goals"]["away"] > 0
    assert 0 < v["goals"]["over_2_5"] < 1 and abs(v["goals"]["over_2_5"] + v["goals"]["under_2_5"] - 1) < 1e-5 and 0 < v["goals"]["both_teams_to_score"] < 1
    assert len(v["top_scorelines"]) == 5 and v["top_scorelines"][0]["p"] >= v["top_scorelines"][4]["p"]
    assert v["drivers"] and v["data_completeness"]["of"] == 13 and "missing" in v["data_completeness"]
    assert any("No backtest" in w for w in v["warnings"]) and any("Unavailable" in w for w in v["warnings"])      # data-quality warnings are carried
    assert v["model"] == "dixon_coles" and v["checkpoint"] == "discovery" and v["official"] is True
    assert v["provider_refs"]["provider_fixture_id"] == "555" and v["provider_refs"]["fixture_provider"] == "football-data.org"
    assert "not betting or financial advice" in v["label"]
    row = versions(conn, fx["id"])[0]
    assert row["generated_at"] == NOW and row["kickoff_utc"] == fx["kickoff_utc"] and row["snapshot_id"] and row["model_version_id"] and row["input_sha256"]


def test_percentages_always_add_up_to_exactly_one_hundred():
    rnd = random.Random(7)
    for _ in range(500):
        a, b = sorted((rnd.random(), rnd.random()))
        p = [a, b - a, 1 - b]
        assert round(sum(ff.percentages(p)), 1) == 100.0
    assert ff.percentages([1 / 3, 1 / 3, 1 / 3]) == [33.4, 33.3, 33.3]


# ---- versioning ---------------------------------------------------------------------------------------------------------------------

def test_an_identical_refresh_stores_nothing_new(conn, ws):
    _, wid = ws
    fx = add_fixture(conn, wid)
    ff.generate_version(conn, fx, "discovery", "First.", NOW)
    r = ff.generate_version(conn, fx, "h24", "Checkpoint.", NOW + timedelta(hours=1))
    assert r["status"] == "unchanged" and r["version_no"] == 1 and len(versions(conn, fx["id"])) == 1


def test_a_reschedule_makes_a_new_version_and_keeps_the_old_one_unchanged(conn, ws):
    _, wid = ws
    fx = add_fixture(conn, wid)
    ff.generate_version(conn, fx, "discovery", "First.", NOW)
    first = versions(conn, fx["id"])[0]
    moved = fx["kickoff_utc"] + timedelta(hours=26)
    conn.execute("update football_fixtures set kickoff_utc=%s, fixture_date=%s where id=%s", (moved, moved.date(), fx["id"]))
    fx2 = conn.execute("select * from football_fixtures where id=%s", (fx["id"],)).fetchone()
    r = ff.generate_version(conn, fx2, "reschedule", "The provider moved the kickoff.", NOW + timedelta(hours=2))
    assert r["status"] == "created" and r["version_no"] == 2
    vs = versions(conn, fx["id"])
    assert len(vs) == 2 and vs[0]["p_home"] == first["p_home"] and vs[0]["generated_at"] == first["generated_at"] and vs[0]["refresh_reason"] == "First."     # version 1 untouched
    assert vs[1]["refresh_reason"] == "The provider moved the kickoff." and vs[1]["checkpoint"] == "reschedule" and vs[1]["change_from_previous"]["previous_version"] == 1
    assert [v["is_official"] for v in vs] == [False, True]                                                   # the official marker moved to the latest


def test_a_changed_result_history_changes_the_forecast(client, conn, ws):
    h, wid = ws
    fx = add_fixture(conn, wid)
    ff.generate_version(conn, fx, "discovery", "First.", NOW)
    # import the same clubs' later results: a different data hash gives a different forecast input
    body = {"filename": "E0.csv", "combined": True, "csv": five_csv([(NOW.date() - timedelta(days=30), HOME, OTHERS[0], 4, 0), (NOW.date() - timedelta(days=20), OTHERS[1], AWAY, 3, 0)])}
    assert post(client, h, "import", body).status_code == 200
    r = ff.generate_version(conn, fx, "h24", "New results were imported.", NOW + timedelta(hours=1))
    assert r["status"] == "created" and r["version_no"] == 2
    assert versions(conn, fx["id"])[1]["change_from_previous"]["max_abs_change"] >= 0


@pytest.mark.parametrize("sql", ["update football_prediction_versions set p_home=0.9, p_draw=0.05, p_away=0.05 where id=%s", "update football_prediction_versions set refresh_reason='edited' where id=%s",
                                 "update football_prediction_versions set generated_at=generated_at - interval '1 day' where id=%s"])
def test_stored_versions_cannot_be_edited(conn, ws, sql):
    _, wid = ws
    fx = add_fixture(conn, wid)
    ff.generate_version(conn, fx, "discovery", "First.", NOW)
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(sql, (versions(conn, fx["id"])[0]["id"],))
    conn.rollback()


def test_only_the_official_marker_may_change_and_only_one_version_is_official(conn, ws):
    _, wid = ws
    fx = add_fixture(conn, wid)
    ff.generate_version(conn, fx, "discovery", "First.", NOW)
    moved = fx["kickoff_utc"] + timedelta(hours=3)
    conn.execute("update football_fixtures set kickoff_utc=%s where id=%s", (moved, fx["id"]))
    ff.generate_version(conn, conn.execute("select * from football_fixtures where id=%s", (fx["id"],)).fetchone(), "reschedule", "Moved.", NOW + timedelta(hours=1))
    assert sum(v["is_official"] for v in versions(conn, fx["id"])) == 1
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute("update football_prediction_versions set is_official=true where fixture_id=%s", (fx["id"],))


# ---- information boundaries ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["in_play", "paused", "finished", "awarded", "postponed", "suspended", "cancelled"])
def test_only_scheduled_matches_are_forecast(conn, ws, status):
    _, wid = ws
    fx = add_fixture(conn, wid, status=status)
    r = ff.generate_version(conn, fx, "discovery", "x", NOW)
    assert r["status"] == "ineligible" and status.replace("_", " ") in r["reason"] and versions(conn, fx["id"]) == []


def test_no_forecast_can_be_made_at_or_after_kickoff(conn, ws):
    _, wid = ws
    fx = add_fixture(conn, wid, kick=NOW + timedelta(hours=2))
    ff.generate_version(conn, fx, "h1", "Before kickoff.", NOW)
    for later in (fx["kickoff_utc"], fx["kickoff_utc"] + timedelta(minutes=1)):
        r = ff.generate_version(conn, fx, "manual", "Too late.", later)
        assert r["status"] == "ineligible" and "Kickoff has passed" in r["reason"]
    assert len(versions(conn, fx["id"])) == 1


def test_the_database_rejects_a_version_stamped_at_or_after_kickoff(conn, ws):
    _, wid = ws
    fx = add_fixture(conn, wid)
    ff.generate_version(conn, fx, "discovery", "First.", NOW)
    v = versions(conn, fx["id"])[0]
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("""insert into football_prediction_versions (workspace_id, fixture_id, version_no, model_version_id, model_name, goal_model, snapshot_id, input_sha256, generated_at, kickoff_utc,
                         checkpoint, refresh_reason, p_home, p_draw, p_away, completeness) values (%s,%s,2,%s,'dixon_coles','dixon_coles',%s,'x',%s,%s,'manual','late',0.4,0.3,0.3,'{}')""",
                     (wid, fx["id"], v["model_version_id"], v["snapshot_id"], fx["kickoff_utc"], fx["kickoff_utc"]))
    conn.rollback()


def test_results_from_today_or_later_never_enter_a_forecast(client, conn, ws):
    h, wid = ws
    fx = add_fixture(conn, wid)
    ff.generate_version(conn, fx, "discovery", "First.", NOW)
    # a result dated today (even one that finished an hour ago) is not used before kickoff day's cutoff; the forecast input is therefore unchanged
    body = {"filename": "E0.csv", "combined": True, "csv": five_csv([(NOW.date(), HOME, OTHERS[0], 7, 0)])}
    post(client, h, "import", body)
    assert ff.generate_version(conn, fx, "h6", "Check.", NOW + timedelta(hours=1))["status"] == "unchanged"


def test_clubs_without_history_or_with_too_little_get_no_forecast_and_a_reason(conn, ws):
    _, wid = ws
    unknown = add_fixture(conn, wid, home="Brand New Town", away=AWAY)
    r = ff.generate_version(conn, unknown, "discovery", "x", NOW)
    assert r["status"] == "ineligible" and "Brand New Town" in r["reason"]
    thin = add_fixture(conn, wid, home=OTHERS[0], away=OTHERS[1], kick=NOW + timedelta(days=4))
    conn.execute("""delete from match_history where workspace_id=%s and (home_team=%s or away_team=%s) and ctid not in
                    (select ctid from match_history where workspace_id=%s and (home_team=%s or away_team=%s) order by match_date limit 3)""", (wid, OTHERS[0], OTHERS[0], wid, OTHERS[0], OTHERS[0]))
    r = ff.generate_version(conn, thin, "discovery", "x", NOW)
    assert r["status"] == "ineligible" and "at least 5" in r["reason"]


def test_non_epl_fixtures_are_not_forecast(conn, ws):
    _, wid = ws
    fx = add_fixture(conn, wid, competition="LL")
    assert ff.generate_version(conn, fx, "discovery", "x", NOW)["status"] == "ineligible"


# ---- the scheduled path -------------------------------------------------------------------------------------------------------------

def test_pending_fixtures_get_a_first_forecast_once(conn, ws):
    _, wid = ws
    a = add_fixture(conn, wid)
    b = add_fixture(conn, wid, home=OTHERS[0], away=OTHERS[1], kick=NOW + timedelta(days=5))
    add_fixture(conn, wid, home=OTHERS[2], away=OTHERS[3], kick=NOW + timedelta(days=6), status="postponed")
    add_fixture(conn, wid, home=OTHERS[4], away=OTHERS[5], kick=NOW + timedelta(days=40))                      # beyond the 14-day horizon
    r = ff.generate_pending(conn, wid, NOW)
    assert r["considered"] == 2 and r["created"] == 2 and r["ineligible"] == []
    assert len(versions(conn, a["id"])) == 1 and len(versions(conn, b["id"])) == 1
    again = ff.generate_pending(conn, wid, NOW + timedelta(minutes=5))
    assert again["considered"] == 0 and again["created"] == 0


def test_pending_run_is_bounded_in_number_and_time(conn, ws):
    _, wid = ws
    for i in range(3):
        add_fixture(conn, wid, home=OTHERS[2 * i], away=OTHERS[2 * i + 1], kick=NOW + timedelta(days=2 + i))
    assert ff.generate_pending(conn, wid, NOW, limit=2)["created"] == 2
    r = ff.generate_pending(conn, wid, NOW, max_seconds=-1)
    assert r["created"] == 0 and r["deferred"] == 1                       # out of time: left for the next run, not half-written


def test_ineligible_pending_fixtures_are_reported_with_reasons(conn, ws):
    _, wid = ws
    add_fixture(conn, wid, home="Brand New Town", away=AWAY)
    r = ff.generate_pending(conn, wid, NOW)
    assert r["created"] == 0 and "Brand New Town" in r["ineligible"][0]["reason"]


def test_scheduled_cycle_creates_forecasts_after_syncing(conn, ws, monkeypatch):
    import httpx
    from stratiq import football_jobs
    _, wid = ws
    monkeypatch.setenv("FOOTBALL_DATA_API_KEY", "k" * 32)
    kick = (NOW + timedelta(days=2)).replace(hour=15, minute=0, second=0)
    m = {"id": 9001, "utcDate": kick.strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "TIMED", "homeTeam": {"name": HOME}, "awayTeam": {"name": AWAY}, "score": {"fullTime": {}}}
    real = fp.FootballDataOrg
    monkeypatch.setattr(fp, "FootballDataOrg", lambda: real("k" * 32, httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"matches": [m]})))))
    out = football_jobs.run_workspace(conn, wid, "schedule", allow_retrain=False, today=NOW.date())
    assert out["live_sync"]["status"] == "complete" and out["live_forecasts"]["created"] == 1 and "error" not in out


# ---- API ----------------------------------------------------------------------------------------------------------------------------

def test_forecast_endpoints(client, conn, ws):
    h, wid = ws
    fx = add_fixture(conn, wid)
    url = f"/api/v1/football/live/fixtures/{fx['id']}/forecast"
    empty = client.get(url, headers=h).json()
    assert empty["latest"] is None and empty["versions"] == 0 and "No forecast has been generated" in empty["no_forecast_reason"]
    made = client.post(url, headers=h)
    assert made.status_code == 200 and made.json()["status"] == "created"
    assert client.post(url, headers=h).json()["status"] == "unchanged"
    got = client.get(url, headers=h).json()
    assert got["versions"] == 1 and got["latest"]["official"] and got["official"]["version_no"] == 1 and round(sum(got["latest"]["percent"].values()), 1) == 100.0
    lst = client.get(url + "s", headers=h).json()
    assert lst["total"] == 1 and lst["versions"][0]["checkpoint"] == "manual"
    listing = client.get("/api/v1/football/live/fixtures?window=all&forecast=yes", headers=h).json()
    assert listing["total"] == 1 and listing["fixtures"][0]["forecast"]["version_no"] == 1
    assert client.get("/api/v1/football/live/fixtures?window=all&forecast=no", headers=h).json()["total"] == 0
    assert client.get("/api/v1/football/live/fixtures?forecast=maybe", headers=h).status_code == 422


def test_ineligible_manual_request_is_a_clear_conflict(client, conn, ws):
    h, wid = ws
    fx = add_fixture(conn, wid, status="postponed")
    r = client.post(f"/api/v1/football/live/fixtures/{fx['id']}/forecast", headers=h)
    assert r.status_code == 409 and "postponed" in r.json()["detail"]
    nf = client.get(f"/api/v1/football/live/fixtures/{fx['id']}/forecast", headers=h).json()
    assert nf["latest"] is None and "postponed" in nf["no_forecast_reason"]


def test_viewers_can_read_but_not_request_and_workspaces_are_isolated(client, conn, ws):
    h, wid = ws
    fx = add_fixture(conn, wid)
    vh = hdr(make_user(conn, role="viewer", workspace_id=wid)[0], wid, exp_in=900)
    url = f"/api/v1/football/live/fixtures/{fx['id']}/forecast"
    assert client.post(url, headers=vh).status_code == 403
    assert client.get(url, headers=vh).status_code == 200
    ou, ow = make_user(conn)
    other = hdr(ou, ow, exp_in=900)
    assert client.get(url, headers=other).status_code == 404 and client.post(url, headers=other).status_code == 404
    assert client.get(url + "s", headers=other).status_code == 404
    assert client.get("/api/v1/football/live/fixtures/nonsense/forecast", headers=h).status_code == 404


# ---- Phase 4C: dashboard API --------------------------------------------------------------------------------------------------------

def played(conn, wid, home, away, days_ago, score, forecast=True):
    """A fixture that kicked off `days_ago` days ago and is now finished. The forecast (if any) was generated before kickoff."""
    kick = NOW - timedelta(days=days_ago)
    fx = add_fixture(conn, wid, home=home, away=away, kick=kick)
    if forecast:
        assert ff.generate_version(conn, fx, "discovery", "First.", kick - timedelta(hours=30))["status"] == "created"
    conn.execute("update football_fixtures set status='finished', home_goals=%s, away_goals=%s where id=%s", (*score, fx["id"]))
    return fx


def test_completed_matches_compare_the_result_with_the_official_forecast(client, conn, ws):
    h, wid = ws
    won = played(conn, wid, HOME, AWAY, 3, (3, 0))
    played(conn, wid, OTHERS[0], OTHERS[1], 5, (1, 1), forecast=False)
    played(conn, wid, OTHERS[2], OTHERS[3], 6, (0, 2))
    r = client.get("/api/v1/football/live/fixtures?window=recent&status=completed&limit=100", headers=h).json()
    assert r["total"] == 3 and all(f["status"] == "finished" for f in r["fixtures"])
    by = {f["home_team"]: f for f in r["fixtures"]}
    a, b = by[HOME], by[OTHERS[0]]
    assert a["final_score"] == {"home": 3, "away": 0} and a["forecast"]["official"] is True
    assert a["result_check"]["available"] and a["result_check"]["outcome"] == "home" and a["result_check"]["most_likely"] in ("home", "draw", "away") and 0 < a["result_check"]["probability_given_to_outcome"] < 1
    assert b["forecast"] is None and b["result_check"]["available"] is False and b["result_check"]["outcome"] == "draw" and "No official forecast" in b["result_check"]["note"]
    assert won and client.get("/api/v1/football/live/fixtures?window=month&status=completed", headers=h).json()["total"] == 0      # completed matches are in the past


def test_a_finished_match_without_a_verified_score_is_not_compared(client, conn, ws):
    h, wid = ws
    fx = played(conn, wid, HOME, AWAY, 3, (1, 0))
    conn.execute("update football_fixtures set home_goals=null, away_goals=null where id=%s", (fx["id"],))
    f = client.get("/api/v1/football/live/fixtures?window=recent&status=completed", headers=h).json()["fixtures"][0]
    assert f["final_score"] is None and f["result_check"]["available"] is False and "full-time score" in f["result_check"]["note"]


def test_day_and_model_filters(client, conn, ws):
    h, wid = ws
    a = add_fixture(conn, wid, kick=NOW.replace(hour=12) + timedelta(days=3))
    add_fixture(conn, wid, home=OTHERS[0], away=OTHERS[1], kick=NOW.replace(hour=12) + timedelta(days=4))
    ff.generate_version(conn, a, "discovery", "First.", NOW)
    day = (NOW + timedelta(days=3)).strftime("%Y-%m-%d")
    g = lambda q: client.get("/api/v1/football/live/fixtures?window=all&" + q, headers=h)  # noqa: E731
    assert [f["home_team"] for f in g(f"day={day}").json()["fixtures"]] == [HOME]
    assert g("model=dixon_coles").json()["total"] == 1 and g("model=ensemble").json()["total"] == 0
    assert g("model=magic").status_code == 422 and g("day=2026-13-45").status_code == 422 and g("day=tomorrow").status_code == 422


def test_forecast_detail_carries_the_team_comparison_and_unavailable_factors(client, conn, ws):
    h, wid = ws
    fx = add_fixture(conn, wid)
    ff.generate_version(conn, fx, "discovery", "First.", NOW)
    d = client.get(f"/api/v1/football/live/fixtures/{fx['id']}/forecast", headers=h).json()["snapshot"]
    assert d["home"]["matches_played"] >= 5 and d["away"]["form_5"] and d["head_to_head"] is not None and d["elo_difference"] is not None
    assert d["factors"]["player_availability"]["status"] == "unavailable" and "not supplied" in d["note"]


def test_forecast_history_lists_every_version_with_filters(client, conn, ws):
    h, wid = ws
    fx = add_fixture(conn, wid)
    other = add_fixture(conn, wid, home=OTHERS[0], away=OTHERS[1], kick=NOW + timedelta(days=5))
    ff.generate_version(conn, fx, "discovery", "First.", NOW)
    moved = fx["kickoff_utc"] + timedelta(hours=30)
    conn.execute("update football_fixtures set kickoff_utc=%s where id=%s", (moved, fx["id"]))
    ff.generate_version(conn, conn.execute("select * from football_fixtures where id=%s", (fx["id"],)).fetchone(), "reschedule", "Moved.", NOW + timedelta(hours=1))
    ff.generate_version(conn, other, "discovery", "First.", NOW)
    g = lambda q="": client.get("/api/v1/football/live/forecast-history?" + q, headers=h)  # noqa: E731
    r = g().json()
    assert r["total"] == 3 and [v["version_no"] for v in r["versions"] if v["fixture_id"] == str(fx["id"])] == [2, 1]
    assert g(f"fixture_id={fx['id']}").json()["total"] == 2 and g(f"team={HOME[:4]}").json()["total"] == 2 and g("team=%25").json()["total"] == 0
    assert g("model=ensemble").json()["total"] == 0 and g("model=nope").status_code == 422 and g("fixture_id=zzz").status_code == 404
    ou, ow = make_user(conn)
    assert client.get("/api/v1/football/live/forecast-history", headers=hdr(ou, ow, exp_in=900)).json()["total"] == 0


def test_deleting_a_workspace_removes_its_forecasts_cleanly(conn, ws):
    _, wid = ws
    fx = add_fixture(conn, wid)
    ff.generate_version(conn, fx, "discovery", "First.", NOW)
    conn.execute("select set_config('stratiq.allow_prediction_delete','on',true)")
    conn.execute("delete from workspaces where id=%s", (wid,))
    assert conn.execute("select count(*) n from football_prediction_versions where workspace_id=%s", (wid,)).fetchone()["n"] == 0
