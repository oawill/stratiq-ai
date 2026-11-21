"""SimLab: the sports scenario model, and the persistent, versioned, access-controlled run records around it.
All data is SYNTHETIC (real club names, random scores). Nothing here says anything about real forecasting accuracy."""
import copy
import math
import random
from datetime import date, datetime, timedelta, timezone

import pytest

from stratiq import football_models as fm
from stratiq import plans
from stratiq import simlab_api
from stratiq import sports_sim as ss
from .conftest import hdr, make_user
from .test_football_intel import FIVE, load, tamper

MS = sorted(FIVE, key=lambda m: (m[0], m[1], m[2]))
CUTOFF = MS[1500][0]
SETTINGS = {"tuned": False, "run_id": None, "poisson": {"half_life_days": 730.0, "prior_games": 2.0}, "rho": 0.0}
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def run(scenarios=None, home="Arsenal", away="Southampton", settings=SETTINGS, ms=MS, scheduled=False):
    return ss.run(ms, home, away, CUTOFF, settings, scenarios or [], scheduled, None, NOW)


# ------------------------------------------------------------------ probability normalisation
def test_percentages_always_add_to_exactly_one_hundred():
    rnd = random.Random(3)
    for _ in range(300):
        raw = [rnd.random() ** 3 + 1e-6 for _ in range(rnd.choice([2, 3, 5]))]
        for d in (0, 1, 2):
            out = ss.percent_split(raw, d)
            assert round(sum(out), d + 3) == 100.0 and all(v >= 0 for v in out)
    assert ss.percent_split([1, 1, 1]) == [33.4, 33.3, 33.3]          # the leftover tenth goes to the largest remainder
    assert ss.percent_split([2, 1, 1]) == [50.0, 25.0, 25.0]
    with pytest.raises(ValueError):
        ss.percent_split([0, 0, 0])


def test_every_scenario_is_normalised_whatever_the_assumptions():
    rnd = random.Random(9)
    keys = list(ss.ADJUSTMENTS)
    for _ in range(40):
        adj = {k: rnd.uniform(ss.ADJUSTMENTS[k][0], ss.ADJUSTMENTS[k][1]) for k in rnd.sample(keys, rnd.randint(1, len(keys)))}
        r = run([{"name": "x", "adjustments": adj}])
        for s in (r["baseline"], r["scenarios"][0]):
            assert abs(sum(s["probs"]) - 1) < 1e-9 and min(s["probs"]) > 0 and round(sum(s["percent"]), 6) == 100.0
            assert 0 < s["p_over_2_5"] < 1 and 0 < s["p_btts"] < 1


# ------------------------------------------------------------------ Poisson score distribution
def test_the_score_grid_is_independent_poisson_without_the_low_score_correction():
    r = run()
    lh, la = r["baseline"]["expected_goals"]
    grid, tail = r["baseline"]["score_grid"], r["baseline"]["grid_tail"]
    assert abs(sum(sum(row) for row in grid) + tail - 1) < 1e-12 and tail >= 0
    for h in range(4):
        for a in range(4):
            expected = fm.poisson_pmf(h, lh) * fm.poisson_pmf(a, la)
            assert abs(grid[h][a] - expected) < 5e-4                   # equal up to renormalising the truncated 0..10 grid
    assert [t["p"] for t in r["baseline"]["top_scorelines"]] == sorted((t["p"] for t in r["baseline"]["top_scorelines"]), reverse=True) and len(r["baseline"]["top_scorelines"]) == 5


def test_the_dixon_coles_correction_changes_only_the_lowest_scorelines():
    plain = run()["baseline"]
    dc = run(settings={**SETTINGS, "rho": -0.1})["baseline"]
    assert dc["probs"] != plain["probs"]
    assert abs(dc["score_grid"][4][4] / plain["score_grid"][4][4] - 1) < 0.02 and dc["score_grid"][0][0] != plain["score_grid"][0][0]
    assert run(settings={**SETTINGS, "rho": -0.1})["provenance"]["base_model"] == "Dixon-Coles" and run()["provenance"]["base_model"] == "Poisson"


