#!/usr/bin/env python3
"""
backend/scripts/smoke_hybrid_embedding.py

Smoke test for the empty-object-text embedding fix.
Validates that the fixed generate_hybrid_embedding() behaves correctly
across all signal combinations, without needing any real ML models.

Usage (from repo root):
    cd D:\\gssoc\\find\\Find
    python -m pytest backend/tests/test_hybrid_embedding.py -v
    python backend/scripts/smoke_hybrid_embedding.py
"""
from __future__ import annotations

import os
import sys
import traceback

# Put the backend src on the path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_SRC = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "src"))
sys.path.insert(0, BACKEND_SRC)

# Use mock ML mode so no real models are downloaded
os.environ.setdefault("ML_MODE", "mock")

import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

_passed = 0
_failed = 0


def ok(msg: str) -> None:
    global _passed
    _passed += 1
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str, detail: str = "") -> None:
    global _failed
    _failed += 1
    print(f"  {RED}✗{RESET} {msg}")
    if detail:
        print(f"    {YELLOW}{detail}{RESET}")


def section(title: str) -> None:
    print(f"\n{BOLD}{title}{RESET}")


# ---------------------------------------------------------------------------
# Helper: create a reproducible fake PIL image
# ---------------------------------------------------------------------------
def _fake_image(r: int = 100, g: int = 149, b: int = 237) -> Image.Image:
    img = Image.new("RGB", (64, 64), color=(r, g, b))
    return img


# ---------------------------------------------------------------------------
# Smoke checks
# ---------------------------------------------------------------------------

def smoke_mock_mode_returns_list():
    """Mock mode path (no CLIP) still returns a valid float list."""
    section("1. Mock mode basic sanity")
    from find_api.workers.processors import generate_hybrid_embedding

    img = _fake_image()
    metadata = {"caption": "a test image", "objects": []}
    result = generate_hybrid_embedding(img, metadata)

    if not isinstance(result, list):
        fail("result is not a list", f"got {type(result)}")
        return
    ok(f"returns list of length {len(result)}")

    if not all(isinstance(x, float) for x in result):
        fail("result contains non-float values")
        return
    ok("all elements are float")

    norm = float(np.linalg.norm(result))
    if abs(norm - 1.0) < 1e-4:
        ok(f"output is unit-norm (norm={norm:.6f})")
    else:
        fail(f"output is NOT unit-norm (norm={norm:.6f})")


def smoke_deterministic_for_same_input():
    """Same image + metadata always produces same vector (determinism)."""
    section("2. Determinism")
    from find_api.workers.processors import generate_hybrid_embedding

    img = _fake_image(120, 80, 200)
    meta = {"caption": "a purple square", "objects": [{"class": "square"}]}

    r1 = generate_hybrid_embedding(img, meta)
    r2 = generate_hybrid_embedding(img, meta)

    if r1 == r2:
        ok("two calls with same input produce identical output")
    else:
        diff = float(np.linalg.norm(np.array(r1) - np.array(r2)))
        fail(f"non-deterministic output (diff={diff:.6e})")


def smoke_different_images_different_vectors():
    """Different images produce different embedding vectors."""
    section("3. Different images → different vectors")
    from find_api.workers.processors import generate_hybrid_embedding

    img_a = _fake_image(255, 0, 0)    # red
    img_b = _fake_image(0, 0, 255)    # blue
    meta = {"caption": "", "objects": []}

    r_a = np.array(generate_hybrid_embedding(img_a, meta))
    r_b = np.array(generate_hybrid_embedding(img_b, meta))

    cosine = float(np.dot(r_a, r_b))
    if not np.allclose(r_a, r_b):
        ok(f"different images → different vectors (cosine={cosine:.4f})")
    else:
        fail("different images produced identical vectors")


def smoke_no_objects_vs_with_objects_differ():
    """
    Same image: adding detected objects changes the embedding.
    This verifies that the objects branch actually fires.
    """
    section("4. Adding objects changes the embedding")
    from find_api.workers.processors import generate_hybrid_embedding

    img = _fake_image(80, 160, 80)
    meta_no_objects  = {"caption": "a forest",  "objects": []}
    meta_with_objects = {"caption": "a forest", "objects": [{"class": "tree"}, {"class": "bird"}]}

    r_no  = np.array(generate_hybrid_embedding(img, meta_no_objects))
    r_yes = np.array(generate_hybrid_embedding(img, meta_with_objects))

    if not np.allclose(r_no, r_yes):
        cosine = float(np.dot(r_no, r_yes))
        ok(f"adding objects changes vector (cosine with/without={cosine:.4f})")
    else:
        fail("objects metadata had no effect on the embedding")


def smoke_caption_changes_embedding():
    """Adding a caption must change the embedding."""
    section("5. Caption changes the embedding")
    from find_api.workers.processors import generate_hybrid_embedding

    img = _fake_image(200, 200, 50)
    meta_no_cap   = {"caption": "",                "objects": []}
    meta_with_cap = {"caption": "a golden field",  "objects": []}

    r_no  = np.array(generate_hybrid_embedding(img, meta_no_cap))
    r_yes = np.array(generate_hybrid_embedding(img, meta_with_cap))

    if not np.allclose(r_no, r_yes):
        ok("caption changes the embedding vector")
    else:
        fail("caption had no effect — check mock embedder's text path")


def smoke_unit_norm_all_scenarios():
    """All four signal combinations produce unit-norm output."""
    section("6. Unit-norm output in all signal combinations")
    from find_api.workers.processors import generate_hybrid_embedding

    img = _fake_image()
    scenarios = [
        ("no caption, no objects",  "",             []),
        ("caption only",            "a sunny day",  []),
        ("objects only",            "",             [{"class": "sun"}]),
        ("caption + objects",       "a sunny day",  [{"class": "sun"}]),
    ]

    for label, caption, objects in scenarios:
        meta = {"caption": caption, "objects": objects}
        result = generate_hybrid_embedding(img, meta)
        norm = float(np.linalg.norm(result))
        if abs(norm - 1.0) < 1e-4:
            ok(f"{label}: norm={norm:.6f}")
        else:
            fail(f"{label}: NOT unit-norm (norm={norm:.6f})")


def smoke_malformed_objects_no_crash():
    """Objects missing 'class' key must not crash the pipeline."""
    section("7. Malformed objects dict — no crash, no KeyError")
    from find_api.workers.processors import generate_hybrid_embedding

    img = _fake_image()
    meta = {
        "caption": "scene",
        "objects": [
            {"label": "cat"},   # wrong key
            {"name": "dog"},    # wrong key
            {},                 # empty dict
            "not a dict",       # not a dict at all
        ],
    }
    try:
        result = generate_hybrid_embedding(img, meta)
        ok(f"no crash; result length={len(result)}")
    except Exception as exc:
        fail(f"crashed with: {exc}", traceback.format_exc())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\n{BOLD}=== Hybrid Embedding Smoke Tests ==={RESET}")
    print(f"ML_MODE={os.environ.get('ML_MODE', 'not set')}")

    smoke_mock_mode_returns_list()
    smoke_deterministic_for_same_input()
    smoke_different_images_different_vectors()
    smoke_no_objects_vs_with_objects_differ()
    smoke_caption_changes_embedding()
    smoke_unit_norm_all_scenarios()
    smoke_malformed_objects_no_crash()

    total = _passed + _failed
    print(f"\n{BOLD}Results: {_passed}/{total} passed{RESET}")
    if _failed:
        print(f"{RED}{_failed} test(s) FAILED{RESET}")
        sys.exit(1)
    else:
        print(f"{GREEN}All checks passed!{RESET}")
        sys.exit(0)