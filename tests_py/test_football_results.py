"""Phase 4F: result reconciliation, evaluation of the official forecast, corrections, and performance reports.
History is SYNTHETIC (real club names, random scores); nothing here says anything about real forecasting accuracy."""
import math
from datetime import datetime, timedelta, timezone

import pytest

from stratiq import football_forecast as ff
from stratiq import football_performance as perf
from stratiq import football_refresh as fr
from stratiq import football_results as res

from .conftest import hdr, make_user
from .test_football import five_csv
from .test_football_forecast import AWAY, HOME, OTHERS, add_fixture, played, versions, ws  # noqa: F401  (ws is a fixture)
from .test_football_intel import post

NOW = datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture(autouse=True)
def no_provider(monkeypatch):
    monkeypatch.delenv("FOOTBALL_DATA_API_KEY", raising=False)


def fixture_row(conn, fid):
    return conn.execute("select * from football_fixtures where id=%s", (fid,)).fetchone()


def evals(conn, fid):
    return conn.execute("select * from football_prediction_evaluations where fixture_id=%s order by evaluated_at", (fid,)).fetchall()


def reconcile(conn, fid, now=NOW):
    return res.reconcile_fixture(conn, fixture_row(conn, fid), now)


def hist_rows(conn, wid, home=HOME, away=AWAY):
    return conn.execute("select * from match_history where workspace_id=%s and home_team=%s and away_team=%s and source_provider='football-data.org'", (wid, home, away)).fetchall()


# ---- the scores themselves ----------------------------------------------------------------------------------------------------------

def test_metrics_match_hand_calculation():
    m = res.metrics([0.5, 0.3, 0.2], 0)
    assert abs(m["log_loss"] + math.log(0.5)) < 1e-12 and abs(m["brier"] - (0.25 + 0.09 + 0.04)) < 1e-12 and m["correct"] is True
    assert abs(m["rps"] - ((0.5 - 1) ** 2 + (0.8 - 1) ** 2) / 2) < 1e-12                      # ranked probability score
    assert res.metrics([0.2, 0.3, 0.5], 0)["correct"] is False and abs(res.metrics([0.4, 0.3, 0.3], 1)["p_actual"] - 0.3) < 1e-12
    assert abs(res.metrics([1 / 3] * 3, 2)["log_loss"] - res.UNIFORM["log_loss"]) < 1e-12 and abs(res.metrics([1 / 3] * 3, 1)["brier"] - res.UNIFORM["brier"]) < 1e-12


# ---- reconciliation -----------------------------------------------------------------------------------------------------------------

def test_a_finished_match_is_scored_added_to_history_and_fed_to_the_tracking_tables(conn, ws):  # noqa: F811
    _, wid = ws
    before = conn.execute("select matches from football_teams where workspace_id=%s and name=%s", (wid, HOME)).fetchone()["matches"]
    fx = played(conn, wid, HOME, AWAY, 3, (2, 1))
    r = reconcile(conn, fx["id"])
    assert r["status"] == "evaluated" and r["history"] == "added" and r["revision"] == 1 and r["correction"] is False
    ev = evals(conn, fx["id"])[0]
    off = versions(conn, fx["id"])[0]
    assert ev["version_id"] == off["id"] and (ev["home_goals"], ev["away_goals"], ev["outcome"]) == (2, 1, 0) and ev["model_name"] == off["model_name"]
    assert abs(ev["log_loss"] - (-math.log(off["p_home"]))) < 1e-4 and abs(ev["brier"] - ((off["p_home"] - 1) ** 2 + off["p_draw"] ** 2 + off["p_away"] ** 2)) < 1e-4
    assert ev["markets"]["over_2_5"]["happened"] is True and ev["markets"]["btts"]["happened"] is True and "in_top_five" in ev["markets"]["exact_score"] and "home" in ev["markets"]["goals_error"]
    h = hist_rows(conn, wid)
    assert len(h) == 1 and (h[0]["home_goals"], h[0]["away_goals"]) == (2, 1) and h[0]["source_reference"].startswith("football-data.org:") and h[0]["season"] == "2026/27"
    f = fixture_row(conn, fx["id"])
    assert (f["reconciled_home"], f["reconciled_away"]) == (2, 1) and f["reconciled_at"] == NOW
    out = conn.execute("""select o.log_loss, o.outcome from football_predictions p join football_prediction_outcomes o on o.prediction_id=p.id
                          where p.workspace_id=%s and p.kind='live' and p.home_team=%s and p.away_team=%s""", (wid, HOME, AWAY)).fetchall()
    assert len(out) == 1 and out[0]["outcome"] == 0 and abs(out[0]["log_loss"] - ev["log_loss"]) < 1e-4                  # drift monitoring sees the same score
    assert conn.execute("select matches from football_teams where workspace_id=%s and name=%s", (wid, HOME)).fetchone()["matches"] == before + 1    # the club registry was refreshed


