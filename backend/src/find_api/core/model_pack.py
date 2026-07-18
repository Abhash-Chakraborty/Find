"""
Thin interfaces for versioned model pack metadata and caching.

This module defines the CONTRACT for installer-mode model download/cache
behavior. It intentionally does not implement real downloading yet — see
docs/plans/partial/model-cache-design.md for the full design. Existing ML
loaders in find_api/ml/ are NOT modified by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol


class PackCategory(str, Enum):
    """Which ML capability a pack provides."""

    CAPTION = "caption"
    OCR = "ocr"
    OBJECTS = "objects"
    EMBEDDINGS = "embeddings"
    FACES = "faces"


@dataclass(frozen=True)
class ModelPack:
    """Versioned metadata for a single downloadable model pack.

    Maps onto the existing loader/config surface:
      - EMBEDDINGS -> settings.CLIP_MODEL / settings.CLIP_PRETRAINED (clip_embedder.py)
      - CAPTION    -> settings.BLIP_MODEL (captioner.py)
      - OBJECTS    -> settings.YOLO_MODEL (object_detector.py)
      - OCR        -> PaddleOCR "en" pipeline (ocr.py)
      - FACES      -> InsightFace "antelopev2" (face_detector.py)
    """

    pack_id: str
    category: PackCategory
    version: str
    source_url: str
    license: str
    size_bytes: int
    checksum_sha256: str
    compatible_app_versions: str  # e.g. ">=1.0.0,<2.0.0"
    config_key: str  # matches the loader's config_key format, e.g. "model=..."
    description: str = ""


class PackStatus(str, Enum):
    NOT_INSTALLED = "not_installed"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    INSTALLED = "installed"
    CORRUPTED = "corrupted"
    FAILED = "failed"


@dataclass
class PackProgress:
    """Progress snapshot for a single pack download."""

    pack_id: str
    status: PackStatus
    bytes_downloaded: int = 0
    bytes_total: int = 0
    error: str | None = None


class PackCache(Protocol):
    """Contract for a model-pack cache implementation.

    This is intentionally a thin interface: no real download/verify logic
    ships in this PR. A concrete implementation (e.g. FilesystemPackCache)
    will be added in a follow-up once this contract is agreed.
    """

    def is_installed(self, pack: ModelPack) -> bool:
        """Return True if the pack is present and passes checksum verification."""
        ...

    def status(self, pack: ModelPack) -> PackProgress:
        """Return current status/progress for a pack."""
        ...

    def install(
        self,
        pack: ModelPack,
        on_progress: Callable[[PackProgress], None] | None = None,
    ) -> None:
        """Download, verify, and atomically install a pack. Must support
        resume/retry and must never leave a partially-installed pack marked
        as installed."""
        ...

    def verify(self, pack: ModelPack) -> bool:
        """Re-check an already-installed pack's checksum (corruption recovery)."""
        ...

    def remove(self, pack: ModelPack) -> None:
        """Delete a cached pack from disk."""
        ...


class NotImplementedPackCache:
    """Placeholder PackCache used until a real implementation lands.

    Every method raises NotImplementedError on purpose — this class exists
    only so other code can type-check against PackCache today without a
    working cache backend yet.
    """

    def is_installed(self, pack: ModelPack) -> bool:
        raise NotImplementedError("PackCache implementation not yet added")

    def status(self, pack: ModelPack) -> PackProgress:
        raise NotImplementedError("PackCache implementation not yet added")

    def install(self, pack: ModelPack, on_progress=None) -> None:
        raise NotImplementedError("PackCache implementation not yet added")

    def verify(self, pack: ModelPack) -> bool:
        raise NotImplementedError("PackCache implementation not yet added")

    def remove(self, pack: ModelPack) -> None:
        raise NotImplementedError("PackCache implementation not yet added")
