"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  CheckCircle,
  Image as ImageIcon,
  Loader2,
  Package,
  Upload,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";
import {
  extractErrorMessage,
  getJobStatus,
  type JobStatus,
  type UploadResponse,
  type UploadResult,
  uploadImages,
  uploadImagesBulk,
} from "@/lib/api";

type UploadMode = "single" | "bulk";
type ProcessingState = "queued" | "processing" | "indexed" | "failed";

type UploadListItem = UploadResult & {
  jobStatus?: JobStatus["status"];
  processingState?: ProcessingState;
  processingStage?: string;
};

function hydrateResults(response: UploadResponse) {
  return response.results.map<UploadListItem>((result) => ({
    ...result,
    jobStatus: result.status === "uploaded" ? "queued" : undefined,
    processingState: result.status === "uploaded" ? "queued" : undefined,
  }));
}

function getProcessingState(jobStatus?: JobStatus["status"]): ProcessingState {
  if (jobStatus === "finished") {
    return "indexed";
  }
  if (jobStatus === "failed") {
    return "failed";
  }
  if (jobStatus === "started") {
    return "processing";
  }
  return "queued";
}

function getDisplayStatus(item: UploadListItem) {
  if (item.status === "duplicate") {
    return "duplicate";
  }
  if (item.status === "failed") {
    return "upload failed";
  }
  if (item.processingState === "indexed") {
    return "indexed";
  }
  if (item.processingState === "failed") {
    return "processing failed";
  }
  if (item.processingState === "processing") {
    return "processing";
  }
  return "queued";
}

function getDisplayStage(item: UploadListItem) {
  if (item.status !== "uploaded") {
    return null;
  }
  if (item.processingState === "indexed") {
    return "indexed";
  }
  if (item.processingState === "failed") {
    return item.processingStage ?? "failed";
  }
  return item.processingStage ?? item.processingState ?? "queued";
}

function getStatusClasses(item: UploadListItem) {
  if (item.status === "duplicate") {
    return "accent-badge status-pending";
  }
  if (item.status === "failed" || item.processingState === "failed") {
    return "accent-badge status-failed";
  }
  if (item.processingState === "indexed") {
    return "accent-badge status-indexed";
  }
  if (item.processingState === "processing") {
    return "accent-badge status-processing";
  }
  return "accent-badge status-default";
}

