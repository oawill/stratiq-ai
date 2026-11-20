"""Team management: roles, invitations, seats, leaving, ownership transfer, activity. Workspace isolation throughout."""
import uuid
from datetime import timedelta

import pytest

from stratiq.team_api import hash_token
from .conftest import hdr, make_user
from .test_billing import subscribe


def workspace_with(conn, *roles):
    """A workspace with one user per role (first role is the creator). Returns (wid, [(uid, headers), ...])."""
    uid, wid = make_user(conn, roles[0])
    out = [(uid, hdr(uid, wid))]
    for r in roles[1:]:
        u, _ = make_user(conn, r, workspace_id=wid)
        out.append((u, hdr(u, wid)))
    return wid, out


def invite(client, h, email=None, role="member"):
    return client.post("/api/v1/team/invites", json={"email": email or f"{uuid.uuid4().hex[:8]}@example.com", "role": role}, headers=h)


# ------------------------------------------------------------------ listing
def test_members_listing_and_invite_visibility(client, conn):
    wid, [(o, ho), (m, hm)] = workspace_with(conn, "owner", "member")
    invite(client, ho, "pending@example.com")
    for_owner = client.get("/api/v1/team/members", headers=ho).json()
    assert [x["role"] for x in for_owner["members"]] == ["owner", "member"]
    assert for_owner["me"]["role"] == "owner"
    assert [i["email"] for i in for_owner["invites"]] == ["pending@example.com"]
    assert for_owner["seats"] == {"members": 2, "pending": 1, "cap": None}
    # Plain members see the team, but not pending invitation addresses.
    for_member = client.get("/api/v1/team/members", headers=hm).json()
    assert len(for_member["members"]) == 2 and for_member["invites"] == []


def test_requires_auth(client):
    for method, path in [("get", "/api/v1/team/members"), ("post", "/api/v1/team/invites"), ("get", "/api/v1/team/activity"), ("post", "/api/v1/team/leave")]:
        assert getattr(client, method)(path).status_code == 401


# ------------------------------------------------------------------ invitations
def test_invite_returns_token_once_and_stores_only_its_hash(client, conn):
    wid, [(o, ho)] = workspace_with(conn, "owner")
    r = invite(client, ho, "New.Person@Example.com", "viewer")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "new.person@example.com" and body["role"] == "viewer"
    row = conn.execute("select token_hash, email from workspace_invites where id=%s", (body["id"],)).fetchone()
    assert row["token_hash"] == hash_token(body["token"]) and body["token"] not in row["token_hash"]
    assert len(body["token"]) >= 40
    listed = client.get("/api/v1/team/members", headers=ho).json()["invites"]
    assert "token" not in listed[0]


@pytest.mark.parametrize("who,role,status", [("owner", "admin", 201), ("admin", "member", 201), ("admin", "viewer", 201),
                                              ("admin", "admin", 403), ("member", "member", 403), ("viewer", "viewer", 403)])
def test_who_may_invite_whom(client, conn, who, role, status):
    wid, people = workspace_with(conn, "owner", who) if who != "owner" else workspace_with(conn, "owner")
    h = people[-1][1]
    assert invite(client, h, role=role).status_code == status


def test_invite_validation_and_duplicates(client, conn):
    wid, [(o, ho), (m, hm)] = workspace_with(conn, "owner", "member")
    assert invite(client, ho, "not-an-email").status_code == 422
    assert client.post("/api/v1/team/invites", json={"email": "a@b.co", "role": "owner"}, headers=ho).status_code == 422
    email = conn.execute("select email from users where id=%s", (m,)).fetchone()["email"]
    assert invite(client, ho, email).status_code == 409  # already a member


def test_reinviting_replaces_the_old_invitation_without_using_another_seat(client, conn, monkeypatch):
    monkeypatch.setenv("BILLING_ENFORCED", "1")
    wid, [(o, ho)] = workspace_with(conn, "owner")  # Explorer: 2 seats, one used by the owner
    first = invite(client, ho, "same@example.com").json()
    second = invite(client, ho, "same@example.com")
    assert second.status_code == 201
    old = conn.execute("select revoked_at from workspace_invites where id=%s", (first["id"],)).fetchone()
    assert old["revoked_at"] is not None
    assert len(client.get("/api/v1/team/members", headers=ho).json()["invites"]) == 1


