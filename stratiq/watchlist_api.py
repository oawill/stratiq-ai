"""Watchlists: clubs and upcoming fixtures a person wants to keep an eye on, with a current status computed from the imported history.

Nothing here is a feed. A club's status is calculated from the matches you imported; a fixture's forecast comes from the same Dixon-Coles
model as Football intelligence (tuned settings if a backtest exists, defaults otherwise, and it says which). Items are personal to the
signed-in user inside their workspace.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from datetime import date as Date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StringConstraints

from . import football_features as ff
from . import football_intel as fi
from .db import get_conn
from .football_api import _plain, _stored
from .football_intel_api import COMPETITION, _latest_run, _settings
from .security import Auth

router = APIRouter(prefix="/api/v1/watchlists", tags=["watchlists"])
MAX_ITEMS = 50
Name = Annotated[str, StringConstraints(min_length=1, max_length=60)]


def _today() -> date:
    return datetime.now(timezone.utc).date()


class AddBody(BaseModel):
    kind: Literal["team", "fixture"]
    team: Name | None = None
    home: Name | None = None
    away: Name | None = None
    date: Date | None = None


def _history(conn, wid) -> list:
    return _plain(_stored(conn, wid, COMPETITION))


@router.get("/options")
def options(p: Auth, conn=Depends(get_conn)):
    """Clubs in the imported history and the upcoming fixtures that can be added."""
    ms = _history(conn, p.workspace_id)
    teams = sorted({t for _, h, a, *_ in ms for t in (h, a)})
    fx = conn.execute("select fixture_date, home_team, away_team from football_fixtures where workspace_id=%s and fixture_date >= %s order by fixture_date limit 60", (p.workspace_id, _today())).fetchall()
    return {"has_history": bool(ms), "teams": teams, "fixtures": [{"date": r["fixture_date"], "home": r["home_team"], "away": r["away_team"]} for r in fx]}


@router.post("", status_code=201)
def add(body: AddBody, p: Auth, conn=Depends(get_conn)):
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
        row = conn.execute("select 1 from football_fixtures where workspace_id=%s and fixture_date=%s and home_team=%s and away_team=%s", (p.workspace_id, body.date, body.home, body.away)).fetchone()
        if not row:
            raise HTTPException(422, "That fixture is not among the imported upcoming fixtures")
        key, label = f"{body.date.isoformat()}|{body.home}|{body.away}", f"{body.home} vs {body.away} ({body.date.isoformat()})"
    n = conn.execute("select count(*) n from watchlist_items where workspace_id=%s and user_id=%s", (p.workspace_id, p.user_id)).fetchone()["n"]
    if n >= MAX_ITEMS:
        raise HTTPException(422, f"A watchlist holds at most {MAX_ITEMS} items")
    row = conn.execute(
        """insert into watchlist_items (workspace_id, user_id, kind, item_key, label) values (%s,%s,%s,%s,%s)
           on conflict (workspace_id, user_id, kind, item_key) do update set label=excluded.label returning id""",
        (p.workspace_id, p.user_id, body.kind, key, label)).fetchone()
    return {"id": str(row["id"]), "kind": body.kind, "label": label}


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
            "goals_against_per_match": prof.get("goals_against_per_match"), "recent": recent, "next_fixture": nxt,
            "as_of": ms[-1][0].isoformat() if ms else None}


@router.get("")
def listing(p: Auth, conn=Depends(get_conn)):
    items = conn.execute("select id, kind, item_key, label, created_at from watchlist_items where workspace_id=%s and user_id=%s order by created_at desc", (p.workspace_id, p.user_id)).fetchall()
    ms = sorted(_history(conn, p.workspace_id), key=lambda m: (m[0], m[1], m[2]))
    today = _today()
    fixtures = [{"date": r["fixture_date"], "home": r["home_team"], "away": r["away_team"]} for r in conn.execute(
        "select fixture_date, home_team, away_team from football_fixtures where workspace_id=%s and fixture_date >= %s order by fixture_date", (p.workspace_id, today)).fetchall()]
    run = _latest_run(conn, p)
    settings = _settings(run)
    out = []
    for it in items:
        base = {"id": str(it["id"]), "kind": it["kind"], "label": it["label"], "created_at": it["created_at"]}
        if not ms:
            out.append({**base, "status": None, "note": "The match history has been removed, so there is nothing to compute."})
            continue
        if it["kind"] == "team":
            known = {t for _, h, a, *_ in ms for t in (h, a)}
            out.append({**base, "status": _team_status(ms, it["item_key"], today, fixtures) if it["item_key"] in known else None,
                        "note": None if it["item_key"] in known else "This club is no longer in the imported matches."})
            continue
        d, home, away = it["item_key"].split("|")
        fdate = date.fromisoformat(d)
        played = next((m for m in ms if m[0] == fdate and m[1] == home and m[2] == away), None)
        if played:
            out.append({**base, "status": {"result": f"{played[3]}-{played[4]}", "note": "Played: the result has been imported."}})
            continue
        if fdate < today:
            out.append({**base, "status": None, "note": "This fixture date has passed and no result has been imported yet."})
            continue
        try:
            fc = fi.live_forecast(ms, home, away, min(fdate, today), settings)["dixon_coles"]
            out.append({**base, "status": {"date": d, "model": "Dixon-Coles", "p_home": fc["probs"][0], "p_draw": fc["probs"][1], "p_away": fc["probs"][2], "tuned": settings["tuned"],
                                           "note": ("Settings tuned on a validation period." if settings["tuned"] else "Default settings: no backtest has been run, so nothing is tuned.") + " A model estimate, not a certainty."}})
        except Exception:  # noqa: BLE001 - one bad item must not break the list
            out.append({**base, "status": None, "note": "A forecast could not be computed for this fixture."})
    return {"items": out, "limit": MAX_ITEMS, "generated_at": datetime.now(timezone.utc).isoformat(), "as_of": ms[-1][0].isoformat() if ms else None}
