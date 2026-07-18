"""
Remote ML client — sends ML work to a user-controlled Find ML server.

Only active when ML_MODE=remote. Local, full, and mock modes are untouched.
All requests use Authorization: Bearer <token>.
EXIF is stripped before transmission when REMOTE_ML_STRIP_EXIF=true.
"""

import io
import logging
from typing import Any, Dict, List

import httpx
from PIL import Image

from find_api.core.config import settings

logger = logging.getLogger(__name__)

# Features that transmit full image bytes to the remote server.
_IMAGE_FEATURES = {"embed", "caption", "detect", "ocr"}

# Timeout for remote ML requests (seconds).
_REQUEST_TIMEOUT = 120.0


class RemoteMLError(Exception):
    """Raised when the remote ML server returns an error or is unreachable."""


class RemoteMLAuthError(RemoteMLError):
    """Raised when the remote server rejects the bearer token (HTTP 401/403)."""


def _strip_exif(image: Image.Image) -> bytes:
    """Re-encode the image as JPEG without EXIF metadata."""
    rgb = image.convert("RGB")
    buf = io.BytesIO()
    rgb.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _image_to_bytes(image: Image.Image, *, strip_exif: bool) -> bytes:
    """Return image bytes ready for transmission."""
    if strip_exif:
        return _strip_exif(image)

    buf = io.BytesIO()
    fmt = image.format or "JPEG"
    image.save(buf, format=fmt, exif=image.getexif())
    return buf.getvalue()


def _auth_headers() -> Dict[str, str]:
    """Return the Authorization header used on every authenticated request."""
    return {"Authorization": f"Bearer {settings.REMOTE_ML_API_KEY}"}


def _base_url() -> str:
    """Return the remote server base URL with a trailing slash removed."""
    return (settings.REMOTE_ML_URL or "").rstrip("/")


def _feature_enabled(feature: str) -> bool:
    """Return True when *feature* is listed in REMOTE_ML_FEATURES."""
    enabled = {
        f.strip().lower()
        for f in settings.REMOTE_ML_FEATURES.split(",")
        if f.strip()
    }
    return feature.lower() in enabled


def _raise_for_auth(response: httpx.Response) -> None:
    """Convert 401/403 into RemoteMLAuthError."""
    if response.status_code in (401, 403):
        raise RemoteMLAuthError(
            f"Remote ML server rejected credentials (HTTP {response.status_code}). "
            "Check REMOTE_ML_API_KEY."
        )


# --- Public API ---

def check_health() -> Dict[str, Any]:
    url = f"{_base_url()}/api/ml/health"
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        raise RemoteMLError(f"Health check failed: HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise RemoteMLError(f"Health check connection error: {exc}") from exc


def remote_analyze(image: Image.Image) -> Dict[str, Any]:
    url = f"{_base_url()}/api/ml/analyze"
    image_bytes = _image_to_bytes(image, strip_exif=settings.REMOTE_ML_STRIP_EXIF)

    try:
        with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
            response = client.post(
                url,
                headers=_auth_headers(),
                files={"image": ("image.jpg", image_bytes, "image/jpeg")},
            )
        _raise_for_auth(response)
        response.raise_for_status()
        return response.json()
    except (RemoteMLAuthError, RemoteMLError):
        raise
    except httpx.HTTPStatusError as exc:
        raise RemoteMLError(f"remote_analyze failed: HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise RemoteMLError(f"remote_analyze connection error: {exc}") from exc


def remote_embed(image: Image.Image, metadata: Dict[str, Any]) -> List[float]:
    url = f"{_base_url()}/api/ml/embed"
    image_bytes = _image_to_bytes(image, strip_exif=settings.REMOTE_ML_STRIP_EXIF)

    import json
    try:
        with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
            response = client.post(
                url,
                headers=_auth_headers(),
                files={"image": ("image.jpg", image_bytes, "image/jpeg")},
                data={"metadata": json.dumps(metadata)},
            )
        _raise_for_auth(response)
        response.raise_for_status()
        payload = response.json()
        return payload["embedding"]
    except (RemoteMLAuthError, RemoteMLError):
        raise
    except httpx.HTTPStatusError as exc:
        raise RemoteMLError(f"remote_embed failed: HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise RemoteMLError(f"remote_embed connection error: {exc}") from exc


def remote_cluster(embeddings: List[List[float]]) -> Dict[str, Any]:
    url = f"{_base_url()}/api/ml/cluster"

    try:
        with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
            response = client.post(
                url,
                headers={**_auth_headers(), "Content-Type": "application/json"},
                json={"embeddings": embeddings},
            )
        _raise_for_auth(response)
        response.raise_for_status()
        return response.json()
    except (RemoteMLAuthError, RemoteMLError):
        raise
    except httpx.HTTPStatusError as exc:
        raise RemoteMLError(f"remote_cluster failed: HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise RemoteMLError(f"remote_cluster connection error: {exc}") from exc
