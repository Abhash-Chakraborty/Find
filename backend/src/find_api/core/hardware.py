"""Hardware acceleration capability detection + execution-provider resolution.

Two clearly separated concerns:

- **Detection** (`detect_capabilities`): probe the host for available
  accelerators (CUDA/ROCm/CoreML/DirectML/CPU). Every probe is wrapped so a
  missing library or driver degrades gracefully to "not available" — detection
  must NEVER raise, because it runs on every platform incl. CPU-only/edge.
- **Resolution** (`resolve_execution`): pure function mapping a requested mode
  (``auto``/``gpu``/``cpu``) + a capability report to the ONNX Runtime
  execution-provider list to use, with **automatic CPU fallback** and a
  non-blocking notice when a requested GPU path isn't available. No hardware
  access here, so it is fully unit-testable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, Optional

logger = logging.getLogger(__name__)

AccelMode = Literal["auto", "gpu", "cpu"]

# ONNX Runtime execution provider identifiers.
CPU_EP = "CPUExecutionProvider"
CUDA_EP = "CUDAExecutionProvider"
ROCM_EP = "ROCMExecutionProvider"
COREML_EP = "CoreMLExecutionProvider"
DIRECTML_EP = "DmlExecutionProvider"

# GPU providers in preference order (best first).
_GPU_EP_PREFERENCE = [CUDA_EP, ROCM_EP, COREML_EP, DIRECTML_EP]


@dataclass
class CapabilityReport:
    """What the host can do, as detected (or injected for tests)."""

    # ONNX Runtime execution providers actually available in this process.
    available_providers: list[str] = field(default_factory=lambda: [CPU_EP])
    # torch device hints (best-effort; independent of ONNX).
    torch_cuda: bool = False
    torch_mps: bool = False  # Apple Metal

    # Convenience: any non-CPU provider present.
    @property
    def has_gpu(self) -> bool:
        return any(ep in self.available_providers for ep in _GPU_EP_PREFERENCE)

    def best_gpu_provider(self) -> Optional[str]:
        for ep in _GPU_EP_PREFERENCE:
            if ep in self.available_providers:
                return ep
        return None

    def to_dict(self) -> dict:
        return {
            "available_providers": self.available_providers,
            "torch_cuda": self.torch_cuda,
            "torch_mps": self.torch_mps,
            "has_gpu": self.has_gpu,
            "best_gpu_provider": self.best_gpu_provider(),
        }


@dataclass
class ExecutionPlan:
    """Resolved execution decision for a requested accel mode."""

    mode: AccelMode
    # Ordered EP list to hand to an ONNX Runtime InferenceSession.
    providers: list[str]
    # True when a GPU was requested/preferred but we fell back to CPU.
    fell_back_to_cpu: bool
    # Human-readable, non-blocking notice (or None).
    notice: Optional[str] = None

    @property
    def using_gpu(self) -> bool:
        return any(ep in self.providers for ep in _GPU_EP_PREFERENCE)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "providers": self.providers,
            "using_gpu": self.using_gpu,
            "fell_back_to_cpu": self.fell_back_to_cpu,
            "notice": self.notice,
        }


# --- Detection (never raises) ----------------------------------------------
def _safe_onnx_providers() -> list[str]:
    try:
        import onnxruntime as ort  # type: ignore

        providers = list(ort.get_available_providers())
        # Guarantee CPU is always present as the floor.
        if CPU_EP not in providers:
            providers.append(CPU_EP)
        return providers
    except Exception as exc:  # noqa: BLE001
        logger.debug("ONNX Runtime not available for provider probe: %s", exc)
        return [CPU_EP]


def _safe_torch_devices() -> tuple[bool, bool]:
    """Return (cuda_available, mps_available), never raising."""
    cuda = False
    mps = False
    try:
        import torch  # type: ignore

        try:
            cuda = bool(torch.cuda.is_available())
        except Exception:  # noqa: BLE001
            cuda = False
        try:
            mps = bool(
                getattr(torch.backends, "mps", None)
                and torch.backends.mps.is_available()
            )
        except Exception:  # noqa: BLE001
            mps = False
    except Exception as exc:  # noqa: BLE001
        logger.debug("torch not available for device probe: %s", exc)
    return cuda, mps


def detect_capabilities() -> CapabilityReport:
    """Probe the host for accelerators. Safe on any platform (never raises)."""
    providers = _safe_onnx_providers()
    cuda, mps = _safe_torch_devices()
    return CapabilityReport(
        available_providers=providers,
        torch_cuda=cuda,
        torch_mps=mps,
    )


# --- Resolution (pure) -----------------------------------------------------
def resolve_torch_device(
    mode: AccelMode,
    *,
    cuda_available: bool,
    mps_available: bool = False,
) -> str:
    """Pure mapping of accel mode + torch availability → device string.

    Returns "cuda", "mps", or "cpu". Mirrors `resolve_execution`'s policy for
    Find's PyTorch models (open_clip / InsightFace / YOLO):
      - cpu  → always "cpu".
      - gpu  → best GPU (cuda > mps); **auto-fall back to "cpu"** if none.
      - auto → best GPU if present, else "cpu" silently.

    Injecting the availability flags keeps this unit-testable without a GPU.
    """
    normalized: AccelMode = mode.lower() if isinstance(mode, str) else mode  # type: ignore
    if normalized == "cpu":
        return "cpu"
    if cuda_available:
        return "cuda"
    if mps_available:
        return "mps"
    # gpu requested but unavailable, or auto with no GPU → CPU fallback.
    return "cpu"


def current_torch_device() -> str:
    """Resolve the torch device for the configured ACCEL_MODE, probing torch.

    Live helper used by the ML modules. Never raises — degrades to "cpu".
    Honors the legacy ``USE_GPU=false`` as a hard CPU pin for back-compat.
    """
    # Imported lazily to avoid a hard dependency at module import.
    from find_api.core.config import settings

    mode: AccelMode = getattr(settings, "ACCEL_MODE", "auto")
    # Back-compat: an explicit USE_GPU=False forces CPU regardless of mode.
    if getattr(settings, "USE_GPU", True) is False and mode == "auto":
        return "cpu"
    cuda, mps = _safe_torch_devices()
    return resolve_torch_device(mode, cuda_available=cuda, mps_available=mps)


def resolve_execution(mode: AccelMode, report: CapabilityReport) -> ExecutionPlan:
    """Map a requested mode + capabilities to an execution plan.

    - ``cpu``: always CPU, no notice.
    - ``gpu``: use the best GPU provider; if none, **fall back to CPU** with a
      notice (no crash, no hard GPU dependency).
    - ``auto``: use the best GPU provider when present, else CPU silently
      (CPU is the expected baseline, not a failure).

    The returned ``providers`` list always ends with CPU so ONNX Runtime can
    fall back per-op if a GPU provider fails to initialize at session time.
    """
    normalized: AccelMode = mode.lower() if isinstance(mode, str) else mode  # type: ignore

    if normalized == "cpu":
        return ExecutionPlan(mode="cpu", providers=[CPU_EP], fell_back_to_cpu=False)

    gpu_ep = report.best_gpu_provider()

    if normalized == "gpu":
        if gpu_ep is None:
            return ExecutionPlan(
                mode="gpu",
                providers=[CPU_EP],
                fell_back_to_cpu=True,
                notice=(
                    "GPU acceleration was requested but no GPU execution "
                    "provider is available; using CPU instead."
                ),
            )
        return ExecutionPlan(
            mode="gpu", providers=[gpu_ep, CPU_EP], fell_back_to_cpu=False
        )

    # auto (default + any unknown value treated as auto)
    if gpu_ep is None:
        return ExecutionPlan(mode="auto", providers=[CPU_EP], fell_back_to_cpu=False)
    return ExecutionPlan(
        mode="auto", providers=[gpu_ep, CPU_EP], fell_back_to_cpu=False
    )
