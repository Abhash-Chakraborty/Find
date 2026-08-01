"""Build-capability and runtime-resolution tests for modular AI artifacts."""

from unittest.mock import patch

from find_api.core import runtime_profile
from find_api.core.runtime_profile import (
    RuntimePreferences,
    bind_runtime,
    current_accel_mode,
    current_map_enabled,
    current_ml_mode,
    installed_features,
    reset_runtime,
    resolve_runtime,
    supported_modes,
)


def _preferences(
    *, ai_enabled=True, accel_mode="auto", map_enabled=False, ml_mode="full"
):
    return RuntimePreferences(
        accel_mode=accel_mode,
        ai_enabled=ai_enabled,
        map_enabled=map_enabled,
        ml_mode=ml_mode,
    )


def test_artifacts_expose_only_installed_modes():
    # "remote" is present everywhere: it offloads inference over HTTP and needs
    # no local model runtime, so even the no-ai artifact can be pointed at a
    # remote server.
    assert supported_modes("no-ai") == ("disabled", "remote")
    assert supported_modes("mock") == ("disabled", "mock", "remote")
    assert supported_modes("cpu") == ("disabled", "mock", "full", "remote")
    assert supported_modes("nvidia") == ("disabled", "mock", "full", "remote")


def test_no_ai_artifact_is_metadata_only():
    resolution = resolve_runtime(
        _preferences(), build_profile="no-ai", configured_mode="full"
    )
    assert resolution.applied_mode == "unavailable"
    assert resolution.restart_required is True
    assert installed_features("no-ai") == ("thumbnails", "dimensions", "exif")


def test_kill_switch_disables_even_installed_full_runtime():
    resolution = resolve_runtime(
        _preferences(ai_enabled=False),
        build_profile="nvidia",
        configured_mode="full",
    )
    assert resolution.applied_mode == "disabled"
    assert resolution.restart_required is False


def test_remote_mode_is_unavailable_without_local_fallback(monkeypatch):
    """Unconfigured remote must stay unavailable and never silently run locally."""
    monkeypatch.setattr(runtime_profile.settings, "REMOTE_ML_URL", None)
    monkeypatch.setattr(runtime_profile.settings, "REMOTE_ML_API_KEY", None)

    resolution = resolve_runtime(
        _preferences(), build_profile="nvidia", configured_mode="remote"
    )
    assert resolution.applied_mode == "unavailable"
    assert resolution.restart_required is False
    assert "will not fall back" in (resolution.unavailable_reason or "").lower()


def test_configured_remote_mode_resolves_to_remote(monkeypatch):
    """A pointed-at remote server must resolve to the remote runtime.

    Resolving it to "unavailable" made every `applied_mode == "unavailable"`
    guard fire -- analyze_image raised RuntimeUnavailableError before the
    remote dispatch was reached, so remote mode could not ingest anything.
    """
    monkeypatch.setattr(
        runtime_profile.settings, "REMOTE_ML_URL", "https://ml.example.com"
    )
    monkeypatch.setattr(runtime_profile.settings, "REMOTE_ML_API_KEY", "token")

    resolution = resolve_runtime(
        _preferences(), build_profile="nvidia", configured_mode="remote"
    )
    assert resolution.applied_mode == "remote"
    assert resolution.unavailable_reason is None
    assert resolution.restart_required is False


def test_remote_mode_is_supported_in_slim_profiles(monkeypatch):
    """Remote needs no local model runtime, so no-ai artifacts can use it."""
    monkeypatch.setattr(
        runtime_profile.settings, "REMOTE_ML_URL", "https://ml.example.com"
    )
    monkeypatch.setattr(runtime_profile.settings, "REMOTE_ML_API_KEY", "token")

    resolution = resolve_runtime(
        _preferences(), build_profile="no-ai", configured_mode="remote"
    )
    assert resolution.applied_mode == "remote"
    assert "remote" in resolution.supported_modes


def test_bound_job_preferences_drive_all_runtime_seams_and_reset():
    resolution = resolve_runtime(
        _preferences(accel_mode="cpu", map_enabled=True),
        build_profile="cpu",
        configured_mode="mock",
    )
    with (
        patch("find_api.core.runtime_profile.settings.ML_MODE", "disabled"),
        patch("find_api.core.runtime_profile.settings.ACCEL_MODE", "auto"),
        patch("find_api.core.runtime_profile.settings.MAP_ENABLED", False),
    ):
        tokens = bind_runtime(resolution)
        try:
            assert current_ml_mode() == "mock"
            assert current_accel_mode() == "cpu"
            assert current_map_enabled() is True
        finally:
            reset_runtime(tokens)

        assert current_map_enabled() is False
