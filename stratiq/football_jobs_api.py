"""Football jobs API: monitoring status, manual runs, and the endpoint a scheduler calls.

The scheduler endpoint is protected by the shared secret in CRON_SECRET (a scheduler such as Vercel Cron sends it as `Authorization: Bearer ...`).
Without that variable set the endpoint does not exist, so nothing can trigger it by accident.
"""
from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from . import football_jobs as jobs
from .db import get_conn
from .security import Auth, require_write

router = APIRouter(prefix="/api/v1/football/jobs", tags=["football-jobs"])


class RetrainBody(BaseModel):
    force: bool = False


@router.get("/status")
def status(p: Auth, conn=Depends(get_conn)):
    """Drift report, whether a retrain is due, and the recent job runs for this workspace."""
    runs = conn.execute("select id, kind, trigger, status, detail, started_at, finished_at from football_job_runs where workspace_id=%s order by started_at desc limit 10", (p.workspace_id,)).fetchall()
    return {"monitor": jobs.monitor(conn, p.workspace_id), "runs": runs, "scheduler_configured": len(os.environ.get("CRON_SECRET", "")) >= 16}


@router.post("/monitor")
def run_monitor(p: Auth, conn=Depends(get_conn)):
    require_write(p)
    started = datetime.now(timezone.utc)
    scored = jobs.football_store.reconcile(conn, p.workspace_id)
    out = {"scored": scored, "monitor": jobs.monitor(conn, p.workspace_id)}
    jobs.record(conn, p.workspace_id, "monitor", "manual", "complete", out, started)
    return out


@router.post("/retrain")
def run_retrain(body: RetrainBody, p: Auth, conn=Depends(get_conn)):
    """Retrain now if the policy says it is due, or regardless when `force` is true. Takes up to a minute on ten seasons."""
    require_write(p)
    started = datetime.now(timezone.utc)
    out = jobs.retrain(conn, p.workspace_id, body.force)
    jobs.record(conn, p.workspace_id, "retrain", "manual", {"complete": "complete", "skipped": "skipped"}.get(out["status"], "failed"), {k: v for k, v in out.items() if k != "monitor"}, started)
    return out


@router.post("/scheduled")
def scheduled(authorization: Annotated[str | None, Header()] = None, conn=Depends(get_conn)):
    """Called by a scheduler: one cycle for every workspace with match history."""
    secret = os.environ.get("CRON_SECRET", "")
    if len(secret) < 16:
        raise HTTPException(404, "Not found")
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token.encode(), secret.encode()):
        raise HTTPException(401, "Unauthorized")
    return jobs.run_all(conn, "schedule")


# Vercel Cron issues GET requests.
router.add_api_route("/scheduled", scheduled, methods=["GET"], include_in_schema=False)
