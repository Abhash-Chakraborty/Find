"""Model footprint reporting.

Builds a read-only inventory of the ML models Find can load: configured
identifier, on-disk cache footprint, loaded/unloaded state, execution
device, and last-use time. Consumed by:

- ``GET /status/models/footprint`` (admin-only; never returns filesystem
  paths — see ``build_report(include_paths=False)``).
- ``backend/scripts/model_footprint_report.py`` (local CLI; may show paths
  since it runs with the operator's own filesystem access).

Design constraints (tracked by issue #339, the CPU-only runtime profile):

- Never downloads model weights. Every lookup here is a local filesystem
  read, or a read of a local cache *index* (``huggingface_hub.scan_cache_dir``
  reads on-disk metadata only, no network).
- Never raises. Any failure to resolve a cache location degrades to
  "not cached" rather than crashing the report.
- Never exposes credentials or private media metadata. The only thing this
  module reads is ML model cache directories, not user data.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from find_api.core.config import settings
from find_api.core.hardware import (
    current_torch_device,
    detect_capabilities,
    resolve_execution,
)
from find_api.core.model_manager import get_model_manager

# --- Pack identifiers --------------------------------------------------------
PACK_LIGHT = "light"
PACK_FULL = "full"
PACK_PROPOSED_CPU = "proposed_cpu"  # not implemented — tracked by issue #339


# --- Cache lookup -------------------------------------------------------------
@dataclass(frozen=True)
class CacheInfo:
    """Best-effort description of a model's on-disk footprint."""

    resolver: str
    path: Optional[str]
    exists: bool
    bytes_on_disk: int
    file_count: int
    last_modified: Optional[float]  # epoch seconds
    note: Optional[str] = None

    def to_dict(self, include_path: bool) -> dict:
        payload = {
            "cached": self.exists,
            "bytes_on_disk": self.bytes_on_disk,
            "file_count": self.file_count,
            "last_modified": _iso(self.last_modified),
            "resolver": self.resolver,
        }
        if self.note:
            payload["note"] = self.note
        if include_path:
            payload["path"] = self.path
        return payload


_EMPTY_CACHE = CacheInfo(
    resolver="none",
    path=None,
    exists=False,
    bytes_on_disk=0,
    file_count=0,
    last_modified=None,
)


def _dir_size(path: Path) -> tuple[int, int, Optional[float]]:
    """Sum file sizes/mtimes under ``path``. Never raises."""
    total = 0
    count = 0
    latest: Optional[float] = None
    try:
        for root, _dirs, files in os.walk(path):
            for fname in files:
                fp = Path(root) / fname
                try:
                    st = fp.stat()
                except OSError:
                    continue
                total += st.st_size
                count += 1
                if latest is None or st.st_mtime > latest:
                    latest = st.st_mtime
    except OSError:
        pass
    return total, count, latest


def _current_hf_hub_cache_dir() -> str:
    """Resolve the HF Hub cache directory from *current* env vars.

    ``huggingface_hub`` bakes ``HF_HUB_CACHE`` into a module-level constant
    at import time, so it can miss ``HF_HOME``/``HUGGINGFACE_HUB_CACHE``
    changes made afterwards (e.g. by our own settings loading, or by tests).
    Recomputing it here keeps this report accurate for the environment as
    it is right now.
    """
    explicit = os.getenv("HUGGINGFACE_HUB_CACHE") or os.getenv("HF_HUB_CACHE")
    if explicit:
        return explicit
    hf_home = os.getenv("HF_HOME") or os.path.expanduser("~/.cache/huggingface")
    return os.path.join(hf_home, "hub")


