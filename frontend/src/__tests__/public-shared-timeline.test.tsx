import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PublicSharedAlbumPage from "../app/public/shared/[key]/page";

const api = vi.hoisted(() => ({
  getPublicSharedAlbum: vi.fn(),
}));

const preloadedUrls: string[] = [];

class FakeResizeObserver {
  constructor(private callback: ResizeObserverCallback) {}

  observe(target: Element) {
    this.callback(
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

vi.mock("@/lib/api", () => api);
vi.mock("next/navigation", () => ({
  useParams: () => ({ key: "safe-share" }),
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PublicSharedAlbumPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.getPublicSharedAlbum.mockReset();
  preloadedUrls.length = 0;
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.stubGlobal("innerHeight", 5000);
  vi.stubGlobal(
    "Image",
    class {
      onload: (() => void) | null = null;
      set src(value: string) {
        preloadedUrls.push(value);
      }
    },
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PublicSharedAlbumPage timeline", () => {
  it("opens the viewer using only share-scoped URLs", async () => {
    api.getPublicSharedAlbum.mockResolvedValue({
      album: { id: 1, name: "Shared", description: null },
      allow_download: true,
      show_exif: false,
      total: 1,
      items: [
        {
          id: 9,
          filename: "safe.jpg",
          width: 1200,
          height: 800,
          created_at: "2026-03-01T00:00:00Z",
          thumbnail_url: "/api/public/shared/safe-share/asset/9/thumbnail",
          url: "/api/public/shared/safe-share/asset/9/original",
        },
      ],
    });

    renderPage();
    fireEvent.click(await screen.findByTestId("open-shared-asset-9"));

    expect(screen.getByTestId("viewer-image")).toHaveAttribute(
      "src",
      "http://localhost:8000/api/public/shared/safe-share/asset/9/thumbnail",
    );
    await waitFor(() =>
      expect(preloadedUrls).toContain(
        "http://localhost:8000/api/public/shared/safe-share/asset/9/original",
      ),
    );
    expect(preloadedUrls.some((url) => url.includes("/api/image/"))).toBe(
      false,
    );
    expect(api.getPublicSharedAlbum).toHaveBeenCalledWith({
      key: "safe-share",
      password: undefined,
    });
  });

  it("uses the share thumbnail as the view-only original fallback", async () => {
    api.getPublicSharedAlbum.mockResolvedValue({
      album: { id: 1, name: "View only", description: null },
      allow_download: false,
      show_exif: false,
      total: 1,
      items: [
        {
          id: 10,
          filename: "view-only.jpg",
          width: 800,
          height: 800,
          created_at: null,
          thumbnail_url: "/api/public/shared/safe-share/asset/10/thumbnail",
          url: null,
        },
      ],
    });

    renderPage();
    fireEvent.click(await screen.findByTestId("open-shared-asset-10"));

    await waitFor(() => expect(preloadedUrls.length).toBeGreaterThan(0));
    expect(
      preloadedUrls.every(
        (url) =>
          url ===
          "http://localhost:8000/api/public/shared/safe-share/asset/10/thumbnail",
      ),
    ).toBe(true);
  });
});
