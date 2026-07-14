/**
 * Component test for the album detail page's viewer wiring — clicking an
 * album photo opens the AssetViewer over the album's assets.
 *
 * Run with: pnpm vitest run src/__tests__/album-detail-viewer.test.tsx
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
import AlbumDetailPage from "../app/albums/[id]/page";

const api = vi.hoisted(() => ({
  getAlbum: vi.fn(),
  getAlbumAssets: vi.fn(),
  removeAlbumAssets: vi.fn(),
  updateAlbum: vi.fn(),
  deleteAlbum: vi.fn(),
  toggleLike: vi.fn(),
  setArchive: vi.fn(),
  trashImage: vi.fn(),
  getSharedLinks: vi.fn(),
  createSharedLink: vi.fn(),
  deleteSharedLink: vi.fn(),
  getImageDetail: vi.fn(),
  deleteImage: vi.fn(),
  reprocessImage: vi.fn(),
  submitCaptionCorrection: vi.fn(),
  submitObjectCorrection: vi.fn(),
}));

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
vi.mock("@/lib/media", () => ({
  resolveMediaUrl: (u: string) => u,
  MINIO_URL_STALE_TIME_MS: 60_000,
  MINIO_URL_REFRESH_INTERVAL_MS: 60_000,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "1" }),
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock("next/link", () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <span>{children}</span>
  ),
}));

const item = (id: number) => ({
  id,
  filename: `img-${id}.jpg`,
  minio_key: `images/test/${id}.jpg`,
  status: "indexed" as const,
  created_at: "2026-03-01T00:00:00+00:00",
  thumbnail_url: `/api/image/${id}/thumbnail`,
});

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AlbumDetailPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset();
  api.getAlbum.mockResolvedValue({
    id: 1,
    name: "Trip",
    description: null,
    cover_media_id: null,
    cover_thumbnail_url: null,
    asset_count: 2,
    created_at: null,
    updated_at: null,
  });
  api.getAlbumAssets.mockResolvedValue({
    items: [item(10), item(11)],
    total: 2,
  });
  api.getSharedLinks.mockResolvedValue({ shared_links: [], total: 0 });
  api.getImageDetail.mockImplementation(async (id: number) => ({
    ...item(id),
    file_hash: `hash-${id}`,
    url: `/api/image/${id}/original`,
    metadata: {},
    exif: {},
  }));
  vi.stubGlobal("ResizeObserver", FakeResizeObserver);
  vi.stubGlobal("innerHeight", 5000);
  vi.stubGlobal(
    "Image",
    class {
      onload: (() => void) | null = null;
      set src(_v: string) {}
    },
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AlbumDetailPage viewer", () => {
  it("opens the metadata preview when an album photo is clicked", async () => {
    renderPage();

    const tile = await screen.findByTestId("open-asset-10");
    fireEvent.click(tile);

    await waitFor(() =>
      expect(screen.getByTestId("image-preview-modal")).toBeInTheDocument(),
    );
    expect(api.getImageDetail).toHaveBeenCalledWith(10);
  });

  it("does not show the viewer until a photo is clicked", async () => {
    renderPage();
    await screen.findByTestId("open-asset-10");
    expect(screen.queryByTestId("image-preview-modal")).toBeNull();
  });

  it("archives the viewed asset and closes the viewer", async () => {
    api.setArchive.mockResolvedValue({ id: 10, is_archived: true });
    renderPage();

    fireEvent.click(await screen.findByTestId("open-asset-10"));
    await screen.findByTestId("image-preview-modal");
    fireEvent.click(screen.getByTestId("preview-archive"));

    await waitFor(() => expect(api.setArchive).toHaveBeenCalledWith(10, true));
    await waitFor(() =>
      expect(screen.queryByTestId("image-preview-modal")).toBeNull(),
    );
  });

  it("moves the viewed asset to trash and closes the viewer", async () => {
    api.trashImage.mockResolvedValue({
      id: 10,
      deleted_at: "2026-06-29T00:00:00+00:00",
    });
    renderPage();

    fireEvent.click(await screen.findByTestId("open-asset-10"));
    await screen.findByTestId("image-preview-modal");
    fireEvent.click(screen.getByTestId("preview-trash"));

    await waitFor(() => expect(api.trashImage).toHaveBeenCalledWith(10));
  });
});
