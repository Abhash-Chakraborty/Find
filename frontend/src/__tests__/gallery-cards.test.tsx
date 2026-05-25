// Tests for Gallery cards in light mode
// Uses Vitest and React Testing Library

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/api";
import GalleryPage from "../app/gallery/page";

// Mock next/navigation utilities with original exports preserved
vi.mock("next/navigation", async (importOriginal) => {
  const original = await importOriginal();
  return {
    ...original,
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
    usePathname: () => "/gallery",
    useSearchParams: () => new URLSearchParams(),
  };
});

vi.mock("@/lib/api");
vi.mock("@/lib/media", async (importOriginal) => {
  const original = await importOriginal();
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
    // The loading spinner is an SVG with class containing 'loader-circle'
    const loader = document.querySelector(".lucide-loader-circle");
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
    vi.mocked(api.getGallery).mockResolvedValue({ items: [], total: 0 });
    renderWithClient(<GalleryPage />);
    await waitFor(() => {
      expect(screen.getByText(/No images found/i)).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: /Upload your first images/i }),
      ).toBeInTheDocument();
    });
  });

  const mockItems = [
    {
      id: 1,
      filename: "image1.jpg",
      url: "http://example.com/image1.jpg",
      minio_key: "key1",
      status: "indexed",
      liked: false,
      caption: "A caption",
    },
    {
      id: 2,
      filename: "image2.jpg",
      url: "http://example.com/image2.jpg",
      minio_key: "key2",
      status: "failed",
      liked: false,
      caption: null,
    },
    {
      id: 3,
      filename: "image3.jpg",
      url: null,
      minio_key: null,
      status: "indexed",
      liked: true,
      caption: "Liked image",
    },
  ];

  it("renders cards with correct UI for normal, liked and failed states", async () => {
    vi.mocked(api.getGallery).mockResolvedValue({ items: mockItems, total: 3 });
    renderWithClient(<GalleryPage />);
    // Wait for cards to appear
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /View/i })).toHaveLength(3);
    });
    // Normal card (id 1) should show image and no filled heart
    const card1Img = screen.getByAltText("image1.jpg");
    expect(card1Img).toBeInTheDocument();
    expect(card1Img.closest("article")).toContainElement(
      screen.getAllByLabelText("Status: Indexed")[0],
    );
    const heartBtn1 = screen.getAllByLabelText("Like image")[0];
    expect(heartBtn1).toBeInTheDocument();
    // Liked card (id 3) should have filled heart
    const heartBtn3 = screen.getAllByLabelText("Unlike image")[0];
    expect(heartBtn3).toBeInTheDocument();
    expect(heartBtn3.closest("article")).toContainElement(
      screen.getAllByLabelText("Status: Indexed")[1],
    );
    // Failed card (id 2) should show retry button
    const card2Img = screen.getByAltText("image2.jpg");
    expect(card2Img.closest("article")).toContainElement(
      screen.getByLabelText("Status: Failed"),
    );
    const retryBtn = screen.getByLabelText("Retry analysis");
    expect(retryBtn).toBeInTheDocument();
  });
});
