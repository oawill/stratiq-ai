"""Boosted trees, the calibrated ensemble, drift monitoring, retraining policy and scheduled jobs.
All data is SYNTHETIC (real club names, random scores). Nothing here says anything about real forecasting accuracy."""
import math
import random
from datetime import date, timedelta

import pytest

from stratiq import football_backtest as fb
from stratiq import football_ensemble as fe
from stratiq import football_gbm as gb
from stratiq import football_jobs as jobs
from stratiq import football_models as fm
from stratiq import football_monitor as mon
from .conftest import hdr, make_user
from .test_football_intel import FIVE, SPLIT, get, load, post, seasons, tamper


@pytest.fixture()
def ws(client, conn):
    uid, wid = make_user(conn)
    return hdr(uid, wid, exp_in=900), wid      # retraining takes longer than the default 60-second test token


def ll(probs, ys):
    return sum(-math.log(max(p[y], 1e-12)) for p, y in zip(probs, ys)) / len(ys)


# ------------------------------------------------------------------ features
def test_features_never_use_that_days_or_later_results():
    ms = sorted(FIVE[:700], key=lambda m: (m[0], m[1], m[2]))
    day = ms[500][0]
    pre, _ = fm.elo_pass(ms, fm.EloParams())
    a = gb.feature_rows(ms, pre, 65.0)
    ms2 = tamper(ms, day)
    pre2, _ = fm.elo_pass(ms2, fm.EloParams())
    b = gb.feature_rows(ms2, pre2, 65.0)
    upto = sum(1 for m in ms if m[0] <= day)
    assert a[:upto] == b[:upto] and a != b          # every match ON the day is described from before the day


def test_a_club_with_no_history_gets_neutral_features_not_errors():
    x = gb.live_vector([], "Arsenal", "Chelsea", date(2025, 8, 1), 0.0)
    assert len(x) == len(gb.FEATURES) and all(math.isfinite(v) for v in x)


# ------------------------------------------------------------------ boosted trees
def synthetic(n, seed):
    rnd = random.Random(seed)
    X, y = [], []
    for _ in range(n):
        a, noise = rnd.uniform(-2, 2), rnd.uniform(-2, 2)
        x = [a] + [noise * rnd.random() for _ in range(len(gb.FEATURES) - 1)]
        pa = fm.sigmoid(2.0 * a)
        u = rnd.random()
        X.append(x)
        y.append(0 if u < pa * 0.7 else 2 if u > 1 - (1 - pa) * 0.7 else 1)
    return X, y


def test_boosted_trees_learn_a_known_signal_and_beat_the_base_rate():
    X, y = synthetic(2400, 1)
    Xt, yt = synthetic(1200, 2)
    model = gb.fit(X[:1800], y[:1800], None, X[1800:], y[1800:])
    base = [math.log(max(sum(1 for v in y if v == k) / len(y), 1e-9)) for k in range(3)]
    flat = [gb._softmax(base)] * len(yt)
    assert ll([gb.predict(model, x) for x in Xt], yt) < ll(flat, yt) - 0.05
    assert next(iter(model["importance"])) == "elo_gap"             # feature 0 is the informative one
    for x in Xt[:20]:
        p = gb.predict(model, x)
        assert abs(sum(p) - 1) < 1e-9 and min(p) > 0


def test_boosted_trees_are_deterministic_and_serialisable():
    import json
    X, y = synthetic(900, 3)
    a = gb.fit(X, y, {"max_rounds": 15})
    b = gb.fit(X, y, {"max_rounds": 15})
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    c = json.loads(json.dumps(a))
    assert gb.predict(c, X[0]) == gb.predict(a, X[0])


def test_boosted_trees_refuse_to_train_on_too_little_data():
    X, y = synthetic(60, 4)
    with pytest.raises(ValueError):
        gb.fit(X, y)


def test_validation_rows_stop_training_early_and_pick_the_best_round_count():
    X, y = synthetic(1500, 5)
    m = gb.fit(X[:1000], y[:1000], {"max_rounds": 150}, X[1000:], y[1000:])
    assert 1 <= m["rounds"] <= 150 and len(m["trees"]) == m["rounds"]
    assert m["validation_curve"][m["rounds"] - 1] == min(m["validation_curve"])


