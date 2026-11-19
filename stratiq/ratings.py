"""Maher-style attack/defence rating fit by iterative Poisson maximum likelihood.

    home_xg = mu * attack[home] * defence[away] * home_adv
    away_xg = mu * attack[away] * defence[home]

`defence` is a concession multiplier (higher = concedes more). A weak prior of
`prior_games` pseudo-matches pulls every rating towards 1 so small samples stay sane.
Deterministic: same inputs always give the same ratings.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Match:
    home: str
    away: str
    home_goals: int
    away_goals: int


@dataclass
class Ratings:
    mu: float
    home_adv: float
    attack: dict[str, float]
    defence: dict[str, float]
    n_matches: int
    iterations: int
    converged: bool
    team_matches: dict[str, int] = field(default_factory=dict)

    def expected_goals(self, home: str, away: str) -> tuple[float, float]:
        ah, dh = self.attack.get(home, 1.0), self.defence.get(home, 1.0)
        aa, da = self.attack.get(away, 1.0), self.defence.get(away, 1.0)
        return self.mu * ah * da * self.home_adv, self.mu * aa * dh


def fit_ratings(
    matches: list[Match],
    teams: list[str],
    prior_games: float = 2.0,
    max_iter: int = 500,
    tol: float = 1e-10,
) -> Ratings:
    n = len(matches)
    counts = {t: 0 for t in teams}
    for m in matches:
        counts[m.home] = counts.get(m.home, 0) + 1
        counts[m.away] = counts.get(m.away, 0) + 1
    if n == 0:
        return Ratings(1.3, 1.0, {t: 1.0 for t in teams}, {t: 1.0 for t in teams}, 0, 0, True, counts)

    all_teams = sorted(set(teams) | set(counts))
    total_goals = sum(m.home_goals + m.away_goals for m in matches)
    mu = max(total_goals / (2 * n), 0.05)
    gamma = 1.0
    att = {t: 1.0 for t in all_teams}
    dfn = {t: 1.0 for t in all_teams}
    home_goals_total = sum(m.home_goals for m in matches)

    converged = False
    it = 0
    for it in range(1, max_iter + 1):
        prev = (dict(att), dict(dfn), gamma)
        # attack update
        g_for = {t: 0.0 for t in all_teams}
        d_for = {t: 0.0 for t in all_teams}
        for m in matches:
            g_for[m.home] += m.home_goals
            d_for[m.home] += mu * dfn[m.away] * gamma
            g_for[m.away] += m.away_goals
            d_for[m.away] += mu * dfn[m.home]
        att = {t: (g_for[t] + prior_games * mu) / (d_for[t] + prior_games * mu) for t in all_teams}
        # defence update
        g_ag = {t: 0.0 for t in all_teams}
        d_ag = {t: 0.0 for t in all_teams}
        for m in matches:
            g_ag[m.away] += m.home_goals
            d_ag[m.away] += mu * att[m.home] * gamma
            g_ag[m.home] += m.away_goals
            d_ag[m.home] += mu * att[m.away]
        dfn = {t: (g_ag[t] + prior_games * mu) / (d_ag[t] + prior_games * mu) for t in all_teams}
        # home advantage update
        denom = sum(mu * att[m.home] * dfn[m.away] for m in matches)
        gamma = home_goals_total / denom if denom > 0 else 1.0
        # fix scale: mean attack = mean defence = 1, absorbing into mu
        ca = sum(att.values()) / len(att)
        att = {t: v / ca for t, v in att.items()}
        mu *= ca
        cd = sum(dfn.values()) / len(dfn)
        dfn = {t: v / cd for t, v in dfn.items()}
        mu *= cd

        delta = max(
            max(abs(att[t] - prev[0][t]) for t in all_teams),
            max(abs(dfn[t] - prev[1][t]) for t in all_teams),
            abs(gamma - prev[2]),
        )
        if delta < tol:
            converged = True
            break

    return Ratings(mu, gamma, att, dfn, n, it, converged, counts)
