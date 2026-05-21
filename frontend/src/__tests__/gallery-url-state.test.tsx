/**
 * Tests: gallery URL-state restoration
 * File: frontend/src/__tests__/gallery-url-state.test.tsx
 *
 * Covers issue #93 acceptance criteria:
 *   1. Status tab state is restored from the URL
 *   2. Liked-only filter state is restored from the URL
 *   3. Media deep-link (?media=<id>) still works with filter params
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ---------------------------------------------------------------------------
// Mock next/navigation
// ---------------------------------------------------------------------------
const mockSearchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useSearchParams: () => mockSearchParams,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/gallery",
}));

// ---------------------------------------------------------------------------
// Mock next/image
// ---------------------------------------------------------------------------
vi.mock("next/image", () => ({
  // biome-ignore lint/performance/noImgElement: test mock only
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

// ---------------------------------------------------------------------------
// Mock next/link
// ---------------------------------------------------------------------------
vi.mock("next/link", () => ({
  default: ({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) => <a href={href}>{children}</a>,
}));

// ---------------------------------------------------------------------------
// Mock sonner
// ---------------------------------------------------------------------------
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// ---------------------------------------------------------------------------
// Mock API layer
// ---------------------------------------------------------------------------
const MOCK_ITEMS = [
  {
    id: 1,
    filename: "sunset.jpg",
    status: "indexed",
    liked: false,
    url: "/images/1.jpg",
    minio_key: null,
    caption: "A sunset",
  },
  {
    id: 2,
    filename: "mountain.jpg",
    status: "processing",
    liked: false,
    url: "/images/2.jpg",
    minio_key: null,
    caption: null,
  },
  {
    id: 3,
    filename: "beach.jpg",
    status: "failed",
    liked: false,
    url: "/images/3.jpg",
    minio_key: null,
    caption: null,
  },
  {
    id: 4,
    filename: "forest.jpg",
    status: "indexed",
    liked: true,
    url: "/images/4.jpg",
    minio_key: null,
    caption: "A forest",
  },
];

type GalleryQuery = {
  page?: number;
  limit?: number;
  status?: string;
  liked?: boolean;
};

vi.mock("@/lib/api", () => ({
  getGallery: vi.fn((query?: GalleryQuery) => {
    const filteredItems = MOCK_ITEMS.filter((item) => {
      if (query?.status && item.status !== query.status) {
        return false;
      }
      if (query?.liked && !item.liked) {
        return false;
      }
      return true;
    });

    return Promise.resolve({
      items: filteredItems,
      total: filteredItems.length,
      page: query?.page ?? 1,
      limit: query?.limit ?? 24,
    });
  }),
  getImageDetail: vi.fn((id: number) => {
    const item = MOCK_ITEMS.find((i) => i.id === id);
    if (!item) return Promise.reject(new Error("Not found"));
    return Promise.resolve(item);
  }),
  toggleLike: vi.fn((id: number) => Promise.resolve({ id })),
  deleteImage: vi.fn((id: number) => Promise.resolve({ id })),
  reprocessImage: vi.fn((id: number) => Promise.resolve({ media_id: id })),
}));

vi.mock("@/lib/media", () => ({
  resolveMediaUrl: vi.fn(() => "/images/mock.jpg"),
}));

// ---------------------------------------------------------------------------
// Mock child components not under test
// ---------------------------------------------------------------------------
vi.mock("@/components/image-preview-modal", () => ({
  ImagePreviewModal: ({ media }: { media: { filename: string } }) => (
    <div role="dialog" aria-label="image preview">
      <span data-testid="modal-filename">{media.filename}</span>
    </div>
  ),
}));

vi.mock("@/components/status-indicator", () => ({
  StatusIndicator: ({ status }: { status: string }) => (
    <span data-testid="status-indicator">{status}</span>
  ),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

function setParams(params: Record<string, string>) {
  for (const k of Array.from(mockSearchParams.keys())) {
    mockSearchParams.delete(k);
  }
  for (const [k, v] of Object.entries(params)) {
    mockSearchParams.set(k, v);
  }
}

function clearParams() {
  for (const k of Array.from(mockSearchParams.keys())) {
    mockSearchParams.delete(k);
  }
}

// ---------------------------------------------------------------------------
// Import component under test
// ---------------------------------------------------------------------------
import GalleryPage from "../app/gallery/page";

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Gallery — URL-state restoration", () => {
  beforeEach(() => {
    clearParams();
    vi.clearAllMocks();
  });

  afterEach(() => {
    clearParams();
  });

  // ── 1. Status tab UI ─────────────────────────────────────────────────────

  describe("status tab UI", () => {
    it("renders all four filter tab links", async () => {
      render(<GalleryPage />, { wrapper: makeWrapper() });

      await waitFor(() => {
        expect(
          screen.getByRole("link", { name: /^all$/i }),
        ).toBeInTheDocument();
        expect(
          screen.getByRole("link", { name: /^indexed$/i }),
        ).toBeInTheDocument();
        expect(
          screen.getByRole("link", { name: /^processing$/i }),
        ).toBeInTheDocument();
        expect(
          screen.getByRole("link", { name: /^failed$/i }),
        ).toBeInTheDocument();
      });
    });

    it("shows all gallery items on initial load", async () => {
      render(<GalleryPage />, { wrapper: makeWrapper() });

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /view sunset\.jpg/i }),
        ).toBeInTheDocument();
        expect(
          screen.getByRole("button", { name: /view mountain\.jpg/i }),
        ).toBeInTheDocument();
        expect(
          screen.getByRole("button", { name: /view beach\.jpg/i }),
        ).toBeInTheDocument();
        expect(
          screen.getByRole("button", { name: /view forest\.jpg/i }),
        ).toBeInTheDocument();
      });
    });

    it("calls getGallery on mount", async () => {
      const { getGallery } = await import("@/lib/api");
      render(<GalleryPage />, { wrapper: makeWrapper() });

      await waitFor(() => {
        expect(getGallery).toHaveBeenCalled();
      });
    });

    it("restores Processing tab from ?status=processing and calls getGallery with status:processing", async () => {
      const { getGallery } = await import("@/lib/api");
      setParams({ status: "processing" });

      render(<GalleryPage />, { wrapper: makeWrapper() });

      await waitFor(() => {
        expect(getGallery).toHaveBeenCalledWith(
          expect.objectContaining({ status: "processing" }),
        );
        expect(
          screen.getByRole("button", { name: /view mountain\.jpg/i }),
        ).toBeInTheDocument();
      });

      expect(
        screen.queryByRole("button", { name: /view sunset\.jpg/i }),
      ).not.toBeInTheDocument();
    });

    it("restores Failed tab from ?status=failed and calls getGallery with status:failed", async () => {
      const { getGallery } = await import("@/lib/api");
      setParams({ status: "failed" });

      render(<GalleryPage />, { wrapper: makeWrapper() });

      await waitFor(() => {
        expect(getGallery).toHaveBeenCalledWith(
          expect.objectContaining({ status: "failed" }),
        );
        expect(
          screen.getByRole("button", { name: /view beach\.jpg/i }),
        ).toBeInTheDocument();
      });

      expect(
        screen.queryByRole("button", { name: /view sunset\.jpg/i }),
      ).not.toBeInTheDocument();
    });

    it("restores Indexed tab from ?status=indexed and calls getGallery with status:indexed", async () => {
      const { getGallery } = await import("@/lib/api");
      setParams({ status: "indexed" });

      render(<GalleryPage />, { wrapper: makeWrapper() });

      await waitFor(() => {
        expect(getGallery).toHaveBeenCalledWith(
          expect.objectContaining({ status: "indexed" }),
        );
        expect(
          screen.getByRole("button", { name: /view sunset\.jpg/i }),
        ).toBeInTheDocument();
        expect(
          screen.getByRole("button", { name: /view forest\.jpg/i }),
        ).toBeInTheDocument();
      });

      expect(
        screen.queryByRole("button", { name: /view mountain\.jpg/i }),
      ).not.toBeInTheDocument();
    });
  });

  // ── 2. Liked-only filter UI ───────────────────────────────────────────────

  describe("liked-only filter UI", () => {
    it("renders the liked toggle button showing 'All images' by default", async () => {
      render(<GalleryPage />, { wrapper: makeWrapper() });

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /all images/i }),
        ).toBeInTheDocument();
      });
    });

    it("shows all images on initial load", async () => {
      render(<GalleryPage />, { wrapper: makeWrapper() });

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /view sunset\.jpg/i }),
        ).toBeInTheDocument();
        expect(
          screen.getByRole("button", { name: /view forest\.jpg/i }),
        ).toBeInTheDocument();
      });
    });

    it("restores liked-only mode from ?liked=true and calls getGallery with liked:true", async () => {
      const { getGallery } = await import("@/lib/api");
      setParams({ liked: "true" });

      render(<GalleryPage />, { wrapper: makeWrapper() });

      await waitFor(() => {
        expect(getGallery).toHaveBeenCalledWith(
          expect.objectContaining({ liked: true }),
        );
      });
    });

    it("shows 'Liked' button text when ?liked=true is in the URL", async () => {
      setParams({ liked: "true" });

      render(<GalleryPage />, { wrapper: makeWrapper() });

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /^liked$/i }),
        ).toBeInTheDocument();
      });
    });

    it("shows only liked items in gallery when ?liked=true is in the URL", async () => {
      setParams({ liked: "true" });

      render(<GalleryPage />, { wrapper: makeWrapper() });

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /view forest\.jpg/i }),
        ).toBeInTheDocument();
      });

      expect(
        screen.queryByRole("button", { name: /view sunset\.jpg/i }),
      ).not.toBeInTheDocument();
    });
  });

  // ── 3. Media deep-link (?media=) — already implemented in page.tsx ────────

  describe("media deep-link with filter params", () => {
    it("opens image preview modal when ?media=1 is in the URL", async () => {
      setParams({ media: "1" });

      render(<GalleryPage />, { wrapper: makeWrapper() });

      await waitFor(() => {
        expect(screen.getByRole("dialog")).toBeInTheDocument();
        expect(screen.getByTestId("modal-filename")).toHaveTextContent(
          "sunset.jpg",
        );
      });
    });

    it("opens modal for item id=4 when ?media=4", async () => {
      setParams({ media: "4" });

      render(<GalleryPage />, { wrapper: makeWrapper() });

      await waitFor(() => {
        expect(screen.getByRole("dialog")).toBeInTheDocument();
        expect(screen.getByTestId("modal-filename")).toHaveTextContent(
          "forest.jpg",
        );
      });
    });

    it("does not open modal when ?media param is absent", async () => {
      render(<GalleryPage />, { wrapper: makeWrapper() });

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /view sunset\.jpg/i }),
        ).toBeInTheDocument();
      });

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("fetches image detail for off-page ?media id not in gallery results", async () => {
      const { getGallery, getImageDetail } = await import("@/lib/api");

      // Return only item 1 from gallery so item 2 is "off page"
      (getGallery as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        items: [MOCK_ITEMS[0]],
        total: 1,
        page: 1,
        limit: 24,
      });

      setParams({ media: "2" });

      render(<GalleryPage />, { wrapper: makeWrapper() });

      await waitFor(() => {
        expect(getImageDetail).toHaveBeenCalledWith(2);
      });
    });

    it("handles non-existent ?media id gracefully without crashing", async () => {
      setParams({ media: "9999" });

      render(<GalleryPage />, { wrapper: makeWrapper() });

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /view sunset\.jpg/i }),
        ).toBeInTheDocument();
      });

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("handles non-numeric ?media value gracefully without crashing", async () => {
      setParams({ media: "not-a-number" });

      render(<GalleryPage />, { wrapper: makeWrapper() });

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /view sunset\.jpg/i }),
        ).toBeInTheDocument();
      });

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("media deep-link still works when combined with ?status and ?liked filter params", async () => {
      const { getGallery } = await import("@/lib/api");
      setParams({ media: "4", status: "indexed", liked: "true" });

      render(<GalleryPage />, { wrapper: makeWrapper() });

      await waitFor(() => {
        expect(getGallery).toHaveBeenCalledWith(
          expect.objectContaining({ status: "indexed", liked: true }),
        );
        expect(screen.getByRole("dialog")).toBeInTheDocument();
        expect(screen.getByTestId("modal-filename")).toHaveTextContent(
          "forest.jpg",
        );
      });
    });
  });
});
