"""Reproducible Monte Carlo engine shared by every domain. Pure Python, no I/O, no AI.

A simulation is: input variables drawn from probability distributions, plus output
formulas over those variables. Formulas are parsed with `ast`, validated against a strict
whitelist (arithmetic, comparisons, a few math functions) and compiled; they are never
passed to an unrestricted eval. A run with the same config and seed reproduces the same
draws (and `result_hash`) on the same Python version.
"""
from __future__ import annotations

import ast
import bisect
import hashlib
import math
import random
import re
import struct
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

from .brand import NAME

ENGINE_VERSION = "0.1.0"
MIN_ITER, MAX_ITER = 100, 200_000
MAX_VARS, MAX_OUTPUTS = 12, 5
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,30}$")
HIST_BINS = 30
CHECKPOINTS = 20


class ConfigError(ValueError):
    """The simulation definition is invalid (reported to the user)."""


class SimulationError(RuntimeError):
    """The model failed while running (e.g. division by zero)."""


class Cancelled(Exception):
    pass


# ------------------------------------------------------------------ expressions
FUNCS: dict[str, Callable[..., float]] = {
    "min": min,
    "max": max,
    "abs": abs,
    "sqrt": math.sqrt,
    "exp": math.exp,
    "log": math.log,
    "log10": math.log10,
    "floor": math.floor,
    "ceil": math.ceil,
    "clip": lambda x, lo, hi: max(lo, min(hi, x)),
}
_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow)
_UNARY = (ast.UAdd, ast.USub, ast.Not)
_CMPOPS = (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)
MAX_EXPR_LEN, MAX_NODES = 500, 200


class _Floats(ast.NodeTransformer):
    """Turn every numeric literal into a float so huge integer powers can never be computed exactly."""

    def visit_Constant(self, node: ast.Constant):
        return ast.copy_location(ast.Constant(float(node.value)), node)


def compile_expr(expr: str, names: set[str]):
    if not isinstance(expr, str) or not expr.strip():
        raise ConfigError("formula is empty")
    if len(expr) > MAX_EXPR_LEN:
        raise ConfigError(f"formula is longer than {MAX_EXPR_LEN} characters")
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        raise ConfigError(f"formula syntax error: {e.msg}") from None
    except (RecursionError, MemoryError, ValueError):
        raise ConfigError("formula is too complex or malformed") from None
    count = 0

    def check(n: ast.AST, depth: int = 0) -> None:
        nonlocal count
        count += 1
        if count > MAX_NODES or depth > 40:
            raise ConfigError("formula is too complex")
        if isinstance(n, ast.Expression):
            check(n.body, depth + 1)
        elif isinstance(n, ast.BinOp):
            if not isinstance(n.op, _BINOPS):
                raise ConfigError("only + - * / % ** are allowed")
            check(n.left, depth + 1), check(n.right, depth + 1)
        elif isinstance(n, ast.UnaryOp):
            if not isinstance(n.op, _UNARY):
                raise ConfigError("unsupported unary operator")
            check(n.operand, depth + 1)
        elif isinstance(n, ast.BoolOp):
            for v in n.values:
                check(v, depth + 1)
        elif isinstance(n, ast.Compare):
            if not all(isinstance(o, _CMPOPS) for o in n.ops):
                raise ConfigError("unsupported comparison")
            check(n.left, depth + 1)
            for c in n.comparators:
                check(c, depth + 1)
        elif isinstance(n, ast.IfExp):
            check(n.test, depth + 1), check(n.body, depth + 1), check(n.orelse, depth + 1)
        elif isinstance(n, ast.Call):
            if not isinstance(n.func, ast.Name) or n.func.id not in FUNCS or n.keywords:
                raise ConfigError(f"only these functions are allowed: {', '.join(sorted(FUNCS))}")
            if not n.args:
                raise ConfigError(f"{n.func.id}() needs arguments")
            for a in n.args:
                if isinstance(a, ast.Starred):
                    raise ConfigError("unpacking is not allowed")
                check(a, depth + 1)
        elif isinstance(n, ast.Name):
            if n.id not in names:
                raise ConfigError(f"unknown name '{n.id}' (use a variable or an earlier output)")
        elif isinstance(n, ast.Constant):
            if isinstance(n.value, bool) or not isinstance(n.value, (int, float)):
                raise ConfigError("only numeric constants are allowed")
        else:
            raise ConfigError(f"'{type(n).__name__}' is not allowed in a formula")

    try:
        check(tree)
        tree = ast.fix_missing_locations(_Floats().visit(tree))
    except RecursionError:
        raise ConfigError("formula is too complex") from None
    return compile(tree, "<formula>", "eval")


