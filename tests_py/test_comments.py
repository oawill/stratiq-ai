"""Comments on saved work: visibility, permissions, threading and workspace isolation."""
import uuid

from .conftest import hdr, make_user
from .test_api import first_fixture
from .test_business_api import SCEN
from .test_team import workspace_with


def scenario_id(client, h):
    return client.post("/api/v1/business/scenarios", json=SCEN, headers=h).json()["id"]


def post(client, h, item_id, body="Looks right", item_type="scenario", **extra):
    return client.post("/api/v1/comments", json={"item_type": item_type, "item_id": item_id, "body": body, **extra}, headers=h)


def listing(client, h, item_id, item_type="scenario"):
    return client.get(f"/api/v1/comments?item_type={item_type}&item_id={item_id}", headers=h)


def test_requires_auth(client):
    assert client.get(f"/api/v1/comments?item_type=scenario&item_id={uuid.uuid4()}").status_code == 401
    assert client.post("/api/v1/comments", json={}).status_code == 401


def test_teammates_see_each_others_comments(client, conn):
    wid, [(o, ho), (m, hm)] = workspace_with(conn, "owner", "member")
    sid = scenario_id(client, ho)
    assert post(client, hm, sid, "  Check the second row  ").status_code == 201
    seen = listing(client, ho, sid).json()["comments"]
    assert len(seen) == 1 and seen[0]["body"] == "Check the second row" and seen[0]["author_name"] == "T"
    assert seen[0]["mine"] is False and seen[0]["can_delete"] is True   # the owner can moderate
    mine = listing(client, hm, sid).json()["comments"][0]
    assert mine["mine"] is True and mine["can_delete"] is True


def test_comments_work_on_forecasts_too(client, conn):
    wid, [(o, ho)] = workspace_with(conn, "owner")
    f = first_fixture(client, ho)
    pid = client.post("/api/v1/sports/predictions", json={"fixture_id": f["id"]}, headers=ho).json()["id"]
    assert post(client, ho, pid, "Home advantage seems high", "prediction").status_code == 201
    assert len(listing(client, ho, pid, "prediction").json()["comments"]) == 1


def test_viewers_read_but_cannot_comment(client, conn):
    wid, [(o, ho), (v, hv)] = workspace_with(conn, "owner", "viewer")
    sid = scenario_id(client, ho)
    post(client, ho, sid)
    assert listing(client, hv, sid).status_code == 200
    assert post(client, hv, sid).status_code == 403


def test_validation(client, conn):
    wid, [(o, ho)] = workspace_with(conn, "owner")
    sid = scenario_id(client, ho)
    assert post(client, ho, sid, "   ").status_code == 422
    assert post(client, ho, sid, "x" * 2001).status_code == 422
    assert post(client, ho, sid, item_type="astrology").status_code == 422
    assert post(client, ho, str(uuid.uuid4())).status_code == 404  # no such item
    assert listing(client, ho, str(uuid.uuid4())).status_code == 404


def test_replies_are_one_level_deep_and_deleting_a_comment_hides_its_replies(client, conn):
    wid, [(o, ho), (m, hm)] = workspace_with(conn, "owner", "member")
    sid = scenario_id(client, ho)
    top = post(client, ho, sid, "Top").json()["id"]
    reply = post(client, hm, sid, "Reply", parent_id=top)
    assert reply.status_code == 201
    assert post(client, ho, sid, "Too deep", parent_id=reply.json()["id"]).status_code == 422
    assert post(client, ho, sid, "Orphan", parent_id=str(uuid.uuid4())).status_code == 404
    assert [c["body"] for c in listing(client, ho, sid).json()["comments"]] == ["Top", "Reply"]
    assert client.delete(f"/api/v1/comments/{top}", headers=ho).status_code == 204
    assert listing(client, ho, sid).json()["comments"] == []


def test_who_may_delete(client, conn):
    wid, [(o, ho), (a, ha), (m, hm), (m2, hm2)] = workspace_with(conn, "owner", "admin", "member", "member")
    sid = scenario_id(client, ho)
    c = post(client, hm, sid).json()["id"]
    assert client.delete(f"/api/v1/comments/{c}", headers=hm2).status_code == 403   # another member
    assert client.delete(f"/api/v1/comments/{c}", headers=ha).status_code == 204    # an admin can moderate
    assert client.delete(f"/api/v1/comments/{c}", headers=hm).status_code == 404    # already gone
    c2 = post(client, hm, sid).json()["id"]
    assert client.delete(f"/api/v1/comments/{c2}", headers=hm).status_code == 204   # authors delete their own


def test_comments_are_isolated_between_workspaces(client, conn):
    wa, [(a, ha)] = workspace_with(conn, "owner")
    wb, [(b, hb)] = workspace_with(conn, "owner")
    sid = scenario_id(client, ha)
    cid = post(client, ha, sid).json()["id"]
    assert listing(client, hb, sid).status_code == 404
    assert post(client, hb, sid).status_code == 404
    assert client.delete(f"/api/v1/comments/{cid}", headers=hb).status_code == 404


def test_commenting_appears_in_the_activity_feed(client, conn):
    wid, [(o, ho)] = workspace_with(conn, "owner")
    sid = scenario_id(client, ho)
    post(client, ho, sid)
    assert client.get("/api/v1/team/activity", headers=ho).json()["activity"][0]["kind"] == "comment.created"
