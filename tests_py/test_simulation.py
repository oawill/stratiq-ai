import math
import statistics

import pytest

from stratiq import simulation as sim
from stratiq.simulation import Cancelled, ConfigError, SimulationError, parse_config


def cfg(variables, outputs, n=20000, seed=1):
    return parse_config(n, seed, variables, outputs)


def V(name, **dist):
    return {"name": name, "dist": dist}


def run1(dist, n=40000, seed=7):
    c = cfg([{"name": "x", "dist": dist}], [{"name": "y", "expr": "x"}], n=n, seed=seed)
    r = sim.run(c)
    return r["outputs"]["y"]["stats"], r


# ------------------------------------------------------------------ distribution moments vs analytic values
@pytest.mark.parametrize(
    "dist,mean,sd",
    [
        ({"type": "normal", "mean": 10, "sd": 2}, 10, 2),
        ({"type": "uniform", "low": 2, "high": 8}, 5, math.sqrt(36 / 12)),
        ({"type": "triangular", "low": 0, "mode": 2, "high": 10}, 4, math.sqrt((0 + 4 + 100 - 0 - 0 - 20) / 18)),
        ({"type": "lognormal", "mean": 50, "sd": 20}, 50, 20),
        ({"type": "beta", "alpha": 2, "beta": 5}, 2 / 7, math.sqrt(2 * 5 / (49 * 8))),
        ({"type": "bernoulli", "p": 0.3}, 0.3, math.sqrt(0.21)),
        ({"type": "binomial", "n": 20, "p": 0.4}, 8, math.sqrt(4.8)),
        ({"type": "poisson", "lambda": 4}, 4, 2),
        ({"type": "constant", "value": 3.5}, 3.5, 0),
        ({"type": "discrete", "values": [{"value": 1, "p": 0.2}, {"value": 5, "p": 0.8}]}, 4.2, math.sqrt(0.2 * 0.8 * 16)),
    ],
)
def test_distribution_moments(dist, mean, sd):
    s, _ = run1(dist)
    se = max(sd, 1e-12) / math.sqrt(40000)
    assert abs(s["mean"] - mean) < 5 * se + 1e-9
    assert s["sd"] == pytest.approx(sd, rel=0.03, abs=1e-9)


def test_bounds_respected():
    s, _ = run1({"type": "uniform", "low": 2, "high": 8})
    assert 2 <= s["min"] and s["max"] <= 8
    s, _ = run1({"type": "beta", "alpha": 2, "beta": 2})
    assert 0 <= s["min"] and s["max"] <= 1
    s, _ = run1({"type": "bernoulli", "p": 0.5})
    assert s["min"] == 0 and s["max"] == 1


# ------------------------------------------------------------------ outputs, probabilities, sensitivity
def test_probability_of_sum_of_uniforms():
    c = cfg([V("a", type="uniform", low=0, high=1), V("b", type="uniform", low=0, high=1)],
            [{"name": "s", "expr": "a + b", "threshold": 1}], n=60000)
    o = sim.run(c)["outputs"]["s"]
    assert o["prob_above"]["p"] == pytest.approx(0.5, abs=5 * o["prob_above"]["se"])
    assert o["stats"]["mean"] == pytest.approx(1.0, abs=0.01)


def test_variance_of_sum_of_independent_normals():
    c = cfg([V("a", type="normal", mean=0, sd=3), V("b", type="normal", mean=0, sd=4)], [{"name": "s", "expr": "a + b"}], n=60000)
    assert sim.run(c)["outputs"]["s"]["stats"]["sd"] == pytest.approx(5.0, rel=0.02)


def test_outputs_can_reference_earlier_outputs():
    c = cfg([V("x", type="constant", value=4)], [{"name": "a", "expr": "x * 2"}, {"name": "b", "expr": "a + 1"}], n=100)
    r = sim.run(c)["outputs"]
    assert r["a"]["stats"]["mean"] == 8 and r["b"]["stats"]["mean"] == 9


def test_sensitivity_ranks_drivers_correctly():
    c = cfg([V("big", type="normal", mean=0, sd=1), V("small", type="normal", mean=0, sd=1), V("none", type="normal", mean=0, sd=1)],
            [{"name": "y", "expr": "3 * big + 0.2 * small"}], n=30000)
    sens = sim.run(c)["outputs"]["y"]["sensitivity"]
    assert [s["variable"] for s in sens][0] == "big" and sens[0]["spearman"] > 0.95
    by = {s["variable"]: s["spearman"] for s in sens}
    assert abs(by["none"]) < 0.03 and 0.03 < by["small"] < 0.2


