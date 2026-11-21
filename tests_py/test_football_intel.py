"""Football prediction intelligence: models, leak-free backtesting, feature snapshots, reliability and what-if scenarios, and the API.
All data is SYNTHETIC (real club names, random scores). Nothing here says anything about real forecasting accuracy."""
import math
import random
from datetime import date, timedelta

import pytest

from stratiq import datasets as ds
from stratiq import football_backtest as fb
from stratiq import football_intel as fi
from stratiq import football_models as fm
from .conftest import hdr, make_user
from .test_football import ALL, fd_csv, five_csv
from .test_team import workspace_with


def seasons(years):
    return [m for y in years for m in ALL[y]]


FIVE = seasons(range(2020, 2025))
SPLIT = {"training": ["2020/21", "2021/22", "2022/23"], "validation": ["2023/24"], "test": ["2024/25"]}


def tamper(ms, from_date):
    return [m if m[0] < from_date else (m[0], m[1], m[2], 9, 0) for m in ms]


# ------------------------------------------------------------------ Elo
def test_elo_mapping_probabilities_sum_to_one_and_favour_the_stronger_side():
    ep, em = fm.EloParams(), fm.EloMap()
    for gap in (-300, -50, 0, 80, 400):
        p = fm.elo_probs(1500 + gap, 1500, ep, em)
        assert abs(sum(p) - 1) < 1e-9 and min(p) >= 0
    assert fm.elo_probs(1700, 1500, ep, em)[0] > fm.elo_probs(1500, 1700, ep, em)[0]


def test_elo_mapping_is_recovered_from_simulated_outcomes():
    rnd = random.Random(1)
    true = fm.EloMap(220.0, 0.9, 0.1)
    gaps, ys = [], []
    for _ in range(6000):
        g = rnd.uniform(-300, 300)
        x = g / true.scale + true.offset
        ph, pa = fm.sigmoid(x - true.draw), fm.sigmoid(-x - true.draw)
        u = rnd.random()
        gaps.append(g)
        ys.append(0 if u < ph else 2 if u > 1 - pa else 1)
    got = fm.fit_elo_map(gaps, ys)
    assert abs(got.scale - 220) < 35 and abs(got.draw - 0.9) < 0.15 and abs(got.offset - 0.1) < 0.12


def test_elo_pre_match_ratings_never_use_that_days_or_later_results():
    ms = FIVE[:600]
    day = ms[400][0]
    pre, _ = fm.elo_pass(ms, fm.EloParams())
    pre2, _ = fm.elo_pass(tamper(ms, day), fm.EloParams())
    upto = sum(1 for m in ms if m[0] <= day)          # even the matches ON the day are rated from before the day
    assert pre[:upto] == pre2[:upto] and pre != pre2


def test_elo_same_day_matches_are_independent_and_newcomers_start_below_average():
    a = [(date(2024, 8, 10), "Arsenal", "Chelsea", 3, 0), (date(2024, 8, 10), "Chelsea", "Everton", 0, 1)]
    assert fm.elo_pass(a, fm.EloParams())[0] == fm.elo_pass(a[::-1], fm.EloParams())[0]
    base = [(date(2023, 8, 10), "Arsenal", "Chelsea", 1, 0), (date(2024, 8, 10), "Arsenal", "Newbies", 1, 0)]
    pre, _ = fm.elo_pass(base, fm.EloParams(newcomer=-75.0))
    assert pre[1][1] < pre[1][0] and pre[1][1] < 1500        # the newcomer begins below the average, and the opening-day clubs began level
    assert fm.elo_pass(base[:1], fm.EloParams(newcomer=-75.0))[0][0] == (1500.0, 1500.0)


