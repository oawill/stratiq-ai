"""Comments on saved forecasts, scenarios and simulation runs. Visible to the whole workspace; viewers can read but not write."""
from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, StringConstraints

from .db import get_conn
from .security import ADMIN_ROLES, Auth, require_write

router = APIRouter(prefix="/api/v1/comments", tags=["comments"])

# Fixed mapping from item type to table: user input never reaches the SQL text.
ITEM_TABLES = {"prediction": "predictions", "scenario": "strategic_scenarios", "simulation": "simulation_runs"}
ItemType = Literal["prediction", "scenario", "simulation"]


def _item_exists(conn, workspace_id: str, item_type: str, item_id: uuid.UUID) -> bool:
    return conn.execute(f"select 1 from {ITEM_TABLES[item_type]} where id=%s and workspace_id=%s", (item_id, workspace_id)).fetchone() is not None


@router.get("")
def list_comments(p: Auth, item_type: ItemType, item_id: uuid.UUID, conn=Depends(get_conn)):
    if not _item_exists(conn, p.workspace_id, item_type, item_id):
        raise HTTPException(404, "Item not found")
    rows = conn.execute(
        """select c.id, c.parent_id, c.body, c.created_at, c.author_id, u.name author_name
           from comments c join users u on u.id=c.author_id
           where c.workspace_id=%s and c.item_type=%s and c.item_id=%s and c.deleted_at is null
           order by c.created_at, c.id""",
        (p.workspace_id, item_type, item_id),
    ).fetchall()
    for r in rows:
        r["mine"] = str(r["author_id"]) == p.user_id
        r["can_delete"] = r["mine"] or p.role in ADMIN_ROLES
    return {"comments": rows}


class CommentBody(BaseModel):
    item_type: ItemType
    item_id: uuid.UUID
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    parent_id: uuid.UUID | None = None


@router.post("", status_code=201)
def add_comment(body: CommentBody, p: Auth, conn=Depends(get_conn)):
    require_write(p)
    if not _item_exists(conn, p.workspace_id, body.item_type, body.item_id):
        raise HTTPException(404, "Item not found")
    if body.parent_id is not None:
        parent = conn.execute(
            "select parent_id from comments where id=%s and workspace_id=%s and item_type=%s and item_id=%s and deleted_at is null",
            (body.parent_id, p.workspace_id, body.item_type, body.item_id),
        ).fetchone()
        if not parent:
            raise HTTPException(404, "The comment you are replying to was not found")
        if parent["parent_id"] is not None:
            raise HTTPException(422, "Replies go one level deep: reply to the original comment")
    row = conn.execute(
        """insert into comments (workspace_id,item_type,item_id,parent_id,author_id,body,created_at) values (%s,%s,%s,%s,%s,%s,clock_timestamp())
           returning id, created_at""",
        (p.workspace_id, body.item_type, body.item_id, body.parent_id, p.user_id, body.body),
    ).fetchone()
    label = {"prediction": "a forecast", "scenario": "a scenario", "simulation": "a simulation run"}[body.item_type]
    conn.execute(
        "insert into activity_history (workspace_id,user_id,kind,summary,ref_type,ref_id) values (%s,%s,'comment.created',%s,%s,%s)",
        (p.workspace_id, p.user_id, f"Commented on {label}", body.item_type, str(body.item_id)),
    )
    return {"id": row["id"], "created_at": row["created_at"]}


@router.delete("/{comment_id}", status_code=204)
def delete_comment(comment_id: uuid.UUID, p: Auth, conn=Depends(get_conn)):
    c = conn.execute(
        "select author_id from comments where id=%s and workspace_id=%s and deleted_at is null", (comment_id, p.workspace_id)
    ).fetchone()
    if not c:
        raise HTTPException(404, "Comment not found")
    if str(c["author_id"]) != p.user_id and p.role not in ADMIN_ROLES:
        raise HTTPException(403, "You can only delete your own comments")
    # Deleting a comment also hides its replies.
    conn.execute("update comments set deleted_at=now() where workspace_id=%s and (id=%s or parent_id=%s) and deleted_at is null", (p.workspace_id, comment_id, comment_id))
