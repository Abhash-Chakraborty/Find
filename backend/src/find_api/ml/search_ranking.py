"""Search ranking helpers for textual boosting and stable reranking."""

from __future__ import annotations

import re
from typing import Any

TEXT_QUERY_TERMS = {
    "text",
    "document",
    "page",
    "notes",
    "invoice",
    "calendar",
    "receipt",
    "screenshot",
    "words",
}


def tokenize(text_value: str) -> set[str]:
    """Tokenize text into lowercase alphanumeric terms."""
    return set(re.findall(r"[a-z0-9]+", (text_value or "").lower()))


def extract_object_labels(objects_payload: Any) -> list[str]:
    """Extract object labels from heterogeneous metadata payloads."""
    labels: list[str] = []
    if not isinstance(objects_payload, list):
        return labels

    for obj in objects_payload:
        if isinstance(obj, str):
            labels.append(obj)
            continue
        if isinstance(obj, dict):
            label = str(obj.get("class") or obj.get("label") or "").strip()
            if label:
                labels.append(label)

    return labels


def compute_textual_boost(
    query_tokens: set[str],
    caption: str,
    ocr_text: str,
    object_labels: list[str],
) -> float:
    """Compute metadata-driven textual boost for a vector similarity score."""
    if not query_tokens:
        return 0.0

    caption_tokens = tokenize(caption)
    ocr_tokens = tokenize(ocr_text)
    object_tokens = tokenize(" ".join(object_labels))

    caption_overlap = len(query_tokens & caption_tokens)
    ocr_overlap = len(query_tokens & ocr_tokens)
    object_overlap = len(query_tokens & object_tokens)

    # OCR overlap gets the strongest boost for document/text-heavy queries.
    boost = (caption_overlap * 0.015) + (ocr_overlap * 0.035) + (object_overlap * 0.01)

    if query_tokens & TEXT_QUERY_TERMS and ocr_tokens:
        boost += 0.05

    return min(boost, 0.25)


def bound_similarity(score: float) -> float:
    """Clamp exposed similarity scores to [0.0, 1.0]."""
    return max(0.0, min(score, 1.0))


def rerank_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort results by boosted similarity, fallback vector score, and newest ID."""
    results.sort(
        key=lambda item: (
            float(item["similarity"]),
            float(item.get("_vector_similarity", 0.0)),
            int(item["media_id"]),
        ),
        reverse=True,
    )

    for item in results:
        item.pop("_vector_similarity", None)

    return results
