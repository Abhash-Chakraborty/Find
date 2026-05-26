"""
tests/test_hybrid_embedding.py

Unit tests for generate_hybrid_embedding() in workers/processors.py.
No real ML model or GPU is required — all CLIP calls are mocked.

Run with:
    cd backend
    python -m pytest tests/test_hybrid_embedding.py -v
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image as PILImage

DIM = 8  # small vector size — enough to test the math


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unit(v: np.ndarray) -> np.ndarray:
    """Return L2-normalised copy of v."""
    return v / np.linalg.norm(v)


def _make_image_vec(*seed: int) -> np.ndarray:
    """Reproducible non-zero unit vector from a seed."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(DIM).astype(np.float32)
    return _unit(v)


def _make_text_vec(*seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(DIM).astype(np.float32)
    return _unit(v)


def _build_mock_embedder(
    image_vec: np.ndarray,
    text_map: dict[str, np.ndarray],
) -> MagicMock:
    """
    Build a MagicMock CLIPEmbedder.
    embed_text(str)  → 1-D vector from text_map
    embed_text(list) → 2-D matrix (one row per string)
    """
    embedder = MagicMock()
    embedder.embed_image.return_value = image_vec

    def _embed_text(text):
        if isinstance(text, str):
            return text_map[text]
        rows = np.stack([text_map[t] for t in text])
        return rows

    embedder.embed_text.side_effect = _embed_text
    return embedder


def _run(
    image_vec: np.ndarray,
    caption: str | None,
    objects: list,
    text_map: dict,
) -> tuple[np.ndarray, MagicMock]:
    """
    Call generate_hybrid_embedding with a fully mocked CLIP embedder.
    Returns (result_vector_as_ndarray, mock_embedder).

    We inject a fake 'find_api.ml.clip_embedder' module directly into
    sys.modules so that the lazy import inside generate_hybrid_embedding()
    never attempts to load torch or open_clip (which are not installed in
    the dev/test venv).  patch.dict() removes the fake module once the
    with-block exits, leaving sys.modules clean for other tests.
    """
    from find_api.workers.processors import generate_hybrid_embedding

    fake_image = MagicMock(spec=PILImage.Image)
    metadata = {"caption": caption, "objects": objects}
    embedder = _build_mock_embedder(image_vec, text_map)

    # Build a fake module whose get_clip_embedder() returns our mock embedder.
    fake_clip_module = MagicMock()
    fake_clip_module.get_clip_embedder.return_value = embedder

    with (
        patch("find_api.workers.processors.settings") as mock_settings,
        patch.dict(sys.modules, {"find_api.ml.clip_embedder": fake_clip_module}),
    ):
        mock_settings.ML_MODE = "full"
        result = generate_hybrid_embedding(fake_image, metadata)

    return np.array(result, dtype=np.float32), embedder


# ---------------------------------------------------------------------------
# Pre-computed vectors used across tests
# ---------------------------------------------------------------------------
IMG_VEC = _make_image_vec(1)
CAP_VEC = _make_text_vec(2)
OBJ_VEC = _make_text_vec(3)
EMPTY_VEC = _make_text_vec(99)  # what "" would produce — should NEVER appear


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHybridEmbeddingSignalSelection:
    """Verify which signals are used based on available metadata."""

    def test_no_text_signals_uses_image_only(self):
        """No caption, no objects → output equals image embedding; embed_text never called."""
        result, embedder = _run(
            image_vec=IMG_VEC,
            caption="",
            objects=[],
            text_map={"": EMPTY_VEC},  # should NOT be called
        )

        # embed_text must never have been called
        embedder.embed_text.assert_not_called()

        # result must equal the (already unit-norm) image vector
        np.testing.assert_allclose(result, IMG_VEC, atol=1e-5)

    def test_caption_only(self):
        """Caption present, no objects → average of image + caption."""
        text_map = {"a sunny beach": CAP_VEC, "": EMPTY_VEC}
        result, embedder = _run(
            image_vec=IMG_VEC,
            caption="a sunny beach",
            objects=[],
            text_map=text_map,
        )

        expected = _unit(IMG_VEC + CAP_VEC)
        np.testing.assert_allclose(result, expected, atol=1e-5)

        # embed_text called once with the caption string, never with ""
        assert embedder.embed_text.call_count == 1
        embedder.embed_text.assert_called_once_with("a sunny beach")

    def test_objects_only(self):
        """Objects detected, caption absent → average of image + objects."""
        objects_text = "detected objects: cat, dog"
        text_map = {objects_text: OBJ_VEC, "": EMPTY_VEC}
        result, embedder = _run(
            image_vec=IMG_VEC,
            caption="",
            objects=[{"class": "cat"}, {"class": "dog"}],
            text_map=text_map,
        )

        expected = _unit(IMG_VEC + OBJ_VEC)
        np.testing.assert_allclose(result, expected, atol=1e-5)

        assert embedder.embed_text.call_count == 1
        embedder.embed_text.assert_called_once_with(objects_text)

    def test_caption_and_objects(self):
        """Both present → all three averaged equally (1/3 each)."""
        objects_text = "detected objects: cat"
        text_map = {
            "a cat on a mat": CAP_VEC,
            objects_text: OBJ_VEC,
            "": EMPTY_VEC,
        }
        result, embedder = _run(
            image_vec=IMG_VEC,
            caption="a cat on a mat",
            objects=[{"class": "cat"}],
            text_map=text_map,
        )

        expected = _unit(IMG_VEC + CAP_VEC + OBJ_VEC)
        np.testing.assert_allclose(result, expected, atol=1e-5)

        # Called once with the list of two strings
        assert embedder.embed_text.call_count == 1
        embedder.embed_text.assert_called_once_with(["a cat on a mat", objects_text])


class TestHybridEmbeddingEdgeCases:
    """Edge cases: whitespace, malformed objects, None values."""

    def test_whitespace_caption_treated_as_absent(self):
        """Caption of only spaces → treated the same as no caption."""
        result, embedder = _run(
            image_vec=IMG_VEC,
            caption="   ",
            objects=[],
            text_map={"   ": EMPTY_VEC, "": EMPTY_VEC},
        )
        embedder.embed_text.assert_not_called()
        np.testing.assert_allclose(result, IMG_VEC, atol=1e-5)

    def test_none_caption_treated_as_absent(self):
        """None caption → treated as no caption."""
        result, embedder = _run(
            image_vec=IMG_VEC,
            caption=None,  # metadata.get("caption") returns None
            objects=[],
            text_map={},
        )
        embedder.embed_text.assert_not_called()
        np.testing.assert_allclose(result, IMG_VEC, atol=1e-5)

    def test_malformed_objects_without_class_key_ignored(self):
        """Objects missing 'class' key must be silently ignored, not raise KeyError."""
        result, embedder = _run(
            image_vec=IMG_VEC,
            caption="",
            objects=[{"label": "cat"}, {"name": "dog"}, {}],  # all missing "class"
            text_map={},
        )
        embedder.embed_text.assert_not_called()
        np.testing.assert_allclose(result, IMG_VEC, atol=1e-5)

    def test_whitespace_only_object_labels_ignored(self):
        """Object labels that strip to empty text must not create an objects embedding."""
        result, embedder = _run(
            image_vec=IMG_VEC,
            caption="",
            objects=[{"class": "   "}, {"class": "\n\t"}],
            text_map={"detected objects: ": EMPTY_VEC},
        )
        embedder.embed_text.assert_not_called()
        np.testing.assert_allclose(result, IMG_VEC, atol=1e-5)

    def test_duplicate_object_classes_deduplicated(self):
        """Same class appearing multiple times → included once in objects_text."""
        objects_text = "detected objects: cat"
        text_map = {objects_text: OBJ_VEC}
        result, embedder = _run(
            image_vec=IMG_VEC,
            caption="",
            objects=[{"class": "cat"}, {"class": "cat"}, {"class": "cat"}],
            text_map=text_map,
        )
        # objects_text must contain "cat" once
        called_with = embedder.embed_text.call_args[0][0]
        assert called_with.count("cat") == 1

    def test_output_is_unit_norm(self):
        """Result vector must always have L2 norm ≈ 1.0."""
        text_map = {"caption text": CAP_VEC, "detected objects: car": OBJ_VEC}
        result, _ = _run(
            image_vec=IMG_VEC,
            caption="caption text",
            objects=[{"class": "car"}],
            text_map=text_map,
        )
        norm = float(np.linalg.norm(result))
        assert abs(norm - 1.0) < 1e-5, f"Expected unit norm, got {norm}"


class TestBiasRemoval:
    """
    Regression tests: demonstrate that the empty-string bias is gone.

    Before the fix: two visually unrelated images both with no objects
    would have high cosine similarity because they both included the same
    empty-string embedding at 1/3 weight.

    After the fix: their similarity should be determined only by their
    image and caption vectors, with no shared phantom component.
    """

    def test_two_unrelated_images_no_objects_low_similarity(self):
        """
        Two images with orthogonal image vectors and no objects must
        have cosine similarity close to 0, not elevated by a shared bias.
        """
        # Two image vectors that are exactly orthogonal → true similarity = 0
        img_a = np.zeros(DIM, dtype=np.float32)
        img_a[0] = 1.0
        img_b = np.zeros(DIM, dtype=np.float32)
        img_b[1] = 1.0

        result_a, _ = _run(img_a, caption="", objects=[], text_map={})
        result_b, _ = _run(img_b, caption="", objects=[], text_map={})

        cosine = float(np.dot(result_a, result_b))
        # Without the fix, cosine ≈ 0.5 (shared empty-string vector pulled both)
        # With the fix, cosine = 0.0 (only image vectors remain)
        assert cosine < 0.1, (
            f"Expected near-zero cosine for unrelated images, got {cosine:.4f}. "
            "This suggests the empty-string bias is still present."
        )

    def test_empty_string_never_embedded_in_any_scenario(self):
        """
        Exhaustively check that embed_text is never called with ""
        across all four signal combinations.
        """
        scenarios = [
            ("", []),
            ("a sunset", []),
            ("", [{"class": "car"}]),
            ("a road", [{"class": "car"}]),
        ]

        all_text_maps = {
            "a sunset": _make_text_vec(10),
            "a road": _make_text_vec(11),
            "detected objects: car": _make_text_vec(12),
            "": EMPTY_VEC,  # present but must NOT be called
        }

        for caption, objects in scenarios:
            _, embedder = _run(IMG_VEC, caption, objects, all_text_maps)

            # Check every individual call to embed_text
            for single_call in embedder.embed_text.call_args_list:
                args = single_call[0][0]  # first positional argument
                if isinstance(args, str):
                    assert args != "", (
                        f"embed_text('') was called for scenario "
                        f"caption={caption!r}, objects={objects}"
                    )
                else:
                    assert (
                        "" not in args
                    ), f"Empty string found in embed_text list call: {args}"
