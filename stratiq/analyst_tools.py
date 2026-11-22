"""Read-only, authenticated tools the AI Analyst can call.

Design rules (each is tested):
  * Every tool has a typed argument model (pydantic). Arguments are validated before anything runs; unknown tools and bad arguments return a
    structured error, never an exception that could leak internals, and never reach the database.
  * No tool writes anything, runs a simulation, fetches an external URL, or accepts SQL. Every query is a fixed statement parameterised with the
    caller's workspace id (and, for conversations, user id), so a person can only retrieve what their own workspace holds.
  * Every result carries what the answer must show: the data itself, citations (source, retrieval time, observation window, model version),
    assumptions and limitations, plus optional display blocks (tables, bars, proposals). A tool that cannot find data says so (`available: false`
    with a reason) instead of returning something plausible.
  * Text that came from a person (club names, scenario titles, notes, file names) is returned as DATA and cleaned of control characters and
    length-capped, so it cannot masquerade as instructions.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Annotated, Any, Callable

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from . import football_features as ff
from . import football_intel as fi
from . import football_intel_api as fia
from .football_api import _plain, _stored
from .football_teams import canonical

SRC_RESULTS = "Premier League results you imported (Data, Historical Football Data)"
MAX_TEXT = 200
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(v: Any, limit: int = MAX_TEXT) -> Any:
    """Data from a person, made safe to show a model: control characters removed and length capped. It is still just data."""
    if isinstance(v, str):
        return _CTRL.sub("", v)[:limit]
    return v


def clean_deep(v: Any) -> Any:
    if isinstance(v, dict):
        return {str(clean(k, 80)): clean_deep(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean_deep(x) for x in v]
    return clean(v)


class ToolError(Exception):
    pass


@dataclass
class Ctx:
    conn: Any
    p: Any
    today: date

    def history(self) -> list:
        return sorted(_plain(_stored(self.conn, self.p.workspace_id, fia.COMPETITION)), key=lambda m: (m[0], m[1], m[2]))

    def teams(self, ms: list | None = None) -> set[str]:
        return {t for _, h, a, *_ in (ms if ms is not None else self.history()) for t in (h, a)}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def result(data: dict | None = None, *, citations: list[dict] | None = None, assumptions: list[str] | None = None, limitations: list[str] | None = None,
           blocks: list[dict] | None = None, available: bool = True, reason: str | None = None) -> dict:
    return {"ok": True, "available": available, "reason": reason, "data": data or {}, "citations": citations or [], "assumptions": assumptions or [], "limitations": limitations or [], "blocks": blocks or []}


def unavailable(reason: str, citations: list[dict] | None = None) -> dict:
    return result(available=False, reason=reason, citations=citations)


def cite(kind: str, label: str, source: str, *, window: str | None = None, model_version: str | None = None, ref: dict | None = None, href: str | None = None) -> dict:
    return {"kind": kind, "label": label, "source": source, "retrieved_at": now_iso(), "window": window, "model_version": model_version, "ref": ref, "href": href}


def window_of(ms: list) -> str:
    return f"{ms[0][0].isoformat()} to {ms[-1][0].isoformat()} ({len(ms):,} matches)" if ms else "no matches"


def resolve_team(ctx: Ctx, ms: list, name: str) -> str:
    canon, _ = canonical(name)
    teams = ctx.teams(ms)
    if canon in teams:
        return canon
    low = {t.lower(): t for t in teams}
    if canon.lower() in low:
        return low[canon.lower()]
    raise ToolError(f"'{clean(name, 60)}' is not a club in the imported matches.")


# ------------------------------------------------------------------ argument models
class Args(BaseModel):
    """Base for every tool's arguments: unknown fields are rejected, so nothing can be smuggled in alongside the declared ones."""
    model_config = ConfigDict(extra="forbid")


class TeamArgs(Args):
    team: Name
    before: date | None = None


class CompareTeamsArgs(Args):
    team_a: Name
    team_b: Name


class FixtureArgs(Args):
    home: Name
    away: Name
    fixture_date: date | None = None


class SavedPredictionsArgs(Args):
    team: Name | None = None
    limit: int = Field(5, ge=1, le=10)


class NoArgs(Args):
    pass


