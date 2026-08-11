import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  getImageDetail: vi.fn(),
  toggleLike: vi.fn(),
  deleteImage: vi.fn(),
  reprocessImage: vi.fn(),
  submitCaptionCorrection: vi.fn(),
  submitObjectCorrection: vi.fn(),
}));

vi.mock("next/image", () => ({
  // biome-ignore lint/performance/noImgElement: test mock only
  default: ({ alt }: { alt: string }) => <img alt={alt} />,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("@/lib/api", () => ({
  getImageDetail: apiMocks.getImageDetail,
  toggleLike: apiMocks.toggleLike,
  deleteImage: apiMocks.deleteImage,
  reprocessImage: apiMocks.reprocessImage,
  submitCaptionCorrection: apiMocks.submitCaptionCorrection,
  submitObjectCorrection: apiMocks.submitObjectCorrection,
}));

import { ImagePreviewModal } from "@/components/image-preview-modal";

function mockClipboard(writeText: ReturnType<typeof vi.fn>) {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
    writable: true,
  });
}

const BASE_MEDIA = {
  id: 1,
  filename: "photo.jpg",
  url: "https://cdn.example.com/photo.jpg",
  status: "indexed" as const,
  liked: false,
};

function detailFor(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    filename: "photo.jpg",
    minio_key: "images/aa/photo.jpg",
    file_hash: "hash",
    status: "indexed",
    created_at: "2026-01-01T00:00:00Z",
    url: "https://cdn.example.com/photo.jpg",
    liked: false,
    ...overrides,
  };
}

function renderModal(
  props: Partial<React.ComponentProps<typeof ImagePreviewModal>> = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <ImagePreviewModal
        media={BASE_MEDIA}
        onClose={vi.fn()}
        syncUrl={false}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { queryClient, ...utils };
}

// The sidebar (delete, reprocess, copy caption) lives in a details panel
// that's collapsed by default; open it before interacting with anything in it.
async function openDetails() {
  fireEvent.click(screen.getByLabelText("Show image details"));
  await waitFor(() =>
    expect(screen.getByLabelText("Hide image details")).toBeInTheDocument(),
  );
}

beforeEach(() => {
  apiMocks.getImageDetail.mockReset();
  apiMocks.toggleLike.mockReset();
  apiMocks.deleteImage.mockReset();
  apiMocks.reprocessImage.mockReset();
  apiMocks.submitCaptionCorrection.mockReset();
  apiMocks.submitObjectCorrection.mockReset();
  apiMocks.getImageDetail.mockResolvedValue(detailFor());
  mockClipboard(vi.fn().mockResolvedValue(undefined));
});

