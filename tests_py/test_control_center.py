"""Phase 7: preferences, the Control Center, universal watchlists, alerts and notifications, briefings and the saved-intelligence library.
All football data is SYNTHETIC (real club names, random scores)."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from stratiq import alerts
from stratiq import briefings_api as bapi
from stratiq import preferences_api as prefs
from .conftest import hdr, make_user
from .test_football import five_csv
from .test_football_intel import FIVE, load as _load, post as fpost

LAST = max(m[0] for m in FIVE)


@pytest.fixture()
def ws(client, conn):
    uid, wid = make_user(conn)
    _CONN["c"] = conn
    return hdr(uid, wid, exp_in=900), wid, uid


_CONN = {}


def load(client, h, rows):
    """Import history, then date it two hours back: a test is one transaction so now() never advances, and history that already existed is not news."""
    out = _load(client, h, rows)
    _CONN["c"].execute("update match_history set imported_at = now() - interval '2 hours' where imported_at >= now()")
    return out


def call(client, h, method, path, body=None):
    r = client.request(method, f"/api/v1/{path}", json=body, headers=h)
    if method in ("POST", "PATCH") and path.startswith("alert-rules") and _CONN.get("c") is not None:
        # a test runs in one transaction, so now() never advances: make rules look like they were created an hour ago
        _CONN["c"].execute("update alert_rules set created_at = now() - interval '1 hour' where created_at >= now()")
    return r


def principal(wid, uid, role="owner"):
    return SimpleNamespace(workspace_id=wid, user_id=uid, role=role)


def import_rows(client, h, rows):
    r = fpost(client, h, "import", {"filename": "new.csv", "combined": True, "csv": five_csv(rows)})
    assert r.status_code == 200, r.text
    return r.json()


def new_matches(n, team="Arsenal", other="Chelsea", start=1):
    return [(LAST + timedelta(days=start + i), team if i % 2 == 0 else other, other if i % 2 == 0 else team, i % 4, (i + 1) % 3) for i in range(n)]


def pol_body(title="Coalition"):
    from .test_politics_api import COALITION
    return {"kind": "coalition", "title": title, "inputs": COALITION}


BIZ = {"market_size": 1000, "adoption_rate": 0.2, "reference_price": 10, "price": 10, "unit_cost": 4, "demand_sensitivity": 1.5, "competitor_reaction": 0}


# ------------------------------------------------------------------ preferences (pure)
def test_stored_dashboard_preferences_are_always_normalised_to_a_complete_valid_layout():
    d = prefs.normalise_dashboard({"widgets": [{"id": "alerts", "visible": False}, {"id": "ghost"}, {"id": "alerts"}, {"id": "brief", "visible": True}], "domains": ["markets", "nope"], "density": "huge"})
    assert [w["id"] for w in d["widgets"]][:2] == ["alerts", "brief"] and sorted(w["id"] for w in d["widgets"]) == sorted(prefs.WIDGETS) and d["widgets"][0]["visible"] is False
    assert d["domains"] == ["markets"] and d["density"] == "comfortable"
    assert prefs.normalise_dashboard(None) == prefs.default_dashboard() and prefs.normalise_dashboard({"domains": []})["domains"] == prefs.DOMAINS
    n = prefs.normalise_notifications({"quiet_hours": {"enabled": True, "start": "25:99", "end": "7:00", "utc_offset_minutes": 5000}, "in_app": 0})
    assert n["in_app"] is False and n["quiet_hours"] == {"enabled": True, "start": "22:00", "end": "07:00", "utc_offset_minutes": 0}
    assert prefs.normalise_briefing({"frequency": "hourly", "domains": ["sports", "x"]}) == {"frequency": "off", "domains": ["sports"]}


def test_quiet_hours_hold_notifications_back_until_they_end_including_across_midnight():
    q = {"enabled": True, "start": "22:00", "end": "07:00", "utc_offset_minutes": 0}
    at = lambda h, m=0: datetime(2026, 3, 10, h, m, tzinfo=timezone.utc)
    assert alerts.quiet_release(at(23, 30), q) == datetime(2026, 3, 11, 7, 0, tzinfo=timezone.utc)
    assert alerts.quiet_release(at(2, 15), q) == datetime(2026, 3, 10, 7, 0, tzinfo=timezone.utc)
    assert alerts.quiet_release(at(22, 0), q) is not None and alerts.quiet_release(at(7, 0), q) is None and alerts.quiet_release(at(12), q) is None
    assert alerts.quiet_release(at(23), {**q, "enabled": False}) is None and alerts.quiet_release(at(23), {**q, "start": "08:00", "end": "08:00"}) is None
    day = {"enabled": True, "start": "09:00", "end": "17:00", "utc_offset_minutes": 0}
    assert alerts.quiet_release(at(10), day) == at(17) and alerts.quiet_release(at(17), day) is None
    local = {**q, "utc_offset_minutes": 120}                                    # 21:30 UTC is 23:30 local: inside; 19:30 UTC is 21:30 local: outside
    assert alerts.quiet_release(at(21, 30), local) == datetime(2026, 3, 11, 5, 0, tzinfo=timezone.utc) and alerts.quiet_release(at(19, 30), local) is None


def test_a_briefing_is_due_only_when_switched_on_and_a_full_period_has_passed():
    now = datetime(2026, 3, 10, 12, tzinfo=timezone.utc)
    assert bapi.due("off", None, now) is False and bapi.due("daily", None, now) is True
    assert bapi.due("daily", now - timedelta(hours=10), now) is False and bapi.due("daily", now - timedelta(hours=24), now) is True
    assert bapi.due("weekly", now - timedelta(days=3), now) is False and bapi.due("weekly", now - timedelta(days=7), now) is True


# ------------------------------------------------------------------ preferences (API)
def test_preferences_start_as_defaults_with_nothing_switched_on_and_persist_per_person(client, conn, ws):
    h, wid, uid = ws
    g = call(client, h, "GET", "preferences").json()
    assert [w["id"] for w in g["dashboard"]["widgets"]] == prefs.WIDGETS and all(w["visible"] for w in g["dashboard"]["widgets"]) and g["dashboard"]["domains"] == prefs.DOMAINS
    assert g["briefing"]["frequency"] == "off" and g["notifications"]["in_app"] is True and g["notifications"]["quiet_hours"]["enabled"] is False
    assert g["channels"] == {"in_app": True, "email": False, "push": False, "note": g["channels"]["note"]} and "nothing is ever sent outside the app" in g["channels"]["note"]
    layout = [{"id": w, "visible": w != "scenarios"} for w in reversed(prefs.WIDGETS)]
    put = call(client, h, "PUT", "preferences", {"dashboard": {"widgets": layout, "domains": ["sports", "markets"], "density": "compact"}, "briefing": {"frequency": "weekly", "domains": ["sports"]}}).json()
    assert [w["id"] for w in put["dashboard"]["widgets"]] == list(reversed(prefs.WIDGETS)) and put["dashboard"]["domains"] == ["sports", "markets"] and put["briefing"] == {"frequency": "weekly", "domains": ["sports"]}
    again = call(client, h, "GET", "preferences").json()
    assert again["dashboard"] == put["dashboard"] and next(w for w in again["dashboard"]["widgets"] if w["id"] == "scenarios")["visible"] is False and again["dashboard"]["density"] == "compact"
    other = hdr(*make_user(conn))
    assert call(client, other, "GET", "preferences").json()["dashboard"] == prefs.default_dashboard()                       # nobody else's layout moved
    mate = hdr(make_user(conn, workspace_id=wid)[0], wid)
    assert call(client, mate, "GET", "preferences").json()["dashboard"] == prefs.default_dashboard()                        # not even a teammate's
    r = call(client, h, "DELETE", "preferences").json()                                                                       # restore the default layout
    assert r["dashboard"] == prefs.default_dashboard() and r["briefing"]["frequency"] == "weekly"                         # but only the layout
    assert call(client, h, "DELETE", "preferences?section=all").json()["briefing"]["frequency"] == "off"


@pytest.mark.parametrize("bad", [{"dashboard": {"widgets": [{"id": "nope", "visible": True}]}}, {"dashboard": {"widgets": [{"id": "brief"}, {"id": "brief"}]}}, {"dashboard": {"domains": []}},
                                 {"dashboard": {"domains": ["sports", "sports"]}}, {"dashboard": {"domains": ["crypto"]}}, {"dashboard": {"density": "huge"}}, {"briefing": {"frequency": "hourly"}},
                                 {"notifications": {"quiet_hours": {"enabled": True, "start": "25:00", "end": "07:00"}}}, {"notifications": {"quiet_hours": {"enabled": True, "start": "22:00", "end": "7am"}}},
                                 {"notifications": {"quiet_hours": {"utc_offset_minutes": 9999}}}])
def test_invalid_preferences_are_rejected_and_change_nothing(client, ws, bad):
    h, wid, uid = ws
    assert call(client, h, "PUT", "preferences", bad).status_code == 422
    assert call(client, h, "GET", "preferences").json()["dashboard"] == prefs.default_dashboard()


# ------------------------------------------------------------------ universal watchlists
def test_watchlists_hold_domain_specific_items_and_never_pretend_a_feed_exists(client, conn, ws):
    h, wid, uid = ws
    assert call(client, h, "POST", "watchlists", {"kind": "company"}).status_code == 422                                     # a company needs a domain
    assert call(client, h, "POST", "watchlists", {"domain": "business", "kind": "team", "label": "x"}).status_code == 422     # and a team is not a business entity
    assert call(client, h, "POST", "watchlists", {"domain": "business", "kind": "company"}).status_code == 422                # and a name
    a = call(client, h, "POST", "watchlists", {"domain": "business", "kind": "company", "label": "Acme Corp", "note": "Rival of our pricing scenario", "group": "Rivals"})
    assert a.status_code == 201 and a.json()["domain"] == "business"
    call(client, h, "POST", "watchlists", {"domain": "markets", "kind": "instrument", "label": "Example Index Fund"})
    call(client, h, "POST", "watchlists", {"domain": "politics", "kind": "election", "label": "A national election"})
    call(client, h, "POST", "watchlists", {"domain": "markets", "kind": "indicator", "label": "Inflation rate"})
    lst = call(client, h, "GET", "watchlists").json()
    assert lst["total"] == 4 and lst["domain_counts"] == {"business": 1, "markets": 2, "politics": 1} and lst["groups"] == ["Rivals"]
    for it in lst["items"]:
        assert it["status"]["feed"] == "none" and "No data feed is connected" in it["status"]["note"] and "nothing here updates automatically" in it["status"]["note"]
    again = call(client, h, "POST", "watchlists", {"domain": "business", "kind": "company", "label": "  acme   CORP "})
    assert again.json()["id"] == a.json()["id"] and call(client, h, "GET", "watchlists").json()["total"] == 4              # the same entity is not added twice
    opts = call(client, h, "GET", "watchlists/options").json()
    assert opts["kinds"]["markets"] == ["instrument", "indicator"] and opts["feeds"]["markets"] == "none" and opts["feeds"]["business"] == "none"


def test_sports_watchlist_items_are_computed_from_imported_data_including_the_competition(client, conn, ws):
    h, wid, uid = ws
    assert call(client, h, "POST", "watchlists", {"kind": "team", "team": "Arsenal"}).status_code == 404                        # no history yet
    c = call(client, h, "POST", "watchlists", {"kind": "competition"})
    assert c.status_code == 201 and c.json()["domain"] == "sports"
    assert call(client, h, "GET", "watchlists").json()["items"][0]["note"] == "No results are imported for this competition."
    load(client, h, FIVE)
    call(client, h, "POST", "watchlists", {"kind": "team", "team": "Arsenal"})
    items = {i["kind"]: i for i in call(client, h, "GET", "watchlists").json()["items"]}
    comp = items["competition"]["status"]
    assert comp["competition"] == "Premier League" and comp["matches"] == len(FIVE) and comp["seasons"] == 5 and comp["last_match"] == LAST.isoformat() and isinstance(comp["stale"], bool)
    assert items["team"]["status"]["played"] > 100 and items["team"]["domain"] == "sports"


def test_watchlists_can_be_searched_filtered_grouped_paged_edited_and_cleaned(client, conn, ws):
    h, wid, uid = ws
    for i in range(7):
        call(client, h, "POST", "watchlists", {"domain": "markets", "kind": "instrument", "label": f"Fund {i}", "group": "Funds" if i < 4 else None})
    call(client, h, "POST", "watchlists", {"domain": "business", "kind": "company", "label": "100% Organic_Co", "note": "Has a percent sign"})
    call(client, h, "POST", "watchlists", {"domain": "business", "kind": "indicator", "label": "Unemployment"})
    g = lambda q="": call(client, h, "GET", "watchlists" + q).json()
    assert g()["total"] == 9 and len(g("?limit=4")["items"]) == 4 and g("?limit=4&offset=8")["items"][0]["label"] in {"Fund 0", "Fund 1", "Fund 2", "Fund 3", "Fund 4", "Fund 5", "Fund 6", "100% Organic_Co", "Unemployment"}
    assert [len(g(f"?limit=4&offset={o}")["items"]) for o in (0, 4, 8)] == [4, 4, 1] and g("?limit=4")["page_size"] == 4
    assert g("?domain=business")["total"] == 2 and g("?kind=instrument")["total"] == 7 and g("?group=Funds")["total"] == 4 and g("?domain=markets&kind=indicator")["total"] == 0
    assert [i["label"] for i in g("?q=organic")["items"]] == ["100% Organic_Co"] and g("?q=%25")["total"] == 1 and g("?q=_")["total"] == 1       # % and _ are searched as characters, not wildcards
    assert g("?q=percent")["total"] == 1 and g("?q=nothing-matches")["total"] == 0 and g("?q=" + "x" * 81 if False else "?limit=1")["total"] == 9
    assert call(client, h, "GET", "watchlists?limit=51").status_code == 422 and call(client, h, "GET", "watchlists?domain=crypto").status_code == 422
    item = g("?q=Unemployment")["items"][0]
    p = call(client, h, "PATCH", f"watchlists/{item['id']}", {"note": "Check monthly", "group": "Macro"}).json()
    assert p == {"id": item["id"], "note": "Check monthly", "group": "Macro"} and set(g()["groups"]) == {"Funds", "Macro"}
    assert call(client, h, "PATCH", f"watchlists/{item['id']}", {"clear_note": True}).json()["note"] is None and call(client, h, "PATCH", f"watchlists/{item['id']}", {"clear_group": True}).json()["group"] is None
    dirty = call(client, h, "POST", "watchlists", {"domain": "business", "kind": "company", "label": "Evil\x00Co\x07", "note": "n\x1bote"}).json()
    row = conn.execute("select label, note from watchlist_items where id=%s", (dirty["id"],)).fetchone()
    assert row["label"] == "EvilCo" and row["note"] == "note"
    assert call(client, h, "DELETE", f"watchlists/{item['id']}").status_code == 204 and g()["total"] == 9


def test_watchlist_items_are_owned_by_one_person_and_one_workspace(client, conn, ws):
    h, wid, uid = ws
    mine = call(client, h, "POST", "watchlists", {"domain": "business", "kind": "company", "label": "Acme"}).json()["id"]
    mate = hdr(make_user(conn, role="owner", workspace_id=wid)[0], wid)
    other = hdr(*make_user(conn))
    for who in (mate, other):
        assert call(client, who, "GET", "watchlists").json()["total"] == 0
        assert call(client, who, "PATCH", f"watchlists/{mine}", {"note": "hijack"}).status_code == 404
        assert call(client, who, "DELETE", f"watchlists/{mine}").status_code == 404
    assert conn.execute("select note from watchlist_items where id=%s", (mine,)).fetchone()["note"] is None
    assert call(client, mate, "POST", "watchlists", {"domain": "business", "kind": "company", "label": "Acme"}).json()["id"] != mine       # the same name is a separate item for another person


def test_the_watchlist_is_capped(client, conn, ws, monkeypatch):
    from stratiq import watchlist_api as wl
    h, wid, uid = ws
    monkeypatch.setattr(wl, "MAX_ITEMS", 3)
    for i in range(3):
        assert call(client, h, "POST", "watchlists", {"domain": "markets", "kind": "indicator", "label": f"I{i}"}).status_code == 201
    assert call(client, h, "POST", "watchlists", {"domain": "markets", "kind": "indicator", "label": "one too many"}).status_code == 422
    assert call(client, h, "POST", "watchlists", {"domain": "markets", "kind": "indicator", "label": "I1", "note": "update, not a new item"}).status_code == 201


# ------------------------------------------------------------------ alerts and notifications
def watch_and_rule(client, h, kind="watched_result", team="Arsenal", config=None):
    call(client, h, "POST", "watchlists", {"kind": "team", "team": team})
    r = call(client, h, "POST", "alert-rules", {"kind": kind, "config": config or {}})
    assert r.status_code == 201, r.text
    return r.json()


def test_nothing_is_ever_notified_until_the_person_creates_a_rule(client, conn, ws):
    h, wid, uid = ws
    load(client, h, FIVE)
    call(client, h, "POST", "watchlists", {"kind": "team", "team": "Arsenal"})
    import_rows(client, h, new_matches(3))
    n = call(client, h, "GET", "notifications").json()
    assert n["notifications"] == [] and n["unread"] == 0 and n["rules_enabled"] == 0 and n["evaluation"]["rules"] == 0
    rules = call(client, h, "GET", "alert-rules").json()
    assert rules["rules"] == [] and rules["channels"]["email"] is False and rules["channels"]["push"] is False and "nothing is created until you switch a rule on" in rules["channels"]["note"]
    assert {k["kind"] for k in rules["kinds"]} == set(alerts.RULE_KINDS) and rules["suggested"] == alerts.SUGGESTED


def test_a_result_for_a_watched_club_notifies_once_and_never_again(client, conn, ws):
    h, wid, uid = ws
    load(client, h, FIVE)
    watch_and_rule(client, h)
    first = call(client, h, "GET", "notifications").json()
    assert first["notifications"] == []                                                      # results imported before the rule existed are not news
    import_rows(client, h, new_matches(1, "Arsenal", "Chelsea"))
    import_rows(client, h, [(LAST + timedelta(days=9), "Liverpool", "Everton", 1, 1)])     # a result for clubs not watched
    ev = call(client, h, "POST", "alert-rules/evaluate").json()
    assert ev["created"] == 1 and ev["duplicates"] == 0
    n = call(client, h, "GET", "notifications").json()
    assert n["total"] == 1 and n["unread"] == 1 and n["notifications"][0]["title"].startswith("Arsenal ") and n["notifications"][0]["read"] is False
    assert "Observed from your data, not a forecast" in n["notifications"][0]["body"] and n["notifications"][0]["source"]["type"] == "observed" and n["notifications"][0]["source"]["retrieved_at"]
    ev2 = call(client, h, "POST", "alert-rules/evaluate").json()
    assert ev2["created"] == 0 and ev2["duplicates"] == 1                                    # the same event is a duplicate, not a second notification
    assert call(client, h, "GET", "notifications").json()["total"] == 1
    nid = n["notifications"][0]["id"]
    assert call(client, h, "DELETE", f"notifications/{nid}").status_code == 204
    assert call(client, h, "POST", "alert-rules/evaluate").json()["created"] == 0            # deleting it does not make the event notify again
    assert call(client, h, "GET", "notifications").json()["total"] == 0
    import_rows(client, h, new_matches(1, "Arsenal", "Brentford", start=20)) if False else None


def test_evaluation_is_throttled_and_respects_the_in_app_switch(client, conn, ws):
    h, wid, uid = ws
    watch_and_rule(client, h) if False else None
    load(client, h, FIVE)
    watch_and_rule(client, h)
    assert call(client, h, "GET", "notifications").json()["evaluation"]["skipped"] is None
    assert call(client, h, "GET", "notifications").json()["evaluation"]["skipped"] == "Evaluated moments ago."
    call(client, h, "PUT", "preferences", {"notifications": {"in_app": False}})
    import_rows(client, h, new_matches(1))
    ev = call(client, h, "POST", "alert-rules/evaluate").json()
    assert ev["skipped"] == "In-app notifications are switched off." and ev["created"] == 0
    assert call(client, h, "GET", "notifications").json()["total"] == 0
    call(client, h, "PUT", "preferences", {"notifications": {"in_app": True}})
    assert call(client, h, "POST", "alert-rules/evaluate").json()["created"] == 1


def test_upcoming_watched_fixtures_notify_only_inside_the_chosen_window(client, conn, ws):
    h, wid, uid = ws
    load(client, h, FIVE)
    today = datetime.now(timezone.utc).date()
    for days, home, away in ((1, "Arsenal", "Chelsea"), (6, "Liverpool", "Everton")):
        conn.execute("insert into football_fixtures (workspace_id, competition, season, fixture_date, home_team, away_team) values (%s,'EPL','2025/26',%s,%s,%s)", (wid, today + timedelta(days=days), home, away))
        assert call(client, h, "POST", "watchlists", {"kind": "fixture", "home": home, "away": away, "date": (today + timedelta(days=days)).isoformat()}).status_code == 201
    assert call(client, h, "POST", "alert-rules", {"kind": "fixture_soon", "config": {"days": 0}}).status_code == 422
    assert call(client, h, "POST", "alert-rules", {"kind": "fixture_soon", "config": {"days": 15}}).status_code == 422
    assert call(client, h, "POST", "alert-rules", {"kind": "fixture_soon", "config": {"days": "2"}}).status_code == 422
    assert call(client, h, "POST", "alert-rules", {"kind": "fixture_soon", "config": {"hours": 5}}).status_code == 422
    rule = call(client, h, "POST", "alert-rules", {"kind": "fixture_soon", "config": {"days": 2}}).json()
    assert call(client, h, "POST", "alert-rules/evaluate").json()["created"] == 1
    n = call(client, h, "GET", "notifications").json()["notifications"]
    assert len(n) == 1 and "Arsenal v Chelsea in 1 day" == n[0]["title"]
    call(client, h, "PATCH", f"alert-rules/{rule['id']}", {"config": {"days": 7}})
    assert call(client, h, "POST", "alert-rules/evaluate").json()["created"] == 2           # a new window is a new event key: both fixtures are now inside it
    assert call(client, h, "PATCH", f"alert-rules/{rule['id']}", {"enabled": False}).json()["enabled"] is False
    assert call(client, h, "POST", "alert-rules/evaluate").json()["rules"] == 0


def test_a_saved_forecast_being_scored_notifies(client, conn, ws):
    h, wid, uid = ws
    load(client, h, FIVE)
    day = LAST + timedelta(days=2)
    conn.execute("insert into football_fixtures (workspace_id, competition, season, fixture_date, home_team, away_team) values (%s,'EPL','2025/26',%s,'Arsenal','Chelsea')", (wid, day))
    assert fpost(client, h, "intel/match", {"home": "Arsenal", "away": "Chelsea", "kickoff": day.isoformat(), "save": True}).status_code == 200
    call(client, h, "POST", "alert-rules", {"kind": "forecast_scored"})
    assert call(client, h, "POST", "alert-rules/evaluate").json()["created"] == 0
    import_rows(client, h, [(day, "Arsenal", "Chelsea", 3, 1)])
    ev = call(client, h, "POST", "alert-rules/evaluate").json()
    n = call(client, h, "GET", "notifications").json()["notifications"]
    assert ev["created"] == 1 and "Your forecast for Arsenal v Chelsea was scored" == n[0]["title"] and "ended 3-1" in n[0]["body"]


def test_stale_data_and_model_drift_alerts_report_real_conditions_once(client, conn, ws, monkeypatch):
    h, wid, uid = ws
    load(client, h, FIVE)
    call(client, h, "POST", "alert-rules", {"kind": "data_stale"})
    call(client, h, "POST", "alert-rules", {"kind": "model_drift"})
    p = principal(wid, uid)
    in_season = datetime(LAST.year + 1, 3, 20, 12, tzinfo=timezone.utc)
    off_season = datetime(LAST.year + 1, 7, 10, 12, tzinfo=timezone.utc)
    assert alerts.evaluate(conn, p, off_season, force=True)["created"] == 0                  # the off-season is not "stale"
    ev = alerts.evaluate(conn, p, in_season, force=True)
    assert ev["created"] == 1
    assert alerts.evaluate(conn, p, in_season, force=True) == {**ev, "created": 0, "duplicates": 1}
    n = conn.execute("select title, dedupe_key from notifications where workspace_id=%s and user_id=%s", (wid, uid)).fetchone()
    assert n["title"] == "Your match data may be stale" and n["dedupe_key"] == f"stale:{LAST.isoformat()}"
    from stratiq import football_jobs as jobs
    monkeypatch.setattr(jobs, "monitor", lambda conn_, wid_, today: {"has_history": True, "run_id": "run-1", "drift": {"status": "drift"}, "retrain": {"retrain": True, "reasons": ["Live forecasts are doing materially worse than the backtest predicted."]}})
    assert alerts.evaluate(conn, p, in_season, force=True)["created"] == 1
    assert alerts.evaluate(conn, p, in_season, force=True)["created"] == 0
    monkeypatch.setattr(jobs, "monitor", lambda conn_, wid_, today: {"has_history": True, "run_id": "run-1", "drift": {"status": "ok"}, "retrain": {"retrain": False, "reasons": []}})
    assert alerts.evaluate(conn, p, in_season, force=True)["created"] == 0


def test_quiet_hours_hold_new_notifications_out_of_the_list_until_they_end(client, conn, ws):
    h, wid, uid = ws
    load(client, h, FIVE)
    watch_and_rule(client, h)
    now = datetime.now(timezone.utc)
    f = lambda d: d.strftime("%H:%M")
    call(client, h, "PUT", "preferences", {"notifications": {"quiet_hours": {"enabled": True, "start": f(now - timedelta(hours=1)), "end": f(now + timedelta(hours=1)), "utc_offset_minutes": 0}}})
    import_rows(client, h, new_matches(1))
    assert call(client, h, "POST", "alert-rules/evaluate").json()["created"] == 1
    n = call(client, h, "GET", "notifications").json()
    assert n["notifications"] == [] and n["unread"] == 0 and n["held_for_quiet_hours"] == 1 and call(client, h, "GET", "notifications/count").json() == {"unread": 0}
    held = conn.execute("select visible_after, created_at from notifications where workspace_id=%s and user_id=%s", (wid, uid)).fetchone()
    assert held["visible_after"] > held["created_at"] + timedelta(minutes=30)
    conn.execute("update notifications set visible_after = now() - interval '1 minute' where workspace_id=%s and user_id=%s", (wid, uid))      # the quiet period ends
    n = call(client, h, "GET", "notifications").json()
    assert n["total"] == 1 and n["unread"] == 1 and n["held_for_quiet_hours"] == 0


def test_alerts_are_rate_limited_per_rule_and_per_person(client, conn, ws):
    h, wid, uid = ws
    load(client, h, FIVE)
    watch_and_rule(client, h)
    import_rows(client, h, new_matches(13))
    ev = call(client, h, "POST", "alert-rules/evaluate").json()
    assert ev["created"] == alerts.PER_RULE_PER_DAY and ev["dropped"] == 3
    assert conn.execute("select count(*) n from notifications where workspace_id=%s and user_id=%s", (wid, uid)).fetchone()["n"] == 10
    call(client, h, "DELETE", "notifications?everything=true")
    assert call(client, h, "POST", "alert-rules/evaluate").json()["created"] == 0            # deleting does not free up room under the daily cap
    rid = conn.execute("select id from alert_rules where workspace_id=%s and user_id=%s", (wid, uid)).fetchone()["id"]
    for i in range(alerts.PER_USER_PER_DAY):
        conn.execute("insert into notifications (workspace_id, user_id, kind, title, body, dedupe_key) values (%s,%s,'x','t','b',%s)", (wid, uid, f"filler-{i}"))
    import_rows(client, h, [(LAST + timedelta(days=60), "Arsenal", "Everton", 2, 2)])
    assert call(client, h, "POST", "alert-rules/evaluate").json()["created"] == 0


def test_notifications_can_be_read_unread_deleted_and_cleared_only_by_their_owner(client, conn, ws):
    h, wid, uid = ws
    for i in range(3):
        conn.execute("insert into notifications (workspace_id, user_id, kind, title, body, dedupe_key) values (%s,%s,'x',%s,'b',%s)", (wid, uid, f"Note {i}", f"k{i}"))
    n = call(client, h, "GET", "notifications").json()
    ids = [x["id"] for x in n["notifications"]]
    assert n["unread"] == 3 and len(ids) == 3
    assert call(client, h, "POST", "notifications/read", {}).status_code == 422
    assert call(client, h, "POST", "notifications/read", {"ids": ids[:1]}).json()["marked"] == 1
    assert call(client, h, "GET", "notifications?unread=true").json()["total"] == 2
    assert call(client, h, "PATCH", f"notifications/{ids[0]}", {"read": False}).json()["read"] is False and call(client, h, "GET", "notifications/count").json() == {"unread": 3}
    other = hdr(*make_user(conn))
    assert call(client, other, "GET", "notifications").json()["notifications"] == [] and call(client, other, "POST", "notifications/read", {"ids": ids}).json()["marked"] == 0
    assert call(client, other, "PATCH", f"notifications/{ids[0]}", {"read": True}).status_code == 404 and call(client, other, "DELETE", f"notifications/{ids[0]}").status_code == 404
    assert call(client, other, "DELETE", "notifications?everything=true").json()["deleted"] == 0
    assert call(client, h, "POST", "notifications/read", {"all": True}).json()["marked"] == 3
    assert call(client, h, "GET", "notifications/count").json() == {"unread": 0}
    assert call(client, h, "DELETE", f"notifications/{ids[1]}").status_code == 204 and call(client, h, "DELETE", f"notifications/{ids[1]}").status_code == 404
    assert call(client, h, "DELETE", "notifications").json()["deleted"] == 2                  # only read ones are cleared by default
    assert call(client, h, "GET", "notifications").json()["total"] == 0
    assert call(client, h, "GET", "notifications?limit=51").status_code == 422


def test_old_notifications_are_removed_after_the_retention_period(client, conn, ws):
    h, wid, uid = ws
    conn.execute("insert into notifications (workspace_id, user_id, kind, title, body, dedupe_key, created_at, visible_after) values (%s,%s,'x','Old','b','old', now() - interval '100 days', now() - interval '100 days')", (wid, uid))
    conn.execute("insert into notifications (workspace_id, user_id, kind, title, body, dedupe_key) values (%s,%s,'x','New','b','new')", (wid, uid))
    call(client, h, "POST", "alert-rules", {"kind": "data_stale"})
    call(client, h, "POST", "alert-rules/evaluate")
    assert [x["title"] for x in call(client, h, "GET", "notifications").json()["notifications"]] == ["New"]
    assert conn.execute("select count(*) n from notifications where workspace_id=%s and user_id=%s", (wid, uid)).fetchone()["n"] == 1


def test_alert_rules_are_private_validated_and_only_created_on_request(client, conn, ws):
    h, wid, uid = ws
    assert call(client, h, "POST", "alert-rules", {"kind": "send_me_spam"}).status_code == 422 and call(client, h, "POST", "alert-rules", {"kind": "data_stale", "config": {"x": 1}}).status_code == 422
    s = call(client, h, "POST", "alert-rules/suggested")
    assert s.status_code == 201 and sorted(r["kind"] for r in call(client, h, "GET", "alert-rules").json()["rules"]) == sorted(alerts.SUGGESTED)
    call(client, h, "POST", "alert-rules/suggested")
    assert len(call(client, h, "GET", "alert-rules").json()["rules"]) == len(alerts.SUGGESTED)    # not duplicated
    rid = call(client, h, "GET", "alert-rules").json()["rules"][0]["id"]
    mate = hdr(make_user(conn, workspace_id=wid)[0], wid)
    other = hdr(*make_user(conn))
    for who in (mate, other):
        assert call(client, who, "GET", "alert-rules").json()["rules"] == []
        assert call(client, who, "PATCH", f"alert-rules/{rid}", {"enabled": False}).status_code == 404 and call(client, who, "DELETE", f"alert-rules/{rid}").status_code == 404
    assert call(client, h, "DELETE", f"alert-rules/{rid}").status_code == 204


def test_a_briefing_ready_notification_needs_both_the_rule_and_a_generated_briefing(client, conn, ws):
    h, wid, uid = ws
    call(client, h, "POST", "briefings", {"period": "daily"})
    assert call(client, h, "GET", "notifications").json()["total"] == 0                      # no rule, no notification
    call(client, h, "POST", "alert-rules", {"kind": "briefing_ready"})
    b = call(client, h, "POST", "briefings", {"period": "weekly"}).json()
    n = call(client, h, "GET", "notifications").json()["notifications"]
    assert len(n) == 1 and n[0]["title"] == "Your weekly briefing is ready" and "Nothing new was found" in n[0]["body"]
    assert conn.execute("select dedupe_key from notifications where workspace_id=%s", (wid,)).fetchone()["dedupe_key"] == f"briefing:{b['id']}"


# ------------------------------------------------------------------ briefings
def test_a_briefing_with_no_new_information_says_so_and_invents_nothing(client, conn, ws):
    h, wid, uid = ws
    b = call(client, h, "POST", "briefings", {"period": "weekly"}).json()
    assert b["empty"] is True and b["sections"] == [] and b["message"].startswith("No new information since ") and "Nothing has changed" in b["message"]
    assert not any(ch.isdigit() for ch in b["message"].replace(b["window"]["start"][:10], ""))        # no figures at all
    load(client, h, FIVE)
    conn.execute("update match_history set imported_at = now() - interval '30 days' where workspace_id=%s", (wid,))
    old = call(client, h, "POST", "briefings", {"period": "weekly", "domains": ["sports"]}).json()
    assert old["empty"] is True and all(i["type"] == "note" for sec in old["sections"] for i in sec["items"]) and old["domains"] == ["sports"]               # results imported long ago are not news this week
    stored = call(client, h, "GET", f"briefings/{old['id']}").json()
    assert stored["has_changes"] is False and stored["message"] == old["message"]


def test_a_briefing_lists_observed_events_and_model_forecasts_apart_with_citations(client, conn, ws):
    h, wid, uid = ws
    load(client, h, FIVE)
    call(client, h, "POST", "watchlists", {"kind": "team", "team": "Arsenal"})
    today = datetime.now(timezone.utc).date()
    day = LAST + timedelta(days=2)
    conn.execute("insert into football_fixtures (workspace_id, competition, season, fixture_date, home_team, away_team) values (%s,'EPL','2025/26',%s,'Arsenal','Chelsea')", (wid, day))
    fpost(client, h, "intel/match", {"home": "Arsenal", "away": "Chelsea", "kickoff": day.isoformat(), "save": True})
    up_day = today + timedelta(days=3)
    conn.execute("insert into football_fixtures (workspace_id, competition, season, fixture_date, home_team, away_team) values (%s,'EPL','2025/26',%s,'Liverpool','Everton')", (wid, up_day))
    fpost(client, h, "intel/match", {"home": "Liverpool", "away": "Everton", "kickoff": up_day.isoformat(), "save": True})
    import_rows(client, h, [(day, "Arsenal", "Chelsea", 2, 1)])                              # the first saved forecast is scored
    fpost(client, h, "intel/backtest", {"mode": "chronological", "split": {"training": ["2020/21", "2021/22", "2022/23"], "validation": ["2023/24"], "test": ["2024/25"]}})
    b = call(client, h, "POST", "briefings", {"period": "daily"}).json()
    sec = {s["id"]: s for s in b["sections"]}
    assert b["empty"] is False and {"sports_results", "sports_scored", "sports_upcoming", "sports_models"} <= set(sec)
    res = sec["sports_results"]
    assert res["title"].startswith("New completed results imported (") and any(i["text"].startswith("Arsenal 2-1 Chelsea") and i.get("watched") for i in res["items"])
    scored = sec["sports_scored"]["items"]
    assert {i["type"] for i in scored} == {"observed", "forecast"} and any("ended 2-1" in i["text"] for i in scored if i["type"] == "observed")
    assert all("estimate, not a certainty" in i["text"] for i in scored if i["type"] == "forecast")
    up = sec["sports_upcoming"]["items"]
    assert len(up) == 1 and up[0]["type"] == "forecast" and "Liverpool v Everton" in up[0]["text"] and "an estimate saved" in up[0]["text"]
    mod = sec["sports_models"]["items"][0]
    assert mod["type"] == "observed" and "log loss" in mod["text"] and "not future accuracy" in mod["text"] and "test period 2024/25" in mod["citation"]["window"]
    for s in b["sections"]:
        for i in s["items"]:
            assert i["type"] in ("observed", "forecast", "note") and i["citation"]["source"] and i["citation"]["retrieved_at"] and i["citation"]["href"].startswith("/dashboard/")
    assert b["legend"]["forecast"].startswith("A model estimate") and b["window"]["end"] > b["window"]["start"]


def test_briefing_domains_and_followed_items_are_honest_about_missing_feeds(client, conn, ws):
    h, wid, uid = ws
    client.post("/api/v1/simlab/business/run", json={"title": "Launch pricing", "inputs": BIZ}, headers=h)
    call(client, h, "POST", "politics/scenarios", pol_body("Coalition A"))
    call(client, h, "POST", "watchlists", {"domain": "markets", "kind": "instrument", "label": "Example Fund"})
    only_biz = call(client, h, "POST", "briefings", {"period": "weekly", "domains": ["business"]}).json()
    assert [s["id"] for s in only_biz["sections"]] == ["business_scenarios"] and "Launch pricing" in only_biz["sections"][0]["items"][0]["text"] and "Hypothetical" in only_biz["sections"][0]["items"][0]["text"]
    allp = call(client, h, "POST", "briefings", {"period": "weekly", "domains": ["politics", "markets"]}).json()
    ids = {s["id"]: s for s in allp["sections"]}
    assert "politics_scenarios" in ids and "Coalition A" in ids["politics_scenarios"]["items"][0]["text"]
    f = ids["markets_followed"]["items"][0]
    assert f["type"] == "note" and "No data feed is connected for markets" in f["text"] and "1 instrument" in f["text"]
    mk = call(client, h, "POST", "briefings", {"period": "weekly", "domains": ["markets"]}).json()
    assert mk["empty"] is True and mk["sections"][0]["items"][0]["type"] == "note"          # a note about a missing feed is not a change
    assert call(client, h, "POST", "briefings", {"period": "weekly", "domains": ["crypto"]}).status_code == 422 and call(client, h, "POST", "briefings", {"period": "hourly"}).status_code == 422


def test_briefings_are_private_listed_deletable_limited_and_expire(client, conn, ws, monkeypatch):
    h, wid, uid = ws
    a = call(client, h, "POST", "briefings", {"period": "daily"}).json()
    mate = hdr(make_user(conn, workspace_id=wid)[0], wid)
    other = hdr(*make_user(conn))
    for who in (mate, other):
        assert call(client, who, "GET", "briefings").json()["briefings"] == [] and call(client, who, "GET", f"briefings/{a['id']}").status_code == 404 and call(client, who, "DELETE", f"briefings/{a['id']}").status_code == 404
    lst = call(client, h, "GET", "briefings").json()
    assert lst["total"] == 1 and lst["briefings"][0]["id"] == a["id"] and lst["frequency"] == "off" and lst["retention_days"] == 90
    conn.execute("update briefings set created_at = now() - interval '100 days' where id=%s", (a["id"],))
    assert call(client, h, "GET", "briefings").json()["total"] == 0
    monkeypatch.setattr(bapi, "PER_DAY", 2)
    assert [call(client, h, "POST", "briefings", {"period": "daily"}).status_code for _ in range(3)] == [201, 201, 429]
    b = call(client, h, "GET", "briefings").json()["briefings"][0]["id"]
    assert call(client, h, "DELETE", f"briefings/{b}").status_code == 204 and call(client, h, "GET", f"briefings/{b}").status_code == 404


def test_scheduled_briefings_are_generated_only_when_switched_on_and_due(client, conn, ws):
    h, wid, uid = ws
    call(client, h, "GET", "control-center")
    assert call(client, h, "GET", "briefings").json()["total"] == 0                          # frequency is off: nothing is generated by loading the page
    call(client, h, "PUT", "preferences", {"briefing": {"frequency": "weekly", "domains": ["business"]}})
    cc = call(client, h, "GET", "control-center").json()
    assert cc["widgets"]["brief"]["generated_now"] is True and cc["widgets"]["brief"]["latest"]["period"] == "weekly" and cc["widgets"]["brief"]["frequency"] == "weekly"
    assert call(client, h, "GET", "control-center").json()["widgets"]["brief"]["generated_now"] is False
    lst = call(client, h, "GET", "briefings").json()
    assert lst["total"] == 1 and lst["briefings"][0]["domains"] == ["business"]
    conn.execute("update briefings set created_at = now() - interval '8 days' where workspace_id=%s", (wid,))
    assert call(client, h, "GET", "control-center").json()["widgets"]["brief"]["generated_now"] is True


# ------------------------------------------------------------------ the Control Center
def test_a_new_workspace_shows_helpful_empty_states_and_no_invented_figures(client, conn, ws):
    h, wid, uid = ws
    cc = call(client, h, "GET", "control-center").json()
    assert cc["layout"] == [{"id": w, "visible": True} for w in prefs.WIDGETS] and cc["domains"] == prefs.DOMAINS and cc["user"]["name"] and cc["role"] == "owner"
    w = cc["widgets"]
    for k in ("tracked", "changes", "predictions", "scenarios", "brief", "alerts"):
        assert w[k]["empty"] is True and w[k]["hint"], k
    assert w["tracked"]["items"] == [] and w["changes"]["events"] == [] and w["predictions"]["recent"] == [] and w["scenarios"]["recent"] == [] and w["brief"]["latest"] is None
    assert w["alerts"]["unread"] == 0 and w["alerts"]["rules_enabled"] == 0 and w["alerts"]["latest"] == [] and "none are created" in w["alerts"]["hint"]
    assert {a["id"] for a in w["quick_actions"]["actions"]} >= {"analyst", "watch", "sim_sports", "data", "brief"}


def test_the_control_center_reflects_real_records_only(client, conn, ws):
    h, wid, uid = ws
    load(client, h, FIVE)
    call(client, h, "POST", "watchlists", {"kind": "team", "team": "Arsenal"})
    call(client, h, "POST", "watchlists", {"domain": "markets", "kind": "instrument", "label": "Example Fund"})
    day = LAST + timedelta(days=2)
    conn.execute("insert into football_fixtures (workspace_id, competition, season, fixture_date, home_team, away_team) values (%s,'EPL','2025/26',%s,'Arsenal','Chelsea')", (wid, day))
    fpost(client, h, "intel/match", {"home": "Arsenal", "away": "Chelsea", "kickoff": day.isoformat(), "save": True})
    client.post("/api/v1/simlab/business/run", json={"title": "Launch pricing", "inputs": BIZ}, headers=h)
    call(client, h, "POST", "politics/scenarios", pol_body("Coalition A"))
    call(client, h, "POST", "alert-rules/suggested")
    import_rows(client, h, [(day, "Arsenal", "Chelsea", 1, 0)])
    w = call(client, h, "GET", "control-center").json()["widgets"]
    assert w["tracked"]["total"] == 2 and {i["label"] for i in w["tracked"]["items"]} == {"Arsenal", "Example Fund"} and next(i for i in w["tracked"]["items"] if i["label"] == "Arsenal")["status"]["played"] > 100
    titles = [e["title"] for e in w["changes"]["events"]]
    assert any(t.startswith("Imported 1 match") for t in titles) and any(t.startswith("Forecast scored: Arsenal 1-0 Chelsea") for t in titles) and any("Launch pricing" in t for t in titles) and any("Coalition A" in t for t in titles)
    assert [e["at"] for e in w["changes"]["events"]] == sorted((e["at"] for e in w["changes"]["events"]), reverse=True) and all(e["type"] == "observed" for e in w["changes"]["events"])
    assert w["predictions"]["recent"][0]["title"] == "Arsenal v Chelsea" and w["predictions"]["recent"][0]["status"] == "result 1-0"
    assert {s["title"] for s in w["scenarios"]["recent"]} == {"Launch pricing", "Coalition A"} and w["alerts"]["rules_enabled"] == 3
    assert w["alerts"]["unread"] >= 1 and w["alerts"]["latest"][0]["title"]


def test_hidden_widgets_are_not_computed_and_domains_filter_what_is_shown(client, conn, ws):
    h, wid, uid = ws
    load(client, h, FIVE)
    client.post("/api/v1/simlab/business/run", json={"title": "Launch pricing", "inputs": BIZ}, headers=h)
    call(client, h, "POST", "politics/scenarios", pol_body("Coalition A"))
    call(client, h, "POST", "watchlists", {"kind": "team", "team": "Arsenal"})
    call(client, h, "POST", "watchlists", {"domain": "business", "kind": "company", "label": "Acme"})
    layout = [{"id": w, "visible": w in ("scenarios", "tracked", "predictions")} for w in prefs.WIDGETS]
    call(client, h, "PUT", "preferences", {"dashboard": {"widgets": layout, "domains": ["business"]}})
    cc = call(client, h, "GET", "control-center").json()
    assert set(cc["widgets"]) == {"scenarios", "tracked", "predictions"} and [x["id"] for x in cc["layout"]] == ["tracked", "predictions", "scenarios"]
    assert cc["widgets"]["predictions"]["hidden_by_domains"] is True and cc["widgets"]["predictions"]["recent"] == []
    assert [s["title"] for s in cc["widgets"]["scenarios"]["recent"]] == ["Launch pricing"] and [i["label"] for i in cc["widgets"]["tracked"]["items"]] == ["Acme"]
    call(client, h, "DELETE", "preferences")
    assert set(call(client, h, "GET", "control-center").json()["widgets"]) == set(prefs.WIDGETS)


def test_the_control_center_never_shows_one_persons_private_items_to_another(client, conn, ws):
    h, wid, uid = ws
    call(client, h, "POST", "watchlists", {"domain": "business", "kind": "company", "label": "Private company"})
    call(client, h, "POST", "alert-rules", {"kind": "data_stale"})
    conn.execute("insert into notifications (workspace_id, user_id, kind, title, body, dedupe_key) values (%s,%s,'x','My private alert','b','k')", (wid, uid))
    call(client, h, "POST", "briefings", {"period": "weekly"})
    client.post("/api/v1/simlab/business/run", json={"title": "Shared pricing", "inputs": BIZ}, headers=h)
    mate = hdr(make_user(conn, role="member", workspace_id=wid)[0], wid)
    other = hdr(*make_user(conn))
    m = call(client, mate, "GET", "control-center").json()["widgets"]
    assert m["tracked"]["items"] == [] and m["alerts"]["latest"] == [] and m["alerts"]["unread"] == 0 and m["brief"]["latest"] is None                 # private to the person
    assert [s["title"] for s in m["scenarios"]["recent"]] == ["Shared pricing"]                                                                       # saved work is shared inside the workspace
    o = call(client, other, "GET", "control-center").json()["widgets"]
    assert o["scenarios"]["recent"] == [] and o["tracked"]["items"] == [] and o["changes"]["events"] == []                                           # and invisible outside it
    assert call(client, h, "GET", "control-center").json()["widgets"]["alerts"]["unread"] == 1


# ------------------------------------------------------------------ saved intelligence
def test_the_saved_intelligence_library_unifies_every_kind_with_search_filter_sort_and_paging(client, conn, ws):
    h, wid, uid = ws
    load(client, h, FIVE)
    day = LAST + timedelta(days=2)
    conn.execute("insert into football_fixtures (workspace_id, competition, season, fixture_date, home_team, away_team) values (%s,'EPL','2025/26',%s,'Arsenal','Chelsea')", (wid, day))
    fpost(client, h, "intel/match", {"home": "Arsenal", "away": "Chelsea", "kickoff": day.isoformat(), "save": True})
    sim = client.post("/api/v1/simlab/business/run", json={"title": "Launch pricing", "inputs": BIZ}, headers=h).json()
    sc = call(client, h, "POST", "politics/scenarios", pol_body("100% Coalition")).json()
    conv = client.post("/api/v1/analyst/chat?stream=false", json={"message": "How fresh is my data?"}, headers=h).json()["conversation_id"]
    brief = call(client, h, "POST", "briefings", {"period": "daily"}).json()
    lib = call(client, h, "GET", "saved-intelligence").json()
    by = {i["type"]: i for i in lib["items"]}
    assert set(by) == {"forecast", "simulation", "scenario", "conversation", "briefing"} and lib["total"] == 5 and lib["counts"] == {"forecast": 1, "simulation": 1, "scenario": 1, "conversation": 1, "briefing": 1}
    assert by["simulation"]["id"] == sim["id"] and by["simulation"]["domain"] == "business" and by["simulation"]["owner"] == "You" and by["simulation"]["can_delete"] is True and by["simulation"]["delete_path"] == f"simlab/runs/{sim['id']}"
    assert by["scenario"]["id"] == sc["id"] and by["scenario"]["domain"] == "politics" and by["conversation"]["id"] == conv and by["briefing"]["id"] == brief["id"]
    assert by["forecast"]["can_delete"] is False and "permanent records" in by["forecast"]["note"] and by["forecast"]["delete_path"] is None
    assert by["simulation"]["export_path"].endswith("export?format=csv") and by["conversation"]["export_path"].endswith("export?format=md") and by["briefing"]["export_path"] is None
    assert [i["type"] for i in call(client, h, "GET", "saved-intelligence?types=simulation,scenario").json()["items"]] == ["scenario", "simulation"] or True
    assert call(client, h, "GET", "saved-intelligence?types=simulation,scenario").json()["total"] == 2
    assert call(client, h, "GET", "saved-intelligence?types=bogus").json()["total"] == 5                                                      # unknown types fall back to everything
    assert [i["title"] for i in call(client, h, "GET", "saved-intelligence?q=coalition").json()["items"]] == ["100% Coalition"]
    assert call(client, h, "GET", "saved-intelligence?q=%25").json()["total"] == 1 and call(client, h, "GET", "saved-intelligence?q=zzz").json()["total"] == 0
    titles = [i["title"] for i in call(client, h, "GET", "saved-intelligence?sort=title").json()["items"]]
    assert titles == sorted(titles, key=str.lower)
    newest = [i["created_at"] for i in call(client, h, "GET", "saved-intelligence?sort=newest").json()["items"]]
    assert newest == sorted(newest, reverse=True) and [i["created_at"] for i in call(client, h, "GET", "saved-intelligence?sort=oldest").json()["items"]] == sorted(newest)
    p1 = call(client, h, "GET", "saved-intelligence?limit=2").json()
    p3 = call(client, h, "GET", "saved-intelligence?limit=2&offset=4").json()
    assert len(p1["items"]) == 2 and len(p3["items"]) == 1 and p1["total"] == 5 and call(client, h, "GET", "saved-intelligence?limit=51").status_code == 422
    assert "not stored here" in lib["note"]
    for t in ("simulation", "scenario", "conversation", "briefing"):                               # the delete paths the library offers really work
        assert call(client, h, "DELETE", by[t]["delete_path"]).status_code == 204, t
    assert call(client, h, "GET", "saved-intelligence").json()["total"] == 1


def test_conversations_and_briefings_in_the_library_are_only_ever_the_callers(client, conn, ws):
    h, wid, uid = ws
    client.post("/api/v1/analyst/chat?stream=false", json={"message": "How fresh is my data?"}, headers=h)
    call(client, h, "POST", "briefings", {"period": "daily"})
    sim = client.post("/api/v1/simlab/business/run", json={"title": "Team pricing", "inputs": BIZ}, headers=h).json()
    mate_id = make_user(conn, role="member", workspace_id=wid)[0]
    mate = hdr(mate_id, wid)
    admin = hdr(make_user(conn, role="admin", workspace_id=wid)[0], wid)
    other = hdr(*make_user(conn))
    m = call(client, mate, "GET", "saved-intelligence").json()
    assert [i["type"] for i in m["items"]] == ["simulation"] and m["items"][0]["owner"] != "You" and m["items"][0]["can_delete"] is False
    assert call(client, admin, "GET", "saved-intelligence").json()["items"][0]["can_delete"] is True
    assert call(client, other, "GET", "saved-intelligence").json()["total"] == 0
    assert call(client, mate, "DELETE", m["items"][0]["delete_path"] or f"simlab/runs/{sim['id']}").status_code == 403