class SimArgs(Args):
    id: uuid.UUID | None = None
    domain: Annotated[str, StringConstraints(pattern="^(sports|business|politics|markets)$")] | None = None
    limit: int = Field(5, ge=1, le=10)


class CompareSimArgs(Args):
    ids: list[uuid.UUID] = Field(min_length=2, max_length=4)


# ------------------------------------------------------------------ team statistics
def _profile_block(p: dict) -> list[dict]:
    rows = [["Played", p["played"]], ["Won / drawn / lost", f"{p.get('wins', 0)} / {p.get('draws', 0)} / {p.get('losses', 0)}"], ["Points per match", p.get("points_per_match")],
            ["Goals for / against per match", f"{p.get('goals_for_per_match')} / {p.get('goals_against_per_match')}"], ["Clean sheets", p.get("clean_sheet_rate")],
            ["Home record (W/D/L)", f"{p['home']['wins']}/{p['home']['draws']}/{p['home']['losses']} in {p['home']['played']}"],
            ["Away record (W/D/L)", f"{p['away']['wins']}/{p['away']['draws']}/{p['away']['losses']} in {p['away']['played']}"], ["Form, last 5", p["form_last_5"]["results"]], ["Elo rating", p["elo"]]]
    return [{"type": "table", "title": f"{p['team']}: record from your imported matches", "columns": ["Measure", "Value"], "rows": rows}]


def team_statistics(ctx: Ctx, a: TeamArgs) -> dict:
    ms = ctx.history()
    if not ms:
        return unavailable("No match history is imported, so there are no team statistics.")
    team = resolve_team(ctx, ms, a.team)
    before = a.before or ctx.today
    prof = ff.team_profile(ms, team, before)
    if not prof["played"]:
        return unavailable(f"{team} has no matches before {before.isoformat()} in the imported history.")
    prior = [m for m in ms if m[0] < before]
    c = cite("team_statistics", f"{team} statistics", SRC_RESULTS, window=window_of(prior), ref={"team": team, "before": before.isoformat()}, href="/dashboard/sports")
    return result({"team": team, "as_of": before.isoformat(), "profile": prof}, citations=[c],
                  assumptions=["Descriptive statistics: averages over every imported league match before the as-of date."],
                  limitations=[prof["sample_note"], (prof.get("coverage") or {}).get("note", "League matches only."), "Descriptive history says nothing by itself about the next match."], blocks=_profile_block(prof))


def compare_teams(ctx: Ctx, a: CompareTeamsArgs) -> dict:
    ms = ctx.history()
    if not ms:
        return unavailable("No match history is imported, so teams cannot be compared.")
    ta, tb = resolve_team(ctx, ms, a.team_a), resolve_team(ctx, ms, a.team_b)
    if ta == tb:
        raise ToolError("Choose two different clubs to compare.")
    pa, pb = ff.team_profile(ms, ta, ctx.today), ff.team_profile(ms, tb, ctx.today)
    h2h = ff.head_to_head(ms, ta, tb, ctx.today)
    c = cite("team_comparison", f"{ta} compared with {tb}", SRC_RESULTS, window=window_of(ms), ref={"teams": [ta, tb]}, href="/dashboard/sports")
    rows = [[lab, fa, fb] for lab, fa, fb in (("Played", pa["played"], pb["played"]), ("Points per match", pa.get("points_per_match"), pb.get("points_per_match")),
                                              ("Goals for per match", pa.get("goals_for_per_match"), pb.get("goals_for_per_match")), ("Goals against per match", pa.get("goals_against_per_match"), pb.get("goals_against_per_match")),
                                              ("Form, last 5", pa["form_last_5"]["results"], pb["form_last_5"]["results"]), ("Elo rating", pa["elo"], pb["elo"]))]
    return result({"team_a": pa, "team_b": pb, "head_to_head": h2h, "elo_difference": round(pa["elo"] - pb["elo"], 1)}, citations=[c], assumptions=["Descriptive statistics from the same imported matches for both clubs."],
                  limitations=["Clubs may have different numbers of matches in the data: compare the Played row before reading differences.", "Head-to-head counts are small samples."],
                  blocks=[{"type": "table", "title": f"{ta} v {tb}", "columns": ["Measure", ta, tb], "rows": rows}])


