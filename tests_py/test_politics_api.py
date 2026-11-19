import uuid

import pytest

from .conftest import hdr, make_user

COALITION = {"parties": [{"name": "A", "seats": 49, "position": 1}, {"name": "B", "seats": 48, "position": 2}, {"name": "C", "seats": 3, "position": 3}]}
ALLOC = {"method": "dhondt", "seats": 8, "threshold": 0, "parties": [{"name": n, "votes": v} for n, v in [("A", 100000), ("B", 80000), ("C", 30000), ("D", 20000)]]}
TURNOUT = {
    "parties": ["A", "B"], "method": "dhondt", "seats": 10, "threshold": 0,
    "blocs": [{"name": "Bloc 1", "electorate": 1000, "turnout": 0.5, "prefs": {"A": 0.8, "B": 0.2}},
              {"name": "Bloc 2", "electorate": 1000, "turnout": 0.5, "prefs": {"A": 0.2, "B": 0.8}}],
    "sweep": {"mode": "bloc", "bloc": 0, "lo": 0, "hi": 1},
}
POLICY = {
    "alternatives": ["Policy 1", "Policy 2", "Policy 3"],
    "criteria": [{"name": "Benefit", "weight": 1, "direction": "benefit"}, {"name": "Cost", "weight": 1, "direction": "cost"}],
    "scores": [[10, 1], [20, 3], [30, 5]], "seed": 5, "samples": 500,
}


def H(conn):
    uid, wid = make_user(conn)
    return uid, wid, hdr(uid, wid)


# ------------------------------------------------------------------ auth & stateless tools
@pytest.mark.parametrize("path", ["coalitions", "allocate", "simulate", "turnout", "policy"])
def test_requires_auth(client, path):
    assert client.post(f"/api/v1/politics/{path}", json={}).status_code == 401


def test_coalition_endpoint(client, conn):
    _, _, h = H(conn)
    r = client.post("/api/v1/politics/coalitions", json=COALITION, headers=h)
    assert r.status_code == 200, r.text
    a = r.json()
    assert [p["shapley_shubik_exact"] for p in a["parties"]] == ["1/3", "1/3", "1/3"]
    assert a["connected_minimal_winning"] == 2 and "not a poll" in a["notice"].lower()


@pytest.mark.parametrize(
    "mut",
    [
        {"parties": COALITION["parties"][:1]},
        {"quota_fraction": 0.2},
        {"parties": [{"name": "A", "seats": 5}, {"name": "A", "seats": 5}]},
        {"parties": [{"name": "A", "seats": -5}, {"name": "B", "seats": 5}]},
        {"parties": [{"name": "A", "seats": 0}, {"name": "B", "seats": 0}]},
    ],
)
def test_coalition_validation(client, conn, mut):
    _, _, h = H(conn)
    assert client.post("/api/v1/politics/coalitions", json={**COALITION, **mut}, headers=h).status_code == 422


def test_allocate_endpoint(client, conn):
    _, _, h = H(conn)
    r = client.post("/api/v1/politics/allocate", json=ALLOC, headers=h).json()
    assert [p["seats"] for p in r["parties"]] == [4, 3, 1, 0]
    assert sum(p["vote_share"] for p in r["parties"]) == pytest.approx(1)
    r = client.post("/api/v1/politics/allocate", json={**ALLOC, "method": "sainte_lague"}, headers=h).json()
    assert [p["seats"] for p in r["parties"]] == [3, 3, 1, 1]
    for bad in [{"method": "magic"}, {"seats": 0}, {"seats": 9999}, {"threshold": 1.5}, {"threshold": 0.9}]:
        assert client.post("/api/v1/politics/allocate", json={**ALLOC, **bad}, headers=h).status_code == 422, bad


