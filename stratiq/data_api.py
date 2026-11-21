"""User-supplied datasets: validate, store privately per workspace, and use them in the Sports, Markets, Politics and SimLab modules."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StringConstraints

from . import datasets as ds
from . import model as sports_model
from . import plans
from .db import get_conn
from .security import ADMIN_ROLES, Auth, require_write

router = APIRouter(prefix="/api/v1/data", tags=["data"])

Kind = Literal["sports_results", "market_returns", "political_seats", "series"]
DsName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class UploadBody(BaseModel):
    kind: Kind
    csv: str = Field(max_length=ds.MAX_CHARS + 1000)
    options: dict[str, Any] = Field(default_factory=dict)


class CreateBody(UploadBody):
    name: DsName
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


def _parse(body: UploadBody) -> ds.Parsed:
    return ds.parse(body.kind, body.csv, body.options)


@router.post("/preview")
def preview(body: UploadBody, p: Auth):
    """Validate a file without saving it. Problems come back as a list of line-numbered messages, not as an HTTP error."""
    try:
        parsed = _parse(body)
    except ds.DataError as e:
        return {"ok": False, "errors": e.errors}
    return {"ok": True, "row_count": parsed.row_count, "summary": parsed.summary, "warnings": parsed.warnings, "sha256": parsed.sha256}


@router.post("/datasets", status_code=201)
def create_dataset(body: CreateBody, p: Auth, conn=Depends(get_conn)):
    require_write(p)
    plans.check_quota(conn, p.workspace_id, "datasets")
    try:
        parsed = _parse(body)
    except ds.DataError as e:
        raise HTTPException(422, {"errors": e.errors})
    row = conn.execute(
        """insert into datasets (workspace_id, kind, name, description, row_count, summary, data, sha256, created_by)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id, created_at""",
        (p.workspace_id, body.kind, body.name, body.description or None, parsed.row_count, json.dumps(parsed.summary), json.dumps(parsed.data), parsed.sha256, p.user_id),
    ).fetchone()
    conn.execute(
        "insert into activity_history (workspace_id,user_id,kind,summary,ref_type,ref_id) values (%s,%s,'dataset.created',%s,'dataset',%s)",
        (p.workspace_id, p.user_id, f"Uploaded dataset: {body.name}", str(row["id"])),
    )
    conn.execute(
        "insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'dataset.create',%s)",
        (p.workspace_id, p.user_id, json.dumps({"dataset_id": str(row["id"]), "kind": body.kind, "rows": parsed.row_count, "sha256": parsed.sha256})),
    )
    return {"id": row["id"], "created_at": row["created_at"], "kind": body.kind, "name": body.name, "row_count": parsed.row_count,
            "summary": parsed.summary, "warnings": parsed.warnings, "sha256": parsed.sha256}


@router.get("/datasets")
def list_datasets(p: Auth, conn=Depends(get_conn), kind: Kind | None = None):
    rows = conn.execute(
        """select d.id, d.kind, d.name, d.description, d.row_count, d.summary, d.sha256, d.created_at, u.name created_by_name
           from datasets d left join users u on u.id=d.created_by
           where d.workspace_id=%s and (%s::text is null or d.kind=%s) order by d.created_at desc""",
        (p.workspace_id, kind, kind),
    ).fetchall()
    return {"datasets": rows}


def _get(conn, p, dataset_id: uuid.UUID, kind: str | None = None) -> dict:
    row = conn.execute("select * from datasets where id=%s and workspace_id=%s", (dataset_id, p.workspace_id)).fetchone()
    if not row:
        raise HTTPException(404, "Dataset not found")
    if kind and row["kind"] != kind:
        raise HTTPException(422, f"This dataset is {row['kind'].replace('_', ' ')}, not {kind.replace('_', ' ')}")
    return row


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    r = _get(conn, p, dataset_id)
    return {k: r[k] for k in ("id", "kind", "name", "description", "row_count", "summary", "sha256", "created_at")}


@router.get("/datasets/{dataset_id}/data")
def get_data(dataset_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    """The validated, normalized content (not the original file)."""
    r = _get(conn, p, dataset_id)
    return {"id": r["id"], "kind": r["kind"], "name": r["name"], "sha256": r["sha256"], "data": r["data"]}


@router.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    r = _get(conn, p, dataset_id)
    if str(r["created_by"]) != p.user_id and p.role not in ADMIN_ROLES:
        raise HTTPException(403, "Only the uploader, an admin or the owner can delete a dataset")
    if p.role == "viewer":
        raise HTTPException(403, "Your role is read-only")
    conn.execute("delete from datasets where id=%s and workspace_id=%s", (dataset_id, p.workspace_id))
    conn.execute(
        "insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'dataset.delete',%s)",
        (p.workspace_id, p.user_id, json.dumps({"dataset_id": str(dataset_id), "name": r["name"], "sha256": r["sha256"]})),
    )


# ------------------------------------------------------------------ Markets: hand a returns dataset to the historical tool
@router.get("/datasets/{dataset_id}/returns-csv")
def returns_csv(dataset_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    r = _get(conn, p, dataset_id, "market_returns")
    d = r["data"]
    names = d["names"]
    lines = [",".join(names)] + [",".join(repr(d["returns"][n][i]) for n in names) for i in range(r["row_count"])]
    return {"csv": "\n".join(lines), "unit": "decimal", "periods_per_year": d["periods_per_year"], "names": names}


# ------------------------------------------------------------------ SimLab: fit a distribution to one column
class FitBody(BaseModel):
    column: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    distribution: Literal["auto", "normal", "lognormal", "triangular"] = "auto"


@router.post("/datasets/{dataset_id}/fit")
def fit(dataset_id: uuid.UUID, body: FitBody, p: Auth, conn=Depends(get_conn)):
    r = _get(conn, p, dataset_id)
    if r["kind"] not in ("series", "market_returns"):
        raise HTTPException(422, "Only numeric series and return datasets can be fitted")
    cols = r["data"]["columns"] if r["kind"] == "series" else r["data"]["returns"]
    if body.column not in cols:
        raise HTTPException(404, f"Column '{body.column}' not found. Columns: {', '.join(cols)}")
    try:
        out = ds.fit_distribution(cols[body.column], body.distribution)
    except ds.DataError as e:
        raise HTTPException(422, "; ".join(e.errors))
    return {**out, "dataset": {"id": r["id"], "name": r["name"], "sha256": r["sha256"]}, "column": body.column}


# ------------------------------------------------------------------ Sports: forecast from uploaded results
class ForecastBody(BaseModel):
    home: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    away: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    save: bool = False


@router.post("/datasets/{dataset_id}/forecast", status_code=200)
def forecast(dataset_id: uuid.UUID, body: ForecastBody, p: Auth, conn=Depends(get_conn)):
    """Fit team ratings on the uploaded matches and forecast one fixture. Unsaved by default; `save` stores an immutable prediction."""
    r = _get(conn, p, dataset_id, "sports_results")
    counts = r["summary"]["team_matches"]
    for t in (body.home, body.away):
        if t not in counts:
            raise HTTPException(422, f"'{t}' is not a team in this dataset")
    if body.home == body.away:
        raise HTTPException(422, "Choose two different teams")
    now = datetime.now(timezone.utc)
    hist = ds.hist_matches(r["data"]["matches"])
    try:
        res = sports_model.predict(hist, sorted(counts), body.home, body.away, now, r["name"])
    except ValueError as e:
        raise HTTPException(422, str(e))
    inputs = {**res["inputs"], "home_name": body.home, "away_name": body.away, "dataset_id": str(r["id"]), "dataset_sha256": r["sha256"],
              "data_source": "user_upload", "retrospective": False}
    out = {"id": None, "created_at": None, "feature_cutoff": now,
           "model": {"name": sports_model.MODEL_NAME, "version": sports_model.MODEL_VERSION}, "inputs": inputs, "outputs": res["outputs"], "assumptions": res["assumptions"]}
    if not body.save:
        return out
    require_write(p)
    plans.check_quota(conn, p.workspace_id, "predictions")
    mv = conn.execute("select id from model_versions where name=%s and version=%s", (sports_model.MODEL_NAME, sports_model.MODEL_VERSION)).fetchone()
    if not mv:
        raise HTTPException(503, "Model version is not registered")
    row = conn.execute(
        """insert into predictions (workspace_id,user_id,domain,model_version_id,subject_type,subject_id,feature_cutoff,inputs,outputs,assumptions,input_hash,created_at)
           values (%s,%s,'sports',%s,'sports_dataset',%s,%s,%s,%s,%s,%s,%s) returning id, created_at""",
        (p.workspace_id, p.user_id, mv["id"], f"{r['id']}:{body.home}|{body.away}", now, json.dumps(inputs), json.dumps(res["outputs"]),
         json.dumps(res["assumptions"]), sports_model.input_hash(inputs), now),
    ).fetchone()
    conn.execute(
        "insert into activity_history (workspace_id,user_id,kind,summary,ref_type,ref_id) values (%s,%s,'prediction.created',%s,'prediction',%s)",
        (p.workspace_id, p.user_id, f"Sports forecast: {body.home} vs {body.away} (your data)", str(row["id"])),
    )
    conn.execute(
        "insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,'prediction.create',%s)",
        (p.workspace_id, p.user_id, json.dumps({"prediction_id": str(row["id"]), "dataset_id": str(r["id"]), "model": f"{sports_model.MODEL_NAME}@{sports_model.MODEL_VERSION}"})),
    )
    return {**out, "id": row["id"], "created_at": row["created_at"]}
