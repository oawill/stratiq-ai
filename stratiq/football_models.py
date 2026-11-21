"""Football forecasting models: Elo, time-weighted Poisson, Dixon-Coles, and a frequency baseline. Pure Python, deterministic.

Every function that produces a forecast for a fixture on a date uses only matches played strictly before that date. Anything a
forecast depends on is returned in `inputs`, so the same probabilities can be recomputed later from the stored inputs alone.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from datetime import date

from .football_history import season_label
from .poisson import poisson_pmf

M = tuple[date, str, str, int, int]      # (date, home, away, home_goals, away_goals), in date order
MAX_GOALS = 10
ELO_START = 1500.0


def outcome(hg: int, ag: int) -> int:
    return 0 if hg > ag else 1 if hg == ag else 2     # home, draw, away


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x)) if x >= 0 else math.exp(x) / (1.0 + math.exp(x))


def golden(f, lo: float, hi: float, iters: int = 24) -> float:
    """Minimise a one-dimensional function on [lo, hi]."""
    g = (math.sqrt(5) - 1) / 2
    a, b = lo, hi
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(iters):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = f(d)
    return (a + b) / 2


# ------------------------------------------------------------------ Model A: Elo
@dataclass(frozen=True)
class EloParams:
    k: float = 20.0
    home_adv: float = 65.0     # points added to the home side's rating when updating; the probability mapping then learns any remaining offset
    regress: float = 0.25      # share of each rating pulled back to the average at the start of a season (squads change)
    newcomer: float = 0.0      # rating offset from the average for a club never seen before (promoted clubs start below it when this is negative)


def elo_pass(matches: list[M], p: EloParams) -> tuple[list[tuple[float, float]], dict[str, float]]:
    """Pre-match (home, away) ratings for every match, and the ratings after the last one. Matches on the same date are all
    rated from the ratings at the start of that date, so none uses another's result."""
    rating: dict[str, float] = {}
    out: list[tuple[float, float]] = []
    i, n = 0, len(matches)
    prev_season: str | None = None
    started = False        # clubs first seen after the opening day are newcomers; everyone on the opening day starts level

    def start_of(team: str) -> float:
        if not started or not rating:
            return ELO_START
        return sum(rating.values()) / len(rating) + p.newcomer

    while i < n:
        d = matches[i][0]
        j = i
        while j < n and matches[j][0] == d:
            j += 1
        s = season_label(d)
        if prev_season is not None and s != prev_season and rating:
            mean = sum(rating.values()) / len(rating)
            for t in rating:
                rating[t] = mean + (1 - p.regress) * (rating[t] - mean)
        prev_season = s
        day = matches[i:j]
        for _, h, a, *_ in day:
            for t in (h, a):
                if t not in rating:
                    rating[t] = start_of(t)
        deltas: dict[str, float] = {}
        for _, h, a, hg, ag in day:
            rh, ra = rating[h], rating[a]
            out.append((rh, ra))
            exp_h = 1.0 / (1.0 + 10 ** (-((rh + p.home_adv) - ra) / 400.0))
            actual = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
            gd = abs(hg - ag)
            mult = 1.0 if gd <= 1 else 1.5 if gd == 2 else (11 + gd) / 8
            delta = p.k * mult * (actual - exp_h)
            deltas[h] = deltas.get(h, 0.0) + delta
            deltas[a] = deltas.get(a, 0.0) - delta
        for t, dv in deltas.items():
            rating[t] += dv
        started = True
        i = j
    return out, rating


@dataclass(frozen=True)
class EloMap:
    """Turns a rating gap into home/draw/away probabilities (an ordered logit)."""
    scale: float = 174.0       # rating points per logit unit (174 is the standard Elo scale)
    draw: float = 0.55         # width of the draw band
    offset: float = 0.0        # constant shift in favour of the home side


def elo_probs(r_home: float, r_away: float, p: EloParams, m: EloMap) -> list[float]:
    x = ((r_home + p.home_adv) - r_away) / m.scale + m.offset
    ph, pa = sigmoid(x - m.draw), sigmoid(-x - m.draw)
    return [ph, max(1.0 - ph - pa, 0.0), pa]


def fit_elo_map(gaps: list[float], outcomes: list[int]) -> EloMap:
    """Maximum-likelihood scale, draw width and offset from pre-match rating gaps and what happened."""
    def nll(s: float, c: float, o: float) -> float:
        tot = 0.0
        for g, y in zip(gaps, outcomes):
            x = g / s + o
            ph, pa = sigmoid(x - c), sigmoid(-x - c)
            pr = (ph, max(1.0 - ph - pa, 1e-12), pa)[y]
            tot -= math.log(max(pr, 1e-12))
        return tot / max(len(gaps), 1)
    s, c, o = 174.0, 0.55, 0.0
    for _ in range(3):
        s = golden(lambda v: nll(v, c, o), 80.0, 500.0)
        c = golden(lambda v: nll(s, v, o), 0.05, 2.0)
        o = golden(lambda v: nll(s, c, v), -1.0, 1.0)
    return EloMap(s, c, o)


