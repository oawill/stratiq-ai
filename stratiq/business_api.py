"""Business Strategy endpoints: deterministic game-theory solving and saved scenarios."""
from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StringConstraints, model_validator

from . import gametheory as gt
from .db import get_conn
from .security import ADMIN_ROLES, Auth, require_write

router = APIRouter(prefix="/api/v1/business", tags=["business"])

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Payoffs = list[list[list[float]]]


class MatrixBody(BaseModel):
    row_strategies: list[Name] = Field(min_length=2, max_length=gt.MAX_STRATEGIES)
    col_strategies: list[Name] = Field(min_length=2, max_length=gt.MAX_STRATEGIES)
    payoffs: Payoffs


class ScenarioBody(MatrixBody):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    notes: Annotated[str, StringConstraints(max_length=2000)] | None = None
    players: list[Name] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def _distinct_players(self):
        if self.players[0] == self.players[1]:
            raise ValueError("the two players must have different names")
        return self


class SensitivityBody(MatrixBody):
    row: int = Field(ge=0, lt=gt.MAX_STRATEGIES)
    col: int = Field(ge=0, lt=gt.MAX_STRATEGIES)
    player: str = Field(pattern="^(row|col)$")
    lo: float
    hi: float


class CompareBody(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=2, max_length=4)


def _game(body: MatrixBody) -> gt.Game:
    try:
        return gt.build_game(body.row_strategies, body.col_strategies, body.payoffs)
    except gt.GameError as e:
        raise HTTPException(422, str(e))


@router.post("/solve")
def solve(body: MatrixBody, p: Auth):
    """Stateless analysis: nothing is stored."""
    return gt.analyse(_game(body))


@router.post("/sensitivity")
def sens(body: SensitivityBody, p: Auth):
    g = _game(body)
    try:
        return gt.sensitivity(g, body.row, body.col, body.player, body.lo, body.hi)
    except gt.GameError as e:
        raise HTTPException(422, str(e))


@router.post("/scenarios", status_code=201)
def save_scenario(body: ScenarioBody, p: Auth, conn=Depends(get_conn)):
    require_write(p)
    analysis = gt.analyse(_game(body))
    definition = {
        "players": body.players,
        "row_strategies": body.row_strategies,
        "col_strategies": body.col_strategies,
        "notes": body.notes,
    }
    sid = conn.execute(
        "insert into strategic_scenarios (workspace_id, created_by, title, domain, definition) "
        "values (%s,%s,%s,'business',%s) returning id, created_at",
        (p.workspace_id, p.user_id, body.title, json.dumps(definition)),
    ).fetchone()
    conn.execute(
        "insert into payoff_matrices (scenario_id, workspace_id, matrix, solution) values (%s,%s,%s,%s)",
        (sid["id"], p.workspace_id, json.dumps(body.payoffs), json.dumps(analysis)),
    )
    conn.execute(
        "insert into activity_history (workspace_id,user_id,kind,summary,ref_type,ref_id) "
        "values (%s,%s,'scenario.created',%s,'scenario',%s)",
        (p.workspace_id, p.user_id, f"Saved strategic scenario: {body.title}", str(sid["id"])),
    )
    conn.execute(
        "insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'scenario.create',%s)",
        (p.workspace_id, p.user_id, json.dumps({"scenario_id": str(sid["id"])})),
    )
    return {"id": sid["id"], "created_at": sid["created_at"], "analysis": analysis}


@router.get("/scenarios")
def list_scenarios(p: Auth, conn=Depends(get_conn), limit: int = Query(50, ge=1, le=200)):
    rows = conn.execute(
        """select s.id, s.title, s.created_at, u.name created_by_name,
                  s.definition->'players' players,
                  jsonb_array_length(s.definition->'row_strategies') rows_n,
                  jsonb_array_length(s.definition->'col_strategies') cols_n,
                  jsonb_array_length(m.solution->'pure_nash') nash_n
           from strategic_scenarios s
           join users u on u.id = s.created_by
           left join payoff_matrices m on m.scenario_id = s.id
           where s.workspace_id=%s and s.domain='business'
           order by s.created_at desc limit %s""",
        (p.workspace_id, limit),
    ).fetchall()
    return {"scenarios": rows}


def _load(conn, p, sid: uuid.UUID):
    row = conn.execute(
        """select s.id, s.title, s.created_at, s.created_by, s.definition, m.matrix
           from strategic_scenarios s join payoff_matrices m on m.scenario_id = s.id
           where s.id=%s and s.workspace_id=%s""",
        (sid, p.workspace_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Scenario not found")  # identical for missing and other-workspace
    return row


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    row = _load(conn, p, scenario_id)
    d = row["definition"]
    analysis = gt.analyse(gt.build_game(d["row_strategies"], d["col_strategies"], row["matrix"]))
    return {"id": row["id"], "title": row["title"], "created_at": row["created_at"], **d, "payoffs": row["matrix"], "analysis": analysis}


@router.post("/compare")
def compare(body: CompareBody, p: Auth, conn=Depends(get_conn)):
    out = []
    for sid in dict.fromkeys(body.ids):
        row = _load(conn, p, sid)
        d = row["definition"]
        g = gt.build_game(d["row_strategies"], d["col_strategies"], row["matrix"])
        a = gt.analyse(g)

        def nm(cell):
            return {"row": d["row_strategies"][cell["row"]], "col": d["col_strategies"][cell["col"]]}

        dom = a["dominance"]
        out.append({
            "id": row["id"], "title": row["title"], "players": d["players"],
            "row_strategies": d["row_strategies"], "col_strategies": d["col_strategies"],
            "pure_nash": [{**nm(n), "payoffs": n["payoffs"]} for n in a["pure_nash"]],
            "row_dominant": d["row_strategies"][dom["row"]["strictly_dominant"]] if dom["row"]["strictly_dominant"] is not None else None,
            "col_dominant": d["col_strategies"][dom["col"]["strictly_dominant"]] if dom["col"]["strictly_dominant"] is not None else None,
            "max_welfare": {"value": a["max_welfare"]["value"], "cells": [nm(c) for c in a["max_welfare"]["cells"]]},
            "mixed_2x2": a["mixed_2x2"],
            "notes": a["notes"],
        })
    if len(out) < 2:
        raise HTTPException(422, "Choose at least two different scenarios")
    return {"scenarios": out}


@router.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    require_write(p)
    row = _load(conn, p, scenario_id)
    if str(row["created_by"]) != p.user_id and p.role not in ADMIN_ROLES:
        raise HTTPException(403, "Only the author or a workspace admin can delete a scenario")
    conn.execute("delete from strategic_scenarios where id=%s and workspace_id=%s", (scenario_id, p.workspace_id))
    conn.execute(
        "insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'scenario.delete',%s)",
        (p.workspace_id, p.user_id, json.dumps({"scenario_id": str(scenario_id), "title": row["title"]})),
    )
    conn.execute(
        "insert into activity_history (workspace_id,user_id,kind,summary) values (%s,%s,'scenario.deleted',%s)",
        (p.workspace_id, p.user_id, f"Deleted strategic scenario: {row['title']}"),
    )
