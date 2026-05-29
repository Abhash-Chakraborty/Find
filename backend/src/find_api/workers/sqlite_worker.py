"""SQLite-backed background worker for desktop mode.

Polls the SQLite job queue table and executes jobs using the same
processing functions as the RQ worker.  Designed to run as a daemon thread
or subprocess.
"""

from __future__ import annotations

import importlib
import logging
import time
import traceback
from typing import Any

from find_api.core.queue_sqlite import (
    SQLiteJob,
    SQLiteQueue,
    _clear_current_job,
    _set_current_job,
    ensure_queue_tables,
    fail_job,
)
from find_api.utils.errors import sanitize_error

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1.0
GRACEFUL_SHUTDOWN_TIMEOUT = 30.0


def resolve_function(func_name: str) -> Any:
    """Resolve a ``module.path:function_name`` string to the callable."""
    if ":" not in func_name:
        raise ValueError(f"Invalid function spec: {func_name} (expected 'module:name')")
    module_path, name = func_name.rsplit(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, name)


def execute_job(job: SQLiteJob) -> None:
    """Execute a single job, handling success and failure.

    Sets the thread-local current job so that ``get_current_job()``
    (imported via ``find_api.core.queue``) returns the active job during
    execution.
    """
    _set_current_job(job)
    try:
        func = resolve_function(job.func_name)
        result = func(*job.args, **job.kwargs)

        from find_api.core.queue_sqlite import complete_job

        complete_job(job.id, result)
        logger.info("Job %s completed successfully", job.id)
    except Exception as exc:  # noqa: BLE001
        safe_error = sanitize_error(exc)
        tb = traceback.format_exc()
        logger.error("Job %s failed: %s\n%s", job.id, safe_error, tb)
        fail_job(job.id, safe_error)
    finally:
        _clear_current_job()


def run_worker_once(queue: SQLiteQueue) -> bool:
    """Claim and execute one job from the queue.

    Returns True if a job was processed, False if the queue was empty.
    """
    job = queue.dequeue()
    if job is None:
        return False

    logger.info("Worker picked up job %s: %s", job.id, job.func_name)
    execute_job(job)
    return True


def run_worker_loop(
    queue_name: str = "default",
    shutdown_event=None,
) -> None:
    """Run the worker loop, polling the SQLite queue until shutdown.

    Args:
        queue_name: Queue name to poll.
        shutdown_event: A threading.Event that signals shutdown when set.
    """
    ensure_queue_tables()
    queue = SQLiteQueue(queue_name)
    logger.info(
        "SQLite worker started (queue=%s, poll_interval=%ss)",
        queue_name,
        POLL_INTERVAL_SECONDS,
    )

    while True:
        if shutdown_event is not None and shutdown_event.is_set():
            logger.info("SQLite worker shutting down gracefully")
            break

        try:
            run_worker_once(queue)
        except Exception:  # noqa: BLE001
            logger.exception("Worker loop error, continuing")

        time.sleep(POLL_INTERVAL_SECONDS)

    logger.info("SQLite worker stopped")


def run_worker_blocking(
    queue_name: str = "default", max_jobs: int | None = None
) -> None:
    """Run the worker loop in the current thread (blocking).

    Processes up to ``max_jobs`` jobs, or indefinitely if None.

    Useful for the ``desktop-worker`` CLI entry point.
    """
    ensure_queue_tables()
    queue = SQLiteQueue(queue_name)
    logger.info("SQLite blocking worker started (queue=%s)", queue_name)

    processed = 0
    while max_jobs is None or processed < max_jobs:
        try:
            if run_worker_once(queue):
                processed += 1
            else:
                if max_jobs is not None:
                    break
                time.sleep(POLL_INTERVAL_SECONDS)
        except Exception:  # noqa: BLE001
            logger.exception("Worker loop error, continuing")
            time.sleep(POLL_INTERVAL_SECONDS)

    logger.info("SQLite blocking worker finished (%s jobs processed)", processed)
