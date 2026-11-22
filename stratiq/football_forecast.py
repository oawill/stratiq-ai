"""Versioned pre-match forecasts for live fixtures (Phase 4B).

For each scheduled fixture the production model (the calibrated ensemble when a backtest has produced one, otherwise Dixon-Coles) is run on a
frozen snapshot of what was known before kickoff. Every run that changes anything is stored as a NEW version; stored versions are immutable
(a database trigger enforces it), and the last version generated before kickoff is marked as the official evaluation forecast.

Information boundary: a forecast is only ever generated while the fixture is `scheduled` and `now < kickoff`, from results dated before today.
Nothing published after kickoff can enter a version, and the database rejects a version whose timestamp is not before kickoff.
Nothing is invented: ineligible fixtures (unknown club, too little history) get no forecast and a stated reason.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import datetime, timedelta, timezone

from . import football_backtest as fb
from . import football_intel as fi
from . import football_intel_api as api
from . import football_provider as fp
from . import football_store
from .football_jobs import system_principal

MIN_MATCHES = 5                 # a club with fewer earlier matches in the history gets no forecast
SIGNIFICANT_CHANGE = 0.05       # a move of 5 percentage points in any outcome counts as significant
HISTORY_STALE_DAYS = 14
LABEL = "Model estimate made before kickoff. A probability is not a prediction that something will happen, and this is not betting or financial advice."
CHECKPOINTS = ("discovery", "h48", "h24", "h6", "h1", "reschedule", "lineup", "manual")


def production_model(run) -> str:
    return "ensemble" if run and run["tuning"] and run["tuning"].get("ensemble") else "dixon_coles"


def percentages(probs: list[float]) -> list[float]:
    """Display percentages with one decimal that add up to exactly 100.0 (largest-remainder rounding)."""
    raw = [p * 1000 for p in probs]
    floor = [math.floor(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - floor[i], reverse=True)[: 1000 - sum(floor)]:
        floor[i] += 1
    return [f / 10 for f in floor]


def eligibility(fx: dict, now: datetime) -> str | None:
    """None when a forecast may be generated, otherwise the reason it may not."""
    if fx["status"] != "scheduled":
        return f"The match is {fx['status'].replace('_', ' ')}; only scheduled matches are forecast."
    if not fx["kickoff_utc"]:
        return "The fixture has no kickoff time from the provider."
    if now >= fx["kickoff_utc"]:
        return "Kickoff has passed, and a forecast must be made before it."
    if fx["competition"] != api.COMPETITION:
        return "Only Premier League fixtures are supported."
    return None


def _load(conn, wid: str):
    ms = api._plain(api._stored(conn, wid, api.COMPETITION))
    run = api._latest_run(conn, system_principal(wid))
    return ms, run, football_store.load_stats(conn, wid)


def _provider_refs(conn, fx: dict, snap: dict, now: datetime) -> dict:
    m = conn.execute("select provider, provider_fixture_id from football_fixture_provider_mappings where fixture_id=%s order by created_at limit 1", (fx["id"],)).fetchone()
    return {"fixture_provider": m["provider"] if m else None, "provider_fixture_id": m["provider_fixture_id"] if m else None,
            "provider_updated_at": fx["provider_updated_at"], "fixture_last_synced_at": fx["last_synced_at"], "kickoff_utc": fx["kickoff_utc"],
            "results_history_as_of": snap.get("history_as_of"), "forecast_generated_at": now}


def _change(prev, probs: list[float]) -> dict | None:
    if not prev:
        return None
    d = [probs[0] - prev["p_home"], probs[1] - prev["p_draw"], probs[2] - prev["p_away"]]
    big = max(abs(x) for x in d)
    return {"previous_version": prev["version_no"], "home": round(d[0], 4), "draw": round(d[1], 4), "away": round(d[2], 4), "max_abs_change": round(big, 4), "significant": big >= SIGNIFICANT_CHANGE}


def generate_version(conn, fx: dict, checkpoint: str, reason: str, now: datetime | None = None, loaded=None) -> dict:
    """One forecast for one fixture. Returns {status: created|unchanged|ineligible, ...}; never raises for data problems."""
    now = now or datetime.now(timezone.utc)
    if checkpoint not in CHECKPOINTS:
        raise ValueError("Unknown checkpoint")
    why = eligibility(fx, now)
    if why:
        return {"status": "ineligible", "reason": why}
    wid = str(fx["workspace_id"])
    ms, run, stats = loaded or _load(conn, wid)
    if not ms:
        return {"status": "ineligible", "reason": "No match history is imported, so there is nothing to forecast from."}
    known = {t for _, h, a, *_ in ms for t in (h, a)}
    missing = [t for t in (fx["home_team"], fx["away_team"]) if t not in known]
    if missing:
        return {"status": "ineligible", "reason": f"No history for {', '.join(missing)}: it is not among the imported clubs, so it is not forecast."}
    ko = fx["kickoff_utc"].date()
    cutoff = min(now.date(), ko)                    # results dated before today; never after the kickoff day
    snap = fi.build_snapshot(ms, fx["home_team"], fx["away_team"], cutoff, stats, ko)
    thin = min(snap["features"].get("home_matches_played", 0), snap["features"].get("away_matches_played", 0))
    if thin < MIN_MATCHES:
        return {"status": "ineligible", "reason": f"One of the clubs has only {thin} earlier match(es) in the history; at least {MIN_MATCHES} are needed."}
    settings = api._settings(run)
    fc = fi.live_forecast(ms, fx["home_team"], fx["away_team"], cutoff, settings)
    name = production_model(run)
    if name not in fc:
        name = "dixon_coles"
    probs = [float(x) for x in fc[name]["probs"]]
    if not all(math.isfinite(x) and 0 <= x <= 1 for x in probs) or abs(sum(probs) - 1) > 1e-6:
        return {"status": "ineligible", "reason": "The model produced probabilities that were not valid, so none were stored."}
    goal = fc["dixon_coles"]
    data_sha = fb.data_sha([m for m in ms if m[0] < cutoff])
    p = system_principal(wid)
    mv = api._version(conn, p, name, {"model": name, "settings": api._light(settings)}, data_sha)
    sha = hashlib.sha256(json.dumps({"snapshot": snap["sha256"], "model_version": mv, "model": name, "kickoff": fx["kickoff_utc"].isoformat()}, sort_keys=True).encode()).hexdigest()

    conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (str(fx["id"]),))          # one forecast writer per fixture at a time
    prev = conn.execute("select * from football_prediction_versions where fixture_id=%s order by version_no desc limit 1", (fx["id"],)).fetchone()
    if prev and prev["input_sha256"] == sha:
        return {"status": "unchanged", "version_no": prev["version_no"], "id": str(prev["id"]), "message": "Nothing the forecast depends on has changed, so no new version was stored."}
    snap_row = conn.execute(
        """insert into football_feature_snapshots (workspace_id, fixture_date, home_team, away_team, cutoff, features, availability, warnings, sha256) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
           on conflict (workspace_id, home_team, away_team, fixture_date, cutoff, sha256) do update set sha256=excluded.sha256 returning id""",
        (wid, ko, fx["home_team"], fx["away_team"], cutoff, json.dumps(snap["features"], default=str), json.dumps(snap["availability"]), json.dumps(snap["warnings"]), snap["sha256"])).fetchone()
    rel = fi.reliability(fc, snap, api._calibration(run))
    warnings = list(snap["warnings"])
    last = snap.get("history_as_of")
    if last and (now.date() - datetime.fromisoformat(last).date()).days > HISTORY_STALE_DAYS:
        warnings.append(f"The newest imported result is from {last}; results since then are not reflected.")
    if not api._settings(run)["tuned"]:
        warnings.append("No backtest has been run on this history, so the model settings are untuned defaults.")
    drivers = fc[name].get("drivers") or goal.get("drivers") or []
    cur = conn.execute("""insert into football_prediction_versions (workspace_id, fixture_id, version_no, model_version_id, model_name, goal_model, snapshot_id, input_sha256, generated_at, kickoff_utc,
                              checkpoint, refresh_reason, p_home, p_draw, p_away, expected_home, expected_away, p_over_2_5, p_btts, top_scorelines, drivers, warnings, completeness, provider_refs, change_from_previous)
                          values (%s,%s,coalesce((select max(version_no) from football_prediction_versions where fixture_id=%s),0)+1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                          returning id, version_no""",
                       (wid, fx["id"], fx["id"], mv, name, "dixon_coles", snap_row["id"], sha, now, fx["kickoff_utc"], checkpoint, reason[:300], probs[0], probs[1], probs[2],
                        goal["expected_goals"][0], goal["expected_goals"][1], goal["p_over_2_5"], goal["p_btts"], json.dumps(goal["top_scorelines"][:5]), json.dumps(drivers, default=str),
                        json.dumps(warnings), json.dumps(rel["data_completeness"]), json.dumps(_provider_refs(conn, fx, snap, now), default=str), json.dumps(_change(prev, probs)))).fetchone()
    mark_official(conn, str(fx["id"]))
    return {"status": "created", "version_no": cur["version_no"], "id": str(cur["id"]), "significant_change": bool((_change(prev, probs) or {}).get("significant"))}


def mark_official(conn, fixture_id: str) -> None:
    """The official evaluation forecast is the latest version generated before the fixture's current kickoff."""
    r = conn.execute("""select v.id from football_prediction_versions v join football_fixtures f on f.id=v.fixture_id
                        where v.fixture_id=%s and v.generated_at < f.kickoff_utc order by v.version_no desc limit 1""", (fixture_id,)).fetchone()
    conn.execute("update football_prediction_versions set is_official=false where fixture_id=%s and is_official and id is distinct from %s", (fixture_id, r["id"] if r else None))
    if r:
        conn.execute("update football_prediction_versions set is_official=true where id=%s and not is_official", (r["id"],))


def generate_pending(conn, workspace_id: str, now: datetime | None = None, days: int = 14, limit: int = 10, max_seconds: float = 40.0) -> dict:
    """First forecast for scheduled fixtures that have none. Bounded in number and time so a scheduled run always finishes."""
    now = now or datetime.now(timezone.utc)
    fx = conn.execute("""select * from football_fixtures f where workspace_id=%s and status='scheduled' and kickoff_utc > %s and kickoff_utc <= %s
                           and not exists (select 1 from football_prediction_versions v where v.fixture_id=f.id) order by kickoff_utc limit %s""",
                      (workspace_id, now, now + timedelta(days=days), limit)).fetchall()
    out = {"considered": len(fx), "created": 0, "ineligible": [], "deferred": 0}
    if not fx:
        return out
    loaded, start = _load(conn, workspace_id), time.monotonic()
    for i, f in enumerate(fx):
        if time.monotonic() - start > max_seconds:
            out["deferred"] = len(fx) - i
            break
        r = generate_version(conn, f, "discovery", "The fixture was discovered.", now, loaded)
        if r["status"] == "created":
            out["created"] += 1
        elif r["status"] == "ineligible":
            out["ineligible"].append({"fixture_id": str(f["id"]), "home": f["home_team"], "away": f["away_team"], "reason": r["reason"]})
    return out


# ---- presentation --------------------------------------------------------------------------------------------------------------------

def present(v: dict) -> dict:
    probs = [v["p_home"], v["p_draw"], v["p_away"]]
    pct = percentages(probs)
    return {"id": str(v["id"]), "version_no": v["version_no"], "official": v["is_official"], "generated_at": v["generated_at"], "kickoff_utc": v["kickoff_utc"],
            "checkpoint": v["checkpoint"], "refresh_reason": v["refresh_reason"], "model": v["model_name"], "goal_model": v["goal_model"],
            "probabilities": {"home": probs[0], "draw": probs[1], "away": probs[2]}, "percent": {"home": pct[0], "draw": pct[1], "away": pct[2]},
            "expected_goals": {"home": v["expected_home"], "away": v["expected_away"]},
            "goals": {"over_2_5": v["p_over_2_5"], "under_2_5": None if v["p_over_2_5"] is None else round(1 - v["p_over_2_5"], 6), "both_teams_to_score": v["p_btts"]},
            "top_scorelines": v["top_scorelines"], "drivers": v["drivers"], "warnings": v["warnings"], "data_completeness": v["completeness"], "provider_refs": v["provider_refs"],
            "change_from_previous": v["change_from_previous"], "label": LABEL}
