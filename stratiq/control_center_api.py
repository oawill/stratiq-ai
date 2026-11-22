"""The personalised Control Center and the saved-intelligence library.

Everything returned here is read from records belonging to the signed-in person or their workspace; nothing is estimated or invented. A widget with
nothing to show says so (`empty: true`) and tells the person how to fill it. Widgets are computed only if the person's layout shows them, and only for
the domains they chose.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import StringConstraints

from . import alerts
from . import briefings_api as briefings
from . import preferences_api as prefs
from . import watchlist_api as wl
from .db import get_conn
from .security import ADMIN_ROLES, Auth

router = APIRouter(prefix="/api/v1", tags=["control-center"])
DOMAIN_OF = {"business": "business", "politics": "politics", "finance": "markets"}
SCENARIO_TABLE = {"business": "business", "politics": "politics", "markets": "finance"}
QUICK_ACTIONS = [
    {"id": "analyst", "label": "Ask the AI Analyst", "href": "/dashboard/analyst", "domain": None},
    {"id": "sim_sports", "label": "Run a sports simulation", "href": "/dashboard/simulations", "domain": "sports"},
    {"id": "sim_business", "label": "Try a pricing scenario", "href": "/dashboard/simulations", "domain": "business"},
    {"id": "watch", "label": "Add to a watchlist", "href": "/dashboard/watchlists", "domain": None},
    {"id": "data", "label": "Import football data", "href": "/dashboard/data", "domain": "sports"},
    {"id": "politics", "label": "Build a political scenario", "href": "/dashboard/politics", "domain": "politics"},
    {"id": "markets", "label": "Stress-test a portfolio", "href": "/dashboard/finance", "domain": "markets"},
    {"id": "brief", "label": "Generate a briefing", "href": "/dashboard/reports?tab=briefings", "domain": None},
]


def recent_events(conn, wid: str, domains: list[str], limit: int = 10) -> list[dict]:
    """What changed recently, taken from real records: imports, scored forecasts, backtests, saved scenarios and runs. Newest first."""
    ev: list[dict] = []
    if "sports" in domains:
        for r in conn.execute("select created_at, filename, report from match_imports where workspace_id=%s order by created_at desc limit 5", (wid,)).fetchall():
            new = (r["report"] or {}).get("new", 0)
            ev.append({"type": "observed", "domain": "sports", "title": f"Imported {new} match{'es' if new != 1 else ''}" if new else "Re-imported results (nothing new)", "detail": r["filename"] or "Premier League results",
                       "at": r["created_at"], "href": "/dashboard/data"})
        for r in conn.execute("""select pr.home_team, pr.away_team, max(o.home_goals) hg, max(o.away_goals) ag, max(o.scored_at) at from football_predictions pr join football_prediction_outcomes o on o.prediction_id=pr.id
                                 where pr.workspace_id=%s and pr.kind='live' group by pr.fixture_date, pr.home_team, pr.away_team order by max(o.scored_at) desc limit 5""", (wid,)).fetchall():
            ev.append({"type": "observed", "domain": "sports", "title": f"Forecast scored: {r['home_team']} {r['hg']}-{r['ag']} {r['away_team']}", "detail": "Your saved forecast was compared with the imported result.", "at": r["at"], "href": "/dashboard/sports"})
        for r in conn.execute("select created_at, mode from football_backtest_runs where workspace_id=%s and status='complete' order by created_at desc limit 3", (wid,)).fetchall():
            ev.append({"type": "observed", "domain": "sports", "title": f"A {r['mode']} backtest was run", "detail": "See Model performance for its results.", "at": r["created_at"], "href": "/dashboard/sports"})
    for r in conn.execute("select title, domain, version, created_at from simlab_runs where workspace_id=%s and domain = any(%s) order by created_at desc limit 5", (wid, domains)).fetchall():
        ev.append({"type": "observed", "domain": r["domain"], "title": f"Saved simulation: {r['title']}", "detail": f"Version {r['version']}. Hypothetical.", "at": r["created_at"], "href": "/dashboard/simulations"})
    tables = [SCENARIO_TABLE[d] for d in domains if d in SCENARIO_TABLE]
    if tables:
        for r in conn.execute("select title, domain, created_at from strategic_scenarios where workspace_id=%s and domain = any(%s) order by created_at desc limit 5", (wid, tables)).fetchall():
            ev.append({"type": "observed", "domain": DOMAIN_OF.get(r["domain"], r["domain"]), "title": f"Saved scenario: {r['title']}", "detail": "Hypothetical, built from numbers you entered.", "at": r["created_at"], "href": f"/dashboard/{r['domain']}"})
    ev.sort(key=lambda e: e["at"], reverse=True)
    return ev[:limit]


def recent_predictions(conn, wid: str, limit: int = 5) -> list[dict]:
    out = []
    for r in conn.execute("""select pr.fixture_date, pr.home_team, pr.away_team, max(pr.created_at) made, bool_or(o.prediction_id is not null) scored, max(o.home_goals) hg, max(o.away_goals) ag
                             from football_predictions pr left join football_prediction_outcomes o on o.prediction_id=pr.id where pr.workspace_id=%s and pr.kind='live'
                             group by pr.fixture_date, pr.home_team, pr.away_team order by max(pr.created_at) desc limit %s""", (wid, limit)).fetchall():
        out.append({"title": f"{r['home_team']} v {r['away_team']}", "date": r["fixture_date"].isoformat(), "status": f"result {r['hg']}-{r['ag']}" if r["scored"] else "waiting for the result", "at": r["made"], "href": "/dashboard/sports", "kind": "model forecast"})
    for r in conn.execute("select created_at, inputs from predictions where workspace_id=%s order by created_at desc limit %s", (wid, limit)).fetchall():
        i = r["inputs"] or {}
        out.append({"title": f"{i.get('home_name') or i.get('home_team')} vs {i.get('away_name') or i.get('away_team')}", "date": None, "status": "saved forecast", "at": r["created_at"], "href": "/dashboard/history", "kind": "saved forecast"})
    out.sort(key=lambda x: x["at"], reverse=True)
    return out[:limit]


def recent_scenarios(conn, wid: str, domains: list[str], limit: int = 6) -> list[dict]:
    out = []
    for r in conn.execute("select id, title, domain, version, created_at from simlab_runs where workspace_id=%s and domain = any(%s) order by created_at desc limit %s", (wid, domains, limit)).fetchall():
        out.append({"id": str(r["id"]), "title": r["title"], "domain": r["domain"], "version": r["version"], "at": r["created_at"], "href": "/dashboard/simulations", "kind": "simulation"})
    tables = [SCENARIO_TABLE[d] for d in domains if d in SCENARIO_TABLE]
    if tables:
        for r in conn.execute("select id, title, domain, definition, created_at from strategic_scenarios where workspace_id=%s and domain = any(%s) order by created_at desc limit %s", (wid, tables, limit)).fetchall():
            out.append({"id": str(r["id"]), "title": r["title"], "domain": DOMAIN_OF.get(r["domain"], r["domain"]), "version": int((r["definition"] or {}).get("version", 1)), "at": r["created_at"], "href": f"/dashboard/{r['domain']}", "kind": "scenario"})
    out.sort(key=lambda x: x["at"], reverse=True)
    return out[:limit]


@router.get("/control-center")
def control_center(p: Auth, conn=Depends(get_conn)):
    pr = prefs.load(conn, p.user_id)
    dash = pr["dashboard"]
    domains = dash["domains"]
    visible = [w["id"] for w in dash["widgets"] if w["visible"]]
    name = conn.execute("select name from users where id=%s", (p.user_id,)).fetchone()
    ws = conn.execute("select name from workspaces where id=%s", (p.workspace_id,)).fetchone()
    ev = alerts.evaluate(conn, p)
    w: dict = {}
    if "tracked" in visible:
        lst = wl.listing(p, conn, domain=None, kind=None, q=None, group=None, limit=wl.PAGE_MAX, offset=0)
        items = [i for i in lst["items"] if i["domain"] in domains][:6]
        w["tracked"] = {"items": items, "total": sum(n for d, n in lst["domain_counts"].items() if d in domains), "empty": not items,
                        "hint": "Nothing is tracked in your chosen domains yet. Add a club, a fixture or a note on the Watchlists page."}
    if "changes" in visible:
        events = recent_events(conn, p.workspace_id, domains, 10)
        w["changes"] = {"events": events, "empty": not events, "hint": "Nothing has changed yet. Import results, save a forecast or run a simulation and it will appear here."}
    if "alerts" in visible:
        rules = conn.execute("select count(*) n from alert_rules where workspace_id=%s and user_id=%s and enabled", (p.workspace_id, p.user_id)).fetchone()["n"]
        unread = conn.execute("select count(*) n from notifications where workspace_id=%s and user_id=%s and deleted_at is null and visible_after <= now() and read_at is null", (p.workspace_id, p.user_id)).fetchone()["n"]
        latest = conn.execute("select id, kind, title, body, created_at, read_at from notifications where workspace_id=%s and user_id=%s and deleted_at is null and visible_after <= now() order by visible_after desc limit 4", (p.workspace_id, p.user_id)).fetchall()
        w["alerts"] = {"unread": unread, "rules_enabled": rules, "latest": [{"id": str(r["id"]), "title": r["title"], "body": r["body"], "at": r["created_at"], "read": r["read_at"] is not None} for r in latest],
                       "empty": rules == 0 and not latest, "hint": "No alerts are switched on, so none are created. Choose what to be told about on the Notifications page."}
    if "predictions" in visible:
        preds = recent_predictions(conn, p.workspace_id, 5) if "sports" in domains else []
        w["predictions"] = {"recent": preds, "empty": not preds, "hidden_by_domains": "sports" not in domains, "hint": "No forecasts are saved yet. Open Sports, choose a fixture and save a forecast."}
    if "scenarios" in visible:
        sc = recent_scenarios(conn, p.workspace_id, domains, 6)
        w["scenarios"] = {"recent": sc, "empty": not sc, "hint": "No scenarios are saved yet. Build one in SimLab, Strategy, Politics or Markets and save it."}
    if "brief" in visible:
        made = briefings.ensure_due(conn, p) if pr["briefing"]["frequency"] != "off" else None
        row = conn.execute("select id, period, created_at, has_changes, content from briefings where workspace_id=%s and user_id=%s order by created_at desc limit 1", (p.workspace_id, p.user_id)).fetchone()
        latest = None
        if row:
            c = row["content"]
            first = [i for s in c["sections"] for i in s["items"] if i["type"] != "note"][:3]
            latest = {"id": str(row["id"]), "period": row["period"], "created_at": row["created_at"], "has_changes": row["has_changes"], "message": c.get("message"), "highlights": first}
        w["brief"] = {"latest": latest, "frequency": pr["briefing"]["frequency"], "generated_now": bool(made), "empty": latest is None,
                      "hint": "No briefing yet. Generate one, or choose daily or weekly briefings in Settings."}
    if "quick_actions" in visible:
        w["quick_actions"] = {"actions": [a for a in QUICK_ACTIONS if a["domain"] is None or a["domain"] in domains], "empty": False}
    return {"user": {"name": name["name"] if name else None}, "workspace": ws["name"] if ws else None, "role": p.role, "generated_at": datetime.now(timezone.utc).isoformat(), "preferences": pr["dashboard"], "widgets": w,
            "layout": [x for x in dash["widgets"] if x["visible"]], "alert_evaluation": ev, "domains": domains}


# ------------------------------------------------------------------ saved intelligence
Type = Literal["prediction", "forecast", "simulation", "scenario", "conversation", "briefing"]
ALL_TYPES = ["prediction", "forecast", "simulation", "scenario", "conversation", "briefing"]


@router.get("/saved-intelligence")
def saved_intelligence(p: Auth, conn=Depends(get_conn), types: Annotated[str | None, StringConstraints(max_length=100)] = None, q: Annotated[str | None, StringConstraints(max_length=80)] = None,
                       sort: Literal["newest", "oldest", "title"] = "newest", limit: int = Query(25, ge=1, le=50), offset: int = Query(0, ge=0)):
    """One list of everything saved: forecasts, simulations, scenarios, your Analyst conversations and your briefings. Conversations and briefings are only ever yours."""
    want = [t for t in (types.split(",") if types else ALL_TYPES) if t in ALL_TYPES] or ALL_TYPES
    like = None if not q else "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    u = """
      select 'prediction' as type, p.id::text as id, coalesce(p.inputs->>'home_name', p.inputs->>'home_team') || ' vs ' || coalesce(p.inputs->>'away_name', p.inputs->>'away_team') as title,
             p.created_at, 'sports' as domain, us.name as owner, null::uuid as owner_id
        from predictions p join users us on us.id=p.user_id where p.workspace_id=%(w)s
      union all
      select 'forecast', pr.fixture_date::text || '|' || pr.home_team || '|' || pr.away_team, pr.home_team || ' v ' || pr.away_team || ' (' || pr.fixture_date::text || ')', max(pr.created_at), 'sports', null, null
        from football_predictions pr where pr.workspace_id=%(w)s and pr.kind='live' group by pr.fixture_date, pr.home_team, pr.away_team
      union all
      select 'simulation', r.id::text, r.title || ' (v' || r.version || ')', r.created_at, r.domain, us.name, r.created_by
        from simlab_runs r join users us on us.id=r.created_by where r.workspace_id=%(w)s
      union all
      select 'scenario', s.id::text, s.title, s.created_at, case s.domain when 'finance' then 'markets' else s.domain end, us.name, s.created_by
        from strategic_scenarios s join users us on us.id=s.created_by where s.workspace_id=%(w)s and s.domain in ('business','politics','finance')
      union all
      select 'conversation', c.id::text, c.title, c.updated_at, null, null, c.user_id from analyst_conversations c where c.workspace_id=%(w)s and c.user_id=%(u)s
      union all
      select 'briefing', b.id::text, initcap(b.period) || ' briefing, ' || to_char(b.created_at, 'YYYY-MM-DD'), b.created_at, null, null, b.user_id from briefings b where b.workspace_id=%(w)s and b.user_id=%(u)s
    """
    order = {"newest": "created_at desc, id", "oldest": "created_at asc, id", "title": "lower(title), id"}[sort]
    args = {"w": p.workspace_id, "u": p.user_id, "t": want, "q": like, "l": limit, "o": offset}
    where = "type = any(%(t)s) and (%(q)s::text is null or title ilike %(q)s)"
    rows = conn.execute(f"select * from ({u}) x where {where} order by {order} limit %(l)s offset %(o)s", args).fetchall()
    total = conn.execute(f"select count(*) n from ({u}) x where {where}", args).fetchone()["n"]
    counts = {r["type"]: r["n"] for r in conn.execute(f"select type, count(*) n from ({u}) x where (%(q)s::text is null or title ilike %(q)s) group by type", args).fetchall()}
    out = []
    for r in rows:
        mine = r["owner_id"] is not None and str(r["owner_id"]) == str(p.user_id)
        t = r["type"]
        item = {"type": t, "id": r["id"], "title": r["title"], "created_at": r["created_at"], "domain": r["domain"], "owner": "You" if mine or t in ("conversation", "briefing") else r["owner"]}
        item["can_delete"] = (t in ("conversation", "briefing")) or (t in ("simulation", "scenario") and (mine or p.role in ADMIN_ROLES))
        item["href"] = {"prediction": "/dashboard/history", "forecast": "/dashboard/sports", "simulation": "/dashboard/simulations", "scenario": "/dashboard/simulations", "conversation": "/dashboard/analyst", "briefing": "/dashboard/reports?tab=briefings"}[t]
        item["delete_path"] = {"simulation": f"simlab/runs/{r['id']}", "scenario": f"simlab/scenarios/{r['id']}", "conversation": f"analyst/conversations/{r['id']}", "briefing": f"briefings/{r['id']}"}.get(t) if item["can_delete"] else None
        item["export_path"] = {"simulation": f"simlab/runs/{r['id']}/export?format=csv", "scenario": f"simlab/scenarios/{r['id']}/export?format=csv", "conversation": f"analyst/conversations/{r['id']}/export?format=md"}.get(t)
        item["note"] = "Saved forecasts are permanent records and cannot be deleted." if t in ("prediction", "forecast") else None
        out.append(item)
    return {"items": out, "total": total, "counts": counts, "limit": limit, "offset": offset, "types": want,
            "note": "Reports are generated from your records when you open them, so they are not stored here. Comparisons are not saved separately: the scenarios they compare are."}
