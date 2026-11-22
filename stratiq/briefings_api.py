"""Intelligence briefings: a daily or weekly summary of what changed in the records this workspace holds, with citations and timestamps.

A briefing is built only from stored records whose timestamps fall inside its window: results imported, forecasts scored, backtests run, scenarios
saved. Observed events (something that happened and is recorded) are kept apart from model forecasts (estimates made before a match). When nothing
new exists the briefing says so: it never invents a change. Domains without a data feed (business, politics and markets indicators) report only
your own saved scenarios, and say that no feed is connected. A briefing is private to the person who generated it.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import alerts
from . import preferences_api as prefs
from .db import get_conn
from .football_api import _stored
from .football_intel_api import COMPETITION, freshness_of
from .security import Auth

router = APIRouter(prefix="/api/v1/briefings", tags=["briefings"])
PER_DAY = 10
RETENTION_DAYS = 90
PERIOD = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}
DUE_AFTER = {"daily": timedelta(hours=23), "weekly": timedelta(days=6, hours=12)}
MAX_LIST = 8
DOMAIN_TABLE = {"business": "business", "politics": "politics", "markets": "finance"}


class GenerateBody(BaseModel):
    period: Literal["daily", "weekly"]
    domains: list[str] | None = Field(None, max_length=4)


def _item(text: str, kind: str, source: str, href: str, retrieved: str, window: str | None = None, **extra) -> dict:
    return {"text": text[:400], "type": kind, "citation": {"source": source, "retrieved_at": retrieved, "window": window, "href": href}, **extra}


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def sports_sections(conn, wid: str, uid: str, start: datetime, end: datetime, now: datetime) -> list[dict]:
    iso, win = now.isoformat(), f"{start.date().isoformat()} to {end.date().isoformat()}"
    today = now.date()
    watched = {r["item_key"] for r in conn.execute("select item_key from watchlist_items where workspace_id=%s and user_id=%s and domain='sports' and kind='team'", (wid, uid)).fetchall()}
    secs: list[dict] = []
    # --- new completed results (observed)
    res = conn.execute("select match_date, home_team, away_team, home_goals, away_goals from match_history where workspace_id=%s and competition=%s and imported_at >= %s and imported_at < %s order by match_date desc, home_team",
                       (wid, COMPETITION, start, end)).fetchall()
    items = []
    for r in res[:MAX_LIST]:
        mine = r["home_team"] in watched or r["away_team"] in watched
        items.append(_item(f"{r['home_team']} {r['home_goals']}-{r['away_goals']} {r['away_team']} ({r['match_date'].isoformat()})" + (" · a club you watch" if mine else ""), "observed",
                           "Premier League results you imported", "/dashboard/sports", iso, win, watched=mine))
    if len(res) > MAX_LIST:
        items.append(_item(f"{len(res) - MAX_LIST} more results were imported in this period.", "observed", "Premier League results you imported", "/dashboard/data", iso, win))
    if items:
        secs.append({"id": "sports_results", "domain": "sports", "title": f"New completed results imported ({len(res)})", "items": items})
    # --- saved forecasts scored (observed result; the earlier forecast is labelled as a forecast)
    scored = conn.execute("""select pr.fixture_date, pr.home_team, pr.away_team, o.home_goals hg, o.away_goals ag, o.correct, pr.p_home, pr.p_draw, pr.p_away, pr.created_at made, v.name model, o.scored_at
                             from football_predictions pr join football_prediction_outcomes o on o.prediction_id=pr.id join football_model_versions v on v.id=pr.model_version_id
                             where pr.workspace_id=%s and pr.kind='live' and o.scored_at >= %s and o.scored_at < %s and v.name = 'dixon_coles' order by o.scored_at desc limit %s""", (wid, start, end, MAX_LIST)).fetchall()
    items = []
    for r in scored:
        items.append(_item(f"{r['home_team']} v {r['away_team']} ended {r['hg']}-{r['ag']}.", "observed", "Your saved forecasts, scored against imported results", "/dashboard/sports", r["scored_at"].isoformat(), win))
        items.append(_item(f"Forecast made {r['made'].date().isoformat()}, before the match (an estimate, not a certainty): {_pct(r['p_home'])} home, {_pct(r['p_draw'])} draw, {_pct(r['p_away'])} away. The most likely result was {'right' if r['correct'] else 'not the one that happened'}.",
                           "forecast", "Your saved forecasts", "/dashboard/sports", r["made"].isoformat(), None))
    if items:
        secs.append({"id": "sports_scored", "domain": "sports", "title": "Saved forecasts that were scored", "items": items})
    # --- upcoming saved forecasts (forecasts)
    up = conn.execute("""select pr.fixture_date, pr.home_team, pr.away_team, pr.p_home, pr.p_draw, pr.p_away, pr.created_at from football_predictions pr join football_model_versions v on v.id=pr.model_version_id
                         left join football_prediction_outcomes o on o.prediction_id=pr.id where pr.workspace_id=%s and pr.kind='live' and o.prediction_id is null and pr.fixture_date >= %s and pr.fixture_date <= %s
                         and v.name='dixon_coles' order by pr.fixture_date limit 5""", (wid, today, today + timedelta(days=14))).fetchall()
    items = [_item(f"{r['home_team']} v {r['away_team']} on {r['fixture_date'].isoformat()}: model forecast {_pct(r['p_home'])} home, {_pct(r['p_draw'])} draw, {_pct(r['p_away'])} away (an estimate saved {r['created_at'].date().isoformat()}).",
                   "forecast", "Your saved forecasts", "/dashboard/sports", r["created_at"].isoformat()) for r in up]
    if items:
        secs.append({"id": "sports_upcoming", "domain": "sports", "title": "Saved forecasts waiting for results", "items": items})
    # --- model performance updates (observed)
    runs = conn.execute("select id, created_at, results, config from football_backtest_runs where workspace_id=%s and mode='chronological' and status='complete' and created_at >= %s and created_at < %s order by created_at desc limit 2", (wid, start, end)).fetchall()
    items = []
    for r in runs:
        t = (r["results"] or {}).get("test", {})
        dc, fr = (t.get("dixon_coles") or {}).get("1x2"), (t.get("frequency") or {}).get("1x2")
        if dc and fr:
            items.append(_item(f"A chronological backtest was run on {r['created_at'].date().isoformat()}. On its test period, Dixon-Coles had log loss {dc['log_loss']:.3f} and the frequency baseline {fr['log_loss']:.3f} (lower is better) over {dc['n']} matches. This describes past matches, not future accuracy.",
                               "observed", "Backtest run in this workspace", "/dashboard/sports", r["created_at"].isoformat(), (r["config"] or {}).get("split", {}).get("test") and f"test period {', '.join(r['config']['split']['test'])}"))
    if items:
        secs.append({"id": "sports_models", "domain": "sports", "title": "Model performance updates", "items": items})
    # --- data freshness (observed, only when it needs attention)
    fr = freshness_of(_stored(conn, wid, COMPETITION), 0, None, today)
    if fr.get("stale"):
        secs.append({"id": "sports_freshness", "domain": "sports", "title": "Data freshness", "items": [_item(fr["note"], "note", "Imports recorded in this workspace", "/dashboard/data", iso)]})
    # --- watched clubs' next imported fixtures (observed)
    items = []
    for t in sorted(watched):
        nf = conn.execute("select fixture_date, home_team, away_team from football_fixtures where status not in ('cancelled','postponed','suspended') and workspace_id=%s and fixture_date >= %s and fixture_date <= %s and (home_team=%s or away_team=%s) order by fixture_date limit 1",
                          (wid, today, today + timedelta(days=14), t, t)).fetchone()
        if nf:
            items.append(_item(f"{t}: next imported fixture is {nf['home_team']} v {nf['away_team']} on {nf['fixture_date'].isoformat()}.", "observed", "Fixtures you imported", "/dashboard/watchlists", iso))
    if items:
        secs.append({"id": "sports_watched", "domain": "sports", "title": "Clubs you watch", "items": items[:MAX_LIST]})
    return secs


def other_sections(conn, wid: str, uid: str, domain: str, start: datetime, end: datetime, now: datetime) -> list[dict]:
    iso, win = now.isoformat(), f"{start.date().isoformat()} to {end.date().isoformat()}"
    label = {"business": "Business", "politics": "Politics", "markets": "Markets"}[domain]
    secs = []
    items = []
    for r in conn.execute("select title, definition, created_at from strategic_scenarios where workspace_id=%s and domain=%s and created_at >= %s and created_at < %s order by created_at desc limit %s", (wid, DOMAIN_TABLE[domain], start, end, MAX_LIST)).fetchall():
        v = int((r["definition"] or {}).get("version", 1))
        items.append(_item(f"Saved scenario “{r['title']}” (version {v}). A hypothetical built from numbers you entered.", "observed", "Saved scenarios in this workspace", f"/dashboard/{'finance' if domain == 'markets' else domain}", r["created_at"].isoformat(), win))
    for r in conn.execute("select title, version, created_at from simlab_runs where workspace_id=%s and domain=%s and created_at >= %s and created_at < %s order by created_at desc limit %s", (wid, domain, start, end, MAX_LIST)).fetchall():
        items.append(_item(f"SimLab run “{r['title']}” (version {r['version']}). Hypothetical.", "observed", "Saved SimLab runs", "/dashboard/simulations", r["created_at"].isoformat(), win))
    if items:
        secs.append({"id": f"{domain}_scenarios", "domain": domain, "title": f"{label}: scenarios saved in this period", "items": items[:MAX_LIST]})
    followed = conn.execute("select kind, count(*) n from watchlist_items where workspace_id=%s and user_id=%s and domain=%s group by kind", (wid, uid, domain)).fetchall()
    if followed:
        what = ", ".join(f"{r['n']} {r['kind']}{'s' if r['n'] != 1 else ''}" for r in followed)
        secs.append({"id": f"{domain}_followed", "domain": domain, "title": f"{label}: items you follow",
                     "items": [_item(f"You follow {what}. No data feed is connected for {label.lower()}, so no changes to them can be reported: these are your own notes.", "note", "Your watchlist", "/dashboard/watchlists", iso)]})
    return secs


def build(conn, wid: str, uid: str, period: str, domains: list[str], now: datetime) -> dict:
    end, start = now, now - PERIOD[period]
    sections: list[dict] = []
    for d in domains:
        sections += sports_sections(conn, wid, uid, start, end, now) if d == "sports" else other_sections(conn, wid, uid, d, start, end, now)
    real = [s for s in sections if any(i["type"] != "note" for i in s["items"])]
    has_changes = bool(real)
    return {"title": f"{period.title()} briefing", "generated_at": now.isoformat(), "window": {"start": start.isoformat(), "end": end.isoformat()}, "domains": domains, "sections": sections, "empty": not has_changes,
            "message": None if has_changes else f"No new information since {start.date().isoformat()}. Nothing has changed in the records VELQORIN holds for the domains you follow.",
            "legend": {"observed": "Something that happened and is recorded in your data.", "forecast": "A model estimate made before an event. Not a certainty.", "note": "Your own note or a limitation, not a change."}}


def generate(conn, p, period: str, domains: list[str] | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    doms = domains or prefs.load(conn, p.user_id)["briefing"]["domains"]
    content = build(conn, p.workspace_id, p.user_id, period, doms, now)
    row = conn.execute("insert into briefings (workspace_id, user_id, period, domains, window_start, window_end, content, has_changes) values (%s,%s,%s,%s,%s,%s,%s,%s) returning id, created_at",
                       (p.workspace_id, p.user_id, period, doms, content["window"]["start"], content["window"]["end"], json.dumps(content), not content["empty"])).fetchone()
    alerts.notify_briefing(conn, p, str(row["id"]), period, not content["empty"], now)
    return {"id": str(row["id"]), "created_at": row["created_at"], "period": period, **content}


def due(frequency: str, last: datetime | None, now: datetime) -> bool:
    return frequency in DUE_AFTER and (last is None or now - last >= DUE_AFTER[frequency])


def ensure_due(conn, p, now: datetime | None = None) -> dict | None:
    """Generate the person's scheduled briefing if their chosen frequency says one is due. Does nothing unless they switched briefings on."""
    now = now or datetime.now(timezone.utc)
    freq = prefs.load(conn, p.user_id)["briefing"]["frequency"]
    if freq == "off":
        return None
    last = conn.execute("select max(created_at) t from briefings where workspace_id=%s and user_id=%s and period=%s", (p.workspace_id, p.user_id, freq)).fetchone()["t"]
    return generate(conn, p, freq, None, now) if due(freq, last, now) else None