def test_revoking_an_invitation(client, conn):
    wid, [(o, ho), (m, hm)] = workspace_with(conn, "owner", "member")
    iid = invite(client, ho, "gone@example.com").json()["id"]
    assert client.delete(f"/api/v1/team/invites/{iid}", headers=hm).status_code == 403
    assert client.delete(f"/api/v1/team/invites/{iid}", headers=ho).status_code == 204
    assert client.delete(f"/api/v1/team/invites/{iid}", headers=ho).status_code == 404
    assert client.get("/api/v1/team/members", headers=ho).json()["invites"] == []


def test_expired_invitations_do_not_show_or_use_seats(client, conn):
    wid, [(o, ho)] = workspace_with(conn, "owner")
    iid = invite(client, ho, "late@example.com").json()["id"]
    conn.execute("update workspace_invites set expires_at = now() - interval '1 minute' where id=%s", (iid,))
    data = client.get("/api/v1/team/members", headers=ho).json()
    assert data["invites"] == [] and data["seats"]["pending"] == 0


def test_invitations_are_isolated_between_workspaces(client, conn):
    wa, [(a, ha)] = workspace_with(conn, "owner")
    wb, [(b, hb)] = workspace_with(conn, "owner")
    iid = invite(client, ha, "x@example.com").json()["id"]
    assert client.delete(f"/api/v1/team/invites/{iid}", headers=hb).status_code == 404
    assert client.get("/api/v1/team/members", headers=hb).json()["invites"] == []


# ------------------------------------------------------------------ seats
def test_seat_limits_follow_the_plan_when_billing_is_enforced(client, conn, monkeypatch):
    monkeypatch.setenv("BILLING_ENFORCED", "1")
    wid, [(o, ho)] = workspace_with(conn, "owner")
    assert invite(client, ho, "one@example.com").status_code == 201  # owner + 1 = 2 seats (Explorer cap)
    r = invite(client, ho, "two@example.com")
    assert r.status_code == 402 and r.json()["detail"]["code"] == "seat_limit"
    subscribe(conn, wid, "strategy_pro")  # cap 5
    for n in range(3):
        assert invite(client, ho, f"more{n}@example.com").status_code == 201
    assert invite(client, ho, "over@example.com").status_code == 402
    assert client.get("/api/v1/team/members", headers=ho).json()["seats"] == {"members": 1, "pending": 4, "cap": 5}


def test_no_seat_limit_while_billing_is_not_enforced(client, conn, monkeypatch):
    monkeypatch.delenv("BILLING_ENFORCED", raising=False)
    wid, [(o, ho)] = workspace_with(conn, "owner")
    for n in range(8):
        assert invite(client, ho, f"p{n}@example.com").status_code == 201


# ------------------------------------------------------------------ roles
def test_owner_changes_roles_but_never_their_own_or_to_owner(client, conn):
    wid, [(o, ho), (m, hm)] = workspace_with(conn, "owner", "member")
    assert client.patch(f"/api/v1/team/members/{m}", json={"role": "admin"}, headers=ho).status_code == 200
    assert conn.execute("select role from workspace_members where user_id=%s", (m,)).fetchone()["role"] == "admin"
    assert client.patch(f"/api/v1/team/members/{o}", json={"role": "member"}, headers=ho).status_code == 403
    assert client.patch(f"/api/v1/team/members/{m}", json={"role": "owner"}, headers=ho).status_code == 422


def test_admin_role_limits(client, conn):
    wid, [(o, ho), (a, ha), (m, hm), (v, hv)] = workspace_with(conn, "owner", "admin", "member", "viewer")
    assert client.patch(f"/api/v1/team/members/{v}", json={"role": "member"}, headers=ha).status_code == 200
    assert client.patch(f"/api/v1/team/members/{m}", json={"role": "admin"}, headers=ha).status_code == 403  # cannot mint admins
    assert client.patch(f"/api/v1/team/members/{o}", json={"role": "viewer"}, headers=ha).status_code == 403  # cannot touch the owner
    assert client.patch(f"/api/v1/team/members/{m}", json={"role": "viewer"}, headers=hm).status_code == 403  # members cannot manage


