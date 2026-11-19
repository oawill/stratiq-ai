"""Authentication and authorization shared by all API routers."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException

from .db import get_conn

WRITE_ROLES = {"owner", "admin", "member"}
ADMIN_ROLES = {"owner", "admin"}

@dataclass(frozen=True)
class Principal:
    user_id: str
    workspace_id: str
    role: str

def principal(authorization: Annotated[str | None, Header()] = None, conn=Depends(get_conn)) -> Principal:
    secret = os.environ.get("INTERNAL_API_SECRET", "")
    if len(secret) < 32:
        raise HTTPException(503, "Service is not configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing credentials")
    try:
        claims = jwt.decode(
            authorization[7:], secret, algorithms=["HS256"], issuer="stratiq-web",
            options={"require": ["exp", "sub", "wid", "iss"]},
        )
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired credentials")
    try:
        uuid.UUID(str(claims["sub"])), uuid.UUID(str(claims["wid"]))
    except ValueError:
        raise HTTPException(401, "Invalid credentials")
    row = conn.execute(
        "select role from workspace_members where user_id=%s and workspace_id=%s",
        (claims["sub"], claims["wid"]),
    ).fetchone()
    if not row:
        raise HTTPException(403, "Not a member of this workspace")
    return Principal(str(claims["sub"]), str(claims["wid"]), row["role"])

Auth = Annotated[Principal, Depends(principal)]

def require_write(p: Principal) -> None:
    if p.role not in WRITE_ROLES:
        raise HTTPException(403, "Your role is read-only")
