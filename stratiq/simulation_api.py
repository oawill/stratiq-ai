"""Simulation Lab endpoints: validate, run asynchronously, poll, cancel, compare, export."""
from __future__ import annotations

import json
import os
import re
import secrets
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, StringConstraints

from . import simulation as sim
from .db import get_conn
from .security import ADMIN_ROLES, Auth, require_write
from .simulation_runner import execute_run, fail_stale, start_in_thread

router = APIRouter(prefix="/api/v1/simulations", tags=["simulations"])

# Module-level so tests can substitute a synchronous launcher.
launch = start_in_thread

Domain = Literal["general", "business", "finance", "politics", "sports"]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class VarIn(BaseModel):
    name: str = Field(max_length=40)
    dist: dict[str, Any]
    label: str | None = Field(None, max_length=80)


class OutIn(BaseModel):
    name: str = Field(max_length=40)
    expr: str = Field(max_length=sim.MAX_EXPR_LEN + 100)
    threshold: float | None = None


class ModelBody(BaseModel):
    variables: list[VarIn] = Field(min_length=1, max_length=sim.MAX_VARS)
    outputs: list[OutIn] = Field(min_length=1, max_length=sim.MAX_OUTPUTS)


class RunBody(ModelBody):
    title: Title
    domain: Domain = "general"
    iterations: int = Field(ge=sim.MIN_ITER, le=sim.MAX_ITER)
    seed: int | None = Field(None, ge=0, lt=2**31)
    notes: Annotated[str, StringConstraints(max_length=2000)] | None = None


class ValidateBody(ModelBody):
    seed: int = Field(0, ge=0, lt=2**31)


class CompareBody(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=2, max_length=4)


def _cfg(body: ModelBody, iterations: int, seed: int) -> sim.Config:
    try:
        return sim.parse_config(
            iterations, seed,
            [{"name": v.name, "dist": v.dist} for v in body.variables],
            [{"name": o.name, "expr": o.expr, "threshold": o.threshold} for o in body.outputs],
        )
    except sim.ConfigError as e:
        raise HTTPException(422, str(e))


def _pilot(cfg: sim.Config) -> dict:
    try:
        return sim.pilot(cfg)
    except sim.SimulationError as e:
        raise HTTPException(422, f"The model fails when run: {e}")


@router.post("/validate")
def validate(body: ValidateBody, p: Auth):
    """Checks the model and runs 200 throw-away draws. Nothing is stored."""
    return {"ok": True, "pilot": _pilot(_cfg(body, sim.MIN_ITER, body.seed))}


@router.post("/runs", status_code=201)
def create_run(body: RunBody, background: BackgroundTasks, p: Auth, conn=Depends(get_conn)):
    require_write(p)
    seed = body.seed if body.seed is not None else secrets.randbelow(2**31)
    cfg = _cfg(body, body.iterations, seed)
    _pilot(cfg)  # fail fast on a broken model instead of after a long wait
    config = {
        "variables": [v.model_dump() for v in body.variables],
        "outputs": [o.model_dump() for o in body.outputs],
        "notes": body.notes,
    }
    row = conn.execute(
        """insert into simulation_runs (workspace_id, created_by, domain, config, seed, iterations, title, status, progress)
           values (%s,%s,%s,%s,%s,%s,%s,'queued',0) returning id, created_at""",
        (p.workspace_id, p.user_id, body.domain, json.dumps(config), seed, body.iterations, body.title),
    ).fetchone()
    conn.execute(
        "insert into activity_history (workspace_id,user_id,kind,summary,ref_type,ref_id) values (%s,%s,'simulation.started',%s,'simulation',%s)",
        (p.workspace_id, p.user_id, f"Started simulation: {body.title}", str(row["id"])),
    )
    conn.execute(
        "insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'simulation.create',%s)",
        (p.workspace_id, p.user_id, json.dumps({"run_id": str(row["id"]), "iterations": body.iterations, "seed": seed})),
    )
    if os.environ.get("VERCEL") or os.environ.get("SIMULATION_INLINE") == "1":
        # Serverless hosts freeze a function once it has responded, so a background thread would strand the job.
        # Run it inside this request instead (runs are capped at 200,000 iterations, a few seconds of work).
        execute_run(conn, str(row["id"]))
    else:
        background.add_task(launch, str(row["id"]))  # runs after the transaction has committed
    return {"id": row["id"], "status": "queued", "seed": seed, "created_at": row["created_at"]}


