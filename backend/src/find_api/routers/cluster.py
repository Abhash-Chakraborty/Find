from fastapi import APIRouter, HTTPException
import logging

from find_api.core.queue import enqueue_clustering_job

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/cluster/trigger")
def trigger_clustering():
    """
    Manually trigger the image clustering job
    """
    try:
        result = enqueue_clustering_job(reason="manual-alias")
        return {"status": "success", **result}
    except Exception as exc:
        logger.exception("Failed to trigger clustering")
        raise HTTPException(
            status_code=503,
            detail="Failed to queue clustering job. Please retry.",
        ) from exc
