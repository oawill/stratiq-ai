import math
import random
from statistics import NormalDist

import pytest

from stratiq import finance as fin
from stratiq.finance import FinanceError

N = NormalDist()
ONE = [[1.0]]


def mc(**kw):
    base = dict(names=["A"], weights=[1.0], mu=[0.07], sigma=[0.2], corr=ONE, initial_value=1000.0, horizon_years=1.0, steps_per_year=12,
                iterations=6000, rebalance="every_step", tails="normal", df=5.0, seed=1, confidences=[0.95, 0.99], loss_threshold=None, drawdown_threshold=None)
    base.update(kw)
    return fin.monte_carlo(**base)


# ------------------------------------------------------------------ correlation & portfolio analytics
def test_cholesky_reconstructs_the_matrix_and_allows_perfect_correlation():
    a = [[1, 0.6, 0.3], [0.6, 1, -0.2], [0.3, -0.2, 1]]
    L = fin.cholesky(a)
    for i in range(3):
        for j in range(3):
            assert sum(L[i][k] * L[j][k] for k in range(3)) == pytest.approx(a[i][j], abs=1e-12)
    fin.cholesky([[1, 1], [1, 1]])
    fin.cholesky([[1, -1], [-1, 1]])


@pytest.mark.parametrize(
    "corr,frag",
    [
        ([[1, 0.9, -0.9], [0.9, 1, 0.9], [-0.9, 0.9, 1]], "positive semi-definite"),
        ([[1, 0.5], [0.4, 1]], "symmetric"),
        ([[1, 1.2], [1.2, 1]], "between -1 and 1"),
        ([[1, 0], [0, 0.9]], "diagonal"),
        ([[1]], "square"),
    ],
)
def test_invalid_correlation_matrices(corr, frag):
    with pytest.raises(FinanceError, match=frag):
        fin.check_correlation(corr, 3 if len(corr) == 3 else 2)


def test_two_asset_volatility_closed_forms():
    eq = lambda rho: fin.portfolio_analytics(["A", "B"], [0.5, 0.5], [0.05, 0.07], [0.2, 0.2], [[1, rho], [rho, 1]])  # noqa: E731
    assert eq(1)["volatility"] == pytest.approx(0.2)  # perfect correlation: no diversification
    assert eq(0)["volatility"] == pytest.approx(0.2 / math.sqrt(2))
    assert eq(-1)["volatility"] == pytest.approx(0.0, abs=1e-9)
    assert eq(1)["diversification_ratio"] == pytest.approx(1.0)
    assert eq(0)["expected_return"] == pytest.approx(0.06)


def test_risk_contributions_sum_to_one_and_match_euler_decomposition():
    rng = random.Random(3)
    for _ in range(40):
        n = rng.randint(2, 6)
        w = [rng.random() for _ in range(n)]
        w = [x / sum(w) for x in w]
        sig = [rng.uniform(0.05, 0.4) for _ in range(n)]
        # random valid correlation matrix: normalised Gram matrix
        g = [[rng.gauss(0, 1) for _ in range(n)] for _ in range(n)]
        cov = [[sum(g[i][k] * g[j][k] for k in range(n)) for j in range(n)] for i in range(n)]
        corr = [[cov[i][j] / math.sqrt(cov[i][i] * cov[j][j]) for j in range(n)] for i in range(n)]
        a = fin.portfolio_analytics([f"a{i}" for i in range(n)], w, [0.05] * n, sig, corr)
        assert sum(x["risk_contribution"] for x in a["assets"]) == pytest.approx(1.0)
        # finite-difference check: d(vol)/d(w_i) * w_i / vol
        def vol(ws):
            return math.sqrt(sum(ws[i] * ws[j] * sig[i] * sig[j] * corr[i][j] for i in range(n) for j in range(n)))
        for i in range(n):
            h = 1e-6
            up = list(w); up[i] += h
            dn = list(w); dn[i] -= h
            assert w[i] * (vol(up) - vol(dn)) / (2 * h) / vol(w) == pytest.approx(a["assets"][i]["risk_contribution"], abs=1e-5)