def test_simulate_endpoint(client, conn):
    _, _, h = H(conn)
    body = {"method": "dhondt", "seats": 100, "threshold": 0, "concentration": 100000, "iterations": 200, "seed": 3,
            "parties": [{"name": "A", "votes": 45}, {"name": "B", "votes": 35}, {"name": "C", "votes": 20}], "candidates": [["A", "B"], ["C"]]}
    r = client.post("/api/v1/politics/simulate", json=body, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["seed"] == 3 and out["candidates"][0]["p_winning"] > 0.99 and out["candidates"][1]["p_winning"] == 0
    assert out == client.post("/api/v1/politics/simulate", json=body, headers=h).json()  # same seed, same output
    assert client.post("/api/v1/politics/simulate", json={**body, "seed": None}, headers=h).json()["seed"] >= 0
    assert client.post("/api/v1/politics/simulate", json={**body, "candidates": [["Z"]]}, headers=h).status_code == 422
    assert client.post("/api/v1/politics/simulate", json={**body, "iterations": 10}, headers=h).status_code == 422
    assert client.post("/api/v1/politics/simulate", json={**body, "parties": [{"name": "A", "votes": 1}, {"name": "A", "votes": 2}]}, headers=h).status_code == 422


def test_turnout_endpoint(client, conn):
    _, _, h = H(conn)
    r = client.post("/api/v1/politics/turnout", json=TURNOUT, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["baseline"]["seats"] == [5, 5]
    assert any(abs(c["at"] - 0.5) < 1e-6 for c in out["sweep"]["changes"])
    bad_prefs = {**TURNOUT, "blocs": [{**TURNOUT["blocs"][0], "prefs": {"A": 0.9, "B": 0.2}}, TURNOUT["blocs"][1]]}
    assert client.post("/api/v1/politics/turnout", json=bad_prefs, headers=h).status_code == 422
    assert client.post("/api/v1/politics/turnout", json={**TURNOUT, "sweep": {"mode": "bloc", "bloc": 9, "lo": 0, "hi": 1}}, headers=h).status_code == 422
    assert client.post("/api/v1/politics/turnout", json={**TURNOUT, "sweep": None}, headers=h).json().get("sweep") is None


def test_policy_endpoint(client, conn):
    _, _, h = H(conn)
    r = client.post("/api/v1/politics/policy", json=POLICY, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["seed"] == 5 and all(a["pareto_optimal"] for a in out["alternatives"])
    assert out == client.post("/api/v1/politics/policy", json=POLICY, headers=h).json()
    assert client.post("/api/v1/politics/policy", json={**POLICY, "scores": [[1, 2]]}, headers=h).status_code == 422
    assert client.post("/api/v1/politics/policy", json={**POLICY, "criteria": [{"name": "x", "weight": -1, "direction": "benefit"}, POLICY["criteria"][1]]}, headers=h).status_code == 422


# ------------------------------------------------------------------ saved scenarios
def save(client, h, kind, inputs, title="Scenario"):
    r = client.post("/api/v1/politics/scenarios", json={"kind": kind, "title": title, "inputs": inputs, "notes": "n"}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_save_list_get_with_audit(client, conn):
    uid, wid, h = H(conn)
    sid = save(client, h, "coalition", COALITION, "Three-party")
    lst = client.get("/api/v1/politics/scenarios", headers=h).json()["scenarios"]
    assert [(s["title"], s["kind"]) for s in lst] == [("Three-party", "coalition")]
    assert client.get("/api/v1/politics/scenarios?kind=turnout", headers=h).json()["scenarios"] == []
    got = client.get(f"/api/v1/politics/scenarios/{sid}", headers=h).json()
    assert got["kind"] == "coalition" and got["notes"] == "n" and got["analysis"]["parties"][0]["name"] == "A"
    assert conn.execute("select count(*) n from audit_logs where workspace_id=%s and action='political_scenario.create'", (wid,)).fetchone()["n"] == 1
    # politics scenarios never leak into the Business module's list
    assert client.get("/api/v1/business/scenarios", headers=h).json()["scenarios"] == []


def test_policy_scenario_seed_is_fixed_so_it_reproduces(client, conn):
    _, _, h = H(conn)
    sid = save(client, h, "policy", {**POLICY, "seed": None})
    a = client.get(f"/api/v1/politics/scenarios/{sid}", headers=h).json()
    b = client.get(f"/api/v1/politics/scenarios/{sid}", headers=h).json()
    assert a["inputs"]["seed"] is not None and a["analysis"] == b["analysis"]


def test_invalid_scenarios_rejected(client, conn):
    _, wid, h = H(conn)
    for body in [
        {"kind": "coalition", "title": "x", "inputs": {"parties": []}},
        {"kind": "turnout", "title": "x", "inputs": COALITION},
        {"kind": "nope", "title": "x", "inputs": {}},
        {"kind": "coalition", "title": "  ", "inputs": COALITION},
    ]:
        assert client.post("/api/v1/politics/scenarios", json=body, headers=h).status_code == 422, body
    assert conn.execute("select count(*) n from strategic_scenarios where workspace_id=%s", (wid,)).fetchone()["n"] == 0


def test_isolation_roles_and_delete(client, conn):
    a_uid, a_ws, ha = H(conn)
    _, _, hb = H(conn)
    sid = save(client, ha, "coalition", COALITION)
    assert client.get(f"/api/v1/politics/scenarios/{sid}", headers=hb).status_code == 404
    assert client.delete(f"/api/v1/politics/scenarios/{sid}", headers=hb).status_code == 404
    assert client.get("/api/v1/politics/scenarios", headers=hb).json()["scenarios"] == []
    assert client.get(f"/api/v1/politics/scenarios/{uuid.uuid4()}", headers=ha).status_code == 404
    v_uid, _ = make_user(conn, role="viewer", workspace_id=a_ws)
    hv = hdr(v_uid, a_ws)
    assert client.post("/api/v1/politics/coalitions", json=COALITION, headers=hv).status_code == 200  # analysis is read-only
    assert client.post("/api/v1/politics/scenarios", json={"kind": "coalition", "title": "x", "inputs": COALITION}, headers=hv).status_code == 403
    assert client.delete(f"/api/v1/politics/scenarios/{sid}", headers=hv).status_code == 403
    m_uid, _ = make_user(conn, role="member", workspace_id=a_ws)
    assert client.delete(f"/api/v1/politics/scenarios/{sid}", headers=hdr(m_uid, a_ws)).status_code == 403
    assert client.delete(f"/api/v1/politics/scenarios/{sid}", headers=ha).status_code == 204


def test_political_and_business_scenarios_are_separate_namespaces(client, conn):
    _, _, h = H(conn)
    pid = save(client, h, "coalition", COALITION)
    biz = client.post("/api/v1/business/scenarios", headers=h, json={
        "title": "B", "players": ["X", "Y"], "row_strategies": ["a", "b"], "col_strategies": ["a", "b"], "payoffs": [[[1, 1], [0, 0]], [[0, 0], [1, 1]]]}).json()["id"]
    assert client.get(f"/api/v1/business/scenarios/{pid}", headers=h).status_code == 404
    assert client.get(f"/api/v1/politics/scenarios/{biz}", headers=h).status_code == 404


def test_compare_same_kind_only(client, conn):
    _, _, h = H(conn)
    c1 = save(client, h, "coalition", COALITION, "Base")
    c2 = save(client, h, "coalition", {"parties": [{"name": "A", "seats": 60}, {"name": "B", "seats": 40}]}, "A dominant")
    t1 = save(client, h, "turnout", TURNOUT, "Turnout")
    p1 = save(client, h, "policy", POLICY, "Policy")
    r = client.post("/api/v1/politics/compare", json={"ids": [c1, c2]}, headers=h)
    assert r.status_code == 200 and r.json()["kind"] == "coalition"
    s = {x["title"]: x["summary"] for x in r.json()["scenarios"]}
    assert s["A dominant"]["parties"][0]["veto"] is True and s["Base"]["minimal_winning_count"] == 3
    rt = client.post("/api/v1/politics/compare", json={"ids": [t1, save(client, h, "turnout", {**TURNOUT, "sweep": None}, "No sweep")]}, headers=h).json()
    assert rt["kind"] == "turnout" and rt["scenarios"][0]["summary"]["change_points"] is not None and rt["scenarios"][1]["summary"]["change_points"] is None
    rp = client.post("/api/v1/politics/compare", json={"ids": [p1, save(client, h, "policy", {**POLICY, "scores": [[30, 5], [20, 3], [10, 1]]}, "Reordered")]}, headers=h).json()
    assert rp["kind"] == "policy" and all("ranking" in x["summary"] for x in rp["scenarios"])
    assert client.post("/api/v1/politics/compare", json={"ids": [c1, t1]}, headers=h).status_code == 422  # mixed kinds
    assert client.post("/api/v1/politics/compare", json={"ids": [c1, c1]}, headers=h).status_code == 422
    assert client.post("/api/v1/politics/compare", json={"ids": [c1]}, headers=h).status_code == 422
    _, _, other = H(conn)
    assert client.post("/api/v1/politics/compare", json={"ids": [c1, c2]}, headers=other).status_code == 404
