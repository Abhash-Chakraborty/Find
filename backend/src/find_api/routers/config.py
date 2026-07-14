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
from find_api.core.runtime_profile import (
    ACCEL_MODE_KEY,
    AI_ENABLED_KEY,
    MAP_ENABLED_KEY,
    ML_MODE_KEY,
    get_worker_process_status,
    get_worker_runtime_status,
    load_runtime_preferences,
    resolve_runtime,
    worker_health,
)
from find_api.models.app_setting import AppSetting
from find_api.models.user import User

router = APIRouter()

_VALID_ACCEL_MODES = ("auto", "gpu", "cpu")
TRASH_RETENTION_DAYS_KEY = "trash_retention_days"


def get_setting(db: Session, key: str, default: str) -> str:
    """Read a persisted setting, falling back to ``default`` (the env value)."""
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row is not None else default


def _effective_accel_mode(db: Session) -> str:
    """The accel mode in force: the persisted preference, else the env default."""
    return get_setting(db, ACCEL_MODE_KEY, settings.ACCEL_MODE)


def _trash_retention_days(db: Session) -> int:
    raw = get_setting(
        db,
        TRASH_RETENTION_DAYS_KEY,
        str(settings.TRASH_RETENTION_DAYS),
    )
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return settings.TRASH_RETENTION_DAYS
    return value if 0 <= value <= 3650 else settings.TRASH_RETENTION_DAYS


def _runtime_resolution(db: Session):
    return resolve_runtime(load_runtime_preferences(db))


@router.get("/config")
def get_app_config(db: Session = Depends(get_db)):
    """
    Return safe public application configuration
    """

    runtime = _runtime_resolution(db)
    return {
        "ml_mode": runtime.applied_mode,
        "configured_ml_mode": runtime.configured_mode,
        "accel_mode": runtime.configured_accel_mode,
        "ai_enabled": runtime.ai_enabled,
        "map_enabled": runtime.map_enabled,
        "build_profile": runtime.build_profile,
        "supported_ml_modes": list(runtime.supported_modes),
    }


@router.get("/config/runtime")
def get_runtime_config(db: Session = Depends(get_db)):
    """Report installed capabilities, desired state, and worker-applied state."""
    runtime = _runtime_resolution(db)
    report = detect_capabilities()
    plan = resolve_execution(runtime.configured_accel_mode, report)
    worker_process = get_worker_process_status()
    payload = runtime.to_worker_status(source="database")
    payload.update(
        {
            "hardware": {
                "capabilities": report.to_dict(),
                "resolved": plan.to_dict(),
            },
            "worker": {
                "health": worker_health(worker_process),
                "applied": get_worker_runtime_status(),
            },
        }
    )
    return payload


@router.get("/config/hardware")
def get_hardware_capabilities(db: Session = Depends(get_db)):
    """Report detected accelerators + the execution plan for the current mode.

    Consumed by the settings panel to render the Auto/GPU/CPU toggle and show
    whether the chosen mode resolves to GPU or has fallen back to CPU. The mode
    is the persisted preference when set, else the env default.
    """
    mode = load_runtime_preferences(db).accel_mode
    report = detect_capabilities()
    plan = resolve_execution(mode, report)
    return {
        "accel_mode": mode,
        "capabilities": report.to_dict(),
        "resolved": plan.to_dict(),
    }


class SettingsResponse(BaseModel):
    accel_mode: Literal["auto", "gpu", "cpu"]
    ai_enabled: bool
    map_enabled: bool
    ml_mode: Literal["disabled", "full", "mock", "remote"]
    supported_ml_modes: list[str]
    trash_retention_days: int


class SettingsUpdate(BaseModel):
    accel_mode: Optional[Literal["auto", "gpu", "cpu"]] = None
    ai_enabled: Optional[bool] = None
    map_enabled: Optional[bool] = None
    ml_mode: Optional[Literal["disabled", "full", "mock", "remote"]] = None
    trash_retention_days: Optional[int] = None


def _settings_response(db: Session) -> SettingsResponse:
    preferences = load_runtime_preferences(db)
    return SettingsResponse(
        accel_mode=preferences.accel_mode,
        ai_enabled=preferences.ai_enabled,
        map_enabled=preferences.map_enabled,
        ml_mode=preferences.ml_mode,
        supported_ml_modes=list(resolve_runtime(preferences).supported_modes),
        trash_retention_days=_trash_retention_days(db),
    )


def _upsert_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value


@router.get("/settings", response_model=SettingsResponse)
def get_settings(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_required_user),
):
    """Return the persisted, runtime-adjustable settings.

    Readable by any authenticated user (or anyone in local mode) so the
    settings panel can show the saved values.
    """
    return _settings_response(db)


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
        _upsert_setting(db, ACCEL_MODE_KEY, request.accel_mode)

    if request.ai_enabled is not None:
        _upsert_setting(db, AI_ENABLED_KEY, str(request.ai_enabled).lower())

    if request.map_enabled is not None:
        _upsert_setting(db, MAP_ENABLED_KEY, str(request.map_enabled).lower())

    if request.ml_mode is not None:
        modes = resolve_runtime(load_runtime_preferences(db)).supported_modes
        if request.ml_mode not in modes:
            raise HTTPException(
                422,
                f"ML mode '{request.ml_mode}' is not installed in this artifact",
            )
        _upsert_setting(db, ML_MODE_KEY, request.ml_mode)

    if request.trash_retention_days is not None:
        if not 0 <= request.trash_retention_days <= 3650:
            raise HTTPException(
                422,
                "trash_retention_days must be between 0 and 3650",
            )
        _upsert_setting(
            db,
            TRASH_RETENTION_DAYS_KEY,
            str(request.trash_retention_days),
        )

    if request.model_fields_set:
        db.commit()

    return _settings_response(db)
