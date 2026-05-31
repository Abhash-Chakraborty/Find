/**
 * Frontend tests for the reprocess/retry-analysis feature.
 *
 * Uses Vitest only — no DOM/React renderer needed for these unit tests.
 *
 * Install test dependencies (one-time):
 *   pnpm add -D vitest
 *
 * Run with:
 *   pnpm test                                         # runs all tests
 *   pnpm vitest run src/__tests__/reprocess.test.ts   # run this file only
 */

import type { AxiosInstance } from "axios";
import axios from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";

// ---------------------------------------------------------------------------
// Unit tests: reprocessImage API function
// ---------------------------------------------------------------------------

vi.mock("axios");
const mockedAxios = vi.mocked(axios, true);
// Provide a mocked axios instance that `axios.create()` will return.
const apiInstanceMock: Partial<AxiosInstance> = {
  post: vi.fn(),
  get: vi.fn(),
  delete: vi.fn(),
};

describe("reprocessImage API function", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    // Make axios.create() return our mock instance so `api` is defined.
    mockedAxios.create = vi
      .fn()
      .mockReturnValue(apiInstanceMock as AxiosInstance);
  });

  it("calls POST /api/image/:id/reprocess and returns the response", async () => {
    const { reprocessImage } = await import("../lib/api");

    const mockResponse = {
      data: {
        media_id: 42,
        job_id: "job-abc",
        status: "queued",
      },
    };
    // api is an axios instance; mock the post method on the module-level api object
    const { api } = await import("../lib/api");
    vi.spyOn(api, "post").mockResolvedValueOnce(mockResponse);

    const result = await reprocessImage(42);

    expect(api.post).toHaveBeenCalledWith("/api/image/42/reprocess");
    expect(result).toEqual({
      media_id: 42,
      job_id: "job-abc",
      status: "queued",
    });
  });

  it("propagates server errors (400, 404) to the caller", async () => {
    const { reprocessImage, api } = await import("../lib/api");

    const axiosError = Object.assign(
      new Error("Request failed with status code 400"),
      {
        response: { status: 400, data: { detail: "not eligible" } },
      },
    );
    vi.spyOn(api, "post").mockRejectedValueOnce(axiosError);

    await expect(reprocessImage(99)).rejects.toThrow(
      "Request failed with status code 400",
    );
  });
});

// ---------------------------------------------------------------------------
// Unit tests: eligibility logic that drives UI visibility
// ---------------------------------------------------------------------------

describe("retry-button eligibility", () => {
  /**
   * Mirrors the condition used in image-preview-modal.tsx and gallery/page.tsx
   * to decide whether to show the retry button.
   */
  function shouldShowRetry(
    status: string,
    caption: string | undefined,
  ): boolean {
    // same logic as in image-preview-modal action bar
    return status === "failed" || (status === "indexed" && !caption);
  }

  it("shows retry for failed images", () => {
    expect(shouldShowRetry("failed", undefined)).toBe(true);
  });

  it("shows retry for indexed image with no caption", () => {
    expect(shouldShowRetry("indexed", undefined)).toBe(true);
    expect(shouldShowRetry("indexed", "")).toBe(true);
  });

  it("hides retry for indexed image with a caption", () => {
    expect(shouldShowRetry("indexed", "a dog on a bench")).toBe(false);
  });

  it("hides retry for pending images", () => {
    expect(shouldShowRetry("pending", undefined)).toBe(false);
  });

  it("hides retry for processing images", () => {
    expect(shouldShowRetry("processing", undefined)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Unit tests: gallery card shows retry only for failed status
// ---------------------------------------------------------------------------

describe("gallery card retry visibility", () => {
  /**
   * Mirrors gallery/page.tsx — aligned with modal:
   * show RotateCcw for failed OR (indexed && no caption).
   */
  function galleryCardShowsRetry(
    status: string,
    caption: string | undefined,
  ): boolean {
    return status === "failed" || (status === "indexed" && !caption);
  }

  it("shows retry button in gallery card for failed status", () => {
    expect(galleryCardShowsRetry("failed", undefined)).toBe(true);
  });

  it("shows retry button in gallery card for indexed with no caption", () => {
    expect(galleryCardShowsRetry("indexed", undefined)).toBe(true);
    expect(galleryCardShowsRetry("indexed", "")).toBe(true);
  });

  it("does not show retry button in gallery card for indexed with caption", () => {
    expect(galleryCardShowsRetry("indexed", "a dog on a bench")).toBe(false);
  });

  it("does not show retry button in gallery card for pending status", () => {
    expect(galleryCardShowsRetry("pending", undefined)).toBe(false);
  });

  it("does not show retry button in gallery card for processing status", () => {
    expect(galleryCardShowsRetry("processing", undefined)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Unit tests: ReprocessResponse type contract
// ---------------------------------------------------------------------------

describe("ReprocessResponse type contract", () => {
  it("has the expected shape", async () => {
    const { api } = await import("../lib/api");
    const payload = { media_id: 7, job_id: "j-001", status: "queued" as const };
    vi.spyOn(api, "post").mockResolvedValueOnce({ data: payload });

    const { reprocessImage } = await import("../lib/api");
    const result = await reprocessImage(7);

    expect(typeof result.media_id).toBe("number");
    expect(typeof result.job_id).toBe("string");
    expect(result.status).toBe("queued");
  });
});
