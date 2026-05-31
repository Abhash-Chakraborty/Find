#!/usr/bin/env python3
"""
Quick smoke checks for hybrid embedding signal selection.

This script exercises the full-mode branch of
`generate_hybrid_embedding()` using a mocked CLIP embedder so it can run
without downloading real models or requiring a GPU.

Usage (from the backend directory):
    uv run python scripts/smoke_hybrid_embedding.py
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

DIM = 8


def _unit(vector: np.ndarray) -> np.ndarray:
    return vector / np.linalg.norm(vector)


def _vector(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    vector = rng.standard_normal(DIM).astype(np.float32)
    return _unit(vector)


def _build_embedder(
    image_vector: np.ndarray,
    text_map: dict[str, np.ndarray],
) -> MagicMock:
    embedder = MagicMock()
    embedder.embed_image.return_value = image_vector

    def _embed_text(text):
        if isinstance(text, str):
            return text_map[text]
        return np.stack([text_map[item] for item in text])

    embedder.embed_text.side_effect = _embed_text
    return embedder


def _run(
    image_vector: np.ndarray,
    *,
    caption: str | None,
    objects: list[object],
    text_map: dict[str, np.ndarray],
) -> tuple[np.ndarray, MagicMock]:
    from find_api.workers.processors import generate_hybrid_embedding

    fake_clip_module = MagicMock()
    embedder = _build_embedder(image_vector, text_map)
    fake_clip_module.get_clip_embedder.return_value = embedder

    image = Image.new("RGB", (16, 16), color=(25, 25, 25))

    with (
        patch("find_api.workers.processors.settings") as mock_settings,
        patch.dict(sys.modules, {"find_api.ml.clip_embedder": fake_clip_module}),
    ):
        mock_settings.ML_MODE = "full"
        result = generate_hybrid_embedding(
            image,
            {"caption": caption, "objects": objects},
        )

    return np.array(result, dtype=np.float32), embedder


def _assert(name: str, condition: bool, detail: str) -> None:
    if not condition:
        raise AssertionError(f"{name} failed: {detail}")
    print(f"[ok] {name}")


def main() -> None:
    image_vector = _vector(1)
    caption_vector = _vector(2)
    objects_vector = _vector(3)

    caption = "a sunny beach"
    objects_text = "detected objects: cat, dog"

    # Image-only path should never embed text.
    result, embedder = _run(
        image_vector,
        caption="",
        objects=[],
        text_map={},
    )
    _assert(
        "image-only result",
        np.allclose(result, image_vector, atol=1e-5),
        "expected image vector to pass through unchanged",
    )
    _assert(
        "image-only skips text embedding",
        embedder.embed_text.call_count == 0,
        "embed_text should not be called when caption and objects are absent",
    )

    # Caption + objects path should use one batched text call and re-normalize.
    result, embedder = _run(
        image_vector,
        caption=caption,
        objects=[{"class": "dog"}, {"class": "cat"}, {"class": "dog"}],
        text_map={caption: caption_vector, objects_text: objects_vector},
    )
    expected = _unit(image_vector + caption_vector + objects_vector)
    _assert(
        "caption+objects average",
        np.allclose(result, expected, atol=1e-5),
        "expected equal-weight normalized combination",
    )
    _assert(
        "caption+objects batched text call",
        embedder.embed_text.call_args[0][0] == [caption, objects_text],
        "expected batched embed_text call with caption and deduplicated objects",
    )

    # Whitespace-only object labels must not leak through as a ghost signal.
    result, embedder = _run(
        image_vector,
        caption="",
        objects=[{"class": "   "}, {"class": "\n\t"}],
        text_map={"detected objects: ": objects_vector},
    )
    _assert(
        "whitespace-only objects ignored",
        np.allclose(result, image_vector, atol=1e-5),
        "whitespace-only labels should not create an object-text embedding",
    )
    _assert(
        "whitespace-only objects skip text embedding",
        embedder.embed_text.call_count == 0,
        "embed_text should not be called for stripped-empty labels",
    )

    print("\nAll hybrid embedding smoke checks passed.")


if __name__ == "__main__":
    main()
