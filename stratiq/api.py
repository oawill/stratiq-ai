"""VELQORIN FastAPI service, v1.

Authentication: the Next.js server mints a short-lived HS256 JWT (INTERNAL_API_SECRET) after
validating the user's session cookie. This service verifies it AND re-checks workspace
membership in the database, so a forged or stale claim cannot cross workspace boundaries.
Browsers never receive this token and never call this service directly.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated, Literal

import jwt
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from . import model as sports_model
from . import plans
from .brand import NAME
from .db import get_conn, load_dotenv_local
from .security import Auth, Principal, principal, require_write  # noqa: F401
from .model import HistMatch, input_hash, predict

load_dotenv_local()

_PROD = bool(os.environ.get("VERCEL"))  # no public API docs in production; every route needs a token anyway
app = FastAPI(title=f"{NAME} API", version="1.0.0", docs_url=None if _PROD else "/api/v1/docs", openapi_url=None if _PROD else "/api/v1/openapi.json")
router = APIRouter(prefix="/api/v1")



def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- public
@router.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


# ---------------------------------------------------------------- identity / overview
@router.get("/me")
def me(p: Auth, conn=Depends(get_conn)):
    row = conn.execute(
        """select u.id user_id, u.name, u.email, w.id workspace_id, w.name workspace_name, m.role
           from users u join workspace_members m on m.user_id=u.id join workspaces w on w.id=m.workspace_id
           where u.id=%s and w.id=%s""",
        (p.user_id, p.workspace_id),
    ).fetchone()
    return row


@router.get("/models")
def models(p: Auth, conn=Depends(get_conn), domain: str | None = None):
    rows = conn.execute(
        "select id,domain,name,version,description,status,created_at from model_versions "
        "where (%s::text is null or domain=%s) order by domain, created_at",
        (domain, domain),
    ).fetchall()
    return {"models": rows}


def _metrics(conn):
    return conn.execute(
        """select mv.name, mv.version, mv.domain, em.metric, em.value, em.sample_size, em.dataset, em.computed_at
           from evaluation_metrics em join model_versions mv on mv.id=em.model_version_id
           order by mv.name, em.metric"""
    ).fetchall()


@router.get("/overview")
def overview(p: Auth, conn=Depends(get_conn)):
    ws = p.workspace_id
    predictions = conn.execute(
        """select p.id, p.domain, p.subject_type, p.subject_id, p.created_at, p.outputs, p.inputs,
                  mv.name model_name, mv.version model_version
           from predictions p join model_versions mv on mv.id=p.model_version_id
           where p.workspace_id=%s order by p.created_at desc limit 5""",
        (ws,),
    ).fetchall()
    sims = conn.execute(
        "select id, title, domain, status, progress, created_at from simulation_runs where workspace_id=%s order by created_at desc limit 5",
        (ws,),
    ).fetchall()
    scenarios = conn.execute(
        "select count(*) n from strategic_scenarios where workspace_id=%s", (ws,)
    ).fetchone()["n"]
    activity = conn.execute(
        "select id, kind, summary, ref_type, ref_id, created_at from activity_history "
        "where workspace_id=%s order by created_at desc limit 8",
        (ws,),
    ).fetchall()
    counts = conn.execute(
        "select (select count(*) from predictions where workspace_id=%s) predictions,"
        " (select count(*) from simulation_runs where workspace_id=%s) simulations",
        (ws, ws),
    ).fetchone()
    return {
        "models": conn.execute(
            "select id,domain,name,version,description,status from model_versions order by domain, created_at"
        ).fetchall(),
        "recent_predictions": predictions,
        "saved_simulations": sims,
        "saved_scenarios": scenarios,
        "metrics": _metrics(conn),
        "activity": activity,
        "counts": counts,
    }


# ---------------------------------------------------------------- sports
@router.get("/sports/leagues")
def leagues(p: Auth, conn=Depends(get_conn)):
    return {
        "leagues": conn.execute(
            """select l.id, l.name, l.country, l.data_source, l.is_fictional,
                      (select count(*) from sports_teams t where t.league_id=l.id) teams,
                      (select count(*) from sports_matches m where m.league_id=l.id and m.status='finished') finished,
                      (select count(*) from sports_matches m where m.league_id=l.id and m.status='scheduled') scheduled
               from sports_leagues l order by l.name"""
        ).fetchall()
    }


@router.get("/sports/fixtures")
def fixtures(
    p: Auth,
    conn=Depends(get_conn),
    league_id: str | None = None,
    status: Literal["scheduled", "finished"] = "scheduled",
    limit: int = Query(30, ge=1, le=200),
):
    order = "asc" if status == "scheduled" else "desc"
    rows = conn.execute(
        f"""select m.id, m.league_id, m.kickoff, m.status, m.home_goals, m.away_goals, m.data_source,
                   m.home_team_id, h.name home_name, m.away_team_id, a.name away_name
            from sports_matches m
            join sports_teams h on h.id=m.home_team_id join sports_teams a on a.id=m.away_team_id
            where m.status=%s and (%s::text is null or m.league_id=%s)
            order by m.kickoff {order}, m.id limit %s""",
        (status, league_id, league_id, limit),
    ).fetchall()
    return {"fixtures": rows}


def _league_history(conn, league_id: str) -> tuple[list[str], list[HistMatch]]:
    teams = [r["id"] for r in conn.execute("select id from sports_teams where league_id=%s order by id", (league_id,))]
    hist = [
        HistMatch(r["home_team_id"], r["away_team_id"], r["home_goals"], r["away_goals"], r["kickoff"])
        for r in conn.execute(
            "select home_team_id,away_team_id,home_goals,away_goals,kickoff from sports_matches "
            "where league_id=%s and status='finished'",
            (league_id,),
        )
    ]
    return teams, hist


def _team(conn, team_id: str):
    t = conn.execute("select id,name,league_id from sports_teams where id=%s", (team_id,)).fetchone()
    if not t:
        raise HTTPException(404, "Unknown team")
    return t


def _results(conn, team_id: str, limit: int):
    return conn.execute(
        """select m.id, m.kickoff, m.home_goals, m.away_goals, h.name home_name, a.name away_name,
                  m.home_team_id, m.away_team_id
           from sports_matches m join sports_teams h on h.id=m.home_team_id join sports_teams a on a.id=m.away_team_id
           where m.status='finished' and (m.home_team_id=%s or m.away_team_id=%s)
           order by m.kickoff desc limit %s""",
        (team_id, team_id, limit),
    ).fetchall()


@router.get("/sports/teams")
def teams(p: Auth, league_id: str, conn=Depends(get_conn)):
    if not conn.execute("select 1 from sports_leagues where id=%s", (league_id,)).fetchone():
        raise HTTPException(404, "Unknown league")
    tids, hist = _league_history(conn, league_id)
    from .ratings import Match, fit_ratings

    r = fit_ratings([Match(m.home, m.away, m.home_goals, m.away_goals) for m in hist], tids)
    names = {t["id"]: t["name"] for t in conn.execute("select id,name from sports_teams where league_id=%s", (league_id,))}
    out = [
        {"id": t, "name": names[t], "attack": round(r.attack[t], 4), "defence": round(r.defence[t], 4),
         "matches": r.team_matches.get(t, 0)}
        for t in tids
    ]
    out.sort(key=lambda x: -(x["attack"] / x["defence"]))
    return {"teams": out, "league_mean_goals": round(r.mu, 4), "home_advantage": round(r.home_adv, 4)}


@router.get("/sports/compare")
def compare(p: Auth, home_team_id: str, away_team_id: str, conn=Depends(get_conn)):
    h, a = _team(conn, home_team_id), _team(conn, away_team_id)
    if h["id"] == a["id"]:
        raise HTTPException(422, "Choose two different teams")
    if h["league_id"] != a["league_id"]:
        raise HTTPException(422, "Teams must be in the same league")
    tids, hist = _league_history(conn, h["league_id"])
    res = predict(hist, tids, h["id"], a["id"], _now(), hist and "fictional-dev-dataset" or "none")
    h2h = conn.execute(
        """select m.id, m.kickoff, m.home_goals, m.away_goals, hh.name home_name, aa.name away_name
           from sports_matches m join sports_teams hh on hh.id=m.home_team_id join sports_teams aa on aa.id=m.away_team_id
           where m.status='finished' and ((m.home_team_id=%s and m.away_team_id=%s) or (m.home_team_id=%s and m.away_team_id=%s))
           order by m.kickoff desc limit 10""",
        (h["id"], a["id"], a["id"], h["id"]),
    ).fetchall()
    return {
        "home": h, "away": a, "ratings": res["inputs"], "projection": res["outputs"],
        "home_form": _results(conn, h["id"], 5), "away_form": _results(conn, a["id"], 5), "head_to_head": h2h,
    }


class PredictionRequest(BaseModel):
    fixture_id: int | None = Field(None, ge=1)
    home_team_id: str | None = Field(None, max_length=120)
    away_team_id: str | None = Field(None, max_length=120)

    @model_validator(mode="after")
    def _one_source(self):
        if self.fixture_id is None and not (self.home_team_id and self.away_team_id):
            raise ValueError("provide fixture_id or both home_team_id and away_team_id")
        return self


@router.post("/sports/predictions", status_code=201)
def create_prediction(body: PredictionRequest, p: Auth, conn=Depends(get_conn)):
    require_write(p)
    plans.check_quota(conn, p.workspace_id, "predictions")
    now = _now()
    fixture = None
    if body.fixture_id is not None:
        fixture = conn.execute("select * from sports_matches where id=%s", (body.fixture_id,)).fetchone()
        if not fixture:
            raise HTTPException(404, "Unknown fixture")
        home_id, away_id = fixture["home_team_id"], fixture["away_team_id"]
        cutoff = min(fixture["kickoff"], now)  # never look past the fixture's own kickoff
    else:
        home_id, away_id, cutoff = body.home_team_id, body.away_team_id, now
    h, a = _team(conn, home_id), _team(conn, away_id)
    if h["id"] == a["id"]:
        raise HTTPException(422, "Choose two different teams")
    if h["league_id"] != a["league_id"]:
        raise HTTPException(422, "Teams must be in the same league")

    tids, hist = _league_history(conn, h["league_id"])
    dataset = conn.execute("select data_source from sports_leagues where id=%s", (h["league_id"],)).fetchone()["data_source"]
    res = predict(hist, tids, h["id"], a["id"], cutoff, dataset)
    inputs = {**res["inputs"], "fixture_id": body.fixture_id, "home_name": h["name"], "away_name": a["name"],
              "league_id": h["league_id"], "retrospective": bool(fixture and fixture["status"] == "finished")}
    mv = conn.execute(
        "select id from model_versions where name=%s and version=%s", (sports_model.MODEL_NAME, sports_model.MODEL_VERSION)
    ).fetchone()
    if not mv:
        raise HTTPException(503, "Model version is not registered")
    subject = str(body.fixture_id) if fixture else f"{h['id']}|{a['id']}"
    row = conn.execute(
        """insert into predictions (workspace_id,user_id,domain,model_version_id,subject_type,subject_id,
                                    feature_cutoff,inputs,outputs,assumptions,input_hash,created_at)
           values (%s,%s,'sports',%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id, created_at""",
        (p.workspace_id, p.user_id, mv["id"], "sports_fixture" if fixture else "sports_pairing", subject, cutoff,
         json.dumps(inputs), json.dumps(res["outputs"]), json.dumps(res["assumptions"]), input_hash(inputs), now),
    ).fetchone()
    summary = f"Sports forecast: {h['name']} vs {a['name']}"
    conn.execute(
        "insert into activity_history (workspace_id,user_id,kind,summary,ref_type,ref_id) values (%s,%s,'prediction.created',%s,'prediction',%s)",
        (p.workspace_id, p.user_id, summary, str(row["id"])),
    )
    conn.execute(
        "insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'prediction.create',%s)",
        (p.workspace_id, p.user_id, json.dumps({"prediction_id": str(row["id"]), "model": f"{sports_model.MODEL_NAME}@{sports_model.MODEL_VERSION}"})),
    )
    return {
        "id": row["id"], "created_at": row["created_at"], "feature_cutoff": cutoff,
        "model": {"name": sports_model.MODEL_NAME, "version": sports_model.MODEL_VERSION},
        "inputs": inputs, "outputs": res["outputs"], "assumptions": res["assumptions"],
    }


@router.get("/sports/predictions")
def list_predictions(p: Auth, conn=Depends(get_conn), limit: int = Query(25, ge=1, le=100)):
    rows = conn.execute(
        """select p.id, p.created_at, p.feature_cutoff, p.inputs, p.outputs, mv.name model_name, mv.version model_version
           from predictions p join model_versions mv on mv.id=p.model_version_id
           where p.workspace_id=%s and p.domain='sports' order by p.created_at desc limit %s""",
        (p.workspace_id, limit),
    ).fetchall()
    return {"predictions": rows}


@router.get("/sports/predictions/{prediction_id}")
def get_prediction(prediction_id: str, p: Auth, conn=Depends(get_conn)):
    try:
        row = conn.execute(
            """select p.*, mv.name model_name, mv.version model_version, mv.limitations
               from predictions p join model_versions mv on mv.id=p.model_version_id
               where p.id=%s and p.workspace_id=%s""",
            (prediction_id, p.workspace_id),
        ).fetchone()
    except Exception:
        raise HTTPException(404, "Prediction not found")
    if not row:
        raise HTTPException(404, "Prediction not found")  # same answer for 'other workspace' and 'missing'
    return row


@router.get("/sports/model")
def sports_model_info(p: Auth, conn=Depends(get_conn)):
    mv = conn.execute(
        "select id,name,version,description,status,assumptions,limitations from model_versions where name=%s and version=%s",
        (sports_model.MODEL_NAME, sports_model.MODEL_VERSION),
    ).fetchone()
    metrics = [m for m in _metrics(conn) if m["name"] == sports_model.MODEL_NAME]
    return {"model": mv, "metrics": metrics}


from .business_api import router as business_router  # noqa: E402
from .simulation_api import router as simulation_router  # noqa: E402
from .politics_api import router as politics_router  # noqa: E402
from .finance_api import router as finance_router  # noqa: E402
from .assistant_api import router as assistant_router  # noqa: E402
from .library_api import router as library_router, ws_router  # noqa: E402
from .billing_api import router as billing_router  # noqa: E402
from .team_api import router as team_router  # noqa: E402
from .comments_api import router as comments_router  # noqa: E402
from .data_api import router as data_router  # noqa: E402
from .football_api import router as football_router  # noqa: E402
from .football_intel_api import router as football_intel_router  # noqa: E402
from .football_jobs_api import router as football_jobs_router  # noqa: E402
from .watchlist_api import router as watchlist_router  # noqa: E402
from .reports_api import router as reports_router  # noqa: E402
from .simlab_api import router as simlab_router  # noqa: E402
from .analyst_api import router as analyst_router  # noqa: E402

app.include_router(router)
app.include_router(business_router)
app.include_router(simulation_router)
app.include_router(politics_router)
app.include_router(finance_router)
app.include_router(assistant_router)
app.include_router(library_router)
app.include_router(ws_router)
app.include_router(billing_router)
app.include_router(team_router)
app.include_router(comments_router)
app.include_router(data_router)
app.include_router(football_router)
app.include_router(football_intel_router)
app.include_router(football_jobs_router)
app.include_router(watchlist_router)
app.include_router(reports_router)
app.include_router(simlab_router)
app.include_router(analyst_router)
