import json
import uuid

import pytest

from stratiq import assistant, simulation_api, simulation_runner

from .conftest import hdr, make_user

BIZ = {"title": "Price war", "players": ["Acme", "Globex"], "row_strategies": ["Hold", "Cut"], "col_strategies": ["Hold", "Cut"], "payoffs": [[[3, 3], [0, 5]], [[5, 0], [1, 1]]]}
COAL = {"kind": "coalition", "title": "Three parties", "inputs": {"parties": [{"name": "A", "seats": 49}, {"name": "B", "seats": 48}, {"name": "C", "seats": 3}]}}
FIN = {"kind": "stress", "title": "Shock set", "inputs": {"assets": [{"name": "Eq", "weight": 0.6}, {"name": "Bd", "weight": 0.4}], "initial_value": 100000,
       "scenarios": [{"name": "Equity -30%", "shocks": {"Eq": -0.3}}], "reverse_target_loss": 0.1}}
SIM = {"title": "Revenue", "domain": "business", "iterations": 1000, "seed": 4,
       "variables": [{"name": "u", "dist": {"type": "normal", "mean": 100, "sd": 10}}], "outputs": [{"name": "r", "expr": "u * 2", "threshold": 200}]}


@pytest.fixture()
def sync(monkeypatch, conn):
    monkeypatch.setattr(simulation_api, "launch", lambda rid: simulation_runner.execute_run(conn, rid))


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def H(conn):
    uid, wid = make_user(conn)
    return uid, wid, hdr(uid, wid)


