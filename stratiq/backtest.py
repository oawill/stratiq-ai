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


MAX_EVAL = 400  # most recent matches scored; bounds the work (each one refits the model)
BINS = 5


def evaluate(matches: list[HistMatch], league_teams: list[str], dataset: str, min_train: int = 100, max_eval: int = MAX_EVAL) -> dict:
    """Rolling-origin evaluation for uploaded data, with the context needed to read it honestly.

    Each scored match is predicted from strictly earlier matches only. The model is compared with a baseline that
    knows only how often home wins, draws and away wins happened before (Laplace-smoothed). Besides Brier score and
    log loss it reports the hit rate, a paired estimate of the log-loss gain with a standard error, and a
    reliability table (how often outcomes happened when the model said a given probability).
    """
    ordered = sorted(matches, key=lambda m: (m.kickoff, m.home, m.away))
    if len(ordered) <= min_train:
        return {"sample_size": 0, "min_train": min_train, "matches": len(ordered)}
    start = max(min_train, len(ordered) - max_eval)
    rows = []  # (model probs, baseline probs, outcome)
    for i in range(start, len(ordered)):
        m = ordered[i]
        prior = ordered[:i]
        pred = predict(prior, league_teams, m.home, m.away, m.kickoff, dataset)["outputs"]
        p = [pred["p_home"], pred["p_draw"], pred["p_away"]]
        counts = [sum(1 for x in prior if _outcome(x) == k) + 1 for k in range(3)]
        tot = sum(counts)
        rows.append((p, [c / tot for c in counts], _outcome(m)))
    n = len(rows)
    ll = [_logloss(p, y) for p, _, y in rows]
    bl = [_logloss(b, y) for _, b, y in rows]
    diff = [b - a for a, b in zip(ll, bl)]  # positive = the model beat the baseline on that match
    mean_d = sum(diff) / n
    se = math.sqrt(sum((d - mean_d) ** 2 for d in diff) / (n - 1) / n) if n > 1 else 0.0
    hits = sum(1 for p, _, y in rows if max(range(3), key=lambda k: p[k]) == y)
    base_hits = sum(1 for _, b, y in rows if max(range(3), key=lambda k: b[k]) == y)
    # Reliability: pool every (match, outcome) probability, bucket it, and compare with how often it came true.
    buckets = [[0, 0.0, 0] for _ in range(BINS)]
    for p, _, y in rows:
        for k in range(3):
            j = min(int(p[k] * BINS), BINS - 1)
            buckets[j][0] += 1
            buckets[j][1] += p[k]
            buckets[j][2] += 1 if k == y else 0
    reliability = [
        {"low": j / BINS, "high": (j + 1) / BINS, "count": c, "mean_predicted": sp / c, "observed": o / c}
        for j, (c, sp, o) in enumerate(buckets) if c
    ]
    model_ll = sum(ll) / n
    base_ll = sum(bl) / n
    return {
        "sample_size": n,
        "matches": len(ordered),
        "min_train": min_train,
        "first_scored": ordered[start].kickoff.date().isoformat(),
        "last_scored": ordered[-1].kickoff.date().isoformat(),
        "brier": sum(_brier(p, y) for p, _, y in rows) / n,
        "baseline_brier": sum(_brier(b, y) for _, b, y in rows) / n,
        "log_loss": model_ll,
        "baseline_log_loss": base_ll,
        "log_loss_gain": mean_d,
        "log_loss_gain_se": se,
        "gain_is_clear": bool(se > 0 and mean_d > 2 * se),
        "accuracy": hits / n,
        "baseline_accuracy": base_hits / n,
        "reliability": reliability,
    }


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
