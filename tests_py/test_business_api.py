import uuid

from .conftest import hdr, make_user

PD = {
    "row_strategies": ["Cooperate", "Defect"],
    "col_strategies": ["Cooperate", "Defect"],
    "payoffs": [[[3, 3], [0, 5]], [[5, 0], [1, 1]]],
}
SCEN = {**PD, "title": "Pricing dilemma", "players": ["Acme", "Globex"], "notes": "illustrative"}


def test_solve_requires_auth_and_returns_analysis(client, conn):
    assert client.post("/api/v1/business/solve", json=PD).status_code == 401
    uid, wid = make_user(conn)
    r = client.post("/api/v1/business/solve", json=PD, headers=hdr(uid, wid))
    assert r.status_code == 200
    a = r.json()
    assert [(n["row"], n["col"]) for n in a["pure_nash"]] == [(1, 1)]
    assert a["dominance"]["row"]["strictly_dominant"] == 1


def test_solve_does_not_store_anything(client, conn):
    uid, wid = make_user(conn)
    client.post("/api/v1/business/solve", json=PD, headers=hdr(uid, wid))
    assert conn.execute("select count(*) n from strategic_scenarios where workspace_id=%s", (wid,)).fetchone()["n"] == 0


def test_invalid_matrices_are_rejected_with_422(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    bad = [
        {**PD, "payoffs": [[[1, 1]]]},                                    # wrong shape
        {**PD, "row_strategies": ["A", "A"]},                             # duplicate names
        {**PD, "row_strategies": ["A"]},                                  # too few
        {**PD, "payoffs": [[[1, 1], [1, 1e12]], [[1, 1], [1, 1]]]},       # out of range
        {**PD, "payoffs": [[[1, "x"], [1, 1]], [[1, 1], [1, 1]]]},        # not a number
        {"row_strategies": ["A", "B"]},                                   # missing fields
    ]
    for b in bad:
        assert client.post("/api/v1/business/solve", json=b, headers=h).status_code == 422, b


def test_sensitivity_endpoint(client, conn):
    uid, wid = make_user(conn)
    r = client.post("/api/v1/business/sensitivity", json={**PD, "row": 1, "col": 1, "player": "row", "lo": -2, "hi": 3}, headers=hdr(uid, wid))
    assert r.status_code == 200
    assert r.json()["thresholds"] == [0.0]
    bad = client.post("/api/v1/business/sensitivity", json={**PD, "row": 1, "col": 1, "player": "row", "lo": 3, "hi": -2}, headers=hdr(uid, wid))
    assert bad.status_code == 422
    assert client.post("/api/v1/business/sensitivity", json={**PD, "row": 0, "col": 0, "player": "both", "lo": 0, "hi": 1}, headers=hdr(uid, wid)).status_code == 422
    assert client.post("/api/v1/business/sensitivity", json={**PD, "row": 7, "col": 0, "player": "row", "lo": 0, "hi": 1}, headers=hdr(uid, wid)).status_code == 422


def test_save_list_get_scenario_with_audit(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    r = client.post("/api/v1/business/scenarios", json=SCEN, headers=h)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    lst = client.get("/api/v1/business/scenarios", headers=h).json()["scenarios"]
    assert len(lst) == 1 and lst[0]["title"] == "Pricing dilemma" and lst[0]["nash_n"] == 1
    got = client.get(f"/api/v1/business/scenarios/{sid}", headers=h).json()
    assert got["players"] == ["Acme", "Globex"] and got["payoffs"] == PD["payoffs"]
    assert got["analysis"]["pure_nash"][0]["payoffs"] == [1.0, 1.0]
    assert conn.execute("select count(*) n from audit_logs where workspace_id=%s and action='scenario.create'", (wid,)).fetchone()["n"] == 1
    assert conn.execute("select count(*) n from activity_history where workspace_id=%s and kind='scenario.created'", (wid,)).fetchone()["n"] == 1


def test_scenario_validation(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    assert client.post("/api/v1/business/scenarios", json={**SCEN, "title": "  "}, headers=h).status_code == 422
    assert client.post("/api/v1/business/scenarios", json={**SCEN, "players": ["A", "A"]}, headers=h).status_code == 422
    assert client.post("/api/v1/business/scenarios", json={**SCEN, "players": ["A"]}, headers=h).status_code == 422


def test_workspace_isolation_and_roles(client, conn):
    a_uid, a_ws = make_user(conn)
    b_uid, b_ws = make_user(conn)
    ha, hb = hdr(a_uid, a_ws), hdr(b_uid, b_ws)
    sid = client.post("/api/v1/business/scenarios", json=SCEN, headers=ha).json()["id"]
    assert client.get(f"/api/v1/business/scenarios/{sid}", headers=hb).status_code == 404
    assert client.get("/api/v1/business/scenarios", headers=hb).json()["scenarios"] == []
    assert client.delete(f"/api/v1/business/scenarios/{sid}", headers=hb).status_code == 404
    assert client.get(f"/api/v1/business/scenarios/{uuid.uuid4()}", headers=ha).status_code == 404
    assert client.get("/api/v1/business/scenarios/not-a-uuid", headers=ha).status_code == 422
    # viewers can analyse but not save
    v_uid, _ = make_user(conn, role="viewer", workspace_id=a_ws)
    hv = hdr(v_uid, a_ws)
    assert client.post("/api/v1/business/solve", json=PD, headers=hv).status_code == 200
    assert client.post("/api/v1/business/scenarios", json=SCEN, headers=hv).status_code == 403
    assert client.delete(f"/api/v1/business/scenarios/{sid}", headers=hv).status_code == 403
    # a plain member cannot delete someone else's scenario; the author can
    m_uid, _ = make_user(conn, role="member", workspace_id=a_ws)
    assert client.delete(f"/api/v1/business/scenarios/{sid}", headers=hdr(m_uid, a_ws)).status_code == 403
    assert client.delete(f"/api/v1/business/scenarios/{sid}", headers=ha).status_code == 204
    assert client.get(f"/api/v1/business/scenarios/{sid}", headers=ha).status_code == 404


def test_compare_scenarios(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    s1 = client.post("/api/v1/business/scenarios", json=SCEN, headers=h).json()["id"]
    coord = {**SCEN, "title": "Coordination", "row_strategies": ["A", "B"], "col_strategies": ["A", "B"],
             "payoffs": [[[2, 2], [0, 0]], [[0, 0], [1, 1]]]}
    s2 = client.post("/api/v1/business/scenarios", json=coord, headers=h).json()["id"]
    r = client.post("/api/v1/business/compare", json={"ids": [s1, s2]}, headers=h)
    assert r.status_code == 200, r.text
    out = {s["title"]: s for s in r.json()["scenarios"]}
    assert out["Pricing dilemma"]["row_dominant"] == "Defect"
    assert len(out["Coordination"]["pure_nash"]) == 2
    assert out["Coordination"]["row_dominant"] is None
    # same id twice -> fewer than two distinct scenarios
    assert client.post("/api/v1/business/compare", json={"ids": [s1, s1]}, headers=h).status_code == 422
    assert client.post("/api/v1/business/compare", json={"ids": [s1]}, headers=h).status_code == 422
    # cannot compare with another workspace's scenario
    o_uid, o_ws = make_user(conn)
    assert client.post("/api/v1/business/compare", json={"ids": [s1, s2]}, headers=hdr(o_uid, o_ws)).status_code == 404
