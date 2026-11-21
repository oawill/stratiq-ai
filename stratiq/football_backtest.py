"""Leak-free evaluation of the football models on imported history. Pure; no database.

Chronological mode: tune on a validation period, then report a later test period that nothing was tuned on. Rolling-origin mode:
fixed default settings, each season predicted from all earlier seasons. Every forecast for a fixture uses only matches played
strictly before that fixture's date (Poisson models are refitted each match week from matches before the week's first fixture).
"""
from __future__ import annotations

import bisect
import hashlib
import math
from collections import defaultdict
from datetime import date

from . import football_models as fm
from .football_history import season_label
from .football_models import M, outcome

MODEL_VERSION = "1.0.0"
MODELS = {
    "frequency": "Historical frequencies (baseline)",
    "elo": "Elo rating",
    "poisson": "Time-weighted Poisson",
    "dixon_coles": "Dixon-Coles",
}
DEFAULT_SPLIT = {"training": [f"{y}/{(y + 1) % 100:02d}" for y in range(2016, 2023)], "validation": ["2023/24"], "test": ["2024/25", "2025/26"]}
ELO_GRID = [fm.EloParams(k, 65.0, r, nc) for k in (15.0, 25.0) for r in (0.15, 0.35) for nc in (0.0, -75.0)]
POISSON_GRID = [(hl, pr) for hl in (365.0, 730.0, 1460.0) for pr in (2.0, 6.0)]
DEFAULT_ELO, DEFAULT_POISSON = fm.EloParams(), (730.0, 2.0)
RHO_WINDOW = 1140          # how many earlier fixtures the Dixon-Coles parameter is estimated from
BINS = 10
MIN_SEASONS = 4


def data_sha(ms: list[M]) -> str:
    return hashlib.sha256("\n".join(f"{d}|{h}|{a}|{x}|{y}" for d, h, a, x, y in ms).encode()).hexdigest()


