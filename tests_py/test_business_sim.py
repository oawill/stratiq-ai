"""Business scenario model: formulas, validation, sensitivity, and the stored SimLab run. Every input is a hypothetical assumption."""
import math
import re

import pytest

from stratiq import business_sim as bs
from .conftest import hdr, make_user

BASE = {"market_size": 10_000, "adoption_rate": 0.2, "reference_price": 50.0, "price": 50.0, "unit_cost": 20.0, "demand_sensitivity": 2.0, "competitor_reaction": 0.0}


# ------------------------------------------------------------------ formulas
def test_at_the_reference_price_units_are_market_size_times_adoption():
    o = bs.outcome(BASE)
    assert o["units"] == pytest.approx(2000) and o["revenue"] == pytest.approx(100_000) and o["gross_profit"] == pytest.approx(60_000) and o["gross_margin"] == pytest.approx(0.6)


def test_constant_elasticity_demand_behaves_as_documented():
    doubled = bs.outcome(BASE, 100.0)
    assert doubled["units"] == pytest.approx(2000 / 4)                  # elasticity 2: doubling the price quarters the volume
    assert doubled["revenue"] == pytest.approx(100 * 500) and doubled["gross_profit"] == pytest.approx((100 - 20) * 500)
    assert bs.outcome({**BASE, "demand_sensitivity": 0.0}, 100.0)["units"] == pytest.approx(2000)       # zero sensitivity: volume ignores price
    assert bs.outcome({**BASE, "adoption_rate": 0.4})["units"] == pytest.approx(4000)


def test_competitor_reaction_mutes_the_volume_response_and_full_matching_removes_it():
    half = {**BASE, "competitor_reaction": 0.5}
    assert bs.effective_elasticity(half) == pytest.approx(1.0)
    assert bs.outcome(half, 100.0)["units"] == pytest.approx(2000 / 2)
    full = {**BASE, "competitor_reaction": 1.0}
    assert bs.effective_elasticity(full) == 0 and bs.outcome(full, 100.0)["units"] == pytest.approx(2000)


def test_the_documented_profit_maximising_price_really_maximises_gross_profit():
    opt = bs.optimal_price(BASE)                                         # e = 2 -> p* = c * e / (e - 1) = 40
    assert opt["exists"] and opt["price"] == pytest.approx(40.0)
    best = bs.outcome(BASE, 40.0)["gross_profit"]
    for p in (20.5, 30, 39, 41, 50, 80, 200):
        assert bs.outcome(BASE, p)["gross_profit"] < best
    x = {**BASE, "demand_sensitivity": 3.0, "competitor_reaction": 0.4, "unit_cost": 12.0}
    e = bs.effective_elasticity(x)
    assert bs.optimal_price(x)["price"] == pytest.approx(12.0 * e / (e - 1))


def test_without_enough_price_sensitivity_there_is_no_interior_best_price_and_the_model_says_so():
    low = bs.optimal_price({**BASE, "demand_sensitivity": 1.0})
    assert low["exists"] is False and low["price"] is None and "no interior best price" in low["note"]
    free = bs.optimal_price({**BASE, "unit_cost": 0.0})
    assert free["exists"] is False and "lowest price" in free["note"]


def test_gross_margin_is_undefined_not_infinite_when_there_is_no_revenue():
    assert bs.outcome({**BASE, "adoption_rate": 0.0})["gross_margin"] is None


