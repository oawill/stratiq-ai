import math
import random
from datetime import datetime, timedelta, timezone

import pytest

from stratiq import backtest, dataset
from stratiq.model import HistMatch, predict
from stratiq.poisson import poisson_pmf, scoreline_model
from stratiq.ratings import Match, fit_ratings


def test_pmf_known_values():
    assert poisson_pmf(2, 1.5) == pytest.approx(0.25102143, rel=1e-6)
    assert poisson_pmf(0, 0.0) == 1.0
    assert poisson_pmf(3, 0.0) == 0.0
    assert sum(poisson_pmf(k, 2.7) for k in range(60)) == pytest.approx(1.0, abs=1e-12)


def test_outcomes_sum_to_one_and_symmetry():
    m = scoreline_model(1.4, 1.4)
    assert m.p_home + m.p_draw + m.p_away == pytest.approx(1.0, abs=1e-12)
    assert m.p_home == pytest.approx(m.p_away, abs=1e-12)
    assert sum(sum(r) for r in m.grid) == pytest.approx(1.0, abs=1e-12)


def test_known_poisson_outcome_probabilities():
    # Reference values from an independent plain-loop sum over a 30x30 grid (math.factorial pmf).
    m = scoreline_model(1.6, 1.1)
    assert m.p_home == pytest.approx(0.4895735, abs=1e-6)
    assert m.p_draw == pytest.approx(0.2489110, abs=1e-6)
    assert m.p_away == pytest.approx(0.2615155, abs=1e-6)


def test_monotonic_in_home_xg():
    low, high = scoreline_model(1.0, 1.2), scoreline_model(2.0, 1.2)
    assert high.p_home > low.p_home and high.p_away < low.p_away


def test_rejects_invalid_input():
    with pytest.raises(ValueError):
        scoreline_model(-1, 1)
    with pytest.raises(ValueError):
        scoreline_model(float("nan"), 1)


def _simulate(seed, n_rounds=12):
    params, ms = dataset.generate("nfl-fict", seed, now=datetime(2026, 1, 1, tzinfo=timezone.utc), scheduled_rounds=0)
    return params, [m for m in ms]


def test_ratings_recover_known_strengths():
    # Large synthetic sample from known parameters; fit should recover ordering and home advantage.
    rng = random.Random(7)
    teams = ["A", "B", "C", "D", "E", "F"]
    att = {t: math.exp(rng.gauss(0, 0.3)) for t in teams}
    dfn = {t: math.exp(rng.gauss(0, 0.3)) for t in teams}
    mu, gamma = 1.3, 1.3
    ms = []
    for _ in range(4000):
        for h in teams:
            for a in teams:
                if h != a and rng.random() < 0.15:
                    ms.append(Match(h, a, dataset._poisson_sample(rng, mu * att[h] * dfn[a] * gamma),
                                    dataset._poisson_sample(rng, mu * att[a] * dfn[h])))
    r = fit_ratings(ms, teams, prior_games=0.0)
    assert r.converged
    assert r.home_adv == pytest.approx(gamma, rel=0.05)
    # compare scale-free quantities: expected goals for several pairings
    for h, a in [("A", "B"), ("C", "D"), ("E", "F")]:
        true = (mu * att[h] * dfn[a] * gamma)
        assert r.expected_goals(h, a)[0] == pytest.approx(true, rel=0.06)


def test_fit_is_deterministic():
    ms = [Match("A", "B", 2, 1), Match("B", "C", 0, 0), Match("C", "A", 1, 3), Match("A", "C", 2, 2)]
    r1, r2 = fit_ratings(ms, ["A", "B", "C"]), fit_ratings(ms, ["A", "B", "C"])
    assert r1.attack == r2.attack and r1.defence == r2.defence


def test_no_data_gives_neutral_prior():
    r = fit_ratings([], ["A", "B"])
    assert r.attack == {"A": 1.0, "B": 1.0}


def test_dataset_is_seed_deterministic_and_fictional():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _, a = dataset.generate("nfl-fict", 1, now=now)
    _, b = dataset.generate("nfl-fict", 1, now=now)
    _, c = dataset.generate("nfl-fict", 2, now=now)
    assert a == b and a != c
    assert len(a) == 12 * 11  # double round robin
    assert sum(1 for m in a if m["status"] == "scheduled") == 12
    assert all(m["home"] != m["away"] for m in a)


