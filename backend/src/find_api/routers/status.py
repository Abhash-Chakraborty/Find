"""
Status endpoint for checking job progress
"""

import json

from datetime import datetime

from fastapi import APIRouter, HTTPException
from redis import Redis
from rq.job import Job

from find_api.core.config import settings
from find_api.core.model_manager import get_model_manager
from find_api.core.queue import get_queue_backend

router = APIRouter()

redis_conn = Redis.from_url(settings.REDIS_URL)


@router.get("/status/models")
def get_loaded_models():
    """
    Get currently loaded ML models across API/worker processes.
    """
    manager = get_model_manager()
    local_status = manager.get_status()
    process_status = {local_status["process"]: local_status}

    for key in redis_conn.scan_iter("find:model_status:*"):
        try:
            raw_status = redis_conn.get(key)
            if not raw_status:
                continue
            status = json.loads(raw_status)
            process_name = status.get("process")
            if process_name:
                process_status[process_name] = status
        except Exception:
            continue

    loaded_models = sorted(
        {
            model_name
            for status in process_status.values()
            for model_name in status.get("loaded_models", [])
        }
    )

    return {
        "loaded_models": loaded_models,
        "processes": process_status,
        "ttl_seconds": settings.ML_MODEL_IDLE_TTL_SECONDS,
    }


@router.get("/status/{job_id}")
def get_job_status(job_id: str):
    """
    Check status of a processing job.

    Works with both RQ/Redis and SQLite backends.

    Args:
        job_id: Job ID

    Returns:
        Job status information with stage tracking
    """
    backend = get_queue_backend()

    if backend == "sqlite":
        try:
            from find_api.core.queue_sqlite import _get_connection

            conn = _get_connection()
            try:
                row = conn.execute(
                    "SELECT * FROM job_queue WHERE id = ?", (job_id,)
                ).fetchone()
                if row is None:
                    raise HTTPException(
                        status_code=404, detail=f"Job not found: {job_id}"
                    )

                def _to_iso(val: float | None) -> str | None:
                    if val is None:
                        return None
                    return datetime.fromtimestamp(val).isoformat()

                status_info = {
                    "job_id": job_id,
                    "status": row["status"],
                    "stage": "queued",
                    "created_at": _to_iso(row["created_at"]),
                    "started_at": _to_iso(row["started_at"]),
                    "ended_at": _to_iso(row["completed_at"]),
                }

                meta = {}
                if row["meta"]:
                    try:
                        meta = json.loads(row["meta"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                status_info["stage"] = meta.get("stage", row["status"])

                if row["status"] == "finished":
                    raw_result = row["result"]
                    if raw_result is not None and isinstance(raw_result, str):
                        try:
                            status_info["result"] = json.loads(raw_result)
                        except (json.JSONDecodeError, TypeError):
                            status_info["result"] = raw_result
                    else:
                        status_info["result"] = raw_result

                if row["status"] == "failed":
                    status_info["error"] = meta.get(
                        "error",
                        row["error"] if row["error"] is not None else "Job failed",
                    )
                    status_info["stage"] = meta.get("stage", "failed")

                return status_info
            finally:
                conn.close()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=404, detail=f"Job not found: {job_id}"
            ) from exc

    try:
        job = Job.fetch(job_id, connection=redis_conn)

        status_info = {
            "job_id": job_id,
            "status": job.get_status(),
            "stage": job.meta.get("stage", "queued"),
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "ended_at": job.ended_at.isoformat() if job.ended_at else None,
        }

        if job.is_finished:
            status_info["result"] = job.result

        if job.is_failed:
            status_info["error"] = job.meta.get("error", "Job failed")
            status_info["stage"] = job.meta.get("stage", "failed")

        return status_info

    except Exception:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