@pytest.mark.parametrize(
    "kw,frag",
    [
        (dict(weights=[0.6]), "100%"), (dict(weights=[1.2, -0.2], names=["A", "B"], mu=[0.1, 0.1], sigma=[0.1, 0.1], corr=[[1, 0], [0, 1]]), "short"),
        (dict(sigma=[-0.1]), "negative"), (dict(names=["A", "A"], weights=[0.5, 0.5], mu=[0.1, 0.1], sigma=[0.1, 0.1], corr=[[1, 0], [0, 1]]), "uniquely"),
        (dict(mu=[0.1, 0.1]), "each asset"),
    ],
)
def test_portfolio_validation(kw, frag):
    base = dict(names=["A"], weights=[1.0], mu=[0.07], sigma=[0.2], corr=ONE)
    base.update(kw)
    with pytest.raises(FinanceError, match=frag):
        fin.portfolio_analytics(**base)


# ------------------------------------------------------------------ VaR / ES
def test_empirical_var_es_known_values():
    losses = [float(i) for i in range(1, 101)]
    var, es, k = fin.var_es_empirical(losses, 0.95)
    assert (k, var, es) == (5, 96.0, 98.0)
    var, es, k = fin.var_es_empirical(losses, 0.99)
    assert (k, var, es) == (1, 100.0, 100.0)  # 1% of 100 observations: just the single worst loss


def test_empirical_es_is_never_below_var_and_is_monotone_in_confidence():
    rng = random.Random(2)
    for _ in range(100):
        xs = [rng.gauss(0, 1) for _ in range(rng.randint(50, 400))]
        prev = None
        for c in (0.9, 0.95, 0.99):
            v, e, k = fin.var_es_empirical(xs, c)
            assert e >= v and k >= 1
            if prev:
                assert v >= prev[0] and e >= prev[1]
            prev = (v, e)


def test_floating_point_boundary_does_not_inflate_tail_count():
    assert fin.var_es_empirical([float(i) for i in range(100)], 0.95)[2] == 5  # (1-0.95)*100 = 5.000000000000004 in floats


def test_normal_var_es_textbook_values():
    v, e = fin.var_es_normal(0.0, 1.0, 0.95)
    assert v == pytest.approx(1.6449, abs=1e-4) and e == pytest.approx(2.0627, abs=1e-4)
    v, e = fin.var_es_normal(0.0, 1.0, 0.99)
    assert v == pytest.approx(2.3263, abs=1e-4) and e == pytest.approx(2.6652, abs=1e-4)
    v, e = fin.var_es_normal(0.1, 0.2, 0.95)
    assert v == pytest.approx(-0.1 + 0.2 * 1.6449, abs=1e-4)


def test_empirical_var_converges_to_normal_var_on_normal_data():
    rng = random.Random(9)
    xs = [-rng.gauss(0.001, 0.01) for _ in range(200000)]
    v, e, _ = fin.var_es_empirical(xs, 0.99)
    pv, pe = fin.var_es_normal(0.001, 0.01, 0.99)
    assert v == pytest.approx(pv, rel=0.03) and e == pytest.approx(pe, rel=0.03)


def test_kupiec_known_cases():
    assert fin.kupiec(5, 100, 0.95)["lr"] == pytest.approx(0, abs=1e-9) and fin.kupiec(5, 100, 0.95)["p_value"] == pytest.approx(1)
    k = fin.kupiec(10, 100, 0.95)
    p, pi, n, x = 0.05, 0.1, 100, 10
    ref = -2 * (((n - x) * math.log(1 - p) + x * math.log(p)) - ((n - x) * math.log(1 - pi) + x * math.log(pi)))
    assert k["lr"] == pytest.approx(ref) and k["p_value"] == pytest.approx(math.erfc(math.sqrt(ref / 2))) and k["p_value"] < 0.05
    assert fin.kupiec(0, 250, 0.99)["p_value"] < 1  # zero exceedances is defined
    with pytest.raises(FinanceError):
        fin.kupiec(5, 3, 0.95)


def test_confidence_validation():
    for c in (0.4, 1.0, 1.5):
        with pytest.raises(FinanceError):
            fin.var_es_empirical([1.0, 2.0], c)


# ------------------------------------------------------------------ historical analysis
def hist(series, weights=None, ppy=252, conf=(0.95,)):
    names = list(series)
    weights = weights or {n: 1 / len(names) for n in names}
    return fin.historical_analysis(series, weights, ppy, list(conf))


