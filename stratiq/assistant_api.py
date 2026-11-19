"""Assistant endpoints. The assistant explains stored, structured results; it cannot create, change or delete anything."""
from __future__ import annotations

import json
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints

from . import assistant, explain as ex, gametheory as gt, simulation as sim
from .db import get_conn
from .facts_loader import load_facts
from .security import Auth

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])

ItemType = Literal["prediction", "simulation", "scenario"]
Focus = Literal["overview", "uncertainty", "assumptions", "limitations", "next", "all"]


class ExplainBody(BaseModel):
    type: ItemType
    id: uuid.UUID
    focus: Focus = "all"
    question: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    use_llm: bool = True


class CompareBody(BaseModel):
    type: Literal["simulation", "scenario"]
    ids: list[uuid.UUID] = Field(min_length=2, max_length=4)
    use_llm: bool = True


def _audit(conn, p, action: str, detail: dict) -> None:
    conn.execute("insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,%s,%s)", (p.workspace_id, p.user_id, action, json.dumps(detail)))


@router.get("/status")
def status(p: Auth):
    return {**assistant.llm_status(), "deterministic": True,
            "note": "Explanations are assembled from the engines' own numbers. If a language model is configured, its text is shown only when every number in it matches the computed results."}


@router.post("/explain")
def explain(body: ExplainBody, p: Auth, conn=Depends(get_conn)):
    facts, meta = load_facts(conn, p, body.type, body.id)
    try:
        out = assistant.explain(facts, body.focus, body.question, body.use_llm)
    except assistant.AssistantUnavailable as e:
        raise HTTPException(422, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    _audit(conn, p, "assistant.explain", {"type": body.type, "id": str(body.id), "mode": out["mode"], "focus": body.focus, "rejected": out["grounding"]["rejected"]})
    out["item"] = {"type": body.type, "id": str(body.id), **meta}
    return out


def _scenario_summary(conn, p, sid: uuid.UUID):
    row = conn.execute("select id, title, domain, definition from strategic_scenarios where id=%s and workspace_id=%s", (sid, p.workspace_id)).fetchone()
    if not row:
        raise HTTPException(404, "Item not found")
    d, domain = row["definition"], row["domain"]
    if domain == "business":
        m = conn.execute("select matrix from payoff_matrices where scenario_id=%s", (sid,)).fetchone()
        a = gt.analyse(gt.build_game(d["row_strategies"], d["col_strategies"], m["matrix"]))
        R, C = d["row_strategies"], d["col_strategies"]
        return domain, "business", row["title"], {"pure_nash": [{"row": R[n["row"]], "col": C[n["col"]]} for n in a["pure_nash"]], "max_welfare": a["max_welfare"]["value"]}
    return domain, d["kind"], row["title"], d["summary"]


@router.post("/compare")
def compare(body: CompareBody, p: Auth, conn=Depends(get_conn)):
    ids = list(dict.fromkeys(body.ids))
    if len(ids) < 2:
        raise HTTPException(422, "Choose at least two different items")
    if body.type == "simulation":
        runs = []
        for i in ids:
            r = conn.execute("select title, status, result from simulation_runs where id=%s and workspace_id=%s", (i, p.workspace_id)).fetchone()
            if not r:
                raise HTTPException(404, "Item not found")
            if r["status"] != "completed":
                raise HTTPException(409, "Only completed runs can be compared")
            runs.append(r)
        comp = sim.compare([r["result"] for r in runs], [r["title"] for r in runs])
        lines = ex.compare_text("simulation", [{"title": "", "summary": row} for row in comp["outputs"]])
        domain, kind = "simulation", "simulation"
    else:
        got = [_scenario_summary(conn, p, i) for i in ids]
        if len({(g[0], g[1]) for g in got}) != 1:
            raise HTTPException(422, "Compare scenarios of the same module and type")
        domain, kind = got[0][0], got[0][1]
        lines = ex.compare_text(kind, [{"title": g[2], "summary": g[3]} for g in got])
    facts = ex.Facts("comparison", domain, "Comparison of " + str(len(ids)) + " items", "Differences between saved results", overview=lines,
                     uncertainty=["Differences describe the entered assumptions. If the inputs were uncertain, the differences are too."],
                     next_steps=["Change one assumption at a time to see which difference it drives."])
    out = assistant.explain(facts, "overview", None, body.use_llm)
    _audit(conn, p, "assistant.compare", {"type": body.type, "ids": [str(i) for i in ids], "mode": out["mode"]})
    out["lines"] = lines
    return out
