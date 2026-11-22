"""Per-user preferences: dashboard layout and preferred domains, notification settings (with quiet hours), and briefing settings.

Stored as three small JSON documents per person. Everything is validated against fixed lists, so a stored layout can never reference a widget that
does not exist, and reading always returns a complete, valid object (defaults fill anything missing). Nothing is opt-out: notifications start with
no rules and briefings start switched off.
"""
from __future__ import annotations

import json
import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .db import get_conn
from .security import Auth

router = APIRouter(prefix="/api/v1/preferences", tags=["preferences"])

WIDGETS = ["brief", "tracked", "changes", "alerts", "predictions", "scenarios", "quick_actions"]
WIDGET_LABELS = {"brief": "Intelligence brief", "tracked": "Tracked items", "changes": "Recent intelligence changes", "alerts": "Alert summary",
                 "predictions": "Recent predictions", "scenarios": "Saved scenarios", "quick_actions": "Quick actions"}
DOMAINS = ["sports", "business", "politics", "markets"]
DENSITIES = ("comfortable", "compact")
FREQUENCIES = ("off", "daily", "weekly")
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def default_dashboard() -> dict:
    return {"widgets": [{"id": w, "visible": True} for w in WIDGETS], "domains": list(DOMAINS), "density": "comfortable"}


def default_notifications() -> dict:
    return {"in_app": True, "quiet_hours": {"enabled": False, "start": "22:00", "end": "07:00", "utc_offset_minutes": 0}, "last_evaluated": None}


def default_briefing() -> dict:
    return {"frequency": "off", "domains": list(DOMAINS)}


class WidgetIn(BaseModel):
    id: str
    visible: bool = True


class DashboardIn(BaseModel):
    widgets: list[WidgetIn] | None = Field(None, max_length=len(WIDGETS))
    domains: list[str] | None = Field(None, max_length=len(DOMAINS))
    density: Literal["comfortable", "compact"] | None = None


class QuietIn(BaseModel):
    enabled: bool = False
    start: str = "22:00"
    end: str = "07:00"
    utc_offset_minutes: int = Field(0, ge=-720, le=840)


class NotificationsIn(BaseModel):
    in_app: bool | None = None
    quiet_hours: QuietIn | None = None


class BriefingIn(BaseModel):
    frequency: Literal["off", "daily", "weekly"] | None = None
    domains: list[str] | None = Field(None, max_length=len(DOMAINS))


class PrefsIn(BaseModel):
    dashboard: DashboardIn | None = None
    notifications: NotificationsIn | None = None
    briefing: BriefingIn | None = None


def _domains(v: list[str]) -> list[str]:
    if not v or any(d not in DOMAINS for d in v) or len(set(v)) != len(v):
        raise HTTPException(422, f"Domains must be a non-empty list without repeats, chosen from: {', '.join(DOMAINS)}.")
    return [d for d in DOMAINS if d in v]


def normalise_dashboard(raw: dict | None) -> dict:
    """A complete, valid dashboard preference. Unknown or repeated widgets in stored data are dropped; widgets never saved are appended visible."""
    base = default_dashboard()
    raw = raw or {}
    seen: set[str] = set()
    widgets = []
    for w in raw.get("widgets") or []:
        if isinstance(w, dict) and w.get("id") in WIDGETS and w["id"] not in seen:
            seen.add(w["id"])
            widgets.append({"id": w["id"], "visible": bool(w.get("visible", True))})
    widgets += [{"id": w, "visible": True} for w in WIDGETS if w not in seen]
    doms = [d for d in DOMAINS if d in (raw.get("domains") or [])] or base["domains"]
    dens = raw.get("density") if raw.get("density") in DENSITIES else base["density"]
    return {"widgets": widgets, "domains": doms, "density": dens}


def normalise_notifications(raw: dict | None) -> dict:
    base = default_notifications()
    raw = raw or {}
    q = {**base["quiet_hours"], **(raw.get("quiet_hours") or {})}
    q = {"enabled": bool(q["enabled"]), "start": q["start"] if HHMM.match(str(q["start"])) else "22:00", "end": q["end"] if HHMM.match(str(q["end"])) else "07:00",
         "utc_offset_minutes": q["utc_offset_minutes"] if isinstance(q["utc_offset_minutes"], int) and -720 <= q["utc_offset_minutes"] <= 840 else 0}
    return {"in_app": bool(raw.get("in_app", True)), "quiet_hours": q, "last_evaluated": raw.get("last_evaluated")}