# ------------------------------------------------------------------ fixture details and the model's forecast
def fixture_details(ctx: Ctx, a: FixtureArgs) -> dict:
    ms = ctx.history()
    if not ms:
        return unavailable("No match history is imported, so no forecast can be made.")
    home, away = resolve_team(ctx, ms, a.home), resolve_team(ctx, ms, a.away)
    if home == away:
        raise ToolError("Choose two different clubs.")
    kick = a.fixture_date
    scheduled = None
    if kick:
        scheduled = ctx.conn.execute("select fixture_date from football_fixtures where status not in ('cancelled','postponed','suspended') and workspace_id=%s and fixture_date=%s and home_team=%s and away_team=%s", (ctx.p.workspace_id, kick, home, away)).fetchone()
        if not scheduled:
            return unavailable(f"No imported fixture has {home} at home to {away} on {kick.isoformat()}.")
    else:
        row = ctx.conn.execute("select fixture_date from football_fixtures where status not in ('cancelled','postponed','suspended') and workspace_id=%s and home_team=%s and away_team=%s and fixture_date >= %s order by fixture_date limit 1",
                               (ctx.p.workspace_id, home, away, ctx.today)).fetchone()
        scheduled, kick = row, (row["fixture_date"] if row else None)
    cutoff = min(kick, ctx.today) if kick else ctx.today
    run = fia._latest_run(ctx.conn, ctx.p)
    settings = fia._settings(run)
    stats = []
    snap = fi.build_snapshot(ms, home, away, cutoff, stats, kick or ctx.today)
    fc = fi.live_forecast(ms, home, away, cutoff, settings)
    prior = [m for m in ms if m[0] < cutoff]
    primary = fc["dixon_coles"]
    pr = primary["probs"]
    avail = snap["availability"]
    got = [k for k, v in avail.items() if v["status"] == "available"]
    names = {x["key"]: x["name"] for x in fi.FACTORS}
    version = f"live {fia.LIVE_VERSION}" + (f", settings from backtest {settings['run_id'][:8]}" if settings.get("tuned") else ", default settings (no backtest has been run)")
    c = cite("model_forecast", f"Model forecast: {home} v {away}", SRC_RESULTS, window=f"matches before {cutoff.isoformat()} ({len(prior):,} matches)", model_version=version,
             ref={"home": home, "away": away, "fixture_date": kick.isoformat() if kick else None}, href="/dashboard/sports")
    data = {"home": home, "away": away, "scheduled": bool(scheduled), "fixture_date": kick.isoformat() if kick else None, "cutoff": cutoff.isoformat(), "matches_used": len(prior),
            "settings_tuned": bool(settings.get("tuned")),
            "model": "Dixon-Coles", "p_home": pr[0], "p_draw": pr[1], "p_away": pr[2], "expected_goals_home": primary["expected_goals"][0], "expected_goals_away": primary["expected_goals"][1],
            "p_over_2_5": primary["p_over_2_5"], "p_btts": primary["p_btts"], "top_scorelines": [{"home": t["home"], "away": t["away"], "p": t["p"]} for t in primary["top_scorelines"][:5]],
            "other_models": {k: {"p_home": v["probs"][0], "p_draw": v["probs"][1], "p_away": v["probs"][2]} for k, v in fc.items() if k != "dixon_coles"},
            "drivers": [clean_deep(d) for d in primary["drivers"]], "inputs": {k: v for k, v in primary["inputs"].items() if isinstance(v, (int, float))},
            "elo_difference": snap["features"].get("elo_difference"), "form": {"home": snap["features"].get("home_form_5"), "away": snap["features"].get("away_form_5")},
            "factors_used": [names.get(k, k) for k in got], "factors_unavailable": [names.get(k, k) for k, v in avail.items() if v["status"] == "unavailable"]}
    lim = ["A probability is the model's estimate, not a prediction of what will happen and not a measure of the model's accuracy.", *snap["warnings"][:4]]
    blocks = [{"type": "bars", "title": f"{home} v {away}: model probabilities", "unit": "%", "items": [{"label": f"{home} win", "value": pr[0]}, {"label": "Draw", "value": pr[1]}, {"label": f"{away} win", "value": pr[2]}]},
              {"type": "table", "title": "Likeliest scorelines", "columns": ["Score", "Probability"], "rows": [[f"{t['home']}–{t['away']}", t["p"]] for t in primary["top_scorelines"][:5]]}]
    return result(data, citations=[c], assumptions=[f"Goals are modelled as Poisson with a low-score correction, using results before {cutoff.isoformat()} only.",
                                                    "Only factors in the imported data are used: " + ", ".join(names.get(k, k) for k in got) + "."] + ([] if scheduled else [f"No imported fixture pairs these clubs, so {home} is treated as the home side: a hypothetical matchup, not a scheduled match."]),
                  limitations=lim, blocks=blocks)


