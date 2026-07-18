"""Tests for the dimension-check decision logic in migrate_db.

Isolated from PostgreSQL by using lightweight mocks.
"""

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock


def _load_migrate_db():
    fake_settings = types.SimpleNamespace(
        DATABASE_URL="postgresql://fake/fake",
        EMBEDDING_DIM=768,
    )
    fake_config_mod = types.ModuleType("find_api.core.config")
    fake_config_mod.settings = fake_settings

    # Temporarily shim find_api.core.config so migrate_db imports the fake
    # settings during exec. CRITICAL: restore the original sys.modules entries
    # afterward — this runs at import/collection time, and leaving the fake in
    # place pollutes every later test module that imports the real `Settings`
    # (manifested as "cannot import name 'Settings' (unknown location)").
    keys = ("find_api", "find_api.core", "find_api.core.config")
    saved = {k: sys.modules.get(k) for k in keys}

    sys.modules.setdefault("find_api", types.ModuleType("find_api"))
    sys.modules.setdefault("find_api.core", types.ModuleType("find_api.core"))
    sys.modules["find_api.core.config"] = fake_config_mod

    try:
        spec = importlib.util.spec_from_file_location(
            "migrate_db",
            os.path.join(os.path.dirname(__file__), "..", "migrate_db.py"),
        )
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        # Restore real modules (or remove the shim if there was none).
        for key, original in saved.items():
            if original is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = original


_mod = _load_migrate_db()
should_clear_vectors = _mod.should_clear_vectors
get_vector_dimension = _mod.get_vector_dimension

TARGET = 768


class TestShouldClearVectors:
    def test_matching_dimension_preserves(self):
        assert should_clear_vectors(TARGET, TARGET) is False

    def test_lower_dimension_clears(self):
        assert should_clear_vectors(512, TARGET) is True

    def test_higher_dimension_clears(self):
        assert should_clear_vectors(1024, TARGET) is True

    def test_none_clears_conservatively(self):
        assert should_clear_vectors(None, TARGET) is True

    def test_non_default_target_match(self):
        assert should_clear_vectors(512, 512) is False

    def test_zero_treated_as_mismatch(self):
        assert should_clear_vectors(0, TARGET) is True


def _conn(atttypmod):
    row = MagicMock()
    row.__getitem__ = lambda s, i: atttypmod
    result = MagicMock()
    result.fetchone.return_value = row
    c = MagicMock()
    c.execute.return_value = result
    return c


def _conn_no_row():
    result = MagicMock()
    result.fetchone.return_value = None
    c = MagicMock()
    c.execute.return_value = result
    return c


class TestGetVectorDimension:
    def test_positive_atttypmod(self):
        assert get_vector_dimension(_conn(768), "media", "vector") == 768

    def test_minus_one_returns_none(self):
        assert get_vector_dimension(_conn(-1), "media", "vector") is None

    def test_zero_returns_none(self):
        assert get_vector_dimension(_conn(0), "clusters", "centroid_vector") is None

    def test_absent_column_returns_none(self):
        assert get_vector_dimension(_conn_no_row(), "media", "vector") is None

    def test_bind_params_forwarded(self):
        c = _conn(512)
        get_vector_dimension(c, "my_table", "my_col")
        params = c.execute.call_args[0][1]
        assert params["table"] == "my_table"
        assert params["column"] == "my_col"

    def test_non_default_dim(self):
        assert get_vector_dimension(_conn(1536), "media", "vector") == 1536


class TestIntegration:
    def test_match_preserves(self):
        dim = get_vector_dimension(_conn(TARGET), "media", "vector")
        assert should_clear_vectors(dim, TARGET) is False

    def test_mismatch_clears(self):
        dim = get_vector_dimension(_conn(512), "media", "vector")
        assert should_clear_vectors(dim, TARGET) is True

    def test_missing_column_clears(self):
        dim = get_vector_dimension(_conn_no_row(), "media", "vector")
        assert should_clear_vectors(dim, TARGET) is True
