import random
import uuid

import pytest

from .conftest import hdr, make_user

PF = {
    "assets": [{"name": "Equity", "weight": 0.6, "mu": 0.07, "sigma": 0.18}, {"name": "Bonds", "weight": 0.4, "mu": 0.03, "sigma": 0.06}],
    "correlation": [[1, 0.2], [0.2, 1]], "initial_value": 100000,
}
MC = {**PF, "horizon_years": 1, "iterations": 1000, "seed": 7, "confidences": [0.95, 0.99], "loss_threshold": 0.1}
STRESS = {"assets": [{"name": "Equity", "weight": 0.6}, {"name": "Bonds", "weight": 0.4}], "initial_value": 100000,
          "scenarios": [{"name": "Equity -30%", "shocks": {"Equity": -0.3}}, {"name": "Rates up", "shocks": {"Bonds": -0.08, "Equity": -0.05}}], "reverse_target_loss": 0.15}


def series(seed, n=60):
    r = random.Random(seed)
    return [round(r.gauss(0.0004, 0.01), 6) for _ in range(n)]


HIST = {"series": {"A": series(1), "B": series(2)}, "weights": {"A": 0.5, "B": 0.5}, "periods_per_year": 252, "confidences": [0.95]}


def same(a, b):
    """Equal results ignoring wall-clock runtime."""
    a, b = dict(a), dict(b)
    a.pop("runtime_ms", None), b.pop("runtime_ms", None)
    return a == b


def H(conn):
    uid, wid = make_user(conn)
    return uid, wid, hdr(uid, wid)


# ------------------------------------------------------------------ auth, data sources, stateless
@pytest.mark.parametrize("path", ["portfolio", "montecarlo", "stress", "historical"])
def test_requires_auth(client, path):
    assert client.post(f"/api/v1/finance/{path}", json={}).status_code == 401
    assert client.get("/api/v1/finance/data-sources").status_code == 401


def test_data_sources_state_is_honest(client, conn, monkeypatch):
    _, _, h = H(conn)
    monkeypatch.delenv("FINANCE_DATA_PROVIDER", raising=False)
    d = client.get("/api/v1/finance/data-sources", headers=h).json()
    assert d["configured"] is False and d["automated_trading"] is False and "No market-data provider" in d["message"]
    monkeypatch.setenv("FINANCE_DATA_PROVIDER", "acme")  # naming a provider must not pretend it works
    assert client.get("/api/v1/finance/data-sources", headers=h).json()["configured"] is False


def test_portfolio_endpoint(client, conn):
    _, _, h = H(conn)
    r = client.post("/api/v1/finance/portfolio", json=PF, headers=h)
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["expected_return"] == pytest.approx(0.6 * 0.07 + 0.4 * 0.03) and 0 < a["volatility"] < 0.18
    assert sum(x["risk_contribution"] for x in a["assets"]) == pytest.approx(1) and "Not investment advice" in a["notice"]


@pytest.mark.parametrize(
    "mut",
    [
        {"correlation": [[1, 0.2], [0.3, 1]]},
        {"correlation": [[1, 1.5], [1.5, 1]]},
        {"assets": [{"name": "Equity", "weight": 0.9, "mu": 0.07, "sigma": 0.18}, {"name": "Bonds", "weight": 0.4, "mu": 0.03, "sigma": 0.06}]},
        {"assets": [{"name": "Equity", "weight": 1.2, "mu": 0.07, "sigma": 0.18}, {"name": "Bonds", "weight": -0.2, "mu": 0.03, "sigma": 0.06}]},
        {"assets": [{"name": "A", "weight": 0.5, "mu": 0.07, "sigma": 0.18}, {"name": "A", "weight": 0.5, "mu": 0.03, "sigma": 0.06}]},
        {"initial_value": 0},
    ],
)
def test_portfolio_validation(client, conn, mut):
    _, _, h = H(conn)
    assert client.post("/api/v1/finance/portfolio", json={**PF, **mut}, headers=h).status_code == 422


