"""A common interface for football outcome models, so a new model (or a better version of an existing one) can be added without touching the
callers: fit on matches before a cutoff, then forecast a fixture.

Every forecast carries what is needed to judge it later: the model name and version, the training cutoff, when it was made, how fresh the
data was, how many matches were used, a plain explanation of the inputs and, for goal models, expected goals and the likeliest scorelines.
Probabilities are the model's estimate of how likely each result is. They are not a confidence score and not a measure of accuracy: how
accurate a model has been is measured by backtesting, never read off a forecast.

Implemented: independent Poisson (the baseline), Dixon-Coles (a low-score correction on top of the same fit) and Elo. A new model implements
`OutcomeModel` and is added with `register`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Protocol

from . import football_models as fm
from .football_models import M

__all__ = ["Forecast", "OutcomeModel", "PoissonModel", "DixonColesModel", "EloModel", "REGISTRY", "register", "get_model", "forecast"]


@dataclass(frozen=True)
class Forecast:
    model: str
    version: str
    home: str
    away: str
    p_home: float
    p_draw: float
    p_away: float
    training_cutoff: date                 # only matches strictly before this date were used
    data_through: date | None             # the date of the newest match that was available
    matches_used: int
    generated_at: datetime
    expected_goals: tuple[float, float] | None = None
    top_scorelines: list[dict] = field(default_factory=list)
    p_over_2_5: float | None = None
    p_btts: float | None = None
    explanation: list[dict] = field(default_factory=list)

    @property
    def probs(self) -> list[float]:
        return [self.p_home, self.p_draw, self.p_away]

    @property
    def data_age_days(self) -> int | None:
        """How old the newest available match was at the cutoff. A large number means the model is forecasting from stale data."""
        return None if self.data_through is None else (self.training_cutoff - self.data_through).days


class OutcomeModel(Protocol):
    name: str
    version: str

    def fit(self, matches: list[M], cutoff: date) -> Any:
        """Learn from matches played strictly before `cutoff`. Must not look at anything else."""

    def forecast(self, fitted: Any, home: str, away: str, cutoff: date) -> Forecast: ...


def _prior(matches: list[M], cutoff: date) -> list[M]:
    return [m for m in matches if m[0] < cutoff]


def _normalise(p: list[float]) -> list[float]:
    s = sum(p)
    return [v / s for v in p]


@dataclass
class _PoissonFit:
    fit: fm.PoissonFit
    matches: int
    newest: date | None


class PoissonModel:
    """Independent Poisson goals: each side's goals are Poisson with a rate from its attack, the opponent's defence, the league average and
    (for the home side) a home advantage, all estimated from matches before the cutoff with recent matches weighted more."""
    name = "poisson"
    version = "1.0.0"
    rho = 0.0

    def __init__(self, half_life_days: float = 730.0, prior_games: float = 2.0):
        self.half_life_days, self.prior_games = half_life_days, prior_games

    def fit(self, matches: list[M], cutoff: date) -> _PoissonFit:
        prior = _prior(matches, cutoff)
        if len(prior) < 30:
            raise ValueError(f"Fewer than 30 matches were played before {cutoff.isoformat()}, which is too few to estimate attack and defence.")
        return _PoissonFit(fm.fit_poisson(prior, cutoff, self.half_life_days, self.prior_games), len(prior), max(m[0] for m in prior))

    def _rates(self, fitted: _PoissonFit, home: str, away: str) -> tuple[float, float, dict]:
        inp = fitted.fit.inputs(home, away)
        lh = inp["mu"] * inp["attack_home"] * inp["defence_away"] * inp["home_adv"]
        la = inp["mu"] * inp["attack_away"] * inp["defence_home"]
        return lh, la, inp

    def forecast(self, fitted: _PoissonFit, home: str, away: str, cutoff: date) -> Forecast:
        lh, la, inp = self._rates(fitted, home, away)
        grid = fm.score_grid(lh, la, self.rho)
        mk = fm.grid_markets(grid)
        probs = _normalise([mk["p_home"], mk["p_draw"], mk["p_away"]])
        return Forecast(self.name, self.version, home, away, probs[0], probs[1], probs[2], cutoff, fitted.newest, fitted.matches, datetime.now(timezone.utc),
                        (lh, la), mk["top_scorelines"][:5], mk["p_over_2_5"], mk["p_btts"],
                        explain_poisson(inp, lh, la, fitted.matches, self.half_life_days, self.rho))


class DixonColesModel(PoissonModel):
    """The same fit as Poisson with a correction that lets 0-0, 1-0, 0-1 and 1-1 scorelines be more or less likely than independence implies (rho)."""
    name = "dixon_coles"
    version = "1.0.0"

    def __init__(self, rho: float = -0.05, **kw):
        super().__init__(**kw)
        self.rho = rho


@dataclass
class _EloFit:
    ratings: dict[str, float]
    matches: int
    newest: date | None


class EloModel:
    """Elo ratings updated match by match, mapped to home / draw / away probabilities by an ordered-logit curve."""
    name = "elo"
    version = "1.0.0"

    def __init__(self, params: fm.EloParams | None = None, mapping: fm.EloMap | None = None):
        self.params, self.mapping = params or fm.EloParams(), mapping or fm.EloMap()

    def fit(self, matches: list[M], cutoff: date) -> _EloFit:
        prior = _prior(matches, cutoff)
        if len(prior) < 30:
            raise ValueError(f"Fewer than 30 matches were played before {cutoff.isoformat()}, which is too few to rate clubs.")
        _, ratings = fm.elo_pass(prior, self.params)
        return _EloFit(ratings, len(prior), max(m[0] for m in prior))

    def forecast(self, fitted: _EloFit, home: str, away: str, cutoff: date) -> Forecast:
        rh, ra = fitted.ratings.get(home, fm.ELO_START), fitted.ratings.get(away, fm.ELO_START)
        p = _normalise(fm.elo_probs(rh, ra, self.params, self.mapping))
        why = [{"factor": "Home club rating", "value": round(rh, 1)}, {"factor": "Away club rating", "value": round(ra, 1)},
               {"factor": "Rating gap including home advantage", "value": round(rh + self.params.home_adv - ra, 1), "unit": "points"},
               {"factor": "Matches used", "value": fitted.matches}]
        return Forecast(self.name, self.version, home, away, p[0], p[1], p[2], cutoff, fitted.newest, fitted.matches, datetime.now(timezone.utc), explanation=why)


def explain_poisson(inp: dict, lh: float, la: float, n: int, half_life_days: float, rho: float) -> list[dict]:
    """The inputs behind a goal-model forecast, in plain terms."""
    return [
        {"factor": "League average goals per team per match", "value": round(inp["mu"], 3)},
        {"factor": "Home side attack strength (1.00 is average)", "value": round(inp["attack_home"], 3)},
        {"factor": "Home side defensive weakness (below 1.00 concedes less than average)", "value": round(inp["defence_home"], 3)},
        {"factor": "Away side attack strength (1.00 is average)", "value": round(inp["attack_away"], 3)},
        {"factor": "Away side defensive weakness (below 1.00 concedes less than average)", "value": round(inp["defence_away"], 3)},
        {"factor": "Home advantage multiplier on the home side's goals", "value": round(inp["home_adv"], 3)},
        {"factor": "Expected goals", "value": [round(lh, 2), round(la, 2)]},
        {"factor": "Matches used, weighted with a half-life of days", "value": [n, half_life_days]},
        {"factor": "Low-score correction (rho)", "value": rho},
    ]


REGISTRY: dict[str, OutcomeModel] = {}


def register(model: OutcomeModel) -> None:
    if model.name in REGISTRY:
        raise ValueError(f"A model named '{model.name}' is already registered.")
    REGISTRY[model.name] = model


def get_model(name: str) -> OutcomeModel:
    try:
        return REGISTRY[name]
    except KeyError:
        raise ValueError(f"Unknown model '{name}'. Registered: {', '.join(sorted(REGISTRY))}.") from None


def forecast(name: str, matches: list[M], home: str, away: str, cutoff: date) -> Forecast:
    """Fit the named model on matches before `cutoff` and forecast the fixture."""
    model = get_model(name)
    return model.forecast(model.fit(matches, cutoff), home, away, cutoff)


for _m in (PoissonModel(), DixonColesModel(), EloModel()):
    register(_m)