# ------------------------------------------------------------------ what each assumption does
def test_neutral_adjustments_reproduce_the_baseline_exactly():
    r = run([{"name": "Nothing changed", "adjustments": {}}, {"name": "Explicit neutral", "adjustments": {k: v[2] for k, v in ss.ADJUSTMENTS.items()}}])
    for sc in r["scenarios"]:
        assert sc["probs"] == r["baseline"]["probs"] and sc["expected_goals"] == r["baseline"]["expected_goals"] and sc["changed"] == []
        assert all(abs(v) < 1e-12 for k, v in sc["delta_vs_baseline"].items() if k != "unit")


def test_each_assumption_moves_the_result_in_the_documented_direction():
    r = run([{"name": "Stronger home attack", "adjustments": {"home_attack_multiplier": 1.3}}, {"name": "Faster game", "adjustments": {"tempo_multiplier": 1.2}},
             {"name": "Home missing attackers", "adjustments": {"home_missing_attack_loss": 0.3}}])
    b = r["baseline"]
    atk, tempo, missing = r["scenarios"]
    weak = run([{"name": "Weak away defence", "adjustments": {"away_defence_multiplier": 1.4}}])["scenarios"][0]
    assert atk["expected_goals"][0] > b["expected_goals"][0] and atk["expected_goals"][1] == b["expected_goals"][1] and atk["probs"][0] > b["probs"][0]
    assert tempo["expected_goals"][0] > b["expected_goals"][0] and tempo["expected_goals"][1] > b["expected_goals"][1] and tempo["p_over_2_5"] > b["p_over_2_5"]
    assert missing["expected_goals"][0] < b["expected_goals"][0] and missing["probs"][0] < b["probs"][0]
    assert weak["expected_goals"][0] > b["expected_goals"][0] and weak["probs"][2] < b["probs"][2]
    ha = run([{"name": "More home advantage", "adjustments": {"home_advantage_multiplier": 1.4}}])["scenarios"][0]
    assert ha["probs"][0] > b["probs"][0] and ha["expected_goals"][1] == b["expected_goals"][1]
    d = atk["delta_vs_baseline"]
    assert d["p_home"] == pytest.approx((atk["probs"][0] - b["probs"][0]) * 100) and d["expected_goals_home"] > 0 and abs(d["p_home"] + d["p_draw"] + d["p_away"]) < 1e-9


def test_tempo_scales_both_expected_goals_by_exactly_the_multiplier_before_capping():
    r = run([{"name": "t", "adjustments": {"tempo_multiplier": 0.8}}])
    b, s = r["baseline"]["expected_goals"], r["scenarios"][0]["expected_goals"]
    assert s[0] == pytest.approx(b[0] * 0.8) and s[1] == pytest.approx(b[1] * 0.8)


def test_expected_goals_are_capped_to_a_sane_range():
    lo, hi = ss.expected_goals({"mu": 0.001, "home_adv": 1, "attack_home": 1, "defence_home": 1, "attack_away": 1, "defence_away": 1}, {})
    assert lo == ss.LAMBDA_MIN and hi == ss.LAMBDA_MIN
    big = ss.expected_goals({"mu": 9, "home_adv": 2, "attack_home": 3, "defence_home": 3, "attack_away": 3, "defence_away": 3}, {"tempo_multiplier": 1.2})
    assert big == (ss.LAMBDA_MAX, ss.LAMBDA_MAX)


# ------------------------------------------------------------------ validation and honesty
@pytest.mark.parametrize("bad", [{"nonsense": 1.0}, {"home_attack_multiplier": 2.0}, {"tempo_multiplier": 0.5}, {"home_missing_attack_loss": -0.1}, {"home_missing_attack_loss": 0.9},
                                 {"home_attack_multiplier": float("nan")}, {"home_attack_multiplier": float("inf")}, {"tempo_multiplier": True}, {"tempo_multiplier": "1.1"}])
