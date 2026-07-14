"""Collect a privacy-safe local diagnostics bundle.

All collection stays on-box. The returned structure is passed through the
redaction layer before it is returned to callers.
"""

from __future__ import annotations

import logging
import os
import platform
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from find_api import __version__
from find_api.core.config import settings
from find_api.diagnostics.redact import redact_payload, scrub_string
from find_api.utils.errors import sanitize_error

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
ERROR_LOG_LIMIT = 20

PRIVACY_NOTICE = (
    "Local diagnostics only. This bundle is generated on-request, never "
    "uploaded automatically, and is redacted to exclude passwords, tokens, "
    "storage keys, paths, filenames, captions, OCR, embeddings, faces, and "
    "user identifiers. Attach it to a GitHub issue only after reviewing it."
)


class _ErrorLogBuffer(logging.Handler):
    """Keep the last N ERROR+ log records in memory for diagnostics."""

    def __init__(self, capacity: int = ERROR_LOG_LIMIT) -> None:
        super().__init__(level=logging.ERROR)
        self._records: deque[dict[str, Any]] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record) if self.formatter else record.getMessage()
            self._records.append(
                {
                    "timestamp": datetime.fromtimestamp(
                        record.created, tz=timezone.utc
                    ).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": scrub_string(message),
                    "source": "log",
                }
            )
        except Exception:  # noqa: BLE001 — never break the logging pipeline
            self.handleError(record)

    def snapshot(self) -> list[dict[str, Any]]:
        self.acquire()
        try:
            return list(self._records)
        finally:
            self.release()


_error_buffer = _ErrorLogBuffer()
_error_buffer.name = "find_diagnostics_error_buffer"
_buffer_installed = False


def ensure_error_log_buffer() -> None:
    """Attach the in-process error ring buffer to the root logger once.

    Uses a stable handler ``name`` check (not ``isinstance``) so uvicorn
    ``--reload`` re-imports do not stack duplicate buffers when the class
    object identity changes across reloads.
    """
    global _buffer_installed
    if _buffer_installed:
        return
    root = logging.getLogger()
    if not any(
        getattr(h, "name", None) == _error_buffer.name for h in root.handlers
    ):
        root.addHandler(_error_buffer)
    _buffer_installed = True


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _check_postgresql() -> dict[str, Any]:
    started = time.perf_counter()
    try:
        from sqlalchemy import text

        from find_api.core.database import engine

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {
            "ok": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": scrub_string(sanitize_error(exc)),
        }


def _check_redis() -> dict[str, Any]:
    started = time.perf_counter()
    try:
        from redis import Redis

        client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        client.ping()
        return {
            "ok": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": scrub_string(sanitize_error(exc)),
        }


