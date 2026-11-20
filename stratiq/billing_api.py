"""Read-only billing state for the signed-in workspace. Subscriptions are written only by the Stripe webhook in the web app."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends

from . import plans
from .db import get_conn
from .security import Auth

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


@router.get("/plan")
def current_plan(p: Auth, conn=Depends(get_conn)):
    plan = plans.workspace_plan(conn, p.workspace_id)
    name, limits = plans.PLANS[plan]
    sub = conn.execute(
        "select status, billing_interval, current_period_end, cancel_at_period_end from subscriptions where workspace_id=%s",
        (p.workspace_id,),
    ).fetchone()
    return {
        "plan": plan,
        "name": name,
        "enforced": plans.enforced(),
        "limits": asdict(limits),
        "usage": plans.usage(conn, p.workspace_id),
        "subscription": sub,
    }
