"""Admin-only local diagnostics bundle export.

GET /api/admin/diagnostics/bundle returns a privacy-redacted JSON document
generated on this host. Nothing is uploaded externally — the caller must
explicitly request and download the payload.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from find_api.core.dependencies import get_admin_user
from find_api.diagnostics.bundle import (
    collect_diagnostics_bundle,
    ensure_error_log_buffer,
)
from find_api.diagnostics.redact import scrub_string
from find_api.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

_BUNDLE_HEADERS = {
    "Content-Disposition": 'attachment; filename="find-diagnostics-bundle.json"',
    "X-Find-Diagnostics": "local-only",
}

# Install the in-process error buffer when this router is imported so recent
# ERROR logs are available by the time an admin requests a bundle.
ensure_error_log_buffer()


@router.get("/admin/diagnostics/bundle")
def export_diagnostics_bundle(
    _admin: Optional[User] = Depends(get_admin_user),
):
    """Return a privacy-safe local diagnostics bundle as JSON.

    Admin-only in shared mode (open in local mode), matching other
    instance-wide admin endpoints. Requires an explicit HTTP request —
    no background telemetry or outbound upload is performed.
    """
    try:
        bundle = collect_diagnostics_bundle()
    except Exception as exc:  # noqa: BLE001 — never leak stack traces to clients
        logger.exception("Diagnostics bundle collection failed")
        # Scrub secrets first; sanitize_error path stripping can tear across
        # "password=..." assignments if applied before credential scrubbing.
        safe_message = scrub_string(str(exc))
        if len(safe_message) > 150:
            safe_message = safe_message[:150] + "..."
        return JSONResponse(
            status_code=500,
            content={"error": f"{exc.__class__.__name__}: {safe_message}"},
            headers=_BUNDLE_HEADERS,
        )

    return JSONResponse(
        content=bundle,
        headers=_BUNDLE_HEADERS,
    )
