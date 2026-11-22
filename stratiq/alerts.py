"""Smart alerts: user-scoped rules, event triggers, deduplication, quiet hours and rate limiting. In-app only.

Nothing is created for anyone by default: notifications come only from rules a person switched on. Each rule looks at real records (imported
results, fixtures, scored forecasts, data freshness, model monitoring) and turns a new event into at most one notification: the `dedupe_key`
identifies the event, so evaluating again never repeats it. Quiet hours do not delete anything: a notification created during them is held
back (`visible_after`) until they end. Email and push do not exist, so nothing is ever sent outside the app.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from . import football_jobs as jobs
from . import preferences_api as prefs
from .football_api import _stored
from .football_intel_api import COMPETITION, freshness_of

PER_USER_PER_DAY = 30
PER_RULE_PER_DAY = 10
THROTTLE_SECONDS = 60
RETENTION_DAYS = 90

RULE_KINDS: dict[str, dict] = {
    "watched_result": {"label": "A result for a club you watch", "description": "When a match involving a club on your watchlist is imported after you switch this on.", "config": {}, "needs": "A watched club and imported results."},
    "fixture_soon": {"label": "A watched fixture is coming up", "description": "When a fixture on your watchlist is within the number of days you choose.", "config": {"days": {"min": 1, "max": 14, "default": 2}}, "needs": "A watched imported fixture."},
    "forecast_scored": {"label": "A forecast you saved was scored", "description": "When the result of a match you saved a forecast for is imported.", "config": {}, "needs": "Saved forecasts."},
    "data_stale": {"label": "Your match data may be stale", "description": "When the newest imported result is old for the time of year.", "config": {}, "needs": "Imported results."},
    "model_drift": {"label": "Model drift or retraining due", "description": "When live forecasts are doing materially worse than their backtest, or a retrain is due.", "config": {}, "needs": "A backtest and scored forecasts."},
    "briefing_ready": {"label": "A briefing is ready", "description": "When a briefing you generated or scheduled is created.", "config": {}, "needs": "Briefings switched on."},
}
SUGGESTED = ["watched_result", "forecast_scored", "data_stale"]


# ------------------------------------------------------------------ quiet hours (pure)
def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def quiet_release(now: datetime, quiet: dict) -> datetime | None:
    """If `now` falls inside the person's quiet hours, the moment they end (UTC); otherwise None. The window may cross midnight."""
    if not quiet.get("enabled"):
        return None
    start, end = _minutes(quiet["start"]), _minutes(quiet["end"])
    if start == end:
        return None
    local = now + timedelta(minutes=quiet.get("utc_offset_minutes", 0))
    cur = local.hour * 60 + local.minute
    inside = start <= cur < end if start < end else (cur >= start or cur < end)
    if not inside:
        return None
    wait = (end - cur) % (24 * 60)
    return (now.replace(second=0, microsecond=0) + timedelta(minutes=wait))


# ------------------------------------------------------------------ candidate events per rule kind
def _cand(key: str, title: str, body: str, href: str, retrieved: str | None = None, kind: str = "observed") -> dict:
    return {"dedupe_key": key[:300], "title": title[:200], "body": body[:600], "source": {"href": href, "retrieved_at": retrieved, "type": kind}}


def candidates(conn, wid: str, uid: str, rule: dict, now: datetime) -> list[dict]:
    k, cfg, since = rule["kind"], rule["config"] or {}, rule["created_at"]
    today = now.date()
    out: list[dict] = []
    if k == "watched_result":
        teams = [r["item_key"] for r in conn.execute("select item_key from watchlist_items where workspace_id=%s and user_id=%s and domain='sports' and kind='team'", (wid, uid)).fetchall()]
        if teams:
            for r in conn.execute("""select match_date, home_team, away_team, home_goals, away_goals, imported_at from match_history where workspace_id=%s and competition=%s and imported_at > %s
                                     and (home_team = any(%s) or away_team = any(%s)) order by imported_at desc limit 20""", (wid, COMPETITION, since, teams, teams)).fetchall():
                d = r["match_date"].isoformat()
                out.append(_cand(f"result:{d}:{r['home_team']}:{r['away_team']}", f"{r['home_team']} {r['home_goals']}-{r['away_goals']} {r['away_team']}",
                                 f"Result of {d}, imported into your workspace. Observed from your data, not a forecast.", "/dashboard/sports", r["imported_at"].isoformat()))
    elif k == "fixture_soon":
        days = int(cfg.get("days", 2))
        for r in conn.execute("select item_key, label from watchlist_items where workspace_id=%s and user_id=%s and domain='sports' and kind='fixture'", (wid, uid)).fetchall():
            d, home, away = r["item_key"].split("|")
            fd = date.fromisoformat(d)
            if today <= fd <= today + timedelta(days=days):
                left = (fd - today).days
                out.append(_cand(f"fixture:{r['item_key']}:{days}", f"{home} v {away} {'today' if left == 0 else 'in ' + str(left) + (' day' if left == 1 else ' days')}",
                                 f"An imported fixture on your watchlist is on {d}.", "/dashboard/watchlists"))
    elif k == "forecast_scored":
        for r in conn.execute("""select pr.fixture_date, pr.home_team, pr.away_team, max(o.home_goals) hg, max(o.away_goals) ag, max(o.scored_at) scored, count(*) n
                                 from football_predictions pr join football_prediction_outcomes o on o.prediction_id=pr.id where pr.workspace_id=%s and pr.kind='live' and o.scored_at > %s
                                 group by pr.fixture_date, pr.home_team, pr.away_team order by scored desc limit 20""", (wid, since)).fetchall():
            out.append(_cand(f"scored:{r['fixture_date'].isoformat()}:{r['home_team']}:{r['away_team']}", f"Your forecast for {r['home_team']} v {r['away_team']} was scored",
                             f"The match ended {r['hg']}-{r['ag']}. {r['n']} saved forecast{'s' if r['n'] != 1 else ''} for it {'were' if r['n'] != 1 else 'was'} scored against the result.", "/dashboard/sports", r["scored"].isoformat()))
    elif k == "data_stale":
        rows = _stored(conn, wid, COMPETITION)
        fr = freshness_of(rows, 0, None, today)
        if fr.get("stale"):
            out.append(_cand(f"stale:{fr['last_match']}", "Your match data may be stale", fr["note"], "/dashboard/data"))
    elif k == "model_drift":
        mon = jobs.monitor(conn, wid, today)
        if mon.get("has_history") and mon.get("run_id"):
            status = mon["drift"]["status"]
            due = mon["retrain"]["retrain"]
            if status == "drift" or due:
                why = mon["retrain"]["reasons"][0] if mon["retrain"]["reasons"] else "Live forecasts are doing worse than their backtest."
                out.append(_cand(f"drift:{mon['run_id']}:{status}:{int(due)}", "Model drift or retraining due" if status == "drift" else "Retraining is due", why, "/dashboard/sports"))
    return out


