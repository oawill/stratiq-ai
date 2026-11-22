"""Live fixtures API (Phase 4A): fixtures synchronised from the provider, with kickoff times in the caller's time zone.

Reading needs a signed-in member of the workspace; synchronising needs write access. No credential is ever returned.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query

from . import football_provider as fp
from . import football_sync as sync
from .db import get_conn
from .security import Auth, require_write

router = APIRouter(prefix="/api/v1/football/live", tags=["football-live"])
WINDOWS = ("today", "tomorrow", "week", "month", "all")
STATUSES = ("scheduled", "in_play", "paused", "finished", "awarded", "postponed", "suspended", "cancelled")


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise HTTPException(422, "Unknown time zone. Use a name such as Europe/London.") from None


def bounds(window: str, tz: ZoneInfo, now: datetime) -> tuple[datetime | None, datetime | None]:
    """UTC instants for the start and end of a window, where days begin and end at midnight in the caller's time zone."""
    local_today = now.astimezone(tz).date()
    def at(days: int) -> datetime:
        return datetime.combine(local_today + timedelta(days=days), time.min, tzinfo=tz).astimezone(timezone.utc)
    return {"today": (at(0), at(1)), "tomorrow": (at(1), at(2)), "week": (at(0), at(7)), "month": (at(0), at(30)), "all": (None, None)}[window]


def present(r: dict, tz: ZoneInfo) -> dict:
    k = r["kickoff_utc"]
    return {"id": str(r["id"]), "competition": r["competition"], "season": r["season"], "matchday": r["matchday"], "home_team": r["home_team"], "away_team": r["away_team"],
            "status": r["status"], "venue": r["venue"], "kickoff_utc": k, "kickoff_local": k.astimezone(tz).isoformat() if k else None, "time_zone": tz.key,
            "date": str(r["fixture_date"]), "source": r["provider"] or "uploaded file", "provider_updated_at": r["provider_updated_at"], "last_synced_at": r["last_synced_at"],
            "final_score": {"home": r["home_goals"], "away": r["away_goals"]} if r["home_goals"] is not None else None,
            "forecastable": r["status"] not in fp.INACTIVE and r["status"] not in fp.FINAL}


@router.get("/provider")
def provider_status(p: Auth, conn=Depends(get_conn)):
    """Whether live fixtures are configured, what the provider can and cannot supply, and its health. The key itself is never shown."""
    h = sync.health(conn)
    jobs = conn.execute("select id, trigger, status, fetched, created, updated, unchanged, skipped, error, started_at, finished_at from football_sync_jobs where workspace_id=%s order by started_at desc limit 5", (p.workspace_id,)).fetchall()
    return {"provider": fp.PROVIDER, "configured": fp.configured(), "capabilities": fp.CAPABILITIES, "rate_limit_per_minute": fp.per_minute_limit(),
            "health": {k: h.get(k) for k in ("last_success_at", "last_failure_at", "consecutive_failures", "last_error", "paused_until")},
            "freshness": sync.freshness(conn, p.workspace_id), "recent_jobs": jobs,
            "note": "Free-plan schedules and scores can be delayed by the provider. Connectivity is only confirmed once a synchronisation has completed."}


@router.get("/fixtures")
def fixtures(p: Auth, conn=Depends(get_conn), window: str = Query("week"), tz: str = Query("UTC", max_length=64), status: str | None = Query(None), team: str | None = Query(None, max_length=60),
             competition: str = Query("EPL", max_length=10), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=5000)):
    if window not in WINDOWS:
        raise HTTPException(422, f"window must be one of {', '.join(WINDOWS)}.")
    if status and status not in STATUSES:
        raise HTTPException(422, f"status must be one of {', '.join(STATUSES)}.")
    z = zone(tz)
    start, end = bounds(window, z, sync.utcnow())
    where, args = ["workspace_id=%s", "competition=%s", "kickoff_utc is not null"], [p.workspace_id, competition]
    if start:
        where += ["kickoff_utc >= %s", "kickoff_utc < %s"]
        args += [start, end]
    if status:
        where.append("status=%s")
        args.append(status)
    if team:
        like = "%" + team.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(home_team ilike %s or away_team ilike %s)")
        args += [like, like]
    sql = " and ".join(where)
    total = conn.execute(f"select count(*) n from football_fixtures where {sql}", args).fetchone()["n"]
    rows = conn.execute(f"select * from football_fixtures where {sql} order by kickoff_utc, home_team limit %s offset %s", [*args, limit, offset]).fetchall()
    fr = sync.freshness(conn, p.workspace_id)
    return {"fixtures": [present(r, z) for r in rows], "total": total, "window": window, "time_zone": z.key, "freshness": fr,
            "note": "Kickoff times come from the provider. This list only contains fixtures it has supplied." if rows else
                    ("No fixtures in this window." + (" " + fr["message"] if fr["message"] else ""))}


@router.get("/fixtures/{fixture_id}/history")
def history(fixture_id: str, p: Auth, conn=Depends(get_conn)):
    """Every status or kickoff change a synchronisation has seen for one fixture, oldest first."""
    try:
        f = conn.execute("select id from football_fixtures where id=%s and workspace_id=%s", (fixture_id, p.workspace_id)).fetchone()
    except Exception:
        raise HTTPException(404, "Fixture not found") from None
    if not f:
        raise HTTPException(404, "Fixture not found")
    rows = conn.execute("select old_status, new_status, old_kickoff, new_kickoff, observed_at from football_fixture_status_history where fixture_id=%s order by observed_at, id", (fixture_id,)).fetchall()
    return {"history": rows}


@router.post("/sync")
def run_sync(p: Auth, conn=Depends(get_conn)):
    """Fetch the next 30 days (and the last 7) from the provider now. At most once every five minutes per workspace."""
    require_write(p)
    now = sync.utcnow()
    if sync.recently_synced(conn, p.workspace_id, now):
        return {"status": "recent", "message": "Fixtures were refreshed in the last five minutes, so nothing was requested.", "freshness": sync.freshness(conn, p.workspace_id, now)}
    out = sync.sync_workspace(conn, p.workspace_id, "manual", now=now)
    conn.execute("insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'football.live_sync',%s)",
                 (p.workspace_id, p.user_id, __import__("json").dumps({k: out.get(k) for k in ("status", "fetched", "created", "updated", "unchanged", "skipped")}, default=str)))
    return {**out, "freshness": sync.freshness(conn, p.workspace_id)}
