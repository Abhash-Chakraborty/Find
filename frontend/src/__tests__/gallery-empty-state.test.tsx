import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockPush, mockReplace, mockSearchParams } = vi.hoisted(() => {
  const searchParams = new URLSearchParams();

  return {
    mockPush: vi.fn(),
    mockReplace: vi.fn(),
    mockSearchParams: searchParams,
  };
});

const apiMocks = vi.hoisted(() => ({
  getGallery: vi.fn(),
  getGalleryCounts: vi.fn(),
  getImageDetail: vi.fn(),
  toggleLike: vi.fn(),
  deleteImage: vi.fn(),
  reprocessImage: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => mockSearchParams,
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
  usePathname: () => "/gallery",
}));

vi.mock("next/image", () => ({
  // biome-ignore lint/performance/noImgElement: test mock only
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) => <a href={href}>{children}</a>,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("@/lib/api", () => ({
  getGallery: apiMocks.getGallery,
  getGalleryCounts: apiMocks.getGalleryCounts,
  getImageDetail: apiMocks.getImageDetail,
  toggleLike: apiMocks.toggleLike,
  deleteImage: apiMocks.deleteImage,
  reprocessImage: apiMocks.reprocessImage,
}));

vi.mock("@/components/image-preview-modal", () => ({
  ImagePreviewModal: () => null,
}));

vi.mock("@/components/status-indicator", () => ({
  StatusIndicator: ({ status }: { status: string }) => (
    <span data-testid="status-indicator">{status}</span>
  ),
}));

import GalleryPage from "../app/gallery/page";

function renderWithQueryClient() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(<GalleryPage />, {
    wrapper: ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  });
}

function resetSearchParams() {
  for (const key of Array.from(mockSearchParams.keys())) {
    mockSearchParams.delete(key);
  }
}

describe("Gallery empty states", () => {
  beforeEach(() => {
    resetSearchParams();
    mockPush.mockReset();
    mockReplace.mockReset();
    apiMocks.getGallery.mockReset();
    apiMocks.getGalleryCounts.mockReset();
    apiMocks.getGalleryCounts.mockResolvedValue({
      all: 0,
      indexed: 0,
      processing: 0,
      failed: 0,
    });
    apiMocks.getImageDetail.mockReset();
    apiMocks.toggleLike.mockReset();
    apiMocks.deleteImage.mockReset();
    apiMocks.reprocessImage.mockReset();
  });

  it("shows the upload link when the gallery is empty", async () => {
    apiMocks.getGallery.mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      limit: 24,
    });

    renderWithQueryClient();

    await waitFor(() => {
      expect(screen.getByText(/no images found/i)).toBeInTheDocument();
    });

    expect(
      screen.getByRole("link", { name: /upload your first images/i }),
    ).toHaveAttribute("href", "/upload");
  });

  it("keeps the active filter when clearing liked-only empty results", async () => {
    mockSearchParams.set("status", "processing");
    mockSearchParams.set("liked", "true");
    apiMocks.getGallery.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      limit: 24,
    });

    renderWithQueryClient();

    await waitFor(() => {
      expect(
        screen.getByText(/no liked images are processing/i),
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /view all images/i }));

    expect(mockPush).toHaveBeenCalledWith("/gallery?status=processing", {
      scroll: false,
    });
  });

  it("requests gallery data with status and liked filters from the URL", async () => {
    mockSearchParams.set("status", "failed");
    mockSearchParams.set("liked", "true");
    apiMocks.getGallery.mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      limit: 24,
    });

    renderWithQueryClient();

    await waitFor(() => {
      expect(apiMocks.getGallery).toHaveBeenCalledWith(
        expect.objectContaining({
          page: 1,
          limit: 24,
          status: "failed",
          liked: true,
        }),
      );
    });
  });
});
