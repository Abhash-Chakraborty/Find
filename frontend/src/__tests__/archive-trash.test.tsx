/**
 * Component tests for the Archive and Trash pages (frontend for Phase 4.4).
 *
 * Run with: pnpm vitest run src/__tests__/archive-trash.test.tsx
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
import ArchivePage from "../app/archive/page";
import TrashPage from "../app/trash/page";

const api = vi.hoisted(() => ({
  getArchive: vi.fn(),
  getTrash: vi.fn(),
  setArchive: vi.fn(),
  restoreImage: vi.fn(),
  emptyTrash: vi.fn(),
}));

vi.mock("@/lib/api", () => api);
vi.mock("@/lib/media", () => ({ resolveMediaUrl: (u: string) => u }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

const mediaItem = (id: number) => ({
  id,
  filename: `img-${id}.jpg`,
  minio_key: `images/test/${id}.jpg`,
  status: "indexed" as const,
  created_at: "2026-03-01T00:00:00+00:00",
  thumbnail_url: `/api/image/${id}/thumbnail`,
});

const listResponse = (ids: number[]) => ({
  items: ids.map(mediaItem),
  total: ids.length,
  skip: 0,
  page: 1,
  limit: 50,
});

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset();
});

afterEach(() => cleanup());

describe("TrashPage", () => {
  it("shows empty state", async () => {
    api.getTrash.mockResolvedValue(listResponse([]));
    renderWithClient(<TrashPage />);
    await waitFor(() =>
      expect(screen.getByTestId("trash-empty")).toBeInTheDocument(),
    );
  });

  it("shows an error state when loading fails", async () => {
    api.getTrash.mockRejectedValue(new Error("boom"));
    renderWithClient(<TrashPage />);
    await waitFor(() =>
      expect(screen.getByTestId("trash-error")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("trash-empty")).toBeNull();
  });

  it("lists trashed items and restores one", async () => {
    api.getTrash.mockResolvedValue(listResponse([1, 2]));
    api.restoreImage.mockResolvedValue({ id: 1, deleted_at: null });
    renderWithClient(<TrashPage />);

    await waitFor(() =>
      expect(screen.getByTestId("trash-item-1")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("restore-1"));
    await waitFor(() => expect(api.restoreImage).toHaveBeenCalledWith(1));
  });

  it("empties the trash", async () => {
    api.getTrash.mockResolvedValue(listResponse([1]));
    api.emptyTrash.mockResolvedValue({
      message: "Trash emptied",
      deleted_ids: [1],
      missing_ids: [],
      failed_ids: [],
      deleted_count: 1,
      missing_count: 0,
      failed_count: 0,
    });
    renderWithClient(<TrashPage />);

    await waitFor(() =>
      expect(screen.getByTestId("empty-trash")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("empty-trash"));
    await waitFor(() => expect(api.emptyTrash).toHaveBeenCalled());
  });
});

describe("ArchivePage", () => {
  it("shows empty state", async () => {
    api.getArchive.mockResolvedValue(listResponse([]));
    renderWithClient(<ArchivePage />);
    await waitFor(() =>
      expect(screen.getByTestId("archive-empty")).toBeInTheDocument(),
    );
  });

  it("shows an error state when loading fails", async () => {
    api.getArchive.mockRejectedValue(new Error("boom"));
    renderWithClient(<ArchivePage />);
    await waitFor(() =>
      expect(screen.getByTestId("archive-error")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("archive-empty")).toBeNull();
  });

  it("lists archived items and unarchives one", async () => {
    api.getArchive.mockResolvedValue(listResponse([5]));
    api.setArchive.mockResolvedValue({ id: 5, is_archived: false });
    renderWithClient(<ArchivePage />);

    await waitFor(() =>
      expect(screen.getByTestId("archive-item-5")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId("unarchive-5"));
    await waitFor(() => expect(api.setArchive).toHaveBeenCalledWith(5, false));
  });
});