# ------------------------------------------------------------------ saved predictions
def saved_predictions(ctx: Ctx, a: SavedPredictionsArgs) -> dict:
    team = None
    if a.team:
        team = resolve_team(ctx, ctx.history(), a.team)
    keys = ctx.conn.execute(
        """select fixture_date, home_team, away_team, max(created_at) latest from football_predictions where workspace_id=%s and kind='live' and (%s::text is null or home_team=%s or away_team=%s)
           group by fixture_date, home_team, away_team order by fixture_date desc, latest desc limit %s""", (ctx.p.workspace_id, team, team, team, a.limit)).fetchall()
    if not keys:
        return unavailable("No forecast has been saved" + (f" for {team}" if team else "") + " yet.")
    out = []
    for k in keys:
        rows = ctx.conn.execute(
            """select pr.created_at, pr.cutoff, pr.p_home, pr.p_draw, pr.p_away, v.name model, v.version, o.home_goals, o.away_goals, o.outcome, o.log_loss, o.correct
               from football_predictions pr join football_model_versions v on v.id=pr.model_version_id left join football_prediction_outcomes o on o.prediction_id=pr.id
               where pr.workspace_id=%s and pr.kind='live' and pr.fixture_date=%s and pr.home_team=%s and pr.away_team=%s order by v.name""",
            (ctx.p.workspace_id, k["fixture_date"], k["home_team"], k["away_team"])).fetchall()
        scored = [r for r in rows if r["outcome"] is not None]
        out.append({"date": k["fixture_date"].isoformat(), "home": k["home_team"], "away": k["away_team"], "status": "scored" if scored else "waiting", "result": f"{scored[0]['home_goals']}-{scored[0]['away_goals']}" if scored else None,
                    "forecasts": [{"model": fi.MODEL_NAMES.get(r["model"], r["model"]), "version": r["version"], "made_at": r["created_at"].isoformat(), "training_cutoff": r["cutoff"].isoformat(),
                                   "p_home": r["p_home"], "p_draw": r["p_draw"], "p_away": r["p_away"], "correct": r["correct"], "log_loss": r["log_loss"]} for r in rows]})
    c = cite("saved_predictions", "Forecasts you saved before the match", "Saved live forecasts in this workspace", window=f"{out[-1]['date']} to {out[0]['date']}", ref={"team": team}, href="/dashboard/sports")
    rows_tbl = [[f"{o['home']} v {o['away']}", o["date"], o["status"], o["result"] or "waiting"] for o in out]
    return result({"fixtures": out}, citations=[c], assumptions=["Each forecast was stored before its match using only matches before its training cutoff."],
                  limitations=["Saved forecasts are a small sample: one scored match says little about a model. Judge a model on its backtest."], blocks=[{"type": "table", "title": "Saved predictions", "columns": ["Fixture", "Date", "Status", "Result"], "rows": rows_tbl}])