def test_invalid_assumptions_are_rejected(bad):
    with pytest.raises(ValueError):
        run([{"name": "bad", "adjustments": bad}])


def test_scenario_limits_and_names_and_clubs_are_enforced():
    with pytest.raises(ValueError, match="At most 3"):
        run([{"name": f"s{i}", "adjustments": {}} for i in range(4)])
    with pytest.raises(ValueError, match="unique"):
        run([{"name": "a", "adjustments": {}}, {"name": "a", "adjustments": {}}])
    with pytest.raises(ValueError, match="Baseline"):
        run([{"name": "baseline", "adjustments": {}}])
    with pytest.raises(ValueError, match="different clubs"):
        run(home="Arsenal", away="Arsenal")
    with pytest.raises(ValueError, match="not a club"):
        run(home="Nowhere FC")
    with pytest.raises(ValueError, match="Fewer than 30"):
        ss.run(MS[:20], "Arsenal", "Southampton", MS[19][0] + timedelta(days=1), SETTINGS, [], False)


def test_calibrated_and_speculative_parameters_are_kept_apart_and_labelled():
    r = run([{"name": "a", "adjustments": {"home_attack_multiplier": 1.2}}])
    assert {c["name"] for c in r["calibrated_parameters"]} >= {"League average goals per team", "Home advantage multiplier", "Arsenal attack strength", "Southampton defensive weakness", "Matches used"}
    spec = r["scenarios"][0]["speculative_parameters"]
    assert len(spec) == len(ss.ADJUSTMENTS) and all(s["status"] == "speculative assumption, not validated" for s in spec)
    assert [s["key"] for s in spec if s["changed"]] == ["home_attack_multiplier"]
    assert "not statistically validated" in r["validation_status"] and "no backtest has been run" in r["validation_status"]
    assert "HYPOTHETICAL" in r["label"] and "Not forecasts" in r["label"]
    tuned = run(settings={**SETTINGS, "tuned": True, "run_id": "r1"})
    assert "tuned on a validation period" in tuned["validation_status"] and tuned["provenance"]["settings_from_backtest"] == "r1"


def test_a_pairing_is_only_called_scheduled_when_it_is_an_imported_fixture():
    hyp = run()
    assert hyp["matchup"]["scheduled"] is False and "not a scheduled match" in hyp["matchup"]["label"] and hyp["matchup"]["fixture_date"] is None
    sch = ss.run(MS, "Arsenal", "Southampton", CUTOFF, SETTINGS, [], True, date(2026, 5, 1), NOW)
    assert sch["matchup"]["scheduled"] is True and sch["matchup"]["fixture_date"] == "2026-05-01" and "not a scheduled match" not in sch["matchup"]["label"]


# ------------------------------------------------------------------ reproducibility and leakage
def test_the_same_inputs_always_give_the_same_outputs_and_there_is_no_random_seed():
    sc = [{"name": "a", "adjustments": {"tempo_multiplier": 1.1, "home_attack_multiplier": 1.2}}]
    a, b = run(sc), run(sc)
    assert a == b and a["provenance"]["deterministic"] is True and a["provenance"]["random_seed"] is None


def test_no_match_on_or_after_the_cutoff_can_change_anything():
    sc = [{"name": "a", "adjustments": {"home_attack_multiplier": 1.2}}]
    a, b = run(sc), run(sc, ms=tamper(MS, CUTOFF))
    assert a == b
    prov = a["provenance"]
    assert prov["training_cutoff"] == CUTOFF.isoformat() and date.fromisoformat(prov["data_through"]) < CUTOFF and prov["matches_used"] == sum(1 for m in MS if m[0] < CUTOFF) and len(prov["data_sha256"]) == 64
    assert run(ms=MS[:-5])["provenance"]["data_sha256"] == prov["data_sha256"]          # matches after the cutoff are not part of the fingerprint either


