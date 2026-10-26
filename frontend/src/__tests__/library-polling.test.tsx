import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UploadQueueMonitor } from "@/components/upload-status-indicator";
import { LIBRARY_SETTLE_MS, useLibraryBusy } from "@/lib/use-library-busy";
import { useUploadQueueStore } from "@/store/uploadQueueStore";

const api = vi.hoisted(() => ({
  getGalleryCounts: vi.fn(),
  getJobStatus: vi.fn(),
}));

vi.mock("@/lib/api", () => api);

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function queueUpload(jobId: string) {
  useUploadQueueStore.getState().completeUpload({
    total: 1,
    results: [
      {
        filename: `${jobId}.jpg`,
        status: "uploaded",
        media_id: 1,
        job_id: jobId,
      },
    ],
  });
}

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: state,
  });
  document.dispatchEvent(new Event("visibilitychange"));
}

beforeEach(() => {
  vi.useFakeTimers();
  localStorage.clear();
  useUploadQueueStore.getState().clearAll();
  api.getGalleryCounts.mockResolvedValue({
    all: 3,
    indexed: 3,
    processing: 0,
    failed: 0,
  });
  api.getJobStatus.mockResolvedValue({ job_id: "job-1", status: "started" });
});

afterEach(() => {
  cleanup();
  setVisibility("visible");
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("useLibraryBusy", () => {
  it("is idle when nothing is processing", async () => {
    const { result } = renderHook(() => useLibraryBusy(), { wrapper });
    await act(() => vi.advanceTimersByTimeAsync(0));

    expect(result.current).toBe(false);
    // An idle library doesn't keep asking the server.
    await act(() => vi.advanceTimersByTimeAsync(60_000));
    expect(api.getGalleryCounts).toHaveBeenCalledTimes(1);
  });

  it("stays busy for a while after this tab's uploads settle", async () => {
    queueUpload("job-1");
    const { result } = renderHook(() => useLibraryBusy(), { wrapper });
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(result.current).toBe(true);

    act(() => {
      useUploadQueueStore
        .getState()
        .updateJob({ job_id: "job-1", status: "finished" });
    });
    // Clustering runs after indexing, so pages keep polling briefly.
    expect(result.current).toBe(true);
    await act(() => vi.advanceTimersByTimeAsync(LIBRARY_SETTLE_MS));
    expect(result.current).toBe(false);
  });

  it("is busy while the server reports processing images", async () => {
    api.getGalleryCounts.mockResolvedValue({
      all: 3,
      indexed: 2,
      processing: 1,
      failed: 0,
    });
    const { result } = renderHook(() => useLibraryBusy(), { wrapper });
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(result.current).toBe(true);

    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(api.getGalleryCounts).toHaveBeenCalledTimes(2);
  });
});

describe("UploadQueueMonitor", () => {
  it("polls running jobs every 2.5 s, not after every response", async () => {
    queueUpload("job-1");
    render(<UploadQueueMonitor />, { wrapper });
    await act(() => vi.advanceTimersByTimeAsync(100));
    expect(api.getJobStatus).toHaveBeenCalledTimes(1);

    await act(() => vi.advanceTimersByTimeAsync(2500));
    expect(api.getJobStatus).toHaveBeenCalledTimes(2);
  });

  it("skips job polls while the tab is hidden and catches up when shown", async () => {
    queueUpload("job-1");
    render(<UploadQueueMonitor />, { wrapper });
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(api.getJobStatus).toHaveBeenCalledTimes(1);

    setVisibility("hidden");
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    expect(api.getJobStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      setVisibility("visible");
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(api.getJobStatus).toHaveBeenCalledTimes(2);
  });
});