# ------------------------------------------------------------------ Poisson and Dixon-Coles
def test_poisson_fit_weights_recent_matches_and_ignores_the_cutoff_and_after():
    d0 = date(2022, 1, 1)
    old = [(d0 + timedelta(days=7 * i), "Strong", "Other", 4, 0) for i in range(20)] + [(d0 + timedelta(days=7 * i), "Other", "Strong", 0, 4) for i in range(20)]
    new = [(date(2024, 1, 1) + timedelta(days=7 * i), "Strong", "Other", 0, 2) for i in range(20)] + [(date(2024, 1, 1) + timedelta(days=7 * i), "Other", "Strong", 2, 0) for i in range(20)]
    cutoff = date(2025, 1, 1)
    short = fm.fit_poisson(old + new, cutoff, half_life_days=120)
    long_ = fm.fit_poisson(old + new, cutoff, half_life_days=5000)
    assert short.attack["Strong"] < long_.attack["Strong"]          # recent weakness counts for more with a short memory
    assert fm.fit_poisson(old + new + [(cutoff, "Strong", "Other", 9, 9)], cutoff, 730).attack == fm.fit_poisson(old + new, cutoff, 730).attack
    assert fm.fit_poisson([], cutoff).matches == 0


def test_dixon_coles_grid_is_a_distribution_and_shifts_low_score_mass_the_way_rho_says():
    for rho in (0.0, -0.1, 0.08):
        g = fm.score_grid(1.4, 1.1, rho)
        assert abs(sum(map(sum, g)) - 1) < 1e-9
        mk = fm.grid_markets(g)
        assert abs(mk["p_home"] + mk["p_draw"] + mk["p_away"] - 1) < 1e-9
    assert fm.score_grid(1.4, 1.1, -0.1)[0][0] > fm.score_grid(1.4, 1.1, 0.0)[0][0]
    assert fm.score_grid(1.4, 1.1, -0.1)[1][0] < fm.score_grid(1.4, 1.1, 0.0)[1][0] and fm.score_grid(1.4, 1.1, -0.1)[1][1] > fm.score_grid(1.4, 1.1, 0.0)[1][1]


def test_rho_is_near_zero_for_independent_scores_and_negative_when_low_scores_are_over_represented():
    rnd = random.Random(2)
    rows = [(1.3, 1.1, _p(rnd, 1.3), _p(rnd, 1.1)) for _ in range(4000)]
    assert abs(fm.fit_rho(rows)) < 0.08
    skew = [(1.3, 1.1, h, a) for _, _, h, a in rows]
    skew = [(lh, la, 0, 0) if (h, a) in ((1, 0), (0, 1)) and rnd.random() < 0.5 else (lh, la, h, a) for lh, la, h, a in skew]     # more 0-0 than independence allows
    assert fm.fit_rho(skew) < fm.fit_rho(rows)


def _p(rnd, lam):
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rnd.random()
        if p <= limit:
            return k
        k += 1


def test_frequency_baseline_uses_only_earlier_matches():
    ms = FIVE[:300]
    f = fm.Frequencies(ms)
    d = ms[200][0]
    a = f.before(d)
    b = fm.Frequencies(tamper(ms, d)).before(d)
    assert a == b and a["matches"] == sum(1 for m in ms if m[0] < d) and abs(sum(a["p"]) - 1) < 1e-9


# ------------------------------------------------------------------ backtests: no leakage, nothing tuned on the test period
@pytest.fixture(scope="module")
def chrono():
    return fb.run_chronological(FIVE, SPLIT)


def test_chronological_backtest_shape_probabilities_and_baselines(chrono):
    r = chrono
    assert r["mode"] == "chronological" and r["split"] == SPLIT and r["periods"]["validation"]["last"] < r["periods"]["test"]["first"]
    assert set(r["results"]) == {"validation", "test"}
    for period in ("validation", "test"):
        res = r["results"][period]
        assert set(res) == set(fb.MODELS)                           # every model and both baselines are scored on the same fixtures
        n = res["frequency"]["1x2"]["n"]
        assert all(res[m]["1x2"]["n"] == n for m in fb.MODELS)
        for m in ("poisson", "dixon_coles"):
            assert {"over_2_5", "btts", "correct_score"} <= set(res[m]) and "over_2_5" not in res["elo"]
        assert "vs_frequency" in res["elo"]["gain"] and "vs_elo" in res["poisson"]["gain"]
        assert res["poisson"]["1x2"]["reliability"] and set(res["elo"]["by_season"]) <= {"2023/24", "2024/25"}
    for p in r["predictions"]:
        assert abs(sum(p["probs"]) - 1) < 1e-6 and min(p["probs"]) >= 0
        assert p["period"] in ("validation", "test") and p["inputs"]
        if p["model"] in ("poisson", "dixon_coles"):
            assert p["drivers"] and abs(math.exp(sum(x["effect_home"] for x in p["drivers"])) - p["xg"][0]) < 1e-6        # the contributions rebuild the expected goals exactly


