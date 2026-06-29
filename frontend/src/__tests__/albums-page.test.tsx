/**
 * Component tests for the Albums list page (frontend for Phase 4.2 backend).
 *
 * Run with: pnpm vitest run src/__tests__/albums-page.test.tsx
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
import AlbumsPage from "../app/albums/page";

const api = vi.hoisted(() => ({
  getAlbums: vi.fn(),
  createAlbum: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getAlbums: api.getAlbums,
  createAlbum: api.createAlbum,
}));

vi.mock("@/lib/media", () => ({
  resolveMediaUrl: (u: string) => u,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...rest
  }: {
    children: React.ReactNode;
    href: string;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AlbumsPage />
    </QueryClientProvider>,
  );
}

const album = (id: number, name: string, assetCount = 0) => ({
  id,
  name,
  description: null,
  cover_media_id: null,
  cover_thumbnail_url: null,
  asset_count: assetCount,
  created_at: null,
  updated_at: null,
});

beforeEach(() => {
  api.getAlbums.mockReset();
  api.createAlbum.mockReset();
});

afterEach(() => cleanup());

describe("AlbumsPage", () => {
  it("shows the empty state when there are no albums", async () => {
    api.getAlbums.mockResolvedValue({ albums: [], total: 0 });
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("albums-empty")).toBeInTheDocument(),
    );
  });

  it("shows an error state when album loading fails", async () => {
    api.getAlbums.mockRejectedValue(new Error("boom"));
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("albums-error")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("albums-empty")).toBeNull();
  });

  it("lists albums with their photo counts", async () => {
    api.getAlbums.mockResolvedValue({
      albums: [album(1, "Trip", 3), album(2, "Pets", 1)],
      total: 2,
    });
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("album-card-1")).toBeInTheDocument(),
    );
    expect(screen.getByText("Trip")).toBeInTheDocument();
    expect(screen.getByText("3 photos")).toBeInTheDocument();
    expect(screen.getByText("1 photo")).toBeInTheDocument();
  });

  it("creates an album and refreshes the list", async () => {
    api.getAlbums.mockResolvedValue({ albums: [], total: 0 });
    api.createAlbum.mockResolvedValue(album(5, "New One"));
    renderPage();

    const input = screen.getByLabelText("New album name");
    fireEvent.change(input, { target: { value: "New One" } });
    fireEvent.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() =>
      expect(api.createAlbum).toHaveBeenCalledWith({ name: "New One" }),
    );
  });

  it("does not create an album with a blank name", async () => {
    api.getAlbums.mockResolvedValue({ albums: [], total: 0 });
    renderPage();

    const button = screen.getByRole("button", { name: /create/i });
    expect(button).toBeDisabled();
  });
});
