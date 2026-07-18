"""Background worker that polls the SQLite job queue and executes jobs."""

from __future__ import annotations

import logging
import threading
import traceback

from find_api.core.config import settings
from find_api.core.sqlite_queue import (
    SqliteJob,
    SqliteQueue,
    _resolve_job_type,
    register_job,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL = 1.0  # seconds between polls

# Register known job types for the SQLite worker.
# The key matches the string stored by enqueue_call (module:qualname).
_JOB_REGISTRATIONS = False


def _ensure_registrations() -> None:
    global _JOB_REGISTRATIONS
    if _JOB_REGISTRATIONS:
        return
    from find_api.workers.jobs import analyze_image, cluster_images, cluster_faces

    register_job(
        f"{analyze_image.__module__}:{analyze_image.__qualname__}", analyze_image
    )
    register_job(
        f"{cluster_images.__module__}:{cluster_images.__qualname__}", cluster_images
    )
    register_job(
        f"{cluster_faces.__module__}:{cluster_faces.__qualname__}", cluster_faces
    )
    _JOB_REGISTRATIONS = True


def _dispatch(job: SqliteJob, queue: SqliteQueue) -> None:
    """Resolve and execute a single job, then mark complete/fail."""
    func = _resolve_job_type(job.type)
    if func is None:
        queue.fail(job.id, f"Unknown job type: {job.type}")
        logger.error("Unknown job type %s for job %s", job.type, job.id)
        return

    payload = job._payload if hasattr(job, "_payload") else {}
    args = payload.get("args", [])
    kwargs = payload.get("kwargs", {})

    try:
        result = func(*args, **kwargs)
        queue.complete(job.id, result)
        logger.debug("Job %s (%s) completed", job.id, job.type)
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        error_info = f"{type(exc).__name__}: {exc}\n{tb}"
        queue.fail(job.id, error_info)
        logger.error("Job %s (%s) failed: %s", job.id, job.type, exc)


def run_worker_once(queue: SqliteQueue) -> int:
    """Dequeue and execute a single job, returning 1 if a job was run else 0."""
    _ensure_registrations()
    job = queue.dequeue()
    if job is None:
        return 0
    _dispatch(job, queue)
    return 1


def run_worker_loop(
    queue: SqliteQueue | None = None,
    *,
    poll_interval: float = POLL_INTERVAL,
    stop_event: threading.Event | None = None,
) -> None:
    """Poll the queue and execute jobs until ``stop_event`` is set.

    This is the main entry point for both the background thread and the
    standalone worker process.
    """
    q = queue or SqliteQueue()
    stop = stop_event or threading.Event()

    _ensure_registrations()

    logger.info(
        "SQLite worker started (poll_interval=%ss, db=%s)", poll_interval, q._db_path
    )

    while not stop.is_set():
        try:
            q.reset_stale_running(timeout_seconds=settings.WORKER_TIMEOUT)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to reset stale jobs")

        try:
            count = 0
            job = q.dequeue()
            while job is not None:
                _dispatch(job, q)
                count += 1
                job = q.dequeue()
            if count:
                logger.info("Processed %s jobs", count)
        except Exception:  # noqa: BLE001
            logger.exception("Worker loop iteration failed")

        stop.wait(poll_interval)


WORKER_SHUTDOWN_TIMEOUT = 5.0


def start_worker_thread(
    queue: SqliteQueue | None = None,
    *,
    poll_interval: float = POLL_INTERVAL,
) -> threading.Thread:
    """Start the worker loop in a daemon thread and return it.

    Validates the queue and registrations on the calling thread so
    initialization failures surface immediately.
    """
    q = queue or SqliteQueue()
    _ensure_registrations()
    stop_event = threading.Event()
    thread = threading.Thread(
        target=run_worker_loop,
        args=(q,),
        kwargs={"poll_interval": poll_interval, "stop_event": stop_event},
        daemon=True,
        name="sqlite-worker",
    )
    thread.start()
    # Attach the stop event so callers can signal shutdown
    thread._stop_event = stop_event  # type: ignore[attr-defined]
    logger.info("SQLite worker thread started")
    return thread


def stop_worker_thread(thread: threading.Thread) -> None:
    """Signal the worker thread to stop and wait for it to exit."""
    stop_event = getattr(thread, "_stop_event", None)
    if stop_event:
        stop_event.set()
    thread.join(timeout=WORKER_SHUTDOWN_TIMEOUT)
    if thread.is_alive():
        logger.warning(
            "SQLite worker thread did not stop within %ss", WORKER_SHUTDOWN_TIMEOUT
        )


# Allow running as a standalone script::
#   python -m find_api.workers.sqlite_worker
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger.info("Starting standalone SQLite worker")
    run_worker_loop()