def test_forecasts_can_be_recomputed_from_their_stored_inputs(chrono):
    for p in chrono["predictions"][::97]:
        i = p["inputs"]
        if p["model"] == "elo":
            ep = fm.EloParams(i["k"], i["home_adv"], i["regress"], i["newcomer"])
            assert fm.elo_probs(i["rating_home"], i["rating_away"], ep, fm.EloMap(i["scale"], i["draw"], i["offset"])) == pytest.approx(p["probs"])
        elif p["model"] in ("poisson", "dixon_coles"):
            lh = i["mu"] * i["attack_home"] * i["defence_away"] * i["home_adv"]
            la = i["mu"] * i["attack_away"] * i["defence_home"]
            mk = fm.grid_markets(fm.score_grid(lh, la, i["rho"]))
            assert [mk["p_home"], mk["p_draw"], mk["p_away"]] == pytest.approx(p["probs"])


def test_no_forecast_uses_results_from_its_own_date_or_later():
    key = lambda p: (p["model"], p["date"], p["home"], p["away"])
    base = {key(p): p["probs"] for p in fb.run_chronological(FIVE, SPLIT)["predictions"]}
    cut = [m for m in FIVE if m[0] >= date(2024, 8, 1)][150][0]
    changed = {key(p): p["probs"] for p in fb.run_chronological(tamper(FIVE, cut), SPLIT)["predictions"]}
    early = [k for k in base if k[1] < cut.isoformat()]
    assert early and all(base[k] == changed[k] for k in early)       # every forecast made before the cutoff date is untouched by later results
    assert any(base[k] != changed[k] for k in base if k[1] >= cut.isoformat())


def test_nothing_is_tuned_on_the_test_period(chrono):
    test_start = date.fromisoformat(chrono["periods"]["test"]["first"])
    changed = fb.run_chronological(tamper(FIVE, test_start), SPLIT)
    assert changed["tuning"] == chrono["tuning"]                     # settings, mappings and rho are identical whatever the test results are
    assert changed["results"]["validation"] == chrono["results"]["validation"]


def test_splits_are_validated():
    with pytest.raises(ValueError, match="At least 4 seasons"):
        fb.default_split(seasons([2020, 2021, 2022]))
    with pytest.raises(ValueError, match="after training"):
        fb.run_chronological(FIVE, {"training": ["2020/21"], "validation": ["2024/25"], "test": ["2023/24"]})
    with pytest.raises(ValueError, match="not all present"):
        fb.run_chronological(FIVE, {"training": ["2020/21"], "validation": ["2023/24"], "test": ["2031/32"]})
    assert fb.default_split(seasons(range(2016, 2026))) == {"training": [f"{y}/{(y + 1) % 100:02d}" for y in range(2016, 2023)], "validation": ["2023/24"], "test": ["2024/25", "2025/26"]}


def test_rolling_origin_predicts_each_later_season_from_earlier_ones_only():
    ms = seasons(range(2020, 2024))
    r = fb.run_rolling(ms)
    assert r["seasons_predicted"] == ["2022/23", "2023/24"] and set(r["results"]["rolling"]) == set(fb.MODELS)
    cut = [m for m in ms if m[0] >= date(2023, 8, 1)][100][0]
    again = fb.run_rolling(tamper(ms, cut))
    key = lambda p: (p["model"], p["date"], p["home"], p["away"])
    base = {key(p): p["probs"] for p in r["predictions"]}
    other = {key(p): p["probs"] for p in again["predictions"]}
    assert all(base[k] == other[k] for k in base if k[1] < cut.isoformat())
    assert r == fb.run_rolling(ms)                                    # deterministic
    with pytest.raises(ValueError):
        fb.run_rolling(seasons([2020, 2021]))


