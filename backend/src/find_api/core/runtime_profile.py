"""Truthful runtime/build capability resolution.

The deployment artifact (no-AI, mock, CPU, or NVIDIA) determines which
dependencies are installed. Runtime settings may disable an installed feature,
but they must never claim to install or activate a capability that is absent.
Worker jobs bind the resolved preferences through context variables so cached
model loaders use the dashboard-selected acceleration mode without mutating the
process-wide Pydantic settings object.
"""

from __future__ import annotations

import importlib.util
import json
import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from find_api.core.config import settings
from find_api.models.app_setting import AppSetting

AccelMode = Literal["auto", "gpu", "cpu"]
ConfiguredMLMode = Literal["disabled", "full", "mock", "remote"]
AppliedMLMode = Literal["disabled", "full", "mock", "unavailable"]

ACCEL_MODE_KEY = "accel_mode"
AI_ENABLED_KEY = "ai_enabled"
MAP_ENABLED_KEY = "map_enabled"
ML_MODE_KEY = "ml_mode"
RUNTIME_SETTING_KEYS = (ACCEL_MODE_KEY, AI_ENABLED_KEY, MAP_ENABLED_KEY, ML_MODE_KEY)

CORE_FEATURES = ("thumbnails", "dimensions", "exif")
MOCK_FEATURES = ("mock_inference", "semantic_search", "clustering")
FULL_FEATURES = (
    "embeddings",
    "captioning",
    "object_detection",
    "ocr",
    "face_detection",
    "semantic_search",
    "clustering",
)

_PROFILE_MODES: dict[str, tuple[str, ...]] = {
    "no-ai": ("disabled",),
    "mock": ("disabled", "mock"),
    "cpu": ("disabled", "mock", "full"),
    "nvidia": ("disabled", "mock", "full"),
}

_active_ml_mode: ContextVar[str | None] = ContextVar(
    "find_active_ml_mode", default=None
)
_active_accel_mode: ContextVar[str | None] = ContextVar(
    "find_active_accel_mode", default=None
)
_active_map_enabled: ContextVar[bool | None] = ContextVar(
    "find_active_map_enabled", default=None
)


class RuntimeUnavailableError(RuntimeError):
    """Raised when requested inference is not present in this artifact."""

    def __init__(self, resolution: "RuntimeResolution"):
        self.resolution = resolution
        super().__init__(
            resolution.unavailable_reason
            or "The configured AI runtime is unavailable in this artifact."
        )


@dataclass(frozen=True)
class RuntimePreferences:
    """Persisted instance preferences resolved with environment fallbacks."""

    accel_mode: AccelMode
    ai_enabled: bool
    map_enabled: bool
    ml_mode: ConfiguredMLMode


@dataclass(frozen=True)
class RuntimeResolution:
    """Desired runtime mapped onto the capabilities installed in this image."""

    build_profile: str
    supported_modes: tuple[str, ...]
    configured_mode: ConfiguredMLMode
    configured_accel_mode: AccelMode
    ai_enabled: bool
    map_enabled: bool
    applied_mode: AppliedMLMode
    installed_features: tuple[str, ...]
    restart_required: bool
    unavailable_reason: str | None = None

    def to_worker_status(self, *, source: str) -> dict[str, Any]:
        payload = asdict(self)
        payload["supported_modes"] = list(self.supported_modes)
        payload["installed_features"] = list(self.installed_features)
        payload["preferences_source"] = source
        return payload


def _package_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        return False


def _development_modes() -> tuple[str, ...]:
    modes = ["disabled"]
    if _package_available("numpy") and _package_available("sklearn"):
        modes.append("mock")
    full_modules = (
        "torch",
        "open_clip",
        "transformers",
        "ultralytics",
        "paddleocr",
        "insightface",
        "onnxruntime",
    )
    if all(_package_available(module) for module in full_modules):
        modes.append("full")
    return tuple(modes)


def supported_modes(build_profile: str | None = None) -> tuple[str, ...]:
    profile = build_profile or settings.FIND_BUILD_PROFILE
    if profile == "development":
        return _development_modes()
    return _PROFILE_MODES.get(profile, ("disabled",))


def installed_features(build_profile: str | None = None) -> tuple[str, ...]:
    profile = build_profile or settings.FIND_BUILD_PROFILE
    modes = supported_modes(profile)
    features = list(CORE_FEATURES)
    if "mock" in modes:
        features.extend(MOCK_FEATURES)
    if "full" in modes:
        features.extend(FULL_FEATURES)
    return tuple(dict.fromkeys(features))


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def default_runtime_preferences() -> RuntimePreferences:
    return RuntimePreferences(
        accel_mode=settings.ACCEL_MODE,
        ai_enabled=settings.AI_ENABLED,
        map_enabled=settings.MAP_ENABLED,
        ml_mode=settings.ML_MODE,
    )


