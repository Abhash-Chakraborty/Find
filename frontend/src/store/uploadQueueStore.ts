import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { JobStatus, UploadResponse, UploadResult } from "@/lib/api";

export type UploadProcessingState =
  | "queued"
  | "processing"
  | "indexed"
  | "failed";

export type UploadQueueItem = UploadResult & {
  jobStatus?: JobStatus["status"];
  processingState?: UploadProcessingState;
  processingStage?: string;
};

type UploadQueueState = {
  phase: "idle" | "uploading";
  uploadProgress: number;
  items: UploadQueueItem[];
  beginUpload: () => void;
  setUploadProgress: (progress: number) => void;
  completeUpload: (response: UploadResponse) => void;
  failUpload: () => void;
  updateJob: (job: JobStatus) => void;
  clearCompleted: () => void;
  clearAll: () => void;
};

export const STAGE_PROGRESS: Record<string, number> = {
  queued: 8,
  started: 16,
  processing: 20,
  "loading image": 22,
  "extracting exif": 34,
  "generating mock metadata": 48,
  "detecting objects": 48,
  "generating caption": 62,
  "running ocr": 74,
  "generating embedding": 88,
  "indexing complete": 96,
  "detecting faces": 96,
  "clustering queued": 98,
  indexed: 100,
  failed: 100,
};

export function getProcessingState(
  status?: JobStatus["status"],
): UploadProcessingState {
  if (status === "finished") return "indexed";
  if (status === "failed") return "failed";
  if (status === "started") return "processing";
  return "queued";
}

export function getUploadItemProgress(item: UploadQueueItem): number {
  if (item.status === "failed" || item.processingState === "failed") return 100;
  if (item.processingState === "indexed") return 100;
  const normalizedStage = item.processingStage?.trim().toLowerCase();
  if (normalizedStage && STAGE_PROGRESS[normalizedStage] !== undefined) {
    return STAGE_PROGRESS[normalizedStage] ?? 0;
  }
  if (item.processingState === "processing" || item.jobStatus === "started") {
    return STAGE_PROGRESS.processing ?? 20;
  }
  if (item.processingState === "queued" || item.jobStatus === "queued") {
    return STAGE_PROGRESS.queued ?? 8;
  }
  return 0;
}

function hydrateResults(response: UploadResponse): UploadQueueItem[] {
  return response.results.map((result) => ({
    ...result,
    jobStatus: result.status === "uploaded" ? "queued" : undefined,
    processingState: result.status === "uploaded" ? "queued" : undefined,
  }));
}

export const useUploadQueueStore = create<UploadQueueState>()(
  persist(
    (set) => ({
      phase: "idle",
      uploadProgress: 0,
      items: [],
      beginUpload: () => set({ phase: "uploading", uploadProgress: 1 }),
      setUploadProgress: (progress) =>
        set({ uploadProgress: Math.max(1, Math.min(99, progress)) }),
      completeUpload: (response) =>
        set((state) => ({
          phase: "idle",
          uploadProgress: 100,
          items: [...hydrateResults(response), ...state.items],
        })),
      failUpload: () => set({ phase: "idle", uploadProgress: 0 }),
      updateJob: (job) =>
        set((state) => ({
          items: state.items.map((item) =>
            item.job_id === job.job_id
              ? {
                  ...item,
                  jobStatus: job.status,
                  processingState: getProcessingState(job.status),
                  processingStage: job.stage,
                  error:
                    job.status === "failed"
                      ? (job.error ?? item.error)
                      : item.error,
                }
              : item,
          ),
        })),
      clearCompleted: () =>
        set((state) => ({
          items: state.items.filter(
            (item) =>
              item.status === "failed" || item.processingState === "failed",
          ),
          uploadProgress: 0,
        })),
      clearAll: () => set({ items: [], phase: "idle", uploadProgress: 0 }),
    }),
    {
      name: "find-upload-queue-v1",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ items: state.items }),
    },
  ),
);