# ------------------------------------------------------------------ snapshots and reliability
def test_snapshot_marks_every_factor_and_keeps_missing_ones_unavailable():
    home, away = FIVE[-1][1], FIVE[-1][2]
    snap = fi.build_snapshot(FIVE, home, away, date(2025, 3, 1))
    assert set(snap["availability"]) == {f["key"] for f in fi.FACTORS} and len(fi.FACTORS) == fi.TOTAL_FACTORS == 13
    for k in ("player_availability", "squad_strength", "managerial", "expected_goals", "betting_markets"):
        assert snap["availability"][k]["status"] == "unavailable" and snap["availability"][k]["as_of"] is None
    assert snap["availability"]["team_strength"]["status"] == "available" and snap["availability"]["historical_performance"]["source"] == "Imported match results"
    f = snap["features"]
    assert f["home_form_5"] and len(f["home_form_5"]) <= 5 and f["elo_home"] and f["head_to_head"]["meetings"] >= 0
    assert any("Unavailable and not used" in w for w in snap["warnings"]) and any("manager" in w for w in snap["warnings"])


def test_snapshot_never_sees_the_cutoff_day_or_later_and_is_reproducible():
    home, away = FIVE[-1][1], FIVE[-1][2]
    cut = date(2025, 3, 1)
    a = fi.build_snapshot(FIVE, home, away, cut)
    assert a == fi.build_snapshot(FIVE, home, away, cut)
    assert a["sha256"] == fi.build_snapshot(tamper(FIVE, cut), home, away, cut)["sha256"]       # later results change nothing
    assert a["sha256"] != fi.build_snapshot(FIVE, home, away, date(2025, 3, 8))["sha256"]
    assert all(d < cut for d in [date.fromisoformat(a["history_as_of"])])


def test_uploaded_statistics_are_used_only_from_before_the_cutoff_and_odds_only_on_the_day():
    home, away = "Arsenal", "Chelsea"
    cut = date(2025, 2, 1)
    stats = [{"date": cut - timedelta(days=3 * i), "home": home if i % 2 else away, "away": away if i % 2 else home, "home_xg": 1.5, "away_xg": 1.0, "odds_home": None, "odds_draw": None, "odds_away": None} for i in range(1, 14)]
    snap = fi.build_snapshot(FIVE, home, away, cut, stats)
    assert snap["availability"]["expected_goals"]["status"] == "available" and snap["features"]["home_xg_form"]["matches"] == 10
    future = stats + [{"date": cut, "home": home, "away": away, "home_xg": 9.0, "away_xg": 9.0, "odds_home": 2.0, "odds_draw": 3.5, "odds_away": 4.0}]
    s2 = fi.build_snapshot(FIVE, home, away, cut, future)
    assert s2["features"]["home_xg_form"] == snap["features"]["home_xg_form"]                   # the same-day row's xG is not used
    assert s2["availability"]["betting_markets"]["status"] == "available"
    assert abs(sum(s2["features"]["market_implied"][k] for k in ("home", "draw", "away")) - 1) < 1e-3
    assert fi.build_snapshot(FIVE, home, away, cut, stats[:3])["availability"]["expected_goals"]["status"] == "unavailable"


def test_warnings_for_thin_history_and_promotion():
    ms = list(ALL[2024])
    snap = fi.build_snapshot(ms, ms[0][1], ms[0][2], ms[0][0] + timedelta(days=1))
    assert any("only 0 earlier match" in w or "only 1 earlier" in w for w in snap["warnings"])
    two = list(ALL[2023]) + [m for m in ALL[2024] if m[1] != "Mystery FC"]
    club = next(t for t in {x[1] for x in ALL[2024]} if t not in {x[1] for x in ALL[2023]} | {x[2] for x in ALL[2023]})
    s = fi.build_snapshot(two + [(date(2025, 1, 1), club, "Arsenal", 1, 1)], club, "Arsenal", date(2025, 2, 1))
    assert s["features"]["home_newly_promoted"] is True and any("newly promoted" in w for w in s["warnings"])


