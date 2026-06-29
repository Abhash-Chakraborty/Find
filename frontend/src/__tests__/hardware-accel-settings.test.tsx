/**
 * Component tests for HardwareAccelSettings.
 *
 * Mocks the hardware report API and verifies the toggle, the detected-vs-using
 * display, and the CPU-fallback notice — the user-facing surface of the Phase 5
 * speed/low-end goal.
 *
 * Run with: pnpm vitest run src/__tests__/hardware-accel-settings.test.tsx
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HardwareAccelSettings } from "@/components/hardware-accel-settings";
import type { HardwareReport } from "@/lib/api";

const { getHardwareReport } = vi.hoisted(() => ({
  getHardwareReport: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getHardwareReport,
}));

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

const GPU_REPORT: HardwareReport = {
  accel_mode: "auto",
  capabilities: {
    available_providers: ["CUDAExecutionProvider", "CPUExecutionProvider"],
    torch_cuda: true,
    torch_mps: false,
    has_gpu: true,
    best_gpu_provider: "CUDAExecutionProvider",
  },
  resolved: {
    mode: "auto",
    providers: ["CUDAExecutionProvider", "CPUExecutionProvider"],
    using_gpu: true,
    fell_back_to_cpu: false,
    notice: null,
  },
};

const CPU_FALLBACK_REPORT: HardwareReport = {
  accel_mode: "gpu",
  capabilities: {
    available_providers: ["CPUExecutionProvider"],
    torch_cuda: false,
    torch_mps: false,
    has_gpu: false,
    best_gpu_provider: null,
  },
  resolved: {
    mode: "gpu",
    providers: ["CPUExecutionProvider"],
    using_gpu: false,
    fell_back_to_cpu: true,
    notice:
      "GPU acceleration was requested but no GPU execution provider is available; using CPU instead.",
  },
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("HardwareAccelSettings", () => {
  it("renders the three accel mode options", async () => {
    getHardwareReport.mockResolvedValue(GPU_REPORT);
    renderWithClient(<HardwareAccelSettings />);

    expect(screen.getByTestId("accel-option-auto")).toBeInTheDocument();
    expect(screen.getByTestId("accel-option-gpu")).toBeInTheDocument();
    expect(screen.getByTestId("accel-option-cpu")).toBeInTheDocument();
  });

  it("shows detected GPU and that it is in use", async () => {
    getHardwareReport.mockResolvedValue(GPU_REPORT);
    renderWithClient(<HardwareAccelSettings />);

    await waitFor(() =>
      expect(screen.getByTestId("accel-detected")).toHaveTextContent(
        "GPU available",
      ),
    );
    expect(screen.getByTestId("accel-using")).toHaveTextContent("GPU");
    expect(screen.queryByTestId("accel-notice")).toBeNull();
  });

  it("surfaces the CPU-fallback notice when GPU is unavailable", async () => {
    getHardwareReport.mockResolvedValue(CPU_FALLBACK_REPORT);
    renderWithClient(<HardwareAccelSettings />);

    await waitFor(() =>
      expect(screen.getByTestId("accel-detected")).toHaveTextContent(
        "No GPU detected",
      ),
    );
    expect(screen.getByTestId("accel-using")).toHaveTextContent("CPU");
    expect(screen.getByTestId("accel-notice")).toHaveTextContent(
      /using CPU instead/i,
    );
  });

  it("reflects the controlled selected mode", async () => {
    getHardwareReport.mockResolvedValue(GPU_REPORT);
    renderWithClient(<HardwareAccelSettings value="cpu" />);

    const cpuRadio = screen
      .getByTestId("accel-option-cpu")
      .querySelector("input") as HTMLInputElement;
    expect(cpuRadio.checked).toBe(true);
  });

  it("calls onChange when a different mode is picked", async () => {
    getHardwareReport.mockResolvedValue(GPU_REPORT);
    const onChange = vi.fn();
    renderWithClient(
      <HardwareAccelSettings value="auto" onChange={onChange} />,
    );

    const cpuRadio = screen
      .getByTestId("accel-option-cpu")
      .querySelector("input") as HTMLInputElement;
    cpuRadio.click();
    expect(onChange).toHaveBeenCalledWith("cpu");
  });

  it("shows an error state when the report fails to load", async () => {
    getHardwareReport.mockRejectedValue(new Error("boom"));
    renderWithClient(<HardwareAccelSettings />);

    await waitFor(() =>
      expect(screen.getByTestId("accel-error")).toBeInTheDocument(),
    );
  });
});