def noise(n, seed, mu=0.0005, sd=0.01):
    r = random.Random(seed)
    return [r.gauss(mu, sd) for _ in range(n)]


def test_drawdown_and_total_return_known_values():
    s = [0.1, -0.2, 0.05] + [0.0] * 17
    a = hist({"X": s})["assets"]["X"]
    assert a["max_drawdown"] == pytest.approx(0.2, abs=1e-12)  # 1.1 -> 0.88 is a 20% fall from the peak
    assert a["total_return"] == pytest.approx(1.1 * 0.8 * 1.05 - 1)
    assert a["best_period"] == 0.1 and a["worst_period"] == -0.2


def test_statistics_match_independent_calculation():
    s = noise(500, 4)
    a = hist({"X": s})["assets"]["X"]
    m = sum(s) / 500
    sd = math.sqrt(sum((x - m) ** 2 for x in s) / 499)
    assert a["mean_period"] == pytest.approx(m) and a["vol_period"] == pytest.approx(sd)
    assert a["annualised_vol"] == pytest.approx(sd * math.sqrt(252))
    growth = math.prod(1 + x for x in s)
    assert a["cagr"] == pytest.approx(growth ** (252 / 500) - 1)


def test_normal_data_has_near_zero_skew_and_kurtosis_and_fat_tails_are_detected():
    a = hist({"X": noise(5000, 5)})["assets"]["X"]  # sampling error: skew ~0.035, kurtosis ~0.07
    assert abs(a["skewness"]) < 0.15 and abs(a["excess_kurtosis"]) < 0.3
    r = random.Random(6)
    fat = [r.gauss(0, 0.01) / math.sqrt(r.gammavariate(1.5, 2) / 3) for _ in range(5000)]  # Student-t(3)
    assert hist({"X": fat})["assets"]["X"]["excess_kurtosis"] > 2


def test_correlation_and_portfolio_series():
    a = noise(200, 1)
    out = hist({"A": a, "B": [x * 2 for x in a], "C": [-x for x in a]}, {"A": 0.5, "B": 0.5, "C": 0})
    c = out["correlation"]
    assert c[0][1] == pytest.approx(1.0) and c[0][2] == pytest.approx(-1.0) and c[0][0] == pytest.approx(1)
    port = [0.5 * x + 0.5 * 2 * x for x in a]
    assert out["portfolio"]["mean_period"] == pytest.approx(sum(port) / 200)


def test_historical_risk_block_and_thin_tail_warning():
    out = hist({"X": noise(1000, 2)}, conf=(0.95, 0.99))
    r95, r99 = out["risk"]
    assert r95["tail_observations"] == 50 and r99["tail_observations"] == 10 and r95["warning"] is None
    assert r99["historical"]["es"] >= r99["historical"]["var"] >= r95["historical"]["var"]
    thin = hist({"X": noise(60, 2)}, conf=(0.99,))["risk"][0]
    assert thin["tail_observations"] == 1 and "unreliable" in thin["warning"]
    # on normal data the parametric VaR is not rejected by the Kupiec test
    assert r95["kupiec_parametric"]["p_value"] > 0.01


def test_growth_series_is_consistent():
    s = noise(2000, 8)
    out = hist({"X": s})
    assert out["growth"][-1]["t"] == 1999 and len(out["growth"]) <= 301
    assert out["growth"][-1]["value"] == pytest.approx(math.prod(1 + x for x in s))
    assert all(0 <= g["drawdown"] < 1 for g in out["growth"])


@pytest.mark.parametrize(
    "mut,frag",
    [
        (lambda s, w: s.update(B=[0.01] * 5), "same number"),
        (lambda s, w: s.update(A=[0.01] * 10, B=[0.01] * 10), "between 20 and 5000"),
        (lambda s, w: s["A"].__setitem__(3, -1.0), "greater than -100%"),
        (lambda s, w: s["A"].__setitem__(3, float("nan")), "finite"),
        (lambda s, w: w.update(A=0.9), "100%"),
        (lambda s, w: w.pop("A"), "weight for every"),
    ],
)
def test_historical_validation(mut, frag):
    s = {"A": noise(30, 1), "B": noise(30, 2)}
    w = {"A": 0.5, "B": 0.5}
    mut(s, w)
    with pytest.raises(FinanceError, match=frag):
        fin.historical_analysis(s, w, 252, [0.95])


