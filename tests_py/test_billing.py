"""Plan limits are enforced on the server, per workspace, and only when BILLING_ENFORCED=1."""
import uuid

import pytest

from stratiq import simulation_api
from .conftest import hdr, make_user
from .test_api import first_fixture
from .test_business_api import SCEN
from .test_simulation_api import RUN


@pytest.fixture()
def enforced(monkeypatch):
    monkeypatch.setenv("BILLING_ENFORCED", "1")
    monkeypatch.setattr(simulation_api, "launch", lambda rid: None)


def subscribe(conn, wid, plan, status="active"):
    conn.execute(
        """insert into subscriptions (workspace_id, plan, status, stripe_customer_id, stripe_subscription_id)
           values (%s,%s,%s,%s,%s)""",
        (wid, plan, status, f"cus_{uuid.uuid4().hex[:10]}", f"sub_{uuid.uuid4().hex[:10]}"),
    )


def test_not_enforced_by_default_everyone_has_full_access(client, conn, monkeypatch):
    monkeypatch.delenv("BILLING_ENFORCED", raising=False)
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    for _ in range(5):  # beyond the Explorer cap of 3
        assert client.post("/api/v1/business/scenarios", json=SCEN, headers=h).status_code == 201
    info = client.get("/api/v1/billing/plan", headers=h).json()
    assert info["plan"] == "strategy_pro" and info["enforced"] is False


def test_explorer_scenario_cap_then_upgrade_lifts_it(client, conn, enforced):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    assert client.get("/api/v1/billing/plan", headers=h).json()["plan"] == "explorer"
    for _ in range(3):
        assert client.post("/api/v1/business/scenarios", json=SCEN, headers=h).status_code == 201
    r = client.post("/api/v1/business/scenarios", json=SCEN, headers=h)
    assert r.status_code == 402 and r.json()["detail"]["code"] == "plan_limit"
    subscribe(conn, wid, "strategy_pro")
    assert client.post("/api/v1/business/scenarios", json=SCEN, headers=h).status_code == 201


def test_explorer_prediction_cap_and_sports_pro_unlocks_it(client, conn, enforced):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    f = first_fixture(client, h)
    for _ in range(10):
        assert client.post("/api/v1/sports/predictions", json={"fixture_id": f["id"]}, headers=h).status_code == 201
    assert client.post("/api/v1/sports/predictions", json={"fixture_id": f["id"]}, headers=h).status_code == 402
    subscribe(conn, wid, "sports_pro")
    assert client.post("/api/v1/sports/predictions", json={"fixture_id": f["id"]}, headers=h).status_code == 201
    # Sports Pro does not include Strategy Pro features.
    for _ in range(3):
        client.post("/api/v1/business/scenarios", json=SCEN, headers=h)
    assert client.post("/api/v1/business/scenarios", json=SCEN, headers=h).status_code == 402


def test_simulation_iteration_cap_and_run_cap(client, conn, enforced):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    assert client.post("/api/v1/simulations/runs", json={**RUN, "iterations": 50_000}, headers=h).status_code == 402
    for _ in range(3):
        assert client.post("/api/v1/simulations/runs", json={**RUN, "iterations": 1000}, headers=h).status_code == 201
    assert client.post("/api/v1/simulations/runs", json={**RUN, "iterations": 1000}, headers=h).status_code == 402
    subscribe(conn, wid, "strategy_pro")
    assert client.post("/api/v1/simulations/runs", json={**RUN, "iterations": 50_000}, headers=h).status_code == 201


def test_exports_are_strategy_pro_only(client, conn, enforced):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    assert client.get("/api/v1/library/export", headers=h).status_code == 402
    subscribe(conn, wid, "sports_pro")
    assert client.get("/api/v1/library/export", headers=h).status_code == 402
    conn.execute("update subscriptions set plan='strategy_pro' where workspace_id=%s", (wid,))
    assert client.get("/api/v1/library/export", headers=h).status_code == 200


@pytest.mark.parametrize("status,expected", [("active", "strategy_pro"), ("trialing", "strategy_pro"), ("past_due", "strategy_pro"),
                                             ("canceled", "explorer"), ("unpaid", "explorer"), ("incomplete", "explorer")])
def test_subscription_status_decides_the_plan(client, conn, enforced, status, expected):
    uid, wid = make_user(conn)
    subscribe(conn, wid, "strategy_pro", status)
    assert client.get("/api/v1/billing/plan", headers=hdr(uid, wid)).json()["plan"] == expected


def test_plans_are_per_workspace(client, conn, enforced):
    a_uid, a_ws = make_user(conn)
    b_uid, b_ws = make_user(conn)
    subscribe(conn, a_ws, "strategy_pro")
    assert client.get("/api/v1/billing/plan", headers=hdr(a_uid, a_ws)).json()["plan"] == "strategy_pro"
    assert client.get("/api/v1/billing/plan", headers=hdr(b_uid, b_ws)).json()["plan"] == "explorer"


def test_billing_endpoint_requires_auth(client):
    assert client.get("/api/v1/billing/plan").status_code == 401
