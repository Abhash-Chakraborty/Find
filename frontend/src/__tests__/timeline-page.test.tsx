/**
 * Integration test for the timeline page — verifies the data hook, grid,
 * scrubber, and viewer are wired together against a mocked timeline API.
 *
 * Run with: pnpm vitest run src/__tests__/timeline-page.test.tsx
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
import TimelinePage from "../app/timeline/page";

const navigation = vi.hoisted(() => ({
  useSearchParams: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: navigation.useSearchParams,
}));

const api = vi.hoisted(() => ({
  getTimelineBuckets: vi.fn(),
  getTimelineBucket: vi.fn(),
  getImageDetail: vi.fn(),
  toggleLike: vi.fn(),
  setArchive: vi.fn(),
  trashImage: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getTimelineBuckets: api.getTimelineBuckets,
  getTimelineBucket: api.getTimelineBucket,
  getImageDetail: api.getImageDetail,
  toggleLike: api.toggleLike,
  setArchive: api.setArchive,
  trashImage: api.trashImage,
}));

// jsdom lacks layout + ResizeObserver; provide a fixed-width observer so the
// justified grid produces boxes.
class FakeResizeObserver {
  cb: ResizeObserverCallback;
  constructor(cb: ResizeObserverCallback) {
    this.cb = cb;
  }
  observe(target: Element) {
    this.cb(
      [
        {
          target,
          contentRect: { width: 1000, height: 0 } as DOMRectReadOnly,
        } as ResizeObserverEntry,
      ],
      this as unknown as ResizeObserver,
    );
  }
  unobserve() {}
  disconnect() {}
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <TimelinePage />
    </QueryClientProvider>,
  );
  return {
    ...view,
    rerenderPage: () =>
      view.rerender(
        <QueryClientProvider client={client}>
          <TimelinePage />
        </QueryClientProvider>,
      ),
  };
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.stubGlobal("innerHeight", 5000);
  api.getTimelineBuckets.mockReset();
  api.getTimelineBucket.mockReset();
  api.getImageDetail.mockReset();
  api.toggleLike.mockReset();
  api.setArchive.mockReset();
  api.trashImage.mockReset();
  navigation.useSearchParams.mockImplementation(
    () => new URLSearchParams(window.location.search),
  );
  api.getImageDetail.mockResolvedValue({
    id: 101,
    filename: "photo.jpg",
    minio_key: "images/photo.jpg",
    file_hash: "hash",
    status: "indexed",
    created_at: "2026-03-01T00:00:00+00:00",
    url: "/api/image/101/original",
    liked: false,
    metadata: {},
    exif: {},
  });
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/timeline");
  vi.unstubAllGlobals();
});

describe("TimelinePage", () => {
  it("shows the empty state when there are no photos", async () => {
    api.getTimelineBuckets.mockResolvedValue({ buckets: [], total: 0 });
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("timeline-empty")).toBeInTheDocument(),
    );
  });

  it("shows an error state when the bucket fetch fails", async () => {
    api.getTimelineBuckets.mockRejectedValue(new Error("boom"));
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("timeline-error")).toBeInTheDocument(),
    );
    // The empty state must not also render on error.
    expect(screen.queryByTestId("timeline-empty")).toBeNull();
  });

  it("loads the first bucket and renders its assets as grid cells", async () => {
    api.getTimelineBuckets.mockResolvedValue({
      buckets: [{ timeBucket: "2026-03-01", count: 2 }],
      total: 2,
    });
    api.getTimelineBucket.mockResolvedValue({
      timeBucket: "2026-03-01",
      count: 2,
      id: [101, 102],
      ratio: [1.5, 1.0],
      thumbhash: [null, null],
      liked: [false, false],
      createdAt: ["2026-03-01T00:00:00+00:00", "2026-03-02T00:00:00+00:00"],
      thumbnailUrl: ["/api/image/101/thumbnail", "/api/image/102/thumbnail"],
    });

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("timeline-cell-101")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("timeline-cell-102")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-total")).toHaveTextContent("2 photos");
    // The first bucket was auto-loaded.
    expect(api.getTimelineBucket).toHaveBeenCalledWith(
      expect.objectContaining({ timeBucket: "2026-03-01" }),
    );
  });

  it("opens the asset viewer when a cell is clicked", async () => {
    api.getTimelineBuckets.mockResolvedValue({
      buckets: [{ timeBucket: "2026-03-01", count: 1 }],
      total: 1,
    });
    api.getTimelineBucket.mockResolvedValue({
      timeBucket: "2026-03-01",
      count: 1,
      id: [101],
      ratio: [1.5],
      thumbhash: [null],
      liked: [false],
      createdAt: ["2026-03-01T00:00:00+00:00"],
      thumbnailUrl: ["/api/image/101/thumbnail"],
    });

    // Image() preloads inside the viewer.
    vi.stubGlobal(
      "Image",
      class {
        onload: (() => void) | null = null;
        set src(_v: string) {}
      },
    );

    renderPage();

    const cell = await screen.findByTestId("timeline-cell-101");
    fireEvent.click(cell);

    await waitFor(() =>
      expect(screen.getByTestId("image-preview-modal")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("image-preview-modal")).toHaveClass(
      "h-dvh",
      "w-full",
    );
    const detailsToggle = screen.getByTestId("preview-details-toggle");
    expect(detailsToggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(detailsToggle);
    expect(detailsToggle).toHaveAttribute("aria-expanded", "true");
  });

  it("loads Favorites only from its dedicated sidebar route", async () => {
    api.getTimelineBuckets.mockResolvedValue({
      buckets: [{ timeBucket: "2026-03-01", count: 1 }],
      total: 1,
    });
    api.getTimelineBucket.mockResolvedValue({
      timeBucket: "2026-03-01",
      count: 1,
      id: [101],
      ratio: [1.5],
      thumbhash: [null],
      liked: [true],
      createdAt: ["2026-03-01T00:00:00+00:00"],
      thumbnailUrl: ["/api/image/101/thumbnail"],
    });

    window.history.replaceState(null, "", "/timeline?liked=true");
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Favorites" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("timeline-favorites-toggle")).toBeNull();
    await waitFor(() =>
      expect(api.getTimelineBuckets).toHaveBeenCalledWith(
        expect.objectContaining({ liked: true }),
      ),
    );
  });

  it("reacts when same-route navigation toggles the Favorites query", async () => {
    api.getTimelineBuckets.mockResolvedValue({ buckets: [], total: 0 });
    const view = renderPage();
    expect(
      await screen.findByRole("heading", { name: "Photos" }),
    ).toBeInTheDocument();

    window.history.replaceState(null, "", "/timeline?liked=true");
    view.rerenderPage();

    expect(
      await screen.findByRole("heading", { name: "Favorites" }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(api.getTimelineBuckets).toHaveBeenCalledWith(
        expect.objectContaining({ liked: true }),
      ),
    );
  });

  it("toggles favorite from the timeline viewer", async () => {
    api.getTimelineBuckets.mockResolvedValue({
      buckets: [{ timeBucket: "2026-03-01", count: 1 }],
      total: 1,
    });
    api.getTimelineBucket.mockResolvedValue({
      timeBucket: "2026-03-01",
      count: 1,
      id: [101],
      ratio: [1.5],
      thumbhash: [null],
      liked: [false],
      createdAt: ["2026-03-01T00:00:00+00:00"],
      thumbnailUrl: ["/api/image/101/thumbnail"],
    });
    api.toggleLike.mockResolvedValue({ id: 101, liked: true });
    vi.stubGlobal(
      "Image",
      class {
        onload: (() => void) | null = null;
        set src(_v: string) {}
      },
    );

    renderPage();

    const cell = await screen.findByTestId("timeline-cell-101");
    fireEvent.click(cell);

    const fav = await screen.findByRole("button", { name: "Like image" });
    fireEvent.click(fav);

    await waitFor(() => expect(api.toggleLike).toHaveBeenCalledWith(101));
  });
});
