"""Privacy-safe local diagnostics helpers.

This package collects and redacts support bundles for offline debugging.
Nothing here uploads data or contacts external services.
"""

from __future__ import annotations

from typing import Any

__all__ = ["collect_diagnostics_bundle", "redact_payload"]


def __getattr__(name: str) -> Any:
    if name == "collect_diagnostics_bundle":
        from find_api.diagnostics.bundle import collect_diagnostics_bundle

        return collect_diagnostics_bundle
    if name == "redact_payload":
        from find_api.diagnostics.redact import redact_payload

        return redact_payload
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
