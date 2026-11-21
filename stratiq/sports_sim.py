"""Sports scenario simulator: what a football fixture's Poisson-family forecast would be if some assumptions were different.

Pure and deterministic: no database, no randomness (so there is no seed; the same inputs always give the same outputs).

THE MODEL (documented, version SIM_VERSION)
  Baseline, calibrated from data (matches before the cutoff only):
      lambda_home = mu * attack_home * defence_away * home_advantage
      lambda_away = mu * attack_away * defence_home
  where mu is the league average goals per team, attack is a club's scoring strength (1.00 is average), defence is a club's defensive
  weakness (above 1.00 concedes more) and home_advantage is a multiplier on the home side's goals. They are fitted by time-weighted maximum
  likelihood. Scorelines are Poisson(lambda_home) x Poisson(lambda_away), with the Dixon-Coles low-score correction rho when a tuned value is
  available (rho = 0 is plain independent Poisson). The scoreline grid is renormalised to 1, so home + draw + away = 100%.

  Scenario, speculative assumptions chosen by the user, applied multiplicatively to the calibrated numbers:
      attack_home     *= home_attack_multiplier * (1 - home_missing_attack_loss)        (and the same for the away side)
      defence_away    *= away_defence_multiplier * (1 + away_missing_defence_loss)      (and the same for the home side)
      home_advantage  *= home_advantage_multiplier
      both lambdas    *= tempo_multiplier
  Expected goals are capped to [0.05, 6]. Tempo scales both sides' expected goals to represent a faster or slower game.

WHAT IS AND IS NOT VALIDATED
  The baseline is estimated from results and can be backtested (see Football intelligence, Model performance). The adjustments are NOT
  validated: no backtest has tested whether moving a slider predicts anything, and the model was not trained on lineups, injuries or tempo.
  A scenario is "what the model would say if this assumption were true", never a forecast.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone

from . import football_backtest as fb
from . import football_intel as fi
from . import football_models as fm
from .football_models import M

SIM_VERSION = "1.0.0"
LAMBDA_MIN, LAMBDA_MAX = 0.05, 6.0
GRID_SHOWN = 6          # the score table shows 0..6 goals each; the remaining probability is reported as a tail
MAX_SCENARIOS = 3

# key: (lowest, highest, neutral, label, plain explanation)
ADJUSTMENTS: dict[str, tuple[float, float, float, str, str]] = {
    "home_attack_multiplier": (0.5, 1.5, 1.0, "Home attack", "Multiplies the home side's scoring strength."),
    "away_attack_multiplier": (0.5, 1.5, 1.0, "Away attack", "Multiplies the away side's scoring strength."),
    "home_defence_multiplier": (0.5, 1.5, 1.0, "Home defensive weakness", "Above 1 makes the home side concede more; below 1 makes it concede less."),
    "away_defence_multiplier": (0.5, 1.5, 1.0, "Away defensive weakness", "Above 1 makes the away side concede more; below 1 makes it concede less."),
    "home_advantage_multiplier": (0.5, 1.5, 1.0, "Home advantage", "Multiplies the home advantage the model estimated from the data."),
    "tempo_multiplier": (0.8, 1.2, 1.0, "Tempo", "Scales both sides' expected goals: above 1 is a faster, more open game."),
    "home_missing_attack_loss": (0.0, 0.5, 0.0, "Home attack lost to absences", "The share of the home side's attack you assume is missing. Your assumption, not an estimate from data."),
    "away_missing_attack_loss": (0.0, 0.5, 0.0, "Away attack lost to absences", "The share of the away side's attack you assume is missing. Your assumption, not an estimate from data."),
    "home_missing_defence_loss": (0.0, 0.5, 0.0, "Home defence lost to absences", "How much more the home side concedes because of assumed absences. Your assumption."),
    "away_missing_defence_loss": (0.0, 0.5, 0.0, "Away defence lost to absences", "How much more the away side concedes because of assumed absences. Your assumption."),
}

DOCUMENTATION = (
    "Baseline: expected goals = league average x the club's attack x the opponent's defensive weakness (x home advantage for the home side), "
    "estimated from matches before the cutoff. Scorelines follow independent Poisson distributions with an optional Dixon-Coles low-score correction, "
    "renormalised so home win, draw and away win add to 100%. Scenario: your assumptions multiply those calibrated numbers; tempo scales both sides' "
    "expected goals. Only the baseline is estimated from data and can be backtested; the adjustments are your assumptions and are not statistically validated."
)


def percent_split(probs: list[float], decimals: int = 1) -> list[float]:
    """Probabilities as percentages rounded to `decimals`, adjusted by the largest-remainder method so they add to exactly 100."""
    unit = 10 ** decimals
    total = 100 * unit
    s = sum(probs)
    if s <= 0:
        raise ValueError("Probabilities must add to a positive number.")
    raw = [p / s * total for p in probs]
    base = [math.floor(v) for v in raw]
    order = sorted(range(len(raw)), key=lambda i: raw[i] - base[i], reverse=True)
    for i in order[: total - sum(base)]:
        base[i] += 1
    return [b / unit for b in base]


def validate_adjustments(adj: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for k, v in (adj or {}).items():
        if k not in ADJUSTMENTS:
            raise ValueError(f"'{k}' is not an adjustment this model uses. Supported: {', '.join(sorted(ADJUSTMENTS))}.")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f"'{k}' must be a finite number.")
        lo, hi = ADJUSTMENTS[k][0], ADJUSTMENTS[k][1]
        if not lo <= v <= hi:
            raise ValueError(f"'{ADJUSTMENTS[k][3]}' must be between {lo:g} and {hi:g}.")
        out[k] = float(v)
    return out


def expected_goals(inp: dict, adj: dict[str, float]) -> tuple[float, float]:
    shaped = fi.apply_adjustments(inp, {k: v for k, v in adj.items() if k != "tempo_multiplier"})
    tempo = adj.get("tempo_multiplier", 1.0)
    lh = shaped["mu"] * shaped["attack_home"] * shaped["defence_away"] * shaped["home_adv"] * tempo
    la = shaped["mu"] * shaped["attack_away"] * shaped["defence_home"] * tempo
    return min(LAMBDA_MAX, max(LAMBDA_MIN, lh)), min(LAMBDA_MAX, max(LAMBDA_MIN, la))


def evaluate(inp: dict, rho: float, adj: dict[str, float]) -> dict:
    """One scenario: expected goals, normalised outcome probabilities, markets and the score distribution."""
    lh, la = expected_goals(inp, adj)
    grid = fm.score_grid(lh, la, rho)
    mk = fm.grid_markets(grid)
    probs = [mk["p_home"], mk["p_draw"], mk["p_away"]]
    s = sum(probs)
    probs = [p / s for p in probs]
    n = GRID_SHOWN
    shown = [[grid[h][a] for a in range(n + 1)] for h in range(n + 1)]
    return {"expected_goals": [lh, la], "probs": probs, "percent": percent_split(probs), "p_over_2_5": mk["p_over_2_5"], "p_btts": mk["p_btts"],
            "top_scorelines": [{"home": t["home"], "away": t["away"], "p": t["p"]} for t in mk["top_scorelines"][:5]],
            "score_grid": shown, "grid_tail": 1.0 - sum(sum(r) for r in shown), "grid_goals": n}


def delta(base: dict, other: dict) -> dict:
    return {"p_home": (other["probs"][0] - base["probs"][0]) * 100, "p_draw": (other["probs"][1] - base["probs"][1]) * 100, "p_away": (other["probs"][2] - base["probs"][2]) * 100,
            "expected_goals_home": other["expected_goals"][0] - base["expected_goals"][0], "expected_goals_away": other["expected_goals"][1] - base["expected_goals"][1],
            "p_over_2_5": (other["p_over_2_5"] - base["p_over_2_5"]) * 100, "p_btts": (other["p_btts"] - base["p_btts"]) * 100, "unit": "percentage points (goals for expected goals)"}


def speculative_parameters(adj: dict[str, float]) -> list[dict]:
    return [{"key": k, "label": ADJUSTMENTS[k][3], "value": adj.get(k, ADJUSTMENTS[k][2]), "neutral": ADJUSTMENTS[k][2], "changed": k in adj and adj[k] != ADJUSTMENTS[k][2],
             "range": [ADJUSTMENTS[k][0], ADJUSTMENTS[k][1]], "meaning": ADJUSTMENTS[k][4], "status": "speculative assumption, not validated"} for k in ADJUSTMENTS]


def run(ms: list[M], home: str, away: str, cutoff: date, settings: dict, scenarios: list[dict], scheduled: bool, fixture_date: date | None = None,
        now: datetime | None = None) -> dict:
    """The baseline for a fixture plus up to three named scenarios. `scenarios` is [{"name": str, "adjustments": {...}}]."""
    if home == away:
        raise ValueError("Choose two different clubs.")
    if len(scenarios) > MAX_SCENARIOS:
        raise ValueError(f"At most {MAX_SCENARIOS} alternative scenarios can be compared with the baseline.")
    prior = [m for m in ms if m[0] < cutoff]
    if len(prior) < 30:
        raise ValueError("Fewer than 30 matches came before the cutoff, which is too few to estimate attack and defence.")
    known = {t for _, h, a, *_ in prior for t in (h, a)}
    for t in (home, away):
        if t not in known:
            raise ValueError(f"'{t}' is not a club in the imported matches before the cutoff.")
    p = settings["poisson"]
    fit = fm.fit_poisson(prior, cutoff, p["half_life_days"], p["prior_games"])
    inp = fit.inputs(home, away)
    rho = float(settings.get("rho", 0.0))
    base = evaluate(inp, rho, {})
    results = []
    names = set()
    for i, sc in enumerate(scenarios):
        name = (sc.get("name") or f"Scenario {i + 1}").strip()[:60]
        if name in names or name.lower() == "baseline":
            raise ValueError(f"Scenario names must be unique and cannot be 'Baseline' ('{name}').")
        names.add(name)
        adj = validate_adjustments(sc.get("adjustments") or {})
        ev = evaluate(inp, rho, adj)
        results.append({"name": name, "adjustments": adj, "speculative_parameters": speculative_parameters(adj), **ev, "delta_vs_baseline": delta(base, ev),
                        "changed": sorted(k for k in adj if adj[k] != ADJUSTMENTS[k][2])})
    return {
        "matchup": {"home": home, "away": away, "scheduled": scheduled, "fixture_date": fixture_date.isoformat() if fixture_date else None,
                    "label": "An imported upcoming fixture." if scheduled else "A hypothetical matchup: this pairing is not a scheduled match."},
        "baseline": {"name": "Baseline", **base, "status": "Calibrated from your imported matches. Not changed by any assumption."},
        "scenarios": results,
        "calibrated_parameters": [
            {"name": "League average goals per team", "value": inp["mu"]}, {"name": "Home advantage multiplier", "value": inp["home_adv"]},
            {"name": f"{home} attack strength", "value": inp["attack_home"]}, {"name": f"{home} defensive weakness", "value": inp["defence_home"]},
            {"name": f"{away} attack strength", "value": inp["attack_away"]}, {"name": f"{away} defensive weakness", "value": inp["defence_away"]},
            {"name": "Low-score correction (rho)", "value": rho}, {"name": "Weighting half-life (days)", "value": p["half_life_days"]}, {"name": "Prior games", "value": p["prior_games"]},
            {"name": "Matches used", "value": len(prior)}],
        "provenance": {"model": "sports_sim", "model_version": SIM_VERSION, "base_model": "Dixon-Coles" if rho else "Poisson", "settings_tuned": bool(settings.get("tuned")),
                       "settings_from_backtest": settings.get("run_id"), "data_sha256": fb.data_sha(sorted(prior, key=lambda m: (m[0], m[1], m[2]))), "training_cutoff": cutoff.isoformat(),
                       "data_through": max(m[0] for m in prior).isoformat(), "matches_used": len(prior), "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
                       "deterministic": True, "random_seed": None},
        "documentation": DOCUMENTATION,
        "validation_status": ("The baseline is estimated from results" + (" with settings tuned on a validation period of a backtest." if settings.get("tuned") else " with default settings: no backtest has been run, so nothing is tuned.")
                              + " The adjustments are your assumptions and are not statistically validated: no backtest has tested whether moving a slider predicts anything."),
        "label": "HYPOTHETICAL scenarios compared with a model baseline. Not forecasts, not betting or financial advice.",
    }