# ------------------------------------------------------------------ sensitivity and sweeps
def test_sensitivity_moves_each_input_one_at_a_time_by_ten_percent():
    rows = {r["key"]: r for r in bs.sensitivity(BASE)}
    base = bs.outcome(BASE)
    mc = rows["unit_cost"]
    assert mc["low"]["value"] == pytest.approx(18.0) and mc["high"]["value"] == pytest.approx(22.0)
    assert mc["high"]["gross_profit_change"] == pytest.approx(-2.0 * 2000) and mc["low"]["gross_profit_change"] == pytest.approx(2.0 * 2000)
    assert mc["high"]["revenue_change"] == 0                                                   # a cost change does not move revenue
    ms = rows["market_size"]["high"]
    assert ms["revenue_change"] == pytest.approx(base["revenue"] * 0.1) and ms["gross_profit_change"] == pytest.approx(base["gross_profit"] * 0.1)
    assert rows["adoption_rate"]["high"]["revenue_change"] > 0
    assert rows["demand_sensitivity"]["high"]["revenue_change"] == 0                          # at the reference price the ratio is 1, so sensitivity cannot matter
    above = {r["key"]: r for r in bs.sensitivity({**BASE, "price": 60.0, "competitor_reaction": 0.3})}                    # priced above the reference: more sensitivity loses volume, rival matching restores it
    assert above["demand_sensitivity"]["high"]["revenue_change"] < 0 and above["competitor_reaction"]["high"]["revenue_change"] > 0
    order = [max((abs(s["gross_profit_change"]) for s in (r["low"], r["high"]) if s), default=0) for r in bs.sensitivity(BASE)]
    assert order == sorted(order, reverse=True)                                                 # biggest influence first


def test_inputs_at_a_boundary_are_only_moved_in_the_allowed_direction():
    rows = {r["key"]: r for r in bs.sensitivity({**BASE, "adoption_rate": 1.0, "competitor_reaction": 0.0})}
    assert rows["adoption_rate"]["high"] is None and rows["adoption_rate"]["low"]["value"] == pytest.approx(0.9)
    assert rows["competitor_reaction"]["low"] is None and rows["competitor_reaction"]["high"] is None      # 0 * 1.1 stays 0: nothing to move


def test_the_price_sweep_covers_half_to_one_and_a_half_times_the_price():
    sw = bs.price_sweep(BASE)
    assert len(sw) == bs.SWEEP_POINTS and sw[0]["price"] == pytest.approx(25.0) and sw[-1]["price"] == pytest.approx(75.0) and sw[5]["price"] == pytest.approx(50.0)
    assert [x["price"] for x in sw] == sorted(x["price"] for x in sw)


# ------------------------------------------------------------------ validation and scenarios
@pytest.mark.parametrize("key,val", [("market_size", 0), ("adoption_rate", 1.5), ("adoption_rate", -0.1), ("price", 0), ("unit_cost", -1), ("demand_sensitivity", 11),
                                     ("competitor_reaction", 1.2), ("price", float("nan")), ("price", float("inf")), ("market_size", True), ("price", "50")])
def test_invalid_inputs_are_rejected_with_a_named_message(key, val):
    with pytest.raises(ValueError, match=re.escape(bs.INPUTS[key][2])):
        bs.run({**BASE, key: val})


def test_missing_and_unknown_inputs_are_rejected():
    with pytest.raises(ValueError, match="required"):
        bs.run({k: v for k, v in BASE.items() if k != "unit_cost"})
    with pytest.raises(ValueError, match="Unknown"):
        bs.run({**BASE, "mystery": 1})


def test_scenarios_override_inputs_and_report_the_change_from_the_base_case():
    r = bs.run(BASE, [{"name": "Price cut", "overrides": {"price": 40.0}}, {"name": "Rival matches", "overrides": {"price": 40.0, "competitor_reaction": 1.0}}])
    base, cut, matched = r["base"], r["scenarios"][0], r["scenarios"][1]
    assert cut["overrides"] == {"price": 40.0} and cut["units"] > base["units"] and cut["change_vs_base"]["units"] == pytest.approx(cut["units"] - base["units"])
    assert matched["units"] == pytest.approx(2000) and matched["revenue"] < base["revenue"]            # a matched cut: no extra volume, lower revenue
    assert math.isclose(cut["change_vs_base"]["gross_profit"], cut["gross_profit"] - base["gross_profit"])
    assert bs.run(BASE, [{"name": "None", "overrides": {}}])["scenarios"][0]["change_vs_base"] == {"units": 0.0, "revenue": 0.0, "gross_profit": 0.0}
    with pytest.raises(ValueError, match="At most 3"):
        bs.run(BASE, [{"name": f"s{i}", "overrides": {}} for i in range(4)])
    with pytest.raises(ValueError, match="unique"):
        bs.run(BASE, [{"name": "a"}, {"name": "A"}])
    with pytest.raises(ValueError, match="Base case"):
        bs.run(BASE, [{"name": "base case"}])
    with pytest.raises(ValueError, match="Price"):
        bs.run(BASE, [{"name": "bad", "overrides": {"price": -5}}])


