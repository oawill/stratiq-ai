"""Sports prediction model: Poisson goals with Maher-style ratings. Deterministic."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from .poisson import scoreline_model
from .ratings import Match, fit_ratings

MODEL_NAME = "poisson-maher"
MODEL_VERSION = "0.1.0"
MODEL_DESCRIPTION = (
    "Independent Poisson goal model. Team attack and defence multipliers and a league-wide "
    "home-advantage factor are fit by iterative maximum likelihood on finished matches "
    "before the feature cutoff."
)
ASSUMPTIONS = [
    "Goals for each team are independent Poisson variables.",
    "Expected goals = league mean x attack x opponent defence x home advantage (home side only).",
    "Team strength is constant over the data window (no form, injuries, lineups, or time decay).",
    "A weak prior of 2 pseudo-matches shrinks every rating toward the league average.",
    "Scoreline probabilities are computed on a 0-10 goal grid and renormalised; the removed tail mass is recorded.",
    "Only matches with kickoff strictly before the feature cutoff are used (no look-ahead).",
]
LIMITATIONS = [
    "Trained on a FICTIONAL development dataset until a licensed historical data source is configured.",
    "Ignores correlation between home and away goals (no Dixon-Coles adjustment), so low scores are slightly mis-weighted.",
    "No player-level, tactical, schedule, or market information is used.",
    "Probabilities express model uncertainty under these assumptions, not certainty about the result.",
]


@dataclass(frozen=True)
class HistMatch:
    home: str
    away: str
    home_goals: int
    away_goals: int
    kickoff: datetime


def _r(x: float, d: int = 6) -> float:
    return round(float(x), d)


def predict(
    history: list[HistMatch],
    league_teams: list[str],
    home: str,
    away: str,
    cutoff: datetime,
    dataset: str,
) -> dict:
    """Return {inputs, outputs, assumptions}. Uses only matches with kickoff < cutoff."""
    if home == away:
        raise ValueError("home and away teams must differ")
    used = sorted(
        (m for m in history if m.kickoff < cutoff),
        key=lambda m: (m.kickoff, m.home, m.away),
    )
    ratings = fit_ratings([Match(m.home, m.away, m.home_goals, m.away_goals) for m in used], league_teams)
    hx, ax = ratings.expected_goals(home, away)
    sm = scoreline_model(hx, ax)

    digest = hashlib.sha256(
        json.dumps([[m.home, m.away, m.home_goals, m.away_goals, m.kickoff.isoformat()] for m in used]).encode()
    ).hexdigest()
    inputs = {
        "home_team": home,
        "away_team": away,
        "feature_cutoff": cutoff.isoformat(),
        "dataset": dataset,
        "matches_used": len(used),
        "matches_used_digest": digest,
        "home_team_matches": ratings.team_matches.get(home, 0),
        "away_team_matches": ratings.team_matches.get(away, 0),
        "league_mean_goals": _r(ratings.mu),
        "home_advantage": _r(ratings.home_adv),
        "home_attack": _r(ratings.attack.get(home, 1.0)),
        "home_defence": _r(ratings.defence.get(home, 1.0)),
        "away_attack": _r(ratings.attack.get(away, 1.0)),
        "away_defence": _r(ratings.defence.get(away, 1.0)),
        "fit_iterations": ratings.iterations,
        "fit_converged": ratings.converged,
    }
    outputs = {
        "home_xg": _r(hx),
        "away_xg": _r(ax),
        "p_home": _r(sm.p_home),
        "p_draw": _r(sm.p_draw),
        "p_away": _r(sm.p_away),
        "p_btts": _r(sm.p_btts),
        "p_over_2_5": _r(sm.p_over(2.5)),
        "top_scorelines": [{**s, "p": _r(s["p"])} for s in sm.top_scorelines(6)],
        "scoreline_grid": [[_r(p) for p in row[:7]] for row in sm.grid[:7]],
        "grid_tail_mass_removed": _r(sm.tail_mass, 9),
    }
    return {"inputs": inputs, "outputs": outputs, "assumptions": ASSUMPTIONS}


def input_hash(inputs: dict) -> str:
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
