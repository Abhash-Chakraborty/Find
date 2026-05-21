"""
Configuration endpoints
"""

from fastapi import APIRouter

from find_api.core.config import settings

router = APIRouter()


@router.get("/config")
def get_app_config():
    """
    Return safe public application configuration
    """

    return {
        "ml_mode": settings.ML_MODE,
    }
