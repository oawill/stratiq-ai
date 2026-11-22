"""Live forecast performance: what the official pre-kickoff forecasts scored once results arrived, plus the daily and weekly reports (Phase 4F).

Only official, not-voided evaluations count, one per match. With few matches the numbers say little, and every summary says so. The comparison
point is a forecast of one third each ("no information"): beating it is the minimum to claim a model adds anything.
"""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone

from . import football_results as res

BINS = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0001)


def _agg(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    mean = lambda k: round(sum(r[k] for r in rows) / n, 4)  # noqa: E731
    out = {"n": n, "log_loss": mean("log_loss"), "brier": mean("brier"), "rps": mean("rps"), "accuracy": round(sum(1 for r in rows if r["correct"]) / n, 4), "mean_probability_given_to_outcome": mean("p_actual")}
    base_rps = sum(res.metrics([1 / 3] * 3, r["outcome"])["rps"] for r in rows) / n           # the ranked probability score of "one third each" depends on which results happened
    out["vs_no_information"] = {"log_loss": round(res.UNIFORM["log_loss"] - out["log_loss"], 4), "brier": round(res.UNIFORM["brier"] - out["brier"], 4), "rps": round(base_rps - out["rps"], 4)}   # positive = better than one third each
    out["beats_no_information"] = out["log_loss"] < res.UNIFORM["log_loss"]
    out["enough_matches_to_judge"] = n >= res.MIN_FOR_VERDICT
    return out


def summary(conn, wid: str, since: datetime | None = None, until: datetime | None = None, model: str | None = None) -> dict:
    where, args = ["e.workspace_id=%s", "e.voided_at is null"], [wid]
    if since:
        where.append("e.evaluated_at >= %s")
        args.append(since)
    if until:
        where.append("e.evaluated_at < %s")
        args.append(until)
    if model:
        where.append("e.model_name=%s")
        args.append(model)
    rows = conn.execute(f"""select e.fixture_id, e.model_name, e.log_loss, e.brier, e.rps, e.correct, e.p_actual, e.correction_count, e.outcome, v.p_home, f.home_team, f.away_team, f.fixture_date
                            from football_prediction_evaluations e join football_prediction_versions v on v.id=e.version_id join football_fixtures f on f.id=e.fixture_id
                            where {' and '.join(where)}""", args).fetchall()
    models = sorted({r["model_name"] for r in rows})
    by_model = {m: _agg([r for r in rows if r["model_name"] == m]) for m in models}
    cal = []
    for lo, hi in zip(BINS, BINS[1:]):
        b = [r for r in rows if lo <= r["p_home"] < hi]
        cal.append({"low": lo, "high": min(hi, 1.0), "n": len(b), "mean_forecast": round(sum(r["p_home"] for r in b) / len(b), 4) if b else None, "home_win_rate": round(sum(1 for r in b if r["outcome"] == 0) / len(b), 4) if b else None})
    ranked = sorted(rows, key=lambda r: r["log_loss"])
    pick = lambda r: {"fixture_id": str(r["fixture_id"]), "match": f"{r['home_team']} v {r['away_team']}", "date": str(r["fixture_date"]), "log_loss": round(r["log_loss"], 3)}  # noqa: E731
    voided = conn.execute("select count(*) n from football_prediction_evaluations where workspace_id=%s and voided_at is not null", (wid,)).fetchone()["n"]
    conflicts = conn.execute("select count(*) n from football_fixtures where workspace_id=%s and result_note like 'The provider''s score differs%%'", (wid,)).fetchone()["n"]
    return {"overall": _agg(rows), "by_model": by_model, "home_win_calibration": cal, "best": [pick(r) for r in ranked[:3]], "worst": [pick(r) for r in ranked[-3:][::-1]] if len(ranked) > 3 else [],
            "corrections": sum(r["correction_count"] for r in rows), "voided_matches": voided, "result_conflicts": conflicts,
            "baseline": {"description": "A forecast of one third for each outcome, which carries no information. Its ranked probability score depends on which results happened, so it is compared per match.", "log_loss": round(res.UNIFORM["log_loss"], 4), "brier": round(res.UNIFORM["brier"], 4)},
            "note": f"Fewer than {res.MIN_FOR_VERDICT} scored matches say very little about a model: a few results can make a good model look bad or a poor one look good. The performance laboratory scores thousands of past matches." if len(rows) < res.MIN_FOR_VERDICT else
                    "Scores are for official pre-kickoff forecasts only, one per match."}


def _window(period: str, now: datetime) -> tuple[datetime, datetime]:
    today = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    if period == "daily":
        return today - timedelta(days=1), today
    monday = today - timedelta(days=today.weekday())
    return monday - timedelta(days=7), monday


def make_reports(conn, wid: str, now: datetime | None = None) -> dict:
    """Create the daily summary for the last full UTC day and the weekly report for the last full Monday-to-Sunday week, if they have something to report and do not exist."""
    now = now or datetime.now(timezone.utc)
    made = []
    for period in ("daily", "weekly"):
        start, end = _window(period, now)
        if conn.execute("select 1 from football_performance_reports where workspace_id=%s and period=%s and window_end=%s", (wid, period, end)).fetchone():
            continue
        s = summary(conn, wid, start, end)
        if not s["overall"]["n"]:
            continue                                                          # nothing was scored in that period: no empty report
        s["cumulative"] = _agg_all(conn, wid)
        conn.execute("insert into football_performance_reports (workspace_id, period, window_start, window_end, summary) values (%s,%s,%s,%s,%s) on conflict do nothing",
                     (wid, period, start, end, json.dumps(s, default=str)))
        made.append(period)
    return {"created": made}


def _agg_all(conn, wid: str) -> dict:
    return summary(conn, wid)["overall"]