def test_negative_driver_has_negative_spearman():
    c = cfg([V("x", type="uniform", low=0, high=1)], [{"name": "y", "expr": "10 - x"}], n=2000)
    assert sim.run(c)["outputs"]["y"]["sensitivity"][0]["spearman"] == pytest.approx(-1.0)


def test_percentiles_match_statistics_module():
    s, r = run1({"type": "normal", "mean": 0, "sd": 1}, n=5001)
    # reconstruct the same samples to cross-check against the stdlib implementation
    import random
    rng = random.Random(7)
    xs = sorted(rng.gauss(0, 1) for _ in range(5001))
    q = statistics.quantiles(xs, n=20, method="inclusive")
    assert s["p05"] == pytest.approx(q[0]) and s["p50"] == pytest.approx(statistics.median(xs)) and s["p95"] == pytest.approx(q[-1])


def test_histogram_counts_sum_to_n_and_convergence_is_recorded():
    r = sim.run(cfg([V("x", type="normal", mean=5, sd=1)], [{"name": "y", "expr": "x"}], n=1000))
    o = r["outputs"]["y"]
    assert sum(o["histogram"]["counts"]) == 1000 and len(o["histogram"]["edges"]) == len(o["histogram"]["counts"]) + 1
    assert o["convergence"][-1]["n"] == 1000 and len(o["convergence"]) == sim.CHECKPOINTS
    assert o["convergence"][-1]["mean"] == pytest.approx(o["stats"]["mean"])
    assert o["stats"]["ci95_mean"][0] < o["stats"]["mean"] < o["stats"]["ci95_mean"][1]


# ------------------------------------------------------------------ reproducibility
def test_same_seed_same_result_different_seed_differs():
    mk = lambda seed: cfg([V("x", type="normal", mean=0, sd=1), V("k", type="binomial", n=10, p=0.5)],  # noqa: E731
                          [{"name": "y", "expr": "x + k"}], n=3000, seed=seed)
    a, b, c = sim.run(mk(42)), sim.run(mk(42)), sim.run(mk(43))
    assert a["result_hash"] == b["result_hash"] and a["outputs"] == b["outputs"]
    assert a["result_hash"] != c["result_hash"]


def test_chunk_size_does_not_change_results():
    c = cfg([V("x", type="normal", mean=0, sd=1)], [{"name": "y", "expr": "x"}], n=5000, seed=5)
    assert sim.run(c, chunk=100)["result_hash"] == sim.run(c, chunk=4999)["result_hash"]


def test_progress_callback_and_cancellation():
    c = cfg([V("x", type="uniform", low=0, high=1)], [{"name": "y", "expr": "x"}], n=10000)
    seen = []
    sim.run(c, progress=lambda d, t: seen.append((d, t)), chunk=2500)
    assert seen == [(2500, 10000), (5000, 10000), (7500, 10000), (10000, 10000)]
    with pytest.raises(Cancelled):
        sim.run(c, progress=lambda d, t: d < 5000 or False, chunk=2500)


# ------------------------------------------------------------------ safety of user formulas
HOSTILE = [
    "__import__('os').system('echo hi')",
    "().__class__.__bases__[0].__subclasses__()",
    "x.__class__",
    "open('/etc/passwd')",
    "[i for i in range(10)]",
    "lambda: 1",
    "x[0]",
    "'string'",
    "eval('1')",
    "exec('1')",
    "max(*[1, 2])",
    "max(key=abs)",
    "True",
    "x if x else __builtins__",
    "(yield)",
    "x := 3",
    "f'{x}'",
    "x // 2",
    "x << 2",
    "x & 1",
    "",
    "   ",
    "x +",
    "unknown_var + 1",
    "max",
    "a" * 600,
    "-" * 60 + "x",
    "-" * 20000 + "x",
    "(" * 500 + "x" + ")" * 500,
    "\x00",
]


@pytest.mark.parametrize("expr", HOSTILE)
def test_hostile_formulas_are_rejected_at_validation(expr):
    with pytest.raises(ConfigError):
        cfg([V("x", type="constant", value=1)], [{"name": "y", "expr": expr}], n=100)


def test_complexity_limit():
    expr = "+".join(["x"] * 150)
    with pytest.raises(ConfigError, match="too complex"):
        cfg([V("x", type="constant", value=1)], [{"name": "y", "expr": expr}], n=100)


def test_runtime_failures_are_reported_not_crashed():
    for expr, frag in [("1 / (x - 1)", "iteration 1"), ("log(x - 5)", "iteration 1"), ("9 ** 9 ** 9", "iteration 1"), ("sqrt(0 - x)", "iteration 1")]:
        c = cfg([V("x", type="constant", value=1)], [{"name": "y", "expr": expr}], n=100)
        with pytest.raises(SimulationError, match=frag):
            sim.run(c)


