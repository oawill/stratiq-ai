"""Scheduled refresh of live forecasts (Phase 4E): one light "tick" that a scheduler can call every few minutes, safely and repeatedly.

A tick, per workspace, does only what is due:
  1. synchronise fixtures when the interval has passed (shorter around kickoff, longer otherwise; never faster than the shared response cache)
  2. re-forecast fixtures whose kickoff time moved
  3. make a first forecast for scheduled fixtures that have none
  4. re-forecast at each configured checkpoint before kickoff (default 48h, 24h, 6h and 1h), once per checkpoint per kickoff time

Everything is idempotent. A checkpoint is claimed with a unique row, so overlapping or repeated runs cannot do it twice; a forecast whose inputs did not
change stores nothing; a rescheduled match gets its checkpoints again. Late runs act only on the most recent checkpoint that has passed (earlier ones
are marked skipped), and nothing is ever generated at or after kickoff. Lineup-triggered refresh is not available: the provider plan in use supplies no
lineups, so nothing is faked. Provider trouble never stops the rest of a tick and never changes stored data.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

from . import football_forecast as ff
from . import football_performance as perf
from . import football_provider as fp
from . import football_results as results
from . import football_sync as sync

DEFAULT_CHECKPOINTS = (2880, 1440, 360, 60)
NAMED = {2880: "h48", 1440: "h24", 360: "h6", 60: "h1"}
MIN_CHECKPOINT, MAX_CHECKPOINT = 15, 14400            # 15 minutes to 10 days before kickoff
CLAIM_STALE = timedelta(minutes=10)                   # a claim older than this belongs to a run that died
MAX_ATTEMPTS = 3
LIVE_WINDOW_BEFORE, LIVE_WINDOW_AFTER = timedelta(hours=2), timedelta(hours=3)
TICK_BUDGET_SECONDS = 45.0                            # the API function limit is 60 seconds


class Lazy:
    """Match history, the latest backtest and uploaded statistics, loaded only if a forecast is actually generated: most ticks have nothing to do and cost one cheap query."""

    def __init__(self, conn, wid: str):
        self.conn, self.wid, self._v = conn, wid, None

    def _get(self):
        if self._v is None:
            self._v = ff._load(self.conn, self.wid)
        return self._v

    def __iter__(self):
        return iter(self._get())

    def __getitem__(self, i):
        return self._get()[i]

    def __bool__(self):
        return True


def log(event: str, **kw) -> None:
    """One structured JSON line per event, for the platform's log search."""
    print(json.dumps({"event": f"football.{event}", **kw}, default=str, sort_keys=True), flush=True)


def _int_env(name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(int(os.environ.get(name, default)), hi))
    except ValueError:
        return default