# ------------------------------------------------------------------ model evaluation
def model_evaluation(ctx: Ctx, a: NoArgs) -> dict:
    from .reports_api import _metrics
    run = fia._latest_run(ctx.conn, ctx.p)
    if not run:
        return unavailable("No chronological backtest has been run on this history, so there are no historical accuracy figures to report.")
    cfg = run["config"] or {}
    current = ctx.history()
    from . import football_backtest as fb
    changed = bool(current) and fb.data_sha(current) != run["data_sha256"]
    test = _metrics((run["results"] or {}).get("test"))
    c = cite("model_evaluation", "Chronological backtest", "Backtest run in this workspace", window=f"test period {', '.join((cfg.get('split') or {}).get('test', []))}; {run['matches']:,} matches in the run",
             model_version=f"football models {cfg.get('model_version')}", ref={"backtest_run": str(run["id"])}, href="/dashboard/sports")
    rows = [[m["model"], m["matches"], round(m["log_loss"], 3), round(m["brier"], 3), None if m["accuracy"] is None else round(m["accuracy"], 3),
             None if m["gain_vs_frequency"] is None else round(m["gain_vs_frequency"], 3)] for m in test]
    return result({"run_id": str(run["id"]), "run_date": run["created_at"].isoformat(), "split": cfg.get("split"), "test_models": test, "history_changed_since": changed,
                   "warnings": run["warnings"] or []}, citations=[c],
                  assumptions=["Walk-forward backtest: every forecast used only matches played before that fixture; settings were chosen on a validation period, never on the test period."],
                  limitations=["A backtest measures how a model would have done on past matches; it does not promise future accuracy.", *(["The imported history has changed since this backtest, so re-run it before relying on it."] if changed else []),
                               *[w for w in (run["warnings"] or [])[:2]]],
                  blocks=[{"type": "table", "title": "Test-period results (never used to choose settings)", "columns": ["Model", "Matches", "Log loss", "Brier", "Right result", "Log-loss gain vs frequency baseline"], "rows": rows}])


# ------------------------------------------------------------------ SimLab scenarios
def _sim_listing(ctx: Ctx, domain: str | None, limit: int) -> list[dict]:
    out = []
    for r in ctx.conn.execute("select id, domain, title, version, created_at, model_name, model_version from simlab_runs where workspace_id=%s and (%s::text is null or domain=%s) order by created_at desc limit %s",
                              (ctx.p.workspace_id, domain, domain, limit)).fetchall():
        out.append({"id": str(r["id"]), "source": "run", "domain": r["domain"], "title": clean(r["title"]), "version": r["version"], "saved_at": r["created_at"].isoformat(), "engine": f"{r['model_name']}@{r['model_version']}"})
    dom_map = {"politics": "politics", "markets": "finance", "business": "business"}
    wanted = [v for k, v in dom_map.items() if domain in (None, k)]
    if wanted:
        for r in ctx.conn.execute("select id, domain, title, created_at, definition from strategic_scenarios where workspace_id=%s and domain = any(%s) order by created_at desc limit %s", (ctx.p.workspace_id, wanted, limit)).fetchall():
            d = r["definition"] or {}
            out.append({"id": str(r["id"]), "source": "scenario", "domain": {"finance": "markets"}.get(r["domain"], r["domain"]), "title": clean(r["title"]), "version": int(d.get("version", 1)), "saved_at": r["created_at"].isoformat(), "kind": d.get("kind") or "payoff game"})
    out.sort(key=lambda x: x["saved_at"], reverse=True)
    return out[:limit]


def _run_view(r: dict) -> dict:
    o = r["outputs"]
    base = {"id": str(r["id"]), "source": "run", "domain": r["domain"], "title": clean(r["title"]), "version": r["version"], "saved_at": r["created_at"].isoformat(), "engine": f"{r['model_name']}@{r['model_version']}",
            "provenance": clean_deep(r["provenance"]), "hypothetical": True}
    if r["domain"] == "sports":
        base.update({"matchup": clean_deep(o["matchup"]), "baseline": {"percent": o["baseline"]["percent"], "expected_goals": o["baseline"]["expected_goals"]},
                     "scenarios": [{"name": clean(s["name"], 60), "percent": s["percent"], "expected_goals": s["expected_goals"], "changed": s["changed"], "adjustments": {k: s["adjustments"][k] for k in s["changed"]},
                                    "delta_points": {k: s["delta_vs_baseline"][k] for k in ("p_home", "p_draw", "p_away")}} for s in o["scenarios"]],
                     "validation_status": o["validation_status"], "calibrated_note": "Baseline is calibrated from imported results; scenario adjustments are the user's assumptions and are not validated."})
    elif r["domain"] == "business":
        base.update({"inputs": o["inputs"], "base": {k: o["base"][k] for k in ("price", "units", "revenue", "gross_profit", "gross_margin")}, "effective_elasticity": o["effective_elasticity"],
                     "scenarios": [{"name": clean(s["name"], 60), "overrides": s["overrides"], "units": s["units"], "revenue": s["revenue"], "gross_profit": s["gross_profit"], "change_vs_base": s["change_vs_base"]} for s in o["scenarios"]],
                     "sensitivity_top": [{"input": x["label"], "gross_profit_change_minus10": (x["low"] or {}).get("gross_profit_change"), "gross_profit_change_plus10": (x["high"] or {}).get("gross_profit_change")} for x in o["sensitivity"][:3]],
                     "validation_status": o["validation_status"]})
    return base