# ------------------------------------------------------------------ ensemble
def truth(n, seed):
    rnd = random.Random(seed)
    P, y = [], []
    for _ in range(n):
        raw = [rnd.uniform(0.2, 1.0), rnd.uniform(0.2, 0.8), rnd.uniform(0.2, 1.0)]
        t = sum(raw)
        p = [v / t for v in raw]
        u = rnd.random()
        P.append(p)
        y.append(0 if u < p[0] else 1 if u < p[0] + p[1] else 2)
    return P, y


def test_ensemble_weights_sum_to_one_and_favour_the_better_member():
    P, y = truth(800, 1)
    uniform = [[1 / 3] * 3 for _ in P]
    e = fe.fit_ensemble({"good": P, "bad": uniform}, y)
    assert abs(sum(e["weights"].values()) - 1) < 1e-9
    assert e["weights"]["good"] >= 0.8
    assert e["validation_log_loss_calibrated"] <= e["validation_log_loss_pooled"] + 1e-9


def test_ensemble_calibration_softens_an_overconfident_model():
    P, y = truth(2000, 2)
    sharp = [fe.temper(p, 1 / 1.6) for p in P]                    # the same ranking, but 1.6x too confident
    e = fe.fit_ensemble({"sharp": sharp}, y)
    assert 1.3 < e["temperature"] <= 1.8
    assert e["validation_log_loss_calibrated"] < ll(sharp, y) - 0.005
    out = fe.apply_ensemble(e, {"sharp": sharp[0]})
    assert abs(sum(out) - 1) < 1e-9 and max(out) < max(sharp[0])


def test_ensemble_needs_enough_validation_matches():
    with pytest.raises(ValueError):
        fe.fit_ensemble({"a": [[0.4, 0.3, 0.3]] * 10}, [0] * 10)


# ------------------------------------------------------------------ backtest integration
def test_chronological_backtest_reports_boosted_trees_and_ensemble_and_never_tunes_on_the_test_period():
    r = fb.run_chronological(FIVE, SPLIT)
    for period in ("validation", "test"):
        assert {"gbm", "ensemble"} <= set(r["results"][period])
        assert r["results"][period]["ensemble"]["1x2"]["n"] == r["results"][period]["gbm"]["1x2"]["n"]
        assert "vs_dixon_coles" in r["results"][period]["gbm"]["gain"]
    ens = r["tuning"]["ensemble"]
    assert set(ens["members"]) == {"elo", "dixon_coles", "gbm"} and abs(sum(ens["weights"].values()) - 1) < 1e-9
    assert r["tuning"]["gbm"]["model_for_test"]["training_matches"] > r["tuning"]["gbm"]["importance_validation_fit"].__len__()
    # Corrupt every test-period result: nothing fitted on training/validation may change.
    first_test = min(date.fromisoformat(p["date"]) for p in r["predictions"] if p["period"] == "test")
    r2 = fb.run_chronological(tamper(FIVE, first_test), SPLIT)
    assert r2["tuning"]["ensemble"] == r["tuning"]["ensemble"]
    assert r2["tuning"]["gbm"]["chosen"] == r["tuning"]["gbm"]["chosen"] and r2["tuning"]["gbm"]["grid"] == r["tuning"]["gbm"]["grid"]
    assert r2["results"]["validation"]["gbm"] == r["results"]["validation"]["gbm"]
    assert r2["results"]["validation"]["ensemble"] == r["results"]["validation"]["ensemble"]


def test_gbm_and_ensemble_rows_have_valid_probabilities():
    r = fb.run_chronological(FIVE, SPLIT)
    rows = [p for p in r["predictions"] if p["model"] in ("gbm", "ensemble")]
    assert rows and all(abs(sum(p["probs"]) - 1) < 1e-9 and min(p["probs"]) >= 0 for p in rows)


# ------------------------------------------------------------------ monitoring
def losses(n, mean, spread=0.3, seed=1):
    rnd = random.Random(seed)
    return [max(0.05, rnd.gauss(mean, spread)) for _ in range(n)]


def scored(ls, p_home=0.45, rate=0.45, seed=2):
    rnd = random.Random(seed)
    return [{"log_loss": x, "p_home": p_home, "home_win": rnd.random() < rate} for x in ls]


def test_drift_says_nothing_with_too_few_results():
    base = mon.baseline_from(losses(500, 1.0))
    r = mon.drift_report(scored(losses(10, 1.5)), base)
    assert r["status"] == "insufficient" and "at least 30" in r["note"]
    assert mon.drift_report(scored(losses(60, 1.0)), None)["status"] == "insufficient"