# ------------------------------------------------------------------ API: persistence, versioning, access, limits, exports
@pytest.fixture()
def ws(client, conn):
    uid, wid = make_user(conn)
    return hdr(uid, wid, exp_in=900), wid, uid


def call(client, h, method, path, body=None):
    return client.request(method, f"/api/v1/simlab/{path}", json=body, headers=h)


def add_fixture(conn, wid, days_ahead=3, home="Arsenal", away="Chelsea"):
    d = datetime.now(timezone.utc).date() + timedelta(days=days_ahead)
    conn.execute("insert into football_fixtures (workspace_id, competition, season, fixture_date, home_team, away_team) values (%s,'EPL','2025/26',%s,%s,%s)", (wid, d, home, away))
    return d


BODY = {"home": "Arsenal", "away": "Chelsea", "scenarios": [{"name": "Key attacker out", "adjustments": {"home_missing_attack_loss": 0.2}}, {"name": "Open game", "adjustments": {"tempo_multiplier": 1.15}}]}


def test_requires_sign_in_and_history(client, ws):
    h, wid, _ = ws
    assert client.get("/api/v1/simlab/runs").status_code == 401
    assert call(client, h, "POST", "sports/run", BODY).status_code == 404
    assert call(client, h, "GET", "sports/context").json()["has_history"] is False
    assert call(client, h, "GET", "sports/adjustments").json()["max_scenarios"] == 3


def test_a_run_is_stored_with_inputs_outputs_model_version_provenance_and_timestamp(client, conn, ws):
    h, wid, uid = ws
    load(client, h, FIVE)
    r = call(client, h, "POST", "sports/run", {**BODY, "title": "Cup tie"})
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["version"] == 1 and j["title"] == "Cup tie" and len(j["scenarios"]) == 2 and j["matchup"]["scheduled"] is False
    row = conn.execute("select * from simlab_runs where id=%s", (j["id"],)).fetchone()
    assert row["domain"] == "sports" and row["model_name"] == "sports_sim" and row["model_version"] == ss.SIM_VERSION and row["seed"] is None and str(row["created_by"]) == uid and row["created_at"]
    assert row["inputs"]["scenarios"][0]["adjustments"] == {"home_missing_attack_loss": 0.2}
    assert row["provenance"]["matches_used"] > 100 and len(row["provenance"]["data_sha256"]) == 64 and row["provenance"]["settings_tuned"] is False
    got = call(client, h, "GET", f"runs/{j['id']}").json()
    assert got["baseline"] == j["baseline"] and got["scenarios"] == j["scenarios"] and got["created_by_name"] and got["versions"][0]["version"] == 1
    listing = call(client, h, "GET", "runs?domain=sports").json()["runs"]
    assert len(listing) == 1 and listing[0]["baseline_percent"] == j["baseline"]["percent"] and listing[0]["scenarios"] == 2
    assert call(client, h, "GET", "runs?domain=business").json()["runs"] == []
    assert conn.execute("select count(*) n from activity_history where workspace_id=%s and kind='simlab.run'", (wid,)).fetchone()["n"] == 1


def test_running_the_same_inputs_twice_reproduces_the_same_outputs(client, ws):
    h, wid, _ = ws
    load(client, h, FIVE)
    a, b = (call(client, h, "POST", "sports/run", BODY).json() for _ in range(2))
    strip = lambda x: {k: v for k, v in x.items() if k not in ("id", "created_at", "scenario_key", "provenance")} | {"prov": {k: v for k, v in x["provenance"].items() if k != "generated_at"}}
    assert strip(a) == strip(b) and a["scenario_key"] != b["scenario_key"]


