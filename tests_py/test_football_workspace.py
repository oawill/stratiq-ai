"""The football model interface, data freshness, fixtures and results, saved predictions and team intelligence.
All data is SYNTHETIC (real club names, random scores). Nothing here says anything about real forecasting accuracy."""
import math
from datetime import date, datetime, timedelta, timezone

import pytest

from stratiq import football_intel as fi
from stratiq import football_interface as fx
from stratiq import football_models as fm
from stratiq.football_intel_api import freshness_of
from .conftest import hdr, make_user
from .test_football_intel import FIVE, SPLIT, load, post, tamper

MS = sorted(FIVE, key=lambda m: (m[0], m[1], m[2]))
CUTOFF = MS[1200][0]
PRIOR = [m for m in MS if m[0] < CUTOFF]


# ------------------------------------------------------------------ model interface
@pytest.mark.parametrize("name", ["poisson", "dixon_coles", "elo"])
def test_every_registered_model_returns_a_normalised_forecast_with_full_provenance(name):
    f = fx.forecast(name, MS, "Arsenal", "Chelsea", CUTOFF)
    assert abs(sum(f.probs) - 1) < 1e-9 and min(f.probs) > 0
    assert f.model == name and f.version and f.training_cutoff == CUTOFF and f.matches_used == len(PRIOR)
    assert f.data_through < CUTOFF and f.data_through == max(m[0] for m in PRIOR) and f.data_age_days == (CUTOFF - f.data_through).days
    assert abs((datetime.now(timezone.utc) - f.generated_at).total_seconds()) < 60
    assert f.explanation and all("factor" in e for e in f.explanation)


def test_poisson_gives_expected_goals_and_the_five_likeliest_scorelines():
    f = fx.forecast("poisson", MS, "Arsenal", "Chelsea", CUTOFF)
    assert f.expected_goals[0] > 0 and f.expected_goals[1] > 0
    top = f.top_scorelines
    assert len(top) == 5 and [t["p"] for t in top] == sorted((t["p"] for t in top), reverse=True)
    assert 0 < sum(t["p"] for t in top) < 1
    assert 0 < f.p_over_2_5 < 1 and 0 < f.p_btts < 1
    assert fx.forecast("elo", MS, "Arsenal", "Chelsea", CUTOFF).expected_goals is None          # a results-only rating model does not forecast goals


def test_the_interface_agrees_with_the_live_forecast_used_by_the_application():
    f = fx.forecast("poisson", MS, "Arsenal", "Chelsea", CUTOFF)
    live = fi.live_forecast(MS, "Arsenal", "Chelsea", CUTOFF)["poisson"]
    assert all(abs(a - b) < 1e-9 for a, b in zip(f.probs, live["probs"]))
    assert abs(f.expected_goals[0] - live["expected_goals"][0]) < 1e-9


def test_forecasts_ignore_every_match_on_or_after_the_cutoff():
    for name in ("poisson", "dixon_coles", "elo"):
        a = fx.forecast(name, MS, "Arsenal", "Chelsea", CUTOFF)
        b = fx.forecast(name, tamper(MS, CUTOFF), "Arsenal", "Chelsea", CUTOFF)
        assert a.probs == b.probs and a.matches_used == b.matches_used and a.data_through == b.data_through


def test_too_little_history_is_refused_rather_than_guessed():
    with pytest.raises(ValueError, match="Fewer than 30 matches"):
        fx.forecast("poisson", MS[:40], "Arsenal", "Chelsea", MS[10][0])


def test_dixon_coles_changes_only_the_low_score_cells():
    p, d = fx.forecast("poisson", MS, "Arsenal", "Chelsea", CUTOFF), fx.forecast("dixon_coles", MS, "Arsenal", "Chelsea", CUTOFF)
    assert d.probs != p.probs and abs(sum(d.probs) - 1) < 1e-9 and d.expected_goals == p.expected_goals


