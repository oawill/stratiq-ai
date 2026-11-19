"""Standalone worker for long-lived hosts:  python -m stratiq.worker

Polls for queued simulation runs and executes them. Use this where the API itself runs on
short-lived serverless functions that cannot host background threads."""
from __future__ import annotations

import logging
import time

import psycopg
from psycopg.rows import dict_row

from .db import database_url, load_dotenv_local
from .simulation_runner import execute_run, fail_stale


def main(poll_seconds: float = 2.0) -> None:
    logging.basicConfig(level=logging.INFO)
    load_dotenv_local()
    log = logging.getLogger("stratiq.worker")
    log.info("worker started")
    while True:
        try:
            with psycopg.connect(database_url(), autocommit=True, row_factory=dict_row, prepare_threshold=None) as conn:
                while True:
                    fail_stale(conn)
                    row = conn.execute(
                        "select id from simulation_runs where status='queued' order by created_at limit 1"
                    ).fetchone()
                    if row:
                        log.info("running %s", row["id"])
                        execute_run(conn, row["id"])
                    else:
                        time.sleep(poll_seconds)
        except Exception:  # noqa: BLE001 - reconnect and keep going
            log.exception("worker loop error; retrying in 5s")
            time.sleep(5)


if __name__ == "__main__":
    main()
