"""Result reconciliation and evaluation of live forecasts (Phase 4F).

When the provider reports a fixture as finished with a full-time score, this module, once per fixture and score:
  1. checks that it is a result worth scoring (a played match, not postponed, suspended, cancelled, awarded or still live)
  2. records the score in `football_result_history` (a correction is a new revision, never an overwrite)
  3. adds the match to `match_history`, the training and analysis record, unless a different score for that match is already there from another source
  4. scores the official pre-kickoff forecast (one row per version, so a match is never counted twice)
  5. feeds the existing forecast-tracking tables, so drift monitoring and the performance laboratory see the same forecast and result
  6. refreshes the club registry (ratings are recomputed from match_history at forecast time, so the new result reaches every later forecast)

Safety rules: an unfinished or implausibly early result is never scored; "awarded" results (decided off the pitch) are not scored; a conflict with an
uploaded result for the same match is reported and left for a person, never overwritten; a score the provider later changes re-scores the match and counts the
correction; a match the provider later withdraws from "finished" has its evaluation voided. Running it again changes nothing.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

from . import football_intel_api as api
from . import football_match as fm_
from . import football_provider as fp
from . import football_store
from .football_history import season_label

MIN_AFTER_KICKOFF = timedelta(minutes=60)       # a finished status earlier than this after kickoff is not believed
OUTCOME = ("home", "draw", "away")
UNIFORM = {"log_loss": math.log(3), "brier": 2 / 3}      # a forecast of one third each scores exactly this on every match (its RPS depends on the result)
MIN_FOR_VERDICT = 30


def _outcome(hg: int, ag: int) -> int:
    return 0 if hg > ag else 1 if hg == ag else 2


def metrics(probs: list[float], outcome: int) -> dict:
    """Scores for one 1X2 forecast. Lower is better for all three."""
    p = probs[outcome]
    cum_f, cum_o, rps = 0.0, 0.0, 0.0
    for k in range(2):
        cum_f += probs[k]
        cum_o += 1.0 if outcome == k else 0.0
        rps += (cum_f - cum_o) ** 2
    return {"p_actual": p, "log_loss": -math.log(max(p, 1e-12)), "brier": sum((probs[k] - (1.0 if k == outcome else 0.0)) ** 2 for k in range(3)), "rps": rps / 2,
            "correct": max(range(3), key=lambda k: probs[k]) == outcome}


def market_metrics(v: dict, grid: dict | None, hg: int, ag: int) -> dict:
    out: dict = {}
    if v["p_over_2_5"] is not None:
        happened = hg + ag > 2
        p = v["p_over_2_5"] if happened else 1 - v["p_over_2_5"]
        out["over_2_5"] = {"happened": happened, "p": round(p, 4), "log_loss": round(-math.log(max(p, 1e-12)), 4), "brier": round((v["p_over_2_5"] - (1.0 if happened else 0.0)) ** 2, 4)}
    if v["p_btts"] is not None:
        happened = hg > 0 and ag > 0
        p = v["p_btts"] if happened else 1 - v["p_btts"]
        out["btts"] = {"happened": happened, "p": round(p, 4), "log_loss": round(-math.log(max(p, 1e-12)), 4), "brier": round((v["p_btts"] - (1.0 if happened else 0.0)) ** 2, 4)}
    out["exact_score"] = {"in_top_five": any(s["home"] == hg and s["away"] == ag for s in (v["top_scorelines"] or [])),
                          "p": round(grid["full"][hg][ag], 5) if grid and hg < len(grid["full"]) and ag < len(grid["full"]) else None}
    if v["expected_home"] is not None:
        out["goals_error"] = {"home": round(v["expected_home"] - hg, 3), "away": round(v["expected_away"] - ag, 3)}
    return out


def _worth_scoring(fx: dict, now: datetime) -> str | None:
    """None if the fixture carries a verified result that may be scored, else the reason it may not."""
    if fx["status"] != "finished":
        return f"The match is {fx['status'].replace('_', ' ')}, not finished." if fx["status"] != "awarded" else "A result decided off the pitch is not a played match, so it is not scored."
    if fx["home_goals"] is None or fx["away_goals"] is None:
        return "The provider has not supplied a verified full-time score."
    if not fx["kickoff_utc"] or now < fx["kickoff_utc"] + MIN_AFTER_KICKOFF:
        return "The match is reported finished less than an hour after kickoff, which is not believed."
    return None


def _result_revision(conn, fx: dict, now: datetime) -> tuple[int, bool]:
    """(revision number, is_correction). Records the score if it differs from the latest revision."""
    last = conn.execute("select revision, home_goals, away_goals from football_result_history where fixture_id=%s order by revision desc limit 1", (fx["id"],)).fetchone()
    if last and (last["home_goals"], last["away_goals"]) == (fx["home_goals"], fx["away_goals"]):
        return last["revision"], False
    rev = (last["revision"] + 1) if last else 1
    conn.execute("insert into football_result_history (workspace_id, fixture_id, revision, home_goals, away_goals, observed_at) values (%s,%s,%s,%s,%s,%s)",
                 (fx["workspace_id"], fx["id"], rev, fx["home_goals"], fx["away_goals"], now))
    return rev, last is not None


def _history_row(conn, fx: dict, now: datetime) -> str:
    """'added', 'updated', 'unchanged' or 'conflict'. A different score from another source is never overwritten."""
    wid, season = str(fx["workspace_id"]), season_label(fx["fixture_date"])
    ref = f"{fp.PROVIDER}:{fx['id']}"
    row = conn.execute("select id, home_goals, away_goals, source_provider from match_history where workspace_id=%s and competition=%s and season=%s and match_date=%s and home_team=%s and away_team=%s",
                       (wid, fx["competition"], season, fx["fixture_date"], fx["home_team"], fx["away_team"])).fetchone()
    if row is None:
        conn.execute("""insert into match_history (workspace_id, competition, season, match_date, home_team, away_team, home_goals, away_goals, source_provider, source_reference, imported_at, updated_at)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (wid, fx["competition"], season, fx["fixture_date"], fx["home_team"], fx["away_team"], fx["home_goals"], fx["away_goals"], fp.PROVIDER, ref, now, now))
        return "added"
    if (row["home_goals"], row["away_goals"]) == (fx["home_goals"], fx["away_goals"]):
        return "unchanged"
    if row["source_provider"] != fp.PROVIDER:
        return "conflict"
    conn.execute("update match_history set home_goals=%s, away_goals=%s, updated_at=%s where id=%s", (fx["home_goals"], fx["away_goals"], now, row["id"]))
    return "updated"


