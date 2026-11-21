"""Plans and server-side limits. The web app mirrors the catalog in src/lib/plans.ts; THIS module is what enforces it.

Enforcement is off by default (BILLING_ENFORCED unset): every workspace then gets Strategy Pro limits, which is the
early-access behavior. Switch it on only once billing is live. Counts are per workspace.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import HTTPException

PAID_STATUSES = {"active", "trialing", "past_due"}  # past_due keeps access while Stripe retries the payment


@dataclass(frozen=True)
class Limits:
    predictions: int | None   # saved forecasts; None = unlimited
    scenarios: int | None     # saved strategic scenarios
    runs: int | None          # saved simulation runs
    iterations: int           # max Monte Carlo iterations per run
    exports: bool             # report downloads and full workspace export
    seats: int                # members plus pending invitations (only enforced when billing is)
    datasets: int | None      # uploaded datasets kept in the workspace


PLANS: dict[str, tuple[str, Limits]] = {
    "explorer": ("Explorer", Limits(predictions=10, scenarios=3, runs=3, iterations=10_000, exports=False, seats=2, datasets=1)),
    "sports_pro": ("Sports Pro", Limits(predictions=None, scenarios=3, runs=3, iterations=10_000, exports=False, seats=2, datasets=3)),
    "strategy_pro": ("Strategy Pro", Limits(predictions=None, scenarios=None, runs=None, iterations=200_000, exports=True, seats=5, datasets=20)),
}


def enforced() -> bool:
    return os.environ.get("BILLING_ENFORCED") == "1"


def workspace_plan(conn, workspace_id: str) -> str:
    if not enforced():
        return "strategy_pro"
    row = conn.execute("select plan, status from subscriptions where workspace_id=%s", (workspace_id,)).fetchone()
    if row and row["status"] in PAID_STATUSES and row["plan"] in PLANS:
        return row["plan"]
    return "explorer"


def limits_for(conn, workspace_id: str) -> Limits:
    return PLANS[workspace_plan(conn, workspace_id)][1]


_COUNT_SQL = {
    "predictions": "select count(*) as n from predictions where workspace_id=%s",
    "scenarios": "select (select count(*) from strategic_scenarios where workspace_id=%s) + (select count(*) from simlab_runs where workspace_id=%s) as n",
    "runs": "select count(*) as n from simulation_runs where workspace_id=%s",
    "datasets": "select count(*) as n from datasets where workspace_id=%s",
}


def seat_cap(conn, workspace_id: str) -> int | None:
    """Max members plus pending invitations, or None (unlimited) while billing is not enforced (early access)."""
    return limits_for(conn, workspace_id).seats if enforced() else None


def usage(conn, workspace_id: str) -> dict[str, int]:
    return {k: int(conn.execute(sql, (workspace_id,) * sql.count("%s")).fetchone()["n"]) for k, sql in _COUNT_SQL.items()}


def _refuse(message: str, code: str):
    raise HTTPException(402, {"code": code, "message": message})


def check_quota(conn, workspace_id: str, kind: str) -> None:
    """Call before saving a prediction, scenario or run. Raises 402 when the plan's cap is reached."""
    cap = getattr(limits_for(conn, workspace_id), kind)
    if cap is None:
        return
    if usage(conn, workspace_id)[kind] >= cap:
        label = {"predictions": "saved forecasts", "scenarios": "saved scenarios", "runs": "saved simulation runs", "datasets": "uploaded datasets"}[kind]
        _refuse(f"Your plan allows {cap} {label}. Upgrade to save more.", "plan_limit")


def check_iterations(conn, workspace_id: str, iterations: int) -> None:
    cap = limits_for(conn, workspace_id).iterations
    if iterations > cap:
        _refuse(f"Your plan allows up to {cap:,} iterations per simulation. Upgrade for larger runs.", "plan_limit")


def check_exports(conn, workspace_id: str) -> None:
    if not limits_for(conn, workspace_id).exports:
        _refuse("Report and workspace exports are part of Strategy Pro.", "plan_limit")
