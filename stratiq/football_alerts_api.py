"""Football alert preferences, the workspace's recent football events, and a readiness report (Phase 4G).

Preferences are per person and opt-in: nothing is sent until a person chooses categories. Reading needs a signed-in member; everyone edits only their own choices.
"""
from __future__ import annotations

import os
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import football_notify as notify
from . import football_provider as fp
from . import football_refresh as fr
from . import football_sync as sync
from .db import get_conn
from .football_teams import CLUBS
from .security import Auth

router = APIRouter(prefix="/api/v1/football/live", tags=["football-alerts"])


class PrefsBody(BaseModel):
    categories: list[str] = Field(default_factory=list, max_length=8)
    competitions: list[str] = Field(default_factory=lambda: ["EPL"], max_length=5)
    teams: list[str] = Field(default_factory=list, max_length=notify.MAX_TEAMS)
    channels: dict[str, bool] = Field(default_factory=dict)


def _known_teams(conn, wid: str) -> list[str]:
    rows = conn.execute("select name from football_teams where workspace_id=%s and competition='EPL'", (wid,)).fetchall()
    return sorted({r["name"] for r in rows} | set(CLUBS))


@router.get("/alert-settings")
def get_alert_settings(p: Auth, conn=Depends(get_conn)):
    """This person's football alert choices, what each category means, which channels exist, and the clubs they can pick."""
    return {**notify.get_prefs(conn, p.workspace_id, p.user_id), "catalogue": [{"id": k, **c} for k, c in notify.CATEGORIES.items()],
            "channel_status": notify.channel_status(), "competitions_available": notify.COMPETITIONS, "teams_available": _known_teams(conn, p.workspace_id),
            "note": "Alerts appear in your notifications inside the app. Nothing is sent to anyone who has not chosen categories, and nothing leaves the app."}


@router.put("/alert-settings")
def put_alert_settings(body: PrefsBody, p: Auth, conn=Depends(get_conn)):
    try:
        v = notify.validate_prefs(body.categories, body.competitions, body.teams, body.channels, set(_known_teams(conn, p.workspace_id)))
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return notify.save_prefs(conn, p.workspace_id, p.user_id, v)


@router.get("/alert-events")
def alert_events(p: Auth, conn=Depends(get_conn), category: str | None = Query(None), limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0, le=5000)):
    """Recent football events in this workspace, whether or not anyone chose to be told, newest first."""
    if category and category not in notify.CATEGORIES:
        raise HTTPException(422, "Unknown category.")
    where, args = ["workspace_id=%s"], [p.workspace_id]
    if category:
        where.append("category=%s")
        args.append(category)
    sql = " and ".join(where)
    total = conn.execute(f"select count(*) n from football_notification_events where {sql}", args).fetchone()["n"]
    rows = conn.execute(f"select id, category, title, body, href, delivered, created_at from football_notification_events where {sql} order by created_at desc limit %s offset %s", [*args, limit, offset]).fetchall()
    return {"events": rows, "total": total}


TABLES = ["football_fixtures", "football_fixture_provider_mappings", "football_fixture_status_history", "football_sync_jobs", "football_provider_health", "football_prediction_versions",
          "football_prediction_evaluations", "football_live_settings", "football_refresh_runs", "football_notification_preferences", "football_notification_events", "football_performance_reports"]


@router.get("/readiness")
def readiness(p: Auth, conn=Depends(get_conn)):
    """What is and is not ready for live data, stated plainly. A provider is only 'verified' once a real fetch has succeeded."""
    now = sync.utcnow()
    h = sync.health(conn)
    missing = [t for t in TABLES if conn.execute("select to_regclass(%s) r", (f"public.{t}",)).fetchone()["r"] is None]
    last_sync = conn.execute("select max(finished_at) t from football_sync_jobs where workspace_id=%s and status='complete'", (p.workspace_id,)).fetchone()["t"]
    versions = conn.execute("select count(*) n from football_prediction_versions where workspace_id=%s", (p.workspace_id,)).fetchone()["n"]
    evals = conn.execute("select count(*) n from football_prediction_evaluations where workspace_id=%s and voided_at is null", (p.workspace_id,)).fetchone()["n"]
    tick = conn.execute("select max(started_at) t from football_job_runs where workspace_id=%s and kind='live'", (p.workspace_id,)).fetchone()["t"]
    secret = len(os.environ.get("CRON_SECRET", "")) >= 16

    def stale(t, mins: int) -> bool:
        return t is None or now - t > timedelta(minutes=mins)

    checks = [
        {"id": "database", "label": "Database tables for live football", "ok": not missing, "detail": "All present." if not missing else f"Missing: {', '.join(missing)}. Apply the migrations."},
        {"id": "provider_key", "label": "Fixture provider key on the server", "ok": fp.configured(), "detail": "FOOTBALL_DATA_API_KEY is set." if fp.configured() else "FOOTBALL_DATA_API_KEY is not set, so no fixtures can be fetched."},
        {"id": "provider_connectivity", "label": "A real fetch from the provider has succeeded", "ok": h["last_success_at"] is not None,
         "detail": f"Last success {h['last_success_at']:%Y-%m-%d %H:%M} UTC." if h["last_success_at"] else "Never. Connectivity is unverified until a synchronisation completes against the real provider."},
        {"id": "provider_health", "label": "Provider currently healthy", "ok": h["consecutive_failures"] == 0 and h["last_success_at"] is not None,
         "detail": f"{h['consecutive_failures']} failure(s) in a row. {h['last_error'] or ''}".strip() if h["consecutive_failures"] else "No recent failures."},
        {"id": "scheduler_secret", "label": "Scheduler secret configured", "ok": secret, "detail": "CRON_SECRET is set." if secret else "CRON_SECRET is not set, so the scheduled endpoints do not exist and nothing runs automatically."},
        {"id": "scheduler_running", "label": "Scheduler has acted recently", "ok": not stale(tick, 24 * 60), "detail": f"Last non-idle run {tick:%Y-%m-%d %H:%M} UTC." if tick else "No automatic run has been recorded for this workspace."},
        {"id": "fixtures_fresh", "label": "Fixtures synchronised in the last 12 hours", "ok": not stale(last_sync, 12 * 60), "detail": f"Last synchronisation {last_sync:%Y-%m-%d %H:%M} UTC." if last_sync else "Never synchronised."},
        {"id": "forecasts", "label": "Forecasts stored", "ok": versions > 0, "detail": f"{versions} version(s)." if versions else "None yet."},
        {"id": "evaluations", "label": "Results scored", "ok": evals > 0, "detail": f"{evals} match(es) scored." if evals else "None yet; scoring starts once a played match is reported with a verified result."},
    ]
    normal, live = fr.sync_intervals()
    return {"checks": checks, "ready": all(c["ok"] for c in checks[:6]), "connectivity_verified": h["last_success_at"] is not None,
            "intervals_minutes": {"fixture_sync": int(normal.total_seconds() // 60), "fixture_sync_near_kickoff": int(live.total_seconds() // 60)},
            "note": "Automated tests use mocked provider responses. Real connectivity is verified only by the provider check script or a completed synchronisation."}
