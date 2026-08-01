import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AboutSettings } from "@/components/about-settings";

const api = vi.hoisted(() => ({
  getAppConfig: vi.fn(),
  getRuntimeConfig: vi.fn(),
}));

vi.mock("@/lib/api", () => api);

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

const appConfig = {
  app_version: "1.1.3",
  ml_mode: "mock",
  configured_ml_mode: "mock",
  accel_mode: "cpu",
  ai_enabled: true,
  map_enabled: false,
  build_profile: "mock",
  supported_ml_modes: ["disabled", "mock"],
};

const runtimeConfig = {
  build_profile: "mock",
  supported_modes: ["disabled", "mock"],
  configured_mode: "mock",
  configured_accel_mode: "cpu",
  ai_enabled: true,
  map_enabled: false,
  applied_mode: "mock",
  installed_features: [],
  restart_required: false,
  unavailable_reason: null,
  worker: { health: { state: "healthy", age_seconds: 8 }, applied: null },
};

function mockClipboard(writeText: ReturnType<typeof vi.fn>) {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
    writable: true,
  });
}

beforeEach(() => {
  api.getAppConfig.mockReset();
  api.getRuntimeConfig.mockReset();
  api.getAppConfig.mockResolvedValue(appConfig);
  api.getRuntimeConfig.mockResolvedValue(runtimeConfig);
});

afterEach(() => {
  cleanup();
});

describe("AboutSettings", () => {
  it("renders the version, build profile, applied AI mode, and worker health", async () => {
    renderWithClient(<AboutSettings />);

    expect(
      await screen.findByRole("heading", { name: "About this instance" }),
    ).toBeInTheDocument();

    const details = screen.getByTestId("about-details");
    await waitFor(() => expect(details).toHaveTextContent("1.1.3"));
    expect(details).toHaveTextContent("mock");
    await waitFor(() => expect(details).toHaveTextContent("Healthy"));
    expect(details).toHaveTextContent("last seen 8s ago");
  });

  it("notes when AI is switched off", async () => {
    api.getAppConfig.mockResolvedValue({ ...appConfig, ai_enabled: false });
    renderWithClient(<AboutSettings />);

    await waitFor(() =>
      expect(screen.getByTestId("about-details")).toHaveTextContent("(AI off)"),
    );
  });

  it("copies the support summary and reports success", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    mockClipboard(writeText);
    renderWithClient(<AboutSettings />);

    await waitFor(() =>
      expect(screen.getByTestId("about-details")).toHaveTextContent("1.1.3"),
    );
    fireEvent.click(screen.getByTestId("copy-support-summary"));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const copied = writeText.mock.calls[0]?.[0] as string;
    expect(copied).toContain("App version: 1.1.3");
    expect(copied).toContain("Worker: healthy, last seen 8s ago");

    await waitFor(() =>
      expect(screen.getByTestId("copy-status")).toHaveTextContent(
        "Support summary copied.",
      ),
    );
  });

  it("explains the fallback when the clipboard is unavailable", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    mockClipboard(writeText);
    renderWithClient(<AboutSettings />);

    fireEvent.click(screen.getByTestId("copy-support-summary"));

    await waitFor(() =>
      expect(screen.getByTestId("copy-status")).toHaveTextContent(
        "Couldn't copy. Select the details above and copy manually.",
      ),
    );
  });

  it("surfaces an alert when the version cannot be read", async () => {
    api.getAppConfig.mockRejectedValue(new Error("offline"));
    renderWithClient(<AboutSettings />);

    expect(await screen.findByTestId("about-error")).toHaveTextContent(
      "Couldn't read the instance version.",
    );
    expect(screen.queryByTestId("about-details")).not.toBeInTheDocument();
  });

  it("still copies a summary when the worker state is unknown", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    mockClipboard(writeText);
    api.getRuntimeConfig.mockRejectedValue(new Error("offline"));
    renderWithClient(<AboutSettings />);

    await waitFor(() =>
      expect(screen.getByTestId("about-details")).toHaveTextContent("1.1.3"),
    );
    fireEvent.click(screen.getByTestId("copy-support-summary"));

    await waitFor(() => expect(writeText).toHaveBeenCalled());
    expect(writeText.mock.calls[0]?.[0]).toContain(
      "Worker: unknown, last seen unknown",
    );
  });
});
