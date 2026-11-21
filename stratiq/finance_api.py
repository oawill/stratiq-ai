"""Financial Intelligence endpoints: educational scenario analysis.

No market data is fetched or stored by this service and no endpoint can place an order. Historical analysis runs only
on return series supplied in the request body. The deliberate absence of a data provider is reported by /data-sources."""
from __future__ import annotations

import json
import os
import secrets
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StringConstraints, ValidationError

from . import finance as fin
from .brand import NAME
from .db import get_conn
from . import plans
from . import scenario_meta
from .simlab_api import _limit
from .security import ADMIN_ROLES, Auth, require_write

router = APIRouter(prefix="/api/v1/finance", tags=["finance"])

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
NOTICE = "Educational scenario analysis. Not investment advice, not a forecast, and not connected to any broker."
MAX_STORED_POINTS = 20_000


class AssetIn(BaseModel):
    name: Name
    weight: float = Field(ge=0, le=1)
    mu: float = Field(ge=-1, le=5, description="expected annual return (assumption)")
    sigma: float = Field(ge=0, le=5, description="annual volatility (assumption)")


class PortfolioBody(BaseModel):
    assets: list[AssetIn] = Field(min_length=1, max_length=fin.MAX_ASSETS)
    correlation: list[list[float]]
    initial_value: float = Field(100000, gt=0, le=1e12)


class McBody(PortfolioBody):
    horizon_years: float = Field(1, ge=0.1, le=30)
    steps_per_year: Literal[4, 12, 52] = 12
    iterations: int = Field(5000, ge=500, le=20000)
    rebalance: Literal["every_step", "none"] = "every_step"
    tails: Literal["normal", "student_t"] = "normal"
    df: float = Field(5, ge=3, le=100)
    seed: int | None = Field(None, ge=0, lt=2**31)
    confidences: list[Annotated[float, Field(ge=0.5, lt=1)]] = Field(default_factory=lambda: [0.95, 0.99], min_length=1, max_length=4)
    loss_threshold: float | None = Field(None, ge=0, le=1)
    drawdown_threshold: float | None = Field(None, ge=0, le=1)


class StressAsset(BaseModel):
    name: Name
    weight: float = Field(ge=0, le=1)


class Scenario(BaseModel):
    name: Name
    shocks: dict[Name, float]


class StressBody(BaseModel):
    assets: list[StressAsset] = Field(min_length=1, max_length=fin.MAX_ASSETS)
    initial_value: float = Field(100000, gt=0, le=1e12)
    scenarios: list[Scenario] = Field(min_length=1, max_length=20)
    reverse_target_loss: float | None = Field(None, gt=0, lt=1)


class HistBody(BaseModel):
    series: dict[Name, list[float]] = Field(min_length=1, max_length=fin.MAX_ASSETS)
    weights: dict[Name, float]
    periods_per_year: int = Field(252, ge=1, le=366)
    confidences: list[Annotated[float, Field(ge=0.5, lt=1)]] = Field(default_factory=lambda: [0.95, 0.99], min_length=1, max_length=4)


def _guard(fn, *a, **k):
    try:
        return fn(*a, **k)
    except fin.FinanceError as e:
        raise HTTPException(422, str(e))


def _pf(b: PortfolioBody):
    return [a.name for a in b.assets], [a.weight for a in b.assets], [a.mu for a in b.assets], [a.sigma for a in b.assets]


def run_portfolio(b: PortfolioBody) -> dict:
    names, w, mu, sg = _pf(b)
    out = _guard(fin.portfolio_analytics, names, w, mu, sg, b.correlation)
    out["notice"] = NOTICE
    return out


def run_mc(b: McBody, seed: int) -> dict:
    names, w, mu, sg = _pf(b)
    out = _guard(fin.monte_carlo, names, w, mu, sg, b.correlation, b.initial_value, b.horizon_years, b.steps_per_year, b.iterations,
                 b.rebalance, b.tails, b.df, seed, b.confidences, b.loss_threshold, b.drawdown_threshold)
    out["analytics"] = run_portfolio(b)
    out["initial_value"] = b.initial_value
    out["notice"] = NOTICE
    return out


def run_stress(b: StressBody) -> dict:
    out = _guard(fin.stress_test, [a.name for a in b.assets], [a.weight for a in b.assets], b.initial_value,
                 [s.model_dump() for s in b.scenarios], b.reverse_target_loss)
    out["notice"] = NOTICE
    return out


