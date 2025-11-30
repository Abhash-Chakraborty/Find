from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session
import logging

from app.core.database import get_db
from app.workers.jobs import cluster_images
from rq import Queue
from redis import Redis
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/cluster/trigger")
async def trigger_clustering():
    """
    Manually trigger the image clustering job
    """
    try:
        # Connect to Redis
        redis_conn = Redis.from_url(settings.REDIS_URL)
        q = Queue('default', connection=redis_conn)
        
        # Enqueue job
        job = q.enqueue(cluster_images)
        
        return {
            "status": "success",
            "message": "Clustering job triggered",
            "job_id": job.get_id()
        }
    except Exception as e:
        logger.error(f"Failed to trigger clustering: {e}")
        return {
            "status": "error",
            "message": str(e)
        }
