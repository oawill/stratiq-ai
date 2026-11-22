"""Football alerts (Phase 4G): record each football event once, then deliver it to the people who asked for it.

Delivery is in-app, through the existing `notifications` table, so it inherits that system's rules: a person's in-app switch, quiet hours (held back, not
lost), the daily cap, and deduplication (one notification per person per event, even if the event is raised again or the notification is deleted).
Nothing is sent to anyone who has not opted in: with no football preferences, or no chosen categories, nobody is notified. Events are recorded
whether or not anyone is listening, once each (the workspace plus a dedupe key is unique).

Email and push are designed as adapters (`Channel`) that are consulted only for people who switched that channel on, and only when the adapter reports
itself available. None is implemented or configured today, so none can be switched on and nothing leaves the application.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone

from . import alerts
from . import preferences_api as prefs

CATEGORIES: dict[str, dict] = {
    "new_fixture": {"label": "New fixtures", "description": "A fixture is added to the schedule.", "team_scoped": True, "available": True},
    "new_prediction": {"label": "New predictions", "description": "A first forecast is made for a fixture.", "team_scoped": True, "available": True},
    "probability_change": {"label": "Significant probability changes", "description": "A refreshed forecast moves an outcome by 5 percentage points or more.", "team_scoped": True, "available": True},
    "lineup_change": {"label": "Confirmed lineup changes", "description": "A confirmed lineup changes the forecast.", "team_scoped": True, "available": False,
                      "unavailable_reason": "The fixture provider plan in use supplies no lineups, so this alert cannot fire."},
    "final_result": {"label": "Final match results", "description": "A verified full-time result is recorded, or the provider corrects one.", "team_scoped": True, "available": True},
    "evaluation_complete": {"label": "Prediction evaluation completed", "description": "The official forecast has been scored against the result.", "team_scoped": True, "available": True},
    "provider_failure": {"label": "Provider failures", "description": "The fixture provider has failed several times in a row.", "team_scoped": False, "available": True},
    "data_quality": {"label": "Data quality issues", "description": "A result conflicts with your uploaded data, a club name is not recognised, or a fixture cannot be forecast.", "team_scoped": False, "available": True},
}
AVAILABLE = [k for k, v in CATEGORIES.items() if v["available"]]
COMPETITIONS = ["EPL"]
MAX_TEAMS = 20
FANOUT_MAX_FIXTURES = 5          # more new fixtures than this in one synchronisation become a single summary event


@contextmanager
def guard(conn, what: str):
    """Run notification work so that it can never break the pipeline that raised it: it gets its own savepoint, and any failure is logged and swallowed."""
    try:
        with conn.transaction():
            yield
    except Exception as e:                                                  # noqa: BLE001
        print(json.dumps({"event": "football.notify_failed", "what": what, "error": f"{type(e).__name__}: {e}"[:200]}), flush=True)


# ---- channels (designed, none implemented) ------------------------------------------------------------------------------------------

class Channel:
    """An optional delivery channel besides the app. A subclass reports whether it can be used and sends one event to one person; it is never called for anyone who has not switched it on."""
    name = "channel"

    def available(self) -> tuple[bool, str]:
        return False, "Not available."

    def send(self, user_id: str, event: dict) -> bool:
        raise NotImplementedError


class EmailChannel(Channel):
    name = "email"

    def available(self) -> tuple[bool, str]:
        return False, "Email delivery is not connected to the analytics service, so football alerts are not emailed."


class PushChannel(Channel):
    name = "push"

    def available(self) -> tuple[bool, str]:
        return False, "Push notifications are not set up."


CHANNELS: dict[str, Channel] = {"email": EmailChannel(), "push": PushChannel()}


def channel_status() -> dict:
    return {n: dict(zip(("available", "reason"), c.available())) for n, c in CHANNELS.items()}


# ---- preferences --------------------------------------------------------------------------------------------------------------------

def get_prefs(conn, wid: str, uid: str) -> dict:
    r = conn.execute("select categories, competitions, teams, channels, updated_at from football_notification_preferences where workspace_id=%s and user_id=%s", (wid, uid)).fetchone()
    if not r:
        return {"categories": [], "competitions": ["EPL"], "teams": [], "channels": {"email": False, "push": False}, "updated_at": None, "configured": False}
    return {"categories": list(r["categories"]), "competitions": list(r["competitions"]), "teams": list(r["teams"]), "channels": r["channels"], "updated_at": r["updated_at"], "configured": True}


def validate_prefs(categories: list[str], competitions: list[str], teams: list[str], channels: dict, known_teams: set[str]) -> dict:
    cats = sorted(set(categories))
    bad = [c for c in cats if c not in CATEGORIES]
    if bad:
        raise ValueError(f"Unknown alert categories: {', '.join(bad)}.")
    na = [c for c in cats if not CATEGORIES[c]["available"]]
    if na:
        raise ValueError(f"{CATEGORIES[na[0]]['label']} cannot be switched on: {CATEGORIES[na[0]]['unavailable_reason']}")
    comps = sorted(set(competitions)) or ["EPL"]
    if any(c not in COMPETITIONS for c in comps):
        raise ValueError(f"Supported competitions: {', '.join(COMPETITIONS)}.")
    tm = sorted(set(teams))
    if len(tm) > MAX_TEAMS:
        raise ValueError(f"Choose at most {MAX_TEAMS} teams.")
    unknown = [t for t in tm if t not in known_teams]
    if unknown:
        raise ValueError(f"Not a club in your match history: {', '.join(unknown)}.")
    ch = {"email": bool(channels.get("email")), "push": bool(channels.get("push"))}
    for name, on in ch.items():
        ok, why = CHANNELS[name].available()
        if on and not ok:
            raise ValueError(why)
    return {"categories": cats, "competitions": comps, "teams": tm, "channels": ch}


def save_prefs(conn, wid: str, uid: str, v: dict) -> dict:
    conn.execute("""insert into football_notification_preferences (workspace_id, user_id, categories, competitions, teams, channels, updated_at) values (%s,%s,%s,%s,%s,%s,now())
                    on conflict (workspace_id, user_id) do update set categories=excluded.categories, competitions=excluded.competitions, teams=excluded.teams, channels=excluded.channels, updated_at=now()""",
                 (wid, uid, v["categories"], v["competitions"], v["teams"], json.dumps(v["channels"])))
    return get_prefs(conn, wid, uid)


# ---- emitting and delivering --------------------------------------------------------------------------------------------------------

def matches(pref: dict, event: dict) -> bool:
    """Does this person's choice cover this event? Team-scoped alerts need one of the chosen teams (if any were chosen); provider and data alerts ignore teams."""
    if event["category"] not in pref["categories"] or event["competition"] not in pref["competitions"]:
        return False
    if pref["teams"] and CATEGORIES[event["category"]]["team_scoped"]:
        return bool(set(event["teams"]) & set(pref["teams"]))                  # a summary event carries no teams, so it does not reach people who chose specific teams
    return True


