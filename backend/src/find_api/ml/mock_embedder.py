"""Deterministic lightweight embeddings for contributor development."""

import hashlib
import re
import threading
from typing import Any

import numpy as np
from PIL import Image

from find_api.core.config import settings


class MockEmbedder:
    """Generate stable vectors without loading external ML models."""

    def _vector_from_bytes(self, payload: bytes) -> np.ndarray:
        chunks = []
        counter = 0
        target_bytes = settings.EMBEDDING_DIM * 4

        while sum(len(chunk) for chunk in chunks) < target_bytes:
            chunks.append(hashlib.sha256(payload + counter.to_bytes(4, "big")).digest())
            counter += 1

        raw = b"".join(chunks)[:target_bytes]
        vector = np.frombuffer(raw, dtype=np.uint32).astype(np.float32)
        vector = (vector / np.iinfo(np.uint32).max) - 0.5

        norm = np.linalg.norm(vector)
        if norm == 0:
            vector[0] = 1.0
            return vector

        return vector / norm

    def _vector_from_text(self, text: str) -> np.ndarray:
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        if not tokens:
            return self._vector_from_bytes(b"text:")

        vectors = [
            self._vector_from_bytes(f"token:{token}".encode("utf-8"))
            for token in tokens
        ]
        vector = np.mean(vectors, axis=0)
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        return vector.astype(np.float32)

    def embed_image(self, image: Image.Image) -> np.ndarray:
        if image.mode != "RGB":
            image = image.convert("RGB")

        thumbnail = image.resize((16, 16))
        payload = (
            b"image:"
            + image.width.to_bytes(4, "big")
            + image.height.to_bytes(4, "big")
            + thumbnail.tobytes()
        )
        return self._vector_from_bytes(payload)

    def embed_text(self, text: str | list[str]) -> np.ndarray:
        if isinstance(text, str):
            return self._vector_from_text(text)

        return np.asarray(
            [self._vector_from_text(item) for item in text],
            dtype=np.float32,
        )

    def embed_metadata(
        self, image: Image.Image, metadata: dict[str, Any]
    ) -> list[float]:
        caption = str(metadata.get("caption", ""))
        objects = metadata.get("objects", [])
        object_text = ",".join(
            sorted(
                {
                    str(item.get("class", ""))
                    for item in objects
                    if isinstance(item, dict)
                }
            )
        )
        image_vector = self.embed_image(image)
        text_vector = self.embed_text(f"{caption} {object_text}")
        hybrid_vector = (image_vector + text_vector) / 2.0
        norm = np.linalg.norm(hybrid_vector)
        if norm > 0:
            hybrid_vector = hybrid_vector / norm
        return hybrid_vector.tolist()


_mock_embedder: MockEmbedder | None = None
_mock_embedder_lock = threading.Lock()


def get_mock_embedder() -> MockEmbedder:
    """Get or create the global mock embedder."""
    global _mock_embedder
    if _mock_embedder is None:
        with _mock_embedder_lock:
            if _mock_embedder is None:
                _mock_embedder = MockEmbedder()
    return _mock_embedder
