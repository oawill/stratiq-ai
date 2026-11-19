"""Rolling-origin backtest: for each later match, fit on strictly earlier matches only."""
from __future__ import annotations

import math

from .model import HistMatch, predict


def _outcome(m: HistMatch) -> int:
    return 0 if m.home_goals > m.away_goals else (1 if m.home_goals == m.away_goals else 2)


def _brier(p: list[float], y: int) -> float:
    return sum((p[i] - (1.0 if i == y else 0.0)) ** 2 for i in range(3))


def _logloss(p: list[float], y: int) -> float:
    return -math.log(max(p[y], 1e-12))


def run(matches: list[HistMatch], league_teams: list[str], dataset: str, min_train: int = 40) -> dict:
    ordered = sorted(matches, key=lambda m: (m.kickoff, m.home, m.away))
    b = l = bb = bl = 0.0
    n = 0
    for i, m in enumerate(ordered):
        if i < min_train:
            continue
        prior = ordered[:i]
        pred = predict(prior, league_teams, m.home, m.away, m.kickoff, dataset)["outputs"]
        p = [pred["p_home"], pred["p_draw"], pred["p_away"]]
        y = _outcome(m)
        base_counts = [sum(1 for x in prior if _outcome(x) == k) + 1 for k in range(3)]
        tot = sum(base_counts)
        base = [c / tot for c in base_counts]
        b += _brier(p, y)
        l += _logloss(p, y)
        bb += _brier(base, y)
        bl += _logloss(base, y)
        n += 1
    if n == 0:
        return {"sample_size": 0}
    return {
        "sample_size": n,
        "brier": b / n,
        "log_loss": l / n,
        "baseline_brier": bb / n,
        "baseline_log_loss": bl / n,
    }
