"""
Status endpoint for checking job progress
"""

from fastapi import APIRouter, HTTPException
from redis import Redis
from rq.job import Job

from find_api.core.config import settings

router = APIRouter()

redis_conn = Redis.from_url(settings.REDIS_URL)


@router.get("/status/{job_id}")
def get_job_status(job_id: str):
    """
    Check status of a processing job

    Args:
        job_id: RQ job ID

    Returns:
        Job status information with stage tracking
    """
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
