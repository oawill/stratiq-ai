"""SimLab across every store: version lineage and provenance on political and financial scenarios, one saved list, export, deletion, limits."""
import json

import pytest

from stratiq import simlab_api
from .conftest import hdr, make_user
from .test_business_api import PD as GAME
from .test_finance_api import MC, STRESS
from .test_politics_api import COALITION, TURNOUT


@pytest.fixture()
def ws(client, conn):
    uid, wid = make_user(conn)
    return hdr(uid, wid, exp_in=900), wid, uid


def api(client, h, method, path, body=None):
    return client.request(method, f"/api/v1/{path}", json=body, headers=h)


def pol(client, h, kind="coalition", inputs=COALITION, title="Coalition", **kw):
    return api(client, h, "POST", "politics/scenarios", {"kind": kind, "title": title, "inputs": inputs, **kw})


def fin(client, h, kind="montecarlo", inputs=MC, title="Portfolio", **kw):
    return api(client, h, "POST", "finance/scenarios", {"kind": kind, "title": title, "inputs": inputs, **kw})


# ------------------------------------------------------------------ lineage and provenance
def test_political_scenarios_record_provenance_and_a_version_chain(client, conn, ws):
    h, wid, _ = ws
    v1 = pol(client, h)
    assert v1.status_code == 201, v1.text
    a = v1.json()
    assert a["version"] == 1 and a["parent_id"] is None and len(a["scenario_key"]) == 36
    d = conn.execute("select definition from strategic_scenarios where id=%s", (a["id"],)).fetchone()["definition"]
    assert d["version"] == 1 and d["scenario_key"] == a["scenario_key"] and d["provenance"]["engine"] == "politics" and d["provenance"]["deterministic"] is True
    assert "not official results" in d["provenance"]["input_data"] and d["provenance"]["generated_at"]
    v2 = pol(client, h, based_on=a["id"]).json()
    v3 = pol(client, h, based_on=v2["id"]).json()
    assert (v2["version"], v3["version"]) == (2, 3) and v2["scenario_key"] == v3["scenario_key"] == a["scenario_key"] and v3["parent_id"] == v2["id"]
    rows = {r["id"]: r for r in api(client, h, "GET", "politics/scenarios").json()["scenarios"]}
    assert rows[v3["id"]]["version"] == 3 and rows[v3["id"]]["scenario_key"] == a["scenario_key"]
    assert pol(client, h, "turnout", TURNOUT, "Turnout", based_on=a["id"]).status_code == 404            # a different kind cannot continue the chain
    assert pol(client, h, based_on="00000000-0000-0000-0000-000000000000").status_code == 404
    other = hdr(*make_user(conn))
    assert pol(client, other, based_on=a["id"]).status_code == 404                                       # nor can another workspace


def test_financial_scenarios_record_the_seed_engine_version_and_chain(client, conn, ws):
    h, wid, _ = ws
    a = fin(client, h).json()
    d = conn.execute("select definition from strategic_scenarios where id=%s", (a["id"],)).fetchone()["definition"]
    assert d["provenance"]["engine"] == "finance" and d["provenance"]["engine_version"] and d["provenance"]["random_seed"] == 7 and "no market data is fetched" in d["provenance"]["input_data"]
    assert fin(client, h, "stress", STRESS, "Stress").json()["version"] == 1
    b = fin(client, h, based_on=a["id"]).json()
    assert b["version"] == 2 and b["scenario_key"] == a["scenario_key"]
    assert api(client, h, "GET", f"finance/scenarios/{b['id']}").json()["analysis"]["seed"] == 7        # still reproducible from the stored inputs


def test_a_monte_carlo_scenario_without_a_seed_gets_one_that_is_stored(client, conn, ws):
    h, wid, _ = ws
    no_seed = {k: v for k, v in MC.items() if k != "seed"}
    a = fin(client, h, inputs=no_seed).json()
    d = conn.execute("select definition from strategic_scenarios where id=%s", (a["id"],)).fetchone()["definition"]
    assert isinstance(d["provenance"]["random_seed"], int) and d["inputs"]["seed"] == d["provenance"]["random_seed"]