def run_hist(b: HistBody) -> dict:
    out = _guard(fin.historical_analysis, b.series, b.weights, b.periods_per_year, b.confidences)
    out["notice"] = NOTICE
    return out


# ------------------------------------------------------------------ stateless
@router.get("/data-sources")
def data_sources(p: Auth):
    requested = os.environ.get("FINANCE_DATA_PROVIDER") or None
    return {
        "configured": False, "requested_provider": requested,
        "message": (f"No market-data provider is configured, so no historical market data is available in {NAME}. "
                    "You can analyse return series you supply yourself; they are used as-is and are not verified. "
                    "Only supply data you are permitted to use."),
        "user_supplied_series": True, "automated_trading": False,
    }


@router.post("/portfolio")
def portfolio(body: PortfolioBody, p: Auth):
    return run_portfolio(body)


@router.post("/montecarlo")
def montecarlo(body: McBody, p: Auth):
    return run_mc(body, body.seed if body.seed is not None else secrets.randbelow(2**31))


@router.post("/stress")
def stress(body: StressBody, p: Auth):
    return run_stress(body)


@router.post("/historical")
def historical(body: HistBody, p: Auth):
    return run_hist(body)


# ------------------------------------------------------------------ saved scenarios
KIND_MODEL: dict[str, type[BaseModel]] = {"montecarlo": McBody, "stress": StressBody, "historical": HistBody}


class ScenarioBody(BaseModel):
    kind: Literal["montecarlo", "stress", "historical"]
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    notes: Annotated[str, StringConstraints(max_length=2000)] | None = None
    inputs: dict[str, Any]
    based_on: uuid.UUID | None = None      # save as the next version of this scenario


class CompareBody(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=2, max_length=4)


