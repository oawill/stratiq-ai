"""Financial risk mathematics: portfolio analytics, VaR / Expected Shortfall, stress tests, Monte Carlo.

Educational scenario analysis only. Nothing here is investment advice, nothing fetches market data, and nothing
can place an order. Historical analysis runs only on return series the user supplies; there is no built-in dataset.
Portfolios are long-only and fully invested (weights >= 0, summing to 1): no leverage and no short positions.
"""
from __future__ import annotations

import hashlib
import math
import random
import struct
import sys
import time
from statistics import NormalDist
from typing import Any

from .simulation import percentile, summarise

ENGINE_VERSION = "0.1.0"
MAX_ASSETS = 10
MAX_MC_WORK = 30_000_000  # iterations * steps * n(n+1)/2
_N = NormalDist()


class FinanceError(ValueError):
    pass


def _fin(x: Any, what: str) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise FinanceError(f"{what} must be a finite number")
    return float(x)


# ================================================================== portfolio inputs
def check_weights(weights: list[float]) -> None:
    if any(w < 0 for w in weights):
        raise FinanceError("weights must be 0 or more (no short positions in this version)")
    if abs(sum(weights) - 1) > 1e-6:
        raise FinanceError(f"weights must add up to 100% (they add up to {sum(weights) * 100:.4g}%)")


def check_correlation(corr: list[list[float]], n: int) -> None:
    if len(corr) != n or any(len(r) != n for r in corr):
        raise FinanceError("the correlation matrix must be square, one row and column per asset")
    for i in range(n):
        if abs(corr[i][i] - 1) > 1e-9:
            raise FinanceError("the correlation matrix must have 1 on its diagonal")
        for j in range(n):
            v = _fin(corr[i][j], "correlation")
            if not -1 <= v <= 1:
                raise FinanceError("correlations must be between -1 and 1")
            if abs(v - corr[j][i]) > 1e-9:
                raise FinanceError("the correlation matrix must be symmetric")
    cholesky(corr)  # raises if not positive semi-definite


def cholesky(a: list[list[float]]) -> list[list[float]]:
    """Lower-triangular L with L L^T = a. Accepts positive *semi*-definite matrices (e.g. correlation = +/-1)."""
    n = len(a)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = a[i][j] - sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                if s < -1e-9:
                    raise FinanceError("the correlation matrix is not positive semi-definite (the correlations are mutually inconsistent)")
                L[i][j] = math.sqrt(max(s, 0.0))
            else:
                L[i][j] = 0.0 if L[j][j] < 1e-12 else s / L[j][j]
    # verify (catches inconsistent matrices whose failure shows up off-diagonal)
    for i in range(n):
        for j in range(n):
            if abs(sum(L[i][k] * L[j][k] for k in range(n)) - a[i][j]) > 1e-7:
                raise FinanceError("the correlation matrix is not positive semi-definite (the correlations are mutually inconsistent)")
    return L


def portfolio_analytics(names: list[str], weights: list[float], mu: list[float], sigma: list[float], corr: list[list[float]]) -> dict:
    n = len(names)
    if not 1 <= n <= MAX_ASSETS or len(set(names)) != n:
        raise FinanceError(f"between 1 and {MAX_ASSETS} uniquely named assets are needed")
    if not (len(weights) == len(mu) == len(sigma) == n):
        raise FinanceError("each asset needs a weight, expected return and volatility")
    check_weights(weights)
    if any(s < 0 for s in sigma):
        raise FinanceError("volatility cannot be negative")
    check_correlation(corr, n)
    cov = [[sigma[i] * sigma[j] * corr[i][j] for j in range(n)] for i in range(n)]
    cw = [sum(cov[i][j] * weights[j] for j in range(n)) for i in range(n)]
    var = sum(weights[i] * cw[i] for i in range(n))
    vol = math.sqrt(max(var, 0.0))
    wsig = sum(w * s for w, s in zip(weights, sigma))
    rc = [(weights[i] * cw[i] / var) if var > 0 else 0.0 for i in range(n)]
    return {
        "expected_return": sum(w * m for w, m in zip(weights, mu)),
        "volatility": vol,
        "diversification_ratio": (wsig / vol) if vol > 0 else 1.0,
        "assets": [{"name": names[i], "weight": weights[i], "risk_contribution": rc[i], "stand_alone_vol": sigma[i]} for i in range(n)],
        "notes": ["Arithmetic annual figures; the expected return is your assumption, not a forecast."],
    }


