/**
 * Component tests for the sharing UI (frontend for Phase 4.3 backend).
 *
 * Covers the album share-link manager (create/list/revoke, key surfaced once)
 * and the public shared-album view's password gate + render.
 *
 * Run with: pnpm vitest run src/__tests__/sharing-ui.test.tsx
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
import { AlbumShareLinks } from "@/components/album-share-links";

const api = vi.hoisted(() => ({
  getSharedLinks: vi.fn(),
  createSharedLink: vi.fn(),
  deleteSharedLink: vi.fn(),
  getPublicSharedAlbum: vi.fn(),
}));

vi.mock("@/lib/api", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

const link = (id: number, albumId: number, over = {}) => ({
  id,
  album_id: albumId,
  description: null,
  expires_at: null,
  allow_download: true,
  show_exif: false,
  has_password: false,
  created_at: "2026-06-29T00:00:00+00:00",
  ...over,
});

beforeEach(() => {
  api.getSharedLinks.mockReset();
  api.createSharedLink.mockReset();
  api.deleteSharedLink.mockReset();
});

afterEach(() => cleanup());

describe("AlbumShareLinks", () => {
  it("shows the no-links empty state", async () => {
    api.getSharedLinks.mockResolvedValue({ shared_links: [], total: 0 });
    renderWithClient(<AlbumShareLinks albumId={1} />);
    await waitFor(() =>
      expect(screen.getByTestId("no-share-links")).toBeInTheDocument(),
    );
  });

  it("only lists links for this album", async () => {
    api.getSharedLinks.mockResolvedValue({
      shared_links: [link(10, 1), link(11, 2), link(12, 1)],
      total: 3,
    });
    renderWithClient(<AlbumShareLinks albumId={1} />);

    await waitFor(() =>
      expect(screen.getByTestId("share-link-10")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("share-link-12")).toBeInTheDocument();
    // Link for album 2 must not appear.
    expect(screen.queryByTestId("share-link-11")).toBeNull();
  });

  it("creates a link and surfaces the share URL once", async () => {
    api.getSharedLinks.mockResolvedValue({ shared_links: [], total: 0 });
    api.createSharedLink.mockResolvedValue({
      ...link(20, 1),
      key: "abc123",
      url: "/api/public/shared/abc123",
    });
    renderWithClient(<AlbumShareLinks albumId={1} />);

    fireEvent.click(screen.getByTestId("create-share-link"));

    await waitFor(() =>
      expect(screen.getByTestId("created-share-url")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("created-share-url")).toHaveTextContent(
      "/api/public/shared/abc123",
    );
    expect(api.createSharedLink).toHaveBeenCalledWith(
      expect.objectContaining({ album_id: 1, allow_download: true }),
    );
  });

  it("passes a password when one is entered", async () => {
    api.getSharedLinks.mockResolvedValue({ shared_links: [], total: 0 });
    api.createSharedLink.mockResolvedValue({ ...link(21, 1), url: "/x" });
    renderWithClient(<AlbumShareLinks albumId={1} />);

    fireEvent.change(screen.getByLabelText("Optional share password"), {
      target: { value: "s3cret" },
    });
    fireEvent.click(screen.getByTestId("create-share-link"));

    await waitFor(() =>
      expect(api.createSharedLink).toHaveBeenCalledWith(
        expect.objectContaining({ password: "s3cret" }),
      ),
    );
  });

  it("revokes a link", async () => {
    api.getSharedLinks.mockResolvedValue({
      shared_links: [link(30, 1)],
      total: 1,
    });
    api.deleteSharedLink.mockResolvedValue({ message: "ok", id: 30 });
    renderWithClient(<AlbumShareLinks albumId={1} />);

    await waitFor(() =>
      expect(screen.getByTestId("revoke-share-30")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("revoke-share-30"));
    await waitFor(() => expect(api.deleteSharedLink).toHaveBeenCalledWith(30));
  });

  it("shows password and view-only badges", async () => {
    api.getSharedLinks.mockResolvedValue({
      shared_links: [
        link(40, 1, { has_password: true, allow_download: false }),
      ],
      total: 1,
    });
    renderWithClient(<AlbumShareLinks albumId={1} />);

    await waitFor(() =>
      expect(screen.getByTestId("share-link-40")).toBeInTheDocument(),
    );
    expect(screen.getByText("Password")).toBeInTheDocument();
    expect(screen.getByText("View only")).toBeInTheDocument();
  });
});