# ------------------------------------------------------------------ evaluation
def _today_counts(conn, wid: str, uid: str, rule_id) -> tuple[int, int]:
    """Created in the last day, deleted or not: deleting a notification does not free up room under the caps."""
    n = conn.execute("select count(*) n from notifications where workspace_id=%s and user_id=%s and created_at > now() - interval '1 day'", (wid, uid)).fetchone()["n"]
    r = conn.execute("select count(*) n from notifications where workspace_id=%s and user_id=%s and rule_id=%s and created_at > now() - interval '1 day'", (wid, uid, rule_id)).fetchone()["n"]
    return n, r


def create(conn, wid: str, uid: str, rule_id, kind: str, cand: dict, visible_after: datetime | None) -> bool:
    """`visible_after` None means visible immediately (the database clock decides, so there is no skew with the app clock)."""
    row = conn.execute("""insert into notifications (workspace_id, user_id, rule_id, kind, title, body, source, dedupe_key, visible_after) values (%s,%s,%s,%s,%s,%s,%s,%s,coalesce(%s, now()))
                          on conflict (workspace_id, user_id, dedupe_key) do nothing returning id""", (wid, uid, rule_id, kind, cand["title"], cand["body"], json.dumps(cand["source"]), cand["dedupe_key"], visible_after)).fetchone()
    return row is not None


def evaluate(conn, p, now: datetime | None = None, force: bool = False) -> dict:
    """Turn new events into notifications for the rules this person switched on. Safe to call repeatedly: a repeated event is a duplicate, and calls
    within THROTTLE_SECONDS of the last one do nothing unless forced."""
    now = now or datetime.now(timezone.utc)
    pr = prefs.load(conn, p.user_id)["notifications"]
    out: dict[str, Any] = {"created": 0, "duplicates": 0, "dropped": 0, "rules": 0, "skipped": None}
    if not pr["in_app"]:
        out["skipped"] = "In-app notifications are switched off."
        return out
    last = pr.get("last_evaluated")
    if not force and last and (now - datetime.fromisoformat(last)).total_seconds() < THROTTLE_SECONDS:
        out["skipped"] = "Evaluated moments ago."
        return out
    prefs.save_section(conn, p.user_id, "notifications", {**pr, "last_evaluated": now.isoformat()})
    release = quiet_release(now, pr["quiet_hours"])
    visible = release
    rules = conn.execute("select id, kind, config, created_at from alert_rules where workspace_id=%s and user_id=%s and enabled order by created_at", (p.workspace_id, p.user_id)).fetchall()
    for rule in rules:
        if rule["kind"] == "briefing_ready":
            continue
        out["rules"] += 1
        for cand in candidates(conn, p.workspace_id, p.user_id, rule, now):
            total, per_rule = _today_counts(conn, p.workspace_id, p.user_id, rule["id"])
            if total >= PER_USER_PER_DAY or per_rule >= PER_RULE_PER_DAY:
                out["dropped"] += 1
                continue
            if create(conn, p.workspace_id, p.user_id, rule["id"], rule["kind"], cand, visible):
                out["created"] += 1
            else:
                out["duplicates"] += 1
    conn.execute("delete from notifications where workspace_id=%s and user_id=%s and created_at < now() - make_interval(days => %s)", (p.workspace_id, p.user_id, RETENTION_DAYS))
    return out


def notify_briefing(conn, p, briefing_id: str, period: str, has_changes: bool, now: datetime | None = None) -> bool:
    """Called when a briefing is created: a notification only if the person has the 'briefing ready' rule on and in-app notifications enabled."""
    now = now or datetime.now(timezone.utc)
    pr = prefs.load(conn, p.user_id)["notifications"]
    rule = conn.execute("select id from alert_rules where workspace_id=%s and user_id=%s and kind='briefing_ready' and enabled", (p.workspace_id, p.user_id)).fetchone()
    if not rule or not pr["in_app"]:
        return False
    release = quiet_release(now, pr["quiet_hours"])
    c = _cand(f"briefing:{briefing_id}", f"Your {period} briefing is ready", "It lists what changed in your records." if has_changes else "Nothing new was found in your records for this period.", "/dashboard/reports")
    return create(conn, p.workspace_id, p.user_id, rule["id"], "briefing_ready", c, release)
