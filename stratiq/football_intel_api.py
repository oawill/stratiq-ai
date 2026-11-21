"""Football prediction intelligence API: backtests, match intelligence, what-if scenarios, upcoming fixtures and tracked outcomes.

Forecasts use match results (and uploaded statistics where they exist) only; factors without data are reported as unavailable.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StringConstraints

from . import football_backtest as fb
from . import football_intel as fi
from . import football_store
from .db import get_conn
from .football_api import _plain, _stored
from .security import Auth, require_write

router = APIRouter(prefix="/api/v1/football/intel", tags=["football-intelligence"])
Team = Annotated[str, StringConstraints(min_length=1, max_length=60)]
COMPETITION = "EPL"
LIVE_VERSION = "1.0.0"


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _history(conn, p) -> list:
    rows = _plain(_stored(conn, p.workspace_id, COMPETITION))
    if not rows:
        raise HTTPException(404, "Import some match history first (Data page, Historical Football Data).")
    return rows


def _latest_run(conn, p, mode: str = "chronological"):
    return conn.execute("select * from football_backtest_runs where workspace_id=%s and mode=%s and status='complete' order by created_at desc limit 1", (p.workspace_id, mode)).fetchone()


def _settings(run) -> dict:
    """Tuned settings from the latest chronological backtest (fitted on training + validation only), else untuned defaults."""
    if not run or not run["tuning"]:
        return fi.default_settings()
    t = run["tuning"]
    s = {"tuned": True, "run_id": str(run["id"]), "elo": {**t["elo"]["chosen"], **t["elo"]["mapping_for_test"]}, "poisson": t["poisson"]["chosen"], "rho": t["dixon_coles"]["rho_test"]}
    if t.get("gbm") and t.get("ensemble"):
        s["gbm"], s["ensemble"] = t["gbm"]["model_for_test"], t["ensemble"]
    return s


def _light(settings: dict) -> dict:
    """Settings without the tree structure, for recording against a model version (the run id identifies the trees)."""
    return {k: v for k, v in settings.items() if k != "gbm"} | ({"gbm": {"rounds": settings["gbm"]["rounds"], "max_depth": settings["gbm"]["params"]["max_depth"]}} if settings.get("gbm") else {})


def _calibration(run) -> dict | None:
    if not run or not run["results"]:
        return None
    m = run["results"].get("test", {}).get("dixon_coles", {}).get("1x2")
    return {"model": "Dixon-Coles", "period": "test", "matches": m["n"], "calibration_error": m["calibration_error"], "log_loss": m["log_loss"],
            "note": "Average gap between predicted and observed frequencies on the test period; lower is better calibrated."} if m else None


def _version(conn, p, name: str, params: dict, data_sha: str, run_id=None, trained_through: date | None = None) -> str:
    row = conn.execute(
        """select id from football_model_versions where workspace_id=%s and name=%s and version=%s and data_sha256=%s and backtest_run_id is not distinct from %s and params=%s::jsonb""",
        (p.workspace_id, name, fb.MODEL_VERSION if run_id else LIVE_VERSION, data_sha, run_id, json.dumps(params, sort_keys=True))).fetchone()
    if row:
        return str(row["id"])
    return str(conn.execute(
        "insert into football_model_versions (workspace_id, name, version, params, trained_through, data_sha256, backtest_run_id) values (%s,%s,%s,%s,%s,%s,%s) returning id",
        (p.workspace_id, name, fb.MODEL_VERSION if run_id else LIVE_VERSION, json.dumps(params, sort_keys=True), trained_through, data_sha, run_id)).fetchone()["id"])


# ------------------------------------------------------------------ factors
@router.get("/factors")
def factors(p: Auth, conn=Depends(get_conn)):
    """Every factor group, where it comes from, and whether this workspace has data behind it."""
    n_res = conn.execute("select count(*) n, min(match_date) a, max(match_date) b from match_history where workspace_id=%s", (p.workspace_id,)).fetchone()
    st = conn.execute("select count(*) n, count(home_xg) xg, count(odds_home) odds from football_team_statistics where workspace_id=%s", (p.workspace_id,)).fetchone()
    fx = conn.execute("select count(*) n from football_fixtures where workspace_id=%s and fixture_date >= current_date", (p.workspace_id,)).fetchone()["n"]
    have = {"results": n_res["n"] > 0, "xg": st["xg"] > 0, "odds": st["odds"] > 0, "venue": n_res["n"] > 0, "never": False}
    sources = conn.execute(
        """select distinct on (kind) kind, name, provider, reference, licence_note, coverage, quality, created_at from football_data_sources where workspace_id=%s
           order by kind, created_at desc""", (p.workspace_id,)).fetchall()
    return {"factors": [{**f, "status": "available" if have[f["needs"]] else "unavailable"} for f in fi.FACTORS],
            "data": {"matches": n_res["n"], "first": n_res["a"], "last": n_res["b"], "statistics_rows": st["n"], "xg_rows": st["xg"], "odds_rows": st["odds"], "upcoming_fixtures": fx},
            "sources": sources,
            "notes": ["A factor is only used when data for it exists; nothing is estimated or filled in.", "VELQORIN does not fetch data: every source here was uploaded by a person in this workspace."]}


# ------------------------------------------------------------------ backtests
class BacktestBody(BaseModel):
    mode: Literal["chronological", "rolling"] = "chronological"
    split: dict[str, list[str]] | None = Field(default=None, description="Optional training/validation/test seasons, e.g. {'validation': ['2023/24'], 'test': ['2024/25']}")


def _store_run(conn, p, res: dict, ms: list) -> dict:
    now = datetime.now(timezone.utc)
    config = {"split": res.get("split"), "periods": res.get("periods"), "seasons_predicted": res.get("seasons_predicted"), "settings": res.get("settings"), "model_version": fb.MODEL_VERSION}
    run = conn.execute(
        """insert into football_backtest_runs (workspace_id, mode, config, data_sha256, matches, results, tuning, warnings, created_by, finished_at) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id, created_at""",
        (p.workspace_id, res["mode"], json.dumps(config, default=str), res["data_sha256"], res["matches"], json.dumps(res["results"]), json.dumps(res.get("tuning") or {}) if res.get("tuning") else None,
         json.dumps(res["warnings"]), p.user_id, now)).fetchone()
    run_id = str(run["id"])
    last = ms[-1][0] if ms else None
    versions = {}
    for model in fb.MODELS:
        tun = (res.get("tuning") or {}).get(model)
        if model == "gbm" and tun:
            tun = {k: v for k, v in tun.items() if k != "model_for_test"}
        params = {"model": model, "tuning": tun, "settings": res.get("settings")}
        versions[model] = _version(conn, p, model, params, res["data_sha256"], run_id, last)
    pred_rows, out_rows = [], []
    for r in res["predictions"]:
        pid = uuid.uuid4()
        pr = r["probs"]
        outputs = {"drivers": r.get("drivers"), "actual": r["actual"], "top_scoreline_hit": r.get("top_scoreline_hit")}
        pred_rows.append((pid, p.workspace_id, run_id, versions[r["model"]], r.get("period"), r["season"], r["date"], r["home"], r["away"], r["date"], pr[0], pr[1], pr[2], r.get("p_over_2_5"), r.get("p_btts"),
                          (r.get("xg") or [None, None])[0], (r.get("xg") or [None, None])[1], json.dumps(outputs), json.dumps(r["inputs"])))
        y = r["actual_outcome"]
        out_rows.append((pid, r["actual"][0], r["actual"][1], y, -math.log(max(pr[y], 1e-12)), sum((pr[k] - (1.0 if k == y else 0.0)) ** 2 for k in range(3)), max(range(3), key=lambda k: pr[k]) == y))
    with conn.cursor() as cur:
        cur.executemany(
            """insert into football_predictions (id, workspace_id, kind, backtest_run_id, model_version_id, period, season, fixture_date, home_team, away_team, cutoff, p_home, p_draw, p_away,
               p_over_2_5, p_btts, expected_home, expected_away, outputs, inputs) values (%s,%s,'backtest',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", pred_rows)
        cur.executemany("insert into football_prediction_outcomes (prediction_id, home_goals, away_goals, outcome, log_loss, brier, correct) values (%s,%s,%s,%s,%s,%s,%s)", out_rows)
    conn.execute("insert into activity_history (workspace_id,user_id,kind,summary,ref_type,ref_id) values (%s,%s,'football.backtest',%s,'football_backtest',%s)",
                 (p.workspace_id, p.user_id, f"Ran a {res['mode']} football backtest on {res['matches']:,} matches", run_id))
    conn.execute("insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'football.backtest',%s)",
                 (p.workspace_id, p.user_id, json.dumps({"run_id": run_id, "mode": res["mode"], "data_sha256": res["data_sha256"], "predictions": len(pred_rows)})))
    return {"id": run_id, "created_at": run["created_at"]}


@router.post("/backtest")
def backtest(body: BacktestBody, p: Auth, conn=Depends(get_conn)):
    """Replay history chronologically (tune on validation, report a later test period) or by rolling origin (fixed settings, each season from earlier ones).
    Every forecast uses only matches played before its fixture. Takes up to a minute on ten seasons."""
    require_write(p)
    ms = _history(conn, p)
    try:
        split = None
        if body.split:
            base = fb.default_split(ms) if body.mode == "chronological" else None
            split = {**(base or {}), **body.split} if base else body.split
            if not all(k in split for k in ("training", "validation", "test")):
                split = {**fb.default_split(ms), **body.split}
        res = fb.run_chronological(ms, split) if body.mode == "chronological" else fb.run_rolling(ms)
    except ValueError as e:
        raise HTTPException(422, str(e))
    meta = _store_run(conn, p, res, ms)
    return {**meta, **{k: res[k] for k in res if k != "predictions"}, "predictions_stored": len(res["predictions"])}


@router.get("/backtests")
def backtests(p: Auth, conn=Depends(get_conn)):
    rows = conn.execute("select id, mode, status, data_sha256, matches, config, warnings, created_at, finished_at from football_backtest_runs where workspace_id=%s order by created_at desc limit 20", (p.workspace_id,)).fetchall()
    return {"runs": rows}


@router.get("/backtests/{run_id}")
def backtest_detail(run_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    r = conn.execute("select * from football_backtest_runs where id=%s and workspace_id=%s", (run_id, p.workspace_id)).fetchone()
    if not r:
        raise HTTPException(404, "Backtest not found")
    current = fb.data_sha(sorted(_plain(_stored(conn, p.workspace_id, COMPETITION)), key=lambda m: (m[0], m[1], m[2])))
    return {**r, "history_changed_since": current != r["data_sha256"]}


@router.get("/backtests/{run_id}/predictions")
def backtest_predictions(run_id: uuid.UUID, p: Auth, conn=Depends(get_conn), model: str | None = None, period: str | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    if not conn.execute("select 1 from football_backtest_runs where id=%s and workspace_id=%s", (run_id, p.workspace_id)).fetchone():
        raise HTTPException(404, "Backtest not found")
    rows = conn.execute(
        """select pr.fixture_date, pr.home_team, pr.away_team, pr.season, pr.period, v.name model, pr.p_home, pr.p_draw, pr.p_away, pr.p_over_2_5, pr.p_btts, pr.expected_home, pr.expected_away,
                  pr.outputs, pr.inputs, o.home_goals, o.away_goals, o.log_loss, o.correct
           from football_predictions pr join football_model_versions v on v.id=pr.model_version_id left join football_prediction_outcomes o on o.prediction_id=pr.id
           where pr.backtest_run_id=%s and (%s::text is null or v.name=%s) and (%s::text is null or pr.period=%s) order by pr.fixture_date, pr.home_team, v.name limit %s offset %s""",
        (run_id, model, model, period, period, limit, offset)).fetchall()
    return {"predictions": rows, "limit": limit, "offset": offset}


@router.get("/performance")
def performance(p: Auth, conn=Depends(get_conn)):
    """What the dashboard shows: the latest backtests and how tracked live forecasts have done since."""
    chrono, rolling = _latest_run(conn, p), _latest_run(conn, p, "rolling")
    live = conn.execute(
        """select v.name model, count(*) n, avg(o.log_loss) log_loss, avg(o.brier) brier, avg(case when o.correct then 1.0 else 0.0 end) accuracy
           from football_predictions pr join football_model_versions v on v.id=pr.model_version_id join football_prediction_outcomes o on o.prediction_id=pr.id
           where pr.workspace_id=%s and pr.kind='live' group by v.name""", (p.workspace_id,)).fetchall()
    pending = conn.execute("select count(*) n from football_predictions pr left join football_prediction_outcomes o on o.prediction_id=pr.id where pr.workspace_id=%s and pr.kind='live' and o.prediction_id is null", (p.workspace_id,)).fetchone()["n"]
    shape = lambda r: None if not r else {"id": r["id"], "mode": r["mode"], "created_at": r["created_at"], "matches": r["matches"], "config": r["config"], "results": r["results"], "tuning": r["tuning"], "warnings": r["warnings"]}
    return {"chronological": shape(chrono), "rolling": shape(rolling), "live": {"scored": live, "waiting_for_results": pending}, "models": fb.MODELS}


# ------------------------------------------------------------------ match intelligence and scenarios
class MatchBody(BaseModel):
    home: Team
    away: Team
    kickoff: date | None = None
    adjust: dict[str, float] | None = None
    save: bool = False


ADJUST_KEYS = {"home_advantage_multiplier": (0.5, 1.5), "home_attack_multiplier": (0.5, 1.5), "away_attack_multiplier": (0.5, 1.5), "home_defence_multiplier": (0.5, 1.5), "away_defence_multiplier": (0.5, 1.5),
               "home_missing_attack_loss": (0.0, 0.5), "away_missing_attack_loss": (0.0, 0.5), "home_missing_defence_loss": (0.0, 0.5), "away_missing_defence_loss": (0.0, 0.5),
               "home_rating_points": (-200.0, 200.0), "away_rating_points": (-200.0, 200.0), "home_advantage_points": (-100.0, 100.0)}


def _shape(fc: dict) -> dict:
    out = {}
    for name, f in fc.items():
        pr = f["probs"]
        out[name] = {"name": fi.MODEL_NAMES[name], "p_home": pr[0], "p_draw": pr[1], "p_away": pr[2], "p_over_2_5": f.get("p_over_2_5"), "p_btts": f.get("p_btts"),
                     "expected_goals": f.get("expected_goals"), "top_scorelines": f.get("top_scorelines"), "drivers": f.get("drivers"), "inputs": f["inputs"]}
    return out


def _persist_live(conn, p, snap: dict, fc: dict, settings: dict, data_sha: str, fixture_date: date, cutoff: date) -> dict:
    snap_row = conn.execute(
        """insert into football_feature_snapshots (workspace_id, fixture_date, home_team, away_team, cutoff, features, availability, warnings, sha256) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
           on conflict (workspace_id, home_team, away_team, fixture_date, cutoff, sha256) do update set sha256=excluded.sha256 returning id""",
        (p.workspace_id, fixture_date, snap["home"], snap["away"], cutoff, json.dumps(snap["features"], default=str), json.dumps(snap["availability"]), json.dumps(snap["warnings"]), snap["sha256"])).fetchone()
    ids = {}
    for name, f in fc.items():
        vid = _version(conn, p, name, {"model": name, "settings": _light(settings)}, data_sha)
        pr = f["probs"]
        row = conn.execute(
            """insert into football_predictions (workspace_id, kind, model_version_id, snapshot_id, season, fixture_date, home_team, away_team, cutoff, p_home, p_draw, p_away, p_over_2_5, p_btts,
               expected_home, expected_away, outputs, inputs) values (%s,'live',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               on conflict (workspace_id, model_version_id, fixture_date, home_team, away_team, cutoff) where kind = 'live' do update set outputs=excluded.outputs returning id""",
            (p.workspace_id, vid, snap_row["id"], fi.season_label(fixture_date), fixture_date, snap["home"], snap["away"], cutoff, pr[0], pr[1], pr[2], f.get("p_over_2_5"), f.get("p_btts"),
             (f.get("expected_goals") or [None, None])[0], (f.get("expected_goals") or [None, None])[1],
             json.dumps({"drivers": f.get("drivers"), "top_scorelines": f.get("top_scorelines")}), json.dumps(f["inputs"]))).fetchone()
        ids[name] = str(row["id"])
    return {"snapshot_id": str(snap_row["id"]), "prediction_ids": ids}


def _intelligence(conn, p, home: str, away: str, kickoff: date | None, adjust: dict | None, ms: list, run, stats: list[dict]) -> dict:
    today = _today()
    ko = kickoff or today
    cutoff = min(ko, today)           # what is known now, or what was known before a past kickoff
    known = {t for _, h, a, *_ in ms for t in (h, a)}
    for t in (home, away):
        if t not in known:
            raise HTTPException(422, f"'{t}' is not a club in the imported matches")
    if home == away:
        raise HTTPException(422, "Choose two different clubs")
    settings = _settings(run)
    snap = fi.build_snapshot(ms, home, away, cutoff, stats, ko)
    fc = fi.live_forecast(ms, home, away, cutoff, settings)
    data_sha = fb.data_sha([m for m in ms if m[0] < cutoff])
    out = {"home": home, "away": away, "kickoff": ko.isoformat(), "cutoff": cutoff.isoformat(), "generated_at": datetime.now(timezone.utc).isoformat(), "data_sha256": data_sha,
           "model_version": {"version": LIVE_VERSION, "settings_from_backtest": settings.get("run_id"), "tuned": settings["tuned"],
                             "note": "Settings tuned on a validation period of an earlier backtest." if settings["tuned"] else "Default settings: no backtest has been run, so nothing is tuned."},
           "snapshot": snap, "forecasts": _shape(fc), "reliability": fi.reliability(fc, snap, _calibration(run)), "warnings": snap["warnings"],
           "label": "Model forecast. Not a certainty, and not betting or financial advice."}
    if adjust:
        for k, v in adjust.items():
            lo, hi = ADJUST_KEYS.get(k, (None, None))
            if lo is None or not lo <= v <= hi:
                raise HTTPException(422, f"Adjustment '{k}' must be one of the supported settings and between {lo} and {hi}.")
        out["scenario"] = {"hypothetical": True, "adjustments": adjust, "forecasts": _shape(fi.live_forecast(ms, home, away, cutoff, settings, adjust)),
                           "note": "HYPOTHETICAL: what the models would say if these assumptions were true. This is not a forecast. Missing-player losses are percentages you chose, not estimates from data."}
    return out, fc, snap, settings, data_sha, ko, cutoff


@router.post("/match")
def match(body: MatchBody, p: Auth, conn=Depends(get_conn)):
    """Everything known about a fixture before kickoff, the forecasts of each model, how reliable the picture is, and optionally a what-if scenario."""
    ms = _history(conn, p)
    run = _latest_run(conn, p)
    out, fc, snap, settings, data_sha, ko, cutoff = _intelligence(conn, p, body.home, body.away, body.kickoff, body.adjust, ms, run, football_store.load_stats(conn, p.workspace_id))
    if body.save:
        if body.adjust:
            raise HTTPException(422, "A what-if scenario cannot be saved as a forecast.")
        require_write(p)
        out["saved"] = _persist_live(conn, p, snap, fc, settings, data_sha, ko, cutoff)
    return out


@router.get("/fixtures")
def upcoming(p: Auth, conn=Depends(get_conn), days: int = Query(14, ge=1, le=60), limit: int = Query(20, ge=1, le=30)):
    """Upcoming fixtures (from imported fixtures files) with each model's forecast. Forecasts are stored once per fixture and data state, then scored when results arrive."""
    today = _today()
    fx = conn.execute(
        """select f.fixture_date, f.home_team, f.away_team, f.season from football_fixtures f
           where f.workspace_id=%s and f.fixture_date between %s and %s
             and not exists (select 1 from match_history m where m.workspace_id=f.workspace_id and m.match_date=f.fixture_date and m.home_team=f.home_team and m.away_team=f.away_team)
           order by f.fixture_date, f.home_team limit %s""", (p.workspace_id, today, today + timedelta(days=days), limit)).fetchall()
    if not fx:
        total = conn.execute("select count(*) n from football_fixtures where workspace_id=%s", (p.workspace_id,)).fetchone()["n"]
        return {"fixtures": [], "note": "No upcoming fixtures in the next %d days." % days + ("" if total else " Import a fixtures file (future-dated rows in the same layout as results) on the Data page to see them here.")}
    ms = _history(conn, p)
    run = _latest_run(conn, p)
    stats = football_store.load_stats(conn, p.workspace_id)
    out = []
    for r in fx:
        try:
            item, fc, snap, settings, data_sha, ko, cutoff = _intelligence(conn, p, r["home_team"], r["away_team"], r["fixture_date"], None, ms, run, stats)
        except HTTPException as e:
            out.append({"date": r["fixture_date"], "home": r["home_team"], "away": r["away_team"], "error": e.detail})
            continue
        saved = _persist_live(conn, p, snap, fc, settings, data_sha, ko, cutoff) if p.role != "viewer" else None
        out.append({"date": r["fixture_date"], "home": r["home_team"], "away": r["away_team"], "forecasts": item["forecasts"], "warnings": item["warnings"], "reliability": item["reliability"],
                    "tracked": bool(saved)})
    return {"fixtures": out, "model_version": item["model_version"] if fx and "model_version" in item else None, "generated_at": datetime.now(timezone.utc).isoformat()}


@router.post("/reconcile")
def reconcile(p: Auth, conn=Depends(get_conn)):
    """Score stored live forecasts whose match results have now been imported."""
    require_write(p)
    return {"scored": football_store.reconcile(conn, p.workspace_id)}