def test_drift_is_ok_when_live_matches_the_baseline_and_flags_a_real_degradation():
    base = mon.baseline_from(losses(600, 1.0, 0.3, 1))
    assert mon.drift_report(scored(losses(60, 1.0, 0.3, 5), rate=0.45), base)["status"] == "ok"
    bad = mon.drift_report(scored(losses(60, 1.25, 0.3, 6), rate=0.45), base)
    assert bad["status"] == "drift" and bad["performance"]["excess"] > 0.15


def test_a_statistically_detectable_but_tiny_loss_increase_is_not_called_drift():
    base = {"mean": 1.0, "std": 0.05, "n": 500}
    r = mon.drift_report(scored([1.02] * 60), base)
    assert r["performance"]["z"] > 3 and r["performance"]["status"] == "watch"


def test_calibration_drift_is_flagged_when_home_wins_are_much_rarer_than_predicted():
    base = mon.baseline_from(losses(600, 1.0, 0.3, 1))
    r = mon.drift_report(scored(losses(60, 1.0, 0.3, 7), p_home=0.6, rate=0.2, seed=8), base)
    assert r["calibration"]["status"] == "drift" and r["status"] == "drift"


def test_retrain_policy_reasons():
    none = mon.retrain_decision(has_run=True, matches_since_run=10, days_since_run=20, drift_status="ok")
    assert not none["retrain"] and none["reasons"] == []
    assert mon.retrain_decision(has_run=False, matches_since_run=0, days_since_run=None, drift_status="insufficient")["retrain"]
    assert mon.retrain_decision(has_run=True, matches_since_run=100, days_since_run=5, drift_status="ok")["retrain"]
    assert mon.retrain_decision(has_run=True, matches_since_run=0, days_since_run=500, drift_status="ok")["retrain"] is False   # old but nothing new
    assert mon.retrain_decision(has_run=True, matches_since_run=25, days_since_run=100, drift_status="ok")["retrain"]
    assert mon.retrain_decision(has_run=True, matches_since_run=1, days_since_run=5, drift_status="drift")["retrain"]
    assert mon.retrain_decision(has_run=True, matches_since_run=1, days_since_run=5, drift_status="watch")["retrain"] is False


def test_challenger_is_accepted_unless_clearly_worse():
    assert mon.accept_challenger(None, 1.0)["accept"]
    assert mon.accept_challenger(1.0, 1.003)["accept"]
    assert not mon.accept_challenger(1.0, 1.02)["accept"]
    assert not mon.accept_challenger(1.0, None)["accept"]


def test_rolling_split_moves_forward_with_new_seasons():
    a = jobs.rolling_split(seasons(range(2020, 2025)))
    b = jobs.rolling_split(seasons(range(2020, 2026)))
    assert a == {"training": ["2020/21", "2021/22"], "validation": ["2022/23"], "test": ["2023/24", "2024/25"]}
    assert b["test"] == ["2024/25", "2025/26"] and b["validation"] == ["2023/24"]
    with pytest.raises(ValueError):
        jobs.rolling_split(seasons(range(2020, 2023)))


# ------------------------------------------------------------------ API and jobs (database)
def test_match_forecast_includes_boosted_trees_and_ensemble_after_a_backtest_but_not_in_what_ifs(client, ws):
    h, wid = ws
    load(client, h, FIVE)
    before = post(client, h, "intel/match", {"home": "Arsenal", "away": "Chelsea", "kickoff": "2025-04-01"}).json()
    assert "gbm" not in before["forecasts"]                      # nothing is tuned, so there are no trees yet
    assert post(client, h, "intel/backtest", {"mode": "chronological", "split": SPLIT}).status_code == 200
    m = post(client, h, "intel/match", {"home": "Arsenal", "away": "Chelsea", "kickoff": "2025-04-01", "adjust": {"home_attack_multiplier": 1.1}}).json()
    assert {"gbm", "ensemble"} <= set(m["forecasts"])
    for k in ("gbm", "ensemble"):
        f = m["forecasts"][k]
        assert abs(f["p_home"] + f["p_draw"] + f["p_away"] - 1) < 1e-6
    assert "gbm" not in m["scenario"]["forecasts"] and "ensemble" not in m["scenario"]["forecasts"]
    saved = post(client, h, "intel/match", {"home": "Arsenal", "away": "Chelsea", "kickoff": "2025-04-01", "save": True}).json()
    assert {"gbm", "ensemble"} <= set(saved["saved"]["prediction_ids"])


