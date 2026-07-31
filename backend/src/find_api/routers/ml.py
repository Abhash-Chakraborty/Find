"""
/api/ml/ — Remote ML inference endpoints.

These endpoints turn any Find backend running in full ML mode into a
remote ML server that other Find instances (ML_MODE=remote) can offload
work to.
"""

import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image
import io

from find_api.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ml", tags=["remote-ml"])

_bearer_scheme = HTTPBearer(auto_error=False)
_ML_API_VERSION = "0.1.0"


def _require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """Validate the bearer token against REMOTE_ML_API_KEY."""

    # Prevent infinite loops: A remote client cannot act as a server.
    if settings.ML_MODE.lower() == "remote":
        logger.error("Rejecting ML request: This server is itself in remote mode.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This server is configured as a client (ML_MODE=remote) and cannot process ML requests.",
        )

    configured_key = (settings.REMOTE_ML_API_KEY or "").strip()

    if not configured_key:
        logger.warning(
            "ML request received but REMOTE_ML_API_KEY is not set. Rejecting."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Remote ML endpoints are not configured on this server.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Provide: Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    import hmac

    token_matches = hmac.compare_digest(
        credentials.credentials.encode(),
        configured_key.encode(),
    )
    if not token_matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _load_image(upload: UploadFile) -> Image.Image:
    """Read an uploaded file and return a PIL Image."""
    try:
        data = upload.file.read()
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as exc:
        logger.warning(f"Could not decode uploaded image: {exc}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not decode uploaded image.",
        ) from exc


@router.get("/health")
def health() -> Dict[str, Any]:
    """Unauthenticated liveness check."""
    return {
        "status": "ok",
        "ml_mode": settings.ML_MODE,
        "version": _ML_API_VERSION,
    }


@router.post("/analyze", dependencies=[Depends(_require_auth)])
def analyze(image: UploadFile = File(...)) -> Dict[str, Any]:
    """Run object detection, captioning, and OCR on the uploaded image."""
    pil_image = _load_image(image)

    try:
        from find_api.workers.processors import extract_image_metadata

        metadata = extract_image_metadata(pil_image)
    except Exception as exc:
        logger.exception("analyze endpoint: extract_image_metadata failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ML inference failed on the remote server.",
        ) from exc

    # Deep-sanitize the stage_status to prevent CodeQL information exposure warnings
    raw_status = metadata.get("stage_status", {})
    clean_status = {}
    for stage, data in raw_status.items():
        if isinstance(data, dict):
            err = data.get("error")
            clean_status[stage] = {
                "status": str(data.get("status", "pending")),
                "error": str(err) if err else None,
            }

    return {
        "caption": str(metadata.get("caption", "")),
        "objects": metadata.get("objects", []),
        "ocr_text": str(metadata.get("ocr_text", "")),
        "text_blocks": metadata.get("text_blocks", []),
        "stage_status": clean_status,
    }


@router.post("/embed", dependencies=[Depends(_require_auth)])
def embed(
    image: UploadFile = File(...),
    metadata: str = Form(default="{}"),
) -> Dict[str, Any]:
    """Generate a hybrid CLIP embedding from the image and optional metadata."""
    pil_image = _load_image(image)

    try:
        meta_dict: Dict[str, Any] = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="metadata field must be valid JSON.",
        )
    if not isinstance(meta_dict, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="metadata field must be a JSON object.",
        )
    try:
        from find_api.workers.processors import generate_hybrid_embedding

        embedding = generate_hybrid_embedding(pil_image, meta_dict)
    except Exception as exc:
        logger.exception("embed endpoint: generate_hybrid_embedding failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Embedding generation failed on the remote server.",
        ) from exc

    return {"embedding": embedding}


@router.post("/embed_text", dependencies=[Depends(_require_auth)])
def embed_text(body: Dict[str, Any]) -> Dict[str, Any]:
    """Embed a search query with the same CLIP model used for image vectors."""
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="text must be a non-empty string.",
        )

    try:
        from find_api.ml.clip_embedder import get_clip_embedder

        embedding = get_clip_embedder().embed_text(text)
    except Exception as exc:
        logger.exception("embed_text endpoint: embed_text failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Text embedding failed on the remote server.",
        ) from exc

    return {"embedding": list(embedding)}


@router.post("/cluster", dependencies=[Depends(_require_auth)])
def cluster(body: Dict[str, Any]) -> Dict[str, Any]:
    """Run HDBSCAN clustering on a list of embedding vectors."""
    embeddings: List[List[float]] = body.get("embeddings", [])

    if not embeddings:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="embeddings must be a non-empty list of float arrays.",
        )

    try:
        import numpy as np
        from sklearn.cluster import HDBSCAN

        X = np.array(embeddings, dtype=np.float32)
        clusterer = HDBSCAN(
            min_cluster_size=settings.MIN_CLUSTER_SIZE,
            min_samples=settings.MIN_SAMPLES,
        )
        labels = clusterer.fit_predict(X).tolist()

        n_clusters = len(set(lbl for lbl in labels if lbl >= 0))
        n_noise = labels.count(-1)

        return {
            "labels": labels,
            "info": {
                "n_clusters": n_clusters,
                "n_noise": n_noise,
                "n_points": len(labels),
            },
        }
    except Exception as exc:
        logger.exception("cluster endpoint: HDBSCAN failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Clustering failed on the remote server.",
        ) from exc