export default function UploadPage() {
  const [uploadedFiles, setUploadedFiles] = useState<UploadListItem[]>([]);
  const [mode, setMode] = useState<UploadMode>("single");
  const queryClient = useQueryClient();

  const parsedUploadLimit = Number(
    process.env.NEXT_PUBLIC_MAX_UPLOAD_SIZE_MB ?? "50",
  );
  const maxUploadSizeMb =
    Number.isFinite(parsedUploadLimit) && parsedUploadLimit > 0
      ? Math.floor(parsedUploadLimit)
      : 50;

  const parsedBulkLimit = Number(
    process.env.NEXT_PUBLIC_MAX_BULK_FILES ?? "200",
  );
  const maxBulkFiles =
    Number.isFinite(parsedBulkLimit) && parsedBulkLimit > 0
      ? Math.floor(parsedBulkLimit)
      : 200;

  const uploadMutation = useMutation({
    mutationFn: uploadImages,
    onSuccess: (data) => {
      setUploadedFiles((prev) => [...hydrateResults(data), ...prev]);
      void queryClient.invalidateQueries({ queryKey: ["gallery"] });
      toast.success(
        `Queued ${data.total} file${data.total === 1 ? "" : "s"} for analysis`,
      );
    },
    onError: (error) => {
      toast.error(extractErrorMessage(error, "Upload failed"));
    },
  });

  const bulkUploadMutation = useMutation({
    mutationFn: uploadImagesBulk,
    onSuccess: (data) => {
      setUploadedFiles((prev) => [...hydrateResults(data), ...prev]);
      void queryClient.invalidateQueries({ queryKey: ["gallery"] });
      const uploadedCount = data.results.filter(
        (item) => item.status === "uploaded",
      ).length;
      const failedResults = data.results.filter(
        (item) => item.status === "failed" && item.error,
      );
      toast.success(
        `Archive accepted (${uploadedCount} new upload${
          uploadedCount === 1 ? "" : "s"
        })`,
      );
      if (failedResults.length > 0) {
        toast.error(
          failedResults.length === 1
            ? failedResults[0]?.error
            : `${failedResults.length} files failed. ${failedResults[0]?.error}`,
        );
      }
    },
    onError: (error) => {
      toast.error(extractErrorMessage(error, "Bulk upload failed"));
    },
  });

  const isUploading = uploadMutation.isPending || bulkUploadMutation.isPending;

  const activeJobs = useMemo(
    () =>
      uploadedFiles.filter(
        (item) =>
          item.job_id &&
          item.status === "uploaded" &&
          item.processingState !== "indexed" &&
          item.processingState !== "failed",
      ),
    [uploadedFiles],
  );

  useEffect(() => {
    if (activeJobs.length === 0) {
      return;
    }

    let cancelled = false;

    const pollJobs = async () => {
      const jobStatuses = await Promise.all(
        activeJobs.map(async (item) => {
          if (!item.job_id) {
            return null;
          }

          try {
            return await getJobStatus(item.job_id);
          } catch {
            return {
              job_id: item.job_id,
              status: "failed",
              error: "Could not reach the job status endpoint.",
            } as JobStatus;
          }
        }),
      );

      if (cancelled) {
        return;
      }

      if (
        jobStatuses.some(
          (job) => job?.status === "finished" || job?.status === "failed",
        )
      ) {
        void queryClient.invalidateQueries({ queryKey: ["gallery"] });
      }

      setUploadedFiles((current) =>
        current.map((item) => {
          if (!item.job_id) {
            return item;
          }

          const job = jobStatuses.find(
            (entry) => entry?.job_id === item.job_id,
          );
          if (!job) {
            return item;
          }

          const processingState = getProcessingState(job.status);
          return {
            ...item,
            jobStatus: job.status,
            processingState,
            processingStage: job.stage,
            error:
              processingState === "failed"
                ? (job.error ?? item.error)
                : item.error,
          };
        }),
      );
    };

    void pollJobs();
    const intervalId = window.setInterval(() => {
      void pollJobs();
    }, 3000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [activeJobs, queryClient]);

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles.length === 0) {
        toast.error("No valid images selected");
        return;
      }

      uploadMutation.mutate(acceptedFiles);
    },
    [uploadMutation],
  );

  const onBulkDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles.length === 0) {
        toast.error("No archive selected");
        return;
      }

      const [archive] = acceptedFiles;
      if (!archive) {
        toast.error("No archive selected");
        return;
      }

      bulkUploadMutation.mutate(archive);
    },
    [bulkUploadMutation],
  );

  const {
    getRootProps: getSingleRootProps,
    getInputProps: getSingleInputProps,
    isDragActive: isSingleDragActive,
    fileRejections: singleRejections,
  } = useDropzone({
    onDrop,
    accept: {
      "image/jpeg": [".jpg", ".jpeg"],
      "image/png": [".png"],
      "image/webp": [".webp"],
      "image/gif": [".gif"],
    },
    maxSize: maxUploadSizeMb * 1024 * 1024,
    multiple: true,
    disabled: mode !== "single" || isUploading,
  });

  const {
    getRootProps: getBulkRootProps,
    getInputProps: getBulkInputProps,
    isDragActive: isBulkDragActive,
    fileRejections: bulkRejections,
  } = useDropzone({
    onDrop: onBulkDrop,
    accept: {
      "application/zip": [".zip"],
      "application/x-zip-compressed": [".zip"],
    },
    maxFiles: 1,
    multiple: false,
    disabled: mode !== "bulk" || isUploading,
  });

  const activeRootProps =
    mode === "single" ? getSingleRootProps : getBulkRootProps;
  const activeInputProps =
    mode === "single" ? getSingleInputProps : getBulkInputProps;
  const isDragActive =
    mode === "single" ? isSingleDragActive : isBulkDragActive;
  const fileRejections = mode === "single" ? singleRejections : bulkRejections;

  const helperText = useMemo(() => {
    if (mode === "single") {
      return `JPEG, PNG, WebP, GIF. Max ${maxUploadSizeMb}MB each`;
    }

    return `ZIP archive up to ${maxBulkFiles} images`;
  }, [mode, maxUploadSizeMb, maxBulkFiles]);

  const stats = useMemo(
    () => ({
      queued: uploadedFiles.filter((item) => item.processingState === "queued")
        .length,
      processing: uploadedFiles.filter(
        (item) => item.processingState === "processing",
      ).length,
      indexed: uploadedFiles.filter(
        (item) => item.processingState === "indexed",
      ).length,
      failed: uploadedFiles.filter(
        (item) => item.status === "failed" || item.processingState === "failed",
      ).length,
      duplicates: uploadedFiles.filter((item) => item.status === "duplicate")
        .length,
    }),
    [uploadedFiles],
  );

  const showActions = stats.indexed > 0 || stats.duplicates > 0;

  return (
    <div className="page-shell">
      <div className="container-shell max-w-3xl py-10 md:py-14">
        <div className="page-enter mb-10 text-center">
          <h1 className="section-heading mb-4 text-5xl font-medium md:text-6xl">
            Upload
          </h1>
          <p className="muted-copy mx-auto max-w-xl text-sm leading-6">
            Add images to analyze. Search and clustering update as jobs finish.
          </p>
        </div>

        <div className="delayed-enter mb-5 flex justify-center">
          <div className="frost-panel flex rounded-full p-1">
            <button
              type="button"
              aria-pressed={mode === "single"}
              onClick={() => setMode("single")}
              className={`rounded-full px-5 py-2 text-sm font-medium transition ${
                mode === "single"
                  ? "bg-white text-black"
                  : "text-[color:var(--silver)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--near-white)]"
              }`}
            >
              Files
            </button>
            <button
              type="button"
              aria-pressed={mode === "bulk"}
              onClick={() => setMode("bulk")}
              className={`rounded-full px-5 py-2 text-sm font-medium transition ${
                mode === "bulk"
                  ? "bg-white text-black"
                  : "text-[color:var(--silver)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--near-white)]"
              }`}
            >
              ZIP
            </button>
          </div>
        </div>

        <div
          {...activeRootProps()}
          className={`frost-panel scan-line cursor-pointer rounded-3xl p-10 text-center transition md:p-14 ${
            isDragActive
              ? "scale-[1.01] border-[color:var(--blue)] bg-[var(--blue-soft)]"
              : "hover:border-[var(--frost-strong)] hover:bg-[color:var(--frost-soft)]"
          } ${isUploading ? "pointer-events-none opacity-50" : ""}`}
        >
          <input {...activeInputProps()} />

          <div className="mx-auto mb-5 grid h-14 w-14 place-items-center rounded-full border border-[var(--frost)] bg-[color:var(--frost-soft)]">
            {mode === "single" ? (
              <Upload className="h-6 w-6 text-[color:var(--blue)]" />
            ) : (
              <Package className="h-6 w-6 text-[color:var(--orange)]" />
            )}
          </div>

          <p className="mb-2 text-base font-medium text-[color:var(--near-white)]">
            {isDragActive
              ? "Drop to upload"
              : mode === "single"
                ? "Drop images here"
                : "Drop a ZIP archive here"}
          </p>

          <p className="text-sm text-[color:var(--silver)]">{helperText}</p>
        </div>
        {fileRejections.length > 0 && (
          <div className="mt-6 rounded-3xl border border-[var(--red-soft)] bg-[var(--red-soft)] p-4">
            <p className="mb-2 text-sm font-medium text-[#ff9bab]">
              Some files were rejected:
            </p>
            <ul className="space-y-1 text-sm text-[#ff9bab]/85">
              {fileRejections.map(({ file, errors }) => (
                <li key={file.name}>
                  {file.name}: {errors[0]?.message}
                </li>
              ))}
            </ul>
          </div>
        )}

        {(isUploading || activeJobs.length > 0) && (
          <div className="frost-panel mt-8 flex items-center gap-4 rounded-3xl p-4">
            <Loader2 className="h-5 w-5 animate-spin text-[color:var(--blue)]" />
            <div>
              <p className="text-sm font-medium text-[color:var(--near-white)]">
                {isUploading
                  ? "Uploading"
                  : `Analyzing ${activeJobs.length} image${
                      activeJobs.length === 1 ? "" : "s"
                    }`}
              </p>
              <p className="text-xs text-[color:var(--silver)]">
                Indexing updates live.
              </p>
            </div>
          </div>
        )}

        {showActions && (
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link
              href="/gallery"
              className="white-pill px-5 py-2.5 text-sm font-semibold"
            >
              Open gallery
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/clusters"
              className="frost-button px-5 py-2.5 text-sm font-medium"
            >
              View clusters
            </Link>
          </div>
        )}

        {uploadedFiles.length > 0 && (
          <div className="page-enter mt-12">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-medium text-[color:var(--near-white)]">
                Recent uploads
              </h3>
              <span className="text-xs text-[color:var(--silver)]">
                {uploadedFiles.length} total
              </span>
            </div>
            <div className="space-y-2">
              {uploadedFiles.map((result) => {
                const displayStatus = getDisplayStatus(result);
                const displayStage = getDisplayStage(result);

                return (
                  <div
                    key={`${result.job_id ?? result.media_id ?? result.filename}-${result.status}`}
                    className="frost-panel flex items-center justify-between gap-4 rounded-2xl px-4 py-3"
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      {result.status === "duplicate" ? (
                        <ImageIcon className="h-4 w-4 shrink-0 text-[#ffe08a]" />
                      ) : result.status === "failed" ||
                        result.processingState === "failed" ? (
                        <XCircle className="h-4 w-4 shrink-0 text-[#ff9bab]" />
                      ) : result.processingState === "indexed" ? (
                        <CheckCircle className="h-4 w-4 shrink-0 text-[#7dffc7]" />
                      ) : (
                        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-[color:var(--blue)]" />
                      )}

                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-[color:var(--near-white)]">
                          {result.filename}
                        </p>
                        {displayStage && (
                          <p className="truncate text-xs text-[color:var(--silver)]">
                            {displayStage}
                          </p>
                        )}
                        {result.processingState === "failed" &&
                          result.error && (
                            <p className="truncate text-xs text-[#ff9bab]">
                              {result.error}
                            </p>
                          )}
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <span className={getStatusClasses(result)}>
                        {displayStatus}
                      </span>

                      {result.status === "duplicate" &&
                        result.media_id != null && (
                          <Link
                            href={`/gallery?media=${result.media_id}`}
                            className="text-xs text-[color:var(--blue)] hover:underline"
                          >
                            View existing
                          </Link>
                        )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
