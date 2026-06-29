"""
Status endpoint for checking job progress
"""

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from find_api.core.config import settings
from find_api.core.dependencies import get_admin_user, get_required_user
from find_api.core.model_manager import get_model_manager
from find_api.core.queue import get_job, get_redis_connection
from find_api.models.user import User

router = APIRouter()


@router.get("/status/models")
def get_loaded_models(_admin: Optional[User] = Depends(get_admin_user)):
    """
    Get currently loaded ML models across API/worker processes.

    Exposes deployment internals, so this is admin-only in shared mode
    (no-op restriction in local mode).
    """
    manager = get_model_manager()
    local_status = manager.get_status()
    process_status = {local_status["process"]: local_status}

    try:
        redis_conn = get_redis_connection()
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
    except Exception:
        pass

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
def get_job_status(
    job_id: str,
    _user: Optional[User] = Depends(get_required_user),
):
    """
    Check status of a processing job

    Args:
        job_id: RQ job ID

    Returns:
        Job status information with stage tracking
    """
    try:
        job = get_job(job_id)

        if job is None:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

        status_info = {
            "job_id": job_id,
            "status": job.get_status(),
            "stage": job.meta.get("stage", "queued")
            if hasattr(job, "meta")
            else "queued",
            "created_at": _attr_iso(job, "created_at"),
            "started_at": _attr_iso(job, "started_at"),
            "ended_at": _attr_iso(job, "ended_at") or _attr_iso(job, "completed_at"),
        }

        if job.is_finished:
            status_info["result"] = job.result

        if job.is_failed:
            status_info["error"] = getattr(job, "error_info", None) or job.meta.get(
                "error", "Job failed"
            )
            status_info["stage"] = (
                job.meta.get("stage", "failed") if hasattr(job, "meta") else "failed"
            )

        return status_info

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Error fetching job {job_id}: {exc}"
        ) from exc


def _attr_iso(obj: Any, attr: str) -> str | None:
    """Return an ISO-formatted string for a datetime-like attribute, or None."""
    val = getattr(obj, attr, None)
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)
