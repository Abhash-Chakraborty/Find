/**
 * Component tests for the Activity page.
 *
 * Run with: pnpm vitest run src/__tests__/activity.test.tsx
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ActivityPage from "../app/activity/page";

const api = vi.hoisted(() => ({
  getActivity: vi.fn(),
  clearActivity: vi.fn(),
  purgeActivity: vi.fn(),
}));

vi.mock("@/lib/api", () => api);

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

const activityItem = (id: number, overrides: Record<string, unknown> = {}) => ({
  id,
  category: "media",
  action: "trashed",
  user_id: null,
  media_id: id,
  payload: null,
  created_at: "2026-07-20T10:00:00+00:00",
  ...overrides,
});

const listResponse = (
  items: ReturnType<typeof activityItem>[],
  total = items.length,
) => ({
  items,
  total,
  skip: 0,
  page: 1,
  limit: 50,
});

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset();
  api.purgeActivity.mockResolvedValue({ message: "ok", deleted_count: 0 });
});

afterEach(() => {
  cleanup();
});

describe("ActivityPage", () => {
  it("shows empty state", async () => {
    api.getActivity.mockResolvedValue(listResponse([]));
    renderWithClient(<ActivityPage />);
    await waitFor(() =>
      expect(screen.getByTestId("activity-empty")).toBeInTheDocument(),
    );
  });

  it("shows an error state with a working retry", async () => {
    api.getActivity.mockRejectedValueOnce(new Error("boom"));
    renderWithClient(<ActivityPage />);
    await waitFor(() =>
      expect(screen.getByTestId("activity-retry")).toBeInTheDocument(),
    );

    api.getActivity.mockResolvedValueOnce(listResponse([activityItem(1)]));
    fireEvent.click(screen.getByTestId("activity-retry"));
    await waitFor(() =>
      expect(screen.getByTestId("activity-item-1")).toBeInTheDocument(),
    );
  });

  it("lists activity with a readable description and a link to the photo", async () => {
    api.getActivity.mockResolvedValue(
      listResponse([
        activityItem(1, {
          category: "upload",
          action: "completed",
          payload: { filename: "beach.jpg" },
        }),
      ]),
    );
    renderWithClient(<ActivityPage />);

    await waitFor(() =>
      expect(screen.getByText("Uploaded beach.jpg")).toBeInTheDocument(),
    );
    expect(screen.getByRole("link", { name: "View" })).toHaveAttribute(
      "href",
      "/image/1",
    );
  });

  it("purges expired entries on mount, best-effort", async () => {
    api.getActivity.mockResolvedValue(listResponse([]));
    renderWithClient(<ActivityPage />);
    await waitFor(() => expect(api.purgeActivity).toHaveBeenCalled());
  });

  it("refetches with the category filter when a pill is clicked", async () => {
    api.getActivity.mockResolvedValue(listResponse([activityItem(1)]));
    renderWithClient(<ActivityPage />);

    await waitFor(() =>
      expect(screen.getByTestId("activity-item-1")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Vault" }));
    await waitFor(() =>
      expect(api.getActivity).toHaveBeenCalledWith(
        expect.objectContaining({ category: "vault" }),
      ),
    );
  });

  it("clears activity", async () => {
    api.getActivity.mockResolvedValue(listResponse([activityItem(1)]));
    api.clearActivity.mockResolvedValue({
      message: "Activity cleared",
      deleted_count: 1,
    });
    renderWithClient(<ActivityPage />);

    await waitFor(() =>
      expect(screen.getByTestId("clear-activity")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("clear-activity"));
    await waitFor(() => expect(api.clearActivity).toHaveBeenCalled());
  });
});