# ------------------------------------------------------------------ stress testing
def test_stress_impact_and_contributions_are_exact():
    out = fin.stress_test(["Eq", "Bond", "Cash"], [0.6, 0.3, 0.1], 100000.0,
                          [{"name": "Equity crash", "shocks": {"Eq": -0.3, "Bond": 0.02}}, {"name": "Boom", "shocks": {"Eq": 0.2}}], reverse_target=0.1)
    crash = out["scenarios"][0]
    assert crash["portfolio_return"] == pytest.approx(0.6 * -0.3 + 0.3 * 0.02)
    assert crash["pnl"] == pytest.approx(-17400) and crash["value_after"] == pytest.approx(82600)
    assert sum(c["contribution"] for c in crash["contributions"]) == pytest.approx(crash["portfolio_return"])
    assert out["worst"] == "Equity crash"
    # reverse stress: scale the shock so the loss equals the 10% target, then verify
    s = crash["scale_to_target"]
    assert s * crash["portfolio_return"] == pytest.approx(-0.1) and out["scenarios"][1]["scale_to_target"] is None


@pytest.mark.parametrize(
    "scen,frag",
    [
        ([{"name": "x", "shocks": {"Nope": -0.1}}], "not in the portfolio"),
        ([{"name": "x", "shocks": {"A": -1.5}}], "-100%"),
        ([{"name": "x", "shocks": {}}, {"name": "x", "shocks": {}}], "unique"),
        ([], "between 1 and 20"),
    ],
)
def test_stress_validation(scen, frag):
    with pytest.raises(FinanceError, match=frag):
        fin.stress_test(["A", "B"], [0.5, 0.5], 1000.0, scen, None)


# ------------------------------------------------------------------ Monte Carlo
def test_single_asset_matches_the_lognormal_model_exactly_in_distribution():
    r = mc(iterations=20000, horizon_years=2.0, seed=3)
    t, mu, s = 2.0, 0.07, 0.2
    stats = r["terminal"]["return"]
    # E[V_T] = V0 e^{mu T} exactly under the model; the simulated mean must agree within sampling error
    assert r["terminal"]["analytic_mean_value"] == pytest.approx(1000 * math.exp(mu * t), rel=1e-12)
    assert abs(r["terminal"]["mean_value"] - r["terminal"]["analytic_mean_value"]) < 4.5 * r["terminal"]["se_mean_value"]
    # log-return mean (mu - s^2/2) T and sd s sqrt(T)
    assert math.log(1 + stats["p50"]) == pytest.approx((mu - s * s / 2) * t, abs=0.02)
    sd_log = (math.log(1 + stats["p95"]) - math.log(1 + stats["p05"])) / (2 * 1.6449)
    assert sd_log == pytest.approx(s * math.sqrt(t), rel=0.03)


def test_monte_carlo_var_es_converge_to_analytic_lognormal_values():
    r = mc(iterations=20000, horizon_years=1.0, seed=4, confidences=[0.95, 0.99])
    mu, s, t = 0.07, 0.2, 1.0
    m, sd = (mu - s * s / 2) * t, s * math.sqrt(t)
    for row in r["risk"]:
        a = 1 - row["confidence"]
        za = N.inv_cdf(a)
        var = 1 - math.exp(m + sd * za)
        es = 1 - math.exp(mu * t) * N.cdf(za - sd) / a
        assert row["mc_var"] == pytest.approx(var, rel=0.06) and row["mc_es"] == pytest.approx(es, rel=0.06)
        assert row["mc_es"] >= row["mc_var"]


def test_perfect_correlation_gives_no_diversification_and_negative_correlation_reduces_risk():
    one = lambda rho: mc(names=["A", "B"], weights=[0.5, 0.5], mu=[0.07, 0.07], sigma=[0.2, 0.2], corr=[[1, rho], [rho, 1]], iterations=8000, seed=5)  # noqa: E731
    sd = lambda r: r["terminal"]["return"]["sd"]  # noqa: E731
    assert sd(one(1)) == pytest.approx(sd(mc(iterations=8000, seed=5)), rel=0.02)
    assert sd(one(-1)) < 0.25 * sd(one(1))  # rebalancing monthly keeps the hedge nearly perfect


