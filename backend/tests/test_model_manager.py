import pytest
from unittest.mock import MagicMock
from find_api.core.model_manager import ModelManager, get_model_manager


@pytest.fixture
def fresh_model_manager():
    """Provide a fresh instance of ModelManager for each test.

    Since ModelManager is a singleton, we temporarily bypass the singleton instance
    creation in the fixture to ensure a completely clean state.
    """
    # Create a new instance bypassing the singleton cache in __new__
    manager = object.__new__(ModelManager)
    manager._initialized = False
    manager.__init__()
    return manager


def test_model_manager_singleton():
    """Verify that ModelManager behaves as a singleton under normal usage."""
    m1 = get_model_manager()
    m2 = get_model_manager()
    assert m1 is m2


def test_get_model_success(fresh_model_manager):
    """Verify that a successful model loader caches and returns the model correctly."""
    loader_mock = MagicMock(return_value="fake-florence-model")

    # First call: invokes loader
    model = fresh_model_manager.get_model("test-model", loader_mock)
    assert model == "fake-florence-model"
    loader_mock.assert_called_once()

    # Second call: returns cached model without calling loader again
    loader_mock.reset_mock()
    model_cached = fresh_model_manager.get_model("test-model", loader_mock)
    assert model_cached == "fake-florence-model"
    loader_mock.assert_not_called()


def test_get_model_failure_caches_exception(fresh_model_manager):
    """Verify that a failing model loader caches the exception and raises it on retries."""
    loader_mock = MagicMock(side_effect=RuntimeError("CUDA OOM or loading error"))

    # First call: raises the exception and caches it
    with pytest.raises(RuntimeError, match="CUDA OOM or loading error"):
        fresh_model_manager.get_model("failing-model", loader_mock)
    loader_mock.assert_called_once()

    # Second call: raises the same exception without executing loader again
    loader_mock.reset_mock()
    with pytest.raises(RuntimeError, match="CUDA OOM or loading error"):
        fresh_model_manager.get_model("failing-model", loader_mock)
    loader_mock.assert_not_called()


def test_multiple_models_isolated(fresh_model_manager):
    """Verify that multiple models have isolated loading, caching, and error states."""
    success_loader = MagicMock(return_value="good-model")
    fail_loader = MagicMock(side_effect=ValueError("Invalid configuration"))

    # Load failing model
    with pytest.raises(ValueError, match="Invalid configuration"):
        fresh_model_manager.get_model("model-bad", fail_loader)

    # Load successful model (should load fine, isolated from the failed model)
    good_model = fresh_model_manager.get_model("model-good", success_loader)
    assert good_model == "good-model"
    success_loader.assert_called_once()

    # Re-access failing model (should raise cached exception, no load attempt)
    fail_loader.reset_mock()
    with pytest.raises(ValueError, match="Invalid configuration"):
        fresh_model_manager.get_model("model-bad", fail_loader)
    fail_loader.assert_not_called()

    # Re-access successful model (should return cached model, no load attempt)
    success_loader.reset_mock()
    good_model_cached = fresh_model_manager.get_model("model-good", success_loader)
    assert good_model_cached == "good-model"
    success_loader.assert_not_called()


def test_get_model_concurrent_loading(fresh_model_manager):
    """Verify that concurrent threads loading the same model only trigger the loader once and receive the same instance."""
    import threading
    import time

    call_count = 0
    call_count_lock = threading.Lock()

    def slow_loader():
        nonlocal call_count
        time.sleep(0.05)  # stretch race condition window
        with call_count_lock:
            call_count += 1
        return "concurrent-success-model"

    results = []
    threads = []
    barrier = threading.Barrier(10)

    def worker():
        barrier.wait()  # lock-step trigger
        try:
            model = fresh_model_manager.get_model("concurrent-model", slow_loader)
            results.append((model, None))
        except Exception as e:
            results.append((None, e))

    for _ in range(10):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert len(results) == 10
    for model, err in results:
        assert err is None
        assert model == "concurrent-success-model"

    # Loader must be called exactly once
    assert call_count == 1


def test_get_model_concurrent_failure(fresh_model_manager):
    """Verify that concurrent threads loading a failing model only trigger the loader once and all raise the same cached exception."""
    import threading
    import time

    call_count = 0
    call_count_lock = threading.Lock()

    def slow_failing_loader():
        nonlocal call_count
        time.sleep(0.05)  # stretch race condition window
        with call_count_lock:
            call_count += 1
        raise RuntimeError("Fatal loading failure")

    results = []
    threads = []
    barrier = threading.Barrier(10)

    def worker():
        barrier.wait()  # lock-step trigger
        try:
            fresh_model_manager.get_model("concurrent-fail-model", slow_failing_loader)
            results.append((True, None))
        except Exception as e:
            results.append((False, e))

    for _ in range(10):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert len(results) == 10
    for success, err in results:
        assert not success
        assert isinstance(err, RuntimeError)
        assert str(err) == "Fatal loading failure"

    # Failing loader must be executed exactly once
    assert call_count == 1