# ------------------------------------------------------------------ Model B: time-weighted Poisson
@dataclass
class PoissonFit:
    mu: float
    home_adv: float
    attack: dict[str, float]
    defence: dict[str, float]
    matches: int
    iterations: int
    converged: bool
    cutoff: date | None = None

    def rates(self, home: str, away: str) -> tuple[float, float]:
        return (self.mu * self.attack.get(home, 1.0) * self.defence.get(away, 1.0) * self.home_adv,
                self.mu * self.attack.get(away, 1.0) * self.defence.get(home, 1.0))

    def inputs(self, home: str, away: str) -> dict:
        return {"mu": self.mu, "home_adv": self.home_adv, "attack_home": self.attack.get(home, 1.0), "defence_home": self.defence.get(home, 1.0),
                "attack_away": self.attack.get(away, 1.0), "defence_away": self.defence.get(away, 1.0)}


def fit_poisson(matches: list[M], cutoff: date, half_life_days: float = 730.0, prior_games: float = 2.0, init: PoissonFit | None = None,
                max_iter: int = 150, tol: float = 1e-7) -> PoissonFit:
    """Attack/defence multipliers and a home-advantage factor by weighted maximum likelihood. Each match counts for
    0.5 ** (age / half_life): recent matches weigh more. Only matches dated before `cutoff` are used."""
    used = [m for m in matches if m[0] < cutoff]
    n = len(used)
    if n == 0:
        return PoissonFit(1.3, 1.0, {}, {}, 0, 0, True, cutoff)
    w = [0.5 ** (((cutoff - m[0]).days) / half_life_days) for m in used]
    sw = sum(w)
    teams = sorted({t for m in used for t in (m[1], m[2])})
    mu = max(sum(wi * (m[3] + m[4]) for wi, m in zip(w, used)) / (2 * sw), 0.05)
    gamma = 1.0
    att = {t: 1.0 for t in teams}
    dfn = {t: 1.0 for t in teams}
    if init is not None:
        mu, gamma = init.mu, init.home_adv
        att = {t: init.attack.get(t, 1.0) for t in teams}
        dfn = {t: init.defence.get(t, 1.0) for t in teams}
    home_goals = sum(wi * m[3] for wi, m in zip(w, used))
    converged, it = False, 0
    for it in range(1, max_iter + 1):
        pa, pd, pg = att, dfn, gamma
        g_for = dict.fromkeys(teams, 0.0)
        d_for = dict.fromkeys(teams, 0.0)
        for wi, (_, h, a, hg, ag) in zip(w, used):
            g_for[h] += wi * hg
            d_for[h] += wi * mu * dfn[a] * gamma
            g_for[a] += wi * ag
            d_for[a] += wi * mu * dfn[h]
        att = {t: (g_for[t] + prior_games * mu) / (d_for[t] + prior_games * mu) for t in teams}
        g_ag = dict.fromkeys(teams, 0.0)
        d_ag = dict.fromkeys(teams, 0.0)
        for wi, (_, h, a, hg, ag) in zip(w, used):
            g_ag[a] += wi * hg
            d_ag[a] += wi * mu * att[h] * gamma
            g_ag[h] += wi * ag
            d_ag[h] += wi * mu * att[a]
        dfn = {t: (g_ag[t] + prior_games * mu) / (d_ag[t] + prior_games * mu) for t in teams}
        denom = sum(wi * mu * att[h] * dfn[a] for wi, (_, h, a, *_r) in zip(w, used))
        gamma = home_goals / denom if denom > 0 else 1.0
        ca = sum(att.values()) / len(att)
        att = {t: v / ca for t, v in att.items()}
        mu *= ca
        cd = sum(dfn.values()) / len(dfn)
        dfn = {t: v / cd for t, v in dfn.items()}
        mu *= cd
        delta = max(max(abs(att[t] - pa[t]) for t in teams), max(abs(dfn[t] - pd[t]) for t in teams), abs(gamma - pg))
        if delta < tol:
            converged = True
            break
    return PoissonFit(mu, gamma, att, dfn, n, it, converged, cutoff)


