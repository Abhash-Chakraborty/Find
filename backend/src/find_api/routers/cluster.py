from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
import logging

from find_api.core.dependencies import get_admin_user
from find_api.core.queue import enqueue_clustering_job
from find_api.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/cluster/trigger")
def trigger_clustering(_admin: Optional[User] = Depends(get_admin_user)):
    """
    Manually trigger the image clustering job

    Rebuilds clusters across every uploader's media, so this is admin-only
    in shared mode (no-op restriction in local mode).
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
