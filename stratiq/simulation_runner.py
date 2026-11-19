"""Executes queued simulation runs. Claiming is atomic, so an in-process thread and a standalone
worker (`python -m stratiq.worker`) can coexist without ever running the same job twice."""
from __future__ import annotations

import json
import logging
import threading
import time

import psycopg
from psycopg.rows import dict_row

from . import simulation as sim
from .db import database_url

log = logging.getLogger("stratiq.simulation")
STALE_SECONDS = 60


def fail_stale(conn, workspace_id: str | None = None) -> None:
    """A running job whose heartbeat stopped (worker crashed or was redeployed) is marked failed, honestly."""
    conn.execute(
        """update simulation_runs set status='failed', finished_at=now(),
                  error='The worker stopped responding before this run finished. Start it again.'
           where status='running' and heartbeat_at < now() - make_interval(secs => %s)
             and (%s::uuid is null or workspace_id = %s::uuid)""",
        (STALE_SECONDS, workspace_id, workspace_id),
    )


def execute_run(conn, run_id) -> None:
    """Claim and run one job on `conn`. Safe to call when the job is not queued (it then does nothing)."""
    row = conn.execute(
        """update simulation_runs set status='running', started_at=now(), heartbeat_at=now(), progress=0
           where id=%s and status='queued' returning config, seed, iterations""",
        (run_id,),
    ).fetchone()
    if not row:
        return
    last = [0.0]

    def progress(done: int, total: int) -> bool:
        now = time.monotonic()
        if done < total and now - last[0] < 0.4:
            return True
        last[0] = now
        alive = conn.execute(
            "update simulation_runs set progress=%s, heartbeat_at=now() where id=%s and status='running' returning id",
            (done / total, run_id),
        ).fetchone()
        return alive is not None  # row gone from 'running' => cancelled

    try:
        c = row["config"]
        cfg = sim.parse_config(row["iterations"], row["seed"], c["variables"], c["outputs"])
        result = sim.run(cfg, progress=progress)
        conn.execute(
            "update simulation_runs set status='completed', progress=1, result=%s, finished_at=now() "
            "where id=%s and status='running'",
            (json.dumps(result), run_id),
        )
    except sim.Cancelled:
        conn.execute("update simulation_runs set finished_at=now() where id=%s and status='cancelled'", (run_id,))
    except (sim.SimulationError, sim.ConfigError) as e:
        conn.execute(
            "update simulation_runs set status='failed', error=%s, finished_at=now() where id=%s and status='running'",
            (str(e), run_id),
        )
    except Exception:  # noqa: BLE001 - never leave a job in 'running'
        log.exception("simulation %s crashed", run_id)
        conn.execute(
            "update simulation_runs set status='failed', error=%s, finished_at=now() where id=%s and status='running'",
            ("Internal error while running the simulation.", run_id),
        )


def _thread_main(run_id) -> None:
    try:
        with psycopg.connect(database_url(), autocommit=True, row_factory=dict_row, prepare_threshold=None) as conn:
            execute_run(conn, run_id)
    except Exception:  # noqa: BLE001
        log.exception("simulation thread failed for %s", run_id)


def start_in_thread(run_id) -> None:
    """Fire-and-forget execution inside the API process (needs a long-lived server process)."""
    threading.Thread(target=_thread_main, args=(str(run_id),), daemon=True, name=f"sim-{run_id}").start()
