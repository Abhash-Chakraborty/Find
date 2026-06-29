/**
 * Component tests for the AddToAlbumModal.
 *
 * Run with: pnpm vitest run src/__tests__/add-to-album-modal.test.tsx
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
import { AddToAlbumModal } from "@/components/add-to-album-modal";

const api = vi.hoisted(() => ({
  getAlbums: vi.fn(),
  createAlbum: vi.fn(),
  addAlbumAssets: vi.fn(),
}));

vi.mock("@/lib/api", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderModal(
  props: Partial<Parameters<typeof AddToAlbumModal>[0]> = {},
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const onClose = props.onClose ?? vi.fn();
  const onAdded = props.onAdded ?? vi.fn();
  render(
    <QueryClientProvider client={client}>
      <AddToAlbumModal
        mediaIds={props.mediaIds ?? [1, 2]}
        onClose={onClose}
        onAdded={onAdded}
      />
    </QueryClientProvider>,
  );
  return { onClose, onAdded };
}

const album = (id: number, name: string, count = 0) => ({
  id,
  name,
  description: null,
  cover_media_id: null,
  cover_thumbnail_url: null,
  asset_count: count,
  created_at: null,
  updated_at: null,
});

beforeEach(() => {
  api.getAlbums.mockReset();
  api.createAlbum.mockReset();
  api.addAlbumAssets.mockReset();
});

afterEach(() => cleanup());

describe("AddToAlbumModal", () => {
  it("lists existing albums to pick from", async () => {
    api.getAlbums.mockResolvedValue({
      albums: [album(1, "Trip"), album(2, "Pets")],
      total: 2,
    });
    renderModal();
    await waitFor(() =>
      expect(screen.getByTestId("pick-album-1")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("pick-album-2")).toBeInTheDocument();
  });

  it("adds selected media to a picked album", async () => {
    api.getAlbums.mockResolvedValue({ albums: [album(1, "Trip")], total: 1 });
    api.addAlbumAssets.mockResolvedValue({
      added_ids: [1, 2],
      skipped_ids: [],
      added_count: 2,
    });
    const { onAdded, onClose } = renderModal({ mediaIds: [1, 2] });

    fireEvent.click(await screen.findByTestId("pick-album-1"));

    await waitFor(() =>
      expect(api.addAlbumAssets).toHaveBeenCalledWith(1, [1, 2]),
    );
    await waitFor(() => expect(onAdded).toHaveBeenCalled());
    expect(onClose).toHaveBeenCalled();
  });

  it("creates a new album and adds to it", async () => {
    api.getAlbums.mockResolvedValue({ albums: [], total: 0 });
    api.createAlbum.mockResolvedValue(album(9, "Holiday"));
    api.addAlbumAssets.mockResolvedValue({
      added_ids: [1, 2],
      skipped_ids: [],
      added_count: 2,
    });
    renderModal({ mediaIds: [1, 2] });

    fireEvent.change(screen.getByLabelText("New album name"), {
      target: { value: "Holiday" },
    });
    fireEvent.click(screen.getByTestId("create-and-add"));

    await waitFor(() =>
      expect(api.createAlbum).toHaveBeenCalledWith({ name: "Holiday" }),
    );
    await waitFor(() =>
      expect(api.addAlbumAssets).toHaveBeenCalledWith(9, [1, 2]),
    );
  });

  it("shows a hint when there are no albums", async () => {
    api.getAlbums.mockResolvedValue({ albums: [], total: 0 });
    renderModal();
    await waitFor(() =>
      expect(screen.getByTestId("no-albums-hint")).toBeInTheDocument(),
    );
  });

  it("closes via the close button", async () => {
    api.getAlbums.mockResolvedValue({ albums: [], total: 0 });
    const { onClose } = renderModal();
    fireEvent.click(screen.getByTestId("add-to-album-close"));
    expect(onClose).toHaveBeenCalled();
  });

  it("closes on Escape", async () => {
    api.getAlbums.mockResolvedValue({ albums: [], total: 0 });
    const { onClose } = renderModal();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