def test_removing_members(client, conn):
    wid, [(o, ho), (a, ha), (m, hm), (v, hv)] = workspace_with(conn, "owner", "admin", "member", "viewer")
    assert client.delete(f"/api/v1/team/members/{v}", headers=hm).status_code == 403
    assert client.delete(f"/api/v1/team/members/{a}", headers=ha).status_code == 403   # admin cannot remove an admin (or themselves)
    assert client.delete(f"/api/v1/team/members/{o}", headers=ha).status_code == 403   # nobody removes the owner
    assert client.delete(f"/api/v1/team/members/{v}", headers=ha).status_code == 204
    assert client.delete(f"/api/v1/team/members/{a}", headers=ho).status_code == 204   # the owner can remove an admin
    left = [r["role"] for r in client.get("/api/v1/team/members", headers=ho).json()["members"]]
    assert left == ["owner", "member"]
    # A removed user is no longer authorized for the workspace, even with a still-valid token.
    assert client.get("/api/v1/team/members", headers=hdr(v, wid)).status_code == 403


def test_removal_clears_the_removed_users_active_workspace(client, conn):
    wid, [(o, ho), (m, hm)] = workspace_with(conn, "owner", "member")
    conn.execute("update users set active_workspace_id=%s where id=%s", (wid, m))
    client.delete(f"/api/v1/team/members/{m}", headers=ho)
    assert conn.execute("select active_workspace_id from users where id=%s", (m,)).fetchone()["active_workspace_id"] is None


def test_leave_and_ownership_transfer(client, conn):
    wid, [(o, ho), (m, hm)] = workspace_with(conn, "owner", "member")
    assert client.post("/api/v1/team/leave", headers=ho).status_code == 403  # owner must transfer first
    assert client.post("/api/v1/team/transfer", json={"user_id": m}, headers=hm).status_code == 403
    assert client.post("/api/v1/team/transfer", json={"user_id": o}, headers=ho).status_code == 422
    assert client.post("/api/v1/team/transfer", json={"user_id": str(uuid.uuid4())}, headers=ho).status_code == 404
    assert client.post("/api/v1/team/transfer", json={"user_id": m}, headers=ho).status_code == 200
    roles = {str(r["user_id"]): r["role"] for r in conn.execute("select user_id, role from workspace_members where workspace_id=%s", (wid,)).fetchall()}
    assert roles == {o: "admin", m: "owner"}
    assert client.post("/api/v1/team/leave", headers=ho).status_code == 204  # the former owner (now admin) can leave
    assert client.get("/api/v1/team/members", headers=ho).status_code == 403


def test_cannot_manage_members_of_other_workspaces(client, conn):
    wa, [(a, ha), (am, _)] = workspace_with(conn, "owner", "member")
    wb, [(b, hb)] = workspace_with(conn, "owner")
    assert client.delete(f"/api/v1/team/members/{am}", headers=hb).status_code == 404
    assert client.patch(f"/api/v1/team/members/{am}", json={"role": "viewer"}, headers=hb).status_code == 404
    assert conn.execute("select count(*) n from workspace_members where workspace_id=%s", (wa,)).fetchone()["n"] == 2


# ------------------------------------------------------------------ activity
def test_activity_feed_records_team_events_and_is_workspace_scoped(client, conn):
    wid, [(o, ho), (m, hm)] = workspace_with(conn, "owner", "member")
    invite(client, ho, "feed@example.com")
    client.patch(f"/api/v1/team/members/{m}", json={"role": "viewer"}, headers=ho)
    feed = client.get("/api/v1/team/activity", headers=hm).json()["activity"]
    kinds = [a["kind"] for a in feed]
    assert kinds[:2] == ["member.role_changed", "member.invited"]
    assert feed[0]["user_name"] == "T"
    other, [(b, hb)] = workspace_with(conn, "owner")
    assert client.get("/api/v1/team/activity", headers=hb).json()["activity"] == []
    assert conn.execute("select count(*) n from audit_logs where workspace_id=%s and action='member.invited'", (wid,)).fetchone()["n"] == 1
    assert len(client.get("/api/v1/team/activity?limit=1", headers=ho).json()["activity"]) == 1
    assert client.get("/api/v1/team/activity?limit=0", headers=ho).status_code == 422


def test_viewers_cannot_write_saved_work_but_can_read_the_team(client, conn):
    wid, [(o, ho), (v, hv)] = workspace_with(conn, "owner", "viewer")
    assert client.get("/api/v1/team/members", headers=hv).status_code == 200
    from .test_business_api import SCEN
    assert client.post("/api/v1/business/scenarios", json=SCEN, headers=hv).status_code == 403