def test_the_result_is_labelled_hypothetical_deterministic_and_has_nothing_calibrated():
    r = bs.run(BASE)
    assert "HYPOTHETICAL" in r["label"] and "not financial or business advice" in r["label"] and r["calibrated_parameters"] == []
    assert "Nothing in this model is calibrated from data" in r["validation_status"] and r["provenance"]["random_seed"] is None and r["provenance"]["deterministic"] is True
    assert bs.run(BASE) == bs.run(BASE)


# ------------------------------------------------------------------ stored run
@pytest.fixture()
def ws(client, conn):
    uid, wid = make_user(conn)
    return hdr(uid, wid, exp_in=900), wid


def call(client, h, method, path, body=None):
    return client.request(method, f"/api/v1/simlab/{path}", json=body, headers=h)


def test_a_business_run_is_stored_versioned_listed_exported_and_private(client, conn, ws):
    h, wid = ws
    body = {"title": "Launch pricing", "inputs": BASE, "scenarios": [{"name": "Price cut", "overrides": {"price": 40}}]}
    r = call(client, h, "POST", "business/run", body)
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["version"] == 1 and j["base"]["gross_profit"] == pytest.approx(60_000) and j["provenance"]["generated_at"]
    row = conn.execute("select domain, model_name, model_version, seed, inputs from simlab_runs where id=%s", (j["id"],)).fetchone()
    assert row["domain"] == "business" and row["model_name"] == "business_sim" and row["seed"] is None and row["inputs"]["inputs"]["price"] == 50.0
    v2 = call(client, h, "POST", "business/run", {**body, "based_on": j["id"]}).json()
    assert v2["version"] == 2 and v2["scenario_key"] == j["scenario_key"]
    listing = call(client, h, "GET", "runs?domain=business").json()["runs"]
    assert len(listing) == 2 and listing[0]["gross_profit"] == pytest.approx(60_000) and call(client, h, "GET", "runs?domain=sports").json()["runs"] == []
    got = call(client, h, "GET", f"runs/{j['id']}").json()
    assert got["base"] == j["base"] and got["domain"] == "business"
    csv_text = call(client, h, "GET", f"runs/{j['id']}/export?format=csv")
    assert csv_text.status_code == 200 and "HYPOTHETICAL" in csv_text.text and "Price cut" in csv_text.text and "business_sim@" in csv_text.text
    assert call(client, h, "GET", f"runs/{j['id']}/export?format=html").status_code == 422
    other = hdr(*make_user(conn))
    assert call(client, other, "GET", f"runs/{j['id']}").status_code == 404 and call(client, other, "POST", "business/run", {**body, "based_on": j["id"]}).status_code == 404
    assert call(client, h, "POST", "business/run", {"inputs": BASE, "based_on": call(client, h, 'GET', 'runs').json()['runs'][0]['id']}).status_code == 201


def test_business_inputs_are_validated_and_viewers_cannot_run(client, conn, ws):
    h, wid = ws
    assert call(client, h, "POST", "business/run", {"inputs": {**BASE, "price": -1}}).status_code == 422
    assert call(client, h, "POST", "business/run", {"inputs": {k: v for k, v in BASE.items() if k != "price"}}).status_code == 422
    assert call(client, h, "POST", "business/run", {"inputs": BASE, "scenarios": [{"name": "x", "overrides": {"nonsense": 1}}]}).status_code == 422
    assert call(client, h, "GET", "business/inputs").json()["inputs"][0]["key"] == "market_size"
    viewer = hdr(make_user(conn, role="viewer", workspace_id=wid)[0], wid)
    assert call(client, viewer, "POST", "business/run", {"inputs": BASE}).status_code == 403
    assert conn.execute("select count(*) n from simlab_runs where workspace_id=%s", (wid,)).fetchone()["n"] == 0
