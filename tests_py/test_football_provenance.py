"""Source provenance on football imports: where a file came from, its licence as stated, when it was retrieved, and its dataset version.
All data is SYNTHETIC (real club names, random scores)."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from .conftest import hdr, make_user
from .test_football import five_csv
from .test_football_intel import FIVE, post

ROWS = [m for m in FIVE if m[0].year == 2023 or (m[0].year == 2024 and m[0].month < 8)][:380]
GOOD = {"source_url": "https://example.org/data/E0.csv", "source_licence": "Private, non-commercial use", "retrieved_on": "2026-01-05", "dataset_version": "2025-26 week 20"}


@pytest.fixture()
def ws(client, conn):
    uid, wid = make_user(conn)
    return hdr(uid, wid, exp_in=900), wid


def do_import(client, h, provenance=None, **kw):
    body = {"filename": "E0.csv", "combined": True, "csv": five_csv(ROWS), **kw}
    if provenance is not None:
        body["provenance"] = provenance
    return post(client, h, "import", body)


def test_provenance_is_stored_with_the_source_the_report_and_the_audit_log(client, conn, ws):
    h, wid = ws
    r = do_import(client, h, GOOD)
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["provenance"] == {**GOOD}
    src = conn.execute("select source_url, source_licence, retrieved_on, dataset_version, provider, reference from football_data_sources where workspace_id=%s and kind='match_results'", (wid,)).fetchone()
    assert src["source_url"] == GOOD["source_url"] and src["source_licence"] == GOOD["source_licence"] and str(src["retrieved_on"]) == "2026-01-05" and src["dataset_version"] == GOOD["dataset_version"]
    assert src["provider"] == "user_upload" and "sha256:" in src["reference"]          # the file fingerprint is recorded too, so the data can be traced to the exact file
    audit = conn.execute("select detail from audit_logs where workspace_id=%s and action='football.import'", (wid,)).fetchone()["detail"]
    assert audit["provenance"] == GOOD and audit["file_sha256"] == rep["file_sha256"] and audit["new"] == len(ROWS)
    stored = conn.execute("select report from match_imports where workspace_id=%s", (wid,)).fetchone()["report"]
    assert stored["provenance"] == GOOD
    ev = hdr_get(client, h, "reports/evidence")["data"]["sources"][0]
    assert ev["source_url"] == GOOD["source_url"] and ev["retrieved_on"] == "2026-01-05" and ev["dataset_version"] == GOOD["dataset_version"]


def hdr_get(client, h, path):
    r = client.get(f"/api/v1/{path}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_provenance_is_optional_and_a_missing_field_is_reported_as_not_recorded_never_invented(client, conn, ws):
    h, wid = ws
    rep = do_import(client, h).json()
    assert rep["provenance"] is None
    src = conn.execute("select source_url, source_licence, retrieved_on, dataset_version, licence_note from football_data_sources where workspace_id=%s", (wid,)).fetchone()
    assert src["source_url"] is None and src["source_licence"] is None and src["retrieved_on"] is None and src["dataset_version"] is None
    assert "Supplied by the user" in src["licence_note"]


def test_blank_fields_are_stored_as_nothing_and_text_is_trimmed(client, conn, ws):
    h, wid = ws
    rep = do_import(client, h, {"source_url": "  https://example.org/x.csv  ", "source_licence": "   ", "retrieved_on": None, "dataset_version": ""}).json()
    assert rep["provenance"] == {"source_url": "https://example.org/x.csv", "source_licence": None, "retrieved_on": None, "dataset_version": None}


@pytest.mark.parametrize("bad", [{"source_url": "ftp://example.org/x.csv"}, {"source_url": "not a url"}, {"source_url": "https://a b.org/x"}, {"source_url": "javascript:alert(1)"},
                                 {"retrieved_on": (datetime.now(timezone.utc).date() + timedelta(days=2)).isoformat()}, {"retrieved_on": "yesterday"},
                                 {"source_licence": "x" * 301}, {"dataset_version": "v" * 61}, {"source_url": "https://e.org/" + "a" * 500}])
def test_invalid_provenance_is_rejected_and_nothing_is_stored(client, conn, ws, bad):
    h, wid = ws
    r = do_import(client, h, bad)
    assert r.status_code == 422
    assert conn.execute("select count(*) n from match_history where workspace_id=%s", (wid,)).fetchone()["n"] == 0
    assert conn.execute("select count(*) n from football_data_sources where workspace_id=%s", (wid,)).fetchone()["n"] == 0


def test_a_check_only_import_stores_no_source_and_no_audit_entry(client, conn, ws):
    h, wid = ws
    r = do_import(client, h, GOOD, dry_run=True)
    assert r.status_code == 200 and r.json()["dry_run"] is True and r.json()["provenance"] == GOOD
    assert conn.execute("select count(*) n from football_data_sources where workspace_id=%s", (wid,)).fetchone()["n"] == 0
    assert conn.execute("select count(*) n from audit_logs where workspace_id=%s and action='football.import'", (wid,)).fetchone()["n"] == 0


def test_re_importing_the_same_file_adds_no_matches_but_records_a_second_import_only_when_something_is_new(client, conn, ws):
    h, wid = ws
    do_import(client, h, GOOD)
    again = do_import(client, h, {**GOOD, "dataset_version": "re-download"}).json()
    assert again["new"] == 0 and again["unchanged"] == len(ROWS)
    n = conn.execute("select count(*) n from football_data_sources where workspace_id=%s and kind='match_results'", (wid,)).fetchone()["n"]
    assert n == 1                                                              # nothing new was stored, so no new source record claims to have provided data
    assert conn.execute("select count(*) n from match_imports where workspace_id=%s", (wid,)).fetchone()["n"] == 2          # but the attempt itself is in the import log
    assert json.loads(json.dumps(again["provenance"]))["dataset_version"] == "re-download"