# ------------------------------------------------------------------ distributions
def _num(d: dict, key: str, lo: float | None = None, hi: float | None = None, *, lo_open=False, hi_open=False) -> float:
    v = d.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ConfigError(f"'{key}' must be a finite number")
    if lo is not None and (v <= lo if lo_open else v < lo):
        raise ConfigError(f"'{key}' must be {'greater than' if lo_open else 'at least'} {lo:g}")
    if hi is not None and (v >= hi if hi_open else v > hi):
        raise ConfigError(f"'{key}' must be {'less than' if hi_open else 'at most'} {hi:g}")
    return float(v)


def _poisson(lam: float) -> Callable[[random.Random], float]:
    limit = math.exp(-lam)

    def draw(rng: random.Random) -> float:
        k, p = 0, 1.0
        while True:
            p *= rng.random()
            if p <= limit:
                return float(k)
            k += 1

    return draw


def make_sampler(d: Any) -> Callable[[random.Random], float]:
    if not isinstance(d, dict) or "type" not in d:
        raise ConfigError("distribution needs a 'type'")
    t = d["type"]
    if t == "normal":
        m, s = _num(d, "mean"), _num(d, "sd", 0, lo_open=True)
        return lambda r: r.gauss(m, s)
    if t == "lognormal":  # parameterised by the mean and sd of the variable itself
        m, s = _num(d, "mean", 0, lo_open=True), _num(d, "sd", 0, lo_open=True)
        s2 = math.log(1 + (s / m) ** 2)
        mu, sg = math.log(m) - s2 / 2, math.sqrt(s2)
        return lambda r: r.lognormvariate(mu, sg)
    if t == "uniform":
        lo, hi = _num(d, "low"), _num(d, "high")
        if not lo < hi:
            raise ConfigError("'low' must be less than 'high'")
        return lambda r: r.uniform(lo, hi)
    if t == "triangular":
        lo, mode, hi = _num(d, "low"), _num(d, "mode"), _num(d, "high")
        if not (lo < hi and lo <= mode <= hi):
            raise ConfigError("need low < high and low <= mode <= high")
        return lambda r: r.triangular(lo, hi, mode)
    if t == "beta":
        a, b = _num(d, "alpha", 0, lo_open=True), _num(d, "beta", 0, lo_open=True)
        return lambda r: r.betavariate(a, b)
    if t == "bernoulli":
        p = _num(d, "p", 0, 1)
        return lambda r: 1.0 if r.random() < p else 0.0
    if t == "binomial":
        n, p = int(_num(d, "n", 1, 1000)), _num(d, "p", 0, 1)
        if hasattr(random.Random, "binomialvariate"):
            return lambda r: float(r.binomialvariate(n, p))
        return lambda r: float(sum(1 for _ in range(n) if r.random() < p))
    if t == "poisson":
        return _poisson(_num(d, "lambda", 0, 50, lo_open=True))
    if t == "constant":
        v = _num(d, "value")
        return lambda r: v
    if t == "discrete":
        items = d.get("values")
        if not isinstance(items, list) or not (2 <= len(items) <= 20):
            raise ConfigError("'values' must list 2 to 20 {value, p} items")
        vals, probs = [], []
        for it in items:
            if not isinstance(it, dict):
                raise ConfigError("each discrete item must be {value, p}")
            vals.append(_num(it, "value"))
            probs.append(_num(it, "p", 0, 1))
        if abs(sum(probs) - 1) > 1e-6:
            raise ConfigError("discrete probabilities must sum to 1")
        cum, acc = [], 0.0
        for p in probs:
            acc += p
            cum.append(acc)
        return lambda r: vals[min(bisect.bisect_right(cum, r.random()), len(vals) - 1)]
    raise ConfigError(f"unknown distribution '{t}'")