def _hist(seed=3):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _, ms = dataset.generate("nfl-fict", seed, now=now)
    teams = [dataset.team_id("nfl-fict", t) for t in dataset.LEAGUES["nfl-fict"]["teams"]]
    hist = [HistMatch(dataset.team_id("nfl-fict", m["home"]), dataset.team_id("nfl-fict", m["away"]),
                      m["home_goals"], m["away_goals"], m["kickoff"]) for m in ms if m["status"] == "finished"]
    return teams, hist


def test_predict_has_no_lookahead():
    teams, hist = _hist()
    cutoff = hist[40].kickoff
    p1 = predict(hist, teams, teams[0], teams[1], cutoff, "t")
    # Altering results at/after the cutoff must not change the prediction.
    tampered = [h if h.kickoff < cutoff else HistMatch(h.home, h.away, 9, 0, h.kickoff) for h in hist]
    p2 = predict(tampered, teams, teams[0], teams[1], cutoff, "t")
    assert p1 == p2
    assert p1["inputs"]["matches_used"] == sum(1 for h in hist if h.kickoff < cutoff)


def test_predict_is_reproducible_and_normalised():
    teams, hist = _hist()
    cutoff = hist[-1].kickoff + timedelta(days=1)
    a = predict(hist, teams, teams[2], teams[3], cutoff, "t")
    b = predict(hist, teams, teams[2], teams[3], cutoff, "t")
    assert a == b
    o = a["outputs"]
    assert o["p_home"] + o["p_draw"] + o["p_away"] == pytest.approx(1.0, abs=1e-5)


def test_backtest_runs_and_reports_honest_numbers():
    teams, hist = _hist()
    res = backtest.run(hist, teams, "t", min_train=40)
    assert res["sample_size"] == len(hist) - 40
    # Metrics are finite, Brier bounded by [0, 2].
    for k in ("brier", "log_loss", "baseline_brier", "baseline_log_loss"):
        assert math.isfinite(res[k]) and res[k] >= 0
    assert res["brier"] <= 2.0


# ------------------------------------------------------------------ evaluate(): backtest for uploaded data
def _poisson(rnd, lam):
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rnd.random()
        if p <= limit:
            return k
        k += 1


def _league(strengths, rounds=14, seed=5):
    """A double round robin repeated `rounds` times, goals drawn from the same Poisson model the engine assumes."""
    rnd = random.Random(seed)
    names = list(strengths)
    day = datetime(2024, 1, 1, tzinfo=timezone.utc)
    out = []
    for _ in range(rounds):
        for h in names:
            for a in names:
                if h == a:
                    continue
                out.append(HistMatch(h, a, _poisson(rnd, 1.35 * strengths[h] / strengths[a] ** 0.5 * 1.1), _poisson(rnd, 1.1 * strengths[a] / strengths[h] ** 0.5), day))
                day += timedelta(hours=7)
    return names, out


def test_evaluate_finds_real_signal_and_reports_every_piece():
    names, hist = _league({"A": 2.2, "B": 1.6, "C": 1.0, "D": 0.6, "E": 0.4, "F": 1.2})
    res = backtest.evaluate(hist, names, "t", min_train=60, max_eval=150)
    assert res["sample_size"] == 150 and res["matches"] == len(hist)
    assert res["log_loss"] < res["baseline_log_loss"] and res["brier"] < res["baseline_brier"]
    assert res["log_loss_gain"] > 0 and res["gain_is_clear"] is True
    assert res["accuracy"] >= res["baseline_accuracy"]
    assert sum(r["count"] for r in res["reliability"]) == 3 * res["sample_size"]
    for r in res["reliability"]:
        assert 0 <= r["observed"] <= 1 and r["low"] <= r["mean_predicted"] <= r["high"] + 1e-9
    assert res["first_scored"] <= res["last_scored"]


def test_evaluate_does_not_see_an_effect_in_pure_noise():
    names, hist = _league({n: 1.0 for n in "ABCDEF"}, rounds=10, seed=11)
    res = backtest.evaluate(hist, names, "t", min_train=60, max_eval=150)
    assert res["gain_is_clear"] is False          # equal teams: no real skill to find
    assert res["log_loss_gain"] < 0.05


def test_evaluate_needs_enough_history_and_is_deterministic():
    names, hist = _league({"A": 1.5, "B": 1.0, "C": 0.7, "D": 1.2}, rounds=3)
    assert backtest.evaluate(hist, names, "t", min_train=len(hist))["sample_size"] == 0
    a = backtest.evaluate(hist, names, "t", min_train=20, max_eval=20)
    assert a == backtest.evaluate(hist, names, "t", min_train=20, max_eval=20)
    assert a["sample_size"] == len(hist) - 20 == 16   # min_train wins over max_eval