# ================================================================== VaR / ES
def var_es_empirical(losses: list[float], c: float) -> tuple[float, float, int]:
    """Empirical VaR and ES. With n losses sorted worst-first L1 >= L2 >= ...: k = ceil((1-c) n),
    VaR = L_k and ES = mean(L_1..L_k). Always ES >= VaR. k is returned so callers can flag thin tails."""
    if not 0.5 <= c < 1:
        raise FinanceError("confidence must be at least 50% and below 100%")
    n = len(losses)
    if n < 1:
        raise FinanceError("no observations")
    k = max(1, math.ceil(round((1 - c) * n, 9)))
    worst = sorted(losses, reverse=True)[:k]
    return worst[-1], math.fsum(worst) / k, k


def var_es_normal(mean_return: float, sd: float, c: float) -> tuple[float, float]:
    """Delta-normal VaR and ES of *losses* for returns ~ N(mean, sd^2)."""
    z = _N.inv_cdf(c)
    return -mean_return + sd * z, -mean_return + sd * _N.pdf(z) / (1 - c)


def kupiec(exceedances: int, n: int, c: float) -> dict:
    """Kupiec proportion-of-failures test: are exceedances consistent with the VaR confidence level?"""
    p = 1 - c
    x = exceedances
    if n < 1 or not 0 <= x <= n:
        raise FinanceError("invalid backtest counts")

    def ll(prob: float) -> float:
        a = (n - x) * math.log(1 - prob) if n - x else 0.0
        b = x * math.log(prob) if x else 0.0
        return a + b

    pi = x / n  # at pi = 0 or 1 the skipped log terms are exactly 0, so no special case is needed
    lr = max(0.0, -2 * (ll(p) - ll(pi)))
    return {"exceedances": x, "observations": n, "expected": p * n, "lr": lr, "p_value": math.erfc(math.sqrt(lr / 2))}


# ================================================================== historical analysis
def _skew_kurt(xs: list[float]) -> tuple[float, float]:
    n = len(xs)
    m = math.fsum(xs) / n
    s2 = math.fsum((x - m) ** 2 for x in xs) / n
    if s2 == 0:
        return 0.0, 0.0
    s = math.sqrt(s2)
    return math.fsum(((x - m) / s) ** 3 for x in xs) / n, math.fsum(((x - m) / s) ** 4 for x in xs) / n - 3


def _max_drawdown(rets: list[float]) -> float:
    v, peak, mdd = 1.0, 1.0, 0.0
    for r in rets:
        v *= 1 + r
        peak = max(peak, v)
        mdd = max(mdd, (peak - v) / peak)
    return mdd


def _corr(a: list[float], b: list[float]) -> float:
    n = len(a)
    ma, mb = math.fsum(a) / n, math.fsum(b) / n
    sab = math.fsum((x - ma) * (y - mb) for x, y in zip(a, b))
    saa, sbb = math.fsum((x - ma) ** 2 for x in a), math.fsum((y - mb) ** 2 for y in b)
    d = math.sqrt(saa * sbb)
    return 0.0 if d == 0 else sab / d


def _series_stats(rets: list[float], ppy: int) -> dict:
    n = len(rets)
    mean = math.fsum(rets) / n
    sd = math.sqrt(math.fsum((x - mean) ** 2 for x in rets) / (n - 1))
    growth = 1.0
    for r in rets:
        growth *= 1 + r
    sk, ku = _skew_kurt(rets)
    return {
        "periods": n, "mean_period": mean, "vol_period": sd, "annualised_mean": mean * ppy, "annualised_vol": sd * math.sqrt(ppy),
        "total_return": growth - 1, "cagr": growth ** (ppy / n) - 1, "max_drawdown": _max_drawdown(rets),
        "skewness": sk, "excess_kurtosis": ku, "best_period": max(rets), "worst_period": min(rets),
    }