def test_montecarlo_endpoint_reproducible_and_bounded(client, conn):
    _, _, h = H(conn)
    r = client.post("/api/v1/finance/montecarlo", json=MC, headers=h)
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["seed"] == 7 and a["iterations"] == 1000 and len(a["fan"]) == 13 and a["p_loss_exceeds"]["threshold"] == 0.1
    assert a["risk"][1]["mc_es"] >= a["risk"][1]["mc_var"] >= a["risk"][0]["mc_var"] * 0.999
    assert same(a, client.post("/api/v1/finance/montecarlo", json=MC, headers=h).json())
    assert client.post("/api/v1/finance/montecarlo", json={**MC, "seed": None}, headers=h).json()["seed"] >= 0
    for bad in [{"iterations": 5}, {"horizon_years": 99}, {"steps_per_year": 7}, {"tails": "x"}, {"df": 1}, {"confidences": []}, {"loss_threshold": 5}]:
        assert client.post("/api/v1/finance/montecarlo", json={**MC, **bad}, headers=h).status_code == 422, bad


def test_oversized_montecarlo_is_rejected_not_attempted(client, conn):
    _, _, h = H(conn)
    n = 10
    big = {"assets": [{"name": f"a{i}", "weight": 0.1, "mu": 0.05, "sigma": 0.2} for i in range(n)],
           "correlation": [[1.0 if i == j else 0.1 for j in range(n)] for i in range(n)], "iterations": 20000, "horizon_years": 30, "steps_per_year": 52}
    r = client.post("/api/v1/finance/montecarlo", json=big, headers=h)
    assert r.status_code == 422 and "too large" in r.json()["detail"]


def test_stress_endpoint(client, conn):
    _, _, h = H(conn)
    r = client.post("/api/v1/finance/stress", json=STRESS, headers=h)
    assert r.status_code == 200, r.text
    a = r.json()
    s0 = a["scenarios"][0]
    assert s0["portfolio_return"] == pytest.approx(-0.18) and s0["pnl"] == pytest.approx(-18000) and a["worst"] == "Equity -30%"
    assert s0["scale_to_target"] == pytest.approx(0.15 / 0.18)
    assert client.post("/api/v1/finance/stress", json={**STRESS, "scenarios": [{"name": "x", "shocks": {"Gold": -0.1}}]}, headers=h).status_code == 422
    assert client.post("/api/v1/finance/stress", json={**STRESS, "scenarios": [{"name": "x", "shocks": {"Equity": -2}}]}, headers=h).status_code == 422


def test_historical_endpoint(client, conn):
    _, _, h = H(conn)
    r = client.post("/api/v1/finance/historical", json=HIST, headers=h)
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["provenance"].startswith("User-supplied") and a["risk"][0]["tail_observations"] == 3
    assert a["risk"][0]["warning"] is not None  # only 3 tail observations of 60
    for bad in [{"weights": {"A": 0.5}}, {"weights": {"A": 0.9, "B": 0.9}}, {"series": {"A": [0.01] * 5, "B": [0.01] * 5}},
                {"series": {"A": series(1), "B": series(2, 40)}}, {"periods_per_year": 0}]:
        assert client.post("/api/v1/finance/historical", json={**HIST, **bad}, headers=h).status_code == 422, bad
    nan = {**HIST, "series": {"A": [-1.0] + series(1)[1:], "B": series(2)}}
    assert client.post("/api/v1/finance/historical", json=nan, headers=h).status_code == 422  # a -100% return is rejected


