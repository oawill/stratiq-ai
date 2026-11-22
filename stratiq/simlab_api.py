"""SimLab API: scenario simulations stored as persistent, versioned, access-controlled records. First domain: sports.

Every run is stored with its inputs, outputs, model version, input-data provenance, random seed (null for the deterministic sports model) and
timestamp. Access follows the workspace: members and above can run and save, every member can read, and a run can be deleted by its
author or an admin. Expensive use is limited: at most RATE_PER_MINUTE runs per person per minute and RATE_PER_DAY per workspace per day.
"""
from __future__ import annotations

import csv
import io
import json
import re
import uuid
from datetime import date, datetime, timezone
from html import escape
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, StringConstraints, field_validator

from . import business_sim as bs
from . import football_intel_api as fia
from . import plans
from . import sports_sim as ss
from .db import get_conn
from .football_api import _plain, _stored
from .security import ADMIN_ROLES, Auth, require_write

router = APIRouter(prefix="/api/v1/simlab", tags=["simlab"])
RATE_PER_MINUTE = 20
RATE_PER_DAY = 300
Team = Annotated[str, StringConstraints(min_length=1, max_length=60)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _no_control(v):
    """Titles and names are free text: control characters (a NUL byte would be rejected by the database) are removed rather than stored."""
    return _CTRL.sub("", v) if isinstance(v, str) else v


class ScenarioIn(BaseModel):
    name: Name
    adjustments: dict[str, float] = Field(default_factory=dict, max_length=len(ss.ADJUSTMENTS))

    _clean_name = field_validator("name", mode="before")(lambda cls, v: _no_control(v))


class SportsRunBody(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None = None
    home: Team
    away: Team
    fixture_date: date | None = None
    scenarios: list[ScenarioIn] = Field(default_factory=list, max_length=ss.MAX_SCENARIOS)
    based_on: uuid.UUID | None = None

    _clean_title = field_validator("title", mode="before")(lambda cls, v: _no_control(v))


class BusinessScenarioIn(BaseModel):
    name: Name
    overrides: dict[str, float] = Field(default_factory=dict, max_length=len(bs.INPUTS))

    _clean_name = field_validator("name", mode="before")(lambda cls, v: _no_control(v))


class BusinessRunBody(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None = None
    inputs: dict[str, float] = Field(max_length=len(bs.INPUTS))
    scenarios: list[BusinessScenarioIn] = Field(default_factory=list, max_length=3)
    based_on: uuid.UUID | None = None

    _clean_title = field_validator("title", mode="before")(lambda cls, v: _no_control(v))


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _limit(conn, p) -> None:
    n = conn.execute("""select (select count(*) from simlab_runs where workspace_id=%s and created_by=%s and created_at > now() - interval '1 minute')
                         + (select count(*) from strategic_scenarios where workspace_id=%s and created_by=%s and created_at > now() - interval '1 minute') n""",
                     (p.workspace_id, p.user_id, p.workspace_id, p.user_id)).fetchone()["n"]
    if n >= RATE_PER_MINUTE:
        raise HTTPException(429, f"Too many simulations: at most {RATE_PER_MINUTE} per minute. Wait a moment and try again.")
    d = conn.execute("""select (select count(*) from simlab_runs where workspace_id=%s and created_at > now() - interval '1 day')
                         + (select count(*) from strategic_scenarios where workspace_id=%s and created_at > now() - interval '1 day') n""", (p.workspace_id, p.workspace_id)).fetchone()["n"]
    if d >= RATE_PER_DAY:
        raise HTTPException(429, f"This workspace has reached its limit of {RATE_PER_DAY} simulations in 24 hours.")


@router.get("/sports/adjustments")
def adjustments(p: Auth):
    """The adjustments the sports model understands, with their ranges and plain meanings, and the model documentation."""
    return {"adjustments": [{"key": k, "label": v[3], "min": v[0], "max": v[1], "neutral": v[2], "meaning": v[4]} for k, v in ss.ADJUSTMENTS.items()],
            "documentation": ss.DOCUMENTATION, "model_version": ss.SIM_VERSION, "max_scenarios": ss.MAX_SCENARIOS}


@router.get("/sports/context")
def context(p: Auth, conn=Depends(get_conn)):
    """What the simulator can start from: clubs in the imported history and the upcoming imported fixtures."""
    ms = _plain(_stored(conn, p.workspace_id, fia.COMPETITION))
    teams = sorted({t for _, h, a, *_ in ms for t in (h, a)})
    fx = conn.execute("select fixture_date, home_team, away_team from football_fixtures where status not in ('cancelled','postponed','suspended') and workspace_id=%s and fixture_date >= %s order by fixture_date limit 40", (p.workspace_id, _today())).fetchall()
    run = fia._latest_run(conn, p)
    return {"has_history": bool(ms), "teams": teams, "fixtures": [{"date": r["fixture_date"], "home": r["home_team"], "away": r["away_team"]} for r in fx],
            "settings_tuned": bool(run and run["tuning"]), "history_through": max(m[0] for m in ms).isoformat() if ms else None}


@router.post("/sports/run", status_code=201)
def sports_run(body: SportsRunBody, p: Auth, conn=Depends(get_conn)):
    require_write(p)
    plans.check_quota(conn, p.workspace_id, "scenarios")
    _limit(conn, p)
    ms = _plain(_stored(conn, p.workspace_id, fia.COMPETITION))
    if not ms:
        raise HTTPException(404, "Import some match history first (Data page, Historical Football Data).")
    scheduled = False
    if body.fixture_date:
        row = conn.execute("select 1 from football_fixtures where status not in ('cancelled','postponed','suspended') and workspace_id=%s and fixture_date=%s and home_team=%s and away_team=%s",
                           (p.workspace_id, body.fixture_date, body.home, body.away)).fetchone()
        if not row:
            raise HTTPException(422, "That fixture is not among the imported upcoming fixtures. Leave the date empty to simulate a hypothetical matchup.")
        scheduled = True
    cutoff = min(body.fixture_date, _today()) if body.fixture_date else _today()
    parent = None
    if body.based_on:
        parent = conn.execute("select id, scenario_key, version, domain from simlab_runs where id=%s and workspace_id=%s", (body.based_on, p.workspace_id)).fetchone()
        if not parent or parent["domain"] != "sports":
            raise HTTPException(404, "The run to build on was not found")
    try:
        result = ss.run(sorted(ms, key=lambda m: (m[0], m[1], m[2])), body.home, body.away, cutoff, fia._settings(fia._latest_run(conn, p)),
                        [{"name": s.name, "adjustments": s.adjustments} for s in body.scenarios], scheduled, body.fixture_date)
    except ValueError as e:
        raise HTTPException(422, str(e))
    title = body.title or f"{body.home} v {body.away}"
    key = parent["scenario_key"] if parent else uuid.uuid4()
    version = parent["version"] + 1 if parent else 1
    inputs = {"home": body.home, "away": body.away, "fixture_date": body.fixture_date.isoformat() if body.fixture_date else None, "cutoff": cutoff.isoformat(),
              "scenarios": [{"name": s.name, "adjustments": s.adjustments} for s in body.scenarios]}
    row = conn.execute(
        """insert into simlab_runs (workspace_id, created_by, domain, title, scenario_key, version, parent_id, model_name, model_version, inputs, outputs, provenance, seed)
           values (%s,%s,'sports',%s,%s,%s,%s,'sports_sim',%s,%s,%s,%s,null) returning id, created_at""",
        (p.workspace_id, p.user_id, title, key, version, parent["id"] if parent else None, ss.SIM_VERSION, json.dumps(inputs), json.dumps(result), json.dumps(result["provenance"]))).fetchone()
    conn.execute("insert into activity_history (workspace_id,user_id,kind,summary,ref_type,ref_id) values (%s,%s,'simlab.run',%s,'simlab_run',%s)",
                 (p.workspace_id, p.user_id, f"Ran a sports simulation: {title} (version {version})", str(row["id"])))
    return {"id": str(row["id"]), "title": title, "scenario_key": str(key), "version": version, "parent_id": str(parent["id"]) if parent else None, "created_at": row["created_at"], **result}


def _headline(o: dict) -> dict:
    b = o.get("baseline") or {}
    base = o.get("base") or {}
    return {"baseline_percent": b.get("percent"), "scenarios": len(o.get("scenarios") or []), "scheduled": (o.get("matchup") or {}).get("scheduled"),
            "gross_profit": base.get("gross_profit"), "revenue": base.get("revenue")}


@router.get("/business/inputs")
def business_inputs(p: Auth):
    return {"inputs": [{"key": k, "label": v[2], "meaning": v[3], "min": v[0], "max": v[1]} for k, v in bs.INPUTS.items()], "documentation": bs.DOCUMENTATION, "model_version": bs.SIM_VERSION}


@router.post("/business/run", status_code=201)
def business_run(body: BusinessRunBody, p: Auth, conn=Depends(get_conn)):
    """A hypothetical pricing scenario: every input is the user's assumption. Stored like any other SimLab run."""
    require_write(p)
    plans.check_quota(conn, p.workspace_id, "scenarios")
    _limit(conn, p)
    try:
        result = bs.run(body.inputs, [{"name": s.name, "overrides": s.overrides} for s in body.scenarios])
    except ValueError as e:
        raise HTTPException(422, str(e))
    parent = None
    if body.based_on:
        parent = conn.execute("select id, scenario_key, version, domain from simlab_runs where id=%s and workspace_id=%s", (body.based_on, p.workspace_id)).fetchone()
        if not parent or parent["domain"] != "business":
            raise HTTPException(404, "The run to build on was not found")
    title = body.title or "Pricing scenario"
    key = parent["scenario_key"] if parent else uuid.uuid4()
    version = parent["version"] + 1 if parent else 1
    inputs = {"inputs": result["inputs"], "scenarios": [{"name": s.name, "overrides": s.overrides} for s in body.scenarios]}
    stamp = datetime.now(timezone.utc).isoformat()
    result["provenance"] = {**result["provenance"], "generated_at": stamp}
    row = conn.execute(
        """insert into simlab_runs (workspace_id, created_by, domain, title, scenario_key, version, parent_id, model_name, model_version, inputs, outputs, provenance, seed)
           values (%s,%s,'business',%s,%s,%s,%s,'business_sim',%s,%s,%s,%s,null) returning id, created_at""",
        (p.workspace_id, p.user_id, title, key, version, parent["id"] if parent else None, bs.SIM_VERSION, json.dumps(inputs), json.dumps(result), json.dumps(result["provenance"]))).fetchone()
    conn.execute("insert into activity_history (workspace_id,user_id,kind,summary,ref_type,ref_id) values (%s,%s,'simlab.run',%s,'simlab_run',%s)",
                 (p.workspace_id, p.user_id, f"Ran a business simulation: {title} (version {version})", str(row["id"])))
    return {"id": str(row["id"]), "title": title, "scenario_key": str(key), "version": version, "parent_id": str(parent["id"]) if parent else None, "created_at": row["created_at"], **result}


@router.get("/runs")
def list_runs(p: Auth, conn=Depends(get_conn), domain: Literal["sports", "business", "politics", "markets"] | None = None, limit: int = Query(50, ge=1, le=200)):
    rows = conn.execute(
        """select r.id, r.domain, r.title, r.scenario_key, r.version, r.parent_id, r.model_name, r.model_version, r.created_at, r.outputs, u.name created_by_name
           from simlab_runs r join users u on u.id=r.created_by where r.workspace_id=%s and (%s::text is null or r.domain=%s) order by r.created_at desc limit %s""",
        (p.workspace_id, domain, domain, limit)).fetchall()
    return {"runs": [{**{k: r[k] for k in ("id", "domain", "title", "scenario_key", "version", "parent_id", "model_name", "model_version", "created_at", "created_by_name")}, **_headline(r["outputs"])} for r in rows]}


def _get(conn, p, run_id: uuid.UUID):
    row = conn.execute("select r.*, u.name created_by_name from simlab_runs r join users u on u.id=r.created_by where r.id=%s and r.workspace_id=%s", (run_id, p.workspace_id)).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return row


@router.get("/runs/{run_id}")
def get_run(run_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    r = _get(conn, p, run_id)
    versions = conn.execute("select id, version, created_at from simlab_runs where workspace_id=%s and scenario_key=%s order by version", (p.workspace_id, r["scenario_key"])).fetchall()
    return {"id": str(r["id"]), "domain": r["domain"], "title": r["title"], "scenario_key": str(r["scenario_key"]), "version": r["version"], "parent_id": str(r["parent_id"]) if r["parent_id"] else None,
            "created_at": r["created_at"], "created_by_name": r["created_by_name"], "model_name": r["model_name"], "model_version": r["model_version"], "seed": r["seed"],
            "inputs": r["inputs"], "versions": [{"id": str(v["id"]), "version": v["version"], "created_at": v["created_at"]} for v in versions], **r["outputs"]}


@router.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    r = _get(conn, p, run_id)
    if str(r["created_by"]) != str(p.user_id) and p.role not in ADMIN_ROLES:
        raise HTTPException(403, "Only the person who ran this simulation, or an admin, can delete it")
    conn.execute("delete from simlab_runs where id=%s and workspace_id=%s", (run_id, p.workspace_id))
    conn.execute("insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'simlab.delete',%s)", (p.workspace_id, p.user_id, json.dumps({"run_id": str(run_id)})))


def sports_csv(title: str, o: dict, version: int, created_at) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    prov = o["provenance"]
    w.writerow(["# VELQORIN SimLab sports simulation", title, f"version {version}"])
    w.writerow(["# HYPOTHETICAL scenarios compared with a model baseline. Not forecasts, not betting or financial advice."])
    w.writerow(["# matchup", f"{o['matchup']['home']} v {o['matchup']['away']}", o["matchup"]["label"]])
    w.writerow(["# model", f"{prov['model']}@{prov['model_version']} on {prov['base_model']}", f"training cutoff {prov['training_cutoff']}", f"data through {prov['data_through']}", f"matches used {prov['matches_used']}",
                f"data sha256 {prov['data_sha256']}", f"generated {prov['generated_at']}", f"saved {created_at}", "random seed: none (deterministic)"])
    w.writerow(["scenario", "home_win_percent", "draw_percent", "away_win_percent", "expected_goals_home", "expected_goals_away", "over_2_5_percent", "both_teams_score_percent",
                "change_home_win_points", "change_draw_points", "change_away_win_points", "assumptions_changed"])
    rows = [("Baseline", o["baseline"], None)] + [(s["name"], s, s["delta_vs_baseline"]) for s in o["scenarios"]]
    for name, s, d in rows:
        changed = "; ".join(f"{k}={s['adjustments'][k]:g}" for k in s.get("changed", [])) if name != "Baseline" else "none (calibrated from data)"
        w.writerow([name, *s["percent"], round(s["expected_goals"][0], 3), round(s["expected_goals"][1], 3), round(s["p_over_2_5"] * 100, 1), round(s["p_btts"] * 100, 1),
                    *(["", "", ""] if d is None else [round(d["p_home"], 2), round(d["p_draw"], 2), round(d["p_away"], 2)]), changed])
    w.writerow([])
    w.writerow(["# calibrated parameters (estimated from data)"])
    for c in o["calibrated_parameters"]:
        w.writerow([c["name"], round(c["value"], 4) if isinstance(c["value"], float) else c["value"]])
    w.writerow(["# " + o["validation_status"]])
    return out.getvalue()


def business_csv(title: str, o: dict, version: int, created_at) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["# VELQORIN SimLab business simulation", title, f"version {version}", f"saved {created_at}"])
    w.writerow(["# " + o["label"]])
    w.writerow(["# model", f"business_sim@{o['provenance']['model_version']}", "random seed: none (deterministic)", "all inputs are the user's assumptions"])
    w.writerow(["scenario", "price", "units", "revenue", "gross_profit", "gross_margin", "assumptions_changed"])
    b = o["base"]
    w.writerow(["Base case", b["price"], round(b["units"], 3), round(b["revenue"], 2), round(b["gross_profit"], 2), "" if b["gross_margin"] is None else round(b["gross_margin"], 4), "none"])
    for s in o["scenarios"]:
        w.writerow([s["name"], s["price"], round(s["units"], 3), round(s["revenue"], 2), round(s["gross_profit"], 2), "" if s["gross_margin"] is None else round(s["gross_margin"], 4),
                    "; ".join(f"{k}={v:g}" for k, v in s["overrides"].items()) or "none"])
    w.writerow([])
    w.writerow(["# sensitivity: each input moved by -10% and +10% in turn"])
    w.writerow(["input", "base_value", "gross_profit_change_at_minus_10pct", "gross_profit_change_at_plus_10pct"])
    for r in o["sensitivity"]:
        w.writerow([r["label"], r["base_value"], "" if not r["low"] else round(r["low"]["gross_profit_change"], 2), "" if not r["high"] else round(r["high"]["gross_profit_change"], 2)])
    w.writerow(["# " + o["validation_status"]])
    return out.getvalue()


def sports_html(title: str, o: dict, version: int, created_at) -> str:
    """A self-contained page that prints cleanly (use the browser's Print, then Save as PDF)."""
    prov = o["provenance"]
    head = "".join(f"<th>{escape(h)}</th>" for h in ["Scenario", "Home win", "Draw", "Away win", "xG home", "xG away", "Over 2.5", "Both score", "Assumptions changed"])
    body = ""
    for name, s in [("Baseline", o["baseline"])] + [(x["name"], x) for x in o["scenarios"]]:
        changed = "none (calibrated from data)" if name == "Baseline" else "; ".join(f"{escape(k)} = {s['adjustments'][k]:g}" for k in s.get("changed", [])) or "none"
        body += (f"<tr><th scope='row'>{escape(name)}</th><td>{s['percent'][0]}%</td><td>{s['percent'][1]}%</td><td>{s['percent'][2]}%</td><td>{s['expected_goals'][0]:.2f}</td>"
                 f"<td>{s['expected_goals'][1]:.2f}</td><td>{s['p_over_2_5'] * 100:.1f}%</td><td>{s['p_btts'] * 100:.1f}%</td><td>{changed}</td></tr>")
    params = "".join(f"<li>{escape(c['name'])}: {round(c['value'], 4) if isinstance(c['value'], float) else c['value']}</li>" for c in o["calibrated_parameters"])
    return (f"<!doctype html><html lang='en'><meta charset='utf-8'><title>{escape(title)}</title><style>body{{font:14px/1.5 system-ui,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem;color:#111}}"
            f"table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccc;padding:.35rem .5rem;text-align:left}}.warn{{border:2px dashed #b45309;padding:.6rem;margin:1rem 0}}</style>"
            f"<h1>{escape(title)}</h1><p>VELQORIN SimLab sports simulation, version {version}, saved {escape(str(created_at))}</p>"
            f"<div class='warn'><strong>Hypothetical scenarios compared with a model baseline.</strong> Not forecasts, not betting or financial advice. {escape(o['matchup']['label'])}</div>"
            f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
            f"<h2>Model and provenance</h2><p>{escape(o['documentation'])}</p><p>{escape(o['validation_status'])}</p>"
            f"<p>{escape(prov['model'])}@{escape(prov['model_version'])} on {escape(prov['base_model'])}; training cutoff {prov['training_cutoff']}; data through {prov['data_through']}; "
            f"{prov['matches_used']} matches; data SHA-256 {prov['data_sha256']}; generated {escape(prov['generated_at'])}; random seed: none (deterministic).</p>"
            f"<h2>Calibrated parameters (estimated from data)</h2><ul>{params}</ul></html>")


@router.get("/runs/{run_id}/export")
def export(run_id: uuid.UUID, p: Auth, conn=Depends(get_conn), format: Literal["csv", "html", "json"] = "csv"):
    plans.check_exports(conn, p.workspace_id)
    r = _get(conn, p, run_id)
    if r["domain"] not in ("sports", "business"):
        raise HTTPException(422, "Only sports and business simulations can be exported so far")
    slug = re.sub(r"[^a-z0-9]+", "-", r["title"].lower()).strip("-")[:50] or "simulation"
    if format == "csv":
        body, media = (sports_csv if r["domain"] == "sports" else business_csv)(r["title"], r["outputs"], r["version"], r["created_at"]), "text/csv"
    elif format == "html":
        if r["domain"] != "sports":
            raise HTTPException(422, "The printable page is available for sports simulations only; use CSV or JSON.")
        body, media = sports_html(r["title"], r["outputs"], r["version"], r["created_at"]), "text/html"
    else:
        body, media = json.dumps({"title": r["title"], "version": r["version"], "inputs": r["inputs"], "outputs": r["outputs"], "provenance": r["provenance"]}, indent=2, default=str), "application/json"
    conn.execute("insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'simlab.export',%s)", (p.workspace_id, p.user_id, json.dumps({"run_id": str(run_id), "format": format})))
    return Response(body, media_type=f"{media}; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{slug}-v{r["version"]}.{format}"'})


# ------------------------------------------------------------------ one list across every store
# Sports and business-pricing runs live in simlab_runs. Political, financial and strategy-game scenarios live in strategic_scenarios so the library, comments, the
# assistant and exports keep working; SimLab lists, opens, exports and deletes them alongside the runs, and they carry the same version chain and provenance.
SCENARIO_DOMAINS = {"politics": "politics", "finance": "markets", "business": "business"}
MODULE_HREF = {"politics": "/dashboard/politics", "markets": "/dashboard/finance", "business": "/dashboard/business", "sports": "/dashboard/sports"}
NOTICES = {"politics": "Scenario arithmetic on entered assumptions. Not a poll, not a validated election forecast.",
           "markets": "Educational scenario analysis. Not investment advice, not a forecast, and not connected to any broker.",
           "business": "A game built from payoffs you entered. An equilibrium is a prediction about stable play, not a recommendation."}


@router.get("/saved")
def saved(p: Auth, conn=Depends(get_conn), domain: Literal["sports", "business", "politics", "markets"] | None = None, limit: int = Query(100, ge=1, le=300)):
    """Every saved SimLab run and scenario in the workspace, newest first, with its domain, version and where it is stored."""
    out = []
    for r in conn.execute(
        """select r.id, r.domain, r.title, r.scenario_key, r.version, r.model_name, r.model_version, r.created_at, r.outputs, u.name created_by_name
           from simlab_runs r join users u on u.id=r.created_by where r.workspace_id=%s and (%s::text is null or r.domain=%s) order by r.created_at desc limit %s""",
            (p.workspace_id, domain, domain, limit)).fetchall():
        out.append({"source": "run", "id": str(r["id"]), "domain": r["domain"], "kind": r["domain"], "title": r["title"], "scenario_key": str(r["scenario_key"]), "version": r["version"],
                    "created_at": r["created_at"], "created_by_name": r["created_by_name"], "engine": f"{r['model_name']}@{r['model_version']}", **_headline(r["outputs"])})
    wanted = [k for k, v in SCENARIO_DOMAINS.items() if domain is None or v == domain]
    if wanted:
        for r in conn.execute(
            """select s.id, s.domain, s.title, s.created_at, s.definition, u.name created_by_name from strategic_scenarios s join users u on u.id=s.created_by
               where s.workspace_id=%s and s.domain = any(%s) order by s.created_at desc limit %s""", (p.workspace_id, wanted, limit)).fetchall():
            d = r["definition"] or {}
            prov = d.get("provenance") or {}
            out.append({"source": "scenario", "id": str(r["id"]), "domain": SCENARIO_DOMAINS[r["domain"]], "kind": d.get("kind") or "payoff game", "title": r["title"],
                        "scenario_key": d.get("scenario_key") or str(r["id"]), "version": int(d.get("version", 1)), "created_at": r["created_at"], "created_by_name": r["created_by_name"],
                        "engine": f"{prov['engine']}@{prov['engine_version']}" if prov.get("engine") else None, "scenarios": None})
    out.sort(key=lambda x: x["created_at"], reverse=True)
    return {"runs": out[:limit]}


def _scenario(conn, p, sid: uuid.UUID):
    row = conn.execute("select s.*, u.name created_by_name from strategic_scenarios s join users u on u.id=s.created_by where s.id=%s and s.workspace_id=%s and s.domain = any(%s)",
                       (sid, p.workspace_id, list(SCENARIO_DOMAINS))).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return row


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    r = _scenario(conn, p, scenario_id)
    d = r["definition"] or {}
    dom = SCENARIO_DOMAINS[r["domain"]]
    return {"source": "scenario", "id": str(r["id"]), "domain": dom, "kind": d.get("kind") or "payoff game", "title": r["title"], "version": int(d.get("version", 1)), "scenario_key": d.get("scenario_key") or str(r["id"]),
            "created_at": r["created_at"], "created_by_name": r["created_by_name"], "notes": d.get("notes"), "summary": d.get("summary"), "provenance": d.get("provenance"),
            "notice": NOTICES[dom], "module_href": MODULE_HREF[dom], "players": d.get("players"), "row_strategies": d.get("row_strategies"), "col_strategies": d.get("col_strategies")}


@router.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    require_write(p)
    r = _scenario(conn, p, scenario_id)
    if str(r["created_by"]) != str(p.user_id) and p.role not in ADMIN_ROLES:
        raise HTTPException(403, "Only the person who saved this scenario, or an admin, can delete it")
    conn.execute("delete from strategic_scenarios where id=%s and workspace_id=%s", (scenario_id, p.workspace_id))
    conn.execute("insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'simlab.delete_scenario',%s)", (p.workspace_id, p.user_id, json.dumps({"scenario_id": str(scenario_id), "title": r["title"], "domain": r["domain"]})))


def _flatten(prefix: str, v, out: list) -> None:
    if isinstance(v, dict):
        for k, x in v.items():
            _flatten(f"{prefix}.{k}" if prefix else str(k), x, out)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            _flatten(f"{prefix}[{i}]", x, out)
    else:
        out.append((prefix, v))


@router.get("/scenarios/{scenario_id}/export")
def export_scenario(scenario_id: uuid.UUID, p: Auth, conn=Depends(get_conn), format: Literal["csv", "json"] = "csv"):
    plans.check_exports(conn, p.workspace_id)
    r = _scenario(conn, p, scenario_id)
    d = r["definition"] or {}
    dom = SCENARIO_DOMAINS[r["domain"]]
    slug = re.sub(r"[^a-z0-9]+", "-", r["title"].lower()).strip("-")[:50] or "scenario"
    version = int(d.get("version", 1))
    if format == "json":
        body, media = json.dumps({"title": r["title"], "domain": dom, "kind": d.get("kind"), "version": version, "scenario_key": d.get("scenario_key"), "notes": d.get("notes"), "inputs": d.get("inputs"),
                                  "summary": d.get("summary"), "provenance": d.get("provenance"), "notice": NOTICES[dom]}, indent=2, default=str), "application/json"
    else:
        out = io.StringIO()
        w = csv.writer(out, lineterminator="\n")
        w.writerow(["# VELQORIN SimLab scenario", r["title"], f"version {version}", f"saved {r['created_at']}"])
        w.writerow(["# " + NOTICES[dom]])
        w.writerow(["# provenance", json.dumps(d.get("provenance") or {"note": "saved before provenance was recorded"}, default=str)])
        w.writerow(["field", "value"])
        rows: list = []
        _flatten("", d.get("summary") or {}, rows)
        for k, v in rows:
            w.writerow([k, v])
        body, media = out.getvalue(), "text/csv"
    conn.execute("insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'simlab.export',%s)", (p.workspace_id, p.user_id, json.dumps({"scenario_id": str(scenario_id), "format": format})))
    return Response(body, media_type=f"{media}; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{slug}-v{version}.{format}"'})
