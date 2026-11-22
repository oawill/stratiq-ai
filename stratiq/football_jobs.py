"""Scheduled and manual football jobs: score finished forecasts, forecast upcoming fixtures, monitor drift, retrain when due.

A job never changes what is live by itself, except through the retraining policy in `football_monitor`: a retrain is attempted only when
the policy says it is due (or a person forces it), and its result replaces the current settings only if it is not clearly worse.
Every run is recorded in `football_job_runs`, and a retrain's full results are kept as a normal backtest run whether accepted or not.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi import HTTPException

from . import football_backtest as fb
from . import football_intel_api as api
from . import football_monitor as mon
from . import football_provider, football_store, football_sync
from .football_history import season_label


def system_principal(workspace_id: str):
    """A stand-in for a person when a job runs on a schedule: no user id, so stored rows record no author."""
    return SimpleNamespace(workspace_id=workspace_id, user_id=None, role="system")


def rolling_split(ms: list) -> dict:
    """The newest three seasons are validation and test, everything earlier is training. Used for retraining, so new seasons move the split forward."""
    seasons = sorted({season_label(m[0]) for m in ms})
    if len(seasons) < fb.MIN_SEASONS:
        raise ValueError(f"At least {fb.MIN_SEASONS} seasons are needed to retrain; {len(seasons)} are imported.")
    return {"training": seasons[:-3], "validation": [seasons[-3]], "test": seasons[-2:]}


def _model_for(run) -> str:
    return "ensemble" if run and run["tuning"] and run["tuning"].get("ensemble") else "dixon_coles"


def monitor(conn, workspace_id: str, today: date | None = None) -> dict:
    """Drift report and retraining decision for one workspace."""
    today = today or datetime.now(timezone.utc).date()
    p = system_principal(workspace_id)
    ms = api._plain(api._stored(conn, workspace_id, api.COMPETITION))
    run = api._latest_run(conn, p)
    if not ms:
        return {"has_history": False, "drift": {"status": "insufficient", "note": "No match history is imported."}, "retrain": {"retrain": False, "reasons": []}}
    model = _model_for(run)
    baseline, scored = None, []
    if run:
        losses = [r["log_loss"] for r in conn.execute(
            """select o.log_loss from football_predictions pr join football_model_versions v on v.id=pr.model_version_id join football_prediction_outcomes o on o.prediction_id=pr.id
               where pr.backtest_run_id=%s and pr.period='test' and v.name=%s""", (run["id"], model)).fetchall()]
        baseline = mon.baseline_from(losses)
        scored = [{"log_loss": r["log_loss"], "p_home": r["p_home"], "home_win": r["outcome"] == 0} for r in conn.execute(
            """select o.log_loss, pr.p_home, o.outcome from football_predictions pr join football_model_versions v on v.id=pr.model_version_id
               join football_prediction_outcomes o on o.prediction_id=pr.id where pr.workspace_id=%s and pr.kind='live' and v.name=%s order by pr.fixture_date, pr.created_at""",
            (workspace_id, model)).fetchall()]
    drift = mon.drift_report(scored, baseline)
    since = max(0, len(ms) - run["matches"]) if run else len(ms)
    age = (today - run["created_at"].date()).days if run else None
    decision = mon.retrain_decision(has_run=bool(run), matches_since_run=since, days_since_run=age, drift_status=drift["status"])
    return {"has_history": True, "model": model, "run_id": str(run["id"]) if run else None, "trained_on_matches": run["matches"] if run else None, "matches_now": len(ms),
            "matches_since_training": since, "days_since_training": age, "drift": drift, "retrain": decision}


def retrain(conn, workspace_id: str, force: bool = False, today: date | None = None) -> dict:
    state = monitor(conn, workspace_id, today)
    if not state["has_history"]:
        return {"status": "skipped", "reason": "No match history is imported.", "monitor": state}
    if not force and not state["retrain"]["retrain"]:
        return {"status": "skipped", "reason": "Retraining is not due.", "monitor": state}
    p = system_principal(workspace_id)
    ms = api._plain(api._stored(conn, workspace_id, api.COMPETITION))
    previous = api._latest_run(conn, p)
    try:
        res = fb.run_chronological(ms, rolling_split(sorted(ms, key=lambda m: (m[0], m[1], m[2]))))
    except ValueError as e:
        return {"status": "failed", "reason": str(e), "monitor": state}
    meta = api._store_run(conn, p, res, sorted(ms, key=lambda m: (m[0], m[1], m[2])))
    model = _model_for({"tuning": res.get("tuning")})
    new_ll = res["results"]["validation"].get(model, {}).get("1x2", {}).get("log_loss")
    old_ll = None
    if previous and previous["results"]:
        old_ll = previous["results"].get("validation", {}).get(model, {}).get("1x2", {}).get("log_loss")
    verdict = mon.accept_challenger(old_ll, new_ll)
    if not verdict["accept"]:
        conn.execute("update football_backtest_runs set status='rejected' where id=%s", (meta["id"],))
    conn.execute("insert into audit_logs (workspace_id,user_id,action,detail) values (%s,null,'football.retrain',%s)",
                 (workspace_id, json.dumps({"run_id": meta["id"], "forced": force, "accepted": verdict["accept"], "reasons": state["retrain"]["reasons"]})))
    return {"status": "complete", "run_id": meta["id"], "accepted": verdict["accept"], "verdict": verdict, "reasons": state["retrain"]["reasons"] or ["Forced by a person."],
            "split": res["split"], "model": model}


def forecast_upcoming(conn, workspace_id: str, days: int = 14, limit: int = 20, today: date | None = None) -> dict:
    """Store a tracked forecast for each upcoming fixture so it can be scored once the result arrives."""
    from datetime import timedelta
    today = today or datetime.now(timezone.utc).date()
    fx = conn.execute("select fixture_date, home_team, away_team from football_fixtures where status = 'scheduled' and (kickoff_utc is null or kickoff_utc > now()) and workspace_id=%s and fixture_date >= %s and fixture_date <= %s order by fixture_date limit %s",
                      (workspace_id, today, today + timedelta(days=days), limit)).fetchall()
    if not fx:
        return {"fixtures": 0, "forecast": 0, "errors": []}
    p = system_principal(workspace_id)
    ms = api._plain(api._stored(conn, workspace_id, api.COMPETITION))
    run = api._latest_run(conn, p)
    stats = football_store.load_stats(conn, workspace_id)
    done, errors = 0, []
    for r in fx:
        try:
            _, fc, snap, settings, data_sha, ko, cutoff = api._intelligence(conn, p, r["home_team"], r["away_team"], r["fixture_date"], None, ms, run, stats)
            api._persist_live(conn, p, snap, fc, settings, data_sha, ko, cutoff)
            done += 1
        except HTTPException as e:
            errors.append({"home": r["home_team"], "away": r["away_team"], "error": e.detail})
    return {"fixtures": len(fx), "forecast": done, "errors": errors}


def record(conn, workspace_id: str, kind: str, trigger: str, status: str, detail: dict, started: datetime) -> str:
    row = conn.execute("insert into football_job_runs (workspace_id, kind, trigger, status, detail, started_at, finished_at) values (%s,%s,%s,%s,%s,%s,now()) returning id",
                       (workspace_id, kind, trigger, status, json.dumps(detail, default=str), started)).fetchone()
    return str(row["id"])


def run_workspace(conn, workspace_id: str, trigger: str, allow_retrain: bool = True, today: date | None = None) -> dict:
    """One full cycle for a workspace: score finished forecasts, forecast what is coming, check drift, retrain if due."""
    started = datetime.now(timezone.utc)
    out: dict = {"workspace_id": workspace_id}
    try:
        out["scored"] = football_store.reconcile(conn, workspace_id)
        if football_provider.configured():       # a provider outage is reported here but never stops the rest of the cycle
            sy = football_sync.sync_workspace(conn, workspace_id, "schedule")
            out["live_sync"] = {k: sy.get(k) for k in ("status", "fetched", "created", "updated", "unchanged", "message")}
        out["upcoming"] = forecast_upcoming(conn, workspace_id, today=today)
        out["monitor"] = monitor(conn, workspace_id, today)
        out["retrain"] = retrain(conn, workspace_id, False, today) if allow_retrain else {"status": "skipped", "reason": "Another workspace was retrained in this run."}
        status = "complete" if out["retrain"]["status"] != "failed" else "failed"
    except Exception as e:  # noqa: BLE001 - one workspace failing must not stop the others
        out["error"] = f"{type(e).__name__}: {e}"
        status = "failed"
    record(conn, workspace_id, "scheduled", trigger, status, out, started)
    out["status"] = status
    return out


def run_all(conn, trigger: str = "schedule", max_retrains: int = 1, today: date | None = None) -> dict:
    """Every workspace with match history. At most `max_retrains` workspaces are retrained per call, because a retrain takes tens of seconds."""
    wids = [str(r["workspace_id"]) for r in conn.execute("select distinct workspace_id from match_history where competition=%s", (api.COMPETITION,)).fetchall()]
    results, retrained = [], 0
    for wid in wids:
        r = run_workspace(conn, wid, trigger, retrained < max_retrains, today)
        if r.get("retrain", {}).get("status") == "complete":
            retrained += 1
        results.append({k: r.get(k) for k in ("workspace_id", "status", "scored", "error")} | {"retrain": (r.get("retrain") or {}).get("status"), "drift": ((r.get("monitor") or {}).get("drift") or {}).get("status")})
    return {"workspaces": len(wids), "retrained": retrained, "results": results}
