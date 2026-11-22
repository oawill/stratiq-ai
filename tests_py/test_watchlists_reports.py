"""Watchlists and the workspace evidence report. All data is SYNTHETIC (real club names, random scores)."""
from datetime import timedelta

import pytest

from .conftest import hdr, make_user
from .test_football_intel import FIVE, SPLIT, load, post

LAST = max(m[0] for m in FIVE)


def api(client, h, method, path, body=None):
    return client.request(method, f"/api/v1/{path}", json=body, headers=h)


@pytest.fixture()
def ws(client, conn):
    uid, wid = make_user(conn)
    return hdr(uid, wid, exp_in=900), wid, uid


def add_fixture(conn, wid, days_ahead=3, home="Arsenal", away="Chelsea"):
    from datetime import datetime, timezone
    d = datetime.now(timezone.utc).date() + timedelta(days=days_ahead)
    conn.execute("insert into football_fixtures (workspace_id, competition, season, fixture_date, home_team, away_team) values (%s,'EPL','2025/26',%s,%s,%s)", (wid, d, home, away))
    return d


# ------------------------------------------------------------------ watchlists
def test_requires_sign_in_and_history(client, ws):
    h, wid, _ = ws
    assert client.get("/api/v1/watchlists").status_code == 401
    assert api(client, h, "POST", "watchlists", {"kind": "team", "team": "Arsenal"}).status_code == 404
    assert api(client, h, "GET", "watchlists").json()["items"] == []
    assert api(client, h, "GET", "watchlists/options").json()["has_history"] is False


def test_watch_a_club_and_see_its_status_from_the_imported_matches(client, conn, ws):
    h, wid, _ = ws
    load(client, h, FIVE)
    opts = api(client, h, "GET", "watchlists/options").json()
    assert opts["has_history"] and "Arsenal" in opts["teams"]
    r = api(client, h, "POST", "watchlists", {"kind": "team", "team": "Arsenal"})
    assert r.status_code == 201
    again = api(client, h, "POST", "watchlists", {"kind": "team", "team": "Arsenal"})
    assert again.status_code == 201 and again.json()["id"] == r.json()["id"]          # adding twice does not duplicate
    items = api(client, h, "GET", "watchlists").json()["items"]
    assert len(items) == 1
    st = items[0]["status"]
    assert st["played"] > 100 and 1000 < st["elo"] < 2000 and len(st["recent"]) == 5
    assert all(x["result"] in "WDL" for x in st["recent"]) and st["recent"][0]["date"] >= st["recent"][-1]["date"]
    for x in st["recent"]:
        a, b = map(int, x["score"].split("-"))
        gf, ga = (a, b) if x["venue"] == "H" else (b, a)
        assert x["result"] == ("W" if gf > ga else "D" if gf == ga else "L")
    assert st["next_fixture"] is None and st["as_of"] == LAST.isoformat()


def test_watch_an_upcoming_fixture_gets_an_honest_labelled_forecast(client, conn, ws):
    h, wid, _ = ws
    load(client, h, FIVE)
    d = add_fixture(conn, wid)
    assert api(client, h, "POST", "watchlists", {"kind": "fixture", "home": "Arsenal", "away": "Chelsea", "date": (d + timedelta(days=1)).isoformat()}).status_code == 422   # not imported
    assert api(client, h, "POST", "watchlists", {"kind": "fixture", "home": "Arsenal", "away": "Chelsea"}).status_code == 422
    assert api(client, h, "POST", "watchlists", {"kind": "fixture", "home": "Arsenal", "away": "Chelsea", "date": d.isoformat()}).status_code == 201
    it = api(client, h, "GET", "watchlists").json()["items"][0]
    f = it["status"]
    assert abs(f["p_home"] + f["p_draw"] + f["p_away"] - 1) < 1e-6 and f["tuned"] is False and "no backtest" in f["note"] and "not a certainty" in f["note"]
    assert api(client, h, "POST", "watchlists", {"kind": "team", "team": "Arsenal"}).status_code == 201
    team = [i for i in api(client, h, "GET", "watchlists").json()["items"] if i["kind"] == "team"][0]
    assert team["status"]["next_fixture"] == {"date": d.isoformat(), "opponent": "Chelsea", "venue": "H"}


def test_unknown_clubs_are_rejected_and_the_list_is_capped(client, conn, ws):
    h, wid, _ = ws
    load(client, h, FIVE)
    assert api(client, h, "POST", "watchlists", {"kind": "team", "team": "Nowhere United"}).status_code == 422
    teams = api(client, h, "GET", "watchlists/options").json()["teams"]
    from stratiq import watchlist_api as wl
    for t in teams:
        assert api(client, h, "POST", "watchlists", {"kind": "team", "team": t}).status_code == 201
    assert len(teams) < wl.MAX_ITEMS
    monkey = wl.MAX_ITEMS
    wl.MAX_ITEMS = len(teams)
    try:
        conn.execute("insert into watchlist_items (workspace_id, user_id, kind, item_key, label) select workspace_id, user_id, 'team', 'x', 'x' from watchlist_items limit 1")
        assert api(client, h, "POST", "watchlists", {"kind": "competition"}).status_code == 422      # a new item is refused at the cap
        assert api(client, h, "POST", "watchlists", {"kind": "team", "team": teams[0]}).status_code == 201   # re-adding a watched one just updates it
    finally:
        wl.MAX_ITEMS = monkey


