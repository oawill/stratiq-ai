"""Calibrated ensemble of the football models. Pure; deterministic.

Step 1, pooling: a weighted average of the member models' 1X2 probabilities. The weights (non-negative, summing to one, in steps of
0.1) are the combination with the lowest log loss on the VALIDATION period.
Step 2, calibration: one temperature T is fitted on the same validation rows, so the pooled probabilities p become p^(1/T) renormalised.
T > 1 flattens an over-confident ensemble, T < 1 sharpens an under-confident one.

Both steps use validation rows only; the test period is never touched. With three members that is three numbers fitted on a season of
matches, so the ensemble is only worth trusting if it also beats its members on the later test period (the backtest reports that).
"""
from __future__ import annotations

import itertools
import math

from .football_models import golden

STEP = 10      # weights are multiples of 1/STEP


def pool(weights: dict[str, float], probs: dict[str, list[float]]) -> list[float]:
    out = [0.0, 0.0, 0.0]
    for name, w in weights.items():
        for k in range(3):
            out[k] += w * probs[name][k]
    s = sum(out)
    return [v / s for v in out]


def temper(p: list[float], temperature: float) -> list[float]:
    q = [max(v, 1e-12) ** (1.0 / temperature) for v in p]
    s = sum(q)
    return [v / s for v in q]


def _ll(rows: list[tuple[list[float], int]]) -> float:
    return sum(-math.log(max(p[y], 1e-12)) for p, y in rows) / len(rows)


def fit_ensemble(members: dict[str, list[list[float]]], y: list[int]) -> dict:
    """`members[name][i]` is that model's [home, draw, away] for validation match i; `y[i]` the actual outcome (0, 1, 2)."""
    names = sorted(members)
    n = len(y)
    if n < 50 or any(len(v) != n for v in members.values()):
        raise ValueError("The ensemble needs at least 50 validation matches predicted by every member model.")
    best = None
    for combo in itertools.product(range(STEP + 1), repeat=len(names)):
        if sum(combo) != STEP:
            continue
        w = {nm: c / STEP for nm, c in zip(names, combo)}
        ll = _ll([(pool(w, {nm: members[nm][i] for nm in names}), y[i]) for i in range(n)])
        if best is None or ll < best[0] - 1e-12:
            best = (ll, w)
    ll_pooled, weights = best
    pooled = [pool(weights, {nm: members[nm][i] for nm in names}) for i in range(n)]
    t = golden(lambda T: _ll([(temper(p, T), y[i]) for i, p in enumerate(pooled)]), 0.6, 1.8)
    ll_cal = _ll([(temper(p, t), y[i]) for i, p in enumerate(pooled)])
    return {"members": names, "weights": weights, "temperature": t, "validation_log_loss_pooled": ll_pooled, "validation_log_loss_calibrated": ll_cal,
            "validation_matches": n,
            "member_validation_log_loss": {nm: _ll([(members[nm][i], y[i]) for i in range(n)]) for nm in names}}


def apply_ensemble(params: dict, probs: dict[str, list[float]]) -> list[float]:
    return temper(pool(params["weights"], {nm: probs[nm] for nm in params["members"]}), params["temperature"])