def _feed_tracking(conn, wid: str, v: dict, fx: dict, correction: bool) -> None:
    """Make the official forecast visible to drift monitoring and the performance laboratory (football_predictions + outcomes)."""
    snap = conn.execute("select cutoff from football_feature_snapshots where id=%s", (v["snapshot_id"],)).fetchone()
    conn.execute("""insert into football_predictions (workspace_id, kind, model_version_id, snapshot_id, season, fixture_date, home_team, away_team, cutoff, p_home, p_draw, p_away, p_over_2_5, p_btts,
                       expected_home, expected_away, outputs, inputs) values (%s,'live',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'{}')
                    on conflict (workspace_id, model_version_id, fixture_date, home_team, away_team, cutoff) where kind = 'live' do nothing""",
                 (wid, v["model_version_id"], v["snapshot_id"], season_label(fx["fixture_date"]), fx["fixture_date"], fx["home_team"], fx["away_team"], snap["cutoff"], v["p_home"], v["p_draw"], v["p_away"],
                  v["p_over_2_5"], v["p_btts"], v["expected_home"], v["expected_away"], json.dumps({"drivers": v["drivers"], "top_scorelines": v["top_scorelines"], "from_version": v["version_no"]}, default=str)))
    if correction:
        conn.execute("""delete from football_prediction_outcomes where prediction_id in (select id from football_predictions where workspace_id=%s and kind='live' and fixture_date=%s and home_team=%s and away_team=%s)""",
                     (wid, fx["fixture_date"], fx["home_team"], fx["away_team"]))
    football_store.reconcile(conn, wid)


