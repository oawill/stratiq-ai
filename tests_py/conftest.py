"""API integration tests run against the real Postgres schema inside a transaction that is
ALWAYS rolled back, so no test data is ever committed."""
import os
import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from stratiq.db import database_url, load_dotenv_local

load_dotenv_local()
os.environ["INTERNAL_API_SECRET"] = "t" * 40

import psycopg  # noqa: E402

from stratiq.api import app  # noqa: E402
from stratiq.db import get_conn  # noqa: E402


@pytest.fixture()
def conn():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not configured")
    c = psycopg.connect(database_url(), row_factory=dict_row, prepare_threshold=None)
    try:
        yield c
    finally:
        c.rollback()
        c.close()


@pytest.fixture()
def client(conn):
    app.dependency_overrides[get_conn] = lambda: conn
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_user(conn, role="owner", workspace_id=None):
    uid = uuid.uuid4()
    conn.execute(
        "insert into users (id,email,name,password_hash) values (%s,%s,'T',%s)",
        (uid, f"{uid}@test.invalid", "x"),
    )
    if workspace_id is None:
        workspace_id = uuid.uuid4()
        conn.execute("insert into workspaces (id,name) values (%s,'W')", (workspace_id,))
    conn.execute("insert into workspace_members (workspace_id,user_id,role) values (%s,%s,%s)", (workspace_id, uid, role))
    return str(uid), str(workspace_id)


def token(uid, wid, exp_in=60, secret="t" * 40, iss="stratiq-web"):
    return jwt.encode({"sub": uid, "wid": wid, "iss": iss, "exp": int(time.time()) + exp_in}, secret, algorithm="HS256")


def hdr(uid, wid, **kw):
    return {"Authorization": f"Bearer {token(uid, wid, **kw)}"}
