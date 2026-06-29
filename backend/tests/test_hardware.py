"""Unit tests for hardware capability resolution (Phase 5.2/5.3).

Focus on the pure `resolve_execution` logic and the safe detection contract.
The Auto/GPU/CPU matrix + automatic CPU fallback is the acceptance behavior
for the low-end/edge goal, so it is covered exhaustively here.
"""

from find_api.core.hardware import (
    CPU_EP,
    CUDA_EP,
    COREML_EP,
    DIRECTML_EP,
    ROCM_EP,
    CapabilityReport,
    detect_capabilities,
    resolve_execution,
    resolve_torch_device,
)


def _report(providers):
    return CapabilityReport(available_providers=providers)


class TestCapabilityReport:
    def test_cpu_only_has_no_gpu(self):
        r = _report([CPU_EP])
        assert r.has_gpu is False
        assert r.best_gpu_provider() is None

    def test_best_gpu_provider_prefers_cuda(self):
        r = _report([CUDA_EP, DIRECTML_EP, CPU_EP])
        assert r.best_gpu_provider() == CUDA_EP

    def test_best_gpu_provider_preference_order(self):
        # ROCm preferred over CoreML/DirectML when CUDA absent.
        assert _report([DIRECTML_EP, ROCM_EP, CPU_EP]).best_gpu_provider() == ROCM_EP
        assert _report([DIRECTML_EP, COREML_EP, CPU_EP]).best_gpu_provider() == COREML_EP
        assert _report([DIRECTML_EP, CPU_EP]).best_gpu_provider() == DIRECTML_EP


class TestResolveCpuMode:
    def test_cpu_mode_always_cpu(self):
        plan = resolve_execution("cpu", _report([CUDA_EP, CPU_EP]))
        assert plan.providers == [CPU_EP]
        assert plan.using_gpu is False
        assert plan.fell_back_to_cpu is False
        assert plan.notice is None


class TestResolveGpuMode:
    def test_gpu_mode_uses_gpu_when_available(self):
        plan = resolve_execution("gpu", _report([CUDA_EP, CPU_EP]))
        assert plan.providers == [CUDA_EP, CPU_EP]
        assert plan.using_gpu is True
        assert plan.fell_back_to_cpu is False
        assert plan.notice is None

    def test_gpu_mode_falls_back_to_cpu_with_notice(self):
        """The core low-end acceptance: forced GPU with no GPU → CPU, no crash."""
        plan = resolve_execution("gpu", _report([CPU_EP]))
        assert plan.providers == [CPU_EP]
        assert plan.using_gpu is False
        assert plan.fell_back_to_cpu is True
        assert plan.notice is not None
        assert "CPU" in plan.notice

    def test_gpu_providers_always_end_with_cpu_fallback(self):
        # CPU appended so ORT can fall back per-op if GPU init fails at runtime.
        plan = resolve_execution("gpu", _report([DIRECTML_EP, CPU_EP]))
        assert plan.providers[-1] == CPU_EP
        assert plan.providers[0] == DIRECTML_EP


class TestResolveAutoMode:
    def test_auto_uses_gpu_when_present(self):
        plan = resolve_execution("auto", _report([CUDA_EP, CPU_EP]))
        assert plan.providers == [CUDA_EP, CPU_EP]
        assert plan.using_gpu is True
        assert plan.fell_back_to_cpu is False

    def test_auto_uses_cpu_silently_when_no_gpu(self):
        # CPU is the expected baseline in auto, not a failure → no fallback flag.
        plan = resolve_execution("auto", _report([CPU_EP]))
        assert plan.providers == [CPU_EP]
        assert plan.fell_back_to_cpu is False
        assert plan.notice is None

    def test_unknown_mode_treated_as_auto(self):
        plan = resolve_execution("weird", _report([CUDA_EP, CPU_EP]))  # type: ignore
        assert plan.using_gpu is True

    def test_mode_is_case_insensitive(self):
        assert resolve_execution("GPU", _report([CUDA_EP, CPU_EP])).using_gpu is True
        assert resolve_execution("Cpu", _report([CUDA_EP, CPU_EP])).providers == [CPU_EP]


class TestDetectionIsSafe:
    def test_detect_never_raises_and_always_has_cpu(self):
        # On CI there may be no GPU and possibly no onnxruntime/torch; detection
        # must still return a usable report with CPU present.
        report = detect_capabilities()
        assert CPU_EP in report.available_providers
        # Serializable for the API.
        d = report.to_dict()
        assert "available_providers" in d and "has_gpu" in d


class TestExecutionPlanSerialization:
    def test_to_dict_shape(self):
        plan = resolve_execution("gpu", _report([CPU_EP]))
        d = plan.to_dict()
        assert set(d) == {
            "mode",
            "providers",
            "using_gpu",
            "fell_back_to_cpu",
            "notice",
        }


class TestResolveTorchDevice:
    """Pure torch-device resolution for Find's PyTorch models."""

    def test_cpu_mode_always_cpu(self):
        assert resolve_torch_device("cpu", cuda_available=True, mps_available=True) == "cpu"

    def test_gpu_mode_uses_cuda_when_available(self):
        assert resolve_torch_device("gpu", cuda_available=True) == "cuda"

    def test_gpu_mode_prefers_cuda_over_mps(self):
        assert (
            resolve_torch_device("gpu", cuda_available=True, mps_available=True)
            == "cuda"
        )

    def test_gpu_mode_uses_mps_when_no_cuda(self):
        assert (
            resolve_torch_device("gpu", cuda_available=False, mps_available=True)
            == "mps"
        )

    def test_gpu_mode_falls_back_to_cpu(self):
        # Forced GPU with no accelerator → CPU (no crash, the §5 acceptance).
        assert (
            resolve_torch_device("gpu", cuda_available=False, mps_available=False)
            == "cpu"
        )

    def test_auto_uses_gpu_when_present(self):
        assert resolve_torch_device("auto", cuda_available=True) == "cuda"

    def test_auto_falls_back_to_cpu_silently(self):
        assert (
            resolve_torch_device("auto", cuda_available=False, mps_available=False)
            == "cpu"
        )

    def test_case_insensitive(self):
        assert resolve_torch_device("CPU", cuda_available=True) == "cpu"
