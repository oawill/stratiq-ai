"""Universal watchlists: one personal list per person with domain-specific entity types.

  sports    team, fixture, competition   (computed from the Premier League data you imported)
  business  company, indicator           (your own reminders: no business data feed is connected)
  politics  election, indicator          (your own reminders: no polling or results feed is connected)
  markets   instrument, indicator        (your own reminders: no market data is connected or licensed)

Sports items show a status calculated from the imported history, and a fixture's forecast comes from the same Dixon-Coles model as Football
intelligence (tuned settings if a backtest exists, defaults otherwise, and it says which). Items in the other domains are labelled as having
no data feed: they are notes you keep, and nothing about them updates by itself. Items are private to the signed-in person inside their workspace.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from datetime import date as Date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, StringConstraints

from . import football_features as ff
from . import football_intel as fi
from .db import get_conn
from .football_api import _plain, _stored
from .football_intel_api import COMPETITION, _latest_run, _settings, freshness_of
from .security import Auth

router = APIRouter(prefix="/api/v1/watchlists", tags=["watchlists"])
MAX_ITEMS = 50
PAGE_MAX = 50
DOMAINS = ("sports", "business", "politics", "markets")
KINDS_BY_DOMAIN = {"sports": ("team", "fixture", "competition"), "business": ("company", "indicator"), "politics": ("election", "indicator"), "markets": ("instrument", "indicator")}
DEFAULT_DOMAIN = {"team": "sports", "fixture": "sports", "competition": "sports"}
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
Group = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean(v: str | None) -> str | None:
    return (_CTRL.sub("", v).strip() or None) if isinstance(v, str) else None


def _today() -> date:
    return datetime.now(timezone.utc).date()


class AddBody(BaseModel):
    domain: Literal["sports", "business", "politics", "markets"] | None = None
    kind: Literal["team", "fixture", "competition", "company", "indicator", "election", "instrument"]
    team: Name | None = None
    home: Name | None = None
    away: Name | None = None
    date: Date | None = None
    label: Label | None = None
    note: Note | None = None
    group: Group | None = None


class PatchBody(BaseModel):
    note: Note | None = None
    group: Group | None = None
    clear_note: bool = False
    clear_group: bool = False


def _history(conn, wid) -> list:
    return _plain(_stored(conn, wid, COMPETITION))


@router.get("/options")
def options(p: Auth, conn=Depends(get_conn)):
    """Clubs in the imported history, upcoming imported fixtures, and which entity types each domain supports."""
    ms = _history(conn, p.workspace_id)
    teams = sorted({t for _, h, a, *_ in ms for t in (h, a)})
    fx = conn.execute("select fixture_date, home_team, away_team from football_fixtures where status not in ('cancelled','postponed','suspended') and workspace_id=%s and fixture_date >= %s order by fixture_date limit 60", (p.workspace_id, _today())).fetchall()
    return {"has_history": bool(ms), "teams": teams, "fixtures": [{"date": r["fixture_date"], "home": r["home_team"], "away": r["away_team"]} for r in fx], "kinds": {d: list(k) for d, k in KINDS_BY_DOMAIN.items()},
            "feeds": {"sports": "Premier League results and fixtures you import", "business": "none", "politics": "none", "markets": "none"}}


@router.post("", status_code=201)
def add(body: AddBody, p: Auth, conn=Depends(get_conn)):
    domain = body.domain or DEFAULT_DOMAIN.get(body.kind)
    if not domain:
        raise HTTPException(422, "Choose a domain for this item (business, politics or markets).")
    if body.kind not in KINDS_BY_DOMAIN[domain]:
        raise HTTPException(422, f"A {domain} watchlist can hold: {', '.join(KINDS_BY_DOMAIN[domain])}.")
    note, group = _clean(body.note), _clean(body.group)
    if domain == "sports" and body.kind != "competition":
        ms = _history(conn, p.workspace_id)
        if not ms:
            raise HTTPException(404, "Import some match history first (Data page, Historical Football Data).")
        known = {t for _, h, a, *_ in ms for t in (h, a)}
        if body.kind == "team":
            if body.team not in known:
                raise HTTPException(422, f"'{body.team}' is not a club in the imported matches")
            key, label = body.team, body.team
        else:
            if not (body.home and body.away and body.date):
                raise HTTPException(422, "A fixture needs a home club, an away club and a date")
            row = conn.execute("select 1 from football_fixtures where status not in ('cancelled','postponed','suspended') and workspace_id=%s and fixture_date=%s and home_team=%s and away_team=%s", (p.workspace_id, body.date, body.home, body.away)).fetchone()
            if not row:
                raise HTTPException(422, "That fixture is not among the imported upcoming fixtures")
            key, label = f"{body.date.isoformat()}|{body.home}|{body.away}", f"{body.home} vs {body.away} ({body.date.isoformat()})"
    elif domain == "sports":
        key, label = COMPETITION, "Premier League (your imported results)"
    else:
        label = _clean(body.label)
        if not label:
            raise HTTPException(422, f"Give this {body.kind} a name.")
        key = re.sub(r"\s+", " ", label).lower()
    n = conn.execute("select count(*) n from watchlist_items where workspace_id=%s and user_id=%s", (p.workspace_id, p.user_id)).fetchone()["n"]
    exists = conn.execute("select 1 from watchlist_items where workspace_id=%s and user_id=%s and domain=%s and kind=%s and item_key=%s", (p.workspace_id, p.user_id, domain, body.kind, key)).fetchone()
    if n >= MAX_ITEMS and not exists:
        raise HTTPException(422, f"A watchlist holds at most {MAX_ITEMS} items")
    row = conn.execute(
        """insert into watchlist_items (workspace_id, user_id, domain, kind, item_key, label, note, group_name) values (%s,%s,%s,%s,%s,%s,%s,%s)
           on conflict on constraint watchlist_items_unique_entity do update set label=excluded.label, note=coalesce(excluded.note, watchlist_items.note), group_name=coalesce(excluded.group_name, watchlist_items.group_name)
           returning id""", (p.workspace_id, p.user_id, domain, body.kind, key, label, note, group)).fetchone()
    return {"id": str(row["id"]), "domain": domain, "kind": body.kind, "label": label}


@router.patch("/{item_id}")
def patch(item_id: uuid.UUID, body: PatchBody, p: Auth, conn=Depends(get_conn)):
    row = conn.execute("select note, group_name from watchlist_items where id=%s and workspace_id=%s and user_id=%s", (item_id, p.workspace_id, p.user_id)).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    note = None if body.clear_note else (_clean(body.note) if body.note is not None else row["note"])
    group = None if body.clear_group else (_clean(body.group) if body.group is not None else row["group_name"])
    conn.execute("update watchlist_items set note=%s, group_name=%s where id=%s", (note, group, item_id))
    return {"id": str(item_id), "note": note, "group": group}


@router.delete("/{item_id}", status_code=204)
def remove(item_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    r = conn.execute("delete from watchlist_items where id=%s and workspace_id=%s and user_id=%s", (item_id, p.workspace_id, p.user_id))
    if r.rowcount == 0:
        raise HTTPException(404, "Not found")


def _team_status(ms: list, team: str, today: date, fixtures: list[dict]) -> dict:
    prof = ff.team_profile(ms, team, today)
    last = [m for m in ms if team in (m[1], m[2])][-5:]

    def one(m):
        d, h, a, hg, ag = m
        gf, ga = (hg, ag) if h == team else (ag, hg)
        return {"date": d.isoformat(), "opponent": a if h == team else h, "venue": "H" if h == team else "A", "score": f"{hg}-{ag}", "result": "W" if gf > ga else "D" if gf == ga else "L"}
    recent = [one(m) for m in last][::-1]
    nxt = next(({"date": f["date"], "opponent": f["away"] if f["home"] == team else f["home"], "venue": "H" if f["home"] == team else "A"} for f in fixtures if team in (f["home"], f["away"])), None)
    return {"played": prof["played"], "elo": prof.get("elo"), "points_per_match": prof.get("points_per_match"), "goals_for_per_match": prof.get("goals_for_per_match"),
            "goals_against_per_match": prof.get("goals_against_per_match"), "recent": recent, "next_fixture": nxt, "as_of": ms[-1][0].isoformat() if ms else None}


NO_FEED = {"company": "companies", "indicator": "indicators", "election": "elections", "instrument": "instruments"}


def item_status(conn, p, it: dict, ms: list, fixtures: list[dict], settings: dict, today: date, rows_full: list) -> tuple[dict | None, str | None]:
    """(status, note) for one watchlist row. Sports items are computed from imported data; every other kind says plainly that no feed exists."""
    if it["domain"] != "sports":
        return {"feed": "none", "note": f"No data feed is connected for {NO_FEED.get(it['kind'], 'this')}. This is your own note: nothing here updates automatically."}, None
    if it["kind"] == "competition":
        if not ms:
            return None, "No results are imported for this competition."
        up = len(fixtures)
        fr = freshness_of(rows_full, up, None, today)
        return {"competition": "Premier League", "matches": len(ms), "seasons": len({r[0] for r in rows_full}), "last_match": fr["last_match"], "stale": fr["stale"], "upcoming_fixtures": up, "note": fr["note"]}, None
    if not ms:
        return None, "The match history has been removed, so there is nothing to compute."
    if it["kind"] == "team":
        known = {t for _, h, a, *_ in ms for t in (h, a)}
        return (_team_status(ms, it["item_key"], today, fixtures), None) if it["item_key"] in known else (None, "This club is no longer in the imported matches.")
    d, home, away = it["item_key"].split("|")
    fdate = date.fromisoformat(d)
    played = next((m for m in ms if m[0] == fdate and m[1] == home and m[2] == away), None)
    if played:
        return {"result": f"{played[3]}-{played[4]}", "note": "Played: the result has been imported."}, None
    if fdate < today:
        return None, "This fixture date has passed and no result has been imported yet."
    try:
        fc = fi.live_forecast(ms, home, away, min(fdate, today), settings)["dixon_coles"]
        return {"date": d, "model": "Dixon-Coles", "p_home": fc["probs"][0], "p_draw": fc["probs"][1], "p_away": fc["probs"][2], "tuned": settings["tuned"],
                "note": ("Settings tuned on a validation period." if settings["tuned"] else "Default settings: no backtest has been run, so nothing is tuned.") + " A model estimate, not a certainty."}, None
    except Exception:  # noqa: BLE001 - one bad item must not break the list
        return None, "A forecast could not be computed for this fixture."


@router.get("")
def listing(p: Auth, conn=Depends(get_conn), domain: Literal["sports", "business", "politics", "markets"] | None = None,
            kind: Literal["team", "fixture", "competition", "company", "indicator", "election", "instrument"] | None = None, q: Annotated[str | None, StringConstraints(max_length=80)] = None,
            group: Annotated[str | None, StringConstraints(max_length=40)] = None, limit: int = Query(PAGE_MAX, ge=1, le=PAGE_MAX), offset: int = Query(0, ge=0)):
    like = None if not q else "%" + re.sub(r"([\\%_])", r"\\\1", q.strip()) + "%"
    where = "workspace_id=%s and user_id=%s and (%s::text is null or domain=%s) and (%s::text is null or kind=%s) and (%s::text is null or group_name=%s) and (%s::text is null or label ilike %s or note ilike %s)"
    args = (p.workspace_id, p.user_id, domain, domain, kind, kind, group, group, like, like, like)
    total = conn.execute(f"select count(*) n from watchlist_items where {where}", args).fetchone()["n"]
    items = conn.execute(f"select id, domain, kind, item_key, label, note, group_name, created_at from watchlist_items where {where} order by created_at desc, id limit %s offset %s", (*args, limit, offset)).fetchall()
    groups = [r["group_name"] for r in conn.execute("select distinct group_name from watchlist_items where workspace_id=%s and user_id=%s and group_name is not null order by group_name", (p.workspace_id, p.user_id)).fetchall()]
    domain_counts = {r["domain"]: r["n"] for r in conn.execute("select domain, count(*) n from watchlist_items where workspace_id=%s and user_id=%s group by domain", (p.workspace_id, p.user_id)).fetchall()}
    today = _today()
    need_sports = any(i["domain"] == "sports" for i in items)
    rows_full = _stored(conn, p.workspace_id, COMPETITION) if need_sports else []
    ms = sorted(_plain(rows_full), key=lambda m: (m[0], m[1], m[2]))
    fixtures = [{"date": r["fixture_date"], "home": r["home_team"], "away": r["away_team"]} for r in conn.execute(
        "select fixture_date, home_team, away_team from football_fixtures where status not in ('cancelled','postponed','suspended') and workspace_id=%s and fixture_date >= %s order by fixture_date", (p.workspace_id, today)).fetchall()] if need_sports else []
    settings = _settings(_latest_run(conn, p)) if need_sports else {}
    out = []
    for it in items:
        status, note = item_status(conn, p, it, ms, fixtures, settings, today, rows_full)
        out.append({"id": str(it["id"]), "domain": it["domain"], "kind": it["kind"], "label": it["label"], "user_note": it["note"], "group": it["group_name"], "created_at": it["created_at"], "status": status, "note": note})
    return {"items": out, "total": total, "page_size": limit, "offset": offset, "limit": MAX_ITEMS, "groups": groups, "domain_counts": domain_counts,
            "generated_at": datetime.now(timezone.utc).isoformat(), "as_of": ms[-1][0].isoformat() if ms else None}
