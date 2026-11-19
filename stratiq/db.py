from __future__ import annotations

import os
from collections.abc import Iterator

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def load_dotenv_local() -> None:
    """Dev convenience: read .env.local (never used in production, where env is injected)."""
    p = ".env.local"
    if not os.path.exists(p):
        return
    for line in open(p, encoding="utf-8"):
        line = line.rstrip("\r\n")
        if "=" in line and line[:1].isalpha():
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip('"'))


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    return url


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            database_url(),
            min_size=1,
            max_size=4,
            kwargs={"row_factory": dict_row, "prepare_threshold": None},
            open=True,
        )
    return _pool


def get_conn() -> Iterator:
    """FastAPI dependency: one transaction per request, committed on success."""
    with get_pool().connection() as conn:
        yield conn
