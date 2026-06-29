/**
 * Page test for the settings page wiring (Phase 5.1).
 *
 * Verifies the page loads the persisted accel mode and saves a change through
 * the settings API, invalidating the hardware report. The detection display is
 * covered in hardware-accel-settings.test.tsx; here we test the persistence
 * round-trip the page owns.
 *
 * Run with: pnpm vitest run src/__tests__/settings-page.test.tsx
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SettingsPage from "@/app/settings/page";
import type { AppSettings, HardwareReport } from "@/lib/api";

const { getSettings, updateSettings, getHardwareReport } = vi.hoisted(() => ({
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
  getHardwareReport: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getSettings,
  updateSettings,
  getHardwareReport,
}));

const REPORT: HardwareReport = {
  accel_mode: "cpu",
  capabilities: {
    available_providers: ["CPUExecutionProvider"],
    torch_cuda: false,
    torch_mps: false,
    has_gpu: false,
    best_gpu_provider: null,
  },
  resolved: {
    mode: "cpu",
    providers: ["CPUExecutionProvider"],
    using_gpu: false,
    fell_back_to_cpu: false,
    notice: null,
  },
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SettingsPage />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SettingsPage", () => {
  it("loads the persisted accel mode and selects it", async () => {
    getSettings.mockResolvedValue({ accel_mode: "cpu" } satisfies AppSettings);
    getHardwareReport.mockResolvedValue(REPORT);
    renderPage();

    await waitFor(() => {
      const cpuRadio = screen
        .getByTestId("accel-option-cpu")
        .querySelector("input") as HTMLInputElement;
      expect(cpuRadio.checked).toBe(true);
    });
  });

  it("persists a changed mode via updateSettings", async () => {
    getSettings.mockResolvedValue({ accel_mode: "auto" } satisfies AppSettings);
    getHardwareReport.mockResolvedValue(REPORT);
    updateSettings.mockResolvedValue({
      accel_mode: "gpu",
    } satisfies AppSettings);
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("accel-option-gpu")).toBeInTheDocument(),
    );
    const gpuRadio = screen
      .getByTestId("accel-option-gpu")
      .querySelector("input") as HTMLInputElement;
    gpuRadio.click();

    await waitFor(() =>
      expect(updateSettings).toHaveBeenCalledWith({ accel_mode: "gpu" }),
    );
  });

  it("shows a save error when the update fails", async () => {
    getSettings.mockResolvedValue({ accel_mode: "auto" } satisfies AppSettings);
    getHardwareReport.mockResolvedValue(REPORT);
    updateSettings.mockRejectedValue(new Error("boom"));
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("accel-option-cpu")).toBeInTheDocument(),
    );
    const cpuRadio = screen
      .getByTestId("accel-option-cpu")
      .querySelector("input") as HTMLInputElement;
    cpuRadio.click();

    await waitFor(() =>
      expect(screen.getByTestId("settings-save-error")).toBeInTheDocument(),
    );
  });
});
