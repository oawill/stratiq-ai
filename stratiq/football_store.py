"""Database helpers shared by the football APIs: data-source records, the club registry, uploaded statistics, and scoring forecasts once results exist."""
from __future__ import annotations

import json
import math
from datetime import date, datetime, time, timedelta, timezone


def record_source(conn, p, kind: str, name: str, reference: str | None, coverage: dict, quality: dict) -> str:
    row = conn.execute(
        """insert into football_data_sources (workspace_id, kind, name, provider, reference, coverage, quality, created_by)
           values (%s,%s,%s,'user_upload',%s,%s,%s,%s) returning id""",
        (p.workspace_id, kind, name, reference, json.dumps(coverage), json.dumps(quality), p.user_id),
    ).fetchone()
    return str(row["id"])


def refresh_teams(conn, workspace_id: str, competition: str) -> None:
    """Rebuild the club registry from the stored matches (name, first and last season, matches played)."""
    conn.execute(
        """insert into football_teams (workspace_id, competition, name, first_season, last_season, matches, updated_at)
           select %s, %s, team, min(season), max(season), count(*), now() from (
             select home_team team, season from match_history where workspace_id=%s and competition=%s
             union all select away_team, season from match_history where workspace_id=%s and competition=%s) t group by team
           on conflict (workspace_id, competition, name) do update set first_season=excluded.first_season, last_season=excluded.last_season, matches=excluded.matches, updated_at=now()""",
        (workspace_id, competition, workspace_id, competition, workspace_id, competition),
    )


def store_stats(conn, p, dataset_id, rows: list[dict]) -> None:
    """Copy validated advanced statistics into the queryable table. Post-match statistics become usable the day after the match."""
    cols = ("home_xg", "away_xg", "home_shots", "away_shots", "home_shots_on_target", "away_shots_on_target", "home_corners", "away_corners", "odds_home", "odds_draw", "odds_away")
    with conn.cursor() as cur:
        cur.executemany(
            f"""insert into football_team_statistics (workspace_id, dataset_id, match_date, home_team, away_team, {', '.join(cols)}, available_at)
                values (%s,%s,%s,%s,%s,{', '.join(['%s'] * len(cols))},%s) on conflict do nothing""",
            [(p.workspace_id, dataset_id, r["date"], r["home"], r["away"], *[r.get(c) for c in cols],
              datetime.combine(date.fromisoformat(r["date"]) + timedelta(days=1), time.min, tzinfo=timezone.utc)) for r in rows],
        )


def load_stats(conn, workspace_id: str) -> list[dict]:
    rows = conn.execute(
        """select match_date, home_team, away_team, home_xg, away_xg, odds_home, odds_draw, odds_away from football_team_statistics
           where workspace_id=%s order by match_date""", (workspace_id,)).fetchall()
    return [{"date": r["match_date"], "home": r["home_team"], "away": r["away_team"], "home_xg": r["home_xg"], "away_xg": r["away_xg"],
             "odds_home": r["odds_home"], "odds_draw": r["odds_draw"], "odds_away": r["odds_away"]} for r in rows]


def reconcile(conn, workspace_id: str) -> int:
    """Score every live forecast whose match now has a stored result. Returns how many were scored; scoring twice is harmless."""
    rows = conn.execute(
        """select p.id, p.p_home, p.p_draw, p.p_away, m.home_goals, m.away_goals
           from football_predictions p join match_history m
             on m.workspace_id=p.workspace_id and m.match_date=p.fixture_date and m.home_team=p.home_team and m.away_team=p.away_team
           left join football_prediction_outcomes o on o.prediction_id=p.id
           where p.workspace_id=%s and p.kind='live' and o.prediction_id is null""", (workspace_id,)).fetchall()
    batch = []
    for r in rows:
        probs = [r["p_home"], r["p_draw"], r["p_away"]]
        y = 0 if r["home_goals"] > r["away_goals"] else 1 if r["home_goals"] == r["away_goals"] else 2
        batch.append((r["id"], r["home_goals"], r["away_goals"], y, -math.log(max(probs[y], 1e-12)), sum((probs[k] - (1.0 if k == y else 0.0)) ** 2 for k in range(3)),
                      max(range(3), key=lambda k: probs[k]) == y))
    if batch:
        with conn.cursor() as cur:
            cur.executemany("insert into football_prediction_outcomes (prediction_id, home_goals, away_goals, outcome, log_loss, brier, correct) values (%s,%s,%s,%s,%s,%s,%s) on conflict do nothing", batch)
    return len(batch)
