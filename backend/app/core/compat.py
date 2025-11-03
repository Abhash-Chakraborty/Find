"""Compatibility shims for third-party libraries.

This module centralizes small monkey patches required to keep
upstream dependencies quiet until they ship fixes. Importing
``app.core`` runs :func:`apply_monkey_patches` once at startup.
"""
from __future__ import annotations

import importlib
import logging
import sys
import warnings

logger = logging.getLogger(__name__)


def _patch_timm_layers() -> None:
    """Alias ``timm.layers`` to the legacy ``timm.models.layers`` path.

    Recent ``timm`` releases emit a ``FutureWarning`` whenever a consumer
    imports ``timm.models.layers``; several of our transitive dependencies
    still do that. Creating an alias prevents the deprecated import hook
    from running, eliminating the noisy warning without changing their code.
    """

    if "timm.models.layers" in sys.modules:
        # The alias (or old module) is already loaded; nothing to do.
        return

    try:
        timm_layers = importlib.import_module("timm.layers")
    except ModuleNotFoundError:
        # ``timm`` is optional in some environments. Skip quietly if it is
        # not available; callers that truly need it will fail later as usual.
        logger.debug("timm not installed; skipping compatibility patch")
        return

    sys.modules["timm.models.layers"] = timm_layers

    # Guard against stray FutureWarning coming from Python's module loader if
    # something still triggers the deprecated path before our alias is ready.
    warnings.filterwarnings(
        "ignore",
        message=r".*timm\.models\.layers.*",
        category=FutureWarning,
        module="timm",
    )

    logger.debug("Registered timm.models.layers compatibility alias")


def _suppress_hf_resume_warning() -> None:
    """Silence FutureWarning about the deprecated resume_download flag.

    ``transformers`` still passes this argument when fetching weights, which
    causes a noisy warning during worker startup. The behaviour already matches
    the upcoming default (downloads resume automatically), so it is safe to
    ignore until the dependency drops the argument.
    """

    warnings.filterwarnings(
        "ignore",
        message=r".*resume_download.*deprecated.*",
        category=FutureWarning,
        module=r"huggingface_hub\.file_download",
    )


def apply_monkey_patches() -> None:
    """Apply all third-party compatibility patches once."""

    _patch_timm_layers()
    _suppress_hf_resume_warning()
