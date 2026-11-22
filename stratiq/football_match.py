"""Everything the match page shows, assembled from stored records only (Phase 4D).

Three kinds of information are kept apart and labelled in the response so the page can never blur them:
  * `historical`  statistics computed from imported past results dated before the forecast's cutoff
  * `verified`    current information supplied by the fixture provider or an uploaded, dated source (kickoff, status, final score, availability reports)
  * `model`       estimates made by a model before kickoff (probabilities, expected goals, score distribution, drivers)
Nothing is invented: a section without data says so and why. Single-match evaluation numbers are arithmetic on the stored official forecast
and the verified final score; they are not stored and say little about a model (that is what the performance laboratory is for).
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone

from . import football_forecast as ff
from . import football_models as fm
from . import football_provider as fp

GRID = 6                         # score distribution shown for 0..5 goals each; the rest is reported as "other"
OUTCOME = ("home", "draw", "away")
KINDS = {
    "historical": "Historical statistics: computed from imported results dated before the forecast was made.",
    "verified": "Current verified information: supplied by the fixture provider or a dated source you uploaded.",
    "model": "Model estimate: a probability or expected value produced by a model before kickoff. Not a certainty.",
}


def _recent(conn, wid: str, team: str, before: date, n: int = 5) -> list[dict]:
    rows = conn.execute("""select match_date, home_team, away_team, home_goals, away_goals from match_history where workspace_id=%s and competition='EPL' and match_date < %s
                           and (home_team=%s or away_team=%s) order by match_date desc limit %s""", (wid, before, team, team, n)).fetchall()
    out = []
    for r in rows:
        home = r["home_team"] == team
        gf, ga = (r["home_goals"], r["away_goals"]) if home else (r["away_goals"], r["home_goals"])
        out.append({"date": str(r["match_date"]), "opponent": r["away_team"] if home else r["home_team"], "venue": "H" if home else "A", "goals_for": gf, "goals_against": ga,
                    "result": "W" if gf > ga else "D" if gf == ga else "L"})
    return out


def _meetings(conn, wid: str, a: str, b: str, before: date, n: int = 10) -> list[dict]:
    rows = conn.execute("""select match_date, season, home_team, away_team, home_goals, away_goals from match_history where workspace_id=%s and competition='EPL' and match_date < %s
                           and ((home_team=%s and away_team=%s) or (home_team=%s and away_team=%s)) order by match_date desc limit %s""", (wid, before, a, b, b, a, n)).fetchall()
    return [{"date": str(r["match_date"]), "season": r["season"], "home_team": r["home_team"], "away_team": r["away_team"], "home_goals": r["home_goals"], "away_goals": r["away_goals"]} for r in rows]


def _record(f: dict, role: str, venue: str) -> dict | None:
    r = f.get(f"{role}_{venue}_record")
    return r if r and r.get("played") else None


def _grid(conn, v: dict) -> dict | None:
    """The scoreline distribution implied by the stored expected goals and the Dixon-Coles dependence setting recorded with the model version."""
    if v["expected_home"] is None or v["expected_away"] is None:
        return None
    mv = conn.execute("select params from football_model_versions where id=%s", (v["model_version_id"],)).fetchone()
    rho = float(((mv or {}).get("params") or {}).get("settings", {}).get("rho", 0.0) or 0.0)
    g = fm.score_grid(float(v["expected_home"]), float(v["expected_away"]), rho if v["goal_model"] == "dixon_coles" else 0.0)
    cells = [[round(g[h][a], 5) for a in range(GRID)] for h in range(GRID)]
    shown = sum(sum(r) for r in cells)
    return {"max_goals": GRID - 1, "cells": cells, "other": round(max(0.0, 1 - shown), 5), "rho": rho, "full": g}


def _evaluation(fx: dict, v: dict | None, grid: dict | None, stored: dict | None = None) -> dict | None:
    """What happened against the official forecast, for one match. Plain arithmetic on stored values."""
    if fx["status"] not in fp.FINAL:
        return None
    if fx["status"] == "awarded":
        return {"available": False, "note": "This result was decided off the pitch rather than played, so the forecast is not scored."}
    if fx["home_goals"] is None or fx["away_goals"] is None:
        return {"available": False, "note": "The match is finished but the provider has not supplied a verified full-time score yet, so it is not evaluated."}
    hg, ag = fx["home_goals"], fx["away_goals"]
    actual = 0 if hg > ag else 1 if hg == ag else 2
    base = {"final_score": {"home": hg, "away": ag}, "outcome": OUTCOME[actual]}
    if not v or not v["is_official"]:
        return {"available": False, **base, "note": "No official forecast was made before kickoff, so there is nothing to evaluate."}
    if stored:                                   # the evaluation made by the reconciliation job: the record of truth, including corrections
        mk = stored["markets"] or {}
        return {"available": True, **base, "version_no": v["version_no"], "most_likely": OUTCOME[max(range(3), key=lambda i: (v["p_home"], v["p_draw"], v["p_away"])[i])], "most_likely_was_right": stored["correct"],
                "probability_given_to_outcome": round(stored["p_actual"], 4), "log_loss": round(stored["log_loss"], 4), "brier": round(stored["brier"], 4), "rps": round(stored["rps"], 4),
                "over_2_5": {"happened": mk["over_2_5"]["happened"], "probability": mk["over_2_5"]["p"]} if "over_2_5" in mk else None,
                "both_teams_to_score": {"happened": mk["btts"]["happened"], "probability": mk["btts"]["p"]} if "btts" in mk else None,
                "exact_score": {"in_top_five": mk["exact_score"]["in_top_five"], "probability": mk["exact_score"]["p"]} if "exact_score" in mk else None,
                "stored": True, "evaluated_at": stored["evaluated_at"], "correction_count": stored["correction_count"],
                "note": "Scored automatically when the verified result arrived. One match says little about a model: judge models on the live record and the performance laboratory."
                        + (f" The provider corrected this score {stored['correction_count']} time(s) and the match was re-scored." if stored["correction_count"] else "")}
    p = [v["p_home"], v["p_draw"], v["p_away"]]
    top = max(range(3), key=lambda i: p[i])
    out = {"available": True, "stored": False, **base, "version_no": v["version_no"], "most_likely": OUTCOME[top], "most_likely_was_right": top == actual, "probability_given_to_outcome": round(p[actual], 4),
           "log_loss": round(-math.log(max(p[actual], 1e-12)), 4), "brier": round(sum((p[i] - (1 if i == actual else 0)) ** 2 for i in range(3)), 4)}
    if v["p_over_2_5"] is not None:
        over = hg + ag > 2
        out["over_2_5"] = {"happened": over, "probability": round(v["p_over_2_5"] if over else 1 - v["p_over_2_5"], 4)}
    if v["p_btts"] is not None:
        both = hg > 0 and ag > 0
        out["both_teams_to_score"] = {"happened": both, "probability": round(v["p_btts"] if both else 1 - v["p_btts"], 4)}
    tops = v["top_scorelines"] or []
    out["exact_score"] = {"in_top_five": any(s["home"] == hg and s["away"] == ag for s in tops),
                          "probability": round(grid["full"][hg][ag], 5) if grid and hg <= fm.MAX_GOALS and ag <= fm.MAX_GOALS else None}
    out["note"] = ("One match says little about a model: a 30% outcome is expected to happen about three times in ten. Judge models on the performance laboratory, "
                   "which scores every match. These numbers are not stored.")
    return out


def build(conn, fx: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    wid = str(fx["workspace_id"])
    versions = conn.execute("select * from football_prediction_versions where fixture_id=%s order by version_no", (fx["id"],)).fetchall()
    official = next((v for v in versions if v["is_official"]), None)
    shown = official or (versions[-1] if versions else None)
    snap = conn.execute("select features, availability, cutoff from football_feature_snapshots where id=%s", (shown["snapshot_id"],)).fetchone() if shown else None
    f = snap["features"] if snap else {}
    cutoff = snap["cutoff"] if snap else (fx["kickoff_utc"].date() if fx["kickoff_utc"] else fx["fixture_date"])
    home, away = fx["home_team"], fx["away_team"]
    grid = _grid(conn, shown) if shown else None
    stored_eval = conn.execute("select * from football_prediction_evaluations where fixture_id=%s and voided_at is null", (fx["id"],)).fetchone()

    reports = conn.execute("""select team, player, status, from_date, to_date, available_at from football_player_availability where workspace_id=%s and team in (%s,%s)
                              and available_at <= %s and from_date <= %s and (to_date is null or to_date >= %s) order by team, player limit 60""",
                           (wid, home, away, now, fx["fixture_date"], fx["fixture_date"])).fetchall()
    avail = (snap or {}).get("availability", {}).get("player_availability")
    hist = conn.execute("select old_status, new_status, old_kickoff, new_kickoff, observed_at from football_fixture_status_history where fixture_id=%s order by observed_at, id", (fx["id"],)).fetchall()

    return {
        "kinds": KINDS,
        "fixture": {"id": str(fx["id"]), "competition": fx["competition"], "season": fx["season"], "matchday": fx["matchday"], "home_team": home, "away_team": away, "status": fx["status"],
                    "kickoff_utc": fx["kickoff_utc"], "venue": fx["venue"], "source": fx["provider"] or "uploaded file", "provider_updated_at": fx["provider_updated_at"],
                    "last_synced_at": fx["last_synced_at"], "final_score": {"home": fx["home_goals"], "away": fx["away_goals"]} if fx["home_goals"] is not None else None,
                    "forecastable": fx["status"] not in fp.INACTIVE and fx["status"] not in fp.FINAL, "kind": "verified"},
        "forecast": {"kind": "model", "version": ff.present(shown) if shown else None, "versions": len(versions),
                     "no_forecast_reason": None if shown else (ff.eligibility(fx, now) or "No forecast has been generated yet."),
                     "official_note": "The official evaluation forecast is the last one made before kickoff. It is the one evaluated once the result is known."},
        "form": {"kind": "historical", "cutoff": str(cutoff), "summary": {r: {k: f.get(f"{r}_{k}") for k in ("matches_played", "form_5", "form_5_ppg", "form_10_ppg", "goals_for_avg", "goals_against_avg", "clean_sheet_rate", "rest_days", "league_position", "points")}
                                                                             | {"elo": f.get(f"elo_{r}")} for r in ("home", "away")} if snap else None,
                 "recent": {"home": _recent(conn, wid, home, cutoff), "away": _recent(conn, wid, away, cutoff)},
                 "note": "Computed from imported results dated before the cutoff. Cup and European matches are not in the data."},
        "venue_performance": {"kind": "historical", "cutoff": str(cutoff), "home_team_at_home": _record(f, "home", "home"), "home_team_away": _record(f, "home", "away"),
                              "away_team_at_home": _record(f, "away", "home"), "away_team_away": _record(f, "away", "away"),
                              "note": "How each side has done at home and away in the imported results before the cutoff."},
        "head_to_head": {"kind": "historical", "cutoff": str(cutoff), "summary": f.get("head_to_head"), "meetings": _meetings(conn, wid, home, away, cutoff),
                         "note": "Earlier meetings in the imported results, newest first, home and away fixtures combined."},
        "goals": {"kind": "model", "expected": {"home": shown["expected_home"], "away": shown["expected_away"]} if shown else None, "score_grid": {k: v for k, v in grid.items() if k != "full"} if grid else None,
                  "top_scorelines": shown["top_scorelines"] if shown else None, "over_2_5": shown["p_over_2_5"] if shown else None, "both_teams_to_score": shown["p_btts"] if shown else None,
                  "provider_xg": {"home": f.get("home_xg_form"), "away": f.get("away_xg_form"), "kind": "historical"} if f.get("home_xg_form") else None,
                  "note": "Expected goals and the score distribution are model estimates (Dixon-Coles). Measured expected goals from past matches appear only if you uploaded them."},
        "availability": {"kind": "verified", "status": "reported" if reports else (avail or {}).get("status", "unavailable"),
                         "reports": [{"team": r["team"], "player": r["player"], "status": r["status"], "from_date": str(r["from_date"]), "to_date": str(r["to_date"]) if r["to_date"] else None, "reported_at": r["available_at"]} for r in reports],
                         "note": "Reports are listed only if a dated source was uploaded." if reports else "No injury, suspension or lineup information is available for this match, so none is used and nothing is assumed about who will play.",
                         "source": "uploaded availability records" if reports else (avail or {}).get("source", "none")},
        "drivers": {"kind": "model", "items": shown["drivers"] if shown else [], "note": "How the model arrived at its numbers; not causes in the real world."},
        "revisions": {"kind": "model", "versions": [ff.present(v) | {"generated_at": v["generated_at"]} for v in reversed(versions)],
                      "status_history": [{"old_status": h["old_status"], "new_status": h["new_status"], "old_kickoff": h["old_kickoff"], "new_kickoff": h["new_kickoff"], "observed_at": h["observed_at"]} for h in hist]},
        "result": {"kind": "verified", "evaluation": _evaluation(fx, shown if shown and shown["is_official"] else official, grid, stored_eval), "note": fx.get("result_note")} if fx["status"] in fp.FINAL else None,
        "warnings": shown["warnings"] if shown else [],
        "data_completeness": shown["completeness"] if shown else None,
    }