def test_status_and_manual_retrain_with_the_acceptance_guard(client, conn, ws):
    h, wid = ws
    load(client, h, FIVE)
    s = get(client, h, "jobs/status").json()
    assert s["monitor"]["retrain"]["retrain"] and "No backtest" in s["monitor"]["retrain"]["reasons"][0] and s["scheduler_configured"] is False
    r = post(client, h, "jobs/retrain", {}).json()
    assert r["status"] == "complete" and r["accepted"] is True and r["split"]["test"] == ["2023/24", "2024/25"]
    again = post(client, h, "jobs/retrain", {}).json()
    assert again["status"] == "skipped" and again["reason"] == "Retraining is not due."
    # A forced retrain whose validation result is clearly worse than the previous run is kept for review but not made live.
    live = conn.execute("select id from football_backtest_runs where workspace_id=%s and status='complete' order by created_at desc limit 1", (wid,)).fetchone()["id"]
    conn.execute("update football_backtest_runs set results = jsonb_set(results, '{validation,ensemble,1x2,log_loss}', '0.5') where id=%s", (live,))
    fr = post(client, h, "jobs/retrain", {"force": True})
    assert fr.status_code == 200, fr.text[:800]
    forced = fr.json()
    assert forced["status"] == "complete" and forced["accepted"] is False
    assert conn.execute("select status from football_backtest_runs where id=%s", (forced["run_id"],)).fetchone()["status"] == "rejected"
    assert str(jobs.api._latest_run(conn, jobs.system_principal(wid))["id"]) == str(live)
    resp = get(client, h, "jobs/status")
    assert resp.status_code == 200, resp.text[:600]
    kinds = [r["kind"] for r in resp.json()["runs"]]
    assert kinds.count("retrain") >= 3


def test_monitor_job_scores_finished_forecasts_and_reports_insufficient_evidence_honestly(client, ws):
    h, wid = ws
    load(client, h, FIVE)
    post(client, h, "intel/backtest", {"mode": "chronological", "split": SPLIT})
    post(client, h, "intel/match", {"home": "Arsenal", "away": "Chelsea", "kickoff": "2025-04-01", "save": True})
    out = post(client, h, "jobs/monitor", {}).json()
    assert out["monitor"]["drift"]["status"] == "insufficient" and out["monitor"]["model"] == "ensemble"


def test_scheduled_endpoint_is_off_without_a_secret_and_rejects_a_wrong_one(client, monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    assert client.post("/api/v1/football/jobs/scheduled").status_code == 404
    monkeypatch.setenv("CRON_SECRET", "s" * 24)
    assert client.get("/api/v1/football/jobs/scheduled").status_code == 401
    assert client.get("/api/v1/football/jobs/scheduled", headers={"Authorization": "Bearer nope"}).status_code == 401
    monkeypatch.setattr(jobs, "run_all", lambda conn, trigger: {"workspaces": 0, "retrained": 0, "results": [], "trigger": trigger})
    ok = client.get("/api/v1/football/jobs/scheduled", headers={"Authorization": "Bearer " + "s" * 24})
    assert ok.status_code == 200 and ok.json()["trigger"] == "schedule"


def test_a_scheduled_cycle_scores_forecasts_upcoming_fixtures_and_records_the_run(client, conn, ws):
    h, wid = ws
    load(client, h, FIVE)
    post(client, h, "intel/backtest", {"mode": "chronological", "split": SPLIT})
    last = max(m[0] for m in FIVE)
    today = last + timedelta(days=3)
    conn.execute("insert into football_fixtures (workspace_id, competition, season, fixture_date, home_team, away_team) values (%s,'EPL','2025/26',%s,'Arsenal','Chelsea')", (wid, today + timedelta(days=2)))
    out = jobs.run_workspace(conn, wid, "schedule", True, today)
    assert out["status"] == "complete" and out["upcoming"]["forecast"] == 1 and out["upcoming"]["errors"] == []
    n = conn.execute("select count(*) n from football_predictions where workspace_id=%s and kind='live'", (wid,)).fetchone()["n"]
    assert n >= 5                                                 # one per model
    rec = conn.execute("select kind, trigger, status from football_job_runs where workspace_id=%s", (wid,)).fetchall()
    assert rec == [{"kind": "scheduled", "trigger": "schedule", "status": "complete"}]
