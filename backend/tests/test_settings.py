"""Integration tests for persisted settings (Phase 5.1).

Local mode (no admin) is permissive; shared mode gates writes to admins. The
hardware report reflects the persisted accel-mode preference once set.
"""


class TestSettingsLocalMode:
    def test_get_defaults_to_env(self, client):
        body = client.get("/api/settings").json()
        # Env default is "auto" (no row persisted yet).
        assert body["accel_mode"] == "auto"

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