def reconcile_fixture(conn, fx: dict, now: datetime | None = None) -> dict:
    """One fixture. Returns {status: evaluated|unchanged|ineligible|conflict|no_forecast|voided, ...}; never raises for data problems."""
    now = now or datetime.now(timezone.utc)
    wid = str(fx["workspace_id"])
    if fx["reconciled_at"] is not None and fx["status"] != "finished":
        return _void(conn, fx, now)
    why = _worth_scoring(fx, now)
    if why:
        return {"status": "ineligible", "reason": why}
    if (fx["reconciled_home"], fx["reconciled_away"]) == (fx["home_goals"], fx["away_goals"]) and fx["reconciled_at"] is not None:
        return {"status": "unchanged"}
    conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"football-result:{fx['id']}",))
    rev, correction = _result_revision(conn, fx, now)
    hist = _history_row(conn, fx, now)
    if hist == "conflict":
        conn.execute("update football_fixtures set result_note=%s where id=%s", ("The provider's score differs from a result already stored from another source, so nothing was changed or scored. Check the stored result.", fx["id"]))
        return {"status": "conflict", "reason": "A different score for this match is already stored from another source. It was not overwritten and the forecast was not scored."}
    v = conn.execute("select * from football_prediction_versions where fixture_id=%s and is_official", (fx["id"],)).fetchone()
    out: dict = {"status": "evaluated", "history": hist, "revision": rev, "correction": correction}
    if v is None:
        out["status"] = "no_forecast"
        out["reason"] = "No official forecast was made before kickoff, so there is nothing to score. The result was still added to the match history."
    else:
        o = _outcome(fx["home_goals"], fx["away_goals"])
        probs = [float(v["p_home"]), float(v["p_draw"]), float(v["p_away"])]
        m = metrics(probs, o)
        grid = fm_._grid(conn, v)
        mk = market_metrics(v, grid, fx["home_goals"], fx["away_goals"])
        prev = conn.execute("select id, correction_count from football_prediction_evaluations where version_id=%s", (v["id"],)).fetchone()
        if prev:
            conn.execute("""update football_prediction_evaluations set home_goals=%s, away_goals=%s, outcome=%s, p_actual=%s, log_loss=%s, brier=%s, rps=%s, correct=%s, markets=%s,
                              correction_count=%s, evaluated_at=%s, voided_at=null, void_reason=null where id=%s""",
                         (fx["home_goals"], fx["away_goals"], o, m["p_actual"], m["log_loss"], m["brier"], m["rps"], m["correct"], json.dumps(mk), prev["correction_count"] + (1 if correction else 0), now, prev["id"]))
        else:
            conn.execute("""insert into football_prediction_evaluations (workspace_id, fixture_id, version_id, model_name, home_goals, away_goals, outcome, p_actual, log_loss, brier, rps, correct, markets, evaluated_at)
                            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                         (wid, fx["id"], v["id"], v["model_name"], fx["home_goals"], fx["away_goals"], o, m["p_actual"], m["log_loss"], m["brier"], m["rps"], m["correct"], json.dumps(mk), now))
        _feed_tracking(conn, wid, v, fx, correction)
        out |= {"version_no": v["version_no"], "log_loss": round(m["log_loss"], 4), "brier": round(m["brier"], 4), "correct": m["correct"]}
    football_store.refresh_teams(conn, wid, fx["competition"])
    conn.execute("update football_fixtures set reconciled_home=%s, reconciled_away=%s, reconciled_at=%s, result_note=%s where id=%s",
                 (fx["home_goals"], fx["away_goals"], now, "Score corrected by the provider and re-scored." if correction else None, fx["id"]))
    return out


def _void(conn, fx: dict, now: datetime) -> dict:
    """A match the provider has withdrawn from 'finished' (for example it was abandoned and the result struck out): its evaluation stops counting."""
    wid = str(fx["workspace_id"])
    n = conn.execute("""update football_prediction_evaluations set voided_at=%s, void_reason=%s where fixture_id=%s and voided_at is null""",
                     (now, f"The provider now reports the match as {fx['status'].replace('_', ' ')}.", fx["id"])).rowcount
    conn.execute("""delete from football_prediction_outcomes where prediction_id in (select id from football_predictions where workspace_id=%s and kind='live' and fixture_date=%s and home_team=%s and away_team=%s)""",
                 (wid, fx["fixture_date"], fx["home_team"], fx["away_team"]))
    conn.execute("""delete from match_history where workspace_id=%s and competition=%s and match_date=%s and home_team=%s and away_team=%s and source_provider=%s""",
                 (wid, fx["competition"], fx["fixture_date"], fx["home_team"], fx["away_team"], fp.PROVIDER))
    football_store.refresh_teams(conn, wid, fx["competition"])
    conn.execute("update football_fixtures set reconciled_home=null, reconciled_away=null, reconciled_at=null, result_note=%s where id=%s", (f"Result withdrawn: the match is now {fx['status'].replace('_', ' ')}.", fx["id"]))
    return {"status": "voided", "voided_evaluations": n}


def reconcile_workspace(conn, wid: str, now: datetime | None = None, limit: int = 20) -> dict:
    """Every fixture with a result not yet (or no longer) reconciled. Bounded, so a scheduled run always finishes."""
    now = now or datetime.now(timezone.utc)
    rows = conn.execute("""select * from football_fixtures where workspace_id=%s and (
                              (status='finished' and home_goals is not null and away_goals is not null and kickoff_utc <= %s
                               and (reconciled_at is null or (reconciled_home, reconciled_away) is distinct from (home_goals, away_goals)))
                              or (reconciled_at is not null and status <> 'finished'))
                           order by kickoff_utc limit %s""", (wid, now - MIN_AFTER_KICKOFF, limit)).fetchall()
    out = {"considered": len(rows), "evaluated": 0, "no_forecast": 0, "conflict": 0, "voided": 0, "ineligible": 0, "errors": 0}
    for fx in rows:
        try:
            with conn.transaction():
                r = reconcile_fixture(conn, fx, now)
        except Exception as e:                                           # noqa: BLE001 - one fixture failing must not stop the others
            out["errors"] += 1
            print(json.dumps({"event": "football.reconcile_failed", "workspace_id": wid, "fixture_id": str(fx["id"]), "error": type(e).__name__}), flush=True)
            continue
        if r["status"] in out:
            out[r["status"]] += 1
    return out