def test_watchlists_are_personal_and_private(client, conn, ws):
    h, wid, uid = ws
    load(client, h, FIVE)
    mine = api(client, h, "POST", "watchlists", {"kind": "team", "team": "Arsenal"}).json()["id"]
    mate_id, _ = make_user(conn, role="viewer", workspace_id=wid)
    mate = hdr(mate_id, wid)
    assert api(client, mate, "GET", "watchlists").json()["items"] == []                       # a teammate sees only their own list
    assert api(client, mate, "DELETE", f"watchlists/{mine}").status_code == 404                  # and cannot remove yours
    assert api(client, mate, "POST", "watchlists", {"kind": "team", "team": "Chelsea"}).status_code == 201     # a read-only role may keep a personal list
    other = hdr(*make_user(conn))
    assert api(client, other, "GET", "watchlists").json()["items"] == []
    assert api(client, h, "DELETE", f"watchlists/{mine}").status_code == 204
    assert api(client, h, "GET", "watchlists").json()["items"] == []


def test_a_played_fixture_shows_the_result_instead_of_a_forecast(client, conn, ws):
    h, wid, uid = ws
    load(client, h, FIVE)
    m = FIVE[-1]
    conn.execute("insert into football_fixtures (workspace_id, competition, season, fixture_date, home_team, away_team) values (%s,'EPL','2024/25',%s,%s,%s)", (wid, m[0], m[1], m[2]))
    conn.execute("insert into watchlist_items (workspace_id, user_id, kind, item_key, label) values (%s,%s,'fixture',%s,'x')", (wid, uid, f"{m[0].isoformat()}|{m[1]}|{m[2]}"))
    st = api(client, h, "GET", "watchlists").json()["items"][0]["status"]
    assert st["result"] == f"{m[3]}-{m[4]}" and "p_home" not in st


# ------------------------------------------------------------------ evidence report
def test_report_for_an_empty_workspace_claims_nothing(client, ws):
    h, wid, _ = ws
    r = api(client, h, "GET", "reports/evidence")
    assert r.status_code == 200
    j = r.json()
    assert j["data"]["matches"] == 0 and j["data"]["sources"] == [] and j["historical_evaluation"] == {"chronological": None, "rolling": None}
    assert j["forecasts"]["scored"] == [] and j["forecasts"]["waiting_for_results"] == 0 and j["saved_work"] == {"predictions": 0, "scenarios": 0, "simulations": 0}
    assert any("not betting" in s for s in j["statements"])


def test_report_separates_history_evaluation_from_forecasts_and_shows_provenance(client, conn, ws):
    h, wid, _ = ws
    assert client.get("/api/v1/reports/evidence").status_code == 401
    load(client, h, FIVE)
    j = api(client, h, "GET", "reports/evidence").json()
    assert j["data"]["matches"] == len(FIVE) and len(j["data"]["seasons"]) == 5 and len(j["data"]["data_sha256"]) == 64
    assert j["data"]["sources"] and j["data"]["sources"][0]["kind"] == "match_results" and j["data"]["sources"][0]["provider"] == "user_upload"
    assert j["historical_evaluation"]["chronological"] is None                 # history imported but nothing measured yet: no figures
    assert post(client, h, "intel/backtest", {"mode": "chronological", "split": SPLIT}).status_code == 200
    d = add_fixture(conn, wid, 2)
    post(client, h, "intel/match", {"home": "Arsenal", "away": "Chelsea", "kickoff": d.isoformat(), "save": True})
    j = api(client, h, "GET", "reports/evidence").json()
    ev = j["historical_evaluation"]["chronological"]
    assert ev["history_changed_since"] is False and ev["split"] == SPLIT and ev["data_sha256"] == j["data"]["data_sha256"]
    assert {m["model"] for m in ev["test"]} == {"Historical frequencies (baseline)", "Elo rating", "Dixon-Coles", "Boosted trees", "Calibrated ensemble"}
    assert all(m["matches"] == 380 and 0 < m["log_loss"] < 3 for m in ev["test"]) and ev["versions"] and ev["warnings"]
    assert j["forecasts"]["scored"] == [] and j["forecasts"]["waiting_for_results"] >= 1       # tracked forecasts exist but have no results yet
    # the report never invents a live accuracy: nothing is scored, so there is no live figure at all
    assert "accuracy" not in str(j["forecasts"]["scored"])


def test_report_flags_when_the_history_changed_after_a_backtest(client, conn, ws):
    h, wid, _ = ws
    load(client, h, FIVE)
    post(client, h, "intel/backtest", {"mode": "chronological", "split": SPLIT})
    conn.execute("delete from match_history where workspace_id=%s and match_date=(select max(match_date) from match_history where workspace_id=%s)", (wid, wid))
    ev = api(client, h, "GET", "reports/evidence").json()["historical_evaluation"]["chronological"]
    assert ev["history_changed_since"] is True


def test_report_is_private_to_the_workspace(client, conn, ws):
    h, wid, _ = ws
    load(client, h, FIVE)
    other = hdr(*make_user(conn))
    j = api(client, other, "GET", "reports/evidence").json()
    assert j["data"]["matches"] == 0 and j["data"]["sources"] == []