def test_reliability_keeps_four_things_apart_and_never_reports_a_single_confidence_score():
    ms = FIVE
    snap = fi.build_snapshot(ms, ms[-1][1], ms[-1][2], date(2025, 3, 1))
    fc = fi.live_forecast(ms, ms[-1][1], ms[-1][2], date(2025, 3, 1))
    rel = fi.reliability(fc, snap, None)
    assert set(rel) == {"model_probability", "data_completeness", "historical_calibration", "model_disagreement", "sample_size"}
    assert "confidence" not in " ".join(rel).lower().replace("not a 75% confidence score", "") and rel["data_completeness"]["of"] == 13
    assert "unknown" in rel["historical_calibration"]["note"]
    assert 0 < rel["data_completeness"]["share_available"] < 1 and rel["data_completeness"]["missing"]


def test_what_if_adjustments_move_the_forecast_in_the_expected_direction_without_changing_the_data():
    ms = FIVE
    h, a = ms[-1][1], ms[-1][2]
    base = fi.live_forecast(ms, h, a, date(2025, 3, 1))
    hurt = fi.live_forecast(ms, h, a, date(2025, 3, 1), adjust={"home_missing_attack_loss": 0.3})
    assert hurt["poisson"]["expected_goals"][0] < base["poisson"]["expected_goals"][0] and hurt["poisson"]["probs"][0] < base["poisson"]["probs"][0]
    assert hurt["poisson"]["expected_goals"][1] == base["poisson"]["expected_goals"][1]
    no_ha = fi.live_forecast(ms, h, a, date(2025, 3, 1), adjust={"home_advantage_multiplier": 0.5, "home_advantage_points": -50.0})
    assert no_ha["poisson"]["probs"][0] < base["poisson"]["probs"][0] and no_ha["elo"]["probs"][0] < base["elo"]["probs"][0]
    assert fi.live_forecast(ms, h, a, date(2025, 3, 1)) == base


# ------------------------------------------------------------------ football advanced statistics (data type)
def stats_csv(n=30, xg=True, odds=False, extra=""):
    cols = "date,home_team,away_team" + (",home_xg,away_xg" if xg else ",home_shots,away_shots") + (",odds_home,odds_draw,odds_away" if odds else "")
    rows = []
    for i in range(n):
        d = date(2024, 9, 1) + timedelta(days=i)
        rows.append(f"{d},Arsenal,Chelsea" + (f",{1 + i % 3 * 0.4},{0.8 + i % 2 * 0.3}" if xg else f",{10 + i % 5},{8 + i % 4}") + (",2.1,3.4,3.6" if odds else ""))
    return cols + "\n" + "\n".join(rows) + "\n" + extra


def test_stats_parser_accepts_valid_files_and_keeps_blanks_blank():
    p = ds.parse("football_stats", stats_csv(odds=True))
    assert p.row_count == 30 and p.summary["fields"]["home_xg"] == 30 and p.data["rows"][0]["odds_home"] == 2.1
    blank = ds.parse("football_stats", stats_csv().replace("1.0,0.8", ",", 1).replace("2024-09-01,Arsenal,Chelsea,1.0,0.8", "2024-09-01,Arsenal,Chelsea,,"))
    assert blank.data["rows"][0]["home_xg"] is None and any("stay unavailable" in w for w in blank.warnings)
    ds.parse("football_stats", "Date,HomeTeam,AwayTeam,HS,AS,HST,AST,HC,AC,B365H,B365D,B365A\n" + "\n".join(f"{(date(2024, 9, 1) + timedelta(days=i)).strftime('%d/%m/%Y')},Man City,Spurs,12,8,5,3,6,4,1.5,4.2,6.5" for i in range(25)))


@pytest.mark.parametrize("mutate,expect", [
    (lambda t: t.replace("1.0,0.8", "-1,0.8", 1).replace("1.4,1.1", "-1,1.1", 1), "outside"),
    (lambda t: t.replace(",1.4,", ",abc,", 1), "not a number"),
    (lambda t: "date,home_team,away_team\n" + "\n".join(t.splitlines()[1:]), "no statistics columns"),
    (lambda t: t + "2099-01-01,Arsenal,Chelsea,1,1\n", "future"),
    (lambda t: t.replace("Chelsea", "Arsenal", 1), "two different"),
    (lambda t: t.replace("2024-09-02", "2024-09-01"), "more than once"),
    (lambda t: t.replace("date,", "date,odds_home,", 1), "all three"),
])
def test_stats_parser_rejects_bad_rows_with_reasons(mutate, expect):
    with pytest.raises(ds.DataError) as e:
        ds.parse("football_stats", mutate(stats_csv()))
    assert expect in " ".join(e.value.errors)
    with pytest.raises(ds.DataError, match="At least 20"):
        ds.parse("football_stats", stats_csv(n=5))