def _check_storage() -> dict[str, Any]:
    started = time.perf_counter()
    backend = settings.STORAGE_BACKEND.lower()
    try:
        if backend == "local":
            path = Path(settings.LOCAL_STORAGE_PATH)
            reachable = path.is_dir() and os.access(path, os.W_OK)
            result: dict[str, Any] = {
                "ok": reachable,
                "backend": "local",
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
            if not reachable:
                result["error"] = (
                    "Local storage path is not a writable directory"
                )
            return result

        from minio import Minio

        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        exists = client.bucket_exists(settings.MINIO_BUCKET)
        return {
            "ok": bool(exists),
            "backend": "minio",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            **({} if exists else {"error": "Configured bucket not found"}),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "backend": backend,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": scrub_string(sanitize_error(exc)),
        }


def _collect_migration_state() -> dict[str, Any]:
    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory

        from find_api.core.database import engine

        backend_root = Path(__file__).resolve().parents[3]
        ini_path = backend_root / "alembic.ini"
        if not ini_path.is_file():
            return {
                "status": "unavailable",
                "current": None,
                "heads": [],
                "detail": "alembic.ini not found",
            }

        cfg = Config(str(ini_path))
        cfg.set_main_option("script_location", str(backend_root / "alembic"))
        script = ScriptDirectory.from_config(cfg)
        heads = list(script.get_heads())

        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current = context.get_current_revision()

        if current is None and not heads:
            status = "empty"
        elif current in heads or (current is not None and set(heads) <= {current}):
            status = "ok"
        elif current is None:
            status = "unmigrated"
        else:
            status = "behind"

        return {
            "status": status,
            "current": current,
            "heads": heads,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unavailable",
            "current": None,
            "heads": [],
            "detail": scrub_string(sanitize_error(exc)),
        }


def _collect_queue_stats() -> dict[str, Any]:
    mode = settings.QUEUE_MODE
    try:
        if mode == "sqlite":
            from find_api.core.queue import _get_backend

            backend = _get_backend()
            counts = backend.count_by_status()
            queued = int(counts.get("queued", 0))
            started = int(counts.get("running", 0)) + int(counts.get("started", 0))
            failed = int(counts.get("failed", 0))
            finished = int(counts.get("finished", 0)) + int(
                counts.get("completed", 0)
            )
            return {
                "mode": mode,
                "depth": queued,
                "queued": queued,
                "started": started,
                "failed": failed,
                "finished": finished,
            }

        from rq import Queue
        from rq.registry import FailedJobRegistry, StartedJobRegistry

        from find_api.core.queue import get_redis_connection

        conn = get_redis_connection()
        queue_names = ("high", "default", "low")
        queued = 0
        started = 0
        failed = 0
        finished = 0
        deferred = 0
        scheduled = 0

        for name in queue_names:
            q = Queue(name, connection=conn)
            queued += len(q)
            started += len(StartedJobRegistry(queue=q))
            failed += len(FailedJobRegistry(queue=q))
            try:
                finished += len(q.finished_job_registry)
            except Exception:  # noqa: BLE001
                pass
            try:
                deferred += len(q.deferred_job_registry)
            except Exception:  # noqa: BLE001
                pass
            try:
                scheduled += len(q.scheduled_job_registry)
            except Exception:  # noqa: BLE001
                pass

        return {
            "mode": mode,
            "depth": queued,
            "queued": queued,
            "started": started,
            "failed": failed,
            "finished": finished,
            "deferred": deferred,
            "scheduled": scheduled,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "mode": mode,
            "depth": 0,
            "queued": 0,
            "started": 0,
            "failed": 0,
            "error": scrub_string(sanitize_error(exc)),
        }


def _collect_model_state() -> dict[str, Any]:
    loaded: list[str] = []
    try:
        from find_api.core.model_manager import get_model_manager

        status = get_model_manager().get_status()
        loaded = sorted(status.get("loaded_models") or [])
    except Exception:  # noqa: BLE001
        loaded = []

    return {
        "ml_mode": settings.ML_MODE,
        "accel_mode": settings.ACCEL_MODE,
        "clip_model": settings.CLIP_MODEL,
        "clip_pretrained": settings.CLIP_PRETRAINED,
        "blip_model": settings.BLIP_MODEL,
        "yolo_model": settings.YOLO_MODEL,
        "use_gpu": settings.USE_GPU,
        "embedding_dim": settings.EMBEDDING_DIM,
        "queue_mode": settings.QUEUE_MODE,
        "storage_backend": settings.STORAGE_BACKEND,
        "remote_ml_configured": bool(
            settings.REMOTE_ML_URL and settings.REMOTE_ML_API_KEY
        ),
        "configured_models": sorted(
            {
                settings.CLIP_MODEL,
                settings.BLIP_MODEL,
                settings.YOLO_MODEL,
            }
        ),
        "loaded_models": loaded,
    }


def _collect_recent_errors() -> list[dict[str, Any]]:
    """Merge in-process ERROR logs with recent media analysis failures."""
    ensure_error_log_buffer()
    entries = _error_buffer.snapshot()

    try:
        from find_api.core.database import SessionLocal
        from find_api.models.media import Media

        db = SessionLocal()
        try:
            rows = (
                db.query(Media.error_message, Media.updated_at, Media.created_at)
                .filter(Media.status == "failed", Media.error_message.isnot(None))
                .order_by(Media.id.desc())
                .limit(ERROR_LOG_LIMIT)
                .all()
            )
            for error_message, updated_at, created_at in rows:
                ts = updated_at or created_at
                entries.append(
                    {
                        "timestamp": ts.isoformat() if ts is not None else None,
                        "level": "ERROR",
                        "logger": "media.analysis",
                        "message": scrub_string(str(error_message)),
                        "source": "media",
                    }
                )
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not load media analysis errors: %s", exc)

    # Newest first; keep a stable privacy-safe capped list.
    def _sort_key(item: dict[str, Any]) -> str:
        return item.get("timestamp") or ""

    entries.sort(key=_sort_key, reverse=True)
    return entries[:ERROR_LOG_LIMIT]


def collect_diagnostics_bundle() -> dict[str, Any]:
    """Build and redact a structured diagnostics bundle dict.

    The result is suitable for returning as JSON from an admin endpoint or
    writing to a local file. It never initiates network uploads.
    """
    ensure_error_log_buffer()

    raw: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "privacy_notice": PRIVACY_NOTICE,
        "app": {
            "version": __version__,
            "environment": settings.ENVIRONMENT,
        },
        "runtime": {
            "python_version": sys.version.split()[0],
            "python_implementation": platform.python_implementation(),
            "platform": platform.system(),
            "platform_release": platform.release(),
            "platform_machine": platform.machine(),
        },
        "migrations": _collect_migration_state(),
        "services": {
            "postgresql": _check_postgresql(),
            "redis": _check_redis(),
            "storage": _check_storage(),
        },
        "queue": _collect_queue_stats(),
        "models": _collect_model_state(),
        "errors": _collect_recent_errors(),
    }
    return redact_payload(raw)
