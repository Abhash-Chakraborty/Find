"""
Configuration endpoints
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from find_api.core.config import settings
from find_api.core.database import get_db
from find_api.core.dependencies import get_admin_user, get_required_user
from find_api.core.hardware import detect_capabilities, resolve_execution
from find_api.models.app_setting import AppSetting
from find_api.models.user import User

router = APIRouter()

# The persisted-settings key for the hardware-acceleration mode. Kept narrow on
# purpose (YAGNI): only settings the UI actually exposes + persists live here.
ACCEL_MODE_KEY = "accel_mode"
_VALID_ACCEL_MODES = ("auto", "gpu", "cpu")


def get_setting(db: Session, key: str, default: str) -> str:
    """Read a persisted setting, falling back to ``default`` (the env value)."""
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row is not None else default


def _effective_accel_mode(db: Session) -> str:
    """The accel mode in force: the persisted preference, else the env default."""
    return get_setting(db, ACCEL_MODE_KEY, settings.ACCEL_MODE)


@router.get("/config")
def get_app_config(db: Session = Depends(get_db)):
    """
    Return safe public application configuration
    """

    return {
        "ml_mode": settings.ML_MODE,
        "accel_mode": _effective_accel_mode(db),
    }


@router.get("/config/hardware")
def get_hardware_capabilities(db: Session = Depends(get_db)):
    """Report detected accelerators + the execution plan for the current mode.

    Consumed by the settings panel to render the Auto/GPU/CPU toggle and show
    whether the chosen mode resolves to GPU or has fallen back to CPU. The mode
    is the persisted preference when set, else the env default.
    """
    mode = _effective_accel_mode(db)
    report = detect_capabilities()
    plan = resolve_execution(mode, report)
    return {
        "accel_mode": mode,
        "capabilities": report.to_dict(),
        "resolved": plan.to_dict(),
    }


class SettingsResponse(BaseModel):
    accel_mode: str


class SettingsUpdate(BaseModel):
    accel_mode: Optional[Literal["auto", "gpu", "cpu"]] = None


@router.get("/settings", response_model=SettingsResponse)
def get_settings(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Return the persisted, runtime-adjustable settings.

    Readable by any authenticated user (or anyone in local mode) so the
    settings panel can show the saved values.
    """
    return SettingsResponse(accel_mode=_effective_accel_mode(db))


@router.put("/settings", response_model=SettingsResponse)
def update_settings(
    request: SettingsUpdate,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_admin_user),
):
    """Persist runtime-adjustable settings.

    Admin-only in shared mode (open in local mode), mirroring other
    instance-wide configuration. Only fields present in the request are
    changed. The value is read back immediately by this API process; see
    models/app_setting.py for the cross-process propagation caveat.
    """
    if request.accel_mode is not None:
        # Defensive: Literal already constrains this, but guard the raw write.
        if request.accel_mode not in _VALID_ACCEL_MODES:
            raise HTTPException(422, "accel_mode must be one of auto, gpu, cpu")
        row = db.query(AppSetting).filter(AppSetting.key == ACCEL_MODE_KEY).first()
        if row is None:
            db.add(AppSetting(key=ACCEL_MODE_KEY, value=request.accel_mode))
        else:
            row.value = request.accel_mode
        db.commit()

    return SettingsResponse(accel_mode=_effective_accel_mode(db))
