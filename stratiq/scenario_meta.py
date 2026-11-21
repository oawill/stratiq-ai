"""Provenance and version lineage for saved scenarios.

Political and financial scenarios are stored in strategic_scenarios (so the library, comments, the assistant and exports keep working). This
adds what SimLab records for its own runs: a provenance block (engine, version, seed, time, where the inputs came from) and a version chain
(scenario_key, version, parent_id), kept inside the scenario definition.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException


def lineage(conn, p, domain: str, kind: str, based_on: uuid.UUID | None) -> dict:
    """The version fields for a new scenario: version 1 with a new key, or the next version of `based_on` (same workspace, domain and kind)."""
    if not based_on:
        return {"scenario_key": str(uuid.uuid4()), "version": 1, "parent_id": None}
    row = conn.execute("select id, definition from strategic_scenarios where id=%s and workspace_id=%s and domain=%s", (based_on, p.workspace_id, domain)).fetchone()
    d = (row or {}).get("definition") or {}
    if not row or d.get("kind") != kind:
        raise HTTPException(404, "The scenario to build on was not found")
    return {"scenario_key": d.get("scenario_key") or str(row["id"]), "version": int(d.get("version", 1)) + 1, "parent_id": str(row["id"])}


def provenance(engine: str, version: str, seed: int | None, input_data: str) -> dict:
    return {"engine": engine, "engine_version": version, "deterministic": True, "random_seed": seed, "generated_at": datetime.now(timezone.utc).isoformat(), "input_data": input_data}
