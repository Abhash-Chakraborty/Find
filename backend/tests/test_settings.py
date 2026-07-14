"""Integration tests for persisted settings (Phase 5.1).

Local mode (no admin) is permissive; shared mode gates writes to admins. The
hardware report reflects the persisted accel-mode preference once set.
"""

from unittest.mock import patch

from find_api.core.config import settings


class TestSettingsLocalMode:
    def test_get_defaults_to_env(self, client):
        body = client.get("/api/settings").json()
        # Env default is "auto" (no row persisted yet).
        assert body["accel_mode"] == "auto"
        assert body["ai_enabled"] is True
        assert body["map_enabled"] is False
        assert body["ml_mode"] == settings.ML_MODE
        assert "disabled" in body["supported_ml_modes"]
        assert body["trash_retention_days"] == settings.TRASH_RETENTION_DAYS

    def test_put_persists_and_reads_back(self, client):
        put = client.put("/api/settings", json={"accel_mode": "cpu"})
        assert put.status_code == 200
        assert put.json()["accel_mode"] == "cpu"

        # Subsequent GET reflects the persisted value.
        assert client.get("/api/settings").json()["accel_mode"] == "cpu"

    def test_persisted_mode_flows_into_hardware_report(self, client):
        client.put("/api/settings", json={"accel_mode": "cpu"})
        hw = client.get("/api/config/hardware").json()
        assert hw["accel_mode"] == "cpu"
        # Forced CPU resolves to a CPU-only plan.
        assert hw["resolved"]["providers"] == ["CPUExecutionProvider"]
        assert hw["resolved"]["using_gpu"] is False

    def test_persisted_mode_flows_into_app_config(self, client):
        client.put("/api/settings", json={"accel_mode": "gpu"})
        assert client.get("/api/config").json()["accel_mode"] == "gpu"

    def test_update_is_idempotent_upsert(self, client):
        client.put("/api/settings", json={"accel_mode": "cpu"})
        client.put("/api/settings", json={"accel_mode": "gpu"})
        # Second write updates the same row, not a duplicate.
        assert client.get("/api/settings").json()["accel_mode"] == "gpu"

    def test_empty_put_leaves_value_unchanged(self, client):
        client.put("/api/settings", json={"accel_mode": "cpu"})
        # No fields → no change.
        assert client.put("/api/settings", json={}).json()["accel_mode"] == "cpu"

    def test_invalid_mode_rejected(self, client):
        # Literal validation → 422, value not persisted.
        assert (
            client.put("/api/settings", json={"accel_mode": "turbo"}).status_code == 422
        )
        assert client.get("/api/settings").json()["accel_mode"] == "auto"

    def test_ai_and_map_preferences_persist_together(self, client):
        response = client.put(
            "/api/settings",
            json={"ai_enabled": False, "map_enabled": True},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["accel_mode"] == "auto"
        assert body["ai_enabled"] is False
        assert body["map_enabled"] is True
        assert body["ml_mode"] == settings.ML_MODE
        assert "disabled" in body["supported_ml_modes"]
        assert client.get("/api/config").json()["ai_enabled"] is False
        assert client.get("/api/config").json()["map_enabled"] is True

    def test_trash_retention_is_dashboard_configurable(self, client):
        response = client.put("/api/settings", json={"trash_retention_days": 7})
        assert response.status_code == 200
        assert response.json()["trash_retention_days"] == 7
        assert client.get("/api/settings").json()["trash_retention_days"] == 7

        response = client.put("/api/settings", json={"trash_retention_days": 0})
        assert response.status_code == 200
        assert response.json()["trash_retention_days"] == 0
        assert client.get("/api/settings").json()["trash_retention_days"] == 0

        assert (
            client.put("/api/settings", json={"trash_retention_days": -1}).status_code
            == 422
        )

    def test_installed_ai_mode_can_be_changed_from_settings(self, client):
        with patch("find_api.core.runtime_profile.settings.FIND_BUILD_PROFILE", "cpu"):
            response = client.put("/api/settings", json={"ml_mode": "full"})
        assert response.status_code == 200
        assert response.json()["ml_mode"] == "full"
        assert client.get("/api/config").json()["configured_ml_mode"] == "full"

    def test_uninstalled_ai_mode_is_rejected(self, client):
        with patch(
            "find_api.core.runtime_profile.settings.FIND_BUILD_PROFILE", "no-ai"
        ):
            response = client.put("/api/settings", json={"ml_mode": "full"})
        assert response.status_code == 422

    def test_runtime_endpoint_reports_worker_applied_state(self, client):
        worker_process = {
            "process": "worker",
            "updated_at": 1,
            "runtime": {"applied_mode": "mock", "preferences_source": "database"},
        }
        with (
            patch(
                "find_api.routers.config.get_worker_process_status",
                return_value=worker_process,
            ),
            patch(
                "find_api.routers.config.get_worker_runtime_status",
                return_value=worker_process["runtime"],
            ),
        ):
            body = client.get("/api/config/runtime").json()

        assert body["build_profile"]
        assert body["installed_features"]
        assert body["worker"]["applied"]["applied_mode"] == "mock"
        assert body["worker"]["health"]["state"] in {"healthy", "stale"}