def load_runtime_preferences(db: Session) -> RuntimePreferences:
    """Read all runtime preferences once at an API request/job boundary."""
    rows = db.query(AppSetting).filter(AppSetting.key.in_(RUNTIME_SETTING_KEYS)).all()
    values = {row.key: row.value for row in rows}
    accel_mode = values.get(ACCEL_MODE_KEY, settings.ACCEL_MODE)
    if accel_mode not in {"auto", "gpu", "cpu"}:
        accel_mode = settings.ACCEL_MODE
    ml_mode = values.get(ML_MODE_KEY, settings.ML_MODE)
    if ml_mode not in {"disabled", "full", "mock", "remote"}:
        ml_mode = settings.ML_MODE
    return RuntimePreferences(
        accel_mode=accel_mode,  # type: ignore[arg-type]
        ai_enabled=_parse_bool(values.get(AI_ENABLED_KEY), settings.AI_ENABLED),
        map_enabled=_parse_bool(values.get(MAP_ENABLED_KEY), settings.MAP_ENABLED),
        ml_mode=ml_mode,  # type: ignore[arg-type]
    )


def resolve_runtime(
    preferences: RuntimePreferences | None = None,
    *,
    build_profile: str | None = None,
    configured_mode: ConfiguredMLMode | None = None,
) -> RuntimeResolution:
    """Resolve preferences without ever falling into an unavailable backend."""
    preferences = preferences or default_runtime_preferences()
    profile = build_profile or settings.FIND_BUILD_PROFILE
    mode = configured_mode or preferences.ml_mode
    modes = supported_modes(profile)
    features = installed_features(profile)

    if not preferences.ai_enabled or mode == "disabled":
        applied_mode: AppliedMLMode = "disabled"
        reason = None
        restart_required = False
    elif mode == "remote":
        applied_mode = "unavailable"
        reason = (
            "Remote ML is configured but no remote inference client is installed. "
            "Find will not fall back to local inference."
        )
        restart_required = False
    elif mode not in modes:
        applied_mode = "unavailable"
        reason = (
            f"ML mode '{mode}' is not installed in the '{profile}' artifact. "
            "Start Find with a compatible CPU or NVIDIA profile."
        )
        restart_required = True
    else:
        applied_mode = mode  # type: ignore[assignment]
        reason = None
        restart_required = False

    return RuntimeResolution(
        build_profile=profile,
        supported_modes=modes,
        configured_mode=mode,
        configured_accel_mode=preferences.accel_mode,
        ai_enabled=preferences.ai_enabled,
        map_enabled=preferences.map_enabled,
        applied_mode=applied_mode,
        installed_features=features,
        restart_required=restart_required,
        unavailable_reason=reason,
    )


def bind_runtime(
    resolution: RuntimeResolution,
) -> tuple[Token[str | None], Token[str | None], Token[bool | None]]:
    """Bind a job/request runtime until :func:`reset_runtime` is called."""
    return (
        _active_ml_mode.set(resolution.applied_mode),
        _active_accel_mode.set(resolution.configured_accel_mode),
        _active_map_enabled.set(resolution.map_enabled),
    )


def reset_runtime(
    tokens: tuple[Token[str | None], Token[str | None], Token[bool | None]],
) -> None:
    _active_ml_mode.reset(tokens[0])
    _active_accel_mode.reset(tokens[1])
    _active_map_enabled.reset(tokens[2])


@contextmanager
def runtime_context(db: Session, *, source: str = "database"):
    """Resolve, bind, and publish one consistent job/request runtime snapshot."""
    resolution = resolve_runtime(load_runtime_preferences(db))
    tokens = bind_runtime(resolution)
    try:
        if source == "worker":
            from find_api.core.model_manager import get_model_manager

            get_model_manager().set_runtime_status(
                resolution.to_worker_status(source="database")
            )
        yield resolution
    finally:
        reset_runtime(tokens)


def current_ml_mode() -> str:
    return _active_ml_mode.get() or resolve_runtime().applied_mode


def current_accel_mode() -> AccelMode:
    mode = _active_accel_mode.get() or settings.ACCEL_MODE
    return mode if mode in {"auto", "gpu", "cpu"} else "auto"  # type: ignore[return-value]


def current_map_enabled() -> bool:
    value = _active_map_enabled.get()
    return settings.MAP_ENABLED if value is None else value


def get_worker_process_status() -> dict[str, Any] | None:
    """Read the worker heartbeat published by ``ModelManager`` via Redis."""
    try:
        from find_api.core.queue import get_redis_connection

        raw = get_redis_connection().get("find:model_status:worker")
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def get_worker_runtime_status() -> dict[str, Any] | None:
    status = get_worker_process_status()
    if not status:
        return None
    runtime = status.get("runtime")
    return runtime if isinstance(runtime, dict) else None


def worker_health(status: dict[str, Any] | None) -> dict[str, Any]:
    if status is None:
        return {"state": "unavailable", "age_seconds": None}
    updated_at = status.get("updated_at")
    if not isinstance(updated_at, (int, float)):
        return {"state": "unknown", "age_seconds": None}
    age = max(0.0, time.time() - float(updated_at))
    return {
        "state": "healthy" if age <= 150 else "stale",
        "age_seconds": round(age, 1),
    }