def test_scheduled_and_hypothetical_matchups_are_told_apart_and_a_bad_fixture_is_refused(client, conn, ws):
    h, wid, _ = ws
    load(client, h, FIVE)
    d = add_fixture(conn, wid)
    ok = call(client, h, "POST", "sports/run", {**BODY, "fixture_date": d.isoformat()}).json()
    assert ok["matchup"]["scheduled"] is True and ok["matchup"]["fixture_date"] == d.isoformat()
    assert call(client, h, "POST", "sports/run", {**BODY, "fixture_date": (d + timedelta(days=1)).isoformat()}).status_code == 422
    assert call(client, h, "POST", "sports/run", {**BODY, "home": "Chelsea", "away": "Arsenal", "fixture_date": d.isoformat()}).status_code == 422       # the reverse pairing is not the scheduled match
    assert call(client, h, "POST", "sports/run", BODY).json()["matchup"]["scheduled"] is False


def test_invalid_input_is_refused_with_a_clear_message_and_nothing_is_stored(client, conn, ws):
    h, wid, _ = ws
    load(client, h, FIVE)
    for bad in ({**BODY, "scenarios": [{"name": "x", "adjustments": {"tempo_multiplier": 3}}]}, {**BODY, "scenarios": [{"name": f"s{i}", "adjustments": {}} for i in range(4)]},
                {**BODY, "home": "Nowhere FC"}, {**BODY, "away": "Arsenal"}, {**BODY, "scenarios": [{"name": "x", "adjustments": {"bogus": 1}}]}, {**BODY, "title": ""}):
        assert call(client, h, "POST", "sports/run", bad).status_code == 422
    assert conn.execute("select count(*) n from simlab_runs where workspace_id=%s", (wid,)).fetchone()["n"] == 0


def test_scenarios_are_versioned_and_each_version_stays_retrievable(client, ws):
    h, wid, _ = ws
    load(client, h, FIVE)
    v1 = call(client, h, "POST", "sports/run", BODY).json()
    v2 = call(client, h, "POST", "sports/run", {**BODY, "based_on": v1["id"], "scenarios": [{"name": "Tweaked", "adjustments": {"tempo_multiplier": 0.9}}]}).json()
    v3 = call(client, h, "POST", "sports/run", {**BODY, "based_on": v2["id"]}).json()
    assert (v2["version"], v3["version"]) == (2, 3) and v1["scenario_key"] == v2["scenario_key"] == v3["scenario_key"] and v2["parent_id"] == v1["id"] and v3["parent_id"] == v2["id"]
    g = call(client, h, "GET", f"runs/{v2['id']}").json()
    assert [v["version"] for v in g["versions"]] == [1, 2, 3] and g["scenarios"][0]["name"] == "Tweaked"
    assert call(client, h, "GET", f"runs/{v1['id']}").json()["scenarios"][0]["name"] == "Key attacker out"
    assert call(client, h, "POST", "sports/run", {**BODY, "based_on": "00000000-0000-0000-0000-000000000000"}).status_code == 404


def test_runs_are_private_to_their_workspace_and_ownership_decides_deletion(client, conn, ws):
    h, wid, uid = ws
    load(client, h, FIVE)
    run_id = call(client, h, "POST", "sports/run", BODY).json()["id"]
    other = hdr(*make_user(conn))
    assert call(client, other, "GET", f"runs/{run_id}").status_code == 404 and call(client, other, "GET", "runs").json()["runs"] == [] and call(client, other, "DELETE", f"runs/{run_id}").status_code == 404
    based = call(client, other, "POST", "sports/run", {**BODY, "based_on": run_id})
    assert based.status_code in (404,)                                                                          # cannot build on another workspace's run
    viewer = hdr(make_user(conn, role="viewer", workspace_id=wid)[0], wid)
    assert call(client, viewer, "GET", f"runs/{run_id}").status_code == 200                                      # any member can read
    assert call(client, viewer, "POST", "sports/run", BODY).status_code == 403                                  # a read-only role cannot run
    assert call(client, viewer, "DELETE", f"runs/{run_id}").status_code == 403
    member = hdr(make_user(conn, role="member", workspace_id=wid)[0], wid)
    assert call(client, member, "DELETE", f"runs/{run_id}").status_code == 403                                   # a member who did not run it cannot delete it
    admin = hdr(make_user(conn, role="admin", workspace_id=wid)[0], wid)
    assert call(client, admin, "DELETE", f"runs/{run_id}").status_code == 204
    assert conn.execute("select count(*) n from audit_logs where workspace_id=%s and action='simlab.delete'", (wid,)).fetchone()["n"] == 1
    mine = call(client, h, "POST", "sports/run", BODY).json()["id"]
    assert call(client, h, "DELETE", f"runs/{mine}").status_code == 204


