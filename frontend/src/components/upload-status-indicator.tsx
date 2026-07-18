"use client";

import { useQueryClient } from "@tanstack/react-query";
import { AlertCircle } from "lucide-react";
import { useEffect, useMemo } from "react";
import { getJobStatus } from "@/lib/api";
import {
  getUploadItemProgress,
  useUploadQueueStore,
} from "@/store/uploadQueueStore";

export function UploadQueueMonitor() {
  const queryClient = useQueryClient();
  const items = useUploadQueueStore((state) => state.items);
  const phase = useUploadQueueStore((state) => state.phase);
  const updateJob = useUploadQueueStore((state) => state.updateJob);
  const clearCompleted = useUploadQueueStore((state) => state.clearCompleted);
  const activeJobs = useMemo(
    () =>
      items.filter(
        (item) =>
          item.job_id &&
          item.status === "uploaded" &&
          item.processingState !== "indexed" &&
          item.processingState !== "failed",
      ),
    [items],
  );

  useEffect(() => {
    if (activeJobs.length === 0) return;
    let cancelled = false;
    const poll = async () => {
      const settled = await Promise.allSettled(
        activeJobs.map((item) => getJobStatus(item.job_id ?? "")),
      );
      if (cancelled) return;
      let terminalUpdate = false;
      for (const result of settled) {
        if (result.status !== "fulfilled") continue;
        updateJob(result.value);
        terminalUpdate ||=
          result.value.status === "finished" ||
          result.value.status === "failed";
      }
      if (terminalUpdate) {
        void queryClient.invalidateQueries({ queryKey: ["gallery"] });
        void queryClient.invalidateQueries({ queryKey: ["gallery-infinite"] });
      }
    };
    void poll();
    const interval = window.setInterval(() => void poll(), 2500);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [activeJobs, queryClient, updateJob]);

  useEffect(() => {
    if (phase !== "idle" || items.length === 0 || activeJobs.length > 0) return;
    if (
      items.some(
        (item) => item.status === "failed" || item.processingState === "failed",
      )
    ) {
      return;
    }
    const timer = window.setTimeout(clearCompleted, 1800);
    return () => window.clearTimeout(timer);
  }, [activeJobs.length, clearCompleted, items, phase]);

  return null;
}

export function useUploadStatus() {
  const phase = useUploadQueueStore((state) => state.phase);
  const uploadProgress = useUploadQueueStore((state) => state.uploadProgress);
  const items = useUploadQueueStore((state) => state.items);
  const tracked = items.filter((item) => item.status === "uploaded");
  const failed = items.some(
    (item) => item.status === "failed" || item.processingState === "failed",
  );
  const active = tracked.filter(
    (item) =>
      item.processingState !== "indexed" && item.processingState !== "failed",
  );
  const percent =
    phase === "uploading"
      ? uploadProgress
      : tracked.length > 0
        ? Math.round(
            tracked.reduce(
              (total, item) => total + getUploadItemProgress(item),
              0,
            ) / tracked.length,
          )
        : failed
          ? 100
          : 0;
  return {
    active: phase === "uploading" || active.length > 0 || failed,
    activeCount:
      phase === "uploading" ? Math.max(1, active.length) : active.length,
    failed,
    percent,
    phase,
  };
}

export function UploadStatusRing({ size = 24 }: { size?: number }) {
  const status = useUploadStatus();
  if (!status.active) return null;
  const radius = 9;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - status.percent / 100);

  return (
    <span
      className="relative inline-grid shrink-0 place-items-center"
      style={{ width: size, height: size }}
      role="progressbar"
      aria-label={
        status.failed ? "Upload failed" : "Upload and indexing progress"
      }
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={status.percent}
    >
      <svg
        viewBox="0 0 24 24"
        className="h-full w-full -rotate-90"
        aria-hidden="true"
      >
        <circle
          cx="12"
          cy="12"
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          className="opacity-20"
        />
        <circle
          cx="12"
          cy="12"
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-[stroke-dashoffset] duration-500"
        />
      </svg>
      {status.failed ? <AlertCircle className="absolute h-3 w-3" /> : null}
    </span>
  );
}