def test_reconciling_again_changes_nothing(conn, ws):  # noqa: F811
    _, wid = ws
    fx = played(conn, wid, HOME, AWAY, 3, (2, 1))
    reconcile(conn, fx["id"])
    assert reconcile(conn, fx["id"], NOW + timedelta(hours=1))["status"] == "unchanged"
    assert len(evals(conn, fx["id"])) == 1 and len(hist_rows(conn, wid)) == 1
    assert conn.execute("select count(*) n from football_result_history where fixture_id=%s", (fx["id"],)).fetchone()["n"] == 1
    assert conn.execute("select count(*) n from football_predictions p join football_prediction_outcomes o on o.prediction_id=p.id where p.workspace_id=%s and p.kind='live'", (wid,)).fetchone()["n"] == 1


@pytest.mark.parametrize("status", ["scheduled", "in_play", "paused", "postponed", "suspended", "cancelled", "awarded"])
def test_only_finished_matches_are_scored(conn, ws, status):  # noqa: F811
    _, wid = ws
    fx = played(conn, wid, HOME, AWAY, 3, (2, 1))
    conn.execute("update football_fixtures set status=%s where id=%s", (status, fx["id"]))
    r = reconcile(conn, fx["id"])
    assert r["status"] == "ineligible" and evals(conn, fx["id"]) == [] and hist_rows(conn, wid) == []


def test_unverified_or_implausible_results_are_not_scored(conn, ws):  # noqa: F811
    _, wid = ws
    fx = played(conn, wid, HOME, AWAY, 3, (2, 1))
    conn.execute("update football_fixtures set home_goals=null, away_goals=null where id=%s", (fx["id"],))
    assert "full-time score" in reconcile(conn, fx["id"])["reason"]
    conn.execute("update football_fixtures set home_goals=2, away_goals=1 where id=%s", (fx["id"],))
    early = fixture_row(conn, fx["id"])["kickoff_utc"] + timedelta(minutes=30)             # reported finished 30 minutes after kickoff
    r = res.reconcile_fixture(conn, fixture_row(conn, fx["id"]), early)
    assert r["status"] == "ineligible" and "not believed" in r["reason"] and evals(conn, fx["id"]) == [] and hist_rows(conn, wid) == []


def test_a_match_without_an_official_forecast_still_reaches_the_history_but_is_not_scored(conn, ws):  # noqa: F811
    _, wid = ws
    fx = played(conn, wid, HOME, AWAY, 3, (0, 0), forecast=False)
    r = reconcile(conn, fx["id"])
    assert r["status"] == "no_forecast" and "nothing to score" in r["reason"] and evals(conn, fx["id"]) == [] and len(hist_rows(conn, wid)) == 1


def test_the_official_version_is_the_one_scored(conn, ws):  # noqa: F811
    _, wid = ws
    kick = NOW - timedelta(days=3)
    fx = add_fixture(conn, wid, kick=kick)
    ff.generate_version(conn, fx, "discovery", "First.", kick - timedelta(days=2))
    moved = kick + timedelta(minutes=1)                                                    # a change of kickoff time makes a second version
    conn.execute("update football_fixtures set kickoff_utc=%s where id=%s", (moved, fx["id"]))
    ff.generate_version(conn, fixture_row(conn, fx["id"]), "reschedule", "Moved.", kick - timedelta(hours=5))
    conn.execute("update football_fixtures set status='finished', home_goals=1, away_goals=0 where id=%s", (fx["id"],))
    vs = versions(conn, fx["id"])
    assert [v["is_official"] for v in vs] == [False, True]
    reconcile(conn, fx["id"])
    assert [e["version_id"] for e in evals(conn, fx["id"])] == [vs[1]["id"]]


# ---- corrections, conflicts, withdrawals --------------------------------------------------------------------------------------------