def _hf_hub_cache_matches(*needles: str) -> Optional[CacheInfo]:
    """Best-effort lookup of a Hugging Face Hub cached repo matching any needle.

    Reads the local Hub cache *index* only (``scan_cache_dir``); this never
    triggers a download or network call.
    """
    try:
        from huggingface_hub import scan_cache_dir
    except Exception:
        return None

    try:
        cache_info = scan_cache_dir(cache_dir=_current_hf_hub_cache_dir())
    except Exception:
        return None

    lowered = [n.lower() for n in needles if n]
    if not lowered:
        return None

    matches = [
        repo
        for repo in cache_info.repos
        if any(needle in repo.repo_id.lower() for needle in lowered)
    ]
    if not matches:
        return None

    total_bytes = sum(int(repo.size_on_disk) for repo in matches)
    total_files = sum(int(repo.nb_files) for repo in matches)
    last_modified = max((float(repo.last_modified) for repo in matches), default=None)
    paths = ", ".join(str(repo.repo_path) for repo in matches)
    return CacheInfo(
        resolver="hf_hub_cache",
        path=paths,
        exists=True,
        bytes_on_disk=total_bytes,
        file_count=total_files,
        last_modified=last_modified,
        note=None
        if len(matches) == 1
        else f"{len(matches)} matching cached repos summed",
    )


def _open_clip_legacy_cache(*needles: str) -> Optional[CacheInfo]:
    """Fallback for open_clip checkpoints stored outside the HF Hub cache."""
    cache_dir = os.getenv("OPEN_CLIP_CACHE_DIR") or os.path.expanduser("~/.cache/clip")
    root = Path(cache_dir)
    if not root.exists():
        return None

    lowered = [n.lower() for n in needles if n]
    try:
        matched_files = [
            p
            for p in root.rglob("*")
            if p.is_file() and any(n in p.name.lower() for n in lowered)
        ]
    except OSError:
        return None
    if not matched_files:
        return None

    total = 0
    latest: Optional[float] = None
    for p in matched_files:
        try:
            st = p.stat()
        except OSError:
            continue
        total += st.st_size
        if latest is None or st.st_mtime > latest:
            latest = st.st_mtime

    return CacheInfo(
        resolver="open_clip_cache_dir",
        path=str(root),
        exists=True,
        bytes_on_disk=total,
        file_count=len(matched_files),
        last_modified=latest,
    )


def resolve_siglip_cache() -> CacheInfo:
    needles = (settings.CLIP_MODEL, settings.CLIP_PRETRAINED, "siglip")
    return (
        _hf_hub_cache_matches(*needles)
        or _open_clip_legacy_cache(*needles)
        or CacheInfo(
            resolver="none",
            path=None,
            exists=False,
            bytes_on_disk=0,
            file_count=0,
            last_modified=None,
            note="Checked the Hugging Face Hub cache and $OPEN_CLIP_CACHE_DIR "
            "(default ~/.cache/clip); neither contained a matching checkpoint.",
        )
    )


def resolve_florence_cache() -> CacheInfo:
    repo_id = settings.BLIP_MODEL  # e.g. "microsoft/Florence-2-base"
    short_name = repo_id.split("/")[-1] if repo_id else ""
    return _hf_hub_cache_matches(repo_id, short_name) or CacheInfo(
        resolver="none",
        path=None,
        exists=False,
        bytes_on_disk=0,
        file_count=0,
        last_modified=None,
        note="Not found in the Hugging Face Hub cache.",
    )


def resolve_yolo_cache() -> CacheInfo:
    """Best-effort — Ultralytics does not guarantee a single cache location.

    Checks the process working directory (the default auto-download target),
    the Ultralytics-configured ``weights_dir`` when importable, and the
    conventional ``~/.cache/ultralytics`` fallback.
    """
    weight_name = settings.YOLO_MODEL
    candidates: list[Path] = [Path.cwd() / weight_name]

    try:
        from ultralytics.utils import SETTINGS as _ultra_settings  # type: ignore

        weights_dir = _ultra_settings.get("weights_dir")
        if weights_dir:
            candidates.append(Path(weights_dir) / weight_name)
    except Exception:
        pass

    candidates.append(Path.home() / ".cache" / "ultralytics" / weight_name)

    for candidate in candidates:
        try:
            if candidate.is_file():
                st = candidate.stat()
                return CacheInfo(
                    resolver="ultralytics_weights_file",
                    path=str(candidate),
                    exists=True,
                    bytes_on_disk=st.st_size,
                    file_count=1,
                    last_modified=st.st_mtime,
                    note="Ultralytics does not expose one guaranteed cache "
                    "path; only the common download locations were checked.",
                )
        except OSError:
            continue

    return CacheInfo(
        resolver="ultralytics_weights_file",
        path=None,
        exists=False,
        bytes_on_disk=0,
        file_count=0,
        last_modified=None,
        note="Not found in the working directory, the configured "
        "weights_dir, or ~/.cache/ultralytics.",
    )


