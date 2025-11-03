"""
Status endpoint for checking job progress
"""
from fastapi import APIRouter, HTTPException
from redis import Redis
from rq.job import Job

from app.core.config import settings

router = APIRouter()

redis_conn = Redis.from_url(settings.REDIS_URL)


@router.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """
    Check status of a processing job
    
    Args:
        job_id: RQ job ID
        
    Returns:
        Job status information
    """
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        
        status_info = {
            "job_id": job_id,
            "status": job.get_status(),
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "ended_at": job.ended_at.isoformat() if job.ended_at else None,
        }
        
        # Add result if completed
        if job.is_finished:
            status_info["result"] = job.result
        
        # Add error if failed
        if job.is_failed:
            status_info["error"] = str(job.exc_info)
        
        return status_info
    
    except Exception as e:
        raise HTTPException(404, f"Job not found: {job_id}")
