"""Seed the FICTIONAL development dataset, register the model, and run a real backtest.

    python -m stratiq.seed [--reset] [--seed 42]
"""
from __future__ import annotations

import argparse
import json

import psycopg
from psycopg.rows import dict_row

from . import backtest, dataset
from .db import database_url, load_dotenv_local
from .model import ASSUMPTIONS, LIMITATIONS, MODEL_DESCRIPTION, MODEL_NAME, MODEL_VERSION, HistMatch


def ensure_model_version(conn) -> str:
    row = conn.execute(
        """insert into model_versions (domain, name, version, description, status, assumptions, limitations)
           values ('sports', %s, %s, %s, 'experimental', %s, %s)
           on conflict (name, version) do update set description = excluded.description
           returning id""",
        (MODEL_NAME, MODEL_VERSION, MODEL_DESCRIPTION, json.dumps(ASSUMPTIONS), json.dumps(LIMITATIONS)),
    ).fetchone()
    return str(row["id"])


SOLVER = {
    "name": "nash-solver",
    "version": "0.1.0",
    "description": "Deterministic exact solver for two-player normal-form games: best responses, pure Nash equilibria, dominance, iterated elimination, 2x2 mixed equilibrium, Pareto analysis and exact payoff sensitivity. Payoffs are user assumptions.",
    "assumptions": [
        "Two players choose simultaneously from a finite set of pure strategies.",
        "Payoffs are supplied by the user and treated as exact decimals.",
        "Players are rational, know the payoff matrix, and maximise their own payoff.",
    ],
    "limitations": [
        "Solves only what the entered payoffs imply; it does not estimate payoffs or forecast real competitor behaviour.",
        "Mixed equilibria are computed only for 2x2 games.",
        "Only pure-strategy dominance is analysed.",
    ],
}


def ensure_solver_version(conn) -> str:
    row = conn.execute(
        """insert into model_versions (domain, name, version, description, status, assumptions, limitations)
           values ('business', %s, %s, %s, 'active', %s, %s)
           on conflict (name, version) do update set description = excluded.description
           returning id""",
        (SOLVER["name"], SOLVER["version"], SOLVER["description"], json.dumps(SOLVER["assumptions"]), json.dumps(SOLVER["limitations"])),
    ).fetchone()
    return str(row["id"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    load_dotenv_local()

    with psycopg.connect(database_url(), row_factory=dict_row, prepare_threshold=None) as conn:
        mv_id = ensure_model_version(conn)
        ensure_solver_version(conn)
        if args.reset:
            conn.execute("delete from sports_matches")
            conn.execute("delete from sports_teams")
            conn.execute("delete from sports_leagues")
            conn.execute("delete from evaluation_metrics where model_version_id = %s", (mv_id,))
        for league_id, meta in dataset.LEAGUES.items():
            if conn.execute("select 1 from sports_leagues where id=%s", (league_id,)).fetchone():
                print("exists", league_id)
                continue
            _, matches = dataset.generate(league_id, args.seed)
            conn.execute(
                "insert into sports_leagues (id,name,country,data_source,is_fictional) values (%s,%s,%s,%s,true)",
                (league_id, meta["name"], meta["country"], dataset.DATA_SOURCE),
            )
            for t in meta["teams"]:
                conn.execute(
                    "insert into sports_teams (id,league_id,name) values (%s,%s,%s)",
                    (dataset.team_id(league_id, t), league_id, t),
                )
            for m in matches:
                conn.execute(
                    """insert into sports_matches
                       (league_id,home_team_id,away_team_id,kickoff,home_goals,away_goals,status,data_source)
                       values (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        league_id,
                        dataset.team_id(league_id, m["home"]),
                        dataset.team_id(league_id, m["away"]),
                        m["kickoff"], m["home_goals"], m["away_goals"], m["status"], dataset.DATA_SOURCE,
                    ),
                )
            print("seeded", league_id, len(matches), "matches")

        # Real backtest on the fictional data (pooled across leagues, each league fit separately).
        conn.execute("delete from evaluation_metrics where model_version_id=%s", (mv_id,))
        agg = {"n": 0, "b": 0.0, "l": 0.0, "bb": 0.0, "bl": 0.0}
        for league_id in dataset.LEAGUES:
            teams = [r["id"] for r in conn.execute("select id from sports_teams where league_id=%s", (league_id,))]
            hist = [
                HistMatch(r["home_team_id"], r["away_team_id"], r["home_goals"], r["away_goals"], r["kickoff"])
                for r in conn.execute(
                    "select * from sports_matches where league_id=%s and status='finished'", (league_id,)
                )
            ]
            res = backtest.run(hist, teams, dataset.DATA_SOURCE)
            n = res["sample_size"]
            if n:
                agg["n"] += n
                agg["b"] += res["brier"] * n
                agg["l"] += res["log_loss"] * n
                agg["bb"] += res["baseline_brier"] * n
                agg["bl"] += res["baseline_log_loss"] * n
        if agg["n"]:
            for metric, key in [("brier", "b"), ("log_loss", "l"), ("baseline_brier", "bb"), ("baseline_log_loss", "bl")]:
                conn.execute(
                    "insert into evaluation_metrics (model_version_id,metric,value,sample_size,dataset) values (%s,%s,%s,%s,%s)",
                    (mv_id, metric, agg[key] / agg["n"], agg["n"], f"{dataset.DATA_SOURCE} (seed {args.seed})"),
                )
            print("backtest n=%d brier=%.4f baseline=%.4f" % (agg["n"], agg["b"] / agg["n"], agg["bb"] / agg["n"]))


if __name__ == "__main__":
    main()
