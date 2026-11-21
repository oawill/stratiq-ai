"""Historical football results: import season files, check them, browse and export them, and hand them to the forecasting tools.

Everything is private to the workspace. VELQORIN does not fetch data from any provider: people import files they have the right to use.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StringConstraints, field_validator

from . import datasets as ds
from . import football_features as ff
from . import football_history as fh
from . import football_store
from . import plans
from .data_api import store_dataset
from .db import get_conn
from .security import ADMIN_ROLES, Auth, require_write

router = APIRouter(prefix="/api/v1/football", tags=["football"])

Competition = Literal["EPL"]
SeasonStr = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}/[0-9]{2}$")]


class Provenance(BaseModel):
    """Where a file came from. Supplied by the person importing and stored as given: the application does not fetch or verify it."""
    source_url: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    source_licence: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = None
    retrieved_on: date | None = None
    dataset_version: Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)] | None = None

    @field_validator("source_url", "source_licence", "dataset_version", mode="after")
    @classmethod
    def _blank_is_none(cls, v):
        return v or None

    @field_validator("source_url", mode="after")
    @classmethod
    def _web_address(cls, v):
        if v and not re.match(r"^https?://\S+$", v, re.I):
            raise ValueError("The source address must start with http:// or https:// and contain no spaces.")
        return v

    @field_validator("retrieved_on", mode="after")
    @classmethod
    def _not_future(cls, v):
        if v and v > datetime.now(timezone.utc).date():
            raise ValueError("The retrieval date cannot be in the future.")
        return v


class ImportBody(BaseModel):
    competition: Competition = "EPL"
    filename: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    csv: str = Field(max_length=ds.MAX_CHARS + 1000)
    combined: bool = False       # the file holds several seasons
    dry_run: bool = False        # check only; store nothing
    provenance: Provenance | None = None


def _stored(conn, wid, competition: str, seasons: list[str] | None = None) -> list[tuple]:
    rows = conn.execute(
        """select season, match_date, home_team, away_team, home_goals, away_goals from match_history
           where workspace_id=%s and competition=%s and (%s::text[] is null or season = any(%s))
           order by match_date, home_team, away_team""",
        (wid, competition, seasons, seasons),
    ).fetchall()
    return [(r["season"], r["match_date"], r["home_team"], r["away_team"], r["home_goals"], r["away_goals"]) for r in rows]


def _plain(rows: list[tuple]) -> list[tuple]:
    return [(d, h, a, hg, ag) for _, d, h, a, hg, ag in rows]


@router.post("/import")
def import_file(body: ImportBody, p: Auth, conn=Depends(get_conn)):
    """Validate a results file and (unless dry_run) store its valid matches. Safe to repeat: a stored fixture is never duplicated,
    and a stored fixture whose score differs is reported as a conflict instead of being overwritten."""
    if not body.dry_run:
        require_write(p)
    try:
        src = fh.read_source(body.csv, body.competition, body.combined)
    except ds.DataError as e:
        raise HTTPException(422, {"errors": e.errors})
    seasons = sorted({r.season for r in src.rows})
    existing = {(s, d, h, a): (hg, ag) for s, d, h, a, hg, ag in _stored(conn, p.workspace_id, body.competition, seasons)}
    new, unchanged, clash = [], 0, []
    for r in src.rows:
        got = existing.get(r.key)
        if got is None:
            new.append(r)
        elif got == (r.hg, r.ag):
            unchanged += 1
        else:
            clash.append({"season": r.season, "date": r.date.isoformat(), "home": r.home, "away": r.away, "found": [f"{got[0]}-{got[1]} (stored)", f"{r.hg}-{r.ag} (this file)"]})
    total_after = conn.execute("select count(*) n from match_history where workspace_id=%s and competition=%s", (p.workspace_id, body.competition)).fetchone()["n"] + len(new)
    if total_after > fh.MAX_ROWS_PER_COMPETITION:
        raise HTTPException(422, {"errors": [f"This would bring the stored matches to {total_after:,}; the limit is {fh.MAX_ROWS_PER_COMPETITION:,}."]})

    sha = hashlib.sha256(body.csv.encode()).hexdigest()
    if not body.dry_run and src.upcoming:
        source_id = football_store.record_source(conn, p, "fixtures", body.filename or "Fixtures", f"{body.filename or 'upload'} sha256:{sha[:12]}",
                                                 {"fixtures": len(src.upcoming), "first": src.upcoming[0][1].isoformat(), "last": src.upcoming[-1][1].isoformat()}, {"warnings": src.warnings})
        with conn.cursor() as cur:
            cur.executemany(
                """insert into football_fixtures (workspace_id, competition, season, fixture_date, home_team, away_team, source_id) values (%s,%s,%s,%s,%s,%s,%s)
                   on conflict (workspace_id, competition, fixture_date, home_team, away_team) do nothing""",
                [(p.workspace_id, body.competition, s_, d, h, a, source_id) for s_, d, h, a in src.upcoming])
    if not body.dry_run and new:
        ref = f"{body.filename or 'upload'} sha256:{sha[:12]}"
        with conn.cursor() as cur:
            cur.executemany(
                """insert into match_history (workspace_id, competition, season, match_date, home_team, away_team, home_goals, away_goals, source_provider, source_reference)
                   values (%s,%s,%s,%s,%s,%s,%s,%s,'user_upload',%s)
                   on conflict on constraint match_history_fixture do nothing""",
                [(p.workspace_id, body.competition, r.season, r.date, r.home, r.away, r.hg, r.ag, ref) for r in new],
            )
    if not body.dry_run and new:
        football_store.record_source(conn, p, "match_results", body.filename or "Match results", f"{body.filename or 'upload'} sha256:{sha[:12]}",
                                     {"matches": len(new), "seasons": seasons}, {"rejected": src.rejected_count, "conflicts": src.conflict_count + len(clash), "warnings": src.warnings},
                                     body.provenance.model_dump(mode="json") if body.provenance else None)
        football_store.refresh_teams(conn, p.workspace_id, body.competition)
    scored = football_store.reconcile(conn, p.workspace_id) if (not body.dry_run and new) else 0
    stored = _stored(conn, p.workspace_id, body.competition, seasons)
    if body.dry_run:   # what the stored data would look like after this import
        have = {(s, d, h, a) for s, d, h, a, *_ in stored}
        stored += [(r.season, r.date, r.home, r.away, r.hg, r.ag) for r in new if r.key not in have]
    by_season = {s: [m for m in stored if m[0] == s] for s in seasons}
    reports = [fh.season_report(_plain(by_season[s]), s, body.competition) for s in seasons]
    conflicts = src.conflicts + clash
    needs_review = bool(src.rejected_count or src.conflict_count or clash or any(r["status"] == "incomplete" for r in reports))
    report = {
        "filename": body.filename, "file_sha256": sha, "dry_run": body.dry_run,
        "rows_read": src.rows_read, "valid": len(src.rows), "new": len(new), "unchanged": unchanged,
        "rejected": src.rejected_count, "rejected_rows": src.rejected, "duplicates": src.duplicate_count, "duplicate_rows": src.duplicates,
        "conflicts": src.conflict_count + len(clash), "conflict_rows": conflicts[:fh.MAX_STORED_ISSUES], "unplayed_skipped": src.unplayed,
        "unknown_clubs": src.unknown_clubs, "warnings": src.warnings, "seasons": [{**r, "first_date": r["first_date"].isoformat(), "last_date": r["last_date"].isoformat()} for r in reports],
        "missing": sum(r["missing_count"] for r in reports), "upcoming_fixtures": len(src.upcoming), "forecasts_scored": scored,
        "provenance": body.provenance.model_dump(mode="json") if body.provenance else None,
    }
    if not body.dry_run:
        status = "needs_review" if needs_review else "ok"
        row = conn.execute(
            "insert into match_imports (workspace_id, competition, filename, file_sha256, status, report, created_by) values (%s,%s,%s,%s,%s,%s,%s) returning id, created_at",
            (p.workspace_id, body.competition, body.filename, sha, status, json.dumps(report), p.user_id),
        ).fetchone()
        report.update({"id": row["id"], "created_at": row["created_at"], "status": status})
        label = ", ".join(seasons[:3]) + ("…" if len(seasons) > 3 else "")
        conn.execute(
            "insert into activity_history (workspace_id,user_id,kind,summary,ref_type,ref_id) values (%s,%s,'football.imported',%s,'match_import',%s)",
            (p.workspace_id, p.user_id, f"Imported {len(new)} Premier League matches ({label})", str(row["id"])),
        )
        conn.execute(
            "insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'football.import',%s)",
            (p.workspace_id, p.user_id, json.dumps({"import_id": str(row["id"]), "file_sha256": sha, "new": len(new), "rejected": src.rejected_count, "conflicts": report["conflicts"], "provenance": report["provenance"]})),
        )
    return report


@router.get("/summary")
def summary(p: Auth, conn=Depends(get_conn), competition: Competition = "EPL"):
    out = fh.overview(_stored(conn, p.workspace_id, competition), competition)
    last = conn.execute(
        "select created_at, status, filename from match_imports where workspace_id=%s and competition=%s order by created_at desc limit 1", (p.workspace_id, competition)
    ).fetchone()
    out["last_import"] = last
    out["limits"] = {"max_rows": fh.MAX_ROWS_PER_COMPETITION}
    return out


@router.get("/matches")
def matches(p: Auth, conn=Depends(get_conn), competition: Competition = "EPL", season: SeasonStr | None = None,
            team: Annotated[str, StringConstraints(max_length=60)] | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    where = "workspace_id=%s and competition=%s and (%s::text is null or season=%s) and (%s::text is null or home_team=%s or away_team=%s)"
    args = (p.workspace_id, competition, season, season, team, team, team)
    total = conn.execute(f"select count(*) n from match_history where {where}", args).fetchone()["n"]
    rows = conn.execute(
        f"select season, match_date, home_team, away_team, home_goals, away_goals from match_history where {where} order by match_date desc, home_team limit %s offset %s",
        (*args, limit, offset),
    ).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "matches": rows}


@router.get("/export")
def export(p: Auth, conn=Depends(get_conn), competition: Competition = "EPL", season: SeasonStr | None = None):
    """The five-column CSV (date, home_team, away_team, home_goals, away_goals), oldest first."""
    rows = _plain(_stored(conn, p.workspace_id, competition, [season] if season else None))
    if not rows:
        raise HTTPException(404, "There are no matches to export yet.")
    text = fh.export_csv(rows)
    tag = season.replace("/", "-") if season else "all-seasons"
    return {"filename": f"velqorin_epl_{tag}.csv", "rows": len(rows), "bytes": len(text.encode()), "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "columns": ["date", "home_team", "away_team", "home_goals", "away_goals"], "csv": text}


@router.get("/report")
def report(p: Auth, conn=Depends(get_conn), competition: Competition = "EPL"):
    """Where each season stands now, plus the validation report of the latest imports (accepted, rejected, duplicate, missing)."""
    imports = conn.execute(
        """select i.id, i.created_at, i.filename, i.status, i.report, u.name created_by_name from match_imports i left join users u on u.id=i.created_by
           where i.workspace_id=%s and i.competition=%s order by i.created_at desc limit 15""",
        (p.workspace_id, competition),
    ).fetchall()
    return {"overview": fh.overview(_stored(conn, p.workspace_id, competition), competition), "imports": imports}


@router.delete("/seasons", status_code=204)
def delete_season(season: SeasonStr, p: Auth, conn=Depends(get_conn), competition: Competition = "EPL"):
    """Remove one season so a corrected file can be imported in its place."""
    if p.role not in ADMIN_ROLES:
        raise HTTPException(403, "Only an admin or the owner can remove a season")
    n = conn.execute("delete from match_history where workspace_id=%s and competition=%s and season=%s", (p.workspace_id, competition, season)).rowcount
    if not n:
        raise HTTPException(404, "That season has no stored matches")
    conn.execute("insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'football.season_deleted',%s)",
                 (p.workspace_id, p.user_id, json.dumps({"competition": competition, "season": season, "matches": n})))


class DatasetBody(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    competition: Competition = "EPL"
    seasons: list[SeasonStr] | None = None   # None = everything stored


@router.post("/dataset", status_code=201)
def to_dataset(body: DatasetBody, p: Auth, conn=Depends(get_conn)):
    """Turn the stored matches into a regular sports dataset, so Sports forecasts and backtests can use them."""
    require_write(p)
    plans.check_quota(conn, p.workspace_id, "datasets")
    rows = _plain(_stored(conn, p.workspace_id, body.competition, body.seasons))
    if not rows:
        raise HTTPException(404, "There are no matches to use yet.")
    try:
        parsed = ds.parse_sports(fh.export_csv(rows))
    except ds.DataError as e:
        raise HTTPException(422, {"errors": e.errors})
    return store_dataset(conn, p, "sports_results", body.name, f"Premier League results imported into this workspace ({len(rows)} matches).", parsed, source="Created from imported match history")


# ------------------------------------------------------------------ prediction-engine features (earlier matches only)
def _history(conn, p, competition: str) -> list[ff.M]:
    rows = _plain(_stored(conn, p.workspace_id, competition))
    if not rows:
        raise HTTPException(404, "Import some match history first.")
    return rows


def _before(before: date | None) -> date:
    today = datetime.now(timezone.utc).date()
    if before is None:
        return today
    if before > today:
        raise HTTPException(422, "The date cannot be in the future.")
    return before


@router.get("/team")
def team_profile(team: Annotated[str, StringConstraints(min_length=1, max_length=60)], p: Auth, conn=Depends(get_conn), competition: Competition = "EPL", before: date | None = None):
    rows = _history(conn, p, competition)
    if team not in {x for _, h, a, *_ in rows for x in (h, a)}:
        raise HTTPException(422, f"'{team}' is not a club in the stored matches")
    return ff.team_profile(rows, team, _before(before))


@router.get("/fixture")
def fixture(home: Annotated[str, StringConstraints(min_length=1, max_length=60)], away: Annotated[str, StringConstraints(min_length=1, max_length=60)], p: Auth,
            conn=Depends(get_conn), competition: Competition = "EPL", before: date | None = None):
    rows = _history(conn, p, competition)
    known = {x for _, h, a, *_ in rows for x in (h, a)}
    if home == away or home not in known or away not in known:
        raise HTTPException(422, "Choose two different clubs from the stored matches")
    if len(_prior := [m for m in rows if m[0] < _before(before)]) < 30:
        raise HTTPException(422, "Fewer than 30 matches came before that date, which is too few to fit ratings.")
    return ff.fixture_view(rows, home, away, _before(before))


@router.post("/evaluation")
def evaluation(p: Auth, conn=Depends(get_conn), competition: Competition = "EPL"):
    """Accuracy, log loss, Brier score and calibration of the Poisson model on a later validation period and test period."""
    rows = _history(conn, p, competition)
    res = ff.chronological_evaluation(rows, f"{competition} match history")
    if not res["ok"]:
        raise HTTPException(422, res["reason"])
    return res
