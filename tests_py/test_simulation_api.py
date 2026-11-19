import json
import uuid

import pytest

from stratiq import simulation_api, simulation_runner

from .conftest import hdr, make_user

MODEL = {
    "variables": [
        {"name": "price", "dist": {"type": "triangular", "low": 18, "mode": 20, "high": 24}},
        {"name": "units", "dist": {"type": "normal", "mean": 1000, "sd": 200}},
    ],
    "outputs": [{"name": "revenue", "expr": "price * max(units, 0)", "threshold": 20000}],
}
RUN = {**MODEL, "title": "Revenue test", "domain": "business", "iterations": 2000, "seed": 123}


@pytest.fixture()
def sync(monkeypatch, conn):
    """Run jobs inline on the test transaction (nothing is ever committed)."""
    monkeypatch.setattr(simulation_api, "launch", lambda rid: simulation_runner.execute_run(conn, rid))


@pytest.fixture()
def noop(monkeypatch):
    monkeypatch.setattr(simulation_api, "launch", lambda rid: None)


def new_run(client, h, **over):
    r = client.post("/api/v1/simulations/runs", json={**RUN, **over}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ------------------------------------------------------------------ auth & validation
def test_requires_auth(client):
    for method, path in [("get", "/api/v1/simulations/runs"), ("post", "/api/v1/simulations/runs"), ("post", "/api/v1/simulations/validate")]:
        assert getattr(client, method)(path).status_code == 401


def test_validate_endpoint(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    ok = client.post("/api/v1/simulations/validate", json=MODEL, headers=h)
    assert ok.status_code == 200 and 18 < ok.json()["pilot"]["revenue"]["mean"] < 40000
    bad_formula = {**MODEL, "outputs": [{"name": "y", "expr": "__import__('os')"}]}
    r = client.post("/api/v1/simulations/validate", json=bad_formula, headers=h)
    assert r.status_code == 422
    assert "only these functions are allowed" in r.json()["detail"] or "unknown name" in r.json()["detail"]
    broken = {"variables": [{"name": "x", "dist": {"type": "constant", "value": 1}}], "outputs": [{"name": "y", "expr": "1/(x-1)"}]}
    r = client.post("/api/v1/simulations/validate", json=broken, headers=h)
    assert r.status_code == 422 and "fails when run" in r.json()["detail"]
    assert conn.execute("select count(*) n from simulation_runs where workspace_id=%s", (wid,)).fetchone()["n"] == 0


@pytest.mark.parametrize(
    "over",
    [
        {"iterations": 5}, {"iterations": 10**7}, {"seed": -5}, {"title": "   "}, {"domain": "astrology"},
        {"variables": []}, {"outputs": []},
        {"variables": [{"name": "price", "dist": {"type": "normal", "mean": 1, "sd": -1}}]},
        {"outputs": [{"name": "r", "expr": "ghost + 1"}]},
    ],
)
def test_invalid_runs_rejected(client, conn, noop, over):
    uid, wid = make_user(conn)
    r = client.post("/api/v1/simulations/runs", json={**RUN, **over}, headers=hdr(uid, wid))
    assert r.status_code == 422, r.text
    assert conn.execute("select count(*) n from simulation_runs where workspace_id=%s", (wid,)).fetchone()["n"] == 0


def test_viewer_can_validate_but_not_run(client, conn, noop):
    _, wid = make_user(conn)
    vid, _ = make_user(conn, role="viewer", workspace_id=wid)
    h = hdr(vid, wid)
    assert client.post("/api/v1/simulations/validate", json=MODEL, headers=h).status_code == 200
    assert client.post("/api/v1/simulations/runs", json=RUN, headers=h).status_code == 403


# ------------------------------------------------------------------ running
def test_run_completes_with_full_result_and_audit(client, conn, sync):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    rid = new_run(client, h)
    r = client.get(f"/api/v1/simulations/runs/{rid}", headers=h).json()
    assert r["status"] == "completed" and r["progress"] == 1 and r["seed"] == 123 and r["error"] is None
    res = r["result"]
    assert res["iterations"] == 2000 and res["seed"] == 123 and len(res["result_hash"]) == 64
    assert 18 * 800 < res["outputs"]["revenue"]["stats"]["mean"] < 24 * 1200
    assert res["outputs"]["revenue"]["prob_above"]["threshold"] == 20000
    assert {s["variable"] for s in res["outputs"]["revenue"]["sensitivity"]} == {"price", "units"}
    assert conn.execute("select count(*) n from audit_logs where workspace_id=%s and action='simulation.create'", (wid,)).fetchone()["n"] == 1
    assert conn.execute("select count(*) n from activity_history where workspace_id=%s and kind='simulation.started'", (wid,)).fetchone()["n"] == 1


def test_same_seed_reproduces_and_random_seed_is_recorded(client, conn, sync):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    a, b = new_run(client, h), new_run(client, h)
    ra, rb = (client.get(f"/api/v1/simulations/runs/{i}", headers=h).json() for i in (a, b))
    assert ra["result"]["result_hash"] == rb["result"]["result_hash"]
    assert ra["result"]["outputs"] == rb["result"]["outputs"]
    c = new_run(client, h, seed=None)
    rc = client.get(f"/api/v1/simulations/runs/{c}", headers=h).json()
    assert 0 <= rc["seed"] < 2**31 and rc["result"]["seed"] == rc["seed"]
    # re-running the recorded seed reproduces it exactly
    d = new_run(client, h, seed=rc["seed"])
    assert client.get(f"/api/v1/simulations/runs/{d}", headers=h).json()["result"]["result_hash"] == rc["result"]["result_hash"]


def test_job_that_fails_midway_is_marked_failed_with_reason(client, conn, sync):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    rid = new_run(client, h, variables=[{"name": "x", "dist": {"type": "uniform", "low": -0.0001, "high": 1}}],
                  outputs=[{"name": "y", "expr": "log(x)"}], iterations=100000, seed=11)
    r = client.get(f"/api/v1/simulations/runs/{rid}", headers=h).json()
    assert r["status"] == "failed" and "iteration" in r["error"] and r["result"] is None


def test_queued_cancel_delete_flow(client, conn, noop):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    rid = new_run(client, h)
    assert client.get(f"/api/v1/simulations/runs/{rid}", headers=h).json()["status"] == "queued"
    assert client.delete(f"/api/v1/simulations/runs/{rid}", headers=h).status_code == 409  # still active
    assert client.post(f"/api/v1/simulations/runs/{rid}/cancel", headers=h).json()["status"] == "cancelled"
    assert client.post(f"/api/v1/simulations/runs/{rid}/cancel", headers=h).status_code == 409
    assert simulation_runner.execute_run(conn, rid) is None  # cancelled jobs are never started
    assert client.get(f"/api/v1/simulations/runs/{rid}", headers=h).json()["status"] == "cancelled"
    assert client.delete(f"/api/v1/simulations/runs/{rid}", headers=h).status_code == 204
    assert client.get(f"/api/v1/simulations/runs/{rid}", headers=h).status_code == 404


def test_cancellation_stops_a_running_job(client, conn, noop, monkeypatch):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    rid = new_run(client, h, iterations=20000)
    orig = simulation_runner.sim.run

    def run_then_cancel(cfg, progress=None, chunk=2000):
        def prog(done, total):
            conn.execute("update simulation_runs set status='cancelled' where id=%s", (rid,))  # user pressed Cancel
            return progress(done, total)
        return orig(cfg, progress=prog, chunk=500)

    monkeypatch.setattr(simulation_runner.sim, "run", run_then_cancel)
    simulation_runner.execute_run(conn, rid)
    r = client.get(f"/api/v1/simulations/runs/{rid}", headers=h).json()
    assert r["status"] == "cancelled" and r["result"] is None and r["finished_at"] is not None


def test_job_cannot_be_claimed_twice(client, conn, sync):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    rid = new_run(client, h)
    before = client.get(f"/api/v1/simulations/runs/{rid}", headers=h).json()["result"]["runtime_ms"]
    simulation_runner.execute_run(conn, rid)  # second claim: not queued -> no-op
    assert client.get(f"/api/v1/simulations/runs/{rid}", headers=h).json()["result"]["runtime_ms"] == before


def test_stale_running_job_is_failed_honestly(client, conn, noop):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    rid = new_run(client, h)
    conn.execute("update simulation_runs set status='running', heartbeat_at=now() - interval '10 minutes' where id=%s", (rid,))
    r = client.get(f"/api/v1/simulations/runs/{rid}", headers=h).json()
    assert r["status"] == "failed" and "stopped responding" in r["error"]
    fresh = new_run(client, h)
    conn.execute("update simulation_runs set status='running', heartbeat_at=now() where id=%s", (fresh,))
    assert client.get(f"/api/v1/simulations/runs/{fresh}", headers=h).json()["status"] == "running"


# ------------------------------------------------------------------ isolation, compare, export
def test_workspace_isolation(client, conn, sync):
    a_uid, a_ws = make_user(conn)
    b_uid, b_ws = make_user(conn)
    ha, hb = hdr(a_uid, a_ws), hdr(b_uid, b_ws)
    rid = new_run(client, ha)
    for method, path in [("get", f"/api/v1/simulations/runs/{rid}"), ("post", f"/api/v1/simulations/runs/{rid}/cancel"),
                         ("delete", f"/api/v1/simulations/runs/{rid}"), ("get", f"/api/v1/simulations/runs/{rid}/report?format=csv")]:
        assert getattr(client, method)(path, headers=hb).status_code == 404, path
    assert client.get("/api/v1/simulations/runs", headers=hb).json()["runs"] == []
    other = new_run(client, hb)
    assert client.post("/api/v1/simulations/compare", json={"ids": [rid, other]}, headers=hb).status_code == 404
    assert client.get(f"/api/v1/simulations/runs/{uuid.uuid4()}", headers=ha).status_code == 404
    assert client.get("/api/v1/simulations/runs/not-a-uuid", headers=ha).status_code == 422


def test_only_author_or_admin_can_delete(client, conn, sync):
    owner, wid = make_user(conn)
    member, _ = make_user(conn, role="member", workspace_id=wid)
    rid = new_run(client, hdr(owner, wid))
    assert client.delete(f"/api/v1/simulations/runs/{rid}", headers=hdr(member, wid)).status_code == 403
    assert client.delete(f"/api/v1/simulations/runs/{rid}", headers=hdr(owner, wid)).status_code == 204


def test_compare_runs(client, conn, sync, noop_after=None):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    a = new_run(client, h, title="Base", seed=1)
    shifted = {**MODEL, "variables": [MODEL["variables"][0], {"name": "units", "dist": {"type": "normal", "mean": 1200, "sd": 200}}]}
    b = new_run(client, h, title="More units", seed=2, **shifted)
    r = client.post("/api/v1/simulations/compare", json={"ids": [a, b]}, headers=h)
    assert r.status_code == 200, r.text
    row = r.json()["outputs"][0]
    assert row["output"] == "revenue" and row["diff_vs_first"][0] is None
    d = row["diff_vs_first"][1]
    assert 3000 < d["mean_diff"] < 6500 and d["ci95"][0] < d["mean_diff"] < d["ci95"][1]
    assert len(r.json()["runs"]) == 2 and "revenue" in r.json()["runs"][0]["histograms"]
    assert client.post("/api/v1/simulations/compare", json={"ids": [a, a]}, headers=h).status_code == 422
    assert client.post("/api/v1/simulations/compare", json={"ids": [a]}, headers=h).status_code == 422


def test_compare_rejects_incomplete_runs(client, conn, noop):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    a, b = new_run(client, h), new_run(client, h)
    r = client.post("/api/v1/simulations/compare", json={"ids": [a, b]}, headers=h)
    assert r.status_code == 409 and "completed" in r.json()["detail"]


def test_reports(client, conn, sync):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    rid = new_run(client, h, title="My Report / test")
    res = client.get(f"/api/v1/simulations/runs/{rid}", headers=h).json()["result"]
    js = client.get(f"/api/v1/simulations/runs/{rid}/report?format=json", headers=h)
    assert js.headers["content-disposition"] == 'attachment; filename="my-report-test.json"'
    assert json.loads(js.text)["result"]["result_hash"] == res["result_hash"]
    md = client.get(f"/api/v1/simulations/runs/{rid}/report?format=md", headers=h)
    assert res["result_hash"] in md.text and "Scenario assumptions only" in md.text and md.headers["content-type"].startswith("text/markdown")
    csv_ = client.get(f"/api/v1/simulations/runs/{rid}/report?format=csv", headers=h)
    assert "revenue,mean," in csv_.text and csv_.headers["content-type"].startswith("text/csv")
    assert client.get(f"/api/v1/simulations/runs/{rid}/report?format=exe", headers=h).status_code == 422
    assert conn.execute("select count(*) n from audit_logs where workspace_id=%s and action='simulation.export'", (wid,)).fetchone()["n"] == 3


def test_report_requires_completed_run(client, conn, noop):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    rid = new_run(client, h)
    assert client.get(f"/api/v1/simulations/runs/{rid}/report?format=md", headers=h).status_code == 409


def test_overview_lists_simulations_scoped_to_workspace(client, conn, sync):
    a_uid, a_ws = make_user(conn)
    b_uid, b_ws = make_user(conn)
    new_run(client, hdr(a_uid, a_ws), title="Mine")
    mine = client.get("/api/v1/overview", headers=hdr(a_uid, a_ws)).json()
    assert [s["title"] for s in mine["saved_simulations"]] == ["Mine"] and int(mine["counts"]["simulations"]) == 1
    assert client.get("/api/v1/overview", headers=hdr(b_uid, b_ws)).json()["saved_simulations"] == []


def test_inline_execution_for_serverless_hosts(client, conn, noop, monkeypatch):
    """On Vercel (or SIMULATION_INLINE=1) the job runs inside the request, because a frozen function cannot host a background thread."""
    monkeypatch.setenv("SIMULATION_INLINE", "1")
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    rid = new_run(client, h)  # the launcher is a no-op: only inline execution can complete this run
    r = client.get(f"/api/v1/simulations/runs/{rid}", headers=h).json()
    assert r["status"] == "completed" and r["progress"] == 1 and r["result"]["result_hash"]