# ------------------------------------------------------------------ one saved list
def seed_everything(client, h, conn, wid):
    sports_run = None
    pol_id = pol(client, h).json()["id"]
    fin_id = fin(client, h).json()["id"]
    game = api(client, h, "POST", "business/scenarios", {**GAME, "title": "Pricing dilemma", "players": ["Acme", "Globex"]}).json()["id"]
    biz = api(client, h, "POST", "simlab/business/run", {"inputs": {"market_size": 1000, "adoption_rate": 0.2, "reference_price": 10, "price": 10, "unit_cost": 4, "demand_sensitivity": 1.5, "competitor_reaction": 0}}).json()["id"]
    return {"politics": pol_id, "markets": fin_id, "game": game, "pricing": biz, "sports": sports_run}


def test_saved_lists_every_domain_with_version_and_source_newest_first_and_stays_private(client, conn, ws):
    h, wid, _ = ws
    ids = seed_everything(client, h, conn, wid)
    rows = api(client, h, "GET", "simlab/saved").json()["runs"]
    by_id = {r["id"]: r for r in rows}
    assert {by_id[ids["politics"]]["domain"], by_id[ids["markets"]]["domain"], by_id[ids["game"]]["domain"], by_id[ids["pricing"]]["domain"]} == {"politics", "markets", "business"}
    assert by_id[ids["politics"]]["source"] == "scenario" and by_id[ids["pricing"]]["source"] == "run" and by_id[ids["politics"]]["kind"] == "coalition" and by_id[ids["markets"]]["kind"] == "montecarlo"
    assert by_id[ids["politics"]]["engine"].startswith("politics@") and by_id[ids["markets"]]["engine"].startswith("finance@") and by_id[ids["pricing"]]["engine"].startswith("business_sim@")
    assert [r["created_at"] for r in rows] == sorted((r["created_at"] for r in rows), reverse=True)
    assert [r["id"] for r in api(client, h, "GET", "simlab/saved?domain=markets").json()["runs"]] == [ids["markets"]]
    assert {r["domain"] for r in api(client, h, "GET", "simlab/saved?domain=business").json()["runs"]} == {"business"}
    assert len(api(client, h, "GET", "simlab/saved?limit=2").json()["runs"]) == 2
    other = hdr(*make_user(conn))
    assert api(client, other, "GET", "simlab/saved").json()["runs"] == []


def test_a_saved_scenario_opens_with_its_summary_notice_provenance_and_link(client, conn, ws):
    h, wid, _ = ws
    a = pol(client, h, notes="a note").json()
    g = api(client, h, "GET", f"simlab/scenarios/{a['id']}").json()
    assert g["domain"] == "politics" and g["kind"] == "coalition" and g["version"] == 1 and g["notes"] == "a note" and g["summary"]["total_seats"] == 100
    assert "Not a poll" in g["notice"] and g["module_href"] == "/dashboard/politics" and g["provenance"]["engine"] == "politics"
    m = api(client, h, "GET", f"simlab/scenarios/{fin(client, h).json()['id']}").json()
    assert m["domain"] == "markets" and "Not investment advice" in m["notice"] and m["module_href"] == "/dashboard/finance" and m["summary"]["iterations"] == 1000
    other = hdr(*make_user(conn))
    assert api(client, other, "GET", f"simlab/scenarios/{a['id']}").status_code == 404
    assert api(client, h, "GET", "simlab/scenarios/00000000-0000-0000-0000-000000000000").status_code == 404


def test_scenarios_export_as_csv_and_json_with_the_notice_and_provenance(client, conn, ws):
    h, wid, _ = ws
    a = pol(client, h, title="Coalition export").json()
    csv_r = api(client, h, "GET", f"simlab/scenarios/{a['id']}/export?format=csv")
    assert csv_r.status_code == 200 and "coalition-export-v1.csv" in csv_r.headers["content-disposition"]
    t = csv_r.text
    assert "Not a poll" in t and '""engine"": ""politics""' in t           # the provenance block is written as quoted JSON in one cell
    assert "total_seats,100" in t and "parties[0].name,A" in t
    js = api(client, h, "GET", f"simlab/scenarios/{a['id']}/export?format=json").json()
    assert js["domain"] == "politics" and js["version"] == 1 and js["inputs"]["parties"][0]["name"] == "A" and js["provenance"]["engine"] == "politics" and "Not a poll" in js["notice"]
    assert conn.execute("select count(*) n from audit_logs where workspace_id=%s and action='simlab.export'", (wid,)).fetchone()["n"] == 2
    assert api(client, h, "GET", f"simlab/scenarios/{a['id']}/export?format=pdf").status_code == 422
    other = hdr(*make_user(conn))
    assert api(client, other, "GET", f"simlab/scenarios/{a['id']}/export").status_code == 404


