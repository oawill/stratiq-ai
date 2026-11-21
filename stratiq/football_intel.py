"""Match intelligence: what is known about a fixture before kickoff, which factors are available, the forecasts of every model,
how reliable the picture is, and what-if scenarios. Pure; no database.

Nothing is invented. A factor with no data behind it is reported as unavailable, with the reason, and is never filled in.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date

from . import football_ensemble as fe
from . import football_gbm as gb
from . import football_models as fm
from .football_history import season_label
from .football_models import M

MODEL_NAMES = {"elo": "Elo rating", "poisson": "Time-weighted Poisson", "dixon_coles": "Dixon-Coles", "gbm": "Boosted trees", "ensemble": "Calibrated ensemble"}
TOTAL_FACTORS = 13

# The thirteen factor groups. `needs` says what must exist in the workspace for the factor to be available.
FACTORS = [
    {"key": "historical_performance", "name": "Historical performance", "detail": "Last 5 and 10 matches; wins, draws, losses", "needs": "results", "source": "Imported match results", "rule": "A match counts from the day after it is played."},
    {"key": "home_away", "name": "Home and away advantage", "detail": "Home and away scoring and defensive records", "needs": "results", "source": "Imported match results", "rule": "Matches before the cutoff only."},
    {"key": "team_strength", "name": "Team strength", "detail": "Elo rating, attack and defence ratings", "needs": "results", "source": "Computed from imported match results", "rule": "Fitted on matches before the cutoff only."},
    {"key": "head_to_head", "name": "Head to head", "detail": "Past meetings, weighted towards recent ones", "needs": "results", "source": "Imported match results", "rule": "Meetings before the cutoff only; half-life three years."},
    {"key": "goals", "name": "Goals", "detail": "Scoring averages, clean sheets, over/under 2.5, both teams to score", "needs": "results", "source": "Imported match results", "rule": "Matches before the cutoff only."},
    {"key": "expected_goals", "name": "Expected goals", "detail": "xG, xG against, xG difference (provider-supplied)", "needs": "xg", "source": "Football advanced statistics upload", "rule": "Post-match statistics, usable from the day after the match."},
    {"key": "player_availability", "name": "Player availability", "detail": "Injuries, suspensions, expected absences", "needs": "never", "source": "None: no upload or feed exists yet", "rule": "Would need a licensed feed or upload with timestamps."},
    {"key": "squad_strength", "name": "Squad strength", "detail": "Player ratings, squad depth, transfers", "needs": "never", "source": "None: no upload or feed exists yet", "rule": "Would need licensed player data."},
    {"key": "rest_fatigue", "name": "Rest and fatigue", "detail": "Days since the last match, fixture congestion", "needs": "results", "source": "Imported match results (league matches only)", "rule": "Cup and European matches are not in the data, so rest is overstated for clubs that play in them."},
    {"key": "match_context", "name": "Match context", "detail": "League position, title race, relegation pressure", "needs": "results", "source": "Computed from imported results of the same season", "rule": "Table built from matches before the cutoff."},
    {"key": "managerial", "name": "Managerial changes", "detail": "Manager tenure and recent changes", "needs": "never", "source": "None: no upload or feed exists yet", "rule": "Would need a dated list of manager appointments."},
    {"key": "betting_markets", "name": "Betting markets", "detail": "Pre-match odds and implied probabilities", "needs": "odds", "source": "Football advanced statistics upload (odds columns)", "rule": "Closing odds are known at kickoff; they are shown for comparison, not fed to the models."},
    {"key": "venue_conditions", "name": "Venue and conditions", "detail": "Home ground, travel, weather", "needs": "venue", "source": "Home side's ground from the fixture; travel and weather are not available", "rule": "Weather and travel would need a licensed feed."},
]


# ------------------------------------------------------------------ small helpers over earlier matches
def _prior(ms: list[M], cutoff: date) -> list[M]:
    return [m for m in ms if m[0] < cutoff]


def _team_seq(prior: list[M], team: str) -> list[tuple[date, int, int, bool]]:
    """(date, goals for, goals against, was home) for each earlier match of a team."""
    return [(d, hg if h == team else ag, ag if h == team else hg, h == team) for d, h, a, hg, ag in prior if team in (h, a)]


def _ppg(seq) -> float | None:
    return round(sum(3 if f > a else 1 if f == a else 0 for _, f, a, _ in seq) / len(seq), 3) if seq else None


def _avg(vals) -> float | None:
    vals = list(vals)
    return round(sum(vals) / len(vals), 3) if vals else None


def _side(seq, home: bool) -> dict:
    s = [x for x in seq if x[3] == home]
    return {"played": len(s), "goals_for": _avg(f for _, f, _, _ in s), "goals_against": _avg(a for _, _, a, _ in s), "points_per_match": _ppg(s)}


def _table(prior: list[M], season: str) -> list[dict]:
    pts, gd, played = {}, {}, {}
    for d, h, a, hg, ag in prior:
        if season_label(d) != season:
            continue
        for t in (h, a):
            pts.setdefault(t, 0)
            gd.setdefault(t, 0)
            played.setdefault(t, 0)
        played[h] += 1
        played[a] += 1
        gd[h] += hg - ag
        gd[a] += ag - hg
        pts[h] += 3 if hg > ag else 1 if hg == ag else 0
        pts[a] += 3 if ag > hg else 1 if hg == ag else 0
    rows = sorted(pts, key=lambda t: (-pts[t], -gd[t], t))
    return [{"team": t, "position": i + 1, "points": pts[t], "played": played[t], "goal_difference": gd[t]} for i, t in enumerate(rows)]


def _h2h(prior: list[M], home: str, away: str, cutoff: date, half_life_days: float = 1095.0) -> dict:
    meet = [m for m in prior if {m[1], m[2]} == {home, away}]
    if not meet:
        return {"meetings": 0}
    wsum = diff = 0.0
    wins = [0, 0, 0]
    for d, h, a, hg, ag in meet:
        w = 0.5 ** ((cutoff - d).days / half_life_days)
        gd = (hg - ag) if h == home else (ag - hg)
        wsum += w
        diff += w * gd
        wins[0 if gd > 0 else 1 if gd == 0 else 2] += 1
    return {"meetings": len(meet), "home_team_wins": wins[0], "draws": wins[1], "away_team_wins": wins[2], "recency_weighted_goal_difference": round(diff / wsum, 3),
            "last_meeting": meet[-1][0].isoformat()}


# ------------------------------------------------------------------ the snapshot
def build_snapshot(ms: list[M], home: str, away: str, cutoff: date, stats: list[dict] | None = None, kickoff: date | None = None) -> dict:
    """Everything usable about a fixture before `cutoff`, with which factors are available and why not. `stats` are
    uploaded advanced-statistics rows (dicts with date, home, away and optional xg/odds); only rows dated before the cutoff are used."""
    prior = _prior(ms, cutoff)
    ko = kickoff or cutoff            # information stops at `cutoff`; rest and the season table are read as of the kickoff date
    season = season_label(ko)
    seqs = {t: _team_seq(prior, t) for t in (home, away)}
    f: dict = {"matches_in_history": len(prior)}
    avail: dict = {}
    warn: list[str] = []
    as_of = prior[-1][0].isoformat() if prior else None
    src = "imported_match_results"

    def mark(key: str, status: str, note: str, source: str | None = None, coverage: str | None = None):
        avail[key] = {"status": status, "source": source or next(x["source"] for x in FACTORS if x["key"] == key), "as_of": as_of if status != "unavailable" else None, "coverage": coverage, "note": note}

    for role, t in (("home", home), ("away", away)):
        sq = seqs[t]
        last5, last10 = sq[-5:], sq[-10:]
        f[f"{role}_matches_played"] = len(sq)
        f[f"{role}_form_5_ppg"], f[f"{role}_form_10_ppg"] = _ppg(last5), _ppg(last10)
        f[f"{role}_form_5"] = "".join("W" if x[1] > x[2] else "D" if x[1] == x[2] else "L" for x in last5)
        f[f"{role}_home_record"], f[f"{role}_away_record"] = _side(sq, True), _side(sq, False)
        f[f"{role}_goals_for_avg"], f[f"{role}_goals_against_avg"] = _avg(x[1] for x in sq), _avg(x[2] for x in sq)
        f[f"{role}_clean_sheet_rate"] = _avg(1 if x[2] == 0 else 0 for x in sq)
        f[f"{role}_over_2_5_rate"] = _avg(1 if x[1] + x[2] > 2 else 0 for x in sq)
        f[f"{role}_btts_rate"] = _avg(1 if x[1] > 0 and x[2] > 0 else 0 for x in sq)
        last = sq[-1][0] if sq else None
        f[f"{role}_rest_days"] = (ko - last).days if last else None
        f[f"{role}_matches_last_14_days"] = sum(1 for x in sq if (ko - x[0]).days <= 14)
        f[f"{role}_matches_last_30_days"] = sum(1 for x in sq if (ko - x[0]).days <= 30)
    n_home, n_away = len(seqs[home]), len(seqs[away])
    mark("historical_performance", "available" if min(n_home, n_away) >= 10 else "partial" if min(n_home, n_away) >= 1 else "unavailable",
         f"{n_home} earlier matches for {home}, {n_away} for {away}." + ("" if min(n_home, n_away) >= 10 else " Fewer than 10, so form is thin."), coverage=f"{min(n_home, n_away)} to {max(n_home, n_away)} matches")
    mark("home_away", "available" if min(f["home_home_record"]["played"], f["away_away_record"]["played"]) >= 5 else "partial",
         f"{home} at home: {f['home_home_record']['played']} matches; {away} away: {f['away_away_record']['played']}.")
    mark("goals", "available" if prior else "unavailable", "Scoring averages and rates from earlier matches.")
    mark("rest_fatigue", "partial" if f["home_rest_days"] is not None and f["away_rest_days"] is not None else "unavailable",
         "League matches only: cup and European matches are not in the data, so rest is overstated for clubs that play in them.")
    if prior:
        pre, ratings = fm.elo_pass(prior, fm.EloParams())
        f["elo_home"], f["elo_away"] = round(ratings.get(home, fm.ELO_START), 1), round(ratings.get(away, fm.ELO_START), 1)
        f["elo_difference"] = round(f["elo_home"] - f["elo_away"], 1)
        fit = fm.fit_poisson(prior, cutoff, 730.0, 2.0)
        f["attack_home"], f["defence_home"] = round(fit.attack.get(home, 1.0), 4), round(fit.defence.get(home, 1.0), 4)
        f["attack_away"], f["defence_away"] = round(fit.attack.get(away, 1.0), 4), round(fit.defence.get(away, 1.0), 4)
        f["league_goals_per_team"], f["home_advantage_factor"] = round(fit.mu, 4), round(fit.home_adv, 4)
        mark("team_strength", "available" if min(n_home, n_away) >= 5 else "partial", "Elo and attack/defence ratings fitted on earlier matches only.")
    else:
        mark("team_strength", "unavailable", "No earlier matches.")
    f["head_to_head"] = _h2h(prior, home, away, cutoff)
    mark("head_to_head", "available" if f["head_to_head"]["meetings"] >= 3 else "partial" if f["head_to_head"]["meetings"] else "unavailable",
         f"{f['head_to_head']['meetings']} earlier meeting(s) in the imported matches.")
    table = _table(prior, season)
    pos = {r["team"]: r for r in table}
    if home in pos and away in pos:
        for role, t in (("home", home), ("away", away)):
            r = pos[t]
            f[f"{role}_league_position"], f[f"{role}_points"], f[f"{role}_table_played"] = r["position"], r["points"], r["played"]
            f[f"{role}_points_from_top"] = table[0]["points"] - r["points"]
            f[f"{role}_points_above_drop_zone"] = r["points"] - table[17]["points"] if len(table) >= 18 else None
        mark("match_context", "available" if min(pos[home]["played"], pos[away]["played"]) >= 5 else "partial", f"Table of {season} built from {len(table)} clubs' earlier matches.")
    else:
        mark("match_context", "unavailable", f"{home} or {away} has no earlier {season} match, so there is no table to read.")
    prev = f"{int(season[:4]) - 1}/{season[:4][2:]}"
    seen_prev = {t for d, h, a, *_ in prior if season_label(d) == prev for t in (h, a)}
    f["home_newly_promoted"] = (home not in seen_prev) if seen_prev else None
    f["away_newly_promoted"] = (away not in seen_prev) if seen_prev else None
    # venue: the fixture names the home side, so the ground is known; travel and weather are not
    f["venue"] = home
    mark("venue_conditions", "partial", "Home ground is the home side's; travel distance and weather are not available.")
    for key in ("player_availability", "squad_strength", "managerial"):
        mark(key, "unavailable", next(x["rule"] for x in FACTORS if x["key"] == key))
    # uploaded advanced statistics: expected goals and odds, only from matches before the cutoff
    xg_rows = [s for s in (stats or []) if s["date"] < cutoff and s.get("home_xg") is not None and s.get("away_xg") is not None]
    def xg_form(team: str) -> dict | None:
        mine = [(s["home_xg"], s["away_xg"]) if s["home"] == team else (s["away_xg"], s["home_xg"]) for s in xg_rows if team in (s["home"], s["away"])][-10:]
        return {"matches": len(mine), "xg_for": _avg(x[0] for x in mine), "xg_against": _avg(x[1] for x in mine), "xg_difference": _avg(x[0] - x[1] for x in mine)} if mine else None
    xh, xa = xg_form(home), xg_form(away)
    if xh and xa and min(xh["matches"], xa["matches"]) >= 5:
        f["home_xg_form"], f["away_xg_form"] = xh, xa
        mark("expected_goals", "available", "Provider-supplied xG from your upload, last 10 matches each.", coverage=f"{min(xh['matches'], xa['matches'])} to {max(xh['matches'], xa['matches'])} matches")
    else:
        mark("expected_goals", "unavailable", "No uploaded expected-goals data covers both teams (needs 5 earlier matches each)." if stats else "No football advanced statistics have been uploaded.")
    odds = [s for s in (stats or []) if s["date"] == ko and s["home"] == home and s["away"] == away and s.get("odds_home")]
    if odds:
        o = odds[0]
        inv = [1 / o["odds_home"], 1 / o["odds_draw"], 1 / o["odds_away"]]
        tot = sum(inv)
        f["market_implied"] = {"home": round(inv[0] / tot, 4), "draw": round(inv[1] / tot, 4), "away": round(inv[2] / tot, 4), "overround": round(tot - 1, 4)}
        mark("betting_markets", "available", "Implied probabilities with the bookmaker margin removed; for comparison only.")
    else:
        mark("betting_markets", "unavailable", "No uploaded odds for this fixture.")
    # warnings
    for t, n in ((home, n_home), (away, n_away)):
        if n < 5:
            warn.append(f"{t} has only {n} earlier match(es) in the imported history, so its ratings are very uncertain.")
    for t, k in ((home, "home_newly_promoted"), (away, "away_newly_promoted")):
        if f.get(k):
            warn.append(f"{t} was not in the previous season's imported matches (newly promoted or newly imported), so its history is less relevant.")
    if prior and abs(f.get("elo_difference", 0)) > 350:
        warn.append("The rating gap is unusually large compared with typical fixtures, so the forecast is an extrapolation.")
    missing = [x["name"] for x in FACTORS if avail[x["key"]]["status"] == "unavailable"]
    if missing:
        warn.append("Unavailable and not used: " + ", ".join(missing) + ".")
    if "managerial" in avail and avail["managerial"]["status"] == "unavailable":
        warn.append("Recent manager or squad changes cannot be detected, so they are not reflected in this forecast.")
    body = {"cutoff": cutoff.isoformat(), "kickoff": ko.isoformat(), "home": home, "away": away, "features": f}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    return {**body, "availability": avail, "warnings": warn, "source": src, "history_as_of": as_of, "sha256": digest}


# ------------------------------------------------------------------ live forecasts from tuned settings
def default_settings() -> dict:
    ep = fm.EloParams()
    em = fm.EloMap()
    return {"tuned": False, "elo": {"k": ep.k, "home_adv": ep.home_adv, "regress": ep.regress, "newcomer": ep.newcomer, **vars(em)}, "poisson": {"half_life_days": 730.0, "prior_games": 2.0}, "rho": 0.0}


def live_forecast(ms: list[M], home: str, away: str, cutoff: date, settings: dict | None = None, adjust: dict | None = None) -> dict:
    """Forecasts from every model using only matches before `cutoff`. `adjust` applies what-if changes (see `apply_adjustments`)."""
    st = settings or default_settings()
    prior = _prior(ms, cutoff)
    out: dict = {}
    e = st["elo"]
    ep = fm.EloParams(e["k"], e["home_adv"], e["regress"], e["newcomer"])
    emap = fm.EloMap(e["scale"], e["draw"], e["offset"])
    _, ratings = fm.elo_pass(prior, ep)
    rh, ra = ratings.get(home, fm.ELO_START), ratings.get(away, fm.ELO_START)
    adj = adjust or {}
    rh += adj.get("home_rating_points", 0.0)
    ra += adj.get("away_rating_points", 0.0)
    ha_shift = adj.get("home_advantage_points", 0.0)
    out["elo"] = {"probs": fm.elo_probs(rh + ha_shift, ra, ep, emap), "inputs": {"rating_home": rh, "rating_away": ra, "home_adv": ep.home_adv + ha_shift, "scale": emap.scale, "draw": emap.draw, "offset": emap.offset},
                  "drivers": [{"factor": "Rating gap including home advantage", "points": rh + ep.home_adv + ha_shift - ra}]}
    fit = fm.fit_poisson(prior, cutoff, st["poisson"]["half_life_days"], st["poisson"]["prior_games"])
    inp = fit.inputs(home, away)
    inp = apply_adjustments(inp, adj)
    lh = inp["mu"] * inp["attack_home"] * inp["defence_away"] * inp["home_adv"]
    la = inp["mu"] * inp["attack_away"] * inp["defence_home"]
    for name, rho in (("poisson", 0.0), ("dixon_coles", st.get("rho", 0.0))):
        mk = fm.grid_markets(fm.score_grid(lh, la, rho))
        out[name] = {"probs": [mk["p_home"], mk["p_draw"], mk["p_away"]], "p_over_2_5": mk["p_over_2_5"], "p_btts": mk["p_btts"], "top_scorelines": mk["top_scorelines"],
                     "expected_goals": [lh, la], "inputs": {**inp, "rho": rho}, "drivers": fm.poisson_drivers(inp)}
    # The boosted trees and the ensemble exist only after a backtest, and describe the fixture as it is: a what-if scenario is not applied to them.
    if st.get("gbm") and st.get("ensemble") and not adj:
        x = gb.live_vector(prior, home, away, cutoff, rh + ep.home_adv - ra)
        gp = gb.predict(st["gbm"], x)
        out["gbm"] = {"probs": gp, "inputs": dict(zip(gb.FEATURES, x)), "drivers": [{"factor": f, "share": v} for f, v in list(st["gbm"].get("importance", {}).items())[:3]]}
        members = {"elo": out["elo"]["probs"], "dixon_coles": out["dixon_coles"]["probs"], "gbm": gp}
        out["ensemble"] = {"probs": fe.apply_ensemble(st["ensemble"], members), "inputs": {"weights": st["ensemble"]["weights"], "temperature": st["ensemble"]["temperature"], "members": members}, "drivers": []}
    return out


def apply_adjustments(inp: dict, adj: dict) -> dict:
    """What-if changes to the Poisson inputs. `missing_attack_loss` and `missing_defence_loss` are fractions YOU assume for absent
    players (0.1 = 10% less attack); they are scenario assumptions, not estimates from data."""
    o = dict(inp)
    o["home_adv"] = inp["home_adv"] * adj.get("home_advantage_multiplier", 1.0)
    o["attack_home"] = inp["attack_home"] * adj.get("home_attack_multiplier", 1.0) * (1 - adj.get("home_missing_attack_loss", 0.0))
    o["attack_away"] = inp["attack_away"] * adj.get("away_attack_multiplier", 1.0) * (1 - adj.get("away_missing_attack_loss", 0.0))
    o["defence_home"] = inp["defence_home"] * adj.get("home_defence_multiplier", 1.0) * (1 + adj.get("home_missing_defence_loss", 0.0))
    o["defence_away"] = inp["defence_away"] * adj.get("away_defence_multiplier", 1.0) * (1 + adj.get("away_missing_defence_loss", 0.0))
    return o


# ------------------------------------------------------------------ reliability: four separate things, never one "confidence"
def reliability(forecasts: dict, snapshot: dict, calibration: dict | None) -> dict:
    avail = snapshot["availability"]
    got = [k for k, v in avail.items() if v["status"] == "available"]
    part = [k for k, v in avail.items() if v["status"] == "partial"]
    miss = [k for k, v in avail.items() if v["status"] == "unavailable"]
    homes = [forecasts[m]["probs"][0] for m in MODEL_NAMES if m in forecasts]
    spread = max(homes) - min(homes) if homes else None
    f = snapshot["features"]
    thin = min(f.get("home_matches_played", 0), f.get("away_matches_played", 0))
    return {
        "model_probability": "The forecast probabilities. A 75% probability is not a 75% confidence score: it is how likely the model thinks the outcome is.",
        "data_completeness": {"available": len(got), "partial": len(part), "unavailable": len(miss), "of": TOTAL_FACTORS, "share_available": round((len(got) + 0.5 * len(part)) / TOTAL_FACTORS, 3),
                              "missing": [next(x["name"] for x in FACTORS if x["key"] == k) for k in miss]},
        "historical_calibration": calibration or {"note": "No backtest has been run on this history yet, so how well calibrated the models are is unknown."},
        "model_disagreement": None if spread is None else {"home_win_spread": round(spread, 4), "note": "Gap between the highest and lowest home-win probability across models; a wide gap means the models read the fixture differently."},
        "sample_size": {"fewest_earlier_matches_for_a_team": thin, "note": "Fewer than about 30 earlier matches makes a team's rating uncertain."},
    }
