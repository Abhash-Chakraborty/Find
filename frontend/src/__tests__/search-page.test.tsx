import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  searchImages: vi.fn(),
  submitSearchRating: vi.fn(),
}));

vi.mock("next/image", () => ({
  // biome-ignore lint/performance/noImgElement: test mock only
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

vi.mock("@/lib/api", () => ({
  searchImages: apiMocks.searchImages,
  submitSearchRating: apiMocks.submitSearchRating,
}));

vi.mock("@/components/feedback-rating", () => ({
  FeedbackRating: ({ label }: { label: string }) => (
    <div data-testid="feedback-rating">{label}</div>
  ),
}));

vi.mock("@/components/image-preview-modal", () => ({
  ImagePreviewModal: ({ media }: { media: { filename?: string } }) => (
    <div role="dialog" aria-label="preview">
      <span data-testid="preview-filename">{media.filename}</span>
    </div>
  ),
}));

vi.mock("@/components/status-indicator", () => ({
  StatusIndicator: ({ status }: { status: string }) => (
    <span data-testid="status-indicator">{status}</span>
  ),
}));

import SearchPage from "../app/search/page";

const QUERY_RESULTS = [
  {
    media_id: 101,
    similarity: 0.934,
    metadata: {
      id: 101,
      filename: "sunset.jpg",
      status: "indexed",
      url: "/images/sunset.jpg",
      minio_key: null,
      caption: "Sunset over water",
    },
  },
  {
    media_id: 102,
    similarity: 0.821,
    metadata: {
      id: 102,
      filename: "mountain.jpg",
      status: "processing",
      url: "/images/mountain.jpg",
      minio_key: null,
      caption: "Mountain ridge at dusk",
    },
  },
];

function renderWithQueryClient() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(<SearchPage />, {
    wrapper: ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  });
}

describe("Search page", () => {
  beforeEach(() => {
    apiMocks.searchImages.mockReset();
    apiMocks.submitSearchRating.mockReset();
  });

  it("renders search results after submit and opens the preview modal", async () => {
    apiMocks.searchImages.mockResolvedValueOnce({
      results: QUERY_RESULTS,
      total: QUERY_RESULTS.length,
      query: "sunset",
      page: 1,
      limit: 24,
      skip: 0,
      has_more: false,
    });

    renderWithQueryClient();

    fireEvent.change(
      screen.getByPlaceholderText(/a visual memory, object, scene, or mood/i),
      { target: { value: "sunset" } },
    );
    fireEvent.click(screen.getByRole("button", { name: /^search$/i }));

    await waitFor(() => {
      expect(apiMocks.searchImages).toHaveBeenCalledWith({
        query: "sunset",
        limit: 24,
        skip: 0,
      });
    });

    await waitFor(() => {
      expect(
        screen.getByText((_, element) => {
          return (
            element?.tagName.toLowerCase() === "p" &&
            element.textContent === "2 results for sunset"
          );
        }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /preview sunset\.jpg/i }),
      ).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("button", { name: /preview sunset\.jpg/i }),
    );

    expect(
      await screen.findByRole("dialog", { name: /preview/i }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("preview-filename")).toHaveTextContent(
      "sunset.jpg",
    );
  });

  it("shows the empty search state when no matches are returned", async () => {
    apiMocks.searchImages.mockResolvedValueOnce({
      results: [],
      total: 0,
      query: "nothing",
      page: 1,
      limit: 24,
      skip: 0,
      has_more: false,
    });

    renderWithQueryClient();

    fireEvent.change(
      screen.getByPlaceholderText(/a visual memory, object, scene, or mood/i),
      { target: { value: "nothing" } },
    );
    fireEvent.click(screen.getByRole("button", { name: /^search$/i }));

    await waitFor(() => {
      expect(screen.getByText(/no results found/i)).toBeInTheDocument();
      expect(
        screen.getByText(/try a broader phrase or a visible object/i),
      ).toBeInTheDocument();
    });
  });
});