# ------------------------------------------------------------------ API
def post(client, h, path, body=None):
    return client.post(f"/api/v1/football/{path}", json=body or {}, headers=h)


def get(client, h, path):
    return client.get(f"/api/v1/football/{path}", headers=h)


def load(client, h, rows):
    r = post(client, h, "import", {"filename": "history.csv", "combined": True, "csv": five_csv(rows)})
    assert r.status_code == 200, r.text


@pytest.fixture()
def ws(client, conn):
    uid, wid = make_user(conn)
    return hdr(uid, wid), wid


def test_requires_auth_and_history(client, ws):
    h, _ = ws
    assert client.get("/api/v1/football/intel/factors").status_code == 401
    assert post(client, h, "intel/match", {"home": "Arsenal", "away": "Chelsea"}).status_code == 404
    assert post(client, h, "intel/backtest", {}).status_code == 404


def test_backtest_is_stored_reproducibly_and_visible_only_to_its_workspace(client, conn, ws):
    h, wid = ws
    load(client, h, FIVE)
    r = post(client, h, "intel/backtest", {"mode": "chronological", "split": SPLIT})
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["predictions_stored"] == 760 * 4 and run["split"] == SPLIT and "predictions" not in run
    assert conn.execute("select count(*) n from football_predictions where backtest_run_id=%s", (run["id"],)).fetchone()["n"] == 3040
    assert conn.execute("select count(*) n from football_prediction_outcomes o join football_predictions p on p.id=o.prediction_id where p.backtest_run_id=%s", (run["id"],)).fetchone()["n"] == 3040
    assert conn.execute("select count(*) n from football_model_versions where backtest_run_id=%s", (run["id"],)).fetchone()["n"] == 4
    detail = get(client, h, f"intel/backtests/{run['id']}").json()
    assert detail["data_sha256"] == run["data_sha256"] and detail["history_changed_since"] is False and detail["results"]["test"]["poisson"]["1x2"]["n"] == 380
    page = get(client, h, f"intel/backtests/{run['id']}/predictions?model=dixon_coles&period=test&limit=5").json()["predictions"]
    assert len(page) == 5 and abs(page[0]["p_home"] + page[0]["p_draw"] + page[0]["p_away"] - 1) < 1e-4 and page[0]["home_goals"] is not None and page[0]["inputs"]["rho"] is not None
    perf = get(client, h, "intel/performance").json()
    assert perf["chronological"]["id"] == run["id"] and perf["live"]["waiting_for_results"] == 0
    other = hdr(*make_user(conn))
    assert get(client, other, f"intel/backtests/{run['id']}").status_code == 404 and get(client, other, "intel/performance").json()["chronological"] is None
    load(client, h, ALL[2025])          # new data arrives afterwards
    assert get(client, h, f"intel/backtests/{run['id']}").json()["history_changed_since"] is True


def test_backtest_validation_and_roles(client, conn):
    wid, users = workspace_with(conn, "owner", "viewer")
    (_, ho), (_, hv) = users
    load(client, ho, seasons([2020, 2021]))
    assert post(client, hv, "intel/backtest", {}).status_code == 403
    r = post(client, ho, "intel/backtest", {})
    assert r.status_code == 422 and "At least 4 seasons" in r.json()["detail"]
    assert get(client, hv, "intel/factors").status_code == 200


