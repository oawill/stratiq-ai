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