def test_a_corrected_score_is_rescored_and_counted(client, conn, ws):  # noqa: F811
    h, wid = ws
    fx = played(conn, wid, HOME, AWAY, 3, (2, 1))
    reconcile(conn, fx["id"])
    first = evals(conn, fx["id"])[0]
    conn.execute("update football_fixtures set home_goals=1, away_goals=1 where id=%s", (fx["id"],))                # the provider corrects the score
    r = reconcile(conn, fx["id"], NOW + timedelta(hours=2))
    assert r["status"] == "evaluated" and r["correction"] is True and r["revision"] == 2 and r["history"] == "updated"
    ev = evals(conn, fx["id"])
    assert len(ev) == 1 and ev[0]["id"] == first["id"] and ev[0]["outcome"] == 1 and ev[0]["correction_count"] == 1 and ev[0]["log_loss"] != first["log_loss"]
    assert [(x["revision"], x["home_goals"], x["away_goals"]) for x in conn.execute("select * from football_result_history where fixture_id=%s order by revision", (fx["id"],)).fetchall()] == [(1, 2, 1), (2, 1, 1)]
    assert (hist_rows(conn, wid)[0]["home_goals"], hist_rows(conn, wid)[0]["away_goals"]) == (1, 1) and len(hist_rows(conn, wid)) == 1
    out = conn.execute("select o.outcome from football_predictions p join football_prediction_outcomes o on o.prediction_id=p.id where p.workspace_id=%s and p.kind='live'", (wid,)).fetchall()
    assert [o["outcome"] for o in out] == [1]                                                                         # the tracking tables were re-scored, not duplicated
    assert fixture_row(conn, fx["id"])["result_note"] == "Score corrected by the provider and re-scored."
    m = client.get(f"/api/v1/football/live/fixtures/{fx['id']}/match", headers=h).json()["result"]["evaluation"]
    assert m["stored"] is True and m["correction_count"] == 1 and "corrected this score 1 time" in m["note"] and m["outcome"] == "draw"


def test_a_different_score_from_an_upload_is_never_overwritten(client, conn, ws):  # noqa: F811
    h, wid = ws
    d = (NOW - timedelta(days=3)).date()
    assert post(client, h, "import", {"filename": "E0.csv", "combined": True, "csv": five_csv([(d, HOME, AWAY, 0, 3)])}).status_code == 200
    fx = played(conn, wid, HOME, AWAY, 3, (2, 1))
    assert fixture_row(conn, fx["id"])["fixture_date"] == d
    r = reconcile(conn, fx["id"])
    assert r["status"] == "conflict" and "not overwritten" in r["reason"] and evals(conn, fx["id"]) == []
    row = conn.execute("select home_goals, away_goals, source_provider from match_history where workspace_id=%s and match_date=%s and home_team=%s", (wid, d, HOME)).fetchone()
    assert (row["home_goals"], row["away_goals"], row["source_provider"]) == (0, 3, "user_upload") and fixture_row(conn, fx["id"])["reconciled_at"] is None
    assert "differs from a result already stored" in fixture_row(conn, fx["id"])["result_note"]


def test_an_identical_upload_is_not_a_conflict(client, conn, ws):  # noqa: F811
    h, wid = ws
    d = (NOW - timedelta(days=3)).date()
    post(client, h, "import", {"filename": "E0.csv", "combined": True, "csv": five_csv([(d, HOME, AWAY, 2, 1)])})
    fx = played(conn, wid, HOME, AWAY, 3, (2, 1))
    r = reconcile(conn, fx["id"])
    assert r["status"] == "evaluated" and r["history"] == "unchanged" and len(evals(conn, fx["id"])) == 1


def test_a_match_the_provider_withdraws_stops_counting(conn, ws):  # noqa: F811
    _, wid = ws
    fx = played(conn, wid, HOME, AWAY, 3, (2, 1))
    reconcile(conn, fx["id"])
    conn.execute("update football_fixtures set status='cancelled' where id=%s", (fx["id"],))                        # the result was struck out
    r = reconcile(conn, fx["id"], NOW + timedelta(hours=1))
    assert r["status"] == "voided" and r["voided_evaluations"] == 1
    e = evals(conn, fx["id"])[0]
    assert e["voided_at"] and "cancelled" in e["void_reason"] and hist_rows(conn, wid) == []
    assert conn.execute("select count(*) n from football_predictions p join football_prediction_outcomes o on o.prediction_id=p.id where p.workspace_id=%s and p.kind='live'", (wid,)).fetchone()["n"] == 0
    f = fixture_row(conn, fx["id"])
    assert f["reconciled_at"] is None and "withdrawn" in f["result_note"]
    assert perf.summary(conn, wid)["overall"] == {"n": 0}
    conn.execute("update football_fixtures set status='finished' where id=%s", (fx["id"],))                         # and if it is reinstated, it is scored again
    assert reconcile(conn, fx["id"], NOW + timedelta(hours=2))["status"] == "evaluated"
    assert evals(conn, fx["id"])[0]["voided_at"] is None and perf.summary(conn, wid)["overall"]["n"] == 1