def resolve_insightface_cache() -> CacheInfo:
    home = Path(os.getenv("INSIGHTFACE_HOME", os.path.expanduser("~/.insightface")))
    for sub in ("models/antelopev2", "models/antelopev2/antelopev2"):
        candidate = home / sub
        if candidate.is_dir():
            total, count, latest = _dir_size(candidate)
            if count:
                return CacheInfo(
                    resolver="insightface_home",
                    path=str(candidate),
                    exists=True,
                    bytes_on_disk=total,
                    file_count=count,
                    last_modified=latest,
                )
    return CacheInfo(
        resolver="insightface_home",
        path=str(home / "models/antelopev2"),
        exists=False,
        bytes_on_disk=0,
        file_count=0,
        last_modified=None,
        note="Checked $INSIGHTFACE_HOME (default ~/.insightface).",
    )


def resolve_paddleocr_cache() -> CacheInfo:
    """PaddleOCR 3.x resolves weights through PaddleX; older installs use
    ``~/.paddleocr``. Both are checked."""
    candidates = [
        os.getenv("PADDLE_PDX_CACHE_HOME"),
        os.path.expanduser("~/.paddlex/official_models"),
        os.path.expanduser("~/.paddleocr"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_dir():
            total, count, latest = _dir_size(path)
            if count:
                return CacheInfo(
                    resolver="paddlex_cache_home",
                    path=str(path),
                    exists=True,
                    bytes_on_disk=total,
                    file_count=count,
                    last_modified=latest,
                )
    return CacheInfo(
        resolver="paddlex_cache_home",
        path=None,
        exists=False,
        bytes_on_disk=0,
        file_count=0,
        last_modified=None,
        note="Checked $PADDLE_PDX_CACHE_HOME, ~/.paddlex/official_models, "
        "and ~/.paddleocr.",
    )


# --- Model registry -----------------------------------------------------------
def _insightface_device() -> str:
    plan = resolve_execution(settings.ACCEL_MODE, detect_capabilities())
    return plan.providers[0] if plan.providers else "cpu"


@dataclass(frozen=True)
class ModelSpec:
    key: str  # ModelManager registration key (matches use_model()/get_model() names)
    label: str
    kind: str
    packs: tuple[str, ...]
    identifier: Callable[[], str]
    cache_resolver: Callable[[], CacheInfo]
    device_resolver: Callable[[], str]


MODEL_SPECS: tuple[ModelSpec, ...] = (
    ModelSpec(
        key="siglip",
        label="SigLIP image/text embedding",
        kind="open_clip",
        packs=(PACK_LIGHT, PACK_FULL),
        identifier=lambda: f"{settings.CLIP_MODEL}/{settings.CLIP_PRETRAINED}",
        cache_resolver=resolve_siglip_cache,
        device_resolver=current_torch_device,
    ),
    ModelSpec(
        key="florence-2",
        label="Florence-2 captioning",
        kind="transformers",
        packs=(PACK_FULL,),
        identifier=lambda: settings.BLIP_MODEL,
        cache_resolver=resolve_florence_cache,
        device_resolver=current_torch_device,
    ),
    ModelSpec(
        key="yolo",
        label="YOLO object detection",
        kind="ultralytics",
        packs=(PACK_FULL,),
        identifier=lambda: settings.YOLO_MODEL,
        cache_resolver=resolve_yolo_cache,
        device_resolver=current_torch_device,
    ),
    ModelSpec(
        key="insightface",
        label="InsightFace face detection/recognition",
        kind="insightface",
        packs=(PACK_FULL,),
        identifier=lambda: "antelopev2",
        cache_resolver=resolve_insightface_cache,
        device_resolver=_insightface_device,
    ),
    ModelSpec(
        key="paddleocr",
        label="PaddleOCR text extraction",
        kind="paddleocr",
        packs=(PACK_FULL,),
        identifier=lambda: "PP-OCR (en)",
        cache_resolver=resolve_paddleocr_cache,
        device_resolver=lambda: "cpu",
    ),
)

# Proposed CPU-optimized ONNX pack (issue #339). Not implemented yet, so there
# is nothing on disk to measure — listed so pack totals/documentation have a
# stable place to grow into once it ships.
PROPOSED_CPU_MODELS: tuple[dict, ...] = (
    {"label": "CLIP ViT-B-32 (ONNX, openai)", "replaces": "siglip"},
    {"label": "InsightFace buffalo_s (ONNX)", "replaces": "insightface"},
    {"label": "PP-OCRv5 mobile (ONNX)", "replaces": "paddleocr"},
)


# --- Report assembly -----------------------------------------------------------
def _iso(epoch: Optional[float]) -> Optional[str]:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _aggregate_manager_status() -> set[str]:
    """Model keys reported loaded by this process or any process that has
    published status to Redis. Best-effort; degrades to local-only."""
    manager = get_model_manager()
    local_status = manager.get_status()
    loaded: set[str] = set(local_status.get("loaded_models", []))

    try:
        import json

        from find_api.core.queue import get_redis_connection

        redis_conn = get_redis_connection()
        for key in redis_conn.scan_iter("find:model_status:*"):
            try:
                raw = redis_conn.get(key)
                if not raw:
                    continue
                status = json.loads(raw)
                loaded.update(status.get("loaded_models", []))
            except Exception:
                continue
    except Exception:
        pass

    return loaded


def build_report(include_paths: bool = False) -> dict:
    """Build the full model footprint report.

    ``include_paths=False`` (the default, used by the admin API) omits
    filesystem paths from the cache entries — only sizes, counts, and
    timestamps are returned. ``include_paths=True`` is for the local CLI
    script only; never wire it up to a network-reachable endpoint.
    """
    manager = get_model_manager()
    loaded_keys = _aggregate_manager_status()

    models: list[dict] = []
    pack_totals: dict[str, dict] = {
        PACK_LIGHT: {"bytes_on_disk": 0, "cached_count": 0, "total_count": 0},
        PACK_FULL: {"bytes_on_disk": 0, "cached_count": 0, "total_count": 0},
    }

    for spec in MODEL_SPECS:
        try:
            identifier = spec.identifier()
        except Exception as exc:  # noqa: BLE001
            identifier = f"<unresolved: {exc}>"

        try:
            cache_info = spec.cache_resolver()
        except Exception:  # noqa: BLE001
            cache_info = _EMPTY_CACHE

        try:
            device = spec.device_resolver()
        except Exception:  # noqa: BLE001
            device = "unknown"

        last_used_epoch = manager.last_used.get(spec.key)

        notes: list[str] = []
        if last_used_epoch is None:
            notes.append(
                "last_used reflects this process only and no in-process use "
                "has been recorded yet"
            )

        models.append(
            {
                "key": spec.key,
                "label": spec.label,
                "kind": spec.kind,
                "packs": list(spec.packs),
                "identifier": identifier,
                "loaded": spec.key in loaded_keys,
                "device": device,
                "last_used": _iso(last_used_epoch),
                "cache": cache_info.to_dict(include_paths),
                "notes": notes,
            }
        )

        for pack in spec.packs:
            totals = pack_totals.get(pack)
            if totals is None:
                continue
            totals["total_count"] += 1
            if cache_info.exists:
                totals["cached_count"] += 1
                totals["bytes_on_disk"] += cache_info.bytes_on_disk

    return {
        "generated_at": _iso(time.time()),
        "models": models,
        "packs": {
            PACK_LIGHT: pack_totals[PACK_LIGHT],
            PACK_FULL: pack_totals[PACK_FULL],
            PACK_PROPOSED_CPU: {
                "status": "not_implemented",
                "note": (
                    "CPU-optimized ONNX pack tracked by issue #339. "
                    "Nothing is downloaded yet, so there is no footprint to "
                    "measure."
                ),
                "models": [m["label"] for m in PROPOSED_CPU_MODELS],
            },
        },
    }
