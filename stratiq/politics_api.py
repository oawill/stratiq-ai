"""Political Intelligence endpoints: nonpartisan, aggregate, scenario-based tools.

No polling data is stored or served. Every input is a user-entered assumption and every output says so.
No endpoint accepts or returns individual-level data."""
from __future__ import annotations

import json
import secrets
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StringConstraints, ValidationError

from . import politics as pol
from .db import get_conn
from .security import ADMIN_ROLES, Auth, require_write

router = APIRouter(prefix="/api/v1/politics", tags=["politics"])

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Method = Literal["dhondt", "sainte_lague", "hare"]
SCENARIO_NOTICE = "Scenario arithmetic on entered assumptions. Not a poll, not a validated election forecast."


class PartySeats(BaseModel):
    name: Name
    seats: int = Field(ge=0, le=100000)
    position: float | None = Field(None, ge=-1000, le=1000)


class CoalitionBody(BaseModel):
    parties: list[PartySeats] = Field(min_length=2, max_length=pol.MAX_PARTIES)
    quota_fraction: float = Field(0.5, ge=0.5, lt=1)


class PartyVotes(BaseModel):
    name: Name
    votes: float = Field(ge=0, le=1e12)


class AllocateBody(BaseModel):
    method: Method = "dhondt"
    seats: int = Field(ge=1, le=pol.MAX_SEATS)
    threshold: float = Field(0, ge=0, lt=1)
    parties: list[PartyVotes] = Field(min_length=2, max_length=30)


class SimulateBody(AllocateBody):
    parties: list[PartyVotes] = Field(min_length=2, max_length=10)
    concentration: float = Field(200, ge=5, le=100000)
    quota_fraction: float = Field(0.5, ge=0.5, lt=1)
    candidates: list[list[Name]] = Field(default_factory=list, max_length=10)
    iterations: int = Field(2000, ge=100, le=5000)
    seed: int | None = Field(None, ge=0, lt=2**31)


class Bloc(BaseModel):
    name: Name
    electorate: float = Field(gt=0, le=1e10)
    turnout: float = Field(ge=0, le=1)
    prefs: dict[Name, float]


class Sweep(BaseModel):
    mode: Literal["bloc", "all_shift"]
    bloc: int | None = Field(None, ge=0, lt=pol.MAX_BLOCS)
    lo: float
    hi: float


class TurnoutBody(BaseModel):
    parties: list[Name] = Field(min_length=2, max_length=pol.MAX_PARTIES)
    blocs: list[Bloc] = Field(min_length=1, max_length=pol.MAX_BLOCS)
    method: Method = "dhondt"
    seats: int = Field(100, ge=1, le=pol.MAX_SEATS)
    threshold: float = Field(0, ge=0, lt=1)
    sweep: Sweep | None = None


class Criterion(BaseModel):
    name: Name
    weight: float = Field(ge=0, le=1e6)
    direction: Literal["benefit", "cost"]


class PolicyBody(BaseModel):
    alternatives: list[Name] = Field(min_length=2, max_length=pol.MAX_ALTS)
    criteria: list[Criterion] = Field(min_length=2, max_length=pol.MAX_CRITERIA)
    scores: list[list[float]] = Field(max_length=pol.MAX_ALTS)
    seed: int | None = Field(None, ge=0, lt=2**31)
    samples: int = Field(5000, ge=100, le=20000)


# ------------------------------------------------------------------ analysis wrappers
def _guard(fn, *a, **k):
    try:
        return fn(*a, **k)
    except pol.PoliticsError as e:
        raise HTTPException(422, str(e))


def run_coalition(b: CoalitionBody) -> dict:
    out = _guard(
        pol.coalition_analysis, [p.name for p in b.parties], [p.seats for p in b.parties],
        None if any(p.position is None for p in b.parties) else [p.position for p in b.parties], b.quota_fraction,
    )
    out["notice"] = SCENARIO_NOTICE
    return out


def run_turnout(b: TurnoutBody) -> dict:
    sweep = None if b.sweep is None else b.sweep.model_dump()
    out = _guard(pol.turnout_analysis, b.parties, [x.model_dump() for x in b.blocs], b.method, b.seats, b.threshold, sweep)
    out["notice"] = SCENARIO_NOTICE
    return out


