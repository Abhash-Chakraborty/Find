import { beforeEach, describe, expect, it } from "vitest";
import {
  getUploadItemProgress,
  useUploadQueueStore,
} from "@/store/uploadQueueStore";

describe("persistent upload queue", () => {
  beforeEach(() => {
    localStorage.clear();
    useUploadQueueStore.getState().clearAll();
  });

  it("tracks upload, indexing progress, and clears completed work", () => {
    const queue = useUploadQueueStore.getState();
    queue.beginUpload();
    queue.setUploadProgress(52);
    expect(useUploadQueueStore.getState()).toMatchObject({
      phase: "uploading",
      uploadProgress: 52,
    });

    queue.completeUpload({
      total: 1,
      results: [
        {
          filename: "memory.jpg",
          status: "uploaded",
          media_id: 7,
          job_id: "job-7",
        },
      ],
    });
    let item = useUploadQueueStore.getState().items[0];
    expect(item?.processingState).toBe("queued");

    queue.updateJob({
      job_id: "job-7",
      status: "started",
      stage: "generating caption",
    });
    item = useUploadQueueStore.getState().items[0];
    expect(item?.processingState).toBe("processing");
    expect(item ? getUploadItemProgress(item) : 0).toBe(62);

    queue.updateJob({ job_id: "job-7", status: "finished" });
    item = useUploadQueueStore.getState().items[0];
    expect(item?.processingState).toBe("indexed");
    expect(item ? getUploadItemProgress(item) : 0).toBe(100);

    queue.clearCompleted();
    expect(useUploadQueueStore.getState().items).toEqual([]);
  });

  it("persists queued job identifiers for navigation and reload recovery", () => {
    useUploadQueueStore.getState().completeUpload({
      total: 1,
      results: [
        {
          filename: "persistent.jpg",
          status: "uploaded",
          job_id: "persistent-job",
        },
      ],
    });

    expect(localStorage.getItem("find-upload-queue-v1")).toContain(
      "persistent-job",
    );
  });
});