def _scenario_view(r: dict) -> dict:
    d = r["definition"] or {}
    return {"id": str(r["id"]), "source": "scenario", "domain": {"finance": "markets"}.get(r["domain"], r["domain"]), "title": clean(r["title"]), "version": int(d.get("version", 1)), "saved_at": r["created_at"].isoformat(),
            "kind": d.get("kind") or "payoff game", "summary": clean_deep(d.get("summary")), "provenance": clean_deep(d.get("provenance")), "hypothetical": True,
            "notice": {"politics": "Scenario arithmetic on entered assumptions. Not a poll, not a validated election forecast.", "finance": "Educational scenario analysis. Not investment advice, not a forecast, and not connected to any broker.",
                       "business": "A game built from payoffs the user entered."}.get(r["domain"], "")}


def _load_sim(ctx: Ctx, sid: uuid.UUID) -> dict | None:
    r = ctx.conn.execute("select * from simlab_runs where id=%s and workspace_id=%s", (sid, ctx.p.workspace_id)).fetchone()
    if r:
        return _run_view(r)
    s = ctx.conn.execute("select * from strategic_scenarios where id=%s and workspace_id=%s and domain in ('politics','finance','business')", (sid, ctx.p.workspace_id)).fetchone()
    return _scenario_view(s) if s else None


def simlab_scenarios(ctx: Ctx, a: SimArgs) -> dict:
    if a.id:
        v = _load_sim(ctx, a.id)
        if not v:
            return unavailable("That saved scenario was not found in this workspace.")
        c = cite("simlab_scenario", v["title"], "Saved SimLab run" if v["source"] == "run" else "Saved scenario in this workspace", window=f"saved {v['saved_at'][:10]}", model_version=v.get("engine"),
                 ref={"id": v["id"], "source": v["source"]}, href="/dashboard/simulations")
        return result({"scenario": v}, citations=[c], assumptions=["Hypothetical: every scenario states what a model would output if the user's assumptions were true."],
                      limitations=[v.get("validation_status") or v.get("notice") or "Not a forecast.", "Scenario adjustments are user assumptions and have not been validated by a backtest."])
    items = _sim_listing(ctx, a.domain, a.limit)
    if not items:
        return unavailable("No saved SimLab scenarios" + (f" for {a.domain}" if a.domain else "") + " were found in this workspace.")
    c = cite("simlab_list", "Saved SimLab scenarios", "Saved runs and scenarios in this workspace", window=f"{items[-1]['saved_at'][:10]} to {items[0]['saved_at'][:10]}", href="/dashboard/simulations")
    return result({"scenarios": items}, citations=[c], limitations=["Scenarios are hypothetical, not forecasts."],
                  blocks=[{"type": "table", "title": "Saved scenarios", "columns": ["Title", "Domain", "Version", "Saved"], "rows": [[i["title"], i["domain"], i["version"], i["saved_at"][:10]] for i in items]}])


