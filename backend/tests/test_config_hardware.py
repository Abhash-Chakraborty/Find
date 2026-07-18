"""Tests for config + hardware capability endpoints (Phase 5.2/5.3)."""


class TestConfigEndpoint:
    def test_config_includes_ml_and_accel_mode(self, client):
        body = client.get("/api/config").json()
        assert "ml_mode" in body
        assert "accel_mode" in body
        assert body["accel_mode"] in ("auto", "gpu", "cpu")


class TestHardwareEndpoint:
    def test_hardware_report_shape(self, client):
        body = client.get("/api/config/hardware").json()
        assert "accel_mode" in body
        assert "capabilities" in body
        assert "resolved" in body

        caps = body["capabilities"]
        assert "available_providers" in caps
        assert "has_gpu" in caps
        # CPU is always a floor.
        assert "CPUExecutionProvider" in caps["available_providers"]

        resolved = body["resolved"]
        assert set(resolved) == {
            "mode",
            "providers",
            "using_gpu",
            "fell_back_to_cpu",
            "notice",
        }
        # The resolved provider list always ends with a CPU fallback.
        assert resolved["providers"][-1] == "CPUExecutionProvider"
