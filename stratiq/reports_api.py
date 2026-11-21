"""Workspace evidence report: where the data came from, what was measured, and what has been forecast, in three separate sections.

Every number is read from stored records (imports, backtest runs, tracked forecasts). Nothing is estimated or filled in here, and a part
with no records says so instead of showing a figure. Historical evaluation (backtests on past matches) is kept apart from forecasts
(tracked predictions made before a match, scored after it).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from . import football_backtest as fb
from .db import get_conn
from .football_api import _plain, _stored
from .football_intel_api import COMPETITION, _latest_run
from .security import Auth

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])
SHOWN = ("frequency", "elo", "dixon_coles", "gbm", "ensemble")


def _metrics(res: dict | None) -> list[dict]:
    out = []
    for name in SHOWN:
        m = (res or {}).get(name)
        if not m:
            continue
        x = m["1x2"]
        gain = (m.get("gain") or {}).get("vs_frequency") or {}
        out.append({"model": fb.MODELS[name], "matches": x["n"], "log_loss": x["log_loss"], "brier": x["brier"], "accuracy": x.get("accuracy"), "calibration_gap": x.get("calibration_error"),
                    "gain_vs_frequency": gain.get("log_loss_gain"), "gain_standard_error": gain.get("standard_error"), "gain_clear": gain.get("clear")})
    return out


@router.get("/evidence")
def evidence(p: Auth, conn=Depends(get_conn)):
    wid = p.workspace_id
    ws = conn.execute("select name from workspaces where id=%s", (wid,)).fetchone()
    stored = _stored(conn, wid, COMPETITION)
    ms = _plain(stored)
    seasons = sorted({s for s, *_ in stored})
    sources = conn.execute(
        "select kind, name, provider, reference, licence_note, coverage, created_at from football_data_sources where workspace_id=%s order by created_at desc limit 30", (wid,)).fetchall()
    uploads = conn.execute("select kind, name, row_count, sha256, created_at from datasets where workspace_id=%s order by created_at desc limit 30", (wid,)).fetchall()
    run = _latest_run(conn, p)
    rolling = _latest_run(conn, p, "rolling")
    evaluation: dict = {"chronological": None, "rolling": None}
    if run:
        versions = conn.execute("select name, version, trained_through, data_sha256, created_at from football_model_versions where workspace_id=%s and backtest_run_id=%s order by name", (wid, run["id"])).fetchall()
        current = fb.data_sha(sorted(ms, key=lambda m: (m[0], m[1], m[2]))) if ms else None
        evaluation["chronological"] = {
            "run_id": str(run["id"]), "created_at": run["created_at"], "matches": run["matches"], "data_sha256": run["data_sha256"], "history_changed_since": current != run["data_sha256"],
            "split": (run["config"] or {}).get("split"), "periods": (run["config"] or {}).get("periods"), "model_version": (run["config"] or {}).get("model_version"),
            "test": _metrics((run["results"] or {}).get("test")), "validation": _metrics((run["results"] or {}).get("validation")), "warnings": run["warnings"] or [], "versions": versions}
    if rolling:
        evaluation["rolling"] = {"run_id": str(rolling["id"]), "created_at": rolling["created_at"], "matches": rolling["matches"], "seasons_predicted": (rolling["config"] or {}).get("seasons_predicted"),
                                 "results": _metrics((rolling["results"] or {}).get("rolling")), "warnings": rolling["warnings"] or []}
    live = conn.execute(
        """select v.name model, v.version, count(*) n, avg(o.log_loss) log_loss, avg(o.brier) brier, avg(case when o.correct then 1.0 else 0.0 end) accuracy, min(pr.fixture_date) first, max(pr.fixture_date) last
           from football_predictions pr join football_model_versions v on v.id=pr.model_version_id join football_prediction_outcomes o on o.prediction_id=pr.id
           where pr.workspace_id=%s and pr.kind='live' group by v.name, v.version order by v.name""", (wid,)).fetchall()
    waiting = conn.execute("select count(*) n from football_predictions pr left join football_prediction_outcomes o on o.prediction_id=pr.id where pr.workspace_id=%s and pr.kind='live' and o.prediction_id is null", (wid,)).fetchone()["n"]
    counts = conn.execute(
        """select (select count(*) from predictions where workspace_id=%(w)s) predictions, (select count(*) from strategic_scenarios where workspace_id=%(w)s) scenarios,
                  (select count(*) from simulation_runs where workspace_id=%(w)s) simulations""", {"w": wid}).fetchone()
    return {
        "workspace": ws["name"] if ws else None, "generated_at": datetime.now(timezone.utc).isoformat(),
        "data": {"matches": len(ms), "seasons": seasons, "first": ms[0][0].isoformat() if ms else None, "last": ms[-1][0].isoformat() if ms else None,
                 "data_sha256": fb.data_sha(sorted(ms, key=lambda m: (m[0], m[1], m[2]))) if ms else None, "sources": sources, "uploads": uploads},
        "historical_evaluation": evaluation,
        "forecasts": {"scored": live, "waiting_for_results": waiting,
                      "note": "Forecasts made before a match and scored after it. These are separate from the backtests above, which replay past matches."},
        "saved_work": counts,
        "statements": ["Every figure in this report is read from stored records. Nothing is estimated for the report itself.",
                       "A backtest measures how a model would have done on past matches. It does not promise future accuracy.",
                       "Models use match results only unless other data was uploaded; injuries, odds and expected goals are not used by default.",
                       "This is analysis, not betting, financial or legal advice."],
    }