LIST_COLS = """r.id, r.title, r.domain, r.status, r.progress, r.iterations, r.seed, r.created_at, r.finished_at, u.name created_by_name"""


@router.get("/runs")
def list_runs(p: Auth, conn=Depends(get_conn), limit: int = Query(50, ge=1, le=200)):
    fail_stale(conn, p.workspace_id)
    rows = conn.execute(
        f"select {LIST_COLS} from simulation_runs r join users u on u.id=r.created_by "
        "where r.workspace_id=%s order by r.created_at desc limit %s",
        (p.workspace_id, limit),
    ).fetchall()
    return {"runs": rows}


def _get(conn, p, run_id: uuid.UUID):
    row = conn.execute(
        f"select {LIST_COLS}, r.config, r.result, r.error, r.started_at, r.created_by "
        "from simulation_runs r join users u on u.id=r.created_by where r.id=%s and r.workspace_id=%s",
        (run_id, p.workspace_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Run not found")  # same answer for missing and other-workspace
    return row


@router.get("/runs/{run_id}")
def get_run(run_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    fail_stale(conn, p.workspace_id)
    row = _get(conn, p, run_id)
    row.pop("created_by", None)
    return row


@router.post("/runs/{run_id}/cancel")
def cancel(run_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    require_write(p)
    row = _get(conn, p, run_id)
    if row["status"] not in ("queued", "running"):
        raise HTTPException(409, f"This run is already {row['status']}")
    conn.execute(
        "update simulation_runs set status='cancelled', finished_at=now() where id=%s and workspace_id=%s and status in ('queued','running')",
        (run_id, p.workspace_id),
    )
    conn.execute(
        "insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'simulation.cancel',%s)",
        (p.workspace_id, p.user_id, json.dumps({"run_id": str(run_id)})),
    )
    return {"id": run_id, "status": "cancelled"}


@router.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    require_write(p)
    row = _get(conn, p, run_id)
    if str(row["created_by"]) != p.user_id and p.role not in ADMIN_ROLES:
        raise HTTPException(403, "Only the author or a workspace admin can delete a run")
    if row["status"] in ("queued", "running"):
        raise HTTPException(409, "Cancel the run before deleting it")
    conn.execute("delete from simulation_runs where id=%s and workspace_id=%s", (run_id, p.workspace_id))
    conn.execute(
        "insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'simulation.delete',%s)",
        (p.workspace_id, p.user_id, json.dumps({"run_id": str(run_id), "title": row["title"]})),
    )


@router.post("/compare")
def compare(body: CompareBody, p: Auth, conn=Depends(get_conn)):
    ids = list(dict.fromkeys(body.ids))
    if len(ids) < 2:
        raise HTTPException(422, "Choose at least two different runs")
    runs = [_get(conn, p, i) for i in ids]
    bad = [r["title"] for r in runs if r["status"] != "completed"]
    if bad:
        raise HTTPException(409, f"Only completed runs can be compared (not completed: {', '.join(bad)})")
    out = sim.compare([r["result"] for r in runs], [r["title"] for r in runs])
    out["runs"] = [{"id": r["id"], "title": r["title"], "domain": r["domain"], "iterations": r["iterations"], "seed": r["seed"],
                    "histograms": {k: v["histogram"] for k, v in r["result"]["outputs"].items()}} for r in runs]
    return out


@router.get("/runs/{run_id}/report")
def report(run_id: uuid.UUID, p: Auth, conn=Depends(get_conn), format: Literal["json", "csv", "md"] = "md"):
    row = _get(conn, p, run_id)
    if row["status"] != "completed":
        raise HTTPException(409, "Only completed runs can be exported")
    slug = re.sub(r"[^a-z0-9]+", "-", row["title"].lower()).strip("-")[:50] or "simulation"
    result, config = row["result"], row["config"]
    if format == "json":
        body = json.dumps({"title": row["title"], "domain": row["domain"], "config": config, "result": result}, indent=2)
        media = "application/json"
    elif format == "csv":
        body, media = sim.report_csv(row["title"], result), "text/csv"
    else:
        body, media = sim.report_markdown(row["title"], row["domain"], {"iterations": row["iterations"], "seed": row["seed"], **config}, result), "text/markdown"
    conn.execute(
        "insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'simulation.export',%s)",
        (p.workspace_id, p.user_id, json.dumps({"run_id": str(run_id), "format": format})),
    )
    return Response(body, media_type=f"{media}; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{slug}.{format}"'})
