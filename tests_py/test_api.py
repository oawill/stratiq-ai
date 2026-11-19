import psycopg
import pytest

from .conftest import hdr, make_user, token


def first_fixture(client, h, status="scheduled", league="nfl-fict"):
    r = client.get(f"/api/v1/sports/fixtures?league_id={league}&status={status}&limit=3", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["fixtures"][0]


# ------------------------------------------------------------ authentication
def test_health_is_public(client):
    assert client.get("/api/v1/health").json()["status"] == "ok"


@pytest.mark.parametrize("path", ["/api/v1/overview", "/api/v1/sports/leagues", "/api/v1/me", "/api/v1/sports/predictions"])
def test_protected_routes_reject_anonymous(client, path):
    assert client.get(path).status_code == 401


def test_rejects_bad_expired_and_wrong_issuer_tokens(client, conn):
    uid, wid = make_user(conn)
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    assert client.get("/api/v1/me", headers=hdr(uid, wid, exp_in=-10)).status_code == 401
    assert client.get("/api/v1/me", headers=hdr(uid, wid, secret="x" * 40)).status_code == 401
    assert client.get("/api/v1/me", headers=hdr(uid, wid, iss="someone-else")).status_code == 401
    assert client.get("/api/v1/me", headers=hdr(uid, wid)).status_code == 200


def test_forged_workspace_claim_is_rejected(client, conn):
    uid, _ = make_user(conn)
    _, other_ws = make_user(conn)
    # Valid signature, but the user is not a member of that workspace.
    assert client.get("/api/v1/overview", headers=hdr(uid, other_ws)).status_code == 403


def test_garbage_ids_in_claims_do_not_crash(client):
    assert client.get("/api/v1/me", headers=hdr("not-a-uuid", "also-not")).status_code == 401


# ------------------------------------------------------------ sports reads
def test_leagues_teams_fixtures_are_labelled_fictional(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    leagues = client.get("/api/v1/sports/leagues", headers=h).json()["leagues"]
    assert leagues and all(l["is_fictional"] for l in leagues)
    teams = client.get("/api/v1/sports/teams?league_id=nfl-fict", headers=h).json()
    assert len(teams["teams"]) == 12 and teams["home_advantage"] > 0
    assert client.get("/api/v1/sports/teams?league_id=nope", headers=h).status_code == 404


def test_compare_validations(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    f = first_fixture(client, h)
    ok = client.get(f"/api/v1/sports/compare?home_team_id={f['home_team_id']}&away_team_id={f['away_team_id']}", headers=h)
    assert ok.status_code == 200
    assert abs(sum(ok.json()["projection"][k] for k in ("p_home", "p_draw", "p_away")) - 1) < 1e-4
    same = client.get(f"/api/v1/sports/compare?home_team_id={f['home_team_id']}&away_team_id={f['home_team_id']}", headers=h)
    assert same.status_code == 422


# ------------------------------------------------------------ predictions
def test_create_prediction_stores_full_record(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    f = first_fixture(client, h)
    r = client.post("/api/v1/sports/predictions", json={"fixture_id": f["id"]}, headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    o = body["outputs"]
    assert abs(o["p_home"] + o["p_draw"] + o["p_away"] - 1) < 1e-4
    assert body["model"] == {"name": "poisson-maher", "version": "0.1.0"}
    assert body["assumptions"] and body["inputs"]["matches_used"] > 0
    row = conn.execute("select * from predictions where id=%s", (body["id"],)).fetchone()
    assert row["workspace_id"].hex == wid.replace("-", "")
    assert row["feature_cutoff"] <= row["created_at"]
    assert row["input_hash"] and row["outputs"]["home_xg"] > 0
    # activity + audit written
    assert conn.execute("select count(*) n from activity_history where workspace_id=%s", (wid,)).fetchone()["n"] == 1
    assert conn.execute("select count(*) n from audit_logs where workspace_id=%s and action='prediction.create'", (wid,)).fetchone()["n"] == 1


def test_predictions_are_immutable(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    f = first_fixture(client, h)
    pid = client.post("/api/v1/sports/predictions", json={"fixture_id": f["id"]}, headers=h).json()["id"]
    with pytest.raises(psycopg.errors.RaiseException):
        with conn.transaction():
            conn.execute("update predictions set outputs='{}' where id=%s", (pid,))
    with pytest.raises(psycopg.errors.RaiseException):
        with conn.transaction():
            conn.execute("delete from predictions where id=%s", (pid,))


def test_workspace_isolation_for_predictions(client, conn):
    a_uid, a_ws = make_user(conn)
    b_uid, b_ws = make_user(conn)
    ha, hb = hdr(a_uid, a_ws), hdr(b_uid, b_ws)
    f = first_fixture(client, ha)
    pid = client.post("/api/v1/sports/predictions", json={"fixture_id": f["id"]}, headers=ha).json()["id"]
    assert client.get(f"/api/v1/sports/predictions/{pid}", headers=ha).status_code == 200
    assert client.get(f"/api/v1/sports/predictions/{pid}", headers=hb).status_code == 404
    assert client.get("/api/v1/sports/predictions", headers=hb).json()["predictions"] == []
    assert client.get("/api/v1/overview", headers=hb).json()["recent_predictions"] == []
    assert len(client.get("/api/v1/overview", headers=ha).json()["recent_predictions"]) == 1
    assert client.get("/api/v1/sports/predictions/not-a-uuid", headers=ha).status_code == 404


def test_viewer_cannot_create_predictions(client, conn):
    _, wid = make_user(conn)
    vid, _ = make_user(conn, role="viewer", workspace_id=wid)
    h = hdr(vid, wid)
    f = first_fixture(client, h)
    assert client.post("/api/v1/sports/predictions", json={"fixture_id": f["id"]}, headers=h).status_code == 403


def test_prediction_input_validation(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    assert client.post("/api/v1/sports/predictions", json={}, headers=h).status_code == 422
    assert client.post("/api/v1/sports/predictions", json={"fixture_id": 0}, headers=h).status_code == 422
    assert client.post("/api/v1/sports/predictions", json={"fixture_id": 999999999}, headers=h).status_code == 404
    a = client.get("/api/v1/sports/teams?league_id=nfl-fict", headers=h).json()["teams"][0]["id"]
    b = client.get("/api/v1/sports/teams?league_id=csd-fict", headers=h).json()["teams"][0]["id"]
    assert client.post("/api/v1/sports/predictions", json={"home_team_id": a, "away_team_id": a}, headers=h).status_code == 422
    assert client.post("/api/v1/sports/predictions", json={"home_team_id": a, "away_team_id": b}, headers=h).status_code == 422


def test_retrospective_prediction_has_no_lookahead_and_is_reproducible(client, conn):
    uid, wid = make_user(conn)
    h = hdr(uid, wid)
    f = first_fixture(client, h, status="finished")
    total = len(client.get("/api/v1/sports/fixtures?league_id=nfl-fict&status=finished&limit=200", headers=h).json()["fixtures"])
    r1 = client.post("/api/v1/sports/predictions", json={"fixture_id": f["id"]}, headers=h).json()
    r2 = client.post("/api/v1/sports/predictions", json={"fixture_id": f["id"]}, headers=h).json()
    # Latest finished fixture: strictly earlier matches only, so fewer than all finished matches.
    assert r1["inputs"]["matches_used"] < total
    assert r1["inputs"]["retrospective"] is True
    assert r1["outputs"] == r2["outputs"]
    a = conn.execute("select input_hash from predictions where id=%s", (r1["id"],)).fetchone()
    b = conn.execute("select input_hash from predictions where id=%s", (r2["id"],)).fetchone()
    assert a["input_hash"] == b["input_hash"]


def test_model_endpoint_reports_real_metrics_only(client, conn):
    uid, wid = make_user(conn)
    d = client.get("/api/v1/sports/model", headers=hdr(uid, wid)).json()
    assert d["model"]["name"] == "poisson-maher" and d["model"]["limitations"]
    for m in d["metrics"]:
        assert "fictional" in m["dataset"] and m["sample_size"] > 0