# ------------------------------------------------------------------ Model C: Dixon-Coles
def tau(h: int, a: int, lh: float, la: float, rho: float) -> float:
    """Dixon-Coles correction for the four lowest scorelines; 1 everywhere else."""
    if h == 0 and a == 0:
        return max(1.0 - lh * la * rho, 1e-9)
    if h == 0 and a == 1:
        return max(1.0 + lh * rho, 1e-9)
    if h == 1 and a == 0:
        return max(1.0 + la * rho, 1e-9)
    if h == 1 and a == 1:
        return max(1.0 - rho, 1e-9)
    return 1.0


def score_grid(lh: float, la: float, rho: float = 0.0, max_goals: int = MAX_GOALS) -> list[list[float]]:
    """Scoreline probabilities (renormalised to 1). rho = 0 is the plain independent Poisson."""
    ph = [poisson_pmf(k, lh) for k in range(max_goals + 1)]
    pa = [poisson_pmf(k, la) for k in range(max_goals + 1)]
    raw = [[ph[h] * pa[a] * (tau(h, a, lh, la, rho) if rho else 1.0) for a in range(max_goals + 1)] for h in range(max_goals + 1)]
    z = sum(sum(r) for r in raw)
    return [[v / z for v in r] for r in raw]


def fit_rho(rows: list[tuple[float, float, int, int]]) -> float:
    """Dixon-Coles low-score parameter by maximum likelihood, given predicted goal rates and actual scores. Rates are held fixed
    (a two-stage fit), which keeps the rates comparable with the plain Poisson model."""
    def nll(rho: float) -> float:
        tot = 0.0
        for lh, la, h, a in rows:
            z = 1.0 + poisson_pmf(0, lh) * poisson_pmf(0, la) * (tau(0, 0, lh, la, rho) - 1) + poisson_pmf(0, lh) * poisson_pmf(1, la) * (tau(0, 1, lh, la, rho) - 1) \
                + poisson_pmf(1, lh) * poisson_pmf(0, la) * (tau(1, 0, lh, la, rho) - 1) + poisson_pmf(1, lh) * poisson_pmf(1, la) * (tau(1, 1, lh, la, rho) - 1)
            p = poisson_pmf(h, lh) * poisson_pmf(a, la) * tau(h, a, lh, la, rho) / z
            tot -= math.log(max(p, 1e-300))
        return tot / max(len(rows), 1)
    return golden(nll, -0.25, 0.25, 30) if rows else 0.0


def grid_markets(grid: list[list[float]]) -> dict:
    n = len(grid)
    ph = sum(grid[h][a] for h in range(n) for a in range(n) if h > a)
    pd = sum(grid[i][i] for i in range(n))
    over = sum(grid[h][a] for h in range(n) for a in range(n) if h + a > 2)
    btts = sum(grid[h][a] for h in range(1, n) for a in range(1, n))
    cells = sorted(((grid[h][a], h, a) for h in range(n) for a in range(n)), reverse=True)[:6]
    return {"p_home": ph, "p_draw": pd, "p_away": 1.0 - ph - pd, "p_over_2_5": over, "p_btts": btts,
            "top_scorelines": [{"home": h, "away": a, "p": p} for p, h, a in cells]}


def poisson_drivers(inp: dict) -> list[dict]:
    """The exact multiplicative pieces of each side's expected goals, as effects on log expected goals."""
    ln = math.log
    return [
        {"factor": "League scoring level", "effect_home": ln(inp["mu"]), "effect_away": ln(inp["mu"])},
        {"factor": "Attack strength", "effect_home": ln(inp["attack_home"]), "effect_away": ln(inp["attack_away"])},
        {"factor": "Opponent defence", "effect_home": ln(inp["defence_away"]), "effect_away": ln(inp["defence_home"])},
        {"factor": "Home advantage", "effect_home": ln(inp["home_adv"]), "effect_away": 0.0},
    ]


# ------------------------------------------------------------------ baseline: historical frequencies
class Frequencies:
    """How often home wins, draws, away wins, over 2.5 goals and both-teams-to-score happened before a date (Laplace-smoothed)."""

    def __init__(self, matches: list[M]):
        self.dates = [m[0] for m in matches]
        self.c = [[0, 0, 0]]
        self.over = [0]
        self.btts = [0]
        for _, _, _, hg, ag in matches:
            row = list(self.c[-1])
            row[outcome(hg, ag)] += 1
            self.c.append(row)
            self.over.append(self.over[-1] + (1 if hg + ag > 2 else 0))
            self.btts.append(self.btts[-1] + (1 if hg > 0 and ag > 0 else 0))

    def before(self, d: date) -> dict:
        i = bisect.bisect_left(self.dates, d)
        c = [x + 1 for x in self.c[i]]
        t = sum(c)
        return {"p": [x / t for x in c], "p_over_2_5": (self.over[i] + 1) / (i + 2), "p_btts": (self.btts[i] + 1) / (i + 2), "matches": i}
