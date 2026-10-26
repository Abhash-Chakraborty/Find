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

  it("refreshes the feed once the retention purge has deleted rows", async () => {
    // The purge round-trip lands after the initial list load, which is the
    // race that leaves already-deleted rows on screen.
    api.purgeActivity.mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(() => resolve({ message: "purged", deleted_count: 2 }), 0);
        }),
    );
    api.getActivity.mockResolvedValue(listResponse([activityItem(1)]));
    renderWithClient(<ActivityPage />);

    await waitFor(() =>
      expect(screen.getByTestId("activity-item-1")).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(api.getActivity.mock.calls.length).toBeGreaterThan(1),
    );
  });

  it("leaves the feed alone when the purge deleted nothing", async () => {
    api.getActivity.mockResolvedValue(listResponse([activityItem(1)]));
    renderWithClient(<ActivityPage />);

    await waitFor(() => expect(api.purgeActivity).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.getByTestId("activity-item-1")).toBeInTheDocument(),
    );
    expect(api.getActivity).toHaveBeenCalledTimes(1);
  });

  it("does not render a row twice when new activity shifts the offsets", async () => {
    // Two rows land between the two requests, so a plain offset re-serves
    // id 2 and would otherwise render it in both pages.
    api.getActivity
      .mockResolvedValueOnce({
        items: [activityItem(4), activityItem(3)],
        total: 4,
        skip: 0,
        page: 1,
        limit: 50,
      })
      .mockResolvedValueOnce({
        items: [activityItem(3), activityItem(2)],
        total: 6,
        skip: 2,
        page: 2,
        limit: 50,
      });
    renderWithClient(<ActivityPage />);

    await waitFor(() =>
      expect(screen.getByTestId("activity-item-4")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));

    await waitFor(() =>
      expect(screen.getByTestId("activity-item-2")).toBeInTheDocument(),
    );
    expect(screen.getAllByTestId("activity-item-3")).toHaveLength(1);
  });

  it("offsets the next page past rows added while paging", async () => {
    api.getActivity
      .mockResolvedValueOnce({
        items: [activityItem(4), activityItem(3)],
        total: 4,
        skip: 0,
        page: 1,
        limit: 50,
      })
      .mockResolvedValueOnce({
        items: [activityItem(2)],
        total: 6,
        skip: 2,
        page: 2,
        limit: 50,
      })
      .mockResolvedValueOnce({
        items: [activityItem(1)],
        total: 6,
        skip: 5,
        page: 2,
        limit: 50,
      });
    renderWithClient(<ActivityPage />);

    await waitFor(() =>
      expect(screen.getByTestId("activity-item-4")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await waitFor(() =>
      expect(screen.getByTestId("activity-item-2")).toBeInTheDocument(),
    );

    // Third request skips 3 consumed rows plus the 2 that arrived (total 4 -> 6).
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await waitFor(() =>
      expect(api.getActivity).toHaveBeenLastCalledWith(
        expect.objectContaining({ skip: 5 }),
      ),
    );
  });
});