def _parse(kind: str, inputs: dict) -> BaseModel:
    try:
        return KIND_MODEL[kind].model_validate(inputs)
    except ValidationError as e:
        raise HTTPException(422, "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:5]))


def analyse(kind: str, m: BaseModel) -> dict:
    if kind == "montecarlo":
        return run_mc(m, m.seed or 0)  # type: ignore[arg-type,attr-defined]
    if kind == "stress":
        return run_stress(m)  # type: ignore[arg-type]
    return run_hist(m)  # type: ignore[arg-type]


def summarise(kind: str, a: dict, inputs: dict) -> dict:
    if kind == "montecarlo":
        t = a["terminal"]
        return {
            "horizon_years": a["horizon_years"], "initial_value": a["initial_value"], "seed": a["seed"], "iterations": a["iterations"],
            "model": a["model"], "expected_return": a["analytics"]["expected_return"], "volatility": a["analytics"]["volatility"],
            "assets": [{"name": x["name"], "weight": x["weight"]} for x in a["analytics"]["assets"]],
            "median_value": t["median_value"], "p5_value": t["p5_value"], "p95_value": t["p95_value"], "p_loss": a["p_loss"],
            "max_drawdown_mean": a["max_drawdown"]["mean"],
            "risk": [{"confidence": r["confidence"], "var": r["mc_var"], "es": r["mc_es"]} for r in a["risk"]],
        }
    if kind == "stress":
        return {"initial_value": inputs["initial_value"], "worst": a["worst"],
                "scenarios": [{"name": s["name"], "portfolio_return": s["portfolio_return"], "pnl": s["pnl"]} for s in a["scenarios"]]}
    return {
        "periods": a["portfolio"]["periods"], "assets": a["names"], "weights": a["weights"],
        "cagr": a["portfolio"]["cagr"], "annualised_vol": a["portfolio"]["annualised_vol"], "max_drawdown": a["portfolio"]["max_drawdown"],
        "risk": [{"confidence": r["confidence"], "var": r["historical"]["var"], "es": r["historical"]["es"]} for r in a["risk"]],
    }


@router.post("/scenarios", status_code=201)
def save_scenario(body: ScenarioBody, p: Auth, conn=Depends(get_conn)):
    require_write(p)
    plans.check_quota(conn, p.workspace_id, "scenarios")
    _limit(conn, p)
    lin = scenario_meta.lineage(conn, p, "finance", body.kind, body.based_on)
    inputs = dict(body.inputs)
    if body.kind == "montecarlo" and inputs.get("seed") is None:
        inputs["seed"] = secrets.randbelow(2**31)  # fixed, so the saved scenario reproduces exactly
    model = _parse(body.kind, inputs)
    if body.kind == "historical" and sum(len(v) for v in model.series.values()) > MAX_STORED_POINTS:  # type: ignore[attr-defined]
        raise HTTPException(422, f"Saved scenarios can hold at most {MAX_STORED_POINTS:,} data points; shorten the series or save fewer assets.")
    analysis = analyse(body.kind, model)
    stored = model.model_dump()
    definition = {"kind": body.kind, "inputs": stored, "notes": body.notes, "summary": summarise(body.kind, analysis, stored), **lin,
                  "provenance": scenario_meta.provenance("finance", fin.ENGINE_VERSION, inputs.get("seed") if body.kind == "montecarlo" else None, "entered by the user (no market data is fetched or stored)")}
    row = conn.execute(
        "insert into strategic_scenarios (workspace_id, created_by, title, domain, definition) values (%s,%s,%s,'finance',%s) returning id, created_at",
        (p.workspace_id, p.user_id, body.title, json.dumps(definition)),
    ).fetchone()
    conn.execute(
        "insert into activity_history (workspace_id,user_id,kind,summary,ref_type,ref_id) values (%s,%s,'scenario.created',%s,'scenario',%s)",
        (p.workspace_id, p.user_id, f"Saved financial scenario: {body.title}", str(row["id"])),
    )
    conn.execute(
        "insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'financial_scenario.create',%s)",
        (p.workspace_id, p.user_id, json.dumps({"scenario_id": str(row["id"]), "kind": body.kind})),
    )
    return {"id": row["id"], "created_at": row["created_at"], "kind": body.kind, "analysis": analysis, "version": lin["version"], "scenario_key": lin["scenario_key"], "parent_id": lin["parent_id"]}


@router.get("/scenarios")
def list_scenarios(p: Auth, conn=Depends(get_conn), kind: Literal["montecarlo", "stress", "historical"] | None = None, limit: int = Query(50, ge=1, le=200)):
    rows = conn.execute(
        """select s.id, s.title, s.created_at, u.name created_by_name, s.definition->>'kind' kind, coalesce((s.definition->>'version')::int, 1) version, s.definition->>'scenario_key' scenario_key
           from strategic_scenarios s join users u on u.id = s.created_by
           where s.workspace_id=%s and s.domain='finance' and (%s::text is null or s.definition->>'kind' = %s)
           order by s.created_at desc limit %s""",
        (p.workspace_id, kind, kind, limit),
    ).fetchall()
    return {"scenarios": rows}


def _load(conn, p, sid: uuid.UUID):
    row = conn.execute(
        "select id, title, created_at, created_by, definition from strategic_scenarios where id=%s and workspace_id=%s and domain='finance'",
        (sid, p.workspace_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Scenario not found")  # identical for missing and other-workspace
    return row


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    row = _load(conn, p, scenario_id)
    d = row["definition"]
    return {"id": row["id"], "title": row["title"], "created_at": row["created_at"], "kind": d["kind"], "notes": d.get("notes"),
            "inputs": d["inputs"], "analysis": analyse(d["kind"], _parse(d["kind"], d["inputs"]))}


@router.post("/compare")
def compare(body: CompareBody, p: Auth, conn=Depends(get_conn)):
    ids = list(dict.fromkeys(body.ids))
    if len(ids) < 2:
        raise HTTPException(422, "Choose at least two different scenarios")
    rows = [_load(conn, p, i) for i in ids]
    kinds = {r["definition"]["kind"] for r in rows}
    if len(kinds) != 1:
        raise HTTPException(422, "Compare scenarios of the same type (Monte Carlo, stress or historical)")
    kind = kinds.pop()
    # stored summaries were computed from the same deterministic engine when saved
    return {"kind": kind, "notice": NOTICE, "scenarios": [{"id": r["id"], "title": r["title"], "summary": r["definition"]["summary"]} for r in rows]}


@router.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    require_write(p)
    row = _load(conn, p, scenario_id)
    if str(row["created_by"]) != p.user_id and p.role not in ADMIN_ROLES:
        raise HTTPException(403, "Only the author or a workspace admin can delete a scenario")
    conn.execute("delete from strategic_scenarios where id=%s and workspace_id=%s", (scenario_id, p.workspace_id))
    conn.execute(
        "insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'financial_scenario.delete',%s)",
        (p.workspace_id, p.user_id, json.dumps({"scenario_id": str(scenario_id), "title": row["title"]})),
    )