def compare_simulations(ctx: Ctx, a: CompareSimArgs) -> dict:
    ids = list(dict.fromkeys(a.ids))
    if len(ids) < 2:
        raise ToolError("Choose at least two different saved scenarios.")
    views = []
    for i in ids:
        v = _load_sim(ctx, i)
        if not v:
            return unavailable("One of those saved scenarios was not found in this workspace.")
        views.append(v)
    if len({v["domain"] for v in views}) != 1:
        raise ToolError("Compare scenarios of the same domain.")
    dom = views[0]["domain"]
    cites = [cite("simlab_scenario", v["title"], "Saved SimLab run" if v["source"] == "run" else "Saved scenario in this workspace", window=f"saved {v['saved_at'][:10]}", model_version=v.get("engine"),
                  ref={"id": v["id"]}, href="/dashboard/simulations") for v in views]
    diffs, rows, blocks = [], [], []
    if dom == "sports":
        for v in views:
            for s in [{"name": "Baseline", "percent": v["baseline"]["percent"], "expected_goals": v["baseline"]["expected_goals"], "adjustments": {}}] + v["scenarios"]:
                rows.append([f"{v['title']} v{v['version']}", s["name"], *s["percent"], round(s["expected_goals"][0], 2), round(s["expected_goals"][1], 2), "; ".join(f"{k}={x:g}" for k, x in s["adjustments"].items()) or "none"])
        keys = sorted({k for v in views for s in v["scenarios"] for k in s["adjustments"]})
        for k in keys:
            diffs.append({"parameter": k, "values": [{"run": f"{v['title']} v{v['version']}", "scenario": s["name"], "value": s["adjustments"].get(k)} for v in views for s in v["scenarios"] if k in s["adjustments"]]})
        blocks = [{"type": "table", "title": "Baseline and scenarios side by side (percent)", "columns": ["Run", "Scenario", "Home %", "Draw %", "Away %", "xG home", "xG away", "Assumptions changed"], "rows": rows}]
        notes = ["Baselines can differ between runs because the club pairing, cutoff or data differ: check each run's provenance."]
    elif dom == "business":
        for v in views:
            for s in [{"name": "Base case", **v["base"], "overrides": {}}] + v["scenarios"]:
                rows.append([f"{v['title']} v{v['version']}", s["name"], round(s["units"], 1), round(s["revenue"], 0), round(s["gross_profit"], 0), "; ".join(f"{k}={x:g}" for k, x in s.get("overrides", {}).items()) or "none"])
        keys = sorted({k for v in views for k in v["inputs"] if len({vv["inputs"][k] for vv in views}) > 1})
        diffs = [{"parameter": k, "values": [{"run": f"{v['title']} v{v['version']}", "value": v["inputs"][k]} for v in views]} for k in keys]
        blocks = [{"type": "table", "title": "Base cases and scenarios", "columns": ["Run", "Scenario", "Units", "Revenue", "Gross profit", "Assumptions changed"], "rows": rows}]
        notes = ["Every input is a hypothetical assumption."]
    else:
        notes = ["Only the stored summaries are compared here; open each scenario in its own workspace for the full analysis."]
        blocks = [{"type": "table", "title": "Saved scenarios", "columns": ["Title", "Type", "Version"], "rows": [[v["title"], v["kind"], v["version"]] for v in views]}]
    return result({"domain": dom, "scenarios": views, "parameter_differences": diffs}, citations=cites, assumptions=["Hypothetical scenarios compared as saved: nothing was re-run."], limitations=notes, blocks=blocks)


# ------------------------------------------------------------------ source freshness
def source_freshness(ctx: Ctx, a: NoArgs) -> dict:
    wid = ctx.p.workspace_id
    ms = _stored(ctx.conn, wid, fia.COMPETITION)
    up = ctx.conn.execute("select count(*) n from football_fixtures where status not in ('cancelled','postponed','suspended') and workspace_id=%s and fixture_date >= %s", (wid, ctx.today)).fetchone()["n"]
    last = ctx.conn.execute("select max(created_at) t from match_imports where workspace_id=%s", (wid,)).fetchone()["t"]
    fr = fia.freshness_of(ms, up, last.isoformat() if last else None, ctx.today)
    srcs = [clean_deep({"name": r["name"], "kind": r["kind"], "provider": r["provider"], "source_url": r["source_url"], "licence_as_stated": r["source_licence"], "retrieved_on": r["retrieved_on"].isoformat() if r["retrieved_on"] else None,
                        "dataset_version": r["dataset_version"], "imported_at": r["created_at"].isoformat()})
            for r in ctx.conn.execute("select name, kind, provider, source_url, source_licence, retrieved_on, dataset_version, created_at from football_data_sources where workspace_id=%s order by created_at desc limit 6", (wid,)).fetchall()]
    run = fia._latest_run(ctx.conn, ctx.p)
    c = cite("source_freshness", "Data sources and freshness", "Imports recorded in this workspace", window=f"as of {ctx.today.isoformat()}", href="/dashboard/data")
    data = {"freshness": fr, "sources": srcs, "latest_backtest_at": run["created_at"].isoformat() if run else None,
            "live_feeds": "None. No live provider is connected: results, fixtures and statistics exist only if you imported them."}
    return result(data, citations=[c], assumptions=["Freshness is judged from the newest stored result date."], limitations=["Source details are as typed by the person who imported the files; they are not verified."],
                  blocks=[{"type": "table", "title": "Imported sources", "columns": ["Source", "Kind", "Retrieved", "Licence as stated"], "rows": [[s["name"], s["kind"], s["retrieved_on"] or "not recorded", s["licence_as_stated"] or "not recorded"] for s in srcs]}] if srcs else [])