def test_match_intelligence_forecasts_reliability_scenarios_and_saving(client, conn, ws):
    h, wid = ws
    load(client, h, FIVE)
    home, away = ALL[2024][0][1], ALL[2024][0][2]
    r = post(client, h, "intel/match", {"home": home, "away": away})
    assert r.status_code == 200, r.text
    m = r.json()
    assert set(m["forecasts"]) == {"elo", "poisson", "dixon_coles"}
    for f in m["forecasts"].values():
        assert abs(f["p_home"] + f["p_draw"] + f["p_away"] - 1) < 1e-9
    assert m["forecasts"]["dixon_coles"]["top_scorelines"] and m["forecasts"]["poisson"]["p_over_2_5"] is not None and m["forecasts"]["elo"]["p_over_2_5"] is None
    assert m["model_version"]["tuned"] is False and m["generated_at"] and m["warnings"] and "not betting" in m["label"].lower() and "certain" in m["label"].lower()
    assert m["reliability"]["data_completeness"]["of"] == 13 and "scenario" not in m
    assert post(client, h, "intel/match", {"home": home, "away": away}).json()["forecasts"] == m["forecasts"]        # reproducible
    sc = post(client, h, "intel/match", {"home": home, "away": away, "adjust": {"home_missing_attack_loss": 0.25}}).json()
    assert sc["scenario"]["hypothetical"] is True and "HYPOTHETICAL" in sc["scenario"]["note"] and sc["forecasts"] == m["forecasts"]     # the real forecast is unchanged
    assert sc["scenario"]["forecasts"]["poisson"]["p_home"] < m["forecasts"]["poisson"]["p_home"]
    assert post(client, h, "intel/match", {"home": home, "away": away, "adjust": {"bogus": 1}}).status_code == 422
    assert post(client, h, "intel/match", {"home": home, "away": away, "adjust": {"home_attack_multiplier": 9}}).status_code == 422
    assert post(client, h, "intel/match", {"home": home, "away": away, "adjust": {"home_missing_attack_loss": 0.1}, "save": True}).status_code == 422
    assert post(client, h, "intel/match", {"home": home, "away": home}).status_code == 422
    assert post(client, h, "intel/match", {"home": home, "away": "Nobody FC"}).status_code == 422
    saved = post(client, h, "intel/match", {"home": home, "away": away, "save": True}).json()["saved"]
    assert set(saved["prediction_ids"]) == {"elo", "poisson", "dixon_coles"}
    again = post(client, h, "intel/match", {"home": home, "away": away, "save": True}).json()["saved"]
    assert again["prediction_ids"] == saved["prediction_ids"]                       # saving twice does not duplicate
    assert conn.execute("select count(*) n from football_predictions where workspace_id=%s and kind='live'", (wid,)).fetchone()["n"] == 3


def test_past_kickoff_uses_only_what_was_known_before_it(client, conn, ws):
    h, _ = ws
    load(client, h, FIVE)
    target = ALL[2024][300]
    body = {"home": target[1], "away": target[2], "kickoff": target[0].isoformat()}
    a = post(client, h, "intel/match", body).json()
    assert a["cutoff"] == target[0].isoformat() and a["snapshot"]["features"]["matches_in_history"] == sum(1 for m in FIVE if m[0] < target[0])
    assert a["data_sha256"] == fb.data_sha([m for m in FIVE if m[0] < target[0]])


def test_upcoming_fixtures_are_forecast_tracked_and_scored_when_the_result_arrives(client, conn, ws):
    h, wid = ws
    load(client, h, FIVE)
    assert get(client, h, "intel/fixtures").json()["fixtures"] == []
    soon = date.today() + timedelta(days=3)
    t = [ALL[2024][0][1], ALL[2024][0][2], ALL[2024][1][1], ALL[2024][1][2]]
    csv = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\n" + "\n".join(f"E0,{soon.strftime('%d/%m/%Y')},{a},{b},," for a, b in ((t[0], t[1]), (t[2], t[3]))) + "\n"
    r = post(client, h, "import", {"filename": "fixtures.csv", "csv": csv})
    assert r.status_code == 200, r.text
    assert r.json()["upcoming_fixtures"] == 2 and r.json()["new"] == 0
    assert post(client, h, "import", {"filename": "fixtures.csv", "csv": csv}).json()["upcoming_fixtures"] == 2
    assert conn.execute("select count(*) n from football_fixtures where workspace_id=%s", (wid,)).fetchone()["n"] == 2                 # idempotent
    fx = get(client, h, "intel/fixtures?days=7").json()["fixtures"]
    assert len(fx) == 2 and all(set(f["forecasts"]) == {"elo", "poisson", "dixon_coles"} and f["tracked"] for f in fx)
    assert conn.execute("select count(*) n from football_predictions where workspace_id=%s and kind='live'", (wid,)).fetchone()["n"] == 6
    assert get(client, h, "intel/fixtures?days=1").json()["fixtures"] == []
    # the match is played: put the result in, and the stored forecasts are scored against it
    conn.execute("insert into match_history (workspace_id, competition, season, match_date, home_team, away_team, home_goals, away_goals) values (%s,'EPL',%s,%s,%s,%s,2,1)", (wid, fi.season_label(soon), soon, t[0], t[1]))
    assert post(client, h, "intel/reconcile").json()["scored"] == 3
    assert post(client, h, "intel/reconcile").json()["scored"] == 0                                                                 # scoring twice does nothing
    perf = get(client, h, "intel/performance").json()["live"]
    assert {x["model"] for x in perf["scored"]} == {"elo", "poisson", "dixon_coles"} and perf["waiting_for_results"] == 3 and all(x["n"] == 1 for x in perf["scored"])
    assert len(get(client, h, "intel/fixtures?days=7").json()["fixtures"]) == 1                                                      # the played match drops off the list


