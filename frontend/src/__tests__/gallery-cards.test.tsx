// Tests for Gallery cards in light mode
// Uses Vitest and React Testing Library

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import GalleryPage from "../app/gallery/page";

// Mock next/navigation utilities with original exports preserved
vi.mock("next/navigation", async (importOriginal) => {
  const original = await importOriginal<typeof import("next/navigation")>();
  return {
    ...original,
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
    usePathname: () => "/gallery",
    useSearchParams: () => new URLSearchParams(),
  };
});

vi.mock("@/lib/api");
vi.mock("@/lib/media", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/media")>();
  return {
    ...original,
    resolveMediaUrl: vi.fn((url) => url),
    MINIO_URL_REFRESH_INTERVAL_MS: 0,
    MINIO_URL_STALE_TIME_MS: 0,
  };
});

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });

const renderWithClient = (ui: React.ReactElement) => {
  const client = createQueryClient();
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
};

describe("Gallery card states (light mode)", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    document.documentElement.classList.remove("dark");
  });

  it("renders loading spinner while data is fetching", async () => {
    // Mock getGallery to return a promise that never resolves immediately
    vi.mocked(api.getGallery).mockImplementation(() => new Promise(() => {}));
    renderWithClient(<GalleryPage />);
    // Initial loading now renders an accessible skeleton grid (role=status)
    // rather than a single spinner icon.
    const loader = screen.getByRole("status", { name: /loading gallery/i });
    expect(loader).toBeInTheDocument();
  });

  it("shows error message when query fails", async () => {
    vi.mocked(api.getGallery).mockRejectedValue(new Error("Network error"));
    renderWithClient(<GalleryPage />);
    await waitFor(() => {
      expect(screen.getByText(/Failed to load gallery/i)).toBeInTheDocument();
    });
  });

  it("displays empty state when no items are returned", async () => {
    vi.mocked(api.getGallery).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      limit: 24,
    });
    renderWithClient(<GalleryPage />);
    await waitFor(() => {
      expect(screen.getByText(/No images found/i)).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: /Upload your first images/i }),
      ).toBeInTheDocument();
    });
  });

  const mockItems: api.MediaItem[] = [
    {
      id: 1,
      filename: "image1.jpg",
      url: "http://example.com/image1.jpg",
      minio_key: "key1",
      status: "indexed",
      liked: false,
      caption: "A caption",
      created_at: "2026-05-24T00:00:00Z",
    },
    {
      id: 2,
      filename: "image2.jpg",
      url: "http://example.com/image2.jpg",
      minio_key: "key2",
      status: "failed",
      liked: false,
      caption: undefined,
      created_at: "2026-05-24T00:00:00Z",
    },
    {
      id: 3,
      filename: "image3.jpg",
      url: undefined,
      minio_key: "key3",
      status: "indexed",
      liked: true,
      caption: "Liked image",
      created_at: "2026-05-24T00:00:00Z",
    },
  ];

  it("renders cards with correct UI for normal, liked and failed states", async () => {
    vi.mocked(api.getGallery).mockResolvedValue({
      items: mockItems,
      total: 3,
      page: 1,
      limit: 24,
    });
    renderWithClient(<GalleryPage />);
    // Wait for cards to appear
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /View/i })).toHaveLength(3);
    });
    const indexedLabels = screen.getAllByLabelText("Status: Indexed");
    expect(indexedLabels).toHaveLength(2);
    const [firstIndexedLabel, secondIndexedLabel] = indexedLabels;
    expect(firstIndexedLabel).toBeDefined();
    expect(secondIndexedLabel).toBeDefined();
    if (!firstIndexedLabel || !secondIndexedLabel) {
      throw new Error(
        "Expected indexed status labels for rendered gallery cards",
      );
    }

    // Normal card (id 1) should show image and no filled heart
    const card1Img = screen.getByAltText("image1.jpg");
    expect(card1Img).toBeInTheDocument();
    expect(card1Img.closest("article")).toContainElement(firstIndexedLabel);
    const heartBtn1 = screen.getAllByLabelText("Like image")[0];
    expect(heartBtn1).toBeInTheDocument();

    // Liked card (id 3) should have filled heart
    const unlikeBtns = screen.getAllByLabelText("Unlike image");
    expect(unlikeBtns).toHaveLength(1);
    const [heartBtn3] = unlikeBtns;
    expect(heartBtn3).toBeDefined();
    if (!heartBtn3) {
      throw new Error("Expected unlike button for liked gallery card");
    }
    expect(heartBtn3).toBeInTheDocument();
    expect(heartBtn3.closest("article")).toContainElement(secondIndexedLabel);
    // Failed card (id 2) should show retry button
    const card2Img = screen.getByAltText("image2.jpg");
    expect(card2Img.closest("article")).toContainElement(
      screen.getByLabelText("Status: Failed"),
    );
    const retryBtn = screen.getByLabelText("Retry analysis");
    expect(retryBtn).toBeInTheDocument();
  });

  it("can bulk delete selected gallery cards", async () => {
    vi.mocked(api.getGallery).mockResolvedValue({
      items: mockItems,
      total: 3,
      page: 1,
      limit: 24,
    });
    vi.mocked(api.deleteImagesBulk).mockResolvedValue({
      message: "Bulk delete completed",
      deleted_ids: [1, 2],
      missing_ids: [],
      failed_ids: [],
      deleted_count: 2,
      missing_count: 0,
      failed_count: 0,
    });

    renderWithClient(<GalleryPage />);

    await waitFor(() => {
      expect(screen.getByLabelText("Select image1.jpg")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText("Select image1.jpg"));
    fireEvent.click(screen.getByLabelText("Select image2.jpg"));
    fireEvent.click(screen.getByRole("button", { name: "Delete selected" }));
    const deleteButtons = screen.getAllByRole("button", {
      name: "Delete selected",
    });
    const confirmButton = deleteButtons.at(-1);
    if (!confirmButton) {
      throw new Error("Expected delete confirmation button");
    }
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(api.deleteImagesBulk).toHaveBeenCalledWith([1, 2]);
    });
  });

  it("can archive selected gallery cards", async () => {
    vi.mocked(api.getGallery).mockResolvedValue({
      items: mockItems,
      total: 3,
      page: 1,
      limit: 24,
    });
    vi.mocked(api.setArchive).mockResolvedValue({ id: 1, is_archived: true });

    renderWithClient(<GalleryPage />);

    await waitFor(() => {
      expect(screen.getByLabelText("Select image1.jpg")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText("Select image1.jpg"));
    fireEvent.click(screen.getByLabelText("Select image2.jpg"));
    fireEvent.click(screen.getByRole("button", { name: /archive/i }));

    await waitFor(() => {
      expect(api.setArchive).toHaveBeenCalledWith(1, true);
      expect(api.setArchive).toHaveBeenCalledWith(2, true);
    });
  });

  it("can move selected gallery cards to trash", async () => {
    vi.mocked(api.getGallery).mockResolvedValue({
      items: mockItems,
      total: 3,
      page: 1,
      limit: 24,
    });
    vi.mocked(api.trashImage).mockResolvedValue({
      id: 1,
      deleted_at: "2026-06-29T00:00:00+00:00",
    });

    renderWithClient(<GalleryPage />);

    await waitFor(() => {
      expect(screen.getByLabelText("Select image1.jpg")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText("Select image1.jpg"));
    fireEvent.click(screen.getByRole("button", { name: /move to trash/i }));

    await waitFor(() => {
      expect(api.trashImage).toHaveBeenCalledWith(1);
    });
  });
});