# ---- the scheduled pass -------------------------------------------------------------------------------------------------------------

def test_the_workspace_pass_picks_up_only_what_needs_reconciling_and_survives_a_failure(conn, ws, monkeypatch):  # noqa: F811
    _, wid = ws
    a = played(conn, wid, HOME, AWAY, 3, (2, 1))
    b = played(conn, wid, OTHERS[0], OTHERS[1], 4, (0, 1))
    played(conn, wid, OTHERS[2], OTHERS[3], 5, (1, 1))
    conn.execute("update football_fixtures set status='scheduled' where workspace_id=%s and home_team=%s", (wid, OTHERS[2]))
    real = res.reconcile_fixture
    monkeypatch.setattr(res, "reconcile_fixture", lambda c, fx, n: (_ for _ in ()).throw(RuntimeError("boom")) if fx["id"] == a["id"] else real(c, fx, n))
    out = res.reconcile_workspace(conn, wid, NOW)
    assert (out["considered"], out["evaluated"], out["errors"]) == (2, 1, 1) and len(evals(conn, b["id"])) == 1 and evals(conn, a["id"]) == []
    monkeypatch.setattr(res, "reconcile_fixture", real)
    again = res.reconcile_workspace(conn, wid, NOW)
    assert (again["considered"], again["evaluated"]) == (1, 1)                                 # the failed one is retried, the done one is not touched
    assert res.reconcile_workspace(conn, wid, NOW)["considered"] == 0
    assert res.reconcile_workspace(conn, wid, NOW, limit=0)["considered"] == 0


def test_the_tick_reconciles_and_records_what_it_did(conn, ws):  # noqa: F811
    _, wid = ws
    fx = played(conn, wid, HOME, AWAY, 3, (2, 1))
    out = fr.tick_workspace(conn, wid, NOW)
    assert out["results"]["evaluated"] == 1 and out["status"] == "acted" and len(evals(conn, fx["id"])) == 1
    assert fr.tick_workspace(conn, wid, NOW + timedelta(minutes=10))["results"]["evaluated"] == 0


# ---- performance and reports --------------------------------------------------------------------------------------------------------

def _scored(conn, wid, n=4):
    pairs = [(HOME, AWAY, (2, 1)), (OTHERS[0], OTHERS[1], (0, 0)), (OTHERS[2], OTHERS[3], (1, 2)), (OTHERS[4], OTHERS[5], (3, 0))][:n]
    ids = []
    for i, (h, a, sc) in enumerate(pairs):
        fx = played(conn, wid, h, a, 3 + i, sc)
        assert reconcile(conn, fx["id"])["status"] == "evaluated"
        ids.append(fx["id"])
    return ids


def test_the_summary_aggregates_official_evaluations_against_the_no_information_baseline(conn, ws):  # noqa: F811
    _, wid = ws
    ids = _scored(conn, wid)
    s = perf.summary(conn, wid)
    rows = [evals(conn, i)[0] for i in ids]
    o = s["overall"]
    assert o["n"] == 4 and abs(o["log_loss"] - sum(r["log_loss"] for r in rows) / 4) < 1e-3 and abs(o["brier"] - sum(r["brier"] for r in rows) / 4) < 1e-3
    assert o["accuracy"] == sum(1 for r in rows if r["correct"]) / 4 and o["enough_matches_to_judge"] is False and "Fewer than 30" in s["note"]
    assert abs(o["vs_no_information"]["log_loss"] - (math.log(3) - o["log_loss"])) < 1e-3 and o["beats_no_information"] == (o["log_loss"] < math.log(3))
    assert list(s["by_model"]) == ["dixon_coles"] and s["by_model"]["dixon_coles"]["n"] == 4
    assert sum(b["n"] for b in s["home_win_calibration"]) == 4 and len(s["best"]) == 3 and s["baseline"]["log_loss"] == round(math.log(3), 4)
    assert perf.summary(conn, wid, model="ensemble")["overall"] == {"n": 0}
    assert perf.summary(conn, wid, since=NOW + timedelta(days=1))["overall"] == {"n": 0}