def run_policy(b: PolicyBody, seed: int) -> dict:
    out = _guard(pol.policy_analysis, b.alternatives, [c.model_dump() for c in b.criteria], b.scores, seed, b.samples)
    out["notice"] = "Weights are value judgements entered by the user, not facts."
    return out


# ------------------------------------------------------------------ stateless endpoints
@router.post("/coalitions")
def coalitions(body: CoalitionBody, p: Auth):
    return run_coalition(body)


@router.post("/allocate")
def allocate(body: AllocateBody, p: Auth):
    votes = [x.votes for x in body.parties]
    seats = _guard(pol.allocate, body.method, body.seats, votes, body.threshold)
    total = sum(votes)
    return {
        "method": body.method, "seats": body.seats, "threshold": body.threshold,
        "parties": [{"name": x.name, "votes": x.votes, "vote_share": x.votes / total if total else 0.0, "seats": s, "seat_share": s / body.seats}
                    for x, s in zip(body.parties, seats)],
        "notice": SCENARIO_NOTICE,
    }


@router.post("/simulate")
def simulate(body: SimulateBody, p: Auth):
    names = [x.name for x in body.parties]
    if len(set(names)) != len(names):
        raise HTTPException(422, "party names must be unique")
    try:
        cands = [[names.index(n) for n in c] for c in body.candidates]
    except ValueError:
        raise HTTPException(422, "a candidate coalition names a party that is not in the party list")
    seed = body.seed if body.seed is not None else secrets.randbelow(2**31)
    out = _guard(pol.simulate_coalitions, names, [x.votes for x in body.parties], body.method, body.seats, body.threshold,
                 body.concentration, body.quota_fraction, cands, body.iterations, seed)
    out["notice"] = SCENARIO_NOTICE
    return out


@router.post("/turnout")
def turnout(body: TurnoutBody, p: Auth):
    return run_turnout(body)


@router.post("/policy")
def policy(body: PolicyBody, p: Auth):
    seed = body.seed if body.seed is not None else secrets.randbelow(2**31)
    return run_policy(body, seed)


# ------------------------------------------------------------------ saved scenarios
KIND_MODEL: dict[str, type[BaseModel]] = {"coalition": CoalitionBody, "turnout": TurnoutBody, "policy": PolicyBody}


class ScenarioBody(BaseModel):
    kind: Literal["coalition", "turnout", "policy"]
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    notes: Annotated[str, StringConstraints(max_length=2000)] | None = None
    inputs: dict[str, Any]


class CompareBody(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=2, max_length=4)