# ------------------------------------------------------------------ config
@dataclass(frozen=True)
class Variable:
    name: str
    dist: dict
    sampler: Callable[[random.Random], float]


@dataclass(frozen=True)
class Output:
    name: str
    expr: str
    code: Any
    threshold: float | None


@dataclass(frozen=True)
class Config:
    iterations: int
    seed: int
    variables: list[Variable]
    outputs: list[Output]


def parse_config(iterations: int, seed: int, variables: list[dict], outputs: list[dict]) -> Config:
    if isinstance(iterations, bool) or not isinstance(iterations, int) or not MIN_ITER <= iterations <= MAX_ITER:
        raise ConfigError(f"iterations must be an integer between {MIN_ITER:,} and {MAX_ITER:,}")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**31:
        raise ConfigError("seed must be an integer between 0 and 2147483647")
    if not 1 <= len(variables) <= MAX_VARS:
        raise ConfigError(f"define between 1 and {MAX_VARS} variables")
    if not 1 <= len(outputs) <= MAX_OUTPUTS:
        raise ConfigError(f"define between 1 and {MAX_OUTPUTS} outputs")
    seen: set[str] = set()
    vars_: list[Variable] = []
    for v in variables:
        name = v.get("name") if isinstance(v, dict) else None
        if not isinstance(name, str) or not NAME_RE.match(name) or name in FUNCS:
            raise ConfigError(f"invalid variable name {name!r} (letters, digits, underscore; not a function name)")
        if name in seen:
            raise ConfigError(f"duplicate name '{name}'")
        seen.add(name)
        try:
            vars_.append(Variable(name, v.get("dist"), make_sampler(v.get("dist"))))
        except ConfigError as e:
            raise ConfigError(f"variable '{name}': {e}") from None
    outs: list[Output] = []
    for o in outputs:
        name = o.get("name") if isinstance(o, dict) else None
        if not isinstance(name, str) or not NAME_RE.match(name) or name in FUNCS:
            raise ConfigError(f"invalid output name {name!r}")
        if name in seen:
            raise ConfigError(f"duplicate name '{name}'")
        try:
            code = compile_expr(o.get("expr"), set(seen))
        except ConfigError as e:
            raise ConfigError(f"output '{name}': {e}") from None
        th = o.get("threshold")
        if th is not None:
            th = _num({"threshold": th}, "threshold")
        seen.add(name)
        outs.append(Output(name, o["expr"].strip(), code, th))
    return Config(iterations, seed, vars_, outs)


# ------------------------------------------------------------------ statistics
def percentile(sorted_xs: list[float], q: float) -> float:
    """Linear-interpolation percentile (same convention as numpy's default)."""
    n = len(sorted_xs)
    if n == 1:
        return sorted_xs[0]
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (pos - lo)


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=xs.__getitem__)
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(a: list[float], b: list[float]) -> float:
    n = len(a)
    ma, mb = math.fsum(a) / n, math.fsum(b) / n
    sab = math.fsum((x - ma) * (y - mb) for x, y in zip(a, b))
    saa = math.fsum((x - ma) ** 2 for x in a)
    sbb = math.fsum((y - mb) ** 2 for y in b)
    d = math.sqrt(saa * sbb)
    return 0.0 if d == 0 else sab / d


def spearman(a: list[float], b: list[float]) -> float:
    return _pearson(_ranks(a), _ranks(b))


