"""Notification history and alert rules. Everything is private to the signed-in person inside their workspace.

Notifications appear only if the person created a rule. Reading the list evaluates the rules (at most once a minute) so the list is current without
any background process. In-app only: there is no email or push.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import alerts
from .db import get_conn
from .security import Auth

router = APIRouter(prefix="/api/v1", tags=["notifications"])
PAGE_MAX = 50


class ReadBody(BaseModel):
    ids: list[uuid.UUID] | None = Field(None, max_length=200)
    all: bool = False


class ReadPatch(BaseModel):
    read: bool


class RuleBody(BaseModel):
    kind: str
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class RulePatch(BaseModel):
    config: dict[str, Any] | None = None
    enabled: bool | None = None


def _config(kind: str, cfg: dict) -> dict:
    spec = alerts.RULE_KINDS.get(kind)
    if not spec:
        raise HTTPException(422, f"Unknown alert type. Choose from: {', '.join(alerts.RULE_KINDS)}.")
    allowed = spec["config"]
    if set(cfg) - set(allowed):
        raise HTTPException(422, f"'{kind}' does not take: {', '.join(sorted(set(cfg) - set(allowed)))}.")
    if kind == "fixture_soon":
        d = cfg.get("days", allowed["days"]["default"])
        if isinstance(d, bool) or not isinstance(d, int) or not allowed["days"]["min"] <= d <= allowed["days"]["max"]:
            raise HTTPException(422, f"'days' must be a whole number from {allowed['days']['min']} to {allowed['days']['max']}.")
        return {"days": d}
    return {}


def _rule_row(r) -> dict:
    return {"id": str(r["id"]), "kind": r["kind"], "label": alerts.RULE_KINDS[r["kind"]]["label"], "config": r["config"], "enabled": r["enabled"], "created_at": r["created_at"]}


def _note(r) -> dict:
    return {"id": str(r["id"]), "kind": r["kind"], "title": r["title"], "body": r["body"], "source": r["source"], "created_at": r["created_at"], "visible_at": r["visible_after"], "read": r["read_at"] is not None}


@router.get("/notifications")
def notifications(p: Auth, conn=Depends(get_conn), unread: bool = False, limit: int = Query(20, ge=1, le=PAGE_MAX), offset: int = Query(0, ge=0)):
    ev = alerts.evaluate(conn, p)
    where = "workspace_id=%s and user_id=%s and deleted_at is null and visible_after <= now() and (not %s or read_at is null)"
    args = (p.workspace_id, p.user_id, unread)
    rows = conn.execute(f"select * from notifications where {where} order by visible_after desc, id limit %s offset %s", (*args, limit, offset)).fetchall()
    total = conn.execute(f"select count(*) n from notifications where {where}", args).fetchone()["n"]
    unread_n = conn.execute("select count(*) n from notifications where workspace_id=%s and user_id=%s and deleted_at is null and visible_after <= now() and read_at is null", (p.workspace_id, p.user_id)).fetchone()["n"]
    held = conn.execute("select count(*) n from notifications where workspace_id=%s and user_id=%s and deleted_at is null and visible_after > now()", (p.workspace_id, p.user_id)).fetchone()["n"]
    n_rules = conn.execute("select count(*) n from alert_rules where workspace_id=%s and user_id=%s and enabled", (p.workspace_id, p.user_id)).fetchone()["n"]
    return {"notifications": [_note(r) for r in rows], "total": total, "unread": unread_n, "held_for_quiet_hours": held, "rules_enabled": n_rules, "evaluation": ev, "retention_days": alerts.RETENTION_DAYS}


@router.get("/notifications/count")
def count(p: Auth, conn=Depends(get_conn)):
    alerts.evaluate(conn, p)
    return {"unread": conn.execute("select count(*) n from notifications where workspace_id=%s and user_id=%s and deleted_at is null and visible_after <= now() and read_at is null", (p.workspace_id, p.user_id)).fetchone()["n"]}


@router.post("/notifications/read")
def read(body: ReadBody, p: Auth, conn=Depends(get_conn)):
    if not body.all and not body.ids:
        raise HTTPException(422, "Choose notifications to mark as read, or set all to true.")
    r = conn.execute("update notifications set read_at=now() where workspace_id=%s and user_id=%s and deleted_at is null and read_at is null and visible_after <= now() and (%s or id = any(%s))",
                     (p.workspace_id, p.user_id, body.all, body.ids or []))
    return {"marked": r.rowcount}


@router.patch("/notifications/{nid}")
def patch_note(nid: uuid.UUID, body: ReadPatch, p: Auth, conn=Depends(get_conn)):
    r = conn.execute("update notifications set read_at = case when %s then coalesce(read_at, now()) else null end where id=%s and workspace_id=%s and user_id=%s and deleted_at is null", (body.read, nid, p.workspace_id, p.user_id))
    if r.rowcount == 0:
        raise HTTPException(404, "Not found")
    return {"id": str(nid), "read": body.read}


@router.delete("/notifications/{nid}", status_code=204)
def delete_note(nid: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    if conn.execute("update notifications set deleted_at=now() where id=%s and workspace_id=%s and user_id=%s and deleted_at is null", (nid, p.workspace_id, p.user_id)).rowcount == 0:
        raise HTTPException(404, "Not found")


@router.delete("/notifications")
def clear(p: Auth, conn=Depends(get_conn), everything: bool = False):
    """Delete notifications you have read (or all of them with everything=true). Deleting one never makes the same event notify again within its dedupe window."""
    n = conn.execute("update notifications set deleted_at=now() where workspace_id=%s and user_id=%s and deleted_at is null and (%s or read_at is not null)", (p.workspace_id, p.user_id, everything)).rowcount
    return {"deleted": n}


@router.get("/alert-rules")
def rules(p: Auth, conn=Depends(get_conn)):
    rows = conn.execute("select id, kind, config, enabled, created_at from alert_rules where workspace_id=%s and user_id=%s order by created_at", (p.workspace_id, p.user_id)).fetchall()
    return {"rules": [_rule_row(r) for r in rows], "kinds": [{"kind": k, **{x: v for x, v in spec.items()}} for k, spec in alerts.RULE_KINDS.items()], "suggested": alerts.SUGGESTED,
            "channels": {"in_app": True, "email": False, "push": False, "note": "Alerts are in-app only. Nothing is sent by email or push, and nothing is created until you switch a rule on."}}


@router.post("/alert-rules", status_code=201)
def create_rule(body: RuleBody, p: Auth, conn=Depends(get_conn)):
    cfg = _config(body.kind, body.config)
    row = conn.execute("""insert into alert_rules (workspace_id, user_id, kind, config, enabled) values (%s,%s,%s,%s,%s)
                          on conflict (workspace_id, user_id, kind) do update set config=excluded.config, enabled=excluded.enabled returning id, kind, config, enabled, created_at""",
                       (p.workspace_id, p.user_id, body.kind, json.dumps(cfg), body.enabled)).fetchone()
    return _rule_row(row)


@router.post("/alert-rules/suggested", status_code=201)
def create_suggested(p: Auth, conn=Depends(get_conn)):
    """Switch on the suggested starter rules. Only happens when the person asks for it."""
    for k in alerts.SUGGESTED:
        conn.execute("insert into alert_rules (workspace_id, user_id, kind, config, enabled) values (%s,%s,%s,'{}'::jsonb,true) on conflict (workspace_id, user_id, kind) do update set enabled=true", (p.workspace_id, p.user_id, k))
    return {"enabled": alerts.SUGGESTED}


@router.patch("/alert-rules/{rid}")
def patch_rule(rid: uuid.UUID, body: RulePatch, p: Auth, conn=Depends(get_conn)):
    row = conn.execute("select kind, config, enabled from alert_rules where id=%s and workspace_id=%s and user_id=%s", (rid, p.workspace_id, p.user_id)).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    cfg = _config(row["kind"], body.config) if body.config is not None else row["config"]
    enabled = row["enabled"] if body.enabled is None else body.enabled
    conn.execute("update alert_rules set config=%s, enabled=%s where id=%s", (json.dumps(cfg), enabled, rid))
    return {"id": str(rid), "config": cfg, "enabled": enabled}


@router.delete("/alert-rules/{rid}", status_code=204)
def delete_rule(rid: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    if conn.execute("delete from alert_rules where id=%s and workspace_id=%s and user_id=%s", (rid, p.workspace_id, p.user_id)).rowcount == 0:
        raise HTTPException(404, "Not found")


@router.post("/alert-rules/evaluate")
def evaluate_now(p: Auth, conn=Depends(get_conn)):
    """Check for new events now (still bounded by the daily caps)."""
    return alerts.evaluate(conn, p, force=True)