def test_elo_favours_the_stronger_club_and_the_registry_is_extensible_but_not_overwritable():
    fit = fx.get_model("elo").fit(MS, CUTOFF)
    ranked = sorted(fit.ratings, key=fit.ratings.get)
    weak, strong = ranked[0], ranked[-1]
    assert fx.get_model("elo").forecast(fit, strong, weak, CUTOFF).p_home > fx.get_model("elo").forecast(fit, weak, strong, CUTOFF).p_home

    class Flat:
        name, version = "flat_test_model", "0.0.1"

        def fit(self, matches, cutoff):
            return len([m for m in matches if m[0] < cutoff])

        def forecast(self, fitted, home, away, cutoff):
            return fx.Forecast(self.name, self.version, home, away, 0.4, 0.3, 0.3, cutoff, None, fitted, datetime.now(timezone.utc))

    fx.register(Flat())
    try:
        assert fx.forecast("flat_test_model", MS, "A", "B", CUTOFF).probs == [0.4, 0.3, 0.3]
        with pytest.raises(ValueError, match="already registered"):
            fx.register(Flat())
        with pytest.raises(ValueError, match="Unknown model"):
            fx.get_model("nope")
    finally:
        fx.REGISTRY.pop("flat_test_model", None)


def test_explanations_never_describe_probability_as_accuracy_or_confidence():
    text = " ".join(str(e) for n in ("poisson", "elo") for e in fx.forecast(n, MS, "Arsenal", "Chelsea", CUTOFF).explanation).lower()
    assert "accuracy" not in text and "confidence" not in text
    assert "probabilities are the model's estimate" in fx.__doc__.lower() and "not a confidence score" in fx.__doc__.lower()


# ------------------------------------------------------------------ freshness (pure)
def rows(last, season="2025/26"):
    return [(season, last - timedelta(days=i), "Arsenal", "Chelsea", 1, 0) for i in range(3)][::-1]


def test_freshness_marks_old_data_stale_in_season_and_explains_the_off_season():
    in_season = date(2026, 3, 20)
    ok = freshness_of(rows(date(2026, 3, 15)), 4, None, in_season)
    assert ok["stale"] is False and ok["days_since_last_match"] == 5 and "Up to date" in ok["note"]
    old = freshness_of(rows(date(2026, 2, 1)), 4, None, in_season)
    assert old["stale"] is True and "Import the latest results" in old["note"]
    summer = freshness_of(rows(date(2026, 5, 24)), 0, None, date(2026, 7, 10))
    assert summer["stale"] is False and summer["off_season"] is True and "between seasons" in summer["note"]
    assert freshness_of([], 0, None, in_season) == {"has_history": False, "stale": False, "note": "No match history is imported.", "upcoming_fixtures": 0, "last_import_at": None}


def test_the_current_season_is_reported_separately_and_never_as_complete():
    f = freshness_of(rows(date(2026, 3, 15)), 4, None, date(2026, 3, 20))
    assert f["current_season"]["season"] == "2025/26" and f["current_season"]["matches_stored"] == 3 and "never counted as a complete season" in f["current_season"]["note"]


# ------------------------------------------------------------------ API
@pytest.fixture()
def ws(client, conn):
    uid, wid = make_user(conn)
    return hdr(uid, wid, exp_in=900), wid


