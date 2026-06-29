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

const api = vi.hoisted(() => ({
  getTimelineBuckets: vi.fn(),
  getTimelineBucket: vi.fn(),
  toggleLike: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getTimelineBuckets: api.getTimelineBuckets,
  getTimelineBucket: api.getTimelineBucket,
  toggleLike: api.toggleLike,
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
  return render(
    <QueryClientProvider client={client}>
      <TimelinePage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.stubGlobal("innerHeight", 5000);
  api.getTimelineBuckets.mockReset();
  api.getTimelineBucket.mockReset();
  api.toggleLike.mockReset();
});

afterEach(() => {
  cleanup();
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
      expect(screen.getByTestId("asset-viewer")).toBeInTheDocument(),
    );
  });

  it("refetches buckets with liked=true when favorites is toggled", async () => {
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

    renderPage();

    const toggle = await screen.findByTestId("timeline-favorites-toggle");
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute("aria-pressed", "true");
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

    const fav = await screen.findByTestId("viewer-favorite");
    fireEvent.click(fav);

    await waitFor(() => expect(api.toggleLike).toHaveBeenCalledWith(101));
  });
});