# ------------------------------------------------------------------ saved scenarios
def save(client, h, kind, inputs, title="S"):
    r = client.post("/api/v1/finance/scenarios", json={"kind": kind, "title": title, "inputs": inputs, "notes": "n"}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_save_get_reproduces_and_audits(client, conn):
    _, wid, h = H(conn)
    sid = save(client, h, "montecarlo", {**MC, "seed": None}, "Balanced")
    a = client.get(f"/api/v1/finance/scenarios/{sid}", headers=h).json()
    b = client.get(f"/api/v1/finance/scenarios/{sid}", headers=h).json()
    assert a["inputs"]["seed"] is not None and same(a["analysis"], b["analysis"]) and a["kind"] == "montecarlo" and a["notes"] == "n"
    lst = client.get("/api/v1/finance/scenarios", headers=h).json()["scenarios"]
    assert [(s["title"], s["kind"]) for s in lst] == [("Balanced", "montecarlo")]
    assert client.get("/api/v1/finance/scenarios?kind=stress", headers=h).json()["scenarios"] == []
    assert conn.execute("select count(*) n from audit_logs where workspace_id=%s and action='financial_scenario.create'", (wid,)).fetchone()["n"] == 1
    # finance scenarios are invisible to the other modules
    for mod in ("business", "politics"):
        assert client.get(f"/api/v1/{mod}/scenarios", headers=h).json()["scenarios"] == []
        assert client.get(f"/api/v1/{mod}/scenarios/{sid}", headers=h).status_code == 404


def test_invalid_and_oversized_scenarios_rejected(client, conn):
    _, wid, h = H(conn)
    r = random.Random(1)
    huge = {"series": {f"a{i}": [round(r.gauss(0, 0.01), 5) for _ in range(2500)] for i in range(9)}, "weights": {f"a{i}": 1 / 9 for i in range(9)}}
    assert client.post("/api/v1/finance/scenarios", json={"kind": "historical", "title": "big", "inputs": huge}, headers=h).status_code == 422
    for body in [{"kind": "stress", "title": "x", "inputs": {}}, {"kind": "nope", "title": "x", "inputs": {}}, {"kind": "stress", "title": " ", "inputs": STRESS}]:
        assert client.post("/api/v1/finance/scenarios", json=body, headers=h).status_code == 422
    assert conn.execute("select count(*) n from strategic_scenarios where workspace_id=%s", (wid,)).fetchone()["n"] == 0


def test_isolation_roles_and_delete(client, conn):
    _, a_ws, ha = H(conn)
    _, _, hb = H(conn)
    sid = save(client, ha, "stress", STRESS)
    assert client.get(f"/api/v1/finance/scenarios/{sid}", headers=hb).status_code == 404
    assert client.delete(f"/api/v1/finance/scenarios/{sid}", headers=hb).status_code == 404
    assert client.get("/api/v1/finance/scenarios", headers=hb).json()["scenarios"] == []
    assert client.get(f"/api/v1/finance/scenarios/{uuid.uuid4()}", headers=ha).status_code == 404
    v_uid, _ = make_user(conn, role="viewer", workspace_id=a_ws)
    hv = hdr(v_uid, a_ws)
    assert client.post("/api/v1/finance/stress", json=STRESS, headers=hv).status_code == 200
    assert client.post("/api/v1/finance/scenarios", json={"kind": "stress", "title": "x", "inputs": STRESS}, headers=hv).status_code == 403
    assert client.delete(f"/api/v1/finance/scenarios/{sid}", headers=hv).status_code == 403
    m_uid, _ = make_user(conn, role="member", workspace_id=a_ws)
    assert client.delete(f"/api/v1/finance/scenarios/{sid}", headers=hdr(m_uid, a_ws)).status_code == 403
    assert client.delete(f"/api/v1/finance/scenarios/{sid}", headers=ha).status_code == 204


def test_compare_same_kind_only(client, conn):
    _, _, h = H(conn)
    m1 = save(client, h, "montecarlo", MC, "Base")
    riskier = {**MC, "assets": [{"name": "Equity", "weight": 0.9, "mu": 0.07, "sigma": 0.18}, {"name": "Bonds", "weight": 0.1, "mu": 0.03, "sigma": 0.06}]}
    m2 = save(client, h, "montecarlo", riskier, "Aggressive")
    s1 = save(client, h, "stress", STRESS, "Stress")
    save(client, h, "historical", HIST, "Hist")
    r = client.post("/api/v1/finance/compare", json={"ids": [m1, m2]}, headers=h)
    assert r.status_code == 200, r.text
    s = {x["title"]: x["summary"] for x in r.json()["scenarios"]}
    assert s["Aggressive"]["volatility"] > s["Base"]["volatility"] and s["Aggressive"]["risk"][0]["var"] > s["Base"]["risk"][0]["var"]
    assert client.post("/api/v1/finance/compare", json={"ids": [m1, s1]}, headers=h).status_code == 422
    assert client.post("/api/v1/finance/compare", json={"ids": [m1, m1]}, headers=h).status_code == 422
    _, _, other = H(conn)
    assert client.post("/api/v1/finance/compare", json={"ids": [m1, m2]}, headers=other).status_code == 404
