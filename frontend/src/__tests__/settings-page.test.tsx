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
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SettingsPage from "@/app/settings/page";
import type { AppSettings, HardwareReport } from "@/lib/api";

const { getSettings, updateSettings, getHardwareReport, getRuntimeConfig } =
  vi.hoisted(() => ({
    getSettings: vi.fn(),
    updateSettings: vi.fn(),
    getHardwareReport: vi.fn(),
    getRuntimeConfig: vi.fn(),
  }));

vi.mock("@/lib/api", () => ({
  getSettings,
  updateSettings,
  getHardwareReport,
  getRuntimeConfig,
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
  const settings = (overrides: Partial<AppSettings> = {}): AppSettings => ({
    accel_mode: "auto",
    ai_enabled: true,
    map_enabled: false,
    ml_mode: "full",
    supported_ml_modes: ["disabled", "mock", "full"],
    trash_retention_days: 30,
    ...overrides,
  });

  const prepareRuntime = () => {
    getRuntimeConfig.mockResolvedValue({
      build_profile: "cpu",
      applied_mode: "full",
      ai_enabled: true,
      restart_required: false,
      unavailable_reason: null,
      worker: { health: { state: "healthy", age_seconds: 1 }, applied: null },
    });
  };

  it("loads the persisted accel mode and selects it", async () => {
    prepareRuntime();
    getSettings.mockResolvedValue(settings({ accel_mode: "cpu" }));
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
    prepareRuntime();
    getSettings.mockResolvedValue(settings());
    getHardwareReport.mockResolvedValue(REPORT);
    updateSettings.mockResolvedValue(settings({ accel_mode: "gpu" }));
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
    prepareRuntime();
    getSettings.mockResolvedValue(settings());
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

  it("requires an explicit opt-in before enabling EXIF location storage", async () => {
    prepareRuntime();
    getSettings.mockResolvedValue(settings());
    getHardwareReport.mockResolvedValue(REPORT);
    updateSettings.mockResolvedValue(settings({ map_enabled: true }));
    renderPage();

    const mapSwitch = await screen.findByRole("switch", {
      name: /enable private photo map/i,
    });
    await waitFor(() => expect(mapSwitch).toBeEnabled());
    expect(mapSwitch).toHaveAttribute("aria-checked", "false");
    fireEvent.click(mapSwitch);

    await waitFor(() =>
      expect(updateSettings).toHaveBeenCalledWith({ map_enabled: true }),
    );
  });

  it("controls AI jobs and reports the installed artifact", async () => {
    prepareRuntime();
    getSettings.mockResolvedValue(settings({ ai_enabled: true }));
    updateSettings.mockResolvedValue(settings({ ai_enabled: false }));
    renderPage();

    expect(await screen.findByText("cpu")).toBeInTheDocument();
    const aiSwitch = screen.getByRole("switch", {
      name: /enable local ai processing/i,
    });
    fireEvent.click(aiSwitch);
    await waitFor(() =>
      expect(updateSettings).toHaveBeenCalledWith({ ai_enabled: false }),
    );
  });

  it("switches directly to any AI mode installed in the artifact", async () => {
    prepareRuntime();
    getSettings.mockResolvedValue(settings({ ml_mode: "mock" }));
    updateSettings.mockResolvedValue(settings({ ml_mode: "full" }));
    renderPage();

    const mode = await screen.findByLabelText(/processing mode/i);
    fireEvent.change(mode, { target: { value: "full" } });
    await waitFor(() =>
      expect(updateSettings).toHaveBeenCalledWith({ ml_mode: "full" }),
    );
  });
});