# ------------------------------------------------------------------ domain adapters and what is not supported
DOMAIN_SUPPORT = {
    "sports": {"supported": ["Premier League results you import", "model forecasts (Elo, Poisson, Dixon-Coles, boosted trees, ensemble)", "backtests", "saved predictions", "SimLab what-if scenarios"],
               "unsupported": ["live scores and fixtures feeds", "injuries and team news", "bookmaker odds unless you upload them", "leagues other than the Premier League"]},
    "business": {"supported": ["saved payoff games and pricing scenarios (hypothetical inputs)"], "unsupported": ["market data", "competitor intelligence feeds"]},
    "politics": {"supported": ["saved nonpartisan scenarios built from numbers you entered"], "unsupported": ["live polling or election results", "official results unless you import them with a source"]},
    "markets": {"supported": ["saved portfolio, stress and historical-risk scenarios built from numbers you entered"], "unsupported": ["live or delayed prices", "news", "investment recommendations"]},
}


def domain_capabilities(ctx: Ctx, a: NoArgs) -> dict:
    c = cite("capabilities", "What the Analyst can and cannot use", "VELQORIN configuration", window=f"as of {ctx.today.isoformat()}")
    return result({"domains": DOMAIN_SUPPORT}, citations=[c], limitations=["Anything listed as unsupported is not available to the Analyst and will be reported as such."])


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    fn: Callable[[Ctx, Any], dict]


TOOLS: dict[str, Tool] = {t.name: t for t in (
    Tool("team_statistics", "Descriptive statistics for one Premier League club from the user's imported matches: record, goals, home/away split, form, clean sheets, Elo rating.", TeamArgs, team_statistics),
    Tool("compare_teams", "Compare two clubs from the imported matches, with head-to-head.", CompareTeamsArgs, compare_teams),
    Tool("fixture_details", "The model's forecast for a fixture (or a hypothetical pairing): probabilities, expected goals, likeliest scorelines, drivers, model version, data cutoff and which factors were or were not available.", FixtureArgs, fixture_details),
    Tool("saved_predictions", "Forecasts the user saved before matches, with results once known.", SavedPredictionsArgs, saved_predictions),
    Tool("model_evaluation", "Historical backtest results of the football models on the test period, with sample sizes and limitations.", NoArgs, model_evaluation),
    Tool("simlab_scenarios", "List saved SimLab runs and scenarios, or open one by id.", SimArgs, simlab_scenarios),
    Tool("compare_simulations", "Compare 2 to 4 saved scenarios of the same domain: baselines, scenarios and parameter differences.", CompareSimArgs, compare_simulations),
    Tool("source_freshness", "How fresh the imported data is, where it came from, and whether any live feed exists.", NoArgs, source_freshness),
    Tool("domain_capabilities", "What the Analyst can and cannot use in each domain.", NoArgs, domain_capabilities),
)}


def run_tool(ctx: Ctx, name: str, raw_args: dict | None) -> dict:
    """Validate and run one tool. Never raises: failures come back as {"ok": false, "error": ...}."""
    tool = TOOLS.get(name if isinstance(name, str) else "")
    if tool is None:
        return {"ok": False, "tool": str(name)[:60], "error": "Unknown tool. Only the registered read-only tools can be used."}
    try:
        args = tool.args.model_validate(raw_args or {})
    except ValidationError as e:
        return {"ok": False, "tool": name, "error": "Invalid arguments: " + "; ".join(f"{'.'.join(map(str, x['loc'])) or 'arguments'}: {x['msg']}" for x in e.errors()[:4])}
    try:
        out = tool.fn(ctx, args)
    except ToolError as e:
        return {"ok": False, "tool": name, "error": str(e)}
    out["tool"] = name
    out["args"] = args.model_dump(mode="json")
    return out


def tool_specs() -> list[dict]:
    """Descriptions and JSON schemas of the tools, for a language model's tool-calling interface."""
    return [{"name": t.name, "description": t.description, "input_schema": t.args.model_json_schema()} for t in TOOLS.values()]