def sync_intervals() -> tuple[timedelta, timedelta]:
    """(normal, around-kickoff). The live interval cannot be shorter than the shared cache lifetime, and on the free plan scores are delayed by the provider anyway."""
    floor = int(sync.CACHE_TTL.total_seconds() // 60)
    return (timedelta(minutes=_int_env("FOOTBALL_SYNC_INTERVAL_MINUTES", 360, floor, 1440)), timedelta(minutes=_int_env("FOOTBALL_LIVE_INTERVAL_MINUTES", 15, floor, 120)))


# ---- settings -----------------------------------------------------------------------------------------------------------------------

def validate_checkpoints(values) -> list[int]:
    if not isinstance(values, list) or not 1 <= len(values) <= 8:
        raise ValueError("Choose between 1 and 8 checkpoints.")
    out = []
    for v in values:
        if isinstance(v, bool) or not isinstance(v, int) or not MIN_CHECKPOINT <= v <= MAX_CHECKPOINT:
            raise ValueError(f"Each checkpoint must be a whole number of minutes between {MIN_CHECKPOINT} and {MAX_CHECKPOINT} before kickoff.")
        out.append(v)
    if len(set(out)) != len(out):
        raise ValueError("Checkpoints must be different from each other.")
    return sorted(out, reverse=True)


def get_settings(conn, wid: str) -> dict:
    r = conn.execute("select checkpoint_minutes, auto_forecast, updated_at from football_live_settings where workspace_id=%s", (wid,)).fetchone()
    return {"checkpoint_minutes": sorted(r["checkpoint_minutes"], reverse=True), "auto_forecast": r["auto_forecast"], "updated_at": r["updated_at"], "default": False} if r else \
           {"checkpoint_minutes": list(DEFAULT_CHECKPOINTS), "auto_forecast": True, "updated_at": None, "default": True}


def save_settings(conn, wid: str, uid, minutes: list[int], auto: bool) -> dict:
    conn.execute("""insert into football_live_settings (workspace_id, checkpoint_minutes, auto_forecast, updated_by, updated_at) values (%s,%s,%s,%s,now())
                    on conflict (workspace_id) do update set checkpoint_minutes=excluded.checkpoint_minutes, auto_forecast=excluded.auto_forecast, updated_by=excluded.updated_by, updated_at=now()""",
                 (wid, validate_checkpoints(minutes), auto, uid))
    return get_settings(conn, wid)


def describe(minutes: int) -> str:
    if minutes % 1440 == 0:
        return f"{minutes // 1440} day{'s' if minutes > 1440 else ''}"
    if minutes % 60 == 0:
        return f"{minutes // 60} hour{'s' if minutes > 60 else ''}"
    return f"{minutes} minutes"


# ---- which checkpoint is due --------------------------------------------------------------------------------------------------------

def passed_checkpoints(kickoff: datetime, now: datetime, checkpoints: list[int]) -> list[int]:
    """Checkpoints whose moment has arrived and whose kickoff has not, closest to kickoff first."""
    if now >= kickoff:
        return []
    return sorted((m for m in checkpoints if kickoff - timedelta(minutes=m) <= now), )


def next_checkpoint(kickoff: datetime, now: datetime, checkpoints: list[int], handled: set[int]) -> tuple[int, datetime] | None:
    """The next checkpoint still to come (or overdue and unhandled), with its moment, for display."""
    todo = [(kickoff - timedelta(minutes=m), m) for m in checkpoints if m not in handled and now < kickoff]
    if not todo:
        return None
    at, m = min(todo)
    return m, at


# ---- steps ----------------------------------------------------------------------------------------------------------------------------

def sync_due(conn, wid: str, now: datetime) -> bool:
    normal, live = sync_intervals()
    last = conn.execute("select max(finished_at) filter (where status='complete') ok, max(started_at) any_try from football_sync_jobs where workspace_id=%s and provider=%s", (wid, fp.PROVIDER)).fetchone()
    if last["any_try"] and now - last["any_try"] < timedelta(minutes=5):
        return False                                           # never retry within five minutes, even after a failure
    near = conn.execute("""select 1 from football_fixtures where workspace_id=%s and status in ('scheduled','in_play','paused') and kickoff_utc between %s and %s limit 1""",
                        (wid, now - LIVE_WINDOW_AFTER, now + LIVE_WINDOW_BEFORE)).fetchone()
    interval = live if near else normal
    return last["ok"] is None or now - last["ok"] >= interval


def refresh_rescheduled(conn, wid: str, job_id: str, now: datetime, loaded=None) -> dict:
    """Re-forecast scheduled fixtures whose kickoff moved in this synchronisation (and that already had a forecast)."""
    rows = conn.execute("""select distinct f.* from football_fixture_status_history h join football_fixtures f on f.id=h.fixture_id
                           where h.sync_job_id=%s and h.old_kickoff is not null and h.new_kickoff is distinct from h.old_kickoff and f.status='scheduled'
                             and exists (select 1 from football_prediction_versions v where v.fixture_id=f.id)""", (job_id,)).fetchall()
    out = {"considered": len(rows), "created": 0}
    for f in rows:
        r = ff.generate_version(conn, f, "reschedule", "The provider moved the kickoff time.", now, loaded)
        out["created"] += r["status"] == "created"
    return out


def _claim(conn, wid: str, fx: dict, minutes: int, now: datetime):
    return conn.execute("""insert into football_refresh_runs (workspace_id, fixture_id, kickoff_utc, checkpoint_minutes, outcome, handled_at) values (%s,%s,%s,%s,'claimed',%s)
                           on conflict (fixture_id, kickoff_utc, checkpoint_minutes) do update set outcome='claimed', attempts=football_refresh_runs.attempts+1, handled_at=excluded.handled_at
                             where football_refresh_runs.attempts < %s and (football_refresh_runs.outcome='failed' or (football_refresh_runs.outcome='claimed' and football_refresh_runs.handled_at < %s))
                           returning id""", (wid, fx["id"], fx["kickoff_utc"], minutes, now, MAX_ATTEMPTS, now - CLAIM_STALE)).fetchone()


def refresh_checkpoints(conn, wid: str, now: datetime, checkpoints: list[int], loaded=None, deadline: float | None = None, limit: int = 20) -> dict:
    horizon = now + timedelta(minutes=max(checkpoints))
    fixtures = conn.execute("""select * from football_fixtures where workspace_id=%s and status='scheduled' and kickoff_utc > %s and kickoff_utc <= %s order by kickoff_utc""", (wid, now, horizon)).fetchall()
    out = {"considered": len(fixtures), "created": 0, "unchanged": 0, "ineligible": 0, "failed": 0, "skipped_late": 0, "deferred": 0}
    done = 0
    for fx in fixtures:
        passed = passed_checkpoints(fx["kickoff_utc"], now, checkpoints)
        if not passed:
            continue
        current, earlier = passed[0], passed[1:]                         # only the checkpoint closest to kickoff is acted on
        for m in earlier:                                                # earlier ones that were never handled are recorded as skipped, not run late
            conn.execute("""insert into football_refresh_runs (workspace_id, fixture_id, kickoff_utc, checkpoint_minutes, outcome, handled_at, detail) values (%s,%s,%s,%s,'skipped_late',%s,'A later checkpoint had already arrived.')
                            on conflict do nothing""", (wid, fx["id"], fx["kickoff_utc"], m, now))
        if done >= limit or (deadline is not None and time.monotonic() > deadline):
            out["deferred"] += 1
            continue
        claim = _claim(conn, wid, fx, current, now)
        if claim is None:
            continue                                                     # already handled (or being handled) for this kickoff time
        done += 1
        label = NAMED.get(current, "scheduled")
        try:
            with conn.transaction():                                     # a failure rolls back this fixture only
                r = ff.generate_version(conn, fx, label, f"{describe(current).capitalize()} before kickoff.", now, loaded)
        except Exception as e:                                           # noqa: BLE001 - one fixture failing must not stop the others
            conn.execute("update football_refresh_runs set outcome='failed', detail=%s where id=%s", (f"{type(e).__name__}: {e}"[:300], claim["id"]))
            out["failed"] += 1
            log("refresh_failed", workspace_id=wid, fixture_id=str(fx["id"]), checkpoint=current, error=f"{type(e).__name__}")
            continue
        conn.execute("update football_refresh_runs set outcome=%s, version_no=%s, detail=%s where id=%s", (r["status"], r.get("version_no"), (r.get("reason") or r.get("message") or "")[:300] or None, claim["id"]))
        out[r["status"]] += 1
    return out


# ---- the tick -------------------------------------------------------------------------------------------------------------------------

def tick_workspace(conn, wid: str, now: datetime | None = None, deadline: float | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    got = conn.execute("select pg_try_advisory_xact_lock(hashtext(%s)) ok", (f"football-tick:{wid}",)).fetchone()["ok"]
    if not got:
        return {"workspace_id": wid, "status": "busy"}
    cfg = get_settings(conn, wid)
    out: dict = {"workspace_id": wid, "status": "idle"}
    loaded = Lazy(conn, wid)
    if fp.configured() and sync_due(conn, wid, now):
        r = sync.sync_workspace(conn, wid, "schedule", now=now)
        out["sync"] = {k: r.get(k) for k in ("status", "fetched", "created", "updated", "unchanged", "message")}
        if r.get("job_id") and cfg["auto_forecast"] and r.get("status") == "complete":
            out["rescheduled"] = refresh_rescheduled(conn, wid, r["job_id"], now, loaded)
    out["results"] = results.reconcile_workspace(conn, wid, now)           # finished matches: score the official forecast, update history and tracking
    # the previous day's and week's reports are made in the morning (UTC) or as soon as results arrive; they exist once and only when something was scored
    out["reports"] = perf.make_reports(conn, wid, now) if now.hour < 12 or out["results"]["evaluated"] else {"created": []}
    if cfg["auto_forecast"]:
        out["first_forecasts"] = ff.generate_pending(conn, wid, now, loaded=loaded)
        out["checkpoints"] = refresh_checkpoints(conn, wid, now, cfg["checkpoint_minutes"], loaded, deadline)
    acted = any(out["results"].get(k) for k in ("evaluated", "no_forecast", "voided", "conflict", "errors")) or bool(out["reports"]["created"]) or any((out.get("sync") or {}).get(k) for k in ("created", "updated")) or (out.get("rescheduled") or {}).get("created") or (out.get("first_forecasts") or {}).get("created") \
        or any((out.get("checkpoints") or {}).get(k) for k in ("created", "failed")) or (out.get("sync") or {}).get("status") == "failed"
    out["status"] = "failed" if (out.get("sync") or {}).get("status") == "failed" else "acted" if acted else "idle"
    if out["status"] != "idle":
        conn.execute("insert into football_job_runs (workspace_id, kind, trigger, status, detail, started_at, finished_at) values (%s,'live','schedule',%s,%s,%s,now())",
                     (wid, "failed" if out["status"] == "failed" else "complete", json.dumps(out, default=str), now))
        log("tick", **{k: v for k, v in out.items() if k != "workspace_id"}, workspace_id=wid)
    return out


def tick_all(conn, now: datetime | None = None, budget: float = TICK_BUDGET_SECONDS) -> dict:
    """One light pass over every workspace that has match history, within a time budget. Workspaces left over are picked up by the next tick."""
    now = now or datetime.now(timezone.utc)
    deadline = time.monotonic() + budget
    wids = [str(r["workspace_id"]) for r in conn.execute("""select m.workspace_id from match_history m
                                                            left join football_job_runs j on j.workspace_id=m.workspace_id and j.kind='live'
                                                            group by m.workspace_id order by max(j.started_at) nulls first""").fetchall()]
    res, deferred = [], 0
    for i, wid in enumerate(wids):
        if time.monotonic() > deadline:
            deferred = len(wids) - i
            break
        try:
            with conn.transaction():
                res.append(tick_workspace(conn, wid, now, deadline))
        except Exception as e:                                        # noqa: BLE001 - one workspace failing must not stop the others
            res.append({"workspace_id": wid, "status": "error", "error": type(e).__name__})
            log("tick_error", workspace_id=wid, error=f"{type(e).__name__}: {e}"[:200])
    return {"workspaces": len(wids), "deferred": deferred, "results": res}