def test_huge_literal_power_does_not_hang():
    c = cfg([V("x", type="constant", value=1)], [{"name": "y", "expr": "99999999 ** 99999999 + x"}], n=100)
    with pytest.raises(SimulationError):
        sim.run(c)


def test_allowed_constructs_work():
    c = cfg([V("x", type="uniform", low=-5, high=5)],
            [{"name": "y", "expr": "max(x, 0) + min(x, 0) * 2 + abs(x) + sqrt(4) + clip(x, -1, 1) + (1 if x > 0 else 0) + floor(x) + (x > 0 and x < 2)"}], n=500)
    assert math.isfinite(sim.run(c)["outputs"]["y"]["stats"]["mean"])


# ------------------------------------------------------------------ config validation
@pytest.mark.parametrize(
    "dist",
    [
        {"type": "normal", "mean": 0, "sd": 0}, {"type": "normal", "mean": 0}, {"type": "normal", "mean": "0", "sd": 1},
        {"type": "normal", "mean": float("nan"), "sd": 1}, {"type": "uniform", "low": 2, "high": 1},
        {"type": "triangular", "low": 0, "mode": 5, "high": 3}, {"type": "lognormal", "mean": -1, "sd": 1},
        {"type": "beta", "alpha": 0, "beta": 1}, {"type": "bernoulli", "p": 1.5}, {"type": "binomial", "n": 0, "p": 0.5},
        {"type": "binomial", "n": 5000, "p": 0.5}, {"type": "poisson", "lambda": 0}, {"type": "poisson", "lambda": 500},
        {"type": "discrete", "values": [{"value": 1, "p": 0.5}, {"value": 2, "p": 0.4}]}, {"type": "discrete", "values": [{"value": 1, "p": 1}]},
        {"type": "discrete", "values": ["a", "b"]}, {"type": "mystery"}, {"mean": 1}, "normal", None,
    ],
)
def test_bad_distributions_rejected(dist):
    with pytest.raises(ConfigError):
        parse_config(1000, 1, [{"name": "x", "dist": dist}], [{"name": "y", "expr": "x"}])


@pytest.mark.parametrize(
    "kw",
    [
        {"iterations": 10}, {"iterations": 10**7}, {"iterations": 1000.5}, {"iterations": True},
        {"seed": -1}, {"seed": 2**31}, {"seed": 1.5},
    ],
)
def test_bad_run_parameters(kw):
    args = {"iterations": 1000, "seed": 1, **kw}
    with pytest.raises(ConfigError):
        parse_config(args["iterations"], args["seed"], [V("x", type="constant", value=1)], [{"name": "y", "expr": "x"}])


def test_bad_names_and_counts():
    good_out = [{"name": "y", "expr": "x"}]
    for bad in ["1x", "a b", "max", "", "x" * 40, "a-b"]:
        with pytest.raises(ConfigError):
            parse_config(1000, 1, [V(bad, type="constant", value=1)], good_out)
    with pytest.raises(ConfigError, match="duplicate"):
        parse_config(1000, 1, [V("x", type="constant", value=1), V("x", type="constant", value=2)], good_out)
    with pytest.raises(ConfigError, match="duplicate"):
        parse_config(1000, 1, [V("x", type="constant", value=1)], [{"name": "x", "expr": "1"}])
    with pytest.raises(ConfigError):
        parse_config(1000, 1, [], good_out)
    with pytest.raises(ConfigError):
        parse_config(1000, 1, [V(f"v{i}", type="constant", value=1) for i in range(13)], good_out)
    with pytest.raises(ConfigError):
        parse_config(1000, 1, [V("x", type="constant", value=1)], [{"name": f"o{i}", "expr": "x"} for i in range(6)])


# ------------------------------------------------------------------ comparison & reports
def test_compare_and_reports():
    a = sim.run(cfg([V("x", type="normal", mean=10, sd=1)], [{"name": "y", "expr": "x", "threshold": 10}], n=5000, seed=1))
    b = sim.run(cfg([V("x", type="normal", mean=12, sd=1)], [{"name": "y", "expr": "x", "threshold": 10}], n=5000, seed=2))
    c = sim.compare([a, b], ["A", "B"])
    row = c["outputs"][0]
    d = row["diff_vs_first"][1]
    assert row["diff_vs_first"][0] is None
    assert d["mean_diff"] == pytest.approx(2.0, abs=0.1) and d["ci95"][0] < 2.0 < d["ci95"][1]
    md = sim.report_markdown("T", "business", {"k": 1}, a)
    assert a["result_hash"] in md and "Scenario assumptions only" in md and "Spearman" in md
    csv_text = sim.report_csv("T", a)
    assert "result_hash" in csv_text and "mean" in csv_text and "bin_start" in csv_text
