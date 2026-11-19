"""Workspace library, reports and exports, plus workspace management.

Everything is scoped to the caller's workspace (or, for workspace management, to the caller's own memberships)."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, StringConstraints

from . import explain as ex
from .db import get_conn
from .facts_loader import load_facts
from .security import Auth

router = APIRouter(prefix="/api/v1/library", tags=["library"])
MAX_EXPORT_ITEMS = 1000


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ------------------------------------------------------------------ library listing
@router.get("/items")
def items(p: Auth, conn=Depends(get_conn), q: Annotated[str | None, Query(max_length=100)] = None,
          type: Literal["prediction", "scenario", "simulation"] | None = None, limit: int = Query(200, ge=1, le=500)):
    like = f"%{q}%" if q else None
    rows = conn.execute(
        """select * from (
             select 'prediction' as type, 'sports' as module, 'prediction' as kind, p.id,
                    coalesce(p.inputs->>'home_name', p.inputs->>'home_team') || ' vs ' || coalesce(p.inputs->>'away_name', p.inputs->>'away_team') as title,
                    p.created_at, u.name created_by_name, 'completed' as status
               from predictions p join users u on u.id=p.user_id where p.workspace_id=%(w)s
             union all
             select 'scenario', s.domain, coalesce(s.definition->>'kind', 'business'), s.id, s.title, s.created_at, u.name, 'saved'
               from strategic_scenarios s join users u on u.id=s.created_by where s.workspace_id=%(w)s
             union all
             select 'simulation', 'simulation', 'monte_carlo', r.id, r.title, r.created_at, u.name, r.status
               from simulation_runs r join users u on u.id=r.created_by where r.workspace_id=%(w)s
           ) x
           where (%(t)s::text is null or x.type=%(t)s) and (%(q)s::text is null or x.title ilike %(q)s)
           order by x.created_at desc limit %(l)s""",
        {"w": p.workspace_id, "t": type, "q": like, "l": limit},
    ).fetchall()
    return {"items": rows}


# ------------------------------------------------------------------ reports
@router.get("/report")
def report(p: Auth, type: Literal["prediction", "simulation", "scenario"], id: uuid.UUID, format: Literal["md", "html", "json"] = "html", conn=Depends(get_conn)):
    facts, meta = load_facts(conn, p, type, id)
    gen = _now()
    slug = re.sub(r"[^a-z0-9]+", "-", meta["title"].lower()).strip("-")[:50] or "report"
    if format == "md":
        body, media, disp = ex.report_markdown(facts, gen), "text/markdown", "attachment"
    elif format == "json":
        body, media, disp = ex.report_json(facts, gen), "application/json", "attachment"
    else:
        body, media, disp = ex.report_html(facts, gen), "text/html", "inline"  # opens in a tab; use the browser's Print to save a PDF
    conn.execute("insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'report.export',%s)",
                 (p.workspace_id, p.user_id, json.dumps({"type": type, "id": str(id), "format": format})))
    return Response(body, media_type=f"{media}; charset=utf-8", headers={"Content-Disposition": f'{disp}; filename="{slug}.{format}"', "X-Content-Type-Options": "nosniff"})


# ------------------------------------------------------------------ whole-workspace export
@router.get("/export")
def export_workspace(p: Auth, conn=Depends(get_conn)):
    ws = conn.execute("select id, name, created_at from workspaces where id=%s", (p.workspace_id,)).fetchone()
    preds = conn.execute(
        """select p.id, p.created_at, p.feature_cutoff, p.inputs, p.outputs, p.assumptions, p.input_hash, mv.name model, mv.version model_version
           from predictions p join model_versions mv on mv.id=p.model_version_id where p.workspace_id=%s order by p.created_at desc limit %s""",
        (p.workspace_id, MAX_EXPORT_ITEMS)).fetchall()
    scen = conn.execute(
        """select s.id, s.title, s.domain, s.created_at, s.definition, m.matrix, m.solution
           from strategic_scenarios s left join payoff_matrices m on m.scenario_id=s.id where s.workspace_id=%s order by s.created_at desc limit %s""",
        (p.workspace_id, MAX_EXPORT_ITEMS)).fetchall()
    runs = conn.execute(
        "select id, title, domain, status, seed, iterations, config, result, error, created_at, finished_at from simulation_runs where workspace_id=%s order by created_at desc limit %s",
        (p.workspace_id, MAX_EXPORT_ITEMS)).fetchall()
    bundle = {
        "format": "stratiq-workspace-export", "version": 1, "generated": _now(), "workspace": {"id": str(ws["id"]), "name": ws["name"]},
        "notice": "Exported from STRATIQ AI. Contains only this workspace's saved work. Assumptions and model versions are included so results can be reproduced.",
        "counts": {"predictions": len(preds), "scenarios": len(scen), "simulation_runs": len(runs)},
        "predictions": preds, "scenarios": scen, "simulation_runs": runs,
    }
    conn.execute("insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'workspace.export',%s)", (p.workspace_id, p.user_id, json.dumps(bundle["counts"])))
    slug = re.sub(r"[^a-z0-9]+", "-", ws["name"].lower()).strip("-")[:40] or "workspace"
    return Response(json.dumps(bundle, indent=2, default=str), media_type="application/json; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{slug}-export.json"'})


# ------------------------------------------------------------------ workspace management (caller's own memberships)
ws_router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])
WsName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class CreateWs(BaseModel):
    name: WsName


class ActivateWs(BaseModel):
    workspace_id: uuid.UUID


@ws_router.get("")
def my_workspaces(p: Auth, conn=Depends(get_conn)):
    rows = conn.execute(
        """select w.id, w.name, m.role, w.created_at, (w.id = u.active_workspace_id) as active
           from workspace_members m join workspaces w on w.id=m.workspace_id join users u on u.id=m.user_id
           where m.user_id=%s order by w.created_at""",
        (p.user_id,),
    ).fetchall()
    return {"workspaces": rows, "current": p.workspace_id}


@ws_router.post("", status_code=201)
def create_workspace(body: CreateWs, p: Auth, conn=Depends(get_conn)):
    w = conn.execute("insert into workspaces (name) values (%s) returning id, name", (body.name,)).fetchone()
    conn.execute("insert into workspace_members (workspace_id,user_id,role) values (%s,%s,'owner')", (w["id"], p.user_id))
    conn.execute("update users set active_workspace_id=%s where id=%s", (w["id"], p.user_id))
    conn.execute("insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'workspace.create',%s)", (w["id"], p.user_id, json.dumps({"name": body.name})))
    return {"id": w["id"], "name": w["name"], "role": "owner"}


@ws_router.post("/activate")
def activate(body: ActivateWs, p: Auth, conn=Depends(get_conn)):
    # Membership is verified here, against the database, for the workspace being switched TO.
    m = conn.execute("select role from workspace_members where workspace_id=%s and user_id=%s", (body.workspace_id, p.user_id)).fetchone()
    if not m:
        raise HTTPException(403, "You are not a member of that workspace")
    conn.execute("update users set active_workspace_id=%s where id=%s", (body.workspace_id, p.user_id))
    conn.execute("insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'workspace.switch',%s)", (body.workspace_id, p.user_id, json.dumps({"from": p.workspace_id})))
    return {"active": body.workspace_id, "role": m["role"]}