def test_rebalance_options_and_buy_and_hold_expectation():
    kw = dict(names=["A", "B"], weights=[0.5, 0.5], mu=[0.04, 0.10], sigma=[0.1, 0.25], corr=[[1, 0.2], [0.2, 1]], horizon_years=3.0, iterations=12000)
    hold = mc(rebalance="none", seed=6, **kw)
    reb = mc(rebalance="every_step", seed=6, **kw)
    for r in (hold, reb):
        assert abs(r["terminal"]["mean_value"] - r["terminal"]["analytic_mean_value"]) < 4.5 * r["terminal"]["se_mean_value"]
    assert hold["terminal"]["analytic_mean_value"] > reb["terminal"]["analytic_mean_value"]  # rebalancing sells winners: lower expected growth here


def test_student_t_has_fatter_tails_than_normal_at_equal_variance():
    n = mc(iterations=20000, seed=7, confidences=[0.99], horizon_years=0.25, steps_per_year=52)
    t = mc(iterations=20000, seed=7, tails="student_t", df=3.5, confidences=[0.99], horizon_years=0.25, steps_per_year=52)
    assert t["terminal"]["return"]["sd"] == pytest.approx(n["terminal"]["return"]["sd"], rel=0.12)
    assert t["terminal"]["return"]["min"] < n["terminal"]["return"]["min"]
    assert t["terminal"]["analytic_mean_value"] is None and "unstable" in t["notes"][-1]


def test_reproducibility_and_seed_sensitivity():
    a, b, c = mc(seed=9, iterations=1000), mc(seed=9, iterations=1000), mc(seed=10, iterations=1000)
    assert a["result_hash"] == b["result_hash"] and a["terminal"] == b["terminal"]
    assert a["result_hash"] != c["result_hash"]


def test_fan_chart_and_drawdown_outputs():
    r = mc(iterations=1000, horizon_years=2.0, loss_threshold=0.1, drawdown_threshold=0.1)
    fan = r["fan"]
    assert fan[0]["t"] == 0 and fan[0]["p05"] == fan[0]["p95"] == 1000.0 and fan[-1]["t"] == pytest.approx(2.0)
    assert all(f["p05"] <= f["p25"] <= f["p50"] <= f["p75"] <= f["p95"] for f in fan)
    assert fan[-1]["p95"] - fan[-1]["p05"] > fan[3]["p95"] - fan[3]["p05"]  # uncertainty widens with time
    assert 0 <= r["max_drawdown"]["mean"] <= 1 and r["max_drawdown"]["p_exceeds"]["threshold"] == 0.1
    assert r["p_loss_exceeds"]["p"] <= r["p_loss"] <= 1
    # a path's max drawdown is at least its loss from the starting value, so exceeding 10% drawdown is at least as likely
    assert r["max_drawdown"]["p_exceeds"]["p"] >= r["p_loss_exceeds"]["p"]


def test_max_drawdown_is_at_least_the_terminal_loss():
    r = mc(iterations=2000, seed=11, mu=[-0.2], sigma=[0.1], horizon_years=1.0)
    # per path: max drawdown >= max(0, loss from start), so on average it is at least the mean loss
    assert r["max_drawdown"]["mean"] >= -r["terminal"]["return"]["mean"]


@pytest.mark.parametrize(
    "kw,frag",
    [
        (dict(iterations=100), "iterations"), (dict(iterations=10**6), "iterations"), (dict(horizon_years=0.01), "horizon"), (dict(horizon_years=50), "horizon"),
        (dict(steps_per_year=7), "steps per year"), (dict(rebalance="daily"), "rebalance"), (dict(tails="cauchy"), "tails"),
        (dict(tails="student_t", df=2), "degrees of freedom"), (dict(initial_value=0), "initial value"), (dict(confidences=[]), "confidence"),
        (dict(weights=[0.5]), "100%"),
    ],
)
def test_monte_carlo_validation(kw, frag):
    with pytest.raises(FinanceError, match=frag):
        mc(**kw)


def test_work_limit_rejects_oversized_runs():
    n = 10
    with pytest.raises(FinanceError, match="too large"):
        mc(names=[f"a{i}" for i in range(n)], weights=[0.1] * n, mu=[0.05] * n, sigma=[0.2] * n, corr=[[1.0 if i == j else 0.1 for j in range(n)] for i in range(n)],
           iterations=20000, horizon_years=30, steps_per_year=52)