# ------------------------------------------------------------------ metrics
def metrics_1x2(rows: list[tuple[list[float], int]]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    ll = sum(-math.log(max(p[y], 1e-12)) for p, y in rows) / n
    br = sum(sum((p[k] - (1.0 if k == y else 0.0)) ** 2 for k in range(3)) for p, y in rows) / n
    acc = sum(1 for p, y in rows if max(range(3), key=lambda k: p[k]) == y) / n
    bins = [[0, 0.0, 0] for _ in range(BINS)]
    for p, y in rows:
        for k in range(3):
            b = min(int(p[k] * BINS), BINS - 1)
            bins[b][0] += 1
            bins[b][1] += p[k]
            bins[b][2] += 1 if k == y else 0
    rel = [{"low": j / BINS, "high": (j + 1) / BINS, "count": c, "mean_predicted": sp / c, "observed": o / c} for j, (c, sp, o) in enumerate(bins) if c]
    ece = sum(r["count"] * abs(r["mean_predicted"] - r["observed"]) for r in rel) / sum(r["count"] for r in rel)
    return {"n": n, "log_loss": ll, "brier": br, "accuracy": acc, "calibration_error": ece, "reliability": rel}


def metrics_binary(rows: list[tuple[float, int]]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    pc = lambda p: min(max(p, 1e-12), 1 - 1e-12)
    return {"n": n, "log_loss": sum(-(y * math.log(pc(p)) + (1 - y) * math.log(1 - pc(p))) for p, y in rows) / n,
            "brier": sum((p - y) ** 2 for p, y in rows) / n, "accuracy": sum(1 for p, y in rows if (p >= 0.5) == bool(y)) / n}


def metrics_score(rows: list[tuple[float, bool]]) -> dict:
    n = len(rows)
    return {"n": n, "mean_log_probability": sum(math.log(max(p, 1e-12)) for p, _ in rows) / n, "top_scoreline_hit_rate": sum(1 for _, hit in rows if hit) / n} if n else {"n": 0}


def paired_gain(model_ll: list[float], base_ll: list[float]) -> dict:
    """Mean log-loss improvement over a baseline, per fixture, with a standard error."""
    n = len(model_ll)
    if n < 2:
        return {"n": n}
    d = [b - a for a, b in zip(model_ll, base_ll)]
    mean = sum(d) / n
    se = math.sqrt(sum((x - mean) ** 2 for x in d) / (n - 1) / n)
    return {"n": n, "log_loss_gain": mean, "standard_error": se, "clear": bool(se > 0 and mean > 2 * se)}


def summarize(preds: list[dict]) -> dict:
    """Per model: 1X2, over 2.5, both-teams-to-score and correct-score metrics, plus the same by season and gains over the baselines."""
    out: dict = {}
    for model in MODELS:
        rows = [p for p in preds if p["model"] == model]
        if not rows:
            continue
        m = {"1x2": metrics_1x2([(p["probs"], p["actual_outcome"]) for p in rows])}
        if all(p.get("p_over_2_5") is not None for p in rows):
            m["over_2_5"] = metrics_binary([(p["p_over_2_5"], 1 if p["actual"][0] + p["actual"][1] > 2 else 0) for p in rows])
            m["btts"] = metrics_binary([(p["p_btts"], 1 if p["actual"][0] > 0 and p["actual"][1] > 0 else 0) for p in rows])
        if all(p.get("score_probability") is not None for p in rows):
            m["correct_score"] = metrics_score([(p["score_probability"], p["top_scoreline_hit"]) for p in rows])
        by = defaultdict(list)
        for p in rows:
            by[p["season"]].append((p["probs"], p["actual_outcome"]))
        m["by_season"] = {s: {k: v for k, v in metrics_1x2(r).items() if k != "reliability"} for s, r in sorted(by.items())}
        out[model] = m
    key = lambda p: (p["date"], p["home"], p["away"])
    ll = {mod: {key(p): -math.log(max(p["probs"][p["actual_outcome"]], 1e-12)) for p in preds if p["model"] == mod} for mod in MODELS}
    for model in MODELS:
        if model not in out:
            continue
        gains = {}
        for base in ("frequency", "elo"):
            if base != model and base in ll and ll[base]:
                ks = sorted(set(ll[model]) & set(ll[base]))
                gains[f"vs_{base}"] = paired_gain([ll[model][k] for k in ks], [ll[base][k] for k in ks])
        out[model]["gain"] = gains
    return out


# ------------------------------------------------------------------ prediction rows
def _row(model: str, m: M, probs: list[float], inputs: dict, extra: dict | None = None) -> dict:
    d, h, a, hg, ag = m
    row = {"model": model, "date": d.isoformat(), "home": h, "away": a, "season": season_label(d), "probs": probs, "actual": [hg, ag], "actual_outcome": outcome(hg, ag),
           "p_over_2_5": None, "p_btts": None, "score_probability": None, "top_scoreline_hit": None, "inputs": inputs}
    row.update(extra or {})
    return row


def _grid_row(model: str, m: M, lh: float, la: float, rho: float, inputs: dict) -> dict:
    grid = fm.score_grid(lh, la, rho)
    mk = fm.grid_markets(grid)
    hg, ag = m[3], m[4]
    top = mk["top_scorelines"][0]
    return _row(model, m, [mk["p_home"], mk["p_draw"], mk["p_away"]], {**inputs, "rho": rho, "expected_goals": [lh, la]},
                {"p_over_2_5": mk["p_over_2_5"], "p_btts": mk["p_btts"], "xg": [lh, la],
                 "score_probability": grid[hg][ag] if hg <= fm.MAX_GOALS and ag <= fm.MAX_GOALS else 1e-9,
                 "top_scoreline_hit": (top["home"], top["away"]) == (hg, ag), "drivers": fm.poisson_drivers(inputs)})


def walk_poisson(ms: list[M], idxs, half_life: float, prior: float, refit_days: int = 7) -> dict[int, tuple[float, float, dict]]:
    """Expected goals for each fixture index, from a fit made at the start of its match week using only earlier matches."""
    dates = [m[0] for m in ms]
    out, fit, last = {}, None, None
    for i in idxs:
        d = ms[i][0]
        if fit is None or (d - last).days >= refit_days:
            fit = fm.fit_poisson(ms[:bisect.bisect_left(dates, d)], d, half_life, prior, init=fit)
            last = d
        lh, la = fit.rates(ms[i][1], ms[i][2])
        out[i] = (lh, la, {**fit.inputs(ms[i][1], ms[i][2]), "fit_cutoff": last.isoformat(), "matches_in_fit": fit.matches, "half_life_days": half_life, "prior_games": prior})
    return out


def _elo_rows(ms, idxs, pre, ep: fm.EloParams, emap: fm.EloMap) -> list[dict]:
    rows = []
    for i in idxs:
        rh, ra = pre[i]
        probs = fm.elo_probs(rh, ra, ep, emap)
        rows.append(_row("elo", ms[i], probs, {"rating_home": rh, "rating_away": ra, "k": ep.k, "home_adv": ep.home_adv, "regress": ep.regress, "newcomer": ep.newcomer,
                                                "scale": emap.scale, "draw": emap.draw, "offset": emap.offset},
                         {"drivers": [{"factor": "Rating gap including home advantage", "points": rh + ep.home_adv - ra}]}))
    return rows


def _freq_rows(ms, idxs, freq: fm.Frequencies) -> list[dict]:
    rows = []
    for i in idxs:
        f = freq.before(ms[i][0])
        rows.append(_row("frequency", ms[i], f["p"], {"matches_before": f["matches"]}, {"p_over_2_5": f["p_over_2_5"], "p_btts": f["p_btts"]}))
    return rows


def _rho_rows(ms, rates, lo: int, hi: int) -> list[tuple[float, float, int, int]]:
    return [(rates[i][0], rates[i][1], ms[i][3], ms[i][4]) for i in range(lo, hi) if i in rates]


# ------------------------------------------------------------------ chronological run
def _split_bounds(ms: list[M], split: dict) -> tuple[int, int, int]:
    seas = [season_label(m[0]) for m in ms]
    first = lambda names: min((i for i, s in enumerate(seas) if s in names), default=None)
    last = lambda names: max((i for i, s in enumerate(seas) if s in names), default=None)
    v0, v1, t0, t1 = first(split["validation"]), last(split["validation"]), first(split["test"]), last(split["test"])
    if None in (v0, v1, t0, t1):
        raise ValueError("The validation and test seasons are not all present in the imported matches.")
    if not v1 < t0 or v0 == 0:
        raise ValueError("The validation period must come after training and before the test period.")
    return v0, t0, t1 + 1


def default_split(ms: list[M]) -> dict:
    seasons = sorted({season_label(m[0]) for m in ms})
    if all(s in seasons for s in DEFAULT_SPLIT["validation"] + DEFAULT_SPLIT["test"]):
        return {k: [s for s in v if s in seasons] if k != "training" else [s for s in seasons if s not in DEFAULT_SPLIT["validation"] + DEFAULT_SPLIT["test"] and s < DEFAULT_SPLIT["validation"][0]] for k, v in DEFAULT_SPLIT.items()}
    if len(seasons) < MIN_SEASONS:
        raise ValueError(f"At least {MIN_SEASONS} seasons are needed to split by time; {len(seasons)} are imported.")
    return {"training": seasons[:-3], "validation": [seasons[-3]], "test": seasons[-2:]}


def run_chronological(matches: list[M], split: dict | None = None) -> dict:
    ms = sorted(matches, key=lambda m: (m[0], m[1], m[2]))
    split = split or default_split(ms)
    v0, t0, t_end = _split_bounds(ms, split)
    first_season_len = sum(1 for m in ms if season_label(m[0]) == season_label(ms[0][0]))
    burn = min(first_season_len, v0 // 2)           # ratings need a season of history before they are trusted
    val_idx, test_idx = range(v0, t0), range(t0, t_end)
    out = {"mode": "chronological", "split": split, "matches": len(ms), "data_sha256": data_sha(ms),
           "periods": {"training": {"matches": v0, "first": ms[0][0].isoformat(), "last": ms[v0 - 1][0].isoformat()},
                       "validation": {"matches": t0 - v0, "first": ms[v0][0].isoformat(), "last": ms[t0 - 1][0].isoformat()},
                       "test": {"matches": t_end - t0, "first": ms[t0][0].isoformat(), "last": ms[t_end - 1][0].isoformat()}}, "tuning": {}}
    # --- Elo: choose settings on the validation period (mapping fitted on training only), refit the mapping on training + validation for the test period
    best = None
    grid_log = []
    for ep in ELO_GRID:
        pre, _ = fm.elo_pass(ms, ep)
        gaps = [pre[i][0] + ep.home_adv - pre[i][1] for i in range(burn, v0)]
        emap = fm.fit_elo_map(gaps, [outcome(ms[i][3], ms[i][4]) for i in range(burn, v0)])
        ll = metrics_1x2([(fm.elo_probs(*pre[i], ep, emap), outcome(ms[i][3], ms[i][4])) for i in val_idx])["log_loss"]
        grid_log.append({"k": ep.k, "regress": ep.regress, "newcomer": ep.newcomer, "validation_log_loss": ll})
        if best is None or ll < best[0]:
            best = (ll, ep, emap, pre)
    _, ep, map_val, pre = best
    gaps = [pre[i][0] + ep.home_adv - pre[i][1] for i in range(burn, t0)]
    map_test = fm.fit_elo_map(gaps, [outcome(ms[i][3], ms[i][4]) for i in range(burn, t0)])
    out["tuning"]["elo"] = {"grid": grid_log, "chosen": {"k": ep.k, "home_adv": ep.home_adv, "regress": ep.regress, "newcomer": ep.newcomer},
                            "mapping_for_validation": vars(map_val), "mapping_for_test": vars(map_test)}
    # --- Poisson: choose half-life and prior on the validation period
    pgrid, pbest = [], None
    for hl, pr in POISSON_GRID:
        rates = walk_poisson(ms, val_idx, hl, pr)
        ll = metrics_1x2([(_hda(rates[i][0], rates[i][1]), outcome(ms[i][3], ms[i][4])) for i in val_idx])["log_loss"]
        pgrid.append({"half_life_days": hl, "prior_games": pr, "validation_log_loss": ll})
        if pbest is None or ll < pbest[0]:
            pbest = (ll, hl, pr)
    _, hl, pr = pbest
    lo = max(0, v0 - RHO_WINDOW)
    rates = walk_poisson(ms, range(lo, t_end), hl, pr)
    rho_val = fm.fit_rho(_rho_rows(ms, rates, max(0, v0 - RHO_WINDOW), v0))
    rho_test = fm.fit_rho(_rho_rows(ms, rates, max(0, t0 - RHO_WINDOW), t0))
    out["tuning"]["poisson"] = {"grid": pgrid, "chosen": {"half_life_days": hl, "prior_games": pr}}
    out["tuning"]["dixon_coles"] = {"rho_validation": rho_val, "rho_test": rho_test, "rho_window_fixtures": RHO_WINDOW}
    freq = fm.Frequencies(ms)
    preds: list[dict] = []
    for period, idxs, emap, rho in (("validation", val_idx, map_val, rho_val), ("test", test_idx, map_test, rho_test)):
        rows = _freq_rows(ms, idxs, freq) + _elo_rows(ms, idxs, pre, ep, emap)
        rows += [_grid_row("poisson", ms[i], rates[i][0], rates[i][1], 0.0, rates[i][2]) for i in idxs]
        rows += [_grid_row("dixon_coles", ms[i], rates[i][0], rates[i][1], rho, rates[i][2]) for i in idxs]
        for r in rows:
            r["period"] = period
        preds += rows
    out["results"] = {period: summarize([p for p in preds if p["period"] == period]) for period in ("validation", "test")}
    out["predictions"] = preds
    out["warnings"] = ["Settings were chosen on the validation period only. Nothing was tuned on the test period.",
                       "Models use match results only; injuries, expected goals, odds, squad and manager data were not used."]
    return out


def _hda(lh: float, la: float) -> list[float]:
    mk = fm.grid_markets(fm.score_grid(lh, la))
    return [mk["p_home"], mk["p_draw"], mk["p_away"]]


# ------------------------------------------------------------------ rolling origin
def run_rolling(matches: list[M], first_test_season_index: int = 2) -> dict:
    """Each season from the third on is predicted using only earlier seasons, with fixed default settings (nothing tuned)."""
    ms = sorted(matches, key=lambda m: (m[0], m[1], m[2]))
    seasons = sorted({season_label(m[0]) for m in ms})
    if len(seasons) <= first_test_season_index:
        raise ValueError(f"At least {first_test_season_index + 1} seasons are needed for rolling-origin evaluation.")
    seas = [season_label(m[0]) for m in ms]
    start = min(i for i, s in enumerate(seas) if s == seasons[first_test_season_index])
    ep, (hl, pr) = DEFAULT_ELO, DEFAULT_POISSON
    pre, _ = fm.elo_pass(ms, ep)
    lo = max(0, start - RHO_WINDOW)
    rates = walk_poisson(ms, range(lo, len(ms)), hl, pr)
    freq = fm.Frequencies(ms)
    preds: list[dict] = []
    for s in seasons[first_test_season_index:]:
        idxs = [i for i, x in enumerate(seas) if x == s]
        a = idxs[0]
        burn = min(380, a // 2)
        emap = fm.fit_elo_map([pre[i][0] + ep.home_adv - pre[i][1] for i in range(burn, a)], [outcome(ms[i][3], ms[i][4]) for i in range(burn, a)])
        rho = fm.fit_rho(_rho_rows(ms, rates, max(0, a - RHO_WINDOW), a))
        rows = _freq_rows(ms, idxs, freq) + _elo_rows(ms, idxs, pre, ep, emap)
        rows += [_grid_row("poisson", ms[i], rates[i][0], rates[i][1], 0.0, rates[i][2]) for i in idxs]
        rows += [_grid_row("dixon_coles", ms[i], rates[i][0], rates[i][1], rho, rates[i][2]) for i in idxs]
        for r in rows:
            r["period"] = "rolling"
        preds += rows
    return {"mode": "rolling", "matches": len(ms), "data_sha256": data_sha(ms), "seasons_predicted": seasons[first_test_season_index:],
            "settings": {"elo": vars(ep), "poisson": {"half_life_days": hl, "prior_games": pr}}, "results": {"rolling": summarize(preds)}, "predictions": preds,
            "warnings": ["Fixed default settings were used and nothing was tuned, so every season is an honest out-of-sample check.",
                         "Models use match results only; injuries, expected goals, odds, squad and manager data were not used."]}