def test_factors_endpoint_reports_what_data_exists_and_each_source(client, conn, ws):
    h, wid = ws
    f = get(client, h, "intel/factors").json()
    assert all(x["status"] == "unavailable" for x in f["factors"]) and f["data"]["matches"] == 0
    load(client, h, FIVE[:600])
    f = get(client, h, "intel/factors").json()
    st = {x["key"]: x["status"] for x in f["factors"]}
    assert st["historical_performance"] == "available" and st["team_strength"] == "available" and st["expected_goals"] == "unavailable" and st["player_availability"] == "unavailable"
    assert f["sources"][0]["kind"] == "match_results" and f["sources"][0]["provider"] == "user_upload" and f["sources"][0]["coverage"]["matches"] == 600
    up = client.post("/api/v1/data/datasets", json={"kind": "football_stats", "name": "My xG", "csv": stats_csv(odds=True), "options": {}}, headers=h)
    assert up.status_code == 201, up.text
    assert conn.execute("select count(*) n from football_team_statistics where workspace_id=%s", (wid,)).fetchone()["n"] == 30
    f = get(client, h, "intel/factors").json()
    st = {x["key"]: x["status"] for x in f["factors"]}
    assert st["expected_goals"] == "available" and st["betting_markets"] == "available" and {s["kind"] for s in f["sources"]} == {"match_results", "advanced_statistics"}
    assert client.delete(f"/api/v1/data/datasets/{up.json()['id']}", headers=h).status_code == 204
    assert conn.execute("select count(*) n from football_team_statistics where workspace_id=%s", (wid,)).fetchone()["n"] == 0        # removed with its dataset


def test_uploaded_expected_goals_reach_the_match_intelligence(client, conn, ws):
    h, _ = ws
    load(client, h, FIVE)
    rows = ["date,home_team,away_team,home_xg,away_xg"]
    for i in range(1, 23):
        rows.append(f"{(date.today() - timedelta(days=4 * i)).isoformat()},{'Arsenal' if i % 2 else 'Chelsea'},{'Chelsea' if i % 2 else 'Arsenal'},1.6,0.9")
    assert client.post("/api/v1/data/datasets", json={"kind": "football_stats", "name": "xG", "csv": "\n".join(rows) + "\n", "options": {}}, headers=h).status_code == 201
    m = post(client, h, "intel/match", {"home": "Arsenal", "away": "Chelsea"}).json()
    assert m["snapshot"]["availability"]["expected_goals"]["status"] == "available" and m["snapshot"]["features"]["home_xg_form"]["matches"] >= 5
    assert "Expected goals" not in " ".join(m["reliability"]["data_completeness"]["missing"])


def test_other_dataset_types_are_unchanged(client, conn, ws):
    h, _ = ws
    from .test_datasets import upload
    for kind in ("sports_results", "market_returns", "political_seats", "series"):
        assert upload(client, h, kind=kind, name=f"k-{kind}").status_code == 201
    assert client.post("/api/v1/data/preview", json={"kind": "football_stats", "csv": stats_csv(), "options": {}}, headers=h).json()["ok"] is True
