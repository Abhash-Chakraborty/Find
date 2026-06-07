import time

import pytest

from find_api.core.model_manager import ModelManager


@pytest.fixture(autouse=True)
def reset_model_manager_state():
    """Keep the singleton manager isolated between tests."""
    manager = ModelManager()
    manager.reset_for_tests()
    yield
    manager.reset_for_tests()


def test_model_manager_lazy_loading():
    """Verify that models are only loaded when requested"""
    manager = ModelManager()

    loader_called = 0

    def mock_loader():
        nonlocal loader_called
        loader_called += 1
        return "fake_model"

    assert "test_model" not in manager.models

    # First call loads
    model = manager.get_model("test_model", mock_loader)
    assert model == "fake_model"
    assert loader_called == 1
    assert "test_model" in manager.models

    # Second call uses cache
    model = manager.get_model("test_model", mock_loader)
    assert model == "fake_model"
    assert loader_called == 1


def test_model_manager_unload_idle():
    """Verify that idle models are unloaded after TTL"""
    manager = ModelManager()

    def mock_loader():
        return "fake_model"

    manager.get_model("test_model", mock_loader)
    assert "test_model" in manager.models

    # Set last_used to way back
    manager.last_used["test_model"] = time.time() - 1000

    # Unload with TTL of 600 - should unload
    manager.unload_idle_models(600)
    assert "test_model" not in manager.models
    assert "test_model" not in manager.last_used


def test_model_manager_do_not_unload_active():
    """Verify that active models are NOT unloaded if within TTL"""
    manager = ModelManager()

    def mock_loader():
        return "fake_model"

    manager.get_model("test_model", mock_loader)

    # Unload with TTL of 600 - should NOT unload
    manager.unload_idle_models(600)
    assert "test_model" in manager.models


def test_model_manager_does_not_unload_in_flight_model():
    """Verify that leased models are not unloaded while inference is active."""
    manager = ModelManager()

    def mock_loader():
        return "fake_model"

    with manager.use_model("test_model", mock_loader):
        manager.last_used["test_model"] = time.time() - 1000
        manager.unload_idle_models(600)
        assert "test_model" in manager.models

    manager.last_used["test_model"] = time.time() - 1000
    manager.unload_idle_models(600)
    assert "test_model" not in manager.models


def test_model_manager_max_models():
    """Verify that oldest models are unloaded when capacity is reached"""
    manager = ModelManager()
    manager.set_max_models(2)

    def loader():
        return "model"

    manager.get_model("m1", loader)
    time.sleep(0.01)
    manager.get_model("m2", loader)
    time.sleep(0.01)

    assert len(manager.models) == 2
    assert "m1" in manager.models
    assert "m2" in manager.models

    # Loading m3 should unload m1 (the oldest)
    manager.get_model("m3", loader)
    assert len(manager.models) == 2
    assert "m1" not in manager.models
    assert "m2" in manager.models
    assert "m3" in manager.models


def test_model_manager_rejects_invalid_capacity():
    """Verify invalid model capacity settings are rejected."""
    manager = ModelManager()

    with pytest.raises(ValueError):
        manager.set_max_models(0)
