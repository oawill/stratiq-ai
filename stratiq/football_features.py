"""Team statistics, form, head-to-head and ratings computed from historical results. Pure; no database.

Every function takes a `before` date and uses only matches played strictly earlier, so a figure for a fixture can never include
that fixture or anything after it. Goal rates here are ESTIMATED FROM RESULTS; they are not provider-supplied expected goals.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone

from . import backtest
from .model import HistMatch, predict
from .ratings import Match, fit_ratings

# (date, home, away, home_goals, away_goals); lists are in date order
M = tuple[date, str, str, int, int]

ELO_START = 1500.0
ELO_K = 20.0
ELO_HOME_ADV = 65.0   # rating points a home side starts ahead by; a common convention, not fitted here
GOAL_RATE_NOTE = "Estimated from match results; not provider-supplied expected goals (xG)."


def _prior(matches: list[M], before: date | None) -> list[M]:
    return [m for m in matches if before is None or m[0] < before]


def _points(gf: int, ga: int) -> int:
    return 3 if gf > ga else 1 if gf == ga else 0


def _venue(rows: list[tuple[int, int]]) -> dict:
    n = len(rows)
    w = sum(1 for gf, ga in rows if gf > ga)
    d = sum(1 for gf, ga in rows if gf == ga)
    return {"played": n, "wins": w, "draws": d, "losses": n - w - d,
            "goals_for_per_match": round(sum(r[0] for r in rows) / n, 3) if n else None,
            "goals_against_per_match": round(sum(r[1] for r in rows) / n, 3) if n else None}


def _form(rows: list[tuple[int, int]], n: int) -> dict:
    last = rows[-n:]
    letters = "".join("W" if gf > ga else "D" if gf == ga else "L" for gf, ga in last)
    return {"matches": len(last), "results": letters, "points_per_match": round(sum(_points(*r) for r in last) / len(last), 3) if last else None}


def elo_ratings(matches: list[M], before: date | None = None, k: float = ELO_K, home_adv: float = ELO_HOME_ADV) -> dict[str, float]:
    """Elo-style ratings after playing every match before `before`, in date order. Ties on a date are processed together, so
    two matches on the same day never use each other's result."""
    rating: dict[str, float] = {}
    day_updates: list[tuple[str, float]] = []
    current: date | None = None

    def flush():
        for team, delta in day_updates:
            rating[team] = rating.get(team, ELO_START) + delta
        day_updates.clear()

    for d, h, a, hg, ag in _prior(matches, before):
        if current is not None and d != current:
            flush()
        current = d
        rh, ra = rating.get(h, ELO_START), rating.get(a, ELO_START)
        exp_h = 1.0 / (1.0 + 10 ** (-((rh + home_adv) - ra) / 400.0))
        actual = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
        gd = abs(hg - ag)
        mult = 1.0 if gd <= 1 else 1.5 if gd == 2 else (11 + gd) / 8
        delta = k * mult * (actual - exp_h)
        day_updates.append((h, delta))
        day_updates.append((a, -delta))
    flush()
    return rating


def team_profile(matches: list[M], team: str, before: date | None = None) -> dict:
    prior = _prior(matches, before)
    mine = [(d, h, a, hg, ag) for d, h, a, hg, ag in prior if team in (h, a)]
    seq = [(hg, ag) if h == team else (ag, hg) for _, h, a, hg, ag in mine]          # (for, against) in date order
    home = [(hg, ag) for _, h, _, hg, ag in mine if h == team]
    away = [(ag, hg) for _, _, a, hg, ag in mine if a == team]
    n = len(seq)
    w = sum(1 for gf, ga in seq if gf > ga)
    dr = sum(1 for gf, ga in seq if gf == ga)
    out: dict = {"team": team, "as_of": before.isoformat() if before else None, "played": n}
    if n:
        out.update({
            "wins": w, "draws": dr, "losses": n - w - dr,
            "win_rate": round(w / n, 4), "draw_rate": round(dr / n, 4), "loss_rate": round((n - w - dr) / n, 4),
            "points_per_match": round(sum(_points(*r) for r in seq) / n, 3),
            "goals_for_per_match": round(sum(r[0] for r in seq) / n, 3),
            "goals_against_per_match": round(sum(r[1] for r in seq) / n, 3),
            "average_goals_per_match": round(sum(r[0] + r[1] for r in seq) / n, 3),
            "clean_sheet_rate": round(sum(1 for r in seq if r[1] == 0) / n, 4),
            "failed_to_score_rate": round(sum(1 for r in seq if r[0] == 0) / n, 4),
        })
    out.update({"home": _venue(home), "away": _venue(away), "form_last_5": _form(seq, 5), "form_last_10": _form(seq, 10)})
    if mine:
        ref = before or date.today()
        out["coverage"] = {"first_match": mine[0][0].isoformat(), "last_match": mine[-1][0].isoformat(), "matches": n,
                           "note": "League matches in your imported data only; cups and European matches are not included, so rest days are overstated for clubs that play them."}
        out["days_since_last_match"] = max(0, (ref - mine[-1][0]).days)
    out["sample_note"] = "Fewer than about 30 matches makes any rate here uncertain." if n < 30 else "Rates are averages over every match in the imported data before the as-of date."
    ratings = elo_ratings(matches, before)
    out["elo"] = round(ratings.get(team, ELO_START), 1)
    if prior:
        teams = sorted({x for _, h, a, *_ in prior for x in (h, a)})
        fit = fit_ratings([Match(h, a, hg, ag) for _, h, a, hg, ag in prior], teams)
        out["attack_strength"] = round(fit.attack.get(team, 1.0), 4)
        out["defence_strength"] = round(fit.defence.get(team, 1.0), 4)
        out["goal_rate_note"] = GOAL_RATE_NOTE
    return out