def test_a_scenario_saved_before_provenance_existed_still_lists_opens_and_exports(client, conn, ws):
    h, wid, uid = ws
    legacy = {"kind": "coalition", "inputs": COALITION, "notes": None, "summary": {"total_seats": 100, "seats_needed": 51}}
    sid = conn.execute("insert into strategic_scenarios (workspace_id, created_by, title, domain, definition) values (%s,%s,'Old one','politics',%s) returning id", (wid, uid, json.dumps(legacy))).fetchone()["id"]
    row = next(r for r in api(client, h, "GET", "simlab/saved").json()["runs"] if r["id"] == str(sid))
    assert row["version"] == 1 and row["scenario_key"] == str(sid) and row["engine"] is None
    assert api(client, h, "GET", f"simlab/scenarios/{sid}").json()["provenance"] is None
    assert "saved before provenance was recorded" in api(client, h, "GET", f"simlab/scenarios/{sid}/export").text
    v2 = pol(client, h, based_on=str(sid)).json()
    assert v2["version"] == 2 and v2["scenario_key"] == str(sid)                                         # an older scenario can start a chain


# ------------------------------------------------------------------ deletion and access
def test_deleting_a_scenario_follows_ownership_and_is_audited(client, conn, ws):
    h, wid, _ = ws
    sid = pol(client, h).json()["id"]
    viewer = hdr(make_user(conn, role="viewer", workspace_id=wid)[0], wid)
    member = hdr(make_user(conn, role="member", workspace_id=wid)[0], wid)
    admin = hdr(make_user(conn, role="admin", workspace_id=wid)[0], wid)
    assert api(client, viewer, "GET", f"simlab/scenarios/{sid}").status_code == 200               # any member can read
    assert api(client, viewer, "DELETE", f"simlab/scenarios/{sid}").status_code == 403
    assert api(client, member, "DELETE", f"simlab/scenarios/{sid}").status_code == 403
    other = hdr(*make_user(conn))
    assert api(client, other, "DELETE", f"simlab/scenarios/{sid}").status_code == 404
    assert api(client, admin, "DELETE", f"simlab/scenarios/{sid}").status_code == 204
    assert api(client, h, "GET", f"simlab/scenarios/{sid}").status_code == 404
    audit = conn.execute("select detail from audit_logs where workspace_id=%s and action='simlab.delete_scenario'", (wid,)).fetchone()["detail"]
    assert audit["scenario_id"] == sid and audit["domain"] == "politics"
    mine = fin(client, h).json()["id"]
    assert api(client, h, "DELETE", f"simlab/scenarios/{mine}").status_code == 204


def test_saving_political_and_financial_scenarios_is_rate_limited_together_with_runs(client, conn, ws, monkeypatch):
    h, wid, _ = ws
    monkeypatch.setattr(simlab_api, "RATE_PER_MINUTE", 3)
    assert [pol(client, h).status_code, fin(client, h).status_code, pol(client, h).status_code] == [201, 201, 201]
    r = fin(client, h)
    assert r.status_code == 429 and "Too many simulations" in r.json()["detail"]
    assert api(client, h, "POST", "simlab/business/run", {"inputs": {"market_size": 1000, "adoption_rate": 0.2, "reference_price": 10, "price": 10, "unit_cost": 4, "demand_sensitivity": 1.5, "competitor_reaction": 0}}).status_code == 429
    assert conn.execute("select count(*) n from strategic_scenarios where workspace_id=%s", (wid,)).fetchone()["n"] == 3
    viewer = hdr(make_user(conn, role="viewer", workspace_id=wid)[0], wid)
    assert pol(client, viewer).status_code == 403


def test_political_and_financial_saves_count_toward_the_plan_scenario_quota(client, conn, ws):
    from stratiq import plans
    h, wid, _ = ws
    before = plans.usage(conn, wid)["scenarios"]
    pol(client, h)
    fin(client, h)
    assert plans.usage(conn, wid)["scenarios"] == before + 2
