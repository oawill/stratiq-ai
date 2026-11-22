"""Live fixtures API (Phase 4A): fixtures synchronised from the provider, with kickoff times in the caller's time zone.

Reading needs a signed-in member of the workspace; synchronising needs write access. No credential is ever returned.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query

from . import football_forecast as ff
from . import football_match as fmatch
from . import football_provider as fp
from . import football_sync as sync
from .db import get_conn
from .security import Auth, require_write

router = APIRouter(prefix="/api/v1/football/live", tags=["football-live"])
WINDOWS = ("today", "tomorrow", "week", "month", "recent", "all")
OUTCOME = ("home", "draw", "away")
STATUSES = ("scheduled", "in_play", "paused", "finished", "awarded", "postponed", "suspended", "cancelled", "completed")      # "completed" means finished or awarded
MODELS = ("ensemble", "dixon_coles")


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
    return {"today": (at(0), at(1)), "tomorrow": (at(1), at(2)), "week": (at(0), at(7)), "month": (at(0), at(30)), "recent": (at(-30), at(1)), "all": (None, None)}[window]


def present(r: dict, tz: ZoneInfo) -> dict:
    k = r["kickoff_utc"]
    return {"id": str(r["id"]), "competition": r["competition"], "season": r["season"], "matchday": r["matchday"], "home_team": r["home_team"], "away_team": r["away_team"],
            "status": r["status"], "venue": r["venue"], "kickoff_utc": k, "kickoff_local": k.astimezone(tz).isoformat() if k else None, "time_zone": tz.key,
            "date": str(r["fixture_date"]), "source": r["provider"] or "uploaded file", "provider_updated_at": r["provider_updated_at"], "last_synced_at": r["last_synced_at"],
            "final_score": {"home": r["home_goals"], "away": r["away_goals"]} if r["home_goals"] is not None else None,
            "forecastable": r["status"] not in fp.INACTIVE and r["status"] not in fp.FINAL}


def _fixture(conn, p, fixture_id: str) -> dict:
    try:
        uid = str(uuid.UUID(fixture_id))
    except ValueError:
        raise HTTPException(404, "Fixture not found") from None
    f = conn.execute("select * from football_fixtures where id=%s and workspace_id=%s", (uid, p.workspace_id)).fetchone()
    if not f:
        raise HTTPException(404, "Fixture not found")
    return f


def result_check(fx: dict, off: dict | None) -> dict | None:
    """What happened against what the official pre-kickoff forecast said. A plain comparison of stored values; scoring metrics are not computed or stored here."""
    if fx["home_goals"] is None or fx["away_goals"] is None:
        return {"available": False, "note": "The provider has not supplied a verified full-time score yet."}
    actual = 0 if fx["home_goals"] > fx["away_goals"] else 1 if fx["home_goals"] == fx["away_goals"] else 2
    if not off:
        return {"available": False, "outcome": OUTCOME[actual], "note": "No official forecast was made before kickoff, so there is nothing to compare."}
    probs = [off["p_home"], off["p_draw"], off["p_away"]]
    top = max(range(3), key=lambda i: probs[i])
    return {"available": True, "outcome": OUTCOME[actual], "most_likely": OUTCOME[top], "most_likely_was_right": top == actual, "probability_given_to_outcome": round(probs[actual], 4),
            "version_no": off["version_no"], "note": "One match says little about a model. Judge it on the Model performance tab."}


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
             competition: str = Query("EPL", max_length=10), forecast: str | None = Query(None, pattern="^(yes|no)$"), model: str | None = Query(None), day: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=5000)):
    if window not in WINDOWS:
        raise HTTPException(422, f"window must be one of {', '.join(WINDOWS)}.")
    if status and status not in STATUSES:
        raise HTTPException(422, f"status must be one of {', '.join(STATUSES)}.")
    if model and model not in MODELS:
        raise HTTPException(422, f"model must be one of {', '.join(MODELS)}.")
    z = zone(tz)
    start, end = bounds(window, z, sync.utcnow())
    if day:                                       # one calendar day in the caller's time zone
        try:
            d = datetime.strptime(day, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(422, "day must be a real date (YYYY-MM-DD).") from None
        start = datetime.combine(d, time.min, tzinfo=z).astimezone(timezone.utc)
        end = datetime.combine(d + timedelta(days=1), time.min, tzinfo=z).astimezone(timezone.utc)
    where, args = ["workspace_id=%s", "competition=%s", "kickoff_utc is not null"], [p.workspace_id, competition]
    if start:
        where += ["kickoff_utc >= %s", "kickoff_utc < %s"]
        args += [start, end]
    if status == "completed":
        where.append("status in ('finished','awarded')")
    elif status:
        where.append("status=%s")
        args.append(status)
    if model:
        where.append("exists (select 1 from football_prediction_versions v where v.fixture_id=football_fixtures.id and v.model_name=%s)")
        args.append(model)
    if team:
        like = "%" + team.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(home_team ilike %s or away_team ilike %s)")
        args += [like, like]
    if forecast:
        where.append(("" if forecast == "yes" else "not ") + "exists (select 1 from football_prediction_versions v where v.fixture_id=football_fixtures.id)")
    sql = " and ".join(where)
    total = conn.execute(f"select count(*) n from football_fixtures where {sql}", args).fetchone()["n"]
    rows = conn.execute(f"select * from football_fixtures where {sql} order by kickoff_utc, home_team limit %s offset %s", [*args, limit, offset]).fetchall()
    fr = sync.freshness(conn, p.workspace_id)
    ids = [r["id"] for r in rows]
    latest = {str(v["fixture_id"]): v for v in conn.execute("select distinct on (fixture_id) * from football_prediction_versions where fixture_id = any(%s) order by fixture_id, version_no desc", (ids,)).fetchall()} if rows else {}
    official = {str(v["fixture_id"]): v for v in conn.execute("select * from football_prediction_versions where fixture_id = any(%s) and is_official", (ids,)).fetchall()} if rows else {}
    items = []
    for r in rows:
        it = present(r, z)
        final = r["status"] in fp.FINAL
        v = (official.get(it["id"]) if final else None) or latest.get(it["id"])
        it["forecast"] = {k: ff.present(v)[k] for k in ("version_no", "official", "generated_at", "percent", "model")} if v else None
        it["result_check"] = result_check(r, official.get(it["id"])) if final else None
        items.append(it)
    return {"fixtures": items, "total": total, "window": window, "time_zone": z.key, "freshness": fr,
            "note": "Kickoff times come from the provider. This list only contains fixtures it has supplied." if rows else
                    ("No fixtures in this window." + (" " + fr["message"] if fr["message"] else ""))}


@router.get("/fixtures/{fixture_id}/history")
def history(fixture_id: str, p: Auth, conn=Depends(get_conn)):
    """Every status or kickoff change a synchronisation has seen for one fixture, oldest first."""
    _fixture(conn, p, fixture_id)
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


COMPARE_KEYS = ("matches_played", "form_5", "form_5_ppg", "form_10_ppg", "goals_for_avg", "goals_against_avg", "clean_sheet_rate", "over_2_5_rate", "btts_rate", "rest_days", "league_position", "points")


def comparison(sn: dict) -> dict:
    """The two clubs side by side, read from the frozen snapshot behind the forecast (results dated before its cutoff), plus which factors had no data."""
    f = sn["features"]
    def side(role: str) -> dict:
        return {k: f.get(f"{role}_{k}") for k in COMPARE_KEYS} | {"home_record": f.get(f"{role}_home_record"), "away_record": f.get(f"{role}_away_record"), "elo": f.get(f"elo_{role}")}
    return {"cutoff": str(sn["cutoff"]), "home": side("home"), "away": side("away"), "head_to_head": f.get("head_to_head"), "elo_difference": f.get("elo_difference"),
            "factors": {k: {"status": v["status"], "note": v["note"], "source": v["source"]} for k, v in sn["availability"].items()},
            "note": "Historical statistics from imported results dated before the cutoff. Player availability is not supplied by the provider plan in use."}


@router.get("/fixtures/{fixture_id}/forecast")
def forecast(fixture_id: str, p: Auth, conn=Depends(get_conn)):
    """The latest forecast for a fixture, the official evaluation forecast once one is marked, and why there is none if there is none."""
    f = _fixture(conn, p, fixture_id)
    latest = conn.execute("select * from football_prediction_versions where fixture_id=%s order by version_no desc limit 1", (f["id"],)).fetchone()
    official = conn.execute("select * from football_prediction_versions where fixture_id=%s and is_official", (f["id"],)).fetchone()
    n = conn.execute("select count(*) n from football_prediction_versions where fixture_id=%s", (f["id"],)).fetchone()["n"]
    why = None if latest else (ff.eligibility(f, sync.utcnow()) or "No forecast has been generated yet. The next scheduled run will create one, or a member can request it.")
    snap = None
    if latest:
        sn = conn.execute("select features, availability, cutoff from football_feature_snapshots where id=%s", (latest["snapshot_id"],)).fetchone()
        snap = comparison(sn) if sn else None
    return {"fixture_id": str(f["id"]), "status": f["status"], "snapshot": snap, "latest": ff.present(latest) if latest else None, "official": ff.present(official) if official else None, "versions": n,
            "no_forecast_reason": why, "official_note": "The official evaluation forecast is the last one made before kickoff; it is the one scored once the result is known."}


@router.get("/fixtures/{fixture_id}/match")
def match_page(fixture_id: str, p: Auth, conn=Depends(get_conn)):
    """Everything the match page shows, in sections labelled historical, verified or model estimate."""
    return fmatch.build(conn, _fixture(conn, p, fixture_id), sync.utcnow())


@router.get("/fixtures/{fixture_id}/forecasts")
def forecast_versions(fixture_id: str, p: Auth, conn=Depends(get_conn), limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=1000)):
    """Every stored version, newest first. Earlier versions are never altered or removed."""
    f = _fixture(conn, p, fixture_id)
    rows = conn.execute("select * from football_prediction_versions where fixture_id=%s order by version_no desc limit %s offset %s", (f["id"], limit, offset)).fetchall()
    total = conn.execute("select count(*) n from football_prediction_versions where fixture_id=%s", (f["id"],)).fetchone()["n"]
    return {"versions": [ff.present(v) for v in rows], "total": total}


@router.post("/fixtures/{fixture_id}/forecast")
def make_forecast(fixture_id: str, p: Auth, conn=Depends(get_conn)):
    """Generate a forecast now. Stores a new version only if something the forecast depends on has changed."""
    require_write(p)
    f = _fixture(conn, p, fixture_id)
    out = ff.generate_version(conn, f, "manual", "Requested by a member.")
    if out["status"] == "ineligible":
        raise HTTPException(409, out["reason"])
    conn.execute("insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'football.live_forecast',%s)",
                 (p.workspace_id, p.user_id, json.dumps({"fixture_id": str(f["id"]), "result": out["status"], "version_no": out.get("version_no")})))
    return out


@router.get("/forecast-history")
def forecast_history(p: Auth, conn=Depends(get_conn), team: str | None = Query(None, max_length=60), model: str | None = Query(None), fixture_id: str | None = Query(None),
                     limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0, le=5000), tz: str = Query("UTC", max_length=64)):
    """Every stored forecast version in the workspace, newest first, with its fixture. Earlier versions are never altered or removed."""
    z = zone(tz)
    if model and model not in MODELS:
        raise HTTPException(422, f"model must be one of {', '.join(MODELS)}.")
    where, args = ["v.workspace_id=%s"], [p.workspace_id]
    if team:
        like = "%" + team.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(f.home_team ilike %s or f.away_team ilike %s)")
        args += [like, like]
    if model:
        where.append("v.model_name=%s")
        args.append(model)
    if fixture_id:
        try:
            args.append(str(uuid.UUID(fixture_id)))
        except ValueError:
            raise HTTPException(404, "Fixture not found") from None
        where.append("v.fixture_id=%s")
    sql = " and ".join(where)
    total = conn.execute(f"select count(*) n from football_prediction_versions v join football_fixtures f on f.id=v.fixture_id where {sql}", args).fetchone()["n"]
    rows = conn.execute(f"""select v.*, f.home_team, f.away_team, f.status as fixture_status, f.home_goals, f.away_goals from football_prediction_versions v join football_fixtures f on f.id=v.fixture_id
                            where {sql} order by v.generated_at desc, v.version_no desc limit %s offset %s""", [*args, limit, offset]).fetchall()
    out = []
    for v in rows:
        o = ff.present(v)
        out.append({k: o[k] for k in ("id", "version_no", "official", "generated_at", "kickoff_utc", "checkpoint", "refresh_reason", "model", "percent", "change_from_previous")} |
                   {"fixture_id": str(v["fixture_id"]), "home_team": v["home_team"], "away_team": v["away_team"], "fixture_status": v["fixture_status"], "time_zone": z.key,
                    "final_score": {"home": v["home_goals"], "away": v["away_goals"]} if v["home_goals"] is not None else None})
    return {"versions": out, "total": total}