def summarise(xs: list[float], threshold: float | None) -> dict:
    n = len(xs)
    mean = math.fsum(xs) / n
    sd = math.sqrt(math.fsum((x - mean) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    s = sorted(xs)
    se = sd / math.sqrt(n)
    lo, hi = s[0], s[-1]
    if hi > lo:
        w = (hi - lo) / HIST_BINS
        counts = [0] * HIST_BINS
        for x in xs:
            counts[min(int((x - lo) / w), HIST_BINS - 1)] += 1
        edges = [lo + w * i for i in range(HIST_BINS + 1)]
    else:
        counts, edges = [n], [lo, hi]
    out = {
        "stats": {
            "mean": mean, "sd": sd, "min": lo, "max": hi,
            "p05": percentile(s, 0.05), "p25": percentile(s, 0.25), "p50": percentile(s, 0.5),
            "p75": percentile(s, 0.75), "p95": percentile(s, 0.95),
            "se_mean": se, "ci95_mean": [mean - 1.96 * se, mean + 1.96 * se],
        },
        "histogram": {"edges": edges, "counts": counts},
        "prob_above": None,
    }
    if threshold is not None:
        p = sum(1 for x in xs if x > threshold) / n
        out["prob_above"] = {"threshold": threshold, "p": p, "se": math.sqrt(p * (1 - p) / n)}
    return out


# ------------------------------------------------------------------ run
def run(cfg: Config, progress: Callable[[int, int], bool | None] | None = None, chunk: int = 2000) -> dict:
    """Run the simulation. `progress(done, total)` may return False to cancel."""
    t0 = time.perf_counter()
    rng = random.Random(cfg.seed)
    n = cfg.iterations
    vnames = [v.name for v in cfg.variables]
    samplers = [v.sampler for v in cfg.variables]
    onames = [o.name for o in cfg.outputs]
    codes = [o.code for o in cfg.outputs]
    vcols: list[list[float]] = [[] for _ in vnames]
    ocols: list[list[float]] = [[] for _ in onames]
    env = {"__builtins__": {}, **FUNCS}
    h = hashlib.sha256()
    pack = struct.Struct(f"<{len(onames)}d").pack
    sums = [0.0] * len(onames)
    marks = {max(1, round(n * (i + 1) / CHECKPOINTS)) for i in range(CHECKPOINTS)}
    convergence: list[dict] = []

    for i in range(n):
        loc: dict[str, float] = {}
        for k, (nm, smp) in enumerate(zip(vnames, samplers)):
            x = smp(rng)
            loc[nm] = x
            vcols[k].append(x)
        row = []
        try:
            for k, (nm, code) in enumerate(zip(onames, codes)):
                y = float(eval(code, env, loc))  # noqa: S307 - code is whitelist-validated above
                if not math.isfinite(y):
                    raise ArithmeticError("result is not a finite number")
                loc[nm] = y
                row.append(y)
        except (ArithmeticError, ValueError, TypeError) as e:
            raise SimulationError(f"output '{nm}' failed at iteration {i + 1}: {e}") from None
        for k, y in enumerate(row):
            ocols[k].append(y)
            sums[k] += y
        h.update(pack(*row))
        if (i + 1) in marks:
            convergence.append({"n": i + 1, "means": [s / (i + 1) for s in sums]})
        if progress and ((i + 1) % chunk == 0 or i + 1 == n):
            if progress(i + 1, n) is False:
                raise Cancelled()

    outputs = {}
    for k, o in enumerate(cfg.outputs):
        res = summarise(ocols[k], o.threshold)
        res["expr"] = o.expr
        res["sensitivity"] = sorted(
            ({"variable": vn, "spearman": spearman(vcols[j], ocols[k])} for j, vn in enumerate(vnames)),
            key=lambda d: -abs(d["spearman"]),
        )
        res["convergence"] = [{"n": c["n"], "mean": c["means"][k]} for c in convergence]
        outputs[o.name] = res
    inputs = {}
    for j, v in enumerate(cfg.variables):
        xs = vcols[j]
        m = math.fsum(xs) / n
        inputs[v.name] = {
            "dist": v.dist, "realised_mean": m,
            "realised_sd": math.sqrt(math.fsum((x - m) ** 2 for x in xs) / (n - 1)),
            "realised_min": min(xs), "realised_max": max(xs),
        }
    return {
        "engine_version": ENGINE_VERSION,
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "iterations": n,
        "seed": cfg.seed,
        "result_hash": h.hexdigest(),
        "runtime_ms": round((time.perf_counter() - t0) * 1000),
        "outputs": outputs,
        "inputs": inputs,
    }


def pilot(cfg: Config, n: int = 200) -> dict:
    """Tiny run used for live validation feedback in the UI (never stored)."""
    small = Config(max(n, 1), cfg.seed, cfg.variables, cfg.outputs)
    res = run(small)
    return {name: {"mean": o["stats"]["mean"], "min": o["stats"]["min"], "max": o["stats"]["max"]} for name, o in res["outputs"].items()}


# ------------------------------------------------------------------ comparison & reports
def compare(results: list[dict], titles: list[str]) -> dict:
    """Side-by-side summary of completed runs. Differences use independent-sample standard errors."""
    names = sorted({k for r in results for k in r["outputs"]})
    table = []
    for name in names:
        rows = []
        for r, title in zip(results, titles):
            o = r["outputs"].get(name)
            rows.append(None if o is None else {"title": title, "iterations": r["iterations"], "seed": r["seed"], **o["stats"], "prob_above": o["prob_above"]})
        base = next((x for x in rows if x), None)
        diffs = []
        for x in rows:
            if x is None or base is None or x is base:
                diffs.append(None)
                continue
            d = x["mean"] - base["mean"]
            se = math.sqrt(x["se_mean"] ** 2 + base["se_mean"] ** 2)
            diffs.append({"mean_diff": d, "se": se, "ci95": [d - 1.96 * se, d + 1.96 * se]})
        table.append({"output": name, "runs": rows, "diff_vs_first": diffs})
    return {"outputs": table}


def report_markdown(title: str, domain: str, cfg: dict, result: dict) -> str:
    L = [f"# {title}", "", f"- Domain: {domain}", f"- Iterations: {result['iterations']:,}", f"- Seed: {result['seed']}",
         f"- Engine: {NAME} Monte Carlo {result['engine_version']} (Python {result['python_version']})",
         f"- Result hash: `{result['result_hash']}`", "",
         "> Scenario assumptions only. Results describe the entered model, not a forecast of real outcomes.", "",
         "## Input variables", ""]
    for name, i in result["inputs"].items():
        L.append(f"- **{name}** ~ {i['dist']}  (realised mean {i['realised_mean']:.6g}, sd {i['realised_sd']:.6g})")
    for name, o in result["outputs"].items():
        s = o["stats"]
        L += ["", f"## Output: {name}", "", f"Formula: `{o['expr']}`", "",
              "| Statistic | Value |", "|---|---|",
              f"| Mean | {s['mean']:.6g} (95% CI {s['ci95_mean'][0]:.6g} to {s['ci95_mean'][1]:.6g}) |",
              f"| Std dev | {s['sd']:.6g} |", f"| Min / Max | {s['min']:.6g} / {s['max']:.6g} |",
              f"| 5th / 50th / 95th percentile | {s['p05']:.6g} / {s['p50']:.6g} / {s['p95']:.6g} |"]
        if o["prob_above"]:
            p = o["prob_above"]
            L.append(f"| P(> {p['threshold']:g}) | {p['p'] * 100:.2f}% (SE {p['se'] * 100:.2f}%) |")
        L += ["", "Sensitivity (Spearman rank correlation with the output):", ""]
        L += [f"- {x['variable']}: {x['spearman']:+.3f}" for x in o["sensitivity"]]
    L += ["", "## Configuration (for reproduction)", "", "```json", __import__("json").dumps(cfg, indent=2), "```", ""]
    return "\n".join(L)


def report_csv(title: str, result: dict) -> str:
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["title", title]), w.writerow(["iterations", result["iterations"]]), w.writerow(["seed", result["seed"]])
    w.writerow(["engine_version", result["engine_version"]]), w.writerow(["result_hash", result["result_hash"]]), w.writerow([])
    w.writerow(["output", "statistic", "value"])
    for name, o in result["outputs"].items():
        for k, v in o["stats"].items():
            w.writerow([name, k, v if not isinstance(v, list) else f"{v[0]}..{v[1]}"])
        if o["prob_above"]:
            w.writerow([name, f"prob_above_{o['prob_above']['threshold']:g}", o["prob_above"]["p"]])
        for x in o["sensitivity"]:
            w.writerow([name, f"spearman_{x['variable']}", x["spearman"]])
    w.writerow([]), w.writerow(["output", "bin_start", "bin_end", "count"])
    for name, o in result["outputs"].items():
        e, c = o["histogram"]["edges"], o["histogram"]["counts"]
        for i, cnt in enumerate(c):
            w.writerow([name, e[i], e[i + 1], cnt])
    return buf.getvalue()