def test_expensive_use_is_rate_limited_per_person_and_per_workspace(client, conn, ws, monkeypatch):
    h, wid, _ = ws
    load(client, h, FIVE)
    monkeypatch.setattr(simlab_api, "RATE_PER_MINUTE", 2)
    assert [call(client, h, "POST", "sports/run", BODY).status_code for _ in range(3)] == [201, 201, 429]
    assert "Too many simulations" in call(client, h, "POST", "sports/run", BODY).json()["detail"]
    monkeypatch.setattr(simlab_api, "RATE_PER_MINUTE", 100)
    monkeypatch.setattr(simlab_api, "RATE_PER_DAY", 2)
    r = call(client, h, "POST", "sports/run", BODY)
    assert r.status_code == 429 and "24 hours" in r.json()["detail"]
    assert conn.execute("select count(*) n from simlab_runs where workspace_id=%s", (wid,)).fetchone()["n"] == 2


def test_saved_simulations_count_toward_the_plan_scenario_limit(client, conn, ws):
    h, wid, _ = ws
    load(client, h, FIVE)
    before = plans.usage(conn, wid)["scenarios"]
    call(client, h, "POST", "sports/run", BODY)
    assert plans.usage(conn, wid)["scenarios"] == before + 1


def test_exports_carry_the_hypothetical_label_the_model_and_the_provenance(client, conn, ws):
    h, wid, _ = ws
    load(client, h, FIVE)
    j = call(client, h, "POST", "sports/run", {**BODY, "title": "Export me"}).json()
    csv_resp = call(client, h, "GET", f"runs/{j['id']}/export?format=csv")
    assert csv_resp.status_code == 200 and "attachment" in csv_resp.headers["content-disposition"] and "export-me-v1.csv" in csv_resp.headers["content-disposition"]
    text = csv_resp.text
    assert "HYPOTHETICAL scenarios" in text and "sports_sim@" in text and "random seed: none (deterministic)" in text and f"data sha256 {j['provenance']['data_sha256']}" in text
    lines = [ln for ln in text.splitlines() if ln.startswith(("Baseline,", "Key attacker out,", "Open game,"))]
    assert len(lines) == 3 and lines[0].split(",")[1:4] == [str(x) for x in j["baseline"]["percent"]]
    assert "home_missing_attack_loss=0.2" in lines[1] and "none (calibrated from data)" in lines[0]
    html = call(client, h, "GET", f"runs/{j['id']}/export?format=html")
    assert html.headers["content-type"].startswith("text/html") and "<h1>Export me</h1>" in html.text and "Not forecasts" in html.text and "SHA-256" in html.text
    js = call(client, h, "GET", f"runs/{j['id']}/export?format=json").json()
    assert js["outputs"]["baseline"] == j["baseline"] and js["provenance"]["model"] == "sports_sim"
    assert conn.execute("select count(*) n from audit_logs where workspace_id=%s and action='simlab.export'", (wid,)).fetchone()["n"] == 3
    assert call(client, h, "GET", f"runs/{j['id']}/export?format=pdf").status_code == 422