def get(client, h, path):
    r = client.get(f"/api/v1/football/{path}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def add_fixture(conn, wid, days_ahead, home="Arsenal", away="Chelsea"):
    d = datetime.now(timezone.utc).date() + timedelta(days=days_ahead)
    conn.execute("insert into football_fixtures (workspace_id, competition, season, fixture_date, home_team, away_team) values (%s,'EPL','2025/26',%s,%s,%s)", (wid, d, home, away))
    return d


def test_freshness_endpoint_before_and_after_an_import(client, ws):
    h, wid = ws
    assert get(client, h, "intel/freshness") ["has_history"] is False
    load(client, h, FIVE)
    f = get(client, h, "intel/freshness")
    assert f["has_history"] and f["last_match"] == max(m[0] for m in FIVE).isoformat() and f["last_import_at"] and f["current_season"]["season"]
    assert isinstance(f["stale"], bool) and f["note"]


def test_schedule_lists_recent_results_and_upcoming_fixtures_without_making_forecasts(client, conn, ws):
    h, wid = ws
    load(client, h, FIVE)
    d1, d2 = add_fixture(conn, wid, 3), add_fixture(conn, wid, 9, "Liverpool", "Everton")
    s = get(client, h, "intel/schedule?results=5&days=30")
    assert len(s["results"]) == 5 and [r["date"] for r in s["results"]] == sorted((r["date"] for r in s["results"]), reverse=True)
    assert [f["date"] for f in s["fixtures"]] == [d1.isoformat(), d2.isoformat()] and not any(f["tracked"] for f in s["fixtures"])
    assert conn.execute("select count(*) n from football_predictions where workspace_id=%s", (wid,)).fetchone()["n"] == 0
    post(client, h, "intel/match", {"home": "Arsenal", "away": "Chelsea", "kickoff": d1.isoformat(), "save": True})
    assert [f["tracked"] for f in get(client, h, "intel/schedule")["fixtures"]] == [True, False]
    assert len(get(client, h, "intel/schedule?days=5")["fixtures"]) == 1


def test_saved_predictions_show_provenance_then_the_result_and_exclude_backtest_rows(client, conn, ws):
    h, wid = ws
    load(client, h, FIVE)
    assert get(client, h, "intel/saved") ["fixtures"] == []
    d = add_fixture(conn, wid, 2)
    post(client, h, "intel/match", {"home": "Arsenal", "away": "Chelsea", "kickoff": d.isoformat(), "save": True})
    s = get(client, h, "intel/saved")
    assert s["total"] == 1
    fx0 = s["fixtures"][0]
    assert fx0["status"] == "waiting" and fx0["result"] is None and len(fx0["forecasts"]) >= 3
    for f in fx0["forecasts"]:
        assert f["version"] and f["made_at"] and f["training_cutoff"] and len(f["data_sha256"]) == 64
        assert abs(f["p_home"] + f["p_draw"] + f["p_away"] - 1) < 1e-6 and f["log_loss"] is None and f["correct"] is None
    post(client, h, "intel/backtest", {"mode": "chronological", "split": SPLIT})
    assert get(client, h, "intel/saved")["total"] == 1                              # the backtest's thousands of historical rows are not "saved predictions"
    conn.execute("insert into match_history (workspace_id, competition, season, match_date, home_team, away_team, home_goals, away_goals) values (%s,'EPL','2025/26',%s,'Arsenal','Chelsea',2,1)", (wid, d))
    assert post(client, h, "intel/reconcile").json()["scored"] >= 3
    done = get(client, h, "intel/saved")["fixtures"][0]
    assert done["status"] == "scored" and done["result"] == "2-1" and done["outcome"] == 0
    assert all(f["log_loss"] is not None and isinstance(f["correct"], bool) for f in done["forecasts"])
    assert "not a confidence score" in get(client, h, "intel/saved")["note"]


def test_saved_predictions_paginate_and_stay_private(client, conn, ws):
    h, wid = ws
    load(client, h, FIVE)
    for i, (a, b) in enumerate([("Arsenal", "Chelsea"), ("Liverpool", "Everton"), ("Aston Villa", "Brentford")]):
        d = add_fixture(conn, wid, 2 + i, a, b)
        post(client, h, "intel/match", {"home": a, "away": b, "kickoff": d.isoformat(), "save": True})
    p1 = get(client, h, "intel/saved?limit=2")
    assert p1["total"] == 3 and len(p1["fixtures"]) == 2
    p2 = get(client, h, "intel/saved?limit=2&offset=2")
    assert len(p2["fixtures"]) == 1 and p2["fixtures"][0]["date"] < p1["fixtures"][-1]["date"]
    other = hdr(*make_user(conn))
    assert get(client, other, "intel/saved") ["total"] == 0


def test_team_intelligence_reports_coverage_sample_sizes_and_rest_days(client, ws):
    h, wid = ws
    load(client, h, FIVE)
    t = get(client, h, "team?team=Arsenal")
    n = t["played"]
    assert n > 100 and t["home"]["played"] + t["away"]["played"] == n and t["wins"] + t["draws"] + t["losses"] == n
    assert t["coverage"]["matches"] == n and t["coverage"]["first_match"] < t["coverage"]["last_match"]
    assert t["days_since_last_match"] >= 0 and 0 <= t["clean_sheet_rate"] <= 1 and 0 <= t["failed_to_score_rate"] <= 1
    assert t["form_last_5"]["matches"] == 5 and len(t["form_last_5"]["results"]) == 5 and "attack_strength" in t and "defence_strength" in t
    assert "cups and European" in t["coverage"]["note"] and "Rates are averages" in t["sample_note"]
    early = get(client, h, f"team?team=Arsenal&before={MS[800][0].isoformat()}")
    assert early["played"] < n and all(math.isfinite(early[k]) for k in ("elo", "points_per_match"))
    assert client.get("/api/v1/football/team?team=Nowhere%20FC", headers=h).status_code == 422