def _summary(r) -> dict:
    return {"id": str(r["id"]), "period": r["period"], "domains": r["domains"], "created_at": r["created_at"], "window_start": r["window_start"], "window_end": r["window_end"], "has_changes": r["has_changes"]}


@router.get("")
def listing(p: Auth, conn=Depends(get_conn), limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0)):
    conn.execute("delete from briefings where workspace_id=%s and user_id=%s and created_at < now() - make_interval(days => %s)", (p.workspace_id, p.user_id, RETENTION_DAYS))
    rows = conn.execute("select id, period, domains, created_at, window_start, window_end, has_changes from briefings where workspace_id=%s and user_id=%s order by created_at desc limit %s offset %s", (p.workspace_id, p.user_id, limit, offset)).fetchall()
    total = conn.execute("select count(*) n from briefings where workspace_id=%s and user_id=%s", (p.workspace_id, p.user_id)).fetchone()["n"]
    return {"briefings": [_summary(r) for r in rows], "total": total, "frequency": prefs.load(conn, p.user_id)["briefing"]["frequency"], "retention_days": RETENTION_DAYS}


@router.post("", status_code=201)
def create(body: GenerateBody, p: Auth, conn=Depends(get_conn)):
    n = conn.execute("select count(*) n from briefings where workspace_id=%s and user_id=%s and created_at > now() - interval '1 day'", (p.workspace_id, p.user_id)).fetchone()["n"]
    if n >= PER_DAY:
        raise HTTPException(429, f"You can generate up to {PER_DAY} briefings a day.")
    doms = None
    if body.domains is not None:
        if not body.domains or any(d not in prefs.DOMAINS for d in body.domains) or len(set(body.domains)) != len(body.domains):
            raise HTTPException(422, f"Domains must be a non-empty list without repeats, chosen from: {', '.join(prefs.DOMAINS)}.")
        doms = [d for d in prefs.DOMAINS if d in body.domains]
    return generate(conn, p, body.period, doms)


@router.get("/{bid}")
def get_one(bid: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    r = conn.execute("select * from briefings where id=%s and workspace_id=%s and user_id=%s", (bid, p.workspace_id, p.user_id)).fetchone()
    if not r:
        raise HTTPException(404, "Not found")
    return {**_summary(r), **r["content"]}


@router.delete("/{bid}", status_code=204)
def delete(bid: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    if conn.execute("delete from briefings where id=%s and workspace_id=%s and user_id=%s", (bid, p.workspace_id, p.user_id)).rowcount == 0:
        raise HTTPException(404, "Not found")
