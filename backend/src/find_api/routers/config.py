"""
Configuration endpoints
"""

from fastapi import APIRouter

from find_api.core.config import settings
from find_api.core.hardware import detect_capabilities, resolve_execution

router = APIRouter()


@router.get("/config")
def get_app_config():
    """
    Return safe public application configuration
    """

    return {
        "ml_mode": settings.ML_MODE,
        "accel_mode": settings.ACCEL_MODE,
    }


@router.get("/config/hardware")
def get_hardware_capabilities():
    """Report detected accelerators + the execution plan for the current mode.

    Consumed by the settings panel to render the Auto/GPU/CPU toggle and show
    whether the chosen mode resolves to GPU or has fallen back to CPU.
    """
    report = detect_capabilities()
    plan = resolve_execution(settings.ACCEL_MODE, report)
    return {
        "accel_mode": settings.ACCEL_MODE,
        "capabilities": report.to_dict(),
        "resolved": plan.to_dict(),
    }