def historical_analysis(series: dict[str, list[float]], weights: dict[str, float], ppy: int, confidences: list[float]) -> dict:
    names = list(series)
    if not 1 <= len(names) <= MAX_ASSETS:
        raise FinanceError(f"between 1 and {MAX_ASSETS} return series are needed")
    n = len(series[names[0]])
    if any(len(v) != n for v in series.values()):
        raise FinanceError("every series must have the same number of observations")
    if not 20 <= n <= 5000:
        raise FinanceError("each series needs between 20 and 5000 observations")
    for nm, v in series.items():
        for x in v:
            if not math.isfinite(x) or x <= -1:
                raise FinanceError(f"'{nm}': returns must be finite and greater than -100%")
    if set(weights) != set(names):
        raise FinanceError("give a weight for every series")
    w = [weights[nm] for nm in names]
    check_weights(w)
    if not 1 <= ppy <= 366:
        raise FinanceError("periods per year must be between 1 and 366")
    if not confidences or len(confidences) > 4:
        raise FinanceError("choose between 1 and 4 confidence levels")

    port = [math.fsum(w[i] * series[names[i]][t] for i in range(len(names))) for t in range(n)]
    stats = _series_stats(port, ppy)
    losses = [-r for r in port]
    mean, sd = stats["mean_period"], stats["vol_period"]
    risk = []
    for c in sorted(set(confidences)):
        hv, hes, k = var_es_empirical(losses, c)
        pv, pes = var_es_normal(mean, sd, c)
        exc = sum(1 for x in losses if x > pv)
        risk.append({
            "confidence": c, "tail_observations": k,
            "historical": {"var": hv, "es": hes}, "parametric_normal": {"var": pv, "es": pes},
            "kupiec_parametric": kupiec(exc, n, c),
            "warning": f"Only {k} observation(s) define the tail: treat this estimate as unreliable." if k < 5 else None,
        })
    pts = []
    v = 1.0
    peak = 1.0
    for r in port:
        v *= 1 + r
        peak = max(peak, v)
        pts.append((v, (peak - v) / peak))
    step = max(1, math.ceil(len(pts) / 300))
    return {
        "periods_per_year": ppy,
        "assets": {nm: _series_stats(series[nm], ppy) for nm in names},
        "correlation": [[_corr(series[a], series[b]) for b in names] for a in names],
        "names": names, "weights": w, "portfolio": stats, "risk": risk,
        "growth": [{"t": i, "value": pts[i][0], "drawdown": pts[i][1]} for i in range(0, len(pts), step)] + ([] if (len(pts) - 1) % step == 0 else [{"t": len(pts) - 1, "value": pts[-1][0], "drawdown": pts[-1][1]}]),
        "provenance": "User-supplied data. Not verified, not from a market-data provider.",
        "notes": ["Portfolio returns assume constant weights (rebalanced every period).", "Losses are negative returns; VaR/ES are shown as positive loss fractions of portfolio value."],
    }


# ================================================================== stress testing
def stress_test(names: list[str], weights: list[float], initial_value: float, scenarios: list[dict], reverse_target: float | None) -> dict:
    n = len(names)
    if not 1 <= n <= MAX_ASSETS or len(set(names)) != n or len(weights) != n:
        raise FinanceError(f"between 1 and {MAX_ASSETS} uniquely named assets are needed")
    check_weights(weights)
    if not 1 <= len(scenarios) <= 20:
        raise FinanceError("define between 1 and 20 scenarios")
    if len({s["name"] for s in scenarios}) != len(scenarios):
        raise FinanceError("scenario names must be unique")
    out = []
    for s in scenarios:
        sh = s["shocks"]
        if set(sh) - set(names):
            raise FinanceError(f"scenario '{s['name']}' shocks an asset that is not in the portfolio")
        shocks = [sh.get(nm, 0.0) for nm in names]
        for x in shocks:
            if _fin(x, "shock") < -1:
                raise FinanceError("a shock cannot be below -100%")
        contrib = [weights[i] * shocks[i] for i in range(n)]
        impact = math.fsum(contrib)
        res = {
            "name": s["name"], "portfolio_return": impact, "pnl": impact * initial_value, "value_after": initial_value * (1 + impact),
            "contributions": [{"asset": names[i], "shock": shocks[i], "contribution": contrib[i], "pnl": contrib[i] * initial_value} for i in range(n)],
        }
        if reverse_target is not None:
            res["scale_to_target"] = (-reverse_target / impact) if impact < 0 else None
        out.append(res)
    worst = min(out, key=lambda r: r["portfolio_return"])
    return {"scenarios": out, "worst": worst["name"], "reverse_target": reverse_target,
            "notes": ["Instantaneous revaluation: each asset moves by its shock, weights as given. No rebalancing, hedging, liquidity or second-round effects.",
                      "Shocks are hypothetical inputs, not predictions or statements about past events."]}


