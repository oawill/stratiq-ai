"""Loads a stored item (workspace-scoped) and turns it into explainable Facts."""
from __future__ import annotations

import uuid

from fastapi import HTTPException

from . import explain as ex
from . import finance_api, gametheory as gt, politics_api
from .security import Principal

ItemType = ("prediction", "simulation", "scenario")


def _model_text(conn, name: str) -> tuple[list[str], list[str]]:
    row = conn.execute("select assumptions, limitations from model_versions where name=%s order by created_at desc limit 1", (name,)).fetchone()
    return (row["assumptions"], row["limitations"]) if row else ([], [])


def load_facts(conn, p: Principal, item_type: str, item_id: uuid.UUID) -> tuple[ex.Facts, dict]:
    """Returns (facts, meta). Missing and other-workspace items are indistinguishable (404)."""
    if item_type == "prediction":
        row = conn.execute(
            """select p.id, p.created_at, p.feature_cutoff, p.inputs, p.outputs, p.assumptions, mv.name, mv.version, mv.limitations
               from predictions p join model_versions mv on mv.id=p.model_version_id where p.id=%s and p.workspace_id=%s""",
            (item_id, p.workspace_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Item not found")
        i = row["inputs"]
        title = f"Forecast: {i.get('home_name', i['home_team'])} vs {i.get('away_name', i['away_team'])}"
        f = ex.facts_prediction(title, i, row["outputs"], row["assumptions"], row["limitations"], f"{row['name']}@{row['version']}", row["created_at"].isoformat(), row["feature_cutoff"].isoformat())
        return f, {"module": "sports", "kind": "prediction", "title": title}

    if item_type == "simulation":
        row = conn.execute("select id, title, domain, status, config, result from simulation_runs where id=%s and workspace_id=%s", (item_id, p.workspace_id)).fetchone()
        if not row:
            raise HTTPException(404, "Item not found")
        if row["status"] != "completed" or not row["result"]:
            raise HTTPException(409, "Only completed simulation runs can be explained")
        asm, lim = _model_text(conn, "monte-carlo")
        return ex.facts_simulation(row["title"], row["domain"], row["config"], row["result"], lim, asm), {"module": "simulation", "kind": "simulation", "title": row["title"]}

    if item_type == "scenario":
        row = conn.execute("select id, title, domain, definition from strategic_scenarios where id=%s and workspace_id=%s", (item_id, p.workspace_id)).fetchone()
        if not row:
            raise HTTPException(404, "Item not found")
        d, domain, title = row["definition"], row["domain"], row["title"]
        if domain == "business":
            m = conn.execute("select matrix from payoff_matrices where scenario_id=%s", (item_id,)).fetchone()
            a = gt.analyse(gt.build_game(d["row_strategies"], d["col_strategies"], m["matrix"]))
            asm, lim = _model_text(conn, "nash-solver")
            return ex.facts_business(title, d, a, lim, asm), {"module": "business", "kind": "business", "title": title}
        if domain == "politics":
            kind = d["kind"]
            a = politics_api.analyse(kind, politics_api._parse(kind, d["inputs"]))
            asm, lim = _model_text(conn, "political-scenario-tools")
            build = {"coalition": ex.facts_coalition, "turnout": ex.facts_turnout, "policy": ex.facts_policy}[kind]
            return build(title, d["inputs"], a, lim, asm), {"module": "politics", "kind": kind, "title": title}
        if domain == "finance":
            kind = d["kind"]
            a = finance_api.analyse(kind, finance_api._parse(kind, d["inputs"]))
            asm, lim = _model_text(conn, "financial-risk-tools")
            build = {"montecarlo": ex.facts_fin_mc, "stress": ex.facts_fin_stress, "historical": ex.facts_fin_hist}[kind]
            return build(title, d["inputs"], a, lim, asm), {"module": "finance", "kind": kind, "title": title}
    raise HTTPException(404, "Item not found")
