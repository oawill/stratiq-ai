"""Independent-Poisson scoreline model. Pure math: no I/O, no randomness, no AI."""
from __future__ import annotations

import math
from dataclasses import dataclass

MAX_GOALS = 10


def poisson_pmf(k: int, lam: float) -> float:
    if k < 0:
        return 0.0
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1))


@dataclass(frozen=True)
class ScorelineModel:
    home_xg: float
    away_xg: float
    grid: list[list[float]]  # grid[h][a], renormalised to sum to 1
    tail_mass: float  # probability mass beyond MAX_GOALS removed before renormalising

    @property
    def p_home(self) -> float:
        return sum(p for h, row in enumerate(self.grid) for a, p in enumerate(row) if h > a)

    @property
    def p_draw(self) -> float:
        return sum(self.grid[i][i] for i in range(len(self.grid)))

    @property
    def p_away(self) -> float:
        return sum(p for h, row in enumerate(self.grid) for a, p in enumerate(row) if h < a)

    @property
    def p_btts(self) -> float:
        """Both teams to score."""
        return sum(p for h, row in enumerate(self.grid) for a, p in enumerate(row) if h > 0 and a > 0)

    def p_over(self, line: float) -> float:
        return sum(p for h, row in enumerate(self.grid) for a, p in enumerate(row) if h + a > line)

    def top_scorelines(self, n: int = 5) -> list[dict]:
        cells = [(h, a, p) for h, row in enumerate(self.grid) for a, p in enumerate(row)]
        cells.sort(key=lambda c: -c[2])
        return [{"home": h, "away": a, "p": p} for h, a, p in cells[:n]]


def scoreline_model(home_xg: float, away_xg: float, max_goals: int = MAX_GOALS) -> ScorelineModel:
    if home_xg < 0 or away_xg < 0 or not math.isfinite(home_xg) or not math.isfinite(away_xg):
        raise ValueError("expected goals must be finite and non-negative")
    raw = [
        [poisson_pmf(h, home_xg) * poisson_pmf(a, away_xg) for a in range(max_goals + 1)]
        for h in range(max_goals + 1)
    ]
    covered = sum(sum(r) for r in raw)
    grid = [[p / covered for p in r] for r in raw]
    return ScorelineModel(home_xg, away_xg, grid, 1.0 - covered)