def _parse(kind: str, inputs: dict) -> BaseModel:
    try:
        return KIND_MODEL[kind].model_validate(inputs)
    except ValidationError as e:
        raise HTTPException(422, "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:5]))


def analyse(kind: str, model: BaseModel) -> dict:
    if kind == "coalition":
        return run_coalition(model)  # type: ignore[arg-type]
    if kind == "turnout":
        return run_turnout(model)  # type: ignore[arg-type]
    return run_policy(model, model.seed or 0)  # type: ignore[attr-defined]


def summarise(kind: str, a: dict) -> dict:
    if kind == "coalition":
        return {
            "total_seats": a["total_seats"], "seats_needed": a["seats_needed"], "minimal_winning_count": a["minimal_winning_count"],
            "parties": [{"name": x["name"], "seats": x["seats"], "shapley_shubik": x["shapley_shubik"], "banzhaf": x["banzhaf_normalised"],
                         "veto": x["is_veto"], "dummy": x["is_dummy"]} for x in a["parties"]],
        }
    if kind == "turnout":
        b = a["baseline"]
        s = a.get("sweep")
        return {
            "parties": [{"name": n, "vote_share": b["vote_share"][i], "seats": b["seats"][i]} for i, n in enumerate(a["parties"])],
            "largest": b["largest"], "majority_party": b["majority_party"], "turnout": b["turnout_overall"],
            "change_points": None if s is None else [c["at"] for c in s["changes"][:5]],
        }
    return {
        "ranking": a["ranking"],
        "alternatives": [{"name": x["name"], "score": x["weighted_score"], "rank": x["rank"], "pareto": x["pareto_optimal"], "p_top": x["p_top"]} for x in a["alternatives"]],
    }


@router.post("/scenarios", status_code=201)
def save_scenario(body: ScenarioBody, p: Auth, conn=Depends(get_conn)):
    require_write(p)
    inputs = dict(body.inputs)
    if body.kind == "policy" and inputs.get("seed") is None:
        inputs["seed"] = secrets.randbelow(2**31)  # fixed so the saved scenario reproduces exactly
    model = _parse(body.kind, inputs)
    analysis = analyse(body.kind, model)
    definition = {"kind": body.kind, "inputs": model.model_dump(), "notes": body.notes, "summary": summarise(body.kind, analysis)}
    row = conn.execute(
        "insert into strategic_scenarios (workspace_id, created_by, title, domain, definition) values (%s,%s,%s,'politics',%s) returning id, created_at",
        (p.workspace_id, p.user_id, body.title, json.dumps(definition)),
    ).fetchone()
    conn.execute(
        "insert into activity_history (workspace_id,user_id,kind,summary,ref_type,ref_id) values (%s,%s,'scenario.created',%s,'scenario',%s)",
        (p.workspace_id, p.user_id, f"Saved political scenario: {body.title}", str(row["id"])),
    )
    conn.execute(
        "insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'political_scenario.create',%s)",
        (p.workspace_id, p.user_id, json.dumps({"scenario_id": str(row["id"]), "kind": body.kind})),
    )
    return {"id": row["id"], "created_at": row["created_at"], "kind": body.kind, "analysis": analysis}


@router.get("/scenarios")
def list_scenarios(p: Auth, conn=Depends(get_conn), kind: Literal["coalition", "turnout", "policy"] | None = None, limit: int = Query(50, ge=1, le=200)):
    rows = conn.execute(
        """select s.id, s.title, s.created_at, u.name created_by_name, s.definition->>'kind' kind
           from strategic_scenarios s join users u on u.id = s.created_by
           where s.workspace_id=%s and s.domain='politics' and (%s::text is null or s.definition->>'kind' = %s)
           order by s.created_at desc limit %s""",
        (p.workspace_id, kind, kind, limit),
    ).fetchall()
    return {"scenarios": rows}


def _load(conn, p, sid: uuid.UUID):
    row = conn.execute(
        "select id, title, created_at, created_by, definition from strategic_scenarios where id=%s and workspace_id=%s and domain='politics'",
        (sid, p.workspace_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Scenario not found")  # identical for missing and other-workspace
    return row


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    row = _load(conn, p, scenario_id)
    d = row["definition"]
    model = _parse(d["kind"], d["inputs"])
    return {"id": row["id"], "title": row["title"], "created_at": row["created_at"], "kind": d["kind"], "notes": d.get("notes"),
            "inputs": d["inputs"], "analysis": analyse(d["kind"], model)}


@router.post("/compare")
def compare(body: CompareBody, p: Auth, conn=Depends(get_conn)):
    ids = list(dict.fromkeys(body.ids))
    if len(ids) < 2:
        raise HTTPException(422, "Choose at least two different scenarios")
    rows = [_load(conn, p, i) for i in ids]
    kinds = {r["definition"]["kind"] for r in rows}
    if len(kinds) != 1:
        raise HTTPException(422, "Compare scenarios of the same type (coalition, turnout or policy)")
    kind = kinds.pop()
    out = []
    for r in rows:
        d = r["definition"]
        out.append({"id": r["id"], "title": r["title"], "summary": summarise(kind, analyse(kind, _parse(kind, d["inputs"])))})
    return {"kind": kind, "scenarios": out, "notice": SCENARIO_NOTICE}


@router.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    require_write(p)
    row = _load(conn, p, scenario_id)
    if str(row["created_by"]) != p.user_id and p.role not in ADMIN_ROLES:
        raise HTTPException(403, "Only the author or a workspace admin can delete a scenario")
    conn.execute("delete from strategic_scenarios where id=%s and workspace_id=%s", (scenario_id, p.workspace_id))
    conn.execute(
        "insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'political_scenario.delete',%s)",
        (p.workspace_id, p.user_id, json.dumps({"scenario_id": str(scenario_id), "title": row["title"]})),
    )
