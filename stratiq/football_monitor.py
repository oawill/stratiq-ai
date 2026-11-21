"""Model monitoring and the retraining policy for the football models. Pure; no database.

Monitoring compares how the tracked LIVE forecasts are doing now with how the same model did on the backtest test period:
  * performance drift   - recent mean log loss vs the test-period mean, as a z-score using the test period's own spread;
  * calibration drift   - recent average home-win probability vs the actual home-win rate;
  * data freshness      - matches added since the model was trained, and its age.
Statuses are "ok", "watch" and "drift". With fewer than MIN_WINDOW scored forecasts the status is "insufficient" and nothing is claimed:
a few dozen matches cannot distinguish drift from luck.

The retraining policy says when a new backtest and refit is DUE. It never changes what is live by itself: a retrain only replaces the
current settings when the new run is not worse (see `accept_challenger`).
"""
from __future__ import annotations

import math
from datetime import date

MIN_WINDOW = 30
WINDOW = 60
WATCH_Z, DRIFT_Z = 2.0, 3.0
MIN_EXCESS_LOSS = 0.03        # a drift also needs a practically meaningful loss increase, not just a statistically detectable one
NEW_MATCHES_DUE = 100         # about ten match weeks
AGE_DAYS_DUE = 90
AGE_MIN_NEW = 20              # age alone is not a reason when almost nothing has happened since
ACCEPT_TOLERANCE = 0.005      # a challenger may be this much worse on validation log loss and still be accepted (noise level)


def baseline_from(losses: list[float]) -> dict | None:
    """Mean and spread of per-match log loss on the test period."""
    n = len(losses)
    if n < 2:
        return None
    mean = sum(losses) / n
    var = sum((x - mean) ** 2 for x in losses) / (n - 1)
    return {"mean": mean, "std": math.sqrt(var), "n": n}


def _status(z: float, excess: float) -> str:
    if z >= DRIFT_Z and excess >= MIN_EXCESS_LOSS:
        return "drift"
    return "watch" if z >= WATCH_Z else "ok"


def drift_report(scored: list[dict], baseline: dict | None, window: int = WINDOW) -> dict:
    """`scored` is one model's tracked live forecasts that now have results, oldest first, each {"log_loss", "p_home", "home_win"}."""
    recent = scored[-window:]
    n = len(recent)
    out: dict = {"window": n, "needed": MIN_WINDOW, "scored_total": len(scored)}
    if baseline is None:
        return {**out, "status": "insufficient", "note": "No backtest baseline yet: run a backtest first."}
    if n < MIN_WINDOW:
        return {**out, "status": "insufficient", "note": f"Only {n} tracked forecasts have results; at least {MIN_WINDOW} are needed before drift can be judged."}
    mean = sum(r["log_loss"] for r in recent) / n
    se = max(baseline["std"], 1e-6) / math.sqrt(n)
    z = (mean - baseline["mean"]) / se
    perf = {"recent_log_loss": mean, "baseline_log_loss": baseline["mean"], "excess": mean - baseline["mean"], "z": z, "status": _status(z, mean - baseline["mean"])}
    p_bar = sum(r["p_home"] for r in recent) / n
    rate = sum(1 for r in recent if r["home_win"]) / n
    se_c = math.sqrt(max(p_bar * (1 - p_bar), 1e-6) / n)
    zc = abs(rate - p_bar) / se_c
    cal = {"mean_predicted_home_win": p_bar, "actual_home_win_rate": rate, "z": zc, "status": "drift" if zc >= DRIFT_Z else "watch" if zc >= WATCH_Z else "ok"}
    order = {"ok": 0, "watch": 1, "drift": 2}
    status = max((perf["status"], cal["status"]), key=lambda s: order[s])
    return {**out, "status": status, "performance": perf, "calibration": cal,
            "note": "Drift means the recent forecasts are doing worse than the backtest said they would, by more than chance would explain. It is a prompt to retrain and to look, not proof the model is broken."}


def retrain_decision(*, has_run: bool, matches_since_run: int, days_since_run: int | None, drift_status: str) -> dict:
    reasons = []
    if not has_run:
        reasons.append("No backtest has been run on this history yet.")
    else:
        if drift_status == "drift":
            reasons.append("Live forecasts are doing materially worse than the backtest predicted.")
        if matches_since_run >= NEW_MATCHES_DUE:
            reasons.append(f"{matches_since_run} matches have been added since the models were trained (threshold {NEW_MATCHES_DUE}).")
        if days_since_run is not None and days_since_run >= AGE_DAYS_DUE and matches_since_run >= AGE_MIN_NEW:
            reasons.append(f"The models are {days_since_run} days old and {matches_since_run} matches have been added since (thresholds {AGE_DAYS_DUE} days and {AGE_MIN_NEW} matches).")
    return {"retrain": bool(reasons), "reasons": reasons,
            "policy": {"new_matches": NEW_MATCHES_DUE, "age_days": AGE_DAYS_DUE, "age_needs_new_matches": AGE_MIN_NEW, "drift": "log-loss z >= 3 and at least 0.03 worse than the backtest"}}


def accept_challenger(incumbent_val_ll: float | None, challenger_val_ll: float | None) -> dict:
    """A freshly retrained run replaces the current one unless it is clearly worse on ITS OWN validation period than the incumbent was on its.
    The two validation periods differ (the newer run validates on later matches), so this is a sanity guard against a broken refit, not a
    like-for-like contest; the full results of both runs are kept for review."""
    if challenger_val_ll is None:
        return {"accept": False, "reason": "The new run has no validation result."}
    if incumbent_val_ll is None:
        return {"accept": True, "reason": "There was no earlier run to compare with."}
    ok = challenger_val_ll <= incumbent_val_ll + ACCEPT_TOLERANCE
    return {"accept": ok, "reason": ("Validation log loss " + (f"{challenger_val_ll:.4f} is within {ACCEPT_TOLERANCE} of or better than the previous {incumbent_val_ll:.4f}." if ok
                                                                 else f"{challenger_val_ll:.4f} is worse than the previous {incumbent_val_ll:.4f} by more than {ACCEPT_TOLERANCE}; the previous run stays live."))}


def days_between(a: date, b: date) -> int:
    return (b - a).days