def head_to_head(matches: list[M], a: str, b: str, before: date | None = None, limit: int = 10) -> dict:
    meetings = [(d, h, aw, hg, ag) for d, h, aw, hg, ag in _prior(matches, before) if {h, aw} == {a, b}]
    wa = wb = dr = ga = gb = 0
    for _, h, aw, hg, ag in meetings:
        fa, fb = (hg, ag) if h == a else (ag, hg)
        ga += fa
        gb += fb
        if fa > fb:
            wa += 1
        elif fa < fb:
            wb += 1
        else:
            dr += 1
    recent = [{"date": d.isoformat(), "home": h, "away": aw, "score": f"{hg}-{ag}"} for d, h, aw, hg, ag in meetings[-limit:]][::-1]
    return {"team_a": a, "team_b": b, "meetings": len(meetings), "wins_a": wa, "wins_b": wb, "draws": dr, "goals_a": ga, "goals_b": gb, "recent": recent}


def league_baseline(matches: list[M], before: date | None = None) -> dict:
    prior = _prior(matches, before)
    n = len(prior)
    if not n:
        return {"matches": 0}
    return {"matches": n, "home_win_rate": round(sum(1 for m in prior if m[3] > m[4]) / n, 4), "draw_rate": round(sum(1 for m in prior if m[3] == m[4]) / n, 4),
            "away_win_rate": round(sum(1 for m in prior if m[3] < m[4]) / n, 4), "average_goals_per_match": round(sum(m[3] + m[4] for m in prior) / n, 3)}


def hist_matches(matches: list[M]) -> list[HistMatch]:
    return [HistMatch(h, a, hg, ag, datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc)) for d, h, a, hg, ag in matches]


def fixture_view(matches: list[M], home: str, away: str, before: date, dataset: str = "match history") -> dict:
    """Everything known about a fixture on `before`, from earlier matches only, with the Poisson projection."""
    prior = _prior(matches, before)
    teams = sorted({x for _, h, a, *_ in prior for x in (h, a)} | {home, away})
    cutoff = datetime(before.year, before.month, before.day, tzinfo=timezone.utc)
    pred = predict(hist_matches(prior), teams, home, away, cutoff, dataset)
    return {
        "as_of": before.isoformat(), "matches_used": len(prior),
        "home": team_profile(matches, home, before), "away": team_profile(matches, away, before),
        "head_to_head": head_to_head(matches, home, away, before), "league": league_baseline(matches, before),
        "elo_difference": round(team_profile(matches, home, before)["elo"] - team_profile(matches, away, before)["elo"], 1),
        "projection": {k: pred["outputs"][k] for k in ("home_xg", "away_xg", "p_home", "p_draw", "p_away", "p_btts", "p_over_2_5")},
        "projection_note": GOAL_RATE_NOTE,
    }


# ------------------------------------------------------------------ chronological evaluation
def _spread(lo: int, hi: int, cap: int) -> list[int]:
    n = hi - lo
    if n <= cap:
        return list(range(lo, hi))
    return sorted({lo + int(i * n / cap) for i in range(cap)})


def chronological_evaluation(matches: list[M], dataset: str = "match history", per_period: int = 100, train_share: float = 0.6, validation_share: float = 0.2) -> dict:
    """Split the matches by time into training, validation and test periods (never at random) and score the Poisson model on the
    last two. Every scored match is predicted from all strictly earlier matches only, so nothing leaks backwards. The model has no
    settings that were tuned on either period: the split shows whether performance holds in a later period it has not seen."""
    ordered = sorted(matches, key=lambda m: (m[0], m[1], m[2]))
    n = len(ordered)
    a, b = int(n * train_share), int(n * (train_share + validation_share))
    if a < 100 or b - a < 30 or n - b < 30:
        return {"ok": False, "matches": n, "reason": "Need roughly 250 matches or more to split by time (at least 100 to learn from, and 30 in each later period)."}
    hm = hist_matches(ordered)
    teams = sorted({x for m in ordered for x in (m[1], m[2])})

    def period(name: str, lo: int, hi: int, scored: bool) -> dict:
        info = {"name": name, "matches": hi - lo, "first": ordered[lo][0].isoformat(), "last": ordered[hi - 1][0].isoformat()}
        if scored:
            idx = _spread(lo, hi, per_period)
            info["scored"] = len(idx)
            info.update({k: v for k, v in backtest.summarize(backtest.score_rows(hm, idx, teams, dataset)).items() if k != "sample_size"})
        return info
    return {
        "ok": True, "matches": n,
        "periods": [period("training", 0, a, False), period("validation", a, b, True), period("test", b, n, True)],
        "note": "Matches are split by date: the first 60% for training, the next 20% for validation, the last 20% for testing. Each scored match uses only earlier matches.",
    }


def calibration_error(reliability: list[dict]) -> float:
    """Weighted average gap between what the model said and what happened (0 is perfect)."""
    total = sum(r["count"] for r in reliability)
    return sum(r["count"] * abs(r["mean_predicted"] - r["observed"]) for r in reliability) / total if total else math.nan