def normalise_briefing(raw: dict | None) -> dict:
    raw = raw or {}
    return {"frequency": raw.get("frequency") if raw.get("frequency") in FREQUENCIES else "off", "domains": [d for d in DOMAINS if d in (raw.get("domains") or [])] or list(DOMAINS)}


def load(conn, user_id) -> dict:
    row = conn.execute("select dashboard, notifications, briefing from user_preferences where user_id=%s", (user_id,)).fetchone()
    return {"dashboard": normalise_dashboard(row["dashboard"] if row else None), "notifications": normalise_notifications(row["notifications"] if row else None),
            "briefing": normalise_briefing(row["briefing"] if row else None)}


def save_section(conn, user_id, section: str, value: dict) -> None:
    assert section in ("dashboard", "notifications", "briefing")
    conn.execute(f"""insert into user_preferences (user_id, {section}) values (%s,%s)
                     on conflict (user_id) do update set {section}=excluded.{section}, updated_at=now()""", (user_id, json.dumps(value)))


def validate_hhmm(v: str, label: str) -> str:
    if not HHMM.match(v):
        raise HTTPException(422, f"{label} must be a time like 22:00.")
    return v


@router.get("")
def get_prefs(p: Auth, conn=Depends(get_conn)):
    return {**load(conn, p.user_id), "widgets_available": [{"id": w, "label": WIDGET_LABELS[w]} for w in WIDGETS], "domains_available": DOMAINS,
            "channels": {"in_app": True, "email": False, "push": False, "note": "Only in-app notifications exist. Email and push are not available, so nothing is ever sent outside the app."}}


@router.put("")
def put_prefs(body: PrefsIn, p: Auth, conn=Depends(get_conn)):
    cur = load(conn, p.user_id)
    if body.dashboard:
        d = dict(cur["dashboard"])
        if body.dashboard.widgets is not None:
            ids = [w.id for w in body.dashboard.widgets]
            if any(i not in WIDGETS for i in ids) or len(set(ids)) != len(ids):
                raise HTTPException(422, f"Widgets must be unique and chosen from: {', '.join(WIDGETS)}.")
            d["widgets"] = [{"id": w.id, "visible": w.visible} for w in body.dashboard.widgets]
        if body.dashboard.domains is not None:
            d["domains"] = _domains(body.dashboard.domains)
        if body.dashboard.density is not None:
            d["density"] = body.dashboard.density
        save_section(conn, p.user_id, "dashboard", normalise_dashboard(d))
    if body.notifications:
        n = dict(cur["notifications"])
        if body.notifications.in_app is not None:
            n["in_app"] = body.notifications.in_app
        if body.notifications.quiet_hours is not None:
            q = body.notifications.quiet_hours
            n["quiet_hours"] = {"enabled": q.enabled, "start": validate_hhmm(q.start, "Quiet hours start"), "end": validate_hhmm(q.end, "Quiet hours end"), "utc_offset_minutes": q.utc_offset_minutes}
        save_section(conn, p.user_id, "notifications", normalise_notifications(n))
    if body.briefing:
        b = dict(cur["briefing"])
        if body.briefing.frequency is not None:
            b["frequency"] = body.briefing.frequency
        if body.briefing.domains is not None:
            b["domains"] = _domains(body.briefing.domains)
        save_section(conn, p.user_id, "briefing", normalise_briefing(b))
    return load(conn, p.user_id)


@router.delete("")
def reset(p: Auth, conn=Depends(get_conn), section: Literal["dashboard", "notifications", "briefing", "all"] = Query("dashboard")):
    """Restore defaults. By default only the dashboard layout is reset; notification and briefing settings are only reset when asked for."""
    cols = ["dashboard", "notifications", "briefing"] if section == "all" else [section]
    for c in cols:
        conn.execute(f"update user_preferences set {c}='{{}}'::jsonb, updated_at=now() where user_id=%s", (p.user_id,))
    return load(conn, p.user_id)