def emit(conn, wid: str, category: str, title: str, body: str, dedupe_key: str, fixture_id=None, teams: list[str] | None = None, href: str | None = None,
         detail: dict | None = None, competition: str = "EPL", now: datetime | None = None) -> dict:
    """Record the event once and deliver it. A repeated event (same dedupe key) records and delivers nothing."""
    if category not in CATEGORIES:
        raise ValueError("Unknown category")
    now = now or datetime.now(timezone.utc)
    row = conn.execute("""insert into football_notification_events (workspace_id, category, fixture_id, competition, teams, title, body, href, detail, dedupe_key, created_at)
                          values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict (workspace_id, dedupe_key) do nothing returning id""",
                       (wid, category, fixture_id, competition, teams or [], title[:200], body[:600], href, json.dumps(detail or {}, default=str), dedupe_key[:250], now)).fetchone()
    if row is None:
        return {"status": "duplicate", "delivered": 0}
    event = {"id": str(row["id"]), "workspace_id": wid, "category": category, "competition": competition, "teams": teams or [], "title": title[:200], "body": body[:600], "href": href}
    out = deliver(conn, event, now)
    conn.execute("update football_notification_events set delivered=%s where id=%s", (out["delivered"], row["id"]))
    return {"status": "recorded", "event_id": event["id"], **out}


def deliver(conn, event: dict, now: datetime) -> dict:
    out = {"delivered": 0, "duplicates": 0, "dropped": 0, "filtered": 0, "quiet": 0, "channel_sent": 0, "channel_failed": 0}
    wid = event["workspace_id"]
    rows = conn.execute("select user_id, categories, competitions, teams, channels from football_notification_preferences where workspace_id=%s and cardinality(categories) > 0 and %s = any(categories)",
                        (wid, event["category"])).fetchall()
    for r in rows:
        uid = str(r["user_id"])
        if not matches({"categories": r["categories"], "competitions": r["competitions"], "teams": r["teams"]}, event):
            out["filtered"] += 1
            continue
        member = conn.execute("select 1 from workspace_members where workspace_id=%s and user_id=%s", (wid, uid)).fetchone()
        if not member:
            continue
        pr = prefs.load(conn, uid)["notifications"]
        if pr["in_app"]:
            total = conn.execute("select count(*) n from notifications where workspace_id=%s and user_id=%s and created_at > now() - interval '1 day'", (wid, uid)).fetchone()["n"]
            if total >= alerts.PER_USER_PER_DAY:
                out["dropped"] += 1
            else:
                release = alerts.quiet_release(now, pr["quiet_hours"])
                cand = {"dedupe_key": f"football:{event['id']}", "title": event["title"], "body": event["body"], "source": {"href": event["href"], "type": "football", "category": event["category"]}}
                if alerts.create(conn, wid, uid, None, f"football_{event['category']}", cand, release):
                    out["delivered"] += 1
                    out["quiet"] += release is not None
                else:
                    out["duplicates"] += 1
        for name, on in (r["channels"] or {}).items():                    # optional channels: only for people who switched one on, and only if it is available
            ch = CHANNELS.get(name)
            if on and ch and ch.available()[0]:
                try:
                    out["channel_sent" if ch.send(uid, event) else "channel_failed"] += 1
                except Exception:                                          # noqa: BLE001 - a failing channel must never stop the others or the app
                    out["channel_failed"] += 1
    return out