def test_daily_and_weekly_reports_are_made_once_and_only_when_something_was_scored(conn, ws):  # noqa: F811
    _, wid = ws
    assert perf.make_reports(conn, wid, NOW) == {"created": []}                                    # nothing scored: no empty report
    _scored(conn, wid, 2)
    today = datetime.combine(NOW.date(), datetime.min.time(), tzinfo=timezone.utc)
    yday_noon = today - timedelta(hours=12)
    monday = today - timedelta(days=today.weekday())
    conn.execute("update football_prediction_evaluations set evaluated_at=%s where workspace_id=%s", (yday_noon, wid))
    made = perf.make_reports(conn, wid, NOW)
    assert "daily" in made["created"]
    assert perf.make_reports(conn, wid, NOW) == {"created": []}                                    # once only
    d = conn.execute("select * from football_performance_reports where workspace_id=%s and period='daily'", (wid,)).fetchone()
    assert d["window_end"] == today and d["window_start"] == today - timedelta(days=1) and d["summary"]["overall"]["n"] == 2 and d["summary"]["cumulative"]["n"] == 2
    if yday_noon >= monday - timedelta(days=7) and yday_noon < monday:                               # yesterday fell in the previous week (today is Monday)
        assert "weekly" in made["created"]
    conn.execute("update football_prediction_evaluations set evaluated_at=%s where workspace_id=%s", (monday - timedelta(days=3), wid))
    wk = perf.make_reports(conn, wid, NOW)
    assert "weekly" in wk["created"] or conn.execute("select 1 from football_performance_reports where workspace_id=%s and period='weekly'", (wid,)).fetchone()
    w = conn.execute("select * from football_performance_reports where workspace_id=%s and period='weekly'", (wid,)).fetchone()
    assert w["window_end"] == monday and w["window_start"] == monday - timedelta(days=7) and w["summary"]["overall"]["n"] == 2


# ---- API ----------------------------------------------------------------------------------------------------------------------------

def test_performance_endpoints_and_manual_reconcile(client, conn, ws):  # noqa: F811
    h, wid = ws
    ids = _scored(conn, wid, 2)
    g = client.get("/api/v1/football/live/performance", headers=h).json()
    assert g["overall"]["n"] == 2 and g["days"] is None and client.get("/api/v1/football/live/performance?days=1", headers=h).json()["overall"]["n"] == 2
    conn.execute("update football_prediction_evaluations set evaluated_at=%s where workspace_id=%s", (NOW - timedelta(days=30), wid))
    assert client.get("/api/v1/football/live/performance?days=7", headers=h).json()["overall"] == {"n": 0}
    assert client.get("/api/v1/football/live/performance?model=nope", headers=h).status_code == 422
    assert client.get("/api/v1/football/live/performance/reports?period=monthly", headers=h).status_code == 422
    assert client.get("/api/v1/football/live/performance/reports", headers=h).json() == {"reports": [], "total": 0}
    url = f"/api/v1/football/live/fixtures/{ids[0]}/reconcile"
    assert client.post(url, headers=h).json()["status"] == "unchanged"                          # already done: safe to repeat
    viewer = hdr(make_user(conn, role="viewer", workspace_id=wid)[0], wid, exp_in=900)
    assert client.post(url, headers=viewer).status_code == 403 and client.get("/api/v1/football/live/performance", headers=viewer).status_code == 200
    ou, ow = make_user(conn)
    other = hdr(ou, ow, exp_in=900)
    assert client.post(url, headers=other).status_code == 404 and client.get("/api/v1/football/live/performance", headers=other).json()["overall"] == {"n": 0}
    assert client.post("/api/v1/football/live/fixtures/nonsense/reconcile", headers=h).status_code == 404


def test_the_match_page_uses_the_stored_evaluation_once_it_exists(client, conn, ws):  # noqa: F811
    h, wid = ws
    fx = played(conn, wid, HOME, AWAY, 3, (2, 1))
    url = f"/api/v1/football/live/fixtures/{fx['id']}/match"
    before = client.get(url, headers=h).json()["result"]["evaluation"]
    assert before["stored"] is False and "not stored" in before["note"]
    reconcile(conn, fx["id"])
    after = client.get(url, headers=h).json()["result"]["evaluation"]
    assert after["stored"] is True and after["rps"] > 0 and after["version_no"] == 1 and abs(after["log_loss"] - before["log_loss"]) < 1e-3 and "Scored automatically" in after["note"]
    conn.execute("update football_fixtures set status='awarded' where id=%s", (fx["id"],))
    aw = client.get(url, headers=h).json()["result"]["evaluation"]
    assert aw["available"] is False and "off the pitch" in aw["note"]