def mk_pred(client, h):
    f = client.get("/api/v1/sports/fixtures?league_id=nfl-fict&status=scheduled&limit=1", headers=h).json()["fixtures"][0]
    r = client.post("/api/v1/sports/predictions", json={"fixture_id": f["id"]}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def mk_sim(client, h, **over):
    r = client.post("/api/v1/simulations/runs", json={**SIM, **over}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def mk_scen(client, h, path, body):
    r = client.post(f"/api/v1/{path}/scenarios", json=body, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ------------------------------------------------------------------ assistant
def test_status_and_auth(client, conn):
    assert client.get("/api/v1/assistant/status").status_code == 401
    _, _, h = H(conn)
    s = client.get("/api/v1/assistant/status", headers=h).json()
    assert s["llm_configured"] is False and s["deterministic"] is True and "every number" in s["note"]


@pytest.mark.parametrize("which", ["prediction", "simulation", "business", "politics", "finance"])
def test_explain_every_item_type(client, conn, sync, which):
    uid, wid, h = H(conn)
    if which == "prediction":
        typ, iid = "prediction", mk_pred(client, h)
    elif which == "simulation":
        typ, iid = "simulation", mk_sim(client, h)
    else:
        typ = "scenario"
        iid = {"business": lambda: mk_scen(client, h, "business", BIZ), "politics": lambda: mk_scen(client, h, "politics", COAL), "finance": lambda: mk_scen(client, h, "finance", FIN)}[which]()
    r = client.post("/api/v1/assistant/explain", json={"type": typ, "id": iid}, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["mode"] == "deterministic" and out["narrative"] is None and out["metrics"] and out["notice"]
    assert [s["id"] for s in out["sections"]] == ["overview", "uncertainty", "assumptions", "limitations", "next"]
    assert out["item"]["id"] == iid and out["grounding"]["checked"] is False
    only = client.post("/api/v1/assistant/explain", json={"type": typ, "id": iid, "focus": "limitations"}, headers=h).json()
    assert [s["id"] for s in only["sections"]] == ["limitations"] and only["sections"][0]["items"]
    assert conn.execute("select count(*) n from audit_logs where workspace_id=%s and action='assistant.explain'", (wid,)).fetchone()["n"] == 2


def test_explanation_numbers_match_the_stored_result(client, conn):
    _, _, h = H(conn)
    sid = mk_scen(client, h, "business", BIZ)
    out = client.post("/api/v1/assistant/explain", json={"type": "scenario", "id": sid, "focus": "overview"}, headers=h).json()
    text = " ".join(out["sections"][0]["items"])
    assert "Globex playing Cut" in text and "payoffs 1 and 1" in text  # the (Cut, Cut) equilibrium of the prisoner's dilemma
    assert any(m["label"] == "Pure Nash equilibria" and m["raw"] == 1 for m in out["metrics"])


def test_isolation_validation_and_roles(client, conn, sync):
    _, wid, ha = H(conn)
    _, _, hb = H(conn)
    sid = mk_scen(client, ha, "business", BIZ)
    run = mk_sim(client, ha)
    for typ, iid in (("scenario", sid), ("simulation", run)):
        assert client.post("/api/v1/assistant/explain", json={"type": typ, "id": iid}, headers=hb).status_code == 404
    assert client.post("/api/v1/assistant/explain", json={"type": "scenario", "id": str(uuid.uuid4())}, headers=ha).status_code == 404
    assert client.post("/api/v1/assistant/explain", json={"type": "nope", "id": sid}, headers=ha).status_code == 422
    assert client.post("/api/v1/assistant/explain", json={"type": "scenario", "id": sid, "focus": "x"}, headers=ha).status_code == 422
    assert client.post("/api/v1/assistant/explain", json={"type": "scenario", "id": "not-a-uuid"}, headers=ha).status_code == 422
    v, _ = make_user(conn, role="viewer", workspace_id=wid)
    assert client.post("/api/v1/assistant/explain", json={"type": "scenario", "id": sid}, headers=hdr(v, wid)).status_code == 200  # read-only roles may ask


def test_incomplete_simulation_cannot_be_explained(client, conn, monkeypatch):
    monkeypatch.setattr(simulation_api, "launch", lambda rid: None)
    _, _, h = H(conn)
    rid = mk_sim(client, h)
    assert client.post("/api/v1/assistant/explain", json={"type": "simulation", "id": rid}, headers=h).status_code == 409


def test_free_form_question_requires_a_model(client, conn):
    _, _, h = H(conn)
    sid = mk_scen(client, h, "business", BIZ)
    r = client.post("/api/v1/assistant/explain", json={"type": "scenario", "id": sid, "question": "Who wins?"}, headers=h)
    assert r.status_code == 422 and "language model" in r.json()["detail"]
    assert client.post("/api/v1/assistant/explain", json={"type": "scenario", "id": sid, "question": "q" * 600}, headers=h).status_code == 422


def test_language_model_text_is_used_only_when_grounded(client, conn, monkeypatch):
    uid, wid, h = H(conn)
    sid = mk_scen(client, h, "business", BIZ)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert client.get("/api/v1/assistant/status", headers=h).json()["llm_configured"] is True
    seen = {}

    def good(system, user):
        seen["user"] = user
        return "There is one pure Nash equilibrium where both firms cut, with payoffs 1 and 1. That depends entirely on the payoffs entered."

    monkeypatch.setattr(assistant, "call_llm", good)
    r = client.post("/api/v1/assistant/explain", json={"type": "scenario", "id": sid, "focus": "overview"}, headers=h).json()
    assert r["mode"] == "language_model" and "pure Nash" in r["narrative"] and r["sections"]
    assert "Price war" in seen["user"] and "<facts>" in seen["user"] and "test.invalid" not in seen["user"] and str(uid) not in seen["user"] and str(wid) not in seen["user"]  # no user or workspace identity reaches the model

    monkeypatch.setattr(assistant, "call_llm", lambda s, u: "Both firms will earn $48,200 and the chance of cutting is 91.4%.")
    r = client.post("/api/v1/assistant/explain", json={"type": "scenario", "id": sid}, headers=h).json()
    assert r["mode"] == "deterministic" and r["narrative"] is None and r["grounding"]["rejected"] is True
    assert "$48,200" in r["grounding"]["offending_numbers"] and "91.4%" in r["grounding"]["offending_numbers"]

    def boom(s, u):
        raise RuntimeError("api key test-key rejected")

    monkeypatch.setattr(assistant, "call_llm", boom)
    r = client.post("/api/v1/assistant/explain", json={"type": "scenario", "id": sid}, headers=h)
    assert r.status_code == 200 and r.json()["mode"] == "deterministic" and "test-key" not in r.text
    assert client.post("/api/v1/assistant/explain", json={"type": "scenario", "id": sid, "use_llm": False}, headers=h).json()["mode"] == "deterministic"
    rec = conn.execute("select detail from audit_logs where workspace_id=%s and action='assistant.explain' order by id", (wid,)).fetchall()
    assert [json.loads(x["detail"]) if isinstance(x["detail"], str) else x["detail"] for x in rec][1]["rejected"] is True


def test_compare_simulations_and_scenarios(client, conn, sync):
    _, _, h = H(conn)
    a = mk_sim(client, h, title="Base", seed=1)
    b = mk_sim(client, h, title="Higher", seed=2, variables=[{"name": "u", "dist": {"type": "normal", "mean": 130, "sd": 10}}])
    r = client.post("/api/v1/assistant/compare", json={"type": "simulation", "ids": [a, b]}, headers=h)
    assert r.status_code == 200, r.text
    assert any("excludes zero" in x for x in r.json()["lines"]) and r.json()["mode"] == "deterministic"
    s1, s2 = mk_scen(client, h, "politics", COAL, ), mk_scen(client, h, "politics", {**COAL, "title": "Two", "inputs": {"parties": [{"name": "A", "seats": 60}, {"name": "B", "seats": 40}]}})
    r = client.post("/api/v1/assistant/compare", json={"type": "scenario", "ids": [s1, s2]}, headers=h)
    assert r.status_code == 200 and len(r.json()["lines"]) == 2
    biz = mk_scen(client, h, "business", BIZ)
    assert client.post("/api/v1/assistant/compare", json={"type": "scenario", "ids": [s1, biz]}, headers=h).status_code == 422  # different modules
    assert client.post("/api/v1/assistant/compare", json={"type": "scenario", "ids": [s1, s1]}, headers=h).status_code == 422
    _, _, other = H(conn)
    assert client.post("/api/v1/assistant/compare", json={"type": "scenario", "ids": [s1, s2]}, headers=other).status_code == 404


# ------------------------------------------------------------------ library & reports
def populate(client, h):
    return {"prediction": mk_pred(client, h), "business": mk_scen(client, h, "business", BIZ), "politics": mk_scen(client, h, "politics", COAL),
            "finance": mk_scen(client, h, "finance", FIN), "simulation": mk_sim(client, h)}


def test_library_lists_everything_filters_and_isolates(client, conn, sync):
    _, _, h = H(conn)
    _, _, other = H(conn)
    ids = populate(client, h)
    items = client.get("/api/v1/library/items", headers=h).json()["items"]
    assert {i["id"] for i in items} == set(ids.values())
    assert {i["module"] for i in items} == {"sports", "business", "politics", "finance", "simulation"}
    assert {i["type"] for i in client.get("/api/v1/library/items?type=scenario", headers=h).json()["items"]} == {"scenario"}
    assert [i["title"] for i in client.get("/api/v1/library/items?q=price", headers=h).json()["items"]] == ["Price war"]
    assert client.get("/api/v1/library/items?q=zzzz", headers=h).json()["items"] == []
    assert client.get("/api/v1/library/items", headers=other).json()["items"] == []
    assert client.get("/api/v1/library/items?type=bogus", headers=h).status_code == 422


@pytest.mark.parametrize("which,typ", [("prediction", "prediction"), ("simulation", "simulation"), ("business", "scenario"), ("politics", "scenario"), ("finance", "scenario")])
def test_reports_in_three_formats(client, conn, sync, which, typ):
    _, wid, h = H(conn)
    iid = populate(client, h)[which]
    q = f"/api/v1/library/report?type={typ}&id={iid}"
    md = client.get(q + "&format=md", headers=h)
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown") and md.headers["content-disposition"].startswith("attachment")
    assert "## Key results" in md.text and "## Limitations" in md.text and "Numbers in this report were computed" in md.text
    html = client.get(q + "&format=html", headers=h)
    assert html.headers["content-type"].startswith("text/html") and html.headers["content-disposition"].startswith("inline") and html.text.startswith("<!doctype html>")
    assert html.headers["x-content-type-options"] == "nosniff"
    js = client.get(q + "&format=json", headers=h)
    body = json.loads(js.text)
    assert body["metrics"] and body["sections"] and body["notice"]
    assert conn.execute("select count(*) n from audit_logs where workspace_id=%s and action='report.export'", (wid,)).fetchone()["n"] == 3


def test_report_escapes_hostile_titles_and_blocks_other_workspaces(client, conn):
    _, _, h = H(conn)
    _, _, other = H(conn)
    sid = mk_scen(client, h, "business", {**BIZ, "title": "<script>alert(1)</script><img src=x onerror=alert(2)>"})
    html = client.get(f"/api/v1/library/report?type=scenario&id={sid}&format=html", headers=h).text
    assert "<script>alert(1)" not in html and "<img src=x" not in html and "&lt;script&gt;" in html
    for fmt in ("md", "html", "json"):
        assert client.get(f"/api/v1/library/report?type=scenario&id={sid}&format={fmt}", headers=other).status_code == 404
    assert client.get(f"/api/v1/library/report?type=scenario&id={sid}&format=pdf", headers=h).status_code == 422


def test_incomplete_simulation_report_is_refused(client, conn, monkeypatch):
    monkeypatch.setattr(simulation_api, "launch", lambda rid: None)
    _, _, h = H(conn)
    rid = mk_sim(client, h)
    assert client.get(f"/api/v1/library/report?type=simulation&id={rid}&format=md", headers=h).status_code == 409


def test_workspace_export_contains_only_this_workspace(client, conn, sync):
    _, wid, h = H(conn)
    _, _, other = H(conn)
    ids = populate(client, h)
    mk_scen(client, other, "business", {**BIZ, "title": "SECRET other workspace"})
    r = client.get("/api/v1/library/export", headers=h)
    assert r.status_code == 200 and "-export.json" in r.headers["content-disposition"]
    b = json.loads(r.text)
    assert b["format"] == "stratiq-workspace-export" and b["counts"] == {"predictions": 1, "scenarios": 3, "simulation_runs": 1}
    assert "SECRET" not in r.text and b["predictions"][0]["assumptions"] and b["predictions"][0]["model"] == "poisson-maher"
    assert {s["id"] for s in b["scenarios"]} == {ids["business"], ids["politics"], ids["finance"]}
    assert b["simulation_runs"][0]["result"]["result_hash"]
    assert conn.execute("select count(*) n from audit_logs where workspace_id=%s and action='workspace.export'", (wid,)).fetchone()["n"] == 1
    assert client.get("/api/v1/library/export").status_code == 401


# ------------------------------------------------------------------ workspaces
def test_create_list_and_activate_workspaces(client, conn):
    uid, wid, h = H(conn)
    r = client.post("/api/v1/workspaces", json={"name": "  Research  "}, headers=h)
    assert r.status_code == 201 and r.json()["name"] == "Research" and r.json()["role"] == "owner"
    new = r.json()["id"]
    lst = client.get("/api/v1/workspaces", headers=h).json()["workspaces"]
    assert {w["id"] for w in lst} == {wid, new} and [w["id"] for w in lst if w["active"]] == [new]
    # work saved in the new workspace is invisible from the old one and vice versa
    h_new = hdr(uid, new)
    sid = mk_scen(client, h_new, "business", BIZ)
    assert client.get(f"/api/v1/business/scenarios/{sid}", headers=h).status_code == 404
    assert client.get("/api/v1/library/items", headers=h).json()["items"] == []
    assert len(client.get("/api/v1/library/items", headers=h_new).json()["items"]) == 1
    assert client.post("/api/v1/workspaces/activate", json={"workspace_id": wid}, headers=h_new).status_code == 200
    assert [w["id"] for w in client.get("/api/v1/workspaces", headers=h).json()["workspaces"] if w["active"]] == [wid]
    assert conn.execute("select count(*) n from audit_logs where user_id=%s and action in ('workspace.create','workspace.switch')", (uid,)).fetchone()["n"] == 2


def test_cannot_activate_a_workspace_you_do_not_belong_to(client, conn):
    uid, wid, h = H(conn)
    _, other_ws, _ = H(conn)
    assert client.post("/api/v1/workspaces/activate", json={"workspace_id": other_ws}, headers=h).status_code == 403
    assert conn.execute("select active_workspace_id from users where id=%s", (uid,)).fetchone()["active_workspace_id"] is None
    assert client.post("/api/v1/workspaces/activate", json={"workspace_id": str(uuid.uuid4())}, headers=h).status_code == 403
    assert client.post("/api/v1/workspaces/activate", json={"workspace_id": "bad"}, headers=h).status_code == 422
    # a forged token naming a workspace the user is not in is still rejected before any of this
    assert client.get("/api/v1/workspaces", headers=hdr(uid, other_ws)).status_code == 403


def test_workspace_name_validation_and_listing_is_per_user(client, conn):
    uid, _, h = H(conn)
    for bad in ("", "   ", "x" * 121):
        assert client.post("/api/v1/workspaces", json={"name": bad}, headers=h).status_code == 422
    _, _, other = H(conn)
    client.post("/api/v1/workspaces", json={"name": "Mine"}, headers=h)
    assert all(w["name"] != "Mine" for w in client.get("/api/v1/workspaces", headers=other).json()["workspaces"])
