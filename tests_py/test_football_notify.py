"""Phase 4G: football alerts. In-app only; opt-in; deduplicated. History is SYNTHETIC; provider responses are MOCKED."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from stratiq import football_forecast as ff
from stratiq import football_notify as nf
from stratiq import football_provider as fp
from stratiq import football_results as res
from stratiq import football_sync as sync

from .conftest import hdr, make_user
from .test_football_forecast import AWAY, HOME, OTHERS, add_fixture, played, versions
from .test_football_live import KEY, Provider
from .test_football_live import match as provider_match
from .test_football_provenance import do_import

RealAdapter = fp.FootballDataOrg
NOW = datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture()
def ws(client, conn):
    """(user id, workspace id) with synthetic match history imported."""
    uid, wid = make_user(conn)
    assert do_import(client, hdr(uid, wid, exp_in=900)).status_code == 200
    return uid, wid


@pytest.fixture(autouse=True)
def no_provider(monkeypatch, conn):
    monkeypatch.delenv("FOOTBALL_DATA_API_KEY", raising=False)
    conn.execute("delete from football_provider_health")                          # shared state: start from a provider that has never been contacted (rolled back with the test)
    conn.execute("delete from football_provider_cache")


def opt_in(conn, wid, uid, cats=("new_prediction",), teams=(), comps=("EPL",), channels=None):
    return nf.save_prefs(conn, wid, uid, {"categories": list(cats), "competitions": list(comps), "teams": list(teams), "channels": channels or {"email": False, "push": False}})


def inbox(conn, wid, uid):
    return conn.execute("select * from notifications where workspace_id=%s and user_id=%s order by created_at", (wid, uid)).fetchall()


def events(conn, wid, category=None):
    return conn.execute("select * from football_notification_events where workspace_id=%s and (%s::text is null or category=%s) order by created_at", (wid, category, category)).fetchall()


def emit(conn, wid, key="k1", cat="new_prediction", teams=(HOME, AWAY), **kw):
    return nf.emit(conn, wid, cat, "Title", "Body", key, teams=list(teams), href="/dashboard/sports/live", now=NOW, **kw)


# ---- opt-in, delivery, deduplication ------------------------------------------------------------------------------------------------

def test_nobody_is_notified_without_choosing_categories_but_the_event_is_still_recorded(conn, ws):
    uid, wid = ws
    r = emit(conn, wid)
    assert r["status"] == "recorded" and r["delivered"] == 0 and len(events(conn, wid)) == 1 and inbox(conn, wid, uid) == []
    opt_in(conn, wid, uid, cats=())                                                   # a row with no categories is also silence
    assert emit(conn, wid, "k2")["delivered"] == 0 and inbox(conn, wid, uid) == []


def test_a_person_who_chose_a_category_gets_it_and_a_colleague_who_did_not_does_not(conn, ws):
    uid, wid = ws
    mate, _ = make_user(conn, role="member", workspace_id=wid)
    opt_in(conn, wid, uid)
    r = emit(conn, wid)
    assert r["delivered"] == 1
    n = inbox(conn, wid, uid)
    assert len(n) == 1 and n[0]["kind"] == "football_new_prediction" and n[0]["title"] == "Title" and n[0]["source"]["href"] == "/dashboard/sports/live" and n[0]["read_at"] is None
    assert inbox(conn, wid, mate) == [] and conn.execute("select delivered from football_notification_events where workspace_id=%s", (wid,)).fetchone()["delivered"] == 1


def test_the_same_event_is_never_notified_twice(conn, ws):
    uid, wid = ws
    opt_in(conn, wid, uid)
    first = emit(conn, wid)
    assert emit(conn, wid)["status"] == "duplicate" and len(events(conn, wid)) == 1 and len(inbox(conn, wid, uid)) == 1
    conn.execute("update notifications set deleted_at=now() where workspace_id=%s and user_id=%s", (wid, uid))              # deleting a notification keeps its key
    assert nf.deliver(conn, {"id": first["event_id"], "workspace_id": wid, "category": "new_prediction", "competition": "EPL", "teams": [HOME], "title": "T", "body": "B", "href": None}, NOW)["duplicates"] == 1
    assert len(inbox(conn, wid, uid)) == 1


def test_team_and_competition_choices_filter_what_a_person_hears(conn, ws):
    uid, wid = ws
    anyone, _ = make_user(conn, role="member", workspace_id=wid)
    opt_in(conn, wid, uid, cats=("new_prediction", "provider_failure", "data_quality"), teams=(HOME,))
    opt_in(conn, wid, anyone, cats=("new_prediction",))
    emit(conn, wid, "a", teams=(OTHERS[0], OTHERS[1]))                               # not their club
    assert len(inbox(conn, wid, uid)) == 0 and len(inbox(conn, wid, anyone)) == 1
    emit(conn, wid, "b", teams=(HOME, OTHERS[0]))                                     # their club
    assert len(inbox(conn, wid, uid)) == 1
    emit(conn, wid, "c", teams=())                                                    # a summary event names no clubs: it does not reach people who chose specific clubs
    assert len(inbox(conn, wid, uid)) == 1 and len(inbox(conn, wid, anyone)) == 3
    emit(conn, wid, "d", cat="provider_failure", teams=())                           # provider and data alerts ignore the club choice
    emit(conn, wid, "e", cat="data_quality", teams=())
    assert len(inbox(conn, wid, uid)) == 3
    emit(conn, wid, "f", competition="XX")                                           # another competition
    assert len(inbox(conn, wid, uid)) == 3
    assert not nf.matches({"categories": ["new_fixture"], "competitions": ["EPL"], "teams": []}, {"category": "new_prediction", "competition": "EPL", "teams": []})


def test_in_app_switch_quiet_hours_and_the_daily_cap_are_respected(conn, ws):
    from stratiq import preferences_api as prefs
    uid, wid = ws
    opt_in(conn, wid, uid)
    prefs.save_section(conn, uid, "notifications", {"in_app": False, "quiet_hours": {"enabled": False, "start": "22:00", "end": "07:00", "utc_offset_minutes": 0}})
    assert emit(conn, wid, "off")["delivered"] == 0 and inbox(conn, wid, uid) == []
    hour = NOW.hour
    quiet = {"enabled": True, "start": f"{hour:02d}:00", "end": f"{(hour + 2) % 24:02d}:00", "utc_offset_minutes": 0}
    prefs.save_section(conn, uid, "notifications", {"in_app": True, "quiet_hours": quiet})
    r = emit(conn, wid, "quiet")
    assert r["delivered"] == 1 and r["quiet"] == 1
    assert inbox(conn, wid, uid)[0]["visible_after"] > conn.execute("select now() n").fetchone()["n"]              # held back, not lost
    prefs.save_section(conn, uid, "notifications", {"in_app": True, "quiet_hours": {**quiet, "enabled": False}})
    for i in range(35):
        emit(conn, wid, f"cap{i}")
    assert len(inbox(conn, wid, uid)) == 30                                          # the same daily cap as every other alert
    assert conn.execute("select sum(delivered) s from football_notification_events where workspace_id=%s", (wid,)).fetchone()["s"] == 30


# ---- optional channels --------------------------------------------------------------------------------------------------------------

class Fake(nf.Channel):
    name = "email"

    def __init__(self, ok=True, boom=False):
        self.sent, self.ok, self.boom = [], ok, boom

    def available(self):
        return self.ok, "fake"

    def send(self, user_id, event):
        if self.boom:
            raise RuntimeError("down")
        self.sent.append((user_id, event["title"]))
        return True


def test_email_and_push_cannot_be_switched_on_while_they_are_not_available(conn, ws):
    st = nf.channel_status()
    assert st["email"]["available"] is False and st["push"]["available"] is False and "not" in st["email"]["reason"].lower()
    with pytest.raises(ValueError, match="not connected"):
        nf.validate_prefs(["new_prediction"], ["EPL"], [], {"email": True}, set())
    with pytest.raises(ValueError):
        nf.validate_prefs(["new_prediction"], ["EPL"], [], {"push": True}, set())


def test_an_available_channel_is_used_only_for_people_who_opted_in_and_never_breaks_delivery(conn, ws, monkeypatch):
    uid, wid = ws
    mate, _ = make_user(conn, role="member", workspace_id=wid)
    fake = Fake()
    monkeypatch.setitem(nf.CHANNELS, "email", fake)
    nf.save_prefs(conn, wid, uid, nf.validate_prefs(["new_prediction"], ["EPL"], [], {"email": True}, set()))
    opt_in(conn, wid, mate)                                                           # a colleague who did not switch email on
    r = emit(conn, wid)
    assert r["channel_sent"] == 1 and fake.sent == [(uid, "Title")] and len(inbox(conn, wid, uid)) == 1 and len(inbox(conn, wid, mate)) == 1
    monkeypatch.setitem(nf.CHANNELS, "email", Fake(boom=True))
    r = emit(conn, wid, "second")
    assert r["channel_failed"] == 1 and r["delivered"] == 2 and len(inbox(conn, wid, uid)) == 2          # the in-app alert still arrived
    monkeypatch.setitem(nf.CHANNELS, "email", Fake(ok=False))
    assert emit(conn, wid, "third")["channel_sent"] == 0


# ---- the events the pipeline raises -------------------------------------------------------------------------------------------------

def test_a_failing_notification_never_breaks_forecasting(conn, ws, monkeypatch):
    uid, wid = ws
    opt_in(conn, wid, uid)
    monkeypatch.setattr(nf, "emit", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    fx = add_fixture(conn, wid, kick=NOW + timedelta(days=3))
    assert ff.generate_version(conn, fx, "discovery", "First.", NOW)["status"] == "created" and len(versions(conn, fx["id"])) == 1


def test_first_forecast_raises_new_prediction_once_and_a_significant_move_raises_probability_change(conn, ws):
    uid, wid = ws
    opt_in(conn, wid, uid, cats=("new_prediction", "probability_change"))
    fx = add_fixture(conn, wid, kick=NOW + timedelta(days=3))
    ff.generate_version(conn, fx, "discovery", "First.", NOW)
    n = inbox(conn, wid, uid)
    assert [x["kind"] for x in n] == ["football_new_prediction"] and "Home" in n[0]["body"] and "not a certainty" in n[0]["body"] and n[0]["source"]["href"].endswith(str(fx["id"]))
    ff.generate_version(conn, fx, "h24", "Again.", NOW + timedelta(hours=1))               # unchanged: nothing new
    assert len(inbox(conn, wid, uid)) == 1
    nf.forecast_made(conn, fx, 2, (0.5, 0.3, 0.2), {"significant": True, "max_abs_change": 0.081}, NOW)
    nf.forecast_made(conn, fx, 3, (0.5, 0.3, 0.2), {"significant": False, "max_abs_change": 0.01}, NOW)
    kinds = [x["kind"] for x in inbox(conn, wid, uid)]
    assert kinds.count("football_probability_change") == 1 and "8.1 points" in next(x for x in inbox(conn, wid, uid) if x["kind"] == "football_probability_change")["body"]


def test_lineup_alerts_exist_but_cannot_be_chosen_or_fire(conn, ws):
    assert nf.CATEGORIES["lineup_change"]["available"] is False and "lineups" in nf.CATEGORIES["lineup_change"]["unavailable_reason"]
    with pytest.raises(ValueError, match="supplies no lineups"):
        nf.validate_prefs(["lineup_change"], ["EPL"], [], {}, set())


def test_results_raise_final_result_and_evaluation_alerts_once_and_corrections_raise_a_new_one(conn, ws):
    uid, wid = ws
    opt_in(conn, wid, uid, cats=("final_result", "evaluation_complete", "data_quality"))
    fx = played(conn, wid, HOME, AWAY, 3, (2, 1))
    fixture = lambda: conn.execute("select * from football_fixtures where id=%s", (fx["id"],)).fetchone()  # noqa: E731
    res.reconcile_fixture(conn, fixture(), NOW)
    kinds = sorted(x["kind"] for x in inbox(conn, wid, uid))
    assert kinds == ["football_evaluation_complete", "football_final_result"]
    assert "2–1" in [x for x in inbox(conn, wid, uid) if x["kind"] == "football_final_result"][0]["title"]
    res.reconcile_fixture(conn, fixture(), NOW + timedelta(hours=1))                          # nothing changed: no new alerts
    assert len(inbox(conn, wid, uid)) == 2
    conn.execute("update football_fixtures set home_goals=1, away_goals=1 where id=%s", (fx["id"],))
    res.reconcile_fixture(conn, fixture(), NOW + timedelta(hours=2))
    titles = [x["title"] for x in inbox(conn, wid, uid)]
    assert len(titles) == 4 and any(t.startswith("Score corrected") for t in titles)


def test_a_result_that_conflicts_with_uploaded_data_raises_a_data_quality_alert(client, conn, ws):
    from .test_football import five_csv
    from .test_football_intel import post
    uid, wid = ws
    opt_in(conn, wid, uid, cats=("data_quality",))
    d = (NOW - timedelta(days=3)).date()
    post(client, hdr(uid, wid, exp_in=900), "import", {"filename": "E0.csv", "combined": True, "csv": five_csv([(d, HOME, AWAY, 0, 3)])})
    fx = played(conn, wid, HOME, AWAY, 3, (2, 1))
    res.reconcile_fixture(conn, conn.execute("select * from football_fixtures where id=%s", (fx["id"],)).fetchone(), NOW)
    n = inbox(conn, wid, uid)
    assert len(n) == 1 and n[0]["kind"] == "football_data_quality" and "Result conflict" in n[0]["title"]


def test_an_ineligible_fixture_raises_a_data_quality_alert_once(conn, ws):
    uid, wid = ws
    opt_in(conn, wid, uid, cats=("data_quality",))
    add_fixture(conn, wid, home="Brand New Town", away=AWAY, kick=NOW + timedelta(days=3))
    ff.generate_pending(conn, wid, NOW)
    ff.generate_pending(conn, wid, NOW + timedelta(minutes=10))
    n = inbox(conn, wid, uid)
    assert len(n) == 1 and "Cannot forecast Brand New Town v" in n[0]["title"] and "Brand New Town" in n[0]["body"]


def _provider(monkeypatch, p):
    monkeypatch.setenv("FOOTBALL_DATA_API_KEY", KEY)
    monkeypatch.setattr(fp, "FootballDataOrg", lambda: RealAdapter(KEY, httpx.Client(transport=httpx.MockTransport(p.handler)), sleep=lambda s: None, jitter=lambda: 0.0))


def test_new_fixtures_are_announced_individually_when_few_and_as_one_summary_when_many(conn, ws, monkeypatch):
    uid, wid = ws
    anyone, _ = make_user(conn, role="member", workspace_id=wid)
    opt_in(conn, wid, uid, cats=("new_fixture",), teams=(HOME,))
    opt_in(conn, wid, anyone, cats=("new_fixture",))
    kick = (NOW + timedelta(days=4)).replace(hour=15, minute=0, second=0)
    p = Provider([provider_match(8000 + i, f"{OTHERS[i % 10]} FC", f"{OTHERS[(i + 1) % 10]} FC", kick + timedelta(hours=i)) for i in range(2)] + [provider_match(8100, HOME + " FC", AWAY + " FC", kick)])
    _provider(monkeypatch, p)
    sync.sync_workspace(conn, wid, "manual", now=NOW)
    assert len(events(conn, wid, "new_fixture")) == 3 and len(inbox(conn, wid, anyone)) == 3 and len(inbox(conn, wid, uid)) == 1       # the club filter applies
    sync.sync_workspace(conn, wid, "manual", now=NOW + timedelta(hours=1))
    assert len(events(conn, wid, "new_fixture")) == 3                                                # nothing new, nothing announced
    many = Provider([provider_match(9000 + i, f"{OTHERS[i % 10]} FC", f"{OTHERS[(i + 3) % 10]} FC", kick + timedelta(days=1 + i)) for i in range(8)])
    _provider(monkeypatch, many)
    sync.sync_workspace(conn, wid, "manual", now=NOW + timedelta(days=1))
    summary = [e for e in events(conn, wid, "new_fixture") if e["title"].endswith("new fixtures")]
    assert len(summary) == 1 and summary[0]["detail"]["count"] == 8 and len(inbox(conn, wid, anyone)) == 4 and len(inbox(conn, wid, uid)) == 1


def test_provider_failure_is_announced_once_per_outage_and_unrecognised_clubs_are_reported(conn, ws, monkeypatch):
    uid, wid = ws
    opt_in(conn, wid, uid, cats=("provider_failure", "data_quality"))
    down = Provider(failures=[httpx.Response(503)] * 30)
    _provider(monkeypatch, down)
    t = NOW
    for i in range(2):
        sync.sync_workspace(conn, wid, "manual", now=t)
        t += timedelta(minutes=1)
    assert events(conn, wid, "provider_failure") == []                                               # two failures are not an outage
    sync.sync_workspace(conn, wid, "manual", now=t)
    assert len(events(conn, wid, "provider_failure")) == 1 and len(inbox(conn, wid, uid)) == 1
    sync.sync_workspace(conn, wid, "manual", now=t + sync.PAUSE_FOR + timedelta(minutes=1))
    assert len(events(conn, wid, "provider_failure")) == 1                                           # the same outage is not announced again
    kick = (NOW + timedelta(days=4)).replace(hour=15, minute=0, second=0)
    ok = Provider([provider_match(7, "Imaginary Rovers FC", AWAY + " FC", kick)])
    _provider(monkeypatch, ok)
    sync.sync_workspace(conn, wid, "manual", now=t + timedelta(hours=1))
    assert any("Club names not recognised" in x["title"] and "Imaginary Rovers" in x["body"] for x in inbox(conn, wid, uid))


def test_old_events_are_purged(conn, ws):
    uid, wid = ws
    emit(conn, wid)
    conn.execute("update football_notification_events set created_at=now() - interval '100 days' where workspace_id=%s", (wid,))
    assert nf.purge_old_events(conn) >= 1 and events(conn, wid) == []


# ---- API ----------------------------------------------------------------------------------------------------------------------------

def test_alert_settings_api_validation_and_privacy(client, conn, ws):
    uid, wid = ws
    h = hdr(uid, wid, exp_in=900)
    g = client.get("/api/v1/football/live/alert-settings", headers=h).json()
    assert g["configured"] is False and g["categories"] == [] and {c["id"] for c in g["catalogue"]} == set(nf.CATEGORIES) and HOME in g["teams_available"]
    assert g["channel_status"]["email"]["available"] is False and "Nothing is sent" in g["note"]
    put = lambda body, hh=h: client.put("/api/v1/football/live/alert-settings", json=body, headers=hh)  # noqa: E731
    ok = put({"categories": ["new_prediction", "final_result"], "teams": [HOME, AWAY], "competitions": ["EPL"]})
    assert ok.status_code == 200 and ok.json()["categories"] == ["final_result", "new_prediction"] and ok.json()["teams"] == sorted([HOME, AWAY]) and ok.json()["configured"] is True
    for bad in ({"categories": ["nope"]}, {"categories": ["lineup_change"]}, {"teams": ["Not A Club"]}, {"competitions": ["XX"]}, {"channels": {"email": True}}, {"teams": [f"T{i}" for i in range(25)]}):
        assert put(bad).status_code == 422
    mate = hdr(make_user(conn, role="viewer", workspace_id=wid)[0], wid, exp_in=900)
    assert client.get("/api/v1/football/live/alert-settings", headers=mate).json()["categories"] == []         # choices are per person
    assert put({"categories": ["data_quality"]}, mate).status_code == 200 and client.get("/api/v1/football/live/alert-settings", headers=h).json()["categories"] == ["final_result", "new_prediction"]
    ou, ow = make_user(conn)
    assert client.get("/api/v1/football/live/alert-settings", headers=hdr(ou, ow, exp_in=900)).json()["configured"] is False
    assert client.get("/api/v1/football/live/alert-settings").status_code in (401, 403)


def test_alert_events_api_pages_filters_and_stays_in_the_workspace(client, conn, ws):
    uid, wid = ws
    h = hdr(uid, wid, exp_in=900)
    for i in range(3):
        emit(conn, wid, f"p{i}")
    emit(conn, wid, "d", cat="data_quality", teams=())
    g = lambda q="": client.get("/api/v1/football/live/alert-events?" + q, headers=h)  # noqa: E731
    assert g().json()["total"] == 4 and len(g("limit=2").json()["events"]) == 2 and g("category=data_quality").json()["total"] == 1 and g("category=nope").status_code == 422
    ou, ow = make_user(conn)
    assert client.get("/api/v1/football/live/alert-events", headers=hdr(ou, ow, exp_in=900)).json()["total"] == 0


def test_readiness_is_honest_about_what_is_missing_and_unverified(client, conn, ws, monkeypatch):
    uid, wid = ws
    h = hdr(uid, wid, exp_in=900)
    monkeypatch.delenv("CRON_SECRET", raising=False)
    r = client.get("/api/v1/football/live/readiness", headers=h).json()
    by = {c["id"]: c for c in r["checks"]}
    assert r["ready"] is False and r["connectivity_verified"] is False and by["database"]["ok"] is True
    assert by["provider_key"]["ok"] is False and by["provider_connectivity"]["ok"] is False and "unverified" in by["provider_connectivity"]["detail"]
    assert by["scheduler_secret"]["ok"] is False and by["forecasts"]["ok"] is False and by["evaluations"]["ok"] is False and "mocked" in r["note"]
    assert "FOOTBALL_DATA_API_KEY" not in str(r) or "is not set" in by["provider_key"]["detail"]
    monkeypatch.setenv("FOOTBALL_DATA_API_KEY", KEY)
    monkeypatch.setenv("CRON_SECRET", "s" * 20)
    p = Provider([provider_match(1, HOME + " FC", AWAY + " FC", (NOW + timedelta(days=3)))])
    _provider(monkeypatch, p)
    sync.sync_workspace(conn, wid, "manual", now=sync.utcnow())
    conn.execute("insert into football_job_runs (workspace_id, kind, trigger, status, detail) values (%s,'live','schedule','complete','{}')", (wid,))
    r2 = client.get("/api/v1/football/live/readiness", headers=h).json()
    by2 = {c["id"]: c for c in r2["checks"]}
    assert r2["connectivity_verified"] is True and r2["ready"] is True and by2["provider_health"]["ok"] and by2["fixtures_fresh"]["ok"] and by2["scheduler_running"]["ok"]
    assert KEY not in str(r2)