def purge_old_events(conn, days: int = 90) -> int:
    return conn.execute("delete from football_notification_events where created_at < now() - make_interval(days => %s)", (days,)).rowcount


# ---- the events the football pipeline raises ----------------------------------------------------------------------------------------

def _href(fixture_id) -> str:
    return f"/dashboard/sports/football/matches/{fixture_id}"


def _pct(p: float) -> str:
    return f"{p * 100:.0f}%"


def new_fixtures(conn, wid: str, fixtures: list[dict], job_id: str, now: datetime) -> None:
    if not fixtures:
        return
    if len(fixtures) <= FANOUT_MAX_FIXTURES:
        for f in fixtures:
            emit(conn, wid, "new_fixture", f"New fixture: {f['home_team']} v {f['away_team']}", f"Added to the schedule for {f['fixture_date']}.", f"new_fixture:{f['id']}", f["id"], [f["home_team"], f["away_team"]], _href(f["id"]), now=now)
    else:
        emit(conn, wid, "new_fixture", f"{len(fixtures)} new fixtures", f"{len(fixtures)} fixtures were added to the schedule.", f"new_fixtures:{job_id}", None, [], "/dashboard/sports/live?tab=upcoming", {"count": len(fixtures)}, now=now)


def forecast_made(conn, fx: dict, version_no: int, probs: tuple[float, float, float], change: dict | None, now: datetime) -> None:
    wid, teams = str(fx["workspace_id"]), [fx["home_team"], fx["away_team"]]
    line = f"Home {_pct(probs[0])}, draw {_pct(probs[1])}, away {_pct(probs[2])}."
    if version_no == 1:
        emit(conn, wid, "new_prediction", f"New forecast: {teams[0]} v {teams[1]}", line + " A model estimate, not a certainty.", f"new_prediction:{fx['id']}", fx["id"], teams, _href(fx["id"]), now=now)
    elif change and change.get("significant"):
        emit(conn, wid, "probability_change", f"Forecast moved: {teams[0]} v {teams[1]}",
             f"Version {version_no} moved an outcome by {change['max_abs_change'] * 100:.1f} points. {line}", f"probability_change:{fx['id']}:{version_no}", fx["id"], teams, _href(fx["id"]), {"change": change}, now=now)


def result_recorded(conn, fx: dict, revision: int, correction: bool, now: datetime) -> None:
    wid, teams = str(fx["workspace_id"]), [fx["home_team"], fx["away_team"]]
    score = f"{fx['home_goals']}–{fx['away_goals']}"
    verb = "Score corrected" if correction else "Full time"
    emit(conn, wid, "final_result", f"{verb}: {teams[0]} {score} {teams[1]}", "Verified result from the fixture provider." if not correction else "The provider corrected the score; the forecast was scored again.",
         f"final_result:{fx['id']}:{revision}", fx["id"], teams, _href(fx["id"]), now=now)


def evaluation_done(conn, fx: dict, version_no: int, log_loss: float, correct: bool, corrections: int, now: datetime) -> None:
    wid, teams = str(fx["workspace_id"]), [fx["home_team"], fx["away_team"]]
    emit(conn, wid, "evaluation_complete", f"Forecast scored: {teams[0]} v {teams[1]}", f"The official forecast (version {version_no}) {'named the right result as most likely' if correct else 'did not name the right result as most likely'}; log loss {log_loss:.3f}.",
         f"evaluation:{fx['id']}:{corrections}", fx["id"], teams, _href(fx["id"]), now=now)


def provider_failing(conn, wid: str, streak: int, last_success: datetime | None, message: str | None, now: datetime) -> None:
    emit(conn, wid, "provider_failure", "The fixture provider is failing", f"It has failed {streak} times in a row. Stored fixtures and forecasts are unchanged and shown with their last verified time. {message or ''}".strip(),
         f"provider_failure:{last_success.isoformat() if last_success else 'never'}", None, [], "/dashboard/sports/live", {"streak": streak}, now=now)


def data_issue(conn, wid: str, key: str, title: str, body: str, fixture=None, now: datetime | None = None) -> None:
    emit(conn, wid, "data_quality", title, body, f"data_quality:{key}", fixture["id"] if fixture else None, [], _href(fixture["id"]) if fixture else "/dashboard/sports/live", now=now)
