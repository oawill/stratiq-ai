"""Team management: members, invitations, roles, leaving, ownership transfer and the workspace activity feed.

Roles, highest first: owner, admin, member, viewer.
- owner:  everything, including inviting admins, changing any role, removing anyone and transferring ownership.
- admin:  invite members and viewers, change member/viewer roles, remove members and viewers.
- member: read and write saved work. viewer: read only.
Invitations are bound to an email address and carry a single-use token (only its SHA-256 is stored). Accepting one is done by
the web app, which checks that the signed-in user's email matches the invitation.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, StringConstraints

from . import plans
from .db import get_conn
from .security import ADMIN_ROLES, Auth, Principal

router = APIRouter(prefix="/api/v1/team", tags=["team"])

INVITE_TTL = timedelta(days=7)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
Email = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=3, max_length=254)]


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _log(conn, p: Principal, kind: str, summary: str, detail: dict | None = None, ref_type: str | None = None, ref_id: str | None = None):
    """Record a team event in both the visible activity feed and the audit log."""
    conn.execute(
        "insert into activity_history (workspace_id,user_id,kind,summary,ref_type,ref_id) values (%s,%s,%s,%s,%s,%s)",
        (p.workspace_id, p.user_id, kind, summary, ref_type, ref_id),
    )
    conn.execute(
        "insert into audit_logs (workspace_id,user_id,action,detail) values (%s,%s,%s,%s)",
        (p.workspace_id, p.user_id, kind, json.dumps(detail or {})),
    )


def require_admin(p: Principal) -> None:
    if p.role not in ADMIN_ROLES:
        raise HTTPException(403, "Only workspace owners and admins can do this")


def _seats(conn, workspace_id: str) -> dict:
    members = conn.execute("select count(*) n from workspace_members where workspace_id=%s", (workspace_id,)).fetchone()["n"]
    pending = conn.execute(
        "select count(*) n from workspace_invites where workspace_id=%s and accepted_at is null and revoked_at is null and expires_at > now()",
        (workspace_id,),
    ).fetchone()["n"]
    return {"members": int(members), "pending": int(pending), "cap": plans.seat_cap(conn, workspace_id)}


@router.get("/members")
def members(p: Auth, conn=Depends(get_conn)):
    rows = conn.execute(
        """select u.id user_id, u.name, u.email, m.role, m.created_at joined_at
           from workspace_members m join users u on u.id=m.user_id
           where m.workspace_id=%s
           order by case m.role when 'owner' then 0 when 'admin' then 1 when 'member' then 2 else 3 end, m.created_at""",
        (p.workspace_id,),
    ).fetchall()
    invites = []
    if p.role in ADMIN_ROLES:  # invitation emails are only shown to people who manage the team
        invites = conn.execute(
            """select i.id, i.email, i.role, i.created_at, i.expires_at, u.name invited_by_name
               from workspace_invites i left join users u on u.id=i.invited_by
               where i.workspace_id=%s and i.accepted_at is null and i.revoked_at is null and i.expires_at > now()
               order by i.created_at desc""",
            (p.workspace_id,),
        ).fetchall()
    return {"me": {"user_id": p.user_id, "role": p.role}, "members": rows, "invites": invites, "seats": _seats(conn, p.workspace_id)}


class InviteBody(BaseModel):
    email: Email
    role: Literal["admin", "member", "viewer"] = "member"


@router.post("/invites", status_code=201)
def create_invite(body: InviteBody, p: Auth, conn=Depends(get_conn)):
    require_admin(p)
    if not EMAIL_RE.match(body.email):
        raise HTTPException(422, "Enter a valid email address")
    if body.role == "admin" and p.role != "owner":
        raise HTTPException(403, "Only the owner can invite admins")
    existing = conn.execute(
        "select 1 from workspace_members m join users u on u.id=m.user_id where m.workspace_id=%s and u.email=%s",
        (p.workspace_id, body.email),
    ).fetchone()
    if existing:
        raise HTTPException(409, "That person is already a member of this workspace")
    # Re-inviting the same address replaces the earlier invitation (and its link), without using a second seat.
    conn.execute(
        "update workspace_invites set revoked_at=now() where workspace_id=%s and email=%s and accepted_at is null and revoked_at is null",
        (p.workspace_id, body.email),
    )
    seats = _seats(conn, p.workspace_id)
    if seats["cap"] is not None and seats["members"] + seats["pending"] >= seats["cap"]:
        raise HTTPException(402, {"code": "seat_limit", "message": f"Your plan allows {seats['cap']} members including pending invitations. Upgrade for more."})
    token = secrets.token_urlsafe(32)
    row = conn.execute(
        """insert into workspace_invites (workspace_id,email,role,token_hash,invited_by,expires_at)
           values (%s,%s,%s,%s,%s,%s) returning id, expires_at""",
        (p.workspace_id, body.email, body.role, hash_token(token), p.user_id, _now() + INVITE_TTL),
    ).fetchone()
    _log(conn, p, "member.invited", f"Invited {body.email} as {body.role}", {"invite_id": str(row["id"]), "email": body.email, "role": body.role})
    # The token is returned exactly once, here; only its hash is stored.
    return {"id": row["id"], "email": body.email, "role": body.role, "expires_at": row["expires_at"], "token": token}


@router.delete("/invites/{invite_id}", status_code=204)
def revoke_invite(invite_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    require_admin(p)
    row = conn.execute(
        "update workspace_invites set revoked_at=now() where id=%s and workspace_id=%s and accepted_at is null and revoked_at is null returning email",
        (invite_id, p.workspace_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Invitation not found")
    _log(conn, p, "member.invite_revoked", f"Cancelled the invitation for {row['email']}", {"invite_id": str(invite_id)})


class RoleBody(BaseModel):
    role: Literal["admin", "member", "viewer"]


def _target(conn, p: Principal, user_id: uuid.UUID):
    row = conn.execute(
        "select m.role, u.name, u.email from workspace_members m join users u on u.id=m.user_id where m.workspace_id=%s and m.user_id=%s",
        (p.workspace_id, user_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Member not found")
    return row


@router.patch("/members/{user_id}")
def change_role(user_id: uuid.UUID, body: RoleBody, p: Auth, conn=Depends(get_conn)):
    require_admin(p)
    if str(user_id) == p.user_id:
        raise HTTPException(403, "You cannot change your own role")
    t = _target(conn, p, user_id)
    if t["role"] == "owner":
        raise HTTPException(403, "The owner's role can only change by transferring ownership")
    if p.role == "admin" and (t["role"] not in ("member", "viewer") or body.role not in ("member", "viewer")):
        raise HTTPException(403, "Admins can only change members and viewers; the owner manages admins")
    conn.execute("update workspace_members set role=%s where workspace_id=%s and user_id=%s", (body.role, p.workspace_id, user_id))
    _log(conn, p, "member.role_changed", f"Changed {t['name']} from {t['role']} to {body.role}", {"user_id": str(user_id), "from": t["role"], "to": body.role})
    return {"user_id": str(user_id), "role": body.role}


def _drop_member(conn, workspace_id: str, user_id) -> None:
    conn.execute("delete from workspace_members where workspace_id=%s and user_id=%s", (workspace_id, user_id))
    conn.execute("update users set active_workspace_id=null where id=%s and active_workspace_id=%s", (user_id, workspace_id))


@router.delete("/members/{user_id}", status_code=204)
def remove_member(user_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    require_admin(p)
    if str(user_id) == p.user_id:
        raise HTTPException(403, "Use Leave workspace to remove yourself")
    t = _target(conn, p, user_id)
    if t["role"] == "owner":
        raise HTTPException(403, "The owner cannot be removed")
    if p.role == "admin" and t["role"] not in ("member", "viewer"):
        raise HTTPException(403, "Admins can only remove members and viewers")
    _drop_member(conn, p.workspace_id, user_id)
    _log(conn, p, "member.removed", f"Removed {t['name']} from the workspace", {"user_id": str(user_id)})


@router.post("/leave", status_code=204)
def leave(p: Auth, conn=Depends(get_conn)):
    if p.role == "owner":
        raise HTTPException(403, "The owner cannot leave. Transfer ownership first")
    me = conn.execute("select name from users where id=%s", (p.user_id,)).fetchone()
    _drop_member(conn, p.workspace_id, p.user_id)
    _log(conn, p, "member.left", f"{me['name']} left the workspace", {"user_id": p.user_id})


class TransferBody(BaseModel):
    user_id: uuid.UUID


@router.post("/transfer")
def transfer_ownership(body: TransferBody, p: Auth, conn=Depends(get_conn)):
    if p.role != "owner":
        raise HTTPException(403, "Only the owner can transfer ownership")
    if str(body.user_id) == p.user_id:
        raise HTTPException(422, "You already own this workspace")
    t = _target(conn, p, body.user_id)
    conn.execute("update workspace_members set role='owner' where workspace_id=%s and user_id=%s", (p.workspace_id, body.user_id))
    conn.execute("update workspace_members set role='admin' where workspace_id=%s and user_id=%s", (p.workspace_id, p.user_id))
    _log(conn, p, "workspace.ownership_transferred", f"Transferred ownership to {t['name']}", {"to": str(body.user_id)})
    return {"owner": str(body.user_id)}


@router.get("/activity")
def activity(p: Auth, conn=Depends(get_conn), limit: Annotated[int, Query(ge=1, le=100)] = 50):
    rows = conn.execute(
        """select a.id, a.kind, a.summary, a.ref_type, a.ref_id, a.created_at, u.name user_name
           from activity_history a left join users u on u.id=a.user_id
           where a.workspace_id=%s order by a.created_at desc, a.id desc limit %s""",
        (p.workspace_id, limit),
    ).fetchall()
    return {"activity": rows}