describe("ImagePreviewModal", () => {
  it("renders the dialog for the given image", async () => {
    renderModal();

    await waitFor(() =>
      expect(
        screen.getByRole("dialog", { name: "Image details" }),
      ).toBeInTheDocument(),
    );
  });

  it("closes on Escape", async () => {
    const onClose = vi.fn();
    renderModal({ onClose });
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    fireEvent.keyDown(window, { key: "Escape" });

    expect(onClose).toHaveBeenCalled();
  });

  it("navigates via arrow keys only when a neighbor is available", async () => {
    const onPrevious = vi.fn();
    const onNext = vi.fn();
    renderModal({ hasPrevious: true, hasNext: false, onPrevious, onNext });
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    fireEvent.keyDown(window, { key: "ArrowRight" });
    fireEvent.keyDown(window, { key: "ArrowLeft" });

    expect(onNext).not.toHaveBeenCalled();
    expect(onPrevious).toHaveBeenCalledTimes(1);
  });

  it("toggles like optimistically", async () => {
    apiMocks.toggleLike.mockResolvedValue({ id: 1, liked: true });
    renderModal();
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    const likeButton = screen.getAllByLabelText("Like image").at(0);
    if (!likeButton) throw new Error("Like button not found");
    fireEvent.click(likeButton);

    await waitFor(() => expect(apiMocks.toggleLike).toHaveBeenCalledWith(1));
    await waitFor(() =>
      expect(screen.getAllByLabelText("Unlike image").length).toBeGreaterThan(
        0,
      ),
    );
  });

  it("requires a second click before deleting, and Cancel backs out", async () => {
    apiMocks.deleteImage.mockResolvedValue({ id: 1, message: "deleted" });
    const onClose = vi.fn();
    const onDeleted = vi.fn();
    renderModal({ onClose, onDeleted });
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    await openDetails();

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(
      screen.getByText("Delete this image permanently?"),
    ).toBeInTheDocument();
    expect(apiMocks.deleteImage).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(
      screen.queryByText("Delete this image permanently?"),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(apiMocks.deleteImage).toHaveBeenCalledWith(1));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith(1));
    expect(onClose).toHaveBeenCalled();
  });

  it("retries analysis for a failed image", async () => {
    apiMocks.getImageDetail.mockResolvedValue(
      detailFor({ status: "failed", error: "model unavailable" }),
    );
    apiMocks.reprocessImage.mockResolvedValue({
      media_id: 1,
      job_id: "job-1",
      status: "queued",
    });
    renderModal({ media: { ...BASE_MEDIA, status: "failed" } });
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    await openDetails();

    fireEvent.click(
      await screen.findByRole("button", { name: "Retry analysis" }),
    );

    await waitFor(() =>
      expect(apiMocks.reprocessImage).toHaveBeenCalledWith(1),
    );
  });

  it("resets the delete confirmation when the image changes", async () => {
    const { queryClient, rerender } = renderModal();
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    await openDetails();

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(
      screen.getByText("Delete this image permanently?"),
    ).toBeInTheDocument();

    rerender(
      <QueryClientProvider client={queryClient}>
        <ImagePreviewModal
          media={{ ...BASE_MEDIA, id: 2, filename: "other.jpg" }}
          onClose={vi.fn()}
          syncUrl={false}
        />
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(
        screen.queryByText("Delete this image permanently?"),
      ).not.toBeInTheDocument(),
    );
  });

  it("resets the copy-to-clipboard indicator when the image changes", async () => {
    apiMocks.getImageDetail.mockResolvedValue(
      detailFor({ metadata: { caption: "A sunny day" } }),
    );
    const { queryClient, rerender } = renderModal();
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    await openDetails();
    await waitFor(() =>
      expect(
        screen.getByLabelText("Copy caption to clipboard"),
      ).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByLabelText("Copy caption to clipboard"));
    await waitFor(() =>
      expect(
        screen.getByLabelText("Caption copied to clipboard"),
      ).toBeInTheDocument(),
    );

    apiMocks.getImageDetail.mockResolvedValue(
      detailFor({ id: 2, metadata: { caption: "A rainy day" } }),
    );
    rerender(
      <QueryClientProvider client={queryClient}>
        <ImagePreviewModal
          media={{ ...BASE_MEDIA, id: 2, filename: "other.jpg" }}
          onClose={vi.fn()}
          syncUrl={false}
        />
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(
        screen.getByLabelText("Copy caption to clipboard"),
      ).toBeInTheDocument(),
    );
  });

  it("submits a caption correction for training", async () => {
    apiMocks.submitCaptionCorrection.mockResolvedValue({ status: "ok" });
    apiMocks.getImageDetail.mockResolvedValue(
      detailFor({ metadata: { caption: "A dog" } }),
    );
    renderModal();
    await openDetails();

    fireEvent.click(
      await screen.findByRole("button", { name: "Edit caption for training" }),
    );
    fireEvent.change(screen.getByLabelText("Edit caption for training"), {
      target: { value: "A golden retriever on a beach" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save caption" }));

    await waitFor(() =>
      expect(apiMocks.submitCaptionCorrection).toHaveBeenCalledWith(
        BASE_MEDIA.id,
        "A golden retriever on a beach",
      ),
    );
  });

  it("does not submit a correction that was cancelled", async () => {
    apiMocks.getImageDetail.mockResolvedValue(
      detailFor({ metadata: { caption: "A dog" } }),
    );
    renderModal();
    await openDetails();

    fireEvent.click(
      await screen.findByRole("button", { name: "Edit caption for training" }),
    );
    fireEvent.change(screen.getByLabelText("Edit caption for training"), {
      target: { value: "Discarded text" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    // Back to the collapsed button, and nothing sent.
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Edit caption for training" }),
      ).toBeInTheDocument(),
    );
    expect(apiMocks.submitCaptionCorrection).not.toHaveBeenCalled();

    // Reopening must not still hold the discarded draft.
    fireEvent.click(
      screen.getByRole("button", { name: "Edit caption for training" }),
    );
    expect(
      (
        screen.getByLabelText(
          "Edit caption for training",
        ) as HTMLTextAreaElement
      ).value,
    ).toBe("A dog");
  });
});