# ================================================================== Monte Carlo
def monte_carlo(names: list[str], weights: list[float], mu: list[float], sigma: list[float], corr: list[list[float]], initial_value: float,
                horizon_years: float, steps_per_year: int, iterations: int, rebalance: str, tails: str, df: float, seed: int,
                confidences: list[float], loss_threshold: float | None, drawdown_threshold: float | None) -> dict:
    portfolio_analytics(names, weights, mu, sigma, corr)  # validates everything
    n = len(names)
    if rebalance not in ("every_step", "none"):
        raise FinanceError("rebalance must be 'every_step' or 'none'")
    if tails not in ("normal", "student_t"):
        raise FinanceError("tails must be 'normal' or 'student_t'")
    if tails == "student_t" and not 3 <= df <= 100:
        raise FinanceError("degrees of freedom must be between 3 and 100")
    if not 0.1 <= horizon_years <= 30:
        raise FinanceError("horizon must be between 0.1 and 30 years")
    if steps_per_year not in (4, 12, 52):
        raise FinanceError("steps per year must be 4, 12 or 52")
    if not 500 <= iterations <= 20000:
        raise FinanceError("iterations must be between 500 and 20000")
    if initial_value <= 0:
        raise FinanceError("initial value must be positive")
    steps = max(1, round(horizon_years * steps_per_year))
    if iterations * steps * n * (n + 1) / 2 > MAX_MC_WORK:
        raise FinanceError("this run is too large; reduce the iterations, horizon, step frequency or number of assets")
    if not confidences or len(confidences) > 4:
        raise FinanceError("choose between 1 and 4 confidence levels")

    t0 = time.perf_counter()
    rng = random.Random(seed)
    dt = 1.0 / steps_per_year
    horizon = steps * dt
    L = cholesky(corr)
    drift = [(mu[i] - sigma[i] ** 2 / 2) * dt for i in range(n)]
    vol = [sigma[i] * math.sqrt(dt) for i in range(n)]
    t_scale = math.sqrt((df - 2) / df) if tails == "student_t" else 1.0
    marks = sorted({round(steps * k / 24) for k in range(25)})
    mark_set = set(marks)
    exp = math.exp
    gauss = rng.gauss
    rng_gamma = rng.gammavariate

    finals: list[float] = []
    mdds: list[float] = []
    path_marks: dict[int, list[float]] = {m: [] for m in marks}
    h = hashlib.sha256()
    pack = struct.Struct("<2d").pack
    rows = [(i, L[i][: i + 1]) for i in range(n)]
    for _ in range(iterations):
        if rebalance == "none":
            hold = [initial_value * weights[i] for i in range(n)]
        v = initial_value
        peak = v
        mdd = 0.0
        if 0 in mark_set:
            path_marks[0].append(v)
        for step in range(1, steps + 1):
            z = [gauss(0.0, 1.0) for _ in range(n)]
            if tails == "student_t":
                m = t_scale / math.sqrt(rng_gamma(df / 2, 2.0) / df)
            else:
                m = 1.0
            r = [drift[i] + vol[i] * m * math.fsum(L[i][k] * z[k] for k in range(i + 1)) for i in range(n)]
            if rebalance == "every_step":
                v *= math.fsum(weights[i] * exp(r[i]) for i in range(n))
            else:
                for i in range(n):
                    hold[i] *= exp(r[i])
                v = math.fsum(hold)
            if v > peak:
                peak = v
            elif peak - v > mdd * peak:
                mdd = (peak - v) / peak
            if step in mark_set:
                path_marks[step].append(v)
        finals.append(v)
        mdds.append(mdd)
        h.update(pack(v, mdd))

    rets = [v / initial_value - 1 for v in finals]
    losses = [-r for r in rets]
    summ = summarise(rets, None)
    out_risk = []
    cov = [[sigma[i] * sigma[j] * corr[i][j] for j in range(n)] for i in range(n)]
    mu_p = sum(w * m for w, m in zip(weights, mu))
    sd_p = math.sqrt(max(sum(weights[i] * weights[j] * cov[i][j] for i in range(n) for j in range(n)), 0.0))
    for c in sorted(set(confidences)):
        var, es, k = var_es_empirical(losses, c)
        pv, pes = var_es_normal(mu_p * horizon, sd_p * math.sqrt(horizon), c)
        out_risk.append({"confidence": c, "mc_var": var, "mc_es": es, "tail_observations": k, "approx_normal_var": pv, "approx_normal_es": pes})
    fan = []
    for m in marks:
        xs = sorted(path_marks[m])
        fan.append({"t": m * dt, "p05": percentile(xs, 0.05), "p25": percentile(xs, 0.25), "p50": percentile(xs, 0.5), "p75": percentile(xs, 0.75), "p95": percentile(xs, 0.95)})
    se_v = math.sqrt(math.fsum((x - math.fsum(finals) / iterations) ** 2 for x in finals) / (iterations - 1)) / math.sqrt(iterations)
    analytic = None
    if tails == "normal":  # exact expectation under the model (for checking the simulation)
        if rebalance == "every_step":
            analytic = initial_value * math.fsum(weights[i] * exp(mu[i] * dt) for i in range(n)) ** steps
        else:
            analytic = initial_value * math.fsum(weights[i] * exp(mu[i] * horizon) for i in range(n))
    return {
        "engine_version": ENGINE_VERSION, "python_version": ".".join(map(str, sys.version_info[:3])), "seed": seed, "iterations": iterations,
        "steps": steps, "horizon_years": horizon, "result_hash": h.hexdigest(), "runtime_ms": round((time.perf_counter() - t0) * 1000),
        "terminal": {
            "mean_value": math.fsum(finals) / iterations, "se_mean_value": se_v, "analytic_mean_value": analytic,
            "median_value": initial_value * (1 + summ["stats"]["p50"]), "return": summ["stats"], "histogram": summ["histogram"],
            "p5_value": initial_value * (1 + summ["stats"]["p05"]), "p95_value": initial_value * (1 + summ["stats"]["p95"]),
        },
        "p_loss": sum(1 for x in rets if x < 0) / iterations,
        "p_loss_exceeds": None if loss_threshold is None else {"threshold": loss_threshold, "p": sum(1 for x in losses if x > loss_threshold) / iterations},
        "max_drawdown": {"mean": math.fsum(mdds) / iterations, "p95": percentile(sorted(mdds), 0.95),
                         "p_exceeds": None if drawdown_threshold is None else {"threshold": drawdown_threshold, "p": sum(1 for x in mdds if x > drawdown_threshold) / iterations}},
        "risk": out_risk, "fan": fan,
        "model": {"rebalance": rebalance, "tails": tails, "df": df if tails == "student_t" else None},
        "notes": [
            "Scenario simulation under the assumptions you entered; not a forecast of returns.",
            "Risk figures are loss fractions of the starting value over the whole horizon.",
            "Student-t tails make simulated means unstable (the exact mean does not exist for lognormal-t growth); rely on percentiles, VaR and ES." if tails == "student_t" else "Returns are lognormal with constant volatility and correlation: real markets have volatility clustering and correlation breakdowns that this model omits.",
        ],
    }
